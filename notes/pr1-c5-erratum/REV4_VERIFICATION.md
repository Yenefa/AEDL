# PR1-C5-ERRATUM rev4 — review 逐条核对（对照 rev1）

> 目标文件：notes/pr1-c5-erratum/C2_NEW_SOURCE_OBJECT_ERRATUM_DRAFT.md @ HEAD 9fa9b9e（rev4）。
> 本文件由 pwsh 从该文件**抽取行区间**生成，逐字一致，不是复述。
> 用途：review 连续两轮引用的文本属于 **rev1**（commit 13b180f）；本件给出 HEAD 的真实内容。

## 0. 结论

| blocker | review 引用的 rev1 文本 | HEAD 现状 | 修正 commit |
| --- | --- | --- | --- |
| A | _integer / _text / _identifier 都「返回 None」 | 不存在；见 §1（第 171-177 行） | 91a58ca (rev3) |
| B | 残留自由度含 instances 内容、exclude_from_sim 等 writer 噪声 | 不存在；见 §2a-2d（第 415-496 行） | f01c09d (rev2) |
| C | regression matrix 只有 R1-R11 / §8 写 new R1..R11 | 不存在；见 §3a-3b（第 382-385、513 行） | f01c09d (rev2) / 9fa9b9e (rev4) |

全工作区 ripgrep：new R1..R11 -> 0 hits；纯校验器，返回 -> 2 hits，且都在「rev1 旧文本」引用行内。

## 1. Blocker A — §2.2 返回值说明（HEAD 第 171-177 行原文）

    - **返回值必须分清**（这是 C3 曾踩过的真实坑，见 HANDOFF 2026-09-18 段）：
      - **返回规范值**：`_text`（`return value`，`:92-95`）、`_identifier`（`return text`，`:101-112`）、
        `_sorted_unique`（`return ordered`，`:149-156`）、`_index`（返回映射，`:159-160`）；
      - **纯校验器、返回 `None`**：`_closed`（`:87-89`）、`_integer`（`:115-117`）、`_sha`（`:120-122`）、
        `_uuid`（`:125-132`）、`_identity`（`:135-146`）。
    - 因此上面的代码里 `reference = _identifier(...)` 是**正确**的（它返回规范化 reference）；
      而 `_text(semantics["name"], ...)` 与 `_integer(coordinate, ...)` 只做校验、**不得赋值**

## 2a. Blocker B — §7.1 v1 边界（HEAD 第 415-427 行原文）

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

## 2b. Blocker B — §7.2 instances 不是自由度（HEAD 第 429-448 行原文）

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
    

## 2c. Blocker B — §7.3 exclude_from_sim 收紧（HEAD 第 449-476 行原文）

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
    

## 2d. Blocker B — §7.5 residual freedom 收窄（HEAD 第 477-496 行原文）

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

## 3a. Blocker C — 回归矩阵 R9-R12（HEAD 第 382-385 行原文）

    | R9 | new symbol source-object UUID 未绑定到 aligned `component_uuid`（reference 可以一致） | FAIL —— **integration-path test**：必须走真实 AFTER full object → `_align_new` → `_canonicalize_new_objects` → `compare_delta` + `compare_protected`，不得只单测 helper（见 §6.3）。原 R13 已按 review 意见折入本条，不再单列 |
    | R10 | expected new object 混用形状 | FAIL（`ObservationError`） |
    | R11 | 改新对象语义 → `protected_projection_sha256` **不变**（before 侧对照） | 相等断言 |
    | R12 | new symbol 携带 `exclude_from_sim = yes` | FAIL（v1 只允许 false/absent，见 §7.3）；必须**同时**进入 §6 矩阵 + envelope acceptance + §8 impact，防止实现者只改描述不写 gate |

## 3b. Blocker C — §8 implementation impact（HEAD 第 513 行原文）

                              new R1..R12（R12 = new symbol exclude_from_sim=yes -> FAIL）

## 4. 核验命令（不要用缓存快照）

    git show HEAD:notes/pr1-c5-erratum/C2_NEW_SOURCE_OBJECT_ERRATUM_DRAFT.md > TEMP/d.md
    Select-String -Path TEMP/d.md -Pattern '名称集合、.instances.'   # 期望 0
    Select-String -Path TEMP/d.md -Pattern '^\| R12 '                # 期望 1
    Select-String -Path TEMP/d.md -Pattern '返回值必须分清'           # 期望 3
    Select-String -Path TEMP/d.md -Pattern 'new R1\.\.R11'           # 期望 0
