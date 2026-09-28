"""KICAD_VERIFY as an evidence producer, and the policy that decides from it.

The tests are split deliberately into two lanes, because the claim being made is
platform-dependent and the bug being guarded against is INVISIBLE on the platform it
was written on -- the same property that let the original defect ship twice.

  Lane 1, no tools required: a synthetic bundle. Fast, always runs, and covers the
  rules. This is the lane that carries most of the assertions.

  Lane 2, the real board with real kicad-cli: skipped with a REASON when the binary is
  absent, never passed vacuously. This lane is what makes the claim about the real
  board rather than about a fixture.

The mutation that this suite exists to kill, from the Owner's instruction:

    ERC=0 -> PASS

and its subtler form, which I wrote myself and the real board caught:

    a non-zero kicad-cli exit means "violations found"
    -> reading exit_code == 0 as "the run completed"
    -> a board the tool examined carefully reports "ERC did not complete"
    -> only a board with nothing to report looks successful
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from gates import kicad_evidence, kicad_policy  # noqa: E402

KICAD_CLI = Path(r"C:\dev\tools\kicad-10.0.5\bin\kicad-cli.exe")
REAL_BOARD = REPO / "src" / "hardware" / "m2-board"

SCHEMA = "https://schemas.kicad.org/erc.v1.json"


def synthetic_erc(*, errors: int = 0, warnings: int = 0,
                  ignored=("single_global_label",),
                  declare_limits: bool = True,
                  included=("error", "warning", "exclusion")) -> dict:
    """An ERC report shaped like the real one, including the limits."""
    violations = []
    for _ in range(errors):
        violations.append({"severity": "error", "description": "e"})
    for _ in range(warnings):
        violations.append({"severity": "warning", "description": "w"})
    report = {
        "$schema": SCHEMA,
        "kicad_version": "10.0.5",
        "source": "m2_board.kicad_sch",
        "coordinate_units": "mm",
        "sheets": [{"path": "/", "violations": violations,
                    "unconnected_items": []}],
    }
    if declare_limits:
        report["ignored_checks"] = [
            {"key": key, "description": "ignored: %s" % key} for key in ignored]
        report["included_severities"] = list(included)
    return report


class BundleFixture(unittest.TestCase):
    """A bundle with no tools involved, so the RULES can be tested everywhere."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.design_sha = "a" * 64

    def write_report(self, report: dict, name: str = "erc.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(report), encoding="utf-8")
        return path

    def bundle(self, *, erc_report: dict | None = None, errors: int = 0,
               warnings: int = 0, ignored=("single_global_label",),
               completed=("erc", "netlist", "render", "drc"),
               design_sha: str | None = None, coherent: bool = True,
               declare_limits: bool = True) -> dict:
        sha = design_sha or self.design_sha
        report = synthetic_erc(errors=errors, warnings=warnings, ignored=ignored,
                               declare_limits=declare_limits)
        erc_part = kicad_evidence._erc_part(
            sha, {"argv": ["kicad-cli"], "exit_code": 0, "timed_out": False,
                  "stderr": ""},
            self.write_report(report))
        parts = {}
        for name in ("erc", "netlist", "render", "drc"):
            part = erc_part if name == "erc" else {
                "design_sha256": sha,
                "command": {"argv": ["kicad-cli"], "exit_code": 0,
                            "timed_out": False, "stderr": ""},
                "completed": name in completed,
                "artifacts": [{"name": "%s.out" % name, "bytes": 10,
                               "sha256": "b" * 64}] if name in completed else [],
            }
            if name == "netlist":
                part.update({"components": 21, "nets": 29})
            if name == "render":
                part.update({"file_count": 1})
            parts[name] = part
        out = {
            "schema_version": kicad_evidence.SCHEMA_VERSION,
            "scope": "PR1_CANDIDATE_BYTES",
            "design_sha256": sha,
            "tool_identity": {"kicad_cli_path": "kicad-cli",
                              "kicad_version_reported": "10.0.5",
                              "binary_sha256": "c" * 64,
                              "version_exit_code": 0},
            "coherent": coherent,
            "incoherence": [] if coherent else ["synthetic incoherence"],
            "reasons": [],
            **parts,
        }
        out["bundle_sha256"] = kicad_evidence.digest_of(out)
        return out

    def permissive(self, bundle: dict, **overrides) -> dict:
        policy = kicad_policy.default_policy()
        policy["permitted_ignored_checks"] = [
            c.get("key") for c in
            (bundle["erc"].get("declared_limits") or {}).get("ignored_checks", [])]
        policy["warning_budget"] = 10_000
        policy.update(overrides)
        return policy


# ==========================================================================
# Lane 1 -- the producer produces, and does not decide
# ==========================================================================
class ProducerDoesNotDecideTests(BundleFixture):

    def test_the_bundle_contains_no_verdict_anywhere(self):
        """The separation, asserted structurally rather than by reading.

        If any part of the bundle ever acquires a PASS/FAIL verdict, the producer has
        started deciding and the policy layer is decorative.
        """
        bundle = self.bundle(errors=0, warnings=0)
        blob = json.dumps(bundle)
        for forbidden in ('"PASS"', '"FAIL"', '"VERDICT"', '"decision"'):
            self.assertNotIn(
                forbidden, blob,
                "the producer emitted %s -- it has started deciding" % forbidden)

    def test_the_real_producer_source_emits_no_verdict(self):
        """The check above was testing a HAND-BUILT FIXTURE, not the producer.

        Found by mutation: M6 made `collect_evidence` stamp a `verdict` onto the
        bundle and every test stayed green, because the fixture assembles its own
        dict and never calls the function. So the assertion is now made against the
        producer's actual code, which runs on every host whether or not kicad-cli is
        present.

        Parsed with `ast` rather than grepped. A keyword search over the source is
        worse than useless here: the body carries a comment explaining that
        `ERC=0 -> PASS` is the trap being avoided, so the word PASS appears in prose
        and a naive search fails on the explanation while passing on the code. This
        version looks for what would actually make the producer DECIDE -- a string
        constant that is a verdict, a dict key or name that carries one -- and is
        therefore immune to both comments and docstrings.
        """
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(
            inspect.getsource(kicad_evidence.collect_evidence)))

        verdicts = {"PASS", "FAIL", "VERDICT", "REFUSE", "UNKNOWN"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and node.value in verdicts:
                self.fail("collect_evidence embeds the verdict %r at line %d -- the "
                          "producer has started deciding"
                          % (node.value, node.lineno))
            if isinstance(node, ast.Dict):
                for key in node.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str) \
                            and any(w in key.value.lower()
                                    for w in ("verdict", "decision", "status")):
                        self.fail("collect_evidence has a %r key at line %d -- the "
                                  "producer has started deciding"
                                  % (key.value, key.lineno))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and any(w in node.name.lower()
                            for w in ("verdict", "decide")):
                self.fail("collect_evidence defines %r" % node.name)

    def test_the_policy_is_the_only_module_with_a_decision(self):
        """And the producer exposes no decision function at all."""
        public = [name for name in dir(kicad_evidence)
                  if not name.startswith("_") and "decide" in name.lower()]
        self.assertEqual(public, [],
                         "kicad_evidence grew a %r; deciding belongs to "
                         "kicad_policy" % public)
        self.assertTrue(hasattr(kicad_policy, "decide"))

    def test_every_part_carries_the_design_it_was_produced_from(self):
        bundle = self.bundle()
        for name in ("erc", "netlist", "render", "drc"):
            self.assertEqual(bundle[name]["design_sha256"], bundle["design_sha256"],
                             "%s is not bound to the design" % name)

    def test_the_digest_covers_the_bundle_but_not_itself(self):
        bundle = self.bundle()
        self.assertEqual(kicad_evidence.digest_of(bundle),
                         bundle["bundle_sha256"])
        edited = dict(bundle)
        edited["bundle_sha256"] = "0" * 64
        self.assertEqual(kicad_evidence.digest_of(edited),
                         bundle["bundle_sha256"],
                         "the digest must ignore its own field")

    def test_editing_any_part_changes_the_digest_a_decision_binds_to(self):
        bundle = self.bundle(warnings=3)
        before = bundle["bundle_sha256"]
        edited = json.loads(json.dumps(bundle))
        edited["erc"]["severity_counts"]["warning"] = 0
        self.assertNotEqual(kicad_evidence.digest_of(edited), before,
                            "an edited bundle kept its digest, so a decision could "
                            "not be tied to the evidence it was made on")

    def test_a_report_that_will_not_say_what_it_skipped_is_not_offered_as_evidence(self):
        """The anti-`ERC=0 -> PASS` guard at the producer.

        A report with no `ignored_checks` is NOT defaulted to "nothing was ignored".
        That default is the assumption the whole design exists to refuse.
        """
        bundle = self.bundle(declare_limits=False)
        self.assertFalse(bundle["erc"]["limits_declared"])
        self.assertIn("does not declare its limits",
                      bundle["erc"].get("unavailable", ""))

    def test_limits_are_read_from_the_tool_not_invented(self):
        bundle = self.bundle(ignored=("alpha", "beta", "gamma"))
        limits = bundle["erc"]["declared_limits"]
        self.assertEqual([c["key"] for c in limits["ignored_checks"]],
                         ["alpha", "beta", "gamma"])
        self.assertEqual(limits["declared_by"], "kicad")
        self.assertEqual(limits["included_severities"],
                         ["error", "warning", "exclusion"])


class CompletionSemanticsTests(BundleFixture):
    """The bug the real board caught, pinned so it cannot come back.

    kicad-cli with `--exit-code-violations` exits NON-ZERO when it FINDS violations.
    Keying `completed` off the exit code therefore reports a board the tool examined
    and found problems on as "the run did not complete", and makes a board with
    nothing to report the only one that looks successful.
    """

    def test_a_nonzero_exit_still_counts_as_the_tool_having_run(self):
        part = kicad_evidence._part(
            "a" * 64,
            {"argv": ["kicad-cli", "sch", "erc"], "exit_code": 5,
             "timed_out": False, "stderr": ""},
            [self.write_report(synthetic_erc(warnings=39), "erc.json")])
        self.assertTrue(part["completed"],
                        "exit 5 from --exit-code-violations means violations were "
                        "FOUND, not that the tool failed")
        self.assertEqual(part["command"]["exit_code"], 5,
                         "the exit code is still recorded verbatim")

    def test_a_tool_that_produced_nothing_has_not_completed(self):
        part = kicad_evidence._part(
            "a" * 64,
            {"argv": ["kicad-cli"], "exit_code": 0, "timed_out": False,
             "stderr": ""},
            [])
        self.assertFalse(part["completed"])

    def test_a_tool_that_never_started_has_not_completed(self):
        part = kicad_evidence._part(
            "a" * 64,
            {"argv": ["kicad-cli"], "exit_code": None, "timed_out": True,
             "stderr": "timed out"},
            [self.write_report(synthetic_erc(), "erc.json")])
        self.assertFalse(part["completed"],
                         "a timed-out tool that left a stale file behind is not a "
                         "completed run")


# ==========================================================================
# Lane 1 -- the policy decides
# ==========================================================================
class PolicyDecidesTests(BundleFixture):

    def test_no_policy_means_no_verdict(self):
        decision = kicad_policy.decide(self.bundle(), None)
        self.assertEqual(decision["decision"], "REFUSE")
        self.assertEqual(decision["reason_codes"][0]["code"],
                         kicad_policy.REFUSE_NO_POLICY)

    def test_no_bundle_means_no_verdict(self):
        decision = kicad_policy.decide(None, kicad_policy.default_policy())
        self.assertEqual(decision["decision"], "REFUSE")

    def test_an_incoherent_bundle_is_refused_not_judged(self):
        bundle = self.bundle(coherent=False)
        decision = kicad_policy.decide(bundle, self.permissive(bundle))
        self.assertEqual(decision["decision"], "REFUSE")
        self.assertEqual(decision["reason_codes"][0]["code"],
                         kicad_policy.REFUSE_INCOHERENT)

    def test_a_missing_part_is_refused(self):
        bundle = self.bundle(completed=("erc", "netlist"))
        decision = kicad_policy.decide(bundle, self.permissive(bundle))
        self.assertEqual(decision["decision"], "REFUSE")
        self.assertIn(kicad_policy.REFUSE_INCOMPLETE,
                      [r["code"] for r in decision["reason_codes"]])

    def test_evidence_about_other_bytes_is_refused(self):
        bundle = self.bundle()
        decision = kicad_policy.decide(bundle, self.permissive(bundle),
                                       expected_design_sha256="f" * 64)
        self.assertEqual(decision["decision"], "REFUSE")
        self.assertEqual(decision["reason_codes"][0]["code"],
                         kicad_policy.REFUSE_UNBOUND)

    def test_unpermitted_ignored_checks_are_refused(self):
        bundle = self.bundle(ignored=("secret_check",))
        decision = kicad_policy.decide(bundle, kicad_policy.default_policy())
        self.assertEqual(decision["decision"], "REFUSE")
        self.assertIn(kicad_policy.REFUSE_IGNORED_CHECKS,
                      [r["code"] for r in decision["reason_codes"]])

    def test_an_untolerated_severity_is_refused(self):
        bundle = self.bundle(errors=1)
        decision = kicad_policy.decide(bundle, self.permissive(bundle))
        self.assertEqual(decision["decision"], "REFUSE")
        self.assertIn(kicad_policy.REFUSE_SEVERITY,
                      [r["code"] for r in decision["reason_codes"]])

    def test_a_warning_budget_is_enforced(self):
        bundle = self.bundle(warnings=5)
        policy = self.permissive(bundle, warning_budget=4)
        decision = kicad_policy.decide(bundle, policy)
        self.assertEqual(decision["decision"], "REFUSE")
        self.assertIn(kicad_policy.REFUSE_WARNING_BUDGET,
                      [r["code"] for r in decision["reason_codes"]])

    def test_the_decision_records_the_evidence_it_decided_on(self):
        bundle = self.bundle(warnings=7, ignored=("alpha", "beta"))
        decision = kicad_policy.decide(bundle, self.permissive(bundle))
        self.assertEqual(decision["decision"], "PASS")
        on = decision["decided_on"]
        self.assertEqual(on["bundle_sha256"], bundle["bundle_sha256"])
        self.assertEqual(on["warnings"], 7)
        self.assertEqual([c["key"] for c in on["ignored_checks"]],
                         ["alpha", "beta"])
        self.assertEqual(on["kicad_version"], "10.0.5")

    def test_the_refusal_is_a_policy_choice_not_a_hard_coded_no(self):
        """Same evidence, two policies, two answers.

        This is what separates a policy from a verdict machine. If both policies gave
        the same answer the bundle alone would be deciding, which is the thing being
        removed.
        """
        bundle = self.bundle(warnings=3, ignored=("alpha",))
        strict = kicad_policy.decide(bundle, kicad_policy.default_policy())
        relaxed = kicad_policy.decide(bundle, self.permissive(bundle))
        self.assertEqual(strict["decision"], "REFUSE")
        self.assertEqual(relaxed["decision"], "PASS")


class ErsZeroToPassTests(BundleFixture):
    """The specific thing the Owner refused, as executable assertions."""

    def test_a_board_with_zero_errors_and_many_warnings_is_not_a_pass(self):
        """The exact shape of the real board: 0 errors, 39 warnings, 4 skipped."""
        bundle = self.bundle(errors=0, warnings=39,
                             ignored=("single_global_label", "four_way_junction",
                                      "simulation_model_issue", "footprint_filter"))
        self.assertEqual(bundle["erc"]["error_count"], 0,
                         "the fixture must really have zero errors, or the test is "
                         "not testing what it claims")
        decision = kicad_policy.decide(bundle, kicad_policy.default_policy())
        self.assertEqual(decision["decision"], "REFUSE",
                         "a zero error count must not be a pass")

    def test_dropping_the_limits_from_the_decision_record_is_visible(self):
        """If the decision stopped carrying the limits, it would stop being honest.

        The bundle is unchanged; what is checked is that the DECISION names what it
        decided on, so a reader can see the skipped checks rather than having to
        trust a number.
        """
        bundle = self.bundle(ignored=("alpha", "beta", "gamma", "delta"))
        decision = kicad_policy.decide(bundle, self.permissive(bundle))
        self.assertEqual(decision["decision"], "PASS")
        self.assertEqual(len(decision["decided_on"]["ignored_checks"]), 4,
                         "the decision must carry every skipped check")

    def test_a_producer_with_no_limits_cannot_be_decided_on_at_all(self):
        bundle = self.bundle(declare_limits=False)
        decision = kicad_policy.decide(bundle, self.permissive(bundle))
        self.assertEqual(decision["decision"], "REFUSE")


# ==========================================================================
# Lane 2 -- the real board, real kicad-cli
# ==========================================================================
@unittest.skipUnless(KICAD_CLI.is_file() and REAL_BOARD.is_dir(),
                     "kicad-cli 10.0.5 or the m2 board is not present on this host")
class RealBoardEvidenceTests(unittest.TestCase):
    """Run the producer for real, against the board this repository ships.

    Skipped with a reason when the tool is absent, never passed vacuously -- the same
    discipline the F1 link tests use, and for the same reason: a test that cannot run
    must not look like a test that passed.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name)
        cls.bundle = kicad_evidence.collect_evidence(REAL_BOARD, cls.out, KICAD_CLI)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_the_bundle_is_coherent_against_the_real_board(self):
        self.assertTrue(self.bundle["coherent"],
                        "incoherent: %s" % self.bundle["incoherence"])

    def test_the_tool_identity_is_recorded(self):
        identity = self.bundle["tool_identity"]
        self.assertTrue(identity["kicad_version_reported"].startswith("10."),
                        "expected the pinned 10.x, got %r"
                        % identity["kicad_version_reported"])
        self.assertEqual(len(identity["binary_sha256"]), 64)

    def test_all_four_evidence_kinds_come_from_real_runs(self):
        for name in ("erc", "netlist", "render", "drc"):
            self.assertTrue(self.bundle[name]["completed"], name)
            self.assertTrue(self.bundle[name]["artifacts"], name)

    def test_the_erc_report_declares_its_own_limits(self):
        erc = self.bundle["erc"]
        self.assertTrue(erc["limits_declared"])
        self.assertIn("ignored_checks", erc["declared_limits"])
        self.assertIn("included_severities", erc["declared_limits"])

    def test_the_real_board_has_zero_errors_and_nonzero_warnings(self):
        """Pins the measurement the whole design rests on.

        If KiCad changes and this board's numbers move, this fails and the design
        rationale is re-examined rather than silently invalidated.
        """
        erc = self.bundle["erc"]
        self.assertEqual(erc["error_count"], 0)
        self.assertGreater(erc["violations_total"], 0,
                           "this board is expected to carry ERC warnings; if it no "
                           "longer does, the motivating measurement has changed")

    def test_the_real_bundle_carries_no_verdict(self):
        """The same property, on the bundle the REAL producer built.

        The synthetic-lane check inspects a hand-assembled dict, which is how M6
        survived; this one goes through `collect_evidence` for real.
        """
        blob = json.dumps(self.bundle)
        for forbidden in ('"PASS"', '"FAIL"', '"verdict"', '"decision"'):
            self.assertNotIn(
                forbidden, blob,
                "the real producer emitted %s" % forbidden)

    def test_the_netlist_and_render_are_real_artifacts(self):
        self.assertGreater(self.bundle["netlist"]["components"], 0)
        self.assertGreater(self.bundle["netlist"]["nets"], 0)
        self.assertGreaterEqual(self.bundle["render"]["file_count"], 1)

    def test_the_default_policy_refuses_the_real_board(self):
        """The end-to-end claim, on the real board, with the real tool.

        `ERC=0 -> PASS` would pass this board. The default policy refuses it, and
        says which of the two rules did it.
        """
        decision = kicad_policy.decide(
            self.bundle, kicad_policy.default_policy(),
            expected_design_sha256=self.bundle["design_sha256"])
        self.assertEqual(decision["decision"], "REFUSE")
        codes = {r["code"] for r in decision["reason_codes"]}
        self.assertTrue(
            codes & {kicad_policy.REFUSE_IGNORED_CHECKS,
                     kicad_policy.REFUSE_WARNING_BUDGET},
            "expected a limits-based refusal, got %s" % codes)

    def test_a_policy_that_permits_this_board_passes_it(self):
        erc = self.bundle["erc"]
        policy = kicad_policy.default_policy()
        policy["permitted_ignored_checks"] = [
            c["key"] for c in erc["declared_limits"]["ignored_checks"]]
        policy["warning_budget"] = erc["violations_total"] + 1
        decision = kicad_policy.decide(self.bundle, policy,
                                       expected_design_sha256=self.bundle["design_sha256"])
        self.assertEqual(decision["decision"], "PASS",
                         "refusal reason: %s" % decision["reason_codes"])


if __name__ == "__main__":
    unittest.main()
