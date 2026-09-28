"""ARH ContextBuilder tests — RFC §3.2 RepairContext 字段表 / D3-D7 落地。

Zero network, zero model calls, zero file reads: every fixture (``ContextInputs``
/ ``Finding`` / trajectory row) is built in memory inside this file, so the suite
stays runnable offline like the rest of ``sandbox_runtime/tests``.

Coverage map (one group per RFC requirement):

* findings **逐字透传**（D1：stall 指纹只吃 ``code/message``，改一个字都算失败）
* ``locator_block`` 键集合 = RFC §3.2 行 4 ∩ 仓库真实 ``Finding.details`` 键，
  缺键不编造（D2）
* ``receipts_digest`` 投影（D5）、``allowlist`` 字段投影（D6）
* ``attempt_history`` 折叠 + ``folded_older`` 省略量（D3）
* ``rejected_proposals`` 全量常驻（row 7：65% 重复补丁）
* L1 缺失即 ``None``；``code_window`` 是**唯一**截断 L1 的地方
* ``deny_list`` 来自 config（§2.3 逐条抄录，渲染归 repair_agent）
* token 估算（启发式）与四步裁剪顺序、永不裁字段、``over_budget`` 如实报告
* digest 确定性 / 敏感性；harness 身份 ``domain_id`` / ``candidate_root`` 不进 prompt（T-07）
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from aedl_sandbox.arh.context_builder import (
    DEFAULT_DENY_LIST,
    LOCATOR_EXTRACT_KEYS,
    TRIM_ATTEMPT_HISTORY,
    TRIM_CODE_WINDOW,
    TRIM_KNOWLEDGE_PTR,
    TRIM_LOCATOR_BLOCK,
    TRIM_RECEIPTS_DIGEST,
    BuildReport,
    ContextBuilder,
    ContextConfig,
)
from aedl_sandbox.arh.schema import (
    AttemptRow,
    ContextInputs,
    RejectedRow,
    canonical_json,
    encode_finding,
)
from aedl_sandbox.protocol import Finding

#: 预算拉到天文数字 = 永不触发裁剪，用来隔离“结构本身”的断言。
FAR = ContextConfig(l0_token_budget=10**9)

#: T-07 红线：这两个 harness 身份**绝不能**出现在 prompt 载荷里。
HARNESS_DOMAIN = "HARNESS-DOMAIN-IDENTITY"
HARNESS_ROOT = Path("C:/harness/identity/candidate-1")

UNICODE_MESSAGE = "焊盘 GPIO43 未连接：netclass “Power” → ✅ ¿verificación ñ? —— 一字不改"
LONG_MESSAGE = ("REPAIR_LOOP：design_subject 未改变，fingerprint 与上一轮重复。" * 120)

FINDING_A = Finding(
    code="VERIFY_PIN_UNCONNECTED",
    message=UNICODE_MESSAGE,
    source="test-verifier",
    details={
        "mpn": "SS34",  # 故意乱序，键序应由 LOCATOR_EXTRACT_KEYS 决定
        "contract_id": "EDD-001.POWER",
        "note": "非定位键，不得进 locator_block",
    },
)
FINDING_B = Finding(
    code="VERIFY_CONTRACT_MISSING",
    message=LONG_MESSAGE,
    source="test-verifier",
    details={"pin": "GPIO43", "line": 17},
)
FINDING_NO_LOCATOR = Finding(
    code="VERIFY_NO_DETAIL",
    message="details 里没有定位键",
    source="test-verifier",
    details={"missing_evidence_ids": ["WROOM1_DATASHEET"], "parameter_id": "vbus.v"},
)
FINDINGS = (FINDING_A, FINDING_B)

ATTEMPTS = tuple(
    AttemptRow(
        round=index,
        fingerprint12=f"fp{index:010d}",
        diagnosis=f"diagnosis {index}",
        design_action="DESIGN_ASSIGN_PIN",
        subject_digest=f"subject{index}",
        outcome="DENIED",
    ).to_row()
    for index in (1, 2, 3)
)

REJECTED = tuple(
    RejectedRow(
        round=index,
        design_action="DESIGN_SELECT_COMPONENT",
        subject_digest=f"rejected{index}",
        reason="POLICY_SUBJECT_MALFORMED: unexpected key",
    ).to_row()
    for index in (1, 2)
)

_BUNDLE_HASH = "sha256:0f1e2d3c4b5a"


def make_inputs(**overrides) -> ContextInputs:
    """最小 ``ContextInputs`` 构造器（纯内存，不读任何仓库文件）。

    注意 ``contract_ref`` 只含合同侧 ``bundle_hash``：harness 侧的
    ``domain_id`` / ``candidate_root`` 按 T-07 不进 prompt（见
    ``test_prompt_payload_carries_no_harness_identity``）。
    """
    values: dict = dict(
        domain_id=HARNESS_DOMAIN,
        candidate_root=HARNESS_ROOT,
        contract_ref={"bundle_hash": _BUNDLE_HASH},
        subject_frozen={
            "design_action": "DESIGN_ASSIGN_PIN",
            "design_subject": {"pin": "GPIO43", "function": "U0TXD"},
        },
        fingerprint_state={
            "now": "fp-2",
            "prev": "fp-1",
            "stall_count": 0,
            "repair_count": 1,
            "max_repairs": 3,
        },
        verification_ref={
            "status": "FAIL",
            "candidate_id": "cand-1",
            "actor_id": "test-verifier",
        },
        receipts_digest=(
            {
                "event_type": "verify",
                "hash12": "aaaabbbbcccc",
                "payload": {"sequence": 2},
                "sequence": 2,
                "run_id": "run-1",
            },
            {"event_type": "preflight", "hash12": "ddddeeeeffff", "candidate_id": "cand-1"},
        ),
        allowlist={
            "evidence_ids": ["WROOM1_DATASHEET", "S3_DATASHEET"],
            "active_rules": [{"rule_id": "R1", "fingerprint": "f" * 16}],
            "allowed_components": [
                {
                    "mpn": "ESP32-S3-WROOM-1-N8R8",
                    "role": "mcu_module",
                    "required_evidence_ids": ["WROOM1_DATASHEET"],
                }
            ],
        },
        action_schema={
            "DESIGN_ASSIGN_PIN": [
                {"name": "pin", "type": "str", "required": True},
                {"name": "function", "type": "str", "required": True},
            ]
        },
        knowledge_ptr=("docs/ID_MAP.md", "docs/specs/AEDL_AGENT_RUNTIME_RFC.md"),
        code_window=None,
        rule_source=None,
        datasheet_excerpt=None,
        evidence_excerpt=None,
    )
    values.update(overrides)
    return ContextInputs(**values)


def build(
    inputs: ContextInputs | None = None,
    findings=FINDINGS,
    attempts=ATTEMPTS,
    rejected=REJECTED,
    config: ContextConfig | None = None,
):
    """``(context, report)``，默认用拉满预算的 config 隔离结构断言。"""
    builder = ContextBuilder(FAR if config is None else config)
    return builder.build_with_report(
        make_inputs() if inputs is None else inputs, findings, attempts, rejected
    )


def all_keys(value) -> set[str]:
    """递归收集 JSON 载荷里的所有键名（用来证明身份字段一个都没漏进来）。"""
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            keys.update(all_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(all_keys(item))
    return keys


def fat_allowlist(count: int = 300) -> dict:
    """一个塞满组件的 allowlist：大到四步裁剪也救不回预算。"""
    return {
        "evidence_ids": [f"EVID-{index:03d}" for index in range(count)],
        "active_rules": [
            {"rule_id": f"R{index}", "fingerprint": f"{index:08x}"}
            for index in range(count)
        ],
        "allowed_components": [
            {"mpn": f"MPN-{index}", "role": "mcu_module", "required_evidence_ids": []}
            for index in range(count)
        ],
    }


class FindingsPassthroughTests(unittest.TestCase):
    """RFC §3.2 row 3 / D1：``code``/``message`` 一个字符都不能改。"""

    def test_findings_are_passed_through_by_identity_and_text(self) -> None:
        context, _ = build()
        self.assertEqual(context.findings_current, FINDINGS)
        # 同一对象透传（不是重建、不是改写后再造一个）
        self.assertIs(context.findings_current[0], FINDING_A)
        self.assertIs(context.findings_current[1], FINDING_B)
        self.assertEqual(FINDING_A.message, UNICODE_MESSAGE)
        self.assertEqual(FINDING_B.message, LONG_MESSAGE)

    def test_prompt_payload_findings_are_verbatim_including_unicode_and_long_text(self) -> None:
        context, _ = build()
        payload = context.to_prompt_dict()["findings_current"]
        self.assertEqual(payload[0], encode_finding(FINDING_A))
        self.assertEqual(payload[1], encode_finding(FINDING_B))
        self.assertEqual(payload[0]["message"], UNICODE_MESSAGE)
        self.assertEqual(payload[1]["message"], LONG_MESSAGE)
        self.assertEqual(payload[0]["code"], "VERIFY_PIN_UNCONNECTED")
        # details 同样逐字保留（含那个“非定位键”，它只是不进 locator_block）
        self.assertEqual(payload[0]["details"]["note"], "非定位键，不得进 locator_block")


class LocatorBlockTests(unittest.TestCase):
    """RFC §3.2 row 4 / D2：确定性派生、键序固定、缺键不编造。"""

    def test_locator_block_extracts_only_known_keys_in_findings_order(self) -> None:
        context, _ = build()
        rows = list(context.locator_block)
        self.assertEqual(len(rows), 2)  # FINDING_NO_LOCATOR 不出行
        # 键序 = LOCATOR_EXTRACT_KEYS 序（details 原始顺序是 mpn 在前）
        self.assertEqual(list(rows[0]), ["contract_id", "mpn"])
        self.assertEqual(rows[0], {"contract_id": "EDD-001.POWER", "mpn": "SS34"})
        self.assertEqual(rows[1], {"pin": "GPIO43", "line": 17})
        # 行序 = findings 顺序（第一行来自 FINDING_A，第二行来自 FINDING_B）
        self.assertEqual(
            [row.get("contract_id") for row in rows],
            ["EDD-001.POWER", None],
        )
        # 非定位键不得混入
        self.assertNotIn("note", json.dumps(context.locator_block, ensure_ascii=False))

    def test_locator_block_never_invents_missing_keys(self) -> None:
        context, _ = build(findings=(FINDING_NO_LOCATOR,))
        self.assertEqual(context.locator_block, ())
        text = canonical_json(context.locator_block)
        self.assertNotIn("UNKNOWN", text)
        self.assertNotIn("rule_fingerprint", text)  # 仓库无此 details 键
        # 提取键集合本身是冻结的（RFC 行4 ∩ §3.3 LOCATOR_KEYS）
        self.assertEqual(
            LOCATOR_EXTRACT_KEYS,
            ("contract_id", "rule_fingerprint", "evidence_id", "pin", "mpn", "path", "line"),
        )


class ProjectionTests(unittest.TestCase):
    """D5 receipts 投影 / D6 allowlist 字段投影。"""

    def test_receipts_digest_rows_keep_only_event_type_and_hash12(self) -> None:
        context, _ = build()
        self.assertEqual(len(context.receipts_digest), 2)
        self.assertEqual(
            context.receipts_digest[0],
            {"event_type": "verify", "hash12": "aaaabbbbcccc"},
        )
        self.assertEqual(
            context.receipts_digest[1],
            {"event_type": "preflight", "hash12": "ddddeeeeffff"},
        )
        text = canonical_json(list(context.receipts_digest))
        for forbidden in ("payload", "sequence", "run_id", "candidate_id"):
            self.assertNotIn(forbidden, text)

    def test_receipts_digest_row_missing_a_key_is_not_filled_in(self) -> None:
        inputs = make_inputs(
            receipts_digest=(
                {"event_type": "verify"},
                {"hash12": "ffffffffffff"},
            )
        )
        context, _ = build(inputs=inputs)
        self.assertEqual(list(context.receipts_digest[0]), ["event_type"])
        self.assertEqual(list(context.receipts_digest[1]), ["hash12"])
        self.assertNotIn("UNKNOWN", canonical_json(list(context.receipts_digest)))

    def test_allowlist_projection_drops_every_other_key(self) -> None:
        inputs = make_inputs(
            allowlist={
                "evidence_ids": ["WROOM1_DATASHEET"],
                "active_rules": [],
                "allowed_components": [],
                # D6 明令禁止进 prompt 的东西
                "engine_document": {"pins": ["GPIO1"], "rules": ["*"] * 50},
                "secret_extra": "leak-me",
            }
        )
        context, _ = build(inputs=inputs)
        self.assertEqual(
            sorted(context.allowlist),
            ["active_rules", "allowed_components", "evidence_ids"],
        )
        text = canonical_json(dict(context.allowlist))
        self.assertNotIn("engine_document", text)
        self.assertNotIn("secret_extra", text)
        self.assertNotIn("leak-me", text)
        self.assertNotIn("GPIO1", text)

    def test_allowlist_projection_keeps_only_keys_present_in_input(self) -> None:
        inputs = make_inputs(allowlist={"evidence_ids": ["WROOM1_DATASHEET"]})
        context, _ = build(inputs=inputs)
        self.assertEqual(dict(context.allowlist), {"evidence_ids": ["WROOM1_DATASHEET"]})
        # 一个键都没有的入参 → 空投影，不补默认值
        context_empty, _ = build(inputs=make_inputs(allowlist={}))
        self.assertEqual(context_empty.allowlist, {})


class TrajectoryTests(unittest.TestCase):
    """D3 折叠 / row 7 拒绝提案常驻。"""

    def test_attempt_history_folds_older_rows_and_reports_omitted_count(self) -> None:
        context, report = build()
        self.assertEqual(len(context.attempt_history), 2)
        # 最近 1 轮原样保留（含 proposal 嵌套结构，键序不重排）
        self.assertEqual(context.attempt_history[0], dict(ATTEMPTS[2]))
        self.assertEqual(dict(context.attempt_history[1]), {"folded_older": 2})
        self.assertEqual(report.trims, ())  # 正常折叠不是裁剪，不记 trims

    def test_attempt_history_is_untouched_when_within_keep(self) -> None:
        context, report = build(config=ContextConfig(l0_token_budget=10**9, attempts_keep=3))
        self.assertEqual(context.attempt_history, tuple(dict(row) for row in ATTEMPTS))
        self.assertEqual(report.trims, ())
        # attempts 为空 → 既不折叠也不塞 folded_older 占位
        context_empty, _ = build(attempts=())
        self.assertEqual(context_empty.attempt_history, ())

    def test_rejected_proposals_are_passed_through_in_full(self) -> None:
        context, _ = build()
        self.assertEqual(context.rejected_proposals, tuple(dict(row) for row in REJECTED))
        self.assertEqual(len(context.rejected_proposals), 2)
        row = context.rejected_proposals[0]
        self.assertEqual(
            sorted(row), ["action", "reason", "round", "subject_digest"]
        )
        self.assertIn("POLICY_SUBJECT_MALFORMED", row["reason"])
        # 全量常驻：即使预算为 1，也绝不裁（row 7 / 65% 重复补丁）
        starved, _ = build(config=ContextConfig(l0_token_budget=1))
        self.assertEqual(
            starved.rejected_proposals, tuple(dict(row) for row in REJECTED)
        )


class L1FieldTests(unittest.TestCase):
    """RFC §3.2 rows 14-16：缺则 ``None``；``code_window`` 是唯一截断点。"""

    def test_l1_fields_default_to_none_and_are_omitted_from_prompt(self) -> None:
        context, report = build()
        self.assertIsNone(context.code_window)
        self.assertIsNone(context.rule_source)
        self.assertIsNone(context.datasheet_excerpt)
        self.assertIsNone(context.evidence_excerpt)
        payload = context.to_prompt_dict()
        for name in ("code_window", "rule_source", "datasheet_excerpt", "evidence_excerpt"):
            self.assertNotIn(name, payload)
        self.assertEqual(report.trims, ())

    def test_l1_fields_pass_through_when_supplied(self) -> None:
        inputs = make_inputs(
            code_window={"path": "src/uart.py", "start": 10, "lines": ["a", "b", "c"]},
            rule_source={"rule_id": "R1", "source_ids": {"R1": "sha256:abc"}},
            datasheet_excerpt={"mpn": "SS34", "page": 3, "text": "Vf = 0.5 V"},
            evidence_excerpt={"evidence_id": "WROOM1_DATASHEET", "text": "pin 38"},
        )
        context, report = build(inputs=inputs)
        self.assertEqual(
            context.code_window, {"path": "src/uart.py", "start": 10, "lines": ["a", "b", "c"]}
        )
        self.assertEqual(context.rule_source, {"rule_id": "R1", "source_ids": {"R1": "sha256:abc"}})
        self.assertEqual(context.datasheet_excerpt["mpn"], "SS34")
        self.assertEqual(context.evidence_excerpt["evidence_id"], "WROOM1_DATASHEET")
        self.assertEqual(report.trims, ())
        self.assertIn("code_window", context.to_prompt_dict())

    def test_code_window_is_truncated_to_configured_line_count_and_recorded(self) -> None:
        window = {"path": "src/board.py", "start": 1, "lines": [f"line {i}" for i in range(100)]}
        context, report = build(
            inputs=make_inputs(code_window=window),
            config=ContextConfig(l0_token_budget=10**9, code_window_lines=40),
        )
        self.assertEqual(len(context.code_window["lines"]), 40)
        self.assertEqual(context.code_window["lines"][0], "line 0")
        self.assertEqual(context.code_window["lines"][-1], "line 39")
        # 其余字段不被动过；截断被如实记录
        self.assertEqual(context.code_window["path"], "src/board.py")
        self.assertEqual(context.code_window["start"], 1)
        self.assertEqual(report.trims, (TRIM_CODE_WINDOW,))
        # 自定义阈值（D3 的 40 行是 TO_VERIFY 估算值）
        short, short_report = build(
            inputs=make_inputs(code_window=window),
            config=ContextConfig(l0_token_budget=10**9, code_window_lines=5),
        )
        self.assertEqual(len(short.code_window["lines"]), 5)
        self.assertEqual(short_report.trims, (TRIM_CODE_WINDOW,))
        # 没有 lines 列表 / 行数未超 → 不动也不记录
        unchanged, unchanged_report = build(
            inputs=make_inputs(code_window={"path": "p", "lines": ["only"]})
        )
        self.assertEqual(unchanged.code_window, {"path": "p", "lines": ["only"]})
        self.assertEqual(unchanged_report.trims, ())


class DenyListTests(unittest.TestCase):
    """RFC §2.3 never-grant 摘要（逐条抄录）作为顶层字段交付，不渲染。"""

    def test_deny_list_is_the_rfc_23_summary_and_comes_from_config(self) -> None:
        context, _ = build()
        self.assertEqual(tuple(context.deny_list), DEFAULT_DENY_LIST)
        self.assertEqual(context.deny_list, ContextConfig().deny_list)
        self.assertEqual(len(context.deny_list), 14)  # §2.3 共 14 条
        for index, item in enumerate(context.deny_list, start=1):
            self.assertTrue(item.startswith(f"{index}. "), item)
        # 第 5 条是 T-07 权威字段（不可改写语义）
        self.assertIn("PolicyRequest", context.deny_list[4])
        self.assertIn("T-07", context.deny_list[4])
        # deny_list 在 prompt 载荷里（渲染首尾是 repair_agent 的职责）
        self.assertEqual(
            context.to_prompt_dict()["deny_list"], list(DEFAULT_DENY_LIST)
        )

    def test_configured_deny_list_replaces_default(self) -> None:
        config = ContextConfig(l0_token_budget=10**9, deny_list=("1. 只留这一条。",))
        context, _ = build(config=config)
        self.assertEqual(tuple(context.deny_list), ("1. 只留这一条。",))
        self.assertNotEqual(tuple(context.deny_list), DEFAULT_DENY_LIST)


class BudgetAndTrimTests(unittest.TestCase):
    """token 估算 + RFC 四步裁剪顺序 + 永不裁 + over_budget 如实报告。"""

    def test_token_estimate_is_canonical_json_length_over_four(self) -> None:
        context, report = build()
        expected = len(canonical_json(context.to_prompt_dict())) // 4
        self.assertEqual(report.estimated_tokens, expected)
        self.assertFalse(report.over_budget)
        self.assertIsInstance(report, BuildReport)

    def test_four_trims_run_in_rfc_order(self) -> None:
        context, report = build(config=ContextConfig(l0_token_budget=1))
        self.assertEqual(
            report.trims,
            (
                TRIM_KNOWLEDGE_PTR,
                TRIM_RECEIPTS_DIGEST,
                TRIM_ATTEMPT_HISTORY,
                TRIM_LOCATOR_BLOCK,
            ),
        )
        # 每一步真的生效了
        self.assertEqual(context.knowledge_ptr, ())
        self.assertEqual(context.receipts_digest, ())
        self.assertEqual(context.attempt_history, ({"folded_older": len(ATTEMPTS)},))
        self.assertEqual(context.locator_block, ())
        self.assertGreater(report.estimated_tokens, 1)

    def test_trims_stop_as_soon_as_the_budget_is_met(self) -> None:
        full = make_inputs()
        without_knowledge = make_inputs(knowledge_ptr=())
        before = build(inputs=full)[1].estimated_tokens
        after_first_step = build(inputs=without_knowledge)[1].estimated_tokens
        self.assertGreater(before, after_first_step)

        context, report = build(
            inputs=full,
            config=ContextConfig(l0_token_budget=after_first_step),
        )
        # 只裁了第一步就达标 → 后三步不执行（达标即停，不虚报裁剪）
        self.assertEqual(report.trims, (TRIM_KNOWLEDGE_PTR,))
        self.assertEqual(report.estimated_tokens, after_first_step)
        self.assertFalse(report.over_budget)
        # 被裁的只有 knowledge_ptr，其余结构原样
        self.assertEqual(context.receipts_digest[0], {"event_type": "verify", "hash12": "aaaabbbbcccc"})
        self.assertEqual(len(context.locator_block), 2)

    def test_never_trimmed_fields_survive_a_severe_budget(self) -> None:
        inputs = make_inputs()
        context, report = build(inputs=inputs, config=ContextConfig(l0_token_budget=1))
        # 四步之外的字段一步都不许裁（D7）
        never = {
            "findings_current",
            "allowlist",
            "action_schema",
            "deny_list",
            "fingerprint_state",
            "contract_ref",
            "subject_frozen",
            "verification_ref",
            "rejected_proposals",
        }
        self.assertTrue(never.isdisjoint(set(report.trims)))
        # findings 逐字相等
        self.assertEqual(context.findings_current, FINDINGS)
        self.assertEqual(
            [encode_finding(finding)["message"] for finding in context.findings_current],
            [UNICODE_MESSAGE, LONG_MESSAGE],
        )
        # allowlist / action_schema / deny_list 逐字相等
        self.assertEqual(
            dict(context.allowlist), dict(make_inputs().allowlist)
        )
        self.assertEqual(dict(context.action_schema), dict(inputs.action_schema))
        self.assertEqual(tuple(context.deny_list), DEFAULT_DENY_LIST)
        self.assertEqual(dict(context.fingerprint_state), dict(inputs.fingerprint_state))
        self.assertEqual(dict(context.contract_ref), dict(inputs.contract_ref))
        self.assertEqual(dict(context.subject_frozen), dict(inputs.subject_frozen))
        self.assertEqual(dict(context.verification_ref), dict(inputs.verification_ref))
        self.assertEqual(context.rejected_proposals, tuple(dict(r) for r in REJECTED))

    def test_over_budget_is_reported_without_raising_when_four_steps_do_not_fit(self) -> None:
        inputs = make_inputs(allowlist=fat_allowlist(300))
        context, report = build(
            inputs=inputs, config=ContextConfig(l0_token_budget=100)
        )
        # 四步都裁完仍然超 → 如实 True，不抛异常、不偷裁 allowlist
        self.assertTrue(report.over_budget)
        self.assertEqual(
            report.trims,
            (
                TRIM_KNOWLEDGE_PTR,
                TRIM_RECEIPTS_DIGEST,
                TRIM_ATTEMPT_HISTORY,
                TRIM_LOCATOR_BLOCK,
            ),
        )
        self.assertGreater(report.estimated_tokens, 100)
        self.assertEqual(len(context.allowlist["allowed_components"]), 300)
        self.assertEqual(context.allowlist, inputs.allowlist)


class DeterminismTests(unittest.TestCase):
    """同输入 → 同 digest；改一个 message → digest 变。"""

    def test_same_inputs_produce_the_same_context_and_digest(self) -> None:
        first, _ = build()
        second, _ = build()
        self.assertEqual(first, second)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(
            canonical_json(first.to_prompt_dict()),
            canonical_json(second.to_prompt_dict()),
        )

    def test_changing_one_message_changes_the_digest(self) -> None:
        original, _ = build()
        mutated = Finding(
            code=FINDING_A.code,
            message=FINDING_A.message + "（换个说法）",
            source=FINDING_A.source,
            details=dict(FINDING_A.details),
        )
        changed, _ = build(findings=(mutated, FINDING_B))
        self.assertNotEqual(original.digest, changed.digest)

    def test_build_returns_exactly_what_build_with_report_returns(self) -> None:
        builder = ContextBuilder(FAR)
        inputs = make_inputs()
        via_build = builder.build(inputs, FINDINGS, ATTEMPTS, REJECTED)
        via_report, report = builder.build_with_report(inputs, FINDINGS, ATTEMPTS, REJECTED)
        self.assertEqual(via_build, via_report)
        self.assertEqual(via_build.digest, via_report.digest)
        self.assertFalse(report.over_budget)
        self.assertEqual(report.trims, ())


class PromptBoundaryTests(unittest.TestCase):
    """T-07：harness 身份不进 prompt；contract_ref 由 wiring 供给且不裁。"""

    def test_prompt_payload_carries_no_harness_identity(self) -> None:
        context, _ = build()
        payload = context.to_prompt_dict()
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        # 值不出现
        self.assertNotIn(HARNESS_DOMAIN, text)
        self.assertNotIn("candidate-1", text)
        # 键不出现（顶层与递归）
        self.assertNotIn("domain_id", set(payload))
        self.assertNotIn("candidate_root", set(payload))
        keys = all_keys(payload)
        self.assertNotIn("domain_id", keys)
        self.assertNotIn("candidate_root", keys)

    def test_domain_id_and_candidate_root_do_not_influence_the_context(self) -> None:
        # builder 必须**忽略**这两个字段：改它们不改变任何 prompt 内容
        first, _ = build(
            inputs=make_inputs(
                domain_id="DOMAIN-A", candidate_root=Path("/tmp/candidate-a")
            )
        )
        second, _ = build(
            inputs=make_inputs(
                domain_id="DOMAIN-B", candidate_root=Path("/completely/other/root")
            )
        )
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(
            canonical_json(first.to_prompt_dict()),
            canonical_json(second.to_prompt_dict()),
        )

    def test_contract_ref_from_wiring_is_passed_through_and_never_trimmed(self) -> None:
        # RFC §3.2 row 1 的 contract_ref = {domain_id, bundle_hash} 是**合同侧**
        # 由 wiring 提供的映射：builder 只透传（既不注入 inputs.domain_id，
        # 也不删除调用方给的键），且它属于“绝不裁”四步之外的字段。
        contract_ref = {"domain_id": "CONTRACT-DOMAIN", "bundle_hash": _BUNDLE_HASH}
        context, report = build(
            inputs=make_inputs(contract_ref=contract_ref),
            config=ContextConfig(l0_token_budget=1),
        )
        self.assertEqual(dict(context.contract_ref), contract_ref)
        self.assertNotIn("contract_ref", report.trims)
        # harness 侧身份依然没进来
        text = json.dumps(context.to_prompt_dict(), ensure_ascii=False)
        self.assertNotIn(HARNESS_DOMAIN, text)
        self.assertNotIn("candidate-1", text)


if __name__ == "__main__":  # pragma: no cover - discovery 入口
    unittest.main()
