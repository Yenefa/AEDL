# 06 — Red Team：把 LLM Agent 接进 AEDL 后可能绕过 / 削弱 Trust Plane 的全部路径

> 纯代码审计研究。唯一写入文件为本文。所有行号来自对 `sandbox_runtime/src/aedl_sandbox/` 的静态精读（protocol / orchestrator / policy/engine / policy/edd001 / policy/paths / trust/store / adapters / workspace / state / cli），**未运行任何测试（NOT_RUN）**，未执行任何 git 操作。
> 分类纪律：`现有缺口` = 与 Agent 无关、今天就存在；`接入后新增风险` = 只有当 Harness 给出某个能力/数据通道才成立。两者不混写。未读到实现的写 `TO_VERIFY` / `UNKNOWN`。
> 配套：`02-repair-loop.md` D1–D10（proposal-only 已定），本文回答"proposal-only 之外还有哪些口子会被打开、打开会怎样"。

---

## 0. 审计锚点（事实）

| 事实 | 位置 |
| --- | --- |
| `RepairPort.propose(run_id, candidate_id, findings) -> PolicyRequest` 是唯一 LLM 插入点 | `protocol.py` L250-252 |
| `_repair()` 只消费返回值的 `action / action_id / subject` 三个字段写入 `repair_plan`；`run_id / domain_id / candidate_root / actor / capability_grants / verified_bundle_sha256` 全部被丢弃 | `orchestrator.py` L525-537 |
| `repair_plan` 中只有 `subject` 被再次读取（`_current_subject`）；`action`、`action_id` 写进 state 后无人消费 | `orchestrator.py` L310-314 |
| 生产代码中**没有任何地方构造 `CapabilityGrant` 或给 `PolicyRequest` 设 `actor`**（全仓库仅 tests 构造）→ `_has_capability_grant` 恒 `False` | `policy/engine.py` L378-398；grep 结果 |
| policy 只校验**内层** `design_subject` 的精确字段集；envelope 额外键不进 policy、但原样进 executor | `adapters.py` L162-196, L310-320；`policy/engine.py` L852-863 |
| `TrustPort.record()` 无签发者认证，内容寻址 + `O_EXCL`；`assess_promotion` 只认 `receipt_root` 下的 PASS verification receipt | `trust/store.py` L312-357, L359-409, L458-460 |
| action ledger（`.actions.jsonl`）无签名、且被排除出 candidate 内容哈希 | `workspace.py` L23, L125-156 |
| `resume()` 的 `approved_by` 只需非空、`approver_role` 任意字符串 | `orchestrator.py` L209-234；`trust/store.py` L442-443 |
| `checkpoint.sqlite` 与 candidate 同在 run 目录下 | `cli.py` L76, L93 |
| 五个 port 用 `@runtime_checkable` Protocol 做 `isinstance` 检查（只查方法存在） | `protocol.py` L235-258；`orchestrator.py` L143-151 |

---

## 1. 威胁清单

### A. 写入面

```
T-01 候选文件直写 → 自我认证（绕过 policy / transaction / fresh read-back）
```
**路径**：1) Harness 给 Agent 任一写入口（`CandidateWorkspace.write_candidate_bytes`、裸文件写、shell）；2) Agent 直接写入 `run/<run>/candidate/<id>/` 下的 artifact（不经 `_execute` 的 policy ALLOW）；3) `_verify` 只调 `verifier.verify(...)`，不核对文件来源（`orchestrator.py` L438-453），verifier 在 Agent 自产内容上判定；4) PASS → verification receipt（L454-476）→ 人工审批 → `_promote_or_reject` 只重算 candidate 哈希（L592）与核对 receipt（`store.py` L458-460），两条链都对"内容谁写的"无感 → 晋级。
**信任假设**：Agent 获得候选目录任意写能力。
**现有防线**：`workspace.py` L94-120（绝对路径/盘符/`..`/`.` 拒绝 + `_ensure_confined` resolve 复查）；`orchestrator.py` L86-96, L117-119（artifact 越界即 `EXECUTION_ARTIFACT_ESCAPE`）；`_execution_failure_reason` L99-120。**这些只约束"路径"，不约束"谁写的内容"** —— 内容来源无签名、无 txn 提交点、无"执行前/后 fresh read-back 与 execution receipt 比对"。
**缺口**：现有缺口（无内容来源证明）+ 接入后新增风险（写入口本身是接入决策）。防线对路径 fail-closed，对来源完全无防线（NONE）。
**V1 缓解**：永不给候选写能力；写只由 `ExecutorPort` 在 policy ALLOW 后发生；V1 的 inspect 只读 API 不暴露 `write_candidate_bytes`。

```
T-02 workspace 写入口的路径约束残留（穿越 / 保留名）
```
**路径**：1) Agent 传入畸形 relative 路径；2) 目标逃出 candidate 但仍在 workspace root 内（跨 run / 跨 candidate / 触及 `receipt_root`、`checkpoint.sqlite`，二者都在 run 根下：`cli.py` L76、`adapters.py` L562-564）；3) 写入即 T-04/T-16 的前置。
**信任假设**：Agent 拿到 `write_candidate_bytes`（或任何以 workspace root 为界的写工具）。
**现有防线**：`workspace.py` L94-110 逐段拒绝 `..`/`.`/绝对/盘符；L84-92 `_ensure_confined` 用 `resolve()` 后 `relative_to(self._root)` 复查；`policy/paths.py` L38-58 `resolve_within` 拒绝空串/`..`/越界（strict 拒绝根自身）。
**缺口**：`_ensure_confined` 的边界是 **workspace root 而非 candidate root**（L87），candidate 内约束完全依赖 L103 的字面 `..` 检查 —— Windows 段尾点/空格归一化（`".. "`）是否能在 resolve 后落回上级但仍在 workspace root 内，**TO_VERIFY（未运行验证）**；`_validate_segment` 只匹配精确保留名（L51），`con.txt`/`nul.txt` 未拦（写入结果 `UNKNOWN`）。防线在设计上 fail-closed，但这两点是未验证的边。
**V1 缓解**：V1 不给写入口（T-01）即整体豁免；若 V2 给写，先补测试证明"candidate 外、workspace 内"不可达，并把 `_ensure_confined` 边界收紧到 candidate root。

```
T-03 action ledger 伪造与重放（`.actions.jsonl`）
```
**路径**：1) Agent 写候选根下的 `.actions.jsonl`（`write_candidate_bytes` 对文件名无额外限制）预置 `{"action_id":"execute:<cand>","result":{"success":true,...}}`；2) `_execute` L372 读到 `recorded`，L385-389 直接跳到 `PHASE_VERIFY` —— **不调 executor、也不写 execution receipt**；3) 伪造条目不改变 `candidate_hash`（L23 排除出哈希），既有 receipt 不失效；4) verifier 判定 Agent 直写内容 → 自证闭环（与 T-01 合流）。另一变体：`get_recorded_action` 取**首条**匹配（L153），预置条目永远压过真实执行记录。
**信任假设**：Agent 有候选目录写能力。
**现有防线**：`orchestrator.py` L111-119 对"回放结果"同样 fail-closed（success/action_id/candidate_id/artifact 边界）；ledger 由 orchestrator 追加写（L394）。
**缺口**：现有缺口 —— ledger 无签名/MAC，且被有意排除出内容哈希（`workspace.py` L19-23 注释承认它是"运行时记录"）。校验的是**内容形状**，不是**写入者**。
**V1 缓解**：Agent 永不见 ledger 文件；ledger 路径进 never-grant 清单；V2 若要修，需给 ledger 条目加 HMAC 或纳入独立哈希（契约变更，ADR 级）。

### B. Trust / Evidence 面

```
T-04 伪造 PASS verification receipt（TrustPort.record 无签发者认证）
```
**路径**：1) 调用者构造 `EvidenceEvent(event_type="verification", input_hashes={"candidate_sha256": <当前候选哈希>}, payload={"status":"PASS","sequence":999,...})`；2) `record()` 只校验 `run_id` 是安全段（L316-318）与 verification/promotion 必须带 64-hex `candidate_sha256`（L319-323），**不校验调用者身份、不校验 status 真实性**；3) 内容寻址文件落盘（L331-357）；4) `assess_promotion` → `_latest_verification_hash` 只检查 canonical 串与文件名哈希一致、`event_type`、`candidate_id`、`status==PASS`、`sequence` 取最大（L359-409），**不认识签发者**；5) 与当前 `candidate_hash` 相等 → `PROMOTION_ALLOWED`（L458-461）。Agent 还能自己算 candidate 哈希（`workspace.py` L158-184 是纯公开函数）。
**信任假设**：Agent 拿到 `TrustPort` 实例、或能写 `receipt_root`（fixture 下即 `workspace_root/receipts`，`adapters.py` L562-564，与 candidate 同根）。
**现有防线**：canonical JSON + 内容寻址（L324-341）、`O_EXCL` 永不覆盖（L344-351）、`run_id` 路径段校验（L316-318）、orchestrator 只在自身流程内调用 record。**NONE on caller authentication。**
**缺口**：现有缺口（receipt = 文件系统隔离的函数），接入后新增风险（把 record 或 receipt_root 写权限交给 Agent）。防线对"字节篡改"fail-closed（`record()` 返回 `valid=False` → `EVIDENCE_RECEIPT_INVALID` 终止，`orchestrator.py` L421-428/L468-476），但对"合法字节的伪造签发"无防线。
**V1 缓解**：`TrustPort.record` 与 `receipt_root` 一律 never-grant；trajectory / agent 自述永不落 receipt_root（见 T-06）。

```
T-05 receipt_root 与 checkpoint.sqlite 与 candidate 同根 → 双篡改闭环
```
**路径**：1) Agent 获得以 run 根为界的写能力；2) 同时改 `checkpoint.sqlite`（`cli.py` L76/L93）与 `receipt_root/*.json`；3) 状态侧伪造 `verification_result.status`/`approved_by`（`state.py` L33-60），receipt 侧伪造 PASS → `assess_promotion` 的两道独立检查同时被满足。
**信任假设**：Agent 写权限越出 candidate（T-02 的归一化残留或 root 级写工具）。
**现有防线**：`_promote_or_reject` 不信 state 里的旧哈希，重算 `candidate_hash`（`orchestrator.py` L592）；approval receipt 绑定当前候选字节与具名 approver（L605-612，`store.py` L436-443）；`interrupt` 未 resume 前无法前进（L223-224）。**只改 checkpoint 不改 receipt → `EVIDENCE_STALE`（`store.py` L458-460）**。
**缺口**：现有缺口（checkpoint 无完整性链/签名，LangGraph SqliteSaver 原样落盘）；单点篡改被 receipt 对账挡住，但两处同权即无防线（NONE）。
**V1 缓解**：checkpoint 与 receipt 目录进 never-grant；Harness 不向 Agent 暴露 run 根句柄，只暴露 candidate 子树且只读。

```
T-06 Trajectory / Evidence 混淆（LLM 自述冒充权威 Evidence）
``` 
**路径**：1) Harness 用 `FileTrustStore.record` 记录 agent trajectory（"记录一下 agent 这轮干了啥"）；2) `record()` 接受**任意** `event_type`（L312-331 只特殊处理 verification/promotion 的哈希格式），payload 由 Agent 文本填充；3) 若事件类型被写成 `verification` 或 payload 被塞进 `status:"PASS"`，即直接进入 T-04 的伪 receipt 通道；4) 或下游把 trajectory 文件当成 receipt 用于报告/`EVIDENCE_INDEX` 主张。
**信任假设**：Harness 复用 Trust 口写 trajectory，或把 trajectory 目录当 evidence 目录。
**现有防线**：`_evidence_status` 只认 `state.evidence_receipts`（`orchestrator.py` L655-667），`assess_promotion` 只认 `receipt_root` 文件 —— trajectory 天然在信任链外，**前提是不写进这两处**。
**缺口**：现有机制对"谁写的 event"无区分（同 T-04）；把 trajectory 混进 receipt_root 是**接入后新增风险**，且一旦发生即为现有缺口被激活。
**V1 缓解**：`TrajectoryRecorder` 独立 append-only 文件、独立目录、独立扩展名；禁用 `TrustPort` 记录任何 LLM 事件；Evidence 条目只引用 orchestrator 写的 receipt。

### C. PolicyRequest 注入面

```
T-07 RepairPort 返回值字段透传（actor / capability_grants / candidate_root / verified_bundle_sha256）
```
**路径**：1) LLM 产出的 `RepairProposal` 被 Harness 直接落成 `PolicyRequest` 并把 `actor`、`capability_grants` 带进 orchestrator/policy；2) `_has_capability_grant` 的全部校验是：`actor.actor_id` 非空、`grant.run_id==request.run_id`、`grant.actor_id==actor.actor_id`、`grant.capability` 匹配、**`receipt_sha256` 非空**（`engine.py` L386-397）—— 它**从不把这个 sha256 与任何真实 receipt 对账**；3) Agent 自签 `CapabilityGrant(run_id=<已知>, actor_id="agent-1", capability="writer=compiler", receipt_sha256="deadbeef...")` 即通过 → `_handle_file_write` 的 `writer=compiler` 门槛（L791-803）或 `DESIGN_ASSIGN_PIN` 的 soft-reserved 覆盖（L556-568）被突破。`protocol.py` L108-110/L207 宣称"grants 从 orchestrator action ledger 读"，但**全仓库无该实现**（仅 tests 构造 grant）。
**信任假设**：Harness 透传 proposal 的 actor/grants 字段（今天 `_repair` 只取 3 字段，`orchestrator.py` L528-536，这行白名单是唯一防线）。
**缺口**：现有缺口（grant 校验不含 receipt 对账 + ledger 发放机制未实现，`TO_VERIFY: 是否有仓外实现`）；透传是接入后新增风险。当前因 `actor` 恒为 `None` 而整体 fail-closed（L386 `return False`），属"靠没人用它才安全"。
**V1 缓解**：Harness 自建 `PolicyRequest`，`actor` 固定为 harness 身份；proposal schema **拒绝**（而非读取）`actor/capability_grants/run_id/domain_id/candidate_root/verified_bundle_sha256/action_id`；grants 只能由 orchestrator 对账真实 receipt 后附加（先补 G1）。

```
T-08 envelope subject 旁路：policy 只校验内层，extras 直达 executor
```
**路径**：1) Agent 在 proposal 的 subject 里放 `design_action` + `design_subject`（合法内层）**外加任意键**（`design_subject(...)` 的 `payload.update(extra)` 正是这个形状，`adapters.py` L310-320）；2) `_evaluate_design_action` 抽出内层给 engine，envelope extras 被 policy 完全无视（L162-196）；3) orchestrator `_execute` 把**整个 envelope** 作为 `request.subject` 交给 executor（`orchestrator.py` L356-363）—— `_TestOnlyExecutor` 就从 envelope 取 `fixture_attempt`（`adapters.py` L471）；4) extras 成为绕过 subject schema 的 agent→executor 未过滤通道（可夹带路径、标志、注入串）。
**信任假设**：Agent 能提 proposal（V1 即成立）。
**现有防线**：内层 `design_subject` 精确字段集校验，多/少/错型即 `POLICY_SUBJECT_MALFORMED`（`engine.py` L303-331, L852-863，fail-closed）；action 词表封闭（L303-315）；`preflight` 直接丢弃 subject（`adapters.py` L151-157）。
**缺口**：现有缺口 —— envelope 层**零校验**（NONE），且 executor 消费的正是未校验的那层。policy DENY 只挡"设计动作非法"，挡不住"合法设计 + 恶意 extras"。
**V1 缓解**：Harness 构造 envelope 用固定白名单 schema（`design_action`/`design_subject` + 已知 fixture 键），proposal 中任何额外键直接拒绝并记 finding；executor 侧再做一次输入 schema 校验。

```
T-09 action_id / candidate_id 命名空间被 subject 控制 → 幂等与预算边界可迁移
```
**路径**：1) `candidate_id = derive(run, domain, bundle, subject)`（`orchestrator.py` L341-343，`workspace.py` L186-201），subject 由 Agent 全量替换（`_current_subject` L310-314）；2) `action_id = f"execute:{candidate_id}"`（L355）→ Agent 换一个 subject 键（如 extras 里加一个注释字段）即得到**新 candidate、新 ledger、新 action_id 空间**；3) 逃逸既有 ledger 的失败冻结（L372-389 first-match），重新触发 executor 副作用与新 verification receipt；4) 每轮新建目录/ledger/receipt 文件，磁盘与日志增长。
**信任假设**：Agent 控制 proposal subject（V1 即成立）。
**现有防线**：轮次被 `max_repairs` 封顶（L514-519）+ `recursion_limit = 6*(max+1)+10`（L170）；新 candidate 仍要走完整 policy → execute → verify；`run()` 拒绝二次启动（L176-178）。
**缺口**：机制本身是现有设计（subject 派生身份）；接入后被放大为"预算/副作用迁移"攻击。**不是越权写**，但削弱 ledger 的幂等语义（现有性质）。
**V1 缓解**：Harness 冻结 subject 的非设计字段（只允许白名单键参与 derive）；对每轮新建 candidate 计数并设 run 级上限（Harness 层预算）。

### D. findings / 自我验证

```
T-10 findings / datasheet / artifact 的 prompt injection
```
**路径**：1) 进 LLM 上下文的机器字段 = `state.findings` 全量 `code/message/source/details`（`state.py` L63-69）经 `_repair` 传入 `propose`（`orchestrator.py` L526-527）；2) `Finding.message` 内嵌 agent 可控字符串：action 名（`engine.py` L311）、mpn（L497）、路径（L763-767）、tool/capability（L734-739）、`actor_id` 等 payload；`details` 来自 verifier，可能回显候选文件内容（真实 verifier 实现 **UNKNOWN**）；3) 注入文本反向指挥 Agent。
**信任假设**：Agent 消费 findings 文本（V1 即成立）。
**现有防线**：findings **不驱动状态机路由** —— 路由只看 `terminal_reason` 与 `verification_result.status`（`orchestrator.py` L293-306），Agent 无法靠改写"希望看到的结论"改变走向；action 词表封闭 + subject 精确 schema 使"把注入文本当动作/主体"必然 DENY/BLOCKED（fail-closed）。
**缺口**：机器防线对**结构化通道**有效；对 **Harness 行为**（Agent 说服 Harness 去做某事）无防线（NONE）——这是接入后新增风险，不是现有 bug。proposal-only 下最有害的注入动作排序：①诱导 Harness 附加 grant（T-07）②诱导 Harness 落 extras（T-08）③诱导 Harness 写 receipt/trajectory 到 receipt_root（T-04/T-06）④诱导 Harness 调 `resume(APPROVED)`（T-13）。
**V1 缓解**：Harness 的工具/ACI 是**能力白名单 + 结构化输出 schema**，注入文本只能影响"下一条 proposal 的内容"，不能路由到能力；所有 findings 字段当不可信数据处理（不进 system prompt、不拼成指令）。

```
T-11 自我验证：Agent 控制 verifier 输入 / verifier 可被替换
```
**路径**：1) verifier 的输入是候选文件（`orchestrator.py` L441），其内容由 Agent 的 subject 经 executor 生成（fixture 直白演示：subject `fixture_attempt>=2` → `artifact.json` → PASS，`adapters.py` L471-503）；若 verifier 判据可被 subject 参数化，Agent 即"自证"；2) Harness 若允许 Agent 参与选择/构造 `VerifierPort`（或把 verdict 交给 LLM），独立 oracle 消失；3) port 检查只是 `isinstance` 结构检查（`orchestrator.py` L143-151，`@runtime_checkable` 只查方法存在）→ 任何带 `verify()` 的对象都能过装配。
**信任假设**：Agent 影响 verifier 选择、实现或判据。
**现有防线**：`_verify` 只信 `VerificationResult.status/candidate_id`（L442-450，candidate 不符即 `VERIFY_IDENTITY_MISMATCH` 终止）；verifier/executor/policy 是构造期注入的独立 port；verdict 写进 receipt（L454-467）。
**缺口**：现有缺口 —— 无"verifier 与注册表（`document.verifiers`）核对"、无"verifier 只读"约束（若 verifier 自己写候选，`candidate_hash` 在 L453 **之后**计算，会把 verifier 的写入算进 PASS 证据）。port 结构检查是 `UNKNOWN` 强度的弱防线。Agent 影响 verifier 本身 = 接入后新增风险（D1 禁止）。
**V1 缓解**：verifier/executor 实例由 Harness 硬编码装配，Agent 永不参与；`VerificationResult` 构造权 never-grant；verifier 必须只读（写路径不给）。

### E. 身份 / 审批面

```
T-12 ActorIdentity 冒用（actor_kind / actor_id）
```
**路径**：1) Agent 让 Harness 以 `actor_kind="compiler"` 或 `actor_id=<他人>` 发起动作；2) `actor_kind` 是纯描述字段、policy 完全不读（`protocol.py` L191-195 自述"本身不断言权威"）；3) `actor_id` 只在 `_has_capability_grant` 里与 grant 匹配（`engine.py` L393），而 grant 机制当前恒 False → 冒用**当前不改变任何判定**；4) 但 `ExecutionResult.actor_id` / `VerificationResult.actor_id` **不经任何注册表核对**就进 state、ledger 与 receipt payload（`orchestrator.py` L416, L462；`state.py` L104, L113）→ 审计链里的身份是自我声明。
**信任假设**：Agent 能影响 actor 字段构造；启用 grant 后（T-07）才升级为权限问题。
**现有防线**：policy 层 fail-closed（`actor is None → False`，L386）；grant 需 run/actor/capability/receipt 全匹配（L388-397）。
**缺口**：现有缺口 —— `actor_id` 未与 `document.compilers/verifiers` 注册表绑定（NONE），receipt 中的 actor 声明可伪；`approver_role` 同样不校验（见 T-13）。
**V1 缓解**：actor 三字段由 Harness 打戳且固定 `actor_kind="agent"`；proposal schema 拒绝 actor 字段；在启用 grant 前先补 G1。

```
T-13 人工审批无认证（resume / CLI）
```
**路径**：1) 任何能调 `orchestrator.resume(APPROVED, approved_by=<任意非空串>, approver_role="human_reviewer")`（`orchestrator.py` L209-234）或 `python -m aedl_sandbox.cli resume ... --approved-by X`（`cli.py` L130-147）的调用者即可批准；2) trust 只检查 `approved_by` 非空（`store.py` L442-443），`approver_role` 任意字符串直接进 receipt（`orchestrator.py` L554, L610）；3) 若 Agent 拿到 shell/CLI 句柄，可自批 → 配合 T-04/T-11 即端到端绕过人工边界。
**信任假设**：Agent 获得 shell/CLI/`resume` 句柄之一。
**现有防线**：必须存在 pending interrupt（L223-224）；decision 枚举校验（L216-217, L563-566）；legacy 字符串 resume 因无 approver 被 trust 拒绝 fail-closed（L555-562 + `store.py` L442-443）；approval receipt 绑定候选哈希（`store.py` L436-439）。
**缺口**：现有缺口 —— approver 身份/角色**无认证、无白名单**，是"调用者诚实"假设（NONE on authentication）。legacy 分支的 fail-closed 是有效防线，但对"具名假人"无效。
**V1 缓解**：`resume`/CLI 句柄 never-grant；Harness 不暴露 shell；审批走独立人工通道，`approver_role` 白名单校验（建议先补 G3）。

### F. 其余攻击面

```
T-14 上下文侧信道（ContextBuilder 泄漏）
```
**路径**：1) ContextBuilder 直接 dump `orchestrator.current_state()`（`orchestrator.py` L246-247，含 receipts 哈希、actor_id、approver）、`engine.document`（`engine.py` L224-226，全量 pin/参数/规则指纹与 supersession）、`get_recorded_action`（`workspace.py` L138-156，历史 action 结果）、或 `receipt_root/<run_id>`（他人 run 的候选哈希与 `approved_by` 个人信息）；2) 或 read 工具以 run 根为界，读到 baseline/未授权合同副本、他人 run 数据；3) 密钥类：sandbox_runtime 内**未发现任何读 env/secret 的代码**（grep `environ|getenv|api_key` 无命中）→ 本模块密钥泄漏面 `NONE`，仓库其他部分 `UNKNOWN`。
**信任假设**：ContextBuilder 的字段选择权；read 工具的作用域。
**现有防线**：**NONE** —— policy 词表里根本没有 READ 动作（`SUBJECT_SPECS`，`engine.py` L72-117），读取能力不受 policy 治理，只受 Harness 边界治理。
**缺口**：接入后新增风险（今天没有 Agent 读取通道）。policy 内容非机密（透明性是设计目标），但他人 run 数据 / approver 信息 / 未授权 baseline 属应控数据。
**V1 缓解**：ContextBuilder 只读白名单字段（当前轮 findings 全量 + 冻结 subject + 摘要历史，对齐 `02` D2/D3）；read 作用域限定当前 candidate 子树 + 已授权合同清单；不 dump `state`/`engine.document`/receipt_root。

```
T-15 预算与熔断绕过
```
**路径**：1) `finding_fingerprint` 只对 `(code, message)`（`state.py` L127-134），而 message 内嵌 subject 可控值（`engine.py` L497, L763-767）→ Agent 每轮换措辞级差异即可让指纹不重复，**吃满 `max_repairs` 而不触发 `REPAIR_STALLED`**；2) 每轮换 subject（T-09）→ 新 candidate/ledger/receipt 文件累积，无清理；3) 每次 `propose` = 一次 LLM 调用，**Harness 若在 `propose` 之外允许 Agent 自我循环重试，现有代码无任何约束**（`max_repairs` 只管图内轮次）；4) 反复产无效 proposal 触发 policy DENY → 直接 `terminal_reason` 终止（`_preflight` L331-336），这条其实是**便宜的止损**。
**信任假设**：Agent 控制 proposal（V1 即成立）；预算口径含 LLM token/调用数时才升级。
**现有防线**：`max_repairs`（L514-519）、`recursion_limit`（L170）、fingerprint 早熔断（L507-513）、policy DENY 即停、receipt `O_EXCL` 幂等（`store.py` L339-351）、`run()` 幂等（L176-178）。
**缺口**：现有缺口较轻（stall 指纹可被 message 扰动 —— 属现有设计，`02` D9 已知）；预算口径外的 LLM 循环是接入后新增风险（NONE 现有防线）。
**V1 缓解**：Budget&Stop 放在 Harness（每 run 的 LLM 调用数 / token / wall-clock 上限 + 无效 proposal 连续计数即停），不依赖 `max_repairs` 单独兜底；每轮 proposal 去重（`02` D7）。

```
T-16 LangGraph interrupt / checkpoint 状态面
```
**路径**：1) Agent 相关字段（`findings`、`subject`、`repair_plan`）进 checkpoint（`state.py` L33-60）；2) 试图经 resume 影响人工审查：`pending_human_action` 的 question 是硬编码常量（`orchestrator.py` L487-493），Agent 文本**目前**进不了审批提问；3) 若未来 Harness 把 findings/trajectory 拼进审批 UI 文本，即成社会工程面；4) 篡改 checkpoint（T-05）或调用 `Command(resume=...)` 注入（L551-562 已区分 mapping/string 两种回答）。
**信任假设**：Agent 能写 checkpoint 文件，或能触发 resume，或 Harness 扩展了 interrupt payload 内容。
**现有防线**：interrupt 必须经 `resume()` 且 decision/approved_by 校验（L209-234）；legacy 字符串 resume 被 trust 拒绝（L555-562）；`_promote_or_reject` 重算哈希 + receipt 对账（L592，`store.py` L458-460）→ 只改 state 难以独立晋级；`repair_plan` 只有 `subject` 被消费（L311-314）。
**缺口**：现有缺口 —— checkpoint 无完整性保护（签名/哈希链，NONE），interrupt payload 内容目前安全但**未被 schema 固定**（扩展即风险）。resume 无认证见 T-13。
**V1 缓解**：interrupt payload 结构冻结（Harness 层 schema 白名单，禁止塞 findings/trajectory）；checkpoint 目录 never-grant；审批文案不进 Agent 可影响的字段。

---

## 2. V1 禁止事项（never-grant）—— RFC ② Tool/ACI Contract 的 deny-by-default 输入

1. **任何候选/工作区写能力**：`write_candidate_bytes`、裸文件写、shell/`SHELL_EXECUTE`、任意路径读写工具（T-01/T-02）。
2. **`.actions.jsonl`（ledger）、`receipt_root`、`checkpoint.sqlite`、run 根**的读写（T-03/T-04/T-05）。
3. **`TrustPort.record` / `assess_promotion` 句柄**；任何会向 receipt 目录写字的 API（T-04）。
4. **`orchestrator.resume()` / CLI `resume` / `Command(resume=...)` 句柄**，以及 `approved_by`、`approver_role`、`human_decision`、`pending_human_action` 的写权（T-13/T-16）。
5. **`PolicyRequest` 的权威字段**：`actor`、`capability_grants`、`run_id`、`domain_id`、`candidate_root`、`action_id`、`action`、`verified_bundle_sha256`、`verified_manifest_path` —— proposal schema 遇到即拒绝，不透传（T-07）。
6. **envelope 额外键**：`design_action` + `design_subject` 之外的 subject 键一律拒绝（T-08）。
7. **port 装配权**：`PolicyPort/ExecutorPort/VerifierPort/RepairPort/TrustPort/checkpointer` 的选择与实例注入；`isinstance` 结构检查不构成授权（T-11）。
8. **结果对象构造权**：`VerificationResult`、`ExecutionResult`、`EvidenceEvent`、`EvidenceReceipt`、`Finding`（Agent 只能读 findings）（T-04/T-11）。
9. **`TrajectoryRecorder` 写入 receipt 目录或复用 `FileTrustStore`**（T-06）。
10. **网络出口**（policy 侧本就恒 DENY：`engine.py` L814-823；工具层同样不给）。
11. **跨 run / 他人 receipt / 未授权 baseline 的读权限**，以及 `engine.document`、`current_state()` 的全量 dump（T-14）。
12. **verifier 输入的参数化权**（Agent 不能选择 verifier 判据/版本，只能提供候选内容）（T-11）。

---

## 3. 必须先补的防线（缺口清单，两类不混）

### 3.1 现有缺口（与 Agent 无关，今天即存在）

| ID | 缺口 | 位置 | 为什么必须先补 / 或明确声明为信任假设 |
| --- | --- | --- | --- |
| G1 | `CapabilityGrant.receipt_sha256` **只查非空、不与真实 receipt 对账**；"从 action ledger 读 grant"在生产代码中**无实现**（仅 tests 构造） | `engine.py` L378-398；`protocol.py` L108-110/L207 | 一旦启用任何 capability（`writer=compiler`、soft-reserved pin 覆盖），grant 即可自签。**启用前必须实现 grant↔receipt 对账**（否则 T-07 必然成立）。当前因 `actor` 恒 None 而 fail-closed |
| G2 | receipt 无签发者认证，`receipt_root` 文件系统隔离是唯一控制 | `store.py` L312-357, L359-409 | 任何能写该目录者可铸 PASS receipt。至少要把 receipt_root 明确划为"进程外不可写"边界并写进文档；更优是加 MAC/签发者字段（契约变更 → ADR） |
| G3 | 人工审批无认证：`approved_by` 任意非空、`approver_role` 任意字符串直接进 receipt | `orchestrator.py` L209-234, L554, L610；`store.py` L442-443 | "谁批准"是审计主张，当前只是调用者声明。需 approver 白名单/角色校验，否则 T-13 永远成立 |
| G4 | action ledger 无签名且被排除出 candidate 哈希；first-match 读取 | `workspace.py` L23, L125-156 | 伪造 ledger 不触发任何哈希失效，且可抢先于真实记录 |
| G5 | 无"文件来源"证据：`_verify` 不比对 execution receipt 的 artifacts 与候选实际内容 | `orchestrator.py` L372-436, L438-453 | 只要出现直写入口（T-01），自证即成立。需"执行后 fresh read-back 与 execution receipt 绑定"或显式声明写隔离为唯一防线 |
| G6 | `actor_id` 未与 `document.compilers/verifiers` 注册表核对即入 receipt payload | `orchestrator.py` L416, L462；`state.py` L104, L113 | 审计链身份可伪（不影响 promotion 判定，但影响可信留痕） |
| G7 | envelope extras 零校验且直达 executor | `adapters.py` L162-196, L310-320；`orchestrator.py` L356-363 | policy 的精确 schema 只保护内层，executor 消费的是未校验层 |
| G8 | workspace 边界是 workspace root 而非 candidate root；Windows 归一化/保留名残留 | `workspace.py` L51, L84-92, L103 | `TO_VERIFY`：需测试证明 `..\ `类归一化不可达；补测试前不得开任何写入口 |

### 3.2 接入 Agent 后新增的风险（不是现有 bug）

| ID | 新增风险 | 依赖的既有薄弱点 | V1 控制 |
| --- | --- | --- | --- |
| N1 | findings/datasheet/artifact 文本进入 LLM → prompt injection | G7、G6（回显可控串） | 能力白名单 + 结构化 schema；注入只影响 proposal 内容，不能路由能力 |
| N2 | Harness 落 `PolicyRequest` 时字段透传 | G1 | 由 Harness 构造请求，proposal 拒绝权威字段 |
| N3 | Agent 获得任何写/网络/shell 工具 | G2/G4/G5/G8 | never-grant 第 1/2/10 条 |
| N4 | trajectory 混入 receipt/evidence | G2 | 独立 recorder，禁用 `TrustPort` 记 LLM 事件 |
| N5 | ContextBuilder 侧信道（他人 run、approver、baseline） | 读取面本无 policy 治理（NONE） | 字段白名单 + 作用域限定 |
| N6 | `propose` 之外的 LLM 自循环无预算约束 | 现有 `max_repairs` 只管图内 | Budget&Stop 放 Harness，独立计数 |
| N7 | 审批文案 / interrupt payload 被 Agent 文本污染 | payload 未被 schema 固定 | 冻结 payload 结构 |
| N8 | 装配期注入 Agent 可影响的 port 实例 | `isinstance` 仅结构检查 | port 硬编码装配 |

---

## 4. 不确定性

- **TO_VERIFY**：Windows 路径归一化是否能让 `workspace.resolve_candidate_path` 的字面 `..` 检查被 `..\ `/尾随点变体绕过（G8）；未运行任何测试。
- **TO_VERIFY**：`CapabilityGrant` 是否存在仓外/未读到的发放实现（grep 仅见 tests）；若存在，G1 的"对账缺失"需重新评估。
- **UNKNOWN**：真实 `VerifierPort` 实现的 `Finding.details` 是否回显候选文件内容（决定 T-10 注入带宽）；`sandbox_runtime` 内未见 verifier 生产实现，当前只有 fixture double（`adapters.py` L486-515）。
- **UNKNOWN**：`approver_role` / `actor_id` 是否已有仓外审计校验层（仓内未见）。
- **NOT_RUN**：本文无任何执行验证；所有"防线有效"的判断都是静态阅读结论。
- **最不确定的一点**：G1 与 G2 同时存在意味着"capability 授权"与"Evidence 签发"两条链的**根信任都落在文件系统/调用者诚实**上。V1 靠"不暴露这些句柄"就能安全，但这属于**边界纪律而非机制保证** —— 一旦未来某个 Harness 便捷功能（调试用 record、只读 ledger、审批自动化）打开其中一个口，防线不会报错、只会静默接受。
