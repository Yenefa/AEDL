import json
from pathlib import Path
import tempfile
import unittest

from gates.run_gates import _evaluate_intent, evaluate_evidence, run


ROOT = Path(__file__).resolve().parents[1]


class RunGatesTests(unittest.TestCase):
    def test_m2_intent_declares_two_virtual_power_flags(self):
        intent = json.loads(
            (ROOT / "src" / "hardware" / "m2-board" / "intent_v1.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            {
                ref
                for ref, component in intent["components"].items()
                if component.get("virtual")
                and component.get("lib_id") == "power:PWR_FLAG"
                and component.get("value") == "PWR_FLAG"
            },
            {"#FLG01", "#FLG02"},
        )
        self.assertIn("#FLG01.1", intent["nets"]["+5V"])
        self.assertIn("#FLG02.1", intent["nets"]["GND"])

    def test_m2_schematic_declares_power_flags_at_their_power_labels(self):
        schematic = (
            ROOT / "src" / "hardware" / "m2-board" / "m2_board.kicad_sch"
        ).read_text(encoding="utf-8")

        self.assertIn('(symbol "power:PWR_FLAG"', schematic)
        self.assertIn('(lib_id "power:PWR_FLAG") (at 15.24 15.24 0)', schematic)
        self.assertIn('(lib_id "power:PWR_FLAG") (at 45.72 15.24 0)', schematic)
        self.assertIn('(label "+5V" (at 15.24 15.24 90)', schematic)
        self.assertIn('(label "GND" (at 45.72 15.24 90)', schematic)

    def test_intent_accepts_virtual_power_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            intent_path = root / "src" / "hardware" / "m2-board" / "intent_v1.json"
            intent_path.parent.mkdir(parents=True)
            intent_path.write_text(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "components": {
                            "U3": {"lib_id": "Regulator_Linear:ME6211C33M5"},
                            "U1": {"lib_id": "RF_Module:ESP32-C3-WROOM-02"},
                            "#FLG01": {
                                "lib_id": "power:PWR_FLAG",
                                "value": "PWR_FLAG",
                                "virtual": True,
                            },
                            "#FLG02": {
                                "lib_id": "power:PWR_FLAG",
                                "value": "PWR_FLAG",
                                "virtual": True,
                            },
                        },
                        "nets": {
                            "+5V": ["U3.1", "#FLG01.1"],
                            "GND": ["U1.9", "#FLG02.1"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = _evaluate_intent(root)

        self.assertEqual(result["status"], "pass", result["errors"])

    def test_historical_evidence_is_reported_as_blocked_not_green(self):
        manifest = evaluate_evidence(
            ROOT,
            ROOT / "notes/m1-evidence/g2_erc_m2board.json",
            ROOT / "notes/m1-evidence/g4_drc_final.json",
            ROOT / "tests/fixtures/board_review_before_release.json",
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
