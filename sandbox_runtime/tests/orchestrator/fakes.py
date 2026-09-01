"""Deterministic fake ports for Agent H orchestrator tests.

No LLM calls, no network, no hardware facts. Every port records its calls
so tests can prove that denied or blocked runs never reach the executor.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, Iterable, Mapping

from aedl_sandbox.protocol import (
    ApprovalStatus,
    EvidenceEvent,
    EvidenceReceipt,
    ExecutionResult,
    Finding,
    Outcome,
    PolicyDecision,
    PolicyRequest,
    PromotionDecision,
    PromotionRequest,
    VerificationResult,
    VerificationStatus,
)


class ScriptedPolicy:
    def __init__(self, decide: Callable[[PolicyRequest], PolicyDecision]):
        self._decide = decide
        self.calls: list[PolicyRequest] = []

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        self.calls.append(request)
        return self._decide(request)


def allow_all(request: PolicyRequest) -> PolicyDecision:
    return PolicyDecision(outcome=Outcome.ALLOW, reason_code="POLICY_TEST_ALLOW")


def deny_direct_kicad(request: PolicyRequest) -> PolicyDecision:
    if request.subject.get("action") == "write_kicad":
        return PolicyDecision(
            outcome=Outcome.DENY,
            reason_code="POLICY_DIRECT_KICAD_WRITE",
            findings=(
                Finding(
                    code="POLICY_DIRECT_KICAD_WRITE",
                    message="direct KiCad file writes are forbidden",
                    source="test-policy",
                ),
            ),
        )
    return allow_all(request)


class CountingExecutor:
    def __init__(self) -> None:
        self.calls: list[PolicyRequest] = []

    def execute(self, request: PolicyRequest) -> ExecutionResult:
        self.calls.append(request)
        target = request.candidate_root / "artifact.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {"action_id": request.action_id, "subject": dict(request.subject)},
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return ExecutionResult(
            success=True,
            action_id=request.action_id,
            candidate_id=request.candidate_root.name,
            artifacts=(target,),
        )


class ScriptedExecutor:
    """Executor double whose result is request-derived except for declared
    overrides (Wave 3 fail-closed regression double: failed executions,
    identity mismatches, artifact escapes)."""

    def __init__(self, **overrides) -> None:
        self.calls: list[PolicyRequest] = []
        self._overrides = overrides

    def execute(self, request: PolicyRequest) -> ExecutionResult:
        self.calls.append(request)
        target = request.candidate_root / "artifact.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
        values: dict = dict(
            success=True,
            action_id=request.action_id,
            candidate_id=request.candidate_root.name,
            artifacts=(target,),
        )
        values.update(self._overrides)
        return ExecutionResult(**values)


class ForeignCandidateVerifier:
    """Verifier double that returns a well-formed result stamped with a
    foreign candidate_id (trust-chain break double for Wave 3)."""

    def __init__(
        self,
        status: VerificationStatus = VerificationStatus.PASS,
        reported_candidate_id: str = "cand-foreign",
    ) -> None:
        self._status = status
        self._reported = reported_candidate_id
        self.calls: list[str] = []

    def verify(self, run_id: str, candidate_id: str, candidate_root: Path) -> VerificationResult:
        self.calls.append(candidate_id)
        return VerificationResult(status=self._status, candidate_id=self._reported)


class ScriptedVerifier:
    def __init__(self, results: Iterable[VerificationResult], actor_id: str = ""):
        self._results = list(results)
        self._actor_id = actor_id
        self.calls: list[tuple[str, str, Path]] = []

    def verify(self, run_id: str, candidate_id: str, candidate_root: Path) -> VerificationResult:
        self.calls.append((run_id, candidate_id, candidate_root))
        template = self._results.pop(0)
        return VerificationResult(
            status=template.status,
            candidate_id=candidate_id,
            findings=template.findings,
            actor_id=self._actor_id,
        )


def fail_result(code: str, details: Mapping | None = None) -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.FAIL,
        candidate_id="",
        findings=(
            Finding(
                code=code,
                message=f"scripted failure {code}",
                source="test-verifier",
                details=dict(details or {}),
            ),
        ),
    )


def blocked_result(code: str) -> VerificationResult:
    return VerificationResult(
        status=VerificationStatus.BLOCKED,
        candidate_id="",
        findings=(Finding(code=code, message=f"scripted block {code}", source="test-verifier"),),
    )


def pass_result() -> VerificationResult:
    return VerificationResult(status=VerificationStatus.PASS, candidate_id="")


class IncrementRepair:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Finding, ...]]] = []
        self._round = 0

    def propose(self, run_id: str, candidate_id: str, findings) -> PolicyRequest:
        self.calls.append((candidate_id, tuple(findings)))
        self._round += 1
        return PolicyRequest(
            run_id=run_id,
            domain_id="TEST",
            action_id=f"repair-{self._round}",
            action="repair",
            candidate_root=Path("."),
            subject={"action": "fixture", "round": self._round},
        )


class StrictTrust:
    def __init__(
        self,
        receipts_valid: bool = True,
        invalid_event_types: Iterable[str] = (),
    ) -> None:
        self.receipts_valid = receipts_valid
        self.invalid_event_types = frozenset(invalid_event_types)
        self.events: list[EvidenceEvent] = []
        self.assess_calls: list[PromotionRequest] = []

    def record(self, event: EvidenceEvent) -> EvidenceReceipt:
        self.events.append(event)
        canonical = json.dumps(
            {
                "run_id": event.run_id,
                "candidate_id": event.candidate_id,
                "event_type": event.event_type,
                "input_hashes": dict(event.input_hashes),
                "payload": dict(event.payload),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return EvidenceReceipt(
            event_hash="ev-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
            run_id=event.run_id,
            candidate_id=event.candidate_id,
            valid=self.receipts_valid and event.event_type not in self.invalid_event_types,
        )

    def assess_promotion(self, request: PromotionRequest) -> PromotionDecision:
        self.assess_calls.append(request)
        # Mirror of the real FileTrustStore V2 receipt validation: a receipt,
        # when present, must be bound to this run and this candidate hash and
        # must name its approver, otherwise promotion fails closed.
        receipt = getattr(request, "approval_receipt", None)
        if receipt is not None and (
            receipt.run_id != request.run_id
            or receipt.candidate_sha256 != request.candidate_hash
            or not str(receipt.approved_by).strip()
        ):
            return PromotionDecision(
                outcome=Outcome.DENY, reason_code="APPROVAL_RECEIPT_INVALID"
            )
        if request.verification_status != VerificationStatus.PASS:
            return PromotionDecision(outcome=Outcome.DENY, reason_code="VERIFY_NOT_PASS")
        if request.approval_status != ApprovalStatus.APPROVED:
            return PromotionDecision(outcome=Outcome.DENY, reason_code="APPROVAL_NOT_APPROVED")
        if request.evidence_status.value == "INVALID":
            return PromotionDecision(outcome=Outcome.DENY, reason_code="EVIDENCE_INVALID")
        if request.evidence_status.value != "COMPLETE":
            return PromotionDecision(outcome=Outcome.DENY, reason_code="EVIDENCE_INCOMPLETE")
        return PromotionDecision(outcome=Outcome.ALLOW, reason_code="APPROVAL_GRANTED")
