# AEDL 两人 + 多 AI 协作协议 v4（2026-09-01）

> 📢 **公告（2026-09-01）**：大统领 GitHub 账号已由 `sca331613-commits` 改名为 **`Yenefa`**。
> 旧 URL 靠重定向仍可达；新建仓库/引用一律用 `Yenefa`；`gh repo create` 不带用户名前缀。
> 当前 private 的实验/Evidence 卫星仓：`https://github.com/Yenefa/AEDL-spike`；其治理入口为
> `Yenefa/AEDL-spike#1` / Draft PR #2。

> 目的：两名真人开发者通过各自独立 clone 协作，同时允许多个 AI 会话在受控领地内辅助；所有成果经 Issue、任务分支、PR 和另一名真人 Review 交接，避免覆盖、混提和身份误记。
> 本协议是 AGENTS.md 的并行扩展，冲突时以 AGENTS.md 为准。
> **每个会话开工时（按序，缺一不可）**：读 `AGENTS.md` → 读 `docs/HANDOFF.md` 状态卡 → **读本文件** → `git status` 看现场 → 在 `docs/compliance/AI_USAGE_LOG.md` 领号（见 §0.1）。
> v4 变更：新增主仓与实验/Evidence 卫星仓的唯一职责和回流协议（§0.7）；v3 的真人协作者身份、独立 clone、Issue-first 分支/PR 和 GitHub 强制能力边界继续生效。治理实施由 GitHub Issue #1 跟踪。

## 0. 比赛时钟（2026-08-31 大统领确认）

- **AIC 赛事提交截止约 2026-10-03（还剩约 33 天）**。所有任务按此排优先级。
- 关键路径：人工重签 board_review → 嘉立创下单（物理周期 1-2 周）→ 回件 C 级实测 → 报告/PPT/视频 + FAIRNESS_CHECK + 版本冻结。
- 板子生产是唯一不可压缩环节：9 月第一周不下单，实测容错窗口就没了。
- 等板子的窗口（9 月上中旬）= 并行任务黄金期：competition 资产、C 方案升级、前端、intake 全在这里消化。
- 资产现状（2026-09-01 实查）：`FUSION_MAP.md`、`OPEN_OUTPUTS.md`、`PROBLEM_EVIDENCE.md`、`SUBMISSION_CHECKLIST.md` 已存在；`AIC_STANDARD.md`、`SCORING_MAP.md` 仍不存在。后两者在触发正式评分/定位任务前保持 `NOT_FOUND`，不得假装已读。

---

## 1. 文件领地划分（核心规则）

每个任务有**唯一属主**。属主外的一切文件只读。需要跨领地改动时，在 TASKS 看板留言请求，不擅自动手。

| 任务 ID     | 领地（可写）                                                                                                                                             | 依赖他人的部分                                             |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| P1-CONTRACT | `gates/requirements_contract.py`、`gates/requirements_runtime.py`、`tests/test_requirements_*.py`、`tests/fixtures/requirements/`、`gates/requirements/` | 前端 API 形状可先 mock                                     |
| P2-FRONTEND | `web/` 整个目录（新建）                                                                                                                                  | 只依赖 P1 在 `docs/api/requirements_api.md` 声明的接口形状 |
| P3-INTAKE   | `notes/open_source_intake/*.md`（四份项目报告）                                                                                                          | 无依赖，纯研究                                             |
| P4-GATES    | `gates/run_gates.py`（挂载第 10 门禁）                                                                                                                   | **必须等 P1 测试全绿 + 大统领确认后才动**                  |

**共享只读区**（谁都不许写，除非大统领指令）：`src/`、`delivery/`、`docs/compliance/` 台账（追加自己那条除外）、既有 9 门禁代码、`notes/m2-*`。

**追加型文件**（只许 append 自己的条目，不许改别人的）：`docs/compliance/AI_USAGE_LOG.md`、`docs/HANDOFF.md`（各改各的章节）。

## 0.1 台账领号（防撞号，2026-08-31 两次实战撞号后固化）

1. 领号 = `grep -o "AI-2026[0-9-]*" docs/compliance/AI_USAGE_LOG.md | sort -u | tail -1` 取最大号 +1。
2. **领号后第一步立即追加占位条目**（标题 + 一行"claimed by <会话名>，内容完工后补"）再开始干活——占位即锁号。
3. 提交信息里的 `[AI-...]` 标签以台账条目**内容**为准，撞号时按条目甄别，不改写已提交历史。

## 0.2 pre-commit 钩子（prettier）处置规则

- 钩子会要求重排 md/json。**证据文件（manifest、receipt、test-results、datasheet 记录）严禁重排**——哈希绑定的证据改字节 = 破坏证据链。
- 证据批次 commit 用 `git commit --no-verify`，**理由必须写进提交信息**（如 "evidence JSON is hash-bound, reformatting would alter evidence bytes"）。
- 纯文档/代码批次正常过钩子；`--no-verify` 是例外不是惯例，滥用=违规。

## 0.3 撞车仲裁（同树多 agent 实战规则）

1. 发现自己的领地文件已被他人修改（内容/mtime 不符）：**立即停手**，不 revert 不覆盖。
2. 评估：对方方案更优 → 撤自己撞车部分、保留对方、补对方遗漏的接缝（参考 AI-20260831-020 的处理）。
3. 无法判定优劣 → 报告大统领取舍，两边都停在 PENDING_HUMAN_REVIEW。
4. 预防：开工前 `git status` + `git diff <自己领地文件>` 必做；大任务先写任务卡（§3 看板）再动手。

## 0.4 真人协作者接入与身份边界

1. **一人一份 clone**：两名真人不得共用同一个工作目录、index 或未提交工作树。AI 可以在其所属真人的 clone 内工作，但必须服从该任务 Issue 的 Owner 与领地。
2. **身份先核实再归因**：项目负责人已确认 GitHub 账号 `la4876949-bot` 是第二名真人协作者，当前具有 write 权限；另有一条 `invitee=null` 的未过期 write 邀请，接收人仍为 `UNKNOWN`，不得据此推断第三人身份。
3. **贡献分类**：项目负责人已确认 `la4876949-bot` 为 `AEDL_TEAM`（正式团队成员）。成员身份不等于已经产生贡献；只有实际贡献发生后才写入 `TEAM_CONTRIBUTIONS.md`。未来如接收外部贡献，仍须保留来源、授权、使用边界，不得包装成正式团队自主成果。
4. **正式 clone 地址**：只使用 `https://github.com/Yenefa/AEDL.git`。旧 owner URL 仅为历史重定向，不再写入新文档或命令。
5. **当前协作基线**：`fix/m2-schematic-semantic-release` @ `e7ff3c1` 是 2026-09-01 治理启动前冻结点。治理 PR 合入后，以该远端分支最新提交为任务分支起点；不要从当时落后 44 个提交的默认 `master` 开工。

首次接入命令：

```powershell
git clone https://github.com/Yenefa/AEDL.git
cd AEDL
git fetch origin
git switch --track origin/fix/m2-schematic-semantic-release
```

## 0.5 Issue → Branch → PR → Review

1. **先建 Issue**：每个工作单元只有一个 Goal、一个 Owner 和一组独占写路径。Issue 必须写 Scope、Out of Scope、Acceptance Criteria、Evidence Needed、AIC Score Target 与合规触发项。
2. **再开任务分支**：从最新协作基线创建 `feat/`、`fix/`、`docs/`、`test/`、`chore/` 等任务分支；一个分支只承载一个 Issue。
3. **禁止直推共享分支**：不得直接向 `master` 或 `fix/m2-schematic-semantic-release` 提交任务改动。当前过渡期 PR 目标为 `fix/m2-schematic-semantic-release`；待该分支经稳定化 PR 回归 `master` 后，恢复以 `master` 为唯一稳定基线。
4. **逐路径暂存**：`git add <明确路径>`；禁止 `git add .`、`git add -A`。提交前检查 working/staged diff、secret、Evidence 字节与未知删除。
5. **另一名真人 Review**：作者不能把自己的 PR 标记为人工批准。审查者核对真实 diff 与实际测试后才能合并；AI 始终保持 `PENDING_HUMAN_REVIEW`。
6. **冲突串行化**：两个 Issue 需要同一文件时，后领任务暂停该文件，由前一 Owner 完成交接或项目负责人重新划分领地；禁止依赖事后冲突合并解决所有权问题。

GitHub 模板：`.github/ISSUE_TEMPLATE/task.md`、`.github/PULL_REQUEST_TEMPLATE.md`；`CODEOWNERS` 只作审查提醒，不能替代 Issue Owner。GitHub 官方规则要求 Issue/PR 模板位于**默认分支**才会自动出现在新建界面；当前默认 `master` 尚未包含本治理批次，因此稳定化合入 `master` 前，模板文件只能作为手工填写规范，不能声称 UI 已自动启用。

## 0.6 当前 GitHub 强制能力边界

- 仓库为 private；2026-09-01 对 `master` 与协作基线查询 branch protection/rulesets 均返回 403，提示需升级套餐或公开仓库。
- 在许可证、第三方再分发与公开内容边界未完成前，**不得为了分支保护把仓库改成 public**。
- 当前所有“禁止直推”“必须另一名真人 Review”等要求均属于协作流程纪律，由 Yenefa 与 Percy 在各自操作及 Merge 决策中共同执行；AI 不得把未受 GitHub 技术强制的规则描述成已技术锁定。
- 若套餐或可见性变化，先建立最小 ruleset（禁止 force-push、要求 PR、至少 1 名真人 Review），再更新本节。

## 0.7 主仓 ↔ 实验/Evidence 卫星仓

1. **主仓唯一真源**：`Yenefa/AEDL` 负责集成代码、工程合同、ADR、合规台账、比赛主张、正式 Evidence 索引与制造权限；任何对外能力主张必须能回到主仓的确定提交和证据。
2. **卫星仓职责**：`Yenefa/AEDL-spike` 负责边界清晰的协议执行器实验、故障注入样例和过程 Evidence。卫星实验通过不等于主仓已集成、M2 已制造放行或实体硬件已验证。
3. **各仓独立治理**：卫星任务同样执行 Issue → task branch → Draft PR → 另一名真人 Review；不得直接 push/force-push 其 `main`。当前入口为卫星 Issue #1 / Draft PR #2。
4. **受控回流**：准备吸收卫星成果时，在主仓创建或扩展一个 Issue，明确写出 exact spike commit、源文件路径、要吸收的机制、复现命令、已知限制和主仓独占写路径；随后只在主仓任务分支集成并重新验证。
5. **Evidence 不偷换**：卫星的历史 Evidence 保留原路径和提交；主仓可以索引或镜像可审计摘要，但不能把旧运行重命名成当前运行、把 native/Wokwi 结果写成物理结果，或手工改写原始 Evidence 得到 PASS。
6. **架构与许可证边界**：卫星仓不单独改变主仓架构、比赛主张、制造签发、公开范围或许可证。需要公开或再分发时，先核对 `THIRD_PARTY_RESOURCES.md`、`NOTICE` 和 `OPEN_OUTPUTS.md`，由人类裁决。
7. **不在两仓重复开发同一任务**：同一工作单元必须指定主仓或卫星仓为 Owner；跨仓修改可以共享一个 AI Usage ID，但每个仓都保留自己的 commit、PR 和 Handoff。

## 0.8 权限语义：OWNED / SHARED / FOREIGN

三个文件分工：`CODEOWNERS` = Who（review 路由）；本文件 = 权限语义（Policy）；`AGENTS.md` = Agent 执行规则（Execution）。

- **OWNED**：列明的 Owner 主导修改；正常 PR 流程。
- **SHARED**（contracts/schemas、核心状态、Evidence 语义、`.github/workflows`）：任何实质修改必须 Yenefa + Percy 双人确认。
- **FOREIGN**：对当前任务负责人默认只读；确需修改必须扩 Scope + Impact Analysis，获得相应 Owner 确认。

**CODEOWNERS 是路由器不是警察**：它自动请求相关 Owner 的 Review，但当前 GitHub 套餐无法强制 gate；SHARED 双人确认由本规范规定，并由成员在 Merge 前人工执行。

## 2. 交接规范

1. **开工**：`git status` 确认自己领地内没有别人未提交的改动（有 -> 停，按 §0.3 仲裁）。
2. **每个工作单元结束**：在自己领地内留产物 + 在 `docs/HANDOFF.md` 的"并行会话状态"章节写三行：做了什么 / 文件清单 / 下一步。
3. **commit 授权分级（v2 改）**：
   - **大统领已验收/明示提交的批次**：执行会话可 commit + push，提交信息带 `[AI-...]` 标签。
   - **未验收的在制品**：不 commit，靠 handoff + 台账留痕。
   - 同树多会话时：commit 前确认只暂存自己领地文件（`git add` 逐路径），**禁止 `git add -A`**——防止把他人未提交批次混进提交。
4. **冲突处理**：见 §0.3。
5. **红线继承 AGENTS.md**：AI 不得设置 `manufacturing_release=true` / `HUMAN_REVIEWED` / `ACCEPTED`；不得动 board_review 签发；不得把 Wokwi/DRC 说成实体验证。

## 3. 任务看板（TASKS）

状态：`open`（可领） / `claimed`（某 AI 领取中） / `blocked`（等依赖） / `done`

### TASK-P1：Requirements Contract 实装 ✅ done（AI-20260831-002，待人工审）

- 属主：ZCode/GLM
- 完成内容：`gates/requirements_contract.py`（C1-C7）+ `gates/requirements_runtime.py`（LLM 建议层）+ 18 测试全绿 + M2 补录合同（决策 A）+ 第 10 门禁挂载（10 gate：9 PASS + board_review 待重签）+ 95/95 回归通过
- 待人工审：单向绑定修复、补录合同内容、挂载、COLLABORATION.md 本身

### TASK-P2：简易前端（需求澄清工作台）✅ done（AI-20260831-003，待人工审）

- 属主：WorkBuddy（本次会话）
- 内容：`web/` 下静态单页（纯 HTML+JS，零构建，双击可开）。功能：输入 NL 需求 -> 展示 LLM 建议的问题清单（从 mock/真实 runtime 来）-> 人工逐题作答 -> 生成合同 JSON 预览 + 下载 -> 展示 gate 校验结果。**接口契约见 `docs/api/requirements_api.md`（P1 已备好）**。
- 验收：浏览器打开能用；mock 模式演示完整闭环；真实 API 接入点预留（配置项/baseURL）。

**实际改动文件清单**（全部在 `web/` 领地内，新增，无越界）：

| 文件                      | 说明                                                                                   |
| ------------------------- | -------------------------------------------------------------------------------------- |
| `web/index.html`          | 页面结构，5 步工作流；普通 `<script>` 非 ES module（`file://` 下 module 会被 CORS 拦） |
| `web/styles.css`          | 浅色主题样式，无框架                                                                   |
| `web/sha256.js`           | 纯 JS SHA-256，仅 mock 传输层用于模拟服务端自哈希                                      |
| `web/canonical-json.js`   | 复刻 Python `json.dumps(ensure_ascii=False, sort_keys=True, separators=(",",":"))`     |
| `web/contract-builder.js` | 组装合同草稿，无 DOM 依赖，UI 与测试共用同一条代码路径                                 |
| `web/mock-data.js`        | 契约文档「Mock 数据」原样照抄 + mock 端预检                                            |
| `web/api-client.js`       | 传输层：mock / http 双实现，按契约定义 5 个端点                                        |
| `web/app.js`              | UI 逻辑                                                                                |
| `web/verify-hash.js`      | Node：校验 JS 自哈希与 Python 门禁一致                                                 |
| `web/smoke-test.js`       | Node：无头闭环测试（无 DOM）                                                           |
| `web/e2e-browser.js`      | 真实浏览器端到端驱动（`index.html?e2e=1`）                                             |
| `web/README.md`           | 运行方式、验证方式、契约缺口与诚实边界                                                 |

领地外仅按大统领指令追加：`docs/COLLABORATION.md`（本卡片）、`docs/compliance/AI_USAGE_LOG.md`（新增一条）。
未 commit、未 push、未建 PR。

**关键实现说明**：

1. 契约「前端必须遵守的语义」四条逐条落地：① blocking 未答则「生成合同」按钮 disabled 并显示「还剩 N 个必答问题」；② 下拉提供 `unknown` / `No preference`，但空答案永不许提交（nonblocking 同样要求显式选择）；③ 问题清单增/删/改后才作答（文本、kind、dimension、选项均可编辑）；④ `errors[]` 原样渲染，不过滤不美化。
2. **自哈希归属服务端**：前端草稿不含 `contract_sha256`，由 `POST /api/finalize` 写入。mock 传输层为能在离线演示闭环，用 `canonical-json.js` + `sha256.js` 复刻 Python 算法，并已与真实门禁交叉验证。
3. **字段裁剪**：`open_questions` 恰好为 `{id, question, answer, kind, source_ids}`，故建议层的 `dimension`/`options`/`source` **不进合同**（否则门禁判 unknown field）；`assumptions` 同理只保留 `{id, text, source_ids, status}`。已确认假设写入，剔除的假设不留痕。
4. **零依赖**：未引入任何框架、构建工具或 CDN 资源。

**验证**（全部真实运行，非推断）：

- `node web/verify-hash.js` → `OK: JS digest matches the Python gate's digest`。对 `gates/requirements/requirements_contract_v1.json`（M2 真实合同，Python 门禁已 PASS，声明哈希 `82c136df...`）重算，JS 与 Python 得**同一**摘要 `82c136dfe9da...e5d8`。
- `node web/smoke-test.js` → `SMOKE TEST PASSED`（propose→answer→finalize→validate 全绿 + fail-closed 反例）。
- 真实浏览器 `web/index.html?e2e=1` → `E2E PASSED (19/19)`（Chrome headless `--dump-dom` 复现，驱动真实 DOM 事件与按钮）。
- **权威门禁反验**：把前端生成的合同送 `gates/requirements_contract.py`，`contract_sha256` 重算**一致**；C1-C7 仅报 1 条错误，即下方遗留问题 #1。把 `intent_binding` 改为 C4 要求的 `{intent_path}` 后**错误归零**——证明合同组装本身完全正确，冲突是唯一阻塞项。

**遗留问题 / 契约缺口（提交 P1 · ZCode/GLM 定案，前端未自行猜测定义）**：

1. ⚠️ **契约与实现矛盾（阻塞）**：`docs/api/requirements_api.md` 要求 `intent_binding` 含 `intent_path` + `intent_sha256`，而 `gates/requirements_contract.py` C4 要求**恰好只含 `intent_path`**（`if set(binding) != {"intent_path"}`）。前端按契约文档生成（本次指令明确：契约文档为唯一依据），故该合同送真实门禁时 C4 必 FAIL。页面第 4 步已加醒目提示。**建议 P1 二选一：改契约文档删 `intent_sha256`，或改 C4 放行两字段并说明 `intent_sha256` 语义。**
2. `POST /api/propose` 请求体形状未定义（只说「入参 NL 需求文本」）→ 前端发 `{"request": "..."}`，键名取自 P1 的 `build_proposal_prompt(request)` 参数名，待确认。
3. `POST /api/finalize` 请求体形状未定义（「入参 用户最终确认」）→ 前端发 `{"contract": <draft>}`，待确认。
4. `POST /api/validate` 入参「合同路径」：**浏览器没有服务端文件系统视角，契约未定义前端如何取得该路径**，键名亦未定义 → 前端发 `{"path": ...}`，路径由第 5 步输入框手填。建议 P1 补充浏览器侧约定（或改传合同正文）。
5. `POST /api/answer` 返回结构未定义（只说「返回未答 blocking 数」）→ 前端**不依赖**该返回值，未答 blocking 数由本地问题清单重算，原始响应仅调试可见。
6. 错误码：契约除 `GET /api/contract` 的 404 外**未定义任何错误码** → 前端按 404=无合同、其余原样透出 status+body 处理，建议补全。
7. P1 的 `gates/requirements_runtime_server.py` 尚不存在，真实 API 模式当前必然连接失败（预期行为，已在 UI 明示）。

**诚实边界（避免误读验收结果）**：MOCK 模式下第 5 步的 `PASS` 是**前端本地预检**，只覆盖契约文档明文规定的规则，**不是** `gates/requirements_contract.py` 的 C1-C7 结果，也不能替代它。结果面板已显式标注来源。

### TASK-P3：开源 Intake Phase 2-3（KiCad MCP + KiCadAI 研究）✅ done（AI-20260831-004，待人工审）

- 属主：ZCode/GLM（P3 会话）
- 完成内容：`notes/open_source_intake/kicadai.md` + `kicad-mcp.md` 六步协议完成；本地浅克隆双仓库做源码级核实（`_kicadai_repo/` @ `4f18765`、`_kicad_mcp_repo/` @ `aa53d52`，均含 .git 勿提交）；intake README 目录状态同步。
- 关键校准：碰撞分析 §6.2"KiCadAI 的 KiCad 生成链路未见源码"经本地克隆复核**判为误判**（writer/ERC-DRC subprocess/MNA 仿真源码俱在；kicadai.md 附节有逐项对照与误判归因——其会话当时抓不到仓库内容，与其 §5 自我教训同型）；§6.1 kicad-ai(amcolex) 本轮 WebFetch 取得 GitHub 404 渲染页（非网络故障），"从未存在"的强结论仍待人工浏览器定案。
- 合规红线新发现：KiCad MCP（mixelpixx）后继项目 **Konnect 为 AGPL-3.0**，AEDL 禁止吸收（已写入 kicad-mcp.md）。
- 待人工审：两份 intake 报告；碰撞分析校准结论是否回写 `notes/competitor-collision-analysis-2026-08-30.md`（该文件非 P3 领地，本轮**未改动**，仅在 kicadai.md 内对照）；两个克隆目录是否预先加入 .gitignore 排除。

### TASK-P4：第 10 门禁挂载 ✅ done（与 P1 同会话完成）

- 已挂载：`gates/run_gates.py` gates 列表追加 `_safe_gate("requirements_contract", ...)`，纯增量。
- 注意：test_run_gates.py 的 gate 集合断言已同步 9->10（预期契约变更）。

### TASK-P5：C 方案——intent 语义哈希绑定 ✅ done（AI-20260831-006，待人工审）

- 属主：WorkBuddy（大统领直接指派，领地：`gates/requirements_contract.py`、`gates/requirements/`、`gates/requirements_runtime.py`、`tests/test_requirements_contract.py`、`docs/api/requirements_api.md`）
- 解决的缺口：单向 lockfile 绑定抓不到"改电路不重签"——**已实测**：往 intent 塞一个 U9 电阻、保留旧合同引用，gate 仍 PASS（合同描述一块它从没见过的板子）。
- 实现要点：
  - `INTENT_SEMANTIC_FIELDS = ("components", "nets")` **白名单写死在代码注释**（双向维护约定：intent 协议新增电路语义字段必须跟白名单；加白名单字段=所有已签合同一次性作废，须同变更重签）。
  - `intent_semantic_sha256(intent)`：对白名单两字段做 `json.dumps(ensure_ascii=False, sort_keys=True, separators=(",",":"))` 后 sha256。缺失字段按 `null` 参与哈希不跳过（破损 intent ≠ 正常 intent）。
  - 合同 `intent_binding` 从 `{"intent_path"}` 扩为 `{"intent_path", "intent_semantic_sha256"}`，**仍是单向**：语义哈希只依赖 intent 的 components+nets，不碰合同内容，无循环依赖。
  - C4 新增语义检查：不一致 → `intent 语义内容已变更，须重签合同 (...)`。
  - `requirements_runtime.py::draft_contract` 新增必填参数 `intent_semantic_sha256`（组装层不做 IO，"签哪个电路版本"必须显式出现在调用点）。
  - **禁止项均遵守**：未引入双向哈希；`requirements_contract` 绑定字段本身不计入语义哈希。
- M2 重签与级联：合同写入语义哈希 `be8b649c…b850` 并重算自哈希 `82c136df…` → `f0fec3f8…48d8`；intent 的 lockfile 引用同步重指（**跨领地单行改动**，`src/` 共享只读区，依据大统领验收标准"requirements_contract 仍 PASS"的必然要求）；delivery manifest 经 `export_delivery.py` 重导，4 个 source 哈希绑定全部复核一致。
- 契约文档同步：`docs/api/requirements_api.md` 新增「intent_binding 语义哈希范围」章节（白名单、排除项、维护约定、canonical JSON 定义），并修正 finalize 说明（服务端写语义哈希、前端草稿只写 intent_path）。
- **验收（全部真实运行）**：① 塞 U9 电阻不重签 → FAIL（正是原缺口，现被拦）；② 换料 U3 value 不重签 → FAIL；③ 只重指绑定/电路不变 → PASS；④ 只改 `protocol_version` 元数据 → PASS；⑤ `tests.test_requirements_contract` **31/31**（新增 13 个语义绑定用例）；⑥ 全量回归 **114/114 OK**（零回归）；⑦ `run_gates.py` 10 门禁：**9 PASS + board_review FAIL**（仍仅为 `manufacturing_release=false` 等人工重签，与接手时语义一致）。
- ⚠️ **留给 P1 的连带缺口（本会话领地外，未改动）**：`gates/requirements_runtime_server.py` 的 `finalize`（L128-136）只写 `contract_sha256`，**没有写 `intent_semantic_sha256`**。已实测：经它 finalize 的合同送 C4 会被拒（`intent_binding must contain exactly intent_path, intent_semantic_sha256` + `malformed`）。修法：在写自哈希前 `binding["intent_semantic_sha256"] = intent_semantic_sha256(json.loads(intent_path.read_text(...)))`。该文件属 P1 领地，本会话只记录不动手。
- 遗留（非阻塞）：run_gates/export 在本会话环境里被 WorkBuddy 的 sitecustomize safe-delete 钩子拦截 `unlink`/`rmtree`（回收站不可用），需用 `python -S` 运行或人工在正常终端跑；这不是仓库代码问题。

### TASK-P7：finalize 语义哈希缺口修复 + runtime server 测试补强 ✅ done（AI-20260831-012/013/014，待人工审）

- 属主：ZCode 主会话。缺口实为 P1 后段已修，实测验收 + 31 新测试 + 400 JSON 修复 + RecordedProvider 回放（AI-018）。任务书全文（领地/待办池/验收标准）：`docs/OVERNIGHT_20260901.md` TASK-P7 卡。

### TASK-P8：开源 Intake Phase 4（NeuroBoard）+ 遗留定案 ✅ done（AI-20260831-015，待人工审）

- 属主：Qoder（通宵 P8 会话，研究路，领地 `notes/open_source_intake/`）。任务书：`docs/OVERNIGHT_20260901.md` TASK-P8 卡（含进度日志）。
- 完成内容：① `neuroboard.md` 六步 intake（克隆 `_neuroboard_repo/` @ `d8e3248`；License 双声明矛盾 → 零代码复用判决；11 门禁能力对照表）；② kicad-ai(amcolex) GitHub API 五层取证定案"公开仓库无存在证据"（`kicadai.md` 补记）；③ Konnect license 双来源核实 + README 商业条款原文摘录（`THIRD_PARTY.md` §2.4，红线不变）；④ README 目录/附属同步。
- 待人工审：三份取证结论；`.gitignore` 补 `_neuroboard_repo/` 排除（本次未越界改）；台账撞号说明（见 `docs/OVERNIGHT_20260901.md` P8 进度日志）。

### TASK-P9：board_review 特征化测试 + 可插拔协议预备 ✅ done（AI-20260831-016，待人工审）

- 属主：WorkBuddy（通宵 P9 会话，代码路）。任务书：`docs/OVERNIGHT_20260901.md` TASK-P9 卡（含进度日志与「P9 协议观察」小节）。
- 完成内容：① `tests/test_board_review_golden.py` **新建 51 用例全绿**（纯函数特征化 10 / `parse_pcb` 6 / 8 项 review 特征化 9 / golden 端到端 5 / 对抗与盲区 21）；② 夹具 `tests/fixtures/board_review/`（`minimal.kicad_pcb` 按 8 项判据反推摆放的 60×40mm 最小板 + `minimal.kicad_sch` + `golden_minimal.json` 冻结）；③ **1 处最小 bug 修复**：`parse_pcb` 新增 `vbus_caps`，`review_protection` 不再读全局 `PCB_PATH`（修复前传入"另一块板"的 parse 结果会**静默返回错误板子的 PROTECTION 结论**）；④ 协议观察小节（BoardReview 事实标准已成形；**RouteRepair 受门禁约束的实现数 = 0，按"≥2 实现才定形式"本轮不定协议**）。
- 关键取舍：golden **刻意打桩掉渲染**（真实 kicad-cli 存在但渲染 ~26s、PNG 字节不可复现会让 golden flaky），故 golden 无 `render_evidence` 且 `main()` 返回 1——渲染证据链另由 `tests/test_board_review.py::RenderEvidenceTests` 覆盖。**未**为规范化路径分隔符改生产代码（那会重写 `notes/m2-evidence-reset/` 已冻结证据），改在测试 `stable()` 里归一化。
- 锁定但未修（待人工拍板）：4 处现状怪癖（① `edge_distance` 越界返回负值；② `boundary_distance` 在无 courtyard/旋转件时静默退化为质心距；③ `review_exit_code([])` 空表返回 1；④ `courtyard` 是 tuple）+ 1 处盲区（`review_decoupling` 按关键字选 IC，U3 改成实际封装 **SC-70-5** 后**静默消失**而总判定仍 pass）。
- 验证：`tests.test_board_review_golden` 51/51；全量回归 **206/206 OK**（零回归）；bug 修复后真实 M2 板 PROTECTION 与已冻结证据**逐字节一致**；`run_gates.py` board_review 仍 `manufacturing_release is false`（接手前既有，非本次改动）。
- 待人工审：① 该 bug 修复；② 51 条断言是否真反映"想要的现状"（怪癖与盲区目前是**锁定**而非认可）；③ RouteRepair 是否同意"实现数 0 → 本轮不定协议"；④ golden 刻意缺 `render_evidence` 是否可接受。
- 领号说明：开工领 012，后发现并行会话撞号（013/014/015 亦被占），按任务书「撞号再 +1」改用 **016**，映射已记入任务书 P9 进度日志。

## 4. 大统领的职责（只有你能做的）

- 审 M2 的 89 文件 + 重签 board_review + commit/push 授权（不变，仍是第一优先）
- 审 P1 产物（合同 + 测试）后批准 P4 挂载
- 多 AI 的成果统一由你审核提交（保持单一 commit 权限，历史干净）

### TASK-P12-A：USB courtyard 任意边越界 FAIL（问题1）🔨 待领

- 属主：待领。难度：中。领地（可写）：`tools/board_review.py`（仅 USB_EDGE 评审函数，约 220–224 行一带）、`tests/test_board_review.py`（追加自己的用例）、`docs/compliance/AI_USAGE_LOG.md`（自己条目）、本卡状态行。
- 背景：`review_usb_edge`（或对应评审函数）只算 courtyard 前沿到板框上边的 Y 距离，不查 X 方向/其他边。已复现：板框 0..60 × 0..40，J1 x=-5、y=0.5、courtyard=(-1,-0.4,1,0.4)，仍 PASS。
- 任务：带 courtyard 的 USB 连接器从**任意一边**（左/右/上/下）越出板框都必须 FAIL；只算"在板框内的距离"当 courtyard 全在板内时才成立，越界（任何方向出框）直接 FAIL。
- 验收：四边参数化回归测试（至少左/右各一 + 既有上边用例保持）；修复后 `py -3 -m unittest tests.test_board_review` 全绿；不破坏既有 PASS 用例。
- **协调（必读）**：`tools/board_review.py` 同时有 P12-B 在改天线函数、P12-C 在改报告生成处（只加 `algorithm_revision` 字段）。只动自己的函数体；开工前 `git status` 看现场；**不要重新生成 `board_review_auto.json`（P12-C 专属）**；不 commit 不 push。
- 禁止：改 `gates/`、改几何算法之外的评审逻辑、设置 manufacturing_release、reset/checkout。

### TASK-P12-B：U1 天线模块板外 FAIL（问题2）🔨 待领

- 属主：待领。难度：中。领地（可写）：`tools/board_review.py`（仅 `review_antenna` 及其 edge 距离辅助，约 249、274–276 行一带）、`tests/test_board_review.py`（追加自己的用例）、`docs/compliance/AI_USAGE_LOG.md`（自己条目）、本卡状态行。
- 背景：`edge_distance` 在板外返回负数，但 `review_antenna` 未先检查模块是否在板内。已复现：U1 x=12、y=-1、rot=0 → edge_distance=-1.0，总判定 PASS。
- 任务：`review_antenna` 先判定模块 courtyard/主体在板框内，任意一边越界即 FAIL（负距离/出框都算越界）。
- 验收：四边参数化测试（x<0、x>宽、y<0、y>高 至少各一，或等价参数化）；**保留现有 rot=0/180 朝向测试不动**；修复后 `py -3 -m unittest tests.test_board_review` 全绿。
- **协调（必读）**：同 P12-A（同文件不同函数；不要重新生成 auto 报告；不 commit 不 push）。
- 禁止：同 P12-A。

## 5. 当前活动任务（Wave 4，2026-09-01 发卡）

- **COLLAB-BASELINE**：两人协作入口 → GitHub Issue #1 / Draft PR #6；分支 `codex/collaboration-onboarding`；已请求 `la4876949-bot` Review，状态 `PENDING_HUMAN_REVIEW`。
- **TASK-W4A**：EDD-001 证据冻结 + POWER 合同草案 → GitHub Issue #2；**Owner：`Yenefa`**（2026-09-02 指派；碰撞 1 已交付：六份 provenance 元数据冻结 + POWER DRAFT，`PENDING_HUMAN_REVIEW`；难度★★）。
- **TASK-W4B**：kicad-happy 六步 intake + 吸收方案 → GitHub Issue #3；Owner `la4876949-bot`，贡献分类 `AEDL_TEAM`（难度★★★）。六步完成，见 `notes/open_source_intake/kicad-happy.md`；交付 PR #14，`PENDING_HUMAN_REVIEW`。
- **TASK-W4C**：U3 ECO 准备 + 治理杂项 → GitHub Issue #4；旧文档属主为 ZCode 主会话，GitHub 真人 Owner `TO_ASSIGN`。
- **SANDBOX-V3**：外部信任锚 + orchestrator 注入闭环 → GitHub Issue #5；与 Wave 4 硬件任务独立领取。
- 任务书全文（领地/待办/验收/禁止）：`docs/WAVE4_TASKS_20260901.md`
