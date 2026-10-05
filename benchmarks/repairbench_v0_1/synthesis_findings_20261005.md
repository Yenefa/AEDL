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