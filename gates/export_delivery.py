# -*- coding: utf-8 -*-
"""Export a clean, hash-bound JLCPCB manufacturing package from the M2 PCB."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SCHEMA = "https://aedl.local/schemas/m2-delivery-manifest.v1.json"
PRODUCTION_LAYERS = (
    "F.Cu",
    "B.Cu",
    "F.Paste",
    "B.Paste",
    "F.Silkscreen",
    "B.Silkscreen",
    "F.Mask",
    "B.Mask",
    "Edge.Cuts",
)
EXPECTED_GERBER_FILES = {
    "m2_board-F_Cu.gtl",
    "m2_board-B_Cu.gbl",
    "m2_board-F_Paste.gtp",
    "m2_board-B_Paste.gbp",
    "m2_board-F_Silkscreen.gto",
    "m2_board-B_Silkscreen.gbo",
    "m2_board-F_Mask.gts",
    "m2_board-B_Mask.gbs",
    "m2_board-Edge_Cuts.gm1",
    "m2_board-job.gbrjob",
    "m2_board.drl",
}
JOB_GERBER_FILES = EXPECTED_GERBER_FILES - {
    "m2_board-job.gbrjob",
    "m2_board.drl",
}

if __package__:
    from .gate_core import (
        read_bom_refs,
        read_intent_physical_refs,
        read_pos_refs,
        sha256_file,
        validate_bom,
        validate_bom_freshness,
        validate_bom_stock_evidence,
    )
    from .make_bom_csv import generate_bom_csv
    from .make_jlc_cpl import generate_jlc_cpl
else:
    sys.path.insert(0, str(ROOT))
    from gates.gate_core import (  # type: ignore
        read_bom_refs,
        read_intent_physical_refs,
        read_pos_refs,
        sha256_file,
        validate_bom,
        validate_bom_freshness,
        validate_bom_stock_evidence,
    )
    from gates.make_bom_csv import generate_bom_csv  # type: ignore
    from gates.make_jlc_cpl import generate_jlc_cpl  # type: ignore


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_export_commands(
    kicad_cli: Path,
    board: Path,
    gerber_dir: Path,
    raw_pos: Path,
) -> Tuple[List[str], List[str], List[str]]:
    """Build the pinned KiCad commands; the explicit units/layers are safety controls."""
    cli = str(kicad_cli)
    board_arg = str(board)
    gerbers = [
        cli,
        "pcb",
        "export",
        "gerbers",
        "--layers",
        ",".join(PRODUCTION_LAYERS),
        "--check-zones",
        "--subtract-soldermask",
        "--precision",
        "6",
        "--output",
        str(gerber_dir),
        board_arg,
    ]
    drill = [
        cli,
        "pcb",
        "export",
        "drill",
        "--format",
        "excellon",
        "--drill-origin",
        "absolute",
        "--excellon-zeros-format",
        "decimal",
        "--excellon-oval-format",
        "alternate",
        "--excellon-units",
        "mm",
        "--output",
        str(gerber_dir),
        board_arg,
    ]
    pos = [
        cli,
        "pcb",
        "export",
        "pos",
        "--format",
        "csv",
        "--units",
        "mm",
        "--side",
        "both",
        "--exclude-dnp",
        "--output",
        str(raw_pos),
        board_arg,
    ]
    return gerbers, drill, pos


def validate_gerber_set(gerber_dir: Path) -> List[str]:
    """Require exactly the ordinary FR-4 production layers and a matching job file."""
    gerber_dir = Path(gerber_dir)
    errors: List[str] = []
    if not gerber_dir.is_dir():
        return [f"Gerber directory does not exist: {gerber_dir}"]
    actual = {entry.name for entry in gerber_dir.iterdir() if entry.is_file()}
    missing = sorted(EXPECTED_GERBER_FILES - actual)
    unexpected = sorted(actual - EXPECTED_GERBER_FILES)
    if missing:
        errors.append(f"missing Gerber production files: {missing}")
    if unexpected:
        errors.append(f"unexpected non-production Gerber files: {unexpected}")

    job_path = gerber_dir / "m2_board-job.gbrjob"
    if job_path.is_file():
        try:
            job = json.loads(job_path.read_text(encoding="utf-8-sig"))
            attributes = job.get("FilesAttributes") if isinstance(job, dict) else None
            if not isinstance(attributes, list) or not attributes:
                raise ValueError("FilesAttributes must be a non-empty list")
            paths = []
            for index, item in enumerate(attributes):
                if not isinstance(item, dict) or not isinstance(item.get("Path"), str):
                    raise ValueError(f"FilesAttributes[{index}] has no Path")
                path = item["Path"].replace("\\", "/")
                if "/" in path or path in paths:
                    raise ValueError(f"unsafe or duplicate job path {path!r}")
                paths.append(path)
            job_files = set(paths)
            if job_files != JOB_GERBER_FILES:
                errors.append(
                    "Gerber job file layer set differs from production layer set: "
                    f"missing={sorted(JOB_GERBER_FILES - job_files)} "
                    f"unexpected={sorted(job_files - JOB_GERBER_FILES)}"
                )
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid Gerber job file: {type(exc).__name__}: {exc}")
    return errors


def create_gerber_zip(gerber_dir: Path, archive_path: Path) -> None:
    """Create a flat ZIP only after the exact production file set validates."""
    errors = validate_gerber_set(gerber_dir)
    if errors:
        raise ValueError("; ".join(errors))
    archive_path = Path(archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(archive_path), "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(EXPECTED_GERBER_FILES):
            archive.write(str(Path(gerber_dir) / name), arcname=name)


def _find_kicad_cli(explicit: Optional[str]) -> Optional[Path]:
    candidates: List[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    found = shutil.which("kicad-cli")
    if found:
        candidates.append(Path(found))
    candidates.append(Path(r"C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _run_checked(command: Sequence[str], cwd: Path) -> str:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        timeout=180,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
    stderr = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout={stdout[-1000:]}\nstderr={stderr[-1000:]}"
        )
    return stdout.strip()


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _safe_remove_publish_path(path: Path, delivery_dir: Path) -> None:
    resolved_parent = path.resolve().parent
    if resolved_parent != delivery_dir.resolve():
        raise RuntimeError(f"refusing to remove path outside delivery directory: {path}")
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _publish(stage: Path, delivery_dir: Path) -> None:
    names = (
        "gerbers",
        "bom.csv",
        "pos.csv",
        "jlc_gerber_upload.zip",
        "manifest_v1.json",
    )
    backup = delivery_dir / ".delivery-previous"
    if backup.exists():
        raise RuntimeError(
            f"previous recovery directory exists; inspect and restore it before export: {backup}"
        )
    backup.mkdir()
    moved_old: List[str] = []
    moved_new: List[str] = []
    try:
        for name in names:
            current = delivery_dir / name
            if current.exists():
                current.replace(backup / name)
                moved_old.append(name)
        for name in names:
            source = stage / name
            if not source.exists():
                raise RuntimeError(f"staged delivery output is missing: {source}")
            source.replace(delivery_dir / name)
            moved_new.append(name)
    except Exception:
        for name in reversed(moved_new):
            _safe_remove_publish_path(delivery_dir / name, delivery_dir)
        for name in reversed(moved_old):
            (backup / name).replace(delivery_dir / name)
        raise
    else:
        _safe_remove_publish_path(backup, delivery_dir)


def export_delivery(root: Path, kicad_cli: Path) -> Dict[str, Any]:
    """Generate, validate, hash-bind, and publish the complete M2 delivery package."""
    root = Path(root).resolve()
    delivery_dir = root / "delivery"
    delivery_dir.mkdir(parents=True, exist_ok=True)
    board = root / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb"
    intent = root / "src" / "hardware" / "m2-board" / "intent_v1.json"
    bom = root / "gates" / "bom" / "bom_v1.json"
    stock_evidence = root / "notes" / "m2-evidence-reset" / "generated" / "bom_stock_current.json"
    for source in (board, intent, bom, stock_evidence):
        if not source.is_file():
            raise FileNotFoundError(f"required delivery source is missing: {source}")
    bom_errors = validate_bom(bom) + validate_bom_freshness(bom)
    bom_errors.extend(validate_bom_stock_evidence(bom, stock_evidence))
    if bom_errors:
        raise ValueError("canonical BOM is not current and valid: " + "; ".join(bom_errors))

    kicad_version = _run_checked([str(kicad_cli), "version"], root)
    with tempfile.TemporaryDirectory(prefix=".delivery-stage-", dir=str(delivery_dir)) as temp_dir:
        stage = Path(temp_dir)
        gerber_dir = stage / "gerbers"
        gerber_dir.mkdir()
        raw_pos = stage / "kicad-pos-mm.csv"
        commands = build_export_commands(kicad_cli, board, gerber_dir, raw_pos)
        for command in commands:
            _run_checked(command, root)

        gerber_errors = validate_gerber_set(gerber_dir)
        if gerber_errors:
            raise ValueError("invalid Gerber export: " + "; ".join(gerber_errors))
        cpl_rows = generate_jlc_cpl(raw_pos, stage / "pos.csv", units="mm")
        bom_rows = generate_bom_csv(bom, stage / "bom.csv")

        intent_refs = read_intent_physical_refs(intent)
        bom_refs = read_bom_refs(bom)
        pos_refs = read_pos_refs(stage / "pos.csv")
        delivery_bom_refs = read_pos_refs(stage / "bom.csv")
        if not (intent_refs == bom_refs == pos_refs == delivery_bom_refs):
            raise ValueError(
                "staged reference sets differ: "
                f"intent={len(intent_refs)} bom={len(bom_refs)} "
                f"cpl={len(pos_refs)} delivery_bom={len(delivery_bom_refs)}"
            )
        if cpl_rows != len(intent_refs) or bom_rows != len(intent_refs):
            raise ValueError("staged BOM/CPL row count differs from physical intent")

        archive = stage / "jlc_gerber_upload.zip"
        create_gerber_zip(gerber_dir, archive)
        generated_at = _utc_now()
        manifest = {
            "$schema": MANIFEST_SCHEMA,
            "schema_version": 1,
            "generated_at": generated_at,
            "generator": "gates/export_delivery.py",
            "kicad_cli": str(kicad_cli),
            "kicad_version": kicad_version,
            "settings": {
                "gerber_layers": list(PRODUCTION_LAYERS),
                "gerber_x2": True,
                "gerber_netlist_attributes": True,
                "gerber_protel_extensions": True,
                "position_units": "mm",
                "position_sides": "both",
                "bottom_x_negated": False,
                "rotation_correction_applied": False,
                "jlc_preview_orientation_review_required": True,
            },
            "sources": {
                "board": {"path": str(board.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(board)},
                "intent": {"path": str(intent.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(intent)},
                "bom": {"path": str(bom.relative_to(root)).replace("\\", "/"), "sha256": sha256_file(bom)},
                "bom_stock_evidence": {
                    "path": str(stock_evidence.relative_to(root)).replace("\\", "/"),
                    "sha256": sha256_file(stock_evidence),
                },
            },
            "artifacts": {
                "bom": {"path": "delivery/bom.csv", "sha256": sha256_file(stage / "bom.csv"), "rows": bom_rows},
                "cpl": {"path": "delivery/pos.csv", "sha256": sha256_file(stage / "pos.csv"), "rows": cpl_rows},
                "gerber_zip": {
                    "path": "delivery/jlc_gerber_upload.zip",
                    "sha256": sha256_file(archive),
                    "entries": sorted(EXPECTED_GERBER_FILES),
                },
                "gerbers": {
                    name: sha256_file(gerber_dir / name)
                    for name in sorted(EXPECTED_GERBER_FILES)
                },
            },
        }
        _write_json(stage / "manifest_v1.json", manifest)
        _publish(stage, delivery_dir)
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--kicad-cli", default=None)
    args = parser.parse_args(argv)
    cli = _find_kicad_cli(args.kicad_cli)
    if cli is None:
        print("[DELIVERY] FAIL kicad-cli not found")
        return 1
    try:
        manifest = export_delivery(args.root, cli)
    except Exception as exc:
        print(f"[DELIVERY] FAIL {type(exc).__name__}: {exc}")
        return 1
    print(
        f"[DELIVERY] PASS rows={manifest['artifacts']['bom']['rows']} "
        f"zip_entries={len(manifest['artifacts']['gerber_zip']['entries'])} "
        f"board_sha256={manifest['sources']['board']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
