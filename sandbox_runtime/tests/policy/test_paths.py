"""Path containment regression: root and target are compared at the same
resolution level (realpath), so junctions/symlinks cannot cause false escapes
(GH-20 CI matrix finding: GitHub Windows runner TEMP behind a junction made
every FILE_WRITE resolve as POLICY_PATH_ESCAPE)."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from aedl_sandbox.policy.paths import is_within


class PathContainmentTests(unittest.TestCase):
    def test_plain_containment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "candidate"
            root.mkdir()
            self.assertTrue(is_within(root, (root / "a" / "b").resolve()))
            self.assertFalse(is_within(root, (Path(tmp).parent / "outside").resolve()))

    @unittest.skipUnless(os.name == "nt", "junction regression is Windows-only")
    def test_containment_through_a_junction_does_not_false_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real = base / "real"
            real.mkdir()
            link = base / "link"
            # cmd.exe emits localized ANSI/OEM-codepage bytes (never UTF-8);
            # text=True without an errors strategy crashed a subprocess reader
            # thread inside the gate (review iteration 4, 2026-09-02). Only the
            # return code drives logic, so undecodable bytes are replaced.
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(real)],
                capture_output=True, text=True, errors="replace",
            )
            if result.returncode != 0:
                self.skipTest(f"junction creation failed: {result.stderr}")
            root = link / "candidate"                 # unresolved form (junction inside)
            root.mkdir(parents=True)
            target = (root / "design.net").resolve()  # resolved form (real path)
            self.assertTrue(is_within(root, target), "junction must not false-escape")
            outside = (base / "outside.net").resolve()
            self.assertFalse(is_within(root, outside))
