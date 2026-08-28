"""Run the project-027 M2 evidence gates with fail-closed semantics.

The runner deliberately treats KiCad's process exit code as diagnostic only;
the structured ERC/DRC reports are parsed by :mod:`gate_core` and determine
the gate verdict.  A manifest is written even when a tool or report is
missing, so a failed run remains auditable.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Dict, Iterable, List, Optional

try:
    from .gate_core import (
        count_drc_findings,
        erc_gate_verdict,
        drc_gate_verdict,
        read_bom_refs,
        read_pos_refs,
        sha256_file,
        validate_board_review,
        validate_bom,
        zip_entry_names,
    )
except ImportError:  # direct ``py gates/run_gates.py`` execution
    from gate_core import (  # type: ignore
        count_drc_findings,
        drc_gate_verdict,
        erc_gate_verdict,
        read_bom_refs,
        read_pos_refs,
        sha256_file,
        validate_board_review,
        validate_bom,
        zip_entry_names,
    )


REQUIRED_ZIP_ENTRIES = {
    "m2_board-Edge_Cuts.gm1",
    "m2_board-F_Cu.gtl",
    "m2_board-B_Cu.gbl",
    "m2_board.drl",
    "m2_board-job.gbrjob",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _gate(name: str, status: str, details: Optional[Dict[str, Any]] = None, errors: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "details": details or {},
        "errors": list(errors or []),
    }


def _safe_gate(name: str, callback) -> Dict[str, Any]:
    try:
        return callback()
    except Exception as exc:  # malformed evidence must never become green
        return _gate(name, "fail", errors=[f"{type(exc).__name__}: {exc}"])


def _evaluate_erc(path: Path) -> Dict[str, Any]:
    verdict = erc_gate_verdict(path)
    return _gate("erc", verdict["status"], verdict, ["ERC error violations present"] if verdict["status"] == "fail" else [])


def _evaluate_drc(path: Path) -> Dict[str, Any]:
    verdict = drc_gate_verdict(path)
    return _gate("drc", verdict["status"], verdict, ["DRC findings present"] if verdict["status"] == "fail" else [])


def _evaluate_bom(root: Path) -> Dict[str, Any]:
    path = root / "gates" / "bom" / "bom_v1.json"
    errors = validate_bom(path)
    return _gate("bom", "pass" if not errors else "fail", {"path": str(path), "error_count": len(errors)}, errors)


def _evaluate_delivery(root: Path) -> Dict[str, Any]:
    bom = root / "gates" / "bom" / "bom_v1.json"
    pos = root / "delivery" / "pos.csv"
    csv_path = root / "delivery" / "bom.csv"
    archive = root / "delivery" / "jlc_gerber_upload.zip"
    errors: List[str] = []
    details: Dict[str, Any] = {"paths": [str(bom), str(pos), str(csv_path), str(archive)]}
    for path in (bom, pos, csv_path, archive):
        if not path.is_file():
            errors.append(f"missing delivery artifact: {path}")

    if not errors:
        bom_refs = read_bom_refs(bom)
        pos_refs = read_pos_refs(pos)
        details["bom_ref_count"] = len(bom_refs)
        details["pos_ref_count"] = len(pos_refs)
        if bom_refs != pos_refs:
            errors.append("BOM and POS reference sets differ")
        names = set(zip_entry_names(archive))
        details["zip_entry_count"] = len(names)
        missing = sorted(REQUIRED_ZIP_ENTRIES - names)
        if missing:
            errors.append(f"ZIP is missing required entries: {missing}")
    return _gate("delivery", "pass" if not errors else "fail", details, errors)


def _evaluate_intent(root: Path) -> Dict[str, Any]:
    path = root / "src" / "hardware" / "m2-board" / "intent_v1.json"
    errors: List[str] = []
    details: Dict[str, Any] = {"path": str(path)}
    if not path.is_file():
        return _gate("intent", "fail", details, [f"missing intent: {path}"])
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    components = data.get("components")
    nets = data.get("nets")
    if data.get("protocol_version") != 1:
        errors.append("intent protocol_version must be 1")
    if not isinstance(components, dict) or not components:
        errors.append("intent components must be a non-empty object")
        components = {}
    if not isinstance(nets, dict) or not nets:
        errors.append("intent nets must be a non-empty object")
        nets = {}
    details["component_count"] = len(components)
    details["net_count"] = len(nets)
    for ref, component in components.items():
        if not isinstance(ref, str) or not ref:
            errors.append("intent contains an empty component reference")
        if not isinstance(component, dict) or not isinstance(component.get("lib_id"), str):
            errors.append(f"intent component {ref!r} has no lib_id")
        if isinstance(component, dict) and component.get("virtual"):
            errors.append(f"intent contains unsupported virtual component {ref}")
    for net, members in nets.items():
        if not isinstance(members, list) or len(members) < 2:
            errors.append(f"intent net {net!r} must have at least two members")
            continue
        for member in members:
            if not isinstance(member, str) or "." not in member:
                errors.append(f"intent net {net!r} has malformed member {member!r}")
                continue
            ref = member.split(".", 1)[0]
            if ref not in components:
                errors.append(f"intent net {net!r} references unknown component {ref}")
    return _gate("intent", "pass" if not errors else "fail", details, errors)


def _evaluate_ops(root: Path) -> Dict[str, Any]:
    path = root / "notes" / "m1-evidence" / "ops_validate.json"
    if not path.is_file():
        return _gate("ops", "fail", {"path": str(path)}, [f"missing operations evidence: {path}"])
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    errors = []
    if data.get("valid") is not True:
        errors.append("ops_validate.valid is not true")
    if data.get("errors") != []:
        errors.append("ops_validate.errors is not empty")
    return _gate("ops", "pass" if not errors else "fail", {"path": str(path), "op_count": data.get("op_count")}, errors)


def _evaluate_board_review(path: Path) -> Dict[str, Any]:
    errors = validate_board_review(path)
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    reviews = data.get("reviews") if isinstance(data.get("reviews"), list) else []
    status_counts: Dict[str, int] = {}
    for review in reviews:
        if isinstance(review, dict) and isinstance(review.get("status"), str):
            status = review["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
    metadata = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
    details = {
        "path": str(path),
        "review_count": len(reviews),
        "status_counts": status_counts,
        "manufacturing_release": metadata.get("manufacturing_release"),
    }
    return _gate("board_review", "pass" if not errors else "fail", details, errors)


def evaluate_evidence(root: Path, erc_report: Path, drc_report: Path, board_review: Path) -> Dict[str, Any]:
    """Evaluate all non-process evidence and return a serializable manifest."""
    root = Path(root).resolve()
    gates = [
        _safe_gate("erc", lambda: _evaluate_erc(Path(erc_report))),
        _safe_gate("drc", lambda: _evaluate_drc(Path(drc_report))),
        _safe_gate("bom", lambda: _evaluate_bom(root)),
        _safe_gate("delivery", lambda: _evaluate_delivery(root)),
        _safe_gate("intent", lambda: _evaluate_intent(root)),
        _safe_gate("ops", lambda: _evaluate_ops(root)),
        _safe_gate("board_review", lambda: _evaluate_board_review(Path(board_review))),
    ]
    passed = all(gate["status"] == "pass" for gate in gates)
    return {
        "schema_version": "m2-evidence-reset.v1",
        "status": "pass" if passed else "fail",
        "exit_code": 0 if passed else 1,
        "gates": gates,
    }


def _find_kicad_cli(explicit: Optional[str]) -> Optional[Path]:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    env_value = __import__("os").environ.get("KICAD_CLI")
    if env_value:
        candidates.append(Path(env_value))
    found = shutil.which("kicad-cli")
    if found:
        candidates.append(Path(found))
    candidates.append(Path(r"C:\Users\fuker\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _run_tool(command: List[str], cwd: Path) -> Dict[str, Any]:
    try:
        # KiCad may emit a mixture of UTF-8 and the Windows console code page.
        # Capture bytes and decode lossily so a diagnostic encoding mismatch
        # cannot hide the real process exit code or report file.
        completed = subprocess.run(command, cwd=str(cwd), capture_output=True, timeout=180)
        stdout = completed.stdout.decode("utf-8", errors="replace") if completed.stdout else ""
        stderr = completed.stderr.decode("utf-8", errors="replace") if completed.stderr else ""
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": stdout[-2000:],
            "stderr": stderr[-2000:],
        }
    except Exception as exc:
        return {"command": command, "exit_code": None, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _git_snapshot(root: Path) -> Dict[str, Any]:
    def call(arguments: List[str]) -> str:
        completed = subprocess.run(
            ["git", *arguments], cwd=str(root), capture_output=True, timeout=30
        )
        return (completed.stdout or b"").decode("utf-8", errors="replace").strip()

    commit = call(["rev-parse", "HEAD"])
    status = call(["status", "--porcelain"])
    return {"commit": commit or None, "dirty": bool(status), "status_porcelain": status}


def _artifact_hashes(paths: Dict[str, Path]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for name, path in paths.items():
        result[name] = {
            "path": str(path),
            "sha256": sha256_file(path) if path.is_file() else None,
            "exists": path.is_file(),
        }
    return result


def run(root: Path, kicad_cli: Optional[str] = None, manifest_path: Optional[Path] = None, skip_kicad: bool = False) -> Dict[str, Any]:
    root = Path(root).resolve()
    # Snapshot repository state before the runner rewrites its own reports.
    git = _git_snapshot(root)
    evidence_dir = root / "notes" / "m2-evidence-reset" / "generated"
    erc_report = evidence_dir / "g2_erc_current.json"
    drc_report = evidence_dir / "g4_drc_current.json"
    tools: List[Dict[str, Any]] = []
    tool_errors: List[str] = []

    if skip_kicad:
        erc_report = root / "notes" / "m1-evidence" / "g2_erc_m2board.json"
        drc_report = root / "notes" / "m1-evidence" / "g4_drc_final.json"
        tools.append({"name": "kicad", "skipped": True, "reason": "--skip-kicad"})
    else:
        cli = _find_kicad_cli(kicad_cli)
        if cli is None:
            tool_errors.append("kicad-cli not found; rerun with --kicad-cli or install KiCad")
        else:
            sch = root / "src" / "hardware" / "m2-board" / "m2_board.kicad_sch"
            board = root / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            erc_command = [str(cli), "sch", "erc", "--format", "json", "--severity-all", "--exit-code-violations", "--output", str(erc_report), str(sch)]
            drc_command = [str(cli), "pcb", "drc", "--format", "json", "--severity-all", "--exit-code-violations", "--output", str(drc_report), str(board)]
            tools.append({"name": "kicad_erc", **_run_tool(erc_command, root)})
            tools.append({"name": "kicad_drc", **_run_tool(drc_command, root)})

    board_review = root / "gates" / "board_review_v1.json"
    evidence = evaluate_evidence(root, erc_report, drc_report, board_review)
    if tool_errors:
        evidence["gates"].append(_gate("kicad_tool", "fail", errors=tool_errors))
        evidence["status"] = "fail"
        evidence["exit_code"] = 1
    run_at = _utc_now()
    for gate in evidence["gates"]:
        gate["evidence_grade"] = "C" if gate["name"] == "board_review" else "A"
    artifacts = _artifact_hashes(
        {
            "intent": root / "src" / "hardware" / "m2-board" / "intent_v1.json",
            "bom": root / "gates" / "bom" / "bom_v1.json",
            "pos": root / "delivery" / "pos.csv",
            "delivery_bom": root / "delivery" / "bom.csv",
            "gerber_zip": root / "delivery" / "jlc_gerber_upload.zip",
            "board_review": board_review,
            "erc_report": erc_report,
            "drc_report": drc_report,
        }
    )
    manifest = {
        "schema_version": "m2-evidence-reset-run.v1",
        "run_id": f"m2-{git.get('commit') or 'unknown'}-{run_at}",
        "run_at": run_at,
        "root": str(root),
        "git": git,
        "status": evidence["status"],
        "exit_code": evidence["exit_code"],
        "tool_runs": tools,
        "reports": {"erc": str(erc_report), "drc": str(drc_report)},
        "artifacts": artifacts,
        "gates": evidence["gates"],
    }
    target = Path(manifest_path) if manifest_path else root / "notes" / "m2-evidence-reset" / "run_manifest.json"
    _write_json_atomic(target, manifest)
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    parser.add_argument("--kicad-cli", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--skip-kicad", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    manifest = run(root, args.kicad_cli, Path(args.manifest) if args.manifest else None, args.skip_kicad)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return int(manifest["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
