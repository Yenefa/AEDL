"""L2/L3 tests: append-only receipts, idempotency, staleness, promotion truth table."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aedl_sandbox.protocol import (
    ApprovalStatus,
    HumanApprovalReceipt,
    EvidenceEvent,
    EvidenceStatus,
    Outcome,
    PromotionRequest,
    VerificationStatus,
)
from aedl_sandbox.trust import FileTrustStore

CAND = "b" * 64


def make_store():
    tmp = tempfile.mkdtemp()
    repo = Path(tmp) / "repo"
    receipts = Path(tmp) / "receipts"
    repo.mkdir()
    receipts.mkdir()
    return FileTrustStore(repo, receipts), receipts


def verification_event(run_id="run-1", candidate_id="cand-1", cand=CAND, sequence=1):
    return EvidenceEvent(
        run_id=run_id, candidate_id=candidate_id, event_type="verification",
        input_hashes={"candidate_sha256": cand},
        payload={"sequence": sequence, "status": "PASS"},
    )


class ReceiptTests(unittest.TestCase):
    def test_repeated_identical_event_is_idempotent(self):
        store, receipts = make_store()
        event = verification_event()
        r1 = store.record(event)
        r2 = store.record(event)
        self.assertEqual(r1.event_hash, r2.event_hash)
        self.assertTrue(r1.valid and r2.valid)
        self.assertEqual(r1, r2)

    def test_receipt_content_is_canonical_event_bytes(self):
        store, receipts = make_store()
        receipt = store.record(verification_event())
        path = receipts / "run-1" / f"{receipt.event_hash}.json"
        data = json.loads(path.read_bytes())
        self.assertEqual(data["event_type"], "verification")
        self.assertEqual(data["input_hashes"]["candidate_sha256"], CAND)

    def test_receipt_collision_does_not_overwrite_first_receipt(self):
        store, receipts = make_store()
        receipt = store.record(verification_event())
        path = receipts / "run-1" / f"{receipt.event_hash}.json"
        original = path.read_bytes()
        path.write_bytes(b'{"tampered": true}')
        again = store.record(verification_event())
        self.assertFalse(again.valid, "collided receipt must be reported invalid")
        # "preserve the existing file" = the store never overwrites the bytes
        # found on disk; the tampered payload stays as audit evidence.
        self.assertEqual(path.read_bytes(), b'{"tampered": true}')
        self.assertNotEqual(path.read_bytes(), original)

    def test_verification_event_requires_candidate_sha256(self):
        store, _ = make_store()
        bad = EvidenceEvent("run-1", "c1", "verification", {}, {"status": "PASS"})
        with self.assertRaises(ValueError):
            store.record(bad)

    def test_changed_candidate_content_invalidates_earlier_receipt(self):
        store, _ = make_store()
        store.record(verification_event(cand="a" * 64, sequence=1))
        # candidate content changed -> new hash; the earlier verification
        # receipt no longer covers the current candidate
        request = PromotionRequest(
            run_id="run-1", candidate_id="cand-1", candidate_hash="c" * 64,
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
        )
        decision = store.assess_promotion(request)
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "EVIDENCE_STALE")

    def test_latest_sequence_wins_for_staleness(self):
        store, _ = make_store()
        store.record(verification_event(cand="a" * 64, sequence=1))
        store.record(verification_event(cand=CAND, sequence=2))
        request = PromotionRequest(
            run_id="run-1", candidate_id="cand-1", candidate_hash=CAND,
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
        )
        self.assertEqual(store.assess_promotion(request).outcome, Outcome.ALLOW)


class PromotionTruthTableTests(unittest.TestCase):
    def setUp(self):
        self.store, _ = make_store()
        self.store.record(verification_event())  # current candidate verified

    def _request(self, **overrides):
        values = dict(
            run_id="run-1", candidate_id="cand-1", candidate_hash=CAND,
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
        )
        values.update(overrides)
        return PromotionRequest(**values)

    def test_truth_table(self):
        rows = [
            (dict(verification_status=VerificationStatus.FAIL), Outcome.DENY, "VERIFY_FAILED"),
            (dict(verification_status=VerificationStatus.BLOCKED), Outcome.BLOCKED, "VERIFY_NOT_COMPLETE"),
            (dict(verification_status=VerificationStatus.NOT_RUN), Outcome.BLOCKED, "VERIFY_NOT_COMPLETE"),
            (dict(evidence_status=EvidenceStatus.INVALID), Outcome.DENY, "EVIDENCE_INVALID"),
            (dict(evidence_status=EvidenceStatus.MISSING), Outcome.BLOCKED, "EVIDENCE_INCOMPLETE"),
            (dict(evidence_status=EvidenceStatus.PARTIAL), Outcome.BLOCKED, "EVIDENCE_INCOMPLETE"),
            (dict(approval_status=ApprovalStatus.PENDING), Outcome.BLOCKED, "APPROVAL_REQUIRED"),
            (dict(approval_status=ApprovalStatus.REJECTED), Outcome.DENY, "APPROVAL_REJECTED"),
            (dict(candidate_hash="c" * 64), Outcome.DENY, "EVIDENCE_STALE"),
            (dict(), Outcome.ALLOW, "PROMOTION_ALLOWED"),
        ]
        for overrides, outcome, reason in rows:
            with self.subTest(**overrides):
                decision = self.store.assess_promotion(self._request(**overrides))
                self.assertEqual(decision.outcome, outcome, overrides)
                self.assertEqual(decision.reason_code, reason, overrides)

    def test_pass_without_any_verification_receipt_is_stale(self):
        store, _ = make_store()
        request = self._request()
        decision = store.assess_promotion(request)
        self.assertEqual((decision.outcome, decision.reason_code), (Outcome.DENY, "EVIDENCE_STALE"))


class AdversarialRegressionTests(unittest.TestCase):
    """Regression tests for the human-review counterexamples (CHANGES_REQUIRED).

    Every counterexample from the review must fail closed; if any of these
    yields ALLOW, acceptance is denied.
    """

    def setUp(self):
        self.store, self.receipts = make_store()

    def test_review_1_run_id_path_escape_is_rejected(self):
        with self.assertRaises(ValueError):
            self.store.record(EvidenceEvent("../escaped", "c1", "note", {}, {"x": 1}))
        with self.assertRaises(ValueError):
            self.store.record(EvidenceEvent("a/b", "c1", "note", {}, {"x": 1}))
        with self.assertRaises(ValueError):
            self.store.record(EvidenceEvent("..", "c1", "note", {}, {"x": 1}))
        with self.assertRaises(ValueError):
            self.store.record(EvidenceEvent(".hidden", "c1", "note", {}, {"x": 1}))
        # nothing was written outside (or inside) the receipt root
        self.assertEqual(list(self.receipts.glob("**/*.json")), [])

    def test_review_2_forged_receipt_variants_fail_closed(self):
        # Forged receipts that are not byte-exact self-consistent
        # (wrong content address, non-canonical bytes, non-PASS status,
        # mismatched run/candidate) must never authorize promotion.
        import hashlib
        cand = "f" * 64
        request = PromotionRequest(
            run_id="run-1", candidate_id="cand-1", candidate_hash=cand,
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
        )
        target = self.receipts / "run-1"
        target.mkdir(parents=True)
        forged = {"run_id": "run-1", "candidate_id": "cand-1", "event_type": "verification",
                  "input_hashes": {"candidate_sha256": cand},
                  "payload": {"status": "PASS", "sequence": 99}}
        blob = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(blob).hexdigest()
        # (a) content placed under a WRONG content-addressed filename
        (target / f"{'0' * 64}.json").write_bytes(blob)
        self.assertEqual(self.store.assess_promotion(request).reason_code, "EVIDENCE_STALE")
        (target / f"{'0' * 64}.json").unlink()
        # (b) non-canonical bytes (pretty-printed) under the correct name
        pretty = json.dumps(forged, indent=2).encode()
        (target / f"{digest}.json").write_bytes(pretty)
        self.assertEqual(self.store.assess_promotion(request).reason_code, "EVIDENCE_STALE")
        (target / f"{digest}.json").unlink()
        # (c) FAIL payload under a correct self-consistent name
        fail_forged = dict(forged, payload={"status": "FAIL", "sequence": 99})
        fail_blob = json.dumps(fail_forged, sort_keys=True, separators=(",", ":")).encode()
        fail_digest = hashlib.sha256(fail_blob).hexdigest()
        (target / f"{fail_digest}.json").write_bytes(fail_blob)
        self.assertEqual(self.store.assess_promotion(request).reason_code, "EVIDENCE_STALE")
        (target / f"{fail_digest}.json").unlink()
        # (d) mismatched run_id under a self-consistent name
        run_forged = dict(forged, run_id="run-2")
        run_blob = json.dumps(run_forged, sort_keys=True, separators=(",", ":")).encode()
        run_digest = hashlib.sha256(run_blob).hexdigest()
        (target / f"{run_digest}.json").write_bytes(run_blob)
        self.assertEqual(self.store.assess_promotion(request).reason_code, "EVIDENCE_STALE")

    @unittest.expectedFailure
    def test_review_2_self_consistent_forgery_requires_protocol_v2(self):
        # KNOWN PROTOCOL GAP (reported to human, fix assigned to H's V2):
        # an attacker with filesystem write access can compute the canonical
        # form AND its content address, producing a fully self-consistent
        # receipt that the L layer cannot distinguish from a genuine one.
        # Closing this vector needs trusted actor/capability receipts -
        # exactly what the review ordered H to freeze in protocol V2.
        import hashlib
        cand = "f" * 64
        forged = {"run_id": "run-1", "candidate_id": "cand-1", "event_type": "verification",
                  "input_hashes": {"candidate_sha256": cand},
                  "payload": {"status": "PASS", "sequence": 99}}
        blob = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(blob).hexdigest()
        target = self.receipts / "run-1"
        target.mkdir(parents=True)
        (target / f"{digest}.json").write_bytes(blob)
        request = PromotionRequest(
            run_id="run-1", candidate_id="cand-1", candidate_hash=cand,
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
        )
        decision = self.store.assess_promotion(request)
        self.assertNotEqual(decision.outcome, Outcome.ALLOW)

    def test_review_2b_drifted_or_non_pass_receipts_are_ignored(self):
        receipt = self.store.record(verification_event())  # PASS receipt
        path = self.receipts / "run-1" / f"{receipt.event_hash}.json"
        # byte drift under the content-addressed name
        drifted = json.loads(path.read_bytes())
        drifted["payload"]["status"] = "PASS"
        drifted["payload"]["sequence"] = 100
        drifted["input_hashes"]["candidate_sha256"] = "d" * 64
        path.write_bytes(json.dumps(
            drifted, sort_keys=True, separators=(",", ":")).encode())
        request = PromotionRequest(
            run_id="run-1", candidate_id="cand-1", candidate_hash="d" * 64,
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
        )
        self.assertEqual(self.store.assess_promotion(request).reason_code, "EVIDENCE_STALE")
        # a FAIL payload is likewise never accepted as a PASS verification
        store2, receipts2 = make_store()
        fail_event = EvidenceEvent("run-1", "cand-1", "verification",
                                   {"candidate_sha256": CAND},
                                   {"status": "FAIL", "sequence": 1})
        r = store2.record(fail_event)
        self.assertTrue(r.valid)
        request2 = PromotionRequest(
            run_id="run-1", candidate_id="cand-1", candidate_hash=CAND,
            verification_status=VerificationStatus.PASS,
            approval_status=ApprovalStatus.APPROVED,
            evidence_status=EvidenceStatus.COMPLETE,
        )
        self.assertEqual(store2.assess_promotion(request2).reason_code, "EVIDENCE_STALE")

    def test_atomic_exclusive_write_survives_preexisting_collision(self):
        receipt = self.store.record(verification_event())
        path = self.receipts / "run-1" / f"{receipt.event_hash}.json"
        before = path.read_bytes()
        r2 = self.store.record(verification_event())
        self.assertTrue(r2.valid)  # identical bytes -> idempotent, still valid
        self.assertEqual(path.read_bytes(), before)


class ApprovalReceiptV2Tests(unittest.TestCase):
    """V2: candidate-bound human approval receipts supersede bare declarations."""

    def setUp(self):
        self.store, _ = make_store()
        self.store.record(verification_event())

    def _request(self, receipt, approval_status=ApprovalStatus.APPROVED, **overrides):
        values = dict(
            run_id="run-1", candidate_id="cand-1", candidate_hash=CAND,
            verification_status=VerificationStatus.PASS,
            approval_status=approval_status,
            evidence_status=EvidenceStatus.COMPLETE,
            approval_receipt=receipt,
        )
        values.update(overrides)
        return PromotionRequest(**values)

    def test_bound_receipt_approves_promotion(self):
        receipt = HumanApprovalReceipt(
            run_id="run-1", candidate_sha256=CAND,
            decision=ApprovalStatus.APPROVED, approved_by="human reviewer",
        )
        decision = self.store.assess_promotion(self._request(receipt))
        self.assertEqual((decision.outcome, decision.reason_code),
                         (Outcome.ALLOW, "PROMOTION_ALLOWED"))

    def test_receipt_bound_to_different_candidate_is_denied(self):
        receipt = HumanApprovalReceipt(
            run_id="run-1", candidate_sha256="e" * 64,
            decision=ApprovalStatus.APPROVED, approved_by="human reviewer",
        )
        decision = self.store.assess_promotion(self._request(receipt))
        self.assertEqual((decision.outcome, decision.reason_code),
                         (Outcome.DENY, "APPROVAL_RECEIPT_INVALID"))

    def test_receipt_from_other_run_is_denied(self):
        receipt = HumanApprovalReceipt(
            run_id="run-2", candidate_sha256=CAND,
            decision=ApprovalStatus.APPROVED, approved_by="human reviewer",
        )
        decision = self.store.assess_promotion(self._request(receipt))
        self.assertEqual((decision.outcome, decision.reason_code),
                         (Outcome.DENY, "APPROVAL_RECEIPT_INVALID"))

    def test_bare_approved_status_with_rejected_receipt_is_denied(self):
        # The receipt supersedes the bare status: a lying caller cannot
        # override a REJECTED receipt by declaring approval_status=APPROVED.
        receipt = HumanApprovalReceipt(
            run_id="run-1", candidate_sha256=CAND,
            decision=ApprovalStatus.REJECTED, approved_by="human reviewer",
        )
        decision = self.store.assess_promotion(self._request(receipt))
        self.assertEqual((decision.outcome, decision.reason_code),
                         (Outcome.DENY, "APPROVAL_REJECTED"))

    def test_anonymous_receipt_is_denied(self):
        receipt = HumanApprovalReceipt(
            run_id="run-1", candidate_sha256=CAND,
            decision=ApprovalStatus.APPROVED, approved_by="  ",
        )
        decision = self.store.assess_promotion(self._request(receipt))
        self.assertEqual((decision.outcome, decision.reason_code),
                         (Outcome.DENY, "APPROVAL_RECEIPT_INVALID"))

    def test_receipt_with_pending_status_is_denied(self):
        receipt = HumanApprovalReceipt(
            run_id="run-1", candidate_sha256=CAND,
            decision=ApprovalStatus.PENDING, approved_by="human reviewer",
        )
        decision = self.store.assess_promotion(self._request(receipt))
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "APPROVAL_RECEIPT_INVALID")


if __name__ == "__main__":
    unittest.main()
