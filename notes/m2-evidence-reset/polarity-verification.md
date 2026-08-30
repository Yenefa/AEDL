# M2 极性方向数据级验证报告（打板前必读）

> 日期：2026-08-31
> 触发：多模态 AI 目检在 1600×900 整板缩略图下对 D1/U2/U3 三个极性件的方向"看不清"。
> 方法：放弃看图，改用**数据级推导**——从 KiCad 官方符号库读引脚定义，从 intent/PCB 读实际
>   网络连接，逐器件对齐。这是目检做不到的精确判定。
> 证据来源（全部本机读文件，非训练记忆）：
>   - `C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\Device.kicad_sym`
>   - `C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints\LED_SMD.pretty\LED_0603_1608Metric.kicad_mod`
>   - `src/hardware/m2-board/intent_v1.json`、`m2_board.kicad_pcb`

---

## 0. 一句话结论

**D1（LED）极性接反了**——阴极 K 接到了驱动信号、阳极 A 接到了 GND，电流路径反向，LED 不会亮。
U2（SHT30）、U3（LDO）经数据级核对**方向正确**。

这是打板前必须修的 bug，且**恰好是所有机器门禁都抓不到的那一类错误**（详见 §4）。

---

## 1. D1（LED）—— 反接，铁证

### 证据链（逐环）

| 环 | 事实 | 来源 |
|---|---|---|
| ① KiCad LED 符号 | `pin "1"` name=`K`（阴极），`pin "2"` name=`A`（阳极） | `Device.kicad_sym` 直接读取，`(name "K") (number "1")` + `(name "A") (number "2")` |
| ② Sim.Pins 佐证 | `Sim.Pins = "1=K 2=A"` | 同符号库 |
| ③ Footprint pad 对应 | pad1=pin1=K，pad2=pin2=A（KiCad ERC 强制 pad 号匹配 pin 号） | 约定 |
| ④ Footprint 阴极标记 | F.Fab 层阴极三角标记在 pad1 侧（x=-0.8~-0.5，左侧） | `LED_0603_1608Metric.kicad_mod` 直接读取 |
| ⑤ PCB 实际网络 | `D1` pad1 → net `LED_A`，pad2 → net `GND` | `m2_board.kicad_pcb` 直接读取 |
| ⑥ intent 网络 | `LED_A = [R4.2, D1.1]`，`LED_DRV = [U1.15, R4.1]`，`GND` 含 `D1.2` | `intent_v1.json` 直接读取 |

### 结论

物理电流路径（GPIO 高电平 3.3V 时）：

```text
U1.15(GPIO) → R4.1 → R4.2 → LED_A → D1.1(pad1=阴极 K) → [LED] → D1.2(pad2=阳极 A) → GND
```

LED 需要**阳极 A 接正、阴极 K 接负**才能导通发光。现在阴极 K 接驱动侧（正）、阳极 A 接 GND（负），
**反向偏置，不导通，LED 不亮**。3.3V 低于 LED 反向击穿电压（一般 >5V），所以不会损坏，只是不亮。

正确接法应为：`U1.15 → R4 → D1 阳极A → D1 阴极K → GND`。

---

## 2. U3（ME6211C33 LDO）—— 正确

intent 网络 vs 数据手册（V20，pin1=VIN/pin2=GND/pin3=CE/pin4=NC/pin5=VOUT）：

| 引脚 | 应接 | 实际网络 | 判定 |
|---|---|---|---|
| U3.1 | VIN | +5V | ✅ |
| U3.2 | GND | GND | ✅ |
| U3.3 | CE（高使能） | +5V | ✅ |
| U3.4 | NC | 未连 | ✅ |
| U3.5 | VOUT | +3V3 | ✅ |

U3 换料后引脚序正确（ADR-005 审核的 SOT-353 pinout 落地无误）。

---

## 3. U2（SHT30 DFN-8）—— 正确

intent 网络 vs SHT30-DIS 标准 pinout（pin1=SDA/pin2=ADDR/pin3=ALERT/pin4=SCL/pin5=VDD/pin6=nRESET/pin7=GND/pin8=GND/EP=GND）：

| 引脚 | 应接 | 实际网络 | 判定 |
|---|---|---|---|
| U2.1 | SDA | SDA | ✅ |
| U2.2 | ADDR（接地=0x44） | GND | ✅（语义合同 SHT30_ADDRESS 已锁定） |
| U2.4 | SCL | SCL | ✅ |
| U2.5 | VDD | +3V3 | ✅ |
| U2.7/8/9 | GND/EP | GND | ✅ |
| U2.3(ALERT)/U2.6(nRESET) | 不连 | 未连 | ✅（语义合同 SHT30_UNUSED_PINS 已锁定） |

U2 完全正确。

---

## 4. 为什么所有机器门禁都 PASS，却抓不到这个反接？

这是本项目最需要记下的一课，也是 PIT-20260830-001「多层自洽 ≠ 独立正确性」的**第二次应验**：

| 门禁 | 为什么抓不到 |
|---|---|
| ERC | 只查电气类型（pin 是 passive 连 passive），不理解"LED 的 K 必须朝 GND 侧"这个语义 |
| DRC | 只查几何（间距/连通），不管电流方向 |
| intent/ops/schematic_semantics | 都查"一致"，而反接错误在**最初写 intent 时**就种下，三层一致地延续了这个错 |
| board_review ASSEMBLY | 机器只查"极性件**有**标记"，不查"标记方向**对不对**" |
| 多模态目检 | 整板缩略图下器件太小，D1 色带"看不清" |

**根因**：LED 反接是**语义级**错误，而 AEDL 现有的验证层里，唯一能抓语义错误的是
`schematic_semantics` 的数据手册契约——但 M2 的契约里**没有一条规则覆盖 LED 极性**（契约锁了
USB 极性、SHT30 地址、EN 网络、GPIO9 上拉，唯独漏了 LED）。

---

## 5. 修复建议（按成本排序）

1. **修 intent + 全链重放**（治本，必修）：把 intent 里 D1.1/D1.2 的网络对调（D1.1→GND，D1.2→LED_A），
   或者改原理图符号方向。二选一，然后重放 ops → 原理图 → PCB → ERC/DRC → 交付，重跑 10 门禁。
   ⚠️ 注意：这会让 delivery manifest 等所有哈希级联失效，需全套重导（和 U3 换料同一套流程）。

2. **补一条 LED 极性语义契约**（防再犯，建议）：在 `m2_schematic_contract_v1.json` 加一条规则，
   检查"LED 的阳极 pin 必须连到驱动/正侧网络、阴极 pin 必须连 GND"。这正是这次漏掉的那一条。

3. **board_review ASSEMBLY 升级**（治本）：把"极性件有标记"升级为"极性件的阳极/阴极网络方向正确"，
   机器可判定（读 footprint pad 号 + 网络名），不需要看图。

---

## 6. 诚实边界

- D1 反接结论基于 KiCad 官方符号定义（`pin1=K, pin2=A`，已直接读库确认），**不是训练记忆**。
- 该结论是数据级推导，未经过"人对照原理图符号图形"的最后一关。若原理图里 LED 符号本身
  是镜像/特殊放置的，理论上可能引入额外翻转——但 pin 编号→网络 的映射不受符号旋转影响，
  所以结论成立。仍建议修复时人工瞄一眼原理图 LED 符号三角朝向做最终确认。
- U2/U3 的"正确"结论依赖数据手册 pinout（V20/SHT30 标准），这些是 ADR-005 已审核过的基线。
