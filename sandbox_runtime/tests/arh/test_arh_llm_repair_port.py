"""LLMRepairPort tests — the frozen RepairPort contract, closed end to end.

What is actually under test here is the division of authority: the model
produces a proposal, and every field of the resulting ``PolicyRequest`` is
stamped by the harness from provider inputs. Round bookkeeping, trajectory
feeding, and budget trips are the other three properties the Trust Plane
depends on (N2/N4/N6 at the port level).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from . import fixtures as fx
from aedl_sandbox.arh.budget import BudgetConfig, BudgetExceeded, BudgetStop
from aedl_sandbox.arh.llm_repair_port import ARH_ACTOR_ID, LLMRepairPort
from aedl_sandbox.arh.model_adapter import FakeModelAdapter
from aedl_sandbox.arh.repair_agent import AgentConfig
from aedl_sandbox.arh.schema import AUTHORITY_FIELDS, AuthorityFieldError, MalformedProposalError
from aedl_sandbox.arh.trajectory import TrajectoryRecorder
from aedl_sandbox.protocol import ActorIdentity, Finding, PolicyRequest


class LLMRepairPortTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.trajectory = TrajectoryRecorder(self.root, "run-1")
        self.provider_calls: list[tuple[str, str, tuple[Finding, ...]]] = []

    def _provider(self, run_id: str, candidate_id: str, findings):
        findings = tuple(findings)
        self.provider_calls.append((run_id, candidate_id, findings))
        return fx.inputs()

    def _port(self, responses, *, budget=None, agent_config=None, model=None):
        model = model or FakeModelAdapter(responses)
        port = LLMRepairPort(
            model=model,
            inputs_provider=self._provider,
            trajectory=self.trajectory,
            budget=budget
            or BudgetStop(
                BudgetConfig(
                    max_calls=16,
                    max_consecutive_invalid=5,
                    max_consecutive_format_errors=5,
                )
            ),
            agent_config=agent_config,
        )
        return port, model

    def _propose(self, responses, **kwargs) -> tuple[PolicyRequest, FakeModelAdapter]:
        port, model = self._port(responses, **kwargs)
        request = port.propose("run-1", "c1", (fx.finding(),))
        return request, model

    # ------------------------------------------------------- happy path

    def test_request_carries_only_harness_stamped_fields(self) -> None:
        request, model = self._propose([fx.response(fx.valid_text())])
        self.assertIsInstance(request, PolicyRequest)
        self.assertEqual(request.run_id, "run-1")
        self.assertEqual(request.domain_id, "EDD-001")
        self.assertEqual(request.action_id, "arh-r1")
        self.assertEqual(request.action, "repair")
        self.assertEqual(request.candidate_root, Path("runs/run-1/candidate/c1"))
        self.assertEqual(
            request.actor,
            ActorIdentity(actor_id=ARH_ACTOR_ID, actor_kind="agent", run_id="run-1"),
        )
        # V1 holds no capability at all: the grant path stays fail-closed.
        self.assertEqual(request.capability_grants, ())
        self.assertEqual(
            set(request.subject),
            {"design_action", "design_subject"},
        )
        self.assertEqual(
            request.subject["design_action"], "DESIGN_SELECT_COMPONENT"
        )
        self.assertEqual(len(model.requests), 1)

    def test_round_start_and_attempt_are_recorded(self) -> None:
        self._propose([fx.response(fx.valid_text())])
        starts = self.trajectory.rows("round_start")
        self.assertEqual(len(starts), 1)
        payload = starts[0]["payload"]
        self.assertEqual(payload["round"], 1)
        self.assertEqual(payload["candidate_id"], "c1")
        self.assertEqual(payload["findings_before"], ["UNRESOLVED_PART"])
        self.assertEqual(len(payload["context_digest"]), 16)
        attempts = self.trajectory.rows("attempt")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["payload"]["fingerprint12"], fx.FINGERPRINT_NOW[:12])
        self.assertEqual(attempts[0]["payload"]["outcome"], "accepted")

    def test_provider_inputs_are_the_only_identity_source(self) -> None:
        request, _ = self._propose([fx.response(fx.valid_text())])
        self.assertEqual(len(self.provider_calls), 1)
        run_id, candidate_id, findings = self.provider_calls[0]
        self.assertEqual((run_id, candidate_id), ("run-1", "c1"))
        self.assertEqual(findings, (fx.finding(),))
        self.assertEqual(request.domain_id, "EDD-001")
        # The identity fields the model must not touch are in the deny set.
        self.assertIn("domain_id", AUTHORITY_FIELDS)
        self.assertIn("candidate_root", AUTHORITY_FIELDS)
        self.assertEqual(
            request.candidate_root, fx.inputs().candidate_root
        )

    # ---------------------------------------------------- round sequence

    def test_second_round_numbers_up_and_sees_the_first_attempt(self) -> None:
        port, model = self._port([fx.response(fx.valid_text()), fx.response(fx.valid_text())])
        first = port.propose("run-1", "c1", (fx.finding(),))
        second = port.propose("run-1", "c1", (fx.finding(),))
        self.assertEqual(first.action_id, "arh-r1")
        self.assertEqual(second.action_id, "arh-r2")
        self.assertEqual(len(self.trajectory.rows("round_start")), 2)
        # Round 2's prompt embeds round 1's attempt row (D1 attempt_history).
        second_user = model.requests[1].messages[-1].content
        self.assertIn('"attempt_history"', second_user)
        self.assertIn("UNRESOLVED_PART: selected part is outside the allowlist", second_user)
        self.assertIn('"fingerprint12"', second_user)

    def test_rejected_rows_from_a_failed_round_reach_the_next_prompt(self) -> None:
        port, model = self._port(
            [fx.response("not json at all"), fx.response(fx.valid_text())],
            agent_config=AgentConfig(max_attempts=1),
        )
        with self.assertRaises(MalformedProposalError):
            port.propose("run-1", "c1", (fx.finding(),))
        self.assertEqual(self.trajectory.rows("attempt"), [])
        failed = self.trajectory.rows("round_failed")
        self.assertEqual(len(failed), 1)
        rejected = self.trajectory.rejected()
        self.assertEqual(len(rejected), 1)
        self.assertTrue(rejected[0]["reason"].startswith("format:"))

        request = port.propose("run-1", "c1", (fx.finding(),))
        self.assertEqual(request.action_id, "arh-r2")
        second_user = model.requests[1].messages[-1].content
        self.assertIn('"rejected_proposals"', second_user)
        self.assertIn("format: model output is not one JSON object", second_user)

    def test_authority_injection_fails_the_round_and_records_nothing_as_done(self) -> None:
        import json as _json

        raw = _json.dumps({**fx.VALID_PROPOSAL, "capability_grants": []})
        port, _ = self._port([fx.response(raw)])
        with self.assertRaises(AuthorityFieldError):
            port.propose("run-1", "c1", (fx.finding(),))
        self.assertEqual(self.trajectory.rows("attempt"), [])
        self.assertEqual(len(self.trajectory.rows("round_failed")), 1)
        reason = self.trajectory.rows("round_failed")[0]["payload"]["reason"]
        self.assertTrue(reason.startswith("authority_field:"), reason)
        # The round was still announced: failure is observable, not silent.
        self.assertEqual(len(self.trajectory.rows("round_start")), 1)

    # ----------------------------------------------------------- budget

    def test_call_budget_trip_is_recorded_then_propagates(self) -> None:
        budget = BudgetStop(BudgetConfig(max_calls=1))
        port, model = self._port([fx.response(fx.valid_text())], budget=budget)
        port.propose("run-1", "c1", (fx.finding(),))
        with self.assertRaises(BudgetExceeded) as caught:
            port.propose("run-1", "c1", (fx.finding(),))
        self.assertEqual(caught.exception.code, "BUDGET_CALLS")
        self.assertTrue(caught.exception.invalid_run)
        trips = self.trajectory.rows("budget_trip")
        self.assertEqual(len(trips), 1)
        payload = trips[0]["payload"]
        self.assertEqual(payload["round"], 2)
        self.assertEqual(payload["code"], "BUDGET_CALLS")
        self.assertEqual(payload["budget"]["calls"], 1)
        self.assertEqual(len(model.requests), 1, "no model call after the trip")

    def test_invalid_proposal_round_failure_keeps_the_counter_observable(self) -> None:
        budget = BudgetStop(BudgetConfig(max_calls=16, max_consecutive_invalid=5))
        port, _ = self._port(
            [fx.response(fx.valid_text(design_action="FILE_WRITE"))],
            budget=budget,
            agent_config=AgentConfig(max_attempts=1),
        )
        with self.assertRaises(MalformedProposalError):
            port.propose("run-1", "c1", (fx.finding(),))
        self.assertEqual(budget.snapshot()["total_invalid"], 1)
        self.assertEqual(len(self.trajectory.rows("round_failed")), 1)


if __name__ == "__main__":
    unittest.main()
