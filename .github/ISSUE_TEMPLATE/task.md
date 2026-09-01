---
name: AEDL task
about: Create a scoped engineering, research, or governance task
title: ""
labels: ""
assignees: ""
---

## Goal

State the single outcome this task must achieve.

## Scope

### In scope

- List the permitted work.

### Out of scope

- List adjacent work that must not be included.

## Ownership

- Owner: `TO_ASSIGN`
- Contributor classification: `TO_VERIFY` (`AEDL_TEAM` / `EXTERNAL_CONTRIBUTOR`)
- Start condition: do not begin until exactly one owner is assigned.

## Base

Baseline approved at task creation; drift from it = BLOCKED until a human decision (admission checks this).

```yaml
base:
  branch: master
  sha: <approval-time-SHA>
```

## Owned paths (Allowed Paths)

- List every writable file or directory (glob patterns allowed).

## Forbidden paths

- List paths that are default-denied for this task; crossing them requires STOP + scope expansion approved by the human owner.

## Shared read-only paths and dependencies

- List files that may be read but must not be changed.
- List upstream Issues, contracts, or human decisions.
- Machine-checked dependencies (admission blocks until satisfied):

```yaml
dependencies:
  - ref: GH-9
    required_state: merged   # merged | closed | open
```

## Change Budget

Declare expected size before starting; if actuals exceed the budget, STOP and redo the impact analysis (AGENTS.md §2.2):

```yaml
change_budget:
  expected_files: N
  expected_modules: [module-a]
  cross_module: false
  contract_change: false
  evidence_semantics_change: false
```

## Verification Policy Change

- Mark YES only when this task modifies `.github/workflows/**` or the required test set, secret scan, runner environment, or skip conditions. Such changes require both human owners (Yenefa + Percy) to confirm.
- `YES / NO`

## Acceptance criteria

- [ ] Goal is met without expanding scope.
- [ ] Task-specific verification has been run and recorded.
- [ ] `git status`, working diff, and staged diff have been reviewed.
- [ ] No secret, unrelated file, or unverified technical claim is included.
- [ ] Compliance records triggered by the work are updated.

## Verification

- Commands to run: `TO_VERIFY`
- Evidence Needed: `YES / NO / TO_VERIFY`
- AIC Score Target: `NONE / UNKNOWN / <score item>`

## Compliance triggers

- AI Usage: `YES / NO / TO_VERIFY`
- Third-party: `YES / NO / TO_VERIFY`
- ADR: `YES / NO / TO_VERIFY`
- Evidence Index: `YES / NO / TO_VERIFY`
- Fusion Map / Open Outputs / Submission Check: `YES / NO / TO_VERIFY`

## Escalation

When BLOCKED (admission, gate, or boundary): STOP → Explain → Escalate → Human decision → Record → Resume/Reject. Never silently bypass.

```text
BLOCKED
Task: <GH-N>
Reason:
Observed need:
Requested:
Owner decision: PENDING / APPROVED / REJECTED
Decision ref:
```

## Known risks and blockers

- Record `UNKNOWN`, `TO_VERIFY`, `NOT_RUN`, `PENDING`, or `BLOCKED` explicitly.

## Human review

`PENDING_HUMAN_REVIEW`
