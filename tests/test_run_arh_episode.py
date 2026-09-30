"""Cross-layer regression: C4's real receipt shape must reach C5 verification."""
import copy
import unittest
from tools import repair_pipeline


class NativeWriterReceiptTests(unittest.TestCase):
    def setUp(self):
        self.receipt = {"status": "APPLIED_TO_STAGE", "changed": True,
            "before_source_sha256": "a" * 64, "after_source_sha256": "b" * 64,
            "native_before": {"source_sha256": "a" * 64},
            "native_after": {"source_sha256": "b" * 64},
            "tool": {"mode": "PYTHON_WRITER", "tool_applied": None, "exit_code": 0,
                     "op_results": [{"op_index": 0, "status": "ok"}]}}

    def test_bound_api_effect_is_accepted_without_inventing_applied_true(self):
        self.assertTrue(repair_pipeline._stage_write_succeeded(self.receipt))
        self.assertIsNone(self.receipt["tool"]["tool_applied"])

    def test_missing_or_false_effect_is_rejected(self):
        for mutation in ("missing_before", "missing_after", "unbound_after", "unchanged",
                         "empty_ops", "op_error", "op_gap", "false_applied", "wrong_mode", "exit_error",
                         "malformed_native"):
            with self.subTest(mutation=mutation):
                receipt = copy.deepcopy(self.receipt)
                if mutation == "missing_before": receipt.pop("native_before")
                elif mutation == "missing_after": receipt.pop("native_after")
                elif mutation == "unbound_after": receipt["native_after"]["source_sha256"] = "c" * 64
                elif mutation == "unchanged": receipt["changed"] = False
                elif mutation == "empty_ops": receipt["tool"]["op_results"] = []
                elif mutation == "op_error": receipt["tool"]["op_results"][0]["status"] = "error"
                elif mutation == "op_gap": receipt["tool"]["op_results"][0]["op_index"] = 1
                elif mutation == "false_applied": receipt["tool"]["tool_applied"] = False
                elif mutation == "wrong_mode": receipt["tool"]["mode"] = "CLI_STRICT"
                elif mutation == "exit_error": receipt["tool"]["exit_code"] = 1
                elif mutation == "malformed_native": receipt["native_after"] = "not-an-observation"
                self.assertFalse(repair_pipeline._stage_write_succeeded(receipt))

    def test_commit_rechecks_real_api_effect_instead_of_requiring_cli_field(self):
        receipt = {"route": "CONSTRAINED_EXCEPTION", "stage": {
            "status": "APPLIED_TO_STAGE", "tool_applied": None, "changed": True}}
        args = dict(live_equals_snapshot=True, hashes_recomputed=True, binding_drift=[],
                    permission_drift=[], lock_held=True, writer_calls=1)
        thin = {"scope": "PR1_CANDIDATE_BYTES", "status": "PASS"}
        self.assertTrue(repair_pipeline._commit_predicate(
            receipt, thin, staged_receipt=self.receipt, **args)[0])
        broken = copy.deepcopy(self.receipt)
        broken["native_after"]["source_sha256"] = "c" * 64
        ok, _, failed = repair_pipeline._commit_predicate(receipt, thin, staged_receipt=broken, **args)
        self.assertFalse(ok)
        self.assertIn("route_and_effect_checks", failed)
