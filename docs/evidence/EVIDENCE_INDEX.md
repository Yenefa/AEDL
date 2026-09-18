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

## EVID-20260901-003 — GH-20 LF 字节基线收口（双平台同一测试集）

- 日期：2026-09-01
- 对应主张：LF 声明哈希的文件在 Windows 与 CI/Linux 检出同一字节基线；原 3 个
  CRLF-pinned 测试与 10 个 LF-pinned 哈希绑定在同一测试集内双平台全过，CI 不再
  需要平台排除（`excluded_checks` 为空）。
- 关联模块：`.gitattributes`（选择性 eol=lf / eol=crlf）、`delivery/manifest_v1.json`
  （文本绑定重冻结）、`tests/fixtures/board_review/golden_minimal.json`（LF 基线重生成）、
  `notes/m2-evidence-reset/generated/bom_stock_current.json`（bom_sha256 声明刷新）、
  `tools/dev_gate.py`、`.github/workflows/ci.yml`、`gates/contracts/**` 与
  `src/hardware/edd001-board/evidence/contracts/**`（仅 checkout 表示规范化，git 字节零变化）
- 关联 AI Usage：AI-20260901-011
- 关联 ADR：ADR-011；GitHub Issue #20（Tasks 1-5+9）
- 测试/实验：RED→GREEN 双平台回归。RED：LF 工作树（模拟 CI）上 frozen_golden /
  delivery_manifest_hash / bom_stock_evidence 失败，Windows 上 learning_gate /
  run_gates / 8 个 sandbox EDD-001 绑定失败；GREEN：修复后双平台同一测试集全过。
- 环境：Windows（py -3 = 3.9.13；uv 0.11.32；git 2.54）；LF 工作树以
  `core.autocrlf=false` 检出模拟 Linux/CI。
- 执行命令：
  - `py -3 -S -m unittest discover -s tests`（LF 工作树）→ 282/282 OK
  - `py -3 -m tools.dev_gate --envelope tasks/GH-20.yaml`（Windows）→ PASS exit 0；
    main 282 OK；sandbox 272 OK（1 skip、1 expectedFailure）；secret_scan PASS；
    scope_check PASS；excluded_checks 空
- Runs：RED 捕获每侧 1 轮；修复后 LF 工作树全量 1 轮 + Windows 全量 2 轮（含中间
  gerber 双 CRLF 事故修复轮）。
- 结果：manifest 8 处文本绑定 + 11 个 gerber CRLF 绑定 + golden + FROZEN_PROTOCOL +
  7 处 fault-injection 绑定 + bom_stock 声明全部对齐；M2 Evidence 仓库字节零变化
  （所有 blob 为 LF，工作树规范化 diff-free）；EDD-001 preflight 保持 BLOCKED。
- 原始证据：`delivery/manifest_v1.json`、`tests/fixtures/board_review/golden_minimal.json`、
  `notes/m2-evidence-reset/generated/bom_stock_current.json`；gate receipt 存于仓库外
  （gh20-receipt.json）。
- 是否可复现：YES（本地 Windows ✅、LF 工作树模拟 ✅；GitHub 双平台实际矩阵
  ubuntu ✅ / windows ✅，PR #21 run 33557715205 全绿——同一测试集、零平台排除）。
- 已知限制：矩阵首跑在 windows leg 暴露三个 runner 特有根因并已修复——
  ① setup-uv 仓库根 .venv 遮蔽 `python`（主套件误跑 3.11）；② cp1252 控制台导致中文
  print UnicodeEncodeError；③ TEMP 经 8.3 短名（RUNNER~1）/junction 与混合解析层级
  （abspath vs realpath）导致路径误判（sandbox is_within + 两处测试断言，已改为双端
  realpath，含 junction 回归测试）。修复后双平台全绿。不构成实体硬件验证；
  `notes/m2-evidence-reset/generated/**` 除 bom_stock_current.json 声明刷新外零字节变化。
- 人工核验：`PENDING_HUMAN_REVIEW`

## EVID-20260902-001 — GH-20 尾巴：EDD-001 preflight 组件真源对齐（SS34 + AP63203WU-7 双报出）

- 日期：2026-09-02
- 对应主张：真实 EDD-001 preflight 的组件证据需求集与冻结三合同收敛：按已仲裁
  嵌套声明路径收集 `POWER_SOURCE_SEPARATION.constraint.regulator_3v3.device`（AP63203WU-7）与
  `USB_VBUS_REVERSE_PROTECTION.constraint.device`（SS34）同时报出；bundle manifest
  `missing_requirements` 对齐为 POWER + 5 个组件证据项（新增 SS34_DATASHEET）。
- 关联模块：`sandbox_runtime/src/aedl_sandbox/policy/edd001.py`（`_collect_components`
  增加声明路径白名单：顶层 mpn/device + 已仲裁嵌套 regulator_3v3）、`sandbox_runtime/tests/policy/test_edd001_preflight.py`、
  `sandbox_runtime/tests/trust/test_trust.py`、
  `sandbox_runtime/tests/orchestrator/test_integration.py`、
  `src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json`
- 关联 AI Usage：AI-20260902-003
- 关联 ADR：无；GitHub Issue #20（Tasks 6-7，碰撞 2 envelope `tasks/GH-20.yaml`）
- 测试/实验：RED→GREEN 回归。RED：新回归测试 `test_nested_and_direct_power_parts_are_both_required`
  与 4 处计数断言在修复前失败（AP63203WU-7 缺席：KeyError / 7!=8）；GREEN：声明路径白名单修复后全过。
- 环境：Windows；py -3 = 3.9.13；uv（sandbox runtime，Python 3.11，uv.lock 冻结）
- 执行命令：
  - `uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests -p test_*.py` → 275 tests OK（skipped=1，expected failures=1）
  - `py -3 -m tools.dev_gate --envelope tasks/GH-20.yaml --admit-receipt ..\gh20-collision2-admit.json` → PASS exit 0
- Runs：RED 目标测试 1 轮（4 失败/错误）；GREEN 目标测试 1 轮（4/4 OK）；sandbox 全量 1 轮；dev_gate 全量 1 轮；Review 迭代 1（REQUEST_CHANGES 处置）后 sandbox 全量 1 轮（277 tests）+ admit/gate 重走 1 轮
- 结果：真实 preflight findings 7→8（新增 AP63203WU-7 的 EVIDENCE_COMPONENT_SOURCE_MISSING，
  evidence id ESP32_S3_TECHPEDIA）；manifest missing_requirements 5→6（+SS34_DATASHEET）；
  EDD-001 preflight 保持 BLOCKED（诚实失败关闭）；冻结契约（gates/contracts/** 与
  evidence/contracts/**）仓库字节零变化
- 原始证据：本仓库提交 diff；admit + gate receipt 原件随 review bundle 交付
  （review-bundles/fix_gh-20-preflight-component-truth/，admit-receipt.json /
  gate-receipt.json，二者 envelope_sha256 与最终提交的 tasks/GH-20.yaml 一致）
- 授权链（Review 迭代 1 收口）：重新 admission（envelope 修订后，含 B2/M1 处置与
  budget 对齐）→ ADMIT；final dev_gate 以同一 envelope + 同一 admit receipt 运行 →
  binding_check PASS；三者（提交内 GH-20.yaml / admit receipt / gate receipt）
  envelope sha 一致。首迭代的 hash 矛盾系 bundle 摘要段 glob 收编碰撞 1 遗留 receipt
  所致（详见 AI-20260902-003 Review 迭代 1；遗留 receipt 已归档
  ../receipts-2026-09-01-archive/）。
- 是否可复现：YES
- 已知限制：软件/Evidence 完整性验证，不构成实体硬件验证。SS34 的 evidence id
  ESPRESSIF_S3_LCD_EV_BOARD 已按官方 ESP32-S3-LCD-EV-Board user guide 原理图页
  （Power Supply over USB：D1 = SS34，USB VBUS → USB_5V）在原理图文本级核对成立；
  参数级核对与 SS34 vendor datasheet 冻结仍归 W4A（Issue #2）。组件声明语义为
  白名单路径（顶层 mpn/device + regulator_3v3），引用性嵌套结构不产生 findings
  （负向回归 DeclarationSemanticsTests 锁定）。
- 人工核验：`PENDING_HUMAN_REVIEW`
## EVID-20260902-002 — W4A Collision 1：EDD-001 组件证据 provenance 冻结（元数据级）+ POWER DRAFT

- 日期：2026-09-02
- 对应主张：五份组件资料 + 一份参考设计资料的来源、sha256、字节数、retrieved_at 与
  PDF 元数据已全部钉住（manifest `metadata.remote_evidence` 六条记录，可复核）；其中
  TYPE-C-31-M-12 制造商核实为 Korean Hroparts Elec（LCSC 目录级 + PDF 全文零
  HIROSE/elecfans 反证）；AP63203 datasheet 为 Diodes DS41326 Rev. 3-2（2024-11）；
  POWER 合同草案（DRAFT）以 evidence-first 方式基于该 datasheet 起草。Owner 裁定
  （2026-09-02）：六份 redistribution 全部 TO_VERIFY → binary 不入仓、仅元数据冻结，
  六项 missing_requirements 如实保留（来源债已消，本地冻结债留红）。
- 关联模块：`src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json`
  （metadata.remote_evidence + missing_requirements 描述精化 + notes）、
  `gates/contracts/edd001_power_contract_v1.json`（DRAFT，含 evidence/contracts 镜像）、
  `docs/compliance/THIRD_PARTY_RESOURCES.md`（RES-010）
- 关联 AI Usage：AI-20260902-005（原 004，撞号改号，见台账该条目说明）
- 关联 ADR：无；GitHub Issue #2（W4A）；envelope `tasks/GH-2.yaml`（随 Review 迭代
  多次重绑，机器字段 base.sha 为准；PR #27 描述记录终态 admit/gate 回执）
- 测试/实验：manifest 结构变更（新增 metadata 段）后真实 bundle 测试回归。
- 环境：Windows；py -3 = 3.9.13；uv（sandbox，Python 3.11）；curl 8.x（下载）；
  本地二进制暂存 `../w4a-staging/`（仓库外）
- 执行命令：
  - `uv run --frozen --project sandbox_runtime python -m unittest
    sandbox_runtime.tests.trust.test_trust.RealEdd001ManifestTests
    sandbox_runtime.tests.orchestrator.test_integration.Int01RealEdd001Tests.test_int_01_real_bundle_manifest_is_honestly_partial`
    → 2 tests OK（metadata 段 schema 合法、六项 missing_requirements 保留、PARTIAL 状态不变）
  - sandbox 全量（final gate 内）→ 见 gate receipt
- Runs：下载 6 份（2 份首试为 HTML 反爬页，换 datasheet.lcsc.com 直链后成功）；
  trust/integration 回归 1 轮；final gate 1 轮
- 结果：六条 remote_evidence 记录 sha256/bytes/retrieved_at/PDF 元数据与本地暂存
  二进制逐一核对一致；evidence_status 保持 PARTIAL（诚实）；preflight 行为不变
  （datasheets/ 目录无本地文件，组件 findings 如实保留）
- 原始证据：`../w4a-staging/`（本地暂存二进制，不入 git）+ manifest
  `metadata.remote_evidence`（仓库内可复核 provenance）+ 下载 URL
- 是否可复现：YES（六条 URL + sha256 逐份重新下载可核）
- 已知限制：元数据级冻结不等于本地证据冻结——runtime preflight 的组件 findings
  保持 BLOCKED（诚实）；redistribution 边界公开前须逐份复审（Owner 裁定记录于
  manifest notes）；AP63203 契约 evidence id（ESP32_S3_TECHPEDIA 网页）无法如实
  冻结为本地文件，其 runtime finding 诚实保留
- 人工核验：`PENDING_HUMAN_REVIEW`
### EVID-20260902-002 · Review 迭代 1 更正（2026-09-02）

外部 review 发现 POWER DRAFT 电感值误抄（Figure 2 为 AP63205 绘制，4.7µH 为
AP63205/5V 值）：经冻结 PDF 原文重新核对，DS41326 Rev. 3-2 Table 2 对 AP63203/3.3V
为 **L = 3.9µH**。合同/镜像/manifest/台账已全部改正（allowed_design_range 2.2–10µH
不受影响）；EV 板 corroboration 同步收窄至 power-entry 段（VBUS → SS34 → protected
rail），buck 段证据责任归 datasheet + 冻结拓扑。本条目为更正记录，不替代原
Evidence（其元数据冻结结论不受影响）。

## EVID-20260918-001 — SchGen exposed DEV 格式导入（ingest-only 重切）

- 分类：**DEV_ONLY**；本项是开发记录，不是 `gates/run_gates.py` 正式 Evidence，也不是 preregistered SchGen 实验或制造放行。
- 对应主张：`tools/schgen_native_ingest.py` 能在**不导入任何 AEDL 修复模块**的前提下完成已曝光 DEV 输入的格式导入 —— 只删空的 legacy `(symbol_instances)` 根块，保持源字节与其他全部根形式，对象图（wire/junction/label/symbol/no_connect 清点）不变，并产出可独立复验的 fresh 观察与新清单。
- 模块：`tools/schgen_native_ingest.py`；测试 `tests/test_schgen_native_ingest.py`。
- 环境：Python 3.9.13（本机 `py -3.9`）。本轮**未**调用 KiCad 或 akcli：工具链调用是 `--kicad-cli` 的运行期要求，本 PR 只做单元边界验证。
- 命令 / 方法 / 实数：
  - `py -3.9 -m unittest tests.test_schgen_native_ingest` → **Ran 14, OK**。覆盖：legacy tail 判定与非 8.x 读取器、空导出视图拒绝、library-nested symbol 不计入 placement、删块前后 `graph_sha256` 相等、幂等、非空 instance 元数据拒绝、清单 split/重复/引用拒绝，以及模块 AST 级「不导入任何 `tools.*`」。
  - `py -3.9 -m unittest discover -s tests` 与 `py -3.9 -m tools.dev_gate` → 见 PR 正文回执。
- 原始证据路径：本 PR 的测试文件与其输出。历史 DEV 回放产物仍在 Codex 输出 `outputs/schgen-dev-mainline/`，属 **held 半，未进本 PR**。
- 可复现状态：可复现（纯 Python，无外部工具依赖）。
- 已知限制：真实 KiCad 8.0.9 端到端导入回放 **NOT_RUN**（本轮）。导入变化**不是**电气修复；本 PR 未重新测量任何 ΔJ。chain/score 半未移植，故本 PR 不产生任何修复或配对结论。`--kicad-cli` 的 8.0.9 门禁在真实回放前未经验证。
- 关联：AI-20260918-DSH-C7396AEC9D7DC7BCD22C6337E56A806E；RES-011；`notes/schgen-dev-chain/TASK.md`；已关闭的 PR #74（held 半）。
- **2026-09-18 评审整改轮（同一条目，不新开）**：Owner REQUEST_CHANGES 后闭环两项 P1 绑定缺陷 + 治理字段 + 交付证据。
  - **修复**：raw/request/manifest 全部改为「读一次 → 哈希这些字节 → 用这些字节 parse/写盘」（原实现先 `sha(path)` 再 `shutil.copyfile(path)`，存在 TOCTOU 窗口）；reference 导出不再只看 `net.is_file()`，改为重新读字节 + 只读结构 sanity（单一 `(export ...)` 根、`(nets ...)` 下至少一个 `(node ...)`），未通过不得写入 `evaluation-references.json`；`cross_module` 改 `true`；`export_netlist` 记录 `kicad_cli_sha256` 并在运行后复算。
  - **反向对照（变异测试）**：把绑定处还原为「`sha(path)` + `copyfile`」→ 新增扰动回归 **FAILED (failures=1)**；把 reference 处还原为「只看文件存在」→ 两条 reference 发布回归 **FAILED (failures=1)**。还原修复版后复跑全绿。
  - **真实 KiCad 8.0.9 ingest smoke（已跑）**：二进制 sha256 `8b7f4a889dc8cfb8c3eae1337d64ade2fe0cf1ec5daa87878cc709904378fb26`。
    - Case A（真实已曝光 DEV 生成件 stage1 `Qwiic_Power_Switch_Schematic_v10`，raw sha256 `1d39e5ebbe995d37323c1ae36e22a343f18a77cfee75f3e7602c9e541395b350`）：legacy `LEGACY_INSTANCE_TAIL`（empty=True，5 个后续根形式）→ `READY_FOR_DEV` / `FORMAT_ADAPTER_TRANSLATION` / 对象图不变；fresh netlist **PASS** exit=0 components=3 nets=5 pins=7；ERC **PASS**（6 flags）；prepared sha256 `693cd67b2465ae766f23c8c6134b731f58c7290a56e3276b14e15627ebdf3f5f`。
    - Case B（同一真实产物导入后的字节，无需 translation）：`READY_FOR_DEV` / `UNCHANGED_FORMAT` / prepared 与 original **逐字节相同**；fresh netlist **PASS** exit=0 components=3 nets=5 pins=7；ERC **PASS**。
  - 两次 fresh export 的 XML sha256 不同属**预期**（kicad-cli 导出含 `(date ...)` 时间戳，该哈希只作 provenance、不作比较键；连接性两次一致）。
  - 测试：`tests.test_schgen_native_ingest` → **Ran 21, OK**（首轮 14 + 整改轮 7）。全量 `discover -s tests` 与 `dev_gate` 见 PR 回执。
  - 原始产出：`scratch\schgen-recut\smoke\`（`SMOKE-RESULT.json` + `out-A` / `out-B` 完整 ingestion 记录）。
  - **仍未运行**：scorer、任何 repair、held half、ΔJ、模型调用、正式实验、HELD_OUT 读取。
- 人工核验：PENDING_HUMAN_REVIEW。
