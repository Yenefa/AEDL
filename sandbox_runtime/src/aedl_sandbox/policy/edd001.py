"""Normalization of the three frozen EDD-001 contracts into a policy document.

Owner: Agent M. This module reads ``gates/contracts/edd001_*.json`` read-only,
never writes to them, and never modifies the frozen protocol.

Supersession
------------
``edd001_pin_constraints_v1.json`` declares that CORE_BASE v0.1 supersedes its
pin/reset/boot/decoupling/antenna rules while ``USB_DIFFERENTIAL`` and
``POWER_SOURCE_SEPARATION`` stay active. The superseded set is parsed from the
contract's own ``superseded_by.note`` rather than restated here, so the
contract remains the single source of truth. Honoring it is load-bearing: the
rule id ``EN_RESET_NETWORK`` exists in both contracts with different payloads,
so dropping supersession would surface a duplicate-conflict and fail closed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from .errors import PolicyDocumentError

__all__ = [
    "CONTRACT_FILENAMES",
    "REQUIRED_DOMAIN_CONTRACT_IDS",
    "build_document_from_contracts",
    "build_edd001_document",
    "load_contracts_bound_to_manifest",
    "superseded_rule_ids",
]

CONTRACT_FILENAMES: tuple[str, ...] = (
    "edd001_core_base_contract_v1.json",
    "edd001_pin_constraints_v1.json",
    "edd001_usb_contract_v1.json",
)

# The POWER contract is required by the domain but does not exist yet. It is
# listed so the engine keeps reporting EVIDENCE_REQUIRED_CONTRACT_MISSING
# instead of silently assuming a power budget.
REQUIRED_DOMAIN_CONTRACT_IDS: tuple[str, ...] = (
    "EDD-001.CORE_BASE",
    "EDD-001.PIN_CONSTRAINTS",
    "EDD-001.POWER",
    "EDD-001.USB",
)

DOMAIN_ID = "EDD-001"
BOARD_ID = "project-027-edd001"
SCHEMA_VERSION = 1

CONTRACTS_SUBPATH = Path("gates") / "contracts"
EVIDENCE_SUBPATH = (
    Path("src") / "hardware" / "edd001-board" / "evidence" / "datasheets"
)

# No contract in the bundle declares artifact kinds, so the Execution Sandbox
# vocabulary is declared here and must be reviewed by a human.
ALLOWED_ARTIFACT_KINDS: tuple[str, ...] = (
    "hir",
    "netlist",
    "bom",
    "report",
    "kicad_sch",
    "kicad_pcb",
)
AGENT_FORBIDDEN_ARTIFACT_KINDS: tuple[str, ...] = ("kicad_sch", "kicad_pcb")

# Parameters are hand-transcribed from the contracts; each entry names the
# contract rule it comes from. Nothing here is inferred from model memory.
_PARAMETER_TABLE: tuple[dict[str, Any], ...] = (
    # CORE_BASE power_entry.decoupling.C_CORE_BULK = 22uF
    {
        "parameter_id": "CORE_BULK_CAP_UF",
        "value_type": "number",
        "unit": "uF",
        "allowed_values": [22.0],
        "required_evidence_ids": ["WROOM1_DATASHEET"],
    },
    # CORE_BASE power_entry.decoupling.C_CORE_HF = 100nF
    {
        "parameter_id": "CORE_HF_CAP_UF",
        "value_type": "number",
        "unit": "uF",
        "allowed_values": [0.1],
        "required_evidence_ids": ["WROOM1_DATASHEET"],
    },
    # CORE_BASE reset.en_pullup = 10k
    {
        "parameter_id": "EN_PULLUP_OHM",
        "value_type": "number",
        "unit": "ohm",
        "allowed_values": [10000.0],
        "required_evidence_ids": ["ESP32_S3_SCHEMATIC_CHECKLIST"],
    },
    # CORE_BASE reset.en_cap = 1uF
    {
        "parameter_id": "EN_CAP_UF",
        "value_type": "number",
        "unit": "uF",
        "allowed_values": [1.0],
        "required_evidence_ids": ["ESP32_S3_SCHEMATIC_CHECKLIST"],
    },
    # CORE_BASE boot.gpio0_external_pullup = 10k
    {
        "parameter_id": "BOOT_PULLUP_OHM",
        "value_type": "number",
        "unit": "ohm",
        "allowed_values": [10000.0],
        "required_evidence_ids": ["ESPTOOL_BOOT_MODE"],
    },
    # USB USB_CC_RESISTORS: 5.1k 1% independent pull-down on CC1 and CC2
    {
        "parameter_id": "USB_CC_PULLDOWN_OHM",
        "value_type": "number",
        "unit": "ohm",
        "allowed_values": [5100.0],
        "required_evidence_ids": ["ESPRESSIF_S3_LCD_EV_BOARD"],
    },
    # USB USB_NATIVE_DATA: 22ohm baseline / 33ohm alternative series resistor
    {
        "parameter_id": "USB_SERIES_RESISTOR_OHM",
        "value_type": "number",
        "unit": "ohm",
        "allowed_values": [22.0, 33.0],
        "required_evidence_ids": ["ESPRESSIF_SCHEMATIC_CHECKLIST"],
    },
    # pin_constraints USB_DIFFERENTIAL (still active): 90ohm +/-10%
    {
        "parameter_id": "USB_DIFF_IMPEDANCE_OHM",
        "value_type": "number",
        "unit": "ohm",
        "minimum": 81.0,
        "maximum": 99.0,
        "required_evidence_ids": ["ESPRESSIF_LAYOUT_GUIDE"],
    },
)

_PIN_STATUS_TO_CLASS = {
    "HARD_FORBIDDEN": "hard_forbidden",
    "CORE_RESERVED": "core_reserved",
    "SOFT_RESERVED": "soft_reserved",
}


def _fingerprint(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _rule_id(rule: Any) -> str | None:
    if isinstance(rule, Mapping) and isinstance(rule.get("id"), str) and rule["id"]:
        return rule["id"]
    return None


def superseded_rule_ids(contract: Mapping[str, Any]) -> frozenset[str]:
    """Parse the rule ids this contract declares as superseded.

    Only the parenthetical enumeration that follows ``supersedes`` is read, so
    rules named later in the note as "still active" are not captured.
    """
    declared = {rid for rid in (_rule_id(r) for r in contract.get("rules", ())) if rid}
    note = ""
    superseded_by = contract.get("superseded_by")
    if isinstance(superseded_by, Mapping):
        raw_note = superseded_by.get("note")
        if isinstance(raw_note, str):
            note = raw_note
    if not note:
        return frozenset()

    match = re.search(r"supersedes[^.]*?\(([^)]*)\)", note, re.IGNORECASE)
    if match is None:
        return frozenset()

    superseded: set[str] = set()
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]*\*?", match.group(1)):
        if token.endswith("*"):
            prefix = token[:-1]
            superseded.update(rid for rid in declared if rid.startswith(prefix))
        elif token in declared:
            superseded.add(token)
    return frozenset(superseded)


def _domain_contract_id(filename: str, contract: Mapping[str, Any]) -> str:
    block = contract.get("block")
    if isinstance(block, str) and block:
        return block
    stem = Path(filename).name
    slug = stem
    if slug.startswith("edd001_"):
        slug = slug[len("edd001_") :]
    for suffix in ("_contract_v1.json", "_v1.json", ".json"):
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
            break
    return f"EDD-001.{slug.upper()}"


def _device_evidence(contract: Mapping[str, Any]) -> list[str]:
    sources = contract.get("sources")
    if not isinstance(sources, Mapping):
        return []
    return sorted(key for key in sources if isinstance(key, str) and key.endswith("DATASHEET"))


def _iter_declared_parts(constraint: Mapping[str, Any]) -> Iterator[str]:
    """Yield part numbers declared anywhere inside a rule constraint.

    A part is "declared" when any mapping in the constraint — the constraint
    itself or a nested block such as POWER_SOURCE_SEPARATION's
    ``regulator_3v3`` — carries a non-empty ``mpn`` or ``device`` string.
    Issue #20's frozen-contract adjudication requires the direct SS34
    declaration (USB_VBUS_REVERSE_PROTECTION) and the nested AP63203WU-7
    declaration (POWER_SOURCE_SEPARATION.regulator_3v3.device) to converge
    into one required component set, so collection walks the constraint
    recursively instead of only its top level.
    """
    for key, value in constraint.items():
        if key in ("mpn", "device"):
            if isinstance(value, str) and value:
                yield value
        elif isinstance(value, Mapping):
            yield from _iter_declared_parts(value)


def _collect_components(
    contracts: Sequence[tuple[str, Mapping[str, Any]]]
) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for _filename, contract in contracts:
        device = contract.get("device")
        if isinstance(device, Mapping) and isinstance(device.get("mpn"), str):
            records[device["mpn"]] = {
                "mpn": device["mpn"],
                "role": "mcu_module",
                "required_evidence_ids": _device_evidence(contract),
            }
        rules = contract.get("rules")
        if not isinstance(rules, list):
            continue
        for rule in rules:
            if not isinstance(rule, Mapping):
                continue
            constraint = rule.get("constraint")
            if not isinstance(constraint, Mapping):
                continue
            rule_id = _rule_id(rule)
            if not rule_id:
                continue
            declared = sorted(set(_iter_declared_parts(constraint)))
            if not declared:
                continue
            # This covers kind == "component" (USB_CONNECTOR, USB_ESD), parts
            # declared inside other rule kinds (SS34 under a power rule), and
            # nested devices (POWER_SOURCE_SEPARATION's regulator_3v3).
            source_ids = rule.get("source_ids")
            evidence = (
                sorted(str(item) for item in source_ids if isinstance(item, str))
                if isinstance(source_ids, list)
                else []
            )
            for mpn in declared:
                records[mpn] = {
                    "mpn": mpn,
                    "role": rule_id,
                    "required_evidence_ids": evidence,
                }
    return [records[mpn] for mpn in sorted(records)]


def _collect_pins(
    contracts: Sequence[tuple[str, Mapping[str, Any]]]
) -> dict[str, Any]:
    core_base: Mapping[str, Any] | None = None
    for filename, contract in contracts:
        if "core_base" in filename:
            core_base = contract
            break
    if core_base is None:
        return {
            "allowed": [],
            "core_reserved": [],
            "hard_forbidden": [],
            "soft_reserved": [],
            "rule_sources": {},
        }

    pin_policy = core_base.get("pin_policy")
    if not isinstance(pin_policy, Mapping):
        raise PolicyDocumentError("CORE_BASE contract has no pin_policy")

    pool = pin_policy.get("agent_gpio_pool")
    rule_sources: dict[str, str] = {}
    rules = core_base.get("rules")
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, Mapping):
                continue
            deny = rule.get("deny")
            rule_id = _rule_id(rule)
            if not isinstance(deny, Mapping) or not rule_id:
                continue
            target = _PIN_STATUS_TO_CLASS.get(str(deny.get("status", "")))
            pins_value = deny.get("pins")
            if target and isinstance(pins_value, list):
                for pin in pins_value:
                    if isinstance(pin, str):
                        rule_sources[pin] = rule_id

    return {
        "allowed": sorted(str(p) for p in pool) if isinstance(pool, list) else [],
        "core_reserved": sorted(pin_policy.get("core_reserved", {})),
        "hard_forbidden": sorted(pin_policy.get("hard_forbidden", {})),
        "soft_reserved": sorted(pin_policy.get("soft_reserved", {})),
        "rule_sources": rule_sources,
    }


def _has_verifiable_file(path: Path, seen: frozenset[Path] = frozenset()) -> bool:
    """True only when ``path`` holds at least one readable file with size > 0.

    Directories are searched recursively; symlink cycles are cut by resolving
    each entry and skipping anything already visited. An empty directory, a
    directory holding only empty files, and unreadable entries all count as
    *missing* evidence, never as present evidence.
    """
    try:
        resolved = path.resolve()
        if resolved in seen:
            return False
        if path.is_file():
            return path.stat().st_size > 0
        if not path.is_dir():
            return False
        next_seen = seen | {resolved}
        for child in path.iterdir():
            if _has_verifiable_file(child, next_seen):
                return True
    except OSError:
        return False
    return False


def discover_local_evidence_ids(repo_root: Path) -> list[str]:
    """Evidence ids that have a local, verifiable artifact.

    Only the immediate children of the EDD-001 datasheet directory count, and
    a child counts only when it is non-empty and contains at least one
    verifiable file (size > 0). An empty directory is evidence *missing* and
    must keep the policy BLOCKED, never ALLOW. A ``sources`` entry in a
    contract is a URL and is never local evidence.
    """
    root = Path(repo_root) / EVIDENCE_SUBPATH
    if not root.is_dir():
        return []
    return sorted({path.name for path in root.iterdir() if _has_verifiable_file(path)})


def build_document_from_contracts(
    contracts: Sequence[tuple[str, Mapping[str, Any]]],
    repo_root: Path,
    *,
    honor_supersession: bool = True,
) -> dict[str, Any]:
    """Normalize EDD-001 contracts into a policy document mapping.

    ``honor_supersession=False`` exists only to prove that supersession is
    load-bearing; it makes the bundle fail closed on a duplicate-rule conflict.
    """
    if not contracts:
        raise PolicyDocumentError("no EDD-001 contracts supplied")

    active_rules: list[dict[str, Any]] = []
    available_contract_ids: set[str] = set()

    for filename, contract in contracts:
        if not isinstance(contract, Mapping):
            raise PolicyDocumentError(f"contract {filename} is not a JSON object")
        if contract.get("schema_version") != SCHEMA_VERSION:
            raise PolicyDocumentError(
                f"contract {filename} has unsupported schema_version {contract.get('schema_version')!r}"
            )
        if contract.get("board_id") != BOARD_ID:
            raise PolicyDocumentError(
                f"contract {filename} has board_id {contract.get('board_id')!r}, expected {BOARD_ID!r}"
            )

        available_contract_ids.add(_domain_contract_id(filename, contract))
        superseded = superseded_rule_ids(contract) if honor_supersession else frozenset()

        rules = contract.get("rules")
        if not isinstance(rules, list):
            continue
        for rule in rules:
            rule_id = _rule_id(rule)
            if rule_id is None or rule_id in superseded:
                continue
            active_rules.append(
                {
                    "rule_id": rule_id,
                    "source_contract_id": filename,
                    "kind": str(rule.get("kind", "unknown")),
                    "fingerprint": _fingerprint(rule),
                }
            )

    active_rules.sort(key=lambda item: (item["rule_id"], item["source_contract_id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "domain_id": DOMAIN_ID,
        "board_id": BOARD_ID,
        "allowed_components": _collect_components(contracts),
        "pins": _collect_pins(contracts),
        "parameters": [dict(parameter) for parameter in _PARAMETER_TABLE],
        "file_policy": {
            "candidate_root_only": True,
            "direct_kicad_write": False,
            "allowed_artifact_kinds": list(ALLOWED_ARTIFACT_KINDS),
            "agent_forbidden_artifact_kinds": list(AGENT_FORBIDDEN_ARTIFACT_KINDS),
        },
        "network_policy": {"runtime_access": False},
        "shell_policy": {"arbitrary_shell": False},
        # No deterministic toolchain is registered yet; empty registries make
        # every compile/verify/execute request BLOCKED or DENY rather than ALLOW.
        "tools": [],
        "compilers": [],
        "verifiers": [],
        "prerequisites": {
            "required_contract_ids": list(REQUIRED_DOMAIN_CONTRACT_IDS),
            "required_evidence_ids": [],
            "required_component_resolutions": [],
        },
        "available": {
            "contract_ids": sorted(available_contract_ids),
            "evidence_ids": discover_local_evidence_ids(repo_root),
        },
        "active_rules": active_rules,
    }


def build_edd001_document(repo_root: Path) -> dict[str, Any]:
    """Load the three frozen contracts from ``repo_root`` and normalize them."""
    contracts_dir = Path(repo_root) / CONTRACTS_SUBPATH
    loaded: list[tuple[str, Mapping[str, Any]]] = []
    for filename in CONTRACT_FILENAMES:
        path = contracts_dir / filename
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PolicyDocumentError(f"cannot read required contract {filename}: {exc}") from exc
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PolicyDocumentError(f"contract {filename} is not valid JSON: {exc}") from exc
        if not isinstance(document, Mapping):
            raise PolicyDocumentError(f"contract {filename} must be a JSON object")
        loaded.append((filename, document))
    return build_document_from_contracts(loaded, repo_root)


def load_contracts_bound_to_manifest(
    repo_root: Path, manifest_path: Path
) -> tuple[list[tuple[str, Mapping[str, Any]]], str]:
    """Load the three frozen contracts strictly bound to a bundle manifest.

    The manifest must already have passed ``FileTrustStore.validate_bundle``
    (the adapter layer owns that step; this module never judges manifest
    validity on its own). Binding here means:

    1. every consumed contract file must be pinned by the manifest with a
       well-formed sha256, and
    2. the contract bytes on disk must hash to the pinned value.

    Any gap or drift raises ``PolicyDocumentError`` (fail closed) instead of
    letting the policy consume contracts it cannot tie to the validated
    manifest. Returns the parsed contracts plus the sha256 of the manifest
    bytes, which becomes the engine's verified-bundle identity.
    """
    manifest_path = Path(manifest_path)
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise PolicyDocumentError(f"cannot read bundle manifest {manifest_path}: {exc}") from exc
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyDocumentError(f"bundle manifest {manifest_path} is not valid JSON: {exc}") from exc
    if not isinstance(manifest, Mapping):
        raise PolicyDocumentError("bundle manifest must be a JSON object")

    files = manifest.get("files")
    pinned: dict[str, str] = {}
    if isinstance(files, list):
        for entry in files:
            if not isinstance(entry, Mapping):
                continue
            repo_path = entry.get("repo_path")
            sha256 = entry.get("sha256")
            if isinstance(repo_path, str) and isinstance(sha256, str):
                pinned[repo_path] = sha256

    contracts_dir = Path(repo_root) / CONTRACTS_SUBPATH
    loaded: list[tuple[str, Mapping[str, Any]]] = []
    for filename in CONTRACT_FILENAMES:
        repo_path = (CONTRACTS_SUBPATH / filename).as_posix()
        expected = pinned.get(repo_path, "")
        if len(expected) != 64:
            raise PolicyDocumentError(
                f"contract {filename} is not pinned by the bundle manifest as {repo_path!r}"
            )
        path = contracts_dir / filename
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise PolicyDocumentError(f"cannot read required contract {filename}: {exc}") from exc
        actual = hashlib.sha256(raw).hexdigest()
        if actual != expected:
            raise PolicyDocumentError(
                f"contract {filename} drifted from the validated bundle manifest "
                f"(pinned {expected[:12]}…, actual {actual[:12]}…)"
            )
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PolicyDocumentError(f"contract {filename} is not valid JSON: {exc}") from exc
        if not isinstance(document, Mapping):
            raise PolicyDocumentError(f"contract {filename} must be a JSON object")
        loaded.append((filename, document))
    return loaded, hashlib.sha256(manifest_bytes).hexdigest()
