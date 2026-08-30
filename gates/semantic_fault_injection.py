"""Generate machine-verifiable proof that semantic regressions are detected."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gates.schematic_semantics import evaluate_observations


REPORT_SCHEMA = "https://aedl.local/schemas/semantic-fault-injection-report.v1.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_object(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _display_path(path: Path, root: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return str(resolved)


def inject_fault(observations: Mapping[str, Any], fixture: Mapping[str, Any]) -> Dict[str, Any]:
    required = {"id", "expected_rule", "mutations"}
    if set(fixture) != required:
        raise ValueError(f"fault fixture fields must be exactly {sorted(required)}")
    if not isinstance(fixture["id"], str) or not fixture["id"].strip():
        raise ValueError("fault fixture has no id")
    if not isinstance(fixture["expected_rule"], str) or not fixture["expected_rule"].strip():
        raise ValueError("fault fixture has no expected_rule")
    mutations = fixture["mutations"]
    if not isinstance(mutations, list) or not mutations:
        raise ValueError("fault fixture has no mutations")

    result = copy.deepcopy(observations)
    for index, mutation in enumerate(mutations):
        if not isinstance(mutation, dict):
            raise ValueError(f"mutation {index} must be an object")
        op = mutation.get("op")
        expected_fields = {"op", "path", "value"} if op == "set" else {"op", "path"}
        if set(mutation) != expected_fields or op not in ("set", "delete"):
            raise ValueError(f"mutation {index} has unknown operation or fields")
        path = mutation["path"]
        if not isinstance(path, list) or not path or any(not isinstance(part, str) or not part for part in path):
            raise ValueError(f"mutation {index} has malformed path")
        cursor: Any = result
        for part in path[:-1]:
            if not isinstance(cursor, dict) or part not in cursor:
                raise ValueError(f"mutation {index} path does not exist: {path}")
            cursor = cursor[part]
        leaf = path[-1]
        if not isinstance(cursor, dict) or leaf not in cursor:
            raise ValueError(f"mutation {index} target does not exist: {path}")
        if op == "set":
            cursor[leaf] = mutation["value"]
        else:
            del cursor[leaf]
    return result


def generate_fault_injection_report(
    contract_path: Path,
    good_observations_path: Path,
    fixture_paths: Iterable[Path],
    *,
    root: Path,
) -> Dict[str, Any]:
    contract_path = Path(contract_path)
    good_observations_path = Path(good_observations_path)
    root = Path(root)
    contract = _load_object(contract_path)
    good = _load_object(good_observations_path)
    baseline = evaluate_observations(contract, good)
    cases: List[Dict[str, Any]] = []

    for fixture_path in sorted((Path(path) for path in fixture_paths), key=lambda item: str(item)):
        try:
            fixture = _load_object(fixture_path)
            injected = inject_fault(good, fixture)
            semantic_report = evaluate_observations(contract, injected)
            detected_rules = sorted(
                item["rule_id"] for item in semantic_report["findings"] if item["status"] == "fail"
            )
            caught = semantic_report["status"] == "fail" and fixture["expected_rule"] in detected_rules
            cases.append(
                {
                    "id": fixture["id"],
                    "fixture": _display_path(fixture_path, root),
                    "fixture_sha256": _sha256(fixture_path),
                    "expected_rule": fixture["expected_rule"],
                    "semantic_status": semantic_report["status"],
                    "detected_rules": detected_rules,
                    "status": "caught" if caught else "missed",
                }
            )
        except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            cases.append(
                {
                    "id": fixture_path.stem,
                    "fixture": _display_path(fixture_path, root),
                    "fixture_sha256": _sha256(fixture_path) if fixture_path.exists() else None,
                    "expected_rule": None,
                    "semantic_status": "invalid",
                    "detected_rules": [],
                    "status": "missed",
                    "error": str(exc),
                }
            )

    caught = sum(case["status"] == "caught" for case in cases)
    missed = len(cases) - caught
    status = "pass" if baseline["status"] == "pass" and cases and missed == 0 else "fail"
    return {
        "$schema": REPORT_SCHEMA,
        "schema_version": 1,
        "generated_at": _utc_now(),
        "status": status,
        "baseline_status": baseline["status"],
        "inputs": {
            "contract": {
                "path": _display_path(contract_path, root),
                "sha256": _sha256(contract_path),
            },
            "good_observations": {
                "path": _display_path(good_observations_path, root),
                "sha256": _sha256(good_observations_path),
            },
        },
        "summary": {"caught": caught, "missed": missed, "total": len(cases)},
        "cases": cases,
    }


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--good-observations", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    fixtures = sorted(args.fixture_dir.glob("fault_*.json"))
    report = generate_fault_injection_report(
        args.contract,
        args.good_observations,
        fixtures,
        root=args.root,
    )
    _write_report(args.output, report)
    print(
        f"[SEMANTIC-FAULT-INJECTION] {report['status'].upper()} "
        f"caught={report['summary']['caught']} missed={report['summary']['missed']} "
        f"total={report['summary']['total']} -> {args.output}"
    )
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
