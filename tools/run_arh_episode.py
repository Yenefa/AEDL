"""Run GH-110's bounded native episode with the real ARH repair port.

Example (key supplied only through AEDL_ARH_API_KEY):
  python -m tools.run_arh_episode --run-root C:/dev/aedl-episodes/run-1 \
    --worker-python <akcli-0.21.0-python> --kicad-cli <kicad-10.0.5-cli> \
    --base-url <provider-url> --model <configured-model>
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


def run_episode(run_root, worker_python, kicad_cli, model, *, real_model, max_repairs=2):
    from langgraph.checkpoint.sqlite import SqliteSaver
    from aedl_sandbox.adapters import build_arh_orchestrator, build_trust_port
    from aedl_sandbox.arh.budget import BudgetConfig, BudgetStop, BudgetExceeded
    from aedl_sandbox.arh.model_adapter import ModelError
    from aedl_sandbox.nativeports import NativeEpisodePorts, INITIAL_SUBJECT, DOMAIN, save

    root = Path(run_root).resolve()
    # Never resume over stale candidates/reports and never overwrite a prior run.
    root.mkdir(parents=True, exist_ok=False)
    ports = NativeEpisodePorts(REPO, root / "observations", worker_python, kicad_cli)
    budget = BudgetStop(BudgetConfig(max_calls=3, max_total_tokens=24000,
                                   max_wall_clock_s=300))
    allowlist = {"allowed_components": [{"mpn": "SHT30-DIS-B", "role": "sensor"}],
                 "evidence_ids": ["SHT3X_DIS_DATASHEET", "SHT30_ADDRESS"]}
    run_id = "gh110-episode"
    error = None
    with SqliteSaver.from_conn_string(str(root / "checkpoint.sqlite")) as saver:
        orchestrator = build_arh_orchestrator(root, run_id, saver, repo_root=REPO,
            model=model, subject=copy.deepcopy(INITIAL_SUBJECT), allowlist=allowlist,
            policy=ports.policy, executor=ports, verifier=ports,
            trust=build_trust_port(REPO, root / "receipts"), max_repairs=max_repairs,
            budget=budget, domain_id=DOMAIN)
        try:
            state = orchestrator.run()
            pending = orchestrator.pending_interrupt()
        except (BudgetExceeded, ModelError) as exc:
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
    args = parser.parse_args(argv)
    if args.max_repairs < 0:
        parser.error("--max-repairs must be nonnegative")
    if args.offline_control:
        proposal = {"diagnosis": "SHT30_ADDRESS: the fresh netlist shows U2.2 floating",
            "design_action": "DESIGN_ASSIGN_PIN", "design_subject": {
                "pin": "U2.2", "function": "GND", "approval_status": "NOT_REQUIRED"},
            "evidence_ids": ["SHT30_ADDRESS"], "locator": {"pin": "U2.2"}}
        model = FakeModelAdapter([ModelResponse(json.dumps(proposal), ModelUsage(), "offline-control")])
    else:
        key = os.environ.get("AEDL_ARH_API_KEY")
        if not key or not args.base_url or not args.model:
            parser.error("real episode requires AEDL_ARH_API_KEY, --base-url and --model")
        model = OpenAICompatibleAdapter(base_url=args.base_url, api_key=key, model=args.model,
                                        transport=urllib_default_transport)
    summary = run_episode(args.run_root, args.worker_python, args.kicad_cli, model,
                          real_model=not args.offline_control, max_repairs=args.max_repairs)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["result"] in ("REPAIR_VERIFIED", "CONTROL_RUN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
