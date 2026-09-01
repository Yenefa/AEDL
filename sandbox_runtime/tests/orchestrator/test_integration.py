"""Mandatory final integration scenarios INT-01..INT-14 (Agent H, Wave 2).

Real Agent M policy engine and Agent L trust store are wired through
adapters.py; executor/verifier/repair remain deterministic TEST_ONLY doubles.
The real-EDD scenario runs under sandbox_runtime/.runs (gitignored, inside the
repository so Agent M's containment check holds); synthetic scenarios run
under system temporary directories. Nothing is written into real EDD evidence
paths. The TEST_ONLY fixtures prove orchestration mechanics only — they are
not evidence that EDD-001 electronics are correct.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

try:
    from langgraph.checkpoint.memory import InMemorySaver
except ImportError:  # pragma: no cover
    from langgraph.checkpoint.memory import MemorySaver as InMemorySaver  # type: ignore
from langgraph.checkpoint.sqlite import SqliteSaver

from aedl_sandbox import adapters
from aedl_sandbox.orchestrator import APPROVED, REJECTED, SandboxOrchestrator
from aedl_sandbox.protocol import EvidenceStatus, Finding, VerificationResult, VerificationStatus
from aedl_sandbox.workspace import CandidateWorkspace

try:
    from .fakes import (
        CountingExecutor,
        IncrementRepair,
        ScriptedVerifier,
        StrictTrust,
        pass_result,
    )
except ImportError:  # focused discovery: tests/orchestrator is the top level
    from fakes import (  # type: ignore
        CountingExecutor,
        IncrementRepair,
        ScriptedVerifier,
        StrictTrust,
        pass_result,
    )

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_MANIFEST = REPO_ROOT / "src/hardware/edd001-board/evidence/sandbox_bundle_manifest_v1.json"
RUNS_ROOT = REPO_ROOT / "sandbox_runtime" / ".runs"


class _StuckVerifier:
    """TEST_ONLY: always FAIL with the same finding (stall detection)."""

    def __init__(self) -> None:
        self.calls = 0

    def verify(self, run_id, candidate_id, candidate_root) -> VerificationResult:
        self.calls += 1
        return VerificationResult(
            status=VerificationStatus.FAIL,
            candidate_id=candidate_id,
            findings=(
                Finding(
                    code="VERIFY_TEST_ONLY_STUCK",
                    message="identical scripted failure",
                    source="test-only-verifier",
                ),
            ),
        )


class _ChangingVerifier:
    """TEST_ONLY: FAIL with a different finding on every call (limit test)."""

    def __init__(self) -> None:
        self.calls = 0

    def verify(self, run_id, candidate_id, candidate_root) -> VerificationResult:
        self.calls += 1
        return VerificationResult(
            status=VerificationStatus.FAIL,
            candidate_id=candidate_id,
            findings=(
                Finding(
                    code=f"VERIFY_TEST_ONLY_ROUND_{self.calls}",
                    message=f"changing scripted failure {self.calls}",
                    source="test-only-verifier",
                ),
            ),
        )


class Int01RealEdd001Tests(unittest.TestCase):
    def test_int_01_real_edd001_preflight_blocked_zero_executor_calls(self):
        run_root = RUNS_ROOT / "int-01"
        self.addCleanup(shutil.rmtree, run_root, ignore_errors=True)
        executor = CountingExecutor()
        orchestrator = SandboxOrchestrator(
            policy=adapters.build_real_edd001_policy_port(REPO_ROOT),
            executor=executor,
            verifier=ScriptedVerifier([pass_result()]),
            repair=IncrementRepair(),
            trust=StrictTrust(),
            workspace=CandidateWorkspace(run_root),
            run_id="int-01",
            domain_id="EDD-001",
            bundle_hash="int-01-real-edd001",
            subject=adapters.test_only_design_subject(1),
            checkpointer=InMemorySaver(),
        )
        state = orchestrator.run()
        self.assertEqual(state["phase"], "TERMINAL")
        self.assertEqual(state["policy_result"]["outcome"], "BLOCKED")
        self.assertEqual(state["terminal_reason"], "EVIDENCE_COMPONENT_SOURCE_MISSING")
        self.assertEqual(len(executor.calls), 0)
        self.assertFalse((run_root / "run").exists())
        findings = state["policy_result"]["findings"]
        self.assertEqual(len(findings), 7)
        self.assertEqual(
            {finding["code"] for finding in findings},
            {
                "EVIDENCE_COMPONENT_SOURCE_MISSING",
                "EVIDENCE_REQUIRED_CONTRACT_MISSING",
                "POLICY_COMPILER_NOT_REGISTERED",
                "POLICY_VERIFIER_COVERAGE_MISSING",
            },
        )

    def test_int_01_real_bundle_manifest_is_honestly_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            trust = adapters.build_trust_port(REPO_ROOT, Path(tmp) / "receipts")
            status, _findings = trust.validate_bundle(REAL_MANIFEST)
        self.assertEqual(status, EvidenceStatus.PARTIAL)
        manifest = json.loads(REAL_MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["missing_requirements"]), 5)
        self.assertEqual(manifest["tool_coverage"], {"compilers": [], "verifiers": []})


class Int02To06And13PolicyGateTests(unittest.TestCase):
    """Violating design actions terminate at the policy gate: preflight allows
    the complete TEST_ONLY bundle, the execute gate stops the run, and the
    executor is never called."""

    def _run(self, action: str, subject: dict) -> dict:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ws_root = Path(self._tmp.name)
        self.executor = CountingExecutor()
        orchestrator = SandboxOrchestrator(
            policy=adapters.build_test_only_policy_port(self.ws_root),
            executor=self.executor,
            verifier=ScriptedVerifier([pass_result()]),
            repair=IncrementRepair(),
            trust=StrictTrust(),
            workspace=CandidateWorkspace(self.ws_root),
            run_id="int-policy-gate",
            domain_id="EDD-001",
            bundle_hash="int-policy-gate-bundle",
            subject=adapters.design_subject(action, subject),
            checkpointer=InMemorySaver(),
        )
        return orchestrator.run()

    def test_int_02_unknown_component_denied(self):
        state = self._run(
            "DESIGN_SELECT_COMPONENT",
            {"mpn": "UNKNOWN-MPN-999", "role": "power_regulator", "evidence_ids": []},
        )
        self.assertEqual(state["terminal_reason"], "POLICY_COMPONENT_NOT_ALLOWED")
        self.assertEqual(len(self.executor.calls), 0)

    def test_int_03_gpio36_denied(self):
        state = self._run(
            "DESIGN_ASSIGN_PIN",
            {"pin": "GPIO36", "function": "gpio", "approval_status": "NOT_REQUIRED"},
        )
        self.assertEqual(state["terminal_reason"], "POLICY_PIN_HARD_FORBIDDEN")
        self.assertEqual(len(self.executor.calls), 0)

    def test_int_04_network_denied(self):
        state = self._run(
            "NETWORK_ACCESS",
            {"destination": "example.invalid", "purpose": "datasheet fetch"},
        )
        self.assertEqual(state["terminal_reason"], "POLICY_NETWORK_DISABLED")
        self.assertEqual(len(self.executor.calls), 0)

    def test_int_05_direct_kicad_write_denied(self):
        state = self._run(
            "FILE_WRITE",
            {"path": "board.kicad_sch", "artifact_kind": "kicad_sch", "writer": "agent"},
        )
        self.assertEqual(state["terminal_reason"], "POLICY_DIRECT_KICAD_WRITE")
        self.assertEqual(len(self.executor.calls), 0)

    def test_int_06_missing_verifier_coverage_blocked(self):
        state = self._run(
            "VERIFY_ARTIFACT",
            {
                "verifier_id": adapters.TEST_ONLY_VERIFIER_ID,
                "verifier_version": "1.0.0",
                "artifact_kind": "kicad_sch",
                "coverage_ids": ["ERC", "SPICE"],
            },
        )
        self.assertEqual(state["terminal_reason"], "POLICY_VERIFIER_COVERAGE_MISSING")
        self.assertEqual(len(self.executor.calls), 0)

    def test_int_13_outside_root_write_denied_no_outside_file(self):
        state = self._run(
            "FILE_WRITE",
            {"path": "../outside.txt", "artifact_kind": "report", "writer": "agent"},
        )
        self.assertEqual(state["terminal_reason"], "POLICY_PATH_ESCAPE")
        self.assertEqual(len(self.executor.calls), 0)
        run_dir = self.ws_root / "run" / "int-policy-gate"
        self.assertFalse((self.ws_root / "outside.txt").exists())
        self.assertFalse((run_dir / "outside.txt").exists())
        self.assertFalse((run_dir.parent / "outside.txt").exists())


class Int07To09FixtureTests(unittest.TestCase):
    def _fixture(self, tmp: str, run_id: str, **kwargs) -> tuple[SandboxOrchestrator, dict]:
        return (
            adapters.build_test_only_fixture_orchestrator(
                Path(tmp), run_id, InMemorySaver(), **kwargs
            ),
            {},
        )

    def test_int_07_fail_once_repairs_to_pass_then_interrupts(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = adapters._TestOnlyExecutor()
            orchestrator = adapters.build_test_only_fixture_orchestrator(
                Path(tmp), "int-07", InMemorySaver(), executor=executor
            )
            state = orchestrator.run()
            self.assertEqual(state["repair_count"], 1)
            self.assertEqual(state["verification_result"]["status"], "PASS")
            self.assertIsNone(state["promotion_result"])
            pending = orchestrator.pending_interrupt()
            self.assertIsNotNone(pending)
            self.assertEqual(pending["verification_status"], "PASS")
            self.assertEqual(len(executor.calls), 2)
            candidate_dir = Path(tmp) / "run" / "int-07" / "candidate"
            self.assertEqual(len(list(candidate_dir.iterdir())), 2)

    def test_int_08_approval_promotes_without_repeating_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            executor = adapters._TestOnlyExecutor()
            orchestrator = adapters.build_test_only_fixture_orchestrator(
                Path(tmp), "int-08", InMemorySaver(), executor=executor
            )
            state = orchestrator.run()
            artifact = Path(state["candidate_root"]) / "artifact.json"
            before = artifact.read_bytes()
            final = orchestrator.resume(APPROVED, approved_by="int-reviewer@example")
            self.assertEqual(final["terminal_reason"], "STATE_PROMOTED")
            self.assertEqual(final["promotion_result"]["outcome"], "ALLOW")
            self.assertEqual(final["promotion_result"]["reason_code"], "PROMOTION_ALLOWED")
            self.assertEqual(final["candidate_id"], state["candidate_id"])
            action_ids = [call.action_id for call in executor.calls]
            self.assertEqual(len(action_ids), 2)
            self.assertEqual(len(set(action_ids)), 2)
            self.assertEqual(artifact.read_bytes(), before)
            receipts = final["evidence_receipts"]
            self.assertTrue(all(receipt["valid"] for receipt in receipts))

    def test_int_09_rejection_retains_candidate_unpromoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = adapters.build_test_only_fixture_orchestrator(
                Path(tmp), "int-09", InMemorySaver()
            )
            state = orchestrator.run()
            candidate_root = Path(state["candidate_root"])
            final = orchestrator.resume(REJECTED, approved_by="int-reviewer@example")
            self.assertEqual(final["terminal_reason"], "APPROVAL_HUMAN_REJECTED")
            self.assertEqual(final["promotion_result"]["outcome"], "DENY")
            self.assertTrue(candidate_root.exists())
            self.assertEqual(final["candidate_id"], state["candidate_id"])


class Int10To11RepairBoundTests(unittest.TestCase):
    def test_int_10_repeated_finding_stalls_before_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            verifier = _StuckVerifier()
            orchestrator = adapters.build_test_only_fixture_orchestrator(
                Path(tmp), "int-10", InMemorySaver(), verifier=verifier
            )
            state = orchestrator.run()
            self.assertEqual(state["terminal_reason"], "REPAIR_STALLED")
            self.assertEqual(state["repair_count"], 1)
            self.assertEqual(state["stall_count"], 1)
            self.assertLess(state["repair_count"], state["max_repairs"])

    def test_int_11_changing_findings_hit_repair_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            verifier = _ChangingVerifier()
            orchestrator = adapters.build_test_only_fixture_orchestrator(
                Path(tmp), "int-11", InMemorySaver(), verifier=verifier, max_repairs=2
            )
            state = orchestrator.run()
            self.assertEqual(state["terminal_reason"], "REPAIR_LIMIT_REACHED")
            self.assertEqual(state["repair_count"], 2)
            self.assertEqual(verifier.calls, 3)


class Int12MutationTests(unittest.TestCase):
    def test_int_12_candidate_mutation_denied_evidence_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = adapters.build_test_only_fixture_orchestrator(
                Path(tmp), "int-12", InMemorySaver()
            )
            state = orchestrator.run()
            (Path(state["candidate_root"]) / "mutation.txt").write_text(
                "post-verification mutation", encoding="utf-8"
            )
            final = orchestrator.resume(APPROVED, approved_by="int-reviewer@example")
            self.assertEqual(final["terminal_reason"], "EVIDENCE_STALE")
            self.assertEqual(final["promotion_result"]["outcome"], "DENY")
            self.assertEqual(final["promotion_result"]["reason_code"], "EVIDENCE_STALE")

    def test_int_15_hidden_file_mutation_denied_evidence_stale(self):
        # Review P1 counter-example through the REAL M/L adapters: mutating a
        # hidden file after verification must invalidate the candidate hash,
        # so promotion is denied EVIDENCE_STALE instead of promoted on stale
        # evidence.
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = adapters.build_test_only_fixture_orchestrator(
                Path(tmp), "int-15", InMemorySaver()
            )
            state = orchestrator.run()
            (Path(state["candidate_root"]) / ".hidden_meta").write_text(
                "post-verification hidden mutation", encoding="utf-8"
            )
            final = orchestrator.resume(APPROVED, approved_by="int-reviewer@example")
            self.assertEqual(final["terminal_reason"], "EVIDENCE_STALE")
            self.assertEqual(final["promotion_result"]["outcome"], "DENY")
            self.assertEqual(final["promotion_result"]["reason_code"], "EVIDENCE_STALE")


class Int14RestartTests(unittest.TestCase):
    def test_int_14_restart_resumes_without_repeating_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws_root = Path(tmp)
            run_id = "int-14"
            db_path = ws_root / "run" / run_id / "checkpoint.sqlite"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            executor_first = adapters._TestOnlyExecutor()
            with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
                first = adapters.build_test_only_fixture_orchestrator(
                    ws_root, run_id, checkpointer, executor=executor_first
                )
                state_first = first.run()
                self.assertIsNotNone(first.pending_interrupt())
            artifact = Path(state_first["candidate_root"]) / "artifact.json"
            artifact_before = artifact.read_bytes()
            candidate_dir = ws_root / "run" / run_id / "candidate"

            def ledger_lines() -> int:
                return sum(
                    len(ledger.read_text(encoding="utf-8").splitlines())
                    for ledger in candidate_dir.glob("*/.actions.jsonl")
                )

            lines_before = ledger_lines()

            executor_second = adapters._TestOnlyExecutor()
            with SqliteSaver.from_conn_string(str(db_path)) as checkpointer:
                second = adapters.build_test_only_fixture_orchestrator(
                    ws_root, run_id, checkpointer, executor=executor_second
                )
                state_second = second.resume(APPROVED, approved_by="int-reviewer@example")
            self.assertEqual(len(executor_second.calls), 0)
            self.assertEqual(state_second["run_id"], state_first["run_id"])
            self.assertEqual(state_second["candidate_id"], state_first["candidate_id"])
            self.assertEqual(state_second["terminal_reason"], "STATE_PROMOTED")
            self.assertEqual(artifact.read_bytes(), artifact_before)
            self.assertEqual(ledger_lines(), lines_before)


if __name__ == "__main__":
    unittest.main()
