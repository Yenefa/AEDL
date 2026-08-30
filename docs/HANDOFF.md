# HANDOFF — project-027-autonomous-hardware-agent

> **AI 接手强制前置**：在任何实质修改前，完整阅读根目录 `AGENTS.md`（v1.4，含 2.1
> 硬件发布前必读 `docs/knowledge/` 两份文档）；该文件是 AEDL 当前 Agent 执行层唯一规范。
> 本 HANDOFF 提供项目状态与硬件证据边界；`docs/compliance/AEDL_开发记录与AI使用规范_v1.0.md`
> 仅保留为历史基线与格式参考。
>
> **接手惯例（2026-08-30 起生效）**：开工时另读 `docs/compliance/AI_USAGE_LOG.md` 最近
> 2–3 条记录——git 作者统一为用户身份，提交信息里的 `[AI-YYYYMMDD-NNN]` 只有台账能解码
> 到具体会话；据此识别前任/并行会话的工作边界、未审改动和已知坑，避免并发写坏工作区。
> 收尾时按 AGENTS.md 第 4 节为本次实质工作新增一条记录，默认 `PENDING_HUMAN_REVIEW`。

## 项目状态卡（2026-08-31，AI-20260831-011 更新）

- 板子：M2 ESP32-C3+SHT30；D1 极性已修、U3 已换料 C235316；待人工重签 board_review 后方可下单。
- 门禁：11 个 = 9 PASS + board_review FAIL（仅 `manufacturing_release=false` 等重签）+ datasheet_contract FAIL（32 项 BLOCK，全部待人工签发类）。
- 分支：`fix/m2-schematic-semantic-release` @ `e51fa93`，已推送（与 origin 同步）；master 未合并。
- 测试：127/127 全绿（`py -3 -m unittest discover -s tests`，2026-08-31 实测）。
- 待大统领：① 重签 board_review；② datasheet_contract 32 项签发（优先 U3 热复核、J1 需 HRO 官方图纸）；③ 未提交批次 commit 决定（第 11 门禁全套 + D1 修复证据）；④ master 合并。
- 吸收：CircuitBot intake+实装（第 10/11 门禁）；KiCadAI / KiCad MCP intake 完成（Konnect AGPL 红线）；NeuroBoard 未开始；kicad-ai(amcolex) 404 待人工定案。
- 检索：ID 引用地图见 `docs/ID_MAP.md`；协作任务卡见 `docs/COLLABORATION.md`；RAG 取舍见 `docs/knowledge/RAG_DECISION.md`。
- 历史细节：见下方归档区（现状以上方状态卡为准）。

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
- 调试产物可删：`freerouting_run2/3.log`、`g4_drc_probe.json`、`m2_board_rerun.ses`、
  `tools/polish_routes.py`、`tools/probe_pads.py`。
- （P3 会话补，2026-08-31）GitHub 克隆 KiCadAI 这类深路径仓库在 Windows 检出会因路径
  长度失败（exit 128），需 `git clone -c core.longpaths=true`。
