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
        read_intent_physical_refs,
        read_pos_refs,
        sha256_file,
        validate_board_review,
        validate_bom,
        validate_bom_freshness,
        validate_bom_stock_evidence,
        validate_delivery_manifest,
        validate_delivery_bom,
        validate_jlc_cpl,
        validate_render_evidence,
        zip_entry_names,
    )
    from .export_delivery import EXPECTED_GERBER_FILES, validate_gerber_set
    from .learning_gate import validate_lessons_registry
    from .make_jlc_cpl import generate_jlc_cpl
    from .schematic_semantics import REPORT_SCHEMA as SEMANTIC_REPORT_SCHEMA, evaluate_paths
    from .semantic_fault_injection import REPORT_SCHEMA as FAULT_REPORT_SCHEMA, generate_fault_injection_report
    from .datasheet_contract import validate_datasheet_bundle
except ImportError:  # direct ``py gates/run_gates.py`` execution
    from gate_core import (  # type: ignore
        count_drc_findings,
        drc_gate_verdict,
        erc_gate_verdict,
        read_bom_refs,
        read_intent_physical_refs,
        read_pos_refs,
        sha256_file,
        validate_board_review,
        validate_bom,
        validate_bom_freshness,
        validate_bom_stock_evidence,
        validate_delivery_manifest,
        validate_delivery_bom,
        validate_jlc_cpl,
        validate_render_evidence,
        zip_entry_names,
    )
    from export_delivery import EXPECTED_GERBER_FILES, validate_gerber_set  # type: ignore
    from learning_gate import validate_lessons_registry  # type: ignore
    from make_jlc_cpl import generate_jlc_cpl  # type: ignore
    from schematic_semantics import REPORT_SCHEMA as SEMANTIC_REPORT_SCHEMA, evaluate_paths  # type: ignore
    from semantic_fault_injection import REPORT_SCHEMA as FAULT_REPORT_SCHEMA, generate_fault_injection_report  # type: ignore
    from datasheet_contract import validate_datasheet_bundle  # type: ignore


REQUIRED_ZIP_ENTRIES = set(EXPECTED_GERBER_FILES)
OPS_EVIDENCE_SCHEMA = "https://aedl.local/schemas/m2-ops-validation.v1.json"
LEARNING_REPORT_SCHEMA = "https://aedl.local/schemas/learning-gate-report.v1.json"


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
    stock_evidence = root / "notes" / "m2-evidence-reset" / "generated" / "bom_stock_current.json"
    errors = validate_bom(path) + validate_bom_freshness(path)
    details: Dict[str, Any] = {
        "path": str(path),
        "stock_evidence": str(stock_evidence),
    }
    if not stock_evidence.is_file():
        errors.append(f"missing current BOM stock evidence: {stock_evidence}")
    else:
        errors.extend(validate_bom_stock_evidence(path, stock_evidence))
        with stock_evidence.open("r", encoding="utf-8-sig") as handle:
            evidence = json.load(handle)
        stocks = [
            (part.get("assembly_stock"), part.get("lcsc"))
            for part in evidence.get("parts", [])
            if isinstance(part, dict)
            and isinstance(part.get("assembly_stock"), int)
            and not isinstance(part.get("assembly_stock"), bool)
        ]
        if stocks:
            minimum_stock, minimum_code = min(stocks)
            details["minimum_assembly_stock"] = minimum_stock
            details["minimum_stock_lcsc"] = minimum_code
    details["error_count"] = len(errors)
    return _gate("bom", "pass" if not errors else "fail", details, errors)


def _evaluate_delivery(root: Path, fresh_cpl: Optional[Path] = None) -> Dict[str, Any]:
    bom = root / "gates" / "bom" / "bom_v1.json"
    intent = root / "src" / "hardware" / "m2-board" / "intent_v1.json"
    pos = root / "delivery" / "pos.csv"
    csv_path = root / "delivery" / "bom.csv"
    archive = root / "delivery" / "jlc_gerber_upload.zip"
    manifest = root / "delivery" / "manifest_v1.json"
    gerber_dir = root / "delivery" / "gerbers"
    errors: List[str] = []
    details: Dict[str, Any] = {
        "paths": [str(intent), str(bom), str(pos), str(csv_path), str(archive), str(manifest)],
    }
    for path in (intent, bom, pos, csv_path, archive, manifest):
        if not path.is_file():
            errors.append(f"missing delivery artifact: {path}")

    if all(path.is_file() for path in (intent, bom, pos, csv_path)):
        bom_refs = read_bom_refs(bom)
        pos_refs = read_pos_refs(pos)
        delivery_bom_refs = read_pos_refs(csv_path)
        intent_refs = read_intent_physical_refs(intent)
        details["intent_ref_count"] = len(intent_refs)
        details["bom_ref_count"] = len(bom_refs)
        details["pos_ref_count"] = len(pos_refs)
        details["delivery_bom_ref_count"] = len(delivery_bom_refs)
        if bom_refs != intent_refs:
            errors.append("canonical BOM and physical intent reference sets differ")
        if pos_refs != intent_refs:
            errors.append("POS and physical intent reference sets differ")
        if delivery_bom_refs != intent_refs:
            errors.append("delivery BOM and physical intent reference sets differ")
        errors.extend(validate_delivery_bom(bom, csv_path))
        errors.extend(validate_jlc_cpl(pos))

    if manifest.is_file():
        errors.extend(validate_delivery_manifest(root, manifest, EXPECTED_GERBER_FILES))
    errors.extend(validate_gerber_set(gerber_dir))

    if archive.is_file():
        names = set(zip_entry_names(archive))
        details["zip_entry_count"] = len(names)
        missing = sorted(EXPECTED_GERBER_FILES - names)
        unexpected = sorted(names - EXPECTED_GERBER_FILES)
        if missing:
            errors.append(f"ZIP is missing required entries: {missing}")
        if unexpected:
            errors.append(f"ZIP contains unexpected non-production entries: {unexpected}")

    if fresh_cpl is not None:
        fresh_cpl = Path(fresh_cpl)
        details["fresh_cpl"] = str(fresh_cpl)
        if not fresh_cpl.is_file():
            errors.append(f"fresh current-PCB CPL evidence is missing: {fresh_cpl}")
        else:
            errors.extend(validate_jlc_cpl(fresh_cpl))
            details["fresh_cpl_sha256"] = sha256_file(fresh_cpl)
            if pos.is_file() and pos.read_bytes() != fresh_cpl.read_bytes():
                errors.append("delivery CPL differs from fresh current-PCB millimetre export")
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
            is_power_flag = (
                ref.startswith("#FLG")
                and component.get("lib_id") == "power:PWR_FLAG"
                and component.get("value") == "PWR_FLAG"
            )
            if not is_power_flag:
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
    path = root / "notes" / "m2-evidence-reset" / "generated" / "ops_validate_current.json"
    ops_path = root / "src" / "hardware" / "m2-board" / "ops_gen.json"
    details: Dict[str, Any] = {"path": str(path), "ops_path": str(ops_path)}
    errors: List[str] = []
    if not path.is_file():
        return _gate("ops", "fail", details, [f"missing current M2 operations evidence: {path}"])
    if not ops_path.is_file():
        return _gate("ops", "fail", details, [f"missing current M2 operations file: {ops_path}"])
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    with ops_path.open("r", encoding="utf-8-sig") as handle:
        ops_data = json.load(handle)
    expected_fields = {
        "$schema", "schema_version", "generated_at", "target", "ops_sha256",
        "op_count", "valid", "errors", "generator", "validator",
    }
    if not isinstance(data, dict):
        return _gate("ops", "fail", details, ["ops evidence root must be an object"])
    missing = sorted(expected_fields - set(data))
    unknown = sorted(set(data) - expected_fields)
    if missing:
        errors.append(f"ops evidence missing fields: {missing}")
    if unknown:
        errors.append(f"ops evidence has unknown fields: {unknown}")
    if data.get("$schema") != OPS_EVIDENCE_SCHEMA or data.get("schema_version") != 1:
        errors.append("ops evidence schema/version mismatch")
    if data.get("target") != "src/hardware/m2-board/ops_gen.json":
        errors.append("ops evidence target is not current M2 ops_gen.json")
    if data.get("valid") is not True:
        errors.append("ops evidence valid is not true")
    if data.get("errors") != []:
        errors.append("ops evidence errors is not empty")
    if not isinstance(ops_data, dict) or ops_data.get("protocol_version") != 2:
        errors.append("current M2 ops protocol_version must be 2")
        ops = []
    else:
        ops = ops_data.get("ops")
        if not isinstance(ops, list) or not ops:
            errors.append("current M2 ops must be a non-empty list")
            ops = []
    current_hash = sha256_file(ops_path)
    details.update({"op_count": data.get("op_count"), "ops_sha256": current_hash})
    if data.get("ops_sha256") != current_hash:
        errors.append("ops evidence hash does not match current M2 ops_gen.json")
    if data.get("op_count") != len(ops):
        errors.append("ops evidence op_count does not match current M2 ops_gen.json")
    for field in ("generator", "validator", "generated_at"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f"ops evidence has no {field}")
    return _gate("ops", "pass" if not errors else "fail", details, errors)


def _evaluate_schematic_semantics(root: Path, path: Path) -> Dict[str, Any]:
    details: Dict[str, Any] = {"path": str(path)}
    if not path.is_file():
        return _gate("schematic_semantics", "fail", details, [f"missing semantic report: {path}"])
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    errors: List[str] = []
    required = {"$schema", "schema_version", "board_id", "generated_at", "status", "summary", "findings", "inputs"}
    if not isinstance(data, dict):
        return _gate("schematic_semantics", "fail", details, ["semantic report root must be an object"])
    missing = sorted(required - set(data))
    unknown = sorted(set(data) - required)
    if missing:
        errors.append(f"semantic report missing fields: {missing}")
    if unknown:
        errors.append(f"semantic report has unknown fields: {unknown}")
    if data.get("$schema") != SEMANTIC_REPORT_SCHEMA or data.get("schema_version") != 1:
        errors.append("semantic report schema/version mismatch")
    findings = data.get("findings")
    if not isinstance(findings, list) or not findings:
        errors.append("semantic report findings must be a non-empty list")
        findings = []
    failed = 0
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"semantic finding {index} is malformed")
            continue
        if finding.get("status") not in ("pass", "fail"):
            errors.append(f"semantic finding {index} has unknown status")
        if finding.get("severity") not in ("critical", "major"):
            errors.append(f"semantic finding {index} has unknown severity")
        failed += finding.get("status") == "fail"
    summary = data.get("summary")
    if not isinstance(summary, dict) or summary.get("total") != len(findings) or summary.get("failed") != failed:
        errors.append("semantic report summary is inconsistent")
    if data.get("status") != ("fail" if failed else "pass"):
        errors.append("semantic report status is inconsistent")
    if data.get("status") != "pass":
        errors.append("semantic contract findings are present")

    input_targets = {
        "contract": root / "gates" / "contracts" / "m2_schematic_contract_v1.json",
        "intent": root / "src" / "hardware" / "m2-board" / "intent_v1.json",
        "netlist": root / "notes" / "m2-evidence-reset" / "generated" / "m2_board_current.net.xml",
        "pcb": root / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb",
        "firmware": root / "src" / "firmware" / "include" / "sht30.h",
    }
    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("semantic report inputs must be an object")
    else:
        for name, target in input_targets.items():
            item = inputs.get(name)
            if not target.is_file():
                errors.append(f"semantic input is missing: {target}")
            elif not isinstance(item, dict) or item.get("sha256") != sha256_file(target):
                errors.append(f"semantic input hash mismatch: {name}")
    details.update({"status": data.get("status"), "summary": summary})
    return _gate("schematic_semantics", "pass" if not errors else "fail", details, errors)


def _evaluate_learning(root: Path, path: Path) -> Dict[str, Any]:
    details: Dict[str, Any] = {"path": str(path)}
    if not path.is_file():
        return _gate("learning", "fail", details, [f"missing learning report: {path}"])
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    errors: List[str] = []
    required = {"$schema", "schema_version", "generated_at", "status", "lesson_count", "errors", "inputs"}
    if not isinstance(data, dict):
        return _gate("learning", "fail", details, ["learning report root must be an object"])
    if set(data) != required:
        errors.append("learning report fields do not match strict schema")
    if data.get("$schema") != LEARNING_REPORT_SCHEMA or data.get("schema_version") != 1:
        errors.append("learning report schema/version mismatch")
    if data.get("status") != "pass" or data.get("errors") != []:
        errors.append("learning report is not pass")
    if not isinstance(data.get("lesson_count"), int) or data.get("lesson_count", 0) < 1:
        errors.append("learning report has no lessons")
    input_targets = {
        "registry": root / "gates" / "lessons_registry_v1.json",
        "fault_injection_proof": root / "notes" / "m2-evidence-reset" / "generated" / "semantic_fault_injection_current.json",
    }
    inputs = data.get("inputs")
    if not isinstance(inputs, dict):
        errors.append("learning report inputs must be an object")
    else:
        for name, target in input_targets.items():
            item = inputs.get(name)
            if not target.is_file():
                errors.append(f"learning input is missing: {target}")
            elif not isinstance(item, dict) or item.get("sha256") != sha256_file(target):
                errors.append(f"learning input hash mismatch: {name}")
    details.update({"lesson_count": data.get("lesson_count"), "status": data.get("status")})
    return _gate("learning", "pass" if not errors else "fail", details, errors)


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
    root = Path(path).resolve().parents[1]
    auto_reference = metadata.get("auto_evidence")
    auto_evidence_path: Optional[Path] = None
    if not isinstance(auto_reference, str) or not auto_reference.strip():
        errors.append("board review _meta has no auto_evidence pointer")
    else:
        candidate = Path(auto_reference)
        auto_evidence_path = candidate if candidate.is_absolute() else root / candidate
        errors.extend(validate_render_evidence(
            auto_evidence_path,
            root / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb",
        ))
    details = {
        "path": str(path),
        "review_count": len(reviews),
        "status_counts": status_counts,
        "manufacturing_release": metadata.get("manufacturing_release"),
        "auto_evidence": str(auto_evidence_path) if auto_evidence_path else None,
    }
    return _gate("board_review", "pass" if not errors else "fail", details, errors)


def evaluate_evidence(
    root: Path,
    erc_report: Path,
    drc_report: Path,
    board_review: Path,
    semantic_report: Optional[Path] = None,
    learning_report: Optional[Path] = None,
    fresh_cpl: Optional[Path] = None,
) -> Dict[str, Any]:
    """Evaluate all non-process evidence and return a serializable manifest."""
    root = Path(root).resolve()
    semantic_report = semantic_report or root / "notes" / "m2-evidence-reset" / "generated" / "schematic_semantics_current.json"
    learning_report = learning_report or root / "notes" / "m2-evidence-reset" / "generated" / "learning_gate_current.json"

    def _evaluate_requirements_contract(root: Path) -> Dict[str, Any]:
        """10th gate: NL -> intent provenance (Phase 1 CircuitBot intake).

        Fail-closed wrapper around the deterministic contract validator; the
        LLM advisory runtime (gates/requirements_runtime.py) is intentionally
        NOT called here - the gate only verifies artifacts, never generates.
        """
        from gates.requirements_contract import requirements_contract_gate_verdict

        contract_path = root / "gates" / "requirements" / "requirements_contract_v1.json"
        intent_path = root / "src" / "hardware" / "m2-board" / "intent_v1.json"
        verdict = requirements_contract_gate_verdict(contract_path, intent_path)
        return _gate(
            "requirements_contract",
            verdict["status"],
            {
                "contract_path": str(contract_path),
                "intent_path": str(intent_path),
                "contract_sha256": verdict.get("contract_sha256"),
            },
            verdict["errors"],
        )

    def _evaluate_datasheet_contract(root: Path) -> Dict[str, Any]:
        """11th gate: datasheet truth layer (external world, not self-consistency).

        ERC/DRC PASS can never override a BLOCK here: critical components stay
        blocked until exact MPN binding, frozen datasheet copies, pin->net
        assertions and explicit check evidence all exist.
        """
        manifest_path = root / "src" / "hardware" / "m2-board" / "evidence" / "datasheet_manifest.json"
        contracts_path = root / "src" / "hardware" / "m2-board" / "evidence" / "contracts" / "m2_component_contracts.json"
        bom_path = root / "gates" / "bom" / "bom_v1.json"
        intent_path = root / "src" / "hardware" / "m2-board" / "intent_v1.json"
        errors = validate_datasheet_bundle(manifest_path, contracts_path, bom_path, intent_path, root)
        return _gate(
            "datasheet_contract",
            "pass" if not errors else "fail",
            {
                "manifest": str(manifest_path),
                "contracts": str(contracts_path),
                "block_count": len(errors),
            },
            errors,
        )

    gates = [
        _safe_gate("erc", lambda: _evaluate_erc(Path(erc_report))),
        _safe_gate("drc", lambda: _evaluate_drc(Path(drc_report))),
        _safe_gate("bom", lambda: _evaluate_bom(root)),
        _safe_gate("delivery", lambda: _evaluate_delivery(root, fresh_cpl)),
        _safe_gate("intent", lambda: _evaluate_intent(root)),
        _safe_gate("ops", lambda: _evaluate_ops(root)),
        _safe_gate("schematic_semantics", lambda: _evaluate_schematic_semantics(root, Path(semantic_report))),
        _safe_gate("learning", lambda: _evaluate_learning(root, Path(learning_report))),
        _safe_gate("requirements_contract", lambda: _evaluate_requirements_contract(root)),
        _safe_gate("board_review", lambda: _evaluate_board_review(Path(board_review))),
        _safe_gate("datasheet_contract", lambda: _evaluate_datasheet_contract(root)),
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


def run(
    root: Path,
    kicad_cli: Optional[str] = None,
    manifest_path: Optional[Path] = None,
    skip_kicad: bool = False,
    output_root: Optional[Path] = None,
) -> Dict[str, Any]:
    root = Path(root).resolve()
    # Snapshot repository state before the runner rewrites its own reports.
    git = _git_snapshot(root)
    evidence_dir = root / "notes" / "m2-evidence-reset" / "generated"
    erc_report = evidence_dir / "g2_erc_current.json"
    drc_report = evidence_dir / "g4_drc_current.json"
    netlist_report = evidence_dir / "m2_board_current.net.xml"
    semantic_report = evidence_dir / "schematic_semantics_current.json"
    fault_report = evidence_dir / "semantic_fault_injection_current.json"
    learning_report = evidence_dir / "learning_gate_current.json"
    cpl_report = evidence_dir / "m2_board_cpl_current.csv"
    tools: List[Dict[str, Any]] = []
    tool_errors: List[str] = []
    netlist_fresh = False

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
            netlist_temp = netlist_report.with_name(netlist_report.name + ".tmp")
            netlist_temp.unlink(missing_ok=True)
            netlist_command = [str(cli), "sch", "export", "netlist", "--format", "kicadxml", "--output", str(netlist_temp), str(sch)]
            erc_command = [str(cli), "sch", "erc", "--format", "json", "--severity-all", "--exit-code-violations", "--output", str(erc_report), str(sch)]
            drc_command = [str(cli), "pcb", "drc", "--format", "json", "--severity-all", "--exit-code-violations", "--output", str(drc_report), str(board)]
            raw_pos = evidence_dir / "m2_board_pos_mm_current.csv.tmp"
            raw_pos.unlink(missing_ok=True)
            cpl_report.unlink(missing_ok=True)
            pos_command = [
                str(cli), "pcb", "export", "pos", "--format", "csv",
                "--units", "mm", "--side", "both", "--exclude-dnp",
                "--output", str(raw_pos), str(board),
            ]
            netlist_run = {"name": "kicad_netlist", **_run_tool(netlist_command, root)}
            tools.append(netlist_run)
            if netlist_run.get("exit_code") == 0 and netlist_temp.is_file():
                netlist_temp.replace(netlist_report)
                netlist_fresh = True
            tools.append({"name": "kicad_erc", **_run_tool(erc_command, root)})
            tools.append({"name": "kicad_drc", **_run_tool(drc_command, root)})
            pos_run = {"name": "kicad_pos_mm", **_run_tool(pos_command, root)}
            tools.append(pos_run)
            if pos_run.get("exit_code") == 0 and raw_pos.is_file():
                try:
                    generate_jlc_cpl(raw_pos, cpl_report, units="mm")
                except Exception as exc:
                    tool_errors.append(
                        f"fresh current-PCB CPL conversion failed: {type(exc).__name__}: {exc}"
                    )
                finally:
                    raw_pos.unlink(missing_ok=True)
            else:
                tool_errors.append("fresh current-PCB millimetre position export failed")

    generated_at = _utc_now()
    if netlist_fresh:
        semantic_data = evaluate_paths(
            root / "gates" / "contracts" / "m2_schematic_contract_v1.json",
            root / "src" / "hardware" / "m2-board" / "intent_v1.json",
            netlist_report,
            root / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb",
            root / "src" / "firmware" / "include" / "sht30.h",
        )
        semantic_data["generated_at"] = generated_at
    else:
        semantic_data = {
            "$schema": SEMANTIC_REPORT_SCHEMA,
            "schema_version": 1,
            "board_id": "project-027-m2-esp32c3-sht30",
            "generated_at": generated_at,
            "status": "fail",
            "summary": {"passed": 0, "failed": 1, "total": 1},
            "findings": [{
                "rule_id": "INPUT_INVALID",
                "severity": "critical",
                "status": "fail",
                "details": ["fresh KiCad XML netlist export did not complete in this run"],
            }],
            "inputs": {},
        }
    _write_json_atomic(semantic_report, semantic_data)

    try:
        fault_data = generate_fault_injection_report(
            root / "gates" / "contracts" / "m2_schematic_contract_v1.json",
            root / "tests" / "fixtures" / "schematic_semantics" / "good_observations.json",
            sorted((root / "tests" / "fixtures" / "schematic_semantics").glob("fault_*.json")),
            root=root,
        )
    except Exception as exc:
        fault_data = {
            "$schema": FAULT_REPORT_SCHEMA,
            "schema_version": 1,
            "generated_at": generated_at,
            "status": "fail",
            "baseline_status": "invalid",
            "inputs": {},
            "summary": {"caught": 0, "missed": 1, "total": 1},
            "cases": [{"status": "missed", "error": f"{type(exc).__name__}: {exc}"}],
        }
    _write_json_atomic(fault_report, fault_data)

    registry = root / "gates" / "lessons_registry_v1.json"
    learning_errors = validate_lessons_registry(registry, root)
    try:
        lesson_data = json.loads(registry.read_text(encoding="utf-8-sig"))
        lesson_count = len(lesson_data.get("lessons", [])) if isinstance(lesson_data, dict) else 0
    except Exception:
        lesson_count = 0
    learning_inputs = {}
    for name, path in {"registry": registry, "fault_injection_proof": fault_report}.items():
        learning_inputs[name] = {
            "path": str(path),
            "sha256": sha256_file(path) if path.is_file() else None,
        }
    learning_data = {
        "$schema": LEARNING_REPORT_SCHEMA,
        "schema_version": 1,
        "generated_at": generated_at,
        "status": "pass" if not learning_errors else "fail",
        "lesson_count": lesson_count,
        "errors": learning_errors,
        "inputs": learning_inputs,
    }
    _write_json_atomic(learning_report, learning_data)

    board_review = root / "gates" / "board_review_v1.json"
    evidence = evaluate_evidence(
        root,
        erc_report,
        drc_report,
        board_review,
        semantic_report,
        learning_report,
        cpl_report if not skip_kicad else None,
    )
    if tool_errors:
        evidence["gates"].append(_gate("kicad_tool", "fail", errors=tool_errors))
        evidence["status"] = "fail"
        evidence["exit_code"] = 1
    run_at = _utc_now()
    for gate in evidence["gates"]:
        gate["evidence_grade"] = "A"
    artifacts = _artifact_hashes(
        {
            "intent": root / "src" / "hardware" / "m2-board" / "intent_v1.json",
            "bom": root / "gates" / "bom" / "bom_v1.json",
            "pos": root / "delivery" / "pos.csv",
            "delivery_bom": root / "delivery" / "bom.csv",
            "gerber_zip": root / "delivery" / "jlc_gerber_upload.zip",
            "board_review": board_review,
            "ops_evidence": evidence_dir / "ops_validate_current.json",
            "semantic_netlist": netlist_report,
            "cpl_current": cpl_report,
            "semantic_report": semantic_report,
            "fault_injection_report": fault_report,
            "learning_report": learning_report,
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
        "reports": {
            "erc": str(erc_report),
            "drc": str(drc_report),
            "semantic": str(semantic_report),
            "learning": str(learning_report),
            "fault_injection": str(fault_report),
            "netlist": str(netlist_report),
            "cpl": str(cpl_report),
        },
        "artifacts": artifacts,
        "gates": evidence["gates"],
    }
    if manifest_path:
        target = Path(manifest_path)
    elif output_root:
        target = Path(output_root)
        if not target.is_absolute():
            target = root / target
        target = target / "run_manifest.json"
    else:
        target = root / "notes" / "m2-evidence-reset" / "run_manifest.json"
    _write_json_atomic(target, manifest)
    return manifest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    parser.add_argument("--scope", choices=("m2",), default="m2")
    parser.add_argument("--kicad-cli", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--skip-kicad", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    manifest = run(
        root,
        args.kicad_cli,
        Path(args.manifest) if args.manifest else None,
        args.skip_kicad,
        Path(args.output_root) if args.output_root else None,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return int(manifest["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
