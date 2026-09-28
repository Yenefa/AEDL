# 05 · Repair 收敛能力 Benchmark Protocol（RFC 交付物④ 可执行条款）

> 回答一个问题：真实 LLM 接回 AEDL 后，"它能根据 verifier findings 反复修复并收敛"这一主张如何被**测**、被**对照**、被**复算**。
> 方向（保留 LangGraph + RepairPort + Trust/Transaction 层，做薄的 AEDL-native Agent Harness）已定，本文不重论证，只填实证条款。
> 状态：本文**未运行任何 benchmark**，所有数量结论为口径推导或文献引用 → 标 `NOT_RUN` / `TO_VERIFY` / `UNKNOWN`。

## 0. 本地锚点（本协议必须贴着的既有事实）

| 事实 | 出处 |
| --- | --- |
| `terminal_reason` 全集含 `STATE_PROMOTED` / `REPAIR_STALLED` / `REPAIR_LIMIT_REACHED` / `APPROVAL_HUMAN_REJECTED` / `EXECUTION_*` / `VERIFY_IDENTITY_MISMATCH` / `EVIDENCE_RECEIPT_INVALID`；policy DENY 直接把 `decision.reason_code` 写进 `terminal_reason` | `orchestrator.py` `_preflight` / `_execute` / `_detect_stall` |
| stall 检测**先于**上限：fingerprint 相同 → `REPAIR_STALLED`；否则 `repair_count >= max_repairs` → `REPAIR_LIMIT_REACHED` | `_detect_stall`（`max_repairs` 默认 3） |
| fingerprint 只取 findings 的 `(code, message)` 排序后 sha256，**不含 `details`** | `state.finding_fingerprint` |
| PASS 不是 terminal：PASS → `pending_human_action` → `interrupt()` → `human_review` | `_verify` / `_human_review` |
| 每轮 verify 写一条 receipt（`event_type="verification"`，`payload.sequence = repair_count+1`，`payload.findings` 逐轮留存于 receipt 文件） | `trust/store.py::record` |
| `SandboxState.findings` / `verification_result` **只保留最后一轮**，历史轮次要回读 receipt | `state.py` / `orchestrator._verify` |
| policy 只存最后一次 `policy_result{outcome, reason_code, findings}`，**不含 action_id** | `state.encode_policy_decision` |
| V1 确定性基线已存在：`_TestOnlyRepair` + `_TestOnlyVerifier`（attempt≥2 才 PASS，policy/trust 用真实实现） | `adapters.py::build_test_only_fixture_orchestrator` |

**直接后果（RFC 决定 D0.1）**：benchmark 的逐轮指标一律从 `receipt_root/<run_id>/<event_hash>.json` 读，不读 `SandboxState.findings`；否则拿到的是最后一轮快照，regression 差集口径会错。

## 1. 指标定义与判定口径

### 1.1 收敛（converged）——三层，禁止混用

设 run `r` 的轮次序列为 `t=0..T`，`F_t` = 第 `t` 次 verify 的 finding 集合（元素规范化为 `(code, message)`）。

- **D1.1 `machine_converged`**（机器收敛，主指标）：`verification_result.status == PASS` 且 `pending_human_action` 非空。
  与 `terminal_reason` 解耦，因为 PASS 会停在 interrupt 而不是 terminal。
- **D1.2 `promoted`**：`terminal_reason == "STATE_PROMOTED"`。**benchmark 必须把人工审批脚本化**为恒 `APPROVED` + 具名 `approved_by`（`resume()` 强制非空）；出现 `APPROVAL_HUMAN_REJECTED` 说明 harness 缺陷，该 run 记 `INVALID_RUN` 而非"未收敛"。
- **D1.3 `converged_strict`**（计入发表结论的口径）：`machine_converged` **且** `new_regressions == 0` **且** `faults_all_cleared == 1`（全部注入 fault 对应 finding 已从 `F_T` 消失，见 §2 D2.2）**且** `invalid_proposals == 0`。
- 失败分类互斥，且必须**分开报告**，不得合并成一个 "fail rate"：
  - `REPAIR_STALLED` → **stall 型**（原地打转，模型自认为在改但 findings 不变）；
  - `REPAIR_LIMIT_REACHED` → **budget 型**（在改但太慢，`repair_count=3` 用尽）；
  - `POLICY_*` 前缀 → **policy 拒绝型**；
  - `EXECUTION_*` / `VERIFY_IDENTITY_MISMATCH` / `EVIDENCE_RECEIPT_INVALID` → **fail-closed 异常**，单列为 harness/环境缺陷，**不得计入模型能力分母**（ABC 的 outcome validity：评分器故障不能算被试失败）。

### 1.2 指标公式

| 指标 | 公式 / 判定 | 数据来源 |
| --- | --- | --- |
| `converge_rate` | `#{converged_strict} / #{valid_runs}`，配 **Wilson 95% CI**（禁用 CLT 正态区间，小样本下严重低估不确定性） | 上述字段 |
| `pass@1 / pass@k` | k 次独立 run，Chen et al. 无偏估计 `1 - C(n-c,k)/C(n,k)`；k=1 即 `c/n` | run 级布尔 |
| `pass^k`（**主报告口径**） | 全部 k 次都收敛的比例（τ-bench 定义）。AEDL 卖点是"不绕过 Trust Plane"，**可靠性优先于乐观上界** |
| `new_regressions` | `F_T \ F_0`；`regression = |F_T \ F_0| > 0`；比率 `= |F_T \ F_0| / max(1,|F_T|)` | receipt 逐轮 findings |
| `fixed_findings` | `|F_0 \ F_T| / max(1,|F_0|)` | 同上 |
| `invalid_proposals` | 见 D1.4 | 见 D1.4 |
| `policy_denied_runs` | `terminal_reason` 匹配 `POLICY_*` 前缀 → 1/0，跨 run 求率 | `terminal_reason` |
| `rounds` | `repair_count`；报告 median / p95，不报均值（受上限 3 截断） | `repair_count` |
| `verifier_calls` | `#{evidence_receipts[i].event_type=="verification"}` | `evidence_receipts` |
| `tokens` | `Σ(in, out, cache_read, cache_write)` per run，四类分列 | **AEDL state 无此字段**，须 Harness 侧 JSONL 记录 → `NEW_FIELD` |
| `cost_usd` | `Σ(tokens 类 × 价目) + 价目 as-of 日期` | 同上 |
| `latency_ms` | per run wall-clock，报 p50/p95 | Harness 侧 |
| `cost_per_converged` | `total_cost / #{converged_strict}`（失败 run 的成本必须进分子） | 派生 |

**D1.4 invalid proposals vs policy rejects（必须分开，且当前有数据缺口）**
- `preflight` 与 `execute` 都会 `policy.evaluate`，任一 `!= ALLOW` 即 terminal，所以**单个 run 内最多 1 次 policy DENY**——AEDL 的 fail-closed 决定了不可能在 run 内累计多次拒绝。
- 且 `encode_policy_decision` 不含 `action_id`、`phase` 被覆盖为 `TERMINAL`，**仅凭 state 无法区分"preflight 拒绝（提案不合规）"与"execute 拒绝"** → 标 `TO_VERIFY`（policy reason_code 是否语义可分）。
- **RFC 决定**：`invalid_proposals` 由 **Harness 侧**在把 RepairPort 提案交给 policy 前做 schema / allowed-ops 预校验并计数（可多次、可逐 proposal）；`policy_denied_run` 归 Trust Plane 一侧。两者不得合并，也不得互相替代——这正是"LLM 不绕过 Trust Plane"的可观测证据。

**D1.5 口径红线（来自 SWE-bench 教训）**：`new_regressions == 0` **不等于**修对了。SWE-bench 只跑 PR 改过的测试文件，导致 7.8% 的"正确"补丁实际错误，行为差分后达 29.6% 行为分歧，整体虚高 6.4 个百分点。因此 `converged_strict` 必须额外挂一条 **held-out verifier**（不进 prompt 的第二套检查/全量回归），其结果单独记为 `heldout_pass`。缺 held-out 时该指标标 `TO_VERIFY`，不得写进主张。

**D1.6 fingerprint 陷阱**：stall 判定忽略 `details`。若 verifier 在修复有实质进展时只改 `details` 不改 `message`，会被误判 `REPAIR_STALLED`（假 stall）。**RFC 决定**：benchmark 要求注入 fault 对应的 finding `message` 必须随修复状态变化；否则该 fault 标 `INVALID_FAULT` 剔除。此条需在冻结 fault set 前跑通 → `NOT_RUN`。

## 2. 故障集设计

**D2.1 双层 fault set，比例 40 注入 + 20 真实 = 60**
- **A 层（真实缺陷，20）**：现有 verifier/preflight 已能报出的真实 findings（例：`EVIDENCE_COMPONENT_SOURCE_MISSING` 类组件证据缺失，见 `EVIDENCE_INDEX` EVID-20260902-001）。真实但**部分会被 policy 在 preflight 直接 BLOCKED**，模型无从修——这类只用来测"模型是否老实失败关闭"，不进收敛率分母。
- **B 层（人为注入，40）**：mutation-testing 思路。参照 MuBench（1,700 个变异缺陷，Major 框架 7 类 mutator，过滤不可编译/测试不杀的变异）与 Just et al. 2014（357 个真实缺陷 vs 230,000 变异：73% 真实缺陷与变异耦合，但 **17% 真实缺陷不与任何变异耦合）→ 注入缺陷是真实缺陷的**有偏替代**，报告里必须写这条限制，禁止声称"覆盖真实硬件缺陷分布"。

**D2.2 注入的四条硬条件（逐条校验，不满足即剔除）**
1. **可检出（killable）**：注入后 `F_0` 必须包含该 fault 对应 finding——否则是 mutation testing 的 equivalent/stillborn mutant，测不出能力；
2. **可修（有 oracle）**：存在确定性修复路径，V1 确定性 RepairPort 必须能在同样 `max_repairs` 下收敛 → 这条同时把 fixture 变成 ABC 所说的 "automatic oracle solver"（任务有效性自检）；
3. **注入在数据/subject 层，不改 verifier、不改 policy**——注入点必须与模型可控变量正交；
4. **可逆、可复现**：注入以 diff + sha256 冻结成 `fault_set_v1.json`，每次 run 前校验 hash；每个 `(fault_id, model, run)` 由 `run_id` 派生同一初始 candidate 快照（`candidate_hash` 已提供逐轮内容哈希），模型无法影响注入本身（ABC 的 T.5 ground-truth 隔离 / T.6 环境冻结）。

**D2.3 规模依据**：60 个 fault 下，比例型指标的 Wilson 95% 区间半宽约 ±12pp（n=100 约 ±10pp）——此为区间公式推导，非实测，标 `TO_VERIFY`（实际收敛率未知，需 pilot 后重算）。低于 30 个 fault 时任何模型间差异都不可解释 → 不足 30 标 `INSUFFICIENT_SCALE`。

## 3. 对照设计

**D3.1 四臂对照，全部同 fault、同 candidate 字节、同 `F_0` 快照、同 allowed ops、同 `max_repairs=3`**
| 臂 | 内容 | 用途 |
| --- | --- | --- |
| B0 | V1 确定性 RepairPort fixture（已存在） | harness / 指标自检：预期 100% 收敛、`rounds=2`、0 token；它**不**是能力基线，是评分器正确性证据 |
| B1 | `max_repairs=0`（不修复） | 得到 `F_0` 与不可修下界 |
| M | LLM-A / B / C，同一 RepairPort 接口 | 唯一自变量 = 模型 |

**D3.2 变量控制**：`allowed_ops`（`action`/`action_id`/`subject` 动作空间）冻结；上下文 schema 冻结（每轮模型只能看到 `findings{code,message,source,details}` + candidate + allowed ops，不许看到 gold fix）；temperature/seed 显式记录（即使 temp=0 也不假设确定性，见 D3.4）；价目与模型版本标识冻结；每臂独立 workspace（`run_id` 派生），禁止共享状态。

**D3.3 配对与统计**：同一 `fault_id` 上做**配对**比较（配对 bootstrap 或 exact McNemar），不用独立两样本检验；比例区间用 Wilson / Beta-Bernoulli 后验，**禁用 CLT 正态区间**（Bowyer et al.：几百样本以下 CLT 区间覆盖率 92.5% vs 名义 95%，且可能溢出 [0,1]）。

**D3.4 run 次数（方差证据是硬依据）**：《On Randomness in Agentic Evals》在 SWE-bench-Verified 上跑 6 个配置 × 10 次 = 60,000 条轨迹：单 run `pass@1` 极差 **2.2–6.0 个百分点**，标准差 **>1.5pp，即使 temperature=0**；作者结论是 2–3pp 的"改进"很可能是噪声。因此：**默认 k=10 runs / (fault, model)**；Epoch AI 的 benchmark review 也把 "≥5 runs/model 才有 error bars" 列为统计充分性门槛 → k<5 直接判 `INSUFFICIENT_RUNS`，不许出结论。若只跑 k=5，必须声明"只能分辨 ≥X pp 差异"，X 由 pilot 方差定 → `TO_VERIFY`。

**D3.5 污染**：OpenAI 2026-02 审计发现 SWE-bench Verified 抽样 138 题中 59.4% 测试设计有缺陷、且所有受测前沿模型都"见过"部分题目与答案，故停用该基准。AEDL 的 fault set 是自造且**不公开 oracle 修复**，天然规避该风险；但 fault 的**描述模板**若与训练语料同构仍可能被模式记忆 → 标 `TO_VERIFY`，缓解手段是 held-out 子集 + 不公开 fault 描述。

## 4. 成本与退化报告规范

**D4.1 双口径**：`tokens`（原始计数，模型无关、可事后复算）**必须**与 `cost_usd`（价目表 × as-of 日期）分开报。只报 USD 会被质疑价目选择，只报 token 无法比较成本——两者都报，且价目表随 run 记录冻结。

**D4.2 缓存单列**：`cache_read` 必须与普通 input 分开计。AWS `agent-cost-bench` 明确指出：agentic run 中 cache read 常占 prompt token 约 90%，漏算缓存价会把成本高估约 5 倍，使横向比较失效。

**D4.3 分布而非均值**：报 p50/p95（latency、tokens/round、cost/run），并**分别报收敛 run 与失败 run 的成本**——失败不是免费的。禁止把 cost 压成单一标量分数（AgentSLABench 的 EASR 那类加权指标只能作附注，不能作主指标，否则"高成本成功"与"低成本成功"被混为一谈）。

**D4.4 退化曲线**：`cost` 与 `tokens` 必须按 `repair_count` 展开成 per-round 曲线，用来回答"第 3 轮还在修是否值得"；同时报告 `REPAIR_LIMIT_REACHED` run 的沉没成本占比。报告格式：每 run 一行 JSONL（`run_id, fault_id, model_id, scaffold_hash, seed, temperature, repair_count, verifier_calls, tokens{}, cost_usd, latency_ms, terminal_reason, converged, F0_hash, FT_hash`）。

## 5. 最小可行规模

| 档位 | 组成 | run 数 | 能支撑什么 |
| --- | --- | --- | --- |
| Pilot（流程自检） | 20 faults × 2 models × 5 runs | 200 | 只验证 harness 能跑通、指标能算出；**不得出能力结论** |
| 主实验（可发表下限） | 60 faults × 3 models × 10 runs + B0/B1 各 60 | 1,860 | 配对比较 + Wilson 区间 + run 方差控制 |
| 削减方案 | 60 × 3 × 5 | 900 | 仅能分辨 **较大**差异，须显式写明检出下限，小差异标 `TO_VERIFY` |

依据：① run 次数受 2.2–6.0pp 单 run 方差与"≥5 runs"门槛约束（§3.4）；② fault 数受 Wilson 区间约束（§2.3）；③ 模型数 3 是"能否区分模型"的最小可比集合，1 个模型没有对照。
**UNKNOWN**：AEDL 域内 LLM 的实际收敛率分布未知，正式 power 计算（决定 n 或 k）必须先跑 pilot 拿到 `p̂` → 本文不编造数值。总成本同样 `UNKNOWN`（依赖价目与上下文长度，pilot 后可估）。

## 6. 冻结清单（写 production Agent 之前 vs 之后）

**必须先冻结（改任一项 = 结果不可比，须重跑全量）**
1. `fault_set_v1.json`：fault_id、注入 diff、oracle 修复、killable 校验、sha256；
2. 指标口径：`converged_strict` 定义、`F_0/F_T` 差集口径、terminal_reason 分类映射（§1）；
3. 上下文 schema：模型每轮看到什么、不看到什么（含"不给 gold fix"）；
4. `allowed_ops` 动作空间 + `max_repairs=3` + 人工审批脚本化为恒 APPROVED；
5. 随机性控制：temperature、seed 策略、`k` runs、独立 workspace、无跨 run 状态；
6. 模型标识规范（provider / model id / 版本快照日期）与价目表 as-of；
7. verifier / policy / trust 版本绑定（`actor_id` + 代码 hash）、`finding_fingerprint` 算法、receipt 读取路径。

**冻结之后仍可改**
- prompt 措辞、系统提示、上下文压缩（但每改一次 = 新 `scaffold_hash`，须重新计为新臂并重跑）；
- harness 内部实现（LangGraph 节点结构），**前提是不改 `protocol.py` / `state.py` 的语义与 reason-code 命名**；
- 价目表数值（可按新价目复算 `cost_usd`，`tokens` 不变）；
- 新增 fault 生成 `fault_set_v2`（**追加**，v1 不删不改，跨版本不可比需声明）；
- 报告形式、图表、排序方式。

## 7. 指标总表（指标 | 定义/公式 | 数据来源 | 口径风险）

| 指标 | 定义 / 公式 | AEDL 数据来源 | 口径风险 |
| --- | --- | --- | --- |
| `machine_converged` | status==PASS 且有 pending_human_action | `verification_result.status`、`pending_human_action` | PASS 不是 terminal，读 `terminal_reason` 会漏 |
| `promoted` | terminal_reason==STATE_PROMOTED | `terminal_reason` | 依赖人工审批，须脚本化否则引入人类方差 |
| `converged_strict` | 上者 + 无回归 + 全清 fault + 无无效提案 | 派生 | 缺 held-out verifier 时虚高（SWE-bench 弱测试） |
| `stall_rate` | `#{REPAIR_STALLED}/valid` | `terminal_reason` | fingerprint 忽略 `details` → 假 stall（D1.6） |
| `budget_rate` | `#{REPAIR_LIMIT_REACHED}/valid` | `terminal_reason` | 与 stall 合并会掩盖"打转 vs 太慢"的诊断差异 |
| `new_regressions` | `|F_T\F_0|>0`，比率同式 | receipt `payload.findings` 逐轮 | 只在 verifier 覆盖范围内成立；`state.findings` 仅末轮 |
| `fixed_findings` | `|F_0\F_T|/|F_0|` | 同上 | findings 变少 ≠ 修对，须 held-out 交叉 |
| `invalid_proposals` | Harness 预校验失败的提案数 | **NEW_FIELD**（state 无） | 仅 state 不可得，禁与 policy DENY 合并 |
| `policy_denied_runs` | terminal_reason ∈ `POLICY_*` | `terminal_reason` + `policy_result.outcome` | 单 run 上限 1 次；preflight/execute 不可区分 `TO_VERIFY` |
| `rounds` | `repair_count`（median/p95） | `repair_count` | 受 `max_repairs=3` 截断，均值无意义 |
| `verifier_calls` | verification receipt 计数 | `evidence_receipts[].event_type` | fail-closed 分支（身份不符/回执无效）不写回执 → 少计 |
| `failclosed_rate` | EXECUTION_/VERIFY_/EVIDENCE_ 类占比 | `terminal_reason` | 必须剔出模型能力分母，属评分器故障 |
| `tokens` / `cost_usd` / `latency` | Σ分类 token、价目复算、p50/p95 | **Harness JSONL（NEW_FIELD）** | AEDL state 无字段；漏缓存价 ≈ 5× 高估 |
| `pass@k` / `pass^k` | Chen 无偏估计 / 全 k 次收敛 | run 级布尔 | k=1 单 run 噪声 2.2–6.0pp，禁单 run 下结论 |

---

## 来源（全部为查证过的 URL）

**本地**
- `sandbox_runtime/src/aedl_sandbox/orchestrator.py`、`protocol.py`、`state.py`、`adapters.py`、`trust/store.py`
- `docs/evidence/EVIDENCE_INDEX.md`（Evidence 格式与口径；本 benchmark 结果将来按 `EVID-YYYYMMDD-NNN` 入册）

**评测方法学 / 批评**
1. SWE-bench（评测方法：fail-to-pass + pass-to-pass 双测试集）— https://arxiv.org/abs/2310.06770
2. OpenAI, *Why we no longer evaluate SWE-bench Verified*（2026-02：抽样 138 题中 59.4% 测试设计有缺陷；受测前沿模型均"见过"题目与答案；停用建议）— https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/
3. *Are "Solved Issues" in SWE-bench Really Solved Correctly?*（7.8% 补丁经全量测试判错、29.6% 行为分歧、解析率虚高 6.4pp）— https://arxiv.org/abs/2503.15223
4. *SWE-Bench+* / solution leakage（Lite 33.3%、Verified 33.0% 题目直接泄漏解法）— https://arxiv.org/pdf/2410.06992
5. UTBoost（Verified 500 题中 26 题测试不足，修正后 24.4% 榜单排名变化）— https://ddkang.substack.com/p/swe-bench-verified-is-flawed-despite
6. Epoch AI 对 SWE-bench Verified 的 review（"统计充分性：每模型 ≥5 runs 才有 error bars"）— https://epoch.ai/benchmarks/swe-bench-verified/review
7. *Establishing Best Practices for Building Rigorous Agentic Benchmarks*（ABC 清单：task validity / outcome validity / reporting；oracle solver、环境冻结、ground-truth 隔离、显著性与 baseline 要求）— https://arxiv.org/abs/2507.02825
8. *On Randomness in Agentic Evals*（60,000 轨迹；单 run pass@1 极差 2.2–6.0pp、SD>1.5pp 含 temp=0；建议多 run + power analysis + pass@k/pass^k）— https://arxiv.org/abs/2602.07150
9. *Position: Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints*（小样本 CLT 区间失效，推荐 Wilson / Beta-Bernoulli）— https://arxiv.org/abs/2503.01747
10. τ-bench（pass^k 定义：k 次全部成功的比例）— https://arxiv.org/abs/2406.12045
11. HumanEval pass@k 无偏估计（Chen et al. 2021）的组合式说明与实现参考 — https://github.com/aws-samples/sample-agent-cost-bench/blob/main/agent_cost_bench/stats.py

**故障注入 / repair 度量**
12. *Benchmarking Automated Program Repair: Real-World and Artificial Bugs*（MuBench 1,700 变异缺陷、7 mutator、过滤规则；批评跨环境/不同 candidate size 的不公平对照）— https://par.nsf.gov/servlets/purl/10580915
13. *Are Mutants a Valid Substitute for Real Faults?*（357 真实缺陷 / 230,000 变异：73% 耦合、**17% 真实缺陷不与任何变异耦合**）— https://homes.cs.washington.edu/~rjust/publ/mutants_real_faults_fse_2014.pdf
14. *Equivalent Mutants in the Wild*（等价变异体中位率 2.97%）— https://homes.cs.washington.edu/~rjust/publ/equi_mutants_ems_issta_2024.pdf
15. *A Correlation Study between Automated Program Repair and Test-Suite Metrics*（测试套件质量与修复回归率相关；mutation score 与 regression ratio 的关系）— https://mboehme.github.io/paper/EMSE17.pdf
16. *Repair 作为 mutation testing 的对偶（AE）* — https://www.cs.unm.edu/~forrest/publications/ase-13.pdf

**成本 / 资源报告**
17. AWS `agent-cost-bench`（token 分类与价目配置；cache read 占比与漏算 ≈5× 高估；pass@1/pass^k/Wilson 报告）— https://github.com/aws-samples/sample-agent-cost-bench
18. *AgentSLABench*（多维 profile、按 episode 记 cost/latency、EASR 只作附注）— https://arxiv.org/html/2608.00805
19. Stanford HELM（accuracy + efficiency 等 7 指标、prompt 模板/采样数/多 seed 披露清单）— https://benchmarkingagents.com/stanford-helm/
