"""Explicit DEV format ingestion, never electrical repair or uplift.

Only remove an EMPTY legacy symbol_instances root block. Preserve
all other root forms and text. Keep original bytes, hashes, classification,
fresh native observations, and a new manifest separately from previous runs.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess

from tools import akcli_adapter as adapter
from tools.schgen_dev_chain import export_erc, sha, validate_manifest, write_json


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
    roots = adapter.parse_sexpr(text)
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
    after = adapter.parse_sexpr(result)[0][1:]
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
    manifest = json.loads(Path(input_path).read_text(encoding='utf-8-sig'))
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
    version = adapter.tool_version(args.kicad_cli)['version'].strip()
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
            if sha(item['raw']) != item['raw_sha256']:
                raise ValueError('input binding drift')
            if not reference_mode and sha(item['request']) != item['request_sha256']:
                raise ValueError('request binding drift')
            original = directory/'original.kicad_sch'
            prepared = directory/'input.kicad_sch'
            shutil.copyfile(item['raw'], original)
            if not reference_mode:
                shutil.copyfile(item['request'], directory/'request.txt')
            record['original_import_issues'] = adapter.native_import_issues(str(original), version)
            text = original.read_bytes().decode('utf-8')
            prepared.write_bytes(normalize_legacy_order(text).encode('utf-8'))
            record['prepared_sha256'] = sha(prepared)
            record['classification'] = ('FORMAT_ADAPTER_TRANSLATION' if sha(original) != sha(prepared)
                                        else 'UNCHANGED_FORMAT')
            pre_graph, post_graph = adapter.object_graph(str(original)), adapter.object_graph(str(prepared))
            if pre_graph['graph_sha256'] != post_graph['graph_sha256']:
                raise ValueError('object graph changed during format ingestion')
            record['object_graph_unchanged'] = True
            record['native_export'] = adapter.export_netlist(str(prepared), str(directory/'native'), args.kicad_cli)
            record['erc'] = export_erc(prepared, directory/'erc', args.kicad_cli)
            if record['native_export']['status'] != 'PASS' or record['erc']['status'] != 'PASS':
                raise ValueError('prepared native observation failed')
            record['status'] = 'READY_FOR_DEV'
            if reference_mode:
                net = directory/'reference.net'
                argv_export = [args.kicad_cli, 'sch', 'export', 'netlist', '--format',
                               'kicadsexpr', '--output', str(net), str(prepared)]
                process = subprocess.run(argv_export, capture_output=True, timeout=180)
                (directory/'score-export-stdout.txt').write_bytes(process.stdout)
                (directory/'score-export-stderr.txt').write_bytes(process.stderr)
                if process.returncode != 0 or sha(prepared) != record['prepared_sha256'] or not net.is_file():
                    raise ValueError('reference scoring export failed')
                references[item['id']] = dict(path=str(net), sha256=sha(net),
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
    report = dict(schema='aedl-schgen-dev-ingestion/1', N_assigned=len(assignments),
                  N_ready=len(ready), original_manifest_sha256=sha(input_path),
                  role='REFERENCE' if reference_mode else 'REPAIR_INPUT',
                  source_sha256=sha(__file__), adapter_sha256=sha(adapter.__file__),
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
