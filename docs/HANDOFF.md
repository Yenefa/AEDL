# HANDOFF — project-027-autonomous-hardware-agent

## 一、项目现状

2026-08-24 立项。调研报告（docx）已交付并获大统领三项拍板放行（M1 安装授权/首板选题 ESP32-C3 温湿度记录仪/JLC 官方 API 待订单史后申请）。**M1 单点工具链实测已完成 6 项中的 5.5 项**，全部证据在 `notes/m1-evidence/`。

### M1 验收记分板

| #   | 项                              | 结果                                                                                                                                                  |
| --- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| ①   | kicad-cli headless ERC/DRC JSON | ✅ KiCad 10.0.5，样例工程 44/41 违规 JSON 落盘。⚠️发现：有违规时退出码仍为 0 → 门禁必须解析 JSON 计数                                                 |
| ②   | akcli-kicad 画图过 ERC + sim    | ✅ v0.21.0；intent(设计文档)→op-list→draw --strict-nets 一键成图，kicad 权威 ERC **0 违规**；SPICE deck 生成 ✅（断言级 sim 留 M2，最小电路无源可仿） |
| ③   | wokwi-cli                       | ⚠️ v0.26.1 已落地可用；**真跑云仿真需 WOKWI_CLI_TOKEN**（大统领在 wokwi.com/dashboard/ci 免费注册获取）——唯一阻塞项                                   |
| ④   | renode-test + STM32G0           | ✅ harness 全通 + 自写 g0_smoke.robot 2/2 通过（平台加载+adc/dma1/nvic 实例化）；ELF 级行为测试留 M2 固件编译后                                       |
| ⑤   | JRE21 + freerouting.jar         | ✅ Temurin 21.0.12 + freerouting v2.3.0 jar 完整性验证（DSN→SES 循环留 M2）                                                                           |
| ⑥   | 器件库存实查                    | ✅ jlcpcb CLI 直连成功：ESP32-C3-MINI-1-N4 (C2838502, 库存21261, $3.83)、SHT30-DIS-B10KS (C2687423, 库存30438, $2.54)，实时含手册链接                 |

## 二、技术栈与目录

见根目录 README.md 与 AGENTS.md。本机已装：KiCad 10.0.5（用户级 `C:\Users\fuker\AppData\Local\Programs\KiCad`）、Renode 1.16.0、Temurin JRE 21、wokwi-cli/freerouting 在项目 `tools/bin/`。用户级环境变量已固化：KICAD_CLI / KICAD10_SYMBOL_DIR / AKCLI_NGSPICE。

## 三、架构决策记录

1. 实现路径：基于现成 agent 底座集成（OpenCode/Claude Code + 技能生态），不自研 runtime。
2. EDA：KiCad 设计 → 嘉立创打板；akcli-kicad 为主力原理图引擎（intent 层抽象最高）。
3. 验证第一档 = 无实体板交付，证据分级 A/B/C。
4. 起步域：MCU 最小系统+外设 2 层板；ESP32-C3(Wokwi) / STM32G0(Renode) 双路线。
5. "单 Agent" = 一个主控持有全部设计上下文 + 确定性工具进程，不拆多 agent。
6. **门禁哲学修正（M1 实测得出）：EDA 工具退出码不可信（kicad-cli 违规仍返 0），一切门禁以解析结构化 JSON 计数为准。**

## 四、已知坑

- LCSC 零售库存 ≠ JLC 贴片装配库存；jlcpcb CLI 数据源为 jlcpcb.com 自身（即装配口径），选型以此为准。
- kicad-mcp-pro 的 SI/PI/EMC 工具仅一阶估计（~5–10%），只能出 B 级证据。
- renode-test.bat 路径带空格必挂（cmd 参数剥离）→ 用 `subst R:` 盘符绕开，用完 `/d` 清理。
- 本机 python 分裂：`python`=hermes venv(3.11)、`py -3`=VS Python39(renode-test 用)。给 Renode 测试装依赖必须 `py -3 -m pip`。曾误将 requirements 装进 hermes venv 并降级其依赖，已复原 pins（cryptography==48.0.1 / psutil==7.2.2 / ruamel.yaml==0.18.17）。
- PS 5.1 本环境 `>` 重定向会报 FileStream 怪错且写 UTF-16 → 捕获工具输出一律 `cmd /c "... > file 2>&1"` 包装。
- KiCad 新装机器无全局符号表 → 从 `<install>\share\kicad\template\` 复制 sym-lib-table/fp-lib-table 到 `%APPDATA%\kicad\10.0\`。
- Wokwi 不支持 STM32G0；STM32G0 行为仿真走 Renode（外设模型源码级确认存在：STM32G0DMA/STM32G0_ADC）。

## 五、下一步任务（含验收标准）

1. **大统领动作项**：wokwi.com 免费注册 → CI Dashboard 拿 token → 设 `WOKWI_CLI_TOKEN` 环境变量（或明确放弃 Wokwi 线，全走 Renode）。
2. M2 准备：搭 ESP32-C3 温湿度记录仪仓库骨架（ESP-IDF 或 PlatformIO 二选一，M2 首日定）；安装 arm-none-eabi 工具链补 STM32G0 ELF 行为测试。
3. M2 主验收：该板端到端全自动一次跑通——需求→BOM(G1)→原理图(G2 ERC 0 违规 JSON)→PCB freerouting(G4 DRC 0 违规)→固件编译(G7 exit0+Werror)→Wokwi/Renode 行为断言(G9)→Gerber/BOM/坐标包(G10)；全程失败轮次独立存档。
