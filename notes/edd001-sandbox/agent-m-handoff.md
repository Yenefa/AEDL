# EDD-001 Sandbox Runtime — Agent M 交接

**Status: PENDING_HUMAN_REVIEW**（Wave 1 M1–M4 策略内核 + Wave 3 策略层四项修复（NaN 边界、空目录证据、自声明权限移除、Trust manifest 绑定）与反例回归全部完成，协议 V2 钉值已重钉；未 commit / 未 push，详见 §10）

- 日期：2026-09-01
- Agent：M（中难度确定性策略块负责人）
- 任务包：EDD001-Agent-M-Policy.md（M1–M4）
- 设计依据：`docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md`（已完整读取，无冲突）
- 前置条件：`notes/edd001-sandbox/agent-h-handoff.md` 报告 `INTERFACE_READY`，已核对

---

## 1. 冻结协议校验（开工第一步，已完成）

- 文件：`sandbox_runtime/src/aedl_sandbox/protocol.py`
- **实测 SHA-256：`f053aae27a1672ba19fd1311799590fa1f2be4e166c09eaed80f7117d6e52f53`**
- 三种独立工具交叉验证一致：`openssl dgst -sha256`、`sha256sum`、`certutil -hashfile`
- 与 H 交接文件 §1 记录值**完全一致** → 判定为无漂移，按任务包继续执行 M1–M4
- 收尾时（Agent L 已并行落地后）再次重算，仍为同一哈希，**未发生漂移**
- `protocol.py` 全程未被读取修改，未被 M 改动

> 若哈希不一致应按 `STATE_PROTOCOL_DRIFT` 停止并报告。本次**未触发**该分支。

---

## 2. 我改动的文件（全部在 M 专属所有权内）

新增（无删改任何既有文件）：

```
sandbox_runtime/src/aedl_sandbox/policy/__init__.py
sandbox_runtime/src/aedl_sandbox/policy/engine.py
sandbox_runtime/src/aedl_sandbox/policy/document.py
sandbox_runtime/src/aedl_sandbox/policy/edd001.py
sandbox_runtime/src/aedl_sandbox/policy/schema.py
sandbox_runtime/src/aedl_sandbox/policy/paths.py
sandbox_runtime/src/aedl_sandbox/policy/reasons.py
sandbox_runtime/src/aedl_sandbox/policy/errors.py
sandbox_runtime/contracts/domain_policy_schema_v1.json
sandbox_runtime/tests/policy/__init__.py
sandbox_runtime/tests/policy/fixtures.py
sandbox_runtime/tests/policy/test_document_validation.py
sandbox_runtime/tests/policy/test_design_policy.py
sandbox_runtime/tests/policy/test_execution_policy.py
sandbox_runtime/tests/policy/test_edd001_preflight.py
notes/edd001-sandbox/agent-m-handoff.md
```

未触碰：`protocol.py`、`pyproject.toml`、`uv.lock`、`sandbox_runtime/.venv`、`gates/**`、`tests/orchestrator/**`、Agent L 的 `aedl_sandbox/trust/**`、`tests/trust/**`、`contracts/bundle_manifest_schema_v1.json`、`contracts/evidence_event_schema_v1.json`。

工作区既有未提交改动（NOTICE、合规台账、u3 提案、datasheet_manifest、spike/、EDD 合同等）**全部原样保留**。未执行任何 `git add` / `commit` / `push` / `revert` / `reset` / `clean` / `checkout`。

---

## 3. 公共 API

```python
from aedl_sandbox.policy import SandboxPolicyEngine   # __init__ 唯一导出符号

SandboxPolicyEngine.for_edd001(repo_root: Path) -> SandboxPolicyEngine
SandboxPolicyEngine.from_document(document: Mapping[str, JsonValue], repo_root: Path) -> SandboxPolicyEngine
SandboxPolicyEngine.evaluate(request: PolicyRequest) -> PolicyDecision
SandboxPolicyEngine.preflight(run_id: str, candidate_root: Path) -> PolicyDecision
```

- 只读附加属性：`engine.document`（归一化 `PolicyDocument`）、`engine.repo_root`
- `from_document` / `for_edd001` 在文档不可信时**抛 `PolicyDocumentError`**（`ValueError` 子类），绝不产出可能返回 ALLOW 的引擎——这是“fail closed”的实现方式
- 仅使用 Python 标准库；无网络、无子进程、无 shell、无 EDA 写入、无文件修改

### 3.1 支持的动作词汇与必需 subject 字段

| 动作 | subject 字段 |
|---|---|
| `PREFLIGHT` | `{}` |
| `DESIGN_SELECT_COMPONENT` | `mpn`, `role`, `evidence_ids` |
| `DESIGN_ASSIGN_PIN` | `pin`, `function`, `approval_status` |
| `DESIGN_SET_PARAMETER` | `parameter_id`, `value`, `unit`, `evidence_ids` |
| `COMPILE_HIR` | `compiler_id`, `compiler_version`, `output_kind`, `coverage_ids` |
| `VERIFY_ARTIFACT` | `verifier_id`, `verifier_version`, `artifact_kind`, `coverage_ids` |
| `TOOL_EXECUTE` | `tool_id`, `tool_version`, `capability` |
| `FILE_WRITE` | `path`, `artifact_kind`, `writer` ∈ {`agent`,`compiler`} |
| `NETWORK_ACCESS` | `destination`, `purpose` |
| `SHELL_EXECUTE` | `command_class` |

subject 字段集合必须精确相等；多字段、缺字段、类型错误（含用 `bool` 冒充 `number`）一律 `DENY / POLICY_SUBJECT_MALFORMED`，非异常、非放行。

### 3.2 精确 reason code 全集

**ALLOW**
- `POLICY_ALLOWED`

**闭世界 / 未声明（DENY）**
- `POLICY_ACTION_NOT_ALLOWED`、`POLICY_DOMAIN_NOT_ALLOWED`、`POLICY_SUBJECT_MALFORMED`
- `POLICY_COMPONENT_NOT_ALLOWED`、`POLICY_COMPONENT_ROLE_NOT_ALLOWED`
- `POLICY_PIN_NOT_ALLOWED`、`POLICY_PARAMETER_NOT_ALLOWED`

**已知违规（DENY）**
- `POLICY_PIN_HARD_FORBIDDEN`、`POLICY_PIN_CORE_RESERVED`
- `POLICY_PARAMETER_OUT_OF_BOUNDS`、`POLICY_PARAMETER_UNIT_MISMATCH`、`POLICY_PARAMETER_TYPE_INVALID`
- `POLICY_NETWORK_DISABLED`、`POLICY_ARBITRARY_SHELL_DISABLED`
- `POLICY_TOOL_NOT_ALLOWED`、`POLICY_VERIFIER_NOT_ALLOWED`
- `POLICY_PATH_ESCAPE`、`POLICY_DIRECT_KICAD_WRITE`、`POLICY_ARTIFACT_KIND_NOT_ALLOWED`

**已知但未证成（BLOCKED）**
- `POLICY_COMPILER_NOT_REGISTERED`、`POLICY_VERIFIER_COVERAGE_MISSING`
- `POLICY_COMPONENT_RESOLUTION_REQUIRED`
- `EVIDENCE_COMPONENT_SOURCE_MISSING`、`EVIDENCE_PARAMETER_SOURCE_MISSING`
- `EVIDENCE_REQUIRED_CONTRACT_MISSING`、`EVIDENCE_REQUIRED_EVIDENCE_MISSING`
- `APPROVAL_PIN_OVERRIDE_REQUIRED`

全部 code 均落在 `protocol.REASON_CODE_PREFIXES` 命名空间内；测试对每个 decision 断言前缀合法。findings 恒定按 `(code, source, message)` 排序。

### 3.3 判定优先级

1. 已知违规 → `DENY`（即使同时存在缺失前置条件）
2. 否则任何未证成前置条件 → `BLOCKED`
3. 全部满足 → `ALLOW`

`FILE_WRITE` 内部次序（已测试锁定）：subject 形状 → artifact_kind → **PATH_ESCAPE** → DIRECT_KICAD_WRITE → 编译器/前置条件。

---

## 4. 实际运行的测试与真实结果

环境：`uv run --frozen --project sandbox_runtime`，Python 3.11.15（H 的托管 venv，未 `uv sync`、未改 `pyproject.toml` / `uv.lock`）。

### 4.1 最终全量（权威结果）

**M 的 policy 子集（我的交付面，稳定复现）：**

```
uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/policy -t . -p "test_*.py"
→ Ran 133 tests — OK（退出码 0）
```

**全仓库沙箱套件（含 H/L 并行产物，快照）：**

```
uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests -p "test_*.py"
→ Ran 201 tests — FAILED (failures=1)
```

唯一失败项为 **H 自己的 Wave 1 进行中代码**，与 M 无关：

```
FAIL: test_rejects_symlink_escape_and_writes_nothing_outside
      (orchestrator.test_workspace.CandidateWorkspaceTests)
AssertionError: WorkspaceEscapeError not raised
```

成因是 Windows 创建符号链接需要管理员权限 / 开发者模式，链接未真正建立，因此逃逸未被触发。这与本交接 §6 记录的限制同源（我同样未能在 Windows 上运行时验证符号链接逃逸）。**该文件属 H 所有权，M 未修改、未规避。**

> **重要：套件结果会随并发 Agent 落地而变动。** 执行期间 Agent H 已推进 Wave 1（新增 `tests/orchestrator/test_orchestrator.py`、`test_workspace.py` 及编排/工作区实现），Agent L 亦已落地 trust 包。我观测到的快照依次为 172（全绿）→ 196 → 201，失败项始终只出现在 H/L 的模块中，**M 的 133 项全程保持全绿**。请以“policy 子集 133 OK”作为 M 的交付判据。

### 4.2 测试优先（RED/GREEN）实际记录

| 阶段 | 动作 | 真实结果 |
|---|---|---|
| 1 | 新增 malformed 文档 + 闭世界 component/pin 测试 | **RED**：`ModuleNotFoundError: No module named 'aedl_sandbox.policy'`（2 模块导入失败） |
| 2 | 实现 schema + 归一化 + 校验 | 先 RED 58/59（暴露两处真实缺陷：`$defs` 未纳入关键字白名单；`schema_version=1.0` 被 `const` 放行）→ 修复后 **GREEN 59/59** |
| 3 | 新增执行域测试 | **RED 已实证**：在内存中摘除 6 个执行动作处理器后重跑 → `tests=37 failures=0 errors=32`（未改动任何文件） |
| 4 | 实现执行域判定 | 先 RED 2 项，均为**真实缺陷**（见 4.3）→ 修复后 **GREEN 98/98** |
| 5 | 新增真实 EDD 预检 + 取代关系测试 | **RED**：`ModuleNotFoundError: ...policy.edd001`（35 项中 34 项 error） |
| 6 | 实现 `for_edd001` + `preflight` | 先 RED 5 项（2 项代码缺陷、3 项我的测试假设错误）→ 修复后 **GREEN 133/133** |

### 4.3 测试捕获并修复的真实缺陷（非测试笔误）

1. **空白路径逃逸（安全缺陷）**：`FILE_WRITE` 的 path 为 `"   "` 时，`Path.resolve()` 会归一化回 candidate_root 本身，导致判定为 ALLOW。修复：文件写入改用 `resolve_within(..., strict=True)`，目标解析到根目录本身即拒绝。已加回归测试。
2. **预检编译器/验证器分支互斥**：原实现用 `if/elif`，编译器为空时不再报验证器缺口，导致真实预检漏报 `POLICY_VERIFIER_COVERAGE_MISSING`。修复：改为两个独立 `if`。
3. `$defs` 未列入 JSON Schema 关键字白名单；`schema_version` 缺 `type: integer`（`1.0` 会被 `const: 1` 放行）。均已修。

另有 2 项是我的测试断言写错（`a/b/c/../../../escape.net` 实际仍在根目录内；`EN_RESET_NETWORK` 被取代的是 pin 合同副本、CORE_BASE 版本本就应保留），已更正测试而非放宽实现。

---

## 5. 真实 EDD-001 preflight 结果

```
engine = SandboxPolicyEngine.for_edd001(repo_root)
engine.preflight("run-agent-m-real", repo_root/"sandbox_runtime"/".runs"/"agent-m-preflight")
```

- **Outcome：`BLOCKED`**
- **Primary reason：`EVIDENCE_COMPONENT_SOURCE_MISSING`**
- **7 条 findings**（已排序）：

| # | code | source | message | details |
|---|---|---|---|---|
| 1 | `EVIDENCE_COMPONENT_SOURCE_MISSING` | evidence_store | component ESP32-S3-WROOM-1-N8R8 has no local datasheet evidence | missing: S3_DATASHEET, WROOM1_DATASHEET |
| 2 | `EVIDENCE_COMPONENT_SOURCE_MISSING` | evidence_store | component SS34 has no local datasheet evidence | missing: ESPRESSIF_S3_LCD_EV_BOARD |
| 3 | `EVIDENCE_COMPONENT_SOURCE_MISSING` | evidence_store | component TYPE-C-31-M-12 has no local datasheet evidence | missing: LCSC_C165948 |
| 4 | `EVIDENCE_COMPONENT_SOURCE_MISSING` | evidence_store | component USBLC6-2SC6 has no local datasheet evidence | missing: ST_USBLC6_2 |
| 5 | `EVIDENCE_REQUIRED_CONTRACT_MISSING` | contract_bundle | required contract EDD-001.POWER is not present | contract_id: EDD-001.POWER |
| 6 | `POLICY_COMPILER_NOT_REGISTERED` | tool_registry | no deterministic compiler is registered | — |
| 7 | `POLICY_VERIFIER_COVERAGE_MISSING` | tool_registry | no independent verifier is registered | — |

任务包要求的 4 类 code **全部出现**。

事实依据（均已在仓库内核验，非模型推断）：

- `gates/contracts/` 下只有 `edd001_core_base_contract_v1.json`、`edd001_pin_constraints_v1.json`、`edd001_usb_contract_v1.json`、`m2_schematic_contract_v1.json`——**无 POWER 合同**
- `src/hardware/edd001-board/evidence/datasheets/` **存在但为空（0 个条目）**，无 `datasheet_manifest.json`
- 三份合同的 `sources` 全为 URL，**从不计入本地已验证证据**
- 归一化后的 4 个允许器件：`ESP32-S3-WROOM-1-N8R8`、`SS34`、`TYPE-C-31-M-12`、`USBLC6-2SC6`

### 5.1 取代关系（superseded_by）处理

从 pin 合同自身 `superseded_by.note` 的括号枚举中解析被取代规则集（非硬编码）：

- **被取代（8）**：`PIN_STRAP_GPIO0/3/45/46`、`EN_RESET_NETWORK`、`BOOT_BUTTON_GPIO0`、`POWER_3V3_DECOUPLING`、`ANTENNA_KEEPOUT`
- **仍有效（2）**：`USB_DIFFERENTIAL`、`POWER_SOURCE_SEPARATION`
- 活跃规则总数 **19** = CORE_BASE 8 + USB 9 + pin 合同仍有效 2

取代是**承重的**而非装饰：`EN_RESET_NETWORK` 在两份合同中同名但载荷不同，若忽略取代即触发重复冲突并 fail closed。已用 `honor_supersession=False` 显式证明该路径（`PolicyDocumentError`）。

### 5.2 引脚域归一化结果

- hard_forbidden：`GPIO35/36/37`
- core_reserved：`GPIO0/3/19/20/45/46`
- soft_reserved：`GPIO43/44`
- agent_gpio_pool：25 个，逐项等于 CORE_BASE `pin_policy.agent_gpio_pool`
- `GPIO26`–`GPIO34` 未被推断为可用（不在 pool 内即 `POLICY_PIN_NOT_ALLOWED`）
- 各类互斥，无重叠

---

## 6. 未运行的命令 / 未做的事

- **未运行** `gates/run_gates.py`（任务包明令禁止）
- **未运行** 任何 `git add` / `commit` / `push`
- **未运行** `uv sync`；未改 `pyproject.toml` / `uv.lock` / 共享环境（H 负责依赖）
- **未运行** 端到端编排集成（属 H 的 Wave 2 `adapters.py`）
- **未运行** 真实 KiCad/ERC/DRC/仿真（V1 非目标，且执行沙箱禁止）
- **未运行** 符号链接逃逸的运行时验证（Windows 创建符号链接需特权；`Path.resolve()` 会跟随符号链接，理论上可捕获，但未实测）
- 未更新任何合规台账（本任务包未授予 `docs/compliance/AI_USAGE_LOG.md` 等写权限，留痕由人工在批次收尾统一裁决——与 H 的处理一致）

---

## 7. 已知限制

1. **`domain_policy_schema_v1.json` 由自研的 JSON Schema 子集求值器执行**（`policy/schema.py`）。因限制“策略代码仅用标准库”，无法引入 `jsonschema`。支持关键字有限；**遇到不支持的关键字会抛 `PolicySchemaError` 而非静默忽略**——这是有意的 fail-closed 设计。若日后需要更复杂的 schema 语义，需扩展该求值器。
2. **参数表为人工转录**：`_PARAMETER_TABLE`（8 项）逐条注明来源合同规则（CORE_BASE 去耦/复位/启动、USB CC 下拉/串联电阻、USB 差分阻抗 90Ω±10% → 81–99）。新增合同参数需同步该表，否则未知参数一律 `DENY`。
3. **本地证据 ID 词汇不一致**：证据发现取自 `evidence/datasheets/` 的直接子项名（沿用 m2 的 `U1_ESP32-C3-WROOM-02` 式命名），而合同 `sources` 用的是 `WROOM1_DATASHEET` 式键名。当前该目录为空，故真实预检结论不受影响；一旦开始摄入 EDD-001 数据手册，**必须先定义证据清单映射**，否则证据永远无法被识别为已满足。
4. **`required_component_resolutions` 恒为空**：仓库中尚无 HIR / 设计态产物可供推导。`POLICY_COMPONENT_RESOLUTION_REQUIRED` 路径仅在合成 TEST_ONLY 文档中验证过；HIR 产物落地后需接线。
5. **file_policy 的 artifact 种类为 M 定义**：无任何合同声明产物种类，`allowed_artifact_kinds`（hir/netlist/bom/report/kicad_sch/kicad_pcb）与 `agent_forbidden_artifact_kinds`（kicad_sch/kicad_pcb）需人工确认。
6. **未注册任何 tool / compiler / verifier**：真实 bundle 三个注册表均为空，这是导致预检 BLOCKED 的原因之一，属如实反映现状，非实现缺口。
7. **`REJECTED` 批准状态按 BLOCKED 处理**：软保留引脚在 `approval_status` 非 `APPROVED`（含 `REJECTED`）时统一 `BLOCKED / APPROVAL_PIN_OVERRIDE_REQUIRED`，未引入新的 DENY code。若人工要求 `REJECTED` 判 DENY，需新增 reason code。
8. **无 OS/容器级隔离主张**：本层仅做策略判定；“离线”“禁 shell”由不暴露能力 + 拒绝请求实现，不构成对抗恶意进程的系统级隔离（与规格 §3.2 / §9 一致）。
9. **未做并发/线程安全加固**：`PolicyDocument` 为冻结 dataclass + frozenset/tuple，只读共享是安全的，但未针对高并发调用做专门验证。

---

## 8. Git 状态

- **Branch**：`fix/m2-schematic-semantic-release`（与开工时一致，未新建/切换分支）
- **HEAD**：`f169018037ae5c72c47b20d8502f5aa4e37bda7b`（`f169018 docs(log): spike standalone-repo packaging entry AI-20260831-028`）
- **Commit 状态**：**未提交**（本次全部改动均为未跟踪新文件，无 staged 内容）
- **Push 状态**：**未推送**
- **PR**：未创建
- 开工前既有改动（NOTICE、AI_USAGE_LOG、DECISIONS、THIRD_PARTY_RESOURCES、u3 提案、datasheet_manifest、plans/specs、三份 EDD 合同等）保持原状，未被 M 触碰
- 未创建 `sandbox_runtime/.runs/`（预检使用未实际创建的下游路径）
- `git diff --cached` 中可见的 staged 内容（`docs/superpowers/plans/...`、`specs/...` 等 4 文件）为开工前即已 staged，**非 M 所为**（H 交接 §6 亦有同样记录）

---

## 9. 给人工 / 下游的提示

- **H（Wave 2 集成）**：`SandboxPolicyEngine.for_edd001(repo_root)` 已可用；真实 EDD-001 会稳定返回 `BLOCKED`。请让 orchestrator 在 `ALLOW` 之前先消费 `preflight`，并把 7 条 findings 原样带上，不要用合成数据制造假 PASS。
- **L**：本模块未读取也未依赖 `aedl_sandbox.trust`；并行落地未产生冲突（172 项全绿）。
- **待人工裁决**：第 7 节限制 2/3/5（参数表维护方式、证据 ID 词汇映射、artifact 种类定义）。

**本轮状态：停在 PENDING_HUMAN_REVIEW，未提交、未推送、未集成。**

---

## 10. Wave 3（策略层修复 + V2 适配）交付摘要（最新）

人工审核对本 M 领地判定 CHANGES_REQUIRED（3 项阻断 + 1 项 V2 适配）。本轮在 H 冻结协议 V2 之后开工：开工第一步重算 `protocol.py` SHA-256 = `f7d44732785d17a20283f3a18fde7689eebfee78f10a93ae899e1dd116383cad`（7101 字节），与 agent-h-handoff.md §-2.0 记录严格相等，无 `STATE_PROTOCOL_DRIFT`；收尾复核仍为零漂移（本轮从未触碰 protocol.py）。`FrozenProtocolTests` 钉值已按预期漂移重钉为上述 V2 值。

### 10.1 修复清单逐项结果

1. **NaN/非有限数绕过数值边界（原 engine.py:40）——已修复**
   - `_is_number` 增加 `math.isfinite` 校验：策略输入的任何数值字段（当前词表中即 `DESIGN_SET_PARAMETER.value`）为 NaN/±inf 时在 subject 校验层即拒绝，判 `DENY / POLICY_SUBJECT_MALFORMED`，不再可能静默放行成 ALLOW。
   - 防御纵深：`ParameterRecord.accepts`（document.py）对非有限浮点直接返回 False，`min/max` 边界路径（`81 <= NaN <= 99` 双 False 的经典绕过）与 `allowed_values` 路径均封死。
   - 无新增 reason code；NaN 属拒绝该参数，判 DENY（设计输入角色）。
2. **空目录不算本地证据（原 edd001.py:301）——已修复**
   - `discover_local_evidence_ids` 现要求：目录非空 **且** 递归含至少一个可读、`size > 0` 的文件；空目录、仅含空文件的目录、不可读条目一律按证据缺失处理（保持既有 `EVIDENCE_*` BLOCKED codes，不 ALLOW）。递归以 resolved 路径集防 symlink 环，OSError 一律 fail-closed 为缺失。
   - 原 `test_local_datasheets_are_discovered` / `test_bundle_stays_blocked_even_with_all_datasheets_present` 两处"空目录即证据"的旧断言已改为可验证证据（size>0 文件），并新增空目录反例用例。
3. **移除自声明权限——已修复（V2 消费）**
   - `DESIGN_ASSIGN_PIN.approval_status` 与 `FILE_WRITE.writer="compiler"` 的 subject 值不再具权威性（字段保留以维持 V1 subject 形状，仅作非权威声明）。
   - V2 授权来源：`PolicyRequest.actor`（ActorIdentity）+ `PolicyRequest.capability_grants`（orchestrator 台账签发的 CapabilityGrant）。授权判定要求 capability 串精确相等 **且** `grant.run_id == request.run_id` **且** `grant.actor_id == request.actor.actor_id` **且** `receipt_sha256` 非空；actor 缺失一律不授权。
   - capability 词汇：`writer=compiler` 直接采用协议 docstring 的示例串；软保留脚人工批准按同一 `key=value` 约定映射为 `approval_status=APPROVED`（协议未发明确词汇表，此映射为对被替换 subject 字段的机械镜像，**需 H 灌注侧采用同一词汇**，见 10.4）。
   - 结果码：无授权的 `writer=compiler` → `DENY / POLICY_CAPABILITY_NOT_GRANTED`（新增 code）；无授权的软保留脚覆盖（含自报 APPROVED）→ `BLOCKED / APPROVAL_PIN_OVERRIDE_REQUIRED`。三者（POLICY_/APPROVAL_ 前缀）均在冻结前缀表内。
4. **策略输入绑定 Trust manifest（原 adapters.py:116）——已修复（V2 消费）**
   - `build_real_edd001_policy_port` 现在的构建顺序：先 `FileTrustStore.validate_bundle`（L 权威判定）→ 状态 `INVALID`/`MISSING` → 返回 fail-closed 端口（所有请求 `BLOCKED / EVIDENCE_BUNDLE_INVALID`，携带 trust findings，**不读任何合同**）；`PARTIAL`（含真实 bundle 的 5 条 missing_requirements）→ 继续构建，缺失项由引擎文档自身的 prerequisite 判定照常 BLOCKED（findings 集保持 7 条不变，INT-01 兼容）。
   - 引擎侧新入口 `SandboxPolicyEngine.for_edd001(repo_root, manifest_path=…)`：每份被消费的合同必须被 manifest 钉定（`gates/contracts/<name>` 条目存在且 sha256 良构），且磁盘字节哈希必须等于钉定值，否则 `PolicyDocumentError`（adapter 捕获后同样转 fail-closed 端口）——关闭 validate 与构建之间的 TOCTOU 漂移。引擎记录 `sha256(manifest 字节)` 为其 verified-bundle 身份（新公共属性 `verified_bundle_sha256`）。
   - 请求绑定：`PolicyEnginePort`（真实端口）给每个流经请求注入 `verified_bundle_sha256/verified_manifest_path`（V2 协议字段）；引擎发现请求所引 bundle 身份与自身身份不一致 → `BLOCKED / EVIDENCE_BUNDLE_MISMATCH`（新增 code）。V1 调用方（不带该字段）保持 V1 中性行为。
   - 架构约束保持：adapters 仅 import M/L 公共 API——`policy/__init__` 公共导出扩展为 `SandboxPolicyEngine` + `load_contracts_bound_to_manifest` + `PolicyDocumentError`；`real_edd001_preflight` 与 CLI preflight 一并改走绑定端口。TEST_ONLY 合成端口不绑定 manifest（明确非证据，语义不变）。

### 10.2 反例回归结果（本轮实测，逐条 PASS）

| # | 审核反例 | 回归测试（实际运行） | 修复后结果 |
|---|---|---|---|
| 1 | bounds=[81,99] 时 value=NaN 得 ALLOW | test_design_policy.py::test_nan_value_is_never_allowed / test_infinite_values_are_never_allowed / test_parameter_record_refuses_non_finite_values_directly；test_edd001_preflight.py::Wave3CounterexampleTests::test_nan_against_real_bounds_is_denied_not_allowed（真实合同 USB_DIFF_IMPEDANCE_OHM，NaN/±inf 全 DENY，有限值 95.0 照常走证据 BLOCKED） | PASS（DENY/POLICY_SUBJECT_MALFORMED，0 ALLOW） |
| 2 | 空目录证据 ALLOW | test_edd001_preflight.py::test_empty_evidence_directory_is_not_local_evidence（空目录 + 仅空文件两种形态） | PASS（证据缺失，BLOCKED） |
| 3 | manifest INVALID 后策略仍 ALLOW | test_edd001_preflight.py::TrustBundleBindingTests::test_tampered_contract_fails_closed_blocked / test_missing_manifest_fails_closed_blocked / test_contract_drift_from_manifest_fails_engine_construction / test_real_port_preflight_matches_the_unbound_engine | PASS（BLOCKED/EVIDENCE_BUNDLE_INVALID，端口级 fail-closed，任何 action 均不得 ALLOW） |
| 4 | 自报 APPROVED 通过 | test_design_policy.py::test_self_declared_approval_is_not_authoritative / test_approval_grant_must_bind_run_actor_and_receipt / test_approval_grant_without_a_trusted_actor_is_ignored / test_orchestrator_approval_grant_allows_the_override；test_edd001_preflight.py::Wave3CounterexampleTests::test_self_declared_pin_approval_on_the_real_bundle_is_blocked（GPIO43/44 全形态 BLOCKED） | PASS（BLOCKED/APPROVAL_PIN_OVERRIDE_REQUIRED，仅 orchestrator grant 可解） |
| 5 | 自报 writer=compiler 越权 | test_execution_policy.py::FileWritePolicyTests::test_self_declared_compiler_writer_is_denied / test_compiler_writer_without_a_trusted_actor_is_denied / test_compiler_writer_grant_must_bind_run_actor_and_receipt / test_granted_compiler_may_write_kicad_artifacts；test_edd001_preflight.py::Wave3CounterexampleTests::test_self_declared_compiler_writer_on_the_real_bundle_is_denied | PASS（DENY/POLICY_CAPABILITY_NOT_GRANTED，仅 grant 可放行） |
| 6 | 请求引用错误 bundle 身份 | test_edd001_preflight.py::test_request_citing_a_different_bundle_is_blocked / test_request_citing_the_true_bundle_is_not_mismatched | PASS（BLOCKED/EVIDENCE_BUNDLE_MISMATCH；正确身份不误伤） |

### 10.3 实测结果（全部本轮真实运行，2026-09-01）

- policy 聚焦：`uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/policy -t . -p "test_*.py"` → **Ran 153 tests — OK，exit 0**（Wave 1/V2 轮的 133 例 + 本轮新增 20 例；原唯一 failure 即 V1 钉值漂移，已重钉消除）
- orchestrator 聚焦：**Ran 84 tests — OK，exit 0**（H 领地零改动、零破坏；INT-01～15 与 CLI 断言全部保持）
- trust 聚焦：**Ran 35 tests — OK (expected failures=1)**（skip/expectedFailure 均为 L 既有，本轮未触碰 trust/）
- 全量：`discover -s sandbox_runtime/tests -p "test_*.py"` → **Ran 272 tests — OK (expected failures=1)，exit 0**
- CLI 冒烟（真实进程）：`preflight --repo-root . --domain EDD-001` → **BLOCKED / EVIDENCE_COMPONENT_SOURCE_MISSING / 7 findings，exit 1**（与 H Wave 3 基线逐项一致，未制造假 PASS）；`run-fixture --scenario repair_then_pass` → 人工中断 exit 0，跨进程 `resume --scenario repair_then_pass --approved-by human_reviewer --decision APPROVED` → **TERMINAL / STATE_PROMOTED**，exit 0；冒烟目录 `sandbox_runtime/.runs/wave3-m-smoke` 用毕即删（.runs 为 gitignore）
- 收尾复核：protocol.py SHA-256 = `f7d447…3cad` 零漂移；全部改动限定在 M 领地（policy/*、adapters.py、tests/policy/*、本文件），未 stage/commit/push，未触碰 H（orchestrator/workspace/state/cli/protocol）与 L（trust/）及 NOTICE/M2/U3 等混杂改动

### 10.4 已知状态与限制（如实披露）

1. **capability 词汇表待 H 对齐**：协议仅示例 `writer=compiler`；软保留脚批准的 `approval_status=APPROVED` 为 M 侧对被替换 subject 字段的机械镜像。H 侧 orchestrator/adapters 灌注 grants 时必须采用同一字符串，否则灌注后语义不匹配（当前无灌注 → 全部 fail-closed，方向保守安全）。
2. **orchestrator 侧灌注仍缺（H 领地，非本轮可修）**：真实编排链路尚不向 `PolicyRequest` 灌注 `actor/capability_grants/verified_bundle_sha256`（H handoff §-2.4.3 同项），因此灌注前 `writer=compiler` 与软保留脚覆盖在真实链路一律 fail-closed；bundle 绑定由 `build_real_edd001_policy_port` 在端口层先行兑现。receipt 固化（`record()` 事件）亦属 H 的灌注职责。
3. **TEST_ONLY 引擎不参与 bundle 绑定**：`from_document`/TEST_ONLY 端口的 `verified_bundle_sha256` 为空 → 请求带该字段时不触发一致性检查（V1 中性）。TEST_ONLY 材料本就声明非证据，如需绑定走真实端口路径。
4. **`approval_status` subject 字段保留但失权**：为不破坏 V1 subject 形状（精确字段校验），字段仍在 spec 中但值不具权威性，findings 中以 `declared_approval_status` 留痕。人工如要求彻底删除该字段（旧 subject 将变 SUBJECT_MALFORMED），另行裁决。
5. **新增 3 个 reason code**：`POLICY_CAPABILITY_NOT_GRANTED`、`EVIDENCE_BUNDLE_INVALID`、`EVIDENCE_BUNDLE_MISMATCH`，均在冻结前缀表内，无协议改动。
6. Wave 1 已知限制（evidence-ID 词汇映射、参数表/artifact kinds 权威等）继续有效，见 §7。

### 10.5 Commands not run

`gates/run_gates.py`（禁令）；任何 `git add/commit/push`（禁令）；`uv sync`/依赖变更（Wave 0 已冻结）；protocol.py/orchestrator/workspace/state/cli/trust 的一切写操作（禁令，未发生）；真实 KiCad/ERC/DRC/SPICE/LLM 调用（非目标）。

**本轮状态：Wave 3 策略层四项修复 + 反例回归全部完成，PENDING_HUMAN_REVIEW。**
