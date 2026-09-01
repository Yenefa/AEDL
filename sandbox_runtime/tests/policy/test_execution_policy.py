"""Execution Sandbox policy: tools, network, shell, files, compilers, verifiers.

These tests assert that capability is bounded exactly by the registry: nothing
is authorized by name similarity, and containment is decided on resolved paths.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aedl_sandbox.protocol import REASON_CODE_PREFIXES, Outcome
from aedl_sandbox.policy import SandboxPolicyEngine

from . import fixtures as fx


class ExecutionPolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.candidate_root = self.root / "runs" / "run-test-0001" / "candidate"
        self.candidate_root.mkdir(parents=True)
        self.engine = SandboxPolicyEngine.from_document(fx.complete_document(), self.root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def evaluate(self, action: str, subject: dict, **kwargs):
        decision = self.engine.evaluate(
            fx.request(action, subject, candidate_root=self.candidate_root, **kwargs)
        )
        fx.assert_sorted_findings(self, decision)
        self.assertTrue(
            decision.reason_code.startswith(REASON_CODE_PREFIXES),
            f"reason code {decision.reason_code!r} outside frozen namespace",
        )
        return decision


class NetworkPolicyTests(ExecutionPolicyTestCase):
    def test_network_access_is_always_denied(self) -> None:
        for destination, purpose in (
            ("espressif.com", "datasheet"),
            ("lcsc.com", "pricing"),
            ("", ""),
        ):
            decision = self.evaluate(
                "NETWORK_ACCESS", {"destination": destination, "purpose": purpose}
            )
            self.assertEqual(decision.outcome, Outcome.DENY, msg=destination)
            self.assertEqual(decision.reason_code, "POLICY_NETWORK_DISABLED")

    def test_malformed_network_subject_is_denied_before_the_network_rule(self) -> None:
        decision = self.evaluate("NETWORK_ACCESS", {"destination": "espressif.com"})
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_SUBJECT_MALFORMED")


class ShellPolicyTests(ExecutionPolicyTestCase):
    def test_shell_execute_is_always_denied(self) -> None:
        for command_class in ("arbitrary", "kicad_cli", "", "package_install"):
            decision = self.evaluate("SHELL_EXECUTE", {"command_class": command_class})
            self.assertEqual(decision.outcome, Outcome.DENY, msg=command_class)
            self.assertEqual(decision.reason_code, "POLICY_ARBITRARY_SHELL_DISABLED")


class ToolPolicyTests(ExecutionPolicyTestCase):
    def execute(self, tool_id: str, version: str, capability: str):
        return self.evaluate(
            "TOOL_EXECUTE",
            {"tool_id": tool_id, "tool_version": version, "capability": capability},
        )

    def test_registered_tool_is_allowed(self) -> None:
        decision = self.execute("kicad-cli", "8.0.0", "netlist_export")
        self.assertEqual(decision.outcome, Outcome.ALLOW)

    def test_unregistered_tool_is_denied(self) -> None:
        decision = self.execute("pcbnew", "8.0.0", "netlist_export")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_TOOL_NOT_ALLOWED")

    def test_wrong_version_is_denied(self) -> None:
        decision = self.execute("kicad-cli", "9.0.0", "netlist_export")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_TOOL_NOT_ALLOWED")

    def test_unregistered_capability_is_denied(self) -> None:
        decision = self.execute("kicad-cli", "8.0.0", "gerber_export")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_TOOL_NOT_ALLOWED")

    def test_string_tricks_do_not_authorize_tools(self) -> None:
        for tool_id in ("KICAD-CLI", "kicad-cli ", " kicad-cli", "kicad", "kicad-cli-9"):
            decision = self.execute(tool_id, "8.0.0", "netlist_export")
            self.assertEqual(decision.outcome, Outcome.DENY, msg=repr(tool_id))
            self.assertEqual(decision.reason_code, "POLICY_TOOL_NOT_ALLOWED")

    def test_version_matching_is_exact(self) -> None:
        for version in ("8.0", "8.0.0.0", " 8.0.0", "8.0.0 "):
            decision = self.execute("kicad-cli", version, "netlist_export")
            self.assertEqual(decision.outcome, Outcome.DENY, msg=repr(version))


class FileWritePolicyTests(ExecutionPolicyTestCase):
    def write(self, path: str, artifact_kind: str, writer: str, **kwargs):
        return self.evaluate(
            "FILE_WRITE", {"path": path, "artifact_kind": artifact_kind, "writer": writer}, **kwargs
        )

    def compiler_request(self, path: str, artifact_kind: str, **kwargs):
        return self.evaluate(
            "FILE_WRITE",
            {"path": path, "artifact_kind": artifact_kind, "writer": "compiler"},
            actor=fx.ActorIdentity(actor_id="compiler-1", actor_kind="compiler", run_id="run-test-0001"),
            capability_grants=(fx.compiler_writer_grant(),),
            **kwargs,
        )

    def test_agent_may_write_a_non_kicad_artifact_inside_the_candidate_root(self) -> None:
        decision = self.write("design.net", "netlist", "agent")
        self.assertEqual(decision.outcome, Outcome.ALLOW)

    def test_agent_writing_kicad_sch_is_denied(self) -> None:
        decision = self.write("design.kicad_sch", "kicad_sch", "agent")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_DIRECT_KICAD_WRITE")

    def test_agent_writing_kicad_pcb_is_denied(self) -> None:
        decision = self.write("design.kicad_pcb", "kicad_pcb", "agent")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_DIRECT_KICAD_WRITE")

    def test_self_declared_compiler_writer_is_denied(self) -> None:
        """Audit counterexample (Wave 3): writer=compiler written by the
        requester without an orchestrator-signed grant must never be ALLOW."""
        decision = self.write("design.kicad_sch", "kicad_sch", "compiler")
        self.assertNotEqual(decision.outcome, Outcome.ALLOW)
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_CAPABILITY_NOT_GRANTED")

    def test_compiler_writer_without_a_trusted_actor_is_denied(self) -> None:
        decision = self.engine.evaluate(
            fx.request(
                "FILE_WRITE",
                {"path": "design.kicad_sch", "artifact_kind": "kicad_sch", "writer": "compiler"},
                candidate_root=self.candidate_root,
                capability_grants=(fx.compiler_writer_grant(),),
            )
        )
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_CAPABILITY_NOT_GRANTED")

    def test_compiler_writer_grant_must_bind_run_actor_and_receipt(self) -> None:
        actor = fx.ActorIdentity(actor_id="compiler-1", actor_kind="compiler", run_id="run-test-0001")
        broken_grants = (
            fx.compiler_writer_grant(run_id="other-run"),
            fx.compiler_writer_grant(actor_id="compiler-2"),
            fx.CapabilityGrant(
                run_id="run-test-0001",
                actor_id="compiler-1",
                capability="writer=compiler",
                receipt_sha256="",
            ),
            fx.CapabilityGrant(
                run_id="run-test-0001",
                actor_id="compiler-1",
                capability="writer=compiler ",
                receipt_sha256="b" * 64,
            ),
        )
        for grant in broken_grants:
            decision = self.engine.evaluate(
                fx.request(
                    "FILE_WRITE",
                    {"path": "design.kicad_sch", "artifact_kind": "kicad_sch", "writer": "compiler"},
                    candidate_root=self.candidate_root,
                    actor=actor,
                    capability_grants=(grant,),
                )
            )
            self.assertEqual(decision.outcome, Outcome.DENY, msg=str(grant))
            self.assertEqual(decision.reason_code, "POLICY_CAPABILITY_NOT_GRANTED")

    def test_granted_compiler_may_write_kicad_artifacts(self) -> None:
        decision = self.compiler_request("design.kicad_sch", "kicad_sch")
        self.assertEqual(decision.outcome, Outcome.ALLOW)

    def test_granted_compiler_writing_an_unregistered_output_kind_is_blocked(self) -> None:
        decision = self.compiler_request("design.net", "netlist")
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "POLICY_COMPILER_NOT_REGISTERED")

    def test_unknown_artifact_kind_is_denied(self) -> None:
        decision = self.write("notes.txt", "gerber", "agent")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_ARTIFACT_KIND_NOT_ALLOWED")

    def test_parent_traversal_escapes_are_denied(self) -> None:
        for path in (
            "../escape.net",
            "sub/../../escape.net",
            "../../escape.net",
            "a/b/c/../../../../escape.net",
        ):
            decision = self.write(path, "netlist", "agent")
            self.assertEqual(decision.outcome, Outcome.DENY, msg=path)
            self.assertEqual(decision.reason_code, "POLICY_PATH_ESCAPE")

    def test_absolute_path_outside_candidate_root_is_denied(self) -> None:
        outside = self.root / "outside.net"
        decision = self.write(str(outside), "netlist", "agent")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PATH_ESCAPE")

    def test_absolute_path_inside_candidate_root_is_allowed(self) -> None:
        inside = self.candidate_root / "nested" / "design.net"
        decision = self.write(str(inside), "netlist", "agent")
        self.assertEqual(decision.outcome, Outcome.ALLOW)

    def test_traversal_that_stays_inside_is_allowed(self) -> None:
        decision = self.write("sub/../design.net", "netlist", "agent")
        self.assertEqual(decision.outcome, Outcome.ALLOW)

    def test_empty_and_unresolvable_paths_are_denied(self) -> None:
        for path in ("", "nul\x00byte"):
            decision = self.write(path, "netlist", "agent")
            self.assertEqual(decision.outcome, Outcome.DENY, msg=repr(path))
            self.assertEqual(decision.reason_code, "POLICY_PATH_ESCAPE")

    def test_paths_that_collapse_onto_the_candidate_root_are_denied(self) -> None:
        # Regression: a whitespace-only path normalized back onto the candidate
        # root itself, which is a directory and not a writable file target.
        for path in ("   ", ".", "./", "sub/.."):
            decision = self.write(path, "netlist", "agent")
            self.assertEqual(decision.outcome, Outcome.DENY, msg=repr(path))
            self.assertEqual(decision.reason_code, "POLICY_PATH_ESCAPE")

    def test_traversal_that_returns_to_the_root_stays_inside(self) -> None:
        # a/b/c/../../.. resolves back onto the candidate root; appending a file
        # name keeps the target inside, so this is legitimate and not a bypass.
        decision = self.write("a/b/c/../../../design.net", "netlist", "agent")
        self.assertEqual(decision.outcome, Outcome.ALLOW)

    def test_path_escape_takes_precedence_over_direct_kicad_write(self) -> None:
        decision = self.write("../design.kicad_sch", "kicad_sch", "agent")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PATH_ESCAPE")

    def test_unknown_writer_is_a_malformed_subject(self) -> None:
        decision = self.write("design.net", "netlist", "human")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_SUBJECT_MALFORMED")


class CompileHirPolicyTests(ExecutionPolicyTestCase):
    def compile_hir(self, compiler_id="hir-to-kicad", version="1.0.0", output_kind="kicad_sch", coverage=("ERC", "CONTRACT")):
        return self.evaluate(
            "COMPILE_HIR",
            {
                "compiler_id": compiler_id,
                "compiler_version": version,
                "output_kind": output_kind,
                "coverage_ids": list(coverage),
            },
        )

    def test_registered_compiler_with_full_coverage_is_allowed(self) -> None:
        decision = self.compile_hir()
        self.assertEqual(decision.outcome, Outcome.ALLOW)

    def test_unregistered_compiler_is_blocked(self) -> None:
        decision = self.compile_hir(compiler_id="some-other-compiler")
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "POLICY_COMPILER_NOT_REGISTERED")

    def test_wrong_compiler_version_is_blocked(self) -> None:
        decision = self.compile_hir(version="2.0.0")
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "POLICY_COMPILER_NOT_REGISTERED")

    def test_unregistered_output_kind_is_blocked(self) -> None:
        decision = self.compile_hir(output_kind="kicad_pcb")
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "POLICY_COMPILER_NOT_REGISTERED")

    def test_uncovered_requested_coverage_is_blocked(self) -> None:
        decision = self.compile_hir(coverage=("ERC", "SIMULATION"))
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "POLICY_VERIFIER_COVERAGE_MISSING")
        self.assertIn("SIMULATION", decision.findings[0].details["missing_coverage_ids"])

    def test_missing_required_coverage_is_blocked(self) -> None:
        engine = SandboxPolicyEngine.from_document(
            fx.complete_document(
                verifiers=[
                    {
                        "verifier_id": "kicad-audit",
                        "verifier_version": "1.0.0",
                        "artifact_kind": "kicad_sch",
                        "coverage_ids": ["ERC"],
                    }
                ]
            ),
            self.root,
        )
        decision = engine.evaluate(
            fx.request(
                "COMPILE_HIR",
                {
                    "compiler_id": "hir-to-kicad",
                    "compiler_version": "1.0.0",
                    "output_kind": "kicad_sch",
                    "coverage_ids": ["ERC"],
                },
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "POLICY_VERIFIER_COVERAGE_MISSING")
        self.assertIn("CONTRACT", decision.findings[0].details["missing_coverage_ids"])

    def test_unresolved_generic_component_blocks_compilation(self) -> None:
        engine = SandboxPolicyEngine.from_document(
            fx.complete_document(
                prerequisites={
                    "required_contract_ids": ["EDD-001.CORE_BASE"],
                    "required_evidence_ids": ["TEST_EVIDENCE_A"],
                    "required_component_resolutions": ["LED_GENERIC"],
                }
            ),
            self.root,
        )
        decision = engine.evaluate(
            fx.request(
                "COMPILE_HIR",
                {
                    "compiler_id": "hir-to-kicad",
                    "compiler_version": "1.0.0",
                    "output_kind": "kicad_sch",
                    "coverage_ids": ["ERC", "CONTRACT"],
                },
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "POLICY_COMPONENT_RESOLUTION_REQUIRED")
        self.assertEqual(decision.findings[0].details["generic"], "LED_GENERIC")

    def test_generic_component_may_still_be_selected_at_hir_level(self) -> None:
        decision = self.evaluate(
            "DESIGN_SELECT_COMPONENT",
            {"mpn": "LED_GENERIC", "role": "indicator", "evidence_ids": []},
        )
        self.assertEqual(decision.outcome, Outcome.ALLOW)


class VerifyArtifactPolicyTests(ExecutionPolicyTestCase):
    def verify(self, verifier_id="kicad-audit", version="1.0.0", artifact_kind="kicad_sch", coverage=("ERC",)):
        return self.evaluate(
            "VERIFY_ARTIFACT",
            {
                "verifier_id": verifier_id,
                "verifier_version": version,
                "artifact_kind": artifact_kind,
                "coverage_ids": list(coverage),
            },
        )

    def test_registered_verifier_with_coverage_is_allowed(self) -> None:
        self.assertEqual(self.verify().outcome, Outcome.ALLOW)

    def test_unregistered_verifier_is_denied(self) -> None:
        decision = self.verify(verifier_id="mystery-audit")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_VERIFIER_NOT_ALLOWED")

    def test_wrong_verifier_version_is_denied(self) -> None:
        decision = self.verify(version="0.9.0")
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_VERIFIER_NOT_ALLOWED")

    def test_coverage_gap_is_blocked(self) -> None:
        decision = self.verify(coverage=("ERC", "SIMULATION"))
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "POLICY_VERIFIER_COVERAGE_MISSING")


class OutcomePrecedenceTests(ExecutionPolicyTestCase):
    def test_deny_wins_over_a_missing_prerequisite(self) -> None:
        engine = SandboxPolicyEngine.from_document(
            fx.complete_document(
                prerequisites={
                    "required_contract_ids": ["EDD-001.MISSING"],
                    "required_evidence_ids": [],
                    "required_component_resolutions": [],
                },
                available={"contract_ids": [], "evidence_ids": ["TEST_EVIDENCE_A"]},
            ),
            self.root,
        )
        decision = engine.evaluate(
            fx.request(
                "NETWORK_ACCESS",
                {"destination": "example.com", "purpose": "datasheet"},
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_NETWORK_DISABLED")

    def test_missing_contract_blocks_an_otherwise_valid_action(self) -> None:
        engine = SandboxPolicyEngine.from_document(
            fx.complete_document(
                prerequisites={
                    "required_contract_ids": ["EDD-001.POWER"],
                    "required_evidence_ids": [],
                    "required_component_resolutions": [],
                },
                available={"contract_ids": ["EDD-001.CORE_BASE"], "evidence_ids": ["TEST_EVIDENCE_A"]},
            ),
            self.root,
        )
        decision = engine.evaluate(
            fx.request(
                "DESIGN_ASSIGN_PIN",
                {"pin": "GPIO1", "function": "LED", "approval_status": "NOT_REQUIRED"},
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_REQUIRED_CONTRACT_MISSING")
        self.assertEqual(decision.findings[0].details["contract_id"], "EDD-001.POWER")

    def test_missing_domain_evidence_blocks_an_otherwise_valid_action(self) -> None:
        engine = SandboxPolicyEngine.from_document(
            fx.complete_document(available={"contract_ids": ["EDD-001.CORE_BASE"], "evidence_ids": []}),
            self.root,
        )
        decision = engine.evaluate(
            fx.request(
                "DESIGN_ASSIGN_PIN",
                {"pin": "GPIO2", "function": "LED", "approval_status": "NOT_REQUIRED"},
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_REQUIRED_EVIDENCE_MISSING")


if __name__ == "__main__":
    unittest.main()
