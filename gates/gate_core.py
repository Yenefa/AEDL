"""Pure, fail-closed helpers for the project-027 M2 evidence gates."""

from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Set, Tuple
import zipfile


_REF_RE = re.compile(r"^[A-Z]+[0-9]+$")
_LCSC_RE = re.compile(r"^C[0-9]+$")
BOARD_REVIEW_IDS = (
    "USB_EDGE",
    "ESP_ANTENNA",
    "GROUND_RETURN",
    "DECOUPLING",
    "USB_ROUTING",
    "SHT30_THERMAL",
    "PROTECTION",
    "ASSEMBLY",
)


def _read_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _validate_kicad_metadata(data: Dict[str, Any], report_kind: str, path: Path) -> None:
    expected_schema = f"https://schemas.kicad.org/{report_kind}.v1.json"
    if data.get("$schema") != expected_schema:
        raise ValueError(f"{report_kind.upper()} report has invalid schema metadata: {path}")
    for field in ("kicad_version", "source"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"{report_kind.upper()} report has no {field}: {path}")


def count_erc_errors(path: Path) -> int:
    """Count KiCad ERC violations whose severity is exactly ``error``."""
    data = _read_json(path)
    _validate_kicad_metadata(data, "erc", path)
    sheets = data.get("sheets")
    if not isinstance(sheets, list) or not sheets:
        raise ValueError(f"ERC report has no non-empty sheets list: {path}")

    count = 0
    for index, sheet in enumerate(sheets):
        if not isinstance(sheet, dict) or not isinstance(sheet.get("violations"), list):
            raise ValueError(f"ERC sheet {index} has no violations list: {path}")
        if not isinstance(sheet.get("path"), str) or not sheet["path"]:
            raise ValueError(f"ERC sheet {index} has no path: {path}")
        for violation in sheet["violations"]:
            if not isinstance(violation, dict):
                raise ValueError(f"ERC sheet {index} contains a malformed violation: {path}")
            severity = violation.get("severity")
            if severity not in ("error", "warning", "exclusion"):
                raise ValueError(
                    f"ERC sheet {index} has missing or unknown severity {severity!r}: {path}"
                )
            if severity == "error":
                count += 1
    return count


def count_drc_findings(path: Path) -> Tuple[int, int]:
    """Return ``(violations, unconnected_items)`` from a KiCad DRC report."""
    data = _read_json(path)
    _validate_kicad_metadata(data, "drc", path)
    violations = data.get("violations")
    unconnected = data.get("unconnected_items")
    if not isinstance(violations, list) or not isinstance(unconnected, list):
        raise ValueError(f"DRC report lacks finding arrays: {path}")
    return len(violations), len(unconnected)


def erc_gate_verdict(path: Path) -> Dict[str, Any]:
    """Translate an ERC report into an explicit process verdict."""
    error_count = count_erc_errors(path)
    passed = error_count == 0
    return {
        "status": "pass" if passed else "fail",
        "exit_code": 0 if passed else 1,
        "error_count": error_count,
    }


def drc_gate_verdict(path: Path) -> Dict[str, Any]:
    """Translate a DRC report into an explicit process verdict."""
    violation_count, unconnected_count = count_drc_findings(path)
    passed = violation_count == 0 and unconnected_count == 0
    return {
        "status": "pass" if passed else "fail",
        "exit_code": 0 if passed else 1,
        "violation_count": violation_count,
        "unconnected_count": unconnected_count,
    }


def validate_bom(path: Path) -> List[str]:
    """Validate the canonical grouped BOM without consulting network state."""
    data = _read_json(path)
    errors: List[str] = []
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        errors.append("BOM _meta must be an object")
    else:
        frozen_at = meta.get("frozen_at")
        if not isinstance(frozen_at, str):
            errors.append("frozen_at must be an ISO-8601 UTC string")
        else:
            try:
                parsed = datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
                if not frozen_at.endswith("Z") or parsed.utcoffset() is None:
                    raise ValueError
            except ValueError:
                errors.append(f"malformed frozen_at: {frozen_at!r}")

    items = data.get("items")
    if not isinstance(items, list) or not items:
        return errors + ["BOM items must be a non-empty list"]

    seen: Set[str] = set()
    for index, item in enumerate(items):
        label = f"items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue

        raw_ref = item.get("ref")
        refs = [] if not isinstance(raw_ref, str) else [part.strip() for part in raw_ref.split(",")]
        if not refs or any(not ref for ref in refs):
            errors.append(f"{label} has missing refs")
        for ref in refs:
            if not _REF_RE.fullmatch(ref):
                errors.append(f"{label} has malformed ref {ref!r}")
            if ref in seen:
                errors.append(f"duplicate ref {ref}")
            seen.add(ref)

        lcsc = item.get("lcsc")
        if lcsc == "TBD":
            errors.append(f"{raw_ref or label} LCSC code is TBD")
        elif not isinstance(lcsc, str) or not _LCSC_RE.fullmatch(lcsc):
            errors.append(f"{raw_ref or label} has missing or malformed LCSC code")

        stock = item.get("stock")
        if not isinstance(stock, int) or isinstance(stock, bool) or stock <= 0:
            errors.append(f"{raw_ref or label} has non-positive or missing freeze stock")

        footprint = item.get("footprint")
        if not isinstance(footprint, str) or not footprint.strip():
            errors.append(f"{raw_ref or label} has missing footprint")

        if not isinstance(item.get("value"), str) or not item["value"].strip():
            errors.append(f"{raw_ref or label} has missing value")
        if not isinstance(item.get("jlc_lib"), str) or not item["jlc_lib"].strip():
            errors.append(f"{raw_ref or label} has missing JLC library")

        for key, value in item.items():
            if isinstance(value, str) and "TBD" in value.upper() and not (key == "lcsc" and value == "TBD"):
                errors.append(f"{raw_ref or label} field {key} contains TBD")

    return errors


def read_bom_refs(path: Path) -> Set[str]:
    """Expand and return the unique physical reference set from a grouped BOM."""
    data = _read_json(path)
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError(f"BOM items must be a non-empty list: {path}")

    refs: Set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("ref"), str):
            raise ValueError(f"BOM item {index} has no ref string: {path}")
        for ref in (part.strip() for part in item["ref"].split(",")):
            if not _REF_RE.fullmatch(ref):
                raise ValueError(f"BOM item {index} has malformed ref {ref!r}: {path}")
            if ref in refs:
                raise ValueError(f"BOM contains duplicate ref {ref}: {path}")
            refs.add(ref)
    return refs


def read_pos_refs(path: Path) -> Set[str]:
    """Read references from KiCad whitespace POS or a conventional CSV export."""
    text = Path(path).read_text(encoding="utf-8-sig")
    data_lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not data_lines:
        raise ValueError(f"position file contains no rows: {path}")

    if "," in data_lines[0]:
        reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
        field = next((name for name in ("Designator", "Ref", "Reference") if name in (reader.fieldnames or [])), None)
        if field is None:
            raise ValueError(f"position CSV has no reference column: {path}")
        candidates = [str(row.get(field, "")).strip() for row in reader]
    else:
        candidates = [line.split()[0] for line in data_lines]

    refs: Set[str] = set()
    for ref in candidates:
        if not _REF_RE.fullmatch(ref):
            raise ValueError(f"position file has malformed ref {ref!r}: {path}")
        if ref in refs:
            raise ValueError(f"position file contains duplicate ref {ref}: {path}")
        refs.add(ref)
    if not refs:
        raise ValueError(f"position file contains no references: {path}")
    return refs


def zip_entry_names(path: Path) -> List[str]:
    """Return sorted, safe file entry names from a ZIP archive."""
    with zipfile.ZipFile(str(path), "r") as archive:
        names = [info.filename.replace("\\", "/") for info in archive.infolist() if not info.is_dir()]
    for name in names:
        parts = Path(name).parts
        if name.startswith("/") or ".." in parts:
            raise ValueError(f"unsafe ZIP entry {name!r}: {path}")
    return sorted(names)


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_board_review(path: Path) -> List[str]:
    """Validate board-review structure and require an explicit manufacturing release."""
    data = _read_json(path)
    errors: List[str] = []
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
        errors.append("board review _meta must be an object")

    release = meta.get("manufacturing_release")
    if not isinstance(release, bool):
        errors.append("manufacturing_release must be boolean")
    elif not release:
        errors.append("manufacturing_release is false")

        revocation = meta.get("release_revocation")
        if not isinstance(revocation, dict):
            errors.append("release_revocation must be an object when manufacturing_release is false")
        else:
            incident_id = revocation.get("incident_id")
            if not isinstance(incident_id, str) or not incident_id.strip():
                errors.append("release_revocation has no incident_id")

            revoked_at = revocation.get("revoked_at")
            if not isinstance(revoked_at, str):
                errors.append("release_revocation revoked_at must be an ISO-8601 UTC string")
            else:
                try:
                    parsed = datetime.fromisoformat(revoked_at.replace("Z", "+00:00"))
                    if not revoked_at.endswith("Z") or parsed.utcoffset() is None:
                        raise ValueError
                except ValueError:
                    errors.append(f"malformed release_revocation revoked_at: {revoked_at!r}")

            reason = revocation.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append("release_revocation has no reason")
            if revocation.get("human_resign_required") is not True:
                errors.append("release_revocation must require human re-sign")

            superseded = revocation.get("superseded_signoff")
            if not isinstance(superseded, dict):
                errors.append("release_revocation superseded_signoff must be an object")
            else:
                for field in ("reviewer", "reviewed_at", "auto_evidence", "drc_evidence"):
                    value = superseded.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"release_revocation superseded_signoff has no {field}")

    reviewed_at = meta.get("reviewed_at")
    if reviewed_at is not None:
        if not isinstance(reviewed_at, str):
            errors.append("reviewed_at must be an ISO-8601 UTC string or null")
        else:
            try:
                parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
                if not reviewed_at.endswith("Z") or parsed.utcoffset() is None:
                    raise ValueError
            except ValueError:
                errors.append(f"malformed reviewed_at: {reviewed_at!r}")

    reviewer = meta.get("reviewer")
    if release and (not isinstance(reviewer, str) or not reviewer.strip()):
        errors.append("released board review has no named reviewer")
    if release and reviewed_at is None:
        errors.append("released board review has no reviewed_at timestamp")

    reviews = data.get("reviews")
    if not isinstance(reviews, list):
        reviews = []
        errors.append("board reviews must be a list")

    seen: Set[str] = set()
    statuses: Dict[str, str] = {}
    for index, review in enumerate(reviews):
        label = f"reviews[{index}]"
        if not isinstance(review, dict):
            errors.append(f"{label} must be an object")
            continue
        review_id = review.get("id")
        if not isinstance(review_id, str) or not review_id:
            errors.append(f"{label} has no id")
            continue
        if review_id in seen:
            errors.append(f"duplicate review id {review_id}")
        seen.add(review_id)

        status = review.get("status")
        if status not in ("pass", "fail", "needs_physical"):
            errors.append(f"{review_id} has invalid status {status!r}")
        else:
            statuses[review_id] = status

        if not isinstance(review.get("item"), str) or not review["item"].strip():
            errors.append(f"{review_id} has no item description")
        evidence = review.get("evidence")
        if not ((isinstance(evidence, str) and evidence.strip()) or (isinstance(evidence, list) and evidence)):
            errors.append(f"{review_id} has no evidence")
        if not isinstance(review.get("decision"), str) or not review["decision"].strip():
            errors.append(f"{review_id} has no decision")

    for required_id in BOARD_REVIEW_IDS:
        if required_id not in seen:
            errors.append(f"missing review id {required_id}")
    if release:
        for required_id in BOARD_REVIEW_IDS:
            if statuses.get(required_id) != "pass":
                errors.append(f"released review {required_id} is not pass")
    return errors
