"""Deterministic policy kernel for the EDD-001 Design and Execution Sandboxes.

No LLM, no network, no subprocess, no filesystem writes, no third-party
dependency. The engine is a pure function of (normalized policy document,
request) and returns one of ALLOW / DENY / BLOCKED with stable, sorted
findings.

Outcome precedence (frozen by the task packet):

    known violation            -> DENY     (even when a prerequisite is missing)
    otherwise unproven prereq  -> BLOCKED
    everything satisfied       -> ALLOW
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from aedl_sandbox.protocol import (
    Finding,
    JsonValue,
    Outcome,
    PolicyDecision,
    PolicyRequest,
)

from . import reasons as R
from .document import PolicyDocument, normalize_document
from .paths import is_within, resolve_within

__all__ = ["SandboxPolicyEngine"]


def _is_text(value: Any) -> bool:
    return isinstance(value, str)


def _is_number(value: Any) -> bool:
    """A policy-input number must be a real int/float and must be finite.

    NaN and ±inf are rejected at subject-validation time (fail-closed DENY):
    they compare False against every bound and would otherwise slip through
    range checks (``lo <= NaN <= hi`` is False on both sides) into ALLOW.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_text_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _is_any_scalar(value: Any) -> bool:
    return _is_number(value) or _is_text(value)


# Action -> (field name, predicate). Subjects must carry exactly these fields;
# anything else is malformed and DENIED.
#
# V2 (Wave 3): ``approval_status`` (DESIGN_ASSIGN_PIN) and ``writer``
# (FILE_WRITE) remain part of the subject shape for V1 compatibility but are
# NOT authoritative. Authority for these permissions comes only from
# orchestrator-signed capability grants carried on the request
# (``PolicyRequest.actor`` + ``PolicyRequest.capability_grants``, recorded in
# the orchestrator action ledger), never from requester-filled subject fields.
SUBJECT_SPECS: dict[str, tuple[tuple[str, Callable[[Any], bool]], ...]] = {
    "PREFLIGHT": (),
    "DESIGN_SELECT_COMPONENT": (
        ("mpn", _is_text),
        ("role", _is_text),
        ("evidence_ids", _is_text_list),
    ),
    "DESIGN_ASSIGN_PIN": (
        ("pin", _is_text),
        ("function", _is_text),
        ("approval_status", _is_text),
    ),
    "DESIGN_SET_PARAMETER": (
        ("parameter_id", _is_text),
        ("value", _is_any_scalar),
        ("unit", _is_text),
        ("evidence_ids", _is_text_list),
    ),
    "COMPILE_HIR": (
        ("compiler_id", _is_text),
        ("compiler_version", _is_text),
        ("output_kind", _is_text),
        ("coverage_ids", _is_text_list),
    ),
    "VERIFY_ARTIFACT": (
        ("verifier_id", _is_text),
        ("verifier_version", _is_text),
        ("artifact_kind", _is_text),
        ("coverage_ids", _is_text_list),
    ),
    "TOOL_EXECUTE": (
        ("tool_id", _is_text),
        ("tool_version", _is_text),
        ("capability", _is_text),
    ),
    "FILE_WRITE": (
        ("path", _is_text),
        ("artifact_kind", _is_text),
        ("writer", lambda v: v in ("agent", "compiler")),
    ),
    "NETWORK_ACCESS": (
        ("destination", _is_text),
        ("purpose", _is_text),
    ),
    "SHELL_EXECUTE": (("command_class", _is_text),),
}


def _finding(code: str, message: str, source: str = R.DEFAULT_SOURCE, **details: Any) -> Finding:
    return Finding(
        code=code,
        message=message,
        source=source,
        details={key: _jsonable(value) for key, value in details.items()},
    )


def _jsonable(value: Any) -> JsonValue:
    if isinstance(value, (frozenset, set, tuple)):
        return [_jsonable(item) for item in sorted(value, key=str)]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


class _Verdict:
    """Accumulates DENY-class violations and BLOCKED-class prerequisites."""

    def __init__(self) -> None:
        self.violations: list[Finding] = []
        self.blockers: list[Finding] = []

    def deny(self, finding: Finding) -> None:
        self.violations.append(finding)

    def block(self, finding: Finding) -> None:
        self.blockers.append(finding)

    def finalize(self) -> PolicyDecision:
        key = lambda f: (f.code, f.source, f.message)  # noqa: E731
        findings = tuple(sorted(self.violations + self.blockers, key=key))
        if self.violations:
            return PolicyDecision(Outcome.DENY, sorted(self.violations, key=key)[0].code, findings)
        if self.blockers:
            return PolicyDecision(Outcome.BLOCKED, sorted(self.blockers, key=key)[0].code, findings)
        return PolicyDecision(Outcome.ALLOW, R.ALLOWED, findings)


class SandboxPolicyEngine:
    """Deny-by-default policy kernel for one normalized domain policy."""

    def __init__(
        self,
        document: PolicyDocument,
        repo_root: Path,
        *,
        verified_bundle_sha256: str = "",
    ) -> None:
        self._document = document
        self._repo_root = Path(repo_root)
        # V2 (Wave 3): identity of the trust-validated bundle manifest this
        # engine's contracts were loaded from (empty when the engine was not
        # built through the validated path, e.g. synthetic TEST_ONLY documents).
        self._verified_bundle_sha256 = verified_bundle_sha256

    # ------------------------------------------------------------------ build

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
        repo_root: Path,
        *,
        verified_bundle_sha256: str = "",
    ) -> "SandboxPolicyEngine":
        """Build an engine from a normalized policy document.

        Raises ``PolicyDocumentError`` (fail closed) instead of producing an
        engine that could answer ALLOW on untrustworthy input.
        """
        return cls(
            normalize_document(document),
            Path(repo_root),
            verified_bundle_sha256=verified_bundle_sha256,
        )

    @classmethod
    def for_edd001(cls, repo_root: Path, *, manifest_path: Path | None = None) -> "SandboxPolicyEngine":
        """Build an engine from the three frozen EDD-001 contracts.

        With ``manifest_path`` the contracts are loaded strictly bound to that
        bundle manifest: every consumed contract file must be pinned by the
        manifest and its on-disk bytes must hash to the pinned value, and the
        engine records the manifest hash as its verified-bundle identity. The
        manifest itself must already have passed
        ``FileTrustStore.validate_bundle`` (callers bind that in the adapter
        layer); this class only refuses to consume contracts that drift from
        the validated manifest.
        """
        from .edd001 import build_edd001_document, load_contracts_bound_to_manifest

        repo_root = Path(repo_root)
        if manifest_path is None:
            return cls(normalize_document(build_edd001_document(repo_root)), repo_root)
        contracts, manifest_sha256 = load_contracts_bound_to_manifest(repo_root, Path(manifest_path))
        from .edd001 import build_document_from_contracts

        document = normalize_document(build_document_from_contracts(contracts, repo_root))
        return cls(document, repo_root, verified_bundle_sha256=manifest_sha256)

    @property
    def document(self) -> PolicyDocument:
        return self._document

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def verified_bundle_sha256(self) -> str:
        """V2: identity of the trust-validated bundle manifest backing this
        engine's contracts (empty when built outside the validated path)."""
        return self._verified_bundle_sha256

    # --------------------------------------------------------------- evaluate

    def preflight(
        self,
        run_id: str,
        candidate_root: Path,
        *,
        verified_bundle_sha256: str = "",
        verified_manifest_path: str = "",
    ) -> PolicyDecision:
        request = PolicyRequest(
            run_id=run_id,
            domain_id=self._document.domain_id,
            action_id="preflight",
            action="PREFLIGHT",
            candidate_root=Path(candidate_root),
            subject={},
            verified_bundle_sha256=verified_bundle_sha256,
            verified_manifest_path=verified_manifest_path,
        )
        return self.evaluate(request)

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        document = self._document

        # V2 (Wave 3): policy input is bound to the trust-validated bundle.
        # A request that claims a verified bundle identity which differs from
        # the identity this engine's contracts were loaded from is a broken
        # trust chain: fail closed (BLOCKED), never evaluate against the
        # wrong bundle. Requests without a verified reference (V1 callers)
        # keep V1-neutral behavior.
        if (
            request.verified_bundle_sha256
            and self._verified_bundle_sha256
            and request.verified_bundle_sha256 != self._verified_bundle_sha256
        ):
            return PolicyDecision(
                Outcome.BLOCKED,
                R.EVIDENCE_BUNDLE_MISMATCH,
                (
                    _finding(
                        R.EVIDENCE_BUNDLE_MISMATCH,
                        "request cites a verified bundle that differs from the "
                        "trust-validated manifest this policy was loaded from",
                        source="contract_bundle",
                        request_bundle_sha256=request.verified_bundle_sha256,
                        policy_bundle_sha256=self._verified_bundle_sha256,
                    ),
                ),
            )

        if request.domain_id != document.domain_id:
            return PolicyDecision(
                Outcome.DENY,
                R.DOMAIN_NOT_ALLOWED,
                (
                    _finding(
                        R.DOMAIN_NOT_ALLOWED,
                        f"request domain {request.domain_id!r} is not the governed domain",
                        domain_id=request.domain_id,
                        governed_domain_id=document.domain_id,
                    ),
                ),
            )

        spec = SUBJECT_SPECS.get(request.action)
        if spec is None:
            return PolicyDecision(
                Outcome.DENY,
                R.ACTION_NOT_ALLOWED,
                (
                    _finding(
                        R.ACTION_NOT_ALLOWED,
                        f"action {request.action!r} is not in the supported vocabulary",
                        action=request.action,
                    ),
                ),
            )

        subject = request.subject
        if not isinstance(subject, Mapping):
            return PolicyDecision(
                Outcome.DENY,
                R.SUBJECT_MALFORMED,
                (_finding(R.SUBJECT_MALFORMED, "subject must be a mapping"),),
            )

        error = _validate_subject(subject, spec)
        if error is not None:
            return PolicyDecision(
                Outcome.DENY,
                R.SUBJECT_MALFORMED,
                (_finding(R.SUBJECT_MALFORMED, error, action=request.action),),
            )

        verdict = _Verdict()
        handler = _HANDLERS[request.action]
        handler(self, request, subject, verdict)
        if request.action != "PREFLIGHT":
            self._apply_global_prerequisites(verdict)
        return verdict.finalize()

    # ------------------------------------------------------------ prereqs

    def _apply_global_prerequisites(self, verdict: _Verdict) -> None:
        document = self._document
        for contract_id in document.missing_contract_ids():
            verdict.block(
                _finding(
                    R.REQUIRED_CONTRACT_MISSING,
                    f"required contract {contract_id} is not present in the frozen bundle",
                    source="contract_bundle",
                    contract_id=contract_id,
                )
            )
        for evidence_id in document.missing_evidence_ids():
            verdict.block(
                _finding(
                    R.REQUIRED_EVIDENCE_MISSING,
                    f"required evidence {evidence_id} has no local verified artifact",
                    source="evidence_store",
                    evidence_id=evidence_id,
                )
            )

    def _missing_component_evidence(
        self, required: Sequence[str], declared: Sequence[str]
    ) -> list[str]:
        """Evidence an action must cite and that must exist locally.

        A declaration is only usable when it is both cited and locally
        verified. A source URL is never a local artifact, so citing one can
        only ever add to the missing set.
        """
        required_set = set(required)
        declared_set = set(declared)
        unavailable = declared_set - self._document.available_evidence_ids
        uncited = required_set - declared_set
        return sorted(uncited | unavailable)

    def _has_capability_grant(self, request: PolicyRequest, capability: str) -> bool:
        """V2 (Wave 3): authority comes only from orchestrator-signed grants.

        A grant counts only when it is pinned to this run, names the acting
        actor from the request's trusted ``actor`` identity, and carries the
        receipt hash that anchors it to an orchestrator evidence record.
        Requester-filled subject fields are never consulted.
        """
        if request.actor is None or not request.actor.actor_id:
            return False
        for grant in request.capability_grants:
            if grant.capability != capability:
                continue
            if grant.run_id != request.run_id:
                continue
            if grant.actor_id != request.actor.actor_id:
                continue
            if not grant.receipt_sha256:
                continue
            return True
        return False

    # ------------------------------------------------------------- handlers

    def _handle_preflight(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        document = self._document
        candidate_root = request.candidate_root

        if not isinstance(candidate_root, Path) or not is_within(
            self._repo_root, candidate_root, strict=True
        ):
            verdict.deny(
                _finding(
                    R.PATH_ESCAPE,
                    "candidate_root is not a strict descendant of the repository root",
                    source="file_policy",
                    candidate_root=str(candidate_root),
                    repo_root=str(self._repo_root),
                )
            )

        for contract_id in document.missing_contract_ids():
            verdict.block(
                _finding(
                    R.REQUIRED_CONTRACT_MISSING,
                    f"required contract {contract_id} is not present in the frozen bundle",
                    source="contract_bundle",
                    contract_id=contract_id,
                )
            )

        for evidence_id in document.missing_evidence_ids():
            verdict.block(
                _finding(
                    R.REQUIRED_EVIDENCE_MISSING,
                    f"required evidence {evidence_id} has no local verified artifact",
                    source="evidence_store",
                    evidence_id=evidence_id,
                )
            )

        for mpn in sorted(document.components):
            record = document.components[mpn]
            missing = document.missing_evidence_for(record.required_evidence_ids)
            if missing:
                verdict.block(
                    _finding(
                        R.COMPONENT_SOURCE_MISSING,
                        f"component {mpn} has no local datasheet evidence",
                        source="evidence_store",
                        mpn=mpn,
                        missing_evidence_ids=missing,
                    )
                )

        # Compiler and verifier coverage are independent gaps: the real EDD-001
        # bundle has neither, and preflight must report both.
        if not document.compilers:
            verdict.block(
                _finding(
                    R.COMPILER_NOT_REGISTERED,
                    "no deterministic compiler is registered for this domain",
                    source="tool_registry",
                )
            )

        if not document.verifiers:
            verdict.block(
                _finding(
                    R.VERIFIER_COVERAGE_MISSING,
                    "no independent verifier is registered for this domain",
                    source="tool_registry",
                )
            )
        else:
            for compiler in sorted(document.compilers, key=lambda c: c.identity):
                uncovered = sorted(
                    set(compiler.required_coverage_ids) - document.coverage_for(compiler.output_kind)
                )
                if uncovered:
                    verdict.block(
                        _finding(
                            R.VERIFIER_COVERAGE_MISSING,
                            f"compiler {compiler.compiler_id} output {compiler.output_kind} "
                            f"has no verifier coverage for {uncovered}",
                            source="tool_registry",
                            compiler_id=compiler.compiler_id,
                            output_kind=compiler.output_kind,
                            missing_coverage_ids=uncovered,
                        )
                    )

    def _handle_select_component(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        document = self._document
        mpn = subject["mpn"]
        record = document.components.get(mpn)
        if record is None:
            verdict.deny(
                _finding(
                    R.COMPONENT_NOT_ALLOWED,
                    f"component {mpn!r} is not in the closed allowed set",
                    source="component_policy",
                    mpn=mpn,
                )
            )
            return
        if record.role != subject["role"]:
            verdict.deny(
                _finding(
                    R.COMPONENT_ROLE_NOT_ALLOWED,
                    f"component {mpn!r} is only allowed with role {record.role!r}",
                    source="component_policy",
                    mpn=mpn,
                    declared_role=subject["role"],
                    allowed_role=record.role,
                )
            )
            return
        missing = self._missing_component_evidence(record.required_evidence_ids, subject["evidence_ids"])
        if missing:
            verdict.block(
                _finding(
                    R.COMPONENT_SOURCE_MISSING,
                    f"component {mpn!r} lacks locally verified evidence",
                    source="evidence_store",
                    mpn=mpn,
                    missing_evidence_ids=missing,
                )
            )

    def _handle_assign_pin(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        pins = self._document.pins
        pin = subject["pin"]
        if pin in pins.hard_forbidden:
            verdict.deny(
                _finding(
                    R.PIN_HARD_FORBIDDEN,
                    f"pin {pin} is physically unavailable and must never be assigned",
                    source=pins.source_for(pin) or "pin_policy",
                    pin=pin,
                )
            )
            return
        if pin in pins.core_reserved:
            verdict.deny(
                _finding(
                    R.PIN_CORE_RESERVED,
                    f"pin {pin} is core-reserved and not assignable by the agent",
                    source=pins.source_for(pin) or "pin_policy",
                    pin=pin,
                )
            )
            return
        if pin in pins.soft_reserved:
            # V2: the subject's approval_status is not authoritative. A
            # soft-reserved pin override is only admissible when the
            # orchestrator's action ledger backs a human approval grant for
            # this run and actor. Self-declared "APPROVED" is BLOCKED.
            if not self._has_capability_grant(request, "approval_status=APPROVED"):
                verdict.block(
                    _finding(
                        R.PIN_OVERRIDE_REQUIRED,
                        f"pin {pin} is soft-reserved and requires an orchestrator-recorded "
                        "human approval grant; the subject's approval_status is not "
                        "authoritative",
                        source=pins.source_for(pin) or "pin_policy",
                        pin=pin,
                        declared_approval_status=subject["approval_status"],
                    )
                )
            return
        if pin not in pins.allowed:
            verdict.deny(
                _finding(
                    R.PIN_NOT_ALLOWED,
                    f"pin {pin!r} is not in the agent GPIO pool",
                    source="pin_policy",
                    pin=pin,
                )
            )

    def _handle_set_parameter(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        document = self._document
        parameter_id = subject["parameter_id"]
        record = document.parameters.get(parameter_id)
        if record is None:
            verdict.deny(
                _finding(
                    R.PARAMETER_NOT_ALLOWED,
                    f"parameter {parameter_id!r} is not declared by the domain contracts",
                    source="parameter_policy",
                    parameter_id=parameter_id,
                )
            )
            return
        if record.unit != subject["unit"]:
            verdict.deny(
                _finding(
                    R.PARAMETER_UNIT_MISMATCH,
                    f"parameter {parameter_id!r} is declared in {record.unit!r}",
                    source="parameter_policy",
                    parameter_id=parameter_id,
                    declared_unit=subject["unit"],
                    allowed_unit=record.unit,
                )
            )
            return
        value = subject["value"]
        expected_number = record.value_type == "number"
        if expected_number != _is_number(value):
            verdict.deny(
                _finding(
                    R.PARAMETER_TYPE_INVALID,
                    f"parameter {parameter_id!r} expects a {record.value_type} value",
                    source="parameter_policy",
                    parameter_id=parameter_id,
                    value_type=record.value_type,
                )
            )
            return
        if not record.accepts(value):
            verdict.deny(
                _finding(
                    R.PARAMETER_OUT_OF_BOUNDS,
                    f"value {value!r} is outside the declared bounds of {parameter_id!r}",
                    source="parameter_policy",
                    parameter_id=parameter_id,
                    value=value,
                    unit=record.unit,
                )
            )
            return
        missing = self._missing_component_evidence(record.required_evidence_ids, subject["evidence_ids"])
        if missing:
            verdict.block(
                _finding(
                    R.PARAMETER_SOURCE_MISSING,
                    f"parameter {parameter_id!r} lacks locally verified evidence",
                    source="evidence_store",
                    parameter_id=parameter_id,
                    missing_evidence_ids=missing,
                )
            )

    def _handle_compile_hir(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        document = self._document
        for generic in sorted(set(document.prerequisites.required_component_resolutions)):
            verdict.block(
                _finding(
                    R.COMPONENT_RESOLUTION_REQUIRED,
                    f"generic component {generic!r} must be resolved to an exact part before compilation",
                    source="component_policy",
                    generic=generic,
                )
            )

        output_kind = subject["output_kind"]
        requested = (
            subject["compiler_id"],
            subject["compiler_version"],
            output_kind,
        )
        compiler = next((c for c in document.compilers if c.identity == requested), None)
        if compiler is None:
            verdict.block(
                _finding(
                    R.COMPILER_NOT_REGISTERED,
                    f"compiler {requested} is not registered for this domain",
                    source="tool_registry",
                    compiler_id=subject["compiler_id"],
                    compiler_version=subject["compiler_version"],
                    output_kind=output_kind,
                )
            )
            return

        covered = document.coverage_for(output_kind)
        uncovered_required = sorted(set(compiler.required_coverage_ids) - covered)
        if uncovered_required:
            verdict.block(
                _finding(
                    R.VERIFIER_COVERAGE_MISSING,
                    f"no verifier covers {uncovered_required} for output kind {output_kind!r}",
                    source="tool_registry",
                    output_kind=output_kind,
                    missing_coverage_ids=uncovered_required,
                )
            )
        uncovered_requested = sorted(set(subject["coverage_ids"]) - covered)
        if uncovered_requested:
            verdict.block(
                _finding(
                    R.VERIFIER_COVERAGE_MISSING,
                    f"requested coverage {uncovered_requested} is not provided by any registered verifier",
                    source="tool_registry",
                    output_kind=output_kind,
                    missing_coverage_ids=uncovered_requested,
                )
            )

    def _handle_verify_artifact(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        document = self._document
        artifact_kind = subject["artifact_kind"]
        requested = (subject["verifier_id"], subject["verifier_version"], artifact_kind)
        verifier = next((v for v in document.verifiers if v.identity == requested), None)
        if verifier is None:
            verdict.deny(
                _finding(
                    R.VERIFIER_NOT_ALLOWED,
                    f"verifier {requested} is not registered for this domain",
                    source="tool_registry",
                    verifier_id=subject["verifier_id"],
                    verifier_version=subject["verifier_version"],
                    artifact_kind=artifact_kind,
                )
            )
            return
        uncovered = sorted(set(subject["coverage_ids"]) - set(verifier.coverage_ids))
        if uncovered:
            verdict.block(
                _finding(
                    R.VERIFIER_COVERAGE_MISSING,
                    f"verifier {verifier.verifier_id} does not cover {uncovered}",
                    source="tool_registry",
                    verifier_id=verifier.verifier_id,
                    artifact_kind=artifact_kind,
                    missing_coverage_ids=uncovered,
                )
            )

    def _handle_tool_execute(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        requested = (subject["tool_id"], subject["tool_version"])
        if not any(tool.identity == requested and tool.capability == subject["capability"] for tool in self._document.tools):
            verdict.deny(
                _finding(
                    R.TOOL_NOT_ALLOWED,
                    f"tool {requested} with capability {subject['capability']!r} is not whitelisted",
                    source="tool_registry",
                    tool_id=subject["tool_id"],
                    tool_version=subject["tool_version"],
                    capability=subject["capability"],
                )
            )

    def _handle_file_write(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        policy = self._document.file_policy
        artifact_kind = subject["artifact_kind"]
        writer = subject["writer"]

        if artifact_kind not in policy.allowed_artifact_kinds:
            verdict.deny(
                _finding(
                    R.ARTIFACT_KIND_NOT_ALLOWED,
                    f"artifact kind {artifact_kind!r} is not writable in this domain",
                    source="file_policy",
                    artifact_kind=artifact_kind,
                )
            )
            return

        resolved = resolve_within(request.candidate_root, subject["path"], strict=True)
        if resolved is None:
            verdict.deny(
                _finding(
                    R.PATH_ESCAPE,
                    "resolved write path escapes the candidate root",
                    source="file_policy",
                    path=subject["path"],
                    candidate_root=str(request.candidate_root),
                )
            )
            return

        if (
            writer == "agent"
            and not policy.direct_kicad_write
            and artifact_kind in policy.agent_forbidden_artifact_kinds
        ):
            verdict.deny(
                _finding(
                    R.DIRECT_KICAD_WRITE,
                    f"agents may not write {artifact_kind!r} directly; emit HIR and use a registered compiler",
                    source="file_policy",
                    artifact_kind=artifact_kind,
                    writer=writer,
                )
            )
            return

        if writer == "compiler":
            # V2: writer=compiler is an authority claim, not a label. It must
            # be backed by an orchestrator-signed capability grant bound to
            # this run and actor; a self-declared subject value is DENIED.
            if not self._has_capability_grant(request, "writer=compiler"):
                verdict.deny(
                    _finding(
                        R.CAPABILITY_NOT_GRANTED,
                        "writing as 'compiler' requires an orchestrator-recorded "
                        "writer=compiler capability grant; the subject's writer "
                        "declaration is not authoritative",
                        source="file_policy",
                        artifact_kind=artifact_kind,
                        writer=writer,
                    )
                )
                return
            if not self._document.compilers_for(artifact_kind):
                verdict.block(
                    _finding(
                        R.COMPILER_NOT_REGISTERED,
                        f"no registered compiler produces artifact kind {artifact_kind!r}",
                        source="tool_registry",
                        artifact_kind=artifact_kind,
                    )
                )

    def _handle_network_access(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        verdict.deny(
            _finding(
                R.NETWORK_DISABLED,
                "network access is disabled for the formal EDD-001 runtime",
                source="network_policy",
                destination=subject["destination"],
                purpose=subject["purpose"],
            )
        )

    def _handle_shell_execute(self, request: PolicyRequest, subject: Mapping[str, Any], verdict: _Verdict) -> None:
        verdict.deny(
            _finding(
                R.ARBITRARY_SHELL_DISABLED,
                "arbitrary shell execution is disabled in the execution sandbox",
                source="shell_policy",
                command_class=subject["command_class"],
            )
        )


_Handler = Callable[[SandboxPolicyEngine, PolicyRequest, Mapping[str, Any], _Verdict], None]

_HANDLERS: dict[str, _Handler] = {
    "PREFLIGHT": SandboxPolicyEngine._handle_preflight,
    "DESIGN_SELECT_COMPONENT": SandboxPolicyEngine._handle_select_component,
    "DESIGN_ASSIGN_PIN": SandboxPolicyEngine._handle_assign_pin,
    "DESIGN_SET_PARAMETER": SandboxPolicyEngine._handle_set_parameter,
    "COMPILE_HIR": SandboxPolicyEngine._handle_compile_hir,
    "VERIFY_ARTIFACT": SandboxPolicyEngine._handle_verify_artifact,
    "TOOL_EXECUTE": SandboxPolicyEngine._handle_tool_execute,
    "FILE_WRITE": SandboxPolicyEngine._handle_file_write,
    "NETWORK_ACCESS": SandboxPolicyEngine._handle_network_access,
    "SHELL_EXECUTE": SandboxPolicyEngine._handle_shell_execute,
}


def _validate_subject(
    subject: Mapping[str, Any], spec: tuple[tuple[str, Callable[[Any], bool]], ...]
) -> str | None:
    """Return a reason when the subject is malformed, else None."""
    if set(subject) != {name for name, _ in spec}:
        expected = sorted(name for name, _ in spec)
        actual = sorted(str(key) for key in subject)
        return f"subject fields {actual} do not match required fields {expected}"
    for name, predicate in spec:
        if not predicate(subject[name]):
            return f"subject field {name!r} has an invalid value"
    return None
