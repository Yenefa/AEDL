"""AEDL Y4 实验 · D 组固定规则基线（deterministic baseline）。

作用
----
读取"公共检查器反馈"（gates/schematic_semantics.py 产出的 findings 报告）和
"公共事实包"（公开批准的器件值/约束），按冻结规则推导修复提案，或有理由地拒绝。

设计依据（均有原文出处，2026-09-10 核实）：
- docs/competition/internal/AEDL_W1_Y4_AI_vs_Script_实验方案.md 第 3 节：
  * D 至少六类处理规则（五类已知约束的修复逻辑 + 证据不足时拒绝）
  * 允许查表、条件分支、参数化修复模板；禁止 case_id→标准补丁、
    按案例文件名分支、复制固定最终文件
  * PCB 未同步须显示边界，不得宣称整板通过
- gates/contracts/m2_schematic_contract_v1.json：公开领域规则（5 类约束），
  实验方案明文"它们是 D 可复用的领域知识，不是 AI 独占信息"
- W2 主任务卡 A2-L：与 AI 组相同 proposal schema（schema 尚未冻结，
  本文件输出为 draft-0.1，待与 PR-1 C1 parse_proposal 对齐）

合规要点：
- 不包含任何实验案例的标准补丁；修复目标全部从检查器反馈的
  expected/observed 推导，批准值从公共事实包读取。
- 只按 rule_id（公开合同里的规则类型）分支，绝不按案例文件名/编号分支。
- fail-closed：任何无法用已批准规则解释的失败，整体拒绝（REFUSE），绝不猜补丁。

输入
----
1) feedback：检查器报告 JSON（status/summary/findings；findings[].details 行格式：
   "{view}.{section}.{key}: expected {JSON}, observed {JSON|<missing>}"）
2) facts：公共事实包 JSON（schema: aedl.public-facts.draft-0.1）

用法
----
    py -3 tools/repair_baseline.py --feedback findings.json --facts facts.json --out proposal.json

退出码：0 = 已产出提案（修复/拒绝/无需改动都算）；2 = 输入不合法。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROPOSAL_SCHEMA = "aedl.repair-proposal.draft-0.1"
FACTS_SCHEMA = "aedl.public-facts.draft-0.1"
TOOL_VERSION = "0.3.0"

# 派生修复操作只看这两个视图；pcb 不一致属于"PCB 未同步"边界（方案 §2 验收范围），
# 只记入 notes，不派生操作。
DERIVED_VIEWS = ("intent", "netlist")

MISSING = "<missing>"

# 拒绝原因优先级：一个案例同时踩中多类问题时，取最严重的一类作为 reason_code
_REFUSE_PRIORITY = (
    "UNHANDLED_RULE",
    "MALFORMED_FEEDBACK",
    "EVIDENCE_CONFLICT",
    "FIRMWARE_READ_ONLY_CONFLICT",
    "VALUE_NOT_APPROVED",
    "INSUFFICIENT_EVIDENCE",
)


class BaselineInputError(Exception):
    """输入文件缺失/格式非法（CLI 退出码 2）。"""


# ---------------------------------------------------------------------------
# 公开规则注册表：键 = 公开合同 m2_schematic_contract_v1.json 里的 rule_id。
# 仅声明"该规则可处理"；修复目标一律来自反馈里的 expected，不在此写死任何补丁。
# ---------------------------------------------------------------------------

RULE_REGISTRY: Dict[str, str] = {
    "USB_POLARITY_AND_SERIES": "USB D+/D- 极性与 22R 串阻（对应实验案例 1、3）",
    "SHT30_ADDRESS": "SHT30 ADDR 接低且固件使用 0x44（对应实验案例 2）",
    "SHT30_UNUSED_PINS": "SHT30 ALERT/nRESET 保持悬空（受保护，不得乱接）",
    "ESP32_EN_RC": "EN 复位网络 10k 上拉 + 1uF 电容（对应实验案例 5）",
    "ESP32_GPIO9_PULLUP": "GPIO9 启动上拉 10k（对应实验案例 4）",
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def normalize_value(raw: Any) -> Optional[str]:
    """归一化元件值：22Ω/22R/22 -> 22R；10k/10K/10kΩ -> 10k；1µF/1uF -> 1uF。

    无法识别返回 None（调用方 fail-closed 处理）。
    """
    if raw is None:
        return None
    s = str(raw).strip()
    s = s.replace("µ", "u").replace("μ", "u").replace("Ω", "R").replace("ω", "r")
    m = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(k|K|u|U|n|N|M)?\s*(R|F|r|f)?$", s)
    if not m:
        return None
    num, mult, unit = m.group(1), m.group(2) or "", (m.group(3) or "").upper()
    mult = {"K": "k", "U": "u", "N": "n"}.get(mult, mult)
    if unit == "F":
        return f"{num}{mult}F"
    if mult:  # 10k 风格（合同写法）
        return f"{num}{mult}"
    return f"{num}R"


def parse_detail_line(line: str) -> Optional[Tuple[str, str, str, Any, Any]]:
    """解析检查器 detail 行 -> (view, section, key, expected, observed)。

    observed 可能是字符串 "<missing>"。解析失败返回 None。
    """
    left, sep, rest = line.strip().partition(": expected ")
    if not sep:
        return None
    exp_str, sep2, obs_str = rest.partition(", observed ")
    if not sep2:
        return None
    parts = left.split(".", 2)
    if len(parts) != 3 or parts[1] not in ("pins", "components", "constants"):
        return None
    view, section, key = parts
    try:
        expected = json.loads(exp_str)
    except json.JSONDecodeError:
        return None
    if obs_str.strip() == MISSING:
        observed = MISSING
    else:
        try:
            observed = json.loads(obs_str)
        except json.JSONDecodeError:
            return None
    return view, section, key, expected, observed


def sha256_of_text(obj: Any) -> str:
    canonical = json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# 提案与拒绝的构造
# ---------------------------------------------------------------------------


@dataclass
class Blocker:
    reason_code: str
    what: str
    source: str


@dataclass
class Proposal:
    decision: str  # PROPOSE_REPAIR / REFUSE / NO_CHANGE_NEEDED
    operations: List[Dict[str, Any]] = field(default_factory=list)
    rules_addressed: List[str] = field(default_factory=list)
    unhandled_findings: List[str] = field(default_factory=list)
    refusal: Optional[Dict[str, Any]] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self, feedback_sha: str, facts_sha: str) -> Dict[str, Any]:
        return {
            "schema": PROPOSAL_SCHEMA,
            "note": "schema 为草案，待与 PR-1 C1 parse_proposal 对齐",
            "generated_by": {"arm": "D", "tool": "tools/repair_baseline.py", "version": TOOL_VERSION},
            "inputs": {"feedback_sha256": feedback_sha, "facts_sha256": facts_sha},
            "decision": self.decision,
            "operations": self.operations,
            "rules_addressed": self.rules_addressed,
            "unhandled_findings": self.unhandled_findings,
            "refusal": self.refusal,
            "notes": self.notes,
        }


def _consolidated_refusal(
    blockers: List[Blocker], unhandled: List[str], failing_rule_ids: List[str]
) -> Proposal:
    codes = {b.reason_code for b in blockers}
    reason_code = next((c for c in _REFUSE_PRIORITY if c in codes), "INSUFFICIENT_EVIDENCE")
    gaps = [{"what": b.what, "source": b.source} for b in blockers]
    return Proposal(
        decision="REFUSE",
        operations=[],
        unhandled_findings=list(unhandled),
        refusal={
            "status": "REFUSE",
            "reason_code": reason_code,
            "gaps": gaps,
            "rules_blocked": sorted(set(failing_rule_ids)),
        },
    )


# ---------------------------------------------------------------------------
# 核心：从 findings 推导提案（纯函数）
# ---------------------------------------------------------------------------


def build_proposal(feedback: Dict[str, Any], facts: Dict[str, Any]) -> Proposal:
    blockers: List[Blocker] = []
    unhandled: List[str] = []
    notes: List[str] = []

    # ---- 0. 输入形状校验（fail-closed）----
    if not isinstance(feedback, dict) or not isinstance(feedback.get("findings"), list):
        raise BaselineInputError("feedback 缺少 findings 数组")
    if not isinstance(facts, dict):
        raise BaselineInputError("facts 必须是对象")
    if facts.get("schema") != FACTS_SCHEMA:
        raise BaselineInputError(f"facts schema 必须是 {FACTS_SCHEMA}")

    failing = [f for f in feedback["findings"] if f.get("status") == "fail"]
    if not failing:
        return Proposal(decision="NO_CHANGE_NEEDED")

    # ---- 1. 事实包整体资料不足 -> 全案拒绝（对应第 6 例"资料不足必须拒绝"）----
    failing_rule_ids = [str(f.get("rule_id")) for f in failing]

    if facts.get("facts_status") != "complete":
        pkg_gaps = facts.get("facts_gaps") or [
            {"what": "公共事实包标记为不完整", "source": "facts.facts_status"}
        ]
        blockers.extend(
            Blocker("INSUFFICIENT_EVIDENCE", g["what"], g["source"]) for g in pkg_gaps
        )
        return _consolidated_refusal(blockers, unhandled, failing_rule_ids)

    approved_values = {normalize_value(v) for v in facts.get("approved_component_values", [])}
    approved_values.discard(None)
    protected = facts.get("protected", {})
    merge_forbidden = [tuple(p) for p in protected.get("nets_must_not_merge", [])]
    firmware_read_only = bool(protected.get("firmware_constants_read_only", True))

    # ---- 2. 解析所有失败规则 ----
    # entries: (rule_id, detail_idx, view, section, key, expected, observed)
    entries: List[Tuple[str, int, str, str, str, Any, Any]] = []
    for f in failing:
        rule_id = str(f.get("rule_id"))
        if rule_id not in RULE_REGISTRY:
            unhandled.append(rule_id)
            continue
        for idx, detail in enumerate(f.get("details", [])):
            parsed = parse_detail_line(str(detail))
            if parsed is None:
                blockers.append(Blocker(
                    "MALFORMED_FEEDBACK", f"无法解析的检查反馈行：{detail}",
                    f"{rule_id}.details[{idx}]",
                ))
                continue
            view, section, key, expected, observed = parsed
            entries.append((rule_id, idx, view, section, key, expected, observed))

    if unhandled:
        blockers.extend(Blocker("UNHANDLED_RULE", r, "RULE_REGISTRY") for r in unhandled)
        return _consolidated_refusal(blockers, unhandled, failing_rule_ids)

    # ---- 3. expected 跨视图一致性（intent 与 netlist 必须一致）----
    expected_seen: Dict[Tuple[str, str], Tuple[Any, str]] = {}
    for rule_id, idx, view, section, key, expected, _obs in entries:
        if view not in DERIVED_VIEWS:
            continue
        stamp = (section, key)
        if stamp in expected_seen and expected_seen[stamp][0] != expected:
            blockers.append(Blocker(
                "EVIDENCE_CONFLICT",
                f"{section}.{key} 在不同视图的 expected 不一致："
                f"{json.dumps(expected_seen[stamp][0], ensure_ascii=False)} vs "
                f"{json.dumps(expected, ensure_ascii=False)}",
                rule_id,
            ))
        expected_seen.setdefault(stamp, (expected, rule_id))

    # ---- 4. 固件只读：firmware 视图出现不匹配 -> 拒绝（修复范围仅硬件）----
    for rule_id, idx, view, section, key, expected, observed in entries:
        if view == "firmware" and observed != expected:
            blockers.append(Blocker(
                "FIRMWARE_READ_ONLY_CONFLICT",
                f"固件常量 {key} 与公开规则不一致（expected={expected!r}, observed={observed!r}）；"
                f"固件只读，修复范围仅限硬件连接/参数，因此拒绝猜测性修复",
                f"{rule_id}.details[{idx}]",
            ))

    # ---- 5. 全局聚合 intent/netlist 的 expected/observed ----
    # observed 语义：<missing> 表示"该视图看不到"（intent 天然不列悬空引脚），
    # 不与其他视图冲突。不同视图给出的具体观测只有在关键字段
    # （引脚 → net、元件 → value）一致时才算互证，否则 EVIDENCE_CONFLICT。
    pin_exp: Dict[Tuple[str, str], Dict[str, Any]] = {}
    pin_obs: Dict[Tuple[str, str], Any] = {}
    pin_src: Dict[Tuple[str, str], str] = {}
    comp_exp: Dict[str, Any] = {}
    comp_obs: Dict[str, Any] = {}
    comp_src: Dict[str, str] = {}

    for rule_id, idx, view, section, key, expected, observed in entries:
        if view not in DERIVED_VIEWS:
            continue
        if observed != MISSING and not isinstance(observed, dict):
            blockers.append(Blocker(
                "MALFORMED_FEEDBACK",
                f"{view}.{section}.{key} 的观测值格式异常（应为对象或 <missing>）：{observed!r}",
                f"{rule_id}.details[{idx}]",
            ))
            continue
        if section == "pins":
            ref, dot, pin = key.partition(".")
            if not dot or not pin:
                blockers.append(Blocker(
                    "MALFORMED_FEEDBACK", f"引脚键格式异常（应为 REF.PIN）：{key!r}",
                    f"{rule_id}.details[{idx}]",
                ))
                continue
            stamp = (ref, pin)
            prev = pin_obs.get(stamp, MISSING)
            if isinstance(prev, dict) and isinstance(observed, dict) \
                    and prev.get("net") != observed.get("net"):
                blockers.append(Blocker(
                    "EVIDENCE_CONFLICT",
                    f"引脚 {key} 在不同视图的 net 不一致："
                    f"{prev.get('net')!r} vs {observed.get('net')!r}",
                    rule_id,
                ))
            if isinstance(observed, dict) or prev == MISSING:
                pin_obs[stamp] = observed
            pin_exp[stamp] = expected if isinstance(expected, dict) else {}
            pin_src[stamp] = f"{rule_id}.details[{idx}]"
        elif section == "components":
            prev = comp_obs.get(key, MISSING)
            if isinstance(prev, dict) and isinstance(observed, dict) \
                    and prev.get("value") != observed.get("value"):
                blockers.append(Blocker(
                    "EVIDENCE_CONFLICT",
                    f"元件 {key} 在不同视图的 value 不一致："
                    f"{prev.get('value')!r} vs {observed.get('value')!r}",
                    rule_id,
                ))
            if isinstance(observed, dict) or prev == MISSING:
                comp_obs[key] = observed
            comp_exp[key] = expected.get("value") if isinstance(expected, dict) else None
            comp_src[key] = f"{rule_id}.details[{idx}]"

    # ---- 6. 值审批与操作推导 ----
    def _value_approved(raw: Any) -> bool:
        canon = normalize_value(raw)
        return canon is not None and canon in approved_values

    operations: List[Dict[str, Any]] = []
    seen_ops: set = set()

    def emit(op: Dict[str, Any]) -> None:
        stamp = json.dumps(op, sort_keys=True)
        if stamp not in seen_ops:
            seen_ops.add(stamp)
            operations.append(op)

    # 6a. 元件级分类：完全缺失（可新增）vs 存在（改值/改线）
    present_refs = set()
    for (ref, _pin), observed in pin_obs.items():
        if isinstance(observed, dict):
            present_refs.add(ref)
    for ref, observed in comp_obs.items():
        if isinstance(observed, dict):
            present_refs.add(ref)
    addable_refs = {
        ref: comp_exp[ref]
        for ref in comp_exp
        if ref not in present_refs
    }

    # 6b. 引脚级修复（引脚存在但接错/悬空）
    for (ref, pin), observed in pin_obs.items():
        expected = pin_exp.get((ref, pin), {})
        if isinstance(observed, dict) and observed == expected:
            continue
        if observed == MISSING:
            continue  # 缺失引脚在 6c 处理
        if expected.get("no_connect") is True or expected.get("net") is None:
            emit({"op": "mark_no_connect", "ref": ref, "pin": pin, "because": pin_src[(ref, pin)]})
        elif "net" in expected:
            emit({"op": "set_pin_net", "ref": ref, "pin": pin, "net": expected["net"],
                  "because": pin_src[(ref, pin)]})
        else:
            blockers.append(Blocker(
                "MALFORMED_FEEDBACK", f"引脚 {ref}.{pin} 的 expected 缺少 net 字段：{expected!r}",
                pin_src[(ref, pin)],
            ))

    # 6c. 完全缺失元件的重建
    for ref, raw_value in addable_refs.items():
        pins = {p: e.get("net") for (r, p), e in pin_exp.items() if r == ref}
        if raw_value is None or not pins or any(n is None for n in pins.values()):
            blockers.append(Blocker(
                "INSUFFICIENT_EVIDENCE",
                f"元件 {ref} 缺失，但反馈中没有完整的目标值/引脚映射，不足以重建",
                "pins/components expected",
            ))
            continue
        if not _value_approved(raw_value):
            blockers.append(Blocker(
                "VALUE_NOT_APPROVED",
                f"待新增元件 {ref} 的目标值 {raw_value!r} 不在公共事实包批准值列表中",
                "facts.approved_component_values",
            ))
            continue
        nets = {n for n in pins.values() if n}
        merge_blocked = False
        for a, b in merge_forbidden:
            if a in nets and b in nets:
                blockers.append(Blocker(
                    "EVIDENCE_CONFLICT",
                    f"新增元件 {ref} 会把禁止合并的网 {a}/{b} 接到同一元件",
                    "facts.protected.nets_must_not_merge",
                ))
                merge_blocked = True
                break
        if merge_blocked:
            continue
        emit({"op": "add_component", "ref": ref, "value": normalize_value(raw_value),
              "pins": dict(sorted(pins.items())), "because": "components expected"})

    # 6d. 存在元件的值修正
    for ref, observed in comp_obs.items():
        if ref in addable_refs:
            continue
        expected_value = comp_exp.get(ref)
        if observed == MISSING:
            if ref in present_refs:
                blockers.append(Blocker(
                    "INSUFFICIENT_EVIDENCE",
                    f"元件 {ref} 存在但其值在观测中缺失，无法安全推断",
                    comp_src.get(ref, ref),
                ))
            continue
        if not isinstance(observed, dict):
            blockers.append(Blocker(
                "MALFORMED_FEEDBACK",
                f"元件 {ref} 的观测值格式异常：{observed!r}",
                comp_src.get(ref, ref),
            ))
            continue
        if observed.get("value") == expected_value:
            continue
        if not _value_approved(expected_value):
            blockers.append(Blocker(
                "VALUE_NOT_APPROVED",
                f"元件 {ref} 的目标值 {expected_value!r} 不在公共事实包批准值列表中",
                "facts.approved_component_values",
            ))
            continue
        emit({"op": "set_component_value", "ref": ref, "value": normalize_value(expected_value),
              "because": comp_src[ref]})

    # 6e. 既不属于"可新增元件"、观测又缺失的引脚：现有操作无法安全表达，fail-closed
    for (ref, pin), observed in pin_obs.items():
        if observed == MISSING and ref not in addable_refs:
            blockers.append(Blocker(
                "INSUFFICIENT_EVIDENCE",
                f"引脚 {ref}.{pin} 在观测中缺失，且 {ref} 不是可新增的独立元件"
                f"（公开合同未声明其元件值），无法用现有操作安全表达",
                pin_src[(ref, pin)],
            ))

    if blockers:
        return _consolidated_refusal(blockers, unhandled, failing_rule_ids)

    # ---- 7. pcb 视图不一致 -> 只记边界说明（方案：PCB 未同步必须显示边界）----
    pcb_noted = False
    for rule_id, idx, view, section, key, expected, observed in entries:
        if view == "pcb" and observed != MISSING and expected != observed and not pcb_noted:
            notes.append(
                "pcb 视图与目标存在不一致；本次修复范围仅限原理图连接/参数，PCB 需另行同步，"
                "不得据此宣称整板通过"
            )
            pcb_noted = True

    rules_addressed = sorted({e[0] for e in entries})
    if not operations:
        notes.append("存在失败规则，但可派生的硬件修复操作为空（可能仅 PCB 未同步）")
        return Proposal(
            decision="NO_CHANGE_NEEDED", operations=[],
            rules_addressed=rules_addressed, notes=notes,
        )
    return Proposal(
        decision="PROPOSE_REPAIR", operations=operations,
        rules_addressed=rules_addressed, notes=notes,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_json_file(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise BaselineInputError(f"文件不存在：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BaselineInputError(f"JSON 解析失败 {path}：{exc}") from exc


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Y4 实验 D 组固定规则基线（只吃公开输入，fail-closed）")
    parser.add_argument("--feedback", required=True, help="检查器 findings 报告 JSON 路径")
    parser.add_argument("--facts", required=True, help="公共事实包 JSON 路径")
    parser.add_argument("--out", required=True, help="修复提案输出 JSON 路径")
    args = parser.parse_args(argv)

    try:
        feedback = _load_json_file(Path(args.feedback))
        facts = _load_json_file(Path(args.facts))
        proposal = build_proposal(feedback, facts)
    except BaselineInputError as exc:
        print(f"[baseline] 输入错误：{exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            proposal.to_dict(sha256_of_text(feedback), sha256_of_text(facts)),
            ensure_ascii=False, indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"[baseline] decision={proposal.decision} operations={len(proposal.operations)} "
          f"rules={','.join(proposal.rules_addressed) or '-'}")
    if proposal.refusal:
        print(f"[baseline] refusal={proposal.refusal['reason_code']} gaps={len(proposal.refusal['gaps'])}")
    print(f"[baseline] 提案已写入 {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
