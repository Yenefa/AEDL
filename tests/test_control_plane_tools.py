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


class BundleCheckTests(unittest.TestCase):
    def test_bundle_decision_ci_excluded(self):
        from tools.dev_gate import _bundle_decision
        status, reason = _bundle_decision("feat/x", True, True, True, "h", "feat_x")
        self.assertIsNone(status)
        self.assertIn("CI", reason)

    def test_bundle_decision_stable_branch_excluded(self):
        from tools.dev_gate import _bundle_decision
        status, reason = _bundle_decision("master", False, True, True, "h", "master")
        self.assertIsNone(status)
        self.assertIn("stable", reason)

    def test_bundle_decision_missing_generator_excluded(self):
        from tools.dev_gate import _bundle_decision
        status, reason = _bundle_decision("feat/x", False, False, True, "h", "feat_x")
        self.assertIsNone(status)
        self.assertIn("generator", reason)

    def test_bundle_decision_stale_fails(self):
        from tools.dev_gate import _bundle_decision
        status, reason = _bundle_decision("feat/x", False, True, False, "h", "feat_x")
        self.assertEqual(status, "fail")

    def test_bundle_decision_current_passes(self):
        from tools.dev_gate import _bundle_decision
        status, reason = _bundle_decision("feat/x", False, True, True, "h", "feat_x")
        self.assertEqual(status, "pass")

    def test_run_name_from_branch(self):
        from tools.dev_gate import run_name_from_branch
        self.assertEqual(run_name_from_branch("feat/control-plane"), "feat_control-plane")


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


class CodeownersMatchTests(unittest.TestCase):
    """Review P1 (2026-09-02): Path.match silently returned False for every
    CODEOWNERS directory rule, so make_review_bundle reported shared=[] for
    real SHARED hits. codeowners_match implements the actual semantics."""

    def setUp(self) -> None:
        from tools.make_review_bundle import codeowners_match
        self.match = codeowners_match

    def test_directory_rule_hits_nested_files(self) -> None:
        self.assertTrue(self.match("gates/contracts/edd001_power_contract_v1.json", "/gates/contracts/"))
        self.assertTrue(self.match("docs/evidence/EVIDENCE_INDEX.md", "/docs/evidence/"))
        self.assertTrue(self.match("gates/contracts/sub/dir/deep.md", "/gates/contracts/"))

    def test_directory_rule_matches_the_directory_itself(self) -> None:
        self.assertTrue(self.match("gates/contracts", "/gates/contracts/"))

    def test_directory_rule_negative_prefix_trick(self) -> None:
        # "gates/contracts-extra" must NOT match "/gates/contracts/"
        self.assertFalse(self.match("gates/contracts-extra/file.md", "/gates/contracts/"))
        self.assertFalse(self.match("docs/evidence-backup/x.md", "/docs/evidence/"))
        self.assertFalse(self.match("sandbox_runtime/contracts/x.json", "/gates/contracts/"))

    def test_root_anchored_file_rule(self) -> None:
        self.assertTrue(self.match("gates/lessons_registry_v1.json", "/gates/lessons_registry_v1.json"))
        self.assertFalse(self.match("docs/gates/lessons_registry_v1.json", "/gates/lessons_registry_v1.json"))

    def test_basename_rule_matches_any_directory(self) -> None:
        self.assertTrue(self.match("a/b/CODEOWNERS", "CODEOWNERS"))
        self.assertTrue(self.match("CODEOWNERS", "CODEOWNERS"))
        self.assertFalse(self.match("a/b/CODEOWNERS2", "CODEOWNERS"))

    def test_regression_old_matcher_failed_on_directory_rules(self) -> None:
        """The exact real-world pair that used to be reported as non-SHARED."""
        from pathlib import Path
        self.assertFalse(Path("gates/contracts/edd001_power_contract_v1.json").match("/gates/contracts/"))  # old bug
        self.assertTrue(self.match("gates/contracts/edd001_power_contract_v1.json", "/gates/contracts/"))  # fixed

    def test_real_repo_shared_patterns_against_w4a_change_set(self) -> None:
        """End-to-end against the repo's actual CODEOWNERS: the W4A change set
        must yield exactly the two adjudicated SHARED files (review-verified
        ground truth), and nothing else."""
        from tools.make_review_bundle import shared_patterns, codeowners_match
        root = Path(__file__).resolve().parents[1]
        patterns = shared_patterns(root)
        self.assertIn("/gates/contracts/", patterns)
        changed = [
            "docs/COLLABORATION.md",
            "docs/WAVE4_TASKS_20260901.md",
            "docs/compliance/AI_USAGE_LOG.md",
            "docs/compliance/THIRD_PARTY_RESOURCES.md",
            "docs/evidence/EVIDENCE_INDEX.md",
            "gates/contracts/edd001_power_contract_v1.json",
            "src/hardware/edd001-board/evidence/contracts/edd001_power_contract_v1.json",
            "src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json",
            "tasks/GH-2.yaml",
        ]
        shared = sorted(p for p in changed if any(codeowners_match(p, pat) for pat in patterns))
        self.assertEqual(
            shared,
            [
                "docs/evidence/EVIDENCE_INDEX.md",
                "gates/contracts/edd001_power_contract_v1.json",
            ],
        )


class BundleReceiptDiscoveryTests(unittest.TestCase):
    """Review iteration 4 (2026-09-02): receipts must be discovered INSIDE the
    bundle directory and the three views — review.md evidence section,
    manifest.receipts summaries, manifest.files inventory — must agree. The
    old parent-directory scan reported "no receipts found" while the bundle
    dir held current receipts, and summarized stale receipts from other runs."""

    @staticmethod
    def _init_repo(root: Path) -> None:
        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "T")
        (root / "file.txt").write_text("x", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "init")

    def test_end_to_end_bundle_discovers_and_inventories_receipts(self) -> None:
        from tools.make_review_bundle import build_bundle

        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "repo"
            out = Path(td) / "review-bundles" / "run"
            root.mkdir()
            out.mkdir(parents=True)
            self._init_repo(root)
            (out / "admit-receipt.json").write_text(json.dumps({
                "schema_version": "admit.v1", "verdict": "ADMIT", "exit_code": 0,
                "envelope_sha256": "a" * 64,
            }), encoding="utf-8")
            (out / "gate-receipt.json").write_text(json.dumps({
                "schema_version": "dev-gate.v1", "status": "pass", "exit_code": 0,
                "envelope_sha256": "a" * 64,
            }), encoding="utf-8")

            manifest = build_bundle(root, "run", "HEAD", out, None)

            self.assertIn("admit-receipt.json", manifest["files"])
            self.assertIn("gate-receipt.json", manifest["files"])
            self.assertTrue(manifest["receipts"]["admit-receipt.json"].startswith("ADMIT"))
            self.assertTrue(manifest["receipts"]["gate-receipt.json"].startswith("pass"))
            review = (out / "run-review.md").read_text(encoding="utf-8")
            self.assertIn("admit-receipt.json: ADMIT", review)
            self.assertIn("gate-receipt.json: pass", review)

    def test_receipt_scan_skips_underscore_and_non_receipt_json(self) -> None:
        from tools.make_review_bundle import receipt_summaries

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / "_scratch-receipt.json").write_text("{}", encoding="utf-8")
            (out / "other.json").write_text("{}", encoding="utf-8")
            (out / "manifest.json").write_text("{}", encoding="utf-8")
            (out / "admit-receipt.json").write_text(json.dumps({"verdict": "ADMIT"}), encoding="utf-8")
            summaries = receipt_summaries(out)
            self.assertEqual([s["file"] for s in summaries], ["admit-receipt.json"])

    def test_receipt_scan_dedupes_files_matching_both_globs(self) -> None:
        from tools.make_review_bundle import receipt_summaries

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            # "admit-receipt.json" matches both "*admit*.json" and "*receipt*.json"
            (out / "admit-receipt.json").write_text(json.dumps({"verdict": "ADMIT"}), encoding="utf-8")
            summaries = receipt_summaries(out)
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0]["file"], "admit-receipt.json")


class DevGateInterpreterTests(unittest.TestCase):
    """Review finding F6: `--interpreter` crashed before any check ran.

    Reproduced before fixing:

        py -3 -m tools.dev_gate --interpreter python
        -> status broken, exit_code 2,
           "TypeError: can only concatenate str (not \"list\") to str"

    The default path never showed it, because `resolve_python()` happens to return
    a list.

    NOTE on test shape, because getting this wrong is how the bug survived a green
    suite: `run_gate` short-circuits `--dry-run` BEFORE the interpreter path, so a
    dry-run test never reaches the line that broke. The first version of this class
    had two dry-run subprocess tests and would have passed with the bug still
    present. So the crash site itself is exercised in-process, and exactly one real
    end-to-end run covers argparse.
    """

    def _repo(self):
        from pathlib import Path as _Path
        return _Path(dev_gate.__file__).resolve().parents[1]

    def test_the_crash_site_composes_without_a_type_error(self):
        """`py + [...]` in check_syntax is where it broke; go there directly."""
        import sys
        argv = dev_gate.interpreter_argv(sys.executable)
        self.assertIsNone(dev_gate.probe_interpreter(argv))
        result = dev_gate.check_syntax(argv, self._repo())
        self.assertIn("status", result)
        self.assertNotEqual(result.get("status"), "broken",
                            "check_syntax reported broken: %s" % result)

    def test_the_option_works_end_to_end_through_argparse(self):
        """The only thing that proves the public option survives argparse.

        OPT-IN, and not because it is slow. It spawns a full
        `python -m tools.dev_gate`, and that gate runs `main_tests` -- the suite
        this test lives in. So the test invoked the gate, which invoked the test,
        which invoked the gate: unbounded, and it was killed at 600s.

        That is the same shape of defect the independent review raised as F4 and
        F7 -- a check that looks like it verifies something and is structurally
        unsound. Not wrong in intent, wrong in placement.

        So it runs only with AEDL_DEV_GATE_CLI=1, the pattern this repository
        already uses for `AEDL_PR1_NATIVE=1`, and it SKIPS with the reason rather
        than passing vacuously. The crash-site coverage stays unconditional.
        """
        import json as _json
        import os
        import subprocess
        import sys
        if os.environ.get("AEDL_DEV_GATE_CLI") != "1":
            self.skipTest(
                "opt-in: this spawns a full dev_gate, which runs main_tests, which "
                "is this suite -- nesting the gate inside the gate it runs is "
                "unbounded. The crash site itself is covered unconditionally by "
                "test_the_crash_site_composes_without_a_type_error.")
        result = subprocess.run(
            [sys.executable, "-m", "tools.dev_gate", "--interpreter",
             sys.executable],
            cwd=str(self._repo()), capture_output=True, text=True, timeout=1800)
        combined = result.stdout + result.stderr
        self.assertNotIn("TypeError", combined,
                         "the shape mismatch is back:\n%s" % combined[-600:])
        self.assertNotEqual(result.returncode, 2,
                            "the gate is BROKEN with --interpreter:\n%s"
                            % combined[-600:])
        receipt = _json.loads(result.stdout[result.stdout.index("{"):])
        self.assertEqual(receipt["schema_version"], "dev-gate.v1")
        # the checks really ran, rather than being skipped as a dry-run would
        self.assertNotIn("dry-run", receipt["checks"].get("syntax", {}).get(
            "detail", "") or "")
        self.assertTrue(receipt["checks"], "no checks were recorded")

    def test_a_path_containing_a_space_is_accepted(self):
        """The review asked for this case by name.

        A naive `value.split()` -- which is how `AEDL_PYTHON` is handled, correctly,
        because that option IS an argv prefix -- would turn
        `C:\\Program Files\\...\\python.exe` into a nonexistent executable plus
        two stray arguments. `--interpreter` is a single executable path, so it is
        not split.
        """
        spaced = r"C:\\Program Files\\Python311\\python.exe"
        self.assertEqual(dev_gate.interpreter_argv(spaced), [spaced],
                         "a path with a space was split")
        self.assertIn(" ", dev_gate.interpreter_argv(spaced)[0])

    def test_the_normalisation_is_idempotent(self):
        """Found by probing the fix, not by a failing test.

        The first version did `str(interpreter).strip()` unconditionally, so
        passing an ALREADY-normalised list produced `["['python']"]` -- a silent
        garbage interpreter rather than an error. A function described as the single
        normalisation point has to be safe to call twice.
        """
        once = dev_gate.interpreter_argv("python")
        self.assertEqual(once, ["python"])
        self.assertEqual(dev_gate.interpreter_argv(once), once)
        real = dev_gate.resolve_python()
        self.assertEqual(dev_gate.interpreter_argv(real), real)

    def test_it_never_returns_a_bare_string(self):
        """The shape is the whole bug, so it is asserted directly."""
        for value in (None, "python", ["python"], ["py", "-3"]):
            self.assertIsInstance(dev_gate.interpreter_argv(value), list,
                                  "%r normalised to the wrong shape" % (value,))

    def test_a_blank_value_is_refused_rather_than_defaulting(self):
        """Silently falling back would hide the operator's mistake."""
        for blank in ("", "   "):
            with self.assertRaises(ValueError):
                dev_gate.interpreter_argv(blank)
        with self.assertRaises(ValueError):
            dev_gate.interpreter_argv([])

    def test_a_bad_path_is_refused_by_name(self):
        """It used to surface as a TypeError from inside a check, naming neither
        the option nor the value."""
        reason = dev_gate.probe_interpreter(
            [r"Z:\\definitely\\not\\a\\python.exe"])
        self.assertIsNotNone(reason)
        self.assertIn("Z:", reason, "the reason must name the value it refused")
        self.assertIn("does not exist", reason)

    def test_a_real_interpreter_passes_the_preflight(self):
        import sys
        self.assertIsNone(dev_gate.probe_interpreter([sys.executable]))

    def test_a_non_interpreter_is_refused_not_assumed(self):
        """Something that exists and exits non-zero is still not a Python."""
        reason = dev_gate.probe_interpreter(["cmd", "/c", "exit 3"])
        self.assertIsNotNone(reason)
        self.assertIn("exit code 3", reason)

    def test_the_boundary_asserts_the_shape_it_needs(self):
        """The durable half of the fix.

        `interpreter_argv` is the normalisation point, but a future caller can
        still hand a check a string, and the failure would again be a TypeError
        from a `+`. A named refusal at the boundary costs one line and cannot be
        misread.
        """
        with self.assertRaises(TypeError) as caught:
            dev_gate.check_syntax("python", self._repo())
        self.assertIn("interpreter_argv", str(caught.exception))

    def test_a_blank_interpreter_is_refused_by_run_gate_itself(self):
        """The refusal has to survive the call, not just the helper."""
        receipt = dev_gate.run_gate(root=str(self._repo()), interpreter="   ")
        self.assertEqual(receipt["status"], "broken")
        self.assertEqual(receipt["exit_code"], 2)
        self.assertIn("empty", receipt["detail"])

    def test_the_gate_refuses_a_nonexistent_interpreter_by_name(self):
        """The gap my own mutation run found.

        `probe_interpreter` was tested DIRECTLY, so the suite passed whether or
        not `run_gate` ever called it -- mutation M3 removed the call and every
        test still passed. The behaviour that matters is the GATE refusing, with
        a reason naming the value, instead of a TypeError from inside a check
        after the run has started.
        """
        receipt = dev_gate.run_gate(
            root=str(self._repo()),
            interpreter="Z:\\definitely\\not\\a\\python.exe")
        self.assertEqual(receipt["status"], "broken")
        self.assertEqual(receipt["exit_code"], 2)
        self.assertIn("Z:", receipt["detail"])
        # and it refused BEFORE running anything, which is the point of a preflight
        self.assertNotIn("checks", receipt,
                         "the gate started running checks with a bad interpreter")
