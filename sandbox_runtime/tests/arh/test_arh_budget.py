"""ARH-N6 out-of-graph budget tests (RFC section 5 D4 / D4.2, ADR-016).

Zero network, zero sleeping: the wall-clock limit is exercised through the
injected clock, and every limit is isolated so each of the five thresholds
is proven to trip on its own with its own code.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError

from aedl_sandbox.arh.budget import BudgetConfig, BudgetExceeded, BudgetStop

#: Limits so high that the limit under test is the only one that can trip.
_FAR: dict[str, float] = {
    "max_calls": 10_000,
    "max_total_tokens": 10**9,
    "max_wall_clock_s": 10**9,
    "max_consecutive_invalid": 10_000,
    "max_consecutive_format_errors": 10_000,
}


def isolated(**overrides: float) -> BudgetConfig:
    """A config where only the overridden limit is within reach."""
    values = dict(_FAR)
    values.update(overrides)
    return BudgetConfig(**values)  # type: ignore[arg-type]


class FakeClock:
    """Deterministic monotonic stand-in: no test may depend on real time."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


class BudgetConfigTests(unittest.TestCase):
    def test_default_limits_match_the_rfc_working_values(self) -> None:
        config = BudgetConfig()
        self.assertEqual(config.max_calls, 8)
        self.assertEqual(config.max_total_tokens, 200_000)
        self.assertEqual(config.max_wall_clock_s, 600.0)
        self.assertEqual(config.max_consecutive_invalid, 3)
        self.assertEqual(config.max_consecutive_format_errors, 3)

    def test_config_is_immutable(self) -> None:
        config = BudgetConfig()
        with self.assertRaises(FrozenInstanceError):
            config.max_calls = 99  # type: ignore[misc]


class BudgetThresholdTests(unittest.TestCase):
    def test_call_limit_trips_on_the_fourth_check(self) -> None:
        # Boundary semantics: >=, not >. max_calls=3 -> checks 1..3 pass.
        stop = BudgetStop(isolated(max_calls=3))
        for attempt in range(3):
            with self.subTest(check=attempt + 1):
                stop.check_before_call()
                stop.record_call()
        with self.assertRaises(BudgetExceeded) as ctx:
            stop.check_before_call()
        self.assertEqual(ctx.exception.code, "BUDGET_CALLS")
        self.assertTrue(ctx.exception.invalid_run)

    def test_token_limit_trips_after_accumulation_and_keeps_four_classes(self) -> None:
        stop = BudgetStop(isolated(max_total_tokens=100))
        stop.record_call(input_tokens=40, output_tokens=30, cache_read_tokens=20, latency_ms=12.5)
        snap = stop.snapshot()
        self.assertEqual(snap["input_tokens"], 40)
        self.assertEqual(snap["output_tokens"], 30)
        self.assertEqual(snap["cache_read_tokens"], 20)
        self.assertEqual(snap["cache_write_tokens"], 0)
        self.assertEqual(snap["total_tokens"], 90)
        with self.assertRaises(BudgetExceeded) as ctx:
            stop.record_call(cache_write_tokens=10)  # 90 + 10 == 100 >= 100
        self.assertEqual(ctx.exception.code, "BUDGET_TOKENS")
        self.assertTrue(ctx.exception.invalid_run)
        snap = stop.snapshot()
        self.assertEqual(snap["total_tokens"], 100)
        self.assertEqual(snap["calls"], 2)

    def test_check_before_call_refuses_an_already_spent_token_budget(self) -> None:
        stop = BudgetStop(isolated(max_total_tokens=50))
        with self.assertRaises(BudgetExceeded):
            stop.record_call(input_tokens=50)  # trips inside record_call
        with self.assertRaises(BudgetExceeded) as ctx:
            stop.check_before_call()
        self.assertEqual(ctx.exception.code, "BUDGET_TOKENS")

    def test_wall_clock_limit_trips_on_the_injected_clock(self) -> None:
        clock = FakeClock(1000.0)
        stop = BudgetStop(isolated(max_wall_clock_s=30.0), clock=clock)
        stop.check_before_call()  # elapsed 0
        clock.advance(15.0)
        stop.check_before_call()  # 15 < 30
        clock.advance(15.0)  # exactly at the limit -> trips (>= semantics)
        with self.assertRaises(BudgetExceeded) as ctx:
            stop.check_before_call()
        self.assertEqual(ctx.exception.code, "BUDGET_WALL_CLOCK")
        self.assertTrue(ctx.exception.invalid_run)
        self.assertEqual(stop.snapshot()["elapsed_s"], 30.0)
        self.assertTrue(stop.exhausted)

    def test_consecutive_invalid_proposals_trip_on_the_third(self) -> None:
        stop = BudgetStop(BudgetConfig(max_consecutive_invalid=3))
        stop.record_invalid_proposal()
        stop.record_invalid_proposal()
        with self.assertRaises(BudgetExceeded) as ctx:
            stop.record_invalid_proposal()
        self.assertEqual(ctx.exception.code, "BUDGET_INVALID_PROPOSALS")
        self.assertTrue(ctx.exception.invalid_run)
        snap = stop.snapshot()
        self.assertEqual(snap["consecutive_invalid"], 3)
        self.assertEqual(snap["total_invalid"], 3)

    def test_consecutive_format_errors_trip_on_the_third(self) -> None:
        stop = BudgetStop(BudgetConfig(max_consecutive_format_errors=3))
        stop.record_format_error()
        stop.record_format_error()
        with self.assertRaises(BudgetExceeded) as ctx:
            stop.record_format_error()
        self.assertEqual(ctx.exception.code, "BUDGET_FORMAT_ERRORS")
        self.assertTrue(ctx.exception.invalid_run)
        snap = stop.snapshot()
        self.assertEqual(snap["consecutive_format_errors"], 3)
        self.assertEqual(snap["total_format_errors"], 3)
        # a later successful parse clears only the consecutive counter
        stop.record_format_ok()
        snap = stop.snapshot()
        self.assertEqual(snap["consecutive_format_errors"], 0)
        self.assertEqual(snap["total_format_errors"], 3)

    def test_valid_proposal_clears_consecutive_invalid_but_keeps_the_total(self) -> None:
        stop = BudgetStop(isolated(max_consecutive_invalid=2))
        stop.record_invalid_proposal()
        self.assertEqual(stop.snapshot()["consecutive_invalid"], 1)
        stop.record_valid_proposal()
        snap = stop.snapshot()
        self.assertEqual(snap["consecutive_invalid"], 0)
        self.assertEqual(snap["total_invalid"], 1)
        # cleared, so the second cycle may run again without tripping
        stop.record_invalid_proposal()
        self.assertEqual(stop.snapshot()["consecutive_invalid"], 1)
        self.assertFalse(stop.exhausted)

    def test_format_ok_and_valid_proposal_clear_only_their_own_counter(self) -> None:
        stop = BudgetStop()
        stop.record_invalid_proposal()
        stop.record_format_error()
        stop.record_valid_proposal()
        snap = stop.snapshot()
        self.assertEqual(snap["consecutive_invalid"], 0)
        self.assertEqual(snap["consecutive_format_errors"], 1)
        stop.record_invalid_proposal()
        stop.record_format_ok()
        snap = stop.snapshot()
        self.assertEqual(snap["consecutive_format_errors"], 0)
        self.assertEqual(snap["consecutive_invalid"], 1)
        self.assertEqual(snap["total_invalid"], 2)
        self.assertEqual(snap["total_format_errors"], 1)


class BudgetTripClassificationTests(unittest.TestCase):
    """Every breach is INVALID_RUN and carries its own machine-readable code."""

    def _trippers(self) -> dict[str, tuple[BudgetConfig, object]]:
        def trip_calls(stop: BudgetStop, clock: FakeClock) -> None:
            stop.check_before_call()
            stop.record_call()
            stop.check_before_call()  # calls == max_calls -> refused

        def trip_tokens(stop: BudgetStop, clock: FakeClock) -> None:
            stop.record_call(input_tokens=10, output_tokens=5)

        def trip_clock(stop: BudgetStop, clock: FakeClock) -> None:
            clock.advance(5.0)
            stop.check_before_call()  # elapsed == max_wall_clock_s

        def trip_invalid(stop: BudgetStop, clock: FakeClock) -> None:
            for _ in range(3):
                stop.record_invalid_proposal()

        def trip_format(stop: BudgetStop, clock: FakeClock) -> None:
            for _ in range(3):
                stop.record_format_error()

        return {
            "BUDGET_CALLS": (isolated(max_calls=1), trip_calls),
            "BUDGET_TOKENS": (isolated(max_total_tokens=10), trip_tokens),
            "BUDGET_WALL_CLOCK": (isolated(max_wall_clock_s=5.0), trip_clock),
            "BUDGET_INVALID_PROPOSALS": (BudgetConfig(max_consecutive_invalid=3), trip_invalid),
            "BUDGET_FORMAT_ERRORS": (BudgetConfig(max_consecutive_format_errors=3), trip_format),
        }

    def test_each_of_the_five_limits_trips_with_invalid_run(self) -> None:
        for code, (config, trip) in self._trippers().items():
            with self.subTest(code=code):
                clock = FakeClock()
                stop = BudgetStop(config, clock=clock)
                self.assertFalse(stop.exhausted)
                with self.assertRaises(BudgetExceeded) as ctx:
                    trip(stop, clock)  # type: ignore[operator]
                self.assertEqual(ctx.exception.code, code)
                self.assertIs(ctx.exception.invalid_run, True)
                self.assertTrue(stop.exhausted)

    def test_exhausted_stays_true_after_counters_are_cleared(self) -> None:
        stop = BudgetStop(BudgetConfig(max_consecutive_invalid=3))
        for _ in range(3):
            try:
                stop.record_invalid_proposal()
            except BudgetExceeded:
                break
        self.assertTrue(stop.exhausted)
        stop.record_valid_proposal()
        self.assertEqual(stop.snapshot()["consecutive_invalid"], 0)
        self.assertTrue(stop.exhausted)  # latched, not merely "over threshold"

    def test_a_tripped_stop_cannot_be_talked_out_of_stopping(self) -> None:
        # N6: no reset path exists once the budget has tripped.
        stop = BudgetStop(BudgetConfig(max_consecutive_invalid=3, max_calls=5))
        with self.assertRaises(BudgetExceeded) as tripped:
            for _ in range(3):
                stop.record_invalid_proposal()
        first = tripped.exception
        stop.record_valid_proposal()
        stop.record_format_ok()
        with self.assertRaises(BudgetExceeded) as ctx:
            stop.check_before_call()
        self.assertEqual(ctx.exception.code, first.code)
        self.assertIs(ctx.exception.invalid_run, True)


class BudgetSnapshotTests(unittest.TestCase):
    def test_snapshot_exposes_the_documented_keys_and_limits(self) -> None:
        stop = BudgetStop(isolated(max_calls=7, max_total_tokens=1234), clock=FakeClock(5.0))
        stop.record_call(input_tokens=1, output_tokens=2, cache_read_tokens=3, cache_write_tokens=4)
        stop.record_invalid_proposal()
        stop.record_format_error()
        snap = stop.snapshot()
        self.assertEqual(
            set(snap),
            {
                "calls",
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "total_tokens",
                "elapsed_s",
                "consecutive_invalid",
                "total_invalid",
                "consecutive_format_errors",
                "total_format_errors",
                "tripped",
                "limits",
            },
        )
        self.assertIsNone(snap["tripped"])
        self.assertEqual(
            set(snap["limits"]),
            {
                "max_calls",
                "max_total_tokens",
                "max_wall_clock_s",
                "max_consecutive_invalid",
                "max_consecutive_format_errors",
            },
        )
        self.assertEqual(snap["limits"]["max_calls"], 7)
        self.assertEqual(snap["limits"]["max_total_tokens"], 1234)
        self.assertEqual(snap["calls"], 1)
        self.assertEqual(snap["total_tokens"], 10)
        self.assertEqual(snap["elapsed_s"], 0.0)
        # a snapshot is a plain JSON-serialisable dict (trajectory writes it)
        self.assertEqual(json.loads(json.dumps(snap)), snap)

    def test_exhausted_is_false_until_a_limit_is_reached(self) -> None:
        clock = FakeClock()
        stop = BudgetStop(isolated(max_calls=2, max_wall_clock_s=10.0), clock=clock)
        self.assertFalse(stop.exhausted)
        stop.check_before_call()
        stop.record_call()
        self.assertFalse(stop.exhausted)
        clock.advance(9.0)
        self.assertFalse(stop.exhausted)
        stop.check_before_call()
        stop.record_call()
        self.assertTrue(stop.exhausted)  # calls == max_calls, before any raise
        with self.assertRaises(BudgetExceeded) as ctx:
            stop.check_before_call()
        self.assertEqual(ctx.exception.code, "BUDGET_CALLS")


class BudgetRestoreTests(unittest.TestCase):
    """`from_snapshot` rebuilds the exact latched state (GH-119 follow-up).

    Without it a caller could only replay `record_*` calls, which loses the N6
    latch: a valid proposal clears the consecutive counters but must never
    clear the trip. Replaying counters alone would wash a tripped run clean.
    """

    def test_round_trip_preserves_counters_and_clock(self) -> None:
        clock = FakeClock(100.0)
        stop = BudgetStop(
            isolated(max_calls=7, max_total_tokens=1234), clock=clock
        )
        stop.record_call(input_tokens=1, output_tokens=2)
        stop.record_invalid_proposal()
        clock.advance(4.5)
        snap = stop.snapshot()
        other_clock = FakeClock(1000.0)
        rebuilt = BudgetStop.from_snapshot(snap, clock=other_clock)
        self.assertEqual(rebuilt.snapshot()["calls"], 1)
        self.assertEqual(rebuilt.snapshot()["total_tokens"], 3)
        self.assertEqual(rebuilt.snapshot()["consecutive_invalid"], 1)
        self.assertEqual(rebuilt.snapshot()["tripped"], None)
        # Same wall-clock continues, not restarts: 4.5s already spent.
        self.assertAlmostEqual(rebuilt.snapshot()["elapsed_s"], 4.5)
        other_clock.advance(1.0)
        self.assertAlmostEqual(rebuilt.snapshot()["elapsed_s"], 5.5)

    def test_a_tripped_run_stays_tripped_after_restore(self) -> None:
        """The load-bearing case: trip, then a valid proposal clears the
        consecutive counter. The restored instance must still refuse."""
        clock = FakeClock()
        stop = BudgetStop(isolated(max_consecutive_invalid=2), clock=clock)
        stop.record_invalid_proposal()
        with self.assertRaises(BudgetExceeded):
            stop.record_invalid_proposal()  # trips here
        self.assertIsNotNone(stop.snapshot()["tripped"])
        stop.record_valid_proposal()  # clears consecutive, NOT the latch
        snap = stop.snapshot()
        self.assertEqual(snap["consecutive_invalid"], 0)
        self.assertIsNotNone(snap["tripped"])
        rebuilt = BudgetStop.from_snapshot(snap, clock=FakeClock())
        self.assertTrue(rebuilt.exhausted)
        with self.assertRaises(BudgetExceeded):
            rebuilt.check_before_call()
        # And a further valid proposal cannot talk it out of stopping either.
        rebuilt.record_valid_proposal()
        with self.assertRaises(BudgetExceeded):
            rebuilt.check_before_call()

    def test_old_snapshots_without_tripped_still_load(self) -> None:
        clock = FakeClock(10.0)
        stop = BudgetStop(isolated(max_calls=7), clock=clock)
        stop.record_call(input_tokens=5)
        snap = stop.snapshot()
        del snap["tripped"]
        rebuilt = BudgetStop.from_snapshot(snap, clock=FakeClock(50.0))
        self.assertEqual(rebuilt.snapshot()["calls"], 1)
        self.assertIsNone(rebuilt.snapshot()["tripped"])

    def test_malformed_snapshots_are_refused_not_defaulted(self) -> None:
        clock = FakeClock()
        stop = BudgetStop(isolated(), clock=clock)
        good = stop.snapshot()
        for bad in (
            "not-a-mapping",
            {**good, "tripped": "BUDGET_SOMETHING_ELSE"},
            {**good, "calls": -1},
            {**good, "elapsed_s": -0.5},
            {k: v for k, v in good.items() if k != "limits"},
            {**good, "limits": {}},
        ):
            with self.assertRaises((TypeError, ValueError)):
                BudgetStop.from_snapshot(bad, clock=clock)


if __name__ == "__main__":
    unittest.main()
