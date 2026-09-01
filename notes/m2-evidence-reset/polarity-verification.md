# M2 极性方向数据级验证报告（打板前必读）

> 日期：2026-08-31（rev2：同日经人工独立复核后修订）
> 触发：多模态 AI 目检在 1600×900 整板缩略图下对 D1/U2/U3 三个极性件的方向"看不清"。
> 方法：放弃看图，改用**数据级推导**——从 KiCad 官方符号库读引脚定义，从 intent/PCB 读实际
>   网络连接，逐器件对齐。这是目检做不到的精确判定。
> 证据来源（全部本机读文件，非训练记忆）：
>   - `C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\Device.kicad_sym`
>   - `C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\Sensor_Humidity.kicad_sym`
>   - `C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints\LED_SMD.pretty\LED_0603_1608Metric.kicad_mod`
>   - `src/hardware/m2-board/intent_v1.json`、`m2_board.kicad_pcb`
>
> **rev2 修订记录（人工复核意见全部采纳）**：
> ① 环③术语修正：pin↔pad 对应是 KiCad 的编号映射机制，不是"ERC 强制"；
> ② 删除"3.3V 不会损坏 LED"的死结论——反向偏置可靠性须按具体料号数据手册判定（D1 = KENTO KT-0603R，LCSC C2286）；
> ③ U2 pin7 更正为 `R`（datasheet 要求接 VSS），不再含糊写成 GND 引脚；
> ④ 删除"改原理图符号方向可修复"的错误表述与"镜像可能引入额外翻转"的自相矛盾句——
>    符号旋转/镜像不改变 pin number→net 映射，修复只能改网络（已按此执行，见 §5）。
> ⑤ rev3（2026-08-31 晚）：KT-0603R 一手资料冻结入证据库（湖北匡通承认书 Rev A.0，sha256
>    a3bac1cc…d4a1）。Absolute Maximum Ratings 实测：Pd 40mW / IFP 60mA / IF(DC) 25mA /
>    VR 5V / IR≤5µA@5V / 回流 260C 10s。旧故障态反偏约 3.3V < 5V absmax，严格措辞：
>    "reverse voltage remains below datasheet absolute maximum"——这不表示反接可接受，
>    反接是功能错误，已修复。

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
| ③ Footprint pad 对应 | pad1=pin1=K，pad2=pin2=A（KiCad 按 symbol pin number ↔ footprint pad number 建立电气映射；ERC 只是检查机制，不是映射本身） | 约定 |
| ④ Footprint 阴极标记 | F.Fab 层阴极三角标记在 pad1 侧（x=-0.8~-0.5，左侧） | `LED_0603_1608Metric.kicad_mod` 直接读取 |
| ⑤ PCB 实际网络 | `D1` pad1 → net `LED_A`，pad2 → net `GND` | `m2_board.kicad_pcb` 直接读取 |
| ⑥ intent 网络 | `LED_A = [R4.2, D1.1]`，`LED_DRV = [U1.15, R4.1]`，`GND` 含 `D1.2` | `intent_v1.json` 直接读取 |

### 结论

物理电流路径（GPIO 高电平 3.3V 时）：

```text
U1.15(GPIO) → R4.1 → R4.2 → LED_A → D1.1(pad1=阴极 K) → [LED] → D1.2(pad2=阳极 A) → GND
```

LED 需要**阳极 A 接正、阴极 K 接负**才能导通发光。现在阴极 K 接驱动侧（正）、阳极 A 接 GND（负），
**反向偏置，不导通，LED 不亮**。注意：footprint 不携带反向耐压信息，D1 将处于约 3.3V 反向偏置，
是否存在器件可靠性风险须按最终料号（Hubei KENTO KT-0603R，LCSC C2286）数据手册的
reverse-voltage 规格判定，本报告不下"不会损坏"的结论。

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

intent 网络 vs SHT30-DIS 标准 pinout（pin1=SDA/pin2=ADDR/pin3=ALERT/pin4=SCL/pin5=VDD/pin6=nRESET/**pin7=R（datasheet 要求接 VSS）**/pin8=VSS/中心焊盘=内部连 VSS；KiCad 官方符号 `Sensor_Humidity:SHT30-DIS` 同名：7=`R`、8=`VSS`、9=`VSS`(EP)）：

| 引脚 | 应接 | 实际网络 | 判定 |
|---|---|---|---|
| U2.1 | SDA | SDA | ✅ |
| U2.2 | ADDR（接地=0x44） | GND | ✅（语义合同 SHT30_ADDRESS 已锁定） |
| U2.4 | SCL | SCL | ✅ |
| U2.5 | VDD | +3V3 | ✅ |
| U2.7 | R（datasheet 规定接 VSS） | GND | ✅（电气正确，术语上 pin7 名为 R 而非 GND） |
| U2.8 | VSS | GND | ✅ |
| U2.9 | EP（内部连 VSS） | GND | ✅ |
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

## 5. 修复建议与执行状态

1. **修 intent + 全链重放**（治本，必修）：把 intent 里 D1.1/D1.2 的网络对调（D1.1→GND，D1.2→LED_A），
   然后重放 ops → 原理图 → PCB → ERC/DRC → 交付，重跑 10 门禁。
   ⚠️ 注意：这会让 delivery manifest 等所有哈希级联失效，需全套重导（和 U3 换料同一套流程）。
   **明确排除的错误修法**：旋转/镜像原理图 LED 符号只改变图形显示方向，不会交换 pin1/pin2 的
   网络映射，不能修复本问题——只能改网络连接。
   **执行状态（2026-08-31，TASK-FIX-D1）**：已修。intent/原理图/PCB 三层网络对调一致；
   PCB 侧因铜皮已物理连通 pad1↔R4.2 铜皮、pad2↔GND 铜皮，只换网络属性会造成铜皮-网络冲突
   且 LED 物理上仍反接，故将 D1 footprint **原地旋转 180°**（物理放置变更，使 pad1=K 落到
   GND 铜皮、pad2=A 落到 LED_A 铜皮）并同步交换 pad 网络——这不是"改符号方向"，走线零改动，
   阴极丝印标记随封装转到正确侧。验收：新导网表 `D1 pin1(K)→/GND、pin2(A)→/LED_A`，
   9/10 门禁 PASS + board_review 仅余 `manufacturing_release=false`。

2. **补一条 LED 极性语义契约**（防再犯，建议）：在 `m2_schematic_contract_v1.json` 加规则。
   **通用规则不能写成"LED 阴极必须接 GND"**——active-low（灌电流）接法 `+3V3→R→A|K→GPIO`
   完全合法，此时 K 不接 GND。正确分层：
   - M2 专用（本轮可落）：`D1.1(K) must be GND`、`D1.2(A) must be LED_A`；
   - 通用 AEDL（长期方向）：验证"LED_ON 状态下 VA > VK 且存在合法限流路径"的电气语义规则。
   本轮未实施（留下轮），已按此分层记录。

3. **board_review ASSEMBLY 升级**（治本）：把"极性件有标记"升级为"极性件的阳极/阴极网络方向正确"，
   机器可判定（读 footprint pad 号 + 网络名），不需要看图。

---

## 6. 诚实边界

- D1 反接结论基于 KiCad 官方符号定义（`pin1=K, pin2=A`，已直接读库确认），**不是训练记忆**。
- **符号旋转/镜像不影响 pin number → net 映射**：pin1 永远是 pin1，任何图形方向变化都不会
  交换 D1.1 ↔ D1.2，因此不存在"符号摆放方式引入额外翻转"的例外；也正因为如此，修复只能
  改网络连接，不能靠转符号。
- D1 反接对器件可靠性的影响（反向偏置耐压）超出本报告能力：footprint 无此信息，须按具体料号
  （KENTO KT-0603R）数据手册判定，本报告只负责判定"极性接反、正常不亮"。
- U2/U3 的"正确"结论依赖数据手册 pinout（Sensirion SHT3x-DIS / ME6211 V20，均与 KiCad
  官方符号引脚名交叉核对），这些是 ADR-005 已审核过的基线。
- 修复已于 2026-08-31 执行并通过全链验证（见 §5），但**数据级修正 ≠ 制造放行**：
  board_review 仍需人工对照新渲染图与网表重签 `manufacturing_release`，回件后仍需实体 C 级实测。
