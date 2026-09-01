# EDD-001 CORE_BASE v0.1 冻结记录

> 日期：2026-09-01 ｜ 状态：`FROZEN`（合同 `PENDING_HUMAN_REVIEW`）｜ 性质：设计定案记录，非正式 Evidence
> 上游：EDD-001.USB v0.1 已冻结（TYPE-C-31-M-12 / CC 5.1k×2 / USBLC6-2SC6 / 22Ω×2 / SS34 / GPIO19-20）
> 依据：Espressif 官方硬件设计指南 / 模组与芯片 datasheet / esptool 文档（来源见各节）；数值凡官方未明确者标 `UNKNOWN`，不推断。
> 原则：**数据手册语义写入独立合同（`gates/contracts/edd001_core_base_contract_v1.json`），不得从 intent 自动生成**（PIT-20260830-001）。

---

## 0. 一句话结论

`ESP32-S3-WROOM-1-N8R8` 的生存底座 = **模组本地去耦（22µF + 100nF）+ EN 复位网络（10k + 1µF + 复位键）+ BOOT 网络（GPIO0 10k 外部上拉 + BOOT 键）+ 四颗 strapping pin 全部禁配 + N8R8 PSRAM 三颗 pin 物理封死 + USB pin 硬保留 + UART0 软保留 + 天线伸出板边 + EPAD 焊接**。

这是 AEDL 第一个 **Machine-Readable Hardware Boundary**：以后 Agent 不允许重新发明它。

---

## 1. 电源入口（冻结）

官方典型外围电路在 VDD33 本地放 `22µF + 0.1µF` 到 GND：

```text
3V3
 │
 ├── C_CORE_BULK = 22uF
 ├── C_CORE_HF   = 100nF
 └── ESP32-S3-WROOM-1-N8R8 3V3
```

- 两颗电容**靠近模组 3V3/GND**。
- 前面的 AP63203 已有自己的输出电容，但这两颗属于**模组本地储能/去耦**，不能因为前面有 COUT 就删。
- ⚠️ 修正：上一轮草稿的 `10µF + 1µF` 作废，以官方典型外围电路 `22µF + 100nF` 为准（`edd001_pin_constraints_v1.json#POWER_3V3_DECOUPLING` 已同步修正）。

## 2. EN / RESET（冻结，Verified Infrastructure）

- EN = CHIP_PU，**不能悬空**；推荐 RC 延时；典型 `R = 10kΩ`、`C = 1µF`。
- 复位按钮并联在 EN 与 GND 之间。

```text
3V3 ── R_EN 10kΩ ──┬── EN / CHIP_PU
                    │
                   C_EN 1µF
                    │
                   GND
                    │
              [RESET 键：EN ── GND]
```

```yaml
reset:
  en_pullup: 10k
  en_cap: 1uF
  reset_button: EN_to_GND
```

以后 Agent：❌ 不允许修改 ｜ ❌ 不允许删 RC ｜ ❌ 不允许拿 EN 当普通 GPIO。属于 **Verified Infrastructure**。

## 3. BOOT（冻结）

- GPIO0 默认 weak pull-up；GPIO46 默认 weak pull-down。
- 启动模式：`GPIO0=1 → SPI Boot`；`GPIO0=0 且 GPIO46=0 → Download Boot`。
- 官方建议 GPIO0 预留外部上拉，**警告不要挂大电容**（否则可能误进 Download Mode）。
- 项目锁 `10k` 外部上拉 + BOOT 键到 GND。**10k 是 AEDL baseline 设计选择**；官方只要求"建议外部上拉"，未钉死唯一阻值。

```text
3V3 ── R_BOOT 10kΩ ── GPIO0 ── BOOT_BUTTON ── GND

正常：GPIO0 = HIGH → Boot
按住 BOOT：GPIO0 = LOW → 再 Reset → Download Boot
```

Native USB 下载链闭合。

## 4. 四颗 Strapping Pin：全部进入特殊管制

| Pin | 作用 | 默认/内部 | v0.1 状态 | 信心 |
|---|---|---|---|---|
| **GPIO0** | 启动模式 / 下载模式 | 内部弱上拉 | `reserved`（BOOT） | 高 |
| **GPIO3** | Strapping（JTAG 等） | 官方未明确 | `forbidden_for_agent` | 中 |
| **GPIO45** | VDD_SPI 电压控制 | 1.8V 拉高 / 3.3V 拉低 | `forbidden_for_agent` | 高 |
| **GPIO46** | 启动模式控制 | 内部弱下拉 | `forbidden_for_agent` | 高 |

```yaml
GPIO0:
  class: strap
  status: reserved
  function: boot

GPIO3:
  class: strap
  status: forbidden_for_agent

GPIO45:
  class: strap
  status: forbidden_for_agent

GPIO46:
  class: strap
  status: forbidden_for_agent
```

**第一版 Agent 一个都不许碰。** 先牺牲四颗 GPIO 换可靠性。以后 EDD 扩张可引入 `conditionally_available`：Agent 必须证明外部电路不会改变上电采样状态（后续研究点）。

## 5. N8R8 特有：GPIO35/36/37 物理封死

`ESP32-S3-WROOM-1-N8R8` 使用 **8MB Octal SPI PSRAM**，官方模组 datasheet 明确：`IO35 / IO36 / IO37` 已连接 PSRAM，**不能用于其他用途**。

```yaml
GPIO35:
  status: HARD_FORBIDDEN
  reason: octal_psram

GPIO36:
  status: HARD_FORBIDDEN
  reason: octal_psram

GPIO37:
  status: HARD_FORBIDDEN
  reason: octal_psram
```

与 strapping 不同：strapping 是"暂时不让 Agent 碰"，35/36/37 是"**物理上就别想碰**"。这就是 exact SKU 的意义——只写"ESP32-S3"的话，Agent 很可能自信地"GPIO36 很适合接 LED"，然后翻车。

## 6. USB pins：硬保留

```text
GPIO19 = USB_D-
GPIO20 = USB_D+
```

Agent 不能把 SHT40 SDA 接 GPIO19。Verifier 直接：

```text
❌ PIN_CONFLICT
GPIO19 reserved by CORE_BASE.USB
```

## 7. UART0：Soft Reserve

```text
GPIO43 = U0TXD（串 499Ω 抑制谐波）
GPIO44 = U0RXD
```

```yaml
GPIO43:
  status: soft_reserved
  preferred_function: U0TXD

GPIO44:
  status: soft_reserved
  preferred_function: U0RXD
```

v0.1 默认保留 `DEBUG_UART`（3V3 / GND / TXD0 GPIO43 / RXD0 GPIO44），其中 `GPIO43 ── 499Ω ── UART_TX`。Header 可 **DNP / optional**：正常开发用 USB，出问题还有 UART 救命。

## 8. 天线：最简单最可靠策略

WROOM-1 是板载 PCB 天线。Espressif 第一推荐：**直接把模组天线伸出 base PCB 边缘，feed point 靠近主板边缘**。

```yaml
antenna:
  placement:
    preferred: overhang_board_edge

  copper_under_antenna: forbidden
  traces_under_antenna: forbidden
  components_under_antenna: forbidden
```

- 如果机械尺寸不能伸出去，才进入官方 keepout-zone 规则。
- 终端产品天线周围建议保留至少约 **15 mm clearance**，并最终做吞吐量、通信距离等 RF 实测。
- 关键认知：**我们不是在"设计 RF"**。RF 已被 Espressif 模组封装，我们只验证"集成者有没有把官方已经设计好的天线搞废"。

## 9. EPAD / Ground

```text
EPAD 41 = GND
```

官方：底部 EPAD 并非必须焊接，但焊接可改善热性能。baseline：**焊**。

```yaml
epad:
  net: GND
  soldered: true
```

使用 Espressif 推荐 land pattern。

## 10. 第一版 Pin Policy（Machine-Readable Hardware Boundary）

### 🔴 HARD FORBIDDEN（物理封死）

```text
GPIO35  → PSRAM
GPIO36  → PSRAM
GPIO37  → PSRAM
```

### 🟠 CORE RESERVED（核心保留）

```text
GPIO0   → BOOT
GPIO3   → STRAPPING
GPIO45  → STRAPPING
GPIO46  → STRAPPING
GPIO19  → USB_D-
GPIO20  → USB_D+
```

### 🟡 SOFT RESERVED（软保留）

```text
GPIO43  → UART0 TX
GPIO44  → UART0 RX
```

### 🟢 AGENT DESIGN POOL（25 个 GPIO）

```text
GPIO1  GPIO2  GPIO4  GPIO5  GPIO6  GPIO7  GPIO8  GPIO9
GPIO10 GPIO11 GPIO12 GPIO13 GPIO14 GPIO15 GPIO16 GPIO17
GPIO18 GPIO21 GPIO38 GPIO39 GPIO40 GPIO41 GPIO42 GPIO47 GPIO48
```

I²C、SPI、UART、ADC、PWM、I²S、TWAI、LED、Button、传感器——完全够用。

## 11. 待确认项（TO_VERIFY）

1. GPIO26/27/28 在 WROOM-1 上已引出，但未进 agent pool；确认是否刻意排除（对照模组 datasheet）。
2. GPIO29-32 / GPIO33 / GPIO34 在 WROOM-1 上的引出状态（in-package flash/PSRAM），对照模组 datasheet。
3. GPIO3 strapping 默认态：官方未明确，需按 datasheet / boot log 确认。
4. 逐引脚去耦清单、电源纹波指标：以模组 datasheet 为准。
5. GPIO45 是否需要 R1：取决于 WROOM-1 的 VDD_SPI_FORCE eFuse 配置。

---

## 产出的合同

| 合同 | 状态 | 内容 |
|---|---|---|
| `gates/contracts/edd001_core_base_contract_v1.json` | FROZEN（PENDING_HUMAN_REVIEW） | CORE_BASE 权威合同：电源入口 / EN / BOOT / Pin Policy / 天线 / EPAD |
| `gates/contracts/edd001_pin_constraints_v1.json` | 部分被取代 | Pin Policy 规则被 CORE_BASE 取代；`USB_DIFFERENTIAL`、`POWER_SOURCE_SEPARATION` 仍有效 |
| `gates/contracts/edd001_usb_contract_v1.json` | FROZEN（PENDING_HUMAN_REVIEW） | USB 块合同 |

---

（本文件为设计定案记录，未提交、未进 Evidence/合规台账，供人工核阅。AI 参与：RESEARCH/DOCUMENT，待登记 AI_USAGE_LOG。）
