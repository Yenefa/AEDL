# FUSION_MAP — AEDL「AI + 开源」融合映射

> 用途：AIC「AI+开源」评分项「AI 与开源融合」的证据资产。说明 AEDL 的核心能力是什么、AI 在其中做什么、哪些开源资源直接参与、AEDL 自研模块是什么、移除 AI 会损失什么、如何验证。
> 素材来源（逐项标注，不脑补）：
> - `AGENTS.md` §8.2（融合主张边界）
> - `notes/competitor-collision-analysis-2026-08-30.md` §3（判定语言与反证检索）
> - `notes/open_source_intake/circuitbot.md` / `kicad-mcp.md` / `kicadai.md`（六步 intake 结论）
> - `notes/open_source_intake/AEDL_开源项目吸收与再设计策略_2026-08-30.md`（吸收策略）
> - `docs/compliance/DECISIONS.md`（ADR-004/ADR-005）、`docs/evidence/EVIDENCE_INDEX.md`、`docs/compliance/THIRD_PARTY_RESOURCES.md`（RES-001..007）、`docs/knowledge/PROJECT_PITFALLS.md`（PIT-20260830-001）
> 状态：DRAFT，`PENDING_HUMAN_REVIEW`。本文件是融合主张的索引，不是许可证台账（许可证台账见 `docs/compliance/THIRD_PARTY_RESOURCES.md` 与 `notes/open_source_intake/THIRD_PARTY.md`）。

---

## 0. 一句话定位

AEDL（Autonomous Hardware Engineering Agent）不以重复实现现有 AI EDA 能力为目标，而是在吸收现有开源生态成熟能力的基础上，重点解决硬件 Agent 在**验证可信度、变更一致性、供应链约束、制造签发与经验闭环**上的工程问题：**AI 提议、开源工具执行、AEDL 确定性门禁裁决、人工签发**。

> **北极星**：本项目的终极目标是在受控流程下正确交付实体板卡；以下融合主张是达成该目标的手段。Sandbox 降低的不是“画板子的难度”，而是“让板子一次做对的难度”——把验证从启发式赌博变为可验证的工程闭环（M2 六项缺陷 PIT-20260830-001 是这一转换的动因）。

本文件只主张"每次 `run_gates.py` 都真实执行的机器机制"；对每一套机制，用"截至检查日，在所审公开源码中尚未发现等价实现"单独列证据，并配反证检索留痕。**不使用"首创 / 领先 / 行业空白"字样。**

---

## 1. 融合总览（输入 / 输出 / 接口）

```text
用户自然语言需求
      │
      ▼
[LLM 建议层] gates/requirements_runtime.py        ← AI 提议（可失败，结构性不信任）
      │  提出澄清问题/假设（answer 恒 null，垃圾输入变 warning）
      ▼
[需求合同] gates/requirements/requirements_contract_v1.json   ← 确定性校验 C1-C7
      │  blocking 未答即 FAIL；"No preference" 显式记录；SHA256 自哈希
      ▼
[intent] src/hardware/m2-board/intent_v1.json     ← 引用合同 {sha256, path}
      │
      ▼
[生成/执行层] akcli-kicad / KiCad / freerouting / jlcpcb CLI   ← 开源工具层（SUPPORT）
      │  ops → 原理图 → PCB → 固件 → BOM → 交付物
      ▼
[10 门禁 fail-closed] gates/run_gates.py          ← AEDL 自研裁决层（确定性）
      │  erc / drc / bom / delivery / intent / ops /
      │  schematic_semantics / learning / requirements_contract / board_review
      │  + 常驻故障注入（校验器有效性自证）
      ▼
[人工制造签发] gates/board_review_v1.json         ← 只有具名人工可设 manufacturing_release=true
```

接口约定：所有跨层产物以 SHA256 内容寻址绑定真源（intent/网表/PCB/固件/BOM/CPL/Gerber/zip/manifest/合同），任一视图变更即哈希失配 fail。

---

## 2. 六大核心能力

### 2.1 10 门禁 fail-closed 验证链

- **核心能力是什么**：从 ERC/DRC/BOM/交付/意图/操作/语义/学习/需求合同/板级评审共 10 个门禁，全部以 `_safe_gate` 包装——"malformed evidence must never become green"（`gates/run_gates.py`）。任何结构异常、缺文件、坏 JSON/XML、未知 rule/severity、空视图一律 fail，绝不因"解析失败"而放行。
- **AI 做什么、为什么必要**：AI 生成被验证的产物（intent、ops、语义合同、BOM 快照、交付物），并编写/维护门禁代码本身。AI **不参与门禁判定**——判定全部是确定性代码。必要性的核心：硬件 Agent 的可信度取决于"结果凭什么可信"由谁定义；若判定由生成器自己（LLM judge）做，就是循环举证（PIT-20260830-001 教训，见 `docs/knowledge/PROJECT_PITFALLS.md`）。
- **哪些开源资源直接参与**：KiCad（`kicad-cli` 的 ERC/DRC 结构化 JSON 输出）、akcli-kicad（RES-005，ops 生成）、jlcpcb CLI（RES-006，库存查询）、freerouting（布线）作为**被验证的工具层**；CircuitBot 的 clarify 语义被反转吸收为第 10 门禁（requirements_contract，见 `notes/open_source_intake/circuitbot.md` STEP 5）。
- **AEDL 自研模块是什么**：`gates/run_gates.py`、`gates/gate_core.py`、`gates/requirements_contract.py`、`gates/schematic_semantics.py`、`gates/learning_gate.py`、`gates/export_delivery.py`、`gates/refresh_bom_stock.py`。
- **移除 AI 会损失什么**：门禁代码仍可运行（确定性），但"NL→intent→ops→原理图→PCB"的自动化生成链消失，退回纯人工设计＋机器验证；第 10 门禁的"LLM 建议问题"层消失（合同仍可人工填写，但澄清自动化损失）。
- **如何验证**：EVID-20260829-001（7/7 PASS，历史基线）；EVID-20260830-001（换料后 8/9 PASS，唯一 fail 为 board_review 待人工重签）；全量单测 95/95（AI-20260831-002 记录）。
- **判定语言（碰撞分析 §3 口径）**：截至 2026-08-30 对所列公开源码的检查中，尚未发现将"生成后验证"做成 10 门禁 fail-closed 链的等价实现。对照事实：CircuitBot 的 LLM judge 倾向评分记录（`未核实`其终局否决权）；NeuroBoard 失败后走 self_correction 继续而非 fail（碰撞分析 §2.2）。**反证检索**：需持续检索是否有商业/开源工具把"生成后验证"做成同等严格度的多门禁 fail-closed 链。

### 2.2 独立语义合同（schematic_semantics + requirements_contract）

- **核心能力是什么**：两层合同。① 数据手册约束写入独立合同 `gates/contracts/m2_schematic_contract_v1.json`，与 intent / KiCad XML 网表 / PCB pad-net / 固件常量四视图交叉验证（`gates/schematic_semantics.py`）；② 需求侧 `gates/requirements/requirements_contract_v1.json` 把"一句话需求"固化为可哈希绑定、blocking 未答即 fail 的工程合同（`gates/requirements_contract.py`，C1-C7）。
- **AI 做什么、为什么必要**：AI 读取数据手册提取约束、起草需求合同内容（LLM 建议层只**提出**问题与假设，不定义合同内容）、执行 M2 补录合同（`author` 标注 `retroactive`）。必要性：PIT-20260830-001 证明"原理图符合意图"≠"意图符合数据手册"；ERC/DRC 不理解 USB 信号身份、传感器地址选择或推荐启动网络。
- **哪些开源资源直接参与**：CircuitBot 的 clarify 五维框架（Adapt 借思想重实现，MIT `ff9b003`）；KiCadAI 的 capability assessment 机制形态（Adapt，MIT `4f18765`）；器件数据手册（RES-007）。
- **AEDL 自研模块是什么**：`gates/schematic_semantics.py`、`gates/requirements_contract.py`、`gates/requirements_runtime.py`（LLM 建议层，`parse_llm_proposal` 把 LLM 输出降级为问题草案）、`gates/contracts/m2_schematic_contract_v1.json`、`gates/requirements/requirements_contract_v1.json`。
- **移除 AI 会损失什么**：需求合同需人工逐条填写（M2 补录即"人工＋AI 协作"形态），"NL→合同→intent"自动化损失；数据手册约束提取需人工完成。
- **如何验证**：schematic_semantics gate（EVID-20260830-001 语义修复后 PASS）；requirements_contract gate（`tests/test_requirements_contract.py` 18/18，AI-20260831-002）；合同↔intent 单向绑定 + 语义哈希锁定（TASK-C 方案，`gates/requirements_contract.py` C4）。
- **判定语言**：截至 2026-08-30 对所列公开源码的检查中，尚未发现把"需求澄清结果"固化为带 SHA256 自哈希、blocking 未答即 fail 的工程合同的等价实现。对照事实：CircuitBot 的 clarify 是 fail-open（5 分钟超时继续、No preference 静默丢弃、结果仅存 state、零测试覆盖，`circuitbot.md` STEP 3）；KiCadAI 的 clarification 是单向拒绝状态（`needs_clarification`），非问答回路（`kicadai.md` STEP 3）。

### 2.3 常驻故障注入（meta-verification）

- **核心能力是什么**：`gates/semantic_fault_injection.py` 每次 run 注入故障夹具，必须全部被 caught 否则 fail——"校验器有效性自证"。5 个永久负向夹具同时污染多个派生视图，验证独立合同仍能识别共同模式错误。
- **AI 做什么、为什么必要**：AI 编写/维护故障夹具（`tests/fixtures/schematic_semantics/fault_*.json`）、分析故障注入报告。必要性："Even verification agents require verification"（碰撞分析 §5 元教训）——校验器本身可能失效，必须常驻自证。
- **哪些开源资源直接参与**：无直接开源代码参与（机制为 AEDL 自研）。KiCadAI 的 promotion evidence 是同一方向，但对象是"能力证据"而非"校验器对故障的捕获率"（碰撞分析 §3，需在报告中讲清此差异）。
- **AEDL 自研模块是什么**：`gates/semantic_fault_injection.py`、`tests/fixtures/schematic_semantics/fault_*.json`、`notes/m2-evidence-reset/generated/semantic_fault_injection_current.json`。
- **移除 AI 会损失什么**：故障注入仍运行，但夹具库不再增长，对新缺陷模式的覆盖停滞。
- **如何验证**：`semantic_fault_injection_current.json`（每次 run 生成）；EVID-20260830-001 记录 5 个负向夹具同时污染多个派生视图。
- **判定语言**：截至 2026-08-30 对所列公开源码的检查中，尚未发现将"校验器有效性自证"做成常驻门禁的等价实现（碰撞分析 §3 原句）。**反证检索**：KiCadAI 的 promotion evidence 是同一方向但对象不同，需在报告中讲清差异。

### 2.4 跨视图机器解析 + 哈希绑定

- **核心能力是什么**：intent / KiCad XML 网表 / PCB pad-net / 固件四视图机器解析交叉验证，全程 SHA256 绑定真源（ERC/DRC/BOM/CPL/Gerber/zip/manifest/合同）。
- **AI 做什么、为什么必要**：AI 生成各视图（intent→ops→原理图→PCB→固件）并编写解析器；哈希绑定与比对全部确定性。必要性：PIT-20260830-001 的"循环举证"——同一错误在多份文件高度一致反而制造"证据很多"的假象；旧 BOM/POS 彼此自洽但落后于当前 intent（`PROJECT_PITFALLS.md` 制造交付链事故）。
- **哪些开源资源直接参与**：KiCad（XML 网表导出、`kicad-cli`）；KiCad MCP 的 FTS5 连字符 MPN 教训（Adapt 为 AEDL 器件匹配对抗测试，`kicad-mcp.md` STEP 4）；KiCadAI 的 corpus SHA256 内容寻址（Idea Only 对齐确认，`kicadai.md` STEP 4）。
- **AEDL 自研模块是什么**：`gates/schematic_semantics.py`（四视图交叉）、`gates/export_delivery.py`（manifest 哈希链）、`gates/refresh_bom_stock.py`（库存证据哈希绑定）、`gates/requirements_contract.py`（intent 语义哈希锁定）。
- **移除 AI 会损失什么**：视图需人工生成，哈希绑定仍能验证一致性，但自动化生成链损失。
- **如何验证**：`delivery/manifest_v1.json`；EVID-20260830-001（交付物 21 行哈希绑定）；`tests/test_run_gates.py` 的 stale self-consistent BOM/POS 拒绝测试、CPL 与当前 PCB 临时导出逐字段一致测试。
- **判定语言**：截至 2026-08-30 对所列公开源码的检查中，尚未发现以"机器解析＋独立合同"实现"生成器不当裁判"的等价实现。对照：kicad-ai（amcolex）想用"fresh LLM reviewer"实现同目标，路径不同，且其仓库真实性仍待人工浏览器定案（碰撞分析 §6.1，`kicadai.md` 附节 2026-08-31 WebFetch 得 GitHub 404 渲染页）。**未定案前不写"我们独有"。**

### 2.5 人工制造签发 + 撤销重签

- **核心能力是什么**：`gates/board_review_v1.json` 的 `manufacturing_release` 只能由具名人工复核设置；撤销后 `human_resign_required=true`，必须人工重签；AI 不得自行签发。
- **AI 做什么、为什么必要**：AI 生成自动评审证据（`tools/board_review.py` 8 项机器实测 + 渲染当前 PCB 图 + `render_evidence` 哈希绑定）、执行多模态目检预筛（L1/L2/L3 难度分级，见 `notes/m2-evidence-reset/M2目检提示词-多模态AI.md`）。AI 不设置 `manufacturing_release`。必要性：机器门禁全部通过≠实体板可工作；制造风险的责任边界必须由人承担（ADR-004 决策 4）。
- **哪些开源资源直接参与**：KiCad（渲染、几何数据）；无开源"制造签发"机制（碰撞分析 §3 判四仓库均为自动 pass）。
- **AEDL 自研模块是什么**：`gates/board_review_v1.json`、`tools/board_review.py`、`gates/gate_core.py` 的 `validate_render_evidence`（渲染图新鲜度门禁，防过期图误判）。
- **移除 AI 会损失什么**：8 项评审与渲染图需人工逐项完成，目检预筛自动化损失；签发语义不变（仍人工）。
- **如何验证**：board_review gate 当前 FAIL（`manufacturing_release=false` 等待人工重签，诚实终态，EVID-20260830-001）；渲染图新鲜度门禁（TASK-R1，`validate_render_evidence` 以 PCB SHA256 判定"图过期"）。
- **判定语言**：截至 2026-08-30 对所列公开源码的检查中，尚未发现把"制造签发"做成 fail-closed 人工闸的等价实现（四仓库均为自动 pass，碰撞分析 §3）。**反证检索**：需确认列表内无商业工具/其他开源把"制造签发"做成同等严格度的 fail-closed 人工闸。

### 2.6 经验学习门禁

- **核心能力是什么**：`gates/learning_gate.py` + `gates/lessons_registry_v1.json`，缺字段即 fail，三层晋级；严重经验必须绑定失败证据、夹具、测试、控制和最新故障注入证明。
- **AI 做什么、为什么必要**：AI 分析事故、撰写 lessons 条目（必须满足 7 项准入条件，见 `docs/knowledge/PROJECT_PITFALLS.md` 新经验登记准入）、生成故障注入证明。必要性：PIT-20260830-001 与渲染图事故证明"历史快照不等于独立正确性"；经验必须可执行、可回归，不能只是文字总结。
- **哪些开源资源直接参与**：无直接开源代码；碰撞分析 §5 元教训（"Even verification agents require verification"）作为方法论输入。
- **AEDL 自研模块是什么**：`gates/learning_gate.py`、`gates/lessons_registry_v1.json`、`docs/knowledge/PROJECT_PITFALLS.md`、`docs/knowledge/IMPROVEMENT_SYSTEM.md`。
- **移除 AI 会损失什么**：事故分析需人工完成，经验沉淀速度下降；门禁仍强制完整性。
- **如何验证**：learning gate PASS（EVID-20260830-001）；`lessons_registry_v1.json` 含 PIT-20260830-001 条目（含 root_cause/escaped_controls/failure_evidence/failing_fixtures/regression_tests/fault_injection_proof 必填字段）。
- **判定语言**：截至 2026-08-30 对所列公开源码的检查中，尚未发现把"事故回溯/经验升级"做成缺字段即 fail 的机器门禁的等价实现（碰撞分析 §3）。**反证检索**：未见任何竞品有事故回溯/经验升级机制。

---

## 3. 判定语言与证据对照（碰撞分析 §3 口径）

> 规则：每一项只写"截至检查日，对所审公开源码的检查中，尚未发现等价实现"，并注明该主张需要的证据与可证伪条件。凡缺少对等 competitor 检索的项，一律降级为"未完全核实前提下暂不夹带首创式主张"。

| AEDL 机制 | AEDL 侧实现证据（已验证） | 判定语言写法 | 待补的"他人也做了"的反证检索 |
|---|---|---|---|
| 常驻故障注入 gate | `gates/semantic_fault_injection.py`：每次 run 注入 fault 夹具、必须全 caught 否则 fail | 截至检查日，在所审开源源码中尚未发现将"校验器有效性自证"做成常驻门禁的等价实现 | KiCadAI 的 promotion evidence 是同一方向，但对象是"能力证据"而非"校验器对故障的捕获率" |
| 跨视图机器解析交叉绑定 | `gates/schematic_semantics.py`：独立 contract + intent/KiCad XML netlist/PCB pad/firmware 四视图、sha256 绑定、机器解析 XML/S-expression | 尚未发现等价实现；且该项以"机器解析＋独立合同"实现"生成器不当裁判"，与 kicad-ai 想用"fresh LLM reviewer"实现同目标——路径不同，需先定案 kicad-ai 是否真实才可写 | kicad-ai 的 findings ledger/waiver/done-gate 若源码证实存在，则是同目标临近物；未定案前不得写"我们独有" |
| 人工具名制造签发 + 撤销重签 | `gates/board_review_v1.json`（`manufacturing_release`＋reviewer＋时间戳；revocation 需 `human_resign_required`） | 尚未发现等价实现（四仓库均为自动 pass） | 需确认列表内无商业工具/其他开源把"制造签发"做成 fail-closed 人工闸 |
| 供应链 fail-closed | BOM freshness（7 天过期/未来日期即 fail）、正库存、TBD 拒绝、零库存不自动换料 | 尚未发现等价实现 | CircuitBot 仅 RAG 选料、NeuroBoard 仅声称 JLC validation，未见"过期库存即 fail"等价物 |
| 经验学习门禁 | `gates/learning_gate.py` + `lessons_registry`（缺字段即 fail，三层晋级） | 尚未发现等价实现 | 未见任何竞品有事故回溯/经验升级机制 |
| 需求合同（第 10 门禁） | `gates/requirements_contract.py`：blocking 未答即 fail、No preference 显式记录、SHA256 自哈希、intent 引用校验 | 尚未发现把"澄清结果固化为可哈希绑定工程合同"的等价实现 | CircuitBot clarify 为 fail-open（超时继续/静默丢弃/零测试）；KiCadAI clarification 为单向拒绝非回路 |

> 若进入 AIC 报告，措辞一律用上表"判定语言写法"，并配每格"反证检索"留痕。**任何"首创 / 领先 / 行业空白"字样禁止使用。**

---

## 4. 诚实边界（不主张什么）

- 不主张"用了 Git / Python / LLM / 开源库"本身是融合创新（AGENTS.md §8.2）。
- 不主张 AEDL 是"完整替代品"或"通用电路生成器"：当前只验证一块 ESP32-C3/SHT30 载板与门禁闭环（HANDOFF 约束）。
- 不主张实体板可工作：机器门禁/ERC/DRC/语义合同全部是静态与软件证据，回件前的 C 级实测（上电、功耗、BLE、精度、USB 眼图、瞬态、24/168h 稳定性）尚未执行（EVID-20260830-001 已知限制）。
- 不主张"别人没有"：判定语言一律限定为"截至检查日对所审公开源码"，并保留反证检索留痕。
- 不引用 kicad-ai（amcolex）的任何描述（findings ledger / waivers / done-gate / 4-4 USB case）：其仓库真实性待人工浏览器定案（`kicadai.md` 附节）。

---

## 5. 关联台账（证据链索引）

- 融合主张 ↔ `docs/compliance/THIRD_PARTY_RESOURCES.md`（RES-001..007，许可证台账）
- 融合主张 ↔ `notes/open_source_intake/THIRD_PARTY.md`（intake 版第三方复用清单，含 Konnect AGPL 红线）
- 关键决策 ↔ `docs/compliance/DECISIONS.md`（ADR-004 独立语义合同与人机分离制造放行；ADR-005 替代料审核协议）
- 实际结果 ↔ `docs/evidence/EVIDENCE_INDEX.md`（EVID-20260829-001/002/003、EVID-20260830-001）
- 事故经验 ↔ `docs/knowledge/PROJECT_PITFALLS.md`（PIT-20260830-001）
- AI 参与 ↔ `docs/compliance/AI_USAGE_LOG.md`（AI-20260829-001、AI-20260830-002、AI-20260831-001/002/003/004）
