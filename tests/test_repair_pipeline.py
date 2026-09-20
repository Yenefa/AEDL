"""PR1-C5 stage 1: the host contract, the pure PRECHECK gates and rule binding.

Stage 1 is exactly the surface that must reject a round BEFORE anything durable
happens, so these tests exercise no tool, no stage and no candidate write.  The
last two tests pin the two toolchain checks the Owner required: the before-candidate
symbol digest is a host input cross-checked against the native read, and a mismatch
must block before any write.
"""

import copy
import os
import tempfile
import unittest
from pathlib import Path

from tests.test_host_toolchain import base_binding
from tests.test_repair_verification import circuit, mini
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
        self.node = ["label", "USB_DM", ["at", 0.001, 0.002, 0]]
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

    def test_a_unique_local_label_at_a_pin_resolves_to_its_observed_digest(self):
        status, payload = pipeline.resolve_removal_selector(self.index, self.selector())
        self.assertEqual(status, "PASS")
        self.assertEqual(payload, {"uuid": self.uuid, "kind": "label",
                                   "descriptor_sha256": "a" * 64})

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


if __name__ == "__main__":
    unittest.main()
