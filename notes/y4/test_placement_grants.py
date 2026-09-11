"""Tests for neutral placement-grant generation (public-info-only, oracle-free)."""
import json
import unittest
from pathlib import Path

from notes.y4.placement_grants import (
    CLEARANCE_MM, GrantError, MARGIN_MM, MIN_SLOTS, PAPER_MM, SPACING_MM,
    canonical_grants_bytes, generate_grants, nearest_slot,
)
from notes.y4.source_parser import parse_schematic
from tools import y4_dry_runner as runner

REPO = Path(__file__).resolve().parents[2]
NATIVE = REPO / "tests" / "fixtures" / "repair_pr1" / "native"
CASES = ("DC-01", "DC-02", "DC-03", "DC-04", "DC-05")


class PlacementGrantTests(unittest.TestCase):
    def test_generation_is_deterministic_and_oracle_free(self):
        text = (NATIVE / "DC-01" / "fault.kicad_sch").read_text(encoding="utf-8")
        first = generate_grants(text)
        second = generate_grants(text)
        self.assertEqual(canonical_grants_bytes(first), canonical_grants_bytes(second))
        # the algorithm consumes only the source text and opens no files.
        source = (REPO / "notes" / "y4" / "placement_grants.py").read_text(encoding="utf-8")
        for forbidden in ("repair_ops", "repair_pr1", "tests/fixtures", "open("):
            self.assertNotIn(forbidden, source)

    def test_all_five_cases_have_capacity_on_spec(self):
        for case in CASES:
            with self.subTest(case=case):
                text = (NATIVE / case / "fault.kicad_sch").read_text(encoding="utf-8")
                grants = generate_grants(text)
                self.assertEqual(grants["paper"], "A4")
                self.assertGreaterEqual(grants["slot_count"], MIN_SLOTS)
                slots = grants["slots"]
                pairs = [(s["x_mil"], s["y_mil"]) for s in slots]
                self.assertEqual(len(pairs), len(set(pairs)))
                width_mm, height_mm = PAPER_MM["A4"]
                occupied = [(s.x, s.y) for s in parse_schematic(text).symbols]
                for x_mil, y_mil in pairs:
                    x_mm, y_mm = x_mil * 0.0254, y_mil * 0.0254
                    self.assertGreaterEqual(x_mm, MARGIN_MM - 1e-9)
                    self.assertLessEqual(x_mm, width_mm - MARGIN_MM + 1e-9)
                    self.assertLessEqual(y_mm, height_mm - MARGIN_MM + 1e-9)
                    for px, py in occupied:
                        dist2 = (x_mm - px) ** 2 + (y_mm - py) ** 2
                        self.assertGreaterEqual(dist2, (CLEARANCE_MM - 1e-9) ** 2)
                # grid spacing is fixed and experiment-wide
                self.assertEqual(grants["spacing_mil"], round(SPACING_MM / 0.0254))

    def test_no_case_specific_branching_in_generator(self):
        source = (REPO / "notes" / "y4" / "placement_grants.py").read_text(encoding="utf-8")
        for case in CASES:
            self.assertNotIn(case, source)
        self.assertNotIn("case_public_id", source)
        self.assertNotIn("fault.kicad_sch", source)

    def test_generator_output_passes_runner_validation(self):
        text = (NATIVE / "DC-03" / "fault.kicad_sch").read_text(encoding="utf-8")
        grants = generate_grants(text)["slots"]
        self.assertEqual(runner._grants(grants), grants)

    def test_nearest_slot_is_deterministic_and_granted(self):
        grants = [{"x_mil": 100, "y_mil": 100}, {"x_mil": 500, "y_mil": 100},
                  {"x_mil": 100, "y_mil": 500}]
        chosen = nearest_slot(grants, 4.0, 2.6)
        self.assertIn(chosen, grants)
        self.assertEqual(chosen, nearest_slot(list(reversed(grants)), 4.0, 2.6))

    def test_missing_paper_fails_closed(self):
        with self.assertRaises(GrantError):
            generate_grants("(kicad_sch (symbol (lib_id \"Device:R\")))")


if __name__ == "__main__":
    unittest.main()
