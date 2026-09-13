"""AEDL Y4 · D 组固定规则基线 v0.6.0（A-2′ prime：观测 + 公共合同 → 冻结 Proposal）。

来源与定位（A-2′ prime）
-----------------------
本版的推理内核不是重新设计，而是从**计分 30 槽实跑真正使用的产物**逐行移植：
    r16/candidates/d_adapter_v3_candidate.py
    tool_hash d83d97e7…（scored 30-slot run 记录的 adapter 实现）
移植只做两件事：(1) 把内核搬进本仓库的 tools/repair_baseline.py（自带源码解析器
与 nearest_slot，不再 import notes.y4/*）；(2) 保留 v0.5 的外壳（严格包校验、
拒绝信封、CLI 退出码、C1 冻结发射器）。因此"实跑过的规则引擎"与本仓库产物
字节级一致，而不是又一次"换壳"。

D1 = "C"：L1 事实 + 白名单化 L1.5 策略子集，**没有 L2**
-------------------------------------------------------
v0.5.0 的 L2 事实文法（interpret_facts / FACT_KINDS）与 ObservationView 已删除：
Owner 决策 D1 = "C" 明确 L2 操作邻域事实不属于冻结合同。于是 public_facts
**不再承载修复推理**（本版完全忽略其内容，只保留"必须是数组"的形状守卫，
以免类型不符把包级损坏误判成 exit 2）。D 改为从
  - 观测：public_context.current_observation（kicad_netlist_current.v1）
  - 公共合同：gates/contracts/m2_schematic_contract_v1.json（相对本模块解析）
推导修复——这正是实跑产物已经采用的规则引擎。

移植的确定性语义（r16 逐条保留）
------------------------------
- 网名规范化：`unconnected-*` 表示"未连接"（None）；KiCad 根图纸前缀 `/` 剥掉。
- 引脚不出现在任何 net 的 nodes 里 = 悬空（None）。
- op 顺序：delete_object(0) < place_component(1) < add_net_label(2)，
  随后按 op 的规范 JSON 去重。
- 诊断条目：rule_id = 公共合同规则 id；requirement_level 由 severity 映射
  （critical→MANDATORY，major→RECOMMENDED，其余 UNKNOWN）；fact_ids=[]；
  rationale 只描述公共合同规则。
- 缺件修复：期望引脚网取自合同，footprint 取自同前缀兄弟，几何取自
  source_utf8 的库引脚/导线/标签；坐标只从 placement_grants 取。
- 输出：json.dumps(ensure_ascii=False, sort_keys=True, separators=(",", ":"))，
  **无尾换行**（与实跑 D 的字节一致）。

D2 未决缝（placement policy 尚未冻结）
------------------------------------
所有槽位选择都收敛到唯一的 choose_slot(grants, anchor=None)：当前行为 =
有 anchor 时 nearest_slot(grants, anchor)，否则 grants[0]（与实跑一致）。
"槽位是否顺序消耗、是否去重占用"仍**对 Owner 开放**；若冻结为
"sequential consumption"，只需改这一个函数。槽位**成员性**由 runner 强制
（place_component 逐坐标做 grants 成员检查），D 永不自造坐标。

用法（D 侧 adapter 的 CLI 形态）
----
    py -3 tools/repair_baseline.py --package package.json --out proposal.json

退出码：0 = 已产出合法 Proposal（PATCH/REFUSE 均算）；2 = 包文件级结构损坏。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

TOOL_VERSION = "0.6.0"

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
OP_ORDER = {OP_DELETE_OBJECT: 0, OP_PLACE_COMPONENT: 1, OP_ADD_NET_LABEL: 2}

REASON_PUBLIC_INPUT_MALFORMED = "PUBLIC_INPUT_MALFORMED"
REASON_OBSERVATION_CONFLICT = "OBSERVATION_CONFLICT"
REASON_OPERATION_LIMIT_EXCEEDED = "OPERATION_LIMIT_EXCEEDED"
REASON_GRANTS_EXHAUSTED = "GRANTS_EXHAUSTED"
REASON_NO_DERIVABLE_PLAN = "NO_DERIVABLE_PLAN"

# critical→MANDATORY，major→RECOMMENDED，其余→UNKNOWN（r16 语义）
REQUIREMENT_BY_SEVERITY = {"critical": "MANDATORY", "major": "RECOMMENDED"}

# 公共合同（公共领域知识）相对本模块解析：无硬编码用户路径、无仓库环境变量。
CONTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "gates"
    / "contracts"
    / "m2_schematic_contract_v1.json"
)

REQUIRED_HUMAN_DECISION = (
    "A2-Y/Percy must freeze the D-internal placement slot-selection rule (D2) "
    "and confirm public contract coverage; arm D will not guess."
)

_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")
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


def _bad(explanation: str) -> _Problem:
    return _Problem(REASON_PUBLIC_INPUT_MALFORMED, [], explanation)


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
    # public_facts 的形状守卫放在引擎层：类型不符产出"合法 REFUSE"而不是
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
        raise _bad("placement_grants must be a nonempty list")
    if len(grants) > MAX_GRANT_SLOTS:
        raise _bad("placement_grants exceeds the policy cap")
    seen = set()
    slots: List[Dict[str, int]] = []
    for index, slot in enumerate(grants):
        if not isinstance(slot, dict) or set(slot) != set(GRANT_SLOT_KEYS):
            raise _bad(f"placement_grants[{index}] must hold exactly x_mil and y_mil")
        pair = (slot["x_mil"], slot["y_mil"])
        if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 1000000 for v in pair):
            raise _bad(f"placement_grants[{index}] coordinates must be integer mil")
        if pair in seen:
            raise _bad(f"placement_grants[{index}] duplicates a slot")
        seen.add(pair)
        slots.append({"x_mil": pair[0], "y_mil": pair[1]})
    return slots


# ---------------------------------------------------------------------------
# 公开源码解析器（自包含内联：本分支没有 notes/y4/*，不得 import notes.*）
# 只移植引擎用得到的最小面：导线几何/标签位置/符号引脚原点。
# ---------------------------------------------------------------------------


# 说明：这里刻意不用 @dataclass——D 适配器可能被宿主用
# `importlib.util.spec_from_file_location` 载入而不注册进 sys.modules，
# 在 Python 3.9 下 dataclass + PEP 563 字符串注解会在那时崩溃。普通类等价。

class Wire:
    __slots__ = ("uuid", "x1", "y1", "x2", "y2")

    def __init__(self, uuid: str, x1: float, y1: float, x2: float, y2: float):
        self.uuid = uuid
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    @property
    def mid(self) -> Tuple[float, float]:
        return (round((self.x1 + self.x2) / 2, 4), round((self.y1 + self.y2) / 2, 4))


class Label:
    __slots__ = ("name", "x", "y", "uuid")

    def __init__(self, name: str, x: float, y: float, uuid: Optional[str]):
        self.name = name
        self.x = x
        self.y = y
        self.uuid = uuid


class Symbol:
    __slots__ = ("ref", "lib_id", "x", "y")

    def __init__(self, ref: Optional[str], lib_id: str, x: float, y: float):
        self.ref = ref
        self.lib_id = lib_id
        self.x = x
        self.y = y


class Schematic:
    __slots__ = ("wires", "labels", "symbols")

    def __init__(self, wires: List[Wire], labels: List[Label], symbols: List[Symbol]):
        self.wires = wires
        self.labels = labels
        self.symbols = symbols

    def labels_at(self, x: float, y: float, tol: float = 0.001) -> List[Label]:
        return [l for l in self.labels if abs(l.x - x) <= tol and abs(l.y - y) <= tol]


def _balanced_blocks(source_text: str, opener: str):
    """Yield balanced-paren blocks that start with `opener`.

    Limitation: quoted strings containing parentheses are not unescaped; the
    parser is a best-effort extractor over public source text, not a full s-expr
    reader.
    """
    start = re.compile(opener)
    index = 0
    while True:
        m = start.search(source_text, index)
        if not m:
            return
        depth = 0
        for j in range(m.start(), len(source_text)):
            ch = source_text[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    yield source_text[m.start():j + 1]
                    index = j + 1
                    break
        else:
            return


def parse_schematic(source_text: str) -> Schematic:
    wires: List[Wire] = []
    for block in _balanced_blocks(source_text, r'\(wire\s'):
        pts = re.search(r'\(pts\s+\(xy\s+([\-0-9.]+)\s+([\-0-9.]+)\)\s+'
                        r'\(xy\s+([\-0-9.]+)\s+([\-0-9.]+)\)\)', block)
        uuid_match = re.search(r'\(uuid\s+"(%s)"\)' % _UUID, block)
        if pts and uuid_match:
            wires.append(Wire(uuid_match.group(1), float(pts.group(1)),
                              float(pts.group(2)), float(pts.group(3)),
                              float(pts.group(4))))
    labels: List[Label] = []
    for block in _balanced_blocks(source_text, r'\(label\s'):
        head = re.search(r'\(label\s+"([^"]*)"\s+\(at\s+([\-0-9.]+)\s+([\-0-9.]+)\s+'
                         r'[\-0-9.]+\)', block)
        uuid_match = re.search(r'\(uuid\s+"(%s)"\)' % _UUID, block)
        if head:
            labels.append(Label(head.group(1), float(head.group(2)),
                                float(head.group(3)),
                                uuid_match.group(1) if uuid_match else None))
    symbols: List[Symbol] = []
    for block in _balanced_blocks(source_text, r'\(symbol\s+\(lib_id\s'):
        lib = re.search(r'\(lib_id\s+"([^"]+)"\)', block)
        at = re.search(r'\(at\s+([\-0-9.]+)\s+([\-0-9.]+)', block)
        ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', block)
        if lib and at:
            symbols.append(Symbol(ref_match.group(1) if ref_match else None,
                                  lib.group(1), float(at.group(1)), float(at.group(2))))
    return Schematic(wires, labels, symbols)


# ---------------------------------------------------------------------------
# 宿主授权放置槽位（内联 pr61 notes/y4/placement_grants.py 的语义）
# ---------------------------------------------------------------------------

MM_PER_MIL = 0.0254


def nearest_slot(grants: List[Dict[str, int]], x_mm: float, y_mm: float) -> Dict[str, int]:
    """Deterministic public choice: the granted slot nearest a public anchor."""
    return min(grants, key=lambda s: ((s["x_mil"] * MM_PER_MIL - x_mm) ** 2
                                      + (s["y_mil"] * MM_PER_MIL - y_mm) ** 2,
                                      s["y_mil"], s["x_mil"]))


def choose_slot(grants: List[Dict[str, int]],
                anchor: Optional[Tuple[float, float]] = None) -> Dict[str, int]:
    """D2 未决缝：D 内部槽位选择规则的唯一入口。

    当前行为 = 有公开锚点（导线中点/期望网标签中点）时取 nearest_slot，
    没有锚点时取 grants[0]——与计分实跑的 r16 产物完全一致。
    "槽位顺序消耗 / 占用去重"是否成为 D 内部规则仍对 Owner 开放（D2）；
    若冻结为 sequential consumption，只需改本函数。槽位**成员性**由 runner
    强制（place_component 逐坐标做 grants 成员检查），D 永不自造坐标。
    """
    if anchor is None:
        return grants[0]
    return nearest_slot(grants, anchor[0], anchor[1])


# ---------------------------------------------------------------------------
# 公共合同
# ---------------------------------------------------------------------------


def _load_contract() -> Dict[str, Any]:
    """公共合同只从仓库内固定相对路径读取（无环境变量、无用户路径）。"""
    try:
        return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _bad(f"cannot read the public contract at {CONTRACT_PATH}: {exc}") from exc


# ---------------------------------------------------------------------------
# 观测索引（kicad_netlist_current.v1）：引脚不在任何 net = 悬空
# ---------------------------------------------------------------------------


def observed_state(
    observation: Dict[str, Any],
) -> Tuple[Dict[str, Optional[str]], Dict[str, str], Dict[str, str]]:
    """(pin_net, comp_value, comp_footprint)；形状不符 → 合法 REFUSE。"""
    if not isinstance(observation, dict):
        raise _bad("current_observation must be an object")
    if observation.get("observation_type") != OBSERVATION_TYPE:
        raise _bad(
            "current_observation.observation_type must be "
            f"{OBSERVATION_TYPE!r}; arm D cannot read other formats"
        )
    raw_components = observation.get("components")
    if not isinstance(raw_components, list):
        raise _bad("current_observation.components must be an array")
    comp_value: Dict[str, str] = {}
    comp_footprint: Dict[str, str] = {}
    for index, component in enumerate(raw_components):
        if not isinstance(component, dict) or not isinstance(component.get("ref"), str):
            raise _bad(f"current_observation.components[{index}] is malformed")
        comp_value[component["ref"]] = component.get("value", "")
        comp_footprint[component["ref"]] = component.get("footprint", "")
    raw_nets = observation.get("nets")
    if not isinstance(raw_nets, list):
        raise _bad("current_observation.nets must be an array")
    pin_net: Dict[str, Optional[str]] = {}
    for net_index, net in enumerate(raw_nets):
        if not isinstance(net, dict) or not isinstance(net.get("name"), str):
            raise _bad(f"current_observation.nets[{net_index}] is malformed")
        nodes = net.get("nodes")
        if not isinstance(nodes, list):
            raise _bad(f"current_observation.nets[{net_index}].nodes must be an array")
        name = net["name"]
        if name.startswith("unconnected-"):
            connected: Optional[str] = None
        else:
            # KiCad 根图纸网名导出为 "/NAME"；合同用裸名。这是确定性的名字
            # 规范化，不是猜测。
            connected = name[1:] if name.startswith("/") else name
        for node in nodes:
            if not isinstance(node, dict):
                raise _bad(f"current_observation.nets[{net_index}] node is malformed")
            ref, pin = node.get("ref"), node.get("pin")
            if not isinstance(ref, str) or not isinstance(pin, str):
                raise _bad(
                    f"current_observation.nets[{net_index}] node ref/pin must be strings"
                )
            key = "%s.%s" % (ref, pin)
            if key in pin_net and pin_net[key] != connected:
                raise _Problem(
                    REASON_OBSERVATION_CONFLICT,
                    [],
                    f"pin {key} appears in multiple nets "
                    f"({pin_net[key]} and {connected})",
                )
            pin_net[key] = connected
    return pin_net, comp_value, comp_footprint


# ---------------------------------------------------------------------------
# 合同求值（只有公开 netlist 视图）
# ---------------------------------------------------------------------------


def evaluate_netlist(
    contract: Dict[str, Any], observation: Dict[str, Any]
) -> List[Dict[str, Any]]:
    pin_net, comp_value, _ = observed_state(observation)
    mismatches: List[Dict[str, Any]] = []
    for rule in contract.get("rules", []):
        netlist_checks = rule.get("checks", {}).get("netlist", {})
        for key, expected in netlist_checks.get("pins", {}).items():
            ref = key.split(".")[0]
            if ref not in comp_value:
                continue  # handled at component level
            expected_net = expected.get("net")
            observed_net = pin_net.get(key)
            if expected_net is None:
                if observed_net is not None:
                    mismatches.append({"rule_id": rule["id"], "severity": rule["severity"],
                                       "kind": "pin_should_be_disconnected", "pin": key,
                                       "expected_net": None, "observed_net": observed_net})
            elif observed_net != expected_net:
                mismatches.append({"rule_id": rule["id"], "severity": rule["severity"],
                                   "kind": "pin_net", "pin": key,
                                   "expected_net": expected_net, "observed_net": observed_net})
        for ref, expected in netlist_checks.get("components", {}).items():
            expected_value = expected.get("value")
            if ref not in comp_value:
                mismatches.append({"rule_id": rule["id"], "severity": rule["severity"],
                                   "kind": "missing_component", "ref": ref,
                                   "expected_value": expected_value})
            elif comp_value[ref] != expected_value:
                mismatches.append({"rule_id": rule["id"], "severity": rule["severity"],
                                   "kind": "wrong_value", "ref": ref,
                                   "expected_value": expected_value, "observed_value": comp_value[ref]})
    return mismatches


# ---------------------------------------------------------------------------
# 计划派生（r16 语义）
# ---------------------------------------------------------------------------


def parse_lib_pins(source_text: str) -> Dict[str, Dict[str, Tuple[float, float]]]:
    """Library symbol name -> {pin number: (dx, dy)} from lib_symbols blocks."""
    libs: Dict[str, Dict[str, Tuple[float, float]]] = {}
    for block in _balanced_blocks(source_text, r'\(symbol\s+"'):
        head = re.match(r'\(symbol\s+"([^"]+)"', block)
        if not head:
            continue
        pins: Dict[str, Tuple[float, float]] = {}
        for pin in re.finditer(
                r'\(pin\s+\w+\s+\w+\s+\(at\s+([\-0-9.]+)\s+([\-0-9.]+)\s+[\-0-9.]+\).*?'
                r'\(number\s+"([^"]+)"', block, re.S):
            pins[pin.group(3)] = (float(pin.group(1)), float(pin.group(2)))
        if pins and ":" in head.group(1):
            libs[head.group(1)] = pins
    return libs


def symbol_absolute_pins(sch: Schematic, lib_pins: Dict[str, Dict[str, Tuple[float, float]]],
                         ref: str) -> Optional[Dict[str, Tuple[float, float]]]:
    """Absolute pin positions for one instance (rotation 0, no mirror only)."""
    for sym in sch.symbols:
        if sym.ref != ref:
            continue
        if sym.lib_id not in lib_pins:
            return None
        return {pin: (round(sym.x + dx, 4), round(sym.y - dy, 4))
                for pin, (dx, dy) in lib_pins[sym.lib_id].items()}
    return None


def _sibling_footprint(prefix: str, comp_footprint: Dict[str, str]) -> Optional[str]:
    candidates = [v for k, v in comp_footprint.items()
                  if re.match(r'^%s\d+$' % re.escape(prefix), k) and v]
    if not candidates:
        return None
    return Counter(candidates).most_common(1)[0][0]


def _label_positions(sch: Schematic, name: str) -> List[Tuple[float, float]]:
    return sorted((l.x, l.y) for l in sch.labels if l.name == name)


def _wire_endpoint_labels(sch: Schematic, wire: Wire) -> List[str]:
    names = []
    for point in ((wire.x1, wire.y1), (wire.x2, wire.y2)):
        names += [l.name for l in sch.labels_at(point[0], point[1])]
    return names


def build_plan(mismatches: List[Dict[str, Any]], sch: Schematic,
               lib_pins: Dict[str, Dict[str, Tuple[float, float]]],
               contract: Dict[str, Any], comp_footprint: Dict[str, str],
               grants: List[Dict[str, int]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    ops: List[Dict[str, Any]] = []
    blockers: List[str] = []

    # expected pin nets for missing components (from the contract)
    expected_pins: Dict[str, Dict[str, str]] = {}
    for rule in contract.get("rules", []):
        for key, expected in rule.get("checks", {}).get("netlist", {}).get("pins", {}).items():
            ref, pin = key.split(".", 1)
            if expected.get("net"):
                expected_pins.setdefault(ref, {})[pin] = expected["net"]
    missing_refs = {m["ref"] for m in mismatches if m["kind"] == "missing_component"}
    missing_nets = {net for ref in missing_refs for net in expected_pins.get(ref, {}).values()}

    for mismatch in mismatches:
        kind = mismatch["kind"]
        if kind in ("pin_net", "pin_should_be_disconnected") and \
                mismatch.get("expected_net") in missing_nets:
            # These nets are restored by placing the missing component; touching
            # their labels now would fight the placement repair.
            continue
        if kind == "missing_component":
            ref = mismatch["ref"]
            prefix = re.match(r'^[A-Za-z]+', ref).group(0)
            lib_id = {"R": "Device:R", "C": "Device:C"}.get(prefix)
            if lib_id is None:
                blockers.append("unsupported lib for %s" % ref)
                continue
            footprint = _sibling_footprint(prefix, comp_footprint)
            pins = expected_pins.get(ref, {})
            if footprint is None or len(pins) != 2:
                blockers.append("insufficient sibling/pin evidence for %s" % ref)
                continue
            net_names = sorted(pins.values())
            # A retained wire whose endpoints carry the two expected nets marks
            # where the part used to sit: it is deleted, and its midpoint is a
            # public anchor for choosing a granted slot.
            wire_matches = [w for w in sch.wires
                            if sorted(_wire_endpoint_labels(sch, w)) == net_names]
            anchor: Optional[Tuple[float, float]] = None
            if len(wire_matches) == 1:
                anchor = wire_matches[0].mid
                ops.append({"op": OP_DELETE_OBJECT, "uuid": wire_matches[0].uuid})
            elif len(wire_matches) > 1:
                blockers.append("ambiguous wire match for %s" % ref)
                continue
            if anchor is None:
                anchors = [_label_positions(sch, net) for net in net_names]
                points = [p[0] for p in anchors if p]
                if len(points) == 2:
                    anchor = ((points[0][0] + points[1][0]) / 2.0,
                              (points[0][1] + points[1][1]) / 2.0)
                elif points:
                    anchor = (points[0][0], points[0][1] + 5.08)
            chosen = choose_slot(grants, anchor)
            ops.append({"op": OP_PLACE_COMPONENT, "lib_id": lib_id, "designator": ref,
                        "x_mil": chosen["x_mil"], "y_mil": chosen["y_mil"],
                        "value": mismatch["expected_value"], "footprint": footprint})
            for pin, net in sorted(pins.items()):
                ops.append({"op": OP_ADD_NET_LABEL, "name": net, "at": "%s.%s" % (ref, pin)})
        elif kind == "pin_net":
            pin = mismatch["pin"]
            expected_net = mismatch["expected_net"]
            observed_net = mismatch["observed_net"]
            if observed_net is None:
                ops.append({"op": OP_ADD_NET_LABEL, "name": expected_net, "at": pin})
                continue
            ref = pin.split(".")[0]
            abs_pins = symbol_absolute_pins(sch, lib_pins, ref)
            if not abs_pins or pin.split(".", 1)[1] not in abs_pins:
                blockers.append("pin geometry unavailable for %s" % pin)
                continue
            position = abs_pins[pin.split(".", 1)[1]]
            candidates = [l for l in sch.labels_at(position[0], position[1])
                          if l.name == observed_net]
            if len(candidates) != 1 or not candidates[0].uuid:
                blockers.append("ambiguous label removal for %s" % pin)
                continue
            ops.append({"op": OP_DELETE_OBJECT, "uuid": candidates[0].uuid})
            ops.append({"op": OP_ADD_NET_LABEL, "name": expected_net, "at": pin})
        elif kind == "pin_should_be_disconnected":
            blockers.append("cannot express disconnection for %s" % mismatch["pin"])
        elif kind == "wrong_value":
            blockers.append("no C1 value-update operation for %s" % mismatch["ref"])

    unique = {json.dumps(op, sort_keys=True): op for op in ops}
    ordered = sorted(unique.values(),
                     key=lambda op: (OP_ORDER[op["op"]], json.dumps(op, sort_keys=True)))
    return ordered, blockers


def _diagnosis(mismatches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """合同规则视角的诊断条目（rule_id 取合同规则 id，fact_ids 恒为空）。

    条目数封顶于冻结合同的 MAX_DIAGNOSIS：诊断里只承载公共合同规则，超限时
    截断尾部（按 rule_id 排序后的尾部）而不是让产物超出 C1 的封闭上限——
    "拒绝也必须是合法 Proposal"是硬约束。真实合同 5 条规则，永不触发。
    """
    diagnosis: List[Dict[str, Any]] = []
    by_rule: Dict[str, List[Dict[str, Any]]] = {}
    for mismatch in mismatches:
        by_rule.setdefault(mismatch["rule_id"], []).append(mismatch)
    for rule_id, items in sorted(by_rule.items())[:MAX_DIAGNOSIS]:
        severity = items[0].get("severity", "major")
        observed = "; ".join(
            "%s=%s(expected %s)" % (m.get("pin") or m.get("ref"),
                                    m.get("observed_net", m.get("observed_value", "missing")),
                                    m.get("expected_net", m.get("expected_value")))
            for m in items[:4])
        diagnosis.append({
            "rule_id": rule_id,
            "observed": observed,
            "fact_ids": [],
            "requirement_level": REQUIREMENT_BY_SEVERITY.get(severity, "UNKNOWN"),
            "rationale": "public contract rule evaluated over the package netlist",
        })
    return diagnosis


# ---------------------------------------------------------------------------
# 提案组装（冻结发射器：五字段 + PATCH/REFUSE + 三原语）
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


def _refuse_bound(header: Dict[str, Any], reason_code: str, missing: List[str],
                  explanation: str) -> Dict[str, Any]:
    """把 shell 级拒绝（结构/预算）绑定到冻结包头部。"""
    proposal = _refuse(reason_code, missing, explanation)
    proposal.update(header)
    return proposal


def build_proposal(package: Dict[str, Any],
                   contract: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """从冻结包（+可选注入合同）推导 Proposal。

    contract=None 时读取仓库内公共合同（与实跑 D 使用的同一份）；测试可注入
    中性合成合同。返回 Proposal 字典（render()/propose_bytes() 负责字节化）。
    """
    context = package["public_context"]
    header = {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "context_id": context["context_id"],
        "target": context["target"],
        "base_source_sha256": context["base_source_sha256"],
    }
    max_ops = context["limits"]["max_ops"]
    try:
        # grants / 观测 / 源码的一切不兼容都以"合法 REFUSE"表达（退出码 0）；
        # exit 2 只保留给包文件级结构损坏（load_document 层）。
        grants = _validate_grants(package["placement_grants"])
        facts = context["public_facts"]
        if not isinstance(facts, list):
            # D1=C：facts 不再承载修复推理，但形状不符仍 fail-closed 成合法 REFUSE。
            raise _bad(
                "public_facts must be an array (empty means no supplied facts); "
                "arm D consumes the frozen y4-public.v3 shape only"
            )
        observation = context["current_observation"]
        source_text = package["source_utf8"]
        if not isinstance(source_text, str) or not source_text:
            raise _bad("source_utf8 must be non-empty KiCad s-expression text")
        active_contract = contract if contract is not None else _load_contract()
        if not isinstance(active_contract, dict):
            raise _bad("contract must be an object")
        mismatches = evaluate_netlist(active_contract, observation)
        schematic = parse_schematic(source_text)
        lib_pins = parse_lib_pins(source_text)
        _, _, comp_footprint = observed_state(observation)
        ops, blockers = build_plan(mismatches, schematic, lib_pins, active_contract,
                                   comp_footprint, grants)
    except _Problem as problem:
        return _refuse_bound(header, problem.reason_code, problem.missing,
                             problem.explanation)

    diagnosis = _diagnosis(mismatches)

    if ops and not blockers:
        if len(ops) > max_ops:
            return _refuse_bound(
                header,
                REASON_OPERATION_LIMIT_EXCEEDED,
                [],
                f"derived {len(ops)} operations exceeds limits.max_ops={max_ops}",
            )
        placements = sum(1 for op in ops if op["op"] == OP_PLACE_COMPONENT)
        if placements > len(grants):
            return _refuse_bound(
                header,
                REASON_GRANTS_EXHAUSTED,
                [],
                f"derived {placements} placements exceeds the "
                f"{len(grants)} granted slot(s); member slot selection is "
                "host-granted (D2 open)",
            )
        proposal = dict(header)
        proposal["decision"] = DECISION_PATCH
        proposal["diagnosis"] = diagnosis
        proposal["oplist"] = {"protocol_version": 2, "target_format": "kicad", "ops": ops}
        return proposal

    # 引擎无法表达修复：blockers 逐条写明（r16 语义：携带合同规则诊断）。
    proposal = dict(header)
    proposal["decision"] = DECISION_REFUSE
    proposal["diagnosis"] = diagnosis
    proposal["refusal"] = {
        "reason_code": REASON_NO_DERIVABLE_PLAN,
        "missing_fact_ids": [],
        "explanation": "; ".join(blockers) if blockers else "no public-derivable repair plan",
        "required_human_decision": REQUIRED_HUMAN_DECISION,
    }
    return proposal


def render(proposal: Dict[str, Any]) -> bytes:
    """冻结字节形态：与实跑 D 一致——无尾换行、ASCII 关闭、键排序、紧凑分隔。"""
    return json.dumps(
        proposal,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def propose_bytes(raw: bytes) -> bytes:
    """D 侧适配器：request_bytes（冻结包原始字节）→ Proposal 字节。

    与 tools.y4_dry_runner.run_adapter 的 adapter(request_bytes) -> bytes
    契约一致；BaselineInputError（包级结构损坏）向上抛给调用方记录，
    不在适配器内吞掉。
    """
    return render(build_proposal(load_document(raw)))


def adapter(request_bytes: bytes) -> bytes:  # runner-compatible interface
    """runner 兼容入口（C/D 同字节）：propose_bytes 的别名语义。"""
    return propose_bytes(request_bytes)


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
