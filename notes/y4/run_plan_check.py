"""Five-case Y4-dry run-plan validator (GH-56 freeze preparation).

Machine-enforces the owner-approved structure: canonical experiment and runner
identity, five neutral cases, C/D arms, three repetitions, one Proposal attempt
per slot, exactly 30 unique slots, C=15 / D=15, and an execution order that is a
permutation of the slots. This is a planning validator: it never runs an
experiment, never reads private material and never promotes anything.

CLI (exit 0 PASS / 1 FAIL):
    py -3.9 -m notes.y4.run_plan_check <run-plan.json> [--json]
Tests:
    py -3.9 -m unittest notes.y4.run_plan_check
"""
import argparse
import json
import sys
from pathlib import Path

from tools import y4_dry_runner as runner

# Single source of truth: canonical identity comes from the runner itself, so a
# runner version bump (e.g. y4-dry.v4 attempt enforcement) cannot silently drift
# from the validator. REPETITIONS/ATTEMPTS_PER_SLOT fall back to the approved
# protocol values for runners that predate those constants.
EXPERIMENT_ID = runner.EXPERIMENT_VERSION
RUNNER_VERSION = runner.RUNNER_VERSION
CASES = tuple(runner.CASE_IDS)
ARMS = ("C", "D")
REPETITIONS = tuple(range(1, getattr(runner, "REPETITIONS", 3) + 1))
ATTEMPTS_PER_SLOT = getattr(runner, "ATTEMPTS_PER_SLOT", 1)
TOTAL_SLOTS = len(CASES) * len(ARMS) * len(REPETITIONS)


def canonical_slots():
    return {"%s-%s-r%d" % (case, arm, repetition)
            for case in CASES for arm in ARMS for repetition in REPETITIONS}


def validate(plan):
    """Return a list of failure reasons; empty list means PASS.

    Closed top-level validation: cases / arms / repetitions / attempts_per_slot /
    total_slots are required and exact. Every slot must be semantically
    consistent: slot_id == "<case>-<arm>-r<repetition>", legal case/arm/
    repetition, attempts_per_slot == 1 and status == "NOT_RUN" (before freeze).
    Slot IDs alone can never prove a plan; the fields and the ID must agree.
    """
    reasons = []
    if not isinstance(plan, dict):
        return ["run plan must be a JSON object"]
    if plan.get("experiment_id") != EXPERIMENT_ID:
        reasons.append("experiment_id mismatch")
    if plan.get("runner_version") != RUNNER_VERSION:
        reasons.append("runner_version mismatch")
    if list(plan.get("cases") or []) != list(CASES):
        reasons.append("cases mismatch")
    if list(plan.get("arms") or []) != list(ARMS):
        reasons.append("arms mismatch")
    if plan.get("repetitions") != len(REPETITIONS):
        reasons.append("repetitions must be %d" % len(REPETITIONS))
    if plan.get("attempts_per_slot") != ATTEMPTS_PER_SLOT:
        reasons.append("attempts_per_slot must be %d" % ATTEMPTS_PER_SLOT)
    if plan.get("total_slots") != TOTAL_SLOTS:
        reasons.append("total_slots must be %d" % TOTAL_SLOTS)

    slots = plan.get("slots")
    if not isinstance(slots, list):
        return reasons + ["slots must be a list"]
    expected = canonical_slots()
    slot_ids = [s.get("slot_id") if isinstance(s, dict) else None for s in slots]
    if len(slot_ids) != TOTAL_SLOTS:
        reasons.append("slots count must be %d (got %d)" % (TOTAL_SLOTS, len(slot_ids)))
    if len(set(slot_ids)) != len(slot_ids):
        reasons.append("duplicate slot_id")
    if set(slot_ids) != expected:
        reasons.append("slots are not exactly the %d canonical slots" % TOTAL_SLOTS)
    for slot in slots:
        if not isinstance(slot, dict):
            reasons.append("slot entries must be objects")
            break
        slot_id = slot.get("slot_id")
        case = slot.get("case_public_id")
        arm = slot.get("arm")
        repetition = slot.get("repetition")
        if case not in CASES:
            reasons.append("slot %s case_public_id invalid" % slot_id)
        if arm not in ARMS:
            reasons.append("slot %s arm invalid" % slot_id)
        if repetition not in REPETITIONS:
            reasons.append("slot %s repetition invalid" % slot_id)
        if (case in CASES and arm in ARMS and repetition in REPETITIONS
                and slot_id != "%s-%s-r%s" % (case, arm, repetition)):
            reasons.append("slot %s does not match case/arm/repetition %s-%s-r%s"
                           % (slot_id, case, arm, repetition))
        if slot.get("attempts_per_slot") != ATTEMPTS_PER_SLOT:
            reasons.append("slot %s attempts_per_slot != %d" % (slot_id, ATTEMPTS_PER_SLOT))
        if slot.get("status") != "NOT_RUN":
            reasons.append("slot %s status must be NOT_RUN" % slot_id)
    if sum(1 for s in slots if isinstance(s, dict) and s.get("arm") == "C") != 15:
        reasons.append("C slots must be 15")
    if sum(1 for s in slots if isinstance(s, dict) and s.get("arm") == "D") != 15:
        reasons.append("D slots must be 15")

    order = plan.get("execution_order")
    if not isinstance(order, list):
        reasons.append("execution_order must be a list")
    elif sorted(order) != sorted(slot_ids):
        reasons.append("execution_order must be a permutation of slot_ids")
    return reasons


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    reasons = validate(plan)
    print(json.dumps({"plan": args.plan, "verdict": "PASS" if not reasons else "FAIL",
                      "reasons": reasons}, indent=1))
    return 0 if not reasons else 1


def _synthetic_plan():
    slots = [{"slot_id": s, "case_public_id": s.rsplit("-", 2)[0],
              "arm": s.rsplit("-", 2)[1], "repetition": int(s.rsplit("-r", 1)[1]),
              "attempts_per_slot": 1, "status": "NOT_RUN"} for s in
             sorted(canonical_slots())]
    order = list(reversed([s["slot_id"] for s in slots]))
    return {"experiment_id": EXPERIMENT_ID, "runner_version": RUNNER_VERSION,
            "cases": list(CASES), "arms": list(ARMS), "repetitions": 3,
            "attempts_per_slot": 1, "total_slots": 30, "slots": slots,
            "execution_order": order}


if __name__ == "__main__":
    sys.exit(main())


import unittest  # noqa: E402  (kept at bottom so the CLI stays lightweight)


class RunPlanCheckTests(unittest.TestCase):
    def test_canonical_plan_passes(self):
        self.assertEqual(validate(_synthetic_plan()), [])

    def test_wrong_identity_counts_fail(self):
        plan = _synthetic_plan()
        plan["experiment_id"] = "y4-dry-old"
        plan["attempts_per_slot"] = 2
        plan["total_slots"] = 36
        reasons = validate(plan)
        self.assertIn("experiment_id mismatch", reasons)
        self.assertIn("attempts_per_slot must be 1", reasons)
        self.assertIn("total_slots must be 30", reasons)

    def test_duplicate_or_missing_slots_fail(self):
        plan = _synthetic_plan()
        plan["slots"][1] = dict(plan["slots"][0])
        reasons = validate(plan)
        self.assertIn("duplicate slot_id", reasons)
        self.assertIn("slots are not exactly the 30 canonical slots", reasons)

    def test_slot_level_attempt_must_be_one(self):
        plan = _synthetic_plan()
        plan["slots"][0]["attempts_per_slot"] = 2
        self.assertIn("slot Y4-001-C-r1 attempts_per_slot != 1", validate(plan))

    def test_broken_execution_order_fails(self):
        plan = _synthetic_plan()
        plan["execution_order"] = plan["execution_order"][:-1]
        self.assertIn("execution_order must be a permutation of slot_ids",
                      validate(plan))

    def test_arm_counts_enforced(self):
        plan = _synthetic_plan()
        for slot in plan["slots"]:
            if slot["arm"] == "D":
                slot["arm"] = "C"
                break
        self.assertIn("C slots must be 15", validate(plan))

    def test_slot_case_field_must_match_slot_id(self):
        # slot_id stays canonical but case_public_id diverges -> FAIL.
        plan = _synthetic_plan()
        plan["slots"][0]["case_public_id"] = "Y4-999"
        self.assertIn("slot Y4-001-C-r1 case_public_id invalid", validate(plan))

    def test_arm_swap_keeps_counts_but_fails_semantic_binding(self):
        # Two slots swap arm values; slot_ids and C/D counts stay 15/15, so only
        # the slot-level semantic binding can catch it -> must FAIL.
        plan = _synthetic_plan()
        c_slot = next(s for s in plan["slots"] if s["arm"] == "C")
        d_slot = next(s for s in plan["slots"] if s["arm"] == "D")
        c_slot["arm"], d_slot["arm"] = "D", "C"
        reasons = validate(plan)
        self.assertNotIn("C slots must be 15", reasons)
        self.assertNotIn("D slots must be 15", reasons)
        self.assertTrue(any("does not match case/arm/repetition" in r for r in reasons),
                        reasons)

    def test_repetition_must_be_canonical(self):
        plan = _synthetic_plan()
        plan["slots"][0]["repetition"] = 99
        self.assertIn("slot Y4-001-C-r1 repetition invalid", validate(plan))

    def test_slot_status_must_be_not_run(self):
        plan = _synthetic_plan()
        plan["slots"][0]["status"] = "PASS"
        self.assertIn("slot Y4-001-C-r1 status must be NOT_RUN", validate(plan))

    def test_thirty_six_slot_legacy_plan_is_not_canonical(self):
        # The retired six-case structure (6 x C/D x 3 = 36) must never validate.
        legacy_cases = ["Y4-001", "Y4-002", "Y4-003", "Y4-004", "Y4-005", "Y4-006"]
        slots = [{"slot_id": "%s-%s-r%d" % (case, arm, repetition),
                  "case_public_id": case, "arm": arm, "repetition": repetition,
                  "attempts_per_slot": 1, "status": "NOT_RUN"}
                 for case in legacy_cases for arm in ARMS for repetition in REPETITIONS]
        plan = _synthetic_plan()
        plan["cases"] = legacy_cases
        plan["slots"] = slots
        plan["total_slots"] = len(slots)
        plan["execution_order"] = [s["slot_id"] for s in slots]
        reasons = validate(plan)
        self.assertIn("cases mismatch", reasons)
        self.assertIn("total_slots must be 30", reasons)
        self.assertIn("slots are not exactly the 30 canonical slots", reasons)
