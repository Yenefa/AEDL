"""Frozen public protocol for the AEDL EDD-001 sandbox runtime.

Shared contract between the sandbox orchestration (Agent H), the policy
engine (Agent M) and the trust store (Agent L). Frozen at the Wave 0
INTERFACE_READY checkpoint: consumers import from this module without
editing it, and drift is detected against the SHA-256 recorded in
notes/edd001-sandbox/agent-h-handoff.md.

Reason-code namespace (stable prefixes, see REASON_CODE_PREFIXES):

    POLICY_       deterministic design/execution policy
    EVIDENCE_     bundle or receipt validity
    EXECUTION_    candidate action result
    VERIFY_       independent verification result
    REPAIR_       repair limit or stall
    APPROVAL_     human approval boundary
    STATE_        lifecycle/checkpoint invariant

All tuples and mappings are serialized deterministically before hashing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, Union, runtime_checkable

JsonValue = Union[
    None,
    bool,
    int,
    float,
    str,
    list["JsonValue"],
    dict[str, "JsonValue"],
]

REASON_CODE_PREFIXES: tuple[str, ...] = (
    "POLICY_",
    "EVIDENCE_",
    "EXECUTION_",
    "VERIFY_",
    "REPAIR_",
    "APPROVAL_",
    "STATE_",
)


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
    # V2 (Wave 3) additions — additive, defaulted, V1-constructible.
    # Verified contract bundle reference fixed by the Trust sandbox via
    # validate_bundle (>= PARTIAL, not INVALID) and a receipt; policy must
    # not re-read contract files on its own.
    verified_bundle_sha256: str = ""
    verified_manifest_path: str = ""
    # Trusted actor identity and orchestrator-signed capability grants.
    # Capabilities are read from the orchestrator action ledger, never from
    # the requester's subject payload.
    actor: ActorIdentity | None = None
    capability_grants: tuple[CapabilityGrant, ...] = ()


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
    # V2 (Wave 3): which registered compiler/tool produced this result.
    actor_id: str = ""


@dataclass(frozen=True)
class VerificationResult:
    status: VerificationStatus
    candidate_id: str
    findings: tuple[Finding, ...] = ()
    # V2 (Wave 3): which registered verifier produced this result.
    actor_id: str = ""


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
    # V2 (Wave 3): candidate-bound human approval receipt. When present it
    # supersedes the bare approval_status for approval semantics; V1 callers
    # that only set approval_status keep working.
    approval_receipt: HumanApprovalReceipt | None = None


@dataclass(frozen=True)
class PromotionDecision:
    outcome: Outcome
    reason_code: str
    findings: tuple[Finding, ...] = ()


# ---------------------------------------------------------------------------
# V2 (Wave 3) trust additions. Purely additive: every V1 symbol above keeps
# its frozen shape, and every V2 field carries a V1-neutral default so V1
# constructions and consumers remain valid.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActorIdentity:
    """V2: who is requesting an action or produced a result.

    ``actor_kind`` is a descriptive role string (for example ``"compiler"``,
    ``"verifier"``, ``"agent"``, ``"human"``). It asserts nothing by itself:
    authority comes only from CapabilityGrant receipts recorded by the
    orchestrator.
    """

    actor_id: str
    actor_kind: str = ""
    run_id: str = ""


@dataclass(frozen=True)
class CapabilityGrant:
    """V2: orchestrator-signed capability grant backed by a recorded receipt.

    Example capability strings: ``"writer=compiler"``. Grants are read from
    the orchestrator action ledger — never from the requester's subject —
    and ``receipt_sha256`` pins each grant to its evidence receipt so policy
    verifies authority instead of trusting requester declarations.
    """

    run_id: str
    actor_id: str
    capability: str
    receipt_sha256: str = ""


@dataclass(frozen=True)
class HumanApprovalReceipt:
    """V2: human approval bound to one candidate content hash and one run.

    Replaces subject-carried approval declarations for promotion: the
    receipt pins who approved, when, in which role, and for which candidate
    bytes. ``decision`` distinguishes APPROVED from REJECTED outcomes.
    """

    run_id: str
    candidate_sha256: str
    decision: ApprovalStatus = ApprovalStatus.APPROVED
    approved_by: str = ""
    approver_role: str = "human_reviewer"
    approved_at: str = ""


@runtime_checkable
class PolicyPort(Protocol):
    def evaluate(self, request: PolicyRequest) -> PolicyDecision: ...


@runtime_checkable
class ExecutorPort(Protocol):
    def execute(self, request: PolicyRequest) -> ExecutionResult: ...


@runtime_checkable
class VerifierPort(Protocol):
    def verify(self, run_id: str, candidate_id: str, candidate_root: Path) -> VerificationResult: ...


@runtime_checkable
class RepairPort(Protocol):
    def propose(self, run_id: str, candidate_id: str, findings: tuple[Finding, ...]) -> PolicyRequest: ...


@runtime_checkable
class TrustPort(Protocol):
    def record(self, event: EvidenceEvent) -> EvidenceReceipt: ...
    def assess_promotion(self, request: PromotionRequest) -> PromotionDecision: ...
