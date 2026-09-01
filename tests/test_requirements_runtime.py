"""Boundary tests for gates/requirements_runtime.parse_llm_proposal (TASK-P7 pool item 5).

Discipline: tests only - the implementation is NOT modified in this task. Any
suspected implementation bug is pinned as current behavior with a comment and
recorded in docs/OVERNIGHT_20260901.md TASK-P7 progress log for human review.

parse_llm_proposal is the anti-hallucination boundary between LLM output and
the requirements contract: junk in -> empty/warning (never an exception),
answers NEVER come from the model, unknown severity escalates to blocking.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gates.requirements_runtime import parse_llm_proposal, _MAX_QUESTIONS


def _proposal(**overrides):
    """A minimal well-formed LLM proposal payload."""
    payload = {
        "questions": [
            {"id": "Q1", "question": "power source?", "kind": "blocking",
             "options": ["USB", "battery"], "dimension": "power"},
        ],
        "assumptions": [{"text": "indoor use only"}],
    }
    payload.update(overrides)
    return payload


class JunkInputTests(unittest.TestCase):
    def test_non_json_string_is_empty_proposal_with_warning(self):
        result = parse_llm_proposal("I would build you a nice board!")
        self.assertFalse(result["ok"])
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["assumptions"], [])
        self.assertTrue(any("not a JSON object" in w for w in result["warnings"]))

    def test_non_dict_payload_is_rejected(self):
        for junk in (None, 42, ["list"], "[]"):
            with self.subTest(junk=junk):
                result = parse_llm_proposal(junk)
                self.assertFalse(result["ok"])
                self.assertEqual(result["questions"], [])

    def test_json_wrapped_in_prose_is_extracted(self):
        raw = "Here is my proposal:\n```json\n" + json.dumps(_proposal()) + "\n```\nThanks!"
        result = parse_llm_proposal(raw)
        self.assertEqual(len(result["questions"]), 1)
        self.assertEqual(result["questions"][0]["id"], "Q1")

    def test_broken_json_inside_prose_is_rejected(self):
        result = parse_llm_proposal("see: {questions: [oops}")
        self.assertFalse(result["ok"])
        self.assertEqual(result["questions"], [])

    def test_never_raises_on_any_garbage(self):
        # The boundary must be total: no input shape may raise.
        for junk in (object(), {"questions": {"nested": True}}, {"questions": [object()]},
                     {"questions": [{"question": 42}]}, {"assumptions": "nope"}):
            with self.subTest(junk=type(junk).__name__):
                parse_llm_proposal(junk)


class QuestionTests(unittest.TestCase):
    def test_well_formed_question_passes_through(self):
        result = parse_llm_proposal(_proposal())
        question = result["questions"][0]
        self.assertEqual(question["id"], "Q1")
        self.assertEqual(question["kind"], "blocking")
        self.assertEqual(question["options"], ["USB", "battery"])
        self.assertEqual(question["dimension"], "power")
        self.assertEqual(question["source"], "llm_proposal")

    def test_answer_is_always_unset_even_when_llm_supplies_one(self):
        # Core anti-hallucination property: answers come from humans only.
        payload = _proposal(questions=[
            {"id": "Q1", "question": "power source?", "kind": "blocking",
             "answer": "USB, definitely"},
        ])
        result = parse_llm_proposal(payload)
        self.assertIsNone(result["questions"][0]["answer"])

    def test_unknown_kind_escalates_to_blocking_never_down(self):
        payload = _proposal(questions=[{"id": "Q1", "question": "temp range?", "kind": "whatever"}])
        result = parse_llm_proposal(payload)
        self.assertEqual(result["questions"][0]["kind"], "blocking")
        self.assertTrue(any("escalated to blocking" in w for w in result["warnings"]))

    def test_question_without_text_is_skipped_with_warning(self):
        payload = _proposal(questions=[{"id": "Q1"}, {"id": "Q2", "question": "real?"}])
        result = parse_llm_proposal(payload)
        self.assertEqual([q["id"] for q in result["questions"]], ["Q2"])
        self.assertTrue(any("question[0]" in w for w in result["warnings"]))

    def test_missing_and_duplicate_ids_are_renamed(self):
        # Characterization: renaming picks Q{index+1}; the "_" suffix is only
        # appended when the auto-candidate itself collides with a taken id.
        # Case (a): duplicate "Q1" renames to the still-free "Q3", no suffix.
        payload = _proposal(questions=[
            {"question": "a?"},
            {"id": "Q1", "question": "b?"},
            {"id": "Q1", "question": "c?"},
        ])
        result = parse_llm_proposal(payload)
        ids = [q["id"] for q in result["questions"]]
        self.assertEqual(len(ids), len(set(ids)), ids)
        self.assertEqual(ids, ["Q1", "Q2", "Q3"])
        # Case (b): no-id after "Q2" collides on the auto-candidate -> "Q2_".
        payload = _proposal(questions=[
            {"id": "Q2", "question": "a?"},
            {"question": "b?"},
        ])
        result = parse_llm_proposal(payload)
        self.assertEqual([q["id"] for q in result["questions"]], ["Q2", "Q2_"])
        self.assertTrue(any("duplicate" in w or "renamed" in w for w in result["warnings"]))

    def test_malformed_options_become_none(self):
        payload = _proposal(questions=[
            {"id": "Q1", "question": "a?", "options": "yes,no"},
            {"id": "Q2", "question": "b?", "options": [1, 2]},
        ])
        result = parse_llm_proposal(payload)
        self.assertIsNone(result["questions"][0]["options"])
        self.assertIsNone(result["questions"][1]["options"])

    def test_non_string_dimension_falls_back_to_other(self):
        payload = _proposal(questions=[{"id": "Q1", "question": "a?", "dimension": 7}])
        self.assertEqual(parse_llm_proposal(payload)["questions"][0]["dimension"], "other")

    def test_questions_overflow_is_truncated_with_warning(self):
        payload = _proposal(questions=[
            {"id": f"Q{i}", "question": f"q{i}?"} for i in range(_MAX_QUESTIONS + 3)
        ])
        result = parse_llm_proposal(payload)
        self.assertEqual(len(result["questions"]), _MAX_QUESTIONS)
        self.assertTrue(any("truncated" in w for w in result["warnings"]))

    def test_questions_non_list_is_ignored_with_warning(self):
        result = parse_llm_proposal(_proposal(questions="how many?"))
        self.assertEqual(result["questions"], [])
        self.assertTrue(any("not a list" in w for w in result["warnings"]))


class AssumptionTests(unittest.TestCase):
    def test_assumptions_require_human_confirmation(self):
        result = parse_llm_proposal(_proposal(assumptions=[{"text": "indoor use"}]))
        assumption = result["assumptions"][0]
        self.assertTrue(assumption["requires_human_confirmation"])
        self.assertEqual(assumption["source"], "llm_proposal")
        self.assertEqual(assumption["id"], "A1")

    def test_junk_assumptions_are_skipped_with_warning(self):
        payload = _proposal(assumptions=[{"nope": 1}, "plain string", {"text": "  "}])
        result = parse_llm_proposal(payload)
        self.assertEqual(result["assumptions"], [])
        self.assertEqual(len(result["warnings"]), 3)

    def test_assumptions_non_list_is_ignored(self):
        result = parse_llm_proposal(_proposal(assumptions="none"))
        self.assertEqual(result["assumptions"], [])
        self.assertTrue(any("not a list" in w for w in result["warnings"]))


class CurrentBehaviorPins(unittest.TestCase):
    def test_ok_is_true_on_structured_parse_even_with_warnings(self):
        # PIN for human review (not an endorsement): the implementation returns
        # `{"ok": not warnings or True, ...}` - `or True` makes ok always True
        # on this path, warnings included. Dead logic; whether ok should stay
        # True (envelope parsed) or become False (junk skipped) is a human
        # call. Recorded in TASK-P7 progress log; do not silently change.
        payload = _proposal(questions=[{"id": "Q1"}, {"id": "Q2", "question": "real?"}])
        result = parse_llm_proposal(payload)
        self.assertTrue(result["ok"])
        self.assertTrue(result["warnings"])


if __name__ == "__main__":
    unittest.main()
