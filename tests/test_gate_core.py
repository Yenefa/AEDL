import csv
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from gates.gate_core import (
    count_drc_findings,
    count_erc_errors,
    read_bom_refs,
    read_pos_refs,
    sha256_file,
    validate_board_review,
    validate_bom,
    validate_bom_freshness,
    validate_bom_stock_evidence,
    validate_delivery_manifest,
    validate_delivery_bom,
    validate_jlc_cpl,
    zip_entry_names,
)
from gates.export_delivery import EXPECTED_GERBER_FILES
from gates.make_bom_csv import generate_bom_csv


ROOT = Path(__file__).resolve().parents[1]


class GateCoreTests(unittest.TestCase):
    def test_pre_reset_erc_evidence_is_not_green(self):
        report = ROOT / "tests/fixtures/g2_erc_before_reset.json"
        self.assertEqual(count_erc_errors(report), 2)

    def test_historical_m1_erc_evidence_is_not_green(self):
        report = ROOT / "notes/m1-evidence/g2_erc_m2board.json"
        self.assertEqual(count_erc_errors(report), 2)

    def test_historical_m1_drc_evidence_is_green(self):
        report = ROOT / "notes/m1-evidence/g4_drc_final.json"
        self.assertEqual(count_drc_findings(report), (0, 0))

    def test_canonical_bom_is_complete(self):
        self.assertEqual(validate_bom(ROOT / "gates/bom/bom_v1.json"), [])

    def test_bom_freshness_gate_expires_after_seven_days(self):
        path = ROOT / "gates/bom/bom_v1.json"
        snapshot = json.loads(path.read_text(encoding="utf-8"))["_meta"]["frozen_at"]
        frozen = datetime.fromisoformat(snapshot.replace("Z", "+00:00"))
        self.assertEqual(
            validate_bom_freshness(path, now=frozen, max_age_days=7), []
        )
        errors = validate_bom_freshness(
            path,
            now=frozen + timedelta(days=8),
            max_age_days=7,
        )
        self.assertTrue(any("stale" in error for error in errors))

    def test_bom_stock_evidence_is_bound_to_the_canonical_bom(self):
        bom = ROOT / "gates/bom/bom_v1.json"
        evidence = ROOT / "notes/m2-evidence-reset/generated/bom_stock_current.json"
        self.assertEqual(validate_bom_stock_evidence(bom, evidence), [])

        tampered = json.loads(evidence.read_text(encoding="utf-8"))
        tampered["bom_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "stock.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            errors = validate_bom_stock_evidence(bom, path)
        self.assertTrue(any("hash" in error for error in errors))

    def test_current_jlc_cpl_has_strict_header_and_finite_mm_coordinates(self):
        self.assertEqual(validate_jlc_cpl(ROOT / "delivery/pos.csv"), [])

    def test_delivery_bom_is_field_for_field_equal_to_canonical_bom(self):
        canonical = ROOT / "gates/bom/bom_v1.json"
        delivery = ROOT / "delivery/bom.csv"
        self.assertEqual(validate_delivery_bom(canonical, delivery), [])

        tampered = delivery.read_text(encoding="utf-8-sig").replace("C2934560", "C0", 1)
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bom.csv"
            path.write_text(tampered, encoding="utf-8-sig")
            errors = validate_delivery_bom(canonical, path)
        self.assertTrue(any("LCSC" in error for error in errors))

    def test_delivery_manifest_hash_binds_current_sources_and_outputs(self):
        manifest = ROOT / "delivery/manifest_v1.json"
        self.assertEqual(
            validate_delivery_manifest(ROOT, manifest, EXPECTED_GERBER_FILES),
            [],
        )

        tampered = json.loads(manifest.read_text(encoding="utf-8"))
        tampered["sources"]["board"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            errors = validate_delivery_manifest(ROOT, path, EXPECTED_GERBER_FILES)
        self.assertTrue(any("board" in error and "hash" in error for error in errors))

    def test_bom_rejects_tbd_fixture(self):
        source = json.loads((ROOT / "gates/bom/bom_v1.json").read_text(encoding="utf-8"))
        source["items"][0]["lcsc"] = "TBD"
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture = Path(temp_dir) / "bom.json"
            fixture.write_text(json.dumps(source), encoding="utf-8")
            errors = validate_bom(fixture)
        self.assertTrue(any("TBD" in error for error in errors))

    def test_current_delivery_refs_match_all_21_physical_parts(self):
        bom_refs = read_bom_refs(ROOT / "gates/bom/bom_v1.json")
        pos_refs = read_pos_refs(ROOT / "delivery/pos.csv")
        intent = json.loads(
            (ROOT / "src/hardware/m2-board/intent_v1.json").read_text(encoding="utf-8")
        )
        intent_refs = {
            ref for ref, component in intent["components"].items()
            if not component.get("virtual", False)
        }
        self.assertEqual(bom_refs, pos_refs)
        self.assertEqual(bom_refs, intent_refs)
        self.assertEqual(len(bom_refs), 21)

    def test_zip_entries_and_sha256_are_deterministic(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            payload = root / "payload.bin"
            payload.write_bytes(b"abc")
            archive = root / "package.zip"
            with zipfile.ZipFile(str(archive), "w") as output:
                output.writestr("nested/board.gbr", b"gbr")
                output.writestr("board.drl", b"drl")

            self.assertEqual(
                zip_entry_names(archive),
                ["board.drl", "nested/board.gbr"],
            )
            self.assertEqual(sha256_file(payload), hashlib.sha256(b"abc").hexdigest())

    def test_board_review_requires_all_items_and_release_authorization(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_path = Path(temp_dir) / "review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "_meta": {
                            "reviewer": None,
                            "reviewed_at": None,
                            "manufacturing_release": False,
                        },
                        "reviews": [],
                    }
                ),
                encoding="utf-8",
            )

            errors = validate_board_review(review_path)
            self.assertTrue(any("missing review id USB_EDGE" in error for error in errors))
            self.assertTrue(any("manufacturing_release is false" in error for error in errors))

    def test_complete_released_board_review_is_valid(self):
        required_ids = (
            "USB_EDGE",
            "ESP_ANTENNA",
            "GROUND_RETURN",
            "DECOUPLING",
            "USB_ROUTING",
            "SHT30_THERMAL",
            "PROTECTION",
            "ASSEMBLY",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            review_path = Path(temp_dir) / "review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "_meta": {
                            "reviewer": "board-reviewer",
                            "reviewed_at": "2026-08-28T00:00:00Z",
                            "manufacturing_release": True,
                        },
                        "reviews": [
                            {
                                "id": item_id,
                                "item": item_id,
                                "status": "pass",
                                "evidence": "measured evidence",
                                "decision": "accepted",
                            }
                            for item_id in required_ids
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(validate_board_review(review_path), [])

    def test_current_board_review_release_is_revoked_after_semantic_escape(self):
        review = json.loads((ROOT / "gates/board_review_v1.json").read_text(encoding="utf-8"))
        meta = review["_meta"]
        self.assertIs(meta["manufacturing_release"], False)
        revocation = meta["release_revocation"]
        self.assertEqual(revocation["incident_id"], "PIT-20260830-001")
        self.assertIs(revocation["human_resign_required"], True)
        self.assertEqual(revocation["superseded_signoff"]["reviewer"], "sca331613-commits")
        self.assertTrue(revocation["superseded_signoff"]["auto_evidence"])
        self.assertTrue(revocation["superseded_signoff"]["drc_evidence"])

    def test_revoked_board_review_requires_audit_metadata(self):
        required_ids = (
            "USB_EDGE",
            "ESP_ANTENNA",
            "GROUND_RETURN",
            "DECOUPLING",
            "USB_ROUTING",
            "SHT30_THERMAL",
            "PROTECTION",
            "ASSEMBLY",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            review_path = Path(temp_dir) / "review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "_meta": {
                            "reviewer": None,
                            "reviewed_at": None,
                            "manufacturing_release": False,
                        },
                        "reviews": [
                            {
                                "id": item_id,
                                "item": item_id,
                                "status": "pass",
                                "evidence": "historical measured evidence",
                                "decision": "historical decision",
                            }
                            for item_id in required_ids
                        ],
                    }
                ),
                encoding="utf-8",
            )

            errors = validate_board_review(review_path)

        self.assertTrue(any("release_revocation must be an object" in error for error in errors))

    def test_malformed_structured_reports_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            erc_path = root / "erc.json"
            drc_path = root / "drc.json"
            erc_path.write_text("{}", encoding="utf-8")
            drc_path.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                count_erc_errors(erc_path)
            with self.assertRaises(ValueError):
                count_drc_findings(drc_path)

    def test_generated_bom_matches_every_canonical_field(self):
        source_path = ROOT / "gates/bom/bom_v1.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        by_ref = {}
        for item in source["items"]:
            for ref in (part.strip() for part in item["ref"].split(",")):
                by_ref[ref] = item

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "bom.csv"
            self.assertEqual(generate_bom_csv(source_path, output_path), 21)
            with output_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual({row["Designator"] for row in rows}, set(by_ref))
        for row in rows:
            item = by_ref[row["Designator"]]
            self.assertEqual(row["Comment"], item["value"])
            self.assertEqual(row["Footprint"], item["footprint"])
            self.assertEqual(row["LCSC Part #"], item["lcsc"])
            self.assertEqual(row["JLC Lib"], item["jlc_lib"])
            self.assertEqual(row["Stock@freeze"], str(item["stock"]))

    def test_invalid_bom_does_not_overwrite_existing_csv(self):
        source = json.loads((ROOT / "gates/bom/bom_v1.json").read_text(encoding="utf-8"))
        source["items"][0]["lcsc"] = "TBD"
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_path = root / "bom.json"
            output_path = root / "bom.csv"
            source_path.write_text(json.dumps(source), encoding="utf-8")
            output_path.write_bytes(b"sentinel")

            with self.assertRaises(ValueError):
                generate_bom_csv(source_path, output_path)
            self.assertEqual(output_path.read_bytes(), b"sentinel")


if __name__ == "__main__":
    unittest.main()
