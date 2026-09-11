"""AEDL Y4 · D 组固定规则基线 v0.4.0（PublicContext → 冻结 Proposal）。

本版是针对 PR #60 review（Yenefa，2026-09-11）三条意见的对齐重写：

1) 接口对齐冻结 C1（不再自造协议）
   - 输入 = PublicContext（src/repair/patch_schema_v1.json 的 PublicContext，
     由 tools/repair_pipeline.make_public_context 产出）。
   - 输出 = 冻结 Proposal：decision ∈ {PATCH, REFUSE}；操作只允许公开三原语
     {delete_object, add_net_label, place_component}；头部五字段
     (schema_version/context_id/target/base_source_sha256/decision) 一律取自
     PublicContext 或冻结枚举。v0.3 的 PROPOSE_REPAIR / set_pin_net /
     mark_no_connect / add_component / set_component_value 全部废除。

2) 输入协议对齐 Issue #56 批准架构（不再开旁路）
   PublicContext → AI C / Script D → C1 parse_proposal → Raw Result Package。
   D 与 C 消费完全相同的公共输入；本脚本不再读取 schematic_semantics 的
   findings 报告（expected/observed 行），也不再使用 aedl.public-facts.draft-0.1。

3) 信息级别不写死（顺序归位）
   修复目标只来自 PublicContext.public_facts。其形状
   （aedl.y4-public-facts.draft-0.1）是 D 对 y4-public.v2 冻结包的需求草案，
   最终内容与信息级别由 A2-Y / Percy 冻结；public_facts 未提供的事实一律
   REFUSE 并列出 missing_fact_ids，绝不从任何 expected/答案反推。
   研究 claim 的措辞由 Owner 决定。

确定性规则（全部机械推导，无 AI、无案例编号分支）：
   R1 引脚重定向：锚点观测 == 目标网 → 已满足（不发操作）；观测悬空 →
       add_net_label；观测为其他网 → 必须有配套 deletion_target，先
       delete_object 再 add_net_label，缺 → REFUSE(PUBLIC_INPUT_INSUFFICIENT)。
   R2 新增元件：designator 观测缺失 → place_component + 逐引脚
       add_net_label；已存在但值不同 → REFUSE(NOT_EXPRESSION_IN_PUBLIC_OPS)
       （公开三原语无法表达改值）。
   R3 保护锚点：任何将被标注的锚点 ∈ protected_anchors →
       REFUSE(PUBLIC_INPUT_CONFLICT)。
   R4 跨视图一致性：intent/netlist/pcb 对同一锚点或元件的观测不一致 →
       REFUSE(OBSERVATION_CONFLICT)。
   R5 fail-closed：facts_status=insufficient → REFUSE(PUBLIC_INPUT_INSUFFICIENT，
       missing_fact_ids=facts_gaps)；facts 形状/类型非法（未知键、浮点、
       重复 id 等）→ REFUSE(PUBLIC_INPUT_MALFORMED)；操作数 > 8 或诊断 > 16 →
       REFUSE(OPERATION_LIMIT_EXCEEDED)；无操作可发 → REFUSE(ALREADY_SATISFIED)。

边界：D 只产提案，不执行写入（akcli 执行通道属 B2）；固件不可用公开三原语
修补，任何固件层诉求只能经 required_human_decision 升级人工。提案合法性由
A2 的 C1 parse_proposal 把关（tests/test_repair_baseline.py 用真实 C1 验证
每份输出）。

用法
----
    py -3 tools/repair_baseline.py --context public_context.json --out proposal.json

退出码：0 = 已产出合法 Proposal（PATCH/REFUSE 均算）；2 = 输入不合法。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TOOL_VERSION = "0.4.0"
PROPOSAL_SCHEMA_VERSION = 1
FACTS_SCHEMA = "aedl.y4-public-facts.draft-0.1"

OBSERVATION_VIEWS = ("intent", "netlist", "pcb")

# 冻结 Proposal 常量（与 tools/repair_pipeline.py 保持一致，独立声明以保持
# D 不依赖宿主代码）
DECISION_PATCH = "PATCH"
DECISION_REFUSE = "REFUSE"
OP_DELETE_OBJECT = "delete_object"
OP_ADD_NET_LABEL = "add_net_label"
OP_PLACE_COMPONENT = "place_component"
PUBLIC_LIB_IDS = ("Device:R", "Device:C")
MIN_OPS, MAX_OPS = 1, 8
MAX_DIAGNOSIS = 16
MAX_TEXT_CHARS = 2048

CONTEXT_FIELDS = (
    "schema_version",
    "context_id",
    "target",
    "base_source_sha256",
    "current_observation",
    "public_facts",
    "generic_op_schema",
    "limits",
)

FACTS_TOP_KEYS = (
    "facts_schema",
    "facts_status",
    "facts_gaps",
    "pin_targets",
    "component_targets",
    "deletion_targets",
    "protected_anchors",
)
PIN_TARGET_KEYS = ("id", "anchor", "net")
COMPONENT_TARGET_KEYS = (
    "id",
    "designator",
    "lib_id",
    "value",
    "footprint",
    "pin_nets",
    "placement",
)
DELETION_TARGET_KEYS = ("id", "uuid", "anchor")
PLACEMENT_KEYS = ("x_mil", "y_mil")

# 拒绝原因码（Proposal 的 reason_code 是自由有界文本；这里固定一组并声明
# 优先级，同例多问题时取最严重的一类）
PRIORITY = (
    "PUBLIC_INPUT_MALFORMED",
    "PUBLIC_INPUT_CONFLICT",
    "OBSERVATION_CONFLICT",
    "PUBLIC_INPUT_INSUFFICIENT",
    "NOT_EXPRESSION_IN_PUBLIC_OPS",
    "OPERATION_LIMIT_EXCEEDED",
    "ALREADY_SATISFIED",
)

REQUIRED_HUMAN_DECISION = (
    "A2-Y/Percy must complete the frozen public package or authorize more "
    "public ops; arm D will not guess."
)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")
_ANCHOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z0-9_]+$")
_DESIGNATOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_PIN_KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")
_TEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]+$")


class BaselineInputError(Exception):
    """输入文件缺失/非法（CLI 退出码 2）。"""


class _FactsProblem(Exception):
    """携带优先级码的拒绝条件，由引擎统一择优。"""

    def __init__(self, reason_code: str, missing: List[str], explanation: str):
        super().__init__(explanation)
        self.reason_code = reason_code
        self.missing = missing
        self.explanation = explanation


# ---------------------------------------------------------------------------
# 严格 JSON 载入（拒绝 BOM / 重复键 / NaN / 浮点，向 C1 的 canonical 约定看齐）
# ---------------------------------------------------------------------------


def _pairs_hook(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BaselineInputError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise BaselineInputError(f"NaN/Infinity is not allowed: {name}")


def _reject_floats(value: Any, path: str) -> None:
    if isinstance(value, float):
        raise BaselineInputError(f"float is not allowed at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


def load_context(path: Path) -> Dict[str, Any]:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise BaselineInputError(f"cannot read context file: {exc}") from exc
    if raw.startswith(b"\xef\xbb\xbf"):
        raise BaselineInputError("context file must not start with a BOM")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_hook,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineInputError(f"context is not valid strict JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise BaselineInputError("context must be a JSON object")
    _reject_floats(document, "$")
    _validate_context_shape(document)
    return document


def _validate_context_shape(context: Dict[str, Any]) -> None:
    missing = [key for key in CONTEXT_FIELDS if key not in context]
    if missing:
        raise BaselineInputError(f"context missing fields: {missing}")
    extra = [key for key in context if key not in CONTEXT_FIELDS]
    if extra:
        raise BaselineInputError(f"context has unknown fields: {extra}")
    version = context["schema_version"]
    if isinstance(version, bool) or version != PROPOSAL_SCHEMA_VERSION:
        raise BaselineInputError("context schema_version must be 1")
    if not _ID_RE.match(str(context["context_id"])):
        raise BaselineInputError("context_id is not a valid identifier")
    if not _PATH_RE.match(str(context["target"])):
        raise BaselineInputError("context target is not a valid candidate path")
    if not _SHA_RE.match(str(context["base_source_sha256"])):
        raise BaselineInputError("context base_source_sha256 is not a sha256 hex")
    if context["current_observation"] is not None and not isinstance(
        context["current_observation"], dict
    ):
        raise BaselineInputError("current_observation must be an object or null")
    if context["public_facts"] is not None and not isinstance(
        context["public_facts"], dict
    ):
        raise BaselineInputError("public_facts must be an object or null")
    for key in ("generic_op_schema", "limits"):
        if not isinstance(context[key], dict):
            raise BaselineInputError(f"{key} must be an object")


# ---------------------------------------------------------------------------
# public_facts 校验（closed set，任何越界 → PUBLIC_INPUT_MALFORMED）
# ---------------------------------------------------------------------------


def _bad_facts(explanation: str) -> _FactsProblem:
    return _FactsProblem("PUBLIC_INPUT_MALFORMED", [], explanation)


def _text_field(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _TEXT_RE.match(value):
        raise _bad_facts(f"{where} must be non-empty text without control chars")
    if len(value) > MAX_TEXT_CHARS:
        raise _bad_facts(f"{where} exceeds {MAX_TEXT_CHARS} chars")
    return value


def _int_field(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _bad_facts(f"{where} must be an integer")
    return value


def _id_field(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise _bad_facts(f"{where} must match identifier pattern")
    return value


def _anchor_field(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _ANCHOR_RE.match(value):
        raise _bad_facts(f"{where} must be a REF.PIN anchor")
    return value


def _items(value: Any, where: str) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        raise _bad_facts(f"{where} must be an array")
    for item in value:
        if not isinstance(item, dict):
            raise _bad_facts(f"{where} entries must be objects")
    return value


def _closed(item: Dict[str, Any], keys: Tuple[str, ...], where: str) -> None:
    for key in keys:
        if key not in item:
            raise _bad_facts(f"{where} missing {key!r}")
    for key in item:
        if key not in keys:
            raise _bad_facts(f"{where} has unknown field {key!r}")


def validate_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    """校验 public_facts（draft-0.1 需求草案），返回规范化后的结构。"""
    for key in FACTS_TOP_KEYS:
        if key not in facts:
            raise _bad_facts(f"public_facts missing {key!r}")
    for key in facts:
        if key not in FACTS_TOP_KEYS:
            raise _bad_facts(f"public_facts has unknown field {key!r}")

    if facts["facts_schema"] != FACTS_SCHEMA:
        raise _bad_facts(f"facts_schema must be {FACTS_SCHEMA!r}")
    status = facts["facts_status"]
    if status not in ("complete", "insufficient"):
        raise _bad_facts('facts_status must be "complete" or "insufficient"')

    gaps_raw = facts["facts_gaps"]
    if not isinstance(gaps_raw, list):
        raise _bad_facts("facts_gaps must be an array")
    gap_ids = [_id_field(item, f"facts_gaps[{i}]") for i, item in enumerate(gaps_raw)]
    if len(set(gap_ids)) != len(gap_ids):
        raise _bad_facts("facts_gaps has duplicate ids")

    protected_raw = facts["protected_anchors"]
    if not isinstance(protected_raw, list):
        raise _bad_facts("protected_anchors must be an array")
    protected_anchors = [
        _anchor_field(item, f"protected_anchors[{i}]")
        for i, item in enumerate(protected_raw)
    ]
    if len(set(protected_anchors)) != len(protected_anchors):
        raise _bad_facts("protected_anchors has duplicates")

    pin_targets = []
    for index, item in enumerate(_items(facts["pin_targets"], "pin_targets")):
        where = f"pin_targets[{index}]"
        _closed(item, PIN_TARGET_KEYS, where)
        pin_targets.append(
            {
                "id": _id_field(item["id"], f"{where}.id"),
                "anchor": _anchor_field(item["anchor"], f"{where}.anchor"),
                "net": _text_field(item["net"], f"{where}.net"),
            }
        )

    component_targets = []
    for index, item in enumerate(
        _items(facts["component_targets"], "component_targets")
    ):
        where = f"component_targets[{index}]"
        _closed(item, COMPONENT_TARGET_KEYS, where)
        lib_id = item["lib_id"]
        if lib_id not in PUBLIC_LIB_IDS:
            raise _bad_facts(f"{where}.lib_id must be one of {PUBLIC_LIB_IDS}")
        designator = item["designator"]
        if not isinstance(designator, str) or not _DESIGNATOR_RE.match(designator):
            raise _bad_facts(f"{where}.designator is not a valid designator")
        placement = item["placement"]
        if not isinstance(placement, dict):
            raise _bad_facts(f"{where}.placement must be an object")
        _closed(placement, PLACEMENT_KEYS, f"{where}.placement")
        pin_nets = item["pin_nets"]
        if not isinstance(pin_nets, dict) or not pin_nets:
            raise _bad_facts(f"{where}.pin_nets must be a non-empty object")
        normalized_pins: Dict[str, str] = {}
        for pin_key, pin_net in pin_nets.items():
            if not isinstance(pin_key, str) or not _PIN_KEY_RE.match(pin_key):
                raise _bad_facts(f"{where}.pin_nets key {pin_key!r} is not a pin")
            normalized_pins[pin_key] = _text_field(pin_net, f"{where}.pin_nets.{pin_key}")
        component_targets.append(
            {
                "id": _id_field(item["id"], f"{where}.id"),
                "designator": designator,
                "lib_id": lib_id,
                "value": _text_field(item["value"], f"{where}.value"),
                "footprint": _text_field(item["footprint"], f"{where}.footprint"),
                "pin_nets": normalized_pins,
                "x_mil": _int_field(placement["x_mil"], f"{where}.placement.x_mil"),
                "y_mil": _int_field(placement["y_mil"], f"{where}.placement.y_mil"),
            }
        )
        if component_targets[-1]["designator"] is None:
            raise _bad_facts(f"{where}.designator is not a valid designator")

    deletion_targets = []
    for index, item in enumerate(_items(facts["deletion_targets"], "deletion_targets")):
        where = f"deletion_targets[{index}]"
        _closed(item, DELETION_TARGET_KEYS, where)
        deletion_targets.append(
            {
                "id": _id_field(item["id"], f"{where}.id"),
                "uuid": _id_field(item["uuid"], f"{where}.uuid"),
                "anchor": _anchor_field(item["anchor"], f"{where}.anchor"),
            }
        )

    all_ids = (
        [entry["id"] for entry in pin_targets]
        + [entry["id"] for entry in component_targets]
        + [entry["id"] for entry in deletion_targets]
        + gap_ids
    )
    if len(set(all_ids)) != len(all_ids):
        raise _bad_facts("fact ids are not unique across public_facts")

    return {
        "status": status,
        "gaps": gap_ids,
        "protected": set(protected_anchors),
        "pins": sorted(pin_targets, key=lambda entry: entry["anchor"]),
        "components": sorted(component_targets, key=lambda entry: entry["designator"]),
        "deletions": sorted(deletion_targets, key=lambda entry: entry["uuid"]),
    }


# ---------------------------------------------------------------------------
# 观测访问（只读 current_observation，绝不读取 expected）
# ---------------------------------------------------------------------------


def observed_net(views: Dict[str, Any], anchor: str) -> Optional[str]:
    """返回锚点的跨视图一致观测网；不一致抛 OBSERVATION_CONFLICT，
    全视图缺失或形状不可读抛 PUBLIC_INPUT_INSUFFICIENT。"""
    observed: Optional[str] = None
    seen = False
    for view in OBSERVATION_VIEWS:
        section = views.get(view)
        if not isinstance(section, dict):
            continue
        pins = section.get("pins")
        if not isinstance(pins, dict):
            continue
        if anchor not in pins:
            continue
        entry = pins[anchor]
        net = entry.get("net") if isinstance(entry, dict) else None
        if net is not None and not isinstance(net, str):
            raise _FactsProblem(
                "PUBLIC_INPUT_INSUFFICIENT",
                [f"observation-{anchor.replace('.', '-')}"],
                f"anchor {anchor} in view {view} has unreadable net entry",
            )
        if seen and net != observed:
            raise _FactsProblem(
                "OBSERVATION_CONFLICT",
                [],
                f"anchor {anchor} disagrees across views (net values differ)",
            )
        observed, seen = net, True
    if not seen:
        raise _FactsProblem(
            "PUBLIC_INPUT_INSUFFICIENT",
            [f"observation-{anchor.replace('.', '-')}"],
            f"anchor {anchor} is absent from all observation views",
        )
    return observed


def observed_component(views: Dict[str, Any], designator: str) -> Optional[str]:
    exists_seen: Optional[bool] = None
    value: Optional[str] = None
    for view in OBSERVATION_VIEWS:
        section = views.get(view)
        if not isinstance(section, dict):
            continue
        components = section.get("components")
        if not isinstance(components, dict):
            continue
        here = designator in components
        entry = components.get(designator) if here else None
        here_value = entry.get("value") if isinstance(entry, dict) else None
        if here and here_value is not None and not isinstance(here_value, str):
            raise _FactsProblem(
                "PUBLIC_INPUT_INSUFFICIENT",
                [f"observation-{designator}"],
                f"component {designator} in view {view} has unreadable value",
            )
        if exists_seen is None:
            exists_seen, value = here, here_value
        elif exists_seen != here or value != here_value:
            raise _FactsProblem(
                "OBSERVATION_CONFLICT",
                [],
                f"component {designator} presence/value disagrees across views",
            )
    if exists_seen is None:
        raise _FactsProblem(
            "PUBLIC_INPUT_INSUFFICIENT",
            [f"observation-{designator}"],
            f"component {designator} cannot be observed (no component maps)",
        )
    return value if exists_seen else None


# ---------------------------------------------------------------------------
# 提案组装
# ---------------------------------------------------------------------------


def _refuse(reason_code: str, missing: List[str], explanation: str) -> Dict[str, Any]:
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "decision": DECISION_REFUSE,
        "diagnosis": [],
        "refusal": {
            "reason_code": reason_code,
            "missing_fact_ids": sorted(set(missing)),
            "explanation": explanation,
            "required_human_decision": REQUIRED_HUMAN_DECISION,
        },
    }


def _diagnose(observed_text: str, fact_ids: List[str], rationale: str) -> Dict[str, Any]:
    return {
        "rule_id": "y4-arm-d",
        "observed": observed_text,
        "fact_ids": list(fact_ids),
        "requirement_level": "MANDATORY",
        "rationale": rationale,
    }


def build_proposal(context: Dict[str, Any]) -> Dict[str, Any]:
    header = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "context_id": context["context_id"],
        "target": context["target"],
        "base_source_sha256": context["base_source_sha256"],
    }

    facts_raw = context["public_facts"]
    if facts_raw is None:
        return _complete(
            header, _refuse("PUBLIC_INPUT_INSUFFICIENT", ["public-facts"], "PublicContext carries no public_facts; arm D refuses rather than guess.")
        )
    try:
        facts = validate_facts(facts_raw)
    except _FactsProblem as problem:
        return _complete(
            header, _refuse(problem.reason_code, problem.missing, problem.explanation)
        )

    if facts["status"] == "insufficient":
        return _complete(
            header,
            _refuse(
                "PUBLIC_INPUT_INSUFFICIENT",
                facts["gaps"],
                "public package declares facts_status=insufficient; the listed gaps must be frozen before arm D can derive repairs",
            ),
        )

    # 观察文档形状 = 公开夹具 schematic-observations.v1：视图嵌在 .views 下
    views = (context["current_observation"] or {}).get("views") or {}

    try:
        ops: List[Dict[str, Any]] = []
        diagnosis: List[Dict[str, Any]] = []

        deletions_by_anchor: Dict[str, Dict[str, Any]] = {}
        for entry in facts["deletions"]:
            if entry["anchor"] in deletions_by_anchor:
                raise _bad_facts(
                    f"deletion_targets has more than one entry for anchor {entry['anchor']}"
                )
            deletions_by_anchor[entry["anchor"]] = entry

        # R1：引脚重定向
        for pin in facts["pins"]:
            anchor, net, fact_id = pin["anchor"], pin["net"], pin["id"]
            if anchor in facts["protected"]:
                raise _FactsProblem(
                    "PUBLIC_INPUT_CONFLICT",
                    [],
                    f"approved pin target {anchor} -> {net} touches protected anchor {anchor}",
                )
            observed = observed_net(views, anchor)
            observed_text = f"anchor {anchor} observed net {observed if observed is not None else 'floating'}"
            deletion = deletions_by_anchor.get(anchor)
            if observed == net:
                diagnosis.append(
                    _diagnose(observed_text, [fact_id], "observation already matches the approved target; no operation emitted")
                )
                if deletion is not None:
                    raise _FactsProblem(
                        "OBSERVATION_CONFLICT",
                        [],
                        f"deletion target for {anchor} is unnecessary: observation already matches the approved net",
                    )
                continue
            if observed is None:
                if deletion is not None:
                    raise _FactsProblem(
                        "OBSERVATION_CONFLICT",
                        [],
                        f"deletion target for {anchor} has nothing to delete: anchor is floating",
                    )
                ops.append({"op": OP_ADD_NET_LABEL, "name": net, "at": anchor})
                diagnosis.append(
                    _diagnose(observed_text, [fact_id], "floating anchor receives the approved net label (rule R1)")
                )
            else:
                if deletion is None:
                    raise _FactsProblem(
                        "PUBLIC_INPUT_INSUFFICIENT",
                        [f"deletion-{anchor.replace('.', '-')}"],
                        f"anchor {anchor} is wired to {observed}; retargeting needs a deletion_target uuid for the wrong label, which the public package does not provide",
                    )
                ops.append({"op": OP_DELETE_OBJECT, "uuid": deletion["uuid"]})
                ops.append({"op": OP_ADD_NET_LABEL, "name": net, "at": anchor})
                diagnosis.append(
                    _diagnose(observed_text, [deletion["id"], fact_id], "wrong label is deleted by approved uuid and the approved net label is added (rule R1)")
                )

        # R2：新增元件
        for comp in facts["components"]:
            designator, fact_id = comp["designator"], comp["id"]
            observed_value = observed_component(views, designator)
            if observed_value is not None:
                observed_text = f"component {designator} observed value {observed_value}"
                if observed_value == comp["value"]:
                    diagnosis.append(
                        _diagnose(observed_text, [fact_id], "component already matches the approved value; no operation emitted")
                    )
                    continue
                raise _FactsProblem(
                    "NOT_EXPRESSION_IN_PUBLIC_OPS",
                    [],
                    f"component {designator} exists with value {observed_value} but the approved value is {comp['value']}; the public op primitives cannot modify an existing component value",
                )
            ops.append(
                {
                    "op": OP_PLACE_COMPONENT,
                    "lib_id": comp["lib_id"],
                    "designator": designator,
                    "x_mil": comp["x_mil"],
                    "y_mil": comp["y_mil"],
                    "value": comp["value"],
                    "footprint": comp["footprint"],
                }
            )
            diagnosis.append(
                _diagnose(
                    f"component {designator} absent from observations",
                    [fact_id],
                    "approved component is placed at the host-granted coordinates (rule R2)",
                )
            )
            for pin_key in sorted(comp["pin_nets"]):
                anchor = f"{designator}.{pin_key}"
                if anchor in facts["protected"]:
                    raise _FactsProblem(
                        "PUBLIC_INPUT_CONFLICT",
                        [],
                        f"approved pin label {anchor} touches protected anchor",
                    )
                ops.append(
                    {"op": OP_ADD_NET_LABEL, "name": comp["pin_nets"][pin_key], "at": anchor}
                )
                diagnosis.append(
                    _diagnose(
                        f"anchor {anchor} of newly placed {designator}",
                        [fact_id],
                        "pin of newly placed component receives its approved net label (rule R2)",
                    )
                )
    except _FactsProblem as problem:
        return _complete(
            header, _refuse(problem.reason_code, problem.missing, problem.explanation)
        )

    if not ops:
        return _complete(
            header,
            _refuse(
                "ALREADY_SATISFIED",
                [],
                "all approved targets already match the observation; the frozen schema has no empty patch, so arm D refuses with no change",
            ),
        )
    if len(ops) > MAX_OPS:
        return _complete(
            header,
            _refuse(
                "OPERATION_LIMIT_EXCEEDED",
                [],
                f"derived {len(ops)} operations exceeds the frozen limit of {MAX_OPS}",
            ),
        )
    if len(diagnosis) > MAX_DIAGNOSIS:
        return _complete(
            header,
            _refuse(
                "OPERATION_LIMIT_EXCEEDED",
                [],
                f"derived {len(diagnosis)} diagnosis entries exceeds the frozen limit of {MAX_DIAGNOSIS}",
            ),
        )

    proposal = dict(header)
    proposal["decision"] = DECISION_PATCH
    proposal["diagnosis"] = diagnosis
    proposal["oplist"] = {
        "protocol_version": 2,
        "target_format": "kicad",
        "ops": ops,
    }
    return _complete(header, proposal)


def _complete(header: Dict[str, Any], proposal: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in header.items():
        proposal[key] = value
    if proposal["decision"] == DECISION_PATCH:
        proposal.pop("refusal", None)
    else:
        proposal.pop("oplist", None)
    proposal["diagnosis"] = proposal.get("diagnosis") or []
    return proposal


def render(proposal: Dict[str, Any]) -> bytes:
    return (
        json.dumps(
            proposal,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AEDL Y4 arm-D deterministic baseline")
    parser.add_argument("--context", required=True, help="PublicContext JSON (C1 shape)")
    parser.add_argument("--out", required=True, help="output proposal JSON path")
    args = parser.parse_args(argv)
    try:
        context = load_context(Path(args.context))
        proposal = build_proposal(context)
    except BaselineInputError as exc:
        print(f"baseline: invalid input: {exc}", file=sys.stderr)
        return 2
    Path(args.out).write_bytes(render(proposal))
    print(f"baseline: wrote {proposal['decision']} proposal to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
