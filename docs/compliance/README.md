# AEDL 合规记录入口

## 规范真源

- 项目内规范：`docs/compliance/AEDL_开发记录与AI使用规范_v1.0.md`
- 强制入口：仓库根目录 `AGENTS.md`
- 生效时间：2026-08-29；从本次接入起按任务持续记录。
- 历史工作尚未完成合规回填；没有原始证据的字段必须保持 `UNKNOWN`、`TO_VERIFY`、`NOT_RUN` 或 `PENDING`，禁止根据现状倒推历史。

外部下载目录中的原文件只是本次导入来源。进入仓库后，以项目内副本和 `AGENTS.md` 的项目化规则为准。

## 台账路由

| 发生的事实 | 必须更新 |
| --- | --- |
| AI 对代码、测试、文档、设计、调试、研究、Benchmark 或媒体有实质贡献 | `AI_USAGE_LOG.md` |
| 新增外部工具、库、模型、服务、数据、素材、示例、Prompt 或 Skill | `THIRD_PARTY_RESOURCES.md` |
| 形成架构、接口、验证、Benchmark、范围、安全或开源边界决策 | `DECISIONS.md` |
| 形成测试、Benchmark、故障注入或效果主张 | `../evidence/EVIDENCE_INDEX.md` |
| 需要记录团队实际贡献 | `TEAM_CONTRIBUTIONS.md`，不得由 AI 猜测人员或贡献 |

## 审核状态

AI 新增记录的默认状态必须为 `PENDING_HUMAN_REVIEW`。只有团队成员实际检查 diff、验证结果和第三方资源后，才能写入 `HUMAN_REVIEWED` 或 `ACCEPTED`。

台账不是制造或实体硬件证据。M2 的 A/B/C 证据边界、失败关闭门禁和回件后 C 级实测要求继续适用。
