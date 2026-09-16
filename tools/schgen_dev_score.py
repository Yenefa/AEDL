"""Separate descriptive evaluator for completed exposed DEV native replays."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

from tools.schgen_dev_chain import sha, validate_manifest, write_json
from tools import akcli_adapter as adapter


PINNED_SCORER = 'b9f06ba9c10344d32b7ab4801ec1d8cac7523ac39ba7de588ddcfcb71516bfd8'


def score_text(scorer, reference, candidate):
    if not scorer.build_net_sets_libpart_pin(reference) or not scorer.build_net_sets_libpart_pin(candidate):
        return dict(j=None, f1=None, status='INVALID_EMPTY_SIGNATURE')
    metrics = scorer.compare_netlists_sets(reference, candidate)
    return dict(j=metrics['jaccard'], f1=metrics['f1_A->B'], status='SCORED')


def summarize(rows):
    pairs = [r for r in rows if r['before_j'] is not None and r['after_j'] is not None]
    return dict(N_assigned=len(rows), B=sum(r['before_j'] is not None for r in rows),
                P=len(pairs), mean_delta_j=(sum(r['delta_j'] for r in pairs)/len(pairs)
                                           if pairs else None),
                improved=sum(r['delta_j'] > 0 for r in pairs),
                unchanged=sum(r['delta_j'] == 0 for r in pairs),
                worsened=sum(r['delta_j'] < 0 for r in pairs),
                regression_unknown=sum(r.get('regression', 'UNKNOWN') == 'UNKNOWN' for r in rows),
                formal_confirmatory=False)


def export_score_net(source, directory, cli):
    directory.mkdir()
    output = directory/'netlist.net'
    digest = sha(source)
    argv = [cli, 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '--output',
            str(output), str(source)]
    proc = subprocess.run(argv, capture_output=True, timeout=180)
    (directory/'stdout.txt').write_bytes(proc.stdout)
    (directory/'stderr.txt').write_bytes(proc.stderr)
    binding = dict(argv=argv, returncode=proc.returncode, source_sha256=digest)
    write_json(directory/'export.json', binding)
    if proc.returncode != 0 or sha(source) != digest or not output.is_file():
        raise ValueError('fresh scoring export failed')
    binding.update(netlist_sha256=sha(output), path=str(output))
    write_json(directory/'export.json', binding)
    return output.read_text(encoding='utf-8'), binding


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--references', required=True)
    parser.add_argument('--scorer', required=True)
    parser.add_argument('--kicad-cli', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    run, out = Path(args.run), Path(args.out).resolve()
    out.mkdir()
    assignments = validate_manifest(json.loads((run/'manifest.json').read_text(encoding='utf-8')))
    rows = [dict(id=d['id'], before_j=None, after_j=None, delta_j=None,
                 before_f1=None, after_f1=None, delta_f1=None, status='REPAIR_INCOMPLETE')
            for d in assignments]
    records = {}
    for item in assignments:
        path = run/item['id']/'record.json'
        if path.is_file():
            record = json.loads(path.read_text(encoding='utf-8'))
            if record.get('terminal') is True and record.get('id') == item['id']:
                records[item['id']] = (record, sha(path))
    # All assigned IDs, including failures, must be terminal before the first
    # reference read or scorer import. Missing IDs never disappear from N.
    if len(records) != len(assignments):
        write_json(out/'scores.json', dict(summary=summarize(rows), rows=rows))
        return 1
    if sha(args.scorer) != PINNED_SCORER:
        raise ValueError('upstream scorer hash drift')
    spec = importlib.util.spec_from_file_location('schgen_pinned_external_scorer', args.scorer)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    refs = json.loads(Path(args.references).read_text(encoding='utf-8-sig'))
    if set(refs) != {d['id'] for d in assignments}:
        raise ValueError('reference bindings must cover exactly the assigned IDs')
    for item, row in zip(assignments, rows):
        record, record_hash = records[item['id']]
        row.update(record_sha256=record_hash, disposition=record['disposition'],
                   regression=record.get('regression', 'UNKNOWN'))
        directory = out/item['id']
        directory.mkdir()
        try:
            ref = refs[item['id']]
            if sha(ref['path']) != ref['sha256']:
                raise ValueError('reference hash drift')
            if not ref.get('native_source') or not ref.get('native_source_sha256'):
                raise ValueError('reference requires a bound, import-validated native artifact')
            if sha(ref['native_source']) != ref['native_source_sha256']:
                raise ValueError('reference native source hash drift')
            imported = adapter.export_netlist(ref['native_source'], str(directory/'reference-native'),
                                             args.kicad_cli)
            if imported['status'] != 'PASS':
                raise ValueError('reference native import failed: ' + imported['reason'])
            reference, reference_binding = export_score_net(ref['native_source'], directory/'reference',
                                                            args.kicad_cli)
            row['reference_export'] = reference_binding
            if (not record.get('before') or record['before']['status'] != 'PASS' or
                    record.get('before_erc', {}).get('status') != 'PASS'):
                raise ValueError('baseline is not independently evaluable')
            before = record['before_artifact']
            if sha(before['path']) != before['sha256'] or before['sha256'] != item['raw_sha256']:
                raise ValueError('before binding mismatch')
            text, binding = export_score_net(before['path'], directory/'before', args.kicad_cli)
            baseline = score_text(scorer, reference, text)
            row.update(before_j=baseline['j'], before_f1=baseline['f1'], before_export=binding)
            if baseline['j'] is None:
                raise ValueError('baseline/reference has an empty scorer-visible signature set')
            if not record.get('valid_pair'):
                raise ValueError('terminal artifact has no valid independent after observation')
            after = record['after_artifact']
            if sha(after['path']) != after['sha256']:
                raise ValueError('after binding mismatch')
            text, binding = export_score_net(after['path'], directory/'after', args.kicad_cli)
            final = score_text(scorer, reference, text)
            row.update(after_j=final['j'], after_f1=final['f1'], after_export=binding,
                       status=final['status'])
            if row['before_j'] is not None and row['after_j'] is not None:
                row.update(delta_j=row['after_j']-row['before_j'],
                           delta_f1=row['after_f1']-row['before_f1'])
            if sha(run/item['id']/'record.json') != record_hash:
                raise ValueError('repair record changed during evaluation')
        except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
            row.update(status='NOT_EVALUABLE', error=str(exc), after_j=None, after_f1=None,
                       delta_j=None, delta_f1=None)
        write_json(directory/'score.json', row)
        print(row['id'], row['status'], row['before_j'], row['after_j'], flush=True)
    report = dict(scorer_sha256=PINNED_SCORER, evaluator_sha256=sha(__file__),
                  references_manifest_sha256=sha(args.references),
                  summary=summarize(rows), rows=rows)
    write_json(out/'scores.json', report)
    print(json.dumps(report['summary'], indent=2))
    return 0 if all(r['status'] == 'SCORED' for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
