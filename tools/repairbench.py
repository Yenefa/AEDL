# -*- coding: utf-8 -*-
"""AEDL RepairBench v0.1 runner.

Measures net-level repair against a frozen, datasheet-derived contract. Three
metric layers, per ADR-023:

  primary_oracle            target rule FAIL -> PASS
  regression_guard          every non-target rule that passed before must still pass
  structural_preservation   post-repair netlist matches the withheld acceptance file

Design rules this file obeys:

* The solving arm is shown ONLY ``fault.kicad_sch``. ``repair_ops.json`` (the
  ground-truth repair) is never copied into the arm workspace. The ``oracle``
  control arm reads it deliberately and is a solvability control, not a
  competing method.
* The oracle is the frozen netlist-scope contract projected from
  ``gates/contracts/m2_schematic_contract_v1.json``. Scoring goes through the
  frozen evaluator ``gates.schematic_semantics.evaluate_observations`` -- not a
  second implementation of contract semantics.
* Nothing here claims a repair is correct unless the contract says so.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_by_path(rel: str, alias: str):
    """Load a repo module by explicit file path.

    Measured reason, not style: ``gates`` has no ``__init__.py``, so it is a
    namespace package whose FileFinder cache is keyed on the directory mtime.
    Under ``python -m tools.repairbench`` importing ``gates.schemantic_semantics``
    failed with a bare ModuleNotFoundError even though the file exists and
    ``importlib.util.find_spec()`` resolved it; the same code imported fine under
    ``python -c``. Calling ``importlib.invalidate_caches()`` both before and
    after initialising the parent package did not fix it. Both target modules
    import only the standard library, so loading them by path removes the whole
    failure class without changing behaviour.
    """
    spec = importlib.util.spec_from_file_location(alias, str(REPO_ROOT / rel))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


_rv = _load_by_path("gates/repair_verification.py", "_aedl_repair_verification")
observe_source = _rv.observe_source

_ss = _load_by_path("gates/schematic_semantics.py", "_aedl_schematic_semantics")
_normalise_net = _ss._normalise_net
evaluate_observations = _ss.evaluate_observations

BENCH_DIR = REPO_ROOT / "benchmarks" / "repairbench_v0_1"
CONTRACT_PATH = BENCH_DIR / "netlist_contract_v1.json"
EPISODES_PATH = BENCH_DIR / "episodes_v1.json"
ACCEPTANCE_PATH = REPO_ROOT / "tests" / "fixtures" / "repair_pr1" / "private" / "acceptance_v1.json"

OBSERVATIONS_SCHEMA = "https://aedl.local/schemas/schematic-observations.v1.json"


# --------------------------------------------------------------------------- utils
def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------- oracle view
def project_netlist_view(raw: bytes) -> Dict[str, Any]:
    """Project a ``.kicad_sch`` into the frozen evaluator's ``netlist`` view.

    Uses ``observe_source`` (the C2 pure s-expression reader) so no KiCad, no
    kicad-cli and no network are needed. A named partition becomes that net; an
    unnamed partition becomes ``net: None``, marked ``no_connect`` only when
    every member pin carries an explicit no-connect flag.
    """
    obs = observe_source(raw)

    no_connect_pins = set()
    for pin in obs["pins"]:
        if pin.get("no_connect"):
            no_connect_pins.add((pin["identity"]["reference"], str(pin["identity"]["number"])))

    pins: Dict[str, Dict[str, Any]] = {}
    for part in obs["partitions"]:
        names = [n for n in part.get("names", []) if n]
        # KiCad sheet paths carry a leading "/" ("/GND") while the frozen contract
        # states bare names ("GND"). The frozen evaluator normalises the same way
        # via gates.schematic_semantics._normalise_net, so call it rather than
        # reimplementing the rule here.
        net = _normalise_net(names[0]) if names else None
        members = part.get("members", [])
        all_nc = bool(members) and all(
            (m["reference"], str(m["number"])) in no_connect_pins for m in members
        )
        for member in members:
            pins["%s.%s" % (member["reference"], member["number"])] = {
                "net": net,
                "no_connect": bool(all_nc),
            }

    for ref, num in no_connect_pins:
        pin_id = "%s.%s" % (ref, num)
        if pin_id in pins:
            pins[pin_id] = {"net": None, "no_connect": True}

    components = {
        c["reference"]: {"value": c.get("value", "")}
        for c in obs["components"]
        if c.get("value")
    }
    return {"pins": pins, "components": components, "coverage": obs.get("coverage", {})}


def observations_from_views(view: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap a single projected view into the evaluator's observations envelope."""
    return {
        "$schema": OBSERVATIONS_SCHEMA,
        "schema_version": 1,
        "views": {
            "intent": {"pins": {}, "components": {}},
            "netlist": {"pins": view["pins"], "components": view["components"]},
            "pcb": {"pins": {}, "components": {}},
            "firmware": {"constants": {}},
        },
    }


def rule_statuses(contract: Dict[str, Any], raw: bytes) -> Tuple[Dict[str, str], Dict[str, Any]]:
    view = project_netlist_view(raw)
    report = evaluate_observations(contract, observations_from_views(view))
    return {f["rule_id"]: f["status"] for f in report.get("findings", [])}, view


# ------------------------------------------------------------ structural oracle
def structural_check(episode_id: str, view: Dict[str, Any]) -> Dict[str, Any]:
    """Compare the post-repair net view against the withheld acceptance file."""
    case = load_json(ACCEPTANCE_PATH)["cases"].get(episode_id)
    if case is None:
        return {"status": "UNKNOWN", "problems": ["no acceptance case for %s" % episode_id]}

    observed_nets: Dict[str, List[str]] = {}
    for pin_id, state in view["pins"].items():
        if state.get("net"):
            observed_nets.setdefault(state["net"], []).append(pin_id)

    problems: List[str] = []
    for expectation in case.get("after", []):
        if "names" in expectation:
            # acceptance_v1.json states KiCad sheet-path names ("/GND"); the
            # projected view is already normalised ("GND"). Normalise the
            # expectation too so both sides are compared in one convention.
            want = _normalise_net(expectation["names"][0])
            got = sorted(observed_nets.get(want, []))
            want_members = sorted(expectation.get("members", []))
            if got != want_members:
                problems.append("net %s: expected %s, observed %s" % (want, want_members, got))
        elif "capture" in expectation:
            want_capture = _normalise_net(expectation["capture"])
            for pin_id in expectation.get("add", []):
                got = (view["pins"].get(pin_id) or {}).get("net")
                if got != want_capture:
                    problems.append("pin %s: expected net %s, observed %r" % (
                        pin_id, want_capture, got))

    for comp in case.get("add_components", []):
        got_value = (view["components"].get(comp["reference"]) or {}).get("value")
        if got_value != comp["value"]:
            problems.append("component %s: expected %r, observed %r" % (
                comp["reference"], comp["value"], got_value))

    return {"status": "pass" if not problems else "fail", "problems": problems}


# ------------------------------------------------------------------ episode eval
def evaluate_candidate(contract, episode, before_raw: bytes, after_raw: bytes) -> Dict[str, Any]:
    before_statuses, _ = rule_statuses(contract, before_raw)
    after_statuses, after_view = rule_statuses(contract, after_raw)
    target = episode["target_rule"]

    before = before_statuses.get(target, "unknown")
    after = after_statuses.get(target, "unknown")
    primary_ok = before == "fail" and after == "pass"

    broken = [rid for rid, was in before_statuses.items()
              if rid != target and was == "pass" and after_statuses.get(rid) != "pass"]
    structural = structural_check(episode["id"], after_view)

    return {
        "episode": episode["id"],
        "target_rule": target,
        "primary_before": before,
        "primary_after": after,
        "primary_ok": primary_ok,
        "regression_broken": broken,
        "regression_ok": not broken,
        "structural": structural,
        "before_sha256": sha256_bytes(before_raw),
        "after_sha256": sha256_bytes(after_raw),
        "bytes_changed": before_raw != after_raw,
        "all_rule_statuses_after": after_statuses,
    }


# ------------------------------------------------------------------------- arms
def find_akcli() -> Optional[Path]:
    candidate = Path.home() / "AppData/Local/hermes/hermes-agent/venv/Scripts/akcli.exe"
    return candidate if candidate.is_file() else None


def arm_noop(episode: Dict[str, Any], workdir: Path) -> bytes:
    """Do nothing. Control: MUST NOT pass."""
    target = workdir / "fault.kicad_sch"
    shutil.copyfile(REPO_ROOT / episode["fixture"], target)
    return target.read_bytes()


def arm_oracle(episode: Dict[str, Any], workdir: Path) -> bytes:
    """Apply the withheld ground-truth repair_ops.json. Control: MUST pass."""
    ep_id = episode["id"]
    target = workdir / "fault.kicad_sch"
    shutil.copyfile(
        REPO_ROOT / ("tests/fixtures/repair_pr1/native/%s/fault.kicad_sch" % ep_id), target)
    ops = REPO_ROOT / ("tests/fixtures/repair_pr1/native/%s/repair_ops.json" % ep_id)

    akcli = find_akcli()
    if akcli is None:
        raise RuntimeError("oracle arm needs the pinned akcli writer; not found")

    proc = subprocess.run(
        [str(akcli), "draw", str(target), "--ops", str(ops), "--apply", "--no-erc", "--json"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("oracle arm writer failed rc=%d: %s" % (
            proc.returncode, (proc.stderr or proc.stdout)[:300]))
    return target.read_bytes()


ARMS = {"noop": arm_noop, "oracle": arm_oracle}


# ------------------------------------------------------------------------- runner
def run_arm(arm: str, outdir: Path) -> Dict[str, Any]:
    contract = load_json(CONTRACT_PATH)
    spec = load_json(EPISODES_PATH)
    arm_fn = ARMS.get(arm)
    if arm_fn is None:
        raise SystemExit("unknown arm %r; available: %s" % (arm, ", ".join(sorted(ARMS))))

    results: List[Dict[str, Any]] = []
    for episode in spec["episodes"]:
        before_raw = (REPO_ROOT / episode["fixture"]).read_bytes()
        with tempfile.TemporaryDirectory(prefix="rb-%s-" % arm) as tmp:
            try:
                after_raw = arm_fn(episode, Path(tmp))
                outcome = evaluate_candidate(contract, episode, before_raw, after_raw)
                outcome["arm"] = arm
                outcome["error"] = None
            except Exception as exc:  # an arm that cannot run is a failure, not a pass
                outcome = {
                    "arm": arm, "episode": episode["id"],
                    "target_rule": episode["target_rule"],
                    "primary_ok": False, "regression_ok": False,
                    "structural": {"status": "UNKNOWN", "problems": [str(exc)]},
                    "error": "%s: %s" % (type(exc).__name__, exc),
                }
        results.append(outcome)

    scored = [r for r in results if not r.get("error")]
    summary = {
        "arm": arm,
        "episodes": len(results),
        "executed": len(scored),
        "primary_pass": sum(1 for r in scored if r.get("primary_ok")),
        "regression_clean": sum(1 for r in scored if r.get("regression_ok")),
        "structural_pass": sum(
            1 for r in scored if (r.get("structural") or {}).get("status") == "pass"),
        "errors": [r["episode"] for r in results if r.get("error")],
    }
    report = {
        "benchmark_id": spec["benchmark_id"],
        "arm": arm,
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "episodes_sha256": sha256_file(EPISODES_PATH),
        "acceptance_sha256": sha256_file(ACCEPTANCE_PATH),
        "summary": summary,
        "results": results,
    }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / ("%s.json" % arm)).write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return report


def render(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "AEDL RepairBench v0.1 - arm=%s" % report["arm"],
        "contract sha256: %s" % report["contract_sha256"][:16],
        "",
        "%-8s %-26s %-8s %-9s %-11s %-8s" % (
            "episode", "target_rule", "primary", "regress", "structural", "changed"),
    ]
    for r in report["results"]:
        lines.append("%-8s %-26s %-8s %-9s %-11s %-8s" % (
            r["episode"], r["target_rule"],
            "PASS" if r.get("primary_ok") else "FAIL",
            "clean" if r.get("regression_ok") else "BROKEN",
            (r.get("structural") or {}).get("status", "-"),
            "yes" if r.get("bytes_changed") else "no"))
        if r.get("error"):
            lines.append("         error: %s" % r["error"])
    lines += ["",
        "primary %d/%d   regression clean %d/%d   structural %d/%d   executed %d/%d" % (
            s["primary_pass"], s["episodes"], s["regression_clean"], s["episodes"],
            s["structural_pass"], s["episodes"], s["executed"], s["episodes"])]
    if s["errors"]:
        lines.append("errors: %s" % ", ".join(s["errors"]))
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.repairbench")
    ap.add_argument("--arm", required=True, choices=sorted(ARMS))
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    outdir = Path(args.out) if args.out else (BENCH_DIR / "runs")
    report = run_arm(args.arm, outdir)
    print(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) if args.json
          else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())