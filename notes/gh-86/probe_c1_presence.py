"""GH-86 vertical probe (READ ONLY): does C1 erase rotation presence before C4 sees it?

This probe never writes repository code.  It answers one question for the C4 fix:
if the host builds the authorized proposal (or the on-disk op-list) from C1
parse_proposal(...).to_dict(), has the rotation *presence* already been lost?

Run: py -3 notes/gh-86/probe_c1_presence.py
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from tools.repair_pipeline import parse_proposal
from tools import akcli_adapter as adapter


def raw_proposal(label, op):
    doc = {
        "schema_version": 1,
        "context_id": "ctx-gh86",
        "target": "design/fault.kicad_sch",
        "base_source_sha256": "a" * 64,
        "decision": "PATCH",
        "diagnosis": [],
        "oplist": {"protocol_version": 2, "target_format": "kicad", "ops": [op]},
    }
    return label, json.dumps(doc).encode("utf-8")


def main():
    absent_op = {"op": "add_net_label", "name": "BOOT0", "at": "U1.44"}
    explicit_op = {"op": "add_net_label", "name": "BOOT0", "at": "U1.44", "rotation": 0}
    rows = []
    for label, raw in (raw_proposal("raw absent", absent_op),
                       raw_proposal("raw explicit 0", explicit_op)):
        parsed = parse_proposal(raw)
        doc = parsed.to_dict()
        op = doc["oplist"]["ops"][0]
        norm = adapter._normalize_operation(op, "c1-parsed")
        rows.append({
            "label": label,
            "raw_has_rotation_key": "rotation" in json.loads(raw)["oplist"]["ops"][0],
            "c1_parsed_op": op,
            "c1_parsed_has_rotation_key": "rotation" in op,
            "c1_proposal_sha256": parsed.proposal_sha256,
            "c4_normalized_rotation_mode": norm.get("rotation_mode"),
        })
    print(json.dumps(rows, indent=2, ensure_ascii=False, sort_keys=True))
    same_hash = rows[0]["c1_proposal_sha256"] == rows[1]["c1_proposal_sha256"]
    print("")
    print("C1 erases presence (both parsed ops carry rotation=0):",
          all(r["c1_parsed_has_rotation_key"] for r in rows))
    print("C1 proposal_sha256 collapses absent and explicit 0:", same_hash)
    print("C4 normalization after C1 parse is EXPLICIT_0 for both:",
          [r["c4_normalized_rotation_mode"] for r in rows])


if __name__ == "__main__":
    main()
