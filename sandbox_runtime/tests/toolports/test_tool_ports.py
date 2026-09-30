"""Tool-port tests: the registry, the fail-closed refusals, the artifact class.

Every test here builds its own temporary root. The load-bearing ones assert what
a REFUSAL does and does NOT do -- specifically, that a refusal never becomes a
PASS and never leaves a half-built candidate behind.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aedl_sandbox import adapters
from aedl_sandbox.protocol import ExecutorPort, VerifierPort
from aedl_sandbox.toolports import (
    HIR_ARTIFACT_NAME,
    ToolBackendError,
    ToolNotResolved,
    ToolPlanError,
    ToolRegistry,
    ToolRegistration,
    build_in_repo_ports,
    design_envelope,
    registry_from_document,
    run_command,
)

from . import fixtures


class _NullBackend:
    """A backend that exists and does nothing, for registry-shape tests."""

    backend = adapters.BACKEND_IN_REPO_HIR
    version = "1.0.0"

    def compile(self, registration, request):  # pragma: no cover - never called
        raise AssertionError("the null backend must never run")

    def check(self, registration, candidate_root, **kwargs):  # pragma: no cover
        raise AssertionError("the null backend must never run")


class TempRootTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def _ports(self, *, envelope=None, engine=None):
        envelope = envelope or fixtures.design_envelope_for(self.base)
        engine = engine or fixtures.test_only_engine(self.base)
        action, subject, _kind = fixtures.split(envelope)
        return build_in_repo_ports(engine, design_action=action, design_subject=subject)


class EnvelopeSchemaTests(TempRootTest):
    """The envelope is a CLOSED schema. Extras are the T-08 side channel."""

    def test_unexpected_envelope_key_is_refused(self) -> None:
        envelope = fixtures.design_envelope_for(self.base)
        envelope["smuggled"] = {"anything": True}
        with self.assertRaises(ToolPlanError) as caught:
            fixtures.split(envelope)
        self.assertEqual(caught.exception.code, "ENVELOPE_UNEXPECTED_KEYS")
        self.assertIn("smuggled", caught.exception.details["unexpected_keys"])

    def test_missing_output_kind_is_refused_rather_than_guessed(self) -> None:
        envelope = fixtures.design_envelope_for(self.base)
        del envelope["output_kind"]
        with self.assertRaises(ToolPlanError) as caught:
            fixtures.split(envelope)
        self.assertEqual(caught.exception.code, "ENVELOPE_MISSING_OUTPUT_KIND")

    def test_blank_output_kind_is_refused(self) -> None:
        envelope = fixtures.design_envelope_for(self.base, output_kind="   ")
        with self.assertRaises(ToolPlanError) as caught:
            fixtures.split(envelope)
        self.assertEqual(caught.exception.code, "ENVELOPE_MISSING_OUTPUT_KIND")

    def test_orchestrator_actions_are_not_design_actions(self) -> None:
        envelope = fixtures.design_envelope_for(self.base, action="COMPILE_HIR", subject={})
        with self.assertRaises(ToolPlanError) as caught:
            fixtures.split(envelope)
        self.assertEqual(caught.exception.code, "ENVELOPE_NOT_A_DESIGN_ACTION")

    def test_output_kind_is_envelope_level_not_subject_level(self) -> None:
        """It must NOT be a field a proposal could vary.

        The repair agent validates the inner subject against SUBJECT_SPECS by
        exact field set, so an output_kind inside the subject would make every
        model proposal fail -- a total rejection rate that reads as a model that
        cannot follow instructions. Keeping it in the envelope is what makes the
        artifact kind a contract of the RUN.
        """
        envelope = fixtures.design_envelope_for(self.base)
        self.assertIn("output_kind", envelope)
        self.assertNotIn("output_kind", envelope["design_subject"])
        from aedl_sandbox.policy.engine import SUBJECT_SPECS

        self.assertEqual(
            sorted(envelope["design_subject"]),
            sorted(name for name, _ in SUBJECT_SPECS["DESIGN_SELECT_COMPONENT"]),
        )


class RegistryTests(TempRootTest):
    """Resolution failures are named, and they never fall back."""

    def _registry(self, document, backends=None):
        # registry_from_document reads the PARSED document (engine.document),
        # never the raw dict: the records are what carry the coverage ids, and
        # deriving from anything else would be a second parse of the same file.
        engine = fixtures.engine_for(document, self.base)
        return registry_from_document(
            engine.document,
            backends=backends
            if backends is not None
            else {adapters.BACKEND_IN_REPO_HIR: _NullBackend()},
            backend_for_tool=dict(adapters.IN_REPO_TOOL_BACKENDS),
        )

    def test_registry_is_derived_from_the_document(self) -> None:
        registry = self._registry(adapters.test_only_document())
        ids = sorted(r.tool_id for r in registry.compilers())
        self.assertEqual(ids, ["in-repo-hir", "test-only-compiler"])
        vids = sorted(r.tool_id for r in registry.verifiers())
        self.assertEqual(vids, ["in-repo-hir-verifier", "test-only-verifier"])

    def test_backend_filter_selects_only_that_backend(self) -> None:
        """The filter is by BACKEND, not by runnability."""
        registry = self._registry(adapters.test_only_document())
        only_in_repo = [r.tool_id for r in registry.compilers(backend=adapters.BACKEND_IN_REPO_HIR)]
        self.assertEqual(sorted(only_in_repo), ["in-repo-hir", "test-only-compiler"])
        self.assertEqual(registry.compilers(backend="command"), ())

    def test_unregistered_compiler_refuses_by_name(self) -> None:
        registry = self._registry(adapters.test_only_document())
        with self.assertRaises(ToolNotResolved) as caught:
            registry.resolve_compiler("kicad-hir", "1.0.0")
        self.assertIn("kicad-hir", str(caught.exception))
        self.assertIn("never a fallback", str(caught.exception))

    def test_version_mismatch_refuses_rather_than_running_the_other_version(self) -> None:
        registry = self._registry(adapters.test_only_document())
        with self.assertRaises(ToolNotResolved) as caught:
            registry.resolve_compiler("in-repo-hir", "2.0.0")
        self.assertIn("not at version", str(caught.exception))
        self.assertIn("substitution", str(caught.exception))

    def test_tool_without_a_backend_is_unresolvable_not_skipped(self) -> None:
        registry = ToolRegistry(
            [
                ToolRegistration(
                    kind="compiler",
                    tool_id="ghost",
                    version="1.0.0",
                    artifact_kind="hir",
                    coverage_ids=(),
                    required_coverage_ids=(),
                    backend="no-such-backend",
                )
            ],
            {},
        )
        registration = registry.resolve_compiler("ghost", "1.0.0")
        with self.assertRaises(ToolNotResolved) as caught:
            registry.backend_for(registration)
        self.assertIn("no-such-backend", str(caught.exception))
        self.assertIn("AUTHORIZES", str(caught.exception))

    def test_registry_construction_does_not_require_every_tool_to_be_runnable(self) -> None:
        """A document may legitimately declare tools this process cannot run.

        Regression guard for a design mistake made while building this: the
        registry first refused to CONSTRUCT when any registered tool had no
        backend, which made an unrelated declaration fatal and would have made
        the real EDD-001 document (which declares no tools at all) the only
        construable one. The refusal belongs at resolution.
        """
        registry = self._registry(adapters.test_only_document(), backends={})
        self.assertEqual(len(registry.compilers()), 2)
        self.assertEqual(len(registry.compilers(runnable_only=True)), 0)
        with self.assertRaises(ToolNotResolved):
            registry.backend_for(registry.resolve_compiler("in-repo-hir", "1.0.0"))


class ExecutorRefusalTests(TempRootTest):
    """A refusal is a failed ExecutionResult with a named finding -- never a PASS."""

    def test_unknown_output_kind_is_refused_by_the_executor(self) -> None:
        envelope = fixtures.design_envelope_for(self.base, output_kind="kicad_pcb")
        executor, _verifier = self._ports(envelope=envelope)
        result = executor.execute(fixtures.execute_request(self.base, envelope))
        self.assertFalse(result.success)
        self.assertEqual([f.code for f in result.findings], ["EXECUTOR_TOOL_NOT_RESOLVED"])
        self.assertIn("kicad_pcb", result.findings[0].message)

    def test_not_allowed_component_never_reaches_an_artifact(self) -> None:
        envelope = fixtures.design_envelope_for(
            self.base,
            subject={"mpn": "NOT-IN-THE-DOCUMENT", "role": "power_regulator", "evidence_ids": ["E"]},
        )
        executor, _verifier = self._ports(envelope=envelope)
        request = fixtures.execute_request(self.base, envelope)
        result = executor.execute(request)
        self.assertFalse(result.success)
        self.assertEqual([f.code for f in result.findings], ["PLAN_COMPONENT_NOT_ALLOWED"])
        self.assertFalse((Path(request.candidate_root) / HIR_ARTIFACT_NAME).exists())

    def test_forbidden_pin_is_refused_and_writes_nothing(self) -> None:
        envelope = fixtures.design_envelope_for(
            self.base,
            action="DESIGN_ASSIGN_PIN",
            subject={"pin": "GPIO36", "function": "spi_clk", "approval_status": "PENDING"},
        )
        executor, _verifier = self._ports(envelope=envelope)
        request = fixtures.execute_request(self.base, envelope)
        result = executor.execute(request)
        self.assertFalse(result.success)
        self.assertEqual([f.code for f in result.findings], ["PLAN_PIN_HARD_FORBIDDEN"])
        self.assertFalse((Path(request.candidate_root) / HIR_ARTIFACT_NAME).exists())

    def test_unlisted_pin_is_refused_rather_than_recorded(self) -> None:
        envelope = fixtures.design_envelope_for(
            self.base,
            action="DESIGN_ASSIGN_PIN",
            subject={"pin": "GPIO99", "function": "mystery", "approval_status": "PENDING"},
        )
        executor, _verifier = self._ports(envelope=envelope)
        result = executor.execute(fixtures.execute_request(self.base, envelope))
        self.assertFalse(result.success)
        self.assertEqual([f.code for f in result.findings], ["PLAN_PIN_NOT_ALLOWED"])

    def test_undeclared_parameter_is_refused(self) -> None:
        envelope = fixtures.design_envelope_for(
            self.base,
            action="DESIGN_SET_PARAMETER",
            subject={"parameter_id": "NOPE", "value": 1, "unit": "ohm", "evidence_ids": ["E"]},
        )
        executor, _verifier = self._ports(envelope=envelope)
        result = executor.execute(fixtures.execute_request(self.base, envelope))
        self.assertFalse(result.success)
        self.assertEqual([f.code for f in result.findings], ["PLAN_PARAMETER_NOT_DECLARED"])


class ExecutorWiringTests(TempRootTest):
    def test_assembled_ports_satisfy_the_frozen_protocols(self) -> None:
        executor, verifier = self._ports()
        self.assertIsInstance(executor, ExecutorPort)
        self.assertIsInstance(verifier, VerifierPort)

    def test_assembly_refuses_when_the_domain_registers_no_in_repo_tool(self) -> None:
        """Assembly fails rather than discovering the gap mid-round."""
        from aedl_sandbox.policy.errors import PolicySchemaError

        document = adapters.test_only_document()
        document["compilers"] = []
        document["verifiers"] = []
        try:
            engine = fixtures.engine_for(document, self.base)
        except PolicySchemaError as exc:
            self.skipTest("document without tools is refused earlier: %s" % exc)
        with self.assertRaises(ToolNotResolved):
            build_in_repo_ports(
                engine,
                design_action="DESIGN_SELECT_COMPONENT",
                design_subject={"mpn": "x", "role": "y", "evidence_ids": []},
                backend_for_tool={},
            )

    def test_a_successful_execution_writes_exactly_one_artifact_inside_the_root(self) -> None:
        executor, _verifier = self._ports()
        request = fixtures.execute_request(self.base, fixtures.design_envelope_for(self.base))
        result = executor.execute(request)
        self.assertTrue(result.success)
        self.assertEqual(len(result.artifacts), 1)
        self.assertEqual(result.artifacts[0].name, HIR_ARTIFACT_NAME)
        self.assertEqual(result.actor_id, "in-repo-hir")
        written = sorted(p.name for p in Path(request.candidate_root).iterdir())
        self.assertEqual(written, [HIR_ARTIFACT_NAME])


class VerifierIndependenceTests(TempRootTest):
    """The verifier re-derives and reads bytes; it does not echo a decision."""

    def _run(self):
        envelope = fixtures.design_envelope_for(self.base)
        executor, verifier = self._ports(envelope=envelope)
        request = fixtures.execute_request(self.base, envelope)
        self.assertTrue(executor.execute(request).success)
        return verifier, Path(request.candidate_root)

    def test_untampered_artifact_passes_and_publishes_its_scope(self) -> None:
        verifier, root = self._run()
        result = verifier.verify("run-1", root.name, root)
        self.assertEqual(result.status.value, "PASS")
        self.assertEqual(result.actor_id, "in-repo-hir-verifier")
        codes = [f.code for f in result.findings]
        self.assertIn("VERIFY_IN_REPO_HIR_SCOPE", codes)
        scope = next(f for f in result.findings if f.code == "VERIFY_IN_REPO_HIR_SCOPE")
        for disclaimer in ("does NOT establish", "ERC/DRC", "manufacturability"):
            self.assertIn(disclaimer, scope.message)

    def test_tampered_plan_fails(self) -> None:
        verifier, root = self._run()
        payload = fixtures.read_artifact(root)
        payload["plan"][0]["mpn"] = "TAMPERED"
        fixtures.write_artifact(root, payload)
        result = verifier.verify("run-1", root.name, root)
        self.assertEqual(result.status.value, "FAIL")
        self.assertIn("VERIFY_PLAN_MISMATCH", [f.code for f in result.findings])

    def test_hand_edited_digest_fails(self) -> None:
        verifier, root = self._run()
        payload = fixtures.read_artifact(root)
        payload["plan_sha256"] = "0" * 64
        fixtures.write_artifact(root, payload)
        result = verifier.verify("run-1", root.name, root)
        self.assertEqual(result.status.value, "FAIL")
        self.assertIn("VERIFY_PLAN_DIGEST_MISMATCH", [f.code for f in result.findings])

    def test_non_canonical_bytes_fail_even_when_the_content_is_right(self) -> None:
        verifier, root = self._run()
        payload = fixtures.read_artifact(root)
        fixtures.artifact_path(root).write_text(
            json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8"
        )
        result = verifier.verify("run-1", root.name, root)
        self.assertEqual(result.status.value, "FAIL")
        self.assertIn("VERIFY_ARTIFACT_NOT_CANONICAL", [f.code for f in result.findings])

    def test_missing_artifact_fails_rather_than_passing_an_empty_candidate(self) -> None:
        verifier, root = self._run()
        fixtures.artifact_path(root).unlink()
        result = verifier.verify("run-1", root.name, root)
        self.assertEqual(result.status.value, "FAIL")
        self.assertEqual([f.code for f in result.findings], ["VERIFY_ARTIFACT_MISSING"])

    def test_artifact_claiming_another_writer_fails(self) -> None:
        verifier, root = self._run()
        payload = fixtures.read_artifact(root)
        payload["tool"] = {"tool_id": "test-only-verifier", "version": "1.0.0"}
        fixtures.write_artifact(root, payload)
        result = verifier.verify("run-1", root.name, root)
        self.assertEqual(result.status.value, "FAIL")
        self.assertIn("VERIFY_ARTIFACT_TOOL_MISMATCH", [f.code for f in result.findings])

    def test_verifying_against_a_different_design_than_the_run_used_fails(self) -> None:
        """Independence check: a verifier handed another design must not pass.

        This is what proves the verifier is not reading the expected answer back
        out of the artifact: the design it checks against is a constructor
        argument, so changing it changes the verdict.
        """
        envelope = fixtures.design_envelope_for(self.base)
        engine = fixtures.test_only_engine(self.base)
        executor, _verifier = self._ports(envelope=envelope, engine=engine)
        request = fixtures.execute_request(self.base, envelope)
        self.assertTrue(executor.execute(request).success)
        other = fixtures.design_envelope_for(
            self.base,
            subject={
                "mpn": adapters.TEST_ONLY_COMPONENT_MPN,
                "role": "not_the_role",
                "evidence_ids": [adapters.TEST_ONLY_EVIDENCE_ID],
            },
        )
        _ex2, verifier2 = self._ports(envelope=other, engine=engine)
        result = verifier2.verify("run-1", "cand-1", Path(request.candidate_root))
        self.assertEqual(result.status.value, "FAIL")
        self.assertIn(
            "PLAN_COMPONENT_ROLE_NOT_ALLOWED", [f.code for f in result.findings]
        )


class VerifierReadOnlyTests(TempRootTest):
    def test_verify_writes_nothing_into_the_candidate(self) -> None:
        envelope = fixtures.design_envelope_for(self.base)
        executor, verifier = self._ports(envelope=envelope)
        request = fixtures.execute_request(self.base, envelope)
        self.assertTrue(executor.execute(request).success)
        root = Path(request.candidate_root)

        def snapshot():
            return {
                str(p.relative_to(root)): (p.stat().st_size, p.stat().st_mtime_ns)
                for p in sorted(root.rglob("*"))
                if p.is_file()
            }

        before = snapshot()
        self.assertEqual(verifier.verify("run-1", root.name, root).status.value, "PASS")
        self.assertEqual(snapshot(), before)


class CommandToolTests(TempRootTest):
    """A command-backed tool either runs and is recorded, or refuses by name."""

    def _registration(self, argv):
        return ToolRegistration(
            kind="compiler",
            tool_id="cli-tool",
            version="1.0.0",
            artifact_kind="hir",
            coverage_ids=(),
            required_coverage_ids=(),
            backend="command",
            command=tuple(argv),
        )

    def test_missing_executable_is_a_named_finding_not_a_pass(self) -> None:
        receipt, findings = run_command(
            self._registration(["definitely-not-installed-anywhere-xyz"])
        )
        self.assertEqual(receipt, {})
        self.assertEqual([f.code for f in findings], ["TOOL_NOT_ON_PATH"])

    def test_frozen_vector_runs_without_a_shell_and_is_recorded(self) -> None:
        import sys

        receipt, findings = run_command(
            self._registration([sys.executable, "-c", "print('ok')"])
        )
        self.assertEqual(findings, ())
        self.assertEqual(receipt["exit_code"], 0)
        self.assertEqual(len(receipt["stdout_sha256"]), 64)
        self.assertFalse(receipt["command"][0].endswith("shell"))

    def test_tool_that_writes_nothing_is_still_not_a_pass(self) -> None:
        registration = ToolRegistration(
            kind="compiler",
            tool_id="empty",
            version="1.0.0",
            artifact_kind="hir",
            coverage_ids=(),
            required_coverage_ids=(),
            backend="command",
            command=(),
        )
        with self.assertRaises(ToolNotResolved):
            run_command(registration)

    def test_command_backend_requires_an_injected_document_for_the_hir_class(self) -> None:
        """The in-repo HIR class has NO default document; it refuses by name."""
        from aedl_sandbox.toolports import InRepoHirBackend

        backend = InRepoHirBackend(adapters.test_only_document())
        registration = ToolRegistration(
            kind="verifier",
            tool_id="in-repo-hir-verifier",
            version="1.0.0",
            artifact_kind="hir",
            coverage_ids=(),
            required_coverage_ids=(),
            backend="in-repo-hir",
        )
        with self.assertRaises(ToolBackendError) as caught:
            backend.check(registration, self.base)
        self.assertEqual(caught.exception.code, "CHECK_NEEDS_DESIGN")
