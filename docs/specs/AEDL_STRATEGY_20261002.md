# AEDL 战略收缩与 RepairBench v0.1（Owner 指令原文存档，2026-10-02）

> 来源：Owner 于 2026-10-02 直接下达的战略指示全文，逐字入库。
> 状态：**现行战略**。后续任务的 Scope 取舍、Kill Gate 判定均以此为准；
> 与本文件冲突的旧路线文档视为 deprecated，具体见 §D（Reality Check）。
> 本文件本身是 Owner 决策记录，不是 Agent 提案；修改需 Owner 明示。

---

最后的机会：你现在接手的是 **AEDL（Automated Electronic Design Loop / 自动化电子设计链）** 项目。

在开始任何编码、重构、Issue、PR 或架构设计之前，请先完整理解下面的项目战略变化。

# 0. 最重要的背景：AEDL 已经发生战略收缩

AEDL 早期愿景是：

```text
自然语言需求
→ 器件选型
→ 原理图
→ ERC
→ PCB
→ DRC
→ review
→ manufacturing files
```

并试图通过：

- LLM / Agent
- MCP
- deterministic executor
- repair loop
- fail-closed gates
- independent read-back
- evidence bundle
- ERC / DRC
- human escalation

构成完整 Automated EDA pipeline。

**现在不要继续按照这个“大而全自动 EDA”方向扩张。**

原因不是项目失败，而是外部生态已经快速 commodity 化：

- Natural Language → schematic 已有 SchGen 等项目；
- KiCad MCP 已经出现多个实现；
- deterministic execution、transaction、rollback、semantic diff、read-back、ERC/DRC automation 已不再稀缺；
- “AI 能修改 KiCad 文件”已经不是值得 AEDL 单独证明的问题；
- “Agent 修改后 ERC=0 / DRC=0”也不足以证明它真的修对了工程问题。

因此：

> **AEDL 不再把“自动生成整个 PCB”作为近期核心研究问题。**

当前项目真正需要证明的是一个更窄、更严格的问题：

# 1. AEDL 当前核心 thesis

> **Can an AI agent repair an electronic design while independently proving that a pre-existing engineering constraint changed from FAIL to PASS, without regressing unrelated constraints?**

即：

> **AI 能否修复电子设计，并通过独立于生成/修改路径的冻结工程合同，证明目标问题确实从 FAIL → PASS，同时没有破坏其他已经成立的工程约束？**

关键词：

```text
Verifiable Repair
Frozen Contract
Independent Oracle
Fresh Artifact
FAIL → PASS
Regression Guard
Repair Causality
Evidence
```

这才是当前 AEDL 的主线。

# 2. AEDL 不再试图证明什么

以下内容 **不是近期 moat，也不是优先级**：

```text
❌ “我们也能自然语言生成原理图”
❌ “我们有 KiCad MCP”
❌ “我们有很多 Agent”
❌ “我们用了 LangGraph”
❌ “我们可以自动 ERC / DRC”
❌ “Agent 可以改 schematic / PCB”
❌ “我们可以自动 routing”
❌ “我们有 rollback”
❌ “我们有 human-in-the-loop”
❌ “我们的 pipeline 很长”
❌ “我们可以一句话生成整块板”
```

这些可以作为 infrastructure 存在，但不要把工程时间花在扩大这些能力上，除非它们直接服务于 **Verifiable Repair Benchmark**。

尤其禁止出现：

> 为了让项目看起来完整，而继续增加工具、Agent、Stage、UI、自动路由、制造流程等 feature。

**Scope expansion 默认视为风险，而不是进展。**

# 3. 当前最重要的技术对象：Repair Episode

一个合格的 AEDL Repair Episode 应该具有以下因果结构：

```text
T0

Frozen Contract C exists BEFORE repair
        │
        ▼
Fresh baseline export
        │
        ▼
C(baseline) = FAIL
        │
        ▼
Agent receives bounded evidence/actions
        │
        ▼
Agent mutates candidate artifact
        │
        ▼
Fresh independent export
        │
        ▼
Same C(candidate) = PASS
        │
        ├── Non-target contracts remain PASS
        │
        └── Structural collateral damage is measured
        │
        ▼
Immutable Evidence Bundle
```

关键原则：

## A. Contract 必须先于 repair 存在

不能：

```text
Agent 修改完
→ 再写一个刚好能让结果通过的 verifier
```

这会破坏 benchmark。

正确流程：

```text
contract frozen at T0
→ baseline evaluated
→ repair
→ exact same contract reevaluated
```

## B. 必须明确证明 before = FAIL

不能只证明：

```text
after = PASS
```

否则无法建立 repair causality。

成功 Repair Episode 至少要求：

```text
before = FAIL
after  = PASS
```

## C. 必须使用 fresh artifact

Verifier 不得相信：

- Agent 自己的 success message；
- tool return 中的 “applied=true”；
- 内存中的 graph；
- mutation command 本身；
- stale export。

必须：

```text
mutation
→ fresh export / reread
→ independent verification
```

**Artifact is the source of truth.**

## D. Verifier 必须与生成路径独立

Agent 不允许修改：

- frozen contract；
- oracle logic；
- expected answer；
- benchmark truth；
- baseline evidence。

如果 candidate 可以修改判断自己是否成功的标准，则 benchmark 无效。

# 4. Primary Oracle 与 Secondary Metric 必须严格分层

近期已经研究过 Microsoft SchGen。

结论：

> **SchGen 不能成为 AEDL Repair Agent 的最终 PASS/FAIL oracle。**

SchGen 的 connectivity comparator 更适合回答：

> Candidate 与 golden netlist 的整体拓扑结构有多相似？

而 AEDL 的问题是：

> 某个预先冻结的工程语义约束是否被修好？

因此 benchmark 必须固定为：

```text
Primary Oracle
=
AEDL Frozen Contract FAIL → PASS

Regression Guard
=
所有 non-target frozen contracts 保持 PASS

Secondary Metric
=
Structural Preservation / Collateral Damage
```

SchGen methodology 可以用于第三层。

一句话：

> **SchGen gives a score. AEDL gives the verdict.**

不要为了兼容 SchGen 改变 AEDL contract semantics。

# 5. 为什么不能直接用 Golden Netlist 做最终答案

Repair task 天生可能存在 multiple valid solutions。

例如合同：

```text
U3.EN must connect to VIN
```

Agent A 和 Agent B 可能通过不同拓扑实现：

```text
A ≠ B topology
```

但：

```text
Contract(A) = PASS
Contract(B) = PASS
```

只要没有破坏其他冻结约束，它们都应该被接受。

因此 AEDL 不应该要求：

```text
candidate == golden topology
```

而应该要求：

```text
candidate ∈ set of contract-valid solutions
```

这是当前 benchmark 设计必须守住的核心原则。

# 6. 当前真正值得做的 moat

当前 AEDL 唯一值得重点发展的 differentiator 是：

```text
Pre-frozen
Generator-independent
Semantic engineering contract
+
Fresh artifact read-back
+
Real FAIL → PASS
+
Non-target regression verification
+
Contract-equivalent multiple solutions
+
Immutable causal evidence
```

重点不是：

> Agent 修了东西。

而是：

> **AEDL 可以证明 Agent 修的是原来的问题，而不是仅仅制造了一个看起来正常的新结果。**

尤其要区分：

```text
Execution success
≠
Repair success
```

例如：

```text
tool call succeeded
file changed
KiCad opens
ERC decreases
```

全部成立，也不自动意味着：

```text
target engineering constraint repaired
```

# 7. 接下来项目应该围绕 RepairBench v0.1 建设

近期主目标不是继续扩大 AEDL。

目标：

# AEDL RepairBench v0.1

建立至少约：

```text
20–30 real repair episodes
```

优先覆盖 3–5 类 fault families。

例如：

```text
1. Missing / wrong semantic net connection

2. Required pin → GND / VIN / VBUS / 3V3 violation

3. Incorrect net-label mutation

4. Component / connection mutation

5. Repair that can easily introduce collateral damage
```

不要为了数量制造毫无意义的 toy fixture。

每个 episode 应尽量包含：

```text
baseline artifact
fault injection
frozen contract
before evaluation
agent attempt
candidate artifact
fresh export
after evaluation
regression result
structural preservation result
evidence bundle
```

# 8. Benchmark 建议报告的指标

至少：

```text
Contract Repair Success Rate
```

目标合同：

```text
FAIL → PASS
```

比例。

```text
Non-target Regression Rate
```

原本通过的 contract 因 repair 被破坏的比例。

```text
False-success Detection Rate
```

Agent / tool / ERC 看似成功，但 independent oracle 发现实际没有修好的案例。

这个指标非常重要。

```text
Structural Preservation Score
```

衡量修复目标问题时，对无关结构造成多少 collateral change。

可以吸收 SchGen endpoint-set / Jaccard / F1 methodology，但必须保留 repair 所需 instance identity / semantic channels。

可选：

```text
Attempts
Token Cost
Latency
Evidence Completeness
Mutation Size
```

但这些暂时属于 secondary metrics。

# 9. 必须设置 Baseline

RepairBench 不能只跑 AEDL 自己。

至少需要：

```text
Generic LLM + existing KiCad/MCP tools
            VS
AEDL Repair Agent
```

尽量：

```text
same model
same task
same initial artifact
same action budget
same context
```

这样才能回答：

> AEDL architecture 到底有没有增加价值？

否则：

```text
AEDL succeeded
```

没有研究意义。

# 10. 项目的 Kill Gate

AEDL 不允许因为 sunk cost 无限继续。

RepairBench v0.1 是当前项目的主要 Kill Gate。

重点验证至少三个 hypothesis：

## H1 — semantic contract catches failures ERC/DRC misses

存在真实案例：

```text
ERC / DRC = PASS
```

但：

```text
Frozen semantic contract = FAIL
```

如果成立，说明 AEDL oracle 具有额外信息价值。

## H2 — independent verifier catches false success

存在案例：

```text
Agent / tool reports success
```

但：

```text
fresh artifact + frozen contract = FAIL
```

如果成立，说明 independent verification 有实际意义。

## H3 — contract semantics accepts multiple valid repairs

存在：

```text
Topology A != Topology B
```

但是：

```text
Contract(A) = PASS
Contract(B) = PASS
```

而单 golden-topology similarity scorer 会惩罚其中一个。

如果成立，说明 repair benchmark 不应该简单退化为 generation benchmark。

如果 RepairBench 完成后发现：

```text
ERC/DRC 几乎已经覆盖所有问题；

Generic Agent 和 AEDL 没有显著差异；

Frozen Contract 没有抓到额外 failures；

Evidence 只是包装日志，没有增加可信度；

多解问题在实际 cases 中基本不存在；
```

那么应该：

> **停止项目，而不是继续添加 feature。**

这是明确的项目终止条件。

# 11. 当前 Scope Freeze

近期默认 **允许投入**：

```text
✅ Frozen Contract semantics
✅ Contract compiler / evaluator
✅ Repair Episode
✅ Fault injection
✅ Fresh artifact exporter
✅ Independent read-back
✅ Regression verification
✅ Evidence bundle
✅ Structural preservation metric
✅ SchGen comparator adapter
✅ Benchmark harness
✅ Baseline runner
✅ Evaluation/reporting
```

近期默认 **禁止主动扩张**：

```text
⛔ full PCB generation
⛔ autorouting
⛔ manufacturing automation
⛔ new fancy UI
⛔ agent count expansion
⛔ unnecessary MCP tools
⛔ generic orchestration refactor
⛔ “完整 EDA platform”建设
⛔ 与 benchmark 无直接关系的 architecture polish
```

只有当某项 infrastructure 是 RepairBench 的 blocker 时才能做。

# 12. 对现有代码的处理原则

不要推翻现有 AEDL。

现有很多工作仍然有价值，例如：

```text
fail-closed
bounded mutation
candidate/baseline isolation
read-back
evidence
permission boundaries
transaction semantics
repair loop
```

但现在要重新分类：

```text
Infrastructure
≠
Research contribution
```

不要因为某个模块“做得很好”就默认它需要继续扩张。

# 13. 第一项任务（已执行，见 Reality Check）

Repo Reality Check（`notes/repairbench-v01/reality-check-2026-10-02.md`）已于
2026-10-02 执行，结论：v0.1 全集为 M2（5 夹具），EDD-001 推迟。

# 14. 输出格式（Reality Check 要求，已执行）

见 `notes/repairbench-v01/reality-check-2026-10-02.md`（A–F 六节）。

# 15. 最后的工程原则

整个后续开发始终遵守：

> **Evidence over narrative.**

> **A smaller proven claim is better than a large unproven system.**

> **Do not optimize for “looks impressive”. Optimize for falsifiability.**

> **Do not let the agent define its own success condition.**

> **The benchmark must be capable of proving AEDL wrong.**

> **If AEDL provides no measurable advantage, kill it.**

当前我们不是要证明：

> AEDL 一定有价值。

而是通过 RepairBench 回答：

> **AEDL 到底有没有价值。**

这是接下来整个项目最重要的方向。
