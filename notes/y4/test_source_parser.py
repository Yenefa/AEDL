"""Tests for the public-source parser (promoted from the r15 candidate)."""
import unittest
from pathlib import Path

from notes.y4.source_parser import parse_schematic

REPO = Path(__file__).resolve().parents[2]
NATIVE = REPO / "tests" / "fixtures" / "repair_pr1" / "native"

SYNTHETIC = '''
(kicad_sch
  (wire (pts (xy 10.16 20.32) (xy 20.32 20.32)) (stroke (width 0) (type default)) (uuid "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0001"))
  (label "NET_A" (at 10.16 20.32 0) (effects (font (size 1.27 1.27))) (uuid "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0002"))
  (symbol (lib_id "Device:R") (at 30.48 40.64 0) (unit 1) (uuid "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0003") (pin "1" (uuid "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0004")) (pin "2" (uuid "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0005")) (property "Reference" "R1" (at 0 0 0) (effects (font (size 1.27 1.27)))) (property "Footprint" "Resistor_SMD:R_0603_1608Metric" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes))))
  (symbol (lib_id "Device:R") (at 50.8 40.64 0) (unit 1) (uuid "aaaaaaaa-bbbb-cccc-dddd-eeeeffff0006") (property "Reference" "R3" (at 0 0 0) (effects (font (size 1.27 1.27)))) (property "Footprint" "Resistor_SMD:R_0603_1608Metric" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes))))
)
'''


class SourceParserTests(unittest.TestCase):
    def test_synthetic_parse(self):
        sch = parse_schematic(SYNTHETIC)
        self.assertEqual(len(sch.wires), 1)
        self.assertEqual(sch.wires[0].mid, (15.24, 20.32))
        self.assertEqual([l.name for l in sch.labels], ["NET_A"])
        self.assertEqual(sch.designator_gaps("R"), [2])
        r1 = next(s for s in sch.symbols if s.ref == "R1")
        self.assertEqual(len(r1.pins), 2)

    def test_real_public_sources_parse_and_derive(self):
        checks = {
            "DC-01": {"labels": 2},
            "DC-03": {"prefix": "R", "gaps": [7, 8], "mid": (218.44, 193.04)},
            "DC-04": {"prefix": "R", "next": 9},
            "DC-05": {"prefix": "C", "next": 5},
        }
        for case, expect in checks.items():
            with self.subTest(case=case):
                text = (NATIVE / case / "fault.kicad_sch").read_text(encoding="utf-8")
                sch = parse_schematic(text)
                self.assertGreater(len(sch.symbols), 0)
                self.assertGreater(len(sch.labels), 0)
                if case == "DC-03":
                    self.assertGreater(len(sch.wires), 0)
                if expect.get("labels"):
                    self.assertGreaterEqual(len(sch.labels), expect["labels"])
                if expect.get("gaps"):
                    self.assertEqual(sch.designator_gaps(expect["prefix"]), expect["gaps"])
                if expect.get("next"):
                    self.assertEqual(sch.next_designator(expect["prefix"]), expect["next"])
                if expect.get("mid"):
                    self.assertIn(expect["mid"], sch.wire_midpoints())

    def test_label_lookup_by_name_and_position(self):
        text = (NATIVE / "DC-01" / "fault.kicad_sch").read_text(encoding="utf-8")
        sch = parse_schematic(text)
        labels = [l for l in sch.labels
                  if l.name == "USB_DP" and (l.x, l.y) == (212.09, 295.91)]
        self.assertEqual(len(labels), 1)
        self.assertTrue(labels[0].uuid)


if __name__ == "__main__":
    unittest.main()
