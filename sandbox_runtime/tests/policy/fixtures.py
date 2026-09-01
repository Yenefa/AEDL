"""Shared fixtures for the Agent M policy test suite.

All documents produced here are synthetic TEST_ONLY policy documents. They are
never a substitute for the real EDD-001 contracts, which live in
gates/contracts/ and are exercised by test_edd001_preflight.py.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from aedl_sandbox.protocol import ActorIdentity, CapabilityGrant, Outcome, PolicyRequest

# Sentinel used with complete_document(...) to remove a key entirely.
DELETE = object()

DOMAIN_ID = "EDD-001"
BOARD_ID = "project-027-edd001"

_BASE_DOCUMENT: dict[str, Any] = {
    "schema_version": 1,
    "domain_id": DOMAIN_ID,
    "board_id": BOARD_ID,
    "allowed_components": [
        {
            "mpn": "TEST-RES-10K",
            "role": "pullup",
            "required_evidence_ids": ["TEST_EVIDENCE_A"],
        },
        {
            "mpn": "LED_GENERIC",
            "role": "indicator",
            "required_evidence_ids": [],
            "requires_resolution": True,
        },
    ],
    "pins": {
        "allowed": ["GPIO1", "GPIO2"],
        "core_reserved": ["GPIO0"],
        "hard_forbidden": ["GPIO35"],
        "soft_reserved": ["GPIO43"],
        "rule_sources": {
            "GPIO35": "PIN_PSRAM_HARD_FORBIDDEN",
            "GPIO0": "PIN_CORE_RESERVED",
            "GPIO43": "PIN_SOFT_RESERVED",
        },
    },
    "parameters": [
        {
            "parameter_id": "TEST_PULLUP_OHM",
            "value_type": "number",
            "unit": "ohm",
            "allowed_values": [10000.0],
            "required_evidence_ids": ["TEST_EVIDENCE_A"],
        },
        {
            # Range-bounded (minimum/maximum, no allowed_values): the exact
            # shape behind the NaN/±inf bound-bypass counterexample.
            "parameter_id": "TEST_RANGE_OHM",
            "value_type": "number",
            "unit": "ohm",
            "minimum": 0.0,
            "maximum": 10.0,
            "required_evidence_ids": ["TEST_EVIDENCE_A"],
        },
        {
            "parameter_id": "TEST_LED_COLOR",
            "value_type": "string",
            "unit": "none",
            "allowed_values": ["red", "green"],
            "required_evidence_ids": [],
        },
    ],
    "file_policy": {
        "candidate_root_only": True,
        "direct_kicad_write": False,
        "allowed_artifact_kinds": ["hir", "netlist", "bom", "report", "kicad_sch", "kicad_pcb"],
        "agent_forbidden_artifact_kinds": ["kicad_sch", "kicad_pcb"],
    },
    "network_policy": {"runtime_access": False},
    "shell_policy": {"arbitrary_shell": False},
    "tools": [
        {
            "tool_id": "kicad-cli",
            "tool_version": "8.0.0",
            "capability": "netlist_export",
        }
    ],
    "compilers": [
        {
            "compiler_id": "hir-to-kicad",
            "compiler_version": "1.0.0",
            "output_kind": "kicad_sch",
            "required_coverage_ids": ["ERC", "CONTRACT"],
        }
    ],
    "verifiers": [
        {
            "verifier_id": "kicad-audit",
            "verifier_version": "1.0.0",
            "artifact_kind": "kicad_sch",
            "coverage_ids": ["ERC", "DRC", "CONTRACT"],
        }
    ],
    "prerequisites": {
        "required_contract_ids": ["EDD-001.CORE_BASE"],
        "required_evidence_ids": ["TEST_EVIDENCE_A"],
        "required_component_resolutions": [],
    },
    "available": {
        "contract_ids": ["EDD-001.CORE_BASE"],
        "evidence_ids": ["TEST_EVIDENCE_A"],
    },
    "active_rules": [
        {
            "rule_id": "PIN_PSRAM_HARD_FORBIDDEN",
            "source_contract_id": "edd001_core_base_contract_v1.json",
            "kind": "pin_constraint",
            "fingerprint": "f" * 64,
        }
    ],
}


def complete_document(**overrides: Any) -> dict[str, Any]:
    """Return a fully-valid synthetic TEST_ONLY policy document.

    Keyword arguments replace top-level keys; passing ``DELETE`` removes one.
    """
    doc = copy.deepcopy(_BASE_DOCUMENT)
    for key, value in overrides.items():
        if value is DELETE:
            doc.pop(key, None)
        else:
            doc[key] = value
    return doc


def request(
    action: str,
    subject: dict[str, Any],
    *,
    candidate_root: Path,
    run_id: str = "run-test-0001",
    domain_id: str = DOMAIN_ID,
    action_id: str = "act-0001",
    actor: ActorIdentity | None = None,
    capability_grants: tuple[CapabilityGrant, ...] = (),
    verified_bundle_sha256: str = "",
    verified_manifest_path: str = "",
) -> PolicyRequest:
    """PolicyRequest builder. The V2 keyword arguments exercise the trusted
    request channels (actor identity, orchestrator-signed capability grants,
    verified bundle reference) that the engine consumes instead of
    requester-filled subject fields."""
    return PolicyRequest(
        run_id=run_id,
        domain_id=domain_id,
        action_id=action_id,
        action=action,
        candidate_root=candidate_root,
        subject=subject,
        actor=actor,
        capability_grants=capability_grants,
        verified_bundle_sha256=verified_bundle_sha256,
        verified_manifest_path=verified_manifest_path,
    )


def approved_pin_grant(
    *,
    run_id: str = "run-test-0001",
    actor_id: str = "agent-1",
    receipt_sha256: str = "a" * 64,
) -> CapabilityGrant:
    return CapabilityGrant(
        run_id=run_id,
        actor_id=actor_id,
        capability="approval_status=APPROVED",
        receipt_sha256=receipt_sha256,
    )


def compiler_writer_grant(
    *,
    run_id: str = "run-test-0001",
    actor_id: str = "compiler-1",
    receipt_sha256: str = "b" * 64,
) -> CapabilityGrant:
    return CapabilityGrant(
        run_id=run_id,
        actor_id=actor_id,
        capability="writer=compiler",
        receipt_sha256=receipt_sha256,
    )


def codes(decision: Any) -> list[str]:
    return sorted({finding.code for finding in decision.findings})


def assert_sorted_findings(testcase: Any, decision: Any) -> None:
    keys = [(f.code, f.source, f.message) for f in decision.findings]
    testcase.assertEqual(keys, sorted(keys), "findings must be sorted by (code, source, message)")


def assert_prefixes(testcase: Any, decision: Any, prefixes: tuple[str, ...]) -> None:
    testcase.assertTrue(
        decision.reason_code.startswith(prefixes),
        f"reason code {decision.reason_code!r} outside namespace {prefixes}",
    )


__all__ = [
    "BOARD_ID",
    "DELETE",
    "DOMAIN_ID",
    "Outcome",
    "approved_pin_grant",
    "assert_prefixes",
    "assert_sorted_findings",
    "codes",
    "compiler_writer_grant",
    "complete_document",
    "request",
]
