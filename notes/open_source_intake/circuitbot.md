# CircuitBot 开源项目 Intake 报告（六步协议）

> Repo: https://github.com/HiwarkhedePrasad/CircuitBot
> Commit SHA: `ff9b003b9726f476bd14c02fe47c7ea5b94ed6ff`（本地克隆 `notes/open_source_intake/_circuitbot_repo/`）
> Date Reviewed: 2026-08-31
> License: MIT（LICENSE 文件全文核对，Copyright (c) 2026 CircuitBot contributors；允许商用、修改、再分发，需保留版权声明）
> 审查方法：本地 git clone 后逐文件阅读源码；对照既有 `notes/competitor-collision-analysis-2026-08-30.md` 第二轮结论。
> 证据标记：`已验证`（源码直接读到）/ `未核实`（本轮未查证，不据此断言真或假）。

---

## STEP 1 - CLAIM（它声称做了什么）

README 声称（`README.md`）：

| 声称 | 分类 | 源码核对结果 |
|---|---|---|
| 自然语言 -> clarify -> analyze -> architect -> select -> netlist -> validate -> schematic -> placement -> routing -> export 全流水线 | Implemented | `已验证`：`agent/builder.py` 两个 StateGraph 均按此顺序接线（`set_entry_point("clarify")`） |
| 40+ 专业 agent 节点 | Implemented | `已验证`：`agent/nodes/` 目录 40 个节点文件实数核对 |
| RAG 选料（FAISS + SQLite + 查询扩展 + 模糊匹配 + 锁料） | Implemented | `已验证`：`kicad_rag/`、`agent/knowledge/` 目录存在且被 select 节点引用；本轮未逐函数审（`未核实`深度） |
| ERC + 结构化网络验证 + 连通性修复 + LLM judge | Implemented | `已验证`：`agent/erc_runner.py`、`nodes/llm_judge.py`、`nodes/connectivity_repair.py` 存在；judge 语义见 STEP 3 |
| 10 指标原理图质量评分引擎 | Implemented | `已验证`：`agent/scoring/` 存在；本轮未验证评分正确性 |
| 双自动布线器 + 铺铜 + 坐标校验 | Implemented | `已验证`：`agent/routing/`（两个实现文件）；布线正确性 `未核实` |
| 交互式 Web UI（WebGL/3D 预览） | Implemented | `已验证`：`server/`、`static/` 存在；UX 质量 `未核实` |
| KiCad / tscircuit / circuit JSON 多目标导出 | Implemented | `已验证`：`agent/kicad_export.py`、`tscircuit_export.py` 存在 |
| Benchmark 套件（ESP32 传感器等） | Implemented | `已验证`：`agent/benchmarks/`、`benchmark_runner.py` 存在 |
| Session memory / 可恢复流水线 | Implemented | `已验证`：`agent/sync/`、`agent/state_models.py`；恢复语义 `未核实` |
| MCP server | Implemented | `已验证`：README + server 代码存在；协议完整度 `未核实` |

无 roadmap 条目冒充实现的发现。README 与源码结构一致性高于常见同类项目。

---

## STEP 2 - SOURCE（源码实际上做了什么）

- **语言/框架**：Python 3.10+，LangGraph StateGraph 编排，FastAPI/Node 前端，MIT。
- **Graph 接线**（`agent/builder.py`，`已验证`）：
  - `set_entry_point("clarify")` -> `analyze` -> `deepresearch` -> `research` -> `select` -> `datasheet_search` -> `symbol_compatibility` -> `validate`（conditional edges 到 repair loop / error_end）。
  - 存在第二张图（"Flow" 注释版），节点集合略有差异（含 `architecture_planner`、`capability_resolver`、`freeze_components` 等），两张图的真实选择逻辑由 feature_flags / 路由决定，`未核实`哪张是默认路径。
- **clarify 节点**（`agent/nodes/clarify.py`，297 行，`已验证` 全文阅读）：
  - 关键词维度评估：`_SPECIFIC_KEYWORDS` 五维（mcu/sensor/power/connectivity/display）+ IC 关键词表 + 模拟关键词表。
  - `≥3 个维度已具体 -> 跳过澄清`（`_count_specific_dimensions >= 3`）。
  - LLM 评估（`_assess_clarification`）：失败时 fallback 到 `_heuristic_assessment`（纯关键词启发式，最多 5 问）。
  - 阻塞等待用户回答：`clarify_event.wait(timeout=300)` —— 5 分钟超时。
  - 答案合并回 prompt 字符串（`_build_enhanced_prompt`）：`原始 prompt + "Specific requirements:\n - Q: A"` 列表拼接。
- **analyze 节点**（`agent/nodes/analyze.py`，`已验证` 节选阅读）：
  - LLM 拆子系统；失败 fallback `_fallback_analysis`。
  - `_apply_user_part_intent`：用户点名器件优先于 LLM 分析。
  - **自动注入 MCU 子系统**：`requires_mcu` 且出现 Sensor/Display 等子系统但无 MCU 时，自动插入 "Microcontroller" 子系统（用户未明确要求也插）。
  - IC-based / analog-only 电路会反向剥离 LLM 误加的 MCU 子系统（好设计，值得学）。
- **测试**（`已验证`）：`tests/` 60 个文件；CI（`.github/workflows/test.yml`）跑 ruff + pytest（`--ignore=tests/test_e2e.py`）+ 3 个 JS 回归测试。
  - **clarify 节点零单元测试**（`grep -rln clarify tests/` 无命中）；e2e 也未覆盖 clarify 分支。
  - e2e（test_e2e.py）用本地 LLM 真跑，CI 明确 ignore。
- **commit 活跃度**：最后 push 2026-08-16，单作者仓库。

---

## STEP 3 - FAILURE（它最烂的地方）

按 AEDL 视角，从重到轻：

1. **Clarify 是 fail-open（最严重，直击 AEDL 要害）**：
   - `clarify_event.wait(timeout=300)` 超时后**不等答案直接继续**，还打日志 "No answers received - proceeding with original prompt"。
   - "No preference" 答案在 `_build_enhanced_prompt` 里被**静默丢弃**（`continue`），不进入 prompt，也不留痕。
   - 评估器本身是 LLM，LLM 失败 fallback 到关键词启发式，继续跑——没有"不知道就停"的路径。
   - 对 AEDL 而言：**这正是"澄清结果留在 state、无合同、无哈希、可静默漂移"的源码级实证**，策略文档 2.2 节预判全部成立。
2. **澄清结果无持久化合同**：答案只写进 `state.clarification_answers`（内存 dict）和增强 prompt 字符串，无 artifact、无哈希、无版本。`grep clarification` 在 runtime/sync 无消费者（`已验证`），后续节点只见 prompt 字符串。
3. **澄清维度是平面关键词表**：五维关键词是硬编码英文表，`"usb"` 同时命中 connectivity 和 power；中文/非表内表达完全绕过；`_detect_circuit_type` 对 "mixed" 默认"假设需要 MCU"。
4. **≥3 维度跳过规则可被无关词污染**：任意三个关键词命中即跳过澄清（如 "5v led usb wifi"），与需求工程语义无关。
5. **LLM judge 定位（继承碰撞分析结论）**：倾向评分记录，非 hard fail-closed 门禁；`未核实`其终局否决权（本轮未逐行审 judge 路由）。
6. **clarify 零测试**：60 个测试文件无一覆盖 clarify 节点；LLM judge、fallback 分支全部未测。
7. **analyze 自动注入 MCU**：用户没要求 MCU 也自动插入（AEDL 视角属"静默假设"——虽然它打日志，但对下游是隐式决策；AEDL 的 forbidden_assumptions 机制应显式记录这类假设）。
8. **两图并存**：builder.py 两张 StateGraph 并存，真实路径不明确（`未核实`），提高 intake 复核成本。

---

## STEP 4 - REUSABLE（哪些能力可以合法复用）

| 能力 | 复用方式 | 依据 |
|---|---|---|
| **5 维度澄清框架**（mcu/sensor/power/connectivity/display + circuit_type 三分类） | **Adapt**（借思想重实现） | 维度划分本身合理，AEDL 可扩展并加硬规则；MIT 允许 |
| **每问 2-4 个具体选项 + "No preference"** | **Adapt** | 降低用户回答成本的好交互；但 AEDL 版 "No preference" 必须显式记录为 nonblocking assumption，不得静默丢弃 |
| **circuit_type 三分类（mcu_based/ic_based/analog_only/mixed）+ IC 主器件提取** | **Adapt** | 避免对 555/运放电路乱加 MCU 的守门设计，AEDL 值得吸收 |
| **IC-based 电路剥离误加 MCU 子系统**（analyze.py 反向过滤） | **Adapt** | 同上，防 LLM 过度设计 |
| **LangGraph conditional edge + repair loop + error_end** | **Idea Only** | AEDL 是纯 Python 门禁链不是常驻服务，暂不需要图框架；若未来做交互式前端再评估 |
| **`_build_enhanced_prompt` 的 Q&A 拼接格式** | **Reject** | 拼回字符串正是"澄清无合同"的病根；AEDL 用 JSON contract 替代 |
| **clarify 的 5 分钟超时继续** | **Reject** | fail-open，AEDL 改为"未答即停" |
| LLM 评估 + 关键词 fallback | **Adapt**（双通道保留，但语义反转） | AEDL：LLM/规则只负责**提出**问题；答案合法性、完整性由确定性 gate 校验；两者失败都必须停 |

**License 义务**：MIT。若 Adapt 其代码片段（如关键词表），需在 `THIRD_PARTY.md` 登记（含 SHA、MIT 声明保留）。借思想（维度框架、交互模式）不构成衍生作品，无需额外义务（法律细节 `TO_VERIFY`，非法律意见）。

---

## STEP 5 - AEDL TRANSFORM（接入后语义变化）

核心转化（策略文档 §2.3 的落地版）：

```text
CircuitBot clarify 节点
  （关键词维度 + LLM 评估 + 5min 超时继续 + 答案拼回 prompt 字符串 + state 内存）
        ↓ AEDL 重新定义
1. blocking question 未回答 -> STOP（永不超时继续）
2. "No preference" -> 显式记录为 nonblocking assumption（禁止静默丢弃）
3. 答案产物 = requirements_contract_v1.json（artifact，非 state）
4. contract -> SHA256 自哈希 + intent 引用校验（intent 不引用/引用过期即 fail）
5. LLM 只能提出问题与假设，不能定合同内容；合同字段完整性由确定性 gate 校验
6. circuit_type / requires_mcu / primary_ic 识别结果进 contract 的 resolved_requirements
   （替代 CircuitBot 的"自动注入 MCU"：AEDL 必须显式记录 assumption 并可 forbidden）
```

**AEDL 由此获得**：从"一句话直接生成 intent"升级为"一句话 -> 合同 -> intent"的可追溯链；澄清结果从易失 state 变为哈希绑定 artifact；fail-open 变 fail-closed。

**AEDL 不获得**（诚实边界）：CircuitBot 的交互式聊天澄清 UX、LangGraph 实时编排、RAG 选料库——这些属于产品层，AEDL 现阶段不做（P3+ 视前端需求再议）。

---

## STEP 6 - VERIFY（怎么证明吃进去以后更好）

按策略文档要求，吸收后必须给可证伪验证：

1. **Regression fixture**：构造含歧义的 NL 输入（借 CircuitBot 失败模式）：
   - F1：blocking question 无答案（模拟超时/拒答）-> gate 必须 FAIL（CircuitBot 会继续，AEDL 必须停）。
   - F2：用户答 "No preference" -> contract 必须含 nonblocking_assumptions 条目（CircuitBot 静默丢弃）。
   - F3：contract 修改后旧 intent 引用 -> 必须 FAIL（哈希失配）。
   - F4：contract 缺 forbidden_assumptions 字段 -> 结构校验 FAIL。
2. **Before/After**：M2 复盘——M2 的 intent 当时是人工写定的，无合同链路；对照新链路演示 NL -> contract -> intent 可追溯性提升（定性）。
3. **Fault injection**：将 F1/F3 纳入 `gates/semantic_fault_injection.py` 常驻故障注入（沿用 AEDL 既有 meta-verification 模式）。
4. **证据**：新 gate 运行记录入 `notes/`（EVID 登记按 AGENTS.md 触发条件执行）。

---

## 附：与竞品碰撞分析的对照（两轮结论校准）

本报告与 `notes/competitor-collision-analysis-2026-08-30.md` 无冲突，且补齐了其 §6.3 留空项：
- 碰撞分析判"clarify 真实现"——`已验证` 成立：节点存在、接线为 entry point、交互流完整。
- 碰撞分析判"LLM judge 非 hard fail-closed（倾向评分记录）"——`未核实`，本轮未深挖 judge 路由，维持原判。
- 本报告新增：clarify 的 fail-open 超时语义、答案静默丢弃、零测试覆盖——这三点在碰撞分析中未展开，是 AEDL "重新设计"的直接依据。

（本文件为内部工作分析，按 AGENTS.md 留痕规则，关联 AI-20260831-001，PENDING_HUMAN_REVIEW。）
