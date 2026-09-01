# -*- coding: utf-8 -*-
"""Convert a KiCad 10 position CSV into a JLC-ready CPL CSV."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import sys
import tempfile
from typing import List, Optional


KICAD_FIELDS = ("Ref", "Val", "Package", "PosX", "PosY", "Rot", "Side")
JLC_FIELDS = ("Designator", "Mid X", "Mid Y", "Rotation", "Layer")
SIDE_MAP = {"top": "Top", "bottom": "Bottom"}


def _require_text(value: str, *, field: str, row_number: int) -> str:
    if not value.strip():
        raise ValueError(f"row {row_number}: {field} must not be blank")
    return value


def _require_finite_number(value: str, *, field: str, row_number: int) -> str:
    if not value.strip():
        raise ValueError(f"row {row_number}: {field} must be a finite number")
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(
            f"row {row_number}: {field} must be a finite number"
        ) from error
    if not math.isfinite(number):
        raise ValueError(f"row {row_number}: {field} must be a finite number")
    return value


def generate_jlc_cpl(source_path: Path, output_path: Path, *, units: str) -> int:
    """Validate and atomically convert a KiCad 10 position CSV.

    ``units`` is deliberately mandatory and only ``"mm"`` is accepted. Numeric
    text is validated but copied verbatim; no coordinate or rotation correction
    is applied.
    """
    if units != "mm":
        raise ValueError("units must be explicitly set to 'mm'")

    source_path = Path(source_path)
    output_path = Path(output_path)
    converted_rows = []
    seen_refs = set()

    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError("KiCad CSV is empty; expected an exact header") from error
        if tuple(header) != KICAD_FIELDS:
            raise ValueError(
                "KiCad CSV header must be exactly: " + ",".join(KICAD_FIELDS)
            )

        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(KICAD_FIELDS):
                raise ValueError(
                    f"row {row_number}: expected {len(KICAD_FIELDS)} fields, got {len(row)}"
                )
            ref, value, package, pos_x, pos_y, rotation, side = row
            _require_text(ref, field="Ref", row_number=row_number)
            _require_text(value, field="Val", row_number=row_number)
            _require_text(package, field="Package", row_number=row_number)
            if ref in seen_refs:
                raise ValueError(f"row {row_number}: duplicate Ref {ref}")
            seen_refs.add(ref)

            _require_finite_number(pos_x, field="PosX", row_number=row_number)
            _require_finite_number(pos_y, field="PosY", row_number=row_number)
            _require_finite_number(rotation, field="Rot", row_number=row_number)
            if side not in SIDE_MAP:
                raise ValueError(
                    f"row {row_number}: Side must be exactly 'top' or 'bottom'"
                )

            converted_rows.append(
                {
                    "Designator": ref,
                    "Mid X": pos_x,
                    "Mid Y": pos_y,
                    "Rotation": rotation,
                    "Layer": SIDE_MAP[side],
                }
            )

    if not converted_rows:
        raise ValueError("KiCad CSV must contain at least one placement row")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=str(output_path.parent),
            prefix=output_path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            writer = csv.DictWriter(temporary, fieldnames=JLC_FIELDS)
            writer.writeheader()
            writer.writerows(converted_rows)
        Path(temporary_name).replace(output_path)
    finally:
        if temporary_name:
            temporary_path = Path(temporary_name)
            if temporary_path.exists():
                temporary_path.unlink()

    return len(converted_rows)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--units", required=True, choices=("mm",))
    args = parser.parse_args(argv)

    try:
        row_count = generate_jlc_cpl(args.source, args.output, units=args.units)
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        print(json.dumps({"status": "fail", "errors": [str(error)]}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "status": "pass",
                "rows": row_count,
                "source": str(args.source),
                "output": str(args.output),
                "units": args.units,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
