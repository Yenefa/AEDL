"""PR-1 C4: pinned strict and constrained native writer adapter.

Contract: docs/competition/internal/AEDL_PR1_实现合同_20260907.md
sections 7 (route semantics), 8 (interfaces and receipts), 10 (fail-closed
states), 11 C4 (acceptance).

Three entry points, and nothing else is public:

    read_native(read_request)  -> NativeReadResult
    apply_stage(stage_request) -> StageApplyResult
    worker_main(argv)          -> exit code   # fixed READ / APPLY_EXCEPTION

Boundaries (contract section 3).  The adapter runs the pinned native tool, keeps
the real receipt and returns it.  It never builds a candidate, never grants an
exception, never writes outside the stage it was handed, and never turns a
refusal into a success.  The route is chosen by the pipeline at PRECHECK and is
only executed here: a strict refusal is never retried through the exception
writer, and an exit=6 receipt is never translated into a pass.

Route and version are fixed, not discovered:

* route must equal ROUTE_BY_RULE[policy.bound_rule_id] - E1/E2/E3 go straight to
  the constrained exception writer, DC-04/DC-05 go straight to strict.
* akcli 0.21.0, the pinned upstream commit, the installed distribution digest
  and the bound symbol digest all have to match the host toolchain manifest.

Severity normalization (implementation decision, contract section 8).  The
contract fixes the normalized vocabulary INFO/WARNING/ERROR/CRITICAL and forbids
downgrading unknown values to INFO.  The pinned akcli emits one extra documented
level, NOTE, which has no blocking meaning; it is normalized to INFO while
raw_severity is preserved on every finding.  Any other value leaves the
comparison UNKNOWN and therefore blocks.  NOTE is mapped explicitly rather than
treated as unknown so that the mapping is auditable.

Evidence boundary (this must not be read as a qualification claim).  The native
observation is assembled by the pinned reader alone, so its coverage record is
cross-checked against that reader's own component/pin summary and against the
primitive pin count: that catches a reader silently dropping objects, but it is
NOT an independent proof that nothing is missing.  Independent coverage is the
verifier's job - gates.repair_verification compares the source AST and the fresh
KiCad export against this native observation.  no_connect is not established by
either the C2 source observation or this native read in the current contract
version, so the field stays inert in comparisons and is never claimed as
attested.
"""

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import uuid

from gates.repair_verification import (canonical_json_bytes, canonical_sha256,
                                      hash_bytes, normalize_observation)


AKCLI_VERSION = "0.21.0"
AKCLI_UPSTREAM_COMMIT = "68c2df5e43db2f822ab8dbfea36f777396897d8d"
STRICT_ARGUMENTS = ("draw", "--apply", "--strict-nets", "--no-erc", "--json")
OPLIST_FLAG = "--ops"
OPLIST_PROTOCOL = 2
OPLIST_TARGET_FORMAT = "kicad"
WORKER_MODES = ("READ", "APPLY_EXCEPTION")
ROUTES = ("STRICT", "CONSTRAINED_EXCEPTION")
ROUTE_BY_RULE = {"E1": "CONSTRAINED_EXCEPTION", "E2": "CONSTRAINED_EXCEPTION",
                 "E3": "CONSTRAINED_EXCEPTION", "DC-04": "STRICT", "DC-05": "STRICT"}
CAPABILITIES = ("TOOL_EXECUTE", "FILE_WRITE")
SEVERITIES = ("INFO", "WARNING", "ERROR", "CRITICAL")
SEVERITY_ALIASES = {"INFO": "INFO", "NOTE": "INFO", "WARNING": "WARNING",
                    "ERROR": "ERROR", "CRITICAL": "CRITICAL"}
BLOCKING_SEVERITIES = ("ERROR", "CRITICAL")
NO_CONNECT_CODE = "NO_CONNECT_CONFLICT"
EXCEPTION_BACKUP_DEPTH = 1

_MAX_REQUEST_BYTES = 65536
_MAX_DEPTH = 12
_MAX_OPS = 8
_MAX_TEXT = 2048
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")

_SEVERITY_TEXT = {"INFO", "NOTE", "WARNING", "ERROR", "CRITICAL"}


class AdapterInputError(ValueError):
    """A malformed or unverifiable adapter input; never silently repaired."""


def _reason(code, detail, stage="STAGE_APPLY", object_id=None):
    return {"code": code, "stage": stage, "object_id": object_id, "detail": detail}


# ---------------------------------------------------------------------------
# closed input validation (contract section 4)
# ---------------------------------------------------------------------------

def _reject_unknown(value, fields, label):
    if not isinstance(value, dict):
        raise AdapterInputError("%s must be an object" % label)
    unknown = sorted(set(value) - set(fields))
    if unknown:
        raise AdapterInputError("%s has unknown fields: %s" % (label, ", ".join(unknown)))
    return value


def _required(value, name, label):
    if name not in value:
        raise AdapterInputError("%s is missing the required field %s" % (label, name))
    return value[name]


def _closed(value, fields, label):
    _reject_unknown(value, fields, label)
    missing = sorted(set(fields) - set(value))
    if missing:
        raise AdapterInputError("%s is missing fields: %s" % (label, ", ".join(missing)))
    return value


def _text(value, label, empty=False):
    if not isinstance(value, str) or isinstance(value, bool):
        raise AdapterInputError("%s must be a string" % label)
    if not empty and not value:
        raise AdapterInputError("%s must not be empty" % label)
    if len(value) > _MAX_TEXT:
        raise AdapterInputError("%s exceeds %d characters" % (label, _MAX_TEXT))
    if any(ord(char) < 32 for char in value):
        raise AdapterInputError("%s contains a control character" % label)
    return value


def _identifier(value, label):
    text = _text(value, label)
    if not _IDENTIFIER.match(text):
        raise AdapterInputError("%s is not a canonical identifier" % label)
    return text


def _sha(value, label):
    if not isinstance(value, str) or not _HEX.match(value):
        raise AdapterInputError("%s must be a lowercase SHA256" % label)
    return value


def _integer(value, label, minimum=None):
    if type(value) is not int:
        raise AdapterInputError("%s must be an integer" % label)
    if minimum is not None and value < minimum:
        raise AdapterInputError("%s must be at least %d" % (label, minimum))
    return value


def _load_json_file(path, label):
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise AdapterInputError("%s is unreadable: %s" % (label, exc)) from exc
    return parse_json_bytes(raw, label)


def parse_json_bytes(raw, label):
    """Closed JSON: duplicate keys, NaN/Infinity and over-deep nesting are refused."""
    if not isinstance(raw, (bytes, bytearray)):
        raise AdapterInputError("%s must be bytes" % label)
    if len(raw) > _MAX_REQUEST_BYTES:
        raise AdapterInputError("%s exceeds %d bytes" % (label, _MAX_REQUEST_BYTES))
    text = raw.decode("utf-8")

    def pairs(items):
        seen = set()
        for key, _value in items:
            if key in seen:
                raise AdapterInputError("%s repeats the key %r" % (label, key))
            seen.add(key)
        return dict(items)

    def constant(name):
        raise AdapterInputError("%s carries the non-finite constant %s" % (label, name))

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except AdapterInputError:
        raise
    except ValueError as exc:
        raise AdapterInputError("%s is not valid JSON: %s" % (label, exc)) from exc
    _check_depth(value, label)
    return value


def _check_depth(value, label, depth=0):
    if depth > _MAX_DEPTH:
        raise AdapterInputError("%s exceeds the maximum nesting depth" % label)
    if isinstance(value, dict):
        for key, item in value.items():
            _text(str(key), "JSON key", empty=True)
            _check_depth(item, label, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_depth(item, label, depth + 1)


def _absolute(path, label):
    text = _text(path, label)
    if not os.path.isabs(text):
        raise AdapterInputError("%s must be absolute" % label)
    return os.path.normpath(text)


def _is_link(path):
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _resolve_within(root, relative):
    root = _absolute(root, "declared root")
    rel = _text(relative, "relative path")
    if rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        raise AdapterInputError("the relative path must not be absolute")
    parts = rel.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise AdapterInputError("unsafe relative path %r" % rel)
    if _is_link(root):
        raise AdapterInputError("the declared root must not be a link")
    cursor = root
    for part in parts:
        cursor = os.path.join(cursor, part)
        if os.path.exists(cursor) and _is_link(cursor):
            raise AdapterInputError("linked path components are not allowed")
    if _common_root(os.path.realpath(root), os.path.realpath(cursor),
                    "the resolved path") != os.path.realpath(root):
        raise AdapterInputError("the path escapes its declared root")
    return cursor


def _common_root(left, right, label):
    """os.path.commonpath, but a cross-drive pair is an input error, not a crash."""
    try:
        return os.path.commonpath([left, right])
    except ValueError as exc:
        raise AdapterInputError("%s cannot be compared with the declared root: %s"
                                % (label, exc)) from exc


def _has_linked_component(path):
    """True when the path itself or any existing component is a link/reparse point."""
    text = os.path.normpath(path)
    parts = text.replace("\\", "/").split("/")
    if parts and re.match(r"^[A-Za-z]:$", parts[0]):
        cursor = parts[0] + os.sep
        parts = parts[1:]
    else:
        cursor = os.sep
        parts = text.split(os.sep)
    for part in parts:
        if not part:
            continue
        cursor = os.path.join(cursor, part)
        if os.path.exists(cursor) and _is_link(cursor):
            return True
    return False


def _existing_file(path, label):
    if not os.path.isfile(path) or _is_link(path):
        raise AdapterInputError("%s is missing or a link" % label)
    return path


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# toolchain binding (contract sections 7 and 11 C4)
# ---------------------------------------------------------------------------

_TOOLCHAIN_FIELDS = {"version", "akcli_executable", "akcli_version",
                     "akcli_artifact_sha256", "akcli_upstream_commit",
                     "worker_python", "symbol_digest", "launcher_argv",
                     "timeout_seconds", "environment"}
_MAX_TIMEOUT_SECONDS = 60


def toolchain_manifest(manifest):
    """Validate the host toolchain binding, or raise AdapterInputError."""
    _closed(manifest, _TOOLCHAIN_FIELDS, "toolchain manifest")
    _integer(manifest["version"], "toolchain version", 1)
    if manifest["version"] != 1:
        raise AdapterInputError("unsupported toolchain manifest version")
    _absolute(manifest["akcli_executable"], "akcli executable")
    if manifest["akcli_version"] != AKCLI_VERSION:
        raise AdapterInputError("the toolchain does not pin akcli %s" % AKCLI_VERSION)
    _sha(manifest["akcli_artifact_sha256"], "akcli distribution digest")
    if manifest["akcli_upstream_commit"] != AKCLI_UPSTREAM_COMMIT:
        raise AdapterInputError("the toolchain does not pin the akcli upstream commit")
    _absolute(manifest["worker_python"], "worker interpreter")
    _sha(manifest["symbol_digest"], "symbol digest")
    launcher = manifest["launcher_argv"]
    if not isinstance(launcher, list) or any(
            not isinstance(item, str) or not item or not os.path.isabs(item) for item in launcher):
        raise AdapterInputError("the launcher argv must be a list of absolute paths")
    _integer(manifest["timeout_seconds"], "toolchain timeout", 1)
    if manifest["timeout_seconds"] > _MAX_TIMEOUT_SECONDS:
        raise AdapterInputError("the toolchain timeout exceeds the frozen %d seconds"
                                % _MAX_TIMEOUT_SECONDS)
    environment = manifest["environment"]
    if not isinstance(environment, dict):
        raise AdapterInputError("the toolchain environment must be a mapping")
    for key, value in environment.items():
        _text(key, "environment name")
        _text(value, "environment value", empty=True)
    return manifest


def _toolchain_digest(manifest):
    return canonical_sha256("toolchain", manifest)


# ---------------------------------------------------------------------------
# findings and connectivity (contract section 8)
# ---------------------------------------------------------------------------

def normalize_connectivity(rows, label="connectivity findings"):
    """Normalize severity and keep the raw receipt.

    Returns (findings, status).  Unknown severities are never downgraded: they
    make the comparison indeterminate and therefore block.
    """
    if rows is None:
        return [], "OK"
    if not isinstance(rows, list):
        raise AdapterInputError("%s must be a list" % label)
    findings, indeterminate = [], False
    for row in rows:
        if not isinstance(row, dict):
            raise AdapterInputError("%s rows must be objects" % label)
        code = row.get("code") or row.get("kind") or "UNKNOWN_FINDING"
        raw = str(row.get("severity", "")).split(".")[-1].upper()
        message = str(row.get("message", ""))[: _MAX_TEXT]
        object_id = row.get("object_id")
        if object_id is None and row.get("refs"):
            refs = row.get("refs")
            object_id = refs[0] if isinstance(refs, list) and refs else refs
        normalized = SEVERITY_ALIASES.get(raw)
        if normalized is None:
            indeterminate = True
            normalized = "UNKNOWN"
        findings.append({"code": str(code), "severity": normalized,
                         "raw_severity": raw, "message": message,
                         "object_id": None if object_id is None else str(object_id)})
    findings.sort(key=lambda item: (item["code"], item["severity"], item["message"]))
    return findings, ("UNKNOWN" if indeterminate else "OK")


def _finding_keys(findings):
    return {(row["code"], str(row["object_id"])) for row in findings
            if row["severity"] in ("WARNING", "ERROR", "CRITICAL")}


def connectivity_verdict(before, after, background=None):
    """(status, reasons) for the fresh before/after connectivity comparison.

    after is a fresh native read, never a writer receipt.  A WARNING is tolerated
    only when the host froze that exact (code, object) pair as background; the
    frozen set is empty in this contract version, so every WARNING blocks.
    """
    frozen = _BACKGROUND_WARNINGS if background is None else frozenset(background)
    reasons = []
    if any(row["severity"] == "UNKNOWN" for row in after):
        return "UNKNOWN", [_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                   "the fresh read reported a connectivity severity this adapter "
                                   "cannot normalize")]
    if any(row["severity"] in BLOCKING_SEVERITIES for row in after):
        reasons.append(_reason("REPAIR_EFFECT_MISMATCH",
                               "the fresh read produced an ERROR/CRITICAL connectivity finding"))
    if any(row["code"] == NO_CONNECT_CODE for row in after):
        reasons.append(_reason("REPAIR_EFFECT_MISMATCH",
                               "the fresh read produced a %s finding" % NO_CONNECT_CODE))
    known = _finding_keys(before)
    new_warnings, unfrozen = [], []
    for row in after:
        if row["severity"] != "WARNING":
            continue
        key = (row["code"], str(row["object_id"]))
        if key in frozen:
            continue
        if key in known:
            unfrozen.append(row)
        else:
            new_warnings.append(row)
    if new_warnings:
        reasons.append(_reason("REPAIR_EFFECT_MISMATCH",
                               "the fresh read produced %d new WARNING finding(s) whose code+object "
                               "was not present before" % len(new_warnings)))
    if unfrozen:
        reasons.append(_reason("REPAIR_EFFECT_MISMATCH",
                               "the fresh read still carries %d WARNING finding(s) the host has not "
                               "frozen as background" % len(unfrozen)))
    if reasons:
        return "BLOCKED", reasons
    return "PASS", []


# ---------------------------------------------------------------------------
# worker: the only component that imports akcli
# ---------------------------------------------------------------------------

def _worker_argv(toolchain, mode, request_path, out_path):
    """The worker always runs as the pinned interpreter itself.

    launcher_argv belongs to the akcli CLI invocation only; prepending it here
    would make the interpreter try to execute itself as a script.
    """
    return ([toolchain["worker_python"],
             "-X", "utf8", "-m", "tools.akcli_adapter",
             "--worker", mode, "--request", request_path, "--out", out_path])


def _distribution_manifest(package="akcli-kicad"):
    """Verify the installed distribution against its RECORD and digest every file."""
    import importlib.metadata as metadata
    try:
        distribution = metadata.distribution(package)
    except metadata.PackageNotFoundError as exc:
        raise AdapterInputError("the pinned akcli distribution is not installed") from exc
    root = os.path.dirname(str(distribution._path))
    rows = []
    for entry in distribution.files or ():
        path = os.path.join(root, str(entry))
        if not os.path.isfile(path):
            continue
        rows.append([str(entry).replace(os.sep, "/"), hash_bytes(_read_bytes(path))])
    rows.sort()
    return {"package": package, "version": distribution.version,
            "files": len(rows), "sha256": canonical_sha256("manifest", rows)}


def _symbol_digest(target):
    """Digest of the symbol environment the writer will resolve against.

    KiCad 6 and later keep every placed symbol definition embedded in the
    document itself, and the pinned writer resolves place_component against that
    embedded library.  Digesting it is therefore the exact symbol environment
    for this design; a document without an embedded library fails closed.
    """
    from akcli import sexpr
    from akcli.readers import kicad
    library = kicad.read_embedded_library(target)
    symbols = getattr(library, "symbols", None) if library is not None else None
    if not symbols:
        return None
    dump = getattr(sexpr, "dumps", None)
    rows = []
    for symbol in symbols:
        pins = sorted([[str(pin.number), str(pin.name or ""),
                        str(getattr(pin.electrical_type, "value", pin.electrical_type))]
                       for pin in symbol.pins])
        body = dump(symbol.body_sexpr) if dump is not None and getattr(symbol, "body_sexpr", None) is not None else ""
        rows.append([str(symbol.lib_id), canonical_sha256("protected", pins),
                     hash_bytes(body.encode("utf-8"))])
    rows.sort()
    return canonical_sha256("manifest", rows)


def _new_uuid(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "aedl-native:" + ":".join(str(p) for p in parts)))


def _native_connectivity(target):
    """The pinned reader's own connectivity gate, as before/after finding sets."""
    from akcli import sexpr
    from akcli.writers import connectivity
    document = sexpr.parse(_read_bytes(target).decode("utf-8"))
    rows = connectivity.verify(document, path=target)
    findings = []
    for row in rows:
        severity = getattr(row, "severity", None)
        refs = sorted(str(item) for item in (getattr(row, "refs", None) or []))
        # The contract compares warnings by code AND object; dropping the reader's
        # refs would make two different objects look like the same finding.
        findings.append({"code": str(getattr(row, "code", "UNKNOWN_FINDING")),
                         "severity": str(getattr(severity, "value", severity)),
                         "message": str(getattr(row, "message", "") or "")[: _MAX_TEXT],
                         "object_id": "|".join(refs) if refs else None})
    return findings


def _worker_read(request):
    """Collect the complete native observation from the pinned akcli reader."""
    from akcli.readers import kicad
    target = _existing_file(_absolute(request["bound_target"], "bound target"), "bound target")
    raw = _read_bytes(target)
    source_sha256 = hash_bytes(raw)
    schematic = kicad.read_sch(target)
    primitives = kicad.read_primitives(target)
    library = kicad.read_embedded_library(target)
    sheet_uuid = _new_uuid("sheet", source_sha256)
    library_by_id = {}
    if library is not None:
        for symbol in library.symbols:
            library_by_id[getattr(symbol, "lib_id", None)] = symbol
    components, pins = [], []
    for component in schematic.components:
        reference = str(component.designator)
        unit = int(getattr(component, "part_count", 1) or 1)
        identity = {"sheet_path": "/" + sheet_uuid, "component_uuid": str(component.unique_id),
                    "reference": reference, "unit": unit}
        definition = library_by_id.get(str(component.library_ref))
        if definition is None:
            raise AdapterInputError("the embedded library has no definition for %s"
                                    % component.library_ref)
        definition_rows, definition_index = [], {}
        for pin in definition.pins:
            number = str(pin.number)
            name = str(pin.name or "")
            electrical = str(getattr(pin.electrical_type, "value", pin.electrical_type))
            definition_index[number] = (name, electrical)
            definition_rows.append([number, name, electrical, int(pin.x_mil), int(pin.y_mil)])
        definition_rows.sort()
        components.append({
            "identity": identity, "reference": reference,
            "lib_id": str(component.library_ref),
            "lib_definition_sha256": canonical_sha256("protected",
                                                      {"lib_id": str(component.library_ref),
                                                       "pins": definition_rows}),
            "value": str(component.value or ""), "footprint": str(component.footprint or ""),
            "unit": unit,
            "position_nm": [int(round(float(component.x_mil) * 25400)),
                            int(round(float(component.y_mil) * 25400))],
            "rotation": int(component.rotation or 0),
            "mirror": str(component.mirror or "none"),
            "dnp": bool(component.dnp), "in_bom": bool(component.in_bom),
            "on_board": bool(component.on_board),
            "pin_definition_sha256": canonical_sha256("protected", definition_rows)})
        for pin in component.pins:
            number = str(pin.number)
            name, electrical = definition_index.get(
                number, (str(pin.name or ""), str(getattr(pin.electrical_type, "value",
                                                        pin.electrical_type))))
            pins.append({"identity": dict(identity, number=number,
                                          pin_uuid=_new_uuid("pin", component.unique_id, number)),
                         "name": name, "electrical_type": electrical,
                         "no_connect": False, "partition_key": ""})
    partitions = []
    for net in schematic.nets:
        members = sorted([{"sheet_path": "/" + sheet_uuid, "component_uuid": "",
                           "reference": str(ref), "unit": 1, "number": str(number)}
                          for ref, number in net.members], key=canonical_json_bytes)
        names = sorted("/" + str(name) for name in (net.source_names or [net.name]))
        partitions.append({"key": "", "members": members, "names": names})
    metadata = getattr(schematic, "metadata", None) or {}
    declared_components = metadata.get("component_count")
    declared_pins = metadata.get("pin_count")
    primitive_pins = len(getattr(primitives, "pins", None) or [])
    coverage_basis = {
        "reader_metadata_present": bool(metadata),
        "component_count_matches": (None if declared_components is None
                                    else declared_components == len(components)),
        "pin_count_matches": None if declared_pins is None else declared_pins == len(pins),
        "primitive_pin_count": primitive_pins,
        "primitive_pin_count_matches": (None if not primitive_pins
                                        else primitive_pins == len(pins)),
    }
    return {"source_sha256": source_sha256,
            "components": components, "pins": pins, "partitions": partitions,
            "coverage_basis": coverage_basis,
            "counts": {"components": len(components), "pins": len(pins),
                       "partitions": len(partitions)},
            "primitives": {name: len(getattr(primitives, name))
                           for name in ("wires", "junctions", "labels", "pins",
                                        "buses", "bus_entries")},
            "connectivity": _native_connectivity(target)}


def parse_sexpr(text):
    """Minimal S-expression reader for complete source objects (adapter-local)."""
    tokens = []
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char in "()":
            tokens.append(char)
            index += 1
        elif char.isspace():
            index += 1
        elif char == '"':
            end = index + 1
            while end < length and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            tokens.append(text[index:end + 1])
            index = end + 1
        else:
            end = index
            while end < length and not text[end].isspace() and text[end] not in "()":
                end += 1
            tokens.append(text[index:end])
            index = end
    stack, root = [], []
    for token in tokens:
        if token == "(":
            node = []
            if stack:
                stack[-1].append(node)
            else:
                root.append(node)
            stack.append(node)
        elif token == ")":
            if not stack:
                raise AdapterInputError("unbalanced S-expression")
            stack.pop()
        else:
            if not stack:
                raise AdapterInputError("stray S-expression atom")
            stack[-1].append(token)
    if stack:
        raise AdapterInputError("unterminated S-expression")
    return root


def source_objects(raw):
    """Complete top-level source objects with a stable identity and AST hash."""
    objects = []
    for node in parse_sexpr(raw.decode("utf-8")):
        if not node or not isinstance(node[0], str):
            raise AdapterInputError("a top-level object carries no kind")
        identity = None
        for child in node[1:]:
            if isinstance(child, list) and child and child[0] == "uuid" and len(child) > 1:
                identity = str(child[1])
                break
        if identity is None:
            identity = "root:" + node[0]
        objects.append({"identity": identity, "kind": node[0],
                        "semantic_ast_sha256": canonical_sha256("protected", node),
                        "descriptor": {"ast": node}})
    return objects


def _worker_exception(request):
    """The constrained exception writer; the API has no applied field."""
    from akcli.writers.kicad import apply as apply_ops
    oplist = request["oplist"]
    stage_path = _existing_file(_absolute(request["stage_path"], "stage path"), "stage path")
    backup_dir = _absolute(request["backup_dir"], "backup directory")
    os.makedirs(backup_dir, exist_ok=True)
    findings = []
    results = apply_ops(oplist, stage_path, apply=True, sources=None,
                        backup_dir=backup_dir, backup_depth=EXCEPTION_BACKUP_DEPTH,
                        tol_nm=0, verify_out=findings, allow_open=False)
    return {"op_results": [_op_result(row) for row in results],
            "connectivity": [_receipt_finding(row) for row in findings],
            "tool_applied": None}


def _op_result(row):
    return {"op_index": int(getattr(row, "op_index", -1)),
            "op": getattr(row, "op", None),
            "status": str(getattr(row, "status", "")),
            "created_uuids": [str(item) for item in (getattr(row, "created_uuids", None) or [])],
            "error_code": getattr(row, "error_code", None),
            "message": str(getattr(row, "message", "") or "")[: _MAX_TEXT]}


def _receipt_finding(row):
    severity = getattr(row, "severity", None)
    refs = getattr(row, "refs", None) or []
    return {"code": str(getattr(row, "code", None) or "UNKNOWN_FINDING"),
            "severity": str(getattr(severity, "value", severity)),
            "message": str(getattr(row, "message", "") or "")[: _MAX_TEXT],
            "object_id": str(refs[0]) if refs else None}


def _tool_probe(target=None):
    """What the pinned toolchain actually is, measured rather than assumed."""
    probe = {"version": None, "artifact_sha256": None, "symbol_digest": None,
             "akcli_upstream_commit": AKCLI_UPSTREAM_COMMIT}
    try:
        import importlib.metadata as metadata
        probe["version"] = metadata.version("akcli-kicad")
    except Exception:
        probe["version"] = None
    try:
        probe["artifact_sha256"] = _distribution_manifest()["sha256"]
    except Exception:
        probe["artifact_sha256"] = None
    if target:
        try:
            probe["symbol_digest"] = _symbol_digest(target)
        except Exception:
            probe["symbol_digest"] = None
    return probe


def worker_main(argv=None):
    """Fixed READ / APPLY_EXCEPTION worker. Never a general task executor."""
    parser = argparse.ArgumentParser(prog="tools.akcli_adapter.worker")
    parser.add_argument("--worker", required=True, choices=WORKER_MODES)
    parser.add_argument("--request", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    request = _load_json_file(args.request, "worker request")
    try:
        if args.worker == "READ":
            payload = _worker_read(request)
            payload["tool"] = _tool_probe(request["bound_target"])
        else:
            payload = _worker_exception(request)
            payload["tool"] = _tool_probe(request["stage_path"])
        result = {"status": "OK", "worker": args.worker, "payload": payload}
    except Exception as exc:  # the worker reports; the adapter classifies
        result = {"status": "ERROR", "worker": args.worker,
                  "error": "%s: %s" % (type(exc).__name__, exc)}
    with open(args.out, "wb") as handle:
        handle.write(json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return 0


def _repository_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_worker(toolchain, mode, request, artifact_root):
    request_path = os.path.join(artifact_root, "request-%s.json" % mode.lower())
    out_path = os.path.join(artifact_root, "result-%s.json" % mode.lower())
    with open(request_path, "wb") as handle:
        handle.write(json.dumps(request, sort_keys=True).encode("utf-8"))
    environment = dict(os.environ)
    environment.update(toolchain["environment"])
    # The worker always runs as "python -m tools.akcli_adapter" from a confined
    # working directory, so the repository root has to be importable explicitly.
    search = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (_repository_root() + (os.pathsep + search if search else ""))
    argv = _worker_argv(toolchain, mode, request_path, out_path)
    try:
        completed = subprocess.run(argv, shell=False, cwd=artifact_root,
                                   timeout=toolchain["timeout_seconds"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=environment)
    except subprocess.TimeoutExpired:
        return "TOOL_ERROR", [_reason("REPAIR_TIMEOUT",
                                      "the %s worker exceeded the frozen timeout" % mode)], None
    except OSError as exc:
        return "TOOL_ERROR", [_reason("REPAIR_TOOL_UNAVAILABLE",
                                      "the %s worker could not start: %s" % (mode, exc))], None
    if completed.returncode != 0:
        tail = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        return "TOOL_ERROR", [_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                      "the %s worker exited %d: %s"
                                      % (mode, completed.returncode,
                                         tail[-1] if tail else "no diagnostics"))], None
    try:
        payload = parse_json_bytes(_read_bytes(out_path), "worker result")
    except (AdapterInputError, OSError) as exc:
        return "TOOL_ERROR", [_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                      "the %s worker produced no readable result: %s" % (mode, exc))], None
    if payload.get("status") != "OK":
        return "TOOL_ERROR", [_reason("REPAIR_TOOL_UNAVAILABLE",
                                      "the %s worker failed: %s" % (mode, payload.get("error")))], None
    return "OK", [], payload.get("payload")


# ---------------------------------------------------------------------------
# observation assembly
# ---------------------------------------------------------------------------

def _assemble_observation(source_sha256, raw, payload):
    objects = source_objects(raw)
    components = payload["components"]
    pins = payload["pins"]
    partitions = payload["partitions"]
    component_lookup = {row["reference"]: row for row in components}
    pin_lookup = {(row["identity"]["reference"], row["identity"]["number"]): row for row in pins}
    for component in components:
        component["identity"] = {"sheet_path": component["identity"]["sheet_path"],
                                 "component_uuid": component["identity"]["component_uuid"],
                                 "reference": component["reference"], "unit": component["unit"]}
    for pin in pins:
        pin["identity"] = {"sheet_path": pin["identity"]["sheet_path"],
                           "component_uuid": pin["identity"]["component_uuid"],
                           "reference": pin["identity"]["reference"],
                           "unit": pin["identity"]["unit"],
                           "number": pin["identity"]["number"],
                           "pin_uuid": pin["identity"]["pin_uuid"]}
    for partition in partitions:
        members = []
        for member in partition["members"]:
            component = component_lookup[member["reference"]]
            pin = pin_lookup[(member["reference"], member["number"])]
            members.append(dict(component["identity"], number=member["number"],
                                pin_uuid=pin["identity"]["pin_uuid"]))
        members.sort(key=canonical_json_bytes)
        partition["members"] = members
        partition["key"] = canonical_sha256("topology", members)
    member_to_partition = {}
    for partition in partitions:
        for member in partition["members"]:
            member_to_partition[canonical_json_bytes(member)] = partition["key"]
    for pin in pins:
        pin["partition_key"] = member_to_partition[canonical_json_bytes(pin["identity"])]
    pin_ids = sorted([row["identity"] for row in pins], key=canonical_json_bytes)
    component_ids = sorted([row["identity"] for row in components], key=canonical_json_bytes)
    return {"version": 1, "source_sha256": source_sha256,
            "components": components, "pins": pins, "partitions": partitions,
            "source_objects": objects,
            "coverage": {"expected_pin_count": len(pin_ids),
                         "observed_pin_count": len(pin_ids),
                         "expected_pin_keys_sha256": canonical_sha256("topology", pin_ids),
                         "observed_pin_keys_sha256": canonical_sha256("topology", pin_ids),
                         "expected_component_keys_sha256": canonical_sha256("topology", component_ids),
                         "observed_component_keys_sha256": canonical_sha256("topology", component_ids),
                         "complete": True}}


# ---------------------------------------------------------------------------
# read_native (contract section 8)
# ---------------------------------------------------------------------------

_READ_REQUEST_FIELDS = {"host_binding", "absolute_read_root", "relative_target"}
_HOST_BINDING_FIELDS = {"run_id", "candidate_id", "txn_id", "toolchain_manifest",
                        "toolchain_sha256", "read_authorization"}


def read_native(read_request, artifact_root=None):
    """Read the complete native observation, or fail closed.

    artifact_root is optional and host-provided; without it the worker scratch
    space is a private temporary directory, never the read root.
    """
    result = {"status": "TOOL_ERROR", "source_sha256": None, "observation": None,
              "connectivity_findings": [], "tool": None, "raw_artifact_hashes": {},
              "reasons": [_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                  "the native read did not complete", stage="PRECHECK")]}
    scratch = artifact_root
    try:
        if scratch is None:
            scratch = tempfile.mkdtemp(prefix="aedl-akcli-read-")
        _closed(read_request, _READ_REQUEST_FIELDS, "read request")
        binding = _closed(read_request["host_binding"], _HOST_BINDING_FIELDS, "host binding")
        for field in ("run_id", "candidate_id", "txn_id"):
            _identifier(binding[field], field)
        toolchain = toolchain_manifest(binding["toolchain_manifest"])
        if _toolchain_digest(toolchain) != _sha(binding["toolchain_sha256"], "toolchain digest"):
            raise AdapterInputError("the toolchain digest does not match its manifest")
        authorization = binding["read_authorization"]
        if not isinstance(authorization, dict) or not authorization.get("resolved_authorization_refs"):
            raise AdapterInputError("the native read has no host-resolved authorization")
        _sha(authorization.get("context_digest"), "authorization context digest")
        root = _absolute(read_request["absolute_read_root"], "read root")
        target = _existing_file(_resolve_within(root, read_request["relative_target"]),
                                "read target")
        os.makedirs(scratch, exist_ok=True)
        status, reasons, payload = _run_worker(toolchain, "READ",
                                               {"bound_target": target}, scratch)
        if status != "OK":
            result.update(status=status, reasons=reasons)
            return result
        findings, verdict = normalize_connectivity(payload.get("connectivity"))
        result["tool"] = payload.get("tool")
        result["source_sha256"] = payload["source_sha256"]
        result["connectivity_findings"] = findings
        raw = _read_bytes(target)
        result["observation"] = normalize_observation(
            _assemble_observation(payload["source_sha256"], raw, payload))
        result["raw_artifact_hashes"] = {"source": payload["source_sha256"]}
        if verdict == "UNKNOWN":
            result.update(status="UNKNOWN",
                          reasons=[_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                           "the native read reported an unknown connectivity severity",
                                           stage="PRECHECK")])
            return result
        basis = payload.get("coverage_basis") or {}
        disagreeing = [name for name in ("component_count_matches", "pin_count_matches",
                                         "primitive_pin_count_matches")
                       if basis.get(name) is False]
        if not basis.get("reader_metadata_present") and not basis.get("primitive_pin_count"):
            disagreeing.append("no_independent_inventory")
        if disagreeing:
            result.update(status="UNKNOWN",
                          reasons=[_reason("REPAIR_COVERAGE_INCOMPLETE",
                                           "the pinned reader's own inventories disagree (%s), so the "
                                           "native observation is not complete"
                                           % ", ".join(sorted(disagreeing)), stage="PRECHECK")])
            return result
        result.update(status="PASS", reasons=[])
        return result
    except (AdapterInputError, ValueError, KeyError, TypeError) as exc:
        result.update(status="BLOCKED",
                      reasons=[_reason("REPAIR_INPUT_DRIFT",
                                       "unverifiable native read input: %s" % exc,
                                       stage="PRECHECK")])
        return result


# ---------------------------------------------------------------------------
# apply_stage (contract sections 7, 8, 10)
# ---------------------------------------------------------------------------

_STAGE_REQUEST_FIELDS = {"host_patch", "txn_id", "stage_root", "stage_target",
                         "oplist_path", "native_artifact_root"}
_HOST_PATCH_FIELDS = {"schema_version", "run_id", "candidate_id", "round_id", "patch_id",
                      "context_id", "proposal", "proposal_sha256", "target", "base",
                      "policy", "authority", "toolchain_manifest", "toolchain_sha256",
                      "route", "bound_policy", "patch_sha256"}
_AUTHORITY_FIELDS = {"context_digest", "resolved_authorization_refs", "decisions"}
_POLICY_FIELDS = {"id", "file_sha256", "bound_rule_id", "bound_policy_sha256"}
_DECISION_FIELDS = {"capability", "effect"}
_BASE_FIELDS = {"files", "topology_sha256"}
_PROPOSAL_FIELDS = {"schema_version", "context_id", "target", "base_source_sha256",
                    "decision", "oplist", "diagnosis"}
_DIAGNOSIS_FIELDS = {"rule_id", "observed", "fact_ids", "requirement_level", "rationale"}
_OPLIST_FIELDS = {"protocol_version", "target_format", "ops"}
_REQUIREMENT_LEVELS = ("MANDATORY", "RECOMMENDED", "MARGIN", "UNKNOWN")
_OPERATION_FIELDS = {"delete_object": {"op", "uuid"},
                     "add_net_label": {"op", "name", "at", "scope", "rotation"},
                     "place_component": {"op", "lib_id", "designator", "x_mil", "y_mil",
                                         "value", "footprint", "rotation", "mirror", "unit"}}
_AUTHORITY_EFFECTS = ("ALLOW", "DENY")
_REFERENCE_PIN = re.compile(r"^[A-Za-z0-9_+\-]{1,64}\.[A-Za-z0-9_+\-]{1,16}\Z")
_MAX_DIAGNOSIS = 16

# The frozen contract has no host-bound "background warning" channel, so nothing
# is frozen and every connectivity WARNING blocks.  connectivity_verdict still
# takes the set explicitly so the comparison is testable and a future contract
# can bind it.
_BACKGROUND_WARNINGS = frozenset()


def _validate_proposal(proposal):
    """Recursively closed Proposal (PATCH branch, contract section 4)."""
    _closed(proposal, _PROPOSAL_FIELDS, "proposal")
    if _integer(proposal["schema_version"], "proposal schema version", 1) != 1:
        raise AdapterInputError("unsupported proposal schema version")
    _identifier(proposal["context_id"], "proposal context id")
    _text(proposal["target"], "proposal target")
    _sha(proposal["base_source_sha256"], "proposal base source")
    if proposal["decision"] != "PATCH":
        raise AdapterInputError("only a PATCH proposal can reach the native writer")
    oplist = _closed(proposal["oplist"], _OPLIST_FIELDS, "proposal op-list")
    if _integer(oplist["protocol_version"], "protocol version", 1) != OPLIST_PROTOCOL:
        raise AdapterInputError("the proposal does not use oplist protocol %d" % OPLIST_PROTOCOL)
    if oplist["target_format"] != OPLIST_TARGET_FORMAT:
        raise AdapterInputError("the proposal does not target %s" % OPLIST_TARGET_FORMAT)
    diagnosis = proposal["diagnosis"]
    if not isinstance(diagnosis, list) or len(diagnosis) > _MAX_DIAGNOSIS:
        raise AdapterInputError("the proposal diagnosis must hold at most %d rows" % _MAX_DIAGNOSIS)
    for index, row in enumerate(diagnosis):
        _closed(row, _DIAGNOSIS_FIELDS, "proposal diagnosis %d" % index)
        _text(row["rule_id"], "diagnosis rule", empty=True)
        _text(row["observed"], "diagnosis observation", empty=True)
        facts = row["fact_ids"]
        if not isinstance(facts, list) or any(not isinstance(item, str) for item in facts):
            raise AdapterInputError("diagnosis fact_ids must be a list of strings")
        if row["requirement_level"] not in _REQUIREMENT_LEVELS:
            raise AdapterInputError("unsupported diagnosis requirement level")
        _text(row["rationale"], "diagnosis rationale", empty=True)
    return proposal


def _normalize_operation(row, label):
    """Closed, default-filled Operation v1.

    Comparing operation names alone would let an authorized operation drift into
    a different one while keeping its type, so every field that reaches the
    native writer is compared after normalization.
    """
    if not isinstance(row, dict) or row.get("op") not in _OPERATION_FIELDS:
        raise AdapterInputError("%s is not a supported Operation v1" % label)
    kind = row["op"]
    _reject_unknown(row, _OPERATION_FIELDS[kind], label)
    if kind == "delete_object":
        return {"op": kind, "uuid": _identifier(_required(row, "uuid", label), "operation uuid")}
    if kind == "add_net_label":
        if row.get("scope", "local") != "local" or row.get("rotation", 0) != 0:
            raise AdapterInputError("%s only permits scope=local and rotation=0" % label)
        anchor = _text(_required(row, "at", label), "label anchor")
        if not _REFERENCE_PIN.match(anchor):
            raise AdapterInputError("%s must anchor at REF.PIN" % label)
        return {"op": kind, "name": _text(_required(row, "name", label), "label name"),
                "at": anchor, "scope": "local", "rotation": 0}
    if row.get("rotation", 0) != 0 or row.get("mirror", "none") != "none" or row.get("unit", 1) != 1:
        raise AdapterInputError("%s only permits rotation=0, mirror=none, unit=1" % label)
    return {"op": kind, "lib_id": _text(_required(row, "lib_id", label), "library id"),
            "designator": _identifier(_required(row, "designator", label), "designator"),
            "x_mil": _integer(_required(row, "x_mil", label), "x_mil"),
            "y_mil": _integer(_required(row, "y_mil", label), "y_mil"),
            "value": _text(_required(row, "value", label), "value", empty=True),
            "footprint": _text(_required(row, "footprint", label), "footprint", empty=True),
            "rotation": 0, "mirror": "none", "unit": 1}


def _normalize_operations(ops, label):
    if not isinstance(ops, list) or not 1 <= len(ops) <= _MAX_OPS:
        raise AdapterInputError("%s must hold 1..%d operations" % (label, _MAX_OPS))
    return [_normalize_operation(row, "%s operation %d" % (label, index))
            for index, row in enumerate(ops)]


def stage_result_template(txn_id=None):
    return {"status": "TOOL_ERROR", "txn_id": txn_id, "patch_sha256": None,
            "bound_policy_sha256": None, "route": None,
            "tool": {"mode": None, "version": None, "artifact_sha256": None,
                     "exit_code": None, "tool_applied": None,
                     "op_results": [], "connectivity_findings": []},
            "before_source_sha256": None, "after_source_sha256": None,
            "changed": None, "native_before": None, "native_after": None,
            "raw_artifacts": {}, "reasons": []}


def apply_stage(stage_request):
    """Execute exactly one frozen-route write and report the real receipt."""
    result = stage_result_template()
    try:
        _closed(stage_request, _STAGE_REQUEST_FIELDS, "stage request")
        txn_id = _identifier(stage_request["txn_id"], "transaction id")
        result["txn_id"] = txn_id
        host_patch = _closed(stage_request["host_patch"], _HOST_PATCH_FIELDS, "host patch")
        for field in ("run_id", "candidate_id", "round_id", "patch_id", "context_id"):
            _identifier(host_patch[field], field)
        _sha(host_patch["patch_sha256"], "patch digest")
        body = {key: value for key, value in host_patch.items() if key != "patch_sha256"}
        if canonical_sha256("patch", body) != host_patch["patch_sha256"]:
            raise AdapterInputError("the host patch does not match its own digest")
        proposal = _validate_proposal(host_patch["proposal"])
        if canonical_sha256("proposal", host_patch["proposal"]) != _sha(host_patch["proposal_sha256"],
                                                                        "proposal digest"):
            raise AdapterInputError("the proposal does not match its own digest")
        if proposal["context_id"] != host_patch["context_id"]:
            raise AdapterInputError("the proposal context does not match the host patch context")
        if proposal["target"] != host_patch["target"]:
            raise AdapterInputError("the proposal target does not match the host patch target")
        base = _closed(host_patch["base"], _BASE_FIELDS, "base binding")
        _sha(base["topology_sha256"], "base topology digest")
        if not isinstance(base["files"], dict):
            raise AdapterInputError("base files must be a mapping")
        policy = _closed(host_patch["policy"], _POLICY_FIELDS, "policy binding")
        _identifier(policy["id"], "policy id")
        _sha(policy["file_sha256"], "policy digest")
        _sha(policy["bound_policy_sha256"], "bound policy digest")
        rule = _identifier(policy["bound_rule_id"], "bound rule")
        result["patch_sha256"] = host_patch["patch_sha256"]
        result["bound_policy_sha256"] = policy["bound_policy_sha256"]
        result["route"] = host_patch["route"]
        expected_route = ROUTE_BY_RULE.get(rule)
        if expected_route is None:
            result.update(status="BLOCKED",
                          reasons=[_reason("REPAIR_POLICY_DISABLED",
                                           "rule %s has no frozen route" % rule,
                                           stage="PRECHECK")])
            return result
        if host_patch["route"] not in ROUTES or host_patch["route"] != expected_route:
            result.update(status="BLOCKED",
                          reasons=[_reason("REPAIR_AUTH_DENIED",
                                           "route %r is not the frozen route %s for rule %s"
                                           % (host_patch["route"], expected_route, rule),
                                           stage="PRECHECK")])
            return result
        route = host_patch["route"]
        authority = _closed(host_patch["authority"], _AUTHORITY_FIELDS, "authority")
        _sha(authority["context_digest"], "authorization context digest")
        references = authority["resolved_authorization_refs"]
        if (not isinstance(references, list) or not references
                or any(not isinstance(item, str) or not item for item in references)):
            raise AdapterInputError("the host patch carries no host-resolved authorization")
        decisions = authority["decisions"]
        if not isinstance(decisions, list):
            raise AdapterInputError("authority decisions must be a list")
        resolved = {}
        for index, row in enumerate(decisions):
            _closed(row, _DECISION_FIELDS, "authority decision %d" % index)
            capability = _identifier(row["capability"], "decision capability")
            if row["effect"] not in _AUTHORITY_EFFECTS:
                raise AdapterInputError("unsupported authority effect")
            if capability in resolved:
                result.update(status="BLOCKED",
                              reasons=[_reason("REPAIR_AUTH_DENIED",
                                               "capability %s carries more than one resolved decision"
                                               % capability, stage="PRECHECK")])
                return result
            resolved[capability] = row["effect"]
        denied = sorted(name for name, effect in resolved.items() if effect == "DENY")
        if denied:
            result.update(status="BLOCKED",
                          reasons=[_reason("REPAIR_AUTH_DENIED",
                                           "the host resolved DENY for %s" % ", ".join(denied),
                                           stage="PRECHECK")])
            return result
        missing = [name for name in CAPABILITIES if resolved.get(name) != "ALLOW"]
        if missing:
            result.update(status="BLOCKED",
                          reasons=[_reason("REPAIR_AUTH_DENIED",
                                           "missing an explicit ALLOW for %s" % ", ".join(missing),
                                           stage="PRECHECK")])
            return result
        toolchain = toolchain_manifest(host_patch["toolchain_manifest"])
        if _toolchain_digest(toolchain) != _sha(host_patch["toolchain_sha256"], "toolchain digest"):
            raise AdapterInputError("the toolchain digest does not match its manifest")
        stage_root = _absolute(stage_request["stage_root"], "stage root")
        stage_target = _existing_file(_resolve_within(stage_root, stage_request["stage_target"]),
                                      "stage target")
        op_list_path = _absolute(stage_request["oplist_path"], "op-list path")
        if _common_root(stage_root, op_list_path, "the op-list path") != stage_root:
            raise AdapterInputError("the op-list path escapes the stage root")
        oplist_path = _existing_file(
            _resolve_within(stage_root, os.path.relpath(op_list_path, stage_root).replace(os.sep, "/")),
            "op-list path")
        artifact_root = _absolute(stage_request["native_artifact_root"], "native artifact root")
        if _has_linked_component(artifact_root):
            raise AdapterInputError("the native artifact root must not contain a link")
        os.makedirs(artifact_root, exist_ok=True)
        result["tool"]["mode"] = "CLI" if route == "STRICT" else "PYTHON_WRITER"
        result["tool"]["version"] = toolchain["akcli_version"]
        result["tool"]["artifact_sha256"] = toolchain["akcli_artifact_sha256"]
        proposed = _normalize_operations(proposal["oplist"]["ops"], "proposal op-list")
        on_disk = _closed(parse_json_bytes(_read_bytes(oplist_path), "op-list"),
                          _OPLIST_FIELDS, "op-list")
        if (on_disk["protocol_version"] != OPLIST_PROTOCOL
                or on_disk["target_format"] != OPLIST_TARGET_FORMAT
                or _normalize_operations(on_disk["ops"], "op-list") != proposed):
            result.update(status="BLOCKED",
                          reasons=[_reason("REPAIR_INPUT_DRIFT",
                                           "the on-disk op-list is not the authorized proposal "
                                           "operation for operation",
                                           stage="PRECHECK")])
            return result
        before = _read_bytes(stage_target)
        result["before_source_sha256"] = hash_bytes(before)
        if result["before_source_sha256"] != proposal["base_source_sha256"]:
            result.update(status="BLOCKED",
                          reasons=[_reason("REPAIR_INPUT_DRIFT",
                                           "the stage bytes are not the proposal base source: the "
                                           "proposal is stale for this artefact", stage="PRECHECK")])
            return result
        native_before = _native_read(toolchain, stage_root, stage_request["stage_target"],
                                     artifact_root)
        if native_before["status"] != "PASS":
            result.update(status="TOOL_ERROR" if native_before["status"] == "TOOL_ERROR" else "UNKNOWN",
                          reasons=native_before["reasons"])
            return result
        result["native_before"] = {"source_sha256": native_before["source_sha256"],
                                   "observation": native_before["observation"]}
        receipt, status, reasons = _execute_route(route, toolchain, stage_target,
                                                  oplist_path, on_disk, artifact_root)
        result["tool"].update(receipt)
        after = _read_bytes(stage_target)
        result["after_source_sha256"] = hash_bytes(after)
        result["changed"] = before != after
        result["raw_artifacts"] = {"source_before": result["before_source_sha256"],
                                   "source_after": result["after_source_sha256"]}
        if status == "BLOCKED" and reasons and reasons[0]["code"] == "REPAIR_STRICT_REFUSED":
            result.update(status="BLOCKED", reasons=reasons + [
                _reason("REPAIR_EFFECT_MISMATCH",
                        "a refused strict write is not retried through the exception writer")])
            return result
        if status != "OK":
            result.update(status=status, reasons=reasons)
            return result
        native_after = _native_read(toolchain, stage_root, stage_request["stage_target"],
                                    artifact_root)
        if native_after["status"] != "PASS":
            result.update(status="TOOL_ERROR" if native_after["status"] == "TOOL_ERROR" else "UNKNOWN",
                          reasons=native_after["reasons"])
            return result
        result["native_after"] = {"source_sha256": native_after["source_sha256"],
                                  "observation": native_after["observation"]}
        status, reasons = _verify_effect(route, result, native_before, native_after,
                                         toolchain, len(proposed))
        result.update(status=status, reasons=reasons)
        return result
    except AdapterInputError as exc:
        result.update(status="BLOCKED",
                      reasons=[_reason("REPAIR_INPUT_DRIFT",
                                       "unverifiable stage input: %s" % exc,
                                       stage="PRECHECK")])
        return result


def _native_read(toolchain, root, relative, artifact_root):
    binding = {"run_id": "native-read", "candidate_id": "native-read", "txn_id": "native-read",
               "toolchain_manifest": toolchain,
               "toolchain_sha256": _toolchain_digest(toolchain),
               "read_authorization": {"context_digest": canonical_sha256("context", root),
                                      "resolved_authorization_refs": ["adapter:native-read"],
                                      "decisions": []}}
    return read_native({"host_binding": binding, "absolute_read_root": root,
                        "relative_target": relative}, artifact_root=artifact_root)


def _execute_route(route, toolchain, stage_target, oplist_path, oplist, artifact_root):
    if route == "STRICT":
        return _execute_strict(toolchain, stage_target, oplist_path, artifact_root)
    return _execute_exception(toolchain, stage_target, oplist, artifact_root)


def _strict_argv(toolchain, stage_target, oplist_path):
    return (list(toolchain["launcher_argv"]) + [toolchain["akcli_executable"],
            "draw", stage_target, OPLIST_FLAG, oplist_path] + list(STRICT_ARGUMENTS[1:]))


def _execute_strict(toolchain, stage_target, oplist_path, artifact_root):
    """Exactly one strict write call; refusal is terminal and never retried."""
    receipt = {"exit_code": None, "tool_applied": None, "op_results": [],
               "connectivity_findings": []}
    executable = toolchain["akcli_executable"]
    # Host-frozen executables are allowed to be symlinks: packaged interpreters
    # and CLIs are routinely linked (for example /opt/.../bin/python ->
    # python3.9).  Only data paths keep the strict no-link component rule.
    if not os.path.isfile(executable):
        return receipt, "TOOL_ERROR", [_reason("REPAIR_TOOL_UNAVAILABLE",
                                               "the pinned akcli executable is missing")]
    argv = _strict_argv(toolchain, stage_target, oplist_path)
    environment = dict(os.environ)
    environment.update(toolchain["environment"])
    try:
        completed = subprocess.run(argv, shell=False, cwd=artifact_root,
                                   timeout=toolchain["timeout_seconds"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=environment)
    except subprocess.TimeoutExpired:
        return receipt, "TOOL_ERROR", [_reason("REPAIR_TIMEOUT",
                                               "the strict write exceeded the frozen timeout")]
    except OSError as exc:
        return receipt, "TOOL_ERROR", [_reason("REPAIR_TOOL_UNAVAILABLE",
                                               "the strict write could not start: %s" % exc)]
    receipt["exit_code"] = completed.returncode
    payload = _optional_json(completed.stdout.decode("utf-8", "replace"))
    if completed.returncode == 6:
        if _is_legal_refusal(payload):
            findings, _verdict = normalize_connectivity(_connectivity_of(payload))
            receipt["connectivity_findings"] = findings
            receipt["op_results"] = _op_results_of(payload)
            return receipt, "BLOCKED", [_reason("REPAIR_STRICT_REFUSED",
                                                _refusal_message(payload, completed.stderr))]
        return receipt, "TOOL_ERROR", [_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                               "strict exited 6 without a legal refusal object")]
    if completed.returncode != 0:
        return receipt, "TOOL_ERROR", [_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                               "strict exited %d" % completed.returncode)]
    if not isinstance(payload, dict):
        return receipt, "TOOL_ERROR", [_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                               "strict succeeded without a parseable draw result")]
    applied = payload.get("applied")
    receipt["tool_applied"] = applied if isinstance(applied, bool) else None
    receipt["op_results"] = _op_results_of(payload)
    findings, verdict = normalize_connectivity(_connectivity_of(payload))
    receipt["connectivity_findings"] = findings
    if applied is not True:
        return receipt, "BLOCKED", [_reason("REPAIR_EFFECT_MISMATCH",
                                            "the strict receipt reports applied=%r" % (applied,))]
    if verdict == "UNKNOWN":
        return receipt, "UNKNOWN", [_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                            "the strict receipt carries an unknown connectivity severity")]
    return receipt, "OK", []


def _execute_exception(toolchain, stage_target, oplist, artifact_root):
    """Exactly one constrained writer call through the fixed Python worker."""
    receipt = {"exit_code": None, "tool_applied": None, "op_results": [],
               "connectivity_findings": []}
    if not os.path.isfile(toolchain["worker_python"]):
        return receipt, "TOOL_ERROR", [_reason("REPAIR_TOOL_UNAVAILABLE",
                                               "the pinned worker interpreter is missing")]
    request = {"oplist": oplist, "stage_path": stage_target,
               "backup_dir": os.path.join(artifact_root, "backup")}
    status, reasons, payload = _run_worker(toolchain, "APPLY_EXCEPTION", request, artifact_root)
    if status != "OK":
        return receipt, status, reasons
    receipt["exit_code"] = 0
    receipt["tool_applied"] = payload.get("tool_applied")
    receipt["op_results"] = payload.get("op_results", [])
    findings, verdict = normalize_connectivity(payload.get("connectivity"))
    receipt["connectivity_findings"] = findings
    if verdict == "UNKNOWN":
        return receipt, "UNKNOWN", [_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                                            "the writer reported an unknown connectivity severity")]
    return receipt, "OK", []


def _optional_json(text):
    text = text.strip()
    start = text.find("{")
    if start < 0:
        return None
    try:
        return parse_json_bytes(text[start:].encode("utf-8"), "tool receipt")
    except AdapterInputError:
        return None


def _is_legal_refusal(payload):
    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("error"), dict):
        return True
    if payload.get("status") in ("refused", "preview"):
        return True
    return payload.get("applied") is False


def _refusal_message(payload, stderr):
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        return str(payload["error"].get("message", "strict refused the op-list"))[: _MAX_TEXT]
    lines = stderr.decode("utf-8", "replace").strip().splitlines()
    return str(lines[-1] if lines else "strict refused the op-list")[: _MAX_TEXT]


def _connectivity_of(payload):
    if not isinstance(payload, dict):
        return []
    rows = payload.get("connectivity")
    return rows if isinstance(rows, list) else []


def _op_results_of(payload):
    rows = payload.get("ops")
    if not isinstance(rows, list):
        return []
    results = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        results.append({"op_index": row.get("op_index"), "op": row.get("op"),
                        "status": row.get("status"),
                        "created_uuids": [str(item) for item in (row.get("created_uuids") or [])],
                        "error_code": row.get("error_code"),
                        "message": str(row.get("message") or "")[: _MAX_TEXT]})
    return results


def _verify_effect(route, result, native_before, native_after, toolchain, op_count):
    """All conjunctive conditions of contract section 8 have to hold."""
    reasons = []
    tool = result["tool"]
    # The write resolved against the environment measured by the before read; the
    # after read may legitimately carry a different embedded library once the
    # write added a symbol, so only the installed distribution must be stable.
    before_probe = (native_before or {}).get("tool") or {}
    after_probe = (native_after or {}).get("tool") or {}
    if tool["version"] != AKCLI_VERSION:
        reasons.append(_reason("REPAIR_TOOL_UNAVAILABLE",
                               "the bound toolchain does not declare akcli %s" % AKCLI_VERSION))
    if before_probe.get("version") != AKCLI_VERSION:
        reasons.append(_reason("REPAIR_TOOL_UNAVAILABLE",
                               "the running akcli reports version %r" % (before_probe.get("version"),)))
    if after_probe.get("artifact_sha256") != before_probe.get("artifact_sha256"):
        reasons.append(_reason("REPAIR_TOOL_UNAVAILABLE",
                               "the installed akcli changed between the two native reads"))
    if before_probe.get("artifact_sha256") != toolchain["akcli_artifact_sha256"]:
        reasons.append(_reason("REPAIR_TOOL_UNAVAILABLE",
                               "the installed akcli distribution digest does not match the manifest"))
    if before_probe.get("symbol_digest") != toolchain["symbol_digest"]:
        reasons.append(_reason("REPAIR_TOOL_UNAVAILABLE",
                               "the bound symbol digest does not match the manifest"))
    if reasons:
        return "TOOL_ERROR", reasons
    if not result["changed"]:
        reasons.append(_reason("REPAIR_EFFECT_MISMATCH",
                               "the receipt claims a write but the stage bytes are unchanged"))
    results = tool["op_results"]
    if not results:
        reasons.append(_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                               "the receipt carries no per-operation results"))
    elif [row.get("op_index") for row in results] != list(range(op_count)):
        reasons.append(_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                               "the per-operation results do not cover 0..n-1 exactly once"))
    elif any(row.get("status") != "ok" for row in results):
        reasons.append(_reason("REPAIR_EFFECT_MISMATCH",
                               "at least one operation did not report ok"))
    if route == "CONSTRAINED_EXCEPTION" and tool["tool_applied"] is not None:
        reasons.append(_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                               "the constrained writer API has no applied field, so tool_applied must be null"))
    if route == "STRICT" and tool["tool_applied"] is not True:
        reasons.append(_reason("REPAIR_EFFECT_MISMATCH",
                               "the strict receipt does not report applied=true"))
    # The writer receipt is never the source of truth for the after state; the
    # fresh native read is.  A blocking severity the receipt reports still blocks
    # (fail-closed union), but new warnings are judged on the fresh read alone.
    fresh_before = native_before.get("connectivity_findings") or []
    fresh_after = (native_after or {}).get("connectivity_findings") or []
    connectivity_status, connectivity_reasons = connectivity_verdict(fresh_before, fresh_after)
    if connectivity_status == "UNKNOWN":
        return "UNKNOWN", reasons + connectivity_reasons
    reasons.extend(connectivity_reasons)
    receipt = tool["connectivity_findings"] or []
    fresh_has_blocking = any(row["severity"] in BLOCKING_SEVERITIES for row in fresh_after)
    fresh_has_no_connect = any(row["code"] == NO_CONNECT_CODE for row in fresh_after)
    receipt_blocking = [row for row in receipt if row["severity"] in BLOCKING_SEVERITIES]
    receipt_no_connect = [row for row in receipt if row["code"] == NO_CONNECT_CODE]
    if receipt_blocking and not fresh_has_blocking:
        reasons.append(_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                               "the writer receipt reports %d ERROR/CRITICAL connectivity finding(s) "
                               "the fresh read did not" % len(receipt_blocking)))
    if receipt_no_connect and not fresh_has_no_connect:
        reasons.append(_reason("REPAIR_TOOL_PROTOCOL_ERROR",
                               "the writer receipt reports %d %s finding(s) the fresh read did not"
                               % (len(receipt_no_connect), NO_CONNECT_CODE)))
    if reasons:
        return "BLOCKED", reasons
    return "APPLIED_TO_STAGE", []


def main(argv=None):
    parser = argparse.ArgumentParser(prog="tools.akcli_adapter")
    parser.add_argument("--worker", choices=WORKER_MODES)
    parser.add_argument("--request")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    if not args.worker:
        parser.error("the adapter is a worker; call it with --worker READ|APPLY_EXCEPTION")
    return worker_main(["--worker", args.worker, "--request", args.request, "--out", args.out])


if __name__ == "__main__":
    sys.exit(main())
