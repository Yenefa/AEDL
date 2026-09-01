# project-027 专属踩坑经验

本文件只记录本项目已经发生、能够复现、并已有防复发控制的经验。它不是泛化成功宣言；在晋级条件满足前，规则仍属于 project-027。

## PIT-20260830-001：多层自洽与历史快照不等于独立正确性

### 事故

M2 在进入下单终检后才由独立数据手册复核发现：

- ESP32-C3-WROOM-02 的 USB D−/D+ 管脚身份被写反；
- SHT30 ADDR 悬空，但固件固定使用 `0x44`；
- SHT30 nRESET 被直接接到 3V3，而批准的修复策略要求未使用时明确 NC；
- ESP32-C3 缺少批准设计要求的 USB 22 Ω 串联电阻、EN 1 µF 电容和 GPIO9 10 kΩ 上拉。

原签发已撤销。旧版 ERC 0、DRC 0、8 项板级评审 PASS 只能作为“旧设计符合旧规则”的历史事实，不再构成制造放行证据。

### 为什么会拖到下单终检

根因不是单一管脚抄错，而是验证结构发生共同模式失效：

1. 人工先把错误语义写进 `intent_v1.json`。
2. akcli、原理图和 PCB 都从这个意图或其派生物继续工作。
3. `akcli check` 证明的是“原理图符合意图”，不是“意图符合数据手册”。
4. ERC/DRC 不理解 USB 信号身份、传感器地址选择或推荐启动网络。
5. USB 自动评审只量长度和 skew，没有核对 J1 D+ 最终是否到达 U1 USB D+。
6. “ADDR 已接地”只存在于人工报告文字，没有从网表反查，因此文字和真实连接可以分离。
7. 最终签发没有要求独立合同、负向夹具和故障注入证明。

于是，同一个错误在多份文件中高度一致，反而制造了“证据很多”的假象。这是循环举证，不能当作独立验证。

### 制造交付链的同类扩展事故（2026-08-30）

修复原理图语义并把物理料位从 17 个增加到 21 个后，真实运行一键门禁又暴露出同一类根因：旧交付物能彼此自洽，却没有绑定当前设计源、明确的制造格式合同或即时库存证据。

#### 1. BOM/POS 彼此一致，但同时落后于当前 intent

旧 G10 只比较 `gates/bom/bom_v1.json`、`delivery/bom.csv` 和 `delivery/pos.csv` 的引用集合。三者都停留在 17 个料位时可以一起 PASS，但当前 `intent_v1.json` 已有 21 个物理料位，新增的 R7、R8、R9、C5 会被整体漏掉。

永久控制是四方比对：当前 intent 的非虚拟引用、规范 BOM、交付 BOM、当前 PCB 重新导出的 CPL 必须完全相等；交付 CPL 还必须与本次门禁临时导出的 PCB placement 逐字段一致。回归入口：

- `tests/test_run_gates.py::RunGatesTests::test_delivery_gate_rejects_stale_self_consistent_bom_and_pos`
- `tests/test_run_gates.py::RunGatesTests::test_delivery_gate_rejects_cpl_that_differs_from_fresh_pcb_export`
- `tests/test_gate_core.py::GateCoreTests::test_current_delivery_refs_match_all_21_physical_parts`

#### 2. KiCad 10 原生 POS 不是可直接上传的 JLC CPL

KiCad 10.0.5 的 `pcb export pos` 默认单位是英寸；即使指定 CSV，原生表头仍是 `Ref,Val,Package,PosX,PosY,Rot,Side`，不是 JLC CPL 所需的 `Designator,Mid X,Mid Y,Rotation,Layer`。只看“有一个 pos.csv”无法证明单位和字段语义正确。

永久控制是显式固定 `--format csv --units mm --side both --exclude-dnp`，再通过严格转换器核对原生表头、有限数值和 `top/bottom` 枚举，输出 JLC 表头。转换器不擅自修正坐标或旋转；嘉立创预览中的器件方向仍须人工复核。回归入口：

- `tests/test_export_delivery.py::ExportDeliveryTests::test_commands_pin_production_layers_and_millimetre_cpl`
- `tests/test_gate_core.py::GateCoreTests::test_current_jlc_cpl_has_strict_header_and_finite_mm_coordinates`

#### 3. 复用旧 Gerber 目录再 `Compress-Archive *` 会把非生产层一起打包

旧目录保留过 Adhesive、Courtyard、Fab、Margin、User 等非生产层。若在这个目录上重新导出少数层，再用通配符压缩，旧文件不会自动消失，ZIP 仍可生成且看似完整，却混入不应交给板厂的内容。

永久控制是每次在全新暂存目录导出，显式固定 9 个生产层，加钻孔和 job 文件形成精确的 11 文件集合；目录、job 文件和最终平铺 ZIP 的条目集合必须完全相等，任何缺失或多余文件都失败，然后才原子发布。回归入口：

- `tests/test_export_delivery.py::ExportDeliveryTests::test_gerber_set_and_job_file_must_match_exact_production_files`
- `tests/test_export_delivery.py::ExportDeliveryTests::test_zip_contains_only_the_validated_flat_gerber_set`

#### 4. BOM 中的库存数字是快照，不是稳定供应承诺

库存必须由精确 LCSC 料号查询生成，并与规范 BOM 的 SHA-256、生成时间和每个料号的 MPN/厂商/封装/库别绑定。七天新鲜度门禁只是自动化上限；实际下单前仍须在同一操作会话即时刷新，不能把较早快照当作当前库存。

2026-08-30T06:30:42Z 的机器快照中，U3（C82942，ME6211C33M5G-N）装配库存仅为 5；同日 10:35:01Z 的下单前复查已降为 0，刷新器生成 `status=fail` 证据并保持规范 BOM 不被半更新。旧数字只能描述当时查询结果，不能称为“稳定供应”，也不能据此自动替换料号；替代料必须重新审查数据手册、引脚、封装和电气性能。后续处置（AI-20260830-002）：依据 ME6211C V20 数据手册核实 SOT-353 引脚序与 SOT-23-5 一致后，U3 受控换料为 C235316（ME6211C33R5G，SOT-353），全链同步并重跑门禁，状态 `PENDING_HUMAN_REVIEW`。

永久控制与回归入口：

- `tests/test_gate_core.py::GateCoreTests::test_bom_freshness_gate_expires_after_seven_days`
- `tests/test_gate_core.py::GateCoreTests::test_bom_stock_evidence_is_bound_to_the_canonical_bom`
- `tests/test_refresh_bom_stock.py::RefreshBomStockTests::test_exact_catalog_match_is_required_and_positive`
- `tests/test_refresh_bom_stock.py::RefreshBomStockTests::test_snapshot_updates_every_item_and_binds_metadata`
- `tests/test_refresh_bom_stock.py::RefreshBomStockTests::test_zero_stock_is_preserved_in_fail_closed_attempt_evidence`

以上四类仍属于设计文件、导出流程和目录查询证据。它们没有把 `manufacturing_release` 改为 `true`，也不证明实体板能够工作。

### 永久控制

- 数据手册语义写入独立合同 `gates/contracts/m2_schematic_contract_v1.json`，不得从 intent 自动生成。
- `gates/schematic_semantics.py` 同时读取 intent、KiCad XML 网表、PCB pad-net 和固件常量。
- `gates/run_gates.py` 将交付 BOM/CPL 与当前 intent 和当前 PCB 临时导出物交叉验证，不再接受内部自洽的旧快照。
- `gates/export_delivery.py` 在隔离暂存目录中固定单位、生产层和精确 ZIP 集合，并用 manifest 对源文件与交付物做哈希绑定。
- `gates/refresh_bom_stock.py` 只接受精确料号与正库存查询结果；BOM 快照和库存证据必须同时间、同哈希，下单前即时刷新。
- 缺文件、坏 JSON/XML、未知 rule/severity、空视图或字段不完整一律失败关闭。
- 五个永久负向夹具同时污染多个派生视图，验证独立合同仍能识别共同模式错误。
- `gates/learning_gate.py` 要求严重经验必须绑定失败证据、夹具、测试、控制和最新故障注入证明。
- 机器门禁全部通过后，`manufacturing_release` 仍须由人工重新签发；AI 不得自行签发。

### 证据边界

上述证据是设计文件和软件门禁证据。它不证明实体板可上电工作，不替代回件后的功耗、BLE、精度、USB 眼图、瞬态和 24/168 h 稳定性测试。

### 关联证据

- 事故基线：`notes/m2-semantic-repair/baseline_failure.json`
- 旧设计实跑：`notes/m2-semantic-repair/semantic_failure_before_repair.json`（0/5 PASS）
- 永久夹具：`tests/fixtures/schematic_semantics/fault_*.json`
- 结构化登记：`gates/lessons_registry_v1.json`
- 当前故障注入证明：`notes/m2-evidence-reset/generated/semantic_fault_injection_current.json`
- 当前库存快照：`notes/m2-evidence-reset/generated/bom_stock_current.json`
- 当前交付哈希清单：`delivery/manifest_v1.json`

## 新经验登记准入

新的 A/critical 经验只有同时满足以下条件才可加入本文件：

1. 有可定位的原始失败证据；
2. 根因与“为什么旧防线没拦住”分开写清；
3. 有最小失败夹具或可重放操作；
4. 有先红后绿的回归测试；
5. 有失败关闭的项目控制；
6. 有机器生成、可校验哈希的最新证明；
7. 明确软件、仿真与实体硬件证据边界。

只有文字总结、没有可执行控制的条目，不算完成经验积累。
