"""Bounded stall scheduling through the existing repair and gate nodes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from langgraph.checkpoint.memory import InMemorySaver
except ImportError:  # pragma: no cover - older checkpoint releases
    from langgraph.checkpoint.memory import MemorySaver as InMemorySaver  # type: ignore
from langgraph.checkpoint.sqlite import SqliteSaver

from aedl_sandbox.orchestrator import (
    TERMINAL_REPAIR_LIMIT_REACHED,
    TERMINAL_REPAIR_STALLED,
    SandboxOrchestrator,
)
from aedl_sandbox.protocol import Finding, Outcome, PolicyDecision
from aedl_sandbox.workspace import CandidateWorkspace

try:
    from .fakes import (
        CountingExecutor,
        IncrementRepair,
        ScriptedPolicy,
        ScriptedVerifier,
        StrictTrust,
        allow_all,
        fail_result,
        pass_result,
    )
except ImportError:  # focused discovery: tests/orchestrator is the top level
    from fakes import (  # type: ignore
        CountingExecutor,
        IncrementRepair,
        ScriptedPolicy,
        ScriptedVerifier,
        StrictTrust,
        allow_all,
        fail_result,
        pass_result,
    )


class StallRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.serial = 0

    def _make(
        self,
        *,
        results,
        recovery=None,
        max_repairs=3,
        executor=None,
        repair=None,
        policy=None,
        trust=None,
        workspace=None,
        checkpointer=None,
    ):
        self.serial += 1
        return SandboxOrchestrator(
            policy=policy or ScriptedPolicy(allow_all),
            executor=executor or CountingExecutor(),
            verifier=ScriptedVerifier(results),
            repair=repair or IncrementRepair(),
            trust=trust or StrictTrust(),
            workspace=workspace or CandidateWorkspace(self.base / str(self.serial)),
            run_id="stall-run",
            domain_id="TEST",
            bundle_hash="stall-bundle",
            subject={"action": "fixture"},
            max_repairs=max_repairs,
            checkpointer=checkpointer or InMemorySaver(),
            stall_recovery=recovery,
        )

    def test_default_repeat_still_terminates(self):
        repair = IncrementRepair()
        state = self._make(
            results=[fail_result("VERIFY_A"), fail_result("VERIFY_A")],
            repair=repair,
        ).run()
        self.assertEqual(state["terminal_reason"], TERMINAL_REPAIR_STALLED)
        self.assertEqual(state["repair_count"], 1)
        self.assertEqual(state["stall_count"], 1)
        self.assertEqual(len(repair.calls), 1)

    def test_one_scheduled_recovery_can_pass_without_promotion(self):
        scheduled = []

        def recover(run_id, candidate_id, findings):
            scheduled.append((run_id, candidate_id, findings))
            return True

        executor = CountingExecutor()
        repair = IncrementRepair()
        trust = StrictTrust()
        orchestrator = self._make(
            results=[fail_result("VERIFY_A"), fail_result("VERIFY_A"), pass_result()],
            recovery=recover,
            max_repairs=2,
            executor=executor,
            repair=repair,
            trust=trust,
        )
        state = orchestrator.run()
        self.assertEqual(state["phase"], "HUMAN_REVIEW")
        self.assertEqual(state["verification_result"]["status"], "PASS")
        self.assertEqual(state["repair_count"], 2)
        self.assertEqual(state["stall_count"], 1)
        self.assertEqual(len(scheduled), 1)
        run_id, candidate_id, findings = scheduled[0]
        self.assertEqual(run_id, "stall-run")
        self.assertEqual(candidate_id, executor.calls[1].candidate_root.name)
        self.assertIsInstance(findings, tuple)
        self.assertIsInstance(findings[0], Finding)
        self.assertEqual(findings[0].code, "VERIFY_A")
        self.assertEqual(len(repair.calls), 2)
        self.assertEqual(len(executor.calls), 3)
        self.assertEqual(len(trust.events), 6)
        self.assertFalse(trust.assess_calls)
        self.assertIsNone(state["promotion_result"])
        self.assertIsNotNone(orchestrator.pending_interrupt())

    def test_second_repeat_terminates_without_second_callback(self):
        scheduled = []

        def recover(*args):
            scheduled.append(args)
            return True

        repair = IncrementRepair()
        state = self._make(
            results=[fail_result("VERIFY_A")] * 3,
            recovery=recover,
            repair=repair,
            max_repairs=5,
        ).run()
        self.assertEqual(state["terminal_reason"], TERMINAL_REPAIR_STALLED)
        self.assertEqual(state["repair_count"], 2)
        self.assertEqual(state["stall_count"], 2)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(len(repair.calls), 2)

    def test_changed_findings_do_not_schedule_stall_advice(self):
        scheduled = []

        def recover(*args):
            scheduled.append(args)
            return True

        state = self._make(
            results=[fail_result("VERIFY_A"), fail_result("VERIFY_B"), pass_result()],
            recovery=recover,
        ).run()
        self.assertEqual(state["phase"], "HUMAN_REVIEW")
        self.assertEqual(state["repair_count"], 2)
        self.assertEqual(state["stall_count"], 0)
        self.assertFalse(scheduled)

    def test_repair_limit_checked_before_callback(self):
        for max_repairs in (0, 1):
            with self.subTest(max_repairs=max_repairs):
                scheduled = []

                def recover(*args):
                    scheduled.append(args)
                    return True

                repair = IncrementRepair()
                executor = CountingExecutor()
                state = self._make(
                    results=[fail_result("VERIFY_A")] * (max_repairs + 1),
                    recovery=recover,
                    max_repairs=max_repairs,
                    repair=repair,
                    executor=executor,
                ).run()
                expected = (
                    TERMINAL_REPAIR_LIMIT_REACHED
                    if max_repairs == 0
                    else TERMINAL_REPAIR_STALLED
                )
                self.assertEqual(state["terminal_reason"], expected)
                self.assertEqual(state["repair_count"], max_repairs)
                self.assertEqual(len(repair.calls), max_repairs)
                self.assertEqual(len(executor.calls), max_repairs + 1)
                self.assertFalse(scheduled)

    def test_only_literal_true_authorizes_recovery(self):
        for value in (False, None, 1, "yes", [True], object()):
            with self.subTest(value_type=type(value).__name__):
                state = self._make(
                    results=[fail_result("VERIFY_A")] * 2,
                    recovery=lambda *_args: value,
                ).run()
                self.assertEqual(state["terminal_reason"], TERMINAL_REPAIR_STALLED)
                self.assertEqual(state["repair_count"], 1)
                self.assertEqual(state["stall_count"], 1)

    def test_callback_exception_fails_closed(self):
        def recover(*_args):
            raise RuntimeError("scheduler failed")

        state = self._make(
            results=[fail_result("VERIFY_A")] * 2,
            recovery=recover,
        ).run()
        self.assertEqual(state["terminal_reason"], TERMINAL_REPAIR_STALLED)
        self.assertEqual(state["repair_count"], 1)
        self.assertIsNone(state["pending_human_action"])

    def test_recovery_still_passes_existing_policy_gate(self):
        def policy(request):
            if request.action_id == "preflight-r2":
                return PolicyDecision(Outcome.DENY, "POLICY_TEST_RECOVERY_DENIED")
            return allow_all(request)

        executor = CountingExecutor()
        state = self._make(
            results=[fail_result("VERIFY_A")] * 2,
            recovery=lambda *_args: True,
            executor=executor,
            policy=ScriptedPolicy(policy),
        ).run()
        self.assertEqual(state["terminal_reason"], "POLICY_TEST_RECOVERY_DENIED")
        self.assertEqual(state["repair_count"], 2)
        self.assertEqual(len(executor.calls), 2)
        self.assertIsNone(state["promotion_result"])

    def test_reconstruction_cannot_grant_another_recovery(self):
        class CrashBeforeRecoveredExecution(CountingExecutor):
            def execute(self, request):
                if len(self.calls) == 2:
                    raise RuntimeError("test crash before recovered execution")
                return super().execute(request)

        db_path = self.base / "checkpoint.sqlite"
        workspace = CandidateWorkspace(self.base / "persistent-workspace")
        scheduled_first = []

        def recover_first(*args):
            scheduled_first.append(args)
            return True

        with SqliteSaver.from_conn_string(str(db_path)) as saver:
            first = self._make(
                results=[fail_result("VERIFY_A")] * 2,
                recovery=recover_first,
                executor=CrashBeforeRecoveredExecution(),
                workspace=workspace,
                checkpointer=saver,
            )
            with self.assertRaisesRegex(RuntimeError, "test crash"):
                first.run()
            before_restart = first.current_state()
            self.assertEqual(before_restart["phase"], "EXECUTE")
            self.assertEqual(before_restart["repair_count"], 2)
            self.assertEqual(before_restart["stall_count"], 1)
        self.assertEqual(len(scheduled_first), 1)

        scheduled_second = []

        def recover_second(*args):
            scheduled_second.append(args)
            return True

        second_executor = CountingExecutor()
        second_repair = IncrementRepair()
        with SqliteSaver.from_conn_string(str(db_path)) as saver:
            second = self._make(
                results=[fail_result("VERIFY_A")],
                recovery=recover_second,
                executor=second_executor,
                repair=second_repair,
                workspace=workspace,
                checkpointer=saver,
                max_repairs=99,
            )
            # Resume an interrupted graph execution, rather than submitting a
            # human decision or injecting a synthetic checkpoint payload.
            second._invoke(None)
            state = second.current_state()
        self.assertEqual(state["terminal_reason"], TERMINAL_REPAIR_STALLED)
        self.assertEqual(state["repair_count"], 2)
        self.assertEqual(state["max_repairs"], 3)
        self.assertEqual(state["stall_count"], 2)
        self.assertEqual(
            state["previous_finding_fingerprint"],
            before_restart["previous_finding_fingerprint"],
        )
        self.assertFalse(scheduled_second)
        self.assertFalse(second_repair.calls)
        self.assertEqual(len(second_executor.calls), 1)
        self.assertIsNone(state["pending_human_action"])

    def test_non_callable_recovery_is_rejected_at_construction(self):
        with self.assertRaisesRegex(TypeError, "stall_recovery"):
            self._make(results=[pass_result()], recovery=True)


if __name__ == "__main__":
    unittest.main()
