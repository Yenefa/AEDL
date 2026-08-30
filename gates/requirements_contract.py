"""Requirements contract: fail-closed helpers for the NL -> intent provenance gate.

Phase 1 of the open-source intake plan (CircuitBot clarify absorption).
Semantics are the deliberate inversion of CircuitBot's clarify node
(notes/open_source_intake/circuitbot.md STEP 5):

- an unanswered blocking question is a FAIL, never a timeout-continue;
- "No preference"/"unknown" answers must be recorded, never dropped;
- the contract is an artifact on disk, never in-memory agent state;
- the intent must reference the contract by its self-hash;
- validators are deterministic; LLM output is advisory input only
  (see gates/requirements_runtime.py for the advisory layer).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REQUIREMENTS_CONTRACT_SCHEMA = "https://aedl.local/schemas/requirements-contract.v1.json"
REQUIREMENTS_CONTRACT_EVIDENCE_SCHEMA = "https://aedl.local/schemas/requirements-contract-evidence.v1.json"

CONTRACT_MAX_AGE_DAYS = 7  # aligned with BOM freshness semantics

# ---------------------------------------------------------------------------
# Semantic binding (part of C4): what the contract is signed against.
#
# The lockfile binding alone is not enough. It proves the intent points at this
# contract, but nothing proves the contract was signed against THIS circuit:
# edit `components` (swap a part, add a part) while leaving the old
# requirements_contract reference in place and the gate still passes. The
# contract then claims to describe a board it has never seen.
#
# Fix: the contract also records a hash of the intent's SEMANTIC fields, so any
# circuit change invalidates the signature and forces a re-sign.
#
# HARD-CODED WHITELIST CONVENTION - `components` and `nets` only:
#
#   components : {ref: {lib_id, value, ...}}  what is physically on the board
#   nets       : {net: [pins]}                how those parts are connected
#
# Deliberately EXCLUDED (and why):
#
#   requirements_contract : {sha256, path}
#       The binding field itself. Hashing it would re-create the exact circular
#       dependency the lockfile pattern exists to avoid:
#         contract_sha256 -> intent_binding -> intent semantic hash ->
#         requirements_contract.sha256 -> contract_sha256.
#       Excluding it is also what makes "repoint the binding, keep the circuit"
#       a legal no-re-sign operation.
#   protocol_version (and any future metadata)
#       Not circuit semantics. A protocol bump must not silently invalidate
#       every signed board in the fleet.
#
# MAINTENANCE CONTRACT (two directions, both mandatory):
#   - When the intent protocol gains a field that describes circuit semantics,
#     add it here; until then the gate is blind to that field.
#   - Adding a field here changes every semantic hash, which invalidates every
#     signed contract at once: all boards must be re-signed in the same change.
# ---------------------------------------------------------------------------
INTENT_SEMANTIC_FIELDS = ("components", "nets")

# intent_binding must carry exactly these keys.
INTENT_BINDING_FIELDS = frozenset({"intent_path", "intent_semantic_sha256"})

_STATEMENT_TYPES = (
    "power", "mcu", "sensor", "connectivity", "display", "formfactor", "other",
)
_TOP_LEVEL_FIELDS = (
    "$schema", "schema_version", "board_id", "created_at", "author",
    "user_goal", "source_statements", "resolved_requirements",
    "open_questions", "assumptions", "forbidden_assumptions",
    "intent_binding", "contract_sha256",
)
_SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")

# Keywords used by check C6 (forbidden_assumption enforcement). v1 keeps this
# explainable keyword-level mapping; structural matching is deferred (decision
# point 3, 2026-08-31).
_FORBIDDEN_KEYWORD_MAP = {
    "wifi": ("wifi", "wi-fi", "802.11"),
    "wireless": ("wifi", "wi-fi", "802.11", "esp32", "esp8266", "nrf24"),
    "bluetooth": ("bluetooth", "ble"),
    "display": ("display", "oled", "lcd", "e-ink", "epaper"),
    "debugger": ("debugger", "jtag", "swd", "debug probe"),
    "battery": ("battery", "lipo", "coin cell"),
}


def _read_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def compute_contract_sha256(contract: Dict[str, Any]) -> str:
    """Self-hash: sha256 over the canonical JSON with contract_sha256 removed."""
    payload = {key: contract[key] for key in contract if key != "contract_sha256"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def intent_semantic_sha256(intent: Dict[str, Any]) -> str:
    """Hash the circuit semantics of an intent: `components` and `nets` only.

    See INTENT_SEMANTIC_FIELDS for the whitelist and its rationale. The result
    depends on the intent alone, never on the contract, which is what keeps the
    binding one-directional:

        intent --{sha256,path}--> contract            (lockfile, C4)
        contract --{semantic hash of intent}--> intent (semantic lock, C4)

    Neither side can be computed from the other's own hash, so there is no
    circular dependency and no iteration needed to sign.

    A whitelisted field that is absent hashes as null rather than being
    skipped: a structurally broken intent must not silently hash the same as a
    valid one.
    """
    payload = {field: intent.get(field) for field in INTENT_SEMANTIC_FIELDS}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_id_list(value: Any, field: str, errors: List[str]) -> List[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{field} must be a list of non-empty strings")
        return []
    return list(value)


def _parse_iso8601(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def validate_requirements_contract(
    contract_path: Path,
    intent_path: Path,
    now: Optional[datetime] = None,
) -> List[str]:
    """Deterministic checks C1-C7. Any structural surprise is an error, never a pass."""
    errors: List[str] = []
    try:
        contract = _read_json(contract_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"contract unreadable: {exc}"]

    now = now or datetime.now(timezone.utc)

    # C1: schema, version, top-level completeness, primitive typing.
    if contract.get("$schema") != REQUIREMENTS_CONTRACT_SCHEMA:
        errors.append("contract $schema mismatch")
    if contract.get("schema_version") != 1:
        errors.append("contract schema_version must be 1")
    missing = sorted(set(_TOP_LEVEL_FIELDS) - set(contract))
    unknown = sorted(set(contract) - set(_TOP_LEVEL_FIELDS))
    if missing:
        errors.append(f"contract missing fields: {missing}")
    if unknown:
        errors.append(f"contract has unknown fields: {unknown}")
    for field in ("board_id", "author", "user_goal"):
        if not isinstance(contract.get(field), str) or not contract[field].strip():
            errors.append(f"contract has no {field}")

    # C5: freshness (same 7-day semantics as BOM evidence).
    created_at = contract.get("created_at")
    if not isinstance(created_at, str):
        errors.append("contract created_at must be an ISO8601 string")
    else:
        parsed = _parse_iso8601(created_at)
        if parsed is None:
            errors.append("contract created_at is not a tz-aware ISO8601 timestamp")
        elif parsed > now + timedelta(minutes=5):
            errors.append("contract created_at is in the future")
        elif parsed < now - timedelta(days=CONTRACT_MAX_AGE_DAYS):
            errors.append(
                f"contract is stale (> {CONTRACT_MAX_AGE_DAYS} days); re-confirm with the user"
            )

    # Statement registry.
    statement_ids: set = set()
    statements = contract.get("source_statements")
    if not isinstance(statements, list) or not statements:
        errors.append("contract source_statements must be a non-empty list")
        statements = []
    for index, statement in enumerate(statements):
        if not isinstance(statement, dict):
            errors.append(f"source_statements[{index}] must be an object")
            continue
        if set(statement) != {"id", "text", "type"}:
            errors.append(f"source_statements[{index}] must contain exactly id/text/type")
            continue
        if not isinstance(statement["id"], str) or not statement["id"]:
            errors.append(f"source_statements[{index}] has empty id")
            continue
        if statement["id"] in statement_ids:
            errors.append(f"duplicate statement id {statement['id']}")
        statement_ids.add(statement["id"])
        if not isinstance(statement["text"], str) or not statement["text"].strip():
            errors.append(f"source_statements[{statement['id']}] has empty text")
        if statement["type"] not in _STATEMENT_TYPES:
            errors.append(f"source_statements[{statement['id']}] has unknown type {statement['type']!r}")

    def check_source_ids(owner: str, source_ids: Any) -> None:
        ids = _validate_id_list(source_ids, f"{owner} source_ids", errors)
        dangling = [sid for sid in ids if sid not in statement_ids]
        if dangling:
            errors.append(f"{owner} references unknown statements: {dangling}")

    # resolved_requirements: every claim must trace back to statements or answers.
    requirements = contract.get("resolved_requirements")
    if not isinstance(requirements, list):
        errors.append("contract resolved_requirements must be a list")
        requirements = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            errors.append(f"resolved_requirements[{index}] must be an object")
            continue
        if set(requirement) != {"id", "text", "source_ids"}:
            errors.append(f"resolved_requirements[{index}] must contain exactly id/text/source_ids")
            continue
        if not isinstance(requirement["id"], str) or not requirement["id"]:
            errors.append(f"resolved_requirements[{index}] has empty id")
        if not isinstance(requirement["text"], str) or not requirement["text"].strip():
            errors.append(f"resolved_requirements[{requirement['id']}] has empty text")
        check_source_ids(f"resolved_requirements[{requirement['id']}]", requirement["source_ids"])

    # C3: blocking questions must carry an explicit answer.
    questions = contract.get("open_questions")
    if not isinstance(questions, list):
        errors.append("contract open_questions must be a list")
        questions = []
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            errors.append(f"open_questions[{index}] must be an object")
            continue
        if set(question) != {"id", "question", "answer", "kind", "source_ids"}:
            errors.append(
                f"open_questions[{index}] must contain exactly id/question/answer/kind/source_ids"
            )
            continue
        if not isinstance(question["id"], str) or not question["id"]:
            errors.append(f"open_questions[{index}] has empty id")
        if not isinstance(question["question"], str) or not question["question"].strip():
            errors.append(f"open_questions[{question['id']}] has empty question text")
        kind = question["kind"]
        if kind not in ("blocking", "nonblocking"):
            errors.append(f"open_questions[{question['id']}] has unknown kind {kind!r}")
        answer = question["answer"]
        if kind == "blocking":
            if not isinstance(answer, str) or not answer.strip():
                errors.append(
                    f"blocking question {question['id']} is unanswered (explicit 'unknown' allowed, "
                    "empty is not - CircuitBot would proceed; AEDL must stop)"
                )
        else:
            # Nonblocking answers may be empty but must be explicit strings.
            if not isinstance(answer, str):
                errors.append(f"open_questions[{question['id']}] answer must be a string")
        check_source_ids(f"open_questions[{question['id']}]", question["source_ids"])

    # C7: assumptions must be explicit records, never implicit.
    assumptions = contract.get("assumptions")
    if not isinstance(assumptions, list):
        errors.append("contract assumptions must be a list")
        assumptions = []
    for index, assumption in enumerate(assumptions):
        if not isinstance(assumption, dict):
            errors.append(f"assumptions[{index}] must be an object")
            continue
        if set(assumption) != {"id", "text", "source_ids", "status"}:
            errors.append(f"assumptions[{index}] must contain exactly id/text/source_ids/status")
            continue
        if not isinstance(assumption["id"], str) or not assumption["id"]:
            errors.append(f"assumptions[{index}] has empty id")
        if not isinstance(assumption["text"], str) or not assumption["text"].strip():
            errors.append(f"assumptions[{assumption['id']}] has empty text")
        if assumption["status"] != "recorded":
            errors.append(
                f"assumptions[{assumption['id']}] status must be 'recorded' "
                "(implicit assumptions are how silent MCU injection happens)"
            )
        check_source_ids(f"assumptions[{assumption['id']}]", assumption["source_ids"])

    forbidden = contract.get("forbidden_assumptions")
    if not isinstance(forbidden, list) or any(
        not isinstance(item, str) or not item.strip() for item in forbidden
    ):
        errors.append("contract forbidden_assumptions must be a list of non-empty strings")

    # contract_sha256 self-hash integrity.
    declared_hash = contract.get("contract_sha256")
    if not isinstance(declared_hash, str) or not _SHA256_RE.fullmatch(declared_hash):
        errors.append("contract contract_sha256 is malformed")
    elif compute_contract_sha256(contract) != declared_hash:
        errors.append("contract contract_sha256 mismatch (contract tampered or stale)")

    # C4: the intent must reference this exact contract revision, AND the
    # contract must have been signed against this exact circuit.
    # Binding is deliberately one-directional (lockfile pattern): the intent
    # holds {sha256, path} of the contract. A mutual hash would be circular
    # (contract hash -> intent_binding -> intent hash -> contract reference).
    # The semantic hash is the other half: it hashes only the circuit fields of
    # the intent (see INTENT_SEMANTIC_FIELDS), so it is computable without
    # reading the contract and introduces no cycle.
    intent_relative = None
    binding = contract.get("intent_binding")
    if not isinstance(binding, dict):
        errors.append("contract intent_binding must be an object")
    else:
        if set(binding) != INTENT_BINDING_FIELDS:
            errors.append(
                "contract intent_binding must contain exactly "
                + ", ".join(sorted(INTENT_BINDING_FIELDS))
            )
        intent_relative = binding.get("intent_path")
        if not isinstance(intent_relative, str) or not intent_relative.strip():
            errors.append("contract intent_binding.intent_path is empty")
            intent_relative = None
        declared_semantic = binding.get("intent_semantic_sha256")
        if not isinstance(declared_semantic, str) or not _SHA256_RE.fullmatch(declared_semantic):
            errors.append("contract intent_binding.intent_semantic_sha256 is malformed")
            declared_semantic = None
        if intent_path is not None and intent_relative is not None:
            try:
                intent_data = _read_json(intent_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"bound intent unreadable: {exc}")
            else:
                # C4 semantic lock: the circuit the contract was signed against
                # must be the circuit on disk. Without this, swapping a part in
                # `components` while keeping the old contract reference passes.
                if declared_semantic is not None:
                    current_semantic = intent_semantic_sha256(intent_data)
                    if current_semantic != declared_semantic:
                        errors.append(
                            "intent 语义内容已变更，须重签合同 "
                            f"(intent semantic sha256 mismatch: contract recorded "
                            f"{declared_semantic[:12]}…, intent computes "
                            f"{current_semantic[:12]}…)"
                        )

                reference = intent_data.get("requirements_contract")
                if not isinstance(reference, dict) or set(reference) != {"sha256", "path"}:
                    errors.append(
                        "intent has no requirements_contract {sha256, path} reference"
                    )
                else:
                    # The intent's reference names the contract file (from the
                    # intent's own perspective); the contract's binding names the
                    # intent file. Both are repo-relative paths cross-confirmed
                    # against the files actually passed to this gate.
                    contract_relative = _relative_to_root(contract_path)
                    if reference.get("path") != contract_relative:
                        errors.append(
                            "intent requirements_contract path does not point back at this contract"
                        )
                    elif reference.get("sha256") != declared_hash:
                        errors.append(
                            "intent requirements_contract sha256 does not match this contract"
                        )

                # C6: forbidden assumptions must not surface in the intent.
                errors.extend(_check_forbidden_in_intent(intent_data, forbidden or []))

    return errors


def _relative_to_root(path: Path) -> str:
    """Repo-relative POSIX path (forward slashes) so JSON references stay portable."""
    resolved = Path(path).resolve()
    root = Path(__file__).resolve().parents[1]
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return resolved.name
    return "/".join(relative.parts)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_forbidden_in_intent(intent_data: Dict[str, Any], forbidden: List[str]) -> List[str]:
    """C6: keyword-level mapping between prohibition phrases and intent content."""
    errors: List[str] = []
    text_haystack = _intent_text(intent_data)
    lowered = text_haystack.lower()
    for phrase in forbidden:
        for keyword, needles in _FORBIDDEN_KEYWORD_MAP.items():
            if keyword in phrase.lower():
                for needle in needles:
                    if needle in lowered:
                        errors.append(
                            f"forbidden assumption '{phrase}' matches intent content "
                            f"('{needle}')"
                        )
                        break
    return errors


def _intent_text(intent_data: Dict[str, Any]) -> str:
    """Flatten lib_id/value/net names into one searchable blob."""
    parts: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("lib_id", "value", "footprint") and isinstance(value, str):
                    parts.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(intent_data)
    parts.extend(str(name) for name in intent_data.get("nets", {}).keys()
                 if isinstance(intent_data.get("nets"), dict))
    return " ".join(parts)


def requirements_contract_gate_verdict(
    contract_path: Path,
    intent_path: Path,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Gate-shaped verdict for the (future) 10th gate; standalone until then."""
    errors = validate_requirements_contract(contract_path, intent_path, now=now)
    return {
        "schema": REQUIREMENTS_CONTRACT_EVIDENCE_SCHEMA,
        "status": "pass" if not errors else "fail",
        "contract_path": str(contract_path),
        "intent_path": str(intent_path),
        "contract_sha256": _declared_hash(contract_path),
        "errors": errors,
    }


def _declared_hash(contract_path: Path) -> Optional[str]:
    try:
        return _read_json(contract_path).get("contract_sha256")
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def finalize_contract(contract: Dict[str, Any]) -> Dict[str, Any]:
    """Write the self-hash into a contract dict (used by the runtime, never by the gate).

    The gate only verifies; mutation is confined to the authoring path so that
    'who computed the hash' stays auditable.
    """
    contract["contract_sha256"] = compute_contract_sha256(contract)
    return contract
