"""CLI for the EDD-001 sandbox runtime (Agent H).

Commands:
  preflight    Runs the REAL EDD-001 policy preflight (Agent M's engine over
               the frozen repository contracts) and prints structured JSON;
               exits with a documented non-zero code while the outcome is
               BLOCKED, which is the honest current state of EDD-001 inputs.
  run-fixture  Drives a TEST_ONLY synthetic complete bundle through the REAL
               policy/trust adapters up to the human interrupt; it never
               auto-approves itself.
  resume       Resumes a paused fixture run with an explicit APPROVED/REJECTED
               decision plus --approved-by naming the human deciding.
  run-arh      Assembles a REAL orchestrator whose repair port is the ARH LLM
               agent and runs it. This is the only command that makes the agent
               reachable from a process. The API key is read from the
               AEDL_ARH_API_KEY environment variable and is NOT an option:
               argv reaches process listings and shell history.

The SQLite checkpoint database lives under the caller-supplied run root,
never in a global user directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from . import adapters
from .orchestrator import APPROVED, REJECTED, SandboxOrchestrator
from .workspace import CandidateWorkspace

FIXTURE_SCENARIOS = ("repair_then_pass",)

#: The API key is read from HERE and nowhere else. Deliberately an environment
#: variable and deliberately not a CLI flag: a flag would put the key in the
#: process argument list (visible to any user running `ps`/`wmic` on the host) and
#: in the shell history, and neither is acceptable for a credential.
ARH_API_KEY_ENV = "AEDL_ARH_API_KEY"


class MissingApiKey(RuntimeError):
    """No API key configured. Named, so the refusal says which variable to set."""


def _require_api_key(env: Any = os.environ) -> str:
    """Return the configured API key or refuse BY NAME.

    Fail-closed and early: this runs before any assembly, so a missing key
    cannot leave a half-built workspace or a trajectory file behind suggesting a
    round was attempted. Blank is treated as missing, because an empty string
    would otherwise reach the Authorization header and produce a confusing 401
    from the provider instead of a clear local error.
    """
    raw = env.get(ARH_API_KEY_ENV, "")
    if not str(raw).strip():
        raise MissingApiKey(
            "%s is not set (or is blank). The ARH agent needs a model endpoint "
            "to propose against. Set it in the environment for this shell "
            "rather than passing it on the command line." % ARH_API_KEY_ENV
        )
    return str(raw).strip()


def _fixture_run_id(scenario: str) -> str:
    return f"fixture-{scenario}"


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _preflight(repo_root: Path, domain: str) -> int:
    decision = adapters.real_edd001_preflight(
        repo_root, run_id="preflight-cli"
    )
    _print(
        {
            "outcome": decision.outcome.value,
            "reason_code": decision.reason_code,
            "domain": domain,
            "repo_root": str(repo_root),
            "findings": [
                {
                    "code": finding.code,
                    "message": finding.message,
                    "source": finding.source,
                    "details": dict(finding.details),
                }
                for finding in decision.findings
            ],
            "note": (
                "Real EDD-001 preflight over the frozen contracts (Agent M "
                "engine). BLOCKED is the honest outcome while POWER contract, "
                "local datasheets, compiler registry and verifier coverage "
                "are incomplete; no synthetic data is used to manufacture a PASS."
            ),
        }
    )
    return 0 if decision.outcome.value == "ALLOW" else 1


def _run_fixture(run_root: Path, scenario: str) -> int:
    run_root.mkdir(parents=True, exist_ok=True)
    run_dir = run_root / "run" / _fixture_run_id(scenario)
    run_dir.mkdir(parents=True, exist_ok=True)
    db_path = run_dir / "checkpoint.sqlite"
    with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        orchestrator = adapters.build_test_only_fixture_orchestrator(
            run_root, _fixture_run_id(scenario), checkpointer
        )
        state = orchestrator.run()
        pending = orchestrator.pending_interrupt()
    if pending is not None:
        _print({"status": "HUMAN_REVIEW_PENDING", "interrupt": pending, "state": state})
        return 0
    _print({"status": "TERMINAL", "state": state})
    return 0


def _resume_fixture(
    run_root: Path, scenario: str, decision: str, approved_by: str
) -> int:
    db_path = run_root / "run" / _fixture_run_id(scenario) / "checkpoint.sqlite"
    if not db_path.exists():
        _print({"status": "ERROR", "reason": f"no checkpoint found under {run_root}"})
        return 2
    with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        orchestrator = adapters.build_test_only_fixture_orchestrator(
            run_root, _fixture_run_id(scenario), checkpointer
        )
        if orchestrator.pending_interrupt() is None:
            _print({"status": "ERROR", "reason": "no pending human interrupt for this run"})
            return 2
        state = orchestrator.resume(decision, approved_by=approved_by)
    _print({"status": "TERMINAL", "state": state})
    return 0


class _UnresolvedPort(RuntimeError):
    """A port this command cannot honestly supply yet.

    Raised on USE, not on construction, so the wiring itself is exercisable and
    testable while the missing piece stays impossible to miss at run time.
    """


class _UnresolvedExecutor:
    """No real ExecutorPort exists in this repository yet.

    `_TestOnlyExecutor` exists and would make this command run to completion.
    It is deliberately NOT used: it would write and "verify" against synthetic
    doubles and report a round that never happened. Failing here is the honest
    state, and it is a SEPARATE piece of work from the repair wiring.
    """

    def execute(self, request):
        raise _UnresolvedPort(
            "no real ExecutorPort is implemented yet; only the TEST_ONLY double "
            "exists, and wiring that in would report a repair round that never "
            "ran. The ARH repair port is wired -- see build_arh_orchestrator -- "
            "but nothing can execute or verify a candidate for real yet."
        )


class _UnresolvedVerifier:
    """No real VerifierPort exists. Same reasoning as _UnresolvedExecutor."""

    def verify(self, run_id, candidate_id, candidate_root):
        raise _UnresolvedPort(
            "no real VerifierPort is implemented yet; only the TEST_ONLY double "
            "exists. See _UnresolvedExecutor."
        )


_UNRESOLVED_EXECUTOR = _UnresolvedExecutor()
_UNRESOLVED_VERIFIER = _UnresolvedVerifier()


def _run_arh(
    repo_root: Path,
    run_root: Path,
    run_id: str,
    base_url: str,
    model: str,
    allowlist_path: Path,
    subject_path: Path,
) -> int:
    """Assemble and run a real orchestrator with the ARH repair port.

    Stops at the API boundary by construction: the key is required and named,
    the transport is the one real I/O path in the codebase, and the operator's
    allowlist and subject are read from files the operator points at -- the model
    participates in none of that.
    """
    from .arh.model_adapter import OpenAICompatibleAdapter, urllib_default_transport

    # Before anything is built or written.
    api_key = _require_api_key()

    allowlist = json.loads(allowlist_path.read_text(encoding="utf-8"))
    subject = json.loads(subject_path.read_text(encoding="utf-8"))

    run_root.mkdir(parents=True, exist_ok=True)
    run_dir = run_root / "run" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    model_adapter = OpenAICompatibleAdapter(
        base_url=base_url,
        api_key=api_key,
        model=model,
        # The ONLY place real I/O is reachable: the adapter has no default
        # transport, so passing it here is a deliberate act, and the tests
        # inject a fake instead of ever reaching this line.
        transport=urllib_default_transport,
    )

    db_path = run_dir / "checkpoint.sqlite"
    with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
        orchestrator = adapters.build_arh_orchestrator(
            run_root,
            run_id,
            checkpointer,
            repo_root=repo_root,
            model=model_adapter,
            subject=subject,
            allowlist=allowlist,
            executor=_UNRESOLVED_EXECUTOR,
            verifier=_UNRESOLVED_VERIFIER,
        )
        state = orchestrator.run()
        pending = orchestrator.pending_interrupt()
    if pending is not None:
        _print({"status": "HUMAN_REVIEW_PENDING", "interrupt": pending, "state": state})
        return 0
    _print({"status": "TERMINAL", "state": state})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m aedl_sandbox.cli",
        description="AEDL EDD-001 sandbox runtime CLI (runtime skeleton)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    preflight_parser = sub.add_parser(
        "preflight",
        help="real EDD-001 preflight over the frozen contracts (Agent M engine)",
    )
    preflight_parser.add_argument("--repo-root", type=Path, required=True)
    preflight_parser.add_argument("--domain", required=True)

    fixture_parser = sub.add_parser(
        "run-fixture",
        help="run the TEST_ONLY fixture through the real adapters up to the human interrupt",
    )
    fixture_parser.add_argument("--scenario", required=True, choices=list(FIXTURE_SCENARIOS))
    fixture_parser.add_argument("--run-root", type=Path, required=True)

    resume_parser = sub.add_parser(
        "resume", help="resume a paused fixture run with an explicit decision"
    )
    resume_parser.add_argument("--run-root", type=Path, required=True)
    resume_parser.add_argument("--scenario", required=True, choices=list(FIXTURE_SCENARIOS))
    resume_parser.add_argument("--decision", required=True, choices=[APPROVED, REJECTED])
    resume_parser.add_argument(
        "--approved-by",
        required=True,
        help="identity of the human making the decision; recorded in the approval receipt",
    )

    arh_parser = sub.add_parser(
        "run-arh",
        help="assemble a real orchestrator with the ARH LLM repair port and run it",
    )
    arh_parser.add_argument("--repo-root", type=Path, required=True)
    arh_parser.add_argument("--run-root", type=Path, required=True)
    arh_parser.add_argument("--run-id", required=True)
    arh_parser.add_argument("--base-url", required=True)
    arh_parser.add_argument("--model", required=True)
    arh_parser.add_argument(
        "--allowlist",
        dest="allowlist_path",
        type=Path,
        required=True,
        help="JSON file the OPERATOR writes: the components and evidence ids this "
        "run may use. The model cannot widen it.",
    )
    arh_parser.add_argument(
        "--subject",
        dest="subject_path",
        type=Path,
        required=True,
        help="JSON file the OPERATOR writes: the frozen design subject for the round.",
    )
    arh_parser.add_argument(
        "--max-repairs", type=int, default=3,
        help="repair rounds the orchestrator may run (graph-level bound; the ARH "
        "budget is a separate, independent bound)",
    )

    args = parser.parse_args(argv)
    if args.command == "preflight":
        return _preflight(args.repo_root, args.domain)
    if args.command == "run-fixture":
        return _run_fixture(args.run_root, args.scenario)
    if args.command == "run-arh":
        try:
            return _run_arh(
                args.repo_root, args.run_root, args.run_id, args.base_url,
                args.model, args.allowlist_path, args.subject_path,
            )
        except MissingApiKey as exc:
            _print({"status": "REFUSED", "reason": str(exc), "env_var": ARH_API_KEY_ENV})
            return 2
    return _resume_fixture(args.run_root, args.scenario, args.decision, args.approved_by)


if __name__ == "__main__":
    raise SystemExit(main())
