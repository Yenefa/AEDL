"""ARH out-of-graph budget: five hard limits, a one-way door (D4 / N6).

This module implements ONLY the Harness-side (outside-the-graph) budget of
the double-layer design decided in RFC section 5 D4 and ADR-016:

    layer 1, inside the graph   : the orchestrator's existing ``max_repairs``
                                  trip, the finding-fingerprint early stall
                                  and ``repair_count``. Those already exist
                                  and belong to the orchestrator; this module
                                  never reads, re-implements, replaces or
                                  loosens any of them.
    layer 2, outside the graph  : ``BudgetStop`` -- per-run LLM call count,
                                  token total, wall-clock, consecutive
                                  invalid proposals, consecutive format
                                  errors.

Any ``BudgetExceeded`` is terminal and fail-closed: ``invalid_run`` is
``True``, so the benchmark maps every budget breach to ``INVALID_RUN`` --
never to a repair PASS/FAIL verdict, never to "raise the limit and retry".
The stop is sticky for the life of the instance: once tripped it stays
tripped even if the consecutive counters are cleared afterwards (N6: the
budget cannot be talked out of stopping).

Token accounting keeps four classes apart (RFC section 5 D4.2):
``input_tokens`` / ``output_tokens`` / ``cache_read_tokens`` /
``cache_write_tokens`` are accumulated separately and only summed for the
limit check, so a cache-heavy run is not mispriced by roughly 5x.

Boundary semantics: reaching a limit trips it -- every comparison is
``>=``, not ``>``. With ``max_calls=3`` the fourth ``check_before_call``
raises.

``latency_ms`` is accepted by ``record_call`` for call-signature parity with
the ModelAdapter, but latency/cost bookkeeping belongs to that adapter (RFC
section 1.2): the budget itself only counts calls and tokens.

The clock is injectable so wall-clock behaviour is deterministically
testable without sleeping.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

__all__ = ["BudgetConfig", "BudgetExceeded", "BudgetStop"]


@dataclass(frozen=True)
class BudgetConfig:
    """The five out-of-graph limits (all inclusive: reaching one trips it)."""

    max_calls: int = 8
    max_total_tokens: int = 200_000
    max_wall_clock_s: float = 600.0
    max_consecutive_invalid: int = 3
    max_consecutive_format_errors: int = 3


class BudgetExceeded(RuntimeError):
    """An out-of-graph budget tripped (D4) -- the run is INVALID_RUN.

    ``code`` is one of ``BUDGET_CALLS`` / ``BUDGET_TOKENS`` /
    ``BUDGET_WALL_CLOCK`` / ``BUDGET_INVALID_PROPOSALS`` /
    ``BUDGET_FORMAT_ERRORS``. ``invalid_run`` defaults to ``True`` and is
    what the benchmark reads to classify the run.
    """

    code: str
    invalid_run: bool = True

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class BudgetStop:
    """Per-run LLM budget enforcement point (ARH-N6).

    Call ``check_before_call()`` immediately before every model call, then
    ``record_call()`` with that call's token usage, plus
    ``record_invalid_proposal()`` / ``record_valid_proposal()`` around the
    static proposal validation and ``record_format_error()`` /
    ``record_format_ok()`` around output parsing (``record_format_ok`` is
    called on every successful parse, whether or not the parsed proposal is
    later judged valid -- the two counters are independent).
    """

    def __init__(
        self,
        config: BudgetConfig | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config if config is not None else BudgetConfig()
        self._clock = clock
        self._started_at = clock()
        self._calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._cache_read_tokens = 0
        self._cache_write_tokens = 0
        self._consecutive_invalid = 0
        self._total_invalid = 0
        self._consecutive_format = 0
        self._total_format = 0
        #: Code of the first breach; sticky for the life of this instance.
        self._tripped: str | None = None

    # ------------------------------------------------------------------
    # derived state
    # ------------------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        """Sum of the four separately-accounted token classes (D4.2)."""
        return (
            self._input_tokens
            + self._output_tokens
            + self._cache_read_tokens
            + self._cache_write_tokens
        )

    def _elapsed(self) -> float:
        return self._clock() - self._started_at

    def _trip(self, code: str, detail: str) -> None:
        """Latch the stop (N6, one-way) and raise."""
        self._tripped = code
        raise BudgetExceeded(
            code,
            f"{detail}; out-of-graph budget exceeded (ARH-N6) -> "
            "benchmark records INVALID_RUN",
        )

    # ------------------------------------------------------------------
    # enforcement points
    # ------------------------------------------------------------------

    def check_before_call(self) -> None:
        """Refuse the next model call if any pre-call limit is already hit."""
        cfg = self._config
        if self._calls >= cfg.max_calls:
            self._trip(
                "BUDGET_CALLS",
                f"call budget exhausted: calls={self._calls} "
                f">= max_calls={cfg.max_calls}",
            )
        if self.total_tokens >= cfg.max_total_tokens:
            self._trip(
                "BUDGET_TOKENS",
                f"token budget exhausted: total_tokens={self.total_tokens} "
                f">= max_total_tokens={cfg.max_total_tokens}",
            )
        if self._elapsed() >= cfg.max_wall_clock_s:
            self._trip(
                "BUDGET_WALL_CLOCK",
                f"wall-clock budget exhausted: elapsed={self._elapsed():.3f}s "
                f">= max_wall_clock_s={cfg.max_wall_clock_s}",
            )
        if self._tripped is not None:
            # An earlier breach already made this run INVALID_RUN; clearing a
            # consecutive counter must never un-stop the loop (N6).
            self._trip(
                self._tripped,
                f"budget already tripped ({self._tripped})",
            )

    def record_call(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        latency_ms: float = 0,
    ) -> None:
        """Accumulate one completed model call; trip on the token limit."""
        del latency_ms  # adapter's accounting (RFC section 1.2), not a limit
        self._calls += 1
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens
        self._cache_read_tokens += cache_read_tokens
        self._cache_write_tokens += cache_write_tokens
        if self.total_tokens >= self._config.max_total_tokens:
            self._trip(
                "BUDGET_TOKENS",
                f"token budget exhausted: total_tokens={self.total_tokens} "
                f">= max_total_tokens={self._config.max_total_tokens}",
            )

    def record_invalid_proposal(self) -> None:
        """Count a proposal the static validation refused (D2 counters)."""
        self._consecutive_invalid += 1
        self._total_invalid += 1
        if self._consecutive_invalid >= self._config.max_consecutive_invalid:
            self._trip(
                "BUDGET_INVALID_PROPOSALS",
                f"consecutive invalid proposals "
                f"{self._consecutive_invalid} >= "
                f"max_consecutive_invalid={self._config.max_consecutive_invalid}",
            )

    def record_valid_proposal(self) -> None:
        """A proposal passed static validation: clear the consecutive count."""
        self._consecutive_invalid = 0

    def record_format_error(self) -> None:
        """Count one unparsable model output (format-error breaker)."""
        self._consecutive_format += 1
        self._total_format += 1
        if self._consecutive_format >= self._config.max_consecutive_format_errors:
            self._trip(
                "BUDGET_FORMAT_ERRORS",
                f"consecutive format errors {self._consecutive_format} >= "
                "max_consecutive_format_errors="
                f"{self._config.max_consecutive_format_errors}",
            )

    def record_format_ok(self) -> None:
        """Output parsed: clear the consecutive format count (validity is
        judged separately and does not belong to this counter)."""
        self._consecutive_format = 0

    # ------------------------------------------------------------------
    # observation
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Budget state for one trajectory line (see trajectory.record)."""
        cfg = self._config
        return {
            "calls": self._calls,
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "cache_read_tokens": self._cache_read_tokens,
            "cache_write_tokens": self._cache_write_tokens,
            "total_tokens": self.total_tokens,
            "elapsed_s": self._elapsed(),
            "consecutive_invalid": self._consecutive_invalid,
            "total_invalid": self._total_invalid,
            "consecutive_format_errors": self._consecutive_format,
            "total_format_errors": self._total_format,
            "limits": {
                "max_calls": cfg.max_calls,
                "max_total_tokens": cfg.max_total_tokens,
                "max_wall_clock_s": cfg.max_wall_clock_s,
                "max_consecutive_invalid": cfg.max_consecutive_invalid,
                "max_consecutive_format_errors": cfg.max_consecutive_format_errors,
            },
        }

    @property
    def exhausted(self) -> bool:
        """True once any limit is reached -- latched, never cleared again."""
        if self._tripped is not None:
            return True
        cfg = self._config
        return (
            self._calls >= cfg.max_calls
            or self.total_tokens >= cfg.max_total_tokens
            or self._elapsed() >= cfg.max_wall_clock_s
            or self._consecutive_invalid >= cfg.max_consecutive_invalid
            or self._consecutive_format >= cfg.max_consecutive_format_errors
        )
