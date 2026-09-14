"""PR-1 C2: complete observations and exact/protected, side-effect-free checks.

This module consumes HOST-bound expected observations. It does not load policy
files, grant permission, run tools, publish Evidence or commit candidate bytes.
C3 must independently bind fresh KiCad observations and manifests to real files.
The C1 pipeline remains on its own unmerged branch; these canonical helpers are
the contract's final home and remain byte-compatible with C1.

Local representation details: identities are closed dictionaries; deltas are
sorted lists of {section, identity, field, before, after}; absent values are
{"absent": true}. Expected new UUIDs use new:<reference> / new:<reference>.<pin>
and new:label:<slot>. Only explicit UUID fields are aligned, never arbitrary
property strings. Source descriptors retain their complete canonical AST.
"""

import copy
from decimal import Decimal, localcontext
import hashlib
import json
import os
import re
import stat
import subprocess
import uuid
import xml.etree.ElementTree as ElementTree


DIGEST_KINDS = ("manifest", "proposal", "patch", "policy-bound", "topology",
                "delta", "protected", "toolchain", "context", "receipt")
ABSENT = {"absent": True}
_COMP_ID = {"sheet_path", "component_uuid", "reference", "unit"}
_PIN_ID = _COMP_ID | {"number", "pin_uuid"}
_COMP_FIELDS = {"identity", "reference", "lib_id", "lib_definition_sha256",
                "value", "footprint", "unit", "position_nm", "rotation",
                "mirror", "dnp", "in_bom", "on_board", "pin_definition_sha256"}
_PIN_FIELDS = {"identity", "name", "electrical_type", "no_connect", "partition_key"}
_COVERAGE_FIELDS = {"expected_pin_keys_sha256", "observed_pin_keys_sha256",
                    "expected_component_keys_sha256", "observed_component_keys_sha256",
                    "expected_pin_count", "observed_pin_count", "complete"}
_BOUND_FIELDS = {"version", "rule_id", "route", "policy_file_sha256",
                 "authority_context_digest", "before_source_sha256",
                 "before_topology_sha256", "pin_identity_map", "object_identity_map",
                 "captured_partitions", "new_component_roles", "expected_after",
                 "authorized_delta", "authorized_delta_sha256",
                 "protected_projection_sha256", "operation_constraints"}
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class ObservationError(ValueError):
    """Missing, ambiguous or unsupported observation data: never a PASS."""


class _BindingError(ValueError):
    """A complete host expectation violates its frozen binding or v1 scope."""


def hash_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_json_bytes(value):
    def check(item):
        if item is None or isinstance(item, (str, bool, int)):
            return
        if isinstance(item, dict):
            if any(not isinstance(k, str) for k in item):
                raise ValueError("canonical JSON requires string keys")
            for child in item.values():
                check(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                check(child)
        else:
            raise ValueError("canonical JSON rejects non-JSON values and floats")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def canonical_sha256(kind, json_value):
    if kind not in DIGEST_KINDS:
        raise ValueError("unknown digest kind: %r" % kind)
    return hash_bytes(("AEDL-PR1:" + kind + ":1\0").encode("utf-8")
                      + canonical_json_bytes(json_value))


def _closed(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise ObservationError("%s has missing or unknown fields" % label)


def _text(value, label, empty=False):
    if not isinstance(value, str) or (not value and not empty) or any(ord(c) < 32 for c in value):
        raise ObservationError("invalid %s" % label)
    return value


def _integer(value, label, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ObservationError("invalid integer %s" % label)


def _sha(value, label):
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ObservationError("invalid digest %s" % label)


def _uuid(value, expected=False):
    if expected and isinstance(value, str) and re.fullmatch(r"new:[A-Za-z0-9_.:-]+", value):
        return
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise ObservationError("invalid or noncanonical UUID")


def _identity(value, pin=False, expected=False):
    _closed(value, _PIN_ID if pin else _COMP_ID, "identity")
    sheet = _text(value["sheet_path"], "sheet path")
    if not sheet.startswith("/") or "/" in sheet[1:]:
        raise ObservationError("only a single explicit flat sheet is supported")
    _uuid(sheet[1:])
    _uuid(value["component_uuid"], expected)
    _text(value["reference"], "reference")
    _integer(value["unit"], "unit", 1)
    if pin:
        _text(value["number"], "pin number")
        _uuid(value["pin_uuid"], expected)


def _sorted_unique(values, label):
    if not isinstance(values, list):
        raise ObservationError("%s must be a list" % label)
    ordered = sorted(values, key=canonical_json_bytes)
    keys = [canonical_json_bytes(v) for v in ordered]
    if len(set(keys)) != len(keys):
        raise ObservationError("duplicate %s" % label)
    return ordered


def _index(rows, key="identity"):
    return {canonical_json_bytes(row[key]): row for row in rows}


def normalize_observation(observation, expected=False):
    """Validate completeness and canonicalize SETS without changing source data.

    Coverage is checked against the actual identity inventory, not trusted as a
    boolean. C3 still has to establish that inventory from the source and XML.
    """
    canonical_json_bytes(observation)
    obs = copy.deepcopy(observation)
    _closed(obs, {"version", "source_sha256", "components", "pins", "partitions",
                  "source_objects", "coverage"}, "observation")
    if type(obs["version"]) is not int or obs["version"] != 1:
        raise ObservationError("unsupported observation version")
    _sha(obs["source_sha256"], "source")
    for section in ("components", "pins", "partitions", "source_objects"):
        if not isinstance(obs[section], list) or not obs[section]:
            raise ObservationError("empty or absent %s inventory" % section)
    references, component_uuids, pin_uuids, pin_numbers = set(), set(), set(), set()
    for comp in obs["components"]:
        _closed(comp, _COMP_FIELDS, "component")
        _identity(comp["identity"], expected=expected)
        ident = comp["identity"]
        if comp["reference"] != ident["reference"] or comp["unit"] != ident["unit"]:
            raise ObservationError("component identity disagrees with attributes")
        if comp["reference"] in references or ident["component_uuid"] in component_uuids:
            raise ObservationError("duplicate component reference or UUID")
        references.add(comp["reference"])
        component_uuids.add(ident["component_uuid"])
        for field in ("lib_id", "value", "footprint"):
            _text(comp[field], field, empty=field != "lib_id")
        for field in ("lib_definition_sha256", "pin_definition_sha256"):
            _sha(comp[field], field)
        if not isinstance(comp["position_nm"], list) or len(comp["position_nm"]) != 2:
            raise ObservationError("component position must be an nm pair")
        for coordinate in comp["position_nm"]:
            _integer(coordinate, "position_nm")
        _integer(comp["rotation"], "rotation")
        if comp["rotation"] not in (0, 90, 180, 270) or comp["mirror"] not in ("none", "x", "y"):
            raise ObservationError("unsupported component transform")
        for field in ("dnp", "in_bom", "on_board"):
            if type(comp[field]) is not bool:
                raise ObservationError("invalid assembly boolean")
    components = _index(obs["components"])
    seen_parents = set()
    for item in obs["pins"]:
        _closed(item, _PIN_FIELDS, "pin")
        _identity(item["identity"], pin=True, expected=expected)
        ident = item["identity"]
        parent = canonical_json_bytes({k: ident[k] for k in _COMP_ID})
        number_key = (parent, ident["number"])
        if parent not in components or number_key in pin_numbers:
            raise ObservationError("unknown pin parent or duplicate pin number")
        if ident["pin_uuid"] in pin_uuids | component_uuids:
            raise ObservationError("duplicate pin/component UUID")
        pin_numbers.add(number_key)
        pin_uuids.add(ident["pin_uuid"])
        seen_parents.add(parent)
        _text(item["name"], "pin name", empty=True)
        _text(item["electrical_type"], "pin electrical type")
        if type(item["no_connect"]) is not bool:
            raise ObservationError("NC must be an explicit boolean")
        _sha(item["partition_key"], "partition key")
    if seen_parents != set(components):
        raise ObservationError("component pin inventory missing")
    pins = _index(obs["pins"])
    covered = set()
    partition_keys = set()
    for partition in obs["partitions"]:
        _closed(partition, {"key", "members", "names"}, "partition")
        members = _sorted_unique(partition["members"], "partition members")
        if not members:
            raise ObservationError("empty partition")
        partition["members"] = members
        key = canonical_sha256("topology", members)
        if partition["key"] != key or key in partition_keys:
            raise ObservationError("partition identity mismatch or duplicate")
        partition_keys.add(key)
        names = _sorted_unique(partition["names"], "network aliases")
        for name in names:
            if not _text(name, "scoped network name").startswith("/"):
                raise ObservationError("network aliases require explicit root scope")
        partition["names"] = names
        for ident in members:
            member = canonical_json_bytes(ident)
            if member not in pins or member in covered or pins[member]["partition_key"] != key:
                raise ObservationError("partition coverage is not one-to-one")
            covered.add(member)
    if covered != set(pins):
        raise ObservationError("partition omitted a source pin")
    object_keys = set()
    for obj in obs["source_objects"]:
        _closed(obj, {"identity", "kind", "semantic_ast_sha256", "descriptor"}, "source object")
        ident = _text(obj["identity"], "source object identity")
        if ident in object_keys:
            raise ObservationError("duplicate source object")
        object_keys.add(ident)
        _text(obj["kind"], "source object kind")
        if not isinstance(obj["descriptor"], dict) or "ast" not in obj["descriptor"]:
            raise ObservationError("source object is missing its complete AST")
        if obj["semantic_ast_sha256"] != canonical_sha256("protected", obj["descriptor"]["ast"]):
            raise ObservationError("source AST hash mismatch")
    pin_ids = sorted([p["identity"] for p in obs["pins"]], key=canonical_json_bytes)
    comp_ids = sorted([c["identity"] for c in obs["components"]], key=canonical_json_bytes)
    coverage = obs["coverage"]
    _closed(coverage, _COVERAGE_FIELDS, "coverage")
    if coverage["complete"] is not True:
        raise ObservationError("incomplete source coverage")
    for field in ("expected_pin_count", "observed_pin_count"):
        _integer(coverage[field], field, 1)
        if coverage[field] != len(pin_ids):
            raise ObservationError("pin coverage count mismatch")
    for name, ids in (("pin", pin_ids), ("component", comp_ids)):
        for prefix in ("expected", "observed"):
            if coverage[prefix + "_" + name + "_keys_sha256"] != canonical_sha256("topology", ids):
                raise ObservationError("%s identity coverage mismatch" % name)
    for section in ("components", "pins", "source_objects"):
        obs[section].sort(key=lambda item: canonical_json_bytes(item["identity"]))
    obs["partitions"].sort(key=lambda item: item["key"])
    return obs


def _electrical(obs):
    return {k: v for k, v in obs.items() if k not in ("source_sha256", "coverage")}


def topology_sha256(observation):
    return canonical_sha256("topology", _electrical(normalize_observation(observation)))


def _item(section, ident, field, before, after):
    return {"section": section, "identity": ident, "field": field,
            "before": before, "after": after}


def _delta(before, after):
    changes = []
    for section in ("partitions", "components", "source_objects", "pins"):
        key = "key" if section == "partitions" else "identity"
        left, right = _index(before[section], key), _index(after[section], key)
        for ident in sorted(set(left) | set(right)):
            old, new = left.get(ident), right.get(ident)
            identity = (old or new)[key]
            if section == "partitions":
                if old != new:
                    if old is not None:
                        changes.append(_item("partitions_removed", identity, "$", old, ABSENT))
                    if new is not None:
                        changes.append(_item("partitions_added", identity, "$", ABSENT, new))
            elif section == "components":
                if old is None or new is None:
                    kind = "components_added" if old is None else "components_removed"
                    changes.append(_item(kind, identity, "$", old or ABSENT, new or ABSENT))
                else:
                    for field in sorted(_COMP_FIELDS - {"identity"}):
                        if old[field] != new[field]:
                            changes.append(_item("component_field_changes", identity, field, old[field], new[field]))
            elif section == "source_objects":
                if old != new:
                    changes.append(_item("object_changes", identity, "$", old or ABSENT, new or ABSENT))
            elif old is not None and new is not None:
                for field in ("name", "electrical_type", "no_connect"):
                    if old[field] != new[field]:
                        kind = "no_connect_changes" if field == "no_connect" else "object_changes"
                        changes.append(_item(kind, identity, "pin." + field, old[field], new[field]))
            else:
                # Membership alone cannot describe a new pin's NC/type/name.
                # Retain its complete non-derived state in the exact delta.
                old_state = {k: v for k, v in old.items() if k != "partition_key"} if old else ABSENT
                new_state = {k: v for k, v in new.items() if k != "partition_key"} if new else ABSENT
                changes.append(_item("object_changes", identity, "pin.$", old_state, new_state))
    return sorted(changes, key=canonical_json_bytes)


def observation_delta(before, after, expected=False):
    return _delta(normalize_observation(before), normalize_observation(after, expected=expected))


def _uuid_ast(value, mapping, mask=False):
    """Rewrite only explicit UUID atoms, preserving all other string contents."""
    if isinstance(value, list):
        if len(value) == 2 and value[0] == "uuid":
            atom = value[1]
            if isinstance(atom, dict) and set(atom) == {"string"}:
                raw = atom["string"]
                return ["uuid", {"string": "<UUID>" if mask else mapping.get(raw, raw)}]
        return [_uuid_ast(item, mapping, mask) for item in value]
    if isinstance(value, dict):
        return {k: _uuid_ast(v, mapping, mask) for k, v in value.items()}
    return value


def _reidentify(obs, mapping):
    out = copy.deepcopy(obs)
    for section in ("components", "pins"):
        for row in out[section]:
            for field in ("component_uuid", "pin_uuid"):
                if field in row["identity"]:
                    val = row["identity"][field]
                    row["identity"][field] = mapping.get(val, val)
    for partition in out["partitions"]:
        for ident in partition["members"]:
            for field in ("component_uuid", "pin_uuid"):
                ident[field] = mapping.get(ident[field], ident[field])
        partition["members"].sort(key=canonical_json_bytes)
        partition["key"] = canonical_sha256("topology", partition["members"])
        for pin in out["pins"]:
            if pin["identity"] in partition["members"]:
                pin["partition_key"] = partition["key"]
    for obj in out["source_objects"]:
        obj["identity"] = mapping.get(obj["identity"], obj["identity"])
        obj["descriptor"]["ast"] = _uuid_ast(obj["descriptor"]["ast"], mapping)
        obj["semantic_ast_sha256"] = canonical_sha256("protected", obj["descriptor"]["ast"])
    return out


def _align_new(before, after, expected):
    mapping = {}
    old_refs = {c["reference"] for c in before["components"]}
    after_refs = {c["reference"]: c for c in after["components"]}
    old_ids = {o["identity"] for o in before["source_objects"]}
    old_ids.update(c["identity"]["component_uuid"] for c in before["components"])
    old_ids.update(p["identity"]["pin_uuid"] for p in before["pins"])
    pending = [o["descriptor"]["ast"] for o in before["source_objects"]]
    while pending:
        node = pending.pop()
        if isinstance(node, list):
            if len(node) == 2 and node[0] == "uuid" and isinstance(node[1], dict) and set(node[1]) == {"string"}:
                old_ids.add(_text(node[1]["string"], "source UUID"))
            pending.extend(child for child in node if isinstance(child, list))
    for comp in expected["components"]:
        ref = comp["reference"]
        if ref in old_refs or ref not in after_refs:
            continue
        actual = after_refs[ref]
        actual_uuid = actual["identity"]["component_uuid"]
        if actual_uuid in old_ids:
            raise _BindingError("new component reuses a before UUID")
        mapping[actual_uuid] = comp["identity"]["component_uuid"]
        expected_pins = {p["identity"]["number"]: p for p in expected["pins"]
                         if p["identity"]["reference"] == ref}
        for pin in after["pins"]:
            ident = pin["identity"]
            if ident["reference"] == ref and ident["number"] in expected_pins:
                if ident["pin_uuid"] in old_ids:
                    raise _BindingError("new pin reuses a before UUID")
                mapping[ident["pin_uuid"]] = expected_pins[ident["number"]]["identity"]["pin_uuid"]
    # Labels have no reference. Match complete semantic descriptors with only
    # their own fresh UUID masked. More/fewer matches remain visible as deltas.
    for obj in expected["source_objects"]:
        if obj["kind"] != "label" or not obj["identity"].startswith("new:"):
            continue
        signature = _uuid_ast(obj["descriptor"], {}, mask=True)
        matches = [o for o in after["source_objects"]
                   if o["kind"] == "label" and o["identity"] not in old_ids
                   and _uuid_ast(o["descriptor"], {}, mask=True) == signature]
        if len(matches) == 1 and matches[0]["identity"] not in mapping:
            mapping[matches[0]["identity"]] = obj["identity"]
    return _reidentify(after, mapping)


def _rows(obs, section):
    if section == "pins":
        return [{k: v for k, v in p.items() if k != "partition_key"} for p in obs[section]]
    return obs[section]


def _projection(before, expected, observed, side):
    projection = {}
    for section in ("components", "pins", "partitions", "source_objects"):
        key = "key" if section == "partitions" else "identity"
        left, right = _index(_rows(before, section), key), _index(_rows(expected, section), key)
        changed = {k for k in set(left) | set(right) if left.get(k) != right.get(k)}
        allowed = left if side == "before" else right
        kept = []
        for row in _rows(observed, section):
            ident = canonical_json_bytes(row[key])
            # A changed slot is masked only when its COMPLETE descriptor is
            # exactly authorized. Wrong data at a permitted ID is still kept.
            if ident in changed and ident in allowed and row == allowed[ident]:
                continue
            kept.append(row)
        projection[section] = sorted(kept, key=canonical_json_bytes)
    return projection


def protected_projection_sha256(before, bound_policy):
    left = normalize_observation(before)
    expected = normalize_observation(bound_policy["expected_after"], expected=True)
    return canonical_sha256("protected", _projection(left, expected, left, "before"))


def _prepare(before, after, bound):
    left = normalize_observation(before)
    right = normalize_observation(after)
    _closed(bound, _BOUND_FIELDS, "bound policy")
    expected = normalize_observation(bound["expected_after"], expected=True)
    if type(bound["version"]) is not int or bound["version"] != 1:
        raise ObservationError("unsupported bound policy version")
    for field in ("policy_file_sha256", "authority_context_digest", "before_source_sha256",
                  "before_topology_sha256", "authorized_delta_sha256", "protected_projection_sha256"):
        _sha(bound[field], field)
    if bound["route"] not in ("STRICT", "CONSTRAINED_EXCEPTION"):
        raise ObservationError("unknown bound route")
    for field in ("pin_identity_map", "object_identity_map", "captured_partitions",
                  "new_component_roles", "operation_constraints"):
        if not isinstance(bound[field], dict):
            raise ObservationError("unresolved bound policy %s" % field)
    if (bound["before_source_sha256"] != left["source_sha256"] or
            bound["before_topology_sha256"] != canonical_sha256("topology", _electrical(left))):
        raise _BindingError("before observation no longer matches the host binding")
    old, new = _index(left["components"]), _index(expected["components"])
    if any(key not in new or new[key] != row for key, row in old.items()):
        raise _BindingError("v1 cannot authorize removal or mutation of an existing component")
    old_pins, new_pins = _index(_rows(left, "pins")), _index(_rows(expected, "pins"))
    if any(key not in new_pins or new_pins[key] != row for key, row in old_pins.items()):
        raise _BindingError("v1 cannot authorize existing pin or NC changes")
    added = [c for key, c in new.items() if key not in old]
    roles = bound["new_component_roles"]
    if set(roles) != {"new:" + c["reference"] for c in added}:
        raise _BindingError("new component role set does not match expected additions")
    for comp in added:
        role = "new:" + comp["reference"]
        declaration = roles[role]
        _closed(declaration, {"reference", "pin_numbers"}, "new component role")
        numbers = [p["identity"]["number"] for p in expected["pins"]
                   if p["identity"]["component_uuid"] == role]
        if (comp["identity"]["component_uuid"] != role or
                comp["lib_id"] not in ("Device:R", "Device:C") or sorted(numbers) != ["1", "2"] or
                declaration != {"reference": comp["reference"], "pin_numbers": ["1", "2"]}):
            raise _BindingError("new component role is incomplete or outside the v1 subset")
    old_objects = {o["identity"]: o for o in left["source_objects"]}
    new_objects = {o["identity"]: o for o in expected["source_objects"]}
    removed = {k: v for k, v in old_objects.items() if k not in new_objects}
    for key in set(old_objects) & set(new_objects):
        if old_objects[key] != new_objects[key]:
            raise _BindingError("existing source subtrees cannot be modified in v1")
    declarations = list(bound["object_identity_map"].values())
    for key, obj in removed.items():
        matches = [entry for entry in declarations if isinstance(entry, dict) and entry.get("uuid") == key]
        if (obj["kind"] not in ("wire", "label") or len(matches) != 1 or
                matches[0] != {"uuid": key, "kind": obj["kind"],
                               "descriptor_sha256": canonical_sha256("protected", obj["descriptor"])}):
            raise _BindingError("removed object is not exactly bound to its original descriptor")
    for key, obj in new_objects.items():
        if key not in old_objects and (obj["kind"] not in ("symbol", "label") or not key.startswith("new:")):
            raise _BindingError("expected added source object lacks a permitted symbolic role")
    # P1 role contract (2026-09-08 review): symbolic identities in
    # HostExpectedAfter must carry the exact role the contract froze, so the
    # fresh-UUID alignment chain (operation -> fresh UUID -> role -> authorized
    # delta) has no drift room.  A pin of a new component is exactly
    # "new:<reference>.<pin_number>"; a new label is exactly
    # "new:label:<slot>" with a decimal slot matching new_component_roles'
    # authorized label count.
    for pin in expected["pins"]:
        pin_uuid = pin["identity"]["pin_uuid"]
        if isinstance(pin_uuid, str) and pin_uuid.startswith("new:"):
            component_ref = pin["identity"]["reference"]
            if component_ref in {c["reference"] for c in added}:
                exact = "new:%s.%s" % (component_ref, pin["identity"]["number"])
                if pin_uuid != exact:
                    raise _BindingError(
                        "expected new pin identity %r must be the exact role %r" % (pin_uuid, exact))
    label_slots = []
    for key, obj in new_objects.items():
        if key in old_objects:
            continue
        if obj["kind"] == "label":
            m = re.fullmatch(r"new:label:([0-9]+)", key)
            if m is None:
                raise _BindingError(
                    "expected new label identity %r must be 'new:label:<decimal slot>'" % key)
            label_slots.append(int(m.group(1)))
        elif obj["kind"] == "symbol":
            # component symbolic identity already exact-checked via roles above
            pass
    if label_slots != list(range(len(label_slots))):
        raise _BindingError("new label slots must be dense decimals starting at 0")
    authorized = _delta(left, expected)
    if bound["authorized_delta"] != authorized or bound["authorized_delta_sha256"] != canonical_sha256("delta", authorized):
        raise _BindingError("authorized delta does not match the complete host expectation")
    projection = _projection(left, expected, left, "before")
    if bound["protected_projection_sha256"] != canonical_sha256("protected", projection):
        raise _BindingError("protected projection no longer matches the host binding")
    return left, _align_new(left, right, expected), expected, authorized


def _reason(code, detail):
    return {"code": code, "stage": "DELTA_CHECK", "object_id": None, "detail": detail}


def compare_delta(before, after, bound_policy):
    result = {"status": "UNKNOWN", "authorized_delta_sha256": None,
              "actual_delta_sha256": None, "missing": [], "unexpected": [],
              "coverage_complete": False, "reasons": []}
    try:
        left, right, expected, authorized = _prepare(before, after, bound_policy)
        actual = _delta(left, right)
        wanted = {canonical_json_bytes(x): x for x in authorized}
        seen = {canonical_json_bytes(x): x for x in actual}
        result.update(authorized_delta_sha256=canonical_sha256("delta", authorized),
                      actual_delta_sha256=canonical_sha256("delta", actual),
                      missing=[wanted[k] for k in sorted(set(wanted) - set(seen))],
                      unexpected=[seen[k] for k in sorted(set(seen) - set(wanted))],
                      coverage_complete=True)
        result["status"] = "FAIL" if result["missing"] or result["unexpected"] else "PASS"
        if result["status"] == "FAIL":
            result["reasons"] = [_reason("REPAIR_DELTA_MISMATCH", "actual and authorized deltas differ")]
    except _BindingError as exc:
        result.update(status="FAIL", reasons=[_reason("REPAIR_INPUT_DRIFT", str(exc))])
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        result["reasons"] = [_reason("REPAIR_COVERAGE_INCOMPLETE", str(exc))]
    return result


def _manifest(manifest):
    _closed(manifest, {"version", "files"}, "dependency manifest")
    if type(manifest["version"]) is not int or manifest["version"] != 1 or not isinstance(manifest["files"], list):
        raise ObservationError("invalid manifest version or file inventory")
    out, folded, targets = {}, set(), []
    for row in manifest["files"]:
        _closed(row, {"path", "sha256", "size_bytes", "role"}, "manifest file")
        path = _text(row["path"], "manifest path")
        parts = path.split("/")
        if any(c in path for c in '\\:<>"|?*') or any(
            p in ("", ".", "..") or p.endswith((".", " ")) or
            re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9\u00b9\u00b2\u00b3]|lpt[1-9\u00b9\u00b2\u00b3])(?:\..*)?", p)
            for p in parts
        ):
            raise ObservationError("unsafe candidate-relative manifest path")
        if path.casefold() in folded:
            raise ObservationError("case-colliding or duplicate manifest path")
        folded.add(path.casefold())
        _sha(row["sha256"], "manifest file")
        _integer(row["size_bytes"], "file size", 0)
        if row["role"] not in ("TARGET", "READONLY_DEPENDENCY"):
            raise ObservationError("unknown dependency role")
        if row["role"] == "TARGET":
            targets.append(path)
        out[path] = row
    if len(targets) != 1:
        raise ObservationError("design manifest must have exactly one target")
    return out, targets[0]


def _dependency_changes(manifests):
    _closed(manifests, {"before", "after"}, "dependency pair")
    before, left_target = _manifest(manifests["before"])
    after, right_target = _manifest(manifests["after"])
    changes = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if path == left_target == right_target:
            continue  # Target bytes may change; its exact bytes are bound in C3.
        if old != new:
            changes.append(_item("dependencies", path, "$", old or ABSENT, new or ABSENT))
    return changes


def compare_protected(before, after, bound_policy, dependency_manifests):
    result = {"status": "UNKNOWN", "before_projection_sha256": None,
              "after_projection_sha256": None, "changes": [],
              "dependencies_unchanged": False, "reasons": []}
    try:
        left, right, expected, authorized = _prepare(before, after, bound_policy)
        old_projection = _projection(left, expected, left, "before")
        new_projection = _projection(left, expected, right, "after")
        changes = []
        for section in old_projection:
            key = "key" if section == "partitions" else "identity"
            old_rows, new_rows = _index(old_projection[section], key), _index(new_projection[section], key)
            for identity in sorted(set(old_rows) | set(new_rows)):
                old, new = old_rows.get(identity), new_rows.get(identity)
                if old != new:
                    changes.append(_item(section, (old or new)[key], "$", old or ABSENT, new or ABSENT))
        dependency_changes = _dependency_changes(dependency_manifests)
        changes.extend(dependency_changes)
        result.update(status="FAIL" if changes else "PASS",
                      before_projection_sha256=canonical_sha256("protected", old_projection),
                      after_projection_sha256=canonical_sha256("protected", new_projection),
                      changes=sorted(changes, key=canonical_json_bytes),
                      dependencies_unchanged=not dependency_changes)
        if changes:
            result["reasons"] = [_reason("REPAIR_PROTECTED_DIFF", "undeclared source, topology or dependency change")]
    except _BindingError as exc:
        result.update(status="FAIL", reasons=[_reason("REPAIR_INPUT_DRIFT", str(exc))])
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        result["reasons"] = [_reason("REPAIR_COVERAGE_INCOMPLETE", str(exc))]
    return result


def _source_ast(raw):
    """Lossless semantic S-expression tree, independent of the native writer.

    Quoted strings and numeric atoms retain distinct types. Numeric formatting
    and layout whitespace are canonicalized; child order is never changed.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > 16 * 1024 * 1024:
        raise ObservationError("source must be nonempty bounded bytes")
    text = raw.decode("utf-8")
    stack, roots, i = [], [], 0
    while i < len(text):
        char = text[i]
        if char in " \t\r\n":
            i += 1
            continue
        if char == "(":
            stack.append([])
            if len(stack) > 128:
                raise ObservationError("source nesting limit exceeded")
            i += 1
            continue
        if char == ")":
            if not stack:
                raise ObservationError("unmatched closing parenthesis")
            value = stack.pop()
            if not value or not isinstance(value[0], str):
                raise ObservationError("source form lacks a keyword")
            (stack[-1] if stack else roots).append(value)
            i += 1
            continue
        if not stack:
            raise ObservationError("atom outside schematic")
        if char == '"':
            i += 1
            chars = []
            while i < len(text) and text[i] != '"':
                char = text[i]
                if char == "\\":
                    i += 1
                    escapes = {'"': '"', "\\": "\\", "n": "\n", "r": "\r", "t": "\t"}
                    if i >= len(text) or text[i] not in escapes:
                        raise ObservationError("unsupported string escape")
                    char = escapes[text[i]]
                if char == "\0":
                    raise ObservationError("NUL in source string")
                chars.append(char)
                i += 1
            if i >= len(text):
                raise ObservationError("unterminated source string")
            i += 1
            stack[-1].append({"string": "".join(chars)})
        else:
            start = i
            while i < len(text) and text[i] not in '()" \t\r\n':
                i += 1
            token = text[start:i]
            if any(ord(c) < 32 for c in token):
                raise ObservationError("invalid source atom")
            if re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", token):
                if len(token) > 4096:
                    raise ObservationError("numeric atom exceeds supported precision")
                number = Decimal(token)
                if abs(number.as_tuple().exponent) > 4096:
                    raise ObservationError("numeric atom exceeds supported exponent")
                canonical = format(number, "f")
                if "." in canonical:
                    canonical = canonical.rstrip("0").rstrip(".")
                stack[-1].append({"number": "0" if number.is_zero() else canonical})
            else:
                stack[-1].append(token)
    if stack or len(roots) != 1 or roots[0][0] != "kicad_sch":
        raise ObservationError("incomplete or non-schematic source")
    return roots[0]


def _source_children(node, name):
    return [child for child in node[1:] if isinstance(child, list) and child[0] == name]


def _source_one(node, name, required=True):
    found = _source_children(node, name)
    if len(found) > 1 or (required and not found):
        raise ObservationError("missing or duplicate %s in %s" % (name, node[0]))
    return found[0] if found else None


def _source_text(atom):
    if isinstance(atom, dict) and set(atom) == {"string"}:
        return atom["string"]
    raise ObservationError("expected a quoted source string")


def _source_value(node, name):
    child = _source_one(node, name)
    if len(child) != 2:
        raise ObservationError("invalid scalar %s" % name)
    return _source_text(child[1])


def _source_integer(atom, scale=1):
    if not isinstance(atom, dict) or set(atom) != {"number"}:
        raise ObservationError("expected an exact source number")
    with localcontext() as context:
        context.prec = max(32, len(atom["number"]) + 16)
        number = Decimal(atom["number"]) * scale
        if number != number.to_integral_value():
            raise ObservationError("source coordinate is not exactly representable in nm")
        return int(number)


def _source_at(node, name="at", rotation=True):
    child = _source_one(node, name)
    if len(child) != (4 if rotation else 3):
        raise ObservationError("unsupported %s coordinates" % name)
    point = tuple(_source_integer(x, 1000000) for x in child[1:3])
    angle = _source_integer(child[3]) if rotation else 0
    if angle not in (0, 90, 180, 270):
        raise ObservationError("unsupported source rotation")
    return point, angle


def _source_fields(node, allowed, positional=0, repeated=()):
    seen = set()
    for child in node[1 + positional:]:
        if not isinstance(child, list) or child[0] not in allowed:
            raise ObservationError("unsupported field in %s" % node[0])
        if child[0] in seen and child[0] not in repeated:
            raise ObservationError("duplicate field in %s" % node[0])
        seen.add(child[0])


def _source_properties(node):
    props = {}
    for child in _source_children(node, "property"):
        if len(child) < 3:
            raise ObservationError("incomplete source property")
        name, value = _source_text(child[1]), _source_text(child[2])
        if name in props:
            raise ObservationError("duplicate source property")
        props[name] = value
    return props


def _source_flag(node, name, default):
    child = _source_one(node, name, required=False)
    if child is None:
        return default
    if len(child) != 2 or child[1] not in ("yes", "no"):
        raise ObservationError("invalid source flag %s" % name)
    return child[1] == "yes"


def _source_uuids(root):
    pending, seen = [root], set()
    while pending:
        node = pending.pop()
        if node[0] == "uuid":
            if len(node) != 2:
                raise ObservationError("invalid UUID field")
            value = _source_text(node[1])
            _uuid(value)
            if value in seen:
                raise ObservationError("duplicate UUID anywhere in source")
            seen.add(value)
        pending.extend(c for c in node[1:] if isinstance(c, list))
    return seen


def _source_library_pins(library, unit):
    allowed = {"pin_numbers", "pin_names", "exclude_from_sim", "in_bom", "on_board",
               "in_pos_files", "duplicate_pin_numbers_are_jumpers", "property", "symbol", "power", "embedded_fonts"}
    _source_fields(library, allowed, positional=1, repeated=("property", "symbol"))
    lib_id = _source_text(library[1])
    if _source_children(library, "power") and lib_id != "power:PWR_FLAG":
        raise ObservationError("implicit power nets are outside the flat M2 subset")
    if _source_flag(library, "duplicate_pin_numbers_are_jumpers", False):
        raise ObservationError("implicit library pin jumpers are unsupported")
    _source_properties(library)
    pins = {}
    for symbol in _source_children(library, "symbol"):
        match = re.fullmatch(r".+_(\d+)_(\d+)", _source_text(symbol[1]))
        if not match or int(match[1]) not in (0, unit) or int(match[2]) not in (0, 1):
            raise ObservationError("multi-unit or alternate library body is unsupported")
        _source_fields(symbol, {"pin", "rectangle", "circle", "arc", "polyline", "text", "bezier"},
                       positional=1, repeated=("pin", "rectangle", "circle", "arc", "polyline", "text", "bezier"))
        for node in _source_children(symbol, "pin"):
            if len(node) < 3 or not isinstance(node[1], str) or not isinstance(node[2], str):
                raise ObservationError("invalid library pin type")
            _source_fields(node, {"at", "length", "name", "number", "hide"}, positional=2)
            number = _source_value(node, "number") if len(_source_one(node, "number")) == 2 else _source_text(_source_one(node, "number")[1])
            name = _source_text(_source_one(node, "name")[1])
            if not number or number in pins:
                raise ObservationError("duplicate or empty library pin number")
            point, angle = _source_at(node)
            if node[1] in ("power_in", "power_out") and _source_flag(node, "hide", False):
                raise ObservationError("hidden power pin requires unsupported implicit connectivity")
            pins[number] = {"name": name, "electrical_type": node[1], "point": point,
                            "angle": angle, "ast": node}
    if not pins:
        raise ObservationError("library has no complete pin inventory")
    return pins


def _source_components(root, sheet):
    library_root = _source_one(root, "lib_symbols")
    _source_fields(library_root, {"symbol"}, repeated=("symbol",))
    libraries = {}
    for library in library_root[1:]:
        lib_id = _source_text(library[1])
        if lib_id in libraries:
            raise ObservationError("duplicate library identity")
        libraries[lib_id] = library
    components, pins, positions = [], [], {}
    for node in _source_children(root, "symbol"):
        _source_fields(node, {"lib_id", "at", "unit", "mirror", "uuid", "pin", "property",
                              "instances", "dnp", "in_bom", "on_board", "exclude_from_sim",
                              "fields_autoplaced"}, repeated=("pin", "property"))
        lib_id = _source_value(node, "lib_id")
        if lib_id not in libraries:
            raise ObservationError("unresolved embedded symbol library")
        library = libraries[lib_id]
        props, lib_props = _source_properties(node), _source_properties(library)
        if not props.get("Reference") or "Value" not in props:
            raise ObservationError("component reference or value is missing")
        reference = props["Reference"]
        unit_node = _source_one(node, "unit")
        if len(unit_node) != 2 or _source_integer(unit_node[1]) != 1:
            raise ObservationError("only complete single-unit M2 instances are supported")
        position, rotation = _source_at(node)
        mirror = _source_one(node, "mirror", required=False)
        # The frozen M2 sources and permitted native placements use this exact
        # transform. Other transforms require separate geometry qualification.
        if rotation != 0 or mirror is not None:
            raise ObservationError("transformed instances are outside the qualified M2 subset")
        instances = _source_one(node, "instances")
        _source_fields(instances, {"project"})
        project = _source_one(instances, "project")
        _text(_source_text(project[1]), "instance project")
        _source_fields(project, {"path"}, positional=1)
        path = _source_one(project, "path")
        _source_fields(path, {"reference", "unit"}, positional=1)
        if (_source_text(path[1]) != sheet or _source_value(path, "reference") != reference or
                _source_one(path, "unit") != unit_node):
            raise ObservationError("instance path or identity disagrees with source")
        definitions = _source_library_pins(library, 1)
        instance_pins = {}
        for pin_node in _source_children(node, "pin"):
            _source_fields(pin_node, {"uuid"}, positional=1)
            number = _source_text(pin_node[1])
            if number in instance_pins:
                raise ObservationError("duplicate instance pin number")
            instance_pins[number] = _source_value(pin_node, "uuid")
        if set(instance_pins) != set(definitions):
            raise ObservationError("library and instance pin inventories differ")
        identity = {"sheet_path": sheet, "component_uuid": _source_value(node, "uuid"),
                    "reference": reference, "unit": 1}
        components.append({"identity": identity, "reference": reference, "lib_id": lib_id,
                           "lib_definition_sha256": canonical_sha256("protected", library),
                           "value": props["Value"], "footprint": props.get("Footprint", lib_props.get("Footprint", "")),
                           "unit": 1, "position_nm": list(position), "rotation": 0, "mirror": "none",
                           "dnp": _source_flag(node, "dnp", False),
                           "in_bom": _source_flag(node, "in_bom", _source_flag(library, "in_bom", True)),
                           "on_board": _source_flag(node, "on_board", _source_flag(library, "on_board", True)),
                           "pin_definition_sha256": canonical_sha256("protected", [definitions[n]["ast"] for n in sorted(definitions)])})
        for number, definition in definitions.items():
            pin_identity = dict(identity, number=number, pin_uuid=instance_pins[number])
            point = (position[0] + definition["point"][0], position[1] - definition["point"][1])
            item = {"identity": pin_identity, "name": definition["name"],
                    "electrical_type": definition["electrical_type"], "no_connect": False, "partition_key": ""}
            positions.setdefault(point, []).append(item)
            pins.append(item)
    return components, pins, positions


def _source_partitions(root, pins, positions):
    labels, wires, nc_points = [], [], set()
    for node in _source_children(root, "label"):
        _source_fields(node, {"at", "effects", "uuid", "fields_autoplaced"}, positional=1)
        name = _text(_source_text(node[1]), "label")
        point, _ = _source_at(node)
        _source_value(node, "uuid")
        labels.append((point, "/" + name))
    for node in _source_children(root, "wire"):
        _source_fields(node, {"pts", "stroke", "uuid"})
        _source_value(node, "uuid")
        pts = _source_one(node, "pts")
        if len(pts) != 3 or any(not isinstance(p, list) or p[0] != "xy" or len(p) != 3 for p in pts[1:]):
            raise ObservationError("only two-endpoint straight wires are supported")
        start, end = [tuple(_source_integer(v, 1000000) for v in p[1:]) for p in pts[1:]]
        if start == end or (start[0] != end[0] and start[1] != end[1]):
            raise ObservationError("degenerate or non-orthogonal wire is unsupported")
        wires.append((start, end))
    for node in _source_children(root, "no_connect"):
        _source_fields(node, {"at", "uuid"})
        _source_value(node, "uuid")
        point, _ = _source_at(node, rotation=False)
        if point in nc_points or len(positions.get(point, [])) != 1:
            raise ObservationError("NC must bind exactly one unique pin")
        nc_points.add(point)
        positions[point][0]["no_connect"] = True
    label_points = {p for p, _ in labels}
    wire_points = {p for wire in wires for p in wire}
    if nc_points & (label_points | wire_points):
        raise ObservationError("NC pin also has an electrical connection")
    if wire_points - set(positions) - label_points:
        raise ObservationError("wire endpoint is not a source pin or label anchor")
    if label_points - set(positions) - wire_points:
        raise ObservationError("label cannot be uniquely attributed to a pin")
    points = set(positions) | label_points
    for start, end in wires:
        for point in points - {start, end}:
            if (start[0] == end[0] == point[0] and min(start[1], end[1]) < point[1] < max(start[1], end[1]) or
                    start[1] == end[1] == point[1] and min(start[0], end[0]) < point[0] < max(start[0], end[0])):
                raise ObservationError("interior pin/label contact requires unsupported geometry")
    for index, (a, b) in enumerate(wires):
        for c, d in wires[index + 1:]:
            if {a, b} == {c, d}:
                raise ObservationError("overlapping duplicate wire")
            horizontal, vertical = ((a, b), (c, d)) if a[1] == b[1] else ((c, d), (a, b))
            h1, h2 = horizontal
            v1, v2 = vertical
            if (h1[1] == h2[1] and v1[0] == v2[0] and
                    min(h1[0], h2[0]) <= v1[0] <= max(h1[0], h2[0]) and
                    min(v1[1], v2[1]) <= h1[1] <= max(v1[1], v2[1]) and
                    not ({a, b} & {c, d})):
                raise ObservationError("ambiguous crossing without a qualified junction")
    parent = {point: point for point in points}

    def find(point):
        while parent[point] != point:
            parent[point] = parent[parent[point]]
            point = parent[point]
        return point

    def join(left, right):
        parent[find(left)] = find(right)

    for start, end in wires:
        join(start, end)
    named = {}
    for point, name in labels:
        if name in named:
            join(point, named[name])
        named[name] = point
    groups, names = {}, {}
    for point, items in positions.items():
        groups.setdefault(find(point), []).extend(items)
    for point, name in labels:
        group = find(point)
        if group not in groups:
            raise ObservationError("label/wire island has no observed pin")
        names.setdefault(group, set()).add(name)
    partitions = []
    for group, items in groups.items():
        members = sorted([p["identity"] for p in items], key=canonical_json_bytes)
        key = canonical_sha256("topology", members)
        for pin in items:
            pin["partition_key"] = key
        partitions.append({"key": key, "members": members, "names": sorted(names.get(group, []))})
    return partitions


def observe_source(raw):
    """Observe complete flat M2 source bytes, or raise ObservationError.

    This is a source observation, not a fresh KiCad export proof. Supported
    geometry is unrotated single-unit instances, pin-anchored root labels and
    straight orthogonal bypasses. Unsupported electrical forms fail closed.
    """
    try:
        root = _source_ast(raw)
        _source_fields(root, {"version", "generator", "generator_version", "uuid", "paper", "title_block",
                              "lib_symbols", "sheet_instances", "symbol", "label", "wire", "no_connect"},
                       repeated=("symbol", "label", "wire", "no_connect"))
        version = _source_one(root, "version")
        if len(version) != 2 or _source_integer(version[1]) != 20231120:
            raise ObservationError("source version is outside the qualified M2 profile")
        _source_uuids(root)
        sheet = "/" + _source_value(root, "uuid")
        sheets = _source_one(root, "sheet_instances")
        _source_fields(sheets, {"path"})
        sheet_path = _source_one(sheets, "path")
        _source_fields(sheet_path, {"page"}, positional=1)
        if _source_text(sheet_path[1]) != "/" or _source_value(sheet_path, "page") != "1":
            raise ObservationError("unknown sheet instance")
        components, pins, positions = _source_components(root, sheet)
        partitions = _source_partitions(root, pins, positions)
        objects = []
        for node in root[1:]:
            ident = _source_value(node, "uuid") if _source_children(node, "uuid") else "root:" + node[0]
            objects.append({"identity": ident, "kind": node[0],
                            "semantic_ast_sha256": canonical_sha256("protected", node), "descriptor": {"ast": node}})
        coverage = {"expected_pin_count": len(pins), "observed_pin_count": len(pins), "complete": True}
        for name, rows in (("component", components), ("pin", pins)):
            digest = canonical_sha256("topology", sorted([p["identity"] for p in rows], key=canonical_json_bytes))
            for prefix in ("expected", "observed"):
                coverage[prefix + "_" + name + "_keys_sha256"] = digest
        return normalize_observation({"version": 1, "source_sha256": hash_bytes(raw), "components": components,
                                      "pins": pins, "partitions": partitions, "source_objects": objects, "coverage": coverage})
    except (ValueError, TypeError, KeyError, IndexError, RecursionError, ArithmeticError) as exc:
        if isinstance(exc, ObservationError):
            raise
        raise ObservationError("incomplete source: %s" % exc) from exc

# ---------------------------------------------------------------------------
# C3: fresh KiCad export bound to staged bytes (contract section 9)
#
# The frozen PR-1 command is kicad-cli sch export netlist --format kicadxml.
# Every export runs in a directory this run created, with shell=false, and is
# only accepted when the process completed, exited 0, produced a non-empty
# parseable XML and the source bytes hash is identical before the export,
# after the export and after parsing.  A leftover XML is never a result.
# ---------------------------------------------------------------------------

REQUIRED_KICAD_VERSION = "10.0.5"
EXPORT_TIMEOUT_SECONDS = 60
EXPORT_ARGUMENTS = ("sch", "export", "netlist", "--format", "kicadxml", "--output")
_TOOLCHAIN_FIELDS = {"version", "kicad_cli", "kicad_version", "kicad_cli_sha256",
                     "launcher_argv", "arguments", "timeout_seconds", "environment"}
_EXPORT_REQUEST_FIELDS = {"txn_id", "role", "source_root", "relative_source",
                          "output_dir", "toolchain"}
_BINDING_REQUEST_FIELDS = {"txn_id", "run_id", "candidate_id", "relative_target",
                           "snapshot_root", "stage_root", "before_manifest",
                           "staged_manifest", "bound_policy", "bound_policy_sha256",
                           "toolchain"}
_FILE_MANIFEST_FIELDS = {"version", "files"}


class _ExportHalt(ValueError):
    """A fail-closed export outcome that must stay attributable."""

    def __init__(self, status, code, detail, proof=None):
        ValueError.__init__(self, detail)
        self.status = status
        self.code = code
        self.detail = detail
        self.proof = proof


def _reason_code(code, detail, stage="KICAD_VERIFY"):
    return {"code": code, "stage": stage, "object_id": None, "detail": detail}


def _read_bytes(path):
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise ObservationError("unreadable file: %s" % exc) from exc


def _is_link(path):
    """True for symlinks and Windows reparse points (junctions included)."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _absolute(path, label):
    text = _text(path, label)
    if not os.path.isabs(text):
        raise ObservationError("%s must be absolute" % label)
    return os.path.normpath(text)


def _resolve_within(root, relative):
    """Resolve a candidate-relative path strictly inside its declared root."""
    root_path = _absolute(root, "declared root")
    rel = _text(relative, "candidate-relative path")
    if rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        raise ObservationError("candidate-relative path must not be absolute")
    parts = rel.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ObservationError("unsafe candidate-relative path")
    if _is_link(root_path):
        raise ObservationError("the declared root must not be a link")
    cursor = root_path
    for part in parts:
        cursor = os.path.join(cursor, part)
        if os.path.exists(cursor) and _is_link(cursor):
            raise ObservationError("linked path components are not allowed")
    real_root = os.path.realpath(root_path)
    real_target = os.path.realpath(cursor)
    if os.path.commonpath([real_root, real_target]) != real_root:
        raise ObservationError("path escapes its declared root")
    return cursor


def toolchain_manifest(manifest):
    """Validate the host toolchain binding, or raise ObservationError.

    The manifest carries the absolute kicad-cli path, its digest, the pinned
    version, the frozen command arguments and the symbol/config environment.
    A missing value or a different version never proceeds silently.
    """
    _closed(manifest, _TOOLCHAIN_FIELDS, "toolchain manifest")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ObservationError("unsupported toolchain manifest version")
    executable = _text(manifest["kicad_cli"], "kicad-cli path")
    if not os.path.isabs(executable):
        raise ObservationError("the kicad-cli path must be absolute")
    if _text(manifest["kicad_version"], "kicad version") != REQUIRED_KICAD_VERSION:
        raise ObservationError("the toolchain does not pin KiCad %s" % REQUIRED_KICAD_VERSION)
    _sha(manifest["kicad_cli_sha256"], "kicad-cli digest")
    launcher = manifest["launcher_argv"]
    if not isinstance(launcher, list) or any(
            not isinstance(item, str) or not item for item in launcher):
        raise ObservationError("the launcher argv must be a list of non-empty strings")
    if any(not os.path.isabs(item) for item in launcher):
        raise ObservationError("launcher argv entries must be absolute paths")
    arguments = manifest["arguments"]
    if not isinstance(arguments, list) or tuple(arguments) != EXPORT_ARGUMENTS:
        raise ObservationError("the export arguments are not the frozen command")
    _integer(manifest["timeout_seconds"], "toolchain timeout", 1)
    if manifest["timeout_seconds"] > EXPORT_TIMEOUT_SECONDS:
        raise ObservationError("the toolchain timeout exceeds the frozen %d seconds"
                               % EXPORT_TIMEOUT_SECONDS)
    environment = manifest["environment"]
    if not isinstance(environment, dict):
        raise ObservationError("the toolchain environment must be a mapping")
    for key, value in environment.items():
        _text(key, "environment name")
        _text(value, "environment value", empty=True)
    return manifest


def fresh_export(request):
    """Run one new export and return {status, role, proof, xml_bytes, reasons}.

    Two calls of this function (role BEFORE from the snapshot root, role AFTER
    from the stage root) are what the thin verifier binds.  The proof is
    returned even when the outcome is a failure, so a receipt can show what
    actually happened; a proof never claims completion the run did not reach.
    """
    result = {"status": "TOOL_ERROR", "role": None, "proof": None, "xml_bytes": None,
              "reasons": [_reason_code("REPAIR_TOOL_PROTOCOL_ERROR",
                                       "the fresh export did not complete")]}
    try:
        _closed(request, _EXPORT_REQUEST_FIELDS, "fresh export request")
        role = _text(request["role"], "export role")
        if role not in ("BEFORE", "AFTER"):
            raise ObservationError("the export role must be BEFORE or AFTER")
        result["role"] = role
        txn_id = _text(request["txn_id"], "transaction id")
        toolchain = toolchain_manifest(request["toolchain"])
        digest = canonical_sha256("toolchain", toolchain)
        source = _resolve_within(request["source_root"], request["relative_source"])
        if not os.path.isfile(source) or _is_link(source):
            raise ObservationError("the export source is missing or a link")
        output_dir = _absolute(request["output_dir"], "export output directory")
        if os.path.exists(output_dir) or _is_link(output_dir):
            raise _ExportHalt("BLOCKED", "REPAIR_EXPORT_STALE",
                              "the export directory must be created by this run; "
                              "a leftover directory or XML is never reused")
        try:
            os.makedirs(output_dir)
        except OSError as exc:
            raise _ExportHalt("BLOCKED", "REPAIR_EXPORT_STALE",
                              "the export directory could not be created fresh: %s" % exc) from exc
        executable = toolchain["kicad_cli"]
        if not os.path.isfile(executable) or _is_link(executable):
            raise _ExportHalt("TOOL_ERROR", "REPAIR_TOOL_UNAVAILABLE",
                              "the pinned kicad-cli binary is missing")
        if hash_bytes(_read_bytes(executable)) != toolchain["kicad_cli_sha256"]:
            raise _ExportHalt("TOOL_ERROR", "REPAIR_TOOL_UNAVAILABLE",
                              "the kicad-cli binary no longer matches its pinned digest")
        xml_path = os.path.join(output_dir, role.lower() + ".net.xml")
        argv = (list(toolchain["launcher_argv"]) + [executable]
                + list(toolchain["arguments"]) + [xml_path, source])
        before = hash_bytes(_read_bytes(source))
        environment = dict(os.environ)
        environment.update(toolchain["environment"])
        try:
            completed = subprocess.run(argv, shell=False, cwd=output_dir,
                                       timeout=toolchain["timeout_seconds"],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env=environment)
        except subprocess.TimeoutExpired as exc:
            raise _ExportHalt("TOOL_ERROR", "REPAIR_TIMEOUT",
                              "the export exceeded the frozen timeout") from exc
        except OSError as exc:
            raise _ExportHalt("TOOL_ERROR", "REPAIR_TOOL_UNAVAILABLE",
                              "the export process could not start: %s" % exc) from exc
        after = hash_bytes(_read_bytes(source))
        xml_bytes = None
        if os.path.isfile(xml_path) and not _is_link(xml_path):
            xml_bytes = _read_bytes(xml_path)
        parse_end = hash_bytes(_read_bytes(source))
        parsed = False
        if xml_bytes:
            try:
                ElementTree.fromstring(xml_bytes)
                parsed = True
            except ElementTree.ParseError:
                parsed = False
        proof = {"role": role, "txn_id": txn_id, "argv": argv,
                 "exit_code": completed.returncode,
                 "source_before_sha256": before, "source_after_sha256": after,
                 "source_parse_end_sha256": parse_end, "xml_path": xml_path,
                 "xml_sha256": hash_bytes(xml_bytes) if xml_bytes else None,
                 "toolchain_sha256": digest,
                 "completed": bool(completed.returncode == 0 and parsed and
                                   before == after == parse_end)}
        result["proof"] = proof
        if before != after or after != parse_end:
            raise _ExportHalt("FAIL", "REPAIR_SOURCE_UNBOUND",
                              "the source changed while it was exported and parsed", proof)
        if completed.returncode != 0:
            raise _ExportHalt("TOOL_ERROR", "REPAIR_TOOL_PROTOCOL_ERROR",
                              "the export process exited %d" % completed.returncode, proof)
        if not xml_bytes:
            raise _ExportHalt("FAIL", "REPAIR_TOOL_PROTOCOL_ERROR",
                              "exit=0 produced no netlist file", proof)
        if not parsed:
            raise _ExportHalt("FAIL", "REPAIR_TOOL_PROTOCOL_ERROR",
                              "exit=0 produced an unparseable netlist", proof)
        result.update(status="PASS", xml_bytes=xml_bytes, reasons=[])
        return result
    except _ExportHalt as halt:
        result["status"] = halt.status
        if halt.proof is not None:
            result["proof"] = halt.proof
        result["reasons"] = [_reason_code(halt.code, halt.detail)]
        return result
    except ObservationError as exc:
        result["status"] = "BLOCKED"
        result["reasons"] = [_reason_code("REPAIR_INPUT_DRIFT",
                                          "unverifiable export input: %s" % exc)]
        return result


def _tree_digest(root, manifest, label):
    files, target = _manifest(manifest)
    observed = {}
    for path, row in sorted(files.items()):
        absolute = _resolve_within(root, path)
        if not os.path.isfile(absolute) or _is_link(absolute):
            raise _BindingError("%s file %s is missing or a link" % (label, path))
        raw = _read_bytes(absolute)
        if len(raw) != row["size_bytes"] or hash_bytes(raw) != row["sha256"]:
            raise _BindingError("%s file %s does not match its declared manifest"
                                % (label, path))
        observed[path] = {"sha256": row["sha256"], "size_bytes": row["size_bytes"],
                          "role": row["role"]}
    return observed, target


def bind_inputs(request):
    """Recompute snapshot/stage manifests, policy and toolchain bindings.

    This is the C3 "verifier first recomputes the snapshot, stage and
    dependency hashes; a mismatched input is not PASS" step.  It reads real
    bytes; it does not execute a tool and does not publish anything.
    """
    result = {"status": "BLOCKED", "txn_id": None, "before_files": None,
              "staged_files": None, "before_target": None, "staged_target": None,
              "toolchain_sha256": None, "reasons": []}
    try:
        _closed(request, _BINDING_REQUEST_FIELDS, "stage binding request")
        result["txn_id"] = _text(request["txn_id"], "transaction id")
        _text(request["run_id"], "run id")
        _text(request["candidate_id"], "candidate id")
        relative_target = _text(request["relative_target"], "target path")
        toolchain = toolchain_manifest(request["toolchain"])
        result["toolchain_sha256"] = canonical_sha256("toolchain", toolchain)
        bound = request["bound_policy"]
        _closed(bound, _BOUND_FIELDS, "bound policy")
        _sha(request["bound_policy_sha256"], "bound policy digest")
        if request["bound_policy_sha256"] != canonical_sha256("policy-bound", bound):
            raise _BindingError("the bound policy digest does not match the supplied policy")
        before_files, before_target = _tree_digest(request["snapshot_root"],
                                                   request["before_manifest"], "snapshot")
        staged_files, staged_target = _tree_digest(request["stage_root"],
                                                   request["staged_manifest"], "stage")
        if before_target != relative_target or staged_target != relative_target:
            raise _BindingError("a manifest target does not match the requested target")
        result.update(status="PASS", before_files=before_files,
                      staged_files=staged_files, before_target=before_target,
                      staged_target=staged_target)
    except _BindingError as exc:
        result["reasons"] = [_reason_code("REPAIR_INPUT_DRIFT", str(exc), "SNAPSHOT")]
    except ObservationError as exc:
        result["status"] = "UNKNOWN"
        result["reasons"] = [_reason_code("REPAIR_INPUT_DRIFT",
                                          "unverifiable binding input: %s" % exc, "SNAPSHOT")]
    return result

