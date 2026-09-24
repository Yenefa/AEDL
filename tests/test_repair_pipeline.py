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


if __name__ == "__main__":
    unittest.main()
