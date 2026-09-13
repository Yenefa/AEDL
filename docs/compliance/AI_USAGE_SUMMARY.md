# AI Usage Summary — 工作单元聚合视图

<!-- 本文件是人工维护的聚合层，不是生成物；真源仍是 docs/compliance/ai-usage/<ID>.md -->

> ⚠️ **本文件是 curated / non-authoritative summary —— 人工维护的聚合视图，不是审计真源，也不替代任何 provenance。**
> 完整审计真源是 **逐条记录 [`docs/compliance/ai-usage/<ID>.md`](ai-usage/)** 与 **脚本生成的索引 [`AI_USAGE_LOG.md`](AI_USAGE_LOG.md)**。
> 本文件的工作单元**不构成**对原始记录的替代或改写：条目内容、审核状态、commit / PR 关联一律以上述真源为准；
> 两者出现冲突时以真源为准，并修正本文件（本文件不是审计证据）。
>
> 三层结构：**本文件（work units，默认浏览入口）** → [`AI_USAGE_LOG.md`](AI_USAGE_LOG.md)（逐条索引，脚本生成，禁手改） → `docs/compliance/ai-usage/<ID>.md`（逐条真源）。
>
> - 覆盖核验：本文件引用 94 条记录（92 条历史 + WU-39 单元 2 条：`AI-20260910-LIO-4CADC9CD6CC1E745477A23F629A1AAD5` 与 `AI-20260913-OPENCODE-B411981B20EBDA38FBC7F2E6B2AD30D4`），与 `AI_USAGE_LOG.md` 当前 94 条**双向一致**（无遗漏、无重复、无虚构 ID）。
> - 本文件只做聚合与引用，**不改写任何条目正文**；条目正文的修订请直接改 `ai-usage/<ID>.md` 并重建索引。
> - **`Human owner` 只在该工作单元的记录中明确出现时才具名**；未具名一律写 `TO_VERIFY`，不默认归属给任何人。
> - `Human final decision`：`yes` = 有批准 / merge / 裁决记录；`pending` = 条目仍为 `PENDING_HUMAN_REVIEW` 且无 merge 记录；`TO_VERIFY` = 记录未具名。
> - 身份映射：记录中的「大统领」「项目负责人」按 [`docs/ID_MAP.md`](../ID_MAP.md) 映射为 `Yenefa`；2026-08-29 及之前未登记姓名的记录**保持原样**。
> - 归因规则见 [`ATTRIBUTION_POLICY.md`](ATTRIBUTION_POLICY.md)；人类职责总览见 [`docs/HUMAN_OWNERSHIP.md`](../HUMAN_OWNERSHIP.md)。

## 一览

| Unit | 时间 | 工作单元 | AI role | Human owner | Human final decision | 记录数 |
| --- | --- | --- | --- | --- | --- | --- |
| WU-01 | 2026-08-29 | 合规规范项目化与仓库建立 | ADVISE / DOCUMENT / DEBUG | 项目负责人（2026-08-29 记录未登记姓名；按裁决不回填） | yes — 各条目状态 HUMAN_REVIEWED / ACCEPTED（项目负责人确认审核并授权本地提交） | 5 |
| WU-02 | 2026-08-30 | M2 原理图语义缺陷根因分析与修复 | DEBUG / ADVISE / GENERATE_CODE / RESEARCH | 项目负责人（记录未登记姓名） | yes — ADR-004「项目负责人批准 B′」；ADR-005「CONDITIONAL APPROVE → 整改后采纳」 | 2 |
| WU-03 | 2026-08-31 | 开源吸收 Phase 1–3（CircuitBot / KiCadAI / KiCad MCP intake） | RESEARCH / DOCUMENT | Yenefa（记录作「大统领」） | pending — 条目 PENDING_HUMAN_REVIEW；未提交、未建 PR | 2 |
| WU-04 | 2026-08-31 | Requirements Contract 实装 + 多 AI 协作基础设施 | GENERATE_CODE / GENERATE_TEST / DOCUMENT | Yenefa（记录作「项目负责人」） | pending — 候选 ADR-006 待人工审核；条目 PENDING_HUMAN_REVIEW | 1 |
| WU-05 | 2026-08-31 | 需求澄清工作台前端 + requirements runtime server | GENERATE_CODE / GENERATE_TEST / DOCUMENT | 项目负责人（记录作「项目负责人」；姓名未登记） | pending — 条目 PENDING_HUMAN_REVIEW；未提交 | 3 |
| WU-06 | 2026-08-31 | C 方案 —— intent 语义哈希绑定 | GENERATE_CODE / GENERATE_TEST | Yenefa（记录作「大统领」） | pending — 条目 PENDING_HUMAN_REVIEW | 1 |
| WU-07 | 2026-08-31 | M2 目检渲染证据门禁 + D1 极性修复 | GENERATE_CODE / DEBUG / GENERATE_TEST | Yenefa（记录作「大统领」） | pending — 条目 PENDING_HUMAN_REVIEW | 1 |
| WU-08 | 2026-08-31 | 数据手册真值层 + 证据冻结 | GENERATE_CODE / DOCUMENT / RESEARCH | TO_VERIFY（条目无「团队自主部分」；仅记「人工裁决落地」未具名） | TO_VERIFY — 记录未具名 | 3 |
| WU-09 | 2026-08-31 | 信息架构治理（TASK-INFO：HANDOFF 状态卡 + ID_MAP + RAG 决策） | DOCUMENT | TO_VERIFY（条目仅在「已知限制」中提及「待大统领」事项） | pending — 条目 PENDING_HUMAN_REVIEW | 1 |
| WU-10 | 2026-08-31 | 开源 intake Phase 4（NeuroBoard）+ 遗留定案 | RESEARCH / DOCUMENT | TO_VERIFY（条目只记「P8 研究路；属主认领」） | pending — 条目 PENDING_HUMAN_REVIEW | 1 |
| WU-11 | 2026-08-31 | BoardReview 特征化 / RecordedProvider / P12-C + P8-P9 验收与门禁基线 | GENERATE_CODE / GENERATE_TEST / DEBUG / DOCUMENT | Yenefa（记录作「大统领」） | pending — 条目 PENDING_HUMAN_REVIEW | 9 |
| WU-12 | 2026-08-31 | License 拍板落地（Apache-2.0 + 归因声明） | DOCUMENT | Yenefa（记录作「大统领」） | yes — 大统领 2026-08-31 两项拍板；条目本身仍 PENDING_HUMAN_REVIEW | 1 |
| WU-13 | 2026-08-31 / 09-01 | U3 路线 B 选型提案与候选资料冻结 | RESEARCH / ADVISE / DOCUMENT | Yenefa（记录作「大统领」） | pending — 等选型批准（AI-20260831-026 明记） | 4 |
| WU-14 | 2026-08-31 | spike / spike_stage2 独立仓库打包 | GENERATE_CODE / DOCUMENT | Yenefa（记录作「大统领」） | yes（方案① 由大统领拍板）— 仓库名与可见性另待裁决；条目 PENDING_HUMAN_REVIEW | 1 |
| WU-15 | 2026-09-01 | EDD-001 Sandbox 定义冻结与 H/M/L 三 Agent 实现 | GENERATE_CODE / GENERATE_TEST / DOCUMENT / ADVISE | Yenefa | yes — ADR-008 项目负责人批准；条目记录人工审核 CHANGES_REQUIRED 后复审修复 | 2 |
| WU-16 | 2026-09-01 | Wave 4 发卡 + 两人协作治理基线 + 双仓治理 | DOCUMENT / ADVISE | Yenefa（记录作「大统领」） | yes — PR #6 / #13 由 Yenefa merge | 3 |
| WU-17 | 2026-09-01 | 身份映射 + Issue 模板扩展 + 权限模型 OWNED/SHARED/FOREIGN | DOCUMENT | Yenefa（记录作「项目负责人」） | yes — PR #7 / #17 / #18 由 Yenefa merge | 3 |
| WU-18 | 2026-09-01 | Control Plane 最小切片 + 碰撞两刀 + Authority 三级模型 + GH-20 双平台 CI | GENERATE_CODE / GENERATE_TEST / DOCUMENT | Yenefa | yes — PR #21 由 Yenefa merge | 5 |
| WU-19 | 2026-09-01 | Run 001 Review 整改与晋升 | DEBUG / GENERATE_CODE / GENERATE_TEST / DOCUMENT | Yenefa | yes — AI-20260901-019 状态 HUMAN_REVIEWED（Yenefa merge PR #21） | 4 |
| WU-20 | 2026-09-01 | Review Bundle 机制落地（生成器 + bundle_check） | GENERATE_CODE / GENERATE_TEST / DOCUMENT | Yenefa | yes — PR #24 由 Yenefa merge | 3 |
| WU-21 | 2026-09-02 | Run 002 —— dev_gate secret_scan 修复与 autocrlf 环境要求 | DEBUG / DOCUMENT | Yenefa | yes — AI-20260902-001 状态 HUMAN_REVIEWED（Yenefa merge PR #22） | 3 |
| WU-22 | 2026-09-02 | EDD-001 组件真源对齐 + W4A 证据 provenance 冻结 | DEBUG / DOCUMENT | Yenefa（Owner）；Percy（SHARED 路径 review） | yes — PR #25 / #27 由 Yenefa merge | 2 |
| WU-23 | 2026-09-02 | kicad-happy 六步 intake + AGENT_ONBOARDING | RESEARCH / DOCUMENT | Percy（Issue #3 owner）；Yenefa（审查意见） | yes — PR #14 由 Yenefa merge；PR #30 由 Percy merge | 2 |
| WU-24 | 2026-09-03 | 渲染图新鲜度门禁（AEDL-R1）+ CPL 旋转审计（AEDL-CPL） | DEBUG / DOCUMENT | Yenefa（envelope allow_dirty 由 Yenefa 预授权） | TO_VERIFY — 条目记「人工批准派发；最终采纳由人工定」，未具名 | 2 |
| WU-25 | 2026-09-06 | W1 竞赛任务包入库与双人任务卡分发 | DOCUMENT | Yenefa（Y1–Y5）与 Percy（P1–P6） | yes — PR #35 由 Yenefa merge | 1 |
| WU-26 | 2026-09-06 | W1 交付批次（P1–P6 + Y4 实验方案 v1.0/v1.1） | GENERATE_CODE / GENERATE_TEST / DEBUG / RESEARCH / DOCUMENT | Percy（P1–P6 交付）；Yenefa（Y4 方案与指令） | yes — PR #33/#36/#38/#39/#40/#41/#43 由 Yenefa merge；PR #42 由 Percy merge | 8 |
| WU-27 | 2026-09-07 | W1 工程执行计划 + PR-1 裁决/实现合同 + CI 时间炸弹修复 | DOCUMENT / ADVISE / DEBUG | Yenefa | yes — PR #44/#45/#46/#47 由 Yenefa merge | 5 |
| WU-28 | 2026-09-08 | PR-1 C1/C2 落地 + E5 用户试用协议 v1.1 更正 | GENERATE_CODE / GENERATE_TEST / REFACTOR / DEBUG / DOCUMENT | Yenefa | yes — PR #48/#50 由 Yenefa merge | 4 |
| WU-29 | 2026-09-08 / 09-09 | GH-49 AI Usage 台账拆分治理与复审整改 | REFACTOR / DOCUMENT / DEBUG / GENERATE_CODE / GENERATE_TEST | Yenefa（授权）；Percy（CHANGES_REQUESTED review） | yes — PR #49 由 Yenefa merge | 4 |
| WU-30 | 2026-09-04 / 09-09 | Sandbox V3 设计冻结与复审整改 | DOCUMENT / ADVISE | TO_VERIFY（AI-20260904-001 明记「本会话未获得任何裁决授权，全部四项裁决点原样转交」） | yes — PR #34 由 Yenefa merge | 2 |
| WU-31 | 2026-09-09 | 贡献归因信息架构重构（Issue #54） | DOCUMENT / ADVISE | Yenefa（2026-09-09 会话批准本方案并给出裁决） | pending — 条目 PENDING_HUMAN_REVIEW；PR 待人工审核 | 1 |
| WU-32 | 2026-09-09 | W1 范围边界入库（#37 残值提取 + 角色纪律重写） | DOCUMENT / REFACTOR | Percy（提取范围与 #37 关闭裁定由其人工决定） | yes — PR #53 由 Yenefa merge（合并时 REQUEST_CHANGES 的整改项尚未落地，见明细） | 1 |
| WU-33 | 2026-09-10 | 修复 master 红灯 + #53 遗留整改（M1-2 / M1-5） | DEBUG / DOCUMENT | Percy（「先修 master」优先级由其决定） | pending — 条目 PENDING_HUMAN_REVIEW | 1 |
| WU-36 | 2026-09-11 | GH-56 r19/r20 修正版审计与提交 + PR #60 复核取证 | RESEARCH / REVIEW / DOCUMENT | Yenefa（授权提交 GH-56 变更集；PR #60 复核结论由其判定） | pending — 条目 PENDING_HUMAN_REVIEW；PR #61 待人工评审 | 1 |
| WU-39 | 2026-09-13 | GH-56 PR #60 A2-L D 基线（LIO 初版 → A-2′ 端口）与 master 合并后台账重建 | GENERATE_CODE / GENERATE_TEST / DEBUG / DOCUMENT / REVIEW | Yenefa（D1=C / D2=A / A-2′ 路线、WU-39 与 push 授权由其给出） | pending — 条目 PENDING_HUMAN_REVIEW；PR #60 待人工复核 v0.6 | 2 |

## 明细

### WU-01 · 2026-08-29 — 合规规范项目化与仓库建立

- **Records (5)**：`AI-20260829-001`、`AI-20260829-002`、`AI-20260829-003`、`AI-20260829-004`、`AI-20260829-005`
- **AI role**：ADVISE / DOCUMENT / DEBUG
- **Human owner**：项目负责人（2026-08-29 记录未登记姓名；按裁决不回填）
- **Human final decision**：yes — 各条目状态 HUMAN_REVIEWED / ACCEPTED（项目负责人确认审核并授权本地提交）
- **证据**：各条目「团队自主部分」：项目负责人提供规范原文与 v1.4 最终版、要求建立 AEDL repo、指出 AI 披露不够醒目。

### WU-02 · 2026-08-30 — M2 原理图语义缺陷根因分析与修复

- **Records (2)**：`AI-20260830-001`、`AI-20260830-002`
- **AI role**：DEBUG / ADVISE / GENERATE_CODE / RESEARCH
- **Human owner**：项目负责人（记录未登记姓名）
- **Human final decision**：yes — ADR-004「项目负责人批准 B′」；ADR-005「CONDITIONAL APPROVE → 整改后采纳」
- **证据**：AI-20260830-001/-002「团队自主部分」；ADR-004、ADR-005 状态行与「团队自主判断」。

### WU-03 · 2026-08-31 — 开源吸收 Phase 1–3（CircuitBot / KiCadAI / KiCad MCP intake）

- **Records (2)**：`AI-20260831-001`、`AI-20260831-004`
- **AI role**：RESEARCH / DOCUMENT
- **Human owner**：Yenefa（记录作「大统领」）
- **Human final decision**：pending — 条目 PENDING_HUMAN_REVIEW；未提交、未建 PR
- **证据**：AI-20260831-004「大统领指令领取 TASK-P3、指定参照 circuitbot.md 证据纪律」；001「项目负责人提供《开源项目吸收与再设计策略》并指令接手」。

### WU-04 · 2026-08-31 — Requirements Contract 实装 + 多 AI 协作基础设施

- **Records (1)**：`AI-20260831-002`
- **AI role**：GENERATE_CODE / GENERATE_TEST / DOCUMENT
- **Human owner**：Yenefa（记录作「项目负责人」）
- **Human final decision**：pending — 候选 ADR-006 待人工审核；条目 PENDING_HUMAN_REVIEW
- **证据**：AI-20260831-002「团队自主部分」：项目负责人拍板全部四个设计决策点（A/对齐/关键字/立即实装）并决策启用多 AI 并行协作。

### WU-05 · 2026-08-31 — 需求澄清工作台前端 + requirements runtime server

- **Records (3)**：`AI-20260831-003`、`AI-20260831-005`、`AI-20260831-014`
- **AI role**：GENERATE_CODE / GENERATE_TEST / DOCUMENT
- **Human owner**：项目负责人（记录作「项目负责人」；姓名未登记）
- **Human final decision**：pending — 条目 PENDING_HUMAN_REVIEW；未提交
- **证据**：AI-20260831-003「项目负责人制定多 AI 并行协作协议与领地划分（TASK-P2 领地 = web/）」与两条硬约束。

### WU-06 · 2026-08-31 — C 方案 —— intent 语义哈希绑定

- **Records (1)**：`AI-20260831-006`
- **AI role**：GENERATE_CODE / GENERATE_TEST
- **Human owner**：Yenefa（记录作「大统领」）
- **Human final decision**：pending — 条目 PENDING_HUMAN_REVIEW
- **证据**：AI-20260831-006「大统领指派 C 方案、定义语义白名单（components+nets）、给出验收标准与禁止项」。

### WU-07 · 2026-08-31 — M2 目检渲染证据门禁 + D1 极性修复

- **Records (1)**：`AI-20260831-007`
- **AI role**：GENERATE_CODE / DEBUG / GENERATE_TEST
- **Human owner**：Yenefa（记录作「大统领」）
- **Human final decision**：pending — 条目 PENDING_HUMAN_REVIEW
- **证据**：AI-20260831-007「大统领下达 TASK_FIX_D1.md 任务书、证据链与验收标准」。

### WU-08 · 2026-08-31 — 数据手册真值层 + 证据冻结

- **Records (3)**：`AI-20260831-008`、`AI-20260831-009`、`AI-20260831-010`
- **AI role**：GENERATE_CODE / DOCUMENT / RESEARCH
- **Human owner**：TO_VERIFY（条目无「团队自主部分」；仅记「人工裁决落地」未具名）
- **Human final decision**：TO_VERIFY — 记录未具名
- **证据**：AI-20260831-009 任务名「证据冻结 + check_evidence 状态机升级（人工裁决落地）」；008/010 无团队归属字段。

### WU-09 · 2026-08-31 — 信息架构治理（TASK-INFO：HANDOFF 状态卡 + ID_MAP + RAG 决策）

- **Records (1)**：`AI-20260831-011`
- **AI role**：DOCUMENT
- **Human owner**：TO_VERIFY（条目仅在「已知限制」中提及「待大统领」事项）
- **Human final decision**：pending — 条目 PENDING_HUMAN_REVIEW
- **证据**：AI-20260831-011 已知限制段「状态卡中『待大统领』事项随进展会过期」。

### WU-10 · 2026-08-31 — 开源 intake Phase 4（NeuroBoard）+ 遗留定案

- **Records (1)**：`AI-20260831-015`
- **AI role**：RESEARCH / DOCUMENT
- **Human owner**：TO_VERIFY（条目只记「P8 研究路；属主认领」）
- **Human final decision**：pending — 条目 PENDING_HUMAN_REVIEW
- **证据**：AI-20260831-015「会话：Qoder（P8 研究路；属主认领）」，未具名人类 owner。

### WU-11 · 2026-08-31 — BoardReview 特征化 / RecordedProvider / P12-C + P8-P9 验收与门禁基线

- **Records (9)**：`AI-20260831-016`、`AI-20260831-017`、`AI-20260831-018`、`AI-20260831-019`、`AI-20260831-020`、`AI-20260831-021`、`AI-20260831-022`、`AI-20260831-023`、`AI-20260831-024`
- **AI role**：GENERATE_CODE / GENERATE_TEST / DEBUG / DOCUMENT
- **Human owner**：Yenefa（记录作「大统领」）
- **Human final decision**：pending — 条目 PENDING_HUMAN_REVIEW
- **证据**：AI-20260831-016「大统领下达通宵三路并行任务书、定义领地与红线」；019/021/022/023「大统领直接指派」；024「经人工明确授权修复」。

### WU-12 · 2026-08-31 — License 拍板落地（Apache-2.0 + 归因声明）

- **Records (1)**：`AI-20260831-025`
- **AI role**：DOCUMENT
- **Human owner**：Yenefa（记录作「大统领」）
- **Human final decision**：yes — 大统领 2026-08-31 两项拍板；条目本身仍 PENDING_HUMAN_REVIEW
- **证据**：AI-20260831-025「落地大统领 2026-08-31 两项拍板」。

### WU-13 · 2026-08-31 / 09-01 — U3 路线 B 选型提案与候选资料冻结

- **Records (4)**：`AI-20260831-026`、`AI-20260831-027`、`AI-20260831-029`、`AI-20260901-003`
- **AI role**：RESEARCH / ADVISE / DOCUMENT
- **Human owner**：Yenefa（记录作「大统领」）
- **Human final decision**：pending — 等选型批准（AI-20260831-026 明记）
- **证据**：AI-20260831-026「大统领拍板路线 B（换 ≥1A 级 3.3V 方案）后执行选型调研」；该条目状态「PENDING_HUMAN_REVIEW（等选型批准）」。

### WU-14 · 2026-08-31 — spike / spike_stage2 独立仓库打包

- **Records (1)**：`AI-20260831-028`
- **AI role**：GENERATE_CODE / DOCUMENT
- **Human owner**：Yenefa（记录作「大统领」）
- **Human final decision**：yes（方案① 由大统领拍板）— 仓库名与可见性另待裁决；条目 PENDING_HUMAN_REVIEW
- **证据**：AI-20260831-028「按大统领拍板的方案①」+「需大统领定仓库名与可见性」。

### WU-15 · 2026-09-01 — EDD-001 Sandbox 定义冻结与 H/M/L 三 Agent 实现

- **Records (2)**：`AI-20260901-001`、`AI-20260901-002`
- **AI role**：GENERATE_CODE / GENERATE_TEST / DOCUMENT / ADVISE
- **Human owner**：Yenefa
- **Human final decision**：yes — ADR-008 项目负责人批准；条目记录人工审核 CHANGES_REQUIRED 后复审修复
- **证据**：ADR-008 状态行与「团队自主判断」；AI-20260901-002 任务名含「人工审核 CHANGES_REQUIRED 复审修复」。

### WU-16 · 2026-09-01 — Wave 4 发卡 + 两人协作治理基线 + 双仓治理

- **Records (3)**：`AI-20260901-004`、`AI-20260901-005`、`AI-20260901-006`
- **AI role**：DOCUMENT / ADVISE
- **Human owner**：Yenefa（记录作「大统领」）
- **Human final decision**：yes — PR #6 / #13 由 Yenefa merge
- **证据**：AI-20260901-004「大统领指示转入多 agent 协作模式后切分 Wave 4」；`gh pr list`：PR #6、#13 mergedBy=Yenefa。

### WU-17 · 2026-09-01 — 身份映射 + Issue 模板扩展 + 权限模型 OWNED/SHARED/FOREIGN

- **Records (3)**：`AI-20260901-007`、`AI-20260901-008`、`AI-20260901-009`
- **AI role**：DOCUMENT
- **Human owner**：Yenefa（记录作「项目负责人」）
- **Human final decision**：yes — PR #7 / #17 / #18 由 Yenefa merge
- **证据**：AI-20260901-009「项目负责人指定代称与采用决定；AI 只负责落盘与留痕」；`gh pr list`：PR #7/#17/#18 mergedBy=Yenefa。

### WU-18 · 2026-09-01 — Control Plane 最小切片 + 碰撞两刀 + Authority 三级模型 + GH-20 双平台 CI

- **Records (5)**：`AI-20260901-010`、`AI-20260901-011`、`AI-20260901-012`、`AI-20260901-013`、`AI-20260901-018`
- **AI role**：GENERATE_CODE / GENERATE_TEST / DOCUMENT
- **Human owner**：Yenefa
- **Human final decision**：yes — PR #21 由 Yenefa merge
- **证据**：AI-20260901-010「Yenefa 定稿吸收顺序与四句话原则；AI 负责实现」；012/013「设计由 Yenefa 提出」；ADR-011 状态行。

### WU-19 · 2026-09-01 — Run 001 Review 整改与晋升

- **Records (4)**：`AI-20260901-014`、`AI-20260901-015`、`AI-20260901-017`、`AI-20260901-019`
- **AI role**：DEBUG / GENERATE_CODE / GENERATE_TEST / DOCUMENT
- **Human owner**：Yenefa
- **Human final decision**：yes — AI-20260901-019 状态 HUMAN_REVIEWED（Yenefa merge PR #21）
- **证据**：AI-20260901-014/015/017「Review 结论与整改要求由 Yenefa 提出；AI 执行修复」；019 状态 HUMAN_REVIEWED。

### WU-20 · 2026-09-01 — Review Bundle 机制落地（生成器 + bundle_check）

- **Records (3)**：`AI-20260901-016`、`AI-20260901-020`、`AI-20260901-021`
- **AI role**：GENERATE_CODE / GENERATE_TEST / DOCUMENT
- **Human owner**：Yenefa
- **Human final decision**：yes — PR #24 由 Yenefa merge
- **证据**：AI-20260901-016「特色判定与使用要求由 Yenefa 提出」；020/021「需求由 Yenefa 提出」；`gh pr list`：PR #24 mergedBy=Yenefa。

### WU-21 · 2026-09-02 — Run 002 —— dev_gate secret_scan 修复与 autocrlf 环境要求

- **Records (3)**：`AI-20260902-001`、`AI-20260902-002`、`AI-20260902-004`
- **AI role**：DEBUG / DOCUMENT
- **Human owner**：Yenefa
- **Human final decision**：yes — AI-20260902-001 状态 HUMAN_REVIEWED（Yenefa merge PR #22）
- **证据**：AI-20260902-001「Yenefa 执行 merge（promotion）」与状态 HUMAN_REVIEWED；002「merge 由 Yenefa/Percy 执行」。

### WU-22 · 2026-09-02 — EDD-001 组件真源对齐 + W4A 证据 provenance 冻结

- **Records (2)**：`AI-20260902-003`、`AI-20260902-005`
- **AI role**：DEBUG / DOCUMENT
- **Human owner**：Yenefa（Owner）；Percy（SHARED 路径 review）
- **Human final decision**：yes — PR #25 / #27 由 Yenefa merge
- **证据**：AI-20260902-003「Yenefa 会话内 Owner 决策『收 #20』」；005「Owner（Yenefa）2026-09-02 会话内两项裁定」「la4876949-bot（Percy）：SHARED 路径 review」。

### WU-23 · 2026-09-02 — kicad-happy 六步 intake + AGENT_ONBOARDING

- **Records (2)**：`AI-20260902-006`、`AI-20260902-007`
- **AI role**：RESEARCH / DOCUMENT
- **Human owner**：Percy（Issue #3 owner）；Yenefa（审查意见）
- **Human final decision**：yes — PR #14 由 Yenefa merge；PR #30 由 Percy merge
- **证据**：AI-20260902-006「人类授权：项目负责人（经 Percy 代为确认）指派 Issue #3 给 la4876949-bot」「按 Yenefa 对首版 PR #14 的审查意见返工」。

### WU-24 · 2026-09-03 — 渲染图新鲜度门禁（AEDL-R1）+ CPL 旋转审计（AEDL-CPL）

- **Records (2)**：`AI-20260903-001`、`AI-20260903-002`
- **AI role**：DEBUG / DOCUMENT
- **Human owner**：Yenefa（envelope allow_dirty 由 Yenefa 预授权）
- **Human final decision**：TO_VERIFY — 条目记「人工批准派发；最终采纳由人工定」，未具名
- **证据**：AI-20260903-001「allow_dirty 预授权 granted_by=Yenefa」；002「任务卡由 AEW Terminal Agent 生成、人工批准派发；最终采纳由人工定」。

### WU-25 · 2026-09-06 — W1 竞赛任务包入库与双人任务卡分发

- **Records (1)**：`AI-20260906-001`
- **AI role**：DOCUMENT
- **Human owner**：Yenefa（Y1–Y5）与 Percy（P1–P6）
- **Human final decision**：yes — PR #35 由 Yenefa merge
- **证据**：AI-20260906-001「W1_TASKS 领地表（P1–P6 Percy、Y1–Y5 Yenefa、J1 双方）」；`gh pr list`：PR #35 mergedBy=Yenefa。

### WU-26 · 2026-09-06 — W1 交付批次（P1–P6 + Y4 实验方案 v1.0/v1.1）

- **Records (8)**：`AI-20260906-003`、`AI-20260906-004`、`AI-20260906-005`、`AI-20260906-006`、`AI-20260906-007`、`AI-20260906-009`、`AI-20260906-010`、`AI-20260906-011`
- **AI role**：GENERATE_CODE / GENERATE_TEST / DEBUG / RESEARCH / DOCUMENT
- **Human owner**：Percy（P1–P6 交付）；Yenefa（Y4 方案与指令）
- **Human final decision**：yes — PR #33/#36/#38/#39/#40/#41/#43 由 Yenefa merge；PR #42 由 Percy merge
- **证据**：AI-20260906-003「大统领指令『进军』」；005「Percy 现场已有可招募对象」；006「allow_drift 由 Percy 人工授权」；007「操作者为 Percy（la4876949-bot）」；004/010 为 Yenefa 的 Y4 方案入库。

### WU-27 · 2026-09-07 — W1 工程执行计划 + PR-1 裁决/实现合同 + CI 时间炸弹修复

- **Records (5)**：`AI-20260907-001`、`AI-20260907-002`、`AI-20260907-003`、`AI-20260907-004`、`AI-20260907-005`
- **AI role**：DOCUMENT / ADVISE / DEBUG
- **Human owner**：Yenefa
- **Human final decision**：yes — PR #44/#45/#46/#47 由 Yenefa merge
- **证据**：AI-20260907-003「Yenefa 指令：审查并冻结 PR-1 contract」；004「大统领拍板方案 B」；`docs/competition/internal/AEDL_PR1_大统领裁决_20260907.md`。

### WU-28 · 2026-09-08 — PR-1 C1/C2 落地 + E5 用户试用协议 v1.1 更正

- **Records (4)**：`AI-20260908-001`、`AI-20260908-002`、`AI-20260908-003`、`AI-20260908-YEN-002`
- **AI role**：GENERATE_CODE / GENERATE_TEST / REFACTOR / DEBUG / DOCUMENT
- **Human owner**：Yenefa
- **Human final decision**：yes — PR #48/#50 由 Yenefa merge
- **证据**：AI-20260908-001「大统领指令」；003「大统领源码级审查 REQUEST_CHANGES 三项全落地」；YEN-002「Yenefa 2026-09-08 裁定」。

### WU-29 · 2026-09-08 / 09-09 — GH-49 AI Usage 台账拆分治理与复审整改

- **Records (4)**：`AI-20260908-YEN-001`、`AI-20260909-CODEX-6E819BDC6421B00C5B728D09253CBECE`、`AI-20260909-CODEX-752D7A7FCC04DFBF91D2912F3222B054`、`AI-20260909-CODEX-D685F9E9FAC5AF8DCA0869791DE02AE4`
- **AI role**：REFACTOR / DOCUMENT / DEBUG / GENERATE_CODE / GENERATE_TEST
- **Human owner**：Yenefa（授权）；Percy（CHANGES_REQUESTED review）
- **Human final decision**：yes — PR #49 由 Yenefa merge
- **证据**：AI-20260908-YEN-001「Yenefa 授权，台账拆分治理，终结编号地狱」；CODEX 条目「依据：Percy 对 PR #49 的 CHANGES_REQUESTED」；ADR-012。

### WU-30 · 2026-09-04 / 09-09 — Sandbox V3 设计冻结与复审整改

- **Records (2)**：`AI-20260904-001`、`AI-20260909-001`
- **AI role**：DOCUMENT / ADVISE
- **Human owner**：TO_VERIFY（AI-20260904-001 明记「本会话未获得任何裁决授权，全部四项裁决点原样转交」）
- **Human final decision**：yes — PR #34 由 Yenefa merge
- **证据**：AI-20260904-001「团队自主部分：无——本会话未获得任何裁决授权」；`gh pr list`：PR #34 mergedBy=Yenefa。

### WU-31 · 2026-09-09 — 贡献归因信息架构重构（Issue #54）

- **Records (1)**：`AI-20260909-BOT-C250B615B40C709A46C59E31570F5E61`
- **AI role**：DOCUMENT / ADVISE
- **Human owner**：Yenefa（2026-09-09 会话批准本方案并给出裁决）
- **Human final decision**：pending — 条目 PENDING_HUMAN_REVIEW；PR 待人工审核
- **证据**：该条目「团队自主部分」：项目负责人 2026-09-09 会话批准本方案并给出裁决（Issue #54）。

### WU-32 · 2026-09-09 — W1 范围边界入库（#37 残值提取 + 角色纪律重写）

- **Records (1)**：`AI-20260909-PER-001`
- **AI role**：DOCUMENT / REFACTOR
- **Human owner**：Percy（该条目「团队自主部分」：提取范围与关闭裁定由 Percy 人工决定；Agent 未自行判断哪些内容该丢弃）
- **Human final decision**：yes — PR #53 由 Yenefa merge
- **证据**：`AI-20260909-PER-001`「团队自主部分」；PR #53 merge commit `63bc7e3`。
- **待整改（合并时未落地）**：PR #53 的 REQUEST_CHANGES 提出五项，合并时均未整改，其中三项为内容问题——
  M1-2（`SCOPE_BOUNDARY_W1.md` §0 把「六态判定语义」误记为被 A/B 两维记分取代）、
  M1-3（本条 ID 为序号格式，不符 ADR-012 新发规则，按「只读兼容、不追溯改号」保留）、
  M1-5（`W1_CARD_Percy_20260907.md:9` 与 `W1_TASKS_20260907.md:14` 两处旧角色规则未同步）。
  M1-4（台账未闭环）致 master 的 `ai_usage_ledger` 检查失败、CI 于 2026-09-09T14:38Z 转红。

### WU-33 · 2026-09-10 — 修复 master 红灯 + PR #53 遗留整改

- **Records (1)**：`AI-20260910-PER-3A3AA8B393308B4AA361B83FDA17CEBF`
- **AI role**：DEBUG / DOCUMENT
- **Human owner**：Percy（2026-09-10 指令「先修 master」）
- **Human final decision**：pending — 条目 `PENDING_HUMAN_REVIEW`
- **证据**：该条目「起因」节实测数据——`check` 报 index out of sync、`dev_gate` overall fail、master CI 于 2026-09-09T14:38:07Z 转红；「未处理项」节逐条声明 M1-3 按 ADR-012 保留、M2 留待人工裁决。

### WU-36 · 2026-09-11 — GH-56 r19/r20 修正版审计与提交 + PR #60 复核取证

- **Records (1)**：`AI-20260911-OPENCODE-E1C979A5B030BE12E7E3E174226C2BE7`
- **AI role**：RESEARCH / REVIEW / DOCUMENT
- **Human owner**：Yenefa（授权提交 GH-56 变更集；PR #60 复核分析结论归 Owner）
- **Human final decision**：pending — AI 条目 `PENDING_HUMAN_REVIEW`；PR #61 待人工评审；PR #60 已由 Owner 判定 `CHANGES_REQUESTED`
- **证据**：PR #61（commit `e641b5eb`，CI 双绿）；PR #60 review（`CHANGES_REQUESTED`）；r20 归档全链哈希独立复核；真实冻结包 CLI 实测 exit 2 ×2
- **边界**：未接触 Percy private oracle；复核仅使用公开仓库内容与公开冻结包

### WU-39 · 2026-09-13 — GH-56 PR #60 A2-L D 基线（LIO 初版 → A-2′ 端口）与机械收尾

- **Records (2)**：`AI-20260910-LIO-4CADC9CD6CC1E745477A23F629A1AAD5`（v0.3–v0.5 初版）、`AI-20260913-OPENCODE-B411981B20EBDA38FBC7F2E6B2AD30D4`（v0.6 A-2′ 端口 + 机械收尾）
- **AI role**：GENERATE_CODE / GENERATE_TEST / DEBUG / DOCUMENT / REVIEW
- **Human owner**：Yenefa（2026-09-13 会话给出 D1=C、D2=A、A-2′ 路线、WU-39 与 push 授权）
- **Human final decision**：pending — 两条目均 `PENDING_HUMAN_REVIEW`；PR #60 待人工复核 v0.6
- **证据**：五个冻结计分包逐字节等价 5/5（host 侧 `gh56-y4-dry/r23/candidates/a2l-port/PORT-EQUIVALENCE-RECEIPT.json`，不入库）；`unittest tests.test_repair_baseline` OK 35（skipped=3）；`unittest discover -s tests` OK 552（skipped=3）；合并 `origin/master@c286489` 后台账 `check` fail → `build`（94 条）→ `check` OK
- **边界**：未接触 Percy private oracle；引擎只读仓库内公共合同与公共包内观测/源码

---

## 维护规则

1. 新增 AI 记录后：先建 `ai-usage/<ID>.md` → `python -m tools.build_ai_usage_index build` → 再把该 ID 归入本文件的一个工作单元（同 Issue / PR / 同一目标的多轮活动合并为一个 unit）。
2. 本文件的引用集合必须与 `AI_USAGE_LOG.md` 完全一致；出现差异时以台账为准并修正本文件。
3. 不在此处重述条目结论、不添加条目中没有的事实；需要补充事实时改真源条目。
4. `Human owner` 与 `Human final decision` 的证据不足时写 `TO_VERIFY`，禁止默认归属。
