"""Replay exposed DEV inputs only. No reference/scorer/generator dependencies.

The supported repair is deliberately narrow: attach an explicit request's named
net to an independently exported singleton unconnected pin. Ambiguous grammar,
rail aliases, existing-net rewiring and pin-pair repairs are not inferred.
"""
import argparse
import copy
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from tools import akcli_adapter as adapter


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


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


_DECLARATION = re.compile(
    r'(?:Connect\s+)?(?P<reference>[A-Z][A-Za-z0-9_]*)\s+pin\s+(?P<pin>\d+)'
    r'(?:\s*\([^()]*\))?\s+(?:connects?\s+to|is\s+connected\s+to|to|->|→)\s+'
    r'(?:net\s+label\s+|net\s+)?(?P<net>[A-Za-z_+][A-Za-z0-9_+./-]*)\.?', re.I)


def declarations(request):
    found = {}
    for number, raw_line in enumerate(request.splitlines(), 1):
        line = re.sub(r'[*`]', '', raw_line).strip().lstrip('- ').strip()
        match = _DECLARATION.fullmatch(line)
        if not match:
            continue
        item = match.groupdict()
        item['net'] = item['net'].rstrip('.')
        item['line'] = number
        key = (item['reference'], item['pin'])
        found.setdefault(key, []).append(item)
    return [items[0] for items in found.values()
            if len({item['net'] for item in items}) == 1]


def plan(request, connectivity):
    supported = []
    for item in declarations(request):
        net = connectivity['pins_on_net'].get(item['reference'], {}).get(item['pin'])
        if (net and net.startswith('unconnected-') and
                connectivity['net_members'].get(net) == [item['reference'] + '.' + item['pin']]):
            supported.append(item)
    return supported


def request_partition(request):
    """Read only a complete, strict Exact connectivity markdown section.

    This describes pin partitions, not component choice, polarity, rail aliases
    or a repair authorization. Any unsupported content invalidates the entire
    section so a conditional statement cannot become a partial contract.
    """
    lines = request.splitlines()
    starts = [i for i, line in enumerate(lines)
              if re.fullmatch(r'## Exact connectivity(?: I want \(by net\))?', line.strip(), re.I)]
    if not starts:
        return dict(status='ABSENT', groups=[])
    groups, active = [], None
    invalid = len(starts) != 1
    for number in range(starts[0] + 1, len(lines)):
        line = re.sub(r'[*`]', '', lines[number]).strip()
        if line.startswith('## ') or line == '---':
            break
        if not line:
            continue
        header = re.fullmatch(r'### Net ([A-Za-z_+][A-Za-z0-9_+./()\-]*)', line)
        if header:
            active = dict(net=header[1], pins=[], lines=[])
            groups.append(active)
            continue
        if active is None or not line.startswith('- '):
            invalid = True
            continue
        pins = []
        for token in line[2:].split('↔'):
            match = re.fullmatch(r'([A-Z][A-Za-z0-9_]*) pin (\d+)(?: \([^()]*\))?', token.strip())
            if not match:
                invalid = True
            else:
                pins.append(match[1] + '.' + match[2])
        active['pins'].extend(pins)
        active['lines'].append(number + 1)
    members = [pin for group in groups for pin in group['pins']]
    invalid |= (len(groups) < 2 or any(len(g['pins']) < 2 for g in groups)
                or len(members) != len(set(members))
                or len({g['net'] for g in groups}) != len(groups))
    return dict(status='UNSUPPORTED' if invalid else 'PARSED', groups=groups)


def audit_request_and_native(request, native_xml):
    """DEV preflight only; native pin metadata is not a datasheet oracle.

    Findings require review and block this label-only policy. No findings means
    only that these bounded checks found none; never electrical acceptance.
    References, scorer values, model responses and design IDs are not inputs.
    """
    contract = request_partition(request)
    findings, pins, power = [], {}, {}
    root = ET.parse(native_xml).getroot()
    for net in root.findall('./nets/net'):
        name = net.attrib['name']
        for node in net.findall('node'):
            ref, pin = node.attrib['ref'], node.attrib['pin']
            key = ref + '.' + pin
            if key in pins and pins[key] != name:
                findings.append(dict(code='NATIVE_PIN_IDENTITY_AMBIGUOUS', pin=key,
                                     observed_nets=[pins[key], name]))
                pins[key] = None
                continue
            pins[key] = name
            if node.get('pintype') != 'power_in':
                continue
            function = re.sub(r'[_{}]', '', node.get('pinfunction', '')).upper()
            role = ('return' if function in {'GND', 'VSS', 'VSSD', 'VSSA', 'VSSIO'}
                    else 'supply' if function in {'VDD', 'VDDD', 'VDDA', 'VDDIO'} else None)
            if role:
                power.setdefault((ref, name), {'supply': [], 'return': []})[role].append(key)
    for (ref, name), roles in sorted(power.items()):
        if roles['supply'] and roles['return']:
            findings.append(dict(code='SUPPLY_RETURN_COALESCENCE', reference=ref,
                                 observed_net=name, **roles))
    if contract['status'] == 'UNSUPPORTED':
        findings.append(dict(code='REQUEST_CONTRACT_UNSUPPORTED'))
    elif contract['status'] == 'PARSED':
        owners = {}
        for group in contract['groups']:
            observed = {pin: pins.get(pin) for pin in group['pins']}
            missing = [pin for pin, net in observed.items() if net is None]
            if missing:
                findings.append(dict(code='REQUEST_PIN_MISSING', expected_net=group['net'], pins=missing))
            names = {name for name in observed.values() if name is not None}
            if len(names) > 1:
                findings.append(dict(code='REQUEST_NET_SPLIT', expected_net=group['net'], observed=observed))
            for name in names:
                owners.setdefault(name, []).append(group['net'])
        for name, expected in sorted(owners.items()):
            if len(expected) > 1:
                findings.append(dict(code='REQUEST_NET_MERGE', observed_net=name, expected_nets=expected))
        contract['status'] = 'CHECKED'
    return dict(schema='aedl-schgen-dev-preflight/1',
                decision='REVIEW_REQUIRED' if findings else 'NO_SUPPORTED_VIOLATION_FOUND',
                electrical_acceptance=False, human_adjudication='PENDING_HUMAN_REVIEW',
                native_xml_sha256=sha(native_xml),
                request_text_sha256=hashlib.sha256(request.encode('utf-8')).hexdigest(),
                checked_scope=['explicit_request_pin_partition', 'native_supply_return_coalescence'],
                unchecked_scope=['part_identity', 'values', 'net_names', 'functional_equivalence',
                                 'datasheet_conformance', 'unlisted_connections'],
                contract=contract, findings=findings)


def expected_connectivity(before, planned):
    want = copy.deepcopy(before['pins_on_net'])
    for item in planned:
        want[item['reference']][item['pin']] = item['net']
    return want


def writer_document(candidate, planned):
    return dict(protocol_version=2, target_format='kicad', target_file=str(candidate),
                ops=[dict(op='add_net_label', name=d['net'], scope='local', rotation=0,
                          at=d['reference'] + '.' + d['pin']) for d in planned])


def _protected_forms(path):
    root = adapter.parse_sexpr(Path(path).read_text(encoding='utf-8'))[0]
    # Full forms, including embedded library definitions, pin UUIDs, fields,
    # wires, junctions and net flags. Only newly added local labels are allowed.
    forms = [form for form in root[1:] if not (
        isinstance(form, list) and form and form[0] in ('label', 'generator', 'generator_version'))]
    return Counter(json.dumps(form, sort_keys=True) for form in forms)


def protected_check(raw, candidate, before, after, planned):
    pre_graph, post_graph = adapter.object_graph(str(raw)), adapter.object_graph(str(candidate))
    pre_labels = Counter(json.dumps(x, sort_keys=True) for x in pre_graph['labels'])
    post_labels = Counter(json.dumps(x, sort_keys=True) for x in post_graph['labels'])
    added = post_labels - pre_labels
    expected_names = Counter(item['net'] for item in planned)
    actual_names = Counter()
    for key, count in added.items():
        label = json.loads(key)
        if label['kind'] != 'label':
            return False
        actual_names[label['text']] += count
    return (_protected_forms(raw) == _protected_forms(candidate)
            and not (pre_labels - post_labels)
            and expected_names == actual_names
            and expected_connectivity(before, planned) == after['pins_on_net'])


def export_erc(source, directory, kicad_cli):
    directory.mkdir()
    output = directory / 'erc.json'
    digest = sha(source)
    argv = [kicad_cli, 'sch', 'erc', '--format', 'json', '--output', str(output), str(source)]
    result = dict(status='FAIL', source_sha256=digest, argv=argv)
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=180)
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


def terminal_copy(raw, candidate, final, accept):
    source = candidate if accept else raw
    shutil.copyfile(source, final)
    digest = sha(final)
    return dict(path=str(final), sha256=digest, byte_verified=digest == sha(source))


def process_design(item, root, akcli, kicad_cli):
    directory = root / item['id']
    directory.mkdir()
    record = dict(id=item['id'], terminal=False, disposition='FAILED',
                  regression='UNKNOWN', before=None, after=None, candidate_event=None)
    try:
        for key in ('raw', 'request'):
            if sha(item[key]) != item[key + '_sha256']:
                raise ValueError('input hash drift: ' + key)
        raw, candidate, final = [directory/name for name in
                                 ('raw.kicad_sch', 'candidate.kicad_sch', 'after.kicad_sch')]
        shutil.copyfile(item['raw'], raw)
        shutil.copyfile(item['request'], directory/'request.txt')
        record['before_artifact'] = dict(path=str(raw), sha256=sha(raw))
        record['before'] = adapter.export_netlist(str(raw), str(directory/'before-net'), kicad_cli)
        record['before_erc'] = export_erc(raw, directory/'before-erc', kicad_cli)
        if record['before']['status'] != 'PASS' or record['before_erc']['status'] != 'PASS':
            raise ValueError('baseline fresh observation failed')
        request = (directory/'request.txt').read_text(encoding='utf-8')
        record['baseline_audit'] = audit_request_and_native(request, directory/'before-net'/'netlist.xml')
        write_json(directory/'baseline-audit.json', record['baseline_audit'])
        planned = ([] if record['baseline_audit']['decision'] == 'REVIEW_REQUIRED'
                   else plan(request, record['before']['connectivity']))
        record['abstention_reason'] = ('BASELINE_REQUIRES_REVIEW'
            if record['baseline_audit']['decision'] == 'REVIEW_REQUIRED'
            else 'NO_SUPPORTED_REQUEST_ONLY_REPAIR' if not planned else None)
        record['plan'] = planned
        write_json(directory/'plan.json', planned)
        shutil.copyfile(raw, candidate)
        accepted = False
        record['disposition'] = 'ABSTAINED'
        if planned:
            ops = writer_document(candidate, planned)
            expect = [dict(kind='pin_on_net', reference=d['reference'], pin=d['pin'], net=d['net'])
                      for d in planned]
            try:
                applied = adapter.apply_and_verify(dict(target=str(candidate), ops=ops,
                    expect=expect, record_dir=str(directory/'apply'), strict_nets=True,
                    extra_args=['--no-erc'], akcli=akcli, kicad_cli=kicad_cli))
                record['writer_verdict'] = applied['verdict']
            except (ValueError, OSError, KeyError) as exc:
                record['writer_verdict'] = 'FAILED_EXECUTION'
                record['writer_error'] = str(exc)
            # Observe even on writer refusal/timeout; the refused candidate stays
            # intact as evidence, and can never silently become the terminal.
            observed = adapter.export_netlist(str(candidate), str(directory/'candidate-net'), kicad_cli)
            record['candidate_observation'] = observed
            guard = (observed['status'] == 'PASS' and
                     protected_check(raw, candidate, record['before']['connectivity'],
                                     observed['connectivity'], planned))
            record['protected_delta_ok'] = guard
            candidate_erc = export_erc(candidate, directory/'candidate-erc', kicad_cli)
            record['candidate_erc'] = candidate_erc
            before_flags = {json.dumps(x) for x in record['before_erc']['flags']}
            new_flags = ({json.dumps(x) for x in candidate_erc.get('flags', [])} - before_flags)
            record['new_candidate_erc_flags'] = sorted(new_flags)
            accepted = (record['writer_verdict'] == 'APPLIED_VERIFIED' and guard and
                        candidate_erc['status'] == 'PASS' and not new_flags)
            record['disposition'] = 'MODIFIED' if accepted else 'VERIFIED_ROLLBACK'
            if not accepted:
                record['candidate_event'] = dict(writer=record['writer_verdict'],
                    protected_delta_ok=guard, new_erc_flags=sorted(new_flags),
                    electrical_defect_confirmed='UNKNOWN')
        record['after_artifact'] = terminal_copy(raw, candidate, final, accepted)
        record['after'] = adapter.export_netlist(str(final), str(directory/'after-net'), kicad_cli)
        record['after_erc'] = export_erc(final, directory/'after-erc', kicad_cli)
        record['valid_pair'] = (record['after_artifact']['byte_verified'] and
            record['after']['status'] == 'PASS' and record['after_erc']['status'] == 'PASS')
        if record['valid_pair'] and not accepted and sha(raw) == sha(final):
            record['regression'] = 'FALSE'
        if not record['valid_pair']:
            record['disposition'] = 'AFTER_ARTIFACT_INVALID'
    except (ValueError, OSError, KeyError, TypeError, ET.ParseError) as exc:
        record['error'] = str(exc)
        record['valid_pair'] = False
    record['terminal'] = True
    write_json(directory/'record.json', record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--akcli', required=True)
    parser.add_argument('--kicad-cli', required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding='utf-8-sig'))
    assignments = validate_manifest(manifest)
    if adapter.tool_version(args.kicad_cli)['version'].strip() != '8.0.9':
        raise ValueError('this DEV qualification requires KiCad 8.0.9')
    root = Path(args.out).resolve()
    root.mkdir()  # exclusive; no stale output reuse or resume overwrite
    write_json(root/'manifest.json', manifest)
    summary = dict(schema='aedl-schgen-exposed-dev/1', split='EXPOSED_DEV',
                   manifest_sha256=sha(args.manifest), N_assigned=len(assignments),
                   source_sha256=sha(__file__), adapter_sha256=sha(adapter.__file__),
                   formal_authorized=False, results=[])
    for item in assignments:
        record = process_design(item, root, args.akcli, args.kicad_cli)
        summary['results'].append(dict(id=item['id'], disposition=record['disposition'],
                                      valid_pair=record['valid_pair']))
        write_json(root/'summary.json', summary)
        print(item['id'], record['disposition'], 'valid_pair=', record['valid_pair'], flush=True)
    return 0 if all(r['valid_pair'] for r in summary['results']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
