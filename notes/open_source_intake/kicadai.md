# KiCadAI 开源项目 Intake 报告（六步协议）

> Repo: https://github.com/dshills/KiCadAI
> Commit SHA: `4f18765776e4c2f53a644475fc5c8611b8131aca`（本地克隆 `notes/open_source_intake/_kicadai_repo/`，浅克隆 depth=1，无本地历史；上游公开页称 1,734 commits，最后 push 2026-08-24）
> Date Reviewed: 2026-08-31
> License: MIT（LICENSE 文件全文核对，Copyright (c) 2026 Davin Hills；允许商用、修改、再分发，需保留版权声明）
> 审查方法：本地 git clone 后逐文件阅读源码（`internal/` 90+ 子包、`cmd/` 25 个入口、CI workflow、关键 spec）；对照既有 `notes/competitor-collision-analysis-2026-08-30.md` 第二轮结论逐项复核。
> 证据标记：`已验证`（源码直接读到）/ `未核实`（本轮未查证，不据此断言真或假）/ `复测待环境`（源码已读，但运行级验证本轮未执行）。
> 规模事实：824 个 `_test.go` vs 809 个非测试 `.go`（测试:源码 ≈ 1:1）；Go 1.23+，KiCad 10.0.3 为记录的参考版本。

---

## STEP 1 - CLAIM（它声称做了什么）

README（`README.md`）与 ROADMAP（`specs/ROADMAP.md`，2026-08-20 版）声称：

| 声称 | 分类 | 源码核对结果 |
|---|---|---|
| "AI proposes. KiCadAI proves—or refuses."：行为需求进，确定性证据支撑的原生 KiCad 工程出，证明不了就拒绝 | Implemented | `已验证`：架构与源码结构一致（见 STEP 2）；运行级 demo 数字（2 架构/194 仿真/6,326 角点/15/15 布局/12/12 布线/ERC-DRC 0/0/round-trip 0 差异/两次生成同哈希）`复测待环境`，本轮未运行 `make public-demo` |
| 生成前确定性能力评估：supported / experimental / unsupported 三态 + 证据链接 | Implemented | `已验证`：`internal/capabilitygate/assessment.go`（Classification 三常量 + Evidence 四状态 + SHA-256 封印） |
| unsupported 请求不突变工程、返回结构化 gaps；experimental 需显式 opt-in 且不得进 fabrication-ready | Implemented | `已验证`：classification 推导 + `FabricationReadyEligible = (classification == supported)` |
| frozen corpus（SHA-256 内容寻址）+ evidence/report/corpus 绑定 | Implemented | `已验证`：`internal/capabilityevaluation/artifacts.go`（`CorpusSHA256` 不匹配即报错）+ `specs/adversarial-function-corpus/` 下 BASELINE/FINAL 报告各带 `.sha256` |
| capability-eval 拒绝非法输入并 exit 非 0 | Implemented | `已验证`：`cmd/kicadai-capability-eval/main.go` 等系列 `os.Exit(1)` |
| 直接 KiCad 工程/原理图/PCB writer + writer 正确性 + 归一化 round-trip 验证 | Implemented | `已验证`：`internal/kicadfiles/`（93 个 Go 文件，含 checks/design/library/pcb/project/roundtrip/schematic/sexpr 子包；roundtrip 在副本上跑 KiCad CLI 并比对归一化结果） |
| ERC/DRC 经 kicad-cli subprocess，要求证据时缺失即 fail-closed | Implemented | `已验证`：`internal/designworkflow/kicad_checks.go` + `internal/kicadfiles/checks/runner.go`（注释原文："A requested ERC or DRC check always fails closed when the CLI or its evidence is unavailable"） |
| 仿真（MNA：非线性/瞬态/直流扫描/热/电热） | Implemented | `已验证`：`internal/simmodel/` 含 `mna_solver.go`、`mna_nonlinear.go`、`mna_transient.go`、`mna_dc_sweep.go`、`mna_thermal.go`、`mna_electrothermal.go` 等全套纯 Go 实现及配套测试；数值正确性 `未核实` |
| 确定性修复回路（validation → repair → 复验） | Implemented | `已验证`：`internal/repair/`（39 文件）+ `internal/repairloop/`；修复正确性 `未核实` |
| 对抗性夹具（adversarial corpus） | Implemented | `已验证`（存在性）：`specs/adversarial-function-corpus/`、`specs/adversarial-multi-function-composition/`、`specs/adversarial-*` 多个；README 所称具体数字（如"10 个"）`未核实`——不同 spec 记录的数字不同（held-out 合成审计记"1 个矛盾输入 + 4 个对抗输入 fail closed"） |
| clarification loop（澄清回路） | **仅状态，非回路** | 见 STEP 3 第 4 条：源码只有 `needs_clarification` 单向拒绝状态，无问答回路 |
| v1.0.0-rc.1 发布冻结；"arbitrary-circuit generation and fabrication approval are not v1 claims" | 诚实边界 | `已验证`：ROADMAP 原文如此声明，且 README 明确"This is an ERC/DRC-checked deterministic candidate, **not a fabrication release**. Human … review remains required." |

**与同类项目显著差异**：README/spec 无发现 roadmap 条目冒充实现；且对公开 demo 同时给出"证明运行"（`make public-demo`）与"拒绝运行"（`make public-demo-refusal`：热/SOA 超限请求必须 exit 失败且不产出工程）两个方向的自证入口——把"会拒绝"本身当作可验证主张，这是 AEDL 同款的证明哲学。

---

## STEP 2 - SOURCE（源码实际上做了什么）

- **语言/框架**：纯 Go（无 LangGraph/无外部编排框架），MIT，单作者 dshills（PR 仅 2 个，第二个来自其自己的 codex 分支合并）。
- **能力门（判决核心）**（`internal/capabilitygate/assessment.go`，`已验证` 全文阅读）：
  - `Classification`：`supported` / `experimental` / `unsupported` 三态。
  - `Evidence.Status`：`verified` / `inferred` / `missing` / `failed` 四档；verified 证据必须有稳定 source + SHA-256 digest。
  - `Assessment` 结构含 `Requirements[]`（每条能力声明挂证据 ID）、`Gaps[]`、`Risks[]`、`Checkpoints[]`；`sealAssessment` 对整体做哈希封印。
  - `FabricationReadyEligible` 仅在 supported 时为 true。
  - Checkpoint 语义：工作流检查点只能"保持或降低"置信度，不能升高（防止后段粉饰前段缺口）。
- **ERC/DRC 链路**（`已验证`）：
  - `internal/designworkflow/kicad_checks.go`：`RunKiCadChecks` 发现 CLI 失败 → `SeverityBlocked` issue；解析 KiCad JSON 报告为结构化 findings（含 RepairCategory 分类、建议文本）；工具错误四分类：`ToolErrorNone` / `NoOutputCrash` / `MissingReport` / `ReportParse`——**工具故障与设计违规显式分离，工具故障绝不冒充"0 违规"**。
  - `internal/kicadfiles/checks/runner.go`：`exec.CommandContext` + 1MB 输出限幅 + 退出码捕获 + 跨平台 CLI 发现；KiCad-backed 测试由 `KICADAI_RUN_KICAD_CLI` 环境变量显式开启（默认 hermetic，CI 不依赖 KiCad）。
- **仿真引擎**（`已验证` 存在性）：`internal/simmodel/` 纯 Go MNA（节点分析法）——solver/非线性/瞬态/直流扫描/偏置/热/电热/DC-DC/稳压器/控制环路/容差全套 + 大量测试。不依赖外部 SPICE。
- **AI 参与边界**（`已验证`）：`internal/aiprovider/` 的 OpenAI provider 仅做 `GenerateIntent`（生成行为意图）；输出信封强校验（"must contain exactly one JSON object"、字节上限、schema 版本检查、malformed 错误分类）；`RecordedProvider` 用录制 fixture 做确定性回放测试，live 测试需显式环境变量。**架构、选型、计算、仿真、生成、布局、布线、验证、最终 pass-or-refuse 全部是确定性 Go 代码**。
- **澄清机制**（`已验证`）：`internal/intentplanner/plan.go` 的 `PlanStatusNeedsClarification`（得 50 分）+ `Clarifications[]` 结构化 notes（ID/Path/Message/Suggestion）；有 clarifications 即整个 plan 判为 needs_clarification。`未发现`任何用户回答输入路径（无 UserAnswer/answerFile/stdin 交互）。
- **writer 与 round-trip**（`已验证`）：`internal/kicadfiles/roundtrip/` 把生成文件复制到临时工作区，跑 KiCad CLI（`sch upgrade --force` 等）后与原件归一化比对——"KiCad 自己保存一遍后仍相同"作为 writer 正确性证据。
- **promotion 工具链**（`已验证`）：`toolchain/kicad-promotion.lock.json` 锁定 KiCad 10.0.3 + 各平台信任根（symbols/footprints 路径）；clean-checkout 两遍执行 + 归一化比对 + 内容寻址离线证据。
- **CI**（`已验证`）：`.github/workflows/` 三条——`ci.yml`（offline quality：gofmt 变更范围检查、golangci-lint、promotion 契约测试、冻结语料核验）、`kicad-promotion.yml`、`release.yml`；actions 全部用 pinned SHA 引用。
- **反过拟合纪律**（`已验证`）：`specs/external-review-mitigation/AUDIT.md` 声明"No production code recognizes a matrix path, scenario ID, coordinate, board size, block name, net name, or fixture hash. Scenario-specific identities occur only in test data and test bindings."——生产代码不识别场景 ID/坐标/板尺寸/网络名/fixture 哈希。
- **外部评审流程**（`已验证`）：`specs/external-review-mitigation/` 记录一次 6 项 findings 的独立外部评审，全部以通用行为修复并纳入发布回归阶梯（每条 finding 带对应 commit 与 CI run 链接）。

---

## STEP 3 - FAILURE（它最烂的地方）

按 AEDL 视角，从重到轻：

1. **单点维护，bus factor = 1**：1,734 commits 单作者；PR 仅 2 个（其一来自作者自己的 codex 分支）。项目工程质量和纪律罕见地高，但可持续性完全系于一人。
2. **能力包络是有界的（by design，但必须看清）**：supported 集合只有被 promotion 证据覆盖的窄域（内置 25 个 block，多数仍是保守 `structural` 级验证；README 明确"arbitrary-circuit generation … are not v1 claims"）。它不是通用电路生成器——它对"知道自己不知道什么"极其严格，这是优点；但 AEDL 在叙事时不得把它当"完整替代品"，也不能因此低估其机制质量。
3. **v1.0.0-rc.1 冻结未发版**：release freeze 状态，正式 v1 未出；发布工件链（bounded public contract、release artifacts）按 ROADMAP 仍在收尾。
4. **clarification 不是 loop**：`needs_clarification` 是一次性拒绝状态（plan 打 50 分停下报告），用户必须自己改需求再重跑，没有"提问→回答→继续"的交互路径。对 AEDL 而言：**这反向印证了 requirements_contract + 人工回答路径的价值**——KiCadAI 把歧义处理成"拒绝"，AEDL 把歧义处理成"合同化对话"，两者是不同的产品决策，但 AEDL 的 P1 已实现交互问答闭环而 KiCadAI 未做。
5. **运行级证据本轮未复测**：public-demo 的数字（两次生成同哈希等）是 README 声称，本轮 `NOT_RUN`（需 Go 1.23 + KiCad 10.0.3 环境 + 数小时），不构成 AEDL 侧的独立证据。
6. **平台边界**：README 称 demo 检测"standard macOS and Linux KiCad installations"；Windows 下的 promotion 路径 `未核实`（CI 在 ubuntu 跑，toolchain lock 首平台为 darwin/arm64）。AEDL 在 Windows 上复用其命令时需自行验证。
7. **测试虽多但默认 hermetic**：默认 Go 测试不跑 KiCad-backed 证据；KiCad 级验证集中在 opt-in 套件与 promotion lane——阅读其"全绿"时必须区分是哪一层。

---

## STEP 4 - REUSABLE（哪些能力可以合法复用）

| 能力 | 复用方式 | 依据 |
|---|---|---|
| **生成前能力评估（pre-mutation capability assessment）**：三态分类 + 每条能力声明挂证据 ID + 拒绝时不突变 | **Adapt**（借机制重实现） | 这是 AEDL 尚缺的一层：AEDL 的门禁是"生成后验证"，KiCadAI 证明了"生成前评估"可以工程化且与 fail-closed 天然兼容。MIT 允许；借机制不构成衍生作品（法律细节 `TO_VERIFY`） |
| **工具错误与设计发现分离的四分类**（None/NoOutputCrash/MissingReport/ReportParse） | **Adapt** | AEDL gate_core 的"malformed evidence must never become green"同型，但 KiCadAI 的四分类更细；AEDL 的 kicad-cli 封装可直接借鉴此分类法 |
| **Checkpoint 单调性**（置信度只能保持或降低） | **Adapt** | 防止后段证据粉饰前段缺口的简单而有效的语义约束 |
| **RecordedProvider（AI 输出录制回放）** | **Adapt（近期可落地）** | AEDL 的 `gates/requirements_runtime.py` LLM 建议层当前测试用构造输入；录制/回放 fixture 可让 LLM 层测试确定性化 |
| **纯 Go MNA 仿真引擎**（simmodel） | **Direct Reuse 候选（M3+）** | MIT；若 AEDL 未来做 simulation-grounded 检查（策略文档 §4.2 的 INSUFFICIENT_EVIDENCE 场景），这是现成引擎。当前 AEDL 不需要，不引入 |
| **corpus freeze + SHA256 + 内容寻址证据 + promotion 两遍执行比对** | Idea Only（对齐确认） | AEDL 已有等价物（manifest 哈希链、run_manifest）；KiCadAI 证明该模式可推到"能力晋级"场景 |
| **反过拟合声明纪律**（生产代码不识别场景 ID/坐标/fixture 哈希） | **Adapt** | 值得写进 AEDL 的 gate 代码审查清单：门禁代码不得识别 board_id/坐标/料号特例 |
| 其 Go 代码本体（含 writer、routing、placement） | **暂不引入** | AEDL 的 M2 已用 KiCad 真实工程 + 自有工具链；引入其代码收益低、维护成本高（单作者上游、Go 技术栈差异） |

**License 义务**：MIT。若未来 Direct Reuse 其代码（如 simmodel），需在 `docs/compliance/THIRD_PARTY_RESOURCES.md` 登记（含 commit SHA、MIT 声明保留）。本轮零代码复制，仅机制借鉴，无新增第三方登记项。

---

## STEP 5 - AEDL TRANSFORM（接入后语义变化）

核心转化（策略文档 §4.4 的落地版）：

```text
KiCadAI capability assessment
  （生成前三态评估 + 证据链接 + unsupported 拒绝不突变 + checkpoint 单调降级）
        ↓ AEDL 重新定义
1. AEDL 保持"生成后门禁"主轴（10 gate），新增"生成前能力预检"层：
   NL → requirements_contract → capability preflight（supported/experimental/unsupported）
   → unsupported/超 envelope：STOP，不进入 intent/生成，不烧算力
2. 判决体系不外包原则不变：
   KiCadAI 的 assessment 是它自己的判决层；AEDL 吸收的是"能力边界显式化"的
   机制形态（三态+证据挂链+单调降级），不是接它的代码来当 AEDL 的门禁。
3. 澄清维度的反差利用：
   KiCadAI = 歧义 → needs_clarification 单向拒绝（无回答路径）
   AEDL  = 歧义 → blocking question → 人工回答 → requirements_contract 固化
   （P1 已实装；KiCadAI 的拒绝式设计反向验证了 AEDL"对话式合同"的差异化价值）
4. 工具错误四分类并入 AEDL 的 kicad-cli 封装语义：
   工具崩溃/报告缺失/报告不可解析 ≠ 0 违规，各自独立成 fail 原因
```

**AEDL 由此获得**：一个被工程化验证过的"能力预检"机制模板；工具错误分类法；AI 输出录制回放测试模式；对"拒绝即主张"（refusal demo）这种自证形式的合法性确认。

**AEDL 不获得**（诚实边界）：KiCadAI 的 MNA 仿真深度、确定性架构搜索、promotion 全链路——这些是它的核心资产，AEDL 借不走也不必借（AEDL 的差异化在验证纵深与人工签发，不在生成器本身）。

---

## STEP 6 - VERIFY（怎么证明吃进去以后更好）

按策略文档要求，吸收后必须给可证伪验证（以下为本轮可复测项 + 未来实装时的 fixture 计划）：

1. **对 KiCadAI 的既验事实可直接复测**（本轮源码级 `已验证`，运行级留待环境）：
   - `go run ./cmd/kicadai-capability-eval`（非法输入）→ 期望 exit 非 0。
   - 请求 ERC/DRC 而 CLI 不可用 → 期望 SeverityBlocked（非 skip、非 0 违规）。
   - `make public-demo-refusal` → 热/SOA 超限请求 exit 失败且不产出 KiCad 工程。
2. **AEDL 侧 fixture（若采纳 capability preflight，M3 实装时）**：
   - F1：构造超出 AEDL 能力 envelope 的 NL 需求（如"48V/20A BLDC 控制器"）→ preflight 必须 unsupported/STOP，不产出 intent，不进入后续 gate。
   - F2：experimental 域需求未显式 opt-in → 必须停在 preflight，不生成。
   - F3：preflight 声称 supported 的每条能力声明必须挂证据 ID；缺证据的 supported 判定 → gate FAIL。
   - F4：将 F1-F3 纳入 `gates/semantic_fault_injection.py` 常驻故障注入（沿用 AEDL meta-verification 模式）。
3. **对照（Before/After）**：M2 复盘——M2 是人工写定 intent；若当时有 preflight，"ESP32-C3 载板"属 supported envelope 会放行，而"高压大电流"类请求会在零算力处停下（定性对照，写入实装 PR 的动机部分）。
4. **证据**：本 intake 报告即研究证据（EVID 登记按 AGENTS.md 触发条件另行执行）；实装后再补运行记录。

---

## 附：与竞品碰撞分析的对照（两轮结论校准）

本报告对 `notes/competitor-collision-analysis-2026-08-30.md` 的 KiCadAI 部分做**重大校准**：

- 碰撞分析判"capability/evidence 机器实现为真（已验证）"——**本轮维持且加固**：`capabilitygate`、`capabilityevaluation`、corpus SHA256、`os.Exit(1)` 全部源码复核成立。
- 碰撞分析判"KiCad 生成、ERC/DRC subprocess、simulation/thermal/SOA、10 个 adversarial 夹具、clarification loop 均只见 README/spec/readiness 文档、未见源码调用链"——**本轮判其中大部分为误判（calibration 失败）**：
  - KiCad 生成 writer：源码存在（kicadfiles 93 文件）`已验证`；
  - ERC/DRC subprocess：源码存在（kicad_checks.go + runner.go，全仓 64 个文件含 exec 引用）`已验证`；
  - simulation/thermal：MNA 引擎源码存在（mna_thermal/mna_electrothermal 等）`已验证`（数值正确性仍未审）；
  - SOA 具体实现与"10 个夹具"的准确数字：`未核实`；
  - clarification loop：**碰撞分析方向部分成立**——存在澄清机制但是单向拒绝状态，非交互回路。
  - 误判原因与碰撞分析 §5 自我教训同型：其会话工具当时抓不到仓库内容（"把活仓库判成 404"同源问题），"未见"被写成了过强的否定结论。本轮用本地克隆消除了该失败模式。
- **威胁等级更新建议**：KiCadAI 从"值得升档但先别标红"升为**当前四个研究对象中验证纪律最强、能力评估+生成链路最完整的真实现**。AEDL 的差异化必须严格落在自己已实装的交互澄清合同、跨视图哈希绑定、人工制造签发、经验学习门禁上，不得再依赖"它没有生成链路"这类已被证伪的对照点。

### kicad-ai（amcolex）遗留未决项更新

碰撞分析 §6.1 要求人工浏览器定案 `github.com/amcolex/kicad-ai` 真实性。本轮（2026-08-31）以 WebFetch 访问该 URL，返回的是 **GitHub 404 渲染页**（非网络故障：页面为完整导航的"找不到仓库"态，含登录回跳地址）。结合上轮会话两轮抓取 404：现有证据一致指向**该 URL 当前无公开仓库**。但仍不能排除"私有/改名/已删除"，"从未存在"的强结论维持 `待人工浏览器定案`。在其定案前，AEDL 材料中继续不引用 kicad-ai 的任何描述（findings ledger / waivers / done-gate / 4-4 USB case）。

（本文件为内部工作分析，按 AGENTS.md 留痕规则，关联 AI-20260831-004，PENDING_HUMAN_REVIEW。）
