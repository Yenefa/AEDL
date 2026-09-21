"""C2 comparisons use independent, TEST_ONLY host expectations, never a binder.

These tests establish software comparison behavior, not fresh KiCad verification
or permission to execute a repair. The production module cannot read fixtures.
"""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import uuid

from gates import repair_verification as verification

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def digest(kind, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(("AEDL-PR1:" + kind + ":1\0").encode() + raw).hexdigest()


def stable_uuid(name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "aedl-c2-test:" + name))


SHEET = "/" + stable_uuid("sheet")
ABSENT = {"absent": True}


def component(reference, value="10k", lib_id="Device:R", new=False):
    ident = {"sheet_path": SHEET, "component_uuid": stable_uuid(reference),
             "reference": reference, "unit": 1}
    if new:
        ident["component_uuid"] = "new:" + reference
    return {"identity": ident, "reference": reference, "lib_id": lib_id,
            "lib_definition_sha256": "1" * 64, "value": value,
            "footprint": "Resistor_SMD:R_0603_1608Metric", "unit": 1,
            "position_nm": [100000, 200000], "rotation": 0, "mirror": "none",
            "dnp": False, "in_bom": True, "on_board": True,
            "pin_definition_sha256": "2" * 64}


def pin(comp, number):
    ident = dict(comp["identity"], number=number,
                 pin_uuid=stable_uuid(comp["reference"] + "." + number))
    if ident["component_uuid"].startswith("new:"):
        ident["pin_uuid"] = ident["component_uuid"] + "." + number
    return {"identity": ident, "name": number, "electrical_type": "passive",
            "no_connect": False, "partition_key": ""}


def source_object(ident, kind, ast=None):
    ast = ast or [kind, ["uuid", {"string": ident}]]
    return {"identity": ident, "kind": kind,
            "semantic_ast_sha256": digest("protected", ast),
            "descriptor": {"ast": ast}}


def refresh(observation):
    """Independent bookkeeping only; do not derive expected effects here."""
    for partition in observation["partitions"]:
        partition["members"].sort(key=lambda x: json.dumps(x, sort_keys=True))
        partition["key"] = digest("topology", partition["members"])
        for item in observation["pins"]:
            if item["identity"] in partition["members"]:
                item["partition_key"] = partition["key"]
    pins = sorted([p["identity"] for p in observation["pins"]],
                  key=lambda x: json.dumps(x, sort_keys=True))
    comps = sorted([c["identity"] for c in observation["components"]],
                   key=lambda x: json.dumps(x, sort_keys=True))
    observation["coverage"] = {
        "expected_pin_keys_sha256": digest("topology", pins),
        "observed_pin_keys_sha256": digest("topology", pins),
        "expected_component_keys_sha256": digest("topology", comps),
        "observed_component_keys_sha256": digest("topology", comps),
        "expected_pin_count": len(pins), "observed_pin_count": len(pins),
        "complete": True,
    }
    return observation


def circuit():
    comps = [component("R1"), component("R2")]
    pins = [pin(c, n) for c in comps for n in ("1", "2")]
    return refresh({"version": 1, "source_sha256": "a" * 64,
                    "components": comps, "pins": pins,
                    "partitions": [{"key": "", "members": [p["identity"]],
                                    "names": []} for p in pins],
                    "source_objects": [source_object(c["identity"]["component_uuid"], "symbol")
                                       for c in comps] + [source_object("root:lib_symbols", "lib_symbols")],
                    "coverage": {}})


def join_first_two(before):
    after = copy.deepcopy(before)
    first, second = after["partitions"][:2]
    after["partitions"] = [{"key": "", "members": first["members"] + second["members"],
                            "names": ["/TEST"]}] + after["partitions"][2:]
    after["source_objects"].append(semantic_label("new:label:0", "test-anchor-0", [1000000, 2000000]))
    after["source_sha256"] = "b" * 64
    return refresh(after)


def policy(before, expected):
    """Explicit TEST_ONLY host object; no runtime permission is asserted."""
    delta = verification.observation_delta(before, expected, expected=True)
    roles = {"new:" + c["reference"]: {"reference": c["reference"], "pin_numbers": ["1", "2"]}
             for c in expected["components"] if c["identity"]["component_uuid"].startswith("new:")}
    before_objects = {o["identity"]: o for o in before["source_objects"]}
    after_objects = {o["identity"]: o for o in expected["source_objects"]}
    removed = {key: {"uuid": key, "kind": obj["kind"],
                     "descriptor_sha256": digest("protected", obj["descriptor"])}
               for key, obj in before_objects.items() if key not in after_objects}
    bound = {"version": 1, "rule_id": "TEST_ONLY", "route": "STRICT",
             "policy_file_sha256": "c" * 64, "authority_context_digest": "d" * 64,
             "before_source_sha256": before["source_sha256"],
             "before_topology_sha256": verification.topology_sha256(before),
             "pin_identity_map": {}, "object_identity_map": removed,
             "captured_partitions": {}, "new_component_roles": roles,
             "expected_after": expected, "authorized_delta": delta,
             "authorized_delta_sha256": digest("delta", delta),
             "protected_projection_sha256": "e" * 64, "operation_constraints": {}}
    bound["protected_projection_sha256"] = verification.protected_projection_sha256(before, bound)
    return bound


def semantic_label(role, name, point_nm, rotation=0):
    """TEST_ONLY expected shape for a new label: engineering semantics only."""
    return {"identity": role, "kind": "label",
            "semantics": {"name": name, "scope": "local",
                          "point_nm": list(point_nm), "rotation": rotation}}


def semantic_symbol(reference):
    """TEST_ONLY expected shape for a new component symbol."""
    return {"identity": "new:" + reference, "kind": "symbol",
            "semantics": {"reference": reference}}


def actual_new_object(obj, real):
    """TEST_ONLY real AFTER shape for one semantic expectation."""
    if obj["kind"] == "symbol":
        return source_object(real, "symbol", ["symbol", ["uuid", {"string": real}]])
    semantics = obj["semantics"]
    x, y = semantics["point_nm"]
    return source_object(real, "label", [
        "label", {"string": semantics["name"]},
        ["at", {"number": str(x / 1000000)}, {"number": str(y / 1000000)},
         {"number": str(semantics["rotation"])}],
        ["uuid", {"string": real}]])


def actualize(expected):
    replacements = {}

    def replace(value):
        if isinstance(value, str) and value.startswith("new:"):
            return replacements.setdefault(value, stable_uuid("actual:" + value))
        if isinstance(value, dict):
            return {k: replace(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace(v) for v in value]
        return value

    actual = replace(copy.deepcopy(expected))
    objects = []
    for obj in actual["source_objects"]:
        if "semantics" in obj:
            objects.append(actual_new_object(obj, obj["identity"]))
        else:
            obj["semantic_ast_sha256"] = digest("protected", obj["descriptor"]["ast"])
            objects.append(obj)
    actual["source_objects"] = objects
    return refresh(actual)


def symbolic_labels(observation, mapping):
    """Swap concrete label UUIDs for symbolic new:label:<slot> roles in-place."""
    def walk(value):
        if isinstance(value, str):
            return mapping.get(value, value)
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value
    for obj in observation["source_objects"]:
        if "descriptor" in obj and "ast" in obj["descriptor"]:
            obj["descriptor"]["ast"] = walk(obj["descriptor"]["ast"])
        elif "semantics" in obj:
            obj["semantics"] = walk(obj["semantics"])
        obj["identity"] = mapping.get(obj["identity"], obj["identity"])
    return observation


def semanticize(observation):
    """TEST_ONLY: convert symbolic new: objects to the semantic expected shape."""
    objects = []
    for obj in observation["source_objects"]:
        if obj["identity"].startswith("new:"):
            if obj["kind"] == "label":
                semantics = verification._label_semantics(obj["descriptor"]["ast"])
            else:
                semantics = {"reference": obj["identity"][len("new:"):]}
            objects.append({"identity": obj["identity"], "kind": obj["kind"],
                            "semantics": semantics})
        else:
            obj["semantic_ast_sha256"] = verification.canonical_sha256(
                "protected", obj["descriptor"]["ast"])
            objects.append(obj)
    observation["source_objects"] = objects
    return observation


def resync_bookkeeping(observation):
    """Recompute partition keys, per-pin partition_key and coverage digests.

    TEST_ONLY: after a deliberate mutation this restores internal consistency
    so a rejection is attributable to the frozen expectation alone.
    """
    for part in observation["partitions"]:
        part["key"] = verification.canonical_sha256("topology",
            verification._sorted_unique(part["members"], "partition members"))
    for pin_row in observation["pins"]:
        for part in observation["partitions"]:
            if any(m == pin_row["identity"] for m in part["members"]):
                pin_row["partition_key"] = part["key"]
                break
    pin_ids = sorted([p["identity"] for p in observation["pins"]],
                     key=verification.canonical_json_bytes)
    comp_ids = sorted([c["identity"] for c in observation["components"]],
                      key=verification.canonical_json_bytes)
    coverage = observation["coverage"]
    coverage["expected_pin_keys_sha256"] = verification.canonical_sha256("topology", pin_ids)
    coverage["observed_pin_keys_sha256"] = coverage["expected_pin_keys_sha256"]
    coverage["expected_component_keys_sha256"] = verification.canonical_sha256("topology", comp_ids)
    coverage["observed_component_keys_sha256"] = coverage["expected_component_keys_sha256"]
    coverage["expected_pin_count"] = coverage["observed_pin_count"] = len(pin_ids)
    return observation


def manifests():
    manifest = {"version": 1, "files": [
        {"path": "design/board.kicad_sch", "sha256": "a" * 64, "size_bytes": 10, "role": "TARGET"},
        {"path": "design/firmware.h", "sha256": "b" * 64, "size_bytes": 8, "role": "READONLY_DEPENDENCY"}]}
    return {"before": manifest, "after": copy.deepcopy(manifest)}


FIXTURES = Path(__file__).parent / "fixtures" / "repair_pr1"


def symbolic_source(comp, pins):
    return source_object(comp["identity"]["component_uuid"], "symbol", [
        "symbol", ["uuid", {"string": comp["identity"]["component_uuid"]}],
        ["property", {"string": "Reference"}, {"string": comp["reference"]}],
    ] + [["pin", {"string": p["identity"]["number"]},
          ["uuid", {"string": p["identity"]["pin_uuid"]}]] for p in pins])


def replace_partitions(obs, definitions):
    lookup = {p["identity"]["reference"] + "." + p["identity"]["number"]: p["identity"]
              for p in obs["pins"]}
    members = {p for definition in definitions for p in definition["members"]}
    obs["partitions"] = [part for part in obs["partitions"]
                         if not any(p["reference"] + "." + p["number"] in members for p in part["members"])]
    for definition in definitions:
        obs["partitions"].append({"key": "", "members": [lookup[p] for p in definition["members"]],
                                  "names": definition["names"]})
    return refresh(obs)


def five_case(case):
    """Independent electrical fixture; source parsing is tested on real bytes.

    This function is TEST_ONLY and never loads the host runtime policy. P4's
    private expectations determine the desired graph and component values.
    """
    acceptance = json.loads((FIXTURES / "private" / "acceptance_v1.json").read_text(encoding="utf-8"))["cases"][case]
    pin_numbers = {"J1": ["A6", "B6", "A7", "B7"], "U1": ["2", "8", "13", "14"],
                   "U2": ["2", "5", "6", "7", "8", "9"], "U3": ["1", "2", "3", "4", "5"],
                   "R3": ["1", "2"], "R7": ["1", "2"], "R8": ["1", "2"],
                   "R9": ["1", "2"], "C5": ["1", "2"], "SW1": ["1", "2"], "SW2": ["1", "2"]}
    missing = {entry["reference"] for entry in acceptance["add_components"]}
    comps = [component(ref, value="22R" if ref in ("R7", "R8") else "10k")
             for ref in pin_numbers if ref not in missing]
    pins = [pin(c, n) for c in comps for n in pin_numbers[c["reference"]]]
    for p in pins:
        if p["identity"]["reference"] == "U2" and p["identity"]["number"] == "6":
            p["no_connect"] = True
    obs = refresh({"version": 1, "source_sha256": "a" * 64, "components": comps,
                   "pins": pins, "partitions": [{"key": "", "members": [p["identity"]], "names": []} for p in pins],
                   "source_objects": [symbolic_source(c, [p for p in pins if p["identity"]["reference"] == c["reference"]]) for c in comps]
                   + [source_object("root:lib_symbols", "lib_symbols")], "coverage": {}})
    gnd = ["U2.7", "U2.8", "U2.9", "SW1.2", "SW2.2", "U3.2"]
    if case != "DC-02":
        gnd.append("U2.2")
    if case != "DC-05":
        gnd.append("C5.2")
    supply = ["U2.5", "R3.1", "U3.5"] + ([] if case == "DC-04" else ["R9.1"])
    nets = [{"names": ["/GND"], "members": gnd}, {"names": ["/+3V3"], "members": supply},
            {"names": ["/BOOT"], "members": ["SW2.1", "U1.8"] + ([] if case == "DC-04" else ["R9.2"])},
            {"names": ["/EN"], "members": ["R3.2", "SW1.1", "U1.2"] + ([] if case == "DC-05" else ["C5.1"])}]
    if case == "DC-03":
        nets += [{"names": ["/USB_DP", "/USB_DP_CONN"], "members": ["J1.A6", "J1.B6", "U1.14"]},
                 {"names": ["/USB_DM", "/USB_DM_CONN"], "members": ["J1.A7", "J1.B7", "U1.13"]}]
    else:
        nets += [{"names": ["/USB_DP_CONN"], "members": ["J1.A6", "J1.B6", "R7.1"]},
                 {"names": ["/USB_DM_CONN"], "members": ["J1.A7", "J1.B7", "R8.1"]},
                 {"names": ["/USB_DP"], "members": ["R7.2", "U1.13" if case == "DC-01" else "U1.14"]},
                 {"names": ["/USB_DM"], "members": ["R8.2", "U1.14" if case == "DC-01" else "U1.13"]}]
    replace_partitions(obs, nets)
    remove_objects = []
    for n in range(2 if case in ("DC-01", "DC-03") else 0):
        kind = "wire" if case == "DC-03" else "label"
        obj = source_object(stable_uuid("fault-" + case + str(n)), kind)
        remove_objects.append(obj)
    obs["source_objects"].extend(remove_objects)
    expected = copy.deepcopy(obs)
    expected["source_sha256"] = "b" * 64
    expected["source_objects"] = [o for o in expected["source_objects"] if o not in remove_objects]
    for declaration in acceptance["add_components"]:
        c = component(declaration["reference"], new=True)
        c.update(declaration)
        pp = [pin(c, number) for number in ("1", "2")]
        expected["components"].append(c)
        expected["pins"].extend(pp)
        expected["partitions"].extend({"key": "", "members": [p["identity"]], "names": []} for p in pp)
        expected["source_objects"].append(semantic_symbol(c["reference"]))
    definitions = []
    for part in acceptance["after"]:
        if "capture" in part:
            captured = next(p for p in obs["partitions"] if part["capture"] in p["names"])
            members = [p["reference"] + "." + p["number"] for p in captured["members"]]
            definitions.append({"names": [part["capture"]], "members": members + part["add"]})
        else:
            definitions.append(part)
    replace_partitions(expected, definitions)
    label_count = {"DC-01": 2, "DC-02": 1, "DC-03": 0, "DC-04": 2, "DC-05": 2}[case]
    for n in range(label_count):
        role = "new:label:" + str(n)
        expected["source_objects"].append(
            semantic_label(role, "test-anchor-" + str(n), [1000000 + n, 2000000 + n]))
    return obs, expected, policy(obs, expected), actualize(expected)


class DeltaAndProtectedTests(unittest.TestCase):
    def setUp(self):
        self.before = circuit()
        self.expected = join_first_two(self.before)
        self.bound = policy(self.before, self.expected)
        self.after = actualize(self.expected)

    # --- P1 role contract rejections (2026-09-08 review) -------------------
    def test_expected_new_pin_uuid_must_be_exact_role(self):
        before, expected, bound, after = five_case("DC-04")
        bound = copy.deepcopy(bound)
        corrupted = False
        for p in bound["expected_after"]["pins"]:
            pu = p["identity"]["pin_uuid"]
            if isinstance(pu, str) and pu.startswith("new:") and "." in pu:
                wrong = "new:totally_wrong_pin_role"
                # keep partitions internally consistent (members + recomputed
                # key): the rejection must come from the role rule alone
                for part in bound["expected_after"]["partitions"]:
                    for m in part["members"]:
                        if m == p["identity"]:
                            m["pin_uuid"] = wrong
                    part["key"] = verification.canonical_sha256("topology",
                        verification.normalize_observation.__wrapped__ if False else part["members"]) if False else part["key"]
                p["identity"]["pin_uuid"] = wrong
                corrupted = True
                break
        self.assertTrue(corrupted)
        # keep ALL bookkeeping consistent so the rejection comes from the role rule alone
        resync_bookkeeping(bound["expected_after"])
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")
        self.assertEqual(verification.compare_protected(before, after, bound, manifests())["status"], "FAIL")

    def test_expected_new_label_uuid_must_use_label_slot_role(self):
        before, expected, bound, after = five_case("DC-04")
        bound = copy.deepcopy(bound)
        corrupted = False
        for obj in bound["expected_after"]["source_objects"]:
            if obj["kind"] == "label" and obj["identity"].startswith("new:"):
                obj["identity"] = "new:bogus_label_role"
                corrupted = True
                break
        self.assertTrue(corrupted)
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")
        self.assertEqual(verification.compare_protected(before, after, bound, manifests())["status"], "FAIL")

    def test_expected_new_label_slots_must_be_dense_from_zero(self):
        before, expected, bound, after = five_case("DC-04")
        bound = copy.deepcopy(bound)
        slots = sorted(o["identity"] for o in bound["expected_after"]["source_objects"]
                       if o["kind"] == "label" and o["identity"].startswith("new:"))
        if len(slots) < 2:
            self.skipTest("fixture carries fewer than two labels")
            return
        for obj in bound["expected_after"]["source_objects"]:
            if obj["identity"] == slots[-1]:
                obj["identity"] = "new:label:7"
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")
        self.assertEqual(verification.compare_protected(before, after, bound, manifests())["status"], "FAIL")

    # --- parsed-label alignment through the real S-expression parser ------
    def test_parsed_new_label_aligns_only_its_uuid(self):
        # label anchors need wire geometry to be attributable to a pin: pin A
        # sits at (10, 9); run a wire down to (10, 15) and hang two labels on
        # that wire endpoint.
        raw = mini(extra=label("/NET_A", 10, 9, slot=11) + label("/NET_B", 10, 11, slot=12)
                   + wire(10, 9, 10, 11))
        before = verification.normalize_observation(verification.observe_source(raw))
        label_a_uuid = "00000000-0000-0000-0000-000000000011"
        label_b_uuid = "00000000-0000-0000-0000-000000000012"
        role_a = "new:label:0"
        after = verification.normalize_observation(
            verification.observe_source(raw.replace(label_a_uuid.encode(), stable_uuid("actual label A").encode())))
        expected = symbolic_labels(copy.deepcopy(after), {stable_uuid("actual label A"): role_a})
        semanticize(expected)
        refresh(expected)
        original_descriptor = [o["descriptor"] for o in before["source_objects"]
                               if o["identity"] == label_a_uuid][0]
        bound = policy(before, expected)
        bound["object_identity_map"] = {label_a_uuid: {"uuid": label_a_uuid, "kind": "label",
            "descriptor_sha256": verification.canonical_sha256("protected", original_descriptor)}}
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "PASS")
        after_swapped = verification.normalize_observation(
            verification.observe_source(raw.replace(label_b_uuid.encode(), stable_uuid("actual label A").encode())))
        self.assertEqual(verification.compare_delta(before, after_swapped, bound)["status"], "FAIL")

    # --- frozen-case targeted negative mutations (E2-NC / DC04-BOOT / DC05-EN)
    def test_dc02_addr_must_not_become_no_connect(self):
        before, expected, bound, _ = five_case("DC-02")
        mutated = actualize(expected)
        for p in mutated["pins"]:
            if p["identity"]["reference"] == "U2" and p["identity"]["number"] == "2":
                p["no_connect"] = True
        refresh(mutated)
        resync_bookkeeping(mutated)
        self.assertEqual(verification.compare_delta(before, mutated, bound)["status"], "FAIL")
        self.assertEqual(verification.compare_protected(before, mutated, bound, manifests())["status"], "FAIL")

    def test_dc04_boot_switch_members_must_survive(self):
        before, expected, bound, _ = five_case("DC-04")
        mutated = actualize(expected)
        for part in mutated["partitions"]:
            names = part.get("names") or []
            if "/BOOT" in names:
                part["members"] = [m for m in part["members"]
                                   if not (m["reference"] == "U1" and m["number"] == "8")]
        escapee = [m for m in mutated["pins"] if m["identity"]["reference"] == "U1"
                   and m["identity"]["number"] == "8"][0]["identity"]
        mutated["partitions"].append({"key": "", "members": [escapee], "names": []})
        refresh(mutated)
        resync_bookkeeping(mutated)
        self.assertEqual(verification.compare_delta(before, mutated, bound)["status"], "FAIL")
        self.assertEqual(verification.compare_protected(before, mutated, bound, manifests())["status"], "FAIL")

    def test_dc05_en_pin_u1_2_must_stay_on_en(self):
        before, expected, bound, _ = five_case("DC-05")
        mutated = actualize(expected)
        for part in mutated["partitions"]:
            names = part.get("names") or []
            if "/EN" in names:
                part["members"] = [m for m in part["members"]
                                   if not (m["reference"] == "U1" and m["number"] == "2")]
        escapee = [m for m in mutated["pins"] if m["identity"]["reference"] == "U1"
                   and m["identity"]["number"] == "2"][0]["identity"]
        mutated["partitions"].append({"key": "", "members": [escapee], "names": []})
        refresh(mutated)
        resync_bookkeeping(mutated)
        self.assertEqual(verification.compare_delta(before, mutated, bound)["status"], "FAIL")
        self.assertEqual(verification.compare_protected(before, mutated, bound, manifests())["status"], "FAIL")

    def test_raw_bytes_and_domain_separation(self):
        self.assertNotEqual(verification.hash_bytes(b"a\r\n"), verification.hash_bytes(b"a\n"))
        self.assertEqual(verification.canonical_sha256("delta", {"z": "中文", "a": 1}),
                         digest("delta", {"a": 1, "z": "中文"}))
        self.assertNotEqual(verification.canonical_sha256("delta", {}),
                            verification.canonical_sha256("protected", {}))

    def test_hash_rejects_non_json_numbers_keys_and_unknown_domains(self):
        for value in (1.0, float("nan"), {1: "x"}, {"bad": object()}):
            with self.subTest(value=type(value).__name__), self.assertRaises(ValueError):
                verification.canonical_sha256("delta", value)
        with self.assertRaises(ValueError):
            verification.canonical_sha256("anything", {})

    def test_exact_change_passes_with_fresh_label_uuid(self):
        result = verification.compare_delta(self.before, self.after, self.bound)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["unexpected"], [])
        self.assertEqual(result["actual_delta_sha256"], result["authorized_delta_sha256"])

    def test_protected_complement_and_target_bytes(self):
        deps = manifests()
        deps["after"]["files"][0]["sha256"] = "c" * 64
        result = verification.compare_protected(self.before, self.after, self.bound, deps)
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(result["dependencies_unchanged"])

    def test_order_and_provenance_do_not_change_electrical_delta(self):
        shuffled = copy.deepcopy(self.after)
        for section in ("pins", "partitions", "components", "source_objects"):
            shuffled[section].reverse()
        shuffled["source_sha256"] = "f" * 64
        self.assertEqual(verification.compare_delta(self.before, shuffled, self.bound)["status"], "PASS")

    def test_missing_repair_is_reported(self):
        result = verification.compare_delta(self.before, self.before, self.bound)
        self.assertEqual(result["status"], "FAIL", result)
        self.assertTrue(result["missing"])

    def test_third_network_change_is_reported_by_both_checks(self):
        after = copy.deepcopy(self.after)
        after["partitions"][-1]["names"] = ["/UNAUTHORIZED"]
        refresh(after)
        result = verification.compare_delta(self.before, after, self.bound)
        self.assertEqual(result["status"], "FAIL", result)
        self.assertTrue(result["unexpected"])
        self.assertEqual(verification.compare_protected(self.before, after, self.bound, manifests())["status"], "FAIL")

    def test_attribute_and_nc_changes_fail(self):
        for field, value in (("value", "33R"), ("footprint", "wrong"), ("dnp", True),
                             ("in_bom", False), ("on_board", False), ("position_nm", [0, 0])):
            with self.subTest(field=field):
                after = copy.deepcopy(self.after)
                after["components"][0][field] = value
                self.assertEqual(verification.compare_delta(self.before, after, self.bound)["status"], "FAIL")
                self.assertEqual(verification.compare_protected(self.before, after, self.bound, manifests())["status"], "FAIL")
        after = copy.deepcopy(self.after)
        after["pins"][-1]["no_connect"] = True
        self.assertEqual(verification.compare_delta(self.before, after, self.bound)["status"], "FAIL")

    def test_incomplete_or_forged_coverage_is_unknown(self):
        for mutate in (lambda x: x["pins"].pop(),
                       lambda x: x["coverage"].update(complete=False),
                       lambda x: x["coverage"].update(expected_pin_keys_sha256="0" * 64),
                       lambda x: x["coverage"].update(observed_pin_count=True),
                       lambda x: x["pins"].append(copy.deepcopy(x["pins"][0]))):
            after = copy.deepcopy(self.after)
            mutate(after)
            result = verification.compare_delta(self.before, after, self.bound)
            self.assertEqual(result["status"], "UNKNOWN", result)
            self.assertFalse(result["coverage_complete"])

    def test_unknown_observation_fields_are_not_silently_ignored(self):
        after = copy.deepcopy(self.after)
        after["components"][0]["secret_pin"] = 9
        self.assertEqual(verification.compare_delta(self.before, after, self.bound)["status"], "UNKNOWN")

    def test_alias_set_is_exact(self):
        after = copy.deepcopy(self.after)
        after["partitions"][0]["names"].append("/EXTRA_ALIAS")
        self.assertEqual(verification.compare_delta(self.before, after, self.bound)["status"], "FAIL")

    def test_untouched_unknown_source_subtree_is_protected(self):
        after = copy.deepcopy(self.after)
        obj = next(o for o in after["source_objects"] if o["kind"] == "lib_symbols")
        obj["descriptor"]["ast"].append(["future_field", {"string": "changed"}])
        obj["semantic_ast_sha256"] = digest("protected", obj["descriptor"]["ast"])
        self.assertEqual(verification.compare_protected(self.before, after, self.bound, manifests())["status"], "FAIL")

    def test_dependency_content_set_role_and_case_collisions(self):
        for mutation in ("content", "removed", "added", "role", "case", "target"):
            with self.subTest(mutation=mutation):
                deps = manifests()
                files = deps["after"]["files"]
                if mutation == "content":
                    files[1]["sha256"] = "f" * 64
                elif mutation == "removed":
                    files.pop()
                elif mutation == "added":
                    files.append(dict(files[1], path="design/new.h"))
                elif mutation == "role":
                    files[1]["role"] = "TARGET"
                elif mutation == "case":
                    files.append(dict(files[1], path="design/FIRMWARE.h"))
                else:
                    files[0]["path"] = "design/another.kicad_sch"
                result = verification.compare_protected(self.before, self.after, self.bound, deps)
                self.assertNotEqual(result["status"], "PASS", result)
                self.assertFalse(result["dependencies_unchanged"])

    def test_unsafe_paths_are_rejected(self):
        for path in ("../x", "C:/x", "//host/x", "design//x", "design/CON.txt",
                     "design/file:stream", "design/end.", "design/end ", "design\\x",
                     "design/a?b", "design/a*b", "design/a|b", 'design/a"b',
                     "design/a<b", "design/a>b", "design/COM¹.txt", "design/LPT²"):
            deps = manifests()
            deps["after"]["files"][1]["path"] = path
            with self.subTest(path=path):
                self.assertEqual(verification.compare_protected(self.before, self.after, self.bound, deps)["status"], "UNKNOWN")

    def test_policy_binding_and_authorized_delta_cannot_drift(self):
        for field in ("before_source_sha256", "before_topology_sha256", "authorized_delta_sha256",
                      "protected_projection_sha256"):
            bound = copy.deepcopy(self.bound)
            bound[field] = "0" * 64
            with self.subTest(field=field):
                results = (verification.compare_delta(self.before, self.after, bound),
                           verification.compare_protected(self.before, self.after, bound, manifests()))
                self.assertTrue(all(r["status"] != "PASS" for r in results), results)

    def test_anonymous_singletons_stay_distinct(self):
        self.assertEqual(len({p["key"] for p in self.before["partitions"]}), 4)
        after = copy.deepcopy(self.after)
        after["partitions"][-2]["members"] += after["partitions"].pop()["members"]
        refresh(after)
        self.assertEqual(verification.compare_delta(self.before, after, self.bound)["status"], "FAIL")

    def test_comparisons_do_not_mutate_inputs(self):
        inputs = (self.before, self.after, self.bound, manifests())
        snapshot = copy.deepcopy(inputs)
        verification.compare_delta(*inputs[:3])
        verification.compare_protected(*inputs)
        self.assertEqual(inputs, snapshot)

    def test_five_independent_cases_pass_exact_and_protected(self):
        for case in ("DC-01", "DC-02", "DC-03", "DC-04", "DC-05"):
            with self.subTest(case=case):
                before, expected, bound, after = five_case(case)
                result = verification.compare_delta(before, after, bound)
                self.assertEqual(result["status"], "PASS", result)
                result = verification.compare_protected(before, after, bound, manifests())
                self.assertEqual(result["status"], "PASS", result)

    def test_e1_half_swap_is_not_a_repair(self):
        before, expected, bound, after = five_case("DC-01")
        replace_partitions(after, [{"names": ["/USB_DM", "/USB_DP"], "members": ["R7.2", "R8.2", "U1.13"]},
                                   {"names": [], "members": ["U1.14"]}])
        result = verification.compare_delta(before, after, bound)
        self.assertEqual(result["status"], "FAIL", result)
        self.assertTrue(result["missing"])
        self.assertTrue(result["unexpected"])

    def test_e2_addr_high_or_nc_and_firmware_change_fail(self):
        before, expected, bound, after = five_case("DC-02")
        gnd = next(p for p in after["partitions"] if "/GND" in p["names"])
        supply = next(p for p in after["partitions"] if "/+3V3" in p["names"])
        addr = next(p for p in gnd["members"] if p["reference"] == "U2" and p["number"] == "2")
        gnd["members"].remove(addr)
        supply["members"].append(addr)
        refresh(after)
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")
        deps = manifests()
        deps["after"]["files"][1]["sha256"] = "f" * 64
        self.assertEqual(verification.compare_protected(before, actualize(expected), bound, deps)["status"], "FAIL")

    def test_e3_residual_bypass_and_one_line_only_fail(self):
        before, expected, bound, after = five_case("DC-03")
        for pair in (("/USB_DP", "/USB_DP_CONN"), ("/USB_DM", "/USB_DM_CONN")):
            changed = copy.deepcopy(after)
            parts = [p for p in changed["partitions"] if any(name in pair for name in p["names"])]
            members = [pin["reference"] + "." + pin["number"] for p in parts for pin in p["members"]]
            replace_partitions(changed, [{"names": list(pair), "members": members}])
            self.assertEqual(verification.compare_delta(before, changed, bound)["status"], "FAIL")
        after["source_objects"].extend(copy.deepcopy([o for o in before["source_objects"] if o["kind"] == "wire"]))
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")
        self.assertEqual(verification.compare_protected(before, after, bound, manifests())["status"], "FAIL")

    def test_e3_new_component_values_footprint_assembly_and_pins_are_exact(self):
        before, expected, bound, original = five_case("DC-03")
        for field, value in (("value", "33R"), ("footprint", "wrong"), ("dnp", True),
                             ("on_board", False), ("in_bom", False), ("position_nm", [0, 0])):
            after = copy.deepcopy(original)
            next(c for c in after["components"] if c["reference"] == "R7")[field] = value
            with self.subTest(field=field):
                self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")
        for field, value in (("name", "wrong"), ("electrical_type", "power_in"), ("no_connect", True)):
            after = copy.deepcopy(original)
            next(p for p in after["pins"] if p["identity"]["reference"] == "R7")[field] = value
            with self.subTest(pin_field=field):
                self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")

    def test_dc04_and_dc05_protect_existing_reset_and_boot_components(self):
        for case, references in (("DC-04", ["SW2", "U1"]), ("DC-05", ["R3", "SW1", "U1"])):
            before, expected, bound, original = five_case(case)
            for ref in references:
                after = copy.deepcopy(original)
                next(c for c in after["components"] if c["reference"] == ref)["value"] = "damaged"
                with self.subTest(case=case, reference=ref):
                    self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")
                    self.assertEqual(verification.compare_protected(before, after, bound, manifests())["status"], "FAIL")

    def test_existing_pin_uuid_replacement_and_new_uuid_reuse_are_rejected(self):
        before, expected, bound, original = five_case("DC-03")
        after = copy.deepcopy(original)
        target = next(p for p in after["pins"] if p["identity"]["reference"] == "R7")
        target["identity"]["pin_uuid"] = before["pins"][0]["identity"]["pin_uuid"]
        self.assertNotEqual(verification.compare_delta(before, after, bound)["status"], "PASS")
        after = copy.deepcopy(original)
        old_id = copy.deepcopy(after["pins"][0]["identity"])
        after["pins"][0]["identity"]["pin_uuid"] = stable_uuid("unauthorized replacement")
        for partition in after["partitions"]:
            for i, member in enumerate(partition["members"]):
                if member == old_id:
                    partition["members"][i] = copy.deepcopy(after["pins"][0]["identity"])
        refresh(after)
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")

    def test_new_pin_cannot_reuse_uuid_from_a_removed_nested_source_object(self):
        before, expected, _, after = five_case("DC-03")
        reused = stable_uuid("old nested source object")
        wire_object = next(o for o in before["source_objects"] if o["kind"] == "wire")
        wire_object["descriptor"]["ast"].append(["metadata", ["uuid", {"string": reused}]])
        wire_object["semantic_ast_sha256"] = digest("protected", wire_object["descriptor"]["ast"])
        bound = policy(before, expected)
        target = next(p for p in after["pins"] if p["identity"]["reference"] == "R7")
        old = copy.deepcopy(target["identity"])
        target["identity"]["pin_uuid"] = reused
        for partition in after["partitions"]:
            for member in partition["members"]:
                if member == old:
                    member["pin_uuid"] = reused
        comp = next(c for c in after["components"] if c["reference"] == "R7")
        for index, obj in enumerate(after["source_objects"]):
            if obj["identity"] == comp["identity"]["component_uuid"]:
                after["source_objects"][index] = symbolic_source(comp, [p for p in after["pins"] if p["identity"]["reference"] == "R7"])
        refresh(after)
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")


class FixtureProvenanceTests(unittest.TestCase):
    def test_fixture_bytes_and_exact_manifest_set(self):
        manifest = json.loads((FIXTURES / "manifest_v1.json").read_text(encoding="utf-8"))
        declared = {entry["path"] for entry in manifest["files"]}
        actual = {p.relative_to(FIXTURES).as_posix() for p in FIXTURES.rglob("*")
                  if p.is_file() and p.name != "manifest_v1.json"}
        self.assertEqual(declared, actual)
        self.assertEqual(len(declared), 11)
        for entry in manifest["files"]:
            with self.subTest(path=entry["path"]):
                raw = (FIXTURES / entry["path"]).read_bytes()
                self.assertEqual(len(raw), entry["size_bytes"])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])


ROOT_UUID = "00000000-0000-0000-0000-000000000001"
COMP_UUID = "00000000-0000-0000-0000-000000000002"
PIN1_UUID = "00000000-0000-0000-0000-000000000003"
PIN2_UUID = "00000000-0000-0000-0000-000000000004"


def mini(extra="", symbol_extra="", library_extra=""):
    return ('''(kicad_sch (version 20231120) (generator "eeschema")
      (uuid "%s") (paper "A4")
      (lib_symbols (symbol "Device:R" (in_bom yes) (on_board yes)
        (property "Reference" "R") (property "Value" "R")
        (property "Footprint" "Resistor_SMD:R_0603_1608Metric")
        (symbol "R_0_1" (rectangle (start -1 1) (end 1 -1)))
        (symbol "R_1_1"
          (pin passive line (at 0 1 270) (length 1) (name "A") (number "1"))
          (pin passive line (at 0 -1 90) (length 1) (name "B") (number "2"))) %s))
      (sheet_instances (path "/" (page "1")))
      (symbol (lib_id "Device:R") (at 10 10 0) (unit 1)
        (uuid "%s") (pin "1" (uuid "%s")) (pin "2" (uuid "%s"))
        (property "Reference" "R1") (property "Value" "22R")
        (instances (project "mini" (path "/%s" (reference "R1") (unit 1)))) %s)
      %s)''' % (ROOT_UUID, library_extra, COMP_UUID, PIN1_UUID, PIN2_UUID,
                ROOT_UUID, symbol_extra, extra)).encode("utf-8")


def label(name, x, y, slot=10):
    return '(label "%s" (at %s %s 0) (uuid "00000000-0000-0000-0000-%012d"))' % (name, x, y, slot)


def wire(x1, y1, x2, y2, slot=20):
    return '(wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid "00000000-0000-0000-0000-%012d"))' % (x1, y1, x2, y2, slot)


def no_connect(x, y, slot=30):
    return '(no_connect (at %s %s) (uuid "00000000-0000-0000-0000-%012d"))' % (x, y, slot)


def members(obs, alias):
    result = [part for part in obs["partitions"] if alias in part["names"]]
    assert len(result) == 1, (alias, result)
    return {p["reference"] + "." + p["number"] for p in result[0]["members"]}


class SourceParserTests(unittest.TestCase):
    def observe(self, raw):
        result = verification.observe_source(raw)
        self.assertEqual(result, verification.normalize_observation(result))
        self.assertEqual(result["source_sha256"], verification.hash_bytes(raw))
        return result

    def test_complete_real_m2_including_virtual_components(self):
        raw = (Path(__file__).resolve().parents[1] / "src/hardware/m2-board/m2_board.kicad_sch").read_bytes()
        obs = self.observe(raw)
        self.assertEqual(len(obs["components"]), 23)
        self.assertEqual(len(obs["pins"]), 86)
        self.assertEqual(sum(p["no_connect"] for p in obs["pins"]), 14)
        self.assertEqual({c["reference"] for c in obs["components"] if c["lib_id"] == "power:PWR_FLAG"}, {"#FLG01", "#FLG02"})
        self.assertEqual(members(obs, "/USB_DP"), {"R7.2", "U1.14"})
        self.assertEqual(members(obs, "/USB_DM"), {"R8.2", "U1.13"})
        self.assertEqual(members(obs, "/USB_DP_CONN"), {"J1.A6", "J1.B6", "R7.1"})
        self.assertEqual(members(obs, "/USB_DM_CONN"), {"J1.A7", "J1.B7", "R8.1"})

    def test_five_prescribed_fault_sources_are_complete(self):
        for number, component_count, pin_count in [(1, 23, 86), (2, 23, 86), (3, 21, 82), (4, 22, 84), (5, 22, 84)]:
            with self.subTest(case=number):
                obs = self.observe((Path(__file__).resolve().parents[1] / ("tests/fixtures/repair_pr1/native/DC-%02d/fault.kicad_sch" % number)).read_bytes())
                self.assertEqual((len(obs["components"]), len(obs["pins"])), (component_count, pin_count))
                if number == 1:
                    self.assertEqual(members(obs, "/USB_DP"), {"R7.2", "U1.13"})
                    self.assertEqual(members(obs, "/USB_DM"), {"R8.2", "U1.14"})
                if number == 2:
                    pin = next(p for p in obs["pins"] if p["identity"]["reference"] == "U2" and p["identity"]["number"] == "2")
                    partition = next(p for p in obs["partitions"] if p["key"] == pin["partition_key"])
                    self.assertFalse(pin["no_connect"])
                    self.assertEqual((len(partition["members"]), partition["names"]), (1, []))
                if number == 3:
                    self.assertEqual(members(obs, "/USB_DP"), {"J1.A6", "J1.B6", "U1.14"})
                    aliases = next(p["names"] for p in obs["partitions"] if "/USB_DP" in p["names"])
                    self.assertEqual(aliases, ["/USB_DP", "/USB_DP_CONN"])

    def test_anonymous_pins_are_distinct_and_components_do_not_conduct(self):
        obs = self.observe(mini())
        self.assertEqual(len(obs["partitions"]), 2)
        self.assertEqual([p["names"] for p in obs["partitions"]], [[], []])
        self.assertTrue(all(len(p["members"]) == 1 for p in obs["partitions"]))
        self.assertNotEqual(obs["pins"][0]["partition_key"], obs["pins"][1]["partition_key"])
        self.assertEqual(obs["components"][0]["position_nm"], [10000000, 10000000])

    def test_explicit_nc_remains_separate_state(self):
        obs = self.observe(mini(no_connect(10, 9)))
        by_number = {p["identity"]["number"]: p for p in obs["pins"]}
        self.assertTrue(by_number["1"]["no_connect"])
        self.assertFalse(by_number["2"]["no_connect"])
        self.assertNotEqual(by_number["1"]["partition_key"], by_number["2"]["partition_key"])

    def test_straight_wire_retains_all_label_aliases(self):
        obs = self.observe(mini(label("A", 10, 9) + label("B", 10, 11, 11) + wire(10, 9, 10, 11)))
        self.assertEqual(members(obs, "/A"), {"R1.1", "R1.2"})
        self.assertEqual(obs["partitions"][0]["names"], ["/A", "/B"])

    def test_same_label_name_connects_distant_pin_anchors(self):
        obs = self.observe(mini(label("BUS", 10, 9) + label("BUS", 10, 11, 11)))
        self.assertEqual(members(obs, "/BUS"), {"R1.1", "R1.2"})

    def test_unknown_nested_metadata_is_protected(self):
        base = self.observe(mini())
        changed = self.observe(mini().replace(b'(paper "A4")', b'(paper "A4" (future_metadata (x "001") (x 001)))'))
        self.assertNotEqual(base["source_objects"], changed["source_objects"])
        paper = next(o for o in changed["source_objects"] if o["kind"] == "paper")
        self.assertIn(["future_metadata", ["x", {"string": "001"}], ["x", {"number": "1"}]], paper["descriptor"]["ast"])
        self.assertEqual(paper["semantic_ast_sha256"], verification.canonical_sha256("protected", paper["descriptor"]["ast"]))

    def test_numeric_equivalence_and_whitespace_do_not_change_semantics(self):
        raw = mini()
        changed = raw.replace(b'(at 10 10 0)', b'(at +10.000 1e1 -0.00)').replace(b'(version 20231120)', b'(version 20231120.000)')
        before, after = self.observe(raw), self.observe(changed)
        self.assertNotEqual(before["source_sha256"], after["source_sha256"])
        for field in ("components", "pins", "partitions", "source_objects", "coverage"):
            self.assertEqual(before[field], after[field], field)

    def test_string_content_is_not_numeric_normalized(self):
        a = self.observe(mini().replace(b'"22R"', b'"001"'))
        b = self.observe(mini().replace(b'"22R"', b'"1"'))
        self.assertNotEqual(a["source_objects"], b["source_objects"])
        self.assertEqual((a["components"][0]["value"], b["components"][0]["value"]), ("001", "1"))

    def test_quoted_escapes_are_lossless(self):
        obs = self.observe(mini().replace(b'(paper "A4")', br'(paper "A4" (note "a\\b\"c\nline"))'))
        paper = next(o for o in obs["source_objects"] if o["kind"] == "paper")
        self.assertIn(["note", {"string": 'a\\b"c\nline'}], paper["descriptor"]["ast"])

    def test_inexact_sub_nm_coordinates_are_rejected(self):
        with self.assertRaises(verification.ObservationError):
            verification.observe_source(mini().replace(b'(at 10 10 0)', b'(at 10.0000001 10 0)'))

    def test_duplicate_uuids_anywhere_are_rejected(self):
        for raw in [mini().replace(PIN2_UUID.encode(), PIN1_UUID.encode()), mini(label("A", 10, 9)).replace(b'00000000-0000-0000-0000-000000000010', COMP_UUID.encode()), mini().replace(PIN1_UUID.encode(), ROOT_UUID.encode())]:
            with self.subTest(raw=raw[-80:]), self.assertRaises(verification.ObservationError):
                verification.observe_source(raw)

    def test_missing_or_extra_instance_pins_are_rejected(self):
        raw = mini()
        variants = [raw.replace(('(pin "2" (uuid "%s"))' % PIN2_UUID).encode(), b''), raw.replace(b'(pin "2"', b'(pin "3"')]
        for variant in variants:
            with self.subTest(raw=variant[-80:]), self.assertRaises(verification.ObservationError):
                verification.observe_source(variant)

    def test_duplicate_library_pin_numbers_and_instance_properties_rejected(self):
        for raw in [mini().replace(b'(number "2")', b'(number "1")'), mini(symbol_extra='(property "Reference" "R2")')]:
            with self.subTest(raw=raw[-80:]), self.assertRaises(verification.ObservationError):
                verification.observe_source(raw)

    def test_unknown_electrical_root_forms_and_sheets_rejected(self):
        for extra in ['(sheet (uuid "00000000-0000-0000-0000-000000000050"))', '(bus (pts (xy 1 1) (xy 2 2)))', '(mystery_connection (pin "1"))', '(global_label "A" (at 10 9 0))']:
            with self.subTest(extra=extra), self.assertRaises(verification.ObservationError):
                verification.observe_source(mini(extra))

    def test_wrong_instance_path_or_identity_is_rejected(self):
        for before, after in [(('/' + ROOT_UUID).encode(), b'/00000000-0000-0000-0000-000000000099'), (b'(reference "R1")', b'(reference "R2")'), (b'(unit 1))))', b'(unit 2))))')]:
            with self.subTest(after=after), self.assertRaises(verification.ObservationError):
                verification.observe_source(mini().replace(before, after))

    def test_unknown_electrical_symbol_fields_rejected(self):
        with self.assertRaises(verification.ObservationError):
            verification.observe_source(mini(symbol_extra='(net_tie "1" "2")'))

    def test_orphan_label_and_nc_and_ambiguous_crossing_rejected(self):
        variants = [mini(label("ORPHAN", 50, 50)), mini(no_connect(50, 50)), mini(wire(10, 9, 10, 11) + wire(9, 10, 11, 10, 21)), mini(label("NC", 10, 9) + no_connect(10, 9))]
        for variant in variants:
            with self.subTest(raw=variant[-120:]), self.assertRaises(verification.ObservationError):
                verification.observe_source(variant)

    def test_non_straight_and_zero_length_wire_rejected(self):
        for extra in [wire(10, 9, 10, 9), wire(10, 9, 10, 11).replace('(xy 10 11)', '(xy 10 10) (xy 10 11)')]:
            with self.subTest(extra=extra), self.assertRaises(verification.ObservationError):
                verification.observe_source(mini(extra))

    def test_malformed_source_rejected(self):
        for raw in [b'', b'\xff', mini() + b')', mini()[:-1], b'(not_a_schematic)', mini() + b'(foo)', mini().replace(b'"22R"', b'"unterminated'), mini().replace(b'(at 10 10 0)', b'(at NaN 10 0)')]:
            with self.subTest(raw=raw[-80:]), self.assertRaises(verification.ObservationError):
                verification.observe_source(raw)

    def test_full_source_protection_catches_non_topological_changes(self):
        before = self.observe(mini())
        bound = policy(before, before)
        self.assertEqual(verification.compare_delta(before, before, bound)["status"], "PASS")
        self.assertEqual(verification.compare_protected(before, before, bound, manifests())["status"], "PASS")
        variants = [mini().replace(b'(paper "A4")', b'(paper "A4" (future_metadata "changed"))'),
                    mini(symbol_extra='(property "untouched-note" "changed")'),
                    mini().replace(b'(start -1 1)', b'(start -2 1)')]
        for raw in variants:
            with self.subTest(raw=raw[-60:]):
                after = self.observe(raw)
                self.assertEqual(before["partitions"], after["partitions"])
                self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")
                self.assertEqual(verification.compare_protected(before, after, bound, manifests())["status"], "FAIL")

    def test_parsed_new_component_aligns_only_its_explicit_uuid_fields(self):
        raw = mini()
        node = raw[raw.index(b'(symbol (lib_id'):raw.rfind(b')')]
        mapping = {COMP_UUID: stable_uuid("new source R2"), PIN1_UUID: stable_uuid("new source R2.1"),
                   PIN2_UUID: stable_uuid("new source R2.2")}
        for old, new in mapping.items():
            node = node.replace(old.encode(), new.encode())
        node = node.replace(b'"R1"', b'"R2"').replace(b'(at 10 10 0)', b'(at 20 10 0)')
        after_raw = raw[:raw.rfind(b')')] + node + b')'
        before, after = self.observe(raw), self.observe(after_raw)
        expected = copy.deepcopy(after)
        roles = {mapping[COMP_UUID]: "new:R2", mapping[PIN1_UUID]: "new:R2.1", mapping[PIN2_UUID]: "new:R2.2"}

        def symbolic(value):
            if isinstance(value, dict):
                return {k: roles.get(v, v) if k in ("component_uuid", "pin_uuid", "identity") and isinstance(v, str)
                        else symbolic(v) for k, v in value.items()}
            if isinstance(value, list):
                if len(value) == 2 and value[0] == "uuid":
                    return ["uuid", {"string": roles.get(value[1]["string"], value[1]["string"])}]
                return [symbolic(v) for v in value]
            return value

        expected = symbolic(expected)
        semanticize(expected)
        refresh(expected)
        bound = policy(before, expected)
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "PASS")
        self.assertEqual(verification.compare_protected(before, after, bound, manifests())["status"], "PASS")
        changed = self.observe(after_raw.replace(b'(at 20 10 0)', b'(at 21 10 0)'))
        self.assertEqual(verification.compare_delta(before, changed, bound)["status"], "FAIL")
        self.assertEqual(verification.compare_protected(before, changed, bound, manifests())["status"], "FAIL")

    def test_unqualified_transforms_versions_and_implicit_power_fail_closed(self):
        for raw in [mini().replace(b'(at 10 10 0)', b'(at 10 10 90)'), mini(symbol_extra='(mirror x)'),
                    mini().replace(b'20231120', b'20250114'), mini(library_extra='(power)'),
                    mini().replace(b'(pin passive line', b'(pin power_in line (hide yes)')]:
            with self.subTest(raw=raw[-60:]), self.assertRaises(verification.ObservationError):
                verification.observe_source(raw)



STUB_CLI = '''import json
import os
import sys
import time

args = sys.argv[1:]
source = args[-1]
output = args[args.index("--output") + 1]
name = os.path.basename(source)
folder = os.path.dirname(source)
if "slow" in name:
    time.sleep(5)
if "fail" in name:
    sys.exit(3)
if "empty" in name:
    payload = b""
elif "bad" in name:
    payload = b"<netlist"
elif os.path.exists(os.path.join(folder, "export_plan.xml")):
    with open(os.path.join(folder, "export_plan.xml"), "rb") as handle:
        payload = handle.read()
else:
    payload = b'<export version="E"><components><comp ref="R1"><pins><pin num="1"/><pin num="2"/></pins></comp></components><nets><net code="1" name="A"><node ref="R1" pin="1"/></net><net code="2" name="B"><node ref="R1" pin="2"/></net></nets></export>'
with open(output, "wb") as handle:
    handle.write(payload)
if os.path.exists(os.path.join(folder, "dump_environment")):
    with open(os.path.join(os.path.dirname(output), "env.json"), "w", encoding="utf-8") as handle:
        json.dump(dict(os.environ), handle)
if os.path.exists(os.path.join(folder, "drift_after_export")):
    with open(source, "ab") as handle:
        handle.write(b"drift")
'''


def plan_from_observation(observation):
    """TEST_ONLY netlist that agrees with one observation by construction."""
    components = {}
    for row in observation["pins"]:
        components.setdefault(row["identity"]["reference"], []).append(row["identity"]["number"])
    parts = ['<export version="E"><components>']
    for reference in sorted(components):
        pins = "".join('<pin num="%s"/>' % number for number in sorted(components[reference]))
        parts.append('<comp ref="%s"><pins>%s</pins></comp>' % (reference, pins))
    parts.append('</components><nets>')
    for index, partition in enumerate(observation["partitions"]):
        nodes = "".join('<node ref="%s" pin="%s"/>' % (member["reference"], member["number"])
                        for member in partition["members"])
        parts.append('<net code="%d" name="N%d">%s</net>' % (index + 1, index, nodes))
    parts.append('</nets></export>')
    return "".join(parts).encode("utf-8")


def _make_directory_link(target, link):
    """Create a directory junction/symlink, or return None when unavailable."""
    if sys.platform == "win32":
        completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return str(link) if completed.returncode == 0 else None
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
    except OSError:
        return None
    return str(link)


def declared_child_environment(extra=None):
    """TEST_ONLY: the explicit child environment a host has to declare.

    Production passes the declared manifest environment and nothing else, so a
    test host must name the variables the OS loader needs (SYSTEMROOT, PATH, ...)
    in the manifest -- which is the point: what the child receives is what gets
    hashed.  A child started with an empty environment does not even run on
    Windows (WinError 87).
    """
    declared = {}
    for name in ("SYSTEMROOT", "windir", "PATH", "PATHEXT", "TEMP", "TMP", "COMSPEC",
                 "HOME", "LANG", "LC_ALL", "TMPDIR", "PWD", "SHELL",
                 "USERPROFILE", "APPDATA", "LOCALAPPDATA", "NUMBER_OF_PROCESSORS"):
        if name in os.environ:
            declared[name] = os.environ[name]
    if extra:
        declared.update(extra)
    return declared


class FreshExportTests(unittest.TestCase):
    """C3 sub-items 1-2: fresh export proofs and stage/source binding.

    These tests drive a host-provided toolchain binding whose executable is a
    local stub, so they establish the software contract only: two new exports,
    three source hashes, no reuse of a leftover XML, honest proofs.  A real
    KiCad 10.0.5 run is a separate native qualification and stays NOT_RUN here.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.stub = self.root / "fake_kicad_cli.py"
        self.stub.write_text(STUB_CLI, encoding="utf-8")
        self.stub_sha = hashlib.sha256(self.stub.read_bytes()).hexdigest()
        # The frozen command runs the pinned binary itself, so the stub is
        # substituted at the process seam instead of through the schema.
        self.library = self.root / "symbols.kicad_sym"
        self.library.write_bytes(b'(kicad_symbol_lib (version 20231120) (symbol "R"))')
        self.config = self.root / "kicad_common.json"
        self.config.write_bytes(b'{"environment": {}}')
        self._seam = mock.patch.object(verification, "_spawn", self.fake_spawn)
        self._seam.start()
        self.addCleanup(self._seam.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def fake_spawn(self, argv, **kwargs):
        """TEST_ONLY process seam: run the stub where the pinned binary would run."""
        return subprocess.run([sys.executable, str(self.stub)] + list(argv[1:]), **kwargs)

    def file_manifest(self, *paths):
        rows = []
        for path in paths:
            raw = Path(path).read_bytes()
            rows.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                         "size_bytes": len(raw), "role": "READONLY_DEPENDENCY"})
        return {"version": 1, "files": rows}

    def toolchain(self, **overrides):
        manifest = {"version": 1, "kicad_cli": str(self.stub),
                    "kicad_version": "10.0.5", "kicad_cli_sha256": self.stub_sha,
                    "launcher_argv": [],
                    "arguments": list(verification.EXPORT_ARGUMENTS),
                    "timeout_seconds": 60,
                    "environment": declared_child_environment(),
                    "libraries": self.file_manifest(self.library),
                    "configs": self.file_manifest(self.config)}
        manifest.update(overrides)
        return manifest

    def source(self, name="design.kicad_sch", body=b"(kicad_sch)"):
        root = self.root / ("src_" + name.replace(".", "_"))
        root.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(body)
        return root, name

    def export(self, name="design.kicad_sch", role="BEFORE", output=None, marker=None,
               **overrides):
        root, relative = self.source(name)
        if marker:
            (root / marker).write_bytes(b"1")
        target = output or (self.root / ("out_%s_%s" % (role, name.replace(".", "_"))))
        request = {"txn_id": "txn-1", "role": role, "source_root": str(root),
                   "relative_source": relative, "output_dir": str(target),
                   "toolchain": self.toolchain(**overrides)}
        return verification.fresh_export(request)

    def test_before_and_after_exports_are_independently_proven(self):
        seen = []
        for role in ("BEFORE", "AFTER"):
            result = self.export(role=role)
            self.assertEqual(result["status"], "PASS", result["reasons"])
            proof = result["proof"]
            self.assertEqual(proof["role"], role)
            self.assertEqual(proof["exit_code"], 0)
            self.assertTrue(proof["completed"])
            self.assertEqual(proof["source_before_sha256"], proof["source_after_sha256"])
            self.assertEqual(proof["source_after_sha256"], proof["source_parse_end_sha256"])
            self.assertEqual(proof["xml_sha256"], hashlib.sha256(result["xml_bytes"]).hexdigest())
            self.assertEqual(proof["argv"][-1], str(self.root / "src_design_kicad_sch" / "design.kicad_sch"))
            self.assertEqual(proof["argv"][-2], proof["xml_path"])
            self.assertIn("netlist", proof["argv"])
            # the program that ran is the pinned binary itself, not a wrapper
            self.assertEqual(proof["argv"][0], str(self.stub))
            seen.append(proof["xml_path"])
        self.assertEqual(len(set(seen)), 2)

    def test_leftover_xml_is_never_reused_and_one_directory_serves_one_export(self):
        root, relative = self.source(name="fail.kicad_sch")
        stale = self.root / "stale_dir"
        stale.mkdir()
        (stale / "before.net.xml").write_bytes(b"<export><netlist><old /></netlist></export>")
        request = {"txn_id": "txn-1", "role": "BEFORE", "source_root": str(root),
                   "relative_source": relative, "output_dir": str(stale),
                   "toolchain": self.toolchain()}
        result = verification.fresh_export(request)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_EXPORT_STALE")
        self.assertIsNone(result["proof"])
        self.assertEqual((stale / "before.net.xml").read_bytes(),
                         b"<export><netlist><old /></netlist></export>")

        fresh = self.root / "single_use"
        first = self.export(name="design.kicad_sch", output=fresh)
        self.assertEqual(first["status"], "PASS")
        second_request = {"txn_id": "txn-1", "role": "BEFORE",
                          "source_root": str(self.root / "src_design_kicad_sch"),
                          "relative_source": "design.kicad_sch",
                          "output_dir": str(fresh), "toolchain": self.toolchain()}
        second = verification.fresh_export(second_request)
        self.assertEqual(second["status"], "BLOCKED")
        self.assertEqual(second["reasons"][0]["code"], "REPAIR_EXPORT_STALE")

    def test_failed_empty_and_broken_exports_are_not_results(self):
        for name, status, code in (("fail.kicad_sch", "TOOL_ERROR", "REPAIR_TOOL_PROTOCOL_ERROR"),
                                   ("empty.kicad_sch", "FAIL", "REPAIR_TOOL_PROTOCOL_ERROR"),
                                   ("bad.kicad_sch", "FAIL", "REPAIR_TOOL_PROTOCOL_ERROR")):
            with self.subTest(name=name):
                result = self.export(name=name)
                self.assertEqual(result["status"], status, result["reasons"])
                self.assertEqual(result["reasons"][0]["code"], code)
                self.assertFalse(result["proof"]["completed"])
                self.assertIsNone(result["xml_bytes"])

    def test_source_change_between_export_and_parse_is_not_bound(self):
        result = self.export(name="drift.kicad_sch", marker="drift_after_export")
        self.assertEqual(result["status"], "FAIL", result["reasons"])
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_SOURCE_UNBOUND")
        proof = result["proof"]
        self.assertFalse(proof["completed"])
        self.assertNotEqual(proof["source_before_sha256"], proof["source_parse_end_sha256"])

    def test_tool_version_and_argument_gaps_fail_closed(self):
        missing = self.export(name="tool_missing.kicad_sch",
                              kicad_cli=str(self.root / "missing-kicad-cli.exe"))
        self.assertEqual(missing["status"], "TOOL_ERROR")
        self.assertEqual(missing["reasons"][0]["code"], "REPAIR_TOOL_UNAVAILABLE")
        drifted = self.export(name="tool_digest.kicad_sch", kicad_cli_sha256="0" * 64)
        self.assertEqual(drifted["status"], "TOOL_ERROR")
        self.assertEqual(drifted["reasons"][0]["code"], "REPAIR_TOOL_UNAVAILABLE")
        wrong_version = self.export(name="tool_version.kicad_sch", kicad_version="9.0.0")
        self.assertEqual(wrong_version["status"], "BLOCKED")
        self.assertEqual(wrong_version["reasons"][0]["code"], "REPAIR_INPUT_DRIFT")
        wrong_arguments = self.export(name="tool_args.kicad_sch",
                                      arguments=list(verification.EXPORT_ARGUMENTS) + ["--flat"])
        self.assertEqual(wrong_arguments["status"], "BLOCKED")
        self.assertEqual(wrong_arguments["reasons"][0]["code"], "REPAIR_INPUT_DRIFT")

    def test_export_timeout_is_a_tool_error_not_a_skip(self):
        result = self.export(name="slow.kicad_sch", timeout_seconds=1)
        self.assertEqual(result["status"], "TOOL_ERROR", result["reasons"])
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_TIMEOUT")

    def test_relative_paths_cannot_escape_their_root(self):
        root, _ = self.source()
        for relative in ("../outside.kicad_sch", "/absolute.kicad_sch", "C:/outside.kicad_sch",
                         "sub/../../outside.kicad_sch"):
            with self.subTest(relative=relative):
                result = verification.fresh_export(
                    {"txn_id": "txn-1", "role": "BEFORE", "source_root": str(root),
                     "relative_source": relative, "output_dir": str(self.root / "escape_out"),
                     "toolchain": self.toolchain()})
                self.assertEqual(result["status"], "BLOCKED")
                self.assertEqual(result["reasons"][0]["code"], "REPAIR_INPUT_DRIFT")

    def test_a_transaction_id_cannot_escape_the_report_root(self):
        """The report path is built from the transaction id, so the id is a path segment.

        `_text()` accepts `../../escape` quite happily, and this id used to be joined
        straight into `report_root/exports/<txn_id>/<role>` and into the thin-verification
        file name. A non-empty string is not a safe path segment.
        """
        for txn_id in ("../../escape", "..\\..\\escape", "sub/escape", "C:/escape", ".."):
            with self.subTest(txn_id=txn_id):
                request, _ = self.scenario()
                request["txn_id"] = txn_id
                result = verification.verify_stage(request)
                self.assertEqual(result["status"], "BLOCKED", result["reasons"])
                self.assertEqual(result["reasons"][0]["code"], "REPAIR_INPUT_DRIFT")
                # nothing was created, least of all outside the declared root
                self.assertFalse((Path(request["report_root"]) / "exports").exists())
                self.assertFalse((self.root / "escape").exists())
                self.assertFalse((self.root / "escape.json").exists())

    def test_the_report_root_must_not_traverse_a_link(self):
        """A junction above the export directory redirects the whole write."""
        request, _ = self.scenario()
        reports = Path(request["report_root"])
        outside = self.root / "outside_reports"
        outside.mkdir()
        if _make_directory_link(outside, reports / "exports") is None:
            self.skipTest("directory links are not available on this platform")
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "BLOCKED", result["reasons"])
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_INPUT_DRIFT")
        self.assertEqual(list(outside.iterdir()), [])

    def test_a_kicad_cli_that_changes_during_the_export_is_a_tool_error(self):
        """The binary is digested before the run and re-checked after it."""
        real_read = verification._read_bytes
        seen = []

        def drifting(path):
            raw = real_read(path)
            if str(path) == str(self.stub):
                seen.append(path)
                if len(seen) > 1:
                    return raw + b"\n"
            return raw

        with mock.patch.object(verification, "_read_bytes", side_effect=drifting):
            result = self.export()
        self.assertGreater(len(seen), 1, "the post-run digest check never read the binary")
        self.assertEqual(result["status"], "TOOL_ERROR", result["reasons"])
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_TOOL_UNAVAILABLE")

    def bound_policy(self):
        bound = {"version": 1, "rule_id": "E1", "route": "STRICT",
                 "policy_file_sha256": "0" * 64, "authority_context_digest": "1" * 64,
                 "before_source_sha256": "2" * 64, "before_topology_sha256": "3" * 64,
                 "pin_identity_map": {}, "object_identity_map": {},
                 "captured_partitions": {}, "new_component_roles": {},
                 "expected_after": {}, "authorized_delta": [],
                 "authorized_delta_sha256": "4" * 64,
                 "protected_projection_sha256": "5" * 64,
                 "operation_constraints": {}}
        return bound, verification.canonical_sha256("policy-bound", bound)

    def manifest(self, root, name):
        raw = (root / name).read_bytes()
        return {"version": 1, "files": [{"path": name,
                                         "sha256": hashlib.sha256(raw).hexdigest(),
                                         "size_bytes": len(raw), "role": "TARGET"}]}

    def binding(self):
        snapshot = self.root / "snapshot"
        stage = self.root / "stage"
        for directory in (snapshot, stage):
            directory.mkdir(exist_ok=True)
        (snapshot / "design.kicad_sch").write_bytes(b"(kicad_sch before)")
        (stage / "design.kicad_sch").write_bytes(b"(kicad_sch after)")
        bound, digest = self.bound_policy()
        return {"txn_id": "txn-1", "run_id": "run-1", "candidate_id": "cand-1",
                "relative_target": "design.kicad_sch",
                "snapshot_root": str(snapshot), "stage_root": str(stage),
                "before_manifest": self.manifest(snapshot, "design.kicad_sch"),
                "staged_manifest": self.manifest(stage, "design.kicad_sch"),
                "bound_policy": bound, "bound_policy_sha256": digest,
                "toolchain": self.toolchain()}

    def test_bind_inputs_recomputes_manifests_policy_and_toolchain(self):
        request = self.binding()
        result = verification.bind_inputs(request)
        self.assertEqual(result["status"], "PASS", result["reasons"])
        self.assertEqual(result["staged_target"], "design.kicad_sch")
        self.assertEqual(result["toolchain_sha256"],
                         verification.canonical_sha256("toolchain", request["toolchain"]))
        self.assertEqual(sorted(result["staged_files"]), ["design.kicad_sch"])

    def test_bind_inputs_rejects_byte_policy_and_target_drift(self):
        request = self.binding()
        (self.root / "stage" / "design.kicad_sch").write_bytes(b"(kicad_sch tampered)")
        result = verification.bind_inputs(request)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_INPUT_DRIFT")
        self.assertEqual(result["reasons"][0]["stage"], "SNAPSHOT")

        request = self.binding()
        request["bound_policy_sha256"] = "0" * 64
        result = verification.bind_inputs(request)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_INPUT_DRIFT")

        request = self.binding()
        request["relative_target"] = "other.kicad_sch"
        result = verification.bind_inputs(request)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_INPUT_DRIFT")


    def design_tree(self, name, raw, plan, marker=None):
        root = self.root / name
        root.mkdir(parents=True, exist_ok=True)
        (root / "design.kicad_sch").write_bytes(raw)
        (root / "export_plan.xml").write_bytes(plan)
        if marker:
            (root / marker).write_bytes(b"1")
        return root

    def design_manifest(self, root, name="design.kicad_sch", dependencies=()):
        rows = []
        for path in (name,) + tuple(dependencies):
            raw = (root / path).read_bytes()
            rows.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest(),
                         "size_bytes": len(raw),
                         "role": "TARGET" if path == name else "READONLY_DEPENDENCY"})
        return {"version": 1, "files": rows}

    def scenario(self, stage_raw=None, stage_plan=None, stage_marker=None,
                 native_before=None, native_after=None, dependency=None,
                 **tool_overrides):
        raw = mini()
        observation = verification.observe_source(raw)
        stage_raw = raw if stage_raw is None else stage_raw
        stage_observation = verification.observe_source(stage_raw)
        snapshot = self.design_tree("snapshot_candidate", raw,
                                    plan_from_observation(observation))
        stage = self.design_tree("stage_candidate", stage_raw,
                                 plan_from_observation(stage_observation)
                                 if stage_plan is None else stage_plan,
                                 marker=stage_marker)
        dependencies = (dependency,) if dependency else ()
        for root in (snapshot, stage):
            for path in dependencies:
                (root / path).write_bytes(b"(read-only dependency bytes)")
        bound = policy(observation, copy.deepcopy(observation))
        self._scenarios = getattr(self, "_scenarios", 0) + 1
        reports = self.root / ("reports_%d" % self._scenarios)
        reports.mkdir(parents=True)
        request = {"txn_id": "txn-c3", "run_id": "run-1", "candidate_id": "cand-1",
                   "patch_sha256": "a" * 64,
                   "bound_policy_sha256": verification.canonical_sha256("policy-bound", bound),
                   "snapshot_root": str(snapshot), "stage_root": str(stage),
                   "relative_target": "design.kicad_sch",
                   "before_manifest": self.design_manifest(snapshot, dependencies=dependencies),
                   "staged_manifest": self.design_manifest(stage, dependencies=dependencies),
                   "bound_policy": bound,
                   "toolchain_manifest": self.toolchain(**tool_overrides),
                   "native_before": observation if native_before is None else native_before,
                   "native_after": stage_observation if native_after is None else native_after,
                   "report_root": str(reports)}
        return request, observation

    def test_thin_verification_passes_only_with_complete_agreement_and_authorized_delta(self):
        request, _ = self.scenario()
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "PASS", result["reasons"])
        self.assertEqual(result["scope"], "PR1_CANDIDATE_BYTES")
        self.assertEqual(sorted(result["checks"]),
                         ["exact_topology_delta", "fresh_export", "protected_diff",
                          "source_hash_binding"])
        self.assertTrue(all(check["status"] == "PASS" for check in result["checks"].values()))
        self.assertEqual({proof["role"] for proof in result["exports"]}, {"BEFORE", "AFTER"})
        self.assertTrue(all(proof["completed"] for proof in result["exports"]))
        for role in ("before", "after"):
            self.assertTrue(result["coverage"][role]["complete"])
            self.assertEqual(result["coverage"][role]["expected_pin_keys_sha256"],
                             result["coverage"][role]["observed_pin_keys_sha256"])
            self.assertEqual(result["coverage"][role]["expected_component_keys_sha256"],
                             result["coverage"][role]["observed_component_keys_sha256"])
            self.assertEqual(result["parser_agreement"][role]["status"], "PASS")
        self.assertEqual(result["authorized_delta_sha256"], result["actual_delta_sha256"])
        self.assertEqual(result["unexpected_delta"], [])
        self.assertEqual(result["missing_delta"], [])
        self.assertEqual(result["protected_changes"], [])
        self.assertTrue(result["dependencies_unchanged"])
        self.assertEqual(result["deferred"], {"erc": "NOT_RUN", "semantic_runner": "NOT_RUN",
                                              "formal_evidence": "NOT_RUN"})
        path, digest = verification.write_thin_verification(result, request["report_root"])
        self.assertTrue(path.endswith(".json"))
        self.assertEqual(len(digest), 64)
        frozen = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(frozen["status"], "PASS")
        self.assertEqual(frozen["checks"], result["checks"])
        self.assertEqual(frozen["reports"], result["reports"])

    def test_partial_or_misgrouped_exports_are_unknown_never_pass(self):
        observation = verification.observe_source(mini())
        partial = plan_from_observation(observation).replace(b'<node ref="R1" pin="2"/>', b"")
        request, _ = self.scenario(stage_plan=partial)
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "UNKNOWN", result["reasons"])
        self.assertFalse(result["coverage"]["after"]["complete"])
        self.assertEqual(result["parser_agreement"]["after"]["status"], "FAIL")
        self.assertIn("REPAIR_COVERAGE_INCOMPLETE",
                      result["parser_agreement"]["after"]["reason_codes"])
        self.assertEqual(result["checks"]["exact_topology_delta"]["status"], "NOT_RUN")
        self.assertNotEqual(result["coverage"]["after"]["expected_pin_keys_sha256"],
                            result["coverage"]["after"]["observed_pin_keys_sha256"])

        nodes = "".join('<node ref="%s" pin="%s"/>' % (row["identity"]["reference"],
                                                            row["identity"]["number"])
                        for row in observation["pins"])
        merged = ('<export version="E"><components><comp ref="R1"><pins>'
                  '<pin num="1"/><pin num="2"/></pins></comp></components>'
                  '<nets><net code="1" name="N0">%s</net></nets></export>' % nodes).encode("utf-8")
        self.assertIn(b'<node ref="R1" pin="2"/>', merged)
        request, _ = self.scenario(stage_plan=merged)
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "UNKNOWN", result["reasons"])
        self.assertTrue(result["coverage"]["after"]["complete"])
        self.assertEqual(result["parser_agreement"]["after"]["status"], "FAIL")
        self.assertIn("REPAIR_PARSER_DISAGREEMENT",
                      result["parser_agreement"]["after"]["reason_codes"])

    def test_native_misread_is_rejected_at_the_verifier(self):
        request, observation = self.scenario()
        misread = copy.deepcopy(observation)
        misread["components"][0]["value"] = "33R"
        request["native_after"] = misread
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "UNKNOWN", result["reasons"])
        self.assertEqual(result["parser_agreement"]["after"]["status"], "FAIL")
        self.assertIn("REPAIR_PARSER_DISAGREEMENT",
                      result["parser_agreement"]["after"]["reason_codes"])
        self.assertEqual(result["checks"]["exact_topology_delta"]["status"], "NOT_RUN")

    def test_unauthorized_stage_change_is_a_delta_failure(self):
        changed = mini().replace(b'(property "Value" "22R")', b'(property "Value" "33R")')
        self.assertNotEqual(changed, mini())
        request, _ = self.scenario(stage_raw=changed)
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "FAIL", result["reasons"])
        self.assertEqual(result["checks"]["exact_topology_delta"]["status"], "FAIL")
        self.assertEqual(result["checks"]["protected_diff"]["status"], "FAIL")
        self.assertTrue(result["unexpected_delta"])
        self.assertNotEqual(result["authorized_delta_sha256"], result["actual_delta_sha256"])

    def test_source_drift_during_export_blocks_and_binds_fail(self):
        request, _ = self.scenario(stage_marker="drift_after_export")
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "BLOCKED", result["reasons"])
        self.assertEqual(result["checks"]["fresh_export"]["status"], "FAIL")
        self.assertEqual(result["checks"]["source_hash_binding"]["status"], "FAIL")
        self.assertIn("REPAIR_SOURCE_UNBOUND",
                      result["checks"]["source_hash_binding"]["reason_codes"])
        self.assertEqual(result["checks"]["exact_topology_delta"]["status"], "NOT_RUN")

    def test_a_read_only_dependency_changed_during_the_exports_is_not_unchanged(self):
        """Section 9: the dependency set and content must hold from start to end.

        bind_inputs() reads the declared manifests once, before the exports.  A
        manifest comparison only proves the two declarations agree with each
        other; a read-only dependency rewritten while the exports ran used to
        leave dependencies_unchanged=true.
        """
        request, _ = self.scenario(dependency="device.lib")
        dependency = Path(request["snapshot_root"]) / "device.lib"
        real_export = verification.fresh_export

        def exporting(export_request):
            outcome = real_export(export_request)
            if export_request["role"] == "AFTER":
                dependency.write_bytes(b"tampered dependency bytes")
            return outcome

        with mock.patch.object(verification, "fresh_export", exporting):
            result = verification.verify_stage(request)
        self.assertEqual(result["status"], "BLOCKED", result["reasons"])
        self.assertIn("REPAIR_INPUT_DRIFT", [r["code"] for r in result["reasons"]])
        self.assertFalse(result["dependencies_unchanged"])

    def test_the_child_process_environment_is_exactly_the_bound_manifest(self):
        """Section 9 fixes the host-configured symbol environment, so the child
        must receive the declared map and nothing else.

        The export used to start from dict(os.environ) and then override it, so
        every ambient KICAD-*/HOME/APPDATA value reached kicad-cli while
        toolchain_sha256 covered only the declared overlay -- the same class of
        hole as a launcher, one layer down.  The stub dumps its own os.environ,
        so this observes the real child, not the caller's intention.
        """
        declared = declared_child_environment({"AEDL_DECLARED_PROBE": "bound"})
        with mock.patch.dict(os.environ, {"AEDL_UNBOUND_PROBE": "leaked"}):
            result = self.export(name="env_probe.kicad_sch", marker="dump_environment",
                                 environment=declared)
        self.assertEqual(result["status"], "PASS", result["reasons"])
        observed = json.loads((Path(result["proof"]["xml_path"]).parent
                               / "env.json").read_text(encoding="utf-8"))
        self.assertEqual(observed.get("AEDL_DECLARED_PROBE"), "bound")
        self.assertNotIn("AEDL_UNBOUND_PROBE", observed)

    def test_a_launcher_argv_is_not_part_of_the_frozen_command(self):
        """The frozen command is kicad-cli sch export netlist ..., not a wrapper.

        A non-empty launcher would make the digested kicad-cli only an argument
        to some other program, so the program that actually ran need not be the
        one that was pinned.
        """
        result = self.export(name="launcher.kicad_sch", launcher_argv=[sys.executable])
        self.assertEqual(result["status"], "BLOCKED", result["reasons"])
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_INPUT_DRIFT")

    def test_a_declared_library_that_changes_during_the_export_is_a_tool_error(self):
        """A declared symbol library is bound by bytes, not by its path string."""
        real_read = verification._read_bytes
        seen = []

        def drifting(path):
            raw = real_read(path)
            if str(path) == str(self.library):
                seen.append(path)
                if len(seen) > 1:
                    return raw + b"\n"
            return raw

        with mock.patch.object(verification, "_read_bytes", side_effect=drifting):
            result = self.export(name="lib_drift.kicad_sch")
        self.assertGreater(len(seen), 1, "the post-run library digest check never ran")
        self.assertEqual(result["status"], "TOOL_ERROR", result["reasons"])
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_TOOL_UNAVAILABLE")

    def test_a_declared_library_that_is_missing_is_not_bound(self):
        missing = {"version": 1, "files": [
            {"path": str(self.root / "missing.kicad_sym"), "sha256": "0" * 64,
             "size_bytes": 4, "role": "READONLY_DEPENDENCY"}]}
        result = self.export(name="lib_missing.kicad_sch", libraries=missing)
        self.assertEqual(result["status"], "TOOL_ERROR", result["reasons"])
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_TOOL_UNAVAILABLE")

    def test_the_export_format_of_kicad_10_0_5_is_modelled_exactly(self):
        """Pins come from net nodes; virtual power symbols stay out of both."""
        observation = circuit()
        virtual = component("#FLG01", lib_id="power:PWR_FLAG")
        flag_pin = pin(virtual, "1")
        observation["components"].append(virtual)
        observation["pins"].append(flag_pin)
        observation["source_objects"].append(
            source_object(virtual["identity"]["component_uuid"], "symbol"))
        target = next(part for part in observation["partitions"]
                      if any(member["reference"] == "R1" and member["number"] == "1"
                             for member in part["members"]))
        target["members"].append(flag_pin["identity"])
        observation = refresh(observation)

        def export_bytes(observation, drop=None):
            real = [row for row in observation["components"]
                    if not row["reference"].startswith("#")]
            parts = ['<export version="E"><components>']
            for row in real:
                parts.append('<comp ref="%s"><value>%s</value></comp>'
                             % (row["reference"], row["value"]))
            parts.append('</components><nets>')
            for index, part in enumerate(observation["partitions"]):
                members = [(member["reference"], member["number"])
                           for member in part["members"]
                           if not member["reference"].startswith("#")
                           and (member["reference"], member["number"]) != drop]
                if not members:
                    continue
                nodes = "".join('<node ref="%s" pin="%s"/>' % member for member in members)
                parts.append('<net code="%d" name="N%d">%s</net>' % (index + 1, index, nodes))
            parts.append('</nets></export>')
            return "".join(parts).encode("utf-8")

        components, nets = verification._kicad_partition(export_bytes(observation))
        coverage, agree = verification._projected_coverage(observation, components, nets)
        self.assertTrue(coverage["complete"], coverage)
        self.assertTrue(agree)
        self.assertEqual(coverage["expected_pin_count"], 4)
        self.assertEqual(coverage["observed_pin_count"], 4)
        self.assertEqual(coverage["expected_pin_keys_sha256"],
                         coverage["observed_pin_keys_sha256"])
        self.assertNotIn("#FLG01", components)

        components, nets = verification._kicad_partition(export_bytes(observation, drop=("R2", "2")))
        coverage, agree = verification._projected_coverage(observation, components, nets)
        self.assertFalse(coverage["complete"])
        self.assertFalse(agree)
        self.assertNotEqual(coverage["expected_pin_keys_sha256"],
                            coverage["observed_pin_keys_sha256"])


class NativeKiCadExportTests(unittest.TestCase):
    """C3 native qualification against the real pinned kicad-cli 10.0.5.

    Opt-in, exactly like the C4 native lane: `AEDL_PR1_NATIVE=1` plus
    `AEDL_KICAD_CLI=<absolute kicad-cli>` (the variable the frozen criteria sheet names
    in §4).  With opt-in and a missing or wrong toolchain this FAILS rather than
    skipping, so the native lane can never go green through absence.

    This class exists because the card's own limitation used to be "本机没有 kicad-cli
    10.0.5，所以真原生未跑", and it admitted that `_kicad_partition()` /
    `_projected_coverage()` had only ever been exercised against hand-built XML.
    """

    FIXTURE = os.path.join(REPO, "tests", "fixtures", "repair_pr1", "native", "DC-04",
                           "fault.kicad_sch")
    # The same binary digest the C4 native lane pins.
    PINNED_KICAD_SHA256 = "FC142E3B4C13AF868501FCBC9312DD94AD62D3C05882F97A23B6FD9F8118D0C3"

    def setUp(self):
        if os.environ.get("AEDL_PR1_NATIVE") != "1":
            self.skipTest("native qualification is not opted in (AEDL_PR1_NATIVE=1)")
        self.kicad = os.environ.get("AEDL_KICAD_CLI")
        if not self.kicad or not os.path.isfile(self.kicad):
            self.fail("AEDL_PR1_NATIVE=1 requires AEDL_KICAD_CLI to point at kicad-cli 10.0.5")
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_real_export_is_fresh_parseable_and_projects_onto_the_native_read(self):
        binary = Path(self.kicad).read_bytes()
        # The DC-04 fixture carries its symbols embedded, so there is no external
        # symbol library to bind; the empty manifests are the host's explicit
        # statement of that, not a silent omission.
        toolchain = {"version": 1, "kicad_cli": self.kicad, "kicad_version": "10.0.5",
                     "kicad_cli_sha256": hashlib.sha256(binary).hexdigest(),
                     "launcher_argv": [], "arguments": list(verification.EXPORT_ARGUMENTS),
                     "timeout_seconds": 60,
                     "environment": declared_child_environment(),
                     "libraries": {"version": 1, "files": []},
                     "configs": {"version": 1, "files": []}}
        self.assertEqual(toolchain["kicad_cli_sha256"].upper(), self.PINNED_KICAD_SHA256,
                         "the available kicad-cli is not the pinned 10.0.5 binary")
        source_root = self.root / "src"
        source_root.mkdir()
        source = source_root / "design.kicad_sch"
        shutil.copy2(self.FIXTURE, source)
        observation = verification.observe_source(source.read_bytes())

        for role in ("BEFORE", "AFTER"):
            with self.subTest(role=role):
                result = verification.fresh_export(
                    {"txn_id": "txn-native", "role": role, "source_root": str(source_root),
                     "relative_source": "design.kicad_sch",
                     "output_dir": str(self.root / "exports" / "txn-native" / role.lower()),
                     "toolchain": toolchain})
                self.assertEqual(result["status"], "PASS", result["reasons"])
                proof = result["proof"]
                self.assertEqual(proof["exit_code"], 0)
                self.assertTrue(proof["completed"])
                # three source hashes: before the export, after it, and after parsing
                self.assertEqual(proof["source_before_sha256"], proof["source_after_sha256"])
                self.assertEqual(proof["source_after_sha256"],
                                 proof["source_parse_end_sha256"])
                self.assertTrue(result["xml_bytes"])
                components, nets = verification._kicad_partition(result["xml_bytes"])
                self.assertTrue(components)
                self.assertTrue(nets)
                coverage, agree = verification._projected_coverage(observation,
                                                                   components, nets)
                self.assertTrue(agree, coverage)
                self.assertEqual(coverage["expected_pin_count"],
                                 coverage["observed_pin_count"])
                self.assertEqual(coverage["expected_pin_keys_sha256"],
                                 coverage["observed_pin_keys_sha256"])
                self.assertEqual(coverage["expected_component_keys_sha256"],
                                 coverage["observed_component_keys_sha256"])


def plan_without_one_pin(observation):
    """TEST_ONLY: the same netlist with one pin node removed (a coverage gap)."""
    text = plan_from_observation(observation).decode("utf-8")
    member = observation["partitions"][-1]["members"][-1]
    node = '<node ref="%s" pin="%s"/>' % (member["reference"], member["number"])
    if node not in text:
        raise AssertionError("the helper could not find %s to remove" % node)
    return text.replace(node, "", 1).encode("utf-8")


class C3PerturbationTests(unittest.TestCase):
    """B5 criteria sheet section C3 -- the seven C3-P1..C3-P7 perturbations.

    Each test applies one perturbation from the frozen criteria sheet to the
    real `verify_stage\u0060 boundary and asserts that the red lands **where the
    sheet names it**, and that no perturbation produces a PASS.  The C3 layer has
    no \u0060COMMITTED\u0060 status (that is the pipeline's TransactionStatus, C5), so
    "no COMMITTED" is recorded here as "no PASS result was produced" -- stated,
    not implied.

    The executable is the same host-supplied stub the FreshExportTests use, so
    these establish the software contract; the real KiCad 10.0.5 run is the
    separate opt-in NativeKiCadExportTests qualification.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.stub = self.root / "fake_kicad_cli.py"
        self.stub.write_text(STUB_CLI, encoding="utf-8")
        self.stub_sha = hashlib.sha256(self.stub.read_bytes()).hexdigest()
        self.library = self.root / "symbols.kicad_sym"
        self.library.write_bytes(b'(kicad_symbol_lib (version 20231120) (symbol "R"))')
        self.config = self.root / "kicad_common.json"
        self.config.write_bytes(b'{"environment": {}}')
        self._seam = mock.patch.object(verification, "_spawn", self.fake_spawn)
        self._seam.start()
        self.addCleanup(self._seam.stop)
        self._scenarios = 0

    def tearDown(self):
        self._tmp.cleanup()

    def fake_spawn(self, argv, **kwargs):
        """TEST_ONLY process seam: run the stub where the pinned binary would run."""
        return subprocess.run([sys.executable, str(self.stub)] + list(argv[1:]), **kwargs)

    def file_manifest(self, *paths):
        rows = []
        for path in paths:
            raw = Path(path).read_bytes()
            rows.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                         "size_bytes": len(raw), "role": "READONLY_DEPENDENCY"})
        return {"version": 1, "files": rows}

    def toolchain(self, **overrides):
        manifest = {"version": 1, "kicad_cli": str(self.stub),
                    "kicad_version": "10.0.5", "kicad_cli_sha256": self.stub_sha,
                    "launcher_argv": [],
                    "arguments": list(verification.EXPORT_ARGUMENTS),
                    "timeout_seconds": 60,
                    "environment": declared_child_environment(),
                    "libraries": self.file_manifest(self.library),
                    "configs": self.file_manifest(self.config)}
        manifest.update(overrides)
        return manifest

    def design_tree(self, name, raw, plan, marker=None):
        root = self.root / name
        root.mkdir(parents=True, exist_ok=True)
        (root / "design.kicad_sch").write_bytes(raw)
        (root / "export_plan.xml").write_bytes(plan)
        if marker:
            (root / marker).write_bytes(b"1")
        return root

    def design_manifest(self, root, name="design.kicad_sch"):
        raw = (root / name).read_bytes()
        return {"version": 1, "files": [{"path": name,
                                         "sha256": hashlib.sha256(raw).hexdigest(),
                                         "size_bytes": len(raw), "role": "TARGET"}]}

    def scenario(self, stage_raw=None, stage_plan=None, stage_marker=None,
                 native_after=None, **tool_overrides):
        raw = mini()
        observation = verification.observe_source(raw)
        stage_raw = raw if stage_raw is None else stage_raw
        stage_observation = verification.observe_source(stage_raw)
        snapshot = self.design_tree("snapshot_candidate", raw,
                                    plan_from_observation(observation))
        stage = self.design_tree("stage_candidate", stage_raw,
                                 plan_from_observation(stage_observation)
                                 if stage_plan is None else stage_plan,
                                 marker=stage_marker)
        bound = policy(observation, copy.deepcopy(observation))
        self._scenarios += 1
        reports = self.root / ("reports_%d" % self._scenarios)
        reports.mkdir(parents=True)
        request = {"txn_id": "txn-c3", "run_id": "run-1", "candidate_id": "cand-1",
                   "patch_sha256": "a" * 64,
                   "bound_policy_sha256": verification.canonical_sha256("policy-bound", bound),
                   "snapshot_root": str(snapshot), "stage_root": str(stage),
                   "relative_target": "design.kicad_sch",
                   "before_manifest": self.design_manifest(snapshot),
                   "staged_manifest": self.design_manifest(stage),
                   "bound_policy": bound,
                   "toolchain_manifest": self.toolchain(**tool_overrides),
                   "native_before": observation,
                   "native_after": stage_observation if native_after is None else native_after,
                   "report_root": str(reports)}
        return request, observation

    def assertNotPass(self, result, perturbation="C3"):
        self.assertNotEqual(result["status"], "PASS",
                            "%s produced a PASS: %r" % (perturbation, result["reasons"]))

    # -- C3-P1: the export fails, and a stale netlist must not be reused --------
    def test_p1_a_failed_export_never_falls_back_to_a_stale_netlist(self):
        request, observation = self.scenario()
        stale = Path(request["report_root"]) / "exports" / request["txn_id"] / "before"
        stale.mkdir(parents=True)
        (stale / "before.net.xml").write_bytes(plan_from_observation(observation))
        request["toolchain_manifest"] = self.toolchain(
            kicad_cli=str(self.root / "not-executable.exe"))
        result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P1")
        self.assertEqual(result["checks"]["fresh_export"]["status"], "FAIL")
        self.assertIn("REPAIR_EXPORT_STALE", result["checks"]["fresh_export"]["reason_codes"])
        self.assertEqual(result["exports"], [])
        self.assertEqual(result["coverage"], {"before": None, "after": None})

    def test_p1_a_missing_binary_is_a_tool_error_not_a_result(self):
        request, _ = self.scenario()
        request["toolchain_manifest"] = self.toolchain(kicad_cli=str(self.root / "gone.exe"))
        result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P1")
        self.assertEqual(result["checks"]["fresh_export"]["status"], "FAIL")
        self.assertIn("REPAIR_TOOL_UNAVAILABLE",
                      result["checks"]["fresh_export"]["reason_codes"])

    # -- C3-P2: exit 0 with an empty or unparseable export is not a result -----
    def test_p2_exit_zero_with_an_empty_or_broken_export_is_not_a_result(self):
        for plan in (b"", b"<netlist"):
            request, _ = self.scenario(stage_plan=plan)
            result = verification.verify_stage(request)
            self.assertNotPass(result, "C3-P2")
            self.assertEqual(result["checks"]["fresh_export"]["status"], "FAIL", plan)
            self.assertIn("REPAIR_TOOL_PROTOCOL_ERROR",
                          result["checks"]["fresh_export"]["reason_codes"], plan)
            self.assertIn(result["status"], ("FAIL", "TOOL_ERROR"), plan)

    # -- C3-P3: the stage changes between export and parse ---------------------
    def test_p3_a_stage_changed_between_export_and_parse_is_not_bound(self):
        request, _ = self.scenario(stage_marker="drift_after_export")
        result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P3")
        self.assertEqual(result["checks"]["source_hash_binding"]["status"], "FAIL")
        self.assertIn("REPAIR_SOURCE_UNBOUND",
                      result["checks"]["source_hash_binding"]["reason_codes"])
        self.assertEqual(result["status"], "BLOCKED")

    # -- C3-P4: the commit predicate, re-read after the verifier returned ------
    def test_p4_a_report_replaced_after_the_verifier_returns_is_refused(self):
        request, _ = self.scenario()
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "PASS", result["reasons"])
        clean = verification.recheck_reports(result, request["report_root"])
        self.assertEqual(clean["status"], "PASS", clean["reasons"])
        self.assertEqual(clean["checked"], 2)
        target = Path(request["report_root"]) / result["reports"]["files"][0]["path"]
        target.write_bytes(b'<export version="E"/>')
        after = verification.recheck_reports(result, request["report_root"])
        self.assertEqual(after["status"], "FAIL")
        self.assertIn("REPAIR_EXPORT_STALE", [r["code"] for r in after["reasons"]])

    def test_p4_a_staged_source_replaced_after_the_verifier_returns_is_refused(self):
        request, _ = self.scenario()
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "PASS", result["reasons"])
        (Path(request["stage_root"]) / "design.kicad_sch").write_bytes(b"(kicad_sch)")
        binding = verification.bind_inputs({key: request[key] for key in (
            "txn_id", "run_id", "candidate_id", "relative_target", "snapshot_root",
            "stage_root", "before_manifest", "staged_manifest", "bound_policy",
            "bound_policy_sha256")} | {"toolchain": request["toolchain_manifest"]})
        self.assertEqual(binding["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", [r["code"] for r in binding["reasons"]])

    # -- C3-P5: a toolchain/policy/txn binding that does not match the request --
    def test_p5_a_toolchain_that_is_not_the_pinned_kicad_is_refused(self):
        request, _ = self.scenario()
        request["toolchain_manifest"] = self.toolchain(kicad_version="10.1.0")
        result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P5")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", [r["code"] for r in result["reasons"]])
        self.assertIsNone(result["toolchain_sha256"])

    def test_p5_a_policy_binding_that_drifted_is_refused(self):
        request, _ = self.scenario()
        request["bound_policy_sha256"] = "b" * 64
        result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P5")
        self.assertIn("REPAIR_INPUT_DRIFT", [r["code"] for r in result["reasons"]])
        # the mismatch has to be readable off the receipt itself
        self.assertEqual(result["bound_policy_sha256"], "b" * 64)

    def test_p5_the_receipt_carries_the_patch_and_policy_bindings(self):
        """Section 9's anchors are only useful if the receipt actually carries them.

        Regression: _sha() validates and returns nothing, so an earlier revision
        wrote null into both fields and no mismatch could ever be read off them.
        """
        request, _ = self.scenario()
        result = verification.verify_stage(request)
        self.assertEqual(result["status"], "PASS", result["reasons"])
        self.assertEqual(result["patch_sha256"], request["patch_sha256"])
        self.assertEqual(result["bound_policy_sha256"], request["bound_policy_sha256"])
        self.assertIsNotNone(result["toolchain_sha256"])

    def test_p5_a_toolchain_digest_that_does_not_match_the_binary_is_refused(self):
        request, _ = self.scenario()
        request["toolchain_manifest"] = self.toolchain(kicad_cli_sha256="0" * 64)
        result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P5")
        self.assertEqual(result["checks"]["fresh_export"]["status"], "FAIL")
        self.assertIn("REPAIR_TOOL_UNAVAILABLE",
                      result["checks"]["fresh_export"]["reason_codes"])

    # -- C3-P6: incomplete coverage, or native/export disagreement -------------
    def test_p6_an_export_that_misses_a_pin_is_incomplete_coverage(self):
        request, _ = self.scenario()
        stage_observation = verification.observe_source(mini())
        request, _ = self.scenario(
            stage_plan=plan_without_one_pin(stage_observation))
        result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P6")
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertFalse(result["coverage"]["after"]["complete"])
        self.assertEqual(result["parser_agreement"]["after"]["status"], "FAIL")
        self.assertIn("REPAIR_COVERAGE_INCOMPLETE",
                      result["parser_agreement"]["after"]["reason_codes"])
        self.assertEqual(result["checks"]["fresh_export"]["status"], "PASS")

    def test_p6_a_native_read_that_disagrees_with_the_export_is_rejected(self):
        request, observation = self.scenario()
        misread = copy.deepcopy(observation)
        misread["components"][0]["value"] = "33R"
        request["native_after"] = misread
        result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P6")
        self.assertEqual(result["parser_agreement"]["after"]["status"], "FAIL")
        self.assertIn("REPAIR_PARSER_DISAGREEMENT",
                      result["parser_agreement"]["after"]["reason_codes"])

    # -- C3-P7: a required check left NOT_RUN, and honest deferred statuses -----
    def test_p7_a_required_check_left_not_run_is_never_pass(self):
        """Direct perturbation: everything else passes and one check is NOT_RUN.

        The earlier revision drove this through a stage-source drift, which fails
        C3-P3 first and leaves the delta checks NOT_RUN for an unrelated reason --
        a false red under criteria sheet section 1 rule 2.  Here the only
        perturbation is the required check's own outcome.
        """
        request, _ = self.scenario()
        not_run = {"status": "NOT_RUN", "actual_delta_sha256": None,
                   "unexpected": [], "missing": [], "reasons": []}
        with mock.patch.object(verification, "compare_delta", return_value=not_run):
            result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P7")
        self.assertEqual(result["checks"]["exact_topology_delta"]["status"], "NOT_RUN")
        # the other three required checks really did pass: the red is this check
        self.assertEqual(result["checks"]["fresh_export"]["status"], "PASS")
        self.assertEqual(result["checks"]["source_hash_binding"]["status"], "PASS")
        self.assertEqual(result["checks"]["protected_diff"]["status"], "PASS")
        self.assertEqual(result["status"], "FAIL")

    def test_p7_a_forged_deferred_status_is_never_pass(self):
        """Direct perturbation: deferred.erc is written PASS while all else passes.

        The PASS invariant used to read the mutable _DEFERRED mapping, so a
        forged entry agreed with itself and the receipt could carry status=PASS
        together with deferred.erc=PASS.
        """
        request, _ = self.scenario()
        with mock.patch.dict(verification._DEFERRED, {"erc": "PASS"}):
            result = verification.verify_stage(request)
        self.assertNotPass(result, "C3-P7")
        self.assertEqual(result["deferred"]["erc"], "PASS")
        self.assertEqual(result["checks"]["exact_topology_delta"]["status"], "PASS")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_p7_the_deferred_checks_are_always_not_run(self):
        request, _ = self.scenario()
        passed = verification.verify_stage(request)
        self.assertEqual(passed["status"], "PASS", passed["reasons"])
        self.assertEqual(passed["deferred"],
                         {"erc": "NOT_RUN", "semantic_runner": "NOT_RUN",
                          "formal_evidence": "NOT_RUN"})
        stalled = verification.verify_stage(self.scenario(stage_plan=b"")[0])
        self.assertNotPass(stalled, "C3-P7")
        self.assertEqual(stalled["deferred"]["erc"], "NOT_RUN")


class ErratumNewObjectTests(unittest.TestCase):
    """PR1-C5-ERRATUM R1..R12: the rev4 acceptance regression matrix.

    Every case is driven through the real compare_delta / compare_protected
    entry points (full AFTER observation -> alignment -> canonicalization),
    never through a helper unit call alone.
    """

    def case(self):
        return five_case("DC-04")

    def actual_role(self, role):
        return stable_uuid("actual:" + role)

    def new_object(self, observation, role):
        target = self.actual_role(role)
        return next(o for o in observation["source_objects"] if o["identity"] == target)

    def rehash(self, obj):
        obj["semantic_ast_sha256"] = verification.canonical_sha256(
            "protected", obj["descriptor"]["ast"])
        return obj

    def both_fail(self, before, mutated, bound):
        self.assertEqual(verification.compare_delta(before, mutated, bound)["status"], "FAIL")
        self.assertEqual(
            verification.compare_protected(before, mutated, bound, manifests())["status"], "FAIL")

    # --- R1 existing object: any unauthorized AST change ---------------------
    def test_r1_existing_object_ast_change_fails(self):
        before, expected, bound, after = self.case()
        mutated = copy.deepcopy(after)
        target = before["components"][0]["identity"]["component_uuid"]
        obj = next(o for o in mutated["source_objects"] if o["identity"] == target)
        obj["descriptor"]["ast"].append(["future_field", {"string": "changed"}])
        self.rehash(obj)
        self.both_fail(before, mutated, bound)

    # --- R2 / R3 removed object binding --------------------------------------
    def test_r2_removed_descriptor_mismatch_fails(self):
        before, expected, bound, after = five_case("DC-01")
        bound = copy.deepcopy(bound)
        key = sorted(bound["object_identity_map"])[0]
        bound["object_identity_map"][key]["descriptor_sha256"] = "0" * 64
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")

    def test_r3_removed_kind_must_match(self):
        before, expected, bound, after = five_case("DC-01")
        bound = copy.deepcopy(bound)
        key = sorted(bound["object_identity_map"])[0]
        bound["object_identity_map"][key]["kind"] = "symbol"
        self.assertEqual(verification.compare_delta(before, after, bound)["status"], "FAIL")

    # --- R4 a new object must not reuse a before UUID ------------------------
    def test_r4_new_object_must_not_reuse_a_before_uuid(self):
        before, expected, bound, after = self.case()
        reused = before["pins"][0]["identity"]["pin_uuid"]
        mutated = copy.deepcopy(after)
        self.new_object(mutated, "new:label:0")["identity"] = reused
        self.both_fail(before, mutated, bound)

    # --- R5 extra undeclared source object -----------------------------------
    def test_r5_extra_source_object_fails(self):
        before, expected, bound, after = self.case()
        mutated = copy.deepcopy(after)
        extra = stable_uuid("extra object")
        mutated["source_objects"].append(source_object(
            extra, "wire", ["wire", ["uuid", {"string": extra}]]))
        self.both_fail(before, mutated, bound)

    # --- R6 missing expected new object --------------------------------------
    def test_r6_missing_expected_new_object_fails(self):
        before, expected, bound, after = self.case()
        mutated = copy.deepcopy(after)
        target = self.actual_role("new:label:0")
        mutated["source_objects"] = [o for o in mutated["source_objects"]
                                     if o["identity"] != target]
        # A MISSING authorized addition is the delta's job (missing/unexpected).
        # compare_protected only reports unauthorized changes, so it stays PASS.
        self.assertEqual(verification.compare_delta(before, mutated, bound)["status"], "FAIL")
        self.assertEqual(
            verification.compare_protected(before, mutated, bound, manifests())["status"], "PASS")

    # --- R7 wrong new-label semantics: FAIL and never masked -----------------
    def test_r7_wrong_label_semantics_fails_and_is_not_masked(self):
        for mutation in ("name", "point", "rotation"):
            before, expected, bound, after = self.case()
            mutated = copy.deepcopy(after)
            obj = self.new_object(mutated, "new:label:0")
            node = obj["descriptor"]["ast"]
            if mutation == "name":
                node[1] = {"string": "WRONG"}
            elif mutation == "point":
                node[2][1] = {"number": "99"}
            else:
                node[2][3] = {"number": "90"}
            self.rehash(obj)
            self.assertEqual(
                verification.compare_delta(before, mutated, bound)["status"], "FAIL", mutation)
            protected = verification.compare_protected(before, mutated, bound, manifests())
            self.assertEqual(protected["status"], "FAIL", mutation)
            self.assertTrue(
                any(change["identity"] == obj["identity"] for change in protected["changes"]),
                "wrong %s must stay visible in the after projection" % mutation)

    # --- R8 ambiguous new-label semantics ------------------------------------
    def test_r8_ambiguous_label_semantics_fails(self):
        before, expected, bound, after = self.case()
        mutated = copy.deepcopy(after)
        obj = self.new_object(mutated, "new:label:0")
        twin = copy.deepcopy(obj)
        twin_role = stable_uuid("twin label")
        twin["identity"] = twin_role
        twin["descriptor"]["ast"][-1] = ["uuid", {"string": twin_role}]
        self.rehash(twin)
        mutated["source_objects"].append(twin)
        self.both_fail(before, mutated, bound)

    # --- R9 new symbol must bind to the aligned component UUID ---------------
    def test_r9_new_symbol_must_bind_to_the_component_uuid(self):
        before, expected, bound, after = self.case()
        mutated = copy.deepcopy(after)
        obj = self.new_object(mutated, "new:R9")
        obj["identity"] = stable_uuid("unbound symbol")
        self.both_fail(before, mutated, bound)
        with self.assertRaises(verification._BindingError):
            verification._canonical_new_object(
                {"identity": "new:R9", "kind": "symbol",
                 "descriptor": {"ast": ["symbol", ["uuid", {"string": "x"}]]}}, [])

    # --- R10 a mixed expected shape is never accepted ------------------------
    def test_r10_mixed_expected_shape_is_never_accepted(self):
        before, expected, bound, after = self.case()
        bound = copy.deepcopy(bound)
        obj = next(o for o in bound["expected_after"]["source_objects"]
                   if o["identity"].startswith("new:"))
        obj["descriptor"] = {"ast": ["label", ["uuid", {"string": obj["identity"]}]]}
        result = verification.compare_delta(before, after, bound)
        # A host-side schema violation is an incomplete observation, not a
        # protected diff. The security property is that it is never PASS.
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["reasons"][0]["code"], "REPAIR_COVERAGE_INCOMPLETE")

    # --- R11 new-object semantics never enter the before projection ----------
    def test_r11_new_semantics_do_not_change_the_before_projection(self):
        before, expected, bound, after = self.case()
        mutated = copy.deepcopy(bound)
        obj = next(o for o in mutated["expected_after"]["source_objects"]
                   if o["identity"] == "new:label:0")
        obj["semantics"]["name"] = "OTHER"
        self.assertEqual(verification.protected_projection_sha256(before, mutated),
                         bound["protected_projection_sha256"])

    # --- R12 new symbol must not exclude itself from simulation --------------
    def test_r12_new_symbol_exclude_from_sim_fails(self):
        before, expected, bound, after = self.case()
        mutated = copy.deepcopy(after)
        obj = self.new_object(mutated, "new:R9")
        obj["descriptor"]["ast"].append(["exclude_from_sim", "yes"])
        self.rehash(obj)
        self.both_fail(before, mutated, bound)


if __name__ == "__main__":
    unittest.main()



