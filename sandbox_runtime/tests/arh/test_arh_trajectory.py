"""ARH TrajectoryRecorder tests (RFC section 1.2 / 3.2 rows 6-7 / N4).

Covers: path-traversal refusal, append-only + crash-safe flush, line
envelope, event filtering, ``AttemptRow`` / ``RejectedRow`` projection
compared key-by-key against the frozen schema classes, fail-closed
projection, the LLM-visible vs audit views, and the three N4 assertions
(trajectory directory, no verdict-store keys, no verdict-store code).

Temp files live in the system temp directory via ``tempfile``; nothing is
written inside the repository and nothing touches the network.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import aedl_sandbox.arh.trajectory as trajectory_module
from aedl_sandbox.arh.schema import AttemptRow, RejectedRow
from aedl_sandbox.arh.trajectory import SCHEMA_ID, TrajectoryRecorder

FROZEN_TS = 1_700_000_000.0


def collect_keys(node, found: set[str]) -> set[str]:
    """Every mapping key anywhere inside a JSON-ish structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            collect_keys(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_keys(item, found)
    return found


class TrajectoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.run_dir = Path(tmp.name)

    def recorder(self, run_id: str = "run-1") -> TrajectoryRecorder:
        return TrajectoryRecorder(self.run_dir, run_id, clock=lambda: FROZEN_TS)


class RunIdConfinementTests(TrajectoryTestCase):
    def test_path_traversal_run_ids_are_rejected_before_any_write(self) -> None:
        for run_id in (
            "a/b",
            "a\\b",
            "../evil",
            "..\\evil",
            "..",
            ".",
            "/abs/path",
            "run/../evil",
            "",
            "   ",
            None,
            42,
        ):
            with self.subTest(run_id=run_id):
                with self.assertRaises(ValueError):
                    TrajectoryRecorder(self.run_dir, run_id, clock=lambda: FROZEN_TS)  # type: ignore[arg-type]
        # fail-closed: nothing was created for a refused identifier
        self.assertFalse((self.run_dir / "trajectory").exists())

    def test_path_is_a_trajectory_dir_with_a_jsonl_suffix(self) -> None:
        recorder = self.recorder("run-ok")
        path = recorder.path
        self.assertEqual(path.parent.name, "trajectory")
        self.assertEqual(path.suffix, ".jsonl")
        self.assertEqual(path.name, "run-ok.jsonl")
        self.assertEqual(path.parent.parent.resolve(), self.run_dir.resolve())
        self.assertTrue(path.parent.is_dir())


class RecordWriteTests(TrajectoryTestCase):
    def test_record_writes_one_line_with_the_documented_envelope(self) -> None:
        recorder = self.recorder()
        written = recorder.record("model_call", {"call": 1, "tokens": 12})
        lines = [line for line in recorder.path.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry, written)
        self.assertEqual(
            set(entry), {"schema", "seq", "ts", "run_id", "event", "payload"}
        )
        self.assertEqual(entry["schema"], SCHEMA_ID)
        self.assertEqual(entry["seq"], 1)
        self.assertEqual(entry["ts"], FROZEN_TS)
        self.assertEqual(entry["run_id"], "run-1")
        self.assertEqual(entry["event"], "model_call")
        self.assertEqual(entry["payload"], {"call": 1, "tokens": 12})
        # one physical line per record: the file is JSONL, not JSON
        self.assertEqual(len(lines), len(recorder.rows()))

    def test_records_append_without_rewriting_earlier_lines(self) -> None:
        recorder = self.recorder()
        recorder.record("context", {"round": 1})
        recorder.record("attempt", _attempt_payload(1))
        before = recorder.path.read_bytes()
        recorder.record("budget", {"calls": 1})
        after = recorder.path.read_bytes()
        self.assertTrue(after.startswith(before))
        self.assertEqual(after[: len(before)], before)

    def test_sequence_numbering_resumes_across_recorders(self) -> None:
        first = self.recorder()
        for round_ in (1, 2, 3):
            first.record("attempt", _attempt_payload(round_))
        self.assertEqual([row["seq"] for row in first.rows()], [1, 2, 3])
        raw_before = first.path.read_bytes()

        second = self.recorder()  # same run id, fresh process equivalent
        entry = second.record("model_call", {"call": 4})
        self.assertEqual(entry["seq"], 4)
        self.assertTrue(second.path.read_bytes().startswith(raw_before))
        self.assertEqual([row["seq"] for row in second.rows()], [1, 2, 3, 4])

    def test_record_rejects_a_bad_event_or_payload(self) -> None:
        recorder = self.recorder()
        for event, payload in (
            ("", {"a": 1}),
            (None, {"a": 1}),  # type: ignore[arg-type]
            ("model_call", []),  # type: ignore[arg-type]
            ("model_call", None),  # type: ignore[arg-type]
            ("model_call", "text"),  # type: ignore[arg-type]
        ):
            with self.subTest(event=event, payload=payload):
                with self.assertRaises(ValueError):
                    recorder.record(event, payload)  # type: ignore[arg-type]
        self.assertEqual(recorder.rows(), [])
        self.assertFalse(recorder.path.exists())

    def test_crash_after_record_leaves_a_complete_parseable_line(self) -> None:
        recorder = self.recorder()

        class Boom(RuntimeError):
            pass

        def step() -> None:
            recorder.record("model_call", {"call": 1, "tokens": 7})
            raise Boom("simulated crash immediately after the write")

        with self.assertRaises(Boom):
            step()
        # record() flushed before returning: the line is already durable
        lines = [
            line
            for line in recorder.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])  # must not raise
        self.assertEqual(entry["event"], "model_call")
        self.assertEqual(entry["run_id"], "run-1")
        # and a brand-new recorder reads the same durable state
        reopened = self.recorder()
        self.assertEqual(len(reopened.rows()), 1)
        self.assertEqual(reopened.rows()[0]["payload"], {"call": 1, "tokens": 7})


class AuditViewTests(TrajectoryTestCase):
    def test_rows_returns_every_event_and_filters_by_event(self) -> None:
        recorder = self.recorder()
        recorder.record("attempt", _attempt_payload(1))
        recorder.record("model_call", {"call": 1})
        recorder.record("attempt", _attempt_payload(2))
        recorder.record("rejected", _rejected_payload(1))
        self.assertEqual(len(recorder.rows()), 4)
        self.assertEqual(len(recorder.rows("attempt")), 2)
        self.assertEqual(len(recorder.rows("rejected")), 1)
        self.assertEqual(recorder.rows("no_such_event"), [])
        events = [row["event"] for row in recorder.rows()]
        self.assertEqual(events, ["attempt", "model_call", "attempt", "rejected"])

    def test_rows_on_a_fresh_run_dir_is_empty_not_an_error(self) -> None:
        recorder = self.recorder()
        self.assertEqual(recorder.rows(), [])

    def test_payload_text_survives_verbatim_including_line_separator_chars(self) -> None:
        recorder = self.recorder()
        payload = _attempt_payload(1)
        payload["diagnosis"] = "first line\u2028second line\r\nthird"
        recorder.record("attempt", payload)
        rows = recorder.rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["payload"]["diagnosis"], payload["diagnosis"])
        self.assertEqual(recorder.attempts()[0]["diagnosis"], payload["diagnosis"])

    def test_attempts_match_schema_attemptrow_to_row_key_by_key(self) -> None:
        recorder = self.recorder()
        payloads = [_attempt_payload(1), _attempt_payload(2)]
        for payload in payloads:
            recorder.record("attempt", payload)

        expected = [
            AttemptRow(
                round=1,
                fingerprint12=payloads[0]["fingerprint12"],
                diagnosis=payloads[0]["diagnosis"],
                design_action=payloads[0]["design_action"],
                subject_digest=payloads[0]["subject_digest"],
                outcome=payloads[0]["outcome"],
            ).to_row(),
            AttemptRow(
                round=2,
                fingerprint12=payloads[1]["fingerprint12"],
                diagnosis=payloads[1]["diagnosis"],
                design_action=payloads[1]["design_action"],
                subject_digest=payloads[1]["subject_digest"],
                outcome=payloads[1]["outcome"],
            ).to_row(),
        ]
        actual = recorder.attempts()
        self.assertEqual(actual, expected)
        for got, want in zip(actual, expected):
            self.assertEqual(set(got), set(want))
            for key in want:
                self.assertEqual(got[key], want[key], key)
        # RFC section 3.2 row 6 shape, spelled out
        self.assertEqual(
            set(expected[0]),
            {"round", "fingerprint12", "diagnosis", "proposal", "outcome"},
        )
        self.assertEqual(set(expected[0]["proposal"]), {"action", "subject_digest"})

    def test_rejected_match_schema_rejectedrow_to_row_key_by_key(self) -> None:
        recorder = self.recorder()
        payload = _rejected_payload(2)
        recorder.record("rejected", payload)
        expected = [
            RejectedRow(
                round=2,
                design_action=payload["design_action"],
                subject_digest=payload["subject_digest"],
                reason=payload["reason"],
            ).to_row()
        ]
        actual = recorder.rejected()
        self.assertEqual(actual, expected)
        self.assertEqual(
            set(actual[0]), {"round", "action", "subject_digest", "reason"}
        )
        self.assertEqual(actual[0]["action"], payload["design_action"])

    def test_projection_fails_closed_on_missing_or_mistyped_keys(self) -> None:
        recorder = self.recorder()
        missing = _attempt_payload(1)
        del missing["outcome"]
        recorder.record("attempt", missing)
        wrong_type = _attempt_payload(2)
        wrong_type["round"] = "2"
        recorder.record("attempt", wrong_type)
        bool_type = _attempt_payload(3)
        bool_type["round"] = True
        recorder.record("attempt", bool_type)
        missing_rejected = _rejected_payload(4)
        del missing_rejected["reason"]
        recorder.record("rejected", missing_rejected)
        wrong_rejected = _rejected_payload(5)
        wrong_rejected["subject_digest"] = 7
        recorder.record("rejected", wrong_rejected)

        with self.assertRaises(ValueError):
            recorder.attempts()
        with self.assertRaises(ValueError):
            recorder.rejected()
        with self.assertRaises(ValueError):
            recorder.llm_visible_rows()
        # the raw audit view still works: refusal is in the projection only
        self.assertEqual(len(recorder.rows("attempt")), 3)
        self.assertEqual(len(recorder.rows("rejected")), 2)

    def test_llm_visible_view_is_strictly_narrower_than_the_audit_view(self) -> None:
        recorder = self.recorder()
        recorder.record("attempt", _attempt_payload(1))
        recorder.record("attempt", _attempt_payload(2))
        recorder.record("rejected", _rejected_payload(1))
        recorder.record("model_call", {"call": 1, "tokens": 100})
        recorder.record("model_call", {"call": 2, "tokens": 90})
        recorder.record("context", {"round": 2})
        recorder.record("budget", {"calls": 2, "total_tokens": 190})

        audit_events = {row["event"] for row in recorder.rows()}
        visible = recorder.llm_visible_rows()
        self.assertEqual(
            set(visible), {"attempt_history", "rejected_proposals"}
        )
        self.assertEqual(len(visible["attempt_history"]), 2)
        self.assertEqual(len(visible["rejected_proposals"]), 1)
        # the difference between the two views is exactly the internal events
        self.assertEqual(
            audit_events - {"attempt", "rejected"},
            {"model_call", "context", "budget"},
        )
        self.assertEqual(len(recorder.rows()), 7)
        # model-visible rows are schema rows, never raw trajectory lines
        self.assertNotIn("schema", visible["attempt_history"][0])


class CrashSafetyTests(TrajectoryTestCase):
    def test_audit_view_fails_closed_on_a_corrupt_line(self) -> None:
        recorder = self.recorder()
        recorder.record("model_call", {"call": 1})
        with recorder.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write('{"schema":"arh_trajectory.v1","seq":2,"tru\n')
        with self.assertRaises(ValueError):
            recorder.rows()

    def test_a_torn_tail_is_terminated_so_the_next_line_stays_aligned(self) -> None:
        recorder = self.recorder()
        path = recorder.path
        path.write_bytes(b'{"schema":"arh_trajectory.v1","seq":1,"torn')  # no newline

        reopened = self.recorder()  # repairs by appending a newline only
        raw = path.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertEqual(raw.count(b"\n"), 1)

        entry = reopened.record("model_call", {"call": 2})
        self.assertEqual(entry["seq"], 2)
        lines = path.read_bytes().split(b"\n")
        self.assertTrue(lines[-1] == b"" and lines[-2])
        self.assertEqual(json.loads(lines[-2])["event"], "model_call")


class NonEvidenceBoundaryTests(TrajectoryTestCase):
    """N4 acceptance: trajectory is observation, never an evidence artifact."""

    def test_recorded_lines_carry_no_verdict_store_keys(self) -> None:
        recorder = self.recorder()
        recorder.record("attempt", _attempt_payload(1))
        recorder.record("rejected", _rejected_payload(1))
        recorder.record("model_call", {"call": 1, "tokens": 10})
        recorder.record("budget", {"calls": 1, "total_tokens": 10})
        found: set[str] = set()
        for row in recorder.rows():
            collect_keys(row, found)
        self.assertNotIn("event_hash", found)
        self.assertNotIn("valid", found)
        # and the envelope itself stays the six documented keys
        for row in recorder.rows():
            self.assertEqual(
                set(row), {"schema", "seq", "ts", "run_id", "event", "payload"}
            )

    def test_source_text_never_mentions_the_verdict_store(self) -> None:
        source = Path(trajectory_module.__file__).read_text(encoding="utf-8")
        lowered = source.lower()
        self.assertNotIn("trust", lowered)
        self.assertNotIn("receipt_root", lowered)
        self.assertNotIn("aedl_sandbox.trust", lowered)
        self.assertNotIn("filetruststore", lowered)


def _attempt_payload(round_: int) -> dict:
    return {
        "round": round_,
        "fingerprint12": f"fp{round_:010d}"[:12],
        "diagnosis": f"D{round_}: finding text",
        "design_action": "DESIGN_SELECT_COMPONENT",
        "subject_digest": f"subj{round_:010d}",
        "outcome": "REJECTED" if round_ % 2 else "APPLIED",
    }


def _rejected_payload(round_: int) -> dict:
    return {
        "round": round_,
        "design_action": "DESIGN_ASSIGN_PIN",
        "subject_digest": f"subj{round_:010d}",
        "reason": "duplicate of an earlier submission",
    }


if __name__ == "__main__":
    unittest.main()
