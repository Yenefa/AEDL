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
- [07:01] 第1周期: `neuroboard.md` 六步完成（本地克隆 `_neuroboard_repo/` @ `d8e3248`；碰撞分析 §2.3/§2.4 逐项复核成立并补行号；新增 5 项发现：LICENSE 文件 MIT 与 README 法律声明块 CC BY-NC 4.0 双声明矛盾、`GlobalDRC` 恒 `return True`、`engines/` 零文件但被 `victory_lap.py` 依赖、`tests/` 仅 2 文件 307 行且无测试 CI、`__pycache__`/运行产物入库）；11 门禁能力对照表成文（erc/drc 有形态等价但 fail-open，其余 9 项无等价）；判决=零代码复用，只作反面教材；全量测试 127/127 绿。

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

### TASK-P7 进度日志
- [夜间] 周期1: 发现任务书背景已过时——finalize 缺口在 P1 会话后段已修（commit 1857db4 内含
  `intent_semantic_sha256` 写入，P5 报告针对的是修复前版本）。按验收标准改为实测：新建
  `tests/test_requirements_runtime_server.py` 10 用例（finalize 产物过 C1-C7 全绿、签约后 intent
  电路变更被语义锁拒、未答 blocking 经 finalize 后仍被 gate 拒（锁定分层：server 组装/gate 权威）、
  三条 fail-closed 报错路径、HTTP 层 4 项端点行为）。**附带修复真 bug**：`_route` 原先无任何
  try/except，`ValueError("malformed JSON body")` 等异常导致客户端连接重置而非 400 JSON——
  加 `_safe_route` 包装（ValueError→400 {"error"}）。全量回归 137/127+10 全绿。
