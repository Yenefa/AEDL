"""C4 - the real akcli apply path with a mandatory independent writer gate.

One apply = one audited record.  apply_and_verify() never trusts the writer:

  1. PRE-STATE   sha256 the artifact, parse its object graph with this module own
                 s-expression reader (never the writer reader) and export a
                 fresh KiCad netlist into a directory this run creates.
  2. AUTHORIZED DELTA  the caller declares what SHOULD change.  An op list
                 without a declared expectation is rejected; expect: [] is the
                 explicit declaration of an idempotent no-op.  A receipt can
                 never be its own expectation.
  3. APPLY       akcli draw <target> --ops <ops.json> --apply --strict-nets --json
                 The receipt is captured verbatim and is never proof.
  4. POST-STATE  re-hash, re-parse with the same reader, re-export.
  5. VERDICT     exactly one of
                   APPLIED_VERIFIED          the declared delta is observable
                                             in the independent read-back
                   NO_OP_VERIFIED            nothing was declared AND the object
                                             graph did not move (equal bytes are
                                             not required, unequal bytes are not
                                             a failure either)
                   FAILED_UNOBSERVED_CHANGE  the receipt claims success but the
                                             read-back does not match the
                                             declared delta (the C4-P1 case)
                   FAILED_EXECUTION          non-zero akcli exit, writer refusal
                                             or malformed/unusable receipt

Why the read-back and not the receipt: akcli 0.21.0 add_wire with pure-coordinate
vertices reports applied=true / status="applied" / ops[0].status="ok" while
creating no wire at all (created_uuids: []).  On a fresh file the bytes DO change
(the writer injects normalization junctions) and on an already normalised file
they do not, so neither "hash changed" nor "hash unchanged" is a success signal.

Local design decisions (kept explicit because the verdict depends on them):

  * The object graph is read by the parser in this file: it imports nothing from
    akcli and nothing from gates/ (deliberately not the C2/C3 observation code,
    whose qualified profile rejects a file that carries junctions).
  * NO_OP_VERIFIED requires an empty object delta, not equal bytes: writer
    normalization may legitimately rewrite bytes while the caller declared
    nothing.  An undeclared object change (e.g. injected junctions) under an
    empty declaration is FAILED_UNOBSERVED_CHANGE - the writer mutated the
    artifact beyond what was authorized.
  * With a non-empty declaration, undeclared object changes are recorded under
    observed_delta["undeclared"] but the declared items decide the verdict.
  * kicadxml exports embed a date stamp, so netlist hashes are never compared;
    connectivity is compared semantically (pin -> net).
  * A writer refusal (--strict-nets exit 6, applied absent or false) is
    FAILED_EXECUTION: the requested change was not executed.
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree


SCHEMA = "aedl-akcli-adapter/1"

VERDICT_APPLIED_VERIFIED = "APPLIED_VERIFIED"
VERDICT_NO_OP_VERIFIED = "NO_OP_VERIFIED"
VERDICT_FAILED_UNOBSERVED_CHANGE = "FAILED_UNOBSERVED_CHANGE"
VERDICT_FAILED_EXECUTION = "FAILED_EXECUTION"
VERDICTS = (VERDICT_APPLIED_VERIFIED, VERDICT_NO_OP_VERIFIED,
            VERDICT_FAILED_UNOBSERVED_CHANGE, VERDICT_FAILED_EXECUTION)

EXIT_INPUT_ERROR = 2
EXIT_VERDICT = {VERDICT_APPLIED_VERIFIED: 0, VERDICT_NO_OP_VERIFIED: 0,
                VERDICT_FAILED_UNOBSERVED_CHANGE: 3, VERDICT_FAILED_EXECUTION: 4}

# The frozen apply command: --apply --strict-nets --json, matching the style the
# repository already uses for akcli (gates/run_gates.py: akcli ops validate --json).
DRAW_ARGUMENTS = ("draw",)
DEFAULT_AKCLI_FLAGS = ("--apply", "--strict-nets", "--json")
DRAW_TIMEOUT_SECONDS = 300
EXPORT_TIMEOUT_SECONDS = 180
EXPORT_ARGUMENTS = ("sch", "export", "netlist", "--format", "kicadxml", "--output")

LABEL_KINDS = ("label", "global_label", "hierarchical_label")
GRAPH_SECTIONS = ("wires", "junctions", "labels", "symbols", "no_connects")
MAX_DELTA_ITEMS = 500

EXPECTATION_KINDS = (
    "wire_appears", "wire_disappears", "wire_count_delta", "junction_count_delta",
    "label_appears", "label_disappears", "symbol_count_delta",
    "pins_shorted", "pins_split", "pin_on_net")

_DOMAIN_OF_KIND = {
    "wire_appears": "wires", "wire_disappears": "wires", "wire_count_delta": "wires",
    "junction_count_delta": "junctions",
    "label_appears": "labels", "label_disappears": "labels",
    "symbol_count_delta": "symbols",
    "pins_shorted": "nets", "pins_split": "nets", "pin_on_net": "nets",
}


class AdapterInputError(ValueError):
    """A caller-contract violation.  Never a verdict: the run does not start."""


# ---------------------------------------------------------------------------
# time / hashing / tool discovery
# ---------------------------------------------------------------------------

def utc_now():
    return (datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
            .isoformat().replace("+00:00", "Z"))


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path):
    with open(path, "rb") as handle:
        return sha256_bytes(handle.read())


def read_bytes(path):
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise AdapterInputError("unreadable artifact: %s" % exc)


def _key(value):
    """Stable JSON key for set membership (coordinates are already rounded)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _existing(candidates):
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def find_akcli(explicit=None):
    """Locate the pinned writer: explicit, AKCLI / AEDL_AKCLI, PATH, toolchain.

    A git worktree sits beside the toolchain directory, so both the repository
    root and its parent are searched for toolchain/py311/Scripts/akcli.exe.
    """
    candidates = []
    if explicit:
        candidates.append(explicit)
    for variable in ("AKCLI", "AEDL_AKCLI"):
        candidates.append(os.environ.get(variable))
    candidates.append(shutil.which("akcli"))
    root = repo_root()
    for base in (root, os.path.dirname(root)):
        candidates.append(os.path.join(base, "toolchain", "py311", "Scripts", "akcli.exe"))
    return _existing(candidates)


def find_kicad_cli(explicit=None):
    """Locate kicad-cli, the tool that produces the independent netlist."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    candidates.append(os.environ.get("KICAD_CLI"))
    candidates.append(shutil.which("kicad-cli"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for version in ("10.0", "8.0"):
            candidates.append(os.path.join(local, "Programs", "KiCad", version,
                                           "bin", "kicad-cli.exe"))
    return _existing(candidates)


def tool_version(executable):
    try:
        proc = subprocess.run([executable, "--version"], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"argv": [executable, "--version"], "exit_code": None, "version": None,
                "error": "%s: %s" % (type(exc).__name__, exc)}
    text = (proc.stdout or b"").decode("utf-8", "replace").strip()
    if not text:
        text = (proc.stderr or b"").decode("utf-8", "replace").strip()
    return {"argv": [executable, "--version"], "exit_code": proc.returncode,
            "version": text or None, "error": None}


# ---------------------------------------------------------------------------
# independent object-graph reader (this file own s-expression parser)
# ---------------------------------------------------------------------------

def parse_sexpr(text):
    """Read a KiCad s-expression document into nested lists.

    Strings keep their quotes so an atom can be told from a string.  Raises
    ValueError on unbalanced input: an unreadable artifact is never a verdict.
    """
    root = []
    stack = [root]
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char == "(":
            node = []
            stack[-1].append(node)
            stack.append(node)
            index += 1
        elif char == ")":
            if len(stack) == 1:
                raise ValueError("unbalanced close paren at offset %d" % index)
            stack.pop()
            index += 1
        elif char == chr(34):
            cursor = index + 1
            while cursor < length:
                if text[cursor] == chr(92):
                    cursor += 2
                    continue
                if text[cursor] == chr(34):
                    break
                cursor += 1
            if cursor >= length:
                raise ValueError("unterminated string at offset %d" % index)
            stack[-1].append(text[index:cursor + 1])
            index = cursor + 1
        elif char.isspace():
            index += 1
        else:
            cursor = index
            while (cursor < length and not text[cursor].isspace()
                   and text[cursor] not in "()" + chr(34)):
                cursor += 1
            stack[-1].append(text[index:cursor])
            index = cursor
    if len(stack) != 1:
        raise ValueError("unbalanced open paren: %d form(s) left open" % (len(stack) - 1))
    return root


def _unquote(atom):
    if isinstance(atom, str) and len(atom) >= 2 and atom[0] == chr(34) and atom[-1] == chr(34):
        return atom[1:-1]
    return atom


def _number(atom, label):
    try:
        return float(_unquote(atom))
    except (TypeError, ValueError):
        raise AdapterInputError("expected a number for %s, saw %r" % (label, atom))


def _child(node, name):
    for item in node:
        if isinstance(item, list) and item and _unquote(item[0]) == name:
            return item
    return None


def _children(node, name):
    return [item for item in node
            if isinstance(item, list) and item and _unquote(item[0]) == name]


def _point(node, label):
    if not node or len(node) < 3:
        raise AdapterInputError("malformed %s: %r" % (label, node))
    return [round(_number(node[1], label + ".x"), 3),
            round(_number(node[2], label + ".y"), 3)]


def _wire_points(node):
    pts = _child(node, "pts")
    if pts is None:
        raise AdapterInputError("a (wire ...) form carries no (pts ...)")
    points = [_point(item, "wire point") for item in _children(pts, "xy")]
    if len(points) != 2:
        raise AdapterInputError("unsupported wire geometry with %d points" % len(points))
    return sorted(points, key=_key)


def _placed_symbol(node):
    lib_id = _child(node, "lib_id")
    at = _child(node, "at")
    uuid_node = _child(node, "uuid")
    reference, value = None, None
    for prop in _children(node, "property"):
        if len(prop) < 3:
            continue
        name = _unquote(prop[1])
        if name == "Reference":
            reference = _unquote(prop[2])
        elif name == "Value":
            value = _unquote(prop[2])
    position = _point(at, "symbol at") if at is not None else None
    if position is not None and len(at) > 3:
        position = position + [round(_number(at[3], "symbol rotation"), 3)]
    return {"reference": reference, "value": value,
            "lib_id": _unquote(lib_id[1]) if lib_id and len(lib_id) > 1 else None,
            "at": position,
            "uuid": _unquote(uuid_node[1]) if uuid_node and len(uuid_node) > 1 else None}


def object_graph(path):
    """Independent read of the artifact object graph.

    Returns counts plus the full inventory of wire segments, junctions, labels
    and placed symbols.  Only root-level forms are objects: symbol definitions
    nested inside (lib_symbols ...) are not placements.
    """
    raw = read_bytes(path)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", "replace")
    roots = parse_sexpr(text)
    if len(roots) != 1 or not roots[0] or _unquote(roots[0][0]) != "kicad_sch":
        raise AdapterInputError("not a single kicad_sch document: %s" % path)
    wires, junctions, labels, symbols, no_connects = [], [], [], [], []
    for node in roots[0][1:]:
        if not isinstance(node, list) or not node:
            continue
        head = _unquote(node[0])
        if head == "wire":
            wires.append(_wire_points(node))
        elif head == "junction":
            junctions.append(_point(_child(node, "at"), "junction at"))
        elif head in LABEL_KINDS:
            at = _child(node, "at")
            labels.append({"kind": head,
                           "text": _unquote(node[1]) if len(node) > 1 else None,
                           "at": _point(at, "label at") if at is not None else None})
        elif head == "symbol":
            symbols.append(_placed_symbol(node))
        elif head == "no_connect":
            no_connects.append(_point(_child(node, "at"), "no_connect at"))
    graph = {
        "sha256": sha256_bytes(raw),
        "counts": {"wires": len(wires), "junctions": len(junctions),
                   "labels": len(labels), "symbols": len(symbols),
                   "no_connects": len(no_connects)},
        "labels_by_kind": {kind: sum(1 for item in labels if item["kind"] == kind)
                           for kind in LABEL_KINDS},
        "wires": sorted(wires, key=_key),
        "junctions": sorted(junctions, key=_key),
        "labels": sorted(labels, key=_key),
        "symbols": sorted(symbols, key=_key),
        "no_connects": sorted(no_connects, key=_key),
    }
    graph["graph_sha256"] = sha256_bytes(_key({
        "counts": graph["counts"], "wires": graph["wires"],
        "junctions": graph["junctions"], "labels": graph["labels"],
        "symbols": graph["symbols"], "no_connects": graph["no_connects"],
    }).encode("utf-8"))
    return graph


# ---------------------------------------------------------------------------
# independent fresh netlist export
# ---------------------------------------------------------------------------

def parse_netlist(raw):
    """Read one kicadxml export into connectivity: pin -> net, net -> members."""
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise AdapterInputError("unparseable netlist: %s" % exc)
    if root.tag != "export":
        raise AdapterInputError("unknown netlist root %r" % root.tag)
    components = {}
    section = root.find("components")
    if section is None:
        raise AdapterInputError("the netlist carries no component inventory")
    for comp in section.findall("comp"):
        reference = comp.get("ref")
        if not reference:
            raise AdapterInputError("an exported component carries no reference")
        numbers = []
        pins = comp.find("pins")
        if pins is not None:
            for pin in pins.findall("pin"):
                if pin.get("num"):
                    numbers.append(pin.get("num"))
        components[reference] = sorted(set(numbers))
    pins_on_net, net_members = {}, {}
    section = root.find("nets")
    if section is None:
        raise AdapterInputError("the netlist carries no net section")
    for net in section.findall("net"):
        name = net.get("name")
        if name is None:
            raise AdapterInputError("an exported net carries no name")
        members = []
        for node in net.findall("node"):
            reference, number = node.get("ref"), node.get("pin")
            if not reference or not number:
                raise AdapterInputError("an exported node is missing its identity")
            pins_on_net.setdefault(reference, {})[number] = name
            members.append("%s.%s" % (reference, number))
        net_members[name] = sorted(set(members))
    if not components or not pins_on_net or not net_members:
        raise AdapterInputError("empty component or connectivity view is not independently evaluable")
    return {"components": components, "pins_on_net": pins_on_net,
            "net_members": net_members, "net_count": len(net_members),
            "component_count": len(components),
            "pin_count": sum(len(item) for item in pins_on_net.values())}


def native_import_issues(source, version):
    """KiCad 8 stops consuming root objects after legacy symbol_instances.

    A successful but truncated export is not a valid observation. The caller
    must perform separately recorded format ingestion, never an electrical fix.
    """
    if not str(version).startswith('8.'):
        return []
    roots = parse_sexpr(read_bytes(source).decode('utf-8'))
    if len(roots) != 1 or not roots[0] or roots[0][0] != 'kicad_sch':
        raise AdapterInputError('not a single kicad_sch document')
    forms = roots[0][1:]
    issues = []
    for index, form in enumerate(forms):
        if isinstance(form, list) and form and form[0] == 'symbol_instances':
            tail = [f[0] for f in forms[index+1:] if isinstance(f, list) and f]
            if tail:
                issues.append(dict(code='LEGACY_INSTANCE_TAIL', root_index=index,
                                   empty=(len(form) == 1), ignored_root_forms=tail))
    return issues


def export_netlist(source, output_dir, kicad_cli=None, timeout=EXPORT_TIMEOUT_SECONDS):
    """One fresh export into a directory this run creates.

    A leftover directory or XML is never reused.  The source hash is taken
    before the process, after it and after parsing; a change in between makes
    the export unbound.  The export carries a date stamp, so the returned hash
    is provenance, never a comparison key.
    """
    if os.path.exists(output_dir):
        raise AdapterInputError("the export directory must be created by this run: "
                                "%s already exists" % output_dir)
    result = {"status": "FAIL", "reason": None, "argv": None, "exit_code": None,
              "xml_path": None, "xml_sha256": None, "connectivity": None,
              "source_before_sha256": None, "source_after_sha256": None,
              "source_parse_end_sha256": None, "kicad_cli": None, "version": None}
    executable = find_kicad_cli(kicad_cli)
    if executable is None:
        result["reason"] = "kicad-cli is unavailable: no independent netlist can be exported"
        return result
    result["kicad_cli"] = executable
    result["version"] = tool_version(executable)["version"]
    try:
        result['source_before_sha256'] = sha256_file(source)
        result['native_import_issues'] = native_import_issues(source, result['version'])
    except (ValueError, OSError) as exc:
        result['reason'] = 'native import preflight failed: %s' % exc
        return result
    if result['native_import_issues']:
        result['reason'] = 'LEGACY_INSTANCE_TAIL: KiCad 8 would omit trailing root objects'
        return result
    os.makedirs(output_dir)
    xml_path = os.path.join(output_dir, "netlist.xml")
    argv = [executable] + list(EXPORT_ARGUMENTS) + [xml_path, source]
    result["argv"] = argv
    before = sha256_file(source)
    try:
        proc = subprocess.run(argv, shell=False,
                              cwd=os.path.dirname(os.path.abspath(source)),
                              timeout=timeout, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        exit_code = proc.returncode
        stderr = (proc.stderr or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        result["reason"] = "the fresh export exceeded %ds" % timeout
        return result
    except OSError as exc:
        result["reason"] = "the fresh export could not start: %s" % exc
        return result
    after = sha256_file(source)
    result["source_before_sha256"] = before
    result["exit_code"] = exit_code
    if before != after:
        result["source_after_sha256"] = after
        result["reason"] = "the artifact changed while it was exported"
        return result
    if exit_code != 0:
        result["reason"] = "kicad-cli exited %s: %s" % (exit_code, stderr.strip()[:400])
        return result
    raw = read_bytes(xml_path) if os.path.isfile(xml_path) else b""
    if not raw:
        result["reason"] = "exit=0 produced no netlist file"
        return result
    try:
        connectivity = parse_netlist(raw)
    except AdapterInputError as exc:
        result["reason"] = str(exc)
        return result
    final = sha256_file(source)
    result["source_parse_end_sha256"] = final
    if final != before:
        result["reason"] = "the artifact changed while the export was parsed"
        return result
    result.update(status="PASS", reason=None, xml_path=xml_path,
                  xml_sha256=sha256_bytes(raw), connectivity=connectivity)
    return result


# ---------------------------------------------------------------------------
# declared (never observed) expectation
# ---------------------------------------------------------------------------

def _expectation_points(value, label):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise AdapterInputError("%s must be two [x, y] endpoints" % label)
    points = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise AdapterInputError("%s must be two [x, y] endpoints" % label)
        for coordinate in point:
            if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
                raise AdapterInputError("%s coordinates must be numbers" % label)
        points.append([round(float(point[0]), 3), round(float(point[1]), 3)])
    return sorted(points, key=_key)


def _pin_name(value, label):
    if not isinstance(value, str) or "." not in value:
        raise AdapterInputError("%s must be REFERENCE.PIN, saw %r" % (label, value))
    reference, number = value.rsplit(".", 1)
    if not reference or not number:
        raise AdapterInputError("%s must be REFERENCE.PIN, saw %r" % (label, value))
    return reference, number


def normalize_expectation(declared):
    """Validate the caller declared delta.  Never derived from a receipt."""
    if declared is None:
        raise AdapterInputError(
            "an op list without a declared expectation is rejected: pass "
            "expect=[] to declare an idempotent no-op")
    if not isinstance(declared, (list, tuple)):
        raise AdapterInputError("the declared delta must be a list of expectations")
    normalized = []
    for item in declared:
        if not isinstance(item, dict):
            raise AdapterInputError("every expectation must be an object, saw %r" % (item,))
        kind = item.get("kind")
        if kind not in EXPECTATION_KINDS:
            raise AdapterInputError("unknown expectation kind %r (known: %s)"
                                    % (kind, ", ".join(EXPECTATION_KINDS)))
        entry = {"kind": kind}
        if kind in ("wire_appears", "wire_disappears"):
            entry["endpoints"] = _expectation_points(item.get("endpoints"), kind)
        elif kind in ("wire_count_delta", "junction_count_delta", "symbol_count_delta"):
            value = item.get("value")
            if isinstance(value, bool) or not isinstance(value, int):
                raise AdapterInputError("%s.value must be an integer" % kind)
            entry["value"] = value
        elif kind in ("label_appears", "label_disappears"):
            text = item.get("text")
            if not isinstance(text, str) or not text:
                raise AdapterInputError("%s.text must be a non-empty string" % kind)
            entry["text"] = text
            if item.get("label_kind") is not None:
                if item["label_kind"] not in LABEL_KINDS:
                    raise AdapterInputError("unknown label_kind %r" % item["label_kind"])
                entry["label_kind"] = item["label_kind"]
        elif kind in ("pins_shorted", "pins_split"):
            a = _pin_name(item.get("a"), kind + ".a")
            b = _pin_name(item.get("b"), kind + ".b")
            if a == b:
                raise AdapterInputError("%s needs two different pins" % kind)
            entry["a"], entry["b"] = list(a), list(b)
        elif kind == "pin_on_net":
            reference, number = item.get("reference"), item.get("pin")
            if not isinstance(reference, str) or not reference:
                raise AdapterInputError("pin_on_net.reference must be a reference")
            if not isinstance(number, str) or not number:
                raise AdapterInputError("pin_on_net.pin must be a pin number")
            net = item.get("net")
            if not isinstance(net, str) or not net:
                raise AdapterInputError("pin_on_net.net must be a non-empty string")
            entry["reference"], entry["pin"], entry["net"] = reference, number, net
        normalized.append(entry)
    return normalized


def authorized_delta_sha256(declared):
    return sha256_bytes(_key(declared).encode("utf-8"))


# ---------------------------------------------------------------------------
# observed delta
# ---------------------------------------------------------------------------

def _section_delta(before, after):
    before_keys = {_key(item): item for item in before}
    after_keys = {_key(item): item for item in after}
    return {
        "added": [after_keys[key] for key in sorted(after_keys) if key not in before_keys],
        "removed": [before_keys[key] for key in sorted(before_keys) if key not in after_keys],
        "count_before": len(before), "count_after": len(after),
    }


def _net_delta(pre, post):
    pre_nets, post_nets = pre["net_members"], post["net_members"]
    pins_moved, truncated = [], False
    for reference in sorted(set(pre["pins_on_net"]) | set(post["pins_on_net"])):
        before_pins = pre["pins_on_net"].get(reference, {})
        after_pins = post["pins_on_net"].get(reference, {})
        for number in sorted(set(before_pins) | set(after_pins)):
            before_name, after_name = before_pins.get(number), after_pins.get(number)
            if before_name == after_name:
                continue
            if len(pins_moved) >= MAX_DELTA_ITEMS:
                truncated = True
                break
            pins_moved.append({"reference": reference, "pin": number,
                               "before": before_name, "after": after_name})
    changed = sorted([{"net": name, "before": pre_nets[name], "after": post_nets[name]}
                      for name in set(pre_nets) & set(post_nets)
                      if pre_nets[name] != post_nets[name]], key=_key)
    return {
        "nets_added": sorted(name for name in post_nets if name not in pre_nets),
        "nets_removed": sorted(name for name in pre_nets if name not in post_nets),
        "net_members_changed": changed[:MAX_DELTA_ITEMS],
        "pins_moved_net": pins_moved,
        "pins_moved_net_truncated": truncated,
        "net_count_before": pre["net_count"], "net_count_after": post["net_count"],
    }


def observed_delta(pre_graph, post_graph, pre_conn, post_conn, declared=()):
    delta = {"bytes_changed": pre_graph["sha256"] != post_graph["sha256"]}
    for domain in GRAPH_SECTIONS:
        delta[domain] = _section_delta(pre_graph[domain], post_graph[domain])
    delta["netlist"] = _net_delta(pre_conn, post_conn)
    object_changed = any(delta[domain]["added"] or delta[domain]["removed"]
                         for domain in GRAPH_SECTIONS)
    netlist = delta["netlist"]
    nets_changed = bool(netlist["nets_added"] or netlist["nets_removed"]
                        or netlist["pins_moved_net"] or netlist["net_members_changed"])
    delta["object_changed"] = object_changed
    delta["nets_changed"] = nets_changed
    delta["empty"] = not object_changed and not nets_changed
    declared_domains = {_DOMAIN_OF_KIND[item["kind"]] for item in declared}
    undeclared = {}
    for domain in GRAPH_SECTIONS:
        if domain in declared_domains:
            continue
        if delta[domain]["added"] or delta[domain]["removed"]:
            undeclared[domain] = {"added": delta[domain]["added"],
                                  "removed": delta[domain]["removed"]}
    if "nets" not in declared_domains and any(
            netlist[key] for key in ("nets_added", "nets_removed",
                                     "net_members_changed", "pins_moved_net")):
        undeclared["nets"] = {key: netlist[key] for key in
                              ("nets_added", "nets_removed", "net_members_changed",
                               "pins_moved_net")}
    delta["undeclared"] = undeclared
    return delta


# ---------------------------------------------------------------------------
# expectation checks against the independent read-back
# ---------------------------------------------------------------------------

def _wire_present(graph, endpoints):
    key = _key(endpoints)
    return key in {_key(item) for item in graph["wires"]}


def _label_present(graph, text, label_kind=None):
    return any(item["text"] == text and (label_kind is None or item["kind"] == label_kind)
               for item in graph["labels"])


def _net_of(connectivity, reference, number):
    return connectivity["pins_on_net"].get(reference, {}).get(number)


def check_expectation(entry, pre_graph, post_graph, pre_conn, post_conn):
    """One declared item against the pre/post independent observations."""
    kind = entry["kind"]
    check = {"kind": kind, "declared": entry, "ok": False, "detail": ""}
    if kind == "wire_appears":
        was = _wire_present(pre_graph, entry["endpoints"])
        now = _wire_present(post_graph, entry["endpoints"])
        check.update(ok=(not was) and now,
                     detail="wire %s present before: %s, present after: %s"
                     % (_key(entry["endpoints"]), was, now))
    elif kind == "wire_disappears":
        was = _wire_present(pre_graph, entry["endpoints"])
        still = _wire_present(post_graph, entry["endpoints"])
        check.update(ok=was and not still,
                     detail="wire %s present before: %s, present after: %s"
                     % (_key(entry["endpoints"]), was, still))
    elif kind == "wire_count_delta":
        moved = post_graph["counts"]["wires"] - pre_graph["counts"]["wires"]
        check.update(ok=moved == entry["value"],
                     detail="wire count %d -> %d (delta %d, declared %d)"
                     % (pre_graph["counts"]["wires"], post_graph["counts"]["wires"],
                        moved, entry["value"]))
    elif kind == "junction_count_delta":
        moved = post_graph["counts"]["junctions"] - pre_graph["counts"]["junctions"]
        check.update(ok=moved == entry["value"],
                     detail="junction count %d -> %d (delta %d, declared %d)"
                     % (pre_graph["counts"]["junctions"], post_graph["counts"]["junctions"],
                        moved, entry["value"]))
    elif kind == "symbol_count_delta":
        moved = post_graph["counts"]["symbols"] - pre_graph["counts"]["symbols"]
        check.update(ok=moved == entry["value"],
                     detail="symbol count %d -> %d (delta %d, declared %d)"
                     % (pre_graph["counts"]["symbols"], post_graph["counts"]["symbols"],
                        moved, entry["value"]))
    elif kind in ("label_appears", "label_disappears"):
        text, label_kind = entry["text"], entry.get("label_kind")
        before = _label_present(pre_graph, text, label_kind)
        after = _label_present(post_graph, text, label_kind)
        want = (not before) and after if kind == "label_appears" else before and not after
        check.update(ok=want, detail="label %r present before: %s, after: %s"
                     % (text, before, after))
    elif kind in ("pins_shorted", "pins_split"):
        (ref_a, pin_a), (ref_b, pin_b) = entry["a"], entry["b"]
        identities = [_net_of(conn, ref, pin) for conn in (pre_conn, post_conn)
                      for ref, pin in ((ref_a, pin_a), (ref_b, pin_b))]
        if any(name is None for name in identities):
            check["detail"] = "both pin identities must exist in both fresh exports"
            return check
        before = _net_of(pre_conn, ref_a, pin_a) == _net_of(pre_conn, ref_b, pin_b)
        after = _net_of(post_conn, ref_a, pin_a) == _net_of(post_conn, ref_b, pin_b)
        want = (not before) and after if kind == "pins_shorted" else before and not after
        check.update(ok=want,
                     detail="%s.%s / %s.%s on the same net before: %s, after: %s"
                     % (ref_a, pin_a, ref_b, pin_b, before, after))
    elif kind == "pin_on_net":
        observed = _net_of(post_conn, entry["reference"], entry["pin"])
        check.update(ok=observed == entry["net"],
                     detail="%s.%s net after: %r (declared %r)"
                     % (entry["reference"], entry["pin"], observed, entry["net"]))
    return check


# ---------------------------------------------------------------------------
# the apply path
# ---------------------------------------------------------------------------

def _reason(code, detail):
    return {"code": code, "detail": detail}


def _write_json(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write(chr(10))
    return path


def persist_record(record, record_dir):
    """Persist receipt, hashes, graph summaries, observed delta, export paths,
    the verdict and every raw artifact a batch run needs to be auditable."""
    if not record_dir:
        raise AdapterInputError("a record directory is required for an apply")
    if not os.path.isdir(record_dir):
        raise AdapterInputError("the record directory is created by the caller: %s"
                                % record_dir)
    paths = {}
    paths["record"] = _write_json(os.path.join(record_dir, "record.json"), record)
    if record.get("receipt") is not None:
        paths["receipt"] = _write_json(os.path.join(record_dir, "receipt.json"),
                                       record["receipt"])
    if record.get("pre"):
        paths["pre_graph"] = _write_json(os.path.join(record_dir, "pre_graph.json"),
                                         record["pre"]["graph"])
    if record.get("post"):
        paths["post_graph"] = _write_json(os.path.join(record_dir, "post_graph.json"),
                                          record["post"]["graph"])
    if record.get("observed_delta") is not None:
        paths["observed_delta"] = _write_json(
            os.path.join(record_dir, "observed_delta.json"), record["observed_delta"])
    pre = record.get("pre") or {}
    post = record.get("post") or {}
    paths["verdict"] = _write_json(
        os.path.join(record_dir, "verdict.json"),
        {"schema": SCHEMA, "recorded_at": record["recorded_at"],
         "label": record.get("label"), "target": record["target"],
         "verdict": record["verdict"], "reasons": record["reasons"],
         "pre_sha256": pre.get("sha256"), "post_sha256": post.get("sha256"),
         "authorized_delta_sha256": record["authorized_delta_sha256"],
         "declared_expectation": record["declared_expectation"],
         "expectation_checks": record.get("expectation_checks", []),
         "pre_netlist": (pre.get("netlist") or {}).get("xml_path"),
         "post_netlist": (post.get("netlist") or {}).get("xml_path"),
         "record": os.path.abspath(paths["record"])})
    return paths


def apply_and_verify(request):
    """The C4 apply path.  Returns the audited record; never returns unverified.

    request keys:
      target        path of the .kicad_sch artifact (required)
      ops           the akcli op-list document (required)
      expect        the declared delta (required; [] declares a no-op)
      record_dir    new directory for the audit record (required)
      strict_nets   use the frozen --strict-nets policy (default True)
      extra_args    extra akcli arguments, e.g. ["--no-erc"] (optional)
      akcli / kicad_cli  explicit tool paths (optional)
      label         human label for the run (optional)
    """
    target = request.get("target")
    if not target or not isinstance(target, str):
        raise AdapterInputError("request.target must be a path")
    target = os.path.abspath(target)
    if not os.path.isfile(target):
        raise AdapterInputError("request.target is not a file: %s" % target)
    ops = request.get("ops")
    if not isinstance(ops, dict) or not isinstance(ops.get("ops"), list):
        raise AdapterInputError("request.ops must be an op-list document with an ops list")
    declared = normalize_expectation(request.get("expect"))
    record_dir = request.get("record_dir")
    if not record_dir:
        raise AdapterInputError("request.record_dir is required for an audited apply")
    record_dir = os.path.abspath(record_dir)
    if os.path.exists(record_dir):
        raise AdapterInputError("the record directory must be new: %s already exists"
                                % record_dir)
    os.makedirs(record_dir)
    strict_nets = request.get("strict_nets", True)
    extra_args = [str(item) for item in (request.get("extra_args") or [])]
    executable = find_akcli(request.get("akcli"))
    if executable is None:
        raise AdapterInputError("no akcli executable found (set AKCLI or pass akcli=)")

    record = {"schema": SCHEMA, "recorded_at": utc_now(), "label": request.get("label"),
              "target": target, "record_dir": record_dir,
              "declared_expectation": declared,
              "authorized_delta_sha256": authorized_delta_sha256(declared),
              "strict_nets": bool(strict_nets), "extra_args": extra_args,
              "verdict": None, "reasons": [], "receipt": None, "receipt_sha256": None,
              "akcli": None, "pre": None, "post": None, "observed_delta": None,
              "expectation_checks": [], "artifacts": {}}
    _write_json(os.path.join(record_dir, "declared_expectation.json"),
                {"declared_expectation": declared,
                 "authorized_delta_sha256": record["authorized_delta_sha256"]})
    ops_path = _write_json(os.path.join(record_dir, "ops.json"), ops)

    # ---- 1. PRE-STATE -----------------------------------------------------
    pre_graph = object_graph(target)
    pre_export = export_netlist(target, os.path.join(record_dir, "netlist-pre"),
                                request.get("kicad_cli"))
    record["pre"] = {"sha256": pre_graph["sha256"], "graph": pre_graph,
                     "netlist": {"xml_path": pre_export["xml_path"],
                                 "xml_sha256": pre_export["xml_sha256"],
                                 "status": pre_export["status"],
                                 "kicad_cli": pre_export["kicad_cli"],
                                 "kicad_version": pre_export["version"],
                                 "argv": pre_export["argv"]}}
    if pre_export["status"] != "PASS":
        record["verdict"] = VERDICT_FAILED_EXECUTION
        record["reasons"] = [_reason("PRE_EXPORT_FAILED",
                                     "the pre-state netlist export failed: %s"
                                     % pre_export["reason"])]
        record["artifacts"] = persist_record(record, record_dir)
        return record

    # ---- 2/3. AUTHORIZED DELTA then APPLY ----------------------------------
    flags = list(DEFAULT_AKCLI_FLAGS) if strict_nets else ["--apply", "--json"]
    argv = [executable] + list(DRAW_ARGUMENTS) + [target, "--ops", ops_path] + flags + extra_args
    record["akcli"] = {"executable": executable,
                       "version": tool_version(executable)["version"],
                       "argv": argv, "exit_code": None, "stdout_sha256": None,
                       "stderr_sha256": None}
    try:
        proc = subprocess.run(argv, shell=False, cwd=os.path.dirname(target),
                              timeout=DRAW_TIMEOUT_SECONDS,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = proc.stdout or b""
        stderr = proc.stderr or b""
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        record["verdict"] = VERDICT_FAILED_EXECUTION
        record["reasons"] = [_reason("AKCLI_TIMEOUT",
                                     "akcli exceeded %ds" % DRAW_TIMEOUT_SECONDS)]
        record["artifacts"] = persist_record(record, record_dir)
        return record
    except OSError as exc:
        record["verdict"] = VERDICT_FAILED_EXECUTION
        record["reasons"] = [_reason("AKCLI_UNSTARTABLE",
                                     "akcli could not start: %s" % exc)]
        record["artifacts"] = persist_record(record, record_dir)
        return record
    record["akcli"].update(exit_code=exit_code, stdout_sha256=sha256_bytes(stdout),
                           stderr_sha256=sha256_bytes(stderr))
    with open(os.path.join(record_dir, "akcli_stdout.txt"), "wb") as handle:
        handle.write(stdout)
    with open(os.path.join(record_dir, "akcli_stderr.txt"), "wb") as handle:
        handle.write(stderr)
    receipt, receipt_error = None, None
    try:
        receipt = json.loads(stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        receipt_error = "akcli produced no JSON receipt (%s)" % exc
    if exit_code != 0:
        detail = "akcli exited %s" % exit_code
        if isinstance(receipt, dict) and isinstance(receipt.get("error"), dict):
            detail += ": %s" % receipt["error"].get("message")
        record["receipt"] = receipt
        if isinstance(receipt, dict):
            record["receipt_sha256"] = sha256_bytes(_key(receipt).encode("utf-8"))
        record["verdict"] = VERDICT_FAILED_EXECUTION
        record["reasons"] = [_reason("AKCLI_EXIT", detail)]
        record["artifacts"] = persist_record(record, record_dir)
        return record
    if receipt_error or not isinstance(receipt, dict):
        record["verdict"] = VERDICT_FAILED_EXECUTION
        record["reasons"] = [_reason("MALFORMED_RECEIPT",
                                     receipt_error or "the receipt is not an object")]
        record["artifacts"] = persist_record(record, record_dir)
        return record
    record["receipt"] = receipt
    record["receipt_sha256"] = sha256_bytes(_key(receipt).encode("utf-8"))
    if receipt.get("applied") is not True:
        record["verdict"] = VERDICT_FAILED_EXECUTION
        record["reasons"] = [_reason("AKCLI_NOT_APPLIED",
                                     "exit=0 but the receipt does not claim applied=true "
                                     "(status=%r)" % receipt.get("status"))]
        record["artifacts"] = persist_record(record, record_dir)
        return record

    # ---- 4. POST-STATE -----------------------------------------------------
    post_graph = object_graph(target)
    post_export = export_netlist(target, os.path.join(record_dir, "netlist-post"),
                                 request.get("kicad_cli"))
    record["post"] = {"sha256": post_graph["sha256"], "graph": post_graph,
                      "netlist": {"xml_path": post_export["xml_path"],
                                  "xml_sha256": post_export["xml_sha256"],
                                  "status": post_export["status"],
                                  "kicad_cli": post_export["kicad_cli"],
                                  "kicad_version": post_export["version"],
                                  "argv": post_export["argv"]}}
    if post_export["status"] != "PASS":
        record["verdict"] = VERDICT_FAILED_EXECUTION
        record["reasons"] = [_reason("POST_EXPORT_FAILED",
                                     "the post-state netlist export failed: %s"
                                     % post_export["reason"])]
        record["artifacts"] = persist_record(record, record_dir)
        return record

    # ---- 5. VERDICT --------------------------------------------------------
    delta = observed_delta(pre_graph, post_graph, pre_export["connectivity"],
                           post_export["connectivity"], declared)
    checks = [check_expectation(item, pre_graph, post_graph,
                                pre_export["connectivity"], post_export["connectivity"])
              for item in declared]
    record["observed_delta"] = delta
    record["expectation_checks"] = checks
    if not declared:
        if delta["empty"]:
            record["verdict"] = VERDICT_NO_OP_VERIFIED
            record["reasons"] = [_reason(
                "NOTHING_DECLARED_NOTHING_MOVED",
                "the declared delta is empty and the independent read-back shows no "
                "object or net change (bytes changed: %s)" % delta["bytes_changed"])]
        else:
            record["verdict"] = VERDICT_FAILED_UNOBSERVED_CHANGE
            record["reasons"] = [_reason(
                "UNDECLARED_CHANGE",
                "the declared delta is empty but the artifact changed: %s"
                % ", ".join(sorted(delta["undeclared"])))]
    else:
        failed = [item for item in checks if not item["ok"]]
        if not failed:
            record["verdict"] = VERDICT_APPLIED_VERIFIED
            record["reasons"] = [_reason(
                "DECLARED_DELTA_OBSERVED",
                "all %d declared expectation(s) are observable in the independent "
                "read-back" % len(checks))]
        else:
            record["verdict"] = VERDICT_FAILED_UNOBSERVED_CHANGE
            record["reasons"] = [_reason("DECLARED_DELTA_NOT_OBSERVED", item["detail"])
                                 for item in failed]
            record["reasons"].append(_reason(
                "RECEIPT_CONTRADICTED",
                "the receipt claims applied=true while the read-back does not show the "
                "declared delta (a receipt is not evidence)"))
    record["artifacts"] = persist_record(record, record_dir)
    return record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_json(path, label):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise AdapterInputError("cannot read %s %s: %s" % (label, path, exc))
    except ValueError as exc:
        raise AdapterInputError("%s %s is not JSON: %s" % (label, path, exc))


def observe_command(args):
    graph = object_graph(args.target)
    summary = {"target": os.path.abspath(args.target), "sha256": graph["sha256"],
               "graph_sha256": graph["graph_sha256"], "counts": graph["counts"],
               "labels_by_kind": graph["labels_by_kind"]}
    if args.netlist:
        export = export_netlist(os.path.abspath(args.target), args.netlist, args.kicad_cli)
        connectivity = export["connectivity"] or {}
        summary["netlist"] = {"status": export["status"], "reason": export["reason"],
                              "xml_path": export["xml_path"],
                              "xml_sha256": export["xml_sha256"],
                              "kicad_cli": export["kicad_cli"],
                              "version": export["version"],
                              "net_count": connectivity.get("net_count"),
                              "component_count": connectivity.get("component_count")}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def apply_command(args):
    record = apply_and_verify({
        "target": args.target,
        "ops": _load_json(args.ops, "op-list"),
        "expect": _load_json(args.expect, "declared expectation"),
        "record_dir": args.record_dir,
        "strict_nets": not args.no_strict_nets,
        "extra_args": args.extra_args or [],
        "akcli": args.akcli,
        "kicad_cli": args.kicad_cli,
        "label": args.label,
    })
    if args.json:
        print(json.dumps(record, indent=2, ensure_ascii=False))
    else:
        print("VERDICT: %s" % record["verdict"])
        for reason in record["reasons"]:
            print("  %s: %s" % (reason["code"], reason["detail"]))
        print("  record: %s" % record["artifacts"].get("record"))
    return EXIT_VERDICT[record["verdict"]]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m tools.akcli_adapter",
        description="Apply an akcli op-list and decide the outcome from an "
                    "independent read-back, never from the writer receipt.")
    subparsers = parser.add_subparsers(dest="command")

    observe = subparsers.add_parser("observe", help="read one artifact independently")
    observe.add_argument("--target", required=True)
    observe.add_argument("--netlist", default=None,
                         help="export a fresh netlist into this new directory")
    observe.add_argument("--kicad-cli", default=None)
    observe.set_defaults(handler=observe_command)

    writer = subparsers.add_parser("apply", help="apply an op-list and verify it")
    writer.add_argument("--target", required=True)
    writer.add_argument("--ops", required=True,
                        help="akcli op-list JSON (protocol_version 2)")
    writer.add_argument("--expect", required=True,
                        help="declared delta JSON; an op-list without one is rejected, "
                             "[] declares an idempotent no-op")
    writer.add_argument("--record-dir", required=True,
                        help="new directory for the audit record (must not exist)")
    writer.add_argument("--label", default=None)
    writer.add_argument("--no-strict-nets", action="store_true",
                        help="relax the frozen --strict-nets policy (recorded)")
    writer.add_argument("--extra-args", nargs=argparse.REMAINDER, default=[],
                        help="extra akcli arguments, e.g. --no-erc (must come last)")
    writer.add_argument("--akcli", default=None)
    writer.add_argument("--kicad-cli", default=None)
    writer.add_argument("--json", action="store_true",
                        help="print the full audit record instead of a summary")
    writer.set_defaults(handler=apply_command)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return EXIT_INPUT_ERROR
    try:
        return args.handler(args)
    except AdapterInputError as exc:
        print("REFUSED (caller contract): %s" % exc, file=sys.stderr)
        return EXIT_INPUT_ERROR


if __name__ == "__main__":
    sys.exit(main())
