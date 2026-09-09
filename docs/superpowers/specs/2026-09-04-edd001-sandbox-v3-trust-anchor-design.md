# EDD-001 Sandbox V3 —— 外部信任锚与编排器灌注闭环设计规格

**状态：** 修订提案，`PENDING_HUMAN_REVIEW`。本稿把算法、信任边界、身份/密钥生命周期和兼容语义写成一套具体方案，待人工审定后冻结；不把提案称为已批准的设计冻结。Issue #5 要求“仅在设计获审后进入实现”，本 PR 不修改 `sandbox_runtime/**`、锁文件或现有 expectedFailure。

**日期：** 2026-09-04；修订：2026-09-09（PR #34 信任模型复审）。

**范围：** Issue #5 的外部信任锚、审批签名与编排器 actor/bundle/capability 注入。硬件合同、制造签发和下单流程不在本次变更内。

## 0. 已核对的实现基线与缺口

本次源码核对基线：PR head `9876e23d45cd7bf661bbd4047c6d8a1c9b912d99`。

- `protocol.py` 的 V2 SHA-256 为 `f7d44732785d17a20283f3a18fde7689eebfee78f10a93ae899e1dd116383cad`；现有 `HumanApprovalReceipt` 没有签名字段。
- `Sandbox.resume()` 仅接收 decision/approved_by/approver_role；`_human_review()` 后生成 approved_at，`_promote_or_reject()` 又用现场哈希重建审批内容。不能把这个流程直接称为“CLI 已签名”。
- `_latest_verification_hash()` 校验 JSON、内容地址、run/candidate、PASS 和 candidate hash，但没有认证来源。攻击者可重算 SHA-256 并伪造 PASS；哈希只证明字节一致，不能证明 verifier 身份。
- 既有 `test_review_2_self_consistent_forgery_requires_protocol_v2` 正是在伪造 verification receipt。只加“缺人工签名即拒绝”就让此测试通过，仍不能证明 verification 伪造漏洞已修复。
- `verified_bundle_sha256` / `capability_grants` 已在 V2 协议中，但编排器未注入；可写 `.actions.jsonl` 不能成为能力授权真源。
- 原稿记录的 **283 tests / 1 skip / 1 expected failure** 是原提交验证记录。本轮结果随 Review Bundle 单独记录；此设计文档不是新机制运行成功的证据。

## 1. 威胁模型与可信计算基（TCB）

攻击者可以读写 repository working tree、candidate 工作区、普通 receipt/evidence 目录、模型输出及这些目录内的 checkpoint、`.actions.jsonl` 和脚本；可以调用公开 CLI、伪造 JSON、重算内容地址、跨 run 重放、在验证期间更换路径或文件。不能把“人工键入 --approved-by”或“文件位于仓库外”单独当作隔离证明。

| 区域 | 信任与权限 |
| --- | --- |
| repository project data、candidate、普通 receipts、模型/执行器输出 | 不可信，全部按攻击者输入处理；不能提供 verifier 代码、权威公钥、政策或授权 |
| 人工签名 CLI 及其依赖、私钥访问边界 | 受保护安装，独立人工会话；Agent 不能读取私钥或调用可自动签名的会话 |
| promotion verifier、policy engine、最终 promotion 执行器及依赖 | 受保护 host 安装；代码/解释器/模块搜索路径不从 working tree 加载 |
| trust-root manifest、部署包/政策/bundle 的预期摘要 | 受保护 host config；只有人工运维身份可更新 |
| 权威 run/candidate 映射、actor/capability 台账、已消费审批记录、发布目标 | 受保护控制面状态；攻击者无写权限，编排器的普通 checkpoint 只是提示 |
| 本次待验的候选快照 | 由 TCB 拷贝到隔离目录，攻击者不可写；批准、重验与发布绑定同一快照 |

**采用方案：受保护安装包 + 仓库外 host config，并钉住 manifest SHA-256。**

- host bootstrap 从独立受信渠道取得安装包及依赖摘要，核验后装到攻击者不可写的位置。不能从攻击者提供的源码构建后，把该源码自身算出的哈希当作认证。
- host config 固定 trust manifest 的绝对路径及预期 SHA-256；两者均不接受 candidate、普通环境变量、可写 checkpoint 或调用者任意替换。manifest 缺失、摘要错误、路径落入不可信区域或部署隔离无法建立时保持 `BLOCKED`。
- 仓库可保存 schema/无授权效力的示例，不能从 `sandbox_runtime/contracts/trusted_approvers_v1.json` 自动加载权威密钥，也不能缺配置时回退到仓库 allowlist。
- 同一 OS 用户拥有任意主机文件/进程访问权限时，仅把私钥或 verifier 挪出仓库不构成隔离。部署必须使用受限 Agent 身份与独立的签名/控制面权限；未验证此边界的开发模式没有权威 promotion 能力。
- 最终消费者只接受受保护 promotion 执行器的结果；攻击者修改 working-tree `trust/store.py` 返回 ALLOW、写一份 promotion receipt 或伪造 CLI 输出，均不能改变权威状态。

**非目标：** root/管理员或 TCB/人工私钥已沦陷、人工判断质量、自动 PKI/多签门限、分布式信任和硬件制造签发。手工撤销、轮换和失效处理属于本设计，不排除在生命周期之外。

## 2. 算法、信任根与密钥/身份生命周期

**算法固定为 Ed25519；验证侧仅持有公钥。** HMAC 不作为本稿的候选运行模式，不允许算法降级或自制密码算法。实现依赖选用 `cryptography` 的 Ed25519 支持；具体版本、许可证/再分发登记与 `uv.lock` 更新在实现 PR 中核验，本设计 PR 不安装或宣称已部署新依赖。

host trust manifest v1 的每个 `signer_key_id` 至少包含：

```text
public_key        Ed25519 原始 32-byte 公钥的严格 base64 编码
principal_id      稳定的真人标识（账号 ID，不用可变的显示名）
allowed_roles     显式非空角色集合，例如 ["human_reviewer"]
not_before        UTC 生效时间
not_after         UTC 失效时间
revoked           boolean；true 后该 key 不再授权新的 promotion
```

manifest 自身必须有 schema_version 和单调递增 generation。重复 JSON key、未知字段/算法、重复 key ID、无效公钥或角色、无效时间范围均拒绝加载。固定摘要与最低 generation 放在受保护 bootstrap 配置中；攻击者不能重放旧 manifest 撤销一次吊销。

生命周期固定如下：

1. 两名真人各自生成并持有独立私钥，不共享密钥。私钥只存在于各自受保护的人工签名环境，不进入仓库、Agent shell 环境、编排器或普通 receipts；公钥登记需线下/已认证渠道确认归属。
2. 运维人工审核 principal_id、allowed_roles、公钥指纹和有效期后，原子部署新 manifest 与对应摘要/generation；普通代码 PR 不自动改变 host 的信任根。没有实际登记记录时保持 `TO_VERIFY`。
3. 每次 promotion 使用当时有效的 manifest 校验：receipt.approved_by 必须逐字等于 principal_id，approver_role 必须属于 allowed_roles；有效签名不授予任意身份或角色。
4. 吊销或丢失私钥时，先将该 key 禁用于未来 promotion，再生成新 key、新 key ID；key ID 永不复用。已签但尚未消费的旧审批同样失效，必须重新人工审批。历史签名仍可保留作审计，不能恢复授权。
5. 轮换采用新增 key ID、验证新配置、撤销旧 key 的手工流程。离队人员撤销全部 key；备份不能成为 Agent 可读副本。host config 更新失败时不回退到更旧配置。

## 3. 精确签名数据与 CLI → resume 流程

V3 保留现有 `HumanApprovalReceipt` 字段，追加 `signature: str = ""`、`signer_key_id: str = ""`、`candidate_id: str = ""`。原构造调用仍可解析；空值**不表示可信或允许晋升**。candidate_id 明确纳入签名，防止同 run 内别的候选借用审批。

签名只覆盖以下固定对象，所有值是字符串，`schema_version` 固定为 `human-approval.v3`；未知字段、缺字段、重复 JSON key、错误类型必须拒绝：

```text
schema_version, signer_key_id, run_id, candidate_id, candidate_sha256,
decision, approved_by, approver_role, approved_at
```

规范字节为：

```python
b"AEDL/HumanApprovalReceipt/v3\0" + json.dumps(
    payload, sort_keys=True, separators=(",", ":"),
    ensure_ascii=False, allow_nan=False,
).encode("utf-8")
```

签名为上述字节的 Ed25519 detached signature，严格 base64 编码，解码必须为 64 bytes。公钥从当前 host manifest 的 signer_key_id 查得，receipt 不携带可自授信的公钥。签名包含 key ID 与版本，禁止跨用途替换。approved_at 使用 UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`；只在签名前格式化，验签时不做 trim、大小写、Unicode 或时区重写。

完整流程（下述接口是实现阶段必须满足的契约，不是已有 API）：

1. 受保护控制面从当前候选创建不可变快照、确定 run_id/candidate_id/hash，并将该摘要与候选摘要展示给人工。不能盲信可写 checkpoint 中的摘要。
2. 人工 CLI 解析 signer_key_id，用 manifest 解析/核对 principal_id 和角色；现场生成 approved_at，构造完整未签 receipt，签 exact canonical bytes。
3. CLI 一次传递签名及全部原始字段：

   ```python
   Sandbox.resume(
       decision, approved_by=approved_by, approver_role=approver_role,
       approved_at=approved_at, signer_key_id=signer_key_id,
       signature=signature, run_id=run_id,
       candidate_id=candidate_id, candidate_sha256=candidate_sha256,
   )
   ```

4. resume、state、`_human_review()`、`_promote_or_reject()` 只校验/透传 signed fields；不再生成 approved_at，不以现场 hash 替换签名中的 candidate_sha256，不从空角色回退默认值。现场 hash 是独立比对输入，发现不同即拒绝并要求重新审批。
5. 签名私钥绝不传给编排器；通用 CLI 被 Agent 调用不构成人工审批。测试用 key 只能出现在 `TEST_ONLY` 测试上下文，不能进入生产 trust manifest。

## 4. Promotion 必须重新验证候选，普通 PASS receipt 不授权

**选择 fresh trusted verification，不选择在可写 receipt 目录中寻找历史 PASS 作为授权依据。** execution/verification receipt 可继续作为普通诊断记录不签名，但其来源不因此可信；禁止用它们授权 promotion 或 capability。

V3 `assess_promotion` 的实现必须由受保护启动器注入真实 verifier、快照解析器及受保护 run/policy/grant 状态，不能接收调用者注入的假 PASS 结果或任意 verifier 对象。缺少这些依赖的旧 `FileTrustStore(repo_root, receipt_root)` 构造仍可用于读历史记录，但不能返回 ALLOW。

决策流程：

1. 校验 TCB/config 可用且当前 key 未撤销/过期；检查 receipt 结构、签名、principal/role 和 run/candidate/hash 绑定。没有 receipt、只有裸 `approval_status=APPROVED` 或 unsigned V1/V2 receipt，都拒绝晋升。
2. approved_at 必须在 key 有效区间内，不能早于受保护 run 的创建时间；host 时钟不可用或超出 5 分钟未来容差时阻断。approved_at 是签名者声明的时间，不是可信时间戳服务证明；撤销检查始终按当前 host 状态执行。
3. `REJECTED` 也由人工 CLI 签名、由相同认证路径验收并生成审批审计记录，然后直接 `DENY / APPROVAL_REJECTED`，不调用用于放行的 fresh verify，不产生 promotion。验签失败的 REJECTED 不是已认证的人工拒绝。
4. 对有效 APPROVED，在受保护区域固化快照后重算 hash，与签名及受保护候选映射比对。目录成员、文件内容、相对路径均纳入既有 candidate hash 契约；拒绝 symlink/junction/path escape。复制期间检测变化或最终快照 hash 不符即拒绝；不得仅在攻击者可写目录上先 hash 再 verify。
5. 从受保护部署政策/bundle 预期摘要重验所有输入与覆盖要求，再调用 trusted verifier 的实际 read-back 检查，读取**同一快照**。普通 receipt 的 PASS/sequence/evidence_status、调用者的 `verification_status` 都不能替代此次结果。
6. fresh verify=FAIL → DENY；异常/超时/NOT_RUN/BLOCKED/缺真实 verifier 或证据不完整 → BLOCKED。普通 receipt 删改、伪造或顺序增大不能将结果变成 ALLOW。
7. 通过后由受保护 promotion 执行器以同一快照完成发布。检查 key/config 仍有效，并在同一控制面事务中消费此 run/candidate/签名字节摘要；并发/重复请求只返回既有结果，不重复执行副作用。禁止验证完再从可写 candidate 拷贝另一份内容，也禁止外部调用者凭一个可写 JSON 的 ALLOW 自行发布。

拟采用诊断：`APPROVAL_REQUIRED`、`APPROVAL_SIGNATURE_MISSING`、`APPROVAL_SIGNER_UNKNOWN`、`APPROVAL_SIGNATURE_INVALID`、`APPROVAL_IDENTITY_MISMATCH`、`APPROVAL_ROLE_DENIED`、`APPROVAL_KEY_INACTIVE`、`APPROVAL_REJECTED`、`EVIDENCE_STALE`、`VERIFY_FAILED`、`VERIFY_NOT_COMPLETE`。TCB 配置不可用作为独立 BLOCKED finding；诊断映射不得改变上述拒绝/阻断语义。

## 5. 编排器 actor / bundle / capability 灌注闭环

- `actor` 从受保护控制面注册的执行器身份映射注入，不能来自 request.subject、可写 checkpoint 或自报 compiler role；策略必须检查请求 actor 与授权 actor 一致。
- `verified_bundle_sha256` / `verified_manifest_path` 来自 trusted preflight 对固定预期 bundle 的重新读取。PARTIAL 允许展示缺口但不授予可执行能力；INVALID/MISSING/BLOCKED 不补造散列以继续执行，promotion 必须 COMPLETE。
- `capability_grants` 来自受保护控制面的权限台账（通过已认证执行器/控制面事件写入），不是 candidate 下 `.actions.jsonl` 或普通内容地址 receipt。持有其 hash 不能证明有该权限。
- capability 使用受信政策定义的精确 `key=value` token：只允许已登记 key/value、恰好一个等号、无首尾/内部空白，不做宽松归一化；重复、未知或冲突声明拒绝。至少绑定 run_id、actor_id、capability 与受保护授权记录；跨 run/actor 搬运无效。
- 编排器只能经受保护适配器获取这些值。缺注入保持 fail-closed，普通 graph 状态即使被改成 PASS/APPROVED/有效 grant，也不能绕过最终 protected promotion。

## 6. V1/V2 兼容边界与交付阶段

数据结构与导入符号保持增量兼容，历史 unsigned receipt 仍可读取作审计；**授权语义不向后放宽**：裸 APPROVED、默认空签名、新字段缺失、缺 TCB 的旧构造一律不能在 V3 promotion 返回 ALLOW。不提供 production legacy-allow 开关。

本设计审定后才分阶段实现：先部署 TCB/config 与精确签名编解码，再接 fresh verify/受保护发布及能力灌注，最后运行对抗/集成测试并核验 OS 权限。没有真实部署证明时只能报告“测试环境机制通过”，不能报告“外部信任锚已上线”。依赖版本和机器路径在实现/部署记录中锁定，不重新打开 Ed25519、信任根位置、拒绝语义与 identity binding 的架构选择。

## 7. 必须先红后绿的验收矩阵

| 用例 | 必须观察到的结果 |
| --- | --- |
| 修改仓库 allowlist / store.py / 同名 Python 模块 / config hint | 受保护执行路径不采用它们；不能影响权威 promotion |
| 正确 manifest 配合攻击者替换的预期摘要；旧 generation 重放 | BLOCKED，预期摘要与最低 generation 只能来自 protected bootstrap |
| 自洽伪造 verification PASS + **真实合法人工签名** + fresh verifier FAIL | DENY；实际 verifier 被调用；此用例不可用“缺签名”提前返回冒充修复 |
| 同上 + verifier 超时、异常、缺失、NOT_RUN、BLOCKED | BLOCKED，不能回退历史 PASS |
| 历史 FAIL/伪造 PASS 任意排序、删除普通 receipt | 不产生授权；仅可能影响诊断可用性 |
| signed payload 任意字段变动、非规范签名、错误 key、假公钥 | DENY；包括 key ID、candidate ID、approved_at 与版本/域 |
| 合法 key 冒名 approved_by / 越权 role / 已撤销或过期 key | DENY；历史有效签名不能恢复当前授权 |
| CLI → resume → checkpoint 恢复 → receipt 编解码 | signed fields 和 canonical bytes 逐字相同；时间与 hash 均不重算覆盖 |
| 跨 run、跨 candidate、重复或并发消费、run 创建时间之后的状态回滚 | 不发生未授权/重复发布；run/消费记录从 protected state 校验 |
| 人工签名后换 candidate；复制期间修改；verify 后更换 live 目录 | hash 不符即拒绝，最终只发布已验证快照，无 TOCTOU 换包 |
| `.actions.jsonl`/subject/checkpoint 伪造 grant、错误 actor、bundle 漂移 | DENY/BLOCKED，缺实际注入时不能 ALLOW |
| unsigned V1/V2、裸 APPROVED、无 TCB 的旧构造 | 可读取历史，不能 promotion ALLOW |
| signed REJECTED；signed APPROVED + fresh PASS + 完整可信输入 | 前者认证后 DENY 并留审批记录；后者恰好一次成功发布 |

保留原 expectedFailure，直到实现真正关闭它表达的漏洞；转绿时同时具备“真实签名 + 伪造 verification”负向测试和成功路径。同步更新 `StrictTrust` 与 CLI/state 集成测试，禁止只依靠全部拒绝取得绿灯。Sandbox 全套、主仓库回归和 `dev_gate` 必须真实运行；实际 EDD-001 preflight 缺硬件资料/真实 verifier 时保持诚实 BLOCKED。

## 8. Evidence / 审核

本 PR 的文档与现有回归检查属于开发验证；新密码学路径、host ACL、key custody、真实 EDD-001 promotion 均为 `NOT_RUN`。实现阶段再登记真实对抗测试/部署验证 Evidence，不能以设计文本或 CI 绿灯替代。

AIC Score Target：创新性与方案设计（Issue #5）。ADR 在设计人工审定时登记；本稿不冒充已采纳的架构决策。

Human review：`PENDING_HUMAN_REVIEW`。

接口参考：[cryptography Ed25519 官方文档](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/)。该引用仅核对算法接口/编码长度，不构成当前实现或依赖版本证据。
