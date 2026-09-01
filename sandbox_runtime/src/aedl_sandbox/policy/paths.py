"""Path containment for the Execution Sandbox.

Contains only lexical and OS-level resolution. It deliberately never compares
basenames, prefixes or substrings: containment is decided on fully resolved,
case-normalized absolute paths.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["is_within", "resolve_within"]


def _norm(path: Path) -> str:
    # Root and target must be compared at the SAME resolution level: realpath
    # (not abspath) so junctions/symlinks (e.g. a TEMP dir through a junction)
    # cannot make a contained target look like an escape, or vice versa.
    return os.path.normcase(os.path.realpath(os.path.abspath(str(path))))


def is_within(root: Path, target: Path, *, strict: bool = False) -> bool:
    """Return True when ``target`` is contained in ``root``.

    ``strict`` additionally requires ``target`` to be a proper descendant.
    """
    try:
        normalized_root = _norm(Path(root))
        normalized_target = _norm(Path(target))
    except (OSError, ValueError, TypeError):
        return False
    if normalized_target == normalized_root:
        return not strict
    return normalized_target.startswith(normalized_root.rstrip(os.sep) + os.sep)


def resolve_within(root: Path, raw: str, *, strict: bool = False) -> Path | None:
    """Resolve ``raw`` against ``root`` and return it only if it stays inside.

    Returns None for anything that escapes, is empty, is not a string, or
    cannot be resolved. Callers must treat None as a DENY, never as a default.

    ``strict`` rejects a path that resolves to ``root`` itself. File writes
    must use it: a whitespace-only or dot-only path can normalize back onto the
    root directory, which is not a writable file target.
    """
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        return None
    try:
        candidate = Path(raw)
        target = candidate if candidate.is_absolute() else (Path(root) / candidate)
        resolved = target.resolve()
    except (OSError, ValueError):
        return None
    if not is_within(root, resolved, strict=strict):
        return None
    return resolved
