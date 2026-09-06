# OPEN_OUTPUTS — 准备对外复用的开放成果

> 用途：AIC「AI+开源」评分项「开放成果与复用价值」的证据资产。记录 AEDL 准备公开复用的协议、门禁代码、测试夹具、需求合同 schema、目检提示词。
> 素材来源：`AGENTS.md` §8.3（开放成果不是"仓库 Public"）、`docs/compliance/THIRD_PARTY_RESOURCES.md`（RES-001..007）、`docs/evidence/EVIDENCE_INDEX.md`、`notes/m2-evidence-reset/M2目检提示词-多模态AI.md`、`gates/` 与 `tests/` 实际代码。
> 状态：DRAFT，`PENDING_HUMAN_REVIEW`。许可证与再分发权凡未核实一律 `TO_VERIFY`；不把"GitHub 仓库是 public"本身当成开放成果。

---

## 0. 开放原则

- 只开放 AEDL **团队自主创作**的部分；第三方内容（KiCad 库、akcli、jlcpcb 数据、数据手册、被借鉴项目的代码）**不随项目再分发**，只给引用与安装方式。
- 每个成果标注：准备开放什么 / 团队自主创作边界 / 许可证（`TO_VERIFY` 未定）/ 哪些第三方内容不随项目再分发 / 最小安装与运行方式 / 外部用户如何复现最小 Demo / 已知限制 / 维护状态。
- 项目根目录**已有 `LICENSE`（Apache-2.0）**（2026-09-06 核实；本条原记载"当前无 LICENSE"为过期信息）。但下表各成果的许可证栏**保持 `TO_VERIFY` 不变**——仓库级 LICENSE 不自动等于每项成果的再分发权，各项仍需按第三方边界（RES-003）逐项核实后才能定稿。
- 仓库仍为 **private**（ADR-003，2026-09-06 以未认证请求实测确认：匿名访问返回 404）。公开化是独立决策，本文件只登记"准备开放"清单，**尚不构成"已开放成果"**。

---

## 1. 需求合同 Schema（requirements-contract.v1）

- **准备开放什么**：`requirements_contract_v1.json` 的 JSON Schema 与字段语义（`$schema: https://aedl.local/schemas/requirements-contract.v1.json`），以及配套的确定性校验规则 C1-C7（blocking 未答即 fail、No preference 显式记录、SHA256 自哈希、intent 单向绑定 + 语义哈希锁定）。
- **团队自主创作边界**：Schema 与校验语义为 AEDL 自研（设计稿 `notes/open_source_intake/requirements_contract_design_v1.md`；实现 `gates/requirements_contract.py`）。五维澄清框架**思想**借鉴自 CircuitBot（MIT `ff9b003`，`circuitbot.md` STEP 4），AEDL 重实现并扩展 formfactor/other 维度——不复制其代码。
- **许可证**：`TO_VERIFY`（项目 LICENSE 未定）。
- **不随项目再分发**：CircuitBot 源码与代码片段。
- **最小安装与运行**：`py -3 gates\requirements_contract.py` 的校验函数可直接调用；示例合同见 `gates/requirements/requirements_contract_v1.json`（M2 补录版，`author=retroactive`）。
- **外部用户如何复现最小 Demo**：构造一个含 blocking 问题但未作答的合同 JSON → 校验必须 FAIL；作答后 → PASS。回归入口 `tests/test_requirements_contract.py`（18/18）。
- **已知限制**：C6 forbidden 匹配当前为关键字级映射（`_FORBIDDEN_KEYWORD_MAP`），对间接载体无法穷举（代码注释与 intake 报告已披露）；`intent_binding` 的 `intent_semantic_sha256` 为 TASK-C 新增字段，M2 合同重签待人工审。
- **维护状态**：第 10 门禁已挂载 `gates/run_gates.py`；设计稿 4 个决策点（M2 追溯 A/B、过期阈值、C6 匹配方式、实装时机）待人工拍板。

## 2. 门禁代码（fail-closed 验证链）

- **准备开放什么**：`gates/run_gates.py`（10 门禁 runner）、`gates/gate_core.py`（结构化证据失败关闭）、`gates/semantic_fault_injection.py`（常驻故障注入）、`gates/schematic_semantics.py`（四视图交叉）、`gates/learning_gate.py`（经验门禁）、`gates/export_delivery.py`（manifest 哈希链）、`gates/refresh_bom_stock.py`（库存失败关闭）。
- **团队自主创作边界**：以上均为 AEDL 自研。被验证的工具层（KiCad `kicad-cli`、akcli-kicad RES-005、jlcpcb CLI RES-006、freerouting）是第三方，只作为外部依赖调用，不随项目再分发。
- **许可证**：`TO_VERIFY`。
- **不随项目再分发**：KiCad、akcli-kicad、jlcpcb CLI、freerouting 二进制与数据。
- **最小安装与运行**：`py -3 gates\run_gates.py`（需本机 KiCad 10.0.5 路径可读；`--skip-kicad` 可跳过工具层只跑证据门禁）。
  **全新机器必须先初始化 KiCad 全局库表**——headless `kicad-cli` 不会触发 GUI 首次启动时的库表生成，缺这一步 ERC 会报 39 条 `lib_symbol_issues` / `footprint_link_issues` 假警告（全为 warning，非 error，但外部用户无法据此判断是环境问题还是设计缺陷）：
  ```
  复制 <KiCad安装目录>/share/kicad/template/sym-lib-table
       <KiCad安装目录>/share/kicad/template/fp-lib-table
  到   %APPDATA%\kicad\10.0\
  ```
  版本必须锁 **10.0.5**（与 `delivery/manifest_v1.json` 的 `kicad_version` 一致）；winget 默认给 10.0.6，需 `--version 10.0.5 --exact` 显式指定。跨补丁版可能改变导出与哈希。
  实测记录见 `notes/m2-evidence-reset/independent-reproduction-20260906.md`（补库表后 ERC 39→2 warning，2 条与冻结证据逐条一致；DRC 0/0 一致）。
- **外部用户如何复现最小 Demo**：`py -3 -m unittest discover -s tests`（95/95，AI-20260831-002 记录）验证门禁自测；`notes/m2-evidence-reset/run_manifest.json` 为每次 run 的完整审计清单。
- **已知限制**：门禁验证的是静态/软件证据，不构成实体硬件验证（EVID-20260829-001/20260830-001 已知限制）。
- **维护状态**：活跃维护中；门禁集合断言 9→10 为预期变更（AI-20260831-002）。

## 3. 测试夹具（负向故障注入 + 历史快照隔离）

- **准备开放什么**：`tests/fixtures/schematic_semantics/fault_*.json`（5 个永久负向夹具，同时污染多个派生视图）、`good_observations.json`（基线）、`tests/fixtures/board_review_before_release.json`（签发前冻结夹具，验证历史证据失败关闭）。
- **团队自主创作边界**：夹具为 AEDL 自研，基于 PIT-20260830-001 事故模式构造。
- **许可证**：`TO_VERIFY`。
- **不随项目再分发**：无第三方内容（夹具全部自研）。
- **最小安装与运行**：`py -3 -m unittest tests.test_run_gates.RunGatesTests.test_historical_evidence_is_reported_as_blocked_not_green -v`（EVID-20260829-003）。
- **外部用户如何复现最小 Demo**：运行上述测试，观察"历史证据被报告为 blocked 而非 green"。
- **已知限制**：夹具覆盖的是已识别的缺陷模式；新缺陷模式需持续补充（依赖故障注入常驻机制）。
- **维护状态**：随事故经验增长（PIT 准入 7 项条件，`docs/knowledge/PROJECT_PITFALLS.md`）。

## 4. 目检提示词（多模态 AI 板级目检）

- **准备开放什么**：`notes/m2-evidence-reset/M2目检提示词-多模态AI.md`——打板前对 KiCad 渲染图做目检预筛的完整提示词，含 L1/L2/L3 难度分级与"AI 只报告像素事实、人对照网表终审"的分工铁律。
- **团队自主创作边界**：提示词为 AEDL 自研；其"版本注意"段落记录了渲染图过期事故教训（2026-08-31）。
- **许可证**：`TO_VERIFY`。
- **不随项目再分发**：渲染图 PNG 本身（含板卡设计内容，公开前需审计）。
- **最小安装与运行**：把「一、提示词」整段复制给多模态模型，连同两张渲染图一起发。
- **外部用户如何复现最小 Demo**：对任意 KiCad 板渲染 top/bottom 图，按提示词要求模型输出 L1/L2 观察清单（位号|观察|可疑否|置信度|说明）。
- **已知限制**：3D 渲染图有透视与阴影，丝印判读不清时需 2D SVG 参考；L3 项（J1 方向 vs D+/D- 映射、U1 天线净空）必须人 + datasheet/网表兜底，AI 只能弱参考。
- **维护状态**：随渲染图新鲜度门禁（TASK-R1，`validate_render_evidence`）配套维护。

## 5. 协议与接口契约（API / 证据 Schema）

- **准备开放什么**：`docs/api/requirements_api.md`（P2 前端接口契约 + mock，AI-20260831-003）；证据 Schema 族（`https://aedl.local/schemas/` 下的 requirements-contract.v1、requirements-contract-evidence.v1、requirements-proposal.v1、m2-ops-validation.v1、learning-gate-report.v1、schematic_semantics 报告 Schema、semantic_fault_injection 报告 Schema）。
- **团队自主创作边界**：接口契约与 Schema 为 AEDL 自研。
- **许可证**：`TO_VERIFY`。
- **不随项目再分发**：无第三方内容。
- **最小安装与运行**：`gates/requirements_runtime_server.py` 起来后联调真实 API 模式（当前 `NOT_RUN`——P2 前端 mock 模式已验证，真实 API 联调待 P1 定案 `intent_binding` 冲突后执行，AI-20260831-003）。
- **已知限制**：`requirements_api.md` 的 `intent_binding` 字段与 `requirements_contract.py` C4 存在契约冲突（P2 会话记录），定案后需同步。
- **维护状态**：P2 前端已交付（`web/`），接口契约待 P1 补全。

---

## 6. 开放成果总表

| 成果 | 类型 | 团队自主创作边界 | 第三方内容不随项目再分发 | 许可证 | 最小复现 | 已知限制 |
|---|---|---|---|---|---|---|
| requirements-contract.v1 Schema + C1-C7 | 协议/Schema | 自研（五维框架思想借鉴 CircuitBot，重实现） | CircuitBot 代码 | `TO_VERIFY` | 构造未答 blocking 合同 → FAIL | C6 关键字级匹配 |
| 10 门禁代码 | 门禁代码 | 自研 | KiCad/akcli/jlcpcb/freerouting | `TO_VERIFY` | `run_gates.py` + 95/95 单测 | 静态证据非实体验证 |
| 负向故障夹具 | 测试夹具 | 自研（基于 PIT-20260830-001） | 无 | `TO_VERIFY` | 历史证据 blocked 测试 | 覆盖已识别模式 |
| 目检提示词 | Prompt/Skill | 自研 | 渲染图 PNG | `TO_VERIFY` | 提示词 + 渲染图 | L3 项需人兜底 |
| API 契约 + 证据 Schema | 协议 | 自研 | 无 | `TO_VERIFY` | mock 已验证；真实 API `NOT_RUN` | intent_binding 契约冲突待定案 |

> 维护状态：全部 `PENDING_HUMAN_REVIEW`；项目 LICENSE 与公开化决策（ADR-003）完成后，再逐项确认最终开放方式与许可证。
