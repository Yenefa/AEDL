"""Datasheet truth-layer gate: bind critical components to external datasheets.

Consistency gates (ERC/DRC/intent/ops/semantics) only prove that generated
artifacts agree with *each other*.  This gate proves agreement with the
physical world: every critical component must be bound to an exact
Manufacturer+MPN in the canonical BOM (DS0), have a locally frozen datasheet
copy with a matching sha256 (DS1), satisfy machine-checkable pin->net
assertions from the component contracts (DS2), carry a human-signed review
record for BLOCK_UNTIL_REVIEWED contracts (DS3) and a human-signed
check_evidence record for every remaining required check (DS4-DS6).

check_evidence state machine (missing is the implicit start):

    missing -> evidence_found -> machine_prechecked -> awaiting_engineer
            -> verified | rejected

``status`` and ``decision`` are separate on purpose: ``verified`` means
"the datasheet fact is confirmed", ``decision`` means "the design meets it"
(pass | fail | blocked).  A check only clears when ``status == "verified"``
AND ``decision == "pass"`` AND ``signed_by == "human"``.  The machine may
collect evidence, locate pages and prefill candidate values
(``machine_prechecked``), but it must never sign: anything short of a human
signature fails closed, and an ERC/DRC PASS can never override a BLOCK here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .gate_core import _REF_RE, sha256_file
except ImportError:  # direct script execution
    from gate_core import _REF_RE, sha256_file  # type: ignore

MANIFEST_SCHEMA = "https://aedl.local/schemas/m2-datasheet-manifest.v1.json"


def _read_object(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _expand_bom_refs(bom: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    by_ref: Dict[str, Dict[str, Any]] = {}
    items = bom.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("canonical BOM items must be a non-empty list")
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("ref"), str):
            raise ValueError(f"canonical BOM item {index} has no ref string")
        for ref in (part.strip() for part in item["ref"].split(",")):
            if not _REF_RE.fullmatch(ref) or ref in by_ref:
                raise ValueError(f"canonical BOM has malformed or duplicate ref {ref!r}")
            by_ref[ref] = item
    return by_ref


def _pin_net_map(intent: Dict[str, Any]) -> Dict[str, str]:
    nets = intent.get("nets")
    if not isinstance(nets, dict) or not nets:
        raise ValueError("intent nets must be a non-empty object")
    mapping: Dict[str, str] = {}
    for net, members in nets.items():
        if not isinstance(members, list):
            raise ValueError(f"intent net {net!r} must be a list")
        for member in members:
            if isinstance(member, str) and member:
                mapping[member] = net
    return mapping


def validate_datasheet_bundle(
    manifest_path: Path,
    contracts_path: Path,
    bom_path: Path,
    intent_path: Path,
    root: Path,
) -> List[str]:
    """Return the list of fail-closed violations (empty list = gate PASS)."""
    manifest_path, contracts_path = Path(manifest_path), Path(contracts_path)
    bom_path, intent_path, root = Path(bom_path), Path(intent_path), Path(root)
    if not manifest_path.is_file():
        return [f"missing datasheet manifest: {manifest_path}"]
    if not contracts_path.is_file():
        return [f"missing component contracts: {contracts_path}"]

    errors: List[str] = []
    try:
        manifest = _read_object(manifest_path)
        contracts = _read_object(contracts_path)
        bom = _read_object(bom_path)
        intent = _read_object(intent_path)
    except (OSError, ValueError) as exc:
        return [f"datasheet bundle unreadable: {type(exc).__name__}: {exc}"]

    if manifest.get("$schema") != MANIFEST_SCHEMA or manifest.get("schema_version") != 1:
        errors.append("datasheet manifest schema/version mismatch")
    components = manifest.get("components")
    if not isinstance(components, list) or not components:
        errors.append("datasheet manifest components must be a non-empty list")
        components = []

    try:
        bom_by_ref = _expand_bom_refs(bom)
        pin_nets = _pin_net_map(intent)
    except ValueError as exc:
        return errors + [f"datasheet gate inputs invalid: {exc}"]

    assertion_contracts: Dict[str, List[Dict[str, Any]]] = {}
    review_contracts: Dict[str, List[Dict[str, Any]]] = {}
    for contract in contracts.get("contracts") or []:
        if not isinstance(contract, dict):
            errors.append("component contracts contain a malformed entry")
            continue
        ref = contract.get("refdes")
        if not isinstance(ref, str) or not ref:
            errors.append("component contract has no refdes")
            continue
        if contract.get("severity") == "BLOCK_UNTIL_REVIEWED":
            review_contracts.setdefault(ref, []).append(contract)
        elif isinstance(contract.get("assertions"), list):
            assertion_contracts.setdefault(ref, []).append(contract)

    for component in components:
        if not isinstance(component, dict):
            errors.append("datasheet manifest contains a malformed component")
            continue
        ref = component.get("refdes")
        if not isinstance(ref, str) or not ref:
            errors.append("datasheet manifest component has no refdes")
            continue

        # DS0 MPN_BOUND: manifest identity must match the canonical BOM exactly.
        manufacturer, mpn = component.get("manufacturer"), component.get("mpn")
        if not isinstance(manufacturer, str) or not manufacturer.strip() or not isinstance(mpn, str) or not mpn.strip():
            errors.append(f"DS0 {ref}: manufacturer/MPN not bound in manifest")
            continue
        bom_item = bom_by_ref.get(ref)
        if bom_item is None:
            errors.append(f"DS0 {ref}: missing from canonical BOM")
            continue
        if bom_item.get("mpn") != mpn:
            errors.append(f"DS0 {ref}: manifest MPN {mpn!r} differs from BOM {bom_item.get('mpn')!r}")
        if bom_item.get("manufacturer") != manufacturer:
            errors.append(f"DS0 {ref}: manifest manufacturer differs from BOM {bom_item.get('manufacturer')!r}")
        if isinstance(component.get("lcsc"), str) and bom_item.get("lcsc") != component["lcsc"]:
            errors.append(f"DS0 {ref}: manifest LCSC {component['lcsc']!r} differs from BOM {bom_item.get('lcsc')!r}")

        # DS1 SOURCE_PRESENT: at least one locally frozen document with matching sha256.
        documents = component.get("documents")
        if not isinstance(documents, list):
            documents = []
        local_docs = [d for d in documents if isinstance(d, dict) and d.get("local_file")]
        if not local_docs:
            errors.append(f"DS1 {ref}: no local datasheet/drawing copy frozen (URL-only is not evidence)")
        for doc in local_docs:
            doc_path = Path(doc["local_file"])
            if not doc_path.is_absolute():
                doc_path = root / doc_path
            if not doc_path.is_file():
                errors.append(f"DS1 {ref}: local document missing: {doc_path}")
                continue
            recorded = doc.get("sha256")
            if not isinstance(recorded, str) or recorded != sha256_file(doc_path):
                errors.append(f"DS1 {ref}: sha256 mismatch for {doc_path.name}")

        # DS2 PINOUT_VERIFIED: contract pin->net assertions against the intent.
        for contract in assertion_contracts.get(ref, []):
            for assertion in contract["assertions"]:
                if not isinstance(assertion, dict):
                    errors.append(f"DS2 {ref}: malformed assertion in {contract.get('id')!r}")
                    continue
                pin = f"{ref}.{assertion.get('pin')}"
                expected = assertion.get("net")
                actual = pin_nets.get(pin)
                if expected is None:
                    if actual is not None:
                        errors.append(f"DS2 {ref}: pin {assertion.get('pin')} must be unconnected but is on net {actual!r}")
                elif actual != expected:
                    errors.append(f"DS2 {ref}: pin {assertion.get('pin')} must be on net {expected!r}, found {actual!r}")

        # DS3 ELECTRICAL_VERIFIED: BLOCK_UNTIL_REVIEWED contracts need a
        # human-signed review record with a passing design decision.
        check_evidence = component.get("check_evidence")
        if not isinstance(check_evidence, dict):
            check_evidence = {}
        for contract in review_contracts.get(ref, []):
            record = check_evidence.get(contract.get("id"))
            if record is None:
                errors.append(
                    f"DS3 {ref}: contract {contract.get('id')!r} is BLOCK_UNTIL_REVIEWED "
                    "and has no check_evidence record yet"
                )
                continue
            record_error = _check_record_verdict(ref, f"contract {contract.get('id')!r}", record)
            if record_error:
                errors.append(f"DS3 {record_error}")

        # DS4-DS6: every required check needs a human-signed check_evidence record.
        required = component.get("required_checks")
        if not isinstance(required, list) or not required:
            errors.append(f"DS4-6 {ref}: required_checks must be a non-empty list")
            continue
        for check in required:
            record = check_evidence.get(check)
            if record is None:
                errors.append(f"DS4-6 {ref}: required check {check!r} has no check_evidence record")
                continue
            record_error = _check_record_verdict(ref, f"check {check!r}", record)
            if record_error:
                errors.append(f"DS4-6 {record_error}")

    return errors


CHECK_STATUSES = ("evidence_found", "machine_prechecked", "awaiting_engineer", "verified", "rejected", "blocked")


def _check_record_verdict(ref: str, name: str, record: Any) -> Optional[str]:
    """Return the fail-closed violation for one check_evidence record.

    None means the check is cleared: status == "verified" (the datasheet fact
    is confirmed) AND decision == "pass" (the design meets the fact) AND
    signed_by == "human".  ``verified`` and ``decision`` are deliberately
    separate; the machine may prefill candidates but must never sign.
    """
    if not isinstance(record, dict):
        return f"{ref}: {name} has a malformed check_evidence record"
    status = record.get("status")
    if status not in CHECK_STATUSES:
        return f"{ref}: {name} has unknown check_evidence status {status!r}"
    if status == "verified":
        if record.get("signed_by") != "human":
            return f"{ref}: {name} is verified but not signed by a human (agent self-signing is forbidden)"
        decision = record.get("decision")
        if decision == "pass":
            return None
        if decision == "blocked":
            return f"{ref}: DESIGN-BLOCK {name} — human-verified fact, design deliberately blocked"
        if decision == "fail":
            return f"{ref}: DESIGN-FAIL {name} — human-verified fact, design fails the datasheet requirement"
        return f"{ref}: {name} has unknown decision {decision!r}"
    if status == "rejected":
        return f"{ref}: {name} evidence was rejected"
    if status == "blocked":
        if record.get("signed_by") == "human":
            return f"{ref}: DESIGN-BLOCK {name} — human-signed design block (e.g. thermal/reselection hold)"
        return f"{ref}: {name} is recorded as blocked but the block decision needs engineer sign-off"
    return f"{ref}: {name} is unsigned (status={status}); only a human signature clears a check"
