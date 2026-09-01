"""Normalization of the EDD-001 policy document into immutable records.

Normalization is deny-by-default in two senses:

1. The document must satisfy ``contracts/domain_policy_schema_v1.json``; any
   violation raises ``PolicyDocumentError``.
2. Beyond the schema, two authoritative declarations that disagree also raise.
   An ambiguous policy is not a policy: it fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .errors import PolicyDocumentError
from .schema import iter_violations, load_schema

__all__ = [
    "ActiveRule",
    "ComponentRecord",
    "CompilerRecord",
    "FilePolicy",
    "ParameterRecord",
    "PinPolicy",
    "PolicyDocument",
    "Prerequisites",
    "ToolRecord",
    "VerifierRecord",
    "normalize_document",
]

_PIN_CLASSES = ("allowed", "core_reserved", "hard_forbidden", "soft_reserved")


@dataclass(frozen=True)
class ComponentRecord:
    mpn: str
    role: str
    required_evidence_ids: tuple[str, ...]
    requires_resolution: bool = False

    @property
    def identity(self) -> str:
        return self.mpn


@dataclass(frozen=True)
class ParameterRecord:
    parameter_id: str
    value_type: str
    unit: str
    required_evidence_ids: tuple[str, ...]
    minimum: float | None = None
    maximum: float | None = None
    allowed_values: tuple[Any, ...] = ()

    @property
    def identity(self) -> str:
        return self.parameter_id

    def accepts(self, value: Any) -> bool:
        """Exact value check. Never coerces, never matches prefixes.

        Non-finite floats (NaN/±inf) are refused unconditionally: they compare
        False against every bound and would otherwise pass both minimum and
        maximum range checks while matching no allowed value.
        """
        import math

        if isinstance(value, float) and not math.isfinite(value):
            return False
        if self.allowed_values:
            return any(_same_value(value, allowed) for allowed in self.allowed_values)
        if self.minimum is not None and value < self.minimum:
            return False
        if self.maximum is not None and value > self.maximum:
            return False
        return self.minimum is not None or self.maximum is not None


@dataclass(frozen=True)
class ToolRecord:
    tool_id: str
    tool_version: str
    capability: str

    @property
    def identity(self) -> tuple[str, str]:
        return (self.tool_id, self.tool_version)


@dataclass(frozen=True)
class CompilerRecord:
    compiler_id: str
    compiler_version: str
    output_kind: str
    required_coverage_ids: tuple[str, ...]

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.compiler_id, self.compiler_version, self.output_kind)


@dataclass(frozen=True)
class VerifierRecord:
    verifier_id: str
    verifier_version: str
    artifact_kind: str
    coverage_ids: tuple[str, ...]

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.verifier_id, self.verifier_version, self.artifact_kind)


@dataclass(frozen=True)
class PinPolicy:
    allowed: frozenset[str]
    core_reserved: frozenset[str]
    hard_forbidden: frozenset[str]
    soft_reserved: frozenset[str]
    rule_sources: Mapping[str, str] = field(default_factory=dict)

    def source_for(self, pin: str) -> str:
        return self.rule_sources.get(pin, "")


@dataclass(frozen=True)
class FilePolicy:
    candidate_root_only: bool
    direct_kicad_write: bool
    allowed_artifact_kinds: frozenset[str]
    agent_forbidden_artifact_kinds: frozenset[str]


@dataclass(frozen=True)
class Prerequisites:
    required_contract_ids: tuple[str, ...]
    required_evidence_ids: tuple[str, ...]
    required_component_resolutions: tuple[str, ...]


@dataclass(frozen=True)
class ActiveRule:
    rule_id: str
    source_contract_id: str
    kind: str
    fingerprint: str

    @property
    def identity(self) -> str:
        return self.rule_id


@dataclass(frozen=True)
class PolicyDocument:
    schema_version: int
    domain_id: str
    board_id: str
    components: Mapping[str, ComponentRecord]
    pins: PinPolicy
    parameters: Mapping[str, ParameterRecord]
    file_policy: FilePolicy
    tools: tuple[ToolRecord, ...]
    compilers: tuple[CompilerRecord, ...]
    verifiers: tuple[VerifierRecord, ...]
    prerequisites: Prerequisites
    available_contract_ids: frozenset[str]
    available_evidence_ids: frozenset[str]
    active_rules: tuple[ActiveRule, ...]

    def missing_contract_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(set(self.prerequisites.required_contract_ids) - self.available_contract_ids)
        )

    def missing_evidence_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(set(self.prerequisites.required_evidence_ids) - self.available_evidence_ids)
        )

    def missing_evidence_for(self, required: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(required) - self.available_evidence_ids))

    def compilers_for(self, output_kind: str) -> tuple[CompilerRecord, ...]:
        return tuple(c for c in self.compilers if c.output_kind == output_kind)

    def verifiers_for(self, artifact_kind: str) -> tuple[VerifierRecord, ...]:
        return tuple(v for v in self.verifiers if v.artifact_kind == artifact_kind)

    def coverage_for(self, artifact_kind: str) -> frozenset[str]:
        covered: set[str] = set()
        for verifier in self.verifiers_for(artifact_kind):
            covered.update(verifier.coverage_ids)
        return frozenset(covered)


def _same_value(left: Any, right: Any) -> bool:
    """Exact equality that refuses to equate booleans with numbers.

    Numeric int/float spellings of the same value are accepted (an authored
    ``10000`` and ``10000.0`` are the same resistance); every other type pair
    must match exactly. Prefix, case and whitespace variants never match.
    """
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    return type(left) is type(right) and left == right


def _as_str_tuple(values: Any) -> tuple[str, ...]:
    return tuple(str(value) for value in values)


def _index(
    records: tuple[Any, ...],
    conflicts: list[str],
    label: str,
) -> Mapping[Any, Any]:
    indexed: dict[Any, Any] = {}
    for record in records:
        key = record.identity
        existing = indexed.get(key)
        if existing is None:
            indexed[key] = record
        elif existing != record:
            conflicts.append(f"conflicting duplicate {label} {key!r}")
    return indexed


def _check_pin_classes(pins: Mapping[str, Any], conflicts: list[str]) -> None:
    for left_index, left in enumerate(_PIN_CLASSES):
        for right in _PIN_CLASSES[left_index + 1 :]:
            overlap = sorted(set(pins[left]) & set(pins[right]))
            if overlap:
                conflicts.append(
                    f"pin(s) {overlap} declared in both {left} and {right}"
                )


def normalize_document(raw: Any, *, schema: Mapping[str, Any] | None = None) -> PolicyDocument:
    """Validate and normalize a policy document, or fail closed."""
    if not isinstance(raw, Mapping):
        raise PolicyDocumentError("policy document must be a JSON object")

    active_schema = load_schema() if schema is None else schema
    violations = iter_violations(raw, active_schema)
    if violations:
        raise PolicyDocumentError("policy document violates the normalized schema", violations=violations)

    conflicts: list[str] = []

    components = _index(
        tuple(
            ComponentRecord(
                mpn=str(item["mpn"]),
                role=str(item["role"]),
                required_evidence_ids=_as_str_tuple(item["required_evidence_ids"]),
                requires_resolution=bool(item.get("requires_resolution", False)),
            )
            for item in raw["allowed_components"]
        ),
        conflicts,
        "component mpn",
    )

    parameters = _index(
        tuple(
            ParameterRecord(
                parameter_id=str(item["parameter_id"]),
                value_type=str(item["value_type"]),
                unit=str(item["unit"]),
                required_evidence_ids=_as_str_tuple(item["required_evidence_ids"]),
                minimum=None if item.get("minimum") is None else float(item["minimum"]),
                maximum=None if item.get("maximum") is None else float(item["maximum"]),
                allowed_values=tuple(item.get("allowed_values", ())),
            )
            for item in raw["parameters"]
        ),
        conflicts,
        "parameter id",
    )

    tools = tuple(
        ToolRecord(
            tool_id=str(item["tool_id"]),
            tool_version=str(item["tool_version"]),
            capability=str(item["capability"]),
        )
        for item in raw["tools"]
    )
    compilers = tuple(
        CompilerRecord(
            compiler_id=str(item["compiler_id"]),
            compiler_version=str(item["compiler_version"]),
            output_kind=str(item["output_kind"]),
            required_coverage_ids=_as_str_tuple(item["required_coverage_ids"]),
        )
        for item in raw["compilers"]
    )
    verifiers = tuple(
        VerifierRecord(
            verifier_id=str(item["verifier_id"]),
            verifier_version=str(item["verifier_version"]),
            artifact_kind=str(item["artifact_kind"]),
            coverage_ids=_as_str_tuple(item["coverage_ids"]),
        )
        for item in raw["verifiers"]
    )

    _index(tools, conflicts, "tool id/version")
    _index(compilers, conflicts, "compiler id/version/output")
    _index(verifiers, conflicts, "verifier id/version/artifact")

    raw_pins = raw["pins"]
    pins = PinPolicy(
        allowed=frozenset(_as_str_tuple(raw_pins["allowed"])),
        core_reserved=frozenset(_as_str_tuple(raw_pins["core_reserved"])),
        hard_forbidden=frozenset(_as_str_tuple(raw_pins["hard_forbidden"])),
        soft_reserved=frozenset(_as_str_tuple(raw_pins["soft_reserved"])),
        rule_sources={str(k): str(v) for k, v in raw_pins.get("rule_sources", {}).items()},
    )
    _check_pin_classes(
        {
            "allowed": pins.allowed,
            "core_reserved": pins.core_reserved,
            "hard_forbidden": pins.hard_forbidden,
            "soft_reserved": pins.soft_reserved,
        },
        conflicts,
    )

    active_rules = tuple(
        ActiveRule(
            rule_id=str(item["rule_id"]),
            source_contract_id=str(item["source_contract_id"]),
            kind=str(item["kind"]),
            fingerprint=str(item["fingerprint"]),
        )
        for item in raw["active_rules"]
    )
    _index(active_rules, conflicts, "active rule id")

    if conflicts:
        raise PolicyDocumentError(
            "policy document contains conflicting authoritative declarations",
            violations=tuple(conflicts),
        )

    file_policy = FilePolicy(
        candidate_root_only=bool(raw["file_policy"]["candidate_root_only"]),
        direct_kicad_write=bool(raw["file_policy"]["direct_kicad_write"]),
        allowed_artifact_kinds=frozenset(_as_str_tuple(raw["file_policy"]["allowed_artifact_kinds"])),
        agent_forbidden_artifact_kinds=frozenset(
            _as_str_tuple(raw["file_policy"]["agent_forbidden_artifact_kinds"])
        ),
    )

    prerequisites = Prerequisites(
        required_contract_ids=_as_str_tuple(raw["prerequisites"]["required_contract_ids"]),
        required_evidence_ids=_as_str_tuple(raw["prerequisites"]["required_evidence_ids"]),
        required_component_resolutions=_as_str_tuple(
            raw["prerequisites"]["required_component_resolutions"]
        ),
    )

    return PolicyDocument(
        schema_version=int(raw["schema_version"]),
        domain_id=str(raw["domain_id"]),
        board_id=str(raw["board_id"]),
        components=components,
        pins=pins,
        parameters=parameters,
        file_policy=file_policy,
        tools=tools,
        compilers=compilers,
        verifiers=verifiers,
        prerequisites=prerequisites,
        available_contract_ids=frozenset(_as_str_tuple(raw["available"]["contract_ids"])),
        available_evidence_ids=frozenset(_as_str_tuple(raw["available"]["evidence_ids"])),
        active_rules=active_rules,
    )
