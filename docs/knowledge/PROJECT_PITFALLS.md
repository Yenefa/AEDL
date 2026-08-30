# project-027 专属踩坑经验

本文件只记录本项目已经发生、能够复现、并已有防复发控制的经验。它不是泛化成功宣言；在晋级条件满足前，规则仍属于 project-027。

## PIT-20260830-001：错误意图的多层一致性不等于电路语义正确

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

### 永久控制

- 数据手册语义写入独立合同 `gates/contracts/m2_schematic_contract_v1.json`，不得从 intent 自动生成。
- `gates/schematic_semantics.py` 同时读取 intent、KiCad XML 网表、PCB pad-net 和固件常量。
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
