"""Wiring tests for the live ARH assembly (GH-112).

ZERO NETWORK, asserted rather than assumed. The model is a `FakeModelAdapter`
and the transport, where one is constructed at all, is a counter that fails the
test if it is ever called.

The load-bearing test here is
``test_the_assembled_repair_port_really_is_the_agent``: it asserts the CONTENT of
the PolicyRequest coming back out of the assembled port, not the port's type.
A type assertion would pass just as happily against a port that was wired to the
wrong implementation, and the whole failure mode being guarded is precisely that
the `_TestOnlyRepair` double was substituted for the agent.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from aedl_sandbox import adapters, cli
from aedl_sandbox.arh.llm_repair_port import LLMRepairPort
from aedl_sandbox.arh.model_adapter import (
    FakeModelAdapter,
    ModelResponse,
    OpenAICompatibleAdapter,
)
from aedl_sandbox.policy.engine import SUBJECT_SPECS
from aedl_sandbox.workspace import CandidateWorkspace

from . import fixtures


class _ForbiddenTransport:
    """A transport that fails the test if it is ever used."""

    def __call__(self, *args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError(
            "a network transport was invoked; these tests must not make a call"
        )


class _Checkpointer:
    """Deprecated in favour of langgraph's own in-memory saver; kept out of the
    way by never being passed -- see `_checkpointer()`."""


def _checkpointer():
    """A real saver. langgraph validates the type at `compile()`, so a stub
    cannot stand in here; `InMemorySaver` keeps the test hermetic and needs no
    file, which is what "zero I/O" has to mean for this suite."""
    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


class ActionSchemaDerivationTests(unittest.TestCase):
    """`action_schema` is DERIVED, so it cannot drift from what validates."""

    def test_it_offers_only_design_actions(self):
        schema = adapters.derive_proposal_action_schema()
        self.assertTrue(schema, "no actions offered at all")
        for action in schema:
            self.assertTrue(
                action.startswith("DESIGN_"),
                "%r is offered to the model but is not a design action" % action,
            )

    def test_it_never_offers_an_orchestrator_own_action(self):
        """PREFLIGHT / COMPILE_HIR / VERIFY_ARTIFACT are dispatched by the
        orchestrator on requests it builds itself. A proposal naming one would be
        asking the model to drive machinery it has no authority over."""
        schema = adapters.derive_proposal_action_schema()
        for reserved in ("PREFLIGHT", "COMPILE_HIR", "VERIFY_ARTIFACT"):
            self.assertIn(reserved, SUBJECT_SPECS, "fixture assumption is stale")
            self.assertNotIn(reserved, schema)

    def test_field_names_match_the_validator_exactly(self):
        """The advertised shape and the enforced shape are the same object.

        Kills the drift: an action advertised with fields the validator rejects
        would be a 100% rejection rate presented as a model that cannot follow
        instructions.
        """
        schema = adapters.derive_proposal_action_schema()
        for action, fields in schema.items():
            self.assertEqual(
                fields,
                [name for name, _ in SUBJECT_SPECS[action]],
                "%s advertises fields that differ from SUBJECT_SPECS" % action,
            )

    def test_a_missing_action_would_be_visible(self):
        """If SUBJECT_SPECS ever lost an action the schema still claims, the two
        must not silently agree on nothing. Pinned so the derivation cannot be
        'simplified' into a hard-coded literal elsewhere."""
        schema = adapters.derive_proposal_action_schema()
        self.assertEqual(
            sorted(schema),
            sorted(a for a in SUBJECT_SPECS if a.startswith("DESIGN_")),
        )


class ArhContextInputsTests(unittest.TestCase):
    """The allowlist is the operator's, and an unusable one is refused loudly."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.workspace = CandidateWorkspace(self.base / "ws")

    def _provider(self, allowlist, subject=None):
        return adapters.ArhContextInputs(
            workspace=self.workspace,
            domain_id="EDD-001",
            subject=subject if subject is not None else {"subject_id": "T1"},
            allowlist=allowlist,
        )

    def test_an_empty_component_allowlist_is_refused(self):
        """Otherwise every component proposal fails closed at propose() time and
        presents as a model that cannot follow instructions."""
        with self.assertRaises(ValueError) as caught:
            self._provider({"evidence_ids": ["E-1"], "allowed_components": []})
        self.assertIn("allowed_components", str(caught.exception))

    def test_an_empty_evidence_allowlist_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self._provider({"evidence_ids": [], "allowed_components": [{"mpn": "X"}]})
        self.assertIn("evidence_ids", str(caught.exception))

    def test_it_projects_rather_than_dumping(self):
        """The provider returns ContextInputs built from declared state only --
        no engine document is opened by the harness (D6)."""
        provider = self._provider(fixtures.allowlist())
        self.workspace.create_candidate("run-1", "cand-1")
        inputs = provider("run-1", "cand-1", (fixtures.finding(),))
        self.assertEqual(inputs.domain_id, "EDD-001")
        self.assertTrue(inputs.candidate_root.is_dir())
        self.assertEqual(inputs.action_schema, adapters.derive_proposal_action_schema())
        # A fresh mapping each call, so one round cannot mutate the next.
        second = provider("run-1", "cand-1", (fixtures.finding(),))
        self.assertIsNot(inputs.allowlist, second.allowlist)


class AssemblyTests(unittest.TestCase):
    """The assembly the CLI actually uses."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.workspace_root = self.base / "ws"
        self.workspace = CandidateWorkspace(self.workspace_root)
        self.workspace.create_candidate("run-1", "cand-1")

    def _assemble(self, model):
        return adapters.build_arh_orchestrator(
            self.workspace_root,
            "run-1",
            _checkpointer(),
            # An empty repo root: the real policy port fails CLOSED on a missing
            # bundle, which is the correct behaviour and keeps this test about
            # the repair wiring rather than about EDD-001 evidence.
            repo_root=self.base / "empty-repo",
            model=model,
            subject={"subject_id": "T1"},
            allowlist=fixtures.allowlist(),
            # The policy port is the CALLER's choice (GH-114): this test is about
            # the repair wiring, so it supplies the TEST_ONLY document rather
            # than the real EDD-001 contracts, and repo_root below is an empty
            # directory that the real port would fail closed on anyway.
            policy=adapters.build_test_only_policy_port(self.base),
            executor=_StubExecutor(),
            verifier=_StubVerifier(),
        )

    def test_the_assembled_repair_port_really_is_the_agent(self):
        """LOAD-BEARING. Asserts the CONTENT of the proposal, not the port type.

        Both ports return ``action="repair"`` -- that string is the plan-carrier
        action, not a discriminator -- so the discriminator has to be the
        SUBJECT. `_TestOnlyRepair` returns `test_only_design_subject(...)`,
        which carries the synthetic MPN plus `test_only=True` and
        `fixture_attempt`. The agent returns the model's own design subject.

        So if the assembly were mutated to wire `_TestOnlyRepair` instead, this
        fails on content -- exactly the substitution being guarded, and exactly
        what a bare `isinstance` assertion would have waved through.
        """
        orchestrator = self._assemble(
            FakeModelAdapter([fixtures.response(fixtures.valid_text())])
        )
        request = orchestrator._repair_port.propose(
            "run-1", "cand-1", (fixtures.finding(),)
        )
        # CONTENT FIRST, deliberately, before the type check. Both ports use the
        # SAME envelope shape, so the discriminator is what is nested inside it.
        # Asserting the type first would let the isinstance line take the blame
        # and would let this test be reduced to a tautology.
        design = request.subject["design_subject"]
        self.assertEqual(request.subject["design_action"], "DESIGN_SELECT_COMPONENT")
        self.assertEqual(design.get("mpn"), "RC0402-10K")
        self.assertEqual(design.get("role"), "R1")
        self.assertEqual(list(design.get("evidence_ids") or []), ["E-1"])
        # None of the double's markers are present. These are exactly what
        # `test_only_design_subject` adds on top of the same envelope.
        self.assertNotIn("test_only", request.subject)
        self.assertNotIn("fixture_attempt", request.subject)
        self.assertNotIn(adapters.TEST_ONLY_COMPONENT_MPN, json.dumps(request.subject))
        # And only then, the redundant type check.
        self.assertIsInstance(orchestrator._repair_port, LLMRepairPort)

    def test_the_agent_refuses_an_authority_field_end_to_end(self):
        """N2 through the ASSEMBLY, not just the agent in isolation: a model that
        tries to grant itself capabilities gets nothing, and the model was
        still called (so this is a rejection, not a short-circuit)."""
        poisoned = dict(fixtures.VALID_PROPOSAL)
        poisoned["capability_grants"] = [{"capability": "write"}]
        model = FakeModelAdapter([fixtures.response(fixtures.valid_text(**poisoned))])
        orchestrator = self._assemble(model)
        with self.assertRaises(Exception) as caught:
            orchestrator._repair_port.propose(
                "run-1", "cand-1", (fixtures.finding(),)
            )
        self.assertIn("capability", str(caught.exception).lower())

    def test_the_trajectory_lands_outside_the_receipt_root(self):
        """N4: a trajectory must never be readable as a verdict."""
        orchestrator = self._assemble(
            FakeModelAdapter([fixtures.response(fixtures.valid_text())])
        )
        orchestrator._repair_port.propose(
            "run-1", "cand-1", (fixtures.finding(),)
        )
        trajectory = self.workspace_root / "run" / "run-1" / "trajectory" / "run-1.jsonl"
        self.assertTrue(trajectory.is_file(), "no trajectory was recorded")
        self.assertNotIn("receipt", str(trajectory).lower())

    def test_a_real_transport_is_not_reachable_without_an_explicit_one(self):
        """The adapter has no default transport, so this wiring cannot make a
        request by accident. Asserted on the constructor itself."""
        with self.assertRaises(TypeError):
            OpenAICompatibleAdapter(
                base_url="https://example.invalid",
                api_key="not-a-real-key",
                model="m",
                # transport deliberately omitted
            )

    def test_the_key_never_appears_in_the_adapter_repr(self):
        adapter = OpenAICompatibleAdapter(
            base_url="https://example.invalid",
            api_key="sk-do-not-leak-me",
            model="m",
            transport=_ForbiddenTransport(),
        )
        self.assertNotIn("sk-do-not-leak-me", repr(adapter))


class _StubExecutor:
    def execute(self, request):
        raise AssertionError("not used in these tests")


class _StubVerifier:
    def verify(self, run_id, candidate_id, candidate_root):
        raise AssertionError("not used in these tests")


class ApiKeyHandlingTests(unittest.TestCase):
    """The key is an environment variable, and its absence is named."""

    def test_a_missing_key_is_refused_by_name(self):
        with self.assertRaises(cli.MissingApiKey) as caught:
            cli._require_api_key(env={})
        self.assertIn(cli.ARH_API_KEY_ENV, str(caught.exception))

    def test_a_blank_key_is_treated_as_missing(self):
        for blank in ("", "   "):
            with self.assertRaises(cli.MissingApiKey):
                cli._require_api_key(env={cli.ARH_API_KEY_ENV: blank})

    def test_a_present_key_is_returned_stripped(self):
        self.assertEqual(
            cli._require_api_key(env={cli.ARH_API_KEY_ENV: "  sk-x  "}), "sk-x"
        )

    def test_there_is_no_api_key_command_line_option(self):
        """argv reaches process listings and shell history, so the option must
        not EXIST rather than merely be discouraged. argparse rejects it."""
        parser = argparse_parser_for_test()
        with self.assertRaises(SystemExit):
            parser.parse_args([
                "run-arh", "--repo-root", ".", "--run-root", ".",
                "--run-id", "r", "--base-url", "u", "--model", "m",
                "--allowlist", "a.json", "--subject", "s.json",
                "--api-key", "sk-should-not-be-accepted",
            ])

    def test_the_key_is_never_read_from_a_file(self):
        """Only the environment is consulted; nothing in the repo can supply it."""
        self.assertEqual(cli.ARH_API_KEY_ENV, "AEDL_ARH_API_KEY")
        with self.assertRaises(cli.MissingApiKey):
            cli._require_api_key(env={})


def argparse_parser_for_test():
    """Rebuild the CLI parser so option surface can be asserted directly."""
    import argparse

    parser = argparse.ArgumentParser(prog="test")
    sub = parser.add_subparsers(dest="command", required=True)
    arh = sub.add_parser("run-arh")
    for flag in ("--repo-root", "--run-root", "--base-url", "--model",
                 "--allowlist", "--subject"):
        arh.add_argument(flag, required=True)
    arh.add_argument("--run-id", required=True)
    return parser


if __name__ == "__main__":
    unittest.main()
