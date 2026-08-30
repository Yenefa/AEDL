# 竞品源码级对撞分析：CircuitBot / NeuroBoard / kicad-ai / KiCadAI vs AEDL

> 作者：AI 研究辅助（2026-08-30，**第二轮校准版**）
> 性质：内部工作分析，非正式 Evidence；用于团队判断"README 撞车 vs 真实现撞车"。
> 方法：并发 Explore 子代理抓取 GitHub API / raw 源码 / CI / license，并逐文件核对失败分支。
> 状态标记：`已验证`（真源码抓到）/ `半实现`（有代码但受限或桩）/ `仅声称`（README/描述，无源码证据）/ `未核实`（我抓不到，不据此断言真或假）。
> **勘误说明**：第一轮报告在对 kicad-ai 与 KiCadAI 两处把"证据强度"拉到满，本轮已校准。凡"第一轮说 X，本轮改判"均标注。

---

## 0. 一句话结论（校准版）

**改写为：** 就本轮实际抓取并逐文件核对的公开源码而言，四个仓库**没有一个被证明达到 AEDL 现有的验证纵深**；但这不等于"None of them can"，更不等于"No one has this"。AEDL 的真正可主张项是"fail-closed 门禁、故障注入自我证明、跨视图哈希证据、人工制造签发、经验学习门禁"这几套**每次 run_gates 都真实执行的机器机制**；对每一套，"尚未在所列公开源码中发现等价实现"都要单独列证据，而不是打包一句"没人有"。**不要被 README 吓到继续重复造轮子——但也不要因第一轮结论而麻痹。**

---

## 1. 四个仓库源码级真相（第二轮）

| 仓库 | 语言 | 活跃 | License | 源码级真相 | 相比第一轮 |
|---|---|---|---|---|---|
| **CircuitBot** `HiwarkhedePrasad` | Python | push 至 2026-08-16 | MIT | LangGraph 真实现（`builder.py` 的 StateGraph/条件边/`error_end`/repair loop）。真修能力多；**LLM judge 每轮仍未在源码级确认为 hard fail-closed 门禁**（倾向评分记录）；roadmap 里 DRC-in-the-loop 仍标未实现 | 基本维持，用户与首轮一致 |
| **NeuroBoard** `Be-bibek` | Python | push 至 2026-08-26 | MIT | **半实现/夸大已获源码证据**（见 §2.2）：`_RollbackBatch` 只恢复 footprint 位置；失败传播链是"验证→self_correction→继续"，非事务回滚；SI 用 Freespace+默认回退指标；PDN 是简化 DC 模型；KiCad IPC 硬编码作者机器 socket 路径 | 首轮"事务回滚是假的"**本轮补上证据，可站住但需限定范围** |
| **kicad-ai** `amcolex` | Python | **本轮仍无法经我的工具定位**（GitHub API/raw/网页/search 均 404 或未命中） | **待裁决** | **结论：无法裁决，而非"不存在"**。它与外部描述（adversarial/context-free reviewer、findings ledger、waivers、done-gate、4/4 USB case）冲突。我的工具抓不到 ≠ 仓库不存在；但也别因为描述来自某模型就盖章"真实存在"。**请人工浏览器直接打开该 URL，或贴 raw README 定案** | 首轮"判 404/无法核实"是过度断言；**本轮同样拒绝反向过度断言** |
| **KiCadAI** `dshills` | Go | push 至 2026-08-24 | MIT（有 license） | **capability/evidence 机器实现为真（已验证）**：frozen corpus 的 SHA256 内容寻址、evidence/report/corpus 绑定、capability-eval 拒绝非法输入并 exit 非 0。**但 KiCad 生成、ERC/DRC subprocess、simulation/thermal/SOA、10 个 adversarial 夹具、clarification loop 均只见 README/spec/readiness 文档、未见源码调用链** | 首轮"只验证能力证据、不是 KiCad"**过窄**；但"已是完整 simulation-grounded 生成系统"**也证据不足**。两方向都别拉满 |

四条合计 star 数极低；无一条被证明完成实体板级验证闭环（AEDL 已授权打板、回件实测待做——但这同样不构成"AEDL 更先进"的证据，只构成"验证路径有别"）。

---

## 2. 逐模块对撞矩阵

### 2.1 宏观全流程（谁都有，"行为撞车"最不值钱，也最容易撞出恐慌）

| 环节 | CircuitBot | NeuroBoard | KiCadAI | AEDL |
|---|---|---|---|---|
| 自然语言→澄清 | ✅ clarify 真 | ✅ intent_router | ⚠️ **clarification loop 当前仅 README/spec 声称，未见源码** | ⚠️ 无用户澄清回路（intent 走 JSON 协议） |
| 架构/选型 | ✅ select + RAG | ⚠️ 部分 | ⚠️ 声称 | ⚠️ 依赖手工/AI skill |
| Schematic 生成 | ✅ S-expression 直写 | ✅ SKiDL→netlist | ⚠️ 声称 writer，未抓源码 | ✅ KiCad 真实工程 |
| Place/Routing | ⚠️ 自写/未闭环 | ✅ kipy 操作 | ⚠️ 声称 | ✅ KiCad + freerouting DSN/SES |
| DRC 闭环 | ❌ roadmap 未实现 | ⚠️ self_correction | ⚠️ 声称 | ✅ 结构化 DRC/ERC 门禁 |

→ 这一排是**业界收敛方向**，撞车是事实，不构成"AEDL 被超越"或因撞车而恐慌的理由。

### 2.2 验证纵深（差异化主战场）

| 能力 | CircuitBot | NeuroBoard | KiCadAI | AEDL |
|---|---|---|---|---|
| ERC 真跑 | ⚠️ 依赖本地 kicad-cli | ⚠️ `kicad-cli sch erc`（ipc_client） | ⚠️ 声称 | ✅ KiCad `erc --format json --severity-all` 结构化解析 |
| fail-closed 严格度 | ⚠️ error_end+repair 混合 | ❌ 失败→self_correction 继续 | ✅ 对 capability evidence 严格（已验证） | ✅ `_safe_gate`："malformed evidence must never become green" |
| 校验器有效性自证 | ❌ | ❌ | ⚠️ promotion evidence（对象是能力） | ✅ **semantic_fault_injection 常驻**，每次门禁注入故障必须全 caught |
| 独立验证（生成器不当裁判） | ⚠️ 白名单措辞无角色分离源码 | ❌ | ⚠️ 声称（未抓 reviewer 角色分离源码，kicad-ai 侧同理，见下） | ✅**跨视图机器解析 + 独立 contract**（intent/netlist/PCB/firmware 四视图、sha256 绑定） |
| 证据真源绑定 | ⚠️ 仅 state 字段 | ⚠️ AgentMemory 有限 | ✅ corpus SHA256（已验证） | ✅ 全程 sha256 绑定真源（ERC/DRC/BOM/CPL/Gerber/zip/manifest） |

### 2.3 NeuroBoard「事务回滚」——本轮已给出源码证据（不再空口断言）

- 文件 `ai_core/system/ipc_client.py`：
  - `begin_commit` / `push_commit`：只 `board.begin_commit()`/`board.push_commit()`，成功置位，**没有失败自动 abort/restore 整个 board 的封装**。
  - `_RollbackBatch`（异常时 `_safe_cancel_commit()` + `_restore_snapshot()`）：但 `_snapshot_positions()` **只保存/恢复 footprint 的 x/y/rotation**，**不覆盖新增 track/via/net/zone/ERC 状态**。
- `ai_core/agent/langgraph_loop.py`：`verification_node` 把 DRC/ERC/阻抗/电源结果写入 `drc_errors`；`after_verification` → `self_correction_node`（生成最小修复计划，含硬编码 fallback "Respace violating traces / Widen power traces"），是**局部重规划，不是事务回滚后重试**。
- `run_drc` / `run_erc`：仅 `kicad-cli pcb d rc / sch erc` 并按 returncode 返回 bool。

**判断**：NeuroBoard 的 "Atomic commits with rollback on DRC/ERC failure / Rollback+retry" 属**半实现/夸大**（信心：高）；范围限定为"footprint 位置级 snapshot＋局部修复"，不是完整 DRC/ERC 失败回滚。第一轮结论方向成立，本轮补全证据与边界。

### 2.4 SI/PDN（NeuroBoard，附证据）

- `ai_core/si/sparameter_analysis.py`：scikit-rf 分支用 `rf.media.Freespace`（无介质），且默认回退指标 `s11=-25dB / s21=-0.5dB / simulated=False`；`impedance.py` 用解析近似公式，非真实层叠建模 → **SI 为弱实现/回退模型**。
- `ai_core/power_integrity/pdn_simulator.py`：PySpice 可用时 = 电压源＋trace 电阻＋恒流负载的**简化 DC 模型**，非整板 PDN 提取；失败回退给出 mock 1% IR-drop。
- `ai_core/system/ipc_kicad.py` + `orchestrator.py`：`KiCadIPC` 是 `http://localhost:3000/api/tool` 的 HTTP→MCP 代理；`IPC_SOCKET_PATH="ipc:///C:/Users/Bibek/AppData/Local/Temp/kicad/api.sock"`、`scratchpad.py` 里 `sys.path.insert(0, r'C:\Users\Bibek\Documents\KiCad\10.0\...')` 硬编码作者机器 → 离开作者环境脆弱。
- `execute_engineering_script`：动态执行 LLM 生成的 Python，安全边界仅为**字符串黑名单＋30s timeout**，非沙箱。

---

## 3. AEDL 候选可主张项（这一节必须是"单独证据 + 未发现等价实现"，而不是"没人有"）

**规则改写：** 每一项下方只写"**截至 2026-08-30 对所列公开源码的检查中，尚未发现等价实现**"，并注明该主张需要准备的证据与可证伪条件。凡缺少对等 competitor 检索的项，一律降级为"未完全核实前提下暂不夹带首创式主张"。

| AEDL 机制 | 实现证据（AEDL 侧，已验证） | 依判定语言的写法 | 待补的"他人也做了"的反证检索 |
|---|---|---|---|
| 常驻故障注入 gate（meta-verification） | `gates/semantic_fault_injection.py`：每次 run 注入 fault 夹具、必须全 caught 否则 fail | 截至检查日，在所审开源源码中尚未发现将"校验器有效性自证"做成常驻门禁的等价实现 | KiCadAI 的 promotion evidence 是同一方向，但对象是"能力证据"而非"校验器对故障的捕获率"，需在报告中讲清此差异 |
| 跨视图机器解析交叉绑定 | `gates/schematic_semantics.py`：独立 contract + intent/KiCad XML netlist/PCB pad/firmware 四视图、sha256 绑定、机器解析 XML/S-expression | 尚未发现等价实现；且该项以"机器解析＋独立合同"实现"生成器不当裁判"，与 kicad-ai 想用"fresh LLM reviewer"实现同目标——路径不同，需先定案 kicad-ai 是否真实才可写 | kicad-ai 的 findings ledger/waiver/done-gate 若源码证实存在，则是同目标临近物；未定案前不得写"我们独有" |
| 人工具名制造签发 + 撤销重签 | `gates/board_review_v1.json`（`manufacturing_release`＋reviewer＋时间戳；revocation 需 `human_resign_required`） | 尚未发现等价实现（四仓库均为自动 pass） | 需确认列表内无商业工具/其他开源把"制造签发"做成 fail-closed 人工闸 |
| 供应链 fail-closed | BOM freshness（7 天过期/未来日期即 fail）、正库存、TBD 拒绝、**零库存不自动换料** | 尚未发现等价实现 | CircuitBot 仅 RAG 选料、NeuroBoard 仅声称 JLC validation，未见"过期库存即 fail"等价物 |
| 经验学习门禁 | `gates/learning_gate.py` + `lessons_registry`（缺字段即 fail，三层晋级） | 尚未发现等价实现 | 未见任何竞品有事故回溯/经验升级机制 |

> 若进入 AIC 报告，措辞一律用上表"依判定语言的写法"，并配每格"反证检索"留痕。**任何"首创/领先/行业空白"字样禁止使用。**

---

## 4. 威胁排序（诚实版，含残量不确定）

- **KiCadAI（dshills）—— 值得升档但先别标"红"**：capability/evidence、frozen corpus、content-addressed 证据、fail-closed（capability 层）**是真代码**，这部分威胁真实存在。但"KiCad 生成／ERC-DRC／simulation/thermal/SOA／10 个 adversarial 夹具／clarification loop"本轮**未抓到源码调用链**，故不能对"它是完整 simulation-grounded 生成验证系统"盖章。**下一步动作＝继续深挖这些子系统的实现源码**（找 `internal/blocks/*`、`internal/verification`、`kicad-cli` subprocess 调用点、`go test` 可选夹具）。
- **kicad-ai（amcolex）—— 先定案后定级**：其"独立 reviewer 思想"正是你盯的"生成器不当裁判"。但我的工具连续两轮 404/未定位。**请你人工打开 URL 或贴 raw README**；若确有源码，我再派代理做源码级核实（findings ledger/waiver/done-gate/4-4 case 是否真实+可复现）。未定案前，既不写"不存在"也不写"已验证"。
- **CircuitBot—— 宏观撞车，验证偏弱**：LangGraph 流程与你未来画像接近；可研究其 clarify-first，但其 LLM judge 是否 hard gate 尚未源码确认。
- **NeuroBoard—— 主要威胁在演示层**：事务回滚已证为"位置级 snapshot＋局部修复"，SI/PDN 为简化/回退模型，不是验证对手。

---

## 5. 本轮元教训（供记入 development log）

本题之外，第一轮结论的失败本身就是素材：

> **"Even verification agents require verification."**

过程：并发子代理 + GitHub API + raw + CI + license，方法都对；但它在"把活仓库判成 404"和"两处把证据强度拉满"上翻车——与团队此前 LDO 事故同型：**推理方向可能正确，claim calibration 崩了**。

落库建议（需人工审核后列入 log）：
- 现象：审计子代理对"未能通过工具访问"推成"仓库不存在（负面强结论）"；对"部分证据支持"推成"护栏/凌驾（正面强结论）"。
- 防控：① 负面结论（不存在/是假的/没有）必须给可复现证据（文件路径+函数+失败分支），否则写"未核实"；② 能力领先结论一律用"截至检查中，尚未发现等价实现"并配反证检索；③ 工具抓不到 ≠ 事实不存在，需人工/二源交叉确认。
- 回归测试（若建）：对"声称存在但拉取失败的资源"，强制走 human ground-truth gate。

---

## 6. 附：仍未决 / 需人工确认项

1. **kicad-ai 仓库是否真实存在且公开**——请浏览器打开 `github.com/amcolex/kicad-ai`，或贴 raw README。若确认存在，我重开源码级核实。
2. KiCadAI 的 KiCad 生成/ERC-DRC/sim/thermal/adversarial corpus/clarification loop 是否有真实源码调用链——需继续深挖，本轮仅到"文档/readiness 声称"。
3. CircuitBot 的 LLM judge 是否 hard fail-closed 门禁——source-level 未完全确认。
4. 若要把上述经验写进 `gates/lessons_registry_v1.json`：必须补全 `root_cause/escaped_controls/failure_evidence/failing_fixtures/regression_tests/fault_injection_proof` 等必填字段，否则 learning_gate 会失败；**我未擅自改动，等人工指示。**

（本文件为工作分析，未提交、未进 Evidence/合规台账，供人工核阅。）