# Y4-dry harness — GH-56

Status: `PENDING_HUMAN_REVIEW`. Scored case set: 5 (DC-01..DC-05); canonical experiment version `y4-dry-5case-20260910-v1`. Formal C/D trajectories, native execution and A/B scoring: `NOT_RUN`.

> Pre-freeze protocol amendment (owner, 2026-09-10; version assigned r8): the
> scored Y4-dry case-set target is amended from six cases to five (DC-01..DC-05).
> DC-06 is preserved as `EXCLUDED_BEFORE_FREEZE`, reason `PUBLIC_INPUT_INSUFFICIENT`,
> role `UNSCORED_GOVERNANCE_INCIDENT`; no replacement case will be searched
> or fabricated. The amendment occurred before formal freeze; `C_D_runs` and
> `A_B_scores` are `NOT_RUN`; it was driven by input determinacy / evidence
> sufficiency, not by observed model performance. The runner was amended
> accordingly: `y4-dry.v3` froze the five-case set (`freeze` accepts exactly the
> five neutral IDs Y4-001..Y4-005 under the canonical experiment version, and
> fails closed on four/six cases, duplicate IDs and wrong versions);
> `y4-dry.v4` locks the canonical `attempts_per_slot=1` invariant (metadata
> `attempt` must be exactly 1; 0/2/3/booleans fail closed; repetitions remain
> 1..3; a failed or retried generation cannot create a second formal slot). See
> `DC06_INPUT_GOVERNANCE_INCIDENT.md` and the r7/r8 host deliveries.

Execution continuation prepared six fresh current-observation candidates with
generation-time bindings using an actual task-local KiCad 10.0.6 XML exporter,
plus ten small primary-source/static-source fact candidates. These are review
inputs, not an approved array or a formal public-package freeze. The source-to-Y4
mapping remains unassigned. See the r3 host delivery and INPUT_HANDOFF.md.

Owner intake, producer provenance and A3 handoff requirements are in
[INPUT_HANDOFF.md](INPUT_HANDOFF.md). The current host worksheet is deliberately
not a freeze input; audit-time source hashes do not constitute producer bindings.

This tool freezes supplied public inputs, presents identical bytes to C and D,
validates their raw responses using C1 and records unscored results. It does not
create answers or infer public inputs from host policy or private acceptance.

## Impact and scope

- Direct: `tools/y4_dry_runner.py`, `tests/test_y4_dry_runner.py`, this directory,
  `tasks/GH-56.yaml`, one AI usage entry, its generated index, curated summary
  and the approved decision record ADR-013.
- Potentially affected: consumers of new public packages/raw records.
- Unchanged: C1 parser/projection, C2 verifier/API, C3–C6, private/native fixtures,
  D solver and independent scorer. No new runtime dependency.
- Risk: MEDIUM, because hash binding and experiment exposure need precise records.
- Budget: up to 13 files in the declared scope. The approved draft Y4 package
  v2 adds required observation binding; existing C1/C2 contracts and formal
  Evidence semantics stay unchanged. Scope is recorded in the task envelope.

## Architecture boundary approved by Yenefa on 2026-09-10

Issue #56's original acceptance item 4 referenced C2 comparison for A scoring. Existing
`compare_delta(before, after, bound_policy)` requires an actual after-observation
and host-bound expectations. C1 validates only the Proposal schema. This harness
does not manufacture an after-observation or call C2 for answer scoring.

Approved dry boundary: public input → C/D → C1 → raw record; A3/Percy independently
scores A repair correctness and B qualitative correctness. C2 remains available
for later actual native observations. The user explicitly approved this decision
and directed the Issue #56 update on 2026-09-10; see ADR-013 and the issue.
Architecture approval does not mark implementation review, five-case execution,
all A2 acceptance or merge complete. No C1/C2 API is changed here.

## Missing production inputs

At master `63bc7e31523b403f3229cda2f2db5c291b33482d`, there is no
`tests/fixtures/repair_pr1/public/` directory. Directory inventory shows five
native fault sources (DC-01–05), each next to a repair operation file. Those
operation files and private acceptance were not read or used to build inputs.
Yenefa subsequently identified `src/hardware/m2-board/m2_board.kicad_sch` as the
sixth candidate, using its current real state without fault injection. Do not
create a native/DC-06 fault file. All six candidate byte hashes now match their
baseline Git blobs, but all remain PENDING_OWNER_REVIEW for public release.
Neutral source mapping is unassigned and will be randomized/frozen separately on
the host; never infer it from DC order. The owner had not supplied observations,
bindings/producer records or approved facts. The execution continuation now
provides newly generated observation/binding candidates and researched fact
candidates for owner review; approved facts are still absent.
Six identified source candidates do not constitute six approved public contexts.
Old `notes/m2-evidence-reset` artifacts are not substitutes for six observations;
the full `m2-device-facts-v1.md` or `datasheet_manifest.json` is not public facts.
Subsequently (2026-09-10) DC-06 was excluded before freeze for input
insufficiency and the scored target amended to five cases; the intake history
above is retained verbatim as history. See `DC06_INPUT_GOVERNANCE_INCIDENT.md`.

Provide five owner-reviewed public inputs containing:

1. Neutral case ID plus unique context ID; maintain DC mapping separately.
2. Exact fault source bytes as UTF-8 text (preserve LF/CRLF) and relative target.
3. Current observation and common public facts, including their real verification
   status. No expected terminal state, correct patch, host binding or score.
4. Producer-supplied source/observation hashes and producer identifier.
5. One experiment version and identical budgets across the five cases.

No files named `Y4-001.json` through `Y4-005.json` are shipped as pretend production
inputs. Unit tests use clearly labelled synthetic sources and proposals only.
The missing input question was raised in the task; no answer has been inferred
from elapsed time or the instruction to continue implementation.

## Freeze interface

`freeze` accepts a UTF-8 JSON array of exactly five objects carrying the
canonical experiment version. Each object has these closed fields:

| Field | Meaning |
|---|---|
| `experiment_version` | Must equal the canonical `y4-dry-5case-20260910-v1`; other versions are rejected |
| `case_public_id` | Exactly one of `Y4-001` … `Y4-005`, each used once |
| `context_id` | Unique C1 identifier |
| `target` | C1 candidate-relative design path |
| `source_utf8` | Nonempty exact public source text; no newline normalization |
| `current_observation` | Nonempty public object, supplied rather than synthesized |
| `observation_binding` | Exactly `source_sha256`, `observation_sha256`, `producer_id`; supplied by the observation producer |
| `public_facts` | Public fact array; empty explicitly means none supplied |
| `budget` | `max_ops`, `max_request_bytes`, `max_output_tokens`, `timeout_ms` |

`max_ops` is 1–8 and `max_request_bytes` is 1–65536. `max_request_bytes` is the
legacy C1 field name: it is enforced on the proposer/model raw Proposal bytes
entering C1, **not** on the public package input size (the package itself has no
input-size cap in this field).
Token and wall-time limits must be chosen before formal runs, not after failure.
The token setting is carried to the external adapter; this harness does not
tokenize provider output and records `token_budget_status=NOT_VERIFIED`.

From repository root, with approved input prepared outside the proposer session:

```text
py -3.9 -m tools.y4_dry_runner freeze --inputs <approved-public-inputs.json> --out <new-public-directory>
```

The output is five canonical JSON packages plus `manifest.json`, written last.
Each `y4-public.v2` package contains a C1 `make_public_context` projection, exact source text,
source hash, context digest, generic operation schema, budget, frozen generic
instruction and exposure field list. There are no source filesystem paths or
private assets in a package. Freeze order is independent of input array order.
The producer declares source SHA-256 over exact UTF-8 source bytes and observation
SHA-256 over the existing canonical JSON bytes, plus a 1–64 character C1-style
identifier for its reader/version. The freezer verifies both hashes and retains
the declaration; it never generates a matching declaration to repair stale data.
Source/observation mismatch fails even if a caller recomputes the outer package
or context hash. V1 packages lack this required binding and are rejected; obtain
a newly produced observation/declaration and freeze a new experiment version.
An incomplete batch without a manifest is unusable; retry into a new directory.
Existing directories are never replaced. This is not a crash-recovery system.

## Hash domains and trust

- Package hash: SHA-256 of exact canonical generated UTF-8 bytes, no trailing LF.
- Source hash: SHA-256 of `source_utf8.encode('utf-8')`, preserving its line endings.
- Observation hash: SHA-256 of exact `canonical_json_bytes(current_observation)`;
  paired with the source hash and producer ID in `observation_binding`.
- Context/Proposal digest: existing C1 domain-separated canonical digest.
- Raw response hash: SHA-256 of exact received bytes, including whitespace or
  invalid UTF-8. Base64 retains those bytes losslessly in one result JSON file.

Retain the reviewed manifest/package hashes separately from writable runs. Loader
requires the independently supplied package hash and also reconstructs derived
fields. Replacing both data and its trusted hash is outside this integrity check.
The producer declaration detects stale/mismatched data pairs, but replacing both
payloads and producer declaration remains possible in the same writable trust
domain. Hashes do not prove that an input is authorized, confidential-data-free,
a real KiCad source, or that an observation truthfully represents that source. Those
remain input-review responsibilities. Keyword guards are defense in depth;
they cannot detect answers disguised as arbitrary prose. Path guards reject
known private input paths but are not a sandbox against an arbitrary adapter.

## C and D invocation

`request_bytes(package_bytes, pinned_hash, metadata)` returns the exact package
bytes. Both arms receive the same instruction and data. C must run in a new,
isolated session given only its one package; D supplies an implementation of the
same `adapter(request_bytes) -> bytes` protocol. A caller may use `run_adapter`
for a single invocation, or collect an external provider's byte response via CLI.
There is no bundled model-provider integration or D solver.

The adapter owns actual provider timeout, token enforcement and provider logs.
`run_adapter` calls once, measures elapsed time and records returned bytes;
it cannot interrupt an arbitrary in-process callback. Exceptions are recorded
as `ADAPTER_ERROR` with no proposal; there are no automatic retries or fabricated
REFUSE answers. An external caller importing a response supplies observed runtime.
Exposure values are declarations, not verified isolation guarantees. A new
session does not erase prior developer/model exposure.

Run metadata has exactly `run_id`, `arm` (`C`/`D`), `repetition` (1–3), `attempt`
(exactly 1 — one Proposal generation per slot), `model_or_script_id`, `settings`
and `exposure`. `settings` records the
actual model/script configuration (no secrets). Exposure has exactly:

- `session_id`: identifier.
- `fresh_session`: explicit boolean.
- `input_scope`: `PUBLIC_PACKAGE_ONLY`.
- `prior_case_exposure` and `author_exposure`: `YES`, `NO` or `UNKNOWN`.
- `declaration`: nonempty explanation, truthful about what was accessed.

This harness session read implementation/contract excerpts and earlier task
context, including some host contract details. It is not a blind C trajectory.
No private fixture or native repair operation file was read by the implementation
agent. Existing regression tests may load their fixtures internally when run;
that is not a dependency of the Y4 runtime and produces no formal C proposal.

## Record and independently verify

```text
py -3.9 -m tools.y4_dry_runner record --package <case.json> --package-sha256 <frozen-sha256> --raw <response.bin> --metadata <run-metadata.json> --runtime-ms <observed-ms> --out <raw-directory>
py -3.9 -m tools.y4_dry_runner verify --package <case.json> --package-sha256 <frozen-sha256> --result <raw-record.json>
```

`record` creates `<run>_<case>_<arm>_r<repeat>_a<attempt>.json` exclusively. Reusing
the same slot cannot replace a failure or previous result. Because `attempt` is
pinned to 1, `_a1` is the only accepted slot form; a provider/transport failure
is a failed invocation and must not be replaced by another attempt or an
automatic generation retry. Orchestration must
retain run IDs, allocate the planned schedule, enforce total calls/time and keep
failed invocations; arbitrary new IDs are not a global experiment budget control.

The closed raw record has version/case/input hashes, exact base64 output/hash,
metadata/exposure, C1 parsed Proposal/digest or parse failure, binding status,
observed runtime, byte/op/time budget status, token-verification limitation,
invocation error and record status. `scoring` is always `NOT_RUN`.
Unknown result fields or inconsistent derived fields fail reload. A/B score
fields are not permitted. C1 may normalize documented operation defaults in the
parsed representation; the original byte response is still preserved separately.

`RECORDED` means schema, case binding and measured byte/op/time limits passed.
It does **not** mean a correct repair, native execution or A/B score. Bad JSON,
unknown Proposal fields, wrong binding or exceeded limits remain `REJECTED`
records with their original bytes. Verification recomputes C1 and derived fields;
it reports integrity separately from record status.

Exit codes: `0` freeze/record success; `1` validly stored but rejected response;
`2` package/metadata/integrity or filesystem error. A failed invocation is not a
successful refusal. Native transaction outcome and formal Evidence remain absent.

## Verification

```text
py -3.9 -m unittest tests.test_y4_dry_runner -v
py -3.9 -m unittest tests.test_repair_contract tests.test_repair_verification
py -3.9 -m tools.build_ai_usage_index check --json
py -3.9 -m tools.dev_gate --envelope tasks/GH-56.yaml --admit-receipt <admission.json> --receipt <gate.json>
```

Initial admission used an exact external envelope copy on the clean worktree.
After the user's 2026-09-10 revision approval, the expanded envelope was re-admitted
with `--allow-dirty` to retain the explicitly reviewed existing task diff. Its
authority source is recorded in the envelope/receipt. No drift/dependency bypass
or gate waiver was used. The gate must use the new admission/envelope hash.
Actual results and any baseline failures are in the task review handoff; none
of these checks is a Y4 experiment score or a human acceptance decision.
