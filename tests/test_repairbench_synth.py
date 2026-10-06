# -*- coding: utf-8 -*-
"""Regression tests for RepairBench missing-part synthesis.

These lock in the facts that took several rounds to establish, so a future change to
akcli or to the verifier cannot quietly break them again.
"""
import io
import json
import os
import re
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools import repairbench as rb  # noqa: E402
from tools import repairbench_synth as synth  # noqa: E402
from tools import akcli_identity  # noqa: E402

CONTRACT = json.loads(rb.CONTRACT_PATH.read_text(encoding="utf-8"))
SOURCE = synth.DEFAULT_SOURCE
# None on a host without the writer: these tests then skip with a reason that
# names how to supply it, instead of erroring on an attribute of None or on a
# generic "not available" that a reviewer cannot act on.
AKCLI = synth.AKCLI
NEEDS_AKCLI = akcli_identity.missing_reason("op-batch synthesis")


def statuses(raw):
    return rb.rule_statuses(CONTRACT, raw)[0]


def read_bytes(path):
    with io.open(path, "rb") as fh:
        return fh.read()


def read_json(path):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


@unittest.skipUnless(AKCLI is not None, NEEDS_AKCLI)
class MissingPartSynthesis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not SOURCE.exists():
            raise unittest.SkipTest("frozen M2 schematic not present")
        cls.dest, cls.placement = synth.synthesise_fault(
            SOURCE, "R9", statuses, rb.observe_source, AKCLI)

    def test_fault_fails_target_rule_only(self):
        """The whole value of an episode: target fails, nothing else moves."""
        st = statuses(self.dest.read_bytes())
        self.assertEqual(st["ESP32_GPIO9_PULLUP"], "fail")
        for rule in ("ESP32_EN_RC", "SHT30_ADDRESS", "SHT30_UNUSED_PINS",
                     "USB_POLARITY_AND_SERIES"):
            self.assertEqual(st[rule], "pass", rule)

    def test_fault_board_parses(self):
        """No orphaned labels: the verifier must not fail closed."""
        rb.observe_source(self.dest.read_bytes())

    def test_placement_record_is_self_contained(self):
        """A solver gets the part and its pin geometry without any answer key."""
        p = self.placement
        self.assertEqual([c["reference"] for c in p["components"]], ["R9"])
        self.assertEqual(p["components"][0]["lib_id"], "Device:R")
        self.assertEqual(p["components"][0]["value"], "10k")
        self.assertEqual(len(p["pin_points_nm"]["R9"]), 2)
        self.assertTrue(p["labels"])

    def test_repair_closes_the_loop(self):
        """Place plus native labels restores every rule."""
        st = synth.repair(self.dest, self.placement, statuses, rb.observe_source, AKCLI)
        for rule, value in st.items():
            self.assertEqual(value, "pass", rule)

    def test_repaired_board_is_stable(self):
        """Repaired twice in a row must not drift or start failing."""
        first = synth.repair(self.dest, self.placement, statuses, rb.observe_source, AKCLI)
        second = synth.repair(self.dest, self.placement, statuses, rb.observe_source, AKCLI)
        self.assertEqual(first, second)


class SymbolGeometry(unittest.TestCase):
    """Facts about the frozen board that do not need akcli."""

    def setUp(self):
        if not SOURCE.exists():
            self.skipTest("frozen M2 schematic not present")

    def test_device_r_pin_axis_is_y(self):
        text = SOURCE.read_text(encoding="utf-8", errors="replace")
        offsets = synth.symbol_pin_offsets(text, "Device:R")
        self.assertEqual(len(offsets), 2)
        for _number, dx, dy in offsets:
            self.assertEqual(dx, 0.0, "Device:R pins must share one x offset")
            self.assertNotEqual(dy, 0.0, "Device:R pins must be offset in y")

    def test_native_label_block_matches_frozen_shape(self):
        block = synth.native_label_block("+3V3", (34290000, 254000000))
        self.assertIn('(label "+3V3" (at 34.29 254.00 0)', block)
        self.assertIn("(justify left bottom)", block)
        self.assertIn("(uuid \"", block)


class CapabilityBound(unittest.TestCase):
    """Documents the akcli v1 gap this module exists to work around."""

    def test_native_label_block_uses_only_primitives_the_verifier_knows(self):
        """The verifier accepts labels only on pin points or wire endpoints.

        A label written here must therefore carry an explicit point, because there is no
        akcli op that can. This test fails if someone replaces the native writer with an
        add_net_label call, which silently drops its at field.
        """
        block = synth.native_label_block("BOOT", (34290000, 261620000))
        self.assertNotIn("add_net_label", block)
        self.assertIn("(at 34.29 261.62", block)


class GeneratedEpisodeIntegrity(unittest.TestCase):
    """Locks DC-06 against the exact failure mode that produced it.

    The first generation run verified the answer key by calling repair() on the fixture
    itself, which silently rewrote the fault into an already-repaired board. The episode
    then scored UNKNOWN because the target rule already passed before any attempt. These
    tests exist so that a regenerated or repaired DC-06 can never be committed again.
    """

    EPISODE = REPO_ROOT + "/tests/fixtures/repair_pr1/native/DC-06"
    RULE = "USB_POLARITY_AND_SERIES"

    def setUp(self):
        if not os.path.isfile(self.EPISODE + "/fault.kicad_sch"):
            self.skipTest("DC-06 not generated")
        # This class proves the withheld answer key really repairs a copy, which
        # is a claim about the writer's behaviour, not about our code paths.
        if AKCLI is None:
            self.skipTest(NEEDS_AKCLI)

    def test_fixture_is_still_a_fault(self):
        st = statuses(read_bytes(self.EPISODE + "/fault.kicad_sch"))
        self.assertEqual(st[self.RULE], "fail",
                         "DC-06 fault.kicad_sch must still fail its target rule")
        for rule, value in st.items():
            if rule != self.RULE:
                self.assertEqual(value, "pass", rule)

    def test_answer_key_repairs_a_copy(self):
        ops = read_json(self.EPISODE + "/repair_ops.json")
        labels = read_json(self.EPISODE + "/native_labels.json")

        before = statuses(read_bytes(self.EPISODE + "/fault.kicad_sch"))
        self.assertEqual(before[self.RULE], "fail")

        import shutil
        import tempfile
        tmp = tempfile.mkdtemp()
        copy_path = os.path.join(tmp, "probe.kicad_sch")
        shutil.copyfile(self.EPISODE + "/fault.kicad_sch", copy_path)
        rc, out = synth._akcli_draw(copy_path, ops["ops"], AKCLI)
        self.assertEqual(rc, 0, out[:300])
        synth.write_native_labels(copy_path, [(e["name"], tuple(e["point_nm"]))
                                             for e in labels])
        after = statuses(read_bytes(copy_path))
        self.assertEqual(after[self.RULE], "pass")
        for rule, value in after.items():
            self.assertEqual(value, "pass", rule)

        # the fixture must be untouched by any of this
        again = statuses(read_bytes(self.EPISODE + "/fault.kicad_sch"))
        self.assertEqual(again, before, "verification must never mutate the fixture")


class EpisodeGovernance(unittest.TestCase):
    """Input-governance and scope gates that must run on every host, writer or not.

    Measured 2026-10-07: DC-06's `placement.json` held a `labels` array identical to
    `native_labels.json` -- the sidecar the oracle arm applies -- and its fault board
    contains zero occurrences of those four net names, so the public input was not merely
    helpful, it was the only proposer-visible source of the answer. Both model arms were
    handed it, and the episode sat in the headline denominator. The gates below are what
    makes that state impossible to re-commit, and they are deliberately free of any
    dependency on the external writer: the class that held DC-06's earlier key-name check
    skipped on a writer-less host, so CI never ran it.
    """

    EPISODES = read_json(REPO_ROOT + "/benchmarks/repairbench_v0_1/episodes_v1.json")

    @staticmethod
    def _oracle_names(episode_id):
        path = ("%s/tests/fixtures/repair_pr1/native/%s/native_labels.json"
                % (REPO_ROOT, episode_id))
        return {e["name"] for e in read_json(path)} if os.path.isfile(path) else set()

    def test_projection_keeps_only_granted_geometry(self):
        record = {"components": [{"reference": "R7"}], "pin_points_nm": {"R7": {}},
                  "labels": [{"name": "USB_DP", "point_nm": [0, 0]}],
                  "whatever_comes_next": True}
        self.assertEqual(sorted(synth.PUBLIC_PLACEMENT_FIELDS),
                         ["components", "pin_points_nm"])
        self.assertEqual(sorted(synth.public_placement(record)),
                         ["components", "pin_points_nm"])

    def test_published_files_hold_no_oracle_net_name(self):
        for episode in self.EPISODES["episodes"]:
            public = episode.get("public_input")
            if not public:
                continue
            with self.subTest(episode=episode["id"]):
                payload = read_json(REPO_ROOT + "/" + public)
                self.assertTrue(set(payload) <= set(synth.PUBLIC_PLACEMENT_FIELDS),
                                "%s publishes %s" % (public, sorted(payload)))
                text = json.dumps(payload, ensure_ascii=False)
                leaked = {v for v in _quoted_values(text)} & self._oracle_names(episode["id"])
                self.assertFalse(leaked, "public input repeats oracle net names: %s"
                                 % sorted(leaked))

    def test_scored_answer_is_recoverable_from_the_board(self):
        """A scored episode must not need its public input to name the answer.

        `aedl_contract` receives the contract's expected pin/net intent while
        `baseline_generic` receives only `fault_summary`, so a net name written on the
        board is common ground and a name that exists only in the withheld key is not.
        Excluding such an episode has to be recorded in its scope_note, or the flag is
        decoration.
        """
        for episode in self.EPISODES["episodes"]:
            names = self._oracle_names(episode["id"])
            if not names:
                continue
            board = read_bytes("%s/tests/fixtures/repair_pr1/native/%s/fault.kicad_sch"
                               % (REPO_ROOT, episode["id"])).decode("utf-8", "replace")
            missing = sorted(name for name in names if name not in board)
            if episode["in_scope_v0_1"]:
                self.assertEqual(missing, [], "%s is scored but names %s appear in no "
                                              "public material" % (episode["id"], missing))
            else:
                self.assertTrue(
                    not missing or "public" in episode["scope_note"].lower(),
                    "%s withheld from scoring without recording why" % episode["id"])

    def test_dc06_is_out_of_scope_for_a_recorded_reason(self):
        episode = next(e for e in self.EPISODES["episodes"] if e["id"] == "DC-06")
        self.assertFalse(episode["in_scope_v0_1"],
                         "DC-06 stays out of the headline while its answer names are "
                         "absent from every public source")
        self.assertFalse(episode["solvable_from_frozen_source"])
        self.assertIn("USB_DP", episode["scope_note"])

    def test_duplicate_in_scope_episodes_are_rejected(self):
        """Two in-scope episodes must not be the same fault on the same rule.

        Lives in this ungated class on purpose: it inspects only committed fixtures, but
        while it sat in `MultiPartEpisode` a writer-less host skipped the whole class and
        CI never ran this guard. The key includes fault_family on purpose: DC-01 and DC-09
        both target USB_POLARITY_AND_SERIES in the same family and are legitimate, because
        a mislabelled pair and a single deleted connector-side label are different defects
        at pin level. What must never happen is the same family, same rule and same
        pin-level signature twice -- the near-copy DC-06 was when it duplicated DC-04.
        """
        episodes = self.EPISODES["episodes"]

        def pin_nets(raw):
            out = {}
            for part in rb.observe_source(raw)["partitions"]:
                names = part.get("names") or []
                label = "/".join(sorted(names)) if names else ""
                for member in part["members"]:
                    if member.get("reference"):
                        out["%s.%s" % (member["reference"], member.get("number"))] = label
            return out

        pristine = pin_nets(read_bytes(str(synth.DEFAULT_SOURCE)))

        def signature(raw):
            """Pin-level defect fingerprint: which pins changed net, and how.

            Three earlier key shapes were all proxies and each produced a confident wrong
            answer: rule plus failing set flagged DC-06 against DC-01; adding fault_family
            flagged DC-07 against DC-02; net-name difference flagged DC-09 against DC-01.
            Pin-level mapping is the measure the contract actually scores.
            """
            fault = pin_nets(raw)
            return frozenset(
                (pin, fault.get(pin, ""), pristine.get(pin, ""))
                for pin in set(fault) | set(pristine)
                if fault.get(pin, "") != pristine.get(pin, ""))

        seen = {}
        for episode in episodes:
            if not episode.get("in_scope_v0_1"):
                continue
            sig = signature(read_bytes(os.path.join(REPO_ROOT, episode["fixture"])))
            key = (episode["fault_family"], episode["target_rule"], sig)
            self.assertNotIn(key, seen,
                             "%s duplicates %s at pin level" % (episode["id"],
                                                                seen.get(key)))
            seen[key] = episode["id"]


def _quoted_values(text):
    """Every quoted string in a JSON document, for oracle-name comparison."""
    return {m.group(1) for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', text)}


class MultiPartEpisode(unittest.TestCase):
    """The USB series rule asserts a pair, which single-part synthesis gets wrong.

    Deleting R7 alone breaks USB_POLARITY_AND_SERIES, and placing R7 back does not
    satisfy it, because R8 is required too. So the episode has to be the pair. And
    deleting a part deletes the labels on all of its nets, including the ones at the far
    end on other components, so a repair that restores only the pin-sitting labels leaves
    the net unnamed and the rule still fails.
    """

    REFS = ["R7", "R8"]
    RULE = "USB_POLARITY_AND_SERIES"

    @classmethod
    def setUpClass(cls):
        if not SOURCE.exists():
            raise unittest.SkipTest("frozen M2 schematic not present at %s" % SOURCE)
        if AKCLI is None:
            raise unittest.SkipTest(akcli_identity.missing_reason("fault synthesis"))
        cls.dest, cls.placement = synth.synthesise_fault(
            SOURCE, cls.REFS, statuses, rb.observe_source, AKCLI)

    def test_pair_fault_fails_only_the_target_rule(self):
        st = statuses(self.dest.read_bytes())
        self.assertEqual(sorted(k for k, v in st.items() if v == "fail"), [self.RULE])

    def test_both_parts_are_removed(self):
        text = self.dest.read_text(encoding="utf-8", errors="replace")
        for ref in self.REFS:
            self.assertNotIn('"%s"' % ref, text, ref)

    def test_repair_restores_every_deleted_label(self):
        """Not only the labels on the restored pins."""
        st = synth.repair(self.dest, self.placement, statuses, rb.observe_source, AKCLI)
        for rule, value in st.items():
            self.assertEqual(value, "pass", rule)
        pin_points = set()
        for points in self.placement["pin_points_nm"].values():
            pin_points.update(tuple(p) for p in points.values())
        on_pins = [tuple(e["point_nm"]) for e in self.placement["labels"]
                   if tuple(e["point_nm"]) in pin_points]
        self.assertLess(len(on_pins), len(self.placement["labels"]),
                        "this episode must exercise labels beyond the restored pins")


class LabelFaultSynthesis(unittest.TestCase):
    """connectivity_label episodes: delete one label that exactly one rule depends on.

    These are the cheapest honest episodes available because the frozen board already
    satisfies every rule, so removing one label gives a fault that violates that rule and
    nothing else. Measured on the M2 board: 15 of 72 labels qualify, spread across all
    four rules.
    """

    RULES = ["SHT30_ADDRESS", "ESP32_EN_RC", "USB_POLARITY_AND_SERIES"]

    @classmethod
    def setUpClass(cls):
        if not SOURCE.exists():
            raise unittest.SkipTest("frozen M2 schematic not present at %s" % SOURCE)
        if AKCLI is None:
            raise unittest.SkipTest(akcli_identity.missing_reason("fault synthesis"))

    def test_each_rule_has_a_clean_single_label_fault(self):
        for rule in self.RULES:
            with self.subTest(rule=rule):
                dest, record = synth.synthesise_label_fault(
                    SOURCE, rule, statuses, rb.observe_source, AKCLI)
                st = statuses(dest.read_bytes())
                self.assertEqual(sorted(k for k, v in st.items() if v == "fail"), [rule])
                self.assertEqual(record["broken_rule"], rule)
                self.assertTrue(record["label"])
                self.assertEqual(len(record["point_nm"]), 2)

    def test_label_fault_restores_cleanly(self):
        for rule in self.RULES:
            with self.subTest(rule=rule):
                dest, record = synth.synthesise_label_fault(
                    SOURCE, rule, statuses, rb.observe_source, AKCLI)
                st = synth.repair_label(dest, record, statuses, rb.observe_source, AKCLI)
                for name, value in st.items():
                    self.assertEqual(value, "pass", "%s: %s" % (rule, name))
                # repair_label writes in place, so the board is now correct; the
                # assertion that the *fixture* is untouched lives in the DC-06 tests.
                again = statuses(dest.read_bytes())
                self.assertEqual([k for k, v in again.items() if v == "fail"], [])

    def test_in_scope_set_covers_both_families(self):
        episodes = read_json("%s/benchmarks/repairbench_v0_1/episodes_v1.json" % REPO_ROOT)["episodes"]
        in_scope = [e for e in episodes if e.get("in_scope_v0_1")]
        families = {e["fault_family"] for e in in_scope}
        self.assertEqual(families, {"connectivity_label", "add_component"})
        self.assertGreaterEqual(len(in_scope), 4,
                                "headline denominator must not shrink below 4")


if __name__ == "__main__":
    unittest.main()