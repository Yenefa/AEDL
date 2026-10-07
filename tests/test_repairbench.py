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
from tools import repairbench_synth as synth

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


class LlmArmInputGovernance(unittest.TestCase):
    """What the two model arms are actually handed, and under which guard they write.

    Both arms run the same model with the same writer, so the only admissible
    differences are the ones the benchmark declares: the AEDL arm sees the frozen
    contract rule, the baseline arm sees a written defect summary. Anything else --
    an answer key in the prompt, or one arm silently writing under the other's guard --
    makes the two numbers incomparable. Measured 2026-10-07 that DC-06's published
    placement.json repeated the withheld net labels, and `_llm_arm` read the guard from
    a hardcoded `ARM_GUARD["aedl_contract"]` key for both arms.
    """

    def _stubbed_llm(self, reply='{"ops": []}'):
        calls = {"writer": [], "prompt": []}

        def fake_run(argv, **kwargs):
            calls["writer"].append([str(a) for a in argv])
            return subprocess.CompletedProcess(argv, 0, "{}", "")

        def fake_prompt(system, user, base_url, model, key, **kw):
            calls["prompt"].append(user)
            return reply

        for patch in (
            mock.patch.object(rb.akcli_identity, "resolve", return_value=Path("stub-akcli")),
            mock.patch.object(rb.subprocess, "run", side_effect=fake_run),
            mock.patch.object(rb, "resolve_endpoint",
                              return_value=("http://stub.invalid/v1", "stub-key", "stub-model")),
            mock.patch.object(rb, "_repair_prompt", side_effect=fake_prompt),
            # _import_synth reloads the module from REPO_ROOT, which the scratch episode
            # redirects; the canonical import is the same code.
            mock.patch.object(rb, "_import_synth", return_value=synth),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        return calls

    def _episode_with_public_input(self, extra):
        """A scratch episode: fault board copied verbatim, public input authored by us."""
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        source = json.loads(rb.EPISODES_PATH.read_text(encoding="utf-8"))
        dc06 = next(e for e in source["episodes"] if e["id"] == "DC-06")
        shutil.copyfile(rb.REPO_ROOT / dc06["fixture"], tmp / "fault.kicad_sch")
        (tmp / "public.json").write_text(json.dumps(extra), encoding="utf-8")
        episode = dict(dc06, fixture="fault.kicad_sch", public_input="public.json")
        patch = mock.patch.object(rb, "REPO_ROOT", tmp)
        patch.start()
        self.addCleanup(patch.stop)
        return episode

    def test_answer_bearing_public_input_is_not_forwarded(self):
        """Even if a fixture ships net names, the prompt must not receive them."""
        episode = self._episode_with_public_input({
            "components": [{"reference": "R7", "x_mil": 8600, "y_mil": 7600}],
            "pin_points_nm": {"R7": {"1": [218440000, 189230000]}},
            "labels": [{"name": "USB_DP_CONN", "point_nm": [218440000, 189230000]}],
        })
        calls = self._stubbed_llm()
        rb.arm_baseline_generic(episode, Path(tempfile.mkdtemp()))
        self.assertEqual(len(calls["prompt"]), 1)
        sent = json.loads(calls["prompt"][0])
        self.assertEqual(sorted(sent["placement_record"]), ["components", "pin_points_nm"])
        self.assertNotIn("USB_DP_CONN", calls["prompt"][0],
                         "the withheld net name reached the model prompt")

    def test_each_llm_arm_uses_its_own_guard(self):
        """`baseline_generic` and `aedl_contract` must not share one guard key."""
        episode = self._episode_with_public_input({"components": [], "pin_points_nm": {}})
        original = dict(rb.ARM_GUARD)
        rb.ARM_GUARD.update({"baseline_generic": False, "aedl_contract": True})
        self.addCleanup(rb.ARM_GUARD.update, original)

        calls = self._stubbed_llm()
        rb.arm_baseline_generic(episode, Path(tempfile.mkdtemp()))
        rb.arm_aedl_contract(episode, Path(tempfile.mkdtemp()))
        self.assertEqual(len(calls["writer"]), 2)
        self.assertNotIn("--strict-nets", calls["writer"][0],
                         "baseline must write under its own guard, observed %s"
                         % calls["writer"][0])
        self.assertIn("--strict-nets", calls["writer"][1],
                      "aedl_contract must write under its own guard, observed %s"
                      % calls["writer"][1])

    def test_only_the_contract_arm_receives_the_contract_rule(self):
        episode = self._episode_with_public_input({"components": [], "pin_points_nm": {}})
        calls = self._stubbed_llm()
        rb.arm_baseline_generic(episode, Path(tempfile.mkdtemp()))
        rb.arm_aedl_contract(episode, Path(tempfile.mkdtemp()))
        baseline = json.loads(calls["prompt"][0])
        aedl = json.loads(calls["prompt"][1])
        self.assertIn("defect_hint", baseline)
        self.assertNotIn("frozen_contract_rule", baseline)
        self.assertIn("frozen_contract_rule", aedl)
        self.assertNotIn("defect_hint", aedl)



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


class RunReceiptIsolation(unittest.TestCase):
    """A receipt must correspond to exactly one run and say what it was run against.

    Measured on master before this card: `runs/<arm>.json` was the only path an arm could
    write, so that directory held `aedl_contract.json` with every result `BudgetExceeded`
    (a spend-ceiling control that had overwritten the model run) beside a `noop.json`
    written by a DIFFERENT code schema, while `executed=0` rendered as `primary 0/5` --
    indistinguishable from a genuine zero.
    """

    def _run(self, arm="noop", parent=None):
        parent = Path(parent or tempfile.mkdtemp())
        run_dir = rb.allocate_run_dir(arm, parent)
        return rb.run_arm(arm, run_dir), run_dir

    def _dead_arm(self):
        def dead(episode, workdir):
            raise rb.BudgetExceeded("model spend ceiling reached: 1.0000 of 1.00 CNY used")
        return dead

    def test_two_runs_never_share_a_destination(self):
        parent = Path(tempfile.mkdtemp())
        first = rb.allocate_run_dir("noop", parent)
        second = rb.allocate_run_dir("noop", parent)
        self.assertNotEqual(first, second)
        self.assertTrue(first.is_dir() and second.is_dir())

    def test_run_dir_names_the_time_the_arm_and_the_code(self):
        sha = rb.code_identity()["sha"]
        name = rb.allocate_run_dir("oracle", Path(tempfile.mkdtemp())).name
        self.assertRegex(name, r"^\d{8}T\d{6}Z-oracle-([0-9a-f]{7}|nohash)-\d{2}$")
        if sha != "UNKNOWN":
            self.assertIn(sha[:7], name)

    def test_a_receipt_is_never_overwritten(self):
        run_dir = rb.allocate_run_dir("noop", Path(tempfile.mkdtemp()))
        rb.run_arm("noop", run_dir)
        with self.assertRaises(rb.RunCollision):
            rb.run_arm("noop", run_dir)

    def test_receipt_pins_everything_it_was_run_against(self):
        report, run_dir = self._run()
        prov = report["provenance"]
        self.assertEqual(prov["run_id"], run_dir.name)
        for key in ("started_at", "finished_at", "code", "writer", "model", "inputs",
                    "budget_before", "budget_after"):
            self.assertIn(key, prov)
        self.assertTrue(prov["code"]["sha"])
        self.assertIsNotNone(prov["code"]["dirty"], "dirty must be known, not merely absent")
        for name, path in (("contract_sha256", rb.CONTRACT_PATH),
                           ("episodes_sha256", rb.EPISODES_PATH),
                           ("acceptance_sha256", rb.ACCEPTANCE_PATH),
                           ("fixture_manifest_sha256", rb.FIXTURE_MANIFEST_PATH)):
            self.assertEqual(prov["inputs"][name], rb.sha256_file(path), name)
        self.assertIn("ceiling_cny", prov["budget_before"])

    def test_writer_absence_is_recorded_as_not_run_not_silence(self):
        writer = self._run()[0]["provenance"]["writer"]
        if writer["status"] == "NOT_RUN":
            self.assertIn("AKCLI=", writer["reason"],
                          "the receipt must tell the next host how to supply the writer")
            self.assertIn("looked_for", writer)
        else:
            self.assertEqual(len(writer["sha256"]), 64)

    def test_receipt_carries_no_credential(self):
        report = self._run()[0]
        model = report["provenance"]["model"]
        self.assertIn(model["status"], ("configured", "unavailable"))
        if model["status"] == "configured":
            self.assertEqual(sorted(model), ["host", "model", "status"])
        text = json.dumps(report, ensure_ascii=False)
        try:
            key = rb.resolve_endpoint()[1]
        except Exception:
            key = None
        if key:
            self.assertNotIn(key, text, "the endpoint key must never enter a receipt")
        for marker in ("Bearer ", "Authorization:", '"api_key"'):
            self.assertNotIn(marker, text)

    def test_verdict_separates_execution_failure_from_not_passing(self):
        report = self._run()[0]
        self.assertEqual({r["verdict"] for r in report["results"]}, {"fail"},
                         "noop executes everywhere: that is a fail, not a non-execution")
        self.assertEqual(report["summary"]["not_executed"], 0)
        self.assertTrue(report["reportable"], "noop correctly fails everything")

    def test_an_arm_that_never_runs_is_not_reportable(self):
        original = rb.ARMS["noop"]
        rb.ARMS["noop"] = self._dead_arm()
        self.addCleanup(rb.ARMS.__setitem__, "noop", original)
        report = self._run()[0]
        self.assertEqual({r["verdict"] for r in report["results"]}, {"not_executed"})
        self.assertEqual(report["summary"]["executed"], 0)
        self.assertEqual(report["summary"]["primary_pass"], 0)
        self.assertFalse(report["reportable"])
        self.assertTrue(any("execution failure" in reason
                            for reason in report["unreportable_reasons"]))
        rendered = rb.render(report)
        self.assertIn("NOT EXECUTED", rendered)
        self.assertIn("REPORTABLE: no", rendered)

    def test_control_findings_enforce_the_manifest_controls(self):
        """The decision is pure, so a control rule is testable without running anything."""
        def row(episode, verdict, in_scope=True):
            return {"episode": episode, "verdict": verdict, "in_scope_v0_1": in_scope}

        self.assertEqual(rb.control_findings("noop", [row("DC-01", "fail")]), [])
        self.assertTrue(rb.control_findings("noop", [row("DC-01", "pass")]),
                        "a noop that passes means the benchmark measures nothing")
        self.assertEqual(rb.control_findings("oracle", [row("DC-01", "pass")]), [])
        self.assertTrue(rb.control_findings("oracle", [row("DC-01", "fail")]),
                        "an answer key that does not reach PASS means the fixture is broken")
        self.assertEqual(rb.control_findings("noop", [row("DC-07", "pass", False)]), [],
                         "out-of-scope episodes decide nothing")
        self.assertTrue(rb.control_findings(
            "baseline_generic", [row("DC-01", "not_executed"), row("DC-02", "not_executed")]))

    def test_main_exits_nonzero_when_the_run_cannot_be_reported(self):
        import contextlib
        import io
        original = rb.ARMS["noop"]
        rb.ARMS["noop"] = self._dead_arm()
        self.addCleanup(rb.ARMS.__setitem__, "noop", original)
        with contextlib.redirect_stdout(io.StringIO()):
            code = rb.main(["--arm", "noop", "--runs-dir", tempfile.mkdtemp()])
        self.assertEqual(code, 3, "an unreportable run must not exit as success")


if __name__ == "__main__":
    unittest.main()
