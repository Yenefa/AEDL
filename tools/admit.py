"""Admission check — run BEFORE any edit on a task (AGENTS.md §2.3).

Fail-closed: if admission cannot verify a precondition, the verdict is
BLOCKED with reasons. BLOCKED is not a refusal — it is the escalation entry:

    STOP → Explain → Escalate → Human Decision → Record → Resume / Reject

    python -m tools.admit --envelope tasks/GH-N.yaml

Flags record themselves in the receipt, and each is an escalation decision:
    --allow-dirty   tolerate an unclean working tree
    --allow-drift   tolerate HEAD != envelope base sha
    --skip-deps     do not verify dependency states (gh unavailable / waived)

Exit codes:
    0  ADMIT
    1  BLOCKED
    2  GATE_BROKEN  (admission itself could not run)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from tools.envelope import parse_envelope

SCHEMA_VERSION = "admit.v1"

EXCEPTION_FLAGS = ("allow_dirty", "allow_drift", "skip_deps")


def check_flag_exception(flag: str, exceptions: dict) -> tuple:
    """An override flag is only legal when the task envelope pre-authorizes it
    (permitted=True + authority, or granted_by + decision_ref). The agent can
    never self-authorize: a flag without an envelope exception is a bypass
    with audit, not an escalation."""
    exc = exceptions.get(flag)
    if not exc:
        return False, f"--{flag} has no pre-authorized exception in the envelope (agent cannot self-authorize; add exceptions.{flag} with granted_by/decision_ref or pre-authorize)"
    valid = (exc.get("permitted") is True and exc.get("authority")) or (
        exc.get("granted_by") and exc.get("decision_ref")
    )
    if not valid:
        return False, f"--{flag} exception is malformed (need permitted+authority or granted_by+decision_ref)"
    ref = exc.get("decision_ref") or exc.get("authority")
    return True, f"--{flag} exception granted: {ref}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class GitCommandError(RuntimeError):
    """A git primitive failed: the control plane must treat this as broken,
    never as 'clean' or 'no changes' (fail-closed)."""


def git_checked(root, *args) -> str:
    """Run a git command; non-zero exit raises (empty stdout is NOT success)."""
    try:
        completed = subprocess.run(["git", *args], cwd=str(root), capture_output=True, timeout=60)
    except Exception as exc:
        raise GitCommandError(f"git {' '.join(args)} could not run: {type(exc).__name__}: {exc}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
        raise GitCommandError(f"git {' '.join(args)} failed (rc={completed.returncode}): {err[:200]}")
    return (completed.stdout or b"").decode("utf-8", errors="replace").strip()


def git_ok(root, *args) -> bool:
    """Return-code based check (git cat-file -e prints nothing on success)."""
    try:
        completed = subprocess.run(["git", *args], cwd=str(root), capture_output=True, timeout=60)
        return completed.returncode == 0
    except Exception:
        return False


def ref_number(ref: str):
    match = re.search(r"(\d+)$", ref)
    return int(match.group(1)) if match else None


def gh_json(args, root) -> dict | None:
    """Returns parsed gh JSON, {'_error': ...} on gh failure, or None when gh
    is unavailable or not authenticated."""
    try:
        auth = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=30)
        if auth.returncode != 0:
            return None
        completed = subprocess.run(["gh", *args], cwd=str(root), capture_output=True, timeout=60)
        if completed.returncode != 0:
            err = (completed.stderr or b"").decode("utf-8", errors="replace").strip()[-500:]
            return {"_error": err or "gh command failed"}
        return json.loads((completed.stdout or b"{}").decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def dependency_satisfied(required_state: str, actual_state: dict) -> tuple:
    """Pure mapping required_state -> actual state, for unit testing."""
    state = (actual_state.get("state") or "").upper()
    if required_state == "merged":
        ok = state == "MERGED" or actual_state.get("mergedAt") is not None
        detail = "PR merged" if ok else f"PR state={state or 'UNKNOWN'} mergedAt={actual_state.get('mergedAt')}"
        return ok, detail
    if required_state == "closed":
        ok = state == "CLOSED"
        return ok, "issue closed" if ok else f"issue state={state or 'UNKNOWN'}"
    if required_state == "open":
        ok = state == "OPEN"
        return ok, "issue open" if ok else f"issue state={state or 'UNKNOWN'}"
    return False, f"unsupported required_state: {required_state}"


def check_dependencies(root, envelope) -> tuple:
    deps = envelope["dependencies"]
    if not deps:
        return {"id": "dependencies", "status": "ok", "detail": "none declared"}, []
    results, blocked, unknown = [], [], []
    for dep in deps:
        number = ref_number(dep["ref"])
        if number is None:
            results.append({"ref": dep["ref"], "status": "unknown", "detail": "cannot parse issue/PR number"})
            unknown.append(dep["ref"])
            continue
        if dep["required_state"] == "merged":
            state = gh_json(["pr", "view", str(number), "--json", "state,mergedAt"], root)
        else:
            state = gh_json(["issue", "view", str(number), "--json", "state"], root)
        if state is None:
            results.append({"ref": dep["ref"], "status": "unknown", "detail": "gh unavailable / not authenticated"})
            unknown.append(dep["ref"])
        elif "_error" in state:
            results.append({"ref": dep["ref"], "status": "unknown", "detail": state["_error"]})
            unknown.append(dep["ref"])
        else:
            ok, detail = dependency_satisfied(dep["required_state"], state)
            results.append({"ref": dep["ref"], "status": "ok" if ok else "blocked", "detail": detail})
            if not ok:
                blocked.append(dep["ref"])
    reasons = []
    if blocked:
        reasons.append("dependency not satisfied: " + ", ".join(blocked))
    if unknown:
        reasons.append("dependency state unknown: " + ", ".join(unknown) + " (verify manually or --skip-deps)")
    status = "blocked" if (blocked or unknown) else "ok"
    return {"id": "dependencies", "status": status, "detail": json.dumps(results, ensure_ascii=False)}, reasons


def run_admit(root=None, envelope_path=None, allow_dirty=False, allow_drift=False, skip_deps=False) -> dict:
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    started = time.monotonic()
    head = git_checked(root, "rev-parse", "HEAD")
    branch = git_checked(root, "branch", "--show-current")
    porcelain = git_checked(root, "status", "--porcelain")
    dirty = bool(porcelain)
    if not head:
        raise RuntimeError(f"not a git repository: {root}")
    checks, reasons = [], []
    exception_records = {}
    dirty_detail = f"{len(porcelain.splitlines())} dirty entr(y/ies)" if dirty else "clean"
    if dirty and not allow_dirty:
        reasons.append(f"repo dirty ({dirty_detail}) — clean or --allow-dirty (escalation)")
    checks.append({"id": "dirty", "status": "blocked" if (dirty and not allow_dirty) else "ok", "detail": dirty_detail})

    envelope = None
    if not envelope_path:
        reasons.append("no task envelope — substantial tasks require tasks/GH-N.yaml (AGENTS.md §2.3)")
        checks.append({"id": "envelope", "status": "blocked", "detail": "missing --envelope"})
    else:
        path = Path(envelope_path)
        if not path.is_file():
            reasons.append(f"envelope not found: {envelope_path}")
            checks.append({"id": "envelope", "status": "blocked", "detail": "file not found"})
        else:
            envelope = parse_envelope(path.read_text(encoding="utf-8"))
            if envelope["errors"]:
                reasons.append("envelope parse errors: " + "; ".join(envelope["errors"]))
                checks.append({"id": "envelope", "status": "blocked", "detail": "; ".join(envelope["errors"])})
            else:
                exceptions = envelope.get("exceptions", {})
                flags_used = [
                    f for f, used in (
                        ("allow_dirty", allow_dirty),
                        ("allow_drift", allow_drift),
                        ("skip_deps", skip_deps),
                    ) if used
                ]
                for flag in flags_used:
                    allowed, detail = check_flag_exception(flag, exceptions)
                    if not allowed:
                        reasons.append(detail)
                    else:
                        exception_records[flag] = detail
                checks.append({"id": "envelope", "status": "ok", "detail": f"task={envelope['task'] or 'UNSET'}"})
                if envelope["base_branch"] and envelope["base_branch"] != branch:
                    reasons.append(f"branch mismatch: envelope base={envelope['base_branch']}, current={branch}")
                    checks.append({"id": "base_branch", "status": "blocked", "detail": f"{envelope['base_branch']} != {branch}"})
                else:
                    checks.append({"id": "base_branch", "status": "ok", "detail": branch or "UNKNOWN"})
                sha = envelope["base_sha"]
                if not sha:
                    reasons.append("envelope base.sha missing")
                    checks.append({"id": "baseline", "status": "blocked", "detail": "envelope base.sha missing"})
                elif sha != head:
                    drift = f"baseline drift: envelope@{sha[:7]}, HEAD@{head[:7]}"
                    exists = git_ok(root, "cat-file", "-e", sha + "^{commit}")
                    if not exists:
                        reasons.append(f"envelope base.sha not in repository history: {sha}")
                        checks.append({"id": "baseline", "status": "blocked", "detail": drift})
                    elif not allow_drift:
                        reasons.append(drift + " — --allow-drift (escalation)")
                        checks.append({"id": "baseline", "status": "blocked", "detail": drift})
                    else:
                        checks.append({"id": "baseline", "status": "ok", "detail": drift + " (allowed)"})
                else:
                    checks.append({"id": "baseline", "status": "ok", "detail": sha[:7]})
                dep_check, dep_reasons = check_dependencies(root, envelope)
                skip_authorized = skip_deps and "skip_deps" in exception_records
                if dep_reasons and skip_authorized:
                    checks.append({**dep_check, "status": "waived",
                                   "detail": dep_check["detail"] + " (waived by authorized --skip-deps)"})
                elif dep_reasons and not skip_deps:
                    reasons.extend(dep_reasons)
                    checks.append({**dep_check, "status": "blocked"})
                else:
                    checks.append(dep_check)

    verdict = "ADMIT" if not reasons else "BLOCKED"
    envelope_sha256 = None
    if envelope_path and Path(envelope_path).is_file():
        envelope_sha256 = hashlib.sha256(Path(envelope_path).read_bytes()).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "verdict": verdict,
        "exit_code": 0 if verdict == "ADMIT" else 1,
        "envelope_sha256": envelope_sha256,
        "reasons": reasons,
        "checks": checks,
        "envelope": {
            "path": envelope_path or None,
            "task": (envelope or {}).get("task"),
            "base_branch": (envelope or {}).get("base_branch"),
            "base_sha": (envelope or {}).get("base_sha"),
            "dependency_count": len((envelope or {}).get("dependencies", [])),
            "allowed_count": len((envelope or {}).get("allowed_paths", [])),
            "forbidden_count": len((envelope or {}).get("forbidden_paths", [])),
        },
        "git": {"branch": branch, "head_sha": head, "dirty": dirty},
        "flags": {"allow_dirty": allow_dirty, "allow_drift": allow_drift, "skip_deps": skip_deps},
        "exceptions_used": exception_records,
        "run_at": utc_now(),
        "duration_s": round(time.monotonic() - started, 1),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    parser.add_argument("--envelope", required=True, help="path to tasks/GH-N.yaml")
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--allow-drift", action="store_true")
    parser.add_argument("--skip-deps", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = run_admit(args.root, args.envelope, args.allow_dirty, args.allow_drift, args.skip_deps)
    except Exception as exc:
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "verdict": "GATE_BROKEN",
            "exit_code": 2,
            "reasons": [f"{type(exc).__name__}: {exc}"],
            "checks": [],
            "envelope": {"path": args.envelope},
            "git": {},
            "flags": {"allow_dirty": args.allow_dirty, "allow_drift": args.allow_drift, "skip_deps": args.skip_deps},
            "exceptions_used": {},
            "run_at": utc_now(),
        }
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return int(receipt["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
