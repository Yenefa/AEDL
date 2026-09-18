"""Explicit DEV format ingestion -- never electrical repair or uplift.

Only an EMPTY legacy ``(symbol_instances)`` root block is removed.  Every other
root form and every source byte is preserved, hashed and classified, and a fresh
native observation plus a new manifest are written next to the originals.

Self-contained by design: this module imports neither the repair adapter nor the
repair chain, so DEV format ingestion carries no writer surface at all.  The
read-only helpers it needs (s-expression reader, object-graph inventory, fresh
netlist export, ERC export) are carried here and bound to this file's own hash.

Port note (2026-09-18 re-cut): the helpers below were extracted from the DEV
chain's old draft adapter so that ingestion no longer depends on it.  Behaviour
is preserved except that an unreadable `kicad-cli --version` now fails with the
documented recipe error instead of an AttributeError.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

EXPORT_TIMEOUT_SECONDS = 180
EXPORT_ARGUMENTS = ("sch", "export", "netlist", "--format", "kicadxml", "--output")
LABEL_KINDS = ("label", "global_label", "hierarchical_label")


class IngestionInputError(ValueError):
    """A caller-contract violation.  The ingestion does not start."""


# ---------------------------------------------------------------------------
# hashing / small IO
# ---------------------------------------------------------------------------

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
        raise IngestionInputError("unreadable artifact: %s" % exc)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n',
                          encoding='utf-8')


def _key(value):
    """Stable JSON key for set membership (coordinates are already rounded)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------------------
# tool discovery
# ---------------------------------------------------------------------------

def find_kicad_cli(explicit=None):
    """Locate kicad-cli, the tool that produces the independent netlist."""
    candidates = [explicit, os.environ.get("KICAD_CLI"), shutil.which("kicad-cli")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for version in ("10.0", "8.0"):
            candidates.append(os.path.join(local, "Programs", "KiCad", version,
                                           "bin", "kicad-cli.exe"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


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
# independent object-graph reader (this file's own s-expression parser)
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
        raise IngestionInputError("expected a number for %s, saw %r" % (label, atom))


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
        raise IngestionInputError("malformed %s: %r" % (label, node))
    return [round(_number(node[1], label + ".x"), 3),
            round(_number(node[2], label + ".y"), 3)]


def _wire_points(node):
    pts = _child(node, "pts")
    if pts is None:
        raise IngestionInputError("a (wire ...) form carries no (pts ...)")
    points = [_point(item, "wire point") for item in _children(pts, "xy")]
    if len(points) != 2:
        raise IngestionInputError("unsupported wire geometry with %d points" % len(points))
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
        raise IngestionInputError("not a single kicad_sch document: %s" % path)
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
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise IngestionInputError("unparseable netlist: %s" % exc)
    if root.tag != "export":
        raise IngestionInputError("unknown netlist root %r" % root.tag)
    components = {}
    section = root.find("components")
    if section is None:
        raise IngestionInputError("the netlist carries no component inventory")
    for comp in section.findall("comp"):
        reference = comp.get("ref")
        if not reference:
            raise IngestionInputError("an exported component carries no reference")
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
        raise IngestionInputError("the netlist carries no net section")
    for net in section.findall("net"):
        name = net.get("name")
        if name is None:
            raise IngestionInputError("an exported net carries no name")
        members = []
        for node in net.findall("node"):
            reference, number = node.get("ref"), node.get("pin")
            if not reference or not number:
                raise IngestionInputError("an exported node is missing its identity")
            pins_on_net.setdefault(reference, {})[number] = name
            members.append("%s.%s" % (reference, number))
        net_members[name] = sorted(set(members))
    if not components or not pins_on_net or not net_members:
        raise IngestionInputError("empty component or connectivity view is not independently evaluable")
    return {"components": components, "pins_on_net": pins_on_net,
            "net_members": net_members, "net_count": len(net_members),
            "component_count": len(components),
            "pin_count": sum(len(item) for item in pins_on_net.values())}


def validate_reference_netlist(raw, label="reference netlist"):
    """Read-only structural sanity for a kicadsexpr export.

    `exit 0` plus a file on disk is not an observation.  An empty, undecodable,
    structurally broken or signature-free export must never be published as a
    reference, so the bytes are re-read here instead of trusting the receipt.
    """
    if not raw:
        return dict(status="FAIL", reason="EMPTY_FILE", bytes=0, nets=0, nodes=0)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return dict(status="FAIL", reason="UNDECODABLE: %s" % exc, bytes=len(raw),
                    nets=0, nodes=0)
    try:
        roots = parse_sexpr(text)
    except ValueError as exc:
        return dict(status="FAIL", reason="UNPARSEABLE: %s" % exc, bytes=len(raw),
                    nets=0, nodes=0)
    if len(roots) != 1 or not isinstance(roots[0], list) or not roots[0]:
        return dict(status="FAIL", reason="NOT_ONE_ROOT", bytes=len(raw),
                    roots=len(roots), nets=0, nodes=0)
    head = _unquote(roots[0][0])
    if head != "export":
        return dict(status="FAIL", reason="UNEXPECTED_ROOT:%s" % head, bytes=len(raw),
                    roots=1, nets=0, nodes=0)
    nets_section = _child(roots[0], "nets")
    nets = _children(nets_section, "net") if nets_section is not None else []
    nodes = sum(len(_children(net, "node")) for net in nets)
    if not nets or nodes == 0:
        return dict(status="FAIL", reason="NO_SIGNATURE_BEARING_CONTENT", bytes=len(raw),
                    roots=1, nets=len(nets), nodes=nodes)
    return dict(status="PASS", reason=None, bytes=len(raw), roots=1,
                nets=len(nets), nodes=nodes)


def native_import_issues(source, version):
    """KiCad 8 stops consuming root objects after legacy symbol_instances.

    A successful but truncated export is not a valid observation. The caller
    must perform separately recorded format ingestion, never an electrical fix.
    """
    if not str(version).startswith('8.'):
        return []
    roots = parse_sexpr(read_bytes(source).decode('utf-8'))
    if len(roots) != 1 or not roots[0] or roots[0][0] != 'kicad_sch':
        raise IngestionInputError('not a single kicad_sch document')
    forms = roots[0][1:]
    issues = []
    for index, form in enumerate(forms):
        if isinstance(form, list) and form and form[0] == 'symbol_instances':
            tail = [f[0] for f in forms[index+1:] if isinstance(f, list) and f]
            if tail:
                issues.append(dict(code='LEGACY_INSTANCE_TAIL', root_index=index,
                                   empty=(len(form) == 1), ignored_root_forms=tail))
    return issues


def export_netlist(source, output_dir, kicad_cli=None, timeout=EXPORT_TIMEOUT_SECONDS,
                   binding=None):
    """One fresh export into a directory this run creates.

    A leftover directory or XML is never reused.  The source hash is taken
    before the process, after it and after parsing; a change in between makes
    the export unbound.  The export carries a date stamp, so the returned hash
    is provenance, never a comparison key.
    """
    if os.path.exists(output_dir):
        raise IngestionInputError("the export directory must be created by this run: "
                                  "%s already exists" % output_dir)
    result = {"status": "FAIL", "reason": None, "argv": None, "exit_code": None,
              "xml_path": None, "xml_sha256": None, "connectivity": None,
              "source_before_sha256": None, "source_after_sha256": None,
              "source_parse_end_sha256": None, "kicad_cli": None, "version": None,
              "kicad_cli_sha256": None, "kicad_cli_sha256_after": None}
    executable = find_kicad_cli(kicad_cli)
    if executable is None:
        result["reason"] = "kicad-cli is unavailable: no independent netlist can be exported"
        return result
    result["kicad_cli"] = executable
    result["version"] = tool_version(executable)["version"]
    if binding is None:
        try:
            binding = ToolchainBinding(executable)
        except IngestionInputError as exc:
            result["reason"] = str(exc)
            return result
    result["kicad_cli_sha256"] = binding.sha256
    try:
        result['source_before_sha256'] = sha256_file(source)
        result['native_import_issues'] = native_import_issues(source, result['version'])
    except (ValueError, OSError) as exc:
        result['reason'] = 'native import preflight failed: %s' % exc
        return result
    if result['native_import_issues']:
        result['reason'] = 'LEGACY_INSTANCE_TAIL: KiCad 8 would omit trailing root objects'
        return result
    try:
        binding.verify('before the netlist export')
    except IngestionInputError as exc:
        result['reason'] = str(exc)
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
    try:
        binding.verify('after the netlist export')
    except IngestionInputError as exc:
        result["reason"] = str(exc)
        return result
    result["kicad_cli_sha256_after"] = binding.sha256
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
    except IngestionInputError as exc:
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


def export_erc(source, directory, kicad_cli, binding=None):
    """One fresh ERC export; violations live under sheets[], not at the top."""
    directory.mkdir()
    output = directory / 'erc.json'
    digest = sha(source)
    argv = [kicad_cli, 'sch', 'erc', '--format', 'json', '--output', str(output), str(source)]
    result = dict(status='FAIL', source_sha256=digest, argv=argv)
    if binding is None:
        try:
            binding = ToolchainBinding(kicad_cli)
        except IngestionInputError as exc:
            result['error'] = str(exc)
            return result
    result['kicad_cli_sha256'] = binding.sha256
    try:
        binding.verify('before the ERC export')
        proc = subprocess.run(argv, capture_output=True, timeout=180)
        binding.verify('after the ERC export')
        result['kicad_cli_sha256_after'] = binding.sha256
        (directory/'stdout.txt').write_bytes(proc.stdout)
        (directory/'stderr.txt').write_bytes(proc.stderr)
        result['returncode'] = proc.returncode
        if proc.returncode != 0 or sha(source) != digest:
            return result
        doc = json.loads(output.read_text(encoding='utf-8'))
        sheets = doc['sheets']
        if not isinstance(sheets, list) or not sheets:
            return result
        violations = [v for sheet in sheets for v in sheet['violations']]
        flags = sorted((v['type'], v['severity'],
                        tuple(sorted(i['uuid'] for i in v['items']))) for v in violations)
        result.update(status='PASS', path=str(output), sha256=sha(output), flags=flags)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        result['error'] = str(exc)
    return result


# ---------------------------------------------------------------------------
# input manifest / format ingestion
# ---------------------------------------------------------------------------

def _file_digest(path):
    try:
        return sha256_file(path)
    except OSError:
        return None


class ToolchainBinding(object):
    """One ingestion run, one bound toolchain binary.

    Every subprocess that drives the toolchain is bracketed by a digest re-read.
    A binary that changed, or that can no longer be read at all, fails the run:
    "could not prove the toolchain is unchanged" is never reported as "no change
    was observed".
    """

    def __init__(self, path):
        self.path = str(path)
        self.sha256 = _file_digest(self.path)
        if self.sha256 is None:
            raise IngestionInputError("the toolchain binary cannot be read: %s" % self.path)

    def verify(self, when):
        current = _file_digest(self.path)
        if current is None:
            raise IngestionInputError(
                "the toolchain binary could not be rebound %s: %s" % (when, self.path))
        if current != self.sha256:
            raise IngestionInputError(
                "the toolchain binary changed %s: %s -> %s" % (when, self.sha256, current))
        return current


def validate_manifest(manifest):
    if set(manifest) != {'split', 'assignments'} or manifest['split'] != 'EXPOSED_DEV':
        raise ValueError('this command accepts an EXPOSED_DEV input manifest only')
    assignments = manifest['assignments']
    if not isinstance(assignments, list) or not assignments:
        raise ValueError('a nonempty assigned cohort is mandatory')
    ids = []
    for item in assignments:
        if set(item) != {'id', 'raw', 'raw_sha256', 'request', 'request_sha256'}:
            raise ValueError('repair inputs must contain only raw artifact and request bindings')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', item['id']):
            raise ValueError('unsafe design id')
        for key in ('raw_sha256', 'request_sha256'):
            if not re.fullmatch(r'[0-9a-f]{64}', item[key]):
                raise ValueError('invalid input digest')
        ids.append(item['id'])
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate assigned design id')
    return assignments


def _root_spans(text):
    spans, depth, start, quoted, escaped = [], 0, None, False, False
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == '(':
            if depth == 1:
                start = index
            depth += 1
        elif char == ')':
            if depth == 2:
                spans.append((start, index + 1))
            depth -= 1
    if depth or quoted:
        raise ValueError('unbalanced native document')
    return spans


def normalize_legacy_order(text):
    roots = parse_sexpr(text)
    if len(roots) != 1 or roots[0][0] != 'kicad_sch':
        raise ValueError('expected one native schematic root')
    forms = roots[0][1:]
    spans = _root_spans(text)
    if len(spans) != len(forms) or any(not isinstance(f, list) for f in forms):
        raise ValueError('unsupported root grammar')
    indexes = [i for i, f in enumerate(forms) if f and f[0] == 'symbol_instances']
    if not indexes:
        return text
    if len(indexes) != 1:
        raise ValueError('multiple legacy instance blocks are unsupported')
    index = indexes[0]
    if len(forms[index]) != 1:
        raise ValueError('nonempty instance metadata requires independent migration review')
    start, end = spans[index]
    # Keeping the empty terminator, even last, would truncate the next writer's
    # appended objects. Remove only this explicitly obsolete empty root block.
    result = text[:start] + text[end:]
    after = parse_sexpr(result)[0][1:]
    expected = forms[:index] + forms[index+1:]
    if Counter(json.dumps(f) for f in expected) != Counter(json.dumps(f) for f in after):
        raise ValueError('format ingestion changed a root form')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--manifest')
    inputs.add_argument('--reference-sources')
    parser.add_argument('--out', required=True)
    parser.add_argument('--kicad-cli', required=True)
    args = parser.parse_args(argv)
    reference_mode = args.reference_sources is not None
    input_path = args.reference_sources if reference_mode else args.manifest
    # Read once.  The parsed document, the recorded digest and the written
    # artifacts all derive from these exact bytes; the path is never read twice.
    manifest_raw = read_bytes(input_path)
    manifest = json.loads(manifest_raw.decode('utf-8-sig'))
    if reference_mode:
        if set(manifest) != {'split', 'assignments'} or manifest['split'] != 'EXPOSED_DEV_REFERENCE':
            raise ValueError('reference ingestion requires explicitly tagged reference inputs')
        assignments = manifest['assignments']
        if not isinstance(assignments, list) or not assignments:
            raise ValueError('empty reference assignments')
        for item in assignments:
            if (set(item) != {'id', 'raw', 'raw_sha256'} or
                    not re.fullmatch('[A-Za-z0-9_-]+', item['id']) or
                    not re.fullmatch('[0-9a-f]{64}', item['raw_sha256'])):
                raise ValueError('invalid reference binding')
        if len({d['id'] for d in assignments}) != len(assignments):
            raise ValueError('duplicate reference assignment')
    else:
        assignments = validate_manifest(manifest)
    # --kicad-cli is a required flag, so the explicit path is authoritative:
    # there is no PATH or installed-toolchain fallback for an ingestion run.
    executable = os.path.abspath(args.kicad_cli)
    if not os.path.isfile(executable):
        raise ValueError('the kicad-cli binary does not exist: %s' % args.kicad_cli)
    # One ingestion run binds exactly one toolchain binary.  Every subprocess --
    # including the version probe itself -- is bracketed by a digest re-read, so
    # a binary swapped in right after `--version` reported 8.0.9 can never become
    # the binary this run actually drives.  The same digest lands in every record
    # and in the run report, and a binary that cannot be re-read is a failure
    # rather than an unobserved change.
    binding = ToolchainBinding(executable)
    binding.verify('before the version probe')
    probe = tool_version(executable)
    binding.verify('after the version probe')
    if probe['exit_code'] != 0:
        raise ValueError('the kicad-cli version probe exited %s: %s'
                         % (probe['exit_code'], executable))
    version = (probe['version'] or '').strip()
    if version != '8.0.9':
        raise ValueError('this qualified ingestion recipe requires KiCad 8.0.9')
    root = Path(args.out).resolve()
    root.mkdir()
    records, ready, references = [], [], {}
    for item in assignments:
        directory = root/item['id']
        directory.mkdir()
        record = dict(id=item['id'], status='FAIL', formal_authorized=False,
                      electrical_repair=False, source_raw_sha256=item['raw_sha256'])
        try:
            # Bind, read and write the SAME bytes.  A separate hash pass over the
            # path followed by a copy pass could be fooled by a source path that
            # changes in between (TOCTOU): the record would then claim a digest the
            # copied artifact does not have.  There is no second read of the path.
            raw_bytes = read_bytes(item['raw'])
            if sha256_bytes(raw_bytes) != item['raw_sha256']:
                raise ValueError('input binding drift')
            original = directory/'original.kicad_sch'
            original.write_bytes(raw_bytes)
            if not reference_mode:
                request_bytes = read_bytes(item['request'])
                if sha256_bytes(request_bytes) != item['request_sha256']:
                    raise ValueError('request binding drift')
                (directory/'request.txt').write_bytes(request_bytes)
            prepared = directory/'input.kicad_sch'
            record['original_import_issues'] = native_import_issues(str(original), version)
            text = raw_bytes.decode('utf-8')
            prepared.write_bytes(normalize_legacy_order(text).encode('utf-8'))
            record['prepared_sha256'] = sha(prepared)
            record['classification'] = ('FORMAT_ADAPTER_TRANSLATION' if sha(original) != sha(prepared)
                                        else 'UNCHANGED_FORMAT')
            pre_graph, post_graph = object_graph(str(original)), object_graph(str(prepared))
            if pre_graph['graph_sha256'] != post_graph['graph_sha256']:
                raise ValueError('object graph changed during format ingestion')
            record['object_graph_unchanged'] = True
            record['native_export'] = export_netlist(str(prepared), str(directory/'native'),
                                                     executable, binding=binding)
            record['erc'] = export_erc(prepared, directory/'erc', executable, binding=binding)
            if record['native_export']['status'] != 'PASS' or record['erc']['status'] != 'PASS':
                raise ValueError('prepared native observation failed')
            record['status'] = 'READY_FOR_DEV'
            if reference_mode:
                net = directory/'reference.net'
                argv_export = [executable, 'sch', 'export', 'netlist', '--format',
                               'kicadsexpr', '--output', str(net), str(prepared)]
                binding.verify('before the reference scoring export')
                process = subprocess.run(argv_export, capture_output=True, timeout=180)
                binding.verify('after the reference scoring export')
                (directory/'score-export-stdout.txt').write_bytes(process.stdout)
                (directory/'score-export-stderr.txt').write_bytes(process.stderr)
                net_raw = read_bytes(net) if net.is_file() else b''
                if (process.returncode != 0
                        or sha(prepared) != record['prepared_sha256']
                        or not net_raw):
                    raise ValueError('reference scoring export failed')
                # exit 0 plus a file on disk is not an observation: an empty or
                # structureless reference must never reach the references manifest.
                sanity = validate_reference_netlist(net_raw)
                if sanity['status'] != 'PASS':
                    raise ValueError('reference scoring export is not evaluable: %s'
                                     % sanity['reason'])
                references[item['id']] = dict(path=str(net), sha256=sha256_bytes(net_raw),
                    bytes=len(net_raw), sanity=sanity,
                    native_source=str(prepared), native_source_sha256=sha(prepared))
                ready.append(item['id'])
            else:
                ready.append(dict(id=item['id'], raw=str(prepared), raw_sha256=sha(prepared),
                                  request=str(directory/'request.txt'), request_sha256=item['request_sha256']))
        except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            record['status'] = 'FAIL'
            record['error'] = str(exc)
        write_json(directory/'ingestion.json', record)
        records.append(record)
        print(item['id'], record['status'], record.get('classification'), flush=True)
    # Close the bracket: the toolchain must still be the one this run bound.
    # If it is not, no manifest may be published under an unbound toolchain.
    toolchain_error = None
    try:
        binding.verify('at the end of the ingestion run')
    except IngestionInputError as exc:
        toolchain_error = str(exc)
        ready = []
    report = dict(schema='aedl-schgen-dev-ingestion/1', N_assigned=len(assignments),
                  N_ready=len(ready), original_manifest_sha256=sha256_bytes(manifest_raw),
                  role='REFERENCE' if reference_mode else 'REPAIR_INPUT',
                  source_sha256=sha(__file__),
                  kicad_cli=executable, kicad_cli_version=version,
                  kicad_cli_sha256=binding.sha256,
                  toolchain_binding='FAILED' if toolchain_error else 'PASS',
                  toolchain_error=toolchain_error,
                  formal_authorized=False, records=records)
    write_json(root/'ingestion-report.json', report)
    # Do not silently drop failed assignments and publish a survivors cohort.
    if len(ready) == len(assignments):
        if reference_mode:
            write_json(root/'evaluation-references.json', references)
        else:
            write_json(root/'repair-inputs.json', dict(split='EXPOSED_DEV', assignments=ready))
        return 0
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
