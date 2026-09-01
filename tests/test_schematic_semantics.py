import copy
import json
from pathlib import Path
import tempfile
import unittest

from gates.schematic_semantics import (
    collect_observations,
    evaluate_observations,
    evaluate_paths,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "schematic_semantics"
CONTRACT = ROOT / "gates" / "contracts" / "m2_schematic_contract_v1.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def inject_fault(base, fault):
    result = copy.deepcopy(base)
    for mutation in fault["mutations"]:
        cursor = result
        for part in mutation["path"][:-1]:
            cursor = cursor[part]
        leaf = mutation["path"][-1]
        if mutation["op"] == "set":
            cursor[leaf] = mutation["value"]
        elif mutation["op"] == "delete":
            del cursor[leaf]
        else:
            raise AssertionError(f"unknown fixture mutation {mutation['op']}")
    return result


class SchematicSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_json(CONTRACT)
        self.good = load_json(FIXTURES / "good_observations.json")

    def test_good_independent_observations_pass(self):
        report = evaluate_observations(self.contract, self.good)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"], {"passed": 5, "failed": 0, "total": 5})

    def test_common_mode_fault_injections_are_rejected(self):
        fixtures = sorted(FIXTURES.glob("fault_*.json"))
        self.assertEqual(len(fixtures), 5)
        for path in fixtures:
            with self.subTest(fixture=path.name):
                fault = load_json(path)
                observations = inject_fault(self.good, fault)
                report = evaluate_observations(self.contract, observations)
                self.assertEqual(report["status"], "fail")
                failed_ids = {item["rule_id"] for item in report["findings"] if item["status"] == "fail"}
                self.assertIn(fault["expected_rule"], failed_ids)

    def test_missing_view_fails_closed(self):
        observations = copy.deepcopy(self.good)
        del observations["views"]["pcb"]
        report = evaluate_observations(self.contract, observations)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["findings"][0]["rule_id"], "INPUT_INVALID")

    def test_unknown_contract_severity_and_kind_fail_closed(self):
        for field, value in (("severity", "warning"), ("kind", "looks_ok")):
            with self.subTest(field=field):
                contract = copy.deepcopy(self.contract)
                contract["rules"][0][field] = value
                report = evaluate_observations(contract, self.good)
                self.assertEqual(report["status"], "fail")
                self.assertEqual(report["findings"][0]["rule_id"], "CONTRACT_INVALID")

    def test_missing_input_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"
            report = evaluate_paths(CONTRACT, missing, missing, missing, missing)
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["findings"][0]["rule_id"], "INPUT_INVALID")

    def test_collectors_parse_native_formats_and_explicit_no_connect(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            intent = root / "intent.json"
            netlist = root / "netlist.xml"
            pcb = root / "board.kicad_pcb"
            firmware = root / "sht30.h"
            intent.write_text(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "components": {"R7": {"value": "22R"}, "U2": {"value": "SHT30"}},
                        "nets": {"USB_DP": ["R7.2"], "GND": ["U2.2"]},
                    }
                ),
                encoding="utf-8",
            )
            netlist.write_text(
                """<?xml version="1.0"?><export><components>
                <comp ref="R7"><value>22R</value></comp><comp ref="U2"><value>SHT30</value></comp>
                </components><nets><net code="1" name="/USB_DP"><node ref="R7" pin="2" pintype="passive"/></net>
                <net code="2" name="unconnected-(U2-ALERT-Pad3)"><node ref="U2" pin="3" pintype="output+no_connect"/></net></nets></export>""",
                encoding="utf-8",
            )
            pcb.write_text(
                """(kicad_pcb
                (footprint "Resistor_SMD:R_0603" (property "Reference" "R7") (property "Value" "22R")
                  (pad "2" smd rect (net "USB_DP")))
                (footprint "Sensor:SHT30" (property "Reference" "U2") (property "Value" "SHT30")
                  (pad "3" smd rect)))""",
                encoding="utf-8",
            )
            firmware.write_text("static constexpr uint8_t DEFAULT_ADDR = 0x44;", encoding="utf-8")

            observations = collect_observations(intent, netlist, pcb, firmware)

        self.assertEqual(observations["views"]["intent"]["pins"]["R7.2"]["net"], "USB_DP")
        self.assertEqual(observations["views"]["netlist"]["pins"]["U2.3"], {"net": None, "no_connect": True})
        self.assertEqual(observations["views"]["pcb"]["pins"]["R7.2"]["net"], "USB_DP")
        self.assertEqual(observations["views"]["pcb"]["pins"]["U2.3"]["net"], None)
        self.assertEqual(observations["views"]["firmware"]["constants"]["DEFAULT_ADDR"], 68)


if __name__ == "__main__":
    unittest.main()
