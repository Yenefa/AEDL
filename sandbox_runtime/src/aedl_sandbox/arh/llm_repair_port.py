"""LLMRepairPort — the only door between an LLM and the RepairPort contract.

``RepairPort.propose(run_id, candidate_id, findings) -> PolicyRequest`` is a
frozen contract (ADR-016, RFC §1.2 KEEP row). This class implements it by
closing one repair round:

    inputs  <- ContextInputsProvider   (wiring supplies projected state; the
                                        model never sees raw state, D6)
    context <- ContextBuilder          (L0/L1 assembly, trim budget)
    probe   <- RepairAgent             (model call + static gate)
    request <- THE HARNESS             (actor / action_id / capability_grants
                                        are stamped here, never parsed)

Security-relevant properties, each covered by a test in
``tests/arh/test_arh_llm_repair_port.py``:

* ``actor`` is fixed to ``actor_kind="agent"`` and ``capability_grants`` is
  always ``()`` — V1 enables no capability at all (G1 stays unimplemented,
  grants absent → policy's grant path stays fail-closed).
* ``domain_id`` / ``candidate_root`` come from the provider inputs only;
  model text cannot influence them (RFC §2.3, threat T-07).
* The returned ``subject`` is exactly ``{design_action, design_subject}``
  — the shape ``adapters._evaluate_design_action`` unwraps; ``action`` is
  the plan-carrier string ``"repair"`` (same convention as the repository's
  own fixtures), because preflight/execute build their own authoritative
  requests and never evaluate the plan's ``action``.
* Refusals raise (``ProposalError``) instead of fabricating a request:
  there is no honest ``PolicyRequest`` for "the model never produced a
  valid proposal". Mapping that exception onto a terminal orchestrator
  state is future wiring — the orchestrator is untouched in this envelope.

Declared not-implemented (ARH-HARNESS): real assembly of
``ContextInputsProvider`` from a live orchestrator state — the orchestrator
is frozen in this envelope, so production wiring arrives after it unfreezes.
Tests inject the provider and prove the flow end to end without it.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Protocol

from aedl_sandbox.arh.budget import BudgetExceeded, BudgetStop
from aedl_sandbox.arh.context_builder import ContextBuilder
from aedl_sandbox.arh.model_adapter import ModelAdapter
from aedl_sandbox.arh.repair_agent import AgentConfig, RepairAgent
from aedl_sandbox.arh.schema import (
    AuthorityFieldError,
    ContextInputs,
    ProposalError,
    RepairProposal,
)
from aedl_sandbox.arh.trajectory import TrajectoryRecorder
from aedl_sandbox.protocol import ActorIdentity, Finding, PolicyRequest, RepairPort

__all__ = [
    "ContextInputsProvider",
    "LLMRepairPort",
    "ARH_ACTOR_ID",
]

#: The only actor this port ever stamps. Descriptive by itself (protocol
#: ActorIdentity docstring): authority still comes only from grant receipts,
#: and V1 holds none.
ARH_ACTOR_ID = "arh-repair-agent"

#: The plan-carrier action string on the returned request. The orchestrator
#: stores ``action``/``action_id``/``subject`` as the repair plan and builds
#: its own ``preflight`` / ``execute_candidate`` requests afterwards; policy
#: never evaluates this string (adapters.py dispatches on its own requests).
PLAN_CARRIER_ACTION = "repair"


class ContextInputsProvider(Protocol):
    """Wiring hook: projected run state for one round.

    Implementations must return already-projected fields (RFC §3.2, D6) —
    this port never opens ``engine.document`` or trust stores itself.
    """

    def __call__(
        self, run_id: str, candidate_id: str, findings: tuple[Finding, ...]
    ) -> ContextInputs: ...


class LLMRepairPort(RepairPort):
    """Proposal-only repair through a model, with the harness holding all authority."""

    def __init__(
        self,
        *,
        model: ModelAdapter,
        inputs_provider: ContextInputsProvider,
        trajectory: TrajectoryRecorder,
        budget: BudgetStop,
        builder: ContextBuilder | None = None,
        agent: RepairAgent | None = None,
        agent_config: AgentConfig | None = None,
        clock=time.monotonic,
    ) -> None:
        self._model = model
        self._inputs = inputs_provider
        self._trajectory = trajectory
        self._budget = budget
        self._builder = builder or ContextBuilder()
        self._agent = agent or RepairAgent(model, agent_config, clock=clock)

    def propose(
        self, run_id: str, candidate_id: str, findings: tuple[Finding, ...]
    ) -> PolicyRequest:
        findings = tuple(findings)
        inputs = self._inputs(run_id, candidate_id, findings)

        # Round numbers count recorded rounds, so they stay monotonic across
        # process restarts (the trajectory file is append-only per run).
        round_no = len(self._trajectory.rows("round_start")) + 1

        ctx, report = self._builder.build_with_report(
            inputs,
            findings,
            self._trajectory.attempts(),
            self._trajectory.rejected(),
        )
        self._trajectory.record(
            "round_start",
            {
                "round": round_no,
                "candidate_id": candidate_id,
                "context_digest": ctx.digest,
                "findings_before": [finding.code for finding in findings],
                "estimated_tokens": report.estimated_tokens,
                "trims": list(report.trims),
                "over_budget": report.over_budget,
            },
        )

        try:
            proposal = self._agent.propose(
                ctx,
                budget=self._budget,
                trajectory=self._trajectory,
                round_no=round_no,
            )
        except BudgetExceeded as exc:
            self._trajectory.record(
                "budget_trip",
                {"round": round_no, "code": exc.code, "budget": self._budget.snapshot()},
            )
            raise
        except ProposalError as exc:
            # Authority violations keep their classification at round level:
            # an audit reader must not have to correlate two rows to learn
            # that a round died to an injection attempt (N2).
            prefix = "authority_field: " if isinstance(exc, AuthorityFieldError) else ""
            self._trajectory.record(
                "round_failed",
                {"round": round_no, "reason": prefix + str(exc)},
            )
            raise

        fingerprint_now = str(ctx.fingerprint_state.get("now") or "")
        self._trajectory.record(
            "attempt",
            {
                "round": round_no,
                "fingerprint12": fingerprint_now[:12],
                "diagnosis": proposal.diagnosis,
                "design_action": proposal.design_action,
                "subject_digest": proposal.subject_digest,
                "outcome": "accepted",
            },
        )
        return self._build_request(run_id, round_no, inputs, proposal)

    # ----------------------------------------------------------- request

    @staticmethod
    def _build_request(
        run_id: str,
        round_no: int,
        inputs: ContextInputs,
        proposal: RepairProposal,
    ) -> PolicyRequest:
        """Harness-stamped fields; nothing here originates in model text."""
        return PolicyRequest(
            run_id=run_id,
            domain_id=inputs.domain_id,
            action_id=f"arh-r{round_no}",
            action=PLAN_CARRIER_ACTION,
            candidate_root=Path(inputs.candidate_root),
            subject=proposal.envelope(),
            actor=ActorIdentity(
                actor_id=ARH_ACTOR_ID,
                actor_kind="agent",
                run_id=run_id,
            ),
            capability_grants=(),
        )
