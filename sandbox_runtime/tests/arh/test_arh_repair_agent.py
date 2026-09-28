"""RepairAgent static-gate tests — where an untrusted string dies or passes.

The negative cases are the point of this file. Each one documents an attack
or failure mode from the red-team report (RFC threats T-07/T-08, N2, D2)
and asserts the observable consequence: no retry after an authority
injection, counters on the budget, a reason row in the trajectory.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from . import fixtures as fx
from aedl_sandbox.arh.budget import BudgetConfig, BudgetExceeded, BudgetStop
from aedl_sandbox.arh.model_adapter import FakeModelAdapter
from aedl_sandbox.arh.repair_agent import AgentConfig, RepairAgent
from aedl_sandbox.arh.schema import AuthorityFieldError, MalformedProposalError
from aedl_sandbox.arh.trajectory import TrajectoryRecorder


class RepairAgentGateTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def _run(
        self,
        responses,
        *,
        ctx=None,
        budget=None,
        config=None,
        round_no: int = 1,
    ):
        model = FakeModelAdapter(responses)
        budget = budget or BudgetStop(
            BudgetConfig(max_calls=16, max_consecutive_invalid=5, max_consecutive_format_errors=5)
        )
        trajectory = TrajectoryRecorder(self.root, "run-1")
        agent = RepairAgent(model, config)
        proposal = agent.propose(
            ctx or fx.context(),
            budget=budget,
            trajectory=trajectory,
            round_no=round_no,
        )
        return proposal, model, budget, trajectory

    def _expect_error(self, error_type, responses, **kwargs):
        model = FakeModelAdapter(responses)
        budget = kwargs.pop(
            "budget",
            BudgetStop(
                BudgetConfig(max_calls=16, max_consecutive_invalid=5, max_consecutive_format_errors=5)
            ),
        )
        trajectory = kwargs.pop("trajectory", TrajectoryRecorder(self.root, "run-1"))
        agent = RepairAgent(model, kwargs.pop("config", None))
        with self.assertRaises(error_type) as caught:
            agent.propose(
                kwargs.pop("ctx", None) or fx.context(),
                budget=budget,
                trajectory=trajectory,
                round_no=kwargs.pop("round_no", 1),
            )
        self.assertEqual(kwargs, {})
        return caught, model, budget, trajectory

    # ------------------------------------------------------------ accepted

    def test_valid_proposal_is_accepted_on_the_first_call(self) -> None:
        proposal, model, budget, trajectory = self._run([fx.response(fx.valid_text())])
        self.assertEqual(proposal.design_action, "DESIGN_SELECT_COMPONENT")
        self.assertEqual(proposal.evidence_ids, ("E-1",))
        self.assertEqual(len(model.requests), 1)
        snapshot = budget.snapshot()
        self.assertEqual(snapshot["calls"], 1)
        self.assertEqual(snapshot["total_invalid"], 0)
        self.assertEqual(snapshot["total_format_errors"], 0)
        self.assertEqual(len(trajectory.rows("model_call")), 1)
        self.assertEqual(trajectory.rows("rejected"), [])

    def test_fenced_json_is_formatting_not_a_fault(self) -> None:
        fenced = f"```json\n{fx.valid_text()}\n```"
        _, _, budget, _ = self._run([fx.response(fenced)])
        self.assertEqual(budget.snapshot()["total_format_errors"], 0)

    def test_format_error_then_recovery_resets_the_consecutive_counter(self) -> None:
        _, _, budget, trajectory = self._run(
            [fx.response("definitely not json"), fx.response(fx.valid_text())]
        )
        snapshot = budget.snapshot()
        self.assertEqual(snapshot["total_format_errors"], 1)
        self.assertEqual(snapshot["consecutive_format_errors"], 0)
        reasons = [row["payload"]["reason"] for row in trajectory.rows("rejected")]
        self.assertEqual(len(reasons), 1)
        self.assertTrue(reasons[0].startswith("format:"))

    def test_prompt_renders_deny_list_at_both_ends(self) -> None:
        _, model, _, _ = self._run([fx.response(fx.valid_text())])
        system, user = (m.content for m in model.requests[0].messages)
        for item in fx.DENY_LIST:
            self.assertIn(item, system)
            self.assertIn(item, user)
        self.assertIn("NO execution authority", system)
        # Findings travel verbatim (D1): the raw message is in the prompt.
        self.assertIn("selected part is not in the allowlist", user)
        self.assertNotIn("domain_id", user)

    def test_model_call_event_carries_usage_and_prompt_digest(self) -> None:
        _, _, _, trajectory = self._run([fx.response(fx.valid_text())])
        payload = trajectory.rows("model_call")[0]["payload"]
        self.assertEqual(payload["usage"]["input_tokens"], 100)
        self.assertEqual(payload["usage"]["output_tokens"], 50)
        self.assertEqual(payload["usage"]["cache_read_tokens"], 10)
        self.assertEqual(len(payload["prompt_digest"]), 16)
        self.assertEqual(payload["model_id"], "fake-model")

    # ---------------------------------------------------------- authority

    def test_authority_field_is_refused_without_spending_a_retry(self) -> None:
        # N2's agent-level evidence: injection is detected, counted, and the
        # loop stops — a regression that retried instead would show up as
        # len(model.requests) > 1 here.
        raw = json.dumps({**fx.VALID_PROPOSAL, "actor": "root"}, ensure_ascii=False)
        _, model, budget, trajectory = self._expect_error(
            AuthorityFieldError, [fx.response(raw), fx.response(fx.valid_text())]
        )
        self.assertEqual(len(model.requests), 1, "authority violation must not retry")
        self.assertEqual(budget.snapshot()["total_invalid"], 1)
        reason = trajectory.rows("rejected")[0]["payload"]["reason"]
        self.assertTrue(reason.startswith("authority_field:"), reason)
        self.assertIn("actor", reason)

    def test_authority_rejection_never_records_an_attempt(self) -> None:
        raw = json.dumps({**fx.VALID_PROPOSAL, "run_id": "elsewhere"}, ensure_ascii=False)
        _, _, _, trajectory = self._expect_error(
            AuthorityFieldError, [fx.response(raw)]
        )
        self.assertEqual(trajectory.rows("attempt"), [])

    # -------------------------------------------------------- vocabulary

    def test_action_outside_the_v1_whitelist_is_refused_then_corrected(self) -> None:
        bad = fx.valid_text(design_action="FILE_WRITE")
        proposal, model, budget, trajectory = self._run(
            [fx.response(bad), fx.response(fx.valid_text())]
        )
        self.assertEqual(proposal.design_action, "DESIGN_SELECT_COMPONENT")
        self.assertEqual(len(model.requests), 2)
        self.assertEqual(budget.snapshot()["total_invalid"], 1)
        feedback = model.requests[1].messages[-1].content
        self.assertIn("rejected", feedback)
        self.assertIn("FILE_WRITE", feedback)
        reason = trajectory.rows("rejected")[0]["payload"]["reason"]
        self.assertIn("outside the V1 whitelist", reason)

    def test_action_absent_from_the_run_schema_is_refused(self) -> None:
        ctx = fx.context(action_schema={})
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError, [fx.response(fx.valid_text())], ctx=ctx, config=AgentConfig(max_attempts=1)
        )
        reason = trajectory.rows("rejected")[0]["payload"]["reason"]
        self.assertIn("not offered by this run's action_schema", reason)

    def test_subject_missing_required_field_is_refused(self) -> None:
        subject = dict(fx.VALID_PROPOSAL["design_subject"])
        del subject["role"]
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(design_subject=subject))],
            config=AgentConfig(max_attempts=1),
        )
        reason = trajectory.rows("rejected")[0]["payload"]["reason"]
        self.assertIn("!= required", reason)

    def test_subject_extra_field_is_refused(self) -> None:
        # T-08 at subject level: a smuggled field is not dropped silently.
        subject = {**fx.VALID_PROPOSAL["design_subject"], "approval_status": "auto"}
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(design_subject=subject))],
            config=AgentConfig(max_attempts=1),
        )
        self.assertIn("!= required", trajectory.rows("rejected")[0]["payload"]["reason"])

    def test_subject_field_failing_the_contract_predicate_is_refused(self) -> None:
        subject = {**fx.VALID_PROPOSAL["design_subject"], "evidence_ids": "E-1"}
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(design_subject=subject))],
            config=AgentConfig(max_attempts=1),
        )
        self.assertIn(
            "contract predicate",
            trajectory.rows("rejected")[0]["payload"]["reason"],
        )

    def test_design_action_missing_from_subject_is_refused(self) -> None:
        # The common "model emits only the action name" failure.
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(design_subject={"mpn": "RC0402-10K"}))],
            config=AgentConfig(max_attempts=1),
        )
        self.assertIn("!= required", trajectory.rows("rejected")[0]["payload"]["reason"])

    # ------------------------------------------------------------ evidence

    def test_evidence_outside_the_allowlist_is_refused(self) -> None:
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(evidence_ids=["E-99"]))],
            config=AgentConfig(max_attempts=1),
        )
        reason = trajectory.rows("rejected")[0]["payload"]["reason"]
        self.assertIn("not in allowlist.evidence_ids", reason)
        self.assertIn("E-99", reason)

    def test_required_evidence_must_be_cited(self) -> None:
        subject = {**fx.VALID_PROPOSAL["design_subject"], "evidence_ids": ["E-2"]}
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(design_subject=subject, evidence_ids=["E-2"]))],
            config=AgentConfig(max_attempts=1),
        )
        reason = trajectory.rows("rejected")[0]["payload"]["reason"]
        self.assertIn("required evidence not cited", reason)
        self.assertIn("E-1", reason)

    def test_component_must_be_in_the_allowlist(self) -> None:
        subject = {**fx.VALID_PROPOSAL["design_subject"], "mpn": "SNEAKY-1"}
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(design_subject=subject))],
            config=AgentConfig(max_attempts=1),
        )
        self.assertIn(
            "not in allowlist.allowed_components",
            trajectory.rows("rejected")[0]["payload"]["reason"],
        )

    def test_missing_component_allowlist_fails_closed(self) -> None:
        ctx = fx.context(allowlist={"evidence_ids": ["E-1", "E-2"]})
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text())],
            ctx=ctx,
            config=AgentConfig(max_attempts=1),
        )
        self.assertIn(
            "fail-closed",
            trajectory.rows("rejected")[0]["payload"]["reason"],
        )

    # ----------------------------------------------------------- diagnosis

    def test_diagnosis_must_cite_a_finding_code_or_unknown(self) -> None:
        vague = fx.valid_text(diagnosis="the part value is wrong somehow")
        proposal, model, budget, _ = self._run(
            [fx.response(vague), fx.response(fx.valid_text(diagnosis="UNKNOWN: no anchor"))]
        )
        self.assertIn("UNKNOWN", proposal.diagnosis)
        self.assertEqual(len(model.requests), 2)
        self.assertEqual(budget.snapshot()["total_invalid"], 1)

    def test_empty_diagnosis_is_refused(self) -> None:
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(diagnosis="   "))],
            config=AgentConfig(max_attempts=1),
        )
        self.assertIn(
            "diagnosis is empty",
            trajectory.rows("rejected")[0]["payload"]["reason"],
        )

    def test_overlong_diagnosis_is_refused(self) -> None:
        long_text = "UNRESOLVED_PART: " + "x" * 40
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(diagnosis=long_text))],
            config=AgentConfig(max_attempts=1, max_diagnosis_chars=20),
        )
        self.assertIn("chars, max 20", trajectory.rows("rejected")[0]["payload"]["reason"])

    # ------------------------------------------------------------- locator

    def test_locator_path_traversal_is_refused(self) -> None:
        _, _, _, trajectory = self._expect_error(
            MalformedProposalError,
            [fx.response(fx.valid_text(locator={"path": "../../etc/passwd"}))],
            config=AgentConfig(max_attempts=1),
        )
        self.assertIn(
            "must be relative",
            trajectory.rows("rejected")[0]["payload"]["reason"],
        )

    # -------------------------------------------------------------- budget

    def test_consecutive_invalid_proposals_trip_the_budget(self) -> None:
        budget = BudgetStop(BudgetConfig(max_calls=16, max_consecutive_invalid=2))
        responses = [fx.response(fx.valid_text(design_action="FILE_WRITE"))] * 3
        _, model, _, _ = self._expect_error(
            BudgetExceeded, responses, budget=budget
        )
        self.assertEqual(len(model.requests), 2, "trip must stop the loop at the limit")
        self.assertEqual(budget.snapshot()["total_invalid"], 2)

    def test_consecutive_format_errors_trip_the_budget(self) -> None:
        budget = BudgetStop(BudgetConfig(max_calls=16, max_consecutive_format_errors=2))
        _, model, _, _ = self._expect_error(
            BudgetExceeded, [fx.response("not json at all")] * 3, budget=budget
        )
        self.assertEqual(len(model.requests), 2)
        self.assertEqual(budget.snapshot()["total_format_errors"], 2)

    def test_exhausted_call_budget_stops_before_the_model_is_called(self) -> None:
        budget = BudgetStop(BudgetConfig(max_calls=0))
        _, model, _, _ = self._expect_error(
            BudgetExceeded, [fx.response(fx.valid_text())], budget=budget
        )
        self.assertEqual(len(model.requests), 0, "N6: the budget is checked first")

    def test_retries_exhaust_raise_the_last_validation_error(self) -> None:
        bad = fx.valid_text(design_action="FILE_WRITE")
        _, model, budget, _ = self._expect_error(
            MalformedProposalError,
            [fx.response(bad)] * 3,
            config=AgentConfig(max_attempts=3),
        )
        self.assertEqual(len(model.requests), 3)
        self.assertEqual(budget.snapshot()["total_invalid"], 3)

    def test_config_rejects_a_round_that_may_not_call_the_model(self) -> None:
        with self.assertRaises(ValueError):
            AgentConfig(max_attempts=0)


if __name__ == "__main__":
    unittest.main()
