# AEDL Control Plane — 最小原语

> 项目不是目录，也不是对话，更不是一个 Agent。项目是一套长期存在的 Control
> Plane；Agent 只是被调度进来的临时执行单元。
>
> 本文件是控制面的**装载规则**，不是新的台账。真源仍然是 Git / GitHub / Issue /
> PR / 正式 Evidence；这里只定义三个可执行原语：**Task Envelope → Admission →
> Development Gate**，以及配套的 **Escalation 协议**。

## 状态阶梯

```text
Task (Issue)
  ↓ 1. Envelope 绑定（base / deps / paths）
ADMIT                       ← python -m tools.admit --envelope tasks/GH-N.yaml
  ↓ 2. 执行（只在 allowed paths 内写）
Development Gate            ← python -m tools.dev_gate --envelope tasks/GH-N.yaml
  ↓ 3. Receipt（开发验证回执，不是 Evidence）
PENDING_HUMAN_REVIEW
  ↓ 4. 人工 Review + Merge（唯一的 promotion）
AUTHORITATIVE STATE
```

## 1. Task Envelope（≈ CRD 的 spec）

实例放 `tasks/GH-<N>.yaml`（GitHub Issue 是它的人类可读视图），模板在
`docs/ENVELOPE_EXAMPLE.yaml`。机器字段只有五个：

```yaml
task: GH-11
base:
  branch: master
  sha: abc123            # 任务批准时的 commit；漂移 = BLOCKED
dependencies:
  - ref: GH-9
    required_state: merged   # merged | closed | open
allowed_paths:
  - src/**
forbidden_paths:
  - gates/**
exceptions:
  allow_dirty:
    granted_by: Yenefa
    decision_ref: GH-20#comment-1
```

- **base.sha 解决 C 类失败（State Coordination）**：Agent 不是"从 master 开"，
  而是"在 master@abc123 批准的任务上开"。master 前进且中间改了 contract →
  drift → BLOCKED → escalation，而不是悄悄继续。
- **allowed_paths 是白名单**：未声明可写 = FOREIGN（默认只读，AGENTS.md §2.2）。
- 其余字段（goal / scope / acceptance / budget / escalation）是自由文本，工具不解释。

## 2. Admission（开工前，fail-closed）

```bash
python -m tools.admit --envelope tasks/GH-N.yaml
```

检查：repo 是否 dirty / envelope 是否存在且可解析 / 分支是否匹配 / base.sha 是否
漂移（`git cat-file` 验证存在性）/ 依赖状态（`gh` 查询，例如 GH-9 未 merge →
BLOCKED）。

输出 `ADMIT`（exit 0）或 `BLOCKED`（exit 1）+ reasons。BLOCKED 不是拒绝，是
**escalation 入口**：

```text
STOP → Explain → Escalate → Human Decision → Record → Resume / Reject
```

三个 flag 本身只是 bypass request——必须由 envelope 的 `exceptions` 预授权（§4），
否则 BLOCKED（cannot self-authorize）；授权后记录进回执 `exceptions_used`：

```bash
--allow-dirty   # 容忍脏工作区
--allow-drift   # 容忍 baseline 漂移
--skip-deps     # 跳过依赖核验（gh 不可用/豁免）
```

## 3. Development Gate（完成前，单一入口）

```bash
python -m tools.dev_gate [--envelope tasks/GH-N.yaml] [--receipt PATH]
```

本地 Agent、Yenefa/Percy、GitHub CI 调用**同一个入口**（CI 见
`.github/workflows/ci.yml`）。检查：

```text
syntax         compileall gates tools tests sandbox_runtime
main_tests     主仓库单测（3.9 解释器，与 CI 一致）
sandbox_tests  sandbox_runtime 单测（uv；uv 缺失时显式 excluded）
secret_scan    高置信 secret 模式（原 CI job 同款）
scope_check    工作区 diff vs envelope 的 allowed/forbidden（有 envelope 时）
```

GH-20 后无平台排除：同一命令，一种 PASS 语义，排除项可见（`excluded_checks`）。

**binding_check（TOCTOU 绑定）**：gate 带 `--admit-receipt <admission receipt>` 时，
校验当前 envelope 的 sha256 == admission 时记录的 `envelope_sha256`。不一致则
FAIL → task/control state changed after admission → re-admit。admission 与 execution
之间的控制面状态必须逐字节一致（Time Of Check == Time Of Use）。gate receipt 同样
记录 `envelope_sha256` 供审计。

退出码：`0` PASS / `1` FAIL / `2` GATE_BROKEN（门禁自身坏了，不是候选的错）。

### Receipt（开发验证回执）

```json
{
  "schema_version": "dev-gate.v1",
  "gate_version": "1",
  "status": "PASS",
  "exit_code": 0,
  "baseline_sha": "18b2381",
  "envelope_sha256": "e3b0c442…",
  "branch": "feat/...",
  "dirty": false,
  "checks": {
    "syntax": {"status": "pass"},
    "main_tests": {"status": "pass", "detail": "Ran 269 tests OK"},
    "sandbox_tests": {"status": "pass"},
    "secret_scan": {"status": "pass"},
    "scope_check": {"status": "pass"}
  },
  "excluded_checks": [
    {"id": "sandbox_tests", "reason": "uv unavailable on this host"}
  ]
}
```

**Receipt ≠ Evidence**：它是 candidate change 的开发验证回执；正式 Evidence 由
`gates/run_gates.py`（Evidence Gate）产出，位于 `notes/*/generated` 与
`docs/evidence`。Receipt 不晋升任何东西——promotion 永远是人工 merge。

## 4. Authority 三级模型 + Exception 预授权

三个概念必须分开（Gemini PolicyIntegrityManager 反证）：

```text
Policy    什么情况下应该允许？
Authority 谁有资格改变这个决定？
Integrity 我怎么知道 Policy/Authority 在检查后没有偷偷变？
```

`hash(policy)` ≠ `trusted(policy)`：policy 与 policy_integrity.json 在同一可写
trust domain，等于"攻击者改完文件 A 顺手更新文件 B"。**Hash 证明一致性，不证明权威性。**

**L1 — Declared Authority**（当前实现）：envelope 字段存在性检查。文档中准确称
declared，不得写成 verified/cryptographic。

**L2 — Promotion-bound Authority**（下一步）：授权必须存在于**已 Human Promotion
的 Git 状态**。关键不是 Git 本身，而是：**授权与普通 Agent candidate 不在同一个
promotion level**——`master` 上的 exceptions 有 authority，`feat/*` 上 Agent
自己写的 `granted_by` 只是合法 YAML，不是授权。判断标准是
`Does authorization originate from a promoted control-plane state?`，而不是
`Does this YAML contain granted_by?`。

**L3 — Externally Verified Authority**（未来，现在不做）：GitHub identity /
signature / 外部审批验证（comment 存在、author 匹配、内容授权、task 匹配）。

规则：**Agent 不能给自己授权；authority 必须存在 BEFORE exception 被消费。**

Run 001（GH-20）是唯一例外：授权是事后 reconcile 的
（**historically reconciled authorization**），不构成机制成功案例——它发现的
正是 authority gap 本身。从 Run 002 起严格执行 authority-before-consumption。

**Gemini 实证对照（2026-09-01 源码深潜，`notes/open_source_intake/gemini-cli-policy-deepdive-2026-09-01.md` 「Authority Provenance」节）**：

- Gemini 的 PolicyIntegrityManager ≈ **L2 的失败原型**：pin 与策略同信任域
  （`~/.gemini/policy_integrity.json`）、headless 策略变更 **warn + auto-accept
  （fail-open）**、且已被 `disableWorkspacePolicies` flag 整体禁用（#18186 根因）。
  结论：**L2 的锚必须是 human-promoted 的 git 状态，不是再造一个可写的 pin 文件**。
- 拒绝采纳：自管 pin（无独立信任根）、headless auto-accept、无 provenance 的批准落盘
  （Gemini 的 auto-saved.toml 规则无时间戳/用户/session）。
- 复用面：Gemini 批准按命令前缀复用（同前缀任意参数命中）；AEDL exception 是
  envelope 域（任务域），binding_check 已防跨任务复用；同任务内参数级重验留给
  Trigger（第一次出现同任务参数变更导致越权时）。
- Gemini 检查与执行之间**无二次校验**；AEDL 的 gate binding_check 就是那层二次校验。

`--allow-dirty / --allow-drift / --skip-deps` 只是 bypass with audit，不是 escalation。
真正的 escalation 至少是：BLOCKED → exception requested → authority granted → resume。
异步场景用**预授权 exception**（envelope 里声明），而不是强同步 ASK：

```yaml
exceptions:
  allow_dirty:
    permitted: true          # 预授权：envelope 本身是 authority
    reason: existing unaccepted work-in-progress
    authority: task-envelope
  allow_drift:
    granted_by: Yenefa       # 事后批准：人授权后补录 decision_ref
    decision_ref: GH-20#comment-1
```

- flag 无 envelope 例外 → admit BLOCKED（`cannot self-authorize`），不是放行。
- 例外记录进回执（`exceptions_used`），随 receipt 留痕。
- 等价设计分叉（Gemini CLI 对照）：pre-approval（agent 停下问人，人答了才继续）vs
  post-recorded（先做、flag 留痕、人 review）。AECP 采用预授权 + 事后补录的混合，
  不引入强同步 ASK；若未来出现"必须等人在场"的硬场景，再考虑 ASK-with-timeout→auto-DENY。

## 5. Hash Domain（哈希域）——每个 SHA256 必须声明绑定哪个 byte domain

GH-20 碰撞证明：同样的"sha256"字段可能绑定四种不同字节域，LF/CRLF 只是表象：

```text
git_blob                Git 仓库规范化字节（LF）
working_tree            检出后的工作树字节（可能 CRLF）
archive_entry           ZIP/打包产物条目字节
generated_bytes         生成器输出字节（可能与以上都不同）
```

当前 AEDL 绑定域图（2026-09-01，GH-20 后）：

| 绑定 | domain | 说明 |
|---|---|---|
| manifest sources.board/intent/bom/bom_stock + artifacts.bom/cpl | `git_blob` | 声明 = blob 哈希；工作树经 eol=lf 属性与 blob 一致 |
| manifest artifacts.gerbers + gerber_zip entries | `working_tree == archive_entry` | 文件与 ZIP 条目必须逐字节一致（CRLF）；blob 反而是 LF |
| fault-injection proof / FROZEN_PROTOCOL / golden algorithm_revision | `git_blob` | LF 声明 |
| bom_stock_current.json.bom_sha256 | `git_blob` | 声明 = blob 哈希 |

Review 四个事实（push 前必查）：

```bash
git check-attr text eol -- delivery/gerbers/m2_board-F_Cu.gtl   # 属性契约
git cat-file blob HEAD:delivery/gerbers/m2_board-F_Cu.gtl | sha256sum   # blob 域
sha256sum delivery/gerbers/m2_board-F_Cu.gtl                    # 工作树域
# ZIP 条目域：python -c "import zipfile,hashlib;print(hashlib.sha256(zipfile.ZipFile('delivery/jlc_gerber_upload.zip').read('m2_board-F_Cu.gtl')).hexdigest())"
```

设计规则：git_blob(LF) ≠ working_tree(CRLF) == archive_entry(CRLF) 的差异必须是
**有意不同**（eol=crlf 契约 + manifest 绑定 working_tree==archive_entry），不是误以为相同。
manifest schema 目前不扩展 `hash_domain` 字段（避免破坏 validate_delivery_manifest
的精确字段集校验）；Trigger：出现新绑定类型或 packaging 路径变化时，先加字段再扩展校验。

## 6. Escalation（BLOCKED 记录模板）

```text
BLOCKED
Task: <GH-N>
Reason: <admission / gate / 边界输出>
Observed need: <任务实际需要的授权或变更>
Requested: <expand scope / change baseline / waive check>
Owner decision: PENDING / APPROVED / REJECTED
Decision ref: <issue/PR comment 链接>
```

记录留在 Issue/PR 线程里（GitHub 是 event store，不再造第二个数据库）。
决策本身进入复利阶梯：重复出现 → 变成规则 → 变成 hook。

## 7. 碰撞记录（Run Log）

### Run 001 状态（2026-09-01）

```text
Run 001 execution: COMPLETED
Verification:       PASS（单测 20/20；LF 工作树 282/282；gate PASS exit 0，binding 绑定）
Human review:       PENDING
Promotion:          PENDING
Promotion 序列:     Yenefa/Percy Review → SHARED 确认（ci.yml/gates/contracts/manifest）
                    → commit → push → CI 双平台矩阵实际运行 → PR → human merge
```

AECP 自身遵守：Agent may propose, but not promote——控制面代码自己不例外。

### Run 001 评审与迭代账本（2026-09-01）

| 轮次 | 载体 | 结论 |
|---|---|---|
| R1 | bundle Review（run001-review.md） | REQUEST_CHANGES：CI 双跑 sandbox / EVID 过早 YES / ADR 陈旧 / 称谓修正 |
| R2 | 源码 Review（run001-review-new-files.md 全内容） | REQUEST_CHANGES：5 个 hard blockers（git rc / BLOCKED binding / 空 allowed fail-open / HEAD 绑定 / broken 聚合）+ parser provenance + skip_deps 语义 |
| R3 | delta Review（run001-review-delta.md） | 源码 APPROVE + 2 个文本 truth（机器字段五、CI 注释 task-context 语义） |
| R4 | 真实 hunks（run001-source-diff.patch） | SOURCE REVIEW APPROVE → ⑥ commit 授权（CONDITIONAL） |
| R5 | PR #21 + bundle（promotion） | CI 双平台全绿 → EVID YES → ⑪ Yenefa merge（master @ 084fb92） |

统计：**评审 5 轮 / CI 矩阵迭代 3 次**（1st venv 遮蔽+cp1252 → 2nd 8.3 短名路径 → 3rd 全绿）/
**自我拦截 1 次**（BLOCKED receipt 不能绑定，admit-v3-drift-blocked 实证）/
**技术债 2 项被机器暴露**（CRLF 哈希缺口、路径解析层级不一致）。

### 设计冻结（Freeze，直到 Run 002）

```text
FREEZE（不新增）: 新 Policy 类型 / 新 Authority tier 实现 / 新 Router / 新 Hook /
                 新 Projection / 新 Memory 系统
FIX（继续允许）:  admit bug / gate bug / receipt bug / binding correctness /
                 blocker / security flaw
```

Trigger backlog（知道怎么做 ≠ 现在值得做，等生产故障证明维护成本值得）：
L2 Promotion-bound Authority 实现 / hash_domain schema / dirty 归因 snapshot /
参数级重验 / policy tiers / authorization schema（task identity + exception type +
scope + base/control-plane version + validity）。

```text
Run 001 — GH-20（dirty workspace / soft override）
  真实 CI 技术债 → envelope → admission BLOCK（dirty 16）→ --allow-dirty → 修复 → gate PASS
  发现 1: exception authority 模糊（agent 自授权风险）→ Exception contract（L1 declared）
  发现 2: hash 绑定 byte domain 模糊 → Hash Domain（§5）
  发现 3: authority provenance / TOCTOU → 下一代需求（§4 L2/L3 + binding_check）
  授权定性: historically reconciled（authority 在消费之后补录；机制成功案例从 Run 002 起算）

Run 002 — 待选: scope violation / dependency drift / contract escalation（SS34/AP63203）
  原则: 优先天然 collision（operational validation）；synthetic fault injection
  （单测 + admit BLOCKED 演示）只证明机制（mechanism validation），两者分开计数。
```

演化链（第一代）：真实 CI 技术债 → Task Envelope → Admission BLOCK → 发现 exception
authority 模糊 → Exception contract → 发现 hash representation 模糊 → Hash Domain
→ 又暴露 authority provenance / TOCTOU → 下一代控制面需求。

## 8. Review Bundle（AECP 特色：外部 AI Review 载体）

> 定位：**Agent 交付时必备的流程产物**（硬性）——把候选变更集的全部审查面（状态、SHARED 项、
> 风险、验证证据、diff、新文件全内容）压缩成**一份可整体发送的 Markdown**，让
> 外部审查者（尤其是对话式 AI）可以在不看仓库、不跑命令的前提下完成独立复核。

### 存放与命名

```text
本地独立文件夹（仓库外，绝不进候选变更集）：
  review-bundles/
    run-001/
      run001-review.md             # 主 bundle：状态 + SHARED 项 + 风险 + 验证证据 + tracked diff
      run001-review-new-files.md   # 新文件全内容（源码 Review 用）
      run001-source-diff.patch     # 源码 Review 整改的真实 hunks（基线=review 时快照）
      run001-review-delta.md       # 整改摘要（delta 仅辅助；真实补丁以 .patch 为准）
      <admit/gate receipts>.json   # 配套 receipt，随 bundle 归档
```

### 使用方法（写给 AI 审查者与人工审查者）

1. **生成**：候选变更集形成后，从工作树拼装（git status / git diff / 新文件列表 +
   已运行验证证据）。Delta 复审一律用**真实 hunks**（.patch），不用摘要冒充补丁。
2. **发送**：整包（或按需单文件）手动发送给对话式 AI 进行外部 Review——
   **选用高质量 AI 模型，思考强度调高**（例如 GPT 5.6 Sol，思考强度：高）。
3. **Review 重点**（给 AI 的指令骨架）：
   - 安全边界：任何 fail-open / fail-closed 语义是否成立（含 error 路径、空白名单、git rc）；
   - 状态真实性：desired state 不得冒充 observed state（如 CI 未跑不能写 YES）；
   - SHARED 双人确认项逐条过；provenance / TOCTOU 是否被绕开；
   - 只审 bundle 内的东西，结论格式：blocker / 必修 / 通过 + 逐条证据。
4. **地位（硬性）**：bundle 是**流程产物，不是可选项**——**任何需要人工 Review 的
   Agent 交付，交付时都必须附带 bundle；无 bundle 不进入人工 Review。**
   其余硬性项不变：SHARED 双人确认、commit/push 授权、CI 实际运行、PR、human merge。

### 铁律

- bundle 是人工 Review 的前置交付物：Agent 交付时生成，缺失 = 交付不完整。
- bundle 永远放仓库外（review-bundles/）；AI 审查结论只是 candidate judgment，
  不能冒充人工批准。
- 补丁类产物（.patch）必须可回溯到当时被 review 的快照（基线留存）。

## 五句话

> **Agent may propose, but not promote.**  
> **Rules may guide, but gates enforce.**  
> **Memory may suggest, but provenance decides.**  
> **Exceptions may escalate, but never silently bypass.**  
> **项目不是目录；但控制面住在 repo 里，因此连控制面的修改本身也必须走 candidate → review → promotion。**
