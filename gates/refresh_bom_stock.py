"""Refresh every canonical BOM code from the live JLC assembly catalog.

Exact LCSC code matching, positive assembly stock, model, package, and library
are required.  The canonical BOM is replaced only after the full snapshot
validates, and a hash-bound evidence report is written.
"""

from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Mapping


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SCHEMA = "https://aedl.local/schemas/bom-stock-snapshot.v1.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _write_evidence_atomic(path: Path, evidence: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(dict(evidence), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_stock_evidence(
    *,
    root: Path,
    source_path: Path,
    catalog: Mapping[str, Mapping[str, Any]],
    generated_at: str,
    tool_version: str,
    status: str,
    errors: list,
) -> Dict[str, Any]:
    if status not in ("pass", "fail"):
        raise ValueError(f"unknown stock evidence status {status!r}")
    if status == "pass" and errors:
        raise ValueError("pass stock evidence cannot contain errors")
    if status == "fail" and not errors:
        raise ValueError("fail stock evidence must contain errors")
    return {
        "$schema": EVIDENCE_SCHEMA,
        "schema_version": 1,
        "generated_at": generated_at,
        "status": status,
        "errors": list(errors),
        "tool": tool_version,
        "bom": str(source_path.relative_to(root)).replace("\\", "/"),
        "bom_sha256": sha256_file(source_path),
        "parts": [
            {
                "lcsc": code,
                "mpn": catalog[code]["model"],
                "manufacturer": catalog[code]["brand"],
                "package": catalog[code]["package"],
                "library": catalog[code]["library"],
                "assembly_stock": catalog[code]["stock"],
            }
            for code in sorted(catalog)
        ],
    }


def select_exact_part(
    code: str,
    payload: Mapping[str, Any],
    *,
    require_positive: bool = True,
) -> Dict[str, Any]:
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError(f"catalog response for {code} has no items list")
    exact = [item for item in items if isinstance(item, dict) and item.get("component_code") == code]
    if len(exact) != 1:
        raise ValueError(f"catalog response for {code} must contain exactly one exact-code item")
    item = copy.deepcopy(exact[0])
    stock = item.get("stock")
    if not isinstance(stock, int) or isinstance(stock, bool) or stock < 0:
        raise ValueError(f"catalog exact item {code} has invalid stock")
    if require_positive and stock <= 0:
        raise ValueError(f"catalog exact item {code} has no positive stock")
    for field in ("model", "brand", "package"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise ValueError(f"catalog exact item {code} has no {field}")
    if item.get("library") not in ("base", "expand"):
        raise ValueError(f"catalog exact item {code} has unknown library {item.get('library')!r}")
    return item


def apply_catalog_snapshot(
    source: Mapping[str, Any],
    catalog: Mapping[str, Mapping[str, Any]],
    generated_at: str,
    tool_version: str,
) -> Dict[str, Any]:
    result = copy.deepcopy(dict(source))
    meta = result.get("_meta")
    items = result.get("items")
    if not isinstance(meta, dict) or not isinstance(items, list) or not items:
        raise ValueError("canonical BOM must contain _meta and non-empty items")
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("lcsc"), str):
            raise ValueError("canonical BOM item has no LCSC code")
        code = item["lcsc"]
        part = catalog.get(code)
        if not isinstance(part, Mapping):
            raise ValueError(f"live catalog snapshot is missing {code}")
        item["stock"] = part["stock"]
        item["jlc_lib"] = part["library"]
        item["mpn"] = part["model"]
        item["manufacturer"] = part["brand"]
        item["catalog_package"] = part["package"]
        item["stock_checked_at"] = generated_at
        item["stock_source"] = f"JLC assembly catalog via {tool_version} exact-code query"

    meta.update(
        {
            "frozen_at": generated_at,
            "frozen_at_basis": "live exact-LCSC-code queries for every canonical BOM item",
            "data_source": f"JLC assembly catalog via {tool_version}",
            "source_query": "gates/refresh_bom_stock.py",
            "freshness": "live snapshot; re-run before ordering because inventory is volatile",
        }
    )
    return result


def _run_json(command, cwd: Path) -> Dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"catalog command failed ({completed.returncode}): {completed.stderr[-500:]}"
        )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise ValueError("catalog command returned a non-object JSON value")
    return payload


def refresh(source_path: Path, evidence_path: Path, jlcpcb: str = "jlcpcb") -> Dict[str, Any]:
    source_path = Path(source_path).resolve()
    evidence_path = Path(evidence_path).resolve()
    root = source_path.parents[2]
    source = json.loads(source_path.read_text(encoding="utf-8-sig"))
    codes = sorted({item["lcsc"] for item in source.get("items", []) if isinstance(item, dict) and isinstance(item.get("lcsc"), str)})
    if not codes:
        raise ValueError("canonical BOM contains no queryable LCSC codes")

    version_run = subprocess.run(
        [jlcpcb, "--version"], cwd=str(root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    if version_run.returncode != 0 or not version_run.stdout.strip():
        raise ValueError("jlcpcb version query failed")
    tool_version = f"jlcpcb {version_run.stdout.strip()}"

    def query(code: str):
        payload = _run_json(
            [jlcpcb, "part", "list", "-q", code, "--limit", "20"],
            root,
        )
        return code, select_exact_part(code, payload, require_positive=False)

    with ThreadPoolExecutor(max_workers=4) as executor:
        catalog = dict(executor.map(query, codes))

    generated_at = utc_now()
    unavailable = sorted(code for code, part in catalog.items() if part["stock"] <= 0)
    if unavailable:
        errors = [f"{code} has zero JLC assembly stock" for code in unavailable]
        evidence = build_stock_evidence(
            root=root,
            source_path=source_path,
            catalog=catalog,
            generated_at=generated_at,
            tool_version=tool_version,
            status="fail",
            errors=errors,
        )
        _write_evidence_atomic(evidence_path, evidence)
        raise ValueError("; ".join(errors))

    updated = apply_catalog_snapshot(source, catalog, generated_at, tool_version)
    source_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = source_path.with_name(source_path.name + ".tmp")
    temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if __package__:
        from .gate_core import validate_bom
    else:
        sys.path.insert(0, str(root))
        from gates.gate_core import validate_bom
    errors = validate_bom(temporary)
    if errors:
        temporary.unlink(missing_ok=True)
        raise ValueError("refreshed BOM is invalid: " + "; ".join(errors))
    temporary.replace(source_path)

    evidence = build_stock_evidence(
        root=root,
        source_path=source_path,
        catalog=catalog,
        generated_at=generated_at,
        tool_version=tool_version,
        status="pass",
        errors=[],
    )
    _write_evidence_atomic(evidence_path, evidence)
    return evidence


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "gates/bom/bom_v1.json")
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "notes/m2-evidence-reset/generated/bom_stock_current.json",
    )
    parser.add_argument("--jlcpcb", default="jlcpcb")
    args = parser.parse_args(argv)
    try:
        evidence = refresh(args.source, args.evidence, args.jlcpcb)
    except Exception as exc:
        print(f"[BOM-STOCK] FAIL {type(exc).__name__}: {exc}")
        return 1
    print(
        f"[BOM-STOCK] PASS parts={len(evidence['parts'])} "
        f"sha256={evidence['bom_sha256']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
