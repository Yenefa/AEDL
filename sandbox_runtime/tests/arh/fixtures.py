"""Shared ARH test fixtures — minimal in-memory state, zero I/O, zero network.

Every factory returns FRESH mutable structures so one test's mutations can
never leak into another. Values are deliberately boring and stable: they are
inputs to assertions, not data under test themselves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aedl_sandbox.arh.model_adapter import ModelResponse, ModelUsage
from aedl_sandbox.arh.schema import ContextInputs, RepairContext
from aedl_sandbox.protocol import Finding

__all__ = [
    "VALID_PROPOSAL",
    "DENY_LIST",
    "action_schema",
    "allowlist",
    "context",
    "finding",
    "inputs",
    "response",
    "valid_text",
]

DENY_LIST = (
    "never write files directly",
    "never grant capabilities",
    "never approve or promote candidates",
)

#: Stable 12-char fingerprint used in fingerprint_state["now"].
FINGERPRINT_NOW = "a1b2c3d4e5f6"


def finding(
    code: str = "UNRESOLVED_PART",
    message: str = "selected part is not in the allowlist",
) -> Finding:
    return Finding(
        code=code,
        message=message,
        source="verifier",
        details={"mpn": "RC0402-10K", "contract_id": "EDD-001"},
    )


def action_schema() -> dict[str, Any]:
    """Projection of SUBJECT_SPECS actions offered for this run (V1 set)."""
    return {
        "DESIGN_SELECT_COMPONENT": ["mpn", "role", "evidence_ids"],
        "DESIGN_ASSIGN_PIN": ["pin", "function", "approval_status"],
        "DESIGN_SET_PARAMETER": ["parameter_id", "value", "unit", "evidence_ids"],
    }


def allowlist(**overrides: Any) -> dict[str, Any]:
    """Allowlist projection (RFC §3.2 row 9). ``overrides`` may add keys —
    the builder must drop non-projection keys (D6), which its tests assert."""
    base: dict[str, Any] = {
        "evidence_ids": ["E-1", "E-2"],
        "active_rules": [{"rule_id": "R1", "fingerprint": "fp-1"}],
        "allowed_components": [
            {"mpn": "RC0402-10K", "role": "R1", "required_evidence_ids": ["E-1"]}
        ],
    }
    base.update(overrides)
    return base


def _fingerprint_state() -> dict[str, Any]:
    return {
        "now": FINGERPRINT_NOW,
        "prev": "",
        "stall_count": 0,
        "repair_count": 0,
        "max_repairs": 3,
    }


def inputs(**overrides: Any) -> ContextInputs:
    """Wiring-side inputs. ``domain_id``/``candidate_root`` here are the ONLY
    source of those fields on the eventual PolicyRequest (T-07)."""
    base: dict[str, Any] = {
        "domain_id": "EDD-001",
        "candidate_root": Path("runs") / "run-1" / "candidate" / "c1",
        "contract_ref": {"contract_id": "EDD-001", "bundle_sha256": "b" * 64},
        "subject_frozen": {"subject_id": "T1", "kind": "power-board"},
        "fingerprint_state": _fingerprint_state(),
        "verification_ref": {
            "status": "FAIL",
            "candidate_id": "c1",
            "actor": "verifier",
        },
        "receipts_digest": ({"event_type": "preflight", "hash12": "0123456789ab"},),
        "allowlist": allowlist(),
        "action_schema": action_schema(),
        "knowledge_ptr": ("docs/knowledge/PROJECT_PITFALLS.md",),
    }
    base.update(overrides)
    return ContextInputs(**base)


def context(**overrides: Any) -> RepairContext:
    """A ready-to-prompt RepairContext for direct RepairAgent tests."""
    base: dict[str, Any] = {
        "contract_ref": {"contract_id": "EDD-001"},
        "subject_frozen": {"subject_id": "T1"},
        "findings_current": (finding(),),
        "locator_block": (
            {
                "finding_code": "UNRESOLVED_PART",
                "contract_id": "EDD-001",
                "mpn": "RC0402-10K",
            },
        ),
        "fingerprint_state": _fingerprint_state(),
        "attempt_history": (),
        "rejected_proposals": (),
        "receipts_digest": ({"event_type": "preflight", "hash12": "0123456789ab"},),
        "allowlist": allowlist(),
        "action_schema": action_schema(),
        "deny_list": DENY_LIST,
        "knowledge_ptr": (),
        "verification_ref": {"status": "FAIL"},
    }
    base.update(overrides)
    return RepairContext(**base)


#: The canonical model output: passes every gate (whitelist action, exact
#: subject fields, evidence ⊆ allowlist, required evidence cited, diagnosis
#: cites the finding code).
VALID_PROPOSAL: dict[str, Any] = {
    "diagnosis": "UNRESOLVED_PART: selected part is outside the allowlist",
    "design_action": "DESIGN_SELECT_COMPONENT",
    "design_subject": {
        "mpn": "RC0402-10K",
        "role": "R1",
        "evidence_ids": ["E-1"],
    },
    "evidence_ids": ["E-1"],
    "locator": {"mpn": "RC0402-10K"},
}


def valid_text(**overrides: Any) -> str:
    """JSON text of the canonical proposal, with optional field overrides."""
    data = {**VALID_PROPOSAL, **overrides}
    return json.dumps(data, ensure_ascii=False)


def response(text: str, *, input_tokens: int = 100, output_tokens: int = 50) -> ModelResponse:
    return ModelResponse(
        text=text,
        usage=ModelUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=10,
            cache_write_tokens=0,
            raw={"prompt_tokens": input_tokens},
        ),
        model_id="fake-model",
        latency_ms=1,
    )
