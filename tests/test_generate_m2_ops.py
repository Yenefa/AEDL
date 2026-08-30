import copy
import unittest

from tools.generate_m2_ops import inject_virtual_power_ops, split_akcli_intent


class GenerateM2OpsTests(unittest.TestCase):
    def setUp(self):
        self.intent = {
            "protocol_version": 1,
            "components": {
                "U1": {"lib_id": "Device:R", "value": "1k"},
                "#FLG01": {"lib_id": "power:PWR_FLAG", "value": "PWR_FLAG", "virtual": True},
                "#FLG02": {"lib_id": "power:PWR_FLAG", "value": "PWR_FLAG", "virtual": True},
            },
            "nets": {
                "+5V": ["U1.1", "#FLG01.1"],
                "GND": ["U1.2", "#FLG02.1"],
            },
        }

    def test_split_removes_only_supported_virtual_power_flags(self):
        akcli_intent, virtual = split_akcli_intent(self.intent)
        self.assertEqual(set(akcli_intent["components"]), {"U1"})
        self.assertEqual(akcli_intent["nets"], {"+5V": ["U1.1"], "GND": ["U1.2"]})
        self.assertEqual(set(virtual), {"#FLG01", "#FLG02"})
        self.assertIn("#FLG01", self.intent["components"])

    def test_unknown_virtual_component_fails_closed(self):
        intent = copy.deepcopy(self.intent)
        intent["components"]["X1"] = {"lib_id": "Device:R", "value": "1k", "virtual": True}
        intent["nets"]["GND"].append("X1.1")
        with self.assertRaisesRegex(ValueError, "unsupported virtual"):
            split_akcli_intent(intent)

    def test_injection_adds_deterministic_power_flag_ops_and_labels(self):
        _, virtual = split_akcli_intent(self.intent)
        base = {
            "protocol_version": 2,
            "target_format": "kicad",
            "_generator": "akcli ops from-intent",
            "ops": [
                {"op": "place_component", "lib_id": "Device:R", "designator": "U1", "x_mil": 1000, "y_mil": 1000, "value": "1k"},
                {"op": "add_net_label", "name": "+5V", "at": "U1.1"},
                {"op": "add_no_connect", "pin": "U1.3"},
            ],
        }

        result = inject_virtual_power_ops(base, self.intent, virtual)

        placed = {op["designator"]: op for op in result["ops"] if op["op"] == "place_component"}
        self.assertEqual(placed["#FLG01"]["lib_id"], "power:PWR_FLAG")
        self.assertEqual((placed["#FLG01"]["x_mil"], placed["#FLG01"]["y_mil"]), (600, 600))
        self.assertEqual((placed["#FLG02"]["x_mil"], placed["#FLG02"]["y_mil"]), (1800, 600))
        labels = {(op.get("name"), op.get("at")) for op in result["ops"] if op["op"] == "add_net_label"}
        self.assertIn(("+5V", "#FLG01.1"), labels)
        self.assertIn(("GND", "#FLG02.1"), labels)
        self.assertIn("controlled virtual PWR_FLAG compatibility", result["_generator"])


if __name__ == "__main__":
    unittest.main()
