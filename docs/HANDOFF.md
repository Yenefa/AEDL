# HANDOFF — project-027-autonomous-hardware-agent

## 一、项目现状

2026-08-24 立项。调研报告（docx）已交付并获大统领三项拍板放行。**M1 完成（5.5/6）；M2 已打通固件链 + G1 选型冻结 + G2 原理图门禁**，git 提交 bd9d973。全部证据在 `notes/m1-evidence/`。

### M2 记分板（进行中）

| Gate | 项                | 结果                                                                                                                                                                      |
| ---- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| —    | 固件编译 G7 预演  | ✅ esp32c3(真机 CDC) + esp32c3_simstub(UART0+桩传感器) 双环境 SUCCESS                                                                                                     |
| G8   | host 单测         | ✅ 4/4（数据手册 CRC 向量 / 好帧 / 坏 CRC 拒收 / RH 钳位），PIO native+Unity                                                                                              |
| G9   | Wokwi 行为断言    | ✅ **已转绿（方案 A：Arduino→ESP-IDF 6.0.1 迁移）**。关键组合：sdkconfig CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y + diagram attrs.serialInterface=USB_SERIAL_JTAG + flasher_args 路径别名修正(tools/fix_flasher_args.py) + FLASHSIZE_4MB 对齐。串口日志含完整 boot 链+`{"seq":1,"t_c":25.10,"rh":51.0}` 断言命中，exit 0 |
| G1   | BOM 冻结          | ✅ gates/bom/bom_v1.json：18 料位全命中实时库存（含 2 个 Basic 库料 C15850/C2286）；换型记录在案（MINI-1→WROOM-02 因 KiCad 无符号）                                        |
| G2   | 原理图            | ✅ intent(17 元件/13 网络)→93 ops→落图→intent 比对 0 差异 + ERC JSON 0 违规；strapping 冲突(GPIO9=BOOT)设计阶段发现改版（I2C→IO4/IO5），固件已同步                        |
| **G4** | **PCB 全链**    | ✅ **intent 建板(自动装箱布局+77 pad 多实例全挂网)→DSN→freerouting 无头路由→SES 回读→DRC JSON 0 违规 0 未连接**；工具链 tools/build_board.py + dsn_ses.py 可复用           |
| **G10** | **交付打包**   | ✅ delivery/：jlc_gerber_upload.zip(26 文件)+bom.csv(17 料位与板一致)+pos.csv(坐标表)；正式测试报告 docs/M2板级测试报告.docx                                                |

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

1. **打板**：delivery/jlc_gerber_upload.zip 上传嘉立创下单（BOM/坐标已配套）；回件后按报告第五章人工上电实测（C 级项闭环）。
2. **M3 固化**：把 G1-G10 各环封装为一键技能包（skills/mcp 化），支持任意"一句话需求"输入；token 计量与迭代预算上线。
3. 大统领动作项（保留）：JLCPCB 官方 API 申请（有订单史后）。
