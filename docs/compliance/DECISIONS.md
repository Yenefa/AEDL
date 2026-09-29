# Engineering Decisions

> 关键工程与治理决策使用 `ADR-NNN`。状态只表示决策是否采用，不等于人工审核台账已经完成。

## ADR-013 — Y4-dry 生成与独立评分分离

- 日期：2026-09-10
- 状态：Human decision approved；实现仍为 `PENDING_HUMAN_REVIEW`，不等于 merge 或完整实验验收。
- Decision owner: Yenefa
- Proposal source: Mixed
- Final decision: Human
- Implementation: AI-assisted
- Review authority: Yenefa（架构/实现）；Percy（独立评分与验收）
- Promotion / merge authority: Yenefa
- 问题：C1 `parse_proposal` 仅校验 Proposal；C2 `compare_delta(before, after, bound)` 需要真实 after observation 与 host-bound 预期，不能直接给 dry Proposal 打 A 分。
- 候选方案：新增 symbolic executor 后调用 C2；或 A2 只输出原始 Proposal，由 A3 独立评分。选择后者，避免引入第二套修复执行语义。
- 决策：A2 冻结 public input，C/D 使用相同接口，C1 校验并记录原始输出；A/B 两维均交 A3/Percy 使用独立 oracle 评分，A2 `scoring=NOT_RUN`。Y4-dry 不调用 C2 评分，不新增 fake/symbolic executor。C2 留给 C3–C6 就绪后的 Y4-native 真实 candidate execution 与 fresh AfterObservation。
- 配套完整性：public package v2 增加生成方提供的 source/observation 双 hash 与 producer 标识，拒绝错配或过期数据对；这只是声明与内容一致性，不替代 C3 独立导出、权威来源或真实性证明。C1/C2 与 Proposal schema 不变。
- AI 参与：分析接口差异、提出生成/评分分离方案、按批准实现 harness/绑定/测试；同一工作单元 `AI-20260909-CODEX-08B3C72E2039158034BF8831C5648828`。
- 团队自主判断：Yenefa 于当前 Codex 会话明确批准「dry scoring 架构裁决，并更新 Issue #56」，并要求 summary/envelope、binding/tests 及复验；Codex 仅同步决定。未将代码状态改为 HUMAN_REVIEWED/ACCEPTED。
- Reference：[Issue #56](https://github.com/Yenefa/AEDL/issues/56) 的 Human-approved dry scoring decision；2026-09-10 当前用户指令。
- 影响：允许新增的 Y4 draft package binding 字段；不读取 private oracle，不改 sandbox，不豁免 #51，不宣称 dry 正确性等于 native 修复成功。
- 复查条件：五例（DC-01..DC-05；DC-06 为 `EXCLUDED_BEFORE_FREEZE` / `UNSCORED_GOVERNANCE_INCIDENT`）public inputs 准备/审查、A3 rubric 冻结、J1 决策，或进入 Y4-native 实际观察验证时复查。真实实验结果仍为 NOT_RUN。

## ADR 字段规范（2026-09-09 起适用于新 ADR）

> 目的：把"谁提出、谁决定、谁实现、谁有权 review / merge"从正文散文提升为**显式字段**。
> 适用范围：**本规范生效之后新写的 ADR**。生效之前的 ADR 保持原文，**不回填**这些字段——
> 历史事实以各自正文的「AI 参与」「团队自主判断」为准，聚合总览见 [`docs/HUMAN_OWNERSHIP.md`](../HUMAN_OWNERSHIP.md)。

新 ADR 除 `AGENTS.md` §6 既有内容外，必须声明：

```text
- Decision owner:              <人类 / 角色>
- Proposal source:             Human / AI-assisted / Mixed
- Final decision:              Human
- Implementation:              Human / AI-assisted / Mixed
- Review authority:            <人类 / 角色>
- Promotion / merge authority: <人类 / 角色>
```

填写规则：

- `Final decision` 恒为 `Human`：AI 可以提议、实现与验证，但不能晋升或批准（AGENTS.md §2.3、§3.7）。
- `Proposal source` 与 `Implementation` 允许 `Mixed`：人类提出目标/约束、AI 收敛技术方案、
  人类最终批准时按 `Mixed` 记录，不写成 `Human`（见 [`ATTRIBUTION_POLICY.md`](ATTRIBUTION_POLICY.md) §3）。
- 无法核验时写 `TO_VERIFY`，不得猜测。
- 本字段规范只约束新 ADR，不改写任何既有 ADR 正文。

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
- 状态：**Accepted**（2026-09-01 经 PR #21 merge 至 master @ `084fb92`，Run 001 晋升完成；
  双平台 CI 全绿，EVID-20260901-003 = YES）

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

## ADR-012 — AI Usage 台账拆分：per-entry 文件 + actor 随机 ID + 生成索引

- 日期：2026-09-08
- 状态：**Proposed**（GH-49 PR 待人工审核合并后转 Accepted）

- 问题：
  - 单文件 append-only 台账（`AI_USAGE_LOG.md`）+ 每日全局递增 ID（`AI-YYYYMMDD-NNN`）在多 Agent / 多分支并行下系统性失效：所有分支在同一文件末尾同一位置 append → Git 文本冲突；各分支各自"取最大号 +1" → 语义撞号。2026-09-06 一日累计四次并行撞号（002→007→010 连锁改号，台账自记"顺序编号在多分支并行下系统性失效"）；PR #36 rebase 冲突再次复现。
  - 撞号后的改号无法修改已共享提交的 commit message（AGENTS §3.7 禁改写历史），只能在新条目里写改号说明，台账出现"ID 名不副实"的历史包袱。

- 候选方案：
  1. 维持现状，冲突靠手工 rebase 解决——继续制造冲突与撞号。
  2. actor 前缀 + 局部递增——不同 actor 被隔开，同 actor 的不同分支仍会同时取到相同最大号 +1；文件不是跨分支锁。
  3. 拆分存储 + actor 前缀 + 随机后缀 + 生成索引——记录独立分配，索引由脚本重建并校验。

- 决策：
  - 采用方案 3（GH-49）。
  - 存储：条目真源 `docs/compliance/ai-usage/<ID>.md`（一文件一可审计工作单元）；`AI_USAGE_LOG.md` 降级为**自动生成索引**，文件头带 GENERATED 标记，禁止手工编辑。
  - 工具：`tools/build_ai_usage_index.py` 的 new / migrate / build / check。new 用标准库 `secrets.token_hex(16).upper()`，生成 128 bit、32 位大写 hex 后缀，并排他创建新文件；同目录碰撞重试且不覆盖。无需中央序号或扫描最大值。
  - 新格式 `AI-YYYYMMDD-<ACTOR>-<RANDOM>`；存量 `AI-YYYYMMDD-NNN`、早期 `<ACTOR>-<NN>` 继续只读兼容、不追溯改号。actor 是审计分类标签，不是身份认证。
  - migrate：同 ID 同字节正文才 skip；不同正文 HARD FAIL，先预检整个批次再写新文件。`--source` 支持外部旧台账快照；任何已知历史补记也必须显式调和，不能自动豁免。
  - check：校验 ID、日期、审核状态、目录杂项，且与 `build_index_text(entries)` 全文比对，涵盖数量/摘要/顺序/链接；索引漂移由 dev_gate fail-closed。
  - 随机 ID 是概率保证，不承诺数学上的零碰撞。共享生成索引仍可能冲突；保留双方记录后重新 build/check。相同 ID 不同正文不得静默吞掉一方。

- Evidence / Reference：
  - `tools/build_ai_usage_index.py`、`tests/test_build_ai_usage_index.py`、`docs/COLLABORATION.md` §0.1、`docs/ID_MAP.md`、`AGENTS.md` §4；实际数量与测试结果以对应 head 的 Review Bundle 为准。
  - AI-20260908-YEN-001（台账）。
  - 2026-09-09 复审修订：AI-20260909-CODEX-D685F9E9FAC5AF8DCA0869791DE02AE4；[Python secrets 官方文档](https://docs.python.org/3/library/secrets.html#secrets.token_hex)。

- 影响：
  - 迁移保留条目内部字节；条目间空行属结构，可移除至一个终止换行。原迁移另对 2 条 stub（AI-20260901-007/-008）追加默认 `PENDING_HUMAN_REVIEW`；这是已披露的正文修订，不能称为全部正文零差异。
  - 必须先处理仍追加旧式台账的开放 PR（含 #34），再对最终 master 迁移、build、check，并重跑全部测试与门禁。#50 已合入 master `4d5a8f4`，本轮已收编其两条旧记录；过程与当前计数见 `ai-usage/README.md`。旧提交计数不能用作后续 head 的证据。
  - 新增记录后忘记 build 会被 check 拦下，但 check 无法凭空发现没有导入的外部旧台账；最终迁移必须独立核对源条目集合。
  - 后续复查条件：若 per-entry 文件数量增长到使目录枚举显著变慢（>500 条），再评估按月分目录；当前规模不做。

## ADR-014 — 「零违规」不构成证据：ERC/DRC 若落地必须绑定并记录 `ignored_checks`

- 日期：2026-09-28
- 状态：**Accepted**（Owner 2026-09-28 裁定「3.处理」，在 PR #99 被关闭的同一轮）

- 问题：
  - 一个验证器若只检查「违规数为零」，这个判据可以被**把规则设为 ignore** 轻易满足。
  - 实测（KiCad 10.0.5，M2 板）给出直接证据：工程文件与板同名关联时，DRC 连续 12 次稳定报
    `violations: []`，而该报告的 `ignored_checks` 列出了 5 类被禁用的规则
    （`missing_courtyard`、`track_not_centered_on_via`、`tuning_profile_track_geometries`、
    `footprint_filters_mismatch`、`footprint_type_mismatch`）。**一块真的存在 courtyard 缺失、
    track 未对中 via、footprint 与符号不匹配的板，也会报 `violations: []`。**
  - 这不是从形式验证论文推来的类比，而是**在本项目自己的板、自己的工具上直接演示出来的
    空证明实例**。
  - 同一轮实测的另一半：判定是「板 × 关联工程 × 规则严重度设置」的联合函数。工程未关联时
    条数在 35/36/37 之间波动，关联后稳定为 0。**无论哪种配置，DRC 都不适合作为 `COMMIT` 门禁。**
  - 另一会话（ZCODE）产出的设计评审独立得出同向结论，并把它标为 F11。

- 本仓库已经犯过这个错：
  - 被关闭的 PR #99 在自己的证据产物里报了 `error: {total: 0, by_type: {}}`，
    而实测该 fixture 的 ERC 报告 `ignored_checks` **非空**，含 4 条：
    `single_global_label`、`four_way_junction`、`simulation_model_issue`、`footprint_filter`。
    **即：零错误这个数字，在不知道哪些规则被关掉的前提下是没有意义的。**
  - 同一份产物还记录了一个恒为 0 的 `exit_code`：不传 `--exit-code-violations` 时，
    即使有 37 条违规 ERC 也返回 0；带上该标志则返回 5。

- 候选方案：
  1. 维持「零违规即通过」——已被上述实测直接证伪。
  2. 把 ERC/DRC 移出 `deferred` 并纳入门禁——与合同 §21/§351 冲突，且继承同一不确定性。
  3. **保持 `deferred: NOT_RUN`，并把「零违规不是证据」写成一条对 PR-2 有约束力的硬约束。**

- 决策：
  - 采用方案 3。ERC / DRC / 语义 runner / 形式证据**继续永久保持 `deferred: NOT_RUN`**，
    依合同 §21（属 PR-2）与 §424（deferred ERC 不得被伪写 PASS）。PR-1 的 thin verifier
    只覆盖「变更局部功能等价性」一层（合同 §373 的四项检查），**不扩张**。
  - **约束（对 PR-2 有约束力）**：任何以「违规数为零」为判据的检查，必须同时
    (1) 绑定并记录 `ignored_checks`（键与描述）；
    (2) 记录 `included_severities`；
    (3) 把工程文件摘要纳入 toolchain（工程是否与板同名关联会改变判定）。
    三者缺一即该判据无效，**不得**据此得出 PASS。
  - 记录一条 ERC/DRC 判据时必须附**实测依据**（`stability_evidence`）：哪台机器、哪个工具版本、
    哪块载体、几次重复、哪些字段会变。没有实测依据的 evidence 规则不允许上线。
  - 取证命令必须显式钉全部相关标志。已知五类陷阱，逐条实测：
    不带 `--exit-code-violations` 时有违规也返回 0；`--save-board` / `--refill-zones`
    会改写输入 PCB（禁用）；`pcb export svg` 不带 `--mode-*` 时默认行为已弃用；
    `--output` 在 `--mode-single` 下是文件、在 `--mode-multi` 下是目录；
    输出内嵌绝对本机路径（入库前必须剥离）。
  - 报告**不是 artifact**。把一次采集结果当产物求哈希，会得到「同一设计两个不同身份」。
    故证据身份分五类：`raw`（provenance）/ `semantic`（唯一可作比较依据）/
    `execution` / `context` / **`report`（观测，不可作身份）**。
  - 一个已知但尚未实现的免费版本守卫：ERC/DRC 报告自带 `$schema`
    （`erc.v1.json` / `drc.v1.json`），且该 schema 是 `additionalProperties: false`，
    字段增删必升版。**把 `$schema` 值纳入 expected 常量并 fail-closed 检查，
    可在不解析内容的前提下发现 schema 漂移。**（本轮未实现。）

- 影响：
  - PR-1 的 KICAD_VERIFY 只跑四项必需检查，ERC 留在 `deferred`，本决策不改变已合并的行为。
  - PR-2 实现 ERC 时必须先满足上述三条绑定要求，且必须带实测依据。
  - 「delta 是否满足 requirements_contract」是**另一个**空证明方向：当前 C5 链路验证的是
    「变更是否等于授权的变更」，没有任何一环验证「变更是否满足需求」。列为 P1，
    且只能覆盖可自动判定的需求项。

- 复查条件：
  - KiCad 升级并改变 ERC/DRC 报告结构（`$schema` 升版）时复查。
  - `stability_evidence` 目前只有一块载体、一个 KiCad 版本；第二载体解封后必须复现，
    否则它不具备强制化资格。
  - 若将来把 ERC 纳入门禁，必须先证明它在**已知缺陷**上有检出率——现有实测是：
    标准 ERC 对 DC-04 缺陷类的检出率为 **0**（缺陷态 error 数为 0）。

- Evidence / Reference：
  - 被关闭的 PR #99 及其关闭评论（记录了本决策的由来，以及本仓库犯下的具体错误）
  - `tasks/PR1-C5-KICAD-VERIFY.yaml` 的 `design_frozen_by_owner` 裁定 3
  - 实测来源：KiCad 10.0.5（sha256 `fc142e3b…`）本机运行；ERC JSON 顶层键为
    `$schema / coordinate_units / date / ignored_checks / included_severities /
    kicad_version / sheets / source`
  - 另一会话产出的 KICAD_VERIFY 设计评审 v2（§1.5 受控 A/B、§1.4 schema、F11）
  - 合同 §21 / §351 / §373 / §424
- 团队自主判断：本条由 Owner 直接裁定（2026-09-28 会话「3.处理」），
  依据是本项目自己工具链上的实测，不是外部偏好。
- AI 参与：实测与 ADR 文本由 OPENCODE 会话产出，见
  `AI-20260928-OPENCODE-76DB9B9EC4A1703B7C2C8B2B1C30969B`（该条目同时记录了被关闭的
  PR #99 的四个实测缺陷，含本决策的由来）。

## ADR-015 — 单写者锁的实现解释：固定内容锚点 + OS 字节范围锁

- 日期：2026-09-28
- 状态：**Accepted**（Owner 2026-09-28 裁定「锁单独开一个 PR，本轮如实标记不可达」，
  随后裁定推进主线；本条记录该 PR 落地时对合同 :376 的解释）

- 问题：
  - 合同 :376 规定：`candidate/.repair.lock` 为**内容固定、不因 unlock 删除**的锁文件。
  - **内容固定 + 永不删除 ⇒ 文件是否存在无法表示「是否持锁」**，所以排除机制必须另有来源。
  - 合同同时把「单写者锁仍由本事务持有」列为 commit 谓词的第九个合取项（:346），
    并要求 PRECHECK「获取 candidate 单写者锁」（:369）。
  - 实测：本仓库**没有任何锁原语**。`lock_path` 只作为 `workspace` 的一个路径字段被校验过
    （`tools/repair_pipeline.py`），从未被获取；`msvcrt|flock|LockFileEx|filelock|
    portalocker` 在 AEDL 代码中 `NOT_FOUND`。
  - 猜错是双向的：要么两个写者同时进入同一个 candidate（正是 COMMIT 要防的灾难，
    因为两者都通过谓词后都会 replace 同一份 design 字节），要么锁比合同更严导致死锁。

- 候选方案：
  1. 文件存在即持锁，unlock 时删除 —— 直接违反 :376（内容固定、不因 unlock 删除）。
  2. 用 `mkdir` 的原子性做互斥 —— 不是「锁文件」，且 :376 明确说的是文件。
  3. **固定内容锚点 + OS 字节范围锁**（本条采纳）。
  4. 不实现锁，把合取项报为未满足 —— Owner 已裁定锁单独落地，故不采纳。

- 决策：
  - 采用方案 3：
    - `<candidate>/.repair.lock` 是**固定内容锚点**（本轮为
      `aedl-repair-single-writer-lock-v1\n`），O_EXCL 创建一次，**字节永不改变，
      永不删除**。:376 字面满足。
    - **排除性来自锚点上的 OS 字节范围锁**，Windows 用 `msvcrt.locking(LK_NBLCK)`，
      POSIX 用 `fcntl.flock`，均非阻塞。进程死亡时由 OS 释放，因此**崩溃不可能留下
      陈旧锁** —— 这正是合同 :390 的保证边界「进程异常/可检测 I/O 故障与重启恢复」
      能够成立的原因，而不必虚构 :390 明确拒绝声称的突然断电/磁盘物理损坏保证。
  - **失败关闭**：拿不到 OS 原语、或锚点内容与冻结值不符，都**拒绝**。
    绝不使用进程内 fallback —— 一个无法排除其它进程的机制不是锁。
  - 锁在 PRECHECK 之前获取、在 `finally` 中释放；恢复（:385 的恢复会**写** design 文件）
    必须在持锁状态下进行，否则两个轮次会同时恢复同一个 candidate。
  - **Windows 实测**（不是推断）：持锁时锚点**既不能 `open` 也不能 `read`**
    （字节范围锁同时挡住两者）。所以冲突会先出现在内容校验那一步，两处都必须
    报「another writer holds the lock」而不是「锚点无法准备」——后者会把读者
    引向错误的文件。
  - 锚点被外部改写时**拒绝并保留原内容**，不重写：那个内容是证据。

- 影响：
  - 谓词第九项（:346）从「恒为假、结构性不可达」变为可满足，COMMIT 因此第一次真正可达。
  - 一个轮次在同进程内连续跑两次是安全的；锁不跨进程残留。
  - 本条是**对合同 :376 的解释**，不是合同原文。若 Owner 认为 :376 指的是别的东西，
    回退成本是局部的：`_SingleWriterLock` 是唯一依赖该机制的类。

- 复查条件：
  - 若平台不提供可移植的字节范围锁语义（当前只有 Windows 与 POSIX 两条路径实测过），
    或需要跨主机分布式锁，则本条失效并须重新裁定。
  - 若合同 :376 被修订或澄清，本条须重写。

- Evidence / Reference：
  - 实测：Windows 上锚点被持锁时 `open` 与 `read` 均抛 `PermissionError`；
    释放后同一进程可再次获取；锚点内容在 unlock 后不变。
  - 变异检验 `mut_writer.py` 15/15，其中 X1（锁恒成功）、X2（不释放）、
    X3（不校验锚点内容）、X15（缺 lock_path 时假定而非拒绝）各自被检出；
    X2 在 CPython 下是**等价变异**（局部对象被引用计数回收时句柄即关闭），已如实标注。
  - 合同 :369 / :376 / :384 / :385 / :386 / :387 / :390
- 团队自主判断：Owner 裁定锁的**排期**（单独 PR）与推进授权；机制解释由 AI 依据
  合同 :376 的字面约束与本机实测作出，**已在三处显式标注为解释**，并采用失败关闭，
  使得猜错的代价是「轮次拒绝」而不是「静默的双写者」。
- AI 参与：本条由 OPENCODE 会话产出，实测与代码见
  `AI-20260928-OPENCODE-449C2176753ED1792897B0855526CD92`。

## ADR-016 — ARH：LLM Repair Agent 以 proposal-only 接入既有 Trust Plane，benchmark 口径先冻结后实现

- 日期：2026-09-28
- 状态：**Accepted**（Owner 2026-09-28 会话批复原文：「批复，没有本阶段不做的，全量全速全质推进！开始」；
  D1–D7 与 B1–B5 按 `docs/specs/ARH_DECISION_SHEET.md` Recommended 全数通过）

- 问题：
  - 要把真实 LLM 接回 AEDL，让它依据 verifier findings 反复修复，同时**不破坏**已建成的
    Trust Plane（authorization / HostPatch / transaction / compare_delta / fresh read-back /
    post-condition / evidence / 人工晋升）。
  - 三条现成路径各有一个致命面：直接拿 coding harness 当 runtime（其 ACI 假设 Agent 拥有
    shell 与代码写权，等于允许 LLM 直接 `sed` 一个 `.kicad_sch`）；从零造 Agent framework
    （重复造轮子）；整体迁到现成 agent framework（SDK 可换，AEDL 契约不可换）。
  - 实验方法学问题：D1/D2/D4 是 benchmark 口径不是功能选择，先写代码后定口径 = 数据作废
    （RFC §4.5 冻结依赖）；且 RFC §4.2 注入条件①会静默剔除 verifier 漏检的 fault，
    使漏检率在协议结构上不可测（O-12）。

- 候选方案：
  1. coding harness（mini-SWE-agent / SWE-agent / OpenHands）直接作为 AEDL runtime —— 否决。
  2. 迁移到现成 agent framework（OpenAI Agents SDK 等）作为运行时 —— 否决。
  3. 自研完整 Agent framework —— 否决（V1 不需要）。
  4. **薄的 AEDL-native ARH**（本条采纳）：保留 LangGraph + RepairPort + Trust/Transaction 层，
    新增五个薄模块，吸收 coding harness 的 Model/Environment/Trajectory/ACI **设计经验**而不
    继承其权限模型。

- 决策：
  - 架构五行走齐：`LangGraph KEEP`（外层 routing/checkpoint，ADR-008 边界不变）、
    `RepairPort KEEP`（frozen 签名 `propose(run_id, candidate_id, findings) -> PolicyRequest`
    是 LLM 的唯一出口）、`Trust Plane KEEP`、`Coding harness REFERENCE ONLY`、
    `ARH = THIN AEDL-NATIVE`（ModelAdapter / ContextBuilder / RepairAgent /
    TrajectoryRecorder / Budget&Stop）。细则以
    `docs/specs/AEDL_AGENT_RUNTIME_RFC.md` 为准。
  - V1：**单 Repair Agent、proposal-only**（无 execute / shell / 任何写工具），产出
    `RepairProposal`，由 Harness 构造 `PolicyRequest`（`actor`/`capability_grants`/
    `run_id`/`action_id`/`action` 等权威字段 agent 不可携带，出现即 schema 拒绝）。
    真实 LLM 接入前置 = RFC §2.5 五项 BLOCKING（N2/N3/N4/N6/N8）落地 + G1/G8 保持不启用。
  - **D1**：fingerprint 维持 `(code, message)`，`state.py` 不动；「换措辞绕过 stall」记为
    V1 已知限制，由 Harness 预算/去重兜底；severity 过滤或 `details` 入指纹属 V2 契约变更。
  - **D2**：`invalid_proposals` 由 Harness 预校验层统一计数（含输出侧丢弃的重试），与
    `policy_denied_runs` 严格分列；**保留**其为 `converged_strict` 必要条件。
  - **D3**：上下文窗口取保守值（`code_window` 40 行 / attempt_history 最近 1 轮折叠），
    全标 `TO_VERIFY`，pilot 中 A/B 40 vs 100。
  - **D4**：双层预算——图内完全复用 `max_repairs`/fingerprint/`repair_count`（不新造、不放宽）；
    图外 LLM 预算（调用数/token/wall-clock/连续无效提案/格式错误）由 Harness 强制，超限记
    `INVALID_RUN`。Budget&Stop 为**独立模块**（ARH-N6），不 fold 进其他文件。
  - **D5**：`receipts_digest` 用 `{event_type, hash12}`（以 `state.encode_receipt` 现有字段为准）。
  - **D6**：allowlist 是字段**投影**，禁止 `engine.document` / `current_state()` 全量进 prompt。
  - **D7**：V1 不引入 READ grant；读能力 = Harness 工具白名单 + 作用域；V2 引入 grant 的
    前置 = G1 对账实现。
  - **Stage 0**：`Verifier Capability Pre-measurement`（RFC §4.0）作为 fault set 构建的
    前置工序，谓词复用 §4.2 条件①（= 冻结项 1 的 killable 校验），唯一改变是「过滤器 →
    过滤器 + 计数器」；Stage 1 收敛指标 conditional on detectability，recall 表与收敛率
    **绑定报告**；recall 不进 scoring。
  - **顺序**：拍板（本条）→ §4.5 文本类冻结项即刻冻结（引用本 ADR 所在 commit）→
    implementation。fault set、随机性/模型参数类冻结项因 `NOT_RUN` 尚未冻结，Stage 0
    执行时补齐后方可进入主实验。
  - **位置**：ARH 落 `sandbox_runtime/src/aedl_sandbox/arh/`（新增包；`protocol.py`、
    `state.py` 语义不改）；benchmark 工具链与 runtime 预算分账（runner/fault 生成/评测
    独立于 500–1000 行的 harness runtime 预算）。

- 影响：
  - `protocol.py` / `state.py` / LangGraph 节点结构不动；orchestrator 未来仅在装配点接收
    一个 `RepairPort` 实现。
  - benchmark 文本类口径自本条冻结，改 = 重跑（§4.5）。
  - RFC 红队分账的 8 项**现有**缺口（G1–G8）不因本条被宣称已修复：G1 对账（「Execution
    Authority Binding」）单独立项，未实现前 V1 不启用任何 capability（恒 fail-closed）。
  - 对外主张纪律：只能声称「V1 设计上 Agent 无写权限、权威字段 schema 拒绝」（可演示），
    **不得**声称「已证明 Agent 无法绕过」——执行验证 `NOT_RUN`。

- 复查条件：
  - 五项 BLOCKING 未全部落地前，真实 LLM 不接入（RFC §2.5）。
  - 若需启用任何 capability、或变更 fingerprint 语义 → 本条相应部分失效，须新 ADR。
  - Stage 0 recall 若出现 `VERIFIER_BLIND_CLASS` 且落在核心 fault class 上 → benchmark
    主张范围重议。
  - 若 `protocol.py` 冻结被解冻或 RepairPort 签名变更 → 重议 ARH 出口契约。

- Evidence / Reference：
  - `docs/specs/AEDL_AGENT_RUNTIME_RFC.md`（§1–§7，含 §4.0 与 O-01..O-28）
  - `docs/specs/ARH_DECISION_SHEET.md`（拍板回执，2026-09-28）
  - `docs/research/agent-runtime/01..06`（六路研究，各带来源）
  - `AI-20260928-OPENCODE-8651841DEF357F134049F6F9FA652DCE`（六路研究 + RFC 综合）、
    `AI-20260928-OPENCODE-787EDCFDB16A56688A50C97A85C1DE5C`（§4.0 + Decision Sheet）
  - ADR-008（LangGraph 边界）、ADR-014/ADR-015（同期纪律）
  - 一切 benchmark 数字：**NOT_RUN**（本条只冻结口径，不含任何结果）

- 团队自主判断：架构四选一（A coding harness / B 迁框架 / C 自造 framework / D 薄 ARH）由
  Owner 在 RFC 评审中裁定选 D；「V1 不上 Multi-Agent、单 Agent 是要验证的实验本身」为 Owner
  先前裁定；D1–D7 的 Recommended 为 AI 依据六份研究报告给出，**批准动作是人的**。
- AI 参与：OPENCODE 主会话 + 7 个子代理（6 研究 + 1 综合）产出 RFC 与报告；本条 ADR 文本
  由 OPENCODE 起草，记录于上述两条 AI usage 条目，`PENDING_HUMAN_REVIEW`。

## ADR-017: 候选边界是**候选**，不是 workspace；别名文件不是候选内容

- 状态：accepted（未合并，pending human review）
- 日期：2026-09-28
- 编号说明：跳过 016。同一仓库中另一个 session 的未合并分支 `feat/arh-harness`
  已使用 ADR-016（ARH approvals），此处取 016 会在合并时产生两个同号决策。
  冲突是可预见的，所以跳过被**记录**在此，而不是留成意外。
- AI 参与：AI-20260928-OPENCODE-92503CBF192B51EC0ECAEBF2B1859A4F
- 关联：`sandbox_runtime/src/aedl_sandbox/workspace.py`；PR-1 合同 :378
  （文件 link count/别名与实际身份）；`tasks/PR1-F1-CANDIDATE-ISOLATION.yaml`

### 问题

`CandidateWorkspace._root` 是整个 workspace，`_ensure_confined` 做
`resolved.relative_to(self._root)`。于是**任何仍在 workspace 内的目标都通过** ——
包括兄弟候选。边界粗了一级。

把四条逃逸路线跑起来之后，其中三条解析路径检查原理上就修不了：

1. 跨候选写入：`mklink /J` 从 candidate-a 进入 candidate-b，写入被 ALLOW，字节同时落在
   两个候选里。junction 不需要提权。
2. 内容身份：`candidate_hash` 走 `rglob`，而 **rglob 会跟随 junction**。实测
   candidate-a 的哈希在 B 的文件被改动时**跟着变**（`cebd096cd88dbcca` →
   `c1555a69510bbade` → `72ecff9007f13e4d`）。无异常、无痕迹。绑在 A 上的内容寻址
   回执会被「别人改了 B」作废，两个不同候选可以被做成同一身份。
   **这条不是「逃出边界」，是「走进另一个候选」，所以解析再比较在这里没有作用。**
3. ledger 没有任何约束调用。而 ledger 被排除在内容哈希之外 —— 这恰恰使它成为放
   「非设计内容」最方便的位置，所以它值得至少同等的注意。
4. 硬链接：`Path.resolve()` **不跟随**硬链接，两个名字都是同一 inode 的合法路径，
   所以 A 里指向 B 的硬链接解析后**仍在 A 之内**，比较通过，写入落进 B。

### 候选方案

- A. 保持 workspace 边界不变，只在文档里说明「候选之间不互相写」。**否决**：四条路线
  没有一条被关掉，其中两条静默。
- B. 全部用解析后路径比较。**否决**：对 2 和 4 无效，而且是原理性的，不是实现问题。
- C. 候选内容中出现任何链接就**跳过**，哈希只算真实文件。**否决**：算出来的哈希会
  与磁盘上的字节**不一致而不声明**，而内容寻址的全部意义就是它不撒谎。
- D. 候选边界 + 非跟随遍历 + 链接数检查，命中即**拒绝**。**采纳**。

### 决策

1. 候选范围内的操作以**解析后的候选根**为边界。workspace 边界**保留不替换** ——
   `create_candidate` 本来就要在它下面建目录；候选边界严格更紧，所以原有「逃出
   workspace」的测试逐条照旧通过。
2. 遍历用 `os.walk(followlinks=False)` **并且**对每个目录做显式 reparse-point 检查。
   只用 `followlinks=False` 不够：`followlinks` 认的是 symlink，而 junction 是
   reparse point。
3. 候选内出现链接 → **拒绝**，不跳过。
4. `st_nlink > 1` 的文件 → **拒绝**。这是合同 :378 的「文件 link count/别名与实际
   身份」在 Sandbox 侧的同一个性质。
5. 链接判定必须**可移植**：`Path.is_symlink()` 不覆盖 Windows junction，
   `Path.is_junction()` 在本仓库的车道（Python 3.9）里不存在。所以走
   `st_file_attributes`，别处退回 symlink 判定。
6. 边界是**通过链接到达的**时候，本身就不是边界 —— 候选根本身是链接时拒绝。

### 理由

第 1 条和第 2 条的分工是这次修复的核心教训：**边界检查与遍历约束是两件事**。
第 4 条证明「总是先解析再比较」是**部分**策略而不是完整策略，只是看起来完整。
第 5 条是实测决定的：`Path.is_junction()` 不存在这件事，只看文档很容易以为 symlink
判定就够。

### 团队自主判断

「拒绝优于跳过」「workspace 边界保留不替换」「冗余的边界检查保留并标注理由」都是
工程判断，不是合同条文。合同只要求隔离，没有规定用哪种隔离，也没有规定遇到链接时
该拒绝还是该跳过。

### 影响

- 行为**变更**：候选里合法指向共享只读内容的符号链接现在会被拒。安全的方向，但是
  一个变更。
- 冗余保留：`record_action` 在 append 前后各再查一次边界，而 `ledger_path` 已经约束
  同一条路径，所以这两处在 `ledger_path` 成功时不可能失败。**保留**并标注为纵深防御 ——
  删掉边界上的冗余检查并不明显是安全的，而为它写一个**不可能失败**的测试更糟。承重的
  那一条由独立测试钉住。

### known_limitations

- **TOCTOU 未关闭。** `write_candidate_bytes` 的前后检查对**已经发生**的越界是**检测**，
  不是**阻止**：字节已经落盘才被发现。要关掉它需要描述符相对的 no-follow 打开
  （`openat` + `O_NOFOLLOW` 一类），Windows 不提供等价能力。写在这里而不是靠措辞
  掩盖。
- 本 ADR 不改变信任存储、晋升策略或编排器。

### 复查条件

- 如果候选树需要合法承载指向共享只读内容的链接，则第 3、4 条要重新讨论；届时应当
  显式白名单，而不是恢复「静默跳过」。
- 如果出现 descriptor-relative no-follow 的跨平台方案，第 1 条的前后检查可以被真正的
  原子打开取代。

---

## ADR-017 修正 A：目录的 `st_nlink` 不是别名计数（GH-109，2026-09-29）

- 状态：amendment（修正已随 PR 合入前提交，待人工 review）
- AI 参与：AI-20260929-OPENCODE-4DF0E253EF9FDABD36AF6D7ECF0E97FC
- 关联：ADR-017 §4；`sandbox_runtime/src/aedl_sandbox/workspace.py`；
  `tasks/GH-109.yaml`；Issue #109

### 问题

ADR-017 §4 决定「`st_nlink > 1` 的**文件** → 拒绝」。实现写成了对**所有路径**
无条件检查，而这两者不是一回事。

POSIX 下**目录**的 `st_nlink` 是 `2 + 子目录数`（`.` 与每个子目录都是它的名字），
所以一个从未含过子目录的新目录也报 2。把它当别名计数读，于是 **Linux 上每一个
目录都被拒绝**，包括 `create_candidate` 刚刚建好的候选根。实测（基线 `c6d52d9`，
WSL2 Ubuntu-24.04）：sandbox 套件 438 项中 **56 项失败**（2 failures + 54 errors），
全部同源。

Windows 的 NTFS 不报告目录链接数（恒为 1），所以同一份代码在 Windows 全绿 ——
缺陷在它被书写的平台上不可见，这也是它能进入 `master` 的原因。

### 决策

**目录豁免该检查；文件维持拒绝。** 豁免不削弱守卫，理由是它没有覆盖到任何东西：

- 非特权进程**根本无法**对目录建硬链接（`link(2)` 返回 `EPERM`），所以
  「目录有多个名字」不是一种可利用的别名。
- 目录别名在真正发生的地方已被覆盖：`resolved` 在此之前已被
  `Path.resolve()` **完全解析**，指向或 junction 出去的目录是以其**真实目标**
  参与边界比较的；`_candidate_boundary` 另外在到达此处之前就拒绝
  「自身是链接」的候选根。
- 逃逸原语是**文件**（设计文件、ledger），它们全部仍是文件，仍被拒绝。

这是**实现向决策回归**，不是决策变更：ADR-017 §4 与合同 :378 原文写的都是
「**文件** link count」。因此 `contract_change: false`。

### 团队自主判断

- 豁免的是**检查的适用范围**，不是检查的强度；两侧都由测试钉住
  （目录必须豁免 / 文件仍必须拒绝），区分二者的只有文件目录位。
- 该缺陷在 Windows 上不可见，所以它的测试**在 Windows 上强制 POSIX 语义**
  （把目录报成 `nlink=2, S_IFDIR`）才使 Windows 的绿有证明力。
  两个变异体在 Windows 上均被杀：删 `S_ISDIR` 分支 → 目录测试以与 Linux
  完全相同的异常失败；把 `links > 1` 改成 `links > 99` → 文件测试报
  `WorkspaceEscapeError not raised`。
- 「在看不见缺陷的平台上强制可见的语义」是本条修正里可复用的做法，与
  `PR1-LINUX-PATH-FLAVOUR`（POSIX flavour 模拟）是同一原则的两次应用。

### 影响

- **行为变更**：Linux 上候选操作从「全部拒绝」恢复为可用。这是修复，不是放宽。
- 这 54 项此前是 `setUp` 内的 **error**，不是断言失败 —— 也就是说候选隔离守卫在
  Linux 上**从未被执行过**。修好后它们开始真正运行，并立即暴露出一个被掩盖的
  第三个缺陷（`os.rmdir` 移除 symlink，POSIX 报 `ENOTDIR`）。该修复作为
  GH-109 的范围修正 A1 记录，并已先呈交 Owner。
- 不改信任存储、晋升策略或编排器。

### known_limitations

- 目录的「多名字」在 POSIX 上无法被无特权进程制造，因此该豁免在**本语义下**
  安全；若将来引入容器/命名空间/用户命名空间等使 `link(2)` 对目录可用的机制，
  本条需复查。
- `st_nlink` 之外的别名手段（bind mount、overlay）不在此检查覆盖范围内，
  本条也不声称覆盖。

