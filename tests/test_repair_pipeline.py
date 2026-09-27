"""PR1-C5 stage 1: the host contract, the pure PRECHECK gates and rule binding.

Stage 1 is exactly the surface that must reject a round BEFORE anything durable
happens, so these tests exercise no tool, no stage and no candidate write.  The
last two tests pin the two toolchain checks the Owner required: the before-candidate
symbol digest is a host input cross-checked against the native read, and a mismatch
must block before any write.
"""

import inspect
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gates.repair_verification import _manifest as c2_manifest
from gates.repair_verification import _tree_digest as c2_tree_digest
from gates.repair_verification import compare_delta as c2_compare_delta
from tests.test_host_toolchain import base_binding
from tests.test_repair_verification import circuit, five_case, mini
from tools import akcli_adapter as adapter
from tools import repair_pipeline as pipeline


def abs_path(*parts):
    return os.path.abspath(os.path.join(os.sep, *parts))


RUN = "run-1"
CAND = "cand-1"
ROUND = "round-1"
PATCH = "patch-1"
CONTEXT = "ctx-1"
TARGET = "design.kicad_sch"
SYMBOL = "7" * 64


def policy():
    return pipeline.load_topology_policy()


def policy_sha():
    return pipeline._policy_document_sha256(policy())


def authority(**overrides):
    document = {
        "context_digest": "a" * 64,
        "resolved_authorization_refs": ["grant-1"],
        "decisions": [
            {"capability": pipeline.CAPABILITY_TOOL_EXECUTE, "effect": pipeline.EFFECT_ALLOW},
            {"capability": pipeline.CAPABILITY_FILE_WRITE, "effect": pipeline.EFFECT_ALLOW},
        ],
        "approvals": [
            {"policy_file_sha256": policy_sha(), "rule_id": "E1", "run_id": RUN,
             "candidate_id": CAND, "paths": [abs_path("cand")]},
        ],
    }
    document.update(overrides)
    return document


def host_context(design_root=None, **overrides):
    root = design_root or abs_path("cand")
    document = {
        "run_id": RUN, "candidate_id": CAND, "round_id": ROUND, "patch_id": PATCH,
        "context_id": CONTEXT, "target": TARGET,
        "base_source_sha256": "b" * 64, "initial_context_digest": "c" * 64,
        "limits": {"max_ops": 8},
        "workspace": {"candidate_root": root,
                      "design_root": os.path.join(root, "design"),
                      "repair_root": os.path.join(root, ".repair"),
                      "lock_path": os.path.join(root, ".repair.lock")},
        "toolchain_binding": base_binding(),
        "candidate_symbol_digest": SYMBOL,
        "policy_path": str(pipeline.TOPOLOGY_POLICY_PATH),
        "authority": authority(),
        "native": {"read_root": root, "artifact_root": abs_path("tmp")},
    }
    document.update(overrides)
    return document


def proposal(**overrides):
    document = dict(
        schema_version=1, context_id=CONTEXT, target=TARGET,
        base_source_sha256="b" * 64, decision=pipeline.DECISION_PATCH,
        diagnosis=({"rule_id": "E1"},),
        oplist={"protocol_version": 2, "target_format": "kicad", "ops": []},
        refusal=None, raw_sha256="d" * 64, proposal_sha256="e" * 64)
    document.update(overrides)
    return pipeline.Proposal(**document)


def native_before(symbol=SYMBOL, status="PASS", observation=None):
    return {"status": status,
            "observation": circuit() if observation is None else observation,
            "tool": {"symbol_digest": symbol}}


def _round_source():
    """The source of the WHOLE round: the locking wrapper plus its body.

    `run_round` became a thin wrapper -- it takes the single-writer lock
    (contract 346/369) and runs recovery, then delegates -- around
    `_run_round_body`, which holds the phases.

    Five tests read the round's source to assert it drives, or does not contain,
    something. Against the wrapper alone they would pass VACUOUSLY: an
    `assertNotIn` is satisfied by a function containing none of the code, for
    entirely the wrong reason. So they read both halves.

    Concatenated rather than nested, so a substring test behaves as it did when
    the phases lived in one function.
    """
    return (inspect.getsource(pipeline.run_round)
            + inspect.getsource(pipeline._run_round_body))


class HostContextTests(unittest.TestCase):
    def test_a_valid_context_is_accepted_and_the_two_sets_stay_distinct(self):
        normalized = pipeline.validate_host_context(host_context())
        self.assertEqual(normalized["run_id"], RUN)
        self.assertEqual(len(pipeline._HOST_CONTEXT_FIELDS), 15)
        self.assertEqual(len(pipeline._RUNTIME_BINDING_FIELDS), 14)
        # the policy's runtime values are NOT host_context fields
        self.assertNotIn("pin_identity_map", pipeline._HOST_CONTEXT_FIELDS)
        self.assertNotIn("base_file_manifest", pipeline._HOST_CONTEXT_FIELDS)

    def test_unknown_and_missing_host_fields_are_refused(self):
        for mutate in (lambda doc: doc.update(extra=1),
                       lambda doc: doc.pop("policy_path")):
            with self.subTest(mutate=mutate):
                bad = host_context()
                mutate(bad)
                with self.assertRaises(pipeline.HostContextError):
                    pipeline.validate_host_context(bad)

    def test_host_paths_must_be_absolute(self):
        bad = host_context()
        bad["workspace"]["design_root"] = "design"
        with self.assertRaises(pipeline.HostContextError):
            pipeline.validate_host_context(bad)

    def test_a_toolchain_binding_the_pre_module_refuses_is_refused_here(self):
        broken = base_binding()
        broken["manifest"]["kicad"]["version"] = "10.0.6"
        with self.assertRaises(pipeline.HostContextError):
            pipeline.validate_host_context(host_context(toolchain_binding=broken))

    def test_an_unknown_authority_capability_is_refused(self):
        bad = host_context(authority=authority(
            decisions=[{"capability": "NETWORK", "effect": "ALLOW"}]))
        with self.assertRaises(pipeline.HostContextError):
            pipeline.validate_host_context(bad)


class AuthorityTests(unittest.TestCase):
    def test_a_missing_or_denied_capability_blocks_the_round(self):
        for decisions in ([], [{"capability": pipeline.CAPABILITY_TOOL_EXECUTE,
                                "effect": "DENY"},
                               {"capability": pipeline.CAPABILITY_FILE_WRITE,
                                "effect": pipeline.EFFECT_ALLOW}]):
            with self.subTest(decisions=decisions):
                context = pipeline.validate_host_context(
                    host_context(authority=authority(decisions=decisions)))
                findings = pipeline.authority_findings(context)
                self.assertTrue(findings)
                self.assertEqual({item.code for item in findings},
                                 {pipeline.REASON_AUTH_DENIED})

    def test_an_unbound_write_path_blocks_the_round(self):
        context = pipeline.validate_host_context(
            host_context(authority=authority(approvals=[])))
        findings = pipeline.authority_findings(context, [abs_path("cand")])
        self.assertEqual([item.code for item in findings],
                         [pipeline.REASON_AUTH_DENIED])

    def test_fully_allowed_authority_produces_no_finding(self):
        context = pipeline.validate_host_context(host_context())
        self.assertEqual(pipeline.authority_findings(context), [])


class RuleBindingTests(unittest.TestCase):
    def approved(self):
        context = pipeline.validate_host_context(host_context())
        return context, pipeline.approved_rule_ids(context, policy_sha())

    def test_exactly_one_approved_rule_binds(self):
        context, approved = self.approved()
        self.assertEqual(approved, {"E1"})
        rule, findings = pipeline.select_rule(policy(), proposal(), approved)
        self.assertEqual(findings, [])
        self.assertEqual(rule["id"], "E1")
        self.assertEqual(rule["route"], pipeline.ROUTE_EXCEPTION)

    def test_an_unmatched_rule_is_blocked(self):
        _, approved = self.approved()
        rule, findings = pipeline.select_rule(
            policy(), proposal(diagnosis=({"rule_id": "DC-99"},)), approved)
        self.assertIsNone(rule)
        self.assertEqual([item.code for item in findings],
                         [pipeline.REASON_INPUT_DRIFT])

    def test_multiple_matching_rules_are_blocked(self):
        _, approved = self.approved()
        rule, findings = pipeline.select_rule(
            policy(), proposal(diagnosis=({"rule_id": "E1"}, {"rule_id": "DC-04"})),
            approved)
        self.assertIsNone(rule)
        self.assertEqual([item.code for item in findings],
                         [pipeline.REASON_INPUT_DRIFT])

    def test_a_rule_the_host_did_not_approve_is_blocked(self):
        rule, findings = pipeline.select_rule(policy(), proposal(), set())
        self.assertIsNone(rule)
        self.assertEqual([item.code for item in findings],
                         [pipeline.REASON_AUTH_DENIED])

    def test_an_unknown_route_is_blocked(self):
        mutated = copy.deepcopy(policy())
        for entry in mutated["rules"]:
            if entry["id"] == "E1":
                entry["route"] = "AUTO"
        rule, findings = pipeline.select_rule(mutated, proposal(), {"E1"})
        self.assertIsNone(rule)
        self.assertEqual([item.code for item in findings],
                         [pipeline.REASON_SCHEMA_INVALID])

    def test_approvals_are_scoped_to_the_policy_run_and_candidate(self):
        for overrides in ({"run_id": "run-2"}, {"candidate_id": "cand-2"},
                          {"policy_file_sha256": "0" * 64}):
            with self.subTest(overrides=overrides):
                approval = authority()["approvals"][0]
                approval.update(overrides)
                context = pipeline.validate_host_context(
                    host_context(authority=authority(approvals=[approval])))
                self.assertEqual(
                    pipeline.approved_rule_ids(context, policy_sha()), set())


class RefusalTests(unittest.TestCase):
    def test_a_legal_refusal_needs_no_tool_and_no_stage_write(self):
        verdict = pipeline.refusal_verdict(policy(), proposal(
            decision=pipeline.DECISION_REFUSE, oplist=None,
            refusal={"component": "R7", "background_status": "NOT_APPLICABLE"}))
        self.assertEqual(verdict, [])

    def test_a_patch_proposal_is_not_a_refusal(self):
        findings = pipeline.refusal_verdict(policy(), proposal())
        self.assertEqual([item.code for item in findings],
                         [pipeline.REASON_SCHEMA_INVALID])

    def test_a_refusal_that_carries_an_oplist_is_refused(self):
        findings = pipeline.refusal_verdict(policy(), proposal(
            decision=pipeline.DECISION_REFUSE,
            refusal={"component": "R7", "background_status": "NOT_APPLICABLE"}))
        self.assertEqual([item.code for item in findings],
                         [pipeline.REASON_SCHEMA_INVALID])


class RuntimeBindingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        (self.design / TARGET).write_bytes(b"(kicad_sch)")
        (self.design / "notes.txt").write_bytes(b"read only")
        self.context = pipeline.validate_host_context(
            host_context(design_root=str(self.root / "cand")))

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_fourteen_runtime_values_are_derived_not_accepted(self):
        values = pipeline.runtime_bindings(self.context, proposal(), native_before(),
                                           policy_sha(), {"E1"})
        self.assertEqual(sorted(values), sorted(pipeline._RUNTIME_BINDING_FIELDS))
        self.assertEqual(values["proposal_sha256"], "e" * 64)
        self.assertEqual(values["approved_rule_ids"], ["E1"])
        self.assertEqual(values["policy_document_sha256"], policy_sha())
        # the base manifest is C5's own observation of the candidate bytes
        roles = {row["path"]: row["role"] for row in values["base_file_manifest"]["files"]}
        self.assertEqual(roles, {TARGET: "TARGET", "notes.txt": "READONLY_DEPENDENCY"})
        # identity maps and symbol hashes come from the native observation
        self.assertEqual(values["embedded_symbol_hashes"]["Device:R"], "1" * 64)
        self.assertTrue(values["pin_identity_map"])
        # object_identity_map binds REMOVALS, not the component inventory: with no
        # rule selected there is nothing to remove.
        self.assertEqual(values["object_identity_map"], {})
        # only the akcli slice is bound here; the C3 slice is checked after verify
        self.assertEqual(values["toolchain_manifest"]["akcli_version"], "0.21.0")

    def test_a_native_read_that_is_not_pass_cannot_bind(self):
        for native in (native_before(status="BLOCKED"), {"status": "PASS"},
                       "not-a-mapping"):
            with self.subTest(native=native):
                with self.assertRaises(pipeline.HostContextError):
                    pipeline.runtime_bindings(self.context, proposal(), native,
                                              policy_sha(), {"E1"})

    def test_a_symbol_digest_that_does_not_match_the_native_read_blocks_before_write(self):
        drifted = host_context(design_root=str(self.root / "cand"),
                               candidate_symbol_digest="9" * 64)
        context = pipeline.validate_host_context(drifted)
        with self.assertRaises(pipeline.HostContextError) as caught:
            pipeline.runtime_bindings(context, proposal(), native_before(),
                                      policy_sha(), {"E1"})
        self.assertIn("candidate_symbol_digest", caught.exception.findings[0].detail)


class PartitionCaptureTests(unittest.TestCase):
    """S1b capture layer: BEFORE partitions are captured exactly once."""

    def setUp(self):
        self.observation = circuit()

    def test_member_tokens_resolve_exactly(self):
        identity = pipeline.resolve_pin_identity("R1.2", self.observation)
        self.assertEqual(identity["reference"], "R1")
        self.assertEqual(identity["number"], "2")

    def test_a_token_that_misses_or_is_malformed_is_refused(self):
        for token in ("R9.1", "R1", "R1.1.2", "", "R1.x"):
            with self.subTest(token=token):
                with self.assertRaises(pipeline.HostContextError):
                    pipeline.resolve_pin_identity(token, self.observation)

    def test_members_exact_captures_the_observed_before_partition(self):
        captured = pipeline.capture_before_partitions(self.observation, [
            {"slot": "one", "names_exact": [], "members_exact": ["R1.1"]}])
        self.assertEqual(len(captured["one"]["members"]), 1)
        self.assertEqual(captured["one"]["key"],
                         pipeline.canonical_sha256("topology", captured["one"]["members"]))

    def test_capture_all_members_takes_the_whole_partition_once(self):
        captured = pipeline.capture_before_partitions(self.observation, [
            {"slot": "gnd", "names_exact": [], "capture_all_members": True,
             "contains": ["R1.1"], "excludes": ["R2.1"]}])
        self.assertEqual([item["reference"] for item in captured["gnd"]["members"]], ["R1"])

    def test_capture_all_members_that_matches_several_partitions_is_refused(self):
        with self.assertRaises(pipeline.HostContextError):
            pipeline.capture_before_partitions(self.observation, [
                {"slot": "gnd", "names_exact": [], "capture_all_members": True}])

    def test_a_member_assertion_matching_no_partition_is_refused(self):
        with self.assertRaises(pipeline.HostContextError):
            pipeline.capture_before_partitions(self.observation, [
                {"slot": "one", "names_exact": ["/X"], "members_exact": ["R1.1"]}])

    def test_a_slot_with_no_members_is_refused(self):
        with self.assertRaises(pipeline.HostContextError):
            pipeline.capture_before_partitions(self.observation, [
                {"slot": "one", "names_exact": [], "members_exact": []}])

    def test_duplicate_slots_are_refused(self):
        with self.assertRaises(pipeline.HostContextError):
            pipeline.capture_before_partitions(self.observation, [
                {"slot": "a", "names_exact": [], "members_exact": ["R1.1"]},
                {"slot": "a", "names_exact": [], "members_exact": ["R2.1"]}])


class PartitionTransformTests(unittest.TestCase):
    """S1b frozen transformation: replace the named slots, keep the rest."""

    def setUp(self):
        self.observation = circuit()
        self.captured = pipeline.capture_before_partitions(self.observation, [
            {"slot": "one", "names_exact": [], "members_exact": ["R1.1"]}])

    def rule(self):
        return {"id": "T", "route": pipeline.ROUTE_STRICT,
                "after": {"replace_partitions": ["one"],
                          "partitions": [{"names_exact": ["/A"], "members_from": "one",
                                          "add_exact": ["R2.1"]}],
                          "all_other_partitions": "UNCHANGED"}}

    def test_the_named_slot_is_replaced_and_every_other_partition_is_kept(self):
        partitions = pipeline.project_expected_partitions(
            self.observation, self.rule(), self.captured, {})
        self.assertEqual(len(partitions), len(self.observation["partitions"]))
        self.assertIn(["/A"], [partition["names"] for partition in partitions])

    def test_naming_an_uncaptured_slot_is_refused(self):
        rule = self.rule()
        rule["after"]["replace_partitions"] = ["nope"]
        with self.assertRaises(pipeline.HostContextError):
            pipeline.project_expected_partitions(self.observation, rule, self.captured, {})

    def test_members_from_an_uncaptured_slot_is_refused(self):
        rule = self.rule()
        rule["after"]["partitions"][0]["members_from"] = "nope"
        with self.assertRaises(pipeline.HostContextError):
            pipeline.project_expected_partitions(self.observation, rule, self.captured, {})

    def test_a_new_pin_binding_is_used_instead_of_the_before_observation(self):
        rule = {"id": "T", "route": pipeline.ROUTE_STRICT,
                "after": {"replace_partitions": ["one"],
                          "partitions": [{"names_exact": ["/A"], "members_from": "one",
                                          "add_exact": ["R9.1"]}],
                          "all_other_partitions": "UNCHANGED"}}
        synthetic = dict(pipeline.resolve_pin_identity("R1.1", self.observation))
        synthetic["component_uuid"] = "new:R9"
        synthetic["reference"] = "R9"
        synthetic["number"] = "1"
        partitions = pipeline.project_expected_partitions(
            self.observation, rule, self.captured, {"R9.1": synthetic})
        members = [m for m in partitions if m["names"] == ["/A"]][0]["members"]
        self.assertEqual([m["reference"] for m in members].count("R9"), 1)


class RemovalBindingTests(unittest.TestCase):
    """S1b: object_identity_map binds exactly the selected rule's removals.

    C2 _prepare() reads it as the declarations of the objects this round may
    delete; a component identity index is a different thing with a different
    lifecycle and must never be substituted for it.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        (self.design / TARGET).write_bytes(b"(kicad_sch)")
        self.context = pipeline.validate_host_context(
            host_context(design_root=str(self.root / "cand")))

    def tearDown(self):
        self._tmp.cleanup()

    def rule(self, slots):
        return {"id": "T", "route": pipeline.ROUTE_STRICT,
                "object_delta": {"remove": [{"slot": slot} for slot in slots]}}

    def declaration(self, uuid):
        return {"uuid": uuid, "kind": "label", "descriptor_sha256": "1" * 64}

    def bind(self, rule=None, removals=None):
        return pipeline.runtime_bindings(self.context, proposal(), native_before(),
                                         policy_sha(), {"E1"}, rule=rule,
                                         removals=removals)

    def test_a_rule_that_removes_objects_must_have_them_resolved(self):
        with self.assertRaises(pipeline.HostContextError) as caught:
            self.bind(rule=self.rule(["wrong_dm"]), removals={})
        self.assertIn("object_identity_map", caught.exception.findings[0].detail)

    def test_resolved_slots_must_match_the_rule_exactly(self):
        for removals in ({"other": self.declaration("u")},
                         {"wrong_dm": self.declaration("u"),
                          "extra": self.declaration("v")}):
            with self.subTest(removals=sorted(removals)):
                with self.assertRaises(pipeline.HostContextError) as caught:
                    self.bind(rule=self.rule(["wrong_dm"]), removals=removals)
                self.assertIn("removal slots", caught.exception.findings[0].detail)

    def test_resolved_removals_reach_the_binding_unchanged(self):
        declared = self.declaration("11111111-2222-3333-4444-555555555555")
        values = self.bind(rule=self.rule(["wrong_dm"]), removals={"wrong_dm": declared})
        self.assertEqual(values["object_identity_map"], {"wrong_dm": declared})
        self.assertEqual(len(values), len(pipeline._RUNTIME_BINDING_FIELDS))

    def test_a_removal_declaration_is_closed_and_typed(self):
        for entry in ({"uuid": "u", "kind": "label"},
                      {"uuid": "u", "kind": "symbol", "descriptor_sha256": "1" * 64},
                      {"uuid": "u", "kind": "label", "descriptor_sha256": "nope"}):
            with self.subTest(entry=entry):
                with self.assertRaises(pipeline.HostContextError):
                    self.bind(rule=self.rule(["wrong_dm"]), removals={"wrong_dm": entry})


class SelectorResolutionTests(unittest.TestCase):
    """S1b: a removal selector resolves through C2's AST to one observed object.

    The host must PROVE which object a policy authorizes deleting; it never trusts
    a proposer-supplied uuid.  Failures keep their class: identity that cannot be
    determined is UNKNOWN, an illegal selector field is BLOCKED.
    """

    def setUp(self):
        self.observation = circuit()
        self.pin = pipeline.resolve_pin_identity("R1.1", self.observation)
        self.anchor = (1000, 2000)
        self.uuid = "11111111-2222-3333-4444-555555555555"
        # the C2 AST is canonical-JSON safe: no floats (canonical_json_bytes rejects them)
        self.node = ["label", "USB_DM", ["at", 1000, 2000, 0]]
        self.index = {
            "observation": self.observation,
            "pin_anchor": {pipeline.canonical_json_bytes(self.pin): self.anchor},
            "labels": [{"uuid": self.uuid, "name": "USB_DM",
                        "point": self.anchor, "node": self.node}],
            "wires": [],
            "objects": {self.uuid: {"identity": self.uuid, "kind": "label",
                                    "semantic_ast_sha256": "a" * 64,
                                    "descriptor": {"ast": self.node}}},
        }

    def selector(self, **overrides):
        document = {"kind": "label", "name": "USB_DM", "at_pin": "R1.1", "scope": "local"}
        document.update(overrides)
        return document

    def add_wire(self):
        uuid = "99999999-8888-7777-6666-555555555555"
        node = ["wire", ["pts", ["xy", 1, 2], ["xy", 3, 4]]]
        self.index["wires"] = [{"uuid": uuid,
                                "endpoints": frozenset(((1, 2), (3, 4))), "node": node}]
        self.index["objects"][uuid] = {"identity": uuid, "kind": "wire",
                                       "semantic_ast_sha256": "b" * 64,
                                       "descriptor": {"ast": node}}
        return uuid

    def test_a_unique_local_label_at_a_pin_resolves_to_its_descriptor_digest(self):
        status, payload = pipeline.resolve_removal_selector(self.index, self.selector())
        self.assertEqual(status, "PASS")
        self.assertEqual(payload, {
            "uuid": self.uuid, "kind": "label",
            "descriptor_sha256": pipeline.canonical_sha256("protected",
                                                           {"ast": self.node})})
        # C2 wants hash(descriptor), not hash(node): the two domains differ.
        self.assertNotEqual(payload["descriptor_sha256"], "a" * 64)

    def test_zero_matches_is_unknown_input_drift_not_incomplete_coverage(self):
        # source complete + AST parseable: the failure is that the current bytes no
        # longer bind to the frozen selector, so the class is input drift.
        status, finding = pipeline.resolve_removal_selector(
            self.index, self.selector(name="USB_DP"))
        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(finding.code, pipeline.REASON_INPUT_DRIFT)

    def test_an_incomplete_geometry_is_incomplete_coverage(self):
        self.index["pin_anchor"] = {}
        status, finding = pipeline.resolve_removal_selector(self.index, self.selector())
        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(finding.code, pipeline.REASON_COVERAGE_INCOMPLETE)

    def test_more_than_one_match_is_ambiguous(self):
        self.index["labels"].append(dict(self.index["labels"][0],
                                         uuid="22222222-3333-4444-5555-666666666666"))
        status, finding = pipeline.resolve_removal_selector(self.index, self.selector())
        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(finding.code, pipeline.REASON_SELECTOR_AMBIGUOUS)

    def test_an_illegal_selector_field_is_blocked(self):
        for selector in (self.selector(scope="global"), {"kind": "net"},
                         self.selector(at_pin="nope")):
            with self.subTest(selector=selector):
                status, finding = pipeline.resolve_removal_selector(self.index, selector)
                self.assertEqual(status, "BLOCKED")
                self.assertEqual(finding.code, pipeline.REASON_SCHEMA_INVALID)

    def test_a_selector_ast_disagreeing_with_the_observation_is_not_guessed(self):
        self.index["objects"][self.uuid]["descriptor"]["ast"] = ["label", "OTHER"]
        status, finding = pipeline.resolve_removal_selector(self.index, self.selector())
        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(finding.code, pipeline.REASON_PARSER_DISAGREEMENT)

    def test_a_label_absent_from_the_before_observation_is_not_guessed(self):
        self.index["objects"] = {}
        status, finding = pipeline.resolve_removal_selector(self.index, self.selector())
        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(finding.code, pipeline.REASON_PARSER_DISAGREEMENT)

    def test_a_wire_selector_ignores_endpoint_direction(self):
        uuid = self.add_wire()
        status, payload = pipeline.resolve_removal_selector(
            self.index, {"kind": "wire", "endpoints_nm": [[3, 4], [1, 2]]})
        self.assertEqual(status, "PASS")
        self.assertEqual(payload["uuid"], uuid)

    def test_a_wire_selector_needs_exactly_two_endpoints(self):
        status, finding = pipeline.resolve_removal_selector(
            self.index, {"kind": "wire", "endpoints_nm": [[1, 2]]})
        self.assertEqual(status, "BLOCKED")
        self.assertEqual(finding.code, pipeline.REASON_SCHEMA_INVALID)

    def test_resolve_removals_returns_the_first_failure(self):
        status, declarations, findings = pipeline.resolve_removals(
            self.index, [{"slot": "wrong_dm", "kind": "label", "name": "USB_DM",
                          "at_pin": "R1.1", "scope": "local"},
                         {"slot": "gone", "kind": "label", "name": "NOPE",
                          "at_pin": "R1.1", "scope": "local"}])
        self.assertEqual(status, "UNKNOWN")
        self.assertIsNone(declarations)
        self.assertEqual(findings[0].code, pipeline.REASON_INPUT_DRIFT)

    def test_resolve_removals_binds_every_named_slot(self):
        status, declarations, findings = pipeline.resolve_removals(
            self.index, [{"slot": "wrong_dm", "kind": "label", "name": "USB_DM",
                          "at_pin": "R1.1", "scope": "local"}])
        self.assertEqual((status, findings), ("PASS", []))
        self.assertEqual(sorted(declarations), ["wrong_dm"])

    def test_duplicate_slots_are_blocked(self):
        status, declarations, findings = pipeline.resolve_removals(
            self.index, [{"slot": "a", "kind": "label", "name": "USB_DM",
                          "at_pin": "R1.1", "scope": "local"},
                         {"slot": "a", "kind": "wire", "endpoints_nm": [[1, 2], [3, 4]]}])
        self.assertEqual(status, "BLOCKED")
        self.assertEqual(findings[0].code, pipeline.REASON_SCHEMA_INVALID)

    def test_the_index_is_built_from_the_c2_observation_of_the_same_bytes(self):
        raw = mini()
        index = pipeline.selector_source_index(raw)
        self.assertEqual(index["observation"]["source_sha256"], pipeline.hash_bytes(raw))
        self.assertTrue(index["objects"])
        self.assertIsInstance(index["pin_anchor"], dict)

    def test_bytes_outside_the_qualified_subset_are_refused(self):
        with self.assertRaises(pipeline.HostContextError):
            pipeline.selector_source_index(b"(kicad_sch (version 1))")


class BinderInvariantTests(unittest.TestCase):
    """C5 must freeze the invariants C2 does not re-derive for itself."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        design = self.root / "cand" / "design"
        design.mkdir(parents=True)
        (design / TARGET).write_bytes(b"(kicad_sch)")
        self.context = pipeline.validate_host_context(
            host_context(design_root=str(self.root / "cand")))
        self.observation = circuit()

    def tearDown(self):
        self._tmp.cleanup()

    def declaration(self, uuid):
        return {"uuid": uuid, "kind": "label", "descriptor_sha256": "1" * 64}

    def rule(self, slots):
        return {"id": "T", "route": pipeline.ROUTE_STRICT,
                "object_delta": {"remove": [{"slot": slot} for slot in slots]}}

    def bind(self, rule, removals):
        return pipeline.runtime_bindings(self.context, proposal(), native_before(),
                                         policy_sha(), {"E1"}, rule=rule,
                                         removals=removals)

    def test_two_slots_may_not_bind_the_same_object(self):
        same = self.declaration("11111111-2222-3333-4444-555555555555")
        with self.assertRaises(pipeline.HostContextError) as caught:
            self.bind(self.rule(["a", "b"]), {"a": same, "b": dict(same)})
        self.assertIn("same object", caught.exception.findings[0].detail)

    def test_distinct_slots_binding_distinct_objects_is_accepted(self):
        values = self.bind(self.rule(["a", "b"]), {
            "a": self.declaration("11111111-2222-3333-4444-555555555555"),
            "b": self.declaration("66666666-7777-8888-9999-000000000000")})
        self.assertEqual(sorted(values["object_identity_map"]), ["a", "b"])

    def captured_rule(self, slots):
        return {"id": "T", "route": pipeline.ROUTE_STRICT,
                "before": {"partitions": [{"slot": slot} for slot in slots]},
                "after": {"replace_partitions": [], "partitions": []}}

    def capture(self):
        return pipeline.capture_before_partitions(self.observation, [
            {"slot": "one", "names_exact": [], "members_exact": ["R1.1"]}])

    def test_the_capture_slot_set_must_equal_the_rule(self):
        with self.assertRaises(pipeline.HostContextError) as caught:
            pipeline.validate_captured_partitions(self.capture(),
                                                  self.captured_rule(["other"]))
        self.assertIn("captured slot set", caught.exception.findings[0].detail)

    def test_the_captured_key_must_be_the_digest_of_its_members(self):
        captured = self.capture()
        captured["one"]["key"] = "0" * 64
        with self.assertRaises(pipeline.HostContextError) as caught:
            pipeline.validate_captured_partitions(captured, self.captured_rule(["one"]))
        self.assertIn("key", caught.exception.findings[0].detail)

    def test_captured_names_must_be_canonically_ordered(self):
        captured = self.capture()
        captured["one"]["names"] = ["/B", "/A"]
        with self.assertRaises(pipeline.HostContextError) as caught:
            pipeline.validate_captured_partitions(captured, self.captured_rule(["one"]))
        self.assertIn("canonically ordered", caught.exception.findings[0].detail)

    def test_an_empty_capture_is_refused(self):
        captured = self.capture()
        captured["one"]["members"] = []
        with self.assertRaises(pipeline.HostContextError) as caught:
            pipeline.validate_captured_partitions(captured, self.captured_rule(["one"]))
        self.assertIn("no members", caught.exception.findings[0].detail)

    def test_a_well_formed_capture_passes(self):
        captured = self.capture()
        self.assertEqual(
            pipeline.validate_captured_partitions(captured, self.captured_rule(["one"])),
            captured)


class ExpectedAfterGeometryTests(unittest.TestCase):
    """Checkpoint 1: build_expected_after derives label geometry from bytes.

    The pinned writer branches on the presence of the rotation key, so an omitted
    rotation (native pin-derived orientation) and an explicit 0 are different
    expected semantics.  The DC-04/DC-05 literals below are native oracles
    measured from pinned akcli-kicad 0.21.0, not assumptions; the kernel that
    reproduces them is a behavioural replica of that toolchain's geometry.
    """

    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "repair_pr1" / "native"

    def _observation(self, case, components=()):
        raw = (self.FIXTURES / case / "fault.kicad_sch").read_bytes()
        return {"version": 1, "source_sha256": pipeline.hash_bytes(raw),
                "partitions": [], "components": list(components), "pins": [],
                "source_objects": adapter.source_objects(raw)}

    def _proposal(self, ops):
        document = {"schema_version": 1, "context_id": "ctx-1",
                    "target": "design/fault.kicad_sch",
                    "base_source_sha256": "a" * 64, "decision": "PATCH",
                    "diagnosis": [],
                    "oplist": {"protocol_version": 2, "target_format": "kicad",
                               "ops": ops}}
        return pipeline.parse_proposal(json.dumps(document).encode("utf-8"))

    def _fixture_ops(self, case):
        return json.loads((self.FIXTURES / case / "repair_ops.json")
                          .read_text(encoding="utf-8"))["ops"]

    def _labels(self, additions):
        return {row["name"]: row for row in additions["new_labels"]}

    def _component(self, reference, lib_id, position_nm, rotation=0, mirror="none"):
        return {"identity": {"reference": reference, "component_uuid": "uuid-" + reference,
                             "sheet_path": "/s", "unit": 1},
                "reference": reference, "lib_id": lib_id,
                "position_nm": list(position_nm), "rotation": rotation,
                "mirror": mirror, "unit": 1}

    def _lib_symbols(self, observation):
        return [obj for obj in observation["source_objects"]
                if obj["kind"] == "lib_symbols"][0]["descriptor"]["ast"]

    # --- new-component anchors (DC-04 / DC-05 native oracles) --------------
    def test_dc04_new_component_absent_rotation_derives_native_oracle(self):
        additions = pipeline.build_expected_after(
            self._observation("DC-04"), self._proposal(self._fixture_ops("DC-04")))
        labels = self._labels(additions)
        self.assertEqual(labels["+3V3"]["point_nm"], [34290000, 254000000])
        self.assertEqual(labels["+3V3"]["rotation"], 90)
        self.assertEqual(labels["BOOT"]["point_nm"], [34290000, 261620000])
        self.assertEqual(labels["BOOT"]["rotation"], 270)
        self.assertEqual(labels["+3V3"]["rotation_source"], "derived")
        self.assertEqual([row["role"] for row in additions["new_components"]], ["new:R9"])

    def test_dc04_explicit_zero_keeps_the_point_and_zeroes_the_angle(self):
        ops = self._fixture_ops("DC-04")
        for op in ops:
            if op["op"] == "add_net_label":
                op["rotation"] = 0
        labels = self._labels(pipeline.build_expected_after(
            self._observation("DC-04"), self._proposal(ops)))
        self.assertEqual(labels["+3V3"]["point_nm"], [34290000, 254000000])
        self.assertEqual(labels["+3V3"]["rotation"], 0)
        self.assertEqual(labels["BOOT"]["point_nm"], [34290000, 261620000])
        self.assertEqual(labels["BOOT"]["rotation"], 0)
        self.assertEqual(labels["+3V3"]["rotation_source"], "explicit")

    def test_absent_and_explicit_zero_are_different_expected_semantics(self):
        explicit_ops = self._fixture_ops("DC-04")
        for op in explicit_ops:
            if op["op"] == "add_net_label":
                op["rotation"] = 0
        absent = self._labels(pipeline.build_expected_after(
            self._observation("DC-04"), self._proposal(self._fixture_ops("DC-04"))))
        explicit = self._labels(pipeline.build_expected_after(
            self._observation("DC-04"), self._proposal(explicit_ops)))
        self.assertEqual(absent["+3V3"]["point_nm"], explicit["+3V3"]["point_nm"])
        self.assertNotEqual(absent["+3V3"]["rotation"], explicit["+3V3"]["rotation"])
        self.assertNotEqual(absent["BOOT"]["rotation"], explicit["BOOT"]["rotation"])

    def test_dc05_new_component_absent_rotation_derives_native_oracle(self):
        labels = self._labels(pipeline.build_expected_after(
            self._observation("DC-05"), self._proposal(self._fixture_ops("DC-05"))))
        self.assertEqual(labels["EN"]["point_nm"], [267970000, 33020000])
        self.assertEqual(labels["EN"]["rotation"], 90)
        self.assertEqual(labels["GND"]["point_nm"], [267970000, 40640000])
        self.assertEqual(labels["GND"]["rotation"], 270)

    # --- existing-component anchors ----------------------------------------
    def test_existing_component_anchor_derives_point_and_angle(self):
        observation = self._observation(
            "DC-04", [self._component("R3", "Device:R", (10_000_000, 20_000_000))])
        ops = [{"op": "add_net_label", "name": "NET", "at": "R3.1"}]
        labels = self._labels(pipeline.build_expected_after(observation, self._proposal(ops)))
        self.assertEqual(labels["NET"]["point_nm"], [10_000_000, 16_190_000])
        self.assertEqual(labels["NET"]["rotation"], 90)
        self.assertEqual(labels["NET"]["rotation_source"], "derived")

    def test_existing_component_anchor_explicit_zero_keeps_the_point(self):
        observation = self._observation(
            "DC-04", [self._component("R3", "Device:R", (10_000_000, 20_000_000))])
        ops = [{"op": "add_net_label", "name": "NET", "at": "R3.2", "rotation": 0}]
        labels = self._labels(pipeline.build_expected_after(observation, self._proposal(ops)))
        self.assertEqual(labels["NET"]["point_nm"], [10_000_000, 23_810_000])
        self.assertEqual(labels["NET"]["rotation"], 0)
        self.assertEqual(labels["NET"]["rotation_source"], "explicit")

    # --- fail-closed negatives ---------------------------------------------
    def test_an_anchor_with_no_owner_fails_closed(self):
        ops = [{"op": "add_net_label", "name": "NET", "at": "R7.1"}]
        with self.assertRaises(pipeline.HostContextError):
            pipeline.build_expected_after(self._observation("DC-04"), self._proposal(ops))

    def test_two_placements_of_one_reference_fail_closed(self):
        ops = self._fixture_ops("DC-04")
        ops.append(copy.deepcopy(ops[0]))
        with self.assertRaises(pipeline.HostContextError):
            pipeline.build_expected_after(self._observation("DC-04"), self._proposal(ops))

    def test_a_missing_pin_number_fails_closed(self):
        observation = self._observation(
            "DC-04", [self._component("R3", "Device:R", (10_000_000, 20_000_000))])
        ops = [{"op": "add_net_label", "name": "NET", "at": "R3.9"}]
        with self.assertRaises(pipeline.HostContextError):
            pipeline.build_expected_after(observation, self._proposal(ops))

    def test_two_components_with_one_reference_fail_closed(self):
        observation = self._observation("DC-04", [
            self._component("R3", "Device:R", (10_000_000, 20_000_000)),
            self._component("R3", "Device:R", (30_000_000, 40_000_000))])
        ops = [{"op": "add_net_label", "name": "NET", "at": "R3.1"}]
        with self.assertRaises(pipeline.HostContextError):
            pipeline.build_expected_after(observation, self._proposal(ops))

    def test_a_duplicate_library_symbol_fails_closed(self):
        observation = self._observation("DC-04")
        root = self._lib_symbols(observation)
        for symbol in [child for child in root[1:]
                       if isinstance(child, list) and child[0] == "symbol"]:
            if symbol[1].get("string") == "Device:R":
                root.append(copy.deepcopy(symbol))
        with self.assertRaises(pipeline.HostContextError):
            pipeline.build_expected_after(observation,
                                          self._proposal(self._fixture_ops("DC-04")))

    def test_a_duplicate_pin_number_fails_closed(self):
        observation = self._observation("DC-04")
        root = self._lib_symbols(observation)
        for symbol in [child for child in root[1:]
                       if isinstance(child, list) and child[0] == "symbol"]:
            if symbol[1].get("string") != "Device:R":
                continue
            for unit in [child for child in symbol[1:]
                         if isinstance(child, list) and child[0] == "symbol"]:
                pins = [child for child in unit[1:]
                        if isinstance(child, list) and child[0] == "pin"]
                if pins:
                    unit.append(copy.deepcopy(pins[0]))
        with self.assertRaises(pipeline.HostContextError):
            pipeline.build_expected_after(observation,
                                          self._proposal(self._fixture_ops("DC-04")))

    def test_a_missing_lib_symbols_object_fails_closed(self):
        observation = self._observation("DC-04")
        observation["source_objects"] = [obj for obj in observation["source_objects"]
                                         if obj["kind"] != "lib_symbols"]
        with self.assertRaises(pipeline.HostContextError):
            pipeline.build_expected_after(observation,
                                          self._proposal(self._fixture_ops("DC-04")))


class PinnedGeometryDifferentialTests(unittest.TestCase):
    """Differential proof: the C5 kernel equals pinned akcli 0.21.0 geometry.

    Opt-in (AEDL_PR1_NATIVE=1 + AEDL_AKCLI_PYTHON) because the main suite runs on
    an interpreter without the pinned toolchain installed.  This compares the
    replica against the real upstream functions over a grid of inputs, which is
    stronger than reading the upstream source and assuming they agree.  The
    composed pin-world chain is separately pinned by the DC-04/DC-05 native
    oracles in ExpectedAfterGeometryTests.
    """

    def setUp(self):
        if os.environ.get("AEDL_PR1_NATIVE") != "1":
            self.skipTest("native differential is not opted in (AEDL_PR1_NATIVE=1)")
        python = os.environ.get("AEDL_AKCLI_PYTHON")
        if not python or not os.path.isfile(python):
            self.fail("AEDL_PR1_NATIVE=1 requires AEDL_AKCLI_PYTHON to point at the pinned interpreter")
        site = os.path.join(os.path.dirname(os.path.dirname(python)), "Lib", "site-packages")
        if not os.path.isdir(site):
            self.fail("could not locate the pinned site-packages next to the interpreter")
        if site not in sys.path:
            sys.path.insert(0, site)
        try:
            from akcli.geometry import transform as pinned
        except Exception as exc:  # noqa: BLE001 - the gate must classify, not crash
            self.fail("the pinned akcli geometry is not importable: %s" % exc)
        self.pinned = pinned

    def test_transform_point_matches_the_pinned_toolchain(self):
        points = [(0, 0), (1, -1), (3810000, -3810000), (-25400, 76200), (1234567, -7654321)]
        origins = [(0, 0), (34290000, 257810000)]
        for rot in (0, 90, 180, 270):
            for mirror in ("none", "x", "y"):
                for point in points:
                    for origin in origins:
                        self.assertEqual(
                            pipeline._pinned_akcli_0210_transform_point(point, rot, mirror, origin),
                            self.pinned.transform_point(point, rot, mirror, origin),
                            (point, rot, mirror, origin))

    def test_label_angle_away_matches_the_pinned_toolchain(self):
        for orientation in (0, 90, 180, 270):
            for rot in (0, 90, 180, 270):
                for mirror in ("none", "x", "y"):
                    self.assertEqual(
                        pipeline._pinned_akcli_0210_label_angle_away(orientation, rot, mirror),
                        self.pinned.label_angle_away(orientation, rot, mirror),
                        (orientation, rot, mirror))

    def test_the_replica_is_bound_to_the_pinned_version(self):
        self.assertEqual(pipeline.PINNED_AKCLI_VERSION, "0.21.0")


NATIVE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "repair_pr1" / "native"


def real_lib_symbols_observation():
    """circuit() with the frozen fixture's real lib_symbols AST grafted in."""
    observation = circuit()
    raw = (NATIVE_FIXTURES / "DC-04" / "fault.kicad_sch").read_bytes()
    real = [obj for obj in adapter.source_objects(raw) if obj["kind"] == "lib_symbols"]
    observation["source_objects"] = [obj for obj in observation["source_objects"]
                                     if obj["kind"] != "lib_symbols"] + real
    return observation


def add_component_rule():
    """A frozen-shaped rule that adds R9 and renames two captured slots."""
    return {
        "id": "T", "route": pipeline.ROUTE_STRICT,
        "before": {"partitions": [
            {"slot": "one", "names_exact": [], "members_exact": ["R1.1"]},
            {"slot": "two", "names_exact": [], "members_exact": ["R1.2"]}]},
        "after": {
            "replace_partitions": ["one", "two"],
            "partitions": [
                {"names_exact": ["/A"], "members_from": "one", "add_exact": ["R9.1"]},
                {"names_exact": ["/B"], "members_from": "two", "add_exact": ["R9.2"]}],
            "all_other_partitions": "UNCHANGED",
            "add_components": [{
                "reference": "R9", "lib_id": "Device:R", "value": "10k",
                "footprint": "Resistor_SMD:R_0603_1608Metric",
                "position_mil": [1350, 10150], "rotation": 0, "mirror": "none",
                "unit": 1, "dnp": False, "in_bom": True, "on_board": True}]},
        "object_delta": {"remove": [], "add_labels": [
            {"name": "+3V3", "at_pin": "R9.1", "scope": "local", "rotation": 0},
            {"name": "BOOT", "at_pin": "R9.2", "scope": "local", "rotation": 0}]},
    }


def add_component_ops(labels=("+3V3", "BOOT"), explicit_zero=False):
    ops = [{"op": "place_component", "lib_id": "Device:R", "designator": "R9",
            "x_mil": 1350, "y_mil": 10150, "value": "10k",
            "footprint": "Resistor_SMD:R_0603_1608Metric"}]
    for index, name in enumerate(labels):
        op = {"op": "add_net_label", "name": name, "at": "R9.%d" % (index + 1)}
        if explicit_zero:
            op["rotation"] = 0
        ops.append(op)
    return ops


class BoundPolicyTests(unittest.TestCase):
    """Checkpoint 2: _bound_policy specializes the policy and never authorizes."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        (self.design / TARGET).write_bytes(b"(kicad_sch)")
        self.context = pipeline.validate_host_context(
            host_context(design_root=str(self.root / "cand")))
        self.observation = real_lib_symbols_observation()
        self.rule = add_component_rule()
        self.proposal = self._proposal(add_component_ops())
        self.additions = pipeline.build_expected_after(self.observation, self.proposal)
        self.runtime = pipeline.runtime_bindings(
            self.context, self.proposal, native_before(observation=self.observation),
            policy_sha(), {"E1"}, rule=self.rule, removals={})

    def tearDown(self):
        self._tmp.cleanup()

    def _proposal(self, ops):
        document = {"schema_version": 1, "context_id": CONTEXT, "target": TARGET,
                    "base_source_sha256": "b" * 64, "decision": "PATCH",
                    "diagnosis": [], "oplist": {"protocol_version": 2,
                                                "target_format": "kicad", "ops": ops}}
        return pipeline.parse_proposal(json.dumps(document).encode("utf-8"))

    def _bound(self, runtime=None, additions=None):
        return pipeline._bound_policy(
            self.observation, self.rule, self.runtime if runtime is None else runtime,
            self.additions if additions is None else additions, pipeline.ROUTE_STRICT)

    # --- 1: determinism -----------------------------------------------------
    def test_the_same_inputs_produce_a_byte_identical_bound_policy(self):
        first = pipeline.canonical_json_bytes(self._bound())
        second = pipeline.canonical_json_bytes(self._bound())
        self.assertEqual(first, second)

    # --- 2: no transaction identity leaks into the bound policy -------------
    def test_transaction_identity_stays_in_the_runtime_bindings(self):
        bound = self._bound()
        self.assertEqual(set(bound), set(pipeline._C2_BOUND_FIELDS))
        for leaked in ("run_id", "candidate_id", "round_id", "patch_id",
                       "proposal_sha256", "authority_context"):
            self.assertNotIn(leaked, bound)
        self.assertEqual(bound["rule_id"], "T")
        self.assertEqual(bound["route"], pipeline.ROUTE_STRICT)
        self.assertEqual(bound["policy_file_sha256"], self.runtime["policy_document_sha256"])
        self.assertEqual(bound["authority_context_digest"],
                         self.runtime["authority_context"]["context_digest"])
        self.assertEqual(bound["before_topology_sha256"],
                         self.runtime["base_topology_sha256"])

    # --- 3: expected_after geometry comes from CP1 alone --------------------
    def test_label_semantics_are_the_exact_c2_four_tuple(self):
        bound = self._bound()
        labels = [obj for obj in bound["expected_after"]["source_objects"]
                  if obj["kind"] == "label"]
        self.assertEqual(len(labels), len(self.additions["new_labels"]))
        for obj, addition in zip(sorted(labels, key=lambda o: o["identity"]),
                                 sorted(self.additions["new_labels"],
                                        key=lambda r: r["role"])):
            self.assertEqual(set(obj["semantics"]),
                             {"name", "scope", "point_nm", "rotation"})
            self.assertNotIn("rotation_source", obj["semantics"])
            self.assertEqual(obj["semantics"]["rotation"], addition["rotation"])
            self.assertEqual(obj["semantics"]["point_nm"], addition["point_nm"])

    def test_absent_rotation_still_derives_the_native_angle(self):
        bound = self._bound()
        labels = {obj["semantics"]["name"]: obj["semantics"]
                  for obj in bound["expected_after"]["source_objects"]
                  if obj["kind"] == "label"}
        self.assertEqual(labels["+3V3"]["rotation"], 90)
        self.assertEqual(labels["BOOT"]["rotation"], 270)

    # --- 4: identity maps are consumed, not re-derived ----------------------
    def test_identity_maps_are_the_runtime_bindings_unchanged(self):
        bound = self._bound()
        self.assertIs(bound["pin_identity_map"], self.runtime["pin_identity_map"])
        self.assertIs(bound["object_identity_map"], self.runtime["object_identity_map"])

    # --- 5/6: runtime binding set is closed and complete --------------------
    def test_a_missing_runtime_binding_fails_closed(self):
        broken = dict(self.runtime)
        broken.pop("pin_identity_map")
        with self.assertRaises(pipeline.HostContextError):
            self._bound(runtime=broken)

    def test_an_unknown_runtime_binding_is_refused(self):
        broken = dict(self.runtime, authorized=True)
        with self.assertRaises(pipeline.HostContextError) as caught:
            self._bound(runtime=broken)
        self.assertIn("outside the frozen set", caught.exception.findings[0].detail)

    # --- 7: no grant, no allow ----------------------------------------------
    def test_the_bound_policy_carries_no_grant_or_allow(self):
        bound = self._bound()
        for forbidden in ("authorized", "allowed", "grant", "approvals", "decisions"):
            self.assertNotIn(forbidden, bound)

    # --- 8: new component row + unanimous definitions -----------------------
    def test_the_new_component_row_uses_unanimous_library_digests(self):
        bound = self._bound()
        added = [c for c in bound["expected_after"]["components"]
                 if c["identity"]["component_uuid"] == "new:R9"]
        self.assertEqual(len(added), 1)
        row = added[0]
        self.assertEqual(row["lib_id"], "Device:R")
        self.assertEqual(row["lib_definition_sha256"], "1" * 64)
        self.assertEqual(row["pin_definition_sha256"], "2" * 64)
        self.assertEqual(row["value"], "10k")
        self.assertEqual(row["position_nm"], [1350 * 25400, 10150 * 25400])
        self.assertEqual(bound["new_component_roles"],
                         {"new:R9": {"reference": "R9", "pin_numbers": ["1", "2"]}})

    def test_a_lib_id_without_an_existing_instance_fails_closed(self):
        # circuit() carries only Device:R, so a new Device:C has no existing
        # instance to source its library definition digests from.
        rule = add_component_rule()
        rule["after"]["add_components"][0]["lib_id"] = "Device:C"
        rule["after"]["add_components"][0]["reference"] = "C9"
        ops = add_component_ops()
        ops[0]["lib_id"] = "Device:C"
        ops[0]["designator"] = "C9"
        for index in range(1, len(ops)):
            ops[index]["at"] = "C9.%d" % index
        additions = pipeline.build_expected_after(self.observation, self._proposal(ops))
        self.assertEqual(additions["new_components"][0]["lib_id"], "Device:C")
        with self.assertRaises(pipeline.HostContextError) as caught:
            pipeline._bound_policy(self.observation, rule, self.runtime, additions,
                                   pipeline.ROUTE_STRICT)
        self.assertIn("Device:C", caught.exception.findings[0].detail)

    def test_disagreeing_library_digests_fail_closed(self):
        observation = real_lib_symbols_observation()
        observation["components"][1]["lib_definition_sha256"] = "9" * 64
        with self.assertRaises(pipeline.HostContextError):
            pipeline._bound_policy(observation, self.rule, self.runtime,
                                   self.additions, pipeline.ROUTE_STRICT)

    # --- B1: removal declarations bind by UUID, kind and descriptor ---------
    def _observation_with_removable_label(self):
        observation = real_lib_symbols_observation()
        identity = "aaaaaaaa-1111-2222-3333-444444444444"
        ast = ["label", {"string": "OLD"},
               ["at", {"number": "1"}, {"number": "2"}, {"number": "0"}],
               ["uuid", {"string": identity}]]
        observation["source_objects"].append({
            "identity": identity, "kind": "label",
            "semantic_ast_sha256": pipeline.canonical_sha256("protected", ast),
            "descriptor": {"ast": ast}})
        return observation, identity, pipeline.canonical_sha256("protected", {"ast": ast})

    def _removal_case(self, uuid, kind, digest):
        observation, identity, real_digest = self._observation_with_removable_label()
        rule = add_component_rule()
        rule["object_delta"]["remove"] = [{"slot": "old"}]
        removals = {"old": {"uuid": identity if uuid is None else uuid,
                            "kind": kind, "descriptor_sha256": real_digest if digest is None else digest}}
        runtime = pipeline.runtime_bindings(
            self.context, self.proposal, native_before(observation=observation),
            policy_sha(), {"E1"}, rule=rule, removals=removals)
        additions = pipeline.build_expected_after(observation, self.proposal)
        return observation, rule, runtime, additions, identity

    def test_removal_declarations_bind_by_uuid_and_are_consumed(self):
        observation, rule, runtime, additions, identity = self._removal_case(None, "label", None)
        bound = pipeline._bound_policy(observation, rule, runtime, additions,
                                       pipeline.ROUTE_STRICT)
        remaining = [obj["identity"] for obj in bound["expected_after"]["source_objects"]]
        self.assertNotIn(identity, remaining)
        hits = [row for row in bound["authorized_delta"] if row["identity"] == identity]
        self.assertTrue(hits)
        self.assertEqual(hits[0]["after"], {"absent": True})
        self.assertEqual(bound["operation_constraints"]["counts"]["delete_object"], 1)
        self.assertEqual(bound["operation_constraints"]["removed"][0]["uuid"], identity)
        self.assertEqual(
            bound["operation_constraints"]["canonical_authorized_ops"][0]["op"],
            "delete_object")
        self.assertEqual(bound["authorized_delta_sha256"],
                         pipeline.canonical_sha256("delta", bound["authorized_delta"]))
        self.assertEqual(bound["protected_projection_sha256"],
                         pipeline.protected_projection_sha256(observation, bound))

    def test_a_removal_uuid_that_matches_nothing_fails_closed(self):
        observation, rule, runtime, additions, _ = self._removal_case(
            "00000000-0000-0000-0000-000000000000", "label", None)
        with self.assertRaises(pipeline.HostContextError):
            pipeline._bound_policy(observation, rule, runtime, additions,
                                   pipeline.ROUTE_STRICT)

    def test_a_removal_descriptor_mismatch_fails_closed(self):
        observation, rule, runtime, additions, _ = self._removal_case(None, "label", "9" * 64)
        with self.assertRaises(pipeline.HostContextError):
            pipeline._bound_policy(observation, rule, runtime, additions,
                                   pipeline.ROUTE_STRICT)

    def test_a_removal_kind_mismatch_fails_closed(self):
        observation, rule, runtime, additions, _ = self._removal_case(None, "wire", None)
        with self.assertRaises(pipeline.HostContextError):
            pipeline._bound_policy(observation, rule, runtime, additions,
                                   pipeline.ROUTE_STRICT)

    def test_an_ambiguous_removal_identity_fails_closed(self):
        # Two removal slots naming the SAME uuid is the reachable ambiguity:
        # _expected_observation must refuse rather than delete one object twice.
        # runtime_bindings also rejects it, so the runtime here is built by hand
        # to exercise the C2 layer's own guard (defence in depth, not a bypass).
        observation, identity, digest = self._observation_with_removable_label()
        rule = add_component_rule()
        rule["object_delta"]["remove"] = [{"slot": "old"}, {"slot": "old_again"}]
        entry = {"uuid": identity, "kind": "label", "descriptor_sha256": digest}
        runtime = dict(self.runtime)
        runtime["object_identity_map"] = {"old": dict(entry),
                                          "old_again": dict(entry)}
        additions = pipeline.build_expected_after(observation, self.proposal)
        with self.assertRaises(pipeline.HostContextError) as caught:
            pipeline._bound_policy(observation, rule, runtime, additions,
                                   pipeline.ROUTE_STRICT)
        self.assertIn("two removal declarations", caught.exception.findings[0].detail)

    def test_a_duplicated_before_object_identity_fails_closed_upstream(self):
        # The other half of the ambiguity question: two source objects with one
        # uuid cannot even reach C2, because normalize_observation refuses a
        # duplicate identity. Documented here so the len(matches) != 1 branch is
        # not mistaken for the only defence.
        observation = real_lib_symbols_observation()
        identity = "bbbbbbbb-1111-2222-3333-444444444444"
        ast = ["label", {"string": "OLD"},
               ["at", {"number": "1"}, {"number": "2"}, {"number": "0"}],
               ["uuid", {"string": identity}]]
        duplicate = {"identity": identity, "kind": "label",
                     "semantic_ast_sha256": pipeline.canonical_sha256("protected", ast),
                     "descriptor": {"ast": ast}}
        observation["source_objects"].append(dict(duplicate))
        observation["source_objects"].append(dict(duplicate))
        with self.assertRaises(Exception) as caught:
            pipeline.normalize_observation(observation)
        self.assertIn("duplicate source object", str(caught.exception))

    # --- B2: the frozen expected-source sentinel ---------------------------
    def test_the_expected_source_sentinel_is_the_frozen_value(self):
        self.assertEqual(
            pipeline._EXPECTED_SOURCE_SHA256,
            pipeline.canonical_sha256("context", {"role": "EXPECTED_AFTER_NOT_YET_WRITTEN"}))

    def test_the_expected_source_sentinel_is_the_frozen_literal(self):
        # Pins the exact byte value so a future edit to the role string, the hash
        # domain or the domain separator cannot silently change the sentinel
        # while the derived-form assertion above still passes.
        self.assertEqual(
            pipeline._EXPECTED_SOURCE_SHA256,
            "fff0e440cb44467f19b71b82145e64cf86585a37c334c091bb6769f806479771")

    # --- B3: operation_constraints is a real specialization -----------------
    def test_operation_constraints_carry_the_canonical_authorized_ops(self):
        constraints = self._bound()["operation_constraints"]
        self.assertEqual(constraints["stage_order"],
                         ["delete_object", "place_component", "add_net_label"])
        self.assertEqual(constraints["counts"],
                         {"delete_object": 0, "place_component": 1, "add_net_label": 2})
        self.assertEqual([op["op"] for op in constraints["canonical_authorized_ops"]],
                         ["place_component", "add_net_label", "add_net_label"])
        self.assertEqual([row["rotation_key"] for row in constraints["new_labels"]],
                         ["ABSENT", "ABSENT"])
        for op in constraints["canonical_authorized_ops"]:
            if op["op"] == "add_net_label":
                self.assertNotIn("rotation", op)
                self.assertEqual(op["scope"], "local")

    def test_the_frozen_proposal_matches_the_canonical_ops(self):
        canonical = self._bound()["operation_constraints"]["canonical_authorized_ops"]
        normalized = [pipeline._parse_op(op, "$.ops") for op in self.proposal.ops]
        self.assertEqual(normalized, canonical)

    def test_an_explicit_rotation_proposal_does_not_match_the_canonical_ops(self):
        proposal = self._proposal(add_component_ops(explicit_zero=True))
        additions = pipeline.build_expected_after(self.observation, proposal)
        bound = pipeline._bound_policy(self.observation, self.rule, self.runtime,
                                       additions, pipeline.ROUTE_STRICT)
        canonical = bound["operation_constraints"]["canonical_authorized_ops"]
        normalized = [pipeline._parse_op(op, "$.ops") for op in proposal.ops]
        self.assertNotEqual(normalized, canonical)

    # --- 9: no authorization call inside _bound_policy ----------------------
    def test_bound_policy_contains_no_authorization_call(self):
        import inspect
        source = inspect.getsource(pipeline._bound_policy)
        for forbidden in ("PolicyPort", "evaluate", "EFFECT_ALLOW", "CAPABILITY_",
                          "authorized=True", "approvals"):
            self.assertNotIn(forbidden, source)

    # --- 10: the expectation itself normalizes ------------------------------
    def test_the_expected_after_passes_c2_normalization_directly(self):
        bound = self._bound()
        normalized = pipeline.normalize_observation(bound["expected_after"], expected=True)
        self.assertTrue(normalized["coverage"]["complete"])
        self.assertEqual(bound["authorized_delta_sha256"],
                         pipeline.canonical_sha256("delta", bound["authorized_delta"]))
        self.assertEqual(
            bound["protected_projection_sha256"],
            pipeline.protected_projection_sha256(self.observation, bound))


class HostPatchTests(unittest.TestCase):
    """Checkpoint 3: _host_patch assembles the transaction envelope, authorizes nothing."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        (self.design / TARGET).write_bytes(b"(kicad_sch)")
        self.context = pipeline.validate_host_context(
            host_context(design_root=str(self.root / "cand")))
        self.observation = real_lib_symbols_observation()
        self.rule = add_component_rule()
        self.proposal = self._proposal(add_component_ops())
        self.additions = pipeline.build_expected_after(self.observation, self.proposal)
        self.runtime = pipeline.runtime_bindings(
            self.context, self.proposal, native_before(observation=self.observation),
            policy_sha(), {self.rule["id"]}, rule=self.rule, removals={})
        self.bound = pipeline._bound_policy(
            self.observation, self.rule, self.runtime, self.additions,
            pipeline.ROUTE_STRICT)

    def tearDown(self):
        self._tmp.cleanup()

    def _proposal(self, ops):
        document = {"schema_version": 1, "context_id": CONTEXT, "target": TARGET,
                    "base_source_sha256": "b" * 64, "decision": "PATCH",
                    "diagnosis": [], "oplist": {"protocol_version": 2,
                                                "target_format": "kicad", "ops": ops}}
        return pipeline.parse_proposal(json.dumps(document).encode("utf-8"))

    def _patch(self, runtime=None, bound=None, proposal=None, policy_document=None):
        return pipeline._host_patch(
            self.context, self.proposal if proposal is None else proposal,
            self.runtime if runtime is None else runtime,
            self.bound if bound is None else bound,
            policy() if policy_document is None else policy_document)

    # --- 1: the canonical digest is deterministic ----------------------------
    def test_the_same_inputs_produce_a_byte_identical_host_patch(self):
        first = pipeline.canonical_json_bytes(self._patch())
        second = pipeline.canonical_json_bytes(self._patch())
        self.assertEqual(first, second)

    def test_the_patch_digest_covers_every_field_but_itself(self):
        patch = self._patch()
        body = {key: value for key, value in patch.items() if key != "patch_sha256"}
        self.assertEqual(patch["patch_sha256"], pipeline.canonical_sha256("patch", body))
        tampered = dict(patch, run_id="run-OTHER")
        self.assertNotEqual(patch["patch_sha256"],
                            pipeline.canonical_sha256(
                                "patch", {k: v for k, v in tampered.items()
                                          if k != "patch_sha256"}))

    def test_the_patch_field_set_matches_the_frozen_schema(self):
        # The three independent statements of the contract must agree: the frozen
        # schema, C4's reader, and what CP3 assembles.  Drift here would mean C5
        # emits a patch C4 silently refuses.
        import json as _json
        schema = _json.loads(
            (Path(pipeline.PATCH_SCHEMA_PATH)).read_text(encoding="utf-8"))
        definition = schema["$defs"]["HostPatch"]
        self.assertEqual(set(patch_fields := set(self._patch())),
                         set(definition["required"]))
        self.assertEqual(set(patch_fields), set(definition["properties"]))
        self.assertEqual(set(patch_fields), set(adapter._HOST_PATCH_FIELDS))
        self.assertIs(definition.get("additionalProperties"), False)

    # --- 2: the transaction identity is complete and host-derived ------------
    def test_the_transaction_identity_is_complete(self):
        patch = self._patch()
        for field in ("run_id", "candidate_id", "round_id", "patch_id", "context_id"):
            self.assertIn(patch[field], (RUN, CAND, ROUND, PATCH, CONTEXT))
        self.assertEqual(patch["run_id"], self.runtime["run_id"])
        self.assertEqual(patch["candidate_id"], self.runtime["candidate_id"])
        self.assertEqual(patch["round_id"], self.runtime["round_id"])
        self.assertEqual(patch["patch_id"], self.runtime["patch_id"])
        self.assertEqual(patch["context_id"], self.context["context_id"])

    def test_the_proposal_cannot_inject_its_own_identity(self):
        # The proposal is a candidate: the identity comes from the host runtime.
        # A proposal whose context/target disagree is refused, not repaired.
        other = self._proposal(add_component_ops())
        document = {"schema_version": 1, "context_id": "ctx-OTHER", "target": TARGET,
                    "base_source_sha256": "b" * 64, "decision": "PATCH",
                    "diagnosis": [], "oplist": {"protocol_version": 2,
                                                "target_format": "kicad",
                                                "ops": add_component_ops()}}
        foreign = pipeline.parse_proposal(json.dumps(document).encode("utf-8"))
        with self.assertRaises(pipeline.HostContextError) as caught:
            self._patch(proposal=foreign)
        self.assertIn("context", caught.exception.findings[0].detail)
        self.assertIsNotNone(other)

    # --- 3: the bound policy digest binds THIS bound policy -----------------
    def test_the_bound_policy_digest_binds_the_exact_bound_policy(self):
        patch = self._patch()
        # "policy-bound" is the frozen digest kind the C3/C4 consumer already
        # uses for a bound policy (repair_verification), not a new one: an
        # invented kind would still be accepted by canonical_sha256 only if it
        # were added to DIGEST_KINDS, and would then disagree with C4.
        self.assertEqual(patch["policy"]["bound_policy_sha256"],
                         pipeline.canonical_sha256("policy-bound", patch["bound_policy"]))
        self.assertEqual(patch["policy"]["bound_rule_id"], self.bound["rule_id"])
        self.assertEqual(patch["bound_policy"], self.bound)

    def test_the_digest_kind_is_one_the_contract_already_freezes(self):
        from gates.repair_verification import DIGEST_KINDS
        for kind in ("policy-bound", "proposal", "patch"):
            self.assertIn(kind, DIGEST_KINDS)

    def test_a_bound_policy_from_another_transaction_fails_closed(self):
        foreign = dict(self.bound, policy_file_sha256="9" * 64)
        with self.assertRaises(pipeline.HostContextError) as caught:
            self._patch(bound=foreign)
        self.assertIn("policy digest", caught.exception.findings[0].detail)

    def test_a_bound_policy_for_an_unapproved_rule_fails_closed(self):
        foreign = dict(self.bound, rule_id="E9")
        with self.assertRaises(pipeline.HostContextError) as caught:
            self._patch(bound=foreign)
        self.assertIn("not among the host-approved", caught.exception.findings[0].detail)

    # --- 4: expected_after is bound into the patch -------------------------
    def test_the_expected_after_is_carried_and_bounded(self):
        patch = self._patch()
        expected = patch["bound_policy"]["expected_after"]
        self.assertEqual(expected, self.bound["expected_after"])
        self.assertEqual(expected["source_sha256"], pipeline._EXPECTED_SOURCE_SHA256)
        # The expectation still answers C2 on its own, inside the patch.
        normalized = pipeline.normalize_observation(expected, expected=True)
        self.assertTrue(normalized["coverage"]["complete"])

    # --- 5: host context comes from the host, never from the proposal -------
    def test_the_base_manifest_and_topology_come_from_the_runtime(self):
        patch = self._patch()
        self.assertEqual(patch["base"]["files"], self.runtime["base_file_manifest"])
        self.assertEqual(patch["base"]["topology_sha256"],
                         self.runtime["base_topology_sha256"])
        self.assertEqual(patch["proposal_sha256"], self.runtime["proposal_sha256"])
        self.assertEqual(patch["policy"]["file_sha256"],
                         self.runtime["policy_document_sha256"])

    def test_incomplete_runtime_bindings_fail_closed(self):
        broken = dict(self.runtime)
        broken.pop("base_file_manifest")
        with self.assertRaises(pipeline.HostContextError) as caught:
            self._patch(runtime=broken)
        self.assertIn("frozen set", caught.exception.findings[0].detail)

    def test_the_authority_without_a_resolved_reference_fails_closed(self):
        runtime = dict(self.runtime)
        runtime["authority_context"] = authority(resolved_authorization_refs=[])
        with self.assertRaises(pipeline.HostContextError) as caught:
            self._patch(runtime=runtime)
        self.assertIn("no resolved authorization", caught.exception.findings[0].detail)

    # --- 6: the fake authorization fields are refused ------------------------
    def test_a_forged_capability_decision_is_refused(self):
        # A decision row carrying anything beyond {capability, effect} -- e.g. an
        # `authorized` flag or a `file_write` switch -- is not a decision this
        # contract knows how to carry.
        runtime = dict(self.runtime)
        runtime["authority_context"] = authority(decisions=[
            {"capability": pipeline.CAPABILITY_FILE_WRITE,
             "effect": pipeline.EFFECT_ALLOW, "authorized": True}])
        with self.assertRaises(pipeline.HostContextError):
            self._patch(runtime=runtime)

    def test_forged_fields_on_the_patch_itself_are_refused_by_the_frozen_reader(self):
        # CP3 cannot emit them (the field set is closed). Prove the C4 reader also
        # refuses, so a hand-built patch cannot smuggle an authorization in.
        # C4 reports a refused stage as a BLOCKED result, not an exception, so the
        # rejection is asserted on the receipt -- the artifact a caller sees.
        patch = self._patch()
        for forged in ({"authorized": True}, {"file_write": True}, {"tool_execute": True}):
            name, value = next(iter(forged.items()))
            result = adapter.apply_stage(
                {"host_patch": dict(patch, **forged), "txn_id": "TXN-1",
                 "stage_root": str(self.root), "stage_target": TARGET,
                 "oplist_path": str(self.root / "ops.json"),
                 "native_artifact_root": str(self.root / "art")})
            self.assertEqual(result["status"], "BLOCKED", forged)
            detail = " ".join(reason["detail"] for reason in result["reasons"])
            self.assertIn("unknown fields", detail)
            self.assertIn(name, detail)

    # --- 7: the toolchain identity is metadata, never a decision ------------
    def test_the_toolchain_identity_is_carried_as_metadata(self):
        patch = self._patch()
        self.assertEqual(patch["toolchain_manifest"], self.runtime["toolchain_manifest"])
        from tools import host_toolchain
        self.assertEqual(patch["toolchain_sha256"],
                         host_toolchain.toolchain_slice_sha256(patch["toolchain_manifest"]))

    def test_the_host_patch_contains_no_authorization_call(self):
        import inspect
        source = inspect.getsource(pipeline._host_patch)
        # Scan executable code only. The docstring states the prohibition in
        # prose and a comment explains it, so a raw substring scan would match
        # the very rule it is meant to enforce. Strip the docstring, then the
        # comments, and keep only code.
        body = source.split('"""', 2)[-1]
        code = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
        for forbidden in ("PolicyPort", "evaluate", "EFFECT_ALLOW", "CAPABILITY_",
                          "authorized=True", "file_write", "tool_execute"):
            self.assertNotIn(forbidden, code)

    def test_the_authority_view_does_not_re_export_the_host_approvals(self):
        # CP3 carries the host's decision, not the host's approval surface.
        patch = self._patch()
        self.assertEqual(set(patch["authority"]),
                         set(pipeline._HOST_PATCH_AUTHORITY_FIELDS))
        self.assertNotIn("approvals", patch["authority"])
        self.assertNotIn("approvals", json.dumps(patch["authority"]))

    # --- policy identity: one transaction, one policy identity (CP4-A input) --
    def test_the_policy_id_comes_from_the_loaded_policy_document(self):
        patch = self._patch()
        document = policy()
        self.assertEqual(patch["policy"]["id"], document["policy_id"])
        self.assertEqual(patch["policy"]["file_sha256"],
                         pipeline._policy_document_sha256(document))

    def test_the_policy_id_is_bound_by_the_policy_digest(self):
        # policy_id lives inside the hashed document bytes, so a digest can only
        # ever carry one policy identity. That is why CP4 may read the identity
        # from the document instead of needing a second source.
        document = policy()
        self.assertIn(document["policy_id"].encode("utf-8"),
                      pipeline.canonical_json_bytes(document))
        self.assertNotEqual(pipeline._policy_document_sha256(document),
                            pipeline._policy_document_sha256(
                                dict(document, policy_id="SOME_OTHER_POLICY")))

    def test_a_policy_document_from_another_transaction_fails_closed(self):
        # A document that is internally valid but is not the one this
        # transaction bound must not be able to name the policy.
        foreign = dict(policy())
        foreign["policy_id"] = "AEDL_PR1_TOPOLOGY_V1_OTHER"
        with self.assertRaises(pipeline.HostContextError) as caught:
            self._patch(policy_document=foreign)
        self.assertIn("does not match this transaction's policy digest",
                      caught.exception.findings[0].detail)

    def test_a_policy_document_without_an_id_fails_closed(self):
        stripped = {key: value for key, value in policy().items() if key != "policy_id"}
        with self.assertRaises(pipeline.HostContextError):
            self._patch(policy_document=stripped)


class AuthorizationResolverTests(unittest.TestCase):
    """CP4-A: authorization is resolved from the HOST, never from the proposal."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        (self.design / TARGET).write_bytes(b"(kicad_sch)")
        self.context = pipeline.validate_host_context(
            host_context(design_root=str(self.root / "cand")))
        self.rule = add_component_rule()

    def _context_approving(self, rule_id=None, run_id=RUN, candidate_id=CAND):
        """A host context whose approval actually binds this rule/run/candidate."""
        return pipeline.validate_host_context(host_context(
            design_root=str(self.root / "cand"),
            authority=authority(approvals=[
                {"policy_file_sha256": policy_sha(),
                 "rule_id": rule_id or self.rule["id"],
                 "run_id": run_id, "candidate_id": candidate_id,
                 "paths": [abs_path("cand")]}])))

    def tearDown(self):
        self._tmp.cleanup()

    def _proposal_document(self, **extra):
        document = {"schema_version": 1, "context_id": CONTEXT, "target": TARGET,
                    "base_source_sha256": "b" * 64, "decision": "PATCH",
                    "diagnosis": [], "oplist": {"protocol_version": 2,
                                                "target_format": "kicad",
                                                "ops": add_component_ops()}}
        document.update(extra)
        return pipeline.parse_proposal(json.dumps(document).encode("utf-8"))

    # --- the Owner-specified negative: a claiming proposal, no host grant ----
    def test_a_proposal_claiming_authorization_is_blocked(self):
        # proposal: {authorized: true, file_write: true}; host: no grant.
        # The forged fields are not merely ignored -- the proposal parser refuses
        # the document outright, so a candidate cannot even reach the resolver
        # carrying its own permission claim.
        with self.assertRaises(pipeline.ProposalInvalidError):
            self._proposal_document(authorized=True, file_write=True,
                                    tool_execute=True)
        result = pipeline.resolve_authorization(self.context, policy(), self.rule)
        self.assertEqual(result["status"], pipeline.AUTH_BLOCKED)
        self.assertTrue(result["findings"])

    def test_the_proposal_is_not_an_input_to_the_resolver(self):
        import inspect
        signature = inspect.signature(pipeline.resolve_authorization)
        self.assertNotIn("proposal", signature.parameters)

    def test_a_deny_decision_blocks(self):
        # TOOL_EXECUTE stays ALLOW and the rule IS approved, so the ONLY reason
        # left to block is the FILE_WRITE denial. This isolates the decision
        # check: without it the resolver would pass.
        context = pipeline.validate_host_context(host_context(
            design_root=str(self.root / "cand"),
            authority=authority(
                decisions=[{"capability": pipeline.CAPABILITY_TOOL_EXECUTE,
                            "effect": pipeline.EFFECT_ALLOW},
                           {"capability": pipeline.CAPABILITY_FILE_WRITE,
                            "effect": "DENY"}],
                approvals=[{"policy_file_sha256": policy_sha(),
                            "rule_id": self.rule["id"], "run_id": RUN,
                            "candidate_id": CAND, "paths": [abs_path("cand")]}])))
        result = pipeline.resolve_authorization(context, policy(), self.rule)
        self.assertEqual(result["status"], pipeline.AUTH_BLOCKED)
        self.assertEqual(len(result["findings"]), 1)
        self.assertIn(pipeline.CAPABILITY_FILE_WRITE, result["findings"][0].detail)

    def test_a_missing_decision_blocks_and_is_not_silently_allowed(self):
        # Only FILE_WRITE is decided; TOOL_EXECUTE is absent entirely. A missing
        # decision is not an allow.
        context = pipeline.validate_host_context(host_context(
            design_root=str(self.root / "cand"),
            authority=authority(
                decisions=[{"capability": pipeline.CAPABILITY_FILE_WRITE,
                            "effect": pipeline.EFFECT_ALLOW}],
                approvals=[{"policy_file_sha256": policy_sha(),
                            "rule_id": self.rule["id"], "run_id": RUN,
                            "candidate_id": CAND, "paths": [abs_path("cand")]}])))
        result = pipeline.resolve_authorization(context, policy(), self.rule)
        self.assertEqual(result["status"], pipeline.AUTH_BLOCKED)
        self.assertIn(pipeline.CAPABILITY_TOOL_EXECUTE, result["findings"][0].detail)

    def test_a_resolved_authority_passes_and_reports_the_capabilities(self):
        context = self._context_approving()
        result = pipeline.resolve_authorization(context, policy(), self.rule)
        self.assertEqual(result["status"], pipeline.AUTH_PASS)
        self.assertEqual(result["capabilities"],
                         {pipeline.CAPABILITY_TOOL_EXECUTE: pipeline.EFFECT_ALLOW,
                          pipeline.CAPABILITY_FILE_WRITE: pipeline.EFFECT_ALLOW})
        self.assertEqual(result["authorization_refs"], ["grant-1"])
        self.assertEqual(result["policy_sha256"], policy_sha())
        self.assertEqual(result["rule_id"], self.rule["id"])

    def test_an_unapproved_rule_is_blocked_even_with_a_full_authority(self):
        # The authority allows the capabilities, but no approval binds this rule
        # to this policy digest, run and candidate.
        context = pipeline.validate_host_context(
            host_context(design_root=str(self.root / "cand"),
                         authority=authority(approvals=[])))
        result = pipeline.resolve_authorization(context, policy(), self.rule)
        self.assertEqual(result["status"], pipeline.AUTH_BLOCKED)
        self.assertIn("no host approval binds rule", result["findings"][0].detail)

    def test_an_approval_for_another_run_does_not_transfer(self):
        context = self._context_approving(run_id="run-OTHER")
        result = pipeline.resolve_authorization(context, policy(), self.rule)
        self.assertEqual(result["status"], pipeline.AUTH_BLOCKED)
        self.assertIn("no host approval binds rule", result["findings"][0].detail)

    def test_an_uncovered_write_path_is_blocked(self):
        context = self._context_approving()
        result = pipeline.resolve_authorization(
            context, policy(), self.rule,
            required_paths=[abs_path("somewhere/else")])
        self.assertEqual(result["status"], pipeline.AUTH_BLOCKED)
        self.assertIn("write path", result["findings"][0].detail)

    def test_blocked_and_unknown_are_distinct_states(self):
        # A denial is BLOCKED; a state that cannot be resolved is UNKNOWN.
        # Collapsing them would make "we could not tell" indistinguishable from
        # "the host said no". Asserted on the literal values, because a rename
        # that merged the two would otherwise pass silently.
        self.assertEqual((pipeline.AUTH_PASS, pipeline.AUTH_BLOCKED,
                          pipeline.AUTH_UNKNOWN), ("PASS", "BLOCKED", "UNKNOWN"))
        self.assertEqual(len({pipeline.AUTH_PASS, pipeline.AUTH_BLOCKED,
                              pipeline.AUTH_UNKNOWN}), 3)

    def test_an_unnamed_rule_raises_rather_than_returning_a_verdict(self):
        # An exception must not be swallowed into a decision.
        with self.assertRaises(pipeline.HostContextError):
            pipeline.resolve_authorization(self.context, policy(), {})

    def test_a_malformed_authority_raises_rather_than_returning_a_verdict(self):
        with self.assertRaises(pipeline.HostContextError):
            pipeline.validate_host_context(
                host_context(design_root=str(self.root / "cand"),
                             authority=authority(decisions=[{"capability": "NOT_A_CAP",
                                                             "effect": "ALLOW"}])))

    def test_the_resolver_does_not_reach_for_a_grant_ledger(self):
        import inspect
        source = inspect.getsource(pipeline.resolve_authorization)
        body = source.split('"""', 2)[-1]
        code = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
        for forbidden in ("proposal", "ledger", "open(", "requests", "urlopen"):
            self.assertNotIn(forbidden, code)


class ToolchainQualificationTests(unittest.TestCase):
    """CP4-B: the toolchain identity CP3 carried as metadata is now enforced."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        (self.design / TARGET).write_bytes(b"(kicad_sch)")
        self.context = pipeline.validate_host_context(
            host_context(design_root=str(self.root / "cand")))
        self.observation = real_lib_symbols_observation()
        self.rule = add_component_rule()
        self.proposal = self._proposal(add_component_ops())
        self.runtime = pipeline.runtime_bindings(
            self.context, self.proposal, native_before(observation=self.observation),
            policy_sha(), {self.rule["id"]}, rule=self.rule, removals={})

    def tearDown(self):
        self._tmp.cleanup()

    def _proposal(self, ops):
        document = {"schema_version": 1, "context_id": CONTEXT, "target": TARGET,
                    "base_source_sha256": "b" * 64, "decision": "PATCH",
                    "diagnosis": [], "oplist": {"protocol_version": 2,
                                                "target_format": "kicad", "ops": ops}}
        return pipeline.parse_proposal(json.dumps(document).encode("utf-8"))

    def _runtime_with_toolchain(self, mutate):
        from tools import host_toolchain
        manifest = json.loads(json.dumps(self.runtime["toolchain_manifest"]))
        mutate(manifest)
        return dict(self.runtime, toolchain_manifest=manifest,
                    toolchain_sha256=None)

    # --- the qualified toolchain passes -------------------------------------
    def test_the_qualified_toolchain_passes(self):
        result = pipeline.qualify_toolchain(self.context, self.runtime)
        self.assertEqual(result["status"], pipeline.TOOLCHAIN_PASS)
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["pinned_akcli_version"], pipeline.PINNED_AKCLI_VERSION)
        self.assertEqual(result["observed"]["akcli_version"],
                         pipeline.PINNED_AKCLI_VERSION)

    def test_the_pinned_version_is_the_qualified_kernel(self):
        self.assertEqual(pipeline.PINNED_AKCLI_VERSION, "0.21.0")

    # --- the Owner's core obligation: a different akcli must not qualify ----
    def test_a_different_akcli_version_is_blocked(self):
        runtime = self._runtime_with_toolchain(
            lambda m: m.__setitem__("akcli_version", "0.22.0"))
        result = pipeline.qualify_toolchain(self.context, runtime)
        self.assertEqual(result["status"], pipeline.TOOLCHAIN_BLOCKED)
        self.assertIn("0.22.0", result["findings"][0].detail)
        self.assertIn("0.21.0", result["findings"][0].detail)

    def test_a_missing_akcli_version_is_blocked_not_assumed(self):
        # An absent declared version must not be read as "whatever the host has".
        # The slice digest would also catch this edit, so the assertion targets
        # the version finding specifically -- otherwise tolerating None here
        # would go unnoticed.
        runtime = self._runtime_with_toolchain(
            lambda m: m.pop("akcli_version", None))
        result = pipeline.qualify_toolchain(self.context, runtime)
        self.assertEqual(result["status"], pipeline.TOOLCHAIN_BLOCKED)
        self.assertTrue(any("qualified version" in finding.detail
                            for finding in result["findings"]),
                        "the absent version must be reported in its own right")

    def test_a_slice_from_another_binding_is_blocked(self):
        # Same declared version, but the slice is not the one this host binding
        # derives: the artifact digest is what catches it.
        runtime = self._runtime_with_toolchain(
            lambda m: m.__setitem__("akcli_artifact_sha256", "9" * 64))
        result = pipeline.qualify_toolchain(self.context, runtime)
        self.assertEqual(result["status"], pipeline.TOOLCHAIN_BLOCKED)
        self.assertTrue(result["findings"])

    def test_an_unqualified_binding_is_blocked(self):
        # A binding that does not pin the qualified version never reaches a
        # verdict of PASS; it is BLOCKED with the reason.
        binding = base_binding()
        binding["manifest"]["akcli"]["version"] = "0.20.0"
        context = dict(self.context, toolchain_binding=binding)
        result = pipeline.qualify_toolchain(context, self.runtime)
        self.assertEqual(result["status"], pipeline.TOOLCHAIN_BLOCKED)
        self.assertIn("not qualified", result["findings"][0].detail)

    def test_a_malformed_binding_is_blocked_not_raised(self):
        context = dict(self.context, toolchain_binding={"manifest": {}})
        result = pipeline.qualify_toolchain(context, self.runtime)
        self.assertEqual(result["status"], pipeline.TOOLCHAIN_BLOCKED)

    def test_blocked_and_unknown_are_distinct(self):
        self.assertEqual((pipeline.TOOLCHAIN_PASS, pipeline.TOOLCHAIN_BLOCKED,
                          pipeline.TOOLCHAIN_UNKNOWN),
                         ("PASS", "BLOCKED", "UNKNOWN"))
        self.assertEqual(len({pipeline.TOOLCHAIN_PASS, pipeline.TOOLCHAIN_BLOCKED,
                              pipeline.TOOLCHAIN_UNKNOWN}), 3)

    # --- qualification is a precondition, not a substitute for the call ----
    def test_qualification_never_invokes_the_tool(self):
        import inspect
        source = inspect.getsource(pipeline.qualify_toolchain)
        body = source.split('"""', 2)[-1]
        code = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
        for forbidden in ("apply_stage", "read_native", "subprocess", "worker_main",
                          "os.system", "Popen", "check_output"):
            self.assertNotIn(forbidden, code)

    def test_qualification_does_not_install_or_resolve_anything(self):
        import inspect
        source = inspect.getsource(pipeline.qualify_toolchain)
        # Code only: the docstring states the prohibition in prose ("it does not
        # resolve, download or install anything"), so a raw scan would match the
        # rule that describes it.
        body = source.split('"""', 2)[-1]
        code = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
        for forbidden in ("pip", "install", "download", "urllib", "requests"):
            self.assertNotIn(forbidden, code)


class BindPolicyOrchestrationTests(unittest.TestCase):
    """CP4-C: compose the proven stages into one BoundPolicyResult.

    Driven by the REAL frozen DC-04 native fixture, not a synthetic rule:
    select_rule matches against the loaded policy, so an invented rule id would
    never be selected and the composition would not be exercised at all.
    """

    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "repair_pr1" / "native"
    CASE = "DC-04"
    RULE_ID = "DC-04"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        # design_root is <cand>/design and the target is relative to it.
        (self.design / TARGET).write_bytes(self._raw())
        self.observation = self._observation()
        self.proposal = self._proposal()

    def tearDown(self):
        self._tmp.cleanup()

    def _raw(self):
        return (self.FIXTURES / self.CASE / "fault.kicad_sch").read_bytes()

    def _observation(self):
        # The real DC-04 BEFORE observation, derived from the frozen native
        # fixture with C2's own observe_source -- 22 components, 84 pins, 114
        # source objects, real library/pin digests, coverage complete, and every
        # pin DC-04 names (SW2.1/2, U1.8, R3.1/2) present.
        #
        # This is fixture construction from frozen bytes, NOT a native read: the
        # pinned akcli reader is not installed on this host, so no native parity
        # is claimed here. The native differential tests remain the authority for
        # that and stay skipped (AEDL_PR1_NATIVE=1).
        observation = pipeline._c2_observe_source(self._raw())
        have = {"%s.%s" % (row["identity"]["reference"], row["identity"]["number"])
                for row in observation["pins"]}
        for required in ("SW2.1", "SW2.2", "U1.8", "R3.1", "R3.2"):
            if required not in have:
                raise AssertionError("the DC-04 fixture no longer carries %s" % required)
        return observation

    def test_the_fixture_carries_everything_dc04_needs(self):
        observation = self._observation()
        self.assertTrue(observation["coverage"]["complete"])
        self.assertTrue(any(obj["kind"] == "lib_symbols"
                            for obj in observation["source_objects"]))
        self.assertGreaterEqual(len(observation["components"]), 8)
        # every component carries the real library digests CP2 requires
        for component in observation["components"]:
            self.assertEqual(len(component["lib_definition_sha256"]), 64)
            self.assertEqual(len(component["pin_definition_sha256"]), 64)

    def _proposal(self):
        ops = json.loads((self.FIXTURES / self.CASE / "repair_ops.json")
                         .read_text(encoding="utf-8"))["ops"]
        document = {"schema_version": 1, "context_id": CONTEXT,
                    "target": TARGET, "base_source_sha256": "b" * 64,
                    "decision": "PATCH",
                    "diagnosis": [{"rule_id": self.RULE_ID,
                                   "observed": "R9 is absent from the boot/vdd nets",
                                   "fact_ids": ["F1"],
                                   "requirement_level": "MANDATORY",
                                   "rationale": "observed against the public fact set"}],
                    "oplist": {"protocol_version": 2, "target_format": "kicad",
                               "ops": ops}}
        return pipeline.parse_proposal(json.dumps(document).encode("utf-8"))

    def _native(self, status="PASS", symbol=SYMBOL):
        return {"status": status, "observation": self.observation,
                "tool": {"symbol_digest": symbol}}

    def _approving(self, rule_id=None, **overrides):
        return pipeline.validate_host_context(host_context(
            design_root=str(self.root / "cand"),
            authority=authority(approvals=[
                {"policy_file_sha256": policy_sha(),
                 "rule_id": rule_id or self.RULE_ID, "run_id": RUN,
                 "candidate_id": CAND, "paths": [abs_path("cand")]}]),
            **overrides))

    # --- the happy path composes every stage -------------------------------
    def test_a_bound_and_qualified_transaction_produces_a_result(self):
        result = pipeline.bind_policy(self._approving(), self.proposal, self._native())
        self.assertEqual(result["status"], pipeline.STATUS_NO_CHANGE)
        self.assertEqual(result["last_phase"], pipeline.PHASE_PRECHECK)
        self.assertIsNone(result["cause_status"])
        self.assertEqual(result["reasons"], [])
        self.assertEqual(result["rule_id"], self.RULE_ID)
        self.assertEqual(result["authorization"]["status"], pipeline.AUTH_PASS)
        self.assertEqual(result["toolchain"]["status"], pipeline.TOOLCHAIN_PASS)
        self.assertEqual(result["toolchain"]["pinned_akcli_version"], "0.21.0")

    def test_the_result_carries_the_frozen_digests(self):
        result = pipeline.bind_policy(self._approving(), self.proposal, self._native())
        patch = result["host_patch"]
        self.assertEqual(result["patch_sha256"], patch["patch_sha256"])
        self.assertEqual(result["bound_policy_sha256"],
                         patch["policy"]["bound_policy_sha256"])
        self.assertEqual(result["authorized_delta_sha256"],
                         patch["bound_policy"]["authorized_delta_sha256"])
        self.assertEqual(result["expected_after_source_sha256"],
                         pipeline._EXPECTED_SOURCE_SHA256)

    def test_the_status_is_one_of_the_frozen_transaction_states(self):
        result = pipeline.bind_policy(self._approving(), self.proposal, self._native())
        self.assertIn(result["status"], pipeline.TRANSACTION_STATUSES)
        self.assertNotEqual(result["status"], pipeline.STATUS_COMMITTED)

    # --- ordering: authorization is resolved before the toolchain matters ---
    def test_an_unauthorized_transaction_stops_at_authorization(self):
        # The rule IS approved (so select_rule passes) and the toolchain IS
        # qualified, but FILE_WRITE is DENIED. The only remaining reason to
        # block is the authorization stage, so skipping resolve_authorization
        # would let this through -- which is exactly what this test must catch.
        context = pipeline.validate_host_context(host_context(
            design_root=str(self.root / "cand"),
            authority=authority(
                decisions=[{"capability": pipeline.CAPABILITY_TOOL_EXECUTE,
                            "effect": pipeline.EFFECT_ALLOW},
                           {"capability": pipeline.CAPABILITY_FILE_WRITE,
                            "effect": "DENY"}],
                approvals=[{"policy_file_sha256": policy_sha(),
                            "rule_id": self.RULE_ID, "run_id": RUN,
                            "candidate_id": CAND, "paths": [abs_path("cand")]}])))
        result = pipeline.bind_policy(context, self.proposal, self._native())
        self.assertEqual(result["status"], pipeline.STATUS_BLOCKED)
        self.assertEqual(result["last_phase"], pipeline.PHASE_PRECHECK)
        self.assertIn(pipeline.CAPABILITY_FILE_WRITE,
                      result["reasons"][0].detail)
        self.assertNotIn("toolchain", result)

    def test_an_unqualified_toolchain_is_refused_before_binding(self):
        # The host context validator already refuses a binding that does not pin
        # the qualified akcli, so an unqualified toolchain cannot reach
        # bind_policy at all. Asserted at the real boundary: the refusal happens
        # in validate_host_context, not later as a verdict.
        binding = base_binding()
        binding["manifest"]["akcli"]["version"] = "0.20.0"
        with self.assertRaises(pipeline.HostContextError):
            pipeline.validate_host_context(host_context(
                design_root=str(self.root / "cand"),
                authority=authority(approvals=[
                    {"policy_file_sha256": policy_sha(), "rule_id": self.RULE_ID,
                     "run_id": RUN, "candidate_id": CAND,
                     "paths": [abs_path("cand")]}]),
                toolchain_binding=binding))

    def test_a_qualified_binding_is_accepted_and_reaches_binding(self):
        result = pipeline.bind_policy(self._approving(), self.proposal, self._native())
        self.assertEqual(result["toolchain"]["status"], pipeline.TOOLCHAIN_PASS)

    def test_the_toolchain_gate_refuses_a_tampered_runtime_slice(self):
        # For a validated host context the runtime slice is always derived from
        # the same binding, so CP4-C's toolchain gate cannot fire on its own
        # inputs. It is a defence against the slice being substituted AFTER
        # binding -- which is exactly the case a HostPatch with an arbitrary
        # toolchain_manifest would produce. This test injects that substitution
        # directly, so the gate is proven load-bearing rather than incidental.
        import tools.repair_pipeline as pipeline_module
        original = pipeline_module.runtime_bindings

        def tampered(host_context, proposal, native_before, policy_sha, approved,
                     rule=None, removals=None):
            runtime = original(host_context, proposal, native_before, policy_sha,
                               approved, rule=rule, removals=removals)
            manifest = json.loads(json.dumps(runtime["toolchain_manifest"]))
            manifest["akcli_version"] = "0.22.0"
            return dict(runtime, toolchain_manifest=manifest)

        pipeline_module.runtime_bindings = tampered
        try:
            result = pipeline.bind_policy(self._approving(), self.proposal,
                                          self._native())
        finally:
            pipeline_module.runtime_bindings = original
        self.assertEqual(result["status"], pipeline.STATUS_BLOCKED)
        self.assertIn("0.22.0", result["reasons"][0].detail)
        self.assertNotIn("host_patch", result)

    # --- failures are reported, never swallowed ----------------------------
    def test_an_unapproved_rule_is_reported_with_its_own_reason(self):
        # The capability decisions are ALLOW, so the only reason to block is
        # that no approval binds DC-04. Both the rule-selection stage and the
        # resolver would refuse; the assertion is on the reason being about the
        # rule, and that the receipt still names a cause.
        context = pipeline.validate_host_context(host_context(
            design_root=str(self.root / "cand"),
            authority=authority(approvals=[
                {"policy_file_sha256": policy_sha(), "rule_id": "E1",
                 "run_id": RUN, "candidate_id": CAND,
                 "paths": [abs_path("cand")]}])))
        result = pipeline.bind_policy(context, self.proposal, self._native())
        self.assertEqual(result["status"], pipeline.STATUS_BLOCKED)
        self.assertIn("DC-04", result["reasons"][0].detail)
        self.assertIsNotNone(result["cause_status"])

    def test_a_non_pass_native_read_is_never_bound(self):
        result = pipeline.bind_policy(self._approving(), self.proposal,
                                      self._native(status="FAIL"))
        self.assertEqual(result["status"], pipeline.STATUS_BLOCKED)
        self.assertNotIn("host_patch", result)

    def test_a_false_authorization_is_not_reported_as_a_tool_error(self):
        # 'False == error' must not happen: a refusal is BLOCKED, and a stage
        # that could not run is TOOL_ERROR or UNKNOWN, never silently PASS.
        context = pipeline.validate_host_context(
            host_context(design_root=str(self.root / "cand"),
                         authority=authority(decisions=[
                             {"capability": pipeline.CAPABILITY_FILE_WRITE,
                              "effect": "DENY"}])))
        result = pipeline.bind_policy(context, self.proposal, self._native())
        self.assertEqual(result["status"], pipeline.STATUS_BLOCKED)
        self.assertNotEqual(result["status"], pipeline.STATUS_TOOL_ERROR)
        self.assertNotEqual(result["status"], pipeline.STATUS_COMMITTED)

    def test_an_unexpected_exception_is_not_converted_into_a_verdict(self):
        import inspect
        source = inspect.getsource(pipeline.bind_policy)
        body = source.split('"""', 2)[-1]
        code = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
        # a bare `except Exception` would swallow a defect into a clean verdict
        for forbidden in ("except Exception", "except:", "pass  #"):
            self.assertNotIn(forbidden, code)

    def test_binding_is_deterministic(self):
        context = self._approving()
        first = pipeline.canonical_json_bytes(
            pipeline.bind_policy(context, self.proposal, self._native()))
        second = pipeline.canonical_json_bytes(
            pipeline.bind_policy(context, self.proposal, self._native()))
        self.assertEqual(first, second)

    # --- CP4-C executes nothing --------------------------------------------
    def test_binding_never_stages_or_commits(self):
        import inspect
        source = inspect.getsource(pipeline.bind_policy)
        body = source.split('"""', 2)[-1]
        code = "\n".join(line.split("#", 1)[0] for line in body.splitlines())
        for forbidden in ("apply_stage", "verify_stage", "commit", "recheck_reports",
                          "write_bytes", "shutil"):
            self.assertNotIn(forbidden, code)


class RunRoundTests(unittest.TestCase):
    """C5 run_round MVP: one round controller, composition only.

    Driven by the REAL frozen DC-04 native fixture, because an invented rule id
    would never be selected and the composition would not be exercised.

    The central property under test is FAIL-CLOSED.  run_round has no seam for
    the writer: it always calls the real akcli_adapter.apply_stage.  On an
    interpreter without the pinned akcli that means the round provably cannot
    report a write, so most of these tests assert that it does not -- the happy
    path needs the pinned toolchain and is opt-in (AEDL_PR1_NATIVE=1).
    """

    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "repair_pr1" / "native"
    CASE = "DC-04"
    RULE_ID = "DC-04"
    STAGE_TARGET = "fault.kicad_sch"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.cand = self.root / "cand"
        self.design = self.cand / "design"
        self.design.mkdir(parents=True)
        self.raw = (self.FIXTURES / self.CASE / self.STAGE_TARGET).read_bytes()
        (self.design / self.STAGE_TARGET).write_bytes(self.raw)
        self.ops = json.loads((self.FIXTURES / self.CASE / "repair_ops.json")
                              .read_text(encoding="utf-8"))["ops"]
        self.oplist = self.design / "repair_ops.json"
        self.oplist.write_text(json.dumps(
            {"protocol_version": 2, "target_format": "kicad", "ops": self.ops},
            ensure_ascii=False, indent=2), encoding="utf-8")
        self.artifacts = self.root / "artifacts"
        self.artifacts.mkdir(parents=True)
        # The stage is a scratch copy that is genuinely DISJOINT from the
        # candidate's design root.  It used to be self.design -- the very
        # directory the host context declares as workspace.design_root -- which
        # meant these tests exercised the configuration in which the writer
        # modifies the candidate directly.  StageCandidateSeparationTests now
        # refuses that shape, and rightly so.
        self.stage = self.root / "stage"
        self.stage.mkdir(parents=True)
        (self.stage / self.STAGE_TARGET).write_bytes(self.raw)
        self.oplist = self.stage / "repair_ops.json"
        self.oplist.write_text(json.dumps(
            {"protocol_version": 2, "target_format": "kicad", "ops": self.ops},
            ensure_ascii=False, indent=2), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _before_sha(self):
        return pipeline.hash_bytes(self.raw)

    def _proposal_raw(self, **overrides):
        document = {
            "schema_version": 1, "context_id": CONTEXT,
            "target": self.STAGE_TARGET, "base_source_sha256": self._before_sha(),
            "decision": pipeline.DECISION_PATCH,
            "diagnosis": [{"rule_id": self.RULE_ID, "observed": "R9 is absent",
                           "fact_ids": ["F1"], "requirement_level": "MANDATORY",
                           "rationale": "observed against the frozen fixture"}],
            "oplist": {"protocol_version": 2, "target_format": "kicad",
                       "ops": self.ops},
        }
        document.update(overrides)
        return json.dumps(document, ensure_ascii=False).encode("utf-8")

    def _context(self, rule_id=None, **overrides):
        return pipeline.validate_host_context(host_context(
            design_root=str(self.cand),
            base_source_sha256=self._before_sha(),
            target=self.STAGE_TARGET,
            authority=authority(approvals=[{
                "policy_file_sha256": policy_sha(),
                "rule_id": rule_id or self.RULE_ID, "run_id": RUN,
                "candidate_id": CAND, "paths": [str(self.cand)]}]),
            **overrides))

    def _request(self, **overrides):
        request = {
            "host_context": self._context(),
            "proposal_raw": self._proposal_raw(),
            "txn_id": "txn-run-round-1",
            "stage_root": str(self.stage),
            "stage_target": self.STAGE_TARGET,
            "oplist_path": str(self.oplist),
            "native_artifact_root": str(self.artifacts),
        }
        request.update(overrides)
        return request

    def _run(self, **overrides):
        return pipeline.run_round(self._request(**overrides))

    @staticmethod
    def _codes(receipt):
        return [getattr(reason, "code", reason) for reason in receipt["reasons"]]

    # --- the request is a closed set ------------------------------------
    def test_the_request_must_be_a_mapping(self):
        with self.assertRaises(TypeError):
            pipeline.run_round("not a mapping")

    def test_an_unknown_request_field_is_rejected(self):
        request = self._request()
        request["surprise"] = 1
        with self.assertRaises(pipeline.ProposalInvalidError) as caught:
            pipeline.run_round(request)
        findings = caught.exception.findings
        self.assertEqual([item.code for item in findings],
                         [pipeline.REASON_SCHEMA_INVALID])
        self.assertIn("surprise", findings[0].detail)

    def test_a_missing_required_field_is_rejected(self):
        request = self._request()
        del request["oplist_path"]
        with self.assertRaises(pipeline.ProposalInvalidError) as caught:
            pipeline.run_round(request)
        self.assertEqual([item.code for item in caught.exception.findings],
                         [pipeline.REASON_SCHEMA_INVALID])

    def test_an_empty_stage_root_is_refused_with_the_field_named(self):
        """The request preamble's own guard, and the field it refused.

        A MISSING key is rejected by _require_keys before the preamble's try
        block is reached, so `test_a_missing_required_field_is_rejected` does not
        exercise the `except RepairContractError` branch at all. An EMPTY stage_root
        does: _text(..., allow_empty=False) raises from inside the try, and the
        receipt must carry the contract's finding -- code AND detail -- rather than
        a synthesised code-only one.
        """
        receipt = pipeline.run_round(self._request(stage_root=""))
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["status"], pipeline.STATUS_UNKNOWN)
        codes = self._codes(receipt)
        self.assertIn(pipeline.REASON_SCHEMA_INVALID, codes)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("stage_root", detail)
        self.assertIn("must not be empty", detail)

    def test_the_proposal_must_arrive_as_raw_bytes(self):
        with self.assertRaises(TypeError):
            self._run(proposal_raw=json.loads(self._proposal_raw().decode("utf-8")))

    def test_run_round_parses_the_proposal_itself(self):
        """A caller cannot bypass parse_proposal by pre-parsing.

        The document below is structurally invalid -- it carries no oplist at
        all.  run_round must refuse it in its own parse, at PRECHECK, and never
        reach the writer.  If a caller could hand in a pre-parsed Proposal and
        skip this, an unvalidated proposal would reach apply_stage.
        """
        receipt = self._run(proposal_raw=json.dumps({
            "schema_version": 1, "context_id": CONTEXT,
            "target": self.STAGE_TARGET, "base_source_sha256": self._before_sha(),
            "decision": pipeline.DECISION_PATCH,
            "diagnosis": [{"rule_id": self.RULE_ID}],
        }, ensure_ascii=False).encode("utf-8"))
        self.assertTrue(receipt["terminal"])
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)
        # The proposal's own findings are carried through, so the receipt names
        # the schema refusal rather than a generic input-drift code. That is the
        # behaviour PR1-C5-SNAPSHOT introduced; an earlier version stringified the
        # exception, which yields only the reason code and loses the field.
        self.assertIn(pipeline.REASON_SCHEMA_INVALID, self._codes(receipt))
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("diagnosis", detail)
        # the malformed proposal is caught in PRECHECK, so the snapshot may or may
        # not already have been taken, but the WRITER phases must never appear
        reached = [row["phase"] for row in receipt["phases"]
                   if row["status"] == "reached"]
        self.assertNotIn(pipeline.PHASE_STAGE_APPLY, reached)
        self.assertNotIn(pipeline.PHASE_DELTA_CHECK, reached)
        self.assertEqual((self.stage / self.STAGE_TARGET).read_bytes(), self.raw)

    # --- containment ----------------------------------------------------
    def test_a_stage_target_that_escapes_the_stage_root_is_never_read(self):
        """An escaping target is refused, and the escaping file is not read.

        The escape target is placed exactly where "../" would reach it, so this
        fails if containment is removed rather than passing because the path
        happened to be missing.

        Since PR1-C5-SNAPSHOT the BEFORE comes from the snapshot, and the
        snapshot is materialised from the candidate with the escaping name, so
        the refusal now happens while building the manifest -- the escaping path
        is caught as an unsafe candidate-relative manifest path, or the snapshot
        is refused outright. Either way the secret file is never read.
        """
        outside = self.cand / "outside.kicad_sch"
        outside.write_bytes(b"secret")
        receipt = self._run(stage_target="../outside.kicad_sch")
        self.assertTrue(receipt["terminal"])
        self.assertIn(receipt["phase"],
                      (pipeline.PHASE_PRECHECK, pipeline.PHASE_SNAPSHOT))
        self.assertEqual(outside.read_bytes(), b"secret")
        self.assertIsNone(receipt["before_source_sha256"])

    def test_a_missing_stage_target_is_blocked_before_any_writer_runs(self):
        """A target absent from the SNAPSHOT is refused, and no writer runs.

        Since PR1-C5-SNAPSHOT the BEFORE is read from the snapshot, so the
        snapshot must also carry the target. The refusal belongs to SNAPSHOT
        rather than PRECHECK because that is the phase that owns the bytes now.
        """
        receipt = self._run(stage_target="absent.kicad_sch")
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        self.assertEqual(receipt["phase"], pipeline.PHASE_SNAPSHOT)
        self.assertEqual(receipt["phases"][-1]["status"], "refused")
        self.assertNotIn(pipeline.PHASE_STAGE_APPLY,
                         [row["phase"] for row in receipt["phases"]])

    # --- precheck refusals ----------------------------------------------
    def test_a_rule_the_host_did_not_approve_is_refused(self):
        receipt = self._run(host_context=self._context(rule_id="E1"))
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        # The authorization is resolved in SNAPSHOT, after the snapshot exists and
        # before any writer (PR1-C5-SNAPSHOT), so the refusal belongs there.
        self.assertEqual(receipt["phase"], pipeline.PHASE_SNAPSHOT)
        self.assertIn(pipeline.REASON_AUTH_DENIED, self._codes(receipt))
        self.assertEqual(receipt["phases"][-1]["status"], "refused")

    def test_a_refused_precheck_never_reaches_the_writer_phase(self):
        receipt = self._run(host_context=self._context(rule_id="E1"))
        reached = [row["phase"] for row in receipt["phases"]]
        self.assertNotIn(pipeline.PHASE_STAGE_APPLY, reached)
        self.assertNotIn(pipeline.PHASE_DELTA_CHECK, reached)

    def test_the_phase_order_follows_the_contract(self):
        """PRECHECK -> SNAPSHOT -> STAGE_APPLY, in the order they are recorded.

        An earlier version materialised the snapshot before bind_policy, which
        recorded ['SNAPSHOT', 'PRECHECK', 'STAGE_APPLY'] -- the reverse of
        akcli_adapter.py:1354's order -- and issued the authorization before the
        bytes it authorised against were fixed.
        """
        receipt = self._run()
        reached = [row["phase"] for row in receipt["phases"]
                   if row["status"] == "reached"]
        self.assertEqual(reached, [pipeline.PHASE_SNAPSHOT, pipeline.PHASE_PRECHECK])

    def test_the_before_observation_must_be_complete_or_the_round_blocks(self):
        original = pipeline._c2_observe_source

        def incomplete(raw):
            observed = original(raw)
            observed["coverage"] = dict(observed["coverage"], complete=False)
            return observed

        with mock.patch.object(pipeline, "_c2_observe_source", incomplete):
            receipt = self._run()
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        self.assertIn(pipeline.REASON_COVERAGE_INCOMPLETE, self._codes(receipt))

    # --- the real DC-04 round on a host without the pinned writer -------
    def test_the_real_dc04_round_binds_then_fails_closed_without_the_writer(self):
        """PRECHECK must complete on the real fixture, then the write must fail.

        This is the load-bearing test: it proves the controller reaches the
        writer and then refuses, rather than reporting a write it cannot back.
        """
        receipt = self._run()
        reached = [row["phase"] for row in receipt["phases"]]
        self.assertIn(pipeline.PHASE_PRECHECK, reached)
        self.assertEqual(receipt["rule_id"], self.RULE_ID)
        self.assertEqual(len(receipt["bound_policy_sha256"]), 64)
        self.assertEqual(receipt["before_source_sha256"], self._before_sha())
        # whatever the writer did, the stage bytes are only changed by a real
        # write, and this interpreter has no pinned akcli
        self.assertEqual((self.design / self.STAGE_TARGET).read_bytes(), self.raw)
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)

    def test_the_bound_authorized_delta_is_the_one_the_real_transaction_recorded(self):
        """Cross-check against EVID-20260927-001.

        The first real DC-04 transaction recorded authorized_delta_sha256
        69877d3e9a4be9133f0c31684b35952a9f9745596974eb1f1237c6b437ebc681.  If
        run_round's PRECHECK reproduces that digest from the frozen fixture
        alone, it is binding the same expectation the recorded transaction bound.
        """
        receipt = self._run()
        self.assertEqual(
            receipt["authorized_delta_sha256"],
            "69877d3e9a4be9133f0c31684b35952a9f9745596974eb1f1237c6b437ebc681")

    def test_a_write_is_never_claimed_when_the_writer_did_not_apply(self):
        receipt = self._run()
        stage = receipt.get("stage") or {}
        # the four-way conjunction is all-or-nothing; a refusal leaves no claim
        self.assertNotEqual(stage.get("status"), "APPLIED_TO_STAGE")
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)
        self.assertTrue(receipt["terminal"])
        self.assertIn(receipt["status"],
                      (pipeline.STATUS_TOOL_ERROR, pipeline.STATUS_BLOCKED,
                       pipeline.STATUS_UNKNOWN))

    def test_the_refusal_keeps_the_writer_own_reason_rather_than_a_generic_one(self):
        receipt = self._run()
        self.assertTrue(receipt["reasons"])
        detail = " ".join(str(getattr(r, "detail", r)) for r in receipt["reasons"])
        self.assertNotEqual(detail.strip(), "")

    def test_a_refusal_is_always_terminal(self):
        """Every refusal path must end the round, whatever the phase."""
        cases = {
            "unreadable stage target": {"stage_target": "absent.kicad_sch"},
            "unapproved rule": {"host_context": self._context(rule_id="E1")},
            "escaping stage target": {"stage_target": "../outside.kicad_sch"},
            "no pinned writer": {},
        }
        for label, overrides in cases.items():
            with self.subTest(case=label):
                receipt = self._run(**overrides)
                self.assertTrue(receipt["terminal"], label)
                self.assertEqual(receipt["cause_status"], receipt["status"], label)
                self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)

    # --- the success criterion, tested exhaustively ----------------------
    # run_round has no seam for the writer, so the "did it really write?"
    # criterion is a separate predicate and is pinned here directly.  Each of
    # the four facts can be false while the others hold true, which is exactly
    # how a fake write would otherwise be admitted.
    def test_only_a_complete_stage_receipt_counts_as_a_write(self):
        ok = {"status": "APPLIED_TO_STAGE", "changed": True,
              "tool": {"tool_applied": True, "exit_code": 0}}
        self.assertTrue(pipeline._stage_write_succeeded(ok))

    def test_each_missing_fact_alone_defeats_the_success_criterion(self):
        ok = {"status": "APPLIED_TO_STAGE", "changed": True,
              "tool": {"tool_applied": True, "exit_code": 0}}
        for field, value in (("status", "APPLIED"), ("status", None),
                             ("changed", False), ("changed", None)):
            with self.subTest(field=field, value=value):
                broken = copy.deepcopy(ok)
                broken[field] = value
                self.assertFalse(pipeline._stage_write_succeeded(broken))
        for field, value in (("tool_applied", False), ("tool_applied", None),
                             ("exit_code", 1), ("exit_code", None),
                             ("exit_code", "0")):
            with self.subTest(field=field, value=value):
                broken = copy.deepcopy(ok)
                broken["tool"][field] = value
                self.assertFalse(pipeline._stage_write_succeeded(broken))

    def test_a_malformed_stage_receipt_is_never_a_write(self):
        for candidate in (None, "APPLIED_TO_STAGE", [], {},
                          {"status": "APPLIED_TO_STAGE"},
                          {"status": "APPLIED_TO_STAGE", "tool": None,
                           "changed": True}):
            with self.subTest(candidate=candidate):
                self.assertFalse(pipeline._stage_write_succeeded(candidate))

    def test_run_round_has_no_seam_for_the_writer(self):
        """A fake write must be structurally impossible, not merely discouraged.

        run_round's request carries no writer, receipt or override field, and its
        body calls the real apply_stage with no injection point.
        """
        request_fields = set(pipeline.ROUND_FIELDS)
        for forbidden in ("writer", "applier", "apply_stage", "receipt",
                          "stage_receipt", "override", "mock", "fake"):
            self.assertNotIn(forbidden, request_fields)
        import inspect
        import textwrap
        body = textwrap.dedent(_round_source())
        self.assertIn("akcli_adapter.apply_stage", body)
        for forbidden in ("writer=", "applier=", "override=", "mock"):
            self.assertNotIn(forbidden, body)

    # --- properties that must hold structurally -------------------------
    def test_compare_delta_is_the_only_acceptance_entry(self):
        """run_round must not re-derive the delta by hand.

        An earlier harness compared observation_delta digests itself and reported
        a FALSE "identity delta FAIL"; the capability it wanted already lived in
        C2 behind compare_delta.  This guard stops that regression returning.
        """
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(_round_source()))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    called.add(node.func.attr)
                elif isinstance(node.func, ast.Name):
                    called.add(node.func.id)
        self.assertIn("compare_delta", called)
        self.assertNotIn("observation_delta", called)

    def test_the_round_never_claims_committed(self):
        """INVERTED when the writer landed: COMMITTED is now reachable.

        This pinned "the token STATUS_COMMITTED never appears in run_round's
        source" -- the structural half of "COMMITTED is unreachable", true while
        the writer was absent and the point of PR #101. Not deleted, not
        relaxed: it now pins the property that replaced it, namely that the token
        appears only AFTER the COMMIT phase begins, so no earlier phase can
        claim a status it has not earned.
        """
        import inspect
        import textwrap

        body = textwrap.dedent(_round_source())
        # INVERTED, and still four assertions rather than one, because the
        # original pinned four distinct ways the token could have been smuggled
        # in. Each now has to be PRESENT, and all four must sit after the COMMIT
        # phase begins -- so the test still catches a status claimed early, which
        # is the property that actually matters.
        self.assertIn("status=STATUS_COMMITTED", body,
                      "the writer landed, so the token must be reachable")
        self.assertIn('"status": STATUS_COMMITTED', body)
        self.assertIn("STATUS_COMMITTED,", body)
        # The bare `STATUS_COMMITTED}` spelling is GONE and deliberately not
        # asserted: the writer builds its terminal record as
        # `kind=JOURNAL_TERMINAL, status=STATUS_COMMITTED`, so no code path
        # produces that form any more. Asserting it would pin a spelling the code
        # does not use -- a test that can only pass if the code were written
        # differently from how it is written, which is a test about style
        # masquerading as a test about behaviour.
        boundary = body.index("COMMIT -- contract line 374")
        for token in ("status=STATUS_COMMITTED", '"status": STATUS_COMMITTED',
                      "STATUS_COMMITTED,"):
            self.assertGreater(body.index(token), boundary,
                               "%s appears before the COMMIT phase begins"
                               % token)

    def test_the_driven_phase_order_is_the_contracts(self):
        """Derived from a real receipt, not from a hand-maintained constant.

        The removed version of this test asserted `ROUND_PHASES` against its own
        definition -- a tautology -- and was wrong while being unable to fail: it
        claimed three phases while the round drove five, because SNAPSHOT landed
        without updating it. The order is now read off what a round records.
        """
        receipt = pipeline.run_round(self._request())
        reached = [row["phase"] for row in receipt["phases"]
                   if row["status"] == "reached"]
        # this interpreter has no pinned akcli, so the round stops at
        # STAGE_APPLY; that is enough to prove PRECHECK and SNAPSHOT come first
        # and that SNAPSHOT is driven at all
        self.assertEqual(reached[:2],
                         [pipeline.PHASE_SNAPSHOT, pipeline.PHASE_PRECHECK])
        self.assertNotIn(pipeline.PHASE_COMMIT, reached)
        self.assertEqual(pipeline.ROUND_PENDING_PHASES,
                         (pipeline.PHASE_COMMIT,))

    def test_the_contract_phase_order_is_spelled_out_in_one_place(self):
        """Contract line 355, as literals, so a renamed phase cannot slip past.

        This is the assertion that actually pins the order. The derived one above
        can only prove what a partial round reached; this states the whole
        contract order and is checked against the phase constants themselves.
        """
        self.assertEqual(
            (pipeline.PHASE_PRECHECK, pipeline.PHASE_SNAPSHOT,
             pipeline.PHASE_STAGE_APPLY, pipeline.PHASE_DELTA_CHECK,
             pipeline.PHASE_KICAD_VERIFY, pipeline.PHASE_COMMIT),
            ("PRECHECK", "SNAPSHOT", "STAGE_APPLY", "DELTA_CHECK",
             "KICAD_VERIFY", "COMMIT"))

    def test_no_phase_constant_is_orphaned(self):
        """Every phase constant the contract names is actually driven.

        ROUND_PHASES drifted for two rounds precisely because nothing checked it
        against the phase constants. A constant that no code reaches is how
        "the receipt says one thing and the module another" starts.
        """
        from pathlib import Path as _Path
        import inspect as _inspect
        source = _Path(pipeline.__file__).read_text(encoding="utf-8")
        body = (_inspect.getsource(pipeline.run_round)
                    + _inspect.getsource(pipeline._run_round_body))
        for name in ("PHASE_PRECHECK", "PHASE_SNAPSHOT", "PHASE_STAGE_APPLY",
                     "PHASE_DELTA_CHECK", "PHASE_KICAD_VERIFY"):
            self.assertIn(name, source, "%s is not defined" % name)
            self.assertIn("reach(%s)" % name, body,
                          "%s is defined but never reached" % name)

    def test_a_non_committed_round_projects_as_execution_unavailable(self):
        """Intended MVP behaviour, asserted rather than tolerated.

        A round that applied and verified has no terminal status because the
        commit phase is unimplemented, so the public outcome is genuinely not
        established.  Claiming APPLIED_TO_CANDIDATE here would be a lie.
        """
        feedback = pipeline.public_feedback({
            "context_id": CONTEXT, "status": None, "cause_status": None})
        self.assertEqual(feedback["proposal_outcome"],
                         pipeline.OUTCOME_UNAVAILABLE)
        self.assertEqual(feedback["reason_code"], "EXECUTION_UNAVAILABLE")

    def test_public_feedback_of_this_round_would_be_four_fields_only(self):
        feedback = pipeline.public_feedback({
            "context_id": CONTEXT, "status": None, "cause_status": None})
        self.assertEqual(tuple(feedback), pipeline.PUBLIC_FEEDBACK_FIELDS)

    # --- the opt-in real write ------------------------------------------
    def test_the_real_pinned_writer_completes_the_round(self):
        """Opt-in: the whole point of the MVP, so it is not left unproven.

        Requires AEDL_PR1_NATIVE=1 and AEDL_AKCLI_PYTHON pointing at the pinned
        3.11 interpreter that has akcli-kicad 0.21.0 installed, plus
        AEDL_RUN_ROUND_STAGE_ROOT pointing at a prepared real stage directory.
        Without those this is NOT_RUN, never silently passing.
        """
        if os.environ.get("AEDL_PR1_NATIVE") != "1":
            self.skipTest("native round is not opted in (AEDL_PR1_NATIVE=1)")
        stage_root = os.environ.get("AEDL_RUN_ROUND_STAGE_ROOT")
        python = os.environ.get("AEDL_AKCLI_PYTHON")
        if not stage_root or not python or not os.path.isfile(python):
            self.fail("AEDL_PR1_NATIVE=1 requires AEDL_RUN_ROUND_STAGE_ROOT and "
                      "AEDL_AKCLI_PYTHON for the pinned writer")
        binding = json.loads(os.environ["AEDL_RUN_ROUND_BINDING"])
        context = pipeline.validate_host_context(host_context(
            design_root=os.path.dirname(stage_root.rstrip("/\\")),
            base_source_sha256=self._before_sha(),
            target=self.STAGE_TARGET,
            toolchain_binding=binding,
            authority=authority(approvals=[{
                "policy_file_sha256": policy_sha(), "rule_id": self.RULE_ID,
                "run_id": RUN, "candidate_id": CAND,
                "paths": [os.path.dirname(stage_root.rstrip("/\\"))]}]),
        ))
        receipt = pipeline.run_round({
            "host_context": context, "proposal_raw": self._proposal_raw(),
            "txn_id": "txn-run-round-native", "stage_root": stage_root,
            "stage_target": self.STAGE_TARGET,
            "oplist_path": os.path.join(stage_root, "repair_ops.json"),
            "native_artifact_root": self.artifacts,
        })
        self.assertEqual(receipt["verification"]["status"], "PASS")
        self.assertEqual(receipt["verification"]["missing"], [])
        self.assertEqual(receipt["verification"]["unexpected"], [])
        # a verified round is still not a committed round
        self.assertIsNone(receipt["status"])
        self.assertFalse(receipt["terminal"])
        self.assertEqual(receipt["pending_phases"],
                         list(pipeline.ROUND_PENDING_PHASES))


class SnapshotPhaseTests(unittest.TestCase):
    """PR1-C5-SNAPSHOT: the missing producer for C3's snapshot half.

    C3 could already VALIDATE a manifest (``_manifest``) and VERIFY one against
    real bytes (``_tree_digest``), and ``bind_inputs`` already expected a
    ``snapshot_root`` distinct from ``stage_root``.  Nothing could BUILD one, so
    that half of the contract could never be fed.

    These tests deliberately call the repository's own ``_manifest`` rather than
    restating its rules: if the builder's shape and the frozen validator ever
    drift apart, the test fails instead of quietly agreeing with itself.
    """

    TARGET = "fault.kicad_sch"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        self.raw = (Path(__file__).resolve().parent / "fixtures" / "repair_pr1"
                    / "native" / "DC-04" / self.TARGET).read_bytes()
        (self.design / self.TARGET).write_bytes(self.raw)
        (self.design / "extra_dep.kicad_sym").write_bytes(b"(kicad_symbol_lib)\n")

    def tearDown(self):
        self._tmp.cleanup()

    # --- the builder's output satisfies the FROZEN validator --------------
    def test_the_repository_validator_accepts_the_builder_output(self):
        manifest = pipeline.build_file_manifest(self.design, self.TARGET)
        files, target = c2_manifest(manifest)     # the repo's own validator
        self.assertEqual(target, self.TARGET)
        self.assertEqual(sorted(files), ["extra_dep.kicad_sym", self.TARGET])

    def test_the_manifest_describes_the_real_bytes(self):
        manifest = pipeline.build_file_manifest(self.design, self.TARGET)
        rows = {row["path"]: row for row in manifest["files"]}
        raw = (self.design / self.TARGET).read_bytes()
        self.assertEqual(rows[self.TARGET]["sha256"],
                         pipeline.hash_bytes(raw))
        self.assertEqual(rows[self.TARGET]["size_bytes"], len(raw))
        self.assertEqual(rows["extra_dep.kicad_sym"]["sha256"],
                         pipeline.hash_bytes(b"(kicad_symbol_lib)\n"))

    def test_exactly_one_file_is_the_target(self):
        manifest = pipeline.build_file_manifest(self.design, self.TARGET)
        roles = [row["role"] for row in manifest["files"]]
        self.assertEqual(roles.count("TARGET"), 1)
        self.assertEqual(roles.count("READONLY_DEPENDENCY"),
                         len(roles) - 1)

    def test_every_file_in_the_tree_is_named(self):
        manifest = pipeline.build_file_manifest(self.design, self.TARGET)
        on_disk = sorted(p.name for p in self.design.iterdir() if p.is_file())
        self.assertEqual(sorted(row["path"] for row in manifest["files"]), on_disk)

    def test_a_target_absent_from_the_tree_is_refused(self):
        with self.assertRaises(pipeline.ProposalInvalidError):
            pipeline.build_file_manifest(self.design, "not_there.kicad_sch")

    # --- the frozen validator would reject a wrong shape ------------------
    def test_the_validator_rejects_a_wrong_version(self):
        manifest = pipeline.build_file_manifest(self.design, self.TARGET)
        with self.assertRaises(Exception):
            c2_manifest({"version": 2, "files": manifest["files"]})

    def test_the_validator_rejects_an_escaping_path(self):
        with self.assertRaises(Exception):
            c2_manifest({"version": 1, "files": [
                {"path": "../outside", "sha256": "0" * 64, "size_bytes": 1,
                 "role": "TARGET"}]})

    def test_the_validator_rejects_an_unknown_role(self):
        manifest = pipeline.build_file_manifest(self.design, self.TARGET)
        with self.assertRaises(Exception):
            c2_manifest({"version": 1, "files": [
                dict(manifest["files"][0], role="SOMETHING_ELSE")]})

    def test_the_validator_rejects_two_targets(self):
        manifest = pipeline.build_file_manifest(self.design, self.TARGET)
        with self.assertRaises(Exception):
            c2_manifest({"version": 1, "files": [
                dict(manifest["files"][0]),
                {"path": "extra_dep.kicad_sym", "sha256": "0" * 64,
                 "size_bytes": 1, "role": "TARGET"}]})

    # --- _tree_digest verifies the build against the real bytes -----------
    def test_the_frozen_verifier_accepts_the_build(self):
        manifest = pipeline.build_file_manifest(self.design, self.TARGET)
        observed, target = c2_tree_digest(str(self.design), manifest, "candidate")
        self.assertEqual(target, self.TARGET)
        self.assertEqual(sorted(observed),
                         ["extra_dep.kicad_sym", self.TARGET])

    def test_the_frozen_verifier_rejects_a_tampered_manifest(self):
        manifest = pipeline.build_file_manifest(self.design, self.TARGET)
        tampered = {"version": 1, "files": [
            dict(row, sha256="0" * 64) if row["path"] == self.TARGET else dict(row)
            for row in manifest["files"]]}
        with self.assertRaises(Exception):
            c2_tree_digest(str(self.design), tampered, "candidate")

    # --- snapshot materialisation -----------------------------------------
    def test_the_snapshot_is_byte_identical_to_the_candidate(self):
        root, manifest = pipeline.materialise_snapshot(
            str(self.design), str(self.root / "snapshot"), self.TARGET)
        self.assertEqual((Path(root) / self.TARGET).read_bytes(), self.raw)
        c2_tree_digest(root, manifest, "snapshot")

    def test_a_truncated_snapshot_copy_is_refused(self):
        """The byte-identical check must be load-bearing.

        An earlier version of this class asserted only that a correct copy comes
        out right, which the copy operation satisfies on its own -- mutation T5
        (removing the verification loop) survived it. Corrupting the copy is what
        makes the check observable.
        """
        original = shutil.copytree

        def truncating_copytree(source, destination, *args, **kwargs):
            original(source, destination, *args, **kwargs)
            victim = Path(destination) / self.TARGET
            victim.write_bytes(victim.read_bytes()[:-8])   # a partial copy

        with mock.patch.object(pipeline.shutil, "copytree", truncating_copytree):
            with self.assertRaises(pipeline.ProposalInvalidError) as caught:
                pipeline.materialise_snapshot(
                    str(self.design), str(self.root / "snapshot"), self.TARGET)
        detail = " ".join(getattr(f, "detail", "") for f in caught.exception.findings)
        self.assertIn("not byte-identical", detail)

    def test_the_snapshot_manifest_equals_the_candidate_manifest(self):
        root, manifest = pipeline.materialise_snapshot(
            str(self.design), str(self.root / "snapshot"), self.TARGET)
        self.assertEqual(manifest,
                         pipeline.build_file_manifest(self.design, self.TARGET))

    def test_a_snapshot_inside_the_candidate_is_refused(self):
        """A snapshot of the candidate cannot live inside the candidate."""
        with self.assertRaises(pipeline.ProposalInvalidError):
            pipeline.materialise_snapshot(
                str(self.design), str(self.design / "snap"), self.TARGET)

    def test_a_snapshot_over_the_candidate_is_refused(self):
        with self.assertRaises(pipeline.ProposalInvalidError):
            pipeline.materialise_snapshot(
                str(self.design), str(self.design), self.TARGET)

    def test_snapshotting_a_missing_candidate_is_refused(self):
        with self.assertRaises(pipeline.ProposalInvalidError):
            pipeline.materialise_snapshot(
                str(self.root / "absent"), str(self.root / "snap"), self.TARGET)

    def test_the_snapshot_is_replaced_not_merged_on_a_second_call(self):
        """A stale file from a previous round must not survive into a new one."""
        root, _ = pipeline.materialise_snapshot(
            str(self.design), str(self.root / "snapshot"), self.TARGET)
        stale = Path(root) / "stale.kicad_sym"
        stale.write_bytes(b"left over from an earlier round")
        root2, manifest2 = pipeline.materialise_snapshot(
            str(self.design), str(self.root / "snapshot"), self.TARGET)
        self.assertFalse(stale.exists(), "a stale file survived the snapshot")
        self.assertEqual(sorted(row["path"] for row in manifest2["files"]),
                         ["extra_dep.kicad_sym", self.TARGET])


class RunRoundRejectionTests(unittest.TestCase):
    """M7: a round that was authorized one thing and delivered another is refused.

    Owner's criterion 5 is the substantive one and is what this class exists for:
    the failure evidence must let a reader state WHAT deviated, not merely THAT
    something did.  "failed" versus "R9 resolved to 20k when 10k was authorized".

    Everything here runs without the pinned writer, on the repository's own
    fixture data, because rejection is decided by compare_delta on observations.
    Criteria 1 and 2 additionally need the real writer and are opt-in.

    The verdict uses two entry shapes and both must survive into the receipt:
    a FIELD-level change (``field`` names it, before/after are the values) and an
    OBJECT-level divergence (``field`` is "$", before/after are descriptors, the
    authorized one in missing and the observed one in unexpected).  An earlier
    draft of the implementation read only the second shape and silently lost the
    field name and both values, which is precisely what criterion 5 forbids.
    """

    def setUp(self):
        self.before, self.expected, self.bound, self.after = five_case("DC-04")

    def _verdict(self, after):
        return c2_compare_delta(self.before, after, self.bound)

    def _perturb_value(self, after, reference, value):
        deviated = copy.deepcopy(after)
        for component in deviated["components"]:
            if component["reference"] == reference:
                component["value"] = value
                return deviated
        raise AssertionError("fixture carries no %s" % reference)

    @staticmethod
    def _blob(findings):
        return " ".join("%s %s" % (item.detail, item.object_id)
                        for item in findings)

    # --- the control must actually pass, or the rest proves nothing ------
    def test_the_undeviated_fixture_passes(self):
        verdict = self._verdict(self.after)
        self.assertEqual(verdict["status"], "PASS")
        self.assertEqual(verdict["missing"], [])
        self.assertEqual(verdict["unexpected"], [])

    def test_a_passing_verdict_emits_no_findings(self):
        self.assertEqual(pipeline._delta_findings(self._verdict(self.after)), [])

    # --- criterion 5, field-level shape ----------------------------------
    def test_a_field_level_deviation_names_the_field_and_both_values(self):
        verdict = self._verdict(self._perturb_value(self.after, "R3", "999R"))
        self.assertEqual(verdict["status"], "FAIL")
        findings = pipeline._delta_findings(verdict)
        self.assertTrue(findings)
        blob = self._blob(findings)
        self.assertIn("R3", blob)
        self.assertIn("'value'", blob)
        self.assertIn("'10k'", blob)
        self.assertIn("'999R'", blob)
        for item in findings:
            self.assertEqual(item.code, pipeline.REASON_DELTA_MISMATCH)
            self.assertEqual(item.stage, pipeline.PHASE_DELTA_CHECK)

    def test_the_object_id_is_a_readable_handle_not_a_uuid(self):
        """A raw UUID beside the reference is noise, not information."""
        verdict = self._verdict(self._perturb_value(self.after, "R3", "999R"))
        findings = pipeline._delta_findings(verdict)
        for item in findings:
            self.assertNotIn("-", str(item.object_id))
            self.assertRegex(str(item.object_id), r"^[A-Za-z0-9_.:]+$")

    # --- criterion 5, object-level shape ---------------------------------
    def test_an_inconsistent_observation_is_refused_rather_than_judged(self):
        """Deleting R9 but leaving the partitions referencing it is not a verdict.

        This is not a FAIL and emphatically not a PASS: compare_delta reports
        UNKNOWN / REPAIR_COVERAGE_INCOMPLETE, because an observation that does
        not cover its own partitions cannot support any judgement.  Pinning it
        because "refuse to judge" is a different and stronger property than
        "detect the deviation", and it is easy to regress by accident.
        """
        deviated = copy.deepcopy(self.after)
        deviated["components"] = [c for c in deviated["components"]
                                  if c["reference"] != "R9"]
        deviated["pins"] = [p for p in deviated["pins"]
                            if p["identity"]["reference"] != "R9"]
        verdict = self._verdict(deviated)
        self.assertEqual(verdict["status"], "UNKNOWN")
        self.assertNotEqual(verdict["status"], "PASS")
        self.assertEqual([r["code"] for r in verdict["reasons"]],
                         [pipeline.REASON_COVERAGE_INCOMPLETE])
        self.assertEqual(pipeline._delta_findings(verdict), [])

    def test_an_object_level_absence_is_rendered_named(self):
        """The object-level shape, rendered from a real verdict row.

        The row below is the shape compare_delta emits for an authorized object
        that was never observed, captured from a real DC-04 run rather than
        invented.  Producing it end-to-end would need the real writer, so the
        RENDERING is pinned here and the end-to-end path is opt-in below.
        """
        verdict = {
            "status": "FAIL",
            "reasons": [{"code": pipeline.REASON_DELTA_MISMATCH,
                         "detail": "actual and authorized deltas differ",
                         "stage": pipeline.PHASE_DELTA_CHECK}],
            "missing": [{
                "field": "$",
                "section": "components_added",
                "identity": {"component_uuid": "new:R9", "reference": "R9",
                             "sheet_path": "/s1", "unit": 1},
                "before": {"absent": True},
                "after": {"reference": "R9", "value": "10k", "rotation": 0,
                          "footprint": "Resistor_SMD:R_0603_1608Metric",
                          "identity": {"component_uuid": "new:R9",
                                       "reference": "R9"}},
            }],
            "unexpected": [],
        }
        findings = pipeline._delta_findings(verdict)
        self.assertEqual(len(findings), 1)
        self.assertIn("R9 (new:R9)", findings[0].detail)
        self.assertIn("authorized but not observed", findings[0].detail)
        self.assertEqual(findings[0].object_id, "new:R9")
        self.assertEqual(findings[0].code, pipeline.REASON_DELTA_MISMATCH)
        self.assertEqual(findings[0].stage, pipeline.PHASE_DELTA_CHECK)

    def test_an_object_level_pair_reports_the_differing_fields(self):
        verdict = {
            "status": "FAIL",
            "reasons": [{"code": pipeline.REASON_DELTA_MISMATCH,
                         "detail": "actual and authorized deltas differ"}],
            "missing": [{
                "field": "$", "section": "components_added",
                "identity": {"component_uuid": "new:R9", "reference": "R9"},
                "before": {"absent": True},
                "after": {"reference": "R9", "value": "10k", "rotation": 0},
            }],
            "unexpected": [{
                "field": "$", "section": "components_added",
                "identity": {"component_uuid": "new:R9", "reference": "R9"},
                "before": {"absent": True},
                "after": {"reference": "R9", "value": "20k", "rotation": 0},
            }],
        }
        findings = pipeline._delta_findings(verdict)
        self.assertEqual(len(findings), 1, "the pair must render as one finding")
        detail = findings[0].detail
        self.assertIn("R9 (new:R9)", detail)
        self.assertIn("value", detail)
        self.assertIn("'10k'", detail)
        self.assertIn("'20k'", detail)
        self.assertNotIn("rotation", detail, "only the differing field is reported")

    def test_a_role_is_reported_as_a_role(self):
        """A synthesized identity like new:R9 must keep that label visible."""
        self.assertEqual(pipeline._delta_identity_label(
            {"reference": "R9", "component_uuid": "new:R9"}), "R9 (new:R9)")
        self.assertEqual(pipeline._delta_object_id(
            {"reference": "R9", "component_uuid": "new:R9"}), "new:R9")

    def test_a_plain_uuid_identity_collapses_to_the_reference(self):
        identity = {"reference": "R3",
                    "component_uuid": "2c5361b2-e942-5a48-9439-906dc5051432"}
        self.assertEqual(pipeline._delta_identity_label(identity), "R3")
        self.assertEqual(pipeline._delta_object_id(identity), "R3")

    # --- the findings ADD information, they do not replace it ------------
    def test_the_generic_reason_is_kept_and_the_findings_added(self):
        verdict = self._verdict(self._perturb_value(self.after, "R3", "999R"))
        generic = [r for r in verdict["reasons"]
                   if r["code"] == pipeline.REASON_DELTA_MISMATCH]
        self.assertTrue(generic)
        combined = list(verdict["reasons"]) + pipeline._delta_findings(verdict)
        self.assertGreater(len(combined), len(verdict["reasons"]))
        self.assertIn(pipeline.REASON_DELTA_MISMATCH,
                      [r["code"] for r in verdict["reasons"]])

    def test_a_malformed_verdict_emits_nothing_rather_than_raising(self):
        for verdict in ({}, {"missing": None, "unexpected": None},
                        {"missing": [], "unexpected": []}):
            with self.subTest(verdict=verdict):
                self.assertEqual(pipeline._delta_findings(verdict), [])

    # --- criteria 3 and 4, at the projection level ------------------------
    def test_a_rejection_projects_as_rejected(self):
        """Criterion 3: the public projection is REJECTED, not UNAVAILABLE.

        Driven through _delta_refusal -- the mapping run_round actually calls --
        rather than through _feedback_outcome in isolation.  An earlier version
        of this test called _feedback_outcome directly, so it passed while
        run_round was still refusing with cause_status=STATUS_ROLLBACK and
        publishing a genuinely rejected round as EXECUTION_UNAVAILABLE.  Only the
        end-to-end run against a real writer exposed that.
        """
        verdict = self._verdict(self._perturb_value(self.after, "R3", "999R"))
        status, cause, reasons = pipeline._delta_refusal(verdict)
        self.assertEqual(status, pipeline.STATUS_ROLLBACK)
        self.assertEqual(cause, pipeline.STATUS_BLOCKED)
        self.assertTrue(reasons)
        feedback = pipeline.public_feedback({
            "context_id": CONTEXT, "status": status, "cause_status": cause,
            "reasons": [{"code": pipeline.REASON_DELTA_MISMATCH}]})
        self.assertEqual(feedback["proposal_outcome"], pipeline.OUTCOME_REJECTED)

    def test_the_wrong_cause_status_would_have_published_unavailable(self):
        """Pin WHY the pairing matters, so the fix cannot be quietly undone."""
        verdict = self._verdict(self._perturb_value(self.after, "R3", "999R"))
        status, cause, _ = pipeline._delta_refusal(verdict)
        wrong = pipeline.public_feedback({
            "context_id": CONTEXT, "status": status, "cause_status": status,
            "reasons": []})
        self.assertEqual(wrong["proposal_outcome"], pipeline.OUTCOME_UNAVAILABLE)
        self.assertNotEqual(cause, status)

    def test_run_round_forwards_the_mapped_cause_status(self):
        """The mapping must be wired in, not merely correct in isolation.

        The match is on the full call, not a substring: ``cause_status=cause``
        also occurs inside ``cause_status=cause_status or status`` in refuse()'s
        own default, so a substring guard here passed even with the forwarding
        removed.  That weakness was found by mutation, not by reading.
        """
        import inspect
        import textwrap
        body = textwrap.dedent(_round_source())
        self.assertIn("_delta_refusal", body)
        self.assertIn("status, cause, reasons = _delta_refusal(verdict)", body)
        self.assertIn("refuse(PHASE_DELTA_CHECK, status, reasons, "
                      "cause_status=cause)", body)

    def test_the_rejection_reason_code_maps_to_a_public_reason(self):
        feedback = pipeline.public_feedback({
            "context_id": CONTEXT, "status": pipeline.STATUS_ROLLBACK,
            "cause_status": pipeline.STATUS_BLOCKED,
            "reasons": [{"code": pipeline.REASON_DELTA_MISMATCH}]})
        self.assertNotEqual(feedback["reason_code"], "EXECUTION_UNAVAILABLE")

    def test_a_rejection_can_never_report_committed(self):
        """Criterion 4, structurally: no rejection path names COMMITTED."""
        import inspect
        import textwrap
        body = textwrap.dedent(inspect.getsource(pipeline._delta_findings))
        self.assertNotIn("STATUS_COMMITTED", body)
        self.assertEqual(pipeline._feedback_outcome(
            pipeline.STATUS_ROLLBACK, pipeline.STATUS_BLOCKED),
            pipeline.OUTCOME_REJECTED)
        # COMMITTED is the ONLY status that projects APPLIED_TO_CANDIDATE
        applied = [status for status in (
            pipeline.STATUS_COMMITTED, pipeline.STATUS_NO_CHANGE,
            pipeline.STATUS_REFUSED, pipeline.STATUS_ROLLBACK,
            pipeline.STATUS_BLOCKED, pipeline.STATUS_TOOL_ERROR,
            pipeline.STATUS_UNKNOWN)
            if pipeline._feedback_outcome(status, pipeline.STATUS_BLOCKED)
            == pipeline.OUTCOME_APPLIED]
        self.assertEqual(applied, [pipeline.STATUS_COMMITTED])

    def test_run_round_actually_emits_these_findings(self):
        """The renderer is worthless if the round does not reach it.

        Criteria 5 is about the RECEIPT.  These tests pin the renderer, so the
        wiring has to be pinned too.  run_round delegates to _delta_refusal,
        which is what calls _delta_findings, so both links are asserted -- a
        guard on only the inner name would pass if the delegation were removed
        and the helper left unused.
        """
        import inspect
        import textwrap
        body = textwrap.dedent(_round_source())
        self.assertIn("_delta_refusal", body)
        delegate = textwrap.dedent(inspect.getsource(pipeline._delta_refusal))
        self.assertIn("_delta_findings", delegate)
        # additive, not replacing: the generic verdict reason is still forwarded
        self.assertIn("verdict[\"reasons\"]", body)
        self.assertIn("STATUS_ROLLBACK", delegate)

    # --- the reader's view: criterion 5 stated as a sentence --------------
    def test_a_reader_can_state_the_failure_without_internals(self):
        verdict = self._verdict(self._perturb_value(self.after, "R3", "999R"))
        receipt_reasons = list(verdict["reasons"]) + \
            pipeline._delta_findings(verdict)
        # everything a reviewer is allowed to read
        visible = " ".join(
            "%s %s" % (r["detail"] if isinstance(r, dict) else r.detail,
                       r.get("object_id") if isinstance(r, dict) else r.object_id)
            for r in receipt_reasons)
        self.assertIn("R3", visible)
        self.assertIn("'value'", visible)
        self.assertIn("'10k'", visible)
        self.assertIn("'999R'", visible)
        # and it is not merely a generic error string
        self.assertNotEqual(visible.strip(), "")


class StageCandidateSeparationTests(unittest.TestCase):
    """The writer's stage must be provably disjoint from the candidate.

    Motivation is measured, not theoretical.  ``_WORKSPACE_FIELDS`` declares no
    stage at all, and neither run_round nor akcli_adapter knew where the candidate
    was, so the separation was conventional and enforced by nothing.  Both the M6
    and the M7 demonstration pointed ``stage_root`` at the host's declared
    ``workspace.design_root``; the M7 round was REJECTED and its unauthorized
    bytes were left sitting in the candidate design directory.

    So these tests exist to make "the round stopped before COMMIT" mean "the
    candidate was not modified" rather than merely "no commit phase ran".
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        (self.design / "fault.kicad_sch").write_bytes(b"(kicad_sch)\n")

    def tearDown(self):
        self._tmp.cleanup()

    # --- the classification, in all three overlap shapes ------------------
    def test_an_equal_stage_and_design_root_is_an_overlap(self):
        self.assertEqual(
            pipeline._stage_candidate_overlap(self.design, self.design),
            "equal")

    def test_a_stage_containing_the_design_root_is_an_overlap(self):
        """stage is a descendant of design.

        The direction matters: if the stage merely CONTAINS the design root, the
        adapter's own _resolve_within containment check would still let an
        op-list path reach into the candidate's design.  These two directions
        were once swapped in the implementation and only a run caught it.
        """
        self.assertEqual(
            pipeline._stage_candidate_overlap(self.design / "sub", self.design),
            "design_contains_stage")

    def test_a_design_root_containing_the_stage_is_an_overlap(self):
        self.assertEqual(
            pipeline._stage_candidate_overlap(self.root / "cand", self.design),
            "stage_contains_design")

    def test_a_genuinely_disjoint_stage_is_not_an_overlap(self):
        for stage in (self.root / "scratch",
                      self.root / "a" / "b" / "c",
                      self.design.parent / "repair" / "stage"):
            with self.subTest(stage=str(stage)):
                self.assertIsNone(
                    pipeline._stage_candidate_overlap(stage, self.design))

    def test_a_sibling_with_a_shared_prefix_is_not_an_overlap(self):
        """'design' and 'design-backup' must not be confused for containment."""
        sibling = self.design.parent / "design-backup"
        sibling.mkdir()
        self.assertIsNone(
            pipeline._stage_candidate_overlap(sibling, self.design))

    # --- SNAPSHOT as a real phase (PR1-C5-SNAPSHOT) -----------------------
    def test_the_round_takes_its_snapshot_and_reads_before_from_it(self):
        """BEFORE must come from fixed bytes, not from the stage.

        This is the substance of PR1-C5-SNAPSHOT: the round used to read its
        BEFORE from stage_root, so its before and its after were the same file
        observed either side of one write, and nothing recorded those bytes
        before the round decided anything.
        """
        request = self._round_request()
        receipt = pipeline.run_round(request)
        self.assertIn(pipeline.PHASE_SNAPSHOT,
                      [row["phase"] for row in receipt["phases"]])
        snapshot = receipt.get("snapshot")
        self.assertIsNotNone(snapshot, "no snapshot was taken")
        snapshot_target = Path(snapshot["root"]) / "fault.kicad_sch"
        self.assertTrue(snapshot_target.is_file())
        self.assertEqual(receipt["before_source_sha256"],
                         pipeline.hash_bytes(snapshot_target.read_bytes()))

    def test_before_comes_from_the_snapshot_even_if_the_stage_differs(self):
        """BEFORE must be the SNAPSHOT's bytes, not the stage's.

        Asserting that the before digest equals the snapshot's digest is not
        enough on its own: the stage is seeded FROM the snapshot, so the two are
        equal by construction and a regression reading BEFORE from the stage
        would be invisible. That is exactly why mutation T9 survived the weaker
        assertion.

        So the stage is made to differ AFTER the seeding, between the seed and
        the read. Tampering BEFORE the call is useless -- the seed overwrites it,
        which is the seeding working correctly, and the first version of this
        test made that mistake and asserted the wrong direction.
        """
        request = self._round_request()
        receipt = pipeline.run_round(request)
        snapshot_target = Path(receipt["snapshot"]["root"]) / "fault.kicad_sch"
        self.assertEqual(receipt["before_source_sha256"],
                         pipeline.hash_bytes(snapshot_target.read_bytes()))

    def test_before_is_not_taken_from_a_stage_modified_after_seeding(self):
        """The distinguishing case: the stage differs from the snapshot.

        The stage is modified by the untrusted-environment hook at the moment the
        round would otherwise read BEFORE. If BEFORE came from the stage the
        recorded digest would follow the tampered bytes; coming from the snapshot
        it cannot.
        """
        request = self._round_request()
        original_build = pipeline.build_file_manifest

        def build_then_tamper(root, target):
            manifest = original_build(root, target)
            if Path(root) == Path(request["stage_root"]).resolve():
                # the stage has just been seeded; corrupt it
                (Path(root) / target).write_bytes(
                    b"(kicad_sch (version 20240108) (tampered stage))\n")
            return manifest

        with mock.patch.object(pipeline, "build_file_manifest",
                               build_then_tamper):
            receipt = pipeline.run_round(request)
        snapshot_target = Path(receipt["snapshot"]["root"]) / "fault.kicad_sch"
        self.assertEqual(receipt["before_source_sha256"],
                         pipeline.hash_bytes(snapshot_target.read_bytes()))
        staged = Path(request["stage_root"]) / "fault.kicad_sch"
        self.assertNotEqual(receipt["before_source_sha256"],
                            pipeline.hash_bytes(staged.read_bytes()))

    def test_the_snapshot_lives_outside_the_candidate(self):
        receipt = pipeline.run_round(self._round_request())
        snapshot_root = Path(receipt["snapshot"]["root"]).resolve()
        design = (self.root / "cand" / "design").resolve()
        self.assertNotEqual(snapshot_root, design)
        self.assertNotIn(str(design), str(snapshot_root))

    def test_the_stage_is_seeded_from_the_snapshot(self):
        """Both ends of the round start from the same fixed bytes."""
        request = self._round_request()
        receipt = pipeline.run_round(request)
        snapshot_bytes = (Path(receipt["snapshot"]["root"])
                          / "fault.kicad_sch").read_bytes()
        staged = Path(request["stage_root"]) / "fault.kicad_sch"
        self.assertEqual(staged.read_bytes(), snapshot_bytes)

    def test_a_missing_repair_root_is_refused_rather_than_inventing_one(self):
        """Fail-closed: no repair root means nowhere to snapshot.

        The round must refuse AND take no snapshot. Asserting only the refusal is
        not enough: a mutation that swaps the refusal for an invented location
        still ends the round, just with a different message, so the refusal alone
        does not distinguish them. The snapshot must be absent.
        """
        request = self._round_request()
        del request["host_context"]["workspace"]["repair_root"]
        receipt = pipeline.run_round(request)
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        # PRECHECK, not SNAPSHOT. The refusal is unchanged and still fail-closed;
        # it is now decided one layer earlier because the WRAPPER needs
        # repair_root to locate the durable journal, and it does that before the
        # body reaches SNAPSHOT. Same complaint, earlier decision -- and earlier
        # is correct, since an earlier transaction must be ruled out before this
        # one starts writing.
        self.assertEqual(receipt["phase"], pipeline.PHASE_PRECHECK)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        # the complaint is still about having nowhere to put things, and it now
        # names the FIRST user of repair_root: the durable journal the wrapper
        # must read before the body can take a snapshot
        self.assertIn("journal", detail, detail)
        # the distinguishing assertion: nothing was invented and nothing copied
        self.assertIsNone(receipt.get("snapshot"))
        self.assertNotIn(pipeline.PHASE_SNAPSHOT,
                         [row["phase"] for row in receipt["phases"]
                          if row["status"] == "reached"])

    def test_tampering_with_the_snapshot_after_it_is_taken_is_detected(self):
        """A snapshot is only a record if it cannot drift under the decision."""
        request = self._round_request()
        original = pipeline.materialise_snapshot

        def snapshot_then_tamper(candidate, destination, target):
            root, manifest = original(candidate, destination, target)
            (Path(root) / target).write_bytes(b"(kicad_sch (tampered))\n")
            return root, manifest

        with mock.patch.object(pipeline, "materialise_snapshot",
                               snapshot_then_tamper):
            receipt = pipeline.run_round(request)
        self.assertTrue(receipt["terminal"])
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)
        verification = receipt.get("verification") or {}
        self.assertNotEqual(verification.get("status"), "PASS")

    def test_an_unreadable_snapshot_says_which_operation_failed(self):
        """A read failure must not read as a caller's missing file.

        The snapshot block performs three of its own operations in one try: copy
        the tree, seed the stage, read BEFORE out of the snapshot. A bare OSError
        message ("[Errno 2] No such file") names none of them, and earlier in this
        round a genuine ordering bug presented exactly that way -- the stage
        re-seed deleted the op-list and the receipt blamed the caller.

        The injection is Path.read_bytes scoped to the snapshot root, because the
        stage is seeded FROM the snapshot: deleting the target makes the stage
        manifest build fail first, which is a different refusal. Two earlier
        versions of this test therefore did not test the read at all -- the first
        compared against a repair_root the fixture never uses, the second broke
        the stage instead of the read.
        """
        request = self._round_request()
        original_snapshot = pipeline.materialise_snapshot
        original_read = Path.read_bytes
        captured = {}

        def capture_snapshot(candidate, destination, target):
            root, manifest = original_snapshot(candidate, destination, target)
            captured["root"] = str(Path(root).resolve())
            return root, manifest

        def read_bytes_but_fail_for_the_snapshot(path_self):
            if str(path_self.resolve()).startswith(captured.get("root", "\\0")):
                raise FileNotFoundError(
                    2, "No such file or directory", str(path_self))
            return original_read(path_self)

        with mock.patch.object(pipeline, "materialise_snapshot",
                               capture_snapshot), \
                mock.patch.object(Path, "read_bytes", read_bytes_but_fail_for_the_snapshot):
            receipt = pipeline.run_round(request)

        self.assertTrue(captured, "the snapshot was never taken")
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        self.assertEqual(receipt["phase"], pipeline.PHASE_SNAPSHOT)
        self.assertEqual(receipt["phases"],
                         [{"phase": pipeline.PHASE_SNAPSHOT, "status": "refused"}])
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("could not be read out of it", detail)
        # the cause is still reported, not swallowed
        self.assertIn("No such file", detail)

    def _round_request(self, **overrides):
        """A request that gets as far as the snapshot, on a VALID host context.

        An earlier version built the host context by hand and it was missing
        authority, target, run_id, toolchain_binding and ten more fields, so
        validate_host_context rejected it and every snapshot test quietly
        observed a PRECHECK refusal instead.  The module's `host_context()`
        helper is used instead, the same one RunRoundTests uses, so these tests
        travel the path a real round travels.
        """
        cand = self.root / "cand"
        (cand / "design").mkdir(parents=True, exist_ok=True)
        raw = b"(kicad_sch)\n"
        (cand / "design" / "fault.kicad_sch").write_bytes(raw)
        stage = self.root / "stage"
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "fault.kicad_sch").write_bytes(raw)
        oplist = stage / "repair_ops.json"
        oplist.write_text(json.dumps(
            {"protocol_version": 2, "target_format": "kicad", "ops": []}),
            encoding="utf-8")
        context = pipeline.validate_host_context(host_context(
            design_root=str(cand),
            base_source_sha256=pipeline.hash_bytes(raw),
            target="fault.kicad_sch",
            authority=authority(approvals=[{
                "policy_file_sha256": policy_sha(), "rule_id": "DC-04",
                "run_id": RUN, "candidate_id": CAND, "paths": [str(cand)]}]),
        ))
        request = {
            "host_context": context,
            # parse_proposal requires 1..8 ops, so the ops are NOT empty. They
            # are the real frozen DC-04 ops; whether the writer executes them is
            # a different matter, and irrelevant here because the pinned akcli is
            # not importable on this interpreter. An earlier version used an empty
            # op list and was refused with "$.oplist.ops must hold 1..8 ops",
            # which surfaced as a PRECHECK refusal rather than a snapshot.
            "proposal_raw": json.dumps({
                "schema_version": 1, "context_id": CONTEXT,
                "target": "fault.kicad_sch",
                "base_source_sha256": pipeline.hash_bytes(raw),
                "decision": pipeline.DECISION_PATCH,
                "diagnosis": [{"rule_id": "DC-04", "observed": "nothing",
                               "fact_ids": ["F1"],
                               "requirement_level": "MANDATORY",
                               "rationale": "snapshot tests"}],
                "oplist": {"protocol_version": 2, "target_format": "kicad",
                           "ops": json.loads((Path(__file__).resolve().parent
                                              / "fixtures" / "repair_pr1" / "native"
                                              / "DC-04" / "repair_ops.json")
                                             .read_text(encoding="utf-8"))["ops"]},
            }, ensure_ascii=False).encode("utf-8"),
            "txn_id": "txn-snapshot-1",
            "stage_root": str(stage),
            "stage_target": "fault.kicad_sch",
            "oplist_path": str(oplist),
            "native_artifact_root": str(self.root / "artifacts"),
        }
        request.update(overrides)
        return request

    # --- the guard as run_round applies it -------------------------------
    def _request(self, stage_root, design_root=None, **overrides):
        cand = self.root / "cand"
        (cand / "design").mkdir(parents=True, exist_ok=True)
        (cand / "design" / "fault.kicad_sch").write_bytes(b"(kicad_sch)\n")
        stage = Path(stage_root)
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "fault.kicad_sch").write_bytes(b"(kicad_sch)\n")
        oplist = stage / "repair_ops.json"
        oplist.write_text(json.dumps(
            {"protocol_version": 2, "target_format": "kicad", "ops": []}),
            encoding="utf-8")
        request = {
            "host_context": {
                "candidate_symbol_digest": fixtures_symbol(),
                "context_id": CONTEXT,
                "workspace": {
                    "candidate_root": str(cand),
                    "design_root": str(design_root or (cand / "design")),
                    "repair_root": str(cand / ".repair"),
                    "lock_path": str(cand / ".repair.lock"),
                },
            },
            "proposal_raw": b"{}",
            "txn_id": "txn-separation-1",
            "stage_root": str(stage),
            "stage_target": "fault.kicad_sch",
            "oplist_path": str(oplist),
            "native_artifact_root": str(stage),
        }
        request.update(overrides)
        return request

    def test_run_round_refuses_a_stage_that_is_the_candidate(self):
        receipt = pipeline.run_round(self._request(self.design))
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["phase"], pipeline.PHASE_PRECHECK)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("disjoint", detail)
        self.assertIn("IS the candidate design root", detail)
        # and it names BOTH paths
        self.assertIn(str(self.design.resolve()), detail)

    def test_run_round_refuses_a_stage_nested_inside_the_candidate(self):
        receipt = pipeline.run_round(self._request(self.design / "scratch"))
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("INSIDE the candidate design root", detail)

    def test_run_round_refuses_a_stage_that_contains_the_candidate(self):
        receipt = pipeline.run_round(self._request(self.design.parent))
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("CONTAINS the candidate design root", detail)

    def test_the_refusal_happens_before_any_byte_is_read_from_the_stage(self):
        """A rejected stage must not even be observed.

        Proven behaviourally rather than by reading the source: the stage is BOTH
        overlapping AND missing its target file.  If the guard runs first the
        finding is the separation one; if the read ran first the finding would be
        "could not be read for observation" instead.  The two are
        distinguishable, so the ordering is actually observed.
        """
        request = self._request(self.design)
        (self.design / "fault.kicad_sch").unlink()
        receipt = pipeline.run_round(request)
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("disjoint", detail)
        self.assertNotIn("could not be read for observation", detail)

    def test_the_receipt_records_both_roots_for_a_disjoint_stage(self):
        scratch = self.root / "scratch"
        receipt = pipeline.run_round(self._request(scratch))
        # it gets past the guard (and fails later, for an unrelated reason)
        self.assertNotEqual(
            " ".join(getattr(r, "detail", "") for r in receipt["reasons"]),
            "")
        self.assertEqual(receipt["candidate_design_root"],
                         str((self.root / "cand" / "design").resolve()))

    def test_a_context_without_a_design_root_is_refused_fail_closed(self):
        """Disjointness that cannot be proven must not be assumed."""
        request = self._request(self.root / "scratch")
        del request["host_context"]["workspace"]["design_root"]
        receipt = pipeline.run_round(request)
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("cannot be proven disjoint", detail)

    # --- existing behaviour must be untouched ----------------------------
    def test_the_pre_existing_round_tests_are_unaffected(self):
        """The 25 RunRoundTests must keep passing; the guard adds no new field."""
        self.assertNotIn("design_root", pipeline.ROUND_FIELDS)
        self.assertNotIn("candidate_root", pipeline.ROUND_FIELDS)
        for name in ("stage_root", "candidate_design_root"):
            self.assertIn(name, pipeline._round_receipt(
                pipeline.STATUS_BLOCKED, pipeline.PHASE_PRECHECK, [], False))


def fixtures_symbol():
    from tests.test_repair_pipeline import SYMBOL
    return SYMBOL


class ThinVerificationMappingTests(unittest.TestCase):
    """PR1-C5-VERIFY-STAGE: contract line 373's status mapping, table-driven.

    The table is separated from run_round precisely so it can be tested without
    running the verifier, following the `_delta_refusal` precedent. Each row is
    contract text, not a preference.
    """

    def test_each_row_of_the_contract_mapping(self):
        """Compared against the LITERALS, not the constants.

        The first version built its expectations from `pipeline.STATUS_*` -- the
        very constants `_THIN_REFUSAL_CAUSE` is built from -- so mutating the
        table moved the expectation with it and mutation V6 passed. That is the
        same defect as K5 in PR #99, in a new place. `test_the_status_constants_
        are_what_the_contract_calls_them` pins the constants separately.
        """
        rows = (
            # (verify_stage status, expected round status, expected cause)
            # contract line 373, in its own words
            ("FAIL", "ROLLBACK", "BLOCKED"),        # 真实回归
            ("BLOCKED", "ROLLBACK", "BLOCKED"),     # 旧报告 / 源漂移
            ("TOOL_ERROR", "ROLLBACK", "TOOL_ERROR"),  # 缺工具/超时/坏 XML
            ("UNKNOWN", "ROLLBACK", "UNKNOWN"),     # coverage / 解析器分歧
        )
        for thin, want_status, want_cause in rows:
            status, cause, reasons = pipeline._thin_verification_refusal(
                {"status": thin, "reasons": []})
            self.assertEqual(status, want_status, thin)
            self.assertEqual(cause, want_cause, thin)
            self.assertTrue(reasons, "%s produced no reason at all" % thin)

    def test_the_status_constants_are_what_the_contract_calls_them(self):
        for name, value in (("STATUS_ROLLBACK", "ROLLBACK"),
                            ("STATUS_BLOCKED", "BLOCKED"),
                            ("STATUS_TOOL_ERROR", "TOOL_ERROR"),
                            ("STATUS_UNKNOWN", "UNKNOWN")):
            self.assertEqual(getattr(pipeline, name), value, name)

    def test_every_row_of_the_table_is_covered_by_the_literal_test(self):
        """A row added to the table without a contract row is a silent gap."""
        self.assertEqual(sorted(pipeline._THIN_REFUSAL_CAUSE),
                         ["BLOCKED", "FAIL", "TOOL_ERROR", "UNKNOWN"])

    def test_a_real_regression_is_not_published_as_a_tool_problem(self):
        """FAIL must not become cause=TOOL_ERROR.

        The delta verdict already learned this the hard way: a ROLLBACK caused by
        a BLOCKED authorization publishes as REJECTED, not UNAVAILABLE, and
        getting that pairing wrong was silent. Same trap, different verdict.
        """
        _, cause, _ = pipeline._thin_verification_refusal(
            {"status": "FAIL", "reasons": []})
        self.assertNotEqual(cause, pipeline.STATUS_TOOL_ERROR)
        self.assertNotEqual(cause, pipeline.STATUS_UNKNOWN)

    def test_an_unrecognised_status_is_never_treated_as_a_pass(self):
        status, cause, reasons = pipeline._thin_verification_refusal(
            {"status": "SOMETHING_NEW", "reasons": []})
        self.assertEqual(status, pipeline.STATUS_ROLLBACK)
        self.assertEqual(cause, pipeline.STATUS_UNKNOWN)
        self.assertTrue(reasons)

    def test_a_bare_refusal_still_names_itself(self):
        """A verifier that returns a status and no reason is still reported."""
        _, _, reasons = pipeline._thin_verification_refusal(
            {"status": "UNKNOWN", "reasons": []})
        self.assertEqual(len(reasons), 1)
        self.assertIn("UNKNOWN", getattr(reasons[0], "detail", ""))

    def test_the_verifiers_dict_reasons_become_readable_findings(self):
        """verify_stage reports dicts; a dict has no .detail.

        Passing them through unchanged would be SILENT -- every consumer reads
        reasons with getattr(r, "detail", ""), so a dict yields "" and the
        refusal appears to carry no explanation. The first version of this test
        passed dicts in and then indexed .detail on them, which is the same
        mistake the production code would have made.
        """
        given = [{"code": pipeline.REASON_COVERAGE_INCOMPLETE,
                  "stage": pipeline.PHASE_KICAD_VERIFY, "object_id": None,
                  "detail": "the parser disagreed"}]
        _, _, reasons = pipeline._thin_verification_refusal(
            {"status": "UNKNOWN", "reasons": given})
        self.assertEqual([r.detail for r in reasons], ["the parser disagreed"])
        self.assertEqual([r.code for r in reasons],
                         [pipeline.REASON_COVERAGE_INCOMPLETE])
        self.assertEqual([r.stage for r in reasons],
                         [pipeline.PHASE_KICAD_VERIFY])

    def test_a_reason_dict_with_no_detail_still_says_something(self):
        _, _, reasons = pipeline._thin_verification_refusal(
            {"status": "UNKNOWN",
             "reasons": [{"code": pipeline.REASON_INPUT_DRIFT}]})
        self.assertTrue(reasons[0].detail)

    def test_a_non_mapping_reason_is_kept_rather_than_dropped(self):
        _, _, reasons = pipeline._thin_verification_refusal(
            {"status": "UNKNOWN", "reasons": ["something went sideways"]})
        self.assertIn("something went sideways", reasons[0].detail)

    def test_pending_phases_no_longer_claims_a_reached_phase(self):
        """A round that reached KICAD_VERIFY must not report it as pending.

        The superseded tuple was (KICAD_VERIFY, COMMIT) and was written
        unconditionally, so a round that had just run the phase still reported it
        pending. A receipt that contradicts itself is worse than no receipt.
        """
        self.assertEqual(pipeline.ROUND_PENDING_PHASES, (pipeline.PHASE_COMMIT,))
        self.assertNotIn(pipeline.PHASE_KICAD_VERIFY,
                         pipeline.ROUND_PENDING_PHASES)
        self.assertEqual(
            pipeline.ROUND_PENDING_PHASES_SUPERSEDED,
            (pipeline.PHASE_KICAD_VERIFY, pipeline.PHASE_COMMIT))

    def test_the_phase_order_matches_the_contract(self):
        """Contract line 355, in the order the receipt records them."""
        self.assertEqual(
            (pipeline.PHASE_PRECHECK, pipeline.PHASE_SNAPSHOT,
             pipeline.PHASE_STAGE_APPLY, pipeline.PHASE_DELTA_CHECK,
             pipeline.PHASE_KICAD_VERIFY, pipeline.PHASE_COMMIT),
            ("PRECHECK", "SNAPSHOT", "STAGE_APPLY", "DELTA_CHECK",
             "KICAD_VERIFY", "COMMIT"))


class CommitPredicateTests(unittest.TestCase):
    """Contract 335-347, the pipeline's ONLY commit predicate (line 349: a
    conjunction, with no "high confidence" / "warning only" / "most checks PASS"
    exception)."""

    def _thin(self, **overrides):
        """A thin result in the SHAPE the real verifier produces.

        That shape is the point. The first version of the predicate read
        `checks` values as strings, `coverage` as {before: True} and
        `parser_agreement` values as strings; the real producer emits dicts for
        checks and agreement, and `coverage` carries `complete`. So the predicate
        was False for every genuine PASS and no test noticed, because the round
        refused for a different reason. `test_a_real_pass_satisfies_the_invariant
        _conjunct` below is the test that would have caught it.
        """
        thin = {
            "status": "PASS",
            "scope": "PR1_CANDIDATE_BYTES",
            "txn_id": "txn-1", "run_id": "run-1", "candidate_id": "cand-1",
            "bound_policy_sha256": "b" * 64, "toolchain_sha256": "c" * 64,
            "dependencies_unchanged": True,
            "checks": {name: {"status": "PASS", "reason_codes": [],
                              "artifact_paths": []}
                       for name in ("fresh_export", "source_hash_binding",
                                    "exact_topology_delta", "protected_diff")},
            "coverage": {"before": {"complete": True, "keys": ["a"],
                                    "expected_sha256": "d" * 64,
                                    "observed_sha256": "d" * 64},
                         "after": {"complete": True, "keys": ["a"],
                                   "expected_sha256": "d" * 64,
                                   "observed_sha256": "d" * 64}},
            "parser_agreement": {"before": {"status": "PASS", "reason_codes": []},
                                 "after": {"status": "PASS", "reason_codes": []}},
            "exports": [{"role": "BEFORE", "completed": True},
                        {"role": "AFTER", "completed": True}],
            "missing_delta": [], "unexpected_delta": [],
            "protected_changes": [],
            "deferred": {"erc": "NOT_RUN", "semantic_runner": "NOT_RUN",
                         "formal_evidence": "NOT_RUN"},
            "reasons": [],
        }
        thin.update(overrides)
        return thin

    def _receipt(self, **overrides):
        receipt = {
            "txn_id": "txn-1", "route": "STRICT",
            "stage": {"status": "APPLIED_TO_STAGE", "tool_applied": True,
                      "changed": True, "one_write_call": True},
            "kicad_verify": {"run_id": "run-1", "bound_policy_sha256": "b" * 64,
                             "toolchain_sha256": "c" * 64,
                             "dependencies_unchanged": True},
        }
        receipt.update(overrides)
        return receipt

    def _ok(self, receipt=None, thin=None, **overrides):
        # writer_calls defaults to 1 because that is what a correct round does,
        # and the point of the table below is that every OTHER conjunct is
        # observable in isolation.
        args = {"live_equals_snapshot": True, "hashes_recomputed": True,
                "binding_drift": [], "permission_drift": [], "lock_held": True,
                "writer_calls": 1}
        args.update(overrides)
        return pipeline._commit_predicate(
            receipt or self._receipt(), thin or self._thin(), **args)

    def test_it_is_pure_and_reports_each_failure(self):
        ok, reasons, unsatisfied = self._ok()
        self.assertTrue(ok)
        self.assertEqual(reasons, [])
        self.assertEqual(unsatisfied, [])
        # calling it again with the same arguments gives the same answer
        self.assertEqual(self._ok()[:3], (ok, reasons, unsatisfied))

    def test_every_conjunct_is_independently_observable(self):
        """Each of the nine, driven to failure with the other eight satisfied.

        This is the test the aliasing bug could not survive. A conjunct that is
        checked twice under two names, or checked against a constant that never
        varies, cannot produce this table.
        """
        # Every row is (receipt_overrides, thin_overrides, call_overrides) --
        # all three, even when two are empty. The first version mixed 2-tuples
        # and 3-tuples and the unpacking raised ValueError.
        cases = {
            # contract 338
            "stage_applied_to_stage": (
                {"stage": {"status": "REFUSED", "tool_applied": True,
                           "changed": True, "one_write_call": True}}, {}, {}),
            # contract 339 -- route, tool result, ONE WRITE CALL, effect. This
            # row breaks `tool_applied`, NOT the route: the first version set
            # the route to CONSTRAINED_EXCEPTION expecting a failure, but that
            # is one of the two routes the policy document really defines, so
            # the conjunct correctly held. The route half has its own test.
            "route_and_effect_checks": (
                {"stage": {"status": "APPLIED_TO_STAGE", "tool_applied": False,
                           "changed": True}}, {}, {}),
            # contract 340
            "thin_scope_is_candidate_bytes": (
                {}, {"scope": "SOMETHING_ELSE"}, {}),
            # contract 341
            "thin_pass_invariants": ({}, {"status": "UNKNOWN"}, {}),
            # contract 342
            "bindings_equal": (None, None, {"binding_drift": ["run_id differs"]}),
            # contract 343
            "recomputed_hashes_match": (None, None, {"hashes_recomputed": False}),
            # contract 344
            "live_design_still_equals_snapshot": (
                None, None, {"live_equals_snapshot": False}),
            # contract 345
            "policy_and_dependencies_undrifted": (
                None, None, {"permission_drift": ["dependencies changed"]}),
            # contract 346
            "single_writer_lock_held": (None, None, {"lock_held": False}),
        }
        self.assertEqual(sorted(cases), sorted(pipeline.COMMIT_CONJUNCTS),
                         "the table and the contract's nine conjuncts disagree")
        for name, (receipt_over, thin_over, call_over) in sorted(cases.items()):
            ok, reasons, unsatisfied = self._ok(
                receipt=self._receipt(**receipt_over) if receipt_over else None,
                thin=self._thin(**thin_over) if thin_over else None,
                **call_over)
            self.assertFalse(ok, "%s was not observable" % name)
            self.assertEqual(unsatisfied, [name],
                             "%s did not fail alone: %r" % (name, unsatisfied))
            # The conjunct is named FIRST and always. A drift conjunct carries a
            # SECOND reason naming what differs -- "bindings_equal" alone tells a
            # reader nothing actionable. So the count is 2 for the two drift
            # conjuncts and 1 for the rest; the first version asserted 1 for all
            # nine, which was wrong about the implementation, not strict.
            self.assertIn(name, reasons[0].detail,
                          "the first reason must name the conjunct")
            carries_note = bool(call_over.get("binding_drift")
                                or call_over.get("permission_drift"))
            self.assertEqual(
                len(reasons), 2 if carries_note else 1,
                "%s produced %d reasons" % (name, len(reasons)))
            if carries_note:
                note = (call_over.get("binding_drift")
                        or call_over.get("permission_drift"))[0]
                self.assertIn(note, reasons[1].detail,
                              "the drift note was not carried through")

    def test_the_write_call_count_is_the_rounds_own(self):
        """Contract 339's "one-write-call" and 371's 「native 只调用一次」.

        The first version read this from `apply_stage`'s receipt, which has no
        such field -- so the conjunct was unsatisfiable in PRODUCTION as well as
        in tests, and a real round refused at COMMIT with
        `route_and_effect_checks`. Found by driving a real round, not by a green
        suite. The count is now the round's own, passed in.

        So: any count other than exactly 1 fails the conjunct, and the value is
        not read out of any receipt.
        """
        for calls, should_pass in ((1, True), (0, False), (2, False), (7, False)):
            ok, _, unsatisfied = self._ok(writer_calls=calls)
            self.assertEqual(ok, should_pass,
                             "writer_calls=%d" % calls)
            if not should_pass:
                self.assertIn("route_and_effect_checks", unsatisfied)
        source = Path(pipeline.__file__).read_text(encoding="utf-8")
        self.assertNotIn('stage.get("one_write_call")', source,
                         "the conjunct reads a field apply_stage never emits")

    def test_a_real_pass_satisfies_the_invariant_conjunct(self):
        """Conjunct 4 must accept the SHAPE the real verifier emits.

        This is the test the wrong-shape bug could not survive: it hands the
        predicate a dict-shaped `checks` and a dict-shaped `parser_agreement`
        with the real `coverage` keys, which is what gates/repair_verification.py
        produces. The first version read all three as strings and was False for
        every genuine PASS.

        It also asserts the invariant is the VERIFIER's, not a local copy: a
        result whose four checks are not all PASS cannot be status PASS, because
        gates:2014-2019 would not have produced that status.
        """
        ok, reasons, unsatisfied = self._ok()
        self.assertTrue(ok, "a real-shaped thin PASS was rejected: %s"
                        % [r.detail for r in reasons])
        for name, check in self._thin()["checks"].items():
            self.assertIsInstance(check, dict,
                                  "%s is a dict in the real result" % name)
        # a FAIL check is not reachable as a PASS status, so the conjunct holds
        ok, _, _ = self._ok(thin=self._thin(status="FAIL"))
        self.assertFalse(ok)

    def test_the_routes_are_the_policy_document_s_own(self):
        """M3: the first version listed a route that exists nowhere.

        Read from the policy document rather than restated, because a test that
        builds its expectation from a constant in the module under test is the
        pattern `test_each_row_of_the_contract_mapping` already documents.
        """
        import json
        policy = json.loads(
            (Path(pipeline.__file__).resolve().parents[1]
             / "src" / "repair" / "topology_policy_v1.json").read_text(
                 encoding="utf-8"))
        found = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "route" and isinstance(value, str):
                        found.add(value)
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(policy)
        self.assertTrue(found, "no route found in the policy document")
        self.assertEqual(set(pipeline.COMMIT_ROUTES), found)
        for route in found:
            ok, _, unsatisfied = self._ok(receipt=self._receipt(route=route))
            self.assertTrue(ok, "route %r can never commit: %s"
                            % (route, unsatisfied))
        ok, _, unsatisfied = self._ok(receipt=self._receipt(route="SAFE"))
        self.assertFalse(ok, "a route the policy does not define was accepted")
        self.assertIn("route_and_effect_checks", unsatisfied)


class CommitJournalTests(unittest.TestCase):
    """Contract 387: recovery reads the durable journal, and a history reader
    that skips bad lines must not be its sole basis."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aedl-journal-")
        self.journal = Path(self.root) / "journal.jsonl"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _record(self, **overrides):
        # The FULL field set, not a hand-picked subset: `JOURNAL_FIELDS` gained
        # snapshot_root / snapshot_sha256 / design_root because contract 385's
        # restore has to read the snapshot's original bytes, and a recovery that
        # could not find them could only guess. A fixture carrying a subset
        # would be refused as malformed -- which is the reader working correctly
        # and the test being wrong about the shape.
        row = {"kind": pipeline.JOURNAL_COMMIT_INTENT, "txn_id": "old-txn",
               "run_id": "run-1", "candidate_id": "cand-1", "patch_id": "p-1",
               "stage_sha256": "a" * 64, "before_sha256": "b" * 64,
               "after_sha256": "c" * 64, "target": "x", "status": None,
               "snapshot_root": str(Path(self.root) / "snapshot"),
               "snapshot_sha256": "b" * 64,
               "design_root": str(Path(self.root) / "cand" / "design")}
        row.update(overrides)
        return row

    def test_a_torn_final_line_fails_closed_rather_than_reading_as_absent(self):
        """The normal artefact of a crash mid-append is a torn LAST line.

        A reader that skips it concludes "no COMMIT_INTENT", i.e. "the round
        never committed" -- the exact inversion contract 387 forbids.
        """
        import json
        good = json.dumps(self._record(), sort_keys=True)
        with open(str(self.journal), "w", encoding="utf-8") as handle:
            handle.write(good + "\n")
            handle.write('{"kind": "COMMIT_INTENT", "txn_id": "torn"')  # no newline

        records, corrupt = pipeline._read_journal(self.journal)
        self.assertEqual(len(records), 1, "the intact line should still read")
        self.assertEqual(len(corrupt), 1)
        self.assertIn("LAST line", corrupt[0],
                      "the tear was not identified as the final line")
        self.assertIn("torn by a crash", corrupt[0])

        pending, corrupt_out = pipeline._unresolved_intents(self.journal, "new")
        self.assertEqual(pending, [], "nothing may be reported as pending here")
        self.assertEqual(len(corrupt_out), 1,
                         "a corrupt journal must NOT come back as clean")

    def test_a_corrupt_interior_line_is_also_reported(self):
        import json
        with open(str(self.journal), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(self._record(), sort_keys=True) + "\n")
            handle.write("not json at all\n")
            handle.write(json.dumps(
                self._record(txn_id="later"), sort_keys=True) + "\n")
        records, corrupt = pipeline._read_journal(self.journal)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(corrupt), 1)
        self.assertNotIn("LAST line", corrupt[0],
                         "an interior line is not a torn final line")

    def test_a_record_missing_a_field_is_reported_not_accepted(self):
        import json
        row = self._record()
        del row["patch_id"]
        with open(str(self.journal), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
        records, corrupt = pipeline._read_journal(self.journal)
        self.assertEqual(records, [])
        self.assertEqual(len(corrupt), 1)
        self.assertIn("patch_id", corrupt[0])

    def test_an_unresolved_intent_is_found_and_a_terminal_one_is_not(self):
        import json
        with open(str(self.journal), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(self._record(txn_id="open-1"),
                                    sort_keys=True) + "\n")
            handle.write(json.dumps(self._record(txn_id="closed-1"),
                                    sort_keys=True) + "\n")
            handle.write(json.dumps(
                self._record(txn_id="closed-1", kind=pipeline.JOURNAL_TERMINAL,
                             status=pipeline.STATUS_COMMITTED),
                sort_keys=True) + "\n")
        pending, corrupt = pipeline._unresolved_intents(self.journal, "new-txn")
        self.assertEqual(corrupt, [])
        self.assertEqual([row["txn_id"] for row in pending], ["open-1"],
                         "a terminalised transaction must not be pending")

    def test_this_rounds_own_intent_is_not_pending(self):
        import json
        with open(str(self.journal), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(self._record(txn_id="mine"),
                                    sort_keys=True) + "\n")
        pending, _ = pipeline._unresolved_intents(self.journal, "mine")
        self.assertEqual(pending, [])

    def test_the_fixture_matches_the_field_set_the_reader_demands(self):
        """A hand-written record is a liability, so pin it to the real set.

        Without this, adding a field to `JOURNAL_FIELDS` would make every test
        in this class fail with a confusing "missing ..." message, and the fix
        would be to trim the fixture rather than to think about the new field.
        """
        record = self._record()
        self.assertEqual(sorted(record), sorted(pipeline.JOURNAL_FIELDS))

    def test_a_missing_journal_is_empty_not_an_error(self):
        self.assertEqual(pipeline._read_journal(
            Path(self.root) / "absent.jsonl"), ([], []))
        self.assertEqual(pipeline._unresolved_intents(
            Path(self.root) / "absent.jsonl", "new"), ([], []))

    def test_a_corrupt_journal_refuses_at_precheck(self):
        """Contract 369: 先处理未完成事务. A journal this reader cannot trust
        means an earlier transaction cannot be ruled out."""
        with open(str(self.journal), "w", encoding="utf-8") as handle:
            handle.write("{ this is not json\n")
        request = self._request(repair_root=self.root)
        receipt = pipeline.run_round(request)
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("never committed", detail)
        self.assertIn("cannot trust", detail)

    def test_live_bytes_that_are_neither_before_nor_after_are_quarantined(self):
        """CONVERTED to contract 386's QUARANTINE -- the branch that must refuse.

        PR #101 asserted "an unresolved intent refuses at PRECHECK and names the
        file", which was correct while rule 385's restore did not exist. Now that
        it does, an ORDINARY unresolved intent is resolved and the round carries
        on, so that assertion is no longer true of this fixture.

        Rather than delete it, it moves to the one case where refusing is the ONLY
        correct answer: the live bytes match neither the recorded before-digest
        nor the recorded after-digest, so they may be a human's edit or another
        process's. Contract 386: 「隔离现场，不覆盖可能的人类/其他进程修改」 --
        quarantine, do not overwrite, do not open another round.

        So the round refuses, says it QUARANTINED (a different human response from
        a plain failure), names the transaction and the journal, and leaves the
        bytes exactly as found.
        """
        import json
        from tests.test_repair_pipeline import RunRoundTests
        # Path(), because CommitJournalTests.setUp does `tempfile.mkdtemp()` and
        # so `self.root` is a STRING here -- unlike the suites where a fixture
        # attribute shadows it with a Path. `self.root / "cand"` raised TypeError.
        design = Path(self.root) / "cand" / "design"
        design.mkdir(parents=True, exist_ok=True)
        stranger = design / RunRoundTests.STAGE_TARGET
        stranger.write_bytes(b"\x00 someone else wrote this\n")
        stranger_sha = pipeline.hash_bytes(stranger.read_bytes())

        record = self._record(txn_id="stuck")
        record["target"] = str(stranger)
        with open(str(self.journal), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

        receipt = pipeline.run_round(self._request(repair_root=self.root))

        self.assertTrue(receipt["terminal"])
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("QUARANTINE", detail,
                      "the refusal must distinguish quarantining from failing")
        self.assertIn("stuck", detail, "the unresolved txn was not named")
        self.assertIn("journal.jsonl", detail,
                      "the reason must name the file a human has to read")
        # the whole point of rule 386: unrecognised bytes are left alone
        self.assertEqual(pipeline.hash_bytes(stranger.read_bytes()), stranger_sha,
                         "recovery overwrote bytes it did not recognise")

    def _request(self, repair_root=None):
        """RunRoundTests' real fixture, with its setUp actually run.

        Reusing the repository's own builder rather than hand-rolling a second
        copy: the first version called `_request` on a bare instance, which has
        no `self.cand`, and raised AttributeError.

        `repair_root` is nested inside `host_context.workspace`, not passed flat.
        Passing it flat added an unknown top-level field and the round refused
        with REPAIR_SCHEMA_INVALID before ever reaching the journal -- which
        would have made the test pass for entirely the wrong reason, since an
        absent journal also reports "no pending intents".
        """
        from tests.test_repair_pipeline import RunRoundTests
        case = RunRoundTests("test_the_request_must_be_a_mapping")
        case.setUp()
        self.addCleanup(case.tearDown)
        request = case._request()
        if repair_root is not None:
            request["host_context"]["workspace"]["repair_root"] = str(repair_root)
            # and prove the round reads the journal from exactly there, so a
            # path typo cannot make a refusal test pass vacuously
            self.assertEqual(pipeline._journal_file(request["host_context"]),
                             Path(repair_root).resolve() / "journal.jsonl")
        return request


class VerifyStageWiringTests(unittest.TestCase):
    """PR1-C5-VERIFY-STAGE: run_round calls the contract's own verifier.

    `verify_stage` had 25 test callers and ZERO production callers. These tests
    are about the wiring, not about the verifier, which `tests/test_repair_
    verification.py` already covers.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "repair_pr1" / "native"
    CASE = "DC-04"

    def test_the_real_verifier_accepts_the_request_run_round_builds(self):
        """Nothing in this file executed the real `verify_stage` until now.

        Every other wiring test patches it, so nothing established that the
        request `run_round` assembles is ACCEPTED by the consumer -- and the
        envelope's acceptance criterion for the two fresh exports is therefore
        untested in the suite. The end-to-end harness proves it against real
        kicad-cli, but that is not the suite and does not run in CI here.

        So: capture the request, hand it to the REAL verifier, and require the
        real refusal. It will refuse on this interpreter -- the pinned akcli is
        not importable, and the frozen export toolchain points at a kicad-cli
        that is not the bound one -- but the point is that it refuses with a
        NAMED reason about a VALIDATED request, not "you have missing or unknown
        fields". That distinction is exactly what a hand-forked request breaks.
        """
        from gates import repair_verification as c2
        seen = {}
        self._run_with(verify_stage=lambda request: (
            seen.update(request), self._thin("PASS"))[1])

        # the request is complete and of the right shape before it is used at all
        self.assertEqual(sorted(seen), sorted(c2._VERIFICATION_REQUEST_FIELDS))
        c2.toolchain_manifest(seen["toolchain_manifest"])
        c2._manifest(seen["before_manifest"])
        c2._manifest(seen["staged_manifest"])

        result = c2.verify_stage(dict(seen))
        self.assertIn(result["status"], ("PASS", "FAIL", "BLOCKED",
                                          "TOOL_ERROR", "UNKNOWN"))
        # and it got past REQUEST VALIDATION, which is the property at stake
        blob = " ".join(str(r) for r in (result.get("reasons") or []))
        self.assertNotIn("missing or unknown fields", blob)
        self.assertNotIn("has missing or unknown fields", blob)
        # a refusal, if any, names something concrete
        if result["status"] != "PASS":
            self.assertTrue(result.get("reasons"),
                            "the real verifier refused with no reason at all")

    def test_the_deriver_used_is_the_repository_own(self):
        """C1: the KiCad slice must come from the canonical deriver.

        A parallel copy produced a DIFFERENT toolchain digest for a legal
        binding -- the canonical `_resolved_files` sorts the declared rows and
        the copy did not, and `canonical_json_bytes` sorts dict keys but not
        lists -- so the gate the receipt exists to satisfy refused legitimate
        runs. This is the same failure mode as PR #99.
        """
        import inspect
        from pathlib import Path as _Path
        source = _Path(pipeline.__file__).read_text(encoding="utf-8")
        body = _round_source()
        self.assertIn("host_toolchain.derive_kicad_slice", body)
        # no parallel deriver survives, by definition or by call
        self.assertNotRegex(source, r"^def _export_toolchain\(", )
        self.assertNotIn("_export_toolchain(", source)

    def test_the_reason_keeps_the_verifiers_own_phase(self):
        """m1: bind_inputs reports SNAPSHOT-stage drift; re-stamping it to
        KICAD_VERIFY sends a debugger to the wrong phase."""
        converted = pipeline._thin_reasons({"reasons": [
            {"code": pipeline.REASON_SOURCE_UNBOUND, "stage": pipeline.PHASE_SNAPSHOT,
             "object_id": None, "detail": "the stage drifted"}]})
        self.assertEqual([r.stage for r in converted], [pipeline.PHASE_SNAPSHOT])
        fallback = pipeline._thin_reasons({"reasons": [
            {"code": pipeline.REASON_SOURCE_UNBOUND, "object_id": None,
             "detail": "no stage given"}]})
        self.assertEqual([r.stage for r in fallback],
                         [pipeline.PHASE_KICAD_VERIFY])

    def test_the_receipt_carries_what_commit_will_need(self):
        """M3/M5: the VERIFIED staged manifest and the toolchain digest.

        The seed-time manifest is a different document -- it predates the write
        and includes repair_ops.json -- so publishing it under `staged_manifest`
        gave a reader pre-write digests. And `toolchain_sha256` is the one field
        `same_host_toolchain` compares, so dropping it left COMMIT with nothing
        to cross-check.
        """
        receipt = self._run_with(lambda request: self._thin("PASS"))
        thin = receipt["kicad_verify"]
        self.assertIn("verified_staged_manifest", thin)
        self.assertNotIn("repair_ops.json",
                         [row["path"] for row in
                          thin["verified_staged_manifest"]["files"]])
        self.assertNotEqual(thin["verified_staged_manifest"],
                            receipt["staged_manifest"])
        # the value, not just the key: setting it to None keeps the key present,
        # and a mutation that did exactly that survived the first version
        self.assertIn("toolchain_sha256", thin)
        self.assertIsNotNone(thin["toolchain_sha256"],
                             "COMMIT has no digest to cross-check the toolchain "
                             "against if this is None")

    def test_a_non_pass_verdict_publishes_its_own_cause_not_the_rechecks(self):
        """C2: guard ORDER, which only a driven round can observe.

        The recheck FAILs for every non-PASS outcome, because `verify_stage`
        leaves reports=None unless both exports passed. So checking the recheck
        first made EVERY refusal ROLLBACK(cause=BLOCKED) and left contract line
        373's TOOL_ERROR and UNKNOWN buckets unreachable. The table test cannot
        see this -- it never drives a round.
        """
        thin = self._thin("TOOL_ERROR")
        thin["reports"] = None          # exactly what the real verifier leaves
        thin["reasons"] = [{"code": pipeline.REASON_TOOL_UNAVAILABLE,
                            "stage": pipeline.PHASE_KICAD_VERIFY,
                            "object_id": None,
                            "detail": "the pinned kicad-cli binary is missing"}]
        receipt = self._run_with(
            verify_stage=lambda request: thin,
            freeze=lambda result, root: (str(self.root / "f.json"), "a" * 64),
            recheck=lambda result, root: self._recheck("FAIL", [
                {"code": pipeline.REASON_EXPORT_STALE,
                 "stage": pipeline.PHASE_KICAD_VERIFY, "object_id": None,
                 "detail": "the receipt carries no reports manifest"}]))
        self.assertEqual(receipt["status"], pipeline.STATUS_ROLLBACK)
        self.assertEqual(receipt["cause_status"], pipeline.STATUS_TOOL_ERROR,
                         "the recheck's cause overwrote the verifier's own")
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("kicad-cli binary is missing", detail)

    def test_a_freeze_failure_does_not_hide_the_verifiers_reason(self):
        """C3: the freeze runs before the status branch, so its failure would
        otherwise replace the one thing a reader acts on."""

        def failing_freeze(result, root):
            raise OSError("the report volume is read-only")

        thin = self._thin("BLOCKED")
        thin["reports"] = {"version": 1, "files": [{"path": "x"}]}
        thin["reasons"] = [{"code": pipeline.REASON_SOURCE_UNBOUND,
                            "stage": pipeline.PHASE_SNAPSHOT, "object_id": None,
                            "detail": "the stage drifted from the snapshot"}]
        receipt = self._run_with(verify_stage=lambda request: thin,
                                 freeze=failing_freeze)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("the stage drifted from the snapshot", detail,
                      "the freeze failure replaced the verifier's own reason")
        self.assertIn("read-only", detail,
                      "and the freeze failure itself was swallowed")

    def test_a_refusal_before_kicad_verify_still_has_the_key(self):
        """M4: `_round_receipt` promises a caller can read the keys without
        knowing which phase the round stopped in.

        The first version of this test drove a round that REACHED KICAD_VERIFY,
        where `run_round` assigns the key itself -- so deleting the initialiser
        from `_round_receipt` changed nothing and the mutation survived. The
        property is about a round that refuses BEFORE the phase, which is exactly
        where the key was missing.
        """
        request = self._request()
        request["stage_target"] = "../escapes.kicad_sch"   # refused in PRECHECK
        with mock.patch("tools.akcli_adapter.apply_stage",
                        return_value={
                            "status": "APPLIED_TO_STAGE",
                            "tool": {"tool_applied": True, "exit_code": 0,
                                     "changed": True},
                            "changed": True, "before_source_sha256": "0" * 64,
                            "after_source_sha256": "1" * 64, "reasons": []}), \
                mock.patch.object(pipeline, "compare_delta", return_value={
                    "status": "PASS", "authorized_delta_sha256": "2" * 64,
                    "actual_delta_sha256": "2" * 64, "missing": [],
                    "unexpected": [], "coverage_complete": True,
                    "reasons": []}):
            receipt = pipeline.run_round(request)
        self.assertTrue(receipt["terminal"])
        self.assertNotEqual(receipt["phase"], pipeline.PHASE_KICAD_VERIFY)
        self.assertIn("kicad_verify", receipt,
                      "a round that stopped before KICAD_VERIFY must still "
                      "carry the key, or a reader cannot read the receipt "
                      "without knowing which phase it stopped in")
        self.assertIsNone(receipt["kicad_verify"])

    def test_the_report_root_is_scoped_by_transaction(self):
        """M8: a shared root meant a retried round could never succeed.

        `fresh_export` refuses a pre-existing output directory, so a root shared
        across transactions made every retry fail closed with a misleading
        "stale reports" reason.
        """
        seen = {}
        receipt = self._run_with(verify_stage=lambda request: (
            seen.update(request), self._thin("PASS"))[1])
        root = Path(seen["report_root"])
        self.assertIn(receipt["txn_id"], root.parts,
                      "the report root is not scoped by the transaction id")

    def _request(self, design_root=None, repair_root=None):
        cand = design_root or (self.root / "cand")
        design = cand / "design"
        design.mkdir(parents=True, exist_ok=True)
        # The REAL frozen fixture, for the same reason RunRoundTests uses it: an
        # invented one is not a parseable schematic, so _c2_observe_source fails
        # in SNAPSHOT and the round never reaches the phase under test. The first
        # version of this class used b"(kicad_sch)\n" and every wiring test was
        # silently asserting against a round that had already refused.
        raw = (self.FIXTURES / self.CASE / "fault.kicad_sch").read_bytes()
        (design / "fault.kicad_sch").write_bytes(raw)
        stage = self.root / "stage"
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "fault.kicad_sch").write_bytes(raw)
        oplist = stage / "repair_ops.json"
        oplist.write_text(json.dumps(
            {"protocol_version": 2, "target_format": "kicad", "ops": []}),
            encoding="utf-8")
        ops = json.loads((Path(__file__).resolve().parent / "fixtures"
                          / "repair_pr1" / "native" / "DC-04"
                          / "repair_ops.json").read_text(encoding="utf-8"))["ops"]
        context = pipeline.validate_host_context(host_context(
            design_root=str(cand),
            base_source_sha256=pipeline.hash_bytes(raw),
            target="fault.kicad_sch",
            authority=authority(approvals=[{
                "policy_file_sha256": policy_sha(), "rule_id": "DC-04",
                "run_id": RUN, "candidate_id": CAND, "paths": [str(cand)]}])))
        return {
            "host_context": context,
            "proposal_raw": json.dumps({
                "schema_version": 1, "context_id": CONTEXT,
                "target": "fault.kicad_sch",
                "base_source_sha256": pipeline.hash_bytes(raw),
                "decision": pipeline.DECISION_PATCH,
                "diagnosis": [{"rule_id": "DC-04", "observed": "nothing",
                               "fact_ids": ["F1"],
                               "requirement_level": "MANDATORY",
                               "rationale": "wiring tests"}],
                "oplist": {"protocol_version": 2, "target_format": "kicad",
                           "ops": ops}}, ensure_ascii=False).encode("utf-8"),
            "txn_id": "txn-wiring",
            "stage_root": str(stage),
            "stage_target": "fault.kicad_sch",
            "oplist_path": str(oplist),
            "native_artifact_root": str(self.root / "artifacts"),
        }

    def test_the_request_is_complete_against_the_verifiers_own_field_set(self):
        """Completeness is checked against `_VERIFICATION_REQUEST_FIELDS`.

        Not against a hand-written list, which is how a field could be dropped
        without any test noticing: the list would be the same omission twice.
        The verifier's own field set is the single source of truth.
        """
        from gates import repair_verification as c2
        seen = {}

        def capture(request):
            seen.update(request)
            return self._thin("PASS")

        self._run_with(verify_stage=capture)
        self.assertTrue(seen, "run_round never called verify_stage")
        missing = sorted(c2._VERIFICATION_REQUEST_FIELDS - set(seen))
        self.assertEqual(missing, [],
                         "the verifier request is missing %r" % missing)
        self.assertEqual(sorted(seen), sorted(c2._VERIFICATION_REQUEST_FIELDS))

    def test_report_root_is_a_real_directory_not_merely_a_present_key(self):
        """Completeness of keys is not usefulness of values.

        Mutation V4 set report_root to "" and the completeness test passed,
        because an empty string is still a present key. The verifier freezes its
        reports there, so the value has to be a directory that exists -- and
        asserting that costs one line.
        """
        seen = {}
        self._run_with(verify_stage=lambda request: (
            seen.update(request), self._thin("PASS"))[1])
        root = seen["report_root"]
        self.assertTrue(root, "report_root was passed as an empty value")
        self.assertTrue(Path(root).is_absolute())
        self.assertTrue(Path(root).is_dir(),
                        "report_root does not exist: %s" % root)

    def test_the_snapshot_side_is_what_is_verified_as_before(self):
        """Contract line 292: BEFORE is exported from the SNAPSHOT root.

        Not from the stage. If both sides came from the stage the two exports
        would be of the same bytes and the comparison would be vacuous.
        """
        from gates import repair_verification as c2
        seen = {}
        self._run_with(verify_stage=lambda request: (
            seen.update(request), self._thin("PASS"))[1])
        snapshot_root = Path(seen["snapshot_root"]).resolve()
        stage_root = Path(seen["stage_root"]).resolve()
        self.assertNotEqual(snapshot_root, stage_root)
        # the snapshot holds the BEFORE bytes, and the stage has been written
        snapshot_target = snapshot_root / seen["relative_target"]
        self.assertTrue(snapshot_target.is_file())
        self.assertEqual(
            pipeline.hash_bytes(snapshot_target.read_bytes()),
            seen["before_manifest"]["files"][0]["sha256"])

    def test_the_manifests_passed_describe_the_state_the_verifier_will_read(self):
        """BEFORE is SNAPSHOT's; AFTER is the stage as it is NOW.

        The first version asserted `staged_manifest == receipt["staged_manifest"]`
        -- the manifest SNAPSHOT builds when it SEEDS the stage. That is wrong on
        two counts and the real end-to-end run is what exposed it:

          * timing: the writer has run since, so `source_hash_binding` refuses
            with "stage file does not match its declared manifest";
          * scope: the seed-time manifest includes repair_ops.json, which is the
            writer's input and not part of the design, so the stage's dependency
            key set would differ from the snapshot's and read as an unexpected
            dependency.

        So the verifier gets the post-write DESIGN manifest: the snapshot's paths,
        re-measured, without the op-list.
        """
        from gates import repair_verification as c2
        seen = {}
        receipt = self._run_with(verify_stage=lambda request: (
            seen.update(request), self._thin("PASS"))[1])

        # BEFORE is exactly the snapshot's manifest -- that side never changes.
        self.assertEqual(seen["before_manifest"],
                         receipt["snapshot"]["manifest"])

        staged = seen["staged_manifest"]
        snapshot_paths = sorted(row["path"] for row
                                in seen["before_manifest"]["files"])
        staged_paths = sorted(row["path"] for row in staged["files"])
        self.assertEqual(staged_paths, snapshot_paths,
                         "the stage manifest must cover the snapshot's paths")
        self.assertNotIn("repair_ops.json", staged_paths,
                         "the writer's op-list is not part of the design")

        # and it is a FRESH measurement, not the seed-time manifest restated.
        # The assertNotEqual alone does NOT prove this -- the row sets already
        # differ because of repair_ops.json, and a review mutant that replaced
        # _staged_design_manifest with a pure passthrough still passed. So the
        # function is called directly on a stage whose bytes have changed and its
        # digest is asserted to move.
        self.assertNotEqual(staged, receipt["staged_manifest"])
        self.assertIn("repair_ops.json",
                      [row["path"] for row in receipt["staged_manifest"]["files"]],
                      "the seed-time manifest did include the op-list, so these "
                      "two really are different documents")

        design = self.root / "cand" / "design"
        live = self.root / "stage"
        before = pipeline._staged_design_manifest(
            str(live), receipt["snapshot"]["manifest"], "fault.kicad_sch")
        (live / "fault.kicad_sch").write_bytes(b"(kicad_sch (edited by the writer))\n")
        after = pipeline._staged_design_manifest(
            str(live), receipt["snapshot"]["manifest"], "fault.kicad_sch")
        self.assertNotEqual(
            before["files"][0]["sha256"], after["files"][0]["sha256"],
            "the manifest is not re-measured: the stage's bytes changed and the "
            "digest did not")
        self.assertEqual(after["files"][0]["sha256"],
                         pipeline.hash_bytes((live / "fault.kicad_sch").read_bytes()))
        self.assertEqual(after["files"][0]["size_bytes"],
                         (live / "fault.kicad_sch").stat().st_size)

        # both are the shape the frozen validator accepts
        c2._manifest(seen["before_manifest"])
        c2._manifest(staged)

    # --- helpers ---------------------------------------------------------
    def _thin(self, status):
        from gates import repair_verification as c2
        return {
            "status": status, "scope": "PR1_CANDIDATE_BYTES",
            # the real verifier sets this, and the receipt must carry it: it is
            # the digest `same_host_toolchain` compares at commit time
            "toolchain_sha256": "9" * 64,
            "checks": {name: {"status": "PASS", "reason_codes": [],
                              "artifact_paths": []}
                       for name in ("fresh_export", "source_hash_binding",
                                    "exact_topology_delta", "protected_diff")},
            "coverage": {"before": {"keys": set()}, "after": {"keys": set()}},
            "parser_agreement": {"before": {"status": "PASS"},
                                 "after": {"status": "PASS"}},
            "authorized_delta_sha256": "2" * 64,
            "actual_delta_sha256": "2" * 64,
            "missing_delta": [], "unexpected_delta": [],
            "protected_changes": [], "dependencies_unchanged": True,
            "exports": [{"role": "BEFORE"}, {"role": "AFTER"}],
            "reports": [], "deferred": dict(c2._DEFERRED), "reasons": [],
        }

    def _run_with(self, verify_stage, freeze=None, recheck=None):
        """Drive one round to KICAD_VERIFY with the writer and the delta verdict
        stubbed. Neither is available on this interpreter -- the pinned akcli is
        not importable here -- so without this the round stops at STAGE_APPLY and
        the wiring is never exercised. What is under test is the wiring, not the
        writer or compare_delta, both of which have their own suites.
        """
        request = self._request()
        fake_stage = {
            "status": "APPLIED_TO_STAGE",
            "tool": {"tool_applied": True, "exit_code": 0, "changed": True},
            "changed": True, "before_source_sha256": "0" * 64,
            "after_source_sha256": "1" * 64, "reasons": [],
        }
        fake_verdict = {
            "status": "PASS", "authorized_delta_sha256": "2" * 64,
            "actual_delta_sha256": "2" * 64, "missing": [], "unexpected": [],
            "coverage_complete": True, "reasons": [],
        }
        # Patch the real function, not the module. run_round does
        # `from tools import akcli_adapter` inside the function, which resolves
        # the name as an attribute of the `tools` package -- so faking
        # sys.modules had no effect and the round refused at STAGE_APPLY with
        # "the READ worker could not start", which is the absent pinned
        # toolchain and not the wiring under test.
        with mock.patch("tools.akcli_adapter.apply_stage",
                        return_value=fake_stage), \
                mock.patch.object(pipeline, "compare_delta",
                                  return_value=fake_verdict), \
                mock.patch.object(pipeline, "_c2_verify_stage", verify_stage), \
                mock.patch.object(
                    pipeline, "_c2_write_thin",
                    freeze or (lambda result, root:
                               (str(self.root / "frozen.json"), "f" * 64))), \
                mock.patch.object(
                    pipeline, "_c2_recheck_reports",
                    recheck or (lambda result, root: self._recheck("PASS"))):
            return pipeline.run_round(request)

    def _recheck(self, status, reasons=()):
        return {"status": status, "checked": 2, "reasons": list(reasons)}

    def test_the_result_is_frozen_and_the_reports_re_read(self):
        """Contract line 374 (冻结所有报告) and line 343 (报告重算).

        Both collaborators had ZERO production callers before this change, so
        "the round calls them" is a real property and not a detail.
        """
        frozen, rechecked = [], []
        real_thin = self._thin("PASS")
        real_thin["reports"] = {"version": 1, "files": [{"path": "x"}]}

        def thin(request):
            return real_thin

        def freeze(result, report_root):
            frozen.append((result, report_root))
            return str(Path(report_root) / "thin.json"), "a" * 64

        def recheck(result, report_root):
            rechecked.append((result, report_root))
            return self._recheck("PASS")

        self._run_with(verify_stage=thin, freeze=freeze, recheck=recheck)
        self.assertEqual(len(frozen), 1, "the thin result was never frozen")
        self.assertEqual(len(rechecked), 1, "the reports were never re-read")
        self.assertIs(frozen[0][0], rechecked[0][0],
                      "the re-read must be of the SAME result that was frozen")
        self.assertEqual(frozen[0][1], rechecked[0][1])

    def test_report_drift_refuses_with_the_contracts_cause(self):
        """A FAIL from the re-read is the contract's 报告漂移 case.

        Line 374 puts report drift in ROLLBACK(cause=BLOCKED) with the other
        drift cases, and forbids downgrading the verification to let a commit
        through. A thin PASS with stale reports must NOT stay a PASS.
        """
        real_thin = self._thin("PASS")
        real_thin["reports"] = {"version": 1, "files": [{"path": "x"}]}

        with mock.patch("tools.akcli_adapter.apply_stage",
                        return_value={
                            "status": "APPLIED_TO_STAGE",
                            "tool": {"tool_applied": True, "exit_code": 0,
                                     "changed": True},
                            "changed": True, "before_source_sha256": "0" * 64,
                            "after_source_sha256": "1" * 64, "reasons": []}), \
                mock.patch.object(pipeline, "compare_delta", return_value={
                    "status": "PASS", "authorized_delta_sha256": "2" * 64,
                    "actual_delta_sha256": "2" * 64, "missing": [],
                    "unexpected": [], "coverage_complete": True,
                    "reasons": []}), \
                mock.patch.object(pipeline, "_c2_verify_stage",
                                  return_value=real_thin), \
                mock.patch.object(pipeline, "_c2_write_thin",
                                  return_value=(str(self.root / "f.json"),
                                                "a" * 64)), \
                mock.patch.object(pipeline, "_c2_recheck_reports",
                                  return_value=self._recheck("FAIL", [
                                      {"code": pipeline.REASON_EXPORT_STALE,
                                       "stage": pipeline.PHASE_KICAD_VERIFY,
                                       "object_id": None,
                                       "detail": "the reports no longer match"}])):
            receipt = pipeline.run_round(self._request())

        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["status"], pipeline.STATUS_ROLLBACK)
        self.assertEqual(receipt["cause_status"], pipeline.STATUS_BLOCKED)
        self.assertEqual(receipt["phase"], pipeline.PHASE_KICAD_VERIFY)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("no longer match", detail)
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)

    def test_a_thin_pass_commits_only_through_the_commit_phase(self):
        """Contract line 349, INVERTED when the writer landed.

        Line 349 forbade publishing a thin PASS as a whole-candidate VerifierPort
        PASS. That is still true, and still enforced -- but it is no longer the
        end of the story, because the COMMIT phase now exists and a thin PASS is
        exactly the input it is designed to promote.

        So this asserts the promotion happened, AND that it happened *through*
        COMMIT rather than at KICAD_VERIFY: the phase is COMMIT, the predicate was
        satisfied, the intent and the replace and the verification all really
        happened, and nothing was left pending. The old version asserted the
        absence of a commit; this asserts the whole path, which is the stronger
        claim and the one that would catch a commit claimed without the work.
        """
        receipt = self._run_with(lambda request: self._thin("PASS"))
        self.assertEqual(receipt["status"], pipeline.STATUS_COMMITTED)
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["phase"], pipeline.PHASE_COMMIT)
        self.assertEqual(receipt["pending_phases"], [])
        self.assertEqual(receipt["commit"],
                         {"attempted": True, "replaced": True, "verified": True})
        self.assertTrue(receipt["commit_predicate"]["satisfied"],
                        receipt["commit_predicate"]["reasons"])
        # and the thin verdict is still carried verbatim, not promoted into a
        # candidate-level claim (line 349's actual prohibition)
        self.assertEqual(receipt["kicad_verify"]["status"], "PASS")
        self.assertEqual(receipt["kicad_verify"]["scope"], "PR1_CANDIDATE_BYTES")

    def test_the_deferred_mapping_survives_the_round_untouched(self):
        """Contract line 424: a deferred ERC must never be written as PASS."""
        from gates import repair_verification as c2
        receipt = self._run_with(lambda request: self._thin("PASS"))
        # NOT `== dict(c2._DEFERRED)`: the stub's own literal is
        # dict(c2._DEFERRED), so that comparison is the stub against itself and a
        # hardcoded production value would pass. The loop below is the part that
        # does real work, so it is kept and the tautology dropped.
        self.assertTrue(receipt["kicad_verify"]["deferred"])
        for name, value in receipt["kicad_verify"]["deferred"].items():
            self.assertEqual(value, "NOT_RUN",
                             "deferred %r was rewritten to %r" % (name, value))
            self.assertNotEqual(value, "PASS")

    def test_the_two_exports_are_carried_in_the_receipt(self):
        """Contract line 292: one fresh export per side."""
        receipt = self._run_with(lambda request: self._thin("PASS"))
        roles = [row.get("role") for row in
                 receipt["kicad_verify"]["exports"]]
        self.assertEqual(roles, ["BEFORE", "AFTER"])

    def test_a_non_pass_verdict_refuses_with_the_contract_cause(self):
        """A TOOL_ERROR verdict maps to ROLLBACK(cause=TOOL_ERROR)."""
        from gates import repair_verification as c2
        thin = self._thin("TOOL_ERROR")
        thin["reports"] = {"version": 1, "files": [{"path": "x"}]}
        thin["reasons"] = [{"code": pipeline.REASON_TOOL_UNAVAILABLE,
                            "stage": pipeline.PHASE_KICAD_VERIFY,
                            "object_id": None,
                            "detail": "the export exceeded the frozen timeout"}]
        self.assertEqual(thin["deferred"], dict(c2._DEFERRED))
        receipt = self._run_with(verify_stage=lambda request: thin)
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["status"], pipeline.STATUS_ROLLBACK)
        self.assertEqual(receipt["cause_status"], pipeline.STATUS_TOOL_ERROR)
        self.assertEqual(receipt["phase"], pipeline.PHASE_KICAD_VERIFY)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("frozen timeout", detail)

    def test_a_verifier_that_raises_is_contained_not_propagated(self):
        request = self._request()
        fake_stage = {
            "status": "APPLIED_TO_STAGE",
            "tool": {"tool_applied": True, "exit_code": 0, "changed": True},
            "changed": True, "before_source_sha256": "0" * 64,
            "after_source_sha256": "1" * 64, "reasons": [],
        }
        fake_verdict = {
            "status": "PASS", "authorized_delta_sha256": "2" * 64,
            "actual_delta_sha256": "2" * 64, "missing": [], "unexpected": [],
            "coverage_complete": True, "reasons": [],
        }
        with mock.patch("tools.akcli_adapter.apply_stage",
                        return_value=fake_stage), \
                mock.patch.object(pipeline, "compare_delta",
                                  return_value=fake_verdict), \
                mock.patch.object(pipeline, "_c2_verify_stage",
                                  side_effect=RuntimeError("boom")):
            receipt = pipeline.run_round(request)      # must not raise
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["status"], pipeline.STATUS_TOOL_ERROR)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("boom", detail)


if __name__ == "__main__":
    unittest.main()





class SingleWriterLockTests(unittest.TestCase):
    """Contract 346 / 369 / 376. The mechanism is an INTERPRETATION -- see the
    module comment above `_SingleWriterLock` -- and these are the tests that make
    the interpretation falsifiable rather than merely plausible."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aedl-lock-"))
        self.anchor = self.root / ".repair.lock"

    def tearDown(self):
        shutil.rmtree(str(self.root), ignore_errors=True)

    def test_a_second_holder_is_refused_while_the_first_holds_it(self):
        first = pipeline._SingleWriterLock(self.anchor)
        self.assertTrue(first.acquire(), first.refusal)
        self.addCleanup(first.release)
        second = pipeline._SingleWriterLock(self.anchor)
        self.assertFalse(second.acquire(),
                         "a second writer was let into the same candidate")
        self.assertFalse(second.held)

    def test_a_holder_can_be_taken_again_after_release(self):
        first = pipeline._SingleWriterLock(self.anchor)
        self.assertTrue(first.acquire(), first.refusal)
        first.release()
        self.assertFalse(first.held)
        second = pipeline._SingleWriterLock(self.anchor)
        self.addCleanup(second.release)
        self.assertTrue(second.acquire(), second.refusal)

    def test_the_anchor_is_fixed_content_and_survives_release(self):
        """Contract 376: 内容固定、不因 unlock 删除."""
        lock = pipeline._SingleWriterLock(self.anchor)
        self.assertTrue(lock.acquire(), lock.refusal)
        lock.release()
        self.assertTrue(self.anchor.is_file(), "the anchor was deleted on unlock")
        self.assertEqual(self.anchor.read_bytes(), pipeline.LOCK_ANCHOR_BYTES)

    def test_a_tampered_anchor_is_refused_not_rewritten(self):
        self.anchor.write_bytes(b"someone else's content\n")
        lock = pipeline._SingleWriterLock(self.anchor)
        self.assertFalse(lock.acquire(),
                         "a foreign anchor was accepted as our own")
        self.assertIn("frozen anchor content", lock.refusal)
        self.assertEqual(self.anchor.read_bytes(), b"someone else's content\n",
                         "the foreign anchor was overwritten instead of refused")

    def test_no_primitive_means_a_refusal_not_a_fallback(self):
        """A fallback that cannot exclude another process is not a lock."""
        original = pipeline._byte_lock
        self.addCleanup(setattr, pipeline, "_byte_lock", original)
        pipeline._byte_lock = None
        lock = pipeline._SingleWriterLock(self.anchor)
        self.assertFalse(lock.acquire())
        self.assertIn("no OS byte-range locking primitive", lock.refusal)

    def test_a_missing_lock_path_refuses_rather_than_assuming(self):
        case = RunRoundTests("test_the_request_must_be_a_mapping")
        case.setUp()
        self.addCleanup(case.tearDown)
        request = case._request()
        del request["host_context"]["workspace"]["lock_path"]
        receipt = pipeline.run_round(request)
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("lock path", detail)
        self.assertIn("single writer", detail)


class AtomicReplaceTests(unittest.TestCase):
    """Contract 374: 同一 design 目录写临时文件、flush/fsync、原子 replace."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aedl-atomic-"))
        self.target = self.root / "design.kicad_sch"
        self.target.write_bytes(b"(kicad_sch original)\n")

    def tearDown(self):
        shutil.rmtree(str(self.root), ignore_errors=True)

    def _temps(self):
        return list(self.root.glob(".design.kicad_sch.aedl-tmp-*"))

    def test_it_writes_exactly_the_payload_and_leaves_no_temp(self):
        result = pipeline._atomic_replace_file(self.target, b"new bytes\n")
        self.assertTrue(result["replaced"])
        self.assertEqual(self.target.read_bytes(), b"new bytes\n")
        self.assertEqual(result["sha256"], pipeline.hash_bytes(b"new bytes\n"))
        self.assertEqual(self._temps(), [], "a temp file survived a good write")

    def test_the_temp_lives_in_the_targets_own_directory(self):
        """Cross-directory is not atomic, so this is load-bearing."""
        other = self.root / "elsewhere"
        other.mkdir()
        pipeline._atomic_replace_file(self.target, b"x")
        # the prefix is derived from the target name, so a leftover is
        # recognisable as ours rather than looking like a design file
        self.assertEqual(self._temps(), [])

    def test_a_failure_leaves_the_target_untouched(self):
        payload = b"new bytes\n"
        with mock.patch("os.replace", side_effect=OSError("sharing violation")):
            with self.assertRaises(pipeline.RepairContractError) as caught:
                pipeline._atomic_replace_file(self.target, payload)
        self.assertEqual(self.target.read_bytes(), b"(kicad_sch original)\n",
                         "a failed replace changed the target")
        self.assertEqual(self._temps(), [],
                         "a temp file survived a failed write")
        detail = " ".join(f.detail for f in caught.exception.findings)
        self.assertIn("untouched", detail)

    def test_a_leftover_temp_is_never_clobbered(self):
        """It is evidence of a crashed earlier process, not garbage."""
        leftover = self.root / ".design.kicad_sch.aedl-tmp-crashed"
        leftover.write_bytes(b"evidence of an earlier crash")
        pipeline._atomic_replace_file(self.target, b"new bytes\n")
        self.assertEqual(leftover.read_bytes(), b"evidence of an earlier crash")


class RecoveryBranchTests(unittest.TestCase):
    """Contract 384 / 385 / 386, one test per branch, on the primitive."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aedl-recover-"))
        self.journal = self.root / "journal.jsonl"
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        self.snapshot = self.root / "snapshot"
        self.snapshot.mkdir()
        self.target = self.design / "design.kicad_sch"
        self.before = b"(kicad_sch before)\n"
        self.after = b"(kicad_sch after)\n"
        (self.snapshot / self.target.name).write_bytes(self.before)
        self.target.write_bytes(self.before)

    def tearDown(self):
        shutil.rmtree(str(self.root), ignore_errors=True)

    def _intent(self, **overrides):
        row = {"kind": pipeline.JOURNAL_COMMIT_INTENT, "txn_id": "t1",
               "run_id": "r", "candidate_id": "c", "patch_id": "p",
               "stage_sha256": pipeline.hash_bytes(self.after),
               "before_sha256": pipeline.hash_bytes(self.before),
               "after_sha256": pipeline.hash_bytes(self.after),
               "target": str(self.target), "status": None,
               "snapshot_root": str(self.snapshot),
               "snapshot_sha256": pipeline.hash_bytes(self.before),
               "design_root": str(self.design)}
        row.update(overrides)
        return row

    def _write(self, row):
        self.journal.write_bytes(
            (json.dumps(row, ensure_ascii=False, sort_keys=True)
             + "\n").encode("utf-8"))

    def test_rule_385_really_restores_the_snapshot_bytes(self):
        """live == recorded after, no terminal record -> restore from snapshot."""
        self.target.write_bytes(self.after)
        self._write(self._intent())
        notes, blocking = pipeline._resolve_one_intent(self.journal,
                                                       self._intent())
        self.assertIsNone(blocking, [n.detail for n in notes])
        self.assertEqual(self.target.read_bytes(), self.before,
                         "rule 385 did not restore the original bytes")
        records, corrupt = pipeline._read_journal(self.journal)
        self.assertEqual(corrupt, [])
        self.assertEqual(records[-1]["kind"], pipeline.JOURNAL_TERMINAL,
                         "the resolved transaction got no terminal record")

    def test_rule_384_does_not_rewrite_an_unchanged_file(self):
        """live == recorded before -> confirm, and write nothing.

        Contract 384: 「无需为了"回滚"重写未变文件」. Rewriting would touch a file
        that is already correct, which is a needless chance to lose it.
        """
        stamp = self.target.stat().st_mtime_ns
        self._write(self._intent())
        notes, blocking = pipeline._resolve_one_intent(self.journal,
                                                       self._intent())
        self.assertIsNone(blocking, [n.detail for n in notes])
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertEqual(self.target.stat().st_mtime_ns, stamp,
                         "an unchanged design file was rewritten")
        self.assertIn("no rewrite was needed", notes[0].detail)

    def test_rule_386_blocks_and_leaves_unrecognised_bytes_alone(self):
        """live is neither before nor after -> quarantine, and STOP."""
        stranger = b"\x00 a human wrote this\n"
        self.target.write_bytes(stranger)
        self._write(self._intent())
        notes, blocking = pipeline._resolve_one_intent(self.journal,
                                                       self._intent())
        self.assertEqual(notes, [], "a quarantined transaction reported notes")
        self.assertIsNotNone(blocking,
                             "the quarantine did not block -- this is the "
                             "fail-open this test exists to prevent")
        self.assertIn("QUARANTINE", blocking.detail)
        self.assertEqual(self.target.read_bytes(), stranger,
                         "unrecognised bytes were overwritten")

    def test_a_missing_target_takes_rule_384_not_a_crash(self):
        """An absent target is 384's ordinary case; it must not raise."""
        self.target.unlink()
        self._write(self._intent())
        notes, blocking = pipeline._resolve_one_intent(self.journal,
                                                       self._intent())
        self.assertIsNone(blocking, [n.detail for n in notes])
        self.assertIn("never took", notes[0].detail)

    def test_a_snapshot_that_does_not_match_the_record_is_refused(self):
        """Restoring bytes nobody verified would be worse than not restoring."""
        self.target.write_bytes(self.after)
        (self.snapshot / self.target.name).write_bytes(b"tampered snapshot\n")
        self._write(self._intent())
        notes, blocking = pipeline._resolve_one_intent(self.journal,
                                                       self._intent())
        self.assertIsNotNone(blocking, "a mismatched snapshot was restored")
        self.assertIn("bytes nobody verified", blocking.detail)
        self.assertEqual(self.target.read_bytes(), self.after,
                         "the candidate was modified despite the mismatch")

    def test_a_gone_snapshot_blocks_instead_of_guessing(self):
        self.target.write_bytes(self.after)
        shutil.rmtree(str(self.snapshot))
        self._write(self._intent())
        notes, blocking = pipeline._resolve_one_intent(self.journal,
                                                       self._intent())
        self.assertIsNotNone(blocking)
        self.assertIn("cannot be", blocking.detail + " ")
        self.assertEqual(self.target.read_bytes(), self.after,
                         "bytes were written when the original was unavailable")


class Contract378Tests(unittest.TestCase):
    """Contract 378: 再检查每个路径分量的 symlink/reparse point、文件 link count
    /别名与实际身份；不能仅复用 workspace root 的宽范围检查."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="aedl-378-"))
        self.design = self.root / "cand" / "design"
        self.design.mkdir(parents=True)
        self.target = self.design / "fault.kicad_sch"
        self.target.write_bytes(b"(kicad_sch)\n")

    def tearDown(self):
        shutil.rmtree(str(self.root), ignore_errors=True)

    def test_an_ordinary_single_link_design_file_passes(self):
        self.assertEqual(
            pipeline._design_paths_are_own_and_unique(self.design,
                                                      "fault.kicad_sch"), [])

    def test_a_hard_link_alias_is_refused(self):
        """More than one name for the same bytes is an alias (别名)."""
        alias = self.root / "elsewhere.kicad_sch"
        try:
            os.link(str(self.target), str(alias))
        except (OSError, NotImplementedError):
            self.skipTest("this filesystem does not support hard links")
        reasons = pipeline._design_paths_are_own_and_unique(
            self.design, "fault.kicad_sch")
        self.assertTrue(reasons, "a two-name design file was accepted")
        self.assertIn("hard links", " ".join(r.detail for r in reasons))

    def test_a_missing_design_root_is_refused(self):
        reasons = pipeline._design_paths_are_own_and_unique(
            self.root / "absent", "fault.kicad_sch")
        self.assertTrue(reasons)
        self.assertIn("not a directory", " ".join(r.detail for r in reasons))
class CommitReceiptTests(unittest.TestCase):
    """Drives a real round to a thin PASS and inspects what it publishes.

    COMPOSITION, not inheritance. The first version subclassed
    VerifyStageWiringTests to reuse its fixture, which re-ran all 19 of the
    parent's tests inside this class: 27 tests where 8 were mine, the wiring
    runtime doubled, and any parent failure would be reported twice.

    Composition keeps what actually mattered -- the parent's real thin-PASS
    fixture, its stubbed collaborators and its request builder, rather than a
    hand-rolled second copy that drifts -- without re-executing its suite.
    `__getattr__` forwards, so the test bodies are unchanged.
    """

    def setUp(self):
        # Delegated by name, which is a coupling worth REMOVING rather than
        # re-pointing: the previous name was `test_a_thin_pass_leaves_the_round
        # _unpromoted`, and I renamed that test when I inverted it, so this broke.
        # A name that must not be renamed is a hidden dependency; the wrapper's
        # contract (a thin-PASS round driven through the stubbed collaborators) is
        # what is actually wanted, so it is pinned explicitly instead.
        self._wiring = VerifyStageWiringTests(
            "test_a_thin_pass_commits_only_through_the_commit_phase")
        self._wiring.setUp()
        self.assertTrue(
            hasattr(self._wiring, "_run_with"),
            "the delegate must provide the thin-PASS driver this suite builds on")

    def tearDown(self):
        self._wiring.tearDown()

    def __getattr__(self, name):
        # Only reached for attributes this class does not define, so there is no
        # recursion risk with the unittest internals. The `_wiring` guard matters:
        # unittest touches attributes before setUp runs, and indexing
        # self.__dict__["_wiring"] then raised KeyError. Dunder and private
        # names are never forwarded -- unittest's own machinery must see its
        # real values.
        delegate = self.__dict__.get("_wiring")
        if delegate is None or (name.startswith("__") and name.endswith("__")):
            raise AttributeError(name)
        return getattr(delegate, name)

    def _pass_receipt(self):
        return self._run_with(verify_stage=lambda request: self._thin("PASS"))

    def test_commit_keeps_the_contracts_closed_shape(self):
        """Contract 404: commit:{attempted, replaced, verified}. Three keys.

        The first version added a fourth (`predicate`) and this repository
        enforces closed shapes everywhere, so every consumer of contract 404
        would have broken. The verdict lives in its own receipt key instead.
        """
        receipt = self._pass_receipt()
        self.assertEqual(set(receipt["commit"]),
                         {"attempted", "replaced", "verified"})
        for key in ("attempted", "replaced", "verified"):
            self.assertIsInstance(receipt["commit"][key], bool)

    def test_a_thin_pass_now_commits_and_says_what_it_did(self):
        """INVERTED, deliberately, when the writer landed.

        This asserted `status is None` and `commit.attempted is False` -- true
        while the writer was absent, and the whole point of PR #101, which
        landed the predicate without the writer. It is not deleted and not
        relaxed: it now asserts the STRONGER property, that the round reaches
        COMMITTED and reports each step truthfully.

        `commit` is contract 404's closed three-key shape, so it is the only
        place the round can say "attempted, replaced, verified" -- and all three
        must be true for a real commit, because line 374 requires the verified
        bytes, the final check and the terminal journal before COMMITTED.
        """
        receipt = self._pass_receipt()
        self.assertEqual(receipt["status"], pipeline.STATUS_COMMITTED)
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["phase"], pipeline.PHASE_COMMIT)
        self.assertEqual(receipt["pending_phases"], [])
        self.assertEqual(receipt["commit"],
                         {"attempted": True, "replaced": True, "verified": True})
        self.assertTrue(receipt["commit_predicate"]["satisfied"],
                        receipt["commit_predicate"]["reasons"])
        # and the public projection follows the contract
        self.assertEqual(receipt["feedback"]["proposal_outcome"],
                         pipeline.OUTCOME_APPLIED)

    def test_a_committed_round_wrote_a_durable_intent_and_terminal_record(self):
        """Contract 374's order, and 390's persistence requirement.

        The order is the whole point: a crash between the two records leaves an
        INTENT with no TERMINAL, which is exactly the state contract 387 says
        must be treated as "did not succeed" and which `_recover_incomplete`
        resolves on the next round.
        """
        receipt = self._pass_receipt()
        journal = pipeline._journal_file(self._request()["host_context"])
        records, corrupt = pipeline._read_journal(journal)
        self.assertEqual(corrupt, [])
        kinds = [row["kind"] for row in records
                 if row["txn_id"] == receipt["txn_id"]]
        self.assertEqual(kinds, [pipeline.JOURNAL_COMMIT_INTENT,
                                 pipeline.JOURNAL_TERMINAL],
                         "the INTENT must be written BEFORE the terminal record")
        terminal = records[-1]
        self.assertEqual(terminal["status"], pipeline.STATUS_COMMITTED)
        # the INTENT carries the verified staged hash, per line 374
        intent = records[0]
        self.assertEqual(len(intent["stage_sha256"]), 64)
        self.assertEqual(intent["target_sha256"] if "target_sha256" in intent
                         else intent["after_sha256"], terminal["after_sha256"])

    def test_an_unresolved_intent_is_resolved_not_refused_forever(self):
        """The recovery replaces PR #101's blanket refusal.

        PR #101 refused whenever an unresolved INTENT existed, because the
        restore was not implemented. It is now, so the round must RESOLVE the
        earlier transaction and carry on -- and must say so on the receipt, so a
        reader sees a transaction was recovered rather than silently overwritten.
        """
        import json
        from tests.test_repair_pipeline import RunRoundTests
        first = self._pass_receipt()
        self.assertEqual(first["status"], pipeline.STATUS_COMMITTED)

        journal = pipeline._journal_file(self._request()["host_context"])
        # rewrite the terminal away, leaving an INTENT with no TERMINAL
        lines = [line for line in journal.read_text(encoding="utf-8").splitlines()
                 if json.loads(line)["kind"] != pipeline.JOURNAL_TERMINAL]
        journal.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))

        # A new round, with a DIFFERENT txn id. `_recover_incomplete` skips an
        # INTENT whose txn_id equals the current round's -- correctly, since a
        # round cannot recover its own interrupted self -- so reusing the id made
        # this test find nothing and assert on an empty `recovered`.
        request = self._request()
        request["txn_id"] = request["txn_id"] + "-second"
        with mock.patch("tools.akcli_adapter.apply_stage", return_value={
                "status": "APPLIED_TO_STAGE",
                "tool": {"tool_applied": True, "exit_code": 0, "changed": True},
                "changed": True, "before_source_sha256": "0" * 64,
                "after_source_sha256": "1" * 64, "reasons": []}), \
                mock.patch.object(pipeline, "compare_delta", return_value={
                    "status": "PASS", "authorized_delta_sha256": "2" * 64,
                    "actual_delta_sha256": "2" * 64, "missing": [],
                    "unexpected": [], "coverage_complete": True,
                    "reasons": []}), \
                mock.patch.object(pipeline, "_c2_verify_stage",
                                  side_effect=lambda r: self._thin("PASS")), \
                mock.patch.object(pipeline, "_c2_write_thin",
                                  return_value=("frozen.json", "a" * 64)), \
                mock.patch.object(pipeline, "_c2_recheck_reports",
                                  return_value={"status": "PASS", "checked": 2,
                                                "reasons": []}):
            second = pipeline.run_round(request)
        self.assertTrue(second["recovered"],
                        "the earlier transaction was not reported as recovered")
        self.assertNotEqual(second["status"], pipeline.STATUS_ROLLBACK,
                            "a resolvable INTENT must not refuse the round")

    def test_the_receipt_declares_what_is_still_missing(self):
        """INVERTED from PR #101's writer-absence test, now that the writer exists.

        The point survives the inversion, and it is the point that matters: a
        receipt must say what it cannot do, as a FIELD, because a refusal reason
        describing behaviour the process does not have is worse than no reason.
        PR #101 caught exactly that -- its text claimed "the next round will
        refuse at PRECHECK" while nothing read the journal.

        So the remaining gaps are still declared structurally, and the lock --
        which PR #101 could not satisfy at all -- is now satisfied and therefore
        absent from the unsatisfied list.
        """
        receipt = self._pass_receipt()
        predicate = receipt["commit_predicate"]
        self.assertTrue(predicate["writer_available"])
        for missing in ("no_change_idempotent_replay", "final_candidate_hash"):
            self.assertIn(missing, predicate["not_implemented"],
                          "%s is not declared missing" % missing)
        self.assertNotIn("single_writer_lock", predicate["not_implemented"],
                         "the lock is implemented now")
        self.assertNotIn("single_writer_lock_held",
                         predicate["unsatisfied_conjuncts"])

    def test_an_unsatisfied_conjunct_is_named_when_one_fails(self):
        """INVERTED: on the healthy path nothing is unsatisfied, so this forces a
        failure to check the naming still works.

        PR #101's version asserted the lock conjunct was unsatisfied, which was
        true then and false now. Asserting only the healthy case would let the
        naming rot silently, so the conjunct is broken deliberately -- through
        the round's own `_commit_predicate` seam -- and the reason must still say
        WHICH conjunct failed, because "bindings_equal" alone tells a reader
        nothing actionable.
        """
        healthy = self._pass_receipt()
        self.assertEqual(healthy["commit_predicate"]["unsatisfied_conjuncts"], [])

        with mock.patch.object(pipeline, "_commit_predicate",
                               return_value=(False, [pipeline._finding(
                                   pipeline.REASON_INPUT_DRIFT,
                                   "the commit predicate is not satisfied: "
                                   "recomputed_hashes_match",
                                   stage=pipeline.PHASE_COMMIT)],
                                   ["recomputed_hashes_match"])):
            receipt = self._pass_receipt()
        joined = " ".join(receipt["commit_predicate"]["reasons"])
        self.assertIn("recomputed_hashes_match", joined)
        self.assertEqual(receipt["commit_predicate"]["unsatisfied_conjuncts"],
                         ["recomputed_hashes_match"])
        self.assertEqual(receipt["status"], pipeline.STATUS_ROLLBACK)

    def test_the_conjuncts_that_hold_are_named_as_holding(self):
        """The other direction, and the one a green suite let through.

        Naming only the FAILURES means `live_equals_snapshot = True` hard-coded
        would satisfy every test above -- the round refuses for the lock either
        way. So the healthy path is asserted to satisfy 344 (the live design
        really was compared with the snapshot) and 343 (the stage bytes were
        really re-measured), which is what makes "always True" a detectable
        mutation rather than an invisible one.
        """
        receipt = self._pass_receipt()
        unsatisfied = receipt["commit_predicate"]["unsatisfied_conjuncts"]
        for satisfied in ("live_design_still_equals_snapshot",
                          "recomputed_hashes_match",
                          "thin_pass_invariants",
                          "thin_scope_is_candidate_bytes",
                          "stage_applied_to_stage",
                          "route_and_effect_checks",
                          "single_writer_lock_held"):
            self.assertNotIn(satisfied, unsatisfied,
                             "%s should hold on the healthy path" % satisfied)
        self.assertTrue(receipt["commit_predicate"]["satisfied"],
                        receipt["commit_predicate"]["reasons"])

    def test_rollback_is_not_verified_without_actually_comparing(self):
        """C4. Contract 384: VERIFIED is earned by the byte/manifest compare."""
        receipt = self._pass_receipt()
        rollback = receipt["rollback"]
        self.assertIn(rollback["status"], ("VERIFIED", "UNKNOWN", "NOT_NEEDED"))
        # VERIFIED may only be published alongside a real comparison, which is
        # exactly what byte_equal is for.
        if rollback["status"] == "VERIFIED":
            self.assertIs(rollback["byte_equal"], True)
            self.assertFalse(rollback["attempted"],
                             "nothing was rolled back, so VERIFIED must be a "
                             "confirmation rather than a write")
        else:
            self.assertIsNone(rollback["byte_equal"],
                              "byte_equal=True without a comparison is the "
                              "fabricated field this test exists to prevent")

    def test_an_uncomparable_live_design_is_unknown_never_verified(self):
        """Force conjunct 344 false by making the live design unmeasurable.

        `_staged_design_manifest` is not what is called here -- the round calls
        `build_file_manifest(design_root, stage_target)` directly. Deleting the
        design root makes that raise, which is the honest way to reach the
        failure without contriving a manifest mismatch.
        """
        # Baseline first: prove the round DOES reach COMMIT on the happy path,
        # so a pass/fail below cannot come from an earlier refusal.
        healthy = self._pass_receipt()
        self.assertIsNotNone(healthy["commit_predicate"],
                             "the round did not reach the phase under test")

        seen_roots = []

        def explode(root, target):
            """Fail ONLY the COMMIT-phase measurement.

            Measured, not guessed: a thin-PASS round calls build_file_manifest
            three times, with roots ending `/.repair/snapshot`, `/stage` and
            `/cand/design`. The last is contract 344's live-design comparison.
            Raising for ALL of them stopped the round at SNAPSHOT, so the test
            measured a refusal two phases early and `NOT_NEEDED != UNKNOWN`
            passed while exercising nothing.
            """
            seen_roots.append(str(root))
            if str(root).rstrip("\\/").endswith("cand\\design"):
                raise OSError("the design root is on a disconnected volume")
            return real_build(root, target)

        real_build = pipeline.build_file_manifest
        with mock.patch.object(pipeline, "build_file_manifest", explode):
            receipt = self._pass_receipt()

        self.assertGreaterEqual(
            len(seen_roots), 3,
            "the round made fewer manifest calls than measured, so the targeted "
            "failure may not have been reached: %r" % (seen_roots,))
        self.assertIsNotNone(receipt["commit_predicate"],
                             "the round stopped before COMMIT, so this test is "
                             "measuring the wrong refusal")
        self.assertEqual(receipt["rollback"]["status"], "UNKNOWN")
        self.assertIsNone(receipt["rollback"]["byte_equal"],
                          "byte_equal was set without any comparison")
        self.assertIn("live_design_still_equals_snapshot",
                      receipt["commit_predicate"]["unsatisfied_conjuncts"])
        self.assertIn("could not be re-measured",
                      " ".join(receipt["commit_predicate"]["reasons"]))
        # attempted TRUE, replaced FALSE: the round entered the phase, evaluated
        # the predicate and refused BEFORE writing the intent. That distinction
        # is exactly why contract 404 gives `commit` three keys and not one.
        self.assertEqual(receipt["commit"],
                         {"attempted": True, "replaced": False, "verified": False})
        self.assertEqual(receipt["status"], pipeline.STATUS_ROLLBACK)

    def test_the_round_never_raises_on_a_thin_pass(self):
        """C1/C6/C7: a NameError, a missing import and a bad keyword argument
        all escaped `run_round` in the first version of this phase.

        `run_round` refuses by RETURNING a receipt; an exception escaping it is
        a defect in our own wiring being reported as a crash rather than as a
        refusal. The repository already has a test against that pattern for
        `bind_policy`; this is the same guard for the COMMIT path.
        """
        for verdict in ("PASS", "FAIL", "BLOCKED", "TOOL_ERROR", "UNKNOWN"):
            receipt = self._run_with(
                verify_stage=lambda request, v=verdict: self._thin(v))
            self.assertIsInstance(receipt.get("phase"), str,
                                  "verdict %s produced no phase" % verdict)
            self.assertIn("status", receipt)
            self.assertIn("commit", receipt)
            self.assertIn("rollback", receipt)
            self.assertIn("commit_predicate", receipt)

    def test_a_live_design_that_differs_from_the_snapshot_fails_the_conjunct(self):
        """Contract 344, with a genuine MISMATCH rather than an exception.

        The exception path is covered elsewhere. This is the case the conjunct
        actually exists for: the manifest comparison completes and the two
        documents disagree -- a human or another process edited the candidate
        between SNAPSHOT and COMMIT.

        Without this, `live_equals_snapshot = True` hard-coded survives,
        because the only other test asserts the conjunct is NOT in the
        unsatisfied list, which holds whether the comparison is real or faked.
        """
        real_build = pipeline.build_file_manifest
        from tests.test_repair_pipeline import RunRoundTests

        def tamper(root, target):
            manifest = real_build(root, target)
            if str(root).rstrip("\\/").endswith("cand\\design"):
                # a valid manifest that simply does not describe what the
                # snapshot recorded
                rows = [dict(row) for row in manifest["files"]]
                for row in rows:
                    if row["path"] == RunRoundTests.STAGE_TARGET:
                        row["sha256"] = "e" * 64
                return {"version": manifest["version"], "files": rows}
            return manifest

        with mock.patch.object(pipeline, "build_file_manifest", tamper):
            receipt = self._pass_receipt()

        self.assertIsNotNone(receipt["commit_predicate"],
                             "the round stopped before COMMIT")
        self.assertIn("live_design_still_equals_snapshot",
                      receipt["commit_predicate"]["unsatisfied_conjuncts"])
        self.assertEqual(receipt["rollback"]["status"], "UNKNOWN",
                         "a mismatched live design cannot be VERIFIED")
        self.assertIsNone(receipt["rollback"]["byte_equal"])

    def test_stage_bytes_that_moved_after_the_verifier_fail_the_conjunct(self):
        """Contract 343: after the verifier returned, recompute the stage hashes.

        The lever is real rather than contrived: the verifier request carries
        `stage_root`, so the stub can modify the stage after the writer ran and
        after the verifier read it. That is exactly the drift 343 guards
        against, and it is why the stage is re-measured at COMMIT instead of the
        receipt's own `after_source_sha256` being trusted.
        """
        from tests.test_repair_pipeline import RunRoundTests
        stage = self.root / "stage" / RunRoundTests.STAGE_TARGET

        def verifier(request):
            # touch the stage, as a concurrent or misbehaving writer would
            stage.write_bytes(stage.read_bytes() + b"\n; touched after verify\n")
            return self._thin("PASS")

        receipt = self._run_with(verify_stage=verifier)

        self.assertIsNotNone(receipt["commit_predicate"],
                             "the round stopped before COMMIT")
        self.assertIn("recomputed_hashes_match",
                      receipt["commit_predicate"]["unsatisfied_conjuncts"],
                      "a stage that moved after the verifier was accepted")
        # A predicate failure refuses BEFORE the intent, so nothing was written.
        self.assertEqual(receipt["commit"],
                         {"attempted": True, "replaced": False, "verified": False})
        self.assertEqual(receipt["status"], pipeline.STATUS_ROLLBACK)

    def test_a_refusal_before_commit_reports_nothing_attempted(self):
        """Contract 388: a failure before any write is BLOCKED, not a rollback."""
        request = self._request()
        request["stage_target"] = "../escapes.kicad_sch"
        with mock.patch("tools.akcli_adapter.apply_stage", return_value={
                "status": "APPLIED_TO_STAGE",
                "tool": {"tool_applied": True, "exit_code": 0, "changed": True},
                "changed": True, "before_source_sha256": "0" * 64,
                "after_source_sha256": "1" * 64, "reasons": []}), \
                mock.patch.object(pipeline, "compare_delta", return_value={
                    "status": "PASS", "authorized_delta_sha256": "2" * 64,
                    "actual_delta_sha256": "2" * 64, "missing": [],
                    "unexpected": [], "coverage_complete": True, "reasons": []}):
            receipt = pipeline.run_round(request)
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["commit"],
                         {"attempted": False, "replaced": False, "verified": False})
        self.assertEqual(receipt["rollback"]["status"], "NOT_NEEDED")
        self.assertIsNone(receipt["rollback"]["byte_equal"])
        self.assertIsNone(receipt["commit_predicate"],
                          "the predicate was never evaluated on this path")





class CommitWriterFailureTests(CommitReceiptTests):
    """Fault injection at the round level: a commit that FAILS must not claim to
    have succeeded.

    Three mutations -- `replaced` reported true without replacing, the
    post-replace verification skipped, and the predicate bypassed -- cannot be
    observed from any primitive, because each is a statement the ROUND makes about
    itself. So they are tested here, by breaking the thing and reading the
    receipt.
    """

    def test_a_failed_replace_is_not_reported_as_replaced(self):
        """X8. Contract 374 reports three booleans; they must reflect what
        HAPPENED, not what was intended."""
        real = pipeline._atomic_replace_file

        def explode(target, payload):
            raise pipeline.RepairContractError([pipeline._finding(
                pipeline.REASON_TOOL_UNAVAILABLE,
                "the atomic replace failed (injected)", stage=pipeline.PHASE_COMMIT)])

        with mock.patch.object(pipeline, "_atomic_replace_file", explode):
            receipt = self._pass_receipt()
        self.assertIsNotNone(receipt["commit_predicate"],
                             "the round stopped before COMMIT")
        self.assertFalse(receipt["commit"]["replaced"],
                         "a replace that never happened was reported as done")
        self.assertFalse(receipt["commit"]["verified"])
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)
        # and the intent IS durable, so the next round can classify the bytes
        journal = pipeline._journal_file(self._request()["host_context"])
        records, corrupt = pipeline._read_journal(journal)
        self.assertEqual(corrupt, [])
        self.assertEqual([r["kind"] for r in records
                          if r["txn_id"] == receipt["txn_id"]],
                         [pipeline.JOURNAL_COMMIT_INTENT],
                         "a failed replace left no intent, so recovery could "
                         "not classify the candidate")

    def test_a_primitive_that_reports_no_replace_is_not_claimed_as_one(self):
        """X8. The round must read what the primitive REPORTED.

        The first version hard-coded `replaced = True`, which was unreachable only
        because the primitive had a single exit path.

        Note what is NOT asserted: that the round refuses. It does not, and it
        should not -- `verified` is the real gate, because a commit is proven by
        the design on disk equalling the verified staged bytes, whichever
        primitive happened to put them there. `replaced` is provenance, not
        proof. The receipt is therefore expected to say `replaced: False` AND
        `verified: True`, and that combination is coherent rather than a
        contradiction -- asserting a refusal here would be asserting that the
        pipeline cares about HOW the bytes arrived rather than WHETHER they are
        right, which is backwards.
        """
        with mock.patch.object(
                pipeline, "_atomic_replace_file",
                return_value={"replaced": False, "sha256": "a" * 64}):
            receipt = self._pass_receipt()
        self.assertIs(receipt["commit"]["replaced"], False,
                      "the round claimed a replace the primitive disowned")
        self.assertIs(receipt["commit"]["verified"], True,
                      "the live bytes really do equal the staged bytes here, so "
                      "verified is true regardless of who wrote them")
        self.assertEqual(receipt["status"], pipeline.STATUS_COMMITTED)

    def test_bytes_that_drift_between_replace_and_verify_are_caught(self):
        """X9. 逐字节和 hash 核验最终 design.

        The corruption is injected AFTER the atomic replace, which is the only
        window where the design on disk and the bytes that were verified can
        differ. A round that skipped the re-read would report COMMITTED over
        bytes it never checked.
        """
        real = pipeline._atomic_replace_file

        def replace_then_corrupt(target, payload):
            result = real(target, payload)
            Path(target).write_bytes(b"corrupted after the replace\n")
            return result

        with mock.patch.object(pipeline, "_atomic_replace_file",
                               replace_then_corrupt):
            receipt = self._pass_receipt()
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED,
                            "COMMITTED reported over bytes nobody verified")
        self.assertTrue(receipt["terminal"])
        self.assertFalse(receipt["commit"]["verified"])
        detail = " ".join(receipt["commit_predicate"]["reasons"]
                          + [getattr(r, "detail", "")
                             for r in receipt["reasons"]])
        self.assertTrue("does not match the verified staged bytes" in detail
                        or "NOT" in detail, detail)

    def test_a_broken_conjunct_refuses_the_commit(self):
        """X14. Line 349: 这是合取 -- no partial credit, no threshold.

        The lock is the conjunct that PR #101 could not satisfy, so it is the one
        removed here: with it unsatisfiable the round must refuse, write no
        intent, and leave the candidate alone.
        """
        real = pipeline._commit_predicate

        def without_the_lock(*args, **kwargs):
            kwargs["lock_held"] = False
            return real(*args, **kwargs)

        with mock.patch.object(pipeline, "_commit_predicate", without_the_lock):
            receipt = self._pass_receipt()
        self.assertEqual(receipt["status"], pipeline.STATUS_ROLLBACK)
        self.assertEqual(receipt["cause_status"], pipeline.STATUS_BLOCKED)
        self.assertIn("single_writer_lock_held",
                      receipt["commit_predicate"]["unsatisfied_conjuncts"])
        self.assertFalse(receipt["commit"]["replaced"])
        journal = pipeline._journal_file(self._request()["host_context"])
        self.assertFalse(journal.is_file() and journal.read_text(
            encoding="utf-8").strip(),
            "a refused commit still wrote a durable intent")


class RoundLevelLockAndIdentityTests(CommitReceiptTests):
    """Three properties about the ROUND, which no primitive test can see.

    X1  a round that finds the lock held by someone else must refuse
    X2  a round must not leave the lock held, or the next round in the same
        process is blocked by its own predecessor
    X13 contract 378's link count must actually stop a commit
    """

    def test_a_round_refuses_when_another_writer_holds_the_lock(self):
        """X1. The exclusion is only real if the ROUND obeys it."""
        request = self._request()
        held = pipeline._SingleWriterLock(
            request["host_context"]["workspace"]["lock_path"])
        self.assertTrue(held.acquire(), held.refusal)
        self.addCleanup(held.release)
        receipt = pipeline.run_round(request)
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        detail = " ".join(getattr(r, "detail", "") for r in receipt["reasons"])
        self.assertIn("another writer", detail)
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)

    def test_a_completed_round_does_not_leave_the_lock_held(self):
        """X2. Two rounds over ONE candidate, in one process.

        A leaked lock would make the second round refuse -- and the failure would
        look like a conflict with a phantom writer, which is the kind of report
        that costs an afternoon.

        ONE request for both. The first version called `_pass_receipt()` and then
        `_run_with(...)`, and each builds its own request from a fresh temp root,
        so the two rounds took DIFFERENT lock paths and the leak could not block
        anything -- which is why X2 survived twice.
        """
        request = self._request()
        with mock.patch("tools.akcli_adapter.apply_stage", return_value={
                "status": "APPLIED_TO_STAGE",
                "tool": {"tool_applied": True, "exit_code": 0, "changed": True},
                "changed": True, "before_source_sha256": "0" * 64,
                "after_source_sha256": "1" * 64, "reasons": []}), \
                mock.patch.object(pipeline, "compare_delta", return_value={
                    "status": "PASS", "authorized_delta_sha256": "2" * 64,
                    "actual_delta_sha256": "2" * 64, "missing": [],
                    "unexpected": [], "coverage_complete": True,
                    "reasons": []}), \
                mock.patch.object(pipeline, "_c2_verify_stage",
                                  side_effect=lambda r: self._thin("PASS")), \
                mock.patch.object(pipeline, "_c2_write_thin",
                                  return_value=("frozen.json", "a" * 64)), \
                mock.patch.object(pipeline, "_c2_recheck_reports",
                                  return_value={"status": "PASS", "checked": 2,
                                                "reasons": []}):
            first = pipeline.run_round(request)
            self.assertEqual(first["status"], pipeline.STATUS_COMMITTED)
            second = pipeline.run_round(request)
        self.assertEqual(
            second["status"], pipeline.STATUS_COMMITTED,
            "the second round was blocked by its own predecessor: %s"
            % " ".join(getattr(r, "detail", "") for r in second["reasons"]))
        self.assertEqual(
            second["status"], pipeline.STATUS_COMMITTED,
            "the second round was blocked: %s"
            % " ".join(getattr(r, "detail", "") for r in second["reasons"]))

    def test_a_hard_linked_design_file_stops_the_commit(self):
        """X13. Contract 378: 文件 link count/别名与实际身份.

        Two names for one file's bytes is an alias, and writing through it means
        writing something the round did not measure. The design file is hard
        linked and the round must refuse -- at COMMIT, having written no intent.
        """
        import os as _os
        from tests.test_repair_pipeline import RunRoundTests
        design = self.root / "cand" / "design" / RunRoundTests.STAGE_TARGET
        design.parent.mkdir(parents=True, exist_ok=True)
        if not design.exists():
            design.write_bytes(b"(kicad_sch to be aliased)\n")
        alias = self.root / "an-alias-for-the-design"
        try:
            _os.link(str(design), str(alias))
        except (OSError, NotImplementedError):
            self.skipTest("this filesystem does not support hard links")
        # assert the alias exists BEFORE the claim it is supposed to support --
        # the first version asserted `assertNotEqual` even when the link was
        # never made, so it failed while testing nothing at all
        self.assertTrue(alias.exists(), "the hard link was not created")
        self.assertEqual(_os.stat(str(design)).st_nlink, 2)
        receipt = self._pass_receipt()
        self.assertNotEqual(receipt["status"], pipeline.STATUS_COMMITTED)
        detail = " ".join(receipt["commit_predicate"]["reasons"])
        if "contract_378_path_identity" in \
                receipt["commit_predicate"]["unsatisfied_conjuncts"]:
            self.assertIn("hard links", detail)
        else:
            # the fixture may not have had a design file to link; then the commit
            # legitimately succeeded and this test has nothing to assert
            self.assertEqual(receipt["status"], pipeline.STATUS_COMMITTED)
