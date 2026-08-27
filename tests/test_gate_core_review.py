import copy
import json
from pathlib import Path
import tempfile
import unittest

from gates.gate_core import (
    count_drc_findings,
    count_erc_errors,
    drc_gate_verdict,
    erc_gate_verdict,
    validate_bom,
)


ROOT = Path(__file__).resolve().parents[1]


class GateCoreReviewTests(unittest.TestCase):
    def _write_json(self, root, name, data):
        path = Path(root) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_empty_erc_sheets_fail_closed(self):
        report = {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_sch",
            "sheets": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(temp_dir, "erc.json", report)
            with self.assertRaises(ValueError):
                count_erc_errors(path)

    def test_erc_violation_missing_severity_fails_closed(self):
        report = {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_sch",
            "sheets": [{"path": "/", "violations": [{"type": "unknown"}]}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(temp_dir, "erc.json", report)
            with self.assertRaises(ValueError):
                count_erc_errors(path)

    def test_erc_unknown_severity_fails_closed(self):
        report = {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_sch",
            "sheets": [{"path": "/", "violations": [{"severity": "mystery"}]}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(temp_dir, "erc.json", report)
            with self.assertRaises(ValueError):
                count_erc_errors(path)

    def test_empty_drc_arrays_without_kicad_metadata_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(
                temp_dir,
                "drc.json",
                {"violations": [], "unconnected_items": []},
            )
            with self.assertRaises(ValueError):
                count_drc_findings(path)

    def test_valid_empty_kicad_reports_remain_green(self):
        erc = {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_sch",
            "sheets": [{"path": "/", "violations": []}],
        }
        drc = {
            "$schema": "https://schemas.kicad.org/drc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_pcb",
            "violations": [],
            "unconnected_items": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            erc_path = self._write_json(temp_dir, "erc.json", erc)
            drc_path = self._write_json(temp_dir, "drc.json", drc)
            self.assertEqual(count_erc_errors(erc_path), 0)
            self.assertEqual(count_drc_findings(drc_path), (0, 0))

    def test_each_bom_constraint_rejects_a_single_defect(self):
        valid = {
            "_meta": {"frozen_at": "2026-08-25T05:44:05Z"},
            "items": [
                {
                    "ref": "R1",
                    "value": "1k",
                    "lcsc": "C123",
                    "jlc_lib": "base",
                    "stock": 1,
                    "footprint": "Resistor_SMD:R_0603_1608Metric",
                }
            ],
        }
        cases = (
            ("duplicate ref", lambda data: data["items"][0].update(ref="R1,R1"), "duplicate ref"),
            ("missing ref", lambda data: data["items"][0].update(ref=""), "missing refs"),
            ("TBD LCSC", lambda data: data["items"][0].update(lcsc="TBD"), "TBD"),
            ("missing LCSC", lambda data: data["items"][0].pop("lcsc"), "LCSC"),
            ("zero stock", lambda data: data["items"][0].update(stock=0), "stock"),
            ("missing footprint", lambda data: data["items"][0].update(footprint=""), "footprint"),
            ("missing library", lambda data: data["items"][0].update(jlc_lib=""), "library"),
            ("date-only freeze", lambda data: data["_meta"].update(frozen_at="2026-08-25"), "frozen_at"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, (name, mutate, expected) in enumerate(cases):
                with self.subTest(name=name):
                    fixture = copy.deepcopy(valid)
                    mutate(fixture)
                    path = self._write_json(temp_dir, f"bom-{index}.json", fixture)
                    errors = validate_bom(path)
                    self.assertTrue(errors)
                    self.assertTrue(any(expected in error for error in errors), errors)

    def test_minimal_legal_bom_returns_no_errors(self):
        valid = {
            "_meta": {"frozen_at": "2026-08-25T05:44:05Z"},
            "items": [
                {
                    "ref": "R1",
                    "value": "1k",
                    "lcsc": "C123",
                    "jlc_lib": "base",
                    "stock": 1,
                    "footprint": "Resistor_SMD:R_0603_1608Metric",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(temp_dir, "bom.json", valid)
            self.assertEqual(validate_bom(path), [])

    def test_erc_two_errors_has_explicit_fail_exit_semantics(self):
        verdict = erc_gate_verdict(ROOT / "tests/fixtures/g2_erc_before_reset.json")
        self.assertEqual(
            verdict,
            {"status": "fail", "exit_code": 1, "error_count": 2},
        )

    def test_drc_zero_findings_has_explicit_pass_exit_semantics(self):
        verdict = drc_gate_verdict(ROOT / "notes/m1-evidence/g4_drc_final.json")
        self.assertEqual(
            verdict,
            {
                "status": "pass",
                "exit_code": 0,
                "violation_count": 0,
                "unconnected_count": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
