# EDD-001 Sandbox V3 —— 外部信任锚与编排器灌注闭环 设计规格（草案）

**状态：** 草案，PENDING_HUMAN_REVIEW —— 依据 Issue #5 自身验收标准："仅在设计获审后进入实现"，本文件本轮只提交设计，不改动 `sandbox_runtime/` 任何实现文件。

**日期：** 2026-09-04

**范围：** 关闭 Issue #5（Sandbox V3）标题所指两件事——(a) 外部信任锚，(b) 编排器灌注闭环。不涉及 M2、EDD-001 硬件合同或制造流程。

## 0. 现状核实（本轮实测，非转述 Wave 3 交接文档）

- `sandbox_runtime/src/aedl_sandbox/protocol.py` 当前 SHA-256 = `f7d44732785d17a20283f3a18fde7689eebfee78f10a93ae899e1dd116383cad`，与 `notes/edd001-sandbox/agent-h-handoff.md` §-2.0 记录的 V2 冻结值严格相等——V2 协议已是当前 master 的实际状态，非草案。
- 全量套件实测：`uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests -p "test_*.py"` → **283 tests, OK (skipped=1, expected failures=1)**。唯一的 `expectedFailure` 即 `tests/trust/test_receipts_and_promotion.py::test_review_2_self_consistent_forgery_requires_protocol_v2`（Agent L 标记，"KNOWN PROTOCOL GAP...Closing this vector needs trusted actor/capability receipts...V3"）。
- `grep -rn "verified_bundle_sha256|capability_grants" sandbox_runtime/src/aedl_sandbox/orchestrator.py` → 零匹配。`protocol.py` 中 `PolicyRequest.verified_bundle_sha256`/`verified_manifest_path`/`actor`/`capability_grants` 四个 V2 字段已冻结但从未被编排器写入——Agent H 在 §-2.4 第 3 条如实记录的缺口（"V2 bundle/capability 灌注待 M/L 适配"）在本仓库当前 HEAD 依然成立。
- `agent-m-handoff.md` §10 确认 M 的 V1 钉值已重钉为上述 V2 哈希，套件全绿——H 交接遗留的"M 钉值重钉时机"一项已自然解决，不再是待裁决项。

结论：V3 要关闭的不是一个空白问题，而是一个已经被前序三个 Agent 精确定位、范围很窄的两点缺口。以下设计直接对接这两点，不重新发明三层 Sandbox 架构（ADR-008 已批准该架构，见 `docs/compliance/DECISIONS.md`）。

## 1. 威胁模型（冻结定义）

**攻击者能力（in scope）：** 对仓库工作树、candidate 工作区（`run/<run_id>/candidate/<candidate_id>/`）与 receipt 目录拥有文件系统写权限的进程或 Agent——可以读取任意已有 receipt、计算任意 canonical JSON 字节与其 SHA-256、写出任意文件内容。这正是 L 在 rev2 已经对抗过的模型（伪造 receipt 变体、路径逃逸、非原子覆盖）；V3 只是把这个模型延伸到"审批 receipt 本身"。

**明确排除（out of scope，与 V1/V2 一贯的诚实披露风格一致）：**
- 不对抗能读取人工操作者本机私钥文件/环境变量的攻击者（即完整主机沦陷）——那是 OS/密钥托管问题，不是本 Sandbox 的职责边界。
- 不做撤销列表/证书链/密钥轮换自动化——两人团队规模下过度设计（同 ADR-009"不引入两人团队暂时不需要的复杂长期分支模型"的一贯尺度）。
- 不扩展到 execution/verification receipt 的签名——那两类 receipt 的可信度已经由"独立 verifier 重新读回工程文件"这个机制保证（Trust Sandbox 定义 §3.3），不是自证问题；只有 human-approval 这一类 receipt 存在"进程内自造"的死角（L 原话："纯软件层无法区分经 interrupt 的人工审批与攻击者自造的同形 receipt"）。
- 不声称已实现制造签发的密钥治理；`manufacturing_release` 相关签发仍是未来议题。

## 2. 核心设计判断：签名必须发生在 CLI 边界之外，而不是编排器内部

这是本设计与"直接给 HumanApprovalReceipt 加个 signature 字段、orchestrator 顺手算一下"这种做法的关键分歧点，值得在裁决前讲清楚：

`orchestrator.py` 的 `_promote_or_reject` 节点运行在 LangGraph 编排的同一进程/环境里——这正是威胁模型里"攻击者有文件系统写权限"覆盖的那个环境（修复循环里的 RepairPort、Executor 都在这个环境执行）。如果签名密钥必须被这个进程读到才能完成签名，密钥就和它要保护的对象活在同一个信任边界里,"外部锚"就名不副实。

现有代码已经提供了正确的边界：`resume(decision, *, approved_by, approver_role)`（`orchestrator.py:209`）要求人工在 CLI 显式键入 `--approved-by`，这个值只能来自人工在自己终端上的真实敲击,不经过任何 Agent 可达代码路径。V3 应该复用同一条边界,而不是新开一条:

- **签名动作放在 `cli.py` 的 `resume` 子命令里,在调用 `Sandbox.resume()` 之前完成**,对 `HumanApprovalReceipt` 除签名字段外的规范字节（run_id/candidate_sha256/decision/approved_by/approver_role/approved_at）做签名,私钥路径由人工在 CLI 显式传入（例如 `--signing-key-path`，或环境变量,两者都只存在于人工自己的 shell,从不落入仓库或 candidate 目录)。
- `orchestrator.resume()` 与 `_promote_or_reject`（`orchestrator.py:605` 构造 `HumanApprovalReceipt` 处）只新增一个不透明的 `signature` 透传参数,自己不做任何签名或密钥 I/O——延续"LangGraph/编排器不承担硬件正确性判断"的既有分权哲学(§7 of the V1 spec),这里是"编排器不承担密码学信任判断"。
- 验证方（L 的 `FileTrustStore.assess_promotion`,`trust/store.py:412`)只需要**公钥**,可以安全放進已提交仓库的 allowlist 文件——验证路径不需要接触任何密钥。

## 3. 协议 V3 变更（`protocol.py`，纯增量）

延续 V1→V2 的规则："只加不删，V1/V2 全部符号保持原形，全部新字段带中性默认值"：

```python
@dataclass(frozen=True)
class HumanApprovalReceipt:
    run_id: str
    candidate_sha256: str
    decision: ApprovalStatus = ApprovalStatus.APPROVED
    approved_by: str = ""
    approver_role: str = "human_reviewer"
    approved_at: str = ""
    # V3 additions — empty string is the V2-neutral default (unsigned receipt,
    # rejected by assess_promotion once signature verification is wired in).
    signature: str = ""
    signer_key_id: str = ""
```

新增一个独立的、由 L 领地维护的允许签名者清单契约（与 `bundle_manifest_schema_v1.json`/`evidence_event_schema_v1.json` 并列)：

- `sandbox_runtime/contracts/trusted_approvers_v1.json` —— `signer_key_id → {public_key, approver_role, added_at}` 的显式 allowlist,提交入库、人工维护、新增/吊销即一次可审计的 PR。

## 4. 判定语义变更（`FileTrustStore.assess_promotion`）

在现有真值表（`agent-l-handoff.md` §3 的判定顺序,当前实现于 `store.py:412` 起）中,`approval_receipt` 存在时的校验链新增一步,插在现有"类型/run_id/candidate_sha256/decision/approved_by 非空白"结构校验之后、`receipt.decision` 生效之前：

1. 若 `signature` 或 `signer_key_id` 为空 → `DENY / APPROVAL_SIGNATURE_MISSING`（区别于既有 `APPROVAL_RECEIPT_INVALID`,便于运维一眼分辨"缺签名"与"结构损坏"）。
2. 查 `trusted_approvers_v1.json`；`signer_key_id` 不在 allowlist → `DENY / APPROVAL_SIGNER_UNKNOWN`。
3. 用查到的公钥验签,验签对象是**除 signature 外**的 receipt 规范字节（run_id + candidate_sha256 + decision + approved_by + approver_role + approved_at,canonical JSON,与 L 现有 canonical 规则同一套)——验签失败 → `DENY / APPROVAL_SIGNATURE_INVALID`。
4. 全部通过才进入现有逻辑（`receipt.decision` 取代裸 `approval_status` 等)。

这三个新 reason_code 均落在既有 `APPROVAL_` 前缀命名空间内,不需要修改 `REASON_CODE_PREFIXES`。

**验收基准（复用既有 xfail,不新写口号式断言）：** `test_review_2_self_consistent_forgery_requires_protocol_v2` 应从 `@unittest.expectedFailure` 转为真实通过——攻击者纵使能计算出完全自洽的 canonical 字节与内容地址,缺少 `signer_key_id` 对应私钥即无法产生第 3 步能通过的签名,`assess_promotion` 必须落在 `DENY`。这是本设计对"关闭"二字的可执行定义,不是新发明的验收标准。

## 5. 编排器灌注闭环（`orchestrator.py` / `adapters.py`）

这部分 H 在 §-2.0 已经把语义定义清楚(见 `notes/edd001-sandbox/agent-h-handoff.md`),V3 的工作是**实现 + 对抗测试**,不是重新设计：

- **`verified_bundle_sha256` / `verified_manifest_path`**：`preflight` 节点调用 Trust Sandbox 的 `validate_bundle()` 拿到 `EvidenceStatus`（PARTIAL 或以上、非 INVALID）后,把 manifest 路径与其内容哈希封存进 receipt,再传入下游构造的 `PolicyRequest`——policy 自己不得再读合同文件（防止 policy 与 preflight 各读一份、产生 TOCTOU 或不一致）。
- **`capability_grants`**：`execute` 节点签发的权限声明（例如 `"writer=compiler"`）必须来自编排器自己的 action 台账（`workspace.py` 的 `.actions.jsonl`),而不是 request 里 caller 自报的 `subject`——即便攻击者能构造任意 `PolicyRequest.subject`,能力声明的真源头也不在其可控范围内。

## 6. 需要人工裁决的事项（本文件不代为决定）

1. **签名方案：非对称签名（推荐）vs. HMAC 共享密钥。** 我的倾向是非对称（如 Ed25519）——验证方（`FileTrustStore`，运行在攻击者能触及的同一环境）只需公钥，私钥永不进入该环境，这正是"外部信任锚"这四个字要求的边界；HMAC 更省事（stdlib `hmac`/`secrets` 即可，零新依赖），但验证方需要持有与签名方相同的密钥，边界强度打折扣。**这直接牵出下一项：**
2. **新增依赖。** `sandbox_runtime` 的依赖在 Wave 0 已明确冻结（`uv.lock` 视为权威，多份交接记录写明"依赖变更"是禁令外事项）。非对称方案需要引入 `cryptography` 或 `PyNaCl`；这本身是一次需要显式授权的依赖变更，不是我能替项目做的决定。
3. **`REJECTED` 是否也应流经 `assess_promotion` 并产生 receipt？** H 在 §-2.4 已把这个问题原样交回人工："是否让拒绝也经 assess（带 decision=REJECTED receipt）属语义变更，需人工裁决后另行派发"——V3 不是提出这个问题的人，只是如实转达它仍未被回答。
4. **两人团队的私钥/公钥 allowlist 运维方式**：谁持有签名私钥（Yenefa本人?两人各一把?）、密钥物理存放位置、`trusted_approvers_v1.json` 的变更走不走 PR review——这是团队协作约定，不是纯技术设计。

## 7. 验收标准

- `test_review_2_self_consistent_forgery_requires_protocol_v2` 从 xfail 转为真实通过（§4 的可执行定义）。
- 新增对抗用例覆盖 Issue #5 任务清单点名的四类：伪造 receipt（签名字段被篡改/替换）、跨 run 重放（同一签名者对 run-1 的合法签名被搬到 run-2 的请求上）、错误 actor/grant（`capability_grants` 来源不是编排器台账时必须不可信）、bundle 漂移（`verified_bundle_sha256` 与当前 preflight 重算不一致）。
- 现有 283 例全绿不回归；新增用例全部先红后绿，遵循本仓库一贯的"先复现后修复"纪律。
- `sandbox_runtime/tests/orchestrator/fakes.py` 的 `StrictTrust`（H 已建立的镜像校验双打）同步更新,使 H 未来若继续在 orchestrator 领地工作时也能独立捕获同类回归。

## 8. 非目标

- 不做撤销列表、密钥轮换自动化、多签名者门限方案。
- 不扩展签名要求到 execution/verification receipt。
- 不解决"人工判断是否明智"——只证明"谁按下了批准"不可伪造,不评价该判断本身的正确性。
- 不做跨主机分布式信任（仍是单一本地人工操作者模型）。
- 不因本设计而改变 M2/EDD-001 任何硬件合同或制造流程。

## 9. Evidence Needed

NO —— 本文件是设计提案,不是技术声明;不引用外部第三方来源,无需 datasheet 级证据。实现阶段的对抗测试结果才需要作为 Evidence 登记。

## 9.1 AIC Score Target

创新性与方案设计（与 Issue #5 一致）

## Human review

`PENDING_HUMAN_REVIEW`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
