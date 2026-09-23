# GH-56 public input intake and scorer handoff

Status: `BLOCKED_MISSING_PUBLIC_INPUTS` / `PENDING_HUMAN_REVIEW`.
This is a host-side preparation protocol. It is not a public case or an approval.
Architecture follows ADR-013 and [Issue #56](https://github.com/Yenefa/AEDL/issues/56).

> Pre-freeze amendment (owner, 2026-09-10; r7/r8): the scored Y4-dry experiment is
> amended from six cases to five (DC-01..DC-05). DC-06 is `EXCLUDED_BEFORE_FREEZE`
> (`PUBLIC_INPUT_INSUFFICIENT`, `UNSCORED_GOVERNANCE_INCIDENT`); no replacement case
> will be searched or fabricated. The six-candidate inventory narrative below is
> retained as history; current objective, owner worksheet and status counts follow
> the five-case protocol. See `DC06_INPUT_GOVERNANCE_INCIDENT.md` and the r7/r8
> host deliveries.

## Scope of this continuation

2026-09-10 execution continuation: the user's instruction to execute NEXT_STEPS
authorizes preparing fresh read-only current observations and reviewable facts.
The first phase adds a current-only KiCad XML producer and focused tests under
notes/y4 (two new files; cumulative task total 11, within the envelope's 13).
It uses exact source snapshots and generation-time bindings, without executing
repairs, importing old observations, changing frozen C1/C2 APIs or implementing
C3 qualification. Candidate outputs remain outside the repository until review.
Risk is MEDIUM for provenance; toolchain and observation limitations must be
recorded. Public release approval and the formal run plan remain human-owned.

Current objective: identify the five releasable scored source/observation/facts
inputs (DC-01..DC-05) before freezing real packages. The five existing native fault
sources are the scored candidates. Yenefa's 2026-09-10 clarification additionally
identified the current real M2 schematic at `src/hardware/m2-board/m2_board.kicad_sch`
as a sixth no-injection candidate; that candidate was subsequently retired with
DC-06. Do not create `native/DC-06/fault.kicad_sch`.
Historical check (2026-09-10, six-candidate inventory): all six sources were verified
as UTF-8 with LF line endings, no BOM, and exact bytes equal to their baseline Git
blobs at `63bc7e31523b403f3229cda2f2db5c291b33482d`. The first five hashes were
unchanged from the earlier inventory. This checks bytes only; native parsing/export
and public release review were absent. Six current observations, generation-time
bindings/producer records and approved facts were explicitly NOT_PROVIDED before
execution, as confirmed by Yenefa. The r3 continuation generated fresh
observation/binding candidates and drafted ten source-backed fact candidates.
Owner source/observation review for the five scored cases remains pending; the r8
review approved public facts PBF-001..PBF-010 (PBF-011..PBF-015 retired with DC-06;
PBF-016 withheld).

Impact analysis for this continuation:
- Direct: this note, README link, existing GH-56 AI entry and curated summary.
- Potentially affected: owner input intake and A3 handoff preparation.
- Not touched: runner/tests, C1/C2 APIs, source fixtures, native tools, sandbox,
  oracle and scoring implementation.
- Risk: LOW for code; input authority remains unresolved.
- Change budget: 4 repository files for this continuation, within the existing
  envelope's 13-file total. No additional contract or Evidence semantics change.
  Source inventory, owner worksheet and verification receipts live outside the
  repository in the task delivery; source candidate paths stay host-side.

## Owner worksheet and missing data

The delivery contains `HOST-INPUT-REVIEW.json`, an object deliberately incompatible
with the freezer's five-element array. It has the six measured source candidates
(five remain scored candidates after the DC-06 retirement), five unassigned Y4 slots,
proposed unique context IDs, producer/review fields and
an unlocked experiment/budget section. Null means missing, not approved or empty.
Do not infer a DC-to-Y4 mapping from either list's order. Randomize and freeze the
neutral mapping later on the host; no mapping has been generated in this revision.

Yenefa must resolve these fields with the producer, without providing answers:

| Required input | Owner/producer supplies | Acceptance |
|---|---|---|
| Five scored sources (DC-01..DC-05) | Exact source snapshot locations, relative targets, release review | Five identified, UTF-8 round-trip exact, no case-answer cues in targets; DC-06 retired |
| Current observations | Public read/export route, exact producer version/command, raw export/log references | Reproducible from each source snapshot; current state only |
| Producer binding | Source and canonical-observation hashes recorded by that generation event, neutral producer ID | Both hashes match at freeze; generation provenance retained host-side |
| Public facts | Approved array and a host review ledger with source/version/page, applicability and actual verification state | No per-case patch/terminal state; missing verification remains explicit |
| Neutral identity | Five Y4 IDs and five unique context IDs (DC-06 retired); source mapping reviewed separately | No case labels or refusal hints sent to proposer |
| Experiment/budget | One version, max_ops, output-byte limit, output tokens and timeout; review reference | Locked before calls; no quota increase after a failure |

The checked system PATH did not resolve `kicad-cli` or `akcli`. Execution therefore
downloaded the official KiCad 10.0.6 lite AppImage to the task work directory and
ran it through the existing Ubuntu-22.04 WSL distribution. No system package
installation or native source edit was made. Archive hash, CLI version/help and
each actual export command are preserved in the r3 host delivery. A verified
short path resolves the AppImage loader's space-in-LD_PRELOAD warning; original
warning-bearing exports remain available as preparation history.

The source-location gap is now resolved. Identification of a source candidate is
not public release approval; the five scored candidates retain PENDING_OWNER_REVIEW
(DC-06 retired). Do not use old
`notes/m2-evidence-reset` current-board artifacts as five current observations.
Neither the full `m2-device-facts-v1.md` nor `datasheet_manifest.json` is an approved
public-facts array; no such substitution or content import was made here.

## Generation-time provenance

1. Producer reads a fixed source snapshot as bytes, decodes strict UTF-8 without
   newline/BOM removal, and records the source hash for the bytes actually read.
2. Producer uses the approved public read/export route on that same snapshot.
   Retain producer version, invocation, raw output, runtime and source identity.
3. Producer creates the current-observation object from that export. Its digest is
   `hash_bytes(canonical_json_bytes(current_observation))` using the repository's
   existing helper; ordinary pretty-printed JSON bytes are a different domain.
4. Producer records `{source_sha256, observation_sha256, producer_id}` for this
   event. Review metadata, paths and signatures stay outside the closed input
   object. The declared producer ID must fit the existing 1–64 character grammar.
5. If source bytes change during export or afterward before freeze, generate a
   new observation and declaration from a new fixed snapshot. Editing only the
   old declaration's source hash is invalid.

Inventory hashes from this task were measured during audit, **not** observation
generation. Never copy them into a newly invented declaration for an old export.
Fresh observations and declarations were subsequently produced by the r3
current-only producer from new reads and native exports. Hash agreement
does not prove semantic accuracy, authorized disclosure or independent C3 export.

## Construct the approved array after review

Use exactly the existing `INPUT_KEYS` documented in README. Read `source_utf8`
from bytes with strict UTF-8 decoding; do not use universal-newline text reading.
Check its UTF-8 encoding equals the reviewed source bytes before JSON serialization.
Copy the producer's already-recorded binding unchanged. Keep approvals and source
mapping in the host ledger, since extra fields in a public input are rejected.
Create `approved-public-inputs.json` only after owner review of all five scored
entries (DC-01..DC-05).

An empty `public_facts` array means no facts supplied. It is not a substitute for
the currently missing approved facts. `max_request_bytes` is the C1 Proposal
**output** byte ceiling (1–65536), not a size cap on the source/public package.
The other existing ranges are max_ops 1–8, output tokens 1–1000000, timeout
1–3600000 ms. These are schema bounds, not selected experiment quotas.
The external adapter must enforce tokens/timeout and accommodate the full input.

Then execute the existing `freeze` command twice into distinct new directories,
compare all five package byte hashes and the manifest byte hash, and load each
package against the independently retained pins. Preserve an incomplete directory
as failed; do not consume a batch without its final manifest. Human public-content
review is still needed because leak keywords do not detect answers in prose.

## A3 and J1 readiness

After public freeze and the separately locked run plan, A2 preserves every C/D
raw record, failed invocation and planned-but-not-run slot. The scorer handoff
must contain frozen packages/pins, plan and configuration, raw-result hashes,
verification receipts, exposure declarations and provider cost/time records.
Source identity mapping and producer evidence remain host/scorer-side, outside
proposer requests. Exact A3 rubric version, applicability and review belong to Percy.

A3/Percy independently scores A/B against private scoring assets, writing separate
results bound to raw-record hashes. A2 never imports those assets to make inputs,
does not rewrite raw records after scoring, and always keeps `scoring=NOT_RUN`.
C1 PASS and RECORDED are integrity/schema states, not repair correctness.

J1 needs actual input/run completeness, independent A/B results, costs, exposure
limits and a recorded owner decision. Current J1 evidence is limited to readiness
and blockers. No C/D comparison or native-success conclusion is available.

| Item | Current status |
|---|---|
| Five scored source candidates and byte inventory (DC-06 retired) | IDENTIFIED; 5/5 SCORED CANDIDATES MATCH BASELINE; PUBLIC REVIEW PENDING |
| Neutral source mapping | UNASSIGNED; RANDOMIZE/FREEZE LATER ON HOST |
| Current observation / producer binding candidates | GENERATED; OWNER REVIEW PENDING |
| Public facts | PBF-001..PBF-010 OWNER_APPROVED (r8); PBF-011..PBF-015 retired with DC-06; PBF-016 withheld |
| Five-case approved input array | NOT_CREATED |
| Real public freeze/rebuild | NOT_RUN |
| Formal C/D trajectories | NOT_RUN |
| Independent A/B scoring | NOT_RUN |
| J1 decision | NOT_MADE |
| C3–C6/native execution | NOT_RUN |

This implementation session read host implementation and historical experiment
excerpts, including case-specific evaluation text returned by a search. Its
prior-case and author exposure are YES; it is ineligible for a formal blind C run.
Those excerpts are not used to construct sources, observations, facts or scores.
Private fixture files and native repair-operation files were not directly read.

Full development-gate results belong to the current delivery receipts. Any #51
failure is retained truthfully and remains outside #56's modification scope.

## Current-only preparation utility

`produce_current_observations.py` exports a newly written exact source snapshot
through the caller's actual KiCad command prefix. It selects component identity,
value, footprint and net/node membership from that fresh XML; source paths,
timestamps and free-form export metadata are not projected. It does not invent
observations, execute proposals, infer intended topology or read facts/oracles.
Pins absent from the export have no asserted connection state. This is not full
C3 coverage or independent semantic qualification.

The r3 host candidate index binds each source to two generation directories,
raw XML/stdout/stderr, canonical observations and their generation-time bindings.
Each pair is byte-identical after canonical projection. No neutral Y4 mapping is
assigned by this utility. Review all candidate strings and source applicability
before creating an approved array.

Run the isolated producer checks from repository root:

```text
python -m unittest notes.y4.test_current_observation_producer -v
```

The nine synthetic checks cover CRLF preservation and canonical hashes, source
drift/stale pins, failed/timeout exports, immutable destinations, unsupported
hierarchy, malformed/empty XML, and duplicate/unknown connectivity entries.
The separate real-export audit verifies XML source identity, actual exporter
version, raw byte hashes and deterministic projection. Neither is an A/B score.
