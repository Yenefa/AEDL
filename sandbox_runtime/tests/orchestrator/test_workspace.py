"""RED/GREEN tests for CandidateWorkspace confinement (Agent H, Wave 1)."""

from __future__ import annotations

import hashlib
import os
import subprocess
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

class CandidateIsolationAdversarial(unittest.TestCase):
    """F1: writes and identity must be confined to THE CANDIDATE.

    The original check bounded against the WORKSPACE, so any destination still
    inside the workspace passed -- including a sibling candidate. That is the
    whole defect: the boundary was one level too coarse.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.ws_root = self.base / "ws"
        self.run = "run-1"
        self.a = self.ws_root / "run" / self.run / "candidate" / "candidate-a"
        self.b = self.ws_root / "run" / self.run / "candidate" / "candidate-b"
        self.a.mkdir(parents=True)
        self.b.mkdir(parents=True)
        (self.a / "a-only.txt").write_bytes(b"A-ONLY")
        (self.b / "b-only.txt").write_bytes(b"B-ORIGINAL")
        self.ws = CandidateWorkspace(self.ws_root)

    def _junction(self, link: Path, target: Path) -> bool:
        """A Windows directory junction, which needs no elevation."""
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError):
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(target)],
                capture_output=True, text=True, timeout=30)
            if not link.exists():
                self.skipTest("no directory link could be made here: %s"
                              % ((result.stdout or result.stderr).strip()[:80]))
        return True

    def _hardlink(self, link: Path, target: Path) -> None:
        try:
            os.link(str(target), str(link))
        except (OSError, NotImplementedError) as exc:
            self.skipTest("no hard link could be made here: %s" % exc)

    def _digest(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    # ------------------------------------------------------------------ 1
    def test_a_junction_into_another_candidate_refuses_the_write(self):
        self._junction(self.a / "redirect", self.b)
        before = self._digest(self.b / "b-only.txt")
        with self.assertRaises(WorkspaceEscapeError) as caught:
            self.ws.write_candidate_bytes(self.run, "candidate-a",
                                          "redirect/planted.txt", b"CHANGED")
        message = str(caught.exception)
        self.assertIn("candidate root", message,
                      "the refusal must name the boundary it escaped")
        # and the other candidate is untouched, by DIGEST -- so the test cannot
        # pass just because the write failed for an unrelated reason
        self.assertEqual(self._digest(self.b / "b-only.txt"), before)
        self.assertFalse((self.b / "planted.txt").exists())

    def test_a_hard_link_into_another_candidate_refuses_the_write(self):
        """The route `resolve()` cannot see.

        Measured: a hard link planted in A at a file in B resolves to a path
        INSIDE A, because both names are legitimate paths to one inode. So
        resolve-then-compare passes and the write lands in B. Only a link count
        catches it.
        """
        self._hardlink(self.a / "planted.txt", self.b / "b-only.txt")
        self.assertEqual(os.stat(str(self.b / "b-only.txt")).st_nlink, 2)
        before = self._digest(self.b / "b-only.txt")
        with self.assertRaises(WorkspaceEscapeError) as caught:
            self.ws.write_candidate_bytes(self.run, "candidate-a",
                                          "planted.txt", b"WRITTEN-THROUGH")
        self.assertIn("hard link", str(caught.exception))
        self.assertEqual(self._digest(self.b / "b-only.txt"), before,
                         "the other candidate's bytes changed")

    # ------------------------------------------------------------------ 2
    def test_a_junction_inside_a_candidate_refuses_its_content_hash(self):
        """The silent one, and worse than the stray write.

        `rglob` follows a Windows junction, so the walk descended into the sibling
        candidate and mixed its files into this candidate's identity. Measured
        before the fix: candidate-a's hash changed when the junction was added,
        and changed AGAIN when a file in candidate-b was edited.
        """
        clean = self.ws.candidate_hash(self.run, "candidate-a")
        self._junction(self.a / "peek", self.b)
        with self.assertRaises(WorkspaceEscapeError) as caught:
            self.ws.candidate_hash(self.run, "candidate-a")
        self.assertIn("link or junction", str(caught.exception))
        # The refusal did not CHANGE the identity of the clean case -- it declined
        # to produce one at all. Asserted by removing the link and checking the
        # hash comes back to what it was, which is also the only way to show the
        # fix leaves the ordinary path alone. An earlier version asserted the clean
        # hash WHILE the junction was planted, which contradicts the refusal it had
        # just asserted and made the test error on its own second line.
        # os.rmdir, NOT shutil.rmtree. Measured: rmtree does not remove a
        # Windows junction at all -- the junction survives and the target is
        # left alone -- so an rmtree cleanup silently does nothing and the test
        # then errors on its own last assertion. os.rmdir removes the junction
        # itself rather than following it.
        os.rmdir(str(self.a / "peek"))
        self.assertFalse((self.a / "peek").exists())
        self.assertTrue((self.b / "b-only.txt").exists(),
                        "removing the junction must not touch its target")
        self.assertEqual(self.ws.candidate_hash(self.run, "candidate-a"), clean,
                         "the ordinary hash moved once the link was removed")

    def test_a_clean_candidate_hash_is_unchanged_by_the_fix(self):
        """A stricter bound that perturbs the normal path is not a fix."""
        first = self.ws.candidate_hash(self.run, "candidate-a")
        (self.a / "new.txt").write_bytes(b"NEW")
        self.assertNotEqual(self.ws.candidate_hash(self.run, "candidate-a"), first)
        self.assertEqual(self.ws.candidate_hash(self.run, "candidate-a"),
                         self.ws.candidate_hash(self.run, "candidate-a"),
                         "the hash is not deterministic")

    def test_the_ledger_is_still_excluded_from_the_hash(self):
        """Exclusion is a hash rule, not a licence to skip confinement."""
        self.ws.record_action(self.run, "candidate-a", "a1", {"ok": True})
        with_digest = self.ws.candidate_hash(self.run, "candidate-a")
        (self.a / "x.txt").write_bytes(b"X")
        self.assertNotEqual(self.ws.candidate_hash(self.run, "candidate-a"),
                            with_digest)
        self.assertTrue((self.a / ".actions.jsonl").exists())

    # ------------------------------------------------------------------ 3
    def test_reading_a_hard_linked_ledger_refuses_rather_than_disclosing(self):
        """The READ side, which is a different risk from the write side.

        The first version of this test planted a junction inside candidate B
        pointing at A and then recorded an action for A -- whose ledger path
        (`candidate-a/.actions.jsonl`) never traverses B's junction. Nothing
        escaped, the write legitimately succeeded, and the test failed for the
        wrong reason.

        The real ledger route is the file itself being an alias, and reading it is
        a DISCLOSURE rather than only a confinement failure: `get_recorded_action`
        returning another candidate's ledger contents hands over its history.
        """
        self._hardlink(self.a / ".actions.jsonl", self.b / "b-only.txt")
        # Either the call refuses, or it returns nothing. Stated plainly: the
        # first version wrote a conditional assertion that failed ON the correct
        # behaviour, because it compared "REFUSED" with "REFUSED" precisely when
        # the refusal worked.
        try:
            got = self.ws.get_recorded_action(self.run, "candidate-a", "anything")
        except WorkspaceEscapeError:
            got = None
        self.assertIsNone(
            got, "a hard-linked ledger returned another candidate's contents: %r"
            % (got,))

    def test_a_hard_linked_ledger_is_refused(self):
        """The ledger is excluded from the content hash, so it is a convenient
        place to park things that are not design content -- which makes it worth
        at least as much attention as the design files, not less."""
        self._hardlink(self.a / ".actions.jsonl", self.b / "b-only.txt")
        before = self._digest(self.b / "b-only.txt")
        with self.assertRaises(WorkspaceEscapeError) as caught:
            self.ws.record_action(self.run, "candidate-a", "a1", {"ok": True})
        self.assertIn("hard link", str(caught.exception))
        self.assertEqual(self._digest(self.b / "b-only.txt"), before,
                         "the other candidate's ledger was appended to")

    def test_a_legitimate_ledger_still_works(self):
        """The control for the case above: the refusal must be about ALIASES, not
        about the ledger existing."""
        self.ws.record_action(self.run, "candidate-a", "a1", {"ok": True})
        got = self.ws.get_recorded_action(self.run, "candidate-a", "a1")
        self.assertEqual(got, {"ok": True})

    # ------------------------------------------------------------------ 4
    def test_the_workspace_boundary_still_holds(self):
        """The candidate bound is strictly TIGHTER, so the original outer check
        must still refuse what it always refused."""
        outside = self.base / "outside"
        outside.mkdir()
        self.ws.create_candidate(self.run, "cand-y")
        link = self.ws_root / "run" / self.run / "candidate" / "cand-y" / "out"
        self._junction(link, outside)
        with self.assertRaises(WorkspaceEscapeError):
            self.ws.write_candidate_bytes(self.run, "cand-y", "out/evil.txt", b"x")
        self.assertFalse((outside / "evil.txt").exists())

    def test_a_candidate_root_that_is_itself_a_link_is_refused(self):
        """A boundary reached through a link is not a boundary."""
        self._junction(self.a / "self", self.a)
        candidate = self.ws_root / "run" / self.run / "candidate" / "cand-link"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        self._junction(candidate, self.b)
        with self.assertRaises(WorkspaceEscapeError) as caught:
            self.ws.write_candidate_bytes(self.run, "cand-link", "x.txt", b"x")
        self.assertIn("link or junction", str(caught.exception))
