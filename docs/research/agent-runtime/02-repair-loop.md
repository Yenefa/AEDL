# 02 — Repair-loop Agent：failure → diagnosis → proposal → feedback 的已验证模式

> 纯研究记录。本文件不修改任何运行时代码；所有 AEDL 行为引用均来自当前 `main` 源码静态阅读，**未运行任何测试（NOT_RUN）**。
> 目标读者：`agent-runtime` RFC 作者。每节都应能落成 RFC 的一个决定。

---

## 0. 锚点：AEDL 现状（事实，不是建议）

| 事实 | 位置 |
| --- | --- |
| `RepairPort.propose(run_id, candidate_id, findings) -> PolicyRequest` 是冻结协议 | `protocol.py` L251-252 |
| `_repair()` 把返回值的 `action / action_id / subject` 原样存进 `repair_plan`；但 `_preflight()` 构造的 `PolicyRequest` 用的是**自己的** `action="preflight"`、`action_id=f"preflight-r{repair_count}"`，只借用 `plan.subject`，随后才走 policy → execute → verify | `orchestrator.py` L525-537, L320-337 |
| FAIL 后顺序是 `verify → detect_stall → repair → preflight`，fingerprint 判重**先于** `repair_count >= max_repairs` 判定 | `orchestrator.py` L297-306, L503-523 |
| `finding_fingerprint()` 只对 `(code, message)` 排序后哈希，**`details` 不参与** | `state.py` L127-134 |
| `state.findings` 每轮被 `_verify` 覆盖（只保留最新一轮）；`previous_finding_fingerprint` 只存上一轮；`repair_count / stall_count / max_repairs` 为计数器 | `state.py` L33-60, `orchestrator.py` L479-501 |
| 每轮 verification 的 evidence receipt 带 `sequence = repair_count + 1`，`evidence_receipts` 全程累加（含哈希，不含内容） | `orchestrator.py` L454-483 |
| LangGraph 只做路由/checkpoint，硬件判决在确定性 port（ADR-008 方案 3） | `DECISIONS.md` ADR-008 |

**含义**：LLM 可插的位置只有 `RepairPort.propose` 一个点，以及（未冻结的）喂给它的上下文构造。本文其余部分回答：这个窄口里放什么才既收敛又不绕 Trust Plane。

---

## 1. 哪些 loop 模式有实证，哪些被证伪

### 1.1 有实证支持（外部 verifier/executor 在环）

| 模式 | 证据 | 来源 |
| --- | --- | --- |
| 生成 → 外部执行 → 带具体失败信息重生成 | Conversational APR 在 10 个 LLM 上均优于同 prompt 重复采样；ChatRepair 修 Defects4J 162/337（$0.42/bug） | [S1] [S2] |
| 反馈要"具体到失败点"，不是"你错了" | 消融：仅告知错误最差；+test name/error/failing line 更好；`Dynamic`（只在失败点变化时给新信息）最好 | [S2] T5 |
| 采样 N 候选 + 外部测试重排 | Agentless：majority voting 77 → +regression 81 → +repro test 96（SWE-bench Lite） | [S3] |
| 结构化定位先行再修复 | Loc2Repair：44.7% → 预测定位 48.9/49.1% → oracle 52.4%（配对 +4.3/+4.5/+7.7 pp, p<0.001）；ACR +SBFL 19%→22% | [S6] [S5] |
| 环境二值反馈 + 短期反思记忆 | Reflexion HumanEval pass@1 91.0 vs GPT-4 80.1 | [S4] |
| 外部 critic 定期注入结构化纠偏 | SWE-PRM：40.0% → 50.6%（+10.6 pp），成本低至 $0.2 | [S9] |

### 1.2 被证伪或有条件成立

| 主张 | 反证 | 来源 |
| --- | --- | --- |
| "模型能靠自己发现并改正错误" | 去掉 oracle 标签后，所有被测模型自我纠错后准确率**全部下降**；GPT-3.5 在 GSM8K 上 74.7% 保留原答案，且"改对→改错"多于"改错→改对" | [S7] |
| "Self-Refine 通用有效" | TACL 关键综述：公平设置下**没有任何工作**证明"仅靠 prompting 的 LLM 自评反馈"在一般任务上纠错成功；只有"有可靠外部反馈"的任务有效。Reflexion 被点名使用 ground-truth exact-match 作反馈（oracle） | [S8] |
| "迭代改进一定优于独立重采样" | 复现研究：同为 24 次调用，ChatRepair 迭代修 18 个 bug，独立重复采样修 **23 个**；其 plausible patch **65% 是重复** | [S10] |
| "自我评估迭代是中性的" | Self-Refine 中 self-bias **逐轮放大**，模型感知的提升与真实指标背离 → 优化"假阳性修正"；只有换成准确外部反馈才有真实提升 | [S11] |
| "多智能体辩论优于同成本采样" | 等推理预算下 multi-agent debate 不如 self-consistency | [S7] §4 |
| "加一个 LLM critic 总有帮助" | SWE-PRM 消融：**开源** PRM 把 40.0% 拉到 19.6–38.8%；无结构反馈使轨迹 38.6→51.5 步；过度具体指挥只有 44.8% | [S9] |

**RFC 决定 D1**：LLM 不能持有"我认为已经修好了"的停止权。停止/正确性判据只能来自 `VerifierPort`（已有），这与文献中"外部可靠反馈"这一唯一有效条件完全一致，不需要新增任何自评通道。

---

## 2. 每轮信息流的形状：保留什么、丢弃什么

推荐的单轮信息流（箭头即 prompt 组装顺序）：

```
[任务/subject 冻结段]
+ [当前轮 findings 全量（code, message, source, details）]
+ [历史压缩段：每轮一行 {fingerprint前12位, 诊断一句话, 提案动作+对象, 结果=被拒/重复/推进}]
+ [最近 1 轮的原始 verifier 输出全文]
+ [已试过且被否决的 proposal 清单（结构化，去重用）]
→ LLM 输出：diagnosis → proposal（落成 PolicyRequest 字段）
→ policy → execute → verify → findings_after
```

**必须保留**

- **当前 findings 全量**。fingerprint 判重是对 `(code, message)` 集合做的，Agent 看不到全集就无法预判"再改会不会撞指纹"。
- **已试过的失败提案 + 对应失败信息**。这是 conversational APR 相对重复采样的**全部**增益来源；65% 重复率说明不显式列出"试过什么"，模型会反复产出同一补丁 [S1][S2][S10]。
- **每轮诊断结论**（一句话）。诊断质量直接决定修复率：分析完全正确 → 正确补丁 37.8%，部分正确 5.7%，错误 0.8% [S10]。诊断值得占 token、值得单独存。

**必须丢弃/压缩**

- **全量 LLM reasoning 与原始探索日志**。SWE-agent 默认"只留最近 n 条 observation，其余替换为占位符" [S12]；CAT/SWE-AGILE/CompactionRL 的共同实证是 append-only 上下文饱和后**不升反降**（CAT：ReAct 约 60 轮后下降；SWE-AGILE：保留全部 reasoning 比丢弃差 12.42% vs 15.83%，即 lost-in-the-middle）[S13][S14][S15]。
- **多轮全量 findings 原文**。保留摘要 + 当前轮原文即可，V1 不需要 RAG 进历史。
- **模型对 verifier 的转述**。verifier 输出本就结构化；转述引入噪声（"no-influence" 动作在失败轨迹显著更高：RepairAgent 1.2%→6.2%，ACR 4.9%→14.6% [S16]）。

**AEDL 差距**：`state.findings` 只存最新一轮，`previous_finding_fingerprint` 只存上一轮——**运行时没有多轮轨迹供 LLM 回看**；而 `evidence_receipts` 有全轮 `sequence` + 哈希，可作轨迹的完整性骨架。

**RFC 决定 D2**：新增 `TrajectoryRecorder`（append-only JSON，每轮存 `{sequence, fingerprint, findings_digest, diagnosis, proposal, outcome}`），**不**改 `SandboxState`。ContextBuilder 从它读"压缩历史段"，对齐用已有 `evidence_receipts.sequence`。

**RFC 决定 D3**：上下文采用"滑动窗口 + 摘要"而非全量历史（三条独立工作同向 [S13][S14][S15]）。V1 取"当前轮原文 + 最近 1 轮原文 + 其余轮 1 行摘要"，具体阈值 **NOT_RUN**。

---

## 3. 已知失败模式：已有 X / 外部做法 Y / V1 取舍

| 失败模式 | 已有（AEDL） | 外部做法（证据） | V1 取舍 |
| --- | --- | --- | --- |
| **振荡/原地循环修复**（同一处反复改、补丁只差表面） | `finding_fingerprint` 相等 → 立即 `REPAIR_STALLED`（**早于** max_repairs，`orchestrator.py` L507-513） | OpenHands stuck detector 默认开启：同一 action+observation ×4、action+error ×3、纯自白 ×3、乒乓交替 ×6 即停 [S17]；经验研究中 agent 失败案例平均多花 **3.5×** 交互步，C2.1 "non-progressive iteration" 是主形态，根因 65% 是"坚持错误计划的推理缺陷" [S18] | **复用，不改**。早熔断方向正确：外部证据表明循环一旦形成就是纯烧钱。V1 不加新检测器 |
| **stall 误杀**（真实情况变了但 code/message 没变） | fingerprint 忽略 `details`（`state.py` L130）→ 详情变化也判 stall | OpenHands 按"语义内容"比较 action/observation，忽略 id/时间戳 [S17]；SWE-PRM 用 taxonomy 给出"转向建议"而不是直接停 [S9] | **保持 fail-closed**。把 `details` 纳入 fingerprint 是 `state.py` 契约变更 → **V2 / 需 ADR**。V1 缓解：ContextBuilder 把 `details` 全量给 Agent，让它在提案里制造可观测差异 |
| **局部最优卡死**（每轮都在改，但没进展） | `repair_count >= max_repairs` → `REPAIR_LIMIT_REACHED`（3 次） | 无单一"更好"解法；有效的是**换策略而不是加轮次**：Expert-Executor 分工破解 22.2% 此前不可解的问题 [S18]；SWE-PRM taxonomy 反馈 +10.6 pp [S9] | **复用上限**。V1 在 prompt 侧给"结构性转向"指令（对应 taxonomy），不新增 critic port。证据表明盲目加自由度会拉长轨迹（unguided 38.6→51.5 步 [S9]） |
| **过度修复 / 引入 regression**（over-fixing） | 独立 verifier + candidate 内容哈希重算（`_promote_or_reject` L592）+ 人工审批 + artifact 越界即 fail-closed | LLM 时代 test overfitting 仍在：基于白盒测试的 refinement 让 22 个 fail→pass 中 **14 个**在黑盒测试失败，总体 overfitting 21.8%→25.5%；甚至出现"为了骗过测试把 replace 调三次"和"用 reflection 访问私有方法" [S19]。Reflexion 自生成测试的假阳性率 MBPP 16.3% vs HumanEval 1.4% [S4] | **复用 + 一条禁令**：Agent 不得修改 verifier/测试/合同（它们是"oracle"）；只允许改 candidate 内容。Huang 的"改对→改错"数据 [S7] 说明再加一轮自评反而危险。**V1 不做 test generation**（Reflexion 的高分依赖高质量自测，AEDL verifier 比它更可靠，不要降级） |
| **失败轨迹过长 / 终止不知** | recursion_limit = `6*(max_repairs+1)+10`；`Status=BLOCKED` 走 terminal | 成功多在 ~25 轮内完成；失败长尾（OpenHands 失败需 54 轮才覆盖 80%）[S18]；RepairAgent 强制"修复后必须测试"以堵住 generate-without-test 反模式 [S16] | **复用**。把"每轮必须产出 proposal 或显式放弃"写进 prompt（对应 RepairAgent 的强制验证约束），而非新增控制流 |

---

## 4. proposal-only vs Agent 自己执行

**AEDL 的真实问题不是"要不要执行"**——`execute` 是确定性 compiler、`verify` 是独立 verifier，LLM 从来不该碰。真正的问题是：**下一步动作由谁决定、动作空间多大**。

- **窄动作空间不劣于自由 agent**：Agentless 不让 LLM 决定下一步、不用复杂工具，SWE-bench Lite 32.00% / $0.70，超过当时全部开源 agent [S3]。其论证直接对应 AEDL：工具抽象层本身会出错、30-40 轮决策不可调试、自我反思不足会放大单步错误。
- **但信息不足的题上自由 agent 更好**：经验研究显示流水线**早期**败于定位、agent **晚期**卡循环；缺 stacktrace/线索的题上闭源 agent 明显更好 [S3][S18]。
- **折中已被量化**：只加一个只读定位阶段，resolved +4.3~+7.7 pp [S6]；AST 检索 + SBFL +3 pp [S5]。即**探索能力应加在 diagnosis 侧，不是 execution 侧**。

**RFC 决定 D4**：V1 = **proposal-only**——LLM 只产出 diagnosis + 拟议 `PolicyRequest` 字段，`execute`/`verify` 由既有 port 执行，与 `RepairPort.propose` 冻结签名一致且不动 policy/ledger。**同时**允许 `ContextBuilder` 在 diagnosis 阶段做**只读**仓库检索，结果以只读 artifact 进上下文、不进 candidate。该检索是否需要新 capability grant：**TO_VERIFY**（须对照 `CapabilityGrant` 与 policy 内核，本文未读 policy 实现）。

---

## 5. 单 Repair Agent vs 加 Critic Agent

**证据权衡（不是偏好）：**

支持加 critic：SWE-PRM（外部 critic，taxonomy 引导）+10.6 pp 且**同时缩短**轨迹（37.99 vs 38.64 步）[S9]；Expert-Executor 分工破解 22.2% 此前不可解任务 [S18]；轨迹研究主张"单一 agent 缺乏战略性自我纠正" [S18]。

反对加 critic：

1. **critic 必须比 agent 强，否则有害**：开源 PRM 把 40.0% 打到 19.6–38.8% [S9]。这是最强反方证据——V1 无法承诺 critic 质量。
2. **critic 的价值在"结构化"而非"存在"**：taxonomy 50.6% > unguided 45.8% > prescriptive 44.8% [S9]。把 taxonomy 写进单 agent prompt 即可拿到大部分收益，无需第二个 agent。
3. **AEDL 的 critic 职能已被外部组件占用**：`VerifierPort` 是确定性批评者，`PolicyPort` 是行为批评者。文献里 critic 之所以必要，是因为通用 agent 缺可靠外部判据 [S8][S11]；AEDL 有。
4. 自评偏差有实证：self-recognition 与 self-preference 线性相关（GPT-4 自识别 73.5%）[S20]，且在 self-refine 中逐轮放大 [S11]。加同源 LLM critic 会把偏差带回来，verifier 不会。

**RFC 决定 D5**：V1 = **单 RepairAgent + 结构化 taxonomy prompt + 确定性 VerifierPort**，不新增第二个 LLM agent、不新增 CriticPort。Critic 形态**唯一**保留位置：`REPAIR_STALLED` 触发时进入 escalation（second-opinion 属 **V2 / TO_VERIFY**，且必须仍以 `PolicyRequest` 出口）。这样 V1 每次 LLM 调用都可归约到 `propose` 的输入/输出，审计面最小。

---

## 6. Loop 设计决定表

| # | 决定 | 证据来源 | AEDL 机制 |
| --- | --- | --- | --- |
| D1 | 停机/正确性判据只来自 `VerifierPort`；禁止 LLM 自评停止权 | [S7] [S8] [S11] | **复用** `VerificationStatus` / `_route_after_verify` |
| D2 | 新增 append-only `TrajectoryRecorder`，ContextBuilder 读它；**不改** `SandboxState` | [S1][S10]（重复补丁 65%） | **新增**（record 侧）；**复用** `evidence_receipts.sequence` 做对齐 |
| D3 | 上下文 = 当前轮 findings 全量 + 摘要历史 + 最近 1 轮原文；丢弃全量 reasoning/日志 | [S12] [S13] [S14] [S15] | **新增** ContextBuilder；不改 state |
| D4 | proposal-only：LLM 产 diagnosis + PolicyRequest 字段；执行留给 port；diagnosis 侧允许只读检索 | [S3] [S5] [S6] [S16] | **复用** `RepairPort`/`ExecutorPort`/policy/ledger；只读检索 capability **TO_VERIFY** |
| D5 | 单 RepairAgent + taxonomy prompt；不加第二个 LLM critic；stall 后才考虑 escalation | [S9] [S11] [S18] [S20] | **复用** `_detect_stall`；**新增**仅 prompt 资产 |
| D6 | 反馈内容必须"具体到失败点"，`Dynamic` 式只报增量失败 | [S2] Table 5 | **复用** `Finding.details`（喂全量 details） |
| D7 | 保留已试过且被否决的 proposal 清单用于去重 | [S1][S2][S10] | **复用** D2 的 trajectory 记录 |
| D8 | Agent 禁止修改 verifier/测试/合同；只改 candidate 内容 | [S4] [S7] [S19] | **复用** content-addressed candidate、artifact 越界 fail-closed |
| D9 | 保持 fingerprint(`code`,`message`) 早熔断语义；`details` 入指纹留 V2 | [S17] [S18] | **复用** `finding_fingerprint` / `REPAIR_STALLED`；契约变更 → ADR |
| D10 | 不做多候选采样（N-best + 重排） | [S3]（40 样本后 plateau，上限 41%）、[S5]（@1 19% → @3 26%）说明有收益但会触碰"单 candidate + 人工审批"模型 | **未支持**；需 Trust 层契约变更 → **V2 / TO_VERIFY** |

---

## 7. 不确定性与未验证项

- **NOT_RUN**：本文无任何本地运行。现有 repair loop 的轮次分布、fingerprint 命中率、`max_repairs=3` 是否合适，均未观测。
- **TO_VERIFY**：只读检索所需的 `CapabilityGrant` 与 policy 判定路径（未读 policy 内核）；D3 的具体 token 阈值（外部工作均为代码 agent，AEDL findings 体量小得多，外推无依据）；`REPAIR_STALLED` 后引入 second-opinion 的成本/收益（无直接证据）。
- **UNKNOWN**：verifier 的 finding 粒度是否足以支撑"具体到失败点"（D6 取决于 `Finding.details` 实际填充率，未统计）。
- **最弱一环**：全部外部证据来自代码修复 benchmark（可执行、有隐藏测试）。AEDL 是硬件设计域，verifier 覆盖是**部分**的——若 verifier 永不给 PASS，"外部反馈有效"的结论会退化成只能靠 `max_repairs` 兜底。此缺口无法用现有文献闭合。

---

## 来源

- [S1] Conversational Automated Program Repair — https://arxiv.org/abs/2301.13246
- [S2] ChatRepair: Fixing 162 out of 337 bugs for $0.42 each (ISSTA 2024) — https://arxiv.org/html/2304.00385v2
- [S3] Agentless: Demystifying LLM-based Software Engineering Agents — https://arxiv.org/abs/2407.01489
- [S4] Reflexion: Language Agents with Verbal Reinforcement Learning (NeurIPS 2023) — https://arxiv.org/abs/2303.11366
- [S5] AutoCodeRover: Autonomous Program Improvement (ISSTA 2024) — https://arxiv.org/abs/2404.05427 ；https://github.com/AutoCodeRoverSG/auto-code-rover
- [S6] Loc2Repair：仓库级修复中的文件级定位 — https://arxiv.org/html/2606.30963v1
- [S7] Large Language Models Cannot Self-Correct Reasoning Yet (ICLR 2024) — https://arxiv.org/abs/2310.01798
- [S8] When Can LLMs Actually Correct Their Own Mistakes? (TACL) — https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00713/125177
- [S9] When Agents go Astray: Course-Correcting SWE Agents with PRMs — https://www.alphaxiv.org/abs/2509.02360
- [S10] Studying and Understanding the Effectiveness and Failures of Conversational LLM-Based Repair — https://arxiv.org/html/2503.15050v2
- [S11] Pride and Prejudice: LLM Amplifies Self-Bias in Self-Refinement — https://arxiv.org/html/2402.11436
- [S12] SWE-agent History Processors — https://swe-agent.com/1.0/reference/history_processor_config/
- [S13] CAT: Context as a Tool for Long-Horizon SWE-Agents (ACL Findings) — https://aclanthology.org/2026.findings-acl.1032.pdf
- [S14] SWE-AGILE: Dynamic Reasoning Context (ACL Findings) — https://aclanthology.org/2026.findings-acl.868.pdf
- [S15] CompactionRL: RL with Context Compaction for Long-Horizon Agents — https://arxiv.org/pdf/2607.05378
- [S16] Understanding SE Agents: Thought-Action-Result Trajectories — https://arxiv.org/html/2506.18824v2
- [S17] OpenHands Stuck Detector — https://docs.openhands.dev/sdk/guides/agent-stuck-detector
- [S18] An Empirical Study on Failures in Automated Issue Solving — https://arxiv.org/html/2509.13941v1
- [S19] Test Overfitting in Repository-Level LLM APR (TDD-bench Verified) — https://www.arxiv.org/pdf/2511.16858v1
- [S20] LLM Evaluators Recognize and Favor Their Own Generations — https://arxiv.org/abs/2404.13076
