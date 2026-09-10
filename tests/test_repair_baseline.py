import copy
import json
from pathlib import Path
import tempfile
import unittest

from gates.schematic_semantics import evaluate_observations
from tools.repair_baseline import (
    BaselineInputError,
    build_proposal,
    main,
    normalize_value,
    parse_detail_line,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "schematic_semantics"
CONTRACT = ROOT / "gates" / "contracts" / "m2_schematic_contract_v1.json"

# 公共事实包草案（schema 与 tools/repair_baseline.py 对齐）。
# 批准值与保护约束全部来自公开合同 m2_schematic_contract_v1.json，不含任何逐例答案。
FACTS_COMPLETE = {
    "schema": "aedl.public-facts.draft-0.1",
    "facts_status": "complete",
    "facts_gaps": [],
    "approved_component_values": ["22R", "10k", "1uF"],
    "protected": {
        "nets_must_not_merge": [
            ["USB_DP", "USB_DM"],
            ["USB_DP_CONN", "USB_DM_CONN"],
            ["+3V3", "GND"],
        ],
        "firmware_constants_read_only": True,
    },
}


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


def checker_feedback(observations):
    """用真实检查器把观测变成 findings 报告（D 组只吃这份公共反馈）。"""
    return evaluate_observations(load_json(CONTRACT), observations)


def remove_component_fault(ref, pins):
    """按现有夹具同一模式构造"整元件缺失"故障（案例 3 型）。"""
    mutations = []
    for view in ("intent", "netlist", "pcb"):
        for pin in pins:
            mutations.append(
                {"op": "delete", "path": ["views", view, "pins", f"{ref}.{pin}"]}
            )
        mutations.append(
            {"op": "delete", "path": ["views", view, "components", ref]}
        )
    return {"mutations": mutations}


def ops_without_because(proposal):
    return [
        {k: v for k, v in op.items() if k != "because"} for op in proposal.operations
    ]


class RepairBaselineTests(unittest.TestCase):
    def setUp(self):
        self.good = load_json(FIXTURES / "good_observations.json")
        self.facts = copy.deepcopy(FACTS_COMPLETE)

    def feedback_for(self, fixture_name):
        fault = load_json(FIXTURES / fixture_name)
        return checker_feedback(inject_fault(self.good, fault))

    # ---- 基础路径 ----

    def test_no_change_needed_on_passing_board(self):
        feedback = checker_feedback(self.good)
        self.assertEqual(feedback["status"], "pass")
        proposal = build_proposal(feedback, self.facts)
        self.assertEqual(proposal.decision, "NO_CHANGE_NEEDED")
        self.assertEqual(proposal.operations, [])

    # ---- 可修复案例：从检查器 expected 推导操作 ----

    def test_case1_reversed_usb_repairs_chip_pins(self):
        proposal = build_proposal(self.feedback_for("fault_reversed_usb.json"), self.facts)
        self.assertEqual(proposal.decision, "PROPOSE_REPAIR")
        self.assertEqual(proposal.rules_addressed, ["USB_POLARITY_AND_SERIES"])
        self.assertEqual(ops_without_because(proposal), [
            {"op": "set_pin_net", "ref": "U1", "pin": "14", "net": "USB_DP"},
            {"op": "set_pin_net", "ref": "U1", "pin": "13", "net": "USB_DM"},
        ])
        # PCB 未同步必须显示边界（方案 §2）
        self.assertTrue(any("PCB" in note for note in proposal.notes))

    def test_case2_floating_addr_ties_to_gnd(self):
        proposal = build_proposal(self.feedback_for("fault_floating_addr.json"), self.facts)
        self.assertEqual(proposal.decision, "PROPOSE_REPAIR")
        self.assertEqual(proposal.rules_addressed, ["SHT30_ADDRESS"])
        self.assertEqual(ops_without_because(proposal), [
            {"op": "set_pin_net", "ref": "U2", "pin": "2", "net": "GND"},
        ])

    def test_case2b_firmware_mismatch_refuses(self):
        # 固件只读：固件常量与公开规则不符 → 拒绝，不给猜测性补丁
        proposal = build_proposal(self.feedback_for("fault_firmware_address.json"), self.facts)
        self.assertEqual(proposal.decision, "REFUSE")
        self.assertEqual(proposal.operations, [])
        self.assertEqual(proposal.refusal["reason_code"], "FIRMWARE_READ_ONLY_CONFLICT")
        self.assertEqual(proposal.refusal["rules_blocked"], ["SHT30_ADDRESS"])

    def test_case3_missing_usb_series_resistors_added(self):
        fault = remove_component_fault("R7", ["1", "2"])
        fault2 = remove_component_fault("R8", ["1", "2"])
        fault["mutations"].extend(fault2["mutations"])
        proposal = build_proposal(checker_feedback(inject_fault(self.good, fault)), self.facts)
        self.assertEqual(proposal.decision, "PROPOSE_REPAIR")
        self.assertEqual(proposal.rules_addressed, ["USB_POLARITY_AND_SERIES"])
        self.assertEqual(ops_without_because(proposal), [
            {"op": "add_component", "ref": "R7", "value": "22R",
             "pins": {"1": "USB_DP_CONN", "2": "USB_DP"}},
            {"op": "add_component", "ref": "R8", "value": "22R",
             "pins": {"1": "USB_DM_CONN", "2": "USB_DM"}},
        ])

    def test_case4_missing_gpio9_pullup_added(self):
        proposal = build_proposal(
            self.feedback_for("fault_missing_gpio9_pullup.json"), self.facts)
        self.assertEqual(proposal.decision, "PROPOSE_REPAIR")
        self.assertEqual(proposal.rules_addressed, ["ESP32_GPIO9_PULLUP"])
        self.assertEqual(ops_without_because(proposal), [
            {"op": "add_component", "ref": "R9", "value": "10k",
             "pins": {"1": "+3V3", "2": "BOOT"}},
        ])

    def test_case5_missing_en_cap_added(self):
        proposal = build_proposal(self.feedback_for("fault_missing_en_cap.json"), self.facts)
        self.assertEqual(proposal.decision, "PROPOSE_REPAIR")
        self.assertEqual(proposal.rules_addressed, ["ESP32_EN_RC"])
        self.assertEqual(ops_without_because(proposal), [
            {"op": "add_component", "ref": "C5", "value": "1uF",
             "pins": {"1": "EN", "2": "GND"}},
        ])

    # ---- 保护规则：受保护引脚不许乱接 ----

    def test_protected_no_connect_pin_repairs_to_mark_no_connect(self):
        feedback = {"findings": [{
            "rule_id": "SHT30_UNUSED_PINS",
            "status": "fail",
            "details": [
                'netlist.pins.U2.3: expected {"net": null, "no_connect": true}, '
                'observed {"net": "GND", "no_connect": false}',
            ],
        }]}
        proposal = build_proposal(feedback, self.facts)
        self.assertEqual(proposal.decision, "PROPOSE_REPAIR")
        self.assertEqual(ops_without_because(proposal), [
            {"op": "mark_no_connect", "ref": "U2", "pin": "3"},
        ])

    # ---- 拒绝路径（fail-closed）----

    def test_case6_refuses_when_facts_incomplete(self):
        # U3 型案例：公共事实包声明资料不足 → 必须拒绝且零操作
        facts = copy.deepcopy(self.facts)
        facts["facts_status"] = "incomplete"
        facts["facts_gaps"] = [
            {"what": "U3 精确型号/封装的适用参数缺失", "source": "facts.U3"}
        ]
        proposal = build_proposal(self.feedback_for("fault_floating_addr.json"), facts)
        self.assertEqual(proposal.decision, "REFUSE")
        self.assertEqual(proposal.operations, [])
        self.assertEqual(proposal.refusal["reason_code"], "INSUFFICIENT_EVIDENCE")
        self.assertTrue(any("U3" in gap["what"] for gap in proposal.refusal["gaps"]))

    def test_unhandled_rule_refuses(self):
        feedback = self.feedback_for("fault_reversed_usb.json")
        feedback["findings"].append({
            "rule_id": "UNRECOGNIZED_RULE",
            "status": "fail",
            "details": [],
        })
        proposal = build_proposal(feedback, self.facts)
        self.assertEqual(proposal.decision, "REFUSE")
        self.assertEqual(proposal.refusal["reason_code"], "UNHANDLED_RULE")
        self.assertEqual(proposal.operations, [])

    def test_value_not_approved_refuses(self):
        facts = copy.deepcopy(self.facts)
        facts["approved_component_values"] = ["10k", "1uF"]  # 去掉 22R
        fault = remove_component_fault("R7", ["1", "2"])
        proposal = build_proposal(checker_feedback(inject_fault(self.good, fault)), facts)
        self.assertEqual(proposal.decision, "REFUSE")
        self.assertEqual(proposal.refusal["reason_code"], "VALUE_NOT_APPROVED")
        self.assertEqual(proposal.operations, [])

    def test_forbidden_net_merge_refuses(self):
        facts = copy.deepcopy(self.facts)
        facts["protected"]["nets_must_not_merge"] = [["EN", "GND"]]
        proposal = build_proposal(self.feedback_for("fault_missing_en_cap.json"), facts)
        self.assertEqual(proposal.decision, "REFUSE")
        self.assertEqual(proposal.refusal["reason_code"], "EVIDENCE_CONFLICT")
        self.assertEqual(proposal.operations, [])

    def test_conflicting_nets_across_views_refuse(self):
        # 同一引脚在两个视图给出不同 net → 证据冲突，拒绝
        feedback = {"findings": [{
            "rule_id": "USB_POLARITY_AND_SERIES",
            "status": "fail",
            "details": [
                'intent.pins.U1.13: expected {"net": "USB_DM"}, observed {"net": "USB_A"}',
                'netlist.pins.U1.13: expected {"net": "USB_DM"}, observed {"net": "USB_B"}',
            ],
        }]}
        proposal = build_proposal(feedback, self.facts)
        self.assertEqual(proposal.decision, "REFUSE")
        self.assertEqual(proposal.refusal["reason_code"], "EVIDENCE_CONFLICT")

    def test_missing_observation_in_one_view_does_not_conflict(self):
        # intent 天然不列悬空引脚：<missing> 不与具体观测冲突，且具体观测可用
        feedback = {"findings": [{
            "rule_id": "USB_POLARITY_AND_SERIES",
            "status": "fail",
            "details": [
                'intent.pins.U1.13: expected {"net": "USB_DM"}, observed "<missing>"',
                'netlist.pins.U1.13: expected {"net": "USB_DM"}, '
                'observed {"net": "USB_DP", "no_connect": false}',
            ],
        }]}
        proposal = build_proposal(feedback, self.facts)
        self.assertEqual(proposal.decision, "PROPOSE_REPAIR")
        self.assertEqual(ops_without_because(proposal), [
            {"op": "set_pin_net", "ref": "U1", "pin": "13", "net": "USB_DM"},
        ])

    def test_malformed_detail_line_refuses(self):
        feedback = self.feedback_for("fault_reversed_usb.json")
        feedback["findings"][0]["details"] = ["这行不是合法的检查反馈格式"]
        proposal = build_proposal(feedback, self.facts)
        self.assertEqual(proposal.decision, "REFUSE")
        self.assertEqual(proposal.refusal["reason_code"], "MALFORMED_FEEDBACK")

    def test_malformed_pin_key_refuses(self):
        feedback = {"findings": [{
            "rule_id": "SHT30_ADDRESS",
            "status": "fail",
            "details": ['intent.pins.U2: expected {"net": "GND"}, '
                        'observed {"net": null, "no_connect": true}'],
        }]}
        proposal = build_proposal(feedback, self.facts)
        self.assertEqual(proposal.decision, "REFUSE")
        self.assertEqual(proposal.refusal["reason_code"], "MALFORMED_FEEDBACK")

    def test_facts_schema_mismatch_raises(self):
        with self.assertRaises(BaselineInputError):
            build_proposal({"findings": []}, {"schema": "wrong.schema"})

    # ---- 值归一化与解析器 ----

    def test_normalize_value(self):
        cases = {
            "22Ω": "22R", "22R": "22R", "22": "22R", 22: "22R",
            "10K": "10k", "10k": "10k",
            "1µF": "1uF", "1uF": "1uF",
            "not-a-value": None, None: None,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_value(raw), expected)

    def test_parse_detail_line(self):
        parsed = parse_detail_line(
            'intent.pins.U2.2: expected {"net": "GND"}, '
            'observed {"net": null, "no_connect": true}')
        self.assertEqual(
            parsed,
            ("intent", "pins", "U2.2", {"net": "GND"}, {"net": None, "no_connect": True}),
        )
        parsed = parse_detail_line(
            'netlist.components.R9: expected {"value": "10k"}, observed "<missing>"')
        self.assertEqual(
            parsed, ("netlist", "components", "R9", {"value": "10k"}, "<missing>"))
        self.assertIsNone(parse_detail_line(" nonsense "))
        self.assertIsNone(parse_detail_line(
            'intent.pins.U2.2: expected broken json, observed {}'))

    # ---- CLI ----

    def test_cli_writes_proposal_and_exit_codes(self):
        feedback = self.feedback_for("fault_reversed_usb.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            feedback_path = root / "feedback.json"
            facts_path = root / "facts.json"
            out_path = root / "out" / "proposal.json"
            feedback_path.write_text(
                json.dumps(feedback, ensure_ascii=False), encoding="utf-8")
            facts_path.write_text(json.dumps(self.facts), encoding="utf-8")

            rc = main(["--feedback", str(feedback_path),
                       "--facts", str(facts_path), "--out", str(out_path)])
            self.assertEqual(rc, 0)
            proposal = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(proposal["schema"], "aedl.repair-proposal.draft-0.1")
            self.assertEqual(proposal["decision"], "PROPOSE_REPAIR")
            self.assertEqual(proposal["generated_by"]["arm"], "D")
            self.assertEqual(len(proposal["inputs"]["feedback_sha256"]), 64)
            self.assertEqual(len(proposal["inputs"]["facts_sha256"]), 64)

            # facts schema 错误 → 退出码 2
            bad_facts = root / "bad_facts.json"
            bad_facts.write_text(json.dumps({"schema": "nope"}), encoding="utf-8")
            rc = main(["--feedback", str(feedback_path),
                       "--facts", str(bad_facts), "--out", str(out_path)])
            self.assertEqual(rc, 2)

            # 输入文件缺失 → 退出码 2
            rc = main(["--feedback", str(root / "missing.json"),
                       "--facts", str(facts_path), "--out", str(out_path)])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
