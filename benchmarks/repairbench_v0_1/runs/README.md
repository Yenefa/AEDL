# `runs/` — 一条回执对应一次运行

布局（2026-10-07 起，卡片 `RUN-RECEIPT-ISOLATION`）：

```text
runs/<UTC 时间戳>-<arm>-<代码 sha7>-<序号>/<arm>.json
```

- 默认落点由 `tools.repairbench.allocate_run_dir()` 现分配，**每次运行一个新目录**；
  写已存在的同名文件会抛 `RunCollision`，绝不覆盖上一次运行。
- 每份回执自带 `provenance`：代码 sha 与 dirty、python、写入器身份（或 `NOT_RUN` + 如何提供）、
  模型 host/model（**不含密钥**）、四个输入文件哈希（合同 / episode 清单 / structural oracle /
  夹具清单 `manifest_v1.json`）、预算起止快照。
- 每条 episode 有 `verdict ∈ {pass, fail, not_executed}`；`not_executed` 单列计数。
  全部未执行时 `reportable=false`——**没跑成不是 0 分**。
- 想在仓库里留下证据就把该目录一并提交；只想试跑就用 `--runs-dir <仓库外目录>`，
  否则 `dev_gate` 的 `scope_check` 会把未跟踪的运行目录报成越界（这是故意的：证据要经手）。

## 本目录下的平面文件（`noop.json`、`oracle.json`、`baseline_generic.json`、
`aedl_contract.json`、`aedl_contract_deterministic.json`）是**隔离之前的产物**，保留为历史：

- 它们没有 run id、没有代码版本、没有模型与写入器身份、没有预算快照；
- 其中 `aedl_contract.json` 的 5 条结果**全部**是 `BudgetExceeded`、`executed=0`
  （花钱负对照覆盖了真实模型回执），
  `baseline_generic.json` 与 `noop.json` 出自**不同的代码 schema**（前者无 `in_scope_*` 字段）；
- 因此 `docs/evidence/EVIDENCE_INDEX.md` 与 `RESULTS_20261005.md` 里引用这些文件的数字
  **不可复核**，自本卡合并起应视为待重跑；旧文件不删不改（`AGENTS.md` §0A.5 第 5 条）。
