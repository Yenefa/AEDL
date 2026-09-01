# 需求澄清工作台（TASK-P2）

静态单页，**零构建、零依赖、零安装**：双击 `web/index.html` 即可运行。

- 属主：TASK-P2 / `web/` 整个目录
- 接口契约唯一依据：`docs/api/requirements_api.md`
- 合同门禁唯一权威：`gates/requirements_contract.py`（C1-C7，Python，**无法在浏览器内运行**）

---

## 1. 它做什么

```
输入 NL 需求
  → POST /api/propose    LLM 建议的问题清单（answer 恒为 null）
  → 人工逐题作答 + 逐条确认/剔除假设
  → POST /api/finalize   生成需求合同（服务端写入自哈希）
  → POST /api/validate   展示 gate 校验结果 {status, errors}
```

前端实现了 `docs/api/requirements_api.md`「前端必须遵守的语义」四条：

1. **blocking 问题未作答，「生成合同」按钮不可用**，并实时显示「还剩 N 个必答问题」。
2. 答案下拉提供 `unknown` / `No preference`，但**必须显式选择**——空答案永远不允许提交
   （nonblocking 也一样，契约语义 #2 说的是"不许空着提交"，不限定问题类型）。
3. LLM 的问题清单**可增 / 删 / 改**后才作答。问题文本、kind、dimension、选项都可编辑。
4. 校验失败的 `errors[]` **原样渲染**，不过滤、不改写、不排序。

---

## 2. 运行

### MOCK 模式（默认，离线）

直接打开 `index.html`。`/api/*` 由 `mock-data.js` + `api-client.js` 内置的
mock 传输层应答，不联网。

### 真实 API 模式

右上角切到「真实 API」，填 baseURL（默认 `http://127.0.0.1:8787`）。
配置存 localStorage。

> P1 的 `gates/requirements_runtime_server.py` **尚未提供**，
> 因此真实模式下请求失败是预期行为，不是本前端的缺陷。

---

## 3. 文件

| 文件 | 作用 |
|---|---|
| `index.html` | 页面结构（无构建、无模板引擎） |
| `styles.css` | 样式（浅色主题，无框架） |
| `sha256.js` | 纯 JS SHA-256。**仅 mock 传输层用它模拟服务端自哈希** |
| `canonical-json.js` | 复刻 Python `json.dumps(ensure_ascii=False, sort_keys=True, separators=(",",":"))` |
| `contract-builder.js` | 组装合同草稿（无 DOM 依赖，供 UI 与测试共用同一条代码路径） |
| `mock-data.js` | 契约文档「Mock 数据」原样照抄 + mock 端预检 |
| `api-client.js` | 传输层：mock / http 双实现，按契约定义 5 个端点 |
| `app.js` | UI 逻辑 |
| `verify-hash.js` | 校验 JS 自哈希与 Python 门禁一致（Node） |
| `smoke-test.js` | 无头闭环测试（Node，无 DOM） |
| `e2e-browser.js` | 真实浏览器端到端驱动（`index.html?e2e=1`） |

加载顺序见 `index.html` 末尾：普通 `<script>`，**不是 ES module**——
`file://` 协议下 module 会被 CORS 拦掉。

---

## 4. 验证方式

三条验证，从纯逻辑到真实浏览器，全部可复现。

```bash
# 1) JS 自哈希 == Python 门禁自哈希（跨语言交叉验证）
node web/verify-hash.js
#    -> OK: JS digest matches the Python gate's digest for this contract
#    目标：gates/requirements/requirements_contract_v1.json（M2 真实合同，
#          Python 门禁已 PASS，声明哈希 82c136df...）

# 2) 无头闭环（propose -> answer -> finalize -> validate）
node web/smoke-test.js
#    -> SMOKE TEST PASSED
#    产物写入 web/_smoke_out/requirements_contract.json

# 3) 真实浏览器端到端
#    浏览器打开 web/index.html?e2e=1
#    -> E2E PASSED (19/19)
#    无头复现：
#    chrome --headless=new --dump-dom "file:///.../web/index.html?e2e=1"

# 4) 用权威 Python 门禁校验前端生成的合同（真正的验收）
python -c "import sys; sys.path.insert(0,'.'); \
from gates.requirements_contract import validate_requirements_contract; \
print(validate_requirements_contract('web/_smoke_out/requirements_contract.json', None))"
```

`_smoke_out/` 是脚本产物，可随时删除重生成。

---

## 5. 契约缺口与冲突（已记录，未自行猜测定义）

开发过程严格以 `docs/api/requirements_api.md` 为唯一依据。
以下 5 项是该文档**未定义**之处，前端按文档字面实现并在 UI 中明示，
**没有自行发明定义**，全部待 P1（ZCode/GLM）定案：

| # | 位置 | 问题 | 前端当前处理 |
|---|---|---|---|
| 2 | `POST /api/propose` | 「入参 NL 需求文本」，**请求体形状未定义** | 发 `{"request": "..."}`，键名取自 P1 的 `build_proposal_prompt(request)` 参数名 |
| 3 | `POST /api/finalize` | 「入参 用户最终确认」，**请求体形状未定义** | 发 `{"contract": <draft>}` |
| 4 | `POST /api/validate` | 「入参 合同路径」。浏览器没有服务端文件系统视角，**契约未定义前端如何取得该路径**；键名也未定义 | 发 `{"path": ...}`，路径由第 5 步输入框手动填写 |
| 5 | `POST /api/answer` | 「返回未答 blocking 数」，**返回结构未定义** | 前端**不依赖**该返回值：未答 blocking 数由本地问题清单重算；原始响应只在调试可见 |
| 6 | 错误处理 | 契约除 `GET /api/contract` 的 404 外**未定义任何错误码** | 404 = 无合同；其余原样透出 HTTP status + body |

**已解决（历史记录）**：原缺口 #1（`intent_binding` 要 `intent_sha256` vs C4 只收
`intent_path`）已由 C 方案落地终结——`intent_binding` 现为
`{intent_path, intent_semantic_sha256}`，其中语义哈希 = intent 的
`components`/`nets` 白名单 canonical JSON sha256，由**服务端**在 finalize 时写入
（见 `docs/api/requirements_api.md`「intent_binding 语义哈希范围」）。
前端草稿**只写 `intent_path`**，语义哈希不归前端算。

由此产生一条**当前 mock 的已知限制**（诚实边界，非 bug）：mock 传输层没有 intent
文件可读，无法替服务端计算语义哈希，因此 **MOCK 模式生成的合同不含
`intent_semantic_sha256`**，送真实门禁 C4 会因缺字段 FAIL。要拿到能过门禁的合同，
必须走真实 API（`/api/finalize` 服务端读 intent 计算）。页面第 4 步已明示。

另有一处**契约内部隐含的映射规则**（不属缺口，但值得写明）：

`ProposedQuestion` 带 `dimension` / `options` / `source`，而合同的
`open_questions` 条目**必须恰好是** `{id, question, answer, kind, source_ids}`。
因此 `dimension`、`options`、`source` **不进合同**（否则门禁判 unknown field）。
`contract-builder.js` 已按此裁剪。同理 `assumptions` 只保留
`{id, text, source_ids, status}`，`requires_human_confirmation` 不进合同。

---

## 6. 诚实边界（请勿误解这几件事）

- **第 5 步的 PASS 不是真实门禁的 PASS。**
  MOCK 模式下 `/api/validate` 是前端本地预检，只覆盖契约文档**明文规定**的规则
  （字段类型、blocking 必答、必须显式作答等）。
  它**不是** `gates/requirements_contract.py` 的 C1-C7，也没有能力替代它。
  结果面板已明确标注来源。

- **`contract_sha256` 由服务端写入。** 前端草稿不含该字段；
  mock 传输层为了能在离线演示闭环，用 `canonical-json.js` + `sha256.js`
  复刻了 Python 的算法，并用 `verify-hash.js` 与真实门禁交叉验证（见第 4 节）。
  真实模式下该字段一律来自 `/api/finalize`。

- **本目录不含任何第三方依赖**，未引入任何框架、构建工具或 CDN 资源。
