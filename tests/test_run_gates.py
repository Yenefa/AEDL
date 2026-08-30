import json
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

from gates.run_gates import (
    REQUIRED_ZIP_ENTRIES,
    _evaluate_delivery,
    _evaluate_intent,
    _evaluate_ops,
    evaluate_evidence,
    run,
)


ROOT = Path(__file__).resolve().parents[1]


class RunGatesTests(unittest.TestCase):
    def test_delivery_gate_rejects_cpl_that_differs_from_fresh_pcb_export(self):
        current = (ROOT / "delivery/pos.csv").read_text(encoding="utf-8-sig")
        with tempfile.TemporaryDirectory() as temp_dir:
            fresh = Path(temp_dir) / "fresh-cpl.csv"
            fresh.write_text(
                current.replace("C1,54.000000", "C1,55.000000", 1),
                encoding="utf-8-sig",
            )
            result = _evaluate_delivery(ROOT, fresh)

        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("fresh" in error.lower() for error in result["errors"]))

    def test_delivery_gate_rejects_stale_self_consistent_bom_and_pos(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "gates/bom").mkdir(parents=True)
            (root / "delivery").mkdir()
            (root / "src/hardware/m2-board").mkdir(parents=True)
            (root / "gates/bom/bom_v1.json").write_text(
                json.dumps({"items": [{"ref": "U1"}]}), encoding="utf-8"
            )
            (root / "delivery/pos.csv").write_text(
                "Ref,PosX,PosY\nU1,0,0\n", encoding="utf-8"
            )
            (root / "delivery/bom.csv").write_text(
                "Designator,Comment\nU1,part\n", encoding="utf-8"
            )
            (root / "src/hardware/m2-board/intent_v1.json").write_text(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "components": {
                            "U1": {"lib_id": "Device:R"},
                            "U2": {"lib_id": "Device:R"},
                            "#FLG01": {"lib_id": "power:PWR_FLAG", "virtual": True},
                        },
                        "nets": {"N": ["U1.1", "U2.1"]},
                    }
                ),
                encoding="utf-8",
            )
            with zipfile.ZipFile(root / "delivery/jlc_gerber_upload.zip", "w") as archive:
                for name in REQUIRED_ZIP_ENTRIES:
                    archive.writestr(name, "data")

            result = _evaluate_delivery(root)

        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("intent" in error.lower() for error in result["errors"]))

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

    def test_m2_intent_encodes_repaired_datasheet_semantics(self):
        intent = json.loads(
            (ROOT / "src" / "hardware" / "m2-board" / "intent_v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {ref for ref, component in intent["components"].items() if not component.get("virtual")},
            {
                "U1", "U2", "U3", "J1", "SW1", "SW2", "D1",
                "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9",
                "C1", "C2", "C3", "C4", "C5",
            },
        )
        self.assertEqual(intent["components"]["R7"]["value"], "22R")
        self.assertEqual(intent["components"]["R8"]["value"], "22R")
        self.assertEqual(intent["components"]["R9"]["value"], "10k")
        self.assertEqual(intent["components"]["C5"]["value"], "1uF")
        self.assertEqual(intent["nets"]["USB_DP_CONN"], ["J1.A6", "J1.B6", "R7.1"])
        self.assertEqual(intent["nets"]["USB_DP"], ["R7.2", "U1.14"])
        self.assertEqual(intent["nets"]["USB_DM_CONN"], ["J1.A7", "J1.B7", "R8.1"])
        self.assertEqual(intent["nets"]["USB_DM"], ["R8.2", "U1.13"])
        self.assertIn("U2.2", intent["nets"]["GND"])
        self.assertIn("C5.2", intent["nets"]["GND"])
        self.assertIn("C5.1", intent["nets"]["EN"])
        self.assertIn("R9.1", intent["nets"]["+3V3"])
        self.assertIn("R9.2", intent["nets"]["BOOT"])
        all_members = {member for members in intent["nets"].values() for member in members}
        self.assertNotIn("U2.3", all_members)
        self.assertNotIn("U2.6", all_members)

    def test_m2_schematic_declares_power_flags_at_their_power_labels(self):
        schematic = (
            ROOT / "src" / "hardware" / "m2-board" / "m2_board.kicad_sch"
        ).read_text(encoding="utf-8")

        self.assertIn('(symbol "power:PWR_FLAG"', schematic)
        self.assertIn('(lib_id "power:PWR_FLAG") (at 15.24 15.24 0)', schematic)
        self.assertIn('(lib_id "power:PWR_FLAG") (at 45.72 15.24 0)', schematic)
        self.assertRegex(schematic, r'\(label "\+5V" \(at 15\.24 15\.24 (?:90|270)\)')
        self.assertRegex(schematic, r'\(label "GND" \(at 45\.72 15\.24 (?:90|270)\)')

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

    def test_m1_ops_proxy_cannot_satisfy_current_m2_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            proxy = root / "notes" / "m1-evidence" / "ops_validate.json"
            proxy.parent.mkdir(parents=True)
            proxy.write_text(
                json.dumps({"protocol_version": 2, "valid": True, "op_count": 99, "errors": []}),
                encoding="utf-8",
            )

            gate = _evaluate_ops(root)

        self.assertEqual(gate["status"], "fail")
        self.assertIn("m2-evidence-reset", gate["details"]["path"])
        self.assertNotIn("m1-evidence", gate["details"]["path"])

    def test_current_m2_ops_evidence_is_bound_to_ops_hash_and_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ops_path = root / "src" / "hardware" / "m2-board" / "ops_gen.json"
            evidence_path = root / "notes" / "m2-evidence-reset" / "generated" / "ops_validate_current.json"
            ops_path.parent.mkdir(parents=True)
            evidence_path.parent.mkdir(parents=True)
            ops = {"protocol_version": 2, "target_format": "kicad", "ops": [{"op": "place_component"}]}
            encoded = (json.dumps(ops) + "\n").encode("utf-8")
            ops_path.write_bytes(encoded)
            evidence_path.write_text(
                json.dumps(
                    {
                        "$schema": "https://aedl.local/schemas/m2-ops-validation.v1.json",
                        "schema_version": 1,
                        "generated_at": "2026-08-30T00:00:00Z",
                        "target": "src/hardware/m2-board/ops_gen.json",
                        "ops_sha256": hashlib.sha256(encoded).hexdigest(),
                        "op_count": 1,
                        "valid": True,
                        "errors": [],
                        "generator": "akcli ops from-intent",
                        "validator": "akcli ops validate",
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(_evaluate_ops(root)["status"], "pass")
            ops["ops"].append({"op": "add_net_label"})
            ops_path.write_text(json.dumps(ops), encoding="utf-8")
            stale = _evaluate_ops(root)

        self.assertEqual(stale["status"], "fail")
        self.assertTrue(any("hash" in error for error in stale["errors"]))

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
        self.assertEqual(
            {gate["name"] for gate in manifest["gates"]},
            {"erc", "drc", "bom", "delivery", "intent", "ops", "schematic_semantics", "learning", "requirements_contract", "board_review"},
        )
        # The 10th gate must also fail closed on an empty sandbox (missing
        # contract file counts as unreadable evidence, never as a skip).
        rc_gate = next(g for g in manifest["gates"] if g["name"] == "requirements_contract")
        self.assertEqual(rc_gate["status"], "fail")
        self.assertTrue(any("unreadable" in error or "missing" in error.lower()
                            for error in rc_gate["errors"]), rc_gate["errors"])

    def test_output_root_alias_writes_a_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "runs"
            manifest = run(ROOT, skip_kicad=True, output_root=output_root)
            self.assertEqual(manifest["status"], "fail")
            self.assertTrue((output_root / "run_manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
