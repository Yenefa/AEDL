"""Fail-closed M2 hardware semantic checks derived from independent datasheets.

The checker does not trust ERC, DRC, intent conformance, or board-review prose as
proof of pin meaning.  It compares a separately reviewed contract with four
observed views: design intent, KiCad XML netlist, KiCad PCB pads, and firmware
constants.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
import xml.etree.ElementTree as ET


CONTRACT_SCHEMA = "https://aedl.local/schemas/m2-schematic-contract.v1.json"
OBSERVATIONS_SCHEMA = "https://aedl.local/schemas/schematic-observations.v1.json"
REPORT_SCHEMA = "https://aedl.local/schemas/schematic-semantics-report.v1.json"
REQUIRED_VIEWS = ("intent", "netlist", "pcb", "firmware")
DESIGN_VIEWS = ("intent", "netlist", "pcb")
ALLOWED_SEVERITIES = ("critical", "major")
ALLOWED_RULE_KINDS = ("connectivity",)
_PIN_RE = re.compile(r"^[A-Z#]+[0-9]+\.[A-Za-z0-9]+$")
_REF_RE = re.compile(r"^[A-Z#]+[0-9]+$")


class SemanticSchemaError(ValueError):
    """Raised when a contract or observation violates its strict schema."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json_object(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SemanticSchemaError(f"JSON root must be an object: {path}")
    return data


def _exact_keys(data: Mapping[str, Any], required: Iterable[str], allowed: Iterable[str], label: str) -> None:
    required_set = set(required)
    allowed_set = set(allowed)
    missing = sorted(required_set - set(data))
    unknown = sorted(set(data) - allowed_set)
    if missing:
        raise SemanticSchemaError(f"{label} missing fields: {missing}")
    if unknown:
        raise SemanticSchemaError(f"{label} has unknown fields: {unknown}")


def _validate_pin_state(state: Any, label: str, *, require_no_connect: bool) -> None:
    if not isinstance(state, dict):
        raise SemanticSchemaError(f"{label} must be an object")
    required = {"net", "no_connect"} if require_no_connect else {"net"}
    _exact_keys(state, required, {"net", "no_connect"}, label)
    net = state.get("net")
    if net is not None and (not isinstance(net, str) or not net.strip()):
        raise SemanticSchemaError(f"{label}.net must be a non-empty string or null")
    if "no_connect" in state and not isinstance(state["no_connect"], bool):
        raise SemanticSchemaError(f"{label}.no_connect must be boolean")


def _validate_view(view: Any, name: str) -> None:
    if not isinstance(view, dict):
        raise SemanticSchemaError(f"observations view {name} must be an object")
    if name in DESIGN_VIEWS:
        _exact_keys(view, {"pins", "components"}, {"pins", "components"}, f"observations view {name}")
        pins = view["pins"]
        components = view["components"]
        if not isinstance(pins, dict) or not isinstance(components, dict):
            raise SemanticSchemaError(f"observations view {name} pins/components must be objects")
        for pin, state in pins.items():
            if not isinstance(pin, str) or not _PIN_RE.fullmatch(pin):
                raise SemanticSchemaError(f"observations view {name} has malformed pin {pin!r}")
            _validate_pin_state(state, f"observations {name}.{pin}", require_no_connect=True)
        for ref, component in components.items():
            if not isinstance(ref, str) or not _REF_RE.fullmatch(ref):
                raise SemanticSchemaError(f"observations view {name} has malformed ref {ref!r}")
            if not isinstance(component, dict):
                raise SemanticSchemaError(f"observations {name}.{ref} must be an object")
            _exact_keys(component, {"value"}, {"value"}, f"observations {name}.{ref}")
            if not isinstance(component["value"], str) or not component["value"].strip():
                raise SemanticSchemaError(f"observations {name}.{ref}.value must be non-empty")
    else:
        _exact_keys(view, {"constants"}, {"constants"}, "observations view firmware")
        constants = view["constants"]
        if not isinstance(constants, dict):
            raise SemanticSchemaError("observations firmware.constants must be an object")
        for symbol, value in constants.items():
            if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", symbol):
                raise SemanticSchemaError(f"firmware has malformed constant name {symbol!r}")
            if isinstance(value, bool) or not isinstance(value, int):
                raise SemanticSchemaError(f"firmware constant {symbol} must be an integer")


def validate_observations(observations: Mapping[str, Any]) -> None:
    _exact_keys(
        observations,
        {"$schema", "schema_version", "views"},
        {"$schema", "schema_version", "views"},
        "observations",
    )
    if observations["$schema"] != OBSERVATIONS_SCHEMA or observations["schema_version"] != 1:
        raise SemanticSchemaError("observations schema/version mismatch")
    views = observations["views"]
    if not isinstance(views, dict):
        raise SemanticSchemaError("observations views must be an object")
    _exact_keys(views, REQUIRED_VIEWS, REQUIRED_VIEWS, "observations views")
    for name in REQUIRED_VIEWS:
        _validate_view(views[name], name)


def _validate_expected_check(check: Any, label: str) -> None:
    if not isinstance(check, dict) or not check:
        raise SemanticSchemaError(f"{label} must be a non-empty object")
    _exact_keys(check, set(), {"pins", "components", "constants"}, label)
    if not any(field in check for field in ("pins", "components", "constants")):
        raise SemanticSchemaError(f"{label} contains no checks")

    pins = check.get("pins", {})
    if not isinstance(pins, dict) or ("pins" in check and not pins):
        raise SemanticSchemaError(f"{label}.pins must be a non-empty object")
    for pin, state in pins.items():
        if not isinstance(pin, str) or not _PIN_RE.fullmatch(pin):
            raise SemanticSchemaError(f"{label} has malformed pin {pin!r}")
        _validate_pin_state(state, f"{label}.{pin}", require_no_connect=False)

    components = check.get("components", {})
    if not isinstance(components, dict) or ("components" in check and not components):
        raise SemanticSchemaError(f"{label}.components must be a non-empty object")
    for ref, expected in components.items():
        if not isinstance(ref, str) or not _REF_RE.fullmatch(ref):
            raise SemanticSchemaError(f"{label} has malformed ref {ref!r}")
        if not isinstance(expected, dict):
            raise SemanticSchemaError(f"{label}.{ref} must be an object")
        _exact_keys(expected, {"value"}, {"value"}, f"{label}.{ref}")
        if not isinstance(expected["value"], str) or not expected["value"].strip():
            raise SemanticSchemaError(f"{label}.{ref}.value must be non-empty")

    constants = check.get("constants", {})
    if not isinstance(constants, dict) or ("constants" in check and not constants):
        raise SemanticSchemaError(f"{label}.constants must be a non-empty object")
    for symbol, value in constants.items():
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", symbol):
            raise SemanticSchemaError(f"{label} has malformed constant {symbol!r}")
        if isinstance(value, bool) or not isinstance(value, int):
            raise SemanticSchemaError(f"{label}.{symbol} must be an integer")


def validate_contract(contract: Mapping[str, Any]) -> None:
    _exact_keys(
        contract,
        {"$schema", "schema_version", "board_id", "sources", "rules"},
        {"$schema", "schema_version", "board_id", "sources", "rules"},
        "contract",
    )
    if contract["$schema"] != CONTRACT_SCHEMA or contract["schema_version"] != 1:
        raise SemanticSchemaError("contract schema/version mismatch")
    if not isinstance(contract["board_id"], str) or not contract["board_id"].strip():
        raise SemanticSchemaError("contract board_id must be non-empty")

    sources = contract["sources"]
    if not isinstance(sources, dict) or not sources:
        raise SemanticSchemaError("contract sources must be a non-empty object")
    for source_id, url in sources.items():
        if not isinstance(source_id, str) or not source_id.strip():
            raise SemanticSchemaError("contract source id must be non-empty")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise SemanticSchemaError(f"contract source {source_id} must be an HTTPS URL")

    rules = contract["rules"]
    if not isinstance(rules, list) or not rules:
        raise SemanticSchemaError("contract rules must be a non-empty list")
    seen = set()
    for index, rule in enumerate(rules):
        label = f"contract rules[{index}]"
        if not isinstance(rule, dict):
            raise SemanticSchemaError(f"{label} must be an object")
        _exact_keys(
            rule,
            {"id", "kind", "severity", "title", "source_ids", "checks"},
            {"id", "kind", "severity", "title", "source_ids", "checks"},
            label,
        )
        rule_id = rule["id"]
        if not isinstance(rule_id, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]+", rule_id):
            raise SemanticSchemaError(f"{label} has malformed id {rule_id!r}")
        if rule_id in seen:
            raise SemanticSchemaError(f"duplicate contract rule id {rule_id}")
        seen.add(rule_id)
        if rule["kind"] not in ALLOWED_RULE_KINDS:
            raise SemanticSchemaError(f"{rule_id} has unknown kind {rule['kind']!r}")
        if rule["severity"] not in ALLOWED_SEVERITIES:
            raise SemanticSchemaError(f"{rule_id} has unknown severity {rule['severity']!r}")
        if not isinstance(rule["title"], str) or not rule["title"].strip():
            raise SemanticSchemaError(f"{rule_id} has no title")
        source_ids = rule["source_ids"]
        if not isinstance(source_ids, list) or not source_ids or any(item not in sources for item in source_ids):
            raise SemanticSchemaError(f"{rule_id} has missing or unknown source_ids")
        checks = rule["checks"]
        if not isinstance(checks, dict) or not checks:
            raise SemanticSchemaError(f"{rule_id} checks must be a non-empty object")
        unknown_views = sorted(set(checks) - set(REQUIRED_VIEWS))
        if unknown_views:
            raise SemanticSchemaError(f"{rule_id} has unknown views {unknown_views}")
        for view_name, check in checks.items():
            if view_name == "firmware" and any(field in check for field in ("pins", "components")):
                raise SemanticSchemaError(f"{rule_id} firmware check may only contain constants")
            if view_name != "firmware" and "constants" in check:
                raise SemanticSchemaError(f"{rule_id} {view_name} check may not contain constants")
            _validate_expected_check(check, f"{rule_id}.{view_name}")


def _failure_report(rule_id: str, message: str) -> Dict[str, Any]:
    return {
        "$schema": REPORT_SCHEMA,
        "schema_version": 1,
        "status": "fail",
        "summary": {"passed": 0, "failed": 1, "total": 1},
        "findings": [
            {
                "rule_id": rule_id,
                "severity": "critical",
                "status": "fail",
                "details": [message],
            }
        ],
    }


def evaluate_observations(contract: Mapping[str, Any], observations: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate already collected views; schema problems become failing reports."""
    try:
        validate_contract(contract)
    except (SemanticSchemaError, TypeError, KeyError) as exc:
        return _failure_report("CONTRACT_INVALID", str(exc))
    try:
        validate_observations(observations)
    except (SemanticSchemaError, TypeError, KeyError) as exc:
        return _failure_report("INPUT_INVALID", str(exc))

    findings: List[Dict[str, Any]] = []
    for rule in contract["rules"]:
        details: List[str] = []
        for view_name, check in rule["checks"].items():
            observed_view = observations["views"][view_name]
            for section in ("pins", "components", "constants"):
                for key, expected in check.get(section, {}).items():
                    observed = observed_view.get(section, {}).get(key, "<missing>")
                    if section == "pins" and isinstance(observed, dict):
                        matches = all(observed.get(field, "<missing>") == value for field, value in expected.items())
                    else:
                        matches = observed == expected
                    if not matches:
                        details.append(
                            f"{view_name}.{section}.{key}: expected "
                            f"{json.dumps(expected, ensure_ascii=False, sort_keys=True)}, observed "
                            f"{json.dumps(observed, ensure_ascii=False, sort_keys=True)}"
                        )
        findings.append(
            {
                "rule_id": rule["id"],
                "kind": rule["kind"],
                "severity": rule["severity"],
                "status": "fail" if details else "pass",
                "title": rule["title"],
                "source_ids": rule["source_ids"],
                "details": details,
            }
        )

    failed = sum(item["status"] == "fail" for item in findings)
    return {
        "$schema": REPORT_SCHEMA,
        "schema_version": 1,
        "board_id": contract["board_id"],
        "status": "fail" if failed else "pass",
        "summary": {"passed": len(findings) - failed, "failed": failed, "total": len(findings)},
        "findings": findings,
    }


def _normalise_net(name: str) -> Optional[str]:
    if name.startswith("unconnected-"):
        return None
    return name[1:] if name.startswith("/") else name


def _parse_intent(path: Path) -> Dict[str, Any]:
    data = _read_json_object(path)
    if data.get("protocol_version") != 1:
        raise SemanticSchemaError("intent protocol_version must be 1")
    components = data.get("components")
    nets = data.get("nets")
    if not isinstance(components, dict) or not isinstance(nets, dict):
        raise SemanticSchemaError("intent components/nets must be objects")
    observed_components: Dict[str, Dict[str, str]] = {}
    for ref, component in components.items():
        if not isinstance(component, dict) or not isinstance(component.get("value"), str):
            raise SemanticSchemaError(f"intent component {ref!r} has no value")
        observed_components[ref] = {"value": component["value"]}
    pins: Dict[str, Dict[str, Any]] = {}
    for net_name, members in nets.items():
        if not isinstance(net_name, str) or not net_name or not isinstance(members, list):
            raise SemanticSchemaError("intent contains malformed net")
        for pin in members:
            if not isinstance(pin, str) or not _PIN_RE.fullmatch(pin):
                raise SemanticSchemaError(f"intent net {net_name} has malformed pin {pin!r}")
            if pin in pins:
                raise SemanticSchemaError(f"intent pin {pin} appears in multiple nets")
            pins[pin] = {"net": net_name, "no_connect": False}
    return {"pins": pins, "components": observed_components}


def _parse_netlist(path: Path) -> Dict[str, Any]:
    try:
        root = ET.parse(str(path)).getroot()
    except ET.ParseError as exc:
        raise SemanticSchemaError(f"malformed KiCad XML netlist: {exc}") from exc
    if root.tag != "export":
        raise SemanticSchemaError("KiCad XML netlist root must be export")
    components: Dict[str, Dict[str, str]] = {}
    for component in root.findall("./components/comp"):
        ref = component.get("ref")
        value = component.findtext("value")
        if not ref or not value:
            raise SemanticSchemaError("KiCad XML netlist contains component without ref/value")
        components[ref] = {"value": value}
    if not components:
        raise SemanticSchemaError("KiCad XML netlist contains no components")
    pins: Dict[str, Dict[str, Any]] = {}
    nets = root.findall("./nets/net")
    if not nets:
        raise SemanticSchemaError("KiCad XML netlist contains no nets")
    for net in nets:
        raw_name = net.get("name")
        if raw_name is None:
            raise SemanticSchemaError("KiCad XML netlist contains unnamed net")
        net_name = _normalise_net(raw_name)
        for node in net.findall("node"):
            ref = node.get("ref")
            pin = node.get("pin")
            if not ref or not pin:
                raise SemanticSchemaError("KiCad XML netlist contains malformed node")
            key = f"{ref}.{pin}"
            state = {"net": net_name, "no_connect": "no_connect" in (node.get("pintype") or "")}
            if key in pins and pins[key] != state:
                raise SemanticSchemaError(f"KiCad XML pin {key} appears in conflicting nets")
            pins[key] = state
    return {"pins": pins, "components": components}


def _balanced_block(text: str, start: int) -> Tuple[str, int]:
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index + 1], index + 1
    raise SemanticSchemaError("unterminated KiCad S-expression block")


def _parse_pcb(path: Path) -> Dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8-sig")
    if "(kicad_pcb" not in text:
        raise SemanticSchemaError("PCB is not a KiCad board")
    components: Dict[str, Dict[str, str]] = {}
    pins: Dict[str, Dict[str, Any]] = {}
    for match in re.finditer(r"\(footprint\s+", text):
        block, _ = _balanced_block(text, match.start())
        ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        value_match = re.search(r'\(property\s+"Value"\s+"([^"]*)"', block)
        if not ref_match or not value_match:
            continue
        ref = ref_match.group(1)
        value = value_match.group(1)
        if ref in components:
            raise SemanticSchemaError(f"PCB contains duplicate footprint {ref}")
        components[ref] = {"value": value}
        for pad_match in re.finditer(r'\(pad\s+"([^"]+)"', block):
            pad_block, _ = _balanced_block(block, pad_match.start())
            pin = pad_match.group(1)
            net_match = re.search(r'\(net\s+"([^"]+)"\)', pad_block)
            state = {"net": net_match.group(1) if net_match else None, "no_connect": net_match is None}
            key = f"{ref}.{pin}"
            if key in pins and pins[key] != state:
                raise SemanticSchemaError(f"PCB pad {key} appears with conflicting nets")
            pins[key] = state
    if not components or not pins:
        raise SemanticSchemaError("PCB contains no parsed footprints or pads")
    return {"pins": pins, "components": components}


def _parse_firmware(path: Path) -> Dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8-sig")
    constants: Dict[str, int] = {}
    for match in re.finditer(r"\b([A-Z][A-Z0-9_]*)\s*=\s*(0x[0-9A-Fa-f]+|[0-9]+)\b", text):
        name = match.group(1)
        value = int(match.group(2), 0)
        if name in constants and constants[name] != value:
            raise SemanticSchemaError(f"firmware constant {name} has conflicting values")
        constants[name] = value
    if not constants:
        raise SemanticSchemaError("firmware contains no parseable integer constants")
    return {"constants": constants}


def collect_observations(
    intent_path: Path,
    netlist_path: Path,
    pcb_path: Path,
    firmware_path: Path,
) -> Dict[str, Any]:
    """Collect native source observations without consulting the contract."""
    return {
        "$schema": OBSERVATIONS_SCHEMA,
        "schema_version": 1,
        "views": {
            "intent": _parse_intent(Path(intent_path)),
            "netlist": _parse_netlist(Path(netlist_path)),
            "pcb": _parse_pcb(Path(pcb_path)),
            "firmware": _parse_firmware(Path(firmware_path)),
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_paths(
    contract_path: Path,
    intent_path: Path,
    netlist_path: Path,
    pcb_path: Path,
    firmware_path: Path,
) -> Dict[str, Any]:
    """Collect and evaluate native files; every read/parse problem fails closed."""
    try:
        contract = _read_json_object(Path(contract_path))
    except (OSError, json.JSONDecodeError, SemanticSchemaError) as exc:
        return _failure_report("CONTRACT_INVALID", str(exc))
    try:
        observations = collect_observations(intent_path, netlist_path, pcb_path, firmware_path)
    except (OSError, json.JSONDecodeError, SemanticSchemaError, ET.ParseError) as exc:
        return _failure_report("INPUT_INVALID", str(exc))
    report = evaluate_observations(contract, observations)
    report["inputs"] = {
        "contract": {"path": str(contract_path), "sha256": _sha256(Path(contract_path))},
        "intent": {"path": str(intent_path), "sha256": _sha256(Path(intent_path))},
        "netlist": {"path": str(netlist_path), "sha256": _sha256(Path(netlist_path))},
        "pcb": {"path": str(pcb_path), "sha256": _sha256(Path(pcb_path))},
        "firmware": {"path": str(firmware_path), "sha256": _sha256(Path(firmware_path))},
    }
    return report


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(output)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--intent", required=True, type=Path)
    parser.add_argument("--netlist", required=True, type=Path)
    parser.add_argument("--pcb", required=True, type=Path)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    report = evaluate_paths(args.contract, args.intent, args.netlist, args.pcb, args.firmware)
    report["generated_at"] = _utc_now()
    _write_report(args.output, report)
    print(
        f"[SCHEMATIC-SEMANTICS] {report['status'].upper()} "
        f"{report['summary']['passed']}/{report['summary']['total']} pass -> {args.output}"
    )
    for finding in report["findings"]:
        if finding["status"] == "fail":
            print(f"  FAIL {finding['rule_id']}: {'; '.join(finding['details'])}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
