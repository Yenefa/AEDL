"""RED/GREEN tests for CandidateWorkspace confinement (Agent H, Wave 1)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from aedl_sandbox.workspace import CandidateWorkspace, WorkspaceEscapeError


class CandidateWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.ws = CandidateWorkspace(self.base / "ws")

    def test_creates_only_the_documented_candidate_layout(self):
        candidate = self.ws.create_candidate("run-1", "cand-1")
        expected = self.base / "ws" / "run" / "run-1" / "candidate" / "cand-1"
        # Compare at the same resolution level: the module resolves paths and
        # Windows runners may canonicalize TEMP to an 8.3 short name
        # (RUNNER~1), so an unresolved expectation would false-fail.
        self.assertEqual(candidate.resolve(), expected.resolve())
        self.assertTrue(candidate.is_dir())

    def test_rejects_traversal_identifiers(self):
        for run_id, candidate_id in (
            ("../evil", "cand-1"),
            ("run/../evil", "cand-1"),
            ("a/b", "cand-1"),
            (".", "cand-1"),
            ("run-1", ".."),
            ("run-1", "cand/../escape"),
            ("run-1", "c/x"),
            ("run-1", "/abs"),
            ("run-1", "con"),
        ):
            with self.subTest(f"{run_id!r}/{candidate_id!r}"):
                with self.assertRaises(WorkspaceEscapeError):
                    self.ws.create_candidate(run_id, candidate_id)
        self.assertFalse((self.base / "ws" / "run").exists())

    def test_rejects_absolute_candidate_path(self):
        self.ws.create_candidate("run-1", "cand-1")
        outside = self.base / "outside.txt"
        with self.assertRaises(WorkspaceEscapeError):
            self.ws.write_candidate_bytes("run-1", "cand-1", str(outside), b"x")
        self.assertFalse(outside.exists())

    def test_rejects_relative_traversal_writes(self):
        self.ws.create_candidate("run-1", "cand-1")
        for relative in ("../escape.txt", "sub/../../escape.txt", "..", "."):
            with self.subTest(relative):
                with self.assertRaises(WorkspaceEscapeError):
                    self.ws.write_candidate_bytes("run-1", "cand-1", relative, b"x")
        self.assertFalse((self.base / "ws" / "run" / "run-1" / "escape.txt").exists())
        self.assertFalse((self.base / "escape.txt").exists())

    def _link_to(self, link: Path, target: Path) -> None:
        """Materialize a directory link: symlink preferred, junction fallback.

        Some Windows hosts report success for symlink_to without actually
        materializing the reparse point; verify it exists and fall through
        to CreateJunction (which requires no privilege) so the escape
        rejection is genuinely exercised instead of silently skipped.
        """
        try:
            link.symlink_to(target, target_is_directory=True)
            if link.is_symlink():
                return
        except OSError:
            pass
        import _winapi

        _winapi.CreateJunction(str(target), str(link))

    def test_rejects_symlink_escape_and_writes_nothing_outside(self):
        outside = self.base / "outside"
        outside.mkdir()
        candidate = self.ws.create_candidate("run-1", "cand-1")
        link = candidate / "link"
        try:
            self._link_to(link, outside)
        except Exception:
            self.skipTest("symlink/junction creation not permitted on this platform")
        if not os.path.lexists(link):
            self.skipTest(
                "symlink/junction creation silently suppressed on this platform"
            )
        with self.assertRaises(WorkspaceEscapeError):
            self.ws.write_candidate_bytes("run-1", "cand-1", "link/evil.txt", b"x")
        self.assertFalse((outside / "evil.txt").exists())

    def test_confined_relative_write_succeeds(self):
        self.ws.create_candidate("run-1", "cand-1")
        target = self.ws.write_candidate_bytes("run-1", "cand-1", "artifacts/a.json", b"{}")
        self.assertTrue(target.exists())
        self.assertEqual(
            target.resolve(),
            (self.base / "ws" / "run" / "run-1" / "candidate" / "cand-1" / "artifacts" / "a.json").resolve(),
        )

    def test_action_ledger_returns_first_recorded_result(self):
        self.ws.create_candidate("run-1", "cand-1")
        self.ws.record_action("run-1", "cand-1", "a1", {"success": True})
        self.ws.record_action("run-1", "cand-1", "a1", {"success": False})
        self.assertEqual(
            self.ws.get_recorded_action("run-1", "cand-1", "a1"), {"success": True}
        )
        self.assertIsNone(self.ws.get_recorded_action("run-1", "cand-1", "missing"))

    def test_candidate_hash_ignores_only_declared_bookkeeping_and_is_stable(self):
        self.ws.create_candidate("run-1", "cand-1")
        self.ws.write_candidate_bytes("run-1", "cand-1", "a.txt", b"alpha")
        self.ws.record_action("run-1", "cand-1", "a1", {"success": True})
        first = self.ws.candidate_hash("run-1", "cand-1")
        self.ws.record_action("run-1", "cand-1", "a2", {"success": True})
        second = self.ws.candidate_hash("run-1", "cand-1")
        self.assertEqual(first, second)
        self.ws.write_candidate_bytes("run-1", "cand-1", "b.txt", b"beta")
        self.assertNotEqual(first, self.ws.candidate_hash("run-1", "cand-1"))

    def test_hidden_file_mutation_changes_candidate_hash(self):
        # Review P1 counter-example: mutating a hidden engineering file after
        # verification must change candidate_sha256 so receipts bound to the
        # old hash are rejected as stale evidence.
        self.ws.create_candidate("run-1", "cand-1")
        self.ws.write_candidate_bytes("run-1", "cand-1", "board.kicad_sch", b"content")
        self.ws.write_candidate_bytes("run-1", "cand-1", ".project_meta", b"v1")
        before = self.ws.candidate_hash("run-1", "cand-1")
        self.ws.write_candidate_bytes("run-1", "cand-1", ".project_meta", b"v2-mutated")
        after = self.ws.candidate_hash("run-1", "cand-1")
        self.assertNotEqual(before, after)

    def test_candidate_hash_includes_hidden_files_and_directories(self):
        self.ws.create_candidate("run-1", "cand-1")
        self.ws.write_candidate_bytes("run-1", "cand-1", "a.txt", b"alpha")
        self.ws.write_candidate_bytes("run-1", "cand-1", ".hidden/config.json", b"v1")
        first = self.ws.candidate_hash("run-1", "cand-1")
        self.ws.write_candidate_bytes("run-1", "cand-1", ".hidden/config.json", b"v2")
        self.assertNotEqual(first, self.ws.candidate_hash("run-1", "cand-1"))
        # a fresh hidden file also changes the hash
        self.ws.write_candidate_bytes("run-1", "cand-1", ".hidden/extra.json", b"{}")
        self.assertNotEqual(first, self.ws.candidate_hash("run-1", "cand-1"))

    def test_ledger_named_file_in_subdirectory_is_content_not_bookkeeping(self):
        # Only the candidate-root action ledger is internal bookkeeping; a
        # content file that happens to share its name participates in the
        # hash like any other engineering file.
        self.ws.create_candidate("run-1", "cand-1")
        self.ws.write_candidate_bytes("run-1", "cand-1", "a.txt", b"alpha")
        self.ws.record_action("run-1", "cand-1", "a1", {"success": True})
        without = self.ws.candidate_hash("run-1", "cand-1")
        self.ws.write_candidate_bytes("run-1", "cand-1", "sub/.actions.jsonl", b"not-the-ledger")
        self.assertNotEqual(without, self.ws.candidate_hash("run-1", "cand-1"))

    def test_derive_candidate_id_is_deterministic_and_input_sensitive(self):
        first = CandidateWorkspace.derive_candidate_id("r", "d", "b", {"x": 1})
        same = CandidateWorkspace.derive_candidate_id("r", "d", "b", {"x": 1})
        other = CandidateWorkspace.derive_candidate_id("r", "d", "b", {"x": 2})
        self.assertEqual(first, same)
        self.assertNotEqual(first, other)


if __name__ == "__main__":
    unittest.main()
