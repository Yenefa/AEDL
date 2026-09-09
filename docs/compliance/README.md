# AEDL 合规记录入口

## 规范真源

- 当前唯一执行规范：仓库根目录 `AGENTS.md`（AEDL v1.4 基线 + project-027 硬件发布安全扩展）。
- 历史基线与格式参考：`docs/compliance/AEDL_开发记录与AI使用规范_v1.0.md`；不再作为并列执行真源。
- v1.4 导入源：项目负责人提供的 `AGENTS_v1.4_最终版.md`；其 SHA-256 基线为 `AC2E3D6FC75FE4B0BA450006BC9271480E727D1044A7B826FA89481C7107E049`。根文件在此基线上追加项目负责人要求的硬件经验必读与失败关闭规则，不再宣称逐字节一致；当前扩展版 SHA-256 为 `B883156852B671E70852A2BD3EC49365A8088B41470C21B4064DBAF1639E357C`。
- 历史工作尚未完成合规回填；没有原始证据的字段必须保持 `UNKNOWN`、`TO_VERIFY`、`NOT_RUN` 或 `PENDING`，禁止根据现状倒推历史。

外部下载目录中的文件只是导入来源。进入仓库后，以根 `AGENTS.md` 为当前执行真源；
README、HANDOFF 与本文件只负责导航和项目状态说明，不复制维护第二套执行规则。

## 台账路由

| 发生的事实 | 必须更新 |
| --- | --- |
| AI 对代码、测试、文档、设计、调试、研究、Benchmark 或媒体有实质贡献 | `ai-usage/<ID>.md` 新建条目（GH-49）；`AI_USAGE_LOG.md` 为生成索引，禁手改 |
| 新增外部工具、库、模型、服务、数据、素材、示例、Prompt 或 Skill | `THIRD_PARTY_RESOURCES.md` |
| 形成架构、接口、验证、Benchmark、范围、安全或开源边界决策 | `DECISIONS.md` |
| 形成测试、Benchmark、故障注入或效果主张 | `../evidence/EVIDENCE_INDEX.md` |
| 需要记录团队实际贡献 | `TEAM_CONTRIBUTIONS.md`，不得由 AI 猜测人员或贡献 |
| 需要判断一项工作归谁（Human / AI-assisted / Mixed） | `ATTRIBUTION_POLICY.md`（规则）；人类职责总览见 [`../HUMAN_OWNERSHIP.md`](../HUMAN_OWNERSHIP.md) |
| 想按**工作单元**看 AI 使用（默认浏览入口） | `AI_USAGE_SUMMARY.md`；逐条真源 `ai-usage/<ID>.md`，完整索引 `AI_USAGE_LOG.md` |

## 贡献归因与 AI 展示分层（2026-09-09）

```text
docs/HUMAN_OWNERSHIP.md            人类职责、决策权、验收权（引用 ADR / PR / Issue 证据）
  ↓
docs/compliance/DECISIONS.md       架构与治理决策（新 ADR 起启用归因字段）
  ↓
docs/compliance/ATTRIBUTION_POLICY.md   Human / AI-assisted / Mixed / Forbidden 分类规则
  ↓
docs/compliance/AI_USAGE_SUMMARY.md     AI 使用 → 工作单元聚合视图（人工维护）
  ↓
docs/compliance/AI_USAGE_LOG.md         逐条索引（脚本生成，禁手改）
  ↓
docs/compliance/ai-usage/<ID>.md        逐条真源（可审计工作单元）
```

聚合层只做引用：不新增事实、不改写条目正文，`Human owner` 无证据时写 `TO_VERIFY`，不默认归属。

## 台账存储（GH-49 / ADR-012）

`AI_USAGE_LOG.md` 由 `python -m tools.build_ai_usage_index build` 自动生成（文件头有 GENERATED 标记），真源是 `ai-usage/` 下的逐条文件。dev_gate 校验 ID、日期、审核状态、目录杂项与索引全文（含数量和摘要）。新条目由 `new --actor CODEX --summary "任务名"` 分配随机 ID；迁移仅跳过正文逐字节相同的 ID，出现差异必须人工核对，具体步骤见 `ai-usage/README.md`。

## 审核状态

AI 新增记录的默认状态必须为 `PENDING_HUMAN_REVIEW`。只有团队成员实际检查 diff、验证结果和第三方资源后，才能写入 `HUMAN_REVIEWED` 或 `ACCEPTED`。

台账不是制造或实体硬件证据。M2 的 A/B/C 证据边界、失败关闭门禁和回件后 C 级实测要求继续适用。
