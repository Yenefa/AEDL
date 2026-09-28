"""ARH trajectory recorder: append-only observation, never evidence (N4).

RFC section 1.2 / section 2.5 N4 / threat T-06: the trajectory is a
report-class observation of what the harness did during one run. It is not
identity, not an evidence artifact, and it never feeds the candidate hash or
any promotion predicate. Concretely, this module:

* writes only to its own directory and extension,
  ``<run_dir>/trajectory/<run_id>.jsonl``: one JSON object per line,
  append-only (existing lines are never rewritten), flushed and fsync'd
  before ``record()`` returns, so a crash right after any step still leaves
  every completed line individually parseable;
* imports nothing from the verdict/evidence side of the package: schema data
  classes only, and no verdict-shaped field is ever produced here;
* validates ``run_id`` against path traversal (``/``, ``\\``, ``..``) before
  touching the filesystem;
* exposes two views: ``rows()`` -- every recorded event, the audit view --
  and ``llm_visible_rows()`` -- only the attempt history and rejected
  proposals (RFC section 3.2 rows 6-7) that the next round's context may
  show a model.

Projection is fail-closed: an ``attempt`` / ``rejected`` event missing a key
or carrying the wrong type raises ``ValueError`` instead of producing a row
the context builder would misread later, and a corrupt line makes the audit
view raise rather than silently drop observation.

A torn final line (hard kill mid-write) is line-terminated by the next
recorder construction, appending only, so subsequent records stay aligned
and the damage remains visible instead of being spliced into a later line.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from aedl_sandbox.arh.schema import AttemptRow, RejectedRow

__all__ = ["SCHEMA_ID", "TrajectoryRecorder"]

#: Versioned line schema; an audit reader refuses anything else (N4).
SCHEMA_ID = "arh_trajectory.v1"


def _validate_run_id(run_id: str) -> str:
    """A run id must be a plain file-name stem: no separators, no traversal."""
    if not isinstance(run_id, str):
        raise ValueError(f"run_id must be a string, got {type(run_id).__name__}")
    if not run_id.strip():
        raise ValueError("run_id must not be empty")
    for token in ("/", "\\", ".."):
        if token in run_id:
            raise ValueError(
                f"run_id {run_id!r} must not contain {token!r} "
                "(path traversal is refused)"
            )
    if run_id.startswith("."):
        raise ValueError(f"run_id {run_id!r} must not start with '.'")
    return run_id


def _require_str(payload: Mapping[str, Any], key: str, event: str) -> str:
    if key not in payload:
        raise ValueError(f"{event} payload is missing required key {key!r}")
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(
            f"{event} payload key {key!r} must be a string, "
            f"got {type(value).__name__}"
        )
    return value


def _require_int(payload: Mapping[str, Any], key: str, event: str) -> int:
    if key not in payload:
        raise ValueError(f"{event} payload is missing required key {key!r}")
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"{event} payload key {key!r} must be an integer, "
            f"got {type(value).__name__}"
        )
    return value


class TrajectoryRecorder:
    """Append-only JSONL recorder for one run (RFC section 1.2)."""

    def __init__(
        self,
        run_dir: Path,
        run_id: str,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        checked = _validate_run_id(run_id)
        self._run_id = checked
        self._clock = clock
        self._directory = Path(run_dir) / "trajectory"
        self._directory.mkdir(parents=True, exist_ok=True)
        self._path = self._directory / f"{checked}.jsonl"
        self._seq = self._open_existing()

    # ------------------------------------------------------------------
    # file state
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """``<run_dir>/trajectory/<run_id>.jsonl`` (never a verdict store)."""
        return self._path

    @property
    def run_id(self) -> str:
        return self._run_id

    def _open_existing(self) -> int:
        """Terminate a torn tail (append only) and resume the sequence."""
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return 0
        if raw and not raw.endswith(b"\n"):
            # A previous process died mid-line: close the line so the next
            # record cannot be spliced onto the fragment. Never rewrite.
            with self._path.open("ab") as handle:
                handle.write(b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            raw += b"\n"
        # Count complete lines only: a fragment consumes its sequence slot so
        # no number is ever handed out twice.
        return raw.count(b"\n")

    # ------------------------------------------------------------------
    # writing
    # ------------------------------------------------------------------

    def record(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Append one event and durably flush it before returning.

        Returns exactly the object written, so callers can log its ``seq``
        without re-reading the file.
        """
        if not isinstance(event_type, str) or not event_type:
            raise ValueError(
                f"event must be a non-empty string, got {event_type!r}"
            )
        if not isinstance(payload, Mapping):
            raise ValueError(
                f"payload must be a mapping, got {type(payload).__name__}"
            )
        entry: dict[str, Any] = {
            "schema": SCHEMA_ID,
            "seq": self._seq + 1,
            "ts": self._clock(),
            "run_id": self._run_id,
            "event": event_type,
            "payload": dict(payload),
        }
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        # Committed only after the write survived flush + fsync: a failed
        # write must not consume a sequence number.
        self._seq += 1
        return entry

    # ------------------------------------------------------------------
    # reading (audit view)
    # ------------------------------------------------------------------

    def rows(self, event: str | None = None) -> list[dict[str, Any]]:
        """Every recorded line as a dict, optionally filtered by event.

        This is the full audit view: model calls, budget snapshots, context
        builds -- everything. ``llm_visible_rows()`` is the narrow one.
        """
        if not self._path.exists():
            return []
        text = self._path.read_text(encoding="utf-8")
        rows: list[dict[str, Any]] = []
        # Split on the exact separator this module writes; splitlines() would
        # also break inside a payload on U+2028/U+2029 from model text.
        for index, line in enumerate(text.split("\n"), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"trajectory line {index} of {self._path} is not valid JSON"
                ) from exc
            if not isinstance(entry, dict) or entry.get("schema") != SCHEMA_ID:
                raise ValueError(
                    f"trajectory line {index} of {self._path} does not carry "
                    f"schema {SCHEMA_ID!r}"
                )
            if event is None or entry.get("event") == event:
                rows.append(entry)
        return rows

    # ------------------------------------------------------------------
    # projection (RFC section 3.2 rows 6-7)
    # ------------------------------------------------------------------

    def attempts(self) -> list[dict[str, Any]]:
        """``attempt_history`` rows, exactly as ``AttemptRow.to_row()``."""
        rows: list[dict[str, Any]] = []
        for entry in self.rows("attempt"):
            payload = _payload_of(entry, "attempt")
            rows.append(
                AttemptRow(
                    round=_require_int(payload, "round", "attempt"),
                    fingerprint12=_require_str(payload, "fingerprint12", "attempt"),
                    diagnosis=_require_str(payload, "diagnosis", "attempt"),
                    design_action=_require_str(payload, "design_action", "attempt"),
                    subject_digest=_require_str(payload, "subject_digest", "attempt"),
                    outcome=_require_str(payload, "outcome", "attempt"),
                ).to_row()
            )
        return rows

    def rejected(self) -> list[dict[str, Any]]:
        """``rejected_proposals`` rows, exactly as ``RejectedRow.to_row()``."""
        rows: list[dict[str, Any]] = []
        for entry in self.rows("rejected"):
            payload = _payload_of(entry, "rejected")
            rows.append(
                RejectedRow(
                    round=_require_int(payload, "round", "rejected"),
                    design_action=_require_str(payload, "design_action", "rejected"),
                    subject_digest=_require_str(payload, "subject_digest", "rejected"),
                    reason=_require_str(payload, "reason", "rejected"),
                ).to_row()
            )
        return rows

    def llm_visible_rows(self) -> dict[str, list[dict[str, Any]]]:
        """The only trajectory projection a model may ever see (N4)."""
        return {
            "attempt_history": self.attempts(),
            "rejected_proposals": self.rejected(),
        }


def _payload_of(entry: Mapping[str, Any], event: str) -> Mapping[str, Any]:
    payload = entry.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError(f"{event} payload must be an object")
    return payload
