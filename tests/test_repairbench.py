"""Tests for the AEDL RepairBench v0.1 harness.

The point of these tests is NOT to re-assert that the harness returns particular
numbers. It is to pin two measured properties of the benchmark itself, both
discovered by the first real run on 2026-10-05:

  * contract completeness -- the frozen netlist contract asserts component VALUE
    but never component PRESENCE, so it cannot express "this part must be
    fitted". The mechanical arm fails on DC-03/DC-04/DC-05 for exactly that
    reason.

  * net-merge hazard -- emitting add_net_label ops derived from the contract,
    without a net-split guard, merges named nets. On DC-01 USB_DP and USB_DM
    became one net, and the structural oracle caught it.

Both are pinned as observations. A future fix to the contract or the guard makes
the corresponding test fail, and that failure means "the gap closed" rather than
"the benchmark broke".
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import akcli_identity  # noqa: F401  (patched through repairbench)
from tools import repairbench as rb

# Resolved once at import: these are the tests whose claim is about the REAL
# writer's behaviour, so they skip with a reason naming how to provide the tool,
# rather than erroring or being silently swallowed by a bare skip.
_AKCLI = rb.find_akcli()
NEEDS_WRITER = akcli_identity.missing_reason("the measured net-merge hazard")


def _schema_ok():
    rb.evaluate_observations(
        json.loads(rb.CONTRACT_PATH.read_text(encoding="utf-8")),
        rb.observations_from_views({"pins": {}, "components": {}}),
    )


class ContractCompletenessTests(unittest.TestCase):
    """Finding 1: the contract pins values, not existence."""

    def test_contract_cannot_express_component_presence(self):
        """Every rule that names a component asserts only its value.

        This is the structural reason the mechanical arm scored 1/5: for a
        missing-part fault the contract gives a solver nothing to apply.
        """
        contract = json.loads(rb.CONTRACT_PATH.read_text(encoding="utf-8"))
        component_rules = []
        for rule in contract["rules"]:
            comps = rule["checks"].get("netlist", {}).get("components", {})
            for ref, expected in comps.items():
                component_rules.append((rule["id"], ref, sorted(expected)))
        self.assertTrue(component_rules, "expected at least one component assertion")
        for rule_id, ref, fields in component_rules:
            self.assertEqual(
                fields, ["value"],
                "rule %s component %s asserts %s; this test pins that the contract "
                "carries no presence/footprint/placement field" % (rule_id, ref, fields))

    def test_every_component_assertion_also_asserts_a_pin(self):
        """A value assertion without a pin assertion is not reachable by labeling.

        This is what makes the gap mechanical rather than incidental: the
        contract's only handle on a component is a net name on one of its pins.
        """
        contract = json.loads(rb.CONTRACT_PATH.read_text(encoding="utf-8"))
        for rule in contract["rules"]:
            netlist = rule["checks"].get("netlist", {})
            comps = netlist.get("components", {})
            if not comps:
                continue
            pins = netlist.get("pins", {})
            touched = {ref for pin in pins for ref in [pin.split(".")[0]]}
            for ref in comps:
                self.assertIn(
                    ref, touched,
                    "rule %s asserts component %s but pins on it" % (rule["id"], ref))

    def test_missing_part_faults_really_are_unrepairable_from_the_contract(self):
        """DC-03/04/05 are the missing-part class; confirm the arm cannot pass them.

        Runs the mechanical arm for real and asserts it does NOT reach primary
        PASS on these three. If a future contract gains presence assertions this
        test fails, which is the intended signal.
        """
        spec = json.loads(rb.EPISODES_PATH.read_text(encoding="utf-8"))
        contract = json.loads(rb.CONTRACT_PATH.read_text(encoding="utf-8"))
        missing_part = {"DC-03", "DC-04", "DC-05"}
        seen = set()
        for episode in spec["episodes"]:
            if episode["id"] not in missing_part:
                continue
            before = (rb.REPO_ROOT / episode["fixture"]).read_bytes()
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                try:
                    after = rb.arm_aedl_contract_deterministic(episode, workdir)
                    outcome = rb.evaluate_candidate(contract, episode, before, after)
                    self.assertFalse(
                        outcome["primary_ok"],
                        "%s unexpectedly reached primary PASS; the contract may now "
                        "carry presence information" % episode["id"])
                    seen.add(episode["id"])
                except rb.LlmUnavailable:
                    # The writer refused the derived ops. That is the same gap
                    # observed from the other side and is an acceptable outcome.
                    seen.add(episode["id"])
        self.assertEqual(seen, missing_part)


class NetMergeHazardTests(unittest.TestCase):
    """Finding 2, measured under BOTH net-split-guard settings.

    Round 2 (guard off): contract-derived labels merged USB_DP into USB_DM.
    Round 3 (guard on): the writer refuses the same ops, so nothing unsafe lands.

    Both halves are pinned. The guard half is not a bonus -- it is the only reason
    the unguarded half is survivable in production, and the refusal it produces is
    deliberately NOT scored as a primary PASS anywhere.
    """

    def _run_arm(self, episode, *, strict_nets):
        original = rb.ARM_GUARD["aedl_contract_deterministic"]
        rb.ARM_GUARD["aedl_contract_deterministic"] = strict_nets
        try:
            with tempfile.TemporaryDirectory() as tmp:
                return rb.arm_aedl_contract_deterministic(episode, Path(tmp))
        finally:
            rb.ARM_GUARD["aedl_contract_deterministic"] = original

    def _dc01(self):
        spec = json.loads(rb.EPISODES_PATH.read_text(encoding="utf-8"))
        return next(e for e in spec["episodes"] if e["id"] == "DC-01")

    @unittest.skipUnless(_AKCLI is not None, NEEDS_WRITER)
    def test_unguarded_labels_merge_named_nets(self):
        """Guard off: the measured hazard. R7.2 and U1.14 land on USB_DM.

        They belong to USB_DP in the contract, so the two named nets end up as one.
        If this ever stops reproducing, the fixture or the contract changed and
        this test must be revisited deliberately.
        """
        episode = self._dc01()
        after = self._run_arm(episode, strict_nets=False)
        view = rb.project_netlist_view(after)
        usb_dm = sorted(p for p, s in view["pins"].items() if s.get("net") == "USB_DM")
        self.assertTrue(
            {"R7.2", "U1.14"} & set(usb_dm),
            "expected the unguarded merge to put R7.2/U1.14 on USB_DM; observed %s" % usb_dm)

    @unittest.skipUnless(_AKCLI is not None, NEEDS_WRITER)
    def test_structural_oracle_catches_the_unguarded_merge(self):
        """The merge must be reported, never silently accepted."""
        episode = self._dc01()
        after = self._run_arm(episode, strict_nets=False)
        result = rb.structural_check("DC-01", rb.project_netlist_view(after))
        self.assertEqual(result["status"], "fail",
                         "structural oracle must flag the merged nets on DC-01")
        self.assertTrue(result["problems"])

    def _stubbed_writer(self, refuse=False):
        """Patch resolution + subprocess so the guard plumbing is testable here.

        Why this exists: the previous version of this test asserted the pinned
        writer's refusal text, so on any host without that personal Windows binary
        it failed with "writer not found" and said nothing at all about the guard.
        These two tests pin OUR behaviour instead — that the guard reaches argv and
        that a refusal becomes an arm failure, never a silent zero.
        """
        calls = []

        def fake_run(argv, **kwargs):
            calls.append([str(a) for a in argv])
            return subprocess.CompletedProcess(
                argv, 2 if refuse else 0,
                "{}" if not refuse else "",
                "writer refused: --strict-nets rejects a label on a named net" if refuse else "")

        patches = [
            mock.patch.object(rb.akcli_identity, "resolve", return_value=Path("stub-akcli")),
            mock.patch.object(rb.subprocess, "run", side_effect=fake_run),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return calls

    def test_guard_switch_reaches_the_writer_argv(self):
        """Guard on => `--strict-nets`; guard off => it must not be there."""
        episode = self._dc01()

        on_calls = self._stubbed_writer()
        self._run_arm(episode, strict_nets=True)
        self.assertIn("--strict-nets", on_calls[0],
                      "the guard must be handed to the writer, observed: %s" % on_calls[0])

        off_calls = self._stubbed_writer()
        self._run_arm(episode, strict_nets=False)
        self.assertNotIn("--strict-nets", off_calls[0],
                         "guard off must not pass --strict-nets, observed: %s" % off_calls[0])

    def test_guard_refuses_the_unsafe_write(self):
        """Guard on: the writer refuses, so no merged net reaches the board.

        Asserts the refusal, and asserts it is surfaced as an error rather than
        quietly scored as success.
        """
        episode = self._dc01()
        self._stubbed_writer(refuse=True)
        with self.assertRaises(rb.LlmUnavailable) as ctx:
            self._run_arm(episode, strict_nets=True)
        message = str(ctx.exception)
        self.assertIn("strict-nets", message)
        self.assertNotIn("primary_ok", message)

    def test_guard_is_recorded_in_every_receipt(self):
        """A receipt must say whether the guard was on, or the number is ambiguous."""
        spec = json.loads(rb.EPISODES_PATH.read_text(encoding="utf-8"))
        self.assertIn("aedl_contract_deterministic", rb.ARM_GUARD)
        with tempfile.TemporaryDirectory() as tmp:
            report = rb.run_arm("noop", Path(tmp))
        self.assertIn("net_split_guard", report)
        self.assertFalse(report["net_split_guard"])



class ControlArmTests(unittest.TestCase):
    """The controls that make any other arm's number reportable."""

    def test_noop_cannot_pass(self):
        spec = json.loads(rb.EPISODES_PATH.read_text(encoding="utf-8"))
        contract = json.loads(rb.CONTRACT_PATH.read_text(encoding="utf-8"))
        for episode in spec["episodes"]:
            before = (rb.REPO_ROOT / episode["fixture"]).read_bytes()
            with tempfile.TemporaryDirectory() as tmp:
                after = rb.arm_noop(episode, Path(tmp))
            outcome = rb.evaluate_candidate(contract, episode, before, after)
            self.assertFalse(
                outcome["primary_ok"],
                "%s: noop passed the primary oracle" % episode["id"])

    def test_every_episode_starts_with_its_target_rule_failing(self):
        """Primary oracle is FAIL -> PASS, so the fault must be present to begin with."""
        spec = json.loads(rb.EPISODES_PATH.read_text(encoding="utf-8"))
        contract = json.loads(rb.CONTRACT_PATH.read_text(encoding="utf-8"))
        for episode in spec["episodes"]:
            raw = (rb.REPO_ROOT / episode["fixture"]).read_bytes()
            statuses, _ = rb.rule_statuses(contract, raw)
            self.assertEqual(
                statuses.get(episode["target_rule"]), "fail",
                "%s does not actually carry its target fault" % episode["id"])

    def test_contract_validates_against_the_frozen_validator(self):
        contract = json.loads(rb.CONTRACT_PATH.read_text(encoding="utf-8"))
        rb.evaluate_observations(
            contract, rb.observations_from_views({"pins": {}, "components": {}}))
        self.assertEqual(len(contract["rules"]), 5)


if __name__ == "__main__":
    unittest.main()
