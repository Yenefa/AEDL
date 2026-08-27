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
    zip_entry_names,
)


ROOT = Path(__file__).resolve().parents[1]


class GateCoreTests(unittest.TestCase):
    def test_current_erc_is_not_green(self):
        report = ROOT / "notes/m1-evidence/g2_erc_m2board.json"
        self.assertEqual(count_erc_errors(report), 2)

    def test_current_drc_is_green(self):
        report = ROOT / "notes/m1-evidence/g4_drc_final.json"
        self.assertEqual(count_drc_findings(report), (0, 0))

    def test_bom_rejects_tbd(self):
        errors = validate_bom(ROOT / "gates/bom/bom_v1.json")
        self.assertTrue(any("TBD" in error for error in errors))

    def test_current_delivery_refs_match_all_17_physical_parts(self):
        bom_refs = read_bom_refs(ROOT / "gates/bom/bom_v1.json")
        pos_refs = read_pos_refs(ROOT / "delivery/pos.csv")
        self.assertEqual(bom_refs, pos_refs)
        self.assertEqual(len(bom_refs), 17)

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


if __name__ == "__main__":
    unittest.main()
