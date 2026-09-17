# B5 前置：C3–C6 独立验收扰动判据（草案）

> 状态：**draft-4 已按 §7 完成冻结登记（全文 sha256 `0db60076…`，2026-09-14 由 PR #71 登记）；当前生效版本为 draft-5 —— Owner 授权的 post-freeze erratum，仅修 C4-P3 一处（见 §7 第 6 条）。**
> 起草：Claude Code（Percy 会话），2026-09-12；draft-4 修正 2026-09-13；**draft-5 erratum 2026-09-17（Yenefa 裁定，仅 C4-P3）**。
> 历史口径说明：draft-4 登记时本行仍写着 `DRAFT — NOT FROZEN`，与 §7 第 2 步已完成的冻结登记不一致；draft-5 予以理顺，不改判据效力。
> 任务：W2 r3 卡 **B5｜C3–C6 独立验收，Owner: Percy，6h**。
> **纪律：判据必须先于实现冻结。** C3–C6 在 master 上一行未落地（§0.2 实测），所以此刻写判据天然没有实现曝光——这与 A3 rubric 是同一条纪律。
> **红线：Percy 不实现 C3–C6**（W2 r3「永久隔离纪律」）。本文件只定义验收怎么判，不给实现方案。
> **公开方式（Percy 2026-09-12 裁定，Q-B5-1）：判据公开，扰动载荷 host-side 保留。** 本文件可随仓库公开——实现方**应当**照着这些性质去建设；但逐条扰动的具体载荷（伪造的回执 JSON、坏 XML、篡改 hash 的字节）在执行时才产生并留在 host 侧，不随本文件公开，以免被特判掉。

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
| Y4 方案 `AEDL_W1_Y4_AI_vs_Script_实验方案.md` §5「运行结果使用 `PASS / FAIL / UNKNOWN / NOT_RUN / TOOL_ERROR / NOT_APPLICABLE`」 | 判定状态的词表（§1 规则 5、§3 记录格式）。**该词表不出自 PR-1 合同**，是仓库既有的全链状态语义，特此注明出处 |

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
3. **最低标准是没有 COMMITTED**。合同 §9 的 commit 谓词是**合取**，没有「置信度高」「仅 warning」「多数 checks PASS」的例外。**扰动之后**若出现 `TransactionStatus = COMMITTED`，该条直接判失败。
   - **唯一例外：`C6-P6` 的正例。** 它是**未施加扰动**的对照路径（五条 run_round 正常跑完），其 `COMMITTED` 正是被验的正确行为，本条不适用；本条约束的是 `C6-P6` 的**负例**与其余 27 条。**对照路径之外不得再设第二个例外**——若将来需要新增正例，必须同时改本条与该组通过判据，不得只改一处。
4. **回执必须诚实**：失败 phase 之前的必需结果为 `null` / `NOT_RUN`，不得填假 PASS（§10）。`deferred.erc` 等必须保持 `NOT_RUN`。
5. **六态照用**：`PASS / FAIL / UNKNOWN / NOT_RUN / TOOL_ERROR / NOT_APPLICABLE`（词表出自 Y4 方案 §5，见 §0.1）。`UNKNOWN`、`TOOL_ERROR` **不等于**通过；任一 required check 为 `NOT_RUN` 也不得 PASS（合同 §11 C3 原话）。`NOT_APPLICABLE` 只用于**事前范围**就排除的条目（例如某条扰动依赖的接口在该 commit 的范围之外），**不得**在扰动失败后临时扩大使用——同 Y4 方案 §5「`NOT_APPLICABLE` 必须由事前范围和理由确定」。
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
| **C3-P5** | toolchain manifest 指向**非 10.0.5** 的 KiCad，或 txn/policy/tool 绑定与请求不符 | `ThinVerificationResult.status` 非 PASS，且失配体现在 `toolchain_sha256` / `patch_sha256` / `bound_policy_sha256` / `txn_id` 之一（§9：verifier 先重算 snapshot、stage 与依赖 hash，输入不匹配即返回非 PASS）；reason code 取 `REPAIR_INPUT_DRIFT`（§8 固定 reason codes）。缺值或版本不同**不得静默通过** |
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
| **C4-P3** | 走 API 路径（`CONSTRAINED_EXCEPTION`）：回执**没有** `applied` 字段，`tool.tool_applied=null` | `null` **不得**被当作 affirmative applied evidence。合同 §8（L253）规定该路径**原生没有** `applied` 字段，所以事实上的 `null` **本身不构成红**。该路径只有在 `op_results` 完整（逐一覆盖 `0..n-1` 且 status 全 `ok`）、stage 源 bytes **确实改变**、fresh reread 成功、且 connectivity 检查成立（§8 L257）时，才可判 `APPLIED_TO_STAGE`（§8 L255：「exception 同样要求每个 op ok、真实字节改变及重读成功；不能用 API list 非空作为成功条件」）。**红 = 缺上述任一独立条件却仍判成功**，或以「API list 非空」代替这些条件。注：`tool_applied` 在 STRICT 路径上必须为 `true`、在本路径上必须为 `null`，两者不得互相套用 |
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
| **C5-P7** | 在写前 / 写后 / 验证后 / **commit 的 terminal record 写成之前**（含 replace 已完成、`COMMIT_INTENT` 已落盘）**中断进程**，再重启恢复。**不含**「terminal record 已写成之后」的中断：该子情形按合同恢复规则 4「存在完整 terminal record 时，只有全部源/报告/依赖匹配才重用结果」应当**重用 `COMMITTED`**，与本组「七条都红」的通过判据互斥，故**不在本条、也不在本文件 28 条之内**（§5：B5 只验独立性与 fail-closed）；若需验收该子情形须另立条目，并在通过判据里单独豁免 | `ROLLBACK` 且 `rollback.status=VERIFIED`，`cause_status` 保留原失败类别；**不得**记成功；无 COMMITTED terminal record 时即使有 COMMIT_INTENT 且 live=after 也按恢复规则 2 处理。且 **`rollback.byte_equal=true`**；**不得只凭 `rollback.status` 自报判定 VERIFIED**——须将 live target 与写前快照（round snapshot / 已记录的 before bytes）做**独立比对**（逐字节 / sha256 / 文件集合），并把比对结果记入 §3 的 `observed`。依据：合同 §10 恢复规则 1「逐 bytes/manifest 核对后 `rollback.status=VERIFIED`」、规则 2「恢复后逐字节与 hash、文件集合均匹配才 VERIFIED」，最终回执 L405 已定义 `rollback.byte_equal` 字段——本条只把验收锚点钉到该字段，不新增合同要求 |

**通过判据**：七条都红在授权 / 事务边界，且回执能区分「设计失败」与「工具故障」（verifier FAIL → `cause_status=BLOCKED`，保留 `verifier.status=FAIL`）。本组所需的「提交前重核实际文件与验证回执」由 **`C3-P4`** 覆盖（§9 commit 谓词：verifier 返回后重算 stage source/report hashes 与回执一致），C5 组内**不另设条目**——记此归属是为了「主张 → 证据」可追溯。
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
| **C6-P6** | 五条 run_round 真实跑完；负例取 E3 的「**保留旁路**」形态——按合同 §7，E3 唯一允许的最终变化包含「两条旁路删除」，负例即补齐两只 22R 电阻但**不删除那两条竖向旁路线** | 正例：route 与 exact/protected 吻合并 `COMMITTED`。负例：`DeltaCheck.unexpected` 非空或 `actual_delta_sha256 != authorized_delta_sha256`，`compare_protected` 报保护投影不等，`TransactionStatus != COMMITTED`——**不得产生候选提交** |

**通过判据**：P1/P2 必须以失败（而非 SKIP）结束；**P3–P5** 均无候选字节被提交，且回执字段未被抬高；**P6 正负例分开判**——其**正例**（五条 run_round 正常路径）必须真实 `COMMITTED`，这是 C6 唯一允许出现候选提交的条目；其**负例**（E3「保留旁路」形态）不得产生任何候选提交。
**假红示例**：未设置 opt-in 就运行——那本来就允许 SKIP，验不到任何东西。

---

## 3. 记录格式（每条扰动一份，落盘后不改写）

```text
perturbation_id:   C3-P1 … C6-P6
claim:             <被验的主张，引合同章节>
method:            <扰动怎么做；作用在哪个副本>
expected_red:      <字段 + 状态 + reason code>
observed:          <实际输出的关键字段原文>
verdict:           PASS | FAIL | UNKNOWN | TOOL_ERROR | NOT_RUN | NOT_APPLICABLE
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
- **载荷不随判据公开**（Q-B5-1）：本文件描述每条扰动**改什么、红在哪**；具体载荷（伪造回执 JSON、坏 XML、篡改后的 hash 字节、被替换的报告文件）在执行时生成，连同其 sha256 留在 host 侧的执行记录里。公开的是性质，不是可被针对性绕过的具体样本。

---

## 6. 已决（Percy 2026-09-12 裁定：三项均采纳起草者建议）

| # | 问题 | 裁定 | 落到哪里 |
|---|---|---|---|
| **Q-B5-1** | 公开方式 | **判据公开、扰动载荷 host-side 保留**。实现方应当照着这些性质建设（这与 A3 的评分断言不同，判据不是答案）；逐条载荷提前公开容易被特判掉 | 抬头状态块、§5 最后一条 |
| **Q-B5-2** | 存放位置 | `notes/b5-acceptance/`，即本文件当前位置 | — |
| **Q-B5-3** | 何时冻结 | **在 C3 合入之前**登记 sha256 | §7 |

## 7. 冻结程序

1. 本文件随仓库公开合入（判据公开，Q-B5-1）。
2. **在 C3 合入之前**计算全文 sha256 并登记进 AI 台账条目与合入提交；远端提交时间即「判据先于实现」的证据。C3 是 Yenefa 的下一个主线任务（B1，7h），判据晚于它落地，独立性就不存在了。
3. 冻结后不改。若发现判据本身写错，发布新版本并声明修正发生在**观测之前还是之后**；观测之后的修正**不得**用于重判已判条目（同 §5）。
4. 扰动载荷在执行时生成，其 sha256 记入 §3 的执行记录，载荷本体留在 host 侧。
5. C3–C6 逐组落地后即可执行对应组，不必等四组齐备（§4）。
6. **post-freeze erratum 登记（draft-5，2026-09-17）** —— 本文件第一次按第 3 条发布新版本。Owner（Yenefa）2026-09-17 裁定 C4-P3 的期望红与 PR-1 实现合同 §8 **直接矛盾**，明确扩 Scope 授权发布 draft-5，**仅限修正该一处**（不是重新开放整份判据）。

   | 项 | 值 |
   |---|---|
   | 触发 | C4-P3 原把「API 路径没有 `applied` 字段」这一**设计事实**当成失败依据；合同 §8 L253 规定该字段在本路径**本就为 `null`**，L255 规定本路径的成功由独立条件判定 |
   | 修正范围 | **仅 C4-P3 一行**。C4-P1/P2/P4–P8、C3/C5/C6、§1/§3/§4/§5/§6 正文均未改；条数不变（仍 28 条：C3 7 / C4 8 / C5 7 / C6 6） |
   | 旧（draft-4）全文 sha256 | `0db600762b06056f0da0479f23d5ee702311732f932fc8581ea17edfe1070a7c`（21105 B，git blob oid `c36a14b4b6277f015eceee34dca6f12e8767140f`；2026-09-13 由 `158f450` 登记，经 PR #71 于 2026-09-14T03:01Z 合入 master `0d31a8b`） |
   | 新（draft-5）全文 sha256 | 见同提交的 AI 台账条目 `AI-20260917-DSH-…`（按第 2 步登记）；本文件**不自带**自身哈希，以免自指 |
   | **哈希方法（重要）** | 取 **git blob（LF）字节**的 sha256：`git cat-file blob <ref>:notes/b5-acceptance/C3-C6_PERTURBATION_CRITERIA_DRAFT.md`，对输出字节做 sha256。**不要**直接哈希 Windows 工作树文件：`core.autocrlf=true` 且本文件在 `.gitattributes` 中无规则，检出为 CRLF，实测同一文件为 21312 B / `D97DBF5488F1859CF045BA94009991EE9F3A142EA92C09A4C251C17AD8B3A32B`。工作树字节与冻结值不符**不构成**篡改证据 |
   | 勿引用 | draft-4 存在过一个**已作废**的中间哈希 `96f2596f893f51be6e2f3d7c2bbde613f428c50632b18b560570428be6083df9`（`5f1ea53` 登记，11 分钟后被 `158f450` 重新登记并明确作废）。draft-4 的冻结值**只有** `0db60076…` |
   | 修正时点 | **发生在任何观测之前**：C4-P3 至今 `NOT_RUN`，尚无任何 native P3 qualification 被记录；故不触发第 3 条「观测之后的修正不得用于重判」 |
   | 依据 | 合同 §8（`docs/competition/internal/AEDL_PR1_实现合同_20260907.md` L236 / L253 / L255 / L257 / L263 / L371）；`docs/HANDOFF.md` L249–L250；`tasks/PR1-C4.yaml` L91；实现实测（`tools/akcli_adapter.py`：CONSTRAINED_EXCEPTION 路径 `tool_applied is not None` → 拒；STRICT 路径 `is not True` → 拒） |

   **未纳入本次 erratum、另报的两项**（保持授权边界，不顺手改）：§0.2 的「C3–C6 未落地」实测表已过期（C3 于 2026-09-14、C4 于 2026-09-17 落地）；C4-P2 的表述同样只对 STRICT 路径成立，未在本卡授权范围内。

---

## 版本表

| 版本 | 日期 | 状态 | 备注 |
|---|---|---|---|
| draft-1 | 2026-09-12 | `DRAFT — NOT FROZEN` | 初稿：四组共 28 条扰动，逐条钉在合同 §5/§7/§8/§9/§10/§11；当前状态经 master `c286489` 实测（C3–C6 全部未落地）；三项待决 |
| draft-2 | 2026-09-12 | `DRAFT — NOT FROZEN` | Percy 裁定 Q-B5-1/2/3，三项均采纳建议：判据公开、扰动载荷 host-side 保留；位置不变；冻结点定在 C3 合入之前。据此改写抬头状态块、§5 新增载荷保留条、§6 改为已决、新增 §7 冻结程序 |
| draft-3 | 2026-09-13 | `DRAFT — NOT FROZEN` | 按 PR #66 复核意见修订：六态词表注明出自 Y4 方案 §5（不在 PR-1 合同内）并说明 `NOT_APPLICABLE` 的用法，§3 记录格式的 `verdict` 与之对齐；`C3-P5` 补字段锚点与 reason code；`C6-P6` 定义「保留旁路」负例并补锚点 |
| draft-4 | 2026-09-13 | `DRAFT — NOT FROZEN` | 按交付侧复核意见（PR #66 两条，Owner 裁定一次改完）并入验收侧自查，共修订**五处**，**条数不变：仍 28 条（C3 7 / C4 8 / C5 7 / C6 6）**。① §C6 通过判据——P6 含正例（必须 `COMMITTED`），原「P3–P6 均不得提交」与之冲突，改为 P3–P5 不得提交 + P6 正/负例分开判；② `C5-P7` 期望红点名 `rollback.byte_equal=true` 并要求独立字节比对，不再只凭 `rollback.status` 自报（合同 §10 恢复规则 1/2 与最终回执 L405 已定义 VERIFIED 含字节相等，本条只把验收锚点钉到该字段）；③ C5 通过判据注明「提交前重核」由 `C3-P4` 覆盖；④ **验收侧自查补**：§1 规则 3「扰动之后若出现 `COMMITTED`，该条直接判失败」是**全局**规则，同样禁止 P6 正例——①只改组内判据不足以消除矛盾，故补写唯一例外并锁死「不得再设第二个例外」；⑤ **验收侧自查补**：`C5-P7` 扰动点原写「commit 前后」，其中「terminal record 写成之后」的子情形按恢复规则 4 应**重用 `COMMITTED`**，与本组「七条都红」互斥——扰动点收窄至 terminal record 之前，并声明该子情形不在 28 条之内。另把版本表按序号排正（原为 draft-1 / draft-3 / draft-2）。**本次修正发生在任何观测之前**（C3–C6 未落地、28 条均 `NOT_RUN`，见 §0.2），不触发 §5 / §7 第 3 条「观测后修正不得重判」 |
| **draft-5** | 2026-09-17 | **`FROZEN`（draft-4）+ Owner 授权的 post-freeze erratum** | Owner（Yenefa）2026-09-17 裁定 **P3 acceptance erratum**：C4-P3 原写「走 API 路径且 `tool.tool_applied=null` → 不得当成成功」，与 PR-1 实现合同 §8 **直接矛盾**（合同 L253：API 原生没有 `applied` 字段，`tool_applied=null` 是设计使然；L255：exception「同样要求每个 op ok、真实字节改变及重读成功；不能用 API list 非空作为成功条件」）。**只改 C4-P3 一行**，条数不变（仍 28 条：C3 7 / C4 8 / C5 7 / C6 6）；C4-P1/P2/P4–P8 与 C3/C5/C6、§1/§3/§4/§5/§6 正文一字未动。新旧全文 sha256 与哈希方法见 §7 第 6 条。**本次修正发生在任何 native P3 qualification 之前**（C4-P3 至今 `NOT_RUN`），不触发 §5 / §7 第 3 条「观测后修正不得重判」 |
