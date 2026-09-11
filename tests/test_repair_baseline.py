"""AEDL Y4 arm-D baseline tests（v0.5，真实 y4-public.v3 包 → 冻结 Proposal）。

与 v0.4 的本质区别（回应 PR #60 第二轮 review）：
- 输入一律是完整的 y4-public.v3 形状包：public_context 经真实 C1
  make_public_context 构造（含 leak guard），facts 是**数组**，观测是
  kicad_netlist_current.v1（components/nets/nodes），坐标只从
  placement_grants 取，max_ops 从 context.limits 读；
- 每一份输出（PATCH 与 REFUSE 都算）都喂真实 C1 parse_proposal 验证；
- 数据全部为**中性合成**（X1/X9、NA/NB 等通用名），不复刻五个计分案例，
  也不写死任何锚点→网名/UUID/坐标的案例级映射；
- 真实 runner 集成测试（freeze → adapter → collect_result）：y4 runner 在
  PR #61 分支，合入后 import 成功即自动启用（此前显式 skip，原因注明）。
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.repair_baseline import (
    TOOL_VERSION,
    BaselineInputError,
    build_proposal,
    load_package,
    propose_bytes,
    render,
)
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


def comp(ref, value="1k"):
    return {"ref": ref, "value": value, "footprint": "F", "lib": "Device:R", "part": "R"}


def net(name, code, nodes):
    return {"code": code, "name": name, "nodes": [{"ref": ref, "pin": pin} for ref, pin in nodes]}


# 中性合成观测：X1.1 在 NA 上，X2.1 在 NB 上，其余引脚悬空。
OBSERVATION = netlist_observation(
    [net("NA", "1", [("X1", "1")]), net("NB", "2", [("X2", "1")])],
    [comp("X1"), comp("X2")],
)


def connect(fid, anchor, net_name):
    return {"id": fid, "kind": "connect_pin", "anchor": anchor, "net": net_name}


def deletion(fid, uuid, anchor):
    return {"id": fid, "kind": "delete_object", "uuid": uuid, "anchor": anchor}


def place(fid, designator, value="10k", pin_nets=None):
    return {
        "id": fid,
        "kind": "place_component",
        "designator": designator,
        "lib_id": "Device:R",
        "value": value,
        "footprint": "Resistor_SMD:R_0603_1608Metric",
        "pin_nets": pin_nets or {"1": "NA", "2": "NB"},
    }


def make_package(observation_data=OBSERVATION, facts=(), grants=None, limits=None):
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
        "case_public_id": "Y4-001",
        "source_utf8": "(kicad_sch (version 20230121))",
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


def run_baseline(package):
    return must_parse(build_proposal(package))


class HeaderMixin:
    def assert_header_bound(self, proposal, package):
        context = package["public_context"]
        for key in ("schema_version", "context_id", "target", "base_source_sha256"):
            self.assertEqual(proposal[key], context[key], key)


class PatchPathTests(HeaderMixin, unittest.TestCase):
    maxDiff = None

    def test_floating_pin_gets_net_label(self):
        package = make_package(facts=[connect("fct-conn-1", "X1.2", "NB")])
        proposal = run_baseline(package)
        self.assertEqual(proposal["decision"], "PATCH")
        self.assertEqual(
            proposal["oplist"]["ops"],
            [{"op": "add_net_label", "name": "NB", "at": "X1.2"}],
        )
        self.assert_header_bound(proposal, package)
        cited = {fid for entry in proposal["diagnosis"] for fid in entry["fact_ids"]}
        self.assertEqual(cited, {"fct-conn-1"})

    def test_retarget_deletes_then_relabels(self):
        package = make_package(
            facts=[
                deletion("fct-del-1", "obj-uuid-1", "X1.1"),
                connect("fct-conn-1", "X1.1", "NB"),
            ]
        )
        proposal = run_baseline(package)
        self.assertEqual(proposal["decision"], "PATCH")
        self.assertEqual(
            proposal["oplist"]["ops"],
            [
                {"op": "delete_object", "uuid": "obj-uuid-1"},
                {"op": "add_net_label", "name": "NB", "at": "X1.1"},
            ],
        )
        cited = {fid for entry in proposal["diagnosis"] for fid in entry["fact_ids"]}
        self.assertEqual(cited, {"fct-del-1", "fct-conn-1"})

    def test_place_component_takes_grant_slots_in_order(self):
        package = make_package(facts=[place("fct-place-1", "X9"), place("fct-place-2", "X8")])
        proposal = run_baseline(package)
        self.assertEqual(proposal["decision"], "PATCH")
        ops = proposal["oplist"]["ops"]
        self.assertEqual(ops[0]["op"], "place_component")
        self.assertEqual(ops[0]["designator"], "X9")
        self.assertEqual(ops[0]["x_mil"], GRANTS[0]["x_mil"])
        self.assertEqual(ops[0]["y_mil"], GRANTS[0]["y_mil"])
        self.assertEqual(
            ops[1:3],
            [
                {"op": "add_net_label", "name": "NA", "at": "X9.1"},
                {"op": "add_net_label", "name": "NB", "at": "X9.2"},
            ],
        )
        self.assertEqual(ops[3]["designator"], "X8")
        self.assertEqual(
            (ops[3]["x_mil"], ops[3]["y_mil"]),
            (GRANTS[1]["x_mil"], GRANTS[1]["y_mil"]),
        )

    def test_max_ops_read_from_limits_not_hardcoded(self):
        facts = [place("fct-place-1", "X9")]
        over = run_baseline(make_package(facts=facts, limits={**BUDGET, "max_ops": 2}))
        self.assertEqual(over["decision"], "REFUSE")
        self.assertEqual(over["refusal"]["reason_code"], "OPERATION_LIMIT_EXCEEDED")
        exact = run_baseline(make_package(facts=facts, limits={**BUDGET, "max_ops": 3}))
        self.assertEqual(exact["decision"], "PATCH")
        self.assertEqual(len(exact["oplist"]["ops"]), 3)


class RefusePathTests(HeaderMixin, unittest.TestCase):
    maxDiff = None

    def assert_refuse(self, package, reason_code, missing=None):
        proposal = run_baseline(package)
        self.assertEqual(proposal["decision"], "REFUSE")
        self.assertNotIn("oplist", proposal)
        refusal = proposal["refusal"]
        self.assertEqual(refusal["reason_code"], reason_code)
        if missing is not None:
            self.assertEqual(refusal["missing_fact_ids"], missing)
        self.assertTrue(refusal["required_human_decision"])
        return proposal

    def test_empty_facts_array_refuses(self):
        self.assert_refuse(
            make_package(facts=[]),
            "PUBLIC_INPUT_INSUFFICIENT",
            ["public-facts"],
        )

    def test_non_array_facts_refuse_legally_not_exit_2(self):
        """第二轮 review 实测的 exit 2 场景：类型不符也必须产出合法 REFUSE。"""
        for bad_facts in ({"facts": []}, "none supplied", 17):
            package = make_package(facts=bad_facts)
            self.assert_refuse(package, "PUBLIC_INPUT_MALFORMED")

    def test_uninterpretable_facts_refuse_with_ids(self):
        facts = [
            connect("fct-conn-1", "X1.2", "NB"),
            {"id": "fct-odd-1", "kind": "annotate_value", "anchor": "X1.1", "value": "1k"},
            "prose-garbage",
        ]
        self.assert_refuse(
            make_package(facts=facts),
            "UNINTERPRETABLE_FACTS",
            ["fact-2", "fct-odd-1"],
        )

    def test_malformed_fact_shape_refuses(self):
        package = make_package(facts=[{"id": "fct-conn-1", "kind": "connect_pin", "anchor": "X1.2"}])
        self.assert_refuse(package, "PUBLIC_INPUT_MALFORMED")

    def test_unknown_anchor_component_refuses(self):
        self.assert_refuse(
            make_package(facts=[connect("fct-conn-1", "X9.1", "NB")]),
            "PUBLIC_INPUT_INSUFFICIENT",
            ["observation-X9-1"],
        )

    def test_retarget_without_deletion_fact_refuses(self):
        self.assert_refuse(
            make_package(facts=[connect("fct-conn-1", "X1.1", "NB")]),
            "PUBLIC_INPUT_INSUFFICIENT",
            ["delete-X1-1"],
        )

    def test_satisfied_pin_refuses_without_ops(self):
        self.assert_refuse(
            make_package(facts=[connect("fct-conn-1", "X1.1", "NA")]),
            "ALREADY_SATISFIED",
            [],
        )

    def test_satisfied_pin_with_deletion_fact_conflicts(self):
        self.assert_refuse(
            make_package(
                facts=[deletion("fct-del-1", "obj-uuid-1", "X1.1"), connect("fct-conn-1", "X1.1", "NA")]
            ),
            "PUBLIC_INPUT_CONFLICT",
        )

    def test_floating_pin_with_deletion_fact_conflicts(self):
        self.assert_refuse(
            make_package(
                facts=[deletion("fct-del-1", "obj-uuid-1", "X1.2"), connect("fct-conn-1", "X1.2", "NB")]
            ),
            "PUBLIC_INPUT_CONFLICT",
        )

    def test_orphan_deletion_refuses(self):
        self.assert_refuse(
            make_package(facts=[deletion("fct-del-1", "obj-uuid-1", "X1.1")]),
            "PUBLIC_INPUT_INSUFFICIENT",
            ["connect-X1-1"],
        )

    def test_duplicate_connect_anchor_conflicts(self):
        self.assert_refuse(
            make_package(
                facts=[connect("fct-conn-1", "X1.2", "NB"), connect("fct-conn-2", "X1.2", "NA")]
            ),
            "PUBLIC_INPUT_CONFLICT",
        )

    def test_duplicate_place_designator_conflicts(self):
        self.assert_refuse(
            make_package(facts=[place("fct-place-1", "X9"), place("fct-place-2", "X9")]),
            "PUBLIC_INPUT_CONFLICT",
        )

    def test_wrong_existing_value_not_expressible(self):
        self.assert_refuse(
            make_package(facts=[place("fct-place-1", "X1", value="47k")]),
            "NOT_EXPRESSION_IN_PUBLIC_OPS",
        )

    def test_pin_in_two_nets_refuses(self):
        conflicting = netlist_observation(
            [
                net("NA", "1", [("X1", "1")]),
                net("NB", "2", [("X1", "1")]),
            ],
            [comp("X1")],
        )
        self.assert_refuse(
            make_package(observation_data=conflicting, facts=[connect("fct-conn-1", "X1.1", "NA")]),
            "OBSERVATION_CONFLICT",
        )

    def test_wrong_observation_type_refuses(self):
        package = make_package(
            observation_data={"observation_type": "three_view_draft.v1", "views": {}},
            facts=[connect("fct-conn-1", "X1.2", "NB")],
        )
        self.assert_refuse(package, "PUBLIC_INPUT_MALFORMED")

    def test_grants_exhausted_refuses(self):
        package = make_package(
            facts=[place("fct-place-1", "X9"), place("fct-place-2", "X8")],
            grants=[GRANTS[0]],
        )
        self.assert_refuse(package, "PLACEMENT_CAPACITY_EXHAUSTED")

    def test_invalid_grants_refuse_legally_not_exit_2(self):
        for bad_grants in ([], [{"x_mil": 1}], [{"x_mil": 1, "y_mil": 2, "z": 3}], GRANTS + [GRANTS[0]]):
            package = make_package(facts=[place("fct-place-1", "X9")], grants=bad_grants)
            self.assert_refuse(package, "PUBLIC_INPUT_MALFORMED")


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


class DeterminismAndCliTests(unittest.TestCase):
    maxDiff = None

    def test_deterministic_output_and_adapter_bytes(self):
        package = make_package(facts=[connect("fct-conn-1", "X1.2", "NB")])
        first = build_proposal(package)
        self.assertEqual(render(first), render(build_proposal(package)))
        package_bytes = json.dumps(package, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.assertEqual(propose_bytes(package_bytes), render(first))

    def test_cli_end_to_end_patch(self):
        package = make_package(facts=[connect("fct-conn-1", "X1.2", "NB")])
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
            parsed = parse_proposal(raw)
            self.assertEqual(parsed.decision, "PATCH")

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
            self.assertEqual(parsed.refusal["reason_code"], "PUBLIC_INPUT_INSUFFICIENT")

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


def runner_inputs(observation_data, facts, grants=GRANTS, max_ops=8):
    """真实 runner build_package 所需的中性合成公共输入。"""
    source = '(kicad_sch (version 20230121) (paper "A4"))'
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
        inputs = runner_inputs(OBSERVATION, [place("fct-place-1", "X9")])
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
        self.assertEqual(proposal["refusal"]["reason_code"], "PUBLIC_INPUT_INSUFFICIENT")
        self.assertEqual(proposal["refusal"]["missing_fact_ids"], ["public-facts"])

    def test_real_package_cli_end_to_end(self):
        inputs = runner_inputs(OBSERVATION, [place("fct-place-1", "X9")])
        package_raw, _ = self.freeze(inputs)
        with tempfile.TemporaryDirectory() as temp_dir:
            package_path = Path(temp_dir) / "Y4-001.json"
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
