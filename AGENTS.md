# AGENTS.md — project-027-autonomous-hardware-agent

## 项目一句话

单 Agent 自主嵌入式研发系统：用户一句话描述 → 自动完成调研/选型/电路/原理图/PCB/仿真/固件/验证 → 交付可打板生产文件+完整代码+BOM，证据分级标注。

## 技术栈

- Agent 底座：OpenCode / Claude Code（skills + MCP 集成层）
- EDA：KiCad 9/10（kicad-cli headless、ERC/DRC JSON、S-expression 文件直操作）
- 原理图自动化：akcli-kicad（PyPI）、KiSkill、kiutils 系
- PCB 布线：freerouting（DSN/SES 循环）
- 仿真：ngspice（KiCad 内置）、akcli sim 断言
- 固件：ESP-IDF / PlatformIO / Zephyr，arm-none-eabi 工具链，Unity/Ceedling 单测
- 行为验证：Wokwi CLI（ESP32 全家，含 MCP 接口）、Renode（STM32 系，Robot Framework + 覆盖率）
- 器件数据：yaqwsx/jlcparts 目录 + jlcpcb-mcp / jlcpcb(PyPI) 实时库存查询；官方 API 待申请
- 打板渠道：嘉立创 JLCPCB（Gerber/BOM/坐标文件人工或 API 下单）

## 构建命令

```powershell
# 报告再生成（md 草稿 → docx）
python tools\md2docx.py docs\report-draft.md "docs\单Agent自主嵌入式研发系统可行性调研报告.docx"
```

## 代码规范

- 所有工具调用入口必须显式传播真实退出码（禁止末尾 echo 掩盖失败）
- 门禁输出一律结构化 JSON（exit code + violations 列表），agent 只消费机器可判定结果
- 失败轮次证据独立目录保留（带时间戳），禁止被成功轮次覆盖
- 涉及外部事实（库存/价格/板卡支持）必须联网核实并标注确定性，禁止凭记忆断言

## 禁止事项

- ❌ 把"仿真通过/DRC 干净"表述为"实物可用"——证据分级 A(机器已验证)/B(一阶估计)/C(待实物验证) 必须显式标注
- ❌ 用 LCSC 零售库存当作 JLC 贴片装配库存做选型依据
- ❌ 绕过门禁直接交付（任何 gate 不通过 = 不出交付物）
- ❌ 项目文件散落到项目文件夹外
