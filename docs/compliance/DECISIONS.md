# Engineering Decisions

> 关键工程与治理决策使用 `ADR-NNN`。状态只表示决策是否采用，不等于人工审核台账已经完成。

## ADR-001 — 项目内单一规范真源与多入口发现

- 日期：2026-08-29
- 状态：Superseded by ADR-002

- 问题：
  - AEDL v1.0 原文位于下载目录，后续 AI 不一定能发现；只在单次对话中说明也无法形成持续、可审计的项目约束。

- 候选方案：
  1. 只把简版规则追加到 `AGENTS.md`。
  2. 为每一种 AI 工具复制一套完整规则。
  3. 把完整规范复制进项目作为单一真源，在 `AGENTS.md` 强制执行，并由 README/HANDOFF 提供冗余入口。

- 决策：
  - 采用方案 3。

- 理由：
  - 完整规范留在仓库，可版本化、可审计。
  - 核心规则只维护一份，减少不同 AI 入口之间的漂移。
  - `AGENTS.md`、README、HANDOFF 三个入口覆盖自动加载与人工交接场景。
  - 不把治理检查混入当前 M2 7/7 制造门禁，避免改变既有硬件门禁语义。

- AI 参与：
  - AI 比较落地方案、识别证据边界并实施文件组织。

- 团队自主判断：
  - 项目负责人明确要求先将该规范嵌入项目，并要求后续 AI 遵守。

- Evidence：
  - EVID-20260829-001
  - EVID-20260829-002

- 影响：
  - 后续实质 AI 任务必须维护对应台账；AI 记录默认待人工审核。
  - 历史记录不做无证据倒推，后续可基于原始提交和证据逐项回填。

- 后续复查条件：
  - 若某个实际使用的 AI 工具不会读取 `AGENTS.md`、README 或 HANDOFF，再为该工具增加经官方文档核实的薄适配入口；不得复制并维护另一份规则真源。

## ADR-002 — 根 AGENTS v1.4 作为 AEDL 当前唯一执行规范

- 日期：2026-08-29
- 状态：Accepted

- 问题：
  - 旧方案由根 `AGENTS.md` 的项目化摘要与 `docs/compliance/` 下 v1.0 完整规范共同组成；用户提供的 v1.4 已统一 Git、AIC、AI 使用、第三方资源、ADR、Evidence 和安全规则，继续维持两套当前规则会产生漂移。

- 候选方案：
  1. 只把 v1.4 当参考文件，不替换根入口。
  2. 将 v1.4 与现有根规则合并，形成项目私有变体。
  3. 按用户指令逐字节替换根 `AGENTS.md`，把 v1.0 降级为历史基线与格式参考，并同步导航文件。

- 决策：
  - 采用方案 3。

- 理由：
  - 用户明确说明 v1.4 是针对 AEDL 的最新版并要求替换。
  - 根文件与用户提供源保持一致，便于哈希核验和后续版本升级。
  - README、HANDOFF、合规 README 只做导航，不复制维护第二套执行规则。
  - M2 的硬件证据边界继续保留在 HANDOFF 与现有门禁中，不因治理规范替换而改变。

- AI 参与：
  - AI 识别多真源漂移风险，执行精确替换并同步入口与台账。

- 团队自主判断：
  - 项目负责人提供最终版文件，明确其适用于 AEDL，并要求替换现版本。

- Evidence / Reference：
  - 导入源与根 `AGENTS.md` 的 SHA-256 一致性检查。

- 影响：
  - 后续 AI 以根 `AGENTS.md` v1.4 为执行层唯一规范。
  - v1.0 文档继续保留，不删除历史合规基线。

- 后续复查条件：
  - 用户提供更高版本，或实际 Agent 无法发现/执行根 `AGENTS.md` 时复查。

## ADR-003 — GitHub 远端先 private、合规完成后再决定公开

- 日期：2026-08-29
- 状态：Accepted

- 问题：
  - 项目需要 GitHub 远端用于持续迭代和备份，但当前没有 LICENSE，RES-001/RES-003 的再分发权为 `TO_VERIFY`，且 AEDL AGENTS v1.4 改动仍待人工审核。

- 候选方案：
  1. 立即创建 public 仓库并推送全部内容。
  2. 创建 private 空仓、绑定 `origin`，审核并提交当前变更后再首推；公开化另行决策。
  3. 暂不创建远端。

- 决策：
  - 采用方案 2。

- 理由：
  - private 仓库满足备份/协作入口需求，同时避免无许可证和第三方再分发边界不清时公开内容。
  - 当前审计还发现 4 个已跟踪文件含本机用户路径，需要在公开前参数化或脱敏。
  - 保持远端空仓，不绕过当前 `PENDING_HUMAN_REVIEW` 状态。
  - 是否 public 是独立的开源边界决策，应在 LICENSE、第三方资源和公开内容审计完成后由项目负责人确认。

- AI 参与：
  - AI 检查本地 Git、GitHub 登录、同名仓库、许可证和当前工作树状态，创建并核验 private 远端。

- 团队自主判断：
  - 项目负责人明确要求建立名为 `AEDL` 的 repo；公开可见性和首推仍待后续确认。

- Evidence / Reference：
  - GitHub repo 查询结果：`nameWithOwner=sca331613-commits/AEDL`、`visibility=PRIVATE`、`isEmpty=true`。
  - 本地 `git remote -v` 指向预期 URL。
  - 当前工作树与 22 个历史 commit 的高置信 secrets 扫描为 0 命中；个人路径检查命中 4 个已跟踪文件。

- 影响：
  - 本地仓库新增 `origin`，但没有远端分支或 upstream。
  - 当前工作树和既有提交尚未传输到 GitHub。

- 后续复查条件：
  - 当前 diff 获人工审核并准备首推时；或准备将仓库改为 public 时。

- 后续结果（2026-08-30）：
  - private 远端已不再是空仓；当前 `origin/master` 为 `a3a51c6`。
  - B′ 修复位于本地分支 `fix/m2-schematic-semantic-release`，尚未 push；是否推送仍需按用户授权执行。

## ADR-004 — 独立硬件语义合同与人机分离制造放行

- 日期：2026-08-30
- 状态：Accepted（设计方案由项目负责人批准；制造签发仍独立待审）

- 问题：
  - M2 的错误 intent 被 akcli、原理图、PCB、ERC/DRC 与几何评审共同消费，形成同源循环自证；随后旧 BOM/POS、英寸 POS 和残留 Gerber 又证明“文件存在/彼此一致”并不等于制造正确。

- 决策：
  1. 数据手册约束由独立合同维护，同时交叉读取 intent、KiCad 网表、PCB pad-net 和固件常量；共同模式故障注入必须被捕获。
  2. 制造包只能由当前 PCB 在全新暂存目录生成；CPL 强制毫米与 JLC 字段，Gerber/ZIP 只允许显式生产层，并用 manifest 哈希绑定当前源和产物。
  3. BOM 库存证据按精确 LCSC code 即时查询、绑定规范 BOM；零库存生成失败证据且禁止自动换料。
  4. 自动 8 项板级检查与所有机器门禁不能设置 `manufacturing_release=true`；只有具名人工复核可重新签发，下单仍是独立人工动作。
  5. 回件前不得把静态、仿真、ERC/DRC 或软件门禁表述为实体 C 级验证。

- 理由：
  - 独立事实源和负向故障注入可阻断共同模式错误；源/产物哈希与本次 PCB 临时导出可阻断历史快照；人工签发保留制造风险的责任边界。

- AI 参与：
  - AI 完成根因分析、合同/测试/导出链实现、库存复核与证据生成；OpenAI Codex desktop 的精确部署型号仍为 `UNKNOWN`。

- 团队自主判断：
  - 项目负责人批准 B′，要求修复并把事故经验写入项目专属优化系统；具体制造重签与下单尚未批准。

- Evidence / Reference：
  - `notes/m2-semantic-repair/baseline_failure.json`
  - `notes/m2-evidence-reset/generated/semantic_fault_injection_current.json`
  - `notes/m2-evidence-reset/generated/bom_stock_current.json`
  - `delivery/manifest_v1.json`
  - `notes/m2-evidence-reset/run_manifest.json`

- 影响：
  - 旧 2026-08-29 制造签发已撤销；当前自动检查通过也必须保持人工重签阻断。
  - C82942 当前零库存使采购门禁额外失败；替代料必须重新走本 ADR 的独立审查链。

- 后续复查条件：
  - 规则在第二块不同载板复用；制造商/EDA 适配器插件化；或物理回件产生 C 级证据时复查。

## ADR-005 — 替代料换料审核协议：θJA 结温法、结论精度与主张纪律

- 日期：2026-08-30
- 状态：Accepted（换料方案经项目负责人初审 CONDITIONAL APPROVE、整改后采纳；board_review 重签独立待审）

- 问题：
  - C82942 装配库存归零触发受控换料后，AI 首版换料审核材料暴露三类方法论缺陷，全部由人工审核拦截：
    1. 用 "PD 标称值 ÷ 压差" 冒充热电流上限，未按 Tj = Ta + PD×θJA 结温法核算，未声明 Ta 条件；
    2. 把未确认输入（SOT-23-5 "~300mW"，后证实为 SOT23-3 行的解析误读）算成精确结论（"-17%"）；
    3. 无证据的过强主张（"同一颗 die"、"全系唯一候选"），未披露候选检索范围与逐项排除理由。
  - 另发现数据手册版本间实质差异：V20（LCSC 绑定 C235316 的版本）与 V24 家族版热额定不一致（SOT353 PD 250mW vs 450mW；V20 未列 SOT23-5 与 θJA；TOPR 记法不同）。

- 决策：
  1. 换料热验证一律使用结温法：Tj = Ta + (VIN−VOUT) × I × θJA；必须引用 θJA、Tjmax、TOPR，并按工作温度分档（25/60/85°C）核算；PD 标称值仅作独立硬边界交叉校验，不得当作热电流上限直接换算。
  2. 数据手册版本交叉核对：料号绑定版与家族版参数不一致时，以绑定版为硬边界、家族版为旁证；差异登记 `TO_VERIFY` 并列入回件实测清单。
  3. 结论精度必须匹配证据质量：输入为约值或待核实时，结论只能是区间或定性；禁止用推测输入产出精确百分比。
  4. 主张纪律：硅片同一性（"same die"）级别主张需厂商 ordering/选型表直接证据，否则降级为可验证属性陈述（同系列/同输出电压/同引脚映射）；排他性主张（"唯一候选"）必须给出检索范围、候选清单和逐项排除理由，否则限定为"已检索范围内"。
  5. 换料审核固定六维：功能、电气、引脚映射、封装几何、热、制造工艺；硅片同一性不属于必证项。

- 理由：
  - 三类缺陷均为"分析方法正确性"问题，现有机器门禁（ERC/DRC/语义合同/库存绑定）无法覆盖；固化为协议使下一任 Agent 直接执行正确方法，而非重新踩坑。人工审核是当前唯一防线，协议把该防线的要求前置到材料生产侧。

- AI 参与：
  - 首版材料的方法论缺陷由 AI（TRAE，GLM-5.3）产生并经项目负责人人工审核拦截；整改（结温法重算、基线确认、表述降级、版本差异登记）由同一 AI 完成。

- 团队自主判断：
  - 项目负责人判定初版热分析"数学没错但工程解释不够严谨"、排他性结论证据不足，给出 CONDITIONAL APPROVE 与三项整改要求，整改完成后采纳，并指示将教训沉淀为项目经验。

- Evidence / Reference：
  - `docs/compliance/AI_USAGE_LOG.md` AI-20260830-002（含初审意见与整改记录全文）
  - `docs/evidence/EVIDENCE_INDEX.md` EVID-20260830-001
  - ME6211 V20（LCSC C235316 绑定版）与 V24 家族版数据手册 Absolute Maximum Ratings 表

- 影响：
  - 本协议约束 project-027 后续所有替代料审核。
  - 派生固件约束：U3 避免持续 >147mA 负载（V20 保守边界换算）；回件 C 级实测清单增加"持续 WiFi 负载下 U3 温升"项。
  - 方法论教训同步记入 `docs/knowledge/IMPROVEMENT_SYSTEM.md`（当前无可执行控制，不算完成经验积累；热分析合同化是晋级前置）。

- 后续复查条件：
  - 下一次真实替代料审核按本协议执行并回检；或热分析结构化为机器可校验合同时复查。

## ADR-008 — AEDL Engineering Design Sandbox 三层隔离与状态控制平面

- 日期：2026-09-01
- 状态：Accepted（总体定义经项目负责人批准；V1/V2 运行时已实现——2026-09-01 三 Agent 交付并通过人工审核 CHANGES_REQUIRED 复审修复，见 AI-20260901-001/002/003/004）

- 问题：
  - AEDL 已从一次性生成转向内部 Agent 多轮设计—验证—修复循环，但“沙盒”若只表示代码执行隔离，仍无法约束器件、拓扑、引脚、参数、证据来源、冻结状态和制造权限。
  - 当前 EDD-001 已人工收敛 CORE、POWER、USB 与 CORE_BASE，运行时必须保护该有限设计域，不能让 Agent 重新扩张选型空间或把缺失资料解释为通过。
  - 多轮工作流还需解决副作用重复、候选污染冻结基线、同源自证、无限修复和 Agent 自行批准等问题。

- 候选方案：
  1. 只做传统进程/文件系统执行沙盒。
  2. 直接用 LangGraph 节点承载全部硬件判断与修复逻辑。
  3. 建立 Design、Execution、Trust 三层隔离，加跨层状态控制平面；LangGraph 只负责外层编排，工程判决由确定性 AEDL 模块执行。

- 决策：
  - 采用方案 3。
  - Sandbox 默认拒绝，只有显式声明才允许；统一输出 `ALLOW`、`DENY`、`BLOCKED`，不得将未知降级为允许。
  - 正式 EDD-001 运行时默认离线；外部资料检索、下载、许可证核验和证据摄取在 Sandbox 外完成。
  - 所有变更进入 content-addressed candidate；冻结 baseline 不原地修改，候选内容改变即使旧 evidence receipt 失效。
  - compiler 产物必须被独立解析器重新读取后验证，不能只对共同 HIR 做循环自证。
  - 修复循环设上限、finding fingerprint 重复检测和停滞熔断；checkpoint 恢复必须幂等。
  - 新器件、设计域扩张、替换已验证块、候选晋升和制造签发保留人工权限。
  - 首轮实现按高中低三块分工：H 独占公共协议/编排/最终适配，M 独占策略内核，L 独占信任证据；先冻结接口，再并行实现，最后由 H 单点接线。

- 理由：
  - 三层分别回答“能设计什么”“能怎么动手”“什么值得相信”，状态控制平面防止各层状态被一个笼统 `VERIFIED` 覆盖。
  - LangGraph 的 checkpoint、条件路由、interrupt/resume 适合外层循环，但不应成为硬件事实源或验证器。
  - 冻结接口与独占路径使三个 Agent 能并行工作而不抢文件；最终适配器单点接线降低公共接口漂移。

- AI 参与：
  - AI 将项目负责人提出的九类隔离对象收敛为三层 Sandbox、三态判定、状态控制平面和可手工分发的三 Agent 实施计划，并核对当前 EDD-001 合同/缺口与 LangGraph 运行条件。

- 团队自主判断：
  - 项目负责人明确批准该 Sandbox 定义，并决定下一步按工程难度高、中、低拆给三个 Agent；项目目标保持为人工审查下的创客级快速原型，实体可制造性仍是后续追求而非当前主张。

- Evidence / Reference：
  - `docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md`
  - `docs/superpowers/plans/2026-09-01-edd001-sandbox-runtime-v1.md`
  - `gates/contracts/edd001_core_base_contract_v1.json`
  - `gates/contracts/edd001_pin_constraints_v1.json`
  - `gates/contracts/edd001_usb_contract_v1.json`

- 影响：
  - 当前真实 EDD-001 因缺 POWER 合同、本地 datasheet、compiler 与独立 verifier coverage 必须保持 `BLOCKED`。
  - V1 只用确定性 RepairPort fixture 证明多轮机制；不宣称已具备 LLM 自主修复、KiCad 工程生成、系统级网络隔离或制造能力。
  - LangGraph 与 SQLite checkpoint 依赖只有在实现阶段实际加入后，才登记为已使用第三方资源并更新融合图；本 ADR 不把计划写成已实现事实。

- 后续复查条件：
  - V1 运行时完成并产生真实集成测试；首个 KiCad compiler/read-back verifier 接入；Sandbox 扩展到 EDD-001 之外；或引入 OS/容器级强隔离时复查。

## ADR-009 — 两人协作采用 Issue-first、独立 clone 与临时集成基线

- 日期：2026-09-01
- 状态：Proposed（已实施于 Draft PR #6；仍待另一名真人 Review）

- 问题：
  - AEDL 从单人多 AI 会话进入两名真人开发者协作，但 2026-09-01 现场审计发现：默认 `master` 比当前完整工作线落后 44 个提交；GitHub 无开放 PR/Issue/模板；当前 private 套餐不能启用 branch protection/rulesets；第二名协作者的 GitHub 账号与正式/外部身份尚未核实。
  - 若直接让两人从 `master` 或同一工作目录开工，会产生过期基线、共享 index、混合暂存、贡献归因错误和无人工 Review 的风险。

- 候选方案：
  1. 继续通过聊天分工，两人直接向共享分支 push。
  2. 新增长期 `develop` 分支，再设计一套完整 Git Flow。
  3. 采用最小 Issue-first 流程：一人一份 clone；一个 Issue 一个 Owner/领地/分支；过渡期从当前完整工作线开任务分支并向其提 PR；另一名真人 Review；稳定化后回归 `master` 作为唯一基线。

- 决策：
  - 采用方案 3。
  - `fix/m2-schematic-semantic-release` @ `e7ff3c1` 作为治理启动冻结点；治理 PR 合入后，以该远端分支最新提交为临时协作基线。
  - 禁止任务直接 push 到 `master` 或临时协作基线；只 push 任务分支，并通过 PR 交接。
  - GitHub 无法强制保护期间，由项目负责人程序性执行“禁止直推、另一名真人 Review、禁止自批”。
  - 不为了取得分支保护而把 private 仓库改成 public；公开仍受 ADR-003 的许可证与第三方边界约束。
  - 项目负责人已确认 `la4876949-bot` 为第二名真人协作者，贡献分类为 `AEDL_TEAM`，并允许领取 W4B；成员身份本身不登记为团队贡献，待其产生实际贡献后再更新 `TEAM_CONTRIBUTIONS.md` 与相应比赛归因。

- 理由：
  - 方案 3 直接补齐当前实际缺口，保持 AGENTS.md 的稳定分支与人工 Review 原则，同时不引入两人团队暂时不需要的复杂长期分支模型。
  - 独立 clone 隔离 working tree/index；Issue 的唯一 Owner 和 Owned paths 隔离写权限；PR 将 diff、测试与合规 ID 放到同一人工审核点。
  - 临时基线避免朋友从过期 `master` 开工；稳定化后回归 `master`，不把历史功能分支永久制度化。

- AI 参与：
  - OpenAI Codex 对本地 Git、远端分支、GitHub 协作者/邀请、PR/Issue、保护能力和测试基线进行现场审计，提出并实施治理入口、模板与任务卡。

- 团队自主判断：
  - 项目负责人明确表示“直接听你的，你直接开始操作”，授权执行已提交的治理先行方案；最终 PR 审核与 merge 仍保留给真人。

- Evidence / Reference：
  - GitHub Issue #1：两人协作治理基线。
  - GitHub Issues #2–#5：W4A、W4B、W4C 与 Sandbox V3。
  - `docs/COLLABORATION.md` v3。
  - `.github/ISSUE_TEMPLATE/task.md`、`.github/PULL_REQUEST_TEMPLATE.md`、`.github/CODEOWNERS`。

- 影响：
  - 新任务必须先创建 Issue 并明确唯一 Owner、领地、验收和身份分类。
  - 当前过渡期 PR 目标为 `fix/m2-schematic-semantic-release`；稳定化合并完成后改回 `master`。
  - `CODEOWNERS` 当前仅提供提醒，不构成技术强制；不能把程序规则描述成 GitHub 已锁定。
  - GitHub Issue/PR 模板只有进入默认分支才会在新建界面自动生效；治理 PR 仅合入临时协作基线期间，模板作为手工规范使用。

- 后续复查条件：
  - 第二名真人协作者产生首个实际贡献并完成登记；治理 PR 经人工 Review；当前工作线合并回 `master`；GitHub 套餐/可见性允许启用 ruleset；或协作人数超过两人时。

## ADR-010 — AEDL 主仓与 spike 实验/Evidence 卫星采用受控晋升边界

- 日期：2026-09-01
- 状态：Proposed（已实施于两个 Draft PR；仍待另一名真人 Review）

- 问题：
  - `Yenefa/AEDL-spike` 已保存两阶段协议执行器、故障注入与过程 Evidence，但主仓只把它称为“展示仓”，没有定义架构权限、技术主张归属、Evidence 回流或协作门禁。
  - 现场复核发现卫星仓当前为 private、只有历史基础提交、没有 Issue/PR/AGENTS/Handoff；同时主仓 README 仍把已撤销的 2026-08-29 制造签发写成当前 `manufacturing_release=true` 和“已授权下单”。
  - 若继续让两仓各自陈述状态，会产生双重真源、旧 Evidence 冒充当前结果、实验能力未经复验直接进入比赛主张，以及两名开发者跨仓重复修改的风险。

- 候选方案：
  1. 将 spike 内容全部复制回主仓并关闭卫星仓。
  2. 把卫星仓保留为无治理的展示快照，主仓只放一个链接。
  3. 主仓保持集成/技术主张真源，卫星仓成为受治理的实验/过程 Evidence 仓；跨仓吸收必须引用 exact commit/path，并在主仓 Issue/PR 中重新验证。

- 决策：
  - 采用方案 3。
  - `Yenefa/AEDL` 唯一负责集成代码、工程合同、ADR、合规台账、比赛主张、正式 Evidence 索引和制造权限。
  - `Yenefa/AEDL-spike` 负责协议执行器实验、故障注入样例和历史过程 Evidence；它不单独决定主仓架构、制造签发、公开范围或比赛技术主张。
  - 两仓各自执行 Issue → task branch → Draft PR → 另一名真人 Review；同一跨仓工作单元可以共享 AI Usage ID，但必须有独立 commit、PR 和 Handoff。
  - 卫星成果晋升必须记录 exact spike commit、源路径、复现命令、限制和主仓落点；在主仓独立验证后才能改变 Implemented/Claimed 状态。
  - 历史 Evidence 只做索引，不重命名为新运行，不把 native/Wokwi 结果提升为物理验证，不把预设候选池描述成 LLM 自主修复。
  - README 不再复制易漂移的绿色计数或制造授权；当前状态委托给 HANDOFF、Evidence Index 和结构化门禁真源。

- 理由：
  - 方案 3 保留实验历史和独立复现价值，同时用精确提交引用与主仓复验防止双重真源。
  - 关闭卫星会破坏过程上下文；无治理展示仓又不能满足两人协作、证据真实性和 AIC 自研/AI/第三方边界要求。
  - 稳定 README 减少历史结论反复漂移，真实制造状态仍由 `gates/board_review_v1.json` 失败关闭。

- AI 参与：
  - OpenAI Codex desktop 现场复核两仓 Git/GitHub 状态、协作者、历史 Evidence 与复现路径，提出并实施双仓治理、README 状态修复、卫星模板/索引和 Stage 1 Windows 输出解码修复。精确部署型号仍为 `UNKNOWN`。

- 团队自主判断：
  - 项目负责人确认 `la4876949-bot` 为正式团队成员，并明确将两个仓库的治理与修改全权交给当前 Agent；最终 PR Review 与 merge 仍由真人完成。

- Evidence / Reference：
  - 主仓 GitHub Issue #1 / Draft PR #6。
  - 卫星仓 GitHub Issue #1 / Draft PR #2。
  - `docs/COLLABORATION.md` §0.7。
  - `docs/evidence/EVIDENCE_INDEX.md` EVID-20260901-001 / EVID-20260901-002。
  - 卫星治理分支 `codex/spike-governance` @ `0e562e5`。

- 影响：
  - 后续 spike 实验默认在卫星仓立项；只有准备吸收时才修改主仓，并必须保留来源提交和限制。
  - 卫星仓当前保持 private；本决策不触发公开、Release、许可证变更或 Submission Check。
  - 本次只登记历史 Evidence，不重跑 Wokwi，不修改 M2 硬件、生产包、制造签发或实体验证状态。

- 后续复查条件：
  - 首个卫星成果实际晋升主仓；卫星仓准备公开/Release；两仓许可证或再分发边界变化；或正式比赛材料引用卫星结果时复查。

## ADR-011 — 控制面最小切片：Task Envelope + Admission + 单一 Development Gate + Escalation

- 日期：2026-09-01
- 状态：Proposed（分支 `feat/control-plane-minimal-slice`，未 commit/push；已按 Run 001
  Review REQUEST_CHANGES 三项整改收敛为最终 candidate 语义；待 Yenefa + Percy Review）

- 问题：
  - AEDL 已有完整规范文本（AGENTS.md 开工确认、Change Budget、越界 STOP、PENDING_HUMAN_REVIEW）与正式 Evidence Gate（`gates/run_gates.py`），但"开发验证"入口不统一：CI 跑过滤后的单测（`-k` 排除 3 个 CRLF-pinned 测试）、本地 Windows 跑全量、正式 Evidence 跑另一套。2026-09-01 实测：同一 HEAD 上主仓库 269 个测试有 2 个失败、sandbox 272 个有 8 个失败（全部为 Windows CRLF 检出 vs LF 声明哈希失配），而远端 CI 全绿——同一候选在不同环境有不同"验证通过"语义。
  - Agent 开工前没有机器可核验的 baseline/依赖/范围绑定；不同 Agent 可能基于不同 baseline、不同规则版本继续工作（C 类 State Coordination Failure）。

- 候选方案：
  1. 继续依靠 AGENTS.md 文本规则 + 手工核对。
  2. 先做 Context 分层 / Skill 路由优化。
  3. 最小切片：Task Envelope（base/deps/paths 机器字段）→ Admission（fail-closed）→ 单一 Development Gate（本地=CI 同一命令，JSON receipt）→ Escalation 协议；痛点出现一个再机械化一个，不建平台。

- 决策：
  - 采用方案 3。
  - Envelope 实例放 `tasks/GH-N.yaml`（模板 `docs/ENVELOPE_EXAMPLE.yaml`）；机器字段：base / dependencies / allowed_paths / forbidden_paths / exceptions；其余为自由文本。
  - 开工前 `python -m tools.admit --envelope tasks/GH-N.yaml`；fail-closed，BLOCKED 走 STOP → Explain → Escalate → Human Decision → Record → Resume / Reject。
  - 完成前 `python -m tools.dev_gate [--envelope ...] [--admit-receipt ...]`：syntax / main_tests / sandbox_tests / secret_scan / scope_check / binding_check；receipt 是开发验证回执，**不是**正式 Evidence；promotion 只有人工 merge。
  - CI 单一 dev-gate job（ubuntu + windows 矩阵）调用同一命令；GH-20 后**无平台排除**——选择性 `.gitattributes` LF 字节基线使同一测试集在每平台运行，`excluded_checks` 为空；sandbox 测试并入 gate（uv 由 job 提供），不旁生独立验证入口。
  - `--allow-dirty` / `--allow-drift` / `--skip-deps` 三个 flag **本身没有 authority**：必须由 envelope 的 `exceptions` 预授权（permitted+authority 或 granted_by+decision_ref），否则 BLOCKED（cannot self-authorize）；授权记录进 receipt `exceptions_used`。
  - admit receipt 绑定 `envelope_sha256`；gate 的 binding_check 校验 admission 后 envelope 未变（TOCTOU），变更 → FAIL → re-admit。

- 理由：
  - 先解决 B（Enforcement）+ C（State Coordination）两类最危险失败；A（Knowledge / Context）最后优化（上下文路由排第 6）。
  - 单一入口消除"四种验证语义"；receipt 让 PASS 语义可审计、可对比。
  - 本切片不引入任何第三方依赖（stdlib only）、不建平台、不造第二真源。

- AI 参与：
  - DeepSeek Harness（DSH Web）/ deepseek-v4-flash 将前两轮架构讨论（WorkBuddy / Claude Code / GitHub Copilot / Devin / Cursor / Linear 调研收敛）落地为可执行原语；以真实运行验证（单测 13/13、admit 三连演示、dev_gate 全量、干净 worktree 基线归因、gh 探测 PR #18）。

- 团队自主判断：
  - Yenefa 定稿吸收顺序（1 Envelope/Admission → 2 Gate → 3 Candidate→Promotion → 4 Escalation → 5 Derived+Provenance → 6 Context Routing）与四句话原则；AI 只做实现与验证，不做策略裁决。

- Evidence / Reference：
  - `tools/dev_gate.py`、`tools/admit.py`、`tools/envelope.py`、`tests/test_control_plane_tools.py`、`docs/CONTROL_PLANE.md`、`docs/ENVELOPE_EXAMPLE.yaml`。
  - AI-20260901-010（台账）。
  - dev_gate 真实 receipt：baseline `18b238164dc39bd34fbe9a5e7b7e0cf91a53f2f0`，status FAIL（2 主仓 + 8 sandbox 既有 CRLF 哈希失败；干净 worktree 归因与本次改动无关）。
  - 远端 CI 最近 6 次 run 全绿（LF）；本地 Windows 同 HEAD 失败（CRLF）——平台感知排除清单目前不完整：主仓另有 2 个、sandbox 另有 8 个 CRLF-pinned 哈希测试。

- 影响：
  - 变更集 22 个条目（10 修改 + 12 新增/更新，见 AI-20260901-010..013）；`.github/workflows/ci.yml` 变更属 Verification Policy Change，需 Yenefa + Percy 双人确认。
  - CRLF 哈希缺口已在 GH-20（Tasks 1-5）收敛：选择性 `eol=lf`（LF 声明文件）+ `eol=crlf`（gerbers，ZIP 契约）+ 8 处文本绑定重冻结为 blob 哈希 + 3 个 CRLF-pinned 测试重冻结；全局 `eol=lf` 方案被否决（Task 3：不得改写 M2 Evidence 字节）。
  - 未修改 M2 Evidence 仓库字节（工作树规范化 diff-free；bom_stock_current.json 仅声明刷新）；未运行会重写 Evidence 的 `gates/run_gates.py`；不构成制造签发或实体 C 级验证。
  - 本 ADR 承载**最终 candidate 语义**，不做 changelog；第一代→第三代演化记录在 AI-20260901-010..013。

- 后续复查条件：
  - 首个真实 Issue 以 envelope + admission 走完 ADMIT → EXECUTE → GATE → PENDING_HUMAN_REVIEW → MERGE 全链路；CRLF 哈希缺口得到双人裁决；或 CI/本地验证语义再次分叉时复查。
