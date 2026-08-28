# HANDOFF — project-027-autonomous-hardware-agent

## 当前状态（2026-08-28）

本轮完成了 M2 证据重置的确定性部分：canonical BOM、结构化 KiCad 解析、BOM/POS/ZIP 一致性检查、失败关闭 runner，以及 +5V/GND 的两个虚拟 `PWR_FLAG` 电源驱动语义。当前项目仍不是可下单状态。

一键命令：

```powershell
py -3 gates\run_gates.py
```

当前分支为 `master`（HEAD、manifest 的 run_id 请以实时命令查询）。一键 runner
仍返回 `1`，但原因只剩实体板评审未授权，不是 ERC/DRC/BOM/G10 结构问题。

| 门禁 | 结果 | 事实 |
| --- | --- | --- |
| G1 | PASS（结构） | 17 个物理料位；BOM 字段完整，但库存快照为历史数据，当前库存未知 |
| G2 | PASS | KiCad 10.0.5 ERC 0 error；`#FLG01` 驱动 +5V，`#FLG02` 驱动 GND |
| G4 | PASS | KiCad DRC 0 violation / 0 unconnected |
| G10 | PASS（结构） | BOM/POS 17 个引用一致，Gerber ZIP 26 个条目；未授权下单 |
| BOARD_REVIEW | **FAIL** | 8 项均 `needs_physical`，`manufacturing_release=false` |

历史固件编译、host 单测和 Wokwi 桩传感器证据仍在 `notes/m1-evidence/`，只能证明软件/仿真链，不能证明实体板可用。

## 关键文件

- `gates/gate_core.py`：只消费结构化证据，缺字段、空 sheet、未知 severity 均失败关闭。
- `gates/run_gates.py`：一键运行 KiCad ERC/DRC 并生成 manifest；不信任 KiCad 单独退出码。
- `gates/bom/bom_v1.json`：唯一 BOM 真源；`delivery/bom.csv` 由脚本生成。
- `gates/board_review_v1.json`：8 项板级评审的机器记录。
- `docs/M2板级工程评审.md`：阻断原因、关闭条件和后续顺序。

## 下一步验收顺序

1. 具名评审人完成 USB 外形/边缘、ESP 天线净空、地回流、去耦、USB 走线、SHT30 热、输入保护、装配方向 8 项检查。
2. 将每项真实证据写入评审记录，确认 `manufacturing_release=true` 后，才允许复核 G10 并考虑嘉立创下单。
3. 恢复并实测可用的原理图生成器后，重新生成当前含 `PWR_FLAG` 的 M2 `ops_gen.json`；当前 `ops` gate 仍是 M1 历史代理证据，不能当作本版重放证明。
4. 回件后执行上电、功耗、BLE 距离、温湿度读数和 24/168 小时稳定性测试；这些均是后续 C 级证据。

## 约束与边界

- 禁止把 Wokwi/host 单测/DRC 0 描述成实体硬件验证。
- 禁止把当前板描述成已经完成的通用自主硬件 Agent；本轮只验证一块 ESP32-C3/SHT30 载板和门禁闭环。
- 本分支未 push，未下单，未进行物理实验。
