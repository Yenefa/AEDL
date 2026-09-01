# EDD-001 Sandbox Runtime — Agent H 交接

**Status: PENDING_HUMAN_REVIEW**（Wave 0 接口冻结 + Wave 1 H1–H3 + Wave 2 H4 final integration + Wave 3 协议 V2 冻结与人工审核 P1 修复全部完成；未 commit / 未 push）

- 日期：2026-09-01
- Agent：H（高难度编排块负责人）
- 任务包：EDD001-Agent-H-Orchestration.md（Wave 0 + Wave 1 H1–H3 + Wave 2 H4 final integration）+ EDD001-Agent-H-V2.md（Wave 3：协议 V2 冻结 + 人工审核 CHANGES_REQUIRED 的 5 项 P1 阻断修复，含对前一轮未收尾工作的查缺补漏）
- 设计依据：docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md（已完整读取，无冲突）

## -2. Wave 3（协议 V2 冻结 + 人工审核 P1 修复）交付摘要（最新）

人工审核对本批次判定 CHANGES_REQUIRED（5 项 P1 阻断，反例已复现）。本轮时序：冻结协议 V2 → 记录 V2 SHA-256（停 INTERFACE_READY (V2)）→ 在 H 领地内完成全部 P1 修复与反例回归 → 补齐前一轮遗留缺口（V2 运行时接线、本小节与状态记录）。

### -2.0 协议 V2 冻结（INTERFACE_READY (V2)）

- 文件：`sandbox_runtime/src/aedl_sandbox/protocol.py`
- **V2 SHA-256：`f7d44732785d17a20283f3a18fde7689eebfee78f10a93ae899e1dd116383cad`**（7101 字节，LF 行尾，UTF-8；开工、P1 修复后、收尾三次复核零漂移——Wave 3 第二步全部改动在 orchestrator/workspace/state，从未触碰 protocol.py）
- M/L 开工基准：重算本文件 SHA-256 与上值严格相等；不一致即按 `STATE_PROTOCOL_DRIFT` 停止并报告。V1 冻结值 `f053aae27a1672ba19fd1311799590fa1f2be4e166c09eaed80f7117d6e52f53` 作废，仅作历史记录（见 §1）
- V2 四能力（只加不删；V1 全部符号保持原形，全部新字段带 V1 中性默认值，V1 构造与消费者不受影响，`test_protocol.py` V1 契约用例零修改通过）：
  1. **已验证合同 bundle hash**：`PolicyRequest` 增加 `verified_bundle_sha256` / `verified_manifest_path` 字段——由 Trust Sandbox `validate_bundle` 结果（PARTIAL 以上且非 INVALID）经 receipt 固化后传入；策略不得再自行读合同文件
  2. **可信 actor/capability**：新增 `ActorIdentity`（actor_id/actor_kind/run_id）与 `CapabilityGrant`（run_id/actor_id/capability/receipt_sha256，由 orchestrator 签发的 receipt 哈希钉定）；writer=compiler 等权限声明改从 orchestrator action 台账读取，不从请求者 subject 读取
  3. **候选绑定的人工审批 receipt**：新增 `HumanApprovalReceipt`（run_id/candidate_sha256/decision/approved_by/approver_role/approved_at）；`PromotionRequest` 增加 `approval_receipt` 引用字段（presence 时取代裸 approval_status 语义；V1 只设 approval_status 的调用方继续工作，形状由 H 定，M/L 适配）
  4. **compiler/verifier 身份与 candidate ID 一致性**：`ExecutionResult` / `VerificationResult` 增加 `actor_id`；candidate_id 不一致由编排器 fail-closed（见 -2.1 修复 2/3）
- 同步产出：`tests/orchestrator/test_protocol.py` 新增 `V2ProtocolAdditionTests` 9 例（V2 类型 frozen dataclass、字段与默认值、V1 中性默认、receipt 绑定 run/candidate、actor_id 携带）

### -2.1 审核 P1 阻断修复清单（5 项全部落地，均在 H 领地；审批人身份链接入见 -2.6）

1. **候选哈希排除全部点号路径（原 workspace.py:151）**：改为仅排除明确声明的内部簿记名单 `HASH_EXCLUDED_INTERNAL_FILES`（当前仅候选根的 `.actions.jsonl`；子目录同名文件视为内容参与哈希）；其余候选内容含隐藏文件与隐藏目录全部参与哈希
2. **ExecutionResult.success=False 未终止（原 orchestrator.py:307，execute 节点）**：失败、action_id/candidate_id 与请求不符、产物越界（绝对路径出界与 `../../` 相对上跳）→ 一律终态 fail-closed（`EXECUTION_FAILED` / `EXECUTION_IDENTITY_MISMATCH` / `EXECUTION_ARTIFACT_ESCAPE`）：不写有效 evidence receipt、不进 PHASE_VERIFY、不达人工审批；失败结果仍记台账（审计留痕，重放路径复用同一 triage 同判失败）
3. **verifier 返回其他 candidate_id 的结果被登记（原 orchestrator.py:335，verify 节点）**：`VERIFY_IDENTITY_MISMATCH` 终态，外来结果零登记（无 findings、无 receipt、无 verification_result、无人工中断）——身份不一致 = 信任链断裂
4. **非法 receipt 终止路径**：execution / verification / promotion 三处 receipt 无效（含被篡改/冲突的晋升 receipt）→ `EVIDENCE_RECEIPT_INVALID` 终态；晋升 receipt 无效时不晋升
5. **V2 运行时接线（本轮查缺补漏，前一轮冻结了协议但运行时三处脱节）**：
   - `state.py`：`encode_execution`/`encode_verification` 携带 `actor_id`（此前 V2 身份在状态/台账序列化时被丢弃）
   - `orchestrator.py`：execution/verification 的 EvidenceEvent payload 携带 `actor_id`（receipt 固化产出者身份）
   - `orchestrator.py`：晋升节点构造 `HumanApprovalReceipt(run_id, candidate_sha256=实时重算哈希, decision=APPROVED)` 传入 `PromotionRequest.approval_receipt`（此前该 V2 字段为死代码；收据绑定的是被晋升的确切字节，与 EVIDENCE_STALE 重算逻辑同源）

### -2.2 全部反例回归（本轮实测，逐条 PASS）

| # | 审核反例 | 回归测试（实际运行） | 结果 |
|---|---|---|---|
| 1 | 改隐藏工程文件后 candidate_sha256 不变、旧 receipt 仍有效 | test_workspace.py::test_hidden_file_mutation_changes_candidate_hash / test_candidate_hash_includes_hidden_files_and_directories / test_ledger_named_file_in_subdirectory_is_content_not_bookkeeping；test_integration.py::test_int_15_hidden_file_mutation_denied_evidence_stale（真实 M/L 链：隐藏文件变异 → EVIDENCE_STALE DENY） | PASS |
| 2 | ExecutionResult.success=False 仍继续流转 | test_orchestrator.py::test_failed_execution_terminates_fail_closed（trust.events=0、verifier=0、assess=0、无中断） | PASS |
| 3 | action_id/candidate_id 与请求不符仍登记 | test_execution_action_id_mismatch_terminates_fail_closed / test_execution_candidate_id_mismatch_terminates_fail_closed（trust.events=0、verifier=0） | PASS |
| 4 | 产物越界未终止 | test_execution_artifact_escape_terminates_fail_closed（绝对+相对两路；外部文件未产生） | PASS |
| 5 | verifier 返回其他候选结果被登记到当前候选 | test_verifier_identity_mismatch_terminates_fail_closed（trust 仅剩 execution 事件、verification_result=None、findings=[]） | PASS |
| 6 | 非法 receipt 未终止 | test_invalid_verification_receipt_terminates_fail_closed / test_invalid_promotion_receipt_withholds_promotion / test_approval_with_invalid_evidence_is_denied（Wave 3 语义：首个 invalid receipt 即 fail-closed，晋升前拦下） | PASS |
| 7 | 台账重放绕过失败判定 | execute 重放路径复用 `_execution_failure_reason` 同一 triage（源码级保证，-2.1 修复 2 注记） | 结构性覆盖 |
| 8 | V2 身份/审批链断裂 | V2IdentityAndApprovalReceiptTests::test_actor_id_flows_into_state_ledger_and_receipts（state/台账/receipt payload 三处 actor_id 一致）/ test_approval_attaches_candidate_bound_receipt（receipt 绑 run_id+实时哈希+APPROVED+具名审批人）/ test_resume_without_named_approver_is_rejected（匿名/空白审批人 → ValueError）/ CLI test_resume_requires_named_approver（缺 --approved-by → argparse 拒绝） | PASS |

### -2.6 L-V2 审批校验衔接：审批人身份链接入（Wave 3 第二轮，H 领地）

**背景与根因**：L 的 V2 适配（rev3）在 `FileTrustStore.assess_promotion` 上线了 receipt 严格校验——receipt 存在时逐项复验类型/run_id 绑定/candidate_sha256 绑定当前候选/decision 合法/**approved_by 非空白**，任一不满足 → `DENY / APPROVAL_RECEIPT_INVALID`，且 receipt.decision 取代裸 approval_status。H 前一轮构造 `HumanApprovalReceipt` 时未填 `approved_by`（resume API 只收 APPROVED/REJECTED 字符串，审批者身份全链路无处录入），导致 INT-08/12/14/15 + CLI resume 5 例连锁失败。**这是真实的 V2 身份链缺口，L 校验正确触发；H 未要求 L 松校验，修 H 侧。**

**修复（全部 H 所有权文件）**：
1. `orchestrator.py` `resume(decision, *, approved_by, approver_role="human_reviewer")`：`approved_by` 空白 → `ValueError`（人工决策必须具名——审批与拒绝同等要求，拒绝者也入审计）；resume payload 从裸字符串改为 dict `{decision, approved_by, approver_role}`
2. `_human_review` 节点：接受 dict resume payload 并盖 `approved_at`（UTC ISO，决策时刻）；兼容旧 str resume（裸 Command/旧 checkpoint → 无归因 receipt → L fail-closed DENY，不匿名晋升）
3. `state.py`：SandboxState 增加 `approved_by`/`approver_role`/`approved_at`（字符串，SQLite checkpoint 可往返）；`run()` 初始置空
4. `_promote_or_reject`：receipt 填满全部归因字段（approved_by/approver_role/approved_at）；promotion EvidenceEvent payload 记录 `approved_by`（审批人进信任台账）
5. `cli.py`：`resume` 子命令新增必填 `--approved-by`（人类操作者自报身份，录入 receipt）
6. `fakes.py` StrictTrust：镜像 L 的 receipt 绑定校验（run_id/candidate_sha256/approved_by 非空白，否则 `APPROVAL_RECEIPT_INVALID`），使 H 单元套件可独立捕获同类回归
7. 测试：全部 `resume()` 调用点（test_orchestrator 7 处 / test_integration 5 处 / test_cli 3 处）加 `approved_by`；新增 2 例回归（`test_resume_without_named_approver_is_rejected`、CLI `test_resume_requires_named_approver`）；`test_approval_attaches_candidate_bound_receipt` 增断言 approved_by/approver_role/approved_at

**验证（本轮实测）**：全量 252 例 → **唯一失败 = M 领地 V1 钉值**（-2.4 已知状态 1；5 例连锁失败全部消除）；orchestrator 聚焦 **84/84 OK**；trust 聚焦 **35/35 OK**；CLI 冒烟：`resume --decision APPROVED --approved-by human-smoke@example` → STATE_PROMOTED/PROMOTION_ALLOWED，state `approved_by` 落账，全部 receipt valid，protocol.py 哈希零漂移。

**遗留治理项（交人工裁决，非本轮范围）**：
- REJECTED 决策仍短路在 assess_promotion 之前（V1 语义，终态 `APPROVAL_HUMAN_REJECTED`，不产生 promotion receipt/事件）；拒绝者身份已入 state 审计但不进信任台账。是否让拒绝也经 assess（带 decision=REJECTED receipt）属语义变更，需人工裁决后另行派发
- L 的 xfail（纯数据 receipt 无法对抗自洽伪造，需 V3 密码学锚）H 知悉并认同其评估；本修复只解决"归因缺失"，不声称解决"伪造抵抗"

### -2.3 实测结果（含 -2.6 审批人接线后全部真实运行，2026-09-01）

- orchestrator 聚焦：`uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/orchestrator -p "test_*.py"` → **Ran 84 tests — OK，exit 0**（含 protocol V2 契约 9 例、ExecutionFailClosedTests 8 例、V2 运行时接线+审批人归因 4 例、INT-01~15、workspace 隐藏文件 3 例、CLI 审批人必填 1 例）
- policy 聚焦（M 交接命令形态，带 `-t .`）：**Ran 133 tests — 1 failure**（即 -2.4 已知状态 1；其余 132 全绿）
- trust 聚焦：**Ran 35 tests — OK (skipped=1, expected failures=1)**（L rev3 后基线；skip 与 expectedFailure 均为 L 既有，非 H 引入）
- 全量：`discover -s sandbox_runtime/tests -p "test_*.py"` → **Ran 252 tests — FAILED (failures=1)**，唯一 failure 同 -2.4 已知状态 1（M 领地 V1 钉值，预期漂移告警）
- CLI 冒烟（真实进程）：`preflight --repo-root . --domain EDD-001` → BLOCKED / `EVIDENCE_COMPONENT_SOURCE_MISSING` / 7 findings，**exit 1**；`run-fixture --scenario repair_then_pass` → HUMAN_REVIEW_PENDING（repair_count=1，PASS 候选 `cand-7bc865cbf67ef392`），**exit 0**；跨进程 `resume --decision APPROVED --approved-by human-smoke@example` → TERMINAL/`STATE_PROMOTED`/`PROMOTION_ALLOWED`（同 candidate_id，state `approved_by` 落账，全部 receipt valid），**exit 0**
- 收尾复核：protocol.py SHA-256 = `f7d447...3cad`（零漂移）；CLI 冒烟目录用毕即删（.runs 本身被 gitignore）；H 产物全部 untracked，未 stage/commit/push，未触碰他人未提交改动

### -2.4 已知状态与限制（如实披露）

1. **M 领地 V1 钉值失败（预期漂移告警，非缺陷）**：`tests/policy/test_edd001_preflight.py::test_protocol_sha256_matches_the_frozen_value` 仍钉 V1 哈希 `f053aae...`，在 V2 冻结后必然失败——这是 M 的漂移检测按设计触发。M 适配 V2 时将 `FROZEN_PROTOCOL_SHA256` 重钉为 -2.0 的 V2 值即恢复全绿。H 未跨所有权修改 M 文件（任务书禁令）。
2. ~~**HumanApprovalReceipt 的评审人归因字段**~~（**已解决，见 -2.6**）：`approved_by`/`approver_role`/`approved_at` 现由 `resume(decision, *, approved_by, approver_role)` 接入并填入 receipt 与 promotion 事件；匿名决策在 API 边界即被 ValueError 拒绝。注意 L 的评估仍成立：纯数据 receipt 不对抗自洽伪造（密码学锚属 V3）。
3. **V2 bundle/capability 灌注待 M/L 适配**：`verified_bundle_sha256`/`verified_manifest_path`/`actor`/`capability_grants` 已在协议冻结并有契约测试，但 orchestrator/adapters 尚未从 `validate_bundle` receipt 与 action 台账灌注（全仓 grep 证实除协议定义外无接线点）。V1 行为不变；M/L 适配轮接线。
4. **adapters.py 归属**：按 Wave 3 任务书禁令（不动 M 的 policy/edd001.py 与 adapters.py）本轮未触碰。
5. Wave 2 已知限制（TEST_ONLY 语义、policy 套件命令形态差异、evidence-ID 词汇等）继续有效，见 -1 节。

### -2.5 Commands not run

`gates/run_gates.py`（禁令）；任何 `git add/commit/push`（禁令）；`uv sync`/依赖变更（Wave 0 已冻结）；真实 KiCad/ERC/DRC/SPICE/LLM 调用（非目标）；M/L 领地文件修改（禁止，未发生）。

## -1. Wave 2 / H4 final integration 交付摘要

在 M/L 均完成交接后执行 H4，全部产物仍限定 H 专属所有权路径。

**硬门禁（全部通过后才开始 H4）**：
- protocol.py SHA-256 实测 `f053aae27a1672ba19fd1311799590fa1f2be4e166c09eaed80f7117d6e52f53`，与冻结值严格相等（收尾再核一次，仍相等，零漂移）
- 读取 agent-m-handoff.md 与 agent-l-handoff.md；确认 public API 与交接一致：`from aedl_sandbox.policy import SandboxPolicyEngine`（唯一导出）、`from aedl_sandbox.trust import FileTrustStore`
- M focused suite fresh：`discover -s sandbox_runtime/tests/policy -t . -p "test_*.py"` → **Ran 133 tests — OK，exit 0**（M 交接文档记载的标准命令形态）
- L focused suite fresh：`discover -s sandbox_runtime/tests/trust -p "test_*.py"` → **Ran 24 tests — OK (skipped=1)，exit 0**
- 无需修改任何 M/L 文件即可集成；未 import 任何 M/L private module

**H4 改动（全部 H 所有权内）**：
- 新增 `sandbox_runtime/src/aedl_sandbox/adapters.py` — 全仓唯一 import M/L public API 的模块：`PolicyEnginePort`（把编排器内部动作映射到 M 冻结动作词汇：`preflight`→`engine.preflight`、`execute_candidate`→subject 携带的 `design_action`/`design_subject`；非法信封 DENY/POLICY_SUBJECT_MALFORMED，绝不放行）、`build_real_edd001_policy_port`、`build_test_only_policy_port`、`build_trust_port`（FileTrustStore 结构性满足 TrustPort，直接透传）、`real_edd001_preflight`、TEST_ONLY 合成 policy 文档/bundle/fixture 双打、`build_test_only_fixture_orchestrator`
- 修改 `sandbox_runtime/src/aedl_sandbox/orchestrator.py`（3 处，对齐 L 事件契约）：① execution 事件 `input_hashes={"bundle_sha256": <64hex>}`（L schema 要求全部值为 64-hex，非 hex 的 bundle 引用确定性归一为 sha256）；② verification 事件 `input_hashes={"candidate_sha256": ...}` + `payload.sequence`（L 的单调排序键）；③ 晋升节点重算候选实时内容哈希再送 `PromotionRequest`（变异候选 → EVIDENCE_STALE 的关键），ALLOW 后追加记录 promotion 事件（同样携带 candidate_sha256）
- 修改 `sandbox_runtime/src/aedl_sandbox/cli.py` — `preflight` 从 Wave-1 fail-closed stub 换成真实 EDD-001 adapter（输出完整 findings，BLOCKED 时 exit 1）；`run-fixture`/`resume` 改用真实 M/L 端口（policy=合成 TEST_ONLY 完整文档引擎、trust=FileTrustStore、executor/verifier/repair 仍为 TEST_ONLY 双打）
- 修改 `sandbox_runtime/tests/orchestrator/test_cli.py`（真实 preflight 预期）
- 新增 `sandbox_runtime/tests/orchestrator/test_integration.py`（INT-01～INT-14）
- 更新本文件

**INT-01～INT-14 逐项实际结果**（test_integration.py，全部 PASS）：

| ID | 实际结果 |
|---|---|
| INT-01 | 真实 EDD-001 引擎过完整编排器：preflight BLOCKED / `EVIDENCE_COMPONENT_SOURCE_MISSING`（7 findings，含 4×组件证据缺失、POWER 合同缺失、compiler/verifier 注册缺失四类）；executor calls=0；run 目录未创建。真实 bundle manifest 经 FileTrustStore.validate_bundle 如实 `PARTIAL`（声明缺失 5 项 + 工具覆盖双空） |
| INT-02 | `DESIGN_SELECT_COMPONENT` 未知 MPN → DENY/`POLICY_COMPONENT_NOT_ALLOWED`，executor=0 |
| INT-03 | `DESIGN_ASSIGN_PIN` GPIO36 → DENY/`POLICY_PIN_HARD_FORBIDDEN`，executor=0 |
| INT-04 | `NETWORK_ACCESS` → DENY/`POLICY_NETWORK_DISABLED`，executor=0 |
| INT-05 | `FILE_WRITE` agent+kicad_sch → DENY/`POLICY_DIRECT_KICAD_WRITE`，executor=0 |
| INT-06 | `VERIFY_ARTIFACT` 请求 SPICE 覆盖 → BLOCKED/`POLICY_VERIFIER_COVERAGE_MISSING`，executor=0 |
| INT-07 | TEST_ONLY fail-once：execute→verify FAIL→repair→execute→verify PASS→interrupt；repair_count=1，2 个候选目录，executor 恰好 2 次调用 |
| INT-08 | resume APPROVED → `STATE_PROMOTED`/`PROMOTION_ALLOWED`（真实 FileTrustStore 判定）；无重复副作用（2 个互异 action_id 各执行一次，artifact 字节不变，全部 receipt valid） |
| INT-09 | resume REJECTED → `APPROVAL_HUMAN_REJECTED`（promotion DENY，trust.assess 未被调用），候选目录保留未晋升 |
| INT-10 | 相同 finding 连续两次 → `REPAIR_STALLED`（repair_count=1 < max=3，早于上限熔断，stall_count=1） |
| INT-11 | finding 逐轮变化 → `REPAIR_LIMIT_REACHED`（max=2，repair_count=2，verifier 恰好调用 3 次） |
| INT-12 | verify PASS 后向候选根写入 mutation.txt → resume APPROVED → 晋升节点重算哈希与 verification receipt 的 candidate_sha256 不一致 → DENY/`EVIDENCE_STALE`（L 引擎判定） |
| INT-13 | `FILE_WRITE` path=`../outside.txt` → DENY/`POLICY_PATH_ESCAPE`，executor=0，workspace 根/run 目录/上跳路径均无 outside.txt |
| INT-14 | SQLite checkpoint 跨进程重启：新进程/新执行器实例 resume APPROVED 后 executor 调用 0 次；run_id/candidate_id 与重启前一致；artifact 字节不变；action 台账行数不变；终态 STATE_PROMOTED |

INT-02～06/13 的路径说明：违反性设计动作经"完整 TEST_ONLY bundle 过 preflight → execute 门拒绝"路线终止（preflight 必须 ALLOW 才能到达 execute 门），全链真实 M 引擎判定；INT-01 用真实引擎+真实合同。

**Fresh final verification（全部本轮真实运行）**：
- `uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/orchestrator -p "test_*.py" -v` → **Ran 59 tests — OK，exit 0**（Wave 1 44 + Wave 2 新增 15：INT×14 + 真实 manifest PARTIAL 断言）
- `uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/policy -t . -p "test_*.py" -v` → **Ran 133 tests — OK，exit 0**
- `uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/trust -p "test_*.py" -v` → **Ran 24 tests — OK (skipped=1)，exit 0**
- `uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests -p "test_*.py" -v` → **Ran 216 tests — OK (skipped=1)，exit 0**（59+133+24=216，全绿）
- CLI 冒烟：`preflight --repo-root . --domain EDD-001` → BLOCKED JSON + 7 findings，exit 1；`run-fixture --scenario repair_then_pass --run-root sandbox_runtime/.runs/manual-smoke` → HUMAN_REVIEW_PENDING（repair_count=1，PASS 候选 cand-7bc865cbf67ef392），exit 0；跨进程 `resume --decision APPROVED` → TERMINAL/STATE_PROMOTED/PROMOTION_ALLOWED（同 candidate_id），exit 0
- 只读收尾：`git diff --check` exit 0（仅他人文件既有 autocrlf 警告）；H 产物全部 untracked；未 stage/commit/push

**H4 已知限制与如实披露**：
1. **policy 聚焦套件的命令形态差异（非 M 实现缺陷，交人工知悉）**：任务书 Appendix C 的 policy 命令省略 `-t .`，该形态下 M 的测试模块按平铺模式导入，其相对导入（`from .fixtures import`）报 ImportError（4 errors）；按 M 交接文档记载的命令（带 `-t .`）fresh 运行 133/133 全绿，且任务书的全量套件命令（`-s sandbox_runtime/tests`，包发现模式）下 216/216 全绿。即 M 的测试只在"以 tests 为根的包发现"或"带 -t ."时通过——这是发现方式差异，不是策略实现缺陷；H 未跨所有权修改 M 的测试。
2. TEST_ONLY 合成 policy 文档/bundle 仅证明编排机械闭环；不是 EDD-001 电子正确性的证据；真实 EDD-001 如实保持 BLOCKED。
3. 编排器 execute 门授权的是 subject 携带的单个冻结词表设计动作（V1 机械语义）；多动作设计会话、HIR 编译器、真实 ERC/DRC/SPICE 均为下一里程碑非目标。
4. M 交接提出的 evidence-ID 词汇不匹配、人工参数表/artifact kinds 权威等级问题保持现状，H4 未擅自 alias/伪造映射或提升其权威。
5. `sandbox_runtime/.runs/`（INT-01 与 CLI 冒烟的临时 run 目录）被 gitignore，不在真实 EDD evidence 路径内；INT-01 的 run 根因 M 的 repo 包含性检查而置于 repo 内的 gitignored 目录（`sandbox_runtime/.runs/int-01`），测试后即清理。

**Commands not run**：`gates/run_gates.py`（禁令）；任何 `git add/commit/push`（禁令）；`uv sync`/依赖变更（H 已在 Wave 0 完成且冻结）；真实 KiCad/ERC/DRC/SPICE/LLM 调用（V1 非目标）；M/L 私有模块 import（禁止，未发生）。

## 0. Wave 1（H1–H3）交付摘要


实现并验证了运行时编排核心，全部测试真实运行通过：

- **H1 SandboxState**（`state.py`）：TypedDict 跨层状态控制平面，承载 run/domain/bundle 哈希、candidate id/root/hash、phase、repair_count/max_repairs、findings、previous fingerprint、stall_count、policy/execution/verification/promotion 结果、evidence receipts、pending human action、human decision、terminal_reason；值全部 JSON 可序列化（SQLite checkpoint 可跨进程往返）；附带协议 dataclass 的 encode/decode 助手与 finding fingerprint。
- **H1 CandidateWorkspace**（`workspace.py`）：只允许在 `run/<run_id>/candidate/<candidate_id>/` 下创建与写入；拒绝绝对路径、`..`/多段/盘符/保留设备名标识符、相对遍历写、以及经 symlink/NTFS junction 的逃逸写（resolve 后落在 workspace root 之外即 `WorkspaceEscapeError`，且不产生任何外部文件）；冻结 baseline 无写入 API；candidate id 由 canonical 输入确定性派生；每候选 `.actions.jsonl` 追加式 action 台账（重复 action_id 查询返回首录结果）；candidate 哈希为非隐藏文件的确定性内容哈希（台账不参与哈希）。
- **H2 LangGraph 编排**（`orchestrator.py`）：`preflight → create_candidate → execute → verify`；verify PASS→`human_review`→`promote_or_reject`，FAIL→`detect_stall`→`repair`→`preflight`；任意 DENY/BLOCKED→终态；重复 finding fingerprint→`REPAIR_STALLED`，达 max_repairs→`REPAIR_LIMIT_REACHED`。SQLite checkpoint（`langgraph-checkpoint-sqlite`，DB 路径由调用方 run 目录提供，绝不写全局用户目录）；human interrupt 在晋升之前（`interrupt()` + 显式 APPROVED/REJECTED resume，无效值直接抛错）；幂等性=候选确定性派生 + action 台账短路（重复执行节点直接复用已录结果）。
- **H2 CLI**（`cli.py`）：`preflight`（Wave 1 失败关闭测试替身，输出 BLOCKED JSON、exit 1、注明 Wave 2 接线）；`run-fixture --scenario repair_then_pass --run-root <path>`（TEST_ONLY 夹具跑到人工中断即停，不自批）；`resume --decision APPROVED|REJECTED`（显式决策恢复；无 checkpoint/无 pending 时失败关闭 exit 2）。夹具端口全部 TEST_ONLY 且不生成任何硬件事实。
- **H3 测试**：`tests/orchestrator/` 下 fakes.py（确定性假端口，记录调用次数）+ test_protocol.py（Wave 0，15 例）+ test_workspace.py + test_orchestrator.py + test_cli.py。

修复记录（先红后绿）：① `self._repair` 端口属性遮蔽同名节点方法导致 LangGraph 收到端口对象——属性改名 `_repair_port`；② [FAIL,PASS] 场景断言预期错误（两候选各执行一次=2 次调用，action_id 互异各恰好一次）——修正断言并加 action_id 唯一性校验。

## 0.1 Wave 1 测试与冒烟（实际运行，2026-09-01）

聚焦套件（44 例全绿，exit 0）：

```powershell
uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/orchestrator -p "test_*.py" -v
```
实际结果：**Ran 44 tests — OK（无 skip），退出码 0**。

强制 RED/GREEN 场景逐条对应：
- 路径遍历与 symlink/junction 逃逸被拒（junction 回退经 `_winapi.CreateJunction` 实测，非 skip）：`test_workspace.py::test_rejects_traversal_identifiers / test_rejects_relative_traversal_writes / test_rejects_absolute_candidate_path / test_rejects_symlink_escape_and_writes_nothing_outside`
- 直接 KiCad 写请求到不了 ExecutorPort：`test_direct_kicad_write_request_never_reaches_executor`（executor.calls==0）
- DENY 与 BLOCKED 在候选执行前终止：`test_deny_terminates_before_candidate_execution / test_blocked_terminates_before_candidate_execution`（executor.calls==0，无 run 目录）
- 一次 FAIL 经修复转 PASS 并停在人工中断：`test_one_fail_routes_through_repair_then_pass`（repair_count==1，两个候选目录，pending interrupt 非 null，promotion_result 为 null）
- 相同 finding 两次→`REPAIR_STALLED`：`test_identical_findings_twice_trigger_repair_stalled`（repair_count==1，早于上限熔断）
- 达修复上限→`REPAIR_LIMIT_REACHED`：`test_max_repair_count_triggers_limit_reached`（max=2，repair_count==2）
- checkpoint resume 不重复 action_id 副作用：`test_restart_at_interrupt_does_not_repeat_side_effects`（新进程/新端口/新 checkpointer 恢复，executor 第二实例 0 次调用，candidate id 与 artifact 字节不变，终态 STATE_PROMOTED）
- 人工中断先于晋升：`test_interrupt_occurs_before_promotion`（trust.assess 0 次调用）
- 拒绝后候选不晋升：`test_rejection_leaves_candidate_unpromoted`（APPROVAL_HUMAN_REJECTED，trust.assess 0 次，候选目录保留）
- 批准仅在 PASS+证据完备后晋升：`test_approval_promotes_after_pass_with_complete_evidence`（STATE_PROMOTED，2 个互异 action_id 各执行一次）+ `test_approval_with_invalid_evidence_is_denied`（收据 invalid→EVIDENCE_INVALID，DENY）
- CLI 冒烟（真实进程）：`preflight` → BLOCKED JSON，exit 1；`run-fixture` → HUMAN_REVIEW_PENDING（repair_count==1，PASS 候选 cand-f5382ae7d8ebc5b9），exit 0；跨进程 `resume --decision REJECTED` → TERMINAL/APPROVAL_HUMAN_REJECTED（同一 candidate id），exit 0。

## 0.2 Wave 1 已知限制

- CLI `preflight` 是失败关闭测试替身（`POLICY_ADAPTERS_NOT_WIRED`），真实 EDD-001 判定在 Wave 2 接入 M/L 的 `SandboxPolicyEngine`/`FileTrustStore` 后才存在；当前不读取任何 EDD 合同。
- INT-01～INT-06、INT-12（真实 EDD-001 清单/合同、GPIO36、网络能力、EVIDENCE_STALE 变异检测）属 Wave 2 集成场景，本轮未执行。
- 修复循环的"新候选"语义：每轮 repair 派生新 candidate id（内容寻址），失败候选保留为审计证据；旧候选的 evidence receipt 不随新候选复用（evidence_status 判定按当前 candidate id 过滤）。
- langgraph InMemorySaver 仅用于单进程测试；SQLite 恢复已单测与真实 CLI 跨进程验证。
- `findings` 指纹基于 verification findings 的 (code,message) 对；execution findings 不参与指纹（V1 语义，Wave 2 如需可扩展）。

## 1. 冻结接口（M/L 消费基准）

- 文件：`sandbox_runtime/src/aedl_sandbox/protocol.py`
- SHA-256：**V2（当前冻结，Wave 3）`f7d44732785d17a20283f3a18fde7689eebfee78f10a93ae899e1dd116383cad`**（7101 字节，LF 行尾，UTF-8；详见 -2.0 节）。V1 历史冻结值 `f053aae27a1672ba19fd1311799590fa1f2be4e166c09eaed80f7117d6e52f53`（4196 字节，纯 ASCII）已由 V2 取代，仅作 Wave 0–2 审计记录
- 导入方式：`from aedl_sandbox.protocol import ...`（在 sandbox_runtime venv 内运行，见 §3/§4 命令）
- 冻结规则：M 与 L **不得编辑该文件**；开工第一步重算 SHA-256 并与本条核对，不一致即按 `STATE_PROTOCOL_DRIFT` 停止并报告
- 行尾提示：仓库 `core.autocrlf=true`，本文件当前为 LF。哈希以工作区实际字节为准；若日后重新检出被改写为 CRLF，字节级哈希会变化，届时需按 git blob 内容重新冻结

## 2. 公共符号

- 类型别名：`JsonValue`（递归 JSON 兼容类型：None/bool/int/float/str/list/dict）
- 枚举（str Enum）：
  - `Outcome`：ALLOW / DENY / BLOCKED
  - `LifecycleStatus`：DRAFT / CANDIDATE / REJECTED / PROMOTED / FROZEN
  - `VerificationStatus`：NOT_RUN / PASS / FAIL / BLOCKED
  - `ApprovalStatus`：NOT_REQUIRED / PENDING / APPROVED / REJECTED
  - `EvidenceStatus`：MISSING / PARTIAL / COMPLETE / INVALID
- 冻结 dataclass（V1 9 个）：`Finding`、`PolicyRequest`、`PolicyDecision`、`ExecutionResult`、`VerificationResult`、`EvidenceEvent`、`EvidenceReceipt`、`PromotionRequest`、`PromotionDecision`；**V2（Wave 3）新增 3 个**：`ActorIdentity`、`CapabilityGrant`、`HumanApprovalReceipt`，且 `PolicyRequest`/`PromotionRequest`/`ExecutionResult`/`VerificationResult` 增加带 V1 中性默认值的新字段（见 -2.0）
- runtime-checkable 端口（5 个）：`PolicyPort`、`ExecutorPort`、`VerifierPort`、`RepairPort`、`TrustPort`
- 常量：`REASON_CODE_PREFIXES = ("POLICY_", "EVIDENCE_", "EXECUTION_", "VERIFY_", "REPAIR_", "APPROVAL_", "STATE_")`

## 3. 环境（实际执行记录）

- uv 0.11.32；`uv python install 3.11` → 托管 CPython **3.11.15**（本机已预装该托管版本，系统 Python 未改动）
- `uv sync --project sandbox_runtime` → 生成 `sandbox_runtime/uv.lock` 与 `sandbox_runtime/.venv`
- 实装并经 `importlib.metadata` 核实：`langgraph==1.2.11`、`langgraph-checkpoint-sqlite==3.1.1`、`aedl-sandbox==0.1.0`（editable）
- 版本断言实测：`python -c "import sys; print(sys.version); assert sys.version_info[:2] == (3, 11)"` → `3.11.15`，通过

## 4. 测试（实际运行，2026-09-01）

命令（仓库根目录执行）：

```powershell
uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/orchestrator -p "test_*.py" -v
```

实际结果：**Ran 15 tests — OK，退出码 0**。

覆盖内容：五个枚举的成员与值逐一断言；reason-code 前缀表；九个契约类型均为 dataclass 且赋值触发 `FrozenInstanceError`；默认空集合（`details`/`findings`/`artifacts`）且 `details` 默认 dict 不跨实例共享；`Finding.details` 嵌套 JSON 往返、`EvidenceEvent.payload`/`input_hashes` JSON 序列化；五个端口的 runtime-checkable 正例/反例（含 `TrustPort` 双方法缺一不可）。

## 5. 本 Wave 创建的文件（全部在 H 专属所有权内）

- `sandbox_runtime/pyproject.toml`（requires-python >=3.11,<3.12；langgraph==1.2.11；langgraph-checkpoint-sqlite==3.1.1；hatchling；src 布局）
- `sandbox_runtime/uv.lock`（uv sync 生成）
- `sandbox_runtime/.gitignore`（.venv / .runs / __pycache__）
- `sandbox_runtime/src/aedl_sandbox/__init__.py`
- `sandbox_runtime/src/aedl_sandbox/protocol.py`（冻结，见 §1）
- `sandbox_runtime/tests/orchestrator/__init__.py`
- `sandbox_runtime/tests/orchestrator/test_protocol.py`
- 本文件 `notes/edd001-sandbox/agent-h-handoff.md`

Wave 1（H1–H3）新增/修改（全部仍在 H 专属所有权内）：

- `sandbox_runtime/src/aedl_sandbox/state.py`（新）
- `sandbox_runtime/src/aedl_sandbox/workspace.py`（新）
- `sandbox_runtime/src/aedl_sandbox/orchestrator.py`（新）
- `sandbox_runtime/src/aedl_sandbox/cli.py`（新）
- `sandbox_runtime/tests/orchestrator/fakes.py`（新）
- `sandbox_runtime/tests/orchestrator/test_workspace.py`（新）
- `sandbox_runtime/tests/orchestrator/test_orchestrator.py`（新）
- `sandbox_runtime/tests/orchestrator/test_cli.py`（新）
- 本文件（本 Wave 交付摘要更新）
- 未创建 `adapters.py`（属 H 所有权但为 Wave 2 专用，等 M/L 交接后再动）

## 6. 协作注意

- 测试目录布局约定：各测试子目录（`tests/orchestrator`、M 的 `tests/policy`、L 的 `tests/trust`）各自保留 `__init__.py`；`sandbox_runtime/tests/` 本身**不要**创建 `__init__.py`（该路径不在任何人的所有权内；最终套件 `discover -s sandbox_runtime/tests` 的递归发现依赖此布局）
- Wave 1 期间未读取、未依赖、未检查 M/L 的任何私有实现（本轮它们尚不存在于工作区）
- 开工时观察到 `docs/superpowers/plans/2026-09-01-edd001-sandbox-runtime-v1.md` 处于已 stage 状态（git status 显示 `A`）——非本 Agent 所为；本 Agent 未 stage、未 commit、未 push 任何文件
- 工作区既有未提交改动（NOTICE、合规台账、u3 提案、datasheet_manifest、spike/、EDD 合同等）全部原样保留，未触碰
- 本任务包未授予 `docs/compliance/AI_USAGE_LOG.md` 写权限；本交接文件是本 Wave 的指定留痕载体，台账补录由人工在批次收尾时统一裁决
- CLI 冒烟产生的 `sandbox_runtime/.runs/` 已被 `sandbox_runtime/.gitignore` 忽略，不会进入版本库

## 7. 下一步

1. **人工**：复审 Wave 3 交付（本文件 -2 节：协议 V2 冻结哈希、5 项 P1 修复、反例回归表、-2.6 审批人身份链接入、实测结果、已知状态）；裁决 -2.4/-2.6 所列治理项（M 钉值重钉时机、REJECTED 是否经 assess、L xfail 的 V3 密码学锚、V2 bundle/capability 灌注归属）
2. **M 适配（V2 已冻结，可开工）**：M 消费 `verified_bundle_sha256`/`capability_grants`/`approval_receipt` 并重钉其 V1 哈希测试（重钉为 `f7d447...3cad` 即恢复全绿）；完成后 orchestrator/adapters 的 V2 灌注接线
3. 复审通过后另行授权统一提交（H/M/L 均未 commit/push）；提交后进入下一里程碑：冻结 EDD-001 POWER 合同与本地 datasheet bundle → 定义最小 HIR → 确定性 KiCad 编译器适配器 → 独立读回解析器与合同验证器 → 首次沙箱原理图闭环（ERC+语义合同 PASS）→ 提交人工电路评审
4. 本轮 Wave 3（含 L-V2 衔接的审批人身份链修复）已按授权完成：**未 commit，未 push，未跨所有权修改任何文件**

**本轮状态：Wave 0 + Wave 1 + Wave 2/H4 + Wave 3（协议 V2 冻结 + 审核 P1 修复）全部完成，PENDING_HUMAN_REVIEW。**
