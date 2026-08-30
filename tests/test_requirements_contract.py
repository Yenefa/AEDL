"""F1-F8 fixtures for the requirements contract gate (Phase 1 CircuitBot intake).

Each fixture is a deliberate inversion of a CircuitBot clarify failure mode
(notes/open_source_intake/circuitbot.md STEP 3/5/6). The fixtures run in
temp directories so no repo file is mutated by the suite.
"""

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gates.requirements_contract import (
    INTENT_SEMANTIC_FIELDS,
    compute_contract_sha256,
    intent_semantic_sha256,
    requirements_contract_gate_verdict,
    validate_requirements_contract,
)
from gates.requirements_runtime import (
    build_proposal_prompt,
    draft_contract,
    parse_llm_proposal,
    write_contract,
)

NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=timezone.utc)

GOOD_INTENT = {
    "protocol_version": 1,
    "components": {
        "U1": {"lib_id": "RF_Module:ESP32-C3", "value": "ESP32-C3"},
        "R1": {"lib_id": "Device:R", "value": "10k"},
    },
    "nets": {"+3V3": ["U1.1", "R1.1"], "GND": ["U1.9"]},
}


def _good_contract():
    return {
        "$schema": "https://aedl.local/schemas/requirements-contract.v1.json",
        "schema_version": 1,
        "board_id": "unit-test-board",
        "created_at": (NOW - timedelta(hours=1)).isoformat(),
        "author": "human+ai",
        "user_goal": "USB-C powered ESP32-C3 sensor board",
        "source_statements": [
            {"id": "S1", "text": "USB-C 供电", "type": "power"},
            {"id": "S2", "text": "ESP32-C3", "type": "mcu"},
        ],
        "resolved_requirements": [
            {"id": "R1", "text": "USB-C 5V input", "source_ids": ["S1"]},
        ],
        "open_questions": [
            {"id": "Q1", "question": "需要板载调试器吗？", "answer": "不需要",
             "kind": "blocking", "source_ids": ["S1"]},
            {"id": "Q2", "question": "工作温度范围？", "answer": "No preference",
             "kind": "nonblocking", "source_ids": []},
        ],
        "assumptions": [
            {"id": "A1", "text": "民用温度范围 0-50C", "source_ids": [], "status": "recorded"},
        ],
        "forbidden_assumptions": ["no display"],
        "intent_binding": {
            "intent_path": "intent.json",
            "intent_semantic_sha256": intent_semantic_sha256(GOOD_INTENT),
        },
    }


class _Sandbox:
    """Temp repo layout: contract + intent side by side."""

    def __init__(self, contract, intent):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.intent_path = self.root / "intent.json"
        self.contract_path = self.root / "contract.json"
        self.set_intent(copy.deepcopy(intent))
        self.set_contract(copy.deepcopy(contract))

    def set_intent(self, intent):
        self.intent_path.write_text(json.dumps(intent, ensure_ascii=False), encoding="utf-8")
        return self.intent_path

    def set_contract(self, contract):
        contract_path = self.root / "contract.json"
        contract_path.write_text(
            json.dumps(contract, ensure_ascii=False), encoding="utf-8"
        )
        self.contract_path = contract_path

    def validate(self):
        return validate_requirements_contract(self.contract_path, self.intent_path, now=NOW)

    def close(self):
        self._tmp.cleanup()


class RequirementsContractGateTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = _Sandbox(_good_contract(), GOOD_INTENT)
        self.addCleanup(self.sandbox.close)

    def _signed(self, mutate=None):
        contract = _good_contract()
        if mutate:
            mutate(contract)
        contract["contract_sha256"] = compute_contract_sha256(contract)
        return contract

    def _bound_intent(self, contract):
        """GOOD_INTENT carrying a valid lockfile reference to `contract`."""
        intent = copy.deepcopy(GOOD_INTENT)
        intent["requirements_contract"] = {
            "sha256": contract["contract_sha256"], "path": "contract.json",
        }
        return intent

    def _install(self, contract=None, intent=None):
        """Write a consistent, gate-green (contract, intent) pair to the sandbox."""
        contract = self._signed() if contract is None else contract
        intent = self._bound_intent(contract) if intent is None else intent
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        return contract, intent

    def test_f7_valid_contract_passes(self):
        self.sandbox.set_contract(self._signed())
        # intent must reference the signed hash
        intent = copy.deepcopy(GOOD_INTENT)
        intent["requirements_contract"] = {
            "sha256": compute_contract_sha256(
                {k: v for k, v in self._signed().items()}
            ),
            "path": "contract.json",
        }
        self.sandbox.set_intent(intent)
        errors = self.sandbox.validate()
        self.assertEqual(errors, [])

    def test_f1_unanswered_blocking_question_fails(self):
        def mutate(contract):
            contract["open_questions"][0]["answer"] = ""
        contract = self._signed(mutate)
        self.sandbox.set_contract(contract)
        errors = self.sandbox.validate()
        self.assertTrue(any("unanswered" in e for e in errors), errors)

    def test_f1b_explicit_unknown_is_a_valid_answer(self):
        def mutate(contract):
            contract["open_questions"][0]["answer"] = "unknown"
        contract = self._signed(mutate)
        intent = copy.deepcopy(GOOD_INTENT)
        intent["requirements_contract"] = {
            "sha256": contract["contract_sha256"], "path": "contract.json",
        }
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        errors = self.sandbox.validate()
        self.assertFalse(any("unanswered" in e for e in errors), errors)

    def test_f1c_timeout_style_proceed_is_impossible(self):
        """CircuitBot proceeds after 5 minutes without answers; there is no
        code path here that can produce a pass with a missing answer because
        the validator only sees files, never a timeout."""
        contract = self._signed()
        # simulate "answers never arrived": strip every answer
        for question in contract["open_questions"]:
            question["answer"] = None if question["kind"] == "nonblocking" else None
        contract["open_questions"][0]["answer"] = None
        contract["contract_sha256"] = compute_contract_sha256(contract)
        self.sandbox.set_contract(contract)
        errors = self.sandbox.validate()
        self.assertTrue(any("unanswered" in e for e in errors), errors)

    def test_f2_no_preference_is_recorded_not_dropped(self):
        contract = self._signed()
        intent = copy.deepcopy(GOOD_INTENT)
        intent["requirements_contract"] = {
            "sha256": contract["contract_sha256"], "path": "contract.json",
        }
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        errors = self.sandbox.validate()
        # The nonblocking "No preference" answer must not be an error and must
        # still be present in the artifact (CircuitBot drops it silently).
        self.assertFalse(any("No preference" in e for e in errors), errors)
        on_disk = json.loads(self.sandbox.contract_path.read_text(encoding="utf-8"))
        answers = [q["answer"] for q in on_disk["open_questions"]]
        self.assertIn("No preference", answers)

    def test_f3_tampered_contract_hash_mismatch(self):
        contract = self._signed()
        contract["user_goal"] = "tampered after signing"
        self.sandbox.set_contract(contract)  # hash now stale
        errors = self.sandbox.validate()
        self.assertTrue(any("contract_sha256 mismatch" in e for e in errors), errors)

    def test_f3b_intent_referencing_old_contract_revision(self):
        contract = self._signed()
        intent = copy.deepcopy(GOOD_INTENT)
        intent["requirements_contract"] = {
            "sha256": "0" * 64, "path": "contract.json",
        }
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        errors = self.sandbox.validate()
        self.assertTrue(
            any("does not match this contract" in e for e in errors), errors
        )

    def test_f4_missing_forbidden_field_fails(self):
        def mutate(contract):
            del contract["forbidden_assumptions"]
        contract = self._signed(mutate)
        intent = copy.deepcopy(GOOD_INTENT)
        intent["requirements_contract"] = {
            "sha256": contract["contract_sha256"], "path": "contract.json",
        }
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        errors = self.sandbox.validate()
        self.assertTrue(any("missing fields" in e for e in errors), errors)

    def test_f5_forbidden_keyword_surfacing_in_intent(self):
        contract = self._signed(
            mutate=lambda c: c.__setitem__("forbidden_assumptions", ["no wireless"])
        )
        intent = copy.deepcopy(GOOD_INTENT)
        intent["requirements_contract"] = {
            "sha256": contract["contract_sha256"], "path": "contract.json",
        }
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        errors = self.sandbox.validate()
        self.assertTrue(any("forbidden assumption" in e for e in errors), errors)

    def test_f6_stale_contract_fails(self):
        def mutate(contract):
            contract["created_at"] = (NOW - timedelta(days=30)).isoformat()
        contract = self._signed(mutate)
        intent = copy.deepcopy(GOOD_INTENT)
        intent["requirements_contract"] = {
            "sha256": contract["contract_sha256"], "path": "contract.json",
        }
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        errors = self.sandbox.validate()
        self.assertTrue(any("stale" in e for e in errors), errors)

    def test_f8_corrupt_json_fails_safe(self):
        self.sandbox.contract_path.write_text("{ not json", encoding="utf-8")
        errors = self.sandbox.validate()
        self.assertTrue(any("unreadable" in e for e in errors), errors)

    def test_gate_verdict_shape(self):
        verdict = requirements_contract_gate_verdict(
            self.sandbox.contract_path, self.sandbox.intent_path, now=NOW
        )
        self.assertIn(verdict["status"], ("pass", "fail"))
        self.assertIsInstance(verdict["errors"], list)


class IntentSemanticBindingTests(unittest.TestCase):
    """C4 semantic lock: the contract is signed against a CIRCUIT, not a path.

    These cover the gap that motivated the semantic binding: with the lockfile
    binding alone, editing `components` (swap a part, add a part) while leaving
    the old contract reference in place still PASSES, so the contract claims to
    describe a board it has never seen.
    """

    def setUp(self):
        self.sandbox = _Sandbox(_good_contract(), GOOD_INTENT)
        self.addCleanup(self.sandbox.close)

    def _signed(self):
        contract = _good_contract()
        contract["contract_sha256"] = compute_contract_sha256(contract)
        return contract

    @staticmethod
    def _bound_intent(contract):
        intent = copy.deepcopy(GOOD_INTENT)
        intent["requirements_contract"] = {
            "sha256": contract["contract_sha256"], "path": "contract.json",
        }
        return intent

    # --- the core gap -----------------------------------------------------

    def test_c4_component_value_change_requires_resign(self):
        """换料（改 U1 value）不重签合同 -> FAIL。"""
        contract = self._signed()
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(self._bound_intent(contract))
        self.assertEqual(self.sandbox.validate(), [])  # baseline green

        intent = self._bound_intent(contract)
        intent["components"]["U1"]["value"] = "ESP32-C3-WROOM-02-N4"
        self.sandbox.set_intent(intent)

        errors = self.sandbox.validate()
        self.assertTrue(any("intent 语义内容已变更" in e for e in errors), errors)

    def test_c4_adding_a_component_requires_resign(self):
        """塞一个 U9 电阻不重签合同 -> FAIL（本次实测到的具体缺口）。"""
        contract = self._signed()
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(self._bound_intent(contract))

        intent = self._bound_intent(contract)
        intent["components"]["U9"] = {"lib_id": "Device:R", "value": "10k"}
        self.sandbox.set_intent(intent)

        errors = self.sandbox.validate()
        self.assertTrue(any("intent 语义内容已变更" in e for e in errors), errors)

    def test_c4_removing_a_component_requires_resign(self):
        contract = self._signed()
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(self._bound_intent(contract))

        intent = self._bound_intent(contract)
        del intent["components"]["R1"]
        self.sandbox.set_intent(intent)

        errors = self.sandbox.validate()
        self.assertTrue(any("intent 语义内容已变更" in e for e in errors), errors)

    def test_c4_net_change_requires_resign(self):
        """改 nets（连接关系）同样属于语义变更 -> FAIL。"""
        contract = self._signed()
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(self._bound_intent(contract))

        intent = self._bound_intent(contract)
        intent["nets"]["+3V3"] = ["U1.1"]
        self.sandbox.set_intent(intent)

        errors = self.sandbox.validate()
        self.assertTrue(any("intent 语义内容已变更" in e for e in errors), errors)

    def test_c4_resigning_after_semantic_change_is_green_again(self):
        """语义变更后重签合同 -> 恢复 PASS（重签路径必须真的通）。

        注意顺序：语义哈希取自"改过之后的 intent"，且落盘的 intent 必须是同一份
        改过的内容——否则等于用一个电路的哈希去签另一个电路。
        """
        intent = copy.deepcopy(GOOD_INTENT)
        intent["components"]["U9"] = {"lib_id": "Device:R", "value": "10k"}

        contract = self._signed()
        contract["intent_binding"]["intent_semantic_sha256"] = intent_semantic_sha256(intent)
        contract["contract_sha256"] = compute_contract_sha256(contract)

        intent["requirements_contract"] = {
            "sha256": contract["contract_sha256"], "path": "contract.json",
        }
        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        self.assertEqual(self.sandbox.validate(), [])

    # --- the other half: what must NOT invalidate -------------------------

    def test_c4_metadata_change_does_not_require_resign(self):
        """protocol_version 是元数据，改它不该让合同失效。"""
        contract = self._signed()
        intent = self._bound_intent(contract)
        intent["protocol_version"] = 99

        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        self.assertEqual(self.sandbox.validate(), [])

    def test_c4_binding_field_is_excluded_from_semantic_hash(self):
        """绑定字段本身不算进语义哈希。

        故意把 intent 的 requirements_contract 指错：应当只触发 lockfile 错误
        （"does not match this contract"），而不是语义错误。若语义哈希覆盖了绑定
        字段，这里会同时冒出"语义内容已变更"，那就会形成循环依赖。
        """
        contract = self._signed()
        intent = self._bound_intent(contract)
        intent["requirements_contract"] = {"sha256": "0" * 64, "path": "contract.json"}

        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(intent)
        errors = self.sandbox.validate()

        self.assertTrue(any("does not match this contract" in e for e in errors), errors)
        self.assertFalse(any("intent 语义内容已变更" in e for e in errors), errors)

    def test_semantic_hash_ignores_non_whitelisted_fields(self):
        base = intent_semantic_sha256(GOOD_INTENT)

        variant = copy.deepcopy(GOOD_INTENT)
        variant["requirements_contract"] = {"sha256": "f" * 64, "path": "other.json"}
        self.assertEqual(intent_semantic_sha256(variant), base)

        variant = copy.deepcopy(GOOD_INTENT)
        variant["protocol_version"] = 42
        self.assertEqual(intent_semantic_sha256(variant), base)

        variant = copy.deepcopy(GOOD_INTENT)
        variant["some_future_metadata"] = {"anything": True}
        self.assertEqual(intent_semantic_sha256(variant), base)

    def test_semantic_hash_is_deterministic_and_order_independent(self):
        a = intent_semantic_sha256(GOOD_INTENT)
        b = intent_semantic_sha256(copy.deepcopy(GOOD_INTENT))
        self.assertEqual(a, b)
        self.assertRegex(a, r"^[0-9a-f]{64}$")

        # Key insertion order must not matter (canonical JSON sorts keys).
        shuffled = {
            "nets": GOOD_INTENT["nets"],
            "protocol_version": GOOD_INTENT["protocol_version"],
            "components": GOOD_INTENT["components"],
        }
        self.assertEqual(intent_semantic_sha256(shuffled), a)

    def test_semantic_hash_covers_exactly_the_whitelist(self):
        self.assertEqual(set(INTENT_SEMANTIC_FIELDS), {"components", "nets"})

        for field in INTENT_SEMANTIC_FIELDS:
            variant = copy.deepcopy(GOOD_INTENT)
            variant[field] = {"deliberately": "different"}
            self.assertNotEqual(intent_semantic_sha256(variant),
                                intent_semantic_sha256(GOOD_INTENT))

    def test_missing_semantic_field_is_distinct_not_skipped(self):
        """字段缺失按 null 参与哈希，而不是被跳过——破损 intent 不该和正常的一样。"""
        broken = copy.deepcopy(GOOD_INTENT)
        del broken["components"]
        self.assertNotEqual(intent_semantic_sha256(broken),
                            intent_semantic_sha256(GOOD_INTENT))

    def test_binding_missing_semantic_hash_is_malformed(self):
        contract = self._signed()
        del contract["intent_binding"]["intent_semantic_sha256"]
        contract["contract_sha256"] = compute_contract_sha256(contract)

        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(self._bound_intent(contract))
        errors = self.sandbox.validate()
        self.assertTrue(any("intent_semantic_sha256 is malformed" in e for e in errors), errors)

    def test_binding_with_old_shape_is_rejected(self):
        """旧的 {"intent_path"} 单字段形状必须被拒，不能静默放过。"""
        contract = self._signed()
        contract["intent_binding"] = {"intent_path": "intent.json"}
        contract["contract_sha256"] = compute_contract_sha256(contract)

        self.sandbox.set_contract(contract)
        self.sandbox.set_intent(self._bound_intent(contract))
        errors = self.sandbox.validate()
        self.assertTrue(any("intent_binding must contain exactly" in e for e in errors), errors)


class RequirementsRuntimeTests(unittest.TestCase):
    """Layer A (advisory) must never fabricate answers or survive as structure."""

    def test_parse_llm_proposal_clean(self):
        raw = {
            "questions": [
                {"id": "Q1", "question": "供电方式？", "kind": "blocking",
                 "dimension": "power", "options": ["USB-C", "电池"]},
            ],
            "assumptions": [{"text": "两层板"}],
        }
        result = parse_llm_proposal(raw)
        self.assertEqual(len(result["questions"]), 1)
        question = result["questions"][0]
        self.assertEqual(question["answer"], None)
        self.assertEqual(question["source"], "llm_proposal")
        self.assertEqual(len(result["assumptions"]), 1)
        self.assertEqual(result["assumptions"][0]["requires_human_confirmation"], True)

    def test_parse_llm_proposal_garbage_is_warning_not_exception(self):
        for junk in (None, 42, "plain text", "{'broken'", [], {"questions": "oops"}):
            result = parse_llm_proposal(junk)
            self.assertIsInstance(result, dict)
            self.assertIsInstance(result["questions"], list)
            for question in result["questions"]:
                self.assertIsNone(question["answer"])

    def test_unknown_kind_escalates_to_blocking(self):
        result = parse_llm_proposal(
            {"questions": [{"question": "x", "kind": "whatever"}]}
        )
        self.assertEqual(result["questions"][0]["kind"], "blocking")

    def test_more_than_five_questions_truncated(self):
        raw = {"questions": [{"question": f"q{i}"} for i in range(9)]}
        result = parse_llm_proposal(raw)
        self.assertEqual(len(result["questions"]), 5)
        self.assertTrue(result["warnings"])

    def test_prompt_template_contains_request(self):
        prompt = build_proposal_prompt("做一个 USB 供电的温度计")
        self.assertIn("做一个 USB 供电的温度计", prompt)
        self.assertIn("blocking", prompt)

    def test_draft_contract_produces_gate_valid_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            intent_path = root / "intent.json"
            intent_path.write_text(
                json.dumps(GOOD_INTENT, ensure_ascii=False), encoding="utf-8"
            )
            contract = draft_contract(
                user_goal="USB-C powered ESP32-C3 sensor board",
                statements=[
                    {"id": "S1", "text": "USB-C 供电", "type": "power"},
                    {"id": "S2", "text": "ESP32-C3", "type": "mcu"},
                ],
                resolved_requirements=[
                    {"id": "R1", "text": "USB-C 5V input", "source_ids": ["S1"]},
                ],
                questions=[
                    {"id": "Q1", "question": "需要板载调试器吗？", "answer": "不需要",
                     "kind": "blocking", "source_ids": ["S1"]},
                ],
                assumptions=[
                    {"id": "A1", "text": "民用温度范围", "source_ids": [], "status": "recorded"},
                ],
                forbidden_assumptions=["no display"],
                board_id="unit-test-board",
                author="human+ai",
                created_at=(NOW - timedelta(hours=1)).isoformat(),
                intent_path="intent.json",
                intent_semantic_sha256=intent_semantic_sha256(GOOD_INTENT),
            )
            write_contract(contract, root / "contract.json")
            # intent must carry the reference (single-direction binding)
            intent = copy.deepcopy(GOOD_INTENT)
            intent["requirements_contract"] = {
                "sha256": contract["contract_sha256"], "path": "contract.json",
            }
            intent_path.write_text(
                json.dumps(intent, ensure_ascii=False), encoding="utf-8"
            )
            errors = validate_requirements_contract(
                root / "contract.json", intent_path, now=NOW
            )
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
