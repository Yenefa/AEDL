# AEDL — 项目状态（2026-10-05）

> 单点真源。接手请先读本页，再读 `docs/HANDOFF.md` 顶部与 `docs/compliance/DECISIONS.md` 的
> ADR-022（自治模式）与 ADR-023（RepairBench 战略）。
> 本页只做**聚合与导航**，不新增事实；每条主张都给出可核验的仓库证据。

## 1. 运行模式

| 项 | 现状 |
| --- | --- |
| 模式 | `AEDL-AUTO`（AI 全自动驾驶），Owner 2026-10-04 授权 |
| 授权来源 | ADR-022；`AGENTS.md` §0A |
| 终止记录 | **保留为历史**（commit `7a82307`），效力已被 ADR-022 取代，未删未改写 |
| 仓库 | `Yenefa/AEDL`，private，**未归档**、可写 |
| 验收状态 | 双泳道：`人工审核`（`PENDING_HUMAN_REVIEW`，永不代签 `HUMAN_REVIEWED`/`ACCEPTED`）＋ `自主验收`（上限 `AI_ACCEPTED`，fail-closed 校验，两泳道互斥） |
| CI | **可用**，跑在自托管 runner（`actions-runner-aedl`，不计费）。判别红灯性质看 `runner_name` 是否为空 + `steps_count==0` |
| 花费硬上限 | 模型 API 累计 **≤ 1.00 CNY**，`tools/repairbench_budget.py` fail-closed，无运行时开关可绕过 |

## 2. 已落地并可复现

| 模块 | 状态 | 证据 |
| --- | --- | --- |
| 需求/门禁/交付链、Sandbox | PASS | `python -m tools.dev_gate` |
| 修复链 C1–C4、C5 单轮事务、ARH V1 | PASS | ADR-001..021；`tests/test_repair_pipeline.py` 336 OK |
| 首条真实 LLM 修复 episode | DC-02 FAIL→PASS | `EVID-20261001-001` / `-002` |
| 自治验收泳道 | PASS | `tools/build_ai_usage_index.py`，11 条相关回归 |
| **AEDL RepairBench v0.1** | **可运行** | 见下节 |

门禁最近一次全量结果：main **1256 OK (skipped=30)**、sandbox **574 OK (skipped=3, xfail=1)**、
secret_scan 通过、`ai_usage_ledger` **159 条 in sync**。

## 3. RepairBench v0.1 —— 已交付的 benchmark

位置 `benchmarks/repairbench_v0_1/`，运行：

```text
py -3.9 -m tools.repairbench --arm noop                      # 对照：必须过不去
py -3.9 -m tools.repairbench --arm oracle                    # 对照：答案必须能到
py -3.9 -m tools.repairbench --arm aedl_contract_deterministic
py -3.9 -m tools.repairbench --arm baseline_generic          # 需模型，受 1 元上限
py -3.9 -m tools.repairbench --arm aedl_contract             # 需模型，受 1 元上限
py -3.9 -m tools.repairbench_budget                          # 查花费
```

### 结构

- 5 集，每集锁定一条**冻结合同**规则为目标；合同由 `tools/derive_repairbench_contract.py`
  从 `gates/contracts/m2_schematic_contract_v1.json` **机械投影**生成，并用冻结校验器自检。
- 三层指标（ADR-023）：Primary Oracle（目标规则 FAIL→PASS）／Regression Guard（非目标规则不得被弄坏）／
  Structural Preservation（对 `acceptance_v1.json`）。
- **答案泄漏已堵**：`repair_ops.json`（ground truth）与 `fault.kicad_sch` 同目录，
  求解臂只拿到 `fault.kicad_sch`。

### 范围分层（为什么 headline 只有 2 集）

`connectivity_label`（DC-01/02，**可解**，进 headline）与 `add_component`（DC-03/04/05，
**修复腿尚未闭环**，单列不进 headline）。

⚠️ **旧结论已被推翻**：`placement_source_audit_20261005.md` 曾判定「冻结 PCB 与 DC 夹具坐标系不一致」。
合成实验证明**不成立**——schematic 实测 R9 = (34.29, 257.81) mm，与答案键 `acceptance_v1.json`
**完全一致**；不一致的是**冻结 PCB**（(1.45, 22.50) mm）。更正见该文件末尾的追加段落。

### 已验证的两条正面结论（`synthesis_findings_20261005.md`）

1. **冻结合同在真实 M2 板上 5 条规则全 PASS** ⇒ 合同可满足（此前只证明它能判夹具的错）。
2. **缺件夹具可从冻结源干净合成**：`delete_component(R9)` + `delete_object(<其 net 上的 13 个 label>)`
   ⇒ rc=0、解析干净、`ESP32_GPIO9_PULLUP` 恰好 fail、其余 4 条仍 pass。

### 真实结果（离线臂，零花费）

| 臂 | HEADLINE(in-scope) | ALL | 说明 |
| --- | --- | --- | --- |
| `noop` | 0/2 | 0/5 | 对照成立：不能通吃 |
| `oracle` | 2/2 | 5/5 | 对照成立：可解；out-of-scope 也过是因为它读答案键 |
| `aedl_contract_deterministic` | 0/2（守卫关时 1/5 全量） | — | 合同推导，受 net-split 守卫影响 |

**L1 null result（`EVID-20261005-002`）**：同模型/同任务/同产物/同预算下，
`baseline_generic` 3/5 与 `aedl_contract` 3/5 **逐集完全相同** ⇒
**目前没有证据支持「冻结合同提升修复能力」**，ADR-023 Kill Gate 假设 **H1 得不到支持**。

## 4. 已知缺陷与下一步（按逻辑顺序）

| # | 项 | 性质 | 证据 |
| --- | --- | --- | --- |
| 1 | in-scope 仅 2 集 | 样本极小，任何差异都不是结论 | `episodes_v1.json` |
| 2 | `add_component` 修复腿未闭环 | **缺件夹具已能干净合成**（目标规则恰好 fail、其余 pass）；修复腿因 `place_component` 未传旋转角而 fail-closed | `synthesis_findings_20261005.md` |
| 3 | `--strict-nets` 过度拦截 | 把期望修复也拒了（DC-02），确定性臂 1/5→0/5 | `RESULTS_20261005.md` |
| 4 | 合同只断言器件值、不断言存在 | 补器件类无法从合同推导 | `EVID-20261005-001` |
| 5 | 80 条远端分支 0 条可证明全落地 | 未清理（ADR-022 禁止销毁未落地内容） | `notes/branch-unlanded-audit-2026-10-04.md` |
| 6 | PR #65/#70 需时效更正附注；#93 断言 8/9 与现 master 冲突；#94 RES-012 撞号 | 未落地 | GitHub |

**下一步的唯一逻辑序**：造**自带布局意图、与合同同坐标系**的夹具 → 解锁 #2 → 扩规模解 #1 →
再谈 #3 的按 net 对合法性检查。#5/#6 是债务清理，与 benchmark 主线并行。

## 5. 红线（不因自治而放宽）

下单/回件/焊接/上电/C 级实测、花钱与他人账户、`manufacturing_release=true`、
`HUMAN_REVIEWED`/`ACCEPTED`、改写历史与冻结哈希、虚假 PASS/Benchmark/截图 —— 全部不可委托。
详见 `AGENTS.md` §0A.5。
