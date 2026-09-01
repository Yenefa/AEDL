# AEDL AGENTS.md — Git 协作 + AIC 合规执行规范

> 面向：Codex / Claude Code / Gemini CLI / Cursor / OpenHands / 其他参与 AEDL 的 AI Agent。  
> 本文件是 **Agent 执行层唯一规范**：Git/GitHub 工作流、AI 使用留痕、第三方资源、ADR、Evidence、安全与 AIC 合规统一在这里。  
> 原则：**开发即留痕，但不要把留痕变成第二个项目。**

---

## 0. 指令优先级

发生冲突时按以下顺序执行：

1. 当前任务中人类的明确指令；
2. 当前 Issue / PR / 任务说明；
3. 仓库既有架构、接口、测试；
4. 本 `AGENTS.md`；
5. Agent 默认行为。

任何不确定信息不得猜测。必要时使用：

```text
UNKNOWN / TO_VERIFY / NOT_RUN / PENDING / BLOCKED
```

---

# 1. 标准开发闭环

所有**实质开发任务**默认遵循：

```text
Issue / Task
↓
确认 Goal / Scope / Acceptance Criteria
↓
Task Branch
↓
检查现有代码与记录
↓
开发 / 调试 / 测试
↓
git status + git diff
↓
真实运行验证
↓
按触发条件更新合规记录
↓
commit + push（仅在获授权时）
↓
PR / Handoff
↓
PENDING_HUMAN_REVIEW
↓
人工 Review 后才能 Merge main
```

目标优先级：

```text
正确性 > 范围控制 > 可验证性 > 可追溯性 > 最小改动
```

禁止为了“顺手优化”扩大任务范围。

---

# 2. 开工前必须确认

从 Issue / PR / Prompt 中尽量确定：

```text
Goal：要解决什么
Scope：允许修改什么
Out of Scope：明确不做什么
Acceptance Criteria：什么算完成
Evidence Needed：YES / NO / TO_VERIFY
AIC Score Target：已知评分项 / NONE / UNKNOWN
```

若缺项但任务仍明确，可保守执行。

若歧义会影响架构、公共接口、Benchmark、开源边界或比赛技术主张，先请求人工确认。

## 2.1 AEDL 硬件发布前项目专属必读

凡任务涉及硬件选型、原理图、PCB、BOM/CPL/Gerber、板级门禁、制造签发或下单，实质修改前还必须完整读取：

- `docs/knowledge/PROJECT_PITFALLS.md`
- `docs/knowledge/IMPROVEMENT_SYSTEM.md`

并执行 `gates/learning_gate.py` 已提升的项目经验控制。历史交付物彼此一致、ERC/DRC 通过、自动板级评审通过，都不能替代独立数据手册合同、当前源文件哈希绑定、具名人工制造签发或回件后的实体 C 级验证。

## 2.2 变更控制（Change Containment）——所有实质任务必做

> 总原则：**Read broadly, write narrowly, verify explicitly, escalate on boundary change.**
> （广泛读取，窄域修改，显式验证，触碰边界即升级。）

开工前完成 **Impact Analysis** 并随任务记录输出：

```text
Impact Analysis

Direct modifications:   // 本次直接修改的文件
Potentially affected:   // 可能受影响的模块/文件
Explicitly not touched: // 明确不碰的范围
Risk: LOW / MEDIUM / HIGH
```

开工前填写 **Change Budget**（可并入 Issue 或任务记录）：

```text
change_budget:
  expected_files: N
  expected_modules: [module-a, module-b]
  cross_module: false              # 是否跨模块
  contract_change: false           # 是否改公共契约/schema
  evidence_semantics_change: false # 是否改变 Evidence 语义
```

**越界规则**：实际改动超出预算（文件数/模块数显著超预期，或上述任一布尔项从 false 变 true）时：

```text
STOP
→ 重做 Impact Analysis
→ 扩 Scope 需人类确认
```

禁止"顺手"继续扩大范围（目标优先级：正确性 > 范围控制 > 可验证性 > 可追溯性 > 最小改动）。

---

# 3. Git / GitHub 规则

## 3.1 开工检查

实质修改前至少检查：

```bash
git status
git branch --show-current
```

需要时查看：

```bash
git diff
git log --oneline -n 20
git fetch
```

不得为“清理环境”擅自丢弃未知的人类修改。

## 3.2 Branch

`main` 是稳定集成分支。

除非人类明确要求，或执行环境已托管分支，否则实质功能不得直接在 `main` 开发。

推荐：

```text
feat/<topic>
fix/<topic>
test/<topic>
docs/<topic>
refactor/<topic>
experiment/<topic>
chore/<topic>
```

一个 Branch 尽量只承载一个连贯任务；禁止把无关重构、依赖升级、格式化等混入。

## 3.3 Diff

任务结束前必须检查：

```bash
git status
git diff
```

已 staged 时按需检查：

```bash
git diff --staged
```

确认：

- 改动与 Scope 一致；
- 没有无关文件；
- 没有秘密凭据；
- 没有意外删除 Evidence / 合规记录；
- 没有来源不明的大段代码。

## 3.4 Commit

仅在环境或人类允许 commit 时执行。

推荐格式：

```text
<type>(<module>): <summary> [AI-LOG-ID]
```

例如：

```text
feat(simulator): add serial verifier [AI-20260829-001]
fix(build): repair classifier [AI-20260831-003]
```

常用 type：

```text
feat fix test refactor docs chore perf build ci
```

无实质 AI 参与时可不带 AI ID。

禁止 `update`、`123`、`final2` 等无意义提交信息。

不得编造 commit hash。

## 3.5 Push

仅在获授权且凭据可用时：

- push 当前任务分支；
- 不直接 push/force-push `main`；
- 不擅自重写共享历史；
- 不把已知 secrets 推上远端。

Push 失败必须如实报告。

## 3.6 PR

PR 是正式交接点。创建或起草 PR 时至少包含：

```text
What
Why
Scope
Issue / Task
Tests actually run
Not run / limitations
AI Usage ID
Third-party IDs
ADR IDs
Evidence IDs
Known risks / follow-up
Human review: PENDING_HUMAN_REVIEW
```

Agent 可以起草 PR、分析 PR、提出 Review 建议，但不得冒充人工批准。

## 3.7 禁止的 Git 操作

未经本次任务的人类明确授权，不得：

- merge 到 `main`；
- Approve PR；
- force-push `main`；
- 无必要 rebase/重写共享历史；
- 删除含未合并成果的分支；
- 对未知工作执行破坏性 `reset --hard` / `clean`；
- 设置 `HUMAN_REVIEWED` / `ACCEPTED`。

已共享提交需要撤销时，优先 `revert` 而不是改写历史。

---

# 4. AI 使用留痕

当 AI 对以下内容产生**实质贡献**时，更新：

```text
docs/compliance/AI_USAGE_LOG.md
```

触发项：

- 代码生成/修改；
- 重构；
- Bug 诊断/修复；
- 测试生成；
- Benchmark；
- 架构/接口设计；
- Agent Workflow；
- 数据处理；
- 实质文档/Prompt/Skill；
- 第三方资源选型与集成；
- 比赛报告、图片、视频等实质内容。

粒度：**一个可审计工作单元，而不是一个 Prompt。**

同一 Issue / PR、同一目标的多轮 Agent 交互可合并为一条记录。

ID：

```text
AI-YYYYMMDD-NNN
```

参与标签：

```text
ADVISE
GENERATE_CODE
REFACTOR
DEBUG
GENERATE_TEST
RESEARCH
DOCUMENT
BENCHMARK
MEDIA
```

禁止写“AI 完成 70%”等不可审计百分比。

AI 完成后的审核状态只能是：

```text
PENDING_HUMAN_REVIEW
```

---

# 5. 第三方 / 开源资源

新增或实质改变外部资源使用时，更新：

```text
docs/compliance/THIRD_PARTY_RESOURCES.md
```

包括：

```text
库 / 框架 / SDK
模型 / API / SaaS
数据集
模拟器
外部仓库 / 示例代码
Prompt / Skill
Datasheet
Benchmark 数据源
图片 / 图标 / 字体 / 音视频
其他外部服务或组件
```

至少记录：

```text
名称
类型
版本 / TO_VERIFY
来源
License / 授权 / TO_VERIFY
融合角色：CORE / SUPPORT / DEV_ONLY
用途与使用方式
是否修改上游源码
是否再分发
关键义务 / TO_VERIFY
AEDL 自研边界
合规状态：OK / TO_VERIFY / BLOCKED
关联模块
```

融合角色定义：

```text
CORE     = 直接参与 AEDL 核心功能或“AI + 开源融合”主张
SUPPORT  = 运行、构建、验证所需，但不是核心创新
DEV_ONLY = 普通开发工具，不得包装成“AI + 开源融合”创新
```

规则：

- 不猜 License；
- “GitHub Public” ≠ 可随意复制使用；
- 不把外部代码伪装成 AEDL 自研；
- 模型/API/Wokwi/PlatformIO/ESP-IDF/Python 包等同样属于应检查的外部资源。

---

# 6. ADR：关键工程决策

仅当决策实质影响以下内容时更新：

```text
docs/compliance/DECISIONS.md
```

触发：

- 系统架构；
- Agent Workflow；
- Verification Protocol；
- Simulator Adapter；
- Benchmark / Ground Truth；
- 关键接口/Schema；
- 安全边界；
- 开源/License 边界；
- 战略性模型/模拟器选择；
- 比赛核心技术定位。

普通实现细节不要创建 ADR。

ID：

```text
ADR-NNN
```

内容尽量包含：

```text
问题
候选方案
决策
理由
AI 参与
团队自主判断
影响
Evidence / Reference
复查条件
```

---

# 7. Evidence / Benchmark

当实际结果将用于支撑技术主张时更新：

```text
docs/evidence/EVIDENCE_INDEX.md
```

触发：

- 单元/集成/系统测试；
- 多次场景运行；
- Benchmark；
- Fault Injection；
- 性能/稳定性指标；
- Baseline 对比；
- 真实用户反馈；
- 用作证明的日志、JSON、CSV、VCD、截图、报告、视频片段。

ID：

```text
EVID-YYYYMMDD-NNN
```

应记录实际可确认的：

```text
对应主张
模块
AI Usage / ADR
环境
命令 / 方法
Runs
真实结果
指标
原始证据路径
可复现状态
已知限制
人工核验状态
```

没有实际运行：

```text
NOT_RUN
```

不知道：

```text
UNKNOWN
```

绝不生成虚假 PASS、Benchmark 或“人工已验证”。

---

# 8. AIC 赛事合规与评分资产

本节是 **Agent 必须执行的 AIC 赛事层规则**。普通 Coding Task 不需要反复读取赛事材料；只有触发相应条件时，才更新对应赛事资产。

## 8.1 六个评分项与证据映射

AIC「AI+开源」开发记录必须服务于以下评分方向：

| 评分项 | 主要证据资产 | Agent 触发条件 |
|---|---|---|
| 问题与场景价值 | `docs/competition/PROBLEM_EVIDENCE.md` | 任务产生真实用户/场景/痛点/需求证据 |
| 创新性与方案设计 | `docs/compliance/DECISIONS.md` + Baseline | 关键机制、架构、方案取舍、对照设计发生变化 |
| AI 与开源融合 | `docs/competition/FUSION_MAP.md` + `THIRD_PARTY_RESOURCES.md` | 核心 AI/开源资源/自研模块的关系发生变化 |
| 实现完成度与可验证效果 | `docs/evidence/EVIDENCE_INDEX.md` | 产生测试、Benchmark、故障注入、性能或稳定性结果 |
| 开放成果与复用价值 | `docs/competition/OPEN_OUTPUTS.md` | 新增/改变准备公开复用的协议、接口、工具链、测试、示例等 |
| 材料规范与表达 | `docs/competition/SUBMISSION_CHECKLIST.md` | 进入报告、PPT、视频、正式提交或 Release 阶段 |

Issue / PR 若与比赛核心能力相关，应标记：

```text
AIC Score Target: <评分项> / NONE / UNKNOWN
```

纯内部维护允许 `NONE`。不得为了“看起来有分”强行关联评分项。

## 8.2 AI + 开源融合不是工具清单

以下本身 **不等于创新，也不得单独作为融合成果宣传**：

```text
用了 Git/GitHub
用了 Python
调用了通用 LLM/API
用了很多开源库
用了普通 IDE / CLI / 开发环境
做了一个漂亮 UI
```

比赛核心主张应落在 AEDL 自身的：

```text
Mechanism / Architecture / Workflow / Protocol / Integration
Verification / Benchmark / Reusable Output
```

当核心融合关系发生变化时，更新：

```text
docs/competition/FUSION_MAP.md
```

至少说明：

```text
核心能力是什么
AI 在其中做什么、为什么必要
哪些开源资源直接参与核心功能
AEDL 自研模块是什么
输入 / 输出 / 接口如何连接
若移除 AI 或某开源资源会损失什么能力
如何测试或 Evidence 验证该融合
```

第三方资源仍必须同时在 `THIRD_PARTY_RESOURCES.md` 登记；`FUSION_MAP.md` 不是许可证台账。

## 8.3 开放成果不是“仓库 Public”

若任务新增或实质改变准备对外复用的成果，更新：

```text
docs/competition/OPEN_OUTPUTS.md
```

优先考虑真正可复用的：

```text
核心代码 / Adapter SDK / Protocol
Verification / Benchmark / 测试用例
Agent Workflow / Skill / 示例项目 / 文档
```

至少记录：

```text
准备开放什么
团队自主创作边界
许可证 / TO_VERIFY
哪些第三方内容不随项目再分发
最小安装与运行方式
外部用户如何复现最小 Demo
已知限制
维护状态 / 计划
```

不得把“GitHub 仓库是 public”本身当成开放成果。

## 8.4 自研 / AI / 第三方 / 外部贡献必须分开

所有比赛相关开发与材料必须区分：

```text
AEDL 正式团队自主开发
AI 辅助/生成
第三方/开源资源
外部非正式队员贡献
```

不得混写成“全部团队自研”。

非正式参赛成员完成的工作不得冒充正式团队自主成果；如实际使用，应如实记录来源、授权和使用边界。

## 8.5 赛事战略资料按需读取

普通 Coding Task：

```text
只执行本 AGENTS.md
```

当任务涉及 **评分、创新性、比赛定位、融合主张、开放成果、正式提交** 时，再读取：

```text
docs/competition/AIC_STANDARD.md
docs/competition/SCORING_MAP.md
```

并根据任务读取：

```text
FUSION_MAP.md
OPEN_OUTPUTS.md
SUBMISSION_CHECKLIST.md
```

避免把全部赛事说明永久塞进普通 Coding Context。

## 8.6 正式材料与 FAIRNESS_CHECK

正式技术报告、演示视频、答辩 PPT、评审截图和其他提交材料，在输出前执行 `FAIRNESS_CHECK`：

- 学校名称；
- 学校 LOGO；
- 指导教师信息；
- 不必要账号/个人信息；
- API Key / Token / secrets；
- 无权公开的第三方内容；
- 无 Evidence 支撑的技术/创新主张；
- 成果链接不可访问或版本不一致。

## 8.7 比赛版本冻结 / Release Trigger

只有在人类明确进入 **阶段提交、初赛提交、决赛提交或正式 Release** 时触发；普通开发任务不要创建比赛 tag。

建议版本：

```text
aic-2026-initial
aic-2026-final
```

冻结时记录并核对：

```text
commit hash
Git tag / GitHub Release
技术报告版本
演示视频版本
第三方资源清单版本
Evidence 索引版本
开放成果版本
成果链接有效性
```

目标：报告、视频、Benchmark、截图与代码全部能够回到同一个确定版本。

## 8.8 技术主张真实性

所有性能、稳定性、效果、创新性和复用价值主张必须与真实 Evidence / ADR / Repository History 对齐。

不得：

```text
没有对照却声称显著优于 Baseline
没有运行却填写测试结果
将普通工具使用包装成创新机制
将第三方能力写成 AEDL 自研能力
无证据声称“首创 / 首次 / 行业空白 / 行业领先”
```


# 9. Secrets

任何仓库文件、日志、Evidence、PR、示例、截图、比赛材料中禁止写入：

```text
API Key
Token
密码
私钥
Cookie
私人账户凭据
不必要的敏感个人数据
```

只使用占位符：

```text
OPENAI_API_KEY=<REDACTED>
WOKWI_CLI_TOKEN=<REDACTED>
```

若发现泄露：

1. 停止继续传播；
2. 不在回复中复述 secret；
3. 报告受影响路径/提交；
4. 要求人类撤销/轮换凭据；
5. 不擅自改写历史“掩盖”。

---

# 10. 真实性红线

禁止：

- 声称运行过未运行的命令；
- 声称未执行测试已 PASS；
- 编造 Benchmark、日志、截图、用户反馈；
- 猜模型版本、依赖版本、License、服务条款；
- 编造人工审核；
- 隐瞒已知限制；
- 无证据声称“首创 / 首次 / 行业空白 / 行业领先”；
- 把第三方或外部贡献伪装成团队自研。

不确定就明确写：

```text
UNKNOWN / TO_VERIFY / NOT_RUN / PENDING
```

---

# 11. 最小留痕原则

普通实质 AI 任务，额外记录目标成本：

> **2–5 分钟**

不要每个任务把四张台账全部填一遍。

按触发器更新即可：

| 发生的事 | 更新 |
|---|---|
| AI 实质参与 | `AI_USAGE_LOG.md` |
| 新增/改变第三方资源 | `THIRD_PARTY_RESOURCES.md` |
| 重大工程决策 | `DECISIONS.md` |
| 实际产生比赛技术证据 | `EVIDENCE_INDEX.md` |
| 核心 AI+开源融合关系改变 | `FUSION_MAP.md` |
| 准备开放的可复用成果改变 | `OPEN_OUTPUTS.md` |
| 进入正式提交/Release 阶段 | `SUBMISSION_CHECKLIST.md` + 版本冻结 |

避免重复复制描述，优先交叉引用：

```text
Issue #32
PR #41
AI-...
RES-...
ADR-...
EVID-...
```

普通解释、typo、无实质影响的格式调整通常不新增审计记录。

---

# 12. 完成门禁

实质任务结束前必须确认：

### Engineering
- [ ] Goal / Acceptance Criteria 已完成或缺口明确
- [ ] Scope 未无故扩大
- [ ] 已查看 `git status`
- [ ] 已查看 `git diff`
- [ ] 无无关修改

### Verification
- [ ] 实际运行的测试和结果如实记录
- [ ] 未运行的重要测试标记 `NOT_RUN`
- [ ] 无虚假 Evidence / Benchmark
- [ ] 硬件自动静态检查未被表述为人工制造签发或实体 C 级验证
- [ ] BOM 库存已按精确料号即时复核；零库存/未知库存失败关闭且未自动换料

### Compliance
- [ ] AI Usage：按需更新
- [ ] Third-party：按需更新
- [ ] ADR：按需更新
- [ ] Evidence：按需更新
- [ ] 无 secrets
- [ ] 无无证据技术/创新主张
- [ ] 自研 / AI / 第三方边界真实
- [ ] 若触发评分/融合任务，Score Target 与 `FUSION_MAP` 等资产已按需更新
- [ ] 若触发开放成果任务，`OPEN_OUTPUTS.md` 已按需更新
- [ ] 若处于正式提交阶段，已执行 `SUBMISSION_CHECKLIST` / FAIRNESS_CHECK / 版本冻结

### Git / Review
- [ ] 分支使用符合规则
- [ ] Commit / Push 状态如实报告
- [ ] PR/Handoff 足够人工审核
- [ ] 状态保持 `PENDING_HUMAN_REVIEW`

---

# 13. Agent 最终回复格式

完成实质仓库任务后使用：

```text
Changed:
- ...

Git:
- Branch: ...
- Commit: <hash> / not committed
- Push: pushed / not pushed / unavailable
- PR: <ref> / not created

Tests actually run:
- <command> → <real result>

Not run / limitations:
- ... / none

Compliance records:
- AI Usage: AI-... / none
- Third-party: RES-... / none
- ADR: ADR-... / none
- Evidence: EVID-... / none
- Fusion Map: updated / not triggered
- Open Outputs: updated / not triggered
- Submission Check: done / not triggered

AIC score target:
- <评分项> / NONE / UNKNOWN

Human review:
- PENDING_HUMAN_REVIEW
```

---

# 14. 总规则

> **在受控 Git 分支上做最小必要修改，检查真实 diff，运行真实测试；仅按触发条件更新 AIC/AI/第三方/Evidence 记录；获授权后 commit/push/PR；最终接受与 merge 永远留给人类。**
