# RepairBench v0.1 — 合成实验结论（2026-10-05）

> 目的：验证 `add_component` 族能否从**冻结源**合成出「可解」夹具，从而把 headline 分母从 2 提上去。
> 方法：只用 `src/hardware/m2-board/m2_board.kicad_sch`（冻结）、冻结合同、akcli v1 op 词汇表。
> **全程未读取任何 `repair_ops.json`**，未调用模型，0 花费。

## 一、已验证为真的事实

### F1. 冻结合同在真实 M2 板上全 PASS（此前未确立）

对 `src/hardware/m2-board/m2_board.kicad_sch` 跑 v0.1 合同 5 条规则：

| 规则 | 结果 |
| --- | --- |
| ESP32_EN_RC | pass |
| ESP32_GPIO9_PULLUP | pass |
| SHT30_ADDRESS | pass |
| SHT30_UNUSED_PINS | pass |
| USB_POLARITY_AND_SERIES | pass |

**意义**：合同不仅在合成夹具上自洽，**在真实冻结产物上也全部满足**。这是「合同可满足性」的直接证据，
此前 RepairBench 只证明了合同能判夹具的错，没证明它能判真实板的对。

### F2. 夹具基座确认

该板 62825 字节，与 `DC-01/fault.kicad_sch` **同字节数但非同一文件**（已做全字节比对）。
即 DC-01 是从这块冻结板派生、改动了 USB 相关标签。

### F3. 缺件夹具可以干净地合成出来（关键结论）

从冻结板出发，一条批次即可得到「恰好违反一条规则、其余四条仍 pass」的夹具：

```
delete_component(designator="R9")
delete_object(uuid=<R9 所在 net 上的 13 个 label>)
→ rc=0
→ 解析干净（不报错）
→ ESP32_GPIO9_PULLUP = fail，其余 4 条 = pass
```

**这正是 benchmark 想要的一集**：目标规则 fail、非目标规则不受影响（regression guard 有意义）。

### F4. label 是可寻址的 source object

`observe_source` 暴露 72 个 `kind == "label"` 的 source_object，各自带 `identity` UUID 与
`descriptor.ast`。对 label UUID 执行 `delete_object` 返回 **rc=0 / applied**，即
**akcli v1 允许删 label**——这是 F3 能成立的前提。

### F5. 孤儿标签会让解析 fail-closed（这是对的，不要改）

只删 R9 不删其 label 时，解析直接失败：
`ObservationError: label cannot be uniquely attributed to a pin`。
**这是正确的 fail-closed 行为**，不是 bug。含义：任何「删件」型夹具必须同时清理该件的 net label。

### F6. akcli v1 op 词汇表（本次实测确认）

- `delete_component`：required `designator`
- `delete_object`：无必填字段，按 UUID
- `add_net_label`：required **`name`, `at`**（不是 `net` / `x_mil`）
- 另有 `add_wire` / `add_junction` / `add_text` / `move_component` / `add_no_connect` 等

## 二、仍未解决的阻塞（精确定位）

**修复腿没有闭环**：`place_component` + 把 13 个 label 按**记录坐标**全部放回后，解析**仍然 fail-closed**。

已排除的可能：
- 不是 op 字段错（`repair rc=0`，全部 applied）
- 不是 label 坐标缺失（13 个坐标全部从冻结板实测记录）
- 不是 label 重复（按 (name,x,y) 去重）

**最可能的原因（下一步要验证的，就这一件事）**：
`place_component` 调用时**没有传旋转角**。实测几何证据：

```
R9 本体中心      (34.29, 257.81) mm
R9 的两个 net label  (34.29, 254.00) 与 (34.29, 261.62) mm
                 → 相对本体是 ±3.81 mm 的 **Y 方向**，说明原 R9 是**竖放**（旋转 90°）
```

若 `place_component` 按默认 0° 放置，引脚会落在 **X** 方向，两片 label 就仍然贴不到任何引脚上，
解析继续 fail-closed —— 与实测现象完全一致。

**下一步（单一动作）**：从冻结 schematic 的 symbol instance 里取出 R9 的 `rotate` 值，
作为 `rotation` 传给 `place_component`，重跑闭环。

### 顺带确认的一件事（对 ADR-023 有意义）

答案键 `acceptance_v1.json` 里 R9 的坐标是 (34.29, 257.81)，而冻结 schematic 里 R9 的本体坐标
换算后**正是** (34.29, 257.81)（1350 mil × 10150 mil）。
**所以 `schematic` 与 `acceptance` 之间其实不存在坐标系不一致**——此前
`placement_source_audit_20261005.md` 判定的「坐标系不一致」结论**是错的**，
真正的原因是：**冻结 PCB（`.kicad_pcb`，mm）用的是另一套坐标**，而 schematic 与 acceptance 之间是对齐的。
该错误结论必须更正，否则会一直误导「add_component 不可解」的判断。

## 三、对路线的影响

- `add_component` 族**并非不可解**，只是「缺一个 placement 真源 + 缺合成器」。F3 已经证明合成器能做对。
- 因此 `episodes_v1.json` 里 DC-03/04/05 的 `solvable_from_frozen_source: false` **判定依据有误**，
  应在拿到 rotation 后重判。
- 真正的长期解仍是：给每集一份**与 schematic 同坐标系**的 placement 记录，作为公开输入而非答案键。
  F3/F4 已证明这条路径技术上成立。
---

## 四、第二轮诊断（2026-10-05 续）— 推翻两个自己的假设，定位到最后一个未知

上一节把「修复腿失败」最可能的原因归给**旋转角**。实测**否定了它**，同时也否定了「缺线」这一猜测。
两处都靠实测而非推断纠正。

### D1. 旋转角假设：不成立

`place_component` 的模板确有 `rotation` 字段，但 R9 的 instance 块是：

```
(symbol (lib_id "Device:R") (at 34.29 257.81 0) (unit 1) (uuid "e51b8115-...") ...)
```

**没有 `rotate` token**，`at` 的第三分量就是 `0`。即原件按符号**原生方向**放置，旋转角就是 0。
「R9 是竖放所以要传 90°」这个推断**是错的**——实测数据里两个 net label 在
(34.29, 254.00) 与 (34.29, 261.62)，相对本体 (34.29, 257.81) 是 **±3.81 mm 的 Y 方向**，
这与**符号原生方向就是 Y 轴排布**一致，不需要任何旋转。

### D2. 缺线假设：不成立（而且揭示了一条重要事实）

数冻结板与故障板的图元计数：

| 图元 | 冻结板 | 故障板 | 变化 |
| --- | --- | --- | --- |
| `(wire` | **0** | **0** | +0 |
| `(label` | 72 | 59 | −13（我删的那 13 个） |
| `(junction` | **0** | **0** | +0 |
| `(no_connect` | 14 | 14 | +0 |
| `(symbol` | 48 | 47 | −1（R9） |

**冻结 M2 schematic 里一条 wire 都没有，全部连通性靠 net label 直接压在引脚上。**
所以「修复腿需要补 wire」是错的，`delete_component` 也没有连带删线（本来就没有线）。

这条事实本身很重要：它说明本项目的 schematic 是**纯 net-label 连通**风格，
任何「补连通」的修复动作都是 **放件 + 加 label**，不含画线。

### D3. 已确认的两条

1. **只放 R9、不加 label：解析干净，但规则仍然 fail**（`ESP32_GPIO9_PULLUP = fail`）。
   ⇒ 合同的该规则**不只看器件存在性**，还要求 net 连通被恢复。器件在场是不够的。
2. 第一个破坏引脚归属的 label 是 **`+3V3` @ (34.29, 254.00)**，距本体 3.81 mm。
   单独加它就立刻 `label cannot be uniquely attributed to a pin`。

### D4. 剩下的唯一未知（不再猜，给出判定方法）

既然器件位置、label 坐标、旋转、线段都已排除，剩下唯一可能的差异是：
**`place_component` 复原的 R9 引脚几何与冻结原件不完全一致**，导致 label 落点不再精确压在引脚上。

**判定方法（下一步唯一动作，二分对照，不需再试错）**：
把冻结板与「故障板 + place_component」两份文件分别过 `observe_source`，**逐个比较 R9 两个 pin 的
坐标**。若不一致，说明 akcli 放置时对符号引脚几何做了归一化；
若一致，则问题在 label 的落点精度（`at` 的浮点表示），需按引脚实际坐标而非 label 原始坐标放置。

**无论哪种结果，都必须先记录再改判**：在 pin 坐标对照出来之前，
`episodes_v1.json` 里 DC-03/04/05 的 `solvable_from_frozen_source: false` 保持不动。

---

## 五、第三轮（2026-10-05 续）— 上节给的判定方法**跑不了**，这本身是结论

上节说「对冻结板与修复板分别跑 `observe_source`，逐个比较 R9 两个 pin 的坐标」。
**这条判定方法不成立**：公开观测接口**根本不暴露引脚坐标**。

### E1. 实测：pin 记录里没有坐标

`observe_source` 给出的 R9 引脚记录，全部字段就这些：

```json
{
  "identity": {
    "sheet_path": "/a1dbe1c3-...",
    "component_uuid": "e51b8115-84f9-5f14-a897-a0902a20c188",
    "reference": "R9", "unit": 1, "number": "1",
    "pin_uuid": "5978f337-b389-53af-847b-c1bcf574e831"
  },
  "name": "", "electrical_type": "passive", "no_connect": false,
  "partition_key": "92ee5e99..."
}
```

**没有 `position`、没有 `at`、没有任何坐标字段**，只有一个 `partition_key`（连通分区哈希）。
所以「比较 pin 坐标」这件事**用公开接口做不到**——上节的方案是错的，现在更正。

### E2. 实测：`place_component` 的器件复原是**忠实**的

对比冻结板与「故障板 + place_component」的 R9 引脚身份：

| | pin 1 | pin 2 |
| --- | --- | --- |
| 冻结板 | `5978f337-b389-53af-847b-c1bcf574e831` | `1d2f7ac5-6329-54fc-8211-e2563b186f43` |
| 修复板 | `5978f337-b389-53af-847b-c1bcf574e831` | `1d2f7ac5-6329-54fc-8211-e2563b186f43` |

**两个 pin 的 UUID 完全一致** ⇒ `place_component` 保留了符号实例身份，
器件层面的复原**不是**故障来源。这条把「akcli 放置时归一化了引脚几何」这个可能性**排除掉了**。

### E3. 于是剩下的唯一未知收窄为一句话

既不是器件位置、不是旋转、不是线段、也不是器件身份，那么只剩：
**R9 符号的原生引脚轴向是 X 还是 Y，以及两片 label 的落点是否精确压在引脚坐标上。**

R9 的 instance 块**不含引脚坐标**（`(symbol (lib_id "Device:R") (at 34.29 257.81 0) (unit 1)
(uuid ...) (pin "1" (uuid ...)) (pin "2" (uuid ...)) ...)`）——引脚偏移藏在 schematic 的
`lib_symbols` 段里。**所以要判定轴向，必须去读 `Device:R` 的 lib_symbol 定义**，
而不是从 instance 或观测接口里取。

**下一步（唯一动作）**：解析冻结 schematic 的 `lib_symbols` 中 `Device:R` 定义，
读出 pin 1 / pin 2 的 `(at x y angle)`，据此算出 R9 两个引脚的实际坐标，
再判断 (34.29, 254.00) 与 (34.29, 261.62) 是否**恰好**落在引脚上：

- 若**不是**落在引脚上 → 那两片 label 本来就不属于 R9，需要找出它们真正所属的引脚
  （很可能是同 x 的其他元件引脚），故障合成时就不该删它们。
- 若是**落在**引脚上、只是浮点表示不一致 → label 的 `at` 要按引脚计算值给，而不是按 label 原坐标给。

### E4. 这一轮的净结论

- 修复腿的失败**不在器件层**（身份已验证忠实）。
- 上节的判定方法**不可用**，已更正。
- 合成器的 placement 记录**必须包含 lib_symbol 的引脚几何**（或直接包含引脚坐标），
  否则无法在不读答案键的前提下放置 label。这是「自带 placement 记录」方案的**必要条件**，
  之前的设想（只记器件位置 + net 名）**不够**。
