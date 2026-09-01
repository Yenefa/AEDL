# EDD-001 Sandbox Runtime V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first executable AEDL Engineering Design Sandbox skeleton for EDD-001: a deny-by-default, resumable, bounded multi-round workflow that separates design policy, execution capability, and evidence trust while keeping the incomplete real EDD-001 bundle truthfully blocked.

**Architecture:** Use LangGraph only as the outer state-machine/checkpoint/human-interrupt shell. Put all engineering judgments in deterministic AEDL ports. Divide implementation into three non-overlapping ownership blocks: H owns the public protocol and orchestration, M owns policy evaluation, and L owns trust/evidence. Work proceeds in two waves: H first freezes the public interface; then H/M/L work in parallel; finally H alone wires adapters and runs integration tests.

**Tech Stack:** Isolated CPython 3.11 managed by uv, `langgraph==1.2.11`, `langgraph-checkpoint-sqlite==3.1.1`, Python standard-library `unittest`, dataclasses, JSON/JSON Schema documents, SHA-256, SQLite, existing EDD-001 JSON contracts.

---

## 0. Delivery boundary

This plan implements a runtime skeleton and executable contracts. It does not generate a production KiCad board in this batch.

The frozen definition is in:

- `docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md`

The current EDD-001 inputs are read-only:

- `gates/contracts/edd001_core_base_contract_v1.json`
- `gates/contracts/edd001_pin_constraints_v1.json`
- `gates/contracts/edd001_usb_contract_v1.json`
- `src/hardware/edd001-board/evidence/contracts/edd001_core_base_contract_v1.json`
- `src/hardware/edd001-board/evidence/contracts/edd001_pin_constraints_v1.json`
- `src/hardware/edd001-board/evidence/contracts/edd001_usb_contract_v1.json`

Known blockers that must remain visible:

- no EDD-001 POWER contract;
- `src/hardware/edd001-board/evidence/datasheets/` is empty;
- no registered deterministic EDD-001 compiler;
- no registered independent read-back verifier;
- current `gates/run_gates.py` has no EDD-001 scope;
- the existing M2 schematic contract validator is not the schema for these EDD-001 contracts.

Therefore the real EDD-001 preflight result for this batch is `BLOCKED`, not `PASS`.

## 1. Non-negotiable rules for all three agents

- [ ] Read the repository `AGENTS.md`, the approved design spec, and this plan before editing.
- [ ] Run `git status --short --branch` and `git branch --show-current` before editing.
- [ ] Preserve every pre-existing dirty-worktree change.
- [ ] Do not use `reset`, `checkout`, `clean`, amend, rebase, or history rewriting.
- [ ] Do not commit or push unless the human separately authorizes it.
- [ ] Use test-first development: add a failing focused test, confirm RED for the expected reason, make the smallest implementation, then confirm GREEN.
- [ ] Use only the exclusive paths assigned below.
- [ ] Treat all existing EDD-001 contracts and evidence as read-only inputs.
- [ ] Do not download datasheets, invent hashes, fill missing engineering facts, or create a fake complete EDD bundle.
- [ ] Do not run `gates/run_gates.py`; it can rewrite evidence and is outside this batch.
- [ ] Do not modify M2 hardware, BOM, delivery, manufacturing release, or existing spike directories.
- [ ] Do not claim physical validation, manufacturability, or production readiness.
- [ ] End with `git status --short`, a task-owned diff review, exact tests run, limitations, and `PENDING_HUMAN_REVIEW`.

### Shared forbidden paths

No worker may modify these paths in this batch:

```text
AGENTS.md
NOTICE
delivery/**
docs/HANDOFF.md
docs/compliance/**
docs/competition/**
gates/run_gates.py
gates/contracts/edd001_*_contract_v1.json
src/hardware/edd001-board/evidence/contracts/**
src/hardware/m2-board/**
spike/**
spike_stage2/**
```

The coordinating human or lead reviewer owns later governance updates. Worker handoff notes are the only worker-authored audit summaries in this batch.

## 2. Work waves and merge order

```text
Wave 0: Agent H freezes protocol.py and reports INTERFACE_READY
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
Wave 1:  Agent H      Agent M      Agent L
         graph/core   policy       trust/evidence
            └────────────┼────────────┘
                         ▼
Wave 2: Agent H alone adds adapters and integration tests
                         ▼
                 Human review only
```

Rules:

1. Agent M and Agent L must not begin implementation until Agent H reports `INTERFACE_READY` and names the hash of `sandbox_runtime/src/aedl_sandbox/protocol.py`.
2. After that signal, Agent M and Agent L import the frozen protocol but never edit it.
3. Agent H must not inspect or depend on M/L private internals. It may import only their declared public exports.
4. Agent H performs Wave 2 only after M and L each publish a handoff note and all their focused tests pass.
5. Any required public-interface change after `INTERFACE_READY` stops integration and returns to human review; no worker silently changes the shared protocol.

## 3. Exclusive ownership map

| Difficulty | Worker | Exclusive write ownership | Public deliverable |
|---|---|---|---|
| High | Agent H | `sandbox_runtime/pyproject.toml`, `sandbox_runtime/uv.lock`, `sandbox_runtime/.gitignore`, `sandbox_runtime/src/aedl_sandbox/__init__.py`, `protocol.py`, `state.py`, `workspace.py`, `orchestrator.py`, `cli.py`, `adapters.py`, `sandbox_runtime/tests/orchestrator/**`, `notes/edd001-sandbox/agent-h-handoff.md` | frozen protocol, LangGraph runtime, candidate workspace, CLI, final adapters |
| Medium | Agent M | `sandbox_runtime/src/aedl_sandbox/policy/**`, `sandbox_runtime/contracts/domain_policy_schema_v1.json`, `sandbox_runtime/tests/policy/**`, `notes/edd001-sandbox/agent-m-handoff.md` | `SandboxPolicyEngine` |
| Low | Agent L | `sandbox_runtime/src/aedl_sandbox/trust/**`, `sandbox_runtime/contracts/bundle_manifest_schema_v1.json`, `sandbox_runtime/contracts/evidence_event_schema_v1.json`, `sandbox_runtime/tests/trust/**`, `src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json`, `notes/edd001-sandbox/agent-l-handoff.md` | `FileTrustStore` and truthful EDD-001 bundle manifest |

No path appears in more than one row. Test fixtures must live under the owning worker's test directory.

## 4. Frozen public protocol

Agent H creates this interface before parallel work. The other workers consume it without editing it.

Required enums and values:

```python
class Outcome(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    BLOCKED = "BLOCKED"

class LifecycleStatus(str, Enum):
    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    REJECTED = "REJECTED"
    PROMOTED = "PROMOTED"
    FROZEN = "FROZEN"

class VerificationStatus(str, Enum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"

class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"

class EvidenceStatus(str, Enum):
    MISSING = "MISSING"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"
    INVALID = "INVALID"
```

Required immutable dataclasses:

```python
@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    source: str
    details: Mapping[str, JsonValue] = field(default_factory=dict)

@dataclass(frozen=True)
class PolicyRequest:
    run_id: str
    domain_id: str
    action_id: str
    action: str
    candidate_root: Path
    subject: Mapping[str, JsonValue]

@dataclass(frozen=True)
class PolicyDecision:
    outcome: Outcome
    reason_code: str
    findings: tuple[Finding, ...] = ()

@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    action_id: str
    candidate_id: str
    artifacts: tuple[Path, ...] = ()
    findings: tuple[Finding, ...] = ()

@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    candidate_id: str
    findings: tuple[Finding, ...] = ()

@dataclass(frozen=True)
class EvidenceEvent:
    run_id: str
    candidate_id: str
    event_type: str
    input_hashes: Mapping[str, str]
    payload: Mapping[str, JsonValue]

@dataclass(frozen=True)
class EvidenceReceipt:
    event_hash: str
    run_id: str
    candidate_id: str
    valid: bool

@dataclass(frozen=True)
class PromotionRequest:
    run_id: str
    candidate_id: str
    candidate_hash: str
    verification_status: VerificationStatus
    approval_status: ApprovalStatus
    evidence_status: EvidenceStatus

@dataclass(frozen=True)
class PromotionDecision:
    outcome: Outcome
    reason_code: str
    findings: tuple[Finding, ...] = ()
```

`JsonValue` is a recursive JSON-compatible type alias. All tuples and mappings are serialized deterministically before hashing.

Required ports:

```python
class PolicyPort(Protocol):
    def evaluate(self, request: PolicyRequest) -> PolicyDecision: ...

class ExecutorPort(Protocol):
    def execute(self, request: PolicyRequest) -> ExecutionResult: ...

class VerifierPort(Protocol):
    def verify(self, run_id: str, candidate_id: str, candidate_root: Path) -> VerificationResult: ...

class RepairPort(Protocol):
    def propose(self, run_id: str, candidate_id: str, findings: tuple[Finding, ...]) -> PolicyRequest: ...

class TrustPort(Protocol):
    def record(self, event: EvidenceEvent) -> EvidenceReceipt: ...
    def assess_promotion(self, request: PromotionRequest) -> PromotionDecision: ...
```

Stable reason-code namespace:

```text
POLICY_*       deterministic design/execution policy
EVIDENCE_*     bundle or receipt validity
EXECUTION_*    candidate action result
VERIFY_*       independent verification result
REPAIR_*       repair limit or stall
APPROVAL_*     human approval boundary
STATE_*        lifecycle/checkpoint invariant
```

## 5. Agent H packet — High difficulty

Copy the entire block below to the high-difficulty Agent.

### Prompt for Agent H

```text
You own the HIGH-difficulty EDD-001 Sandbox orchestration block.

Repository:
C:\Users\fuker\Desktop\workspace\project-027-autonomous-hardware-agent

Goal:
Create an isolated Python 3.11 Sandbox runtime, freeze the shared public protocol, implement a resumable LangGraph workflow with bounded deterministic repair, confine all writes to content-addressed candidate workspaces, and finally integrate the public policy/trust adapters supplied by the other two agents. This is a runtime skeleton, not a production PCB generator.

Before work:
1. Read repository AGENTS.md completely.
2. Read docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md completely.
3. Read docs/superpowers/plans/2026-09-01-edd001-sandbox-runtime-v1.md completely.
4. Run git status --short --branch and git branch --show-current.
5. Preserve all pre-existing uncommitted changes.

Exclusive write ownership:
- sandbox_runtime/pyproject.toml
- sandbox_runtime/uv.lock
- sandbox_runtime/.gitignore
- sandbox_runtime/src/aedl_sandbox/__init__.py
- sandbox_runtime/src/aedl_sandbox/protocol.py
- sandbox_runtime/src/aedl_sandbox/state.py
- sandbox_runtime/src/aedl_sandbox/workspace.py
- sandbox_runtime/src/aedl_sandbox/orchestrator.py
- sandbox_runtime/src/aedl_sandbox/cli.py
- sandbox_runtime/src/aedl_sandbox/adapters.py
- sandbox_runtime/tests/orchestrator/**
- notes/edd001-sandbox/agent-h-handoff.md

Do not edit any other path. You are not alone in the worktree. Never revert, overwrite, format, stage, or otherwise disturb another agent's files.

Wave 0 — interface freeze:
1. Create sandbox_runtime/pyproject.toml with:
   - requires-python >=3.11,<3.12
   - langgraph==1.2.11
   - langgraph-checkpoint-sqlite==3.1.1
   - hatchling build backend
   - package path src/aedl_sandbox
2. Use uv python install 3.11 and uv sync --project sandbox_runtime. Do not change system Python 3.9.
3. Implement protocol.py exactly as section 4 of the plan specifies.
4. Add protocol contract tests for enum values, frozen dataclasses, JSON-compatible fields, and runtime-checkable ports.
5. Run the focused tests.
6. Calculate SHA-256 for protocol.py.
7. Write notes/edd001-sandbox/agent-h-handoff.md with status INTERFACE_READY, the SHA-256, public symbols, test command, and result. Stop at this checkpoint long enough for the human to dispatch M and L.

Wave 1 — your independent core:
1. Implement SandboxState as a typed state carrying run/domain IDs, bundle hash, candidate ID/root/hash, phase, repair_count, max_repairs, current findings, previous finding fingerprint, stall count, policy/execution/verification/promotion results, evidence receipts, pending human action, and terminal reason.
2. Implement CandidateWorkspace:
   - workspace root is supplied explicitly;
   - create run/<run_id>/candidate/<candidate_id>/ only;
   - reject absolute escape, .. escape, symlink escape, and writes outside candidate root;
   - never mutate the frozen baseline;
   - derive candidate ID/hash from canonical inputs;
   - repeated action_id returns the existing recorded result instead of repeating side effects.
3. Implement LangGraph nodes and conditional edges:
   preflight -> create_candidate -> execute -> verify
   verify PASS -> human_review -> promote_or_reject
   verify FAIL -> detect_stall -> repair -> preflight
   any DENY/BLOCKED -> terminal
   repeated finding fingerprint or max repairs -> terminal
4. Put human interrupt before promotion. A resumed node must not recreate the candidate or repeat executor effects.
5. Use SQLite checkpointing through langgraph-checkpoint-sqlite. The database path must be under a caller-supplied run directory, never a global user directory.
6. Implement deterministic fake ports in tests. Do not call an LLM and do not generate hardware facts.
7. Add a CLI that supports:
   python -m aedl_sandbox.cli preflight --repo-root <path> --domain EDD-001
   python -m aedl_sandbox.cli run-fixture --scenario repair_then_pass --run-root <path>
   The preflight command may initially use a test double until Wave 2 adapters are added.

Mandatory RED/GREEN tests:
- path traversal and symlink escape are rejected;
- direct KiCad write requests never reach ExecutorPort;
- DENY and BLOCKED terminate without candidate execution;
- one FAIL can route through repair and then PASS;
- identical finding fingerprints twice trigger REPAIR_STALLED;
- max repair count triggers REPAIR_LIMIT_REACHED;
- checkpoint resume does not repeat an action_id side effect;
- human interrupt occurs before promotion;
- rejection leaves the candidate unpromoted;
- approved synthetic fixture can promote only after PASS and complete evidence.

Wave 2 — integration, only after M and L handoffs exist:
1. Read notes/edd001-sandbox/agent-m-handoff.md and agent-l-handoff.md.
2. Verify protocol.py still has the INTERFACE_READY hash. If it changed, stop with STATE_PROTOCOL_DRIFT.
3. In adapters.py only, import these public exports:
   from aedl_sandbox.policy import SandboxPolicyEngine
   from aedl_sandbox.trust import FileTrustStore
4. Do not import private modules or edit M/L files.
5. Wire real EDD-001 preflight. It must return BLOCKED because the POWER contract, datasheets, compiler registry, and independent verifier coverage are incomplete.
6. Wire a TEST_ONLY synthetic complete bundle for the full repair/resume integration test. It must be visibly marked TEST_ONLY and must not live under real EDD evidence.
7. Run all sandbox_runtime tests and the two CLI smoke commands.

Safety and scope:
- No network calls in runtime or tests.
- No arbitrary shell execution.
- No direct hand-editing of .kicad_sch/.kicad_pcb.
- No gates/run_gates.py.
- No M2 changes, BOM changes, datasheet downloads, manufacturing release, commit, or push.
- Never turn missing evidence into defaults.

Finish by writing notes/edd001-sandbox/agent-h-handoff.md with:
- Status: PENDING_HUMAN_REVIEW
- Owned files changed
- Protocol hash
- Architecture implemented
- Tests actually run and exact results
- Real EDD-001 preflight outcome and reason codes
- Synthetic scenario outcome
- Commands not run
- Known limitations
- Git branch, HEAD, commit status, push status

Return a concise handoff; do not claim completion without fresh test output.
```

### Agent H task checklist

#### H0 — Freeze the dependency environment and protocol

- [ ] Add `sandbox_runtime/pyproject.toml` and `.gitignore`.
- [ ] Add failing protocol tests.
- [ ] Run `uv run --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/orchestrator -p "test_protocol.py" -v` and confirm RED because the protocol does not exist.
- [ ] Implement `protocol.py` and public exports.
- [ ] Re-run the focused test and confirm GREEN.
- [ ] Generate `sandbox_runtime/uv.lock` with `uv sync --project sandbox_runtime`.
- [ ] Record `INTERFACE_READY` and the protocol SHA-256 in the H handoff note.

#### H1 — Candidate workspace

- [ ] Add failing tests for traversal, symlink escape, frozen-baseline mutation, deterministic IDs, and repeated `action_id`.
- [ ] Implement `CandidateWorkspace` with resolved-path containment checks and an action journal.
- [ ] Confirm the focused workspace suite is GREEN.

#### H2 — LangGraph state machine

- [ ] Add failing routing tests for `ALLOW`, `DENY`, `BLOCKED`, verify pass/fail, repair, and terminal conditions.
- [ ] Implement typed state and graph nodes.
- [ ] Add stable finding fingerprinting using canonical JSON plus SHA-256.
- [ ] Confirm no DENY/BLOCKED path calls ExecutorPort.

#### H3 — Persistence and human approval

- [ ] Add a failing resume test using a temporary SQLite file.
- [ ] Add a failing test proving interrupt precedes promotion.
- [ ] Implement SQLite checkpoint setup and interrupt/resume.
- [ ] Confirm executor side-effect count remains one across resume.

#### H4 — Public adapters and final integration

- [ ] Verify both M/L handoff notes and the frozen protocol hash.
- [ ] Add adapter tests before adapter implementation.
- [ ] Wire `SandboxPolicyEngine` and `FileTrustStore` in `adapters.py`.
- [ ] Confirm real EDD-001 preflight is `BLOCKED` with explicit missing prerequisites.
- [ ] Confirm the TEST_ONLY fixture completes one repair loop, pauses for human review, resumes, and promotes only after approval.
- [ ] Run the complete sandbox suite and CLI smoke tests.

---

## 6. Agent M packet — Medium difficulty

Copy the entire block below to the medium-difficulty Agent after H reports `INTERFACE_READY`.

### Prompt for Agent M

```text
You own the MEDIUM-difficulty EDD-001 deterministic policy block.

Repository:
C:\Users\fuker\Desktop\workspace\project-027-autonomous-hardware-agent

Goal:
Implement the deny-by-default Design Sandbox and Execution Sandbox policy kernel. Convert the current frozen EDD-001 contracts into deterministic ALLOW/DENY/BLOCKED decisions without changing those contracts and without using an LLM.

Start condition:
Do not implement until notes/edd001-sandbox/agent-h-handoff.md reports INTERFACE_READY. Record the stated SHA-256 of sandbox_runtime/src/aedl_sandbox/protocol.py and verify it yourself. Import protocol.py but never edit it.

Before work:
1. Read repository AGENTS.md completely.
2. Read docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md completely.
3. Read docs/superpowers/plans/2026-09-01-edd001-sandbox-runtime-v1.md completely.
4. Read all three current gates/contracts/edd001_*_contract_v1.json files completely as read-only inputs.
5. Run git status --short --branch and git branch --show-current.

Exclusive write ownership:
- sandbox_runtime/src/aedl_sandbox/policy/**
- sandbox_runtime/contracts/domain_policy_schema_v1.json
- sandbox_runtime/tests/policy/**
- notes/edd001-sandbox/agent-m-handoff.md

Do not edit any other path. You are not alone in the worktree. Never revert or overwrite another agent's changes.

Required public API:

from aedl_sandbox.policy import SandboxPolicyEngine

SandboxPolicyEngine.for_edd001(repo_root: Path) -> SandboxPolicyEngine
SandboxPolicyEngine.from_document(document: Mapping[str, JsonValue], repo_root: Path) -> SandboxPolicyEngine
SandboxPolicyEngine.evaluate(request: PolicyRequest) -> PolicyDecision
SandboxPolicyEngine.preflight(run_id: str, candidate_root: Path) -> PolicyDecision

Supported action vocabulary and required subject fields:

PREFLIGHT
  {}

DESIGN_SELECT_COMPONENT
  {"mpn": str, "role": str, "evidence_ids": [str]}

DESIGN_ASSIGN_PIN
  {"pin": str, "function": str, "approval_status": str}

DESIGN_SET_PARAMETER
  {"parameter_id": str, "value": number|string, "unit": str, "evidence_ids": [str]}

COMPILE_HIR
  {"compiler_id": str, "compiler_version": str, "output_kind": str, "coverage_ids": [str]}

VERIFY_ARTIFACT
  {"verifier_id": str, "verifier_version": str, "artifact_kind": str, "coverage_ids": [str]}

TOOL_EXECUTE
  {"tool_id": str, "tool_version": str, "capability": str}

FILE_WRITE
  {"path": str, "artifact_kind": str, "writer": "agent"|"compiler"}

NETWORK_ACCESS
  {"destination": str, "purpose": str}

SHELL_EXECUTE
  {"command_class": str}

Malformed subjects and unknown actions are DENY, not exceptions and not permissive defaults.

Normalized policy document schema:
- schema_version: 1
- domain_id: EDD-001
- board_id: project-027-edd001
- allowed_components: exact MPN records with role and required evidence IDs
- pins: allowed, core_reserved, hard_forbidden, soft_reserved
- parameters: ID, type, unit, inclusive bounds or exact allowed values
- file_policy: candidate_root_only, direct_kicad_write=false, allowed artifact kinds
- network_policy: runtime_access=false
- shell_policy: arbitrary_shell=false
- tools: exact tool ID/version/capability records
- compilers: exact compiler ID/version/output/coverage records
- verifiers: exact verifier ID/version/artifact/coverage records
- prerequisites: required contract IDs and required evidence IDs

for_edd001 must load the three current contracts and normalize them. It must not treat source URLs as locally verified evidence. It must honor superseded_by in edd001_pin_constraints_v1.json: CORE_BASE is authoritative for the superseded pin/reset/boot/decoupling/antenna rules, while USB_DIFFERENTIAL and POWER_SOURCE_SEPARATION remain active.

Required decision semantics:

1. Closed world:
   - unknown component MPN -> DENY / POLICY_COMPONENT_NOT_ALLOWED
   - unknown pin or pin absent from agent_gpio_pool -> DENY / POLICY_PIN_NOT_ALLOWED
   - unknown parameter or unknown action -> DENY

2. Known but incomplete:
   - exact allowed component whose required local datasheet evidence is missing -> BLOCKED / EVIDENCE_COMPONENT_SOURCE_MISSING
   - compiler declared by the request but absent from registry -> BLOCKED / POLICY_COMPILER_NOT_REGISTERED
   - verifier coverage absent -> BLOCKED / POLICY_VERIFIER_COVERAGE_MISSING
   - unresolved GENERIC component at COMPILE_HIR -> BLOCKED / POLICY_COMPONENT_RESOLUTION_REQUIRED
   - missing POWER contract -> BLOCKED / EVIDENCE_REQUIRED_CONTRACT_MISSING

3. Pin rules:
   - GPIO35/GPIO36/GPIO37 -> DENY / POLICY_PIN_HARD_FORBIDDEN
   - GPIO0/GPIO3/GPIO19/GPIO20/GPIO45/GPIO46 -> DENY / POLICY_PIN_CORE_RESERVED for agent assignment
   - GPIO43/GPIO44 without a separately validated human approval -> BLOCKED / APPROVAL_PIN_OVERRIDE_REQUIRED
   - pins in agent_gpio_pool may ALLOW only when the request is otherwise complete
   - do not infer GPIO26-GPIO34 availability from model memory

4. Execution rules:
   - NETWORK_ACCESS always DENY / POLICY_NETWORK_DISABLED for formal runtime
   - SHELL_EXECUTE always DENY / POLICY_ARBITRARY_SHELL_DISABLED
   - unregistered tool/version/capability -> DENY / POLICY_TOOL_NOT_ALLOWED
   - FILE_WRITE outside resolved candidate_root -> DENY / POLICY_PATH_ESCAPE
   - FILE_WRITE of kicad_sch/kicad_pcb with writer=agent -> DENY / POLICY_DIRECT_KICAD_WRITE
   - registered deterministic compiler writing within candidate_root may ALLOW only if all coverage/evidence prerequisites are complete

5. Outcome precedence:
   - a known violation produces DENY even if another prerequisite is missing;
   - otherwise any unproven prerequisite produces BLOCKED;
   - ALLOW only when every applicable rule is satisfied.

Real EDD-001 preflight must report a single PolicyDecision with deterministic, sorted findings for at least:
- EVIDENCE_REQUIRED_CONTRACT_MISSING: POWER contract
- EVIDENCE_COMPONENT_SOURCE_MISSING: local datasheets
- POLICY_COMPILER_NOT_REGISTERED
- POLICY_VERIFIER_COVERAGE_MISSING
Outcome: BLOCKED.

Test requirements:
- table-driven tests for every action and outcome above;
- contract order does not change decisions or finding order;
- duplicate conflicting authoritative rules fail closed;
- malformed JSON, wrong board_id, wrong schema_version, missing required keys, and unknown rule shapes fail closed;
- superseded rules do not silently re-enter the active set;
- source URL alone never satisfies evidence;
- string tricks such as ../, case changes, whitespace, or prefix MPN matches do not bypass exact matching;
- a TEST_ONLY complete policy document can ALLOW one safe GPIO assignment and one deterministic compiler action;
- the real EDD-001 preflight remains BLOCKED.

Implementation constraints:
- Python standard library only inside policy code.
- No network, subprocess, shell, EDA write, datasheet download, or hardware-file modification.
- Never return ALLOW on parser error or unknown input.
- Never use basename/prefix/substring matching for MPN, pin, tool, or path authorization.
- Keep findings stable and sorted by (code, source, message).
- Expose only SandboxPolicyEngine from aedl_sandbox.policy.__init__.

Test-first sequence:
1. Add tests for malformed policy documents and closed-world component/pin handling; run and confirm RED because policy package is absent.
2. Implement strict document normalization and validation; confirm focused GREEN.
3. Add execution-policy tests; confirm RED.
4. Implement exact tool/path/network/shell/compiler/verifier decisions; confirm GREEN.
5. Add real EDD preflight and supersession tests; confirm RED.
6. Implement for_edd001 and preflight; confirm GREEN with real outcome BLOCKED.
7. Run all sandbox_runtime/tests/policy tests through uv.

Use `uv run --frozen --project sandbox_runtime ...` for every test command. Do not run `uv sync` and do not edit `pyproject.toml`, `uv.lock`, or the shared environment; Agent H owns dependency resolution.

Do not run gates/run_gates.py. Do not commit or push.

Finish by writing notes/edd001-sandbox/agent-m-handoff.md with:
- Status: PENDING_HUMAN_REVIEW
- Verified protocol SHA-256
- Owned files changed
- Public API and exact reason codes
- Tests actually run and exact results
- Real EDD-001 preflight outcome/findings
- Commands not run
- Known limitations
- Git branch, HEAD, commit status, push status

Return only evidence-backed results.
```

### Agent M task checklist

#### M1 — Normalize the closed design domain

- [ ] Add failing schema/normalization tests.
- [ ] Create `domain_policy_schema_v1.json` with `additionalProperties: false` at every object level except explicitly free-form evidence metadata.
- [ ] Implement strict normalization of the three read-only EDD contracts.
- [ ] Prove the `superseded_by` declaration prevents older pin rules from regaining authority.
- [ ] Confirm deterministic ordering and exact-match behavior.

#### M2 — Design policy evaluator

- [ ] Add table-driven RED tests for component, pin, and parameter requests.
- [ ] Implement closed-world evaluation and stable reason codes.
- [ ] Confirm hard-forbidden/core-reserved requests are `DENY` and incomplete known items are `BLOCKED`.
- [ ] Confirm no generic component reaches compile authorization.

#### M3 — Execution policy evaluator

- [ ] Add RED tests for network, shell, path, tool, compiler, verifier, and direct KiCad writes.
- [ ] Implement resolved-path containment and exact registry matching.
- [ ] Confirm a known violation takes precedence over missing prerequisites.

#### M4 — Real EDD-001 preflight

- [ ] Add a RED test expecting all four blocker classes.
- [ ] Implement `for_edd001` and `preflight`.
- [ ] Confirm the real bundle is `BLOCKED`, findings are sorted, and no output evidence is rewritten.
- [ ] Run the full policy suite and write the M handoff note.

---

## 7. Agent L packet — Low difficulty

Copy the entire block below to the low-difficulty Agent after H reports `INTERFACE_READY`.

### Prompt for Agent L

```text
You own the LOW-difficulty EDD-001 Trust Sandbox block.

Repository:
C:\Users\fuker\Desktop\workspace\project-027-autonomous-hardware-agent

Goal:
Implement deterministic bundle/hash/evidence receipts and promotion gating. Produce a truthful manifest for the six current EDD-001 contract files. Do not fill missing evidence and do not modify any contract.

Start condition:
Do not implement until notes/edd001-sandbox/agent-h-handoff.md reports INTERFACE_READY. Verify the recorded SHA-256 of sandbox_runtime/src/aedl_sandbox/protocol.py. Import protocol.py but never edit it.

Before work:
1. Read repository AGENTS.md completely.
2. Read docs/superpowers/specs/2026-09-01-edd001-engineering-design-sandbox-design.md completely.
3. Read docs/superpowers/plans/2026-09-01-edd001-sandbox-runtime-v1.md completely.
4. Read the three gates/contracts/edd001_* files and their three mirrored evidence/contracts files as read-only inputs.
5. Run git status --short --branch and git branch --show-current.

Exclusive write ownership:
- sandbox_runtime/src/aedl_sandbox/trust/**
- sandbox_runtime/contracts/bundle_manifest_schema_v1.json
- sandbox_runtime/contracts/evidence_event_schema_v1.json
- sandbox_runtime/tests/trust/**
- src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json
- notes/edd001-sandbox/agent-l-handoff.md

Do not edit any other path. You are not alone in the worktree. Never revert or overwrite another agent's changes.

Required public API:

from aedl_sandbox.trust import FileTrustStore

FileTrustStore(repo_root: Path, receipt_root: Path)
FileTrustStore.sha256_file(path: Path) -> str
FileTrustStore.validate_bundle(manifest_path: Path) -> tuple[EvidenceStatus, tuple[Finding, ...]]
FileTrustStore.record(event: EvidenceEvent) -> EvidenceReceipt
FileTrustStore.assess_promotion(request: PromotionRequest) -> PromotionDecision

Source classes:
- VERIFIED_SOURCE: a local frozen source whose exact file hash and provenance record are present
- UNVERIFIED_SOURCE: a local or referenced source not yet fully validated
- MODEL_PRIOR: model memory; cannot satisfy engineering evidence
- HUMAN_INPUT: human scope/approval input; does not replace a datasheet for engineering facts

Canonical JSON algorithm:
json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

All file paths stored in manifests and receipts must be repository-relative POSIX paths. Resolve every path and reject absolute paths, .. escape, symlink escape, missing required files, duplicate paths, negative sizes, malformed SHA-256, and unknown enum values.

bundle_manifest_schema_v1.json must require:
- schema_version: exactly 1
- domain_id: exactly EDD-001 for the real manifest
- board_id: project-027-edd001
- scope_status: DRAFT|FROZEN
- evidence_status: MISSING|PARTIAL|COMPLETE|INVALID
- execution_status: NOT_READY|READY|RUNNING|COMPLETE|FAILED|BLOCKED
- verification_status: NOT_RUN|PASS|FAIL|BLOCKED
- approval_status: NOT_REQUIRED|PENDING|APPROVED|REJECTED
- files: non-empty array of role, repo_path, size_bytes, sha256, source_class, required
- mirror_sets: authoritative_path, mirror_path, expected_equal=true
- missing_requirements: ID, kind, reason_code, description
- tool_coverage: compiler IDs and verifier IDs
- notes: string array
Use additionalProperties=false throughout except a clearly named metadata object.

The real src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json must state exactly:
- schema_version = 1
- domain_id = EDD-001
- board_id = project-027-edd001
- scope_status = FROZEN
- evidence_status = PARTIAL
- execution_status = NOT_READY
- verification_status = NOT_RUN
- approval_status = PENDING
- all six existing contract files, each with freshly computed size_bytes and full lowercase SHA-256
- three mirror sets showing gates/contracts file versus evidence/contracts copy
- empty compiler and verifier coverage arrays
- missing requirements for, at minimum:
  EDD001_POWER_CONTRACT
  ESP32_S3_WROOM_1_N8R8_DATASHEET
  AP63203WU_7_DATASHEET
  TYPE_C_31_M_12_DRAWING
  USBLC6_2SC6_DATASHEET
- no hash, path, or filename for a missing file
- notes that source URLs inside contracts are references, not frozen local evidence

Do not add generated_at unless it is derived from a caller-supplied deterministic value; a wall-clock timestamp would make repeat runs non-reproducible.

Bundle validation semantics:
- exact file size/hash match and mirror equality are required;
- a required file missing or a hash/size mismatch -> EvidenceStatus.INVALID;
- structurally valid bundle with declared missing_requirements -> EvidenceStatus.PARTIAL;
- COMPLETE requires no missing requirements, non-empty compiler/verifier coverage, and all required files VERIFIED_SOURCE;
- MODEL_PRIOR or HUMAN_INPUT cannot satisfy a required engineering-source record;
- findings are stable and sorted by (code, source, message).

Evidence-event storage:
- content-address one JSON file per event under receipt_root/<run_id>/<event_hash>.json;
- event_hash covers the canonical event, including input_hashes;
- require input_hashes to include candidate_sha256 for verification and promotion events;
- recording the same event twice is idempotent and returns the same valid receipt;
- if an existing event_hash path has different bytes, return valid=false and preserve the existing file;
- never overwrite or delete an existing receipt;
- a changed candidate hash makes prior verification/promotion receipts stale.

Promotion semantics:
- verification_status=FAIL -> DENY / VERIFY_FAILED
- verification_status=BLOCKED or NOT_RUN -> BLOCKED / VERIFY_NOT_COMPLETE
- evidence_status=INVALID -> DENY / EVIDENCE_INVALID
- evidence_status=MISSING or PARTIAL -> BLOCKED / EVIDENCE_INCOMPLETE
- approval_status=PENDING -> BLOCKED / APPROVAL_REQUIRED
- approval_status=REJECTED -> DENY / APPROVAL_REJECTED
- candidate hash mismatch against the latest valid verification receipt -> DENY / EVIDENCE_STALE
- ALLOW only for PASS + COMPLETE + APPROVED + current candidate hash with valid receipts

Required tests:
- canonical key order yields the same event hash;
- a one-byte semantic change yields a different hash;
- NaN and non-JSON values are rejected;
- path escape, symlink escape, duplicates, malformed hashes, and unknown fields fail closed;
- size/hash mismatch and mirror mismatch produce INVALID;
- declared missing requirements produce PARTIAL;
- no URL-only entry becomes VERIFIED_SOURCE;
- repeated identical event recording is idempotent;
- an attempted receipt collision does not overwrite the first receipt;
- changed candidate content invalidates the earlier receipt;
- every promotion truth-table row above returns the exact outcome/reason code;
- real EDD manifest validates as PARTIAL, not COMPLETE and not INVALID;
- a TEST_ONLY complete fixture can validate as COMPLETE.

Test-first sequence:
1. Add canonicalization and bundle validation tests; run and confirm RED because the trust package is absent.
2. Implement canonical JSON, hashing, containment, and strict manifest parsing; confirm GREEN.
3. Add evidence receipt append-only/idempotency tests; confirm RED.
4. Implement FileTrustStore.record; confirm GREEN.
5. Add promotion truth-table tests; confirm RED.
6. Implement assess_promotion; confirm GREEN.
7. Compute the six real file sizes/hashes and create the truthful real manifest.
8. Run all trust tests through uv and independently recompute the six hashes once more.

Use `uv run --frozen --project sandbox_runtime ...` for every test command. Do not run `uv sync` and do not edit `pyproject.toml`, `uv.lock`, or the shared environment; Agent H owns dependency resolution.

No network, subprocess, shell, EDA modification, datasheet download, gates/run_gates.py, commit, or push.

Finish by writing notes/edd001-sandbox/agent-l-handoff.md with:
- Status: PENDING_HUMAN_REVIEW
- Verified protocol SHA-256
- Owned files changed
- Public API and promotion truth table
- Six file sizes/SHA-256 values and mirror comparison result
- Tests actually run and exact results
- Real manifest status
- Commands not run
- Known limitations
- Git branch, HEAD, commit status, push status

Return only evidence-backed results.
```

### Agent L task checklist

#### L1 — Canonical bundle validation

- [ ] Add failing canonicalization, path, schema, size/hash, and mirror tests.
- [ ] Create both strict JSON schema documents.
- [ ] Implement canonical JSON and repository containment.
- [ ] Confirm malformed or altered evidence fails closed.

#### L2 — Append-only evidence receipts

- [ ] Add RED tests for idempotency, collisions, and candidate-hash changes.
- [ ] Implement one immutable file per event hash.
- [ ] Confirm an existing receipt is never overwritten.

#### L3 — Promotion truth table

- [ ] Add every status combination listed in the prompt as a table-driven test.
- [ ] Implement exact `ALLOW`/`DENY`/`BLOCKED` promotion decisions.
- [ ] Confirm only `PASS + COMPLETE + APPROVED + current hash` can ALLOW.

#### L4 — Truthful current EDD-001 manifest

- [ ] Compute sizes and SHA-256 for all six current contract files.
- [ ] Create `sandbox_bundle_manifest_v1.json` without timestamps or invented missing-file hashes.
- [ ] Confirm all three mirror pairs are byte-identical.
- [ ] Confirm validation returns `PARTIAL` and the expected missing requirements.
- [ ] Run the full trust suite and write the L handoff note.

---

## 8. Manual dispatch sequence

The human distributes work in this exact order. These are still three workers; Agent H has two checkpoints because it owns the only shared interface and final wiring.

### Dispatch 1 — H interface freeze

Send Agent H the complete H prompt. Require it to stop after H0 and return `INTERFACE_READY` plus the protocol hash.

Acceptance before continuing:

- [ ] `protocol.py` exists and its focused tests pass.
- [ ] H handoff contains a full lowercase SHA-256.
- [ ] `git diff -- sandbox_runtime/src/aedl_sandbox/protocol.py` contains only H-owned work.
- [ ] No existing EDD/M2/shared-governance file changed.

### Dispatch 2 — Parallel Wave 1

After `INTERFACE_READY`:

1. Tell the same Agent H: `协议已冻结。按原计划继续 H1-H3；暂不做 H4，等 M/L 交接。`
2. Send Agent M the complete M prompt.
3. Send Agent L the complete L prompt.

H, M, and L may now run in parallel because their write sets are disjoint.

### Dispatch 3 — H integration

After M and L each report `PENDING_HUMAN_REVIEW` and focused GREEN tests, tell Agent H:

```text
M/L 已交接。先验证 protocol.py 仍等于 INTERFACE_READY SHA-256，并阅读两份 handoff。
若协议漂移或任一聚焦测试未通过，停止并报告；否则只在 H 独占文件中执行 H4 适配器接线、
全量 sandbox_runtime 测试、真实 EDD-001 BLOCKED preflight、TEST_ONLY 多轮循环与恢复测试。
禁止修改 M/L 文件，禁止修改现有 EDD 合同或任何 M2/制造文件，禁止 commit/push。
```

## 9. Cross-agent handoff contract

Each handoff note must contain these headings in this order:

```text
# EDD-001 Sandbox <H|M|L> Handoff

Status
Protocol SHA-256
Owned files changed
Public API delivered
Tests actually run
Observed results
Not run
Known limitations
Git state
Human review
```

Required values:

- `Status`: `INTERFACE_READY` only for H0; otherwise `PENDING_HUMAN_REVIEW`.
- `Tests actually run`: exact command and fresh result; never a planned command.
- `Not run`: explicitly name integration, hardware, EDA, or physical checks not performed.
- `Git state`: branch, HEAD, staged status, commit status, push status.
- `Human review`: always `PENDING_HUMAN_REVIEW`.

## 10. Final integration scenarios

Agent H must implement and run these scenarios in temporary directories. No fixture may be written into the real EDD evidence directory.

| ID | Input | Expected route | Required final result |
|---|---|---|---|
| INT-01 | real EDD-001 manifest/contracts | preflight -> terminal | `BLOCKED`; executor calls = 0 |
| INT-02 | unknown component | policy -> terminal | `DENY/POLICY_COMPONENT_NOT_ALLOWED`; executor calls = 0 |
| INT-03 | GPIO36 assignment | policy -> terminal | `DENY/POLICY_PIN_HARD_FORBIDDEN`; executor calls = 0 |
| INT-04 | network capability | policy -> terminal | `DENY/POLICY_NETWORK_DISABLED`; executor calls = 0 |
| INT-05 | Agent direct KiCad write | policy -> terminal | `DENY/POLICY_DIRECT_KICAD_WRITE`; executor calls = 0 |
| INT-06 | missing verifier coverage | policy -> terminal | `BLOCKED/POLICY_VERIFIER_COVERAGE_MISSING`; executor calls = 0 |
| INT-07 | TEST_ONLY fail-once fixture | execute -> verify fail -> repair -> execute -> verify pass -> interrupt | waits for human; repair_count = 1 |
| INT-08 | resume INT-07 with approval | resume -> trust -> promote | promoted candidate; no repeated prior action side effect |
| INT-09 | resume INT-07 with rejection | resume -> reject | candidate retained but not promoted |
| INT-10 | repeated same finding | repair loop | `REPAIR_STALLED` before exceeding bound |
| INT-11 | changing findings through limit | repair loop | `REPAIR_LIMIT_REACHED` |
| INT-12 | mutate candidate after verification | promotion assessment | `DENY/EVIDENCE_STALE` |
| INT-13 | write outside candidate root | workspace/policy | `DENY/POLICY_PATH_ESCAPE`; no outside file exists |
| INT-14 | restart process at human interrupt | SQLite resume | same run/candidate/action IDs; executor side-effect count unchanged |

The TEST_ONLY fixture proves orchestration mechanics only. It is not evidence that EDD-001 electronics are correct.

## 11. Required commands and expected evidence

Development environment setup, run by Agent H:

```powershell
uv python install 3.11
uv sync --project sandbox_runtime
uv run --project sandbox_runtime python -c "import sys; print(sys.version); assert sys.version_info[:2] == (3, 11)"
```

The system Python is intentionally untouched. Package installation is a development-time action outside the formal offline runtime.

Focused suites:

```powershell
uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/orchestrator -p "test_*.py" -v
uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/policy -p "test_*.py" -v
uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests/trust -p "test_*.py" -v
```

Final suite:

```powershell
uv run --frozen --project sandbox_runtime python -m unittest discover -s sandbox_runtime/tests -p "test_*.py" -v
```

CLI smoke checks:

```powershell
uv run --frozen --project sandbox_runtime python -m aedl_sandbox.cli preflight --repo-root . --domain EDD-001
uv run --frozen --project sandbox_runtime python -m aedl_sandbox.cli run-fixture --scenario repair_then_pass --run-root sandbox_runtime/.runs/manual-smoke
```

Expected CLI semantics:

- Real preflight exits with a documented non-zero blocked code and prints structured JSON whose outcome is `BLOCKED`.
- The fixture pauses at human review rather than auto-approving itself.
- Resume requires an explicit approval or rejection value.

Read-only final hygiene:

```powershell
git diff --check
git status --short --branch
git diff --name-only
```

The reviewer compares changed names against the ownership table. Any path outside the three owned sets is a scope violation to investigate, not something to auto-revert.

## 12. Acceptance criteria

### Architecture

- [ ] LangGraph is only the outer workflow shell; it contains no hard-coded hardware truth.
- [ ] Policy and trust decisions are deterministic, directly unit-tested, and usable without LangGraph.
- [ ] Candidate workspace writes are confined and idempotent.
- [ ] Public interface did not drift after parallel implementation began.

### Fail-closed behavior

- [ ] Unknown actions, parts, pins, tools, schemas, and fields never default to `ALLOW`.
- [ ] `DENY` is used for known violations; `BLOCKED` is used for unproven prerequisites.
- [ ] Real EDD-001 remains blocked for the documented missing inputs.
- [ ] No source URL or model prior is treated as a verified local datasheet.

### Multi-round repair

- [ ] One deterministic failure can route through repair and re-verification.
- [ ] Repair count is bounded.
- [ ] Repeated finding fingerprints trigger stall detection.
- [ ] Process restart resumes from SQLite without duplicating side effects.
- [ ] Human approval happens before promotion and cannot be self-issued by the Agent.

### Evidence and state

- [ ] All six current contract files have fresh size/hash records.
- [ ] All three mirror pairs are byte-identical.
- [ ] Receipts are content-addressed, append-only, and candidate-hash-bound.
- [ ] Candidate mutation invalidates prior verification evidence.
- [ ] Scope, evidence, execution, verification, and approval states remain separate.

### Repository safety

- [ ] No worker changed existing EDD contracts, M2, BOM, delivery, manufacturing release, compliance files, or spike directories.
- [ ] No worker committed or pushed without separate authorization.
- [ ] `git diff --check` is clean for task-owned changes.
- [ ] Every worker handoff is `PENDING_HUMAN_REVIEW`.

## 13. Explicit non-goals and next milestone

This batch does not implement:

- a KiCad HIR compiler;
- an independent KiCad read-back parser;
- ERC/DRC or SPICE adapters;
- live LLM repair;
- OS/container-level hostile-process isolation;
- network source intake inside formal runtime;
- POWER contract or datasheet ingestion;
- production Gerber/BOM/CPL generation;
- manufacturing approval or physical-board evidence.

The next milestone begins only after this runtime skeleton passes human review:

1. Freeze EDD-001 POWER contract and the required local datasheet bundle.
2. Define a minimal HIR for CORE + POWER + USB + CORE_BASE.
3. Add a deterministic KiCad compiler adapter.
4. Add an independent final-file parser and contract verifier.
5. Run the first sandboxed schematic loop until ERC plus semantic contracts pass.
6. Submit that generated schematic for professional human circuit review.

That milestone is the first useful prototype threshold: simulation/static verification runs through the loop, while manufacturability and physical correctness remain separate future goals.

## 14. Open-source intake boundary

The dependency freeze for this plan was checked against the package indexes on 2026-09-01:

- LangGraph `1.2.11`, MIT, Python `>=3.10`: https://pypi.org/project/langgraph/
- LangGraph SQLite checkpoint `3.1.1`, MIT, Python `>=3.10`: https://pypi.org/project/langgraph-checkpoint-sqlite/

The host currently has only Python 3.9, so the runtime uses an isolated uv-managed Python 3.11 environment. The dependency files are owned by Agent H and do not alter existing gate execution.

Architectural lessons from reviewed repositories may be reimplemented from documented behavior, but workers must not copy source from AGPL or license-unclear projects into this batch. Adding the actual dependencies later triggers the repository third-party register and fusion-map review; this planning-only batch does not claim those integrations are already implemented.
