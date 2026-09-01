# 三仓库审查：boardsmith / NextBoard / kicad-happy 对 AEDL 的价值

> 日期：2026-09-01 ｜ 性质：内部工作分析，非正式 Evidence
> 方法：并发 Explore 子代理，GitHub API + raw 源码 + CI + license 逐文件核实；凡未抓到源码一律标"未核实"，不据 README 推断实现。
> 对 AEDL 的"帮助"按四维度评估：①可抄/可吸收机制（给路径证据）②工程细节参考价值 ③护城河撞车需警惕 ④README 夸大需剥掉。

---

## 0. 三句话结论

1. **kicad-happy（1020★，MIT，Python）—— 对 AEDL 工程价值最高**：它是一个"确定性 KiCad 分析工具包 + agent skill 包"，不是 LLM agent runtime；其 `S-expression 解析器 + 结构化 evidence JSON + deterministic analyzer + LLM review` 架构，正是 AEDL 可吸收的"让 LLM 别直接啃 KiCad 文件"的工具层。
2. **boardsmith（30★，AGPL-3.0，Python）—— 概念最撞、但实现未完全透明**：HIR/provenance/澄清回路/固件编译器是真实源码；但 212 元件、ERC repair、Gerber、DRC/sim 多为 README 声称，且 **AGPL 强 copyleft 对闭源目标有传染风险**。
3. **NextBoard（351★，声明 MIT 但无标准 LICENSE 文件）—— 是"硬件方案设计 Agent 工作流/插件"，不是生成引擎**：有价值的是需求冻结/Gate 1-6/独立评审 Agent/供应链证据链这些**流程治理机制**；自动 EDA 生成、ERC/DRC/sim、BOM/价格引擎均未抓到源码。

---

## 1. kicad-happy —— 最值得吸收的"工具层"

### 1.1 它到底是什么（已核实）
- 不是传统 KiCad 插件，也不是完整 LLM agent runtime，而是**面向 AI coding agent 的确定性 Python 分析工具包 + skill 包**（Claude Code/Codex/Copilot CLI 消费其 JSON 输出）。
- 主语言 Python，MIT，1020★/83 fork，最近 push 2026-08-20，CI 存在（compile-check / skill-metadata / analyzer smoke / harness smoke / schema-contract suite）。
- 核心模块（均已抓源码验证）：
  - `skills/kicad/scripts/sexp_parser.py`：KiCad S-expression 通用解析器
  - `skills/kicad/scripts/analyze_schematic.py`：解析 `.kicad_sch` → 组件/网络/引脚连接/BOM/子电路检测
  - `skills/kicad/scripts/analyze_pcb.py`：解析 `.kicad_pcb` → board/layers/footprint/routing/vias/zones/DFM + connectivity graph
  - `skills/emc/scripts/analyze_emc.py`：几何规则+公式的 EMC 预合规风险报告（非 full-wave）
  - `skills/spice/scripts/simulate_subcircuits.py`：生成 ngspice testbench 并运行（依赖外部 ngspice）
  - `skills/bom/scripts/bom_manager.py`：BOM 字段标准化/MPN 分类/缺失检测/CSV
  - `skills/datasheets/scripts/datasheet_verify.py`：datasheet 抽取缓存 vs 原理图连接比较（**datasheet 抽取依赖 LLM/Claude extraction pipeline**）
  - `skills/kicad/scripts/finding_schema.py`：统一 findings（severity/confidence/evidence source/fix type）
  - `skills/kicad/scripts/schema_codec.py`：dataclass→JSON Schema；`inputs_builder.py`：source hash/run_id envelope

### 1.2 对 AEDL 的可吸收点（给路径证据）
| 可吸收机制 | 证据路径 | 建议 |
|---|---|---|
| KiCad S-expression 解析器 | `sexp_parser.py` | AEDL 若做 KiCad 自动化，直接复用/借鉴，别重写 |
| 结构化 evidence envelope | `inputs_builder.py` / `schema_codec.py` / `finding_schema.py` | 与 AEDL 的 evidence 思想同向，可作为中间 JSON schema 参考 |
| deterministic analyzer + LLM review 分层 | `analyze_schematic.py` / `analyze_pcb.py` / `signal_detectors.py` | **让 LLM 读结构化 JSON 而非直接啃 `.kicad_sch`**，比"LLM 直接改文件"可靠 |
| EMC/SPICE/DFM 分层工具 | `analyze_emc.py` / `simulate_subcircuits.py` | 可作为 AEDL"确定性工程验证器"的参考实现 |
| datasheet cache + LLM extraction bridge | `datasheet_verify.py` | 混合架构：LLM 抽取→cache→确定性 verify |

### 1.3 护城河撞车与夸大
- 撞车点多为公开 KiCad 格式/通用 EDA 数据结构，**护城河有限**；真正差异在 AEDL 的 agent 规划层、制造链/采购/变更约束、fail-closed 门禁与签名验证。
- 夸大需剥掉："AI agent 本体"叙事（实为 tool/skill 脚本）、"every net/every voltage/catches real bugs"强覆盖声明、datasheet 抽取"no ML"（实际依赖 LLM extraction）。

---

## 2. boardsmith —— 概念最撞、AGPL 需警惕

### 2.1 已核实（真源码）
- 定位：`Text prompt → KiCad schematic, BOM, firmware`，入口 `boardsmith_cli/main.py`（`boardsmith build-project --prompt ... --target esp32`）。
- AGPL-3.0-or-later，30★/3 fork，仅 1 commit，CI 用 `BOARDSMITH_NO_LLM=1` 跑 pytest。
- 真实现模块：
  - `shared/models/hir.py`：**HIR（Hardware Intermediate Representation）**，含 `Provenance(source_type/source_ref/confidence/evidence)` —— 这是它最有价值的可追溯结构
  - `shared/agents/clarification_agent.py`：`RequirementsClarificationAgent`（B1 前问需求缺口）+ `ComponentChallengeAgent`（选型后挑战高风险选择），支持 none/single/auto
  - `compiler/boardsmith_fw/cli.py`：固件编译器（Eagle/KiCad schematic→ESP32/STM32/RP2040 固件），`import`/`generate`/`research` 命令
  - `pyproject.toml`：LLM 为 optional deps（anthropic/openai/pdfplumber），`--no-llm` 离线模式有 CI 支撑

### 2.2 未核实（README 声称为主）
- "212 verified components"（有知识库目录，数字未源码逐项核实）
- ERC auto repair（README 详述 ERCAgent + RunERCTool + WriteSchematicPatchTool + 5 次迭代 stall detection，但关键实现文件抓取失败）
- `boardsmith verify` 6 个 rule-based tools（仅列名，未抓到实现）
- Gerber/BOM 生成、DRC/sim、完整 fail-closed gate —— 均未抓到源码证据

### 2.3 对 AEDL 的价值与风险
- **可吸收**：HIR 作为跨视图语义中枢；provenance/evidence/confidence；澄清回路；离线知识库 + LLM 可选；fw compiler 与 schematic 分离。
- **撞车**：与 AEDL"prompt→KiCad+BOM+firmware 自主 agent"叙事高度重合，HIR 概念可能重叠——**若 AEDL 也做板级语义验证/跨视图一致性/firmware-from-schematic，核心叙事会撞**。
- **风险**：**AGPL-3.0-or-later 强 copyleft**，若 AEDL 有闭源/商业目标，引用其代码有传染风险；参考其机制时建议只借鉴设计、不复制代码。

---

## 3. NextBoard —— 流程治理可借鉴，生成能力未实现

### 3.1 它到底是什么（已核实）
- **不是传统工程代码库，而是 AI Agent/Skill 工作流仓库**：给 Claude Code/Codex/Cursor 加载一套"硬件方案设计流程"。
- 351★/51 fork，声明 MIT（但 GitHub API license=null，**无标准 LICENSE 文件**，法律层面需作者确认），最近 push 2026-05-05，**无 GitHub Actions CI**。
- 核心资产（均已抓源码验证）：
  - `skills/hardware-solution/SKILL.md`：技能入口，快速/专业模式
  - `references/design-workflow.md`：需求冻结→架构候选→选型→输出→评审→模块原理图
  - `references/verification-gates.md`：**Gate 1-6**（README 写"7 阶段"，与文件有出入）
  - `agents/hardware-reviewer.md`：**独立评审 Agent**，5 维（Completeness/Risk/Implementability/Cost/Validation），5 轮 PASS/CONCERN/FAIL
  - `references/sourcing-and-risk.md`：datasheet 来源优先级、替代料策略、供应链风险
  - `references/domestic-sources.md`：国产 MCU/模拟/电源/无线模组来源清单
  - `tests/validate.py`：文档结构/引用/Gate 一致性校验（非硬件测试）

### 3.2 未核实（README 声称为主）
- 自动下载 datasheet、自动 BOM 生成、自动价格计算、自动 KiCad/立创 EDA 文件生成、自动 ERC/DRC、自动电路仿真、RAG 向量库 —— **均未抓到源码**。Gate 是 Agent 工作流规则，不是可执行测试/验证程序。

### 3.3 对 AEDL 的价值
- **可吸收**：需求冻结、专业/快速模式、三类架构候选（国产/海外/混合）、Gate fail-closed 语义、独立评审 Agent 五维模型、供应链证据链要求、国内器件来源清单、文档一致性测试。
- **撞车**：与 AEDL"硬件产品需求→架构→选型→BOM/风险→PCB 方案"流程叙事、独立评审 Agent、需求冻结+Gate 门控工作流存在明显撞车风险。
- **差异化建议**：AEDL 应强化**可执行验证**（ERC/DRC/sim/DFM 自动检查）、真实 EDA 文件生成与闭环迭代、可复现实验证据、数据级供应链/制造集成——这些正是 NextBoard 没有的。

---

## 4. 三仓库横向对比（对 AEDL 的价值排序）

| 维度 | kicad-happy | boardsmith | NextBoard |
|---|---|---|---|
| 类型 | 确定性分析工具包+skill | prompt→HIR→schematic/BOM/fw 管线 | Agent 工作流/插件 |
| 许可证 | MIT（干净） | **AGPL-3.0（强 copyleft，慎用）** | 声明 MIT 但无 LICENSE 文件 |
| 工程参考价值 | **高**（S-expression 解析、evidence envelope、deterministic analyzer 分层） | 中（HIR/provenance/澄清回路设计） | 中（流程治理/Gate/评审 Agent） |
| 可执行验证（ERC/DRC/sim） | 部分（EMC/SPICE 真代码，依赖 ngspice） | 未核实 | 未核实 |
| 护城河撞车 | 低（多为公开格式） | **高**（叙事+HIR 概念） | 中（流程叙事+评审 Agent） |
| README 夸大 | 中（"every/catches real bugs"） | 高（212 元件/ERC repair/Gerber） | 高（自动生成/价格/EDA 输出） |

**给 AEDL 的行动建议**：
1. **优先吸收 kicad-happy 的工具层**：S-expression 解析器、结构化 evidence JSON、deterministic analyzer + LLM review 分层——这与 AEDL 的"机器解析 + 独立合同"方向一致，可显著降低"LLM 直接啃 KiCad 文件"的风险。
2. **借鉴 boardsmith 的 HIR/provenance 设计**，但**注意 AGPL 传染**，只借鉴设计不复制代码；同时警惕其"prompt→PCB/fw"叙事与 AEDL 的直接撞车。
3. **借鉴 NextBoard 的流程治理**（需求冻结/Gate/独立评审 Agent/供应链证据链），但不要被其 README 的"自动生成"表述迷惑——它没有可执行验证引擎。
4. **所有"尚未发现等价实现"的 AEDL 主张**，在纳入 AIC 报告前，需按此前校准纪律：对每个 competitor 给"Feature / AEDL evidence / Competitor A-D search evidence / Negative finding confidence"，措辞一律用"截至 2026-09-01 对所列公开源码的检查中，尚未发现等价实现"。

（本文件为工作分析，未提交、未进 Evidence/合规台账，供人工核阅。）