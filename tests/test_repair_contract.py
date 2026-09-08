"""PR-1 C1 acceptance tests - frozen contract, schemas and public projection.

Run: python -X utf8 -m unittest tests.test_repair_contract
"""

import copy
import json
import unittest
from pathlib import Path

from tools.repair_pipeline import (
    EXCEPTION_RULE_IDS,
    FORBIDDEN_PROPOSAL_FIELDS,
    MAX_DIAGNOSIS,
    MAX_OPS,
    MAX_TEXT_CHARS,
    PROPOSAL_COMMON_REQUIRED,
    PUBLIC_CONTEXT_FIELDS,
    PUBLIC_FEEDBACK_FIELDS,
    STRICT_RULE_IDS,
    Finding,
    ProposalInvalidError,
    PolicyInvalidError,
    canonical_sha256,
    hash_bytes,
    load_patch_schema,
    load_topology_policy,
    make_public_context,
    parse_proposal,
    public_feedback,
    validate_topology_policy,
)

ROOT = Path(__file__).resolve().parents[1]
PATCH_SCHEMA = ROOT / "src" / "repair" / "patch_schema_v1.json"
TOPOLOGY_POLICY = ROOT / "src" / "repair" / "topology_policy_v1.json"

TARGET = "design/src/hardware/m2-board/m2_board.kicad_sch"
CONTEXT_ID = "ctx-pr1-c1"
BASE_SHA = "a" * 64

PER_CASE_TOKENS = (
    "USB_DM",
    "USB_DP",
    "22R",
    "10k",
    "1uF",
    "R7",
    "R8",
    "R9",
    "C5",
    "U1.13",
    "J1.A6",
    "8600",
    "10900",
    "1350",
    "10150",
    "10550",
    "1450",
    "218440000",
    "276860000",
    "0603",
    "Resistor_SMD",
    "Capacitor_SMD",
    "0x44",
    "sht30",
    "BOOT",
    "expected_delta",
    "expected_after",
    "standard_patch",
    "golden",
)


def _diagnosis():
    return [
        {
            "rule_id": "RULE-USB",
            "observed": "endpoint labels do not match the frozen intent",
            "fact_ids": ["F1", "F2"],
            "requirement_level": "MANDATORY",
            "rationale": "observed against the public fact set",
        }
    ]


def patch_body(**overrides):
    doc = {
        "schema_version": 1,
        "context_id": CONTEXT_ID,
        "target": TARGET,
        "base_source_sha256": BASE_SHA,
        "decision": "PATCH",
        "diagnosis": _diagnosis(),
        "oplist": {
            "protocol_version": 2,
            "target_format": "kicad",
            "ops": [{"op": "delete_object", "uuid": "obj-uuid-1"}],
        },
    }
    doc.update(overrides)
    return doc


def refuse_body(**overrides):
    doc = {
        "schema_version": 1,
        "context_id": CONTEXT_ID,
        "target": TARGET,
        "base_source_sha256": BASE_SHA,
        "decision": "REFUSE",
        "diagnosis": _diagnosis(),
        "refusal": {
            "reason_code": "MISSING_FACT",
            "missing_fact_ids": ["F9"],
            "explanation": "no public fact authorises this change",
            "required_human_decision": "approve a power budget",
        },
    }
    doc.update(overrides)
    return doc


def encode(doc):
    return json.dumps(doc).encode("utf-8")


def _nested(depth):
    node = {"leaf": 1}
    for _ in range(depth - 1):
        node = {"child": node}
    return node


class ParseBranchTests(unittest.TestCase):
    def test_valid_patch_accepted(self):
        proposal = parse_proposal(encode(patch_body()))
        self.assertEqual(proposal.decision, "PATCH")
        self.assertEqual(proposal.target, TARGET)
        self.assertEqual(len(proposal.ops), 1)
        self.assertTrue(proposal.proposal_sha256)
        self.assertEqual(len(proposal.proposal_sha256), 64)

    def test_valid_refuse_accepted(self):
        proposal = parse_proposal(encode(refuse_body()))
        self.assertEqual(proposal.decision, "REFUSE")
        self.assertIsNone(proposal.oplist)
        self.assertEqual(proposal.ops, ())

    def test_patch_with_refusal_rejected(self):
        doc = patch_body()
        doc["refusal"] = refuse_body()["refusal"]
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_refuse_with_oplist_rejected(self):
        doc = refuse_body()
        doc["oplist"] = patch_body()["oplist"]
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_patch_without_oplist_rejected(self):
        doc = patch_body()
        doc.pop("oplist")
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_refuse_without_refusal_rejected(self):
        doc = refuse_body()
        doc.pop("refusal")
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_unknown_decision_rejected(self):
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(patch_body(decision="APPLY")))

    def test_digest_is_stable_and_order_sensitive(self):
        first = parse_proposal(encode(patch_body()))
        second = parse_proposal(encode(patch_body()))
        self.assertEqual(first.proposal_sha256, second.proposal_sha256)

        ops = [
            {"op": "delete_object", "uuid": "obj-uuid-1"},
            {"op": "delete_object", "uuid": "obj-uuid-2"},
        ]
        a = parse_proposal(encode(patch_body(oplist={"protocol_version": 2, "target_format": "kicad", "ops": ops})))
        b = parse_proposal(encode(patch_body(oplist={"protocol_version": 2, "target_format": "kicad", "ops": list(reversed(ops))})))
        self.assertNotEqual(a.proposal_sha256, b.proposal_sha256)

    def test_defaults_are_normalised_before_digest(self):
        minimal = patch_body(
            oplist={
                "protocol_version": 2,
                "target_format": "kicad",
                "ops": [{"op": "add_net_label", "name": "NET", "at": "U1.13"}],
            }
        )
        explicit = patch_body(
            oplist={
                "protocol_version": 2,
                "target_format": "kicad",
                "ops": [
                    {
                        "op": "add_net_label",
                        "name": "NET",
                        "at": "U1.13",
                        "scope": "local",
                        "rotation": 0,
                    }
                ],
            }
        )
        self.assertEqual(
            parse_proposal(encode(minimal)).proposal_sha256,
            parse_proposal(encode(explicit)).proposal_sha256,
        )


class ClosedFieldTests(unittest.TestCase):
    def test_unknown_top_level_field_rejected(self):
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(patch_body(extra=1)))

    def test_unknown_nested_op_field_rejected(self):
        doc = patch_body(
            oplist={
                "protocol_version": 2,
                "target_format": "kicad",
                "ops": [{"op": "delete_object", "uuid": "u1", "cascade": True}],
            }
        )
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_unknown_diagnosis_field_rejected(self):
        doc = patch_body()
        doc["diagnosis"][0]["severity"] = "high"
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_missing_diagnosis_field_rejected(self):
        doc = patch_body()
        doc["diagnosis"][0].pop("rationale")
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_duplicate_key_rejected(self):
        raw = (
            b'{"schema_version":1,"schema_version":1,"context_id":"c","target":"t",'
            b'"base_source_sha256":"' + BASE_SHA.encode() + b'","decision":"REFUSE",'
            b'"diagnosis":[],"refusal":{"reason_code":"x","missing_fact_ids":[],'
            b'"explanation":"y","required_human_decision":"z"}}'
        )
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(raw)

    def test_nan_rejected(self):
        raw = b'{"schema_version":1,"context_id":"c","x":NaN}'
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(raw)

    def test_infinity_rejected(self):
        raw = b'{"schema_version":1,"context_id":"c","x":Infinity}'
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(raw)

    def test_float_literal_rejected(self):
        doc = patch_body(
            oplist={
                "protocol_version": 2,
                "target_format": "kicad",
                "ops": [
                    {
                        "op": "place_component",
                        "lib_id": "Device:R",
                        "designator": "R1",
                        "x_mil": 1.5,
                        "y_mil": 2,
                        "value": "1k",
                        "footprint": "R_0603",
                    }
                ],
            }
        )
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_bool_as_integer_rejected(self):
        doc = patch_body(
            oplist={
                "protocol_version": 2,
                "target_format": "kicad",
                "ops": [
                    {
                        "op": "place_component",
                        "lib_id": "Device:R",
                        "designator": "R1",
                        "x_mil": 100,
                        "y_mil": 200,
                        "value": "1k",
                        "footprint": "R_0603",
                        "unit": True,
                    }
                ],
            }
        )
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_bool_schema_version_rejected(self):
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(patch_body(schema_version=True)))

    def test_forbidden_self_assertion_fields_rejected(self):
        for field in FORBIDDEN_PROPOSAL_FIELDS:
            with self.subTest(field=field):
                with self.assertRaises(ProposalInvalidError):
                    parse_proposal(encode(patch_body(**{field: "x"})))

    def test_duplicate_fact_ids_rejected(self):
        doc = patch_body()
        doc["diagnosis"][0]["fact_ids"] = ["F1", "F1"]
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_op_subset_is_closed(self):
        doc = patch_body(
            oplist={
                "protocol_version": 2,
                "target_format": "kicad",
                "ops": [{"op": "move_object", "uuid": "u1"}],
            }
        )
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_protocol_and_format_are_frozen(self):
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(
                encode(patch_body(oplist={"protocol_version": 3, "target_format": "kicad", "ops": [{"op": "delete_object", "uuid": "u"}]}))
            )
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(
                encode(patch_body(oplist={"protocol_version": 2, "target_format": "json", "ops": [{"op": "delete_object", "uuid": "u"}]}))
            )


class LimitTests(unittest.TestCase):
    def test_zero_ops_rejected(self):
        doc = patch_body(oplist={"protocol_version": 2, "target_format": "kicad", "ops": []})
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_more_than_max_ops_rejected(self):
        ops = [{"op": "delete_object", "uuid": "u%d" % i} for i in range(MAX_OPS + 1)]
        doc = patch_body(oplist={"protocol_version": 2, "target_format": "kicad", "ops": ops})
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_too_many_diagnosis_entries_rejected(self):
        doc = patch_body(diagnosis=[_diagnosis()[0]] * (MAX_DIAGNOSIS + 1))
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_oversized_text_rejected(self):
        doc = patch_body()
        doc["diagnosis"][0]["rationale"] = "x" * (MAX_TEXT_CHARS + 1)
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_control_character_rejected(self):
        doc = patch_body()
        doc["diagnosis"][0]["rationale"] = "bad\x01text"
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_depth_limit_enforced(self):
        doc = patch_body()
        doc["diagnosis"][0]["observed"] = _nested(14)
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))

    def test_oversized_payload_rejected(self):
        # 16 entries x 2048 characters stays inside MAX_TEXT_CHARS but the
        # UTF-8 encoding of CJK text pushes the payload past 64 KiB.
        entry = _diagnosis()[0]
        entry["rationale"] = "汉" * MAX_TEXT_CHARS
        doc = patch_body(diagnosis=[dict(entry) for _ in range(MAX_DIAGNOSIS)])
        raw = encode(doc)
        self.assertGreater(len(raw), 64 * 1024)
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(raw)

    def test_non_utf8_payload_rejected(self):
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(b'{"schema_version":1,"a":"\xff\xfe"}')

    def test_bom_rejected(self):
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(b"\xef\xbb\xbf" + encode(patch_body()))

    def test_bad_sha256_rejected(self):
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(patch_body(base_source_sha256="A" * 64)))
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(patch_body(base_source_sha256="a" * 63)))

    def test_bad_target_rejected(self):
        for target in ("../escape.sch", "/abs/path.sch", "a//b.sch", "./a.sch", "C:/x.sch", "a/../b.sch"):
            with self.subTest(target=target):
                with self.assertRaises(ProposalInvalidError):
                    parse_proposal(encode(patch_body(target=target)))

    def test_bad_context_id_rejected(self):
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(patch_body(context_id="ctx 1")))

    def test_label_anchor_must_be_ref_pin(self):
        for anchor in ("(100,200)", "100,200", "U1", "1.U1"):
            with self.subTest(anchor=anchor):
                doc = patch_body(
                    oplist={
                        "protocol_version": 2,
                        "target_format": "kicad",
                        "ops": [{"op": "add_net_label", "name": "NET", "at": anchor}],
                    }
                )
                with self.assertRaises(ProposalInvalidError):
                    parse_proposal(encode(doc))

    def test_label_scope_and_rotation_frozen(self):
        base = {"op": "add_net_label", "name": "NET", "at": "U1.13"}
        for override in ({"scope": "global"}, {"rotation": 90}):
            with self.subTest(override=override):
                op = dict(base)
                op.update(override)
                doc = patch_body(oplist={"protocol_version": 2, "target_format": "kicad", "ops": [op]})
                with self.assertRaises(ProposalInvalidError):
                    parse_proposal(encode(doc))

    def test_lib_id_subset_frozen(self):
        doc = patch_body(
            oplist={
                "protocol_version": 2,
                "target_format": "kicad",
                "ops": [
                    {
                        "op": "place_component",
                        "lib_id": "Custom_Library:Part",
                        "designator": "R1",
                        "x_mil": 1,
                        "y_mil": 2,
                        "value": "1k",
                        "footprint": "R_0603",
                    }
                ],
            }
        )
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))


class PolicyDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_topology_policy()

    def test_repo_policy_is_closed_and_consistent(self):
        findings = validate_topology_policy(self.policy)
        self.assertEqual([f.detail for f in findings], [])

    def test_policy_is_disabled_by_default(self):
        self.assertIs(self.policy["enabled_by_default"], False)
        mutated = copy.deepcopy(self.policy)
        mutated["enabled_by_default"] = True
        self.assertTrue(validate_topology_policy(mutated))

    def test_load_topology_policy_errors_are_policy_errors(self):
        """All policy load failures exit as PolicyInvalidError — one path to catch.

        Regression for the C1 review finding: strict-JSON parse failures used to
        escape as ProposalInvalidError (load_json_strict's own wrapping), and
        unreadable paths escaped as raw OSError.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "bad.json"
            bad.write_text('{"policy_version": 1, "dup": 1, "dup": 2}', encoding="utf-8")
            with self.assertRaises(PolicyInvalidError):
                load_topology_policy(bad)

            missing = Path(td) / "missing.json"
            with self.assertRaises(PolicyInvalidError):
                load_topology_policy(missing)

    def test_five_rules_with_unique_ids(self):
        ids = [rule["id"] for rule in self.policy["rules"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(EXCEPTION_RULE_IDS) | set(STRICT_RULE_IDS))

    def test_routes_are_unique_per_rule(self):
        routes = {rule["id"]: rule["route"] for rule in self.policy["rules"]}
        for rule_id in EXCEPTION_RULE_IDS:
            self.assertEqual(routes[rule_id], "CONSTRAINED_EXCEPTION", rule_id)
        for rule_id in STRICT_RULE_IDS:
            self.assertEqual(routes[rule_id], "STRICT", rule_id)

    def test_route_flip_is_reported(self):
        mutated = copy.deepcopy(self.policy)
        for rule in mutated["rules"]:
            if rule["id"] == "E1":
                rule["route"] = "STRICT"
        details = [f.detail for f in validate_topology_policy(mutated)]
        self.assertTrue(any("E1" in d and "route" in d for d in details))

    def test_unknown_rule_id_reported(self):
        mutated = copy.deepcopy(self.policy)
        mutated["rules"].append(copy.deepcopy(mutated["rules"][0]))
        mutated["rules"][-1]["id"] = "E9"
        details = [f.detail for f in validate_topology_policy(mutated)]
        self.assertTrue(any("frozen rule ids" in d for d in details))

    def test_replace_partitions_reference_declared_slots(self):
        for rule in self.policy["rules"]:
            slots = {p["slot"] for p in rule["before"].get("partitions", [])}
            for slot in rule["after"]["replace_partitions"]:
                self.assertIn(slot, slots, rule["id"])

    def test_after_partitions_resolve_to_before_slots(self):
        for rule in self.policy["rules"]:
            before = {p["slot"]: set(p.get("names_exact", [])) for p in rule["before"].get("partitions", [])}
            for partition in rule["after"]["partitions"]:
                source = partition.get("members_from")
                if source is not None:
                    self.assertIn(source, rule["after"]["replace_partitions"], rule["id"])
                    self.assertTrue(before[source], rule["id"])
                    self.assertTrue(set(partition["names_exact"]) <= before[source], rule["id"])
                else:
                    names = set(partition["names_exact"])
                    resolved = [
                        slot
                        for slot in rule["after"]["replace_partitions"]
                        if names & before[slot]
                    ]
                    self.assertTrue(resolved, "%s: %s" % (rule["id"], sorted(names)))

    def test_members_from_resolves_to_a_declared_before_slot(self):
        for rule in self.policy["rules"]:
            for partition in rule["after"]["partitions"]:
                source = partition.get("members_from")
                if source is None:
                    continue
                match = [p for p in rule["before"].get("partitions", []) if p["slot"] == source]
                self.assertEqual(len(match), 1, rule["id"])
                self.assertIn(source, rule["after"]["replace_partitions"], rule["id"])
                self.assertTrue(
                    set(partition["names_exact"]) <= set(match[0].get("names_exact", [])),
                    rule["id"],
                )

    def test_captured_partitions_declare_no_exact_members(self):
        for rule in self.policy["rules"]:
            for partition in rule["before"].get("partitions", []):
                capture = bool(partition.get("capture_all_members"))
                self.assertNotEqual(capture, "members_exact" in partition, rule["id"])

    def test_operation_counts_match_declared_delta(self):
        for rule in self.policy["rules"]:
            delta = rule["object_delta"]
            self.assertEqual(
                rule["operation_counts"]["delete_object"], len(delta.get("remove", [])), rule["id"]
            )
            self.assertEqual(
                rule["operation_counts"]["add_net_label"], len(delta.get("add_labels", [])), rule["id"]
            )
            self.assertEqual(
                rule["operation_counts"]["place_component"],
                len(rule["after"].get("add_components", [])),
                rule["id"],
            )
            total = sum(rule["operation_counts"].values())
            self.assertLessEqual(total, 8, rule["id"])
            self.assertGreaterEqual(total, 1, rule["id"])

    def test_operation_count_drift_is_reported(self):
        mutated = copy.deepcopy(self.policy)
        for rule in mutated["rules"]:
            if rule["id"] == "E1":
                rule["operation_counts"]["delete_object"] = 1
        details = [f.detail for f in validate_topology_policy(mutated)]
        self.assertTrue(any("operation_counts.delete_object" in d for d in details))

    def test_absent_components_match_added_components(self):
        for rule in self.policy["rules"]:
            absent = set(rule["before"].get("absent_components", []))
            added = {c["reference"] for c in rule["after"].get("add_components", [])}
            self.assertEqual(absent, added, rule["id"])

    def test_absent_add_mismatch_is_reported(self):
        mutated = copy.deepcopy(self.policy)
        for rule in mutated["rules"]:
            if rule["id"] == "DC-04":
                rule["before"]["absent_components"] = []
        details = [f.detail for f in validate_topology_policy(mutated)]
        self.assertTrue(any("absent_components" in d for d in details))

    def test_new_component_pins_are_complete(self):
        for rule in self.policy["rules"]:
            for component in rule["after"].get("add_components", []):
                reference = component["reference"]
                pins = set()
                for partition in rule["after"]["partitions"]:
                    for member in partition.get("members_exact", []) + partition.get("add_exact", []):
                        if member.split(".")[0] == reference:
                            pins.add(member.split(".")[1])
                for label in rule["object_delta"].get("add_labels", []):
                    if label["at_pin"].split(".")[0] == reference:
                        pins.add(label["at_pin"].split(".")[1])
                self.assertEqual(pins, {"1", "2"}, "%s/%s" % (rule["id"], reference))

    def test_new_component_pin_removal_is_reported(self):
        mutated = copy.deepcopy(self.policy)
        for rule in mutated["rules"]:
            if rule["id"] != "DC-04":
                continue
            for partition in rule["after"]["partitions"]:
                if partition.get("add_exact") == ["R9.2"]:
                    partition["add_exact"] = []
            rule["object_delta"]["add_labels"] = [
                label for label in rule["object_delta"]["add_labels"] if label["at_pin"] != "R9.2"
            ]
            rule["after"]["distinct_partition_pins"] = [
                [pin for pin in group if pin != "R9.2"]
                for group in rule["after"]["distinct_partition_pins"]
            ]
        details = [f.detail for f in validate_topology_policy(mutated)]
        self.assertTrue(any("pins must be exactly" in d for d in details), details)

    def test_e1_swaps_exactly_two_labels(self):
        rule = next(r for r in self.policy["rules"] if r["id"] == "E1")
        after = {tuple(sorted(p["members_exact"])) for p in rule["after"]["partitions"]}
        self.assertIn(("R8.2", "U1.13"), after)
        self.assertIn(("R7.2", "U1.14"), after)
        self.assertEqual(rule["operation_counts"], {"delete_object": 2, "add_net_label": 2, "place_component": 0})
        self.assertEqual(rule["after"]["all_other_partitions"], "UNCHANGED")

    def test_e3_freezes_four_disjoint_partitions(self):
        rule = next(r for r in self.policy["rules"] if r["id"] == "E3")
        after = {tuple(sorted(p["members_exact"])) for p in rule["after"]["partitions"]}
        self.assertEqual(
            after,
            {
                ("J1.A6", "J1.B6", "R7.1"),
                ("R7.2", "U1.14"),
                ("J1.A7", "J1.B7", "R8.1"),
                ("R8.2", "U1.13"),
            },
        )
        self.assertEqual(len(rule["object_delta"]["remove"]), 2)
        self.assertEqual(rule["operation_counts"]["place_component"], 2)

    def test_distinct_partition_pins_are_disjoint(self):
        for rule in self.policy["rules"]:
            groups = rule["after"].get("distinct_partition_pins", [])
            for index, group in enumerate(groups):
                for other in groups[index + 1:]:
                    self.assertFalse(set(group) & set(other), rule["id"])

    def test_refusal_boundary_declared(self):
        boundary = self.policy["refusal_boundary"]
        self.assertIs(boundary["patch_authorized"], False)
        self.assertEqual(boundary["valid_proposal_decision"], "REFUSE")
        self.assertIs(boundary["design_bytes_must_remain_unchanged"], True)

    def test_public_projection_allow_matches_implementation(self):
        allow = self.policy["public_projection"]["allow"]
        self.assertEqual(sorted(allow), sorted(PUBLIC_CONTEXT_FIELDS))

    def test_acceptance_private_is_not_a_runtime_dependency(self):
        private = self.policy["acceptance_private_contract"]
        self.assertIs(private["runtime_dependency"], False)
        self.assertIn("C", private["forbidden_consumers"])
        self.assertIn("runtime_policy_binder", private["forbidden_consumers"])

    def test_unknown_policy_field_reported(self):
        mutated = copy.deepcopy(self.policy)
        mutated["surprise"] = True
        details = [f.detail for f in validate_topology_policy(mutated)]
        self.assertTrue(any("unknown field 'surprise'" in d for d in details))


class PublicProjectionTests(unittest.TestCase):
    def setUp(self):
        self.host_context = {
            "context_id": CONTEXT_ID,
            "target": TARGET,
            "base_source_sha256": BASE_SHA,
            "limits": {"max_ops": 8, "worker_timeout_seconds": 60, "kicad_timeout_seconds": 60},
            # host-only fields that must never reach the proposer
            "rules": [{"id": "E1"}],
            "bound_policy": {"rule_id": "E1"},
            "route": "CONSTRAINED_EXCEPTION",
            "snapshot_root": "/internal/snapshot",
        }
        self.observation = {"components": [{"reference": "R1"}]}
        self.facts = [{"id": "F1", "status": "VERIFIED"}]

    def test_public_context_is_exactly_the_allowlist(self):
        context = make_public_context(self.host_context, self.observation, self.facts)
        self.assertEqual(tuple(sorted(context)), tuple(sorted(PUBLIC_CONTEXT_FIELDS)))
        for denied in ("rules", "bound_policy", "route", "snapshot_root"):
            self.assertNotIn(denied, context)

    def test_public_context_carries_no_denied_payload(self):
        context = make_public_context(self.host_context, self.observation, self.facts)
        rendered = json.dumps(context, ensure_ascii=False)
        for token in ("expected_delta", "expected_after", "standard_patch", "golden", "approved_rule_ids"):
            self.assertNotIn(token, rendered)

    def test_public_context_rejects_leaked_value(self):
        observation = {"note": "the expected_delta is frozen host side"}
        with self.assertRaises(ProposalInvalidError):
            make_public_context(self.host_context, observation, self.facts)

    def test_public_context_rejects_leaked_key(self):
        observation = {"after": {"USB_DM": ["R8.2", "U1.13"]}}
        with self.assertRaises(ProposalInvalidError):
            make_public_context(self.host_context, observation, self.facts)

    def test_generic_op_schema_has_no_per_case_answers(self):
        context = make_public_context(self.host_context, self.observation, self.facts)
        rendered = json.dumps(context["generic_op_schema"], ensure_ascii=False)
        for token in PER_CASE_TOKENS:
            self.assertNotIn(token, rendered, token)

    def test_generic_op_schema_declares_only_three_primitives(self):
        context = make_public_context(self.host_context, self.observation, self.facts)
        ops = [entry["op"] for entry in context["generic_op_schema"]["operations"]]
        self.assertEqual(ops, ["delete_object", "add_net_label", "place_component"])

    def test_public_context_snapshots_observation_no_aliasing(self):
        """Host-side mutation AFTER issuing must not leak into the context."""
        observation = {"pins": [{"ref": "U1", "net": "/USB_DM"}]}
        context = make_public_context(self.host_context, observation, self.facts)
        observation["pins"][0]["net"] = "/MUTATED"
        self.assertEqual(
            context["current_observation"]["pins"][0]["net"], "/USB_DM"
        )

    def test_public_context_snapshots_facts_no_aliasing(self):
        facts = [{"id": "F1", "entries": [1, 2]}]
        context = make_public_context(self.host_context, self.observation, facts)
        facts[0]["entries"].append(3)
        self.assertEqual(context["public_facts"][0]["entries"], [1, 2])

    def test_public_context_limits_are_snapshotted(self):
        context = make_public_context(self.host_context, self.observation, self.facts)
        self.host_context["limits"]["max_ops"] = 999
        self.assertEqual(context["limits"]["max_ops"], 8)

    def test_public_context_rejects_unserialisable_observation(self):
        with self.assertRaises(ProposalInvalidError):
            make_public_context(self.host_context, {"handle": object()}, self.facts)

    def test_patch_schema_has_no_per_case_answers(self):
        schema_text = PATCH_SCHEMA.read_text(encoding="utf-8")
        section = json.loads(schema_text)["public_op_schema"]
        rendered = json.dumps(section, ensure_ascii=False)
        for token in PER_CASE_TOKENS:
            self.assertNotIn(token, rendered, token)

    def test_public_context_digest_is_bound(self):
        context = make_public_context(self.host_context, self.observation, self.facts)
        digest = canonical_sha256("context", context)
        self.assertEqual(digest, canonical_sha256("context", context))
        other = dict(context)
        other["context_id"] = "other-ctx"
        self.assertNotEqual(digest, canonical_sha256("context", other))

    def test_feedback_shape_is_closed(self):
        for status, expected in (
            ("COMMITTED", "APPLIED_TO_CANDIDATE"),
            ("NO_CHANGE", "NO_CHANGE"),
            ("REFUSED", "REFUSED"),
            ("BLOCKED", "REJECTED"),
            ("TOOL_ERROR", "EXECUTION_UNAVAILABLE"),
            ("UNKNOWN", "EXECUTION_UNAVAILABLE"),
        ):
            with self.subTest(status=status):
                feedback = public_feedback({"context_id": CONTEXT_ID, "status": status})
                self.assertEqual(tuple(feedback), PUBLIC_FEEDBACK_FIELDS)
                self.assertEqual(feedback["proposal_outcome"], expected)
                # Without host findings a rejected transaction cannot be
                # narrowed, so the coarse code stays EXECUTION_UNAVAILABLE
                # rather than guessing at a more specific (and leakier) reason.
                expected_reason = "OK" if expected in ("APPLIED_TO_CANDIDATE", "NO_CHANGE", "REFUSED") else "EXECUTION_UNAVAILABLE"
                self.assertEqual(feedback["reason_code"], expected_reason, status)

    def test_rollback_cause_is_preserved(self):
        self.assertEqual(
            public_feedback({"context_id": CONTEXT_ID, "status": "ROLLBACK", "cause_status": "BLOCKED"})["proposal_outcome"],
            "REJECTED",
        )
        self.assertEqual(
            public_feedback({"context_id": CONTEXT_ID, "status": "ROLLBACK", "cause_status": "TOOL_ERROR"})["proposal_outcome"],
            "EXECUTION_UNAVAILABLE",
        )

    def test_feedback_maps_internal_findings_to_coarse_codes(self):
        cases = {
            "REPAIR_SCHEMA_INVALID": "PROPOSAL_INVALID",
            "REPAIR_AUTH_DENIED": "REPAIR_NOT_AUTHORIZED",
            "REPAIR_POLICY_DISABLED": "REPAIR_NOT_AUTHORIZED",
            "REPAIR_INPUT_DRIFT": "INPUT_CHANGED",
            "REPAIR_DELTA_MISMATCH": "REPAIR_CONSTRAINT_VIOLATION",
            "REPAIR_PROTECTED_DIFF": "REPAIR_CONSTRAINT_VIOLATION",
            "REPAIR_TIMEOUT": "EXECUTION_UNAVAILABLE",
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                feedback = public_feedback(
                    {
                        "context_id": CONTEXT_ID,
                        "status": "BLOCKED",
                        "reasons": [{"code": code, "stage": "PRECHECK", "object_id": None, "detail": "d"}],
                    }
                )
                self.assertEqual(feedback["reason_code"], expected)

    def test_feedback_reason_priority_is_deterministic(self):
        feedback = public_feedback(
            {
                "context_id": CONTEXT_ID,
                "status": "BLOCKED",
                "reasons": [
                    {"code": "REPAIR_TIMEOUT"},
                    {"code": "REPAIR_SCHEMA_INVALID"},
                ],
            }
        )
        self.assertEqual(feedback["reason_code"], "PROPOSAL_INVALID")

    def test_feedback_issue_ids_are_intersected_with_public_allowlist(self):
        feedback = public_feedback(
            {
                "context_id": CONTEXT_ID,
                "status": "BLOCKED",
                "observed_issue_ids": ["ISSUE-1", "ISSUE-SECRET"],
                "public_issue_ids": ["ISSUE-1"],
            }
        )
        self.assertEqual(feedback["observed_issue_ids"], ["ISSUE-1"])

    def test_feedback_emits_nothing_without_an_allowlist(self):
        feedback = public_feedback(
            {"context_id": CONTEXT_ID, "status": "BLOCKED", "observed_issue_ids": ["ISSUE-1"]}
        )
        self.assertEqual(feedback["observed_issue_ids"], [])

    def test_feedback_never_exposes_internal_fields(self):
        feedback = public_feedback(
            {
                "context_id": CONTEXT_ID,
                "status": "COMMITTED",
                "patch_sha256": "b" * 64,
                "route": "STRICT",
                "thin_verification": {"status": "PASS"},
            }
        )
        rendered = json.dumps(feedback)
        for leaked in ("patch_sha256", "route", "thin_verification", "STRICT"):
            self.assertNotIn(leaked, rendered)


class SchemaCrossReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(PATCH_SCHEMA.read_text(encoding="utf-8"))

    def test_schema_declares_host_patch_and_receipt_shapes(self):
        defs = self.schema["$defs"]
        for name in ("Proposal", "HostPatch", "TransactionReceipt", "PublicContext", "PublicFeedback", "Finding"):
            self.assertIn(name, defs)

    def test_schema_required_matches_validator(self):
        self.assertEqual(
            tuple(self.schema["$defs"]["Proposal"]["required"]), PROPOSAL_COMMON_REQUIRED
        )

    def test_schema_forbids_the_same_fields_as_the_validator(self):
        clause = self.schema["$defs"]["Proposal"]["not"]["anyOf"]
        declared = {entry["required"][0] for entry in clause}
        self.assertEqual(declared, set(FORBIDDEN_PROPOSAL_FIELDS))

    def test_proposal_branches_are_mutually_exclusive(self):
        branches = self.schema["$defs"]["Proposal"]["allOf"]
        patch_then = branches[0]["then"]
        refuse_then = branches[1]["then"]
        self.assertIn("oplist", patch_then["required"])
        self.assertIn("refusal", patch_then["not"]["required"])
        self.assertIn("refusal", refuse_then["required"])
        self.assertIn("oplist", refuse_then["not"]["required"])

    def test_object_schemas_are_closed(self):
        closed_defs = (
            "Proposal",
            "HostPatch",
            "PublicContext",
            "PublicFeedback",
            "DeleteObjectOp",
            "AddNetLabelOp",
            "PlaceComponentOp",
            "Oplist",
            "DiagnosisEntry",
            "Refusal",
            "Finding",
            "TransactionReceipt",
        )
        for name in closed_defs:
            with self.subTest(name=name):
                self.assertIs(self.schema["$defs"][name].get("additionalProperties"), False)

    def test_schema_and_validator_reject_the_same_document(self):
        doc = patch_body()
        doc["oplist"]["ops"][0]["cascade"] = True
        with self.assertRaises(ProposalInvalidError):
            parse_proposal(encode(doc))
        op_defs = [
            self.schema["$defs"]["DeleteObjectOp"],
            self.schema["$defs"]["AddNetLabelOp"],
            self.schema["$defs"]["PlaceComponentOp"],
        ]
        self.assertTrue(all("cascade" not in d.get("properties", {}) for d in op_defs))

    def test_public_op_schema_is_not_the_host_patch(self):
        section = self.schema["public_op_schema"]
        rendered = json.dumps(section)
        for host_field in ("route", "bound_policy", "authority", "patch_sha256", "expected_delta"):
            self.assertNotIn(host_field, rendered)


class HashHelperTests(unittest.TestCase):
    def test_hash_bytes_is_raw_sha256(self):
        self.assertEqual(
            hash_bytes(b"abc"),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_canonical_digest_is_kind_bound(self):
        value = {"b": 1, "a": 2}
        self.assertEqual(canonical_sha256("proposal", value), canonical_sha256("proposal", value))
        self.assertNotEqual(canonical_sha256("proposal", value), canonical_sha256("patch", value))

    def test_canonical_json_rejects_floats(self):
        with self.assertRaises(ValueError):
            canonical_sha256("proposal", {"x": 1.5})

    def test_finding_is_host_only_serialisable(self):
        finding = Finding(code="REPAIR_SCHEMA_INVALID", stage="PRECHECK", object_id=None, detail="d")
        self.assertEqual(
            set(finding.to_dict()), {"code", "stage", "object_id", "detail"}
        )


if __name__ == "__main__":
    unittest.main()
