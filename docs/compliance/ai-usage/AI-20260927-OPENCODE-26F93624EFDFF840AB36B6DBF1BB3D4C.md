## AI-20260927-OPENCODE-26F93624EFDFF840AB36B6DBF1BB3D4C

- 日期：2026-09-27
- 任务名称：C5 `run_round` MVP —— 把已存在的 observe / proposal / bind_policy / apply / verify / feedback 串成一轮
- 记录者：OPENCODE
- 会话：opencode（Space Bunny Free），本机 `C:\dev\AEDL`
- 参与：GENERATE_CODE、GENERATE_TEST、DEBUG
- AI 工具/平台：opencode / `space-bunny-free`（provider `opencode`）
- 模型：`space-bunny-free`
- 人工审核：`PENDING_HUMAN_REVIEW`
- 授权来源：Owner 2026-09-27 会话指令 ——「创建新的 C5 envelope，开始 run_round MVP」，
  并明确**不做** self-improvement / benchmark evolution / multi-agent / feedback learning，「只做 one repair round，跑通即可」。

### 目标与边界

`bind_policy`（CP4-C）只做到「绑定并限定」，其 docstring 自己写明：*「A PASS means the transaction is
bound and qualified, NOT that anything was written; committing it is a later phase.」*
缺的正是一个**轮次控制器**。本任务只补这个控制器，**不新增任何能力**：

```
PRECHECK      observe_source -> parse_proposal -> build_expected_after -> bind_policy
STAGE_APPLY   akcli_adapter.apply_stage      (真实 pinned writer)
DELTA_CHECK   gates.repair_verification.compare_delta
```

### 三条承重性质，每一条都来自已经踩过的坑

**1. `compare_delta` 是唯一验收入口。**
上一轮那个 harness 自己比较 `observation_delta` 摘要，得出**假的** "identity delta FAIL"，
而它以为缺失的能力其实一直在 C2 里（`_align_new` ← `_prepare` ← `compare_delta`）。
真正的缺陷是**入口用错**。PR #93 用静态守卫钉住了入口，本轮 `run_round` 直接消费 `compare_delta`，
并新增一条针对 `run_round` 自身的 AST 守卫：其函数体内**不得**出现 `observation_delta` 调用。

**2. writer 没有注入缝。**
`run_round` 永远调用真实 `apply_stage` —— 没有参数、钩子或覆盖。
**假造一次成功写入在结构上不可能**，而不只是「不建议」。
代价是 happy path 需要真实 akcli，因此在无 pinned 工具链的解释器上
（仓库 3.9.13 无 `akcli`）该轮**根本无法报告写入** —— 这正是正确答案，测试也据此断言。

**3. 阶段级状态绝不当作事务级状态。**
`apply_stage` 返回 `APPLIED_TO_STAGE`，那只说明 writer 对着临时 stage 跑过。
真正算成功还需 `tool_applied is True`、`exit_code == 0`、`changed is True` 四项同时成立 ——
**exit 0 但什么都没改，不是写入**。该判据抽成 `_stage_write_succeeded` 纯谓词以便穷举测试，
而 `run_round` 内部仍只调真实 writer。

### 一个必须诚实处理的语义缺口

事务级状态词表里**没有**「已在 stage 应用并验证、但未 commit」这一档：
`STATUS_COMMITTED` → `OUTCOME_APPLIED`，而 COMMIT 阶段未实现。
本轮**没有自造状态词**。已验证的轮次返回 `status=None` + `terminal=False` + `pending_phases`，
`public_feedback()` 因此投影为 `EXECUTION_UNAVAILABLE` —— 这是**真话**（轮次未 commit，公开结论尚未成立），
并作为**预期行为被断言**，而不是被容忍。

**DELTA_CHECK 失败 → `STATUS_ROLLBACK` + `cause_status=STATUS_BLOCKED`（投影 `REJECTED`）的映射。**

理由：DELTA_CHECK 的语义不是「工具失败」，而是「**实际状态不满足授权预期**」——
因此它既不是 `TOOL_ERROR`（工具坏了），也不是 `UNKNOWN`（无法确定），
而是 *attempted transition rejected*（被拒绝的尝试性状态转移）。

**术语边界（Owner 裁定 2026-09-27，必须保持）：**

> `STATUS_ROLLBACK` 意为**丢弃一个未被晋升的 stage 结果**，
> **不是**恢复一个已提交的状态。

`ROLLBACK` 一词容易被误读成「已经 commit，然后再回滚」。本系统中并非如此：
轮次止于 `APPLIED_TO_STAGE`，**从未 commit**，因此不存在「恢复已提交状态」这回事 ——
被丢弃的正是一个**尚未晋升**的临时结果。

Owner 裁定：**保持现状，不扩状态词**。本轮据此未改动任何代码行为。

### 调查中发现的一件事（未修，仅记录）

`apply_stage` 会校验磁盘上的 op-list 与被授权 proposal **逐操作一致**
（`akcli_adapter.py:1129-1132`：`_normalize_operations(on_disk["ops"], "op-list") != proposed` 即拒绝），
所以「篡改 op-list」这条路径在**写入之前**就被拦住，到不了 DELTA_CHECK。

而 `qualify_toolchain`（`repair_pipeline.py:2976-2994`）把 HostPatch 的 toolchain slice
与**同一份 host binding 推导出的** slice 互相比；其中 `akcli_artifact_sha256` 是
**声明值，不是对本机二进制的测量**。因此**替换实际执行的 writer 不会被 qualification 拦下**。

含义：当前设计里，DELTA_CHECK 是替换 writer 的**最后一道防线**，而不是多余的重复检查。
这一点已记录为待跟进项，本轮**未修**（`tools/**` 内属本任务范围但 YEN 裁定冻结 C5，不扩）。

### 变异检验：8/8 全部被捕获

绿灯测试本身不证明任何事。逐条破坏承重性质，要求对应测试失败：

| 变异 | 结果 |
|---|---|
| M1 成功判据削弱为只看 stage status | 捕获 |
| M2 改回手写 delta 比较（历史假 FAIL） | 捕获 |
| M3 去掉 stage 根目录包含性检查 | 捕获 |
| M4 在已验证轮次声称 COMMITTED | 捕获 |
| M5 拒绝不再终止轮次 | 捕获 |
| M6 `run_round` 不再自行解析 proposal | 捕获 |
| M7 请求里加 writer 缝 | 捕获 |
| M8 接受不完整的 before observation | 捕获 |

**第一次变异跑出 2 条 SURVIVED，都不是工具问题而是我自己的测试无效**：

- **M1 存活**：谓词内联在 `run_round` 里，无缝可测，本机 stage status 是 `TOOL_ERROR` 所以变异无可观测差异。
  → 抽出 `_stage_write_succeeded` 并穷举四个事实各自为假的情形。
- **M3 存活**：路径穿越测试**因错误的原因通过** —— `../outside.kicad_sch` 从 `cand/design`
  解析到 `cand/outside.kicad_sch`，而我并没有创建该文件，于是 read 失败照样 BLOCKED，测试根本没碰到包含性。
  → 把逃逸目标**放在 `../` 真正能到达的位置并确实存在**，去掉包含性才会失败。

### 三个自造错误（如实记录）

1. 误用 `REASON_TOOL_ERROR`（该常量不存在）→ 改为 `REASON_TOOL_UNAVAILABLE` / `REASON_TOOL_PROTOCOL_ERROR`。
2. 把 `stage_target` 当 identifier 校验（`_identifier` 拒绝 `fault.kicad_sch` 的点号），
   且**在 adapter 的包含性检查之前**就自己读路径 —— `../` 可以读到 stage 之外。
   → 改为 `_text`，并在读之前强制 `relative_to(stage_root)`。
3. 变异脚本的备份路径用 `with_suffix(".py.mutationbak")`，`.py` 被整体替换，
   还原失败，**把变异后的源码留在了仓库里**。手工修回那一行并逐项校验；
   随后重写为显式备份路径 + 每个变异后立即还原。

### 真实端到端结果（本轮最重要的一条）

一次 `run_round` 调用，真实 pinned akcli 0.21.0 写入：

```
phases reached   : ['PRECHECK', 'STAGE_APPLY', 'DELTA_CHECK']
stage            : APPLIED_TO_STAGE  tool_applied=True exit_code=0 changed=True
before sha256    : 655f585df2e913a8aaade3d8a0a291591ec1e7e275920006a54aec8f75dde7a0
after  sha256    : 2f660180ab180009656da7d47e7b686a75ce42ce9084b610904e2b6d28db99c6
verification     : PASS   missing=[] unexpected=[]
authorized delta == actual delta
                  == 69877d3e9a4be9133f0c31684b35952a9f9745596974eb1f1237c6b437ebc681
status           : None   terminal=False   pending=['KICAD_VERIFY','COMMIT']
feedback outcome : EXECUTION_UNAVAILABLE
```

before/after 摘要与 delta **与 EVID-20260927-001 记录的那笔真实事务逐字节相同** ——
一次调用复现了同一结果。本次 binding 里的 kicad 摘要也是**真实实测**
（P1 之前该字段只能是合同声明，因为 kicad 未安装；现已安装 10.0.5）。

### 改动范围（4 个文件）

| 文件 | 改动 |
|---|---|
| `tools/repair_pipeline.py` | 新增 `run_round`、`_stage_write_succeeded`、`_stage_refusal_status`、请求字段集与阶段常量 |
| `tests/test_repair_pipeline.py` | 新增 `RunRoundTests`（25 条）+ `from unittest import mock` |
| `tasks/PR1-C5-RUN-ROUND.yaml` | 新增 envelope |
| `docs/compliance/ai-usage/<本文件>`、`AI_USAGE_LOG.md` | 记账 |

**未修改 `gates/**`、未新增状态词、未新增 digest kind、未改任何验收合同。**

### 实际运行的验证

- `py -3 -S -m unittest discover -s tests` → **1022 OK (skipped=20)**（master 基线 997/19，+25 条 +1 skip）
- `py -3 -m unittest tests.test_repair_pipeline.RunRoundTests` → **25 OK (skipped=1)**
- 变异检验 → **8/8 捕获**，源码已还原并校验
- 真实端到端 `native_run_round.py` → 全部断言通过（三阶段、真实写入、delta PASS）

### 未运行 / 限制（如实声明）

- **CI：NOT_RUN** —— GitHub Actions 计费阻断未解除；本机 `dev_gate` 仅为单平台（Windows）开发回执。
- **仓内 happy path 测试：skip**（`test_the_real_pinned_writer_completes_the_round` 需
  `AEDL_PR1_NATIVE=1` + `AEDL_AKCLI_PYTHON` + `AEDL_RUN_ROUND_STAGE_ROOT` + `AEDL_RUN_ROUND_BINDING`）。
  真实端到端已在仓外 harness 跑通，但**该仓内测试本身在本轮为 NOT_RUN**，不谎报为通过。
- **`COMMITTED` 仍未声称**；KICAD_VERIFY 与 COMMIT 两阶段仍未实现。
- **不做 feedback learning**：`public_feedback` 仅被调用，无任何消费方。
- `recover_incomplete` 仍未实现（本任务范围外）。
- 正式 Evidence：**未登记**。Owner 指示 PR #94 冻结等 review、「下一步不要继续做 Evidence」，
  故本轮**不**写 `docs/evidence/**`（envelope 中已列为 forbidden）。

### 边界遵守

- 未 merge、未 approve；PR #93 / PR #94 保持 Draft 不动。
- 未触碰 PR #91 / GH-51。
- 未自造状态词或 digest kind；一处语义映射（DELTA_CHECK 失败 → ROLLBACK/REJECTED）已显式标注待确认。

### 待人工确认

- 全部产物 `PENDING_HUMAN_REVIEW`。
- **需 Owner 裁定**：DELTA_CHECK 失败的 `STATUS_ROLLBACK` + `cause_status=STATUS_BLOCKED` 映射。
- **需 Owner 裁定**：envelope 中记录的窄口径 `allow_drift` 例外（仅本任务自身提交）。
