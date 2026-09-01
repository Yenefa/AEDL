# OVERNIGHT 2026-08-31 夜间三路并行任务书（通宵自迭代，2026-09-01 早验收）

> 大统领 2026-08-31 指令：三路分工，一路 ZCode 主会话（P7），两路交其他 AI（P8 / P9）。
> 要求：长时间自迭代，明早验收。
> **通用前置（每个会话开工必做，按序）**：
> 1. 读 `AGENTS.md`（v1.4）→ 读 `docs/COLLABORATION.md`（领地规则）→ 读本文件你自己的卡片全文。
> 2. `git status` 确认工作区——当前基线 commit `24b8eaa`（分支 `fix/m2-schematic-semantic-release`，已推送）。
> 3. 领台账号：`grep -o "AI-2026[0-9-]*" docs/compliance/AI_USAGE_LOG.md | sort -u | tail -1`，
>    你用 最大号+1，**不许假设**（并行会话也在领号；发现撞号就再 +1）。
> 4. 跑基线：`py -3 -m unittest discover -s tests`（当前 127/127 全绿）——先确认你接手时也是绿的。

## 通用自迭代循环协议（三路共用）

每个迭代周期：
1. 从自己卡片的「待办池」按序取一项。
2. 实现/研究 → 自验证（测试或证据核对）。
3. `py -3 -m unittest discover -s tests` 全量必须绿，才允许下一步。
4. 在本文件你卡片的「进度日志」末尾追加一行：`- [HH:MM] 第N周期: 做了什么/验证结果/剩余`。
5. 提交：只 `git add` 自己领地内的文件，commit 信息带 `[AI-YYYYMMDD-NNN]`（你的台账号），
   然后 `git push origin fix/m2-schematic-semantic-release`。
   遇到 `index.lock` 冲突（三路并行同一工作树）等 10 秒重试，最多 5 次；仍失败就跳过 commit 只写进度日志。
6. 回到第 1 步，直到待办池清空或到达停止条件。

**停止条件**（满足任一就收尾）：某项连续 2 个周期修不绿 → 在进度日志记录失败现场并跳过该项；
待办池清空；全量测试红且无法定位。

**全局禁止**（违反即本次工作不合格）：
- 禁止设置 `manufacturing_release=true`、`HUMAN_REVIEWED`、`ACCEPTED`、任何 `signed_by` 字段——人工签发权不可触碰。
- 禁止改 `src/hardware/m2-board/`（板子冻结，等重签）、`gates/bom/`、`delivery/`、`notes/m2-evidence-reset/`。
- 禁止跨领地写文件；读不受限。
- 禁止修改门禁数量或让任何门禁"变绿"——发现门禁问题只记录进卡片，不修。
- 禁止删除/改写他人进度日志。
- 收尾：在 `docs/compliance/AI_USAGE_LOG.md` 追加完整条目，状态 `PENDING_HUMAN_REVIEW`。

---

## TASK-P7：finalize 语义哈希缺口修复 + runtime server 测试补强（ZCode 主会话，属主已领）

- 领地（可写）：`gates/requirements_runtime_server.py`、`tests/test_requirements_runtime_server.py`（新建）、
  本文件本卡片、`docs/compliance/AI_USAGE_LOG.md`（自己条目）、`docs/COLLABORATION.md`（本任务卡状态行）。
- 背景：P5 会话（AI-20260831-006）引入 intent 语义哈希绑定后，`intent_binding` 必须恰好含
  `{intent_path, intent_semantic_sha256}`（旧形状被 C4 拒收，fail-closed）。
  但服务端 `finalize`（`gates/requirements_runtime_server.py` L128-136）只写 `contract_sha256`
  不写 `intent_semantic_sha256`——P5 已实测：经它 finalize 的合同送 C4 被拒
  （`intent_binding must contain exactly intent_path, intent_semantic_sha256`）。
  P5 给出的修法：在写自哈希前
  `binding["intent_semantic_sha256"] = intent_semantic_sha256(json.loads(Path(binding["intent_path"]).read_text(encoding="utf-8")))`。
  语义哈希函数在 `gates/requirements_contract.py`（`intent_semantic_sha256`，白名单 `("components","nets")`）。
- 待办池（按序）：
  1. 修 finalize：写入 `intent_semantic_sha256`；注意 `intent_path` 可能是相对路径（以 root 为基准解析——先读
     `finalize` 现有代码确认它对 `contract_sha256` 的处理惯例，保持一致）。
  2. 新建 `tests/test_requirements_runtime_server.py`：至少覆盖——finalize 产物过 C4（用
     `gates.requirements_contract` 的校验入口对产物合同跑一遍，断言 intent_binding 相关检查通过）；
     intent 文件被篡改后 finalize→C4 必须拒（语义锁生效）；blocking 未答完 finalize 报错路径不变。
  3. 对照 `docs/api/requirements_api.md` 语义哈希章节，若 finalize 行为与文档不一致，修代码向文档对齐
     （文档是 P5 定稿的契约）；并在进度日志记录差异。
  4. 检查 `web/verify-hash.js` 的 mock 自哈希说明是否因本修复过期（只读检查；过期就在进度日志记录，
     `web/` 属 P2 领地不代改）。
  5. 若以上完成且全绿：给 `gates/requirements_runtime.py` 的 `parse_llm_proposal` 补边界用例
     （垃圾输入/未知 kind/超大 payload），该文件在本任务领地内**只加测试不改实现**；
     发现实现 bug 记进度日志，不代修。
- 明早验收标准：finalize 产物能过 C4；新增测试 ≥6 条全绿；全量回归绿；进度日志完整；台账有条目。

## TASK-P8：开源 Intake Phase 4（NeuroBoard）+ 遗留定案（研究路，属主空缺待领）

- 领地（可写）：`notes/open_source_intake/`（neuroboard.md 新建、README.md 目录状态、kicadai.md 仅可追加"补记"小节）、
  本文件本卡片、`docs/compliance/AI_USAGE_LOG.md`（自己条目）、`docs/COLLABORATION.md`（本任务卡状态行）。
- 背景：开源吸收 Phase 4（NeuroBoard）从未开始。intake 六步法看
  `notes/open_source_intake/circuitbot.md`（范例）与 `notes/open_source_intake/README.md`（目录与规程）。
  遗留两案：① kicad-ai（amcolex）上轮 WebFetch 得 GitHub 404 渲染页，"从未存在"待定案；② Konnect（KiCad MCP
  后继）AGPL-3.0 红线已立（`THIRD_PARTY.md` §2.4），其 license 细节（README 头部声明的商业授权条款原文）标 TO_VERIFY。
- 待办池（按序）：
  1. NeuroBoard 六步 intake（是什么/license/成熟度/与 AEDL 碰撞点/吸收建议/证据留痕），
     产出 `notes/open_source_intake/neuroboard.md`，格式对照 circuitbot.md。
     确定性标注：查不到就写"无法确定"，禁止脑补（仓库存在性、license、最近提交都要给证据链接）。
  2. kicad-ai(amcolex) 复核：换检索路径（GitHub API `https://api.github.com/search/repositories?q=...`、
     user 页、fork 网络）定案"从未存在 / 已删除 / 换名"，写进 kicadai.md 追加小节，给证据。
  3. Konnect license 细节取证：原始 README 原文摘录 + 链接，更新 `THIRD_PARTY.md` 对应行
     （`notes/open_source_intake/THIRD_PARTY.md`，仅改 Konnect 行与 §2.4，别的行不碰）。
  4. 若 NeuroBoard 可吸收：列能力对照表（AEDL 现有 11 门禁 vs NeuroBoard 能力），给出
     "吸收什么/怎么吸收/红线"建议，**不实装**。
- 明早验收标准：neuroboard.md 六步齐全；两遗留各有证据定案或"无法确定"+已试路径清单；台账有条目。

### P8 进度日志
- [07:01] 第1周期: `neuroboard.md` 六步完成（本地克隆 `_neuroboard_repo/` @ `d8e3248`；碰撞分析 §2.3/§2.4 逐项复核成立并补行号；新增 5 项发现：LICENSE 文件 MIT 与 README 法律声明块 CC BY-NC 4.0 双声明矛盾、`GlobalDRC` 恒 `return True`、`engines/` 零文件但被 `victory_lap.py` 依赖、`tests/` 仅 2 文件 307 行且无测试 CI、`__pycache__`/运行产物入库）；11 门禁能力对照表成文（erc/drc 有形态等价但 fail-open，其余 9 项无等价）；判决=零代码复用，只作反面教材；全量测试 127/127 绿。已提交推送 `0f8f1f4`（信息带 `[AI-20260831-016]`——见下条撞号说明）。
- [07:25] 第2周期: kicad-ai(amcolex) 定案——换路用 GitHub REST API 五层取证：仓库 404、账号存在（Alex Pabouctsidis，29 公开仓库全列，DSP/RF 画像零 KiCad 相关）、全网 `q=kicad-ai` 224 条无属主命中、事件流无创建/推送痕迹 → 判"公开仓库无存在证据/不可核实"，诚实注明 events API 90 天窗口限制；`kicadai.md` 补记小节写入。注：测试套件被并行会话增至 137 条，中途 1 次瞬态失败（并行写文件竞态），重跑 137/137 全绿，非我领地文件。
- [07:40] 第3周期: Konnect license 细节取证完成——GitHub API license 字段 `agpl-3.0` 与 README 自声明双来源核实；README「free for the little guys」商业授权条款原文摘录 + `COMMERCIAL.md` 关键条款（内部使用免费、分发/网络服务化触发 §13、作者自释"仅交互代码为独立作品"系单方声明）写入 `THIRD_PARTY.md` §2.4 与 Konnect 行；红线不变。附带：THIRD_PARTY.md 中 NeuroBoard / kicad-ai 两行同步为本会话定案状态（该两行即 P8 产出的目录状态）。
- [07:50] 第4周期: 收尾——README 目录/附属更新（含 `_neuroboard_repo` 勿提交警示 + .gitignore 待大统领补一行）、COLLABORATION.md P8 状态行更新、AI_USAGE_LOG 追加条目、全量回归后提交推送。待办池清空，P8 收尾。
- 台账号撞号说明（如实记录）：本会话开工时查到最大号 011，按+1 规则用 `AI-20260831-016` 提交了 `0f8f1f4`；其后发现并行会话也用了 012（`ea5e944`）、013（`266bb23`）、014（P7 台账条目）。已推送提交不改写历史；本会话最终台账条目改用 **AI-20260831-015** 并在条目内注明此撞号经过（`0f8f1f4` 信息中的 [012] 与本条属同一会话），供人工核账。

## TASK-P9：board_review 特征化测试 + 可插拔协议预备（代码路，属主空缺待领）

- 领地（可写）：`tests/test_board_review_golden.py`（新建）、`tests/fixtures/board_review/`（新建夹具目录）、
  `tools/board_review.py`（**仅当发现 bug 时最小修复，每处修必须先在进度日志写明 bug 现场+修复理由**）、
  本文件本卡片、`docs/compliance/AI_USAGE_LOG.md`（自己条目）、`docs/COLLABORATION.md`（本任务卡状态行）。
- 背景：HANDOFF「下一步验收顺序」第 5 条：可插拔协议抽取——先给 `tools/board_review.py` 补
  characterization/golden tests，再固化 BoardReview 与 RouteRepair 协议；**≥2 个真实实现后才定插件加载形式，
  禁止先造空框架**。现有测试 `tests/test_board_review.py`（3 用例）只覆盖 review_exit_code 与 USB 路由两函数。
- 待办池（按序）：
  1. 通读 `tools/board_review.py`，列出全部公开函数与其输入输出形状（写进进度日志第一条）。
  2. 为每个纯计算函数补特征化用例：用现网真实输入形状构造夹具
     （真实输入样例可从 `notes/m2-evidence-reset/generated/board_review_auto.json` 取），
     断言**当前实际输出**（特征化测试锁定现状，不是锁定理想）。
  3. golden 测试：构造一份最小 PCB 几何夹具（复用夹具目录），端到端跑 `tools/board_review.py` 主入口，
     输出与 `board_review_auto.json` 同 schema，把输出冻结为 golden 文件比对。
  4. 协议预备（只写文档不动代码）：在 `docs/` 外不许建文件——把 BoardReview/RouteRepair 的
     输入输出协议草案写进本卡片下方追加的「协议观察」小节，供 ≥2 实现后人工拍板。
  5. 每发现一个 bug（含"换封装后检查项静默消失"这类关键字盲区）即补一条对抗用例防回归。
- 明早验收标准：新增用例 ≥15 条全绿；golden 冻结文件入库；协议观察小节成形；台账有条目。

### P9 进度日志（属主 AI-20260831-016 已领）

- [06:58] 开工前置：分支 `fix/m2-schematic-semantic-release`，HEAD `6baa669`（任务书写基线 `24b8eaa`，
  实测已多出 `e51fa93`/`973f780`/`f395f6c`/`24b8eaa`/`6baa669`，按现状接手）。领号：grep 台账最大
  `AI-20260831-011` → 本会话 **AI-20260831-016**（已核对未撞号）。基线全量 **127/127 OK**（81.6s），接手时是绿的。
- [06:59] 第1周期（待办#1 函数盘点）：通读 `tools/board_review.py`（466 行），18 个公开函数输入/输出形状如下
  （**即特征化测试的锁定对象**）：

  | 函数 | 输入 | 输出 |
  |---|---|---|
  | `utc_now()` | — | `str`，ISO8601 UTC `YYYY-MM-DDTHH:MM:SSZ`（微秒清零） |
  | `review_exit_code(reviews)` | `list[dict]` | `int`：全 `status=="pass"`→0；**空表→1**（fail-closed） |
  | `parse_pcb(text)` | `str`（KiCad 10 s-expr） | `dict{footprints, edge, segments, vias:int, has_zone:bool, nets:list[str], pins:dict[str,`\|`None]}` |
  | `dist(a,b)` | 两个含 `x`/`y` 的 dict | `float` |
  | `edge_distance(fp,edge)` | `fp{x,y}`, `edge=(x1,y1,x2,y2)` | `float`，**可为负**（越界），未取 abs |
  | `review_usb_edge(footprints,edge)` | `list[fp]`, `edge` | review dict `{id,status,evidence,measured}` |
  | `review_antenna(footprints,edge)` | 同上 | review dict |
  | `review_ground_return(pcb)` | pcb dict | review dict（判据仅 `vias>=4 and has_zone`） |
  | `boundary_distance(cap,ic)` | 两个 fp | `float`：cap 质心到 **IC courtyard 边界**；IC 无 courtyard 退化为 `dist` |
  | `review_decoupling(footprints)` | `list[fp]` | review dict |
  | `review_usb_routing(segments,pins)` | `list[seg]`, `dict[pin→net]` | review dict |
  | `review_thermal(footprints)` | `list[fp]` | review dict |
  | `review_protection(sch_text,pcb)` | `str`, pcb dict | review dict —— **⚠️ bug-1：`pcb` 参数未使用，函数体直接读全局 `PCB_PATH`（L319-322）** |
  | `review_assembly(footprints,pcb_text)` | `list[fp]`, `str` | review dict |
  | `sha256_file(path)` | `Path` | `str` 64 hex |
  | `find_kicad_cli()` | —（读 `os.environ`→`PATH`→**硬编码绝对路径**） | `Optional[Path]` |
  | `render_board_views(cli,pcb_path,out_dir)` | 3×`Path` | `List[str]` 错误列表（空=成功） |
  | `main()` | —（读全局 `PCB_PATH`/`SCH_PATH`/`OUT_PATH`） | `int` 0/1 |

  模块常量：`USB_CHANNELS`（D+/D- 各含 `nets` 2 个 + `pins` 5 个）；阈值 `USB_EDGE_MAX_MM=1.0`、
  `ANTENNA_KEEPOUT_MM=7.5`、`DECOUPLING_MAX_MM=8.0`、`USB_DIFF_MAX_SKEW_MM=1.0`、`THERMAL_MIN_DIST_MM=10.0`；
  `RENDER_TARGETS`/`RENDER_WIDTH,HEIGHT=1600,900`。报告 schema（对齐 `board_review_auto.json`）：
  `{generated_at, pcb, board_outline_mm, footprint_count, nets, reviews[8], summary, note, render_evidence?}`；
  8 项 id=`USB_EDGE/ESP_ANTENNA/GROUND_RETURN/DECOUPLING/USB_ROUTING/SHT30_THERMAL/PROTECTION/ASSEMBLY`，
  每项固定 `{id, status, evidence, measured}` 四键。
- [07:00] 第1周期（可测性勘察，为待办#3 铺路）：① `parse_pcb` 在 `tools/`、`gates/` 内**无外部调用方**
  （`gates/schematic_semantics.py` 有自己的 `_parse_pcb`，不共用）→ 扩展其返回键安全。
  ② **kicad-cli 确实存在**（`C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe`），
  故 golden 端到端**必须打桩渲染**：否则单测跑 ~26s 且 PNG 字节不确定（哈希随渲染版本/抗锯齿漂移）→ golden 变 flaky。
  做法：patch `find_kicad_cli`→`None`，`main()` 跳过 `render_evidence` 但**照常计算并写出 8 项 review**，
  冻结这部分即稳定 golden。
- [07:08] 第2周期（待办#2 夹具）：新建 `tests/fixtures/board_review/minimal.kicad_pcb` 与 `tests/fixtures/board_review/minimal.kicad_sch`
  （最小 60x40mm 板，11 footprint / 5 via / 1 zone / 4 段 USB 走线）。几何是**按 8 项判据反推**摆放的：
  J1(USB_C) courtyard 前沿距上板边 0.03mm；U1(ESP32) 质心 (30,15)、7.5mm 净空圈内无器件、rot=0 天线朝板边；
  三颗去耦电容分别贴 U1/U2/U3 的 courtyard 边界（最差 3.9mm <= 8mm）；SHT30 距最近热源 36mm >= 10mm；
  USB 两通道铜长 20.0/19.7mm（skew 0.3mm <= 1mm）；C4 挂 +5V 使 PROTECTION 有 bulk 电容。
  实测 7 项全 pass（PROTECTION 单独验，因其当时读全局）。
- [07:09] **bug-1 现场与修复理由（修复前先记录，遵守本卡"每处修必须先在进度日志写明"）**：
  - **现场**：`review_protection(sch_text, pcb)`（L313-333）签名收了 `pcb: Dict` 却**完全没用它**，
    函数体 L319-322 直接 `Path(PCB_PATH).read_text(encoding="utf-8")` 读**模块级全局常量**重新扫一遍 +5V 电容。
  - **为什么算 bug 而不是风格问题**：`main()` 里 `pcb` 来自 `parse_pcb(PCB_PATH 文本)`，两条路径碰巧同源，
    所以产物一直"看起来对"；但只要调用方传入**另一块板**的 parse 结果（golden 测试 patch 掉 `PCB_PATH` 时、
    以及本卡目标"可插拔协议抽取"要求 `review(inputs)->verdict` 为纯函数时），该函数会
    **静默返回错误板子的 PROTECTION 结论**——fail-closed 门禁里最危险的一类：不报错，只是判错。
  - **修复（最小）**：把 +5V 电容计数下沉进 `parse_pcb`，新增返回键 `vbus_caps`；
    `review_protection` 改为读 `pcb.get("vbus_caps", 0)`，不再读文件、不再依赖全局。
  - **兼容性**：`parse_pcb` 仅在 `tools/board_review.py` 内被调用（`gates/schematic_semantics.py` 有自己的 `_parse_pcb`），
    新增返回键是**纯加法**；`review_protection` 唯一调用方是 `main()`，传入的正是新 parse 结果。
  - **不改的事**：阈值、判据、evidence 文案、`ok = vbus_caps >= 1` 全部保持原样；预期产物逐字节不变
    （修复后已用真实 M2 板复跑比对，见下条）。
- [07:20] 第3周期（待办#2+#3+#5）：新建 `tests/test_board_review_golden.py`，**51 用例全绿**（远超验收 >=15）。
  分布：纯函数特征化 10 / parse_pcb 6 / 8 项 review 特征化 9 / golden 端到端 5 / 对抗与盲区 21。
  golden 冻结于 `tests/fixtures/board_review/golden_minimal.json`（渲染打桩为 None，故报告中无 `render_evidence`，main 返回 1——这是有意的确定性状态）。
- [07:20] **bug-1 修复已落地并验证产物不变**：`parse_pcb` 新增 `vbus_caps` 返回键，`review_protection` 改为读
  `pcb.get("vbus_caps", 0)`。用真实 M2 板复跑比对：PROTECTION 的 `id`/`status`/`evidence`/`measured` 与磁盘上已冻结的
  `board_review_auto.json` **逐字节一致**（vbus_caps=1, tvs=False, pass）。即：修复只改变了"这个函数从哪儿取数"，
  没有改变任何判据或结论。回归用例 `test_protection_uses_the_parsed_pcb_not_the_global_path` 直接钉死该行为（全局指向有 bulk 电容的板、
  入参说没有时，必须按入审判 fail）。
- [07:21] 特征化测试额外锁定的 4 处现状怪癖（均写进用例 docstring，供协议化时决策）：
  ① `edge_distance` 越界返回**负值**不取 abs（`review_usb_edge` 用 `0 <= d <= MAX` 兜底）；
  ② `boundary_distance` 在 IC 无 courtyard（含**旋转件**，parse 时直接置 None）时静默退化为质心距；
  ③ `review_exit_code([])` **空表返回 1**（fail-closed，必须继承）；
  ④ `courtyard` 是 **tuple** 不是 list，且旋转件为 None。
- [07:21] **盲区对抗用例（待办#5，只锁现状未修）**：`review_decoupling` 按 lib_id 关键字选 IC。
  把 U3 从 SOT-353 改名为 **SC-70-5**（正是 M2 换料后 LDO 的实际封装）后，U3 **静默从去耦检查中消失**
  而总判定仍是 pass——这就是任务书点名的"换封装后检查项静默消失"。已写用例
  `test_decoupling_silently_drops_an_ic_whose_package_is_renamed` 冻结该行为；若将来关键字表扩了，这条会先红，提醒人工确认是有意修复还是回归。
- [07:21] golden 可维护性：报告里 `pcb` 字段是 `Path.relative_to(...)` 的结果（Windows 下是反斜杠）。
  **没有**改生产代码去规范化分隔符——那会重写 `notes/m2-evidence-reset/` 里已冻结的 M2 证据（该文件禁止改）。
  改为在测试的 `stable()` 里归一化，golden 因此跨平台稳定。golden 重生命令：
  `py -3 tests/test_board_review_golden.py --regen`。
- [07:26] **台账号撞号更正（按任务书"发现撞号就再 +1"）**：本会话 06:58 查号时台账最大为 011，
  故领用 `AI-20260831-012` 并已写入上面几条日志。现复核发现：并行会话同样领用了 012
  （其台账 L1349-1351 如实记录了这次撞号，并把 013/014/015 也占掉了）。
  当前台账实体条目最大为 `## AI-20260831-015`，且 016 在台账全文无引用 → **本会话改用
  `AI-20260831-016`**，上面日志中的 012 一律按 016 理解（不改写他人日志，只在此留映射）。

### P9 协议观察（待办#4，只写文档不动代码）

> 供 ≥2 个真实实现后人工拍板插件加载形式。**本轮不建任何框架/接口类/抽象基类。**

- **BoardReview 候选协议**（从 8 个 `review_*` 归纳，已是事实标准）：
  `review(inputs) -> {id: str, status: "pass"|"fail", evidence: str, measured: dict}`
  - `id` 常量；`status` 严格二值；`evidence` **必须是给人读的一句话，含实测数字并标注"需人工复核"项**；
    `measured` 只放机器可比的数值/布尔。8 个函数已事实遵守，可直接固化。
  - 汇总契约 `review_exit_code(reviews)`：**空表返回 1（fail-closed）**，这是必须继承的语义，不可改为"空=通过"。
- **RouteRepair 候选协议**：本轮在 `tools/board_review.py` 内**没有任何 RouteRepair 实现**；仓库里
  `tools/polish_routes.py`、`tools/probe_pads.py` 是两个未被门禁纳管、也未读实现的脚本（属他人领地）。
  → **结论：受门禁约束的 RouteRepair 实现数 = 0，不足 2 个。按任务书"≥2 实现后才定形式"，本轮不定协议**，
  仅登记待将来比对的候选形状：`(pcb_path, violations) -> {applied: list, skipped: list, errors: list}`。
- **抽取阻塞项（协议化前必须先解决，均为只读发现，本轮未改）**：
  1. **bug-1（全局读取破坏纯函数性）**：`review_protection(sch_text, pcb)` 不用传入的 `pcb`，
     函数体直接 `Path(PCB_PATH).read_text(...)`（L319-322）。这使函数无法对任意输入求值，
     直接违反 `review(inputs)->review dict` 的纯函数前提。修复见后续周期进度日志。
  2. **硬编码路径副作用**：`find_kicad_cli()` 硬编码 `C:\Users\fuker\...` 用户专属路径；
     `main()` 依赖模块级 `PCB_PATH/SCH_PATH/OUT_PATH` 常量。协议化时应改显式入参 + 依赖注入。
  3. **`edge_distance` 可返回负值**：越界时是负数而非 0；`review_usb_edge` 用 `0 <= d <= MAX` 兜住了，
     但这是隐式约定，协议文档须写明"距离可为负，判定端负责钳位"。

### TASK-P7 进度日志
- [夜间] 周期1: 发现任务书背景已过时——finalize 缺口在 P1 会话后段已修（commit 1857db4 内含
  `intent_semantic_sha256` 写入，P5 报告针对的是修复前版本）。按验收标准改为实测：新建
  `tests/test_requirements_runtime_server.py` 10 用例（finalize 产物过 C1-C7 全绿、签约后 intent
  电路变更被语义锁拒、未答 blocking 经 finalize 后仍被 gate 拒（锁定分层：server 组装/gate 权威）、
  三条 fail-closed 报错路径、HTTP 层 4 项端点行为）。**附带修复真 bug**：`_route` 原先无任何
  try/except，`ValueError("malformed JSON body")` 等异常导致客户端连接重置而非 400 JSON——
  加 `_safe_route` 包装（ValueError→400 {"error"}）。全量回归 137/127+10 全绿。
- [夜间] 周期2: `tests/test_requirements_runtime.py` 新建 18 用例（parse_llm_proposal 反脑补边界：
  垃圾输入永不抛异常、prose 包 JSON 提取、LLM 给的 answer 一律丢弃、未知 kind 升 blocking、
  id 改名两条路径特征化、超量截断、assumptions 强制 requires_human_confirmation）。
  **发现死逻辑**（未代修，已钉现状 + 留人工）：返回 `"ok": not warnings or True` 恒为 True。
  全量 155/155 绿，commit `266bb23`。
- [夜间] 周期3: ① API 文档一致性核对——`docs/api/requirements_api.md` "服务端写语义哈希" 与实现
  一致（周期1测试已钉）；文档仍无错误码章节（P2 遗留缺口，本卡领地外，建议人工补：
  "4xx -> {\"error\": str}"，与 _safe_route 现行为对齐）。② web 只读检查——`web/api-client.js`
  本就按 ApiError(400) 处理非 2xx，`_safe_route` 修复后 mock/真实两种传输层错误路径终于一致；
  `web/verify-hash.js` 校验的是合同自哈希，与本修复无交集，无过期。待办池清空，收尾。
