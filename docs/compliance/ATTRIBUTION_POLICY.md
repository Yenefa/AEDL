# Attribution Policy — 贡献归因政策

> 本文件定义 AEDL 中"一项工作该归给谁"的分类法与红线。它是**规则**，不是台账；
> 具体记录仍在 `docs/compliance/DECISIONS.md`、`docs/compliance/ai-usage/<ID>.md`、
> `docs/compliance/TEAM_CONTRIBUTIONS.md` 与 `docs/evidence/EVIDENCE_INDEX.md`。
>
> 一句话总则：**Human ownership is decision-centric; AI attribution is execution- and assistance-centric.**
> 人类 ownership 由决策、验收与责任定义；AI 归因由执行与协助定义。二者分开记录，互不冒充。

---

## 1. Human-owned（人类拥有）

以下类别**只能**由人类拥有，AI 不得代为取得或代为声明：

| 类别 | 含义 | 记录位置 |
| --- | --- | --- |
| Product direction | 项目目标、北极星、优先级 | README / ADR / Issue |
| Scope | 做什么、不做什么、范围冻结 | Issue Scope / Task Envelope / ADR |
| Acceptance criteria | 什么算完成、判定语义 | Issue Acceptance Criteria / ADR |
| Architecture approval | 架构与关键接口的接受 | ADR 状态与「团队自主判断」 |
| Claims | 对外技术主张、能力表口径 | README / FUSION_MAP / 裁决记录 |
| Merge / release | 合并、晋升、制造签发、下单、公开范围 | PR / `gates/board_review_v1.json` / HANDOFF |

**允许的动词**：owner / approval / final decision / acceptance / sign-off。
**禁止的动词**：sole author / 独立完成 / 亲手编写（除非有逐行可核验的证据，本仓库当前没有此类主张）。

## 2. AI-assisted（AI 协助）

以下类别由 AI 承担执行，并**必须**按 AGENTS.md §4 逐条登记：

- Option generation（候选方案生成与比较）
- Code（代码生成与修改、重构、迁移）
- Tests（测试生成、夹具、回归）
- Research（资料检索、源码核实、第三方 intake）
- Review（对抗性检查、自洽伪造检测、复核）
- Docs（文档、台账、报告草稿）

登记要求：一个**可审计 work unit** 一条记录（不是一次 prompt）；默认 `PENDING_HUMAN_REVIEW`；
审核状态只有团队成员实际检查 diff、验证结果与第三方资源后才可改为 `HUMAN_REVIEWED` / `ACCEPTED`。
聚合视图见 `AI_USAGE_SUMMARY.md`；完整索引见 `AI_USAGE_LOG.md`；逐条真源在 `ai-usage/`。

## 3. Mixed（人机混合）

当**人类提出目标或约束、AI 收敛技术方案、人类最终批准**时，标记为 **Mixed**，
而不是 Human-only，也不是 AI-only。

判定要点（三条同时成立即 Mixed）：

1. 目标 / 约束 / 边界来自人类（有 Issue、指令或裁决记录）；
2. 技术方案的收敛、实现或验证由 AI 完成（有台账条目）；
3. 最终决策由人类作出（有批准、merge 或裁决记录）。

本仓库的典型 Mixed 实例（均可核验）：

| 实例 | 人类输入 | AI 输入 | 人类最终决定 | 证据 |
| --- | --- | --- | --- | --- |
| ADR-008 Sandbox 三层隔离 | 提出九类隔离对象 | 收敛为三层 + 三态判定 + 控制平面 + 三 Agent 计划 | 批准该定义 | ADR-008；AI-20260901-001/002 |
| ADR-011 控制面最小切片 | 定稿吸收顺序与四句话原则 | 落地 Envelope/Admission/Gate 与测试 | PR #21 merge | ADR-011；AI-20260901-010 |
| ADR-005 换料审核协议 | 拦截首版三类方法论缺陷并给整改要求 | 重算、降级表述、登记版本差异 | 整改后采纳 | ADR-005；AI-20260830-002 |
| ADR-012 AI 台账拆分 | 授权"台账拆分治理，终结编号地狱" | 设计并实现 per-entry + 随机 ID + 生成索引 | PR #49 merge | ADR-012；AI-20260908-YEN-001 |

## 4. Forbidden（禁止）

以下写法一律视为归因失真，等同于真实性红线违规（AGENTS.md §10）：

- ❌ 把 AI 生成或 AI 修改的代码标注为人类独立实现；
- ❌ 把 AI 提出的方案改写为"人类原创"（可写"人类提出目标/约束，AI 收敛方案"，不可写"人类设计"）；
- ❌ 删除、篡改或弱化历史 AI provenance（含台账条目、commit message 的 `[AI-...]` 标签、ADR 的「AI 参与」段）；
- ❌ 把"人工 approve / merge"推断成"人类完成全部技术设计"；
- ❌ 把第三方或外部贡献包装成团队自研；
- ❌ 用不可审计的百分比描述 AI 参与度（如"AI 完成 70%"）；
- ❌ 在没有证据时倒推历史归属（保持 `UNKNOWN` / `TO_VERIFY`，不回填）。

## 5. 落地规则

1. **决策类事实**写进 ADR 或 Issue，使用"Decision owner / Final decision"字段；不写"作者"。
2. **执行类事实**写进 `ai-usage/<ID>.md`，标签只用 AGENTS.md §4 的枚举值。
3. **团队贡献**写进 `TEAM_CONTRIBUTIONS.md`；AI 不得推测姓名、身份、工作量或贡献比例。
4. **聚合展示**（`AI_USAGE_SUMMARY.md`、`HUMAN_OWNERSHIP.md`）只能引用既有记录，
   并必须逐条给出 underlying records；无法核验的字段标 `TO_VERIFY`，不得默认归属。
5. 任何新增表述都必须能被当前仓库的 ADR / PR / Issue / AGENTS / Task Envelope / GitHub 历史支持。

## 6. 未来 ADR 的归因字段

新 ADR 除 AGENTS.md §6 既有内容外，必须声明（见 `DECISIONS.md`「ADR 字段规范」）：

```text
Decision owner:        <人类 / 角色>
Proposal source:       Human / AI-assisted / Mixed
Final decision:        Human
Implementation:        Human / AI-assisted / Mixed
Review authority:      <人类 / 角色>
Promotion / merge authority: <人类 / 角色>
```

历史 ADR **不回填**这些字段（本政策生效日期之前的 ADR 保持原文）。
