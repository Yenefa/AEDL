"""LangGraph orchestration shell for the EDD-001 sandbox (Agent H, Wave 1 + 3).

LangGraph only routes state; every hardware-truth decision is delegated to
the deterministic ports frozen in protocol.py. All side-effecting nodes are
idempotent: candidate creation is derived deterministically, and executor
effects are guarded by the per-candidate action ledger on disk.

Wave 3 (review P1 fixes): failed executions, action/candidate identity
mismatches, artifact escapes, foreign verifier results, and invalid evidence
receipts all terminate the run fail-closed — before any receipt is written
for the failure, before PHASE_VERIFY, human approval, or promotion.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .protocol import (
    ApprovalStatus,
    EvidenceEvent,
    EvidenceStatus,
    ExecutorPort,
    Finding,
    HumanApprovalReceipt,
    Outcome,
    PolicyPort,
    PolicyRequest,
    PromotionRequest,
    RepairPort,
    TrustPort,
    VerificationStatus,
    VerifierPort,
)
from .state import (
    PHASE_CREATE_CANDIDATE,
    PHASE_DETECT_STALL,
    PHASE_EXECUTE,
    PHASE_HUMAN_REVIEW,
    PHASE_PREFLIGHT,
    PHASE_PROMOTION,
    PHASE_REPAIR,
    PHASE_TERMINAL,
    PHASE_VERIFY,
    SandboxState,
    decode_findings,
    encode_execution,
    encode_findings,
    encode_policy_decision,
    encode_receipt,
    encode_verification,
    finding_fingerprint,
)
from .workspace import CandidateWorkspace

APPROVED = "APPROVED"
REJECTED = "REJECTED"

TERMINAL_PROMOTED = "STATE_PROMOTED"
TERMINAL_REPAIR_STALLED = "REPAIR_STALLED"
TERMINAL_REPAIR_LIMIT_REACHED = "REPAIR_LIMIT_REACHED"
TERMINAL_HUMAN_REJECTED = "APPROVAL_HUMAN_REJECTED"
# Wave 3 fail-closed terminal reasons (review P1 fixes).
TERMINAL_EXECUTION_FAILED = "EXECUTION_FAILED"
TERMINAL_EXECUTION_IDENTITY_MISMATCH = "EXECUTION_IDENTITY_MISMATCH"
TERMINAL_EXECUTION_ARTIFACT_ESCAPE = "EXECUTION_ARTIFACT_ESCAPE"
TERMINAL_VERIFY_IDENTITY_MISMATCH = "VERIFY_IDENTITY_MISMATCH"
TERMINAL_EVIDENCE_RECEIPT_INVALID = "EVIDENCE_RECEIPT_INVALID"

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _as_hex_digest(value: str) -> str:
    """Evidence-event input_hashes values must be 64-hex digests; normalize
    opaque bundle references deterministically instead of passing them through."""
    if _HEX64.fullmatch(value):
        return value
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _artifact_within_candidate(candidate_root: Path, artifact: object) -> bool:
    """True when the artifact path resolves inside the candidate root."""
    try:
        path = Path(str(artifact))
        if not path.is_absolute():
            path = candidate_root / path
        resolved = path.resolve()
        resolved.relative_to(candidate_root.resolve())
    except (ValueError, OSError, RuntimeError):
        return False
    return True


def _execution_failure_reason(
    request: PolicyRequest,
    candidate_id: str,
    candidate_root: Path,
    encoded: Mapping[str, Any],
) -> str | None:
    """Fail-closed triage of an execution result (fresh or ledger-replayed).

    Known violations first: a failed execution, an action/candidate identity
    mismatch, or an artifact outside the candidate root each terminate the
    run before any evidence receipt or human review can happen.
    """
    if encoded.get("success") is not True:
        return TERMINAL_EXECUTION_FAILED
    if encoded.get("action_id") != request.action_id:
        return TERMINAL_EXECUTION_IDENTITY_MISMATCH
    if encoded.get("candidate_id") != candidate_id:
        return TERMINAL_EXECUTION_IDENTITY_MISMATCH
    for artifact in encoded.get("artifacts") or ():
        if not _artifact_within_candidate(candidate_root, artifact):
            return TERMINAL_EXECUTION_ARTIFACT_ESCAPE
    return None


class SandboxOrchestrator:
    """Resumable sandbox workflow: preflight -> candidate -> execute -> verify
    -> (bounded repair loop) -> human interrupt -> promote or reject."""

    def __init__(
        self,
        *,
        policy: PolicyPort,
        executor: ExecutorPort,
        verifier: VerifierPort,
        repair: RepairPort,
        trust: TrustPort,
        workspace: CandidateWorkspace,
        run_id: str,
        domain_id: str,
        bundle_hash: str,
        subject: Mapping[str, Any],
        max_repairs: int = 3,
        checkpointer: Any,
        stall_recovery: Callable[[str, str, tuple[Finding, ...]], bool] | None = None,
    ) -> None:
        for label, port, port_type in (
            ("policy", policy, PolicyPort),
            ("executor", executor, ExecutorPort),
            ("verifier", verifier, VerifierPort),
            ("repair", repair, RepairPort),
            ("trust", trust, TrustPort),
        ):
            if not isinstance(port, port_type):
                raise TypeError(f"{label} port does not satisfy {port_type.__name__}")
        if not isinstance(workspace, CandidateWorkspace):
            raise TypeError("workspace must be a CandidateWorkspace")
        if checkpointer is None:
            raise ValueError("a checkpointer is required so interrupts can resume")
        if int(max_repairs) < 0:
            raise ValueError("max_repairs must be >= 0")
        if stall_recovery is not None and not callable(stall_recovery):
            raise TypeError("stall_recovery must be callable or None")
        self._policy = policy
        self._executor = executor
        self._verifier = verifier
        self._repair_port = repair
        self._trust = trust
        self._workspace = workspace
        self._run_id = run_id
        self._domain_id = domain_id
        self._bundle_hash = bundle_hash
        self._subject = dict(subject)
        self._max_repairs = int(max_repairs)
        self._stall_recovery = stall_recovery
        self._config = {"configurable": {"thread_id": run_id}}
        self._recursion_limit = 6 * (self._max_repairs + 1) + 10
        self._graph = self._build_graph().compile(checkpointer=checkpointer)

    # ------------------------------------------------------------------ API

    def run(self) -> dict[str, Any]:
        snapshot = self._graph.get_state(self._config)
        if snapshot.values:
            raise RuntimeError("run already started on this thread; use resume()")
        initial: SandboxState = {
            "run_id": self._run_id,
            "domain_id": self._domain_id,
            "bundle_hash": self._bundle_hash,
            "subject": dict(self._subject),
            "repair_plan": None,
            "candidate_id": "",
            "candidate_root": "",
            "candidate_hash": "",
            "phase": PHASE_PREFLIGHT,
            "repair_count": 0,
            "max_repairs": self._max_repairs,
            "findings": [],
            "previous_finding_fingerprint": "",
            "stall_count": 0,
            "policy_result": None,
            "execution_result": None,
            "verification_result": None,
            "promotion_result": None,
            "evidence_receipts": [],
            "pending_human_action": None,
            "human_decision": None,
            "approved_by": "",
            "approver_role": "",
            "approved_at": "",
            "terminal_reason": None,
        }
        self._invoke(initial)
        return self.current_state()

    def resume(
        self,
        decision: str,
        *,
        approved_by: str = "",
        approver_role: str = "human_reviewer",
    ) -> dict[str, Any]:
        if decision not in (APPROVED, REJECTED):
            raise ValueError(f"decision must be {APPROVED} or {REJECTED}")
        if not approved_by.strip():
            raise ValueError(
                "human decisions must name their approver (approved_by); "
                "an anonymous decision can never promote or reject a candidate"
            )
        if self.pending_interrupt() is None:
            raise RuntimeError("no pending human interrupt for this run")
        self._invoke(
            Command(
                resume={
                    "decision": decision,
                    "approved_by": approved_by,
                    "approver_role": approver_role,
                }
            )
        )
        return self.current_state()

    def pending_interrupt(self) -> dict[str, Any] | None:
        snapshot = self._graph.get_state(self._config)
        for task in snapshot.tasks:
            if task.interrupts:
                payload = task.interrupts[0].value
                if isinstance(payload, dict):
                    return dict(payload)
                return {"question": str(payload)}
        return None

    def current_state(self) -> dict[str, Any]:
        return dict(self._graph.get_state(self._config).values)

    def _invoke(self, payload: Any) -> None:
        config = dict(self._config)
        config["recursion_limit"] = self._recursion_limit
        self._graph.invoke(payload, config=config)

    # ---------------------------------------------------------------- graph

    def _build_graph(self) -> StateGraph:
        graph: StateGraph = StateGraph(SandboxState)
        graph.add_node("preflight", self._preflight)
        graph.add_node("create_candidate", self._create_candidate)
        graph.add_node("execute", self._execute)
        graph.add_node("verify", self._verify)
        graph.add_node("detect_stall", self._detect_stall)
        graph.add_node("repair", self._repair)
        graph.add_node("human_review", self._human_review)
        graph.add_node("promote_or_reject", self._promote_or_reject)
        graph.add_edge(START, "preflight")
        graph.add_conditional_edges(
            "preflight",
            self._route_terminal_or_continue,
            {"continue": "create_candidate", "terminal": END},
        )
        graph.add_edge("create_candidate", "execute")
        graph.add_conditional_edges(
            "execute",
            self._route_terminal_or_continue,
            {"continue": "verify", "terminal": END},
        )
        graph.add_conditional_edges(
            "verify",
            self._route_after_verify,
            {"human_review": "human_review", "detect_stall": "detect_stall", "terminal": END},
        )
        graph.add_conditional_edges(
            "detect_stall",
            self._route_terminal_or_continue,
            {"continue": "repair", "terminal": END},
        )
        graph.add_edge("repair", "preflight")
        graph.add_edge("human_review", "promote_or_reject")
        graph.add_edge("promote_or_reject", END)
        return graph

    @staticmethod
    def _route_terminal_or_continue(state: Mapping[str, Any]) -> str:
        return "terminal" if state.get("terminal_reason") else "continue"

    @staticmethod
    def _route_after_verify(state: Mapping[str, Any]) -> str:
        if state.get("terminal_reason"):
            return "terminal"
        status = (state.get("verification_result") or {}).get("status")
        if status == VerificationStatus.PASS.value:
            return "human_review"
        if status == VerificationStatus.FAIL.value:
            return "detect_stall"
        return "terminal"

    # ---------------------------------------------------------------- nodes

    def _current_subject(self, state: Mapping[str, Any]) -> dict[str, Any]:
        plan = state.get("repair_plan")
        if plan and plan.get("subject"):
            return dict(plan["subject"])
        return dict(state.get("subject") or self._subject)

    def _candidate_root_or_run_root(self, state: Mapping[str, Any]) -> Path:
        root = state.get("candidate_root")
        return Path(root) if root else self._workspace.run_root(self._run_id)

    def _preflight(self, state: SandboxState) -> dict[str, Any]:
        request = PolicyRequest(
            run_id=self._run_id,
            domain_id=self._domain_id,
            action_id=f"preflight-r{state.get('repair_count', 0)}",
            action="preflight",
            candidate_root=self._candidate_root_or_run_root(state),
            subject=self._current_subject(state),
        )
        decision = self._policy.evaluate(request)
        encoded = encode_policy_decision(decision)
        if decision.outcome != Outcome.ALLOW:
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": decision.reason_code,
                "policy_result": encoded,
            }
        return {"phase": PHASE_CREATE_CANDIDATE, "policy_result": encoded}

    def _create_candidate(self, state: SandboxState) -> dict[str, Any]:
        subject = self._current_subject(state)
        candidate_id = CandidateWorkspace.derive_candidate_id(
            self._run_id, self._domain_id, self._bundle_hash, subject
        )
        root = self._workspace.create_candidate(self._run_id, candidate_id)
        return {
            "candidate_id": candidate_id,
            "candidate_root": str(root),
            "candidate_hash": self._workspace.candidate_hash(self._run_id, candidate_id),
            "phase": PHASE_EXECUTE,
        }

    def _execute(self, state: SandboxState) -> dict[str, Any]:
        candidate_id = state["candidate_id"]
        candidate_root = Path(state["candidate_root"])
        action_id = f"execute:{candidate_id}"
        request = PolicyRequest(
            run_id=self._run_id,
            domain_id=self._domain_id,
            action_id=action_id,
            action="execute_candidate",
            candidate_root=candidate_root,
            subject=self._current_subject(state),
        )
        decision = self._policy.evaluate(request)
        encoded_policy = encode_policy_decision(decision)
        if decision.outcome != Outcome.ALLOW:
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": decision.reason_code,
                "policy_result": encoded_policy,
            }
        recorded = self._workspace.get_recorded_action(self._run_id, candidate_id, action_id)
        if recorded is not None:
            failure = _execution_failure_reason(
                request, candidate_id, candidate_root, recorded
            )
            if failure is not None:
                return {
                    "phase": PHASE_TERMINAL,
                    "terminal_reason": failure,
                    "execution_result": recorded,
                    "policy_result": encoded_policy,
                    "pending_human_action": None,
                }
            return {
                "phase": PHASE_VERIFY,
                "execution_result": recorded,
                "policy_result": encoded_policy,
            }
        result = self._executor.execute(request)
        encoded = encode_execution(result)
        # Record even failing results: the ledger is the idempotency and
        # audit record, and a replayed failure must fail closed the same way.
        self._workspace.record_action(self._run_id, candidate_id, action_id, encoded)
        failure = _execution_failure_reason(request, candidate_id, candidate_root, encoded)
        if failure is not None:
            # Fail closed: a failed or inconsistent execution writes no
            # evidence receipt and can never reach PHASE_VERIFY or human
            # approval.
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": failure,
                "execution_result": encoded,
                "policy_result": encoded_policy,
                "pending_human_action": None,
            }
        receipt = self._trust.record(
            EvidenceEvent(
                run_id=self._run_id,
                candidate_id=candidate_id,
                event_type="execution",
                input_hashes={"bundle_sha256": _as_hex_digest(self._bundle_hash)},
                payload={
                    "success": result.success,
                    "action_id": result.action_id,
                    "actor_id": result.actor_id,
                    "artifacts": [str(path) for path in result.artifacts],
                },
            )
        )
        if not receipt.valid:
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": TERMINAL_EVIDENCE_RECEIPT_INVALID,
                "execution_result": encoded,
                "policy_result": encoded_policy,
                "pending_human_action": None,
            }
        receipts = list(state.get("evidence_receipts") or [])
        receipts.append(encode_receipt(receipt, "execution"))
        return {
            "phase": PHASE_VERIFY,
            "execution_result": encoded,
            "policy_result": encoded_policy,
            "evidence_receipts": receipts,
        }

    def _verify(self, state: SandboxState) -> dict[str, Any]:
        candidate_id = state["candidate_id"]
        candidate_root = Path(state["candidate_root"])
        result = self._verifier.verify(self._run_id, candidate_id, candidate_root)
        if result.candidate_id != candidate_id:
            # Identity mismatch = broken trust chain: nothing of the foreign
            # result is registered for the current candidate (no findings,
            # no receipt, no verification_result) and the run terminates.
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": TERMINAL_VERIFY_IDENTITY_MISMATCH,
                "pending_human_action": None,
            }
        encoded = encode_verification(result)
        findings = encode_findings(result.findings)
        candidate_hash = self._workspace.candidate_hash(self._run_id, candidate_id)
        receipt = self._trust.record(
            EvidenceEvent(
                run_id=self._run_id,
                candidate_id=candidate_id,
                event_type="verification",
                input_hashes={"candidate_sha256": candidate_hash},
                payload={
                    "status": result.status.value,
                    "actor_id": result.actor_id,
                    "findings": findings,
                    "sequence": int(state.get("repair_count", 0)) + 1,
                },
            )
        )
        if not receipt.valid:
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": TERMINAL_EVIDENCE_RECEIPT_INVALID,
                "verification_result": encoded,
                "findings": findings,
                "candidate_hash": candidate_hash,
                "pending_human_action": None,
            }
        receipts = list(state.get("evidence_receipts") or [])
        receipts.append(encode_receipt(receipt, "verification"))
        update: dict[str, Any] = {
            "verification_result": encoded,
            "findings": findings,
            "candidate_hash": candidate_hash,
            "evidence_receipts": receipts,
        }
        if result.status == VerificationStatus.PASS:
            update["phase"] = PHASE_HUMAN_REVIEW
            update["pending_human_action"] = {
                "question": "Approve promotion of this candidate? Resume with APPROVED or REJECTED.",
                "run_id": self._run_id,
                "candidate_id": candidate_id,
                "candidate_hash": candidate_hash,
                "verification_status": result.status.value,
            }
        elif result.status == VerificationStatus.FAIL:
            update["phase"] = PHASE_DETECT_STALL
            update["pending_human_action"] = None
        else:
            update["phase"] = PHASE_TERMINAL
            update["terminal_reason"] = findings[0]["code"] if findings else "VERIFY_BLOCKED"
            update["pending_human_action"] = None
        return update

    def _detect_stall(self, state: SandboxState) -> dict[str, Any]:
        fingerprint = finding_fingerprint(state.get("findings") or [])
        previous = state.get("previous_finding_fingerprint") or ""
        stall_count = state.get("stall_count", 0)
        if previous and fingerprint == previous:
            # This optional callback only schedules advice for the existing
            # repair node; it must not call a model or execute a repair here.
            # The allowance lives in checkpointed state rather than in the
            # callback instance, so reconstruction cannot grant a new retry.
            if (
                self._stall_recovery is not None
                and stall_count == 0
                and state.get("repair_count", 0)
                < state.get("max_repairs", self._max_repairs)
            ):
                try:
                    recover = self._stall_recovery(
                        self._run_id,
                        state["candidate_id"],
                        decode_findings(state.get("findings") or []),
                    )
                except Exception:
                    # A broken scheduler cannot authorize another repair.
                    recover = False
                if recover is True:
                    return {
                        "phase": PHASE_REPAIR,
                        "previous_finding_fingerprint": fingerprint,
                        "stall_count": stall_count + 1,
                    }
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": TERMINAL_REPAIR_STALLED,
                "previous_finding_fingerprint": fingerprint,
                "stall_count": stall_count + 1,
            }
        if state.get("repair_count", 0) >= state.get("max_repairs", self._max_repairs):
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": TERMINAL_REPAIR_LIMIT_REACHED,
                "previous_finding_fingerprint": fingerprint,
            }
        return {
            "phase": PHASE_REPAIR,
            "previous_finding_fingerprint": fingerprint,
        }

    def _repair(self, state: SandboxState) -> dict[str, Any]:
        findings = decode_findings(state.get("findings") or [])
        plan = self._repair_port.propose(self._run_id, state["candidate_id"], findings)
        return {
            "phase": PHASE_PREFLIGHT,
            "repair_count": state.get("repair_count", 0) + 1,
            "repair_plan": {
                "action": plan.action,
                "action_id": plan.action_id,
                "subject": dict(plan.subject),
            },
            "pending_human_action": None,
        }

    def _human_review(self, state: SandboxState) -> dict[str, Any]:
        payload = dict(
            state.get("pending_human_action")
            or {
                "question": "Approve promotion of this candidate? Resume with APPROVED or REJECTED.",
                "run_id": self._run_id,
                "candidate_id": state.get("candidate_id", ""),
                "candidate_hash": state.get("candidate_hash", ""),
                "verification_status": VerificationStatus.PASS.value,
            }
        )
        answer = interrupt(payload)
        if isinstance(answer, Mapping):
            decision = answer.get("decision")
            approved_by = str(answer.get("approved_by", ""))
            approver_role = str(answer.get("approver_role", "") or "human_reviewer")
        else:
            # Legacy string resume (pre-approver checkpoints or raw Command
            # injection): no approver identity travels with the decision, so
            # the receipt is built unattributed and the trust store rejects
            # it fail-closed instead of promoting anonymously.
            decision = answer
            approved_by = ""
            approver_role = "human_reviewer"
        if decision not in (APPROVED, REJECTED):
            raise ValueError(
                f"invalid human decision {decision!r}; expected APPROVED or REJECTED"
            )
        return {
            "phase": PHASE_PROMOTION,
            "human_decision": decision,
            "approved_by": approved_by,
            "approver_role": approver_role,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "pending_human_action": None,
        }

    def _promote_or_reject(self, state: SandboxState) -> dict[str, Any]:
        decision = state.get("human_decision")
        if decision == REJECTED:
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": TERMINAL_HUMAN_REJECTED,
                "promotion_result": {
                    "outcome": Outcome.DENY.value,
                    "reason_code": TERMINAL_HUMAN_REJECTED,
                    "findings": [],
                },
            }
        verification_payload = state.get("verification_result") or {}
        candidate_id = state["candidate_id"]
        # Recompute the live content hash so a candidate mutated after
        # verification can never be promoted on stale evidence.
        current_hash = self._workspace.candidate_hash(self._run_id, candidate_id)
        request = PromotionRequest(
            run_id=self._run_id,
            candidate_id=candidate_id,
            candidate_hash=current_hash,
            verification_status=VerificationStatus(
                verification_payload.get("status", VerificationStatus.NOT_RUN.value)
            ),
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=self._evidence_status(state),
            # V2: the approval is a receipt bound to the exact candidate bytes
            # being promoted (recomputed above) and to the named human who
            # made the decision — never a bare anonymous declaration.
            approval_receipt=HumanApprovalReceipt(
                run_id=self._run_id,
                candidate_sha256=current_hash,
                decision=ApprovalStatus.APPROVED,
                approved_by=str(state.get("approved_by", "")),
                approver_role=str(state.get("approver_role", "") or "human_reviewer"),
                approved_at=str(state.get("approved_at", "")),
            ),
        )
        promotion = self._trust.assess_promotion(request)
        encoded = {
            "outcome": promotion.outcome.value,
            "reason_code": promotion.reason_code,
        }
        if promotion.outcome == Outcome.ALLOW:
            promotion_receipt = self._trust.record(
                EvidenceEvent(
                    run_id=self._run_id,
                    candidate_id=candidate_id,
                    event_type="promotion",
                    input_hashes={"candidate_sha256": current_hash},
                    payload={
                        "reason_code": promotion.reason_code,
                        "approved_by": str(state.get("approved_by", "")),
                        "sequence": len(state.get("evidence_receipts") or []) + 1,
                    },
                )
            )
            if not promotion_receipt.valid:
                # The promotion receipt is the audit proof of the promotion;
                # an invalid (tampered/conflicting) receipt withholds it and
                # terminates the run fail-closed instead of promoting.
                return {
                    "phase": PHASE_TERMINAL,
                    "terminal_reason": TERMINAL_EVIDENCE_RECEIPT_INVALID,
                    "promotion_result": encoded,
                    "candidate_hash": current_hash,
                }
            return {
                "phase": PHASE_TERMINAL,
                "terminal_reason": TERMINAL_PROMOTED,
                "promotion_result": encoded,
                "candidate_hash": current_hash,
            }
        return {
            "phase": PHASE_TERMINAL,
            "terminal_reason": promotion.reason_code,
            "promotion_result": encoded,
        }

    def _evidence_status(self, state: Mapping[str, Any]) -> EvidenceStatus:
        receipts = state.get("evidence_receipts") or []
        if not receipts:
            return EvidenceStatus.MISSING
        if any(not receipt.get("valid", False) for receipt in receipts):
            return EvidenceStatus.INVALID
        current = state.get("candidate_id")
        has_verification = any(
            receipt.get("event_type") == "verification"
            and receipt.get("candidate_id") == current
            for receipt in receipts
        )
        return EvidenceStatus.COMPLETE if has_verification else EvidenceStatus.PARTIAL
