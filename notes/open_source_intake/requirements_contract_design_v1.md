# Requirements Contract 设计稿 v1（供人工评审，未实装）

> 状态：**设计稿（DRAFT），等待项目负责人评审后才准实装**。本文只写设计，不含任何已实现代码。
> 来源：Phase 1 CircuitBot clarify 吸收（`notes/open_source_intake/circuitbot.md` STEP 5）+ 策略文档 §11。
> 关联：AI-20260831-001（PENDING_HUMAN_REVIEW）。
> 实装前置条件：M2 的 89 个未提交文件收尾完成（避免 diff 混杂），且设计稿经人工拍板。

---

## 1. 目标与边界

**目标**：把"一句话需求 -> intent"升级为"一句话 -> 需求合同（artifact）-> intent"，澄清结果可追溯、可哈希绑定、不可静默篡改。

**明确不做**（本轮）：
- 不做交互式聊天澄清 UX（CircuitBot 产品层，AEDL 无前端）；
- 不做 LLM 自动提问的运行时集成（LLM 可以在会话中**建议**问题清单，但合同生成与校验全部确定性）；
- 不改 9 个既有门禁的任何逻辑（新 gate 是第 10 个，纯增量）。

**与 CircuitBot 的语义反转**（本设计的核心）：

| CircuitBot 行为 | AEDL Requirements Contract 行为 |
|---|---|
| 5 分钟超时后带原 prompt 继续跑 | blocking question 未回答 -> **STOP，gate FAIL** |
| "No preference" 静默丢弃 | 显式记录为 nonblocking_assumption，可审计 |
| 答案只存 LangGraph state（内存） | 落盘 `requirements_contract_v1.json`（artifact） |
| 澄清结果拼回 prompt 字符串 | intent 必须引用 contract_sha256，gate 校验绑定 |
| LLM 评估失败 fallback 关键词继续 | 校验器失败 = gate FAIL（fail-closed） |
| 自动注入 MCU 子系统 | 任何注入必须写进 assumptions，可被 forbidden 列表否决 |

---

## 2. Artifact：requirements_contract_v1.json

位置：`gates/requirements/requirements_contract_v1.json`（与 `bom/bom_v1.json`、`contracts/m2_schematic_contract_v1.json` 同级的"真源"惯例）。

```jsonc
{
  "$schema": "https://aedl.local/schemas/requirements-contract.v1.json",
  "schema_version": 1,
  "board_id": "project-027-m2-esp32c3-sht30",       // 与 m2_schematic_contract_v1.board_id 同键
  "created_at": "2026-08-31T00:00:00+08:00",         // ISO8601，过期规则同 BOM freshness
  "author": "human+ai",                              // 合同生成方式的诚实标注

  // ── 语义主体 ──
  "user_goal": "一块 ESP32-C3 + SHT30 温湿度载板，USB-C 供电，BLE 上报",  // 用户原话或忠实转述，逐句保留
  "source_statements": [                             // 用户输入的语句级拆解（statement extraction）
    { "id": "S1", "text": "USB-C 供电", "type": "power" },
    { "id": "S2", "text": "ESP32-C3", "type": "mcu" }
  ],
  "resolved_requirements": [                         // 已明确的需求（每条必须能溯源到 statement 或 answer）
    { "id": "R1", "text": "供电：USB-C 5V", "source_ids": ["S1"] }
  ],
  "open_questions": [                                // 澄清问答记录（问题+答案+性质）
    {
      "id": "Q1",
      "question": "是否需要板载调试器？",
      "answer": "不需要",
      "kind": "blocking",                            // blocking | nonblocking
      "source_ids": ["S1"]
    }
  ],
  "assumptions": [                                   // 未问用户但设计必须依赖的假设（显式记录，禁止静默）
    { "id": "A1", "text": "工作温度范围按 0~50°C 民用级", "source_ids": [], "status": "recorded" }
  ],
  "forbidden_assumptions": [                         // 禁止下游做出的假设（护栏，下游命中即 fail）
    "禁止在未询问用户的情况下增加 Wi-Fi 模块"
  ],

  // ── 绑定 ──
  "intent_binding": {
    "intent_path": "src/hardware/m2-board/intent_v1.json",
    "intent_sha256": "<intent 文件哈希>"              // 单向：contract 声明它覆盖哪个 intent
  },
  "contract_sha256": "<本文件（去掉该字段后）的 SHA256>"  // 自哈希，防篡改
}
```

**字段语义细则**（gate 校验对象）：
- `user_goal`：非空；若是转述（非原话），`author` 必须能看出 AI 参与。
- `source_statements[].type`：枚举 `power / mcu / sensor / connectivity / display / formfactor / other`（借 CircuitBot 五维框架，AEDL 扩 formfactor/other）。
- `open_questions[].kind=blocking`：该问必须**有答案**才允许生成 intent；答案允许是 "unknown"（用户明确说不知道），但必须是显式答案。
- `assumptions[]`：每条必须带 `source_ids`（可为空数组=纯假设）与 `status: recorded`。
- 自哈希方式：序列化时剔除 `contract_sha256` 字段后算 SHA256（与 delivery manifest 的 `sha256` 条目同一套 `sha256_file` 语义）。

---

## 3. Gate：requirements_contract_gate（第 10 个门禁）

文件：`gates/requirements_contract.py`，注册进 `run_gates.py` 的 `gates = [...]` 列表（纯追加一行 `_safe_gate("requirements_contract", ...)`，不动其他）。

检查项（全部确定性，无 LLM）：

| # | 检查 | 失败条件 | 对应 CircuitBot 缺陷 |
|---|---|---|---|
| C1 | 合同文件存在且 JSON 可解析、schema_version=1、必填字段齐全 | 缺任一顶层字段 / 类型错 | - |
| C2 | 所有 `source_ids` 引用有效（指向存在的 statement id） | 悬空引用 | 无溯源 |
| C3 | 所有 blocking question 必须有非空 answer（"unknown" 合法） | blocking 未答 | **超时继续** |
| C4 | intent 引用完整：intent_v1.json 必须含 `requirements_contract: {sha256, path}` 且哈希与合同实际自哈希一致 | 缺引用/哈希失配 | 无绑定 |
| C5 | 合同时效：`created_at` 距 gate 运行 ≤ 7 天（同 BOM freshness 语义；过期=需重确认） | 超龄 | - |
| C6 | forbidden_assumptions 非空校验：intent 中若存在匹配禁令的组件/功能（关键字级映射，如"wifi"）则 FAIL | 命中禁令 | **静默注入 MCU** |
| C7 | assumptions 全部带 status=recorded；不得出现 status=implicit/hidden | 隐式假设 | 静默假设 |

**Gate 输出**：与既有门禁同构的 `{status, evidence, summary}` 结构，写入 `notes/<阶段>/generated/requirements_contract_current.json`。

**失败语义**：`_safe_gate` 包裹，任何异常 = FAIL（malformed evidence must never become green，沿用 gate_core 哲学）。

---

## 4. 与既有体系的关系（防打架）

- **不替代** schematic_semantics gate：那是 intent/netlist/PCB/firmware 四视图的技术语义校验；本 gate 只管"需求 -> intent"这一段的溯源完整性。
- **board_id 同键**：与 m2_schematic_contract_v1 共用 `board_id`，未来多板扩展时同键关联。
- **M2 追溯问题（需要人工拍板）**：M2 的 intent 已存在且无合同。两个选项：
  - **选项 A（推荐）**：M2 补一份"回溯合同"（`author: retroactive`），把当年会话里真实发生的需求决策补录进 contract，intent 加引用字段。诚实标注"补录"而非"当时生成"。
  - 选项 B：本 gate 只对 M3+ 生效，M2 豁免（gate 对缺文件报 SKIP 而非 FAIL）。
  - 选项 A 更符合"全链哈希绑定"叙事，但补录有"事后伪造"观感风险，需如实在 author 字段披露。
- **实装顺序**：gate 先行独立成文件+单测（不进 run_gates），测试全绿后经人工确认再挂为第 10 门禁。

---

## 5. 测试计划（STEP 6 VERIFY 的落地）

`tests/test_requirements_contract.py`，fixture 放 `tests/fixtures/requirements/`：

| Fixture | 场景 | 期望 |
|---|---|---|
| F1 | blocking question 无答案 | FAIL（C3） |
| F2 | 用户答 "No preference"/"unknown" | PASS 且 assumptions 含显式记录 |
| F3 | intent 引用的 sha256 与合同实际不符（模拟合同被改） | FAIL（C4） |
| F4 | 缺 forbidden_assumptions 字段 | FAIL（C1） |
| F5 | forbidden 禁令 "禁止 wifi" 而 intent 含 wifi 组件 | FAIL（C6） |
| F6 | created_at 超过 7 天 | FAIL（C5） |
| F7 | 合法完整合同 | PASS |
| F8 | JSON 损坏/字段类型错 | FAIL（C1，异常安全） |

全部通过后，F1/F3/F5 再镜像进 `gates/semantic_fault_injection.py` 的常驻注入清单（沿用既有 meta-verification 模式：校验器必须能抓住这些故障，否则注入本身 FAIL）。

---

## 6. 待人工拍板的决策点

1. **M2 追溯**：选项 A（补录合同）还是选项 B（M2 豁免）？--影响 gate 对 M2 的默认行为。
2. **过期阈值**：7 天是否合适（BOM freshness 也是 7 天，对齐还是区分）？
3. **C6 关键字映射**：forbidden 命中用关键字还是结构化组件匹配？v1 建议关键字（简单、可解释），v2 再结构化。
4. **实装时机**：等 M2 的 89 文件收尾后开工；本轮只留设计稿。

---

## 7. 风险与诚实边界

- 本设计稿**未经任何代码验证**，schema 字段在实装时可能调整（尤其自哈希的序列化细节）。
- "提问生成"环节（谁生成 open_questions）本稿刻意留白：会话中 AI 建议、人工审定的流程可以是灵活的，但**合同内容与校验是确定性的**。这个分离是设计核心，不是遗漏。
- CircuitBot 借用的部分（五维框架、选项交互模式）若最终实装包含其代码片段（关键词表等），须登记 THIRD_PARTY.md；纯思想借鉴不构成衍生作品（`TO_VERIFY`，非法律意见）。
- 该 gate 在 M3 出现前没有真实消费者--这是策略文档 STEP 6 指出的最大风险，人工评审时应同时决策"M3 是否立项"。
