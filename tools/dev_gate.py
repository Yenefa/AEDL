"""Development Verification Gate — the single development verification entry.

One command for local agents, local humans and CI:

    python -m tools.dev_gate [--envelope tasks/GH-N.yaml] [--receipt PATH]

Exit codes:
    0  PASS          candidate change satisfies the development verification set
    1  FAIL          at least one check failed
    2  GATE_BROKEN   the gate itself could not run (infrastructure, not the candidate)

The JSON receipt is a development verification receipt, NOT formal Evidence.
Formal Evidence is produced by gates/run_gates.py (Evidence Gate) and lives
under notes/*/generated + docs/evidence. A receipt never promotes anything:
promotion is a human merge.

One entry, one PASS semantics on every platform (LF byte baseline via
.gitattributes, GH-20):
    syntax         compileall gates tools tests sandbox_runtime
    main_tests     full main repo unit test suite (3.9 interpreter, same as CI)
    sandbox_tests  sandbox_runtime unit tests via uv (excluded if uv missing)
    secret_scan    high-confidence secret patterns (same set as the former CI job)
    scope_check    working diff vs envelope allowed/forbidden paths (only with --envelope)

Checks that cannot run in this environment are reported in excluded_checks
with an explicit reason — never silently skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from tools.admit import SCHEMA_VERSION as ADMIT_SCHEMA_VERSION
from tools.envelope import parse_envelope, scope_violations

GATE_VERSION = "1"
SCHEMA_VERSION = "dev-gate.v1"
# GH-20: LF byte baseline (.gitattributes) removed the platform exclusions —
# the full test set runs on every platform with one PASS semantics.
EXCLUDE_DIRS = {".git", ".pio", "node_modules", "__pycache__", ".venv", "dist", "build"}
SECRET_PATTERNS = [
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{22,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _run(cmd, cwd, timeout=1800, tail=2000) -> dict:
    started = time.monotonic()
    try:
        completed = subprocess.run(cmd, cwd=str(cwd), capture_output=True, timeout=timeout)
        out = (completed.stdout or b"").decode("utf-8", errors="replace")
        err = (completed.stderr or b"").decode("utf-8", errors="replace")
        detail = (out + "\n" + err).strip()[-tail:]
        return {
            "status": "pass" if completed.returncode == 0 else "fail",
            "exit_code": completed.returncode,
            "detail": detail or None,
            "duration_s": round(time.monotonic() - started, 1),
        }
    except Exception as exc:
        return {
            "status": "error",
            "exit_code": None,
            "detail": f"{type(exc).__name__}: {exc}",
            "duration_s": round(time.monotonic() - started, 1),
        }


class GitCommandError(RuntimeError):
    """A git primitive failed: never interpret as clean / no changes."""


def git_checked(root, *args) -> str:
    try:
        completed = subprocess.run(["git", *args], cwd=str(root), capture_output=True, timeout=60)
    except Exception as exc:
        raise GitCommandError(f"git {' '.join(args)} could not run: {type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        raise GitCommandError(f"git {' '.join(args)} failed (rc={completed.returncode}): {err[:200]}")
    return (completed.stdout or b"").decode("utf-8", errors="replace").strip()


def resolve_python() -> list:
    env = os.environ.get("AEDL_PYTHON")
    if env:
        return env.split()
    candidates = []
    if sys.platform == "win32":
        candidates.append(["py", "-3"])
    candidates.append(["python"])
    candidates.append(["python3"])
    for candidate in candidates:
        try:
            probe = subprocess.run(candidate + ["--version"], capture_output=True, timeout=30)
            if probe.returncode == 0:
                return candidate
        except Exception:
            continue
    raise RuntimeError("no python interpreter found (set AEDL_PYTHON)")


def changed_files(root) -> list:
    tracked = [p for p in git_checked(root, "diff", "HEAD", "--name-only").splitlines() if p]
    status = git_checked(root, "status", "--porcelain")
    untracked = [line[3:].strip() for line in status.splitlines() if line.startswith("?? ")]
    return sorted({p for p in tracked + untracked if p})


COMPILEALL_EXCLUDE = r"\.venv|\.pio|node_modules|__pycache__|dist|build"


def aggregate_checks(checks: dict) -> tuple:
    """pass/0, fail/1, broken/2: any infrastructure error wins over FAIL."""
    statuses = [c.get("status") for c in checks.values()]
    if any(s == "error" for s in statuses):
        return "broken", 2
    if any(s == "fail" for s in statuses):
        return "fail", 1
    return "pass", 0


def check_syntax(py, root) -> dict:
    """compileall over the repo's own sources; toolchain dirs (.venv/.pio/
    node_modules) are excluded so a local virtualenv cannot fail the gate."""
    cmd = py + ["-m", "compileall", "-q", "-x", COMPILEALL_EXCLUDE,
                "gates", "tools", "tests", "sandbox_runtime"]
    return _run(cmd, root, timeout=300)


def check_main_tests(py, root) -> tuple:
    """Full main-repo unit test suite on every platform (LF byte baseline)."""
    cmd = py + ["-S", "-m", "unittest", "discover", "-s", "tests"]
    return _run(cmd, root), []


def _uv_available() -> bool:
    try:
        probe = subprocess.run(["uv", "--version"], capture_output=True, timeout=30)
        return probe.returncode == 0
    except Exception:
        return False


def check_sandbox_tests(root) -> tuple:
    """sandbox_tests is a REQUIRED check (GH-20 one-PASS semantics): uv missing
    is GATE_BROKEN, not an excluded/skipped check."""
    if not _uv_available():
        return {"status": "error", "exit_code": 2,
                "detail": "uv unavailable: sandbox_tests is required — GATE_BROKEN (no silent exclusions)",
                "duration_s": 0.0}, []
    cmd = ["uv", "run", "--frozen", "--project", "sandbox_runtime",
           "python", "-m", "unittest", "discover", "-s", "sandbox_runtime/tests", "-p", "test_*.py"]
    return _run(cmd, root), []


def _secret_scan_targets(root) -> list:
    """Tracked files plus untracked files that are NOT git-ignored.

    Scanning ignored directories (e.g. intake research clones / venvs such as
    notes/open_source_intake/_circuitbot_venv/) produced false positives; only
    files that git would actually track or stage can leak into the repo.
    """
    targets = []
    for extra in ([], ["--others", "--exclude-standard"]):
        cmd = ["git", "ls-files", "-z"] + extra
        try:
            proc = subprocess.run(cmd, cwd=root, capture_output=True)
        except OSError as exc:
            raise RuntimeError(f"secret_scan cannot execute git: {exc}") from exc
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"secret_scan git ls-files failed (exit={proc.returncode}): {stderr}"
            )
        targets.extend(
            p for p in proc.stdout.decode("utf-8", errors="surrogateescape").split(chr(0)) if p
        )
    return [Path(root) / p for p in targets if p]


def check_secret_scan(root) -> dict:
    started = time.monotonic()
    hits, scanned = [], 0
    try:
        targets = _secret_scan_targets(root)
    except RuntimeError as exc:
        return {
            "status": "fail",
            "exit_code": 1,
            "detail": f"secret scan target enumeration failed: {exc}",
            "duration_s": round(time.monotonic() - started, 1),
        }
    for path in targets:
        try:
            size = path.stat().st_size
        except OSError as exc:
            return {
                "status": "fail",
                "exit_code": 1,
                "detail": f"secret scan cannot stat {path.relative_to(root)}: {exc}",
                "duration_s": round(time.monotonic() - started, 1),
            }
        if size > 1_000_000:
            # Stream large files line-by-line instead of skipping them: they are
            # still scanned (no silent skip), and read failures stay fail-closed.
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                            hits.append(str(path.relative_to(root)))
                            break
            except OSError as exc:
                return {
                    "status": "fail",
                    "exit_code": 1,
                    "detail": f"secret scan cannot read {path.relative_to(root)}: {exc}",
                    "duration_s": round(time.monotonic() - started, 1),
                }
            scanned += 1
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return {
                "status": "fail",
                "exit_code": 1,
                "detail": f"secret scan cannot read {path.relative_to(root)}: {exc}",
                "duration_s": round(time.monotonic() - started, 1),
            }
        scanned += 1
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            hits.append(str(path.relative_to(root)))
    if hits:
        return {"status": "fail", "exit_code": 1, "detail": "secret patterns found:\n" + "\n".join(hits),
                "duration_s": round(time.monotonic() - started, 1)}
    return {"status": "pass", "exit_code": 0, "detail": f"scanned {scanned} text files",
            "duration_s": round(time.monotonic() - started, 1)}


def envelope_binding_mismatch(declared: str, current: str) -> tuple:
    """Pure TOCTOU check: the envelope used at the gate must be byte-identical
    to the envelope admitted. Control-state changes after admission require
    a re-admit."""
    if not declared or len(declared) != 64:
        return False, "admit receipt lacks a valid envelope_sha256 (too old or malformed)"
    if declared != current:
        return False, (
            f"TOCTOU: envelope changed after admission (admit@{declared[:12]}, "
            f"now@{current[:12]}) — control state changed; re-admit before executing"
        )
    return True, f"envelope bound to admission (sha256 {current[:12]})"


def check_binding(root, envelope_path, admit_receipt_path) -> tuple:
    """Admission binding: proves the exact task/control state was ADMITTED
    (verdict ADMIT, exit 0) on the exact envelope and HEAD being verified.
    With an envelope, an admit receipt is REQUIRED — a missing receipt means
    the gate cannot prove admission and the candidate fails."""
    if not envelope_path:
        return None, [{"id": "binding_check", "reason": "no --envelope provided (binding not applicable)"}]
    if not admit_receipt_path:
        return {"status": "fail", "exit_code": 1,
                "detail": "envelope provided without --admit-receipt: cannot prove admission (binding required)",
                "duration_s": 0.0}, []
    path = Path(envelope_path)
    if not path.is_file():
        return {"status": "error", "exit_code": 2, "detail": f"envelope not found: {envelope_path}",
                "duration_s": 0.0}, []
    receipt_path = Path(admit_receipt_path)
    if not receipt_path.is_file():
        return {"status": "error", "exit_code": 2, "detail": f"admit receipt not found: {admit_receipt_path}",
                "duration_s": 0.0}, []
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "exit_code": 2, "detail": f"admit receipt unreadable: {type(exc).__name__}: {exc}",
                "duration_s": 0.0}, []
    if not isinstance(receipt, dict):
        return {"status": "error", "exit_code": 2, "detail": "admit receipt is not a JSON object",
                "duration_s": 0.0}, []
    problems = []
    if receipt.get("schema_version") != ADMIT_SCHEMA_VERSION:
        problems.append(f"receipt schema != {ADMIT_SCHEMA_VERSION}")
    if receipt.get("verdict") != "ADMIT" or receipt.get("exit_code") != 0:
        problems.append("receipt is not an ADMIT (verdict/exit_code) — a BLOCKED receipt cannot bind")
    declared = receipt.get("envelope_sha256")
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    if declared != current:
        problems.append(f"envelope changed after admission (admit@{str(declared)[:12]}, now@{current[:12]})")
    admitted_head = (receipt.get("git") or {}).get("head_sha")
    current_head = git_checked(root, "rev-parse", "HEAD")
    if not admitted_head or admitted_head != current_head:
        problems.append(f"HEAD moved after admission (admit@{str(admitted_head)[:12] or 'none'}, now@{current_head[:12]}) — re-admit")
    if problems:
        return {"status": "fail", "exit_code": 1,
                "detail": "admission binding broken: " + "; ".join(problems),
                "duration_s": 0.0}, []
    return {"status": "pass", "exit_code": 0,
            "detail": f"admission bound (envelope {current[:12]}, HEAD {current_head[:12]})",
            "duration_s": 0.0}, []


def check_scope(root, envelope_path) -> tuple:
    if not envelope_path:
        return None, [{"id": "scope_check", "reason": "no --envelope provided"}]
    path = Path(envelope_path)
    if not path.is_file():
        return {"status": "error", "exit_code": 2, "detail": f"envelope not found: {envelope_path}",
                "duration_s": 0.0}, []
    envelope = parse_envelope(path.read_text(encoding="utf-8"))
    if envelope["errors"]:
        return {"status": "error", "exit_code": 2, "detail": "envelope parse errors:\n" + "\n".join(envelope["errors"]),
                "duration_s": 0.0}, []
    files = changed_files(root)
    violations = scope_violations(files, envelope)
    if violations:
        return {"status": "fail", "exit_code": 1, "detail": "scope violations:\n" + "\n".join(violations),
                "duration_s": 0.0}, []
    detail = (f"changed {len(files)} file(s) in scope; "
              f"allowed={len(envelope['allowed_paths'])} forbidden={len(envelope['forbidden_paths'])}")
    return {"status": "pass", "exit_code": 0, "detail": detail, "duration_s": 0.0}, []


def run_gate(root=None, envelope=None, dry_run=False, receipt_path=None, interpreter=None, admit_receipt=None) -> dict:
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    started = time.monotonic()
    baseline = git_checked(root, "rev-parse", "HEAD")
    branch = git_checked(root, "branch", "--show-current")
    porcelain = git_checked(root, "status", "--porcelain")
    dirty = bool(porcelain)
    if not baseline and not dry_run:
        raise RuntimeError(f"not a git repository: {root}")
    checks, excluded = {}, []
    if dry_run:
        checks = {
            "syntax": {"status": "pending", "detail": "dry-run"},
            "main_tests": {"status": "pending", "detail": "dry-run"},
            "sandbox_tests": {"status": "pending", "detail": "dry-run"},
            "secret_scan": {"status": "pending", "detail": "dry-run"},
        }
        status = "pending"
        exit_code = 1
    else:
        py = interpreter or resolve_python()
        syntax = check_syntax(py, root)
        main, excl_main = check_main_tests(py, root)
        sandbox, excl_sand = check_sandbox_tests(root)
        secret = check_secret_scan(root)
        scope, excl_scope = check_scope(root, envelope)
        binding, excl_binding = check_binding(root, envelope, admit_receipt)
        checks = {"syntax": syntax, "main_tests": main, "sandbox_tests": sandbox, "secret_scan": secret}
        if scope is not None:
            checks["scope_check"] = scope
        if binding is not None:
            checks["binding_check"] = binding
        excluded = excl_main + excl_sand + excl_scope + excl_binding
        status, exit_code = aggregate_checks(checks)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "gate_version": GATE_VERSION,
        "status": status,
        "exit_code": exit_code,
        "baseline_sha": baseline or None,
        "branch": branch or None,
        "dirty": dirty,
        "platform": sys.platform,
        "checks": checks,
        "excluded_checks": excluded,
        "flags": {"envelope": envelope or None, "admit_receipt": admit_receipt or None},
        "envelope_sha256": (
            hashlib.sha256(Path(envelope).read_bytes()).hexdigest()
            if envelope and Path(envelope).is_file() else None
        ),
        "run_at": utc_now(),
        "duration_s": round(time.monotonic() - started, 1),
    }
    if receipt_path:
        Path(receipt_path).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    parser.add_argument("--envelope", default=None)
    parser.add_argument("--receipt", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--interpreter", default=None)
    parser.add_argument("--admit-receipt", default=None)
    args = parser.parse_args(argv)
    try:
        receipt = run_gate(args.root, args.envelope, args.dry_run, args.receipt, args.interpreter, args.admit_receipt)
    except Exception as exc:
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "gate_version": GATE_VERSION,
            "status": "broken",
            "exit_code": 2,
            "detail": f"{type(exc).__name__}: {exc}",
            "run_at": utc_now(),
        }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return int(receipt["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
