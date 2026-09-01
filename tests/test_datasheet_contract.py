import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gates.datasheet_contract import MANIFEST_SCHEMA, validate_datasheet_bundle


def build_bundle(root: Path) -> dict:
    doc = root / "evidence" / "D1_datasheet.pdf"
    doc.parent.mkdir(parents=True)
    doc.write_bytes(b"%PDF-1.4 fake datasheet")
    manifest = {
        "$schema": MANIFEST_SCHEMA,
        "schema_version": 1,
        "board": "unit-test-board",
        "policy": "critical_components_fail_closed",
        "components": [
            {
                "refdes": "D1",
                "manufacturer": "Hubei KENTO Elec",
                "mpn": "KT-0603R",
                "lcsc": "C2286",
                "status": "REQUIRED",
                "documents": [
                    {
                        "type": "datasheet",
                        "source_url": "https://example.com/kt-0603r.pdf",
                        "local_file": "evidence/D1_datasheet.pdf",
                        "sha256": hashlib.sha256(doc.read_bytes()).hexdigest(),
                    }
                ],
                "required_checks": ["polarity"],
                "check_evidence": {
                    "polarity": {
                        "status": "verified",
                        "decision": "pass",
                        "signed_by": "human",
                        "signed_at": "2026-08-31T00:00:00Z",
                        "source": {"document": "D1_datasheet.pdf", "page": 2},
                        "observed": {"parameter": "cathode marking", "value": "pad1 side"},
                        "note": "unit test fixture",
                    }
                },
            }
        ],
    }
    contracts = {
        "schema_version": "1.0",
        "board": "unit-test-board",
        "contracts": [
            {
                "id": "D1-POLARITY",
                "severity": "BLOCK",
                "refdes": "D1",
                "assertions": [
                    {"pin": "1", "semantic": "K", "net": "GND"},
                    {"pin": "2", "semantic": "A", "net": "LED_A"},
                ],
            }
        ],
    }
    bom = {
        "_meta": {"frozen_at": "2026-08-30T00:00:00Z"},
        "items": [
            {
                "ref": "D1",
                "value": "KT-0603R",
                "lcsc": "C2286",
                "mpn": "KT-0603R",
                "manufacturer": "Hubei KENTO Elec",
                "footprint": "LED_SMD:LED_0603_1608Metric",
                "stock": 1,
            }
        ],
    }
    intent = {
        "protocol_version": 1,
        "components": {"D1": {"lib_id": "Device:LED", "value": "KT-0603R"}},
        "nets": {"GND": ["D1.1"], "LED_A": ["R4.2", "D1.2"]},
    }
    paths = {
        "manifest": root / "datasheet_manifest.json",
        "contracts": root / "contracts.json",
        "bom": root / "bom.json",
        "intent": root / "intent.json",
    }
    for name, data in (
        ("manifest", manifest),
        ("contracts", contracts),
        ("bom", bom),
        ("intent", intent),
    ):
        paths[name].write_text(json.dumps(data), encoding="utf-8")
    return paths


def validate(root: Path, paths: dict):
    return validate_datasheet_bundle(
        paths["manifest"], paths["contracts"], paths["bom"], paths["intent"], root
    )


class DatasheetContractTests(unittest.TestCase):
    def test_fully_verified_bundle_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            self.assertEqual(validate(root, paths), [])

    def test_missing_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            paths["manifest"].unlink()
            errors = validate(root, paths)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing datasheet manifest", errors[0])

    def test_mpn_mismatch_with_bom_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            manifest["components"][0]["mpn"] = "WRONG-MPN"
            paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(any("differs from BOM" in error for error in errors), errors)

    def test_frozen_document_sha256_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            (root / "evidence" / "D1_datasheet.pdf").write_bytes(b"tampered")
            errors = validate(root, paths)
        self.assertTrue(any("sha256 mismatch" in error for error in errors), errors)

    def test_url_only_document_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            manifest["components"][0]["documents"][0].pop("local_file")
            paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(any("no local datasheet/drawing copy" in error for error in errors), errors)

    def test_pin_assertion_violation_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            intent = json.loads(paths["intent"].read_text(encoding="utf-8"))
            intent["nets"] = {"GND": ["D1.2"], "LED_A": ["R4.2", "D1.1"]}
            paths["intent"].write_text(json.dumps(intent), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(any("must be on net" in error for error in errors), errors)

    def test_unconnected_pin_assertion_fails_when_connected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            contracts = json.loads(paths["contracts"].read_text(encoding="utf-8"))
            contracts["contracts"][0]["assertions"].append(
                {"pin": "3", "semantic": "NC", "net": None}
            )
            paths["contracts"].write_text(json.dumps(contracts), encoding="utf-8")
            intent = json.loads(paths["intent"].read_text(encoding="utf-8"))
            intent["nets"]["GND"].append("D1.3")
            paths["intent"].write_text(json.dumps(intent), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(any("must be unconnected" in error for error in errors), errors)

    def test_block_until_reviewed_contract_requires_review_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            contracts = json.loads(paths["contracts"].read_text(encoding="utf-8"))
            contracts["contracts"].append(
                {
                    "id": "U3-POWER-MARGIN",
                    "severity": "BLOCK_UNTIL_REVIEWED",
                    "refdes": "D1",
                    "facts": {"vin_v": 5.0},
                }
            )
            paths["contracts"].write_text(json.dumps(contracts), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(any("BLOCK_UNTIL_REVIEWED" in error for error in errors), errors)

    def test_required_check_without_record_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            manifest["components"][0]["required_checks"].append("reverse_voltage")
            paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(
            any("'reverse_voltage'" in error and "no check_evidence record" in error
                for error in errors),
            errors,
        )

    def test_verified_without_human_signature_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            record = manifest["components"][0]["check_evidence"]["polarity"]
            record["signed_by"] = "agent"
            paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(
            any("agent self-signing is forbidden" in error for error in errors), errors
        )

    def test_legacy_verified_record_without_signature_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            manifest["components"][0]["check_evidence"]["polarity"] = {
                "status": "verified",
                "evidence": "legacy shape without signature",
            }
            paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(
            any("agent self-signing is forbidden" in error for error in errors), errors
        )

    def test_human_confirmed_design_block_reports_design_block(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            manifest["components"][0]["check_evidence"]["polarity"] = {
                "status": "verified",
                "decision": "blocked",
                "signed_by": "human",
                "signed_at": "2026-08-31T00:00:00Z",
                "note": "fact verified but design deliberately blocked",
            }
            paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(any("DESIGN-BLOCK" in error for error in errors), errors)
        self.assertFalse(any("DESIGN-FAIL" in error for error in errors), errors)

    def test_machine_prechecked_is_not_a_signature(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            paths = build_bundle(root)
            manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
            manifest["components"][0]["check_evidence"]["polarity"] = {
                "status": "machine_prechecked",
                "candidate_decision": "pass",
                "observed": {"parameter": "x", "value": 1},
            }
            paths["manifest"].write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root, paths)
        self.assertTrue(any("unsigned (status=machine_prechecked)" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
