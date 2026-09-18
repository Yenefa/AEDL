# SchGen exposed DEV native chain

> **2026-09-18 作用域横幅 —— ingest-only 重切**：本文件现在服务于一个**新的** BENCH/DEV PR，
> 它只承载 **adapter 无关的格式导入层**。下方「历史正文」逐字来自已关闭的 PR #74
> （分支 `fix/schgen-dev-native-chain`，head `052750c`）；其中的 repair chain / scorer /
> 旧草稿 adapter / writer 诊断 / DEV-04..06 合同 / 配对评分记录**不在本 PR 中**，
> 仅作为背景历史保留。引用下方历史数字时必须标明「held 半，未进本 PR」。

---

## 历史正文（来自已关闭的 PR #74；held 半，未进本 PR）

2026-09-16 DEV-05/06 continuation: independent writer review is retained as an
agent review, without promotion authorization. No production or writer code
changed this round; diagnostics and contract drafts are under the Codex output
dev05-dev06-contracts-v1. Six fresh KiCad 8 exports isolate two causes: DEV-05
duplicates the entire U1 pin definition, and removing the pins-only duplicate
changes U1.4 occurrences 2->1 without changing any other native partition.
IRLML6402 physical pins are G/S/D, unlike the candidate's G/D/S symbol; preserve
numeric pin-to-net identity before considering functional changes. Gate source
selection, full part identity and operating limits remain contract decisions.

DEV-06 correction: removing connector wire B alone separates supply and return
and removes C1/C2/C4 bypasses. Suspected wire A is not an independent native
short; deleting it disconnects VDDD pin 50. This supersedes earlier multi-bridge
geometry attribution. Real power pins 10/11 remain open in all controls. J1
power pinout and hardware-SCB versus software-I2C intent require adjudication.
Removing B alone is not a complete repair. Source documents, exact diagnostic
objects, requests and native partitions are hash-bound; reference exposure is
disclosed. The drafts contain no executable writer op-list.

Current checkpoint: DEV_CONTRACT_CAUSES_ISOLATED / PENDING_HUMAN_REVIEW. Bound
toolchain, DEV originals, frozen protocol, scorer and paired results remain
unchanged. DEV-04 retains WRITER_QUALIFIED_DEV_ONLY / STRICT_NETS_BLOCKED;
DEV-06's named-net split also remains outside strict-nets. No apply, install,
new after/score, formal experiment, Primary switch, commit, push or PR. Current
verification is dev05-dev06-contracts-v1/VERIFICATION.md and
dev-gate-dev05-dev06-contracts.json; review-dev05-dev06-contracts binds this
10-file worktree state. Next: adjudicate the concrete component/interface/state
contracts before authoring exact edit plans; no authorization is inferred.

2026-09-16 writer-fix qualification: user resolved D1 to the exact table, D2 to
retain strict-nets and fix the writer first (NO exception), and D3 to retain the
requested five-pin contract with component replacement handled separately.
These answers supersede the pending decision text in the historical section below.

The isolated akcli 0.21.0 patch is in the current Codex task's
_src_akcli_dev04/akcli-68c2df5e43db2f822ab8dbfea36f777396897d8d; the older Desktop
_src_akcli_dev04 tree is an earlier RED tree, not the patched implementation.
Four writer files changed; per-sheet pre-edit junction requirements suppress
unrequested normalization, and collapsed wire/bus vertices now fail explicitly.
Separate synthetic regressions and authoring documentation accompany the patch.
No installed toolchain, AEDL production code, strict-nets gate or reader changed.

Fresh qualification (dev04-writer-fix-v1/qualification-20260916) binds all 220
installed Python files to the upstream archive and identifies exactly those four
patched source files. Three new KiCad 8.0.9 exports verify empty-op identity and
corrected-preview P1/P2/P3; the latter changes exactly two deleted wires and one
added wire, preserving all eleven junction forms and every other complete root
form. Writer/native pin partitions agree on this sample after excluding power
symbol tokens. Original plan/input/request/reference and protocol hashes match.

Corrected synthetic test vocabulary: delete_object, not the old delete typo.
Explicitly bound pristine source gives 9 failed / 2 passed; patched full suite
includes all 11 passing regressions. UTF-8 and installed test dependencies remove
the prior broad host failures: 3533 passed, 111 skipped, 2 failed. Both remaining
failures reproduce on pristine 0.21.0; ruff passes and mypy passes 68 source files.
This is not a fully green release gate, nor calibration of the general reader.

DEV-04 is still STRICT_NETS_BLOCKED / PENDING_HUMAN_REVIEW. The +5V split remains
prohibited by D2. No target apply, paired after, new score, component replacement,
formal run, install into bound toolchain, commit, push or PR. Last paired DEV run
remains run-audited / scores-audited, N=B=P=10, 10 ABSTAINED, mean delta J=0.
Review artifacts and reproducible native audit are under dev04-writer-fix-v1.

2026-09-15 DEV-04 writer diagnosis continuation (user-supplied failed plan):
inspect scratch/schgen-eval/dev04-plan read-only; reproduce the three reported
dry runs and isolate coordinate units versus whole-document auto-junctions.
Own new diagnostic outputs only under Codex outputs/schgen-dev-mainline/
dev04-writer-diagnosis-v1, plus existing task/compliance/evidence records in this
10-file budget. Installed akcli and its policies are read-only. Dry-run preview
files are explicitly diagnostic, not applied DEV outputs, after scores or
protocol amendments. Keep D1/D2/D3 unanswered and no apply to DEV-04; do not
relax strict-nets to force a result. Root-cause evidence precedes any new plan.

Writer diagnosis result: original v1/v2/v3 reproduce. Their raw coordinate
arrays use mm numbers where akcli requires mil; all endpoints snap to one
50-mil point, so add_wire creates zero segments while returning ok. Correct
3750/2050 -> 3750/2000 mil coordinates restore VDD in independent KiCad 8
preview. Empty ops also add five global auto-junctions and reproduce the
unnamed STAT/PROG merge prediction. KiCad 8 does not observe that merge until
the original long STAT wire is explicitly segmented; two segmentation controls
confirm this with and without the new junctions. Corrected preview passes
P1/P2/P3 but retains five undeclared junction additions, a model disagreement
and strict named-net refusal on apply. No target apply or scorer run occurred.
Final reproducible diagnosis: dev04-writer-diagnosis-v1/run-03; 5 stock dry runs,
13 fresh native exports and all diagnostic assertions pass. Failed initial
hypotheses are retained. D1/D2/D3 requested from user; PENDING until answered.

Status: DEV_PREFLIGHT_ROUTING_VALIDATED / PENDING_HUMAN_REVIEW. This is engineering qualification,
not the formal SchGen experiment or a Primary promotion.

LATEST (request/native attribution continuation): run-audited / scores-audited
retains N=B=P=10, 10 byte-identical ABSTAINED terminals, mean delta J=0. The
request/native-only preflight routes DEV-04, DEV-05 and DEV-06 to review before
planner/writer dispatch. DEV-04 violates its explicit pin partition (and the
manual review finds a wrong embedded charger symbol); DEV-06 supply/return pins
coalesce. DEV-05 exports U1.4 on two different NC nets, a native identity
ambiguity; the manual PMOS load-sharing concern requires independent review.
DEV-08 and DEV-09 have no demonstrated request violation in this bounded review.
For DEV-09 only, swapping the symmetric jumper's pin tokens in a diagnostic
copy makes all four scorer sets equal. Official J remains 1/3; no schematic,
scorer or endpoint was changed. Diagnostic attribution is not repair efficacy.

Focused verification: 27/27 passed (including three actual native writer
controls). Full gate output is dev-gate-audited.json; the previously reproduced
sandbox junction failure remains a separate existing issue. Reports/bindings:
attribution-v1/ATTRIBUTION.md, adjudication.json and input-bindings.json under the
Codex task output root. Human adjudication is still PENDING_HUMAN_REVIEW for
every row. No supported automatic repair was established and no H1/Primary
gate is passed by this exposed retrospective review.

PREVIOUS INGESTION RESULT (supersedes the phase-one raw-export interpretation below):
the empty legacy symbol_instances root block caused KiCad 8 to omit later
labels/junctions. Nine of ten exposed DEV inputs had this ordering hazard.
An explicit ingestion stage now removes ONLY the empty block, preserves all
other full AST forms and the object graph, keeps source bytes/hashes, and
rejects nonempty/ambiguous metadata. Removing the block also keeps subsequent
writer appends importable. Moving it last was a diagnostic, not the final fix.

Both candidate inputs and native reference artifacts passed fresh KiCad 8
ingestion, 10/10 each. Reference inputs use a separate tagged manifest and are
never published as repair inputs. The evaluator now requires a hash-bound native
reference and exports it freshly after ALL repair terminals exist.

Current run-ingested / scores-ingested: N=B=P=10, all 10 ABSTAINED, delta J=0.
Corrected baseline mean J=0.55454717696097; 5 designs at J<=0.95, not the legacy
record's 8. This is baseline reconstruction, not AEDL electrical uplift and not
confirmation that those five have repairable electrical defects.

Native KiCad 8 synthetic writer controls on disposable DEV copies: legacy input
blocked before apply; ingested input's new test-net connection independently
observed (2/2 expected outcomes). Focused suite: 19/19 pass, including three
KiCad 10 synthetic controls. Main suite: 644 OK (3 opt-in controls skipped there
and separately run). Full dev_gate remains FAIL on the unchanged Windows
sandbox junction test, reproduced on the clean baseline.

Goal: replay all 10 already exposed stage1 DEV artifacts through a request-only
native repair boundary and independent fresh before/after observation. Score
only after every repair terminal is persisted, in a separate evaluator process.
No generation/API calls, new sample selection, or HELD_OUT reads are needed.

Impact Analysis

- Direct modifications: tools/akcli_adapter.py (snapshot of the existing local
  draft from ../_wt_c3, then narrowly fix missing-pin checks);
  tools/schgen_dev_chain.py; tools/schgen_dev_score.py;
  tools/schgen_native_ingest.py;
  tests/test_schgen_dev_chain.py; this task record; AI usage entry/index;
  third-party and evidence indexes if triggered.
- Potentially affected: new DEV commands only. Existing core gates and scratch
  formal scripts retain their current behavior.
- Explicitly not touched: main checkout, other worktrees, SchGen generator,
  raw DEV inputs, reference scorer, frozen protocol and HELD_OUT.
- Risk: MEDIUM. Native writer changes candidate copies only. Refused/failed or
  over-broad mutations are retained as candidate evidence and rolled back to a
  separate byte-verified terminal file with fresh exports.

Change budget: at most 10 tracked files, modules tools/tests/docs/notes;
cross_module=true for the tool/test boundary; contract_change=false for existing
public contracts; evidence_semantics_change=false. New DEV record formats do not
implement or alter preregistered formal inference. Existing untracked adapter is
reused with provenance, not represented as a newly authored 1,000-line module.

Acceptance: meaningful negative tests fail before fixes; real KiCad/akcli DEV
replay has an assigned denominator of 10, one terminal record per assignment,
fresh after artifacts for abstentions/rollbacks, and a separate scorer report.
No success claim based solely on receipt, hash change, or ERC warning count.
Formal safety qualification and human electrical adjudication remain separate.

Route: qualify the native DEV chain first; reconcile split/protocol exposure and
bind F0/T0 before any formal generation. A previous scratch decision or older
split cannot retroactively satisfy the current UNBOUND protocol.

AIC score target: NONE (internal development). No release/merge requested.

## Phase-one observations (superseded as electrical benchmark evidence)

The native writer integration is now executable from the branch. It is not yet
qualified for formal SchGen repair. The final DEV report retains 10 assignments,
10 evaluable baselines and 10 actual after pairs. Nine abstentions and one
verified rollback produce mean delta J = 0; no positive efficacy claim follows.

- Existing draft adapter incorrectly accepted disappearing pins as a short or
  split. Two failing tests reproduced this before the identity checks were fixed.
- Existing draft adapter accepted empty native exports. A failing test and a
  KiCad 10 export of this SchGen DEV input reproduced the empty-view issue;
  empty component/connectivity views now fail closed.
- First integration attempt lacked the required akcli protocol header. The
  refusal and complete run-01 records remain. protocol_version=2, target_format
  and target_file are now explicit and tested.
- run-02: request-only parsing selected three explicit pin/net declarations for
  DEV-01. akcli reported applied=true and added three local labels, but KiCad
  8.0.9's fresh XML kept all three pins on unconnected nets. The adapter returned
  FAILED_UNOBSERVED_CHANGE and the runner retained the candidate and independently
  verified a separate raw-byte rollback terminal. This is a writer/native export
  disagreement; its underlying geometry/import cause is still unresolved.
- Existing DC-04 control fixture did not export under KiCad 8. The KiCad 10
  controls cover positive pin-anchor wire, negative coordinate-only wire and
  positive local label on an unconnected pin (local names are sheet-qualified).
  Those controls do not qualify the SchGen/KiCad 8 path.
- Cross-version diagnostic: KiCad 10 exported the DEV-01 raw and candidate with
  empty connection views. The pre-fix diagnostic records preserve that finding;
  it cannot be used as an alternative baseline, after score or working fix.
- Legacy request digests were over UTF-8 text after Python universal newline
  decoding, not raw Windows file bytes. Bound request copies exactly reproduce
  the recorded generator-input digests; source-byte digests and normalization
  are separately retained in request-provenance.json.

Supported DEV repair grammar is narrow, case-preserving single-line explicit
pin-to-named-net declarations on singleton unconnected pins. No alias inference,
multi-pin/conditional prose, or reference-based repair planning. Unsupported
cases abstain and remain in N. Scoring is descriptive and rejects empty sets.
The separate evaluator imports the pinned upstream scorer by hash. It has no
model calls and cannot feed outcomes back into the repair process.

Full protected forms, exact pin/net mappings, label additions and fresh ERC
flags constrain the label-only candidate. New ERC flags trigger conservative
rollback, never automatic classification as a confirmed electrical defect.
Modified-output electrical adjudication would remain UNKNOWN pending review;
this run's final outputs are byte-identical to their baselines.

## Next mainline checkpoint

2026-09-15 second continuation: audit the five remaining low-J exposed designs.
Within the same 10-file budget, extend tools/schgen_dev_chain.py and its existing
tests with request/native-only preflight diagnostics. Recognize a strict explicit
net-partition section, detect contradictory partitions and supply/return pin
coalescence, and stop unsupported mutations before writer dispatch. Findings
route to review; absence of a supported finding is not electrical acceptance.
No new repair primitive, scorer normalization, automatic package substitution,
or baseline geometry change is authorized by this policy extension. Record
manual score-attribution separately, with reference access disclosed. Risk is
MEDIUM; acceptance requires negative/control tests and all 10 terminal records.

2026-09-15 continuation: the user explicitly requested continuing the native
chain investigation. A single-variable DEV intervention located KiCad 8's
legacy symbol_instances ordering hazard: moving the empty block last restores
the raw design's already present global labels. Nine of ten raw DEV files have
objects after that block. Prior raw-export headroom/paired metrics are retained
as superseded diagnostics, not qualified electrical evidence. Add an importer
guard plus a separate, deterministic DEV format-ingestion tool (one additional
tools file, total tracked-file budget remains 10). The tool must preserve every
AST form and source bytes in an audit trail; format ingestion is never scored
as an AEDL electrical repair. Frozen formal rules and upstream files stay intact.

1. Native import and writer observability are now resolved for this bounded
   KiCad 8 recipe. Keep the separate ingestion stage and both raw/prepared hashes.
   Old raw-export headroom records cannot be reused as electrical evidence.
2. Independently adjudicate genuine defects in the five remaining low-J DEV
   designs; broaden request parsing only as a separately reviewed DEV policy
   change. Freeze the adapter/planner/environment and complete safety regression.
3. Reconcile the existing exposed DEV IDs with the current protocol's split
   construction. Bind an uncontaminated manifest, tool/scorer hashes and named
   adjudicators, and complete T0/F0 prerequisites before formal generation.

The current preregistration files remain unchanged and UNBOUND. No HELD_OUT
content or results were opened by these new commands. No PCBSchemaGen campaign,
new model request, formal experiment, Primary promotion or main-branch merge ran.

## Reproduction

From this worktree, with absolute paths for INPUTS, RUN, REFS, SCORER and OUT:

    py -3.9 -m tools.schgen_native_ingest --manifest RAW_INPUTS --out INGESTED --kicad-cli KICAD8
    py -3.9 -m tools.schgen_dev_chain --manifest INGESTED/repair-inputs.json --out RUN --akcli AKCLI --kicad-cli KICAD8
    py -3.9 -m tools.schgen_native_ingest --reference-sources REF_NATIVE_INPUTS --out REF_INGESTED --kicad-cli KICAD8
    py -3.9 -m tools.schgen_dev_score --run RUN --references REFS --scorer SCORER --kicad-cli KICAD8 --out OUT
    py -3.9 -m unittest tests.test_schgen_dev_chain -v

RUN/OUT must not exist; all inputs are digest-bound. Real fixture controls are
opt-in through AEDL_DEV_AKCLI, AEDL_DEV_KICAD and AEDL_DEV_CONTROL_OUT, using
KiCad 10.0.5 and a new control directory. Standard unit discovery skips those
three controls when tool variables are absent and reports the skips.

Local raw development artifacts: Codex task outputs/schgen-dev-mainline/.
They are not formal gates/run_gates.py Evidence or benchmark preregistration.

## Phase-one verification history (current checks are above)

- Final focused command: 15/15 passed, including three real akcli/KiCad 10
  fixture controls; receipts in controls-current and focused-tests.txt.
- Final KiCad 8 replay: run-final + scores-final, N=B=P=10, 1 rollback /
  9 abstain, all delta J/F1 = 0. Raw input and tool-source hashes recorded.
- Development gate: main suite 640 tests OK (3 opt-in native controls skipped
  there and run separately above); syntax, secret scan and AI ledger pass.
- Gate remains FAIL: sandbox suite (283 tests) has WinError 183 in
  test_containment_through_a_junction_does_not_false_escape at root.mkdir.
  Same error reproduced on clean 0d31a8b in ../_wt_schgen; plain-path companion
  passed. No sandbox source changed.
- Existing gate --interpreter handling raised TypeError. Using the supported
  AEDL_PYTHON='py -3.9' resolver and PYTHONIOENCODING=utf-8 avoids the CLI type/
  GBK output problems without suppressing tests. Full receipt remains FAIL.
- No Task Envelope was assigned for this standalone continuation. Existing
  envelope scope/binding checks are explicitly excluded by the dev gate.
- Git: fix/schgen-dev-native-chain, uncommitted, not pushed, no PR created;
  PENDING_HUMAN_REVIEW. Formal launch remains blocked on native repair
  qualification and protocol bindings, independently of the sandbox test.


---

## 2026-09-18 重切（本 PR 的实际内容）

**触发**：Owner 既定顺序「#74 close and re-cut as a fresh BENCH/DEV PR without the old
adapter」，并在本次会话的裁定中选择「先落 adapter 无关部分」。

**为什么不能只删文件**：PR #74 的 4 个模块全部 `from tools import akcli_adapter`，而
master 上 `tools/akcli_adapter.py` 已是 PR-1 C4 的 fail-closed adapter（API 不同：
`apply_stage` / `read_native` / `source_objects` / `toolchain_manifest`，没有
`apply_and_verify` / `object_graph` / `parse_sexpr` / `export_netlist` /
`check_expectation` / `native_import_issues`）。删除旧 adapter 后这些模块无法原样运行。

**本 PR 落地（全部基于 master `9d048332`）**：

- 新增 `tools/schgen_native_ingest.py`：**自包含**格式导入工具。只删空的 legacy
  `(symbol_instances)` 根块；保留源字节、其余全部根形式与对象图；产出 fresh KiCad 8.0.9
  网表与 ERC 观察、新清单与新绑定。模块**不导入任何 `tools.*`**（有 AST 断言守护）。
- 新增 `tests/test_schgen_native_ingest.py`：**31 例**边界/扰动测试（14 + 7 + 5 + 3 + 2）。

**代码来源**：只读辅助提取自 PR #74 携带的旧草稿 adapter 与 DEV chain（同项目 AI 生成
资产，非第三方源码）。语义差异两处，均已文档化：报告不再写 `adapter_sha256`；
`kicad-cli --version` 读不到时以文档化的 recipe 错误失败而非 AttributeError。

**Impact Analysis**（AGENTS.md §2.2）

```text
Direct modifications:   tools/schgen_native_ingest.py (new),
                        tests/test_schgen_native_ingest.py (new),
                        notes/schgen-dev-chain/TASK.md, docs/evidence/EVIDENCE_INDEX.md,
                        docs/compliance/THIRD_PARTY_RESOURCES.md，docs/HANDOFF.md,
                        docs/compliance/ai-usage/AI-20260918-DSH-C7396AEC9D7DC7BCD22C6337E56A806E.md,
                        docs/compliance/AI_USAGE_LOG.md (generated)
Potentially affected:   none of the existing gates, adapters, fixtures or src/**
Explicitly not touched: tools/akcli_adapter.py (C4)、gates/**、src/**、sandbox_runtime/**、
                        tests/fixtures/**、notes/b5-acceptance/**、HELD_OUT 相关任何内容
Risk:                   LOW（新增独立模块与测试，无现有调用方）
```

```text
change_budget:
  expected_files: 8
  expected_modules: [tools, tests, notes, docs]
  cross_module: true               # 实际跨 tools/tests/notes/docs 四个模块；治理记录如实，
                                   # 不扩大既有 8-file scope（Owner 2026-09-18 评审明确）
  contract_change: false
  evidence_semantics_change: false
```

**Acceptance**：模块可独立导入且不引用任何 AEDL 模块；31 例边界/扰动测试全绿；`dev_gate` 全绿；真实 KiCad 8.0.9 双例 ingest smoke 全通过（见下方 2026-09-18 评审整改节）。

**未完成 / 不在本 PR**（held）：chain / scorer / 旧 adapter 及其全部 writer、合同与配对
评分记录。它们必须在 C4 adapter 上重新落地后才可再提；本 PR 不产生任何修复或 ΔJ 结论。

**首轮未运行、已补**：真实 KiCad 8.0.9 端到端 ingest 回放已在评审整改轮补跑
（见下）。**仍未运行**：正式实验、模型调用、HELD_OUT 读取、任何 scorer 或 repair —— 均为
`NOT_RUN`，不是通过。


---

## 2026-09-18 评审整改（Owner REQUEST_CHANGES @ head `61736f6`）

Owner 裁定方向认可（旧 adapter 已彻底拿掉），但列出 2 个 P1 code blocker + 2 个交付/治理 blocker。
本轮逐条闭环，**未动 C4 adapter，也未把 chain/scorer 塞回来**。

### P1-1 输入绑定 TOCTOU —— 已修

原文在 `sha(path)` 校验之后另起一次 `shutil.copyfile(path, ...)`，即两次独立读路径；
manifest 也是先 parse、最后再按路径重算哈希。改为**读一次**：

```text
read_bytes(path) -> sha256_bytes(这些字节) -> 用这些字节 parse / 写盘
```

- raw / request：绑定、读取、写盘使用**同一份 bytes**；该路径上不再有第二次读取
  （`shutil.copyfile` 已从这条路径移除）。
- manifest：`original_manifest_sha256` 改为报告**被 parse 的那份字节**的哈希。

**反向对照（变异测试）**：把该处还原为「先 `sha(path)` 再 `copyfile`」→
新增扰动回归 `BindingTests.test_a_source_swapped_after_binding_is_not_copied_from_the_path`
**FAILED (failures=1)**；还原修复版后复跑全绿。该回归同时在 `ingest.shutil.copyfile`
上挂 AssertionError，任何「按路径复制」的实现都会当场失败。

### P1-2 空 / 未验证的 reference.net 可被发布 —— 已修

原文只查 `net.is_file()`。现改为：重新读取 reference 字节，**空文件直接失败**；
再过一个只读结构 sanity reader `validate_reference_netlist()` —— 必须是单一
`(export ...)` 根，且 `(nets ...)` 下至少有一个 `(node ...)`（signature-bearing）。
未通过则**不得**写入 `evaluation-references.json`。

**反向对照**：还原为「只看文件存在」→ `ReferencePublicationTests` 两条
（空文件 / 结构为空）**均 FAILED (failures=1)**。

### 治理：`cross_module` —— 已改

`false` → `true`。实际跨 tools / tests / notes / docs 四个模块；不扩大既有 8-file scope。

### 非 blocker：记录 kicad-cli 二进制摘要 —— 已加

`export_netlist()` 在启动工具**前**记录 `kicad_cli_sha256`，运行后复算
`kicad_cli_sha256_after`，不一致即失败；ingestion report 同时带
`kicad_cli` / `kicad_cli_version` / `kicad_cli_sha256`。

### 交付证据：真实 KiCad 8.0.9 ingest smoke —— 已跑

```
KICAD_CLI        C:\Users\Ryan Gosling\AppData\Local\Programs\KiCad\8.0\bin\kicad-cli.exe
kicad-cli 版本   8.0.9
kicad-cli sha256 8b7f4a889dc8cfb8c3eae1337d64ade2fe0cf1ec5daa87878cc709904378fb26

Case A  真实已曝光 DEV 生成件（stage1 Qwiic_Power_Switch_Schematic_v10）
  raw sha256        1d39e5ebbe995d37323c1ae36e22a343f18a77cfee75f3e7602c9e541395b350
  legacy            LEGACY_INSTANCE_TAIL, empty=True, 5 个被忽略的后续根形式
  结果              READY_FOR_DEV / FORMAT_ADAPTER_TRANSLATION / 对象图不变
  fresh netlist     PASS exit=0  components=3 nets=5 pins=7（非空连接）
  ERC               PASS（6 条 violation flags）
  prepared sha256   693cd67b2465ae766f23c8c6134b731f58c7290a56e3276b14e15627ebdf3f5f

Case B  同一真实 DEV 产物经格式导入后的字节（无需 translation）
  结果              READY_FOR_DEV / UNCHANGED_FORMAT / prepared 与 original 逐字节相同
  fresh netlist     PASS exit=0  components=3 nets=5 pins=7
  ERC               PASS（6 条 violation flags）
```

Case B 之所以取「Case A 的导入产物」而非原始 DEV 件：10 个已曝光 DEV 生成件**全部**带
`symbol_instances`（9 个有 tail、1 个块在末尾），没有任何原始 DEV 件是真正的
no-translation 输入；用同一真实产物已绑定的字节验证幂等路径，比另造一个假输入诚实。

两次 fresh export 的 XML sha256 不同是**预期**：kicad-cli 导出带 `(date ...)` 时间戳，
该哈希只作 provenance、不作比较键；两次的 components/nets/pins 完全一致。

**仍未运行**：scorer、任何 repair、held half、ΔJ、模型调用、正式实验、HELD_OUT 读取 —— 全部
`NOT_RUN`，不是通过。原始产出：`scratch\schgen-recut\smoke\`（`SMOKE-RESULT.json` +
`out-A` / `out-B` 完整 ingestion 记录）。

---

## 2026-09-18 第二轮评审整改（Owner REQUEST_CHANGES @ head `45fa912`）

Owner 认可 P1-1 / P1-2 / smoke 已闭合，但指出 tool digest 仍**半绑定**，另有 2 处交付文本过期。

### 1. 「读不到 = 没观察到变化」—— 已消除

原实现是 `if after is not None and after != before: FAIL`。binary 在运行后消失/不可读时
`after is None`，**不会**进入 mismatch 分支，仍可能 PASS。现改为 `ToolchainBinding`：

```text
ToolchainBinding(path)   -> 构造时若读不到 binary 直接 IngestionInputError
verify(when)             -> 复算；读不到 => "could not be rebound"（失败，不是「无变化」）
                            变了   => "changed ...: A -> B"
```

### 2. 整轮只绑定一个 KiCad binary —— 已闭合

`main()` 在版本检查后建立 **一个** `binding`，并把同一个实例传给每一次工具调用：

| 调用 | 绑定 |
|---|---|
| `export_netlist`（native 网表） | 调用前后各 `verify` |
| `export_erc`（ERC） | 调用前后各 `verify`，记录 `kicad_cli_sha256_after` |
| reference `kicadsexpr` 导出 | 调用前后各 `verify` |

循环结束后再 `binding.verify('at the end of the ingestion run')`：失败则 **`ready = []`**，
因此 `repair-inputs.json` / `evaluation-references.json` **都不会**被发布，rc=1。
report 现在带 `kicad_cli_sha256`（= 本轮的绑定 digest，不再是「最后再读一次」）、
`toolchain_binding`（`PASS` / `FAILED`）与 `toolchain_error`。

### 3. 测试与反向对照

测试 21 → **26** 例。新增：`ToolchainBinding` 三例（不可读、运行后消失、被替换）+
两例 run-level（中途消失 → 整体 fail-closed；report 携带绑定 digest）。
**变异对照**：把 netlist 导出处还原为「容忍读不到的旧实现」→
`test_a_toolchain_that_vanishes_during_the_export_fails_closed` **FAILED (failures=1)**；
还原修复版后复跑全绿。

### 4. 真实 KiCad 8.0.9 smoke 复跑（绑定后）

```
toolchain_binding  A = PASS   B = PASS
toolchain_error    A = None   B = None
Case A  1d39e5eb… -> 693cd67b…  FORMAT_ADAPTER_TRANSLATION  3 comps / 5 nets / 7 pins  ERC PASS
Case B  693cd67b… == 693cd67b…  UNCHANGED_FORMAT            3 comps / 5 nets / 7 pins  ERC PASS
```

### 5. 交付文本事实同步

`docs/compliance/THIRD_PARTY_RESOURCES.md` 的 RES-011 原写「KiCad 8.0.9 …（本 PR 未调用）」，
与已跑的真实 smoke 冲突。已改为如实记录：**已在本 PR 的 DEV-only ingest smoke 中实际调用**，
附二进制 sha256，并说明不涉及 repair / scorer / 正式实验。


---

## 2026-09-18 第三轮评审整改（Owner REQUEST_CHANGES @ head `5af7cb3`）

唯一剩余 blocker：**version probe 没有被 binding 包住**。原顺序是
`tool_version(...) → 版本检查 → ToolchainBinding(...)`，留下一个窄窗口：

```text
binary A → --version 返回 8.0.9 → A 被换成 B → binding 哈希 B
→ 后续 verify 对 B 全 PASS → report 仍声称 kicad_cli_version = 8.0.9
```

即「被绑定并实际执行的 B，从未被证明是 KiCad 8.0.9」。另一个同面细节：`tool_version()`
记录了 `returncode`，但 `main()` 只取 version 字符串，`--version` 非零退出而 stdout 恰好是
`8.0.9` 时仍会被接受。

### 修法（顺序反转 + exit_code 门禁）

```text
executable = abspath(--kicad-cli)；不是文件即 ValueError（本命令必填，无 PATH 回退）
binding = ToolchainBinding(executable)
binding.verify('before the version probe')
probe = tool_version(executable)
binding.verify('after the version probe')
probe['exit_code'] != 0 -> ValueError（即使输出含 8.0.9）
version != '8.0.9'      -> ValueError
后续 native / ERC / reference 全部使用同一个 executable + binding
```

report 的 `kicad_cli` 也改为**已解析的绝对路径**（此前记录的是原始参数）。

### 回归（新增 3 例，共 29 例）

- `test_a_binary_swapped_after_the_version_probe_is_refused`：probe 返回 8.0.9 后立刻替换
  binary → **整体拒绝**（`changed after the version probe`），`out` 目录不创建。
- `test_a_nonzero_version_probe_is_refused_even_when_it_prints_8_0_9`。
- `test_a_missing_binary_is_refused_before_anything_is_created`。

**变异对照**：把顺序还原为「先 probe 后 binding」→ 前两条回归 **FAILED (failures=1)**；
还原修复版后复跑全绿。

### smoke 复跑

A / B 两例 `toolchain_binding = PASS`、`toolchain_error = None`、exit 0；连接性与 ERC 与上一轮
一致（3 comps / 5 nets / 7 pins，ERC PASS）。


---

## 2026-09-18 第四轮评审整改（Owner REQUEST_CHANGES @ head `65de069`）

最后一个 blocker 在 helper 里：`export_netlist()` 在 binding verify **之前**又做了一次
`find_kicad_cli()` + `tool_version()`。main 已证明 binary A = 8.0.9；此后 A 若被换成 B，
helper 会对 **B** 先跑一次未绑定的 `--version`，随后才由 verify 发现 A→B。结果不会错误发布，
但不可信 binary 已被执行一次；而 `binding=None` 的 standalone 路径本质仍是「先 probe 后 bind」。

### 修法

- **版本探针只有一处**：`ToolchainBinding.probe_version(expect=...)` —— `verify` →
  `tool_version` → `verify` → 要求 `exit_code == 0`；版本写入 `binding.version`。
  `main()` 只调用它一次。
- **有 binding 时 helper 不再发现/探测工具链**：`export_netlist` 直接用 `binding.path` 与
  `binding.version`；显式传入的 `kicad_cli` 解析后若不等于 `binding.path`，直接 FAIL
  （`the requested toolchain … is not the bound toolchain …`），**不执行任何 subprocess**。
- **standalone 路径同样先绑定后探测**：先 `ToolchainBinding(executable)`，再 `probe_version()`。
- `export_erc` 同样只在 `binding.path` 上运行，并对不一致的显式参数 fail-closed。

### 回归（+2，共 31 例）

- `test_the_netlist_export_does_not_probe_the_toolchain_a_second_time`：计数 `tool_version`
  调用 —— 整轮必须**恰好 1 次**（main 的那次）。
- `test_the_helper_refuses_a_toolchain_that_is_not_the_bound_one`：把与 binding 不一致的路径
  传给 helper → FAIL；同时把 `tool_version` mock 成 AssertionError，证明**没有**第二次探测。

**变异对照**：把 `export_netlist` 还原为「重新 find + 重新 probe」→ 第一条回归
**FAILED (failures=1)**；还原修复版后复跑全绿。

### smoke 复跑

A / B 两例 `toolchain_binding = PASS`、`toolchain_error = None`、exit 0；对象图不变、
连接性与 ERC 与上一轮一致（3 comps / 5 nets / 7 pins，ERC PASS）。

**仍未运行**：scorer、任何 repair、held half、ΔJ、模型调用、正式实验、HELD_OUT 读取。




