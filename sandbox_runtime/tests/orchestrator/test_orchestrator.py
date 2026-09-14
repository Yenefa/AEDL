"""RED/GREEN tests for the sandbox orchestrator (Agent H, Wave 1).

Covers the mandatory Wave 1 scenarios: fail-closed policy routing, the
bounded repair loop, stall detection, checkpoint resume without repeated
side effects, and the human approval boundary before promotion.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from langgraph.checkpoint.memory import InMemorySaver
except ImportError:  # pragma: no cover - older checkpoint releases
    from langgraph.checkpoint.memory import MemorySaver as InMemorySaver  # type: ignore
from langgraph.checkpoint.sqlite import SqliteSaver

from aedl_sandbox.orchestrator import (
    APPROVED,
    REJECTED,
    TERMINAL_EVIDENCE_RECEIPT_INVALID,
    TERMINAL_EXECUTION_ARTIFACT_ESCAPE,
    TERMINAL_EXECUTION_FAILED,
    TERMINAL_EXECUTION_IDENTITY_MISMATCH,
    TERMINAL_VERIFY_IDENTITY_MISMATCH,
    SandboxOrchestrator,
)
from aedl_sandbox.protocol import (
    REASON_CODE_PREFIXES,
    ApprovalStatus,
    ExecutionResult,
    Outcome,
    PolicyDecision,
)
from aedl_sandbox.state import finding_fingerprint
from aedl_sandbox.workspace import CandidateWorkspace

try:
    from .fakes import (
        CountingExecutor,
        ForeignCandidateVerifier,
        IncrementRepair,
        ScriptedExecutor,
        ScriptedPolicy,
        ScriptedVerifier,
        StrictTrust,
        allow_all,
        blocked_result,
        deny_direct_kicad,
        fail_result,
        pass_result,
    )
except ImportError:  # focused discovery: tests/orchestrator is the top level
    from fakes import (  # type: ignore
        CountingExecutor,
        ForeignCandidateVerifier,
        IncrementRepair,
        ScriptedExecutor,
        ScriptedPolicy,
        ScriptedVerifier,
        StrictTrust,
        allow_all,
        blocked_result,
        deny_direct_kicad,
        fail_result,
        pass_result,
    )

RUN_ID = "run-1"
DOMAIN = "EDD-001-TEST"
BUNDLE = "bundlehash1"


class OrchestratorTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _make(
        self,
        *,
        policy=None,
        verifier,
        executor=None,
        repair=None,
        trust=None,
        max_repairs=3,
        checkpointer=None,
        subject=None,
        workspace=None,
    ) -> SandboxOrchestrator:
        return SandboxOrchestrator(
            policy=policy or ScriptedPolicy(allow_all),
            executor=executor or CountingExecutor(),
            verifier=verifier,
            repair=repair or IncrementRepair(),
            trust=trust or StrictTrust(),
            workspace=workspace or CandidateWorkspace(self.base / "ws"),
            run_id=RUN_ID,
            domain_id=DOMAIN,
            bundle_hash=BUNDLE,
            subject=subject or {"action": "fixture"},
            max_repairs=max_repairs,
            checkpointer=checkpointer or InMemorySaver(),
        )


class FailClosedPolicyTests(OrchestratorTestBase):
    def test_deny_terminates_before_candidate_execution(self):
        executor = CountingExecutor()
        orchestrator = self._make(
            policy=ScriptedPolicy(
                lambda request: PolicyDecision(Outcome.DENY, "POLICY_COMPONENT_NOT_ALLOWED")
            ),
            verifier=ScriptedVerifier([pass_result()]),
            executor=executor,
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], "POLICY_COMPONENT_NOT_ALLOWED")
        self.assertEqual(state["phase"], "TERMINAL")
        self.assertEqual(len(executor.calls), 0)
        self.assertEqual(state["candidate_id"], "")
        self.assertFalse((self.base / "ws" / "run").exists())

    def test_blocked_terminates_before_candidate_execution(self):
        executor = CountingExecutor()
        orchestrator = self._make(
            policy=ScriptedPolicy(
                lambda request: PolicyDecision(Outcome.BLOCKED, "POLICY_DATASHEET_MISSING")
            ),
            verifier=ScriptedVerifier([pass_result()]),
            executor=executor,
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], "POLICY_DATASHEET_MISSING")
        self.assertEqual(len(executor.calls), 0)

    def test_direct_kicad_write_request_never_reaches_executor(self):
        executor = CountingExecutor()
        orchestrator = self._make(
            policy=ScriptedPolicy(deny_direct_kicad),
            verifier=ScriptedVerifier([pass_result()]),
            executor=executor,
            subject={"action": "write_kicad"},
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], "POLICY_DIRECT_KICAD_WRITE")
        self.assertEqual(len(executor.calls), 0)

    def test_execute_gate_deny_terminates_without_executor_call(self):
        executor = CountingExecutor()

        def gate(request):
            if request.action == "preflight":
                return PolicyDecision(Outcome.ALLOW, "POLICY_TEST_ALLOW")
            return PolicyDecision(Outcome.DENY, "POLICY_TOOL_NOT_ALLOWED")

        orchestrator = self._make(
            policy=ScriptedPolicy(gate),
            verifier=ScriptedVerifier([pass_result()]),
            executor=executor,
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], "POLICY_TOOL_NOT_ALLOWED")
        self.assertNotEqual(state["candidate_id"], "")
        self.assertEqual(len(executor.calls), 0)

    def test_verify_blocked_terminates_with_finding_code(self):
        orchestrator = self._make(
            verifier=ScriptedVerifier([blocked_result("VERIFY_COVERAGE_MISSING")])
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], "VERIFY_COVERAGE_MISSING")


class RepairLoopTests(OrchestratorTestBase):
    def test_one_fail_routes_through_repair_then_pass(self):
        verifier = ScriptedVerifier([fail_result("VERIFY_A"), pass_result()])
        orchestrator = self._make(verifier=verifier)
        state = orchestrator.run()
        self.assertEqual(state["repair_count"], 1)
        self.assertEqual(state["verification_result"]["status"], "PASS")
        self.assertIsNone(state["promotion_result"])
        self.assertIsNotNone(orchestrator.pending_interrupt())
        candidate_dir = self.base / "ws" / "run" / RUN_ID / "candidate"
        self.assertEqual(len(list(candidate_dir.iterdir())), 2)

    def test_identical_findings_twice_trigger_repair_stalled(self):
        orchestrator = self._make(
            verifier=ScriptedVerifier([fail_result("VERIFY_A"), fail_result("VERIFY_A")])
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], "REPAIR_STALLED")
        self.assertEqual(state["repair_count"], 1)
        self.assertEqual(state["stall_count"], 1)

    def test_max_repair_count_triggers_limit_reached(self):
        orchestrator = self._make(
            verifier=ScriptedVerifier(
                [fail_result("VERIFY_A"), fail_result("VERIFY_B"), fail_result("VERIFY_C")]
            ),
            max_repairs=2,
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], "REPAIR_LIMIT_REACHED")
        self.assertEqual(state["repair_count"], 2)


class HumanApprovalTests(OrchestratorTestBase):
    def test_interrupt_occurs_before_promotion(self):
        trust = StrictTrust()
        orchestrator = self._make(
            verifier=ScriptedVerifier([fail_result("VERIFY_A"), pass_result()]),
            trust=trust,
        )
        state = orchestrator.run()
        pending = orchestrator.pending_interrupt()
        self.assertIsNotNone(pending)
        self.assertEqual(pending["candidate_id"], state["candidate_id"])
        self.assertEqual(pending["verification_status"], "PASS")
        self.assertIsNone(state["promotion_result"])
        self.assertEqual(len(trust.assess_calls), 0)

    def test_rejection_leaves_candidate_unpromoted(self):
        trust = StrictTrust()
        orchestrator = self._make(
            verifier=ScriptedVerifier([fail_result("VERIFY_A"), pass_result()]),
            trust=trust,
        )
        state = orchestrator.run()
        candidate_root = Path(state["candidate_root"])
        final = orchestrator.resume(REJECTED, approved_by="reviewer@example")
        self.assertEqual(final["terminal_reason"], "APPROVAL_HUMAN_REJECTED")
        self.assertEqual(final["promotion_result"]["outcome"], "DENY")
        self.assertEqual(len(trust.assess_calls), 0)
        self.assertTrue(candidate_root.exists())

    def test_approval_promotes_after_pass_with_complete_evidence(self):
        executor = CountingExecutor()
        orchestrator = self._make(
            verifier=ScriptedVerifier([fail_result("VERIFY_A"), pass_result()]),
            executor=executor,
        )
        state = orchestrator.run()
        final = orchestrator.resume(APPROVED, approved_by="reviewer@example")
        self.assertEqual(final["terminal_reason"], "STATE_PROMOTED")
        self.assertEqual(final["promotion_result"]["outcome"], "ALLOW")
        self.assertEqual(final["candidate_id"], state["candidate_id"])
        action_ids = [call.action_id for call in executor.calls]
        self.assertEqual(len(action_ids), 2)
        self.assertEqual(len(set(action_ids)), 2)

    def test_approval_with_invalid_evidence_is_denied(self):
        # Wave 3 semantics: the FIRST invalid receipt (here: the execution
        # receipt) terminates the run fail-closed before verification or
        # human review; promotion is never assessed on invalid evidence.
        trust = StrictTrust(receipts_valid=False)
        verifier = ScriptedVerifier([pass_result()])
        orchestrator = self._make(
            verifier=verifier,
            trust=trust,
        )
        state = orchestrator.run()
        self.assertEqual(state["phase"], "TERMINAL")
        self.assertEqual(state["terminal_reason"], TERMINAL_EVIDENCE_RECEIPT_INVALID)
        self.assertIsNone(orchestrator.pending_interrupt())
        self.assertEqual(len(verifier.calls), 0)
        self.assertEqual(len(trust.assess_calls), 0)

    def test_run_cannot_restart_on_same_thread(self):
        orchestrator = self._make(
            verifier=ScriptedVerifier([fail_result("VERIFY_A"), pass_result()])
        )
        orchestrator.run()
        with self.assertRaises(RuntimeError):
            orchestrator.run()

    def test_resume_requires_pending_interrupt(self):
        orchestrator = self._make(
            verifier=ScriptedVerifier([fail_result("VERIFY_A"), fail_result("VERIFY_A")])
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], "REPAIR_STALLED")
        with self.assertRaises(RuntimeError):
            orchestrator.resume(APPROVED, approved_by="reviewer@example")

    def test_resume_without_named_approver_is_rejected(self):
        orchestrator = self._make(
            verifier=ScriptedVerifier([fail_result("VERIFY_A"), pass_result()])
        )
        orchestrator.run()
        with self.assertRaises(ValueError):
            orchestrator.resume(APPROVED)
        with self.assertRaises(ValueError):
            orchestrator.resume(APPROVED, approved_by="   ")


class CheckpointResumeTests(OrchestratorTestBase):
    def test_restart_at_interrupt_does_not_repeat_side_effects(self):
        db_path = self.base / "run" / RUN_ID / "checkpoint.sqlite"
        db_path.parent.mkdir(parents=True)
        workspace = CandidateWorkspace(self.base / "ws")
        executor_first = CountingExecutor()
        with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
            first = SandboxOrchestrator(
                policy=ScriptedPolicy(allow_all),
                executor=executor_first,
                verifier=ScriptedVerifier([fail_result("VERIFY_A"), pass_result()]),
                repair=IncrementRepair(),
                trust=StrictTrust(),
                workspace=workspace,
                run_id=RUN_ID,
                domain_id=DOMAIN,
                bundle_hash=BUNDLE,
                subject={"action": "fixture"},
                max_repairs=3,
                checkpointer=checkpointer,
            )
            state_first = first.run()
            self.assertIsNotNone(first.pending_interrupt())
        artifact = Path(state_first["candidate_root"]) / "artifact.json"
        self.assertTrue(artifact.exists())
        artifact_before = artifact.read_bytes()
        first_action_ids = [call.action_id for call in executor_first.calls]
        self.assertEqual(len(first_action_ids), 2)
        self.assertEqual(len(set(first_action_ids)), 2)

        executor_second = CountingExecutor()
        trust_second = StrictTrust()
        with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
            second = SandboxOrchestrator(
                policy=ScriptedPolicy(allow_all),
                executor=executor_second,
                verifier=ScriptedVerifier([pass_result()]),
                repair=IncrementRepair(),
                trust=trust_second,
                workspace=workspace,
                run_id=RUN_ID,
                domain_id=DOMAIN,
                bundle_hash=BUNDLE,
                subject={"action": "fixture"},
                max_repairs=3,
                checkpointer=checkpointer,
            )
            state_second = second.resume(APPROVED, approved_by="reviewer@example")
        self.assertEqual(len(executor_second.calls), 0)
        self.assertEqual(state_second["candidate_id"], state_first["candidate_id"])
        self.assertEqual(state_second["run_id"], state_first["run_id"])
        self.assertEqual(artifact.read_bytes(), artifact_before)
        self.assertEqual(state_second["terminal_reason"], "STATE_PROMOTED")
        self.assertEqual(len(trust_second.assess_calls), 1)


class ExecutionFailClosedTests(OrchestratorTestBase):
    """Wave 3 review P1 regressions: failed executions, identity mismatches,
    artifact escapes, foreign verifier results, and invalid receipts must all
    terminate fail-closed — no valid evidence receipt, no PHASE_VERIFY, no
    human approval, no promotion."""

    def test_failed_execution_terminates_fail_closed(self):
        trust = StrictTrust()
        verifier = ScriptedVerifier([pass_result()])
        executor = ScriptedExecutor(success=False)
        orchestrator = self._make(
            verifier=verifier, executor=executor, trust=trust
        )
        state = orchestrator.run()
        self.assertEqual(state["phase"], "TERMINAL")
        self.assertEqual(state["terminal_reason"], TERMINAL_EXECUTION_FAILED)
        self.assertIsNone(orchestrator.pending_interrupt())
        self.assertIsNone(state.get("pending_human_action"))
        # no evidence receipt for a failed execution; verify never ran
        self.assertEqual(len(trust.events), 0)
        self.assertEqual(len(verifier.calls), 0)
        self.assertEqual(len(trust.assess_calls), 0)

    def test_execution_action_id_mismatch_terminates_fail_closed(self):
        trust = StrictTrust()
        verifier = ScriptedVerifier([pass_result()])
        executor = ScriptedExecutor(action_id="execute:someone-else")
        orchestrator = self._make(
            verifier=verifier, executor=executor, trust=trust
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], TERMINAL_EXECUTION_IDENTITY_MISMATCH)
        self.assertEqual(state["phase"], "TERMINAL")
        self.assertEqual(len(trust.events), 0)
        self.assertEqual(len(verifier.calls), 0)

    def test_execution_candidate_id_mismatch_terminates_fail_closed(self):
        trust = StrictTrust()
        verifier = ScriptedVerifier([pass_result()])
        executor = ScriptedExecutor(candidate_id="cand-foreign")
        orchestrator = self._make(
            verifier=verifier, executor=executor, trust=trust
        )
        state = orchestrator.run()
        self.assertEqual(state["terminal_reason"], TERMINAL_EXECUTION_IDENTITY_MISMATCH)
        self.assertEqual(len(trust.events), 0)
        self.assertEqual(len(verifier.calls), 0)

    def test_execution_artifact_escape_terminates_fail_closed(self):
        trust = StrictTrust()
        verifier = ScriptedVerifier([pass_result()])
        outside = self.base / "outside" / "stolen.txt"
        escaping_relative = "../../escape.txt"
        for artifacts in ((outside,), (escaping_relative,)):
            with self.subTest(artifacts=artifacts):
                executor = ScriptedExecutor(artifacts=artifacts)
                orchestrator = self._make(
                    verifier=ScriptedVerifier([pass_result()]),
                    executor=executor,
                    trust=trust,
                )
                state = orchestrator.run()
                self.assertEqual(
                    state["terminal_reason"], TERMINAL_EXECUTION_ARTIFACT_ESCAPE
                )
                self.assertEqual(state["phase"], "TERMINAL")
        self.assertEqual(len(trust.events), 0)
        self.assertFalse(outside.exists())

    def test_verifier_identity_mismatch_terminates_fail_closed(self):
        trust = StrictTrust()
        verifier = ForeignCandidateVerifier()
        orchestrator = self._make(verifier=verifier, trust=trust)
        state = orchestrator.run()
        self.assertEqual(state["phase"], "TERMINAL")
        self.assertEqual(state["terminal_reason"], TERMINAL_VERIFY_IDENTITY_MISMATCH)
        # nothing of the foreign result is registered for this candidate:
        # no verification receipt, no findings, no verification_result
        self.assertEqual([event.event_type for event in trust.events], ["execution"])
        self.assertIsNone(state.get("verification_result"))
        self.assertEqual(state.get("findings"), [])
        self.assertIsNone(orchestrator.pending_interrupt())
        self.assertEqual(len(trust.assess_calls), 0)

    def test_invalid_verification_receipt_terminates_fail_closed(self):
        trust = StrictTrust(invalid_event_types={"verification"})
        verifier = ScriptedVerifier([pass_result()])
        orchestrator = self._make(verifier=verifier, trust=trust)
        state = orchestrator.run()
        self.assertEqual(state["phase"], "TERMINAL")
        self.assertEqual(state["terminal_reason"], TERMINAL_EVIDENCE_RECEIPT_INVALID)
        self.assertIsNone(orchestrator.pending_interrupt())
        self.assertEqual(len(trust.assess_calls), 0)

    def test_invalid_promotion_receipt_withholds_promotion(self):
        trust = StrictTrust(invalid_event_types={"promotion"})
        verifier = ScriptedVerifier([pass_result()])
        orchestrator = self._make(verifier=verifier, trust=trust)
        orchestrator.run()
        self.assertIsNotNone(orchestrator.pending_interrupt())
        final = orchestrator.resume(APPROVED, approved_by="reviewer@example")
        self.assertEqual(final["terminal_reason"], TERMINAL_EVIDENCE_RECEIPT_INVALID)
        self.assertNotEqual(final["terminal_reason"], "STATE_PROMOTED")

    def test_wave3_terminal_reasons_use_frozen_prefixes(self):
        for code in (
            TERMINAL_EXECUTION_FAILED,
            TERMINAL_EXECUTION_IDENTITY_MISMATCH,
            TERMINAL_EXECUTION_ARTIFACT_ESCAPE,
            TERMINAL_VERIFY_IDENTITY_MISMATCH,
            TERMINAL_EVIDENCE_RECEIPT_INVALID,
        ):
            with self.subTest(code):
                self.assertTrue(code.startswith(REASON_CODE_PREFIXES))


class V2IdentityAndApprovalReceiptTests(OrchestratorTestBase):
    """Wave 3 V2 runtime wiring: actor identity survives into state, ledger
    and evidence receipts, and promotion carries a candidate-bound human
    approval receipt instead of a bare approval declaration."""

    def test_actor_id_flows_into_state_ledger_and_receipts(self):
        trust = StrictTrust()
        verifier = ScriptedVerifier([pass_result()], actor_id="verifier-1")
        executor = ScriptedExecutor(actor_id="compiler-1")
        orchestrator = self._make(
            verifier=verifier, executor=executor, trust=trust
        )
        state = orchestrator.run()
        final = orchestrator.resume(APPROVED, approved_by="reviewer@example")
        self.assertEqual(final["execution_result"]["actor_id"], "compiler-1")
        self.assertEqual(final["verification_result"]["actor_id"], "verifier-1")
        ledger = (
            self.base / "ws" / "run" / RUN_ID / "candidate" / state["candidate_id"]
            / ".actions.jsonl"
        )
        entries = [
            json.loads(line)
            for line in ledger.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertTrue(entries)
        self.assertTrue(
            all(entry["result"]["actor_id"] == "compiler-1" for entry in entries)
        )
        execution_event = next(e for e in trust.events if e.event_type == "execution")
        self.assertEqual(execution_event.payload["actor_id"], "compiler-1")
        verification_event = next(
            e for e in trust.events if e.event_type == "verification"
        )
        self.assertEqual(verification_event.payload["actor_id"], "verifier-1")

    def test_approval_attaches_candidate_bound_receipt(self):
        trust = StrictTrust()
        orchestrator = self._make(
            verifier=ScriptedVerifier([fail_result("VERIFY_A"), pass_result()]),
            trust=trust,
        )
        state = orchestrator.run()
        final = orchestrator.resume(
            APPROVED, approved_by="reviewer@example", approver_role="senior_reviewer"
        )
        self.assertEqual(final["terminal_reason"], "STATE_PROMOTED")
        self.assertEqual(len(trust.assess_calls), 1)
        request = trust.assess_calls[0]
        receipt = request.approval_receipt
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.run_id, RUN_ID)
        self.assertEqual(receipt.candidate_sha256, final["candidate_hash"])
        self.assertEqual(receipt.decision, ApprovalStatus.APPROVED)
        self.assertEqual(receipt.approved_by, "reviewer@example")
        self.assertEqual(receipt.approver_role, "senior_reviewer")
        self.assertTrue(receipt.approved_at)
        self.assertEqual(request.approval_status, ApprovalStatus.APPROVED)
        self.assertEqual(request.candidate_hash, receipt.candidate_sha256)


def _voltage_finding(measured, **extra):
    """A quantitative finding: static message, measured value in details."""
    details = {"measured_voltage": measured, "progress_keys": ["measured_voltage"]}
    details.update(extra)
    return {
        "code": "VOLTAGE_ERROR",
        "message": "voltage out of range",
        "source": "verifier",
        "details": details,
    }


class FindingFingerprintProgressKeysTests(unittest.TestCase):
    """`details["progress_keys"]` opts specific fields into stall detection.

    Without it the fingerprint stays exactly `(code, message)`, which is what
    every finding in the tree relies on today. `details` remains free-form
    diagnostic context: putting a number in it is NOT by itself a claim that
    the number represents repair progress.
    """

    def test_declared_progress_value_change_changes_fingerprint(self):
        # 7.0 V -> 3.7 V is real progress even though code and message repeat.
        before = finding_fingerprint([_voltage_finding(7.0)])
        after = finding_fingerprint([_voltage_finding(3.7)])
        self.assertNotEqual(
            before,
            after,
            "a change in a declared progress field must not read as a stall",
        )

    def test_undeclared_detail_churn_keeps_fingerprint_stable(self):
        # Same measured voltage, different diagnostic noise -> still stalled.
        before = finding_fingerprint(
            [_voltage_finding(7.0, timestamp="2026-09-14T00:00:00Z", path="/a/one")]
        )
        after = finding_fingerprint(
            [_voltage_finding(7.0, timestamp="2026-09-14T00:05:00Z", path="/b/two")]
        )
        self.assertEqual(
            before,
            after,
            "undeclared details are diagnostic context, not a progress signal",
        )

    def test_without_progress_keys_semantics_are_unchanged(self):
        # The existing contract: no declaration -> (code, message) only.
        base = {
            "code": "PATH_ESCAPE",
            "message": "resolved write path escapes the candidate root",
            "source": "file_policy",
        }
        first = finding_fingerprint([dict(base, details={"path": "/tmp/one"})])
        second = finding_fingerprint([dict(base, details={"path": "/tmp/two"})])
        self.assertEqual(first, second)

        # And byte-identical to the pre-progress_keys fingerprint, so that
        # `previous_finding_fingerprint` values already written into
        # checkpoints stay comparable after this change.
        legacy_pairs = sorted(
            [str(f.get("code", "")), str(f.get("message", ""))]
            for f in [dict(base, details={"path": "/tmp/one"})]
        )
        legacy = hashlib.sha256(
            json.dumps(legacy_pairs, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        self.assertEqual(first, legacy)

    def test_progress_keys_order_does_not_change_fingerprint(self):
        def finding(keys):
            return {
                "code": "VOLTAGE_ERROR",
                "message": "voltage out of range",
                "source": "verifier",
                "details": {
                    "measured_voltage": 7.0,
                    "measured_current": 0.2,
                    "progress_keys": list(keys),
                },
            }

        forward = finding_fingerprint([finding(["measured_voltage", "measured_current"])])
        reverse = finding_fingerprint([finding(["measured_current", "measured_voltage"])])
        duplicated = finding_fingerprint(
            [finding(["measured_current", "measured_voltage", "measured_current"])]
        )
        self.assertEqual(forward, reverse, "the declaration is a set, not a sequence")
        self.assertEqual(forward, duplicated)

    def test_declared_but_absent_key_is_distinguishable_from_present(self):
        # absent -> present is itself a change the stall detector must see.
        absent = finding_fingerprint(
            [
                {
                    "code": "VOLTAGE_ERROR",
                    "message": "voltage out of range",
                    "source": "verifier",
                    "details": {"progress_keys": ["measured_voltage"]},
                }
            ]
        )
        present = finding_fingerprint([_voltage_finding(7.0)])
        self.assertNotEqual(absent, present)


if __name__ == "__main__":
    unittest.main()
