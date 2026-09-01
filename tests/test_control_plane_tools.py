"""Unit tests for the control plane minimal slice (envelope / gate / admit).

Pure-logic tests only: no git, gh, uv or interpreter required at test time
(dev_gate dry-run exercises the receipt shape without running checks).
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.admit import dependency_satisfied, ref_number
from tools import dev_gate
from tools.envelope import parse_envelope, path_in_scope, scope_violations

FULL_ENVELOPE = """# Task Envelope example
task: GH-11

base:
  branch: master
  sha: abc123def456

goal: |
  Free text that tooling never interprets.

dependencies:
  - ref: GH-9
    required_state: merged
  - GH-12: closed

allowed_paths:
  - src/**
  - AGENTS.md

forbidden_paths:
  - gates/**
  - docs/evidence/**

change_budget:
  expected_files: 3
"""


class EnvelopeParseTests(unittest.TestCase):
    def test_full_envelope(self):
        env = parse_envelope(FULL_ENVELOPE)
        self.assertEqual(env["errors"], [])
        self.assertEqual(env["task"], "GH-11")
        self.assertEqual(env["base_branch"], "master")
        self.assertEqual(env["base_sha"], "abc123def456")
        self.assertEqual(env["dependencies"],
                         [{"ref": "GH-9", "required_state": "merged"},
                          {"ref": "GH-12", "required_state": "closed"}])
        self.assertEqual(env["allowed_paths"], ["src/**", "AGENTS.md"])
        self.assertEqual(env["forbidden_paths"], ["gates/**", "docs/evidence/**"])

    def test_missing_required_state_is_error(self):
        env = parse_envelope("task: GH-1\nbase:\n  branch: master\n  sha: a\n"
                             "dependencies:\n  - ref: GH-2\n")
        self.assertIn("lacks required_state", " ".join(env["errors"]))

    def test_malformed_section_is_error(self):
        env = parse_envelope("base:\n  nonsense: 1\n")
        self.assertTrue(any("unsupported base field" in e for e in env["errors"]))

    def test_opaque_sections_are_ignored(self):
        env = parse_envelope("goal: |\n  some free text\n  more text\nacceptance: |\n  ok\n")
        self.assertEqual(env["errors"], [])


class ScopeTests(unittest.TestCase):
    def test_path_in_scope_dir_glob(self):
        self.assertTrue(path_in_scope("src/firmware/main.cpp", ["src/**"]))
        self.assertTrue(path_in_scope("src", ["src/**"]))
        self.assertFalse(path_in_scope("tools/x.py", ["src/**"]))

    def test_path_in_scope_exact(self):
        self.assertTrue(path_in_scope("AGENTS.md", ["AGENTS.md"]))
        self.assertFalse(path_in_scope("docs/HANDOFF.md", ["AGENTS.md"]))

    def test_scope_violations_forbidden(self):
        env = parse_envelope(FULL_ENVELOPE)
        files = ["src/a.py", "gates/run_gates.py"]
        violations = scope_violations(files, env)
        self.assertIn("gates/run_gates.py: matches forbidden path", violations)

    def test_scope_violations_whitelist(self):
        env = parse_envelope(FULL_ENVELOPE)
        violations = scope_violations(["notes/x.md", "src/a.py"], env)
        self.assertTrue(any("outside allowed paths" in v for v in violations))
        self.assertFalse(any("outside allowed paths" in v for v in scope_violations(["src/a.py"], env)))


class DependencyTests(unittest.TestCase):
    def test_merged(self):
        ok, _ = dependency_satisfied("merged", {"state": "MERGED", "mergedAt": "2026-09-01T00:00:00Z"})
        self.assertTrue(ok)
        ok, detail = dependency_satisfied("merged", {"state": "OPEN", "mergedAt": None})
        self.assertFalse(ok)
        self.assertIn("OPEN", detail)

    def test_closed_and_open(self):
        self.assertTrue(dependency_satisfied("closed", {"state": "CLOSED"})[0])
        self.assertFalse(dependency_satisfied("closed", {"state": "OPEN"})[0])
        self.assertTrue(dependency_satisfied("open", {"state": "OPEN"})[0])

    def test_unsupported_state(self):
        ok, detail = dependency_satisfied("shipped", {"state": "OPEN"})
        self.assertFalse(ok)
        self.assertIn("unsupported", detail)

    def test_ref_number(self):
        self.assertEqual(ref_number("GH-9"), 9)
        self.assertEqual(ref_number("#42"), 42)
        self.assertEqual(ref_number("issues/7"), 7)
        self.assertIsNone(ref_number("GH-abc"))


EXCEPTION_ENVELOPE = """task: GH-1
base:
  branch: master
  sha: abc123
exceptions:
  allow_dirty:
    permitted: true
    reason: existing unaccepted work-in-progress
    authority: task-envelope
  allow_drift:
    granted_by: Yenefa
    decision_ref: GH-20#comment-1
"""

MALFORMED_EXCEPTION_ENVELOPE = """task: GH-1
base:
  branch: master
  sha: abc123
exceptions:
  allow_dirty:
    reason: no authority
"""


class ExceptionTests(unittest.TestCase):
    def test_parse_exceptions_both_forms(self):
        env = parse_envelope(EXCEPTION_ENVELOPE)
        self.assertEqual(env["errors"], [])
        self.assertEqual(env["exceptions"]["allow_dirty"]["permitted"], True)
        self.assertEqual(env["exceptions"]["allow_dirty"]["authority"], "task-envelope")
        self.assertEqual(env["exceptions"]["allow_drift"]["granted_by"], "Yenefa")
        self.assertEqual(env["exceptions"]["allow_drift"]["decision_ref"], "GH-20#comment-1")

    def test_malformed_exception_is_error(self):
        env = parse_envelope(MALFORMED_EXCEPTION_ENVELOPE)
        self.assertTrue(any("malformed" in e for e in env["errors"]))

    def test_unknown_flag_is_error(self):
        env = parse_envelope("exceptions:\n  allow_force:\n    granted_by: X\n    decision_ref: y\n")
        self.assertTrue(any("unknown exception flag" in e for e in env["errors"]))

    def test_check_flag_exception(self):
        from tools.admit import check_flag_exception
        ok, detail = check_flag_exception("allow_dirty", {"allow_dirty": {"permitted": True, "authority": "task-envelope"}})
        self.assertTrue(ok)
        self.assertIn("task-envelope", detail)
        ok, detail = check_flag_exception("allow_dirty", {"allow_dirty": {"granted_by": "Yenefa", "decision_ref": "GH-20#comment-1"}})
        self.assertTrue(ok)
        self.assertIn("GH-20#comment-1", detail)
        ok, detail = check_flag_exception("allow_dirty", {})
        self.assertFalse(ok)
        self.assertIn("cannot self-authorize", detail)
        ok, detail = check_flag_exception("allow_dirty", {"allow_dirty": {"reason": "only"}})
        self.assertFalse(ok)
        self.assertIn("malformed", detail)


class BindingTests(unittest.TestCase):
    def test_envelope_binding_match(self):
        from tools.dev_gate import envelope_binding_mismatch
        ok, detail = envelope_binding_mismatch("a" * 64, "a" * 64)
        self.assertTrue(ok)
        self.assertIn("bound", detail)

    def test_envelope_binding_mismatch(self):
        from tools.dev_gate import envelope_binding_mismatch
        ok, detail = envelope_binding_mismatch("a" * 64, "b" * 64)
        self.assertFalse(ok)
        self.assertIn("TOCTOU", detail)
        self.assertIn("re-admit", detail)

    def test_envelope_binding_missing_hash(self):
        from tools.dev_gate import envelope_binding_mismatch
        ok, detail = envelope_binding_mismatch(None, "a" * 64)
        self.assertFalse(ok)
        self.assertIn("lacks a valid envelope_sha256", detail)


class AdversarialGateTests(unittest.TestCase):
    """Fail-closed safety boundary tests (source review round)."""

    def test_comment_only_when_preceded_by_whitespace(self):
        env = parse_envelope("task: GH-1\nbase:\n  sha: abc\n  branch: master\nexceptions:\n"
                             "  allow_drift:\n    granted_by: Yenefa\n    decision_ref: GH-20#comment-1\n")
        self.assertEqual(env["exceptions"]["allow_drift"]["decision_ref"], "GH-20#comment-1")
        env2 = parse_envelope("task: GH-1 # a real comment\n")
        self.assertEqual(env2["task"], "GH-1")

    def test_empty_allowed_paths_is_zero_write_permission(self):
        env = parse_envelope("task: GH-1\nallowed_paths: []\n")
        # allowed_paths: [] has no list items -> empty list
        violations = scope_violations(["src/a.py"], {"allowed_paths": [], "forbidden_paths": []})
        self.assertTrue(any("outside allowed paths" in v for v in violations))
        self.assertIn("zero write permission", violations[0])
        self.assertEqual(scope_violations([], {"allowed_paths": [], "forbidden_paths": []}), [])

    def test_git_cat_file_ok_is_returncode_based(self):
        from tools.admit import git_ok
        import subprocess
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.assertTrue(git_ok(Path.cwd(), "cat-file", "-e", head + "^{commit}"))
        self.assertFalse(git_ok(Path.cwd(), "cat-file", "-e", "0" * 40 + "^{commit}"))

    def test_git_checked_raises_on_failure(self):
        from tools.admit import git_checked, GitCommandError
        with self.assertRaises(GitCommandError):
            git_checked(Path.cwd(), "cat-file", "-e", "0" * 40 + "^{commit}")

    def test_binding_requires_receipt_when_envelope_given(self):
        from tools import dev_gate
        env = Path(tempfile.mkdtemp()) / "env.yaml"
        env.write_text("task: GH-1\n", encoding="utf-8")
        result, excluded = dev_gate.check_binding(Path.cwd(), str(env), None)
        self.assertEqual(result["status"], "fail")
        self.assertIn("binding required", result["detail"])
        self.assertEqual(excluded, [])

    def test_binding_rejects_blocked_receipt(self):
        from tools import dev_gate
        import hashlib
        tmp = Path(tempfile.mkdtemp())
        env = tmp / "env.yaml"
        env.write_text("task: GH-1\n", encoding="utf-8")
        receipt = tmp / "blocked.json"
        receipt.write_text(json.dumps({
            "schema_version": "admit.v1", "verdict": "BLOCKED", "exit_code": 1,
            "envelope_sha256": hashlib.sha256(env.read_bytes()).hexdigest(),
            "git": {"head_sha": "0" * 40},
        }), encoding="utf-8")
        result, _ = dev_gate.check_binding(Path.cwd(), str(env), str(receipt))
        self.assertEqual(result["status"], "fail")
        self.assertIn("not an ADMIT", result["detail"])

    def test_binding_rejects_head_moved(self):
        from tools import dev_gate
        import hashlib, subprocess
        tmp = Path(tempfile.mkdtemp())
        env = tmp / "env.yaml"
        env.write_text("task: GH-1\n", encoding="utf-8")
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        receipt = tmp / "moved.json"
        receipt.write_text(json.dumps({
            "schema_version": "admit.v1", "verdict": "ADMIT", "exit_code": 0,
            "envelope_sha256": hashlib.sha256(env.read_bytes()).hexdigest(),
            "git": {"head_sha": "0" * 40},
        }), encoding="utf-8")
        result, _ = dev_gate.check_binding(Path.cwd(), str(env), str(receipt))
        self.assertEqual(result["status"], "fail")
        self.assertIn("HEAD moved", result["detail"])
        # correct HEAD passes
        receipt.write_text(json.dumps({
            "schema_version": "admit.v1", "verdict": "ADMIT", "exit_code": 0,
            "envelope_sha256": hashlib.sha256(env.read_bytes()).hexdigest(),
            "git": {"head_sha": head},
        }), encoding="utf-8")
        result, _ = dev_gate.check_binding(Path.cwd(), str(env), str(receipt))
        self.assertEqual(result["status"], "pass")

    def test_aggregate_broken_wins_over_fail(self):
        from tools.dev_gate import aggregate_checks
        self.assertEqual(aggregate_checks({"a": {"status": "pass"}}), ("pass", 0))
        self.assertEqual(aggregate_checks({"a": {"status": "pass"}, "b": {"status": "fail"}}), ("fail", 1))
        self.assertEqual(aggregate_checks({"a": {"status": "fail"}, "b": {"status": "error"}}), ("broken", 2))

    def test_sandbox_uv_missing_is_error(self):
        from tools import dev_gate
        with mock.patch.object(dev_gate, "_uv_available", return_value=False):
            result, excluded = dev_gate.check_sandbox_tests(Path.cwd())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(excluded, [])

    def test_skip_deps_authorized_waives_blocked_dependency(self):
        from tools import admit
        import hashlib, subprocess
        head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
        tmp = Path(tempfile.mkdtemp())
        env = tmp / "env.yaml"
        env.write_text(
            f"task: GH-9\nbase:\n  branch: {branch}\n  sha: {head}\n"
            "dependencies:\n  - ref: GH-999999\n    required_state: merged\n"
            "exceptions:\n  allow_dirty:\n    granted_by: Yenefa\n    decision_ref: GH-20#c-1\n"
            "  skip_deps:\n    granted_by: Yenefa\n    decision_ref: GH-20#c-1\n",
            encoding="utf-8")
        with mock.patch.object(admit, "gh_json", return_value=None):
            receipt = admit.run_admit(root=Path.cwd(), envelope_path=str(env),
                                      allow_dirty=True, skip_deps=True)
        self.assertEqual(receipt["verdict"], "ADMIT")
        dep = [c for c in receipt["checks"] if c["id"] == "dependencies"][0]
        self.assertEqual(dep["status"], "waived")
        self.assertIn("skip_deps", receipt["exceptions_used"])


class DevGateDryRunTests(unittest.TestCase):
    def test_dry_run_receipt_shape(self):
        receipt = dev_gate.run_gate(dry_run=True)
        self.assertEqual(receipt["schema_version"], "dev-gate.v1")
        self.assertEqual(receipt["gate_version"], "1")
        self.assertEqual(receipt["status"], "pending")
        self.assertIn("syntax", receipt["checks"])
        self.assertIn("main_tests", receipt["checks"])
        self.assertIn("excluded_checks", receipt)
        self.assertIsInstance(receipt["baseline_sha"], str)


class SecretScanTests(unittest.TestCase):
    """Failure semantics of the secret scan target enumeration (fail-closed)."""

    def _init_repo(self, td):
        subprocess.run(["git", "init", "-q"], cwd=td, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=td, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=td, check=True)

    def test_ignored_files_excluded_tracked_and_untracked_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._init_repo(td)
            (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
            (root / "untracked.txt").write_text("clean\n", encoding="utf-8")
            (root / "ignored.txt").write_text("ghp_" + "X" * 36 + "\n", encoding="utf-8")
            (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt", ".gitignore"], cwd=td, check=True)
            targets = dev_gate._secret_scan_targets(root)
            names = {p.name for p in targets}
            self.assertIn("tracked.txt", names)
            self.assertIn("untracked.txt", names)
            self.assertNotIn("ignored.txt", names)
            res = dev_gate.check_secret_scan(root)
            self.assertEqual(res["status"], "pass")

    def test_tracked_enumeration_failure_fails_closed(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(
                dev_gate.subprocess, "run",
                return_value=SimpleNamespace(returncode=128, stdout=b"", stderr=b"boom"),
            ):
                res = dev_gate.check_secret_scan(Path(td))
        self.assertEqual(res["status"], "fail")
        self.assertIn("enumeration failed", res["detail"])

    def test_untracked_enumeration_failure_fails_closed(self):
        # First call (tracked) succeeds, second (untracked) fails -> partial
        # enumeration must still FAIL, never PASS on an incomplete target list.
        from types import SimpleNamespace
        ok = SimpleNamespace(returncode=0, stdout=b"a.txt\0", stderr=b"")
        bad = SimpleNamespace(returncode=128, stdout=b"", stderr=b"boom2")
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(dev_gate.subprocess, "run", side_effect=[ok, bad]):
                res = dev_gate.check_secret_scan(Path(td))
        self.assertEqual(res["status"], "fail")
        self.assertIn("enumeration failed", res["detail"])

    def test_git_missing_fails_closed(self):
        with mock.patch.object(
            dev_gate.subprocess, "run", side_effect=FileNotFoundError("git"),
        ):
            res = dev_gate.check_secret_scan(Path("."))
        self.assertEqual(res["status"], "fail")
        self.assertIn("cannot execute git", res["detail"])

    def test_read_error_fails_closed(self):
        # An enumerated target that cannot be read must FAIL, never silently
        # skip and then PASS with a partial scan.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._init_repo(td)
            (root / "secret.env").write_text("clean\n", encoding="utf-8")
            subprocess.run(["git", "add", "secret.env"], cwd=td, check=True)
            with mock.patch.object(
                dev_gate.Path, "read_text", side_effect=PermissionError("denied"),
            ):
                res = dev_gate.check_secret_scan(root)
        self.assertEqual(res["status"], "fail")
        self.assertIn("cannot read", res["detail"])

    def test_large_target_is_streamed_not_skipped(self):
        # Large targets must still be scanned (streamed line-by-line), never
        # silently skipped: a secret at the tail of a >1MB file must be caught.
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._init_repo(td)
            (root / "big.txt").write_text(
                "a" * (1_000_000) + "\n" + "ghp_" + "X" * 36 + "\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "big.txt"], cwd=td, check=True)
            res = dev_gate.check_secret_scan(root)
        self.assertEqual(res["status"], "fail")
        self.assertIn("big.txt", res["detail"])

    def test_large_target_without_secret_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._init_repo(td)
            (root / "big.txt").write_text(
                "a" * (1_000_000) + "\nclean\n", encoding="utf-8",
            )
            subprocess.run(["git", "add", "big.txt"], cwd=td, check=True)
            res = dev_gate.check_secret_scan(root)
        self.assertEqual(res["status"], "pass")


if __name__ == "__main__":
    unittest.main()
