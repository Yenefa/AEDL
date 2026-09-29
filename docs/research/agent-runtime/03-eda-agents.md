# 03 — EDA / 硬件 Agent 的 repair 机制实证调研（源码级）

> 服务同一问题：**怎样把真实 LLM 接回 AEDL，按 verifier findings 反复修复，同时绝不绕过 Trust Plane**（方向已定：LangGraph + RepairPort + Trust 层 + 极薄 harness，本篇只填实证）。
> 判据：读到 GitHub raw 源码 = `已确认`；仅 README/摘要 = `TO_VERIFY`；未跑 = `NOT_RUN`。本轮**未执行任何测试/CLI**（`NOT_RUN`），无 git 操作。

## 0. 本地锚点（先于外部结论）

- `protocol.py:251-252`：`RepairPort.propose(...) -> PolicyRequest`——修复只能是"下一个待审请求"，不是副作用。
- `orchestrator.py:288`：`repair → preflight`，每轮修复必须重过 policy；`:503-523` fingerprint 重复熔断 `REPAIR_STALLED` + `max_repairs` → `REPAIR_LIMIT_REACHED`；`:86-96,117-119` 产物越界即 `ARTIFACT_ESCAPE`。
- `state.py:127-134`：fingerprint 对**全部** findings 的 (code,message) 排序取 SHA-256，**未按 severity 过滤**（下文 boardsmith 做法反照此点）。

**勘误**：任务里"CircuitBot 有 `langgraph_loop.py`"不成立——该文件属 **NeuroBoard**；CircuitBot 的图在 `agent/builder.py`。既有笔记引用需改。

## 1. CircuitBot（HiwarkhedePrasad，MIT，push 2026-08-16）

**repair**：`builder.py:69-82` fatal→`error_end`、repairable 且 `passes<2`→`repair`、超限→`error_end`；`nodes/repair.py:18` `MAX_REPAIR_PASSES=2`，`:361-371` **超限把残留 repairable 提升为 fatal**；策略是确定性表（`:316-323`）+ 通用回退（按错误消息抽查询词，`:237-310`）+ Thompson bandit 选策略（`:344-349`）。ERC 环：`schematic_audit.py:135,163,208` 生成文本→括号/root 校验→`kicad-cli --format json --severity-all`→结构化 `_erc_results`；`route_utils.py:89-103` 有 fixable 且 `_erc_retries<3`→`schematic_repair`，**否则 `return "ask_pcb_approval"`（残留 ERC 不拦，转人审）**。验证环上限 `MAX_VALIDATION_RETRIES=3`（`llm_utils.py:22`），耗尽→`error_end`。`error_end_node`（`builder.py:45-62`）只发事件+写 `state["error"]` 后 END，不抛异常。

**LLM judge（本篇重点，已源码确认）**：`nodes/llm_judge.py` 5 维 0–10 打分（`:17-72`），异常降级 0 分（`:145-157`），`return {"judge_evaluation": result}`（`:163`）；图上 `design_review → llm_judge → END` 为**无条件边**（`builder.py:342-343`），其后无任何路由。→ **纯评分记录，无路由权、无否决权，不可能拦截任何东西**；旧笔记"未源码确认"升级为"已源码确认：不是 hard fail-closed 门禁"。

**写路径**：LLM **不写** `.kicad_sch`。内存 design dict → `kicad_export.py:242 generate_kicad_sch(design)->str`（确定性序列化 + EV001 一致性校验 `:483`）→ 审计节点 → `server/routes.py:211-231 /api/export_sch` 作为附件返回，`ExportValidationError`→500。**无"模型文本=磁盘文件"路径。**

**findings**：`erc_runner.py:23-36` FIXABLE/NON_FIXABLE 白名单；`:96-144` 解析 kicad-cli JSON 为 `{type,description,position,severity}`，error/warning 分流，`fixable` 带 `pin_key`。

## 2. boardsmith（ForestHubAI，**AGPL-3.0-or-later**，push 2026-03-11，34★）

**repair**：`synthesizer.py:274-345` 双层——`ERCRefiner(max_iterations=3,use_llm)`（确定性）→ 仅当 `not passed and tool_available and use_llm` 才上 `ERCAgent(max_iterations=默认5)`（`boardsmith_cli/main.py:114-119`）。`agent/erc_agent.py`：`_violation_fingerprint` **只 hash severity=error、有意排除 warning**（否则 LLM 推理差异会造成假 stall）；同指纹连续 2 轮→打印 stall 并 `stalled=True`；`run()` **never raises**，异常折叠为 `cap_hit=True`；每轮只修一个违规，修完自动重跑 ERC。

**门禁强度（关键反面证据）**：`iterative_orchestrator.py:631-636` `release_ready=False` 仅 `log.warning("GateMatrix failed after accept …")`；`:697` `success = not hitl_required and final_confidence > 0`；`main.py:499-500` 仅 `not success` 才 `exit(1)`；`:376-420` 接受阈值 0.75/0.85/0.90，`accept_reason` 含 `max_iter / converged`，耗尽仍打印 `Design accepted!`。→ **build 主链上 ERC 未清零不改变退出码，门禁是 advisory**。但显式子命令 `boardsmith erc/drc` 失败即 `exit(1)`（`main.py:1523-1564,2639-2685`）——他们知道怎么写硬门禁，只是没放进主链。

**写路径**：LLM **只发结构化操作**。`agent/write_schematic.py:3-10,305-393` 固定顺序：读原文件→**先写时间戳 `.bak`**（失败即 abort）→内存应用 ADD(`lib_id/reference/value`)/MODIFY(`symbol_uuid/property_name/new_value`)→**生产解析器 `parse_kicad_sexpr()` 校验整棵树**→通过才落盘，失败"original file is unchanged"。核心生成路径 LLM 不在环（作者自述"LLM 只在 B1"，`TO_VERIFY`）。

**findings**：`agent/run_erc.py:8-27` `_FIXABLE_RULE_IDS` 白名单，违规格式化为 `{message,severity,fixable,rule_id,items[:3]}`，`ToolResult(confidence=1.0 if tool_available else 0.0)`——**工具可得性直接编码进 confidence**，防"没跑 ERC=通过"。

## 3. kicad-happy（aklofas，**MIT**，1303★，push 2026-09-13）

**无 repair loop**（确定性分析器 + skill 包），价值在证据范式：`finding_schema.py:13` `VALID_CONFIDENCES=('deterministic','heuristic','datasheet-backed')`、`evidence_source` 白名单、非法值直接 raise（`:247-258`）、`assign_finding_ids` 用 sha-256 前缀+排序（`:94-110`，与 AEDL fingerprint 同向）；`deep_review_gate.py:22-25,251-275` LLM findings 必须有 design anchor（component/net/pin 在 analyzer JSON 中真实存在）+ datasheet 引文可定位 + 计算脚本存在，否则 `quarantined[]` 带 reason、**exit 1**；`fab_release_gate.py:34-44,429-434,563,577` 任一 fail→`FAIL`，`--strict` 把 warn 也当 fail，`exit(1)`。**写路径**：LLM 不写；`edit_properties.py:421-429` `--backup` 后按 JSON 改属性，`SKILL.md:39-41` 要求 **dry-run first, then apply**。

## 4. NeuroBoard（Be-bibek，MIT，3★，push 2026-08-26，本轮复核）

`langgraph_loop.py:918-919` `drc_errors`→`self_correction` 否则 end；`:834-837` 默认 5 次超限即 warning 停；**未发现 fingerprint/stall 机制**（措辞：本轮未发现等价实现）。新发现：`:684 MAX_REFLECT=2` 与 `:695` 注释"MAX_REFLECT=3"**不一致**。`:776-777` `strict_mode=False → status="verified_skip", drc_errors=[]`——**验证可配置跳过还返回绿**。回滚/动态执行脚本部分本轮未复核，承既有笔记（`TO_VERIFY`）。

## 5. 学界与同类（repair 样本）

- **pcbGPT**（arXiv:2606.01188）：生成→执行/ERC→validation agent 回传结构化 root-cause→修；终止于"通过全部检查 **或预设迭代上限**"；语义评审明确"**不作为形式验证**"；LLM 产 **Python DSL**。
- **PCBSchemaGen**（arXiv:2602.00510；github.com/HZou9/PCBSchemaGen）：5 层确定性 reward verifier + **pin 级错误定位**回灌 + Thompson bandit refine；自述 V 只是"one upstream gate"，下游仍需 ERC/DRC/签核；**消融：仅用 ERC 的假通过率高 10–13pp**；LLM 产 SKiDL。
- **SchGen**（microsoft/SchGen，arXiv:2605.30345）：**反面证据**——"KiCad file representation yields the lowest performance… low valid circuit ratio"，原生 KiCad 文件是最差表示。
- **Circuitron**（HinVec，MIT，疑似 Shaurya-Sethi 更名 `TO_VERIFY`）：README 称"直到干净"，并自述 footprint 幻觉不稳、项目已弃维护（实现未读，`TO_VERIFY`）。
- **电机驱动多智能体**（engrXiv 6706）：feedback agent 解析原始 ERC 日志、把错误码关联 SKiDL 行号→纠正提示→重生成，"until zero ERC violations"，**未见上限**（`TO_VERIFY`）。
- **DRCY**（arXiv:2603.15672）：五智能体评审，findings 以内联评论贴回 review，**只读不改文件**。

## 6. 可借鉴清单（可直接转成 RFC 决定）

1. **超限升级为 fatal**（CircuitBot `repair.py:361-371`）→ `REPAIR_LIMIT_REACHED` 时残留 findings 必须留痕于 terminal 证据。
2. **写路径 = 结构化操作 + 备份 + 生产解析器校验 + 落盘**（boardsmith `write_schematic.py:305-393`）→ `ExecutorPort` 的 LLM 实现只能"模型产操作 JSON、确定性 applier 在 candidate 根内写"，才能被 `_artifact_within_candidate` 与 action ledger 覆盖。
3. **stall 指纹按严重度过滤**（boardsmith `_violation_fingerprint` 只 hash error、排除 warning）→ RFC 必须显式决定 `state.py:127-134` 的输入范围：否则非致命项抖动造成假 stall，或靠改 message 绕过熔断。
4. **LLM 说法必须有可复核 anchor，否则 quarantine**（kicad-happy `deep_review_gate.py`）→ 锚不到 candidate 内对象的新 findings 不得进入裁决面。
5. **反馈带定位**（PCBSchemaGen pin 级定位 + 消融"Full feedback 才有效"；boardsmith `rule_id+items`）→ `Finding.details` 需要 `locator(ref/pin/net/uuid)` 规范。
6. **表示选择**（SchGen 消融）→ prompt/工具面只喂结构化 JSON/DSL，不喂 `.kicad_sch` 原文。
7. **工具可得性≠通过**（boardsmith `run_erc.py:63` confidence 编码）→ kicad-cli 不可用必须 `BLOCKED` 而非 `PASS`。

## 7. 必须避免清单（带证据 + 破坏 Trust Plane 的理由）

1. **打分式接受、迭代耗尽仍 accepted**（boardsmith `main.py:376-420`、`orchestrator.py:697` 之于 AEDL）→ 会让 `VerificationStatus` 退化为灰度分，`_route_after_verify`（`orchestrator.py:297-306`）的 FAIL→stall 语义被稀释，**三态前提崩**。
2. **门禁降级为 warning**（`iterative_orchestrator.py:631-636`）→ 晋升判定外流到 agent 自评分，`trust.assess_promotion` 形同虚设。
3. **给 LLM 判断路由/否决权**（CircuitBot judge 恰恰没有：`builder.py:342-343` 无条件边）→ 若把 LLM 判断接进 conditional edge 改 `terminal_reason`，等于把 `PolicyDecision/PromotionDecision` 交给概率输出。**RFC：LLM 只产 `Finding`/`EvidenceEvent`，永不产 `Outcome` 或 `terminal_reason`。**
4. **可配置跳过验证还返回绿**（NeuroBoard `:776-777 verified_skip`）→ 造出"绿但未验"候选；AEDL 必须落 `BLOCKED/NOT_RUN`（`protocol.py:65-70`）。
5. **无 stall 的"直到干净"**（Circuitron/engrXiv 式）→ 无界循环使写盘次数与变更面失控；已有 fingerprint + `max_repairs`，不得退回。
6. **LLM 直接写 `.kicad_sch/.kicad_pcb`** → 写路径不经 `ExecutorPort` 即绕过 action ledger、`_execution_failure_reason`（`orchestrator.py:99-120`）与越界检查，**"候选区外没被改"从此无法证明**，evidence 链断在关键一环（本轮所审项目无一这么做）。
7. **复制 boardsmith 代码**（AGPL-3.0-or-later，API `spdx_id=AGPL-3.0` + 源码头 + PyPI，另有商业 CLA）→ 只借鉴设计、零代码复制，否则踩 `docs/WAVE4_TASKS_20260901.md:67` 红线。

## 8. 汇总表

| 项目 | repair 机制 | 终止条件 | 门禁强度 | LLM 写文件路径 | License | 对 AEDL 的结论 |
|---|---|---|---|---|---|---|
| CircuitBot（`builder.py`） | 约束×2 / ERC×3 / 验证×3，确定性策略表 | 超限→fatal→`error_end`；**ERC 残留→`ask_pcb_approval` 放行** | 中：有硬终点，但 judge 纯评分、ERC 残留不拦 | **否**：内存 dict→`generate_kicad_sch()`→服务端导出 | MIT | 抄"超限升级"；**judge 非门禁（已确认）** |
| boardsmith | ERCRefiner×3 + ERCAgent×5，error 指纹 stall，单次单修 | `max_iterations` 或连续 2 轮同指纹；永不抛异常 | **弱**（build 链 warning、`success` 与 ERC 解耦）/ **强**（`erc|drc` 子命令 exit 1） | **部分**：仅 ADD/MODIFY 操作 → `.bak` → 解析校验 → 落盘 | **AGPL-3.0-or-later** | 写路径正面样板；接受阈值+warning 是反面教材 |
| kicad-happy | 无 repair loop（分析器/skill） | gate：quarantine→exit 1；fab：任一 fail→FAIL | **强**（anchor + `--strict`） | **否**：脚本 backup 后按 JSON 改属性，dry-run 先行 | MIT | findings schema 与"说法须可复核"直接可抄 |
| NeuroBoard | verification→self_correction（默认 5） | 超限 warning 停；**无 stall 熔断** | **弱**（`verified_skip` 可跳过） | IPC/动态脚本轮未复核（`TO_VERIFY`） | MIT | 反面教材：可跳过验证 + 无 stall |
| pcbGPT / PCBSchemaGen / SchGen | 生成-执行-修复 / bandit refine，均有预算上限 | 预算用尽 | 硬（执行+ERC）与概率（语义）分层；ERC 假通过率 10–13pp | 均产 **DSL/SKiDL**，不写原生 KiCad 文件 | 论文公开；代码库 license `TO_VERIFY` | 支撑"分层验证 + 结构化表示 + 反馈带定位" |

## 来源（本轮实际抓取）

**本地**：`sandbox_runtime/src/aedl_sandbox/protocol.py`、`orchestrator.py`、`state.py`；`docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md` §7–§9；`notes/competitor-collision-analysis-2026-08-30.md`；`notes/three-repos-review-2026-09-01.md`；`notes/open_source_intake/circuitbot.md`、`kicad-happy.md`；`docs/compliance/THIRD_PARTY_RESOURCES.md`；`docs/WAVE4_TASKS_20260901.md`。

**源码**：
- https://github.com/HiwarkhedePrasad/CircuitBot — `agent/builder.py`、`agent/nodes/llm_judge.py`、`agent/nodes/repair.py`、`agent/nodes/validate_repair.py`、`agent/nodes/schematic_repair.py`、`agent/nodes/schematic_audit.py`、`agent/erc_runner.py`、`agent/kicad_export.py`、`agent/route_utils.py`、`agent/llm_utils.py`、`server/routes.py`（license 经 API：MIT）
- https://github.com/ForestHubAI/boardsmith — `synthesizer/boardsmith_hw/agent/erc_agent.py`、`…/write_schematic.py`、`…/run_erc.py`、`synthesizer/boardsmith_hw/synthesizer.py`、`shared/agents/iterative_orchestrator.py`、`boardsmith_cli/main.py`（API：AGPL-3.0；源码头 AGPL-3.0-or-later；https://pypi.org/project/boardsmith/ ）
- https://github.com/aklofas/kicad-happy — `skills/kicad/scripts/finding_schema.py`、`skills/kicad/review/scripts/deep_review_gate.py`、`skills/kicad/scripts/fab_release_gate.py`、`skills/bom/scripts/edit_properties.py`、`skills/bom/SKILL.md`、`LICENSE`
- https://github.com/Be-bibek/NeuroBoard — `ai_core/agent/langgraph_loop.py`（API：MIT）
- https://github.com/HinVec/circuitron（API：MIT）

**论文/网页**：https://arxiv.org/pdf/2606.01188v1 ｜ https://arxiv.org/abs/2602.00510 与 https://github.com/HZou9/PCBSchemaGen ｜ https://arxiv.org/html/2605.30345 与 https://github.com/microsoft/SchGen（license `TO_VERIFY`）｜ https://arxiv.org/abs/2603.15672 ｜ https://engxiv.org/preprint/download/6706/10976/9340（落地页 `TO_VERIFY`）｜ https://news.ycombinator.com/item?id=47353747（作者自述，非源码，`TO_VERIFY`）。
