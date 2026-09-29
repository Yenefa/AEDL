# AEDL Agent Runtime RFC — ARH（AEDL-native Repair Harness）V1

> **状态：`PENDING_HUMAN_REVIEW`**
> **生成日期：2026-09-28**
> **输入报告（唯一外部论据来源，全部位于 `docs/research/agent-runtime/`）：**
> 1. `01-harness-landscape.md`（Harness Agent：coding harness 架构与 ACI）
> 2. `02-repair-loop.md`（Repair-loop Agent：修复循环实证）
> 3. `03-eda-agents.md`（EDA Agent：硬件 Agent 的 repair 与写路径）
> 4. `04-context-engineering.md`（Context Agent：RepairContext Schema 草案）
> 5. `05-eval-protocol.md`（Eval Agent：Benchmark Protocol 草案）
> 6. `06-red-team-trust-bypass.md`（Red-Team Architect：T-01..T-16 威胁）
>
> 引用格式：`[01 §2]`、`[02 D5]`、`[06 T-07]`、`[05 D1.3]`。各报告的 D/T/G/N 编号相互独立，引用必须带报告号。
> 本 RFC 不做新的外部联网研究；仓库事实引用自 `sandbox_runtime/src/aedl_sandbox/{protocol,state,orchestrator,adapters}.py`、`policy/engine.py`、`trust/store.py` 的静态阅读（**NOT_RUN**，未执行任何测试）。

---

## 0. 前提与范围

**唯一工程问题**：怎样把真实 LLM 接回 AEDL，让它根据 verifier findings 反复修复，同时**绝不绕过现有 Trust Plane**。方向已由项目方给定，本 RFC 不重新论证，只填细节。

**已定骨架（不许改）**：LangGraph KEEP（外层 routing/checkpoint，ADR-008）｜`RepairPort.propose(run_id, candidate_id, findings) -> PolicyRequest` KEEP（frozen）｜Trust Plane KEEP（policy / transaction / fresh read-back / evidence / human approval）｜coding harness REFERENCE ONLY｜ARH = THIN、AEDL-NATIVE。

**V1 硬约束**：一个 Repair Agent；proposal-only（不给 execute 权限）；不上 Multi-Agent；Budget/Stop 复用现有 `max_repairs` / fingerprint stall / `repair_count`，不新造图内熔断。

**Scope**：本 RFC 只产出四件交付物（① 架构决定 ② Tool/ACI Contract ③ Repair Context Schema ④ Benchmark Protocol）＋分歧裁决＋开放问题。不修改 `protocol.py` / `state.py` 任何字段；不实现代码。

---

## 1. 交付物① — Architecture Decision

### 1.1 KEEP / REFERENCE / REJECT 决定表

| # | 对象 | 判定 | 证据 | 决定内容 |
|---|---|---|---|---|
| 1 | LangGraph（外层 routing/checkpoint） | **KEEP** | [01 §0]、[02 §0]、ADR-008 | 只做节点路由与 checkpoint；verifier 判决、`terminal_reason`、fingerprint 一律来自确定性模块，**不得**进 LangGraph 节点或 LLM [01 §0]。checkpoint 目录进 never-grant（T-16），interrupt payload 结构冻结（T-16 V1 缓解） |
| 2 | `RepairPort.propose(run_id, candidate_id, findings) -> PolicyRequest` | **KEEP（frozen）** | [02 §0]、[06 §0]、`protocol.py` L251-252 | LLM 的**唯一**出口。`_repair()` 只消费返回值的 `action / action_id / subject` 三字段（`orchestrator.py` L528-536），且 `_preflight`/`_execute` 只读 `subject`（`_current_subject` L310-314）——Agent 的 `action/action_id` 不构成授权，权威 action 由 orchestrator 固定为 `preflight` / `execute_candidate`（`orchestrator.py` L325, L360；`adapters.py` L151-160） |
| 3 | Trust Plane（policy / transaction / fresh read-back / evidence / human approval） | **KEEP** | [01 §0]、[06 §1] | 每轮修复固定走 `preflight → policy → execute → verify → findings` [02 §0]；ARH 只能是 action ledger 的写入者之一，不能自授能力 [01 §0]。G1–G8 缺口按 §2.5 分级处置 |
| 4 | Coding harness（mini-swe-agent / SWE-agent / OpenHands / Agents SDK） | **REFERENCE ONLY** | [01 §5–§7] | 只吸收 Model/Environment/Trajectory/ACI 的**设计经验**（A1–A12），不引入任何运行时、不引第二套状态真源 [01 §7]。R1–R8 明确 REJECT：任意 shell、agent 自跑验证/自提交、并行 guardrail、LLM guardrail 授权、容器当安全边界、trajectory 当身份 [01 §6] |
| 5 | ARH：ModelAdapter / ContextBuilder / RepairAgent / TrajectoryRecorder / Budget&Stop | **THIN AEDL-NATIVE（新增）** | [01 D1][02 D2–D5][04 D4][06 N1–N8] | 五个薄模块，每个只负责"喂什么、记什么、停在哪"，**不新增任何判定权**（判定权仍在 `VerifierPort`/`PolicyPort`/`TrustPort`）[02 D1][06 §1] |

### 1.2 ARH 五模块职责边界

| 模块 | 职责（属于它） | 不属于它 | 证据 |
|---|---|---|---|
| **ModelAdapter** | provider 调用、prompt/消息格式化、重试与 `FormatError` 类熔断、token/cost 记账（四类 token 分列） | 状态机、判决、写 candidate、构造 `PolicyRequest` 权威字段 | [01 A1][01 §1][05 D4.1] |
| **ContextBuilder** | 组装 `RepairContext`（L0/L1/L2 分层）、findings **逐字**透传、allowlist **投影**（非 dump）、输出侧静态校验（词表/集合/路径前缀） | 改写 `code/message`；dump `engine.document` / `current_state()` / `receipt_root`；产生授权 | [04 D1–D7][06 T-14] |
| **RepairAgent** | 单 agent 的 diagnosis → proposal 循环；结构化 taxonomy prompt；强制"每轮产出 proposal 或显式放弃" | 执行、自评停止权、选择/参数化 verifier、test generation | [02 D1/D5/D8][06 T-11][03 §7.3] |
| **TrajectoryRecorder** | append-only JSONL；每步 `finally` 落盘；schema 版本 + 模型/配置摘要 + `repair_count` + `candidate_id` + receipt 哈希引用；"LLM 可见"与"审计全量"两视图；写入侧脱敏 | 写 `receipt_root`；复用 `FileTrustStore`；进入 candidate hash 或晋升谓词；提供任何判决字段 | [01 D8/A3/A9/A11][02 D2][06 T-06] |
| **Budget&Stop** | 图内：**复用** `max_repairs=3` + fingerprint 早熔断 + `repair_count`（`orchestrator.py` L503-523，不新造、不放宽）；图外（Harness 侧）：每 run 的 LLM 调用数 / token / wall-clock 上限、连续无效 proposal 计数、格式错误连续计数 | 替代 `_detect_stall`；放宽任何既有熔断；把停止权交给模型 | [01 A2/D7][02 D9][06 T-15/N6] |

**V1 结论（按 [02]）**：单 RepairAgent + 结构化 taxonomy prompt + 确定性 `VerifierPort`，不新增第二个 LLM agent、不新增 CriticPort（[02 D5]：开源 PRM 把 40.0% 拉到 19.6–38.8% 的反证；taxonomy 写进单 agent prompt 即可拿到大部分收益）；proposal-only，执行留给既有 port（[02 D4]：Agentless 窄动作空间不劣于自由 agent）。**后续版本一行**：Critic/escalation（`REPAIR_STALLED` 后 second-opinion）、多候选采样、Multi-Agent 均属 V2/TO_VERIFY（[02 D5][02 D10][01 §7]），且出口仍必须是 `PolicyRequest`。

### 1.3 ARH 数据流与不变式

```
Findings(_verify) → ContextBuilder → RepairAgent
    → RepairProposal(diagnosis + design_action/design_subject + evidence_ids)
    → Harness 静态校验(§2.2) → 落成 PolicyRequest → 既有 RepairPort.propose
    → policy → execute → verify → findings  ← 循环
```

不变式（任一破坏即停止接入）：

1. Agent 产出的任何东西都只是 **RepairProposal**，`PolicyRequest` 由 Harness 构造：`run_id/domain_id/action/candidate_root/action_id/actor/capability_grants/verified_bundle_*` 全部由 Harness 盖章或固定，proposal 中出现即**拒绝** [06 never-grant 5][04 §0]。
2. PASS 只来自 `VerifierPort`，晋升只来自 `HumanApprovalReceipt`；LLM 永不产 `Outcome`/`terminal_reason` [02 D1][03 §7.3]。
3. 写路径只有 `ExecutorPort` 在 policy ALLOW 后一条；Agent 无任何写能力 [03 §6.2][06 T-01]。
4. 轨迹是 `report` 类观测，不是 identity（ADR-014），不污染 candidate hash [01 D8]。

---

## 2. 交付物② — Tool / ACI Contract（V1）

### 2.1 Deny-by-default 原则

- 工具集是**闭合白名单**：未列入 §2.2 的工具名一律不可见、不可调用；调用尝试记 `invalid_proposals` 同源计数。
- 读取面**不走 policy**：`SUBJECT_SPECS` 词表中根本没有 READ 动作（`policy/engine.py` L72-117），故读能力由 Harness 白名单 + 作用域限定治理，这是已知的接入后新增风险 **N5** [06 T-14]；V2 是否引入 `READ` 动作词表 + grant → 开放问题 O-08。
- 与 mini/SWE-agent 的差异：不提供任何 bash/shell 工具（[01 R1]；Agents SDK 文档明确内建 `ShellTool/LocalShellTool/ApplyPatchTool` 不走 tool-guardrail pipeline，给 shell 等于关掉 guardrail [01 D11]）。
- 工具返回**只有两种形态**：结构化数据，或结构化错误码；不存在"静默替换输出"——任何拦截必须落成显式 `Finding` [01 D10]。

### 2.2 工具白名单（5 个）

| 工具 | 输入 schema（JSON 形状） | 读/写 | 走 policy？ | 失败时 fail-closed 行为 | 证据 |
|---|---|---|---|---|---|
| `inspect_finding` | `{"finding_code": str?, "include_details": bool=true}` | **只读** | 否（读面无 READ 词表，N5） | 未知 `finding_code` → 返回 `{error:"FINDING_NOT_FOUND"}`，**不猜**、不重试；输出为 `Finding` 四字段（`code/message/source/details`）逐字，禁改写 | [04 D2][06 T-10] |
| `inspect_artifact` | `{"path": str, "start": int?, "lines": int≤40}` | **只读** | 否 | 作用域 = 当前 candidate 子树 + 已授权 baseline；越界/缺失 → `{error:"ARTIFACT_NOT_FOUND"}` + 计数；**禁止整文件 dump**（整文件 viewer 实测比 100 行更差：12.7 vs 18.0 [01 §2]）；窗口 40 行为估算值 → O-09 | [04 D1/§4-5][01 §2] |
| `inspect_evidence` | `{"evidence_id": str}` | **只读** | 否，但复核 policy 集合语义 | `evidence_id ∉ available.evidence_ids` → 拒绝返回内容并标 `UNKNOWN`（不返回"相似"证据）；`cited ⊆ available` 与 `required_evidence_ids ⊆ cited` 在提交前由 Harness 校验，复核 `engine.py` L363-374 / L516-524 | [04 D5][04 §0] |
| `inspect_datasheet_context` | `{"source_id": str \| "mpn": str, "page": int?}` | **只读** | 否 | 只认 sha256 钉死副本；哈希不符 → 丢弃 + `UNKNOWN`；单次 ≤1.5k token（估算，O-09）；禁止输出 URL、禁止凭记忆复述参数值 | [04 D5][04 §7] |
| `propose_repair` | `{"diagnosis": str(≤1句, 指向 finding code), "design_action": enum, "design_subject": object, "evidence_ids": str[]}` | **不产生副作用的写出口**（落成 PolicyRequest 后由既有链执行） | **是**（提交后走既有 `preflight → policy → execute → verify`） | Harness 三重静态校验（词表 / `SUBJECT_SPECS` 精确字段集 / evidence 集合），**不通过不调用 `propose`**；失败 → 丢弃重试 + `invalid_proposals++`；连续超限 → Budget 停（阈值 O-09） | [04 D4][05 D1.4][06 T-07/T-08] |

**`design_action` V1 白名单**（从 `SUBJECT_SPECS` 封闭词表 `engine.py` L72-117 读出后裁剪）：
允许 `DESIGN_SELECT_COMPONENT` / `DESIGN_ASSIGN_PIN` / `DESIGN_SET_PARAMETER`；
**拒绝** `FILE_WRITE` / `NETWORK_ACCESS` / `SHELL_EXECUTE` / `TOOL_EXECUTE` / `COMPILE_HIR` / `VERIFY_ARTIFACT` / `PREFLIGHT`（后三者属执行与判定层，非 proposal 面）。未知 action → `POLICY_ACTION_NOT_ALLOWED`，**没有默认 ALLOW**（`engine.py` L303-315）。

### 2.3 永不授予清单（never-grant，综合 [06 §2] 十二条 + [01 §6]）

1. 任何候选/工作区写能力：`write_candidate_bytes`、裸文件写、shell/`SHELL_EXECUTE`、任意路径读写工具（T-01/T-02）。
2. `.actions.jsonl`（ledger）、`receipt_root`、`checkpoint.sqlite`、run 根的读写（T-03/T-04/T-05）。
3. `TrustPort.record` / `assess_promotion` 句柄，及任何向 receipt 目录写字的 API（T-04）。
4. `orchestrator.resume()` / CLI `resume` / `Command(resume=...)`，以及 `approved_by`/`approver_role`/`human_decision`/`pending_human_action` 写权（T-13/T-16）。
5. `PolicyRequest` 权威字段：`actor`、`capability_grants`、`run_id`、`domain_id`、`candidate_root`、`action_id`、`action`、`verified_bundle_sha256`、`verified_manifest_path` —— proposal schema 遇到即拒绝（T-07）。
6. envelope 额外键：`design_action` + `design_subject` 之外的 subject 键一律拒绝（T-08）。
7. port 装配权：`PolicyPort/ExecutorPort/VerifierPort/RepairPort/TrustPort/checkpointer` 的选择与实例注入（T-11）。
8. 结果对象构造权：`VerificationResult`、`ExecutionResult`、`EvidenceEvent`、`EvidenceReceipt`、`Finding`（Agent 只能读 findings）（T-04/T-11）。
9. `TrajectoryRecorder` 写入 receipt 目录或复用 `FileTrustStore`（T-06）。
10. 网络出口（policy 侧恒 DENY：`engine.py` L814-823；工具层同样不给）（T-01 类）。
11. 跨 run / 他人 receipt / 未授权 baseline 的读权限，以及 `engine.document`、`current_state()` 的全量 dump（T-14）。
12. verifier 输入的参数化权：Agent 不能选择 verifier 判据/版本，只能提供候选内容（T-11）。
13. verifier / 测试 / 合同 / 指纹常量的修改权（oracle 不可自评）（[02 D8]）。
14. 多 agent handoff / 子 agent 编排（[01 §7] REFERENCE ONLY，与 ADR-015 单候选单写者锁冲突面未评估）。

### 2.4 T-01..T-16 → V1 控制映射

| 威胁 | 类别 | V1 控制（落在哪个工具/模块） | 阻塞性 |
|---|---|---|---|
| T-01 候选直写自我认证 | 新增（依赖 G5） | 无任何写工具；写只由 `ExecutorPort` 在 ALLOW 后发生 | **BLOCKING**（白名单必须落地） |
| T-02 workspace 路径残留 | 现有（G8） | 同上，V1 整体豁免 | 非阻塞（开写前 BLOCKING） |
| T-03 ledger 伪造重放 | 现有（G4） | Agent 永不见 `.actions.jsonl` | 可先接入，fail-closed |
| T-04 伪造 PASS receipt | 现有（G2） | `TrustPort.record` + `receipt_root` never-grant | 可先接入，fail-closed |
| T-05 checkpoint/receipt 双篡改 | 现有（G2） | checkpoint 与 receipt 目录 never-grant；只暴露 candidate 子树且只读 | 可先接入，fail-closed |
| T-06 trajectory 混淆 Evidence | 新增（N4） | TrajectoryRecorder 独立目录/扩展名，禁用 `TrustPort` 记 LLM 事件 | **BLOCKING** |
| T-07 权威字段透传 | 现有（G1）+ 新增（N2） | Harness 构造 PolicyRequest；proposal schema **拒绝**权威字段；actor 固定 | **BLOCKING** |
| T-08 envelope extras 旁路 | 现有（G7） | 固定白名单 envelope schema；额外键拒绝并记 Finding | 可先接入，fail-closed |
| T-09 subject 派生身份迁移预算 | 新增（放大 G 系） | 冻结 subject 非设计字段白名单；run 级新建 candidate 计数（Harness 预算） | 可先接入，fail-closed |
| T-10 findings/datasheet 注入 | 新增（N1） | findings 字段当不可信数据：不进 system prompt、不拼成指令；注入只能影响下一条 proposal 内容，不能路由能力 | 可先接入，fail-closed |
| T-11 自我验证/替换 verifier | 现有 + 新增 | verifier/executor 硬编码装配；`VerificationResult` 构造权 never-grant；verifier 只读 | **BLOCKING** |
| T-12 ActorIdentity 冒用 | 现有（G6） | actor 三字段由 Harness 打戳 `actor_kind="agent"`；proposal 拒绝 actor 字段 | 非阻塞（留痕质量问题） |
| T-13 人工审批无认证 | 现有（G3） | `resume`/CLI never-grant；审批走独立人工通道 | 非阻塞（生产化前 BLOCKING，见 O-26 与 §7） |
| T-14 ContextBuilder 侧信道 | 新增（N5） | 字段白名单 + 作用域限定（current run + 授权合同），禁 dump state/engine/receipt | 可先接入，fail-closed |
| T-15 预算/熔断绕过 | 现有（轻）+ 新增（N6） | 图内复用现有熔断；Harness 侧独立 LLM 预算与 proposal 去重 | **BLOCKING**（Budget&Stop 随接入同批交付） |
| T-16 interrupt/checkpoint 状态面 | 现有 | interrupt payload 结构冻结（禁塞 findings/trajectory）；checkpoint never-grant | payload 扩展前 BLOCKING |

### 2.5 缺口分账：现有代码缺口 vs 接入后新增风险

**（a）现有缺口（与 Agent 无关，今天即存在）[06 §3.1]**

| ID | 缺口 | V1 结论 |
|---|---|---|
| G1 | `CapabilityGrant.receipt_sha256` 只查非空、不与真实 receipt 对账；"从 action ledger 读 grant"生产代码无实现（`engine.py` L378-398） | **可先接入但 fail-closed**：V1 不启用任何 capability（`capability_grants` 恒空、actor 由 Harness 固定）。**启用任何 capability 前 = BLOCKING** |
| G2 | receipt 无签发者认证，`receipt_root` 文件系统隔离是唯一控制（`store.py` L312-357, L359-409） | **可先接入但 fail-closed**（never-grant + 独立 trajectory）；任何"便利性写 receipt"功能出现即 BLOCKING |
| G3 | 人工审批无认证：`approved_by` 任意非空、`approver_role` 任意字符串（`store.py` L442-443） | **非阻塞**（V1 不给 resume 句柄）；生产化/对外主张"人工边界"前 = BLOCKING（O-26） |
| G4 | action ledger 无签名且被排除出 candidate 哈希、first-match 读取（`workspace.py` L23, L125-156） | **可先接入但 fail-closed**（ledger never-grant）；启用 ledger 读取功能前 BLOCKING |
| G5 | 无"文件来源"证据：`_verify` 不比对 execution receipt artifacts 与候选实际内容 | **非阻塞**（V1 无写入口，自证闭环不成立）；一旦 V2 给写能力即 **BLOCKING** |
| G6 | `actor_id` 未与 `document.compilers/verifiers` 注册表核对即入 receipt payload | **非阻塞**（不影响 promotion 判定，影响可信留痕） |
| G7 | envelope extras 零校验且直达 executor（`adapters.py` L162-196, L310-320） | **可先接入但 fail-closed**（Harness 白名单 envelope）；出现第二写者前 BLOCKING |
| G8 | workspace 边界是 workspace root 而非 candidate root；Windows 归一化/保留名残留 `TO_VERIFY` | **非阻塞**（V1 无写入口）；开任何写入口前 = **BLOCKING**（[06] 原文"补测试前不得开任何写入口"） |

**（b）接入 Agent 后新增风险 [06 §3.2]**

| ID | 新增风险 | 依赖的既有薄弱点 | V1 结论 |
|---|---|---|---|
| N1 | findings/datasheet/artifact 文本进 LLM → prompt injection | G7、G6 | 可先接入但 fail-closed（结构化 schema + 字段当数据） |
| N2 | Harness 落 PolicyRequest 时字段透传 | G1 | **BLOCKING**（接入前必须实现"Harness 构造 + 拒绝权威字段"） |
| N3 | Agent 获得任何写/网络/shell 工具 | G2/G4/G5/G8 | **BLOCKING**（never-grant 第 1/2/10 条必须随白名单落地） |
| N4 | trajectory 混入 receipt/evidence | G2 | **BLOCKING**（独立 recorder 设计先落） |
| N5 | ContextBuilder 侧信道（他人 run、approver、baseline） | 读取面无 policy 治理（NONE） | 可先接入但 fail-closed（字段白名单 + 作用域） |
| N6 | `propose` 之外的 LLM 自循环无预算约束 | `max_repairs` 只管图内 | **BLOCKING**（Budget&Stop 与接入同批交付） |
| N7 | 审批文案 / interrupt payload 被 Agent 文本污染 | payload 未被 schema 固定 | 非阻塞（当前 payload 硬编码）；扩展 payload 前 BLOCKING |
| N8 | 装配期注入 Agent 可影响的 port 实例 | `isinstance` 仅结构检查 | **BLOCKING**（port 硬编码装配是接入前提） |

**接入放行条件**：N2 / N3 / N4 / N6 / N8 五项 BLOCKING 全部落地 + G1/G8 保持"不启用"，V1 才允许接入真实 LLM。

---

## 3. 交付物③ — Repair Context Schema（v1）

### 3.1 与真实字段对齐（不发明 AEDL 中不存在的数据）

| AEDL 真实类型 | 字段（冻结，`protocol.py`） | Schema 中的用法 |
|---|---|---|
| `Finding` | `code: str`、`message: str`、`source: str`、`details: Mapping[str, JsonValue]`（L86-91） | `findings_current` 逐字透传；`fingerprint` 只吃 `(code, message)`（`state.py` L127-134）→ `code/message` 一个字节都不能改 |
| `VerificationResult` | `status: VerificationStatus(NOT_RUN/PASS/FAIL/BLOCKED)`、`candidate_id`、`findings`、`actor_id`（L133-139） | `verification_ref`（只读引用，Agent 无权构造，never-grant 8） |
| `EvidenceReceipt` | `event_hash`、`run_id`、`candidate_id`、`valid: bool`（L151-156）；`event_type` 由 `state.encode_receipt` 附加（`state.py` L117-124） | `receipts_digest` 只给 `hash12` + `event_type`（**不含 `sequence`**，见分歧 D5） |
| `PolicyRequest` | `run_id/domain_id/action_id/action/candidate_root/subject/verified_bundle_sha256/verified_manifest_path/actor/capability_grants`（L94-112） | 全部权威字段由 Harness 盖章，proposal 拒绝（never-grant 5） |
| `SandboxState` | `run_id/domain_id/bundle_hash/subject/repair_plan/candidate_*/phase/repair_count/max_repairs/findings/previous_finding_fingerprint/stall_count/policy_result/execution_result/verification_result/evidence_receipts/pending_human_action/human_decision/approved_by/approver_role/approved_at/terminal_reason`（`state.py` L33-60） | 只读投影进 L0；**不改任何字段** |
| `SUBJECT_SPECS` | 封闭动作词表（`engine.py` L72-117） | `action_schema` 由 ContextBuilder 从内核**读出**而非手写 |

**注意两处真实语义**：① `state.findings` 每轮被 `_verify` 覆盖只留最新一轮，`previous_finding_fingerprint` 只存上一轮（`state.py` L47-54、`orchestrator.py` L479-501）→ 多轮轨迹必须来自 `TrajectoryRecorder`，不能来自 state；② receipt 的逐轮 `payload.sequence = repair_count+1` 在 **receipt 文件**里（[05 §0]），`state.evidence_receipts` 中没有（分歧 D5）。

### 3.2 RepairContext 字段表

`ContextBuilder` 每轮产出、`RepairAgent` 消费的**单一逻辑结构**（不改冻结签名 `propose(run_id, candidate_id, findings)`，由 Harness 在调用前组装）。

| # | 字段 | 类型 | 来源组件 | 层 | token 预算 | 失败关闭语义 |
|---|---|---|---|---|---|---|
| 1 | `contract_ref` | `{domain_id, bundle_hash}` | orchestrator init（`state.bundle_hash`） | **L0 每轮** | ~60 | 哈希缺失 → 不构造上下文 |
| 2 | `subject_frozen` | `dict` | `state.subject`（只读） | L0 | 视域 | 只读，不可由 LLM 生成 |
| 3 | `findings_current` | `Finding[]` **逐字** | `_verify` → `state.findings` | L0 | ~150-800 | `code/message` 禁改写，否则 stall 判重失效 [04 §2] |
| 4 | `locator_block` | `dict[]` 确定性派生 | ContextBuilder ← `Finding.details`（`contract_id`/rule fingerprint/`evidence_id`/`pin`/`mpn`/行号） | L0 | ~120 | 缺键 → `UNKNOWN`，不编造 [04 D2] |
| 5 | `fingerprint_state` | `{now, prev, stall_count, repair_count, max_repairs}` | `state` | L0 | ~60 | 齐全才允许提案 |
| 6 | `attempt_history` | `list[{round, fingerprint12, diagnosis, proposal{action, subject_digest}, outcome}]` | **TrajectoryRecorder**（state 里没有） | L0 | ≤600 | 折叠行标注省略量；`fingerprint/code/message` 逐字保留 [04 D3] |
| 7 | `rejected_proposals` | `list[action + subject_digest]` | TrajectoryRecorder | L0 | ≤200 | 常驻去重（防 65% 重复补丁 [02 D7]） |
| 8 | `receipts_digest` | `list[{event_type, hash12}]` | `state.evidence_receipts` | L0 | ≤120 | 不带 payload；不进身份判定 |
| 9 | `allowlist` | `{evidence_ids[], active_rules[{rule_id, fingerprint}], allowed_components[{mpn, role, required_evidence_ids}]}` | 合同 document 的**字段投影**（`domain_policy_schema_v1.json` L247-263） | L0 | ~400-900 | 提案只能从此集合选；投影而非 `engine.document` dump（分歧 D6） |
| 10 | `action_schema` | V1 白名单的 `SUBJECT_SPECS` 字段清单 | `policy/engine.py` L72- | L0 | ~200 | 多/缺字段即 `POLICY_SUBJECT_MALFORMED`（L303-331） |
| 11 | `deny_list` | §2.3 摘要 | prompt 资产 | L0 | ~200 | 置 prompt **首尾**（位置效应 [04 D6]） |
| 12 | `knowledge_ptr` | `list[ID / path]`（**不含正文**） | `docs/ID_MAP.md` 式路由 | L0 | ~80 | 只给指针（回声 `RAG_DECISION.md`：ID 精确检索） |
| 13 | `verification_ref` | `{status, candidate_id, actor_id}` | `state.verification_result`（只读） | L0 | ~40 | Agent 引用状态，不得自述 PASS |
| — | **L0 合计** | | | | **≈2.5-4k（估算，O-09）** | 超预算按 `knowledge_ptr → receipts_digest → attempt_history 折叠加深 → locator_block` 裁剪；**绝不裁** `findings_current / allowlist / action_schema / deny_list` [04 D7] |
| 14 | `code_window` | `{path, start, lines≤40}` | 只读检索（按需） | **L1 按需** | ≤1.2k | 取不到 → 省略并标注 [04 §4-5] |
| 15 | `rule_source` | `{rule_id, source_ids → sha256 副本路径}` | 合同 + provenance | L1 | 按需 | 哈希不符即丢弃 |
| 16 | `datasheet_excerpt` | `{mpn, page, text}` 钉死副本 | 证据库（按需，单 ID、带行号窗口） | L1 | ≤1.5k/次（估算） | 只认 sha256 副本 [04 D5] |
| 17 | 证据 artifact 正文 | 任意 | `inspect_evidence` | L1 | 有界 | 仅 allowlist 内 ID |
| — | **L2 禁止** | 完整数据手册 PDF、完整合同 JSON、全轮 findings 原文、LLM reasoning 全文、其他 run 的轨迹、赛事/合规文档正文 | — | **L2 禁止** | — | 仅人工审计时由人打开，永不自动加载 [04 §7] |

### 3.3 提案输出契约与双重校验

Agent 输出（写进 prompt 的输出段）：

```
RepairProposal {
  diagnosis: "<error-aware 一句话，必须指向具体 finding code，缺失字段写 UNKNOWN>",
  design_action: <§2.2 V1 白名单>,
  design_subject: <严格符合该 action 的 SUBJECT_SPECS 字段集>,
  evidence_ids: [<allowlist 枚举选择，禁止 URL>],
  locator: {contract_id?, rule_fingerprint?, pin?, mpn?, path?, line?}   // 可选，缺则 UNKNOWN
}
```

Harness 校验顺序（**两道都在 `propose` 之前**，因为带病提交必然使 `_preflight` 非 ALLOW → run 终止，`orchestrator.py` L331/L366 [04 D4][A1]）：

1. **调用前**：allowlist 集合校验（`cited ⊆ available`、`required_evidence_ids ⊆ cited`）、动作词表校验、权威字段与 envelope extras 拒绝（T-07/T-08）、路径前缀校验；
2. **LLM 返回后**：按 `SUBJECT_SPECS` 精确字段集自校验；不合规 → 丢弃重试（`invalid_proposals++`），**不调用 `propose`**。

落成 `PolicyRequest` 时：`action="preflight"`/`"execute_candidate"` 由 orchestrator 固定，subject 信封只允许 `{design_action, design_subject}`（`adapters.py` L151-196）；`actor` 由 Harness 打戳 `actor_kind="agent"`，`capability_grants=()`。

### 3.4 引用纪律（证据/数据手册）

- prompt 中**从不出现** `evidence_ids` 自由填写位，只给 allowlist 要求"从中选"（[04 D5]：LLM 引用 recall 51.5% / precision 74.5%，且 precision 与感知有用性负相关）。
- 禁止输出 URL；所有引用落到 `evidence_id + sha256`，与 `available.evidence_ids`（"Source URLs never appear here"）一致。
- 参数主张必须能在钉死 excerpt 中**逐字定位**，否则写 `UNKNOWN`（对冲"仅凭 issue 文本猜中 76% 文件路径"的记忆污染 [04 S22]）。
- 每条 proposal 的 `evidence_ids` 与 receipt 对齐关系保持可与 receipt `hash12` 关联（完整性骨架，不带 payload）。

---

## 4. 交付物④ — Benchmark Protocol

> **全部条款为口径设计，本 RFC 未运行任何 benchmark（NOT_RUN）** [05 全文]。

### 4.0 Verifier Capability Pre-measurement（前置测量，非评分维度）

> 增补依据：Owner 2026-09-28 批准（"增加 verifier effectiveness pre-stage"）。
> **本节不修改 §4.1–§4.5 的任何指标、组合规则或 §4.5 冻结项。**

**动机。** §4.2 注入硬条件①要求 fault"可检出（注入后 `F_0` 含对应 finding），不满足即剔除"。该条件保证了能力测量的有效性，但副作用是：**漏检的 fault 在 benchmark 开跑前已被静默剔除，本协议在结构上永远测不出 verifier 自身的漏检率**，O-12 因此只能引用文献、不能变成测量。而 `converged_strict` 的一切数字都以"verifier 能看见"为前提——不测这个前提，收敛率就是无条件的错误自动化（[05 D1.5] SWE-bench 弱测试虚高 6.4pp 的同型风险；[02 §7] O-12）。

**定位。** Stage 0 前置测量：**不含任何 Agent/LLM**，只跑 fault injection → verifier → 检出判定。Stage 1（§4.1–§4.5 repair benchmark）只用 detected faults——与现有条件①**组合规则完全一致**。唯一改变：条件①从"过滤器"升级为"**过滤器 + 计数器**"，被剔除的 fault 按类留痕，不再消失。

**协议**

1. **时点**：fault set 构建期间（与 §4.5 冻结项 1 同一工序），早于任何 Agent 接入与任何 benchmark run。
2. **谓词**：**复用条件①的谓词，不另立标准**——注入后 `F_0` 是否含该 fault 对应的 finding（fault → expected finding 的映射在冻结项 1 的 killable 校验中本来就需要）。
3. **输入**：候选 fault 全集 + 确定性 verifier（不接模型、不接候选修复）。
4. **产物**：与 `fault_set_v1.json`（只收合格 fault，冻结项 1 不变）**并列**的 screening 留痕——每个候选 fault 的注入结果、条件① 判定、accept/reject 及原因，随 fault set 同批以 sha256 钉死。**不新增、不改写 §4.5 冻结项**：其口径 = 冻结项 1 已有的 killable 校验谓词，只是把被剔除者的判定也记下来。
5. **输出（按 §4.2 的五个 fault class 分列）**：

   | 指标 | 定义 | 口径约束 |
   |---|---|---|
   | `verifier_recall[class]` | `detected / injected` | 分母 = 该类注入总数（含被剔除者），**不是** fault_set_v1 内数量 |
   | `verifier_missed[class]` | `injected - detected` | missed 明细须可回溯到 screening 留痕 |
   | `VERIFIER_BLIND_CLASS` | `detected = 0` 的类 | **不得静默删除该类**；Stage 1 对该类零贡献，报告必须写"本 benchmark 不覆盖该类" |

6. **条件性声明（与 Stage 1 绑定报告）**：§4.1–§4.4 的一切收敛指标都是 **conditional on detectability**（"给定 verifier 能看见"）。recall 表是让这个前提可见的唯一方式，**两者必须一起出现**；只报收敛率不报 recall = 违反本节。
7. **与三个核心指标的对应**：verifier recall（本节）/ repair convergence（§4.1 既有指标）/ trust boundary integrity（§4.1 既有 `invalid_proposals` + `policy_denied_runs` + never-grant 违规尝试，本节不新增第三套计数）。三者并列报告，"可信"不得只用其一支撑。

**范围锁定（本节不做什么）**

- 不改 §4.1 指标定义、不改 §4.2 组合规则、不改 §4.5 冻结项；recall **不进** `converged_strict`、不进能力分母、不作为 scoring 维度。
- 不测 false positive / clean-baseline 侧：基线候选本身可能含真实 findings，"误报"判定口径未定义 → O-28。
- recall 结果本身 **NOT_RUN**：表格框架就位不等于已有数字；O-12 在 Stage 0 实际跑出前保持开放。

### 4.1 指标定义

**数据源规则（D0.1）**：逐轮指标一律从 `receipt_root/<run_id>/<event_hash>.json` 读，**不读** `SandboxState.findings`（只保留最后一轮快照，regression 差集口径会错）[05 §0]。

**收敛三层（禁止混用）**

| 指标 | 定义 | 口径风险 |
|---|---|---|
| `machine_converged` | `verification_result.status == PASS` 且 `pending_human_action` 非空 | PASS 不是 terminal（`orchestrator.py` L485-493），读 `terminal_reason` 会漏 [05 D1.1] |
| `promoted` | `terminal_reason == "STATE_PROMOTED"` | 人工审批**脚本化**为恒 `APPROVED` + 具名 `approved_by`；出现 `APPROVAL_HUMAN_REJECTED` 记 `INVALID_RUN` 而非"未收敛" [05 D1.2]。**该脚本化仅限 benchmark，不得进入生产**（G3 仍未修） |
| `converged_strict`（发表口径） | `machine_converged` **且** `new_regressions == 0` **且** `faults_all_cleared == 1` **且** `invalid_proposals == 0` | 缺 held-out verifier 时标 `TO_VERIFY`，不得写进主张（SWE-bench 弱测试致 7.8% "正确"补丁实错、虚高 6.4pp [05 D1.5]） |

**失败分类必须互斥分报，禁止合并成单一 fail rate**：`REPAIR_STALLED` → stall 型；`REPAIR_LIMIT_REACHED` → budget 型；`POLICY_*` → policy 拒绝型；`EXECUTION_*` / `VERIFY_IDENTITY_MISMATCH` / `EVIDENCE_RECEIPT_INVALID` → fail-closed 异常，**剔出模型能力分母**（评分器故障不算被试失败）[05 §1.1]。

**指标总表**

| 指标 | 定义/公式 | 数据来源 | 备注 |
|---|---|---|---|
| `converge_rate` | `#{converged_strict}/#{valid_runs}`，**Wilson 95% CI** | 派生 | 禁 CLT 正态区间（小样本覆盖率 92.5% vs 名义 95%）[05 D3.3] |
| `pass@k` / `pass^k` | Chen 无偏估计 / 全 k 次都收敛 | run 级布尔 | **主报告口径 = `pass^k`**（可靠性优先于乐观上界）[05 §1.2] |
| `new_regressions` | `F_T \ F_0`，比率 `= |F_T\F_0|/max(1,|F_T|)` | receipt 逐轮 findings | findings 变少 ≠ 修对 |
| `fixed_findings` | `|F_0 \ F_T| / max(1,|F_0|)` | 同上 | 须 held-out 交叉 |
| `invalid_proposals` | **Harness 侧**预校验失败的提案数（schema / allowed-ops / 集合校验） | **NEW_FIELD**（state 无） | 与 `policy_denied_runs` **必须分列，不得互替**——这是"LLM 不绕过 Trust Plane"的可观测证据 [05 D1.4]（计数位置见分歧 D2） |
| `policy_denied_runs` | `terminal_reason ∈ POLICY_*` | `terminal_reason` + `policy_result` | 单 run 最多 1 次 DENY（fail-closed 即停）；preflight/execute 是否可分 → O-20 |
| `stall_rate` / `budget_rate` | `#{REPAIR_STALLED}` / `#{REPAIR_LIMIT_REACHED}` ÷ valid | `terminal_reason` | 合并会掩盖"打转 vs 太慢" [05 §7] |
| `rounds` | `repair_count`，报 **median/p95 不报均值** | `repair_count` | 受 `max_repairs=3` 截断 |
| `verifier_calls` | verification receipt 计数 | `evidence_receipts[].event_type` | fail-closed 分支不写回执 → 少计 |
| `tokens` / `cost_usd` / `latency_ms` | 四类 token 分列；价目 × as-of；p50/p95 | **Harness 侧 JSONL（NEW_FIELD）** | `cache_read` 单列，漏算缓存价 ≈ 5× 高估 [05 D4.2] |
| `cost_per_converged` | `total_cost / #{converged_strict}` | 派生 | 失败 run 成本必须进分子；收敛/失败成本分报 [05 D4.3] |

**fingerprint 陷阱（D1.6）**：stall 判定忽略 `details`（`state.py` L127-134）。benchmark 要求注入 fault 对应 finding 的 `message` 必须随修复状态变化，否则该 fault 标 `INVALID_FAULT` 剔除 → **此条需在冻结 fault set 前跑通（NOT_RUN）**。

### 4.2 故障集设计

- **双层 60 个**：A 层真实缺陷 20（现有 verifier/preflight 已能报出；部分会被 policy 在 preflight 直接 BLOCKED → 只测"是否老实失败关闭"，**不进收敛率分母**）；B 层人为注入 40（mutation-testing 思路，参照 MuBench 1,700 变异 / 7 类 mutator）[05 D2.1]。
- **有偏性必须写进报告**：357 真实缺陷 vs 230,000 变异 → 73% 耦合、**17% 真实缺陷不与任何变异耦合**，禁止声称"覆盖真实硬件缺陷分布" [05 D2.1]。
- **注入四条硬条件**（逐条校验，不满足即剔除）：① 可检出（注入后 `F_0` 含对应 finding）；② 可修（确定性 RepairPort 在同样 `max_repairs` 下能收敛 → 同时充当 automatic oracle solver）；③ 注入在数据/subject 层，**不改 verifier、不改 policy**；④ 可逆可复现（diff + sha256 冻结成 `fault_set_v1.json`，run 前校验 hash，`run_id` 派生同一初始 candidate 快照）[05 D2.2]。

### 4.3 对照设计

四臂，全部同 fault、同 candidate 字节、同 `F_0` 快照、同 allowed ops、同 `max_repairs=3`：

| 臂 | 内容 | 用途 |
|---|---|---|
| B0 | V1 确定性 RepairPort fixture（已存在：`_TestOnlyRepair`/`_TestOnlyVerifier`，attempt≥2 才 PASS，policy/trust 用真实实现） | 评分器自检：预期 100% 收敛、`rounds=2`、0 token；**不是能力基线** [05 D3.1][05 §0] |
| B1 | `max_repairs=0`（不修复） | 得 `F_0` 与不可修下界 |
| M | LLM-A / B / C，同一 RepairPort 接口 | 唯一自变量 = 模型 |

变量控制（D3.2）：`allowed_ops` 冻结；上下文 schema 冻结（模型只看到 `findings{code,message,source,details}` + candidate + allowed ops，**不给 gold fix**）；temperature/seed 显式记录；价目与模型版本冻结；每臂独立 workspace、无跨 run 状态。
统计（D3.3/D3.4）：同 `fault_id` **配对**比较（配对 bootstrap 或 exact McNemar）；**默认 k=10 runs/(fault, model)**——单 run `pass@1` 极差 2.2–6.0pp、SD>1.5pp 即使 temp=0（60,000 条轨迹研究）；k<5 判 `INSUFFICIENT_RUNS` 不许出结论（Epoch AI "≥5 runs 才有 error bars"）。
污染（D3.5）：SWE-bench Verified 抽样 138 题 59.4% 测试设计有缺陷且模型均"见过"→ 停用；AEDL fault set 自造且不公开 oracle 修复可规避，但 fault 描述模板与训练语料同构风险 → `TO_VERIFY`。

### 4.4 最小可行规模

| 档位 | 组成 | run 数 | 能支撑什么 |
|---|---|---|---|
| Pilot（流程自检） | 20 faults × 2 models × 5 runs | 200 | 只验证 harness 跑通、指标算得出；**不得出能力结论** |
| 主实验（可发表下限） | 60 faults × 3 models × 10 runs + B0/B1 各 60 | 1,860 | 配对比较 + Wilson 区间 + run 方差控制 |
| 削减方案 | 60 × 3 × 5 | 900 | 仅能分辨较大差异，须写明检出下限，小差异标 `TO_VERIFY` |

依据：run 次数受 2.2–6.0pp 单 run 方差与"≥5 runs"门槛约束；fault 数受 Wilson 约束（60 个 fault 下半宽约 ±12pp，**区间公式推导非实测**，pilot 后重算）；不足 30 fault 标 `INSUFFICIENT_SCALE` [05 §2.3/§3.4/§5]。
**UNKNOWN**：域内 LLM 实际收敛率分布未知 → 正式 power 计算必须先跑 pilot 拿 `p̂`；总成本同样 UNKNOWN [05 §5]。

### 4.5 冻结清单（production Agent 开发**前**必须先冻结）

改任一项 = 结果不可比，须重跑全量 [05 §6]：

1. `fault_set_v1.json`：fault_id、注入 diff、oracle 修复、killable 校验、sha256；
2. 指标口径：`converged_strict` 定义、`F_0/F_T` 差集口径、`terminal_reason` 分类映射；
3. **上下文 schema**：模型每轮看到什么、不看到什么（含"不给 gold fix"）——即本 RFC §3 全表；
4. `allowed_ops` 动作空间 + `max_repairs=3` + 人工审批脚本化为恒 `APPROVED`；
5. 随机性控制：temperature、seed 策略、k runs、独立 workspace、无跨 run 状态；
6. 模型标识规范（provider / model id / 版本快照日期）与价目表 as-of；
7. verifier / policy / trust 版本绑定（`actor_id` + 代码 hash）、`finding_fingerprint` 算法、receipt 读取路径。

**冻结之后仍可改**：prompt 措辞/系统提示/上下文压缩（但每改一次 = 新 `scaffold_hash`，须重计为新臂并重跑）；harness 内部实现（LangGraph 节点结构，前提是不改 `protocol.py`/`state.py` 语义与 reason-code 命名）；价目表数值（可按新价目复算 `cost_usd`，`tokens` 不变）；新增 `fault_set_v2`（**追加**，v1 不删不改）；报告形式。

---

## 5. 分歧与裁决建议（报告间不一致，共 7 条）

> 下表不抹平分歧；每条给出各报告立场 + 裁决建议 + 是否需要人类拍板。

| # | 分歧点 | 各报告立场 | 裁决建议 | 需人类拍板？ |
|---|---|---|---|---|
| **D1** | **fingerprint 输入范围** | [02 D9] 保持 `(code, message)`，`details` 入指纹留 V2，V1 靠喂全量 details 让模型制造可观测差异；[03 §6.3] 以 boardsmith 只 hash `severity=error`（排除 warning）为样板，**要求 RFC 显式决定输入范围**，否则"非致命项抖动假 stall"或"改 message 绕过熔断"；[05 D1.6] 只要求 fault 的 `message` 必须随修复状态变化，否则 `INVALID_FAULT`；[06 T-15] 指出 message 内嵌 subject 可控值 → 换措辞即可吃满 `max_repairs` 而不触发 `REPAIR_STALLED` | **V1 不改 `state.py` 指纹算法**（冻结契约、避免一次改两头）：采用 [05 D1.6] 的 fault-set 约束 + [06] 的 Harness 侧 Budget/去重缓解；severity 过滤与 `details` 纳入指纹 → **V2 / ADR 级契约变更** | **是**：是否给指纹加 severity 过滤（会改契约）；是否接受"换措辞绕过 stall、由 Harness 预算兜底"作为 V1 已知限制 |
| **D2** | **`invalid_proposals` 计数位置** | [05 D1.4] Harness 侧在交 policy **前**做 schema/allowed-ops 预校验并计数，与 `policy_denied_run` 分列；[04 D4] 更进一步——不合规就**不调用 `propose`**（输出侧静态检查、丢弃重试）；[06 T-15] 认为 policy DENY 即终其实是"便宜止损" | **两处统一为"Harness 预校验层"**：`invalid_proposals` = 已产出但被静态校验拦下的 proposal（含被 [04] 丢弃的重试）；通过校验但被 policy 拒 → `policy_denied_runs`。**口径必须写进 [05 §6] 冻结项 2**，否则 benchmark 会漏计 | **是**：`invalid_proposals == 0` 是否继续作为 `converged_strict` 的必要条件（[05 D1.3]），以及被丢弃重试是否计入 |
| **D3** | **上下文窗口阈值** | [04 §7] 取 `code_window ≤40 行`、L0 ≈2.5-4k、L1 ≤1.5k/次，自标**估算值**；[01 §2] 实测 30/100/整文件 = 14.3/18.0/12.7，**100 行最优**、整文件更差；[04 §3] 取"当前 + 最近 1 轮原文"，[01 §2] 取"最近 5 条 observation" | **V1 取 [04] 的保守值（40 行 / 1 行折叠），全部标 TO_VERIFY**，并在 pilot 中对 40 vs 100 行做 A/B；因 `max_repairs=3`、轮次天然有界，"最近 1 轮 vs 最近 5 条"在 V1 不敏感 [04 §9 UNKNOWN] | **是（低优先级）**：pilot 是否包含窗口 A/B；初始值取 40 还是 100 行 |
| **D4** | **Budget&Stop 的强制位置** | [01 A2] 在 `_detect_stall` 之外叠加 step/cost/wall-time/format-error 四阈值且"**由 orchestrator 强制**"；[06 N6/T-15] `propose` 之外的 LLM 自循环无任何约束，Budget&Stop **必须放 Harness**；任务前提"Budget/Stop 复用现有 `max_repairs`/fingerprint/`repair_count`，**不新造**" | **双层且不动 orchestrator**：图内熔断 = 完全复用现有三项（不新造）；图外 LLM 预算（调用数/token/wall-clock/连续无效提案/格式错误）= Harness 进程内强制并计入 `INVALID_RUN`。[01 A2] 的"orchestrator 强制四阈值"属代码变更，**本 RFC 不纳入** | **是**：是否接受"LLM 层预算由 Harness 强制而非 orchestrator 强制"；若要 orchestrator 硬阈值，需另开任务/ADR |
| **D5** | **receipt `sequence` 字段位置** | [04 §4 行 9] 假设 `receipts_digest = list[{sequence, hash12}]` 来自 `state.evidence_receipts`；[05 §0]/[04 §0] 自己也指出 `payload.sequence = repair_count+1` 在 **receipt 文件**里，`state.encode_receipt`（`state.py` L117-124）只有 `event_hash/run_id/candidate_id/valid/event_type` | **以代码为准**：L0 的 `receipts_digest` 用 `{event_type, hash12}`（state 现有字段）；需要轮次序号时由 `TrajectoryRecorder` 的 `round`（可由 `repair_count` 派生）或按 [05 D0.1] 从 receipt 文件读取 | 否（可由 RFC 直接裁决），但需人类确认 [04] 表格按此修订 |
| **D6** | **allowlist 是投影还是 dump** | [04 §4 行 10] 给 `allowlist` 含 `active_rules`/`allowed_components` 等合同字段；[06 T-14] 把 `engine.document` **全量 dump**（全量 pin/参数/规则指纹与 supersession）列为侧信道风险 | **取投影**：`allowlist` = ContextBuilder 按字段白名单从合同 document 投影出的**枚举所需最小集**，禁止 `engine.document`/`current_state()` 序列化整体进 prompt | 否（裁决明确）；投影字段清单在实现评审时确认 |
| **D7** | **只读检索是否需要 CapabilityGrant** | [02 D4] 与 [04 §9] 都把 diagnosis 阶段只读检索的 grant 语义标 **TO_VERIFY**（未读 policy 授权路径）；[06 T-14] 指出读取面**根本不受 policy 治理**（词表无 READ 动作），属 N5 新增风险；[06 G1] 又说明 grant 机制当前恒 fail-closed 且未实现对账 | **V1 不引入 grant**：读能力由 Harness 白名单 + 作用域（current run findings/receipts 只读、candidate 子树、授权合同/证据 allowlist）治理，显式记录为"边界纪律而非机制保证" [06 §4] | **是**：V2 是否引入 `READ` 动作词表 + grant（依赖 G1 对账先补） |

---

## 6. 开放问题（`UNKNOWN` / `TO_VERIFY` / `NOT_RUN` 原样保留，共 28 条）

> 综合过程不改写这些状态；实现与对外主张时必须原样引用。

| # | 类型 | 内容 | 来源 |
|---|---|---|---|
| O-01 | NOT_RUN | 四个被调研框架（mini/SWE-agent/OpenHands/SDK）均未实际运行，所有分数为论文/文档自述 | [01 §8] |
| O-02 | TO_VERIFY | SWE-agent 1.x 的 action/config 源码路径未逐一定位（ACI 细节来自论文与文档） | [01 §8] |
| O-03 | TO_VERIFY | mini-swe-agent v2 是否内置 observation 折叠 | [01 §8] |
| O-04 | UNKNOWN | OpenHands Stuck Detection 窗口参数与 `_detect_stall` fingerprint 的等价性 | [01 §8] |
| O-05 | UNKNOWN | LangGraph checkpoint 与 ARH trajectory 的重复存储成本 | [01 §8] |
| O-06 | 未评估 | 多模态/浏览器工具、跨任务 memory/skill 类 capability | [01 §8] |
| O-07 | NOT_RUN | 现有 repair loop 的轮次分布、fingerprint 命中率、`max_repairs=3` 是否合适，均未观测 | [02 §7] |
| O-08 | TO_VERIFY | 只读检索所需的 `CapabilityGrant` 语义与 policy 判定路径（承 [02 D4]，未读 policy 授权路径实现）；读能力是否需 grant | [02 §7][04 §9] |
| O-09 | TO_VERIFY | 上下文 token 阈值（L0 2.5-4k、40 行窗口、1.5k 单次上限）：外部数字全来自代码修复 benchmark，AEDL findings 体量小得多，外推无依据 | [02 §7][04 §7/§9] |
| O-10 | TO_VERIFY | `REPAIR_STALLED` 后引入 second-opinion（escalation）的成本/收益，无直接证据 | [02 §7] |
| O-11 | UNKNOWN | `Finding.details` 实际填充率（`locator_block`、`D6` 反馈带定位、`D5` 引用纪律都依赖它） | [02 §7][04 §9] |
| O-12 | 最弱一环 | 全部外部证据来自"可执行、有隐藏测试"的代码修复 benchmark；AEDL 是硬件域、verifier 覆盖**部分**——若 verifier 永不给 PASS，"外部反馈有效"会退化为只能靠 `max_repairs` 兜底，此缺口无法用现有文献闭合 | [02 §7][04 §9] |
| O-13 | NOT_RUN | [03] 未执行任何测试/CLI；所有"防线有效/门禁强度"判断为静态阅读 | [03 §0] |
| O-14 | TO_VERIFY | boardsmith "LLM 只在 B1"（作者自述）；Circuitron 实现；电机驱动多智能体"直到零 ERC"未见上限；SchGen/PCBSchemaGen 许可 | [03 §2/§5] |
| O-15 | TO_VERIFY | `RepairContext` schema 是否构成公共契约变更（若是 → 需 ADR） | [04 §9] |
| O-16 | TO_VERIFY | `locator_block` 能否真提升修复率（结构化诊断对照 94.0% vs 95.2%, p=1.000，本地无 A/B） | [04 §9] |
| O-17 | UNKNOWN | `max_repairs=3` 下 `attempt_history` 的真实分布与折叠收益（轮次太少，折叠可能用不上） | [04 §9] |
| O-18 | NOT_RUN | **Benchmark 未运行任何一次**；所有数量结论为口径推导或文献引用 | [05 全文] |
| O-19 | TO_VERIFY | D1.6：注入 fault 的 finding `message` 必须随修复状态变化，需在冻结 fault set 前跑通 | [05 D1.6] |
| O-20 | TO_VERIFY | `encode_policy_decision` 不含 `action_id`、`phase` 被覆盖为 `TERMINAL` → 仅凭 state 无法区分 preflight 拒绝与 execute 拒绝（policy reason_code 是否语义可分） | [05 D1.4] |
| O-21 | TO_VERIFY | 统计口径推导项：60 fault 下 Wilson 半宽约 ±12pp（区间公式推导非实测）；k=5 时可分辨的最小差异 X（pilot 方差定）；fault 描述模板与训练语料同构的污染风险 | [05 §2.3/§3.4/§3.5] |
| O-22 | UNKNOWN | AEDL 域内 LLM 实际收敛率分布未知 → power 计算需先跑 pilot 得 `p̂`；总成本 UNKNOWN | [05 §5] |
| O-23 | TO_VERIFY | Windows 路径归一化（`".. "`、尾随点、`con.txt`/`nul.txt`）能否绕过字面 `..` 检查（G8）；未运行任何测试 | [06 §4] |
| O-24 | TO_VERIFY | `CapabilityGrant` 是否存在仓外/未读到的发放实现（grep 仅见 tests）；若存在，G1 的"对账缺失"需重新评估 | [06 §4] |
| O-25 | UNKNOWN | 真实 `VerifierPort` 的 `Finding.details` 是否回显候选文件内容（决定 T-10 注入带宽）；当前只有 fixture double | [06 §4] |
| O-26 | UNKNOWN | `approver_role` / `actor_id` 是否已有仓外审计校验层（仓内未见） | [06 §4] |
| O-27 | NOT_RUN | [06] 无任何执行验证，所有"防线有效"结论都是静态阅读 | [06 §4] |
| O-28 | TO_VERIFY | verifier 误报侧（false positive / precision）度量口径未定义：基线候选本身可能含真实 findings，"何为误报"未界定 → §4.0 Stage 0 只测 recall，不测 precision | [§4.0 范围锁定] |

---

## 7. 需要人类决定的开放问题（拍板清单）

1. **D1 指纹语义**：是否维持 `(code, message)` 冻结指纹 + 接受"换措辞绕过 stall"为 V1 已知限制（由 Harness 预算兜底），还是把 severity 过滤/`details` 入指纹提前到 V1（= 契约变更 + ADR）。*此项直接决定 benchmark 的 stall 口径。*
2. **D2 指标口径**：`invalid_proposals` 的计数点与"被丢弃的重试是否计入"，以及它是否继续作为 `converged_strict` 的必要条件（`converged_strict` 属 §4.5 冻结项 2，改 = 重跑）。
3. **D4 预算归属**：是否接受 LLM 层预算由 Harness 强制（而非 [01 A2] 的 orchestrator 强制四阈值）；若要 orchestrator 硬阈值，另开任务/ADR。
4. **O-15 schema 冻结级别**：`RepairContext` 是否算公共契约 → 是否需要 ADR 后才能冻结（影响 §4.5 冻结项 3 的时点）。
5. **O-08 / D7 读能力治理**：V1 是否维持"grant 不启用、仅 Harness 白名单"；V2 引入 `READ` 词表 + grant 的前置是 G1 对账实现（[06]：启用任何 capability 前必须补）。
6. **G3 人工审批认证**：是否把 `approved_by` 白名单/角色校验列为**生产接入前置**（当前 V1 靠 never-grant 隔离，属边界纪律而非机制保证 [06 §4]）。注意：benchmark 的"审批脚本化恒 APPROVED"是评测环境决定，**不得**被理解为生产特性。
7. **Benchmark 档位与预算**：Pilot 200 / 主实验 1,860 / 削减 900 三档选哪档；依赖 O-22 的 pilot `p̂`。建议顺序：先 pilot（只验流程，不出能力结论）→ 拿到方差与 `p̂` → 再定主实验规模。
8. **A 层真实缺陷的分母地位**：被 policy 在 preflight 直接 BLOCKED 的真实缺陷"只测老实失败关闭、不进收敛率分母"这一口径是否认可（[05 D2.1]）。
9. **接入放行**：确认 §2.5 的五项 BLOCKING（N2/N3/N4/N6/N8）作为真实 LLM 接入的前置条件清单。

---

## 来源

**输入报告（唯一外部论据）**：`docs/research/agent-runtime/01-harness-landscape.md`、`02-repair-loop.md`、`03-eda-agents.md`、`04-context-engineering.md`、`05-eval-protocol.md`、`06-red-team-trust-bypass.md`（各报告自带来源列表，本 RFC 不重复、不外推）。

**仓库事实（静态阅读，NOT_RUN）**：`sandbox_runtime/src/aedl_sandbox/protocol.py`（L86-91 `Finding`、L94-112 `PolicyRequest`、L133-156 `VerificationResult`/`EvidenceEvent`/`EvidenceReceipt`、L187-232 V2 信任类型、L235-258 五个 port）、`state.py`（L33-60 `SandboxState`、L117-124 `encode_receipt`、L127-134 `finding_fingerprint`）、`orchestrator.py`（L293-306 路由、L310-366 preflight/execute、L454-537 verify/stall/repair、L485-500 PASS→human_review）、`adapters.py`（L94-196 `PolicyEnginePort` 与 envelope 映射）、`policy/engine.py`（L63-117 `SUBJECT_SPECS`、L303-315 动作词表封闭）、`docs/compliance/DECISIONS.md`（ADR-008、ADR-014、ADR-015）。

**状态**：`PENDING_HUMAN_REVIEW`。本 RFC 未运行任何测试、未做任何 git 操作。
