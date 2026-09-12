# B5 前置：C3–C6 独立验收扰动判据（草案）

> 状态：`DRAFT — NOT FROZEN`（draft-1）。起草：Claude Code（Percy 会话），2026-09-12。
> 任务：W2 r3 卡 **B5｜C3–C6 独立验收，Owner: Percy，6h**。
> **纪律：判据必须先于实现冻结。** C3–C6 在 master 上一行未落地（§0.2 实测），所以此刻写判据天然没有实现曝光——这与 A3 rubric 是同一条纪律。
> **红线：Percy 不实现 C3–C6**（W2 r3「永久隔离纪律」）。本文件只定义验收怎么判，不给实现方案。

---

## 0. 这份文件是什么

**是**：B5 四条扰动的做法与判定口径，在 C3–C6 落地之前写死。

**不是**：

- 不是实现方案或测试代码——验收侧不实现被验对象；
- 不是对 C1/C2 的重新验收（C1/C2 已合入，另有其 acceptance）；
- 不是 A3 的 A/B 评分（那是 Y4 的答案正确性，与本文件无关）。

### 0.1 判据来源（唯一合法来源）

| 来源 | 用于 |
|---|---|
| PR-1 实现合同 `docs/competition/internal/AEDL_PR1_实现合同_20260907.md`（master 冻结版）§5 hash/身份/exact/protected、§7 五条许可的执行语义、§8 模块接口与回执、§9 thin verifier 与 commit 谓词、§10 状态机与 fail-closed、§11 每个 commit 的 acceptance | 每条扰动「被验的主张」与「期望红在哪」 |
| W2 r3 任务卡 B5 的四条扰动 | 扰动清单的骨架 |

**不作为来源**：C3–C6 的实现代码（尚不存在）。实现落地后也**不得**据其行为反向修改本判据——那正是「照着实现写判据」。

### 0.2 当前状态（决定每条什么时候能跑）

2026-09-12 在 `origin/master`（`c286489`）实测：

| Commit | 产物 | 现状 | 验收入口（合同 §11） |
|---|---|---|---|
| C3 | `gates.repair_verification.verify_stage` + `FreshExportTests` | **未落地**：`verify_stage` / `ThinVerificationResult` / `ExportProof` / `fresh_export` 在该文件零命中；测试文件只有 C2 的 `DeltaAndProtectedTests` | `python -X utf8 -m unittest tests.test_repair_verification.FreshExportTests` |
| C4 | `tools/akcli_adapter.py` + `tests/test_akcli_adapter.py` | **未落地**：两个文件都不存在 | `python -X utf8 -m unittest tests.test_akcli_adapter` |
| C5 | `repair_pipeline` 的 `run_round` / `bind_policy` / `recover_incomplete` | **未落地**：现有只有 C1 的 `parse_proposal` 与公共投影 `make_public_context` / `public_feedback` | `python -X utf8 -m unittest tests.test_repair_pipeline tests.test_repair_contract` |
| C6 | 四个 native 测试与夹具 manifest | **未落地** | 见 §11；须 opt-in 三个环境变量 |

`tools/dev_gate.py` 用 `unittest discover -s tests`，新测试文件落地后自动进门禁，不需要额外接线。

---

## 1. 通用规则（四条扰动共用）

1. **只在副本上扰动**：绝不改 master、不改真实候选设计、不改冻结夹具。扰动对象是临时工作区中的拷贝。
2. **必须红在指定的地方**。每条扰动预先写死「哪个字段 / 哪个 status / 哪个 reason code 必须非 PASS」。**因别的原因失败不算通过**——它没有证明被验的那条独立性（§4 称为「假红」）。
3. **最低标准是没有 COMMITTED**。合同 §9 的 commit 谓词是**合取**，没有「置信度高」「仅 warning」「多数 checks PASS」的例外。扰动之后若出现 `TransactionStatus = COMMITTED`，该条直接判失败。
4. **回执必须诚实**：失败 phase 之前的必需结果为 `null` / `NOT_RUN`，不得填假 PASS（§10）。`deferred.erc` 等必须保持 `NOT_RUN`。
5. **六态照用**：`PASS / FAIL / UNKNOWN / NOT_RUN / TOOL_ERROR / NOT_APPLICABLE`。`UNKNOWN`、`TOOL_ERROR` **不等于**通过；任一 required check 为 `NOT_RUN` 也不得 PASS（合同 §11 C3 原话）。
6. **逐条留证**：每条扰动按 §3 的格式记录，含实际输出的关键字段与证据路径。
7. **不因「已知限制」放宽**。实现方声明某条是已知限制，不改变判定；要放宽须先改本判据，并按 §5 声明改动发生在观测之前还是之后。

---

## 2. 四条扰动

### C3｜independent export weakened → red

**被验的主张（§9）**：`KICAD_VERIFY` 内对 snapshot before 与 stage after **各执行一次新的导出**，固定 KiCad **10.0.5**；记录 source 在导出前、导出后、解析结束三个 SHA256；`exports` 恰好 `BEFORE`/`AFTER` 两项且 `completed`；PASS 要求四项 required checks（`fresh_export` / `source_hash_binding` / `exact_topology_delta` / `protected_diff`）**全部 PASS**，两份 `Coverage.complete=true` 且 expected/observed keysets 相等，`parser_agreement` 两项 PASS，delta hashes 相等。

| ID | 扰动 | 期望红（必须落在这里） |
|---|---|---|
| **C3-P1** | 让导出进程失败（改 `AEDL_KICAD_CLI` 指向不可执行路径），同时在输出目录留下**上一轮的旧 XML** | `checks.fresh_export` 非 PASS；**不得**复用旧 XML 得出结论（合同 §11 原话：「旧XML残留而export失败不得通过」） |
| **C3-P2** | 导出进程 `exit=0`，但产出**空文件 / 坏 XML** | `checks.fresh_export` FAIL 或 TOOL_ERROR；不得因 exit=0 视为成功 |
| **C3-P3** | 在导出与解析之间修改 stage 源文件 | `checks.source_hash_binding` FAIL —— 三个 source hash（导出前 / 导出后 / 解析结束）不再相等 |
| **C3-P4** | verifier 返回后**替换报告文件**或 staged manifest | commit 谓词落空（§9：「verifier 返回后重算 stage source/report hashes 与回执一致」），最终非 COMMITTED |
| **C3-P5** | toolchain manifest 指向**非 10.0.5** 的 KiCad，或 txn/policy/tool 绑定与请求不符 | 非 PASS；缺值或版本不同**不得静默通过** |
| **C3-P6** | 让 coverage 不完整（漏一个 pin / 零 coverage），或制造 native 观察与 KiCad 导出分歧 | `coverage.complete=false` 或 `parser_agreement` 非 PASS |
| **C3-P7** | 把任一 required check 置为 `NOT_RUN`，或把 `deferred.erc` 伪写成 PASS | 整体非 PASS；`deferred.erc` 必须仍是 `NOT_RUN` |

**通过判据**：七条全部出现**指定位置**的红，且无一条产生 COMMITTED。
**假红示例**（不算通过）：扰动后整个进程因为夹具缺失崩溃、或在 PRECHECK 就被别的原因拒绝——那没有验到 fresh export 这一环。

---

### C4｜forged applied=true → red

**被验的主张（§8）**：STRICT 只有在 `exit=0` **且** 标准 draw-result **且** `applied=true` **且** `op_results` 完整（覆盖 `0..n-1`、status 全 `ok`）**且** 源 bytes 确实改变 **且** 成功重读 时，才返回 `APPLIED_TO_STAGE`；`dry-run exit=0 / applied=false` 不通过；首次 no-op 不通过；adapter **不接受可由 JSON 单独伪造的 `authorized=true`**；只允许**一次写调用**；strict 被拒**不得自动 fallback** 到 exception（route 在 PRECHECK 冻结）。

| ID | 扰动 | 期望红 |
|---|---|---|
| **C4-P1** | 工具回执写 `applied=true`，但 stage 源 bytes **未改变** | `StageApplyResult.status = BLOCKED`；`changed=false` 与 `applied` 矛盾必须被抓 |
| **C4-P2** | `applied` 字段缺失 / `false` / JSON 层面伪造的 `true`（含伪造 `authorized=true`） | BLOCKED，绝不 `APPLIED_TO_STAGE` |
| **C4-P3** | 走 API 路径且 `tool.tool_applied=null` | 不得当成成功 |
| **C4-P4** | `op_results` 缺项 / 重复 index / 任一 `status=error` | BLOCKED（必须逐一覆盖 `0..n-1` 且全 `ok`） |
| **C4-P5** | strict 被拒后**自动改走 exception** | 必须拒绝：route 在 PRECHECK 冻结，不得先试 strict 再升级 |
| **C4-P6** | akcli 版本 ≠ `0.21.0`，或符号库 digest 不符 | 拒绝，不得静默继续 |
| **C4-P7** | 同一轮发起**两次写调用**；或把 DC-04/DC-05 拆成两批 op | 拒绝（合同要求单批、一次写调用） |
| **C4-P8** | 产生新的 `NO_CONNECT_CONFLICT` 或新 WARNING connectivity finding | 阻断（新 warning 与任何 NC 冲突都阻断） |

**通过判据**：八条都红在 adapter 层，且没有任何一条让流程继续走到 `DELTA_CHECK` 之后。
**假红示例**：因为夹具路径不对导致 adapter 根本没启动。

---

### C5｜DENY override → red

**被验的主张（§8/§10）**：没有真实批准依据、或现有 `PolicyPort.evaluate` 对 `TOOL_EXECUTE` / `FILE_WRITE` **任一不为 ALLOW** 时，`BoundPolicyResult` 非 PASS；**DENY/BLOCKED 不可被 exception 覆盖**；伪造 policy / hash / ID 一律拒绝；PRECHECK 须取得 candidate 单写者锁并先处理未完成事务。

| ID | 扰动 | 期望红 |
|---|---|---|
| **C5-P1** | policy 判 DENY，仍尝试走 exception 路径 | `REFUSED` / `BLOCKED` + `REPAIR_AUTH_DENIED`；且**零 native 写调用、零 design 写**（不是"写了再回滚"） |
| **C5-P2** | 伪造 `bound_policy_sha256` / `authority_context_digest` / run/candidate/patch ID | 拒绝；hash 与 ID 不一致不得进入 STAGE_APPLY |
| **C5-P3** | 静态政策草案默认 `disabled`，运行时当作已启用 | 拒绝（`REPAIR_POLICY_DISABLED`） |
| **C5-P4** | 越界路径、兄弟 candidate 链接、硬链接 / symlink / reparse point | 拒绝（§10 要求逐路径分量检查 link count 与实际身份，不能只查 workspace root） |
| **C5-P5** | 绕过单写者锁 / 并发第二个事务 / GUI 占用 | 拒绝 |
| **C5-P6** | 幂等键 `(run_id,candidate_id,patch_id)` 相同，但 proposal/patch/policy/context digest 不同 | `BLOCKED` |
| **C5-P7** | 在写前 / 写后 / 验证后 / commit 前后**中断进程**，再重启恢复 | `ROLLBACK` 且 `rollback.status=VERIFIED`，`cause_status` 保留原失败类别；**不得**记成功；无 COMMITTED terminal record 时即使有 COMMIT_INTENT 且 live=after 也按恢复规则 2 处理 |

**通过判据**：七条都红在授权 / 事务边界，且回执能区分「设计失败」与「工具故障」（verifier FAIL → `cause_status=BLOCKED`，保留 `verifier.status=FAIL`）。
**特别注意两个误读**（合同明写，判据必须体现）：

- **design 恢复成功 ≠ 修复成功**；
- `NO_CHANGE` 只能用于已验证 `COMMITTED` 回执的幂等重放，不能用于首轮。

---

### C6｜fake SKIP → red

**被验的主张（§11 原话）**：「未 opt-in 可标注 SKIP；**opt-in 后缺工具/坏版本必须失败，不能 SKIP 把 C6 变绿**」。

| ID | 扰动 | 期望红 |
|---|---|---|
| **C6-P1** | 设好 `AEDL_PR1_NATIVE=1`，但 `AEDL_KICAD_CLI` 指向缺失 / 错版本 | 必须 **FAIL**，不得 SKIP，不得让 C6 变绿 |
| **C6-P2** | 设好 opt-in，但 akcli 版本错 / 发行包不符 | 同上 |
| **C6-P3** | verify 通过之后**替换 stage** | 拒绝提交 |
| **C6-P4** | DC-06 的 REFUSE 路径 | **零 native 调用、零 design 写** |
| **C6-P5** | thin verifier PASS | **不得**触发正式 promotion；U3 仍 `BLOCKED_POWER_THERMAL`；`full_verification_status` 与 `formal_evidence_status` 保持 `NOT_RUN` |
| **C6-P6** | 五条 run_round 真实跑完 | route 与 exact/protected 吻合；**保留旁路等负例不得产生候选提交** |

**通过判据**：P1/P2 必须以失败（而非 SKIP）结束；P3–P6 均无候选字节被提交，且回执字段未被抬高。
**假红示例**：未设置 opt-in 就运行——那本来就允许 SKIP，验不到任何东西。

---

## 3. 记录格式（每条扰动一份，落盘后不改写）

```text
perturbation_id:   C3-P1 … C6-P6
claim:             <被验的主张，引合同章节>
method:            <扰动怎么做；作用在哪个副本>
expected_red:      <字段 + 状态 + reason code>
observed:          <实际输出的关键字段原文>
verdict:           PASS | FAIL | UNKNOWN | TOOL_ERROR | NOT_RUN
committed:         <是否出现 COMMITTED —— 出现即整条失败>
evidence:          <报告 / 回执 / 日志路径与 sha256>
run_by / run_at:   Percy / <时间>
notes:             <含「假红」判断说明>
```

汇总在执行前建立，全部预填 `NOT_RUN`，不预填 PASS。

---

## 4. 执行前置

| 扰动组 | 需要什么才能跑 |
|---|---|
| C3 | `verify_stage` 与 `FreshExportTests` 落地；本机 KiCad **10.0.5** |
| C4 | `tools/akcli_adapter.py` 与 `tests/test_akcli_adapter.py` 落地；akcli **0.21.0**、固定 3.11 解释器 |
| C5 | `run_round` / `bind_policy` / `recover_incomplete` 落地 |
| C6 | `AEDL_PR1_NATIVE=1`、`AEDL_AKCLI_PYTHON=<3.11 绝对路径>`、`AEDL_KICAD_CLI=<10.0.5 绝对路径>`，且真实工具可用 |

四组互不依赖：C3 落地就可以先跑 C3 组，不必等 C6。

---

## 5. 红线与边界

- **不实现被验对象**：扰动若需要脚本，属验收侧一次性工具，不进生产路径，也**不得**被实现方复用为其通过条件。
- **判据先于观测**：本文件冻结后不改。若发现判据本身写错，发布新版本并声明修正发生在观测**之前还是之后**；观测之后的修正不得用于重判已判条目。
- **范围**：只验「独立性与 fail-closed」，不验电气正确性，也不替代 A3 的 A/B 评分；`thin PASS` 不等于整板通过。
- **不放宽**：实现 PASS 不构成放宽判据的理由。

---

## 6. 待决（Percy）

| # | 问题 | 起草者建议 |
|---|---|---|
| **Q-B5-1** | 公开方式：判据公开 + 具体扰动载荷（伪造回执 JSON、坏 XML、篡改 hash 的字节）host-side 保留？还是全部公开？ | **判据公开、载荷保留到执行时**。实现方**应当**照着这些性质去建设（这与 A3 的评分断言不同，不是答案）；但逐条载荷提前给出，容易被特判掉 |
| **Q-B5-2** | 存放位置 | `notes/b5-acceptance/`（本文件当前位置） |
| **Q-B5-3** | 何时冻结 | **在 C3 合入之前**登记 sha256。C3 是 Yenefa 的下一个主线任务（B1，7h），判据晚于它落地，独立性就没了 |

---

## 版本表

| 版本 | 日期 | 状态 | 备注 |
|---|---|---|---|
| draft-1 | 2026-09-12 | `DRAFT — NOT FROZEN` | 初稿：四组共 28 条扰动，逐条钉在合同 §5/§7/§8/§9/§10/§11；当前状态经 master `c286489` 实测（C3–C6 全部未落地）；三项待决 |
