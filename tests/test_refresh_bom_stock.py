import copy
from pathlib import Path
import tempfile
import unittest

from gates.refresh_bom_stock import (
    apply_catalog_snapshot,
    build_stock_evidence,
    select_exact_part,
)


class RefreshBomStockTests(unittest.TestCase):
    def test_exact_catalog_match_is_required_and_positive(self):
        payload = {
            "items": [
                {
                    "component_code": "C23345",
                    "model": "0603WAF220JT5E",
                    "brand": "UNI-ROYAL",
                    "package": "0603",
                    "library": "base",
                    "stock": 123,
                },
                {"component_code": "C999", "stock": 5},
            ]
        }
        self.assertEqual(select_exact_part("C23345", payload)["stock"], 123)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            select_exact_part("C404", payload)
        payload["items"][0]["stock"] = 0
        with self.assertRaisesRegex(ValueError, "positive stock"):
            select_exact_part("C23345", payload)
        self.assertEqual(
            select_exact_part("C23345", payload, require_positive=False)["stock"],
            0,
        )

    def test_snapshot_updates_every_item_and_binds_metadata(self):
        source = {
            "_meta": {"frozen_at": "2026-08-25T00:00:00Z"},
            "items": [
                {"ref": "R7,R8", "lcsc": "C23345", "stock": 1, "jlc_lib": "expand"},
                {"ref": "C5", "lcsc": "C59782", "stock": 1, "jlc_lib": "expand"},
            ],
        }
        original = copy.deepcopy(source)
        catalog = {
            "C23345": {
                "component_code": "C23345", "model": "0603WAF220JT5E",
                "brand": "UNI-ROYAL", "package": "0603", "library": "base", "stock": 100,
            },
            "C59782": {
                "component_code": "C59782", "model": "CL10B105KO8NNNC",
                "brand": "Samsung", "package": "0603", "library": "expand", "stock": 200,
            },
        }

        updated = apply_catalog_snapshot(
            source, catalog, "2026-08-30T06:30:00Z", "jlcpcb 0.1.0"
        )

        self.assertEqual(source, original)
        self.assertEqual(updated["_meta"]["frozen_at"], "2026-08-30T06:30:00Z")
        self.assertEqual(updated["items"][0]["stock"], 100)
        self.assertEqual(updated["items"][0]["jlc_lib"], "base")
        self.assertEqual(updated["items"][0]["mpn"], "0603WAF220JT5E")
        self.assertEqual(updated["items"][1]["manufacturer"], "Samsung")

    def test_zero_stock_is_preserved_in_fail_closed_attempt_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "gates/bom/bom_v1.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"items": []}', encoding="utf-8")
            evidence = build_stock_evidence(
                root=root,
                source_path=source,
                catalog={
                    "C82942": {
                        "model": "ME6211C33M5G-N",
                        "brand": "MICRONE",
                        "package": "SOT-23-5",
                        "library": "expand",
                        "stock": 0,
                    }
                },
                generated_at="2026-08-30T10:30:00Z",
                tool_version="jlcpcb 0.1.0",
                status="fail",
                errors=["C82942 has zero JLC assembly stock"],
            )

        self.assertEqual(evidence["status"], "fail")
        self.assertEqual(evidence["parts"][0]["assembly_stock"], 0)
        self.assertTrue(evidence["errors"])


if __name__ == "__main__":
    unittest.main()
