# EDD-001 Sandbox Runtime — Agent L 交接

**Status: PENDING_HUMAN_REVIEW**（rev3：V2 协议适配完成——审批 receipt 消费 + 绑定校验 + manifest 收紧；rev2 的 3 项阻断修复见 §10，V2 适配见 §11）

- 日期：2026-09-01
- Agent：L（低难度 trust/evidence 块负责人）
- 任务包：EDD001-Agent-L-Trust.md（唯一可执行任务书，未执行 H/M 指令）
- 设计依据：docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md（已完整读取，无冲突）
- AGENTS.md：已完整读取（v1.4 全文 808 行），无冲突

## 1. 冻结协议核验

- 文件：`sandbox_runtime/src/aedl_sandbox/protocol.py`
- 实测 SHA-256：`f053aae27a1672ba19fd1311799590fa1f2be4e166c09eaed80f7117d6e52f53`
- 与 H handoff 记录**一致**，无 `STATE_PROTOCOL_DRIFT`。未编辑该文件（本任务对 protocol.py 零写入）。

## 2. 专属领地内改动文件（全部新增）

- `sandbox_runtime/src/aedl_sandbox/trust/__init__.py`（公共导出 FileTrustStore/canonical_json/canonical_hash）
- `sandbox_runtime/src/aedl_sandbox/trust/store.py`（FileTrustStore 全部实现 + canonical JSON 工具）
- `sandbox_runtime/contracts/bundle_manifest_schema_v1.json`（声明式契约，与代码校验器一一对应）
- `sandbox_runtime/contracts/evidence_event_schema_v1.json`（事件契约 + verification/promotion 的 candidate_sha256 条件要求）
- `sandbox_runtime/tests/trust/__init__.py`、`test_trust.py`（L1/L4）、`test_receipts_and_promotion.py`（L2/L3）
- `src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json`（真实 manifest）
- 本文件

领地外仅读取；未 revert/reset/checkout/覆盖任何他人文件；`gates/run_gates.py`、pyproject.toml、uv.lock、protocol.py 零触碰。

## 3. 公共 API

```python
from aedl_sandbox.trust import FileTrustStore
FileTrustStore(repo_root: Path, receipt_root: Path)
.sha256_file(path) -> str
.validate_bundle(manifest_path) -> tuple[EvidenceStatus, tuple[Finding, ...]]
.record(event: EvidenceEvent) -> EvidenceReceipt
.assess_promotion(request: PromotionRequest) -> PromotionDecision
```

Promotion 真值表（按判定顺序，命中即返回）：

| 条件 | Outcome | reason_code |
|---|---|---|
| verification_status = FAIL | DENY | VERIFY_FAILED |
| verification_status = BLOCKED / NOT_RUN | BLOCKED | VERIFY_NOT_COMPLETE |
| evidence_status = INVALID | DENY | EVIDENCE_INVALID |
| evidence_status = MISSING / PARTIAL | BLOCKED | EVIDENCE_INCOMPLETE |
| approval_status = PENDING | BLOCKED | APPROVAL_REQUIRED |
| approval_status = REJECTED | DENY | APPROVAL_REJECTED |
| candidate_hash ≠ 最新有效 verification receipt 的 candidate_sha256（含无 receipt） | DENY | EVIDENCE_STALE |
| PASS + COMPLETE + APPROVED + candidate_hash 当前且 receipt 有效 | ALLOW | PROMOTION_ALLOWED |

实现要点：

- canonical JSON：`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")`；NaN/inf/set 等不可序列化值一律归一为 `ValueError`。
- 事件寻址：`receipt_root/<run_id>/<event_hash>.json`，event_hash 覆盖含 input_hashes 的完整 canonical 事件；同事件重复记录幂等返回同一有效 receipt；已存在路径字节不同 → 返回 valid=false 且**不覆盖**（保留现场作审计证据）。
- "最新" verification receipt 的确定性排序：`payload.sequence`（int）优先，缺省 0，再按文件名字典序——写入 schema 说明，不依赖墙钟。
- `record` 对 verification/promotion 事件强制要求 `input_hashes.candidate_sha256`（64 hex），否则 ValueError。
- 路径防线：拒绝绝对路径、`..`、反斜杠/根相对、URL-only（`EVIDENCE_URL_ONLY`，永不成为 VERIFIED_SOURCE）、重复路径、负 size、畸形 sha256、未知枚举、未知字段（additionalProperties=false 语义）、symlink 逃逸（resolve 后 relative_to 校验）。
- bundle 状态机：required 文件缺失/哈希或 size 不匹配/mirror 不等 → INVALID；结构有效且带 missing_requirements → PARTIAL；COMPLETE 需无 missing_requirements + compilers/verifiers 双非空 + 全部 required 文件 VERIFIED_SOURCE；required 文件声明 MODEL_PRIOR/HUMAN_INPUT → `EVIDENCE_SOURCE_CLASS_INSUFFICIENT` finding 且封顶 PARTIAL。findings 按 (code, source, message) 稳定排序。

## 4. 六个合同文件实测（生成后独立重算二次核对，ALL MATCH）

| repo_path | size_bytes | sha256 |
|---|---|---|
| gates/contracts/edd001_core_base_contract_v1.json | 10058 | `d7dd6982fb82367c…`（64 位全值见 manifest） |
| src/hardware/edd001-board/evidence/contracts/edd001_core_base_contract_v1.json | 10058 | 同上（mirror 一致） |
| gates/contracts/edd001_pin_constraints_v1.json | 8610 | `e3b75e74860aa43d…` |
| src/hardware/edd001-board/evidence/contracts/edd001_pin_constraints_v1.json | 8610 | 同上（mirror 一致） |
| gates/contracts/edd001_usb_contract_v1.json | 6038 | `0094292e2340b7a7…` |
| src/hardware/edd001-board/evidence/contracts/edd001_usb_contract_v1.json | 6038 | 同上（mirror 一致） |

三组 mirror 均相等。完整 64 位哈希以 manifest 文件为真源（生成脚本与独立重算两次一致）。

## 5. 真实 EDD-001 manifest 状态

- `src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json`：
  schema_version=1 / domain_id=EDD-001 / board_id=project-027-edd001 / scope_status=FROZEN /
  evidence_status=**PARTIAL** / execution_status=NOT_READY / verification_status=NOT_RUN /
  approval_status=PENDING；6 文件 + 3 mirror_sets + tool_coverage 双空数组；
  missing_requirements 含全部 5 个必需 ID（EDD001_POWER_CONTRACT、ESP32_S3_WROOM_1_N8R8_DATASHEET、
  AP63203WU_7_DATASHEET、TYPE_C_31_M_12_DRAWING、USBLC6_2SC6_DATASHEET），
  **不含任何缺失文件的哈希/路径/文件名/URL**；notes 声明合同内 source URL 仅为引用而非冻结本地证据。
- `generated_at` 按"确定性"要求**未写入**（无可用的调用方确定性时间值；墙钟会破坏可复现性）。
- 未填补任何缺失证据、未修改任何合同文件。

## 6. 实际运行的测试与结果

命令（全部 `uv run --frozen --project sandbox_runtime`，未 `uv sync`，未改 pyproject/uv.lock）：

- `python -m unittest discover -s sandbox_runtime/tests/trust`
  → 先 RED（ModuleNotFoundError: aedl_sandbox.trust，RED/GREEN 序列第 1/3/5 步各确认一次 RED）
  → 最终 **Ran 24 tests, OK (skipped=1)**
- `python -m unittest discover -s sandbox_runtime/tests`（全 sandbox 套件，含 H 的 orchestrator 与 M 的 policy）
  → Ran 41 tests：**errors=2, skipped=1**——2 个 error 均为 `orchestrator/policy/test_design_policy`、
  `test_document_validation` 的 **ModuleNotFoundError（Agent M 的 policy 测试，M 并行开发中，非 L 领地，
  L 未触碰）**；我的 trust 24 例全绿。
- 六哈希独立重算（与生成脚本分离的第二次计算）→ **ALL MATCH**。
- 失败测试先行已落实：canonical/bundle、receipt、promotion 三阶段各自先确认 RED 再实现转 GREEN。

## 7. 未运行的命令 / 未做的事

- 未 commit、未 push（任务包禁止）。
- 未运行 `uv sync`、未安装任何依赖、无网络访问、无 subprocess/shell、无 EDA 修改、无 datasheet 下载。
- 未修改 gates/run_gates.py、M2 板、任何合同文件。

## 8. 已知限制

- symlink 逃逸测试在 Windows 无符号链接特权的主机上**诚实 skip**（1 例）；逃逸防线本体由
  resolve+relative_to 实现并有路径检查单测覆盖（`..`/绝对/URL 用例均实际运行）。
- `payload.sequence` 为"最新 receipt"的排序键：调用方（H 的验证器）写入 verification 事件时
  必须携带单调递增 sequence；缺省 0 时多 receipt 同序则回退文件名字典序。该约定已写入
  evidence_event_schema_v1.json 描述，**H 需知悉**。
- 全 sandbox 套件当前非全绿（2 errors 属 Agent M 领地）；trust 领地 24/24 绿。
- bundle COMPLETE 判定要求 required 文件全部 VERIFIED_SOURCE——UNVERIFIED_SOURCE 的
  required 文件目前同样封顶 PARTIAL（与 spec §3.3 一致，但 reason 粒度未单列）。

## 9. Git 状态

- Branch：`fix/m2-schematic-semantic-release`（工作树为多 agent 共享，含 H/M 及早前会话的未提交改动）
- HEAD：`f169018`（本任务开始时即在此，未产生新 commit）
- Commit：未提交（任务包禁止）
- Push：未推送（任务包禁止）
- L 领地文件均处于未跟踪/新增状态，不影响他人改动


---

## 10. rev2——人工审核 CHANGES_REQUIRED 的 L 领地修复（AI-20260901-002）

人工审核 5 项 P1 中 3 项属 L 领地（store.py），全部**先复现后修复**，反例固化为回归测试：

1. **run_id 路径逃逸（已复现：`../escaped` 实际写出 receipt_root）→ 已封堵**：
   run_id 必须命中 `_SAFE_SEGMENT_RE`（单段、字母数字开头、无分隔符/无 `..`/无隐藏段），
   否则 ValueError；写前再对目标路径做 resolve+relative_to 的 receipt_root 包含校验（纵深）。
2. **原子且不可覆盖写（TOCTOU 修复）**：`write_bytes` 改为 `os.open(O_CREAT|O_EXCL|O_WRONLY)`
   独占创建——竞态写入方或已存在的碰撞文件永远不会被覆盖；碰撞时读回比对字节定 valid。
3. **消费前全量复验 receipt**：`_latest_verification_hash` 现在逐文件要求——字节恰为事件的
   canonical 序列化、文件名 stem == sha256(canonical bytes)、run_id/candidate_id 匹配请求、
   event_type=verification、payload.status=PASS、candidate_sha256 合法 hex；任一不满足即忽略。
4. **反例回归测试**（`AdversarialRegressionTests`，审核指示 3）：路径逃逸 4 变体、
   错误内容地址/非规范字节/FAIL payload/错 run_id 四类伪造全 fail-closed、
   独占创建幂等性。**29/29 OK（1 skip + 1 expectedFailure）**。

**上报协议缺口（审核第 1 项 H 职责，L 无法在当前协议内闭合）**：完全自洽的伪造 receipt
（攻击者可自行计算 canonical 形式与内容地址）仍能通过全部 L 层校验——内容寻址本身无信任锚。
该向量只能由协议 V2 的可信 actor/capability receipt 闭合。已用 `@unittest.expectedFailure`
的 `test_review_2_self_consistent_forgery_requires_protocol_v2` 固化：**V2 落地后该测试必须转绿**。
L 未擅自发明接口（任务包 Shared interface boundary 条款）。

- 领地外阻断项（H 的 workspace.py 隐藏路径哈希、orchestrator 失败推进、M 的 NaN/自报审批）
  本会话零触碰，等待 V2 冻结后的并行派发。
- 测试计数更新：trust 29 用例（24→29，+4 对抗回归 +1 xfail）；全 sandbox 套件 41→46，
  2 errors 仍属 M 并行开发（非 L 领地）。
- 未 commit、未 push（等 V2 批次统一授权）。


---

## 11. rev3——协议 V2 适配（AI-20260901-003）

前置核验：V2 protocol.py SHA-256 `f7d44732785d17a20283f3a18fde7689eebfee78f10a93ae899e1dd116383cad`
（7101 字节）实测与 H handoff Wave 3 记录一致，无 drift。

### L 领地交付

1. **assess_promotion 消费 V2 审批 receipt**：`PromotionRequest.approval_receipt` 存在时，
   逐项校验——类型为 HumanApprovalReceipt、run_id 匹配请求、candidate_sha256 绑定当前候选、
   decision ∈ {APPROVED, REJECTED}、approved_by 非空白；任一不满足 →
   `DENY / APPROVAL_RECEIPT_INVALID`（带结构化 findings）。receipt 的 decision **取代**裸
   approval_status（裸 APPROVED + REJECTED receipt → DENY/APPROVAL_REJECTED，谎报无效）。
   V1 无 receipt 调用方行为不变。
2. **新增 6 例 V2 绑定测试**（ApprovalReceiptV2Tests）：bound→ALLOW、绑错候选哈希→DENY、
   跨 run→DENY、裸 APPROVED 盖不过 REJECTED receipt→DENY、匿名审批人→DENY、
   PENDING 状态 receipt→DENY。trust 套件 **35/35 OK**（1 skip + 1 expectedFailure）。
3. **真实 EDD manifest 收紧**：notes 增补 V2 冻结记录条（哈希 + 审批语义变化声明），
   approval_status=PENDING 保持真实；六文件哈希复核 **ALL MATCH**。

### 上报事项（L 领地无法闭合，需人工/H 裁决）

**A. xfail 裁决：`test_review_2_self_consistent_forgery_requires_protocol_v2` 保持 expectedFailure。**
评估结论：V2 的 HumanApprovalReceipt 是纯数据类（无签名/HMAC/密钥锚），orchestrator 也是
在进程内自造 receipt——纯软件层无法区分"经 interrupt 的人工审批"与"攻击者自造的同形 receipt"。
闭合该向量需要 V3 引入密码学锚（人工审批时用带外密钥签名 receipt），超出本轮 V2 范围。
按任务包边界未擅自发明接口，测试保持 xfail 如实标记。**这是有意的诚实状态，不是遗漏。**

**B. H 领地连锁失败（5 例）：orchestrator 构造的 receipt 缺 `approved_by`。**
我的校验（无具名审批人 → APPROVAL_RECEIPT_INVALID）正确触发 fail-closed，导致 H 的
INT-08/12/14/15 + CLI resume 5 例失败。根因是 V2 身份链缺口：`resume(decision)` 只收
APPROVED/REJECTED 字符串，审批者身份无处录入。**修法在 H 领地**：
`resume(decision, approved_by=...)` 或 interrupt payload 携带审批人，orchestrator 构造
receipt 时填入。L 的严格校验不放松（放松 = 审核阻断项 4 复活）。
当前全 sandbox 套件 250 例：6 失败 = 5×H 的 approved_by 连锁 + 1×M 的 V1 钉值（预期漂移），
L 领地 0 失败。

### 未做 / 边界

- 未跑隔离副本全量与 M2 gate（本轮 sandbox 内改动不影响主仓库；提交前统一验收轮执行）。
- 未 commit、未 push（等 H 补 approved_by、M 适配完成后统一授权）。
