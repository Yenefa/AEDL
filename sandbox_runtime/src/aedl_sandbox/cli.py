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

The SQLite checkpoint database lives under the caller-supplied run root,
never in a global user directory.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

from . import adapters
from .orchestrator import APPROVED, REJECTED, SandboxOrchestrator
from .workspace import CandidateWorkspace

FIXTURE_SCENARIOS = ("repair_then_pass",)


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

    args = parser.parse_args(argv)
    if args.command == "preflight":
        return _preflight(args.repo_root, args.domain)
    if args.command == "run-fixture":
        return _run_fixture(args.run_root, args.scenario)
    return _resume_fixture(args.run_root, args.scenario, args.decision, args.approved_by)


if __name__ == "__main__":
    raise SystemExit(main())
