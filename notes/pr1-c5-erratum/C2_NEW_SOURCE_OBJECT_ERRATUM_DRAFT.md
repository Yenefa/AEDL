# PR1-C5-ERRATUM — C2 new-source-object expected semantics（函数级补丁草案）

> **状态：DRAFT（rev4）— 未应用任何代码改动。**
> 基线：`669aa16`（origin/master）。`gates/repair_verification.py` blob `88a311e17763e0ac83f33c5fd499c2a1852b2c44`
> （与 C5 HEAD `2460d5d` 逐字节相同，已用 `git hash-object` 双向核对）。
> 配套：`tasks/PR1-C5-ERRATUM.yaml`。
>
> **Provenance（不得混淆）**
>
> ```text
> Architecture review decision (AI reviewer, 2026-09-20):
>   CHANGES_REQUESTED -> rev2 已修 2 blockers + 5 items
>   recommend narrow C2 erratum; do not implement before human Owner scope grant
>
> Human Owner scope grant: PENDING
> Decision ref:            PENDING
> ```
>
> 本文件与相关记录的 rev1 曾把该**架构评审**写成「Owner 裁定 / 人类指令」—— 那是 provenance
> 错误，rev2 已更正。issue #83 现有 3 条评论中：2 条是 PR1-C5 / PR1-C5-PRE 的 `allow_drift`
> grant，1 条是本轮 agent 的 BLOCKED 状态记录；**没有**针对本 erratum 的人工 scope grant。
> grant 之前不得改 `gates/repair_verification.py`，也不得 admission。
>
> **Gate 顺序（architecture review 最高指示，2026-09-20）**：先由 architecture review 给出
> `DESIGN_ACCEPTED` / `READY_FOR_HUMAN_SCOPE_GRANT`，**然后**才在 issue #83 请求 human Owner
> 明确批准 `contract_change: true` 与 `gates/repair_verification.py` 的 scope expansion。
> 当前 `Owner scope grant: PENDING` **保持不变**；不得提前申请、不得自行放宽。
>
> **版本核对（rev4）**：三项 review 要求的落点 ——
>
> ```text
> item 1  _text / _identifier / _integer 返回值说明                  -> §2.2「返回值必须分清」
> item 2  §7 删除 instances residual-freedom + exclude_from_sim 收紧 -> §7.2 / §7.3 / §7.1
> item 3  R12 进入 §6 矩阵 + envelope acceptance + §8 impact        -> R12 行 / acceptance / §8
> ```
>
> 核验命令（**不要用缓存快照**）：
> `git show HEAD:notes/pr1-c5-erratum/C2_NEW_SOURCE_OBJECT_ERRATUM_DRAFT.md`
> rev1 的两句旧文本 ——「…`instances` 内容、`exclude_from_sim`、`fields_autoplaced` 等 writer 噪声」
> 与「`_integer` / `_text` / `_identifier` 是纯校验器，返回 `None`」—— **在本版已不存在**
> （分别被 §7.2 / §7.3 与 §2.2「返回值必须分清」取代）。若你看到的仍是这两句，说明读的是 rev1 快照。
>
> **逐条核对件（新路径，无缓存）**：`notes/pr1-c5-erratum/REV4_VERIFICATION.md` —— 由 pwsh 从本文件
> **抽取行区间**生成（逐字，非复述），给出 §2.2 / §7.1–§7.5 / R9–R12 / §8 的 HEAD 原文与核验命令。

---

## 0. TL;DR — 六问直答

| # | 问题 | 本草案结论 |
| --- | --- | --- |
| 1 | 新对象 expected representation | 按 identity 分流的 **closed semantic expectation**，与旧形状互斥；不带 `descriptor` / `semantic_ast_sha256` |
| 2 | `_align_new()` 唯一匹配 | 新 label 按 `(name, scope, point_nm, rotation)` 恰好一对一；新 symbol 仍按 reference，另加 Q6 绑定断言 |
| 3 | `_delta()` 如何消费 | **不加 `new:` 分支**。语义投影在 `_canonicalize_new_objects()` **一次**完成，两侧同形状，`_delta` 保持 shape-blind |
| 4 | `_projection()` fail-closed | **不加分支**。mask 条件是整份 `{identity, kind, semantics}` 相等 —— **identity 相等不构成 mask 理由** |
| 5 | existing / removed 不放松 | §6 逐条列出零改动代码路径 + R1..R12 回归矩阵 |
| 6 | symbol ↔ component 绑定 | `_canonical_new_object()` 断言 source-object UUID **恰等于** component_uuid，且唯一 |

---

## 1. 缺陷证据链（可复核，全部带 file:line）

**今天（`gates/repair_verification.py`）**

- `:251-262` `normalize_observation` 对 **每一个** `source_objects` 项要求
  `{identity, kind, semantic_ast_sha256, descriptor}`（`_closed` = 精确 key 集，`:87-89`），
  且 `descriptor.ast` 必填、`semantic_ast_sha256 == canonical_sha256("protected", ast)`。
  **`new:` 对象没有任何豁免。**
- `:410-419` `_align_new` 对新 label 的匹配键是
  `_uuid_ast(obj["descriptor"], {}, mask=True)` —— 「mask 掉 UUID 的**完整 AST**」。
- `:318-320` `_delta` 对 `source_objects` 做整对象相等比较（含 descriptor）。
- `:436-440` `_projection` 的 mask 条件是 `row == allowed[ident]`（整行相等）。

**为什么 policy / runtime 定义不了那个 AST**

- `src/repair/topology_policy_v1.json:78-83, 180-181, 214-216` 只给
  `{name, at_pin, scope, rotation}`（`at_pin` 是 `"R9.1"` 这类 `REF.PIN` 字符串）。
- pinned akcli 0.21.0：
  - `akcli/writers/handlers/labels.py:109-135` `_emit_net_label` 自造
    `tag / name / at / effects(justify) / uuid`，UUID 由 `identity.seed_label(tag, name, seed)` 播种；
  - `akcli/writers/placement.py:48-97` `_place_symbol` 的 UUID 由 designator 播种，
    pin 集合来自 `kicad_lib.unit_pins()`，依赖 `lib_cache.ensure_cached`；
  - `akcli/writers/properties.py:106+` `_autoplace_ref_value` 是几何启发式 +
    「per-apply anchor registry」，依赖**当前 document 状态**。

**合同自己怎么写的**（`docs/competition/internal/AEDL_PR1_实现合同_20260907.md`）

- `L152`：「新增组件整棵 instance 子树**允许由固定 native writer 生成**，但必须匹配 policy
  的所有属性、固定库定义、两根 pin 的身份/位置和无附加电气结构；未知电气字段不能忽略。」
- `L160`：「`expected_after` **不声称预知 writer 将产生的 bytes hash**。」

→ 结论：C2 对新对象的 expected 语义**过度绑定到 writer 序列化**。这是抽象边界错误，
不是在 C5 里补一个 AST 预言器能修的。

---

## 2. Q1 — 新对象 expected representation（closed schema）

### 2.1 形状（按 identity 分流，两形状互斥）

| identity | expected 形状 |
| --- | --- |
| **不以 `new:` 开头** | **完全不变**：`{identity, kind, semantic_ast_sha256, descriptor:{ast}}` |
| `new:<ref>` + `kind=symbol` | `{identity, kind, semantics:{reference}}`，且 `identity == "new:" + reference` |
| `new:label:<slot>` + `kind=label` | `{identity, kind, semantics:{name, scope, point_nm, rotation}}` |

JSON 例（DC-04）：

```json
{"identity": "new:R9", "kind": "symbol", "semantics": {"reference": "R9"}}
```

```json
{"identity": "new:label:0", "kind": "label",
 "semantics": {"name": "+3V3", "scope": "local", "point_nm": [0, 0], "rotation": 0}}
```

> `point_nm` 是**新组件 pin 的世界锚点**，由 policy placement + BEFORE 内嵌库定义确定
> （C2 已有该几何：`_source_components:918` 的
> `point = (position[0] + definition["point"][0], position[1] - definition["point"][1])`）。
> 既有 pin 的 label 锚点来自 BEFORE 观测。**nm 只进这里，不进 writer op 的 `at`。**

### 2.2 `normalize_observation` 的改动（`:251-262` 替换为分流）

```python
_NEW_PREFIX = "new:"

for obj in obs["source_objects"]:
    ident = _text(obj["identity"], "source object identity")
    if ident in object_keys:
        raise ObservationError("duplicate source object")
    object_keys.add(ident)
    kind = _text(obj["kind"], "source object kind")
    if expected and ident.startswith(_NEW_PREFIX):
        # NEW: closed semantic expectation, no writer AST.
        _closed(obj, {"identity", "kind", "semantics"}, "new source object")
        semantics = obj["semantics"]
        if not isinstance(semantics, dict):
            raise ObservationError("new source object semantics must be a mapping")
        if kind == "symbol":
            _closed(semantics, {"reference"}, "new symbol semantics")
            reference = _identifier(semantics["reference"], "new symbol reference")
            if ident != _NEW_PREFIX + reference:
                raise ObservationError("new symbol identity must be its component role")
        elif kind == "label":
            _closed(semantics, {"name", "scope", "point_nm", "rotation"}, "new label semantics")
            _text(semantics["name"], "new label name")
            if semantics["scope"] != "local":
                raise ObservationError("only root-local labels are qualified")
            point = semantics["point_nm"]
            if not isinstance(point, list) or len(point) != 2:
                raise ObservationError("new label point must be an nm pair")
            for coordinate in point:
                _integer(coordinate, "new label point")
            if semantics["rotation"] not in (0, 90, 180, 270):
                raise ObservationError("unsupported new label rotation")
            if re.fullmatch(r"new:label:[0-9]+", ident) is None:
                raise ObservationError("new label identity must be 'new:label:<slot>'")
        else:
            raise ObservationError("unsupported new source object kind")
    else:
        # UNCHANGED: existing / removed objects keep the full AST contract.
        _closed(obj, {"identity", "kind", "semantic_ast_sha256", "descriptor"}, "source object")
        if not isinstance(obj["descriptor"], dict) or "ast" not in obj["descriptor"]:
            raise ObservationError("source object is missing its complete AST")
        if obj["semantic_ast_sha256"] != canonical_sha256("protected", obj["descriptor"]["ast"]):
            raise ObservationError("source AST hash mismatch")
```

要点：

- `_closed` 是**精确 key 集**（`:87-89`）→ 混用形状（新形状带 `descriptor`、旧形状带 `semantics`）
  自动被拒（回归 **R10**）。
- **返回值必须分清**（这是 C3 曾踩过的真实坑，见 HANDOFF 2026-09-18 段）：
  - **返回规范值**：`_text`（`return value`，`:92-95`）、`_identifier`（`return text`，`:101-112`）、
    `_sorted_unique`（`return ordered`，`:149-156`）、`_index`（返回映射，`:159-160`）；
  - **纯校验器、返回 `None`**：`_closed`（`:87-89`）、`_integer`（`:115-117`）、`_sha`（`:120-122`）、
    `_uuid`（`:125-132`）、`_identity`（`:135-146`）。
- 因此上面的代码里 `reference = _identifier(...)` 是**正确**的（它返回规范化 reference）；
  而 `_text(semantics["name"], ...)` 与 `_integer(coordinate, ...)` 只做校验、**不得赋值**
  （`_integer` 会静默返回 `None`）。
- 新形状**只在 `expected=True` 时接受**；`expected=False` 仍要求旧形状。
- `scope` 在 qualified subset 里结构性恒为 `"local"`（`observe_source:1023-1025` 的 root
  `_source_fields` 只允许 `label`，不含 `global_label`/`hierarchical_label`）。仍显式携带并校验，
  以免 subset 日后放宽时静默漂移。
- `new:label:<slot>` 的 **dense-from-0** 规则（`:537-538`）**保持不变**。

### 2.3 明确不采用

- (a) 不把完整 future AST 塞进 `host_context`；
- (b) C5 不模拟 akcli serializer；
- (c) 不引入 optional/null 的宽松形状（那会扩大 schema 改动面却无额外安全收益）。

---

## 3. Q2 — `_align_new()` 如何唯一匹配

### 3.1 新增语义提取器（复用 C2 自己的解析助手，不 fork 几何/文本规则）

```python
def _label_semantics(node):
    """Engineering semantics of one real AFTER root-local label node."""
    if not isinstance(node, list) or not node or node[0] != "label":
        raise ObservationError("only root-local labels are qualified")
    _source_fields(node, {"at", "effects", "uuid", "fields_autoplaced"}, positional=1)
    name = _text(_source_text(node[1]), "label")
    point, angle = _source_at(node)          # nm + 0/90/180/270, _source_at:762-770
    _source_value(node, "uuid")              # uuid must exist and be readable; its value is not semantics
    return {"name": name, "scope": "local", "point_nm": list(point), "rotation": angle}
```

> 与 `_source_partitions:928-933` 读 label 的方式**同源**（同一 `_source_fields` 白名单、
> 同一 `_source_at`、同一 `_text`）。没有第二套 label 解析。

### 3.2 匹配算法（替换 `:410-419` 的 masked-AST 分支）

```python
for obj in expected["source_objects"]:
    if obj["kind"] != "label" or not obj["identity"].startswith("new:"):
        continue
    wanted = obj["semantics"]
    matches = []
    for candidate in after["source_objects"]:
        if candidate["kind"] != "label" or candidate["identity"] in old_ids:
            continue
        try:
            actual = _label_semantics(candidate["descriptor"]["ast"])
        except ObservationError:
            continue                          # an unparsable real label is left for the delta to expose
        if actual == wanted:
            matches.append(candidate)
    if len(matches) > 1:
        raise _BindingError("ambiguous new label semantics: %r" % obj["identity"])
    if len(matches) == 1 and matches[0]["identity"] not in mapping:
        mapping[matches[0]["identity"]] = obj["identity"]
```

**0 命中 / >1 命中的行为（明确）**

| 情形 | 结果 |
| --- | --- |
| 0 命中 | **不映射**。真实 label 保留 raw UUID → 在 `_delta` 里表现为「一个未授权的 added object」，且 expected 的 `new:label:<slot>` 在 `right` 中不存在 → `REPAIR_DELTA_MISMATCH` FAIL；`_projection` after 侧也不会 mask 它 → `REPAIR_PROTECTED_DIFF` FAIL。**不可能 PASS。** |
| 1 命中 | 建立 `raw UUID → new:label:<slot>` 映射 |
| >1 命中 | `_BindingError` → 直接 FAIL（不再「留作 delta 可见」） |

### 3.3 新 symbol 的匹配

保持 `:391-407` 的 **reference 唯一**逻辑不变（`after_refs[ref]` 唯一定位 component，
再按 `ref + pin number` 映射 pin UUID），另加 §6.3 的绑定断言。

---

## 4. Q3 — `_delta()` 如何消费新对象

### 4.1 结论：**`_delta()` 零改动，不加 `new:` 分支**

理由：`_delta` 现在有 3 个消费点 —— `_prepare:539` 的 `authorized`、
`observation_delta:335-336`、`compare_delta:559+` 的 actual。若在 `_delta` 里加分支，
同一份「新对象语义」逻辑会散落在两个比较站点；`authorized` 与 `actual` 一旦不对称投影，
就会复现**当前这个 bug 的成因模式**（同一个 identity 在两侧形状不同 → 永远 unequal）。
所以本草案把语义投影**收敛到一个点**。

### 4.2 收敛点：新增 `_canonicalize_new_objects()`，在 `_align_new` 末尾调用

```python
def _canonical_new_object(obj, components):
    """Canonical {identity, kind, semantics} for one ALIGNED new source object."""
    ident, kind = obj["identity"], obj["kind"]
    if kind == "symbol":
        owners = [c for c in components if c["identity"]["component_uuid"] == ident]
        if len(owners) != 1:
            raise _BindingError("new symbol source object is not bound to exactly one component")
        reference = owners[0]["reference"]
        if ident != "new:" + reference:
            raise _BindingError("new symbol identity is not its component role")
        node = obj["descriptor"]["ast"]
        if not isinstance(node, list) or not node or node[0] != "symbol":
            raise _BindingError("new symbol source object is not a symbol node")
        if _source_flag(node, "exclude_from_sim", False):          # v1: false / absent only
            raise _BindingError("new symbol must not exclude itself from simulation (v1)")
        return {"identity": ident, "kind": "symbol", "semantics": {"reference": reference}}
    if kind == "label":
        return {"identity": ident, "kind": "label",
                "semantics": _label_semantics(obj["descriptor"]["ast"])}
    raise _BindingError("unsupported new source object kind")


def _canonicalize_new_objects(obs):
    """Rewrite ALIGNED new source objects into the expected semantic shape.

    Existing objects keep their full AST (UUIDs already reidentified by
    _reidentify).  Unmapped new objects keep the raw shape on purpose: they must
    stay visible as an unauthorized addition.
    """
    for index, obj in enumerate(obs["source_objects"]):
        if obj["identity"].startswith(_NEW_PREFIX):
            obs["source_objects"][index] = _canonical_new_object(obj, obs["components"])
    return obs
```

`_align_new` 末尾：`return _canonicalize_new_objects(_reidentify(after, mapping))`
（`_reidentify` 的 UUID 重写逻辑**不改**；components 先于 source_objects 被重写，
所以 `obs["components"]` 里的 `component_uuid` 已经是 `new:<ref>`）。

### 4.3 exact behavior

```text
authorized = _delta(left, expected)   # expected side: {identity, kind, semantics}
actual     = _delta(left, right)      # right side: same shape via _canonicalize_new_objects
```

- 两侧形状相同 → `_delta:318-320` 的 `old != new` 就是**语义逐字段相等**。
- 字段错（name / scope / point_nm / rotation / reference 任一不等）→ 不等 → `compare_delta`
  报 `REPAIR_DELTA_MISMATCH`。
- 0 命中的新 label：`right` 侧 identity 仍是 raw UUID，**不以 `new:` 开头** →
  保持旧形状（带 AST）→ 与 expected 的语义形状必然不等 → FAIL。

### 4.4 一个必须知情的后果

`semantic_ast_sha256` 对 new 对象**消失**，因此 `authorized_delta` 不再包含新对象的任何 AST hash。
这是有意的：AST hash 是 writer 序列化产物，不是授权内容（合同 L160）。
整份 delta 仍由 `authorized_delta_sha256` 绑定（`_prepare:540` 不变）。
**existing / removed 对象的 AST hash 仍在 delta 里**，一个都不少。

---

## 5. Q4 — `_projection()` 如何保持 fail-closed

### 5.1 结论：**`_projection()` 零改动**

因为新对象的 `allowed[ident]` 现在就是 `{identity, kind, semantics}`，而 `:440` 的条件是
`row == allowed[ident]`（**整行**相等），所以：

- **identity 相等不构成 mask 理由**；必须整份语义相等才 mask。
- 同一 symbolic identity 下字段错误的对象 → 不 mask → 留在投影里 →
  `compare_protected:634-635` 报差异 → `REPAIR_PROTECTED_DIFF` FAIL。

### 5.2 两侧投影的逐条结论

| 调用点 | 是否受影响 |
| --- | --- |
| `protected_projection_sha256:447-450` → `_projection(left, expected, left, "before")` | **完全不受影响**。`observed = before`，新对象不在 before；`allowed = left`。**一个字节都不变**（回归 R11 用「改新对象语义 → 该 hash 不变」做对照断言）。 |
| `compare_protected:627` → `_projection(left, expected, right, "after")` | 受控改变：new 行的 mask 判据从「完整 AST 相等」变为「语义相等」。语义错 → 不 mask（fail-closed 保持）。 |

### 5.3 一个必须显式确认的边界

`_projection` 的 `changed` 集合含 **removed + added** 的 identity（`_prepare:492-497` 已保证
existing 对象逐对象相等，所以 existing 永不进 `changed`）。removed 对象不在 `expected` 里 →
`allowed` 里没有它 → **永不 mask** → 删除后若它还在 AFTER 里，一定报 protected diff。
这条行为不变。

---

## 6. Q5 — existing / removed 一字不松（零改动清单 + 回归矩阵）

### 6.1 diff 里必须**零改动**的代码路径

| 位置 | 语义 |
| --- | --- |
| `normalize_observation` 的 `expected=False` 分支 | 真实观测（事实源） |
| `normalize_observation:265-276` | coverage / keyset 校验 |
| `_prepare:472-474` | existing component 逐字段相等 |
| `_prepare:475-477` | existing pin / NC 逐字段相等 |
| `_prepare:478-491` | new component role 子集（Device:R/C、pin ["1","2"]、declaration exact） |
| `_prepare:492-497` | existing source object 逐对象相等（**含完整 AST**） |
| `_prepare:498-504` | removed = exact `{uuid, kind, descriptor_sha256=canonical_sha256("protected", descriptor)}` |
| `_prepare:537-538` | label slot dense from 0 |
| `_prepare:539-541` | `authorized_delta` + `authorized_delta_sha256` 绑定 |
| `_prepare:542-544` | `protected_projection_sha256` 绑定 |
| `protected_projection_sha256` / `_projection` 全体 | protected projection |
| `compare_protected:636-637` | dependency manifests |

### 6.2 回归矩阵（每条都要**真实红**，且按 C3 先例做「还原缺陷形态 → 确认红 → 复绿」自证）

| # | 扰动 | 期望 |
| --- | --- | --- |
| R1 | existing source object AST 任意未授权变化（改一个 string / 数值 / 子节点顺序） | FAIL |
| R2 | removed object 的 `descriptor_sha256` 不匹配 | FAIL |
| R3 | removed object 的 `kind` 改成 `symbol` | FAIL |
| R4 | 真实 AFTER 复用 BEFORE 的 UUID（component / pin / label / symbol） | FAIL |
| R5 | 出现 expected 未声明的额外 source object（extra label / extra symbol / extra wire） | FAIL |
| R6 | 少一个 expected new object（只 place 不加 label） | FAIL |
| R7 | new label 语义字段错（name / point_nm / rotation 各一例） | FAIL，且断言它**没有被 mask**（after 投影里仍在） |
| R8 | 两个真实 label 与同一 expected semantic tuple 匹配 | FAIL（`_BindingError`） |
| R9 | new symbol source-object UUID 未绑定到 aligned `component_uuid`（reference 可以一致） | FAIL —— **integration-path test**：必须走真实 AFTER full object → `_align_new` → `_canonicalize_new_objects` → `compare_delta` + `compare_protected`，不得只单测 helper（见 §6.3）。原 R13 已按 review 意见折入本条，不再单列 |
| R10 | expected new object 混用形状 | **UNKNOWN / REPAIR_COVERAGE_INCOMPLETE**（`ObservationError`）；human review correction 2026-09-21 —— 原写 FAIL，实测 taxonomy 为 UNKNOWN，断言改为「永不 PASS + 精确 reason code」 |
| R11 | 改新对象语义 → `protected_projection_sha256` **不变**（before 侧对照） | 相等断言 |
| R12 | new symbol 携带 `exclude_from_sim = yes` | FAIL（v1 只允许 false/absent，见 §7.3）；必须**同时**进入 §6 矩阵 + envelope acceptance + §8 impact，防止实现者只改描述不写 gate |

### 6.3 Q6 — 新 symbol 的 source object 与 component observation 绑定

**事实基础**：`observe_source:1041-1043` 对 root `symbol` 节点同时产出
`components[i].identity.component_uuid = _source_value(node,"uuid")`（`:906`）与
`source_objects[j].identity = _source_value(node,"uuid")` —— **同源**。
但 `_reidentify` 之后必须**显式断言**，否则「一个正确的 component observation +
一个额外错误 symbol subtree」有混过去的余地。

**断言（落在 `_canonical_new_object` 的 symbol 分支）**：

```text
exactly one component whose identity.component_uuid == the symbol source-object identity
that component.reference == <ref>
identity == "new:" + <ref>
the source object kind == "symbol" (its AST top-level tag is symbol)
no second source object shares that identity (normalize_observation:255-257 already guarantees)
```

反方向（有 component 无 source object）不需要额外断言：`right` 里缺 `new:<ref>` →
delta 不等 → FAIL。

---

## 7. new symbol 的 v1 边界（rev2 更正）

> rev1 把 `instances` 列为「残留自由度」是**事实错误**，把 `exclude_from_sim` 笼统称为
> 「writer 噪声」是**口径错误**。rev2 按 architecture review 的技术结论更正如下。

### 7.1 v1 边界（逐条）

```text
new symbol:
  components / pins / topology                exact
  source-object <-> component UUID            exact（§6.3 断言）
  instances reference / path / unit           existing parser invariants
  dnp / in_bom / on_board                     exact
  exclude_from_sim                            false / absent only      <- rev2 收紧
  property placement / effects /
  fields_autoplaced                           non-electrical presentation freedom
  unknown structural fields                   fail closed
```

### 7.2 更正点 1 —— `instances` **不是**未绑定自由度

`_source_components:886-895` 已经严格约束 `instances`：

```python
instances = _source_one(node, "instances")
_source_fields(instances, {"project"})
project = _source_one(instances, "project")
_text(_source_text(project[1]), "instance project")
_source_fields(project, {"path"}, positional=1)
path = _source_one(project, "path")
_source_fields(path, {"reference", "unit"}, positional=1)
if (_source_text(path[1]) != sheet or _source_value(path, "reference") != reference or
        _source_one(path, "unit") != unit_node):
    raise ObservationError("instance path or identity disagrees with source")
```

即 sheet path / reference / unit 都必须与当前 source observation 一致，且 `_source_fields` 对
未知字段 fail-closed。因此 `instances` 属**既有 parser invariant**，不是 erratum 引入的自由度。

### 7.3 更正点 2 —— `exclude_from_sim` 收紧为 false/absent

`exclude_from_sim` 目前只出现在 `_source_fields` 白名单里（`:867`、`:822`），**从未被读取**。
它不是视觉格式噪声，而是**行为 metadata**；即使当前 PR-1 的 topology / netlist 验证不消费它，
也不应归入「serialization noise」。rev2 采用 architecture review 指定的 v1 口径：

```text
exclude_from_sim 必须 false 或 absent
```

落点：`_canonical_new_object()` 的 symbol 分支读真实 AFTER 节点
（`_source_flag(node, "exclude_from_sim", False)` 必须为 `False`），否则 `_BindingError`（回归 R12）。

> **TO_VERIFY（实现时必做，不是 blocker）**：需在真实 DC-04 / DC-05 native AFTER 上确认
> akcli 0.21.0 对 `Device:R` / `Device:C` 实际写出的 `exclude_from_sim` 形态是 `no` 或 absent；
> 若它写出 `yes`，该要求会 false-negative，须回 Owner 重新裁定。

### 7.4 明确**不批准**的方案 —— property 名称集合闭合

rev1 提出的

```text
set(instance_properties) == set(library_properties) | {"Reference", "Value", "Footprint"}
```

**不作为本 erratum 的条件**（architecture review 明确不批准）：容易 false-negative，
且需要真实 DC-04 / DC-05 AFTER 校准才能定形。本 erratum 只保留 §7.1 的边界。

### 7.5 残留自由度（更正后的准确表述）

erratum 之后，新 symbol 真实子树中**未进入授权语义**的只剩**非电气 presentation metadata**：

```text
非电气 presentation metadata:
  property 的额外非电气表现细节
  property 的 at / effects
  fields_autoplaced
  writer 自造的 uuid（由 alignment 映射到 symbolic identity，不参与授权）
```

**这些仍受 `_source_fields()` 的 closed whitelist 约束**（instance 白名单 `observe_source:866-868`、
root 白名单 `:1023-1025`）：未知结构字段一律 fail-closed，presentation freedom 只存在于白名单
**之内**的取值/位置，不是「可以塞任意节点」。

其余一切（components / pins / topology / lib+pin digest / placement / assembly flags /
`instances` / `exclude_from_sim` / 未知结构字段）要么 exact，要么 fail-closed。

---

## 8. 影响面 / change budget

```text
Direct modifications:   gates/repair_verification.py
                          normalize_observation  source_objects split (:251-262)
                          _align_new              label matching key (:410-419)
                          _reidentify             unchanged (canonicalize appended after it)
                          new _label_semantics / _canonical_new_object / _canonicalize_new_objects
                          _delta                  ZERO change
                          _projection             ZERO change
                          _prepare                only new-object binding assertion (6.3)
                          protected_projection_sha256  ZERO change
                        tests/test_repair_verification.py
                          setUp source_object() builder (:60-65) and new:label fixture (:296)
                          existing fixtures' new-object shape
                          new R1..R12（R12 = new symbol exclude_from_sim=yes -> FAIL）
                          _canonical_new_object() 新增 exclude_from_sim false/absent 检查
                        tasks/PR1-C5-ERRATUM.yaml, notes/pr1-c5-erratum/**,
                        docs/HANDOFF.md, docs/compliance/ai-usage/**

Potentially affected:   PR1-C5 S1b step 4 build_expected_after (must emit the new shape)
                        tests/test_repair_pipeline.py future expected_after construction
Explicitly not touched: tools/**, src/**, sandbox_runtime/**, tests/fixtures/**,
                        gates/run_gates.py, gates/schematic_semantics.py,
                        docs/evidence/**, delivery/**, .gitattributes
Risk:                   MEDIUM-HIGH (changes C2 verification semantics)
```

```yaml
change_budget:
  expected_files: 8
  expected_modules: [gates, tests, tasks, notes, docs]
  cross_module: true
  contract_change: true          # flipped from PR1-C5's false -- requires the Owner grant
  evidence_semantics_change: false
```

**已核对为不需要改动的相邻面**（grep 证据）：

- `tests/test_repair_contract.py` 只在两处提到 `expected_after`（`:69` 的字段名清单、
  `:719` 的 public-projection deny token）—— 与新对象形状无关。
- `tools/repair_pipeline.py` 在基线 `669aa16` 上**完全没有** `expected_after` /
  `descriptor` 引用（C5 stage-1 代码只存在于 C5 分支）。

---

## 9. 本 erratum **不做**的事

- 不改 C1 policy schema / `src/repair/patch_schema_v1.json`；
- 不改 C4 adapter（`tools/akcli_adapter.py`）；
- 不实现 C5 第 4 步（`build_expected_after` / `bind_policy`）—— 等本卡合入 master 后
  C5 吸收新基线再恢复；
- 不新增 reason code、不新增 op、不改路由；
- 不动 `notes/b5-acceptance/**`、不动 native fixture 字节。

---

## 10. ① / ③ 的落地位置（本卡之外，登记以免漂移）

- **① ordered exact authorization**（属 C5 第 4 步，不在本卡）：
  `canonical_authorized_ops` = policy 冻结序 `remove → add_components → add_labels`；
  `add_net_label.at = rule.at_pin`（`"R9.1"` 字符串，**不换算 nm**）；
  `normalize(proposal.oplist.ops) == canonical_authorized_ops` 必须**有序 list equality**；
  回归：同 ops 重排 → BLOCKED；错 delete UUID → BLOCKED；正确 op type 错字段 → BLOCKED；
  缺一个 op → BLOCKED；多一个 op → BLOCKED。
- **③ `EXPECTED_SOURCE_SHA256` sentinel**（属 C5 第 4 步）：
  `canonical_sha256("context", {"role": "EXPECTED_AFTER_NOT_YET_WRITTEN"})`；
  语义写死为 STRUCTURAL PLACEHOLDER ONLY —— 不是 future source attestation，
  不得与 BEFORE hash 比较、不得与 staged/AFTER hash 比较、不得参与 commit predicate 的
  byte equality。真实 AFTER bytes 的事实源只有 C4 fresh native_after + C3 fresh staged
  read / verification。本卡**不**为它改 C2 schema。

---

## 11. 设计问题的处置（rev2）

| # | 问题 | 处置 |
| --- | --- | --- |
| Q1 | new symbol `semantics` 是否只有 `{reference}` | **批准**：不复制 component fields，避免第二真相源 |
| Q2 | 残留自由度 | **有条件批准**：删除 `instances`（事实错误）；`exclude_from_sim` 收紧为 false/absent；presentation-only property / effects / `fields_autoplaced` 不进入授权语义；property 名称集合闭合**不批准**（§7.4） |
| Q3 | `_delta` / `_projection` 零改动 + canonicalization 单点收敛 | **批准** |
| Q4 | R7 显式断言错误 new label 未被 mask | **批准，且必须保留** —— 只断言最终 FAIL 不够，必须证明 fail-closed 的具体机制没被绕掉 |


## 12. label `rotation` 决策（human operator，2026-09-21）：**选 B**

真实 DC-04 / DC-05 native AFTER 的 new label 是 `rotation: 90/270`，而 native op-list **不带 `rotation`**；
pinned akcli `handlers/labels.py:78-88` 在 op 缺 `rotation` 时用
`geometry.label_angle_away(pin.orientation, comp.rotation, comp.mirror)` 派生。

**裁定：选 B —— `rotation` 保留在 semantic expectation 中（exact），由 C5 第 4 步派生。**

- **本卡 C2 侧不改**：`normalize_observation` / `_label_semantics` / `_canonical_new_object` / R7 全部保持
- **C5 第 4 步义务**：`build_expected_after` 必须按同一规则计算 expected label `rotation`
- **可行性已实证**（用 pinned akcli 自己的几何函数 + 真实内嵌库 pin 角度）：

```text
Device:R lib pin angles: {'1': 270, '2': 90}
   pin 1: label_angle_away(270, rot=0, mirror=none) = 90  | 真实 AFTER label = 90  | MATCH
   pin 2: label_angle_away(90,  rot=0, mirror=none) = 270 | 真实 AFTER label = 270 | MATCH
Device:C lib pin angles: {'1': 270, '2': 90}
   pin 1 / pin 2 同上 MATCH
DERIVATION_PROOF PASS
```

  输入恰在 frozen 范围内：内嵌库 pin `(at x y angle)` + placement `rotation=0 / mirror=none`。
- **不采用 A**（会让已冻结在 policy 里的 label 朝向脱管）；**不采用 C**（`_parse_op` /
  `_normalize_operation` 只允许 `rotation == 0`，要改 C1/C4 契约）。
- **附带上报（本卡不处理）**：C4 比较 proposal 与磁盘 op-list 时会把 `rotation` 归一化（缺省补 0），
  于是「省略 rotation」与「显式 rotation: 0」被判为相同，而 writer 读原始 dict、两者输出不同
  （派生 90/270 vs 0）。建议单独记一条 finding。

### 11.1 仍需 human Owner scope grant

以上全部是 **architecture review（AI reviewer）** 的技术结论，**不构成** Owner authorization。
要改 `gates/repair_verification.py`，仍必须取得 **issue #83 上 human Owner 的明确 scope grant
permalink**（已核：现有 3 条评论中没有针对本 erratum 的人工 grant）。
