# M2 CPL 旋转审计报告（打板前核对）

> ⚠️ **过期提示（2026-09-03，AI-20260903-002）**：以下 2026-08-31 原文（rev1）的核心前提已过期——
> D1 已在 AI-20260831-007（TASK-FIX-D1）极性三层修复中被原地旋转 180°，当前 PCB 与 CPL 均为
> **180° 而非 0°**；且本机 KiCad 库（`C:\Users\fuker\...`）已不存在，rev1 §2 的库路径不再可用。
> rev1 原文一个字未删，仅加本横幅；**现行有效结论见文末 §7（rev2，2026-09-03 数据级实测）**。

> 日期：2026-08-31
> 任务：TASK-CPL — 核对极性器件在 CPL（pos.csv）中的旋转角度是否会导致贴片方向错误
> 方法：本机 KiCad footprint 库逐器件读 pin1/极性标记方位 + 比对 PCB 与 CPL 旋转 + 联网核实 JLC 约定
> 证据标记：`已验证`（本机读文件/库实测）/ `待核实`（搜索通道受限，不据此断言）
> 搜索通道状态（如实记录）：豆包 500 次额度耗尽（次月重置）、Go 网关缺 OPENCODE_API_KEY；
>   JLC 官方帮助页经 WebFetch 可访问但**未给出数字偏移表**。

---

## 0. 一句话结论

**5 个方向敏感件 + U1 全部旋转角 = 0°（PCB 与 CPL 完全一致）。0° 旋转在 KiCad→JLC 的 Y 轴翻转下不变，因此"旋转偏移"这一类错误对这块板基本不适用。** 残余风险收敛为一件可验证、可操作的事：JLC 库件（LED C2286、LDO C235316 等）自身的 pin1 朝向是否与 KiCad 原生 footprint 一致——这需要 JLC 组件库数据，本机拿不到，建议用两条不依赖该数据表的兜底路径核实（见 §4）。

---

## 1. 已验证：旋转角全为 0°，PCB 与 CPL 无内部矛盾

| 位号 | 器件 | PCB `at` 旋转 | CPL Rotation | 一致? |
|---|---|---|---|---|
| U1 | ESP32-C3-WROOM-02 | 0 | 0.000000 | ✅ |
| U2 | SHT30 DFN-8 | 0 | 0.000000 | ✅ |
| U3 | ME6211C33R5G (SOT-353) | 0 | 0.000000 | ✅ |
| J1 | USB-C HRO TYPE-C-31-M-12 | 0 | 0.000000 | ✅ |
| D1 | LED 0603 (KT-0603R) | 0 | 0.000000 | ✅ |

数据来源：`src/hardware/m2-board/m2_board.kicad_pcb`（S-expr `(at x y rot)`）与 `delivery/pos.csv`。
两者旋转字段逐位号一致，**不存在"PCB 里转了、CPL 里没转"或反之的内部错位**。

---

## 2. 已验证：footprint 0° 朝向（本机 KiCad 10 官方库逐器件读 pad 坐标）

| 位号 | footprint | pin1/极性在 0° 时的方位 |
|---|---|---|
| U3 | `SOT-353_SC-70-5` | pin1 在 (-0.8375, -0.65) 即**左下角**；pin5 右下、pin3 左上、pin4 右上 |
| D1 | `LED_0603_1608Metric` | pad1 在左（x=-0.7875）、pad2 在右；阴极条丝印标记在 pad1 一侧（x≈-1.485） |
| U2 | `Sensirion_DFN-8-1EP_2.5x2.5mm_P0.5mm_EP1.1x1.7mm` | pin1 在 (-1.175, -0.75) 即**左上角**；pad9 为中心 EP |
| J1 | `USB_C_Receptacle_HRO_TYPE-C-31-M-12` | A1/B1 在 y=-4.045 一端（连接器一侧） |

库路径：`C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints\`（逐文件读，非训练记忆）。
**要点**：这些 footprint 均自带 pin1/极性丝印标记（`M2板级工程评审.md` 也已确认"J1/U2/U3/D1 均有
pin1/极性标记"），所以"图上看不到标记"的问题——第一轮目检的 U3 找不到 pin1——是过期图所致，footprint
库里标记是齐的。

---

## 3. 已验证：Y 轴翻转只影响非 0° 旋转，0° 不变（第一性原理）

pos.csv 里器件 Y 坐标是负值（如 J1 在 y=-5.3），而 board_review 读 PCB 原文得到正 y=+5.3——
这是 KiCad 位置文件导出的标准行为（PCB 内部 +Y 向上，位置文件按 JLC 约定 +Y 向下翻转）。

**推论**：Y 翻转会让 90° CCW 变 90° CW（旋转符号反号），但对 **0° 旋转无影响**——0° 在任何坐标系下
都是"不转"。既然 5 个极性件 + U1 全是 0°，"旋转偏移"这类错误对这块板**结构性不适用**。

---

## 4. 待核实：JLC 库件自身 pin1 朝向（唯一残余风险）

真正还差的一环：JLC 贴片机拿的是它自己组件库里的零件（BOM 里 LCSC 码 C2286 红 LED、C235316 LDO 等），
CPL 的 Rotation 告诉机器"把 JLC 库件转多少度对齐到我的 footprint"。正确性取决于：

```
我的 footprint 的 pin1 方位（已验证 §2）  vs  JLC 库件自身的 pin1 方位（本机拿不到）
```

若两者 pin1 朝向一致 → 0° 正确；若 JLC 库件 pin1 相对我的 footprint 转了 90/180° → 需要补偿旋转。
这个"JLC 库件 pin1 方位"需要 JLC 组件库数据，本机无（需 JLC API/CLI 或官网逐个查）。

**JLC 官方文档的定性确认**（WebFetch 已验证）：JLC 明确推荐用 Fabrication Toolkit 插件并勾选
"Apply automatic component translations (this fixes part rotations/positions for JLCPCB)"——
这个选项的存在本身就是证据：KiCad 默认导出与 JLC 之间**确实存在旋转/位置差异需要修正**。
但该页面**未给出数字偏移表**，无法据此判断 0° 件是否需要修正。

---

## 5. 两条不依赖"旋转表"的兜底核实路径（推荐，可立即执行）

1. **Fabrication Toolkit 重新导出**（首选）：在 KiCad GUI 装 Fabrication Toolkit 插件，勾选
   "Apply automatic component translations"，重新生成 CPL。这是 JLC 官方认可路径，插件内置了
   KiCad→JLC 的旋转对照，直接把正确的旋转角写进新 CPL。与本 pos.csv 对比即可看出哪些件被修正了。
2. **JLC 下单 DFM/装配预览目检**（终极真值）：JLC 下单流程在付款前会渲染**装配图**（每个器件
   贴好后的朝向）。人直接看装配预览，逐个核对 D1 阴极/U3 pin1/U2 pin1/J1 朝向——这是不依赖任何
   旋转表的 ground truth。若有方向错误，预览里直接可见。

两条路径都委托给 JLC 自己的工具/预览，不需要我拿到 JLC 组件库数据。

---

## 6. 结论与建议

- **已排除的错误**：CPL 与 PCB 旋转不一致（无）、极性件非 0° 旋转导致的 Y 翻转偏移（无，全 0°）、
  footprint 缺 pin1/极性标记（无，库内齐全）。
- **未排除的残余风险**：JLC 库件自身 pin1 朝向与 KiCad footprint 是否一致（`待核实`）。
- **建议动作**：打板前走 §5 的两条兜底路径之一。**最低成本是第 2 条**——下单时看 JLC 装配预览
  目检方向，零额外工具、零前置知识。

---

## 附：诚实边界

- 本报告未拿到 JLC 组件库数据，因此"0° 是否正确"的**最终结论是待核实，不是通过**。
- 搜索通道（豆包/Go 网关）均不可用是客观事实；JLC 数字偏移表未取到。
- 未修改 pos.csv 或任何交付文件（本报告仅审计）。
- 若 Fabrication Toolkit 重新导出后发现某件旋转值变化，应以新导出的 CPL 为准并重跑门禁。

---

# §7 rev2（2026-09-03，AI-20260903-002，WorkBuddy Worker 会话）

> 任务卡 AEDL-CPL（AEW 派发）。方法变更：本机无 KiCad（旧机 `fuker` 路径不存在、无
> `kicad-cli`、仓库无 `.kicad_mod`），按任务卡 §3.1 修正后的替代方案，改从 in-repo
> `src/hardware/m2-board/m2_board.kicad_pcb` 直接解析 pad 坐标 + 网络名 + 丝印几何，
> 数据级还原 footprint 0° 朝向。全部为本次实测读文件，非训练记忆。
> 与 rev1 的关系：rev1 结论「全 0°」基于修复前的旧 PCB；D1 极性修复（AI-20260831-007）
> 后 D1 已旋转 180°，rev2 以当前快照 `5c1dff5`/工作树为准重新逐器件核对。

## 7.1 逐器件三要素对齐（6 器件，当前工作树实测）

| 位号 | footprint 0° 朝向（pin1/极性标记方位 + 推断依据） | CPL Rotation | JLC 是否需修正 | 结论 |
|---|---|---|---|---|
| D1（LED 0603，KT-0603R/C2286） | 0° 时 pad1 在 -X（-0.7875,0）= **阴极 K**、pad2 +X=阳极 A；丝印极性条在 -X 侧（x=-1.485 竖线）；依据：PCB pad 坐标+网络（pad1→GND）+fp_line 丝印几何（`m2_board.kicad_pcb` L2967+） | **180.0**（pad1 落板坐标 +X 侧 GND 铜皮） | 无.rotation_correction_applied=false（manifest），无逐件偏移表 → `待核实`（7.3） | **PCB↔CPL 一致；极性方向已由 TASK-FIX-D1 全链修复并经人工复核（rev3 承认书冻结）→ 对** |
| U2（SHT30，DFN-8-1EP/C2687423） | 0° 时 pin1=(-1.175,-0.75)=**左上角**（-X,-Y），pin1 角有实心三角丝印 fp_poly(-1.65,-1.05)；pin2=GND、pin4=SCL 左列，pin5=+3V3 右列，pin9=中心 EP 接 GND；依据：PCB pad 坐标+网络+丝印三角（L2276+） | 0.0 | 同上 `待核实` | **PCB↔CPL 一致；I²C/电源网络映射符合数据手册（既有 schematic_semantics PASS + polarity-verification §"U2 方向正确"）→ 对** |
| U3（ME6211C33R5G，SOT-353/C235316） | 0° 时 pin1=(-0.8375,-0.65)=**左下角**，pin1-3 左列（+5V/GND/+5V），pin5 右下=+3V3；依据：PCB pad 坐标+网络（L966+） | 0.0 | 同上 `待核实` | **PCB↔CPL 一致；引脚序 pin1=VIN/pin2=GND/pin3=CE/pin5=VOUT 与 V20 datasheet 一致（AI-20260831-010 冻结原件人工核过）→ 对** |
| J1（TYPE-C-31-M-12/C165948） | 0° 时 A1/B1 GND 焊盘列在 -Y（y=-4.045）一端，A4/A9/B4/B9=+5V、A5=CC1、B5=CC2、A6/B6=DP、A7/B7=DM；4 个 SH 屏蔽孔接地；依据：PCB pad 坐标+网络（L1886+） | 0.0 | 同上 `待核实` | **PCB↔CPL 一致；USB 极性（DP/DM/CC1/CC2）经 PIT-20260830-001 修复 + schematic_semantics PASS → 对** |
| U1（ESP32-C3-WROOM-02/C2934560） | 0° 时 pin1=(-8.75,-6.0)=**左侧上端**（-X 列 pin1-9 自 -Y 向 +Y：3V3/EN/SDA/SCL/…/GND），pin10-18 右列，pin19=背面接地焊盘阵列；天线区在本地 -Y 端（courtyard 延伸至 y=-18.35）；依据：PCB pad 坐标+网络+courtyard 几何（L3454+） | 0.0 | 同上 `待核实` | **PCB↔CPL 一致；天线朝板边（board_review antenna 项按本地 -Y 判定）→ 对** |
| 复核件：SW1/SW2（TS-1088R-02026/C455280） | 0° 时 pad1=-X（-2.225,0）、pad2=+X；无电子极性但有触点朝向；依据：PCB pad 坐标（L1493/L2720） | 0.0 / 0.0 | 同上 `待核实` | **PCB↔CPL 一致；机械件无贴反风险，rotation 无关紧要 → 对（低风险）** |

复核件说明：任务卡第 6 件未指名，取 BOM 中剩余的两个非纯无源且带 pad1 语义的 SW1/SW2 补位（其余 R/C 为对称无源件，0°/180° 电气等效，不在极性风险内；C5/R7/R8/R9 的 90°/180° 旋转同为对称件摆放需要，已并入 §7.2 全量核对）。

## 7.2 全量 21 行核对（CPL ↔ PCB 旋转逐位号一致）

脚本解析 `m2_board.kicad_pcb` 全部 21 个 footprint 的 `(at x y rot)` 与 `delivery/pos.csv`
逐行比对：**21/21 旋转完全一致，0 个 mismatch**；坐标 Y 满足 `pos_Y = -PCB_Y`
（KiCad 位置文件 +Y-up → JLC CPL +Y-down 的标准翻转），X 完全相等。
即：不存在「PCB 里转了、CPL 没转」或反之的内部错位；D1 的 180° 已正确带入 CPL。
导出链复核：`gates/make_jlc_cpl.py` 仅做格式转换，Rotation **原样拷贝不修正**
（docstring 明言 no rotation correction），`export_delivery.py` manifest 的
`rotation_correction_applied: false` 与此一致——CPL 数字 = KiCad 旋转数字。

## 7.3 JLC 旋转约定联网取证（本次新增出处）

| 断言 | 状态 | 出处 |
|---|---|---|
| JLC CPL Rotation 列「正值为逆时针（Positive values are counter clockwise）」 | **已核实**（官方原文，WebFetch 抓取） | JLCPCB Help Center《Pick & Place File for PCB Assembly》：https://jlcpcb.com/help/article/46-pick-place-file-for-pcb-assembly |
| JLC 官方文档未定义 0° 的参考朝向（pin1 位置无官方文字） | **已核实（缺席性事实）** | 同上页面全文：仅规定 Designator/Mid X/Mid Y/Layer/Rotation 四要素与 mm 单位，无 0° 定义 |
| KiCad↔JLC 逐件旋转修正表（哪类封装偏多少度） | **待核实** | JLC 帮助中心多页抓取均无数字偏移表（PCBA Files Preparation 系列页面正文为空壳/账户限制页）；KiCad 官方 docs 对 .pos 文件 Rot 的符号约定未在可达章节内给出。社区工具（Bouni/kicad-jlcpcb-tools README 自认"JLCPCB seems to need corrected rotation information"，修正表源自 matthewlai/JLCKicadTools）**间接证明差异存在**，但表本体本轮未取到，不引用其数字 |
| KiCad 侧 0° 朝向 = footprint 库文件原始朝向（pad 几何即 0°） | **已核实**（文件级事实） | S-expression `(at X Y [ANGLE])` 语义：ANGLE 为对象相对库文件原始几何的旋转角（dev-docs.kicad.org sexpr-intro「at token defines the positional coordinates and rotation of an object」）；本报告 7.1 的 0° 方位即库文件几何本身，不依赖外部库文件 |

方向关系推论（第一性原理，7.3-1+7.3-4 组合）：KiCad 与 JLC 旋转同为 CCW 正号
→ 同号无符号翻转问题；唯一系统性差异源是位置文件 Y 轴翻转（7.2 已实测存在于本链路），
Y 翻转使 90°↔270° 语义互换、90°/270° 件在 JLC 预览中左右镜像，但 **0°/180° 不受影响**
（0° 恒等；180° 在任何手性下都转到对侧）。本板 5 个极性件 + U1 + SW×2 全部落在
{0°, 180°}，C5/R7/R8/R9 四个 90° 件均为对称无源件（0°/180°/90°/270° 电气等效），
故 Y 翻转对**电气方向无影响**——这一推论把 rev1 §3 的定性判断升级为覆盖全 21 行的枚举结论。

## 7.4 残余风险与兜底路径（沿 rev1 §4/§5，未变化的部分不再重写）

- 残余风险不变：JLC 库件自身 pin1 朝向 vs KiCad footprint 是否一致（`待核实`，需 JLC 组件库数据）。
- 兜底路径仍以 rev1 §5 两条为准：① Fabrication Toolkit 重导对比；② **下单前 JLC 装配预览目检（最低成本、ground truth）**。
- 新增第 3 条（本轮顺带发现）：`delivery/pos.csv` 的 Y 取负映射与 0°/180° 全量一致性已被脚本核对，若未来重导 delivery，可直接重跑该核对（本会话脚本存于仓库外任务卡目录，未入仓）。

## 7.5 rev2 结论（替代 rev1 §0 的一句话结论）

**6 器件（D1/U2/U3/J1/U1/SW 复核）PCB↔CPL 旋转全部一致、全 21 行零错位、5 极性件+U1 全落 {0°,180°} 免疫 Y 翻转，已知系统性旋转错误类全部排除；JLC 官方"正值为逆时针"有出处，JLC 库件自身 pin1 朝向仍 `待核实`——打板前用 rev1 §5 路径②（装配预览目检）兜底。**

## 附：rev2 诚实边界

- 本机无 KiCad：`kicad-cli` 渲染、官方 `.kicad_mod` 直读、Fabrication Toolkit 实操均 NOT_RUN。
- JLC 数字偏移表未取到：不影响本板结论的成立（全部落在免疫区间），但该表本身仍是 `待核实`。
- 未改 `delivery/pos.csv` 及任何交付文件；冻结证据零触碰；本报告为 rev1 的追加修订（rev1 原文未删改一字，仅加横幅）。
