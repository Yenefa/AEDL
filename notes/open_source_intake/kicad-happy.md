# kicad-happy 开源项目 Intake 报告（六步协议）

> Repo: https://github.com/aklofas/kicad-happy
> Commit SHA: `d5fd7da585fce7e59329b68fd065384216d4ff0a`（浅克隆，2026-09-01；正式提交时应移入 `notes/open_source_intake/_kicad_happy_repo/`，随 .gitignore 排除，不进 AEDL 仓库）
> Date Reviewed: 2026-09-01
> License: MIT（`LICENSE` 文件全文核对：`MIT License / Copyright (c) 2025 Andrew Klofas`；GitHub API `license.key=mit` 与文件内容一致，无 NeuroBoard 式双声明矛盾）
> 审查方法：`git clone --depth 1 -c core.longpaths=true` 后逐文件阅读源码；对照既有 `notes/three-repos-review-2026-09-01.md` 第一轮结论；对两个核心分析器实际执行，输入为 AEDL 自己的 `src/hardware/m2-board/m2_board.kicad_sch` 与 `m2_board.kicad_pcb`（真实数据，非合成测试用例）。
> 证据标记：`已验证`（源码直接读到或实际运行得到）/ `未核实`（本轮未查证，不据此断言真或假）。

---

## STEP 1 - CLAIM（它声称做了什么）

README/仓库描述声称：

| 声称 | 分类 | 源码核对结果 |
|---|---|---|
| 面向 AI coding agent 的确定性 Python 分析工具包 + skill 包（非 LLM agent runtime） | Implemented | `已验证`：`skills/` 下全部脚本为纯 Python，无 agent 编排框架依赖 |
| KiCad S-expression 通用解析器 | Implemented | `已验证`：`skills/kicad/scripts/sexp_parser.py`（233 行全文阅读），处理转义、多种 KiCad 版本 flag/property 格式差异 |
| 原理图分析：组件/网络/引脚连接/BOM/子电路检测 | Implemented | `已验证`：`analyze_schematic.py`（10271 行，docstring + 全部 ~85 个函数签名核对，结构上超出声称范围，见 STEP 2） |
| PCB 分析：board/layers/footprint/routing/vias/zones/DFM + connectivity graph | Implemented | `已验证`：`analyze_pcb.py`（7145 行，docstring + 全部 ~75 个函数签名核对，同样超出声称范围） |
| 统一 findings 格式（severity/confidence/evidence source/fix type） | Implemented | `已验证`：`finding_schema.py`（714 行全文阅读），且比声称更丰富——含强类型校验、`trust_level` 自评分机制（详见 STEP 2/4） |
| EMC 预合规、SPICE 子电路仿真（依赖外部 ngspice） | Implemented | `未核实`：本轮未打开 `skills/emc/`、`skills/spice/` 源码，仅确认目录存在 |
| Datasheet 抽取（"no ML"式营销措辞，若存在） | **Implemented，但措辞与实现矛盾** | `已验证`：`datasheet_verify.py` 第 7 行原话 "Requires datasheets/extracted/ cache populated by the **LLM extraction**"——文件自己承认依赖 LLM，任何"无 ML"的对外措辞都与源码矛盾（见 STEP 3） |
| 供应商集成（digikey/element14/jlcpcb/lcsc/mouser/pcbway） | Implemented | `已验证`：目录结构存在；`未核实`：具体实现深度，三仓库综述文档完全未提及这块范围，本轮是新发现 |

无明显"README 声称、源码不存在"的项目；相反，实际实现范围比综述文档描述的更广（详见 STEP 2）。

---

## STEP 2 - SOURCE（源码实际上做了什么）

- **语言/框架**：纯 Python，无重型第三方依赖——`kicad_utils.py` 仅 `import math, os, re`（标准库）；`sexp_parser.py`、`finding_schema.py` 同样零外部依赖。**可直接用 `py -3` 运行，不需要安装 KiCad 本体**（已验证：本轮全程未装 KiCad，两个核心分析器均正常运行）。
- **`sexp_parser.py`**（`已验证` 全文）：
  - 分词 + 递归下降解析，处理 KiCad 的 `{brace_escape}` 转义序列。
  - `get_property()` 专门处理 KiCad 9+ 引入的 `(property private "Name" "Value")` 格式（`private` 关键字导致 name/value 索引整体偏移一位）——说明作者跟踪过 KiCad 版本间的格式演进，不是只测过一个版本。
  - `has_flag()` 兼容三种 flag 表示法（legacy 裸 token / post-20241004 `(flag yes)` / `(flag no)`）。
  - 代码内有 `KH-101` 式内部编号引用（边界检查修复），说明背后有 issue 追踪习惯。
- **`finding_schema.py`**（`已验证` 全文，超出综述文档描述范围）：
  - `make_finding()` 对 `severity`/`confidence`/`evidence_source` 三个字段强校验，非法值直接 `raise ValueError`——与 AEDL 自己 "malformed evidence must never become green" 的 fail-closed 哲学同源。
  - `confidence` 三档：`deterministic` / `heuristic` / `datasheet-backed`。
  - `compute_trust_summary()`：把一批 finding 聚合成整体 `trust_level`（high/mixed/low），**AEDL 现在没有等价机制**——`gates/run_gates.py` 是二元 PASS/FAIL，没有"这个结论有几分把握"的分级（详见 STEP 4）。
  - `sort_findings()` 做确定性排序，注释明确目的是"让 baseline snapshot 保持字节级一致"——与 AEDL 的哈希绑定思路同向。
- **`analyze_schematic.py` / `analyze_pcb.py`**（`已验证` 结构层：docstring + 全部函数签名；**未逐行读完整 17416 行**，体量过大，采用抽样验证）：
  - 覆盖范围远超综述文档的"EMC/SPICE 分层工具"描述：总线协议探测（I2C/SPI/UART/SDIO/CAN/RS485）、跨电源域信号检测、legacy 原理图格式兼容、层级原理图支持（`parse_all_sheets`）、tombstoning 风险、微带阻抗计算、回流路径连续性、载流能力分析、~50 个电路模式自动检测器（`finding_schema.Det` 类枚举：晶振电路、去耦电容、上拉电阻、保护器件、总线协议、RF 匹配、BMS 系统等）。
  - `Det` 类的检测器广度是本轮最重要的结构性发现——kicad-happy **不需要人预先写规则**就能自动识别常见电路模式，这与 AEDL 现有的"人工写清单"模式（见下）是根本不同的机制（详见 STEP 5）。
- **实际执行结果**（`已验证`，对 AEDL 真实硬件跑出的数据）：
  - `analyze_schematic.py` 对 `m2_board.kicad_sch`：exit 0，21 findings（2 error / 2 warning / 17 info），`trust_level: mixed`。
  - `analyze_pcb.py` 对 `m2_board.kicad_pcb`：exit 0，13 findings（1 error / 5 warning / 7 info），`trust_level: high`。
  - 具体 finding 见 STEP 3/5。

---

## STEP 3 - FAILURE（它最烂的地方）

按 AEDL 视角，从重到轻：

1. **"无 ML"式措辞与源码矛盾（若该措辞存在于对外材料）**：`datasheet_verify.py` 自己的说明第 7 行写明依赖 LLM extraction cache。这不是本工具的 bug，是**对外宣传口径与源码不一致**的典型案例——三仓库综述文档已预判此点，本轮用源码原文实锤。
2. **MPN 覆盖率检查对 AEDL 工作流是假阳性**：`audit_sourcing_gate`（SS-001）报"0/14 unique parts 有 MPN"，但 AEDL 的选型数据存在 `gates/bom/`、`datasheet_manifest.json`，**不写进 `.kicad_sch` 文件本身**。工具只读原理图文件，看不到 AEDL 的真实 BOM 状态，直接拿来跑会产生系统性假阳性——不是工具的缺陷，是**集成方式不对会产生的错误结论**，Adapt 时必须先接上 AEDL 自己的 BOM 数据源，不能只喂原始 `.kicad_sch`。
3. **~50 个自动检测器的 confidence 分布以 heuristic 为主**：实测跑 M2 板：schematic 侧 21 条 finding 里 10 条 `heuristic`、11 条 `deterministic`、**0 条 `datasheet-backed`**。AEDL 自己 `gates/schematic_semantics.py` 的每条规则都要求绑定具体数据手册 URL（`source_ids` 字段强制非空）。kicad-happy 的检测器多数是"工程常识启发式"，不是"逐条数据手册核实"，评价证据等级比 AEDL 现有标准低一档（详见 STEP 4/5，这不是缺陷，是需要如实标注的证据等级差异）。
4. **两个核心分析器体量过大，本轮未逐行读完**：`analyze_schematic.py`（10271 行）、`analyze_pcb.py`（7145 行）只做了结构层验证（docstring + 函数签名）与实际运行验证，未做逐函数正确性审计。这是本报告自身的限制，不是项目的缺陷，如实记录以避免过度断言。
5. **EMC/SPICE 子系统本轮完全未核实**：`skills/emc/`、`skills/spice/` 只确认目录存在，源码内容 `未核实`。

---

## STEP 4 - REUSABLE（哪些能力可以合法复用）

| 能力 | 复用方式 | 依据 |
|---|---|---|
| **`sexp_parser.py` 的 S-expression 解析器** | **Adapt**（直接复用/借鉴，别重写） | 233 行、零依赖、处理了多版本 KiCad 格式差异，AEDL 若做 KiCad 自动化解析，这是现成的干净实现 |
| **`finding_schema.py` 的强校验 finding 结构**（severity/confidence/evidence_source 枚举 + `raise` on invalid） | **Adapt** | 与 AEDL fail-closed 哲学同源，可直接作为 AEDL 统一 findings 格式的参考实现（AEDL 现有 `run_gates` 的 `errors[]` 是裸字符串，没有结构） |
| **`compute_trust_summary()` 的分级信任评分概念**（deterministic/heuristic/datasheet-backed 三档 + 聚合 trust_level） | **Adapt**（借思想重实现） | AEDL 现在是二元 PASS/FAIL，没有"这次判定有几分把握"的中间态；三档信任分级思想值得吸收，具体实现按 AEDL 自己的证据分级标准重写 |
| **~50 个 `Det.*` 电路模式自动检测器**（基准点、环宽、测试点覆盖、上拉电阻缺失、ESD/TVS 保护等） | **Adapt，但降级为"候选提示池"而非权威门禁** | 实测已证明能在 AEDL 自己的板子上找到 `board_review.py` 完全没覆盖的项（基准点、环宽、测试点，见 STEP 5）；但 confidence 以 heuristic 为主，不满足 AEDL 现有门禁的"datasheet-backed"标准，Adapt 定位应是"提醒人工复核"而非直接拦截 |
| **`audit_sourcing_gate` 的"MPN 覆盖率不足即阻断"门禁概念** | **Idea Only** | 跟 AEDL 已有的供应链 fail-closed 机制（`gates/refresh_bom_stock.py` 等，检查库存新鲜度/TBD 拒绝）方向相近但不等价——AEDL 查的是"库存数据新不新鲜"，这个查的是"MPN 填没填"；概念上属于同族但不是同一机制，Idea Only 即可，不需要照搬实现 |
| **`datasheet_verify.py` 的 LLM 抽取 -> cache -> 确定性 verify 混合架构** | **Idea Only** | 架构模式（LLM 做抽取、确定性代码做核验）值得参考，但 AEDL 现有 datasheet 处理路径未评估是否需要类似缓存层 |
| **供应商集成 skills（digikey/element14/jlcpcb/lcsc/mouser/pcbway）** | `未核实`（不下判断） | 本轮只看到目录存在，没有读实现深度，不能仓促判 Adapt/Reject——AEDL 自己有 `jlcpcb-mcp` 相关工具链（见 HANDOFF 记录），需要单独立项比较，超出本次 intake 范围 |

**License 义务**：MIT，Copyright (c) 2025 Andrew Klofas，允许商用/修改/再分发，需保留版权声明。若直接 Adapt 代码（如 `sexp_parser.py`），需在 `THIRD_PARTY.md` 登记 SHA + MIT 声明保留；借思想（`Det.*` 检测器设计、trust_level 概念）不构成衍生作品（法律细节 `TO_VERIFY`，非法律意见）。

---

## STEP 5 - AEDL TRANSFORM（接入后语义变化）

**本轮最重要的结构性结论**：kicad-happy 与 AEDL 现有两个自研模块**不是竞争关系，是互补关系**——机制根本不同：

```text
AEDL gates/schematic_semantics.py（契约校验器）
  人工先写 JSON 契约（哪个引脚该接什么、绑定具体数据手册 URL）
  -> 核对 intent/网表/PCB/固件四份独立视图是否与契约一致
  -> 契约里没写的检查项，天然查不到

kicad-happy analyze_schematic.py / analyze_pcb.py（自动模式识别器）
  ~50 个 Det.* 检测器基于工程常识自动识别电路模式
  -> 不需要人预先想到、预先写规则
  -> 但 confidence 以 heuristic 为主，不到 AEDL 的 datasheet-backed 标准
```

**实测证据**（对 AEDL 自己的 M2 板子跑出来的真实结果，非假设）：

| kicad-happy 发现 | AEDL `tools/board_review.py`（8 项：USB_EDGE/ESP_ANTENNA/GROUND_RETURN/DECOUPLING/USB_ROUTING/SHT30_THERMAL/PROTECTION/ASSEMBLY）是否覆盖 | 结论 |
|---|---|---|
| FD-001：F.Cu 层无基准点，板上有细间距件 | 未覆盖 | **真空白**——8 项检查里没有等价项 |
| DFM-001/002：过孔环宽 0.1mm，低于 IPC Class 2 最低 0.125mm | 未覆盖（`GROUND_RETURN` 只数 via 数量，不查尺寸） | **真空白** |
| TE-001：测试点覆盖率 0/12（0%） | 未覆盖 | **真空白**（但 M2 尚在原型阶段，量产前再处理即可，不是当前阻塞项） |
| UC-002：VBUS 无 ESD/TVS 保护 | **已覆盖**——`PROTECTION` 检查原文写"USB 5V 直供 LDO 场景为建议项" | **交叉验证，非新发现**——两个独立工具各自得出同一结论 |
| SS-001：BOM MPN 覆盖率 0% | 不适用（AEDL 选型数据不存在 `.kicad_sch` 里） | **假阳性**，见 STEP 3 |
| PU-001：U2 的 ALERT 引脚缺上拉电阻 | 未覆盖 | 未覆盖，但需人工电路复核确认是否真的需要（可能有片内上拉），不能仅凭这条 finding 直接判定为缺陷 |

**AEDL 由此获得**：一个可以自动扫出"人没想到该查什么"的候选发现层，弥补 `board_review.py` 这种手写清单模式的天然盲区（基准点/环宽/测试点这三条完全在现有 8 项检查之外）。

**AEDL 不获得（诚实边界）**：kicad-happy 的检测结果不能直接顶替 AEDL 现有门禁的裁决地位——它的 heuristic-confidence 发现需要人工复核后才能升级为"契约规则"或"board_review 检查项"，不能自动 fail-closed 拦截制造放行。

---

## STEP 6 - VERIFY（怎么证明吃进去以后更好）

**已完成的验证**（`已验证`，本轮实测，区别于 circuitbot.md 报告阶段的"计划中验证"）：

1. 两个核心分析器（`analyze_schematic.py`、`analyze_pcb.py`）对 AEDL 真实 M2 板文件（非合成测试用例）实际运行，均 exit 0，产出结构化 JSON（分别 11110 行 / 若干行），无崩溃、无异常。
2. 交叉核对 3 条具体 finding（FD-001/DFM-001-002/TE-001）against AEDL 现有 `tools/board_review.py` 全部 8 项检查逐条比对，确认为真空白而非重复劳动。
3. 交叉核对 1 条 finding（UC-002）与 AEDL 现有 `PROTECTION` 检查独立收敛到同一结论，验证了"两个独立工具在同一处发现同一风险"这一更强的证据形式。
4. "无 ML"措辞矛盾：源码原文直接引用，非转述。

**尚待完成的验证**（若正式 Adapt，需要在实装 Issue 里做）：

1. Regression fixture：把 FD-001/DFM-001-002/TE-001 三类检查改写成 AEDL 自己的门禁规则后，构造"有基准点/环宽合规/有测试点"的正例板和"没有"的反例板，验证新规则能正确区分。
2. Before/After：M2 板下单前，实际按 FD-001 建议补基准点、按 DFM-001/002 核实嘉立创工艺能力（本轮未能核实到具体数值，见附注），对比修复前后的 `board_review_auto.json`。
3. Fault injection：仿照 `gates/semantic_fault_injection.py` 的常驻故障注入模式，把"故意去掉基准点"这类场景纳入回归夹具。
4. 供应商集成 skills（digikey/element14/jlcpcb/lcsc/mouser/pcbway）需要单独一轮 SOURCE 级核实，本报告未覆盖（见 STEP 4 的 `未核实` 标注）。

---

## 附注：嘉立创工艺能力核实未完成

DFM-001/002（环宽 0.1mm）的严重程度依赖嘉立创的实际工艺能力表（是否有更高精度工艺档位支持 0.1mm 环宽）。本轮尝试通过浏览器核实 JLCPCB 官网具体数值，因页面渲染/滚动定位问题未能取得确切数字，**如实标注为未核实**，不据 IPC 通用标准直接断言这是嘉立创的阻塞项。建议后续由人工直接登录嘉立创下单页面核对，或联系客服确认。

---

## 附：与竞品/三仓库综述文档的对照

本报告与 `notes/three-repos-review-2026-09-01.md` 无冲突，且补齐/校准了以下几点：

- 综述文档判"kicad-happy 对 AEDL 工程价值最高"——`已验证` 成立，且本轮发现其实际实现范围（总线协议探测、~50 个电路模式检测器、供应商集成 skills）比综述文档描述的更广。
- 综述文档标记"夸大需剥掉：datasheet 抽取'no ML'（实际依赖 LLM extraction）"——`已验证` 属实，源码原文实锤（见 STEP 3 第 1 条）。
- 综述文档未提及供应商集成 skills（digikey/element14/jlcpcb/lcsc/mouser/pcbway）范围——本报告新发现，`未核实`具体实现，建议单独立项评估，可能与 AEDL 自己的 `jlcpcb-mcp` 工具链有重叠或互补关系。
- 本报告新增（综述文档未做）：对 AEDL 真实 M2 板硬件文件的实际执行验证，产出 34 条具体 finding，并逐条与 AEDL 现有 `tools/board_review.py`/`gates/schematic_semantics.py` 做了真实碰撞分析，而非仅基于代码阅读的推测性判断。

（本文件为内部工作分析，按 AGENTS.md 留痕规则，关联 AI-20260902-006，Issue `Yenefa/AEDL#3`，PENDING_HUMAN_REVIEW。Review Bundle: 见随 PR 附带的 bundle_manifest。）
