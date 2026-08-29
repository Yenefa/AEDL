# Third-Party Resources

> 仅登记有来源依据的事实；未知版本、授权或义务保持 `TO_VERIFY`。本台账从 2026-08-29 建立，既有依赖尚未完成全量历史回填。

## RES-001

- 名称：AEDL 开发记录与 AI 使用规范 v1.0
- 类型：文档 / Prompt / 项目治理规范
- 版本：v1.0
- 来源：项目负责人于 2026-08-29 提供的本地文件 `AEDL_开发记录与AI使用规范_v1.0.md`
- License / 授权类型：`TO_VERIFY`；本轮用户已明确授权纳入本项目
- 用途：作为 AEDL 合规接入的历史基线与台账格式参考
- 使用方式：原文保留在 `docs/compliance/AEDL_开发记录与AI使用规范_v1.0.md`；当前执行规则已由 RES-003 的根 `AGENTS.md` v1.4 接替
- 是否修改第三方源码：不适用；项目内副本保持与提供文件一致
- 是否随 AEDL 再分发：`TO_VERIFY`
- 关键许可义务：`TO_VERIFY`
- 使用限制：未经确认不得推断作者、许可证或对外再分发权
- AEDL 自主开发边界：项目负责人决定采用；AI 负责仓库内映射和台账初始化
- 合规状态：`TO_VERIFY`
- 最终开放方式：`TO_VERIFY`
- 对应模块：`docs/compliance/`
- 备注：项目内副本继续保留并可审计，但不再作为当前 Agent 执行层并列真源。

## RES-002

- 名称：OpenAI Codex desktop
- 类型：AI 工具 / 服务
- 版本：`UNKNOWN`（精确客户端与模型 ID 未在当前会话中提供）
- 来源：OpenAI Codex desktop；官方来源细节 `TO_VERIFY`
- License / 授权类型：服务条款，具体版本 `TO_VERIFY`
- 用途：读取项目、设计并写入 AEDL 项目级规范和台账、运行验证命令
- 使用方式：AI 辅助文档与仓库操作；未作为项目运行时依赖
- 是否修改第三方源码：否
- 是否随 AEDL 再分发：NO
- 关键许可义务：`TO_VERIFY`
- 使用限制：不得把 AI 输出视为已人工审核或当然拥有完整知识产权
- AEDL 自主开发边界：规范原文与采用决定来自项目负责人；AI 只实施项目化落地，最终审核由团队完成
- 合规状态：`TO_VERIFY`
- 最终开放方式：不再分发该服务
- 对应模块：AI-20260829-001
- 备注：模型名不猜测，保持 `UNKNOWN`。

## RES-003

- 名称：AEDL AGENTS.md — Git 协作 + AIC 合规执行规范
- 类型：文档 / Prompt / 项目治理规范
- 版本：v1.4（来自用户提供文件名；正文未另行标注版本号）
- 来源：项目负责人于 2026-08-29 提供的本地文件 `AGENTS_v1.4_最终版.md`
- License / 授权类型：`TO_VERIFY`；本轮用户已明确授权替换本项目根 `AGENTS.md`
- 融合角色：SUPPORT（治理与合规执行层，不作为 AEDL 核心技术创新主张）
- 用途：统一 AEDL 的 Git/GitHub、AI 留痕、第三方资源、ADR、Evidence、安全与 AIC 合规执行规则
- 使用方式：逐字节替换仓库根 `AGENTS.md`，并由 README、HANDOFF 与合规入口指向该唯一执行真源
- 是否修改上游源码：否；根文件保持与用户提供文件一致
- 是否随 AEDL 再分发：`TO_VERIFY`
- 关键许可义务：`TO_VERIFY`
- 使用限制：未经确认不得推断作者、许可证或对外再分发权
- AEDL 自主开发边界：项目负责人提供并决定采用 v1.4；AI 仅执行替换、入口同步和合规留痕
- 合规状态：`TO_VERIFY`
- 最终开放方式：`TO_VERIFY`
- 对应模块：`AGENTS.md`、`README.md`、`docs/HANDOFF.md`、`docs/compliance/`
- 备注：导入源 SHA-256 为 `AC2E3D6FC75FE4B0BA450006BC9271480E727D1044A7B826FA89481C7107E049`。

## RES-004

- 名称：GitHub.com
- 类型：SaaS / Git 远端托管服务
- 版本：`UNKNOWN`（托管 SaaS，无项目锁定客户端版本）
- 来源：GitHub 官方服务 `https://github.com/`
- License / 授权类型：服务条款，具体适用版本 `TO_VERIFY`
- 融合角色：SUPPORT（协作、备份与审计托管，不作为 AEDL 核心技术创新主张）
- 用途：托管 AEDL 的 Git 远端仓库，支持后续协作、备份和 PR 审核
- 使用方式：创建 private 空仓并绑定本地 `origin`；本轮未 push
- 是否修改上游源码：否
- 是否随 AEDL 再分发：NO
- 关键许可义务：`TO_VERIFY`
- 使用限制：公开前必须确认项目 LICENSE、第三方内容再分发权、secrets 和隐私边界
- AEDL 自主开发边界：GitHub 仅提供托管；AEDL 的代码、硬件设计、验证流程与治理记录边界仍按仓库事实披露
- 合规状态：`TO_VERIFY`
- 最终开放方式：当前 private；未来是否 public 由项目负责人在合规审计后决定
- 对应模块：Git remote `origin`、`docs/HANDOFF.md`
- 备注：仓库 URL 为 `https://github.com/sca331613-commits/AEDL`。
