"""Run a bounded native episode with the real ARH repair port.

Example (key supplied only through AEDL_ARH_API_KEY):
  python -m tools.run_arh_episode --run-root C:/dev/aedl-episodes/run-1 \
    --worker-python <akcli-0.21.0-python> --kicad-cli <kicad-10.0.5-cli> \
    --base-url <provider-url> --model <configured-model>

GH-117: add --adaptive --specialist for model-selected read-only sources and
one on-demand advisory role. Lead and specialist share --max-calls; the
verifier and native single writer retain all decision and execution authority.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "sandbox_runtime/src"))


def run_episode(run_root, worker_python, kicad_cli, model, *, real_model, max_repairs=2,
                adaptive=False, specialist_models=None, max_calls=8):
    from langgraph.checkpoint.sqlite import SqliteSaver
    from aedl_sandbox.adapters import build_arh_orchestrator, build_trust_port
    from aedl_sandbox.arh.budget import BudgetConfig, BudgetStop, BudgetExceeded
    from aedl_sandbox.arh.model_adapter import ModelError
    from aedl_sandbox.arh.schema import ProposalError
    from aedl_sandbox.nativeports import NativeEpisodePorts, INITIAL_SUBJECT, DOMAIN, save

    root = Path(run_root).resolve()
    if isinstance(max_repairs, bool) or not isinstance(max_repairs, int) or max_repairs < 0:
        raise ValueError("max_repairs must be a nonnegative integer")
    if isinstance(max_calls, bool) or not isinstance(max_calls, int) or max_calls < 1:
        raise ValueError("max_calls must be a positive integer")
    if not callable(getattr(model, "complete", None)):
        raise TypeError("lead model must implement complete")
    if specialist_models and not adaptive:
        raise ValueError("specialists require adaptive investigation")
    if len(specialist_models or {}) > 2:
        raise ValueError("runtime agent roster exceeds three")
    if any(not callable(getattr(m, "complete", None)) for m in (specialist_models or {}).values()):
        raise TypeError("specialist models must implement complete")
    # Never resume over stale candidates/reports and never overwrite a prior run.
    root.mkdir(parents=True, exist_ok=False)
    ports = NativeEpisodePorts(REPO, root / "observations", worker_python, kicad_cli,
                               neutral_findings=adaptive)
    budget = BudgetStop(BudgetConfig(max_calls=max_calls, max_total_tokens=24000,
                                   max_wall_clock_s=300))
    allowlist = {"allowed_components": [{"mpn": "SHT30-DIS-B", "role": "sensor"}],
                 "evidence_ids": ["SHT3X_DIS_DATASHEET", "SHT30_ADDRESS"]}
    run_id = "gh117-episode" if adaptive else "gh110-episode"
    error = None
    with SqliteSaver.from_conn_string(str(root / "checkpoint.sqlite")) as saver:
        orchestrator = build_arh_orchestrator(root, run_id, saver, repo_root=REPO,
            model=model, subject=copy.deepcopy(INITIAL_SUBJECT), allowlist=allowlist,
            policy=ports.policy, executor=ports, verifier=ports,
            trust=build_trust_port(REPO, root / "receipts"), max_repairs=max_repairs,
            budget=budget, domain_id=DOMAIN,
            investigation_resources=ports.investigation_resources() if adaptive else None,
            specialist_models=specialist_models)
        try:
            state = orchestrator.run()
            pending = orchestrator.pending_interrupt()
        except (BudgetExceeded, ModelError, ProposalError) as exc:
            # Provider error text can contain request data. Persist the type/code,
            # not arbitrary provider bodies or authentication headers.
            state, pending = {}, None
            error = getattr(exc, "code", type(exc).__name__)
    observations = ports.observations
    success = bool(budget.snapshot()["calls"] > 0 and len(observations) >= 2
                   and observations[0]["status"] == "FAIL"
                   and observations[-1]["status"] == "PASS"
                   and pending is not None)
    summary = {"task": "GH-110", "domain": DOMAIN, "real_model": real_model,
        "result": ("REPAIR_VERIFIED" if real_model else "CONTROL_RUN") if success else "FAILED",
        "terminal_reason": error or state.get("terminal_reason"), "phase": state.get("phase"),
        "repair_count": state.get("repair_count"), "model_budget": budget.snapshot(),
        "observations": observations, "transactions": [{"status": t["status"], "phase": t["phase"]}
                                                      for t in ports.transactions],
        "candidate_root": state.get("candidate_root"),
        "human_review": "PENDING_HUMAN_REVIEW", "manufacturing_release": False,
        "limits": ["one model, one existing DC-02 native fixture, one independent netlist rule",
                   "ERC/DRC, PCB/firmware contract coverage and physical operation NOT_RUN",
                   "EDD-001 inputs and native tool registrations remain incomplete",
                   "trajectory and development receipts are not formal gate Evidence"]}
    if adaptive:
        trajectory_path = root / "run" / run_id / "trajectory" / (run_id + ".jsonl")
        rows = [json.loads(line) for line in trajectory_path.read_text(encoding="utf-8").splitlines()]
        summary.update(task="GH-117", mode="adaptive",
            agent_roster=["lead", *list(specialist_models or {})], max_agents=3,
            inspections=[r["payload"] for r in rows if r["event"] == "inspection"],
            specialist_events=[r["payload"] for r in rows if r["event"].startswith("second_opinion")
                               or r["event"] == "specialist_advice"],
            role_calls={role: sum(r["event"] == "model_call" and r["payload"].get("role") == role
                                 for r in rows)
                        for role in sorted({r["payload"].get("role", "proposal")
                                            for r in rows if r["event"] == "model_call"})})
    save(root / "summary.json", summary)
    return summary


def main(argv=None):
    from aedl_sandbox.arh.model_adapter import (OpenAICompatibleAdapter, urllib_default_transport,
        FakeModelAdapter, ModelResponse, ModelUsage)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--worker-python", type=Path, required=True)
    parser.add_argument("--kicad-cli", type=Path, required=True)
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--max-repairs", type=int, default=2)
    parser.add_argument("--offline-control", action="store_true",
                        help="explicit scripted model; never counts as a real episode")
    parser.add_argument("--adaptive", action="store_true", help="bounded model-selected read-only inspection")
    parser.add_argument("--specialist", action="store_true", help="enable one on-demand address specialist")
    parser.add_argument("--max-calls", type=int, default=8, help="shared lead and specialist call ceiling")
    args = parser.parse_args(argv)
    if args.max_repairs < 0:
        parser.error("--max-repairs must be nonnegative")
    if args.max_calls < 1 or (args.specialist and not args.adaptive):
        parser.error("positive --max-calls required; --specialist requires --adaptive")
    if args.specialist and args.offline_control:
        parser.error("specialist control is exercised by the deterministic integration tests")
    if args.offline_control:
        proposal = {"diagnosis": "SHT30_ADDRESS: the fresh netlist shows U2.2 floating",
            "design_action": "DESIGN_ASSIGN_PIN", "design_subject": {
                "pin": "U2.2", "function": "GND", "approval_status": "NOT_REQUIRED"},
            "evidence_ids": ["SHT30_ADDRESS"], "locator": {"pin": "U2.2"}}
        responses = [ModelResponse(json.dumps(proposal), ModelUsage(), "offline-control")]
        if args.adaptive:
            responses.insert(0, ModelResponse(json.dumps({"type": "inspect", "resource_ids":
                ["current_netlist", "address_contract"]}), ModelUsage(), "offline-control"))
        model = FakeModelAdapter(responses)
    else:
        key = os.environ.get("AEDL_ARH_API_KEY")
        if not key or not args.base_url or not args.model:
            parser.error("real episode requires AEDL_ARH_API_KEY, --base-url and --model")
        model = OpenAICompatibleAdapter(base_url=args.base_url, api_key=key, model=args.model,
                                        transport=urllib_default_transport)
    summary = run_episode(args.run_root, args.worker_python, args.kicad_cli, model,
                          real_model=not args.offline_control, max_repairs=args.max_repairs,
                          adaptive=args.adaptive,
                          specialist_models={"address-specialist": model} if args.specialist else None,
                          max_calls=args.max_calls)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["result"] in ("REPAIR_VERIFIED", "CONTROL_RUN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
