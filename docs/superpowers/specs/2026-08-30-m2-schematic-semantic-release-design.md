# M2 原理图语义门禁与制造放行修复设计

**状态：** 已获用户批准采用方案 B，等待书面规格复核后实施

**日期：** 2026-08-30

**范围：** AEDL 的 ESP32-C3-WROOM-02 / SHT30 M2 载板、制造门禁、项目专属经验系统

## 1. 问题与立即处置

当前 `manufacturing_release=true` 不能继续作为有效下单许可。现有设计至少包含以下已确认缺陷：

1. `USB_DP` 接到 ESP32-C3-WROOM-02 的 13 脚（GPIO18 / USB D-），`USB_DM` 接到 14 脚（GPIO19 / USB D+），USB 极性反接。
2. SHT30 的 2 脚 ADDR 被标记为未连接，但固件固定使用地址 `0x44`；Sensirion 要求 ADDR 接高或接低，不得悬空。
3. SHT30 的 6 脚 nRESET 直接接 3.3 V，不符合“未使用时悬空，或通过不小于 2 kΩ 的串联电阻接 VDD”的器件指导。
4. ESP32-C3 USB 线上没有建议的 22/33 Ω 串联电阻预留，EN 没有建议的 RC 上电延迟，GPIO9 BOOT 没有建议的外部上拉。
5. 当前 `ops` gate 消费 M1 历史代理，当前 M2 `ops_gen.json` 又不含新增的 `PWR_FLAG`，无法证明本版可重放。

在修复、重新生成证据并完成人工复核前：

- 禁止下单；
- 制造放行必须失败关闭；
- 现有 Gerber/BOM/POS 仅作为撤回版本留存，不能继续称为可下单版本；
- ERC 0、DRC 0、Wokwi、host 单测都不能替代原理图功能语义检查或实体板验证。

## 2. 根因与逃逸链

本事故不是单点手误，而是同源验证造成的共同模式失效：

1. 人工把数据手册管脚语义翻译成 `intent_v1.json` 时发生错误。
2. `akcli check --intent` 只验证“原理图是否忠实复制 intent”，没有验证 intent 是否忠实于官方数据手册。
3. KiCad ERC 只检查电气规则；交换两个双向 USB 管脚、把器件输入标记为 no-connect 都可能得到 ERC 0。
4. PCB DRC 只检查连接和几何；只要错误网表被完整布通，DRC 仍可为 0。
5. `USB_ROUTING` 评审只测长度和 skew，没有检查连接器管脚到 MCU 功能管脚的极性映射，也没有检查差分阻抗与推荐端接。
6. 测试报告中的“SHT30 地址脚接地”没有从网表生成，导致文字结论与设计源真相分叉。
7. 制造放行把多项来自同一错误 intent 的绿色结果误当成独立证据，没有要求数据手册契约和故障注入证明门禁真能拦错。

因此，本次修复必须同时处理电路源文件和验证架构；只改接线会保留复发条件。

## 3. 已选方案

采用用户批准的方案 B：**完整硬件修复 + 独立语义门禁 + 项目经验优化系统**。

未采用：

- 只修 USB/SHT30：速度快，但同类错误仍可再次穿透。
- 整板推倒重建：当前布局和布线仍有可复用价值，代价与新增风险不成比例。

## 4. 目标与非目标

### 4.1 目标

- 让官方数据手册管脚语义成为独立、机器可消费的设计契约。
- 在修改生产源文件前，用失败测试证明当前 USB 极性和 SHT30 ADDR 问题可被门禁捕获。
- 修复 intent、原理图、PCB、BOM、POS、Gerber 和当前 ops 证据。
- 把关键建议电路纳入本版：USB 串联电阻、EN RC、GPIO9 上拉。
- 让制造放行在缺少语义证据、当前 ops 或人工复核时失败关闭。
- 将事故记录为项目专属经验，并把经验自动提升为可执行门禁和回归测试。

### 4.2 非目标

- 不宣称实体板已验证。
- 不在本任务实现通用任意器件数据手册解析器。
- 不在本任务完成最终插件框架。
- 不清理或提交现有 `spike/`、`spike_stage2/` 和其他未知未跟踪文件。
- 不进行嘉立创下单、付款或外部发布。

## 5. 硬件源修复

### 5.1 USB 2.0

修复后的连接必须满足：

- J1 A6/B6（D+）→ `USB_DP_CONN` → 新增 R7（22 Ω）→ `USB_DP` → U1.14（GPIO19 / USB D+）；
- J1 A7/B7（D-）→ `USB_DM_CONN` → 新增 R8（22 Ω）→ `USB_DM` → U1.13（GPIO18 / USB D-）。

R7/R8 使用 0603 封装并靠近 U1 放置。精确 MPN/LCSC 编码必须通过当前嘉立创装配库存核实后写入 BOM，禁止凭记忆填写。

板级 USB 评审必须把连接器侧和 MCU 侧两段网络连同串联电阻视为一条逻辑通道，检查：

- 极性映射；
- 两条逻辑通道总长度与 skew；
- 差分对连续参考平面；
- 过孔数量与成对回流；
- 90 Ω ±10% 阻抗作为制造参数/实体眼图待验证项，不用仅凭几何脚本宣称已证明。

### 5.2 SHT30

- U2.2 ADDR 直接接 GND，固定地址 `0x44`；
- U2.3 ALERT 未使用，保持 no-connect；
- U2.6 nRESET 未使用，改为 no-connect；
- U2.7 R、U2.8 VSS、U2.9 exposed pad 保持接 GND；
- 固件 `DEFAULT_ADDR` 必须与硬件契约中的 `0x44` 一致。

### 5.3 ESP32-C3 上电与启动

- 保留 R3=10 kΩ 的 EN 上拉；
- 新增 C5=1 µF，从 EN 到 GND，形成建议的 RC 上电延迟；
- 保留 SW1 从 EN 到 GND；
- 保留 SW2 从 GPIO9/BOOT 到 GND；
- 新增 R9=10 kΩ，从 BOOT/GPIO9 到 3.3 V。

C5、R7、R8、R9 的 MPN、LCSC 编码和装配状态在 BOM 更新任务中以实时库存为准。

## 6. 独立原理图语义门禁

### 6.1 数据手册契约

新增 `gates/contracts/m2_schematic_contract_v1.json`，至少包含：

- contract schema/version；
- 适用板卡和器件精确型号；
- 官方数据手册 URL、下载时间、文件 SHA-256，以及能够从文档确认的版本/发布日期；无法确认版本时不得启用对应制造放行规则；
- 关键管脚的器件功能语义；
- 必须连接、禁止连接和允许 no-connect 的规则；
- USB 逻辑通道端点；
- SHT30 地址与固件预期；
- EN/BOOT/USB 推荐外围作为本项目制造放行的必选规则；
- 每条规则的严重性；未知严重性必须失败关闭。

该契约由数据手册事实派生，但不由当前 intent 自动生成，避免共同模式失效。

### 6.2 三方比对

新增 `gates/schematic_semantics.py`，同时消费：

1. 数据手册契约；
2. `intent_v1.json`；
3. KiCad 原理图导出的结构化网表；
4. PCB pad-to-net 映射；
5. 固件中受硬件约束的地址常量。

门禁必须检查：

- intent 是否符合数据手册契约；
- 原理图是否符合 intent 与契约；
- PCB 是否符合原理图/intent 与契约；
- 固件地址是否符合硬件 strap；
- 缺文件、空报告、未知规则、解析失败、关键端点多接/少接均为 fail。

KiCad 网表导出失败时不能退化成只检查 intent。

### 6.3 故障注入回归

测试必须先在当前错误设计或等价 fixture 上出现预期失败，再实施修复。至少覆盖：

- USB D+/D- 交换；
- SHT30 ADDR 悬空；
- SHT30 ADDR 与固件地址不一致；
- nRESET 直接接 VDD；
- USB 串联电阻缺失；
- EN 电容缺失；
- GPIO9 上拉缺失；
- 原理图/PCB/intent 任一层端点漂移；
- 缺字段、空报告、未知 severity；
- gate 错用 M1 ops 代理。

## 7. ops 与生成可重放性

- 恢复并锁定实际可运行的 `akcli-kicad` 版本和解释器路径；
- 从修复后的 `intent_v1.json` 重新生成当前 M2 ops；
- `PWR_FLAG` 必须被正式生成或经过可重放、实际加载验证的受控补丁协议处理；
- 重新执行 strict-net intent check；
- 当前 ops 验证证据写入 M2 evidence 目录并包含 ops SHA-256、op count、源 intent SHA-256、工具版本与 errors；
- `run_gates.py` 禁止再读取 `notes/m1-evidence/ops_validate.json` 作为当前 M2 PASS。

## 8. 制造放行与证据状态

在实施开始时，保留历史具名评审内容，同时新增撤回记录并设置：

- `manufacturing_release=false`；
- `release_status=revoked_by_new_evidence`；
- 撤回时间、原因、关联事故 ID；
- `requires_human_resign=true`。

AI 不得把修复后状态自行改回人工批准。机器门禁全绿后，完整 runner 仍应因缺少重新人工签发而失败；用户重新审核并签发后才允许恢复制造放行。

重新签发前必须生成当前版本的：

- ERC JSON；
- DRC JSON；
- schematic semantics JSON；
- current M2 ops validation JSON；
- board review auto JSON；
- BOM/POS/Gerber；
- run manifest 与所有关键 SHA-256。

## 9. 项目专属经验与优化系统

### 9.1 人类可读经验库

新增 `docs/knowledge/PROJECT_PITFALLS.md`，采用追加式事故条目。每条至少包含：

- `PIT-YYYYMMDD-NNN`；
- 严重性与状态；
- 现象和发现阶段；
- 原始证据；
- 技术根因和流程根因；
- 逃逸了哪些门禁以及为什么；
- 修复；
- 防复发控制；
- 自动化测试/门禁/ADR/Evidence 链接；
- 是否已提升到项目优化系统。

第一条记录为本次“错误 intent 被同源门禁循环自证并逃逸到下单终检”的事故。

### 9.2 机器可执行提升注册表

新增 `gates/lessons_registry_v1.json` 和对应验证逻辑。严重事故只有同时满足以下条件才能标为 `promoted`：

- 根因已经记录；
- 至少一个真实失败 fixture；
- 至少一个自动回归测试；
- 至少一个 fail-closed gate/control；
- 证据路径存在；
- 控制能在故障注入时实际失败。

缺字段、未知状态、路径不存在或仅有文字教训时，经验提升门禁失败。

### 9.3 后续 Agent 入口

更新根 `AGENTS.md` 和 `docs/HANDOFF.md`：涉及硬件、门禁或制造放行的 Agent 在实质修改前必须读取项目专属踩坑库和已提升规则。新事故遵循：

```text
发现 → 保存失败证据 → 根因分析 → 写事故条目 → 写负向测试
→ 加入自动控制 → 故障注入验证 → promoted → 后续回归持续执行
```

## 10. 测试与验收

实施完成需满足：

1. 已观察到新增测试在旧设计上因正确原因失败。
2. 修复后所有 Python 单元/集成测试通过。
3. `schematic_semantics` 对 USB、SHT30、EN、BOOT 和固件地址全部 PASS。
4. KiCad 10.0.5 ERC 为 0 error，DRC 为 0 violation / 0 unconnected。
5. 当前 M2 ops 可由锁定工具重放，且不再使用 M1 代理证据。
6. BOM/POS 引用一致；Gerber 由修复后 PCB 重新导出；哈希全部刷新。
7. 自动板级评审重新运行，USB 长度计算覆盖串联电阻两侧。
8. 故障注入版本能被语义门禁阻断，不出现 false PASS。
9. `PIT-20260830-001` 已写入项目经验库并以真实测试和 gate 标为 promoted。
10. `manufacturing_release=false`、`requires_human_resign=true`，直到用户重新审核。

## 11. Git、合规与交付边界

- 在 `fix/m2-schematic-semantic-release` 分支实施；
- 只暂存本任务拥有的文件；不覆盖现有未知修改和未跟踪文件；
- 更新 `AI_USAGE_LOG.md`；
- 本次验证架构决策更新 `DECISIONS.md`；
- 新证据更新 `EVIDENCE_INDEX.md`；
- 新增或改变第三方工具/数据手册记录时更新 `THIRD_PARTY_RESOURCES.md`；
- 不在未获本轮授权时 push；
- 最终状态为 `PENDING_HUMAN_REVIEW`。
