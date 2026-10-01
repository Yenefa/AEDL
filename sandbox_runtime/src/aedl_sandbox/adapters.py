"""Wave 2 integration adapters (Agent H ownership).

This module is the single place that imports Agent M's and Agent L's public
exports, exactly as named in their handoffs:

    from aedl_sandbox.policy import SandboxPolicyEngine
    from aedl_sandbox.trust import FileTrustStore

Everything the orchestrator consumes goes through the frozen protocol ports.
Orchestrator-internal action names are mapped onto the engine's frozen action
vocabulary; M/L internals are never imported, edited, or reinterpreted.

All synthetic material here is TEST_ONLY: it proves orchestration mechanics
only and is never evidence about EDD-001 electronics. Nothing in this module
writes under real EDD evidence paths.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from aedl_sandbox.policy import (
    PolicyDocumentError,
    SandboxPolicyEngine,
)
from aedl_sandbox.policy.engine import SUBJECT_SPECS
from aedl_sandbox.trust import FileTrustStore

from .arh.budget import BudgetConfig, BudgetStop
from .arh.llm_repair_port import LLMRepairPort
from .arh.model_adapter import ModelAdapter
from .arh.schema import ContextInputs
from .arh.trajectory import TrajectoryRecorder

from .orchestrator import SandboxOrchestrator
from .protocol import (
    EvidenceStatus,
    ExecutionResult,
    Finding,
    JsonValue,
    Outcome,
    PolicyDecision,
    PolicyRequest,
    VerificationResult,
    VerificationStatus,
)
from .toolports import (
    BACKEND_IN_REPO_HIR,
    build_in_repo_ports,
    design_envelope,
)
from .workspace import CandidateWorkspace

TEST_ONLY_COMPONENT_MPN = "TEST-ONLY-LDO-3V3"
TEST_ONLY_COMPONENT_ROLE = "power_regulator"
TEST_ONLY_EVIDENCE_ID = "TEST_ONLY_EVIDENCE_1"
TEST_ONLY_COMPILER_ID = "test-only-compiler"
TEST_ONLY_VERIFIER_ID = "test-only-verifier"

# GH-114: the in-repo artifact class. These ids are registered in the policy
# document (see test_only_document) so the policy layer authorizes them; the
# implementations live in toolports.py and are wired into cli.py run-arh.
# Mapping a tool id to a backend is assembly-time knowledge, and this module is
# where the assembly lives.
IN_REPO_COMPILER_ID = "in-repo-hir"
IN_REPO_VERIFIER_ID = "in-repo-hir-verifier"
IN_REPO_TOOL_VERSION = "1.0.0"
IN_REPO_COVERAGE_ID = "STRUCTURE"

TEST_ONLY_NOTE = (
    "TEST_ONLY synthetic material for sandbox orchestration mechanics; "
    "not evidence about EDD-001 electronics and never placed under real "
    "EDD evidence paths."
)

DESIGN_ACTION_KEY = "design_action"
DESIGN_SUBJECT_KEY = "design_subject"

# V2 (Wave 3): the real EDD-001 sandbox bundle manifest that pins the frozen
# contracts. Policy contracts are only ever consumed through the validated
# manifest — never by reading the contract directory on its own authority.
REAL_EDD001_BUNDLE_MANIFEST = (
    Path("src") / "hardware" / "edd001-board" / "evidence" / "sandbox_bundle_manifest_v1.json"
)
# validate_bundle never writes receipts; the receipt root only exists so the
# FileTrustStore constructor is satisfied. It points at the gitignored runs
# area and is never created by validation.
_BUNDLE_VALIDATION_RECEIPT_SUBPATH = Path("sandbox_runtime") / ".runs" / "policy-bundle-validation"


class _FailClosedPolicyPort:
    """V2: policy port that answers BLOCKED for every request.

    Used when the trust-validated bundle cannot back a policy engine at all
    (manifest INVALID/missing, or contract drift against the validated
    manifest). It never reads contracts, never returns ALLOW, and carries the
    trust findings so callers see why the bundle was refused.
    """

    def __init__(self, reason_code: str, findings: tuple[Finding, ...]) -> None:
        self._reason_code = reason_code
        self._findings = findings

    @property
    def reason_code(self) -> str:
        """Why this port refuses everything. Public so an assembly that needs the
        domain's document can say WHICH refusal it hit (GH-114) instead of
        reporting an object that mysteriously lacks one."""
        return self._reason_code

    @property
    def findings(self) -> tuple[Finding, ...]:
        return self._findings

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        return PolicyDecision(
            outcome=Outcome.BLOCKED,
            reason_code=self._reason_code,
            findings=self._findings,
        )


class PolicyEnginePort:
    """PolicyPort adapter around SandboxPolicyEngine (public API only).

    Orchestrator-internal actions map onto the engine's frozen vocabulary:

        "preflight"         -> engine.preflight(run_id, candidate_root)
        "execute_candidate" -> engine.evaluate(design action carried by the
                               subject under DESIGN_ACTION_KEY/DESIGN_SUBJECT_KEY)

    Any other action is forwarded verbatim and is denied by the engine's
    closed vocabulary (POLICY_ACTION_NOT_ALLOWED); nothing defaults to ALLOW.
    A malformed design envelope is DENY/POLICY_SUBJECT_MALFORMED, never ALLOW.

    V2 (Wave 3): when the port was built over a trust-validated bundle it
    stamps every request with the validated manifest identity
    (``verified_bundle_sha256``/``verified_manifest_path``) so the engine can
    refuse to evaluate against any other bundle, and forwards the trusted
    ``actor``/``capability_grants`` from the orchestrator request into the
    adapted design action. Subject fields are never used as authority.
    """

    def __init__(
        self,
        engine: SandboxPolicyEngine,
        *,
        verified_bundle_sha256: str = "",
        verified_manifest_path: str = "",
    ) -> None:
        self._engine = engine
        self._verified_bundle_sha256 = verified_bundle_sha256
        self._verified_manifest_path = verified_manifest_path

    @property
    def engine(self) -> SandboxPolicyEngine:
        return self._engine

    @property
    def document(self) -> Any:
        """The parsed policy document this port evaluates against.

        Exposed because the tool registry is DERIVED from it (GH-114): a port
        that would not show its document would force the assembly to re-parse
        the same contracts, which is how two copies of a registry start to
        disagree.
        """
        return self._engine.document

    @property
    def verified_bundle_sha256(self) -> str:
        """V2: identity of the trust-validated bundle backing this port
        (empty when the port is not bound to a validated bundle)."""
        return self._verified_bundle_sha256

    @property
    def verified_manifest_path(self) -> str:
        return self._verified_manifest_path

    def _bind_verified_bundle(self, request: PolicyRequest) -> PolicyRequest:
        if not self._verified_bundle_sha256 or request.verified_bundle_sha256:
            return request
        return replace(
            request,
            verified_bundle_sha256=self._verified_bundle_sha256,
            verified_manifest_path=self._verified_manifest_path,
        )

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        request = self._bind_verified_bundle(request)
        if request.action == "preflight":
            return self._engine.preflight(
                request.run_id,
                request.candidate_root,
                verified_bundle_sha256=request.verified_bundle_sha256,
                verified_manifest_path=request.verified_manifest_path,
            )
        if request.action == "execute_candidate":
            return self._evaluate_design_action(request)
        return self._engine.evaluate(request)

    def _evaluate_design_action(self, request: PolicyRequest) -> PolicyDecision:
        subject = request.subject if isinstance(request.subject, Mapping) else None
        action = subject.get(DESIGN_ACTION_KEY) if subject else None
        design_subject = subject.get(DESIGN_SUBJECT_KEY) if subject else None
        if not isinstance(action, str) or not isinstance(design_subject, Mapping):
            return PolicyDecision(
                outcome=Outcome.DENY,
                reason_code="POLICY_SUBJECT_MALFORMED",
                findings=(
                    Finding(
                        code="POLICY_SUBJECT_MALFORMED",
                        message=(
                            "execute_candidate subject must carry a 'design_action' "
                            "string and a 'design_subject' mapping drawn from the "
                            "frozen action vocabulary"
                        ),
                        source="adapters",
                    ),
                ),
            )
        adapted = PolicyRequest(
            run_id=request.run_id,
            domain_id=request.domain_id,
            action_id=request.action_id,
            action=action,
            candidate_root=request.candidate_root,
            subject=dict(design_subject),
            # V2: trusted identity and capability grants come from the
            # orchestrator request, never from the requester's subject.
            actor=request.actor,
            capability_grants=request.capability_grants,
            verified_bundle_sha256=request.verified_bundle_sha256,
            verified_manifest_path=request.verified_manifest_path,
        )
        return self._engine.evaluate(adapted)


def build_real_edd001_policy_port(
    repo_root: Path | str,
) -> "PolicyEnginePort | _FailClosedPolicyPort":
    """Policy port over the real EDD-001 contracts, bound to the trust bundle.

    V2 (Wave 3): the engine is only ever built AFTER the bundle manifest has
    passed ``FileTrustStore.validate_bundle`` (Agent L, status not
    INVALID/MISSING; PARTIAL keeps its missing_requirements surfaced as the
    engine's own prerequisite blockers). The engine's contracts are then
    loaded strictly bound to the validated manifest — every contract file
    must be pinned by it and hash to the pinned value — and every request
    flowing through the port is stamped with the validated manifest identity.
    If the manifest is INVALID/missing, or contract bytes drift from the
    validated manifest, the port fails closed: every decision is BLOCKED
    (EVIDENCE_BUNDLE_INVALID) and no contract is read on the policy's own
    authority.
    """
    repo_root = Path(repo_root)
    manifest_path = repo_root / REAL_EDD001_BUNDLE_MANIFEST
    trust = FileTrustStore(repo_root, repo_root / _BUNDLE_VALIDATION_RECEIPT_SUBPATH)
    status, findings = trust.validate_bundle(manifest_path)
    if status in (EvidenceStatus.INVALID, EvidenceStatus.MISSING):
        return _FailClosedPolicyPort(
            "EVIDENCE_BUNDLE_INVALID",
            (
                Finding(
                    code="EVIDENCE_BUNDLE_INVALID",
                    message=(
                        f"real EDD-001 policy refuses to load: bundle manifest is {status.value}"
                    ),
                    source="adapters",
                    details={"manifest_path": str(manifest_path)},
                ),
            )
            + tuple(findings),
        )
    try:
        engine = SandboxPolicyEngine.for_edd001(repo_root, manifest_path=manifest_path)
    except PolicyDocumentError as exc:
        return _FailClosedPolicyPort(
            "EVIDENCE_BUNDLE_INVALID",
            (
                Finding(
                    code="EVIDENCE_BUNDLE_INVALID",
                    message=(
                        "real EDD-001 policy refuses to load: contracts do not match the "
                        f"validated bundle manifest ({exc})"
                    ),
                    source="adapters",
                    details={"manifest_path": str(manifest_path)},
                ),
            ),
        )
    return PolicyEnginePort(
        engine,
        verified_bundle_sha256=engine.verified_bundle_sha256,
        verified_manifest_path=str(manifest_path),
    )


def build_test_only_policy_port(repo_root: Path | str) -> PolicyEnginePort:
    """Policy port over a synthetic TEST_ONLY complete policy document.

    ``repo_root`` only anchors path containment for this engine; it can be the
    workspace root of a temporary run directory.
    """
    return PolicyEnginePort(
        SandboxPolicyEngine.from_document(test_only_document(), Path(repo_root))
    )


def build_trust_port(bundle_repo_root: Path | str, receipt_root: Path | str) -> FileTrustStore:
    """Trust port over Agent L's FileTrustStore.

    FileTrustStore already satisfies the frozen TrustPort structurally
    (record + assess_promotion); ``bundle_repo_root`` anchors bundle manifest
    repo_paths, ``receipt_root`` holds the append-only receipt ledger.
    """
    return FileTrustStore(Path(bundle_repo_root), Path(receipt_root))


def real_edd001_preflight(
    repo_root: Path | str,
    run_id: str = "preflight-cli",
    candidate_root: Path | str | None = None,
) -> PolicyDecision:
    """Run the real EDD-001 preflight (expected BLOCKED while required
    inputs are missing). The candidate root defaults to a run path under the
    repository so the engine's containment check holds.

    V2: goes through :func:`build_real_edd001_policy_port`, so the preflight
    only ever evaluates against the trust-validated bundle; a broken bundle
    yields the fail-closed BLOCKED port instead of a self-read engine."""
    repo_root = Path(repo_root)
    root = (
        Path(candidate_root)
        if candidate_root is not None
        else repo_root / "sandbox_runtime" / ".runs" / run_id
    )
    port = build_real_edd001_policy_port(repo_root)
    request = PolicyRequest(
        run_id=run_id,
        domain_id="EDD-001",
        action_id="preflight",
        action="preflight",
        candidate_root=root,
        subject={},
    )
    return port.evaluate(request)


def design_subject(
    action: str, subject: Mapping[str, JsonValue], **extra: Any
) -> dict[str, JsonValue]:
    """Envelope carrying a frozen-vocabulary design action through the
    orchestrator subject slot."""
    payload: dict[str, JsonValue] = {
        DESIGN_ACTION_KEY: action,
        DESIGN_SUBJECT_KEY: dict(subject),
    }
    payload.update(extra)
    return payload


def test_only_design_subject(attempt: int) -> dict[str, JsonValue]:
    """TEST_ONLY valid design action: selecting the synthetic component."""
    return design_subject(
        "DESIGN_SELECT_COMPONENT",
        {
            "mpn": TEST_ONLY_COMPONENT_MPN,
            "role": TEST_ONLY_COMPONENT_ROLE,
            "evidence_ids": [TEST_ONLY_EVIDENCE_ID],
        },
        fixture_attempt=attempt,
        test_only=True,
    )


def test_only_document() -> dict[str, JsonValue]:
    """Synthetic TEST_ONLY policy document with complete prerequisites so the
    workflow shell can reach execution. Mirrors the real EDD-001 pin shape
    (GPIO35/36/37 hard-forbidden) without reusing real contract content."""
    return {
        "schema_version": 1,
        "domain_id": "EDD-001",
        "board_id": "project-027-edd001",
        "allowed_components": [
            {
                "mpn": TEST_ONLY_COMPONENT_MPN,
                "role": TEST_ONLY_COMPONENT_ROLE,
                "required_evidence_ids": [TEST_ONLY_EVIDENCE_ID],
            },
        ],
        "pins": {
            "allowed": ["GPIO1", "GPIO2", "GPIO4"],
            "core_reserved": ["GPIO0"],
            "hard_forbidden": ["GPIO35", "GPIO36", "GPIO37"],
            "soft_reserved": ["GPIO43"],
            "rule_sources": {"GPIO36": "TEST_ONLY_PIN_PSRAM"},
        },
        "parameters": [],
        "file_policy": {
            "candidate_root_only": True,
            "direct_kicad_write": False,
            "allowed_artifact_kinds": [
                "hir",
                "netlist",
                "bom",
                "report",
                "kicad_sch",
                "kicad_pcb",
            ],
            "agent_forbidden_artifact_kinds": ["kicad_sch", "kicad_pcb"],
        },
        "network_policy": {"runtime_access": False},
        "shell_policy": {"arbitrary_shell": False},
        "tools": [],
        "compilers": [
            {
                "compiler_id": TEST_ONLY_COMPILER_ID,
                "compiler_version": "1.0.0",
                "output_kind": "kicad_sch",
                "required_coverage_ids": ["ERC"],
            },
            # GH-114: the artifact class this repository can ACTUALLY produce.
            # Registered so the policy layer authorizes it explicitly rather
            # than the ports deciding for themselves what they may run: the
            # design's declared output_kind is matched against these entries.
            # It is not a claim that in-repo-hir is an EDD-001 tool -- the real
            # EDD-001 document registers no compiler and no verifier at all.
            {
                "compiler_id": IN_REPO_COMPILER_ID,
                "compiler_version": IN_REPO_TOOL_VERSION,
                "output_kind": "hir",
                "required_coverage_ids": [IN_REPO_COVERAGE_ID],
            },
        ],
        "verifiers": [
            {
                "verifier_id": TEST_ONLY_VERIFIER_ID,
                "verifier_version": "1.0.0",
                "artifact_kind": "kicad_sch",
                "coverage_ids": ["ERC", "DRC", "CONTRACT"],
            },
            {
                "verifier_id": IN_REPO_VERIFIER_ID,
                "verifier_version": IN_REPO_TOOL_VERSION,
                "artifact_kind": "hir",
                "coverage_ids": [IN_REPO_COVERAGE_ID],
            },
        ],
        "prerequisites": {
            "required_contract_ids": ["EDD-001.CORE_BASE"],
            "required_evidence_ids": [TEST_ONLY_EVIDENCE_ID],
            "required_component_resolutions": [],
        },
        "available": {
            "contract_ids": ["EDD-001.CORE_BASE"],
            "evidence_ids": [TEST_ONLY_EVIDENCE_ID],
        },
        "active_rules": [
            {
                "rule_id": "TEST_ONLY_PIN_PSRAM",
                "source_contract_id": "test-only",
                "kind": "pin_constraint",
                "fingerprint": "0" * 64,
            },
        ],
    }


def materialize_test_only_bundle(bundle_dir: Path | str) -> Path:
    """Write a TEST_ONLY synthetic bundle (one VERIFIED_SOURCE marker file plus
    its manifest) into ``bundle_dir`` and return the manifest path. Writing is
    idempotent: identical bytes are produced on every call."""
    bundle_dir = Path(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    evidence = bundle_dir / "test_only_evidence.txt"
    evidence.write_text(
        "TEST_ONLY synthetic evidence marker; not a datasheet, not EDD-001 fact.\n",
        encoding="utf-8",
    )
    data = evidence.read_bytes()
    manifest = {
        "schema_version": 1,
        "domain_id": "EDD-001",
        "board_id": "project-027-edd001",
        "scope_status": "FROZEN",
        "evidence_status": "COMPLETE",
        "execution_status": "NOT_READY",
        "verification_status": "NOT_RUN",
        "approval_status": "PENDING",
        "files": [
            {
                "role": "test-only-evidence",
                "repo_path": "test_only_evidence.txt",
                "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "source_class": "VERIFIED_SOURCE",
                "required": True,
            }
        ],
        "mirror_sets": [],
        "missing_requirements": [],
        "tool_coverage": {
            "compilers": [TEST_ONLY_COMPILER_ID],
            "verifiers": [TEST_ONLY_VERIFIER_ID],
        },
        "notes": [TEST_ONLY_NOTE],
    }
    manifest_path = bundle_dir / "sandbox_bundle_manifest_v1.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return manifest_path


def bundle_manifest_sha256(manifest_path: Path | str) -> str:
    return hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest()


class _TestOnlyExecutor:
    """TEST_ONLY executor double: writes one artifact derived from the fixture
    attempt carried in the design subject. No hardware facts are produced."""

    def __init__(self) -> None:
        self.calls: list[PolicyRequest] = []

    def execute(self, request: PolicyRequest) -> ExecutionResult:
        self.calls.append(request)
        attempt = request.subject.get("fixture_attempt", 1)
        target = request.candidate_root / "artifact.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"fixture_attempt": attempt, "test_only": True}, sort_keys=True),
            encoding="utf-8",
        )
        return ExecutionResult(
            success=True,
            action_id=request.action_id,
            candidate_id=request.candidate_root.name,
            artifacts=(target,),
        )


class _TestOnlyVerifier:
    """TEST_ONLY verifier double: FAIL while the fixture attempt is below 2."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def verify(
        self, run_id: str, candidate_id: str, candidate_root: Path
    ) -> VerificationResult:
        self.calls.append(candidate_id)
        artifact = candidate_root / "artifact.json"
        attempt = 0
        if artifact.exists():
            attempt = int(
                json.loads(artifact.read_text(encoding="utf-8"))["fixture_attempt"]
            )
        if attempt >= 2:
            return VerificationResult(status=VerificationStatus.PASS, candidate_id=candidate_id)
        return VerificationResult(
            status=VerificationStatus.FAIL,
            candidate_id=candidate_id,
            findings=(
                Finding(
                    code="VERIFY_TEST_ONLY_ATTEMPT_INCOMPLETE",
                    message=f"fixture attempt {attempt} < 2",
                    source="test-only-verifier",
                    details={"attempt": attempt},
                ),
            ),
        )


class _TestOnlyRepair:
    """TEST_ONLY repair double: bumps the fixture attempt while keeping the
    design action valid, so the next round clears the policy gates."""

    def propose(self, run_id: str, candidate_id: str, findings) -> PolicyRequest:
        attempt = 1
        for finding in findings:
            if isinstance(finding.details, dict) and "attempt" in finding.details:
                attempt = int(finding.details["attempt"])
                break
        return PolicyRequest(
            run_id=run_id,
            domain_id="EDD-001",
            action_id=f"repair:{candidate_id}",
            action="repair",
            candidate_root=Path("."),
            subject=test_only_design_subject(attempt + 1),
        )


def build_test_only_fixture_orchestrator(
    workspace_root: Path | str,
    run_id: str,
    checkpointer: Any,
    *,
    max_repairs: int = 3,
    executor: Any = None,
    verifier: Any = None,
) -> SandboxOrchestrator:
    """Full real-adapter wiring for the TEST_ONLY repair_then_pass fixture.

    Policy and trust are the REAL M/L public implementations over synthetic
    TEST_ONLY material; only executor/verifier/repair are deterministic
    doubles. Everything lives under ``workspace_root`` (typically a temporary
    run directory), never under real EDD evidence paths.
    """
    workspace_root = Path(workspace_root)
    workspace = CandidateWorkspace(workspace_root)
    manifest = materialize_test_only_bundle(workspace_root / "test-only-bundle")
    return SandboxOrchestrator(
        policy=build_test_only_policy_port(workspace_root),
        executor=executor if executor is not None else _TestOnlyExecutor(),
        verifier=verifier if verifier is not None else _TestOnlyVerifier(),
        repair=_TestOnlyRepair(),
        trust=build_trust_port(
            workspace_root / "test-only-bundle", workspace_root / "receipts"
        ),
        workspace=workspace,
        run_id=run_id,
        domain_id="EDD-001",
        bundle_hash=bundle_manifest_sha256(manifest),
        subject=test_only_design_subject(1),
        max_repairs=max_repairs,
        checkpointer=checkpointer,
    )


# ---------------------------------------------------------------------------
# ARH live wiring (GH-112)
#
# Everything above this line is TEST_ONLY or a public M/L port builder. What
# follows is the assembly that makes the ARH repair agent reachable from a real
# process at all. Until it existed, nothing outside `arh/` referenced the
# harness and the only RepairPort the CLI could reach was `_TestOnlyRepair`.
# ---------------------------------------------------------------------------

#: The action prefix a repair PROPOSAL may name. The orchestrator's own actions
#: (PREFLIGHT / COMPILE_HIR / VERIFY_ARTIFACT / ...) are dispatched by
#: `adapters` on requests it builds itself; a proposal naming one of those would
#: be asking the agent to drive machinery it has no authority over, so they are
#: not offered. Offering them is not a wider capability -- each is individually
#: policy-gated -- but it is a wider SURFACE than the contract intends, and the
#: cheap thing is to not build it.
PROPOSAL_ACTION_PREFIX = "DESIGN_"


def derive_proposal_action_schema() -> dict[str, list[str]]:
    """The design actions a proposal may name, derived from `SUBJECT_SPECS`.

    DERIVED, never hand-written, and that is the whole point.
    `repair_agent` refuses any action absent from `action_schema` AND any action
    absent from `SUBJECT_SPECS`; if the two were maintained separately, the
    failure mode is a proposal the model was TOLD to emit that is then rejected
    100% of the time -- a silent, total rejection rate that looks exactly like a
    model that cannot follow instructions. One source, so they cannot disagree.

    Field names come from the same table that validates them, so the advertised
    shape and the enforced shape are the same object.
    """
    return {
        action: [name for name, _ in SUBJECT_SPECS[action]]
        for action in sorted(SUBJECT_SPECS)
        if action.startswith(PROPOSAL_ACTION_PREFIX)
    }


class ArhContextInputs:
    """Projects run state into `ContextInputs` for one repair round (RFC 3.2, D6).

    A PROJECTION, deliberately not an `engine.document` dump: the harness is
    handed the fields the round needs and nothing else, so there is no path by
    which the full contract document -- and everything it carries -- reaches a
    prompt.

    `allowlist` and `subject_frozen` are supplied by the OPERATOR at assembly
    time, not derived from anything the model or the run can influence. That
    asymmetry is the point: the model chooses WHICH action to propose and WITH
    WHAT arguments, and is confined to the choices the operator declared. An
    allowlist the agent could widen would be no allowlist at all.
    """

    def __init__(
        self,
        *,
        workspace: CandidateWorkspace,
        domain_id: str,
        subject: Mapping[str, Any],
        allowlist: Mapping[str, Any],
        contract_ref: Mapping[str, Any] | None = None,
        fingerprint_state: Mapping[str, Any] | None = None,
        verification_ref: Mapping[str, Any] | None = None,
    ) -> None:
        if not isinstance(allowlist, Mapping):
            raise TypeError("allowlist must be a mapping")
        # Fail closed AT ASSEMBLY rather than at the first proposal. An empty
        # allowed_components is accepted by `repair_agent` and then rejects every
        # component proposal, so a misconfigured allowlist would present as a
        # model that cannot follow instructions. Refusing here names the cause.
        components = allowlist.get("allowed_components")
        if not components:
            raise ValueError(
                "allowlist.allowed_components is empty, so every component "
                "proposal would fail closed. Declare the components this run may "
                "select at assembly time; the harness will not invent them."
            )
        if not allowlist.get("evidence_ids"):
            raise ValueError(
                "allowlist.evidence_ids is empty, so no proposal could cite "
                "evidence and the harness requires cited evidence to be a subset "
                "of the available set. Declare this run's evidence ids."
            )
        self._workspace = workspace
        self._domain_id = domain_id
        self._subject = dict(subject)
        self._allowlist = dict(allowlist)
        self._contract_ref = dict(contract_ref or {})
        self._fingerprint_state = dict(fingerprint_state or {})
        self._verification_ref = dict(verification_ref or {})

    def __call__(
        self, run_id: str, candidate_id: str, findings: tuple[Finding, ...]
    ) -> ContextInputs:
        return ContextInputs(
            domain_id=self._domain_id,
            candidate_root=self._workspace.candidate_root(run_id, candidate_id),
            contract_ref=dict(self._contract_ref),
            subject_frozen=dict(self._subject),
            fingerprint_state=dict(self._fingerprint_state),
            verification_ref={**self._verification_ref, "run_id": run_id, "candidate_id": candidate_id},
            allowlist=dict(self._allowlist),
            action_schema=derive_proposal_action_schema(),
        )


def build_arh_orchestrator(
    workspace_root: Path | str,
    run_id: str,
    checkpointer: Any,
    *,
    repo_root: Path | str,
    model: ModelAdapter,
    subject: Mapping[str, Any],
    allowlist: Mapping[str, Any],
    policy: Any,
    executor: Any,
    verifier: Any,
    trust: Any = None,
    max_repairs: int = 3,
    budget: BudgetStop | None = None,
    run_dir: Path | str | None = None,
    domain_id: str = "EDD-001",
    investigation_resources: Mapping[str, Any] | None = None,
    specialist_models: Mapping[str, ModelAdapter] | None = None,
) -> SandboxOrchestrator:
    """Assemble a REAL orchestrator whose repair port is the ARH agent.

    The port set is chosen HERE, at assembly time, and nowhere else. That is
    RFC 2.5 N8: the agent influences the CONTENT of a proposal and nothing
    about which implementations exist. `SandboxOrchestrator` additionally
    isinstance-checks every port it is handed, so a misassembled port is a
    TypeError at construction rather than a surprise mid-run.

    `executor` and `verifier` are REQUIRED and have NO default. The doubles
    `_TestOnlyExecutor` / `_TestOnlyVerifier` exist and would make this function
    convenient, and that is exactly why they are not wired in here: a live
    repair round that silently executed and verified against test doubles would
    report success it never earned. Supplying them is the caller's explicit
    choice, so the gap is visible in the signature instead of buried in a
    default. They are a separate piece of work.

    `model` is passed in rather than constructed here, for the same reason plus
    one: the adapter's transport is a required argument with no default, so a
    caller who passes a real transport has chosen real I/O and a caller who
    passes a fake one cannot accidentally make a request. No network call
    happens in this function.
    """
    workspace_root = Path(workspace_root)
    workspace = CandidateWorkspace(workspace_root)
    run_dir = Path(run_dir) if run_dir is not None else workspace_root / "run" / run_id
    # N4: the recorder owns its own directory under the run dir. It is never the
    # receipt root, so a trajectory can never be read back as a verdict.
    trajectory = TrajectoryRecorder(run_dir, run_id)
    adaptive = None
    if specialist_models and investigation_resources is None:
        raise ValueError("specialists require operator-registered investigation resources")
    if investigation_resources is not None:
        from .arh.adaptive import AdaptiveRepairAgent
        adaptive = AdaptiveRepairAgent(
            model, resources=investigation_resources,
            experts=specialist_models or {}, trajectory=trajectory,
        )
    repair = LLMRepairPort(
        model=model,
        inputs_provider=ArhContextInputs(
            workspace=workspace,
            domain_id=domain_id,
            subject=subject,
            allowlist=allowlist,
        ),
        trajectory=trajectory,
        budget=budget if budget is not None else BudgetStop(BudgetConfig()),
        agent=adaptive,
    )
    return SandboxOrchestrator(
        policy=policy,
        executor=executor,
        verifier=verifier,
        repair=repair,
        # The trust port is tied to the domain the run evaluates against:
        # receipt_root always lives under the run, but bundle_repo_root is the
        # operator's chosen domain root. A synthetic policy paired with the real
        # evidence tree (or the reverse) would be a mixed-binding run.
        trust=(
            trust
            if trust is not None
            else build_trust_port(repo_root, workspace_root / "receipts")
        ),
        workspace=workspace,
        run_id=run_id,
        domain_id=domain_id,
        bundle_hash="",
        subject=subject,
        max_repairs=max_repairs,
        checkpointer=checkpointer,
        stall_recovery=adaptive.schedule_second_opinion if adaptive is not None else None,
    )


# ---------------------------------------------------------------------------
# GH-114: the real executor/verifier pair.
# ---------------------------------------------------------------------------

#: Tool id -> backend name. The policy document says WHICH tools this domain
#: authorizes; this says HOW each is run. A registered tool absent from here
#: still resolves to NO backend and refuses at assembly by name, which is the
#: fail-closed direction.
IN_REPO_TOOL_BACKENDS: Mapping[str, str] = {
    IN_REPO_COMPILER_ID: BACKEND_IN_REPO_HIR,
    IN_REPO_VERIFIER_ID: BACKEND_IN_REPO_HIR,
}


def build_in_repo_tool_ports(
    engine: Any,
    *,
    design_action: str,
    design_subject: Mapping[str, Any],
    output_kind: str | None = None,
):
    """Assemble the real executor/verifier pair over an engine's OWN registry.

    The engine's document is the only source of the tool set: nothing here names
    a compiler or verifier the policy has not registered. Assembly failures raise
    ToolNotResolved, so an unauthorized artifact class is a configuration error
    rather than a mid-round surprise.

    The selection logic itself lives in toolports.build_in_repo_ports so that the
    CLI and the tests assemble the pair through ONE function; two assembly sites
    is how a test starts exercising a shape the runtime never uses.
    """
    return build_in_repo_ports(
        engine,
        design_action=design_action,
        design_subject=design_subject,
        backend_for_tool=IN_REPO_TOOL_BACKENDS,
        output_kind=output_kind,
    )
