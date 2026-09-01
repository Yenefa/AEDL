# M2 CPL 旋转审计报告（打板前核对）

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
