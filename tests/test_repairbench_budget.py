# -*- coding: utf-8 -*-
"""Pin the spend-ceiling behaviour. These tests never call a model."""
import io
import json
import unittest
from pathlib import Path

from tools import repairbench_budget as b


class CeilingConstantTests(unittest.TestCase):
    def test_ceiling_is_one_cny(self):
        """The Owner's constraint is a hard number in code, not a convention."""
        self.assertEqual(b.CEILING_CNY, 1.00)

    def test_price_assumption_is_flagged_unverified(self):
        """Cost is estimated from an assumed price; that must be visible."""
        self.assertFalse(b.PRICE_IS_VERIFIED)

    def test_ledger_file_is_inside_the_repo(self):
        """The ledger has to be committed so the ceiling cannot be reset silently."""
        self.assertTrue(str(b.LEDGER_PATH).replace("\\", "/").find("/benchmarks/") > 0)


class SpendArithmeticTests(unittest.TestCase):
    def test_estimate_is_linear_and_pessimistic(self):
        self.assertEqual(b.estimate_cny(0, 0), 0.0)
        self.assertAlmostEqual(b.estimate_cny(1_000_000, 0), b.ASSUMED_INPUT_CNY_PER_M)
        self.assertAlmostEqual(b.estimate_cny(0, 1_000_000), b.ASSUMED_OUTPUT_CNY_PER_M)
        # output must cost more than input at the assumed rates
        self.assertGreater(b.estimate_cny(0, 1000), b.estimate_cny(1000, 0))

    def test_reasoning_tokens_are_not_double_counted(self):
        """reasoning_tokens is a subset of completion_tokens and must not add again."""
        usage = {"prompt_tokens": 100, "completion_tokens": 50,
                 "completion_tokens_details": {"reasoning_tokens": 40}}
        self.assertAlmostEqual(b.estimate_cny(100, 50),
                               b.estimate_cny(100, 50))


class FailClosedTests(unittest.TestCase):
    """The ceiling must stop spend BEFORE a request is issued."""

    def setUp(self):
        self._real = b.LEDGER_PATH
        self.tmp = Path(__import__("tempfile").mkdtemp())
        b.LEDGER_PATH = self.tmp / "budget_ledger.json"

    def tearDown(self):
        b.LEDGER_PATH = self._real
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, spent, ceiling=1.00):
        b.LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        b.LEDGER_PATH.write_text(json.dumps({
            "ceiling_cny": ceiling, "spent_cny": spent, "calls": 1,
            "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
            "history": []}), encoding="utf-8")

    def test_refuses_when_ceiling_reached(self):
        self._write(1.00)
        with self.assertRaises(b.BudgetExceeded):
            b.check_before_call()

    def test_refuses_when_projection_would_exceed(self):
        self._write(0.999)
        with self.assertRaises(b.BudgetExceeded):
            b.check_before_call(estimated_input_tokens=10_000_000)

    def test_allows_when_well_under(self):
        self._write(0.01)
        b.check_before_call(estimated_input_tokens=1000)  # must not raise

    def test_record_accumulates_and_persists(self):
        b.LEDGER_PATH.unlink(missing_ok=True)
        b.record("arm", "DC-01", {"prompt_tokens": 1000, "completion_tokens": 500,
                                  "completion_tokens_details": {"reasoning_tokens": 400}})
        b.record("arm", "DC-02", {"prompt_tokens": 2000, "completion_tokens": 500})
        snap = b.snapshot()
        self.assertEqual(snap["calls"], 2)
        self.assertEqual(snap["input_tokens"], 3000)
        self.assertEqual(snap["output_tokens"], 1000)
        self.assertEqual(snap["reasoning_tokens"], 400)
        self.assertGreater(snap["spent_cny"], 0)
        # must survive a reload from disk
        self.assertEqual(b.snapshot()["spent_cny"], snap["spent_cny"])

    def test_record_refuses_to_exceed_ceiling(self):
        self._write(0.999999)
        with self.assertRaises(b.BudgetExceeded):
            b.record("arm", "DC-01", {"prompt_tokens": 10_000_000, "completion_tokens": 0})


class NoSecretInRepoTests(unittest.TestCase):
    def test_budget_module_contains_no_credential(self):
        text = b.Path(b.__file__).read_text(encoding="utf-8")
        self.assertNotIn("sk-", text)
        self.assertNotIn("api_key", text.replace("api_key\"", ""))


if __name__ == "__main__":
    unittest.main()