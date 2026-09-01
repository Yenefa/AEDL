"""Pure, fail-closed helpers for the project-027 M2 evidence gates."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, List, Set, Tuple
import zipfile


_REF_RE = re.compile(r"^[A-Z]+[0-9]+$")
_LCSC_RE = re.compile(r"^C[0-9]+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_JLC_CPL_FIELDS = ("Designator", "Mid X", "Mid Y", "Rotation", "Layer")
_DELIVERY_BOM_FIELDS = (
    "Comment", "Designator", "Footprint", "LCSC Part #", "JLC Lib", "Stock@freeze"
)
_PRODUCTION_LAYERS = (
    "F.Cu", "B.Cu", "F.Paste", "B.Paste", "F.Silkscreen",
    "B.Silkscreen", "F.Mask", "B.Mask", "Edge.Cuts",
)
BOM_STOCK_EVIDENCE_SCHEMA = "https://aedl.local/schemas/bom-stock-snapshot.v1.json"
DELIVERY_MANIFEST_SCHEMA = "https://aedl.local/schemas/m2-delivery-manifest.v1.json"
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

# Board-review algorithm contract (single source of truth).
# tools/board_review.py imports these constants; the gate below binds every
# auto report to the revision derived from them. Changing any role set or
# threshold changes BOARD_REVIEW_ALGORITHM_REVISION, which fail-closes every
# report produced by the previous algorithm version (stale reports can never
# be re-signed as if the current algorithm had produced them).
ANTENNA_MODULE_REF = "U1"                  # ESP32-C3-WROOM-02 module (antenna)
SENSOR_REF = "U2"                          # SHT30 temperature/humidity sensor
EXPECTED_IC_REFS = ("U1", "U2", "U3")      # ICs requiring decoupling caps
HEAT_SOURCE_REFS = ("U3", "J1", "D1")      # SHT30 heat sources: LDO/USB/LED
POLARITY_REFS = ("J1", "U2", "U3", "D1")   # assembly orientation-sensitive parts
POWER_NET_PREFIX = "+"                     # KiCad power-net naming convention
USB_EDGE_MAX_MM = 1.0
ANTENNA_KEEPOUT_MM = 7.5
DECOUPLING_MAX_MM = 8.0
USB_DIFF_MAX_SKEW_MM = 1.0
THERMAL_MIN_DIST_MM = 10.0

BOARD_REVIEW_ALGORITHM_CONTRACT = {
    "review_ids": BOARD_REVIEW_IDS,
    "role_sets": {
        "antenna_module": ANTENNA_MODULE_REF,
        "sensor": SENSOR_REF,
        "expected_ics": EXPECTED_IC_REFS,
        "heat_sources": HEAT_SOURCE_REFS,
        "polarity_parts": POLARITY_REFS,
    },
    "power_net_prefix": POWER_NET_PREFIX,
    "thresholds_mm": {
        "usb_edge_max": USB_EDGE_MAX_MM,
        "antenna_keepout": ANTENNA_KEEPOUT_MM,
        "decoupling_max": DECOUPLING_MAX_MM,
        "usb_diff_max_skew": USB_DIFF_MAX_SKEW_MM,
        "thermal_min_dist": THERMAL_MIN_DIST_MM,
    },
}

def board_review_implementation_sha256() -> str:
    """SHA-256 of the tools/board_review.py source bytes.

    The algorithm revision must bind the ACTUAL judgement implementation, not
    just the role-set/threshold contract: editing review logic (USB off-board
    check, rotated courtyard, antenna orientation, decoupling, assembly)
    without touching a constant would otherwise leave the revision unchanged
    and let a stale report keep passing. Whole-file hashing is deliberately
    simple, deterministic and reproducible - even a comment edit bumps the
    revision (conservative fail-closed), which is preferred over a fragile AST
    summary that might miss a verdict-affecting code path.
    """
    impl_path = Path(__file__).resolve().parents[1] / "tools" / "board_review.py"
    digest = hashlib.sha256()
    with impl_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_board_review_algorithm_revision(
    contract: Any, implementation_sha256: str
) -> str:
    """Deterministic revision = canonical contract + implementation digest.

    Single source of truth for both the generator (tools/board_review.py, which
    writes the report) and the validator (validate_board_review_auto_report).
    Both consume BOARD_REVIEW_ALGORITHM_REVISION below; this function only
    factors the computation so tests can derive a revision from an arbitrary
    implementation digest without duplicating the logic.
    """
    payload = {
        "contract": contract,
        "implementation_sha256": implementation_sha256,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


BOARD_REVIEW_ALGORITHM_REVISION = compute_board_review_algorithm_revision(
    BOARD_REVIEW_ALGORITHM_CONTRACT,
    board_review_implementation_sha256(),
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


def validate_bom_freshness(
    path: Path,
    *,
    now: datetime | None = None,
    max_age_days: int = 7,
) -> List[str]:
    """Fail closed when the canonical BOM stock snapshot is stale or future-dated."""
    if not isinstance(max_age_days, int) or isinstance(max_age_days, bool) or max_age_days <= 0:
        raise ValueError("max_age_days must be a positive integer")

    current = datetime.now(timezone.utc) if now is None else now
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    data = _read_json(path)
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        return ["BOM _meta must be an object for freshness validation"]
    frozen_at = meta.get("frozen_at")
    if not isinstance(frozen_at, str) or not frozen_at.endswith("Z"):
        return ["BOM frozen_at must be an ISO-8601 UTC string for freshness validation"]
    try:
        frozen = datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))
    except ValueError:
        return [f"BOM frozen_at is malformed for freshness validation: {frozen_at!r}"]

    age = current.astimezone(timezone.utc) - frozen.astimezone(timezone.utc)
    if age < -timedelta(minutes=5):
        return [f"BOM stock snapshot is future-dated: frozen_at={frozen_at}"]
    if age > timedelta(days=max_age_days):
        return [
            f"BOM stock snapshot is stale: age={age.total_seconds() / 86400:.2f} days, "
            f"maximum={max_age_days} days"
        ]
    return []


def validate_bom_stock_evidence(bom_path: Path, evidence_path: Path) -> List[str]:
    """Validate the live-catalog report and bind every row to the canonical BOM."""
    bom = _read_json(bom_path)
    evidence = _read_json(evidence_path)
    errors: List[str] = []
    expected_top = {
        "$schema", "schema_version", "generated_at", "status", "errors",
        "tool", "bom", "bom_sha256", "parts",
    }
    missing = sorted(expected_top - set(evidence))
    unknown = sorted(set(evidence) - expected_top)
    if missing:
        errors.append(f"BOM stock evidence missing fields: {missing}")
    if unknown:
        errors.append(f"BOM stock evidence has unknown fields: {unknown}")
    if evidence.get("$schema") != BOM_STOCK_EVIDENCE_SCHEMA or evidence.get("schema_version") != 1:
        errors.append("BOM stock evidence schema/version mismatch")
    if evidence.get("bom") != "gates/bom/bom_v1.json":
        errors.append("BOM stock evidence points to an unexpected BOM path")
    current_hash = sha256_file(bom_path)
    if evidence.get("bom_sha256") != current_hash:
        errors.append("BOM stock evidence hash does not match canonical BOM")

    status = evidence.get("status")
    evidence_errors = evidence.get("errors")
    if status not in ("pass", "fail"):
        errors.append(f"BOM stock evidence has unknown status {status!r}")
    if not isinstance(evidence_errors, list) or any(
        not isinstance(item, str) or not item.strip() for item in (evidence_errors or [])
    ):
        errors.append("BOM stock evidence errors must be a list of non-empty strings")
        evidence_errors = []
    if status == "pass" and evidence_errors:
        errors.append("passing BOM stock evidence contains errors")
    if status == "fail":
        if not evidence_errors:
            errors.append("failed BOM stock evidence has no errors")
        errors.append("BOM stock evidence status is fail: " + "; ".join(evidence_errors))

    generated_at = evidence.get("generated_at")
    frozen_at = bom.get("_meta", {}).get("frozen_at") if isinstance(bom.get("_meta"), dict) else None
    if status == "pass" and generated_at != frozen_at:
        errors.append("BOM stock evidence timestamp does not match canonical BOM frozen_at")
    for field in ("generated_at", "tool"):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            errors.append(f"BOM stock evidence has no {field}")

    items = bom.get("items")
    if not isinstance(items, list) or not items:
        return errors + ["canonical BOM has no items for stock evidence validation"]
    canonical: Dict[str, Dict[str, Any]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("lcsc"), str):
            errors.append(f"canonical BOM item {index} has no LCSC code")
            continue
        code = item["lcsc"]
        expected = {
            "mpn": item.get("mpn"),
            "manufacturer": item.get("manufacturer"),
            "package": item.get("catalog_package"),
            "library": item.get("jlc_lib"),
            "assembly_stock": item.get("stock"),
        }
        if code in canonical and canonical[code] != expected:
            errors.append(f"canonical BOM repeats {code} with conflicting catalog data")
        canonical[code] = expected

    parts = evidence.get("parts")
    if not isinstance(parts, list) or not parts:
        return errors + ["BOM stock evidence parts must be a non-empty list"]
    by_code: Dict[str, Dict[str, Any]] = {}
    expected_part_fields = {
        "lcsc", "mpn", "manufacturer", "package", "library", "assembly_stock"
    }
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            errors.append(f"BOM stock evidence parts[{index}] must be an object")
            continue
        missing_part = sorted(expected_part_fields - set(part))
        unknown_part = sorted(set(part) - expected_part_fields)
        if missing_part:
            errors.append(f"BOM stock evidence parts[{index}] missing fields: {missing_part}")
        if unknown_part:
            errors.append(f"BOM stock evidence parts[{index}] has unknown fields: {unknown_part}")
        code = part.get("lcsc")
        if not isinstance(code, str) or not _LCSC_RE.fullmatch(code):
            errors.append(f"BOM stock evidence parts[{index}] has malformed LCSC code")
            continue
        if code in by_code:
            errors.append(f"BOM stock evidence contains duplicate {code}")
        by_code[code] = part
        stock = part.get("assembly_stock")
        if not isinstance(stock, int) or isinstance(stock, bool) or stock < 0:
            errors.append(f"BOM stock evidence {code} has invalid assembly stock")
        elif status == "pass" and stock <= 0:
            errors.append(f"passing BOM stock evidence {code} has non-positive assembly stock")

    if set(by_code) != set(canonical):
        errors.append(
            "BOM stock evidence code set differs from canonical BOM: "
            f"missing={sorted(set(canonical) - set(by_code))} "
            f"unexpected={sorted(set(by_code) - set(canonical))}"
        )
    for code in sorted(set(by_code) & set(canonical)):
        for field, expected in canonical[code].items():
            if status == "fail" and field == "assembly_stock":
                continue
            if by_code[code].get(field) != expected:
                errors.append(f"BOM stock evidence {code} field {field} differs from canonical BOM")
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


def validate_delivery_bom(canonical_path: Path, delivery_path: Path) -> List[str]:
    """Require every delivery BOM cell to match the expanded canonical BOM."""
    canonical = _read_json(canonical_path)
    items = canonical.get("items")
    if not isinstance(items, list) or not items:
        return ["canonical BOM items must be a non-empty list"]
    expected: Dict[str, Dict[str, str]] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("ref"), str):
            return [f"canonical BOM item {index} has no ref string"]
        for ref in (part.strip() for part in item["ref"].split(",")):
            if not _REF_RE.fullmatch(ref) or ref in expected:
                return [f"canonical BOM has malformed or duplicate ref {ref!r}"]
            expected[ref] = {
                "Comment": str(item.get("value", "")),
                "Designator": ref,
                "Footprint": str(item.get("footprint", "")),
                "LCSC Part #": str(item.get("lcsc", "")),
                "JLC Lib": str(item.get("jlc_lib", "")),
                "Stock@freeze": str(item.get("stock", "")),
            }

    errors: List[str] = []
    actual: Dict[str, Dict[str, str]] = {}
    with Path(delivery_path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != _DELIVERY_BOM_FIELDS:
            return ["delivery BOM header must be exactly: " + ",".join(_DELIVERY_BOM_FIELDS)]
        for row_number, row in enumerate(reader, start=2):
            if None in row:
                errors.append(f"delivery BOM row {row_number} has unexpected extra fields")
                continue
            ref = str(row.get("Designator", "")).strip()
            if not _REF_RE.fullmatch(ref):
                errors.append(f"delivery BOM row {row_number} has malformed designator {ref!r}")
                continue
            if ref in actual:
                errors.append(f"delivery BOM contains duplicate designator {ref}")
            actual[ref] = {field: str(row.get(field, "")) for field in _DELIVERY_BOM_FIELDS}
    if set(actual) != set(expected):
        errors.append(
            "delivery BOM reference set differs from canonical BOM: "
            f"missing={sorted(set(expected) - set(actual))} "
            f"unexpected={sorted(set(actual) - set(expected))}"
        )
    for ref in sorted(set(actual) & set(expected)):
        for field in _DELIVERY_BOM_FIELDS:
            if actual[ref].get(field) != expected[ref][field]:
                errors.append(f"delivery BOM {ref} field {field} differs from canonical BOM")
    return errors


def read_intent_physical_refs(path: Path) -> Set[str]:
    """Return the fail-closed physical component references from canonical intent."""
    data = _read_json(path)
    if data.get("protocol_version") != 1:
        raise ValueError(f"intent protocol_version must be 1: {path}")
    components = data.get("components")
    if not isinstance(components, dict) or not components:
        raise ValueError(f"intent components must be a non-empty object: {path}")
    refs: Set[str] = set()
    for ref, component in components.items():
        if not isinstance(ref, str) or not _REF_RE.fullmatch(ref):
            if isinstance(ref, str) and ref.startswith("#"):
                pass
            else:
                raise ValueError(f"intent has malformed component ref {ref!r}: {path}")
        if not isinstance(component, dict):
            raise ValueError(f"intent component {ref!r} must be an object: {path}")
        virtual = component.get("virtual", False)
        if not isinstance(virtual, bool):
            raise ValueError(f"intent component {ref!r} has non-boolean virtual flag: {path}")
        if virtual:
            continue
        if not _REF_RE.fullmatch(ref):
            raise ValueError(f"physical intent component has malformed ref {ref!r}: {path}")
        refs.add(ref)
    if not refs:
        raise ValueError(f"intent contains no physical component references: {path}")
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


def validate_jlc_cpl(path: Path) -> List[str]:
    """Strictly validate JLC's five-column CPL shape and numeric content."""
    errors: List[str] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return ["JLC CPL is empty"]
        if tuple(header) != _JLC_CPL_FIELDS:
            return ["JLC CPL header must be exactly: " + ",".join(_JLC_CPL_FIELDS)]
        seen: Set[str] = set()
        row_count = 0
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            if len(row) != len(_JLC_CPL_FIELDS):
                errors.append(
                    f"JLC CPL row {row_number} has {len(row)} fields; "
                    f"expected {len(_JLC_CPL_FIELDS)}"
                )
                continue
            ref, pos_x, pos_y, rotation, layer = row
            if not _REF_RE.fullmatch(ref):
                errors.append(f"JLC CPL row {row_number} has malformed designator {ref!r}")
            elif ref in seen:
                errors.append(f"JLC CPL contains duplicate designator {ref}")
            seen.add(ref)
            for field, value in (("Mid X", pos_x), ("Mid Y", pos_y), ("Rotation", rotation)):
                try:
                    number = float(value)
                except ValueError:
                    number = math.nan
                if not math.isfinite(number):
                    errors.append(f"JLC CPL row {row_number} field {field} is not finite")
            if layer not in ("Top", "Bottom"):
                errors.append(f"JLC CPL row {row_number} has invalid Layer {layer!r}")
    if row_count == 0:
        errors.append("JLC CPL contains no placement rows")
    return errors


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


def validate_delivery_manifest(
    root: Path,
    manifest_path: Path,
    expected_gerber_files: Set[str],
) -> List[str]:
    """Bind delivery files and their ZIP payload to the current design sources."""
    root = Path(root).resolve()
    manifest = _read_json(manifest_path)
    errors: List[str] = []
    expected_top = {
        "$schema", "schema_version", "generated_at", "generator", "kicad_cli",
        "kicad_version", "settings", "sources", "artifacts",
    }
    missing = sorted(expected_top - set(manifest))
    unknown = sorted(set(manifest) - expected_top)
    if missing:
        errors.append(f"delivery manifest missing fields: {missing}")
    if unknown:
        errors.append(f"delivery manifest has unknown fields: {unknown}")
    if manifest.get("$schema") != DELIVERY_MANIFEST_SCHEMA or manifest.get("schema_version") != 1:
        errors.append("delivery manifest schema/version mismatch")
    if manifest.get("generator") != "gates/export_delivery.py":
        errors.append("delivery manifest generator mismatch")
    for field in ("generated_at", "kicad_cli", "kicad_version"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            errors.append(f"delivery manifest has no {field}")
    generated_at = manifest.get("generated_at")
    if isinstance(generated_at, str):
        try:
            parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if not generated_at.endswith("Z") or parsed.utcoffset() is None:
                raise ValueError
        except ValueError:
            errors.append(f"delivery manifest generated_at is malformed: {generated_at!r}")

    settings = manifest.get("settings")
    expected_settings = {
        "gerber_layers": list(_PRODUCTION_LAYERS),
        "gerber_x2": True,
        "gerber_netlist_attributes": True,
        "gerber_protel_extensions": True,
        "position_units": "mm",
        "position_sides": "both",
        "bottom_x_negated": False,
        "rotation_correction_applied": False,
        "jlc_preview_orientation_review_required": True,
    }
    if not isinstance(settings, dict):
        errors.append("delivery manifest settings must be an object")
    else:
        if set(settings) != set(expected_settings):
            errors.append("delivery manifest settings field set mismatch")
        for field, expected in expected_settings.items():
            if settings.get(field) != expected:
                errors.append(f"delivery manifest setting {field} mismatch")

    expected_sources = {
        "board": "src/hardware/m2-board/m2_board.kicad_pcb",
        "intent": "src/hardware/m2-board/intent_v1.json",
        "bom": "gates/bom/bom_v1.json",
        "bom_stock_evidence": "notes/m2-evidence-reset/generated/bom_stock_current.json",
    }
    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        errors.append("delivery manifest sources must be an object")
        sources = {}
    if set(sources) != set(expected_sources):
        errors.append("delivery manifest source set mismatch")
    for name, relative in expected_sources.items():
        entry = sources.get(name)
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256"}:
            errors.append(f"delivery manifest source {name} must contain only path and sha256")
            continue
        if entry.get("path") != relative:
            errors.append(f"delivery manifest source {name} path mismatch")
            continue
        source_path = root / Path(relative)
        if not source_path.is_file():
            errors.append(f"delivery manifest source {name} is missing: {source_path}")
            continue
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            errors.append(f"delivery manifest source {name} has malformed hash")
        elif digest != sha256_file(source_path):
            errors.append(f"delivery manifest source {name} hash mismatch")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("delivery manifest artifacts must be an object")
        artifacts = {}
    if set(artifacts) != {"bom", "cpl", "gerber_zip", "gerbers"}:
        errors.append("delivery manifest artifact set mismatch")

    simple_artifacts = {
        "bom": ("delivery/bom.csv", {"path", "sha256", "rows"}),
        "cpl": ("delivery/pos.csv", {"path", "sha256", "rows"}),
        "gerber_zip": (
            "delivery/jlc_gerber_upload.zip",
            {"path", "sha256", "entries"},
        ),
    }
    for name, (relative, fields) in simple_artifacts.items():
        entry = artifacts.get(name)
        if not isinstance(entry, dict) or set(entry) != fields:
            errors.append(f"delivery manifest artifact {name} field set mismatch")
            continue
        if entry.get("path") != relative:
            errors.append(f"delivery manifest artifact {name} path mismatch")
            continue
        artifact_path = root / Path(relative)
        if not artifact_path.is_file():
            errors.append(f"delivery manifest artifact {name} is missing: {artifact_path}")
            continue
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            errors.append(f"delivery manifest artifact {name} has malformed hash")
        elif digest != sha256_file(artifact_path):
            errors.append(f"delivery manifest artifact {name} hash mismatch")
        if name in ("bom", "cpl"):
            rows = entry.get("rows")
            if not isinstance(rows, int) or isinstance(rows, bool) or rows <= 0:
                errors.append(f"delivery manifest artifact {name} has invalid row count")

    gerbers = artifacts.get("gerbers")
    if not isinstance(gerbers, dict):
        errors.append("delivery manifest gerbers must be an object")
        gerbers = {}
    if set(gerbers) != set(expected_gerber_files):
        errors.append("delivery manifest Gerber file set mismatch")
    for name in sorted(set(gerbers) & set(expected_gerber_files)):
        digest = gerbers.get(name)
        file_path = root / "delivery" / "gerbers" / name
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            errors.append(f"delivery manifest Gerber {name} has malformed hash")
        elif not file_path.is_file():
            errors.append(f"delivery Gerber is missing: {file_path}")
        elif digest != sha256_file(file_path):
            errors.append(f"delivery manifest Gerber {name} hash mismatch")

    zip_entry = artifacts.get("gerber_zip")
    archive_path = root / "delivery" / "jlc_gerber_upload.zip"
    if isinstance(zip_entry, dict):
        entries = zip_entry.get("entries")
        if entries != sorted(expected_gerber_files):
            errors.append("delivery manifest ZIP entry list mismatch")
    if archive_path.is_file():
        try:
            actual_entries = zip_entry_names(archive_path)
            if actual_entries != sorted(expected_gerber_files):
                errors.append("delivery ZIP file set differs from required production set")
            with zipfile.ZipFile(str(archive_path), "r") as archive:
                for name in sorted(set(actual_entries) & set(gerbers)):
                    digest = hashlib.sha256(archive.read(name)).hexdigest()
                    if digest != gerbers.get(name):
                        errors.append(f"delivery ZIP entry {name} differs from exported Gerber")
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            errors.append(f"invalid delivery ZIP: {type(exc).__name__}: {exc}")
    return errors


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


def validate_render_evidence(auto_evidence_path: Path, pcb_path: Path) -> List[str]:
    """Bind the M2 visual-inspection renders to the current PCB by content hash.

    Stale renders (images produced from an older PCB) caused false AI
    inspection verdicts, so freshness is judged only by sha256, never mtime:
    the recorded pcb_sha256 must match the current PCB file and each recorded
    PNG hash must match the rendered image on disk.
    """
    auto_evidence_path = Path(auto_evidence_path)
    pcb_path = Path(pcb_path)
    if not auto_evidence_path.is_file():
        return [f"missing board review auto evidence: {auto_evidence_path}"]
    try:
        data = _read_json(auto_evidence_path)
    except (OSError, ValueError) as exc:
        return [f"board review auto evidence is unreadable: {type(exc).__name__}: {exc}"]

    render = data.get("render_evidence")
    if not isinstance(render, dict) or not render:
        return ["board review auto evidence has no render_evidence (rerun tools/board_review.py)"]

    errors: List[str] = []
    recorded_pcb = render.get("pcb_sha256")
    if not isinstance(recorded_pcb, str) or not _SHA256_RE.fullmatch(recorded_pcb):
        errors.append("render_evidence has a malformed pcb_sha256")
    elif not pcb_path.is_file():
        errors.append(f"missing PCB for render evidence validation: {pcb_path}")
    elif recorded_pcb != sha256_file(pcb_path):
        errors.append(
            "render_evidence pcb_sha256 does not match the current PCB "
            "(render images are stale; rerun tools/board_review.py)"
        )

    for key, filename in (
        ("top_png_sha256", "board_top.png"),
        ("bottom_png_sha256", "board_bottom.png"),
    ):
        image_path = auto_evidence_path.parent / filename
        if not image_path.is_file():
            errors.append(f"render evidence image is missing: {image_path}")
            continue
        recorded = render.get(key)
        if not isinstance(recorded, str) or not _SHA256_RE.fullmatch(recorded):
            errors.append(f"render_evidence has a malformed {key}")
        elif recorded != sha256_file(image_path):
            errors.append(f"render_evidence {key} does not match {filename}")
    return errors


def validate_board_review_auto_report(auto_evidence_path: Path) -> List[str]:
    """Strict machine-report checks: exactly the 8 known reviews, all pass, summary honest.

    The manual sign-off and valid render hashes can never paper over a failing
    (or silently trimmed / duplicated / unknown-id) machine report: the
    board_review gate fails on any of these, independent of manufacturing_release.
    """
    auto_evidence_path = Path(auto_evidence_path)
    if not auto_evidence_path.is_file():
        return [f"missing board review auto evidence: {auto_evidence_path}"]
    try:
        data = _read_json(auto_evidence_path)
    except (OSError, ValueError) as exc:
        return [f"board review auto evidence is unreadable: {type(exc).__name__}: {exc}"]

    errors: List[str] = []
    revision = data.get("algorithm_revision")
    if revision != BOARD_REVIEW_ALGORITHM_REVISION:
        errors.append(
            "auto report algorithm revision "
            f"{revision if isinstance(revision, str) else repr(revision)} does not match "
            f"the current board-review algorithm revision {BOARD_REVIEW_ALGORITHM_REVISION!r} "
            "(the report predates the current review algorithm; rerun tools/board_review.py)"
        )
    reviews = data.get("reviews")
    if not isinstance(reviews, list):
        return ["board review auto evidence has no reviews list"]

    seen: Dict[str, str] = {}
    for index, review in enumerate(reviews):
        if not isinstance(review, dict):
            errors.append(f"auto reviews[{index}] must be an object")
            continue
        review_id = review.get("id")
        if not isinstance(review_id, str) or not review_id:
            errors.append(f"auto reviews[{index}] has no id")
            continue
        if review_id in seen:
            errors.append(f"auto report has duplicate review id {review_id}")
            continue
        if review_id not in BOARD_REVIEW_IDS:
            errors.append(f"auto report has unknown review id {review_id!r}")
            continue
        status = review.get("status")
        if status != "pass":
            errors.append(f"auto review {review_id} is not pass (status={status!r})")
        seen[review_id] = status if isinstance(status, str) else "<invalid>"

    for required_id in BOARD_REVIEW_IDS:
        if required_id not in seen:
            errors.append(f"auto report is missing review id {required_id}")

    summary = data.get("summary")
    expected = {rid: "pass" for rid in BOARD_REVIEW_IDS}
    if not isinstance(summary, dict):
        errors.append("auto report summary must be an object")
    elif summary != expected:
        errors.append(
            "auto report summary does not match its reviews "
            f"(summary={summary!r}, reviews say {seen!r})"
        )
    return errors


def validate_board_review_signoff_binding(
    data: Dict[str, Any],
    auto_evidence_path: Path,
    pcb_path: Path,
    schematic_path: Path,
) -> List[str]:
    """A manufacturing release must be pinned to exact evidence versions.

    The manual _meta must carry the sha256 of the exact auto report it signed
    (a path alone can be repointed after the fact) plus the measured hashes of
    the signed inputs (PCB and schematic). Any drift between the signed
    version and the files on disk fails the gate: stale sign-offs must not
    survive a circuit change. Checked only when manufacturing_release is true,
    so the pre-signoff state keeps its honest "release is false" error.
    """
    errors: List[str] = []
    meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
    if meta.get("manufacturing_release") is not True:
        return errors

    declared_auto = meta.get("auto_evidence_sha256")
    if not isinstance(declared_auto, str) or not _SHA256_RE.fullmatch(declared_auto):
        errors.append(
            "released board review _meta.auto_evidence_sha256 is malformed "
            "(the sign-off must pin the exact auto report version, not just a path)"
        )
    elif Path(auto_evidence_path).is_file():
        actual_auto = sha256_file(auto_evidence_path)
        if actual_auto != declared_auto:
            errors.append(
                "released board review signed a different auto report than the one on disk "
                f"(signed {declared_auto[:12]}…, current {actual_auto[:12]}…); re-run "
                "tools/board_review.py and re-sign"
            )

    bindings = meta.get("signoff_inputs_sha256")
    if not isinstance(bindings, dict) or set(bindings) != {"pcb", "schematic"}:
        errors.append(
            "released board review _meta.signoff_inputs_sha256 must be an object with "
            "exactly 'pcb' and 'schematic' sha256 keys"
        )
        return errors
    for name, target in (("pcb", pcb_path), ("schematic", schematic_path)):
        declared = bindings.get(name)
        if not isinstance(declared, str) or not _SHA256_RE.fullmatch(declared):
            errors.append(f"signoff_inputs_sha256.{name} is malformed")
        elif not Path(target).is_file():
            errors.append(f"signoff input is missing: {target}")
        elif sha256_file(target) != declared:
            errors.append(
                f"signoff_inputs_sha256.{name} does not match the current file "
                "(the signed circuit changed; re-run tools/board_review.py and re-sign)"
            )
    return errors
