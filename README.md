# 单 Agent 自主嵌入式研发系统

> 📅 创建日期：2026-08-24
> 🔢 项目编号：project-027
> 🏷️ 状态：M2 完成（8/8 板级评审签发，7/7 门禁全绿 exit 0，授权嘉立创下单；回件实测待做）

## 概述

做一个单 Agent 自主嵌入式研发系统：用户只描述想做什么，Agent 自动完成技术调研、器件选型、电路设计、原理图、PCB、仿真、固件开发、调试和自动验证。本仓库当前以 ESP32-C3/SHT30 板为 M2 载体，重点验证可复现的门禁与证据链。当前 KiCad G2 ERC=0、G4 DRC=0/0、8 项板级评审基于机器实测证据全部签发（`manufacturing_release=true`），一键 runner exit 0，生产文件已授权嘉立创下单；实体板级验证（上电/BLE/温湿度精度/瞬态）待回件后执行。

## AI 开发必读

任何 AI Agent 在本仓库产生实质贡献前，必须完整读取根目录 `AGENTS.md`。该文件是
AEDL 当前 v1.4 Agent 执行层唯一规范；项目实时状态另见 `docs/HANDOFF.md`，合规台账按
`AGENTS.md` 的触发条件更新。`docs/compliance/AEDL_开发记录与AI使用规范_v1.0.md`
保留为历史基线与格式参考，不再作为与根 `AGENTS.md` 并列的当前执行规范。

## 技术栈

- Agent 底座：OpenCode / Claude Code（skills + MCP）
- EDA 自动化：KiCad 9/10 + freerouting（DSN/SES 循环）+ kicad-cli（ERC/DRC/Gerber/POS headless）+ pcbnew Python（建板/扇出/蛇形调谐）
- 电路仿真：ngspice（KiCad 内置）
- 固件与验证：ESP-IDF/PlatformIO/Zephyr + Wokwi CLI / Renode
- 器件数据：yaqwsx/jlcparts + jlcpcb-mcp（LCSC/JLCPCB 目录与实时库存）
- 交付物生成：python-docx（报告）、嘉立创 Gerber/BOM 规范

## 快速开始

```powershell
# 阅读调研报告（正式交付物为 Word）
docs\单Agent自主嵌入式研发系统可行性调研报告.docx
# 重新生成 Word
python tools\md2docx.py docs\report-draft.md "docs\单Agent自主嵌入式研发系统可行性调研报告.docx"
```

## 目录说明

| 目录      | 说明                                          |
| --------- | --------------------------------------------- |
| `src/`    | 硬件（m2-board 原理图/PCB/intent）与固件源码   |
| `docs/`   | 调研报告、HANDOFF.md、M2 测试报告、板级工程评审 |
| `docs/compliance/` | AEDL AI 使用规范、AI/第三方资源/决策/团队贡献台账 |
| `docs/evidence/` | 可验证主张与原始 evidence 的索引 |
| `notes/`  | 各里程碑证据（ERC/DRC/评审/manifest，机器生成）|
| `assets/` | 静态资源（架构图等）                          |
| `gates/`  | 失败关闭门禁（run_gates.py + gate_core.py + bom/board_review 真源）|
| `tools/`  | 建板/布线/评审工具（build_board、dsn_ses、board_review 等）+ md2docx |
| `delivery/` | 嘉立创下单包（Gerber ZIP + bom.csv + pos.csv）|

## 当前门禁与下一步

在仓库根目录运行：

```powershell
py -3 gates\run_gates.py
```

runner 会调用 KiCad 10.0.5、解析结构化 ERC/DRC JSON，并写入
`notes/m2-evidence-reset/run_manifest.json`。当前预期退出码 `0`：ERC=0、DRC=0/0、
BOM/POS/ZIP 结构检查、8 项板级评审（`manufacturing_release=true`）全部通过。
板级评审的机器实测证据由 `py -3 tools\board_review.py` 生成
（`notes/m2-evidence-reset/generated/board_review_auto.json`）。

下一步按顺序完成：

1. 嘉立创下单（`delivery/jlc_gerber_upload.zip` + `bom.csv` + `pos.csv`，2026-08-29 重新导出）。
2. 回件后执行 C 级实测：上电、功耗、BLE 距离、温湿度精度、USB 眼图、瞬态与 24/168 小时稳定性。

## 备注

大统领四项拍板（2026-08-24）：①先出完整调研报告；②KiCad 设计 + 嘉立创打板；③验证边界第一档 = 无实体板交付；④起步域 = MCU 最小系统 + 外设。
