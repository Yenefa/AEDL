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
- **2026-08-31 候选资料冻结（AI-20260831-029，状态 PENDING_HUMAN_REVIEW）**：
  - **AMS1117-3.3 / C6186**：原厂 Advanced Monolithic Systems 数据手册、LCSC 托管的 8 页 PDF 副本（本地冻结于
    `src/hardware/m2-board/evidence/datasheets/U3_CANDIDATE_AMS1117-3.3_C6186/`，sha256 189a2651…，UTC 2026-08-31T14:35:47Z）。
    **候选件，尚未进入 BOM**，`candidate_status = CANDIDATE_ONLY_NOT_BOM_BOUND`，`decision = BLOCKED_PENDING_THERMAL_COUT_INPUT`；
    不替换主 manifest 的 ME6211C33R5G/C235316。仅作事实核对与本地复现，版权归原厂商。
  - **Espressif ESP32-C3 官方供电指南**：官方硬件设计指南 checkpoint 页面本地 HTML 快照
    （`src/hardware/m2-board/evidence/datasheets/U1_ESP32-C3-WROOM-02/esp32c3_schematic_checklist_power_supply_2026-08-31.html`，
    sha256 6a6355…，UTC 2026-08-31T14:36:46Z），已更新进 `datasheet_manifest.json` 的 U1 hardware_design_guidelines 记录。
    仅作事实核对与本地复现，版权归原权利人（Espressif）。两项均未进入再分发。
  - 再分发权对上述两项保持 `TO_VERIFY`；不把 LCSC 托管说成厂商官方网站，准确表述为"原厂数据手册的 LCSC 托管副本"。

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

## RES-009

- 名称：LangGraph + langgraph-checkpoint-sqlite（EDD-001 Sandbox 编排层）
- 类型：第三方库（Python）
- 版本：langgraph==1.2.11、langgraph-checkpoint-sqlite==3.1.1（sandbox_runtime/pyproject.toml 锁定）
- 来源：pypi（langchain-ai/langgraph，MIT）
- License / 授权类型：MIT（`TO_VERIFY`：以随包 LICENSE 文件为准，未逐字核对）
- 融合角色：CORE（Sandbox 外层编排：状态图/条件路由/interrupt-resume/checkpoint，ADR-008 方案 3）
- 用途与使用方式：仅承担编排与人工中断恢复；硬件判决/验证/信任判定均在 AEDL 确定性模块（设计边界见 ADR-008）
- 是否修改上游源码：否
- 是否再分发：否（依赖声明，不随仓库分发源码）
- AEDL 自研边界：三层沙盒（Design/Execution/Trust）、协议 V2、策略引擎、信任存储、promotion 真值表全部自研；LangGraph 仅为外层循环载体
- 关联模块：sandbox_runtime/
## RES-010

- 名称：EDD-001 组件证据远程来源（六份，W4A Collision 1）
- 类型：第三方文档（数据手册 ×5 + 参考设计原理图 ×1，均为 provenance-pinned 远程来源）
- 版本：见下述逐份 sha256；AP63203 为 Diodes DS41326 Rev. 3-2（2024-11）
- 来源：
  - ESP32-S3-WROOM-1 datasheet — Espressif 官方
    （`https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf`，
    sha256 27d71971…，1280501 B，UTC 2026-09-02T01:28:49Z）
  - AP63203WU-7 datasheet — Diodes Incorporated 官方文档的 LCSC C780769 托管副本
    （`https://datasheet.lcsc.com/datasheet/pdf/94820cc9e44613233ddcc1a15801eca3.pdf?productCode=C780769`，
    sha256 ef99daa3…，1226090 B，UTC 2026-09-02T01:33:36Z）
  - TYPE-C-31-M-12 drawing — Korean Hroparts Elec 官方图纸的 LCSC C165948 托管副本
    （`https://datasheet.lcsc.com/datasheet/pdf/9e56b777c022540fcce7c7f67825f55e.pdf?productCode=C165948`，
    sha256 6ae33d50…，118176 B，UTC 2026-09-02T01:32:27Z；全文零 HIROSE/elecfans 标记）
  - USBLC6-2SC6 datasheet — ST 官方
    （`https://www.st.com/resource/en/datasheet/usblc6-2.pdf`，
    sha256 bc30154f…，575521 B，UTC 2026-09-02T01:28:52Z）
  - SS34 datasheet — MDD (Microdiode) 官方文档的 LCSC C8678 托管副本
    （`https://datasheet.lcsc.com/datasheet/pdf/dfa1ff67dea875d0135103ba9ada713a.pdf?productCode=C8678`，
    sha256 fb497087…，1300729 B，UTC 2026-09-02T01:32:29Z）
  - ESP32-S3-LCD-EV-Board-MB V1.5 原理图 — Espressif 官方（参考设计证据）
    （`https://dl.espressif.com/dl/schematics/SCH_ESP32-S3-LCD-Ev-Board-MB_V1.5_20231009.pdf`，
    sha256 384f0639…，1607358 B，UTC 2026-09-02T01:55:25Z）
- License / 授权类型：`TO_VERIFY`（六份文档内均为保留权利式版权声明，未见再分发授权；
  LCSC 托管副本如实表述为"原厂文档的 LCSC 托管副本"，不说成厂商官方网站）
- 融合角色：SUPPORT（EDD-001 证据链输入；POWER DRAFT 合同的事实基础）
- 用途与使用方式：provenance 冻结（URL/sha256/bytes/retrieved_at/PDF 元数据登记于
  `src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json` 的
  `metadata.remote_evidence`）；为 POWER 合同草案（`gates/contracts/edd001_power_contract_v1.json`，
  DRAFT）提供 evidence-first 输入
- 是否修改上游源码：否
- 是否随 AEDL 再分发：**否**——Owner 裁定（2026-09-02）：redistribution TO_VERIFY 期间
  binary 不入仓，仅元数据冻结；公开前须逐份复审再分发边界
- AEDL 自研边界：六份均为第三方文档；本地二进制副本暂存于仓库外（不入 git）
- 合规状态：`TO_VERIFY`
- 关联模块：`src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json`、
  `gates/contracts/edd001_power_contract_v1.json`（DRAFT）
- 关联 AI Usage：AI-20260902-004；关联 Evidence：EVID-20260902-002
