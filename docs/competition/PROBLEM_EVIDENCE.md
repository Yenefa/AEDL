# PROBLEM_EVIDENCE — 硬件 Agent 验证可信度的真实痛点证据

> 用途：AIC「AI+开源」评分项「问题与场景价值」的证据资产。用本项目真实发生、可复现、已有防复发控制的事故，证明"硬件 Agent 的验证可信度"是真实痛点。
> 素材来源（逐项标注，不脑补）：
> - `docs/knowledge/PROJECT_PITFALLS.md`（PIT-20260830-001，USB 接反事故 + 制造交付链同类事故）
> - `docs/PARALLEL_TASKS_20260831.md`（TASK-R1，渲染图过期事故）
> - `docs/compliance/DECISIONS.md`（ADR-004/ADR-005）、`docs/evidence/EVIDENCE_INDEX.md`、`docs/compliance/AI_USAGE_LOG.md`
> - `notes/competitor-collision-analysis-2026-08-30.md` §5（元教训）
> 状态：DRAFT，`PENDING_HUMAN_REVIEW`。所有事故均有可定位原始证据与回归入口；无用户反馈/外部 benchmark，一律不编造。

---

## 0. 问题一句话

**硬件工程 Agent 的瓶颈不是"能不能生成 PCB"，而是"生成的结果凭什么可信"**——现有 AI EDA 工具普遍把验证做成"生成器自证"或"文件存在即通过"，导致同一错误在多份文件中高度一致，反而制造"证据很多"的假象。本项目用四起真实事故证明这一痛点，并据此设计了 fail-closed 验证体系。

---

## 1. 事故一：USB 接反事故（PIT-20260830-001）

### 事实

M2 板（ESP32-C3 + SHT30 温湿度载板）在进入下单终检后才由独立数据手册复核发现：

- ESP32-C3-WROOM-02 的 **USB D−/D+ 管脚身份被写反**；
- SHT30 **ADDR 悬空**，但固件固定使用 `0x44`；
- SHT30 nRESET 被直接接到 3V3，而批准的修复策略要求未使用时明确 NC；
- ESP32-C3 缺少批准设计要求的 USB 22 Ω 串联电阻、EN 1 µF 电容和 GPIO9 10 kΩ 上拉。

原签发已撤销。**旧版 ERC 0、DRC 0、8 项板级评审 PASS 只能作为"旧设计符合旧规则"的历史事实，不再构成制造放行证据。**

### 为什么拖到下单终检（根因）

1. 人工先把错误语义写进 `intent_v1.json`。
2. akcli、原理图和 PCB 都从这个意图或其派生物继续工作。
3. `akcli check` 证明的是"原理图符合意图"，不是"意图符合数据手册"。
4. ERC/DRC 不理解 USB 信号身份、传感器地址选择或推荐启动网络。
5. USB 自动评审只量长度和 skew，没有核对 J1 D+ 最终是否到达 U1 USB D+。
6. "ADDR 已接地"只存在于人工报告文字，没有从网表反查。
7. 最终签发没有要求独立合同、负向夹具和故障注入证明。

> **核心洞察**：同一个错误在多份文件中高度一致，反而制造了"证据很多"的假象。这是**循环举证**，不能当作独立验证。

### 证据与回归入口

- 事故基线：`notes/m2-semantic-repair/baseline_failure.json`
- 旧设计实跑：`notes/m2-semantic-repair/semantic_failure_before_repair.json`（0/5 PASS）
- 永久夹具：`tests/fixtures/schematic_semantics/fault_*.json`（5 个负向夹具同时污染多个派生视图）
- 结构化登记：`gates/lessons_registry_v1.json`
- 永久控制：独立数据手册合同 `gates/contracts/m2_schematic_contract_v1.json` + `gates/schematic_semantics.py` 四视图交叉 + 常驻故障注入（ADR-004）

---

## 2. 事故二：渲染图过期事故（2026-08-31，TASK-R1）

### 事实

M2 目检用的 `board_top.png` / `board_bottom.png` 是 8-29 生成的**过期图**（比当前 PCB 旧一天，跨过 U3 换料），导致多模态 AI 目检全部误判（"丝印 17/21 缺失"等**假警报**）。

### 根因

渲染图是**一次性手工渲的，没脚本化、没 hash 绑定、没进门禁链**。这正是 `lessons_registry` PIT-20260830-001「历史快照不等于独立正确性」的**同型病**——文件存在且"看起来对"，但内容与当前设计源脱节。

### 永久控制（TASK-R1 已落地）

- `tools/board_review.py` 每次用 `kicad-cli pcb render` 重渲当前 PCB 到固定路径，覆盖旧图；
- `board_review_auto.json` 顶层新增 `render_evidence`（`pcb_sha256` / `top_png_sha256` / `bottom_png_sha256` / `rendered_at`，**全部 sha256 内容寻址，不用 mtime**）；
- `gates/gate_core.py` 新增 `validate_render_evidence`：`render_evidence.pcb_sha256` != 当前 PCB sha256 → error（"图过期"的机器判定核心）；png 缺失/失配 → error；
- 回归入口：`tests/test_board_review.py` 新增测试（缺 render_evidence / pcb 失配 / png 缺失 / png 失配）。

### 意义

证明"多模态 AI 目检"这类看似先进的验证手段，其**输入新鲜度**本身就是可信度风险——验证的验证必须机器化、哈希绑定。

---

## 3. 事故三：BOM 库存快照事故（2026-08-30，U3 换料）

### 事实

2026-08-30T06:30:42Z 的机器快照中，U3（C82942，ME6211C33M5G-N）装配库存为 5；同日 10:35:01Z 的下单前复查已降为 **0**。刷新器生成 `status=fail` 证据并保持规范 BOM 不被半更新。

### 根因

BOM 中的库存数字是**快照**，不是稳定供应承诺；旧数字只能描述当时查询结果，不能称为"稳定供应"，也不能据此自动替换料号。

### 永久控制

- `gates/refresh_bom_stock.py` 只接受精确料号与正库存查询结果；零库存/未知库存失败关闭且**不自动换料**；
- BOM 快照和库存证据必须同时间、同哈希，下单前即时刷新；
- 替代料必须重新审查数据手册、引脚、封装和电气性能（ADR-005：θJA 结温法、结论精度、主张纪律、数据手册版本交叉核对）；
- 处置：依据 ME6211C V20 数据手册核实 SOT-353 引脚序与 SOT-23-5 一致后，U3 受控换料为 C235316（ME6211C33R5G，SOT-353），全链同步并重跑门禁（AI-20260830-002，EVID-20260830-001）。

### 回归入口

- `tests/test_gate_core.py::GateCoreTests::test_bom_freshness_gate_expires_after_seven_days`
- `tests/test_gate_core.py::GateCoreTests::test_bom_stock_evidence_is_bound_to_the_canonical_bom`
- `tests/test_refresh_bom_stock.py`（精确匹配/快照绑定/零库存失败关闭）

---

## 4. 事故四：验证 Agent 自身的验证（碰撞分析元教训）

### 事实

在对 CircuitBot / NeuroBoard / KiCadAI / KiCad MCP 做源码级对撞分析时，第一轮审计子代理出现两类 claim calibration 失败：

- 把"未能通过工具访问"推成"仓库不存在"（负面强结论）；
- 把"部分证据支持"推成"护栏/凌驾"（正面强结论）。

与团队此前 LDO 事故同型：**推理方向可能正确，claim calibration 崩了**。方法论教训即"Even verification agents require verification"。

### 防控

- 负面结论（不存在/是假的/没有）必须给可复现证据（文件路径+函数+失败分支），否则写"未核实"；
- 能力领先结论一律用"截至检查中，尚未发现等价实现"并配反证检索；
- 工具抓不到 ≠ 事实不存在，需人工/二源交叉确认。

### 意义

证明"验证可信度"问题不仅存在于硬件设计，也存在于**对竞品/开源生态的研究过程本身**——这正是 AEDL 把"校验器有效性自证"做成常驻故障注入门禁的动机。

---

## 5. 痛点与 AEDL 对策映射

| 痛点（真实事故） | 证据 | AEDL 对策 | 对策证据 |
|---|---|---|---|
| 循环举证：多文件自洽 ≠ 独立正确 | 事故一（PIT-20260830-001） | 独立语义合同 + 四视图交叉 + 故障注入 | ADR-004、`gates/schematic_semantics.py`、EVID-20260830-001 |
| 历史快照/过期产物冒充当前证据 | 事故二（渲染图）、事故三（库存快照） | 全程 SHA256 内容寻址 + 新鲜度门禁 + 即时刷新 | TASK-R1 `validate_render_evidence`、`gates/refresh_bom_stock.py` |
| 供应链约束被当摆设 | 事故三（零库存） | 零库存失败关闭 + 不自动换料 + 替代料审核协议 | ADR-005、EVID-20260830-001 |
| 生成器自证（LLM judge） | 碰撞分析 §2.2（CircuitBot/NeuroBoard） | 10 门禁 fail-closed，判定全部确定性 | `gates/run_gates.py`、`_safe_gate` |
| 验证者自身不可信 | 事故四（审计元教训） | 常驻故障注入（校验器有效性自证） | `gates/semantic_fault_injection.py` |
| 机器全绿 ≠ 实体可工作 | 事故一（ERC 0/DRC 0 仍接反） | 人工制造签发 + 撤销重签 + 回件 C 级实测清单 | `gates/board_review_v1.json`、ADR-004 |

---

## 6. 证据边界（诚实声明）

- 以上全部是**设计文件、导出流程和目录查询证据**；它们没有把 `manufacturing_release` 改为 `true`，也不证明实体板能够工作（`docs/knowledge/PROJECT_PITFALLS.md` 证据边界）。
- 回件后的实体 C 级验证（上电、功耗、BLE、精度、USB 眼图、瞬态、24/168h 稳定性、持续 WiFi 负载下 U3 温升）**尚未执行**（`NOT_RUN`，见 HANDOFF 下一步验收顺序）。
- 无外部用户反馈、无第三方 benchmark 数据；本文件只引用项目内可定位、可复现、有回归入口的真实事故。
