"""Typed workflow state and protocol serialization helpers (Agent H, Wave 1).

The LangGraph state carries only JSON-serializable values so the SQLite
checkpointer can round-trip it across process restarts. Protocol frozen
dataclasses are reconstructed from these payloads inside node functions.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping, TypedDict

from .protocol import (
    EvidenceReceipt,
    ExecutionResult,
    Finding,
    PolicyDecision,
    VerificationResult,
)

PHASE_PREFLIGHT = "PREFLIGHT"
PHASE_CREATE_CANDIDATE = "CREATE_CANDIDATE"
PHASE_EXECUTE = "EXECUTE"
PHASE_VERIFY = "VERIFY"
PHASE_DETECT_STALL = "DETECT_STALL"
PHASE_REPAIR = "REPAIR"
PHASE_HUMAN_REVIEW = "HUMAN_REVIEW"
PHASE_PROMOTION = "PROMOTION"
PHASE_TERMINAL = "TERMINAL"


class SandboxState(TypedDict, total=False):
    """Cross-layer state control plane for one sandbox run."""

    run_id: str
    domain_id: str
    bundle_hash: str
    subject: dict[str, Any]
    repair_plan: dict[str, Any] | None
    candidate_id: str
    candidate_root: str
    candidate_hash: str
    phase: str
    repair_count: int
    max_repairs: int
    findings: list[dict[str, Any]]
    previous_finding_fingerprint: str
    stall_count: int
    policy_result: dict[str, Any] | None
    execution_result: dict[str, Any] | None
    verification_result: dict[str, Any] | None
    promotion_result: dict[str, Any] | None
    evidence_receipts: list[dict[str, Any]]
    pending_human_action: dict[str, Any] | None
    human_decision: str | None
    approved_by: str
    approver_role: str
    approved_at: str
    terminal_reason: str | None


def encode_finding(finding: Finding) -> dict[str, Any]:
    return {
        "code": finding.code,
        "message": finding.message,
        "source": finding.source,
        "details": dict(finding.details),
    }


def decode_finding(payload: Mapping[str, Any]) -> Finding:
    return Finding(
        code=payload["code"],
        message=payload["message"],
        source=payload["source"],
        details=dict(payload.get("details") or {}),
    )


def encode_findings(findings: Iterable[Finding]) -> list[dict[str, Any]]:
    return [encode_finding(finding) for finding in findings]


def decode_findings(payloads: Iterable[Mapping[str, Any]]) -> tuple[Finding, ...]:
    return tuple(decode_finding(payload) for payload in payloads)


def encode_policy_decision(decision: PolicyDecision) -> dict[str, Any]:
    return {
        "outcome": decision.outcome.value,
        "reason_code": decision.reason_code,
        "findings": encode_findings(decision.findings),
    }


def encode_execution(result: ExecutionResult) -> dict[str, Any]:
    return {
        "success": result.success,
        "action_id": result.action_id,
        "candidate_id": result.candidate_id,
        "artifacts": [str(path) for path in result.artifacts],
        "findings": encode_findings(result.findings),
        "actor_id": result.actor_id,
    }


def encode_verification(result: VerificationResult) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "candidate_id": result.candidate_id,
        "findings": encode_findings(result.findings),
        "actor_id": result.actor_id,
    }


def encode_receipt(receipt: EvidenceReceipt, event_type: str) -> dict[str, Any]:
    return {
        "event_hash": receipt.event_hash,
        "run_id": receipt.run_id,
        "candidate_id": receipt.candidate_id,
        "valid": receipt.valid,
        "event_type": event_type,
    }


PROGRESS_KEYS_FIELD = "progress_keys"
_PROGRESS_VALUE_ABSENT = "<absent>"  # cannot collide: json.dumps() output is always quoted/bracketed


def _progress_signature(finding: Mapping[str, Any]) -> list[list[str]] | None:
    """Canonical (key, value) signature for the declared progress fields.

    ``details`` is diagnostic context. A finding opts a subset of it into stall
    detection by listing those key names under ``details["progress_keys"]``;
    everything else in ``details`` stays out of the fingerprint, so a changing
    timestamp or path never reads as repair progress.

    Returns ``None`` when nothing is declared, which keeps the fingerprint on
    the original ``(code, message)`` form -- see ``finding_fingerprint``.
    """
    details = finding.get("details")
    if not isinstance(details, Mapping):
        return None
    declared = details.get(PROGRESS_KEYS_FIELD)
    if not isinstance(declared, (list, tuple)) or not declared:
        return None
    # Sorted + de-duplicated: the declaration is a set, so reordering it must
    # not change the fingerprint.
    keys = sorted({str(key) for key in declared})
    signature = []
    for key in keys:
        if key in details:
            encoded = json.dumps(
                details[key], sort_keys=True, separators=(",", ":"), default=str
            )
        else:
            # A declared-but-absent key is itself a distinguishable state:
            # absent -> present must register as a change.
            encoded = _PROGRESS_VALUE_ABSENT
        signature.append([key, encoded])
    return signature


def finding_fingerprint(findings: Iterable[Mapping[str, Any]]) -> str:
    """Deterministic fingerprint over findings, for stall detection.

    Each finding contributes ``(code, message)``; a finding that declares
    ``details["progress_keys"]`` additionally contributes the canonical values
    of exactly those keys.

    Findings that declare nothing hash **byte-identically to the original
    (code, message) form**, so fingerprints recorded in existing checkpoints
    stay comparable across this change.
    """
    entries = []
    for finding in findings:
        entry = [str(finding.get("code", "")), str(finding.get("message", ""))]
        signature = _progress_signature(finding)
        if signature is not None:
            entry.append(signature)
        entries.append(entry)
    canonical = json.dumps(sorted(entries), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
