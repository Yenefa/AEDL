"""Review Bundle generator - local, automatic (CONTROL_PLANE.md section 8).

Any delivery that needs human review must ship a bundle; this tool makes that
mechanical. It runs automatically from the local post-commit hook
(scripts/post-commit.bundle.sh) and must also be run by the agent at delivery
time (AGENTS.md section 12):

    python -m tools.make_review_bundle [--run <name>] [--out <dir>] [--base <ref>]

Defaults:
    --run  sanitized current branch (e.g. feat/foo -> feat_foo)
    --out  <repo parent>/review-bundles/<run>   (OUTSIDE the repository by design)
    --base origin/master if present, else HEAD

Outputs:
    <run>-review.md            status + SHARED items + verification evidence + diff stat
    <run>-review-new-files.md  full content of new (untracked) text files
    <run>-source-diff.patch    real hunks vs base (untracked files as additions)
    manifest.json              machine-readable bundle manifest
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BUNDLE_SCHEMA = "review-bundle.v1"
MAX_PATCH_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 200 * 1024
FENCE = chr(96) * 3  # markdown code fence, built without backticks in source


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=str(root), capture_output=True, timeout=60)
    if completed.returncode != 0:
        err = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed (rc={completed.returncode}): {err[:200]}")
    return (completed.stdout or b"").decode("utf-8", errors="replace").strip()


def git_diff_no_index(root: Path, other: Path) -> str:
    """git diff --no-index exits 1 when files differ (normal), >1 on error."""
    completed = subprocess.run(
        ["git", "diff", "--no-index", "--", "/dev/null", str(other)],
        cwd=str(root), capture_output=True, timeout=60,
    )
    if completed.returncode > 1:
        err = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git diff --no-index failed (rc={completed.returncode}): {err[:200]}")
    return (completed.stdout or b"").decode("utf-8", errors="replace").strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_name_from_branch(branch: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", branch).strip("_")
    return cleaned or "candidate"


def shared_patterns(root: Path) -> list:
    """Parse the CODEOWNERS SHARED section so SHARED detection stays in sync
    with the ownership file instead of being hard-coded twice."""
    owners = root / ".github" / "CODEOWNERS"
    if not owners.is_file():
        return []
    patterns = []
    in_shared = False
    for raw in owners.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            in_shared = "SHARED" in line
            continue
        if in_shared:
            patterns.append(line.split()[0])
    return patterns


def codeowners_match(path: str, pattern: str) -> bool:
    """CODEOWNERS path semantics (review B2/P1 2026-09-02: Path.match is a
    right-anchored whole-tail matcher and silently returns False for every
    directory rule, so the generator used to report shared=[] for real hits).

    Rules implemented (subset used by this repo's CODEOWNERS):
      - trailing "/"  -> directory rule: root-anchored prefix, matches the
                         directory itself and everything below it
      - leading "/"    -> root-anchored file rule: exact path match
      - no "/" at all -> basename rule: matches in any directory
    """
    pat = pattern.strip()
    if not pat:
        return False
    if pat.endswith("/"):
        prefix = pat.strip("/")
        return path == prefix or path.startswith(prefix + "/")
    if pat.startswith("/"):
        return path == pat.lstrip("/")
    if "/" in pat:
        # contains slashes but not anchored: match relative to any directory
        # (tail match, which IS what Path.match is correct for)
        from pathlib import PurePosixPath
        return PurePosixPath(path).match(pat)
    from pathlib import PurePosixPath
    return PurePosixPath(path).name == pat


def is_text(path: Path, limit: int = 8192) -> bool:
    try:
        return b"\x00" not in path.read_bytes()[:limit]
    except Exception:
        return False


def collect_changes(root: Path, base: str) -> tuple:
    tracked = [p for p in git(root, "diff", "--name-only", base).splitlines() if p]
    untracked = [p for p in git(root, "ls-files", "--others", "--exclude-standard").splitlines() if p]
    return sorted(set(tracked)), sorted(set(untracked))


def build_patch(root: Path, base: str, tracked: list, untracked: list) -> str:
    parts = []
    size = 0
    if tracked:
        body = git(root, "diff", base)
        parts.append(body)
        size += len(body)
    for path in untracked:
        full = root / path
        if not is_text(full):
            parts.append(f"diff --git a/{path} b/{path}")
            parts.append("new file mode 100644")
            parts.append("(binary - see repository)")
            size += 200
            continue
        body = git_diff_no_index(root, full) or ""
        parts.append(body)
        size += len(body)
        if size > MAX_PATCH_BYTES:
            parts.append(f"# [patch truncated at {MAX_PATCH_BYTES} bytes]")
            break
    return "\n".join(parts)


def receipt_summaries(out: Path) -> list:
    """Summarize admit/gate receipts shipped inside the bundle directory.

    Review iteration 4 (2026-09-02): discovery used to scan the repository
    parent for loose receipt files, which (a) missed receipts placed next to
    the bundle — review.md then claimed "no receipts found" while the bundle
    dir held current receipts — and (b) happily summarized stale receipts from
    other runs. The bundle directory is the single source: this scan, the
    manifest.files inventory and the review.md evidence section all read the
    same files. "admit-receipt.json" matches both globs and is deduplicated.
    """
    found, seen = [], set()
    for pattern in ("*admit*.json", "*receipt*.json"):
        for path in sorted(out.glob(pattern)):
            if path.name.startswith("_") or path in seen:
                continue  # scratch/temp receipts are not evidence
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict) and ("verdict" in data or "status" in data):
                seen.add(path)
                found.append({
                    "file": path.name,
                    "verdict": data.get("verdict") or data.get("status"),
                    "exit_code": data.get("exit_code"),
                    "envelope_sha256": (data.get("envelope_sha256") or "")[:12] or None,
                })
    return found


def build_bundle(root: Path, run: str, base: str, out: Path, pr) -> dict:
    head = git(root, "rev-parse", "HEAD")
    branch = git(root, "branch", "--show-current") or "detached"
    tracked, untracked = collect_changes(root, base)
    changed = sorted(set(tracked) | set(untracked))
    patterns = shared_patterns(root)
    shared = [p for p in changed if any(codeowners_match(p, pat) for pat in patterns)]

    patch = build_patch(root, base, tracked, untracked)
    (out / f"{run}-source-diff.patch").write_text(patch, encoding="utf-8")

    new_lines = [
        f"# {run} - new (untracked) files full content",
        f"# generated {utc_now()} | base {base}",
        "",
    ]
    for path in untracked:
        full = root / path
        new_lines.append(f"\n## FILE: {path}")
        if not is_text(full):
            new_lines.append("(binary - see repository)")
            continue
        if full.stat().st_size > MAX_FILE_BYTES:
            new_lines.append(f"(content skipped: {full.stat().st_size} bytes > {MAX_FILE_BYTES})")
            continue
        new_lines.append(FENCE)
        new_lines.append(full.read_text(encoding="utf-8", errors="replace"))
        new_lines.append(FENCE)
    (out / f"{run}-review-new-files.md").write_text("\n".join(new_lines), encoding="utf-8")

    receipts = receipt_summaries(out)
    stat = git(root, "diff", "--stat", base)
    if untracked:
        stat = (stat + f"\n{len(untracked)} new file(s) (see -review-new-files.md)").strip()
    review = [
        f"# {run} - Review Bundle",
        "",
        f"> Auto-generated: {utc_now()} | schema {BUNDLE_SCHEMA}",
        "",
        "## Status",
        "",
        f"- repo: {root}",
        f"- branch: {branch} | HEAD: {head[:12]} | base: {base}",
        f"- changed: {len(changed)} (tracked {len(tracked)} / new {len(untracked)})",
        f"- PR: {pr or '(create after review)'}",
        "",
        "## SHARED items (derived from CODEOWNERS SHARED section)",
        "",
    ]
    if shared:
        review.append("\n".join(f"- {p}" for p in shared))
    else:
        review.append("- (no SHARED path changes)")
    review += [
        "",
        "## Verification evidence (receipt summaries)",
        "",
    ]
    if receipts:
        for r in receipts:
            line = f"- {r['file']}: {r['verdict']} exit={r['exit_code']}"
            if r.get("envelope_sha256"):
                line += f" envelope={r['envelope_sha256']}"
            review.append(line)
    else:
        review.append("- (no admit/gate receipt found - must be produced before delivery)")
    review += [
        "",
        "## Change summary",
        "",
        FENCE,
        stat,
        FENCE,
        "",
        "## New files (full content in -review-new-files.md)",
        "",
    ]
    review.append("\n".join(f"- {p}" for p in untracked) or "- (none)")
    review += [
        "",
        "## Risks and notes (reviewer fills in)",
        "",
        "- Platform/CI differences, Hash Domain (CONTROL_PLANE section 5), TOCTOU binding - verify as needed",
        "- Real hunks in -source-diff.patch (traceable to this bundle generation time)",
        "",
        "## Review commands",
        "",
        FENCE + "bash",
        f"cd {root}",
        "git status",
        f"git diff {base}",
        "git diff --check",
        FENCE,
        "",
    ]
    (out / f"{run}-review.md").write_text("\n".join(review), encoding="utf-8")

    manifest = {
        "schema": BUNDLE_SCHEMA,
        "run": run,
        "branch": branch,
        "base": base,
        "head_sha": head,
        "generated_at": utc_now(),
        "changed": changed,
        "shared": shared,
        # Review iteration 4: receipts shipped in the bundle dir are part of
        # the inventory and are summarized here — review.md evidence section,
        # manifest.receipts and manifest.files all derive from the same
        # receipt_summaries(out) scan (three views, one source).
        "files": [
            f"{run}-review.md",
            f"{run}-review-new-files.md",
            f"{run}-source-diff.patch",
            "manifest.json",
        ] + [r["file"] for r in receipts],
        "receipts": {
            r["file"]: (
                f"{r['verdict']} exit={r['exit_code']}"
                + (f" envelope={r['envelope_sha256']}" if r.get("envelope_sha256") else "")
            )
            for r in receipts
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--base", default=None)
    parser.add_argument("--pr", default=None)
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    if not (root / ".git").exists():
        print(f"not a git repository: {root}", file=sys.stderr)
        return 2
    try:
        branch = git(root, "branch", "--show-current") or "detached"
        run = args.run or run_name_from_branch(branch)
        has_master = bool(git(root, "rev-parse", "--verify", "-q", "origin/master"))
        base = args.base or ("origin/master" if has_master else "HEAD")
        out = Path(args.out) if args.out else root.parent / "review-bundles" / run
        out.mkdir(parents=True, exist_ok=True)
        manifest = build_bundle(root, run, base, out, args.pr)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"bundle generation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
