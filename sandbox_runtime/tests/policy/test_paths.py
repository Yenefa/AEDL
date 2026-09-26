"""Path containment regression: root and target are compared at the same
resolution level (realpath), so junctions/symlinks cannot cause false escapes
(GH-20 CI matrix finding: GitHub Windows runner TEMP behind a junction made
every FILE_WRITE resolve as POLICY_PATH_ESCAPE).

Issue #51: the junction setup itself was not idempotent. `mklink /J` returns 0
but the reparse point is not always usable immediately, and the following
`root.mkdir(parents=True)` then raised FileExistsError [WinError 183] before
any containment assertion ran - silently removing the GH-20 regression
coverage. Setup now verifies readiness and retries instead of trusting rc=0.
"""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from aedl_sandbox.policy.paths import is_within

# Windows error codes that mean "the directory entry is already there", not
# "the caller is wrong": 183 = ERROR_ALREADY_EXISTS (the #51 symptom),
# 145 = ERROR_DIR_NOT_EMPTY (the same race seen through a junction parent).
_TRANSIENT_MKDIR_ERRNOS = frozenset({183, 145})
_RETRY_ATTEMPTS = 5
_RETRY_BASE_SLEEP_S = 0.05


def _mkdir_transient_safe(path: Path, attempts: int = _RETRY_ATTEMPTS) -> None:
    """mkdir() that tolerates the WinError 183/145 junction race, else fails.

    Only those two winerror values are retried. Anything else (access denied,
    path exists as a file, read-only volume, ...) propagates on the first
    attempt, and a persistent 183/145 still propagates after `attempts` - this
    must not become a silent pass.

    Deliberately NOT exist_ok=True: a genuinely pre-existing leaf has to stay
    an error, otherwise the test would quietly stop testing anything.
    """
    for attempt in range(attempts):
        try:
            path.mkdir(parents=True)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) not in _TRANSIENT_MKDIR_ERRNOS:
                raise
            if attempt == attempts - 1:
                raise
            time.sleep(_RETRY_BASE_SLEEP_S * (attempt + 1))


def _synthetic_oserror(exc_class, winerror: int) -> OSError:
    """Build an OSError carrying a chosen .winerror, as Windows raises it."""
    error = exc_class(f"synthetic winerror {winerror}")
    error.winerror = winerror
    return error


def _junction_resolves_to(link: Path, real: Path) -> bool:
    """True when `link` is a directory that actually reaches `real`.

    os.path.samefile() compares stat() identity, so a working junction answers
    True. os.path.islink() is NOT usable here: on Python 3.9 a junction's
    lstat mode is S_IFDIR rather than S_IFLNK, so islink() answers False.
    """
    try:
        return link.is_dir() and os.path.samefile(link, real)
    except OSError:
        return False


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
            #
            # Issue #51: rc=0 is not proof the junction is usable, so readiness
            # is verified (samefile) and creation is retried. rc != 0 keeps the
            # original skip (junctions unavailable in this environment), but
            # rc == 0 with an unusable junction FAILS: mklink claimed success,
            # so losing the regression coverage must be loud, not a skip.
            for attempt in range(_RETRY_ATTEMPTS):
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(real)],
                    capture_output=True, text=True, errors="replace",
                )
                if _junction_resolves_to(link, real):
                    break
                if result.returncode != 0:
                    self.skipTest(f"junction creation failed: {result.stderr}")
                if attempt < _RETRY_ATTEMPTS - 1:
                    time.sleep(_RETRY_BASE_SLEEP_S * (attempt + 1))
            else:
                self.fail(
                    f"mklink returned 0 but the junction is not traversable after "
                    f"{_RETRY_ATTEMPTS} attempts (issue #51 regression)"
                )
            root = link / "candidate"                 # unresolved form (junction inside)
            _mkdir_transient_safe(root)
            target = (root / "design.net").resolve()  # resolved form (real path)
            self.assertTrue(is_within(root, target), "junction must not false-escape")
            outside = (base / "outside.net").resolve()
            self.assertFalse(is_within(root, outside))


class MkdirTransientSafeTests(unittest.TestCase):
    """Deterministic coverage for the #51 retry helper (no Windows race needed)."""

    def test_retries_winerror_183_then_succeeds(self):
        real_mkdir = Path.mkdir
        calls = []

        def fake_mkdir(self, *args, **kwargs):
            # Only the target is faked: Path.mkdir(parents=True) recurses into
            # self.parent.mkdir(), so a blanket patch would intercept the
            # parent's creation too and count it as a retry.
            if self != target:
                return real_mkdir(self, *args, **kwargs)
            calls.append(self)
            if len(calls) < 3:
                raise _synthetic_oserror(OSError, 183)
            return real_mkdir(self, *args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "candidate"
            with mock.patch.object(Path, "mkdir", fake_mkdir):
                _mkdir_transient_safe(target)
            self.assertTrue(target.is_dir(), "retry must actually create the directory")

        self.assertEqual(len(calls), 3, "two transient failures then one success")

    def test_persistent_winerror_183_fails_closed(self):
        calls = []

        def fake_mkdir(self, *args, **kwargs):
            calls.append(self)
            raise _synthetic_oserror(OSError, 183)

        with mock.patch.object(Path, "mkdir", fake_mkdir):
            with self.assertRaises(OSError):
                _mkdir_transient_safe(Path("Z:/not-created"))

        self.assertEqual(len(calls), _RETRY_ATTEMPTS, "must retry, then still raise")

    def test_non_transient_oserror_is_not_retried(self):
        calls = []

        def fake_mkdir(self, *args, **kwargs):
            calls.append(self)
            raise _synthetic_oserror(PermissionError, 5)

        with mock.patch.object(Path, "mkdir", fake_mkdir):
            with self.assertRaises(PermissionError):
                _mkdir_transient_safe(Path("Z:/not-created"))

        self.assertEqual(len(calls), 1, "access denied is a real failure, not a race")
