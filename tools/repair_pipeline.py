"""AEDL PR-1 repair pipeline - C1 subset.

Implementation Contract v1 (docs/competition/internal/AEDL_PR1_实现合同_20260907.md)
is frozen.  This commit implements only the C1 slice (contract section 11):

  * strict Proposal parsing - PATCH/REFUSE, three-op subset, closed fields,
    forbidden self-assertion fields, limits (section 4);
  * topology policy document structure validation - host only (section 6/7);
  * public projection - make_public_context / public_feedback whitelists
    (section 6).

Deliberately NOT present in this commit: run_round, bind_policy,
snapshot/stage/commit, rollback/recovery/replay, adapter and verifier
integration (C2-C5).  They must not be faked or stubbed here.

NOTE on hash helpers: contract section 8 assigns hash_bytes/canonical_sha256 to
gates.repair_verification.  Since C2 landed, that module is the single home and
this module imports from it (digest semantics verified identical 74/74).
"""

import copy
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from gates.repair_verification import (  # single home for digests since C2
    canonical_json_bytes,
    canonical_sha256,
    compare_delta,  # PR1-C5-RUN-ROUND: the ONE acceptance entry point
    hash_bytes,
    normalize_observation,
    observation_delta,
    protected_projection_sha256,
    topology_sha256,
    _BOUND_FIELDS as _C2_BOUND_FIELDS,
    # C5 reuses verifier-private source helpers because selector binding must use the
    # exact same source semantics as C2.  Publicising this interface is deferred; C5
    # must not fork or reinterpret the parser, so the geometry stays defined in C2.
    observe_source as _c2_observe_source,
    _source_ast as _c2_source_ast,
    _source_at as _c2_source_at,
    _source_children as _c2_source_children,
    _source_components as _c2_source_components,
    _source_integer as _c2_source_integer,
    _source_one as _c2_source_one,
    _source_text as _c2_source_text,
    _source_value as _c2_source_value,
)
from tools import host_toolchain  # PR1-C5-PRE: the host toolchain identity

REPO_ROOT = Path(__file__).resolve().parents[1]
PATCH_SCHEMA_PATH = REPO_ROOT / "src" / "repair" / "patch_schema_v1.json"
TOPOLOGY_POLICY_PATH = REPO_ROOT / "src" / "repair" / "topology_policy_v1.json"

SCHEMA_VERSION = 1
PROTOCOL_VERSION = 2
TARGET_FORMAT = "kicad"

MAX_REQUEST_BYTES = 64 * 1024
MAX_JSON_DEPTH = 12
MIN_OPS = 1
MAX_OPS = 8
MAX_DIAGNOSIS = 16
MAX_TEXT_CHARS = 2048
MAX_PIN_ANCHOR_CHARS = 128

PHASE_PRECHECK = "PRECHECK"
PHASE_SNAPSHOT = "SNAPSHOT"
PHASE_STAGE_APPLY = "STAGE_APPLY"
PHASE_DELTA_CHECK = "DELTA_CHECK"
PHASE_KICAD_VERIFY = "KICAD_VERIFY"
PHASE_COMMIT = "COMMIT"
PHASES = (
    PHASE_PRECHECK,
    PHASE_SNAPSHOT,
    PHASE_STAGE_APPLY,
    PHASE_DELTA_CHECK,
    PHASE_KICAD_VERIFY,
    PHASE_COMMIT,
)

REASON_SCHEMA_INVALID = "REPAIR_SCHEMA_INVALID"
REASON_AUTH_DENIED = "REPAIR_AUTH_DENIED"
REASON_POLICY_DISABLED = "REPAIR_POLICY_DISABLED"
REASON_INPUT_DRIFT = "REPAIR_INPUT_DRIFT"
REASON_SELECTOR_AMBIGUOUS = "REPAIR_SELECTOR_AMBIGUOUS"
REASON_STRICT_REFUSED = "REPAIR_STRICT_REFUSED"
REASON_EFFECT_MISMATCH = "REPAIR_EFFECT_MISMATCH"
REASON_DELTA_MISMATCH = "REPAIR_DELTA_MISMATCH"
REASON_PROTECTED_DIFF = "REPAIR_PROTECTED_DIFF"
REASON_TOOL_UNAVAILABLE = "REPAIR_TOOL_UNAVAILABLE"
REASON_TOOL_PROTOCOL_ERROR = "REPAIR_TOOL_PROTOCOL_ERROR"
REASON_TIMEOUT = "REPAIR_TIMEOUT"
REASON_EXPORT_STALE = "REPAIR_EXPORT_STALE"
REASON_SOURCE_UNBOUND = "REPAIR_SOURCE_UNBOUND"
REASON_COVERAGE_INCOMPLETE = "REPAIR_COVERAGE_INCOMPLETE"
REASON_PARSER_DISAGREEMENT = "REPAIR_PARSER_DISAGREEMENT"
REASON_ROLLBACK_FAILED = "REPAIR_ROLLBACK_FAILED"
REASON_RECOVERY_AMBIGUOUS = "REPAIR_RECOVERY_AMBIGUOUS"

REASON_CODES = (
    REASON_SCHEMA_INVALID,
    REASON_AUTH_DENIED,
    REASON_POLICY_DISABLED,
    REASON_INPUT_DRIFT,
    REASON_SELECTOR_AMBIGUOUS,
    REASON_STRICT_REFUSED,
    REASON_EFFECT_MISMATCH,
    REASON_DELTA_MISMATCH,
    REASON_PROTECTED_DIFF,
    REASON_TOOL_UNAVAILABLE,
    REASON_TOOL_PROTOCOL_ERROR,
    REASON_TIMEOUT,
    REASON_EXPORT_STALE,
    REASON_SOURCE_UNBOUND,
    REASON_COVERAGE_INCOMPLETE,
    REASON_PARSER_DISAGREEMENT,
    REASON_ROLLBACK_FAILED,
    REASON_RECOVERY_AMBIGUOUS,
)

PUBLIC_REASON_BY_CODE = {
    REASON_SCHEMA_INVALID: "PROPOSAL_INVALID",
    REASON_AUTH_DENIED: "REPAIR_NOT_AUTHORIZED",
    REASON_POLICY_DISABLED: "REPAIR_NOT_AUTHORIZED",
    REASON_INPUT_DRIFT: "INPUT_CHANGED",
    REASON_EXPORT_STALE: "INPUT_CHANGED",
    REASON_SOURCE_UNBOUND: "INPUT_CHANGED",
    REASON_SELECTOR_AMBIGUOUS: "REPAIR_CONSTRAINT_VIOLATION",
    REASON_STRICT_REFUSED: "REPAIR_CONSTRAINT_VIOLATION",
    REASON_EFFECT_MISMATCH: "REPAIR_CONSTRAINT_VIOLATION",
    REASON_DELTA_MISMATCH: "REPAIR_CONSTRAINT_VIOLATION",
    REASON_PROTECTED_DIFF: "REPAIR_CONSTRAINT_VIOLATION",
    REASON_TOOL_UNAVAILABLE: "EXECUTION_UNAVAILABLE",
    REASON_TOOL_PROTOCOL_ERROR: "EXECUTION_UNAVAILABLE",
    REASON_TIMEOUT: "EXECUTION_UNAVAILABLE",
    REASON_COVERAGE_INCOMPLETE: "EXECUTION_UNAVAILABLE",
    REASON_PARSER_DISAGREEMENT: "EXECUTION_UNAVAILABLE",
    REASON_ROLLBACK_FAILED: "EXECUTION_UNAVAILABLE",
    REASON_RECOVERY_AMBIGUOUS: "EXECUTION_UNAVAILABLE",
}
REJECT_REASON_PRIORITY = (
    "PROPOSAL_INVALID",
    "REPAIR_NOT_AUTHORIZED",
    "INPUT_CHANGED",
    "REPAIR_CONSTRAINT_VIOLATION",
    "EXECUTION_UNAVAILABLE",
)
PUBLIC_REASON_CODES = (
    "OK",
    "PROPOSAL_INVALID",
    "REPAIR_NOT_AUTHORIZED",
    "REPAIR_CONSTRAINT_VIOLATION",
    "INPUT_CHANGED",
    "EXECUTION_UNAVAILABLE",
)

STATUS_COMMITTED = "COMMITTED"
STATUS_NO_CHANGE = "NO_CHANGE"
STATUS_REFUSED = "REFUSED"
STATUS_ROLLBACK = "ROLLBACK"
STATUS_BLOCKED = "BLOCKED"
STATUS_TOOL_ERROR = "TOOL_ERROR"
STATUS_UNKNOWN = "UNKNOWN"
TRANSACTION_STATUSES = (
    STATUS_COMMITTED,
    STATUS_NO_CHANGE,
    STATUS_REFUSED,
    STATUS_ROLLBACK,
    STATUS_BLOCKED,
    STATUS_TOOL_ERROR,
    STATUS_UNKNOWN,
)

OUTCOME_APPLIED = "APPLIED_TO_CANDIDATE"
OUTCOME_NO_CHANGE = "NO_CHANGE"
OUTCOME_REFUSED = "REFUSED"
OUTCOME_REJECTED = "REJECTED"
OUTCOME_UNAVAILABLE = "EXECUTION_UNAVAILABLE"
PUBLIC_OUTCOMES = (
    OUTCOME_APPLIED,
    OUTCOME_NO_CHANGE,
    OUTCOME_REFUSED,
    OUTCOME_REJECTED,
    OUTCOME_UNAVAILABLE,
)

DECISION_PATCH = "PATCH"
DECISION_REFUSE = "REFUSE"
DECISIONS = (DECISION_PATCH, DECISION_REFUSE)

OP_DELETE_OBJECT = "delete_object"
OP_ADD_NET_LABEL = "add_net_label"
OP_PLACE_COMPONENT = "place_component"
ALLOWED_OPS = (OP_DELETE_OBJECT, OP_ADD_NET_LABEL, OP_PLACE_COMPONENT)

# Contract section 4: the public generic library subset.  Pin numbers are a
# property of the frozen symbol, not a per-case answer.
PUBLIC_GENERIC_LIB_IDS = ("Device:R", "Device:C")
PUBLIC_GENERIC_LIB_PINS = {"Device:R": ("1", "2"), "Device:C": ("1", "2")}

# A proposal may never self-assert effect, authorisation or an expected topology.
FORBIDDEN_PROPOSAL_FIELDS = (
    "applied",
    "verdict",
    "verification_pass",
    "accepted",
    "signed_by",
    "snapshot_path",
    "authorization_ref",
    "policy_ref",
    "exception_id",
    "expected_delta",
)

PROPOSAL_COMMON_REQUIRED = (
    "schema_version",
    "context_id",
    "target",
    "base_source_sha256",
    "decision",
    "diagnosis",
)
PROPOSAL_OPTIONAL = ("oplist", "refusal")

DIAGNOSIS_KEYS = ("rule_id", "observed", "fact_ids", "requirement_level", "rationale")
REQUIREMENT_LEVELS = ("MANDATORY", "RECOMMENDED", "MARGIN", "UNKNOWN")
REFUSAL_REQUIRED = (
    "reason_code",
    "missing_fact_ids",
    "explanation",
    "required_human_decision",
)
OPLIST_KEYS = ("protocol_version", "target_format", "ops")

DELETE_OBJECT_KEYS = ("op", "uuid")
ADD_NET_LABEL_KEYS = ("op", "name", "at", "scope", "rotation")
PLACE_COMPONENT_KEYS = (
    "op",
    "lib_id",
    "designator",
    "x_mil",
    "y_mil",
    "value",
    "footprint",
    "rotation",
    "mirror",
    "unit",
)

# Public projection (contract section 6).  Whitelist only - never built by
# copying a private object and deleting fields.
PUBLIC_CONTEXT_FIELDS = (
    "schema_version",
    "context_id",
    "target",
    "base_source_sha256",
    "current_observation",
    "public_facts",
    "generic_op_schema",
    "limits",
)
PUBLIC_CONTEXT_HOST_KEYS = ("context_id", "target", "base_source_sha256", "limits")
PUBLIC_FEEDBACK_FIELDS = (
    "context_id",
    "proposal_outcome",
    "reason_code",
    "observed_issue_ids",
)
PUBLIC_DENY_KEYS = frozenset(
    {
        "rules",
        "rule_id",
        "route",
        "object_delta",
        "after",
        "expected_delta",
        "approved_rule_ids",
        "authority_context",
        "acceptance",
        "golden",
        "standard_patch",
        "private_report",
    }
)
PUBLIC_DENY_SUBSTRINGS = (
    "expected_delta",
    "golden",
    "standard_patch",
    "authority_context",
    "approved_rule_ids",
    "private_report",
    "topology_policy",
)

# Topology policy static document (contract section 6/7).
POLICY_TOP_LEVEL_KEYS = (
    "policy_version",
    "policy_id",
    "classification",
    "artifact_kind",
    "enabled_by_default",
    "base_commit",
    "target",
    "scope",
    "defaults",
    "binding_contract",
    "public_projection",
    "rules",
    "refusal_boundary",
    "acceptance_private_contract",
)
POLICY_DEFAULTS_KEYS = (
    "unknown_field",
    "unmatched_rule",
    "multiple_matching_rules",
    "unresolved_binding",
    "unapproved_policy",
    "operation_limit",
    "native_write_calls",
    "protect",
    "component_removal",
    "existing_component_attribute_change",
    "library_definition_change",
    "no_connect_change",
    "automatic_exception_fallback",
    "required_checks",
    "deferred_checks",
)
POLICY_DEFAULTS_FIXED = {
    "unknown_field": "REJECT",
    "unmatched_rule": "BLOCKED",
    "multiple_matching_rules": "BLOCKED",
    "unapproved_policy": "BLOCKED",
    "component_removal": "FORBIDDEN",
    "existing_component_attribute_change": "FORBIDDEN",
    "library_definition_change": "FORBIDDEN",
    "no_connect_change": "FORBIDDEN",
}
REQUIRED_CHECKS = (
    "fresh_export",
    "source_hash_binding",
    "exact_topology_delta",
    "protected_diff",
)
DEFERRED_CHECKS = {"erc": "NOT_RUN", "semantic_runner": "NOT_RUN", "formal_evidence": "NOT_RUN"}

ROUTE_STRICT = "STRICT"
ROUTE_EXCEPTION = "CONSTRAINED_EXCEPTION"
ROUTES = (ROUTE_STRICT, ROUTE_EXCEPTION)
EXCEPTION_RULE_IDS = frozenset({"E1", "E2", "E3"})
STRICT_RULE_IDS = frozenset({"DC-04", "DC-05"})
EXPECTED_RULE_IDS = frozenset(EXCEPTION_RULE_IDS | STRICT_RULE_IDS)

RULE_KEYS = (
    "id",
    "trace_case",
    "route",
    "before",
    "after",
    "object_delta",
    "operation_counts",
    "derived_risk",
)
BEFORE_KEYS = (
    "partitions",
    "component_assertions",
    "absent_components",
    "readonly_fact_assertions",
)
AFTER_KEYS = (
    "replace_partitions",
    "partitions",
    "add_components",
    "all_other_partitions",
    "distinct_partition_pins",
)
BEFORE_PARTITION_KEYS = (
    "slot",
    "names_exact",
    "members_exact",
    "no_connect",
    "capture_all_members",
    "contains",
    "excludes",
)
AFTER_PARTITION_KEYS = ("names_exact", "members_exact", "members_from", "add_exact")
ADD_COMPONENT_KEYS = (
    "reference",
    "lib_id",
    "value",
    "footprint",
    "position_mil",
    "rotation",
    "mirror",
    "unit",
    "dnp",
    "in_bom",
    "on_board",
)
OBJECT_DELTA_KEYS = ("remove", "add_labels")
REMOVE_ENTRY_KEYS = ("slot", "kind", "name", "at_pin", "scope", "endpoints_nm")
ADD_LABEL_KEYS = ("name", "at_pin", "scope", "rotation")
OPERATION_COUNT_KEYS = ("delete_object", "add_net_label", "place_component")
DERIVED_RISK_KEYS = ("named_split", "named_merge", "counts_alone_authorize")
REFUSAL_BOUNDARY_KEYS = (
    "trace_case",
    "component",
    "background_status",
    "patch_authorized",
    "valid_proposal_decision",
    "design_bytes_must_remain_unchanged",
)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_PIN_ANCHOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*\.[A-Za-z0-9_]+$")
_DESIGNATOR_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


# --------------------------------------------------------------------------
# findings and errors
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    """Host-only finding. Never serialised into public feedback."""

    code: str
    stage: str
    object_id: Optional[str]
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "stage": self.stage,
            "object_id": self.object_id,
            "detail": self.detail,
        }


class RepairContractError(ValueError):
    def __init__(self, findings: Sequence[Finding]):
        self.findings: Tuple[Finding, ...] = tuple(findings)
        if not self.findings:
            self.findings = (
                Finding(REASON_SCHEMA_INVALID, PHASE_PRECHECK, None, "contract violation"),
            )
        super().__init__("; ".join(f.code for f in self.findings))


class ProposalInvalidError(RepairContractError):
    pass


class PolicyInvalidError(RepairContractError):
    pass


def _finding(code: str, detail: str, object_id: Optional[str] = None,
             stage: str = PHASE_PRECHECK) -> Finding:
    # `stage` gained an optional parameter in PR1-C5-M7: a delta mismatch is
    # found in DELTA_CHECK, not in PRECHECK.  It defaults to the previous value
    # so every existing call site is unaffected.
    return Finding(code=code, stage=stage, object_id=object_id, detail=detail)


def _reject(code: str, detail: str, object_id: Optional[str] = None):
    raise ProposalInvalidError([_finding(code, detail, object_id)])


# --------------------------------------------------------------------------
# canonical JSON, hashing, strict parsing
# --------------------------------------------------------------------------


def _reject_non_canonical(value: Any, path: str) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        raise ValueError("canonical JSON rejects floats at %s" % path)
    if isinstance(value, str):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("canonical JSON rejects non-string keys at %s" % path)
            _reject_non_canonical(item, "%s.%s" % (path, key))
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_non_canonical(item, "%s[%d]" % (path, index))
        return
    raise ValueError("canonical JSON rejects %s at %s" % (type(value).__name__, path))


class _StrictJSONError(ValueError):
    pass


def _pairs_hook(pairs):
    seen = set()
    out = {}
    for key, value in pairs:
        if key in seen:
            raise _StrictJSONError("duplicate object key: %r" % (key,))
        seen.add(key)
        out[key] = value
    return out


def _constant_hook(name):
    if name in ("NaN", "Infinity", "-Infinity"):
        raise _StrictJSONError("non-finite number literal: %s" % name)
    return {"null": None, "true": True, "false": False}[name]


def _float_hook(literal):
    raise _StrictJSONError("floating point literal: %s" % literal)


def load_json_strict(text: str) -> Any:
    """json.loads with duplicate keys, NaN/Infinity and float literals rejected."""
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_hook,
            parse_constant=_constant_hook,
            parse_float=_float_hook,
        )
    except _StrictJSONError as exc:
        raise ProposalInvalidError([_finding(REASON_SCHEMA_INVALID, str(exc))])


def _check_depth(value: Any, limit: int = MAX_JSON_DEPTH) -> None:
    stack = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > limit:
            raise ProposalInvalidError(
                [_finding(REASON_SCHEMA_INVALID, "JSON depth exceeds %d" % limit)]
            )
        if isinstance(node, Mapping):
            for item in node.values():
                stack.append((item, depth + 1))
        elif isinstance(node, (list, tuple)):
            for item in node:
                stack.append((item, depth + 1))


# --------------------------------------------------------------------------
# scalar validators
# --------------------------------------------------------------------------


def _mapping(value: Any, path: str) -> Mapping:
    if not isinstance(value, Mapping):
        _reject(REASON_SCHEMA_INVALID, "%s must be an object" % path)
    return value


def _sequence(value: Any, path: str) -> Sequence:
    if not isinstance(value, (list, tuple)):
        _reject(REASON_SCHEMA_INVALID, "%s must be an array" % path)
    return value


def _text(value: Any, path: str, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        _reject(REASON_SCHEMA_INVALID, "%s must be a string" % path)
    if len(value) > MAX_TEXT_CHARS:
        _reject(REASON_SCHEMA_INVALID, "%s exceeds %d characters" % (path, MAX_TEXT_CHARS))
    for char in value:
        if ord(char) < 0x20 or ord(char) == 0x7F:
            _reject(REASON_SCHEMA_INVALID, "%s contains a control character" % path)
    if not allow_empty and not value.strip():
        _reject(REASON_SCHEMA_INVALID, "%s must not be empty" % path)
    return value


def _integer(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _reject(REASON_SCHEMA_INVALID, "%s must be an integer (booleans rejected)" % path)
    return value


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        _reject(REASON_SCHEMA_INVALID, "%s must match %s" % (path, _ID_RE.pattern))
    return value


def _sha256(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.match(value):
        _reject(REASON_SCHEMA_INVALID, "%s must be lowercase 64-hex SHA256" % path)
    return value


def _candidate_path(value: Any, path: str) -> str:
    text = _text(value, path, allow_empty=False)
    segments = text.split("/")
    for segment in segments:
        if not _PATH_SEGMENT_RE.match(segment):
            _reject(REASON_SCHEMA_INVALID, "%s has an invalid path segment" % path)
        if segment in (".", ".."):
            _reject(REASON_SCHEMA_INVALID, "%s contains a dot segment" % path)
        if segment.endswith(".") or segment.endswith(" "):
            _reject(REASON_SCHEMA_INVALID, "%s has a trailing dot or space segment" % path)
    return text


def _pin_anchor(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_PIN_ANCHOR_CHARS:
        _reject(REASON_SCHEMA_INVALID, "%s must be a bounded string" % path)
    if not _PIN_ANCHOR_RE.match(value):
        _reject(REASON_SCHEMA_INVALID, "%s must be a REF.PIN anchor" % path)
    return value


def _designator(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _DESIGNATOR_RE.match(value):
        _reject(REASON_SCHEMA_INVALID, "%s must be a reference designator" % path)
    return value


def _closed_keys(mapping: Mapping, allowed: Sequence[str], path: str) -> None:
    for key in mapping:
        if key not in allowed:
            _reject(REASON_SCHEMA_INVALID, "%s has unknown field %r" % (path, key))


def _require_keys(mapping: Mapping, required: Sequence[str], path: str) -> None:
    for key in required:
        if key not in mapping:
            _reject(REASON_SCHEMA_INVALID, "%s is missing required field %r" % (path, key))


# --------------------------------------------------------------------------
# proposal parsing
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Proposal:
    schema_version: int
    context_id: str
    target: str
    base_source_sha256: str
    decision: str
    diagnosis: Tuple[Dict[str, Any], ...]
    oplist: Optional[Dict[str, Any]]
    refusal: Optional[Dict[str, Any]]
    raw_sha256: str
    proposal_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        document: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "context_id": self.context_id,
            "target": self.target,
            "base_source_sha256": self.base_source_sha256,
            "decision": self.decision,
            "diagnosis": [dict(entry) for entry in self.diagnosis],
        }
        if self.oplist is not None:
            document["oplist"] = self.oplist
        if self.refusal is not None:
            document["refusal"] = self.refusal
        return document

    @property
    def ops(self) -> Tuple[Dict[str, Any], ...]:
        if self.oplist is None:
            return ()
        return tuple(self.oplist["ops"])


def parse_proposal(raw_utf8: bytes) -> Proposal:
    """Strict parse of a proposal document.

    Raises ProposalInvalidError on any violation.  Never mutates host state and
    never performs tool calls.  Route, authorisation and target equality against
    the host context are bound later (C5); this function only enforces the
    closed schema, the limits and the forbidden self-assertion fields.
    """
    if not isinstance(raw_utf8, (bytes, bytearray)):
        _reject(REASON_SCHEMA_INVALID, "proposal payload must be UTF-8 bytes")
    raw = bytes(raw_utf8)
    if len(raw) > MAX_REQUEST_BYTES:
        _reject(
            REASON_SCHEMA_INVALID,
            "proposal payload exceeds %d bytes" % MAX_REQUEST_BYTES,
        )
    if raw.startswith(b"\xef\xbb\xbf"):
        _reject(REASON_SCHEMA_INVALID, "proposal payload must not start with a BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProposalInvalidError(
            [_finding(REASON_SCHEMA_INVALID, "payload is not valid UTF-8: %s" % exc)]
        )

    document = load_json_strict(text)
    if not isinstance(document, Mapping):
        _reject(REASON_SCHEMA_INVALID, "proposal must be a JSON object")
    _check_depth(document)

    _closed_keys(document, tuple(PROPOSAL_COMMON_REQUIRED) + PROPOSAL_OPTIONAL, "$")
    for field in FORBIDDEN_PROPOSAL_FIELDS:
        if field in document:
            _reject(REASON_SCHEMA_INVALID, "proposal must not carry %r" % field)
    _require_keys(document, PROPOSAL_COMMON_REQUIRED, "$")

    schema_version = document["schema_version"]
    if isinstance(schema_version, bool) or schema_version != SCHEMA_VERSION:
        _reject(REASON_SCHEMA_INVALID, "schema_version must be %d" % SCHEMA_VERSION)

    context_id = _identifier(document["context_id"], "$.context_id")
    target = _candidate_path(document["target"], "$.target")
    base_source_sha256 = _sha256(document["base_source_sha256"], "$.base_source_sha256")

    decision = document["decision"]
    if decision not in DECISIONS:
        _reject(REASON_SCHEMA_INVALID, "decision must be one of %s" % (DECISIONS,))

    diagnosis = _parse_diagnosis(document["diagnosis"], "$.diagnosis")

    oplist = None
    refusal = None
    if decision == DECISION_PATCH:
        if "refusal" in document:
            _reject(REASON_SCHEMA_INVALID, "a PATCH proposal must not carry a refusal")
        if "oplist" not in document:
            _reject(REASON_SCHEMA_INVALID, "a PATCH proposal requires an oplist")
        oplist = _parse_oplist(document["oplist"], "$.oplist")
    else:
        if "oplist" in document:
            _reject(REASON_SCHEMA_INVALID, "a REFUSE proposal must not carry an oplist")
        if "refusal" not in document:
            _reject(REASON_SCHEMA_INVALID, "a REFUSE proposal requires a refusal")
        refusal = _parse_refusal(document["refusal"], "$.refusal")

    proposal = Proposal(
        schema_version=SCHEMA_VERSION,
        context_id=context_id,
        target=target,
        base_source_sha256=base_source_sha256,
        decision=decision,
        diagnosis=diagnosis,
        oplist=oplist,
        refusal=refusal,
        raw_sha256=hash_bytes(raw),
        proposal_sha256="",
    )
    proposal_sha256 = canonical_sha256("proposal", proposal.to_dict())
    object.__setattr__(proposal, "proposal_sha256", proposal_sha256)
    return proposal


def _parse_diagnosis(value: Any, path: str) -> Tuple[Dict[str, Any], ...]:
    items = _sequence(value, path)
    if len(items) > MAX_DIAGNOSIS:
        _reject(REASON_SCHEMA_INVALID, "%s exceeds %d entries" % (path, MAX_DIAGNOSIS))
    entries = []
    for index, item in enumerate(items):
        entry_path = "%s[%d]" % (path, index)
        entry = _mapping(item, entry_path)
        _closed_keys(entry, DIAGNOSIS_KEYS, entry_path)
        _require_keys(entry, DIAGNOSIS_KEYS, entry_path)
        level = entry["requirement_level"]
        if level not in REQUIREMENT_LEVELS:
            _reject(
                REASON_SCHEMA_INVALID,
                "%s.requirement_level must be one of %s" % (entry_path, (REQUIREMENT_LEVELS,)),
            )
        fact_ids = _sequence(entry["fact_ids"], entry_path + ".fact_ids")
        for fact_index, fact_id in enumerate(fact_ids):
            _identifier(fact_id, "%s.fact_ids[%d]" % (entry_path, fact_index))
        if len(set(fact_ids)) != len(fact_ids):
            _reject(REASON_SCHEMA_INVALID, "%s.fact_ids has duplicates" % entry_path)
        entries.append(
            {
                "rule_id": _text(entry["rule_id"], entry_path + ".rule_id", allow_empty=False),
                "observed": _text(entry["observed"], entry_path + ".observed", allow_empty=False),
                "fact_ids": list(fact_ids),
                "requirement_level": level,
                "rationale": _text(entry["rationale"], entry_path + ".rationale"),
            }
        )
    return tuple(entries)


def _parse_refusal(value: Any, path: str) -> Dict[str, Any]:
    refusal = _mapping(value, path)
    _closed_keys(refusal, REFUSAL_REQUIRED, path)
    _require_keys(refusal, REFUSAL_REQUIRED, path)
    missing = _sequence(refusal["missing_fact_ids"], path + ".missing_fact_ids")
    for index, fact_id in enumerate(missing):
        _identifier(fact_id, "%s.missing_fact_ids[%d]" % (path, index))
    if len(set(missing)) != len(missing):
        _reject(REASON_SCHEMA_INVALID, "%s.missing_fact_ids has duplicates" % path)
    return {
        "reason_code": _text(refusal["reason_code"], path + ".reason_code", allow_empty=False),
        "missing_fact_ids": list(missing),
        "explanation": _text(refusal["explanation"], path + ".explanation", allow_empty=False),
        "required_human_decision": _text(
            refusal["required_human_decision"],
            path + ".required_human_decision",
            allow_empty=False,
        ),
    }


def _parse_oplist(value: Any, path: str) -> Dict[str, Any]:
    oplist = _mapping(value, path)
    _closed_keys(oplist, OPLIST_KEYS, path)
    _require_keys(oplist, OPLIST_KEYS, path)
    protocol_version = _integer(oplist["protocol_version"], path + ".protocol_version")
    if protocol_version != PROTOCOL_VERSION:
        _reject(
            REASON_SCHEMA_INVALID,
            "%s.protocol_version must be %d" % (path, PROTOCOL_VERSION),
        )
    target_format = _text(oplist["target_format"], path + ".target_format", allow_empty=False)
    if target_format != TARGET_FORMAT:
        _reject(REASON_SCHEMA_INVALID, "%s.target_format must be %r" % (path, TARGET_FORMAT))
    ops = _sequence(oplist["ops"], path + ".ops")
    if not (MIN_OPS <= len(ops) <= MAX_OPS):
        _reject(REASON_SCHEMA_INVALID, "%s.ops must hold %d..%d ops" % (path, MIN_OPS, MAX_OPS))
    parsed = [_parse_op(op, "%s.ops[%d]" % (path, index)) for index, op in enumerate(ops)]
    return {
        "protocol_version": protocol_version,
        "target_format": target_format,
        "ops": parsed,
    }


def _parse_op(value: Any, path: str) -> Dict[str, Any]:
    op = _mapping(value, path)
    name = op.get("op")
    if name not in ALLOWED_OPS:
        _reject(REASON_SCHEMA_INVALID, "%s.op must be one of %s" % (path, (ALLOWED_OPS,)))
    if name == OP_DELETE_OBJECT:
        _closed_keys(op, DELETE_OBJECT_KEYS, path)
        _require_keys(op, DELETE_OBJECT_KEYS, path)
        return {"op": name, "uuid": _identifier(op["uuid"], path + ".uuid")}
    if name == OP_ADD_NET_LABEL:
        _closed_keys(op, ADD_NET_LABEL_KEYS, path)
        _require_keys(op, ("op", "name", "at"), path)
        scope = "local"
        if "scope" in op:
            scope = _text(op["scope"], path + ".scope", allow_empty=False)
            if scope != "local":
                _reject(REASON_SCHEMA_INVALID, "%s.scope must be 'local'" % path)
        # rotation *presence* is execution-semantic: the pinned writer branches on
        # `"rotation" in op` (akcli writers/handlers/labels.py:78-88), so an omitted
        # rotation means the native pin-derived orientation while an explicit 0
        # writes 0.  The two are different canonical Proposal identities, so the key
        # is emitted only when the raw operation carried it -- never default-filled.
        parsed = {
            "op": name,
            "name": _text(op["name"], path + ".name", allow_empty=False),
            "at": _pin_anchor(op["at"], path + ".at"),
            "scope": scope,
        }
        if "rotation" in op:
            rotation = _integer(op["rotation"], path + ".rotation")
            if rotation != 0:
                _reject(REASON_SCHEMA_INVALID, "%s.rotation must be 0" % path)
            parsed["rotation"] = rotation
        return parsed
    _closed_keys(op, PLACE_COMPONENT_KEYS, path)
    _require_keys(
        op,
        ("op", "lib_id", "designator", "x_mil", "y_mil", "value", "footprint"),
        path,
    )
    lib_id = _text(op["lib_id"], path + ".lib_id", allow_empty=False)
    if lib_id not in PUBLIC_GENERIC_LIB_IDS:
        _reject(
            REASON_SCHEMA_INVALID,
            "%s.lib_id must be one of %s" % (path, (PUBLIC_GENERIC_LIB_IDS,)),
        )
    rotation = 0
    if "rotation" in op:
        rotation = _integer(op["rotation"], path + ".rotation")
        if rotation != 0:
            _reject(REASON_SCHEMA_INVALID, "%s.rotation must be 0" % path)
    mirror = "none"
    if "mirror" in op:
        mirror = _text(op["mirror"], path + ".mirror", allow_empty=False)
        if mirror != "none":
            _reject(REASON_SCHEMA_INVALID, "%s.mirror must be 'none'" % path)
    unit = 1
    if "unit" in op:
        unit = _integer(op["unit"], path + ".unit")
        if unit != 1:
            _reject(REASON_SCHEMA_INVALID, "%s.unit must be 1" % path)
    return {
        "op": name,
        "lib_id": lib_id,
        "designator": _designator(op["designator"], path + ".designator"),
        "x_mil": _integer(op["x_mil"], path + ".x_mil"),
        "y_mil": _integer(op["y_mil"], path + ".y_mil"),
        "value": _text(op["value"], path + ".value", allow_empty=False),
        "footprint": _text(op["footprint"], path + ".footprint", allow_empty=False),
        "rotation": rotation,
        "mirror": mirror,
        "unit": unit,
    }


# --------------------------------------------------------------------------
# topology policy document (host only)
# --------------------------------------------------------------------------


def load_patch_schema(path: Optional[Path] = None) -> Dict[str, Any]:
    target = Path(path) if path is not None else PATCH_SCHEMA_PATH
    document = load_json_strict(target.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ProposalInvalidError([_finding(REASON_SCHEMA_INVALID, "patch schema must be an object")])
    return dict(document)


def load_topology_policy(path: Optional[Path] = None) -> Dict[str, Any]:
    target = Path(path) if path is not None else TOPOLOGY_POLICY_PATH
    try:
        document = load_json_strict(target.read_text(encoding="utf-8"))
    except (OSError, RepairContractError) as exc:
        # load_json_strict wraps its own strict-JSON failures as
        # ProposalInvalidError; a policy file failing to parse is a POLICY
        # error, not a proposal one.  Every policy failure exits through
        # PolicyInvalidError so callers/tests have exactly one path to catch.
        raise PolicyInvalidError([_finding(REASON_SCHEMA_INVALID, "topology policy unreadable: %s" % exc)])
    if not isinstance(document, Mapping):
        raise PolicyInvalidError([_finding(REASON_SCHEMA_INVALID, "topology policy must be an object")])
    return dict(document)


def policy_rule_ids(policy: Mapping) -> Tuple[str, ...]:
    rules = policy.get("rules")
    if not isinstance(rules, (list, tuple)):
        return ()
    return tuple(str(rule.get("id")) for rule in rules if isinstance(rule, Mapping))


def validate_topology_policy(policy: Mapping) -> Tuple[Finding, ...]:
    """Structural validation of the static host-only policy document.

    Returns every finding instead of raising, so a reviewer sees the complete
    closure report.  Absence of runtime approval (section 6: enabled only with a
    real host approval record) is NOT validated here - this function only checks
    that the frozen document is internally closed and self-consistent.
    """
    findings: List[Finding] = []

    def add(detail: str, object_id: Optional[str] = None, code: str = REASON_SCHEMA_INVALID):
        findings.append(Finding(code=code, stage=PHASE_PRECHECK, object_id=object_id, detail=detail))

    def closed(mapping: Any, allowed: Sequence[str], path: str) -> Mapping:
        if not isinstance(mapping, Mapping):
            add("%s must be an object" % path)
            return {}
        for key in mapping:
            if key not in allowed:
                add("%s has unknown field %r" % (path, key))
        return mapping

    def strings(value: Any, path: str) -> List[str]:
        if not isinstance(value, (list, tuple)):
            add("%s must be an array" % path)
            return []
        out = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                add("%s[%d] must be a string" % (path, index))
                continue
            out.append(item)
        return out

    def pins(value: Any, path: str) -> List[str]:
        out = strings(value, path)
        for item in out:
            if not _PIN_ANCHOR_RE.match(item):
                add("%s entry %r is not a REF.PIN anchor" % (path, item))
        return out

    if not isinstance(policy, Mapping):
        add("topology policy must be an object")
        return tuple(findings)

    closed(policy, POLICY_TOP_LEVEL_KEYS, "$")
    for key in ("policy_version", "policy_id", "classification", "target", "scope", "defaults", "binding_contract", "public_projection", "rules", "refusal_boundary"):
        if key not in policy:
            add("topology policy is missing %r" % key)

    if policy.get("policy_version") != 1 or isinstance(policy.get("policy_version"), bool):
        add("policy_version must be 1")
    if policy.get("classification") != "HOST_ONLY":
        add("classification must be HOST_ONLY")
    if policy.get("enabled_by_default") is not False:
        add("enabled_by_default must remain false in the static file")
    if policy.get("scope") != "ONE_FLAT_M2_SCHEMATIC_ONE_ROUND":
        add("scope must be ONE_FLAT_M2_SCHEMATIC_ONE_ROUND")

    defaults = closed(policy.get("defaults"), POLICY_DEFAULTS_KEYS, "$.defaults")
    for key, expected in POLICY_DEFAULTS_FIXED.items():
        if defaults.get(key) != expected:
            add("defaults.%s must be %r" % (key, expected))
    if defaults.get("automatic_exception_fallback") is not False:
        add("defaults.automatic_exception_fallback must be false")
    if defaults.get("native_write_calls") != 1:
        add("defaults.native_write_calls must be 1")
    operation_limit = defaults.get("operation_limit")
    if isinstance(operation_limit, bool) or not isinstance(operation_limit, int):
        add("defaults.operation_limit must be an integer")
        operation_limit = MAX_OPS
    elif not (1 <= operation_limit <= MAX_OPS):
        add("defaults.operation_limit must be within 1..%d" % MAX_OPS)
    required_checks = strings(defaults.get("required_checks"), "$.defaults.required_checks")
    if sorted(required_checks) != sorted(REQUIRED_CHECKS):
        add("defaults.required_checks must be exactly %s" % (list(REQUIRED_CHECKS),))
    deferred = defaults.get("deferred_checks")
    if not isinstance(deferred, Mapping):
        add("defaults.deferred_checks must be an object")
    else:
        for key, expected in DEFERRED_CHECKS.items():
            if deferred.get(key) != expected:
                add("defaults.deferred_checks.%s must be %r" % (key, expected))

    rules = policy.get("rules")
    if not isinstance(rules, (list, tuple)) or not rules:
        add("rules must be a non-empty array")
        rules = []
    seen_ids = []
    for rule in rules:
        if not isinstance(rule, Mapping):
            add("rules entries must be objects")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            add("rules entry is missing an id")
            continue
        seen_ids.append(rule_id)
        _validate_rule(rule, rule_id, operation_limit, add, closed, strings, pins)
    if len(set(seen_ids)) != len(seen_ids):
        add("rules ids must be unique")
    if set(seen_ids) != set(EXPECTED_RULE_IDS):
        add("rules ids must be exactly %s" % (sorted(EXPECTED_RULE_IDS),))

    boundary = closed(policy.get("refusal_boundary"), REFUSAL_BOUNDARY_KEYS, "$.refusal_boundary")
    if boundary.get("patch_authorized") is not False:
        add("refusal_boundary.patch_authorized must be false")
    if boundary.get("valid_proposal_decision") != DECISION_REFUSE:
        add("refusal_boundary.valid_proposal_decision must be REFUSE")
    if boundary.get("design_bytes_must_remain_unchanged") is not True:
        add("refusal_boundary.design_bytes_must_remain_unchanged must be true")

    projection = policy.get("public_projection")
    if not isinstance(projection, Mapping):
        add("public_projection must be an object")
    else:
        allow = strings(projection.get("allow"), "$.public_projection.allow")
        if sorted(allow) != sorted(PUBLIC_CONTEXT_FIELDS):
            add("public_projection.allow must be exactly %s" % (list(PUBLIC_CONTEXT_FIELDS),))
        deny = strings(projection.get("deny"), "$.public_projection.deny")
        for key in PUBLIC_DENY_KEYS:
            if key not in deny:
                add("public_projection.deny must include %r" % key)

    private = policy.get("acceptance_private_contract")
    if not isinstance(private, Mapping):
        add("acceptance_private_contract must be an object")
    else:
        if private.get("runtime_dependency") is not False:
            add("acceptance_private_contract.runtime_dependency must be false")
        consumers = strings(private.get("forbidden_consumers"), "$.acceptance_private_contract.forbidden_consumers")
        for consumer in ("C", "D", "runtime_policy_binder", "public_feedback"):
            if consumer not in consumers:
                add("acceptance_private_contract.forbidden_consumers must include %r" % consumer)

    return tuple(findings)


def _validate_rule(rule, rule_id, operation_limit, add, closed, strings, pins):
    path = "$.rules[%s]" % rule_id
    closed(rule, RULE_KEYS, path)

    expected_route = None
    if rule_id in EXCEPTION_RULE_IDS:
        expected_route = ROUTE_EXCEPTION
    elif rule_id in STRICT_RULE_IDS:
        expected_route = ROUTE_STRICT
    else:
        add("%s.id %r is not one of the frozen rule ids" % (path, rule_id))
    if expected_route is not None and rule.get("route") != expected_route:
        add("%s.route must be %r" % (path, expected_route))
    if rule.get("trace_case") is None:
        add("%s.trace_case is required" % path)

    before = closed(rule.get("before"), BEFORE_KEYS, path + ".before")
    after = closed(rule.get("after"), AFTER_KEYS, path + ".after")
    if after.get("all_other_partitions") != "UNCHANGED":
        add("%s.after.all_other_partitions must be UNCHANGED" % path)

    # before partitions
    before_slots = {}
    before_names = {}
    for index, item in enumerate(before.get("partitions") or []):
        slot_path = "%s.before.partitions[%d]" % (path, index)
        partition = closed(item, BEFORE_PARTITION_KEYS, slot_path)
        slot = partition.get("slot")
        if not isinstance(slot, str) or not slot:
            add("%s.slot is required" % slot_path)
            continue
        if slot in before_slots:
            add("%s.slot duplicates %r" % (slot_path, slot))
            continue
        names = strings(partition.get("names_exact") or [], slot_path + ".names_exact")
        members = pins(partition.get("members_exact") or [], slot_path + ".members_exact")
        pins(partition.get("contains") or [], slot_path + ".contains")
        pins(partition.get("excludes") or [], slot_path + ".excludes")
        capture = partition.get("capture_all_members")
        if capture is not None and not isinstance(capture, bool):
            add("%s.capture_all_members must be a boolean" % slot_path)
            capture = None
        has_exact = "members_exact" in partition
        if bool(capture) == has_exact:
            add(
                "%s must declare exactly one of members_exact or capture_all_members"
                % slot_path
            )
        before_slots[slot] = {
            "names": set(names),
            "members": set(members),
            "capture": bool(capture),
        }
        before_names[slot] = set(names)

    absent = strings(before.get("absent_components") or [], path + ".before.absent_components")
    absent_set = set(absent)
    if len(absent_set) != len(absent):
        add("%s.before.absent_components has duplicates" % path)

    # new components
    new_components = {}
    for index, item in enumerate(after.get("add_components") or []):
        comp_path = "%s.after.add_components[%d]" % (path, index)
        component = closed(item, ADD_COMPONENT_KEYS, comp_path)
        reference = component.get("reference")
        if not isinstance(reference, str) or not reference:
            add("%s.reference is required" % comp_path)
            continue
        if reference in new_components:
            add("%s.reference duplicates %r" % (comp_path, reference))
        lib_id = component.get("lib_id")
        if lib_id not in PUBLIC_GENERIC_LIB_PINS:
            add("%s.lib_id must be one of %s" % (comp_path, sorted(PUBLIC_GENERIC_LIB_PINS)))
        position = component.get("position_mil")
        if (
            not isinstance(position, (list, tuple))
            or len(position) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) for v in position)
        ):
            add("%s.position_mil must be [x_mil, y_mil] integers" % comp_path)
        if component.get("rotation") != 0 or isinstance(component.get("rotation"), bool):
            add("%s.rotation must be 0" % comp_path)
        if component.get("mirror") != "none":
            add("%s.mirror must be 'none'" % comp_path)
        if component.get("unit") != 1 or isinstance(component.get("unit"), bool):
            add("%s.unit must be 1" % comp_path)
        if component.get("dnp") is not False:
            add("%s.dnp must be false" % comp_path)
        if component.get("in_bom") is not True:
            add("%s.in_bom must be true" % comp_path)
        if component.get("on_board") is not True:
            add("%s.on_board must be true" % comp_path)
        for field in ("value", "footprint"):
            if not isinstance(component.get(field), str) or not component.get(field):
                add("%s.%s must be a non-empty string" % (comp_path, field))
        new_components[reference] = component

    if set(new_components) != absent_set:
        add(
            "%s: after.add_components references must equal before.absent_components"
            % path,
            object_id=rule_id,
        )

    # replace_partitions closure
    replace = strings(after.get("replace_partitions") or [], path + ".after.replace_partitions")
    if not replace:
        add("%s.after.replace_partitions must be non-empty" % path)
    if len(set(replace)) != len(replace):
        add("%s.after.replace_partitions has duplicates" % path)
    for slot in replace:
        if slot not in before_slots:
            add("%s.after.replace_partitions references unknown slot %r" % (path, slot))

    # after partitions - every change must resolve back to a declared before slot
    referenced_pins: Dict[str, set] = {}
    changed_slots = set()
    for index, item in enumerate(after.get("partitions") or []):
        part_path = "%s.after.partitions[%d]" % (path, index)
        partition = closed(item, AFTER_PARTITION_KEYS, part_path)
        names = strings(partition.get("names_exact") or [], part_path + ".names_exact")
        members = pins(partition.get("members_exact") or [], part_path + ".members_exact")
        source = partition.get("members_from")
        additions = pins(partition.get("add_exact") or [], part_path + ".add_exact")
        if source is None and "members_exact" not in partition:
            add("%s must declare members_exact or members_from" % part_path)
            continue
        if source is not None:
            if source not in before_slots:
                add("%s.members_from references unknown slot %r" % (part_path, source))
            else:
                # members_from names a before slot by identity; the slot may have
                # been declared either as an exact member set or as a captured
                # partition, so no capture requirement is imposed here.
                if source not in replace:
                    add("%s.members_from slot %r is not in replace_partitions" % (part_path, source))
                if names and not set(names) <= before_names[source]:
                    add("%s names are not a subset of slot %r names" % (part_path, source))
                changed_slots.add(source)
        else:
            resolved = [slot for slot in replace if set(names) & before_names.get(slot, set())]
            if not resolved:
                add(
                    "%s does not resolve to any replaced before partition by name"
                    % part_path
                )
            else:
                changed_slots.update(resolved)
                union = set()
                for slot in resolved:
                    union |= before_names[slot]
                if set(names) - union:
                    add("%s introduces names absent from its source slot" % part_path)
        for pin in list(members) + list(additions):
            referenced_pins.setdefault(pin.split(".")[0], set()).add(pin.split(".")[1])

    # distinct_partition_pins must be disjoint groups of real pins
    for index, group in enumerate(after.get("distinct_partition_pins") or []):
        group_path = "%s.after.distinct_partition_pins[%d]" % (path, index)
        group_pins = pins(group, group_path)
        for pin in group_pins:
            referenced_pins.setdefault(pin.split(".")[0], set()).add(pin.split(".")[1])

    # object_delta
    delta = closed(rule.get("object_delta"), OBJECT_DELTA_KEYS, path + ".object_delta")
    remove_slots = []
    for index, item in enumerate(delta.get("remove") or []):
        entry_path = "%s.object_delta.remove[%d]" % (path, index)
        entry = closed(item, REMOVE_ENTRY_KEYS, entry_path)
        if entry.get("kind") not in ("label", "wire"):
            add("%s.kind must be 'label' or 'wire'" % entry_path)
        slot = entry.get("slot")
        if not isinstance(slot, str) or not slot:
            add("%s.slot is required" % entry_path)
        else:
            if slot in remove_slots:
                add("%s.slot duplicates %r" % (entry_path, slot))
            remove_slots.append(slot)
        if "at_pin" in entry:
            pin = _pin_anchor(entry["at_pin"], entry_path + ".at_pin")
            referenced_pins.setdefault(pin.split(".")[0], set()).add(pin.split(".")[1])
    label_count = 0
    for index, item in enumerate(delta.get("add_labels") or []):
        entry_path = "%s.object_delta.add_labels[%d]" % (path, index)
        entry = closed(item, ADD_LABEL_KEYS, entry_path)
        label_count += 1
        if entry.get("scope") != "local":
            add("%s.scope must be 'local'" % entry_path)
        if entry.get("rotation") != 0 or isinstance(entry.get("rotation"), bool):
            add("%s.rotation must be 0" % entry_path)
        if not isinstance(entry.get("name"), str) or not entry.get("name"):
            add("%s.name must be a non-empty string" % entry_path)
        pin = _pin_anchor(entry.get("at_pin"), entry_path + ".at_pin")
        referenced_pins.setdefault(pin.split(".")[0], set()).add(pin.split(".")[1])

    # operation counts must match the declared delta exactly
    counts = rule.get("operation_counts")
    if not isinstance(counts, Mapping):
        add("%s.operation_counts must be an object" % path)
        counts = {}
    else:
        closed(counts, OPERATION_COUNT_KEYS, path + ".operation_counts")
        for key in OPERATION_COUNT_KEYS:
            value = counts.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                add("%s.operation_counts.%s must be a non-negative integer" % (path, key))
    expected_counts = {
        "delete_object": len(delta.get("remove") or []),
        "add_net_label": label_count,
        "place_component": len(after.get("add_components") or []),
    }
    for key, expected in expected_counts.items():
        value = counts.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value != expected:
            add(
                "%s.operation_counts.%s must be %d (declared delta)" % (path, key, expected)
            )
    total = sum(
        v for v in expected_counts.values()
    )
    if not (1 <= total <= operation_limit):
        add("%s declares %d operations, outside 1..%d" % (path, total, operation_limit))

    # every new component pin must be completely covered
    for reference, component in new_components.items():
        expected_pins = set(PUBLIC_GENERIC_LIB_PINS.get(component.get("lib_id"), ()))
        actual = referenced_pins.get(reference, set())
        if actual != expected_pins:
            add(
                "%s: new component %s pins must be exactly %s, found %s"
                % (path, reference, sorted(expected_pins), sorted(actual)),
                object_id=rule_id,
            )
    # a pin may not belong to a component the rule declares absent
    for reference in referenced_pins:
        if reference in absent_set and reference not in new_components:
            add("%s references pin of absent component %r" % (path, reference))

    risk = closed(rule.get("derived_risk"), DERIVED_RISK_KEYS, path + ".derived_risk")
    if risk.get("counts_alone_authorize") is not False:
        add("%s.derived_risk.counts_alone_authorize must be false" % path)


# --------------------------------------------------------------------------
# public projection (contract section 6)
# --------------------------------------------------------------------------


def load_public_op_schema(path: Optional[Path] = None) -> Dict[str, Any]:
    """Generic op schema handed to a proposer. Contains no per-case values."""
    schema = load_patch_schema(path)
    section = schema.get("public_op_schema")
    if not isinstance(section, Mapping):
        raise ProposalInvalidError(
            [_finding(REASON_SCHEMA_INVALID, "patch schema is missing public_op_schema")]
        )
    return json.loads(json.dumps(section))


def make_public_context(
    host_context: Mapping,
    current_observation: Any,
    public_facts: Any,
) -> Dict[str, Any]:
    """Whitelist construction of the proposer-visible context.

    host_context is host-owned and must provide context_id, target,
    base_source_sha256 and limits.  Nothing else is copied: host policy rules,
    bound rule ids, route, expected/delta and internal paths stay host-only.
    """
    if not isinstance(host_context, Mapping):
        raise TypeError("host_context must be a mapping")
    for key in PUBLIC_CONTEXT_HOST_KEYS:
        if key not in host_context:
            raise KeyError("host_context is missing %r" % key)

    def _frozen_copy(value: Any, label: str) -> Any:
        # Deep snapshot via canonical JSON round-trip: the proposer-visible
        # context must never alias host-owned structures, otherwise a later
        # host-side mutation (or in-place tool output) leaks into an already
        # issued PublicContext (aliasing/TOCTOU).  Round-trip through the same
        # strict rules also guarantees the snapshot is JSON-faithful; anything
        # non-serialisable fails loudly instead of silently sharing a reference.
        payload = {"v": value}
        try:
            return json.loads(json.dumps(payload, allow_nan=False))["v"]
        except (TypeError, ValueError) as exc:
            raise ProposalInvalidError(
                [_finding(REASON_SCHEMA_INVALID, "%s is not JSON-serialisable: %s" % (label, exc))]
            )

    context = {
        "schema_version": SCHEMA_VERSION,
        "context_id": _identifier(host_context["context_id"], "host_context.context_id"),
        "target": _candidate_path(host_context["target"], "host_context.target"),
        "base_source_sha256": _sha256(
            host_context["base_source_sha256"], "host_context.base_source_sha256"
        ),
        "current_observation": _frozen_copy(current_observation, "current_observation"),
        "public_facts": _frozen_copy(public_facts, "public_facts"),
        "generic_op_schema": load_public_op_schema(),
        "limits": _frozen_copy(dict(host_context["limits"]) if isinstance(host_context["limits"], Mapping) else host_context["limits"], "host_context.limits"),
    }
    _assert_public_clean(context, "$")
    return context


def _assert_public_clean(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in PUBLIC_DENY_KEYS:
                raise ProposalInvalidError(
                    [
                        _finding(
                            REASON_SCHEMA_INVALID,
                            "public projection leaked denied key %r at %s" % (key, path),
                        )
                    ]
                )
            _assert_public_clean(item, "%s.%s" % (path, key))
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_public_clean(item, "%s[%d]" % (path, index))
        return
    if isinstance(value, str):
        for token in PUBLIC_DENY_SUBSTRINGS:
            if token in value:
                raise ProposalInvalidError(
                    [
                        _finding(
                            REASON_SCHEMA_INVALID,
                            "public projection leaked denied token %r at %s" % (token, path),
                        )
                    ]
                )


def public_context_digest(context: Mapping) -> str:
    return canonical_sha256("context", context)


def public_feedback(receipt: Mapping) -> Dict[str, Any]:
    """Whitelist projection of a transaction receipt.

    Only the four public fields are emitted.  observed_issue_ids is intersected
    with the host allowlist carried on the receipt (public_issue_ids); when that
    allowlist is absent nothing is emitted, because an id that was never public
    cannot be proven public here.
    """
    if not isinstance(receipt, Mapping):
        raise TypeError("receipt must be a mapping")

    context_id = _identifier(receipt.get("context_id"), "receipt.context_id")
    outcome = _feedback_outcome(receipt.get("status"), receipt.get("cause_status"))
    reason = _feedback_reason(outcome, receipt)

    allowlist = receipt.get("public_issue_ids")
    observed = receipt.get("observed_issue_ids") or []
    if not isinstance(observed, (list, tuple)):
        raise TypeError("receipt.observed_issue_ids must be an array")
    if allowlist is None:
        issue_ids: List[str] = []
    else:
        if not isinstance(allowlist, (list, tuple, set, frozenset)):
            raise TypeError("receipt.public_issue_ids must be an array")
        issue_ids = sorted(
            {
                _identifier(issue_id, "receipt.observed_issue_ids")
                for issue_id in observed
                if issue_id in set(allowlist)
            }
        )

    feedback = {
        "context_id": context_id,
        "proposal_outcome": outcome,
        "reason_code": reason,
        "observed_issue_ids": issue_ids,
    }
    if tuple(feedback) != PUBLIC_FEEDBACK_FIELDS:
        raise AssertionError("public feedback shape drifted")
    return feedback


def _feedback_outcome(status: Any, cause_status: Any) -> str:
    if status == STATUS_COMMITTED:
        return OUTCOME_APPLIED
    if status == STATUS_NO_CHANGE:
        return OUTCOME_NO_CHANGE
    if status == STATUS_REFUSED:
        return OUTCOME_REFUSED
    if status == STATUS_BLOCKED:
        return OUTCOME_REJECTED
    if status == STATUS_ROLLBACK:
        if cause_status == STATUS_BLOCKED:
            return OUTCOME_REJECTED
        return OUTCOME_UNAVAILABLE
    if status in (STATUS_TOOL_ERROR, STATUS_UNKNOWN):
        return OUTCOME_UNAVAILABLE
    return OUTCOME_UNAVAILABLE


# ---------------------------------------------------------------------------
# C5 stage 1: the host context contract, runtime bindings and rule binding
# ---------------------------------------------------------------------------
#
# Two different closed sets live here and must not be conflated:
#
#   _HOST_CONTEXT_FIELDS          what the HOST must provide: identities, the
#                                 candidate workspace, the toolchain binding, the
#                                 static policy path, the resolved authority and
#                                 the native execution binding (contract section 8).
#   _RUNTIME_BINDING_FIELDS       what the policy's binding_contract requires a
#                                 BoundPolicy to BIND.  Most of these are derived
#                                 by C5 -- from the parsed proposal, from the host
#                                 native read, or from C5's own observation of the
#                                 candidate's current bytes -- precisely so that a
#                                 caller cannot inject a second truth source for
#                                 the pin/object identity maps, the symbol hashes,
#                                 the before topology or the base file manifest.
#
# A value being in _RUNTIME_BINDING_FIELDS does NOT make it a host_context field.

_HOST_CONTEXT_FIELDS = (
    "run_id", "candidate_id", "round_id", "patch_id",
    "context_id", "target", "base_source_sha256", "initial_context_digest",
    "limits", "workspace", "toolchain_binding", "candidate_symbol_digest",
    "policy_path", "authority", "native",
)
# candidate_symbol_digest is a BEFORE-candidate binding supplied by the host, not a
# host-level toolchain property and not a transaction-after property: the C4 writer
# resolves place_component against the current document's embedded library, so the
# after-digest may legitimately change once a symbol is written.  It is therefore a
# host_context input that PRECHECK cross-checks against the native BEFORE observation.
_WORKSPACE_FIELDS = ("candidate_root", "design_root", "repair_root", "lock_path")
_AUTHORITY_FIELDS = ("context_digest", "resolved_authorization_refs", "decisions",
                     "approvals")
_AUTHORITY_DECISION_FIELDS = ("capability", "effect")
_APPROVAL_FIELDS = ("policy_file_sha256", "rule_id", "run_id", "candidate_id", "paths")
_NATIVE_BINDING_FIELDS = ("read_root", "artifact_root")

CAPABILITY_TOOL_EXECUTE = "TOOL_EXECUTE"
CAPABILITY_FILE_WRITE = "FILE_WRITE"
REQUIRED_CAPABILITIES = (CAPABILITY_TOOL_EXECUTE, CAPABILITY_FILE_WRITE)
EFFECT_ALLOW = "ALLOW"

# policy binding_contract.required_runtime_values (14 items), in contract order.
_RUNTIME_BINDING_FIELDS = (
    "run_id", "candidate_id", "round_id", "patch_id", "proposal_sha256",
    "base_file_manifest", "base_topology_sha256", "toolchain_manifest",
    "policy_document_sha256", "authority_context", "approved_rule_ids",
    "pin_identity_map", "object_identity_map", "embedded_symbol_hashes",
)


class HostContextError(RepairContractError):
    """The host context violates the C5 host contract.  Never a PASS."""


def _host_finding(detail, code=REASON_INPUT_DRIFT, object_id=None):
    return _finding(code, detail, object_id)


def _host_closed(value, allowed, label):
    if not isinstance(value, Mapping):
        raise HostContextError([_host_finding("%s must be a mapping" % label)])
    unknown = sorted(set(value) - set(allowed))
    missing = sorted(set(allowed) - set(value))
    if unknown or missing:
        raise HostContextError([
            _host_finding("%s has missing or unknown fields (missing=%s unknown=%s)"
                          % (label, missing, unknown))
        ])
    return value


def _host_text(value, label, allow_empty=False):
    if not isinstance(value, str) or (not value and not allow_empty):
        raise HostContextError([_host_finding("invalid %s" % label)])
    return value


def _host_identifier(value, label):
    text = _host_text(value, label)
    if not _ID_RE.match(text):
        raise HostContextError([_host_finding("invalid %s" % label)])
    return text


def _host_sha(value, label):
    text = _host_text(value, label)
    if not _SHA256_RE.match(text):
        raise HostContextError([_host_finding("invalid %s" % label)])
    return text


def _host_absolute(value, label):
    text = _host_text(value, label)
    if not os.path.isabs(text):
        raise HostContextError([_host_finding("%s must be an absolute host path" % label)])
    return os.path.normpath(text)


def _host_sequence(value, label):
    if not isinstance(value, (list, tuple)):
        raise HostContextError([_host_finding("%s must be a sequence" % label)])
    return list(value)


def validate_host_context(host_context):
    """Validate the closed host contract and return a normalized copy.

    Every field here is something only the host can supply.  Anything the policy
    requires but C5 can derive is deliberately absent: accepting it from the
    caller would create the second truth source the binding contract forbids.
    """
    _host_closed(host_context, _HOST_CONTEXT_FIELDS, "host_context")
    normalized = {
        "run_id": _host_identifier(host_context["run_id"], "run_id"),
        "candidate_id": _host_identifier(host_context["candidate_id"], "candidate_id"),
        "round_id": _host_identifier(host_context["round_id"], "round_id"),
        "patch_id": _host_identifier(host_context["patch_id"], "patch_id"),
        "context_id": _host_identifier(host_context["context_id"], "context_id"),
        "target": _candidate_path(host_context["target"], "host_context.target"),
        "base_source_sha256": _host_sha(host_context["base_source_sha256"],
                                        "base_source_sha256"),
        "initial_context_digest": _host_sha(host_context["initial_context_digest"],
                                            "initial_context_digest"),
        "limits": _host_closed_mapping(host_context["limits"], "limits"),
        "workspace": _validate_workspace(host_context["workspace"]),
        "toolchain_binding": _validate_toolchain_binding(host_context["toolchain_binding"]),
        "candidate_symbol_digest": _host_sha(host_context["candidate_symbol_digest"],
                                             "candidate_symbol_digest"),
        "policy_path": _host_absolute(host_context["policy_path"], "policy_path"),
        "authority": _validate_authority(host_context["authority"]),
        "native": _validate_native_binding(host_context["native"]),
    }
    return normalized


def _host_closed_mapping(value, label):
    if not isinstance(value, Mapping):
        raise HostContextError([_host_finding("%s must be a mapping" % label)])
    return dict(value)


def _validate_workspace(workspace):
    _host_closed(workspace, _WORKSPACE_FIELDS, "workspace")
    return {
        "candidate_root": _host_absolute(workspace["candidate_root"], "candidate_root"),
        "design_root": _host_absolute(workspace["design_root"], "design_root"),
        "repair_root": _host_absolute(workspace["repair_root"], "repair_root"),
        "lock_path": _host_absolute(workspace["lock_path"], "lock_path"),
    }


def _validate_toolchain_binding(binding):
    """The PR1-C5-PRE host toolchain identity, validated by its own module."""
    try:
        return host_toolchain.validate_host_binding(binding)
    except host_toolchain.HostBindingError as exc:
        raise HostContextError([_host_finding("invalid toolchain_binding: %s" % exc)]) from exc


def _validate_native_binding(native):
    _host_closed(native, _NATIVE_BINDING_FIELDS, "native")
    return {
        "read_root": _host_absolute(native["read_root"], "native.read_root"),
        "artifact_root": _host_absolute(native["artifact_root"], "native.artifact_root"),
    }


def _validate_authority(authority):
    _host_closed(authority, _AUTHORITY_FIELDS, "authority")
    decisions = []
    for index, row in enumerate(_host_sequence(authority["decisions"], "authority.decisions")):
        _host_closed(row, _AUTHORITY_DECISION_FIELDS, "authority.decisions[%d]" % index)
        capability = _host_text(row["capability"], "capability")
        effect = _host_text(row["effect"], "effect")
        if capability not in REQUIRED_CAPABILITIES:
            raise HostContextError([_host_finding("unknown capability %r" % capability)])
        if effect not in (EFFECT_ALLOW, "DENY"):
            raise HostContextError([_host_finding("unknown effect %r" % effect)])
        decisions.append({"capability": capability, "effect": effect})
    approvals = []
    for index, row in enumerate(_host_sequence(authority["approvals"], "authority.approvals")):
        _host_closed(row, _APPROVAL_FIELDS, "authority.approvals[%d]" % index)
        approvals.append({
            "policy_file_sha256": _host_sha(row["policy_file_sha256"], "approval policy digest"),
            "rule_id": _host_identifier(row["rule_id"], "approval rule id"),
            "run_id": _host_identifier(row["run_id"], "approval run id"),
            "candidate_id": _host_identifier(row["candidate_id"], "approval candidate id"),
            "paths": [_host_absolute(item, "approval path")
                      for item in _host_sequence(row["paths"], "approval paths")],
        })
    return {
        "context_digest": _host_sha(authority["context_digest"], "authority context digest"),
        "resolved_authorization_refs": [
            _host_identifier(item, "authorization ref")
            for item in _host_sequence(authority["resolved_authorization_refs"],
                                       "resolved_authorization_refs")
        ],
        "decisions": decisions,
        "approvals": approvals,
    }


def _policy_document_sha256(policy):
    return canonical_sha256("policy-bound", policy)


def approved_rule_ids(host_context, policy_sha):
    """Host-resolved approvals filtered to this policy digest, run and candidate.

    Contract section 8: an approval must bind this policy digest, the rule and the
    run/candidate.  Nothing here can come from the proposal.
    """
    approved = set()
    for row in host_context["authority"]["approvals"]:
        if row["policy_file_sha256"] != policy_sha:
            continue
        if row["run_id"] != host_context["run_id"]:
            continue
        if row["candidate_id"] != host_context["candidate_id"]:
            continue
        approved.add(row["rule_id"])
    return approved


def authority_findings(host_context, required_paths=()):
    """A missing or DENY decision on a required capability is a hard BLOCK."""
    effects = {}
    for row in host_context["authority"]["decisions"]:
        effects[row["capability"]] = row["effect"]
    findings = []
    for capability in REQUIRED_CAPABILITIES:
        if effects.get(capability) != EFFECT_ALLOW:
            findings.append(_finding(
                REASON_AUTH_DENIED,
                "the resolved host authority does not allow %s for this round"
                % capability))
    if findings:
        return findings
    for path in required_paths:
        covered = any(path in row["paths"] for row in host_context["authority"]["approvals"])
        if not covered:
            findings.append(_finding(
                REASON_AUTH_DENIED,
                "no host approval binds the write path %s" % path))
    return findings


def proposal_rule_ids(proposal):
    ordered = []
    for entry in proposal.diagnosis:
        rule_id = entry.get("rule_id")
        if rule_id not in ordered:
            ordered.append(rule_id)
    return ordered


def select_rule(policy, proposal, approved):
    """Exactly one approved rule, taken from the host policy and nowhere else."""
    rules = {rule["id"]: rule for rule in policy["rules"]}
    matched = [rules[rule_id] for rule_id in proposal_rule_ids(proposal)
               if rule_id in rules]
    if not matched:
        return None, [_finding(REASON_INPUT_DRIFT,
                               "no policy rule matches the proposal diagnosis")]
    ids = sorted({rule["id"] for rule in matched})
    if len(ids) > 1:
        return None, [_finding(REASON_INPUT_DRIFT,
                               "multiple policy rules match: %s" % ids)]
    rule = matched[0]
    if rule["id"] not in approved:
        return None, [_finding(REASON_AUTH_DENIED,
                               "rule %s is not host-approved for this policy digest"
                               % rule["id"])]
    if not any(rule["route"] == route for route in ROUTES):
        return None, [_finding(REASON_SCHEMA_INVALID,
                               "unknown route %r" % rule["route"])]
    return rule, []


def refusal_verdict(policy, proposal):
    """A legal REFUSE terminates at PRECHECK: no tool call, no stage write.

    The bytes-must-remain-unchanged half of the refusal boundary is a
    transaction property and is asserted by the round, not here.
    """
    boundary = policy.get("refusal_boundary") or {}
    if proposal.decision != DECISION_REFUSE:
        return [_finding(REASON_SCHEMA_INVALID, "not a REFUSE proposal")]
    findings = []
    if boundary.get("valid_proposal_decision") not in (None, DECISION_REFUSE):
        findings.append(_finding(REASON_SCHEMA_INVALID,
                                 "the policy refusal boundary does not admit REFUSE"))
    if proposal.oplist is not None or proposal.refusal is None:
        findings.append(_finding(REASON_SCHEMA_INVALID,
                                 "a REFUSE proposal carries a refusal and no oplist"))
    return findings


def observe_candidate_manifest(host_context):
    """C5's own observation of the candidate design bytes (contract section 9).

    The base file manifest is observed here rather than accepted from the caller:
    a declaration handed in by the caller is not evidence about the bytes that are
    about to be repaired.
    """
    root = Path(host_context["workspace"]["design_root"])
    target = host_context["target"]
    if not root.is_dir():
        raise HostContextError([_host_finding("design root is not a directory")])
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise HostContextError([_host_finding("the candidate design contains a link")])
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        rows.append({"path": relative, "sha256": hash_bytes(raw),
                     "size_bytes": len(raw),
                     "role": "TARGET" if relative == target else "READONLY_DEPENDENCY"})
    targets = [row for row in rows if row["role"] == "TARGET"]
    if len(targets) != 1:
        raise HostContextError([_host_finding(
            "the candidate design must carry exactly one target, found %d" % len(targets))])
    return {"version": 1, "files": rows}


def runtime_bindings(host_context, proposal, native_before, policy_sha, approved,
                     rule=None, removals=None):
    """Derive the policy's 14 required runtime values.

    Values the proposal, the host native read or C5's own observation already
    determine are derived here and are never accepted from the caller: a second
    caller-supplied truth source for the identity maps, the symbol hashes, the
    before topology or the base manifest is exactly what the policy's
    binding_contract.never_bind_from forbids.
    """
    if not isinstance(native_before, Mapping):
        raise HostContextError([_host_finding("native_before must be a mapping")])
    if native_before.get("status") != "PASS":
        raise HostContextError([_host_finding(
            "native_before is not a PASS; there is no current fault observation to bind")])
    observation = native_before.get("observation")
    if not isinstance(observation, Mapping):
        raise HostContextError([_host_finding("native_before carries no observation")])
    tool = native_before.get("tool") or {}
    symbol_digest = tool.get("symbol_digest")
    # The host supplied the before-candidate symbol digest at PRECHECK.  Cross-check
    # it against what the native read actually measured: a mismatch means the writer
    # would resolve against a different symbol environment than the one that was
    # bound, and this must block BEFORE anything is written.
    if host_context["candidate_symbol_digest"] != symbol_digest:
        raise HostContextError([_host_finding(
            "the host candidate_symbol_digest does not match the native BEFORE symbol "
            "digest (%s != %s)" % (host_context["candidate_symbol_digest"], symbol_digest))])
    binding = host_context["toolchain_binding"]
    try:
        slice_manifest = host_toolchain.derive_akcli_slice(binding, symbol_digest)
    except host_toolchain.HostBindingError as exc:
        raise HostContextError([_host_finding("toolchain slice is not derivable: %s" % exc)]) from exc

    # object_identity_map is NOT a component identity index.  C2 _prepare() L498-504
    # reads it as the declarations of the source objects this round is authorized to
    # REMOVE, keyed by {uuid, kind, descriptor_sha256}.  Component identity belongs to
    # the BEFORE observation; the removal declarations belong to the selected rule.
    # The two have different lifecycles, so this is resolved here -- after rule
    # selection -- and never before it.
    removals = dict(removals or {})
    declared = ((rule or {}).get("object_delta") or {}).get("remove") or []
    declared_slots = [entry["slot"] for entry in declared]
    if declared and not removals:
        raise HostContextError([_host_finding(
            "the selected rule removes %d source object(s); object_identity_map must be "
            "resolved from the current fault bytes, not left empty" % len(declared))])
    if sorted(removals) != sorted(declared_slots):
        raise HostContextError([_host_finding(
            "object_identity_map must bind exactly the selected rule's removal slots: "
            "declared=%s resolved=%s" % (sorted(declared_slots), sorted(removals)))])
    for slot, entry in removals.items():
        _host_closed(entry, ("uuid", "kind", "descriptor_sha256"), "removal %r" % slot)
        _host_sha(entry["descriptor_sha256"], "removal descriptor digest")
        _host_text(entry["uuid"], "removal uuid")
        if entry["kind"] not in ("wire", "label"):
            raise HostContextError([_host_finding(
                "removal %r has unsupported kind %r" % (slot, entry["kind"]))])
    # C2 only consumes values(), so the slot keys carry no weight there.  The binder
    # has to make them mean something: one slot, one object, and no two slots may
    # silently bind the same UUID.
    by_uuid = {}
    for slot, entry in removals.items():
        if entry["uuid"] in by_uuid:
            raise HostContextError([_host_finding(
                "removal slots %r and %r bind the same object %s"
                % (by_uuid[entry["uuid"]], slot, entry["uuid"]))])
        by_uuid[entry["uuid"]] = slot

    pin_identity_map = {}
    embedded_symbol_hashes = {}
    for comp in observation["components"]:
        embedded_symbol_hashes[comp["lib_id"]] = comp["lib_definition_sha256"]
    for row in observation["pins"]:
        ident = row["identity"]
        pin_identity_map["%s.%s" % (ident["reference"], ident["number"])] = ident

    values = {
        "run_id": host_context["run_id"],
        "candidate_id": host_context["candidate_id"],
        "round_id": host_context["round_id"],
        "patch_id": host_context["patch_id"],
        "proposal_sha256": proposal.proposal_sha256,
        "base_file_manifest": observe_candidate_manifest(host_context),
        "base_topology_sha256": topology_sha256(observation),
        "toolchain_manifest": slice_manifest,
        "policy_document_sha256": policy_sha,
        "authority_context": host_context["authority"],
        "approved_rule_ids": sorted(approved),
        "pin_identity_map": pin_identity_map,
        "object_identity_map": removals,
        "embedded_symbol_hashes": embedded_symbol_hashes,
    }
    missing = [field for field in _RUNTIME_BINDING_FIELDS if field not in values]
    if missing:
        raise HostContextError([_host_finding("runtime bindings are incomplete: %s" % missing)])
    return values

def resolve_pin_identity(token, observation):
    """Resolve one REFERENCE.PIN token against the host BEFORE observation.

    Member selection is exact: zero matches or more than one match is a binding
    failure, never a guess.  Nothing here reads the proposal or a fixture.
    """
    text = _host_text(token, "member token")
    reference, separator, number = text.partition(".")
    if not separator or not reference or not number:
        raise HostContextError([_host_finding("invalid member token %r" % text)])
    matches = [row["identity"] for row in observation["pins"]
               if row["identity"]["reference"] == reference
               and row["identity"]["number"] == number]
    if len(matches) != 1:
        raise HostContextError([_host_finding(
            "member token %r resolves to %d pin identities, expected exactly one"
            % (text, len(matches)))])
    return matches[0]


def _member_keys(members):
    return sorted({canonical_json_bytes(identity) for identity in members})


def capture_before_partitions(observation, declarations):
    """Capture the BEFORE partitions a policy rule names, once and completely.

    binding_contract.capture_rule: CAPTURE ENTIRE BEFORE PARTITION ONCE; NO
    REBIND AFTER APPLY.  So a captured slot holds the observed before members, and
    a later stage can never re-derive them from the applied result.
    """
    captured = {}
    partitions = observation["partitions"]
    for declaration in declarations:
        slot = _host_identifier(declaration["slot"], "partition slot")
        if slot in captured:
            raise HostContextError([_host_finding("duplicate partition slot %r" % slot)])
        names = sorted(declaration.get("names_exact") or [])
        if declaration.get("capture_all_members"):
            contains = _member_keys(resolve_pin_identity(token, observation)
                                    for token in declaration.get("contains") or [])
            excludes = _member_keys(resolve_pin_identity(token, observation)
                                    for token in declaration.get("excludes") or [])
            candidates = []
            for partition in partitions:
                observed = _member_keys(partition["members"])
                if sorted(partition["names"]) != names:
                    continue
                if not set(contains) <= set(observed):
                    continue
                if set(excludes) & set(observed):
                    continue
                candidates.append(partition)
            if len(candidates) != 1:
                raise HostContextError([_host_finding(
                    "capture_all_members slot %r matches %d before partitions, expected one"
                    % (slot, len(candidates)))])
            members = sorted(candidates[0]["members"], key=canonical_json_bytes)
        else:
            members = sorted((resolve_pin_identity(token, observation)
                              for token in declaration.get("members_exact") or []),
                             key=canonical_json_bytes)
            matches = [partition for partition in partitions
                       if _member_keys(partition["members"]) == _member_keys(members)
                       and sorted(partition["names"]) == names]
            if len(matches) != 1:
                raise HostContextError([_host_finding(
                    "slot %r members/names match %d before partitions, expected one"
                    % (slot, len(matches)))])
        if not members:
            raise HostContextError([_host_finding("slot %r captured no members" % slot)])
        captured[slot] = {"key": canonical_sha256("topology", members),
                          "names": names, "members": members}
    return captured


def project_expected_partitions(observation, rule, captured, new_pins):
    """Frozen policy transformation: replace the named slots, keep every other
    before partition byte-identical.

    Members come from the CAPTURED before partition plus the rule's exact
    additions; the policy never lets a later stage re-derive them.
    """
    replace = set(rule["after"].get("replace_partitions") or [])
    unknown = replace - set(captured)
    if unknown:
        raise HostContextError([_host_finding(
            "replace_partitions names uncaptured slots %s" % sorted(unknown))])
    replacement = {}
    for entry in rule["after"].get("partitions") or []:
        names = sorted(entry.get("names_exact") or [])
        members = []
        source = entry.get("members_from")
        if source is not None:
            if source not in captured:
                raise HostContextError([_host_finding(
                    "members_from names uncaptured slot %r" % source)])
            members.extend(captured[source]["members"])
        for token in entry.get("members_exact") or []:
            members.append(resolve_pin_identity(token, observation))
        for token in entry.get("add_exact") or []:
            members.append(new_pins.get(token) or resolve_pin_identity(token, observation))
        key = canonical_sha256("topology", sorted(members, key=canonical_json_bytes))
        if key in replacement:
            raise HostContextError([_host_finding("two expected partitions share a member set")])
        replacement[key] = {"key": key, "names": names,
                            "members": sorted(members, key=canonical_json_bytes)}
    kept = [partition for partition in observation["partitions"]
            if not any(name in replace and sorted(partition["names"]) == captured[name]["names"]
                       and _member_keys(partition["members"]) == _member_keys(captured[name]["members"])
                       for name in replace)]
    if len(kept) != len(observation["partitions"]) - len(replace):
        raise HostContextError([_host_finding(
            "replace_partitions does not name whole before partitions")])
    return kept + list(replacement.values())

def selector_source_index(raw_bytes):
    """Rebuild the geometry a removal selector needs from the SAME candidate bytes.

    C2's full observer validates the input first, so this index can only ever
    describe bytes inside the qualified M2 subset.  Pin anchors come from C2's own
    _source_components(); this layer must never fork or reinterpret that geometry.
    """
    try:
        observation = _c2_observe_source(raw_bytes)
        root = _c2_source_ast(raw_bytes)
        sheet = "/" + _c2_source_value(root, "uuid")
        _components, _pins, positions = _c2_source_components(root, sheet)
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise HostContextError([_host_finding(
            "the candidate bytes are outside the qualified source subset: %s" % exc)]) from exc

    pin_anchor = {}
    for point, items in positions.items():
        for item in items:
            pin_anchor[canonical_json_bytes(item["identity"])] = point

    labels = []
    for node in _c2_source_children(root, "label"):
        point, _rotation = _c2_source_at(node)
        labels.append({"uuid": _c2_source_value(node, "uuid"),
                       "name": _c2_source_text(node[1]), "point": point, "node": node})
    wires = []
    for node in _c2_source_children(root, "wire"):
        pts = _c2_source_one(node, "pts")
        start, end = [tuple(_c2_source_integer(value, 1000000) for value in item[1:])
                      for item in pts[1:]]
        # A wire's identity does not depend on which endpoint is drawn first.
        wires.append({"uuid": _c2_source_value(node, "uuid"),
                      "endpoints": frozenset((start, end)), "node": node})
    return {"observation": observation, "pin_anchor": pin_anchor,
            "labels": labels, "wires": wires,
            "objects": {obj["identity"]: obj for obj in observation["source_objects"]}}


def _selector_finding(status, code, detail):
    return status, _finding(code, detail)


def resolve_removal_selector(index, selector):
    """Resolve one policy removal selector to its unique source object.

    The chain is: policy selector -> C2 AST over the current bytes -> one UUID ->
    the same UUID in the BEFORE observation -> the frozen descriptor digest.  The
    digest is taken from what C2/C4 already observed, never re-invented here.
    """
    kind = selector.get("kind")
    if kind not in ("label", "wire"):
        return _selector_finding("BLOCKED", REASON_SCHEMA_INVALID,
                                 "unsupported removal selector kind %r" % kind)
    if kind == "label":
        if selector.get("scope") != "local":
            return _selector_finding("BLOCKED", REASON_SCHEMA_INVALID,
                                     "only root-local label selectors are supported")
        try:
            identity = resolve_pin_identity(selector.get("at_pin"), index["observation"])
        except HostContextError as exc:
            return _selector_finding("BLOCKED", REASON_SCHEMA_INVALID,
                                     "invalid at_pin selector: %s" % exc.findings[0].detail)
        anchor = index["pin_anchor"].get(canonical_json_bytes(identity))
        if anchor is None:
            return _selector_finding("UNKNOWN", REASON_COVERAGE_INCOMPLETE,
                                     "the pinned pin has no observed anchor")
        matches = [row for row in index["labels"]
                   if row["name"] == selector.get("name") and row["point"] == anchor]
        detail = "local label %r at %s" % (selector.get("name"), selector.get("at_pin"))
    else:
        endpoints = selector.get("endpoints_nm")
        if not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2:
            return _selector_finding("BLOCKED", REASON_SCHEMA_INVALID,
                                     "a wire selector needs exactly two endpoints_nm")
        wanted = frozenset(tuple(int(value) for value in point) for point in endpoints)
        matches = [row for row in index["wires"] if row["endpoints"] == wanted]
        detail = "wire %s" % sorted(sorted(point) for point in wanted)

    if not matches:
        # The source observation and the AST are both complete here; what failed is
        # that the CURRENT fault bytes can no longer be bound to the object the frozen
        # selector requires.  That is input drift (status stays UNKNOWN, per
        # policy defaults.unresolved_binding), not incomplete coverage.
        return _selector_finding("UNKNOWN", REASON_INPUT_DRIFT,
                                 "%s matches no source object in the current bytes" % detail)
    if len(matches) > 1:
        return _selector_finding("UNKNOWN", REASON_SELECTOR_AMBIGUOUS,
                                 "%s matches %d source objects" % (detail, len(matches)))
    matched = matches[0]
    observed = index["objects"].get(matched["uuid"])
    if observed is None or observed["kind"] != kind:
        return _selector_finding("UNKNOWN", REASON_PARSER_DISAGREEMENT,
                                 "%s resolved to %s, which the BEFORE observation does not "
                                 "carry as a %s" % (detail, matched["uuid"], kind))
    if observed["descriptor"]["ast"] != matched["node"]:
        return _selector_finding("UNKNOWN", REASON_PARSER_DISAGREEMENT,
                                 "%s: the selector AST and the observed descriptor disagree"
                                 % detail)
    # C2 _prepare() requires canonical_sha256("protected", obj["descriptor"]), i.e. the
    # digest of {"ast": node} -- NOT semantic_ast_sha256, which is the digest of the
    # bare node.  hash(node) != hash({"ast": node}); the two are different domains.
    return "PASS", {"uuid": matched["uuid"], "kind": kind,
                    "descriptor_sha256": canonical_sha256("protected",
                                                          observed["descriptor"])}


def resolve_removals(index, selectors):
    """Resolve every removal selector; the first failure decides the outcome.

    Selector failures are deliberately NOT collapsed into one class: not being able
    to determine identity is UNKNOWN, while an illegal selector field is BLOCKED.
    """
    declarations = {}
    for selector in selectors:
        slot = _host_identifier(selector["slot"], "removal slot")
        if slot in declarations:
            return "BLOCKED", None, [_finding(REASON_SCHEMA_INVALID,
                                              "duplicate removal slot %r" % slot)]
        status, payload = resolve_removal_selector(index, selector)
        if status != "PASS":
            return status, None, [payload]
        declarations[slot] = payload
    return "PASS", declarations, []

def validate_captured_partitions(captured, rule):
    """C5 freezes the capture invariants; C2 only checks that this is a mapping.

    captured_partitions is a capture-once AUDIT record, not a selector cache that a
    later stage may rebind: the slot set, the names, the members and the partition
    key all have to be re-derivable from what was observed BEFORE the write.
    """
    declared = [entry["slot"] for entry in (rule.get("before") or {}).get("partitions") or []]
    if sorted(captured) != sorted(declared):
        raise HostContextError([_host_finding(
            "captured slot set must equal the rule's before.partitions slots: "
            "declared=%s captured=%s" % (sorted(declared), sorted(captured)))])
    for slot, entry in captured.items():
        _host_closed(entry, ("key", "names", "members"), "captured partition %r" % slot)
        members = entry["members"]
        if not members:
            raise HostContextError([_host_finding(
                "captured partition %r holds no members" % slot)])
        if entry["names"] != sorted(entry["names"]):
            raise HostContextError([_host_finding(
                "captured partition %r names are not canonically ordered" % slot)])
        if entry["key"] != canonical_sha256("topology",
                                            sorted(members, key=canonical_json_bytes)):
            raise HostContextError([_host_finding(
                "captured partition %r key is not the digest of its members" % slot)])
    return captured


def _feedback_reason(outcome: str, receipt: Mapping) -> str:
    if outcome in (OUTCOME_APPLIED, OUTCOME_NO_CHANGE, OUTCOME_REFUSED):
        return "OK"
    if outcome == OUTCOME_UNAVAILABLE:
        return "EXECUTION_UNAVAILABLE"
    mapped = set()
    for finding in receipt.get("reasons") or []:
        code = finding.get("code") if isinstance(finding, Mapping) else None
        public = PUBLIC_REASON_BY_CODE.get(code)
        if public:
            mapped.add(public)
    for candidate in REJECT_REASON_PRIORITY:
        if candidate in mapped:
            return candidate
    return "EXECUTION_UNAVAILABLE"

# ===========================================================================
# PR1-C5 S1b step 4 -- expected engineering semantics (checkpoint 1)
# ===========================================================================
#
# Compatibility semantics for pinned akcli-kicad 0.21.0.
#
# The kernel below replicates the geometry of the pinned writer
# (akcli/geometry/transform.py:65-142, upstream commit
# 68c2df5e43db2f822ab8dbfea36f777396897d8d).  It is a behavioural replica,
# never a runtime dependency: the production path must not import akcli,
# because the main suite runs on an interpreter without the pinned toolchain.
#
# It is qualified for akcli-kicad 0.21.0 ONLY.  Do not generalize it to another
# toolchain version without re-qualifying it against that version's geometry and
# native observations.

PINNED_AKCLI_VERSION = "0.21.0"
_PINNED_PIN_DIR = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}


def _pinned_akcli_0210_transform_point(pt, rot=0, mirror="none", origin=(0, 0)):
    """akcli 0.21.0 transform_point: rotate-then-mirror, integer nm, +Y down."""
    x = int(pt[0])
    y = int(pt[1])
    r = int(rot) % 360
    if r == 0:
        pass
    elif r == 90:
        x, y = y, -x
    elif r == 180:
        x, y = -x, -y
    elif r == 270:
        x, y = -y, x
    else:
        raise HostContextError([_host_finding(
            "unsupported component rotation %r" % (rot,))])
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    elif mirror not in ("none", "", None):
        raise HostContextError([_host_finding(
            "unsupported component mirror %r" % (mirror,))])
    return (x + int(origin[0]), y + int(origin[1]))


def _pinned_akcli_0210_pin_world(pin_local_nm_yup, rot=0, mirror="none", origin=(0, 0)):
    """akcli 0.21.0 pin_world: library +Y-up local nm -> world nm (+Y down)."""
    local = (int(pin_local_nm_yup[0]), -int(pin_local_nm_yup[1]))
    return _pinned_akcli_0210_transform_point(local, rot, mirror, origin)


def _pinned_akcli_0210_label_angle_away(pin_orientation, rot=0, mirror="none"):
    """akcli 0.21.0 label_angle_away: the angle whose text leaves the body."""
    dx, dy = _PINNED_PIN_DIR.get(int(pin_orientation) % 360, (1, 0))
    wx, wy = _pinned_akcli_0210_transform_point((-dx, dy), rot, mirror)
    if wx > 0:
        return 0
    if wx < 0:
        return 180
    return 90 if wy < 0 else 270


def _lib_symbols_ast(observation):
    """The BEFORE observation's single lib_symbols AST (C2 source semantics)."""
    matches = [obj for obj in observation["source_objects"]
               if isinstance(obj, Mapping) and obj.get("kind") == "lib_symbols"]
    if len(matches) != 1:
        raise HostContextError([_host_finding(
            "the BEFORE observation must carry exactly one lib_symbols source "
            "object, found %d" % len(matches))])
    descriptor = matches[0].get("descriptor")
    if not isinstance(descriptor, Mapping) or "ast" not in descriptor:
        raise HostContextError([_host_finding("lib_symbols carries no source AST")])
    return descriptor["ast"]


def _source_scalar_string(node, name):
    """Quoted text of a scalar child, read with C2's own semantics."""
    child = _c2_source_one(node, name)
    if len(child) < 2:
        raise HostContextError([_host_finding("invalid %s scalar" % name)])
    return _c2_source_text(child[1])


def _pin_node(lib_symbols, lib_id, pin_number):
    """The unique library pin node for (lib_id, pin_number).

    A KiCad symbol keeps its pins inside unit sub-symbols such as
    '(symbol "R_1_1" ...)', so the search descends exactly one nesting level.
    A missing or duplicated definition is a binding failure, never a guess.
    """
    symbols = [node for node in _c2_source_children(lib_symbols, "symbol")
               if len(node) >= 2 and isinstance(node[1], dict)
               and node[1].get("string") == lib_id]
    if len(symbols) != 1:
        raise HostContextError([_host_finding(
            "library symbol %r resolves to %d definitions, expected exactly one"
            % (lib_id, len(symbols)))])
    matches = []
    for unit in _c2_source_children(symbols[0], "symbol"):
        for pin in _c2_source_children(unit, "pin"):
            if _source_scalar_string(pin, "number") == pin_number:
                matches.append(pin)
    if len(matches) != 1:
        raise HostContextError([_host_finding(
            "pin %s.%s resolves to %d library definitions, expected exactly one"
            % (lib_id, pin_number, len(matches)))])
    return matches[0]


def _pin_local_geometry(lib_symbols, lib_id, pin_number):
    """(local_nm_yup, orientation) of one library pin (see _pin_node)."""
    return _c2_source_at(_pin_node(lib_symbols, lib_id, pin_number))


def _pin_electrical_type(pin_node):
    """The pin's electrical type token, read exactly as the reader reports it."""
    if len(pin_node) < 2 or not isinstance(pin_node[1], str):
        raise HostContextError([_host_finding("library pin lacks an electrical type")])
    return pin_node[1]


def _library_definition_digests(observation, lib_id):
    """The unanimous library definition digests for one lib_id.

    Every existing component of that lib_id must report the same
    lib_definition_sha256 and pin_definition_sha256: the definition belongs to
    the embedded library, not to an instance, so a disagreement means the
    observation is internally inconsistent.  No instance, or a disagreement, is
    a binding failure -- never a first-match guess.
    """
    rows = [row for row in observation["components"] if row["lib_id"] == lib_id]
    if not rows:
        raise HostContextError([_host_finding(
            "the BEFORE observation carries no %r component, so the library "
            "definition digests of a new %r cannot be established" % (lib_id, lib_id))])
    lib_digests = {row["lib_definition_sha256"] for row in rows}
    pin_digests = {row["pin_definition_sha256"] for row in rows}
    if len(lib_digests) != 1 or len(pin_digests) != 1:
        raise HostContextError([_host_finding(
            "existing %r components disagree on their library definition digests "
            "(%d lib, %d pin)" % (lib_id, len(lib_digests), len(pin_digests)))])
    return lib_digests.pop(), pin_digests.pop()


def _anchor_component(observation, proposal, reference):
    """(lib_id, rotation, mirror, origin_nm) for a label anchor's owner.

    The owner is either a component that already exists in the BEFORE
    observation or one placed by this very proposal (DC-04's R9 and DC-05's C5
    are both new).  No match, several matches, a multi-unit part or a second
    placement of the same reference are all binding failures.
    """
    existing = [row for row in observation["components"] if row["reference"] == reference]
    if len(existing) > 1:
        raise HostContextError([_host_finding(
            "reference %r appears %d times in the BEFORE observation"
            % (reference, len(existing)))])
    if existing:
        row = existing[0]
        if int(row.get("unit", 1)) != 1:
            raise HostContextError([_host_finding(
                "reference %r is a multi-unit part; v1 binds unit 1 only" % reference)])
        return (row["lib_id"], int(row["rotation"]), str(row["mirror"]),
                tuple(int(value) for value in row["position_nm"]))
    placements = [op for op in proposal.ops
                  if op["op"] == "place_component" and op["designator"] == reference]
    if len(placements) != 1:
        raise HostContextError([_host_finding(
            "label anchor %r is neither an existing component nor exactly one "
            "place_component in this proposal (placements=%d)"
            % (reference, len(placements)))])
    op = placements[0]
    origin = (int(op["x_mil"]) * 25400, int(op["y_mil"]) * 25400)
    return op["lib_id"], int(op["rotation"]), str(op["mirror"]), origin


def build_expected_after(observation, proposal, rule=None, runtime=None):
    """Pure: the expected engineering semantics this round may create.

    observation is the host native BEFORE read.  Every label geometry is derived
    live from the observation's library AST plus the owning component's
    placement -- never from a static policy default and never from a hard-coded
    angle.  The pinned writer branches on the presence of rotation, so an
    omitted rotation means derive-from-pin while an explicit 0 stays 0; the two
    produce different semantics and are reported as such.

    rule and runtime are carried so the policy layer can bind the result, and
    are deliberately NOT used as a source of geometry: copying a rotation
    default out of the static policy is exactly the defect this checkpoint
    exists to prevent.
    """
    lib_symbols = _lib_symbols_ast(observation)
    additions = {"version": 1, "new_components": [], "new_labels": []}
    roles = set()
    slot = 0
    for op in proposal.ops:
        if op["op"] == "place_component":
            role = "new:" + op["designator"]
            if role in roles:
                raise HostContextError([_host_finding(
                    "duplicate new component role %r" % role)])
            roles.add(role)
            additions["new_components"].append({
                "role": role, "reference": op["designator"], "lib_id": op["lib_id"],
                "position_nm": [int(op["x_mil"]) * 25400, int(op["y_mil"]) * 25400],
                "rotation": int(op["rotation"]), "mirror": str(op["mirror"]),
                "unit": int(op["unit"]),
            })
        elif op["op"] == "add_net_label":
            reference, separator, pin_number = op["at"].partition(".")
            if not separator:
                raise HostContextError([_host_finding(
                    "label anchor %r is not a REF.PIN token" % op["at"])])
            lib_id, rot, mirror, origin = _anchor_component(observation, proposal, reference)
            local, orientation = _pin_local_geometry(lib_symbols, lib_id, pin_number)
            point = _pinned_akcli_0210_pin_world(local, rot, mirror, origin)
            if "rotation" in op:
                angle = int(op["rotation"])
                source = "explicit"
            else:
                angle = _pinned_akcli_0210_label_angle_away(orientation, rot, mirror)
                source = "derived"
            additions["new_labels"].append({
                "slot": slot, "role": "new:label:%d" % slot,
                "name": op["name"], "anchor": op["at"],
                "owner": reference, "lib_id": lib_id, "pin_number": pin_number,
                "point_nm": [point[0], point[1]], "rotation": angle,
                "rotation_source": source,
            })
            slot += 1
    additions["new_labels"].sort(key=lambda row: row["slot"])
    return additions

# ---------------------------------------------------------------------------
# PR1-C5 S1b step 4 -- policy specialization (checkpoint 2)
# ---------------------------------------------------------------------------
#
# _bound_policy answers exactly one question: if this round is authorized, what
# precisely may change?  It performs NO authorization -- no policy port
# evaluation, no TOOL_EXECUTE/FILE_WRITE decision, no ledger lookup, no default
# allow.  Those belong to bind_policy().
#
# It consumes two single sources of truth and re-derives neither: the runtime
# bindings (the only runtime-value source) and build_expected_after (the only
# source of new label geometry).

# The expected AFTER bytes do not exist yet, so an expectation cannot carry their
# hash.  C2 excludes source_sha256 from the electrical topology, so a fixed
# placeholder is the honest value; it is never compared with applied bytes.
# C2 erratum section 10 freezes the exact sentinel for the not-yet-written
# expected AFTER bytes.  It is a STRUCTURAL PLACEHOLDER ONLY: it must never be
# compared with the BEFORE hash, with a staged/AFTER hash, or used in a commit
# byte-equality predicate.  The only fact source for real AFTER bytes is C4's
# fresh native_after plus C3's fresh staged read.
_EXPECTED_SOURCE_SHA256 = canonical_sha256(
    "context", {"role": "EXPECTED_AFTER_NOT_YET_WRITTEN"})


def _refresh_expected_bookkeeping(observation):
    """Recompute partition keys, per-pin partition_key and coverage.

    The expectation is a complete observation, so its bookkeeping must be
    internally consistent before C2 ever normalizes it.  Every pin must belong to
    exactly one partition.
    """
    for partition in observation["partitions"]:
        members = sorted(partition["members"], key=canonical_json_bytes)
        partition["members"] = members
        partition["key"] = canonical_sha256("topology", members)
    owner = {}
    for partition in observation["partitions"]:
        for member in partition["members"]:
            key = canonical_json_bytes(member)
            if key in owner:
                raise HostContextError([_host_finding(
                    "an expected pin appears in two partitions")])
            owner[key] = partition["key"]
    for row in observation["pins"]:
        key = owner.get(canonical_json_bytes(row["identity"]))
        if key is None:
            raise HostContextError([_host_finding(
                "an expected pin belongs to no partition")])
        row["partition_key"] = key
    pin_ids = sorted([row["identity"] for row in observation["pins"]],
                     key=canonical_json_bytes)
    comp_ids = sorted([row["identity"] for row in observation["components"]],
                      key=canonical_json_bytes)
    observation["coverage"] = {
        "expected_pin_keys_sha256": canonical_sha256("topology", pin_ids),
        "observed_pin_keys_sha256": canonical_sha256("topology", pin_ids),
        "expected_component_keys_sha256": canonical_sha256("topology", comp_ids),
        "observed_component_keys_sha256": canonical_sha256("topology", comp_ids),
        "expected_pin_count": len(pin_ids),
        "observed_pin_count": len(pin_ids),
        "complete": True,
    }
    return observation


def _expected_observation(observation, rule, runtime, additions):
    """Materialize the full expected observation from the CP1 additions.

    This does not recompute any label geometry: it wraps the single CP1 result
    into the observation shape C2 verifies.  New component rows take their
    library definition digests from the unanimous same-lib_id instance set, their
    assembly booleans from the frozen rule, and everything else from the
    placement op; new label semantics are the exact C2 four-tuple.

    Returns (expected_observation, captured_partitions).
    """
    expected = copy.deepcopy(observation)
    expected["source_sha256"] = _EXPECTED_SOURCE_SHA256
    # object_identity_map is slot -> {uuid, kind, descriptor_sha256}; C2 consumes
    # its VALUES and matches entry["uuid"] against a source-object identity.  Every
    # declaration must bind exactly one BEFORE object whose kind and descriptor
    # digest agree, and every declaration must actually remove something -- a
    # declared removal that removes nothing is a binding failure, not a no-op.
    removed_ids = set()
    for slot, entry in sorted(runtime["object_identity_map"].items()):
        matches = [obj for obj in expected["source_objects"]
                   if obj["identity"] == entry["uuid"]]
        if len(matches) != 1:
            raise HostContextError([_host_finding(
                "removal %r names %s, which matches %d source objects in the BEFORE "
                "observation, expected exactly one" % (slot, entry["uuid"], len(matches)))])
        obj = matches[0]
        if obj["kind"] != entry["kind"]:
            raise HostContextError([_host_finding(
                "removal %r declares kind %r but %s is a %r"
                % (slot, entry["kind"], entry["uuid"], obj["kind"]))])
        digest = canonical_sha256("protected", obj["descriptor"])
        if digest != entry["descriptor_sha256"]:
            raise HostContextError([_host_finding(
                "removal %r descriptor digest does not match the observed object" % slot)])
        if obj["identity"] in removed_ids:
            raise HostContextError([_host_finding(
                "two removal declarations bind the same source object %s" % obj["identity"])])
        removed_ids.add(obj["identity"])
    expected["source_objects"] = [obj for obj in expected["source_objects"]
                                  if obj["identity"] not in removed_ids]
    if not observation["components"]:
        raise HostContextError([_host_finding(
            "the BEFORE observation carries no component, so a new component "
            "cannot inherit its sheet path")])
    sheet_path = observation["components"][0]["identity"]["sheet_path"]
    lib_symbols = _lib_symbols_ast(observation)
    declared = {row["reference"]: row
                for row in (rule.get("after") or {}).get("add_components") or []}
    new_pins = {}
    for row in additions["new_components"]:
        reference = row["reference"]
        declaration = declared.get(reference)
        if declaration is None:
            raise HostContextError([_host_finding(
                "the frozen rule does not declare the new component %r" % reference)])
        lib_digest, pin_digest = _library_definition_digests(observation, row["lib_id"])
        identity = {"sheet_path": sheet_path, "component_uuid": row["role"],
                    "reference": reference, "unit": row["unit"]}
        expected["components"].append({
            "identity": identity, "reference": reference, "lib_id": row["lib_id"],
            "lib_definition_sha256": lib_digest, "value": declaration["value"],
            "footprint": declaration["footprint"], "unit": row["unit"],
            "position_nm": [row["position_nm"][0], row["position_nm"][1]],
            "rotation": row["rotation"], "mirror": row["mirror"],
            "dnp": declaration["dnp"], "in_bom": declaration["in_bom"],
            "on_board": declaration["on_board"],
            "pin_definition_sha256": pin_digest})
        for number in ("1", "2"):
            pin_node = _pin_node(lib_symbols, row["lib_id"], number)
            pin_identity = {"sheet_path": sheet_path, "component_uuid": row["role"],
                            "reference": reference, "unit": row["unit"],
                            "number": number,
                            "pin_uuid": "new:%s.%s" % (reference, number)}
            expected["pins"].append({
                "identity": pin_identity, "name": _source_scalar_string(pin_node, "name"),
                "electrical_type": _pin_electrical_type(pin_node),
                "no_connect": False, "partition_key": ""})
            new_pins["%s.%s" % (reference, number)] = pin_identity
        expected["source_objects"].append({
            "identity": row["role"], "kind": "symbol",
            "semantics": {"reference": reference}})
    for label in additions["new_labels"]:
        expected["source_objects"].append({
            "identity": label["role"], "kind": "label",
            "semantics": {"name": label["name"], "scope": "local",
                          "point_nm": [label["point_nm"][0], label["point_nm"][1]],
                          "rotation": label["rotation"]}})
    captured = capture_before_partitions(
        observation, (rule.get("before") or {}).get("partitions") or [])
    expected["partitions"] = project_expected_partitions(
        observation, rule, captured, new_pins)
    return _refresh_expected_bookkeeping(expected), captured


def _canonical_authorized_ops(rule, runtime):
    """The ordered op-list this round is authorized to execute.

    Frozen order: remove -> add_components -> add_labels.  Every op is built by
    running the frozen rule's declaration through C1's own parser, so the
    canonical shape cannot drift from what the proposal parser produces.

    The label ops are built WITHOUT the rotation key on purpose.  The pinned
    writer branches on that key's presence, so the policy's expected semantic
    rotation must never be translated into an explicit rotation:0 that the
    proposer did not write.  Presence sensitivity is what keeps the C4/C1
    rotation binding intact at the C5 layer.
    """
    delta = rule.get("object_delta") or {}
    removals = runtime["object_identity_map"]
    ops = []
    try:
        for declaration in delta.get("remove") or []:
            slot = declaration["slot"]
            entry = removals.get(slot)
            if entry is None:
                raise HostContextError([_host_finding(
                    "removal slot %r has no resolved object binding" % slot)])
            ops.append(_parse_op({"op": "delete_object", "uuid": entry["uuid"]}, "$.ops"))
        for row in (rule.get("after") or {}).get("add_components") or []:
            position = row["position_mil"]
            ops.append(_parse_op({
                "op": "place_component", "lib_id": row["lib_id"],
                "designator": row["reference"], "x_mil": position[0],
                "y_mil": position[1], "value": row["value"],
                "footprint": row["footprint"]}, "$.ops"))
        for row in delta.get("add_labels") or []:
            ops.append(_parse_op({"op": "add_net_label", "name": row["name"],
                                  "at": row["at_pin"]}, "$.ops"))
    except ProposalInvalidError as exc:
        raise HostContextError([_host_finding(
            "the frozen rule cannot be projected into an authorized op-list: %s" % exc)])
    return ops


def _operation_constraints(rule, runtime, additions):
    """The transaction's operation snapshot.

    Holds the counts, the exactly resolved removal objects, the new component and
    label attributes, the frozen stage order and the canonical authorized op-list.
    It is a snapshot, never a lazy binding: the later comparison against the
    proposal happens in bind_policy, not here.
    """
    delta = rule.get("object_delta") or {}
    removals = runtime["object_identity_map"]
    removed = []
    for declaration in delta.get("remove") or []:
        entry = removals.get(declaration["slot"])
        if entry is None:
            raise HostContextError([_host_finding(
                "removal slot %r has no resolved object binding" % declaration["slot"])])
        removed.append({"slot": declaration["slot"], "uuid": entry["uuid"],
                        "kind": entry["kind"],
                        "descriptor_sha256": entry["descriptor_sha256"]})
    components = []
    for row in (rule.get("after") or {}).get("add_components") or []:
        components.append({"reference": row["reference"], "lib_id": row["lib_id"],
                           "value": row["value"], "footprint": row["footprint"],
                           "position_mil": list(row["position_mil"]),
                           "rotation": row["rotation"], "mirror": row["mirror"],
                           "unit": row["unit"]})
    labels = []
    for row in delta.get("add_labels") or []:
        labels.append({"name": row["name"], "at_pin": row["at_pin"],
                       "scope": row.get("scope", "local"), "rotation_key": "ABSENT"})
    ops = _canonical_authorized_ops(rule, runtime)
    # The snapshot and the CP1 semantics must describe the same round.
    if (len(components) != len(additions["new_components"])
            or len(labels) != len(additions["new_labels"])):
        raise HostContextError([_host_finding(
            "the authorized op snapshot and the expected additions disagree")])
    return {
        "counts": {"delete_object": len(removed), "place_component": len(components),
                   "add_net_label": len(labels)},
        "removed": removed,
        "new_components": components,
        "new_labels": labels,
        "stage_order": ["delete_object", "place_component", "add_net_label"],
        "canonical_authorized_ops": ops,
    }


def _bound_policy(observation, rule, runtime, additions, route):
    """Specialize the frozen policy for this transaction (no authorization).

    Consumes the runtime bindings as the only runtime-value source and the CP1
    additions as the only source of new label geometry.  The transaction identity
    (run / candidate / round / patch / proposal_sha256) stays in the runtime
    bindings and is bound by the HostPatch, never here.
    """
    if not isinstance(runtime, Mapping):
        raise HostContextError([_host_finding("runtime bindings must be a mapping")])
    unknown = sorted(set(runtime) - set(_RUNTIME_BINDING_FIELDS))
    if unknown:
        raise HostContextError([_host_finding(
            "runtime bindings carry fields outside the frozen set: %s"
            % ", ".join(unknown))])
    missing = sorted(field for field in _RUNTIME_BINDING_FIELDS if field not in runtime)
    if missing:
        raise HostContextError([_host_finding(
            "runtime bindings are incomplete: %s" % ", ".join(missing))])
    if route not in (ROUTE_STRICT, ROUTE_EXCEPTION):
        raise HostContextError([_host_finding("unsupported route %r" % (route,))])
    expected, captured = _expected_observation(observation, rule, runtime, additions)
    normalized = normalize_observation(expected, expected=True)
    authorized = observation_delta(normalize_observation(observation), normalized,
                                   expected=True)
    roles = {"new:" + row["reference"]: {"reference": row["reference"],
                                         "pin_numbers": ["1", "2"]}
             for row in additions["new_components"]}
    bound = {
        "version": 1,
        "rule_id": rule["id"],
        "route": route,
        "policy_file_sha256": runtime["policy_document_sha256"],
        "authority_context_digest": runtime["authority_context"]["context_digest"],
        "before_source_sha256": observation["source_sha256"],
        "before_topology_sha256": runtime["base_topology_sha256"],
        "pin_identity_map": runtime["pin_identity_map"],
        "object_identity_map": runtime["object_identity_map"],
        "captured_partitions": captured,
        "new_component_roles": roles,
        "expected_after": expected,
        "authorized_delta": authorized,
        "authorized_delta_sha256": canonical_sha256("delta", authorized),
        "protected_projection_sha256": None,
        "operation_constraints": _operation_constraints(rule, runtime, additions),
    }
    bound["protected_projection_sha256"] = protected_projection_sha256(observation, bound)
    if set(bound) != set(_C2_BOUND_FIELDS):
        raise HostContextError([_host_finding(
            "the specialized policy does not match the frozen bound-policy field set")])
    return bound


# The frozen HostPatch field set.  Mirrors src/repair/patch_schema_v1.json
# #/$defs/HostPatch and tools/akcli_adapter.py::_HOST_PATCH_FIELDS; it is restated
# here so CP3 can prove the shape it assembles before C4 ever sees it.  The
# schema itself stays read-only (C5 must not edit the contract it implements).
_HOST_PATCH_FIELDS = frozenset({
    "schema_version", "run_id", "candidate_id", "round_id", "patch_id", "context_id",
    "proposal", "proposal_sha256", "target", "base", "policy", "authority",
    "toolchain_manifest", "toolchain_sha256", "route", "bound_policy", "patch_sha256",
})
# The schema's three-field authority view, and the decision row it carries.
_HOST_PATCH_AUTHORITY_FIELDS = ("context_digest", "resolved_authorization_refs",
                                "decisions")
_AUTHORITY_DECISION_FIELDS = ("capability", "effect")


def _host_patch(host_context, proposal, runtime, bound_policy, policy):
    """Assemble the HostPatch: the transaction envelope C4 stages (no authorization).

    CP3 CONSTRUCTS ONLY.  It copies what the host already resolved -- the
    transaction identity, the candidate byte manifest, the toolchain slice and
    the authority context -- binds the CP2 BoundPolicy to it, and stops.  It
    never evaluates a policy port, never looks up a grant, never consults a
    ledger and never decides whether a stage may run: `authority` is carried
    from the host-resolved runtime bindings, so the decision stays exactly where
    the host already made it, and the toolchain identity enters as metadata that
    CP4 re-derives and cross-checks before it may act.

    The runtime bindings are the only runtime-value source, exactly as in CP2.
    Re-observing the candidate here would create a second truth source, and
    reading any transaction fact from the proposal would let a candidate inject
    its own identity -- the frozen schema forbids merging proposal fields in.

    POLICY IDENTITY (Owner decision, 2026-09-27): `policy.id` is read from the
    loaded policy document, never from the proposal and never from a free
    argument.  C4 only checks that `policy.id` is a well-formed identifier, so
    nothing downstream would catch a policy id that disagrees with the policy
    digest; deriving it here and re-deriving the digest from the same document
    closes that gap.  `policy_id` is itself inside the hashed bytes, so one
    digest can only ever carry one policy identity.
    """
    if not isinstance(policy, Mapping):
        raise HostContextError([_host_finding("the policy document must be a mapping")])
    policy_sha = _policy_document_sha256(policy)
    if policy_sha != runtime["policy_document_sha256"]:
        raise HostContextError([_host_finding(
            "the policy document does not match this transaction's policy digest")])
    policy_id = _host_text(policy.get("policy_id"), "policy id")
    if runtime["policy_document_sha256"] == policy_sha:
        # the digest already binds policy_id; re-assert so a document whose id
        # was stripped or altered after hashing cannot be carried silently.
        if canonical_sha256("policy-bound", dict(policy)) != policy_sha:
            raise HostContextError([_host_finding(
                "the policy document does not match its own digest")])
    if not isinstance(bound_policy, Mapping):
        raise HostContextError([_host_finding("the bound policy must be a mapping")])
    if set(bound_policy) != set(_C2_BOUND_FIELDS):
        raise HostContextError([_host_finding(
            "the host patch may only carry a bound policy from the frozen field set")])
    unknown = sorted(set(runtime) - set(_RUNTIME_BINDING_FIELDS))
    missing = sorted(field for field in _RUNTIME_BINDING_FIELDS if field not in runtime)
    if unknown or missing:
        raise HostContextError([_host_finding(
            "the host patch runtime bindings are not the frozen set "
            "(unknown=%s missing=%s)" % (", ".join(unknown) or "none",
                                         ", ".join(missing) or "none"))])
    # The BoundPolicy must be THIS transaction's, not a foreign or stale one.
    for label, actual, expected in (
            ("policy digest", bound_policy["policy_file_sha256"],
             runtime["policy_document_sha256"]),
            ("authority context", bound_policy["authority_context_digest"],
             runtime["authority_context"]["context_digest"]),
            ("before topology", bound_policy["before_topology_sha256"],
             runtime["base_topology_sha256"])):
        if actual != expected:
            raise HostContextError([_host_finding(
                "the bound policy does not carry this transaction's %s" % label)])
    if bound_policy["rule_id"] not in runtime["approved_rule_ids"]:
        raise HostContextError([_host_finding(
            "the bound rule %r is not among the host-approved rule ids"
            % bound_policy["rule_id"])])
    # The authority block is HOST-resolved and carried, never decided here.
    # `_host_closed` proves no extra capability or decision could ride along; the
    # host's `approvals` stay in the host context and are deliberately NOT
    # re-exported, so the patch cannot be read as carrying an approval surface.
    authority = _host_closed(runtime["authority_context"],
                             _AUTHORITY_FIELDS, "host authority")
    references = authority["resolved_authorization_refs"]
    if not isinstance(references, list) or not references or any(
            not isinstance(item, str) or not item for item in references):
        raise HostContextError([_host_finding(
            "the host authority carries no resolved authorization reference")])
    decisions = authority["decisions"]
    if not isinstance(decisions, list) or any(
            not isinstance(row, Mapping) for row in decisions):
        raise HostContextError([_host_finding(
            "the host authority decisions must be a list of mappings")])
    for row in decisions:
        _host_closed(row, _AUTHORITY_DECISION_FIELDS, "authority decision")
    authority_view = {
        "context_digest": authority["context_digest"],
        "resolved_authorization_refs": list(references),
        "decisions": [{key: row[key] for key in _AUTHORITY_DECISION_FIELDS}
                      for row in decisions],
    }
    toolchain = runtime["toolchain_manifest"]
    patch = {
        "schema_version": SCHEMA_VERSION,
        "run_id": runtime["run_id"],
        "candidate_id": runtime["candidate_id"],
        "round_id": runtime["round_id"],
        "patch_id": runtime["patch_id"],
        "context_id": host_context["context_id"],
        "proposal": proposal.to_dict(),
        "proposal_sha256": runtime["proposal_sha256"],
        "target": host_context["target"],
        "base": {"files": runtime["base_file_manifest"],
                 "topology_sha256": runtime["base_topology_sha256"]},
        "policy": {
            "id": policy_id,
            "file_sha256": runtime["policy_document_sha256"],
            "bound_rule_id": bound_policy["rule_id"],
            "bound_policy_sha256": canonical_sha256("policy-bound", bound_policy),
        },
        "authority": authority_view,
        "toolchain_manifest": toolchain,
        "toolchain_sha256": host_toolchain.toolchain_slice_sha256(toolchain),
        "route": bound_policy["route"],
        "bound_policy": bound_policy,
    }
    if set(patch) | {"patch_sha256"} != set(_HOST_PATCH_FIELDS):
        raise HostContextError([_host_finding(
            "the assembled host patch does not match the frozen field set")])
    if set(patch["authority"]) != set(_HOST_PATCH_AUTHORITY_FIELDS):
        raise HostContextError([_host_finding(
            "the host patch authority view does not match the frozen field set")])
    if patch["proposal"]["context_id"] != patch["context_id"]:
        raise HostContextError([_host_finding(
            "the proposal context does not match the host context")])
    if patch["proposal"]["target"] != patch["target"]:
        raise HostContextError([_host_finding(
            "the proposal target does not match the host target")])
    if canonical_sha256("proposal", patch["proposal"]) != patch["proposal_sha256"]:
        raise HostContextError([_host_finding(
            "the carried proposal does not match its own digest")])
    if patch["policy"]["id"] != policy_id:
        raise HostContextError([_host_finding(
            "the host patch policy id does not match the policy document")])
    patch["patch_sha256"] = canonical_sha256(
        "patch", {key: value for key, value in patch.items() if key != "patch_sha256"})
    return patch


# CP4-A result states.  UNKNOWN is not BLOCKED: an authority that cannot be
# resolved is not a denial, and the two must never be collapsed into one value.
AUTH_PASS = "PASS"
AUTH_BLOCKED = "BLOCKED"
AUTH_UNKNOWN = "UNKNOWN"


def resolve_authorization(host_context, policy, rule, required_paths=()):
    """Resolve whether this transaction is authorized to act (CP4-A).

    The decision is a function of the HOST state only: the policy document, the
    host-resolved authority block and the run/candidate binding.  The proposal
    is NOT an input and cannot appear anywhere in it -- an AI-authored candidate
    that could grant its own permission would make the whole safety loop
    decorative.  A proposal-supplied `authorized` / `file_write` / `tool_execute`
    field has no reader here and therefore no effect.

    Denials are BLOCKED (the host said no).  A state that cannot be resolved --
    a missing or non-identifying authority -- is UNKNOWN, never BLOCKED and
    never silently allowed.  An exception is never swallowed into a decision:
    a malformed authority raises, because "we could not tell" is not a verdict.
    """
    if not isinstance(rule, Mapping) or not rule.get("id"):
        raise HostContextError([_host_finding(
            "authorization needs the bound rule, not an unnamed one")])
    findings = authority_findings(host_context, required_paths=required_paths)
    if findings:
        return {"status": AUTH_BLOCKED, "findings": list(findings),
                "capabilities": {}}
    # The approval that authorizes this rule must bind THIS policy document,
    # THIS run and THIS candidate.  approved_rule_ids applies exactly that
    # filter, so a grant for another policy or another candidate cannot carry.
    policy_sha = _policy_document_sha256(policy)
    if rule["id"] not in approved_rule_ids(host_context, policy_sha):
        return {"status": AUTH_BLOCKED,
                "findings": [_finding(
                    REASON_AUTH_DENIED,
                    "no host approval binds rule %s to this policy digest, run and "
                    "candidate" % rule["id"])],
                "capabilities": {}}
    effects = {row["capability"]: row["effect"]
               for row in host_context["authority"]["decisions"]}
    return {
        "status": AUTH_PASS,
        "findings": [],
        "capabilities": {capability: effects[capability]
                         for capability in REQUIRED_CAPABILITIES},
        "policy_sha256": policy_sha,
        "rule_id": rule["id"],
        "authorization_refs": list(host_context["authority"]["resolved_authorization_refs"]),
    }


# CP4-B states.  TOOLCHAIN_PASS means the host toolchain is the qualified one and
# may be invoked.  A mismatch is BLOCKED: the host named a different toolchain
# than the contract qualifies, and "different" is not "unverifiable".
TOOLCHAIN_PASS = "PASS"
TOOLCHAIN_BLOCKED = "BLOCKED"
TOOLCHAIN_UNKNOWN = "UNKNOWN"


def qualify_toolchain(host_context, runtime):
    """Decide whether the host toolchain is the qualified one (CP4-B).

    This is the obligation CP3 only recorded as metadata.  A HostPatch may carry
    any toolchain slice, so until something checks it, "the toolchain identity
    travels with the patch" is documentation rather than a control.  Here the
    slice the transaction will actually use must trace back to THIS host binding
    and to the pinned akcli, or the qualified kernel must not be invoked.

    Deliberately small: this answers one question with the primitives the frozen
    toolchain layer already provides (`validate_host_binding`,
    `derive_akcli_slice`, `toolchain_slice_sha256`).  It is not a version
    management system, it does not resolve, download or install anything, and it
    never calls the tool.  Qualification is a precondition for the call, never a
    substitute for it.

    UNKNOWN is reserved for a state that cannot be established.  A declared
    mismatch, or a binding that does not pin the qualified version, is BLOCKED --
    the host said something definite and it was not the qualified thing.
    """
    binding = host_context["toolchain_binding"]
    try:
        normalized = host_toolchain.validate_host_binding(binding)
    except host_toolchain.HostBindingError as exc:
        return {"status": TOOLCHAIN_BLOCKED, "findings": [_host_finding(
            "the host toolchain binding is not qualified: %s" % exc)],
            "pinned_akcli_version": PINNED_AKCLI_VERSION, "observed": None}
    result = {"status": TOOLCHAIN_BLOCKED, "findings": [],
              "pinned_akcli_version": PINNED_AKCLI_VERSION, "observed": None}
    result["host_binding_sha256"] = host_toolchain.host_binding_sha256(normalized)
    slice_manifest = runtime["toolchain_manifest"]
    result["expected_toolchain_sha256"] = host_toolchain.toolchain_slice_sha256(
        host_toolchain.derive_akcli_slice(
            normalized, host_context["candidate_symbol_digest"]))
    result["observed"] = {
        "toolchain_sha256": host_toolchain.toolchain_slice_sha256(slice_manifest),
        "akcli_version": slice_manifest.get("akcli_version"),
        "akcli_artifact_sha256": slice_manifest.get("akcli_artifact_sha256"),
    }
    if result["observed"]["akcli_version"] != PINNED_AKCLI_VERSION:
        result["findings"].append(_host_finding(
            "the transaction toolchain declares akcli %r, but the qualified "
            "version is %s" % (result["observed"]["akcli_version"],
                               PINNED_AKCLI_VERSION)))
    if result["observed"]["toolchain_sha256"] != result["expected_toolchain_sha256"]:
        result["findings"].append(_host_finding(
            "the transaction toolchain slice is not the slice this host binding "
            "derives for the before-candidate symbol digest"))
    if result["findings"]:
        return result
    result["status"] = TOOLCHAIN_PASS
    return result


def bind_policy(host_context, proposal, native_before, policy=None,
                required_paths=()):
    """Bind one transaction into a BoundPolicyResult (CP4-C, orchestration only).

    Composition, nothing new.  This orders the four already-proven stages and
    stops at the first one that refuses:

        validate host -> CP1 expected_after -> CP4-A authorization
                     -> CP4-B toolchain -> CP3 HostPatch

    Authorization is resolved BEFORE the toolchain is qualified, so a
    transaction that is not permitted never reaches the point where its
    toolchain matters, and a permitted one still cannot act on an unqualified
    toolchain.  The order is the safety order, not a preference.

    A refusal from any stage is a BLOCKED result carrying that stage's own
    findings -- the reason is never replaced with a generic message and never
    swallowed.  TOOL_ERROR is reserved for a stage that could not run (the host
    toolchain is absent or the native read failed); UNKNOWN is reserved for a
    state that could not be established.  Neither is ever reported as PASS, and
    a False is never treated as an error: each stage returns a status, and an
    unexpected exception propagates rather than being converted into a verdict.

    No stage is executed here.  A PASS means the transaction is bound and
    qualified, NOT that anything was written; committing it is a later phase.
    """
    receipt = {
        "status": STATUS_BLOCKED,
        "last_phase": PHASE_PRECHECK,
        "cause_status": None,
        "reasons": [],
    }

    def refuse(phase, status, findings):
        receipt.update(status=status, last_phase=phase, cause_status=status,
                       reasons=list(findings))
        return receipt

    try:
        validate_host_context(host_context)
    except HostContextError as exc:
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, exc.findings)
    if policy is None:
        policy = load_topology_policy()
    policy_sha = _policy_document_sha256(policy)
    try:
        approved = approved_rule_ids(host_context, policy_sha)
        rule, findings = select_rule(policy, proposal, approved)
        if findings:
            return refuse(PHASE_PRECHECK, STATUS_BLOCKED, findings)
        authorization = resolve_authorization(host_context, policy, rule,
                                              required_paths=required_paths)
        if authorization["status"] != AUTH_PASS:
            return refuse(PHASE_PRECHECK, STATUS_BLOCKED, authorization["findings"])
        runtime = runtime_bindings(host_context, proposal, native_before,
                                   policy_sha, approved, rule=rule, removals={})
        toolchain = qualify_toolchain(host_context, runtime)
        if toolchain["status"] != TOOLCHAIN_PASS:
            return refuse(PHASE_PRECHECK, STATUS_BLOCKED, toolchain["findings"])
        additions = build_expected_after(native_before["observation"], proposal)
        bound = _bound_policy(native_before["observation"], rule, runtime, additions,
                              rule["route"])
        host_patch = _host_patch(host_context, proposal, runtime, bound, policy)
    except HostContextError as exc:
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, exc.findings)
    except RepairContractError as exc:
        return refuse(PHASE_PRECHECK, STATUS_UNKNOWN, [_finding(
            REASON_INPUT_DRIFT, "the transaction could not be established: %s" % exc)])
    receipt.update(
        status=STATUS_NO_CHANGE,
        last_phase=PHASE_PRECHECK,
        cause_status=None,
        reasons=[],
        rule_id=rule["id"],
        route=rule["route"],
        policy_sha256=policy_sha,
        authorization={"status": authorization["status"],
                       "capabilities": authorization["capabilities"],
                       "authorization_refs": authorization["authorization_refs"]},
        toolchain={"status": toolchain["status"],
                   "pinned_akcli_version": toolchain["pinned_akcli_version"],
                   "toolchain_sha256": toolchain["observed"]["toolchain_sha256"]},
        bound_policy_sha256=host_patch["policy"]["bound_policy_sha256"],
        patch_sha256=host_patch["patch_sha256"],
        authorized_delta_sha256=bound["authorized_delta_sha256"],
        expected_after_source_sha256=bound["expected_after"]["source_sha256"],
        host_patch=host_patch,
    )
    return receipt


# ===========================================================================
# PR1-C5 RUN-ROUND MVP -- one round controller
# ===========================================================================
#
# Composition only.  Every stage below already existed, already had tests and was
# already frozen; the thing that was missing was the code that ORDERS them and
# refuses to continue past the first refusal.
#
#     PRECHECK      observe_source -> parse_proposal -> build_expected_after
#                   -> bind_policy
#     STAGE_APPLY   akcli_adapter.apply_stage      (the real pinned writer)
#     DELTA_CHECK   gates.repair_verification.compare_delta
#
# Three properties are load-bearing, and each exists because the alternative has
# already gone wrong on this repository:
#
# 1. compare_delta is the ONLY acceptance entry.  An earlier harness compared
#    observation_delta digests by hand and reported a FALSE "identity delta
#    FAIL"; the capability it declared missing had been in C2 all along
#    (_align_new, called from _prepare, called from compare_delta) and the real
#    defect was using the wrong entry point.  PR #93 pinned the entry with a
#    static guard.  run_round consumes compare_delta and never touches
#    observation_delta, so it cannot reintroduce that failure.
#
# 2. There is NO seam for the writer.  run_round always calls the real
#    apply_stage -- no parameter, hook or override.  A successful write is
#    therefore structurally impossible to simulate, not merely discouraged.  On
#    a host without the pinned akcli the round cannot report a write at all,
#    which is the correct answer rather than a gap.
#
# 3. A stage-level status is never read as a transaction status.  apply_stage
#    returns "APPLIED_TO_STAGE", which says only that the writer ran against a
#    scratch stage.  Success additionally requires tool_applied, exit_code == 0
#    and changed, because a tool that exits 0 having applied nothing is not a
#    write.
#
# The round STOPS after DELTA_CHECK.  KICAD_VERIFY and COMMIT are not
# implemented, so a verified round has no terminal transaction status and this
# function does not invent one: it reports status=None with terminal=False and
# the phases still owed.  public_feedback() then projects EXECUTION_UNAVAILABLE,
# which is the truthful public answer -- the outcome is not established because
# the round never committed.  Claiming STATUS_COMMITTED here would be precisely
# the failure this repository exists to prevent.
#
# Round-trip asymmetry worth stating plainly: PRECHECK reads the BEFORE bytes
# from the stage target and DELTA_CHECK reads the AFTER bytes from that same
# path.  Both ends of the comparison are therefore the same file observed either
# side of the real write, so no caller can pair an unrelated before with an
# unrelated after.

ROUND_REQUIRED = (
    "host_context",
    "proposal_raw",
    "txn_id",
    "stage_root",
    "stage_target",
    "oplist_path",
    "native_artifact_root",
)
ROUND_OPTIONAL = ("policy", "required_paths")
ROUND_FIELDS = ROUND_REQUIRED + ROUND_OPTIONAL

# Phases this MVP drives, in order.  KICAD_VERIFY and COMMIT are deliberately
# absent: they are not implemented, and naming them as driven would overstate
# what a run actually proved.
ROUND_PHASES = (PHASE_PRECHECK, PHASE_STAGE_APPLY, PHASE_DELTA_CHECK)
ROUND_PENDING_PHASES = (PHASE_KICAD_VERIFY, PHASE_COMMIT)

# apply_stage reports a stage-level refusal in its own vocabulary.  Each keeps
# its own failure class; collapsing a refusal into UNKNOWN would hide the reason
# code the caller has to act on.
_STAGE_REFUSAL_STATUS = {
    "BLOCKED": STATUS_BLOCKED,
    "TOOL_ERROR": STATUS_TOOL_ERROR,
}


def _round_receipt(status, phase, reasons, terminal):
    return {
        "status": status,
        "phase": phase,
        "cause_status": status if terminal else None,
        "terminal": terminal,
        "reasons": list(reasons),
        "phases": [],
        # Stable shape: a caller must be able to read these without knowing
        # which phase the round stopped in.
        "txn_id": None,
        "stage_root": None,
        "candidate_design_root": None,
        "before_source_sha256": None,
        "after_source_sha256": None,
        "rule_id": None,
        "route": None,
        "policy_sha256": None,
        "bound_policy_sha256": None,
        "patch_sha256": None,
        "authorized_delta_sha256": None,
        "stage": None,
        "verification": None,
        "pending_phases": None,
        "feedback": None,
    }


def _stage_write_succeeded(staged: Mapping) -> bool:
    """True only when the pinned writer really wrote the authorized op-list.

    Property 3 of run_round: ``APPLIED_TO_STAGE`` is a STAGE-level status.  It
    says the writer ran against a scratch stage; it says nothing about whether
    anything was written.  All four facts are required, because each can be false
    while the others are true:

    ``status == "APPLIED_TO_STAGE"``  the writer ran and claimed the stage route
    ``tool_applied is True``          the writer self-reported applying the ops
    ``exit_code == 0``                the tool did not fail
    ``changed is True``               the target bytes actually differ

    A tool that exits 0 having applied nothing is not a write, and treating its
    exit code as success is precisely how a fake write would enter the evidence
    chain.  The predicate is separated from run_round purely so this criterion
    can be tested exhaustively; run_round itself always calls the real
    ``apply_stage`` and has no seam through which a receipt could be injected.
    """
    if not isinstance(staged, Mapping):
        return False
    tool = staged.get("tool")
    if not isinstance(tool, Mapping):
        return False
    return (staged.get("status") == "APPLIED_TO_STAGE"
            and tool.get("tool_applied") is True
            and tool.get("exit_code") == 0
            and staged.get("changed") is True)


def build_file_manifest(root, target_relative):
    """Build a C3 dependency manifest from the REAL bytes under ``root``.

    PR1-C5-SNAPSHOT.  C3 could already VALIDATE a manifest (``_manifest``) and
    VERIFY one against real bytes (``_tree_digest``), but nothing could PRODUCE
    one, so the snapshot half of ``bind_inputs`` could never be fed.  This is
    that missing producer.

    The shape is not invented here: it is exactly what
    ``gates.repair_verification._manifest`` accepts --

        {"version": 1,
         "files": [{"path": ..., "sha256": ..., "size_bytes": ...,
                    "role": "TARGET" | "READONLY_DEPENDENCY"}, ...]}

    -- and the tests assert that by calling the repository's own validator
    rather than restating its rules.  Every digest and size is measured from the
    file; nothing is carried over from a declaration.

    ``target_relative`` names the one TARGET.  Paths are emitted with forward
    slashes and are resolved inside ``root``; a file that escapes the root, or a
    link, is refused rather than described.
    """
    root_path = Path(root).resolve()
    target = _text(target_relative, "target_relative", allow_empty=False)

    rows = []
    for absolute in sorted(root_path.rglob("*")):
        if not absolute.is_file():
            continue
        resolved = absolute.resolve()
        try:
            relative = resolved.relative_to(root_path)
        except ValueError:
            raise ProposalInvalidError([_finding(
                REASON_INPUT_DRIFT,
                "the tree at %s contains a path outside it: %s" % (root, absolute))])
        if absolute.is_symlink() or resolved != absolute:
            raise ProposalInvalidError([_finding(
                REASON_INPUT_DRIFT,
                "a link is not describable in a manifest: %s" % absolute)])
        as_text = relative.as_posix()
        rows.append({
            "path": as_text,
            "sha256": hash_bytes(resolved.read_bytes()),
            "size_bytes": resolved.stat().st_size,
            "role": "TARGET" if as_text == target else "READONLY_DEPENDENCY",
        })

    if not any(row["role"] == "TARGET" for row in rows):
        raise ProposalInvalidError([_finding(
            REASON_INPUT_DRIFT,
            "the tree at %s carries no %r to mark as the TARGET" % (root, target))])
    return {"version": 1, "files": rows}


def materialise_snapshot(candidate_design_root, snapshot_root, target_relative):
    """Copy the candidate's design tree into a snapshot and describe it.

    PR1-C5-SNAPSHOT.  The snapshot is the BEFORE of record: it is what the round
    reads, and what a later COMMIT would restore from.  Copying rather than
    pointing matters -- the point of a snapshot is that the bytes it names cannot
    drift underneath the decision that referenced them.

    Returns ``(snapshot_root, manifest)``.  The copy is verified to be
    byte-identical to the source before the manifest is built, so a truncated or
    partially-copied snapshot fails here instead of being described as valid.

    Refuses a snapshot root that overlaps the candidate, which would make the
    snapshot a view of the thing it is supposed to be independent of.
    """
    source = Path(candidate_design_root).resolve()
    destination = Path(snapshot_root).resolve()
    overlap = _stage_candidate_overlap(destination, source)
    if overlap is not None:
        raise ProposalInvalidError([_finding(
            REASON_INPUT_DRIFT,
            "the snapshot root is not disjoint from the candidate design root: %s "
            "(snapshot=%s candidate=%s); a snapshot of the candidate cannot live "
            "inside the candidate" % (_OVERLAP_DETAIL[overlap], destination, source))])
    if not source.is_dir():
        raise ProposalInvalidError([_finding(
            REASON_INPUT_DRIFT,
            "the candidate design root is not a directory: %s" % source)])

    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)

    # byte-for-byte confirmation, before anything is described as a snapshot
    for absolute in sorted(destination.rglob("*")):
        if not absolute.is_file():
            continue
        relative = absolute.relative_to(destination)
        origin = source / relative
        if not origin.is_file():
            raise ProposalInvalidError([_finding(
                REASON_INPUT_DRIFT,
                "the snapshot carries a file the candidate does not: %s" % relative)])
        if absolute.read_bytes() != origin.read_bytes():
            raise ProposalInvalidError([_finding(
                REASON_INPUT_DRIFT,
                "the snapshot copy of %s is not byte-identical to the candidate"
                % relative)])
    if not (destination / _text(target_relative, "target_relative",
                                allow_empty=False)).is_file():
        raise ProposalInvalidError([_finding(
            REASON_INPUT_DRIFT,
            "the snapshot does not carry the target %r" % target_relative)])

    return str(destination), build_file_manifest(destination, target_relative)


# KICAD_VERIFY tool identity states.  These are EVIDENCE STATES, not verdicts:
# the phase is an evidence generator and the policy layer decides what any of
# them means.  There is deliberately no FAIL among them (Owner ruling 3).
TOOL_IDENTITY_MATCH = "MATCH"
TOOL_IDENTITY_SUBSTITUTION = "SUBSTITUTION"
TOOL_IDENTITY_UNAVAILABLE = "UNAVAILABLE"

# The netlist digest normalisation, as DATA (Owner ruling 1).  A bare
# `normalized_hash` field was explicitly rejected: years later nobody could say
# why two different files hashed alike.  The removed field and the reason travel
# with the digest, and the raw digest is always retained beside it.
_NETLIST_NORMALIZATION = {
    "removed_fields": ["date"],
    "reason": "generator timestamp",
    "note": "kicad-cli writes (date \"...\") into the netlist, so two runs of "
            "identical input produce different bytes. Blanking that one field "
            "makes the digest comparable across rounds. This is LOSSY: the "
            "generation time is exactly what it discards, which is why "
            "netlist_sha256 is retained unmodified alongside it.",
}

# Measured limits of the standard KiCad ERC on this project's own defect class.
# Recorded in the artifact rather than in a comment, so a reader of the evidence
# learns what it does not establish without having to find this file.
_KICAD_VERIFY_LIMITATIONS = (
    "KiCad standard ERC reported 0 errors on the DC-04 fixture in its "
    "defective state. Its 37 warnings were all lib_symbol_issues or "
    "footprint_link_issues -- library resolution, not electrical. This "
    "artifact therefore establishes that the tool ran and what it said; it "
    "does NOT establish that the design is electrically correct.",
    "ERC violation counts on this fixture are dominated by symbol and "
    "footprint library resolution. Read violation_categories.by_type, not the "
    "totals: a total cannot distinguish a missing library from a missing "
    "power connection.",
    "sch export svg writes a DIRECTORY at the requested path "
    "(out.svg/fault.svg), not a file. A caller that tests the requested path "
    "with is_file() concludes the render failed when it succeeded.",
)


def _kicad_binding_identity(toolchain_binding):
    """Read the DECLARED kicad identity out of the validated host binding.

    Read from ``host_context["toolchain_binding"]`` rather than from
    ``host_patch["toolchain_manifest"]``: the patch carries the akcli slice,
    which has no kicad entry at all, so ``toolchain_sha256`` does not commit to
    the kicad binary. That absence is reported in the artifact rather than
    worked around.

    Returns ``(resolved_path, declared_sha256, declared_version)``; any element
    may be ``None`` when the declaration is missing.
    """
    if not isinstance(toolchain_binding, Mapping):
        return None, None, None
    manifest = toolchain_binding.get("manifest")
    declared = manifest.get("kicad") if isinstance(manifest, Mapping) else None
    declared = declared if isinstance(declared, Mapping) else {}
    resolution = toolchain_binding.get("resolution")
    executables = resolution.get("executables") if isinstance(
        resolution, Mapping) else None
    path = executables.get("kicad") if isinstance(executables, Mapping) else None
    return (
        path if isinstance(path, str) and path.strip() else None,
        declared.get("executable_sha256")
        if isinstance(declared.get("executable_sha256"), str) else None,
        declared.get("version") if isinstance(declared.get("version"), str) else None,
    )


def _kicad_tool_identity(toolchain_binding):
    """Resolve, MEASURE and compare the kicad executable. Fail-closed.

    The binary is located ONLY through the binding.  The board_review helper is
    not called and must not be: it reads ``KICAD_CLI``, then ``PATH``, then a
    hardcoded path belonging to a different user, and it returns ``None`` on a
    machine where KiCad 10.0.5 is installed and working.  Falling back to it
    would let the artifact say it verified kicad X while kicad Y actually ran
    (Owner ruling 2).

    The digest is MEASURED from the file that is about to be executed. It is
    never copied from the declaration, because that declaration is exactly the
    value this phase exists to check.
    """
    path, declared_sha, declared_version = _kicad_binding_identity(
        toolchain_binding)
    identity = {
        "resolved_path": path,
        "declared_sha256": declared_sha,
        "measured_sha256": None,
        "declared_version": declared_version,
        "measured_version": None,
        "status": TOOL_IDENTITY_UNAVAILABLE,
        "resolved_from": "toolchain_binding.resolution.executables.kicad",
        "fallback_used": None,
    }
    if path is None:
        identity["detail"] = ("the binding declares no kicad executable, so "
                              "there is nothing to resolve; refusing rather "
                              "than searching the host")
        return identity, None
    try:
        binary = Path(path).resolve()
    except (OSError, ValueError) as exc:
        identity["detail"] = "the bound kicad path could not be resolved: %s" % exc
        return identity, None
    if not binary.is_file():
        identity["detail"] = ("the bound kicad executable does not exist: %s; "
                              "no other binary was searched for and none was "
                              "run" % binary)
        return identity, None
    try:
        identity["measured_sha256"] = hash_bytes(binary.read_bytes())
    except OSError as exc:
        identity["detail"] = "the bound kicad executable could not be read: %s" % exc
        return identity, None
    if declared_sha is None:
        identity["status"] = TOOL_IDENTITY_SUBSTITUTION
        identity["detail"] = ("the binding declares no digest for the kicad "
                              "executable, so the binary that would run cannot "
                              "be shown to be the declared one")
        return identity, None
    if identity["measured_sha256"] != declared_sha:
        identity["status"] = TOOL_IDENTITY_SUBSTITUTION
        identity["detail"] = ("the kicad executable at the bound path does not "
                              "hash to the digest the binding declares")
        return identity, None
    identity["status"] = TOOL_IDENTITY_MATCH
    return identity, binary


def _kicad_run(binary, args, cwd, timeout_seconds):
    """Run kicad-cli and return (exit_code, combined_output). Never raises.

    The usage text goes to STDOUT, not stderr, so both are captured: a probe that
    reads only stderr reports "no output" for a tool that was explaining exactly
    what was wrong.
    """
    try:
        done = subprocess.run([str(binary)] + [str(a) for a in args], cwd=str(cwd),
                              capture_output=True, text=True,
                              timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return None, "the tool did not finish within %ss" % timeout_seconds
    except OSError as exc:
        return None, "the tool could not be started: %s" % exc
    return done.returncode, ((done.stdout or "") + (done.stderr or "")).strip()


def _erc_evidence(binary, project_root, target, artifact_root, timeout_seconds):
    """ERC as machine-readable evidence, categorised.

    Read as JSON rather than scraped from the text report: the JSON carries
    kicad_version, source and included_severities natively, which is provenance
    this phase would otherwise have to assert about itself.

    Bare totals are NOT emitted. 37 carries no information; 22 missing-library
    plus 15 footprint-linkage plus 0 electrical carries a great deal
    (Owner ruling 4).
    """
    report = artifact_root / "erc.json"
    code, text = _kicad_run(
        binary,
        ["sch", "erc", "--output", str(report), "--format", "json",
         "--severity-all", str(project_root / target)],
        project_root, timeout_seconds)
    evidence = {
        "exit_code": code,
        "report_path": str(report),
        "produced": report.is_file(),
        "violations": {
            "error": {"total": 0, "by_type": {}},
            "warning": {"total": 0, "by_type": {}},
        },
        "kicad_version": None,
        "source": None,
        "included_severities": None,
    }
    if not report.is_file():
        evidence["detail"] = text or "the tool produced no report"
        return evidence
    try:
        parsed = json.loads(report.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        evidence["detail"] = "the ERC report is not readable JSON: %s" % exc
        return evidence
    for key in ("kicad_version", "source", "included_severities"):
        evidence[key] = parsed.get(key)
    for sheet in parsed.get("sheets") or []:
        for item in sheet.get("violations") or []:
            severity = item.get("severity")
            bucket = evidence["violations"].get(severity)
            if bucket is None:
                # An unrecognised severity is not silently dropped: it becomes
                # its own bucket rather than vanishing from the count.
                bucket = evidence["violations"][severity] = {"total": 0, "by_type": {}}
            bucket["total"] += 1
            kind = item.get("type") or "unclassified"
            bucket["by_type"][kind] = bucket["by_type"].get(kind, 0) + 1
    return evidence


def _netlist_evidence(binary, project_root, target, artifact_root, timeout_seconds):
    """Netlist with BOTH digests and the normalisation rule as data.

    Measured: two runs of identical input produce different bytes, differing on
    exactly one line, ``(date "2026-09-27T23:47:19")``. So the raw digest
    identifies the artefact and the content digest identifies the design, and
    conflating them would make either claim false.
    """
    netlist = artifact_root / "netlist.net"
    code, text = _kicad_run(
        binary,
        ["sch", "export", "netlist", "--format", "kicadsexpr",
         "-o", str(netlist), str(project_root / target)],
        project_root, timeout_seconds)
    evidence = {
        "requested_path": str(netlist),
        "exit_code": code,
        "produced": netlist.is_file(),
        "netlist_sha256": None,
        "netlist_content_sha256": None,
        "normalization": dict(_NETLIST_NORMALIZATION),
    }
    if not netlist.is_file():
        evidence["detail"] = text or "the tool produced no netlist"
        return evidence
    raw = netlist.read_bytes()
    evidence["netlist_sha256"] = hash_bytes(raw)
    text_form = raw.decode("utf-8", errors="replace")
    blanked, replacements = re.subn(
        r'\(date\s+"[^"]*"\)', '(date "<removed>")', text_form)
    evidence["normalization"]["replacements_in_this_artifact"] = replacements
    evidence["netlist_content_sha256"] = hash_bytes(blanked.encode("utf-8"))
    return evidence


def _render_evidence(binary, project_root, target, artifact_root, timeout_seconds):
    """Enumerate what the render ACTUALLY produced, not what was requested.

    Measured: ``sch export svg -o out.svg`` writes the DIRECTORY ``out.svg``
    containing ``fault.svg``. A caller testing the requested path with is_file()
    concludes the render failed when it succeeded -- the same shape as a tool
    that succeeds and a caller that misreads it (Owner ruling 5).
    """
    outputs = []
    for fmt, arguments in (("svg", ["sch", "export", "svg"]),
                           ("pdf", ["sch", "export", "pdf"])):
        requested = artifact_root / ("render.%s" % fmt)
        code, text = _kicad_run(
            binary, arguments + ["-o", str(requested),
                                 str(project_root / target)],
            project_root, timeout_seconds)
        row = {
            "format": fmt,
            "requested": str(requested),
            "requested_is_file": requested.is_file(),
            "requested_is_directory": requested.is_dir(),
            "exit_code": code,
            "artefacts": [],
        }
        # The artefact may be the requested path itself, or something inside it.
        found = []
        if requested.is_file():
            found = [requested]
        elif requested.is_dir():
            found = sorted(p for p in requested.rglob("*") if p.is_file())
        for artefact in found:
            row["artefacts"].append({
                "actual_path": str(artefact),
                "size_bytes": artefact.stat().st_size,
                "sha256": hash_bytes(artefact.read_bytes()),
            })
        if not found:
            row["detail"] = text or "the tool reported no output"
        outputs.append(row)
    return {"outputs": outputs}


def kicad_verify_evidence(toolchain_binding, project_root, target,
                          artifact_root, timeout_seconds=120):
    """Produce the KICAD_VERIFY evidence artifact. Decides nothing.

    Every branch here returns an artifact; none of them raises into the caller
    and none of them expresses an opinion about whether the transaction may
    proceed. ``tool_identity.status`` is one of MATCH / SUBSTITUTION /
    UNAVAILABLE, and the tool is executed only on MATCH -- because evidence
    gathered by a binary that cannot be identified is not evidence about the
    design.

    The measured reason this is not a gate: KiCad's standard ERC reports ZERO
    errors on the DC-04 fixture in its defective state. A phase that gated on
    that number would be green on a broken board.
    """
    project = Path(project_root).resolve()
    artifacts = Path(artifact_root)
    artifacts.mkdir(parents=True, exist_ok=True)

    artifact = {
        "phase": PHASE_KICAD_VERIFY,
        "role": "evidence-generator",
        "decides": None,
        "tool_identity": None,
        "erc": None,
        "netlist": None,
        "render": None,
        "timeout_seconds": timeout_seconds,
        "limitations": list(_KICAD_VERIFY_LIMITATIONS),
    }

    identity, binary = _kicad_tool_identity(toolchain_binding)
    artifact["tool_identity"] = identity
    if binary is None:
        # Nothing is executed and nothing is invented. The absence of ERC, of a
        # netlist and of a render is itself the evidence.
        artifact["detail"] = identity.get("detail")
        return artifact

    code, text = _kicad_run(binary, ["version"], project, timeout_seconds)
    identity["measured_version"] = (text or "").strip().splitlines()[0] \
        if text else None
    if identity.get("declared_version") and identity["measured_version"] \
            and identity["declared_version"] not in identity["measured_version"]:
        # A version string that disagrees with the declaration is a second,
        # independent signal of substitution.
        identity["status"] = TOOL_IDENTITY_SUBSTITUTION
        identity["version_disagreement"] = {
            "declared": identity["declared_version"],
            "measured": identity["measured_version"],
        }
        artifact["detail"] = ("the bound kicad executable reports a version "
                              "that does not contain the declared version")
        return artifact

    # No further identity check is needed here, and an earlier version had a
    # redundant `if status != MATCH: return` at this point. It was UNREACHABLE:
    # _kicad_tool_identity returns a non-None binary only on MATCH, so every
    # other state has already returned above -- which is why mutation K4
    # (disabling that guard) changed nothing. The invariant it appeared to check
    # is now asserted directly by the test suite, on the function that actually
    # establishes it.

    artifact["erc"] = _erc_evidence(binary, project, target, artifacts,
                                    timeout_seconds)
    artifact["netlist"] = _netlist_evidence(binary, project, target, artifacts,
                                            timeout_seconds)
    artifact["render"] = _render_evidence(binary, project, target, artifacts,
                                          timeout_seconds)
    return artifact


def _delta_identity_label(identity) -> str:
    """Name one object the way a reviewer would.

    ``role`` is only interesting when it is a synthesized role such as
    ``new:R9``.  For an object that already existed, the identity carries a
    plain UUID, and printing that beside the reference is noise rather than
    information -- the reference is what a reviewer recognises.
    """
    if not isinstance(identity, Mapping):
        return "an unnamed object"
    reference = identity.get("reference")
    role = (identity.get("component_uuid") or identity.get("label_uuid")
            or identity.get("pin_uuid"))
    if isinstance(role, str) and role.startswith("new:"):
        return "%s (%s)" % (reference, role) if reference else role
    return str(reference or role or "an unnamed object")


def _delta_object_id(identity) -> str:
    """The stable handle for this object, preferring a readable role."""
    if not isinstance(identity, Mapping):
        return "unknown"
    role = (identity.get("component_uuid") or identity.get("label_uuid")
            or identity.get("pin_uuid"))
    if isinstance(role, str) and role.startswith("new:"):
        return role
    return str(identity.get("reference") or role or "unknown")


def _delta_findings(verdict):
    """Turn a FAIL delta verdict into findings that NAME the deviation.

    PR1-C5-M7, Owner criterion 5.  ``compare_delta`` already reports exactly
    what diverged, but the round receipt only forwarded ``verdict["reasons"]``,
    which is the single generic code REPAIR_DELTA_MISMATCH.  A reader could
    therefore learn THAT the round was refused and nothing about WHY -- the
    difference between "failed" and "failed because R9 resolved to 20k when 10k
    was authorized".

    The verdict uses TWO entry shapes and both must be read correctly:

    * a FIELD-level change on an object that exists on both sides, where
      ``field`` names the field and ``before``/``after`` are the two values::

          {"field": "value", "before": "10k", "after": "20k", "identity": ...}

      Such an entry is self-contained and is reported directly.

    * an OBJECT-level divergence for something added or removed, where
      ``field`` is ``"$"`` and ``before``/``after`` are whole descriptors, the
      authorized one arriving in ``missing`` and the observed one in
      ``unexpected``.  These are paired by identity and their descriptors diffed.

    Reading only the first shape loses the field name and both values, which is
    exactly the specificity criterion 5 asks for, so both are handled.

    These findings are ADDITIVE: the generic code is kept and the full verdict
    still travels under ``receipt["verification"]``.
    """
    missing = list(verdict.get("missing") or [])
    unexpected = list(verdict.get("unexpected") or [])
    missing_by_key = {canonical_json_bytes(row.get("identity")): row
                      for row in missing}

    findings = []
    paired_keys = set()

    for row in unexpected:
        identity = row.get("identity")
        label = _delta_identity_label(identity)
        object_id = _delta_object_id(identity)
        field = row.get("field")
        if field and field != "$":
            # field-level: this entry already carries the field and both values
            detail = ("%s field %r was authorized as %r but observed as %r"
                      % (label, field, row.get("before"), row.get("after")))
        else:
            key = canonical_json_bytes(identity)
            paired_keys.add(key)
            counterpart = missing_by_key.get(key)
            authorized = (counterpart or {}).get("after")
            observed = row.get("after")
            if isinstance(authorized, dict) and isinstance(observed, dict):
                differing = sorted(f for f in set(authorized) | set(observed)
                                   if authorized.get(f) != observed.get(f))
                detail = ("%s differs from what was authorized: %s" % (
                    label, "; ".join(
                        "%s authorized=%r but observed=%r"
                        % (f, authorized.get(f), observed.get(f))
                        for f in differing) or "no differing field"))
            else:
                detail = "%s was observed but not authorized" % label
        findings.append(_finding(REASON_DELTA_MISMATCH, detail,
                                 object_id=object_id, stage=PHASE_DELTA_CHECK))

    for row in missing:
        key = canonical_json_bytes(row.get("identity"))
        if key in paired_keys:
            continue  # already reported as the object-level pair above
        identity = row.get("identity")
        label = _delta_identity_label(identity)
        field = row.get("field")
        if field and field != "$":
            detail = ("%s field %r was authorized as %r but was not observed"
                      % (label, field, row.get("before")))
        else:
            detail = "%s was authorized but not observed" % label
        findings.append(_finding(REASON_DELTA_MISMATCH, detail,
                                 object_id=_delta_object_id(identity),
                                 stage=PHASE_DELTA_CHECK))

    return findings


def _delta_refusal(verdict):
    """Map a failed DELTA_CHECK verdict to (status, cause_status, reasons).

    The pairing is the whole point, so it is separated from run_round to be
    testable on its own.  ``STATUS_ROLLBACK`` together with
    ``cause_status=STATUS_BLOCKED`` is what projects the round as REJECTED:
    what verification found violated is the AUTHORIZATION itself, so the public
    outcome is "rejected" rather than "unavailable".

    Getting this wrong is silent and was in fact wrong once: refusing with
    ``cause_status=STATUS_ROLLBACK`` yields EXECUTION_UNAVAILABLE, so a genuinely
    rejected round would have been published as an execution problem instead of
    a refusal.  An earlier version of this code documented the intended pairing
    in a comment without implementing it, and only the end-to-end run against a
    real writer exposed it.

    Terminology (Owner ruling 2026-09-27): ROLLBACK here means the
    un-promoted stage result is discarded.  It does NOT mean a committed state
    was restored -- this round never committed, so there is nothing to restore.
    """
    return (STATUS_ROLLBACK, STATUS_BLOCKED,
            list(verdict.get("reasons") or []) + _delta_findings(verdict))


def _stage_candidate_overlap(stage_root, design_root):
    """Classify how the writer's stage overlaps the candidate's design area.

    Returns ``"equal"``, ``"stage_contains_design"``, ``"design_contains_stage"``,
    or ``None`` when the two are genuinely disjoint.

    Why this exists.  ``_WORKSPACE_FIELDS`` declares candidate_root, design_root,
    repair_root and lock_path but NO stage, so the stage sits outside the declared
    workspace; and neither run_round nor akcli_adapter knows where the candidate
    is.  The separation was therefore conventional and enforced by nothing.  On
    this host both the M6 and the M7 demonstration pointed ``stage_root`` at the
    very directory the host context declared as ``workspace.design_root``, so the
    writer modified the candidate directly -- and the M7 round, which was REJECTED,
    left its unauthorized bytes in the candidate design directory.

    A stage that overlaps the candidate in EITHER direction is refused, not just
    the equal case: if the stage merely contains the design root, the adapter's
    own ``_resolve_within`` containment check would still let an op-list path
    reach into the design.  Disjointness is the property that makes "the round
    stopped before COMMIT" mean "the candidate was not modified".
    """
    stage = Path(stage_root).resolve()
    design = Path(design_root).resolve()
    if stage == design:
        return "equal"
    # stage is a descendant of design  =>  the stage CONTAINS the design root
    if stage in design.parents:
        return "stage_contains_design"
    # design is a descendant of stage  =>  the design root CONTAINS the stage
    if design in stage.parents:
        return "design_contains_stage"
    return None


_OVERLAP_DETAIL = {
    "equal": "the stage root IS the candidate design root",
    "stage_contains_design": "the stage root CONTAINS the candidate design root",
    "design_contains_stage": "the stage root sits INSIDE the candidate design root",
}


def run_round(round_request):
    """Drive one repair round: PRECHECK -> SNAPSHOT -> STAGE_APPLY ->
    DELTA_CHECK.

    ``round_request`` is a closed mapping:

    ==================  ====================================================
    ``host_context``    the validated host context (identities, workspace,
                        toolchain binding, authority)
    ``proposal_raw``    the proposal as raw bytes.  run_round parses it with
                        ``parse_proposal`` itself, so a caller cannot hand in a
                        pre-parsed proposal and bypass that validation.
    ``txn_id``          transaction id passed through to apply_stage
    ``stage_root``      the scratch stage directory the writer may touch
    ``stage_target``    the target filename, relative to ``stage_root``
    ``oplist_path``     the on-disk op-list the writer executes
    ``native_artifact_root``  where the writer may leave native artifacts
    ``policy``          optional; the policy DOCUMENT.  Identity is derived from
                        it, never from an argument, so a caller cannot offer a
                        ``policy_id`` that disagrees with the hashed bytes.
    ``required_paths``  optional; forwarded to the authorization resolver
    ==================  ====================================================

    Returns a round receipt.  ``status`` is ``None`` for a round that applied
    and verified but has not committed -- there is no terminal status for that
    state and none is fabricated.  A refusal at any phase stops the round and
    carries that phase's own findings through unchanged.
    """
    receipt = _round_receipt(STATUS_BLOCKED, PHASE_PRECHECK, [], False)

    def reach(phase):
        receipt["phases"].append({"phase": phase, "status": "reached"})

    def refuse(phase, status, reasons, cause_status=None):
        # cause_status is separate from status on purpose: a ROLLBACK caused by a
        # BLOCKED authorization must publish as REJECTED, not as UNAVAILABLE.
        receipt["phases"].append({"phase": phase, "status": "refused"})
        receipt.update(status=status, phase=phase,
                       cause_status=cause_status or status,
                       terminal=True, reasons=list(reasons))
        return receipt

    # ---- the request itself ------------------------------------------------
    if not isinstance(round_request, Mapping):
        raise TypeError("round_request must be a mapping")
    _closed_keys(round_request, ROUND_FIELDS, "round request")
    _require_keys(round_request, ROUND_REQUIRED, "round request")
    try:
        host_context = round_request["host_context"]
        txn_id = _identifier(round_request["txn_id"], "txn_id")
        stage_root = _text(round_request["stage_root"], "stage_root", allow_empty=False)
        # stage_target is a FILENAME relative to stage_root, not an identifier:
        # the real targets are things like "fault.kicad_sch".
        stage_target = _text(round_request["stage_target"], "stage_target",
                             allow_empty=False)
        oplist_path = _text(round_request["oplist_path"], "oplist_path",
                            allow_empty=False)
        artifact_root = _text(round_request["native_artifact_root"],
                              "native_artifact_root", allow_empty=False)
        proposal_raw = round_request["proposal_raw"]
        if not isinstance(proposal_raw, (bytes, bytearray)):
            raise TypeError("proposal_raw must be bytes")
        policy = round_request.get("policy")
        required_paths = tuple(round_request.get("required_paths") or ())
    except HostContextError as exc:
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, exc.findings)
    except RepairContractError as exc:
        # Carry the contract's OWN findings through, not str(exc).
        # RepairContractError stringifies to its reason CODES joined by "; ", so
        # the receipt was naming the class of refusal while discarding which
        # field was wrong -- the one piece of information the caller acts on.
        findings = list(getattr(exc, "findings", None) or ())
        if not findings:
            findings = [_finding(REASON_INPUT_DRIFT, str(exc))]
        return refuse(PHASE_PRECHECK, STATUS_UNKNOWN, findings)

    receipt["txn_id"] = txn_id

    # ---- the stage must be provably disjoint from the candidate -----------
    # Checked BEFORE the before-bytes are read and long before the writer runs,
    # so an overlapping stage is never even observed.  Fail-closed: if the
    # candidate's design root cannot be determined, disjointness cannot be
    # proven and the round is refused rather than allowed on trust.
    workspace = host_context.get("workspace") if isinstance(host_context, Mapping) \
        else None
    design_root = workspace.get("design_root") if isinstance(workspace, Mapping) \
        else None
    repair_root = workspace.get("repair_root") if isinstance(workspace, Mapping) \
        else None
    if not isinstance(design_root, str) or not design_root.strip():
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, [_finding(
            REASON_INPUT_DRIFT,
            "the host context declares no candidate design root, so the stage "
            "cannot be proven disjoint from it; refusing rather than trusting it")])
    if not isinstance(repair_root, str) or not repair_root.strip():
        return refuse(PHASE_SNAPSHOT, STATUS_BLOCKED, [_finding(
            REASON_INPUT_DRIFT,
            "the host context declares no repair root, so a snapshot has nowhere "
            "to be taken; refusing rather than inventing a location")])
    try:
        overlap = _stage_candidate_overlap(stage_root, design_root)
    except (OSError, ValueError) as exc:
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, [_finding(
            REASON_INPUT_DRIFT,
            "the stage root and the candidate design root could not be compared: %s"
            % exc)])
    if overlap is not None:
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, [_finding(
            REASON_INPUT_DRIFT,
            "the writer's stage is not disjoint from the candidate: %s "
            "(stage=%s design_root=%s); a round that stops before COMMIT must not "
            "be able to have modified the candidate"
            % (_OVERLAP_DETAIL[overlap], Path(stage_root).resolve(),
               Path(design_root).resolve()))])
    receipt["stage_root"] = str(Path(stage_root).resolve())
    receipt["candidate_design_root"] = str(Path(design_root).resolve())

    # The op-list must already live inside the stage.  The stage is re-seeded
    # from the snapshot in SNAPSHOT, so an op-list from anywhere else would not
    # survive the re-seed, and the writer would be handed a path that no longer
    # exists.  Proving it here means the round refuses before copying anything.
    oplist_source = Path(oplist_path)
    if not oplist_source.is_file():
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, [_finding(
            REASON_INPUT_DRIFT,
            "the op-list path is missing or is not a file: %s" % oplist_path)])
    try:
        oplist_source.resolve().relative_to(Path(stage_root).resolve())
    except ValueError:
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, [_finding(
            REASON_INPUT_DRIFT,
            "the op-list path lies outside the stage root it must be run from")])

    # NOTE: the containment check for the stage target lives ONCE, further down,
    # immediately before the proposal parse. An earlier version of this file
    # carried a second copy here, and that copy was DEAD: it resolved and
    # validated a `target_path` that nothing read, because BEFORE had already
    # moved to the snapshot. A check that can only refuse and can never permit is
    # not a second guard, it is a second place to look. Removed.

    # ---- PRECHECK ----------------------------------------------------------
    # The request was validated and read above.  What follows settles the
    # stage/candidate separation; the BEFORE observation is taken in SNAPSHOT,
    # from bytes fixed before any writer exists.
    # Containment for the target, enforced here and not left to the adapter.
    try:
        resolved_root = Path(stage_root).resolve()
        target_path = (resolved_root / stage_target).resolve()
        target_path.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, [_finding(
            REASON_INPUT_DRIFT,
            "the stage target escapes the stage root and will not be read: %s" % exc)])

    try:
        proposal = parse_proposal(bytes(proposal_raw))
        symbol_digest = host_context["candidate_symbol_digest"]
    except KeyError:
        return refuse(PHASE_PRECHECK, STATUS_BLOCKED, [_finding(
            REASON_INPUT_DRIFT,
            "the host context carries no candidate_symbol_digest")])
    except RepairContractError as exc:
        # Carry the contract's OWN findings through, not str(exc).  RepairContractError
        # stringifies to its reason CODES joined by "; " ("REPAIR_SCHEMA_INVALID"),
        # so the receipt was naming the class of refusal while discarding which
        # field was wrong -- the one piece of information the caller acts on.
        findings = list(getattr(exc, "findings", None) or ())
        if not findings:
            findings = [_finding(REASON_INPUT_DRIFT, str(exc))]
        return refuse(PHASE_PRECHECK, STATUS_UNKNOWN, findings)

    # ---- SNAPSHOT ----------------------------------------------------------
    # Contract order is PRECHECK -> SNAPSHOT -> STAGE_APPLY
    # (akcli_adapter.py:1354).  The snapshot is taken before any writer exists.
    #
    # BEFORE is read from the snapshot, not from the stage.  Reading it from the
    # stage made the round's before and its after the same file observed either
    # side of one write: self-consistent, but it left the bytes the authorization
    # was computed against unfixed.  C3 already expects a snapshot_root distinct
    # from stage_root (_BINDING_REQUEST_FIELDS) and names the roles "BEFORE from
    # the snapshot root, AFTER from the stage root" (:1403); this adopts that.
    #
    # The snapshot lands under repair_root, never inside the candidate, and is
    # held to the same disjointness rule as the stage: a snapshot of the
    # candidate that lives inside the candidate is not a record of anything.
    try:
        snapshot_root, snapshot_manifest = materialise_snapshot(
            design_root, Path(repair_root) / "snapshot", stage_target)
        stage_seeding = Path(stage_root)
        # The op-list is not part of the design, so re-seeding the stage deletes
        # it.  It is the caller's, and it is what the writer is authorised to
        # execute, so it is read into memory BEFORE the re-seed and written back
        # after.  Copying it from the stage afterwards reads a file this function
        # has just deleted -- which is exactly what happened, and presented as a
        # caller's missing file rather than as our own ordering.
        op_list_bytes = oplist_source.read_bytes()
        if stage_seeding.exists():
            shutil.rmtree(stage_seeding)
        shutil.copytree(snapshot_root, stage_seeding)
        re_seeded_oplist = stage_seeding / oplist_source.name
        re_seeded_oplist.write_bytes(op_list_bytes)
        stage_manifest = build_file_manifest(stage_seeding, stage_target)
        op_list = str(re_seeded_oplist)
        before_raw = (Path(snapshot_root) / stage_target).read_bytes()
        before_sha = hash_bytes(before_raw)
    except RepairContractError as exc:
        # The contract's own findings, which name the refusal.
        return refuse(PHASE_SNAPSHOT, STATUS_BLOCKED,
                      list(getattr(exc, "findings", None) or ()))
    except OSError as exc:
        # OSError is reported separately from RepairContractError on purpose.
        # These three operations -- copy the tree, seed the stage, read BEFORE
        # out of the snapshot -- are ours, so a bare "[Errno 2] No such file"
        # reads as a caller's missing file. It is not: earlier in this round a
        # stage re-seed deleted the op-list one line before it was copied back,
        # and the only thing the receipt said was that the file was missing.
        # Which of the three failed is the first thing anyone debugging this
        # needs to know, so it is named.
        return refuse(PHASE_SNAPSHOT, STATUS_BLOCKED, [_finding(
            REASON_INPUT_DRIFT,
            "the snapshot could not be materialised, the stage could not be "
            "seeded from it, or BEFORE could not be read out of it: %s" % exc)])
    reach(PHASE_SNAPSHOT)
    receipt["snapshot"] = {
        "root": snapshot_root,
        "manifest": snapshot_manifest,
        "target_sha256": snapshot_manifest["files"][0]["sha256"]
        if snapshot_manifest["files"] else None,
    }
    receipt["staged_manifest"] = stage_manifest
    receipt["before_source_sha256"] = before_sha

    try:
        before_observation = _c2_observe_source(before_raw)
    except Exception as exc:
        return refuse(PHASE_SNAPSHOT, STATUS_UNKNOWN, [_finding(
            REASON_INPUT_DRIFT,
            "the snapshot observation could not be established: %s" % exc)])
    if not before_observation["coverage"]["complete"]:
        return refuse(PHASE_SNAPSHOT, STATUS_BLOCKED, [_finding(
            REASON_COVERAGE_INCOMPLETE,
            "the snapshot observation is not complete, so no delta can be trusted")])

    # The binding is issued HERE, against the snapshot's observation, so the
    # authorization is computed from bytes that were fixed before it was decided.
    native_before = {"status": "PASS", "observation": before_observation,
                     "tool": {"symbol_digest": symbol_digest}}
    bound = bind_policy(host_context, proposal, native_before, policy=policy,
                        required_paths=required_paths)
    if bound["status"] == STATUS_BLOCKED:
        return refuse(PHASE_SNAPSHOT, STATUS_BLOCKED, bound["reasons"])
    reach(PHASE_PRECHECK)
    receipt.update(
        rule_id=bound["rule_id"],
        route=bound["route"],
        policy_sha256=bound["policy_sha256"],
        bound_policy_sha256=bound["bound_policy_sha256"],
        patch_sha256=bound["patch_sha256"],
        authorized_delta_sha256=bound["authorized_delta_sha256"],
    )

    # ---- STAGE_APPLY -------------------------------------------------------
    from tools import akcli_adapter  # lazy: keeps akcli off the import path

    try:
        staged = akcli_adapter.apply_stage({
            "host_patch": bound["host_patch"],
            "txn_id": txn_id,
            "stage_root": stage_root,
            "stage_target": stage_target,
            "oplist_path": op_list,
            "native_artifact_root": artifact_root,
        })
    except Exception as exc:
        return refuse(PHASE_STAGE_APPLY, STATUS_TOOL_ERROR, [_finding(
            REASON_TOOL_UNAVAILABLE, "the pinned writer could not be run: %s" % exc)])

    tool = staged.get("tool") or {}
    # Property 3: APPLIED_TO_STAGE alone is NOT success.  exit_code 0 with
    # tool_applied False, or changed False, means the writer did not write.
    applied = _stage_write_succeeded(staged)
    receipt["stage"] = {
        "status": staged.get("status"),
        "tool_applied": tool.get("tool_applied"),
        "exit_code": tool.get("exit_code"),
        "changed": staged.get("changed"),
        "before_source_sha256": staged.get("before_source_sha256"),
        "after_source_sha256": staged.get("after_source_sha256"),
        "reasons": staged.get("reasons") or [],
    }
    if not applied:
        status = _STAGE_REFUSAL_STATUS.get(staged.get("status"), STATUS_UNKNOWN)
        findings = list(staged.get("reasons") or []) or [_finding(
            REASON_TOOL_PROTOCOL_ERROR,
            "the writer did not apply the authorized op-list "
            "(status=%r tool_applied=%r exit_code=%r changed=%r)"
            % (staged.get("status"), tool.get("tool_applied"),
               tool.get("exit_code"), staged.get("changed")))]
        return refuse(PHASE_STAGE_APPLY, status, findings)
    reach(PHASE_STAGE_APPLY)

    # ---- DELTA_CHECK -------------------------------------------------------
    # AFTER is read back from the bytes the writer produced.  It is never
    # hand-constructed and never taken from the writer's own claim.
    try:
        after_raw = target_path.read_bytes()
        after_observation = _c2_observe_source(after_raw)
    except Exception as exc:
        return refuse(PHASE_DELTA_CHECK, STATUS_UNKNOWN, [_finding(
            REASON_INPUT_DRIFT, "the after state could not be observed: %s" % exc)])

    verdict = compare_delta(before_observation, after_observation,
                            bound["host_patch"]["bound_policy"])
    receipt["verification"] = {
        "status": verdict["status"],
        "authorized_delta_sha256": verdict["authorized_delta_sha256"],
        "actual_delta_sha256": verdict["actual_delta_sha256"],
        "missing": verdict["missing"],
        "unexpected": verdict["unexpected"],
        "coverage_complete": verdict["coverage_complete"],
        "reasons": verdict["reasons"],
    }
    receipt["after_source_sha256"] = hash_bytes(after_raw)

    if verdict["status"] == "UNKNOWN":
        return refuse(PHASE_DELTA_CHECK, STATUS_UNKNOWN, verdict["reasons"])
    if verdict["status"] != "PASS":
        # The write is real but the stage is not the authorized stage, so it is
        # discarded rather than promoted.  The generic verdict reason is kept AND
        # the concrete divergence is added (PR1-C5-M7 criterion 5), so a reader
        # of this receipt learns what actually deviated and not merely that
        # something did.
        status, cause, reasons = _delta_refusal(verdict)
        return refuse(PHASE_DELTA_CHECK, status, reasons, cause_status=cause)
    reach(PHASE_DELTA_CHECK)

    # ---- KICAD_VERIFY ------------------------------------------------------
    # An EVIDENCE GENERATOR, not a gate (PR1-C5-KICAD-VERIFY).  It runs the bound
    # kicad-cli and records what happened; it does not decide anything, and
    # nothing below this point changes the round's status because of it.
    #
    # The reason is measured, not stylistic: KiCad's standard ERC reports ZERO
    # errors on the DC-04 fixture in its defective state, and its 37 warnings are
    # all library-resolution noise. A phase that gated on that number would be
    # green on a broken board. So the artifact records the counts WITH their
    # categories, the tool's own measured identity, and what it does not
    # establish.
    #
    # The kicad identity is read from the validated host binding, NOT from
    # host_patch["toolchain_manifest"]: that slice is akcli-only and carries no
    # kicad entry, so toolchain_sha256 does not commit to the kicad binary. That
    # gap is reported in the artifact rather than repaired here.
    # The declared timeout is an int on toolchain_manifest["timeout_seconds"]
    # (measured, not assumed -- an earlier version of this line assumed a nested
    # mapping and silently fell back to 120 instead of honouring the declared
    # 60). A missing or non-positive value falls back, and says so in the
    # artifact, rather than being coerced.
    declared_timeout = bound["host_patch"]["toolchain_manifest"].get(
        "timeout_seconds")
    if isinstance(declared_timeout, int) and not isinstance(
            declared_timeout, bool) and declared_timeout > 0:
        kicad_timeout = declared_timeout
    else:
        kicad_timeout = 120
    try:
        kicad_evidence = kicad_verify_evidence(
            toolchain_binding=host_context.get("toolchain_binding"),
            project_root=Path(stage_root),
            target=stage_target,
            artifact_root=Path(artifact_root) / "kicad_verify",
            timeout_seconds=kicad_timeout,
        )
    except Exception as exc:      # never let evidence gathering end the round
        kicad_evidence = {
            "phase": PHASE_KICAD_VERIFY,
            "role": "evidence-generator",
            "decides": None,
            "tool_identity": None,
            "erc": None,
            "netlist": None,
            "render": None,
            "timeout_seconds": kicad_timeout,
            "limitations": list(_KICAD_VERIFY_LIMITATIONS),
            "detail": "the evidence could not be gathered: %s" % exc,
        }
    receipt["kicad_verify"] = kicad_evidence
    reach(PHASE_KICAD_VERIFY)

    # Verified at stage, not committed: no terminal status exists yet.
    receipt.update(status=None, phase=PHASE_KICAD_VERIFY, cause_status=None,
                   terminal=False, reasons=[])
    receipt["pending_phases"] = list(ROUND_PENDING_PHASES)
    receipt["feedback"] = public_feedback({
        "context_id": host_context["context_id"],
        "status": None,
        "cause_status": None,
    })
    return receipt
