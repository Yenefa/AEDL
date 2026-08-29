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
