## AI-20260917-DSH-525A0E8BBDFDEFA274AA1A6CA95F43EE

- 日期：2026-09-17
- 任务名称：PR-1 C4 pinned strict and constrained writer adapter
- 记录者：DSH
- 会话：DeepSeek Harness（DSH）主会话
- 参与：GENERATE_CODE、GENERATE_TEST、DOCUMENT
- AI 工具/平台：DeepSeek Harness（dsh web）
- 模型：`deepseek-v4.1-flash`
- 人工审核：`PENDING_HUMAN_REVIEW`
- 人类指令：用户 2026-09-17 本会话「开吧，向下推进」——授权开 C4 卡并向下推进。

### 起因

命令链：PR #71 合入 B5 判据 draft-4（2026-09-14）→ Yenefa 指示「下一步你本人应该直接进入 C3」→ PR #72（C3 小项 1–4）于 2026-09-14 开卡待审，其 HANDOFF 写明下一步为 **C4 `tools/akcli_adapter.py`**。2026-09-17 用户授权开 C4。本卡从 `origin/master`（`0d31a8b`）起，不依赖未合入的 C3（合同 §3 允许 adapter 只依赖 `repair_verification` 的纯 hash/规范化 helper，这些在 C2 已在 master）。

### AI 与人各做了什么

- **人工**：授权开 C4 卡并向下推进（同 `tasks/W1-C2.yaml`、`tasks/PR1-C3.yaml` 的授权链，含 `allow_dirty`/`allow_drift`）。
- **AI**：读合同 §2/§3/§4/§7/§8/§10/§11 与 B5 判据 §C4，实现 `tools/akcli_adapter.py` 与 `tests/test_akcli_adapter.py`，建 `tasks/PR1-C4.yaml`，跑门禁与真原生资格，起草本条目与 HANDOFF。
- **AI 未做**：未实现 C5/C6；未提交 candidate；未执行 B5 的 C4-P1..P4-P8 扰动；未生成正式 Evidence；未 merge/approve。

### 本次改动

- `tools/akcli_adapter.py`（新）：合同 §8 三个入口 `read_native` / `apply_stage` / `worker_main`。
  - `read_native`：闭合请求校验（未知字段、重复 JSON key、NaN/Infinity、深度、字节上限）、宿主只读授权上下文、声明根内解析并拒绝链接/逃逸；固定 Python worker 用 `akcli.readers.kicad` 的 `read_sch`/`read_primitives`/`read_embedded_library` 收集完整原生观察，经 `normalize_observation` 规范化后返回，并附 `connectivity_findings`（同一 `akcli.writers.connectivity.verify` 集合，供 before/after 比较）。
  - `apply_stage`：HostPatch 自校验（含 `patch_sha256` 重算）、route 与 `ROUTE_BY_RULE` **冻结一致**（E1/E2/E3→exception，DC-04/05→strict，未知规则 `REPAIR_POLICY_DISABLED`）、宿主 `TOOL_EXECUTE`/`FILE_WRITE` 双 ALLOW 凭据、toolchain 绑定重算、stage/op-list 路径包含检查、op-list 与绑定 proposal 的逐 op 一致。
  - STRICT：一次精确 argv（`akcli draw <stage> --ops <oplist> --apply --strict-nets --no-erc --json`，shell=false，单次写调用）；exit=6 合法拒绝对象（两种形态）→ `BLOCKED / REPAIR_STRICT_REFUSED` 且**不复用旧 XML 式回退、不改走 exception**；exit=0 但 `applied` 缺失/false → `BLOCKED / REPAIR_EFFECT_MISMATCH`；伪造 `applied=true` 而字节未变 → 同一码；坏 JSON/非 0 退出 → `TOOL_ERROR`。
  - CONSTRAINED_EXCEPTION：固定 Python worker 只调用 `akcli.writers.kicad.apply(oplist, stage, apply=True, sources=None, backup_dir=host_dir, backup_depth=1, tol_nm=0, verify_out=findings, allow_open=False)`；API 无 `applied` 字段 → `tool_applied=null`，且回执强制该字段为 null。
  - 四项合取验收后写：`op_results` 必须逐一覆盖 `0..n-1` 且全 `ok`、stage 字节真改变、修后成功重读、toolchain/符号 digest 与宿主 manifest 一致、连通性无 ERROR/CRITICAL、无新增 WARNING、无任何 `NO_CONNECT_CONFLICT`；未知 severity → `UNKNOWN`（不降为 INFO）。只有全部成立才 `APPLIED_TO_STAGE`。
- `tests/test_akcli_adapter.py`（新，45 例）：宿主桩 akcli 包（含 RECORD 驱动的发行包摘要、embedded library、connectivity）+ 桩 CLI 覆盖 strict 双形态、dry-run、applied 矛盾、op 缺/重/错、版本/发行包/符号 digest 错、路由冻结、越权/漂移/路径逃逸、单次写调用且被拒后不 fallback、新 WARNING/NC/ERROR/未知 severity；另有 `NativeQualificationTests`（opt-in）。
- `tasks/PR1-C4.yaml`（新）：Goal/Scope/Impact Analysis/Change Budget/allowed-forbidden/acceptance/exceptions。
- `docs/ID_MAP.md`、`tools/build_ai_usage_index.py`：机械重放 Yenefa 2026-09-14 已批准的 `DSH` 代号登记（原登记只存在于未合入的 PR #72 分支）。
- 台账：本条目 + 重建索引；`docs/HANDOFF.md` 追加本节状态。

### 实际运行的验证（原文）

- `py -3.9 -m unittest tests.test_akcli_adapter` → Ran **45**，**OK (skipped=1)**（skip 为未 opt-in 的原生资格类）。
- `py -3.9 -m unittest discover -s tests` → Ran **670**，**OK (skipped=1)**（master 基线 625 + 本卡 45，无回归）。
- **真原生资格（opt-in）**：`AEDL_PR1_NATIVE=1`、`AEDL_AKCLI_PYTHON=<本机 akcli 环境 3.11.15>`、`py -3.9 -m unittest tests.test_akcli_adapter.NativeQualificationTests` → Ran **2**，**OK**：
  - 五个原生夹具 DC-01..DC-05 经 `read_native` 全部 `PASS` 并产出规范化观察（DC-04：22 组件 / 84 pin / 29 分区，`coverage.complete=true`）。
  - 真 strict 路由在 DC-04、DC-05 上经 `apply_stage` → **`APPLIED_TO_STAGE`**，3/3 op `ok`、无 connectivity finding，且 before/after 字节与 2026-09-16 本机独立复现记录**逐字节一致**（DC-04 `655f585d…`→`2f660180…`；DC-05 `08393ee9…`→`033e4efa…`）。
  - 实测工具链：akcli `0.21.0`、发行包摘要 `a81c1a4d…`、本设计 embedded symbol digest `9a0473ff…`。
- `py -3.9 -m tools.admit --envelope tasks/PR1-C4.yaml --allow-dirty` → **ADMIT**（exit 0）。
- `py -3.9 -m tools.dev_gate --envelope tasks/PR1-C4.yaml --admit-receipt <admit-c4.json>` → **status pass / exit 0**，dirty=true（候选未提交）：syntax pass；main_tests pass；sandbox_tests pass；secret_scan pass；ai_usage_ledger pass（99 条，索引同步）；scope_check pass；binding_check pass；bundle_check pass；`excluded_checks` 为空；envelope sha256 `15aa33dcfbfbe223e261e86a3940d1586f18416cae62656e2a90611ee398834c`。

### 未运行 / 限制（如实声明）

- **CONSTRAINED_EXCEPTION 对真 akcli writer：`NOT_RUN`**。仓库既有原生夹具只有 DC-01..DC-05（strict 线），E1/E2/E3 的 exception 夹具不存在，因此本轮只用宿主桩 writer 验证该路径的软件语义；真 `akcli.writers.kicad.apply` 调用未执行。
- **C4-P1..P8（B5 扰动）：`NOT_RUN`**——属验收侧，且需 C5/C6 齐备。
- **C5/C6：`NOT_RUN`**（不在本卡）。
- 未提交 candidate、未 promotion、未生成正式 Evidence（`docs/evidence/**` 在本卡 forbidden）。
- sandbox junction 用例在部分 Windows 机器上 `WinError 183`（未关 Issue #51）；本机 dev_gate 结果以下方补记为准。

### 实现中做出的、需人工复核的判断（合同留白，已显式记录）

1. **`symbol_digest` 的定义**：合同与 B5 C4-P6 要求「符号库 digest 不符即拒」，但 akcli 0.21.0 的 `akcli.writers.lib_cache` 不暴露全局 cache 目录。本实现把符号环境定义为**文档内嵌符号库**（`read_embedded_library`）的摘要——即 `place_component` 实际解析所依据的环境；无内嵌库则 fail-closed。该定义需 Owner/验收侧确认。
2. **原生观察的身份约定**：akcli 的 reader 不返回 KiCad 的逐 pin 实例 UUID（`Pin.unique_id` 为 `None`），因此 `read_native` 的 sheet UUID 与 pin UUID 由适配器确定性派生（`uuid5`），component UUID 用 akcli 的真实 `unique_id`。C3 的 `_native_agreement` 只比较分区/组件/引脚视图（不含身份），故本约定对其成立；但任何跨 reader 的**身份**比较在采用前需评审。
3. **severity 归一化**：akcli 还有 `NOTE` 一级。合同把词表固定为 INFO/WARNING/ERROR/CRITICAL 且禁止把未知值降为 INFO；本实现显式把 `NOTE`→INFO 并保留 `raw_severity`，其余未知值一律 `UNKNOWN` 并阻断（映射在模块 docstring 中公开可审）。
4. **`launcher_argv` 的作用域**：只用于 akcli CLI 调用；worker 一律以 `worker_python -m tools.akcli_adapter` 启动（曾因把 launcher 前缀同时用于 worker 导致解释器自我执行，已修正并在模块内说明）。

### 待人工确认

- 本条目与代码在合入前状态为 `PENDING_HUMAN_REVIEW`；AI 不 merge、不 approve。
- 上述四项实现判断（尤其 `symbol_digest` 定义与身份约定）需 Owner 或验收侧裁定后才能作为冻结语义。

### 2026-09-17 补记 —— PR #75 人工 REQUEST_CHANGES 整改（不改写以上原文）

人工评审（Owner，2026-09-17，针对 head c2800df）给出 REQUEST_CHANGES：3 项 blocker + 3 项应修。逐条整改：

1. **op-list 只比较 op 名称（BLOCKER）** → 新增 _normalized_operations/_normalize_operation：按合同 §4 的 Operation v1 逐字段闭合校验并补默认值（rotation=0、mirror=none、unit=1、scope=local），比较**规范化后的完整 op 对象**，并同时绑定 oplist 的 protocol_version 与 target_format；另补 proposal_sha256 重算（canonical_sha256("proposal", host_patch["proposal"])）。
2. **fresh-after 连通性仍以 writer 回执为事实源（BLOCKER）** → _verify_effect 改用 **fresh native_after 的 connectivity findings** 作 after 事实源；writer 回执仅保留为回执审计，并在其报告 ERROR/CRITICAL 时仍然阻断（fail-closed 并集），新 warning 判定只用 fresh read。
3. **warning 对象身份丢失 + 缺 host-frozen background（BLOCKER）** → _native_connectivity 保留 akcli finding 的 refs 作为对象身份；connectivity_verdict(before, after, background=...) 显式接受 background 集合；本版合同没有 host-frozen background 通道，_BACKGROUND_WARNINGS 为空 → **所有 WARNING 阻断**（取更保守的 fail-closed），并把「缺该通道」作为边界问题上报 Owner。
4. **闭合校验未递归（应修）** → proposal（PATCH 分支全字段 + diagnosis 行）、oplist、base、authority.decisions、op 逐层闭合；新增 _reject_unknown/_required，可选字段不再被误当必填。
5. **op-list 路径 containment 只做 lexical commonpath（应修）** → op-list 改用与 stage target 同级的 _resolve_within（逐组件拒绝 symlink/reparse point + realpath 包含）；native_artifact_root 增加链接组件拒绝（它与 stage 是分离的 host 区域，故只做链接检查、不要求 disjoint）。
6. **coverage.complete 自证 + no_connect 硬编码（应修）** → worker 用 akcli 自身的 metadata.component_count / metadata.pin_count 与 read_primitives().pins 做交叉核对；任一对不上、或没有任何交叉核对可用 → UNKNOWN / REPAIR_COVERAGE_INCOMPLETE。模块 docstring 明确 coverage 是「内部交叉核对，不是独立证明」（独立核对归 verifier：C3 的 _native_agreement）；no_connect 明确记为**当前合同版本未被任何一侧建立**（C2 的 source 观察同样硬编码 False），保持 inert 且不声称已证。

新增回归（对应用户点名的 5 条）：same-op/different-arguments → 0 次 writer 调用 + REPAIR_INPUT_DRIFT；回执干净但 fresh after 出现新 WARNING → BLOCKED；warning 从 R1 移到 U7 → BLOCKED 且对象身份被保留；畸形嵌套 proposal/oplist/op → 闭合 BLOCKED 且不抛异常；op-list 经目录 junction 逃逸 → BLOCKED。另加：background 白名单机制的直接单测、reader 库存不一致/无交叉核对 → UNKNOWN、畸形 stage_request 不抛异常、proposal 自身 digest 不符 → REPAIR_INPUT_DRIFT。

验证（原文）：py -3.9 -m unittest tests.test_akcli_adapter → Ran **57**, OK（skipped=2）；py -3.9 -m unittest discover -s tests → Ran **681**, OK（skipped=2）；真原生资格（opt-in）→ Ran **2**, OK，DC-04/DC-05 仍 APPLIED_TO_STAGE 且 before/after 与本机独立复现逐字节一致；junction 逃逸用例实测执行（非 skip）并通过。

状态：本轮为 PR #75 的整改提交；merge 仍待人工，AI 不 merge、不 approve。

### 2026-09-17 补记②——PR #75 第二轮 REQUEST_CHANGES 整改（不改写以上原文）

Owner 第二轮评审（针对 cdf4f03）：1 项 CI blocker + 3 项 P1/P2 + 文档同步。逐条：

1. **Ubuntu CI 红（BLOCKER）** → 取回 Actions 失败日志定位：`ExceptionWriterTests` 全 4 例在 ubuntu-latest 上失败，原因是 **hosted Python 的 `bin/python` 是指向 `python3.9` 的符号链接**，被适配器的 `_is_link` 判为「pinned worker interpreter is missing」。修法：**宿主冻结的可执行文件（worker_python / akcli_executable）允许是符号链接**（打包解释器/CLI 常规如此），数据路径（stage target、op-list）保留逐组件 no-link 规则。新增 `test_a_symlinked_worker_interpreter_is_accepted`（Windows 无开发者模式时 skip，Linux CI 实跑）。
2. **stale proposal / TOCTOU（P1）** → 新增三项 internal binding，全部在任何 writer call 之前：`hash_bytes(stage bytes) == proposal.base_source_sha256`（否则 BLOCKED/REPAIR_INPUT_DRIFT）、`proposal.context_id == host_patch.context_id`、`proposal.target == host_patch.target`。回归：`test_a_stale_proposal_base_is_input_drift`、`test_a_proposal_that_disagrees_with_the_host_patch_is_input_drift`（均 0 次 writer 调用）。
3. **authority 冲突/重复（P1）** → decisions 改为「每个 capability 恰好一个 resolved decision」：重复 capability → BLOCKED，任何 DENY → BLOCKED，然后才要求 TOOL_EXECUTE/FILE_WRITE 的显式 ALLOW。回归：`test_a_conflicting_or_duplicated_authority_decision_is_refused`（ALLOW+DENY、重复 ALLOW、无关 capability DENY 三种）。
4. **receipt-only NO_CONNECT_CONFLICT（P2）** → 回执与 fresh read 分项比对：回执报 ERROR/CRITICAL 而 fresh read 没有、或回执报 NO_CONNECT_CONFLICT 而 fresh read 没有 → BLOCKED/REPAIR_TOOL_PROTOCOL_ERROR（矛盾本身即阻断，不挑一个信）。回归：`test_a_receipt_only_no_connect_conflict_is_an_inconsistency`。
5. **Windows 跨盘 commonpath 裸异常（P2）** → 新增 `_common_root()` 把 `ValueError` 转成 `AdapterInputError`，op-list 与 `_resolve_within` 都走它。回归：`test_a_cross_drive_op_list_is_an_input_error_not_a_crash`（mock 出跨盘 ValueError）。
6. **bound_policy 口径（P2 建议）** → 已在 PR 正文与本节如实承认：C4 把 `bound_policy` 视为 **host-bound opaque payload**，只要求其存在与 digest 绑定，不宣称 C4 自己重验完整 BoundPolicy；完整 authorized delta / protected diff 由 verifier 与 pipeline 负责。

验证（原文）：tests.test_akcli_adapter → Ran **63**, OK（skipped=3，其中 2 为未 opt-in 原生资格、1 为本机无法建文件符号链接）；discover -s tests → Ran **688**, OK（skipped=3）；真原生资格（opt-in）→ Ran **2**, OK，DC-04/DC-05 仍 APPLIED_TO_STAGE 且 before/after 与本机独立复现逐字节一致。

状态：本轮为 PR #75 的第二轮整改提交；merge 仍待人工，AI 不 merge、不 approve。
