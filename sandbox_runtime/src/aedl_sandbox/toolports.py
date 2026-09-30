"""Real ExecutorPort / VerifierPort implementations (GH-114).

What this module is
-------------------
GH-112 wired the ARH repair agent into the runtime and stopped at the API
boundary. Its scope amendment A1 recorded why one piece was still missing: no
real ExecutorPort / VerifierPort existed anywhere in the repository, so
cli.py run-arh passed stubs that raised on first use. This module is that
missing piece.

What it CLAIMS, precisely
-------------------------
A round of propose -> policy -> execute -> verify now COMPLETES against these
ports. That is all. It does NOT claim that anything was repaired, that any
electrical property was established, or that EDD-001 is any closer to real: the
real EDD-001 policy document registers NO compiler and NO verifier, and still
lacks its power contract and five frozen datasheets.

The design rule, stated because it is contestable
------------------------------------------------
A verifier's realness comes from WHERE ITS CRITERIA COME FROM -- the domain's own
pinned policy registry, a frozen command vector, and artifact bytes read back
from disk -- not from the language it is written in. Every checker under gates/
is Python, and the only third-party tool any of them invokes is kicad-cli, which
is not present on this machine (probed: kicad-cli, arduino-cli, pio, idf.py,
gcc, clang, cmake, ngspice, iverilog -- all missing). A port that demanded
kicad-cli would therefore remain a named failure with no observable difference
from the stub it replaces.

Design consequences
-------------------
* The tool set is DERIVED from PolicyDocument.compilers / .verifiers. There is
  no second hand-written list, so the set of tools a port can run and the set
  the policy authorizes cannot drift apart.
* Everything fails CLOSED and BY NAME. An unregistered, unresolvable, or
  version-mismatched tool is a refusal that names itself; it never becomes a
  silent substitute, and it never becomes a PASS.
* The verifier is INDEPENDENT and READ-ONLY. It re-derives the expected design
  plan from the pinned rules and compares it against the bytes on disk, so a
  tampered or hand-planted artifact fails. It writes nothing.
* Command-backed tools receive a frozen argv VECTOR and are executed without a
  shell. Nothing here reaches a network.

Ownership boundary: this module reads policy.document records and nothing else
from the policy package. It never imports engine internals, never writes outside
the candidate root, and never mutates a policy document.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable

from .protocol import (
    ExecutionResult,
    Finding,
    PolicyRequest,
    VerificationResult,
    VerificationStatus,
)

__all__ = [
    "ARTIFACT_KIND_HIR",
    "BACKEND_IN_REPO_HIR",
    "DESIGN_ACTION_KEY",
    "DESIGN_SUBJECT_KEY",
    "ENVELOPE_OUTPUT_KIND_KEY",
    "HIR_ARTIFACT_NAME",
    "HIR_SCHEMA_ID",
    "CommandBackedExecutor",
    "IN_REPO_BACKENDS",
    "IN_REPO_VERIFIER_ID",
    "InRepoHirBackend",
    "InRepoHirCompiler",
    "InRepoHirVerifier",
    "ToolBackend",
    "ToolExecutor",
    "ToolVerifier",
    "build_tool_ports",
    "run_command",
    "ToolBackendError",
    "ToolNotResolved",
    "ToolPlanError",
    "ToolRegistration",
    "ToolRegistry",
    "build_in_repo_ports",
    "design_envelope",
    "registry_from_document",
]

#: The artifact class this repository can genuinely produce and re-check today.
ARTIFACT_KIND_HIR = "hir"
BACKEND_IN_REPO_HIR = "in-repo-hir"
HIR_ARTIFACT_NAME = "hir.json"
HIR_SCHEMA_ID = "aedl.sandbox.hir.v1"

#: The orchestrator carries a design action through the request subject under
#: these two keys. The policy engine validates the INNER mapping; the envelope
#: itself is refused by this module if it carries anything else (see
#: design_envelope), because T-08 recorded that unvalidated extras were reaching
#: the executor untouched.
DESIGN_ACTION_KEY = "design_action"
DESIGN_SUBJECT_KEY = "design_subject"

#: The artifact kind this run's design produces. Envelope-level, not
#: subject-level: it decides which registered compiler may run, so it must be a
#: contract of the RUN rather than a field a proposal could vary.
ENVELOPE_OUTPUT_KIND_KEY = "output_kind"

#: The complete envelope schema, CLOSED on purpose -- see design_envelope.
#: output_kind appears here because it is permitted at this layer, but it is not
#: REQUIRED of every envelope: a repair proposal carries only the two contract
#: keys, and a round re-drives execution from that proposal. Requiring the kind
#: of every envelope would make every repaired round unexecutable, which a live
#: probe caught. The requirement is enforced where it can be met -- at request
#: time, against the domain's registry (ToolExecutor._request_output_kind).
_ENVELOPE_KEYS = (DESIGN_ACTION_KEY, DESIGN_SUBJECT_KEY, ENVELOPE_OUTPUT_KIND_KEY)

#: The design actions that describe a candidate. The orchestrator's own actions
#: (PREFLIGHT / COMPILE_HIR / VERIFY_ARTIFACT) are not design content and are
#: refused here: a request carrying one of them is a misassembly, not a design.
_PLAN_ACTIONS = ("DESIGN_SELECT_COMPONENT", "DESIGN_ASSIGN_PIN", "DESIGN_SET_PARAMETER")

#: Top-level keys the executor writes and the verifier accepts. An artifact
#: carrying anything else is refused rather than ignored.
_ARTIFACT_KEYS = (
    "schema",
    "domain_id",
    "run_id",
    "candidate_id",
    "tool",
    "plan_sha256",
    "plan",
)


class ToolNotResolved(RuntimeError):
    """A tool the caller asked for is not usable, named precisely.

    Raised at ASSEMBLY time, never at use time: a port that cannot run the tool
    it was built for is a misassembly, and discovering that mid-round would look
    like a model or candidate failure instead of a configuration failure.
    """


class ToolPlanError(ValueError):
    """A design subject cannot be turned into a legal plan. Named, with a code.

    The verifier raises the same error type from the same rules, which is part
    of what makes it independent: two callers, one rule set, no shared mutable
    state.
    """

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = dict(details)


class ToolBackendError(RuntimeError):
    """A backend could not produce or check an artifact, named precisely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Registration: the policy document is the single source of truth.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolRegistration:
    """One entry of the domain's tool registry, as the policy document states it.

    backend names a real implementation registered in this process; it is the
    only field that is not copied from the policy document, and it is the point
    where "the domain authorizes compiler X" meets "something can actually run
    X". When no backend answers to it, the tool is NOT RESOLVED and refuses by
    name -- deliberately, because the alternative is a substitute that reports
    success for a tool that never ran.
    """

    kind: str  # "compiler" | "verifier"
    tool_id: str
    version: str
    artifact_kind: str
    coverage_ids: tuple[str, ...]
    required_coverage_ids: tuple[str, ...]
    backend: str
    command: tuple[str, ...] = ()

    @property
    def identity(self) -> tuple[str, str]:
        return (self.tool_id, self.version)

    @property
    def key(self) -> str:
        return "%s:%s@%s" % (self.kind, self.tool_id, self.version)


class ToolRegistry:
    """The set of tools this process can run, derived from a policy document.

    Derivation is one-way: the document decides WHICH tools exist and what they
    cover; the registry decides HOW each one runs.

    The registry does NOT require every registered tool to have a backend. A
    policy document may legitimately declare tools that no process in this
    repository can run yet -- the real EDD-001 document declares none at all --
    and refusing to build a registry at all would make an unrelated declaration
    fatal. The refusal belongs at RESOLUTION: naming an unbacked tool fails by
    name, and asking for a backend that does not exist fails by name. Both are
    checked here and neither has a fallback.
    """

    def __init__(
        self,
        registrations: "list[ToolRegistration]",
        backends: Mapping[str, "ToolBackend"],
        *,
        domain_id: str | None = None,
    ) -> None:
        self._backends = MappingProxyType(dict(backends))
        self._registrations = tuple(registrations)
        self._domain_id = domain_id

    @property
    def domain_id(self) -> str | None:
        """The pinned document's domain, independent of artifact declarations."""
        return self._domain_id

    @property
    def registrations(self) -> "tuple[ToolRegistration, ...]":
        return self._registrations

    def backend_for(self, registration: ToolRegistration) -> "ToolBackend":
        return self.backend_by_name(registration.backend, registration=registration)

    def backend_by_name(
        self, name: str, *, registration: ToolRegistration | None = None
    ) -> "ToolBackend":
        backend = self._backends.get(name)
        if backend is None:
            raise ToolNotResolved(
                "tool %s declares backend %r, and no backend by that name is "
                "registered in this process. This domain AUTHORIZES the tool; "
                "nothing here can run it. That is a refusal, not a reason to run "
                "a different tool."
                % (registration.key if registration else "<unknown>", name)
            )
        if registration is not None and getattr(backend, "version", None) != registration.version:
            raise ToolNotResolved(
                "tool %s declares version %r, but backend %r reports version %r. "
                "Running a different or unknown version would be a substitution, "
                "not a resolution."
                % (registration.key, registration.version, name, getattr(backend, "version", None))
            )
        return backend

    def compilers(
        self, *, backend: str | None = None, runnable_only: bool = False
    ) -> "tuple[ToolRegistration, ...]":
        return tuple(
            r
            for r in self._registrations
            if r.kind == "compiler"
            and (backend is None or r.backend == backend)
            and (not runnable_only or r.backend in self._backends)
        )

    def verifiers(
        self, *, backend: str | None = None, runnable_only: bool = False
    ) -> "tuple[ToolRegistration, ...]":
        return tuple(
            r
            for r in self._registrations
            if r.kind == "verifier"
            and (backend is None or r.backend == backend)
            and (not runnable_only or r.backend in self._backends)
        )

    def resolve_verifier(self, verifier_id: str) -> ToolRegistration:
        """The named verifier, or a refusal that names what IS registered."""
        found = [r for r in self.verifiers() if r.tool_id == verifier_id]
        if not found:
            raise ToolNotResolved(
                "no verifier %r is registered. Registered verifiers: %s. An "
                "unregistered verifier is a refusal, never a fallback."
                % (verifier_id, self._names(self.verifiers()))
            )
        if len(found) > 1:
            raise ToolNotResolved(
                "verifier %r is registered %d times (%s); the run cannot tell "
                "which registration it is executing."
                % (verifier_id, len(found), ", ".join(r.key for r in found))
            )
        return found[0]

    def resolve_compiler(
        self, compiler_id: str, version: str, *, backend: str | None = None
    ) -> ToolRegistration:
        """The named compiler at the named version, or a refusal by name.

        The VERSION is checked, not ignored: a registry entry pinned to 1.0.0 and
        a request naming 2.0.0 are different tools, and running one while the
        domain authorized the other is exactly the silent substitution this
        module exists to prevent.
        """
        found = [
            r
            for r in self.compilers(backend=backend)
            if r.tool_id == compiler_id and r.version == version
        ]
        if found:
            if len(found) > 1:
                raise ToolNotResolved(
                    "compiler %s@%s is registered %d times"
                    % (compiler_id, version, len(found))
                )
            return found[0]
        same_id = [r for r in self.compilers(backend=backend) if r.tool_id == compiler_id]
        if same_id:
            raise ToolNotResolved(
                "compiler %r is registered, but not at version %r (registered: "
                "%s). Running a different version would be a substitution, not a "
                "resolution." % (compiler_id, version, self._versions(same_id))
            )
        raise ToolNotResolved(
            "compiler %r is not registered for this domain. Registered compilers: "
            "%s. An unregistered compiler is a refusal, never a fallback."
            % (compiler_id, self._names(self.compilers(backend=backend)))
        )

    @staticmethod
    def _names(registrations: "tuple[ToolRegistration, ...]") -> str:
        if not registrations:
            return "<none>"
        return ", ".join(sorted(r.key for r in registrations))

    @staticmethod
    def _versions(registrations: "tuple[ToolRegistration, ...]") -> str:
        return ", ".join(sorted(r.version for r in registrations))


@runtime_checkable
class ToolBackend(Protocol):
    """What a runnable tool must provide.

    backend is the name registrations refer to; version is what the
    implementation actually is, so a registry entry can be checked against the
    code that will run rather than against a declaration nobody verifies.
    """

    backend: str
    version: str

    def compile(
        self, registration: ToolRegistration, request: PolicyRequest
    ) -> "tuple[dict[str, Any], tuple[Finding, ...]]": ...

    def check(
        self, registration: ToolRegistration, candidate_root: Path
    ) -> "tuple[dict[str, Any] | None, tuple[Finding, ...]]": ...


def registry_from_document(
    document: Any,
    *,
    backends: Mapping[str, "ToolBackend"],
    backend_for_tool: Mapping[str, str] | None = None,
    commands: Mapping[str, tuple[str, ...]] | None = None,
) -> ToolRegistry:
    """Derive a registry from a policy document's own compiler/verifier records.

    backend_for_tool maps a tool id to the backend that runs it. A tool the
    document authorizes and this mapping does not name is STILL registered -- and
    then refuses at assembly, by name, because no backend answers to an empty
    name. That is the fail-closed direction: silence about a tool must not read
    as "not authorized" or as "runs somehow".
    """
    mapping = dict(backend_for_tool or {})
    command_table = dict(commands or {})
    registrations: "list[ToolRegistration]" = []
    for compiler in getattr(document, "compilers", ()) or ():
        tool_id = str(compiler.compiler_id)
        registrations.append(
            ToolRegistration(
                kind="compiler",
                tool_id=tool_id,
                version=str(compiler.compiler_version),
                artifact_kind=str(compiler.output_kind),
                coverage_ids=tuple(),
                required_coverage_ids=tuple(compiler.required_coverage_ids),
                backend=mapping.get(tool_id, ""),
                command=tuple(command_table.get(tool_id, ())),
            )
        )
    for verifier in getattr(document, "verifiers", ()) or ():
        tool_id = str(verifier.verifier_id)
        registrations.append(
            ToolRegistration(
                kind="verifier",
                tool_id=tool_id,
                version=str(verifier.verifier_version),
                artifact_kind=str(verifier.artifact_kind),
                coverage_ids=tuple(verifier.coverage_ids),
                required_coverage_ids=tuple(),
                backend=mapping.get(tool_id, ""),
                command=tuple(command_table.get(tool_id, ())),
            )
        )
    return ToolRegistry(registrations, backends, domain_id=document.domain_id)


# ---------------------------------------------------------------------------
# The design plan: the one thing both sides derive, from different inputs.
# ---------------------------------------------------------------------------


def design_envelope(
    request: PolicyRequest,
) -> "tuple[str, Mapping[str, Any], str]":
    """Split an execute request into (design_action, design_subject, output_kind).

    The envelope is a CLOSED whitelist of exactly the keys the executor
    consumes. Policy validates the INNER subject and never sees the envelope
    layer, so an envelope with unknown keys is the unvalidated side channel
    red-team finding T-08 described: extras used to reach the executor untouched.
    Refusing them here is the cheap half of that fix and is exactly what T-08's
    V1 mitigation asked for.

    output_kind lives HERE, not inside the design subject, for two reasons that
    point the same way. The repair agent checks the inner subject against
    policy.engine.SUBJECT_SPECS by exact field set, so any extra field would make
    every model proposal fail validation -- a total rejection rate that looks
    like a model that cannot follow instructions. And the artifact kind is a
    property of the RUN's contract with its domain, not of a single design
    action, so it must not be something a proposal can vary.
    """
    subject = request.subject if isinstance(request.subject, Mapping) else {}
    extras = sorted(set(subject) - set(_ENVELOPE_KEYS))
    if extras:
        raise ToolPlanError(
            "ENVELOPE_UNEXPECTED_KEYS",
            "the design envelope carries keys the schema does not define: %s. "
            "Policy checks only the inner design subject, so anything else here "
            "would reach the executor unchecked." % (extras,),
            unexpected_keys=extras,
        )
    action = subject.get(DESIGN_ACTION_KEY)
    inner = subject.get(DESIGN_SUBJECT_KEY)
    output_kind = subject.get(ENVELOPE_OUTPUT_KIND_KEY)
    if not isinstance(action, str) or not action:
        raise ToolPlanError(
            "ENVELOPE_MISSING_DESIGN_ACTION",
            "the request carries no design action under %r" % DESIGN_ACTION_KEY,
        )
    if not isinstance(inner, Mapping):
        raise ToolPlanError(
            "ENVELOPE_MISSING_DESIGN_SUBJECT",
            "the request carries no design subject mapping under %r"
            % DESIGN_SUBJECT_KEY,
        )
    # Blank is treated as missing, for the same reason the API key is: an empty
    # value would travel one layer further and fail somewhere less legible.
    if output_kind is None:
        # Absent is NOT the same as malformed. A repair proposal carries only
        # design_action + design_subject -- output_kind is deliberately outside
        # the model's action schema -- so a repaired envelope has no kind to
        # restate and a round re-drives execution from it. Refusing here would
        # make every repair round unexecutable; the requirement is enforced
        # against the domain's registry instead, where the answer lives.
        output_kind = ""
    if not isinstance(output_kind, str):
        raise ToolPlanError(
            "ENVELOPE_OUTPUT_KIND_NOT_TEXT",
            "%r must be a string when present, got %r"
            % (ENVELOPE_OUTPUT_KIND_KEY, output_kind),
        )
    if action not in _PLAN_ACTIONS:
        raise ToolPlanError(
            "ENVELOPE_NOT_A_DESIGN_ACTION",
            "%r is not a design action. Only %s describe a candidate; the "
            "orchestrator's own actions are dispatched by the assembly, never "
            "carried in a design envelope." % (action, list(_PLAN_ACTIONS)),
            action=action,
        )
    return action, inner, output_kind


def _text_list(value: Any, field: str) -> "list[str]":
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise ToolPlanError(
            "PLAN_FIELD_NOT_TEXT_LIST",
            "%r must be a list of strings, got %r" % (field, value),
        )
    return [str(item) for item in value]


def _build_plan_row(
    design_action: str, design_subject: Mapping[str, Any], document: Any
) -> "dict[str, Any]":
    """Validate ONE design action against the pinned rules and return its row.

    This deliberately re-checks what the policy already checked. The two callers
    are not in the same trust position: the policy engine decides whether an
    action MAY happen, while this decides what the resulting artifact must
    CONTAIN. Re-deriving is how the verifier compares bytes instead of echoing a
    decision it was handed.
    """
    if document is None:
        raise ToolBackendError(
            "BACKEND_NEEDS_DOCUMENT",
            "this backend needs the domain policy document to derive a plan; the "
            "port was assembled without one",
        )
    if design_action == "DESIGN_SELECT_COMPONENT":
        mpn = design_subject.get("mpn")
        role = design_subject.get("role")
        record = document.components.get(mpn) if isinstance(mpn, str) else None
        if record is None:
            raise ToolPlanError(
                "PLAN_COMPONENT_NOT_ALLOWED",
                "component %r is not in the domain's closed allowed set" % (mpn,),
                mpn=mpn,
            )
        if record.role != role:
            raise ToolPlanError(
                "PLAN_COMPONENT_ROLE_NOT_ALLOWED",
                "component %r is only allowed with role %r, not %r"
                % (mpn, record.role, role),
                mpn=mpn,
                declared_role=role,
                allowed_role=record.role,
            )
        return {
            "action": design_action,
            "mpn": mpn,
            "role": role,
            "evidence_ids": _text_list(design_subject.get("evidence_ids"), "evidence_ids"),
        }
    if design_action == "DESIGN_ASSIGN_PIN":
        pin = design_subject.get("pin")
        function = design_subject.get("function")
        pins = document.pins
        if not isinstance(pin, str) or not isinstance(function, str):
            raise ToolPlanError(
                "PLAN_PIN_MALFORMED",
                "a pin assignment needs a string 'pin' and a string 'function'",
            )
        if pin in pins.hard_forbidden:
            raise ToolPlanError(
                "PLAN_PIN_HARD_FORBIDDEN",
                "pin %r is physically unavailable on this board" % (pin,),
                pin=pin,
            )
        if pin in pins.core_reserved:
            raise ToolPlanError(
                "PLAN_PIN_CORE_RESERVED",
                "pin %r is core-reserved and not assignable" % (pin,),
                pin=pin,
            )
        if pin not in pins.allowed and pin not in pins.soft_reserved:
            # An unknown pin is refused rather than recorded. Recording it would
            # put a pin on the artifact that no contract authorizes, and the
            # artifact is supposed to be a projection of authorized decisions.
            raise ToolPlanError(
                "PLAN_PIN_NOT_ALLOWED",
                "pin %r is not in the domain's assignable set" % (pin,),
                pin=pin,
            )
        # A soft-reserved pin is admissible only with an orchestrator-backed
        # approval grant. That grant is authority this module does not carry and
        # must not invent: the artifact records the assignment, and whether the
        # grant existed is the orchestrator's ledger to prove. A backend that
        # assumed it would be laundering authority it never saw.
        return {"action": design_action, "pin": pin, "function": function}
    if design_action == "DESIGN_SET_PARAMETER":
        parameter_id = design_subject.get("parameter_id")
        value = design_subject.get("value")
        unit = design_subject.get("unit")
        record = (
            document.parameters.get(parameter_id)
            if isinstance(parameter_id, str)
            else None
        )
        if record is None:
            raise ToolPlanError(
                "PLAN_PARAMETER_NOT_DECLARED",
                "parameter %r is not declared by this domain" % (parameter_id,),
                parameter_id=parameter_id,
            )
        if not record.accepts(value):
            raise ToolPlanError(
                "PLAN_PARAMETER_OUT_OF_BOUNDS",
                "value %r is outside the declared bounds of %r"
                % (value, parameter_id),
                parameter_id=parameter_id,
                value=value,
                unit=record.unit,
            )
        if record.unit != unit:
            raise ToolPlanError(
                "PLAN_PARAMETER_UNIT_MISMATCH",
                "parameter %r is declared in %r, not %r"
                % (parameter_id, record.unit, unit),
                parameter_id=parameter_id,
                declared_unit=record.unit,
                requested_unit=unit,
            )
        return {
            "action": design_action,
            "parameter_id": parameter_id,
            "value": value,
            "unit": unit,
            "evidence_ids": _text_list(design_subject.get("evidence_ids"), "evidence_ids"),
        }
    raise ToolPlanError(
        "PLAN_ACTION_NOT_SUPPORTED", "no plan rule exists for %r" % (design_action,)
    )


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _plan_sha256(plan: "list[dict[str, Any]]") -> str:
    return hashlib.sha256(_canonical_bytes(plan)).hexdigest()


def _hir_document(
    *,
    domain_id: str,
    run_id: str,
    candidate_id: str,
    writer_id: str,
    writer_version: str,
    plan: "list[dict[str, Any]]",
) -> "dict[str, Any]":
    """The artifact both sides derive, canonical by construction.

    The tool field names the BACKEND that produced the artifact, not the registry
    entry that authorized the run: the compiler registration and the verifier
    registration are different ids by design, so putting the compiler's id here
    would make the verifier reject every artifact it was meant to check. The
    authorization is the policy document's job; this field answers "what wrote
    these bytes".

    The design plan arrives as the request's subject. Until design decisions are
    persisted somewhere a round can re-read them, a run carries exactly one, so
    the plan is a one-row list; the shape is a list because a design is a
    sequence of decisions and a single-decision renderer would have to be widened
    the moment a second one exists.
    """
    return {
        "schema": HIR_SCHEMA_ID,
        "domain_id": domain_id,
        "run_id": run_id,
        "candidate_id": candidate_id,
        "tool": {"tool_id": writer_id, "version": writer_version},
        "plan_sha256": _plan_sha256(plan),
        "plan": plan,
    }


# ---------------------------------------------------------------------------
# The in-repo artifact class: a compiler that writes, a verifier that re-derives.
# ---------------------------------------------------------------------------


class InRepoHirCompiler:
    """A real executor backend: writes the artifact the approved design defines.

    The design subject has already been evaluated by the policy engine; this
    backend turns that ALLOWED decision into bytes, deterministically, inside the
    candidate root. It is the single write path the RFC requires -- the write
    happens only here, and only after policy ALLOW -- and it writes nothing else.

    It is deliberately NOT a tool that pretends to synthesize hardware. What it
    emits is a normalized record of the decisions this run was authorized to
    make: components, pins, parameters. Anything that turns those into a board
    is a compiler this repository does not have.
    """

    backend = BACKEND_IN_REPO_HIR
    version = "1.0.0"

    def __init__(self, document: Any, *, artifact_name: str = HIR_ARTIFACT_NAME) -> None:
        self._document = document
        self._artifact_name = artifact_name
        #: What the executor reports as the artifact it produced. The executor
        #: reads it from here rather than hard-coding a name, so a backend that
        #: writes something else reports something else.
        self.artifact_name = artifact_name

    def compile(
        self, registration: ToolRegistration, request: PolicyRequest
    ) -> "tuple[dict[str, Any], tuple[Finding, ...]]":
        design_action, design_subject, _output_kind = design_envelope(request)
        row = _build_plan_row(design_action, design_subject, self._document)
        document = _hir_document(
            domain_id=request.domain_id,
            run_id=request.run_id,
            candidate_id=request.candidate_root.name,
            writer_id=self.backend,
            writer_version=self.version,
            plan=[row],
        )
        target = Path(request.candidate_root) / self._artifact_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_canonical_bytes(document))
        return document, ()


class InRepoHirVerifier:
    """An independent, read-only verifier for the in-repo HIR artifact.

    INDEPENDENT means it does not ask the executor what it did. It re-derives the
    expected plan from the pinned rules and the design this run was assembled
    with, then compares that against the artifact BYTES ON DISK. A tampered
    artifact fails, and a PASS that did not go through the comparison cannot
    exist, because there is no other path to PASS in this class.

    READ-ONLY means it opens the artifact for reading and writes nothing, so it
    cannot become a second writer in the candidate root.

    What a PASS states, exactly: the artifact is a faithful, structurally legal
    projection of the design this run's policy approved. It does NOT state that
    the design is electrically correct, that ERC/DRC passes, or that the board is
    manufacturable -- and every PASS carries that sentence as a finding, because
    a scope left to the reader's imagination is how "it verified" starts meaning
    more than it does.
    """

    backend = BACKEND_IN_REPO_HIR
    version = "1.0.0"

    def __init__(self, document: Any, *, artifact_name: str = HIR_ARTIFACT_NAME) -> None:
        self._document = document
        self._artifact_name = artifact_name

    # -- checks that need no artifact content ------------------------------

    def _rederive(self, design_action: str, design_subject: Mapping[str, Any]):
        """The verifier's OWN derivation of what the artifact must contain.

        Two lines, both load-bearing: a plan built only from the pinned rules and
        the run's frozen design, and the digest of that plan. Nothing here reads
        the artifact, so the comparison that follows is between two independent
        derivations rather than a file and a copy of itself.
        """
        row = _build_plan_row(design_action, design_subject, self._document)
        plan = [row]
        return plan, _plan_sha256(plan)

    def _read_artifact(self, candidate_root: Path) -> "tuple[dict[str, Any] | None, tuple[Finding, ...]]":
        target = Path(candidate_root) / self._artifact_name
        if not target.is_file():
            return None, (
                Finding(
                    code="VERIFY_ARTIFACT_MISSING",
                    message=(
                        "the candidate carries no %s, so there is nothing to "
                        "verify. A verifier that passes an empty candidate would "
                        "be reporting on a file it never read." % self._artifact_name
                    ),
                    source="in-repo-hir-verifier",
                    details={"artifact": self._artifact_name},
                ),
            )
        raw = target.read_bytes()
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return None, (
                Finding(
                    code="VERIFY_ARTIFACT_UNREADABLE",
                    message="%s is not parsable JSON: %s" % (self._artifact_name, exc),
                    source="in-repo-hir-verifier",
                    details={"artifact": self._artifact_name},
                ),
            )
        if not isinstance(parsed, Mapping):
            return None, (
                Finding(
                    code="VERIFY_ARTIFACT_NOT_AN_OBJECT",
                    message="%s does not contain a JSON object" % self._artifact_name,
                    source="in-repo-hir-verifier",
                ),
            )
        return dict(parsed), ()

    @staticmethod
    def _canonical_mismatch(raw: bytes, parsed: Mapping[str, Any]) -> "Finding | None":
        """The bytes on disk must be the canonical rendering of what they say.

        Without this, a hand-edited artifact with reordered keys and odd spacing
        would still compare equal after parsing, and the file a human reads would
        not be the file the digest was computed over.
        """
        if raw != _canonical_bytes(parsed):
            return Finding(
                code="VERIFY_ARTIFACT_NOT_CANONICAL",
                message=(
                    "the artifact bytes are not the canonical rendering of their "
                    "own content, so the file on disk is not the file the plan "
                    "digest was computed over"
                ),
                source="in-repo-hir-verifier",
            )
        return None

    def check(
        self,
        registration: ToolRegistration,
        candidate_root: Path,
        *,
        design_action: str | None = None,
        design_subject: Mapping[str, Any] | None = None,
    ) -> "tuple[dict[str, Any] | None, tuple[Finding, ...]]":
        """Read the artifact and check it against an independent derivation.

        The design comes from the VERIFIER's own construction when the caller
        does not name one, so this object is usable as a plain backend while the
        ToolVerifier port (which froze the same design at assembly) is the one
        that decides which registration runs.
        """
        if design_action is None or design_subject is None:
            raise ToolBackendError(
                "CHECK_NEEDS_DESIGN",
                "the in-repo verifier checks an artifact against the design the "
                "run was assembled with; it will not read that design back out of "
                "the artifact, because that is the thing being checked",
            )
        findings: "list[Finding]" = []
        parsed, read_findings = self._read_artifact(candidate_root)
        findings.extend(read_findings)
        if parsed is None:
            return None, tuple(findings)

        raw = (Path(candidate_root) / self._artifact_name).read_bytes()
        canonical = self._canonical_mismatch(raw, parsed)
        if canonical is not None:
            findings.append(canonical)

        # The verifier's own derivation: independent of the executor's output.
        try:
            expected_plan, expected_sha = self._rederive(design_action, design_subject)
        except (ToolPlanError, ToolBackendError) as exc:
            code = getattr(exc, "code", "VERIFY_DERIVATION_FAILED")
            findings.append(
                Finding(
                    code=code,
                    message=(
                        "the artifact cannot be checked against the pinned rules "
                        "because the design this run was assembled with does not "
                        "derive: %s" % exc
                    ),
                    source="in-repo-hir-verifier",
                    details=dict(getattr(exc, "details", {})),
                )
            )
            return parsed, tuple(findings)

        unexpected = sorted(set(parsed) - set(_ARTIFACT_KEYS))
        missing = sorted(set(_ARTIFACT_KEYS) - set(parsed))
        if unexpected or missing:
            findings.append(
                Finding(
                    code="VERIFY_ARTIFACT_SHAPE",
                    message=(
                        "artifact keys do not match the %s contract "
                        "(unexpected=%s, missing=%s)"
                        % (HIR_SCHEMA_ID, unexpected, missing)
                    ),
                    source="in-repo-hir-verifier",
                    details={"unexpected": unexpected, "missing": missing},
                )
            )
        if parsed.get("schema") != HIR_SCHEMA_ID:
            findings.append(
                Finding(
                    code="VERIFY_ARTIFACT_SCHEMA",
                    message="artifact declares schema %r, expected %r"
                    % (parsed.get("schema"), HIR_SCHEMA_ID),
                    source="in-repo-hir-verifier",
                )
            )
        tool = parsed.get("tool")
        # The artifact must name the BACKEND that produced it, checked against
        # this verifier's own backend identity rather than against whichever
        # registration happens to be running: a wrapper that presented a
        # pass-through under the expected tool id must not be accepted merely
        # because it knew the id to print.
        expected_tool = {"tool_id": self.backend, "version": self.version}
        if not isinstance(tool, Mapping) or dict(tool) != expected_tool:
            findings.append(
                Finding(
                    code="VERIFY_ARTIFACT_TOOL_MISMATCH",
                    message=(
                        "artifact names tool %r; the in-repo artifact class is %s. "
                        "The name the artifact carries is the backend that wrote "
                        "it, and it has to be this one."
                        % (tool, expected_tool)
                    ),
                    source="in-repo-hir-verifier",
                    details={"declared_tool": tool if isinstance(tool, Mapping) else None},
                )
            )
        if parsed.get("plan") != expected_plan:
            findings.append(
                Finding(
                    code="VERIFY_PLAN_MISMATCH",
                    message=(
                        "the artifact's plan is not the plan the pinned rules "
                        "derive from this run's design; the bytes on disk and the "
                        "authorized design disagree"
                    ),
                    source="in-repo-hir-verifier",
                    details={"recomputed_plan_sha256": expected_sha},
                )
            )
        if parsed.get("plan_sha256") != expected_sha:
            findings.append(
                Finding(
                    code="VERIFY_PLAN_DIGEST_MISMATCH",
                    message=(
                        "artifact plan digest %r does not match the digest "
                        "recomputed from the pinned rules %r"
                        % (parsed.get("plan_sha256"), expected_sha)
                    ),
                    source="in-repo-hir-verifier",
                )
            )
        return parsed, tuple(findings)


# ---------------------------------------------------------------------------
# Command-backed tools: registered, resolvable, actually invocable -- or named.
# ---------------------------------------------------------------------------


def run_command(
    registration: ToolRegistration, *, timeout_s: float = 60.0
) -> "tuple[dict[str, Any], tuple[Finding, ...]]":
    """Run a frozen argv vector WITHOUT a shell and return a receipt.

    Three properties this exists to guarantee, each of which is a way a tool
    invocation usually stops being evidence:

    * `shell=False` with a vector, never a command string -- there is no
      interpolation for a subject value to reach.
    * The command is the one the OPERATOR registered, not one derived from the
      request.
    * A tool that is not on PATH is a NAMED failure. It is never "skipped", and
      it never counts as a pass.
    """
    if not registration.command:
        raise ToolNotResolved(
            "%s declares no command vector, so it cannot be invoked. Add one at "
            "assembly or run a backend that does not need an external tool."
            % registration.key
        )
    executable = registration.command[0]
    resolved = shutil.which(executable)
    if resolved is None:
        return {}, (
            Finding(
                code="TOOL_NOT_ON_PATH",
                message=(
                    "%s is registered for this domain but %r is not on PATH, so "
                    "the tool never ran. This is a refusal to report a result, "
                    "not a skipped check." % (registration.key, executable)
                ),
                source="toolports",
                details={
                    "tool_id": registration.tool_id,
                    "tool_version": registration.version,
                    "command": list(registration.command),
                },
            ),
        )
    argv = [resolved] + list(registration.command[1:])
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout_s,
            check=False,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return {}, (
            Finding(
                code="TOOL_TIMEOUT",
                message="%s exceeded the %.0fs budget and was terminated"
                % (registration.key, timeout_s),
                source="toolports",
                details={"command": list(registration.command)},
            ),
        )
    except OSError as exc:
        return {}, (
            Finding(
                code="TOOL_COULD_NOT_START",
                message="%s could not start: %s" % (registration.key, exc),
                source="toolports",
                details={"command": list(registration.command)},
            ),
        )
    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    receipt = {
        "tool_id": registration.tool_id,
        "tool_version": registration.version,
        "command": list(registration.command),
        "resolved_executable": resolved,
        "exit_code": completed.returncode,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_bytes": len(stdout),
        "stderr_bytes": len(stderr),
    }
    if completed.returncode != 0:
        return receipt, (
            Finding(
                code="TOOL_EXIT_NONZERO",
                message="%s exited with status %d; the invocation failed"
                % (registration.key, completed.returncode),
                source="toolports",
                details={
                    "tool_id": registration.tool_id,
                    "tool_version": registration.version,
                    "exit_code": completed.returncode,
                    "command": list(registration.command),
                },
            ),
        )
    return receipt, ()


class CommandBackedExecutor:
    """An executor whose tool is an external process, or a named refusal.

    It writes the invocation receipt into the candidate root (the executor is
    the only writer) and reports the tool's own exit status rather than an
    opinion about it. `CommandBackedExecutor` is for tools that produce the
    candidate artifact themselves; the in-repo HIR class does not use it.
    """

    backend = "command"

    def __init__(self, *, timeout_s: float = 60.0) -> None:
        self._timeout_s = timeout_s
        self.version = "1.0.0"

    def compile(
        self, registration: ToolRegistration, request: PolicyRequest
    ) -> "tuple[dict[str, Any], tuple[Finding, ...]]":
        receipt, findings = run_command(registration, timeout_s=self._timeout_s)
        # A failed invocation is still recorded, but never reported as a
        # successful compilation. No receipt exists when the tool never ran.
        if receipt:
            receipt_path = Path(request.candidate_root) / (
                "tool-%s-receipt.json" % registration.tool_id
            )
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(_canonical_bytes(receipt))
        return receipt, findings


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


class ToolExecutor:
    """ExecutorPort over a registry: resolves the registered tool, then runs it.

    The port never invents a tool. It matches the design's declared output kind
    against the domain's own registry and refuses by name when nothing matches,
    when the tool's backend is unbacked, or when the backend itself refuses.
    """

    def __init__(self, registry: ToolRegistry, *, backend: str, timeout_s: float = 60.0) -> None:
        self._registry = registry
        self._backend = backend
        self._timeout_s = timeout_s

    @staticmethod
    def _one_or_them(registrations: "tuple[ToolRegistration, ...]") -> str:
        return "it" if len(registrations) == 1 else "them"

    def _request_output_kind(self, request: PolicyRequest, candidates) -> str:
        """The artifact kind this request declares, resolved or refused.

        A repair PROPOSAL carries only design_action + design_subject, because
        output_kind is deliberately not part of the model's action schema: the
        artifact kind is the RUN's contract with its domain and must not be
        something a proposal can vary. So a repaired envelope cannot restate it,
        and reading the model's silence as "missing" would make every repair
        round fail to execute -- which is exactly what a live probe caught.

        The resolution is therefore: if the request declares a kind, use it. If it
        does not, and the domain's registry offers EXACTLY ONE runnable output
        kind, take that one -- it is the only thing the request could have meant,
        and it is still the DOMAIN's declaration rather than the executor's
        invention. Two or more kinds, or none, is a refusal by name.
        """
        declared = dict(request.subject).get(ENVELOPE_OUTPUT_KIND_KEY)
        if isinstance(declared, str) and declared.strip():
            return declared
        kinds = sorted({r.artifact_kind for r in candidates})
        if len(kinds) == 1:
            return kinds[0]
        raise ToolNotResolved(
            "this request declares no %r and the domain registers %d runnable "
            "artifact kinds (%s), so which one this round produces is genuinely "
            "ambiguous. A repair proposal does not carry the kind by design; a "
            "domain with more than one must state it another way."
            % (ENVELOPE_OUTPUT_KIND_KEY, len(kinds), kinds)
        )

    def _resolve(self, request: PolicyRequest) -> ToolRegistration:
        design_action, design_subject, _declared_kind = design_envelope(request)
        # runnable_only: a registered tool with no backend in this process is
        # NOT a candidate to execute. It is reported as unresolvable rather than
        # quietly skipped, because skipping would let the design "execute"
        # against whatever else happened to match.
        candidates = self._registry.compilers(
            backend=self._backend, runnable_only=True
        )
        if not candidates:
            declared = self._registry.compilers(backend=self._backend)
            if declared:
                raise ToolNotResolved(
                    "this domain authorizes %s, and no backend in this process "
                    "can run %s. The tool is registered and unresolvable, which "
                    "is a refusal rather than a reason to run a different tool."
                    % (
                        ", ".join(r.key for r in declared),
                        self._one_or_them(declared),
                    )
                )
            registered = self._registry.compilers()
            raise ToolNotResolved(
                "no compiler on backend %r is registered for this domain "
                "(registered compilers: %s). The design cannot be executed by a "
                "tool the policy does not authorize."
                % (self._backend, self._registry._names(registered))
            )
        # The artifact kind decides. There is no fallback among COMPILERS: two
        # compilers that both produce the declared kind is a refusal, never a
        # silent pick.
        declared = self._request_output_kind(request, candidates)
        matching = [r for r in candidates if r.artifact_kind == declared]
        if len(matching) == 1:
            return matching[0]
        if len(matching) > 1:
            raise ToolNotResolved(
                "the design declares output kind %r and %d registered compilers "
                "produce it (%s); which one runs is not this port's decision to "
                "make silently."
                % (declared, len(matching), ", ".join(r.key for r in matching))
            )
        raise ToolNotResolved(
            "the design declares output kind %r and no registered compiler on this "
            "backend produces it (registered: %s)."
            % (declared, self._registry._names(candidates))
        )

    def execute(self, request: PolicyRequest) -> ExecutionResult:
        try:
            registration = self._resolve(request)
            backend = self._registry.backend_for(registration)
        except ToolNotResolved as exc:
            return ExecutionResult(
                success=False,
                action_id=request.action_id,
                candidate_id=request.candidate_root.name,
                findings=(
                    Finding(
                        code="EXECUTOR_TOOL_NOT_RESOLVED",
                        message=str(exc),
                        source="toolports",
                    ),
                ),
            )
        try:
            payload, findings = backend.compile(registration, request)
        except ToolPlanError as exc:
            return ExecutionResult(
                success=False,
                action_id=request.action_id,
                candidate_id=request.candidate_root.name,
                findings=(
                    Finding(
                        code=exc.code,
                        message=exc.message,
                        source="toolports",
                        details=exc.details,
                    ),
                ),
            )
        except ToolBackendError as exc:
            return ExecutionResult(
                success=False,
                action_id=request.action_id,
                candidate_id=request.candidate_root.name,
                findings=(
                    Finding(code=exc.code, message=exc.message, source="toolports"),
                ),
            )
        if findings:
            return ExecutionResult(
                success=False,
                action_id=request.action_id,
                candidate_id=request.candidate_root.name,
                findings=findings,
            )
        artifact_name = getattr(backend, "artifact_name", None)
        artifacts = ()
        if isinstance(artifact_name, str) and artifact_name:
            # The executor is the single write path, so the name it reports must
            # be a single boring filename. The orchestrator independently refuses
            # an artifact that resolves outside the candidate root; this check is
            # the earlier one, because a backend that CAN name a path outside the
            # root is a defect worth failing on rather than detecting downstream.
            relative = Path(artifact_name)
            if relative.is_absolute() or len(relative.parts) != 1 or ".." in relative.parts:
                return ExecutionResult(
                    success=False,
                    action_id=request.action_id,
                    candidate_id=request.candidate_root.name,
                    findings=(
                        Finding(
                            code="EXECUTOR_ARTIFACT_NAME_INVALID",
                            message=(
                                "the backend reports artifact name %r; an artifact "
                                "must be a single filename inside the candidate "
                                "root" % (artifact_name,)
                            ),
                            source="toolports",
                        ),
                    ),
                )
            artifacts = (Path(request.candidate_root) / artifact_name,)
        return ExecutionResult(
            success=True,
            action_id=request.action_id,
            candidate_id=request.candidate_root.name,
            artifacts=artifacts,
            actor_id=registration.tool_id,
        )


class ToolVerifier:
    """VerifierPort over a registry: resolves the named verifier, then checks.

    The design it checks against is FROZEN AT ASSEMBLY from the operator's
    subject. It does not read the candidate's own declaration of what the design
    was, because a verifier that learns the expected answer from the thing it is
    checking is not verifying anything.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        backend: str,
        verifier_id: str,
        design_action: str,
        design_subject: Mapping[str, Any],
    ) -> None:
        self._registry = registry
        self._backend = backend
        self._design_action = design_action
        self._design_subject = dict(design_subject)
        self._registration = registry.resolve_verifier(verifier_id)
        registry.backend_for(self._registration)

    def verify(
        self, run_id: str, candidate_id: str, candidate_root: Path
    ) -> VerificationResult:
        """Read-only check. Never writes inside the candidate root."""
        try:
            backend = self._registry.backend_for(self._registration)
            payload, findings = backend.check(
                self._registration,
                Path(candidate_root),
                design_action=self._design_action,
                design_subject=self._design_subject,
            )
        except ToolNotResolved as exc:
            findings = (
                Finding(code="VERIFIER_TOOL_NOT_RESOLVED", message=str(exc), source="toolports"),
            )
            payload = None
        except ToolPlanError as exc:
            findings = (
                Finding(
                    code=exc.code,
                    message=exc.message,
                    source="toolports",
                    details=exc.details,
                ),
            )
            payload = None
        except ToolBackendError as exc:
            findings = (
                Finding(code=exc.code, message=exc.message, source="toolports"),
            )
            payload = None
        if not findings and self._registration.artifact_kind == ARTIFACT_KIND_HIR:
            # The plan can be correct while the file belongs to another domain,
            # run or candidate. Bind its identities to the pinned document and
            # this verification request, never to values read from the artifact.
            if not self._registry.domain_id or not isinstance(payload, Mapping):
                findings = (
                    Finding(
                        code="VERIFY_ARTIFACT_IDENTITY_UNBOUND",
                        message="HIR verification needs a pinned domain and an artifact identity",
                        source="toolports",
                    ),
                )
            else:
                expected = {
                    "domain_id": self._registry.domain_id,
                    "run_id": run_id,
                    "candidate_id": candidate_id,
                }
                findings = tuple(
                    Finding(
                        code="VERIFY_ARTIFACT_IDENTITY_MISMATCH",
                        message="artifact %s %r does not match this verification's identity %r"
                        % (field, payload.get(field), value),
                        source="toolports",
                        details={"field": field, "expected": value, "actual": payload.get(field)},
                    )
                    for field, value in expected.items()
                    if payload.get(field) != value
                )
        if findings:
            return VerificationResult(
                status=VerificationStatus.FAIL,
                candidate_id=candidate_id,
                findings=tuple(findings),
                actor_id=self._registration.tool_id,
            )
        return VerificationResult(
            status=VerificationStatus.PASS,
            candidate_id=candidate_id,
            findings=(
                Finding(
                    code="VERIFY_IN_REPO_HIR_SCOPE",
                    message=(
                        "PASS covers one thing: the artifact is a faithful, "
                        "structurally legal projection of the design this run's "
                        "policy approved, re-derived from the pinned rules and "
                        "compared against the bytes on disk. It does NOT establish "
                        "electrical correctness, ERC/DRC cleanliness, or "
                        "manufacturability, and no EDD-001 claim follows from it."
                    ),
                    source="in-repo-hir-verifier",
                    details={"design_action": self._design_action},
                ),
            ),
            actor_id=self._registration.tool_id,
        )


def build_tool_ports(
    registry: ToolRegistry,
    *,
    executor_backend: str,
    verifier_backend: str,
    verifier_id: str,
    design_action: str,
    design_subject: Mapping[str, Any],
):
    """Build the executor/verifier pair. THIN and in one place, on purpose.

    The CLI and the tests must wire the SAME pair; two assembly sites are how a
    test starts exercising a shape the runtime does not use. Every resolution
    failure raises here, at assembly, rather than mid-round.
    """
    return (
        ToolExecutor(registry, backend=executor_backend),
        ToolVerifier(
            registry,
            backend=verifier_backend,
            verifier_id=verifier_id,
            design_action=design_action,
            design_subject=design_subject,
        ),
    )


#: The backend assignments that make the in-repo artifact class reachable.
#:
#: This mapping is DECLARED, not inferred. A tool the domain registers that is
#: absent here is still registered -- and then refuses at assembly by name --
#: which is the direction that keeps an unauthorized tool from silently running.
IN_REPO_BACKENDS: Mapping[str, str] = MappingProxyType(
    {
        "in-repo-hir": BACKEND_IN_REPO_HIR,
        "in-repo-hir-verifier": BACKEND_IN_REPO_HIR,
    }
)

#: The tool the in-repo verifier has to be addressed by.
IN_REPO_VERIFIER_ID = "in-repo-hir-verifier"


class InRepoHirBackend:
    """One backend for both roles: write on the compile path, read on the check.

    Both roles are the same ARTIFACT CLASS -- that is what the registration names
    -- and keeping them in one object means a backend name cannot resolve to a
    writer in one place and a different checker in another. The independence that
    matters is not object identity: it is that check() re-derives the plan from
    the pinned rules and compares it against bytes on disk, which it does without
    consulting the compiler's output or any shared state.
    """

    backend = BACKEND_IN_REPO_HIR
    version = "1.0.0"

    def __init__(self, document: Any, *, artifact_name: str = HIR_ARTIFACT_NAME) -> None:
        self._compiler = InRepoHirCompiler(document, artifact_name=artifact_name)
        self._verifier = InRepoHirVerifier(document, artifact_name=artifact_name)
        self.artifact_name = artifact_name

    def compile(
        self, registration: ToolRegistration, request: PolicyRequest
    ) -> "tuple[dict[str, Any], tuple[Finding, ...]]":
        return self._compiler.compile(registration, request)

    def check(
        self,
        registration: ToolRegistration,
        candidate_root: Path,
        *,
        design_action: str | None = None,
        design_subject: Mapping[str, Any] | None = None,
    ) -> "tuple[dict[str, Any] | None, tuple[Finding, ...]]":
        if design_action is None or design_subject is None:
            raise ToolBackendError(
                "CHECK_NEEDS_DESIGN",
                "the in-repo verifier checks an artifact against the design the "
                "run was assembled with; it will not read that design back out of "
                "the artifact, because that is the thing being checked",
            )
        return self._verifier.check(
            registration,
            candidate_root,
            design_action=design_action,
            design_subject=design_subject,
        )


def build_in_repo_ports(
    engine: Any,
    *,
    design_action: str,
    design_subject: Mapping[str, Any],
    backend_for_tool: Mapping[str, str] | None = None,
) -> "tuple[ToolExecutor, ToolVerifier]":
    """Assemble the real executor/verifier pair over an engine's OWN registry.

    The engine is a SandboxPolicyEngine; its document is the only source of the
    tool set. Raises ToolNotResolved at assembly when the in-repo tool ids are
    not registered, which makes "this domain does not authorize this artifact
    class" a configuration error instead of a mid-run surprise.
    """
    # Accept either the engine or a policy port that fronts it: both expose
    # .document, and the CLI holds the port while the tests hold the engine.
    document = getattr(engine, "document", None)
    if document is None:
        # A fail-closed port refuses every evaluation and has no document. Saying
        # so by name is the difference between "the domain could not be loaded"
        # and "something passed me the wrong kind of object".
        reason = getattr(engine, "reason_code", None)
        if reason:
            raise ToolNotResolved(
                "the domain's policy port refuses every evaluation (%s), so its "
                "tool registry cannot be read. Fix the domain inputs first: a "
                "registry derived from a refused bundle would authorize tools for "
                "a domain that never loaded." % reason
            )
        raise ToolNotResolved(
            "the object passed to build_in_repo_ports exposes no .document, so "
            "the tool registry cannot be derived from the domain's own records. "
            "Pass a SandboxPolicyEngine or a policy port that fronts one."
        )
    mapping = dict(IN_REPO_BACKENDS)
    if backend_for_tool:
        mapping.update(backend_for_tool)
    registry = registry_from_document(
        document,
        backends={BACKEND_IN_REPO_HIR: InRepoHirBackend(document)},
        backend_for_tool=mapping,
    )
    return build_tool_ports(
        registry,
        executor_backend=BACKEND_IN_REPO_HIR,
        verifier_backend=BACKEND_IN_REPO_HIR,
        verifier_id=IN_REPO_VERIFIER_ID,
        design_action=design_action,
        design_subject=design_subject,
    )
