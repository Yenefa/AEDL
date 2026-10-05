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

---

## 六、第四轮（2026-10-05 续）— 几何已证明精确，假设全部排除，**闭环仍未合上**

### F1. 引脚几何已实测确定（这是本轮最硬的结果）

读 `lib_symbols` 里 `Device:R` 的符号定义：

```
pin 1  passive  at (0.0,  3.81) angle 270
pin 2  passive  at (0.0, -3.81) angle 90
```

R9 本体 (34.29, 257.81)，于是**绝对引脚坐标**：

| 引脚 | 绝对坐标 | 角度 | 该点上的 label |
| --- | --- | --- | --- |
| pin 1 | **(34.29, 261.62)** | 270° | `BOOT` @ (34.29, 261.62) |
| pin 2 | **(34.29, 254.00)** | 90° | `+3V3` @ (34.29, 254.00) |

**两片 label 都精确落在 R9 的引脚上**（误差 < 0.01 mm）。
`Device:R` 的**原生引脚轴向是 Y**，所以上一轮「R9 是竖放」的猜测**结论对、理由错**——
它本来就竖放，不需要传 rotation。

### F2. 假设排除表（每条都是实测，不是推断）

| # | 假设 | 实测结果 | 判定 |
| --- | --- | --- | --- |
| 1 | 缺 rotation | instance 块 `(at 34.29 257.81 0)`，无 `rotate` token；原生轴向即 Y | **排除** |
| 2 | 需要补 wire | 冻结板 `wire`=0、`junction`=0，全靠 label 直接压引脚 | **排除** |
| 3 | akcli 归一化引脚几何 | 冻结板与修复板 R9 两个 pin UUID **完全一致** | **排除** |
| 4 | 引脚坐标不一致 | 引脚坐标**实测算出**，与 label 落点误差 < 0.01 mm | **排除** |
| 5 | label 数量不足（只加 2 片不够） | 只加 R9 上的 2 片：仍 fail；加全部 13 片：也 fail | **排除** |
| 6 | label `scope` 不对 | `scope=local` 与省略**行为完全相同**；`scope=global` 被拒（unsupported field） | **排除** |

### F3. 仍然失败的事实

| 变体 | repair rc | 解析 |
| --- | --- | --- |
| 只放 R9，不加 label | 0 | 干净，但 `ESP32_GPIO9_PULLUP` 仍 **fail** |
| 放 R9 + R9 上的 2 片 label | 0 | `label cannot be uniquely attributed to a pin` |
| 放 R9 + 两 net 上全部 13 片 label | 0 | 同上 |
| 同上 + `scope=local` | 0 | 同上 |

### F4. 结论：故障在 `add_net_label` 的**连接语义**，不在几何

几何已被完全证明正确（label 精确压在引脚上），器件身份忠实（pin UUID 一致），
而 akcli 写出的 label 就是无法被 `_source_partitions` 归属。

**最可能的原因（未验证）**：verifier 的归属判定要求 label 与引脚之间存在**连接语义**
（junction / 端点重合且方向一致 / 端点表登记），而 `add_net_label` 只在图纸上放了一个
文字图元，**没有建立 verifier 认可的连接记录**。换句话说：
**akcli 能画出看起来对的图，但 verifier 不认** —— 这是 akcli 与 AEDL verifier 之间的
**语义鸿沟**，不是坐标问题。

### F5. 下一步（三选一，按成本排序）

1. **读 `_source_partitions` 的归属判定源码**，确认它到底要什么（junction？端点表？容差？），
   再照着构造。前置成本最低，且**不动任何冻结逻辑**，只读。
2. 若是语义鸿沟，则该族的**正确解法不是合成夹具**，而是**人工/半自动生成一集真夹具**，
   用 akcli 画、用现有 DC-03 的手法写 repair_ops（它已含能通过 verifier 的连接建立方式）。
3. placement 记录方案**必须带上 verifier 认的连接语义**，否则永远合不上；
   上一轮记的「必须带 lib_symbol 引脚几何」**还不够**，要再加「连接语义」。

### F6. 对 benchmark 范围的影响（不改标记）

闭环未通 ⇒ `episodes_v1.json` 里 DC-03/04/05 的 `solvable_from_frozen_source: false`
**继续保持不动**（其依据已知有误，但改判必须等闭环或等真夹具落地）。

同时要记住：**修复腿失败不影响已确立的正面结论**——
合同在真实板上可满足、缺件夹具可干净合成、纯 net-label 连通，这三条都成立。

---

## 七、第五轮（2026-10-05 续）— **根因找到：`add_net_label` 忽略 `at`，锚到默认坐标**

### G1. verifier 的归属规则（读源码得到）

`gates/repair_verification.py::_source_partitions`：

```python
label_points = {p for p, _ in labels}
wire_points  = {p for wire in wires for p in wire}
...
if label_points - set(positions) - wire_points:
    raise ObservationError("label cannot be uniquely attributed to a pin")
```

即：**一个 label 合法，当且仅当它的点等于某个引脚点，或等于某条 wire 的端点。**
引脚点按 `(position[0] + def["point"][0], position[1] - def["point"][1])` 计算，
单位是**整数纳米**（Y 轴翻转）。

### G2. 根因：坐标根本没落在请求的位置

把冻结板与修复板的 label 坐标（整数 nm）做集合差：

```
pristine labels: 64   repaired labels: 64

修复后新增、冻结板没有的（=嫌疑人）：
   +3V3  (1270000, 6350000)     on_R9_pin = False
   BOOT  (1270000, 6350000)     on_R9_pin = False

被删掉、没还原的：
   +3V3  (34290000, 254000000)  on_R9_pin = True
   BOOT  (34290000, 261620000)  on_R9_pin = True
```

**`add_net_label` 把两片 label 都放到了 (1270000, 6350000) nm = (1.27, 6.35) mm = (50, 250) mil**，
而我请求的是 (34.29, 254.00) / (34.29, 261.62) mm。
**(50, 250) mil 正是 akcli 的默认锚点。**

⇒ **`add_net_label` 静默忽略了 `at` 字段**（rc=0、不报错、但坐标没生效）。

**这一条解释掉了此前**全部**失败**：几何本来是对的、器件身份是对的、label 数量与 scope 都对，
唯一错的是 akcli 把 label 放错了地方。这不是「语义鸿沟」，是 **`at` 参数不生效**。

### G3. 由此得到的两个可执行结论

1. **`place_component` 的 `x_mil`/`y_mil` 是生效的**（R9 确实回到了本体坐标，
   且 pin UUID 与冻结板一致）；**但 `add_net_label` 的 `at` 不生效**。
   两者行为不一致，**不能把 place 成功类推到 label 成功**。

2. **绕开办法（verifier 明确允许）**：归属条件是 `引脚点 ∪ wire 端点`。
   所以可以**先用 `add_wire` 从 R9 的引脚拉一小段正交线，再把 label 放在该线端点上**——
   `add_wire` 的 `pts` 参数在实测中是被真实施加的（rc=0），
   因此这条路径**不依赖 `add_net_label` 的 `at` 是否生效**。
   这是下一步唯一该做的事。

### G4. 对前面结论的连带修正

第五轮之前写的「akcli 与 verifier 之间存在语义鸿沟」**判断过重，现更正**：
不是语义鸿沟，是 **`add_net_label` 的 `at` 参数不生效**这一处具体缺陷。
本节取代第六节的 F4 推断。

同时，「placement 记录必须带 verifier 认的连接语义」这条设计结论**依然成立**，
但含义要收窄为：placement 记录必须能**驱动 `add_wire` 拉到正确端点**，
而不只是给出 label 的落点。
