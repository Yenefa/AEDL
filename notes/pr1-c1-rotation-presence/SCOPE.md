# PR1-C1-ROTATION-PRESENCE — scope draft（rev2，已按 Astra contract review 重写）

**Status**: `DRAFT` / **NOT ADMITTED** / **NO IMPLEMENTATION**.
**Contract-level review**: Astra，2026-09-23，**CHANGES_REQUIRED_BEFORE_GRANT**；本文件为 rev2 处置稿。
**Owner decision**: 2026-09-23（human）—— 方案 1（presence-preserving），`contract_change: true`。
**Boundary**: 本草案**未修改** `tools/repair_pipeline.py`、`src/repair/**` 或任何合同正文。

处置记录（B1–B4 / N1–N3 / Q1–Q4 / G / H）见同目录 `REVIEW-AND-ACCEPTANCE.md`。

---

## 0. 范围基线：三层同批，缺一不可

`src/repair/patch_schema_v1.json:65-73` 的 add_net_label `defaults`/`constraints` 位于
`public_op_schema`（`:49`）之下，由 `load_public_op_schema()`（`tools/repair_pipeline.py:1313-1321`）
原样投影为 proposer 看到的 `generic_op_schema` ⇒ 它是 **proposer-visible 的公开合同**。
`docs/competition/internal/AEDL_PR1_实现合同_20260907.md:98` 是同一规则的合同层表述。

因此本卡必须同批修改三层：**schema 文本 + 合同正文 + parser**。只改 parser 会同时违反 frozen schema
并让 public contract 说假话。

`$defs/AddNetLabelOp`（:165-176）**结构无须改变**（N1）：`required` 不含 rotation、属性存在时 `const 0`，
已允许两种输入形状；建议仅补 description 引用 canonicalization 规则，并加回归锁住结构不变。

---

## 1. Defect（逐行核对，master d282c0b）

```text
tools/repair_pipeline.py:838-848  _parse_op() add_net_label 分支
    rotation = 0
    if "rotation" in op: rotation = _integer(...)
    return {..., "rotation": rotation}          # 无条件带 rotation
tools/repair_pipeline.py:649       to_dict() 原样返回 self.oplist
tools/repair_pipeline.py:738       proposal_sha256 = canonical_sha256("proposal", proposal.to_dict())
```

碰撞 digest 已复现：`bb9c5c669759c9699f5934fbcb21c74fb8d5a0444d3ada500a954726c66ae137`（absent 与 explicit 0 相同）。
**这是缺陷复现，不是新实现验收通过。**

原生实证（GH-86，pinned akcli 0.21.0）：DC-04 absent 写出 `+3V3 90 / BOOT 270`；explicit 0 写出 `0 / 0`。
见 `notes/gh-86/NATIVE-EVIDENCE.md`。

---

## 2. Target semantics（合同必须明确的三条）

```text
add_net_label.scope:    omitted → local                （保持归一化；有源码与执行证据）
add_net_label.rotation: omitted → 保持 absent          表示 native pin-derived orientation
                        explicit 0 → 保留 rotation:0
                        二者 canonical Proposal identity **不同**
place_component.rotation/mirror/unit: omitted → 0 / none / 1（保持归一化）
```

**不得新增 public 字段**：`rotation_mode` 是 C4 内部 comparison semantics，不得进入 Proposal、
public projection 或实际 writer op-list（Q3）。

**不得按最终角度反推**：即使某 pin 的派生角度恰为 0，也必须保留两种 presence identity。

---

## 3. Exact change surface

1. `src/repair/patch_schema_v1.json`：`public_op_schema.operations[]` 的 add_net_label `defaults` 去掉
   `rotation`（保留 `scope: "local"`）；constraints 改写为 presence 语义；`$defs` 结构不变；
   place_component（:74-85 与 `$defs` :177-193）完全不变。
2. `docs/competition/internal/AEDL_PR1_实现合同_20260907.md`：Operation v1 表格（`add_net_label` 行）与
   规范化段落（:98）按 §2 三条改写，消除「三个固定原生参数」的歧义。
3. `tools/repair_pipeline.py::_parse_op` 的 `add_net_label` 分支：仅在 raw 携带 `rotation` 时输出该键。
   **只允许改这一个分支**，不得借同一路径实现 C5。
4. `Proposal.to_dict()`：不得回填（当前按引用返回，预计零改动，加回归守护）。
5. `ADD_NET_LABEL_KEYS`：输入仍接受可选 `rotation`（仅 0）。
6. `place_component` 分支：不变。非法非零 rotation / 非 local scope 继续拒绝。

---

## 4. Q1 —— 合同正文：**必须 amend，同卡实施**

`AEDL_PR1_实现合同_20260907.md:98` 现文「缺省的三个固定原生参数按上述值规范化后计算 Proposal digest」
可能被理解为仅指 `place_component`，也可能被扩展为通用归一化规则；本 erratum 必须消除歧义。
该文件已加入 `allowed_paths`（不再留到实施后补范围）。

---

## 5. N2 —— 旧断言是**合同修订**，不是「重签 fixture」

`tests/test_repair_contract.py::test_defaults_are_normalised_before_digest`（:191-217）**没有冻结 hash 字面量**，
而是运行时断言两个 digest 相等。故应拆成三条独立合同断言：

1. rotation presence → 两 digest **不等**；
2. scope absent / explicit local → 仍**相等**；
3. place_component 省略与显式默认值 → 仍**相等**。

不得用「重签 fixture」概括全部变化。全仓检索 `proposal_sha256` 无其他冻结字面量。
`raw_sha256 = hash_bytes(raw)` 口径不变。

---

## 6. 验收 / 证伪矩阵（G，写入 envelope acceptance）

| 编号 | 类型 | 必须证明 |
|---|---|---|
| R1 | regression | absent 在 ops / oplist / to_dict() 及序列化往返后仍无 rotation；explicit 0 始终保留 |
| R2 | regression | 两者 digest 不同；raw hash 口径不变；HostPatch 正确绑定 |
| R3 | integration | 完整路径 raw → parse_proposal → to_dict → HostPatch → 序列化重读 stage op-list → C4 PRECHECK |
| R3− | negative | 两方向 presence mismatch 均在 PRECHECK 阻断，writer 0 次，字节不变 |
| R4 | falsification | 恢复旧补 0 行为 → 指定 regression RED；恢复修复 → GREEN |
| P1 | positive | 固定 rotation presence，scope absent/local 的 shape / digest / C4 comparison 相等 |
| P2 | positive | place_component 的 rotation/mirror/unit 省略与显式默认值等价 |
| N1 | negative | 非法 rotation（非零/null/bool/字符串）、非 local scope、注入 public rotation_mode 均拒绝 |
| S1 | contract | public projection 移除 rotation default、明确 presence；`$defs` 与 place_component 不变 |
| NP1 | native | 新 C1→C4 路径下 DC-04 absent 90/270、explicit 0 0/0；scope 两形式字节等价 |
| H1 | historical | 旧 Y4 bytes/hash 不变；历史环境仍可验证；新旧 identity 明确区分 |

R3 的测试中，HostPatch 与 op-list **必须由 C1 解析结果构造**，不得用 raw 重新拼装绕过缺陷。

---

## 7. Non-goals

- 不改 `$defs` 的 JSON Schema **结构**；不新增 public 字段（尤其 rotation_mode）；
- 不扩到 `place_component`；不改 `tools/akcli_adapter.py`（C4）；不实现 C5；
- **不改 Y4 runner / 不加兼容层**（Q4 选 C：兼容执行能力登记为独立 follow-up card）；
- N3：只向 C5 **交接**「expected label rotation 必须派生」这一既有约束（C2 erratum §12），
  不改 policy / C2 / C5，也不得把静态 policy 的 `rotation: 0` 当成所有标签的实际方向。

---

## 8. Q2 / Q3 / Q4 结论

**Q2 —— scope 继续归一化为 `local`。** 有源码与执行证据：pinned `akcli-kicad 0.21.0` 的
`akcli/writers/handlers/labels.py:78` 使用 `op.get("scope", "local")`，后续标签类型/UUID/输出都用解析后的值。
reviewer 另做了原生 writer 的**纯内存 dispatch 与序列化**：scope absent 与 explicit local 输出字节完全相等
（rotation absent → 90/270；explicit 0 → 0/0）。**该实验未执行 CLI 落盘、未调用 C4 `apply_stage()`、
未跑 KiCad 全链，不得描述成这些流程已通过。**

**Q3 —— 下游消费方审计**：
- C4：master 仍含旧 normalization；独立修复用 internal `rotation_mode` 区分 presence；该字段不得外泄。
- Y4：存在 package/result 重建依赖（实质兼容影响，见 §9）。
- tests：需改 C1 默认值等价断言；Y4 测试中直接读 `rotation` 的用例测的是 `place_component`，保持。
- fixtures：DC-01/02/04/05 的 native label ops 均省略 rotation；**不得回填或刷新冻结 fixture**。
- C5 @ `2460d5d`：`runtime_bindings()`（`tools/repair_pipeline.py:1813`）消费
  `proposal.proposal_sha256`（:1895）；`run_round` / `bind_policy` 尚未实现。恢复时必须保留新 parser、
  重新生成绑定与 receipts。
- 其余路径未发现「所有 parsed add_net_label 必有 rotation」的访问假设。

**Q4 —— 选 C：兼容执行能力登记为独立 follow-up card。** 见 §9。

---

## 9. Y4 历史政策（B2，grant 前必须冻结；本卡不实现兼容层）

**独立复核（2026-09-23，只读）**：`gh56-y4-dry/r21/run` 共 **30** 个记录目录 / 30 份 `result.json`，
30 份均带 `raw_output_base64`；**30/30 含 add_net_label 操作且至少一个省略 rotation**，
**0/30 含显式 rotation**；`runner_version` **全部为 `y4-dry.v5`**（无 parser / commit identity 字段）。

两条兼容断点（reviewer 指出，均已核对源码位置）：
1. **输入包先失效**：`load_package()`（`tools/y4_dry_runner.py:195`）经 `build_package()` 用当前 public
   schema 重建旧包 → schema 文本改动后旧包因字节不一致被拒，甚至到不了 Proposal parser。
2. **结果记录随后失效**：`load_result()`（`:353`）重跑 `collect_result()`；旧输出省略 rotation，
   parsed shape / hash 改变。

**冻结政策（本卡立场）**：
- 历史 package / raw output / parsed Proposal / digest / record **原字节不可改写**；
- 历史记录用**冻结的 parser / schema / runner / commit** 验证；
- 新结果使用新合同身份，不混入旧实验记录；
- 最新 executable 无法重建旧记录 **≠** 旧记录损坏或应改 `UNKNOWN`。
- `runner_version` 字符串**不足以**做新旧 dispatch；历史环境靠外部冻结 provenance 绑定，
  未来运行须冻结可区分的合同身份。

若产品要求「最新 executable 必须能验证旧记录」，则该兼容功能成为该产品要求的 merge blocker，
需另行授权实现**显式版本 dispatch（package + result 两层）**，禁止失败后 heuristic fallback。
当前不塞入 C1 卡。

---

## 10. 依赖（B3）

上一版写 `ref: PR-86 / required_state: merged` 是**错的**：#86 是 **OPEN Issue**，不是 PR
（已核：`gh pr view 86` → Could not resolve；`gh issue view 86` → OPEN）。`tools.admit` 对 `merged`
依赖执行 `gh pr view`，无法验证。承载 C4 修复的真实 PR 目前尚不存在。

故 `dependencies: []`，并在 acceptance 中硬性要求：admission 前填入真实 PR 编号并把 base 重锚到
含该 merge 的 master；Issue #86 仅作 provenance。

---

## 11. Sequencing（H，统一口径）

```text
C4 presence fix human-reviewed and merged
→ C1 更新基线与真实依赖（吸收 C4 代码、重锚 base、填真实 PR 依赖）
→ Human Owner scope grant
→ C1 erratum admitted
→ implemented
→ regressions PASS（含 R3 完整路径 / R4 证伪 / NP1 native）
→ longitudinal C1→C4 proof PASS
→ human review
→ merged
→ 才允许 C5 基于最新 master 重新 admission
```

旧 C5 receipts / evidence 必须视为 **stale**，不得沿用为恢复依据。
**本卡 merge 前 C5 保持 `BLOCKED`。**
