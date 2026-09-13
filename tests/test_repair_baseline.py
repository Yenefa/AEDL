"""AEDL Y4 arm-D baseline tests（v0.6.0，A-2′ prime：观测 + 公共合同 → 冻结 Proposal）。

与 v0.5 的本质区别（Owner 决策 D1 = "C"）：
- L2 事实文法（interpret_facts / FACT_KINDS）与 ObservationView 已退役：
  public_facts 不再承载修复推理（只保留"必须是数组"的形状守卫，以免类型不符
  把包级损坏误判成 exit 2）；
- 修复由移植自 r16 实跑产物（d_adapter_v3_candidate.py）的规则引擎从 netlist
  观测 + 公共合同推导。测试通过 build_proposal(package, contract=...) 注入
  **中性合成合同**（X1/X2/R5 等通用名、NA/NB/NC/ND 等通用网名），不复刻五个
  计分案例，也不写死任何案例级锚点→网名/UUID/坐标；
- 每一份输出（PATCH 与 REFUSE 都算）都喂真实 C1 parse_proposal 验证；
- 真实 runner 集成测试仍需要 PR #61 的 tools/y4_dry_runner.py，缺失时自动
  skip（原因注明），合入后自动启用。
"""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.repair_baseline import (
    CONTRACT_PATH,
    CONTRACT_SHA256,
    TOOL_VERSION,
    BaselineInputError,
    build_proposal,
    choose_slot,
    load_package,
    propose_bytes,
    render,
)
import tools.repair_baseline as repair_baseline
from tools.repair_pipeline import (
    canonical_json_bytes,
    hash_bytes,
    make_public_context,
    parse_proposal,
    public_context_digest,
)

# y4 runner（PR #61，分支 feat/gh56-y4-dry-harness）合入前 skip，合入后自动启用。
try:
    from tools.y4_dry_runner import (  # type: ignore
        EXPERIMENT_VERSION as RUNNER_EXPERIMENT_VERSION,
        build_package as runner_build_package,
        run_adapter as runner_run_adapter,
    )

    RUNNER_AVAILABLE = True
except ImportError:
    RUNNER_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "repair_baseline.py"
CONTRACT_PATH = ROOT / "gates" / "contracts" / "m2_schematic_contract_v1.json"

SHA_A = "a" * 64
SHA_B = "b" * 64

BUDGET = {
    "max_ops": 8,
    "max_request_bytes": 64 * 1024,
    "max_output_tokens": 200000,
    "timeout_ms": 600000,
}
HOST_CONTEXT = {
    "context_id": "ctx-y4-neutral-1",
    "target": "candidate/board.kicad_sch",
    "base_source_sha256": SHA_A,
    "limits": dict(BUDGET),
}
GRANTS = [
    {"x_mil": 1000, "y_mil": 2000},
    {"x_mil": 4000, "y_mil": 5000},
    {"x_mil": 7000, "y_mil": 8000},
]


# ---------------------------------------------------------------------------
# 中性合成 fixture（通用名；唯一几何：Device:R 的引脚在 (0, ±3.81)）
# ---------------------------------------------------------------------------

SOURCE_TEMPLATE = """(kicad_sch (version 20230121) (paper "A4")
  (lib_symbols
    (symbol "Device:R" (pin_numbers hide) (pin_names (offset 0))
      (property "Reference" "R" (at 2.032 0 90))
      (property "Value" "R" (at 0 0 90))
      (symbol "R_0_1"
        (rectangle (start -1.016 -2.54) (end 1.016 2.54))
      )
      (symbol "R_1_1"
        (pin passive line (at 0 3.81 270) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
        (pin passive line (at 0 -3.81 90) (length 1.27) (name "~" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
      )
    )
  )
  (symbol (lib_id "Device:R") (at 100 100 0) (unit 1)
    (uuid "11111111-1111-1111-1111-111111111111")
    (property "Reference" "X1" (at 102 100 0))
    (property "Value" "1k" (at 102 103 0))
    (property "Footprint" "Test:R_neutral" (at 0 0 0))
    (pin "1" (uuid "22222222-2222-2222-2222-222222222222"))
    (pin "2" (uuid "33333333-3333-3333-3333-333333333333"))
  )
  (label "NA" (at 100 103.81 0) (uuid "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa01"))
  (label "NA" (at 150 150 0) (uuid "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa02"))
  (label "NB" (at 160 160 0) (uuid "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa03"))
  (label "NC" (at 20 20 0) (uuid "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa04"))
  (label "ND" (at 24 24 0) (uuid "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa05"))
  (wire (pts (xy 150 150) (xy 160 160)) (stroke (width 0) (type default)) (uuid "44444444-4444-4444-4444-444444444444"))
{extra}
)
"""

SOURCE = SOURCE_TEMPLATE.format(extra="")

# 第二根端点带 NA/NB 的导线：制造"歧义导线匹配"的拒绝路径。
SOURCE_TWO_WIRES = SOURCE_TEMPLATE.format(
    extra='  (label "NA" (at 170 170 0) (uuid "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa06"))\n'
    '  (label "NB" (at 180 180 0) (uuid "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa07"))\n'
    '  (wire (pts (xy 170 170) (xy 180 180)) (stroke (width 0) (type default))'
    ' (uuid "55555555-5555-5555-5555-555555555555"))'
)

# 中性合成合同：只声明规则 id / severity / netlist 项，无任何案例级取值。
CONTRACT_PIN = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_PIN_NET",
            "severity": "critical",
            "checks": {"netlist": {"pins": {"X1.2": {"net": "NB"}}}},
        }
    ],
}
CONTRACT_MISSING = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_MISSING_PART",
            "severity": "major",
            "checks": {
                "netlist": {
                    "components": {"R21": {"value": "10k"}},
                    "pins": {"R21.1": {"net": "NA"}, "R21.2": {"net": "NB"}},
                }
            },
        }
    ],
}
CONTRACT_MISSING_LABELS = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_MISSING_LABELS",
            "severity": "major",
            "checks": {
                "netlist": {
                    "components": {"R21": {"value": "10k"}},
                    "pins": {"R21.1": {"net": "NC"}, "R21.2": {"net": "ND"}},
                }
            },
        }
    ],
}
CONTRACT_MISSING_ONE_LABEL = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_MISSING_ONE_LABEL",
            "severity": "minor",
            "checks": {
                "netlist": {
                    "components": {"R21": {"value": "10k"}},
                    "pins": {"R21.1": {"net": "NC"}, "R21.2": {"net": "NE"}},
                }
            },
        }
    ],
}
CONTRACT_TWO_MISSING = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_TWO_MISSING",
            "severity": "major",
            "checks": {
                "netlist": {
                    "components": {"R21": {"value": "10k"}, "R22": {"value": "10k"}},
                    "pins": {
                        "R21.1": {"net": "NA"}, "R21.2": {"net": "NB"},
                        "R22.1": {"net": "NA"}, "R22.2": {"net": "NB"},
                    },
                }
            },
        }
    ],
}
CONTRACT_DISCONNECT = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_DISCONNECT",
            "severity": "major",
            "checks": {"netlist": {"pins": {"X1.2": {"net": None}}}},
        }
    ],
}
CONTRACT_VALUE = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_VALUE",
            "severity": "major",
            "checks": {"netlist": {"components": {"X1": {"value": "22k"}}}},
        }
    ],
}
CONTRACT_UNSUPPORTED = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_UNSUPPORTED",
            "severity": "major",
            "checks": {"netlist": {"components": {"U9": {"value": "x"}}}},
        }
    ],
}
CONTRACT_SATISFIED = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_SATISFIED",
            "severity": "major",
            "checks": {"netlist": {"pins": {"X1.1": {"net": "NA"}}}},
        }
    ],
}
CONTRACT_TWO_PINS = {
    "schema_version": 1,
    "rules": [
        {
            "id": "NEUTRAL_TWO_PINS",
            "severity": "major",
            "checks": {
                "netlist": {"pins": {"X1.2": {"net": "NB"}, "X1.9": {"net": "NC"}}}
            },
        }
    ],
}


def netlist_observation(nets, components):
    return {
        "observation_type": "kicad_netlist_current.v1",
        "components": components,
        "nets": nets,
        "coverage": {
            "view": "schematic_netlist",
            "component_count": len(components),
            "net_count": len(nets),
        },
    }


def comp(ref, value="1k", footprint="Test:R_neutral"):
    return {"ref": ref, "value": value, "footprint": footprint, "lib": "Device:R", "part": "R"}


def net(name, code, nodes):
    return {"code": code, "name": name, "nodes": [{"ref": ref, "pin": pin} for ref, pin in nodes]}


# X1.1 在 NA 上，X2.1 在 NB 上，其余引脚悬空。
OBSERVATION = netlist_observation(
    [net("NA", "1", [("X1", "1")]), net("NB", "2", [("X2", "1")])],
    [comp("X1"), comp("X2")],
)

# X1.2 被错接到 NA（源码里 (100, 103.81) 上有名为 NA 的标签 = X1.2 的绝对位置）
OBSERVATION_WRONG_LABEL = netlist_observation(
    [net("NA", "1", [("X1", "1"), ("X1", "2")]), net("NB", "2", [("X2", "1")])],
    [comp("X1"), comp("X2")],
)

# 同前缀兄弟 R5 提供缺件 R21 的 footprint 证据。
OBSERVATION_WITH_SIBLING = netlist_observation(
    [net("NA", "1", [("X1", "1")]), net("NB", "2", [("X2", "1")])],
    [comp("X1"), comp("X2"), comp("R5", footprint="Test:R_neutral")],
)


def make_package(observation_data=OBSERVATION, facts=(), grants=None, limits=None, source=SOURCE):
    """真实 C1 context + y4-public.v3 封闭包形状（中性合成数据）。"""
    host = dict(HOST_CONTEXT)
    if limits is not None:
        host["limits"] = dict(limits)
    # 非法类型原样透传（类型不符的 REFUSE 语义正是要测 D 自身）；
    # 只有 list/tuple 才做列表化。
    facts_arg = list(facts) if isinstance(facts, (list, tuple)) else facts
    context = make_public_context(host, observation_data, facts_arg)
    return {
        "schema_version": "y4-public.v3",
        "experiment_version": "test-experiment-neutral-1",
        "case_public_id": "Y4-NEUTRAL-001",
        "source_utf8": source,
        "observation_binding": {
            "source_sha256": SHA_A,
            "observation_sha256": SHA_B,
            "producer_id": "test-producer-v1",
        },
        "public_context": context,
        "public_context_sha256": public_context_digest(context),
        "budget": dict(host["limits"]),
        "instruction": "Return exactly one JSON Proposal.",
        "exposure_fields": ["session_id", "fresh_session"],
        "placement_grants": GRANTS if grants is None else grants,
    }


def must_parse(proposal):
    """D 的每份产物（PATCH/REFUSE）都必须过真实 C1 parse_proposal。"""
    parse_proposal(render(proposal))
    return proposal


def run_baseline(package, contract=None):
    return must_parse(build_proposal(package, contract=contract))


class HeaderMixin:
    def assert_header_bound(self, proposal, package):
        context = package["public_context"]
        for key in ("schema_version", "context_id", "target", "base_source_sha256"):
            self.assertEqual(proposal[key], context[key], key)


class SlotSelectionSeamTests(unittest.TestCase):
    """取槽是**实现细节**（D2 = A）：所有槽位选择只经过 choose_slot(grants, anchor)。"""

    def test_without_anchor_takes_first_granted_slot(self):
        self.assertEqual(choose_slot(GRANTS), GRANTS[0])

    def test_with_anchor_takes_nearest_granted_slot(self):
        # (22, 22) mm 距 grants[0] 最近；(155, 155) mm 距 grants[2] 最近。
        self.assertEqual(choose_slot(GRANTS, (22.0, 22.0)), GRANTS[0])
        self.assertEqual(choose_slot(GRANTS, (155.0, 155.0)), GRANTS[2])
        for anchor in ((22.0, 22.0), (155.0, 155.0), (0.0, 0.0)):
            chosen = choose_slot(GRANTS, anchor)
            self.assertIn((chosen["x_mil"], chosen["y_mil"]),
                          {(g["x_mil"], g["y_mil"]) for g in GRANTS})


class ContractPinTests(unittest.TestCase):
    """公共合同的内容 pin：仓库文件必须等于 pin；漂移时 fail-closed 成合法 REFUSE。"""

    def test_pinned_hash_matches_the_repo_contract(self):
        raw = CONTRACT_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), CONTRACT_SHA256)

    def test_contract_drift_refuses_legally_not_exit_2(self):
        package = make_package()
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp) / "m2_schematic_contract_v1.json"
            payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
            payload["rules"][0]["severity"] = "minor"  # 任何字节改动都算漂移
            tampered.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            original = repair_baseline.CONTRACT_PATH
            repair_baseline.CONTRACT_PATH = tampered
            try:
                proposal = build_proposal(package)  # 不注入合同 -> 走文件路径与 pin 校验
            finally:
                repair_baseline.CONTRACT_PATH = original
        parse_proposal(render(proposal))  # 仍是合法 C1 Proposal（不是 exit 2）
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "CONTRACT_DRIFT")


class DerivationTests(HeaderMixin, unittest.TestCase):
    """移植引擎的中性合成推导覆盖（注入合同，不走计分案例）。"""

    maxDiff = None

    def test_floating_pin_gets_net_label(self):
        package = make_package()
        proposal = run_baseline(package, CONTRACT_PIN)
        self.assertEqual(proposal["decision"], "PATCH")
        self.assertEqual(
            proposal["oplist"]["ops"],
            [{"op": "add_net_label", "name": "NB", "at": "X1.2"}],
        )
        self.assert_header_bound(proposal, package)
        entry = proposal["diagnosis"][0]
        self.assertEqual(entry["rule_id"], "NEUTRAL_PIN_NET")
        self.assertEqual(entry["requirement_level"], "MANDATORY")
        self.assertEqual(entry["fact_ids"], [])
        self.assertIn("contract", entry["rationale"])
        self.assertIn("X1.2", entry["observed"])

    def test_wrong_label_is_deleted_then_relabelled(self):
        proposal = run_baseline(make_package(observation_data=OBSERVATION_WRONG_LABEL),
                                CONTRACT_PIN)
        self.assertEqual(proposal["decision"], "PATCH")
        self.assertEqual(
            proposal["oplist"]["ops"],
            [
                {"op": "delete_object", "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaa01"},
                {"op": "add_net_label", "name": "NB", "at": "X1.2"},
            ],
        )
        self.assertEqual(proposal["diagnosis"][0]["requirement_level"], "MANDATORY")

    def test_missing_component_placed_on_granted_slot(self):
        proposal = run_baseline(make_package(observation_data=OBSERVATION_WITH_SIBLING),
                                CONTRACT_MISSING)
        self.assertEqual(proposal["decision"], "PATCH")
        self.assertEqual(
            proposal["oplist"]["ops"],
            [
                {"op": "delete_object", "uuid": "44444444-4444-4444-4444-444444444444"},
                {"op": "place_component", "lib_id": "Device:R", "designator": "R21",
                 "x_mil": 7000, "y_mil": 8000, "value": "10k",
                 "footprint": "Test:R_neutral"},
                {"op": "add_net_label", "name": "NA", "at": "R21.1"},
                {"op": "add_net_label", "name": "NB", "at": "R21.2"},
            ],
        )
        entry = proposal["diagnosis"][0]
        self.assertEqual(entry["rule_id"], "NEUTRAL_MISSING_PART")
        self.assertEqual(entry["requirement_level"], "RECOMMENDED")
        self.assertEqual(entry["fact_ids"], [])

    def test_missing_component_label_midpoint_anchor(self):
        proposal = run_baseline(make_package(observation_data=OBSERVATION_WITH_SIBLING),
                                CONTRACT_MISSING_LABELS)
        ops = proposal["oplist"]["ops"]
        self.assertEqual([op["op"] for op in ops],
                         ["place_component", "add_net_label", "add_net_label"])
        self.assertEqual((ops[0]["x_mil"], ops[0]["y_mil"]), (1000, 2000))

    def test_missing_component_single_label_anchor_offsets_down(self):
        package = make_package(observation_data=OBSERVATION_WITH_SIBLING)
        proposal = run_baseline(package, CONTRACT_MISSING_ONE_LABEL)
        ops = proposal["oplist"]["ops"]
        self.assertEqual(ops[0]["op"], "place_component")
        # 只有 NC 有标签位置 (20, 20) → 锚点 (20, 25.08) → 最近槽位仍是 grants[0]
        self.assertEqual((ops[0]["x_mil"], ops[0]["y_mil"]), (1000, 2000))
        self.assertEqual(proposal["diagnosis"][0]["requirement_level"], "UNKNOWN")

    def test_ambiguous_wire_match_refuses(self):
        proposal = run_baseline(
            make_package(observation_data=OBSERVATION_WITH_SIBLING, source=SOURCE_TWO_WIRES),
            CONTRACT_MISSING,
        )
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "NO_DERIVABLE_PLAN")
        self.assertIn("ambiguous wire match for R21", proposal["refusal"]["explanation"])

    def test_missing_sibling_footprint_refuses(self):
        proposal = run_baseline(make_package(), CONTRACT_MISSING)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "NO_DERIVABLE_PLAN")
        self.assertIn("insufficient sibling/pin evidence for R21",
                      proposal["refusal"]["explanation"])

    def test_unsupported_missing_prefix_refuses(self):
        proposal = run_baseline(make_package(), CONTRACT_UNSUPPORTED)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertIn("unsupported lib for U9", proposal["refusal"]["explanation"])

    def test_disconnection_not_expressible_refuses(self):
        proposal = run_baseline(make_package(observation_data=OBSERVATION_WRONG_LABEL),
                                CONTRACT_DISCONNECT)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "NO_DERIVABLE_PLAN")
        self.assertIn("cannot express disconnection for X1.2",
                      proposal["refusal"]["explanation"])

    def test_wrong_existing_value_not_expressible_refuses(self):
        proposal = run_baseline(make_package(), CONTRACT_VALUE)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertIn("no C1 value-update operation for X1",
                      proposal["refusal"]["explanation"])

    def test_no_mismatch_refuses_without_derivable_plan(self):
        proposal = run_baseline(make_package(), CONTRACT_SATISFIED)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "NO_DERIVABLE_PLAN")
        self.assertEqual(proposal["refusal"]["explanation"],
                         "no public-derivable repair plan")
        self.assertEqual(proposal["refusal"]["missing_fact_ids"], [])
        self.assertTrue(proposal["refusal"]["required_human_decision"])

    def test_default_contract_is_resolved_relative_to_module(self):
        """不注入合同时读取仓库内公共合同（该合同不含中性 refs → 合法 REFUSE）。"""
        self.assertTrue(CONTRACT_PATH.is_file())
        proposal = run_baseline(make_package())
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "NO_DERIVABLE_PLAN")

    def test_render_has_no_trailing_newline(self):
        self.assertEqual(TOOL_VERSION, "0.6.0")
        raw = render(run_baseline(make_package(), CONTRACT_PIN))
        self.assertTrue(raw.startswith(b"{"))
        self.assertFalse(raw.endswith(b"\n"))
        self.assertNotIn(b'": ', raw)
        self.assertNotIn(b'", "', raw)


class BudgetAndGuardTests(HeaderMixin, unittest.TestCase):
    maxDiff = None

    def test_max_ops_read_from_limits_not_hardcoded(self):
        package = make_package(limits={**BUDGET, "max_ops": 1})
        over = run_baseline(package, CONTRACT_TWO_PINS)
        self.assertEqual(over["decision"], "REFUSE")
        self.assertEqual(over["refusal"]["reason_code"], "OPERATION_LIMIT_EXCEEDED")
        exact = run_baseline(make_package(limits={**BUDGET, "max_ops": 2}), CONTRACT_TWO_PINS)
        self.assertEqual(exact["decision"], "PATCH")
        self.assertEqual(len(exact["oplist"]["ops"]), 2)

    def test_grants_exhausted_refuses(self):
        package = make_package(observation_data=OBSERVATION_WITH_SIBLING,
                               grants=[GRANTS[0]])
        proposal = run_baseline(package, CONTRACT_TWO_MISSING)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "GRANTS_EXHAUSTED")

    def test_diagnosis_is_capped_to_frozen_limit(self):
        """诊断条目封顶 16：即使注入合同触发更多规则，产物仍是合法 C1 Proposal。"""
        rules = [
            {"id": "NEUTRAL_%02d" % index, "severity": "major",
             "checks": {"netlist": {"pins": {"X1.%d" % index: {"net": "NB"}}}}}
            for index in range(2, 22)
        ]
        proposal = run_baseline(make_package(), {"schema_version": 1, "rules": rules})
        self.assertLessEqual(len(proposal["diagnosis"]), 16)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "OPERATION_LIMIT_EXCEEDED")

    def test_pin_in_two_nets_conflicts(self):
        conflicting = netlist_observation(
            [
                net("NA", "1", [("X1", "1")]),
                net("NB", "2", [("X1", "1")]),
            ],
            [comp("X1")],
        )
        proposal = run_baseline(make_package(observation_data=conflicting), CONTRACT_PIN)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "OBSERVATION_CONFLICT")

    def test_wrong_observation_type_refuses(self):
        package = make_package(observation_data={"observation_type": "three_view_draft.v1"})
        proposal = run_baseline(package, CONTRACT_PIN)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "PUBLIC_INPUT_MALFORMED")

    def test_non_array_facts_refuses_legally_not_exit_2(self):
        """D1=C 下 facts 不再承载推理，但类型不符仍是合法 REFUSE（不是 exit 2）。"""
        for bad_facts in ({"facts": []}, "none supplied", 17):
            package = make_package(facts=bad_facts)
            proposal = run_baseline(package, CONTRACT_PIN)
            self.assertEqual(proposal["decision"], "REFUSE")
            self.assertEqual(proposal["refusal"]["reason_code"], "PUBLIC_INPUT_MALFORMED")

    def test_invalid_grants_refuse_legally_not_exit_2(self):
        for bad_grants in ([], [{"x_mil": 1}], [{"x_mil": 1, "y_mil": 2, "z": 3}],
                           GRANTS + [GRANTS[0]]):
            package = make_package(grants=bad_grants)
            proposal = run_baseline(package, CONTRACT_PIN)
            self.assertEqual(proposal["decision"], "REFUSE")
            self.assertEqual(proposal["refusal"]["reason_code"], "PUBLIC_INPUT_MALFORMED")


class PackageLevelTests(unittest.TestCase):
    """exit 2 仅保留给包文件级/包级结构损坏。"""

    def write(self, temp_dir, name, raw):
        path = Path(temp_dir) / name
        path.write_bytes(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
        return path

    def assert_invalid(self, raw):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(BaselineInputError):
                load_package(self.write(temp_dir, "pkg.json", raw))

    def test_rejects_non_json_bom_and_duplicate_keys(self):
        self.assert_invalid("{not json")
        self.assert_invalid(b"\xef\xbb\xbf" + json.dumps(make_package()).encode("utf-8"))
        self.assert_invalid(b'{"schema_version": "y4-public.v3", "schema_version": "y4-public.v3"}')

    def test_rejects_wrong_or_missing_package_schema_version(self):
        package = make_package()
        package["schema_version"] = "y4-public.v2"
        self.assert_invalid(json.dumps(package))
        package["schema_version"] = 3
        self.assert_invalid(json.dumps(package))

    def test_rejects_missing_or_unknown_package_field(self):
        package = make_package()
        del package["placement_grants"]
        self.assert_invalid(json.dumps(package))
        package = make_package()
        package["extra"] = 1
        self.assert_invalid(json.dumps(package))

    def test_rejects_bad_context_fields(self):
        for mutate in (
            lambda ctx: ctx.update(context_id="bad id!"),
            lambda ctx: ctx.update(base_source_sha256="nothex"),
            lambda ctx: ctx.update(target="../escape.kicad_sch"),
            lambda ctx: del_key(ctx, "public_facts"),
            lambda ctx: ctx.update(generic_op_schema=None),
        ):
            package = make_package()
            mutate(package["public_context"])
            self.assert_invalid(json.dumps(package))

    def test_rejects_bad_limits(self):
        for bad in (
            {**BUDGET, "max_ops": 9},
            {**BUDGET, "timeout_ms": 0},
            {key: value for key, value in BUDGET.items() if key != "max_output_tokens"},
            {**BUDGET, "unexpected": 1},
        ):
            self.assert_invalid(json.dumps(make_package(limits=bad)))

    def test_missing_package_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(BaselineInputError):
                load_package(Path(temp_dir) / "missing.json")


def del_key(mapping, key):
    del mapping[key]
    return mapping


# ---------------------------------------------------------------------------
# 公共合同驱动的端到端（real contract：公共领域知识，不含案例数据）
# ---------------------------------------------------------------------------


def real_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def contract_satisfied_observation(contract, drop_pin=None, drop_component=None):
    """按公共合同的 netlist 期望构造"全部满足"的观测，再注入单一缺口。

    完全由合同内容生成：不写死任何 ref/网名/坐标。
    """
    components = {}
    nets = {}

    def add_component(ref, value):
        components.setdefault(
            ref,
            {"ref": ref, "value": value, "footprint": "Test:R_neutral",
             "lib": "Device:R", "part": "R"},
        )

    for rule in contract["rules"]:
        checks = rule.get("checks", {}).get("netlist", {})
        for ref, expected in checks.get("components", {}).items():
            add_component(ref, expected.get("value"))
        for key, expected in checks.get("pins", {}).items():
            ref, pin = key.split(".", 1)
            add_component(ref, "")
            if drop_component is not None and ref == drop_component:
                continue
            net_name = expected.get("net")
            if net_name is not None and key != drop_pin:
                nets.setdefault(net_name, []).append((ref, pin))
    if drop_component is not None:
        components.pop(drop_component, None)
    net_list = [net(name, str(index + 1), nodes)
                for index, (name, nodes) in enumerate(sorted(nets.items()))]
    return netlist_observation(net_list, [components[ref] for ref in sorted(components)])


def first_expected_pin(contract):
    for rule in contract["rules"]:
        for key, expected in rule.get("checks", {}).get("netlist", {}).get("pins", {}).items():
            if expected.get("net") is not None:
                return key
    raise AssertionError("real contract has no connected pin expectation")


class DeterminismAndCliTests(unittest.TestCase):
    maxDiff = None

    def test_deterministic_output_and_adapter_bytes(self):
        package = make_package()
        first = build_proposal(package, contract=CONTRACT_PIN)
        self.assertEqual(render(first), render(build_proposal(package, contract=CONTRACT_PIN)))
        package_bytes = json.dumps(package, ensure_ascii=False, sort_keys=True).encode("utf-8")
        # adapter 路径（propose_bytes）走仓库内公共合同，同样必须字节确定。
        self.assertEqual(propose_bytes(package_bytes), render(build_proposal(package)))
        self.assertEqual(propose_bytes(package_bytes), propose_bytes(package_bytes))

    def test_cli_end_to_end_patch_with_real_contract(self):
        contract = real_contract()
        observation = contract_satisfied_observation(
            contract, drop_pin=first_expected_pin(contract)
        )
        package = make_package(observation_data=observation)
        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = Path(temp_dir) / "package.json"
            package_path.write_bytes(json.dumps(package).encode("utf-8"))
            out_path = Path(temp_dir) / "proposal.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--package", str(package_path), "--out", str(out_path)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            raw = out_path.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertFalse(raw.endswith(b"\n"))
            parsed = parse_proposal(raw)
            self.assertEqual(parsed.decision, "PATCH")
            self.assertEqual(len(parsed.ops), 1)
            self.assertEqual(parsed.ops[0]["op"], "add_net_label")

    def test_cli_end_to_end_refuse_exits_zero(self):
        package = make_package(facts=[])
        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = Path(temp_dir) / "package.json"
            package_path.write_bytes(json.dumps(package).encode("utf-8"))
            out_path = Path(temp_dir) / "proposal.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--package", str(package_path), "--out", str(out_path)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            parsed = parse_proposal(out_path.read_bytes())
            self.assertEqual(parsed.decision, "REFUSE")
            self.assertEqual(parsed.refusal["reason_code"], "NO_DERIVABLE_PLAN")

    def test_cli_rejects_broken_package_with_exit_2(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = Path(temp_dir) / "broken.json"
            package_path.write_text('{"schema_version": 9}', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--package", str(package_path), "--out", str(Path(temp_dir) / "out.json")],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid package", result.stderr)


def runner_inputs(observation_data, facts, grants=GRANTS, max_ops=8, source=SOURCE):
    """真实 runner build_package 所需的中性合成公共输入。

    case_public_id 必须取自 runner 的允许集合（`Y4-001..005`，见
    `tools/y4_dry_runner.py::build_package`）——这是 runner 的**命名空间要求**，
    不是案例级映射：这里喂进去的观测仍是合成的（合同满足态去掉一个元件）。
    """
    return {
        "experiment_version": RUNNER_EXPERIMENT_VERSION,
        "case_public_id": "Y4-001",
        "context_id": "ctx-y4-neutral-runner-1",
        "target": "candidate/board.kicad_sch",
        "source_utf8": source,
        "observation_binding": {
            "source_sha256": hash_bytes(source.encode("utf-8")),
            "observation_sha256": hash_bytes(canonical_json_bytes(observation_data)),
            "producer_id": "test-producer-v1",
        },
        "current_observation": observation_data,
        "public_facts": list(facts),
        "budget": {**BUDGET, "max_ops": max_ops},
        "placement_grants": list(grants),
    }


RUNNER_META = {
    "run_id": "run-y4-neutral-1",
    "arm": "D",
    "repetition": 1,
    "attempt": 1,
    "model_or_script_id": "tools/repair_baseline.py@" + TOOL_VERSION,
    "settings": {"script": "tools/repair_baseline.py", "version": TOOL_VERSION},
    "exposure": {
        "session_id": "session-y4-neutral-1",
        "fresh_session": True,
        "input_scope": "PUBLIC_PACKAGE_ONLY",
        "prior_case_exposure": "NO",
        "author_exposure": "NO",
        "declaration": "Synthetic neutral integration input; no scored case data involved.",
    },
}


@unittest.skipUnless(
    RUNNER_AVAILABLE,
    "y4 runner (tools.y4_dry_runner, PR #61) not on this branch yet; "
    "these tests auto-enable once PR #61 merges",
)
class RunnerIntegrationTests(unittest.TestCase):
    """真实冻结包端到端：runner freeze → D adapter → collect_result 绑定校验。"""

    maxDiff = None

    def freeze(self, inputs):
        package_raw = runner_build_package(inputs)
        return package_raw, hash_bytes(package_raw)

    def run_adapter(self, package_raw, package_sha):
        record_raw = runner_run_adapter(package_raw, package_sha, RUNNER_META, propose_bytes)
        return json.loads(record_raw)

    def test_real_package_patch_end_to_end(self):
        contract = real_contract()
        observation = contract_satisfied_observation(contract, drop_component="R7")
        inputs = runner_inputs(observation, [])
        package_raw, package_sha = self.freeze(inputs)
        record = self.run_adapter(package_raw, package_sha)
        self.assertEqual(record["record_status"], "RECORDED")
        self.assertEqual(record["proposal_parse_status"], "PASS")
        self.assertEqual(record["binding_status"], "PASS")
        self.assertEqual(record["budget_status"], "PASS")
        proposal = record["proposal"]
        self.assertEqual(proposal["decision"], "PATCH")
        granted = {(g["x_mil"], g["y_mil"]) for g in inputs["placement_grants"]}
        for op in proposal["oplist"]["ops"]:
            if op["op"] == "place_component":
                self.assertIn((op["x_mil"], op["y_mil"]), granted)

    def test_real_package_refuse_end_to_end(self):
        inputs = runner_inputs(OBSERVATION, [])
        package_raw, package_sha = self.freeze(inputs)
        record = self.run_adapter(package_raw, package_sha)
        self.assertEqual(record["record_status"], "RECORDED")
        self.assertEqual(record["proposal_parse_status"], "PASS")
        self.assertEqual(record["binding_status"], "PASS")
        proposal = record["proposal"]
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertEqual(proposal["refusal"]["reason_code"], "NO_DERIVABLE_PLAN")
        self.assertEqual(proposal["refusal"]["missing_fact_ids"], [])

    def test_real_package_cli_end_to_end(self):
        contract = real_contract()
        observation = contract_satisfied_observation(contract, drop_component="R7")
        inputs = runner_inputs(observation, [])
        package_raw, _ = self.freeze(inputs)
        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = Path(temp_dir) / "package.json"
            package_path.write_bytes(package_raw)
            out_path = Path(temp_dir) / "proposal.json"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--package", str(package_path), "--out", str(out_path)],
                capture_output=True,
                text=True,
                cwd=str(ROOT),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            parsed = parse_proposal(out_path.read_bytes())
            self.assertEqual(parsed.decision, "PATCH")
            self.assertEqual(parsed.context_id, "ctx-y4-neutral-runner-1")


if __name__ == "__main__":
    unittest.main()
