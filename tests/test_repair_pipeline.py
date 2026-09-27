"""PR1-C5 stage 1: the host contract, the pure PRECHECK gates and rule binding.

Stage 1 is exactly the surface that must reject a round BEFORE anything durable
happens, so these tests exercise no tool, no stage and no candidate write.  The
last two tests pin the two toolchain checks the Owner required: the before-candidate
symbol digest is a host input cross-checked against the native read, and a mismatch
must block before any write.
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_host_toolchain import base_binding
from tests.test_repair_verification import circuit, mini
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
            "stage_root": str(self.design),
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
        self.assertEqual(receipt["status"], pipeline.STATUS_UNKNOWN)
        self.assertEqual(receipt["phase"], pipeline.PHASE_PRECHECK)
        # PRECHECK is recorded as refused; no phase was ever REACHED, and the
        # writer phases never appear at all
        self.assertEqual(receipt["phases"],
                         [{"phase": pipeline.PHASE_PRECHECK, "status": "refused"}])
        self.assertEqual([row["phase"] for row in receipt["phases"] if
                          row["status"] == "reached"], [])
        self.assertIn(pipeline.REASON_INPUT_DRIFT, self._codes(receipt))
        self.assertEqual((self.design / self.STAGE_TARGET).read_bytes(), self.raw)

    # --- containment ----------------------------------------------------
    def test_a_stage_target_that_escapes_the_stage_root_is_never_read(self):
        """The escape target is placed exactly where "../" would reach it.

        The stage root is <cand>/design, so a stage_target of
        "../outside.kicad_sch" resolves to <cand>/outside.kicad_sch.  That file
        EXISTS here on purpose: without the containment check run_round would
        read it and sail on, so this test fails if containment is removed rather
        than passing because the path happened to be missing.
        """
        outside = self.cand / "outside.kicad_sch"
        outside.write_bytes(b"secret")
        receipt = self._run(stage_target="../outside.kicad_sch")
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        self.assertTrue(receipt["terminal"])
        self.assertEqual(receipt["phase"], pipeline.PHASE_PRECHECK)
        self.assertIn(pipeline.REASON_INPUT_DRIFT, self._codes(receipt))
        # the file is still there, and the round reported no before-digest for it
        self.assertEqual(outside.read_bytes(), b"secret")
        self.assertIsNone(receipt["before_source_sha256"])

    def test_a_missing_stage_target_is_blocked_before_any_writer_runs(self):
        receipt = self._run(stage_target="absent.kicad_sch")
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        self.assertEqual(receipt["phase"], pipeline.PHASE_PRECHECK)
        self.assertEqual(receipt["phases"][-1]["status"], "refused")

    # --- precheck refusals ----------------------------------------------
    def test_a_rule_the_host_did_not_approve_is_refused(self):
        receipt = self._run(host_context=self._context(rule_id="E1"))
        self.assertEqual(receipt["status"], pipeline.STATUS_BLOCKED)
        self.assertEqual(receipt["phase"], pipeline.PHASE_PRECHECK)
        self.assertIn(pipeline.REASON_AUTH_DENIED, self._codes(receipt))
        self.assertEqual(receipt["phases"][-1]["status"], "refused")

    def test_a_refused_precheck_never_reaches_the_writer_phase(self):
        receipt = self._run(host_context=self._context(rule_id="E1"))
        reached = [row["phase"] for row in receipt["phases"]]
        self.assertNotIn(pipeline.PHASE_STAGE_APPLY, reached)
        self.assertNotIn(pipeline.PHASE_DELTA_CHECK, reached)

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
        body = textwrap.dedent(inspect.getsource(pipeline.run_round))
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

        tree = ast.parse(textwrap.dedent(inspect.getsource(pipeline.run_round)))
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
        """COMMITTED belongs to the unimplemented commit phase.

        The behavioural guarantee is asserted in the fail-closed tests above; this
        pins the structural half: the token is never written into a receipt.
        """
        import inspect
        import textwrap

        body = textwrap.dedent(inspect.getsource(pipeline.run_round))
        self.assertNotIn("status=STATUS_COMMITTED", body)
        self.assertNotIn('"status": STATUS_COMMITTED', body)
        self.assertNotIn("STATUS_COMMITTED,", body)
        self.assertNotIn("STATUS_COMMITTED}", body)

    def test_the_driven_phases_are_exactly_three_and_commit_is_not_one(self):
        self.assertEqual(pipeline.ROUND_PHASES,
                         (pipeline.PHASE_PRECHECK, pipeline.PHASE_STAGE_APPLY,
                          pipeline.PHASE_DELTA_CHECK))
        self.assertNotIn(pipeline.PHASE_COMMIT, pipeline.ROUND_PHASES)
        self.assertEqual(pipeline.ROUND_PENDING_PHASES,
                         (pipeline.PHASE_KICAD_VERIFY, pipeline.PHASE_COMMIT))

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


if __name__ == "__main__":
    unittest.main()
