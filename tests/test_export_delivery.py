import json
from pathlib import Path
import tempfile
import unittest

from gates.export_delivery import (
    EXPECTED_GERBER_FILES,
    PRODUCTION_LAYERS,
    build_export_commands,
    create_gerber_zip,
    validate_gerber_set,
)
from gates.gate_core import zip_entry_names


class ExportDeliveryTests(unittest.TestCase):
    def test_commands_pin_production_layers_and_millimetre_cpl(self):
        root = Path("C:/repo")
        commands = build_export_commands(
            Path("C:/KiCad/kicad-cli.exe"),
            root / "board.kicad_pcb",
            root / "gerbers",
            root / "raw-pos.csv",
        )

        gerbers, drill, pos = commands
        self.assertEqual(gerbers[gerbers.index("--layers") + 1], ",".join(PRODUCTION_LAYERS))
        self.assertIn("--check-zones", gerbers)
        self.assertIn("--subtract-soldermask", gerbers)
        self.assertNotIn("--no-protel-ext", gerbers)
        self.assertNotIn("--no-x2", gerbers)
        self.assertNotIn("--no-netlist", gerbers)
        self.assertEqual(drill[drill.index("--excellon-units") + 1], "mm")
        self.assertEqual(drill[drill.index("--drill-origin") + 1], "absolute")
        self.assertEqual(drill[drill.index("--excellon-zeros-format") + 1], "decimal")
        self.assertEqual(pos[pos.index("--units") + 1], "mm")
        self.assertEqual(pos[pos.index("--side") + 1], "both")
        self.assertIn("--exclude-dnp", pos)
        self.assertNotIn("--bottom-negate-x", pos)

    def test_gerber_set_and_job_file_must_match_exact_production_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in EXPECTED_GERBER_FILES:
                (root / name).write_text("data", encoding="utf-8")
            job_path = root / "m2_board-job.gbrjob"
            job_path.write_text(
                json.dumps(
                    {
                        "FilesAttributes": [
                            {"Path": name}
                            for name in sorted(
                                EXPECTED_GERBER_FILES
                                - {"m2_board-job.gbrjob", "m2_board.drl"}
                            )
                        ]
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(validate_gerber_set(root), [])
            (root / "m2_board-User_Comments.gbr").write_text("unsafe", encoding="utf-8")
            self.assertTrue(any("unexpected" in error for error in validate_gerber_set(root)))

    def test_zip_contains_only_the_validated_flat_gerber_set(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            gerbers = root / "gerbers"
            gerbers.mkdir()
            for name in EXPECTED_GERBER_FILES:
                (gerbers / name).write_text(name, encoding="utf-8")
            (gerbers / "m2_board-job.gbrjob").write_text(
                json.dumps(
                    {
                        "FilesAttributes": [
                            {"Path": name}
                            for name in sorted(
                                EXPECTED_GERBER_FILES
                                - {"m2_board-job.gbrjob", "m2_board.drl"}
                            )
                        ]
                    }
                ),
                encoding="utf-8",
            )
            archive = root / "delivery.zip"

            create_gerber_zip(gerbers, archive)

            self.assertEqual(zip_entry_names(archive), sorted(EXPECTED_GERBER_FILES))


if __name__ == "__main__":
    unittest.main()
