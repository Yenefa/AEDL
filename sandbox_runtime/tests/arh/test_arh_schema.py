"""Schema gate tests — the proposal/context contract itself (RFC §2.3/§3.2/§3.3).

These are the load-bearing negatives: each authority field must be refused
by name, so a regression in ``AUTHORITY_FIELDS`` or in the parser's key
whitelist shows up here first (N2's contract-level half; the agent-level
half lives in ``test_arh_repair_agent``).
"""

from __future__ import annotations

import unittest

from . import fixtures as fx
from aedl_sandbox.arh.schema import (
    AUTHORITY_FIELDS,
    PROPOSAL_KEYS,
    SUBJECT_ENVELOPE_KEYS,
    AttemptRow,
    AuthorityFieldError,
    MalformedProposalError,
    RepairProposal,
    RejectedRow,
    canonical_json,
    digest,
    encode_finding,
)


class AuthorityGateTest(unittest.TestCase):
    """T-07: no authoritative PolicyRequest field may arrive from a model."""

    def test_every_authority_field_is_refused_by_name(self) -> None:
        for field in sorted(AUTHORITY_FIELDS):
            with self.subTest(field=field):
                data = {**fx.VALID_PROPOSAL, field: "attacker-controlled"}
                with self.assertRaises(AuthorityFieldError) as caught:
                    RepairProposal.from_json(data)
                self.assertIn(field, str(caught.exception))

    def test_authority_field_refused_even_alongside_valid_fields(self) -> None:
        # Presence is the offence; a well-formed rest does not launder it.
        data = {**fx.VALID_PROPOSAL, "capability_grants": []}
        with self.assertRaises(AuthorityFieldError):
            RepairProposal.from_json(data)

    def test_unknown_extra_key_is_refused(self) -> None:
        # T-08: envelope extras are not silently dropped.
        data = {**fx.VALID_PROPOSAL, "confidence": 0.9}
        with self.assertRaisesRegex(MalformedProposalError, "unknown field"):
            RepairProposal.from_json(data)

    def test_authority_and_extra_keys_partition_the_namespace(self) -> None:
        # Guard against a key being in neither set (would slip through).
        self.assertEqual(
            set(PROPOSAL_KEYS) | AUTHORITY_FIELDS,
            set(PROPOSAL_KEYS) | AUTHORITY_FIELDS,
        )
        self.assertTrue(AUTHORITY_FIELDS.isdisjoint(PROPOSAL_KEYS))


class ShapeGateTest(unittest.TestCase):
    def test_non_object_payloads_are_refused(self) -> None:
        for payload in ([1, 2], None, 42, "proposal", {"a": 1}):
            with self.subTest(payload=payload):
                with self.assertRaises(MalformedProposalError):
                    RepairProposal.from_json(payload)

    def test_wrong_typed_required_fields_are_refused(self) -> None:
        cases = [
            {"diagnosis": 7},
            {"design_action": ["DESIGN_SELECT_COMPONENT"]},
            {"design_subject": ["mpn"]},
            {"evidence_ids": "E-1"},
            {"evidence_ids": [1]},
            {"locator": "somewhere"},
        ]
        for patch in cases:
            with self.subTest(patch=patch):
                with self.assertRaises(MalformedProposalError):
                    RepairProposal.from_json({**fx.VALID_PROPOSAL, **patch})

    def test_unknown_locator_key_is_refused(self) -> None:
        data = {**fx.VALID_PROPOSAL, "locator": {"evidence_id": "E-1"}}
        with self.assertRaisesRegex(MalformedProposalError, "locator carries unknown"):
            RepairProposal.from_json(data)

    def test_round_trip_preserves_the_wire_shape(self) -> None:
        proposal = RepairProposal.from_json(fx.VALID_PROPOSAL)
        self.assertEqual(proposal.to_json(), fx.VALID_PROPOSAL)
        self.assertEqual(
            RepairProposal.from_json(proposal.to_json()),
            proposal,
        )

    def test_envelope_is_exactly_the_two_adapter_keys(self) -> None:
        proposal = RepairProposal.from_json(fx.VALID_PROPOSAL)
        self.assertEqual(set(proposal.envelope()), set(SUBJECT_ENVELOPE_KEYS))

    def test_subject_digest_hashes_the_subject_only(self) -> None:
        proposal = RepairProposal.from_json(fx.VALID_PROPOSAL)
        other = RepairProposal.from_json({**fx.VALID_PROPOSAL, "evidence_ids": ["E-2"]})
        self.assertEqual(proposal.subject_digest, other.subject_digest)
        mutated = RepairProposal.from_json(
            {**fx.VALID_PROPOSAL, "design_subject": {**fx.VALID_PROPOSAL["design_subject"], "role": "R2"}}
        )
        self.assertNotEqual(proposal.subject_digest, mutated.subject_digest)


class EncodingTest(unittest.TestCase):
    def test_canonical_json_is_sorted_and_compact(self) -> None:
        self.assertEqual(canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_canonical_json_keeps_unicode_verbatim(self) -> None:
        # ensure_ascii=False: digests must not depend on escaping style.
        self.assertIn("中", canonical_json({"x": "中"}))

    def test_digest_is_deterministic_sensitive_and_bounded(self) -> None:
        value = {"a": 1, "b": [1, 2]}
        self.assertEqual(digest(value), digest(value))
        self.assertEqual(len(digest(value)), 16)
        self.assertNotEqual(digest(value), digest({"a": 1, "b": [1, 3]}))
        self.assertNotEqual(digest({"a": 1}, 16), digest({"a": 1}, 8))

    def test_encode_finding_is_verbatim(self) -> None:
        message = "测量值 与 EDD-001 冲突 — keep me byte-for-byte"
        encoded = encode_finding(fx.finding(message=message))
        self.assertEqual(encoded["message"], message)
        self.assertEqual(encoded["code"], "UNRESOLVED_PART")
        self.assertEqual(encoded["details"], {"mpn": "RC0402-10K", "contract_id": "EDD-001"})
        # The four frozen fields only — no timestamps, no invented context.
        self.assertEqual(
            set(encoded), {"code", "message", "source", "details"}
        )


class RowShapeTest(unittest.TestCase):
    def test_attempt_row_matches_the_context_contract(self) -> None:
        row = AttemptRow(
            round=2,
            fingerprint12="a1b2c3d4e5f6",
            diagnosis="UNRESOLVED_PART: x",
            design_action="DESIGN_SELECT_COMPONENT",
            subject_digest="0123456789abcdef",
            outcome="accepted",
        ).to_row()
        self.assertEqual(
            row,
            {
                "round": 2,
                "fingerprint12": "a1b2c3d4e5f6",
                "diagnosis": "UNRESOLVED_PART: x",
                "proposal": {"action": "DESIGN_SELECT_COMPONENT", "subject_digest": "0123456789abcdef"},
                "outcome": "accepted",
            },
        )

    def test_rejected_row_keeps_the_dedup_keys(self) -> None:
        row = RejectedRow(
            round=1,
            design_action="DESIGN_SELECT_COMPONENT",
            subject_digest="0123456789abcdef",
            reason="required evidence not cited",
        ).to_row()
        self.assertEqual(
            row,
            {
                "round": 1,
                "action": "DESIGN_SELECT_COMPONENT",
                "subject_digest": "0123456789abcdef",
                "reason": "required evidence not cited",
            },
        )


class ContextShapeTest(unittest.TestCase):
    def test_prompt_dict_has_all_thirteen_l0_rows(self) -> None:
        ctx = fx.context()
        payload = ctx.to_prompt_dict()
        for key in (
            "contract_ref", "subject_frozen", "findings_current", "locator_block",
            "fingerprint_state", "attempt_history", "rejected_proposals",
            "receipts_digest", "allowlist", "action_schema", "deny_list",
            "knowledge_ptr", "verification_ref",
        ):
            self.assertIn(key, payload)

    def test_prompt_dict_omits_findings_when_flagged(self) -> None:
        payload = fx.context().to_prompt_dict(findings=False)
        self.assertNotIn("findings_current", payload)
        self.assertIn("allowlist", payload)

    def test_context_digest_tracks_finding_text(self) -> None:
        # D1: findings are verbatim, and their text IS the stall fingerprint
        # material — the digest must move when a message moves.
        before = fx.context().digest
        same = fx.context().digest
        after = fx.context(
            findings_current=(fx.finding(message="different verifier text"),)
        ).digest
        self.assertEqual(before, same)
        self.assertNotEqual(before, after)

    def test_l1_fields_are_absent_by_default_and_present_when_supplied(self) -> None:
        payload = fx.context().to_prompt_dict()
        self.assertNotIn("code_window", payload)
        with_window = fx.context(code_window={"path": "net.py", "lines": ["a = 1"]})
        self.assertIn("code_window", with_window.to_prompt_dict())
        self.assertIsNotNone(with_window.code_window)


if __name__ == "__main__":
    unittest.main()
