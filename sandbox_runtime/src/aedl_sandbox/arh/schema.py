"""ARH schema — the two structures that cross the agent boundary.

``RepairContext`` (into the model) and ``RepairProposal`` (out of the model)
are the ONLY things an LLM ever sees or produces in AEDL. Everything else in
the ARH package is plumbing around this boundary, and the boundary itself is
frozen by ADR-016 against:

  docs/specs/AEDL_AGENT_RUNTIME_RFC.md  §3.2 (RepairContext field table)
                                        §3.3 (proposal output contract)
                                        §2.3 (never-grant: authority fields)

Design rules, in force here:

* The model never supplies authoritative ``PolicyRequest`` fields. They are
  listed in ``AUTHORITY_FIELDS``; a proposal carrying any of them is rejected
  at parse time (``AuthorityFieldError``) and counted as an invalid proposal
  — this is the observable evidence for RFC §2.5 N2.
* Nothing in this module reads files, opens sockets, or imports policy
  verdicts. It is data + deterministic encoding only, so every ARH module can
  be tested offline.
* Encodings are deterministic (sorted keys, no whitespace variance): the
  context digest and subject digest are stable across processes, which is
  what makes trajectory rows and stall fingerprints comparable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from aedl_sandbox.protocol import Finding, JsonValue

__all__ = [
    "AUTHORITY_FIELDS",
    "PROPOSAL_KEYS",
    "LOCATOR_KEYS",
    "SUBJECT_ENVELOPE_KEYS",
    "V1_DESIGN_ACTIONS",
    "ProposalError",
    "AuthorityFieldError",
    "MalformedProposalError",
    "RepairProposal",
    "AttemptRow",
    "RejectedRow",
    "ContextInputs",
    "RepairContext",
    "canonical_json",
    "digest",
    "encode_finding",
]

# --------------------------------------------------------------------------
# Frozen key sets (RFC §2.2 / §2.3 / §3.3)
# --------------------------------------------------------------------------

#: Every authoritative ``PolicyRequest`` field. A proposal envelope carrying
#: any of these is not "slightly wrong" — it is an attempt to speak with the
#: Trust Plane's voice, and it is refused before any policy evaluation runs
#: (RFC §2.3 never-grant item 5; threat T-07).
AUTHORITY_FIELDS: frozenset[str] = frozenset(
    {
        "run_id",
        "domain_id",
        "action",
        "action_id",
        "candidate_root",
        "actor",
        "capability_grants",
        "verified_bundle_sha256",
        "verified_manifest_path",
    }
)

#: The complete legal top-level shape of a model-produced proposal
#: (RFC §3.3). Anything else is an envelope-extra (threat T-08).
PROPOSAL_KEYS: frozenset[str] = frozenset(
    {"diagnosis", "design_action", "design_subject", "evidence_ids", "locator"}
)

#: Legal keys inside the optional ``locator`` block (RFC §3.3).
LOCATOR_KEYS: frozenset[str] = frozenset(
    {"contract_id", "rule_fingerprint", "pin", "mpn", "path", "line"}
)

#: The ONLY shape allowed in ``PolicyRequest.subject`` for a repair plan; the
#: policy adapter unwraps exactly these two keys (adapters.py
#: ``_evaluate_design_action``).
SUBJECT_ENVELOPE_KEYS: frozenset[str] = frozenset({"design_action", "design_subject"})

#: RFC §2.2 V1 design-action whitelist. Deliberately excludes FILE_WRITE,
#: NETWORK_ACCESS, SHELL_EXECUTE, TOOL_EXECUTE, COMPILE_HIR, VERIFY_ARTIFACT
#: and PREFLIGHT — execution and verification authority are not proposal
#: surface.
V1_DESIGN_ACTIONS: frozenset[str] = frozenset(
    {"DESIGN_SELECT_COMPONENT", "DESIGN_ASSIGN_PIN", "DESIGN_SET_PARAMETER"}
)


# --------------------------------------------------------------------------
# Errors — one class per failure family, because they are counted differently
# --------------------------------------------------------------------------


class ProposalError(ValueError):
    """Base class: a model output was refused by the harness."""


class AuthorityFieldError(ProposalError):
    """Proposal carried an authoritative PolicyRequest field (N2 evidence)."""


class MalformedProposalError(ProposalError):
    """Proposal failed shape/whitelist/set validation (invalid_proposals)."""


# --------------------------------------------------------------------------
# Deterministic encoding helpers (shared by builder, trajectory and port)
# --------------------------------------------------------------------------


def canonical_json(value: Any) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace.

    ARH hashes decisions, never prose formatting; two structurally equal
    values must always produce the same bytes.
    """
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value: Any, length: int = 16) -> str:
    """Stable sha256 prefix of the canonical encoding of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:length]


def encode_finding(finding: Finding) -> dict[str, JsonValue]:
    """A ``Finding`` as the model sees it: the four frozen fields, verbatim.

    ``code`` and ``message`` are never rewritten — stall detection fingerprints
    them (D1), so a paraphrase here would silently break the orchestrator's
    cycle detection.
    """
    return {
        "code": finding.code,
        "message": finding.message,
        "source": finding.source,
        "details": dict(finding.details),
    }


# --------------------------------------------------------------------------
# Proposal — the only model output shape (RFC §3.3)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RepairProposal:
    """A validated, model-produced repair proposal.

    Never construct one directly from raw model text: ``from_json`` is the
    validation gate (authority keys, envelope extras, locator shape).
    """

    diagnosis: str
    design_action: str
    design_subject: Mapping[str, JsonValue]
    evidence_ids: tuple[str, ...] = ()
    locator: Mapping[str, JsonValue] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: Any) -> "RepairProposal":
        """Strict parse of a decoded model payload.

        Raises ``AuthorityFieldError`` if any authoritative field appears
        anywhere at the top level (even alongside valid fields — presence is
        the offence), and ``MalformedProposalError`` for any other key shape
        violation. Validation of action vocabulary and subject field sets
        happens in the repair agent, which holds the policy vocabulary.
        """
        if not isinstance(data, Mapping):
            raise MalformedProposalError(
                f"proposal must be a JSON object, got {type(data).__name__}"
            )
        offending = sorted(AUTHORITY_FIELDS & set(data))
        if offending:
            raise AuthorityFieldError(
                "proposal carries authoritative PolicyRequest field(s): "
                + ", ".join(offending)
                + " — authority is never agent-controlled"
            )
        extra = sorted(set(data) - PROPOSAL_KEYS)
        if extra:
            raise MalformedProposalError(
                "proposal carries unknown field(s): " + ", ".join(extra)
            )
        for key in ("diagnosis", "design_action"):
            if not isinstance(data.get(key), str):
                raise MalformedProposalError(f"proposal.{key} must be a string")
        subject = data.get("design_subject")
        if not isinstance(subject, Mapping):
            raise MalformedProposalError("proposal.design_subject must be an object")
        evidence_ids = data.get("evidence_ids", [])
        if not isinstance(evidence_ids, (list, tuple)) or not all(
            isinstance(item, str) for item in evidence_ids
        ):
            raise MalformedProposalError("proposal.evidence_ids must be a list of strings")
        locator = data.get("locator", {})
        if not isinstance(locator, Mapping):
            raise MalformedProposalError("proposal.locator must be an object")
        unknown_locator = sorted(set(locator) - LOCATOR_KEYS)
        if unknown_locator:
            raise MalformedProposalError(
                "proposal.locator carries unknown field(s): " + ", ".join(unknown_locator)
            )
        return cls(
            diagnosis=data["diagnosis"],
            design_action=data["design_action"],
            design_subject=dict(subject),
            evidence_ids=tuple(evidence_ids),
            locator=dict(locator),
        )

    def to_json(self) -> dict[str, JsonValue]:
        """The RFC §3.3 wire shape (round-trips through ``from_json``)."""
        return {
            "diagnosis": self.diagnosis,
            "design_action": self.design_action,
            "design_subject": dict(self.design_subject),
            "evidence_ids": list(self.evidence_ids),
            "locator": dict(self.locator),
        }

    def envelope(self) -> dict[str, JsonValue]:
        """The ``PolicyRequest.subject`` shape the policy adapter unwraps."""
        return {
            "design_action": self.design_action,
            "design_subject": dict(self.design_subject),
        }

    @property
    def subject_digest(self) -> str:
        """Stable digest of the design subject — the dedup key (§3.2 row 7)."""
        return digest(dict(self.design_subject))


# --------------------------------------------------------------------------
# Trajectory row shapes — produced by TrajectoryRecorder, consumed by
# ContextBuilder for the next round's attempt history (RFC §3.2 rows 6-7)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AttemptRow:
    """One completed attempt as the next round's context sees it."""

    round: int
    fingerprint12: str
    diagnosis: str
    design_action: str
    subject_digest: str
    outcome: str

    def to_row(self) -> dict[str, JsonValue]:
        return {
            "round": self.round,
            "fingerprint12": self.fingerprint12,
            "diagnosis": self.diagnosis,
            "proposal": {"action": self.design_action, "subject_digest": self.subject_digest},
            "outcome": self.outcome,
        }


@dataclass(frozen=True)
class RejectedRow:
    """A proposal the harness refused — kept so the model stops resubmitting.

    ChatRepair's 65% duplicate-patch rate is why this list is L0-resident
    (RFC §3.2 row 7): a model that cannot see its rejected attempts repeats
    them verbatim.
    """

    round: int
    design_action: str
    subject_digest: str
    reason: str

    def to_row(self) -> dict[str, JsonValue]:
        return {
            "round": self.round,
            "action": self.design_action,
            "subject_digest": self.subject_digest,
            "reason": self.reason,
        }


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextInputs:
    """Everything the *wiring* must supply, which the model never sees raw.

    Two groups live here on purpose:

    * ``domain_id`` / ``candidate_root`` are **harness-side identity** — they
      stamp the eventual ``PolicyRequest`` and are deliberately NOT part of
      the prompt payload, so model text can never influence them (T-07).
    * the remaining fields are the L0 sources the ``ContextBuilder`` projects
      into prompt form (RFC §3.2). The builder receives them already
      projected: nothing here is an ``engine.document`` dump (D6).
    """

    domain_id: str
    candidate_root: Path
    contract_ref: Mapping[str, JsonValue]
    subject_frozen: Mapping[str, JsonValue]
    fingerprint_state: Mapping[str, JsonValue]
    verification_ref: Mapping[str, JsonValue]
    receipts_digest: tuple[Mapping[str, JsonValue], ...] = ()
    allowlist: Mapping[str, JsonValue] = field(default_factory=dict)
    action_schema: Mapping[str, JsonValue] = field(default_factory=dict)
    knowledge_ptr: tuple[str, ...] = ()
    # L1, opt-in per round (pointers or bounded excerpts, never full files)
    code_window: Mapping[str, JsonValue] | None = None
    rule_source: Mapping[str, JsonValue] | None = None
    datasheet_excerpt: Mapping[str, JsonValue] | None = None
    evidence_excerpt: Mapping[str, JsonValue] | None = None


@dataclass(frozen=True)
class RepairContext:
    """The complete, validated prompt payload for one repair round (§3.2).

    Field order follows the RFC table: L0 rows 1-13, then L1 rows 14-17.
    ``deny_list`` sits near the end of construction but is rendered at BOTH
    the top and the bottom of the prompt — position effects are real (D6).
    """

    contract_ref: Mapping[str, JsonValue]
    subject_frozen: Mapping[str, JsonValue]
    findings_current: tuple[Finding, ...]
    locator_block: tuple[Mapping[str, JsonValue], ...]
    fingerprint_state: Mapping[str, JsonValue]
    attempt_history: tuple[Mapping[str, JsonValue], ...]
    rejected_proposals: tuple[Mapping[str, JsonValue], ...]
    receipts_digest: tuple[Mapping[str, JsonValue], ...]
    allowlist: Mapping[str, JsonValue]
    action_schema: Mapping[str, JsonValue]
    deny_list: tuple[str, ...]
    knowledge_ptr: tuple[str, ...]
    verification_ref: Mapping[str, JsonValue]
    code_window: Mapping[str, JsonValue] | None = None
    rule_source: Mapping[str, JsonValue] | None = None
    datasheet_excerpt: Mapping[str, JsonValue] | None = None
    evidence_excerpt: Mapping[str, JsonValue] | None = None

    def to_prompt_dict(self, *, findings: bool = True) -> dict[str, JsonValue]:
        """Deterministic mapping for hashing and for the prompt renderer.

        ``findings=False`` yields the findings-free skeleton used for the
        per-round context digest recorded in the trajectory (the digest must
        be computable even after findings are redacted from an audit view).
        """
        payload: dict[str, JsonValue] = {
            "contract_ref": dict(self.contract_ref),
            "subject_frozen": dict(self.subject_frozen),
            "locator_block": [dict(row) for row in self.locator_block],
            "fingerprint_state": dict(self.fingerprint_state),
            "attempt_history": [dict(row) for row in self.attempt_history],
            "rejected_proposals": [dict(row) for row in self.rejected_proposals],
            "receipts_digest": [dict(row) for row in self.receipts_digest],
            "allowlist": dict(self.allowlist),
            "action_schema": dict(self.action_schema),
            "deny_list": list(self.deny_list),
            "knowledge_ptr": list(self.knowledge_ptr),
            "verification_ref": dict(self.verification_ref),
        }
        if findings:
            payload["findings_current"] = [
                encode_finding(finding) for finding in self.findings_current
            ]
        for name in ("code_window", "rule_source", "datasheet_excerpt", "evidence_excerpt"):
            value = getattr(self, name)
            if value is not None:
                payload[name] = dict(value)
        return payload

    @property
    def digest(self) -> str:
        """Stable per-round context hash, recorded in the trajectory."""
        return digest(self.to_prompt_dict())
