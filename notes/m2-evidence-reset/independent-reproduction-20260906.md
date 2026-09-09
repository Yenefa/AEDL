# M2 冻结证据独立复现记录（2026-09-06）

> 用途：E4「别人能否复现复用」的第一组实测数据。
> 操作者：Percy（`la4876949-bot`）——**非核心实现者**，符合 E4 对"至少 1 次由非核心实现者操作"的要求。
> 状态：`PENDING_HUMAN_REVIEW`。本文件只记录本次实际执行的结果，不声称整套门禁已复现。

---

## 1. 复现环境

| 项 | 值 |
|---|---|
| 机器 | 与产出冻结证据的机器不同（全新安装，此前从未装过 KiCad） |
| KiCad | **10.0.5**，`winget install --id KiCad.KiCad --version 10.0.5 --exact` |
| 安装路径 | `C:\Users\<user>\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe` |
| 被测源 | `src/hardware/m2-board/m2_board.kicad_sch` / `.kicad_pcb` @ `master` |

**版本选择说明**：winget 默认提供 10.0.6，本次**刻意指定 10.0.5**，与 `delivery/manifest_v1.json` 记录的 `kicad_version: "10.0.5"` 对齐。跨补丁版本可能改变导出格式与哈希，独立复现必须锁同一版本。

---

## 2. 关键发现：安装说明缺一步，会让外部用户看到 39 条假警告

全新安装的 KiCad 在**首次以 headless `kicad-cli` 方式使用时不会初始化全局库表**（该动作原本由 GUI 首次启动触发）。缺这一步时 ERC 结果：

| 阶段 | violations | 内容 |
|---|---|---|
| 补库表**前** | **39** | 全部为 `lib_symbol_issues` (23) + `footprint_link_issues` (16)，例如"当前配置不包含符号库 'power'"、"当前配置中不包含封装库 'Capacitor_SMD'" |
| 补库表**后** | **2** | 见 §3 |

**39 条全部是 warning，0 error**——即与冻结证据的 `0 error` 结论不矛盾，但一个外部用户看到 39 条报错，无法判断是自己环境没配好还是这个设计有问题，**很可能直接放弃**。

**补救步骤**（已同步写入 `docs/competition/OPEN_OUTPUTS.md` 安装章节）：

```
复制 <KiCad安装目录>/share/kicad/template/sym-lib-table
     <KiCad安装目录>/share/kicad/template/fp-lib-table
到   %APPDATA%\kicad\10.0\
```

---

## 3. ERC 复现结果：与冻结证据逐条一致

命令：

```
kicad-cli sch erc --output <out>.json --format json src/hardware/m2-board/m2_board.kicad_sch
```

| | 本次复现 | 冻结证据 `notes/m2-evidence-reset/generated/g2_erc_current.json` |
|---|---|---|
| error | 0 | 0 |
| warning | 2 | 2 |
| 第 1 条 | `footprint_link_issues`：在库 'Package_TO_SOT_SMD' 中找不到封装 'SOT-353' | 同 |
| 第 2 条 | `lib_symbol_mismatch`：符号 'ME6211C33M5' 与来源库 'Regulator_Linear' 中的符号存在差异 | 同 |

两条残留 warning **均指向 U3**（ME6211C33R5G / SOT-353）——即当前 `U3_POWER_THERMAL=BLOCKED` 的同一个器件。SOT-353 不在 KiCad 标准 `Package_TO_SOT_SMD` 库内，属已知状态，不是本次复现引入。

## 4. DRC 复现结果：与冻结证据一致

命令：

```
kicad-cli pcb drc --output <out>.json --format json src/hardware/m2-board/m2_board.kicad_pcb
```

| | 本次复现 | 冻结证据 `notes/m2-evidence-reset/generated/g4_drc_current.json` |
|---|---|---|
| violations | 0 | 0 |
| unconnected_items | 0 | 0 |
| schema | `https://schemas.kicad.org/drc.v1.json` | 同 |
| kicad_version | 10.0.5 | 10.0.5 |

---

## 5. 本次证明了什么 / 没证明什么

**已证明：**

- `kicad-cli` 10.0.5 在一台全新机器上可用；
- M2 的 ERC 与 DRC 冻结证据**可由非核心实现者在不同机器上独立复现**，结果逐条相同；
- 安装说明存在一处真实缺口（全局库表初始化），已定位并补齐。

**未证明（明确不声称）：**

- **`ERC 0 error` 不等于设计正确。** M2 在 PIT-20260830-001 事故当时同样是 ERC 0 error、DRC 0 违规、8 项板级评审 PASS，而 USB D+/D- 接反、SHT30 ADDR 悬空等缺陷同时存在。本次复现只说明"两台机器跑出同样的结果"，不构成任何电气正确性结论。
- 未运行 `gates/run_gates.py` 全套（渲染证据需 kicad-cli 重渲，属另一工作单元）；
- 未做实体板验证；
- 未复现 sandbox 之外的第三方工具链（akcli / jlcpcb / freerouting）。

---

## 6. 关联

- 实验：E4（复现与复用）第一组数据；E1 的环境前置。
- 评分项：S4（实现完成度与可验证效果）、S5（开放成果与复用价值）。
- 任务卡：W1 / P1、P6。
