"""AEDL Y4 arm-D baseline tests（v0.4，对齐冻结 C1 接口）。

与 v0.3 的本质区别（回应 PR #60 review）：
- 输入一律用真实 C1 make_public_context 构造 PublicContext（同时验证
  public_facts 草案不触发公共投影 leak guard）；
- 每一份输出（PATCH 与 REFUSE 都算）都喂给真实 C1 parse_proposal 验证，
  证明 D 产物能过冻结合同，而不是"自己发明的协议自己绿"；
- 不再读取 schematic_semantics findings 报告；观测直接来自公开夹具，
  修复目标只来自 public_facts 草案。
"""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.repair_baseline import (
    BaselineInputError,
    build_proposal,
    load_context,
    render,
)
from tools.repair_pipeline import parse_proposal

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "schematic_semantics"
SCRIPT = ROOT / "tools" / "repair_baseline.py"

SHA_A = "a" * 64


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


def fault(name):
    return load_json(FIXTURES / name)


GOOD = load_json(FIXTURES / "good_observations.json")

HOST_CONTEXT = {
    "context_id": "ctx-y4-test-1",
    "target": "candidate/board.kicad_sch",
    "base_source_sha256": SHA_A,
    "limits": {"max_ops": 8},
}


def pin_target(fid, anchor, net):
    return {"id": fid, "anchor": anchor, "net": net}


def component_target(fid, designator, value, pin_nets, x_mil=1000, y_mil=2000):
    return {
        "id": fid,
        "designator": designator,
        "lib_id": "Device:R",
        "value": value,
        "footprint": "Resistor_SMD:R_0603_1608Metric",
        "pin_nets": pin_nets,
        "placement": {"x_mil": x_mil, "y_mil": y_mil},
    }


def deletion_target(fid, uuid, anchor):
    return {"id": fid, "uuid": uuid, "anchor": anchor}


def complete_facts(**overrides):
    facts = {
        "facts_schema": "aedl.y4-public-facts.draft-0.1",
        "facts_status": "complete",
        "facts_gaps": [],
        "pin_targets": [],
        "component_targets": [],
        "deletion_targets": [],
        "protected_anchors": ["U2.3", "U2.6"],
    }
    facts.update(overrides)
    return facts


def make_context(observations, facts):
    """经真实 C1 构造 PublicContext（leak guard 内置）。"""
    from tools.repair_pipeline import make_public_context

    return make_public_context(HOST_CONTEXT, observations, facts)


def to_bytes(proposal):
    return json.dumps(proposal, ensure_ascii=False, sort_keys=True).encode("utf-8")


def must_parse(proposal):
    """断言 D 产物能过真实 C1 parse_proposal，并原样返回 dict 供继续断言。"""
    parse_proposal(to_bytes(proposal))
    return proposal


class BaselineTests(unittest.TestCase):
    maxDiff = None

    def header_matches_context(self, proposal, context):
        for key in ("schema_version", "context_id", "target", "base_source_sha256"):
            self.assertEqual(proposal[key], context[key], key)

    # ------------------------------------------------------------------
    # 五个计分案例型（修复路径）
    # ------------------------------------------------------------------

    def test_case_reversed_usb_needs_deletion_then_relabel(self):
        observations = inject_fault(GOOD, fault("fault_reversed_usb.json"))
        facts = complete_facts(
            pin_targets=[
                pin_target("fact-pin-14", "U1.14", "USB_DP"),
                pin_target("fact-pin-13", "U1.13", "USB_DM"),
            ],
            deletion_targets=[
                deletion_target("fact-del-13", "wire-u1-13", "U1.13"),
                deletion_target("fact-del-14", "wire-u1-14", "U1.14"),
            ],
        )
        context = make_context(observations, facts)
        proposal = must_parse(build_proposal(context))
        self.header_matches_context(proposal, context)
        self.assertEqual(proposal["decision"], "PATCH")
        ops = proposal["oplist"]["ops"]
        self.assertEqual(
            ops,
            [
                # 逐锚点（升序）：先删错标的 uuid，再补批准的网标
                {"op": "delete_object", "uuid": "wire-u1-13"},
                {"op": "add_net_label", "name": "USB_DM", "at": "U1.13"},
                {"op": "delete_object", "uuid": "wire-u1-14"},
                {"op": "add_net_label", "name": "USB_DP", "at": "U1.14"},
            ],
        )
        cited = {fid for entry in proposal["diagnosis"] for fid in entry["fact_ids"]}
        self.assertEqual(cited, {"fact-pin-13", "fact-pin-14", "fact-del-13", "fact-del-14"})

    def test_case_floating_addr_gets_net_label(self):
        observations = inject_fault(GOOD, fault("fault_floating_addr.json"))
        facts = complete_facts(
            pin_targets=[pin_target("fact-pin-gnd", "U2.2", "GND")],
        )
        context = make_context(observations, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "PATCH")
        self.assertEqual(
            proposal["oplist"]["ops"],
            [{"op": "add_net_label", "name": "GND", "at": "U2.2"}],
        )

    def test_case_missing_component_is_placed_with_pin_labels(self):
        observations = inject_fault(GOOD, fault("fault_missing_gpio9_pullup.json"))
        facts = complete_facts(
            component_targets=[
                component_target(
                    "fact-comp-r9", "R9", "10k", {"1": "+3V3", "2": "BOOT"}
                )
            ],
        )
        context = make_context(observations, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "PATCH")
        self.assertEqual(
            proposal["oplist"]["ops"],
            [
                {
                    "op": "place_component",
                    "lib_id": "Device:R",
                    "designator": "R9",
                    "x_mil": 1000,
                    "y_mil": 2000,
                    "value": "10k",
                    "footprint": "Resistor_SMD:R_0603_1608Metric",
                },
                {"op": "add_net_label", "name": "+3V3", "at": "R9.1"},
                {"op": "add_net_label", "name": "BOOT", "at": "R9.2"},
            ],
        )

    def test_case_missing_en_cap_is_placed_with_pin_labels(self):
        observations = inject_fault(GOOD, fault("fault_missing_en_cap.json"))
        facts = complete_facts(
            component_targets=[
                component_target(
                    "fact-comp-c5", "C5", "1uF", {"1": "EN", "2": "GND"}, x_mil=3000
                )
            ],
        )
        context = make_context(observations, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "PATCH")
        ops = proposal["oplist"]["ops"]
        self.assertEqual(ops[0]["op"], "place_component")
        self.assertEqual(ops[0]["designator"], "C5")
        self.assertEqual(ops[0]["x_mil"], 3000)
        self.assertEqual(
            ops[1:],
            [
                {"op": "add_net_label", "name": "EN", "at": "C5.1"},
                {"op": "add_net_label", "name": "GND", "at": "C5.2"},
            ],
        )

    def test_case_missing_series_resistor_style(self):
        """案例 3 型：元件整体缺失（以 R7 为例构造删除型故障）。"""
        mutations = []
        for view in ("intent", "netlist", "pcb"):
            mutations.append({"op": "delete", "path": ["views", view, "pins", "R7.1"]})
            mutations.append({"op": "delete", "path": ["views", view, "pins", "R7.2"]})
            mutations.append({"op": "delete", "path": ["views", view, "components", "R7"]})
        observations = inject_fault(GOOD, {"mutations": mutations})
        facts = complete_facts(
            component_targets=[
                component_target(
                    "fact-comp-r7",
                    "R7",
                    "22R",
                    {"1": "USB_DP_CONN", "2": "USB_DP"},
                )
            ],
        )
        context = make_context(observations, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "PATCH")
        self.assertEqual(len(proposal["oplist"]["ops"]), 3)
        self.assertEqual(proposal["oplist"]["ops"][0]["designator"], "R7")
        self.assertEqual(proposal["oplist"]["ops"][0]["value"], "22R")

    # ------------------------------------------------------------------
    # 拒绝路径（fail-closed）
    # ------------------------------------------------------------------

    def test_insufficient_facts_status_refuses_like_governed_case(self):
        observations = inject_fault(GOOD, fault("fault_reversed_usb.json"))
        facts = complete_facts(
            facts_status="insufficient",
            facts_gaps=["gap-approved-values", "gap-uuid-bindings"],
        )
        context = make_context(observations, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertNotIn("oplist", proposal)
        refusal = proposal["refusal"]
        self.assertEqual(refusal["reason_code"], "PUBLIC_INPUT_INSUFFICIENT")
        self.assertEqual(
            refusal["missing_fact_ids"],
            ["gap-approved-values", "gap-uuid-bindings"],
        )
        self.assertTrue(refusal["required_human_decision"])

    def test_missing_deletion_fact_blocks_retarget(self):
        observations = inject_fault(GOOD, fault("fault_reversed_usb.json"))
        facts = complete_facts(
            pin_targets=[pin_target("fact-pin-14", "U1.14", "USB_DP")],
        )
        context = make_context(observations, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(
            proposal["refusal"]["reason_code"], "PUBLIC_INPUT_INSUFFICIENT"
        )
        self.assertEqual(
            proposal["refusal"]["missing_fact_ids"], ["deletion-U1-14"]
        )

    def test_wrong_existing_component_value_is_not_expressible(self):
        facts = complete_facts(
            component_targets=[
                component_target("fact-comp-r9", "R9", "47k", {"1": "+3V3", "2": "BOOT"})
            ],
        )
        context = make_context(GOOD, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(
            proposal["refusal"]["reason_code"], "NOT_EXPRESSION_IN_PUBLIC_OPS"
        )

    def test_protected_anchor_conflict_refuses(self):
        facts = complete_facts(
            pin_targets=[pin_target("fact-pin-prot", "U2.3", "GND")],
        )
        context = make_context(GOOD, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "PUBLIC_INPUT_CONFLICT")

    def test_cross_view_disagreement_refuses(self):
        observations = copy.deepcopy(GOOD)
        observations["views"]["pcb"]["pins"]["U1.14"]["net"] = "USB_DM"
        facts = complete_facts(
            pin_targets=[pin_target("fact-pin-14", "U1.14", "USB_DP")],
        )
        context = make_context(observations, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "OBSERVATION_CONFLICT")

    def test_already_satisfied_refuses_without_ops(self):
        facts = complete_facts(
            pin_targets=[pin_target("fact-pin-14", "U1.14", "USB_DP")],
        )
        context = make_context(GOOD, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertNotIn("oplist", proposal)
        self.assertEqual(proposal["refusal"]["reason_code"], "ALREADY_SATISFIED")

    def test_operation_limit_refuses(self):
        comps = [
            component_target(
                f"fact-comp-{index}",
                f"R{index}0",
                "10k",
                {"1": "A", "2": "B"},
            )
            for index in range(1, 6)
        ]
        context = make_context(GOOD, complete_facts(component_targets=comps))
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(
            proposal["refusal"]["reason_code"], "OPERATION_LIMIT_EXCEEDED"
        )

    def test_missing_observation_anchor_refuses(self):
        facts = complete_facts(
            pin_targets=[pin_target("fact-pin-x", "J9.1", "SOME_NET")],
        )
        context = make_context(GOOD, facts)
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(
            proposal["refusal"]["reason_code"], "PUBLIC_INPUT_INSUFFICIENT"
        )
        self.assertEqual(proposal["refusal"]["missing_fact_ids"], ["observation-J9-1"])

    def test_null_observation_refuses_insufficient(self):
        context = make_context(None, complete_facts())
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "ALREADY_SATISFIED")

    def test_facts_schema_mismatch_refuses_malformed(self):
        context = make_context(
            GOOD, complete_facts(facts_schema="aedl.public-facts.draft-0.1")
        )
        proposal = must_parse(build_proposal(context))
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "PUBLIC_INPUT_MALFORMED")

    def test_unknown_facts_field_refuses_malformed(self):
        # 带 golden 字样的键会先被 make_public_context 的 leak guard 拒绝，
        # 因此这里绕开 C1 直接改写已产出的 context dict，只测 D 自身 fail-closed。
        context = make_context(GOOD, complete_facts())
        context["public_facts"] = {
            **complete_facts(),
            "golden_hint": {"U1.14": "USB_DP"},
        }
        proposal = build_proposal(context)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "PUBLIC_INPUT_MALFORMED")

    # ------------------------------------------------------------------
    # 输入层校验（退出码 2 路径）
    # ------------------------------------------------------------------

    def test_load_context_rejects_missing_field(self):
        context = make_context(GOOD, complete_facts())
        del context["base_source_sha256"]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ctx.json"
            path.write_text(json.dumps(context), encoding="utf-8")
            with self.assertRaises(BaselineInputError):
                load_context(path)

    def test_load_context_rejects_bad_schema_version(self):
        context = make_context(GOOD, complete_facts())
        context["schema_version"] = 2
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ctx.json"
            path.write_text(json.dumps(context), encoding="utf-8")
            with self.assertRaises(BaselineInputError):
                load_context(path)

    def test_load_context_rejects_bom_and_duplicate_keys_and_floats(self):
        good = make_context(GOOD, complete_facts())
        with tempfile.TemporaryDirectory() as temp_dir:
            bom_path = Path(temp_dir) / "bom.json"
            bom_path.write_bytes(
                b"\xef\xbb\xbf" + json.dumps(good).encode("utf-8")
            )
            with self.assertRaises(BaselineInputError):
                load_context(bom_path)

            dup_path = Path(temp_dir) / "dup.json"
            dup_path.write_bytes(
                b'{"schema_version": 1, "schema_version": 1}'
            )
            with self.assertRaises(BaselineInputError):
                load_context(dup_path)

            float_context = copy.deepcopy(good)
            float_context["limits"] = {"ratio": 1.5}
            float_path = Path(temp_dir) / "float.json"
            float_path.write_text(json.dumps(float_context), encoding="utf-8")
            with self.assertRaises(BaselineInputError):
                load_context(float_path)

    def test_load_context_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(BaselineInputError):
                load_context(Path(temp_dir) / "missing.json")

    # ------------------------------------------------------------------
    # 确定性与 CLI
    # ------------------------------------------------------------------

    def test_deterministic_output(self):
        observations = inject_fault(GOOD, fault("fault_reversed_usb.json"))
        context = make_context(
            observations,
            complete_facts(
                pin_targets=[pin_target("fact-pin-14", "U1.14", "USB_DP")],
                deletion_targets=[deletion_target("fact-del-14", "wire-u1-14", "U1.14")],
            ),
        )
        self.assertEqual(render(build_proposal(context)), render(build_proposal(context)))

    def test_cli_end_to_end(self):
        observations = inject_fault(GOOD, fault("fault_floating_addr.json"))
        context = make_context(
            observations,
            complete_facts(pin_targets=[pin_target("fact-pin-gnd", "U2.2", "GND")]),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            ctx_path = Path(temp_dir) / "context.json"
            out_path = Path(temp_dir) / "proposal.json"
            ctx_path.write_text(json.dumps(context), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--context",
                    str(ctx_path),
                    "--out",
                    str(out_path),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            raw = out_path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            parsed = parse_proposal(raw)
            self.assertEqual(parsed.decision, "PATCH")

    def test_cli_rejects_malformed_input_with_exit_2(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ctx_path = Path(temp_dir) / "bad.json"
            ctx_path.write_text('{"schema_version": 9}', encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--context",
                    str(ctx_path),
                    "--out",
                    str(Path(temp_dir) / "out.json"),
                ],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid input", result.stderr)


if __name__ == "__main__":
    unittest.main()
