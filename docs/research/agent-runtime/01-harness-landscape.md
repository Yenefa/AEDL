# 01 — 通用 Coding Harness 景观调研（ARH / AEDL-native Agent Harness 的实证输入）

> 状态：研究笔记，`PENDING_HUMAN_REVIEW`。不重新论证方向（保留 LangGraph + RepairPort + Trust/Transaction 层做薄 ARH），只给 ARH 五模块（ModelAdapter / ContextBuilder / RepairAgent / TrajectoryRecorder / Budget）填实证与细节。
> 本机只读调研，**NOT_RUN**：未实际运行任何一个被调研框架。

## 0. 落点基准（本篇每条结论都要能钉到这里的既有事实）

| 既有事实 | 出处 | 对 ARH 的约束 |
|---|---|---|
| `RepairPort.propose(run_id, candidate_id, findings) -> PolicyRequest` 是冻结签名，repair 后固定走 `preflight → policy → execute → verify → findings` | `sandbox_runtime/src/aedl_sandbox/protocol.py`（`RepairPort`）、`orchestrator.py` `_repair()` | ARH 的"模型动作"只能产出 `PolicyRequest`，不能产出任意副作用 |
| `_detect_stall` 有 finding fingerprint 重复检测 + `max_repairs` + `repair_count` | `orchestrator.py:503-537` | ARH 的 Budget/Stop 必须叠加在这之上，不能替代它 |
| LangGraph 1.2.11 只做外层 routing/checkpoint，硬件判定全在确定性模块 | 设计文档 §7；ADR-008 | 不允许把 verifier/判决塞进 LangGraph 节点或 LLM |
| Trust Plane：EvidenceEvent/EvidenceReceipt、CapabilityGrant 从 orchestrator action ledger 读、晋升前 HumanApprovalReceipt | `protocol.py` V2 段 | ARH 只能是 ledger 的**写入者之一**，不能自授能力 |
| V1 用确定性 RepairPort fixture，"不宣称已具备 LLM 自主修复" | ADR-008 影响段；spec §9 | ARH 是 V2 论证，措辞不得回写 V1 结论 |

---

## 1. Model / Environment / Agent 的四种分离方式与 trajectory 表示

| 框架 | Model 层 | Environment 层 | Agent 层 | Trajectory 表示 | 代价 |
|---|---|---|---|---|---|
| **mini-swe-agent** | `Model`（litellm/openrouter 适配器，负责 query、把回复解析成 `extra.actions`） | `Environment.execute(action) -> {output, returncode, exception_info}`（Local / docker / singularity 等） | `DefaultAgent`（约 100 行，`messages: list[dict]` + `step()` 循环） | **线性 bash 消息流**：`messages` 数组，`serialize()` 产出 `trajectory_format: "mini-swe-agent-1.1"`，含 `info.model_stats`（cost / api_calls / exit_status / submission） | 解析失败走 `FormatError` + `max_consecutive_format_errors=3`；动作无类型，权限只能对**命令字符串**做判断；上下文靠人肉模板控制 |
| **SWE-agent** | LM + ACI 分层（论文 §2-3：ACI = 可用命令 + 环境状态回传格式 + history 组装） | Linux shell 之上的受限命令集（`find_file`/`search_file`/`open`/`edit`…） | Agent 逐步 thought+command（ReAct） | **线性三元组**：每步 `{response, thought, action, observation, state, query}`，`query` 保存喂给 LM 的精确输入 | 有 shell 逃逸（论文自陈 "built atop the Linux shell, also allows access to common Linux commands"）；观察是纯文本，窗口大小直接决定分数（见 §2） |
| **OpenHands** | `LLM` provider 抽象（带 retry/telemetry） | `Runtime` = Docker 容器内 `ActionExecutionServer`（bash session / Jupyter / browser），REST 收发 Action→Observation | `Agent` 读 EventStream 产 Action，`AgentController` 驱动主循环 | **typed event 流**：append-only `EventLog`，`ActionEvent`/`ObservationEvent` 属 `LLMConvertibleEvent`（有 `to_llm_message()`），`ConversationStateUpdateEvent`/`Condensation`/`PauseEvent` 为**内部事件不进 LLM** | 上下文必然膨胀 → 需要 Condenser（`forgotten_event_ids` + summary）；必须维护"LLM 可见"与"内部"两套视图；schema 失败要 `AgentErrorEvent` 单独兜底 |
| **OpenAI Agents SDK** | `Model` interface + provider（OpenAI / multi-provider / third-party adapter） | 环境非核心抽象，另有可选 `Sandbox`（manifest / capabilities / permissions） | `Agent`（instructions+tools+handoffs）由 `Runner` 执行 | **trace/span 树** + `RunState`/items（工具调用是 items，不是自由文本） | 历史由 session 持久化与 item 重放语义决定；guardrail 拒绝后要用占位符清洗 tool 输出（见 §4） |

**D1**：ARH 动作空间取**少量、强类型、单一出口**的 tool-calling 形态——`RepairPort` 本身就是"返回 `PolicyRequest` 的 tool"。线性 bash 可取的只有**表示**（逐字可重放），不是**能力**。
**D2（代价）**：线性 bash 的损失——解析失败靠连续失败熔断（mini `max_consecutive_format_errors`）；权限只能事后对字符串判断。tool-calling 的损失——schema 失败要单独事件兜底；历史压缩必须显式设计（OpenHands Condenser、SWE-agent 折叠 5 步前的 observation）。

---

## 2. ACI 实证：SWE-agent 论文的"接口影响表现"到底有多硬

来源：arXiv:2405.15793（v3），SWE-bench Lite 300 题，GPT-4 Turbo，同模型只换接口（Table 1 / Table 3）：

| 变量 | 分数 | 相对满配 18.0% |
|---|---|---|
| **Shell-only 基线**（只给 Linux shell） | 11.00%（带 demonstration）/ 7.33%（不带） | SWE-agent 高 **+10.7pp / +64% 相对** |
| 无 `edit` 命令（重定向整文件 / sed） | 10.3% | **−7.7pp** |
| `edit` 但去掉 linting guardrail | 15.0% | −3.0pp |
| 搜索：summarized（带"细化查询"提示） | 18.0% | 满配 |
| 搜索：iterative（逐条 next/prev，模仿 Vim/VSCode） | 12.0% | −6.0pp，**比"没有搜索工具"15.7% 还差** |
| 文件窗口 30 行 / 100 行 / 整文件 | 14.3 / **18.0** / 12.7 | 太少 −3.7，太多 −5.3 |
| 上下文：最近 5 条 observation / 全历史 / 无示例 | **18.0** / 15.0 / 16.3 | 全历史 −3.0 |

行为统计（同论文 §5.2、附录 B.3/B.5）：

- 51.7%（1485/2864）轨迹出现 ≥1 次 lint 失败的 edit；任一次 edit 最终成功概率 **90.5%**，**失败一次后降到 57.2%**。
- "成功快、失败慢"：成功实例中位 **12 步 / $1.21**，失败实例均值 21 步 / $2.52；**93.0% 的成功实例在耗尽预算前提交**（全体 69.0%）→ 作者明确说"提高预算不太可能显著提分"。
- 约半数失败（52.0%）是"实现不正确/过拟合"，级联失败 edit 占 23.4%。

**可转成的 RFC 决定**：

- **D3（动作要复合）**：一个动作完成"改 + 立即回显改动后状态"（SWE-agent 的 `edit`×viewer 联动）；拆步会重演 10.3% 的退化。
- **D4（写前/写后机器校验是得分项）**：lint guardrail 单项 +3.0pp、防级联失败（23.4% 失败类）= AEDL 的 `preflight` + read-back verifier；ARH 不得让 LLM 绕过它们"先写再看"。
- **D5（观察窗口受控）**：整文件 dump 掉 5.3pp → ContextBuilder 对 findings/源码设窗口与折叠，不全文塞 prompt。
- **D6（加工具要有 A/B）**：iterative search 12.0 < 无搜索 15.7，"多一个工具"默认不成立。
- **D7（stall/budget 有实证）**：失败实例步数约为成功 1.75 倍、93.0% 成功实例在预算耗尽前提交 → `max_repairs` + fingerprint 熔断成立，**提预算不是修不动的对策**。

---

## 3. Trajectory / observability 为什么成为一级能力

1. **轨迹是唯一调试/归因输入**。SWE-agent `.traj` 存 action/observation 之外还存 `query`（喂给 LM 的精确消息）与 `state`，并配 CLI/web inspector；文档称 "Trajectories are the main output… best way to understand what SWE-agent does"。
2. **崩溃安全 + 版本化**。mini 在 `run()` 的 `finally` 里**每步** `save(output_path)`，序列化结果带 `trajectory_format` 版本号与 model/env/agent 三段 config——轨迹自带"哪套配置跑出来的"。
3. **trace 结构化、可脱敏、可外送**。SDK 默认整次 run 一个 trace，内分 `task/turn/agent/generation/function/guardrail/handoff_span`；`trace_include_sensitive_data` 可关采集；文档警告 `add_trace_processor` 加的脱敏处理器**失败不阻断 exporter**，脱敏与投递必须同处一个应用自有 exporter。
4. **事件流是旁路服务挂载点**。OpenHands `EventLog` append-only，"Services read from the event log but never mutate state directly"，其中就有 **Stuck Detection（滑动窗口 loop prevention）**——与 `_detect_stall` 同型，但纯观测、不进判决。

**D8（TrajectoryRecorder 硬要求）**：每步 `finally` 落盘，带 schema 版本、模型/配置摘要、`repair_count`、`candidate_id` 与 EvidenceReceipt 哈希引用；**轨迹是 ADR-014 的 `report` 类（观测）不是 identity**，不得充当候选身份、不得污染 candidate hash；分"LLM 可见上下文"与"审计全量"两视图（OpenHands LLMConvertible / internal 之分）；敏感字段写入侧脱敏；LangGraph 节点事件可作骨架，但 fingerprint、terminal_reason、receipt 等**判决字段**来自确定性模块。

---

## 4. Guardrail 在 Agents SDK 的位置，以及能否映射到 AEDL policy

SDK 的三类位置（官方 Guardrails 文档）：

| SDK 机制 | 触发点 | AEDL 对应位 | 映射结论 |
|---|---|---|---|
| Input guardrails | **只对链上第一个 agent** 的初始输入；两种模式：`run_in_parallel=True`（默认，可能 agent 已烧 token/执行工具后才 tripped）与 `run_in_parallel=False`（阻塞，agent 不启动） | `preflight` 的 `PolicyPort.evaluate` | **只吸收 blocking 模式**；parallel 模式 = 允许副作用先于否决 → REJECT |
| Tool guardrails | 包在 `FunctionTool` 上，**每次调用**都跑；input 版在执行前可 skip/替换输出/raise，output 版在执行后；`pre_approval_tool_input_guardrails=True` 可把输入检查提前到"待审批中断"之前 | `_execute` 里的 `policy.evaluate` + CapabilityGrant 校验；审批 = HumanApprovalReceipt | **位置一致**：tool-input ≈ 执行前策略；pre-approval ≈ "先核 ledger 能力、再决定是否进入执行" |
| Output guardrails | 只对产出最终输出的最后一个 agent，**总是执行完才跑**；tripwire 会拒绝候选输出、但保留已完成的 tool 调用（tool 输出被替换成占位符 `"Output withheld by an output guardrail."`） | `verify → detect_stall` 与 `TrustPort.assess_promotion` / HumanApprovalReceipt | **位置一致**：晋升前是唯一"无副作用即可否决"的点；失败候选保留为审计证据 = SDK 保留已完成 tool item |

Tripwire 语义（raise `Input/Output/ToolGuardrailTripwireTriggered` 立即停 run、结果可从 exception 取回）可直接对应 AEDL 的 `Outcome.DENY/BLOCKED + terminal_reason`（fail-closed）。

**三个必须写进 RFC 的限制**：

- **D9**：SDK 允许 guardrail 由一个 LLM 子 agent 实现（示例即如此）。AEDL 中**权威判定不得是 LLM**；LLM 只能产出 `Finding`，`CapabilityGrant` 仍来自 orchestrator ledger。
- **D10**：SDK 的"替换输出"能力要降级——AEDL 不允许静默改写观察，任何拦截必须落成显式 `Finding`（否则违反"不把未知降级为通过"）。
- **D11（对不可吸收清单的硬证据）**：文档明确 **hosted / 内建工具（`WebSearchTool`、`CodeInterpreterTool`、`ComputerTool`、`ShellTool`、`LocalShellTool`、`ApplyPatchTool`）不走 tool-guardrail pipeline**。即：给 agent 一个内建 shell 工具，就等于把 guardrail 关掉。

---

## 5. 可吸收清单（抄哪个设计 → 落到 ARH 哪个模块）

| # | 抄什么（出处） | 落到 |
|---|---|---|
| A1 | Model / Environment / Agent 三接口切分（mini `agents/default.py` + `environments/local.py`） | **ModelAdapter**（只管 query/格式化/成本）；Environment 一职由 AEDL 既有 ExecutorPort 承担，不新造 |
| A2 | `step_limit / cost_limit / wall_time_limit_seconds / max_consecutive_format_errors` 四个硬阈值，超限即 `LimitsExceeded/TimeExceeded` 退出并写 `exit_status` | **Budget**：在 `_detect_stall` 之外叠加步/费/时/format-error 上限，**由 orchestrator 强制**，不由模型自觉 |
| A3 | `save()` 放 `finally`、每步落盘、`trajectory_format` 版本号、`info.config` 记三段配置 | **TrajectoryRecorder**（见 D8） |
| A4 | SWE-agent `.traj` 存 `query`（精确输入）+ `state` + `observation` | **TrajectoryRecorder**：必须能重放"当时到底喂了什么" |
| A5 | ACI 四原则：动作简单、动作紧凑、反馈"有信息但简洁"、guardrail 兜错 | **RepairAgent**（动作面）+ **ContextBuilder**（反馈面） |
| A6 | 最近 N 条 observation 全量、更早折叠为一行 | **ContextBuilder** 的历史压缩策略 |
| A7 | findings/错误**去重 + 只保留首个同类错误**（SWE-agent 略去除首条外的重复报错） | **ContextBuilder**；与 `finding_fingerprint` 天然同源，但注意折叠是**给模型看的**，证据侧不得折叠 |
| A8 | SDK guardrail 三位置 + tripwire fail-closed | **RepairAgent 出口**（input≈preflight 语义复述）+ 说明性映射；权威仍在既有 policy，ARH 不新增判定权 |
| A9 | trace/span 树 + `trace_include_sensitive_data` + 脱敏必须内嵌 exporter | **TrajectoryRecorder** 的脱敏与导出实现 |
| A10 | OpenHands：只读 observer 服务挂 append-only 事件流（Stuck Detection） | **TrajectoryRecorder** 旁挂只读分析器，输出建议给 `_detect_stall`，不改判决 |
| A11 | OpenHands：LLM 可见事件 vs 内部事件分层 | **ContextBuilder** 与 **TrajectoryRecorder** 的两视图 |
| A12 | "成功快失败慢"实证（§2） | **Budget**：把"提前停止"设为默认策略而非惩罚项 |

## 6. 不可吸收清单（进来就会削弱 Trust Plane）

| # | 设计 | 为什么不能进 AEDL |
|---|---|---|
| R1 | **任意 shell**（mini `LocalEnvironment` 直接 `subprocess(shell=True)`；SWE-agent 自陈保留通用 Linux 命令） | spec §10 验收第 3 条要求"候选根之外写入被 DENY"；shell 使 policy 只能事后字符串猜测，绕过 candidate content-addressing |
| R2 | **Agent 自己跑验证并宣布通过**（OpenHands/一般 harness 都给 agent 执行测试的自由） | 同源自证，正是 ADR-008 的核心反模式；verifier 必须是独立 `VerifierPort`。agent 跑的检查最多作为 `report` 类建议性 Finding |
| R3 | **Agent 提交即完成**（mini `local.py`：输出首行是 `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` 就 `Submitted` 并以 submission 为结果） | 这是"模型自我宣告 PASS"；AEDL 的 PASS 只能来自 verifier + 晋升只能来自 HumanApprovalReceipt |
| R4 | **自由写文件 / 重定向式编辑** | 论文实测无 `edit` 只有重定向时 10.3%，且重写整文件会污染冻结 baseline；写入必须走 candidate 工作区与 executor 单点 |
| R5 | **并行（非阻塞）guardrail** | 允许副作用先于 tripwire 发生；AEDL 要求人工中断必须在写入/晋升之前（spec §7） |
| R6 | **LLM guardrail / handoff 作为授权来源** | CapabilityGrant 只能来自 orchestrator action ledger；模型（含子 agent）说话没有 authority |
| R7 | **把容器隔离当安全边界**（OpenHands Docker Runtime 的定位） | ADR-008 明确否决"只做进程/文件系统执行沙盒"；容器是隔离不是设计域策略 |
| R8 | **把 trajectory 当证据身份** | ADR-014：`report` 是观测不是 artifact；轨迹哈希不能进入 candidate identity 或晋升谓词 |

## 7. KEEP / REFERENCE ONLY / REJECT 结论表

| 对象 | 判定 | 一句话 |
|---|---|---|
| mini 的 Model/Environment/Agent 三接口与 100 行主循环 | **KEEP** | ARH 的骨架照此做薄 |
| mini 的 step/cost/wall-time/format-error 四阈值 | **KEEP** | 与 `max_repairs`/fingerprint 并列的第二套熔断，orchestrator 强制 |
| mini 每步 `finally` 落盘 + 版本化 trajectory | **KEEP** | TrajectoryRecorder 的默认行为 |
| SWE-agent ACI 四原则与 Table 3 实证 | **KEEP** | D3–D7 的唯一实证来源 |
| SWE-agent `.traj` 含 `query` 的可重放结构 | **KEEP** | 审计需要"精确输入" |
| Agents SDK 的三类 guardrail 位置与 tripwire | **KEEP（仅结构）** | 判定权仍在 AEDL policy，SDK 只借位置语义 |
| Agents SDK trace/span 树与敏感数据开关 | **KEEP** | TrajectoryRecorder 的结构与脱敏规范 |
| OpenHands append-only EventLog + 只读 observer | **KEEP** | 事件流骨架 + 旁挂分析 |
| OpenHands LLM 可见/内部分层事件 | **KEEP** | 两视图分界 |
| SWE-agent/mini 的通用 shell 与 mini 的 `shell=True` | **REJECT** | R1 |
| Agent 自跑验证 / 自提交即完成 | **REJECT** | R2、R3 |
| 并行 guardrail、LLM guardrail 授权 | **REJECT** | R5、R6 |
| OpenHands 式 Docker 隔离作为安全主张 | **REJECT** | R7（容器可作运行载体，但不构成安全/授权主张） |
| 迭代式搜索工具、更多 bash 工具 | **REFERENCE ONLY** | D6：无 A/B 证据不上工具 |
| 各框架的多 agent handoff / 子 agent 编排 | **REFERENCE ONLY** | 与 AEDL 单候选单写者锁（ADR-015）冲突面未评估 |
| SDK 具体 Session/存储实现 | **REFERENCE ONLY** | AEDL 已有 LangGraph checkpoint + ledger，不引第二套状态真源 |

## 8. 未验证 / 限制

- **NOT_RUN**：四个框架均未实际运行；所有分数为论文/文档自述。
- **TO_VERIFY**：SWE-agent 1.x 的 action/config 源码路径未逐一定位（ACI 细节来自论文与官方文档，非源码核对）。
- **TO_VERIFY**：mini-swe-agent v2 是否内置 observation 折叠（本篇只核对 `agents/default.py`、`environments/local.py`；折叠数字来自论文）。
- **UNKNOWN**：OpenHands Stuck Detection 窗口参数与 `_detect_stall` fingerprint 的等价性。
- **UNKNOWN**：LangGraph checkpoint 与 ARH trajectory 的重复存储成本。
- 未评估：多模态/浏览器工具、跨任务 memory/skill 类 capability。

## 来源

1. SWE-agent 论文（arXiv:2405.15793，CC BY 4.0）：摘要 https://arxiv.org/abs/2405.15793 ；正文（Table 1、Table 3、§5.1/§5.2）https://arxiv.org/html/2405.15793v3
2. mini-swe-agent 仓库与 README：https://github.com/SWE-agent/mini-swe-agent
3. mini-swe-agent `agents/default.py`（AgentConfig 阈值、`step/query/execute_actions`、`serialize/save`）：https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py
4. mini-swe-agent `environments/local.py`（`shell=True`、`_check_finished` 提交哨兵）：https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/environments/local.py
5. SWE-agent trajectory 文档（`.traj` 结构、`query`/`state` 字段）：https://github.com/SWE-agent/SWE-agent/blob/main/docs/usage/trajectories.md
6. SWE-agent trajectory inspector：https://swe-agent.com/latest/usage/inspector/
7. OpenHands Events（typed event、LLMConvertible 分层）：https://docs.openhands.dev/sdk/arch/events
8. OpenHands Runtime 架构（Docker ActionExecutionServer、REST Action→Observation）：https://docs.openhands.dev/openhands/usage/architecture/runtime
9. OpenHands Backend 架构（Agent/EventStream/Runtime 类图）：https://docs.openhands.dev/openhands/usage/architecture/backend
10. OpenHands Conversation（EventLog append-only、Stuck Detection、只读服务）：https://docs.openhands.dev/sdk/arch/conversation
11. OpenHands SDK 总览（Security：执行前动作风险评估）：https://docs.openhands.dev/sdk/arch/overview
12. OpenHands `openhands/README.md` 架构说明：https://github.com/OpenHands/OpenHands/blob/3ec999e8/openhands/README.md
13. OpenAI Agents SDK Guardrails（三类位置、execution modes、tripwire、内建工具不走 pipeline）：https://openai.github.io/openai-agents-python/guardrails/
14. OpenAI Agents SDK Tracing（trace/span 结构、敏感数据开关、脱敏 exporter 警告）：https://openai.github.io/openai-agents-python/tracing/
15. OpenAI Agents SDK Tool guardrails API：https://openai.github.io/openai-agents-python/ref/tool_guardrails/
16. OpenAI Agents SDK Sandbox Permissions（manifest/permissions 类型）：https://openai.github.io/openai-agents-python/ref/sandbox/permissions/
17. 本地：`sandbox_runtime/src/aedl_sandbox/protocol.py`、`sandbox_runtime/src/aedl_sandbox/orchestrator.py`、`docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md` §7/§9/§10、`docs/compliance/DECISIONS.md` ADR-008、ADR-014、ADR-015。
