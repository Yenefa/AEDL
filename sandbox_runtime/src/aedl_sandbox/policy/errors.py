"""Error types for the AEDL sandbox policy kernel.

``PolicyDocumentError`` is the fail-closed signal: a policy document that
cannot be proven valid never becomes an engine, because an engine that cannot
be trusted must not be able to answer ALLOW.
"""

from __future__ import annotations

from typing import Any

__all__ = ["PolicyDocumentError", "PolicySchemaError"]


class PolicyDocumentError(ValueError):
    """Raised when a normalized policy document cannot be trusted."""

    def __init__(self, message: str, *, violations: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.message = message
        # Sorted and de-duplicated so that callers see a deterministic report.
        self.violations: tuple[str, ...] = tuple(sorted(set(violations)))

    def __str__(self) -> str:
        if not self.violations:
            return self.message
        joined = "; ".join(self.violations)
        return f"{self.message}: {joined}"


class PolicySchemaError(RuntimeError):
    """Raised when the schema itself, or the evaluator, is misused.

    This is a programming error, not a policy input error: it must never be
    caught and converted into a permissive decision.
    """

    def __init__(self, message: str, *, path: str = "$", keyword: Any = None) -> None:
        super().__init__(message)
        self.path = path
        self.keyword = keyword
