"""End-to-end tests for cli.py run-arh with the REAL ports (GH-114).

ZERO NETWORK, asserted rather than assumed: the module-level transport the CLI
injects is replaced with a fake, so a test that reached the real one would fail
here rather than quietly open a socket.

What these tests establish, and what they do not: a repair round now COMPLETES
-- propose, policy, execute, verify -- against the domain's own registered
tools. Nothing here claims a real repair happened; the artifact is a projection
of the policy-approved design and the verifier says so in its own finding.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aedl_sandbox import adapters, cli
from aedl_sandbox.arh import model_adapter
from aedl_sandbox.arh.llm_repair_port import LLMRepairPort

TEST_MPN = adapters.TEST_ONLY_COMPONENT_MPN
TEST_EVIDENCE = adapters.TEST_ONLY_EVIDENCE_ID
TEST_ROLE = adapters.TEST_ONLY_COMPONENT_ROLE

#: The proposal a model would have to emit for this design. It names only fields
#: SUBJECT_SPECS declares -- output_kind is NOT among them, because the artifact
#: kind is the run's contract rather than something a proposal may vary.
PROPOSAL = {
    "diagnosis": "UNRESOLVED_PART: selected part is outside the allowlist",
    "design_action": "DESIGN_SELECT_COMPONENT",
    "design_subject": {"mpn": TEST_MPN, "role": TEST_ROLE, "evidence_ids": [TEST_EVIDENCE]},
    "evidence_ids": [TEST_EVIDENCE],
    "locator": {"mpn": TEST_MPN},
}


class _FakeTransport:
    """Serves the model response the round needs. Counts its calls."""

    def __init__(self, proposal: dict | None = None) -> None:
        self.proposal = proposal or PROPOSAL
        self.calls: list[str] = []

    def __call__(self, url, headers, body):
        self.calls.append(url)
        payload = {
            "choices": [
                {"message": {"role": "assistant", "content": json.dumps(self.proposal)}}
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "model": "fake",
        }
        return 200, json.dumps(payload).encode("utf-8")


class RunArhTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.run_root = self.base / "runs"
        self.allowlist_path = self.base / "allowlist.json"
        self.allowlist_path.write_text(
            json.dumps(
                {
                    "allowed_components": [{"mpn": TEST_MPN, "role": TEST_ROLE}],
                    "evidence_ids": [TEST_EVIDENCE],
                }
            ),
            encoding="utf-8",
        )
        self.subject_path = self.base / "subject.json"
        self.subject_path.write_text(
            json.dumps(
                {
                    "design_action": "DESIGN_SELECT_COMPONENT",
                    "design_subject": {
                        "mpn": TEST_MPN,
                        "role": TEST_ROLE,
                        "evidence_ids": [TEST_EVIDENCE],
                    },
                    "output_kind": "hir",
                }
            ),
            encoding="utf-8",
        )

    def _run(self, transport=None, *, subject_path=None, policy_source="test-only", extra=()):
        """Run cli.main(run-arh ...) with a fake transport. Returns (code, stdout)."""
        transport = transport or _FakeTransport()
        argv = [
            "run-arh",
            "--repo-root", str(self.base),
            "--run-root", str(self.run_root),
            "--run-id", "r1",
            "--base-url", "http://127.0.0.1:9/v1",
            "--model", "fake-model",
            "--allowlist", str(self.allowlist_path),
            "--subject", str(subject_path or self.subject_path),
            "--policy-source", policy_source,
            *extra,
        ]
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {"AEDL_ARH_API_KEY": "not-a-real-key"}), \
                mock.patch.object(
                    model_adapter, "urllib_default_transport", transport
                ):
            with contextlib.redirect_stdout(buffer):
                code = cli.main(argv)
        return code, buffer.getvalue()

    def _candidate_root(self):
        found = sorted((self.run_root / "run" / "r1" / "candidate").iterdir())
        self.assertEqual(len(found), 1)
        return found[0]


class RoundCompletionTests(RunArhTest):
    """The round completes. That is the GH-114 deliverable."""

    def test_run_arh_reaches_human_review_with_a_real_verify_pass(self) -> None:
        """The round completes, and it completes WITHOUT a model call.

        That is the operator's declared design being carried through: the frozen
        subject IS the design, so execute and verify have everything they need
        before any repair is requested. Asserting zero transport calls here is
        stronger than asserting one -- it is the zero-network claim, and it is
        only reachable because the real ports can run a design unaided.
        """
        transport = _FakeTransport()
        code, out = self._run(transport)
        payload = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "HUMAN_REVIEW_PENDING")
        self.assertEqual(payload["interrupt"]["verification_status"], "PASS")
        self.assertEqual(payload["state"]["phase"], "HUMAN_REVIEW")
        self.assertEqual(transport.calls, [], "the model was called for a valid design")
        self.assertIsNone(payload["state"]["repair_plan"])

    def test_the_artifact_on_disk_is_the_hir_the_executor_wrote(self) -> None:
        self._run()
        artifact = self._candidate_root() / "hir.json"
        self.assertTrue(artifact.is_file(), "the real executor wrote no artifact")
        parsed = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual(parsed["schema"], "aedl.sandbox.hir.v1")
        self.assertEqual(parsed["tool"], {"tool_id": "in-repo-hir", "version": "1.0.0"})
        self.assertEqual(parsed["plan"][0]["mpn"], TEST_MPN)
        # Canonical bytes: the file IS the canonical rendering of its content.
        self.assertEqual(
            artifact.read_bytes(),
            json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        )

    def test_both_evidence_receipts_were_recorded(self) -> None:
        _code, out = self._run()
        state = json.loads(out)["state"]
        kinds = sorted(r["event_type"] for r in state["evidence_receipts"])
        self.assertEqual(kinds, ["execution", "verification"])
        self.assertTrue(all(r["valid"] for r in state["evidence_receipts"]))

    def test_the_verifier_finding_publishes_the_scope_of_its_pass(self) -> None:
        """A PASS whose scope is implicit is how 'it verified' starts lying."""
        _code, out = self._run()
        state = json.loads(out)["state"]
        codes = [f["code"] for f in state["findings"]]
        self.assertIn("VERIFY_IN_REPO_HIR_SCOPE", codes)
        scope = next(f for f in state["findings"] if f["code"] == "VERIFY_IN_REPO_HIR_SCOPE")
        self.assertIn("does NOT establish", scope["message"])

    def test_the_candidate_is_never_promoted_without_a_human_decision(self) -> None:
        _code, out = self._run()
        state = json.loads(out)["state"]
        self.assertIsNone(state["promotion_result"])
        self.assertIsNone(state["human_decision"])
        self.assertEqual(state["terminal_reason"], None)
        self.assertEqual(state["approved_by"], "")


class RefusalTests(RunArhTest):
    """Refusals are named, early, and leave no half-built run behind."""

    def test_real_edd001_refuses_by_name_and_creates_no_run(self) -> None:
        """Against a real repository root this refuses on the tool registry.

        Against THIS temporary root the bundle manifest is absent, so the policy
        port fails closed first and the refusal names the missing document. Both
        are refusals with exit 2 and neither leaves a run behind; the real
        repository root is exercised separately below.
        """
        code, out = self._run(policy_source="real")
        payload = json.loads(out)
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "REFUSED")
        self.assertIn("refuses every evaluation", payload["reason"])
        self.assertIn("EVIDENCE_BUNDLE_INVALID", payload["reason"])
        # A refusal must not leave a run behind. It may leave the trust store's
        # bundle-validation receipt directory, which is created by validation
        # itself, so what is checked is that no RUN was started.
        self.assertFalse((self.run_root / "run").exists(), "a refused run left a run dir")

    def test_real_edd001_repository_refuses_because_it_registers_no_tool(self) -> None:
        """The honest EDD-001 outcome, against the actual repository.

        EDD-001's bundle manifest declares tool_coverage {compilers: [],
        verifiers: []}, so there is nothing to execute or verify with. This test
        is the reason the task can claim completion of a ROUND without claiming
        anything about real electronics.
        """
        repo_root = Path(__file__).resolve().parents[3]
        self.run_root = self.base / "real-runs"
        argv = [
            "run-arh", "--repo-root", str(repo_root),
            "--run-root", str(self.run_root), "--run-id", "r1",
            "--base-url", "http://127.0.0.1:9/v1", "--model", "m",
            "--allowlist", str(self.allowlist_path),
            "--subject", str(self.subject_path),
            "--policy-source", "real",
        ]
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {"AEDL_ARH_API_KEY": "not-a-real-key"}):
            with contextlib.redirect_stdout(buffer):
                code = cli.main(argv)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "REFUSED")
        # The tool registry is checked at assembly, so the refusal names the
        # first tool the in-repo pair needs; either name is the same fact.
        self.assertIn("is a refusal, never a fallback", payload["reason"])
        self.assertFalse((self.run_root / "run").exists())

    def test_missing_api_key_refuses_before_anything_is_created(self) -> None:
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.dict(os.environ, {"PATH": os.environ.get("PATH", "")}):
                with contextlib.redirect_stdout(buffer):
                    code = cli.main(
                        [
                            "run-arh", "--repo-root", str(self.base),
                            "--run-root", str(self.run_root), "--run-id", "r1",
                            "--base-url", "http://127.0.0.1:9/v1", "--model", "m",
                            "--allowlist", str(self.allowlist_path),
                            "--subject", str(self.subject_path),
                            "--policy-source", "test-only",
                        ]
                    )
        payload = json.loads(buffer.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "REFUSED")
        self.assertEqual(payload["env_var"], "AEDL_ARH_API_KEY")
        self.assertFalse(self.run_root.exists())

    def test_api_key_is_not_an_option_at_all(self) -> None:
        """Not discouraged -- absent. argv lands in process listings and history."""
        with self.assertRaises(SystemExit) as caught:
            with contextlib.redirect_stderr(io.StringIO()):
                cli.main(
                    [
                        "run-arh", "--repo-root", str(self.base),
                        "--run-root", str(self.run_root), "--run-id", "r1",
                        "--base-url", "http://x", "--model", "m",
                        "--api-key", "sk-must-not-be-accepted",
                        "--allowlist", str(self.allowlist_path),
                        "--subject", str(self.subject_path),
                    ]
                )
        self.assertEqual(caught.exception.code, 2)

    def test_envelope_with_an_unknown_key_refuses_before_creating_a_run(self) -> None:
        bad = self.base / "bad-subject.json"
        payload = json.loads(self.subject_path.read_text(encoding="utf-8"))
        payload["smuggled"] = {"anything": True}
        bad.write_text(json.dumps(payload), encoding="utf-8")
        code, out = self._run(subject_path=bad)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["code"], "ENVELOPE_UNEXPECTED_KEYS")
        self.assertFalse(self.run_root.exists())

    def test_envelope_without_output_kind_refuses_before_creating_a_run(self) -> None:
        bad = self.base / "no-kind.json"
        payload = json.loads(self.subject_path.read_text(encoding="utf-8"))
        del payload["output_kind"]
        bad.write_text(json.dumps(payload), encoding="utf-8")
        code, out = self._run(subject_path=bad)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["code"], "ENVELOPE_MISSING_OUTPUT_KIND")
        self.assertFalse(self.run_root.exists())

    def test_policy_source_defaults_to_the_real_domain(self) -> None:
        """A synthetic policy must never be in play without a flag saying so."""
        captured = {}

        def capture(policy_source, repo_root, run_root):
            captured["policy_source"] = policy_source
            raise SystemExit(0)

        with mock.patch.object(cli, "_domain_for", capture):
            with mock.patch.dict(os.environ, {"AEDL_ARH_API_KEY": "k"}):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit):
                        cli.main(
                            [
                                "run-arh", "--repo-root", str(self.base),
                                "--run-root", str(self.run_root), "--run-id", "r1",
                                "--base-url", "http://x", "--model", "m",
                                "--allowlist", str(self.allowlist_path),
                                "--subject", str(self.subject_path),
                            ]
                        )
        self.assertEqual(captured["policy_source"], "real")


class MutationGuardTests(RunArhTest):
    """A wiring test that cannot fail is worse than none.

    If the CLI's tool-port assembly were replaced by the TEST_ONLY doubles -- the
    exact substitution GH-114 exists to prevent -- these tests must die, and they
    must die on CONTENT rather than on a type check.
    """

    def test_substituting_the_test_only_doubles_is_killed(self) -> None:
        """The substitution is killed TWICE: by the fixture double's artifact and
        by the repair agent refusing the double's findings.

        The double verifier reports VERIFY_TEST_ONLY_ATTEMPT_INCOMPLETE, and the
        agent's own validation refuses a diagnosis that cites no finding code --
        so once the doubles are wired in, the round stops being a round. A test
        that only checked the port types would have passed here.
        """
        calls = {"execute": 0, "verify": 0}
        real_executor = adapters._TestOnlyExecutor()
        real_verifier = adapters._TestOnlyVerifier()

        def counting_executor():
            calls["execute"] += 1
            return real_executor

        def counting_verifier():
            calls["verify"] += 1
            return real_verifier

        from aedl_sandbox.arh.budget import BudgetExceeded

        with mock.patch.object(adapters, "_TestOnlyExecutor", counting_executor), \
                mock.patch.object(adapters, "_TestOnlyVerifier", counting_verifier), \
                mock.patch.object(
                    adapters,
                    "build_in_repo_tool_ports",
                    lambda *a, **k: (counting_executor(), counting_verifier()),
                ):
            with self.assertRaises(BudgetExceeded) as caught:
                self._run()
        # The round stops being a round: the double verifier reports its own
        # findings, the agent refuses a diagnosis that cites no finding code, and
        # the budget trips instead of a PASS being manufactured.
        self.assertIn("consecutive invalid proposals", str(caught.exception))
        self.assertEqual(calls["execute"], 1)
        self.assertEqual(calls["verify"], 1)
        # CONTENT, not type: the double wrote ITS OWN artifact under its own
        # name, and the real HIR contract never appeared. A test that only
        # compared port classes would have passed on a wrapper that forwarded to
        # the doubles, which is exactly the substitution being guarded.
        candidate = self._candidate_root()
        self.assertTrue((candidate / "artifact.json").is_file())
        self.assertFalse((candidate / "hir.json").exists())
        double_payload = json.loads((candidate / "artifact.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(double_payload), ["fixture_attempt", "test_only"])
        self.assertIs(double_payload["test_only"], True)

    def test_the_assembled_repair_port_is_the_agent_not_the_double(self) -> None:
        """Same substitution, observed from the port's own type and identity."""
        captured = {}

        def capture(*args, **kwargs):
            captured["executor"] = kwargs.get("executor")
            captured["verifier"] = kwargs.get("verifier")
            captured["policy"] = kwargs.get("policy")
            raise SystemExit(0)

        with mock.patch.object(adapters, "build_arh_orchestrator", capture):
            with self.assertRaises(SystemExit):
                self._run()
        self.assertNotIsInstance(captured["executor"], adapters._TestOnlyExecutor)
        self.assertNotIsInstance(captured["verifier"], adapters._TestOnlyVerifier)
        from aedl_sandbox.toolports import ToolExecutor, ToolVerifier

        self.assertIsInstance(captured["executor"], ToolExecutor)
        self.assertIsInstance(captured["verifier"], ToolVerifier)
        # The repair port is constructed inside the assembly; assert separately
        # that the real assembly still wires the agent (test_arh_wiring.py).
        self.assertIsNotNone(captured["policy"])
