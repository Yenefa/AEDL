# Team Contributions

> 只记录实际发生且可确认的团队贡献。AI 不得推测姓名、身份、工作量或贡献比例。

## 2026-08-29 — AEDL AI 使用规范项目化

- 负责人：`UNKNOWN`（未向 AI 提供可核验姓名）
- 协作者：OpenAI Codex desktop（AI-20260829-001、AI-20260829-002）
- 实际完成：
  - 项目负责人提供 AEDL v1.0 原文，明确决定将其纳入 project-027 并约束后续 AI。
  - AI 将规则映射到项目入口、台账与 Evidence 索引。
  - AI 在验收中发现并修复签发后失效的历史 board review 测试夹具。
- 人工审核：`HUMAN_REVIEWED / ACCEPTED`（项目负责人，姓名未提供，2026-08-29；授权本地提交，明确不 push）
- 关联 AI Usage：AI-20260829-001、AI-20260829-002
- 关联 Commit / PR：本次本地提交（提交信息关联 AI Usage ID）；未创建 PR；不 push
- 关联 Evidence：EVID-20260829-001、EVID-20260829-002、EVID-20260829-003
- 备注：未推断本任务之外的历史团队贡献。

## 2026-08-29 — AEDL AGENTS v1.4 替换

- 负责人：`UNKNOWN`（未向 AI 提供可核验姓名）
- 协作者：OpenAI Codex desktop（AI-20260829-003）
- 实际完成：
  - 项目负责人提供 `AGENTS_v1.4_最终版.md`，明确该规范针对 AEDL，并要求替换现版本。
  - AI 将根 `AGENTS.md` 逐字节替换为 v1.4，并同步 README、HANDOFF 与合规索引的规范真源说明。
- 人工审核：`HUMAN_REVIEWED`（项目负责人明确确认审核完毕）
- 关联 AI Usage：AI-20260829-003
- 关联 Commit / PR：本地提交 `c7f4dda`；未创建 PR；未 push
- 关联 Evidence：无（治理文档替换，不形成硬件或比赛技术效果证据）
- 备注：未推断负责人姓名、许可证或对外再分发权。

## 2026-08-29 — AEDL GitHub repo 建立

- 负责人：`UNKNOWN`（未向 AI 提供可核验姓名）
- 协作者：OpenAI Codex desktop（AI-20260829-004）
- 实际完成：
  - 项目负责人明确要求建立名为 `AEDL` 的 repo。
  - AI 创建 private GitHub 空仓、绑定本地 `origin`，补齐最小 `.gitignore` 防护并记录公开前置条件。
- 人工审核：`HUMAN_REVIEWED`（项目负责人明确确认审核完毕）
- 关联 AI Usage：AI-20260829-004
- 关联 Commit / PR：本地提交 `c7f4dda`；未创建 PR；未 push
- 关联 Evidence：无（Git/GitHub 治理接入，不形成比赛技术效果证据）
- 备注：未推断负责人姓名；未公开或上传项目内容。

## 2026-08-29 — AI 使用披露澄清

- 负责人：`UNKNOWN`（未向 AI 提供可核验姓名）
- 协作者：OpenAI Codex desktop（AI-20260829-005）
- 实际完成：
  - 项目负责人指出仓库需要更醒目地说明实际使用了什么 AI，并同意继续整理。
  - AI 在 README 中区分已登记的 Codex 使用、计划支持的 Agent 底座、非 AI 工具与 `UNKNOWN` 历史边界，并同步提交状态。
- 人工审核：`HUMAN_REVIEWED`（项目负责人明确确认审核完毕）
- 关联 AI Usage：AI-20260829-005
- 关联 Commit / PR：未提交；未创建 PR；未 push
- 关联 Evidence：无（治理文档澄清，不形成硬件或比赛技术效果证据）
- 备注：未根据客户端名称倒推历史精确模型版本。

## 2026-09-11 — PR #60（A2-L D baseline）两轮人工对抗复核

- 负责人：`Yenefa`（ID_MAP 记录的项目负责人）。
- 协作者：OpenCode Desktop（AI 辅助复现取证与发布；`AI-20260911-OPENCODE-E1C979A5B030BE12E7E3E174226C2BE7`）。
- 实际完成：
  - v0.3.0（f190781）首轮 review（GitHub #60 评论）：判定 "green tests, wrong system"——自造 Proposal 协议未对齐冻结 C1 `parse_proposal`、公共输入旁路（checker findings + `aedl.public-facts.draft-0.1`）、expected 信息级别在公共输入冻结前写死。
  - v0.4.0（3ce3a2e）rework 复核（GitHub review `CHANGES_REQUESTED`）：确认第一条已修复（23/23 输出经真实 C1 验证）；判定第二/三条未修复——真实 y4-public.v3 包（calibration + Y4-001）CLI 实测 exit 2（`public_facts` 形态不符）、观测视图不匹配（`kicad_netlist_current.v1` vs `views.*`）；给出三条放行前置。
- 人工审核：本条记录人类审查动作本身；GitHub review 状态 `CHANGES_REQUESTED`（2026-09-11）。
- 关联 AI Usage：`AI-20260911-OPENCODE-E1C979A5B030BE12E7E3E174226C2BE7`
- 关联 Commit / PR：PR #60（评论 + review）；无仓库文件变更。
- 关联 Evidence：无（评审结论，不构成硬件/技术效果证据）。
- 备注：实测取证由 AI 辅助执行并已在 AI 条目登记；结论与责任归属 Yenefa。
