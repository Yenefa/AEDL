"""Bounded scope checks and opt-in real native episode, never network in tests."""
import copy
import os
import tempfile
import unittest
from pathlib import Path

from aedl_sandbox.nativeports import DOMAIN, INITIAL_SUBJECT, NativeEpisodePolicy
from aedl_sandbox.protocol import PolicyRequest, Outcome


class NativeScopeTests(unittest.TestCase):
    def evaluate(self, subject, action="execute_candidate", domain=DOMAIN):
        return NativeEpisodePolicy().evaluate(PolicyRequest("r", domain, "a", action,
                                                            Path("."), subject))

    def test_initial_fault_and_scoped_repair_allowed(self):
        self.assertEqual(self.evaluate(INITIAL_SUBJECT).outcome, Outcome.ALLOW)
        subject = copy.deepcopy(INITIAL_SUBJECT)
        subject["design_subject"]["function"] = "GND"
        subject.pop("output_kind")
        self.assertEqual(self.evaluate(subject).outcome, Outcome.ALLOW)

    def test_foreign_pin_domain_kind_and_authority_are_refused(self):
        for field, value in (("pin", "U1.2"), ("function", "+3V3"),
                             ("approval_status", "APPROVED"), ("authority", "ALLOW")):
            with self.subTest(field=field):
                subject = copy.deepcopy(INITIAL_SUBJECT)
                subject["design_subject"][field] = value
                self.assertEqual(self.evaluate(subject).outcome, Outcome.BLOCKED)
        subject = copy.deepcopy(INITIAL_SUBJECT)
        subject["output_kind"] = "kicad_pcb"
        self.assertEqual(self.evaluate(subject).outcome, Outcome.BLOCKED)
        self.assertEqual(self.evaluate(INITIAL_SUBJECT, domain="EDD-001").outcome, Outcome.BLOCKED)
        self.assertEqual(self.evaluate(INITIAL_SUBJECT, action="promote").outcome, Outcome.BLOCKED)

    @unittest.skipUnless(os.environ.get("AEDL_EPISODE_NATIVE") == "1", "native tools require explicit opt-in")
    def test_native_control_repairs_actual_schematic_and_kills_frozen_initial_verifier(self):
        from tools.run_arh_episode import run_episode
        from aedl_sandbox.arh.model_adapter import FakeModelAdapter, ModelResponse, ModelUsage
        import json
        proposal = {"diagnosis": "SHT30_ADDRESS: U2.2 floating",
            "design_action": "DESIGN_ASSIGN_PIN", "design_subject": {
                "pin": "U2.2", "function": "GND", "approval_status": "NOT_REQUIRED"},
            "evidence_ids": ["SHT30_ADDRESS"], "locator": {"pin": "U2.2"}}
        with tempfile.TemporaryDirectory() as temp:
            summary = run_episode(Path(temp) / "episode", os.environ["AEDL_AKCLI_PYTHON"],
                os.environ["AEDL_KICAD_CLI"], FakeModelAdapter([
                    ModelResponse(json.dumps(proposal), ModelUsage(), "offline-control")]), real_model=False)
            self.assertEqual(summary["result"], "CONTROL_RUN")
            self.assertEqual([o["status"] for o in summary["observations"]], ["FAIL", "PASS"])
            self.assertEqual(summary["transactions"][0]["status"], "COMMITTED")
            self.assertNotEqual(summary["observations"][0]["source_sha256"],
                                summary["observations"][1]["source_sha256"])
            self.assertEqual(summary["model_budget"]["calls"], 1)
            self.assertFalse(summary["real_model"])
            self.assertFalse(summary["manufacturing_release"])
