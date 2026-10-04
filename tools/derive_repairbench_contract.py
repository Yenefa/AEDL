# -*- coding: utf-8 -*-
"""Derive the RepairBench netlist-scope contract from the frozen M2 contract.

Mechanical projection, no hand transcription: for each parent rule keep
id/kind/severity/title/source_ids verbatim and keep only checks.netlist. The
result must validate against gates.schematic_semantics.validate_contract, whose
top-level key set is closed and whose sources values must be HTTPS URL strings.
"""
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT / "gates" / "contracts" / "m2_schematic_contract_v1.json"
OUT = ROOT / "benchmarks" / "repairbench_v0_1" / "netlist_contract_v1.json"

parent = json.loads(PARENT.read_text(encoding="utf-8"))

out = {
    "$schema": parent["$schema"],
    "schema_version": parent["schema_version"],
    "board_id": parent["board_id"],
    "sources": dict(parent["sources"]),
    "rules": [],
}

KEEP = ("id", "kind", "severity", "title", "source_ids")
for rule in parent["rules"]:
    netlist = rule.get("checks", {}).get("netlist")
    if not netlist:
        continue
    projected = {k: rule[k] for k in KEEP if k in rule}
    projected["checks"] = {"netlist": netlist}
    out["rules"].append(projected)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

# Fail loudly rather than shipping a contract the frozen evaluator rejects.
import sys
sys.path.insert(0, str(ROOT))
from gates.schematic_semantics import validate_contract

validate_contract(out)
print("derived %d rules; validate_contract PASSED" % len(out["rules"]))
for r in out["rules"]:
    print("   %-26s severity=%-8s views=%s" % (
        r["id"], r["severity"], ",".join(r["checks"].keys())))