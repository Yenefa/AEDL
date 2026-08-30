# project-027 → AEDL 优化系统

目标是把已证实的项目经验逐级转化为可复用能力，同时防止一次事故被过早包装成“通用自主硬件 Agent 已完成”。

## 三层状态

### 1. 项目专属（project-local）

事故已在本项目发生，具有原始失败证据、负向夹具和项目门禁。此时规则只约束 project-027。

### 2. 晋级候选（candidate）

项目内持续通过，故障注入稳定；规则的输入、输出、失败语义和证据边界已抽象为不依赖 M2 器件编号的协议。候选仍不能称为通用能力。

### 3. AEDL 可复用（promoted）

至少在另一个不同硬件载体上成功复用，且由人工审核确认没有把静态门禁当成实体验证，才能进入 AEDL 优化系统默认模板。

## 晋级门禁

每条 critical 经验必须在 `gates/lessons_registry_v1.json` 中拥有：

- `root_cause`：真实根因；
- `escaped_controls`：旧防线为什么失效；
- `failure_evidence`：事故发生时的原始证据；
- `failing_fixtures`：可永久重放的负向样本；
- `regression_tests`：先红后绿的测试入口；
- `fail_closed_controls`：实际阻断发布的代码或合同；
- `fault_injection_proof`：最新机器生成的捕获证明；
- `optimization.promotion_criteria`：从项目规则晋级的附加条件。

`gates/learning_gate.py` 对缺字段、未知值、丢失文件、哈希漂移、漏捕故障或伪造 proof 一律失败。

## 本次经验的后续优化方向

`PIT-20260830-001` 当前状态为 `project_validated`。在 project-027 内先完成：

1. 将语义合同接口从 M2 固定规则抽象为插件协议；
2. 将 KiCad 网表/PCB/固件观察器变成可注册适配器；
3. 把故障注入和经验登记变成新硬件项目模板；
4. 用第二块不同载板验证，而不是只在 ESP32-C3/SHT30 上自证；
5. 经人工审核后才把候选规则写入 AEDL 默认优化系统。

## 制造交付链扩展矩阵

本轮把“派生物彼此一致却没有独立绑定”的经验扩展到制造交付链。以下控制目前仍是 project-027 专属，不代表 AEDL 已完成通用制造插件：

| 事故类型 | 当前可执行控制 | 回归测试 | 晋级前还缺什么 |
| --- | --- | --- | --- |
| BOM/POS 一起陈旧 | intent、规范 BOM、交付 BOM、当前 PCB CPL 四方引用集相等；交付 CPL 与临时新导出逐字段相等 | `test_delivery_gate_rejects_stale_self_consistent_bom_and_pos`、`test_delivery_gate_rejects_cpl_that_differs_from_fresh_pcb_export` | 在另一块元件增删真实发生的载板上复用 |
| KiCad POS 单位与表头不符合 JLC CPL | 导出命令显式固定 mm/both/exclude-dnp；严格转换原生 KiCad 表头为 JLC 表头 | `test_commands_pin_production_layers_and_millimetre_cpl`、`test_current_jlc_cpl_has_strict_header_and_finite_mm_coordinates` | 抽象制造商格式适配器，并在另一种 EDA/制造商组合验证 |
| 旧 Gerber 目录混入非生产层 | 全新暂存目录、固定生产层、精确目录/job/ZIP 集合、原子发布 | `test_gerber_set_and_job_file_must_match_exact_production_files`、`test_zip_contains_only_the_validated_flat_gerber_set` | 在不同层叠或不同板厂文件合同上验证可配置性 |
| 库存快照被当成当前供应 | 精确料号查询、正库存、BOM 哈希绑定、时间绑定、七天自动过期；下单前同会话即时刷新 | `test_bom_freshness_gate_expires_after_seven_days`、`test_bom_stock_evidence_is_bound_to_the_canonical_bom`、`test_snapshot_updates_every_item_and_binds_metadata` | 定义低库存策略、替代料审核协议，并在第二项目验证 |
| 换料审核材料的方法论缺陷（PD÷压差冒充热限、推测值算成精确数、无证据的排他性主张） | 暂无机器控制——2026-08-30 由人工审核拦截；正确方法已固化为 ADR-005（θJA 结温法、版本交叉核对、主张纪律） | 无（未建） | 把热预算分析结构化为机器可校验合同（θJA/Tjmax/Ta/结温算式为必填字段），把主张范围检查纳入换料审核清单，并在下一次真实换料中验证 |

### 供应风险边界

当前机器快照显示 U3（LCSC C82942）装配库存已从 5 降为 0，最新精确查询为失败证据。这是 project-local 的明确供应阻断，不能写成“稳定供应”，也不能自动替换为相似型号。任何替代必须回到独立数据手册合同，并重新跑原理图语义、PCB、BOM/CPL/Gerber 与人工制造审核。2026-08-30 处置（AI-20260830-002）：U3 已按上述要求受控换料为 C235316（ME6211C33R5G，SOT-353，库存 3329），换料方案经项目负责人初审（CONDITIONAL APPROVE，三项方法论整改）后于同日采纳；全链重跑后仅余 board_review 人工重签与提交审核，状态 `PENDING_HUMAN_REVIEW`。

### 换料审核方法论教训（2026-08-30，人工审核拦截）

U3 换料首版审核材料暴露三类方法论缺陷，全部由项目负责人人工审核发现，现有机器门禁均无法覆盖（它们属于“分析方法正确性”而非“证据结构正确性”）：

1. **热分析方法错误**：用 "PD 标称值 ÷ 压差" 冒充热电流上限。正确方法是 Tj = Ta + (VIN−VOUT)×I×θJA 结温法，须引用 θJA/Tjmax/TOPR 并按工作温度分档核算（本次实算：θJA 210 vs 270°C/W → 同等结温预算持续电流约 -22%）。
2. **结论精度超出证据质量**：把未确认输入（SOT-23-5 "~300mW"，后证实为 SOT23-3 行的解析误读）算成精确结论 "-17%"。输入为约值时结论只能是区间或定性。
3. **无证据的过强主张**：“同一颗 die”（硅片同一性无 ordering 表证据，且非必证项）与“全系唯一候选”（未披露检索范围与排除理由）。正确表述：“已检索候选中唯一 pin-compatible 正库存方案”，附候选清单与逐项排除理由。

伴生发现：**数据手册版本差异必须交叉核对**——V20（LCSC 绑定 C235316 的版本）与 V24 家族版热额定不一致（SOT353 PD 250mW vs 450mW；V20 未列 SOT23-5 与 θJA）。处理：以绑定版为硬边界、家族版为旁证，差异 `TO_VERIFY` 并列入回件实测。

整改协议已固化为 ADR-005，约束后续所有替代料审核。**按本文件准入标准，本条目当前无可执行控制、无回归测试，不算完成经验积累**；晋级前置条件见上方矩阵行。派生固件约束：U3 避免持续 >147mA 负载（V20 保守边界）；回件实测清单增加“持续 WiFi 负载下 U3 温升”。

### 晋级判据补充

制造交付规则从 `project_validated` 升为 `candidate` 前，除既有语义故障注入外，还必须满足：

1. 所有制造商/EDA 格式差异由显式适配器或合同描述，不能把 M2/JLC 字段硬编码包装成通用协议；
2. 至少在第二块不同载板上真实触发元件增删、底层器件或层集合变化，证明陈旧快照与多余文件会被阻断；
3. 库存证据必须与规范 BOM 哈希绑定，并在实际下单操作前即时刷新；
4. 低库存替代料必须经过独立数据手册与人工审核，不能由库存查询自动决策；
5. 嘉立创预览方向和最终下单仍属于人工动作，自动门禁不得代替签发。

## 证据边界

优化系统管理的是设计过程、软件门禁和证据质量。它不能自动创造实体测试结果，也不能在人工未签发时把 `manufacturing_release` 改为 `true`。当前状态仍为 `manufacturing_release=false`，没有形成“可下单”结论。
