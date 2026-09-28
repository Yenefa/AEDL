"""AEDL Agent Runtime Harness (ARH) — thin, proposal-only, fail-closed.

The harness exists so a real LLM can close the loop on verifier findings
WITHOUT holding any engineering authority:

    findings -> RepairContext -> RepairAgent -> RepairProposal
        -> static validation (authority/whitelist/sets)
        -> PolicyRequest constructed by the HARNESS
        -> existing RepairPort consumer: policy -> execute -> verify

Boundaries (ADR-016, docs/specs/AEDL_AGENT_RUNTIME_RFC.md):

* ``protocol.py`` / ``state.py`` / the LangGraph nodes are untouched; the
  harness plugs in through the frozen ``RepairPort.propose`` signature only.
* The model never supplies authoritative ``PolicyRequest`` fields
  (``schema.AUTHORITY_FIELDS``) and never gets execute/shell/write tools.
* Trajectory is observation, evidence is receipt; they never alias (N4).
* Budget lives outside the graph and cannot be talked out of stopping (N6).

Only the schema is exported at package level: sibling modules are imported
explicitly by their consumers so a partially-built tree never fails on import.
"""

from aedl_sandbox.arh.schema import (
    AUTHORITY_FIELDS,
    LOCATOR_KEYS,
    PROPOSAL_KEYS,
    SUBJECT_ENVELOPE_KEYS,
    V1_DESIGN_ACTIONS,
    AttemptRow,
    AuthorityFieldError,
    ContextInputs,
    MalformedProposalError,
    ProposalError,
    RejectedRow,
    RepairContext,
    RepairProposal,
    canonical_json,
    digest,
    encode_finding,
)

__all__ = [
    "AUTHORITY_FIELDS",
    "LOCATOR_KEYS",
    "PROPOSAL_KEYS",
    "SUBJECT_ENVELOPE_KEYS",
    "V1_DESIGN_ACTIONS",
    "AttemptRow",
    "AuthorityFieldError",
    "ContextInputs",
    "MalformedProposalError",
    "ProposalError",
    "RejectedRow",
    "RepairContext",
    "RepairProposal",
    "canonical_json",
    "digest",
    "encode_finding",
]
