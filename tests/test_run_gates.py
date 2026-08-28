import json
from pathlib import Path
import tempfile
import unittest

from gates.run_gates import evaluate_evidence, run


ROOT = Path(__file__).resolve().parents[1]


class RunGatesTests(unittest.TestCase):
    def test_current_evidence_is_reported_as_blocked_not_green(self):
        manifest = evaluate_evidence(
            ROOT,
            ROOT / "notes/m1-evidence/g2_erc_m2board.json",
            ROOT / "notes/m1-evidence/g4_drc_final.json",
            ROOT / "gates/board_review_v1.json",
        )

        self.assertEqual(manifest["status"], "fail")
        by_name = {gate["name"]: gate for gate in manifest["gates"]}
        self.assertEqual(by_name["erc"]["status"], "fail")
        self.assertEqual(by_name["erc"]["details"]["error_count"], 2)
        self.assertEqual(by_name["drc"]["status"], "pass")
        self.assertEqual(by_name["board_review"]["status"], "fail")
        self.assertEqual(by_name["board_review"]["details"]["review_count"], 8)
        self.assertEqual(
            by_name["board_review"]["details"]["status_counts"],
            {"needs_physical": 8},
        )

    def test_malformed_tool_reports_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            erc = root / "erc.json"
            drc = root / "drc.json"
            review = root / "review.json"
            erc.write_text(json.dumps({"sheets": []}), encoding="utf-8")
            drc.write_text(json.dumps({"violations": [], "unconnected_items": []}), encoding="utf-8")
            review.write_text(json.dumps({}), encoding="utf-8")

            manifest = evaluate_evidence(root, erc, drc, review)

        self.assertEqual(manifest["status"], "fail")
        self.assertTrue(all(gate["status"] == "fail" for gate in manifest["gates"]))
        self.assertTrue(any("invalid schema metadata" in error for error in manifest["gates"][0]["errors"]))

    def test_output_root_alias_writes_a_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "runs"
            manifest = run(ROOT, skip_kicad=True, output_root=output_root)
            self.assertEqual(manifest["status"], "fail")
            self.assertTrue((output_root / "run_manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
