# Evidence Index

> 本文件索引可验证主张，不替代 `notes/`、测试日志或其他机器生成原始证据。AI 不得手工改写原始 evidence 来制造通过结论。

## EVID-20260829-001

- 日期：2026-08-29
- 对应主张：以 `ae316d9` 为基线的本轮工作树在 AEDL 规范接入和历史测试夹具修复前后，M2 一键门禁均为 7/7 PASS，`manufacturing_release=true`。
- 关联模块：`gates/run_gates.py`
- 关联 AI Usage：AI-20260829-001
- 关联 ADR：ADR-001
- 测试/实验：运行完整 M2 一键门禁。
- 环境：Windows；KiCad 10.0.5；Python 3.9.13
- 执行命令：`py -3 gates\run_gates.py`
- Runs：3（规范接入前 1，接入与测试修复后 1，本地提交前 1）
- 结果：三次均 PASS；exit 0；最终一次运行时间 `2026-08-29T13:55:43Z`；ERC 0 error；DRC 0 violation / 0 unconnected；BOARD_REVIEW 8/8 pass；`manufacturing_release=true`
- 原始证据：`notes/m2-evidence-reset/run_manifest.json`
- 是否可复现：YES（需本机 KiCad 10.0.5 路径可读）
- 已知限制：这是机器门禁与签发证据，不是回件后的实体硬件 C 级实测。
- 人工核验：`HUMAN_REVIEWED`（项目负责人，姓名未提供，2026-08-29）

## EVID-20260829-002

- 日期：2026-08-29
- 对应主张：AEDL v1.0 已进入仓库，并由根 AGENTS、README、HANDOFF 指向项目内规范和五类台账。
- 关联模块：`.gitattributes`、`AGENTS.md`、`README.md`、`docs/HANDOFF.md`、`docs/compliance/`、`docs/evidence/`
- 关联 AI Usage：AI-20260829-001
- 关联 ADR：ADR-001
- 测试/实验：结构、引用、源文件哈希和 Git diff 检查。
- 环境：Windows PowerShell；Git 2.54.0.windows.1
- 执行命令：PowerShell `Test-Path`/文件长度/`Get-FileHash`/入口 token 检查；`git diff --check`；`git diff --cached --check`
- Runs：2（初次接入后 1，本地提交前 1）
- 结果：两次均 PASS；10/10 必需文件存在且非空；规范源文件与项目副本 SHA-256 均为 `ACFB234A669820621306D72ECAE5DF39345C11C765037E781287B1D85A1844BC`；入口引用齐全；规范原文的 Markdown 强制换行空格由单文件 `.gitattributes` 例外保留；工作树与暂存区 diff check 均 exit 0
- 原始证据：项目文件与 Git diff；结构检查输出未单独持久化
- 是否可复现：YES
- 已知限制：仓库规则能约束会读取项目入口的 AI；无法从仓库内部强制一个完全忽略项目文件的外部工具。
- 人工核验：`HUMAN_REVIEWED`（项目负责人，姓名未提供，2026-08-29）

## EVID-20260830-001

- 日期：2026-08-30
- 对应主张：BOM 零库存失败关闭 → 受控换料 → 全链证据哈希重绑定的完整闭环可执行；
  换料后 DRC/board review 机器实测恢复全绿（不含人工签发与实体验证）。
- 关联模块：`gates/refresh_bom_stock.py`、`gates/run_gates.py`、`gates/export_delivery.py`、
  `tools/generate_m2_ops.py`、`tools/board_review.py`、`src/hardware/m2-board/`
- 关联 AI Usage：AI-20260830-002
- 关联 ADR：无
- 测试/实验：U3 换料 C82942→C235316（SOT-23-5→SOT-353）前后全链门禁与单测对比。
- 环境：Windows；Python 3.9.13；KiCad 10.0.5；akcli 0.21.0；jlcpcb 0.1.0
- 执行命令：
  - `py -3 gates\refresh_bom_stock.py`（换料前：FAIL C82942 zero stock；换料后：PASS parts=14）
  - `py -3 gates\run_gates.py`（换料后：8/9 gate PASS，exit 1，唯一 fail 为
    board_review 人工重签待定）
  - `py -3 -m unittest discover -s tests`（77/77 OK）
  - `py -3 gates\export_delivery.py`（PASS rows=21 zip_entries=11）
  - `py -3 tools\generate_m2_ops.py`（PASS op_count=109）
  - `py -3 tools\board_review.py`（8/8 pass，含 U3 重纳入三项检查）
- Runs：换料前基线 1 轮；换料后全链 2 轮（含收敛迭代共 4 次 run_gates）
- 结果：C82942 库存实时为 0（早 5 → 晚 0）触发失败关闭；C235316 库存 3329；
  DRC 0 violation / 0 unconnected；77/77 单测；交付物 21 行哈希绑定。
- 原始证据：`notes/m2-evidence-reset/generated/bom_stock_current.json`、
  `notes/m2-evidence-reset/generated/g4_drc_current.json`、
  `notes/m2-evidence-reset/generated/ops_validate_current.json`、
  `notes/m2-evidence-reset/generated/board_review_auto.json`、
  `notes/m2-evidence-reset/run_manifest.json`、`delivery/manifest_v1.json`
- 是否可复现：YES（库存为外部瞬时状态，复现时数值会变）
- 已知限制：全部为静态/机器证据；board_review 的 manufacturing_release 仍为 false
  等待人工重签；无任何实体硬件验证；C235316 库存随时可能变化，下单前需重刷。
- 人工核验：`PENDING_HUMAN_REVIEW`

## EVID-20260829-003

- 日期：2026-08-29
- 对应主张：历史 ERC/DRC/board review 证据仍稳定按失败关闭处理，不再被当前签发文件的后续变化污染。
- 关联模块：`tests/test_run_gates.py`、`tests/fixtures/board_review_before_release.json`
- 关联 AI Usage：AI-20260829-002
- 关联 ADR：无
- 测试/实验：先用当前可变 board review 复现失败，再切换到签发前冻结夹具运行同一测试。
- 环境：Windows；Python 3.9.13
- 执行命令：`py -3 -m unittest tests.test_run_gates.RunGatesTests.test_historical_evidence_is_reported_as_blocked_not_green -v`
- Runs：2（目标测试 RED 1、GREEN 1）；全量回归另运行 2 次（修复后 1、本地提交前 1）
- 结果：RED 为预期断言失败；GREEN 为 1/1 PASS；两次全量 `py -3 -m unittest discover -s tests -v` 均为 30/30 PASS
- 原始证据：`tests/fixtures/board_review_before_release.json`；夹具来源为提交 `00bf694`
- 是否可复现：YES
- 已知限制：该测试验证结构化证据判定与历史快照隔离，不构成实体硬件验证。
- 人工核验：`HUMAN_REVIEWED`（项目负责人，姓名未提供，2026-08-29）

## EVID-20260901-001 — AEDL-spike Stage 1 历史 native 验证索引

- 索引日期：2026-09-01
- 历史报告日期：2026-08-29
- 对应主张：在边界明确的 smart-plant 逻辑 fixture 中，历史记录完成了 PlatformIO native Build → Launch → Inject → Observe → Assert → Report 闭环；baseline 为 3/3 PASS，四个注入故障变体均被检出。
- 关联模块：`Yenefa/AEDL-spike` 的 `spike1/`
- 关联 AI Usage：AI-20260901-006
- 关联 ADR：ADR-010
- 环境：卫星 `spike1/evidence/environment.json` 记录 `captured_at=2026-08-29T05:23:07Z`、Python 3.9.13、PlatformIO Core 6.1.19、Windows 10、native host backend。
- 执行命令：在卫星仓根目录运行 `py -3 spike1\verification\runner.py`。
- Runs：历史 Evidence 中 1 个完整矩阵；2026-09-01 治理验收另在干净隔离副本重跑 native 矩阵并 exit 0，但未把临时输出登记为新的比赛技术 Evidence。
- 结果：历史 baseline 3/3 PASS；`fault_threshold`、`fault_buzzer`、`fault_display`、`fault_build` 均被检出。
- 原始证据：`Yenefa/AEDL-spike` 冻结基础提交 `e8ce045adff2e6fb9cf87416e85a076af6669c67` 的 `spike1/evidence/`；报告为同提交 `spike1/SPIKE_REPORT.md`。
- 是否可复现：YES（受记录的本地工具链约束；应在隔离副本或新的 Evidence 批次目录运行）。
- 已知限制：仅为 host native 执行；没有 ESP32 目标执行、真实传感器、GPIO/OLED 电气行为或实体硬件验证。
- 人工核验：`PENDING_HUMAN_REVIEW`

## EVID-20260901-002 — AEDL-spike Stage 2 历史双后端与受限修复索引

- 索引日期：2026-09-01
- 历史报告日期：2026-08-30
- 对应主张：历史 fixture 记录 native 3/3 与 Wokwi ESP32-C3 3/3 baseline，检出四个 native 故障变体，并从预设三个候选补丁中选择出阈值修复后记录 Wokwi target-tier 复检。
- 关联模块：`Yenefa/AEDL-spike` 的 `spike2/`
- 关联 AI Usage：AI-20260901-006
- 关联 ADR：ADR-010
- 环境：卫星 `spike2/evidence/environment.json` 记录 `captured_at=2026-08-29T05:49:13Z`、Python 3.9.13、PlatformIO Core 6.1.19、Wokwi CLI 0.26.1、Windows 10。
- 执行命令：在卫星仓根目录运行 `py -3 spike2\verification\runner.py --backend native`、`--backend wokwi` 与 `py -3 spike2\verification\repair.py`。
- Runs：以冻结报告和 `spike2/evidence/` 的历史记录为准；2026-09-01 治理验收只在隔离副本重跑 native 矩阵并 exit 0，Wokwi 与 repair 未重跑。
- 结果：历史 native/Wokwi baseline 均为 3/3；四个 native 故障变体被检出；预设候选池记录一个成功阈值修复。
- 原始证据：`Yenefa/AEDL-spike` 冻结基础提交 `e8ce045adff2e6fb9cf87416e85a076af6669c67` 的 `spike2/evidence/`；报告为同提交 `spike2/SPIKE_REPORT.md`。
- 是否可复现：PARTIAL（native 依赖记录的本地工具链；Wokwi 还依赖网络、凭据和配额）。
- 已知限制：Wokwi 不是实体硬件；外设是逻辑抽象；候选补丁为预设集合，不是 LLM 生成；未做并发或配额 Benchmark。
- 人工核验：`PENDING_HUMAN_REVIEW`
