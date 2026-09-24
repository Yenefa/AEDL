# GH-86 native evidence — pinned akcli 0.21.0

**Status**: dev qualification on disposable scratch copies. **Not** formal Evidence
(`gates/run_gates.py`), **not** human review. `PENDING_HUMAN_REVIEW`.

## Toolchain (host, outside the repo)

```text
interpreter : <workspace>/project_020_AEDL/toolchain/py311/Scripts/python.exe   (Python 3.11.15)
CLI         : <workspace>/project_020_AEDL/toolchain/py311/Scripts/akcli.exe
akcli       : 0.21.0  (dist akcli-kicad 0.21.0)
env         : AEDL_PR1_NATIVE=1, AEDL_AKCLI_PYTHON=<interpreter>
```

## 1. Native regression on the patched adapter

```text
py -3 -m unittest tests.test_akcli_adapter.NativeQualificationTests \
                          tests.test_akcli_adapter.NativePerturbationTests \
                          tests.test_akcli_adapter.NativeP3QualificationTests -v
→ Ran 12 tests ... OK   (exit 0)
```

覆盖：pinned reader 对 DC-01..DC-05 的规范化观察；真实 strict 路由对 DC-04/DC-05 的
逐字节（记录哈希）复现；P1 applied-但-未变 → BLOCKED；P5 strict 拒绝不重试；
P6 symbol digest / version 写前拒绝（draw 调用 0）；P7 单批一次写调用、拆批不等价；
native read 与 C2 source objects 一致；P3 正对照 + 负扰动。

## 2. 本卡新增的原生 presence-mismatch 用例

```text
py -3 -m unittest tests.test_akcli_adapter.NativeRotationPresenceTests -v
→ Ran 2 tests ... OK   (exit 0)
```

- proposal absent / disk explicit 0 → `BLOCKED` / `REPAIR_INPUT_DRIFT`，`draw` 调用 0 次，
  `exit_code is None`，stage 字节不变
- proposal explicit 0 / disk absent → 同上

## 3. 决定性 angle probe —— presence 改变真实写出的原理图

```text
py -3 notes/gh-86/probe_native_rotation_presence.py
raw output: notes/gh-86/probe_native_rotation_presence.txt
```

冻结 DC-04 op-list（rotation **ABSENT**），真实 strict 写入 disposable scratch 副本：

```text
+3V3 at (34.29, 254)     angle=90
BOOT at (34.29, 261.62)  angle=270
```

同一 op-list，仅把 add_net_label 的 `rotation: 0` 显式写出：

```text
+3V3 at (34.29, 254)     angle=0
BOOT at (34.29, 261.62)  angle=0
```

⇒ **presence 在原生层就是执行语义**：两份「规范化等价」的 op-list 写出物理上不同的原理图。
这是 #86 的前提，本轮在 pinned 工具链上**实测复现**，不再只是引用 writer 源码。

## 限制（如实声明）

- probe 只作用于 disposable scratch 副本，冻结夹具逐字节未动；
- 这是 DEV 资格，不是正式 Evidence，也不是人工审核结论；
- 原生用例是 opt-in：未设 `AEDL_PR1_NATIVE=1` 时在 `dev_gate` 中 SKIP（本轮 skipped=15）。
