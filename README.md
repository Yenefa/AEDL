# 单 Agent 自主嵌入式研发系统

> 📅 创建日期：2026-08-24
> 🔢 项目编号：project-027
> 🏷️ 状态：进行中（调研报告阶段）

## 概述

做一个单 Agent 自主嵌入式研发系统：用户只描述想做什么，Agent 自动完成技术调研、器件选型、电路设计、原理图、PCB、仿真、固件开发、调试和自动验证，反复修改直到所有可执行检查通过，最后交付可直接打板的生产文件、完整代码和采购清单。

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

## 备注

大统领四项拍板（2026-08-24）：①先出完整调研报告；②KiCad 设计 + 嘉立创打板；③验证边界第一档 = 无实体板交付；④起步域 = MCU 最小系统 + 外设。
