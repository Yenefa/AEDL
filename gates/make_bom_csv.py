# -*- coding: utf-8 -*-
"""Generate the per-reference delivery BOM from the canonical grouped BOM."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
import tempfile
from typing import List, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "gates" / "bom" / "bom_v1.json"
DEFAULT_OUTPUT = ROOT / "delivery" / "bom.csv"
FIELDNAMES = (
    "Comment",
    "Designator",
    "Footprint",
    "LCSC Part #",
    "JLC Lib",
    "Stock@freeze",
)

if __package__:
    from .gate_core import validate_bom
else:
    sys.path.insert(0, str(ROOT))
    from gates.gate_core import validate_bom


def generate_bom_csv(source_path: Path, output_path: Path) -> int:
    """Validate *source_path* and atomically generate *output_path*.

    The returned integer is the number of physical reference rows. Invalid input
    raises ``ValueError`` before the existing output is touched.
    """
    source_path = Path(source_path)
    output_path = Path(output_path)
    errors = validate_bom(source_path)
    if errors:
        raise ValueError("invalid canonical BOM: " + "; ".join(errors))

    with source_path.open("r", encoding="utf-8-sig") as handle:
        bom = json.load(handle)

    rows = []
    for item in bom["items"]:
        for ref in (part.strip() for part in item["ref"].split(",")):
            rows.append(
                {
                    "Comment": item["value"],
                    "Designator": ref,
                    "Footprint": item["footprint"],
                    "LCSC Part #": item["lcsc"],
                    "JLC Lib": item["jlc_lib"],
                    "Stock@freeze": item["stock"],
                }
            )
    rows.sort(key=lambda row: row["Designator"])

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
            writer = csv.DictWriter(temporary, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        Path(temporary_name).replace(output_path)
    finally:
        if temporary_name:
            temporary_path = Path(temporary_name)
            if temporary_path.exists():
                temporary_path.unlink()
    return len(rows)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    try:
        row_count = generate_bom_csv(args.source, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "fail", "errors": [str(error)]}, ensure_ascii=False))
        return 1

    print(
        json.dumps(
            {
                "status": "pass",
                "rows": row_count,
                "message": f"bom rows={row_count}",
                "source": str(args.source),
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
