# 单 Agent 自主嵌入式研发系统

> 📅 创建日期：2026-08-24
> 🔢 项目编号：project-027
> 🏷️ 状态：M2 证据重置中（G2 ERC 与板级评审阻断，禁止下单）

## 概述

做一个单 Agent 自主嵌入式研发系统：用户只描述想做什么，Agent 自动完成技术调研、器件选型、电路设计、原理图、PCB、仿真、固件开发、调试和自动验证。本仓库当前以 ESP32-C3/SHT30 板为 M2 载体，重点验证可复现的门禁与证据链；当前真实结果是 G2 ERC 仍有 2 个电源驱动错误，BOARD_REVIEW 未完成，因此不宣称生产文件已获下单授权。

## 技术栈

- Agent 底座：OpenCode / Claude Code（skills + MCP）
- EDA 自动化：KiCad 9/10 + akcli-kicad + KiSkill + freerouting + kicad-cli
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
| `src/`    | 系统源代码（M1 起填充）                       |
| `docs/`   | 调研报告（md 草稿 + docx 正式版）、HANDOFF.md |
| `notes/`  | 开发笔记、工具实测记录                        |
| `assets/` | 静态资源（架构图等）                          |
| `config/` | 项目配置（门禁定义等）                        |
| `tools/`  | md2docx 等内部工具                            |

## 当前门禁与下一步

在仓库根目录运行：

```powershell
py -3 gates\run_gates.py
```

runner 会调用 KiCad 10.0.5、解析结构化 ERC/DRC JSON，并写入
`notes/m2-evidence-reset/run_manifest.json`。当前预期退出码为 `1`：ERC 为 2 个
`power_pin_not_driven`，板级评审 `manufacturing_release=false`；BOM/POS/ZIP
结构检查和 DRC 0/0 仍会如实记录。

下一步必须按顺序完成：

1. 从 intent/原理图生成源补齐 +5V/GND 的电源驱动语义，重新跑 G2 ERC。
2. 由具名评审人完成 USB、天线、回流、去耦、走线、热、保护和装配 8 项评审。
3. 只有 G2 与 BOARD_REVIEW 同时通过，才复核 G10 并考虑嘉立创下单；回件后再做上电和长时间实测。

## 备注

大统领四项拍板（2026-08-24）：①先出完整调研报告；②KiCad 设计 + 嘉立创打板；③验证边界第一档 = 无实体板交付；④起步域 = MCU 最小系统 + 外设。
