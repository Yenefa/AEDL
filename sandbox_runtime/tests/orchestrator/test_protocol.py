"""Contract tests for the frozen public protocol (Wave 0 interface freeze).

These tests pin the public surface consumed by Agents M and L: enum
values, frozen dataclasses, JSON-compatible fields, and runtime-checkable
ports. Any protocol.py change that breaks them is interface drift.
"""

import json
import unittest
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path

from aedl_sandbox.protocol import (
    REASON_CODE_PREFIXES,
    ActorIdentity,
    ApprovalStatus,
    CapabilityGrant,
    EvidenceEvent,
    EvidenceReceipt,
    EvidenceStatus,
    ExecutionResult,
    ExecutorPort,
    Finding,
    HumanApprovalReceipt,
    LifecycleStatus,
    Outcome,
    PolicyDecision,
    PolicyPort,
    PolicyRequest,
    PromotionDecision,
    PromotionRequest,
    RepairPort,
    TrustPort,
    VerificationResult,
    VerificationStatus,
    VerifierPort,
)


def _sample_instances():
    return [
        Finding(code="POLICY_TEST", message="m", source="test"),
        PolicyRequest(
            run_id="r",
            domain_id="d",
            action_id="a",
            action="act",
            candidate_root=Path("c"),
            subject={},
        ),
        PolicyDecision(outcome=Outcome.ALLOW, reason_code="POLICY_TEST"),
        ExecutionResult(success=True, action_id="a", candidate_id="c"),
        VerificationResult(status=VerificationStatus.PASS, candidate_id="c"),
        EvidenceEvent(
            run_id="r",
            candidate_id="c",
            event_type="verify",
            input_hashes={},
            payload={},
        ),
        EvidenceReceipt(event_hash="h", run_id="r", candidate_id="c", valid=True),
        PromotionRequest(
            run_id="r",
            candidate_id="c",
            candidate_hash="h",
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
        ),
        PromotionDecision(outcome=Outcome.ALLOW, reason_code="APPROVAL_TEST"),
    ]


class EnumContractTests(unittest.TestCase):
    def test_outcome_members_and_values(self):
        self.assertEqual(
            {member.name: member.value for member in Outcome},
            {"ALLOW": "ALLOW", "DENY": "DENY", "BLOCKED": "BLOCKED"},
        )
        for member in Outcome:
            self.assertIsInstance(member, str)

    def test_lifecycle_status_members_and_values(self):
        self.assertEqual(
            {member.name: member.value for member in LifecycleStatus},
            {
                "DRAFT": "DRAFT",
                "CANDIDATE": "CANDIDATE",
                "REJECTED": "REJECTED",
                "PROMOTED": "PROMOTED",
                "FROZEN": "FROZEN",
            },
        )

    def test_verification_status_members_and_values(self):
        self.assertEqual(
            {member.name: member.value for member in VerificationStatus},
            {"NOT_RUN": "NOT_RUN", "PASS": "PASS", "FAIL": "FAIL", "BLOCKED": "BLOCKED"},
        )

    def test_approval_status_members_and_values(self):
        self.assertEqual(
            {member.name: member.value for member in ApprovalStatus},
            {
                "NOT_REQUIRED": "NOT_REQUIRED",
                "PENDING": "PENDING",
                "APPROVED": "APPROVED",
                "REJECTED": "REJECTED",
            },
        )

    def test_evidence_status_members_and_values(self):
        self.assertEqual(
            {member.name: member.value for member in EvidenceStatus},
            {"MISSING": "MISSING", "PARTIAL": "PARTIAL", "COMPLETE": "COMPLETE", "INVALID": "INVALID"},
        )

    def test_reason_code_prefixes_namespace(self):
        self.assertEqual(
            REASON_CODE_PREFIXES,
            ("POLICY_", "EVIDENCE_", "EXECUTION_", "VERIFY_", "REPAIR_", "APPROVAL_", "STATE_"),
        )


class FrozenDataclassContractTests(unittest.TestCase):
    def test_all_contract_types_are_dataclasses(self):
        for instance in _sample_instances():
            with self.subTest(type(instance).__name__):
                self.assertTrue(is_dataclass(type(instance)))

    def test_all_contract_types_reject_mutation(self):
        for instance in _sample_instances():
            first_field = fields(instance)[0].name
            current = getattr(instance, first_field)
            with self.subTest(type(instance).__name__):
                with self.assertRaises(FrozenInstanceError):
                    setattr(instance, first_field, current)

    def test_default_empty_collections(self):
        self.assertEqual(Finding(code="c", message="m", source="s").details, {})
        self.assertEqual(
            PolicyDecision(outcome=Outcome.DENY, reason_code="r").findings, ()
        )
        result = ExecutionResult(success=True, action_id="a", candidate_id="c")
        self.assertEqual(result.artifacts, ())
        self.assertEqual(result.findings, ())
        self.assertEqual(
            VerificationResult(status=VerificationStatus.FAIL, candidate_id="c").findings,
            (),
        )
        self.assertEqual(
            PromotionDecision(outcome=Outcome.DENY, reason_code="r").findings, ()
        )

    def test_finding_details_default_is_not_shared_between_instances(self):
        first = Finding(code="c", message="m", source="s")
        second = Finding(code="c", message="m", source="s")
        self.assertIsNot(first.details, second.details)


class JsonCompatibilityContractTests(unittest.TestCase):
    def test_finding_details_round_trips_through_json(self):
        details = {
            "none": None,
            "bool": True,
            "int": 7,
            "float": 1.5,
            "str": "text",
            "list": [1, "two", None, {"nested": False}],
            "dict": {"inner": [3.25, "x"]},
        }
        finding = Finding(code="c", message="m", source="s", details=details)
        self.assertEqual(json.loads(json.dumps(finding.details)), details)

    def test_evidence_event_payload_and_input_hashes_are_json_serializable(self):
        event = EvidenceEvent(
            run_id="r",
            candidate_id="c",
            event_type="verify",
            input_hashes={"contracts": "deadbeef"},
            payload={"status": "PASS", "counts": {"errors": 0}},
        )
        payload = json.loads(json.dumps(event.payload))
        self.assertEqual(payload["status"], "PASS")
        self.assertEqual(json.loads(json.dumps(event.input_hashes))["contracts"], "deadbeef")


class _PolicyStub:
    def evaluate(self, request):
        return PolicyDecision(outcome=Outcome.DENY, reason_code="POLICY_TEST")


class _ExecutorStub:
    def execute(self, request):
        return ExecutionResult(success=True, action_id=request.action_id, candidate_id="c")


class _VerifierStub:
    def verify(self, run_id, candidate_id, candidate_root):
        return VerificationResult(status=VerificationStatus.PASS, candidate_id=candidate_id)


class _RepairStub:
    def propose(self, run_id, candidate_id, findings):
        return PolicyRequest(
            run_id=run_id,
            domain_id="d",
            action_id="repair",
            action="repair",
            candidate_root=Path("c"),
            subject={},
        )


class _TrustStub:
    def record(self, event):
        return EvidenceReceipt(
            event_hash="h", run_id=event.run_id, candidate_id=event.candidate_id, valid=True
        )

    def assess_promotion(self, request):
        return PromotionDecision(outcome=Outcome.DENY, reason_code="APPROVAL_TEST")


class _EmptyStub:
    pass


class RuntimeCheckablePortContractTests(unittest.TestCase):
    def test_stub_implementations_satisfy_their_ports(self):
        self.assertIsInstance(_PolicyStub(), PolicyPort)
        self.assertIsInstance(_ExecutorStub(), ExecutorPort)
        self.assertIsInstance(_VerifierStub(), VerifierPort)
        self.assertIsInstance(_RepairStub(), RepairPort)
        self.assertIsInstance(_TrustStub(), TrustPort)

    def test_unrelated_objects_satisfy_no_port(self):
        empty = _EmptyStub()
        self.assertNotIsInstance(empty, PolicyPort)
        self.assertNotIsInstance(empty, ExecutorPort)
        self.assertNotIsInstance(empty, VerifierPort)
        self.assertNotIsInstance(empty, RepairPort)
        self.assertNotIsInstance(empty, TrustPort)

    def test_trust_port_requires_both_methods(self):
        class _RecordOnly:
            def record(self, event):
                ...

        self.assertNotIsInstance(_RecordOnly(), TrustPort)


class V2ProtocolAdditionTests(unittest.TestCase):
    """Wave 3 (protocol V2) additions: verified bundle reference, actor and
    capability identity, candidate-bound human approval receipts, and
    actor-stamped execution/verification results.

    V2 is additive only: every V1 construction must keep working, and every
    V2 field defaults to a V1-neutral value so V1 callers are unaffected.
    """

    def test_v2_types_are_frozen_dataclasses(self):
        instances = [
            ActorIdentity(actor_id="compiler-1"),
            CapabilityGrant(run_id="r", actor_id="compiler-1", capability="writer=compiler"),
            HumanApprovalReceipt(run_id="r", candidate_sha256="h"),
        ]
        for instance in instances:
            with self.subTest(type(instance).__name__):
                self.assertTrue(is_dataclass(type(instance)))
                first_field = fields(instance)[0].name
                with self.assertRaises(FrozenInstanceError):
                    setattr(instance, first_field, getattr(instance, first_field))

    def test_v2_actor_identity_fields(self):
        identity = ActorIdentity(actor_id="compiler-1")
        self.assertEqual(identity.actor_kind, "")
        self.assertEqual(identity.run_id, "")
        full = ActorIdentity(actor_id="v", actor_kind="verifier", run_id="r")
        self.assertEqual(
            (full.actor_id, full.actor_kind, full.run_id), ("v", "verifier", "r")
        )

    def test_v2_capability_grant_fields(self):
        grant = CapabilityGrant(run_id="r", actor_id="compiler-1", capability="writer=compiler")
        self.assertEqual(grant.receipt_sha256, "")
        pinned = CapabilityGrant(
            run_id="r",
            actor_id="compiler-1",
            capability="writer=compiler",
            receipt_sha256="a" * 64,
        )
        self.assertEqual(pinned.receipt_sha256, "a" * 64)

    def test_v2_human_approval_receipt_binds_run_and_candidate_hash(self):
        receipt = HumanApprovalReceipt(run_id="r", candidate_sha256="h")
        self.assertEqual(receipt.decision, ApprovalStatus.APPROVED)
        self.assertEqual(receipt.approver_role, "human_reviewer")
        self.assertEqual(receipt.approved_by, "")
        self.assertEqual(receipt.approved_at, "")
        rejected = HumanApprovalReceipt(
            run_id="r",
            candidate_sha256="h",
            decision=ApprovalStatus.REJECTED,
            approved_by="reviewer@example",
            approver_role="senior_reviewer",
            approved_at="2026-09-01T00:00:00+00:00",
        )
        self.assertEqual(rejected.decision, ApprovalStatus.REJECTED)
        self.assertEqual(rejected.approver_role, "senior_reviewer")
        self.assertEqual(rejected.approved_at, "2026-09-01T00:00:00+00:00")

    def test_v2_policy_request_fields_default_to_v1_neutral(self):
        request = PolicyRequest(
            run_id="r",
            domain_id="d",
            action_id="a",
            action="act",
            candidate_root=Path("c"),
            subject={},
        )
        self.assertEqual(request.verified_bundle_sha256, "")
        self.assertEqual(request.verified_manifest_path, "")
        self.assertIsNone(request.actor)
        self.assertEqual(request.capability_grants, ())

    def test_v2_policy_request_carries_bundle_actor_and_grants(self):
        grant = CapabilityGrant(
            run_id="r",
            actor_id="compiler-1",
            capability="writer=compiler",
            receipt_sha256="b" * 64,
        )
        request = PolicyRequest(
            run_id="r",
            domain_id="d",
            action_id="a",
            action="act",
            candidate_root=Path("c"),
            subject={},
            verified_bundle_sha256="c" * 64,
            verified_manifest_path="bundle/sandbox_bundle_manifest_v1.json",
            actor=ActorIdentity(actor_id="compiler-1", actor_kind="compiler", run_id="r"),
            capability_grants=(grant,),
        )
        self.assertEqual(request.verified_bundle_sha256, "c" * 64)
        self.assertEqual(
            request.verified_manifest_path, "bundle/sandbox_bundle_manifest_v1.json"
        )
        self.assertEqual(request.actor.actor_kind, "compiler")
        self.assertEqual(request.capability_grants, (grant,))

    def test_v2_promotion_request_approval_receipt_defaults_to_none(self):
        request = PromotionRequest(
            run_id="r",
            candidate_id="c",
            candidate_hash="h",
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
        )
        self.assertIsNone(request.approval_receipt)

    def test_v2_promotion_request_carries_approval_receipt(self):
        receipt = HumanApprovalReceipt(
            run_id="r",
            candidate_sha256="h",
            approved_by="human",
            approved_at="2026-09-01T00:00:00+00:00",
        )
        request = PromotionRequest(
            run_id="r",
            candidate_id="c",
            candidate_hash="h",
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
            approval_receipt=receipt,
        )
        self.assertEqual(request.approval_receipt.candidate_sha256, "h")
        self.assertEqual(request.approval_receipt.run_id, "r")

    def test_v2_execution_and_verification_results_carry_actor_id(self):
        execution = ExecutionResult(success=True, action_id="a", candidate_id="c")
        self.assertEqual(execution.actor_id, "")
        verification = VerificationResult(status=VerificationStatus.PASS, candidate_id="c")
        self.assertEqual(verification.actor_id, "")
        stamped = ExecutionResult(
            success=True, action_id="a", candidate_id="c", actor_id="compiler-1"
        )
        self.assertEqual(stamped.actor_id, "compiler-1")
        checked = VerificationResult(
            status=VerificationStatus.PASS, candidate_id="c", actor_id="verifier-1"
        )
        self.assertEqual(checked.actor_id, "verifier-1")


if __name__ == "__main__":
    unittest.main()
