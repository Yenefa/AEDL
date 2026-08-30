# Requirements Runtime API 契约 v1（P2 前端对接用）

> 属主：P1（ZCode/GLM）。P2 前端按此契约开发，可用 mock 数据先行。
> 真实服务未起时，前端默认走内置 mock（见文末），配置项切真实。

## 端点总览（预留，最终形态以 P1 实装为准）

运行时是一个简易 HTTP 服务（P1 计划 `gates/requirements_runtime_server.py`，标准库 `http.server`，零依赖）：

```text
POST /api/propose      入参 NL 需求文本 -> 出参 LLM 建议的问题清单（answer 全为 null）
GET  /api/contract     出参 当前合同（无则 404）
POST /api/answer       入参 {question_id, answer} -> 合并答案，返回未答 blocking 数
POST /api/finalize     入参 用户最终确认 -> 生成合同（含自哈希 + intent 语义哈希），返回合同全文
POST /api/validate     入参 合同路径 -> 出参 gate 校验结果 {status, errors}
```

> **/api/finalize 与语义哈希**：服务端组装合同时会写入
> `intent_binding.intent_semantic_sha256`（由服务端读 intent 计算，值 = 白名单
> `components`/`nets` 的 canonical JSON sha256，见下文）。前端草稿**不需要**也不应该
> 自己算这个值——签名时刻的电路快照由服务端采集，前端只传 `intent_path`。
> （`gates/requirements_runtime.py::draft_contract` 相应增加了必填参数
> `intent_semantic_sha256`，由调用方传入。）

## 数据形状（TypeScript 风格伪码）

```ts
// POST /api/propose 返回
interface ProposalResponse {
  questions: ProposedQuestion[];
  assumptions: ProposedAssumption[];
  warnings: string[];           // LLM 输出的垃圾会被降级为警告，永不抛异常
}

interface ProposedQuestion {
  id: string;                   // "Q1".."Q5"
  question: string;             // 一句话，一个主题
  kind: "blocking" | "nonblocking";  // 不认识的一律升为 blocking（fail-safe）
  dimension: "power" | "mcu" | "sensor" | "connectivity" | "display" | "formfactor" | "other";
  options: string[] | null;     // 2-4 个具体选项，可空
  source: "llm_proposal";
  answer: null;                 // 恒为 null：答案只来自人类
}

interface ProposedAssumption {
  id: string;                   // "A1"..
  text: string;
  requires_human_confirmation: true;
}

// POST /api/answer 入参 / POST /api/validate 返回
interface GateVerdict {
  status: "pass" | "fail";
  errors: string[];             // 人话，直接可展示
}
```

## 合同 JSON 形状（/api/finalize 产出，与 gates/requirements/requirements_contract_v1.json 同构）

```jsonc
{
  "$schema": "https://aedl.local/schemas/requirements-contract.v1.json",
  "schema_version": 1,
  "board_id": "…",
  "created_at": "2026-08-31T12:00:00+08:00",
  "author": "human+ai",
  "user_goal": "…",
  "source_statements": [{"id": "S1", "text": "…", "type": "power"}],
  "resolved_requirements": [{"id": "R1", "text": "…", "source_ids": ["S1"]}],
  "open_questions": [{"id": "Q1", "question": "…", "answer": "不需要", "kind": "blocking", "source_ids": ["S1"]}],
  "assumptions": [{"id": "A1", "text": "…", "source_ids": [], "status": "recorded"}],
  "forbidden_assumptions": ["…"],
  "intent_binding": {
    "intent_path": "…",
    "intent_semantic_sha256": "…"   // 见下方「intent_binding 语义哈希范围」
  },
  "contract_sha256": "…"
}
```

> **intent_binding 仍是单向绑定（lockfile 模式），不含 intent 的整文件哈希。**
> 双向哈希（intent 存合同哈希 + 合同存 intent 整文件哈希）是循环依赖，数学上无法同时满足。
> 维持单向：intent 侧持有 `{sha256, path}` 指向合同（见 intent_v1.json 的
> `requirements_contract` 字段），合同侧声明 `intent_path` **加上 `intent_semantic_sha256`**。
> 语义哈希只取 intent 的 `components`/`nets` 两字段（不含合同指向、不含元数据），
> 因此既补上了"改电路必须重签"的缺口，又不产生循环依赖。
> 前端组装合同草稿时**只写 `intent_path`**：`intent_semantic_sha256` 由服务端在
> finalize 时读 intent 计算写入（见上方 /api/finalize 说明）；前端写
> `intent_sha256`（整文件哈希，从未实装）或任何多余字段都会被门禁 C4 判 unknown field 而失败。

### intent_binding 语义哈希范围（C4 语义锁）

`intent_semantic_sha256` 是 **intent 电路语义字段的哈希**，不是整个 intent 文件的哈希：

```text
sha256( canonical_json( { "components": intent.components,
                          "nets":       intent.nets } ) )

canonical_json = json.dumps(..., ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"))
```

**白名单（写死约定，见 `gates/requirements_contract.py::INTENT_SEMANTIC_FIELDS`）**：只有 `components` 与 `nets`。

- **进哈希**：`components`（板上有什么器件）、`nets`（它们怎么连）。
- **不进哈希**：`requirements_contract` 绑定字段本身、`protocol_version` 等元数据。
  排除绑定字段是为了维持单向、避免循环依赖；因此重指绑定（不改电路）**不需要重签合同**。
- 缺失的白名单字段按 `null` 参与哈希，不会被跳过——破损的 intent 不会和正常的算出同一个哈希。

**维护约定（双向强制）**：将来 intent 协议新增**描述电路语义**的字段时，必须同步加进白名单；
反之，往白名单加字段会让所有已签合同一次性失效，所有板子须在同一变更内重签。

**为什么要这个锁**：只有 lockfile 绑定时，改 `components`（换料/加器件）而保留旧合同引用，
门禁照样 PASS——合同就成了"描述一块它从没见过的板子"。语义锁让任何电路变更都要求重签
合同（C4 报 `intent 语义内容已变更，须重签合同`）。

## 前端必须遵守的语义（这是 AEDL 的命根子，不是 UI 细节）

1. **blocking 问题未回答，"生成合同"按钮必须不可用**（可显示"还剩 N 个必答问题"）--对应 CircuitBot fail-open 缺陷的反转。
2. 用户的答案可以是 "unknown" / "No preference"（下拉里提供）--但必须显式选择，不许空着提交。
3. LLM 的建议只是建议：前端允许人类**增/删/改**问题清单后才作答（建议层与合同层分离）。
4. 校验失败的 `errors[]` 原样展示，不许前端过滤或"美化"。

## Mock 数据（真实服务未起时前端内置）

```json
{
  "questions": [
    {"id": "Q1", "question": "板子如何供电？", "kind": "blocking", "dimension": "power",
     "options": ["USB-C 5V", "锂电池", "外部电源"], "source": "llm_proposal", "answer": null},
    {"id": "Q2", "question": "需要板载调试器吗？", "kind": "blocking", "dimension": "other",
     "options": ["需要", "不需要"], "source": "llm_proposal", "answer": null},
    {"id": "Q3", "question": "工作温度范围？", "kind": "nonblocking", "dimension": "other",
     "options": ["民用 0~50°C", "工业 -40~85°C"], "source": "llm_proposal", "answer": null}
  ],
  "assumptions": [
    {"id": "A1", "text": "默认单面板两层布线", "requires_human_confirmation": true}
  ],
  "warnings": []
}
```
