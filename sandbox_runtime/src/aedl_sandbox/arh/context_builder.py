"""ARH ContextBuilder — 每轮 ``RepairContext`` 的确定性组装（RFC §3.2 字段表）。

Responsibility boundary (ADR-016, RFC §3.2 / §5 D3-D7):

    ContextInputs + findings + trajectory rows
        -> ContextBuilder.build()
        -> RepairContext (frozen, arh/schema.py) + BuildReport

What this module is allowed to do
---------------------------------

* **findings 逐字透传**（RFC §3.2 row 3, D1）：``code`` / ``message`` 一个字符
  都不改写 —— ``state.py`` 的 stall 指纹只吃 ``(code, message)``，任何改写都会
  静默破坏 orchestrator 的循环判重。本模块只做 ``tuple(findings)``，
  编码发生在 ``schema.encode_finding``（同样逐字）。
* **投影而非 dump**（D6）：``receipts_digest`` 只留 ``{event_type, hash12}``
  （D5 裁决，以 ``state.encode_receipt`` 现有字段为准），``allowlist`` 只留
  RFC §3.2 row 9 的三个枚举键。喂进来的 ``engine.document`` 式大 dump 或
  payload 一律在入参侧被丢弃 —— 本模块不读文件、不联网、不序列化任何
  仓库外对象，L2 禁止清单（完整数据手册 / 完整合同 / 全轮 findings 原文）
  因此在结构上不可达。
* **L1 只透传**（RFC §3.2 rows 14-16）：``code_window`` / ``rule_source`` /
  ``datasheet_excerpt`` / ``evidence_excerpt`` 取 ``inputs`` 对应值，缺则
  ``None``。V1 的 ``inspect`` 工具尚未实现（declared not-implemented），
  所以"取不到 → 省略"是常态，不报错、不编造摘录。
* **折叠**（D3）：``attempt_history`` 只保留最近 ``attempts_keep`` 轮，
  更早的行折叠成 ``{"folded_older": <省略行数>}``；``rejected_proposals``
  **全量常驻**（ChatRepair 65% 重复补丁率是理由，RFC §3.2 row 7）。
* **预算裁剪**（RFC §3.2 注入预算行）：估算超 ``l0_token_budget`` 时按
  ``knowledge_ptr → receipts_digest → attempt_history 折叠加深 →
  locator_block`` 顺序裁，每步后重新估算，达标即停。
  **绝不裁** ``findings_current / allowlist / action_schema / deny_list /
  fingerprint_state / contract_ref / subject_frozen / verification_ref``
  （也绝不裁 ``rejected_proposals``，它是 L0 常驻去重面）——
  裁掉这些要么产生 fail-closed 事故，要么直接放大越权风险 [04 D7]。
  四步裁完仍超 → 如实 ``over_budget=True``，**不抛异常**（报告事实，
  不替调用方做决定）。
* **harness 身份不进 prompt**（T-07）：``ContextInputs.domain_id`` /
  ``candidate_root`` 在本模块**被忽略**，任何字段都不从它们取值。
  （RFC §3.2 row 1 的 ``contract_ref={domain_id, bundle_hash}`` 是**合同侧**
  由 wiring 提供的内容，本模块原样透传、不注入、不改写、也不裁剪。）

``deny_list`` 来源与 locator 提取键
------------------------------------

``ContextConfig.deny_list`` 逐条抄录自 RFC §2.3「永不授予清单」14 条原文
（``docs/specs/AEDL_AGENT_RUNTIME_RFC.md`` L97-110），语义不改写、不删条。
渲染（prompt 首尾各放一遍，位置效应 [04 D6]）是 ``repair_agent`` 的职责，
本模块只把它作为 ``RepairContext.deny_list`` 顶层字段交付。

``locator_block`` 的提取键 = RFC §3.2 row 4 的定位键，按仓库现实收窄：
``LOCATOR_EXTRACT_KEYS = (contract_id, rule_fingerprint, evidence_id, pin,
mpn, path, line)``。依据（grep 本仓库既有 ``Finding(...)`` 构造与 fixture）：

* ``contract_id`` — ``policy/engine.py`` L350/L425；断言见
  ``tests/policy/test_edd001_preflight.py`` L106、
  ``test_execution_policy.py`` L435。
* ``evidence_id`` — ``policy/engine.py`` L359/L435（RFC 行4 明列）。
* ``mpn`` — ``policy/engine.py`` L448/L500/L510/L523；断言见
  ``test_edd001_preflight.py`` L117。
* ``pin`` — ``policy/engine.py`` L537/L547/L564/L575。
* ``path`` — ``policy/engine.py`` L765（FILE_WRITE subject），且属
  ``schema.LOCATOR_KEYS``（§3.3 提案 locator 词表）。
* ``rule_fingerprint`` / ``line`` — 仓库内**没有任何** ``Finding.details``
  用过（只出现在 RFC §3.3 / ``LOCATOR_KEYS`` 词表里）；键位保留但现实中
  不会产生行，**绝不编造** [04 D2]。
* 明确排除：``missing_evidence_ids`` / ``missing_coverage_ids`` /
  ``parameter_id``（engine 的 details 键但不是定位键）、``manifest_path`` /
  ``attempt``（``adapters.py`` L230/L248/L512，不是 §3.3 locator 词表键）。

行序 = findings 顺序（只对至少含一个提取键的 finding 出行），键序 =
``LOCATOR_EXTRACT_KEYS`` 顺序，因此同输入必得同字节。

Token 估算
----------

``len(canonical_json(ctx.to_prompt_dict())) // 4`` —— **启发式**（约 4
字符/token 的经验值），RFC O-09 标 ``TO_VERIFY``：真实 token 数取决于
tokenizer 与渲染排版，本模块不加载任何 tokenizer（零网络、零模型调用）。
``BuildReport.estimated_tokens`` 是**裁剪后**的估算值。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Sequence

from aedl_sandbox.arh.schema import ContextInputs, RepairContext, canonical_json
from aedl_sandbox.protocol import Finding

__all__ = [
    "ALLOWLIST_KEYS",
    "DEFAULT_DENY_LIST",
    "LOCATOR_EXTRACT_KEYS",
    "RECEIPT_DIGEST_KEYS",
    "TRIM_ATTEMPT_HISTORY",
    "TRIM_CODE_WINDOW",
    "TRIM_KNOWLEDGE_PTR",
    "TRIM_LOCATOR_BLOCK",
    "TRIM_RECEIPTS_DIGEST",
    "BuildReport",
    "ContextBuilder",
    "ContextConfig",
]


# --------------------------------------------------------------------------
# Frozen projections (RFC §3.2 rows 4 / 8 / 9, decisions D2 / D5 / D6)
# --------------------------------------------------------------------------

#: ``receipts_digest`` 每行允许保留的键（D5：以 ``state.encode_receipt``
#: 现有字段为准，**不含 ``sequence``**，不带 payload）。
RECEIPT_DIGEST_KEYS: tuple[str, ...] = ("event_type", "hash12")

#: ``allowlist`` 顶层允许出现的三个键（RFC §3.2 row 9）。
ALLOWLIST_KEYS: tuple[str, ...] = ("evidence_ids", "active_rules", "allowed_components")

#: ``locator_block`` 的提取键（RFC §3.2 row 4 ∩ §3.3 LOCATOR_KEYS，见模块
#: docstring 的 grep 依据）。details 里没有的键永不出现 —— 不编造。
LOCATOR_EXTRACT_KEYS: tuple[str, ...] = (
    "contract_id",
    "rule_fingerprint",
    "evidence_id",
    "pin",
    "mpn",
    "path",
    "line",
)

#: Trim 标识：``BuildReport.trims`` 的取值即这五个常量，
#: 顺序 = 实际执行顺序。
TRIM_CODE_WINDOW = "code_window_lines_truncated"  # L1 唯一截断（D3 40 行）
TRIM_KNOWLEDGE_PTR = "knowledge_ptr"  # 预算裁剪 ①
TRIM_RECEIPTS_DIGEST = "receipts_digest"  # 预算裁剪 ②
TRIM_ATTEMPT_HISTORY = "attempt_history_fold"  # 预算裁剪 ③（折叠加深）
TRIM_LOCATOR_BLOCK = "locator_block"  # 预算裁剪 ④


#: RFC §2.3「永不授予清单」14 条**逐条抄录**（docs/specs/
#: AEDL_AGENT_RUNTIME_RFC.md L97-110），语义未改写。
DEFAULT_DENY_LIST: tuple[str, ...] = (
    "1. 任何候选/工作区写能力：`write_candidate_bytes`、裸文件写、shell/`SHELL_EXECUTE`、任意路径读写工具（T-01/T-02）。",
    "2. `.actions.jsonl`（ledger）、`receipt_root`、`checkpoint.sqlite`、run 根的读写（T-03/T-04/T-05）。",
    "3. `TrustPort.record` / `assess_promotion` 句柄，及任何向 receipt 目录写字的 API（T-04）。",
    "4. `orchestrator.resume()` / CLI `resume` / `Command(resume=...)`，以及 `approved_by`/`approver_role`/`human_decision`/`pending_human_action` 写权（T-13/T-16）。",
    "5. `PolicyRequest` 权威字段：`actor`、`capability_grants`、`run_id`、`domain_id`、`candidate_root`、`action_id`、`action`、`verified_bundle_sha256`、`verified_manifest_path` —— proposal schema 遇到即拒绝（T-07）。",
    "6. envelope 额外键：`design_action` + `design_subject` 之外的 subject 键一律拒绝（T-08）。",
    "7. port 装配权：`PolicyPort/ExecutorPort/VerifierPort/RepairPort/TrustPort/checkpointer` 的选择与实例注入（T-11）。",
    "8. 结果对象构造权：`VerificationResult`、`ExecutionResult`、`EvidenceEvent`、`EvidenceReceipt`、`Finding`（Agent 只能读 findings）（T-04/T-11）。",
    "9. `TrajectoryRecorder` 写入 receipt 目录或复用 `FileTrustStore`（T-06）。",
    "10. 网络出口（policy 侧恒 DENY：`engine.py` L814-823；工具层同样不给）（T-01 类）。",
    "11. 跨 run / 他人 receipt / 未授权 baseline 的读权限，以及 `engine.document`、`current_state()` 的全量 dump（T-14）。",
    "12. verifier 输入的参数化权：Agent 不能选择 verifier 判据/版本，只能提供候选内容（T-11）。",
    "13. verifier / 测试 / 合同 / 指纹常量的修改权（oracle 不可自评）（[02 D8]）。",
    "14. 多 agent handoff / 子 agent 编排（[01 §7] REFERENCE ONLY，与 ADR-015 单候选单写者锁冲突面未评估）。",
)


# --------------------------------------------------------------------------
# Configuration and report
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextConfig:
    """RFC §3.2 的三个可调阈值 + deny 资产。

    默认值全部来自 RFC / ADR-016 D3，且**本身标 TO_VERIFY**（pilot 才做
    40 vs 100 行 A/B，见 RFC §5 D3）；本模块不为这些估算值背书。
    """

    #: L0 token 预算（RFC §3.2 合计行 ≈2.5-4k，O-09 TO_VERIFY）。
    l0_token_budget: int = 4000
    #: attempt_history 保留的最近轮数（D3：最近 1 轮）。
    attempts_keep: int = 1
    #: code_window 允许的最大行数（D3：40 行，TO_VERIFY）。
    code_window_lines: int = 40
    #: RFC §2.3 never-grant 摘要，逐条抄录，见 ``DEFAULT_DENY_LIST``。
    deny_list: tuple[str, ...] = DEFAULT_DENY_LIST


@dataclass(frozen=True)
class BuildReport:
    """一次 ``build`` 的可观测事实（不参与 ``RepairContext.digest``）。"""

    #: 裁剪**之后**的启发式估算（``len(canonical_json)//4``，TO_VERIFY）。
    estimated_tokens: int
    #: 实际执行的裁剪/截断步骤，顺序即执行顺序；空 tuple = 一步未裁。
    trims: tuple[str, ...]
    #: 四步预算裁剪做完仍超 ``l0_token_budget`` 时为 True（如实报告，
    #: 不抛异常，也不悄悄裁永不裁的字段）。
    over_budget: bool


# --------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------


def _estimate_tokens(context: RepairContext) -> int:
    """启发式 token 估算：canonical JSON 字节数 ÷ 4。

    TO_VERIFY（RFC O-09）：这是经验值，不是 tokenizer 计数 —— ARH 测试
    零网络、不加载模型，换取的是可复现的**相对**比较（够/不够预算）。
    """
    return len(canonical_json(context.to_prompt_dict())) // 4


class ContextBuilder:
    """Assemble one round's ``RepairContext`` from wiring inputs.

    ``build_with_report`` 是唯一实现入口；``build`` 只是取其第一个返回值。
    本类无可变状态（配置冻结），同一输入重复构建必得相同 ``digest``。
    """

    def __init__(self, config: ContextConfig | None = None) -> None:
        self._config = config or ContextConfig()

    @property
    def config(self) -> ContextConfig:
        return self._config

    # -- public API --------------------------------------------------------

    def build(
        self,
        inputs: ContextInputs,
        findings: Sequence[Finding],
        attempts: Sequence[Mapping[str, Any]] = (),
        rejected: Sequence[Mapping[str, Any]] = (),
    ) -> RepairContext:
        """``build_with_report(...)`` 的第一个返回值（RFC §3.2 的结构本身）。"""
        return self.build_with_report(inputs, findings, attempts, rejected)[0]

    def build_with_report(
        self,
        inputs: ContextInputs,
        findings: Sequence[Finding],
        attempts: Sequence[Mapping[str, Any]] = (),
        rejected: Sequence[Mapping[str, Any]] = (),
    ) -> tuple[RepairContext, BuildReport]:
        """组装 ``RepairContext`` 并报告估算 / 裁剪 / 是否仍超预算。

        不修改入参；trajectory 行只做切片与折叠，**不重排键**。
        """
        cfg = self._config
        trims: list[str] = []

        # --- L0 rows 3-4: findings verbatim + deterministic locator -------
        findings_current = tuple(findings)
        locator_block = self._locator_block(findings_current)

        # --- L0 row 6: fold attempt history (D3) --------------------------
        attempt_rows = [dict(row) for row in attempts]
        attempt_history = self._fold_attempts(attempt_rows, cfg.attempts_keep)

        # --- L0 rows 7-9: rejected resident, receipts/allowlist projected --
        receipts_digest = self._project_receipts(inputs.receipts_digest)
        allowlist = self._project_allowlist(inputs.allowlist)

        # --- L0 row 11: deny list from config (rendering is RepairAgent's) -
        deny_list = tuple(cfg.deny_list)

        # --- L1 rows 14-16: pass-through, missing stays None --------------
        code_window, code_trim = self._code_window(inputs.code_window, cfg.code_window_lines)
        if code_trim is not None:
            trims.append(code_trim)

        context = RepairContext(
            contract_ref=dict(inputs.contract_ref),
            subject_frozen=dict(inputs.subject_frozen),
            findings_current=findings_current,
            locator_block=locator_block,
            fingerprint_state=dict(inputs.fingerprint_state),
            attempt_history=attempt_history,
            rejected_proposals=tuple(dict(row) for row in rejected),
            receipts_digest=receipts_digest,
            allowlist=allowlist,
            action_schema=dict(inputs.action_schema),
            deny_list=deny_list,
            knowledge_ptr=tuple(inputs.knowledge_ptr),
            verification_ref=dict(inputs.verification_ref),
            code_window=code_window,
            rule_source=self._copy_or_none(inputs.rule_source),
            datasheet_excerpt=self._copy_or_none(inputs.datasheet_excerpt),
            evidence_excerpt=self._copy_or_none(inputs.evidence_excerpt),
        )

        # --- budget: trim in RFC order, stop as soon as we fit ------------
        estimated = _estimate_tokens(context)
        collapsed = self._collapsed_attempts(len(attempt_rows))
        steps: tuple[
            tuple[
                str,
                Callable[[RepairContext], bool],
                Callable[[RepairContext], RepairContext],
            ],
            ...,
        ] = (
            (
                TRIM_KNOWLEDGE_PTR,
                lambda ctx: bool(ctx.knowledge_ptr),
                lambda ctx: replace(ctx, knowledge_ptr=()),
            ),
            (
                TRIM_RECEIPTS_DIGEST,
                lambda ctx: bool(ctx.receipts_digest),
                lambda ctx: replace(ctx, receipts_digest=()),
            ),
            (
                TRIM_ATTEMPT_HISTORY,
                lambda ctx: bool(ctx.attempt_history) and ctx.attempt_history != collapsed,
                lambda ctx: replace(ctx, attempt_history=collapsed),
            ),
            (
                TRIM_LOCATOR_BLOCK,
                lambda ctx: bool(ctx.locator_block),
                lambda ctx: replace(ctx, locator_block=()),
            ),
        )
        budget = cfg.l0_token_budget
        for name, needed, apply_step in steps:
            if estimated <= budget:
                break  # 达标即停：不为“记录好看”而多裁
            if not needed(context):
                continue  # 字段已空 = 无操作，不记入 trims（不虚报裁剪）
            context = apply_step(context)
            trims.append(name)
            estimated = _estimate_tokens(context)

        report = BuildReport(
            estimated_tokens=estimated,
            trims=tuple(trims),
            over_budget=estimated > budget,
        )
        return context, report

    # -- projections -------------------------------------------------------

    def _locator_block(
        self, findings: Sequence[Finding]
    ) -> tuple[Mapping[str, Any], ...]:
        """RFC §3.2 row 4：从 ``Finding.details`` 确定性派生定位键。

        行序 = findings 顺序；details 中不存在的提取键**不写入**
        （缺键 → 该键缺席，绝不填 ``UNKNOWN`` 占位 [04 D2]）；
        一个提取键都没有的 finding 不出行（避免空行噪声）。
        """
        rows: list[Mapping[str, Any]] = []
        for finding in findings:
            details = finding.details or {}
            row = {
                key: details[key]
                for key in LOCATOR_EXTRACT_KEYS
                if key in details
            }
            if row:
                rows.append(row)
        return tuple(rows)

    @staticmethod
    def _project_receipts(
        rows: Sequence[Mapping[str, Any]],
    ) -> tuple[Mapping[str, Any], ...]:
        """D5 裁决：每行只留 ``{event_type, hash12}``，多余键（payload /
        sequence / run_id …）一律丢弃。行里本来就缺的键不补占位（不编造）。
        """
        projected: list[Mapping[str, Any]] = []
        for row in rows:
            kept = {
                key: row[key] for key in RECEIPT_DIGEST_KEYS if key in row
            }
            if kept:
                projected.append(kept)
        return tuple(projected)

    @staticmethod
    def _project_allowlist(allowlist: Mapping[str, Any]) -> dict[str, Any]:
        """D6 裁决：allowlist 是**字段投影**，只保留 row 9 的三个枚举键。

        任何其它键（``engine.document`` 式 dump、``secret_extra`` …）
        在这里被丢弃；本模块从不读 ``engine.document``。
        """
        return {
            key: allowlist[key] for key in ALLOWLIST_KEYS if key in allowlist
        }

    @staticmethod
    def _fold_attempts(
        rows: Sequence[Mapping[str, Any]], keep: int
    ) -> tuple[Mapping[str, Any], ...]:
        """D3：只留最近 ``keep`` 行，更早的折叠成 ``{"folded_older": n}``。

        行数未超 ``keep``（或 ``keep <= 0`` 之外的无折叠情形）→ 原样返回。
        ``keep <= 0`` 时折叠掉全部行。键序不重排（``dict(row)`` 只做隔离）。
        """
        if len(rows) <= max(keep, 0):
            return tuple(rows)
        kept = tuple(rows[len(rows) - keep :]) if keep > 0 else ()
        folded: dict[str, Any] = {"folded_older": len(rows) - len(kept)}
        return kept + (folded,)

    def _collapsed_attempts(self, total: int) -> tuple[Mapping[str, Any], ...]:
        """预算裁剪③的目标态：整个 attempt_history 折成单行省略量。"""
        if total <= 0:
            return ()
        return ({"folded_older": total},)

    @staticmethod
    def _copy_or_none(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
        return None if value is None else dict(value)

    @staticmethod
    def _code_window(
        value: Mapping[str, Any] | None, limit: int
    ) -> tuple[dict[str, Any] | None, str | None]:
        """L1 row 14：``lines`` 超 ``limit`` 即截断 —— **唯一**截断 L1 的地方。

        返回 ``(窗口, 记录的 trim 名)``；窗口缺失/行数未超/没有 ``lines``
        列表 → 原样透传且不记录（不编造行、不报错：V1 inspect 未实现）。
        """
        if value is None:
            return None, None
        window = dict(value)
        lines = window.get("lines")
        if isinstance(lines, (list, tuple)) and len(lines) > limit:
            window["lines"] = list(lines)[:limit]
            return window, TRIM_CODE_WINDOW
        return window, None
