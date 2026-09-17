# HANDOFF — project-027-autonomous-hardware-agent

> **AI 接手强制前置**：在任何实质修改前，完整阅读根目录 `AGENTS.md`（v1.4，含 2.1
> 硬件发布前必读 `docs/knowledge/` 两份文档）；该文件是 AEDL 当前 Agent 执行层唯一规范。
> 本 HANDOFF 提供项目状态与硬件证据边界；`docs/compliance/AEDL_开发记录与AI使用规范_v1.0.md`
> 仅保留为历史基线与格式参考。
>
> **接手惯例（2026-08-30 起生效；2026-09-09 调整入口）**：开工时先读
> `docs/compliance/AI_USAGE_SUMMARY.md`（按工作单元聚合，快速看清前任/并行会话做了什么），
> 需要精确定位时再按 ID 读 `docs/compliance/ai-usage/<ID>.md`——git 作者统一为用户身份，
> 提交信息里的 `[AI-...]` 标签只有台账能解码到具体会话；据此识别工作边界、未审改动和已知坑，
> 避免并发写坏工作区。人类职责与决策边界见 `docs/HUMAN_OWNERSHIP.md`。
> 收尾时按 AGENTS.md 第 4 节为本次实质工作新增一条记录，默认 `PENDING_HUMAN_REVIEW`。

## 项目状态卡（2026-09-01，AI-20260901-006 README + 双仓库治理批次）

- Git/GitHub：private 正式仓库为 `https://github.com/Yenefa/AEDL`；本地 `origin` 已改为正式地址。协作冻结点为 `fix/m2-schematic-semantic-release` @ `e7ff3c1`，当时与同名 origin `0/0`；默认 `master` 当时落后 44 个提交，尚未合并。
- 当前治理：GitHub Issue #1 / Draft PR #6，任务分支 `codex/collaboration-onboarding`，已请求正式团队成员 `la4876949-bot` Review；AI 不 merge。Issue/PR 模板只有合入默认 `master` 后才会在 GitHub 新建界面自动生效，之前仅作手工规范。
- 双仓库：`Yenefa/AEDL` 是集成与技术主张真源；当前 private 的 `Yenefa/AEDL-spike` 是实验/过程 Evidence 卫星。卫星治理为 Issue #1 / Draft PR #2，分支 `codex/spike-governance` @ `0e562e5`，同样请求 `la4876949-bot` Review。回流必须引用 exact spike commit/path 并经主仓 PR 复验，见 ADR-010 与 `docs/COLLABORATION.md` §0.7。
- README：提交 `d1c625a` 已移除“门禁全绿、`manufacturing_release=true`、已授权下单”等过期现状叙述；稳定入口改为指向本状态卡、Evidence Index 和结构化门禁真源。该文档治理没有重写硬件或原始 Evidence。
- 后续任务：W4B Issue #3 已指派给第二名真人协作者 `la4876949-bot`；W4A Issue #2、W4C Issue #4、Sandbox V3 Issue #5 仍为 `TO_ASSIGN`。
- 协作者边界：项目负责人已确认 `la4876949-bot` 是第二名真人协作者，贡献分类为 `AEDL_TEAM`（正式团队成员）；当前尚未发生可登记贡献，成员身份本身不写入 `TEAM_CONTRIBUTIONS.md`。另有一条 `invitee=null` 的未过期 write 邀请，接收人 `UNKNOWN`。
- 软件基线（2026-09-01 顺序实测）：Sandbox 272/272 OK（1 skip、1 expectedFailure）；主仓库 269/269 OK。该结果不是实体硬件验证。
- 真实 EDD-001 preflight：`BLOCKED` / 7 findings，缺本地器件资料、`EDD-001.POWER`、compiler registration 与 independent verifier coverage；保持失败关闭。
- 板子：M2 ESP32-C3+SHT30；D1 极性已修、U3 当前仍为 C235316。既有记录为 board_review `manufacturing_release=false`、datasheet_contract 32 项待人工签发；本治理批次未重跑会改写 Evidence 的完整 gate runner，也未执行制造签发。
- **M2 物理线冻结（2026-09-01 人工裁决）**：不再下单/重签/换料；U3（ME6211C33R5G）挂账封存，datasheet_contract 的 M2 阻断记录为已知冻结状态；M2 的验证机制（门禁链/契约/教训库）继续作为 Sandbox 地基保留。
- 北极星：正确交付实体板卡（M2 教训 → sandbox 手段 → EDD-001 兑现板）；叙事锚点见 Issue #15。
- 人工队列：Review/merge Issue #1 的 Draft PR；裁决 U3 路线；datasheet 签发、board_review 重签、下单与实体 C 级验证继续独立保留。
- 检索入口：`docs/ID_MAP.md`；协作规范：`docs/COLLABORATION.md`；Wave 4：`docs/WAVE4_TASKS_20260901.md`；RAG 取舍：`docs/knowledge/RAG_DECISION.md`。

## 归档：并行会话历史（截至 2026-08-31）

> 历史会话记录，仅审计用，现状以上方状态卡为准。各小节原文保留、一个字未删。

## 并行会话状态（多 AI 协作，配套 `docs/COLLABORATION.md`）

> 各会话只追加自己的小节，不改他人小节。领地规则见 COLLABORATION.md。

### P3-INTAKE（AI-20260831-004，2026-08-31）
- 做了什么：领取 TASK-P3，完成 KiCadAI（dshills）与 KiCad MCP（mixelpixx 深审 + 家族调研）六步 intake；关键产出：碰撞分析"KiCadAI 生成链路未见源码"经本地克隆复核判为误判（writer/ERC-DRC/MNA 仿真源码俱在，校准对照在 kicadai.md 附节）；发现 KiCad MCP 后继项目 Konnect 为 AGPL-3.0（AEDL 禁吸收，已写红线）；kicad-ai(amcolex) 本轮 WebFetch 得 GitHub 404 渲染页，"从未存在"仍待人工浏览器定案。
- 文件清单：`notes/open_source_intake/kicadai.md`（新）、`notes/open_source_intake/kicad-mcp.md`（新）、`notes/open_source_intake/README.md`（目录状态更新）、`notes/open_source_intake/_kicadai_repo/`+`_kicad_mcp_repo/`（浅克隆审查证据，含 .git 勿提交）、`docs/COLLABORATION.md`（TASK-P3 标 done）、`docs/compliance/AI_USAGE_LOG.md`（AI-20260831-004）。
- 下一步：待人工审两份报告 + 碰撞分析校准是否回写 + 两个克隆目录是否入 .gitignore；近期可落地建议（KiCadAI RecordedProvider 回放模式用于 LLM 层测试、FTS5 连字符 MPN 教训转 AEDL 器件匹配对抗 fixture）待排期；Phase 4 NeuroBoard intake 未开始。
- （P3 会话观察，未代改他人章节）开工 `git status` 显示当前分支为 `fix/m2-schematic-semantic-release`，与下文"Git / GitHub"节"本地分支：master"记述不一致，留待人工核对历史。

### P2-FRONTEND（AI-20260831-003，2026-08-31）
- 做了什么：领取 TASK-P2（领卡时状态"可立即领取"、属主空缺、`web/` 尚不存在、`docs/HANDOFF.md` 无人认领 → 满足前置条件，未走备选 TASK-P3），完成 `web/` 需求澄清工作台——零构建静态单页（普通 `<script>` 而非 ES module：`file://` 下 module 会被 CORS 拦）。契约「前端必须遵守的语义」四条全部落地：blocking 未答则禁用生成并显示"还剩 N 个必答问题"；必须显式作答（`unknown`/`No preference` 有效，空答案永不许提交）；建议清单可增/删/改后才作答；`errors[]` 原样渲染不过滤不美化。自哈希归属服务端，mock 传输层用自实现的 canonical-JSON + SHA-256 复刻 Python 算法并**与真实门禁交叉验证通过**。发现并记录契约与 `requirements_contract.py` C4 的 `intent_binding` 冲突（合同组装的唯一阻塞项），未自行猜测定义。
- 文件清单：`web/` 全部新增（`index.html`、`styles.css`、`app.js`、`api-client.js`、`contract-builder.js`、`mock-data.js`、`canonical-json.js`、`sha256.js`、`verify-hash.js`、`smoke-test.js`、`e2e-browser.js`、`README.md`）；`docs/COLLABORATION.md`（TASK-P2 标 done + 改动清单/实现说明/7 条遗留问题）；`docs/compliance/AI_USAGE_LOG.md`（AI-20260831-003）；本文件（本节）。未越界改他人领地文件。**未 commit**（项目负责人指令）。
- 下一步：① **等 P1 定案 `intent_binding` 冲突**（契约文档要 `intent_path` + `intent_sha256`，C4 只收 `intent_path`），定案后前端需同步改 `web/contract-builder.js`；② 其余 6 条契约缺口（propose/finalize/validate 请求体形状、answer 返回结构、错误码、浏览器如何取得合同路径）待 P1 补；③ `gates/requirements_runtime_server.py` 起来后需真机联调真实 API 模式（当前必然连不上，已标 NOT_RUN）。
- （P2 会话观察，未代改他人章节）同 P3 观察：当前分支确为 `fix/m2-schematic-semantic-release`。

### P5-SEMANTIC-BINDING（AI-20260831-006，2026-08-31）
- 做了什么：大统领直接指派 C 方案，堵"改电路不重签合同"缺口（已实测：塞 U9 电阻 + 保留旧合同引用，原 lockfile 单向绑定下 gate 仍 PASS）。实现 `INTENT_SEMANTIC_FIELDS = ("components", "nets")` 白名单（写死在代码注释 + 双向维护约定）与 `intent_semantic_sha256()`（canonical JSON sha256，缺失字段按 null 不跳过）；`intent_binding` 扩为恰好 `{intent_path, intent_semantic_sha256}`（旧形状被拒，fail-closed）；C4 新增语义锁——不一致报 `intent 语义内容已变更，须重签合同`。**未引入双向哈希**：语义哈希只依赖 intent 的 components/nets，绑定字段本身明确排除（否则重新成环）。M2 已重签（语义哈希 `be8b649c…`，自哈希 `82c136df…`→`f0fec3f8…`）；`draft_contract` 新增必填参数 `intent_semantic_sha256`。
- 文件清单：`gates/requirements_contract.py`、`gates/requirements_runtime.py`、`gates/requirements/requirements_contract_v1.json`（M2 重签）、`tests/test_requirements_contract.py`（31 用例）、`docs/api/requirements_api.md`（新增语义哈希章节）——以上均在本任务领地；**跨领地**：`src/hardware/m2-board/intent_v1.json`（单行：lockfile 引用重指新哈希，验收"gate 仍 PASS"的必然级联）、`delivery/`（export_delivery.py 重导，manifest 4 source 哈希复核一致）、P2 领地 `web/index.html`+`web/README.md`（过期冲突提示改为语义哈希说明）；台账 `docs/COLLABORATION.md`（TASK-P5 卡）、`docs/compliance/AI_USAGE_LOG.md`（AI-20260831-006）、本节。**未 commit**。
- 验证：原缺口复现→堵住（塞 U9/换料 U3/删器件/改 nets 不重签均 FAIL）；只重指绑定或只改 protocol_version 仍 PASS；`tests.test_requirements_contract` 31/31；全量回归 114/114；`run_gates.py` 10 门禁 9 PASS + board_review FAIL（仍仅为 manufacturing_release=false，语义与接手时一致）；web 三项验证重跑全过。
- 下一步：① **P1 领地连带缺口（最重要）**：`gates/requirements_runtime_server.py::finalize`（L128-136）只写 `contract_sha256` 不写 `intent_semantic_sha256`，已实测其产物被 C4 拒收——修法写在 TASK-P5 卡片，交 P1；② 候选 ADR-007（语义哈希绑定）待人工审立项；③ MOCK 前端无法替服务端算语义哈希，该限制已在 web README + UI 明示；④ 本会话环境（WorkBuddy sitecustomize safe-delete 钩子）拦截 unlink/rmtree，run_gates/export 需 `python -S` 或人工终端运行，非仓库代码问题。
- （P6 会话观察，未代改他人章节）`web/` 的 4 个文件在 01:20 被本会话之外的并行会话同步过（intent_binding 已改 lockfile 单字段形状，与新 C4 语义恰好兼容），本会话只做了 index.html/README 的提示文案同步，未覆盖他人改动。

### RENDER-PROOF + TASK-FIX-D1 + DATASHEET-GATE（AI-20260831-007/008，Qoder 会话，2026-08-31）
- 做了什么：① 目检渲染证据门禁（kicad-cli 脚本化重渲 + `render_evidence` sha256 绑定 PCB，fail-closed）——渲染证据部分已提交 `4e0922a`，但提交信息误标 `[AI-20260831-001]` 与 P1 撞号，实际对应本条 007；② TASK-FIX-D1：D1 极性三层修复（intent/原理图/网标对调/PCB——PCB 因铜皮已物理连通，用 footprint 原地旋转 180° 使 pad1=K 落 GND 铜皮、pad2=A 落 LED_A 铜皮，走线零改动）+ 全链重导（ops 重放/需求合同重签 `82f8aa2f…`→自哈希 `a315effe…`/delivery 重导/网表/ERC/DRC/语义/故障注入/学习/重渲染），`polarity-verification.md` 升 rev2（采纳人工复核 4 处修正）；③ 外部证据包落地 + 第 11 门禁：`src/hardware/m2-board/evidence/`（manifest/contracts/3 份 datasheet PDF 冻结副本含 sha256：U1 Espressif 官方、U2 Sensirion 官方、U3 ME6211 V14 镜像），`gates/datasheet_contract.py`（DS0-DS6 fail-closed），当前如实报 34 项 BLOCK。
- 文件清单：`tools/board_review.py`、`gates/gate_core.py`、`gates/run_gates.py`、`gates/datasheet_contract.py`、`tools/generate_m2_ops.py`（lockfile 字段泄漏修复）、`tests/test_board_review.py`、`tests/test_run_gates.py`、`tests/test_datasheet_contract.py`、`src/hardware/m2-board/{intent_v1.json,m2_board.kicad_sch,m2_board.kicad_pcb}`、`src/hardware/m2-board/evidence/**`、`gates/requirements/requirements_contract_v1.json`、`notes/m2-evidence-reset/generated/*`、`delivery/*`、`notes/m2-evidence-reset/polarity-verification.md`、`docs/compliance/AI_USAGE_LOG.md`（007/008）、本节。D1 修复及门禁改动**未 commit**（任务书铁律）。
- 验证：123/123 单测全绿（114 既有 + 9 新增）；`run_gates.py` 原 9 门禁全 PASS、board_review 仅余 `manufacturing_release=false`、datasheet_contract 如实报 34 BLOCK；新导网表 `D1 pin1(K)→/GND、pin2(A)→/LED_A`；delivery `rows=21 zip_entries=11`。
- 下一步（交人工）：① 按 datasheet_contract 34 项 BLOCK 逐项取证，优先 D1（KT-0603R/C2286 datasheet，反向耐压未知）与 J1（TYPE-C-31-M-12/C165948 mechanical drawing）——本环境 LCSC 直链 TLS 拦截，需人工下载后放入 `evidence/datasheets/` 并更新 manifest sha256；② U3 电源：400mA@SOT353 声明仅有 V20 出处（本地只取到 V14，V14 无按封装电流表且 features 写 500mA@4.3V），两版冲突须按最终版 datasheet 定案；5V→3.3V 压差 1.7V×150mA≈255mW 已触 SOT-353 250mW absmax，热复核或换 ≥1A 级电源方案（正式选型流程）前保持 BLOCK；③ U1/U2 各项 check_evidence 需工程师对照 datasheet 签发后才能转绿。
- 补记（AI-20260831-010，同会话）：两份原件已补取冻结，上条①②的取证阻塞已消除大半——① ME6211 V20 原件经 LCSC 直链取到（上轮 TLS 拦截为瞬态），865046 B，sha256 23084e9d…fae5e6，逐页核对为真：p9『ME6211C33 (SOT343R, FBP1*1-4L, SOT353)』I_OUTMAX=400mA（同页标准封装表 500mA）、p5 SOT353 Pd=250mW，人工裁决获一手背书，合同 fact_verification 升级 verified_locally_from_frozen_original；② TYPE-C drawing 从 elecfans 镜像提取到原始 PDF，118108 B，sha256 ef0e00dd…0294b（16-pin/0.5mm pitch/20V/-30~+80C/280C 10s/PCB EDGE/RECOMMEND P.C.B LAYOUT），**但水印/标题栏为 HIROSE，与 BOM 制造商 Korean Hroparts Elec（HRO）不符**——疑似仿制厂文档或镜像站误标，已标 FROZEN_PROVENANCE_QUESTIONABLE，只作几何参考，签发须取得 HRO 官方图纸（此前预警的同名仿制风险在此具象化）。门禁重跑：DS1 清零，datasheet_contract 余 32 项，全部为待人工签发类别。

### AEDL-R1 渲染图新鲜度门禁——现状核实 + AECP 流程交付（AI-20260903-001，WorkBuddy Worker 会话，2026-09-03）
- 做了什么：领取 AEW 任务 AEDL-R1（TASK-R1）。开工核实发现：TASK-R1 领地内的全部实现（`tools/board_review.py` kicad-cli 渲染步骤 + `render_evidence` 写入、`gates/gate_core.py::validate_render_evidence` 四项 sha256 检查、`gates/run_gates.py::_evaluate_board_review` 挂载、`tests/test_board_review.py::RenderEvidenceTests` 6 用例）**已由上节 AI-20260831-007（Qoder）完成**并随 tarball 快照进入本地 master `5c1dff5`。按 COLLABORATION §0.3 撞车仲裁停手，不重做不覆盖，转为现状核实 + AECP 流程交付：生成 `tasks/AEDL-R1.yaml`（envelope，base.sha=5c1dff5，allow_dirty 预授权 granted_by=Yenefa）→ admit ADMIT → dev_gate 全 pass（exit 0，binding 用 admit 回执绑定 envelope+HEAD）→ Review Bundle 生成（`review-bundles/master/`，base=HEAD，changed 仅 2 个流程文件）→ 台账 AI-20260903-001。
- 验证（真实运行）：`unittest tests.test_board_review` 18/18（含 render_evidence 4 类失败用例）；全量 322/322 零回归；`gates/run_gates.py` 如实记录快照现状——board_review FAIL 列表含 `render_evidence pcb_sha256 does not match the current PCB (render images are stale)`，即门禁对"PCB 已变、图未重渲"的 fail-closed **实测命中**（快照 PCB 与 8-31 渲染证据天然失配，非篡改演练；ops/schematic 语义哈希漂移、datasheet 32 项待签、kicad-cli 缺失均为既有状态）；另以临时目录副本演练"手动改 PCB 不重渲 → 报 pcb_sha256 失配、新鲜证据 → 无 error"闭环，冻结证据零触碰。run_gates 的 4 个 `*_current.json` 运行副作用已还原。
- 已知限制 / 工具缺口（如实报告）：① 真实 kicad-cli 重渲与 `board_review.py` 端到端 NOT_RUN（本机无 KiCad）；② `tools/make_review_bundle.py` L326 的 origin/master 探测在无远端快照仓上抛异常，CLI 的"否则用 HEAD"回退不可达——本会话不改 FOREIGN 代码，直接以 base=HEAD 调 `build_bundle()` 走文档化回退生成 bundle，修法建议留给工具 Owner（`has_master` 探测改用 `git_ok` 式 rc 容错）；③ run name 取 `run_name_from_branch("master")`="master"，bundle 落 `review-bundles/master/`。
- 下一步（交人工）：① 审阅 `tasks/AEDL-R1.yaml` + admit/dev_gate/bundle 产物，确认 AEDL-R1 以"已实现+已验证"状态关闭；② 在有 KiCad 的机器跑 `py -3 tools\board_review.py` 重渲并刷新 render_evidence（当前快照证据对当前 PCB 是过期态，board_review 门禁会如实 FAIL 直到重渲）；③ `manufacturing_release` 重签与 datasheet 签发仍独立保留。
- 补记（同日，人工问询后复查）：① 自查发现首轮 dev_gate 回执跑在 HANDOFF 补写之前、事后改树未重新 admit——已重走 envelope 补授权（`docs/HANDOFF.md`，依据 COLLABORATION §2 追加型文件）→ 重 admit（ADMIT，envelope `54c372710b43…`）→ 重 gate，详见台账 AI-20260903-001 补记；② admit/gate 回执已按上批惯例拷入 `review-bundles/master/`（此前 bundle receipt 区为空）；③ 最终 gate scope_check 如实报 1 项 finding：`.aew/focus.json` 为 **AEW 决策层自有状态目录**（`aew/state.py` 文档化，主会话 23:03 并行写入，内容为"R1 已实现+已验证勿重派"），本会话未写、未删、未入 envelope，报大统领裁决（如收纳 .gitignore）。
- 补记二（同日，人工 Review "通过 + 3 必修"后执行）：① 必修#1 `.aew/` 隔离：`/.aew/` 入 `.gitignore`，独立 housekeeping commit **`a7b6a2c`**（人工批准的 repo 变更，非"顺手改"）；② 必修#3 envelope v3：allowed_paths 9 → **3**（least-privilege：仅 AI_USAGE_LOG / HANDOFF / envelope 本体；领地代码降为只读验证），change_budget 同步，base.sha 重锚 `a7b6a2c`；③ 必修#2 审计定性：历史回执代际以台账 AI-20260903-001 补记二为权威——首轮（envelope `bd4557…`，gate exit 0）与二轮（envelope `54c372…`，scope FAIL on `.aew/`）均 **SUPERSEDED**，v3 envelope 的 admit/gate 回执为唯一 **authoritative**（随 bundle 归档）；本小节此前叙述的"dev_gate 全 pass（exit 0）"指首轮 SUPERSEDED 代，读账时以补记二为准。

## 当前状态（2026-08-31，AI-20260831-002 会话末）

**一键门禁现为 10 gate**（新增 requirements_contract，见下）：9 PASS + board_review FAIL（仍仅为 `manufacturing_release=false` 等待人工重签，与 AI-20260830-002 交接时语义一致，零回归）。

### 本会话新增：Requirements Contract（Phase 1 CircuitBot 吸收落地，AI-20260831-002）

- `gates/requirements_contract.py`：第 10 门禁核心，C1-C7 确定性校验。**设计修正**：合同↔intent 双向哈希是循环依赖，改为 lockfile 式单向绑定（intent 持有 `{sha256, path}`）。
- `gates/requirements_runtime.py`：LLM 自动提问建议层（大统领指令），与合同层物理分离--`parse_llm_proposal` 把 LLM 输出降级为问题草案（answer 恒 null、垃圾输入变 warning、未知 kind 升 blocking），`draft_contract` 只组装不自造；gate 永不调 LLM。
- `gates/requirements/requirements_contract_v1.json`：M2 补录合同（决策 A，author 标注 retroactive），gate 校验 PASS。
- `src/hardware/m2-board/intent_v1.json`：新增 `requirements_contract` 引用字段；delivery manifest 已重导（哈希连锁）。
- 测试：`tests/test_requirements_contract.py` 18/18；全量 95/95；`tests/test_run_gates.py` gate 集合断言 9->10（预期变更）。
- 已知盲区：C6 关键字匹配对间接载体（如 ESP32 内置 Wi-Fi）依赖 carrier 词条，无法穷举，代码注释与 intake 报告已披露。
- 多 AI 协作：`docs/COLLABORATION.md`（领地划分+任务卡，P2 前端/P3 intake 可领取）+ `docs/api/requirements_api.md`（P2 接口契约+mock）。
- 全部待人工审（PENDING_HUMAN_REVIEW）：单向绑定方案、补录合同内容、第 10 门禁挂载、协作协议。

### M2 主线（沿 2026-08-30 末状态）

M2 板级语义修复 + U3 换料完成（**换料方案已经项目负责人 2026-08-30 人工审核采纳**）：
原 U3 LDO（C82942，ME6211C33M5G-N，SOT-23-5）嘉立创装配库存 2026-08-30 实时查询归零
→ 触发失败关闭 → 换料为同厂同系列 **C235316（ME6211C33R5G，SOT-353/SC-70-5，装配库存
3329）**，datasheet V20 核实 pin1=VIN/pin2=GND/pin3=CE/pin5=VOUT 引脚序与 SOT-23-5
完全兼容。intent/BOM/原理图/PCB footprint/逃逸布线全链同步，KiCad 官方库几何逐字替换。
审核过程沉淀 ADR-005（θJA 结温法、结论精度、主张纪律、数据手册版本交叉核对）。

一键门禁（9 gate）当前 **8/9 PASS，exit 1**——唯一 fail 是 `board_review`：
`manufacturing_release=false`（2026-08-29 因 USB D+/D- 接反等语义缺陷被撤签，
incident PIT-20260830-001，`human_resign_required=true`）。机器证据 8/8 全部重新
实测通过；**等待项目负责人人工重签后才能下单**。这是诚实终态，不是回归。

| 门禁 | 结果 | 事实 |
| --- | --- | --- |
| erc | PASS | KiCad 10.0.5 ERC 0 error |
| drc | PASS | 0 violation / 0 unconnected（U3 换封装重布逃逸线后保持） |
| bom | PASS | 21 物理料位；14 个 LCSC 码实时正库存（C235316=3329）；哈希绑定快照 |
| delivery | PASS | BOM/CPL 21 行一致；Gerber ZIP 11 条目；manifest_v1 哈希绑定全部源与产物 |
| intent | PASS | 21 物理组件 + 2 PWR_FLAG 虚拟件 |
| ops | PASS | akcli 0.21.0 已恢复；ops_gen.json 由 intent 重放生成，109 op，SHA-256 绑定 |
| schematic_semantics | PASS | 独立数据手册语义契约（USB 极性/SHT30 ADDR/EN RC 等修复后验证） |
| learning | PASS | 教训登记表可执行检查（含"零库存失败关闭不自动换料"教训） |
| board_review | **FAIL** | 机器实测 8/8 pass，但 `manufacturing_release=false` 等待人工重签 |

板级评审实测要点（换料后新值）：J1 courtyard 距板边 0.03mm；U1 天线净空 7.5mm 无器件；
去耦最差 U3→C1 3.4mm（SOT-353 courtyard 更小，由 2.8mm 改善）；USB 差分 skew 0.95mm；
SHT30 距最近热源 35.2mm；丝印 21/21；方向敏感件 J1/U1/U2/U3/D1。证据：
`notes/m2-evidence-reset/generated/board_review_auto.json`。

## Git / GitHub

- 本地分支：`master`；已提交 HEAD `24b542e`（AI-20260830-001 语义修复系列末位）。
- 本会话（AI-20260830-002，U3 换料 + 收尾）改动**未提交**，等待人工审核。
- 私有远端：`https://github.com/sca331613-commits/AEDL`，`origin` 已绑定并推送到 `a3a51c6`；
  本地领先远端 8 个提交（AI-20260830-001 系列）+ 本会话未提交改动，均未 push。
- 项目尚无 LICENSE，RES-001/RES-003 再分发权 `TO_VERIFY`，4 个已跟踪文件含本机用户路径；
  完成许可证、路径脱敏和公开内容审计前不得改为 public。

## 2026-08-30 U3 换料记录（C82942 → C235316）

1. `refresh_bom_stock.py` 失败关闭拦截零库存（当日库存 5 → 0）。
2. datasheet V20 核实 SOT-353 引脚序与 SOT-23-5 逐脚一致；电气同规格（3.3V/300mA LDO）。
3. `intent_v1.json` / `gates/bom/bom_v1.json` / 原理图 / PCB footprint 同步换料；
   footprint 用 KiCad 官方 `SOT-353_SC-70-5` 几何逐字替换（pad 由 ±1.1375/1.325×0.6
   改 ±0.8375/1.025×0.35）。
4. 逃逸布线重布：+5V 环走廊右移至 x=54.02（pad2 与 pad4/5 之间 0.65mm 走廊，双侧净距
   0.225mm）；+3V3 改垂直落到新 pad5；删除旧 pad3 孤立残段；DRC 收敛回 0/0。
5. `tools/board_review.py` 检测盲区修复：热源/极性/去耦三处 lib_id 关键字补 `SOT-353`
   （否则换封装后 U3 从三项检查中静默消失——变相放水，已禁止）。
6. ops 用 `tools/generate_m2_ops.py`（akcli 0.21.0 已恢复）从新 intent 正规重放；
   delivery 用 `gates/export_delivery.py` 重新导出并哈希绑定。
7. 换料方案人工审核：初审 CONDITIONAL APPROVE（三项方法论整改：热分析改用 θJA 结温法、
   确认 SOT-23-5 热基线、降级过强主张）→ 整改后采纳；发现 V20/V24 数据手册版本热额定
   差异（SOT353 PD 250mW vs 450mW，TO_VERIFY）。经验沉淀为 ADR-005 +
   `docs/knowledge/IMPROVEMENT_SYSTEM.md` 方法论教训条目。

## （归档区结束）以下为仍然生效的长期条目

## 关键文件

- `AGENTS.md`：AEDL v1.4 唯一执行规范；2.1 节硬件发布前必读 `docs/knowledge/`。
- `gates/gate_core.py`：结构化证据失败关闭（含 BOM 新鲜度/库存证据/交付 manifest 校验）。
- `gates/run_gates.py`：一键 9 gate runner，生成 `notes/m2-evidence-reset/run_manifest.json`。
- `gates/bom/bom_v1.json`：唯一 BOM 真源（21 料位 + 实时库存快照字段）。
- `gates/refresh_bom_stock.py`：LCSC 精确码实时库存刷新，零库存失败关闭。
- `gates/export_delivery.py`：Gerber/CPL/BOM/manifest 全套哈希绑定导出。
- `gates/board_review_v1.json`：8 项评审记录；当前 `manufacturing_release=false` 待人工重签。
- `tools/board_review.py`：8 项评审机器实测（含 SOT-353 关键字）。
- `tools/generate_m2_ops.py`：akcli 0.21.0 ops 正规重放（含 PWR_FLAG 受控兼容注入）。
- `gates/schematic_semantics.py` + `gates/contracts/m2_schematic_contract_v1.json`：独立
  数据手册语义契约验证（AI-20260830-001 建立）。
- `gates/learning_gate.py` + `gates/lessons_registry_v1.json`：可执行教训登记表。
- `docs/M2板级工程评审.md`：8 项评审、DRC 收敛与证据边界。
- `notes/m2-semantic-repair/`：语义修复渐进证据链（重建原理图 ERC/路由前后 DRC）。

## 下一步验收顺序

0. **开源吸收 Phase 1 产物待审（AI-20260831-001，2026-08-31）**：
   - `notes/open_source_intake/circuitbot.md`：CircuitBot 六步 Intake 完成。核心证据：
     clarify 为 fail-open（5 分钟超时继续、No preference 静默丢弃、结果仅存 state、
     零测试覆盖）--策略文档"吸收后重新设计"的直接依据。
   - `notes/open_source_intake/requirements_contract_design_v1.md`：Requirements Contract
     设计稿（schema + C1-C7 七项 gate 检查 + 8 fixture 测试计划）。**未实装**，含 4 个
     待人工拍板决策点（M2 追溯 A/B、过期阈值、forbidden 匹配方式、实装时机）。
   - `notes/open_source_intake/_circuitbot_repo/`：CircuitBot 本地克隆（ff9b003，MIT），
     提交前需决定是否入 AEDL git（建议 .gitignore 排除，见 intake README）。
   - 实装前置：M2 的 89 文件收尾完成后才动代码（避免 diff 混杂）。
1. **人工重签 board_review**：项目负责人复核 `board_review_v1.json` + `board_review_auto.json`
   + KiCad 渲染目检（J1/U1/U2/U3/D1 方向极性）后设置 `manufacturing_release=true`；
   重签前不得下单。
2. 嘉立创下单：`delivery/jlc_gerber_upload.zip` + `bom.csv` + `pos.csv`（21 行，U3 已换
   C235316）；下单前如隔日需重跑 `refresh_bom_stock.py`（库存易变）。
3. 回件后 C 级实测：上电、功耗、BLE 距离、温湿度精度、USB 眼图、瞬态、24/168h 稳定性、
   **持续 WiFi 负载下 U3 温升**（ADR-005 新增，同时裁决 V20/V24 热额定差异）；结果回写
   `gates/board_review_v1.json` 实物验证备注。固件注意：U3 避免持续 >147mA 负载
   （V20 保守边界；目标场景周期采集余量充足）。
4. P2：spike_stage2 验证协议执行器整合进 AEDL（native 3/3 + Wokwi 3/3，4 类故障注入
   全检出；当前是"预设候选池受限修复"，非 LLM 自主修复）——`spike/`、`spike_stage2/`
   未提交，作为独立素材单独提交。
5. P3：可插拔协议抽取——先给 `tools/board_review.py` 补 characterization/golden tests，
   再固化 BoardReview 与 RouteRepair 协议；≥2 个真实实现后才定插件加载形式，禁止先造空框架。

## 约束与边界

- 任何 AI 的实质贡献都必须写入 `docs/compliance/AI_USAGE_LOG.md`；AI 不得自行标记
  人工审核通过，不得设置 `manufacturing_release=true` / `HUMAN_REVIEWED` / `ACCEPTED`。
- 禁止把 Wokwi/host 单测/DRC 0 描述成实体硬件验证；C 级实测回件前不得宣称"板子能工作"。
- 8 项评审结论基于机器几何实测 + DRC 0 违规；朝向/阻抗/气流/瞬态的实物复核待回件。
- 禁止把当前板描述成已经完成的通用自主硬件 Agent；本轮只验证一块 ESP32-C3/SHT30 载板
  和门禁闭环。
- BOM 库存按精确料号即时复核；零库存/未知库存失败关闭且不得自动换料（换料必须重走
  datasheet 审查 + 全链同步 + 人工审核，如本次 AI-20260830-002）。
- 替代料热验证一律 θJA 结温法（Tj = Ta + ΔV×I×θJA，分档核算），禁止 PD÷压差冒充热限、
  推测输入产出精确结论、无证据的排他性主张；数据手册版本差异须交叉核对（ADR-005）。
- 下单动作由项目负责人执行。

## 环境关键事实（前人踩过的坑）

- KiCad 10.0.5：pcbnew Python 必须用 KiCad 自带 python.exe
  （`C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\bin\python.exe`）；
  `PCB_VIA.GetWidth()` 无 layer 参数会 assert 崩溃。
- freerouting 2.3.0（`tools\bin\`）：必须 `-mt 1`（多线程产生违规）；遥测拖死进程需
  代理拦截参数（完整命令见 `docs/M2测试报告.md` 第五节）。
- PowerShell 无 heredoc，git commit 用 `-F msgfile.txt` 方式。
- akcli 0.21.0 位于
  `C:\Users\fuker\AppData\Local\hermes\hermes-agent\venv\Scripts\akcli.exe`（已恢复可用）。
- （2026-08-31 大统领批准清理）调试产物已删除：`m2_board_rerun.ses`、`tools/polish_routes.py`、
  `tools/probe_pads.py`（freerouting_run2/3.log、g4_drc_probe.json 此前已不存在）。
- （P3 会话补，2026-08-31）GitHub 克隆 KiCadAI 这类深路径仓库在 Windows 检出会因路径
  长度失败（exit 128），需 `git clone -c core.longpaths=true`。
- （2026-09-03，人工指令，优先级依据 AGENTS.md §0 第 1 条：人类明确指令 > 规范默认值）
  Review Bundle 收藏位迁到桌面：`C:\Users\Ryan Gosling\Desktop\Bundle-Lap\`（一 run 一子夹
  + `INDEX.md` 索引），因默认位 `<repo 父目录>\review-bundles\<run>\` 埋在 WorkBuddy 深路径
  不便人工查阅。**权威生成位不变**（仍是 CONTROL_PLANE §8 的仓库外 `review-bundles/`，
  不进 git，.patch 基线可回溯）；收藏位收审查用副本。会话收尾惯例：生成 → 拷一份到
  Bundle-Lap → INDEX.md 加一行。

## 2026-09-08 PR-1 C2 候选交接（AI-20260908-002）

- 当前：`feat/pr1-c2-repair-verification` 基于 `master@c34cd0d`，完成 C2 的完整源观察、精确拓扑差分和保护比较；16 文件预算内，无硬件/固件修改，未 commit/push，新 PR 未创建，`PENDING_HUMAN_REVIEW`。
- 验证：C2 在 Python 3.9/3.13 各 49 OK；主项目 375 OK；learning PASS；C1 `6cd76c1` 合同 92 OK、摘要兼容 74 PASS。完整 dev_gate 仍 FAIL：原有 Windows junction 测试在 `test_paths.py:41` 报 WinError 183，修改前基线和独立复跑均一致。无 task envelope，scope/binding 门禁未运行；不能写成全绿。
- 下一步：先复审本候选，并与仍 OPEN 的 C1 PR #48 集成 hash 单一来源；按冻结合同进入 C3，两次 fresh KiCad export 绑定源字节、完整 XML/source/native coverage 与依赖清单。C4/C5/C6 继续按依赖顺序实现，纯比较 PASS 不授予执行/提交/promotion 权限。当前 KiCad 20231120 flat M2 以外的几何/层级返回 UNKNOWN；未执行新的 native/KiCad 全链或实体测试。另，EDD-001 preflight 仍有 8 项前置缺口，详见本次 AI log 和仓库外审查报告。

## 2026-09-08 PR-1 C2 候选交接（AI-20260908-002/003）

- **C2 已落地**：`gates/repair_verification.py`（完整观察/exact delta/protected 投影/域分离 hash
  单一归属地）+ `tests/test_repair_verification.py`（56 用例）+ 12 个规定夹具（fixture 字节经
  `.gitattributes -text` 冻结）+ `tools/repair_pipeline.py` 的 hash import 收口（C1 集成完成）。
- **大统领源码级审查（REQUEST_CHANGES）三项全部落地**：new-UUID 角色契约在 `_prepare` 强制
  （new:<ref>.<pin> / new:label:<slot> 密集 slot，篡改样本 PASS→FAIL）；C1 hash 收口；
  envelope `tasks/W1-C2.yaml` + admission 链补齐。
- 验证：repair_verification 56/56（3.9/3.13）、repair_contract 92/92、全量 474/474 OK。
- 状态：`PENDING_HUMAN_REVIEW`（PR 送审中）。C3（fresh KiCad export）待 C2 合并后另卡。

## 2026-09-17 PR-1 C4 候选交接（AI-20260917-DSH-525A0E8BBDFDEFA274AA1A6CA95F43EE）

### C4 pinned strict and constrained writer adapter（分支 feat-pr1-c4-akcli-adapter，base 0d31a8b）

- 落地：合同 §11 C4 的 §8 三入口——read_native（闭合校验 + 宿主只读授权 + 声明根内解析 + 固定 worker 经 akcli.readers 收集完整原生观察并 normalize）、apply_stage（HostPatch 自校验、route 与 ROUTE_BY_RULE 冻结一致、双 ALLOW 凭据、toolchain 重算、op-list 与绑定 proposal 一致）、worker_main（固定 READ / APPLY_EXCEPTION）。
- STRICT：单次精确 argv、shell=false；exit=6 合法拒绝对象 → BLOCKED / REPAIR_STRICT_REFUSED 且不自动改走 exception；applied 缺失/false/伪造 true → 绝不 APPLIED_TO_STAGE；回执必须逐一覆盖 0..n-1 且全 ok、字节真改变并成功重读。
- CONSTRAINED_EXCEPTION：固定 Python worker 调 akcli.writers.kicad.apply(...)；API 无 applied 字段 → tool_applied 强制 null。
- 连通性：ERROR/CRITICAL、新增 WARNING、任何 NO_CONNECT_CONFLICT 阻断；未知 severity → UNKNOWN（不降为 INFO；akcli 的 NOTE 显式映射为 INFO 并保留 raw_severity）。
- 测试：tests/test_akcli_adapter.py 45 例（宿主桩 akcli 包 + 桩 CLI）；tests.test_akcli_adapter → Ran 45 OK（skipped=1）；全量 discover → Ran 670 OK（skipped=1，master 基线 625，无回归）。
- 真原生资格（opt-in，AEDL_PR1_NATIVE=1 + AEDL_AKCLI_PYTHON）：NativeQualificationTests → Ran 2 OK。五个夹具 DC-01..DC-05 经 read_native 全部 PASS 并产出规范化观察（DC-04 = 22 组件 / 84 pin / 29 分区，complete=true）；真 strict 路由在 DC-04、DC-05 上 APPLIED_TO_STAGE，3/3 op ok，before/after 与 2026-09-16 本机独立复现逐字节一致（DC-04 655f585d→2f660180；DC-05 08393ee9→033e4efa）。实测 akcli 0.21.0、发行包摘要 a81c1a4d、本设计 embedded symbol digest 9a0473ff。
- NOT_RUN：CONSTRAINED_EXCEPTION 对真 akcli writer（无 E1/E2/E3 原生夹具，只用桩验证软件语义）；C4-P1..P8 扰动（属验收侧 B5）；C5/C6；candidate 提交与正式 Evidence。
- 需人工裁定的实现判断：① symbol_digest 定义为文档内嵌符号库摘要（akcli 0.21.0 不暴露全局 cache 目录）；② 原生观察的 sheet/pin UUID 由适配器确定性派生（akcli 不返回逐 pin 实例 UUID），C3 的 native 比较不含身份故当前成立；③ severity 的 NOTE→INFO 显式映射；④ launcher_argv 只用于 CLI，worker 一律以 worker_python -m 启动。四项均写入台账条目「实现中做出的、需人工复核的判断」。
- 范围外机械改动：docs/ID_MAP.md 与 tools/build_ai_usage_index.py 重放 Yenefa 2026-09-14 已批准的 DSH 代号登记（原登记只在未合入的 PR #72 分支），已在 envelope 授权链与台账中标注。
- 状态：PENDING_HUMAN_REVIEW；未 commit、未 push、未建 PR（等 Owner 指示）。

## 2026-09-17 PR #75 人工 REQUEST_CHANGES 整改（AI-20260917-DSH-525A0E8BBDFDEFA274AA1A6CA95F43EE 续记）

- 触发：Owner 对 head c2800df 的评审——3 项 blocker（op-list 只比较 op 名称 / fresh-after 仍以 writer 回执为事实源 / warning 对象身份丢失且无 host-frozen background）+ 3 项应修（闭合校验未递归 / op-list 路径 containment 只做 lexical commonpath / coverage 自证与 no_connect 硬编码）。
- 整改：逐条见台账条目补记。核心口径改为「工具说成功不算，fresh artifact 自己说了才算」。
- 新增回归：same-op/different-arguments；回执干净但 fresh 出现新 WARNING；warning 换对象；畸形嵌套 proposal/oplist/op 不抛异常；op-list 经目录 junction 逃逸。另加 background 白名单机制单测、reader 库存不一致或无可交叉核对 → UNKNOWN、畸形 stage_request 不抛异常、proposal 自身 digest 不符。
- 验证：tests.test_akcli_adapter 57 OK；discover 681 OK；真原生资格 2 OK（DC-04/DC-05 仍逐字节一致）；junction 用例实测执行（非 skip）。
- 遗留上报：合同当前没有 host-frozen background warning 的绑定通道，故本版所有 WARNING 一律阻断；需要 Owner/验收侧决定是否新增该通道。
- 状态：PENDING_HUMAN_REVIEW；未 merge。

## 2026-09-17 PR #75 第二轮 REQUEST_CHANGES 整改（同一工作单元续记）

- 触发：Owner 第二轮评审——Ubuntu CI 红（blocker）+ stale proposal/TOCTOU + authority 冲突 + receipt-only NC + Windows 跨盘 commonpath + PR 正文数字过期。
- CI 根因：ubuntu-latest 的 hosted Python `bin/python` 是符号链接，被 `_is_link` 判成解释器缺失，导致 ExceptionWriterTests 全 4 例失败。已改为「宿主冻结的可执行文件允许符号链接，数据路径仍禁链接组件」。
- 其余整改见台账补记②：base_source_sha256/context_id/target 三项 internal binding（写前失败）、authority 重复或 DENY 一律 BLOCKED、回执与 fresh read 分项矛盾即阻断、`_common_root` 把跨盘 ValueError 转成输入错误。
- 口径承认：C4 把 `bound_policy` 当作 host-bound opaque payload，不宣称自行重验完整 BoundPolicy。
- 验证：C4 63 OK（skipped=3）；全量 688 OK（skipped=3）；真原生资格 2 OK（DC-04/05 逐字节不变）。
- 状态：PENDING_HUMAN_REVIEW；未 merge。

## 2026-09-17 C4-P1 原生扰动资格（新卡 PR1-C4-PQ，分支 feat-pr1-c4-perturbation-qualification）

- 分支基线：暂以 PR #75 head `cda3155` 为 base（#75 尚未合入 master，AI 不 merge）；#75 合入后立即 rebase 到 master 再开 PR。
- P1 取证（真 akcli 0.21.0）：`add_net_label name=+5V at=C1.1`（C1.1 本就在 +5V）→ writer 返回 exit=0 / applied=true / status=applied / op ok / created_uuids=[2b641f80-…] / connectivity=[]，**但文件字节零变化**。
- 已固化为回归：`NativePerturbationTests.test_p1_an_applied_receipt_with_an_unchanged_artifact_is_blocked`（opt-in，真工具链）→ 断言 writer 确实报成功且 adapter 判 BLOCKED / REPAIR_EFFECT_MISMATCH；另有常驻用例把同端点 `add_wire` 钉在词表边界（BLOCKED / REPAIR_INPUT_DRIFT，0 次写调用）。
- 验证：tests.test_akcli_adapter 65 OK（skipped=4）；discover 690 OK（skipped=4）；真原生资格 3 OK（DC-04/DC-05 逐字节不变）。
- 待办：C4-P2..P8；`created_uuids` 与实际新增顶层对象的对应关系未校验（合同 §8 要求），已上报待裁定。
- 状态：PENDING_HUMAN_REVIEW。

## 2026-09-17 C4 created UUID ↔ 实际新增对象绑定（卡 PR1-C4-UUIDS，分支 fix-pr1-c4-created-uuid-binding）

- 起因：PR #76 评审裁定 `created_uuids` 对应关系是真实合同缺口（合同 §8），单独立 implementation fix card。base = master `1814548`。
- **开工探针发现的缺陷**：`source_objects()` 未按 C2 口径遍历文档子节点 —— native 观察永远只报 1 个 source 对象（DC-04 真实有 114 个），且身份带字面引号、AST 编码与 C2 不同。已改为复用 verifier 的纯 source helper（同口径、同编码）。
- 绑定实现：`op_results[].created_uuids` 并集必须恰好等于 fresh before/after 顶层对象差集；非 canonical UUID / 重复 UUID → TOOL_ERROR；集合不等 → BLOCKED / REPAIR_DELTA_MISMATCH。
- 真工具链事实：DC-04 / DC-05 均为 114 → 117 个顶层对象，新增 3 = 上报 3，**严格相等**，故按严格相等实现（无容差）。
- 测试夹具同步修正：stage 改为 verifier 可解析源码（uuid 加引号）；桩 CLI / 桩 writer 改为在文档内插入与回执一致的对象（旧桩只在文档外追加文本）。新增 4 例绑定回归 + 承接 PR #76 的 P1 `created_uuids` 断言（钉住观测 UUID）。
- 验证：tests.test_akcli_adapter 69 OK（skipped=4）；discover 694 OK（skipped=4）；真原生 3 OK（DC-04/DC-05 逐字节不变且上报集合 == 新增集合）。
- 上报：adapter 现依赖 `gates.repair_verification` 的三个私有 source helper（如需正式化应在合同层给公共名）；`root:<kind>` 身份按严格一致口径会阻断（fail-closed，已文档化）；本卡只闭合回执 vs artifact，独立 delta 仍归 verifier。
- 状态：PENDING_HUMAN_REVIEW。

## 2026-09-17 C4 UUID 绑定 —— PR #77 评审整改（同卡 PR1-C4-UUIDS，分支 fix-pr1-c4-created-uuid-binding）

- 触发：Owner 对 PR #77（head `838acee`）裁定 **REQUEST_CHANGES** —— 方向认可，2 个 blocker + 1 个 gap。本段为同一 PR 的整改轮，不新开卡、不改判据（先改实现与测试）。
- **blocker 1（状态分类）**：封套 acceptance 与 PR 正文都写定「非 canonical UUID → `TOOL_ERROR / REPAIR_TOOL_PROTOCOL_ERROR`」，但实现把所有 `reasons` 统一落成 `BLOCKED`，测试也断言 `BLOCKED` —— **测试在保护错误行为**。已改为：非 canonical 与「同一 created UUID 被多个 op 上报」一律以 `TOOL_ERROR` 收口并即时返回（不再据畸形集合推导 delta）；按 C4-P4，重复 `op_index` / op 缺项仍保持 `BLOCKED`。桩 CLI 的 `duplicate-op` 形态同步隔离扰动（原来同一次扰动同时制造了重复 index 与重复 UUID，会让两条判据互相污染）。
- **blocker 2（事实源未绑定）**：`read_native` 用 worker 上报的 `source_sha256` 给 host 自己重读的字节盖章；`_assemble_observation` 因此可产出「components 属 revision A、source_objects 属 revision B」的混合观察，而新的 UUID 差集正建立在这份观察上。已改为：`hash_bytes(host_raw) != payload.source_sha256` → `BLOCKED / REPAIR_SOURCE_UNBOUND`（合同 §7 固定 reason code，非新造），不交出不绑定的观察；`_verify_effect` 另要求 `native_before/after.source_sha256` 等于本事务的 before/after 源哈希，否则 `BLOCKED / REPAIR_SOURCE_UNBOUND`，且在任何 delta 推导之前返回。附带修正：`read_native` 的 `BLOCKED` 原被 `apply_stage` 折叠成 `UNKNOWN`，现按原类传播（新增 `_native_failure_status`）。
- **gap 3（平价回归）**：新增 C2↔C4 `source_objects` 平价断言（identity / kind / semantic_ast_sha256 逐一致）两例 —— 普通套件一例直接比对 `adapter.source_objects` 与 `gates.repair_verification.observe_source`；opt-in 真工具一例比对 `read_native` 的观察与 `observe_source`。注意 `normalize_observation` 会对 `source_objects` 排序，故普通套件按 identity 建映射比较，原生一例两边都已归一化、可直接比序列。
- 评审明确不挡 merge 的项：adapter 对 `_source_ast/_source_children/_source_value` 的私有名耦合留作 follow-up（合同层给公共名），本轮未改 `gates/**`。
- 验证（本轮实测原文）：tests.test_akcli_adapter **75 OK（skipped=5）**；全量 discover **700 OK（skipped=5）**；真原生 opt-in（akcli 0.21.0 + 3.11.15）**4 OK**——P1 假成功仍 BLOCKED、DC-04/DC-05 仍 `APPLIED_TO_STAGE` 且上报集合 == 新增集合、新增平价用例通过。
- **反向对照（证明新测试非空转）**：把 `tools/akcli_adapter.py` 临时还原到 HEAD 后，本轮 5 条新增/改判测试全部 FAIL（`Ran 6, FAILED (failures=5)`）；平价用例在修前修后都通过 —— 它是防漂移回归，不是新缺陷证据。随后已还原修复版并复跑全绿。
- 状态：PENDING_HUMAN_REVIEW。

## 2026-09-17 C4 toolchain binding 前移到 PRECHECK（新卡 PR1-C4-PRECHECK，分支 fix-pr1-c4-precheck-binding）

- 触发：Owner 对 PR #78 裁定 **REQUEST_CHANGES / HOLD** ——「这次 qualification 真正发现了一个 C4 adapter 合同缺陷：P6 symbol digest mismatch 发生在写后才拦截」，并指定先开本 fix、修完 merge、再 rebase #78。本卡 base = master `0626375`。
- **缺陷**：`symbol_digest`、运行中 akcli 版本、实际安装分布 digest 都在 `_verify_effect()`（**writer 执行之后**）比较，而同实现的 manifest 版本却在写前拒绝 —— 安全等级不一致。后果：digest 不符时真 writer 仍被启动并成功改写 stage（`tool.exit_code = 0`），之后才报 `TOOL_ERROR`。合同 L355/L369 把「校验 toolchain + native before 全量读取」钉在 PRECHECK、把 native write 钉在 STAGE_APPLY（只调用一次），所以能由 (manifest + native before) 定案的属性必须在写前定案。
- **修法**：新增 `_verify_toolchain_binding()`，在 `native_before` PASS 之后、`_execute_route()` 之前调用；不匹配 → `TOOL_ERROR / REPAIR_TOOL_UNAVAILABLE` 并直接返回。`_verify_effect()` 只保留「分布 digest 在两次读之间变化」这一条（本质上只能在写后观测）。**失败类别与 reason code 相对修前完全不变**，只有时点前移；未改判据、未改 `gates/**`、未改契约语义。
- **测试**：3 条既存桩用例补断言 `call_log() == []` + stage 字节不变；新增桩用例守护被保留的跨读检查；新增**原生**用例（真 akcli 0.21.0 + 扰动 `symbol_digest`，mock 记录每次 subprocess）断言 `draw` 调用 0 次且字节逐字节不变。
- 验证：tests.test_akcli_adapter **77 OK（skipped=6）**；全量 discover **702 OK（skipped=6）**；真原生 opt-in **5 OK**（DC-04/DC-05 仍 `APPLIED_TO_STAGE` 且逐字节一致，正常路径不回归）。
- **反向对照**：把 adapter 临时还原到 HEAD 后，3 条桩用例 `Ran 4, FAILED (failures=3)`；原生写前用例 `FAILED (failures=1)`，断言显示 `draw` 的 argv 列表**非空** —— 未修版确实把真 writer 启动了，正是缺陷本身；被保留的跨读用例在未修版同样通过（行为守护，非缺陷证据）。随后还原修复版并复跑全绿。
- **同会话的 #78 取证（不属本卡目标）**：按 Owner 指示另做一次 P8 `delete_object` bounded probe（对象身份取自 adapter 自己的 pinned parser，非正则）。12 次探针：DC-03 的 2 根 wire、DC-04 的 4 个 label、DC-01 的两个冻结 `delete_object` uuid **全部被 strict 合法拒绝**（exit 6，未写入）；DC-04 的 4 个 `no_connect` 删除成功且字节改变、但 fresh read 新增 finding = **0**。按严格筛选（PRECHECK 过 + writer 真跑 + exit 0 + 字节变 + 之后才出新 finding）候选为 **0** → **P8 native = `NOT_REACHABLE_WITH_CURRENT_V1+FIXTURES`**（据此不改词表、不扩 Operation v1）。原始回执见 PR #78 评论。
- 后续（按 Owner 排序）：本卡 merge → PR #78 rebase 到新 master，并把其 P6 native 断言的 `exit_code == 0` 改成「写调用 0 次 + 字节不变」并更新 grading matrix → P3 acceptance erratum（draft-5，复用 DC-01/02/03 接 E1/E2/E3，**不新造 schematic fixture**）→ C4-P7 round-level 交 C5/pipeline。
- 状态：PENDING_HUMAN_REVIEW。

## 2026-09-17 C4-P3 acceptance erratum（draft-5，新卡 PR1-C4-P3-ERRATUM，分支 docs-pr1-c4-p3-erratum）

- 触发：Owner 2026-09-17 裁定 P3 判据与 PR-1 合同存在**语义冲突**，并**明确扩 Scope** 授权把 `notes/b5-acceptance/C3-C6_PERTURBATION_CRITERIA_DRAFT.md` 加入 `allowed_paths`，同时逐条限定 draft-5 只允许做四件事。本卡 base 暂为 PR #79 head `4ccafca`（同 PR1-C4-PQ 先例），#79 合入后 rebase 到 master。
- **冲突本体**：C4-P3 原文「走 API 路径且 `tool.tool_applied=null` → 不得当成成功」，把「API 路径没有 `applied` 字段」这一**设计事实**当成失败依据。合同 §8 L253 规定该路径**原生没有** `applied` 字段（`null` 是设计使然），L255 规定 exception「同样要求每个 op ok、真实字节改变及重读成功；不能用 API list 非空作为成功条件」——`applied=true` 只是 **STRICT** 路径的合取项。实现亦如此（adapter：API 路径 `tool_applied is not None` → 拒；STRICT 路径 `is not True` → 拒）。
- **反向证据检索（刻意敌意核对）**：合同中「不得当成成功 / 不能当成成功」**零命中**；无任何条文规定 API 路径的 `null` 本身必须失败。两处易被断章取义者均不支持反读（L425 是测试用例清单而非谓词；L371 的「applied 矛盾」指矛盾，而 L253 已确立 `null` 为非矛盾设计值）。结论：矛盾干净。
- **改动（19 insertions / 2 deletions，仅四处）**：① C4-P3 行改为「`null` 不得当作 affirmative applied evidence；须 `op_results` 完整 + 真实字节改变 + fresh reread 成功 + connectivity 成立才可 `APPLIED_TO_STAGE`；红 = 缺任一独立条件却判成功」；② 文件头 `DRAFT — NOT FROZEN` 理顺为「draft-4 已按 §7 第 2 步冻结登记 + draft-5 是 Owner 授权的 post-freeze erratum」，并说明旧字样为历史口径、不改判据效力；③ 版本表新增 draft-5 行（只改一处、条数仍 28 条）；④ §7 新增第 6 条 erratum 登记（触发/范围/新旧 sha256/哈希方法/作废哈希警示/修正时点/依据）。C4-P1/P2/P4–P8 与 C3/C5/C6、§1/§3/§4/§5/§6 **零改动**，评审可按 diff 逐行核对。
- **冻结哈希（按 §7 第 2 步登记）**：draft-4 `0db600762b06056f0da0479f23d5ee702311732f932fc8581ea17edfe1070a7c`（21105 B，blob `c36a14b`）→ **draft-5 `aa6df32bc0aabc4befce14e5b24310aeb1f34343d5a245348f281f5d4f338993`**（28825 B，blob `7345ecc`）。**哈希生效口径**：draft-5 只有这一个**最终生效 / 冻结** hash；PR 内先后出现的两个 candidate `29483b9b…`（`cd48153`）与 `3c4f9167…`（`f5492cf`）**确实 push 过、在 PR 上可见，但从未合入、从未生效，均不得作为冻结版本引用**（与 draft-4 那个已作废 `96f2596f…` 同理，区别是这次属正常的 pre-merge review 修订）。已写进判据 §7 第 6 条。
- **PR #80 合入前评审修订（第 2 轮，Owner 裁定 REQUEST_CHANGES，只挡一处）**：draft-5 首版把 C4-P3 写成「`null` 不是失败；缺任一独立条件却仍成功才算红」—— 但**「缺哪一条条件」没被写进扰动本身**。拿正常 DC-01 去跑（`null` + ops all ok + bytes changed + reread ok + connectivity ok → `APPLIED_TO_STAGE`）是**完全正确**的结果，却与本组「八条都红在 adapter 层」的通过判据**自相矛盾**，会直接影响下一张 native P3 卡怎么判。已按 Owner 指定把 C4-P3 写成**一个正对照 + 一个真扰动**：正对照 = `null` + 独立条件全成立 → **允许** `APPLIED_TO_STAGE`；**负扰动（计入「八条都红」的就是这条）** = 保持 `null`、`op_results` 非空全 `ok`，但移除预先写死的独立成功条件 **「源 bytes 不改变」** → 必须非 `APPLIED_TO_STAGE` 且 `reasons` 含 `REPAIR_EFFECT_MISMATCH`；**verdict 只按负扰动判定**，正对照是控制组。相对首版 draft-5 仅 **7 insertions / 3 deletions**（只动 C4-P3 行 + §7 第 6 条），相对 draft-4 仍是「只改 C4-P3」。
- 该轮顺带写进 §7 第 6 条的两条防重复推演结论：① **不会新设 §1 规则 3 的第二个例外** —— 该规则约束 `COMMITTED`，而它属 pipeline 层 `TransactionStatus`，adapter 层零命中；② **负扰动已有桩层覆盖**：`ExceptionWriterTests.test_a_non_empty_api_result_without_a_byte_change_is_blocked`（exception 路由、`tool_applied=null`、ops 全 `ok`、字节不变 → `BLOCKED` / `REPAIR_EFFECT_MISMATCH`），同类的 `test_the_api_path_reports_tool_applied_null_and_still_verifies_the_bytes` 即 stub 层正对照。
- **第 3 轮（治理 / 审计口径同步，Owner 复审 `f5492cf` 后裁定）**：核心 P3 blocker 已 CLOSED，仅余三处口径未同步。① **envelope acceptance 落后**：仍停在首版「缺任一独立条件却判成功」，**没钉住**正对照 + 固定负扰动 —— 已按 Owner 结构改写 acceptance，明列 positive control / negative perturbation / **qualification validity**，并钉死新语义「**正对照必须先通过；正对照失败 → 本条记 `NOT_RUN` / qualification invalid，不得因负扰动是红的就算 PASS**」（同语义也补进判据 C4-P3 行与 §7「修正范围」）。② **「发生在任何观测之前」过强**：本 PR 自己就承认实现层已有两条 stub 行为测试，即行为观察已存在；已改为「**发生在任何正式 C4-P3 qualification / verdict 之前**」，并明写这些测试从未形成 P3 verdict、故**不用于重判任何既有 P3 结果** —— 口径比原来更强（不是「从没见过实现」，而是「见过实现测试，但 frozen 判据与更高优先级合同冲突，且在正式 P3 验收前修正」）。③ **「draft-5 只有一个 hash / 未发布中间版本」不成立**：`cd48153 / 29483b9b…` 确实 push 过并可见；已改为「只有一个**最终生效 / 冻结** hash，两个 candidate 从未合入从未生效、不得引用」，并把这轮自己产生的 candidate（`3c4f9167…` / `f5492cf`）一并登记，避免后人翻 history 产生无谓疑点。
- **哈希方法（本卡最重要的可复现细节）**：冻结值取 **git blob（LF）字节**的 sha256（`git cat-file blob <ref>:<path> | sha256`）。**不要**直接哈希 Windows 工作树文件：`core.autocrlf=true` 且该文件在 `.gitattributes` 中无规则，检出为 CRLF —— 实测同一份 draft-4 工作树为 21312 B / `D97DBF54…`，与冻结值不同；**工作树字节不符不构成篡改证据**。已写进判据 §7 第 6 条。另警示一个**已作废**的 draft-4 中间哈希 `96f2596f…`（`5f1ea53` 登记，11 分钟后被 `158f450` 作废重登），该值不在 worktree/master 上，勿引用。
- 修正时点：**任何正式 C4-P3 qualification / verdict 之前**（实现层已有既存 stub 行为测试，故不声称「任何观测之前」；但这些测试从未按 C4-P3 判据形成验收 verdict，C4-P3 至今 `NOT_RUN`，本次修正**不用于重判任何既有 P3 结果**），不触发 §5 / §7 第 3 条。冻结时序独立复核：登记 `158f450` 2026-09-13 14:38Z → PR #71 合入 `0d31a8b` 2026-09-14 03:01Z → C3 落地 `1888b5e` 09:42Z，登记早于实现，「判据先于实现」仍成立。
- 过程记录：admit 首次 **BLOCKED**（envelope `base.branch` 写错：`fix-pr1-c4-precheck-binding != docs-pr1-c4-p3-erratum`），按事实修正自己的元数据后 **ADMIT**；dev_gate 的 `scope_check` 首次 **fail**（forbidden 里写 `notes/**` 会连被授权的那个文件一起拒，因该检查对 forbidden **优先**且不支持取反），按 Owner 原话「**其余** notes/**」逐条列出其余 notes 路径后 8/8 全绿。两处均**未放宽任何检查项**。
- 未纳入、另报（Owner 已裁定）：§0.2 的「C3–C6 未落地」表已过期但**不挡本 PR**；C4-P2 的 route-scope 不在本卡动，且 **P2 已发生过观测**，将来改文字**不得**宣称「观测前 erratum」；`.gitattributes` 加 `text eol=lf` 单独立 GH-20 类维护，**不塞本 PR**。
- **操作红线（已解除）**：#80 原以 `fix-pr1-c4-precheck-binding` 为 base；#79 合入后本卡已 rebase 到 master 重锚，红线不再适用（第 4 轮）。
- **第 4 轮：rebase 重锚（#79 已合入后）**：Owner 确认 #79 merge（head `4ccafca` → merge `46f06129f3ba0a8346ac466bd4e57d56e633fa26`）。`git rebase origin/master` **干净重放 3 个提交**（`cd48153→245a508`、`f5492cf→c81455d`、`2b49f88→7fe8140`），随后重锚提交 `3ebc8cc`。**冻结判据字节未变**：rebase 前后 blob sha256 逐位相同 = `aa6df32b…`（28825 B）—— 这正是把冻结哈希钉在**文件字节而非提交身份**上的价值：rebase 改写了提交 SHA，冻结值无需重登。envelope `base.sha` 已重锚为 `46f06129…`，`allow_drift` 的 decision_ref 同步。provenance 影响如实记录：§7 第 6 条引用的 `cd48153`/`f5492cf` 在 rebase 后不再位于本分支历史，但**确实曾 push、在 PR 上仍可解析查看**，原表述依然成立，故**未**改冻结文件（改它只会再次变更已登记哈希）。过程记录：`pre-commit` 钩子拦下过一次格式不合格的提交（守卫按设计生效、**未产生提交**），`prettier --write` 修正后重跑全链通过；另有一次 `admit` 因漏传 `--allow-dirty` 失败（参数遗漏，非放宽检查）。两轮 admit + dev_gate 均 pass；最终 `baseline 3ebc8cc, dirty=false, 8/8, excluded=[]`。
- 后续（按 Owner 精确排序）：① **#79 merge**（已判 `APPROVABLE / MERGE-READY`）→ ② 本 PR 只改 C4-P3 行（已完成）→ ③ #79 合入后本项目 retarget/rebase 到 master，重新 admit/dev_gate/双平台 CI → ④ #80 merge → ⑤ 再开 P3 qualification 卡 → ⑥ rebase #78 并更新 grading matrix。第 ⑤ 步表述须更精确：DC-01/02/03 先证的只是 **native 正对照**，它**不能**证明 P3 扰动 PASS；负例能否 native 要等 bounded probe，做不到就如实写 `positive control = native PASS` / `negative perturbation = stub/hybrid PASS` / `full-native negative = NOT_REACHABLE`，**不得**把一次正常成功叫「native P3 qualification」，也不为凑齐新造 fixture。
- 状态：PENDING_HUMAN_REVIEW。

## 2026-09-18 C4-P3 native qualification（新卡 PR1-C4-P3，分支 test-pr1-c4-p3-qualification）

- 前置：PR #80 已由人合入，master = `f16b427`；判据 **draft-5** 已在 master 上（本卡只读，未改判据）。按 Owner 既定顺序第 ⑤ 步。
- 本卡是**验收侧**卡片：`tools/**`、`gates/**`、`notes/**` 为 forbidden，**未改被验对象一行**。
- **开工 bounded probe（真 akcli 0.21.0，只作用在 scratch 副本）证明两半都是 native**，因此**不需要 stub、不需要新夹具、不需要扩词表**（上一段对第 ⑤ 步的保守预期没有兑现成降级，是好事）：
  - **正对照 native**：DC-01→`E1`、DC-02→`E2`、DC-03→`E3`，全部 `CONSTRAINED_EXCEPTION`；实测 `APPLIED_TO_STAGE` / `tool_applied=None` / `changed=True` / `exit=0` / op 全 `ok`（4 / 1 / 4 个）。即 **API 路径 `tool_applied=null` 且独立条件全成立时可以成功** —— 正是 draft-5 相对 draft-4 要确立的语义。
  - **负扰动 native**：op 固定 `add_net_label name=+3V3 at=C2.1`（C2.1 本就在 +3V3 上 → 不改字节的 no-op）；实测 `BLOCKED` / **`REPAIR_EFFECT_MISMATCH`** / `changed=False` / `tool_applied=None` / `ops=['ok']` / `exit=0`，**两次独立运行逐字段相同**（连 created_uuid `1d801691-1263-56ad-b675-4a56a3e789b5` 都稳定）。这同时是**约束写入器上的真实 false-success 形态**（op 报 ok 且给出 created UUID，字节却不变），与 C4-P1 在 strict 路抓到的同类，只是走 API 路径。
- 改动（全在 `tests/` 与台账）：`_NativeToolchainMixin._patch()` 加 `route` 形参（**默认 `STRICT`**，既有调用者行为不变）；新增 opt-in 类 `NativeP3QualificationTests` 两例 —— ① 正对照，**并断言 writer 真跑了**（`exit_code==0`、ops 全覆盖全 ok）以排除假绿；② 负扰动，**先在同一夹具上内联跑正对照并断言通过**（强制 draft-5 的 qualification validity：正对照失败则本条随之失败，红负扰动不能单独把 P3 判成 PASS），再断言非 `APPLIED_TO_STAGE` 且 `reasons` 含 `REPAIR_EFFECT_MISMATCH`，**且该红确实落在 writer 之后**（`exit=0`、`tool_applied=None`、`changed=False`、ops 非空全 `ok`）。P3 的夹具 helper 保持**类内私有**（`_p3_ops`/`_p3_stage`/`_p3_apply`），刻意不进共享 mixin，避免与仍 HELD 的 #78（它给 mixin 加了 `_fixture_ops`/`_stage`/`_runs`）将来 rebase 冲突。
- 验证：tests.test_akcli_adapter **79 OK（skipped=8）**；全量 discover **704 OK（skipped=8）**；真原生 opt-in **7 OK**。opt-in 语义：未 opt-in → SKIP；opt-in + 解释器路径不存在 → **FAILED (failures=2)**（FAIL 而非 SKIP）。
- **反向对照（变异测试）**：对 `tools/akcli_adapter.py` 施加**单点**变异 —— ①「把 `tool_applied is None` 当作失败」（即**旧判据的读法**）→ 正对照用例 **FAILED (failures=1)**；②「去掉字节变化检查」→ 负扰动用例 **FAILED (failures=1)**；随后还原，`git diff --stat tools/` 为空、两例复跑 OK。**过程诚实记录**：变异脚本第一次因引号转义失败而**根本没施加变异**，那次的「OK」是对**未变异代码**的误读 —— 该次对照已作废，改用脚本文件（锚点未命中恰好一次即报错退出）重做，以上为**重做后**的结果。
- C4-P3 verdict：**PASS（native）**（判据 §3 字段见台账条目）；未产生 `COMMITTED`（adapter 层不产生该状态）。
- 仍未齐备：**C4 组「八条都红」不宣称成立** —— C4-P8 native 已由 #78 论证为 `NOT_REACHABLE_WITH_CURRENT_V1+FIXTURES`（词表假红），缺口属夹具/词表边界而非缺陷。C5/C6 仍 `NOT_RUN`。
- 后续：本卡 merge 后，rebase #78 并把其 grading matrix 的 P3 一行由 `CRITERION ERRATUM REQUIRED` 更新为 **native PASS**。
- 状态：PENDING_HUMAN_REVIEW。

## 2026-09-18 SchGen exposed DEV 格式导入（ingest-only 重切，分支 feat/schgen-dev-native-ingest）

- 触发：Owner 2026-09-18 既定顺序「#74 close and re-cut as a fresh BENCH/DEV PR without the old adapter」，并在本次会话的裁定中选择「先落 adapter 无关部分」。
- 事实：PR #74（head `052750c`）携带的旧草稿 `tools/akcli_adapter.py`（1103 行）与 master 上 PR-1 C4 的 fail-closed adapter **占据同一路径且 API 完全不同**，其 4 个依赖模块无法原样保留（`apply_and_verify` / `object_graph` / `parse_sexpr` / `export_netlist` / `check_expectation` 在 C4 adapter 中均不存在）。
- 本 PR：新增**自包含**的 `tools/schgen_native_ingest.py`（不导入任何 `tools.*`，有 AST 断言守护）+ `tests/test_schgen_native_ingest.py`（31 例）；记录见 `notes/schgen-dev-chain/TASK.md`（作用域横幅 + 历史正文保留）、EVID-20260918-001、RES-011。
- held 半（**未进本 PR**，仍在已关闭的 PR #74 及其分支上）：`tools/schgen_dev_chain.py`、`tools/schgen_dev_score.py`、`tests/test_schgen_dev_chain.py`、旧 `tools/akcli_adapter.py`，以及 writer 诊断、DEV-04/05/06 合同、writer 补丁资格与配对评分记录。须在 C4 adapter 上重新落地后另卡。
- 验证：见 PR 回执（`tests.test_schgen_native_ingest` / `discover -s tests` / `tools.dev_gate`）。首轮真实 KiCad 回放 `NOT_RUN`，已在评审整改轮补跑。
- 2026-09-18 评审整改（同卡 PR #82）：Owner REQUEST_CHANGES 后闭环 —— (a) raw/request/manifest 绑定改为读一次，消除 TOCTOU；(b) reference 导出改为读字节 + 只读结构 sanity，空/无签名内容的 reference 不再可能进 `evaluation-references.json`；(c) `cross_module: true`；(d) `export_netlist` 记录 kicad-cli 二进制 sha256；(e) 补真实 KiCad 8.0.9 双例 ingest smoke。测试 14 → 21 例，并以变异测试证明新回归有咬合力。未动 C4 adapter，chain/scorer 仍未塞回。
- 2026-09-18 第二轮评审整改（同卡 PR #82）：新增 `ToolchainBinding` 消除「读不到 = 没观察到变化」；整轮只绑定一个 KiCad binary（native / ERC / reference 三处调用前后各 verify，末尾再 verify，失败则不发布任何 manifest）；report 增加 `toolchain_binding` / `toolchain_error`；测试 21 → 26 例并做变异对照；真实 smoke 复跑两例 binding 均 PASS；RES-011 去掉「本 PR 未调用」的过期表述。
- 2026-09-18 第三轮评审整改（同卡 PR #82）：`--version` 探针纳入同一 `ToolchainBinding` bracket（binding → verify → probe → verify），并要求 `exit_code == 0`（非零退出即使打印 8.0.9 也拒绝）；`--kicad-cli` 必须指向真实文件、无 PATH 回退；report 记录已解析路径。测试 26 → 29 例 + 变异对照；smoke 复跑两例 binding 仍 PASS。
- 2026-09-18 第四轮评审整改（同卡 PR #82）：版本探针收敛为 `ToolchainBinding.probe_version()`（verify → probe → verify + `exit_code == 0`），整轮恰好 1 次；有 binding 时 `export_netlist`/`export_erc` 不再 `find_kicad_cli`/`tool_version`，只用 `binding.path`/`binding.version`，参数不一致即 FAIL 且不执行 subprocess；standalone 路径同样先绑定后探测。测试 29 → 31 例 + 变异对照；smoke 复跑两例 binding 仍 PASS。

## 2026-09-17 C4-P2..P8 原生扰动资格（新卡 PR1-C4-P2P8，分支 feat-pr1-c4-p2-p8）

- 前置：PR #77 已由人合入，master = `0626375`（Merge PR #77）；本卡从新 master 起分支（Owner 原排序：卡 2 等 #77 合入后再开）。判据唯一来源 `notes/b5-acceptance/C3-C6_PERTURBATION_CRITERIA_DRAFT.md` §C4（只读，未改）。
- 本卡是**验收侧**卡片：`tools/**`、`gates/**` 为 forbidden，adapter 是被验对象，本轮**未改一行实现**。
- 开工探针（真 akcli 0.21.0，只作用在 DC-04 副本）逐条定级，四条硬结论：
  1. **P5 可原生** —— `add_net_label name=GND at=U1.6`（U1.6 是 DC-04 的 `no_connect` 脚且在未命名网络上）触发真 writer **写前**合法拒绝：exit=6 / `error.code=OPLIST` / "net split/merge touches a named net; nothing written" / 字节零变化。
  2. **P6 可原生** —— 真工具照跑，只扰动宿主 binding：`symbol_digest` 不符 → `TOOL_ERROR`（真写入 exit=0 已发生，拒绝来自绑定）；`akcli_version` 不符 → **写前** `BLOCKED`，写调用 0 次。
  3. **P7 可原生** —— 单批 3 op = 恰好 1 次写调用且 `APPLIED_TO_STAGE`；拆两批时第 1 批单独可落地、第 2 批被真 writer 拒绝，最终字节 ≠ 单批结果（拆批与单批不等价）。
  4. **P8 无合法原生路径** —— 能产生连通性 finding 的形态（悬空 wire / 真正 wire 起 no_connect 脚）都需要 **Operation v1 之外**的 op，adapter 在**词表**处即拒（0 次写调用）＝判据 §1 规则 2 明令的**假红**；且实测 v1 的 `add_net_label` 打在被 `no_connect` 的脚上（`U1.5`/`J1.A8`），回执与 fresh read 的 connectivity **均为 0 条 finding**。故 P8 停在 stub-level，native `NOT_RUN`。
- 新增（全部在 `tests/test_akcli_adapter.py`）：`_NativeToolchainMixin` 的原生 qualification 工具（`_stage` 只扰动副本、`_runs` 用 mock 记录 adapter 启动的每一次 subprocess，使「一次写调用」可**实测**）；`NativePerturbationTests` 新增 5 例原生（P5 / P6×2 / P7×2）；新增 `StubPerturbationTests`（P2 伪造 `authorized=true`、P7 两批容器），类 docstring 明确标注 stub-level。P5 与 P6-digest 两例额外断言 `tool.exit_code`（6 / 0），自证红发生在 writer/绑定边界而非无关前置拒绝。
- **C4 组整体判据「八条齐备」：本卡结论是「尚未齐备」**，不宣称 PASS。P8 stub 层 6 个形态（new-warning / silent-warning / moved-warning / no-connect / error-severity / receipt-only-nc）全部阻断。
- 验证：tests.test_akcli_adapter **82 OK（skipped=10）**；全量 discover **707 OK（skipped=10）**；真原生 opt-in **9 OK**（含 P1 与 C2↔C4 平价仍绿）。opt-in 语义核对：未 opt-in → 原生类 skipped=7；opt-in 但解释器路径不存在 → **FAILED (failures=7)**，即 FAIL 而非 SKIP。
- 未闭合并升级 Owner：① **C4-P3 `NOT_RUN`**（缺 E1/E2/E3 原生夹具，卡内禁止自造夹具）；② **C4-P7 的「同一轮两次写调用」超出 adapter 单次调用的可观测范围**，需 round/transaction 层（C5 侧，未实现），本卡如实记为 adapter 边界之外、不冒充已验；③ C4-P6 的 digest 绑定是**写后**检查（version 是写前），供验收侧判断是否需写前绑定；④ 若要求 P8 有原生资格，需新夹具或词表/契约决定，本卡未自行扩范围。
- 状态：PENDING_HUMAN_REVIEW。
