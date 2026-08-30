# KiCad MCP 开源项目家族 Intake 报告（六步协议）

> 研究对象：KiCad MCP 生态（**项目家族，非单一仓库**——GitHub 上多个同名/近名实现）
> 深审代表：mixelpixx/KiCAD-MCP-Server（策略文档 §3.2 能力清单与其重合度最高）
> Commit SHA: `aa53d52c2e37a13cb3574a6e0acf2c728b4d6bfb`（本地克隆 `notes/open_source_intake/_kicad_mcp_repo/`，浅克隆 depth=1；v2.7.0，2026-08-20 "chore: release v2.7.0"）
> Date Reviewed: 2026-08-31
> License: MIT（LICENSE 文件全文核对，Copyright (c) 2024 mixelpixx）
> **后继项目警示**：README 头部声明其下一代 **Konnect**（Rust、原生 KiCad 10 插件、171 工具、含设计评审审计与制造管线）为 **AGPL-3.0**（个人与开源免费，商业需授权）。"This Python/TypeScript server remains fully open (MIT) and maintained."——AEDL 若吸收 KiCad MCP 能力，只能走本 MIT 仓库或独立实现，**禁止吸收 Konnect 代码**（AGPL 传染性，未过 license 审查前零接触）。
> 审查方法：本地 git clone 后阅读源码（src/tools 25 个工具模块、python/commands 50+ 命令实现、kicad_api 三后端）+ 官方文档（TOOL_INVENTORY/KNOWN_ISSUES/JLCPCB 指南）；家族其余成员经公开资料调研（源码级 `未核实`，逐项标注）。
> 证据标记：`已验证`（源码直接读到）/ `未核实`（本轮未查证）/ `家族级`（来自家族成员公开资料，非本仓库源码）。

---

## STEP 1 - CLAIM（它们声称做了什么）

### 1.1 深审对象 mixelpixx/KiCAD-MCP-Server（README v2.7.0 原文声称）

| 声称 | 分类 | 源码核对结果 |
|---|---|---|
| 169 个工具、15 个分类、JSON Schema 校验 | Implemented | `已验证`：`src/tools/` 25 个模块 + `python/schemas/tool_schemas.py` 巨量 schema；仓库自带 `docs/TOOL_INVENTORY.md`（2.1.0 版自记 137 工具，注释"verifiziert via VS Code MCP Discovery Log"——作者用自己的 MCP 发现日志实测计数，计数随版本浮动） |
| 完整原理图工作流（27 工具 + 动态符号加载 ~10,000 符号） | Implemented | `已验证`：`schematic.ts`、`schematic-batch.ts`、`schematic-hierarchy.ts`、`schematic-layout.ts`、`library-symbol.ts`、`symbol-creator.ts` + `python/commands/` 对应实现（wire_manager、symbol_pins、schematic_lint 等） |
| Freerouting 自动布线集成（Java / Docker / Podman） | Implemented | `已验证`：`python/commands/freerouting.py`（DSN 导出 → `java -jar freerouting.jar` → SES 导入；命令 autoroute/export_dsn/import_ses/check_freerouting；文件头注明借鉴 morningfire-pcb-automation 的 freeroute_runner.py） |
| JLCPCB 元器件集成（2.5M+ 目录 + 实时价格/库存） | Implemented | `已验证`（实现存在）：三通道——`jlcpcb_parts.py`（SQLite+FTS5 本地快照，~60 万在库子集）、`jlcpcb.py`（OpenPlatform 官方 API，HMAC 认证）、`jlcsearch.py`（社区 jlcsearch.tscircuit.com 公共 API，免认证）。官方文档自认：搜索必须走本地快照（官方 API 无搜索端点），快照"可滞后数天到数周"，单品实时数据需 OpenPlatform 凭据，结果 `source` 字段标注 `"live-api"` vs `"local-db"` |
| DRC/ERC | Implemented | `已验证`：`run_drc`（`kicad-cli pcb drc --format json`，超时钳制 10-1800s）+ `_handle_run_erc`（`kicad-cli sch erc --format json`，KiCad 8/9 报告嵌套差异已处理，退出码非 0 视为"发现违规"而非错误，无输出才判工具失败） |
| Gerber/钻孔/IPC-2581/ODB++/IPC-D-356/GenCAD 导出 + BOM（CSV/XML/HTML/JSON） | Implemented | `已验证`：`kicad_interface.py` 各 `_handle_export_*`（每个都有 CLI 缺失即返回失败的守卫）+ `export.py` 的 `export_bom` 系列 |
| Eagle/PADS/Altium/CADSTAR 等 vendor PCB 导入 | Implemented | `已验证`：`pcb-import.ts` + `python/commands/pcb_import.py`（经 KiCad 10 原生 importer） |
| 自定义 symbol/footprint 创建与修复 | Implemented | `已验证`：`symbol-creator.ts`、`footprint.ts`、`set_symbol_pin_type.py`（带 dry-run 与 token 白名单校验）、`find_duplicate_symbols.py`、`symbol_repair.py` |
| 实时 KiCad UI 集成（IPC API） | **Experimental**（README 自标） | `已验证`（存在性）：`python/kicad_api/`（ipc_backend / swig_backend / factory 三后端） |
| "Comprehensive error handling and logging" | Implemented | `已验证`：`src/logger.ts`（按日文件 + 大小轮转 + best-effort 不破坏主流程） |

### 1.2 家族其余成员（公开资料，`家族级`，源码未逐个审）

| 仓库 | 定位 | 关键事实 |
|---|---|---|
| lamaalrajih/kicad-mcp | Python+FastMCP，**只读**分析 | 第三方分析称其 stalled maintenance、无任何编辑能力（来源：antonmadto/kicad-mcp 的 PLAN.md，下同） |
| Seeed-Studio/kicad-mcp-server | Python+FastMCP | 家族中 **pin 级网络追踪 + `detect_pin_conflicts`（pinmux 冲突检测）** 的来源；后端间优雅降级；该分析当时记录"repo 无 license 文件"——AEDL 引用前必须复核 license |
| blwfish/kicad-mcp | Python，MIT，448 commits | 17 工具全流程，agent-first 安装（AGENT-INSTALL.md/AGENTS.md）；布线用 FreeRouter v2.2.4+ |
| havamal-65/KiCad-MCP | Python，MIT，167 commits | 自称 110 工具/10 分类（README） |
| antonmadto/kicad-mcp | **纯计划阶段**（PLAN.md，2026-07-04） | 尚未实装；其 PLAN.md 对上述四个参考仓库做了利弊分析（本报告"家族级"结论多引自此，已交叉标注） |
| bunnyf/pcb-mcp | 许可证含混（MIT/GPLv3 冲突）+ 曾提交 secrets | 只借思想，零代码（antonmadto PLAN.md 记录）——AEDL 禁用 |
| ercbb/、7tobias/ 等 fork | mixelpixx 的 fork/import | 非主线上游，忽略 |

**策略文档 §3.2 能力清单与现实的映射结论**：清单是**家族能力并集**——"pinmux conflict detection"在 Seeed 版（本仓库 `未发现` pin conflict 相关代码，`已验证`为否定性检索）；"session/tool logging"在 mixelpixx 版（logger.ts）；其余条目（工程操作/原理图编辑/布局/布线/ERC/DRC/Gerber/BOM/CPL/自定义符号封装/JLC/LCSC/价格/库存/Freerouting/引脚级追踪/PCB 分析）mixelpixx 版基本齐备。

---

## STEP 2 - SOURCE（源码实际上做了什么）

- **架构**：TypeScript MCP server（MCP 2025-06-18 规范）+ Python KiCad 接口层（Node↔Python 桥）；KiCad 访问三后端：IPC API（实时 UI）/ SWIG pcbnew（无 UI）/ 文件直写，factory 按能力选择。
- **DRC 实现**（`python/commands/design_rules.py::run_drc`，`已验证`）：`kicad-cli pcb drc --format json --units mm`，解析 violations（type/severity/description/位置），统计 severity 计数，结果落盘 `<board>_drc_violations.json`（大结果集友好）；CLI 找不到 → `success:False` + 明确报错文本。
- **ERC 实现**（`python/commands/schematic_handlers.py::_handle_run_erc`，`已验证`）：`kicad-cli sch erc --format json`；KiCad 9 把 violations 嵌套在 `sheets[].violations` 的兼容处理；**退出码非 0 ≠ 工具失败**（违规是正常输出），无 JSON 产出才是真失败——错误语义分级正确。
- **Freerouting 集成**（`已验证`）：export_dsn → 外部路由器（java -jar，JAR 默认 `~/.kicad-mcp/freerouting.jar`，支持 Docker/Podman）→ import_ses 回写。与 AEDL 自用 freerouting 2.3.0 + DSN/SES 同构——AEDL 已有等价能力，此处无新增吸收价值。
- **JLCPCB 三通道**（`已验证`）：本地 SQLite+FTS5 快照搜索（含一个被诚实记录并修复的静默失败：带连字符的真实 MPN 如 `SHT41-AD1F-R2` 会被 FTS5 当列过滤/NOT 表达式解析导致搜索空结果——修复为逐词加引号前缀匹配）；OpenPlatform API 实时单品查询（HMAC 签名）；jlcsearch 公共 API 备选。
- **测试**：141 个 Python 测试文件 + 8 个 TS 测试文件（vitest）+ pre-commit（ruff/flake8/eslint/prettier）。
- **文档诚实度**：`docs/KNOWN_ISSUES.md` 主动披露真实缺陷——KiCad 9.0 层枚举 API 破坏（`LT_USER` AttributeError）、**SWIG 后端 zone filler 段错误**、SWIG 改动需手动 UI 重载（by design）。README 的版本日志逐条记录已修复的严重 bug（见 STEP 3）。

---

## STEP 3 - FAILURE（它们最烂的地方）

按 AEDL 视角，从重到轻：

1. **判决层整体缺席（by design，但 AEDL 必须清醒）**：这是纯工具层——DRC/ERC 原始结果直接回给 AI 客户端，无证据绑定、无哈希链、无 gate 语义、无"结果凭什么可信"的定义。策略文档 §3.3 的预判完全成立：**工具可复用，判决体系绝不能外包**。
2. **历史上有文件损坏级 bug（已修但暴露工程风险）**（README v2.6/v2.7 发布注记，`已验证`为仓库自述）：
   - `add_symbol_property` 每次调用丢一个闭括号、可能把 unit symbol 拼进顶层兄弟节点（#362）；
   - S-expr 转义不对称：含 `\"` 的属性值过不了 round-trip（KiCad 自带 419 个符号文件受影响）（#336/#324）；
   - v2.6：`BOARD.Remove()` 把 C++ 所有权交给 Python 导致 SWIG 状态进程级损坏——删任何东西只能成功一次，之后连纯读都崩（已改 `BOARD.Delete()`）；
   - v2.7：Node-Python 桥无请求 ID，超时后下一条命令被上一条的迟到结果静默顶替，此后全部响应错位（#373）。
   - 教训：**AI 直接编辑用户工程文件的工具层，其静默损坏风险是真实发生过的**，不是理论担忧。AEDL 的 M2 用生成-验证-哈希链整链重导的方式规避了这类问题。
3. **"优雅降级"语义与 AEDL fail-closed 相斥**：JLCPCB 工具在 DB 不可用时"degrade gracefully"（#264）；本地快照库存可滞后数天到数周。**AEDL 若借用其器件检索做发现（discovery）可以，做库存门禁（gating）绝对不行**——AEDL 的 refresh_bom_stock.py 精确码实时查询 + 零库存失败关闭不得被替换。
4. **双运行时桥复杂度**：Node+Python 两进程桥是其已知事故来源（响应错位 bug 即此处）；antonmadto 分析也将其列为"accidental complexity"。AEDL 纯 Python 单进程路线无此问题。
5. **家族碎片化 + 名称混淆**：同名项目至少 6 个活跃实现 + 多个 fork，能力/许可证/维护状态差异极大（bunnyf 许可证含混、Seeed 曾无 license 文件、lamaalrajih 停滞）。任何人说"用 KiCad MCP"都必须先问"哪一个"。
6. **IPC 后端实验性**：README 自标 experimental；SWIG 后端有段错误史与 UI 重载问题。生产级稳定性依赖后端选择。
7. **家族级数据的可信度**：本报告对家族成员（除 mixelpixx 外）的结论来自其 README 与第三方 PLAN.md，`家族级`标记，未逐一克隆核verify。若未来 AEDL 决定吸收某个家族成员（如 Seeed 的 pinmux 冲突检测），必须先对该仓库单独走完整六步。

---

## STEP 4 - REUSABLE（哪些能力可以合法复用）

| 能力 | 复用方式 | 依据 |
|---|---|---|
| **FTS5 连字符 MPN 字面化查询修复**（逐词加引号前缀匹配） | **Adapt（近期可落地）** | AEDL 的 BOM/料号匹配是同类问题域：`SHT41-AD1F-R2` 这类 MPN 在各种文本匹配里都会踩连字符/大小写/分隔符坑。其修复模式（ quoting + 前缀归一化）+ 其教训（静默空结果曾长期存活）值得直接吸收进 AEDL 的器件匹配测试 |
| **ERC/DRC 的错误语义分级**（退出码非 0 = 发现违规 ≠ 工具失败；无输出 = 工具失败） | **Adapt** | AEDL 的 kicad-cli 封装已有等价纪律（结构化 JSON 解析 + 失败关闭），此分级法可作为交叉验证 AEDL 实现完整性的对照清单 |
| **JLCPCB 三通道器件发现**（快照搜索 + OpenPlatform 实时 + 社区 API） | **Direct Reuse 候选（M3+，仅 discovery）** | MIT。AEDL 若做 NL→选料建议，其本地快照搜索是好起点；**仅用于候选发现，库存/价格门禁仍走 AEDL 自有 refresh_bom_stock 实时精确码通道** |
| **按日轮转 + best-effort 日志**（logger.ts） | Idea Only | AEDL 已有 run_manifest 证据链，日志用途不同（运维 vs 证据），不引入 |
| **kicad:// 资源 URI / 工具分类路由** | Idea Only | AEDL 非常驻 MCP 服务，暂无消费场景（P2 前端另议） |
| **SWIG/IPC/文件三后端 factory** | **暂不引入** | AEDL 当前以文件级操作 + CLI 验证为主轴（M2 全链已验证）；引入多后端会稀释确定性。若 M4+ 做交互式 UI 再评估 IPC 后端 |
| **Freerouting DSN/SES 封装** | **不需要** | AEDL 已有自己的 freerouting 集成（2.3.0 + `-mt 1` + 遥测拦截，HANDOFF 记录在案） |
| **Konnect（后继项目）** | **禁止接触** | AGPL-3.0；在完成许可证审查并获人类明确授权前，AEDL 任何代码/设计借鉴均不得来源于 Konnect |

**License 义务**：mixelpixx 本体 MIT（Copyright (c) 2024 mixelpixx）。若 M3+ Direct Reuse 其 JLCPCB 检索代码，需在 `docs/compliance/THIRD_PARTY_RESOURCES.md` 登记（commit SHA `aa53d52c`、MIT 声明保留、注明融合角色 SUPPORT）。本轮零代码复制。Seeed-Studio 的 `detect_pin_conflicts` 若未来吸收，必须先补该仓库的 license 核实（历史记录显示曾缺 LICENSE 文件）。

---

## STEP 5 - AEDL TRANSFORM（接入后语义变化）

核心转化（策略文档 §3.3 的落地版）：

```text
KiCad MCP 工具层（DRC/ERC/编辑/导出/器件发现，原始结果直回 AI）
        ↓ AEDL 重新定义
1. 边界不动摇：工具可借，判决体系 AEDL 自持——
   KiCad MCP run_drc() 的 raw JSON → AEDL structured parser
   → evidence binding（sha256 绑定到 board/manifest）
   → semantic gate（10 gate 体系）→ fault injection → manufacturing decision
2. 器件数据双通道分离：
   discovery 通道 = 可借 KiCad MCP 家族的 JLC 检索（快照/社区 API）
   gating 通道 = AEDL 自有 refresh_bom_stock.py（实时精确码 + 零库存失败关闭）
   两通道数据永不相混，gating 永不降级
3. 静默损坏防御吸收为设计原则：
   其 add_symbol_property 丢括号/S-expr 转义不对称/SWIG 所有权崩溃三类事故
   → AEDL 对一切"AI 写工程文件"的场景维持 M2 模式：
     生成到新文件 + 独立解析器验证 + round-trip 比对 + 哈希绑定后再生效
4. FTS5 教训直接落 AEDL 测试：
   为 BOM/料号匹配补"连字符 MPN/前缀/大小写"对抗性 fixture
```

**AEDL 由此获得**：器件发现层的现成候选（M3+ 可选）；一组来自真实事故的"AI 编辑工程文件"防御设计对照；料号文本匹配的对抗性测试用例灵感。

**AEDL 不获得**（诚实边界）：交互式 KiCad 会话能力（IPC 后端实验性且 AEDL 无此场景）；自动布线改进（AEDL 已用 freerouting，KiCad MCP 也只是包了同一个 freerouting）；任何判决/证据语义（本来就没有，这正是 AEDL 的位置）。

---

## STEP 6 - VERIFY（怎么证明吃进去以后更好）

1. **对 KiCad MCP 的既验事实可直接复测**（源码级 `已验证`，运行级待环境）：
   - DRC 工具在 kicad-cli 缺失时返回 `success:False` 而非空违规列表（源码 `kicad_cli_not_found_message()` 守卫已读）；
   - ERC 对"有违规"与"工具失败"返回不同错误类别。
2. **AEDL 侧立即可做的验证（本轮吸收的教训）**：
   - V1：为 AEDL 器件/料号匹配逻辑补对抗性测试——含连字符 MPN（`SHT41-AD1F-R2` 风格）、前缀相似（`ME6211C33M5G` vs `ME6211C33R5G`，M2 U3 换料事件的真实料号对）、大小写/分隔符变体——证明 AEDL 不会重演 KiCad MCP 记录过的"静默搜索空结果"。
   - V2：若 M3+ 引入其 JLC 检索做 discovery：构造"快照库有料但实时通道零库存"的 fixture，证明 AEDL 的 BOM gate 仍以实时通道 FAIL 关闭（discovery 数据不得污染 gating）。
   - V3：把 V1/V2 纳入 `gates/semantic_fault_injection.py` 常驻故障注入。
3. **Before/After**：M2 复盘——M2 的 U3 换料依赖 datasheet 人工核对 + 实时库存失败关闭；若当时有 discovery 通道，候选生成更快，但**决策链一字不变**（这正是"工具借、判决自持"的可验证形态）。
4. **证据**：本 intake 报告即研究证据；V1 属低成本高价值项，建议纳入下个 AEDL 迭代的测试计划（实装时再登记 EVID）。

---

## 附：与策略文档/碰撞分析的对照

- 策略文档 §3 预判"KiCad MCP 属于已有成熟工具层，不值得重复造轮子"——`已验证`成立，且需补充两点精度：① "KiCad MCP"是家族不是单仓库，吸收前必须点名具体成员并单独核 license（本报告深审 mixelpixx 版）；② 其后继 Konnect 已转 AGPL-3.0，"工具层直接复用"必须显式排除 Konnect。
- 策略文档 §3.3 "判决体系不能外包"——源码级确认：该家族全部成员均无证据绑定/gate 语义（其定位使然），AEDL 的差异化位置清晰。
- 碰撞分析未覆盖 KiCad MCP（其范围是 CircuitBot/NeuroBoard/kicad-ai/KiCadAI 四仓库）——本报告为首次源码级 intake，家族成员的威胁评估结论与碰撞分析无冲突。
- 策略文档能力清单中"pinmux conflict detection"一项经核对来自 Seeed-Studio 版（`家族级`），mixelpixx 版无此能力（`已验证`否定性检索）。

（本文件为内部工作分析，按 AGENTS.md 留痕规则，关联 AI-20260831-004，PENDING_HUMAN_REVIEW。）
