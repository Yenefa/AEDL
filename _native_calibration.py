import copy, json, pathlib, subprocess, sys, tempfile
ROOT = pathlib.Path(r'C:\Users\Ryan Gosling\Desktop\workspace\project_020_AEDL\_wt_c5_erratum')
sys.path.insert(0, str(ROOT))
from gates import repair_verification as V
PY = r'C:\Users\Ryan Gosling\Desktop\workspace\project_020_AEDL\toolchain\py311\Scripts\python.exe'

def run_case(case):
    fx = ROOT / 'tests' / 'fixtures' / 'repair_pr1' / 'native' / case
    before_bytes = (fx / 'fault.kicad_sch').read_bytes()
    ops = json.loads((fx / 'repair_ops.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        target = td / 'fault.kicad_sch'
        target.write_bytes(before_bytes)
        opsp = td / 'ops.json'
        opsp.write_text(json.dumps(ops), encoding='utf-8')
        cmd = [PY, '-m', 'akcli', 'draw', str(target), '--ops', str(opsp),
               '--apply', '--strict-nets', '--no-erc', '--json']
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(td))
        after_bytes = target.read_bytes()
    print('  akcli exit=%s  bytes %d -> %d  changed=%s' % (
        r.returncode, len(before_bytes), len(after_bytes), before_bytes != after_bytes))
    if r.returncode != 0:
        print('  stdout:', r.stdout[-300:]); print('  stderr:', r.stderr[-300:]); return
    before = V.normalize_observation(V.observe_source(before_bytes))
    after = V.normalize_observation(V.observe_source(after_bytes))
    old_ids = {o['identity'] for o in before['source_objects']}
    comp_by_uuid = {c['identity']['component_uuid']: c for c in after['components']}
    new_objs = [o for o in after['source_objects'] if o['identity'] not in old_ids]
    print('  new source objects: %s' % [(o['kind'], o['identity'][:8]) for o in new_objs])
    mapping, slot = {}, 0
    for obj in new_objs:
        if obj['kind'] == 'symbol':
            mapping[obj['identity']] = 'new:' + comp_by_uuid[obj['identity']]['reference']
        elif obj['kind'] == 'label':
            mapping[obj['identity']] = 'new:label:%d' % slot; slot += 1
    for obj in new_objs:
        node = obj['descriptor']['ast']
        if obj['kind'] == 'symbol':
            flags = [c for c in node[1:] if isinstance(c, list) and c[0] == 'exclude_from_sim']
            comp = comp_by_uuid[obj['identity']]
            print('  SYMBOL %s' % comp['reference'])
            print('    exclude_from_sim      : %s' % (flags or 'ABSENT'))
            print('    top-level tag         : %s' % node[0])
            print('    child tags            : %s' % [c[0] for c in node[1:] if isinstance(c, list)])
            print('    symbol uuid == comp   : %s' % (obj['identity'] == comp['identity']['component_uuid']))
        else:
            print('  LABEL -> %s' % json.dumps(V._label_semantics(node), ensure_ascii=False))
    reid = V._reidentify(after, mapping)
    canon = V._canonicalize_new_objects(reid)
    got = [o for o in canon['source_objects'] if o['identity'].startswith('new:')]
    print('  CANONICALIZED: %s' % json.dumps(got, ensure_ascii=False, sort_keys=True))

for case in ('DC-04', 'DC-05'):
    print('=== %s ===' % case)
    run_case(case)