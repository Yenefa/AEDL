# NeuroBoard 开源项目 Intake 报告（六步协议，Phase 4）

> Repo: https://github.com/Be-bibek/NeuroBoard
> Commit SHA: `d8e324828aa4cd4667fd07a9523d4f1d60a1c0aa`（本地浅克隆 `notes/open_source_intake/_neuroboard_repo/`，depth=1；克隆时间 2026-08-31，HEAD 提交日期 2026-08-26）
> Date Reviewed: 2026-08-31
> License: **冲突，未定案**——`LICENSE` 文件为 MIT（Copyright (c) 2026 Bibek Das），但 README「License」节顶部有 `[!WARNING]` 法律声明块自称 **CC BY-NC 4.0、禁止任何商业用途**（原文："you are legally prohibited from using this codebase for any commercial purposes, including startups, monetization, or revenue generation"）。两者直接矛盾，按 fail-closed 处理：**在作者澄清前，代码零复用**。
> 审查方法：本地 git clone 后逐模块阅读源码；对照既有 `notes/competitor-collision-analysis-2026-08-30.md` §2.2/§2.3/§2.4 结论（同一提交状态）逐项复核。
> 证据标记：`已验证`（本轮源码直接读到）/ `碰撞分析已核`（2026-08-30 同状态结论，本轮抽查一致）/ `未核实`（本轮未查证，不据此断言）。

---

## STEP 1 - CLAIM（它声称做了什么）

README 声称（`README.md`，含三个"世界第一"标语：*"The World's First Mobile AI Compiler for Native KiCad" / "The First Solo-Developer Agentic Framework for Text-to-PCB" / "The First Multi-LLM Native KiCad Generator Built for Mobile"*）：

| 声称 | 分类 | 源码核对结果 |
|---|---|---|
| NL → BOM → schematic → placement → routing → validation 全流水线 | Implemented | `已验证`：`ai_core/` 对应目录（copilot/schematic/routing/validation）俱在；`ai_core/agent/langgraph_loop.py` 接线完整 |
| **Transactional safety：Atomic commits with rollback on DRC/ERC failure** | Half | `已验证`：`system/ipc_client.py` 有 `begin_commit`/`push_commit`/`_RollbackBatch`，但 `_snapshot_positions()` 只存 footprint 的 x/y/角度（L353-369），不覆盖 track/via/net/zone；失败路径是"验证→self_correction→继续"，见 STEP 3 |
| SI（scikit-rf S 参数）built into pipeline | Half | `已验证`：`si/sparameter_analysis.py` L44 用 `rf.media.Freespace`（无介质回退模型），L32 硬编码目标 `s11_db=-25.0`，L52 空数据回退 `-30.0` |
| PDN（PySpice/NGSpice）built into pipeline | Half | `已验证`：`power_integrity/pdn_simulator.py` L13 "PySpice not installed → mock mode"，L32 `ir_drop_v = nominal_v * 0.01`（mock 1% 压降）；`碰撞分析已核`：即使 PySpice 可用也仅为电压源+走线电阻+恒流负载的简化 DC 模型 |
| DRC/ERC real-time checking | Half | `已验证`：`validation/drc.py` 的 `GlobalDRC` 是自写 shapely 几何检查，**任何违例只打 log，函数硬编码 `return True`**（L60-64 注释 "Warning rather than fatal error"）；`碰撞分析已核`：另有 `kicad-cli pcb drc / sch erc` 按 returncode 返回 bool 的路径（`mcp_server/server.py` L228 `run_drc`） |
| KiCad 10 IPC real-time integration（api.sock 零延迟同步） | Implemented（作者机器限定） | `已验证`：`system/ipc_client.py` L130 默认 socket 路径硬编码 `"ipc:///C:/Users/Bibek/AppData/Local/Temp/kicad/api.sock"` |
| MCP server 架构（neuro_layout / neuro_router / neuro_schematic / neuro_scratchpad） | Implemented | `已验证`：`mcp_runtime/registry.py` 注册四服务器；`mcp_server/scratchpad.py` 即"LLM 写 raw Python → 直接执行"工具（见 STEP 3-5） |
| Rust core router & solvers（`engines/`，README 自标 WIP） | Roadmap 冒充存在 | `已验证`：`engines/` 目录**零文件**；但根目录 `victory_lap.py` L3 `sys.path.insert(0, r'c:\Users\Bibek\NeuroBoard\engines\routing\rust_router')` 依赖它——该能力只存在于作者本地机器 |
| JLCPCB-compatible manufacturability validation | TO_VERIFY | `未核实`：`validation/manufacturability.py` 按 README 结构存在，本轮未逐行审 |
| Neural Part Resolver：LCSC 3M+ 器件自动取库 | Implemented（浅） | `已验证` 存在：`copilot/library_fetcher.py`、`system/lcsc_fetcher.py`；深度（库存/生命周期核验）`未核实`，未见任何库存/新鲜度检查 |
| Test suites（README 项目结构列为 `tests/`） | 名不副实 | `已验证`：`tests/` 仅 2 个文件共 307 行（`benchmark_tests.py` 48 行、`test_dsl_compilation.py` 259 行）；`.github/workflows/` 仅 `deploy.yml`（GitHub Pages 部署），**无测试 CI** |

---

## STEP 2 - SOURCE（源码实际上做了什么）

- **语言/框架**：Python 3.12+ 后端（FastAPI + uvicorn + LangGraph + SKiDL + kipy），Tauri + React 前端，MIT 声明（但见 License 冲突）。
- **Agent 回路**（`agent/langgraph_loop.py`，`已验证` 节选）：
  - `verification_node` 收集 `drc_errors`（L820）；`after_verification`（L918-919）：`return "self_correction" if state.get("drc_errors") else "end"`——**有错就进 self_correction 继续修，不是回滚重来**。
  - `self_correction_node`（L827 起）：按错误生成最小修复计划，清 `drc_errors` 后重试；`MAX_REFLECT = 2`（L684）但注释写 "Hard-capped at MAX_REFLECT=3"（L695）——常量与注释自相矛盾，属小证据表明代码评审松散。
- **事务层**（`system/ipc_client.py`，`已验证`）：`_RollbackBatch.__enter__` 先 `_snapshot_positions()`（仅 `{ref: (x, y, degrees)}`），异常时 `_restore_snapshot` 恢复位置；`begin_commit`/`push_commit` 本身无失败自动 abort 语义。
- **执行安全**（`mcp_server/scratchpad.py`，166 行，`已验证` 关键点）：
  - 文件自述："The LLM writes raw Python → we execute it → we return stdout/stderr"（L6-7）。
  - 防护 = 字符串黑名单 `forbidden = ["import os", "import subprocess", "open(", "eval(", "exec("]`（L87）+ subprocess `timeout=30`（L112）。字符串黑名单对有意规避无效（如 `__builtins__`、`getattr` 拼接），**非沙箱**。
  - L37 硬编码 `sys.path.insert(0, r'C:\\Users\\Bibek\\Documents\\KiCad\\10.0\\3rdparty\\Python311\\site-packages')`。
- **仓库卫生**（`已验证`）：`__pycache__/` 多目录入库；根目录堆着运行产物（`__main__.erc`、`*.log`、`*_sklib.py`、`out.txt`、`pi_hat.net`）与 `victory_lap.py`（庆祝脚本，依赖作者机器路径）；`ai_core/` 下大量一次性脚本（`calc_and_route.py`、`extract_pads_fixed.py` 等，含 `Bibek` 本机路径）。
- **目录实际与 README 漂移**（`已验证`）：`brain/`、`physics/`、`placement/`、`constraints/`、`netlist/`、`integration/`、`scratch/` 实际存在但 README「Project Structure」未列；整体是"作者个人工作目录直接入库"形态。
- **活跃/作者**：单作者（Bibek Das），HEAD 2026-08-26。

---

## STEP 3 - FAILURE（它最烂的地方）

按 AEDL 视角，从重到轻：

1. **License 自相矛盾（最严重，直接决定吸收边界）**：`LICENSE` 文件 = MIT（允许商用），README 法律声明块 = CC BY-NC 4.0（禁止商用、自称"Unauthorized commercial deployment is strictly tracked and enforced"）。同一仓库两种互斥授权声明，任一方向引用都有法律风险。AEDL 是参赛项目（含商业化叙事场景），**按最严解释处理：零代码复用**。
2. **验证全链路无 fail-closed 路径**：
   - `GlobalDRC.check_routing_violations` 硬编码 `return True`，间距违例只 `log.error` 不 raise（注释明说 "Warning rather than fatal error since we handled this geometrically"）；
   - SI 取不到真数据就落硬编码默认指标；PDN 无 PySpice 就落 mock 1% 压降；
   - 验证失败 → `self_correction` 继续，无"失败即停"。
   - 与 AEDL `_safe_gate`"malformed evidence must never become green"是镜像反面。
3. **"事务回滚"仅位置级快照**（`碰撞分析已核`+本轮复核）：`_snapshot_positions` 只存 footprint x/y/角度；新增走线/过孔/网络/铜皮不在回滚范围。README 却写 "your KiCad project is always valid"。
4. **不可移植**：KiCad IPC socket 路径、kipy site-packages 路径、`victory_lap.py` 的 rust_router 路径全部硬编码 `C:/Users/Bibek/...`；离开作者机器，核心链路（IPC、Rust 路由）直接断。
5. **LLM 生成代码直执行**：字符串黑名单 + 30s timeout 不是安全边界；且黑名单本身可被 `builtins` 反射绕过（未实测，仅代码审阅判断）。
6. **测试与 CI 形同虚设**：2 个测试文件 307 行，无测试 CI（唯一 workflow 是 Pages 部署）；"rollback/SI/PDN/validation"等核心声称零回归保护。
7. **Roadmap 冒充实现**：`engines/`（Rust router）零文件，但被架构图与 `victory_lap.py` 依赖；README 首屏三个 "World's First"（无证据、不可证伪式主张——AEDL 材料规范明令禁止的写法，可作反面教材）。
8. **README 与代码结构漂移**：多个实际目录未列、多个运行产物入库——文档可信度打折。

---

## STEP 4 - REUSABLE（哪些能力可以合法复用）

**前置判决：在 License 冲突定案前，代码层面一律 Reject；以下仅为思想层（Idea Only）清单。**

| 能力 | 复用方式 | 依据 |
|---|---|---|
| KiCad IPC 实时同步（api.sock + commit 语义）作为"设计数字孪生"的产品形态 | **Idea Only** | 碰撞分析判"IPC/UI/事件流可吃"指的是设计思想；AEDL 现为文件级产物 + 无头 CLI 管线，实时画布不在近期路线 |
| MCP 服务器按域拆分（layout / router / schematic / scratchpad） | **Idea Only** | 若 AEDL 未来做 BoardReview/RouteRepair 可插拔协议（P9 方向），"按操作域拆分工具面"是可选分组参考；AEDL 不依赖 MCP，绝不引入其 AGPL/NC 风险物 |
| LangGraph plan → execute → reflect → retry 回路（含重试上限） | **Idea Only** | AEDL 是门禁链不是常驻服务；重试上限思想 AEDL 已有等价物（门禁重跑） |
| NeuroModule DSL（约束感知硬件模块抽象） | **Idea Only，未核实深度** | 本轮未逐行审 `schematic/foundation.py`/`modules.py`；AEDL 的 intent JSON 协议已覆盖电路语义 |
| 全部代码 | **Reject** | License 冲突 + 硬编码路径 + 测试缺失 + 黑名单伪安全，任何一条都不满足 AEDL 入库标准 |

**License 义务**：冲突未定案，**不复制任何代码、不衍生任何片段**。若未来人工判定 MIT 有效且作者书面澄清，仍需重新走一遍 intake 才能改变本节结论。

---

## STEP 5 - AEDL TRANSFORM（接入后语义变化）

NeuroBoard 对 AEDL 的价值是**反面教材与流程教训**，不是能力输入：

1. **"Always-True DRC"作为 fail-open 实证样本**：AIC 报告/碰撞分析论述"AEDL fail-closed 门禁链为何必要"时，`GlobalDRC return True`、SI/PDN 回退硬编码、`after_verification→self_correction` 三点是可引用的公开源码级反例（引用时附 commit `d8e3248` 与文件路径，措辞守 AGENTS.md §8.8：不称首创、只陈述检查所见）。
2. **"事务回滚"语义的精确化教训**：对外宣称 "atomic rollback" 必须写清回滚覆盖域（位置级 ≠ 设计状态级）。AEDL 的等价机制是 artifact 级 sha256 绑定 + 门禁重跑，语义更强，报告对照时可讲清差异。
3. **License 矛盾入库流程**：本例登记进 `notes/open_source_intake/THIRD_PARTY.md`（"license 冲突 = BLOCKED，零接触"），作为后续 intake 的标准预检项——**STEP 0 先看 LICENSE 文件与 README 法律声明块是否一致**。
4. **"First/首创"表达的红线对照**：README 首屏三个 First 均无证据；AEDL 材料继续执行"禁止首创式主张"。

**AEDL 不获得**（诚实边界）：不获得任何 NeuroBoard 代码、架构依赖或产品形态承诺；本报告不改变 AEDL 任何现有门禁或管线。

---

## STEP 6 - VERIFY（怎么证明吃进去以后更好）

本次吸收为零代码，验证对象是**本报告结论的可证伪性**：

1. **证据可复核**：本地克隆 `_neuroboard_repo/` @ `d8e3248`；本报告所有 `已验证` 条目均给出文件与行号（`ipc_client.py` L130/L353-369、`sparameter_analysis.py` L32/L44/L52、`pdn_simulator.py` L13/L32、`drc.py` L60-64、`langgraph_loop.py` L684/L820/L918-919、`scratchpad.py` L6-7/L87/L112、`victory_lap.py` L3），人工可在克隆内逐条复核。
2. **证伪条件**：
   - 若作者在 README/LICENSE 澄清唯一授权（且为宽松许可），STEP 4 的 Reject 判决可重审；
   - 若仓库补上验证链路的测试且 `GlobalDRC` 改为真实失败传播，STEP 3-2/3 结论需改写；
   - 若 `engines/` 补上真实代码，STEP 1 "Rust router" 行改判。
3. **流程验证**：本轮起把"License 双声明预检"写进 intake 规程（README 目录更新见 `README.md`），下一个 intake 项目执行该项即证明流程改进落地。

---

## 附 A：能力对照表（AEDL 11 门禁 vs NeuroBoard，任务书待办 #4）

| AEDL 门禁 | AEDL 语义（fail-closed） | NeuroBoard 等价物 | 判定 |
|---|---|---|---|
| erc | kicad-cli ERC 结构化 JSON 解析，全 severity 收集 | `kicad-cli sch erc` 经 IPC（`碰撞分析已核`）；失败进 self_correction 继续 | 有而宽（不阻断） |
| drc | kicad-cli DRC 结构化解析，违例即红 | 自写 `GlobalDRC`（shapely）**恒返回 True** + kicad-cli 路径 | 名存实亡 |
| bom | BOM 新鲜度（7 天/未来日期即 fail）、正库存、零库存不自动换料 | `component_intelligence`/`lcsc_fetcher` 取件，无库存/新鲜度检查（`未核实`深度） | 无等价 |
| delivery | 交付包行/条目数与哈希绑定核验 | 无（导出 .kicad_sch/.net/PCB 但无清单绑定） | 无等价 |
| intent | intent 协议 + 哈希绑定 + 语义哈希锁定 | `intent_parser` 产 BoardSpec（内存态），无哈希无绑定 | 无等价 |
| ops | 制造装配文档一致性 | 无（Phase 13 才做制造链路，roadmap 未勾选） | 无等价 |
| schematic_semantics | 四视图（intent/原理图/PCB/固件）机器解析交叉绑定 | SKiDL 单向生成，无跨视图核对 | 无等价 |
| learning | 事故回溯 + 经验晋级门禁 | 无（`agent_memory` 仅项目记忆） | 无等价 |
| requirements_contract | 澄清合同 + blocking 未答即停 + 自哈希 | 无澄清环节（NL 直接解析，无问题清单） | 无等价 |
| board_review | 具名人工制造签发 + 撤销重签 | 无（全自动流转，无人工闸） | 无等价 |
| datasheet_contract | 器件绑定真实 datasheet 冻结件 + 人工签发 | 无（器件取自 LCSC 库，无 datasheet 证据链） | 无等价 |

**结论**：NeuroBoard 在 erc/drc 两点有形态等价物但均为 fail-open；其余 9 项门禁无等价实现。与碰撞分析 §3 的"候选可主张项"措辞要求一致：只写"截至检查日未发现等价实现"，不写"首创"。

## 附 B：与竞品碰撞分析的对照（两轮结论校准）

- 碰撞分析 §2.3"事务回滚=位置级快照＋局部修复"——`已验证` 成立（本轮独立复核 `ipc_client.py`/`langgraph_loop.py`，同提交状态）。
- 碰撞分析 §2.4 SI/PDN 弱实现、IPC 硬编码、scratchpad 黑名单——`已验证` 成立，本轮补上行号。
- 本报告新增（碰撞分析未展开）：① License MIT/CC-BY-NC 双声明矛盾；② `GlobalDRC return True` 恒真；③ `engines/` 零文件但被依赖；④ 测试/CI 形同虚设；⑤ 仓库卫生（`__pycache__`、运行产物、庆祝脚本入库）。其中①直接抬高吸收门槛至"零代码"。

（本文件为内部工作分析，按通宵任务书协议关联台账条目（见 `docs/compliance/AI_USAGE_LOG.md` 本会话条目），状态 PENDING_HUMAN_REVIEW。）
