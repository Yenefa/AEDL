"""RepairAgent — prompt assembly, the model call loop, and the static gate.

This module is where an untrusted string becomes a validated
``RepairProposal``, or fails closed. RFC
``docs/specs/AEDL_AGENT_RUNTIME_RFC.md``:

* §2.3 never-grant — authoritative ``PolicyRequest`` fields
  (``schema.AUTHORITY_FIELDS``) appearing in model output are refused at
  parse time (threat T-07); this refusal is the observable evidence for the
  §2.5 N2 BLOCKING item.
* §2.2 / §3.3 — the three-fold static validation before any ``propose``
  construction: design_action whitelist (V1 set AND the run's
  ``action_schema``), ``design_subject`` exact field set + contract
  predicates (borrowed read-only from ``policy.engine.SUBJECT_SPECS`` so the
  harness and the policy engine cannot drift apart), and evidence-set
  checks (cited ⊆ available, required ⊆ cited, component membership in
  ``allowlist.allowed_components``).
* §5 D2 — every refusal is counted on the budget's invalid/format counters
  (the harness pre-validation layer), strictly separate from policy
  verdicts; consecutive-limit trips come from ``BudgetStop`` (N6/D4).
* §5 D1 — ``diagnosis``/findings are never rewritten: the context is
  rendered verbatim, so stall fingerprints stay meaningful.

Retry policy: malformed output is retried inside one ``propose`` round
(feedback appended to the transcript) up to ``AgentConfig.max_attempts``.
An *authority-field* violation is NOT retried — it is an adversarial
signal, and the gate fails fast without spending another model call.
Format/validation retries and their consecutive counters live here; the
stop decision lives in ``budget.BudgetStop`` (one place decides, per D4).

Declared not-implemented in V1 (ARH-HARNESS): the RFC §2.2 ``inspect_*``
tool loop — the model consumes the L0/L1 context as rendered and nothing
else. L1 sections may therefore be ``None``; that is a declared gap, not a
silent one.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from aedl_sandbox.arh.budget import BudgetStop
from aedl_sandbox.arh.model_adapter import (
    ModelAdapter,
    ModelMessage,
    ModelRequest,
)
from aedl_sandbox.arh.schema import (
    V1_DESIGN_ACTIONS,
    AuthorityFieldError,
    MalformedProposalError,
    ProposalError,
    RepairContext,
    RepairProposal,
    canonical_json,
    digest,
)
from aedl_sandbox.arh.trajectory import TrajectoryRecorder
from aedl_sandbox.policy.engine import SUBJECT_SPECS

__all__ = [
    "AgentConfig",
    "RepairAgent",
    "ValidationError",
]

#: Feedback lists are truncated so a pathological context cannot blow the
#: prompt with retry feedback (the L0 budget is the authority on length).
_FEEDBACK_MAX_LIST = 20

_SYSTEM_HEADER = (
    "You are the repair agent of the AEDL Engineering Design Sandbox.\n"
    "You receive verifier findings and produce exactly ONE repair proposal.\n"
    "You have NO execution authority: you cannot write files, run tools,\n"
    "compile, verify, approve, or grant capabilities. The orchestrator runs\n"
    "only what policy evaluation later allows.\n"
    "Never emit harness-owned fields (actor, capability_grants, run_id,\n"
    "domain_id, action, action_id, candidate_root, verified_bundle_sha256,\n"
    "verified_manifest_path): a proposal carrying any of them is refused.\n"
    "Output contract: exactly one JSON object, no markdown fences, no prose.\n"
    '  "diagnosis"        <=1 sentence citing a finding code, or UNKNOWN\n'
    '  "design_action"    must come from this run\'s action_schema\n'
    '  "design_subject"   the exact fields that action requires\n'
    '  "evidence_ids"     only ids present in allowlist.evidence_ids\n'
    '  "locator"          optional: contract_id/rule_fingerprint/pin/mpn/path/line\n'
)

_FENCE_RE = re.compile(r"\s*```[A-Za-z0-9_+-]*[ \t]*\r?\n(.*)\r?\n?```\s*", re.DOTALL)


class ValidationError(MalformedProposalError):
    """A proposal that parsed but failed a policy-vocabulary check.

    Carries the action/subject digest when they are known at the failure
    stage so the trajectory's rejected-row can dedup resubmissions
    (ChatRepair: 65% duplicate patches, RFC §3.2 row 7).
    """

    def __init__(
        self,
        message: str,
        *,
        design_action: str = "",
        subject_digest: str = "",
    ) -> None:
        super().__init__(message)
        self.design_action = design_action
        self.subject_digest = subject_digest


@dataclass(frozen=True)
class AgentConfig:
    """Knobs for one repair round. Defaults follow RFC §5 D3/D4 (TO_VERIFY)."""

    max_tokens: int = 2048
    temperature: float = 0.0
    max_attempts: int = 3  # total model calls per propose() round
    max_diagnosis_chars: int = 300

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1: a round that may not call the model must not start")


def _strip_code_fences(text: str) -> str:
    """Models wrap JSON in fences; fence-wrapping is formatting, not a fault.

    Stripping is deliberately narrow: only a full-document ``` fence is
    removed, so a response that *embeds* broken JSON still fails parsing and
    is counted as a format error.
    """
    match = _FENCE_RE.fullmatch(text)
    return match.group(1) if match else text


def _numbered(items: Sequence[str]) -> str:
    if not items:
        return "(deny list empty — this run carries none)\n"
    return "".join(f"{i}. {item}\n" for i, item in enumerate(items, start=1))


def _shorten(values: Sequence[Any]) -> list[Any]:
    return list(values[:_FEEDBACK_MAX_LIST])


class RepairAgent:
    """Calls the model and refuses everything that is not a valid proposal."""

    def __init__(
        self,
        model: ModelAdapter,
        config: AgentConfig | None = None,
        *,
        clock=time.monotonic,
    ) -> None:
        self._model = model
        self._config = config or AgentConfig()
        self._clock = clock

    # ------------------------------------------------------------- prompt

    def render_prompt(self, ctx: RepairContext) -> tuple[str, str]:
        """(system, user) for one round.

        The deny list is rendered at BOTH ends (system head, user tail) —
        position effects on long prompts are real, and RFC §2.3/D6 require
        the boundary to be visible where the model decides and where it
        formats its answer.
        """
        deny = tuple(ctx.deny_list)
        system = _SYSTEM_HEADER + "\nProhibited (deny list):\n" + _numbered(deny)
        body = canonical_json(ctx.to_prompt_dict())
        user = (
            "Repair round context (canonical JSON):\n"
            f"{body}\n\n"
            "Reminder — deny list:\n"
            f"{_numbered(deny)}"
            "Respond with exactly one JSON object."
        )
        return system, user

    # -------------------------------------------------------------- loop

    def propose(
        self,
        ctx: RepairContext,
        *,
        budget: BudgetStop,
        trajectory: TrajectoryRecorder,
        round_no: int,
    ) -> RepairProposal:
        """Run one repair round: call, parse, validate, retry, or fail closed.

        Raises ``BudgetExceeded`` (from the budget, never invented here),
        ``AuthorityFieldError`` (adversarial — no retry), or
        ``MalformedProposalError`` (retries exhausted). Every refusal is
        counted and written to the trajectory before raising.
        """
        system, user = self.render_prompt(ctx)
        prompt_digest = digest({"system": system, "user": user})
        messages: list[ModelMessage] = [
            ModelMessage("system", system),
            ModelMessage("user", user),
        ]
        last_error: ProposalError | None = None

        for attempt in range(1, self._config.max_attempts + 1):
            budget.check_before_call()
            response = self._model.complete(
                ModelRequest(
                    messages=tuple(messages),
                    max_tokens=self._config.max_tokens,
                    temperature=self._config.temperature,
                )
            )
            trajectory.record(
                "model_call",
                {
                    "round": round_no,
                    "attempt": attempt,
                    "prompt_digest": prompt_digest,
                    "model_id": response.model_id,
                    "usage": {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                        "cache_read_tokens": response.usage.cache_read_tokens,
                        "cache_write_tokens": response.usage.cache_write_tokens,
                    },
                    "latency_ms": response.latency_ms,
                },
            )
            budget.record_call(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_read_tokens=response.usage.cache_read_tokens,
                cache_write_tokens=response.usage.cache_write_tokens,
                latency_ms=response.latency_ms,
            )

            data = self._load(response.text)
            if data is _LOAD_FAILED:
                reason = "format: model output is not one JSON object"
                trajectory.record(
                    "rejected",
                    {"round": round_no, "design_action": "", "subject_digest": "", "reason": reason},
                )
                budget.record_format_error()  # may raise BudgetExceeded (D4)
                last_error = MalformedProposalError(reason)
                messages.extend(
                    [
                        ModelMessage("assistant", response.text),
                        ModelMessage("user", _format_feedback()),
                    ]
                )
                continue
            budget.record_format_ok()

            try:
                proposal = self._validate(data, ctx)
            except AuthorityFieldError as exc:
                # Adversarial: never retry, never continue the transcript.
                trajectory.record(
                    "rejected",
                    {"round": round_no, "design_action": "", "subject_digest": "",
                     "reason": f"authority_field: {exc}"},
                )
                budget.record_invalid_proposal()  # may raise BudgetExceeded
                raise
            except MalformedProposalError as exc:
                design_action = getattr(exc, "design_action", "")
                subject_digest = getattr(exc, "subject_digest", "")
                trajectory.record(
                    "rejected",
                    {"round": round_no, "design_action": design_action,
                     "subject_digest": subject_digest, "reason": str(exc)},
                )
                budget.record_invalid_proposal()  # may raise BudgetExceeded
                last_error = exc
                messages.extend(
                    [
                        ModelMessage("assistant", response.text),
                        ModelMessage("user", _validation_feedback(exc, ctx)),
                    ]
                )
                continue

            budget.record_valid_proposal()
            return proposal

        assert last_error is not None  # max_attempts >= 1 guarantees a recorded error
        raise last_error

    # ---------------------------------------------------------- internals

    @staticmethod
    def _load(text: str) -> Any:
        try:
            return json.loads(_strip_code_fences(text))
        except (json.JSONDecodeError, ValueError):
            return _LOAD_FAILED

    def _validate(self, data: Any, ctx: RepairContext) -> RepairProposal:
        """Stage 1 schema gate, then the three-fold policy-vocabulary gate."""
        # Stage 1: authority fields / envelope extras / types / locator keys.
        # Raises AuthorityFieldError (adversarial) or MalformedProposalError.
        proposal = RepairProposal.from_json(data)
        action = proposal.design_action

        # Stage 2: action vocabulary — the V1 set AND this run's schema.
        if action not in V1_DESIGN_ACTIONS:
            raise ValidationError(
                f"design_action {action!r} is outside the V1 whitelist "
                f"{sorted(V1_DESIGN_ACTIONS)}",
                design_action=action,
                subject_digest=proposal.subject_digest,
            )
        if action not in ctx.action_schema:
            raise ValidationError(
                f"design_action {action!r} is not offered by this run's action_schema "
                f"(offered: {sorted(ctx.action_schema)})",
                design_action=action,
                subject_digest=proposal.subject_digest,
            )

        # Stage 3: exact subject field set + contract predicates, straight
        # from the policy engine's own table (read-only import) so harness
        # pre-validation and policy verdicts cannot drift apart.
        spec = SUBJECT_SPECS.get(action)
        if spec is None:
            raise ValidationError(
                f"action {action!r} is absent from SUBJECT_SPECS — the harness "
                "refuses vocabulary it cannot verify",
                design_action=action,
                subject_digest=proposal.subject_digest,
            )
        expected = tuple(name for name, _ in spec)
        actual = tuple(proposal.design_subject)
        if set(actual) != set(expected):
            raise ValidationError(
                f"design_subject fields {sorted(actual)} != required {sorted(expected)} "
                f"for {action}",
                design_action=action,
                subject_digest=proposal.subject_digest,
            )
        for name, predicate in spec:
            if not predicate(proposal.design_subject[name]):
                raise ValidationError(
                    f"design_subject.{name} failed the contract predicate for {action}",
                    design_action=action,
                    subject_digest=proposal.subject_digest,
                )

        # Stage 4: locator path sanity (the only path surface in V1).
        locator_path = proposal.locator.get("path")
        if isinstance(locator_path, str) and not _is_safe_relative_path(locator_path):
            raise ValidationError(
                f"locator.path {locator_path!r} must be relative and contain no '..'",
                design_action=action,
                subject_digest=proposal.subject_digest,
            )

        # Stage 5: evidence sets — cited ⊆ available, component membership,
        # required ⊆ cited (RFC §3.2 row 9, §3.3).
        cited = set(proposal.evidence_ids)
        subject_evidence = proposal.design_subject.get("evidence_ids")
        if isinstance(subject_evidence, (list, tuple)):
            cited.update(str(item) for item in subject_evidence)
        available = set(ctx.allowlist.get("evidence_ids") or ())
        unknown = sorted(cited - available)
        if unknown:
            raise ValidationError(
                f"evidence id(s) not in allowlist.evidence_ids: {_shorten(unknown)}",
                design_action=action,
                subject_digest=proposal.subject_digest,
            )
        if action == "DESIGN_SELECT_COMPONENT":
            components = ctx.allowlist.get("allowed_components")
            if not isinstance(components, (list, tuple)) or not components:
                # Fail closed: with no component allowlist there is nothing to
                # check membership against, and RFC row 9 says proposals draw
                # their targets from this set.
                raise ValidationError(
                    "allowlist.allowed_components is absent/empty — component "
                    "membership cannot be verified (fail-closed)",
                    design_action=action,
                    subject_digest=proposal.subject_digest,
                )
            mpn = proposal.design_subject["mpn"]
            entry = next(
                (
                    item
                    for item in components
                    if isinstance(item, Mapping) and item.get("mpn") == mpn
                ),
                None,
            )
            if entry is None:
                raise ValidationError(
                    f"mpn {mpn!r} is not in allowlist.allowed_components",
                    design_action=action,
                    subject_digest=proposal.subject_digest,
                )
            required = {str(item) for item in (entry.get("required_evidence_ids") or ())}
            missing = sorted(required - cited)
            if missing:
                raise ValidationError(
                    f"required evidence not cited: {_shorten(missing)}",
                    design_action=action,
                    subject_digest=proposal.subject_digest,
                )

        # Stage 6: diagnosis discipline — cite a real finding code or say
        # UNKNOWN; never rewrite findings, only anchor to them (D1).
        diagnosis = proposal.diagnosis.strip()
        if not diagnosis:
            raise ValidationError(
                "diagnosis is empty",
                design_action=action,
                subject_digest=proposal.subject_digest,
            )
        if len(diagnosis) > self._config.max_diagnosis_chars:
            raise ValidationError(
                f"diagnosis is {len(diagnosis)} chars, max {self._config.max_diagnosis_chars}",
                design_action=action,
                subject_digest=proposal.subject_digest,
            )
        codes = [finding.code for finding in ctx.findings_current]
        if "UNKNOWN" not in diagnosis and not any(code in diagnosis for code in codes):
            raise ValidationError(
                "diagnosis must cite one of the finding codes "
                f"{_shorten(codes) if codes else '()'} or say UNKNOWN",
                design_action=action,
                subject_digest=proposal.subject_digest,
            )
        return proposal


# Sentinel distinct from any legal JSON value (None is legal JSON).
_LOAD_FAILED = object()


def _format_feedback() -> str:
    return (
        "Your previous reply was not a single JSON object. Reply with exactly "
        "ONE JSON object and nothing else — no markdown fences, no prose. "
        "Keys: diagnosis, design_action, design_subject, evidence_ids, locator."
    )


def _validation_feedback(error: ProposalError, ctx: RepairContext) -> str:
    offered = sorted(ctx.action_schema)
    codes = [finding.code for finding in ctx.findings_current]
    return (
        f"Your previous proposal was rejected: {error}. "
        f"Allowed design_action values: {offered or sorted(V1_DESIGN_ACTIONS)}. "
        f"Finding codes available to cite: {_shorten(codes) if codes else '(none — say UNKNOWN)'}. "
        "Produce a corrected JSON object."
    )


def _is_safe_relative_path(path: str) -> bool:
    """Relative, no traversal, no drive/UNC — locator.path is text only."""
    if not path or path.startswith(("/", "\\")) or path.startswith("~"):
        return False
    if re.match(r"^[A-Za-z]:", path):
        return False
    parts = re.split(r"[\\/]", path)
    return ".." not in parts
