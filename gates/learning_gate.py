"""Fail-closed validation for project-owned, executable hardware lessons."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set


REGISTRY_SCHEMA = "https://aedl.local/schemas/lessons-registry.v1.json"
FAULT_PROOF_SCHEMA = "https://aedl.local/schemas/semantic-fault-injection-report.v1.json"
LESSON_FIELDS = {
    "id",
    "severity",
    "title",
    "status",
    "root_cause",
    "escaped_controls",
    "failure_evidence",
    "failing_fixtures",
    "regression_tests",
    "fail_closed_controls",
    "fault_injection_proof",
    "optimization",
}


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


def _resolve_artifact(root: Path, reference: str, errors: List[str], label: str) -> Optional[Path]:
    file_part = reference.split("::", 1)[0]
    candidate = Path(file_part)
    if candidate.is_absolute() or ".." in candidate.parts:
        errors.append(f"{label} referenced artifact escapes project root: {reference}")
        return None
    resolved_root = Path(root).resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        errors.append(f"{label} referenced artifact escapes project root: {reference}")
        return None
    if not resolved.is_file():
        errors.append(f"{label} referenced artifact does not exist: {reference}")
        return None
    if "::" in reference:
        symbol = reference.split("::", 1)[1]
        try:
            content = resolved.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            errors.append(f"{label} regression reference is not text: {reference}")
            return resolved
        for token in (part for part in symbol.split("::") if part):
            if token not in content:
                errors.append(f"{label} regression symbol not found: {reference}")
                break
    return resolved


def _string_list(value: Any, label: str, errors: List[str]) -> List[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label} must be a non-empty list")
        return []
    if any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{label} must contain non-empty strings")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{label} contains duplicates")
    return list(value)


def _validate_fault_proof(
    proof: Mapping[str, Any],
    lesson: Mapping[str, Any],
    root: Path,
    errors: List[str],
    label: str,
) -> None:
    if proof.get("$schema") != FAULT_PROOF_SCHEMA or proof.get("schema_version") != 1:
        errors.append(f"{label} fault injection proof schema/version mismatch")
        return
    if proof.get("status") != "pass" or proof.get("baseline_status") != "pass":
        errors.append(f"{label} fault injection proof is not pass")
    summary = proof.get("summary")
    cases = proof.get("cases")
    if not isinstance(summary, dict) or not isinstance(cases, list) or not cases:
        errors.append(f"{label} fault injection proof has no summary/cases")
        return
    if summary.get("total") != len(cases) or summary.get("caught") != len(cases) or summary.get("missed") != 0:
        errors.append(f"{label} fault injection proof summary is inconsistent")

    expected_fixtures = set(lesson.get("failing_fixtures", []))
    cases_by_fixture: Dict[str, Mapping[str, Any]] = {}
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not isinstance(case.get("fixture"), str):
            errors.append(f"{label} fault injection case {index} is malformed")
            continue
        if case["fixture"] in cases_by_fixture:
            errors.append(f"{label} fault injection proof has duplicate fixture {case['fixture']}")
        cases_by_fixture[case["fixture"]] = case
    if set(cases_by_fixture) != expected_fixtures:
        errors.append(f"{label} fault injection proof fixture set does not match registry")

    for fixture in sorted(expected_fixtures):
        case = cases_by_fixture.get(fixture)
        fixture_path = _resolve_artifact(root, fixture, errors, label)
        if case is None or fixture_path is None:
            continue
        if case.get("fixture_sha256") != _sha256(fixture_path):
            errors.append(f"{label} fault injection fixture hash mismatch: {fixture}")
        if case.get("status") != "caught" or case.get("semantic_status") != "fail":
            errors.append(f"{label} fault injection did not catch fixture: {fixture}")
        expected_rule = case.get("expected_rule")
        detected_rules = case.get("detected_rules")
        if not isinstance(expected_rule, str) or not isinstance(detected_rules, list) or expected_rule not in detected_rules:
            errors.append(f"{label} fault injection does not prove expected rule: {fixture}")

    inputs = proof.get("inputs")
    if not isinstance(inputs, dict):
        errors.append(f"{label} fault injection proof has no inputs")
        return
    for input_name in ("contract", "good_observations"):
        item = inputs.get(input_name)
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append(f"{label} fault injection proof has malformed input {input_name}")
            continue
        artifact = _resolve_artifact(root, item["path"], errors, label)
        if artifact is not None and item.get("sha256") != _sha256(artifact):
            errors.append(f"{label} fault injection input hash mismatch: {item['path']}")


def validate_lessons_registry(
    registry_path: Path,
    root: Path,
    *,
    proof_override: Optional[Path] = None,
) -> List[str]:
    """Return all errors. Any missing/unknown/invalid critical evidence fails."""
    errors: List[str] = []
    try:
        registry = _load_object(Path(registry_path))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"lessons registry unreadable: {exc}"]
    allowed_top = {"$schema", "schema_version", "project_id", "lessons"}
    missing_top = sorted(allowed_top - set(registry))
    unknown_top = sorted(set(registry) - allowed_top)
    if missing_top:
        errors.append(f"lessons registry missing fields: {missing_top}")
    if unknown_top:
        errors.append(f"lessons registry has unknown fields: {unknown_top}")
    if registry.get("$schema") != REGISTRY_SCHEMA or registry.get("schema_version") != 1:
        errors.append("lessons registry schema/version mismatch")
    if not isinstance(registry.get("project_id"), str) or not registry.get("project_id", "").strip():
        errors.append("lessons registry project_id must be non-empty")
    lessons = registry.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        errors.append("lessons registry must contain at least one lesson")
        return errors

    seen: Set[str] = set()
    for index, lesson in enumerate(lessons):
        label = f"lessons[{index}]"
        if not isinstance(lesson, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = sorted(LESSON_FIELDS - set(lesson))
        unknown = sorted(set(lesson) - LESSON_FIELDS)
        if missing:
            errors.append(f"{label} missing fields: {missing}")
        if unknown:
            errors.append(f"{label} has unknown fields: {unknown}")
        if missing:
            continue

        lesson_id = lesson["id"]
        if not isinstance(lesson_id, str) or not re.fullmatch(r"PIT-[0-9]{8}-[0-9]{3}", lesson_id):
            errors.append(f"{label} has malformed id {lesson_id!r}")
        elif lesson_id in seen:
            errors.append(f"duplicate lesson id {lesson_id}")
        else:
            seen.add(lesson_id)
        label = str(lesson_id)
        if lesson["severity"] not in ("critical", "major", "minor"):
            errors.append(f"{label} has unknown severity {lesson['severity']!r}")
        if lesson["status"] not in ("active", "resolved", "promoted"):
            errors.append(f"{label} has unknown status {lesson['status']!r}")
        for field in ("title", "root_cause"):
            if not isinstance(lesson[field], str) or not lesson[field].strip():
                errors.append(f"{label} has no {field}")

        escaped = _string_list(lesson["escaped_controls"], f"{label}.escaped_controls", errors)
        failure_evidence = _string_list(lesson["failure_evidence"], f"{label}.failure_evidence", errors)
        fixtures = _string_list(lesson["failing_fixtures"], f"{label}.failing_fixtures", errors)
        regressions = _string_list(lesson["regression_tests"], f"{label}.regression_tests", errors)
        controls = _string_list(lesson["fail_closed_controls"], f"{label}.fail_closed_controls", errors)
        if lesson["severity"] == "critical" and len(escaped) < 2:
            errors.append(f"{label} critical lesson must identify at least two escaped controls")
        for reference in failure_evidence + fixtures + regressions + controls:
            _resolve_artifact(Path(root), reference, errors, label)

        if not isinstance(lesson["fault_injection_proof"], str) or not lesson["fault_injection_proof"].strip():
            errors.append(f"{label} has no fault_injection_proof")
        else:
            proof_path = Path(proof_override) if proof_override is not None else _resolve_artifact(
                Path(root), lesson["fault_injection_proof"], errors, label
            )
            if proof_path is not None:
                try:
                    proof = _load_object(proof_path)
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    errors.append(f"{label} fault injection proof unreadable: {exc}")
                else:
                    _validate_fault_proof(proof, lesson, Path(root), errors, label)

        optimization = lesson["optimization"]
        expected_optimization_fields = {"target", "state", "promotion_criteria"}
        if not isinstance(optimization, dict):
            errors.append(f"{label}.optimization must be an object")
        else:
            if set(optimization) != expected_optimization_fields:
                errors.append(f"{label}.optimization fields must be exactly {sorted(expected_optimization_fields)}")
            if optimization.get("state") not in ("project_validated", "candidate", "promoted"):
                errors.append(f"{label}.optimization has unknown state {optimization.get('state')!r}")
            if not isinstance(optimization.get("target"), str) or not optimization.get("target", "").strip():
                errors.append(f"{label}.optimization has no target")
            _string_list(optimization.get("promotion_criteria"), f"{label}.optimization.promotion_criteria", errors)
    return errors


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    errors = validate_lessons_registry(args.registry, args.root)
    if errors:
        print(f"[LEARNING-GATE] FAIL errors={len(errors)}")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("[LEARNING-GATE] PASS critical lessons are executable and evidenced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
