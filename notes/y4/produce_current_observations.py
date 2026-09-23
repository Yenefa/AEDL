"""Read-only current-state preparation; not C3 qualification or a repair executor.

The caller supplies a reviewed source candidate and an actual KiCad command
prefix. No existing observation/binding can be imported. Output is exclusively
created, with a generation record written last; failures leave no binding.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from tools.repair_pipeline import canonical_json_bytes, hash_bytes

PRODUCER_ID = 'kicad_xml_current_v1'


class ObservationError(ValueError):
    pass


def _required(element, attribute):
    value = element.get(attribute)
    if not value:
        raise ObservationError('missing XML attribute: ' + attribute)
    return value


def project_current_xml(raw):
    """Keep current netlist data, excluding source paths, timestamps and prose.

    Connectivity is the real KiCad export's node membership, never recomputed
    from expected topology. Components/nets are deterministic and answer-free
    by construction of the selected fields, subject to owner review of strings.
    """
    if not raw or len(raw) > 16 * 1024 * 1024:
        raise ObservationError('empty or oversized XML')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ObservationError('XML declarations/entities not allowed')
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ObservationError('invalid XML') from exc
    if root.tag != 'export':
        raise ObservationError('unexpected XML root')
    components = []
    seen_refs = set()
    for node in root.findall('./components/comp'):
        ref = _required(node, 'ref')
        if ref in seen_refs:
            raise ObservationError('duplicate component reference')
        seen_refs.add(ref)
        lib = node.find('libsource')
        if lib is None:
            raise ObservationError('missing component libsource')
        value = node.findtext('value')
        if value is None:
            raise ObservationError('missing component value')
        components.append({'ref': ref, 'value': value,
                           'footprint': node.findtext('footprint') or '',
                           'lib': _required(lib, 'lib'), 'part': _required(lib, 'part')})
    nets, seen_codes, seen_pins = [], set(), set()
    for net in root.findall('./nets/net'):
        code, name = _required(net, 'code'), _required(net, 'name')
        if code in seen_codes:
            raise ObservationError('duplicate net code')
        seen_codes.add(code)
        nodes = []
        for item in net.findall('node'):
            ref, pin = _required(item, 'ref'), _required(item, 'pin')
            if ref not in seen_refs or (ref, pin) in seen_pins:
                raise ObservationError('unknown or multiply-connected node')
            seen_pins.add((ref, pin))
            nodes.append({'ref': ref, 'pin': pin,
                          'pinfunction': item.get('pinfunction', ''),
                          'pintype': item.get('pintype', '')})
        if not nodes:
            raise ObservationError('net has no nodes')
        nets.append({'code': code, 'name': name,
                     'nodes': sorted(nodes, key=lambda n: (n['ref'], n['pin']))})
    if not components or not nets:
        raise ObservationError('empty components or nets')
    return {
        'observation_type': 'kicad_netlist_current.v1',
        'components': sorted(components, key=lambda c: c['ref']),
        'nets': sorted(nets, key=lambda n: (n['name'], n['code'])),
        'coverage': {
            'view': 'schematic_netlist', 'component_count': len(components),
            'net_count': len(nets), 'node_count': len(seen_pins),
            'limits': ['Exported schematic connectivity only; no ERC verdict.',
                       'No PCB, firmware runtime, electrical or thermal measurements.',
                       'Pins absent from this export have no asserted connection state.',
                       'No repair operation has been applied.'],
        },
    }


def _write_new(path, raw):
    with Path(path).open('xb') as stream:
        stream.write(raw)


def generate_current(source, output, command_prefix, path_mapper=str,
                     expected_source_sha256=None, timeout_seconds=120,
                     environment=None):
    """Export a new fixed snapshot, then produce its observation and binding.

    expected_source_sha256 pins the caller's selected source, but the binding
    source hash is computed from bytes actually read in this generation event.
    path_mapper supports WSL paths without executing a shell command string.
    """
    if Path(source).is_symlink():
        raise ObservationError('source is a symlink')
    source, output = Path(source).resolve(), Path(output).resolve()
    normalized = source.as_posix().lower()
    if '/private/' in normalized or source.name != 'fault.kicad_sch' and source.name != 'm2_board.kicad_sch':
        raise ObservationError('source is not an allowed candidate filename')
    if source.is_symlink() or not source.is_file():
        raise ObservationError('source is not a regular file')
    source_bytes = source.read_bytes()
    # Explicit logic, not assert: `python -O` strips assertions, and this check
    # is part of the fail-closed UTF-8/hash-domain guarantee.
    try:
        decoded = source_bytes.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ObservationError('source is not exact UTF-8') from exc
    if decoded.encode('utf-8') != source_bytes:
        raise ObservationError('source is not exact UTF-8')
    if not source_bytes or not source_bytes.lstrip().startswith(b'(kicad_sch'):
        raise ObservationError('source lacks a KiCad schematic header')
    source_digest = hash_bytes(source_bytes)
    if expected_source_sha256 is not None and source_digest != expected_source_sha256:
        raise ObservationError('selected source hash mismatch')
    # Source snapshots contain all embedded symbols for the current case
    # fixtures. Hierarchical sheets require additional bound inputs, outside
    # this producer.
    if re.search(rb'\(\s*sheet(?=\s|\))', source_bytes):
        raise ObservationError('hierarchical source needs separately bound sheets')
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'schematic.kicad_sch'
    xml = output / 'current.net.xml'
    _write_new(snapshot, source_bytes)
    started_at = datetime.now(timezone.utc).isoformat()
    command = list(command_prefix) + ['sch', 'export', 'netlist', '--format', 'kicadxml',
                                     '--output', path_mapper(xml), path_mapper(snapshot)]
    started = time.monotonic()
    with (output / 'export.stdout').open('xb') as stdout, (output / 'export.stderr').open('xb') as stderr:
        try:
            result = subprocess.run(command, stdout=stdout, stderr=stderr,
                                    timeout=timeout_seconds, env=environment)
        except subprocess.TimeoutExpired as exc:
            raise ObservationError('export timed out; no observation binding produced') from exc
    if result.returncode:
        raise ObservationError('native netlist export failed; no observation binding produced')
    if source.read_bytes() != source_bytes or snapshot.read_bytes() != source_bytes:
        raise ObservationError('source drift during export; regenerate from a fresh snapshot')
    xml_bytes = xml.read_bytes()
    observation = project_current_xml(xml_bytes)
    observation_raw = canonical_json_bytes(observation)
    binding = {'source_sha256': source_digest,
               'observation_sha256': hash_bytes(observation_raw), 'producer_id': PRODUCER_ID}
    # Recheck before publishing a binding, after reading and validating the export.
    if source.read_bytes() != source_bytes or snapshot.read_bytes() != source_bytes:
        raise ObservationError('source drift before binding publication')
    _write_new(output / 'current_observation.json', observation_raw)
    _write_new(output / 'observation_binding.json', canonical_json_bytes(binding))
    record = {
        'schema_version': 'y4-current-generation.v1', 'producer_id': PRODUCER_ID,
        'producer_file_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'started_at_utc': started_at, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_path_host_only': str(source), 'snapshot_file': snapshot.name,
        'source_sha256': source_digest, 'export_file': xml.name,
        'export_sha256': hash_bytes(xml_bytes), 'observation_binding': binding,
        'command_host_only': command, 'export_exit_code': result.returncode,
        'duration_ms': int((time.monotonic() - started) * 1000),
        'source_unchanged_after_export': True,
        'public_release_review': 'PENDING_OWNER_REVIEW',
        'independent_C3_qualification': 'NOT_RUN',
    }
    _write_new(output / 'generation-record.json', canonical_json_bytes(record))
    return record
