# PR1-C1-ROTATION-PRESENCE — review & acceptance record（rev2）

**用途**：本卡唯一的审查/验收记录（合并稿）。记录 contract-level review 的结论、逐条处置、
Q1–Q4 决策、验收矩阵与 C5 解锁条件。

**审查基线**：`d282c0bfdd2174e5c159a57a8e1ed4f65db37ebc`（= 实时远端 master）。
**审查者**：Astra（contract-level review，AI reviewer）—— **技术 review，不是 human Owner grant**。
**审查结论**：`CHANGES_REQUIRED_BEFORE_GRANT`。
**当前状态**：`DRAFT` / `NOT_ADMITTED` / `NOT_IMPLEMENTED`；C1 worktree 仅两份未跟踪草案（本文件为第三份）。
`tools/repair_pipeline.py`、`src/repair/**` 相对 base 无改动。

---

## 1. Blocking findings 处置

### B1 — 实现合同正文必须纳入 scope —— **已采纳**

- `docs/competition/internal/AEDL_PR1_实现合同_20260907.md` 已加入 `allowed_paths`（不再留到实施后补范围）。
- 合同须明确三条（见 `SCOPE.md` §2）：`scope` 省略→local；`rotation` 省略→**保持 absent**
  （native pin-derived orientation）、显式 0→保留，二者 canonical Proposal identity 不同；
  `place_component` 的 rotation/mirror/unit 省略→0/none/1。
- 消除 `:98`「三个固定原生参数」的歧义。

### B2 — Y4 历史政策必须冻结 —— **已采纳**（政策写入 `SCOPE.md` §9 与 envelope acceptance §D）

- 删除「记 UNKNOWN 或按新算法重算」的开放口径；改为：历史 package / raw output / parsed Proposal /
  digest / record **原字节不可改写**，用**冻结的 parser/schema/runner/commit** 验证，新结果用新合同身份。
- 两条断点（输入包先失效 `y4_dry_runner.py:195`；结果记录随后失效 `:353`）已登记。
- **独立复核（agent，只读，2026-09-23）确认 reviewer 的数字**：30 个记录目录 / 30 份 `result.json`，
  30/30 带 `raw_output_base64`；**30/30 含至少一个省略 rotation 的 add_net_label；0/30 含显式 rotation**；
  `runner_version` 全为 `y4-dry.v5`。
- 本卡**不实现兼容层**（Q4 选 C）。

### B3 — 依赖指向不存在的 PR —— **已修正**

- 已核实：`gh pr view 86` → *Could not resolve to a PullRequest*；`gh issue view 86` → **OPEN Issue**。
  原 `ref: PR-86 / required_state: merged` 无法被 `tools.admit` 验证。
- 现为 `dependencies: []` + 硬性 acceptance：admission 前填入承载 C4 修复的**真实 PR 编号**
  （`required_state: merged`）并把 base 重锚到含该 merge 的 master；Issue #86 仅作 provenance。

### B4 — 验收必须覆盖实际传递路径 —— **已采纳**

- acceptance §B（R3）要求完整路径：
  `raw Proposal → parse_proposal() → to_dict() → HostPatch.proposal / proposal_sha256
   → 序列化并重读 stage op-list → C4 PRECHECK → writer 输入语义`，两端分别到达
  `DERIVED_FROM_PIN` / `EXPLICIT_0`。
- 明文要求：测试中的 HostPatch 与 op-list **必须由 C1 解析结果构造**，不得用 raw 重新拼装绕过缺陷。
- C5 解锁条件已统一为 H 节完整顺序，删除「probe PASS 后解除」与「merge 前 BLOCKED」的歧义表述。

---

## 2. Non-blocking findings 处置

- **N1**：`$defs/AddNetLabelOp` 结构不变；建议补 description 引用 canonicalization 规则（已写入 S1）。
- **N2**：旧断言按**合同修订**拆分三条（rotation 不等 / scope 相等 / place_component 默认值相等）；
  不再使用「重签 fixture」措辞（该测试无冻结 hash 字面量）。
- **N3**：C5 侧已有 C2 erratum §12 的 expected label rotation 派生义务；本卡只交接约束，
  不改 policy / C2 / C5。

---

## 3. Q1–Q4 决策

| Q | 决策 |
|---|---|
| Q1 合同正文 | **必须 amend，同卡实施**（文件已入 allowed_paths） |
| Q2 scope presence | **继续归一化为 `local`**（源码 + 原生内存 dispatch 证据） |
| Q3 下游消费方 | 审计完成：C4 的 `rotation_mode` 不得外泄；Y4 有实质兼容影响；fixtures 不得回填；C5 @ 2460d5d 消费 `proposal.proposal_sha256` |
| Q4 历史 digest | **选 C**：历史 bytes/hash 不可改写；兼容执行能力登记为独立 follow-up card |

Q2 的证据边界（如实声明）：reviewer 的原生实验是**纯内存 dispatch 与序列化**，
**未执行 CLI 落盘、未调用 C4 `apply_stage()`、未跑 KiCad 全链**；不得描述成这些流程已通过。

---

## 4. 授权范围建议（F 节，**不是 Owner grant**）

```yaml
allowed_paths:   # 9 条
  - src/repair/patch_schema_v1.json
  - tools/repair_pipeline.py
  - tests/test_repair_contract.py
  - tasks/PR1-C1-ROTATION-PRESENCE.yaml
  - notes/pr1-c1-rotation-presence/**
  - docs/competition/internal/AEDL_PR1_实现合同_20260907.md
  - docs/HANDOFF.md
  - docs/compliance/AI_USAGE_LOG.md
  - docs/compliance/ai-usage/**
forbidden_paths: # 16 条（见 envelope）
change_budget:
  expected_files: 10
  expected_modules: [src, tools, tests, tasks, notes, docs]
  cross_module: true
  contract_change: true
  evidence_semantics_change: false   # 前提：历史证据不被重解释或改写
```

10 文件预算 = schema + 合同正文 + parser + tests + envelope + `SCOPE.md` + 本文件 + HANDOFF
+ ai-usage 条目 + 生成的 AI index。

**内容限制**：`tools/repair_pipeline.py` 仅允许改 label parser 分支，不得借同一路径实现 C5；
未列路径与仓库外历史 Y4 artifacts 只读；AI index 由既有生成器更新。

---

## 5. 验收 / 证伪矩阵（G）

| 编号 | 类型 | 必须证明 |
|---|---|---|
| R1 | regression | absent 在 ops / oplist / `to_dict()` 及序列化往返后仍无 rotation；explicit 0 始终保留 |
| R2 | regression | 两者 Proposal digest 不同；raw hash 口径不变；HostPatch 正确绑定 |
| R3 | integration | B4 完整路径分别到达 `DERIVED_FROM_PIN` / `EXPLICIT_0`；不得由 raw 重建绕过 C1 |
| R3− | negative control | 两方向 proposal/disk presence mismatch 均在 PRECHECK 阻断，writer 0 次，stage 字节不变 |
| R4 | falsification | 临时恢复旧补 0 行为 → 指定 regression RED；恢复修复 → GREEN |
| P1 | positive control | 固定 rotation presence，scope absent/local 的 parsed shape / digest / C4 comparison 相等 |
| P2 | positive control | place_component 的 rotation/mirror/unit 分别及组合省略与显式默认值等价 |
| N1 | negative control | 非法 rotation（非零/null/bool/字符串）、非 local scope、注入 public `rotation_mode` 均拒绝 |
| S1 | contract | public projection 移除 rotation default、明确 presence；`$defs` 与 place_component 不变 |
| NP1 | native probe | 新 C1→C4 路径下 DC-04 absent 90/270、explicit 0 0/0；scope 两形式字节等价 |
| H1 | historical control | 旧 Y4 bytes/hash 不变；历史环境仍可验证；新旧 identity 明确区分 |

附加硬约束：**即使某 pin 的派生角度恰为 0，也必须保留两种 presence identity**，
不得按最终角度反推或合并输入。

实施后运行：targeted regressions + 既有 C4 回归 + 全量 discover + 带 envelope 的 dev_gate。
**上述新实现验收与 falsification 本次全部 `NOT_RUN`。**

---

## 6. C5 解锁条件（H）

**C5 remains BLOCKED.** 只有完成下列全部步骤后才允许恢复：

```text
C4 presence fix human-reviewed and merged
→ C1 更新基线与真实依赖
→ Human Owner scope grant
→ C1 erratum admitted
→ implemented
→ regressions PASS
→ longitudinal C1→C4 proof PASS
→ human review
→ merged
→ C5 基于最新 master 重新 admission
```

旧 C5 receipts / evidence 视为 **stale**，不得沿用为恢复依据。

---

## 7. 本次审查的执行边界（如实声明）

- 审查**未修改任何文件**、**未运行 admission**、**未恢复 C5**；
- 本记录与 rev2 草案由 agent 按 review 处置并登记；**不构成 Owner grant、不构成 merge / approve**；
- 所有新实现验收、falsification、native 验证均为 `NOT_RUN`。

---

## 8. Owner decision（2026-09-23 工作会话，human）— **conditional scope grant**

**决定**：原则批准 rev2 的 **9-path scope** 与合同变更方向。
该批准为 **conditional scope grant**：**C4 修复 PR merge 前不得 admission / implementation。**

C4 merge 后必须先完成，才允许 `tools.admit`：

```text
1. 将真实 C4 PR 编号写入 dependencies        （本稿已提前写入 PR-88）
2. rebase 到包含该 merge 的 master
3. 更新 base SHA
4. 保持 rev2 的 9-path scope、contract_change: true 与既定 acceptance
5. 再运行 tools.admit
```

`admission PASS` 后方可实现 C1。**C1 merge 前 C5 保持 `BLOCKED`。**

### 机械闸门（不依赖人工记性）

- `dependencies` 现绑定 **PR-88**（`required_state: merged`）。#88 尚未 merge，
  故 `tools.admit` 的 merged 检查（`dependency_satisfied`）返回不满足 → **BLOCKED**。
  已用纯函数验证：`dependency_satisfied('merged', {'state': 'OPEN', 'mergedAt': None})` → `(False, ...)`。
- `exceptions` 仍刻意留空：**未填 `allow_dirty` / `allow_drift` 时无法完成 admission**
  （脏树 + 分支提交后 drift 都会 fail-closed），因此不会在 C4 merge 前形成「可 admit」的形状。
  admission 时按本 grant 补录这两个例外。
- 本轮**未运行 `tools.admit`**（遵守 conditional grant）。

### 相关 PR

- **PR #88** — `fix(c4): bind add_net_label rotation presence in PRECHECK (GH-86)`
  head `ebf9c721622b27c67bcf06ea047838f374ed1f36`，base `master`，OPEN / MERGEABLE。
- Issue **#86** 保持 OPEN；**仅在该 PR merge 到 master 后才裁关闭**。

---

## 9. 实施与验证（2026-09-24，本轮）

### 前置证明（两者缺一不可，均已取得）

- **dependency proof**：PR-88 `state=MERGED`，`mergedAt=2026-09-24T02:20:24Z`，
  `mergeCommit=b42280bd6afcc8030cb25685c3a84d21ffc38fba`。
- **refreshed base proof**：重新 fetch 后 `origin/master = b42280b`（与 mergeCommit 相同，期间无其他 commit）；
  分支已 rebase 到该 commit，`base.sha` 已重锚为 `b42280b`。
- **Admission：ADMIT / exit 0**（`--allow-dirty`；receipt 同时显示 `baseline ok | b42280b` 与
  `dependencies ok | PR-88 merged`；envelope_sha256 `01d779b90dd22f96…`）。

### 三层改动（实际落地）

| 文件 | 改动 |
|---|---|
| `src/repair/patch_schema_v1.json` | add_net_label `defaults` 去掉 rotation（保留 scope）；constraints 改写为 presence 语义；`$defs/AddNetLabelOp` 仅加 description，**结构不变** |
| `docs/competition/internal/AEDL_PR1_实现合同_20260907.md` | Operation v1 表格 add_net_label 行 + 规范化段落按 presence 两类改写 |
| `tools/repair_pipeline.py` | `_parse_op` 的 add_net_label 分支只在 raw 携带 rotation 时输出该键（仅改这一分支） |
| `tests/test_repair_contract.py` | 旧等价断言拆三条；新增 `RotationPresenceContractTests`(11) 与 `C1ToC4PresenceIntegrationTests`(3) |

### 验收 / 证伪结果（真实运行）

```text
tests.test_repair_contract            → 109 OK / exit 0
full discover -s tests                → 842 OK (skipped=16) / exit 0   （C1 前 825 → +17）
R4 falsification（恢复旧补 0 行为）    → 5 RED（含两个 integration mismatch 被误放行）
  还原后 SHA256 逐位一致               → B000AFF0892088E5… / 109 OK GREEN
```

**R1** absent 在 `ops` / `oplist` / `to_dict()` / 序列化往返后仍无 rotation；explicit 0 保留。
**R2** 两者 `proposal_sha256` 不同；`raw_sha256` 口径不变。
**R3** 完整路径（raw → parse_proposal → to_dict → HostPatch → 序列化重读 stage op-list → C4 PRECHECK）
两个形状均 `APPLIED_TO_STAGE`；HostPatch 与 op-list **由 C1 解析结果构造**。
**R3−** 两个方向的 presence mismatch 均 `BLOCKED` / `REPAIR_INPUT_DRIFT`，writer 调用 0 次，字节不变。
**P1** scope absent 与 explicit local 等价；**P2** place_component 默认值仍等价。
**N1** 非法 rotation（90/null/True/"0"/0.0）、非 local scope、注入 `rotation_mode` 均继续拒绝。
**S1** public schema 不再声明 rotation default；`$defs` 与 place_component 合同不变。

### NP1 —— 原生纵向证明（pinned akcli 0.21.0，`probe_native_c1_to_c4.py`）

```text
absent     C1 parsed op has rotation key: False | proposal_sha=d125a19d5416 | APPLIED_TO_STAGE
           label +3V3   at (34.29, 254)     angle=90
           label BOOT   at (34.29, 261.62)  angle=270
explicit0  C1 parsed op has rotation key: True  | proposal_sha=c8d485569a1b | APPLIED_TO_STAGE
           label +3V3   at (34.29, 254)     angle=0
           label BOOT   at (34.29, 261.62)  angle=0
```

⇒ 两个形状 **identity 不同**且 **物理结果不同**，raw → C1 → C5(未来) → C4 → writer 语义链闭合。

### H1 —— 历史控制（`probe_y4_history.py` / `HISTORICAL-IMPACT.txt`）

```text
historical record dirs        : 30
  without package+result pair : 15        （D 臂目录无 package.json）
load_package rebuilt OK       : 0
load_package REFUSED          : 15
first refusal                 : Y4-001-C-r1: Y4Error: public package is noncanonical or derived fields differ
```

即 reviewer 预言的 **输入包先失效** 已实测：schema 文本改动后 15 份历史 package 全部无法用新代码重建；
`load_result` 因 package 层先失败而未到达（与「先 package、后 result」次序一致）。
所有历史 artifact 的 sha256 已登记，**bytes 未改写**；兼容层不在本卡（Q4 选 C，独立 follow-up）。

### 预算偏差（如实）

`change_budget.expected_files: 10`，本轮实际 **14** 个文件。增量来自 acceptance 矩阵**强制要求**的
NP1 原生探针与 H1 历史探针（各 1 个 `.py` + 1 个原始输出 `.txt`），以及 HANDOFF / AI 台账 / 生成索引。
全部落在既有 allowed path 条目内，无越界路径。

### 待办

- 实现与验证完成，**未 commit / 未 push / 未开 PR**（等待人类授权，同 #86 先例）。
- 下一步：human review → merge → 才允许 C5 基于最新 master 重新 admission（旧 receipts/evidence 视为 stale）。

