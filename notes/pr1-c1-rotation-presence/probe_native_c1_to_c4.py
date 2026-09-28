"""NP1 native longitudinal probe (READ ONLY on the repo): C1 -> C4 -> real writer.

For the frozen DC-04 fixture it drives the *real* path:

    raw Proposal -> parse_proposal() (new presence-preserving C1)
    -> to_dict() -> HostPatch.proposal / proposal_sha256
    -> serialize the parsed op-list and re-read it from disk
    -> adapter.apply_stage() (C4 PRECHECK) -> pinned akcli strict writer

and reads the label angles the writer actually produced.

Requires: AEDL_PR1_NATIVE=1 and AEDL_AKCLI_PYTHON=<toolchain/py311/Scripts/python.exe>
"""
import json
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from tests import test_akcli_adapter as T
from tools import akcli_adapter as adapter
from tools.repair_pipeline import canonical_sha256, hash_bytes, parse_proposal

LABEL = re.compile(r"\(label\s+\"([^\"]+)\"\s+\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)")


class _Probe(T._NativeToolchainMixin, unittest.TestCase):
    def _host_patch(self, toolchain, document, proposal_sha256, stage):
        body = {"schema_version": 1, "run_id": "RUN-1", "candidate_id": "CAND-1",
                "round_id": "ROUND-1", "patch_id": "PATCH-1",
                "context_id": document["context_id"],
                "proposal": document, "proposal_sha256": proposal_sha256,
                "target": document["target"],
                "base": {"files": {}, "topology_sha256": canonical_sha256("topology", "T")},
                "policy": {"id": "POLICY-1", "file_sha256": canonical_sha256("manifest", "F"),
                           "bound_rule_id": "DC-04",
                           "bound_policy_sha256": canonical_sha256("policy-bound", "B")},
                "authority": {"context_digest": canonical_sha256("context", "C"),
                              "resolved_authorization_refs": ["host:ledger:1"],
                              "decisions": [{"capability": "TOOL_EXECUTE", "effect": "ALLOW"},
                                            {"capability": "FILE_WRITE", "effect": "ALLOW"}]},
                "toolchain_manifest": toolchain,
                "toolchain_sha256": adapter._toolchain_digest(toolchain),
                "route": "STRICT", "bound_policy": {"version": 1}}
        body["patch_sha256"] = canonical_sha256("patch", body)
        return body

    def runTest(self):
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        frozen = self._fixture_ops("DC-04")
        explicit = [dict(row, rotation=0) if row.get("op") == "add_net_label" else row
                    for row in frozen]
        for name, ops in (("absent", frozen), ("explicit0", explicit)):
            stage = self._stage("DC-04", "c1to4-" + name)
            with open(os.path.join(stage, "fault.kicad_sch"), "rb") as handle:
                base_source_sha256 = hash_bytes(handle.read())
            raw = json.dumps({"schema_version": 1, "context_id": "CTX-1",
                              "target": "design/fault.kicad_sch",
                              "base_source_sha256": base_source_sha256,
                              "decision": "PATCH", "diagnosis": [],
                              "oplist": {"protocol_version": 2, "target_format": "kicad",
                                         "ops": ops}}).encode("utf-8")
            parsed = parse_proposal(raw)
            document = parsed.to_dict()
            parsed_op = document["oplist"]["ops"][1]
            with open(os.path.join(stage, "oplist.json"), "w", encoding="utf-8",
                      newline="\n") as handle:
                json.dump(document["oplist"], handle)
            body = self._host_patch(toolchain, document, parsed.proposal_sha256, stage)
            result = adapter.apply_stage(self._stage_request(
                body, stage, os.path.join(self.root, "art-" + name)))
            print("%-10s C1 parsed op has rotation key: %-5s | proposal_sha=%s | status=%s"
                  % (name, "rotation" in parsed_op, parsed.proposal_sha256[:12],
                     result["status"]))
            with open(os.path.join(stage, "fault.kicad_sch"), encoding="utf-8") as handle:
                text = handle.read()
            for label, x, y, angle in LABEL.findall(text):
                if (x, y) in (("34.29", "254"), ("34.29", "261.62")):
                    print("           label %-6s at (%s, %s) angle=%s" % (label, x, y, angle))


if __name__ == "__main__":
    suite = unittest.TestSuite([_Probe()])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
