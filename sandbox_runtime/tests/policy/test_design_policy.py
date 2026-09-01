"""Closed-world Design Sandbox policy: components, pins and parameters.

Every case in this module must be decided without an LLM, without network and
without consulting model memory about hardware.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aedl_sandbox.protocol import Outcome
from aedl_sandbox.policy import SandboxPolicyEngine

from . import fixtures as fx


class DesignPolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.candidate_root = self.root / "runs" / "run-test-0001" / "candidate"
        self.candidate_root.mkdir(parents=True)
        self.engine = SandboxPolicyEngine.from_document(fx.complete_document(), self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def evaluate(self, action: str, subject: dict, **kwargs) -> object:
        decision = self.engine.evaluate(fx.request(action, subject, candidate_root=self.candidate_root, **kwargs))
        fx.assert_sorted_findings(self, decision)
        self.assertIn(decision.outcome, tuple(Outcome))
        return decision


class UnknownActionTests(DesignPolicyTestCase):
    def test_unknown_action_is_denied(self) -> None:
        decision = self.evaluate("DESIGN_DELETE_NET", {})
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_ACTION_NOT_ALLOWED")

    def test_empty_action_is_denied(self) -> None:
        decision = self.evaluate("", {})
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_ACTION_NOT_ALLOWED")

    def test_wrong_domain_is_denied(self) -> None:
        decision = self.evaluate(
            "DESIGN_SELECT_COMPONENT",
            {"mpn": "TEST-RES-10K", "role": "pullup", "evidence_ids": ["TEST_EVIDENCE_A"]},
            domain_id="EDD-002",
        )
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_DOMAIN_NOT_ALLOWED")


class MalformedSubjectTests(DesignPolicyTestCase):
    def test_subject_must_be_a_mapping(self) -> None:
        for bad in ([], "x", None, 7):
            decision = self.engine.evaluate(
                fx.request("PREFLIGHT", bad, candidate_root=self.candidate_root)
            )
            self.assertEqual(decision.outcome, Outcome.DENY, msg=repr(bad))
            self.assertEqual(decision.reason_code, "POLICY_SUBJECT_MALFORMED")

    def test_missing_required_fields_are_denied(self) -> None:
        cases = [
            ("DESIGN_SELECT_COMPONENT", {"mpn": "TEST-RES-10K"}),
            ("DESIGN_SELECT_COMPONENT", {"role": "pullup", "evidence_ids": []}),
            ("DESIGN_ASSIGN_PIN", {"pin": "GPIO1"}),
            ("DESIGN_ASSIGN_PIN", {"function": "LED", "approval_status": "NOT_REQUIRED"}),
            ("DESIGN_SET_PARAMETER", {"parameter_id": "TEST_PULLUP_OHM"}),
            ("DESIGN_SET_PARAMETER", {"parameter_id": "TEST_PULLUP_OHM", "value": 1, "unit": "ohm"}),
        ]
        for action, subject in cases:
            decision = self.evaluate(action, subject)
            self.assertEqual(decision.outcome, Outcome.DENY, msg=f"{action} {subject}")
            self.assertEqual(decision.reason_code, "POLICY_SUBJECT_MALFORMED")

    def test_extra_subject_fields_are_denied(self) -> None:
        decision = self.evaluate(
            "DESIGN_SELECT_COMPONENT",
            {
                "mpn": "TEST-RES-10K",
                "role": "pullup",
                "evidence_ids": ["TEST_EVIDENCE_A"],
                "bypass": True,
            },
        )
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_SUBJECT_MALFORMED")

    def test_wrong_field_types_are_denied(self) -> None:
        cases = [
            {"mpn": 1, "role": "pullup", "evidence_ids": []},
            {"mpn": "TEST-RES-10K", "role": None, "evidence_ids": []},
            {"mpn": "TEST-RES-10K", "role": "pullup", "evidence_ids": "TEST_EVIDENCE_A"},
            {"mpn": "TEST-RES-10K", "role": "pullup", "evidence_ids": [1]},
        ]
        for subject in cases:
            decision = self.evaluate("DESIGN_SELECT_COMPONENT", subject)
            self.assertEqual(decision.outcome, Outcome.DENY, msg=str(subject))
            self.assertEqual(decision.reason_code, "POLICY_SUBJECT_MALFORMED")

    def test_booleans_are_not_accepted_as_numbers(self) -> None:
        decision = self.evaluate(
            "DESIGN_SET_PARAMETER",
            {
                "parameter_id": "TEST_PULLUP_OHM",
                "value": True,
                "unit": "ohm",
                "evidence_ids": ["TEST_EVIDENCE_A"],
            },
        )
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_SUBJECT_MALFORMED")


class ComponentClosedWorldTests(DesignPolicyTestCase):
    def select(self, mpn: str, role: str = "pullup", evidence: list | None = None):
        return self.evaluate(
            "DESIGN_SELECT_COMPONENT",
            {"mpn": mpn, "role": role, "evidence_ids": evidence if evidence is not None else ["TEST_EVIDENCE_A"]},
        )

    def test_known_component_with_complete_evidence_is_allowed(self) -> None:
        decision = self.select("TEST-RES-10K")
        self.assertEqual(decision.outcome, Outcome.ALLOW)
        self.assertEqual(decision.reason_code, "POLICY_ALLOWED")

    def test_unknown_mpn_is_denied(self) -> None:
        decision = self.select("SOME-OTHER-PART")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_COMPONENT_NOT_ALLOWED")

    def test_prefix_matches_do_not_authorize(self) -> None:
        for mpn in ("TEST-RES-10K-EXTRA", "TEST-RES-10", "TEST-RES-1"):
            decision = self.select(mpn)
            self.assertEqual(decision.outcome, Outcome.DENY, msg=mpn)
            self.assertEqual(decision.reason_code, "POLICY_COMPONENT_NOT_ALLOWED")

    def test_case_changes_do_not_authorize(self) -> None:
        for mpn in ("test-res-10k", "Test-Res-10K", "TEST-res-10k"):
            decision = self.select(mpn)
            self.assertEqual(decision.outcome, Outcome.DENY, msg=mpn)
            self.assertEqual(decision.reason_code, "POLICY_COMPONENT_NOT_ALLOWED")

    def test_whitespace_variants_do_not_authorize(self) -> None:
        for mpn in (" TEST-RES-10K", "TEST-RES-10K ", "\tTEST-RES-10K", "TEST-RES-10K\n"):
            decision = self.select(mpn)
            self.assertEqual(decision.outcome, Outcome.DENY, msg=repr(mpn))
            self.assertEqual(decision.reason_code, "POLICY_COMPONENT_NOT_ALLOWED")

    def test_role_mismatch_is_denied(self) -> None:
        decision = self.select("TEST-RES-10K", role="decoupling")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_COMPONENT_ROLE_NOT_ALLOWED")

    def test_missing_local_datasheet_evidence_blocks(self) -> None:
        engine = SandboxPolicyEngine.from_document(
            fx.complete_document(available={"contract_ids": ["EDD-001.CORE_BASE"], "evidence_ids": []}),
            self.root,
        )
        decision = engine.evaluate(
            fx.request(
                "DESIGN_SELECT_COMPONENT",
                {"mpn": "TEST-RES-10K", "role": "pullup", "evidence_ids": ["TEST_EVIDENCE_A"]},
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_COMPONENT_SOURCE_MISSING")

    def test_source_url_alone_never_satisfies_evidence(self) -> None:
        engine = SandboxPolicyEngine.from_document(
            fx.complete_document(
                available={
                    "contract_ids": ["EDD-001.CORE_BASE"],
                    "evidence_ids": ["LOCAL_MIRROR_ONLY"],
                }
            ),
            self.root,
        )
        decision = engine.evaluate(
            fx.request(
                "DESIGN_SELECT_COMPONENT",
                {
                    "mpn": "TEST-RES-10K",
                    "role": "pullup",
                    "evidence_ids": ["https://vendor.example/TEST-RES-10K.pdf"],
                },
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_COMPONENT_SOURCE_MISSING")
        self.assertIn("https://vendor.example/TEST-RES-10K.pdf", decision.findings[0].details["missing_evidence_ids"])

    def test_empty_evidence_list_blocks_when_evidence_required(self) -> None:
        decision = self.select("TEST-RES-10K", evidence=[])
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_COMPONENT_SOURCE_MISSING")


class PinClosedWorldTests(DesignPolicyTestCase):
    def assign(self, pin: str, function: str = "LED", approval: str = "NOT_REQUIRED"):
        return self.evaluate(
            "DESIGN_ASSIGN_PIN",
            {"pin": pin, "function": function, "approval_status": approval},
        )

    def test_pool_pin_is_allowed(self) -> None:
        decision = self.assign("GPIO1")
        self.assertEqual(decision.outcome, Outcome.ALLOW)
        self.assertEqual(decision.reason_code, "POLICY_ALLOWED")

    def test_hard_forbidden_pin_is_denied(self) -> None:
        decision = self.assign("GPIO35")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PIN_HARD_FORBIDDEN")

    def test_core_reserved_pin_is_denied(self) -> None:
        decision = self.assign("GPIO0")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PIN_CORE_RESERVED")

    def test_soft_reserved_pin_without_approval_is_blocked(self) -> None:
        for approval in ("NOT_REQUIRED", "PENDING", "REJECTED", "", "approved"):
            decision = self.assign("GPIO43", approval=approval)
            self.assertEqual(decision.outcome, Outcome.BLOCKED, msg=approval)
            self.assertEqual(decision.reason_code, "APPROVAL_PIN_OVERRIDE_REQUIRED")

    def test_self_declared_approval_is_not_authoritative(self) -> None:
        """Audit counterexample (Wave 3): a requester-written
        approval_status=APPROVED in the subject must never yield ALLOW."""
        decision = self.assign("GPIO43", approval="APPROVED")
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "APPROVAL_PIN_OVERRIDE_REQUIRED")
        self.assertNotEqual(decision.outcome, Outcome.ALLOW)

    def test_orchestrator_approval_grant_allows_the_override(self) -> None:
        decision = self.engine.evaluate(
            fx.request(
                "DESIGN_ASSIGN_PIN",
                {"pin": "GPIO43", "function": "U0TXD", "approval_status": "PENDING"},
                candidate_root=self.candidate_root,
                actor=fx.ActorIdentity(actor_id="agent-1", actor_kind="agent", run_id="run-test-0001"),
                capability_grants=(fx.approved_pin_grant(),),
            )
        )
        self.assertEqual(decision.outcome, Outcome.ALLOW)
        self.assertEqual(decision.reason_code, "POLICY_ALLOWED")

    def test_approval_grant_must_bind_run_actor_and_receipt(self) -> None:
        actor = fx.ActorIdentity(actor_id="agent-1", actor_kind="agent", run_id="run-test-0001")
        broken_grants = (
            fx.approved_pin_grant(run_id="other-run"),          # wrong run
            fx.approved_pin_grant(actor_id="agent-2"),          # wrong actor
            fx.CapabilityGrant(                                  # unpinned: no receipt
                run_id="run-test-0001",
                actor_id="agent-1",
                capability="approval_status=APPROVED",
                receipt_sha256="",
            ),
            fx.CapabilityGrant(                                  # wrong capability string
                run_id="run-test-0001",
                actor_id="agent-1",
                capability="approval_status=APPROVED ",
                receipt_sha256="a" * 64,
            ),
        )
        for grant in broken_grants:
            decision = self.engine.evaluate(
                fx.request(
                    "DESIGN_ASSIGN_PIN",
                    {"pin": "GPIO43", "function": "U0TXD", "approval_status": "APPROVED"},
                    candidate_root=self.candidate_root,
                    actor=actor,
                    capability_grants=(grant,),
                )
            )
            self.assertEqual(decision.outcome, Outcome.BLOCKED, msg=str(grant))
            self.assertEqual(decision.reason_code, "APPROVAL_PIN_OVERRIDE_REQUIRED")

    def test_approval_grant_without_a_trusted_actor_is_ignored(self) -> None:
        decision = self.engine.evaluate(
            fx.request(
                "DESIGN_ASSIGN_PIN",
                {"pin": "GPIO43", "function": "U0TXD", "approval_status": "APPROVED"},
                candidate_root=self.candidate_root,
                capability_grants=(fx.approved_pin_grant(),),
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "APPROVAL_PIN_OVERRIDE_REQUIRED")

    def test_unknown_pin_is_denied(self) -> None:
        decision = self.assign("GPIO99")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PIN_NOT_ALLOWED")

    def test_absent_from_pool_pins_are_denied_without_memory_inference(self) -> None:
        # GPIO26-GPIO34 are deliberately absent from the pool. The engine must
        # not infer their availability from model knowledge of the ESP32-S3.
        for pin in ("GPIO26", "GPIO27", "GPIO28", "GPIO29", "GPIO30",
                    "GPIO31", "GPIO32", "GPIO33", "GPIO34"):
            decision = self.assign(pin)
            self.assertEqual(decision.outcome, Outcome.DENY, msg=pin)
            self.assertEqual(decision.reason_code, "POLICY_PIN_NOT_ALLOWED")

    def test_pin_matching_is_exact(self) -> None:
        for pin in ("gpio1", "GPIO01", " GPIO1", "GPIO1 "):
            decision = self.assign(pin)
            self.assertEqual(decision.outcome, Outcome.DENY, msg=repr(pin))
            self.assertEqual(decision.reason_code, "POLICY_PIN_NOT_ALLOWED")

    def test_hard_forbidden_takes_precedence_over_missing_approval(self) -> None:
        engine = SandboxPolicyEngine.from_document(
            fx.complete_document(
                pins={
                    "allowed": ["GPIO1"],
                    "core_reserved": [],
                    "hard_forbidden": ["GPIO35"],
                    "soft_reserved": [],
                    "rule_sources": {"GPIO35": "PIN_PSRAM_HARD_FORBIDDEN"},
                },
                available={"contract_ids": [], "evidence_ids": []},
                prerequisites={
                    "required_contract_ids": ["EDD-001.MISSING"],
                    "required_evidence_ids": [],
                    "required_component_resolutions": [],
                },
            ),
            self.root,
        )
        decision = engine.evaluate(
            fx.request(
                "DESIGN_ASSIGN_PIN",
                {"pin": "GPIO35", "function": "LED", "approval_status": "NOT_REQUIRED"},
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PIN_HARD_FORBIDDEN")


class ParameterClosedWorldTests(DesignPolicyTestCase):
    def set_param(self, parameter_id: str, value, unit: str, evidence=None):
        return self.evaluate(
            "DESIGN_SET_PARAMETER",
            {
                "parameter_id": parameter_id,
                "value": value,
                "unit": unit,
                "evidence_ids": evidence if evidence is not None else ["TEST_EVIDENCE_A"],
            },
        )

    def test_known_parameter_in_bounds_is_allowed(self) -> None:
        decision = self.set_param("TEST_PULLUP_OHM", 10000.0, "ohm")
        self.assertEqual(decision.outcome, Outcome.ALLOW)

    def test_range_bounded_parameter_in_bounds_is_allowed(self) -> None:
        decision = self.set_param("TEST_RANGE_OHM", 5.0, "ohm")
        self.assertEqual(decision.outcome, Outcome.ALLOW)

    def test_nan_value_is_never_allowed(self) -> None:
        """Audit counterexample (Wave 3): bounds=[0,10] with value=NaN must
        not be ALLOW. Non-finite numbers are refused at subject validation."""
        for parameter_id in ("TEST_RANGE_OHM", "TEST_PULLUP_OHM"):
            decision = self.set_param(parameter_id, float("nan"), "ohm")
            self.assertNotEqual(decision.outcome, Outcome.ALLOW, msg=parameter_id)
            self.assertEqual(decision.outcome, Outcome.DENY, msg=parameter_id)
            self.assertEqual(decision.reason_code, "POLICY_SUBJECT_MALFORMED", msg=parameter_id)

    def test_infinite_values_are_never_allowed(self) -> None:
        for value in (float("inf"), float("-inf")):
            for parameter_id in ("TEST_RANGE_OHM", "TEST_PULLUP_OHM"):
                decision = self.set_param(parameter_id, value, "ohm")
                self.assertNotEqual(decision.outcome, Outcome.ALLOW, msg=f"{parameter_id} {value}")
                self.assertEqual(decision.outcome, Outcome.DENY, msg=f"{parameter_id} {value}")

    def test_parameter_record_refuses_non_finite_values_directly(self) -> None:
        from aedl_sandbox.policy.document import ParameterRecord

        bounded = ParameterRecord(
            parameter_id="BOUNDS",
            value_type="number",
            unit="ohm",
            required_evidence_ids=(),
            minimum=0.0,
            maximum=10.0,
        )
        for value in (float("nan"), float("inf"), float("-inf")):
            self.assertFalse(bounded.accepts(value), msg=repr(value))
        self.assertTrue(bounded.accepts(5.0))

    def test_unknown_parameter_is_denied(self) -> None:
        decision = self.set_param("TEST_UNKNOWN", 1.0, "ohm")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PARAMETER_NOT_ALLOWED")

    def test_value_outside_allowed_set_is_denied(self) -> None:
        decision = self.set_param("TEST_PULLUP_OHM", 4700.0, "ohm")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PARAMETER_OUT_OF_BOUNDS")

    def test_unit_mismatch_is_denied(self) -> None:
        decision = self.set_param("TEST_PULLUP_OHM", 10000.0, "kohm")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PARAMETER_UNIT_MISMATCH")

    def test_value_type_mismatch_is_denied(self) -> None:
        decision = self.set_param("TEST_PULLUP_OHM", "10000", "ohm")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PARAMETER_TYPE_INVALID")

    def test_string_parameter_allowed_values(self) -> None:
        self.assertEqual(self.set_param("TEST_LED_COLOR", "red", "none").outcome, Outcome.ALLOW)
        decision = self.set_param("TEST_LED_COLOR", "blue", "none")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PARAMETER_OUT_OF_BOUNDS")

    def test_missing_parameter_evidence_blocks(self) -> None:
        engine = SandboxPolicyEngine.from_document(
            fx.complete_document(available={"contract_ids": ["EDD-001.CORE_BASE"], "evidence_ids": []}),
            self.root,
        )
        decision = engine.evaluate(
            fx.request(
                "DESIGN_SET_PARAMETER",
                {
                    "parameter_id": "TEST_PULLUP_OHM",
                    "value": 10000.0,
                    "unit": "ohm",
                    "evidence_ids": ["TEST_EVIDENCE_A"],
                },
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_PARAMETER_SOURCE_MISSING")


if __name__ == "__main__":
    unittest.main()
