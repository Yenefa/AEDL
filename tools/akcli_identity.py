"""One resolution rule for the pinned `akcli` writer.

Three modules used to answer "where is akcli?" independently: `gates/run_gates.py`
(env -> PATH -> default), `tools/repairbench.py` and `tools/repairbench_synth.py`
(only `Path.home()/AppData/.../akcli.exe`, a personal Windows layout). On any
machine without that exact file — which includes CI — the two tools raised
"pinned akcli writer not found", and a test that asserts the WRITER's refusal
message failed for a reason that had nothing to do with the guard it claimed to
cover.

This module owns the lookup order and the failure text, so a missing tool is
reported as a configuration fact ("set AKCLI=..., looked at these paths") instead
of an unrelated assertion error.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List, Optional

ENV_VAR = "AKCLI"
# Last candidate, not a requirement: keeps the original workstation working with
# no configuration while never being the only way to supply the tool.
PINNED_DEFAULT = Path.home() / "AppData/Local/hermes/hermes-agent/venv/Scripts/akcli.exe"


def candidates() -> List[Path]:
    """Resolution order: explicit env, PATH, then the pinned workstation default."""
    out: List[Path] = []
    env_value = os.environ.get(ENV_VAR)
    if env_value:
        out.append(Path(env_value))
    found = shutil.which("akcli")
    if found:
        out.append(Path(found))
    out.append(PINNED_DEFAULT)
    return out


def resolve() -> Optional[Path]:
    """The first candidate that is actually a file, or None."""
    for candidate in candidates():
        if candidate.is_file():
            return candidate.resolve()
    return None


def describe_lookup() -> str:
    """Every path that was tried, so a skip or failure names a fixable cause."""
    return " | ".join(str(path) for path in candidates())


class AkcliUnavailable(RuntimeError):
    """The pinned writer is required for this operation and was not found."""


def require(purpose: str) -> Path:
    exe = resolve()
    if exe is None:
        raise AkcliUnavailable(
            "akcli writer not found for %s: set %s=<absolute path> (looked for: %s)"
            % (purpose, ENV_VAR, describe_lookup())
        )
    return exe


def missing_reason(purpose: str) -> str:
    """The sentence a test should use when it skips for want of the tool."""
    return ("needs the real akcli writer (%s); set %s=<absolute path> (looked for: %s)"
            % (purpose, ENV_VAR, describe_lookup()))
