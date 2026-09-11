# E5 exploratory 缺陷板 01

> 用途：E5 第一段 exploratory 任务（`notes/e5-user-trial/e5-protocol-v1.md` §4）。
> **仅用于校准第二段两 arm 的题目难度，数据不进入 E5 对照表。**

## 目录

```
exploratory-01/
├── participant/                              ← 可交给参与者
│   └── usb_serial_adapter.kicad_sch          唯一需要发出的文件
└── facilitator/                              ⛔ 仅限主持人，整个目录不得外发
    ├── ANSWER_KEY.md                         缺陷位置、判分标准、验证证据、限制
    ├── usb_serial_adapter_correct.kicad_sch  正确参考版
    └── verify/                               可复现生成与验证
        ├── gen_board.py
        ├── symx.py
        └── verify_net.py
```

**发给参与者时只发 `participant/usb_serial_adapter.kicad_sch` 这一个文件。** 不要发整个文件夹 ——
`facilitator/` 里有答案。

## 参与者拿到的是什么

一份自包含的 KiCad 原理图（符号已内嵌，无需额外安装库），用 KiCad 打开即可。
参与者可用任何自己习惯的方法检查，包括运行 ERC。

## 复现验证

`verify/gen_board.py` 从 KiCad 官方符号库生成缺陷版与正确版两份原理图，两版使用同一套确定性 UUID，
因此逐字节 diff 应当恰好只有 2 行不同。`verify/verify_net.py` 对两版导出的网表做 14 项连通性断言。

```bash
# 在 verify/ 目录下
python gen_board.py --variant defect  --out out/defect/usb_serial_adapter.kicad_sch
python gen_board.py --variant correct --out out/correct/usb_serial_adapter.kicad_sch
kicad-cli sch export netlist --format kicadsexpr -o out/defect/net.net  out/defect/usb_serial_adapter.kicad_sch
kicad-cli sch export netlist --format kicadsexpr -o out/correct/net.net out/correct/usb_serial_adapter.kicad_sch
python verify_net.py out/defect/net.net out/correct/net.net
```

> 注：`symx.py` 中的 KiCad 符号库路径写死为 `D:/Program Files/KiCad/10.0/share/kicad/symbols`，
> 在其他机器上复现须改为本机路径。生成结果与 KiCad 版本相关，本板基于 **KiCad 10.0.5**。

## 隔离约束

- **不得**用作 C2 两 arm 的板子（C2 须另行设计）
- **不得**进入 Y4 的任何输入
- 详见 `facilitator/ANSWER_KEY.md` §1
