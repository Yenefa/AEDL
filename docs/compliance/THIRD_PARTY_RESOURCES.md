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
- 使用方式：作为仓库根 `AGENTS.md` 的 v1.4 基线，并由 README、HANDOFF 与合规入口指向该唯一执行真源；2026-08-30 起在基线上追加 project-027 硬件发布安全扩展
- 是否修改上游源码：导入副本不修改；根执行文件已追加项目专属规则
- 是否随 AEDL 再分发：`TO_VERIFY`
- 关键许可义务：`TO_VERIFY`
- 使用限制：未经确认不得推断作者、许可证或对外再分发权
- AEDL 自主开发边界：项目负责人提供并决定采用 v1.4；AI 仅执行替换、入口同步和合规留痕
- 合规状态：`TO_VERIFY`
- 最终开放方式：`TO_VERIFY`
- 对应模块：`AGENTS.md`、`README.md`、`docs/HANDOFF.md`、`docs/compliance/`
- 备注：导入源 SHA-256 为 `AC2E3D6FC75FE4B0BA450006BC9271480E727D1044A7B826FA89481C7107E049`；项目扩展版当前 SHA-256 为 `B883156852B671E70852A2BD3EC49365A8088B41470C21B4064DBAF1639E357C`，扩展内容与理由见 ADR-004。

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

## RES-005

- 名称：akcli-kicad
- 类型：第三方 EDA 自动化 CLI
- 版本：0.21.0；protocol 2
- 来源：本机 Hermes venv 中的 `akcli.exe`；项目记录指向 `https://pypi.org/project/akcli-kicad/`，安装来源链仍为 `TO_VERIFY`
- License / 授权类型：`TO_VERIFY`
- 用途：从当前 M2 intent 生成并验证 109 条 KiCad ops
- 使用方式：仅作为设计生成/验证工具；最终原理图仍由 KiCad ERC、独立语义合同与人工审核约束
- 是否修改上游源码：否
- 是否随 AEDL 再分发：NO
- 关键许可义务：`TO_VERIFY`
- 使用限制：`akcli check --intent` 只能证明派生物符合 intent，不能证明 intent 符合数据手册
- AEDL 自主开发边界：AEDL 自研的是独立语义合同、故障注入与制造门禁；akcli 是 SUPPORT 工具
- 合规状态：`TO_VERIFY`
- 最终开放方式：不随仓库分发本机安装
- 对应模块：`tools/generate_m2_ops.py`、`src/hardware/m2-board/ops_gen.json`
- 备注：实际可执行路径属于本机环境，不作为跨机器固定路径。

## RES-006

- 名称：jlcpcb CLI / JLC assembly catalog
- 类型：第三方器件目录查询 CLI / 在线数据服务
- 版本：jlcpcb 0.1.0；在线目录为查询时状态
- 来源：本机 Hermes venv 中的 `jlcpcb.exe`；项目记录指向 `https://pypi.org/project/jlcpcb/`
- License / 授权类型：CLI 与在线数据条款均为 `TO_VERIFY`
- 用途：按精确 LCSC code 查询 JLC 装配库的 MPN、厂商、封装、库别和库存
- 使用方式：`gates/refresh_bom_stock.py` 生成与规范 BOM 哈希绑定的即时查询证据
- 是否修改上游源码：否
- 是否随 AEDL 再分发：NO
- 关键许可义务：`TO_VERIFY`
- 使用限制：库存是瞬时外部状态；零库存必须失败关闭，相似型号不得自动替换
- AEDL 自主开发边界：AEDL 自研查询校验、证据绑定和失败关闭；目录内容来自 JLC/LCSC
- 合规状态：`TO_VERIFY`
- 最终开放方式：不随仓库分发本机安装或目录数据全集
- 对应模块：`gates/refresh_bom_stock.py`、`notes/m2-evidence-reset/generated/bom_stock_current.json`
- 备注：2026-08-30T10:35:01Z 精确查询 C82942 的装配库存为 0。

## RES-007

- 名称：器件原厂数据手册与 LCSC 托管副本
- 类型：第三方技术文档
- 版本：查询时可获得版本；逐份修订号 `TO_VERIFY`
- 来源：Espressif ESP32-C3-WROOM-02、Sensirion SHT3x-DIS、MICRONE ME6211C33M5G-N、MICRONE ME6211C33R5G（C235316，V20 版数据手册，用于 U3 换料引脚兼容性核实）以及候选 TECH PUBLIC TP6211C33M5G 的原厂/LCSC 数据手册链接
- License / 授权类型：各权利人版权；再分发权 `TO_VERIFY`
- 用途：建立独立硬件语义合同，并评估零库存器件的候选替代
- 使用方式：只提取管脚、电气和推荐外围约束
- 是否修改上游源码：否
- 是否随 AEDL 再分发：NO
- **2026-08-31 人工决定（AI-20260831-025）**：本地冻结副本**保留**于
  `src/hardware/m2-board/evidence/datasheets/`（6 份 PDF，manifest 记录 source_url/sha256/
  retrieved_at 完整归因）；版权归原厂、仅作参考与本地复现、归因指向官方源的显式声明见
  `NOTICE` 与 README「知识产权与许可合规」节。
- 关键许可义务：引用来源，不复制未获授权全文
- 使用限制：名称相似不代表引脚或电气兼容；缺失参数保持 UNKNOWN
- AEDL 自主开发边界：数据手册是外部事实源；合同、交叉验证和取舍由 AEDL/人工完成
- 合规状态：`TO_VERIFY`
- 最终开放方式：仅保留链接和必要事实引用
- 对应模块：`gates/contracts/m2_schematic_contract_v1.json`、`docs/knowledge/PROJECT_PITFALLS.md`
- 备注：候选替代尚未获人工制造签发。2026-08-30 AI-20260830-002 依据 ME6211C V20 数据手册核实 SOT-353 与 SOT-23-5 引脚序一致后执行 U3 换料（C82942 → C235316），换料全链改动仍处 `PENDING_HUMAN_REVIEW`。

## RES-008

- 名称：项目 License 选择——Apache License 2.0
- 类型：治理决定（人工拍板）
- 版本：Apache License 2.0（正文取自 apache.org 官方原版文本，2026-08-31）
- 来源：大统领 2026-08-31 拍板（此前仓库无 LICENSE，默认保留所有权利）
- License / 授权类型：Apache-2.0；第三方归因载体为 `NOTICE`
- 用途：公开仓库的法律基础（含专利授权条款）；六份冻结 PDF 依 RES-007 补记保留并归因
- 使用方式：见 LICENSE / NOTICE / README「知识产权与许可合规」节
- 是否修改上游源码：否
- 是否随 AEDL 再分发：是（本项目自身代码与文档；第三方文档归因除外）
