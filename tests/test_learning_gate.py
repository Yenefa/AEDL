import copy
import json
from pathlib import Path
import tempfile
import unittest

from gates.learning_gate import validate_lessons_registry
from gates.semantic_fault_injection import generate_fault_injection_report


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "gates" / "lessons_registry_v1.json"
CONTRACT = ROOT / "gates" / "contracts" / "m2_schematic_contract_v1.json"
FIXTURES = ROOT / "tests" / "fixtures" / "schematic_semantics"


class LearningGateTests(unittest.TestCase):
    def test_fault_injection_runner_catches_all_five_reproductions(self):
        report = generate_fault_injection_report(
            CONTRACT,
            FIXTURES / "good_observations.json",
            sorted(FIXTURES.glob("fault_*.json")),
            root=ROOT,
        )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"], {"caught": 5, "missed": 0, "total": 5})
        self.assertTrue(all(case["status"] == "caught" for case in report["cases"]))

    def test_current_critical_lesson_registry_is_valid(self):
        self.assertEqual(validate_lessons_registry(REGISTRY, ROOT), [])

    def test_critical_lesson_missing_required_field_fails_closed(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        del registry["lessons"][0]["root_cause"]
        errors = self._validate_temporary(registry)
        self.assertTrue(any("missing fields" in error and "root_cause" in error for error in errors))

    def test_unknown_severity_fails_closed(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        registry["lessons"][0]["severity"] = "important-ish"
        errors = self._validate_temporary(registry)
        self.assertTrue(any("unknown severity" in error for error in errors))

    def test_missing_referenced_artifact_fails_closed(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        registry["lessons"][0]["failure_evidence"] = ["notes/does-not-exist.json"]
        errors = self._validate_temporary(registry)
        self.assertTrue(any("referenced artifact does not exist" in error for error in errors))

    def test_tampered_fault_injection_proof_fails_closed(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        proof_path = ROOT / registry["lessons"][0]["fault_injection_proof"]
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        proof["cases"][0]["detected_rules"] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            temporary_proof = Path(temp_dir) / "proof.json"
            temporary_proof.write_text(json.dumps(proof), encoding="utf-8")
            errors = validate_lessons_registry(REGISTRY, ROOT, proof_override=temporary_proof)
        self.assertTrue(any("does not prove expected rule" in error for error in errors))

    def _validate_temporary(self, registry):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "registry.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            return validate_lessons_registry(path, ROOT)


if __name__ == "__main__":
    unittest.main()
