# Human Ownership

> 本页把仓库中**已经记录在案**的人类职责集中展示，供新会话、评审与外部读者快速定位"谁做决策、谁验收、谁负责"。
> 本页只做**聚合与导航**：不新增事实、不改写历史、不替代真源。每条主张都给出可核验的仓库证据。
>
> - 决策真源：[`docs/compliance/DECISIONS.md`](compliance/DECISIONS.md)（ADR）、[`docs/COLLABORATION.md`](COLLABORATION.md)、[`AGENTS.md`](../AGENTS.md)
> - 归因规则：[`docs/compliance/ATTRIBUTION_POLICY.md`](compliance/ATTRIBUTION_POLICY.md)
> - AI 使用记录：[AI Usage Summary](compliance/AI_USAGE_SUMMARY.md) → [AI Usage Log](compliance/AI_USAGE_LOG.md) → `docs/compliance/ai-usage/<ID>.md`
> - 人类贡献台账：[`docs/compliance/TEAM_CONTRIBUTIONS.md`](compliance/TEAM_CONTRIBUTIONS.md)（历史 `UNKNOWN` 不回填）
>
> 身份映射：`Yenefa` = 项目负责人（记录中亦称"大统领"）；`la4876949-bot` = Percy = 正式团队成员（AEDL_TEAM）。
> 依据：[`docs/ID_MAP.md`](ID_MAP.md)「真人身份与代称」、[`docs/COLLABORATION.md`](COLLABORATION.md) 顶部公告（`sca331613-commits` → `Yenefa`）。

---

## 1. Project ownership

| 职责 | Owner | 仓库证据 |
| --- | --- | --- |
| 产品方向（北极星：在受控工程流程下正确交付实体板卡） | Yenefa | Issue #15 / PR #16；ADR-008「团队自主判断」 |
| 比赛定位与战略裁决（akcli 身份、PR-1 边界、预先冻结的降级条款） | Yenefa（记录作"大统领"） | `docs/competition/internal/AEDL_PR1_大统领裁决_20260907.md`；AI-20260907-002 |
| 范围边界（支持/不支持、判定语义、零覆盖不算通过） | Yenefa | `docs/competition/internal/W1_CARD_Yenefa_20260907.md` Y1「范围冻结」 |
| 技术主张口径（能力表"禁止越级填绿"） | Yenefa | 同上「当前能力表」「不得把 native writer 5/5 写成 AEDL 修复 5/5」 |
| 工程主张与对外叙述 | Yenefa | Issue #15 / PR #16；AGENTS.md §8.4、§8.8 |
| 发布权限（制造签发 / 下单 / 公开范围） | 具名人类；当前发布队列由 Yenefa 持有 | ADR-004 决策 4；`docs/HANDOFF.md` 人工队列；PR #19（M2 物理线冻结） |
| 仓库可见性决策 | Yenefa | ADR-003「是否 public … 由项目负责人确认」；ADR-009 决策（不为了分支保护改 public） |

## 2. Decision ownership

| 决策类别 | Owner | 仓库证据 |
| --- | --- | --- |
| 架构接受（Architecture acceptance） | Yenefa | ADR-004（批准 B′）、ADR-005（CONDITIONAL APPROVE → 整改后采纳）、ADR-008（批准三层 Sandbox 定义） |
| 范围扩张审批 | 任务 Owner 之外的人类属主 | AGENTS.md §2.2 越界 STOP → 人类确认；`.github/ISSUE_TEMPLATE/task.md`「crossing them requires STOP + scope expansion approved by the human owner」 |
| 风险接受 | Yenefa | ADR-005「数学没错但工程解释不够严谨」→ 三项整改后采纳；ADR-004「人工签发保留制造风险的责任边界」 |
| 制造 / 发布签核 | 具名人类（AI 永不设置 release 状态） | ADR-004 决策 4；`gates/board_review_v1.json` `manufacturing_release=false`；HANDOFF「M2 物理线冻结（2026-09-01 人工裁决）」 |
| 验证政策（Verification Policy） | **SHARED：Yenefa + Percy 双人确认** | `.github/CODEOWNERS`（`/.github/workflows/`、`/docs/evidence/`、`/gates/contracts/`、`/sandbox_runtime/contracts/`）；`.github/ISSUE_TEMPLATE/task.md`「Verification Policy Change … require both human owners (Yenefa + Percy) to confirm」；`docs/COLLABORATION.md` §0.8 |
| Merge 授权（promotion） | 人类审查者；**作者不得自批** | `docs/COLLABORATION.md` §0.5.5；AGENTS.md §3.7；ADR-011「只有人工 merge 才是 promotion」 |
| 拒绝 / 升级裁决 | Yenefa（envelope `escalation.owner`；BLOCKED 记录 `Owner decision`） | AGENTS.md §2.3 升级协议与 BLOCKED 模板；`tasks/GH-49.yaml`、`tasks/GH-54.yaml` `escalation.owner: Yenefa` |
| 验收（acceptance） | 任务 Owner 之外的另一名真人 | `docs/COLLABORATION.md` §0.5.5；`W1_CARD_Yenefa`「Percy 负责独立验收」 |

**GitHub 事实（可由 `gh pr list` 复核）**：Yenefa 提交并 merge 的 PR： #6 #7 #12 #13 #16 #17 #18 #19 #21 #22 #23 #24 #25 #26 #27 #35 #42 #44 #45 #46 #47 #48 #49 #50；
Percy（`la4876949-bot`）提交、Yenefa merge 的 PR：#14 #30 #33 #34 #36 #38 #39 #40 #41 #43；
Percy merge 的 PR：#30、#42。
→ 支撑"merge 权在人类且存在双向 review"，**不**支撑任何"某一人单独完成全部技术设计"的说法。

## 3. Human-originated inputs（只列有证据的）

以下条目全部可在 ADR「团队自主判断」、AI 台账条目「团队自主部分」、Issue 或 GitHub 历史中核验。
**未登记的姓名一律保持 `UNKNOWN`，不回填**（2026-08-29 记录中的"项目负责人"未登记姓名，见 `TEAM_CONTRIBUTIONS.md`）。

### 3.1 明确提出的需求

| 内容 | 记录者 | 证据 |
| --- | --- | --- |
| 建立名为 `AEDL` 的私有仓库 | 项目负责人（姓名未登记） | ADR-003「团队自主判断」；AI-20260829-004 |
| 把 AI 使用规范嵌入项目并约束后续 AI | 项目负责人（姓名未登记） | ADR-001；AI-20260829-001 |
| 用用户提供的 v1.4 最终版替换根 `AGENTS.md` | 项目负责人（姓名未登记） | ADR-002；AI-20260829-003 |
| 更醒目地说明仓库实际使用了什么 AI | 项目负责人（姓名未登记） | AI-20260829-005；`TEAM_CONTRIBUTIONS.md` 2026-08-29 |
| 指派 Issue #3 给 Percy 并审查首版 PR #14 | Yenefa | AI-20260902-006「人类授权」 |

### 3.2 明确提出的设计目标

| 内容 | 记录者 | 证据 |
| --- | --- | --- |
| 北极星：正确交付实体板卡（sandbox 是手段不是目的） | Yenefa | Issue #15 / PR #16 |
| Sandbox 需保护的九类隔离对象 | 项目负责人（经 AI 收敛为三层） | ADR-008「AI 将项目负责人提出的九类隔离对象收敛为三层 Sandbox…」 |
| 控制面吸收顺序（Envelope → Gate → Candidate/Promotion → Escalation → Derived/Provenance → Context Routing）与四句话原则 | Yenefa | ADR-011「团队自主判断」；AI-20260901-010 |
| 换料热分析结温法、结论精度与主张纪律 | Yenefa | ADR-005 决策 1–5 |
| Exception 预授权模型与 Hash Domain 概念 | Yenefa | AI-20260901-012「两刀的设计…由 Yenefa 提出」 |
| Authority 三级模型与 TOCTOU receipt binding | Yenefa | AI-20260901-013 |
| Review Bundle 作为 AECP 特色并强制化 | Yenefa | AI-20260901-016 / -020 / -021 |
| M2 物理线冻结（不再下单 / 重签 / 换料） | 人工裁决 | PR #19；`docs/HANDOFF.md` 状态卡 |

### 3.3 明确冻结的规则

| 内容 | 记录者 | 证据 |
| --- | --- | --- |
| 失败关闭：`UNKNOWN`/缺资料/证据失配不得降级为 PASS | Yenefa | README「核心原则」；AGENTS.md §10 |
| 人机权限分离：Agent 生成/诊断/验证，人工保留晋升、制造签发、下单与最终 Review | Yenefa | README「核心原则」；AGENTS.md §2.3、§3.7 |
| AI 台账默认 `PENDING_HUMAN_REVIEW`，只有团队成员可改 | Yenefa | AGENTS.md §4；`docs/compliance/README.md` |
| 未来 ADR 必须声明 Decision owner / Proposal source / Final decision / Implementation / Review authority / Promotion-merge authority | Yenefa | 本页所在批次 Issue #54；`DECISIONS.md`「ADR 字段规范」 |
| 本批不新增 DSH actor、不回填历史 ADR 的 Decision owner、不回填 `TEAM_CONTRIBUTIONS` 的 `UNKNOWN` | Yenefa | Issue #54 裁决 |

### 3.4 明确拒绝或拦截的方案

| 内容 | 记录者 | 证据 |
| --- | --- | --- |
| 不立即公开仓库（无 LICENSE / 再分发边界未清） | 项目负责人（姓名未登记） | ADR-003 候选方案 1 被否 |
| 不采用"只做进程沙盒"或"LangGraph 承载全部硬件判断" | 项目负责人 | ADR-008 候选方案 1/2 被否，采用方案 3 |
| 首版换料审核材料的三类方法论缺陷被拦截（CONDITIONAL APPROVE） | 项目负责人 | ADR-005「问题」节；AI-20260830-002 |
| 停止"继续研究 akcli 能不能"，改为冻结 PR-1 实现合同 | Yenefa（大统领裁决） | `AEDL_PR1_大统领裁决_20260907.md`「下一步（顺序冻结）」 |
| 不为了保留工具定位牺牲 fail-closed（akcli 降级条款） | Yenefa | 同上「降级条款（预先冻结）」 |
| 不得把 native writer 5/5 写成 AEDL 修复 5/5 | Yenefa | 同上「当前能力表」 |

### 3.5 明确批准的架构

| 内容 | 记录者 | 证据 |
| --- | --- | --- |
| 独立硬件语义合同 + 人机分离制造放行（B′） | 项目负责人 | ADR-004「团队自主判断」 |
| 替代料换料审核协议（整改后采纳） | 项目负责人 | ADR-005 状态行与「团队自主判断」 |
| EDD-001 Sandbox 三层隔离与状态控制平面 | 项目负责人 | ADR-008 状态行 |
| 控制面最小切片（ADR-011） | 人类 merge（PR #21） | ADR-011 状态行；AI-20260901-019（`HUMAN_REVIEWED`） |
| GH-49 AI 台账拆分（ADR-012） | 人类 merge（PR #49） | ADR-012；AI-20260908-YEN-001（Yenefa 授权） |

## 4. AI-assisted execution

本仓库的 AI 参与是**实质且已登记**的，边界如下：

- AI **may**：提出候选方案、生成与修改代码、生成测试、执行研究与对抗性审查、起草文档与台账。
- AI **may not**：自行晋升候选、批准 PR、merge、设置 `HUMAN_REVIEWED` / `ACCEPTED` / `manufacturing_release=true`、force-push、改写共享历史。
- 每条 AI 实质贡献登记于 `docs/compliance/ai-usage/<ID>.md`，默认 `PENDING_HUMAN_REVIEW`；`AI_USAGE_LOG.md` 是生成索引。
- 证据：AGENTS.md §2.3（`Agent may propose, but not promote.`）、§3.7、§4；`docs/COLLABORATION.md` §0.5.5；ADR-011「团队自主判断」（`AI 只做实现与验证，不做策略裁决`）。

## 5. Attribution rule

> **Human ownership is decision-centric; AI attribution is execution- and assistance-centric.**
>
> 人类 ownership 由**决策、验收与责任**定义（产品方向、范围、验收标准、架构批准、主张口径、发布与 merge 权）；
> AI 归因由**执行与协助**定义（实现、测试生成、研究、审查、文档起草、重复迁移与工具化）。
> 两者都不以"谁敲了哪一行代码"为判据；提案来源与最终决策分开记录（见 `ATTRIBUTION_POLICY.md`）。

## 6. 本页不主张什么

- 不主张 Yenefa 独立设计全部架构，也不主张其手写实现代码。
- 不主张人类完成了全部技术设计：ADR 正文与 AI 台账如实记录了 AI 的方案收敛、实现与验证。
- 不把 AI 提案改写成人类原创，不删除或弱化任何 AI provenance。
- 不因"人工 approve"推断"人类完成全部技术设计"（该推断被 `ATTRIBUTION_POLICY.md` 明令禁止）。
- 不回填 `TEAM_CONTRIBUTIONS.md` 中的历史 `UNKNOWN` 负责人，也不据现状倒推历史贡献比例。
