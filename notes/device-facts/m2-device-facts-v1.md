# M2 器件事实目录 v1（信号接线关系 / 已核实器件参数）

> 用途：W1 任务卡 **P3**。为「信号接线关系」「已核实器件参数」两类修复提供**独立于设计文件与实现代码**的真值源。
> 编制：Percy（`la4876949-bot`，独立验收侧），2026-09-06。
> 状态：`PENDING_HUMAN_REVIEW`。

## 0. 为什么需要这份东西

PIT-20260830-001 的根因不是修复能力不足，而是**没有独立真值源**：`akcli check` 证明的是"原理图符合意图"，不是"意图符合数据手册"。所有产物从同一个错误意图派生，于是彼此高度一致，反而制造了"证据很多"的假象。

因此本目录的**唯一合法来源是数据手册原件**，不得从 `intent_v1.json`、原理图、BOM 或任何既有合同反推。

## 1. 纪律

- 每条事实必须给出：**精确型号 + 来源文件 + 页码/章节 + 原文摘录 + 适用条件**。
- **强制要求（must）与建议（recommended）必须分开标注**，不得把"建议"写成"手册要求"。
- 原件里读不到的，一律标 `TO_VERIFY`，**不脑补、不引用社区二手数据**。
- 本目录的期望值**不对修复模型开放**，也不用于调提示词。

### 1.1 核验状态（本目录当前整体为「候选」）

本目录的条目由 **pypdf 机械提取**，按任务卡纪律，**模型抽取只是待审候选，不构成已核实事实**。因此每条事实带一个状态：

| 状态 | 含义 |
|---|---|
| `AI_EXTRACTED_UNVERIFIED` | 已从原件机械提取并记录页码，**尚无人打开 PDF 目视确认** |
| `HUMAN_VERIFIED` | 已有人打开原件、核对该页内容与本文摘录一致，并署名 |

**当前进度（2026-09-08）**：核验表共 **10 条**，其中 **9 条已由 Percy 人工核验通过**（F-U1-01/02/03/05/05b/06、F-U2-01/02/03，覆盖 U1 第 11/12/13/22/34 页与 U2 第 8/9 页，逐页对照原件，**无误**）。**下游三个关键判定所依赖的事实全部已核**：F-U1-01（DC-01）、F-U2-02（DC-02）、F-U1-05（DC-04）。

> 计数更正史：原文曾写"9 条中 6 条"——那是补入 F-U1-05b（p22 的 45 kΩ）之前的旧数，补行后未同步摘要，2026-09-06 更正为 7/10；2026-09-08 Percy 目视核验 p34 与 p22 后为 **9/10**。

未核验的 **1 条**见 §7.1：F-U1-04 中 **p34 Figure 9-1 的图形内容**（`R4 0`/`R6 0` 是否确实串在 D+/D− 路径上）。该条需目视读图，文本提取只能给出无序标号，故保持未核验状态。

文本提取会出的错，重跑提取查不出来——**表格单元格错位**（例如把「0x44 = logic low」读成「= logic high」）、漏掉脚注中的适用条件、跨栏合并。这类错误只能靠人眼对着原件发现。

已由机械手段排除的一类风险：**PDF 页序与文档印刷页码一致**（U1 第 11 页页脚 `Espressif Systems 11`；U2 第 9 页页脚 `9/22`），引用不存在 off-by-one 偏移。

## 2. 来源等级

| 等级 | 含义 | 本轮涉及 |
|---|---|---|
| `A · 原厂手册` | 制造商发布的 datasheet 原件 | U1、U2 |
| `B · 原厂设计指南` | 制造商发布的设计检查清单/应用指南（非 datasheet） | U1 checklist |
| `C · 镜像/二手` | 第三方站点镜像，制造商身份未独立核实 | J1（`FROZEN_PROVENANCE_QUESTIONABLE`） |

---

## 3. U1 — ESP32-C3-WROOM-02-N4

**来源 A**：`src/hardware/m2-board/evidence/datasheets/U1_ESP32-C3-WROOM-02/esp32-c3-wroom-02_datasheet_en.pdf`
**版本：`v1.7`**（页眉原文 `ESP32-C3-WROOM-02 & WROOM-02U Datasheet v1.7`；47 页，PDF CreationDate `D:20260305022759Z`）
**页码基准**：PDF 页序 **=** 文档印刷页码（第 11 页页脚为 `Espressif Systems 11`，12/13 页同），本节引用无偏移。
**来源 B**：同目录 `esp32c3_schematic_checklist_power_supply_2026-08-31.html`（乐鑫原理图检查清单，2026-08-31 抓取）

### F-U1-01　USB 差分对引脚身份　【强制事实 · A】

> **p11，§3 Pin Definitions**
> `IO18  13  I/O/T  GPIO18, USB_D-`
> `IO19  14  I/O/T  GPIO19, USB_D+`

| 语义 | 引脚号 | GPIO |
|---|---|---|
| **USB_D−** | 13 | GPIO18 |
| **USB_D+** | 14 | GPIO19 |

**独立佐证（来源 B）**："GPIO18 and GPIO19 can be used as **D- and D+** of USB respectively." 两来源一致。

> ⚠️ 常见误记：ESP32-**S3** 的 USB 引脚是 GPIO19/GPIO20，与 C3 不同。M2 用的是 C3，引用时不得混用。

### F-U1-02　EN 引脚不得悬空　【强制事实 · A】

> **p11，§3 Pin Definitions**
> `EN  2  I  High: on, enables the chip.` **`Note: Do not leave the EN pin floating.`**

"不得悬空"是手册明文**强制**要求。

### F-U1-03　EN 的 RC 延时　【建议 · **A（datasheet 正文）**，非强制】

> **来源 A，p34（§9 外围设计，Figure 9-1 下方）**：
> "To ensure that the power supply to the ESP32-C3 chip is stable during power-up, it is **advised** to add an RC delay circuit at the EN pin. The **recommended** setting for the RC delay circuit is usually **R = 10 kΩ and C = 1µF**. However, specific parameters should be adjusted based on the power-up timing of the module…"

> **来源 B** 复述同一条，措辞一致。

- **来源等级更正（2026-09-06 核验时发现）**：本条初版被标为「来源 B，datasheet 中没有」——**该判断是错的**，条款就在 datasheet 正文第 34 页。初版的机械检索只搜了 `22Ω` 一类模式，没有覆盖 `RC delay`，因此漏掉。分级（建议 ≠ 强制）不受影响，**来源等级由 B 更正为 A**。
- 措辞是 `advised` / `recommended`，仍**不是**强制条款。
- M2 的 `C5 = 1µF/16V X7R 0603` + `R3 = 10kΩ` 与推荐值一致。
- **判据写法**：缺 C5 应报"未采纳原厂**建议**的 EN RC 延时"，**不得报"违反数据手册强制要求"**。F-U1-02（不得悬空）才是强制项。

### F-U1-04　USB 串联电阻　【建议 · B，非强制】

> **来源 B**："GPIO18 and GPIO19 can be used as D- and D+ of USB respectively. It is **recommended** to reserve **series resistors (initial value can be 22/33 Ω)**"

- 同样是 `recommended`。M2 的 `R7/R8 = 22Ω ±1% 100mW` 对应此条，取值落在建议区间内。
- **datasheet 原件中确无此条（2026-09-06 复核，机械检索）**：全 47 页检索 `22Ω` / `33Ω` / `termination` **均无命中**；`resistor` 仅出现在 p12（strapping 的内部弱上拉/下拉）与 p22（电气特性表的内部上下拉阻值）；`Ω` 仅出现在 p22（45 kΩ 内部上下拉）、p25 与 p37（射频 50 Ω 阻抗）、p34（EN 的 RC 推荐值 10 kΩ）。
- ~~p34 Figure 9-1 中 IO18/IO19 上未画串联电阻~~ **本条错误，2026-09-06 经 Yenefa 交叉复核指出后核实撤回**：
  p34 Figure 9-1 实际含 `R4 0` 与 `R6 0`（均 0Ω），且在提取文本中紧邻 `USB_D-`/`USB_D+` 与 `JP3 USB`。
  原判断来自对图形区域的错误解读，**不成立，已删除该旁证**。
  - 需要说明的是，这一发现**并不推翻本条结论，反而与之一致**：原厂参考图在 USB 路径上预留 0Ω 位置，
    正对应设计指南那句 "**reserve** series resistors (initial value can be 22/33 Ω)"——预留位而非固定阻值。
  - **仍存局限**：PDF 对原理图图形的文本提取只给出无序标号，**空间邻近不等于已证明的电气串联**。
    R4/R6 是否确实串在 D+/D− 路径上，需人眼看图确认（见 §7.1）。
- 因此该要求的权威来源仍是**设计指南（B）**，不是 datasheet——依据是全 47 页机械检索 `22Ω`/`33Ω`/`termination` 零命中，
  **不再依赖已撤回的 Figure 9-1 旁证**。这是 DC-03 判定"报成强制要求即属错误定性"的依据。

### F-U1-05　Strapping 引脚默认电平　【强制事实 · A】

> **p12，Table 4-1 Default Configuration of Strapping Pins**

| Strapping Pin | Default Configuration | Bit Value |
|---|---|---|
| GPIO2 | Floating | – |
| GPIO8 | Floating | – |
| **GPIO9** | **Weak pull-up** | **1** |

**内部上下拉阻值（来源 A，p22 电气特性表；2026-09-06 核验时补录）**：

```
R_PU  Internal weak pull-up resistor    —  45  —  kΩ
R_PD  Internal weak pull-down resistor  —  45  —  kΩ
```

即 GPIO9 的内部弱上拉典型值为 **45 kΩ**。M2 的外部 `R9 = 10 kΩ` 与之并联后主导电平，属加固而非提供缺失的默认值。

- **引用口径限制（2026-09-08 人工核验时确认）**：Table 6-3 中 R_PU / R_PD 的 **Min 与 Max 两列均为「—」，厂家只给 Typ**，且表头条件为 **3.3 V、25 °C**。因此下游（含 P4 的 DC-04 B 维判据）引用时只能写「典型值 45 kΩ @3.3 V/25 °C，厂家未给上下限」，**不得表述为内部上拉「就是」45 kΩ**，也不得据此推算确定的分压结果。

### F-U1-06　启动模式与 GPIO9　【强制事实 · A】

> **p13，Table 4-3 Chip Boot Mode Control**

| Boot Mode | GPIO2 | GPIO8 | GPIO9 |
|---|---|---|---|
| SPI boot mode | 1 | Any value | **1** |
| Joint download boot mode | 1 | 1 | **0** |

**推论（标注为推论，非手册原文）**：GPIO9 **内部已有 weak pull-up**，默认即为 SPI boot。M2 的 `R9 = 10kΩ` 外部上拉属于**加固**（对抗 BOOT 按键漏电流、长走线噪声、上电瞬态），**不是手册强制要求**。

> **判据写法**：缺 R9 不得直接判 FAIL。正确表述是"未加外部上拉加固，默认仍由内部弱上拉决定为 SPI boot；是否可接受取决于 BOOT 按键电路与走线，属设计裕量判断"。

---

## 4. U2 — SHT30-DIS-B10KS

**来源 A**：`src/hardware/m2-board/evidence/datasheets/U2_SHT30-DIS-B10KS/Sensirion_SHT3x_DIS_datasheet.pdf`
**版本：`December 2022 – Version 7`**（页脚原文 `www.sensirion.com December 2022- Version 7 9/22`；共 22 页）
**页码基准**：PDF 页序 **=** 文档印刷页码（第 9 页页脚为 `9/22`），本节引用无偏移。

### F-U2-01　ADDR 引脚不得悬空　【强制事实 · A，手册两处明文】

> **p8，引脚表**
> `2  ADDR  Address pin; input; connect to either logic high or low, do not leave floating`

> **p9，§I2C Address 段**
> **"The ADDR pin must not be left floating."**

手册在两个独立位置重复该要求，属最强等级的强制条款。

### F-U2-02　I²C 地址由 ADDR 电平决定　【强制事实 · A】

> **p9，Table 8 I2C device addresses**

| I²C 地址 | 条件（原文） |
|---|---|
| **0x44**（default） | `ADDR (pin 2) connected to logic low` |
| **0x45** | `ADDR (pin 2) connected to logic high` |

> 补充原文（p9）："only the 7 MSBs of the I2C Read/Write header constitute the I2C Address."

**跨视图判据**：固件写死 `0x44` 时，硬件 ADDR 必须**接地（logic low）**。ADDR 悬空 → 地址未定义 → 与任何固件假设都构成不一致。**这是 ERC/DRC 结构上无法发现的一类错误**（ERC 不理解传感器地址选择语义）。

### F-U2-03　引脚定义　【强制事实 · A，p8】

| 引脚 | 名称 | 手册要求 |
|---|---|---|
| 1 | SDA | — |
| 2 | ADDR | 见 F-U2-01 |
| 4 | SCL | — |
| 5 | VDD | Supply voltage; input |
| 7 | R | connect to VSS |
| 8 | VSS | Ground |
| 9 | VSS_EP | exposed pad internally connected to VSS |

> 与既有 `M2-U2-PINOUT` 合同一致；本目录补的是**页码级出处**（原合同无引用来源）。

---

## 5. J1 — TYPE-C-31-M-12　`TO_VERIFY`

**来源 C**：`.../J1_TYPE-C-31-M-12/TYPE-C-31-M-12_drawing_elecfans_mirror.pdf`

`datasheet_manifest.json` 记录该件状态为 **`FROZEN_PROVENANCE_QUESTIONABLE`**（文件名即表明是 elecfans 镜像，非制造商官方发布；历史上该件曾出现 HIROSE 水印与实际制造商 Korean Hroparts 不符的问题）。

**本轮不从来源 C 提取任何引脚事实。** USB-C 连接器引脚定义应改用 USB Type-C 标准（USB-IF）作为真值源，或取得制造商官方图纸后再补。

`TO_VERIFY`：J1 引脚与 CC1/CC2、D+/D− 的对应关系。

---

## 6. U3 — ME6211C33R5G　`BLOCKED`

**来源 A**：`.../U3_ME6211C33R5G/ME6211_V20_lcsc_official.pdf`（另有 `ME6211_stm32base_mirror.pdf` 为镜像）

`datasheet_manifest.json` 状态：**`BLOCKED_POWER_THERMAL`**。

已知问题（见 `m2_component_contracts.json` 的 `M2-U3-POWER-MARGIN` 与 `docs/u3_route_b_selection_proposal_v1.md`）：

- V20 版给出 **250 mW @ 25°C** 的封装耗散硬边界；
- 实际耗散：150 mA 持续负载 **0.310 W**；345 mA（U1 datasheet v1.7 §6.4.1 的 WiFi TX 峰值）**0.6415 W**；
- **两者均超过 250 mW 上限**；
- **V20 未提供厂家 θJA**，因此无法做结温核算。

`TO_VERIFY`：ME6211C33R5G / SOT-353 的原厂 θJA 与降额条件。

> **这条缺失是真实的、且应当保持 BLOCKED。** 它正好构成 P4 第 6 个开发案例（资料不足 → 系统必须拒绝修复，不得用第三方"常见 θJA"代签）。

---

## 7. 覆盖情况（对照 P4 的 6 个开发案例）

| 案例 | 所需事实 | 状态 |
|---|---|---|
| ① USB D+/D− 接反 | F-U1-01 | ✅ 双来源一致 |
| ② SHT30 ADDR 悬空 vs 固件 0x44 | F-U2-01、F-U2-02 | ✅ 手册两处明文 |
| ③ 缺 USB 22Ω 串阻 | F-U1-04 | ✅ 但**属建议非强制**，判据须相应措辞 |
| ④ 缺 GPIO9 10kΩ 上拉 | F-U1-05、F-U1-06 | ✅ 但**内部已有弱上拉**，不得直接判 FAIL |
| ⑤ 缺 EN 1µF | F-U1-02（强制不得悬空）+ F-U1-03（建议 RC） | ✅ 两级要求须区分 |
| ⑥ U3 资料不足 → 拒绝修复 | §6 | ✅ 缺失属实，应保持 BLOCKED |

## 7.1 人工核验清单

核验方式：打开对应 PDF，翻到该页，**目视确认本文摘录与页面内容一致**，重点看表格是否被提取工具错位。确认后把状态改为 `HUMAN_VERIFIED` 并署名。

| 事实 | 原件 | 页 | 核验要点 | 状态 | 核验人 |
|---|---|---|---|---|---|
| F-U1-01 USB 差分对身份 | U1 v1.7 | 11 | **IO18 是否对 USB_D−、IO19 是否对 USB_D+**（若这两行被读反，DC-01 的答案就是错的） | `HUMAN_VERIFIED` | Percy |
| F-U1-02 EN 不得悬空 | U1 v1.7 | 11 | `Note:` 原文是否确为 "Do not leave the EN pin floating" | `HUMAN_VERIFIED` | Percy |
| F-U1-03 EN 的 RC | **U1 v1.7**（更正） | **34** | 措辞是否确为 `advised`/`recommended`（而非 must/shall）；R/C 取值。**本条来源等级已由 B 更正为 A** | `HUMAN_VERIFIED` | Percy |
| F-U1-04 USB 串阻 | checklist HTML | — | 措辞是否确为 `recommended`。datasheet 无此条已由机械检索复核（`22Ω`/`33Ω`/`termination` 全 47 页零命中）；**剩余需人眼的部分**：p34 Figure 9-1 中 `R4 0`/`R6 0` 是否确实串在 D+/D− 路径上（文本提取只给无序标号，邻近≠已证明串联） | `AI_EXTRACTED_UNVERIFIED` | |
| F-U1-05 Strapping 默认 | U1 v1.7 | 12 | Table 4-1 中 GPIO9 = Weak pull-up / Bit 1 | `HUMAN_VERIFIED` | Percy |
| F-U1-05b 内部上下拉阻值 | U1 v1.7 | 22 | Table 6-3 内部上下拉是否确为 **45 kΩ**；**并确认 Min/Max 两列均为「—」**（即仅给典型值、无保证边界） | `HUMAN_VERIFIED` | Percy |
| F-U1-06 启动模式 | U1 v1.7 | 13 | Table 4-3 各列是否对齐（表格易错位） | `HUMAN_VERIFIED` | Percy |
| F-U2-01 ADDR 不得悬空 | U2 Ver.7 | 8, 9 | 两处原文是否都在 | `HUMAN_VERIFIED` | Percy |
| F-U2-02 地址映射 | U2 Ver.7 | 9 | **Table 8：0x44 是否确对 logic low、0x45 对 logic high**（读反则 DC-02 全错） | `HUMAN_VERIFIED` | Percy |
| F-U2-03 引脚定义 | U2 Ver.7 | 8 | 引脚号与名称是否逐行对应 | `HUMAN_VERIFIED` | Percy |

**三条最要紧**（读反会让下游案例的标准答案整体错误）：**F-U1-01**、**F-U2-02**、**F-U1-05**。时间有限就先核这三条。

## 8. 本轮明确未做

- 未从来源 C（J1 镜像图纸）提取任何事实。
- ~~未核实 U1 datasheet 版本号~~ **已解决**：版本印在每页页眉（U1 `v1.7`、U2 `December 2022 – Version 7`），PDF 元数据无 `/Title` 不代表版本不可得——原记载是查得不够。
- 未覆盖 D1、SW1/SW2、无源件参数——本轮范围限定为两类修复所需的最小事实集。
- 未做任何设计判断或修复建议；本目录只陈述手册事实。

## 9. 关联

- 任务卡：W1 / P3（`docs/competition/internal/W1_CARD_Percy_20260907.md`）
- 下游：P4（6 个开发案例的独立期望值）、E1（24 案例验收）
- 评分项：S2、S3、S4
