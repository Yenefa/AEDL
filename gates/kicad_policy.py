"""The policy layer.  The ONLY place a verdict is produced.

Separated from the producer on purpose, and the separation is the whole point of the
Owner's instruction. `kicad_evidence.collect_evidence` reports what KiCad did, what it
found, and what it declared it skipped. It has no opinion. This module takes that
bundle and decides, and it records **which evidence it decided on** so a decision can
never be separated from the evidence that justified it.

Why this cannot collapse back into `ERC=0 -> PASS`, which is what the code did before:

    the bundle carries the SEVERITY MIX, not just an error count
    the bundle carries `ignored_checks`, read from KiCad's own report
    the decision records both, plus the bundle digest

The board this repository actually ships measures as: 0 error-severity violations, 39
warnings, 4 checks deliberately ignored. A policy that only read the error count would
pass it. This policy cannot pass it while those limits are in force without saying so,
because `ignored_checks` is a first-class part of the decision record and a non-empty
list is a reason the policy is allowed to refuse.

Three rules the policy applies, in order, and each one is a separate mutation target:

  R1  COHERENCE. An incoherent bundle -- parts bound to different bytes, or a report
      that will not say what it skipped -- cannot be decided on at all. Refused, not
      judged.

  R2  COMPLETENESS. Every part the policy requires must be present AND completed. A
      missing render is not a pass with one fewer data point.

  R3  THE LIMITS. `ignored_checks` must be permitted by the policy, and any severity
      the tool actually produced must be one the policy tolerates. Warnings are counted
      against a budget rather than ignored, so "0 errors" cannot stand in for "clean".

Fail closed throughout, and the reason is always recorded. There is no default policy
and no fallback verdict: a bundle with no policy attached is REFUSED, because a
verdict that appears without a stated basis is the exact failure being repaired.
"""

from __future__ import annotations

from typing import Any, Mapping

DECISIONS = ("PASS", "REFUSE", "NOT_RUN")

#: The reasons a policy may refuse, so a refusal is never free text.
REFUSE_INCOHERENT = "EVIDENCE_INCOHERENT"
REFUSE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
REFUSE_IGNORED_CHECKS = "IGNORED_CHECKS_NOT_PERMITTED"
REFUSE_SEVERITY = "SEVERITY_NOT_TOLERATED"
REFUSE_WARNING_BUDGET = "WARNING_BUDGET_EXCEEDED"
REFUSE_NO_POLICY = "NO_POLICY_BOUND"
REFUSE_UNBOUND = "EVIDENCE_NOT_BOUND_TO_THIS_DESIGN"

#: Parts a policy must have before it may decide anything at all.
REQUIRED_PARTS = ("erc", "netlist", "render")


def default_policy() -> dict:
    """A policy that is explicit about every choice it makes.

    `tolerated_severities` omits "error" on purpose -- that is the default posture,
    not an oversight. `warning_budget` is finite so that a board cannot accumulate
    warnings indefinitely behind a passing transaction. `permitted_ignored_checks` is
    empty, so the CURRENT board is REFUSED by the default policy: it declares four
    skipped checks, and a policy that has not been told those are acceptable must not
    wave them through.
    """
    return {
        "schema_version": "kicad-policy.v1",
        "required_parts": list(REQUIRED_PARTS),
        "tolerated_severities": ["warning", "exclusion"],
        "warning_budget": 0,
        "permitted_ignored_checks": [],
        "require_declared_limits": True,
    }


def _reason(code: str, detail: str) -> dict:
    return {"code": code, "detail": detail}


def decide(bundle: Mapping[str, Any] | None,
           policy: Mapping[str, Any] | None = None,
           expected_design_sha256: str | None = None) -> dict:
    """Decide from a bundle. Returns a decision that names the evidence it used.

    Never raises for a bad bundle: an unusable bundle is a REFUSE with a reason,
    because a policy that throws has no verdict to record and the caller is left
    guessing, which is how `ERC=0 -> PASS` looked from the outside.
    """
    if policy is None:
        return {
            "decision": "REFUSE",
            "reason_codes": [_reason(
                REFUSE_NO_POLICY,
                "no policy was bound, and a verdict without a stated basis is the "
                "failure this layer exists to prevent")],
            "decided_on": None,
            "bundle_sha256": None,
        }
    if not isinstance(bundle, Mapping):
        return {
            "decision": "REFUSE",
            "reason_codes": [_reason(REFUSE_NO_POLICY,
                                     "no evidence bundle was supplied")],
            "decided_on": None,
            "bundle_sha256": None,
        }

    erc = bundle.get("erc") or {}
    limits = erc.get("declared_limits") or {}
    ignored = limits.get("ignored_checks") or []
    severities = limits.get("included_severities") or []
    severity_counts = erc.get("severity_counts") or {}

    decided_on = {
        "bundle_sha256": bundle.get("bundle_sha256"),
        "design_sha256": bundle.get("design_sha256"),
        "kicad_version": (bundle.get("tool_identity") or {}).get(
            "kicad_version_reported"),
        "ignored_checks": ignored,
        "included_severities": severities,
        "severity_counts": severity_counts,
        "error_count": erc.get("error_count"),
        "warnings": severity_counts.get("warning", 0),
    }
    reasons: list[dict] = []

    def refuse() -> dict:
        return {"decision": "REFUSE", "reason_codes": reasons,
                "decided_on": decided_on,
                "bundle_sha256": bundle.get("bundle_sha256")}

    # --- R0 the evidence must be about the design being promoted ------------
    if expected_design_sha256 is not None and \
            bundle.get("design_sha256") != expected_design_sha256:
        reasons.append(_reason(
            REFUSE_UNBOUND,
            "the evidence was produced from design %s but %s is being promoted"
            % (str(bundle.get("design_sha256"))[:12],
               str(expected_design_sha256)[:12])))
        return refuse()

    # --- R1 coherence --------------------------------------------------------
    if not bundle.get("coherent"):
        for problem in bundle.get("incoherence") or ["the bundle is not coherent"]:
            reasons.append(_reason(REFUSE_INCOHERENT, problem))
        return refuse()

    # --- R2 completeness -----------------------------------------------------
    for name in policy.get("required_parts") or REQUIRED_PARTS:
        part = bundle.get(name)
        if not isinstance(part, Mapping) or not part.get("completed"):
            reasons.append(_reason(
                REFUSE_INCOMPLETE,
                "the %s evidence is missing or did not complete" % name))
        elif not part.get("artifacts"):
            reasons.append(_reason(
                REFUSE_INCOMPLETE,
                "the %s evidence completed but produced no artifact to point at"
                % name))
    if reasons:
        return refuse()

    # --- R3 the limits -------------------------------------------------------
    if policy.get("require_declared_limits", True) and not erc.get("limits_declared"):
        reasons.append(_reason(
            REFUSE_IGNORED_CHECKS,
            "the ERC evidence does not declare what it skipped, so it cannot be "
            "decided on"))
        return refuse()

    permitted = set(policy.get("permitted_ignored_checks") or [])
    unpermitted = [c for c in ignored
                   if (c.get("key") if isinstance(c, Mapping) else c)
                   not in permitted]
    if unpermitted:
        reasons.append(_reason(
            REFUSE_IGNORED_CHECKS,
            "the ERC run skipped %d check(s) the policy has not permitted: %s"
            % (len(unpermitted),
               ", ".join(sorted(str(c.get("key") if isinstance(c, Mapping) else c)
                                for c in unpermitted)))))

    tolerated = set(policy.get("tolerated_severities") or ())
    produced = {sev for sev, count in severity_counts.items() if count}
    intolerable = sorted(produced - tolerated)
    if intolerable:
        reasons.append(_reason(
            REFUSE_SEVERITY,
            "the ERC run produced severity the policy does not tolerate: %s"
            % ", ".join(intolerable)))

    warnings = int(severity_counts.get("warning", 0) or 0)
    budget = policy.get("warning_budget")
    if budget is not None and warnings > int(budget):
        reasons.append(_reason(
            REFUSE_WARNING_BUDGET,
            "%d ERC warning(s) against a budget of %s; zero errors is not the same "
            "claim as a clean board" % (warnings, budget)))

    if reasons:
        return refuse()

    return {
        "decision": "PASS",
        "reason_codes": [],
        "decided_on": decided_on,
        "bundle_sha256": bundle.get("bundle_sha256"),
    }
