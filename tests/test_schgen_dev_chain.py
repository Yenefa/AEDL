"""Boundaries for the exposed-DEV runner; external tools tested separately."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from tools import akcli_adapter as adapter


class WriterIdentityTests(unittest.TestCase):
    def test_legacy_instance_tail_is_an_import_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'raw.kicad_sch'
            source.write_text('(kicad_sch (symbol_instances) (label "VOUT" (at 1 2 0)))')
            issues = adapter.native_import_issues(str(source), '8.0.9')
            self.assertEqual(issues[0]['code'], 'LEGACY_INSTANCE_TAIL')
            self.assertEqual(issues[0]['ignored_root_forms'], ['label'])

    def test_successful_but_empty_native_export_is_not_an_observation(self):
        with self.assertRaises(adapter.AdapterInputError):
            adapter.parse_netlist(b'<export><components/><nets/></export>')

    def test_disappearing_pins_cannot_prove_a_short(self):
        pre = {"pins_on_net": {"R1": {"1": "a", "2": "b"}}}
        post = {"pins_on_net": {}}
        check = adapter.check_expectation(
            {"kind": "pins_shorted", "a": ["R1", "1"], "b": ["R1", "2"]},
            {}, {}, pre, post)
        self.assertFalse(check["ok"])

    def test_disappearing_pin_cannot_prove_a_split(self):
        pre = {"pins_on_net": {"R1": {"1": "a", "2": "a"}}}
        post = {"pins_on_net": {"R1": {"1": "a"}}}
        check = adapter.check_expectation(
            {"kind": "pins_split", "a": ["R1", "1"], "b": ["R1", "2"]},
            {}, {}, pre, post)
        self.assertFalse(check["ok"])


@unittest.skipUnless(os.environ.get('AEDL_DEV_AKCLI') and os.environ.get('AEDL_DEV_KICAD'),
                     'real tools not configured for fixture controls')
class RealNativeControls(unittest.TestCase):
    def apply(self, name, operation, expectation, strict):
        root = Path(os.environ['AEDL_DEV_CONTROL_OUT'])/name
        root.mkdir(parents=True)
        source = Path(__file__).parent/'fixtures/repair_pr1/native/DC-04/fault.kicad_sch'
        candidate = root/'candidate.kicad_sch'
        shutil.copyfile(source, candidate)
        return adapter.apply_and_verify(dict(target=str(candidate),
            ops=dict(protocol_version=2, target_format='kicad', target_file=str(candidate),
                     ops=[operation]), expect=[expectation], record_dir=str(root/'apply'),
            strict_nets=strict, extra_args=['--no-erc'],
            akcli=os.environ['AEDL_DEV_AKCLI'], kicad_cli=os.environ['AEDL_DEV_KICAD']))

    def test_pin_anchor_wire_changes_real_native_connectivity(self):
        # Intentional short of a synthetic resistor fixture tests writer
        # observability; this is not a safe electrical repair or SchGen sample.
        result = self.apply('pin-wire', dict(op='add_wire', vertices=['R1.1', 'R1.2']),
                            dict(kind='pins_shorted', a='R1.1', b='R1.2'), False)
        self.assertEqual(result['verdict'], 'APPLIED_VERIFIED', result['reasons'])

    def test_coordinate_wire_false_success_is_blocked(self):
        result = self.apply('coordinate-wire',
            dict(op='add_wire', vertices=[[151.13,106.68],[151.13,114.3]]),
            dict(kind='wire_appears', endpoints=[[151.13,106.68],[151.13,114.3]]), False)
        self.assertEqual(result['verdict'], 'FAILED_UNOBSERVED_CHANGE', result['reasons'])

    def test_label_pin_anchor_is_observable_in_native_export(self):
        result = self.apply('pin-label',
            dict(op='add_net_label', at='R1.2', name='DEV_CONTROL', scope='local', rotation=0),
            dict(kind='pin_on_net', reference='R1', pin='2', net='/DEV_CONTROL'), True)
        self.assertEqual(result['verdict'], 'APPLIED_VERIFIED', result['reasons'])


class DevBoundaryTests(unittest.TestCase):
    def native_audit(self, request, nets):
        from tools.schgen_dev_chain import audit_request_and_native
        import xml.etree.ElementTree as ET
        root = ET.Element('export')
        section = ET.SubElement(root, 'nets')
        for name, pins in nets.items():
            net = ET.SubElement(section, 'net', name=name)
            for ref, pin, function, kind in pins:
                ET.SubElement(net, 'node', ref=ref, pin=pin,
                              pinfunction=function, pintype=kind)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'native.xml'
            path.write_bytes(ET.tostring(root))
            return audit_request_and_native(request, path)

    def test_request_partition_detects_merge_without_a_reference(self):
        request = ('## Exact connectivity I want (by net)\n'
                   '### Net **VDD**\n- **J1 pin 1** ↔ **U1 pin 1**\n'
                   '### Net **GND**\n- **J1 pin 2** ↔ **U1 pin 2**\n')
        audit = self.native_audit(request, {'one': [
            ('J1','1','','passive'), ('U1','1','','passive'),
            ('J1','2','','passive'), ('U1','2','','passive')]})
        self.assertEqual(audit['decision'], 'REVIEW_REQUIRED')
        self.assertIn('REQUEST_NET_MERGE', [f['code'] for f in audit['findings']])

    def test_unknown_pin_cannot_satisfy_request_partition(self):
        request = ('## Exact connectivity\n### Net A\n- R1 pin 1 ↔ J1 pin 1\n'
                   '### Net B\n- R1 pin 2 ↔ J1 pin 2\n')
        audit = self.native_audit(request, {'a': [('R1','1','','passive')],
                                           'b': [('R1','2','','passive')]})
        self.assertIn('REQUEST_PIN_MISSING', [f['code'] for f in audit['findings']])

    def test_conditional_or_conflicting_contract_never_becomes_partial_permission(self):
        requests = [
            '## Exact connectivity\n### Net A\n- R1 pin 1 ↔ J1 pin 1 if enabled\n',
            '## Exact connectivity\n### Net A\n- R1 pin 1 ↔ J1 pin 1\n'
            '### Net B\n- R1 pin 1 ↔ J1 pin 2\n']
        for request in requests:
            audit = self.native_audit(request, {'a': [('R1','1','','passive')]})
            self.assertEqual(audit['contract']['status'], 'UNSUPPORTED')
            self.assertEqual(audit['decision'], 'REVIEW_REQUIRED')

    def test_contract_stops_at_next_section_and_checks_partitions_not_net_aliases(self):
        request = ('## Exact connectivity\n### Net A\n- R1 pin 1 ↔ J1 pin 1\n'
                   '### Net B\n- R1 pin 2 ↔ J1 pin 2\n'
                   '## Notes\nDo not connect R1 pin 1 to B.\n')
        audit = self.native_audit(request, {'/A': [('R1','1','','passive'),('J1','1','','passive')],
                                           '/B': [('R1','2','','passive'),('J1','2','','passive')]})
        self.assertEqual(audit['contract']['status'], 'CHECKED')
        self.assertEqual(audit['findings'], [])
        self.assertEqual(audit['decision'], 'NO_SUPPORTED_VIOLATION_FOUND')

    def test_supply_return_short_is_detected_even_when_erc_does_not_call_it_a_short(self):
        audit = self.native_audit('A 3.3V MCU circuit', {'+3.3V': [
            ('U1','1','V_{DDD}','power_in'), ('U1','2','V_{SSD}','power_in'),
            ('C1','1','','passive'), ('C1','2','','passive')]})
        self.assertEqual({f['code'] for f in audit['findings']},
                         {'SUPPLY_RETURN_COALESCENCE'})
        self.assertEqual(audit['decision'], 'REVIEW_REQUIRED')

    def test_separate_power_rails_and_unused_pins_do_not_prove_a_defect(self):
        audit = self.native_audit('An MCU circuit', {
            'VDD': [('U1','1','VDD','power_in')],
            'GND': [('U1','2','VSS','power_in')],
            'unconnected-(U1-IO-Pad3)': [('U1','3','IO','bidirectional')]})
        self.assertEqual(audit['findings'], [])
        self.assertFalse(audit['electrical_acceptance'])

    def test_ambiguous_native_pin_routes_to_review_without_losing_terminal_output(self):
        audit = self.native_audit('An LDO circuit', {
            'unconnected-1': [('U1','4','NC','no_connect')],
            'unconnected-2': [('U1','4','NC','no_connect')]})
        self.assertIn('NATIVE_PIN_IDENTITY_AMBIGUOUS', [f['code'] for f in audit['findings']])
        self.assertEqual(audit['decision'], 'REVIEW_REQUIRED')

    def test_baseline_review_blocks_planner_and_writer_but_retains_after(self):
        from unittest.mock import patch
        from tools import schgen_dev_chain as chain
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, request = root/'raw', root/'request'
            raw.write_bytes(b'baseline')
            request.write_text('Connect J1 pin 1 to VOUT.', encoding='utf-8')
            item = dict(id='one', raw=str(raw), raw_sha256=chain.sha(raw),
                        request=str(request), request_sha256=chain.sha(request))
            def export(source, directory, cli):
                directory = Path(directory)
                directory.mkdir()
                (directory/'netlist.xml').write_text('<export><nets><net name="rail">'
                    '<node ref="U1" pin="1" pinfunction="VDD" pintype="power_in"/>'
                    '<node ref="U1" pin="2" pinfunction="VSS" pintype="power_in"/>'
                    '</net></nets></export>')
                return dict(status='PASS', connectivity={})
            with patch.object(adapter, 'export_netlist', side_effect=export), \
                 patch.object(chain, 'export_erc', return_value=dict(status='PASS', flags=[])), \
                 patch.object(chain, 'plan', side_effect=AssertionError('planner must not run')), \
                 patch.object(adapter, 'apply_and_verify', side_effect=AssertionError('writer must not run')):
                record = chain.process_design(item, root, 'unused', 'unused')
            self.assertTrue(record['terminal'])
            self.assertTrue(record['valid_pair'])
            self.assertEqual(record['abstention_reason'], 'BASELINE_REQUIRES_REVIEW')
            self.assertEqual((root/'one/after.kicad_sch').read_bytes(), raw.read_bytes())

    def test_ingestion_removes_only_empty_root_legacy_block_and_is_idempotent(self):
        from tools.schgen_native_ingest import normalize_legacy_order
        raw = '(kicad_sch\n(symbol_instances)\n(label "(symbol_instances)" (at 1 2 0)))'
        changed = normalize_legacy_order(raw)
        self.assertEqual(changed.count('(symbol_instances)'), 1)
        forms = adapter.parse_sexpr(changed)[0]
        self.assertEqual(forms[-1][0], 'label')
        self.assertEqual(forms[-1][1], '"(symbol_instances)"')
        self.assertEqual(normalize_legacy_order(changed), changed)

    def test_ingestion_does_not_rewrite_nonempty_instance_metadata(self):
        from tools.schgen_native_ingest import normalize_legacy_order
        with self.assertRaises(ValueError):
            normalize_legacy_order('(kicad_sch (symbol_instances (path "x")) (label "Y"))')

    def test_reference_ingestion_cannot_accept_a_repair_input_manifest(self):
        from tools.schgen_native_ingest import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'manifest.json'
            source.write_text(json.dumps(dict(split='EXPOSED_DEV', assignments=[])))
            with self.assertRaises(ValueError):
                main(['--reference-sources', str(source), '--out', str(root/'out'),
                      '--kicad-cli', 'MUST_NOT_RUN'])
            self.assertFalse((root/'out').exists())

    def test_writer_document_binds_protocol_format_and_candidate(self):
        from tools.schgen_dev_chain import writer_document
        doc = writer_document('candidate.kicad_sch',
                              [dict(reference='J1', pin='2', net='VOUT')])
        self.assertEqual(doc['protocol_version'], 2)
        self.assertEqual(doc['target_format'], 'kicad')
        self.assertEqual(doc['target_file'], 'candidate.kicad_sch')
        self.assertEqual(doc['ops'][0]['at'], 'J1.2')

    def test_request_parser_rejects_negation_condition_and_multiple_pins(self):
        from tools.schgen_dev_chain import declarations
        text = '\n'.join([
            '- Connect **J1 pin 2 (C)** to **VOUT**.',
            'Do not connect J1 pin 3 to VOUT.',
            'If enabled, connect J1 pin 4 to VOUT.',
            'J1 pin 5 connects to R1 pin 2 on VOUT.',
            'J1 pin 6 connects to VDD or VBUS.',
        ])
        self.assertEqual([(d['reference'], d['pin'], d['net']) for d in declarations(text)],
                         [('J1', '2', 'VOUT')])

    def test_conflicting_named_rails_abstain_instead_of_first_wins(self):
        from tools.schgen_dev_chain import declarations
        self.assertEqual(declarations('J1 pin 1 -> VIN\nJ1 pin 1 -> VBUS'), [])

    def test_foreign_split_and_reference_bearing_input_rejected(self):
        from tools.schgen_dev_chain import validate_manifest
        for split in ('HELD_OUT', 'DEV', 'FORMAL'):
            with self.assertRaises(ValueError):
                validate_manifest({'split': split, 'assignments': []})
        with self.assertRaises(ValueError):
            validate_manifest({'split': 'EXPOSED_DEV', 'assignments': [
                {'id': 'x', 'reference_netlist': 'answer.net'}]})

    def test_duplicate_designs_rejected(self):
        from tools.schgen_dev_chain import validate_manifest
        item = dict(id='same', raw='a', raw_sha256='0'*64,
                    request='b', request_sha256='1'*64)
        with self.assertRaises(ValueError):
            validate_manifest(dict(split='EXPOSED_DEV', assignments=[item, item]))

    def test_protected_net_change_is_not_authorized_by_a_label_repair(self):
        from tools.schgen_dev_chain import expected_connectivity
        before = {'pins_on_net': {'J1': {'1': 'unconnected-(J1-P1-Pad1)'},
                                  'R1': {'1': 'VIN', '2': 'GND'}}}
        want = expected_connectivity(before, [{'reference': 'J1', 'pin': '1', 'net': 'VOUT'}])
        self.assertEqual(want['R1'], before['pins_on_net']['R1'])
        self.assertEqual(want['J1']['1'], 'VOUT')

    def test_rollback_is_a_distinct_byte_verified_after_file(self):
        from tools.schgen_dev_chain import terminal_copy
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, candidate, final = root/'raw', root/'candidate', root/'after'
            raw.write_bytes(b'baseline')
            candidate.write_bytes(b'unsafe mutation')
            result = terminal_copy(raw, candidate, final, accept=False)
            self.assertEqual(final.read_bytes(), raw.read_bytes())
            self.assertEqual(candidate.read_bytes(), b'unsafe mutation')
            self.assertTrue(result['byte_verified'])

    def test_missing_assigned_results_stay_in_denominator(self):
        from tools.schgen_dev_score import main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assignments = [dict(id=id, raw='unused', request='unused',
                                raw_sha256='0'*64, request_sha256='1'*64) for id in ('one','two')]
            (root/'manifest.json').write_text(json.dumps(dict(split='EXPOSED_DEV', assignments=assignments)))
            (root/'one').mkdir()
            (root/'one/record.json').write_text(json.dumps(dict(id='one', terminal=True)))
            # Missing references/scorer/tools prove no evaluator dependency is
            # opened before ALL assigned repair terminals exist.
            rc = main(['--run', str(root), '--references', 'MUST_NOT_READ',
                       '--scorer', 'MUST_NOT_IMPORT', '--kicad-cli', 'MUST_NOT_RUN',
                       '--out', str(root/'report')])
            report = json.loads((root/'report/scores.json').read_text())
            self.assertEqual(rc, 1)
            self.assertEqual(report['summary']['N_assigned'], 2)
            self.assertEqual([r['id'] for r in report['rows']], ['one', 'two'])
            self.assertTrue(all(r['after_j'] is None for r in report['rows']))

    def test_empty_signature_set_never_returns_numeric_score(self):
        from tools.schgen_dev_score import score_text
        class EmptyScorer:
            def build_net_sets_libpart_pin(self, text):
                return set() if text == 'empty' else {frozenset(['x'])}
            def compare_netlists_sets(self, left, right):
                raise AssertionError('must reject vacuity before scoring')
        self.assertIsNone(score_text(EmptyScorer(), 'valid', 'empty')['j'])


if __name__ == '__main__':
    unittest.main()
