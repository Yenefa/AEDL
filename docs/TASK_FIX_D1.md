# TASK-FIX-D1：M2 LED 极性反接修复（打板前必修）

> 复制本文件「任务书」整段给你的 AI 即可。这是**打板前必修的确定性 bug**，证据链已由主会话
> 完整验证，见 `notes/m2-evidence-reset/polarity-verification.md`（务必先读）。
> 通用前置：读 `AGENTS.md`（v1.4）+ `docs/COLLABORATION.md`。铁律：不 commit、不改
> `manufacturing_release`、改完跑全量回归并如实报告。

---

## 一、背景与 bug 定位（已查实，无需重新判断）

M2 板（ESP32-C3 + SHT30）的 **D1（红色 LED）极性接反**：阴极 K 接到了驱动信号、阳极 A 接到了 GND，
电流反向，LED 不会亮（3.3V 低于反向击穿，不损坏，只是不亮）。

**证据链**（全部本机文件实测，见 `polarity-verification.md`）：

| 环 | 事实 | 文件 |
|---|---|---|
| KiCad LED 符号 | `pin "1"`=name `K`(阴极)、`pin "2"`=name `A`(阳极)，Sim.Pins `"1=K 2=A"` | `C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\share\kicad\symbols\Device.kicad_sym` |
| footprint | pad1=pin1=K，pad2=pin2=A；Fab 阴极三角标记在 pad1 侧（x≈-0.8） | `...\footprints\LED_SMD.pretty\LED_0603_1608Metric.kicad_mod` |
| intent 网络 | `LED_A=[R4.2, D1.1]`、`GND` 含 `D1.2`、`LED_DRV=[U1.15, R4.1]` | `src/hardware/m2-board/intent_v1.json` |
| KiCad 网表 | `node D1 pin=1 pinfunction=K_1` 在 net `/LED_A` | `notes/m2-evidence-reset/generated/m2_board_current.net.xml` |
| PCB | `D1 pad1 → net "LED_A"`、`pad2 → net "GND"` | `src/hardware/m2-board/m2_board.kicad_pcb` |

反接在 intent / netlist / PCB **三层完全一致地存在**（同一错误延续三层，`schematic_semantics`
四视图校验之所以没拦住，是因为它没有 LED 极性规则——见 §四）。

**正确目标**：`U1.15(GPIO) → R4 → D1 阳极A(pin2) → D1 阴极K(pin1) → GND`
即 **D1.1 应连 GND，D1.2 应连 LED_A**（当前正好相反）。

---

## 二、修复范围（3 个文件 + 级联重导）

### 核心改动（真源 + 两个下游视图，必须三处一致）

1. **`src/hardware/m2-board/intent_v1.json`**（真源）
   - `nets` 里 `LED_A` 数组：`["R4.2", "D1.1"]` → `["R4.2", "D1.2"]`
   - `nets` 里 `GND` 数组：把 `D1.2` 改成 `D1.1`
   - （`LED_DRV=[U1.15, R4.1]` 不动）

2. **`src/hardware/m2-board/m2_board.kicad_sch`**（原理图）
   - D1 符号的两个引脚网络对调：pin1 改连 GND、pin2 改连 LED_A。
   - 具体做法二选一（都行，选改动最小、最不容易引入其他错误的）：
     a) 交换 D1 引脚上的 net label；或
     b) 把 D1 符号整体旋转 180°（若符号朝向允许）。
   - ⚠️ 无论哪种，改完必须保证原理图 netlist 里 D1.1→GND、D1.2→LED_A。

3. **`src/hardware/m2-board/m2_board.kicad_pcb`**（PCB）
   - D1 footprint 的两个 pad 网络对调：pad1 的 `(net "LED_A")` → `(net "GND")`，pad2 的 `(net "GND")` → `(net "LED_A")`。
   - 注意：D1 在 PCB 里 pad1 连 LED_A、pad2 连 GND（见 §一），对调即可。trace/过孔不动（LED 两脚就在同一对铜皮上，只需交换 pad 的网络归属，走线本身无需重布——但请目检确认 D1 周边走线是否真的只连这两个 pad）。

### 级联重导（改完真源后必须做）

4. **`py -3 tools\generate_m2_ops.py`** — 从新 intent 重放 `ops_gen.json`（akcli 0.21.0 路径见 §五）。验证 `add_net_label "GND" at "D1.1"` + `"LED_A" at "D1.2"`。

5. **`py -3 gates\export_delivery.py`** — 重导 Gerber/BOM/CPL/manifest（intent 哈希变了，delivery manifest 的 `sources.intent` 会失效，必须重导）。验证 `rows=21 zip_entries=11`。

6. **重跑 ERC/DRC 证据**：`py -3 gates\run_gates.py`（或按其内部逻辑单独重跑 erc/drc）。

---

## 三、验收标准（逐条可验证）

1. `intent_v1.json`：`LED_A` 含 `D1.2`、`GND` 含 `D1.1`，`LED_DRV` 仍 `[U1.15, R4.1]`。
2. KiCad 网表（重导后）：`node D1 pin=1 pinfunction=K_1` 在 net `GND`（或 `/GND`），`node D1 pin=2 pinfunction=A_2` 在 net `LED_A`。
3. PCB：`D1 pad1 → GND`、`D1 pad2 → LED_A`。
4. `py -3 -m unittest discover -s tests` → **114/114 全绿**（重点：`test_schematic_semantics`、`test_run_gates`、`test_requirements_contract` 不能挂）。
5. `py -3 gates\run_gates.py` → 10 门禁：erc/drc/bom/delivery/intent/ops/schematic_semantics/learning/requirements_contract 全 PASS；board_review 仍 FAIL（`manufacturing_release=false`，这是等人工重签的诚实终态，**不算回归**，不要动它）。
6. 关键：**schematic_semantics 门禁必须 PASS**——它校验 intent/netlist/PCB/firmware 四视图一致，若你只改了 intent 没同步 netlist/PCB，它一定 FAIL。

---

## 四、建议顺带补的防再犯项（选做，若时间允许）

在 `gates/contracts/m2_schematic_contract_v1.json` 加一条 LED 极性规则，让 schematic_semantics 以后能
自动抓这类错误（当前它没有 LED 极性规则，是这次漏网的根因）。规则形如：

```jsonc
{
  "id": "LED_POLARITY",
  "kind": "connectivity",
  "severity": "critical",
  "title": "LED anode to driver, cathode to GND",
  "checks": {
    "intent": { "pins": { "D1.1": {"net": "GND"}, "D1.2": {"net": "LED_A"} } },
    "netlist": { "pins": { "D1.1": {"net": "GND"}, "D1.2": {"net": "LED_A"} } },
    "pcb": { "pins": { "D1.1": {"net": "GND"}, "D1.2": {"net": "LED_A"} } }
  }
}
```

并同步更新 `gates/contracts/m2_schematic_contract_v1.json` 的故障注入夹具（`tests/fixtures/schematic_semantics/`
下的 fault 文件需补一个 LED 反接的负向夹具，让 `semantic_fault_injection` 能自证"校验器能抓住 LED 反接"）。
若这块工作量超出本轮，可只在报告里标注"已修 bug 但防再犯规则留待下轮"，不强行完成。

---

## 五、环境关键事实（前人踩过的坑，务必照做）

- **akcli 0.21.0 绝对路径**：`C:\Users\fuker\AppData\Local\hermes\hermes-agent\venv\Scripts\akcli.exe`
- **KiCad 10.0.5 kicad-cli**：`C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe`
  （pcbnew Python 必须用 KiCad 自带 `C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\bin\python.exe`）
- **run_gates.py / export_delivery.py 若报 unlink/rmtree 被拦**：是 WorkBuddy 的 safe-delete 钩子，用
  `python -S py3 ...` 或换人工终端跑，**不是仓库代码问题**。
- **PowerShell 无 heredoc**，git commit 用 `-F msgfile.txt`。
- 改 kicad_sch/kicad_pcb 的 S-expression 时：字段顺序、引号、层名必须与原文严格一致，改完务必用
  `kicad-cli` 或 ERC/DRC 重跑确认语法没坏。

---

## 六、禁止事项

- 不改 `manufacturing_release`（保持 false，等人工重签）。
- 不 commit / 不 push（改动留未提交，交人工统一审核）。
- 不改 D1 之外的任何器件网络（U2/U3 已核对正确，别动）。
- 不把"改了 intent 就完事"当完成——netlist/PCB 必须同步，否则 schematic_semantics 会 fail。
- 修复后不在报告里声称"LED 现在能亮了"——那是回件 C 级实测的事，只能说"极性网络已按符号定义修正，数据级一致"。
