# AI Usage Log

> 项目内所有实质 AI 贡献按 `AI-YYYYMMDD-NNN` 记录。AI 新增记录的默认状态必须为 `PENDING_HUMAN_REVIEW`；只有团队成员实际审核后才能改变人工审核状态。

## AI-20260829-001

- 日期：2026-08-29
- 任务名称：将 AEDL 开发记录与 AI 使用规范固化为 project-027 项目级约束
- 模块/路径：
  - `.gitattributes`
  - `AGENTS.md`
  - `README.md`
  - `docs/HANDOFF.md`
  - `docs/compliance/`
  - `docs/evidence/EVIDENCE_INDEX.md`

- AI 工具/平台：OpenAI Codex desktop
- 模型：`UNKNOWN`（当前会话未暴露可核验的精确模型 ID）

- AI 参与类型：
  - [x] ADVISE
  - [ ] GENERATE_CODE
  - [ ] REFACTOR
  - [ ] DEBUG
  - [ ] GENERATE_TEST
  - [ ] RESEARCH
  - [x] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 任务目标：
  - 把用户提供的 AEDL v1.0 规范迁入仓库，建立所有后续 AI 都能发现的项目入口与合规台账。

- AI 实际产出：
  - 在根 `AGENTS.md` 写入强制开工、收尾、真实性、审核和最终回复规则。
  - 建立项目内规范真源、四类合规台账与 Evidence 索引。
  - 在 README 与 HANDOFF 增加冗余入口，降低不同 AI 工具漏读风险。
  - 为规范原文自带的 Markdown 强制换行空格增加单文件 Git whitespace 例外，保持项目副本与用户提供原文件的 SHA-256 一致，不放宽其他文件。

- 团队自主部分：
  - 项目负责人提供规范原文并明确决定将其纳入本项目，要求后续 AI 一律遵守。
  - AI 只负责项目化映射、文件组织和真实性边界落地。

- 人工修改：
  - 审核期间检测到 `AGENTS.md` 的适用 AI 工具列表由 `Cursor、OpenHands` 调整为 `Opencode`；具体修改者身份无法由 Git 工作树核验（`UNKNOWN`）。

- 人工审核：
  - 状态：`HUMAN_REVIEWED`
  - 审核人：项目负责人（姓名未提供）
  - 审核内容：用户明确确认人工审核通过，并授权本地提交、明确不 push。

- 验证：
  - 修改前命令：`py -3 gates\run_gates.py`
  - 修改前结果：PASS；exit 0；7/7 门禁通过；`manufacturing_release=true`
  - 修改后结构检查：PASS；10 个必需文件存在且非空；规范源文件与项目副本 SHA-256 一致；AGENTS/README/HANDOFF 引用检查通过
  - 修改后回归门禁：PASS；exit 0；7/7 门禁通过；`board_review=pass`；`manufacturing_release=true`
  - Evidence ID：EVID-20260829-001、EVID-20260829-002

- 新增第三方资源：
  - RES-001
  - RES-002

- 关联设计决策：
  - ADR-001

- Commit / PR：
  - 本次本地提交（提交信息关联本记录 ID）；未创建 PR；不 push。

- 最终状态：
  - `ACCEPTED`

- 备注：
  - 本次未对 2026-08-29 之前的历史 AI 使用、第三方资源或团队贡献做无证据回填。

## AI-20260829-002

- 日期：2026-08-29
- 任务名称：修复签发后失效的历史 board review 门禁测试
- 模块/路径：
  - `tests/test_run_gates.py`
  - `tests/fixtures/board_review_before_release.json`

- AI 工具/平台：OpenAI Codex desktop
- 模型：`UNKNOWN`（当前会话未暴露可核验的精确模型 ID）

- AI 参与类型：
  - [ ] ADVISE
  - [ ] GENERATE_CODE
  - [ ] REFACTOR
  - [x] DEBUG
  - [x] GENERATE_TEST
  - [ ] RESEARCH
  - [x] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 任务目标：
  - 保留“历史证据不得被判绿”的失败关闭回归意图，同时使测试不再依赖当前可变的签发文件。

- AI 实际产出：
  - 复现并定位 1/30 单测失败。
  - 从签发前提交冻结 `board_review_before_release.json` 夹具。
  - 让历史证据测试引用冻结夹具；未修改生产门禁实现和当前 `gates/board_review_v1.json`。

- 团队自主部分：
  - 项目既有规则要求历史失败证据与当前签发证据隔离，并保持失败关闭语义。

- 人工修改：
  - 未报告额外人工修改。

- 人工审核：
  - 状态：`HUMAN_REVIEWED`
  - 审核人：项目负责人（姓名未提供）
  - 审核内容：用户明确确认人工审核通过，并授权本地提交、明确不 push。

- 验证：
  - RED：`py -3 -m unittest tests.test_run_gates.RunGatesTests.test_historical_evidence_is_reported_as_blocked_not_green -v`
  - RED 结果：FAIL；当前 signed board review 返回 `pass`，旧断言期望 `fail`
  - GREEN：同一命令
  - GREEN 结果：PASS；1/1
  - 全量单测：`py -3 -m unittest discover -s tests -v` → PASS；30/30
  - Evidence ID：EVID-20260829-003

- 新增第三方资源：
  - 无

- 关联设计决策：
  - 无

- Commit / PR：
  - 本次本地提交（提交信息关联本记录 ID）；未创建 PR；不 push。

- 最终状态：
  - `ACCEPTED`

- 备注：
  - 夹具内容来自仓库提交 `00bf694` 中签发前的 `gates/board_review_v1.json`。

## AI-20260829-003

- 日期：2026-08-29
- 任务名称：将 AEDL 根 AGENTS 执行规范升级为用户提供的 v1.4 最终版
- 模块/路径：
  - `.gitattributes`
  - `AGENTS.md`
  - `README.md`
  - `docs/HANDOFF.md`
  - `docs/compliance/`

- AI 工具/平台：OpenAI Codex desktop
- 模型：`UNKNOWN`（当前会话未暴露可核验的精确模型 ID）

- AI 参与类型：
  - [x] ADVISE
  - [ ] GENERATE_CODE
  - [ ] REFACTOR
  - [ ] DEBUG
  - [ ] GENERATE_TEST
  - [ ] RESEARCH
  - [x] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 任务目标：
  - 用用户提供的 AEDL v1.4 最终版逐字节替换根 `AGENTS.md`，并消除旧 v1.0 与新执行规范之间的多真源歧义。

- AI 实际产出：
  - 根 `AGENTS.md` 与 `AGENTS_v1.4_最终版.md` 保持逐字节一致。
  - README、HANDOFF 与合规 README 改为指向根 v1.4 唯一执行真源。
  - 将 v1.0 标记为历史基线与格式参考，新增 RES-003、ADR-002 和团队贡献记录。

- 团队自主部分：
  - 项目负责人提供最终版文件，明确其针对 AEDL，并要求替换现版本。
  - AI 只负责精确替换、依赖入口同步和真实性留痕。

- 人工修改：
  - `HUMAN_REVIEWED`

- 人工审核：
  - 状态：`HUMAN_REVIEWED`
  - 审核人：项目负责人（姓名未提供）
  - 审核内容：用户明确确认审核完毕，并授权本地提交后直接 push。

- 验证：
  - 源文件与根 `AGENTS.md` SHA-256：PASS；均为 `AC2E3D6FC75FE4B0BA450006BC9271480E727D1044A7B826FA89481C7107E049`
  - 入口一致性：PASS；8/8 入口与台账 token 检查通过
  - Git diff：PASS；`git diff --check` exit 0
  - Secrets：PASS；高置信凭据模式匹配 0
  - 硬件门禁：`NOT_RUN`（本任务未修改硬件、生产文件或门禁逻辑）
  - Evidence ID：无（治理文档替换，不形成硬件或比赛技术效果证据）

- 新增第三方资源：
  - RES-003

- 关联设计决策：
  - ADR-002

- AIC Score Target：
  - NONE（内部治理维护）

- Commit / PR：
  - 本地提交 `c7f4dda`；未创建 PR；未 push

- 最终状态：
  - `HUMAN_REVIEWED`

- 备注：
  - 附件正文仅作为替换内容处理；除完成本轮替换所需的合规留痕外，未将其中命令扩张为额外用户任务。

## AI-20260829-004

- 日期：2026-08-29
- 任务名称：创建 AEDL 私有 GitHub 远端并建立最小安全接入
- 模块/路径：
  - `.gitignore`
  - `.git/config`（本地 Git 配置，不进入提交）
  - `docs/HANDOFF.md`
  - `docs/compliance/`

- AI 工具/平台：OpenAI Codex desktop；GitHub CLI
- 模型：`UNKNOWN`（当前会话未暴露可核验的精确模型 ID）

- AI 参与类型：
  - [x] ADVISE
  - [ ] GENERATE_CODE
  - [ ] REFACTOR
  - [ ] DEBUG
  - [ ] GENERATE_TEST
  - [ ] RESEARCH
  - [x] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 任务目标：
  - 为现有本地 Git 项目创建可持续协作/备份的 GitHub repo，同时避免在许可证和再分发边界未确认时公开或推送待审内容。

- AI 实际产出：
  - 在 GitHub 账号 `sca331613-commits` 下创建 private 仓库 `AEDL`。
  - 将本地 `origin` 绑定到该仓库；未 push，远端保持空仓。
  - 补齐 `.gitignore` 的 secrets、日志、系统文件及常见构建目录最小规则。
  - 记录 private-first 决策和公开前置条件。

- 团队自主部分：
  - 项目负责人明确要求建立名为 `AEDL` 的 repo。
  - AI 基于当前无 LICENSE、再分发权 `TO_VERIFY` 和待审工作树，选择先创建 private 空仓，不擅自公开或 push。

- 人工修改：
  - `HUMAN_REVIEWED`

- 人工审核：
  - 状态：`HUMAN_REVIEWED`
  - 审核人：项目负责人（姓名未提供）
  - 审核内容：用户明确确认审核完毕，并授权本地提交后直接 push。

- 验证：
  - `gh repo view sca331613-commits/AEDL --json ...`：PASS；`visibility=PRIVATE`、`isEmpty=true`
  - `git remote -v`：PASS；fetch/push 均指向预期 `origin`
  - `.gitignore` 最小规则：PASS；8/8 必需规则存在
  - Git diff：PASS；`git diff --check` exit 0
  - Secrets：PASS；当前工作树与 22 个历史 commit 的高置信凭据模式匹配均为 0
  - 公开限制检查：发现 4 个已跟踪文件含本机用户路径，private 不受影响；改为 public 前必须脱敏
  - 项目测试/硬件门禁：`NOT_RUN`（未修改代码、硬件、生产文件或门禁逻辑）
  - Evidence ID：无（仓库治理接入，不形成比赛技术效果证据）

- 新增第三方资源：
  - RES-004

- 关联设计决策：
  - ADR-003

- AIC Score Target：
  - NONE（内部 Git/GitHub 治理维护）

- Commit / PR：
  - 本地提交 `c7f4dda`（本记录 ID 位于 commit body）；未创建 PR；未 push

- 最终状态：
  - `HUMAN_REVIEWED`

- 备注：
  - 未创建 Release/tag，未把仓库设为 public，未向远端传输当前项目内容。
  - 初次按本地目录名创建 private 空仓；用户明确正式名称为 `AEDL` 后，在任何 push 前原地重命名并更新 `origin`，没有遗留第二个仓库。

## AI-20260829-005

- 日期：2026-08-29
- 任务名称：在 README 明确披露实际 AI 使用与未知边界
- 模块/路径：
  - `README.md`
  - `docs/HANDOFF.md`
  - `docs/compliance/AI_USAGE_LOG.md`
  - `docs/compliance/TEAM_CONTRIBUTIONS.md`

- AI 工具/平台：OpenAI Codex desktop
- 模型：基于 GPT-5；精确部署型号/版本 ID 为 `UNKNOWN`

- AI 参与类型：
  - [x] ADVISE
  - [ ] GENERATE_CODE
  - [ ] REFACTOR
  - [ ] DEBUG
  - [ ] GENERATE_TEST
  - [ ] RESEARCH
  - [x] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 任务目标：
  - 让读者在 README 首页即可分辨实际登记的 AI、计划支持的 Agent 底座、非 AI 工具和无法核验的历史/模型信息。

- AI 实际产出：
  - 新增“AI 使用披露”，明确已登记贡献使用 OpenAI Codex desktop。
  - 明确 `AI-20260829-001` 至 `004` 的精确模型 ID 不可核验，当前任务仅能确认 Codex 基于 GPT-5。
  - 明确 OpenCode / Claude Code 是计划支持的技术栈，不是本阶段使用证据；GitHub CLI 不是 AI。
  - 同步 `c7f4dda` 提交状态，修复 HANDOFF 和既有台账中的“未提交”事实漂移。

- 团队自主部分：
  - 项目负责人指出 AI 使用披露不够醒目，并明确同意进行下一步整理。
  - AI 负责核对现有记录、保持未知边界并完成文档同步。

- 人工修改：
  - `HUMAN_REVIEWED`

- 人工审核：
  - 状态：`HUMAN_REVIEWED`
  - 审核人：项目负责人（姓名未提供）
  - 审核内容：用户明确确认审核完毕，并授权本地提交后直接 push。

- 验证：
  - README 披露字段检查：PASS；Codex、GPT-5/`UNKNOWN` 边界、OpenCode / Claude Code 定位、GitHub CLI 非 AI 四类信息均存在
  - Git diff：PASS；`git diff --check` exit 0
  - 项目测试/硬件门禁：`NOT_RUN`（未修改代码、硬件、生产文件或门禁逻辑）
  - Evidence ID：无（治理文档澄清，不形成硬件或比赛技术效果证据）

- 新增第三方资源：
  - 无

- 关联设计决策：
  - 无

- AIC Score Target：
  - NONE（仓库透明度维护，不形成比赛技术主张）

- Commit / PR：
  - 未提交；未创建 PR；未 push

- 最终状态：
  - `HUMAN_REVIEWED`

## AI-20260830-001

- 日期：2026-08-30
- 任务名称：M2 原理图语义缺陷根因分析与完整修复设计
- 模块/路径：
  - `docs/superpowers/specs/2026-08-30-m2-schematic-semantic-release-design.md`
  - `docs/compliance/AI_USAGE_LOG.md`

- AI 工具/平台：OpenAI Codex desktop
- 模型：基于 GPT-5；精确部署型号/版本 ID 为 `UNKNOWN`

- AI 参与类型：
  - [x] ADVISE
  - [ ] GENERATE_CODE
  - [ ] REFACTOR
  - [x] DEBUG
  - [ ] GENERATE_TEST
  - [x] RESEARCH
  - [x] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 任务目标：
  - 解释 USB 极性反接与 SHT30 ADDR 悬空为何能够逃逸至下单终检，并设计同时修复硬件源、制造门禁和项目经验闭环的方案。

- AI 实际产出：
  - 将根因定位为错误 intent 被生成器、ERC、DRC 和几何评审共同消费后形成的同源循环自证。
  - 基于 Espressif 与 Sensirion 官方资料确认关键管脚约束和推荐外围。
  - 形成方案 B 设计：数据手册独立契约、三方网表比对、故障注入、制造许可撤回、完整电路修复和项目专属经验提升注册表。

- 团队自主部分：
  - 项目负责人要求立即纠正优先级、修改项目并把事故经验沉淀进 AEDL 专属优化系统，明确批准方案 B 和必要的 BOM/PCB 调整。

- 人工修改：
  - 未报告额外人工修改。

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 审核人：待项目负责人复核书面规格。

- 验证：
  - 已核对当前 intent、PCB pad-to-net、固件地址常量、M1 ops 代理路径和最新门禁 manifest。
  - 已完成设计规格的 placeholder、内部一致性和范围自检。
  - 代码、硬件和生产文件验证：`NOT_RUN`（设计阶段，尚未实施）。

- 新增第三方资源：
  - 无；官方数据手册登记与哈希将在实施阶段按实际下载文件更新。

- 关联设计决策：
  - 待实施阶段写入正式 ADR。

- AIC Score Target：
  - 创新性与方案设计；实现完成度与可验证效果。

- Commit / PR：
  - 设计规格将单独本地提交；未创建 PR；未 push。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`

## AI-20260830-002

- 日期：2026-08-30
- 任务名称：接手 P0 终检半成品——U3 LDO 零库存换料与全链收敛
- 模块/路径：
  - `src/hardware/m2-board/intent_v1.json`
  - `src/hardware/m2-board/m2_board.kicad_sch`
  - `src/hardware/m2-board/m2_board.kicad_pcb`
  - `src/hardware/m2-board/ops_gen.json`
  - `gates/bom/bom_v1.json`
  - `gates/board_review_v1.json`
  - `tools/board_review.py`
  - `delivery/`（重新导出全套）
  - `docs/HANDOFF.md`
  - `notes/m2-evidence-reset/generated/`（库存/ops/评审/manifest 证据刷新）

- AI 工具/平台：TRAE（GLM）
- 模型：GLM-5.3

- AI 参与类型：
  - [x] ADVISE
  - [x] GENERATE_CODE
  - [ ] REFACTOR
  - [x] DEBUG
  - [ ] GENERATE_TEST
  - [ ] RESEARCH
  - [x] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 任务目标：
  - 接手 AI-20260830-001 停止后遗留的 P0 半成品（2 个失败测试 + 哈希过期交付链），
    完成下单前终检闭环。

- AI 实际产出：
  - 诊断确认：C82942（U3 LDO）嘉立创装配库存当日实时查询为 0（早间快照 5 → 晚间 0），
    `refresh_bom_stock.py` 失败关闭正确拦截；交付 manifest 哈希绑定过期为伴生问题。
  - 换料决策与实施：选定同厂同系列 C235316（ME6211C33R5G，SOT-353/SC-70-5，
    库存 3329）；依据 MICRONE ME6211C V20 数据手册核实 SOT-353 封装
    pin1=VIN/pin2=GND/pin3=CE/pin5=VOUT 引脚序与原 SOT-23-5 完全一致、电气规格相同。
  - 全链同步：intent_v1 / bom_v1 / 原理图（value+footprint+description）/ PCB footprint
    （KiCad 官方 SOT-353_SC-70-5 几何逐字替换，保持 at/rot/pad 网络）/ 逃逸布线重布
    （+5V 环走廊 x=54.02、+3V3 垂直落新 pad5、删旧 pad3 孤立残段）。
  - 检测盲区修复：`tools/board_review.py` 热源/极性/去耦三处 lib_id 关键字补 `SOT-353`，
    否则换封装后 U3 从三项检查中静默消失（属变相放水，违反失败关闭原则）。
  - 证据链刷新：akcli 0.21.0（已恢复）经 `tools/generate_m2_ops.py` 从新 intent 正规
    重放 ops_gen.json（109 op）；`refresh_bom_stock.py` 刷新 14 料实时正库存；
    `export_delivery.py` 重新导出全套交付物并哈希绑定；board_review 8/8 机器实测刷新。
  - 文档：HANDOFF.md 全面更新（过期 HEAD 引用、"远端为空"过期描述、门禁表、换料记录）。
  - 接手惯例固化（经项目负责人确认）：HANDOFF.md 前置块新增"开工时读台账最近 2–3 条、
    收尾时按 AGENTS.md 第 4 节写入记录"的惯例；依据是本会话靠台账识别出并行
    AI-20260830-001 会话边界、避免并发写坏工作区的事实。

- 团队自主部分：
  - 项目负责人明确指令接手 AI-20260830-001 未完成工作并继续 P0 终检，要求遵守全部
    AEDL 规则并保留可审查痕迹。
  - 换料选型（C235316）为 AI 基于库存与数据手册提出的工程方案，最终采纳与制造放行
    留待项目负责人审核。

- 人工修改：
  - 未报告额外人工修改。

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 审核人：项目负责人（姓名未提供）
  - 审核内容：换料方案初审结论为 CONDITIONAL APPROVE（有条件通过），指出三项整改：
    1. 热分析不得用 "250mW÷压差" 冒充热电流上限，须按 θJA 结温法重做；
    2. SOT-23-5 原封装热参数须确认后才允许声称"热余量降低多少"；
    3. "same die"/"全系唯一候选"等过强表述须降级或补排他性证据。
  - 整改完成情况：
    1. 已按 Tj = Ta + PD×θJA 重做热验证（V24 datasheet：SOT-353 θJA=270°C/W、
       SOT-23-5 θJA=210°C/W、Tjmax=150°C、TOPR=-40~+85°C）；结论改为
       "同等结温预算下持续电流能力约 -22%"；
    2. SOT-23-5 基线确认：V20 的 PD 表未列 SOT23-5（初版材料中 "~300mW" 实为
       SOT23-3 行的解析误读）；V24 明确 SOT23-5 PD=0.60W/θJA=210°C/W，且
       V24 内部自洽（125°C/210≈0.60W、125°C/270≈0.45W）；
    3. 表述已降级："same die"→"同系列同输出电压同引脚映射（V24 Selection Guide
       佐证 M5/R5 为同系列不同封装后缀，silicon 同一性不主张也不需要）"；
       "全系唯一"→"JLC 装配目录 ME6211C33 检索的 3 个候选中唯一 pin-compatible
       正库存方案"（C428904 X2-SON-4 因 pin1=CE 引脚序不同排除）。
  - 新增审计发现：V20（C235316 绑定版）与 V24 家族版热额定不一致
    （SOT353 PD 250mW vs 450mW；V20 未列 SOT23-5 与 θJA；TOPR 记法不同）。
    保守处理：以 V20 的 250mW 作为该料号的硬边界，V24 作为"实际能力可能更好"
    的旁证；最终以 MICRONE 官方澄清或回件实测裁决，状态 `TO_VERIFY`。
  - 终审结论：换料方案经项目负责人 2026-08-30 采纳（初审 CONDITIONAL APPROVE → 三项
    整改 → 采纳），并指示将方法论教训沉淀为项目经验。已执行：ADR-005（替代料换料
    审核协议：θJA 结温法、结论精度、主张纪律、版本交叉核对）+ `docs/knowledge/
    IMPROVEMENT_SYSTEM.md` 新增"换料审核方法论教训"条目（按准入标准如实标注
    当前无可执行控制、不算完成经验积累）。
  - 仍待人工：全部改动 diff 审核、board_review 人工重签、commit/push 授权。

- 验证：
  - `py -3 gates\run_gates.py` → exit 1（诚实终态）：erc/drc/bom/delivery/intent/ops/
    schematic_semantics/learning 8 gate PASS；board_review FAIL 仅因
    `manufacturing_release=false` 等待人工重签（机器实测 8/8 pass）。
  - DRC：0 violation / 0 unconnected（换封装重布后收敛）。
  - `py -3 -m unittest discover -s tests` → 77/77 OK。
  - `py -3 gates\refresh_bom_stock.py` → PASS parts=14（C235316 库存 3329）。
  - `py -3 gates\export_delivery.py` → PASS rows=21 zip_entries=11。
  - `py -3 tools\generate_m2_ops.py` → PASS op_count=109。
  - `py -3 tools\board_review.py` → 8/8 pass（含 U3 重新纳入热源/极性/去耦检查）。
  - Evidence ID：EVID-20260830-001（见 docs/evidence/EVIDENCE_INDEX.md）。

- 新增第三方资源：
  - 无（本次使用的 jlcpcb CLI 属既有 RES-006；MICRONE ME6211C V20 数据手册属既有
    RES-007，已将其来源扩展至 ME6211C33R5G/C235316 变体）。

- 关联设计决策：
  - ADR-005（替代料换料审核协议：θJA 结温法、结论精度与主张纪律、数据手册版本交叉核对）。

- AIC Score Target：
  - 实现完成度与可验证效果（零库存失败关闭 → 受控换料 → 全链哈希重绑定的完整闭环）。

- Commit / PR：
  - 未提交（等待人工审核）；未创建 PR；未 push。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`

## AI-20260831-001

- 日期：2026-08-31
- 任务名称：开源吸收 Phase 1 -- CircuitBot clarify 深度 intake 与 Requirements Contract 设计稿
- 模块/路径：
  - `notes/open_source_intake/`（新增目录：README.md、circuitbot.md、requirements_contract_design_v1.md、策略文档归位副本、_circuitbot_repo/ 本地克隆）
  - `docs/HANDOFF.md`（本次会话状态更新）
  - `docs/compliance/AI_USAGE_LOG.md`（本条记录）

- AI 工具/平台：ZCode（GLM）
- 模型：GLM-5.3

- AI 参与类型：
  - [x] ADVISE
  - [ ] GENERATE_CODE
  - [ ] REFACTOR
  - [ ] DEBUG
  - [ ] GENERATE_TEST
  - [x] RESEARCH
  - [x] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 任务目标：
  - 按大统领 2026-08-30《AEDL 开源项目吸收与再设计策略》启动 Phase 1：对 CircuitBot 执行
    六步 Intake 协议（CLAIM/SOURCE/FAILURE/REUSABLE/TRANSFORM/VERIFY），并产出
    Requirements Contract（requirements_contract_v1.json + 第 10 门禁）的设计稿供人工评审。

- AI 实际产出：
  - 策略文档从 Downloads 归位至 `notes/open_source_intake/`（原违反工作台"文件不散落"规则）。
  - CircuitBot 源码级六步 Intake（commit ff9b003，MIT 已核实）：逐文件阅读 clarify 节点
    （297 行全文）、builder.py 图接线、analyze 节点自动注入逻辑、测试与 CI 覆盖。
  - 关键源码证据（策略文档 2.2 节预判的实证）：CircuitBot clarify 为 fail-open --
    `clarify_event.wait(timeout=300)` 超时后带原 prompt 继续设计；"No preference" 答案在
    `_build_enhanced_prompt` 中被静默丢弃；澄清结果仅存 LangGraph state 无 artifact/哈希；
    clarify 节点零测试覆盖。详见 `notes/open_source_intake/circuitbot.md` STEP 3。
  - 可复用清单：五维澄清框架、每问带选项交互、circuit_type 三分类守门（Adapt）；
    Q&A 拼回字符串、超时继续（Reject）；LangGraph 编排（Idea Only，暂不需要）。
  - Requirements Contract 设计稿 v1（未实装）：`requirements_contract_v1.json` schema
    （statement/requirement/question/assumption/forbidden 四层 + 自哈希 + intent 绑定）、
    requirements_contract_gate 七项确定性检查（C1-C7，含 blocking 未答即 FAIL、
    哈希失配即 FAIL、隐式假设 FAIL）、8 个测试 fixture 计划、M2 追溯两选项待拍板。
  - 全程未触碰代码、未触碰 M2 的 89 个未提交文件（与人工 M2 审核并行，工作树零干扰：
    本会话新增文件全部位于 notes/ 与台账，git status 中 notes/open_source_intake/ 与
    本条台账为新增）。

- 团队自主部分：
  - 项目负责人提供《开源项目吸收与再设计策略》文档并指令"接手"；并行推进方案
    （AI 做 Phase 1 只读研究、人工同步审 M2）经项目负责人选定。

- 人工修改：
  - 未报告额外人工修改。

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 待审：① circuitbot.md 六步 intake 结论与复用/拒绝清单；② requirements_contract
    设计稿（含 4 个决策点：M2 追溯 A/B、过期阈值、C6 关键字映射、实装时机）；
  - 红线遵守：本会话未生成任何代码，未触碰 board_review 签发状态。

- 验证：
  - CircuitBot 源码结论全部基于本地克隆（ff9b003）逐文件阅读，文件路径已在
    circuitbot.md 中逐条标注；无凭记忆断言。
  - 本会话无代码改动 -> 无测试运行（NOT_RUN 不适用：未触碰可执行物）。
  - `git status` 核对：新增仅 notes/open_source_intake/（含 _circuitbot_repo 克隆）、
    HANDOFF.md、本台账；既有 89 个 M2 未提交文件未被触碰。

- 新增第三方资源：
  - 暂无登记需求：CircuitBot 本轮仅作源码研究（读），未复制代码进 AEDL；本地克隆仅
    notes/ 下的研究素材。若后续实装包含其代码片段（关键词表等），届时按 AGENTS.md
    第 5 节登记 THIRD_PARTY_RESOURCES.md（RES 条目待生成时编号）。

- 关联设计决策：
  - 无新增 ADR（设计稿本身待人工评审，评审通过实装时再议是否立 ADR-006）。

- AIC Score Target：
  - 创新性与方案设计（Requirements Contract：澄清结果哈希绑定为 AEDL 差异化机制，
    依碰撞分析 §3 判定语言，尚需反证检索后才可写入正式主张）。

- Commit / PR：
  - 未提交（等待人工审核）；未创建 PR；未 push。
  - 注意：notes/open_source_intake/_circuitbot_repo/ 含完整 git 克隆（含 .git），提交前
    需人工决定是否入库（建议 .gitignore 排除或 subtree/子模块化，见 README.md 附属说明）。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`

## AI-20260831-002

- 日期：2026-08-31
- 任务名称：Requirements Contract 实装（第 10 门禁 + LLM 建议层 + M2 补录合同）+ 多 AI 协作基础设施
- 模块/路径：
  - `gates/requirements_contract.py`（新增：C1-C7 确定性校验 + 单向哈希绑定）
  - `gates/requirements_runtime.py`（新增：LLM 建议层，与合同层物理分离）
  - `gates/requirements/requirements_contract_v1.json`（新增：M2 补录合同，决策 A）
  - `src/hardware/m2-board/intent_v1.json`（新增 requirements_contract 引用字段）
  - `gates/run_gates.py`（第 10 门禁挂载，纯增量，不改既有 9 门禁逻辑）
  - `tests/test_requirements_contract.py`（新增：F1-F8 + runtime 层共 18 测试）
  - `tests/test_run_gates.py`（gate 集合断言更新 + 新门禁 fail-closed 断言）
  - `delivery/`（manifest 重导：intent 哈希变更连锁）
  - `docs/COLLABORATION.md`、`docs/api/requirements_api.md`（新增：多 AI 协作协议 + P2 前端接口契约）
  - `notes/open_source_intake/`（上一会话产物，本次继续维护）

- AI 工具/平台：ZCode（GLM）
- 模型：GLM-5.3

- AI 参与类型：
  - [x] ADVISE
  - [x] GENERATE_CODE
  - [x] DEBUG
  - [x] GENERATE_TEST
  - [x] DOCUMENT
  - [ ] REFACTOR

- 任务目标：
  - 项目负责人 2026-08-31 拍板四个决策点（M2 追溯选 A、阈值对齐 BOM 7 天、forbidden 用关键字匹配、实装启动），并新增三条指令：做 LLM 自动提问运行时、搭简易前端预留接口、把 CircuitBot 好东西纳入吸收路线。

- AI 实际产出：
  - 核心门禁：`gates/requirements_contract.py`，C1-C7 全部确定性检查。实装中发现并修复设计级缺陷：合同↔intent 双向哈希绑定是循环依赖（数学上无法同时满足），改为 lockfile 模式单向绑定（intent 持有 {sha256, path}，合同只声明 intent 路径）。
  - LLM 建议层：`gates/requirements_runtime.py`。架构上物理分离两层--建议层（parse_llm_proposal：LLM 输出解析为问题草案，answer 恒为 null，垃圾输入降级为 warning 永不抛异常，未知 kind 一律升为 blocking）与合同层（draft_contract 组装 + finalize 自哈希）。gate 永不调用 LLM。
  - 已知盲区诚实披露：C6 关键字匹配对"ESP32 载体但字面无 wifi"类间接命中靠 carrier 词条（esp32/esp8266/nrf24 归入 wireless），无法枚举所有载体；代码注释与 intake 报告均已标注。
  - M2 补录合同（决策 A）：依据 M2 真实会话记录补录（author 字段明确标注 retroactive 非设计时生成），5 条源语句/4 条已决需求/3 问 3 答（含 Wi-Fi 不需要的 blocking 决策）/3 条显式假设/2 条禁令（禁止静默加 Wi-Fi、禁止零库存自动换料）。
  - 交付链连锁处理：intent 加引用字段后哈希变更 -> 重跑 export_delivery.py 重导 manifest -> delivery gate 保持 PASS。
  - 第 10 门禁挂载：run_gates.py gates 列表纯追加一行；test_run_gates 的 gate 集合断言同步更新（9->10 属预期契约变更，非掩盖回归），并新增断言：空沙箱下 requirements_contract 必须 FAIL（缺文件=不可读证据，不是 skip）。
  - 多 AI 协作基础设施：docs/COLLABORATION.md（文件领地划分 + 交接规范 + 4 个任务卡）+ docs/api/requirements_api.md（P2 前端接口契约 + mock 数据）。
  - 修复两个实装 bug：draft_contract 的 resolved_requirements 参数丢失、C4 分支 reference 空指针。

- 团队自主部分：
  - 项目负责人拍板全部四个设计决策点（A/对齐/关键字/立即实装）与三条新指令；
  - 项目负责人决策启用多 AI 并行协作模式。

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 待审：① 合同↔intent 单向绑定的循环依赖修复方案；② M2 补录合同内容真实性（尤其 3 个问答是否与记忆一致）；③ 第 10 门禁挂载；④ COLLABORATION.md 协作协议。

- 验证：
  - `py -3 -m unittest tests.test_requirements_contract` -> 18/18 OK。
  - `py -3 -m unittest discover -s tests` -> 95/95 OK（含既有 77 + 新 18，test_run_gates 断言更新后全绿）。
  - `py -3 gates/run_gates.py` -> 10 gate：9 PASS + board_review FAIL（manufacturing_release=false 等待人工重签，与接手时 8/9 语义一致，零回归）。
  - `py -3 gates/export_delivery.py` -> PASS rows=21 zip_entries=11（intent 变更后重导）。
  - M2 真实合同对 gate 校验 -> PASS（sha256: 82c136df...）。

- 新增第三方资源：
  - 无（MIT 借思想重实现，未复制 CircuitBot 代码；关键词维度框架为 Adapt 思想借鉴，circuitbot.md STEP 4 已披露）。

- 关联设计决策：
  - 候选 ADR-006（单向哈希绑定 + 建议层/合同层分离）：待人工审核后正式立项。

- AIC Score Target：
  - 创新性与方案设计（fail-closed 需求合同门禁，反证检索完成后方可写入正式主张）。

- Commit / PR：
  - 未提交（与既有 89 文件一并等待人工统一审核提交）；未创建 PR；未 push。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`

## AI-20260831-003

- 日期：2026-08-31
- 任务名称：TASK-P2 简易前端（需求澄清工作台）
- 模块/路径（**全部在 `web/` 领地内新增**，未越界改他人文件）：
  - `web/index.html`（新增：5 步工作流页面结构）
  - `web/styles.css`（新增：浅色主题样式）
  - `web/sha256.js`（新增：纯 JS SHA-256，仅供 mock 传输层模拟服务端自哈希）
  - `web/canonical-json.js`（新增：复刻 Python canonical JSON 序列化）
  - `web/contract-builder.js`（新增：合同草稿组装，UI 与测试共用同一代码路径）
  - `web/mock-data.js`（新增：契约文档 Mock 数据原样照抄 + mock 端预检）
  - `web/api-client.js`（新增：mock / http 双传输层，5 个端点按契约定义）
  - `web/app.js`（新增：UI 逻辑）
  - `web/verify-hash.js`（新增：Node，校验 JS 自哈希与 Python 门禁一致）
  - `web/smoke-test.js`（新增：Node，无头闭环测试）
  - `web/e2e-browser.js`（新增：真实浏览器端到端驱动）
  - `web/README.md`（新增：运行、验证、契约缺口、诚实边界）
  - `docs/COLLABORATION.md`（仅按项目负责人指令标注 TASK-P2 卡片为 done）
  - `docs/compliance/AI_USAGE_LOG.md`（追加本条）

- AI 工具/平台：WorkBuddy
- 模型：Claude（WorkBuddy 内置）

- AI 参与类型：
  - [x] ADVISE
  - [x] GENERATE_CODE
  - [x] GENERATE_TEST
  - [x] DOCUMENT
  - [ ] REFACTOR
  - [ ] DEBUG

- 任务目标：
  - 项目负责人指令：先读 `AGENTS.md` 与 `docs/COLLABORATION.md`，提取领地划分与任务卡格式，
    据此认领任务（优先 TASK-P2，若已被认领/状态非"待领"/缺前置条件则改领 TASK-P3 并说明原因）；
    严格只在自己领地内改文件；接口契约以 `docs/api/requirements_api.md` 为唯一依据，
    发现契约缺失或矛盾时记录问题、不自行猜测定义；完成后在任务卡标注 done 并填写改动文件清单、
    关键实现说明、遗留问题；在 AI_USAGE_LOG 追加记录；全程**不执行任何 git commit**（含 add/push），
    保留全部改动为未提交状态以便人工复核。

- 认领判定（为什么是 P2 而不是 P3）：
  - 领卡时 TASK-P2 状态为「可立即领取」、属主「空缺」，`web/` 目录尚不存在（领地干净），
    且 `docs/HANDOFF.md` 并行会话状态中无任何会话认领 P2 → **满足前置条件，直接认领 TASK-P2**，
    未按备选方案改领 TASK-P3。

- AI 实际产出：
  - 契约「前端必须遵守的语义」四条逐条落地：① blocking 未答 → 「生成合同」按钮 disabled
    并显示「还剩 N 个必答问题」；② 下拉提供 `unknown` / `No preference`，但空答案永不许提交
    （nonblocking 同样要求显式选择，依据语义 #2「不许空着提交」）；③ 建议清单可增/删/改后才作答
    （问题文本、kind、dimension、选项均可编辑）；④ `errors[]` 原样渲染，不过滤、不改写、不排序。
  - 自哈希归属服务端：前端草稿不含 `contract_sha256`，只由 `/api/finalize` 写入。
    mock 传输层为支持离线闭环，用 `canonical-json.js` + `sha256.js` 复刻 Python 的
    `json.dumps(ensure_ascii=False, sort_keys=True, separators=(",",":"))` + sha256，
    并有交叉验证脚本保驾护航。
  - 字段裁剪：`open_questions` 恰好为 `{id, question, answer, kind, source_ids}`，
    故建议层的 `dimension`/`options`/`source` 不进合同（否则门禁判 unknown field）；
    `assumptions` 同理只保留 `{id, text, source_ids, status}`。已确认假设写入合同，
    剔除的假设不留痕（不伪造 "rejected" 状态）。
  - 零依赖：未引入任何框架、构建工具、CDN 资源。用普通 `<script>` 而非 ES module，
    因为 `file://` 协议下 module 会被 CORS 拦截。

- 团队自主部分：
  - 项目负责人制定多 AI 并行协作协议与领地划分（含 TASK-P2 领地 = `web/`）；
  - 项目负责人明确「契约文档为唯一依据、缺矛盾只记录不猜测」与「不 commit」两条硬约束；
  - P1（ZCode/GLM）提供 `docs/api/requirements_api.md` 契约与 mock 数据（本前端按此实现）。

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 待审：① 契约冲突 #1（intent_binding）由 P1 定案后前端需同步；② 请求体形状
    （propose/finalize/validate）三项待 P1 确认；③ 前端 UI 交互与文案。

- 验证（**全部实际运行，结果如实记录**）：
  - `node web/verify-hash.js` → `OK: JS digest matches the Python gate's digest for this contract`。
    对 `gates/requirements/requirements_contract_v1.json`（M2 真实合同，Python 门禁已 PASS，
    声明哈希 `82c136df…e5d8`）重算，JS 与 Python 得**完全一致**的摘要 `82c136dfe9da1e7f155d19165915d95e277d325744544460cbd98bb8b533e5d8`。
  - `node web/smoke-test.js` → `SMOKE TEST PASSED`。含 fail-closed 反例：
    2 个 blocking 留空 → 预检 fail 并各报一条错误。
  - 真实浏览器 `web/index.html?e2e=1` → `E2E PASSED (19/19)`。
    以 `chrome --headless=new --dump-dom` 复现，驱动真实 DOM 事件与按钮点击，
    断言覆盖：初始按钮禁用 → propose 渲染 3 题 → 未答计数 → 作答后启用 →
    finalize 出哈希 → validate PASS 且来源标注为 MOCK → 清空答案后重新禁用。
  - **权威门禁反验**：前端生成的合同送 `gates/requirements_contract.py`，
    `contract_sha256` 重算与声明**一致**；C1-C7 仅 1 条错误
    `contract intent_binding must contain exactly intent_path`（即遗留问题 #1）。
    把 `intent_binding` 改为 C4 要求的 `{intent_path}` 后**错误归零**，
    证明合同组装本身完全正确，该冲突是唯一阻塞项。
  - `node --check` 全部 8 个 JS 文件 → 语法通过。
  - NOT_RUN：真实 API 模式（`gates/requirements_runtime_server.py` 尚不存在，无服务端可连）。

- 新增第三方资源：
  - 无。零依赖、零 CDN；未复制任何第三方代码，SHA-256 为按 FIPS 180-4 自行实现。

- 关联设计决策：
  - 无新增 ADR（本任务为实现任务，未改变架构/接口/开源边界）。
  - 契约缺口与矛盾已记入 `docs/COLLABORATION.md` TASK-P2 卡片与 `web/README.md` 第 5 节。

- 已知限制（诚实边界）：
  - MOCK 模式下第 5 步的 `PASS` 是**前端本地预检**，只覆盖契约文档明文规定的规则，
    **不是** `gates/requirements_contract.py` 的 C1-C7，也不能替代它。UI 已显式标注来源。
  - 按契约文档生成的合同因遗留问题 #1，送真实门禁时 C4 必 FAIL。

- AIC Score Target：
  - NONE（本任务为工艺实现与验证，未产生新的比赛评分证据）。

- Commit / PR：
  - 未提交（遵守项目负责人指令：全程未执行 git add / commit / push）；
    未创建 PR；改动保留在工作树待人工统一审核。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`


---

## AI-20260831-004

- 日期：2026-08-31
- 任务名称：TASK-P3 开源 Intake Phase 2-3 —— KiCadAI 与 KiCad MCP 六步协议研究报告
- 模块/路径：
  - `notes/open_source_intake/kicadai.md`（新建，六步报告）
  - `notes/open_source_intake/kicad-mcp.md`（新建，六步报告）
  - `notes/open_source_intake/README.md`（目录状态与附属克隆说明更新）
  - `notes/open_source_intake/_kicadai_repo/`、`notes/open_source_intake/_kicad_mcp_repo/`（本地浅克隆审查用，含 .git，勿提交进 AEDL 仓库）
  - `docs/COLLABORATION.md`（TASK-P3 任务卡标注 done）
  - `docs/HANDOFF.md`（"并行会话状态"章节三行交接）
  - `docs/compliance/AI_USAGE_LOG.md`（本条记录）

- AI 工具/平台：ZCode（GLM）
- 模型：GLM-5.3

- AI 参与类型：
  - [x] RESEARCH
  - [x] DOCUMENT
  - [x] ADVISE

- 任务目标：
  - 按大统领指令领取 TASK-P3：以六步协议（CLAIM/SOURCE/FAILURE/REUSABLE/TRANSFORM/VERIFY）
    完成 KiCadAI 与 KiCad MCP 的开源 intake，参照 circuitbot.md 的格式与证据纪律；
    处理碰撞分析 §6 两条遗留未决项（KiCadAI 生成链路源码核实、kicad-ai 仓库真实性）。

- AI 实际产出：
  - **KiCadAI（dshills，MIT，HEAD `4f18765` 2026-08-24）源码级六步 intake**：
    - 已验证：capabilitygate 三态分类（supported/experimental/unsupported）+ Evidence 四状态
      + SHA-256 封印 + 仅 supported 才 FabricationReadyEligible；ERC/DRC 子进程链路
      （kicad_checks.go 的 fail-closed 语义 + ToolError 四分类）；kicadfiles 93 个 Go 文件
      的直接 writer + round-trip 验证；simmodel 纯 Go MNA 仿真引擎（solver/非线性/瞬态/热/电热）；
      824 测试文件 vs 809 源文件；capability-eval 系列 os.Exit(1)。
    - **碰撞分析校准（重要）**：2026-08-30 碰撞分析判"KiCad 生成、ERC/DRC subprocess、simulation
      未见源码调用链"经本轮本地克隆复核**判为误判**——上述全部有源码；误判原因与该分析 §5
      自我教训同型（当时工具抓不到仓库内容）。碰撞分析文件非本任务领地，未改动，校准对照
      写在 kicadai.md 附节，是否回写由人工决定。
    - 未核实边界如实标注：clarification 为 needs_clarification 单向拒绝状态而非交互回路；
      运行级 demo 数字 NOT_RUN；SOA 具体实现与夹具准确数字未审。
  - **KiCad MCP 家族 intake（深审 mixelpixx/KiCAD-MCP-Server，MIT，v2.7.0 `aa53d52`）**：
    - 定性：项目家族非单一仓库；策略文档 §3.2 能力清单是家族并集（pinmux 冲突检测在
      Seeed 版，本仓库无——否定性检索已验证）。
    - 已验证：DRC/ERC 的 kicad-cli 子进程实现与错误语义分级（退出码非 0=发现违规≠工具失败）；
      Freerouting DSN/SES 集成；JLCPCB 三通道（SQLite+FTS5 快照/OpenPlatform 实时/社区 API）
      及其官方文档自认的快照滞后；按日轮转日志；141 Python + 8 TS 测试。
    - 合规关键发现：其后继项目 **Konnect 为 AGPL-3.0**——AEDL 禁止吸收，已写入报告红线。
    - STEP 3 素材：其 README/KNOWN_ISSUES 诚实披露的文件损坏级事故史（add_symbol_property
      丢闭括号、S-expr 转义不对称、SWIG C++ 所有权崩溃、响应错位）。
  - **遗留未决项更新**：amcolex/kicad-ai 本轮 WebFetch 取得 GitHub 404 渲染页（非网络故障），
    现有证据一致指向该 URL 当前无公开仓库；"从未存在"强结论维持待人工浏览器定案。
  - **吸收建议（供人工决策，未实装）**：近期可落地两项——KiCadAI 的 RecordedProvider 录制
    回放模式用于 requirements_runtime LLM 层确定性测试；KiCad MCP 的 FTS5 连字符 MPN 教训
    转化为 AEDL 器件匹配对抗性 fixture。中期候选：capability preflight 机制（Adapt）。
  - 未触碰 AEDL 任何代码/门禁/共享只读区；未动 .gitignore（克隆目录排除待人工确认）。

- 团队自主部分：
  - 大统领指令领取 TASK-P3、指定参照 circuitbot.md 证据纪律、要求完成后标注任务卡并
    留痕、不 commit。

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 待审：① 两份 intake 报告的结论与证据标记；② 碰撞分析校准结论（含 KiCadAI 威胁等级
    升级建议）是否回写碰撞分析文件；③ 两个本地克隆目录的处置（建议 .gitignore 排除）；
    ④ Konnect AGPL 红线的执行确认。

- 验证：
  - 源码级：所有"已验证"结论均直接读自本地克隆文件（路径写入报告）；否定性结论
    （如 mixelpixx 无 pinmux 检测）经全仓检索；本人中途一次否定性误判（simmodel 无 MNA，
    系检索 glob 写法错误）已在会话内自我纠正并如实记录于报告措辞。
  - 运行级：KiCadAI 的 `make public-demo` / `public-demo-refusal` / `go test` 均 NOT_RUN
    （需 Go 1.23 + KiCad 10.0.3 环境）；AEDL 侧测试未运行（零代码改动，无影响面）。

- 新增第三方资源：
  - 无融合性使用、零代码复制，THIRD_PARTY_RESOURCES.md 无新增登记项；两个克隆仅为
    审查证据暂存（研究结果引用，非运行时依赖）。

- 关联设计决策：
  - 无新 ADR（纯研究；capability preflight 若 M3 立项再提）。

- AIC Score Target：
  - NONE（纯研究任务，未实装机制、未更新评分资产；产出为后续设计输入）。

- Commit / PR：
  - 未提交（遵守协作协议：不 commit，由大统领统一审核提交）；未创建 PR；未 push。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`


## AI-20260831-005

- 日期：2026-08-31
- 任务名称：补 requirements runtime HTTP 服务器（P2 前端真实 API 模式的集成缺口）
- 模块/路径：
  - `gates/requirements_runtime_server.py`（新增：零依赖 HTTP 壳，五端点）
  - 无其他文件改动（仅新增本文件 + 本条台账）

- AI 工具/平台：ZCode（GLM）
- 模型：GLM-5.3

- AI 参与类型：
  - [x] GENERATE_CODE
  - [x] DEBUG
  - [x] ADVISE

- 任务目标：
  - 并行 AI-003（P2 前端）台账明确标注"P1 的 runtime server 尚未提供，真实 API 模式请求失败是预期行为"；
    本会话核查后发现此缺口系 P1 侧遗漏（API 契约文档承诺了 HTTP 服务但只交付了纯函数层），补上
    契约承诺的 HTTP 壳，使前端"真实 API"模式可联调。

- AI 实际产出：
  - `gates/requirements_runtime_server.py`：标准库 http.server 实现五端点
    POST /api/propose、GET /api/contract、POST /api/answer、POST /api/finalize、POST /api/validate，
    响应形状与 web/api-client.js HttpTransport 逐字段对齐。
  - 设计要点：自哈希只在服务端写入（浏览器草稿永不含 contract_sha256，与 mock 传输层一致）；
    LLM 建议是可插拔 hook，无 hook 时返回启发式草案并明确标注 source=fallback-heuristic +
    warning，绝不伪装成 LLM 产物。
  - 联调发现并修复一个诚实性 bug：初版把启发式草案误路由进 parse_llm_proposal，导致
    source 被覆盖为 "llm_proposal" 且 warning 丢失（fallback 伪装成 LLM）；修复为无 hook 时
    直接返回启发式最终结构。
  - 验证：进程内五端点 + 真实 HTTP 端到端（propose/contract 404/answer/finalize 写哈希/validate）
    全部通过；前端 mock 模式 smoke-test 此前已 PASSED（并行 AI-003 交付）。

- 团队自主部分：
  - 项目负责人指令多 AI 并行协作；本缺口由本会话主动核查并行产物时发现并闭环。

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 待审：runtime server 是否纳入正式交付范围；LLM propose hook 的接入方式（当前无凭据，
    启发式 fallback 已可跑通全流程）。

- 验证：
  - `py -3` 进程内联调：propose/finalize/validate 逻辑通过；source/warnings 修复后复核通过。
  - 真实 HTTP：curl 五端点（propose 返回 5 问+假设+warnings；contract 未生成返回 404；
    answer 返回未答 blocking；finalize 写入 sha256；validate 返回 {status, errors}）。
  - 前端 mock 模式 smoke-test：PASSED（并行 AI-003 交付，本会话复跑确认）。

- 新增第三方资源：无（标准库 http.server）。

- 关联设计决策：无新增 ADR。

- AIC Score Target：
  - 实现完成度与可验证效果（需求澄清工作台前端+后端全链路可跑）。

- Commit / PR：
  - 未提交（与其余改动一并等待人工统一审核提交）。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`


## AI-20260831-006

- 日期：2026-08-31
- 任务名称：C 方案——intent 语义哈希绑定（堵"改电路不重签合同"缺口）
- 模块/路径：
  - `gates/requirements_contract.py`（新增 `INTENT_SEMANTIC_FIELDS` / `INTENT_BINDING_FIELDS` / `intent_semantic_sha256()`；C4 扩展语义锁检查）
  - `gates/requirements_runtime.py`（`draft_contract` 新增必填参数 `intent_semantic_sha256`）
  - `gates/requirements/requirements_contract_v1.json`（M2 重签：写入语义哈希 + 重算自哈希）
  - `tests/test_requirements_contract.py`（新增 `IntentSemanticBindingTests` 13 用例；既有用例同步新 binding 形状）
  - `docs/api/requirements_api.md`（新增「intent_binding 语义哈希范围」章节 + finalize 说明）
  - **跨领地单行改动**：`src/hardware/m2-board/intent_v1.json`（lockfile 引用重指新合同哈希；`src/` 为共享只读区，依据大统领验收标准"run_gates 的 requirements_contract 仍 PASS"的必然级联）
  - **级联重导**：`delivery/`（`gates/export_delivery.py` 重跑，manifest/gerbers/zip/CPL 全部刷新，哈希绑定复核一致）
  - P2 领地连带同步：`web/index.html`（移除过期的 intent_sha256 冲突提示，改为语义哈希说明）、`web/README.md`（缺口 #1 标记已解决 + 新增 mock 语义哈希限制）
  - `docs/COLLABORATION.md`（新增 TASK-P5 卡片）、`docs/HANDOFF.md`（本会话小节）、本条

- AI 工具/平台：WorkBuddy
- 模型：Claude

- AI 参与类型：
  - [x] ADVISE
  - [x] GENERATE_CODE
  - [x] GENERATE_TEST
  - [x] DEBUG
  - [x] DOCUMENT
  - [ ] REFACTOR

- 任务目标（大统领直接指派）：
  - 已实测确认缺口：单向 lockfile 绑定下，往 intent 塞 U9 电阻、保留旧合同引用，gate 仍 PASS。
  - C 方案：合同记录 intent 的「语义字段哈希」，改电路必须重签合同。

- AI 实际产出：
  - 白名单**写死在代码注释**（`INTENT_SEMANTIC_FIELDS = ("components", "nets")`），并写明双向维护约定：intent 协议新增电路语义字段必须跟白名单；往白名单加字段=所有已签合同一次性作废。
  - `intent_semantic_sha256(intent)`：白名单两字段的 canonical JSON（`ensure_ascii=False, sort_keys=True, separators=(",",":")`）sha256。缺失字段按 `null` 参与不跳过。
  - `intent_binding` 扩为恰好 `{"intent_path", "intent_semantic_sha256"}`；旧单字段形状被拒（fail-closed，不静默放过）。
  - C4 语义锁：`合同声明 != 当前 intent 语义哈希` → `intent 语义内容已变更，须重签合同`。
  - 严格未引入双向哈希：语义哈希只依赖 intent 的 components/nets，不碰合同内容；`requirements_contract` 绑定字段本身明确排除（否则重新形成循环依赖）。
  - M2 重签走**署名路径**（`finalize_contract`/`write_contract`，"谁算的哈希"可审计）；intent 引用用字节级精准替换（保留 1 空格缩进/LF/无 BOM 原格式，旧哈希恰好出现 1 次）。

- 团队自主部分：
  - 大统领指派 C 方案、定义语义白名单（components+nets）、给出验收标准与禁止项；
  - ZCode/GLM（P1）此前的 lockfile 单向绑定设计与 runtime_server 是本方案的基础。

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 待审：① 语义白名单与维护约定；② M2 重签内容与跨领地单行改动（intent 重指）；③ delivery 重导产物；
    ④ **P1 领地连带缺口**：`requirements_runtime_server.py::finalize` 未写 `intent_semantic_sha256`（见下"已知限制"）。

- 验证（全部真实运行，结果如实记录）：
  - **原缺口复现→堵住**：用真实 M2 合同+intent 副本实测，塞 U9 电阻不重签 → `intent 语义内容已变更，须重签合同` FAIL；换料 U3 value 不重签 → FAIL；删器件 → FAIL；改 nets → FAIL。
  - **不该失效的不失效**：只重指绑定（电路不变，合同重签）→ PASS；只改 `protocol_version` → PASS；
    绑定字段被故意指错 → 只报 lockfile 错误，**不**报语义错误（证明绑定字段确实不在语义哈希内，无循环）。
  - `py -3 -m unittest tests.test_requirements_contract` → **31/31 OK**（18 既有 + 13 新增；期间修掉本会话自己新用例的一个真 bug：重签用例里语义哈希取自改后 intent、落盘的却是不含改动的 intent）。
  - 全量回归 `python -S -m unittest discover -s tests` → **114/114 OK**（含其他会话新增用例，零回归）。
  - `python -S gates/run_gates.py` → 10 门禁：**9 PASS + board_review FAIL**（仍仅为 `manufacturing_release=false` 等人工重签，与接手时语义一致）；`requirements_contract` gate **PASS**，新自哈希 `f0fec3f860e6ca7d…be648d8`。
  - `gates/export_delivery.py` → manifest 4 个 source（board/intent/bom/bom_stock_evidence）哈希逐一复核与磁盘一致。
  - web/ 三项验证重跑：`verify-hash.js` OK、`smoke-test.js` PASSED、浏览器 E2E **19/19**。

- 新增第三方资源：
  - 无（纯标准库；无新依赖）。

- 关联设计决策：
  - 建议候选 ADR-007：intent 语义哈希绑定（白名单 + 单向 + 重签语义）。是否立项待人工审。

- 已知限制（诚实边界）：
  - **P1 领地连带缺口，本会话未改**：`gates/requirements_runtime_server.py::finalize`（L128-136）只写 `contract_sha256` 不写 `intent_semantic_sha256`，已实测其产物被 C4 拒收（`intent_binding must contain exactly …` + `malformed`）。修法已写入 TASK-P5 卡片，交 P1。
  - **MOCK 前端限制**：mock 传输层无 intent 可读、无法替服务端算语义哈希，故 MOCK 模式生成的合同不含该字段、送真实门禁 C4 必 FAIL（UI 与 README 已明示，非 bug）。
  - 本会话环境（WorkBuddy sitecustomize safe-delete 钩子）拦截 `unlink`/`rmtree`，`run_gates.py`/`export_delivery.py` 需 `python -S` 运行或人工终端执行；非仓库代码问题。
  - NOT_RUN：`requirements_runtime_server.py` 的 HTTP 端到端联调（属 P1 领地且其 finalize 待修）。

- AIC Score Target：
  - 创新性与方案设计（合同↔intent 语义锁；主张成立需 Evidence 支撑，暂不下正式结论）。

- Commit / PR：
  - 未提交（遵守协作协议：全程未执行 git add/commit/push）；未创建 PR；改动保留在工作树待人工统一审核。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`

## AI-20260831-007

- 日期：2026-08-31
- 任务名称：① M2 目检渲染证据门禁（sha256 绑定 PCB）；② TASK-FIX-D1：D1 LED 极性反接修复与全链重放
- 模块/路径：
  - `tools/board_review.py`、`gates/gate_core.py`、`gates/run_gates.py`、`tests/test_board_review.py`（渲染证据）
  - `src/hardware/m2-board/intent_v1.json`、`m2_board.kicad_sch`、`m2_board.kicad_pcb`（D1 极性）
  - `gates/requirements/requirements_contract_v1.json`（重签）、`tools/generate_m2_ops.py`（lockfile 泄漏修复）
  - `notes/m2-evidence-reset/generated/`（级联重导证据）、`delivery/`（重导交付包）

- AI 工具/平台：Qoder
- 模型：`UNKNOWN`（当前会话未暴露可核验的精确模型 ID）

- AI 参与类型：
  - [ ] ADVISE
  - [x] GENERATE_CODE
  - [ ] REFACTOR
  - [x] DEBUG
  - [x] GENERATE_TEST
  - [ ] RESEARCH
  - [x] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 做了什么：
  - **渲染证据门禁**（背景：2026-08-31 过期手工渲染图导致多模态目检误报，PIT-20260830-001 第二次应验的同类缺口）：
    `tools/board_review.py` 用 kicad-cli 脚本化重渲 top/bottom 目检图并写顶层 `render_evidence`
    （pcb_sha256/top_png_sha256/bottom_png_sha256/rendered_at，纯内容寻址，无 mtime）；
    `gate_core.validate_render_evidence` fail-closed 校验；`run_gates` 的 board_review 门禁经
    `_meta.auto_evidence` 指针接入。6 个新单测覆盖缺字段/缺图/PCB 失配/PNG 失配。
  - **TASK-FIX-D1**：按 `docs/TASK_FIX_D1.md` 修复 D1（LED）极性反接：
    - intent：`LED_A=[R4.2, D1.2]`、`GND` 含 `D1.1`（`LED_DRV` 不动）；
    - 原理图：D1 两脚网标对调（pin1→GND、pin2→LED_A）；
    - PCB：**偏离任务书字面做法**——任务书要求"只交换 pad 的 `(net ...)` 属性"，但实测铜皮物理连接是
      pad1↔R4.2 侧铜皮、pad2↔GND 铜皮，只换标签会造成铜皮-网络冲突且 LED 物理上仍反接。
      实际做法：D1 footprint 原地旋转 180°（`(at 44 26)`→`(at 44 26 180)`），pad1 落到 GND 铜皮、
      pad2 落到 LED_A 铜皮，同时交换两 pad 网络属性。走线/过孔零改动，阴极丝印标记随封装一起转到正确侧。
  - **级联重导**：`generate_m2_ops.py` 重放 ops（109 条，`GND at D1.1`+`LED_A at D1.2` 已验证）；
    需求合同重签（语义哈希 `82f8aa2f…02c34`，合同自哈希 `a315effe…7eab0`，intent lockfile 同步）；
    `export_delivery.py` 重导（rows=21 zip_entries=11）；`run_gates.py` 全链重跑（网表/ERC/DRC/语义/故障注入/学习）；
    `tools/board_review.py` 重渲染刷新 render_evidence。
  - **顺带修复（阻塞级联，必须做）**：`tools/generate_m2_ops.py::split_akcli_intent` 会把 P5 任务新增的
    `requirements_contract` lockfile 字段透传给 akcli，被其严格 schema 拒绝（BAD_CONFIG），导致 ops 无法重放。
    改为白名单透传（protocol_version/components/nets/layout/mode）。3 个既有用例不回归。

- 团队自主部分：
  - 大统领下达 TASK_FIX_D1.md 任务书、证据链（polarity-verification.md）与验收标准；
  - PCB 旋转 180° 替代"只换标签"是本会话基于铜皮连通性分析的自主判断（已在上方显式标注偏离）。

- 人工审核：
  - 状态：`PENDING_HUMAN_REVIEW`
  - 待审：① PCB 旋转方案（与任务书字面不同，需人工确认物理正确性）；② generate_m2_ops.py 白名单修复；
    ③ 需求合同重签内容；④ 渲染证据门禁实现（已随 4e0922a 提交）。

- 验证（全部真实运行，结果如实记录）：
  - 三层一致性：intent `LED_A=[R4.2,D1.2]`/`GND` 含 `D1.1`；新导网表 `D1 pin=1 pinfunction=K_1 → /GND`、
    `D1 pin=2 pinfunction=A_2 → /LED_A`；PCB pad1(net GND)/pad2(net LED_A)。
  - `py -3 -m unittest discover -s tests` → **114/114 OK**（零失败；本会话早前该套件有 1 个
    test_requirements_contract 失败，属并行会话遗留，现已随工作树现状全绿）。
  - `py -3 gates/run_gates.py` → 10 门禁：**9 PASS + board_review FAIL**；board_review 唯一错误
    `manufacturing_release is false`（等人工重签的诚实终态，非回归）。渲染证据门禁曾正确抓到
    重渲前的 pcb_sha256 失配（fail-closed 生效），重渲后消除。
  - `tests.test_board_review` 9/9、`tests.test_generate_m2_ops` 3/3 单独复跑通过。
  - `export_delivery.py` → `PASS rows=21 zip_entries=11`。
  - 篡改演练（渲染证据）：改 PCB 不重渲 → board_review 报 `render_evidence pcb_sha256 does not match`；
    恢复后消除（本任务中该机制再次真实触发并被重渲合法消除）。

- 新增第三方资源：无（KiCad 10.0.5 kicad-cli、akcli 0.21.0 为既有登记资源）。

- 已知限制（诚实边界）：
  - **rev2 修订（人工复核采纳）**：`polarity-verification.md` 已按独立复核意见修订 4 处——
    ①"ERC 强制"改为 pin↔pad 编号映射机制；②删除"3.3V 不损坏"死结论（须按 KENTO KT-0603R
    数据手册反向耐压判定）；③U2 pin7 更正为 R（datasheet 要求接 VSS，已与官方符号交叉核对）；
    ④删除"改符号方向可修复"与"镜像翻转"错误表述（符号旋转/镜像不改变 pin→net 映射）。
  - **不声称"LED 现在能亮"**：极性网络已按符号定义在数据级修正且三层一致，但电气功能正确性
    属回件 C 级实测范畴（任务书 §六明令）。
  - 本会话的渲染证据提交 `4e0922a` 的 AI ID 标签误写为 `[AI-20260831-001]`，与本台账 001（P1 会话）
    撞号；该工作实际对应本条 007。不改写已有提交，留人工审核时知悉。
  - 共享工作树有并行会话改动（docs/、lessons 等），本会话只动了上述清单文件；提交时请人工按清单甄别。
  - 防再犯项（任务书 §四：LED_POLARITY 语义契约规则 + 负向故障注入夹具）本轮**未做**，留待下轮。

- AIC Score Target：
  - NONE（内部质量修复；渲染证据门禁若被认定为可复用机制可在后续 Evidence 中另行关联）。

- Commit / PR：
  - 渲染证据部分已提交：`4e0922a`（分支 fix/m2-schematic-semantic-release）；
  - D1 修复及级联产物**未提交**（遵守任务书"不 commit"铁律），留人工统一审核。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`

## AI-20260831-008

- 日期：2026-08-31
- 任务名称：外部 datasheet 真值层落地——证据包核实 + DATASHEET_CONTRACT 第 11 门禁
- 模块/路径：
  - `src/hardware/m2-board/evidence/`（新建：`datasheet_manifest.json`、`contracts/m2_component_contracts.json`、`datasheets/` 三份冻结 PDF）
  - `gates/datasheet_contract.py`（新）、`gates/run_gates.py`（挂载）、`tests/test_datasheet_contract.py`（新）、`tests/test_run_gates.py`（11 门禁断言）

- AI 工具/平台：Qoder
- 模型：`UNKNOWN`（当前会话未暴露可核验的精确模型 ID）

- AI 参与类型：
  - [ ] ADVISE
  - [x] GENERATE_CODE
  - [ ] REFACTOR
  - [ ] DEBUG
  - [x] GENERATE_TEST
  - [x] RESEARCH
  - [ ] DOCUMENT
  - [ ] BENCHMARK
  - [ ] MEDIA

- 做了什么：
  - 对外部证据包（M2_datasheet_evidence_pack）逐项核实，发现并记录三处出入：
    ① 包内 `datasheets/`、`reference_designs/` 为空，PDF 只有链接；
    ② 包内 D1/J1 视图过期（MPN 标 null），实际仓库 BOM 已绑定 D1=KENTO KT-0603R（C2286）、J1=Hropart TYPE-C-31-M-12（C165948），manifest 已按 BOM 真值修正；
    ③ U3"400mA@SOT353"声明仅见于外部复核引用的 V20；本环境只取到 V14 镜像（stm32-base.org），V14 无按封装电流表、features 写 500mA@VIN=4.3V——两版冲突，已写入合同 `fact_verification` 且保持 BLOCK，须人工按最终版 datasheet 定案。
  - 下载并冻结三份资料（均记录 sha256+retrieved_at）：U1 ESP32-C3-WROOM-02 官方 datasheet（2375b1be…）、U2 Sensirion SHT3x-DIS 官方 datasheet（095b1853…）、U3 ME6211 V14 镜像（7e33d665…，已逐页核对：SOT353 Pd absmax=250mW 成立）。
  - 实现 `gates/datasheet_contract.py`（DS0 MPN 绑定对 BOM 精确匹配 / DS1 本地冻结副本 sha256 / DS2 pin→net 断言对 intent / DS3 BLOCK_UNTIL_REVIEWED 需已签复核证据 / DS4-6 每项 required_checks 需 verified check_evidence），fail-closed；作为第 11 门禁挂载进 `run_gates.py`。
  - D1/J1 datasheet 本环境取不到（LCSC 直链 TLS 拦截、elecfans 仅得查看页），保持 BLOCK，已在 manifest/HANDOFF 标注由人工下载补齐。

- 验证（全部真实运行）：
  - `tests.test_datasheet_contract` 9/9 OK（含 fail-closed 各分支）。
  - 全量回归 123/123 OK（114 既有 + 9 新增）。
  - `py -3 gates/run_gates.py` → 原 9 门禁全 PASS；board_review 仅余 `manufacturing_release=false`；
    datasheet_contract FAIL 且如实列出 34 项 BLOCK（U1/U2/U3 各项 check_evidence 未签、U3 电源复核未做、
    D1/J1 无本地 datasheet 副本）。DS2 断言对修复后的 D1 网络零报错（证明三层修复与合同一致）。

- 已知限制（诚实边界）：
  - U3 输出电流按封装的权威数值未定案（V14/V20 冲突），在定案前电源结论保持 BLOCK；
    5V→3.3V 压差 1.7V×150mA≈255mW 已触及 SOT-353 250mW absmax（absmax 不是工作点），
    热复核或换 ≥1A 级 3.3V 电源方案（正式选型流程）前不得放行。
  - D1 反向耐压未知（datasheet 缺失），不声称反偏安全。
  - U1/U2 的 datasheet 级 check（ESR/strapping/天线净空的 datasheet 依据、SHT30 清洗/回流要求等）
    均需工程师对照已冻结 PDF 逐项签发后，门禁才会转绿——机器不代签。

- AIC Score Target：
  - 创新性与方案设计（datasheet 外部真值层：验证从"生成物互洽"扩展到"生成物与物理世界一致"；是否立项待人工审）。

- Commit / PR：
  - 未提交（遵守协作协议），留人工统一审核。

- 最终状态：
  - `PENDING_HUMAN_REVIEW`

## AI-20260831-009

- 日期：2026-08-31
- 任务名称：证据冻结 + check_evidence 状态机升级（人工裁决落地）
- 模块/路径：
  - `src/hardware/m2-board/evidence/datasheets/D1_KT-0603R/KT-0603R_KENTO_approval_spec_revA0.pdf`（新：人工提供原件，机器冻结，sha256 a3bac1cc…d4a1）
  - `src/hardware/m2-board/evidence/datasheet_manifest.json`（D1 冻结+6 项机器预检/待签记录；J1 EVIDENCE_FOUND_NOT_FROZEN；U3 BLOCKED_POWER_THERMAL + 人工裁决）
  - `src/hardware/m2-board/evidence/contracts/m2_component_contracts.json`（U3 400mA 裁决 + 路线 B 建议）
  - `gates/datasheet_contract.py`（状态机：verified/decision/signed_by 三要素分离，机器最高 machine_prechecked 不得代签）
  - `tests/test_datasheet_contract.py`（13 用例）
  - `notes/m2-evidence-reset/polarity-verification.md`（rev3）

- AI 参与类型：GENERATE_CODE / GENERATE_TEST / RESEARCH

- 做了什么：
  - 核实并冻结人工提供的 KT-0603R 承认书（Rev A.0，2018-12-06）：逐条对照
    Pd 40mW / IFP 60mA / IF(DC) 25mA / VR 5V / IR≤5µA@5V / VF 1.8-2.4V@20mA / 回流 260C 10s，全部一致。
  - 按人工裁决冻结 U3 结论：ME6211C33R5G/SOT-353 按 400mA（V20 按封装表优先于分销商 500mA 字段）；
    V20 原件本环境未冻结（TLS 拦截），记录为人工声明待原件补签；θJA 缺失禁止代签，
    热适用性保持 BLOCKED，人工倾向路线 B（正式 ECO/ADR 换 >=1A 级 3.3V 方案，换料前不改 BOM）。
  - TYPE-C-31-M-12：HRO 官方页与 elecfans 镜像已定位（8.94x7.35x3.16mm/16-pin/20V5A/0.5mm pitch），
    本环境无法冻结原始 PDF，状态 EVIDENCE_FOUND_NOT_FROZEN，须人工下载冻结；
    明确不得因『用了 KiCad 官方 footprint』自动签 mechanical PASS（同名仿制件风险）。
  - 门禁升级：check_evidence 状态机 missing→evidence_found→machine_prechecked→awaiting_engineer
    →verified|rejected；转绿三要素 = status:verified + decision:pass + signed_by:human；
    verified 无签名（含 agent 自签/旧格式）→ 拒；decision:blocked（人签）→ DESIGN-BLOCK 独立呈现；
    blocked 未签 → 待工程师签阻塞决定。

- 验证（全部真实运行）：
  - `tests.test_datasheet_contract` 13/13 OK（含：agent 自签被拒、旧格式无签名被拒、
    DESIGN-BLOCK 呈现、machine_prechecked 仍是 unsigned）。
  - 全量回归 127/127 OK。
  - `py -3 gates/run_gates.py` → 原 9 门禁全 PASS；board_review 仅余 manufacturing_release=false；
    datasheet_contract 33 项：1×DS1（J1 无冻结副本）、1×DS3（U3 电源合同无已签复核记录）、
    24×各项无记录（U1/U2/U3 待工程师逐项对 PDF 签发）、6×unsigned（D1 机器预检/待签）、
    1×unsigned-design-block（U3 thermal）。DS0/DS2 零报错（MPN 绑定与 D1 网络断言全对）。

- 已知限制：
  - V20 原件、TYPE-C-31-M-12 原始 drawing 均未冻结，须人工下载后补录
    （manifest documents 字段已留位，含 source_url；补录时记录 sha256+retrieved_at 并重跑门禁）。
  - 34 项（现 33 项）签发一律人工逐条，机器不代签、不批量绿灯。

- AIC Score Target：创新性与方案设计（『外部真值层 + 人机签发分离』机制成形；立项与否待人工审）。

- Commit / PR：未提交（协作协议）。

- 最终状态：`PENDING_HUMAN_REVIEW`

## AI-20260831-010

- 日期：2026-08-31
- 任务名称：补取并冻结两份原件——ME6211 V20 原件 + TYPE-C-31-M-12 mechanical drawing
- 模块/路径：
  - `src/hardware/m2-board/evidence/datasheets/U3_ME6211C33R5G/ME6211_V20_lcsc_official.pdf`（新：865046 B，sha256 23084e9d…fae5e6）
  - `src/hardware/m2-board/evidence/datasheets/J1_TYPE-C-31-M-12/TYPE-C-31-M-12_drawing_elecfans_mirror.pdf`（新：118108 B，sha256 ef0e00dd…0294b）
  - `datasheet_manifest.json`、`contracts/m2_component_contracts.json`（同步更新）

- 做了什么：
  - V20 原件经 LCSC 直链取到（上一轮 TLS 拦截为瞬态），逐页核对为真：
    p9『ME6211C33 (SOT343R, FBP1*1-4L, SOT353)』I_OUTMAX=400mA（同页标准封装表 500mA），
    p5 Absolute Maximum Ratings SOT353 Pd=250mW——人工裁决的 400mA 获得冻结原件一手背书，
    合同 fact_verification 升级为 verified_locally_from_frozen_original。
  - TYPE-C drawing 从 elecfans 镜像页提取到 huaqiu CDN 原始 PDF（1 页工程图：16-pin、0.5mm pitch、
    20V、-30~+80C、280C/10s、PCB EDGE + RECOMMEND P.C.B LAYOUT）。
  - **发现并如实记录出处疑点**：该图纸水印/标题栏为 HIROSE，与 BOM 制造商 Korean Hroparts Elec（HRO）
    不一致——疑似仿制厂文档或镜像站误标，正是此前预警的同名仿制风险。已冻结但标
    FROZEN_PROVENANCE_QUESTIONABLE，只可作几何参考，签发必须取得 HRO 官方图纸。

- 验证：门禁重跑——原 9 门禁全 PASS；board_review 仅余 manufacturing_release=false；
  datasheet_contract 33→32 项（DS1 清零：两份冻结副本均过 sha256；其余 32 项全部为待人工签发类别）。

- 已知限制：HIROSE 水印疑点未消；Espressif 供电建议仍为 URL-only。其余同 009。

- Commit / PR：未提交（协作协议）。

- 最终状态：`PENDING_HUMAN_REVIEW`

## AI-20260831-011

- 日期：2026-08-31
- 任务名称：信息架构治理落地（TASK-INFO：HANDOFF 状态卡 + ID_MAP + RAG 决策记录）
- 模块/路径：
  - `docs/HANDOFF.md`（重构：顶部新增 ≤15 行项目状态卡；并行会话历史小节原位划入"归档区"，零删改）
  - `docs/ID_MAP.md`（新：6 类 ID 体系真源表 + 按任务类型的按需加载路由）
  - `docs/knowledge/RAG_DECISION.md`（新：暂不引入 RAG 的决策记录 + 4 条重启触发条件 + 不立 ADR 判定）
  - 本台账（本条）

- 做了什么：
  - 核实发现 TASK-INFO 任务书（`docs/TASK_INFO_ARCHITECTURE.md`）此前仅写出、未被执行
    （ID_MAP/RAG_DECISION 不存在，HANDOFF 无状态卡），本会话直接执行。
  - HANDOFF 重构采用"纯插入"策略：状态卡与归档区标题为仅有的新增内容，旧 187 行
    全部原位保留（脚本验证：旧文件每行均存在于新文件，丢失 0 行，187→204 行）。
  - 状态卡全部字段实测取得：11 门禁 9 PASS + board_review FAIL + datasheet_contract
    32 BLOCK（读 `notes/m2-evidence-reset/run_manifest.json`）；127/127 测试实测；
    HEAD `e51fa93` 与 origin 同步（`git rev-parse` 双端核对）。
  - ID_MAP 六类 ID 格式逐个与真源核对：AI 台账（最高 010，本条 011）、ADR-001~005
    （DECISIONS.md grep 确认）、EVID/RES/PIT/TASK-PN 各抽 1-3 个在真源命中。
  - RAG 决策：依据 14 万 token 规模 + ID 精确检索 + datasheet sha256 绑定三条理由判
    暂不引入；ADR 判定按 AGENTS.md §6 清单核对后不立项，留人工复核。

- 验证：HANDOFF 零丢失脚本验证通过；ID_MAP 抽查 ID 全部在真源 grep 命中；
  未触碰其他会话未提交文件（gates/datasheet_contract.py 等仅备份对照，未修改）。

- 已知限制：状态卡中"待大统领"事项随进展会过期，接手会话更新状态卡时须逐项重测，
  不得沿用本条数字。

- Commit / PR：未提交（协作协议，与第 11 门禁批次一并待人工决定）。

- 最终状态：`PENDING_HUMAN_REVIEW`
