"""Synthetic, isolated error-path checks; these are not production observations."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from notes.y4.produce_current_observations import (
    ObservationError, generate_current, project_current_xml,
)
from tools.repair_pipeline import canonical_json_bytes, hash_bytes

XML = b'''<export><design><source>host-only-path</source></design>
<components><comp ref="X1"><value>synthetic</value><libsource lib="Example" part="Part"/></comp></components>
<nets><net code="1" name="N"><node ref="X1" pin="1" pintype="passive"/></net></nets></export>'''


class ProducerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'fault.kicad_sch'
        self.source.write_bytes(b'(kicad_sch\r\n)\r\n')
        self.output = self.root / 'new'

    def export(self, command, **kwargs):
        Path(command[command.index('--output') + 1]).write_bytes(XML)
        return subprocess.CompletedProcess(command, 0)

    def generate(self):
        return generate_current(self.source, self.output, ['synthetic-test-only'],
                                expected_source_sha256=hash_bytes(b'(kicad_sch\r\n)\r\n'))

    def test_roundtrip_preserves_bytes_and_uses_generation_observation(self):
        with patch('notes.y4.produce_current_observations.subprocess.run', self.export):
            record = self.generate()
        source = self.source.read_bytes()
        self.assertEqual((self.output / 'schematic.kicad_sch').read_bytes(), source)
        observation_raw = (self.output / 'current_observation.json').read_bytes()
        binding = json.loads((self.output / 'observation_binding.json').read_bytes())
        self.assertEqual(binding['source_sha256'], hash_bytes(source))
        self.assertEqual(binding['observation_sha256'], hash_bytes(observation_raw))
        self.assertEqual(observation_raw, canonical_json_bytes(json.loads(observation_raw)))
        self.assertNotIn(b'host-only-path', observation_raw)
        self.assertEqual(record['independent_C3_qualification'], 'NOT_RUN')

    def test_failed_export_has_no_binding(self):
        with patch('notes.y4.produce_current_observations.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaises(ObservationError):
                self.generate()
        self.assertFalse((self.output / 'observation_binding.json').exists())

    def test_drift_invalidates_generation(self):
        def drift(command, **kwargs):
            result = self.export(command, **kwargs)
            self.source.write_bytes(b'(kicad_sch\n)\n')
            return result
        with patch('notes.y4.produce_current_observations.subprocess.run', drift):
            with self.assertRaisesRegex(ObservationError, 'source drift'):
                self.generate()
        self.assertFalse((self.output / 'observation_binding.json').exists())

    def test_invalid_utf8_source_rejected_before_export(self):
        # Non-UTF-8 bytes must fail closed through explicit logic (assert-based
        # checks would vanish under `python -O`).
        invalid = b'(kicad_sch \xff\xfe)\r\n'
        self.source.write_bytes(invalid)
        with patch('notes.y4.produce_current_observations.subprocess.run') as exporter:
            with self.assertRaisesRegex(ObservationError, 'not exact UTF-8'):
                generate_current(self.source, self.output, ['synthetic-test-only'])
            exporter.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_stale_audit_pin_rejected_before_export(self):
        self.source.write_bytes(b'(kicad_sch changed)')
        with patch('notes.y4.produce_current_observations.subprocess.run') as exporter:
            with self.assertRaisesRegex(ObservationError, 'selected source hash mismatch'):
                self.generate()
            exporter.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_existing_destination_cannot_be_overwritten(self):
        self.output.mkdir()
        (self.output / 'keep').write_bytes(b'old')
        with self.assertRaises(FileExistsError):
            self.generate()
        self.assertEqual((self.output / 'keep').read_bytes(), b'old')

    def test_timeout_has_no_binding(self):
        with patch('notes.y4.produce_current_observations.subprocess.run', side_effect=subprocess.TimeoutExpired([], 1)):
            with self.assertRaisesRegex(ObservationError, 'timed out'):
                self.generate()
        self.assertFalse((self.output / 'observation_binding.json').exists())

    def test_hierarchy_needs_additional_bound_sources(self):
        self.source.write_bytes(b'(kicad_sch (sheet (file other.kicad_sch)))')
        with self.assertRaisesRegex(ObservationError, 'hierarchical'):
            generate_current(self.source, self.output, [])

    def test_bad_xml_and_empty_coverage_rejected(self):
        for raw in (b'', b'<broken', b'<export/>', b'<!DOCTYPE export><export/>'):
            with self.subTest(raw=raw), self.assertRaises(ObservationError):
                project_current_xml(raw)

    def test_unknown_duplicate_and_multiply_connected_pins_rejected(self):
        cases = [XML.replace(b'ref="X1" pin', b'ref="X2" pin'),
                 XML.replace(b'</nets>', b'<net code="2" name="M"><node ref="X1" pin="1"/></net></nets>'),
                 XML.replace(b'</components>', b'<comp ref="X1"><value>x</value><libsource lib="a" part="b"/></comp></components>')]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ObservationError):
                project_current_xml(raw)


if __name__ == '__main__':
    unittest.main()
