# AEDL Strategic Reality Check（2026-10-02，只读审计）

> 基线：`origin/master @ 6deb848`（PR #119）。审计分支代码与之完全一致。
> 方法：三路并行只读审计（contracts / episode 真实性 / evidence 与 legacy），零修改。
> 原则：Repository truth > README narrative > Issue description > Agent memory。

```text
AEDL STRATEGIC REALITY CHECK
```

## A. Current Reality（仓库实际具备的能力）

- **Episode 管道存在且是真的**：`tools/run_arh_episode.py:49-60` 装配 `NativeEpisodePorts`
  同时当 executor 和 verifier；verifier 在 `nativeports.py:209-221` 做 fresh KiCad
  export（`repair_verification.fresh_export`）再按合同判定，`_parse_netlist` 读的是
  落盘的 `after.net.xml`，不是内存自报。
- **但只接了一道题**：`nativeports.py:111` 写死 DC-02 路径，`:119` 写死
  `SHT30_ADDRESS`。`DC-01/03/04/05` 在 `sandbox_runtime/src` 下零引用，无可执行判据。
- **合同现状**：M2 合同 5 条规则（`m2_schematic_contract_v1.json:12,78,92,112,142`）；
  EDD-001 侧仅 `core_base` 标 FROZEN（`:7`），pin/usb 无 status 字段，power 仍 DRAFT（`:6`）；
  manifest `PARTIAL / NOT_READY / NOT_RUN`（`:6-8`），6 项缺口未动；`policy/edd001.py:456-457`
  compilers/verifiers 仍为空数组。
- **测试基本盘**：58 处 `FakeModelAdapter/_TestOnly` 命中（8 文件），**真实网络测试 0 个**
  （`test_arh_model_adapter.py:493-521` 反而断言 transport 未被调用）；sandbox 574 / main 1226，
  master CI 全绿。
- **SchGen**：可执行 adapter **不存在**。仅 `tools/schgen_native_ingest.py`（ingest-only）；
  `schgen_dev_chain/score` 脚本停在已关闭 PR #74 分支里。comparator 只有 RES-011 登记 +
  只读分析（`notes/schgen-dev-chain/benchmark-oracle-2026-10-02.md`）。
- **Agent 装配**：lead + 最多 2 专家（硬上限 3，原生只配 address-specialist 1 个）；
  `_TestOnly*` 双件仍在（`adapters.py:524,548,580`）但 live 路径无默认值、不引用它们；
  CLI 4 子命令。

## B. Already Proven（真实运行支撑的主张）

- **FAIL→PASS 因果链（n=2 全真实 + 1 混合对照）**：GH-110（DC-02，U2.2 null→GND，
  `repair_count=1`，`invalid=0`，C5 COMMITTED）；GH-117 `real-04`（2 真实调用）；
  `mixed-stall-03`（2 脚本 + 4 真实，CONTROL_RUN，FAIL/FAIL→PASS）。
  分类均为 DEV_ONLY，`PENDING_HUMAN_REVIEW`（`EVIDENCE_INDEX.md:293,307,316`）。
- **判定独立性**：`run_arh_episode.py:74-77` 要求 `observations[0]==FAIL 且末个==PASS`；
  trajectory 明确不参与判定（`EVIDENCE_INDEX.md:299`，两 manifest `trajectory_is_verdict: false`）。
- **N6 闩锁可恢复**：PR #119 代码+变异验证已合入（但尚无真实重启 episode 行使过它）。
- **H2 有支撑实例、无干净命名案例**：mixed-stall 的两次独立 FAIL 和历史
  `MalformedProposalError` 证明 verifier 会说不，但“agent 自称成功而 verifier 判 FAIL”
  的标准案例尚未单独记录。
- **H1、H3：均未证明**（见 C）。

## C. Not Yet Proven（设计/mock/假设）

- **H1**：无“ERC/DRC 全过但语义合同 FAIL”的命名实例（且 episode 的 ERC/DRC 覆盖本就 NOT_RUN）。
- **H3**：无 A≠B 双拓扑同 PASS 实例。
- **回归门禁不存在**：verifier 只查目标 rule（`nativeports.py:219-221` 取 `self.rule` 单条），
  其余 4 条 M2 规则在 episode 里**从不被评估** —— Tier 2 目前是文字，不是代码。
- **20+ episodes**：可运行的是 1 个；纸面映射到 5 个（DC-01/03/04/05 需接线，mapping 见下）。
- **Benchmark harness**：无 runner、无 baseline、无 SchGen wrapper、无聚合报告。
- **结构 preservation 分**：无实现。
- **EDD-001 一切**：合同、工具注册、输入证据，全部缺（见 A），且 **v0.1 不需要它们**（见 F）。

### 附：DC-01~05 → M2 规则 mapping（2026-10-02 逐题核实）

| 夹具 | 故障实测 | 对应规则 | 修法 | 判据状态 |
|---|---|---|---|---|
| DC-01 | USB_DP/DM 标签悬空（在板上但未连 U1.13/14，repair 先删后重贴） | `USB_POLARITY_AND_SERIES` | delete + add_net_label | 文字有，可执行无 |
| DC-02 | U2.2 悬空 | `SHT30_ADDRESS` | 加 GND 标签 | 已实证 FAIL→PASS |
| DC-03 | R7/R8 全缺（`22R` 0 次，`_CONN` 网仍在） | `USB_POLARITY_AND_SERIES`（器件 half） | place_component ×2 | 文字有，可执行无 |
| DC-04 | R9 全缺 | `ESP32_GPIO9_PULLUP` | 放 R9 + 贴 `+3V3`/BOOT | 文字有，可执行无 |
| DC-05 | C5 全缺 | `ESP32_EN_RC` | 放 C5 + 贴 EN/GND | 文字有，可执行无 |

DC-01 与 DC-03 共用 USB 规则但故障正交（标签悬空 vs 器件缺失），对照集里保留不算重复。
`SHT30_UNUSED_PINS` 无夹具且不应有（要求 NC 的规则不适合做故障题）。

## D. Legacy / Deprioritized Work（不再是主线）

- `web/`（静态需求澄清台 TASK-P2）：冻结，不扩。
- `delivery/gerbers/` + M2 板全套制造文件：当历史证据保留，不再以“走通制造”为目标。
- `src/m1`、`src/firmware`、`src/repair/patch_schema`：旧路线残留，保持冻结。
- `_TestOnly*` 双件：留着（测试要），但 live 路径已隔离，**禁止再给它们加默认值**。
- EDD-001 整板 scope 决策（Issue #32）：**推迟到 RepairBench v0.1 之后**，M2 已够用。
- SchGen dev-chain 旧脚本（PR #74 分支）：只取 ingest 能力，不复活整套。

## E. RepairBench Blockers

```text
P0（没有就动不了）
1. Episode 参数化：nativeports 去掉 DC-02/SHT30_ADDRESS 写死（fixture 路径 + rule id 入参）—— 否则永远只有 1 个 episode
2. 单 episode 回归检查：每次跑完评估全部 5 条 M2 规则 —— 否则 Tier 2 不存在，因果主张缺一半
3. Baseline runner：同模型同预算的 generic-LLM 对照 —— 否则任何 uplift 数字都没有意义

P1（v0.1 可信度需要）
4. SchGen wrapper（只读分，不改语义）—— Tier 3 结构分
5. H3 实例：为同一规则造第二种合法拓扑并双 PASS
6. H1 实例：从现有夹具里找 ERC 能过、合同 FAIL 的命名案例

P2（可后放）
7. EDD-001 就绪（POWER 冻结、手册裁决、工具注册）—— v0.1 明确不需要，M2 即全集
8. 跨 episode 聚合报告 + 正式 Evidence 晋升路径（等 DEV_ONLY 攒够 + 人工核验）
9. 20–30 规模：5 个 M2 + baseline 跑通之前不谈数量
```

## F. Shortest Path to RepairBench v0.1（最小可信序列）

```text
1. 参数化 nativeports（P0-1）                       → 1 个小任务
2. 接 DC-01/03/04/05 + 全规则回归检查（P0-2）        → 到达 5 episodes，Tier 1+2 成立
3. Baseline runner，同模型同预算跑同样 5 题（P0-3）  → 第一个 uplift 数字 + False-success 检出实例（H2 命名）
4. 从 5 题里命名 H1 实例；为一题造第二拓扑（H3）     → Kill Gate 三个假设逐个有无 verdict
5. SchGen wrapper 只记录 Jaccard/F1 delta（P1-4）    → Tier 3 上线但不参与判决
6. Kill-gate review：若 ERC 已覆盖一切 / baseline 无差异 / 合同无额外检出 → 停项目，不加 feature
```

关键判断：**v0.1 的全集就是 M2，不需要 EDD-001**。EDD-001 的缺项、工具注册、POWER
冻结全部推迟 —— 它们是另一个 benchmark（真板域）的入场券，不是 RepairBench v0.1 的。
最小可信实验是 “5 道 M2 题 + baseline”，不是 20–30 个。
