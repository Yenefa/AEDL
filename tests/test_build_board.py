from pathlib import Path
import tempfile
import unittest

from tools.build_board import (
    FP_MAP,
    PLACEMENT,
    REFERENCE_PLACEMENT,
    apply_reference_placement,
    physical_components,
    resolve_root,
)


ROOT = Path(__file__).resolve().parents[1]


class BuildBoardTests(unittest.TestCase):
    def test_default_root_is_derived_from_script_location(self):
        self.assertEqual(resolve_root(None), ROOT)

    def test_explicit_root_is_resolved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual(resolve_root(temp_dir), Path(temp_dir).resolve())

    def test_virtual_schematic_components_are_not_board_parts(self):
        components = {
            "U1": {"value": "physical"},
            "#FLG01": {"value": "PWR_FLAG", "virtual": True},
            "#FLG02": {"value": "PWR_FLAG", "virtual": True},
        }
        self.assertEqual(list(physical_components(components)), ["U1"])

    def test_repaired_components_have_deterministic_functional_placements(self):
        for ref in ("R7", "R8", "R9", "C5"):
            self.assertIn(ref, FP_MAP)
            self.assertIn(ref, PLACEMENT)

        # U1 pin 14 (D+) and pin 13 (D-) sit at these absolute coordinates
        # for the locked WROOM-02 footprint and U1 placement.
        u1_x, u1_y, _ = PLACEMENT["U1"]
        usb_pins = {
            "R7": (u1_x + 8.75, u1_y),
            "R8": (u1_x + 8.75, u1_y + 1.5),
        }
        for ref, (pin_x, pin_y) in usb_pins.items():
            x, y, rotation = PLACEMENT[ref]
            self.assertLessEqual(abs(x - pin_x), 3.0)
            self.assertLessEqual(abs(y - pin_y), 0.01)
            self.assertEqual(rotation, 180)

        self.assertEqual(PLACEMENT["C5"], (1.45, 13.5, 90))
        self.assertEqual(PLACEMENT["R9"], (1.45, 22.5, 90))
        self.assertEqual(REFERENCE_PLACEMENT["C5"], (1.45, 10.0, 90))
        self.assertEqual(REFERENCE_PLACEMENT["R7"], (23.3, 16.2, 0))
        self.assertEqual(REFERENCE_PLACEMENT["R9"], (1.45, 27.0, 90))
        self.assertEqual(REFERENCE_PLACEMENT["U1"], (12.0, 27.0, 0))

    def test_reference_polish_is_reproducible_and_fails_on_missing_targets(self):
        class FakeReference:
            def __init__(self):
                self.position = None
                self.angle = None

            def SetPosition(self, position):
                self.position = position

            def SetTextAngleDegrees(self, angle):
                self.angle = angle

        class FakeFootprint:
            def __init__(self):
                self.reference = FakeReference()

            def Reference(self):
                return self.reference

        class FakePcbnew:
            @staticmethod
            def FromMM(value):
                return value

            @staticmethod
            def VECTOR2I(x, y):
                return (x, y)

        loaded = {ref: FakeFootprint() for ref in REFERENCE_PLACEMENT}
        apply_reference_placement(loaded, FakePcbnew)
        self.assertEqual(loaded["R7"].reference.position, (23.3, 16.2))
        self.assertEqual(loaded["R7"].reference.angle, 0)

        with self.assertRaisesRegex(ValueError, "targets missing"):
            apply_reference_placement({}, FakePcbnew)


if __name__ == "__main__":
    unittest.main()
