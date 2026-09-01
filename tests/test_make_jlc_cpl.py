import csv
from pathlib import Path
import tempfile
import unittest

from gates.make_jlc_cpl import generate_jlc_cpl


KICAD_HEADER = "Ref,Val,Package,PosX,PosY,Rot,Side\n"


class MakeJlcCplTests(unittest.TestCase):
    def _write_source(self, root: Path, body: str) -> Path:
        source = root / "kicad-pos.csv"
        source.write_text(KICAD_HEADER + body, encoding="utf-8")
        return source

    def test_converts_kicad_columns_and_maps_board_sides(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._write_source(
                root,
                "R7,22R,R_0603,10.250,-2.500,90,top\n"
                "C5,1uF,C_0603,11,3.125,-180,bottom\n",
            )
            output = root / "jlc-cpl.csv"

            self.assertEqual(generate_jlc_cpl(source, output, units="mm"), 2)
            with output.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                self.assertEqual(
                    reader.fieldnames,
                    ["Designator", "Mid X", "Mid Y", "Rotation", "Layer"],
                )

        self.assertEqual(
            rows,
            [
                {
                    "Designator": "R7",
                    "Mid X": "10.250",
                    "Mid Y": "-2.500",
                    "Rotation": "90",
                    "Layer": "Top",
                },
                {
                    "Designator": "C5",
                    "Mid X": "11",
                    "Mid Y": "3.125",
                    "Rotation": "-180",
                    "Layer": "Bottom",
                },
            ],
        )

    def test_rejects_units_other_than_explicit_millimetres(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._write_source(root, "R7,22R,R_0603,1,2,0,top\n")
            with self.assertRaisesRegex(ValueError, "units.*mm"):
                generate_jlc_cpl(source, root / "out.csv", units="in")

    def test_rejects_non_exact_kicad_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "kicad-pos.csv"
            source.write_text(
                KICAD_HEADER.rstrip("\n") + ",Unexpected\n"
                "R7,22R,R_0603,1,2,0,top,value\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "header"):
                generate_jlc_cpl(source, root / "out.csv", units="mm")

    def test_rejects_duplicate_designators(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._write_source(
                root,
                "R7,22R,R_0603,1,2,0,top\n"
                "R7,22R,R_0603,3,4,180,bottom\n",
            )
            with self.assertRaisesRegex(ValueError, "duplicate.*R7"):
                generate_jlc_cpl(source, root / "out.csv", units="mm")

    def test_rejects_non_finite_or_missing_numeric_fields(self):
        invalid_values = ("nan,2,0", "1,inf,0", "1,2,-inf", "1,,0")
        for numeric_fields in invalid_values:
            with self.subTest(numeric_fields=numeric_fields):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    source = self._write_source(
                        root,
                        f"R7,22R,R_0603,{numeric_fields},top\n",
                    )
                    with self.assertRaisesRegex(ValueError, "finite number"):
                        generate_jlc_cpl(source, root / "out.csv", units="mm")

    def test_rejects_unknown_side_without_overwriting_existing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = self._write_source(root, "R7,22R,R_0603,1,2,0,front\n")
            output = root / "out.csv"
            output.write_bytes(b"sentinel")

            with self.assertRaisesRegex(ValueError, "Side"):
                generate_jlc_cpl(source, output, units="mm")

            self.assertEqual(output.read_bytes(), b"sentinel")

    def test_rejects_blank_required_text_fields_and_empty_input(self):
        invalid_bodies = (
            ",22R,R_0603,1,2,0,top\n",
            "R7,,R_0603,1,2,0,top\n",
            "R7,22R,,1,2,0,top\n",
            "",
        )
        for body in invalid_bodies:
            with self.subTest(body=body):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    source = self._write_source(root, body)
                    with self.assertRaises(ValueError):
                        generate_jlc_cpl(source, root / "out.csv", units="mm")


if __name__ == "__main__":
    unittest.main()
