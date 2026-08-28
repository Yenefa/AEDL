from pathlib import Path
import tempfile
import unittest

from tools.build_board import physical_components, resolve_root


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


if __name__ == "__main__":
    unittest.main()
