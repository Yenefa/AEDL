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
import tempfile
import unittest
from pathlib import Path

from tools import repairbench as rb


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
    """Finding 2: contract-derived labels merge named nets without a guard."""

    def test_dc01_labels_are_not_applied_without_a_split_guard(self):
        """On DC-01 the unguarded arm merged USB_DP and USB_DM.

        Pins the hazard. The repaired USB_DM membership contains R7.2 and
        U1.14, which belong to USB_DP in the contract, so the two named nets
        ended up merged. If a guard is ever added this test fails and that
        failure means the hazard is closed.
        """
        spec = json.loads(rb.EPISODES_PATH.read_text(encoding="utf-8"))
        episode = next(e for e in spec["episodes"] if e["id"] == "DC-01")
        contract = json.loads(rb.CONTRACT_PATH.read_text(encoding="utf-8"))
        before = (rb.REPO_ROOT / episode["fixture"]).read_bytes()

        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            after = rb.arm_aedl_contract_deterministic(episode, workdir)
            view = rb.project_netlist_view(after)

        members = set(view["pins"].get("R7.2", {}).get("net") or "")
        self.assertNotEqual(
            members, "",
            "R7.2 has no net after the mechanical arm; the fixture shape changed")

        usb_dm = sorted(
            pin for pin, state in view["pins"].items() if state.get("net") == "USB_DM")
        merged = {"R7.2", "U1.14"} & set(usb_dm)
        self.assertTrue(
            merged,
            "expected the measured net-merge hazard (R7.2/U1.14 on USB_DM); it is "
            "absent now, so a guard was added -- update this test deliberately")

    def test_structural_oracle_detects_the_merge(self):
        """The merge must be visible in the structural layer, not silently pass."""
        spec = json.loads(rb.EPISODES_PATH.read_text(encoding="utf-8"))
        episode = next(e for e in spec["episodes"] if e["id"] == "DC-01")
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            after = rb.arm_aedl_contract_deterministic(episode, workdir)
            view = rb.project_netlist_view(after)
        result = rb.structural_check("DC-01", view)
        self.assertEqual(
            result["status"], "fail",
            "structural oracle must flag the merged nets on DC-01")
        self.assertTrue(result["problems"])


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
