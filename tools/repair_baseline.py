"""AEDL Y4 · D 组固定规则基线 v0.5.0（真实 y4-public.v3 包 → 冻结 Proposal）。

本版针对 PR #60 第二轮 review（Yenefa，2026-09-11，CHANGES_REQUESTED）重写：
v0.4 被认定"第一刀真改了，第二/三刀是换壳"——本版直接消费真实冻结包。

对齐的真实协议（来源 origin/feat/gh56-y4-dry-harness，PR #61，2026-09-11 核对）：
- 包形状 schema_version = "y4-public.v3"（tools/y4_dry_runner.build_package）：
  封闭字段 {schema_version, experiment_version, case_public_id, source_utf8,
  observation_binding, public_context, public_context_sha256, budget,
  instruction, exposure_fields, placement_grants}。
- D 是 adapter(request_bytes) -> bytes（tools.y4_dry_runner.run_adapter 契约）：
  输入即整个包的原始字节（C/D 同字节），propose_bytes() 即该适配器。
- current_observation 真实形状 = kicad_netlist_current.v1
  （notes/y4/produce_current_observations.py）：{observation_type, components
  [{ref,value,footprint,lib,part}], nets [{code,name,nodes[{ref,pin,...}]}],
  coverage}；**引脚不出现在任何 net 的 nodes 里 = 无已断言的连接（悬空）**。
- public_facts 是**数组**（PBF/BB 事实清单，位于 public_context 内；空数组 =
  未供给事实），不是对象；类型不符产出合法 REFUSE，不再 exit 2。
- placement_grants：宿主授权放置槽位列表 [{x_mil,y_mil}]；runner 对
  place_component 逐坐标做成员性检查（collect_result binding 检查）。
  **D 的坐标只从 grants 取**：按包内既定顺序取第一个未占用槽（生成器已按
  (y,x) 规范排序）——成员性由构造保证，无需 D 自查。坐标来源与选择规则在
  此声明，最终语义归 A2-Y/Percy 冻结（放行前置 #3）。
- budget（context.limits）：max_ops 1..8 是操作预算上限，D 从 limits.max_ops
  读取，不再硬编码。

对第二轮 review 各点的回应：
1. 冻结 C1 合同（已认可）：发射器原样保留——头部五字段取自 public_context，
   decision ∈ {PATCH, REFUSE}，仅公开三原语。
2. 同一公共输入：D 的输入就是 runner 冻结出的 y4-public.v3 包本身；
   观察按 kicad_netlist_current.v1 读，facts 按数组消费。有效包一律产出
   **合法 Proposal（含 REFUSE）**，不再 exit 2；exit 2 仅保留给文件级/包级
   结构损坏（非 JSON、缺字段、schema_version 不符、context 头非法）。
3. 信息级别：D 不自带事实草案对象，也不复刻五个计分案例。D 只声明一个
   **可解释事实文法**（closed grammar，见 FACT_KINDS），对包内事实数组逐条
   尝试解释：能解释的派生操作；不能解释的逐 id 记入拒绝（UNINTERPRETABLE_
   FACTS），绝不猜测散文含义。事实形态与信息级别的最终冻结归 A2-Y/Percy
   （放行前置 #1）；文法外事实在冻结前会使 D 拒绝，这是 fail-closed 的
   如实表现，不是绕过。
4. 其他：死代码已删；max_ops 从 limits 读；文档版本改 v3；坐标只从 grants
   取；测试改用中性合成数据（不复刻五案例）+ 真实 runner 集成测试
   （PR #61 合入后自动启用）。

可解释事实文法（FACT_KINDS，需求声明，待 A2-Y/Percy 冻结确认）：
- connect_pin   {id, kind, anchor: REF.PIN, net}      引脚接线路由
- delete_object {id, kind, uuid, anchor: REF.PIN}     删除错误标签/导线
- place_component {id, kind, designator, lib_id, value, footprint, pin_nets}
  （lib_id ∈ {Device:R, Device:C}；坐标自动取自 grants，不在事实里写死）

确定性规则（事实按数组顺序处理，首个问题即终止并拒绝）：
R1 connect_pin：观测 == 目标网 → 已满足；悬空 → add_net_label；
   接了别的网 → 必须有同锚点 delete_object 事实（先删后标），缺 → 拒绝。
R2 place_component：观测中已存在同 designator → 值相同则满足、值不同则
   NOT_EXPRESSION_IN_PUBLIC_OPS（公开原语无法改值）；不存在 → place_component
   （坐标取 grants 顺序槽）+ 逐引脚 add_net_label。
R3 同一锚点出现两条 connect_pin（或同一 designator 两条 place_component）
   → PUBLIC_INPUT_CONFLICT（无法确定性地派生唯一修复）。
R4 孤儿删除：delete_object 事实的锚点没有任何 connect_pin 引用 →
   PUBLIC_INPUT_INSUFFICIENT（D 只为改接而删，不做投机删除）。
R5 引脚出现在多个网 → OBSERVATION_CONFLICT。
R6 操作数 > limits.max_ops（或 >8 绝对上限）→ OPERATION_LIMIT_EXCEEDED。
R7 空事实数组 / 文法外事实 / 形状非法 / facts 类型非数组 / grants 非法 /
   槽位耗尽 → 对应拒绝码，全部产出合法 REFUSE Proposal。

用法（D 侧 adapter 的 CLI 形态）
----
    py -3 tools/repair_baseline.py --package Y4-001.json --out proposal.json

退出码：0 = 已产出合法 Proposal（PATCH/REFUSE 均算）；2 = 包文件级结构损坏。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TOOL_VERSION = "0.5.0"

PACKAGE_VERSION = "y4-public.v3"
PROPOSAL_SCHEMA_VERSION = 1
MAX_OPS_CONTRACT_CEILING = 8
MAX_GRANT_SLOTS = 2048
MAX_DIAGNOSIS = 16

PACKAGE_KEYS = (
    "schema_version",
    "experiment_version",
    "case_public_id",
    "source_utf8",
    "observation_binding",
    "public_context",
    "public_context_sha256",
    "budget",
    "instruction",
    "exposure_fields",
    "placement_grants",
)
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
BUDGET_KEYS = ("max_ops", "max_request_bytes", "max_output_tokens", "timeout_ms")
GRANT_SLOT_KEYS = ("x_mil", "y_mil")

OBSERVATION_TYPE = "kicad_netlist_current.v1"

DECISION_PATCH = "PATCH"
DECISION_REFUSE = "REFUSE"
OP_DELETE_OBJECT = "delete_object"
OP_ADD_NET_LABEL = "add_net_label"
OP_PLACE_COMPONENT = "place_component"
PUBLIC_LIB_IDS = ("Device:R", "Device:C")

# 可解释事实文法：kind -> 封闭字段集（需求声明，最终形状归 A2-Y/Percy 冻结）
FACT_CONNECT_PIN = "connect_pin"
FACT_DELETE_OBJECT = "delete_object"
FACT_PLACE_COMPONENT = "place_component"
FACT_KINDS: Dict[str, Tuple[str, ...]] = {
    FACT_CONNECT_PIN: ("id", "kind", "anchor", "net"),
    FACT_DELETE_OBJECT: ("id", "kind", "uuid", "anchor"),
    FACT_PLACE_COMPONENT: (
        "id",
        "kind",
        "designator",
        "lib_id",
        "value",
        "footprint",
        "pin_nets",
    ),
}

REQUIRED_HUMAN_DECISION = (
    "A2-Y/Percy must freeze the public facts grammar/level and complete the "
    "package; arm D will not guess."
)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")
_ANCHOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z0-9_]+$")
_DESIGNATOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_PIN_KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,16}$")
_TEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]+$")


class BaselineInputError(Exception):
    """包文件级结构损坏（CLI 退出码 2）：无法产出任何绑定 context 的 Proposal。"""


class _Problem(Exception):
    """可绑定的拒绝条件：产出合法 REFUSE Proposal（退出码 0）。"""

    def __init__(self, reason_code: str, missing: List[str], explanation: str):
        super().__init__(explanation)
        self.reason_code = reason_code
        self.missing = missing
        self.explanation = explanation


# ---------------------------------------------------------------------------
# 严格 JSON 载入（拒绝 BOM / 重复键 / NaN；允许 float 值——与宿主
# load_json_strict 行为一致，避免对真实包误判；仅在需要整数处逐一校验）
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


def load_document(raw: bytes) -> Dict[str, Any]:
    """解析并校验冻结包原始字节（D 适配器与 CLI 共用入口）。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        raise BaselineInputError("package file must not start with a BOM")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_hook,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineInputError(f"package is not valid strict JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise BaselineInputError("package must be a JSON object")
    _validate_package_shape(document)
    return document


def load_package(path: Path) -> Dict[str, Any]:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise BaselineInputError(f"cannot read package file: {exc}") from exc
    return load_document(raw)


def _validate_package_shape(package: Dict[str, Any]) -> None:
    missing = [key for key in PACKAGE_KEYS if key not in package]
    if missing:
        raise BaselineInputError(f"package missing fields: {missing}")
    extra = [key for key in package if key not in PACKAGE_KEYS]
    if extra:
        raise BaselineInputError(f"package has unknown fields: {extra}")
    if package["schema_version"] != PACKAGE_VERSION:
        raise BaselineInputError(
            f"package schema_version must be {PACKAGE_VERSION!r}, got {package['schema_version']!r}"
        )
    _validate_context(package["public_context"])


def _validate_context(context: Any) -> Dict[str, Any]:
    if not isinstance(context, dict):
        raise BaselineInputError("public_context must be an object")
    missing = [key for key in CONTEXT_FIELDS if key not in context]
    if missing:
        raise BaselineInputError(f"public_context missing fields: {missing}")
    extra = [key for key in context if key not in CONTEXT_FIELDS]
    if extra:
        raise BaselineInputError(f"public_context has unknown fields: {extra}")
    if context["schema_version"] != PROPOSAL_SCHEMA_VERSION:
        raise BaselineInputError("public_context schema_version must be 1")
    if not isinstance(context["context_id"], str) or not _ID_RE.match(context["context_id"]):
        raise BaselineInputError("context_id is not a valid identifier")
    if not isinstance(context["target"], str) or not _PATH_RE.match(context["target"]):
        raise BaselineInputError("context target is not a valid candidate path")
    # 与 C1 _candidate_path 对齐：拒绝点段与结尾点/空格段
    for segment in context["target"].split("/"):
        if segment in (".", "..") or segment.endswith(".") or segment.endswith(" "):
            raise BaselineInputError("context target has an invalid path segment")
    if not isinstance(context["base_source_sha256"], str) or not _SHA_RE.match(
        context["base_source_sha256"]
    ):
        raise BaselineInputError("context base_source_sha256 is not a sha256 hex")
    for key in ("current_observation", "generic_op_schema", "limits"):
        if not isinstance(context[key], dict):
            raise BaselineInputError(f"{key} must be an object")
    # public_facts 的类型检查放在引擎层：类型不符产出"合法 REFUSE"而不是
    # exit 2（第二轮 review 的放行要求）。此处只要求键存在（封闭字段集）。
    budget = context["limits"]
    for key in BUDGET_KEYS:
        if key not in budget:
            raise BaselineInputError(f"limits missing {key!r}")
    for key in budget:
        if key not in BUDGET_KEYS:
            raise BaselineInputError(f"limits has unknown field {key!r}")
    for key in BUDGET_KEYS:
        value = budget[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise BaselineInputError(f"limits.{key} must be a positive integer")
    if budget["max_ops"] > MAX_OPS_CONTRACT_CEILING:
        raise BaselineInputError("limits.max_ops exceeds the contract ceiling of 8")
    return context


def _validate_grants(grants: Any) -> List[Dict[str, int]]:
    """与 runner 的封闭校验一致；非法 → 可绑定拒绝（合法 REFUSE）。"""
    if not isinstance(grants, list) or not grants:
        raise _Problem(
            "PUBLIC_INPUT_MALFORMED", [], "placement_grants must be a nonempty list"
        )
    if len(grants) > MAX_GRANT_SLOTS:
        raise _Problem(
            "PUBLIC_INPUT_MALFORMED", [], "placement_grants exceeds the policy cap"
        )
    seen = set()
    slots: List[Dict[str, int]] = []
    for index, slot in enumerate(grants):
        if not isinstance(slot, dict) or set(slot) != set(GRANT_SLOT_KEYS):
            raise _Problem(
                "PUBLIC_INPUT_MALFORMED",
                [],
                f"placement_grants[{index}] must hold exactly x_mil and y_mil",
            )
        pair = (slot["x_mil"], slot["y_mil"])
        if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 1000000 for v in pair):
            raise _Problem(
                "PUBLIC_INPUT_MALFORMED",
                [],
                f"placement_grants[{index}] coordinates must be integer mil",
            )
        if pair in seen:
            raise _Problem(
                "PUBLIC_INPUT_MALFORMED", [], f"placement_grants[{index}] duplicates a slot"
            )
        seen.add(pair)
        slots.append({"x_mil": pair[0], "y_mil": pair[1]})
    return slots


# ---------------------------------------------------------------------------
# 可解释事实文法（数组逐条；文法外 → UNINTERPRETABLE_FACTS，绝不猜测）
# ---------------------------------------------------------------------------


def _bad(explanation: str) -> _Problem:
    return _Problem("PUBLIC_INPUT_MALFORMED", [], explanation)


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _TEXT_RE.match(value):
        raise _bad(f"{where} must be non-empty text without control chars")
    if len(value) > 2048:
        raise _bad(f"{where} exceeds 2048 chars")
    return value


def _ident(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise _bad(f"{where} must match identifier pattern")
    return value


def _anchor(value: Any, where: str) -> str:
    if not isinstance(value, str) or not _ANCHOR_RE.match(value):
        raise _bad(f"{where} must be a REF.PIN anchor")
    return value


def interpret_facts(facts: List[Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """解释事实数组：返回 (可解释事实列表, 文法外事实 id 列表)。

    形状非法（缺字段/多字段/值非法）立即以 PUBLIC_INPUT_MALFORMED 终止；
    文法外 kind 逐条收集，交由调用方拒绝。
    """
    interpretable: List[Dict[str, Any]] = []
    uninterpretable: List[str] = []
    for index, record in enumerate(facts):
        if not isinstance(record, dict):
            uninterpretable.append(f"fact-{index}")
            continue
        kind = record.get("kind")
        keys = FACT_KINDS.get(kind) if isinstance(kind, str) else None
        if keys is None:
            uninterpretable.append(
                _ident(record["id"], f"facts[{index}].id")
                if "id" in record and isinstance(record["id"], str) and _ID_RE.match(record["id"])
                else f"fact-{index}"
            )
            continue
        where = f"facts[{index}]"
        missing = [key for key in keys if key not in record]
        extra = [key for key in record if key not in keys]
        if missing or extra:
            raise _bad(
                f"{where} ({kind}) field mismatch: missing={missing} unknown={extra}"
            )
        fact_id = _ident(record["id"], f"{where}.id")
        entry: Dict[str, Any] = {"id": fact_id, "kind": kind}
        if kind == FACT_CONNECT_PIN:
            entry["anchor"] = _anchor(record["anchor"], f"{where}.anchor")
            entry["net"] = _text(record["net"], f"{where}.net")
        elif kind == FACT_DELETE_OBJECT:
            entry["uuid"] = _ident(record["uuid"], f"{where}.uuid")
            entry["anchor"] = _anchor(record["anchor"], f"{where}.anchor")
        elif kind == FACT_PLACE_COMPONENT:
            designator = record["designator"]
            if not isinstance(designator, str) or not _DESIGNATOR_RE.match(designator):
                raise _bad(f"{where}.designator is not a valid designator")
            entry["designator"] = designator
            if record["lib_id"] not in PUBLIC_LIB_IDS:
                raise _bad(f"{where}.lib_id must be one of {PUBLIC_LIB_IDS}")
            entry["lib_id"] = record["lib_id"]
            entry["value"] = _text(record["value"], f"{where}.value")
            entry["footprint"] = _text(record["footprint"], f"{where}.footprint")
            pin_nets = record["pin_nets"]
            if not isinstance(pin_nets, dict) or not pin_nets:
                raise _bad(f"{where}.pin_nets must be a non-empty object")
            normalized: Dict[str, str] = {}
            for pin_key, pin_net in pin_nets.items():
                if not isinstance(pin_key, str) or not _PIN_KEY_RE.match(pin_key):
                    raise _bad(f"{where}.pin_nets key {pin_key!r} is not a pin")
                normalized[pin_key] = _text(pin_net, f"{where}.pin_nets.{pin_key}")
            entry["pin_nets"] = normalized
        interpretable.append(entry)
    all_ids = [entry["id"] for entry in interpretable]
    if len(set(all_ids)) != len(all_ids):
        raise _bad("fact ids are not unique")
    return interpretable, uninterpretable


# ---------------------------------------------------------------------------
# 观测访问（kicad_netlist_current.v1）
# ---------------------------------------------------------------------------


class ObservationView:
    """netlist 观测的只读索引。引脚不在任何 net = 悬空（生产者声明的语义）。"""

    def __init__(self, observation: Dict[str, Any]):
        if observation.get("observation_type") != OBSERVATION_TYPE:
            raise _Problem(
                "PUBLIC_INPUT_MALFORMED",
                [],
                "current_observation.observation_type must be "
                f"{OBSERVATION_TYPE!r}; arm D cannot read other formats",
            )
        self.components: Dict[str, Dict[str, Any]] = {}
        raw_components = observation.get("components")
        if not isinstance(raw_components, list):
            raise _Problem("PUBLIC_INPUT_MALFORMED", [], "components must be an array")
        for index, comp in enumerate(raw_components):
            if not isinstance(comp, dict) or not isinstance(comp.get("ref"), str):
                raise _Problem(
                    "PUBLIC_INPUT_MALFORMED", [], f"components[{index}] is malformed"
                )
            self.components[comp["ref"]] = comp
        self.pin_net: Dict[Tuple[str, str], str] = {}
        raw_nets = observation.get("nets")
        if not isinstance(raw_nets, list):
            raise _Problem("PUBLIC_INPUT_MALFORMED", [], "nets must be an array")
        for net_index, net in enumerate(raw_nets):
            if not isinstance(net, dict) or not isinstance(net.get("name"), str):
                raise _Problem(
                    "PUBLIC_INPUT_MALFORMED", [], f"nets[{net_index}] is malformed"
                )
            nodes = net.get("nodes")
            if not isinstance(nodes, list):
                raise _Problem(
                    "PUBLIC_INPUT_MALFORMED", [], f"nets[{net_index}].nodes must be an array"
                )
            for node in nodes:
                if not isinstance(node, dict):
                    raise _Problem(
                        "PUBLIC_INPUT_MALFORMED", [], f"nets[{net_index}] node malformed"
                    )
                stamp = (node.get("ref"), node.get("pin"))
                if not isinstance(stamp[0], str) or not isinstance(stamp[1], str):
                    raise _Problem(
                        "PUBLIC_INPUT_MALFORMED",
                        [],
                        f"nets[{net_index}] node ref/pin must be strings",
                    )
                if stamp in self.pin_net and self.pin_net[stamp] != net["name"]:
                    raise _Problem(
                        "OBSERVATION_CONFLICT",
                        [],
                        f"pin {stamp[0]}.{stamp[1]} appears in multiple nets "
                        f"({self.pin_net[stamp]} and {net['name']})",
                    )
                self.pin_net[stamp] = net["name"]

    def net_of(self, ref: str, pin: str) -> Optional[str]:
        return self.pin_net.get((ref, pin))

    def component(self, ref: str) -> Optional[Dict[str, Any]]:
        return self.components.get(ref)


# ---------------------------------------------------------------------------
# 提案组装（发射器与 v0.4 相同：冻结五字段 + PATCH/REFUSE + 三原语）
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


def _finish(header: Dict[str, Any], proposal: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in header.items():
        proposal[key] = value
    if proposal["decision"] == DECISION_PATCH:
        proposal.pop("refusal", None)
    else:
        proposal.pop("oplist", None)
    proposal["diagnosis"] = proposal.get("diagnosis") or []
    return proposal


def build_proposal(package: Dict[str, Any]) -> Dict[str, Any]:
    context = package["public_context"]
    header = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "context_id": context["context_id"],
        "target": context["target"],
        "base_source_sha256": context["base_source_sha256"],
    }
    max_ops = context["limits"]["max_ops"]
    try:
        # grants / facts / 观测的一切不兼容都以"合法 REFUSE"表达（退出码 0）；
        # exit 2 只保留给包文件级结构损坏（load_document 层）。
        grants = _validate_grants(package["placement_grants"])
        facts = context["public_facts"]
        if not isinstance(facts, list):
            raise _Problem(
                "PUBLIC_INPUT_MALFORMED",
                [],
                "public_facts must be an array (empty means no supplied facts); "
                "arm D consumes the frozen y4-public.v3 shape only",
            )
        view = ObservationView(context["current_observation"])
        if not facts:
            return _finish(
                header,
                _refuse(
                    "PUBLIC_INPUT_INSUFFICIENT",
                    ["public-facts"],
                    "public_facts is empty (no facts supplied); arm D has no "
                    "approved repair targets and refuses rather than guess",
                ),
            )
        interpretable, uninterpretable = interpret_facts(facts)
        if uninterpretable:
            return _finish(
                header,
                _refuse(
                    "UNINTERPRETABLE_FACTS",
                    uninterpretable,
                    "these approved fact records are outside arm D's declared "
                    "grammar (connect_pin/delete_object/place_component); the "
                    "facts grammar freeze is pending with A2-Y/Percy",
                ),
            )

        ops: List[Dict[str, Any]] = []
        diagnosis: List[Dict[str, Any]] = []
        used_slots = 0
        deletions_by_anchor: Dict[str, Dict[str, Any]] = {}
        connect_seen: Dict[str, str] = {}
        place_seen: set = set()
        retargeted_anchors: set = set()
        for fact in interpretable:
            if fact["kind"] == FACT_DELETE_OBJECT:
                if fact["anchor"] in deletions_by_anchor:
                    raise _bad(
                        f"more than one delete_object fact for anchor {fact['anchor']}"
                    )
                deletions_by_anchor[fact["anchor"]] = fact

        def take_slot() -> Dict[str, int]:
            nonlocal used_slots
            if used_slots >= len(grants):
                raise _Problem(
                    "PLACEMENT_CAPACITY_EXHAUSTED",
                    [],
                    "all placement_grants slots are used; no slot left for the "
                    "next place_component (D takes slots in package order)",
                )
            slot = grants[used_slots]
            used_slots += 1
            return slot

        # R1：connect_pin（按数组顺序）
        for fact in interpretable:
            if fact["kind"] != FACT_CONNECT_PIN:
                continue
            anchor = fact["anchor"]
            if anchor in connect_seen:
                raise _Problem(
                    "PUBLIC_INPUT_CONFLICT",
                    [],
                    f"two connect_pin facts target anchor {anchor} "
                    f"({connect_seen[anchor]!r} and {fact['net']!r}); arm D cannot "
                    "derive a deterministic repair",
                )
            connect_seen[anchor] = fact["net"]
            ref, _, pin = anchor.partition(".")
            if ref not in view.components:
                raise _Problem(
                    "PUBLIC_INPUT_INSUFFICIENT",
                    [f"observation-{anchor.replace('.', '-')}"],
                    f"anchor {anchor} references unknown component {ref}",
                )
            observed = view.net_of(ref, pin)
            target_net = fact["net"]
            observed_text = (
                f"pin {anchor} on net {observed}"
                if observed is not None
                else f"pin {anchor} floating (absent from all nets)"
            )
            deletion = deletions_by_anchor.get(anchor)
            if observed == target_net:
                diagnosis.append(
                    _diagnose(
                        observed_text,
                        [fact["id"]],
                        "observation already matches the approved target; no operation",
                    )
                )
                if deletion is not None:
                    raise _Problem(
                        "PUBLIC_INPUT_CONFLICT",
                        [],
                        f"delete_object fact for {anchor} targets an "
                        "already-satisfied pin",
                    )
                continue
            if observed is None:
                if deletion is not None:
                    raise _Problem(
                        "PUBLIC_INPUT_CONFLICT",
                        [],
                        f"delete_object fact for {anchor} has nothing to "
                        "delete: pin is floating",
                    )
                ops.append({"op": OP_ADD_NET_LABEL, "name": target_net, "at": anchor})
                diagnosis.append(
                    _diagnose(observed_text, [fact["id"]], "floating pin receives the approved net label (R1)")
                )
            else:
                if deletion is None:
                    raise _Problem(
                        "PUBLIC_INPUT_INSUFFICIENT",
                        [f"delete-{anchor.replace('.', '-')}"],
                        f"pin {anchor} is wired to {observed}; retargeting "
                        "needs an approved delete_object fact carrying the wrong "
                        "label uuid, which the package does not supply",
                    )
                retargeted_anchors.add(anchor)
                ops.append({"op": OP_DELETE_OBJECT, "uuid": deletion["uuid"]})
                ops.append({"op": OP_ADD_NET_LABEL, "name": target_net, "at": anchor})
                diagnosis.append(
                    _diagnose(
                        observed_text,
                        [deletion["id"], fact["id"]],
                        "wrong label deleted by approved uuid, approved label added (R1)",
                    )
                )

        # R4：孤儿删除（没有任何 connect_pin 引用的 delete_object）
        for anchor, deletion in deletions_by_anchor.items():
            if anchor not in retargeted_anchors:
                raise _Problem(
                    "PUBLIC_INPUT_INSUFFICIENT",
                    [f"connect-{anchor.replace('.', '-')}"],
                    f"delete_object fact {deletion['id']} for {anchor} has no "
                    "paired connect_pin fact; arm D deletes only to retarget a "
                    "pin, not speculatively",
                )

        # R2：place_component（按数组顺序；坐标按 grants 顺序取槽）
        for fact in interpretable:
            if fact["kind"] != FACT_PLACE_COMPONENT:
                continue
            designator = fact["designator"]
            if designator in place_seen:
                raise _Problem(
                    "PUBLIC_INPUT_CONFLICT",
                    [],
                    f"two place_component facts target designator {designator}; "
                    "arm D cannot derive a deterministic placement",
                )
            place_seen.add(designator)
            existing = view.component(designator)
            if existing is not None:
                observed_value = existing.get("value")
                observed_text = f"component {designator} observed value {observed_value!r}"
                if observed_value == fact["value"]:
                    diagnosis.append(
                        _diagnose(
                            observed_text,
                            [fact["id"]],
                            "component already matches the approved value; no operation",
                        )
                    )
                    continue
                raise _Problem(
                    "NOT_EXPRESSION_IN_PUBLIC_OPS",
                    [],
                    f"component {designator} exists with value {observed_value!r} but "
                    f"the approved value is {fact['value']!r}; public primitives "
                    "cannot modify an existing component",
                )
            slot = take_slot()
            ops.append(
                {
                    "op": OP_PLACE_COMPONENT,
                    "lib_id": fact["lib_id"],
                    "designator": designator,
                    "x_mil": slot["x_mil"],
                    "y_mil": slot["y_mil"],
                    "value": fact["value"],
                    "footprint": fact["footprint"],
                }
            )
            diagnosis.append(
                _diagnose(
                    f"component {designator} absent from netlist observation",
                    [fact["id"]],
                    "approved component placed on host-granted slot "
                    f"({slot['x_mil']}, {slot['y_mil']}) in package order (R2)",
                )
            )
            for pin_key in sorted(fact["pin_nets"]):
                ops.append(
                    {
                        "op": OP_ADD_NET_LABEL,
                        "name": fact["pin_nets"][pin_key],
                        "at": f"{designator}.{pin_key}",
                    }
                )
            diagnosis.append(
                _diagnose(
                    f"{len(fact['pin_nets'])} pins of newly placed {designator}",
                    [fact["id"]],
                    "pins of newly placed component receive approved net labels (R2)",
                )
            )
    except _Problem as problem:
        return _finish(header, _refuse(problem.reason_code, problem.missing, problem.explanation))

    if not ops:
        return _finish(
            header,
            _refuse(
                "ALREADY_SATISFIED",
                [],
                "all approved targets already match the observation; the frozen "
                "schema has no empty patch, so arm D refuses with no change",
            ),
        )
    if len(ops) > max_ops:
        return _finish(
            header,
            _refuse(
                "OPERATION_LIMIT_EXCEEDED",
                [],
                f"derived {len(ops)} operations exceeds limits.max_ops={max_ops}",
            ),
        )
    if len(diagnosis) > MAX_DIAGNOSIS:
        return _finish(
            header,
            _refuse(
                "OPERATION_LIMIT_EXCEEDED",
                [],
                f"derived {len(diagnosis)} diagnosis entries exceeds the frozen "
                f"limit of {MAX_DIAGNOSIS}",
            ),
        )

    proposal = dict(header)
    proposal["decision"] = DECISION_PATCH
    proposal["diagnosis"] = diagnosis
    proposal["oplist"] = {"protocol_version": 2, "target_format": "kicad", "ops": ops}
    return _finish(header, proposal)


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


def propose_bytes(raw: bytes) -> bytes:
    """D 侧适配器：request_bytes（冻结包原始字节）→ Proposal 字节。

    与 tools.y4_dry_runner.run_adapter 的 adapter(request_bytes) -> bytes
    契约一致；BaselineInputError（包级结构损坏）向上抛给调用方记录，
    不在适配器内吞掉。
    """
    return render(build_proposal(load_document(raw)))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AEDL Y4 arm-D deterministic baseline")
    parser.add_argument("--package", required=True, help="y4-public.v3 package JSON (exact C/D request bytes)")
    parser.add_argument("--out", required=True, help="output proposal JSON path")
    args = parser.parse_args(argv)
    try:
        proposal = build_proposal(load_package(Path(args.package)))
    except BaselineInputError as exc:
        print(f"baseline: invalid package: {exc}", file=sys.stderr)
        return 2
    Path(args.out).write_bytes(render(proposal))
    print(f"baseline: wrote {proposal['decision']} proposal to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
