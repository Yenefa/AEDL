"""Boundaries for the self-contained DEV format-ingestion tool.

The re-cut keeps only the adapter-independent half of the exposed-DEV chain, so
these tests must run with no repair adapter and no repair chain importable at
all.  That absence is asserted explicitly, not assumed.
"""
import ast
import json
from pathlib import Path
import tempfile
import unittest

from tools import schgen_native_ingest as ingest


class StandaloneImportTests(unittest.TestCase):
    def test_ingestion_module_imports_no_aedl_module_at_all(self):
        # Discovery imports every test module, so sys.modules is not a valid
        # witness here; the module's own import statements are.
        tree = ast.parse(Path(ingest.__file__).read_text(encoding='utf-8'))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        self.assertEqual([name for name in sorted(imported) if name.startswith('tools')],
                         [], sorted(imported))


class NativeImportIssueTests(unittest.TestCase):
    def test_legacy_instance_tail_is_an_import_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'raw.kicad_sch'
            source.write_text('(kicad_sch (symbol_instances) (label "VOUT" (at 1 2 0)))')
            issues = ingest.native_import_issues(str(source), '8.0.9')
            self.assertEqual(issues[0]['code'], 'LEGACY_INSTANCE_TAIL')
            self.assertEqual(issues[0]['ignored_root_forms'], ['label'])

    def test_a_legacy_block_without_a_tail_is_not_an_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'raw.kicad_sch'
            source.write_text('(kicad_sch (label "VOUT" (at 1 2 0)) (symbol_instances))')
            self.assertEqual(ingest.native_import_issues(str(source), '8.0.9'), [])

    def test_non_eight_reader_reports_no_legacy_issue(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'raw.kicad_sch'
            source.write_text('(kicad_sch (symbol_instances) (label "VOUT" (at 1 2 0)))')
            self.assertEqual(ingest.native_import_issues(str(source), '10.0.5'), [])

    def test_successful_but_empty_native_export_is_not_an_observation(self):
        with self.assertRaises(ingest.IngestionInputError):
            ingest.parse_netlist(b'<export><components/><nets/></export>')


class ObjectGraphTests(unittest.TestCase):
    def test_nested_library_symbols_are_not_placements(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'raw.kicad_sch'
            source.write_text(
                '(kicad_sch (lib_symbols (symbol "Dev:R" (property "Reference" "R")))'
                ' (symbol (lib_id "Dev:R") (at 1 2 0) (uuid "u1")'
                ' (property "Reference" "R1") (property "Value" "10k"))'
                ' (wire (pts (xy 0 0) (xy 1 0))) (label "A" (at 0 0 0)))')
            graph = ingest.object_graph(str(source))
            self.assertEqual(graph['counts']['symbols'], 1)
            self.assertEqual(graph['counts']['wires'], 1)
            self.assertEqual(graph['counts']['labels'], 1)
            self.assertEqual(graph['symbols'][0]['reference'], 'R1')

    def test_removing_the_empty_block_leaves_the_object_graph_identical(self):
        raw = ('(kicad_sch (symbol_instances)'
               ' (wire (pts (xy 0 0) (xy 1 0))) (label "A" (at 0 0 0))'
               ' (junction (at 0 0)))')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = root/'before.kicad_sch'
            after = root/'after.kicad_sch'
            before.write_text(raw)
            after.write_text(ingest.normalize_legacy_order(raw))
            self.assertNotEqual(ingest.sha(before), ingest.sha(after))
            self.assertEqual(ingest.object_graph(str(before))['graph_sha256'],
                             ingest.object_graph(str(after))['graph_sha256'])


class LegacyOrderTests(unittest.TestCase):
    def test_ingestion_removes_only_empty_root_legacy_block_and_is_idempotent(self):
        raw = '(kicad_sch\n(symbol_instances)\n(label "(symbol_instances)" (at 1 2 0)))'
        changed = ingest.normalize_legacy_order(raw)
        self.assertEqual(changed.count('(symbol_instances)'), 1)
        forms = ingest.parse_sexpr(changed)[0]
        self.assertEqual(forms[-1][0], 'label')
        self.assertEqual(forms[-1][1], '"(symbol_instances)"')
        self.assertEqual(ingest.normalize_legacy_order(changed), changed)

    def test_ingestion_does_not_rewrite_nonempty_instance_metadata(self):
        with self.assertRaises(ValueError):
            ingest.normalize_legacy_order('(kicad_sch (symbol_instances (path "x")) (label "Y"))')

    def test_document_without_the_block_is_returned_byte_identical(self):
        raw = '(kicad_sch (label "Y" (at 0 0 0)))'
        self.assertEqual(ingest.normalize_legacy_order(raw), raw)


class ManifestTests(unittest.TestCase):
    def test_reference_ingestion_cannot_accept_a_repair_input_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'manifest.json'
            source.write_text(json.dumps(dict(split='EXPOSED_DEV', assignments=[])))
            with self.assertRaises(ValueError):
                ingest.main(['--reference-sources', str(source), '--out', str(root/'out'),
                             '--kicad-cli', 'MUST_NOT_RUN'])
            self.assertFalse((root/'out').exists())

    def test_foreign_split_and_reference_bearing_input_rejected(self):
        for split in ('HELD_OUT', 'DEV', 'FORMAL'):
            with self.assertRaises(ValueError):
                ingest.validate_manifest({'split': split, 'assignments': []})
        with self.assertRaises(ValueError):
            ingest.validate_manifest({'split': 'EXPOSED_DEV', 'assignments': [
                {'id': 'x', 'reference_netlist': 'answer.net'}]})

    def test_duplicate_designs_rejected(self):
        item = dict(id='same', raw='a', raw_sha256='0'*64,
                    request='b', request_sha256='1'*64)
        with self.assertRaises(ValueError):
            ingest.validate_manifest(dict(split='EXPOSED_DEV', assignments=[item, item]))

    def test_ingestion_cannot_start_without_the_qualified_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root/'manifest.json'
            manifest.write_text(json.dumps(dict(split='EXPOSED_DEV', assignments=[
                dict(id='one', raw='raw', raw_sha256='0'*64,
                     request='request', request_sha256='1'*64)])))
            with self.assertRaises(ValueError):
                ingest.main(['--manifest', str(manifest), '--out', str(root/'out'),
                             '--kicad-cli', 'MUST_NOT_RUN'])
            self.assertFalse((root/'out').exists())


if __name__ == '__main__':
    unittest.main()
