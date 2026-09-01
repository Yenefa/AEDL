"""CLI smoke tests for the sandbox runtime (Agent H, Wave 2 wiring)."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aedl_sandbox import cli

REPO_ROOT = Path(__file__).resolve().parents[3]


class CliTests(unittest.TestCase):
    def _run_cli(self, argv: list[str]) -> tuple[int, dict]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli.main(argv)
        return code, json.loads(buffer.getvalue())

    def test_preflight_reports_real_edd001_blocked_nonzero(self):
        code, payload = self._run_cli(
            ["preflight", "--repo-root", str(REPO_ROOT), "--domain", "EDD-001"]
        )
        self.assertEqual(code, 1)
        self.assertEqual(payload["outcome"], "BLOCKED")
        self.assertEqual(payload["reason_code"], "EVIDENCE_COMPONENT_SOURCE_MISSING")
        self.assertEqual(payload["domain"], "EDD-001")
        codes = {finding["code"] for finding in payload["findings"]}
        self.assertIn("EVIDENCE_COMPONENT_SOURCE_MISSING", codes)
        self.assertIn("EVIDENCE_REQUIRED_CONTRACT_MISSING", codes)
        self.assertIn("POLICY_COMPILER_NOT_REGISTERED", codes)
        self.assertIn("POLICY_VERIFIER_COVERAGE_MISSING", codes)

    def test_run_fixture_pauses_at_human_review_then_resume_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            code_first, first = self._run_cli(
                ["run-fixture", "--scenario", "repair_then_pass", "--run-root", str(run_root)]
            )
            self.assertEqual(code_first, 0)
            self.assertEqual(first["status"], "HUMAN_REVIEW_PENDING")
            self.assertEqual(first["state"]["repair_count"], 1)
            self.assertEqual(first["interrupt"]["verification_status"], "PASS")

            code_second, second = self._run_cli(
                [
                    "resume",
                    "--run-root",
                    str(run_root),
                    "--scenario",
                    "repair_then_pass",
                    "--decision",
                    "REJECTED",
                    "--approved-by",
                    "cli-reviewer@example",
                ]
            )
            self.assertEqual(code_second, 0)
            self.assertEqual(second["state"]["terminal_reason"], "APPROVAL_HUMAN_REJECTED")

    def test_run_fixture_then_resume_approved_promotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            code_first, first = self._run_cli(
                ["run-fixture", "--scenario", "repair_then_pass", "--run-root", str(run_root)]
            )
            self.assertEqual(code_first, 0)
            self.assertEqual(first["status"], "HUMAN_REVIEW_PENDING")

            code_second, second = self._run_cli(
                [
                    "resume",
                    "--run-root",
                    str(run_root),
                    "--scenario",
                    "repair_then_pass",
                    "--decision",
                    "APPROVED",
                    "--approved-by",
                    "cli-reviewer@example",
                ]
            )
            self.assertEqual(code_second, 0)
            self.assertEqual(second["state"]["terminal_reason"], "STATE_PROMOTED")
            self.assertEqual(second["state"]["promotion_result"]["outcome"], "ALLOW")
            self.assertEqual(
                second["state"]["promotion_result"]["reason_code"], "PROMOTION_ALLOWED"
            )

    def test_resume_requires_explicit_decision_value(self):
        with self.assertRaises(SystemExit):
            cli.main(
                [
                    "resume",
                    "--run-root",
                    "x",
                    "--decision",
                    "MAYBE",
                    "--approved-by",
                    "cli-reviewer@example",
                ]
            )

    def test_resume_without_checkpoint_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, payload = self._run_cli(
                [
                    "resume",
                    "--run-root",
                    str(Path(tmp) / "missing"),
                    "--scenario",
                    "repair_then_pass",
                    "--decision",
                    "APPROVED",
                    "--approved-by",
                    "cli-reviewer@example",
                ]
            )
            self.assertEqual(code, 2)
            self.assertEqual(payload["status"], "ERROR")

    def test_resume_requires_named_approver(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            code_first, _first = self._run_cli(
                ["run-fixture", "--scenario", "repair_then_pass", "--run-root", str(run_root)]
            )
            self.assertEqual(code_first, 0)
            # argparse rejects the resume before any checkpoint is touched when
            # the deciding human is not named
            with self.assertRaises(SystemExit):
                cli.main(
                    [
                        "resume",
                        "--run-root",
                        str(run_root),
                        "--scenario",
                        "repair_then_pass",
                        "--decision",
                        "APPROVED",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
