# ARH Decision Sheet — RFC §7 拍板清单（一页版）

> 关联：`docs/specs/AEDL_AGENT_RUNTIME_RFC.md`（§5 分歧 D1–D7 / §6 开放问题 / §7 拍板清单）｜ **ADR-016**
> 状态：**D1–D7 与 B1–B5 已批复**（Owner 2026-09-28 会话原文：「批复，没有本阶段不做的，全量全速全质推进！开始」，按本表 Recommended 执行）；文档本身 `PENDING_HUMAN_REVIEW`
> 生成：2026-09-28 ｜ 分支：`docs/agent-runtime-rfc`
> 用法：逐条批复（APPROVED / REJECTED + 一句理由）。
> **A 组（D1–D4）是 benchmark 口径不是功能选择，必须在 Phase 1 写第一行 harness 代码之前定**——晚定 = §4.5 冻结项失效 = 重跑。B 组可随实现评审同批。

---

## A. 主表：RFC §5 的七条分歧

### D1 — fingerprint 语义

- **Decision**：stall 判定的 finding fingerprint 输入是否维持 `(code, message)` 冻结？
- **Options**：
  - (a) 维持冻结；"换措辞绕过 stall" 由 Harness 预算/去重兜底，记为 V1 已知限制
  - (b) severity 过滤（boardsmith 式只 hash error 级）或 `details` 入指纹 → **契约变更**（改 `state.py`）
- **Recommended**：**(a)**（RFC §5 D1 裁决：V1 不一次改两头）
- **Impact if delayed**：stall 口径悬空 → 每轮数据有效性未定；且 D1.6（fault 的 `message` 必须随修复变化，否则 `INVALID_FAULT`）无法在 fault set 冻结前验证 → 阻塞 §4.5 冻结项 1、7，直接拖住 Stage 0 与 Pilot
- **Affected files**：V1 **不改代码**（`sandbox_runtime/src/aedl_sandbox/state.py` 保持冻结）；影响 RFC §4.1 D1.6、fault 筛选谓词、`stall_rate` 口径

### D2 — `invalid_proposals` 计数

- **Decision**：计数点在哪、被丢弃的重试是否计入、是否仍为 `converged_strict` 的必要条件？
- **Options**：
  - (a) 统一由 **Harness 预校验层**计数（含输出侧丢弃的重试），与 `policy_denied_runs` 严格分列；**保留**其为 `converged_strict` 必要条件
  - (b) 计数口径同 (a)，但从 `converged_strict` 中**移除**该必要条件（收敛只看 verifier 结果）
  - (c) 不统一：Harness 与 policy 各计各的（RFC 已否：会漏计）
- **Recommended**：计数口径取 (a)；**本条真正要拍的是"必要条件去留"**——保留则"LLM 不绕过 Trust Plane"有硬指标支撑，移除则模型能力分更干净但安全性主张变弱
- **Impact if delayed**：`converged_strict` 属 **§4.5 冻结项 2** → 开跑后改 = 重跑全量
- **Affected files**：RFC §4.1、§4.5 冻结项 2；未来 harness 预校验层 + `benchmark_runner`（均尚不存在）

### D3 — 上下文窗口阈值

- **Decision**：`code_window` 行数与 attempt_history 折叠深度取多少？
- **Options**：
  - (a) 40 行 / 最近 1 轮原文折叠（[04] 保守值，全部标 `TO_VERIFY`），pilot 中 A/B 40 vs 100
  - (b) 100 行（[01 §2] 实测 30/100/整文件 = 14.3/18.0/12.7，100 最优）
  - (c) 整文件 dump（实测最差，且违反 never-dump 原则）
- **Recommended**：**(a)**
- **Impact if delayed**：中低——`max_repairs=3` 使轮次天然有界；但晚定则 pilot 没有对照基线，A/B 无从谈起
- **Affected files**：未来 `context_builder.py`、`inspect_artifact` 工具 schema（RFC §2.2）、pilot 设计

### D4 — 预算归属（Budget & Stop）

- **Decision**：LLM 层预算（调用数 / token / wall-clock / 连续无效提案 / 格式错误）由谁强制？
- **Options**：
  - (a) **双层**：图内完全复用现有熔断（`max_repairs` / fingerprint / `repair_count`，不新造）；图外 LLM 预算由 **Harness 进程内强制**，超限记 `INVALID_RUN`
  - (b) orchestrator 加四条硬阈值（[01 A2]）→ **代码变更**，需另开任务/ADR
- **Recommended**：**(a)**
- **Impact if delayed**：N6 是五项 BLOCKING 之一 → 不定则 harness budget 模块无法落地，Phase 1 无法开工；同时影响 `cost_per_converged` 的成本归属口径（§4.5 冻结项 2 关联）
- **Affected files**：未来 ARH-N6 Budget & Stop Controller（独立模块，不得 fold 进其他文件）；RFC §1.2 该行；`orchestrator.py` **V1 不改**

### D5 — receipt `sequence` 字段位置

- **Decision**：L0 上下文的 `receipts_digest` 用什么字段？
- **Options**：
  - (a) **以代码为准**：`{event_type, hash12}`（`state.encode_receipt` 现有字段）；轮次序号由 `TrajectoryRecorder.round`（派生自 `repair_count`）提供
  - (b) 保留 [04] 假设的 `sequence` 字段 → 改 `state.py`（契约变更）
- **Recommended**：**(a)**
- **Impact if delayed**：低（benchmark 未跑，不存在重跑）；但实现评审前必须定，否则 [04] 报告表格与 schema 不一致
- **Affected files**：未来 `context_builder.py`；`docs/research/agent-runtime/04-context-engineering.md` 表格按 (a) 修订

### D6 — allowlist：投影还是 dump

- **Decision**：上下文里的合同 allowlist 是字段投影还是 `engine.document` 全量序列化？
- **Options**：
  - (a) **投影**：按字段白名单取枚举所需最小集
  - (b) 全量 dump（= [06] T-14 侧信道风险，RFC 已否）
- **Recommended**：**(a)**
- **Impact if delayed**：安全边界，实现前定即可；投影字段清单留实现评审确认
- **Affected files**：未来 `context_builder.py`、prompt 资产；`policy/engine.py` 不改

### D7 — 只读检索是否需要 CapabilityGrant

- **Decision**：V1 的 read 能力由什么治理？
- **Options**：
  - (a) **V1 不引入 grant**：读能力 = Harness 工具白名单 + 作用域（current run / candidate 子树 / 授权合同与证据 allowlist），显式记录为"边界纪律而非机制保证"
  - (b) V1 即引入 `READ` 词表 + grant → 依赖 G1 对账，而对账**当前未实现**（恒 fail-closed）→ 现实不可行
- **Recommended**：**(a)**；V2 引入 grant 的前置 = G1 对账实现（RFC §2.5）
- **Impact if delayed**：决定 RFC §2.1/§2.2 的治理措辞与 never-grant 第 11 条边界；不阻塞 Phase 1（按 (a) 已可开工）
- **Affected files**：RFC §2.1、§2.2、§2.3；`policy/engine.py` **V1 不改**

---

## B. 次级拍板（RFC §7 其余五项）

| # | 事项 | 建议 | 拍板时点 |
|---|---|---|---|
| 1 | 接入放行 = §2.5 五项 BLOCKING（N2/N3/N4/N6/N8）+ G1/G8 保持不启用 | 确认为真实 LLM 接入的前置清单 | **Phase 0（本表）** |
| 2 | O-15：`RepairContext` 是否公共契约 → 是否需 ADR 才能冻结 | 按内部契约处理；若将来进 OPEN_OUTPUTS 再升 ADR | Phase 1 前 |
| 3 | A 层真实缺陷分母：preflight BLOCKED 的缺陷只测 fail-closed、不进收敛率分母 | 接受（[05 D2.1]） | Phase 0（本表） |
| 4 | Benchmark 档位：Pilot 200 / 主实验 1,860 / 削减 900 | 先 pilot（只验流程，不出能力结论）→ 拿 `p̂` 与方差 → 再定主实验 | fault set 冻结时 |
| 5 | G3：`approved_by` 白名单/角色校验是否为生产接入前置 | 列为生产前置；**benchmark 的"审批脚本化恒 APPROVED"仅限评测环境，不是生产特性** | 生产化前（O-26） |

---

## C. 本阶段明确不做（防跑偏）

> **状态更新（2026-09-28 Owner 批复，原文见页首）**：C 组不再作为阶段门禁。
> - C-1 的**顺序要素**升格进 ADR-016（拍板 → 文本类冻结 → implementation），提速但不跳步；
> - C-2（G1 对账）、C-3（竞赛叙事改名）、C-4（Multi-Agent / aedl-eval 拆分）转为**按需立项**，不再预先排除；
> - C-5：push 待明确指令执行，**merge 到 master 永远留给人类**（AGENTS §3.7/§14，不因批复解除）；
> - **V1 单 Repair Agent 属 RFC 科学设计（实验变量控制），不随 C 组解除**；改多 Agent = 换实验，须先改 RFC/ADR。
>
> 以下原文保留，作为解除前的历史记录：

1. **不写 implementation 代码**——顺序固定为：本表拍板 → ADR → §4.5 冻结 → implementation branch。
2. **不实现 G1 grant 对账**——那是 "Execution Authority Binding"（V2 Security Hardening），单独任务 + ADR，不伪装成已有能力，也**不做当前 demo**；V1 可演示的只有权威字段 schema 拒绝。
3. **不改竞赛叙事措辞**——"autonomous design" → "Verified Agentic Engineering Loop" 属 §8 竞赛材料口径，须单独触发 `FUSION_MAP` / `SUBMISSION_CHECKLIST` 层面处理，不塞进本轮两个文档。
4. **不做 Multi-Agent / memory / tool marketplace**；`aedl-eval` 仓库拆分（runtime 500–1000 行 vs benchmark 工具链分账）等 benchmark runner 成型后再议。
5. **不 push / 不 merge** 本分支——先 ADR，后 implementation branch，RFC 与代码不一起滚。

---

## D. 拍板回执（人工填写）

| # | 决定 | 批复（APPROVED / REJECTED / 修改后 APPROVED） | 人 | 日期 |
|---|---|---|---|---|
| D1 | 维持 `(code, message)` 冻结指纹 + Harness 预算兜底；severity/details 属 V2 契约变更 | **APPROVED**（按 Recommended） | Owner（会话批复） | 2026-09-28 |
| D2 | 计数统一在 Harness 预校验层；`invalid_proposals == 0` **保留**为 `converged_strict` 必要条件 | **APPROVED**（按 Recommended） | Owner（会话批复） | 2026-09-28 |
| D3 | 40 行 / 最近 1 轮折叠（标 TO_VERIFY），pilot A/B 40 vs 100 | **APPROVED**（按 Recommended） | Owner（会话批复） | 2026-09-28 |
| D4 | 双层预算：图内复用既有熔断；图外 LLM 预算由 Harness 强制，独立 ARH-N6 模块 | **APPROVED**（按 Recommended） | Owner（会话批复） | 2026-09-28 |
| D5 | `receipts_digest = {event_type, hash12}`（以代码为准），[04] 表格实现时修订 | **APPROVED**（按 Recommended） | Owner（会话批复） | 2026-09-28 |
| D6 | allowlist 字段投影，禁 `engine.document` 全量 dump | **APPROVED**（按 Recommended） | Owner（会话批复） | 2026-09-28 |
| D7 | V1 不引入 READ grant；读能力 = 工具白名单 + 作用域；V2 前置 = G1 对账 | **APPROVED**（按 Recommended） | Owner（会话批复） | 2026-09-28 |
| B1 | 接入放行 = §2.5 五项 BLOCKING（N2/N3/N4/N6/N8）+ G1/G8 不启用 | **APPROVED** | Owner（会话批复） | 2026-09-28 |
| B2 | `RepairContext` 按内部契约处理，进 OPEN_OUTPUTS 时再升 ADR | **APPROVED** | Owner（会话批复） | 2026-09-28 |
| B3 | A 层 preflight BLOCKED 缺陷只测 fail-closed、不进收敛率分母 | **APPROVED** | Owner（会话批复） | 2026-09-28 |
| B4 | 先 pilot（只验流程）→ 拿 `p̂` 与方差 → 再定主实验档位 | **APPROVED** | Owner（会话批复） | 2026-09-28 |
| B5 | `approved_by` 白名单列为生产接入前置；脚本化 APPROVED 仅限评测环境 | **APPROVED** | Owner（会话批复） | 2026-09-28 |

> 批复渠道：本会话（无 Issue/PR 线程），原文引用见页首；决议全文见 `docs/compliance/DECISIONS.md` ADR-016。
