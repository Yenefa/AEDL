# THIRD_PARTY — 开源项目 Intake 版第三方复用清单

> 用途：按 `notes/open_source_intake/AEDL_开源项目吸收与再设计策略_2026-08-30.md` §8 要求建立的第三方依赖台账，记录**已实际复用**的外部项目（思想借鉴 / 引用边界 / 红线）。
> 与 `docs/compliance/THIRD_PARTY_RESOURCES.md`（RES-001..007，全量台账）的关系：本文件是 intake 视角的**复用边界**清单，聚焦"从开源项目吸收了什么、边界在哪"；许可证全量登记仍以 RES 台账为准。
> 状态：DRAFT，`PENDING_HUMAN_REVIEW`。License 以各 intake 报告源码核对为准；法律细节 `TO_VERIFY`，非法律意见。
> 铁律（策略文档 §12）：**成熟的轮子，直接用；有缺陷的轮子，拆开修；真正没有的机制，集中火力自己造。** 主动承认成熟基础设施来自哪里，然后把真正属于 AEDL 的系统贡献讲清楚。

---

## 1. 复用总表

| 项目 | Commit / Version | License | 使用内容 | AEDL 修改 | 是否再分发 | 融合角色 | 备注 |
|---|---|---|---|---|---|---|---|
| **CircuitBot**（HiwarkhedePrasad） | `ff9b003`（2026-08-16） | MIT（源码核对） | **思想借鉴**：5 维澄清框架（mcu/sensor/power/connectivity/display）、每问 2-4 选项 + "No preference"、circuit_type 三分类、IC-based 电路剥离误加 MCU | 借思想重实现为 requirements_contract（语义反转：fail-open → fail-closed）；**零代码复制** | NO | CORE（第 10 门禁思想来源） | 其 clarify 的 fail-open 缺陷（5 分钟超时继续、No preference 静默丢弃、零测试）是 AEDL 重新设计的直接依据（`circuitbot.md` STEP 3/5） |
| **KiCad MCP**（mixelpixx 深审 + 家族） | `aa53d52`（v2.7.0，2026-08-20） | MIT（源码核对） | **引用边界**：FTS5 连字符 MPN 字面化查询修复 → Adapt 为 AEDL 器件匹配对抗测试；ERC/DRC 错误语义分级 → 交叉验证 AEDL 封装；JLCPCB 三通道器件发现 → Direct Reuse 候选（M3+，**仅 discovery，不做 gating**） | 本轮零代码复制；FTS5 教训落 AEDL 测试计划 | NO | SUPPORT（工具层参考） | 判决体系不外包：工具可借，`run_drc` 的 raw JSON → AEDL 解析器 → 语义门禁 → 故障注入 → 制造决策（`kicad-mcp.md` STEP 5） |
| **KiCadAI**（dshills） | `4f18765`（2026-08-24，depth=1） | MIT（源码核对） | **引用边界**：生成前能力评估（supported/experimental/unsupported）→ Adapt 机制形态；工具错误四分类 → Adapt；Checkpoint 单调性 → Adapt；RecordedProvider 录制回放 → Adapt（近期可落地）；MNA 仿真引擎 → Direct Reuse 候选（M3+，当前不需要） | 本轮零代码复制，仅机制借鉴 | NO | SUPPORT（机制模板） | 其 clarification 是单向拒绝非问答回路，反向验证 AEDL"对话式合同"差异化价值（`kicadai.md` STEP 5） |
| **Konnect**（KiCad MCP 后继项目） | 未接触 | **AGPL-3.0**（README 声明） | **禁止吸收（红线）** | 不适用 | NO | BLOCKED | **AGPL 传染性，未过许可证审查并获人类明确授权前零接触**；AEDL 若吸收 KiCad MCP 能力只能走 MIT 版或独立实现（`kicad-mcp.md` STEP 4） |
| **NeuroBoard**（Be-bibek） | 未开始 intake | MIT（碰撞分析记录） | 未复用（Phase 4 未开始） | 不适用 | NO | NONE | 碰撞分析已核：IPC/UI/事件流可吃，事务回滚为位置级快照（半实现）；intake 未开始 |
| **kicad-ai**（amcolex） | 未核实 | 未核实 | 未引用 | 不适用 | NO | NONE | 仓库真实性待人工浏览器定案（2026-08-31 WebFetch 得 GitHub 404 渲染页）；定案前不引用其任何描述 |

---

## 2. 逐项边界说明

### 2.1 CircuitBot（思想借鉴，MIT）

- **License**：MIT（`circuitbot.md` 源码核对，Copyright (c) 2026 CircuitBot contributors；允许商用、修改、再分发，需保留版权声明）。
- **是否修改上游源码**：否（零代码复制，仅借思想）。
- **是否再分发**：否。
- **复用内容**：5 维澄清框架、问答选项交互、"No preference" 处理、circuit_type 三分类、IC-based 电路剥离误加 MCU。
- **语义反转（STEP 5）**：CircuitBot 的 clarify 是 fail-open（超时继续 / 静默丢弃 / 结果仅存 state / 零测试）；AEDL 重新定义为 requirements_contract——blocking 未答即 STOP、No preference 显式记录为 nonblocking assumption、产物落盘 `requirements_contract_v1.json`、SHA256 自哈希 + intent 引用校验。
- **义务**：借思想不构成衍生作品（法律细节 `TO_VERIFY`）；若未来 Adapt 其代码片段（如关键词表），需在本表登记（含 SHA、MIT 声明保留）。

### 2.2 KiCad MCP（引用边界，MIT）

- **License**：mixelpixx 本体 MIT（Copyright (c) 2024 mixelpixx）。
- **是否修改上游源码**：否（本轮零代码复制）。
- **是否再分发**：否。
- **复用内容**：FTS5 连字符 MPN 修复模式（Adapt 为 AEDL 器件匹配对抗测试，含 `SHT41-AD1F-R2` 风格与 M2 U3 真实料号对 `ME6211C33M5G` vs `ME6211C33R5G`）；ERC/DRC 错误语义分级（退出码非 0 = 发现违规 ≠ 工具失败）作为 AEDL 封装交叉验证清单；JLCPCB 三通道器件发现（Direct Reuse 候选，M3+，仅 discovery）。
- **边界**：器件数据双通道分离——discovery 通道可借，gating 通道必须走 AEDL 自有 `refresh_bom_stock.py`（实时精确码 + 零库存失败关闭），两通道数据永不相混。
- **家族警示**：同名项目至少 6 个活跃实现 + 多个 fork，能力/许可证/维护状态差异极大（bunnyf 许可证含混、Seeed 曾无 license 文件）；吸收任何家族成员必须先单独走完整六步 intake。

### 2.3 KiCadAI（引用边界，MIT）

- **License**：MIT（Copyright (c) 2026 Davin Hills）。
- **是否修改上游源码**：否（本轮零代码复制，仅机制借鉴）。
- **是否再分发**：否。
- **复用内容**：生成前能力评估机制形态（三态 + 证据挂链 + 拒绝不突变）、工具错误四分类、Checkpoint 单调性、RecordedProvider 录制回放测试模式。
- **边界**：AEDL 保持"生成后门禁"主轴，新增"生成前能力预检"层（M3 实装时）；判决体系不外包——吸收的是"能力边界显式化"的机制形态，不是接其代码当 AEDL 门禁。
- **校准记录**：碰撞分析第一轮"KiCadAI 生成链路未见源码"经本地克隆复核判为误判（writer/ERC-DRC/MNA 仿真源码俱在）；威胁等级从"值得升档但先别标红"升为"验证纪律最强"（`kicadai.md` 附节）。

### 2.4 Konnect（AGPL 红线，禁止吸收）

- **License**：**AGPL-3.0**（README 头部声明：个人与开源免费，商业需授权）。
- **是否修改上游源码**：不适用（零接触）。
- **是否再分发**：否。
- **红线**：AGPL 传染性，未过许可证审查并获人类明确授权前，AEDL 任何代码/设计借鉴均不得来源于 Konnect。AEDL 若吸收 KiCad MCP 能力，只能走 MIT 版（mixelpixx）或独立实现。
- **依据**：`notes/open_source_intake/kicad-mcp.md` STEP 4（"禁止接触"）+ README 头部声明。

---

## 3. 与全量台账的关系

- 本文件只登记**已实际复用**的开源项目复用边界；`docs/compliance/THIRD_PARTY_RESOURCES.md`（RES-001..007）登记全量第三方资源（含 akcli-kicad RES-005、jlcpcb CLI RES-006、数据手册 RES-007、GitHub RES-004、治理规范 RES-001/003 等）。
- 融合角色定义（AGENTS.md §5）：CORE = 直接参与核心功能或"AI+开源"主张；SUPPORT = 运行/构建/验证所需；DEV_ONLY = 普通开发工具不得包装成融合创新。
- 本表 CORE 仅 CircuitBot（第 10 门禁思想来源）；KiCad MCP / KiCadAI 为 SUPPORT（机制/工具层参考）；Konnect 为 BLOCKED（红线）。

---

## 4. 维护规则

- 任何新增/实质改变外部资源使用时，同步更新本表与 `docs/compliance/THIRD_PARTY_RESOURCES.md`（AGENTS.md §5）。
- 任何"Direct Reuse 候选"落地为实际代码复用前，必须先完成：许可证复核 → 本表登记（含 commit SHA、License 声明保留）→ 人工审核。
- 不猜 License；"GitHub Public" ≠ 可随意复制使用；不把外部代码伪装成 AEDL 自研（AGENTS.md §5 规则）。
