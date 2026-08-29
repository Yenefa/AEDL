# HANDOFF — project-027-autonomous-hardware-agent

> **AI 接手强制前置**：在任何实质修改前，完整阅读根目录 `AGENTS.md`、
> `docs/compliance/AEDL_开发记录与AI使用规范_v1.0.md` 与 `docs/compliance/README.md`；
> 收尾时按真实工作更新对应台账；AI 新增记录默认保持 `PENDING_HUMAN_REVIEW`，
> 只有团队成员实际审核后才能改为 `HUMAN_REVIEWED` 或 `ACCEPTED`。

## 当前状态（2026-08-29）

M2 板级闭环完成：功能布局重建（J1 贴边/去耦靠 IC/SHT30 隔热）→ freerouting 重布线 →
DRC 从 5 条违规收敛到 0 → 8 项板级评审基于机器实测证据全部签发（`manufacturing_release=true`，
具名评审人 sca331613-commits）→ delivery 全套重新导出 → 一键 runner **7/7 门禁 PASS，
exit 0**。项目已获下单授权，等待嘉立创回件做 C 级实测。

一键命令：

```powershell
py -3 gates\run_gates.py
```

| 门禁 | 结果 | 事实 |
| --- | --- | --- |
| G1 | PASS | 17 个物理料位；BOM 字段完整，但库存快照为历史数据，下单前需复核 |
| G2 | PASS | KiCad 10.0.5 ERC 0 error；`#FLG01` 驱动 +5V，`#FLG02` 驱动 GND |
| G4 | PASS | KiCad DRC 0 violation / 0 unconnected（2026-08-29 从 5 条收敛） |
| G10 | PASS | BOM/POS 17 个引用一致，Gerber ZIP 26 条目；2026-08-29 由当前 PCB 重新导出 |
| BOARD_REVIEW | **PASS** | 8/8 pass（`tools/board_review.py` 机器实测），`manufacturing_release=true` |

板级评审实测要点：J1 courtyard 前沿距板边 0.03mm（贴边安装）；U1 天线端朝板边、
7.5mm 净空圈无器件；去耦最差 2.8mm（上限 8.0mm）；USB 差分 skew 0.87mm（要求 <=1.0mm）；
SHT30 距最近热源 35.2mm（要求 >=10mm）；丝印 17/17 覆盖。证据：
`notes/m2-evidence-reset/generated/board_review_auto.json`。

## 关键文件

- `AGENTS.md`：项目技术约束与 AEDL AI 开发强制收尾规则；所有 AI 的第一入口。
- `docs/compliance/AEDL_开发记录与AI使用规范_v1.0.md`：项目内 AEDL 规范真源。
- `docs/compliance/README.md`：台账路由、适用起点和历史回填边界。
- `gates/gate_core.py`：只消费结构化证据，缺字段、空 sheet、未知 severity 均失败关闭。
- `gates/run_gates.py`：一键运行 KiCad ERC/DRC 并生成 manifest；不信任 KiCad 单独退出码。
- `gates/bom/bom_v1.json`：唯一 BOM 真源；`delivery/bom.csv` 由脚本生成。
- `gates/board_review_v1.json`：8 项板级评审签发记录（manufacturing_release=true）。
- `tools/board_review.py`：从 PCB 静态几何机器测量 8 项评审证据。
- `tools/build_board.py`：intent 建板 + 功能布局覆盖表 + J1 舌片手工扇出（USB 差分对 0.4/0.2 小过孔逃逸）。
- `docs/M2板级工程评审.md`：8 项评审结果、DRC 收敛记录与证据边界。

## 2026-08-29 布线收敛记录（DRC 5 → 0）

1. 板级最小过孔 0.6→0.4/0.2（舌片 0.5mm 节距走廊放不下 0.6 过孔，与 `.kicad_pro` 同步）。
2. CC2 过孔移位 (46.15,3.1)→(46.45,3.15)，与 USB_DP 净距 0.10→0.48mm。
3. USB_DM B.Cu 深回廊悬空段改为两小过孔直连。
4. 删除 freerouting 残留单层连接过孔（+3V3 冗余）。
5. USB_DM 加 0.55mm 蛇形凸包，差分 skew 1.97→0.87mm；铺铜重灌。

## 下一步验收顺序

1. 嘉立创下单：`delivery/jlc_gerber_upload.zip` + `bom.csv` + `pos.csv`；下单前复核 LCSC 库存。
2. 回件后执行 C 级实测：上电、功耗、BLE 距离、温湿度读数精度、USB 眼图、瞬态、24/168 小时稳定性；结果回写 `gates/board_review_v1.json` 的实物验证备注。
3. 恢复并实测可用的原理图生成器后，重新生成当前含 `PWR_FLAG` 的 M2 `ops_gen.json`；当前 `ops` gate 仍是 M1 历史代理证据，不能当作本版重放证明。
4. 可插拔架构演进：板级评审/布线收敛逻辑沉淀为可复用协议（当前为 tools 内脚本，最终形态插件化）。

## 约束与边界

- 任何 AI 的实质贡献都必须写入 `docs/compliance/AI_USAGE_LOG.md`；涉及新第三方资源、关键决策或效果证据时同步更新对应台账。AI 不得自行标记人工审核通过。
- 禁止把 Wokwi/host 单测/DRC 0 描述成实体硬件验证；C 级实测回件前不得宣称"板子能工作"。
- 8 项评审结论基于机器几何实测 + DRC 0 违规签发；朝向/阻抗/气流/瞬态的实物复核待回件。
- 禁止把当前板描述成已经完成的通用自主硬件 Agent；本轮只验证一块 ESP32-C3/SHT30 载板和门禁闭环。
- 本分支未 push；下单动作由项目负责人执行。
