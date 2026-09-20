# PR1-C5-ERRATUM — C2 new-source-object expected semantics（函数级补丁草案）

> **状态：DRAFT — 未应用任何代码改动。**
> 基线：`669aa16`（origin/master）。`gates/repair_verification.py` blob `88a311e17763e0ac83f33c5fd499c2a1852b2c44`
> （与 C5 HEAD `2460d5d` 逐字节相同，已用 `git hash-object` 双向核对）。
> Owner scope grant：**PENDING**（issue #83）。grant 之前不得改 `gates/repair_verification.py`。
> 配套：`tasks/PR1-C5-ERRATUM.yaml`。

---

## 0. TL;DR — 六问直答

| # | 问题 | 本草案结论 |
| --- | --- | --- |
| 1 | 新对象 expected representation | 按 identity 分流的 **closed semantic expectation**，与旧形状互斥；不带 `descriptor` / `semantic_ast_sha256` |
| 2 | `_align_new()` 唯一匹配 | 新 label 按 `(name, scope, point_nm, rotation)` 恰好一对一；新 symbol 仍按 reference，另加 Q6 绑定断言 |
| 3 | `_delta()` 如何消费 | **不加 `new:` 分支**。语义投影在 `_canonicalize_new_objects()` **一次**完成，两侧同形状，`_delta` 保持 shape-blind |
| 4 | `_projection()` fail-closed | **不加分支**。mask 条件是整份 `{identity, kind, semantics}` 相等 —— **identity 相等不构成 mask 理由** |
| 5 | existing / removed 不放松 | §6 逐条列出零改动代码路径 + R1..R11 回归矩阵 |
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
- `_integer` / `_text` / `_identifier` 是**纯校验器，返回 `None`** —— 上面刻意不写成
  `x = _integer(...)`（这是 C3 曾踩过的真实坑，见 HANDOFF 2026-09-18 段）。
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
| R9 | new symbol source-object UUID ≠ aligned component_uuid | FAIL（见 §6.3） |
| R10 | expected new object 混用形状 | FAIL（`ObservationError`） |
| R11 | 改新对象语义 → `protected_projection_sha256` **不变**（before 侧对照） | 相等断言 |

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

## 7. 残留自由度（**需要 Owner 明确接受或加严**）

erratum 之后，新 symbol 的真实子树不再与「完整未来 AST」比较，只由下列事实约束：

- `observe_source:1023-1025` / `:866-868` 的**结构白名单**（未知字段 fail-closed）；
- `lib_id` 必须解析到内嵌 `lib_symbols`（`:870-871`）；
- pin inventory 必须等于库定义（`:904-905`）；
- Reference/Value 必填、Footprint 有 fallback（`:874-875`、`:910`）；
- `lib_definition_sha256`（`:909`）/ `pin_definition_sha256`（`:915`）逐字节绑定；
- components / pins / partitions 由 `_prepare:472-491` exact 比较。

**因此残留的未绑定自由度是**：instance 子树里**非电气**的
`property` 名称集合、`instances` 内容、`exclude_from_sim`、`fields_autoplaced` 等 writer 噪声。

**可选加严（建议，但须先实测校准）**：

```text
set(instance_properties) == set(library_properties) | {"Reference", "Value", "Footprint"}
```

把「额外 property」也关掉。**但这必须先拿到 C4 的真实 native AFTER**（DC-04 / DC-05），
确认 akcli 0.21.0 实际写出的 property 集合，否则会 false-negative。

> **请 Owner 裁定**：接受残留自由度（writer 噪声不属授权内容，符合合同 L152 的
> 「无附加电气结构」），还是要求加严到 property 名称集合闭合？

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
                          new R1..R11
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
  expected_files: 7
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

## 11. 请 Owner 一并裁定

1. **Q1 形状**：新 symbol 的 `semantics` 是否只保留 `{reference}`（本草案），
   还是要求把 position/rotation/mirror/value/footprint/assembly flags 也复制进来？
   本草案主张**不复制**：这些字段已由同一份观测的 `components` 段在
   `_prepare:472-491` exact 比较，复制会产生第二个真相源。
2. **§7 残留自由度**：接受 writer 噪声不属授权内容，还是加严 property 名称集合闭合？
3. **Q3 收敛点**：同意「`_delta` / `_projection` 零改动 + 语义投影收敛到
   `_canonicalize_new_objects` 一处」，还是在 `_delta` 内显式加 `new:` 分支？
4. **R7 的 mask 断言**：是否同意把「语义错的新对象必须仍出现在 after 投影里」
   写成显式断言（而不只是断言整体 FAIL）？
