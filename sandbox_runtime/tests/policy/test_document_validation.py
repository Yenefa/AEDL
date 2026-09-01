"""Malformed / invalid normalized policy documents must fail closed.

A policy document that cannot be proven valid must never produce an engine
capable of returning ALLOW. ``from_document`` therefore raises
``PolicyDocumentError`` instead of falling back to a permissive default.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aedl_sandbox.policy import SandboxPolicyEngine
from aedl_sandbox.policy.errors import PolicyDocumentError

from . import fixtures as fx

REQUIRED_KEYS = (
    "schema_version",
    "domain_id",
    "board_id",
    "allowed_components",
    "pins",
    "parameters",
    "file_policy",
    "network_policy",
    "shell_policy",
    "tools",
    "compilers",
    "verifiers",
    "prerequisites",
    "available",
    "active_rules",
)


class MalformedDocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assertInvalid(self, document: object, label: str) -> None:
        with self.assertRaises(PolicyDocumentError, msg=f"expected fail-closed: {label}"):
            SandboxPolicyEngine.from_document(document, self.repo_root)  # type: ignore[arg-type]

    def assertValid(self, document: object, label: str) -> None:
        engine = SandboxPolicyEngine.from_document(document, self.repo_root)  # type: ignore[arg-type]
        self.assertIsInstance(engine, SandboxPolicyEngine, msg=label)

    def test_valid_baseline_document_is_accepted(self) -> None:
        self.assertValid(fx.complete_document(), "baseline synthetic document")

    def test_non_mapping_documents_are_rejected(self) -> None:
        for bad in ([], "not-a-document", None, 1, True):
            self.assertInvalid(bad, f"non-mapping document {bad!r}")

    def test_every_required_key_is_mandatory(self) -> None:
        for key in REQUIRED_KEYS:
            self.assertInvalid(fx.complete_document(**{key: fx.DELETE}), f"missing {key}")

    def test_unknown_top_level_key_is_rejected(self) -> None:
        self.assertInvalid(fx.complete_document(extra_key={}), "unknown top-level key")

    def test_unknown_rule_shapes_are_rejected(self) -> None:
        doc = fx.complete_document()
        doc["compilers"][0]["mystery_field"] = "x"
        self.assertInvalid(doc, "unknown key inside compiler record")

        doc = fx.complete_document()
        doc["pins"]["mystery_field"] = []
        self.assertInvalid(doc, "unknown key inside pin policy")

        doc = fx.complete_document()
        doc["prerequisites"]["mystery_field"] = []
        self.assertInvalid(doc, "unknown key inside prerequisites")

    def test_schema_version_must_be_exactly_one(self) -> None:
        for bad in (0, 2, "1", 1.0, True, None):
            self.assertInvalid(fx.complete_document(schema_version=bad), f"schema_version={bad!r}")

    def test_board_id_must_match_frozen_board(self) -> None:
        for bad in ("project-027-edd002", "PROJECT-027-EDD001", " project-027-edd001", "", None):
            self.assertInvalid(fx.complete_document(board_id=bad), f"board_id={bad!r}")

    def test_domain_id_must_match_frozen_domain(self) -> None:
        for bad in ("EDD-002", "edd-001", "EDD-001 ", None):
            self.assertInvalid(fx.complete_document(domain_id=bad), f"domain_id={bad!r}")

    def test_allowed_components_must_be_a_non_empty_list(self) -> None:
        for bad in ([], "TEST-RES-10K", None, {}):
            self.assertInvalid(fx.complete_document(allowed_components=bad), f"allowed_components={bad!r}")

    def test_component_record_shape_is_strict(self) -> None:
        for missing in ("mpn", "role", "required_evidence_ids"):
            doc = fx.complete_document()
            doc["allowed_components"][0].pop(missing)
            self.assertInvalid(doc, f"component record missing {missing}")

        doc = fx.complete_document()
        doc["allowed_components"][0]["manufacturer"] = "ACME"
        self.assertInvalid(doc, "component record with unknown key")

        doc = fx.complete_document()
        doc["allowed_components"][0]["required_evidence_ids"] = [1, 2]
        self.assertInvalid(doc, "component evidence ids must be strings")

        doc = fx.complete_document()
        doc["allowed_components"][0]["requires_resolution"] = "yes"
        self.assertInvalid(doc, "requires_resolution must be boolean")

    def test_duplicate_component_mpn_conflict_fails_closed(self) -> None:
        doc = fx.complete_document()
        doc["allowed_components"].append(
            {"mpn": "TEST-RES-10K", "role": "pulldown", "required_evidence_ids": []}
        )
        self.assertInvalid(doc, "same MPN declared twice with conflicting records")

    def test_duplicate_component_mpn_identical_records_are_tolerated(self) -> None:
        doc = fx.complete_document()
        doc["allowed_components"].append(dict(doc["allowed_components"][0]))
        self.assertValid(doc, "same MPN declared twice with identical records")

    def test_pin_class_overlap_fails_closed(self) -> None:
        pairs = (
            ("allowed", "hard_forbidden"),
            ("allowed", "core_reserved"),
            ("allowed", "soft_reserved"),
            ("core_reserved", "hard_forbidden"),
            ("core_reserved", "soft_reserved"),
            ("hard_forbidden", "soft_reserved"),
        )
        for left, right in pairs:
            doc = fx.complete_document()
            doc["pins"][right] = list(doc["pins"][right]) + [doc["pins"][left][0]]
            self.assertInvalid(doc, f"pin listed in both {left} and {right}")

    def test_pin_policy_shape_is_strict(self) -> None:
        for missing in ("allowed", "core_reserved", "hard_forbidden", "soft_reserved"):
            doc = fx.complete_document()
            doc["pins"].pop(missing)
            self.assertInvalid(doc, f"pin policy missing {missing}")

        doc = fx.complete_document()
        doc["pins"]["allowed"] = [1, 2]
        self.assertInvalid(doc, "pin identifiers must be strings")

        doc = fx.complete_document()
        doc["pins"]["allowed"] = ["GPIO1", "GPIO1"]
        self.assertInvalid(doc, "pin identifiers must be unique")

    def test_parameter_record_shape_is_strict(self) -> None:
        for missing in ("parameter_id", "value_type", "unit", "required_evidence_ids"):
            doc = fx.complete_document()
            doc["parameters"][0].pop(missing)
            self.assertInvalid(doc, f"parameter record missing {missing}")

        doc = fx.complete_document()
        doc["parameters"][0]["value_type"] = "complex"
        self.assertInvalid(doc, "value_type outside enum")

        doc = fx.complete_document()
        doc["parameters"][0]["mystery"] = 1
        self.assertInvalid(doc, "parameter record with unknown key")

    def test_duplicate_parameter_id_conflict_fails_closed(self) -> None:
        doc = fx.complete_document()
        doc["parameters"].append(
            {
                "parameter_id": "TEST_PULLUP_OHM",
                "value_type": "number",
                "unit": "volt",
                "allowed_values": [3.3],
                "required_evidence_ids": [],
            }
        )
        self.assertInvalid(doc, "same parameter_id declared twice with conflicting records")

    def test_duplicate_tool_identity_conflict_fails_closed(self) -> None:
        doc = fx.complete_document()
        doc["tools"].append(
            {"tool_id": "kicad-cli", "tool_version": "8.0.0", "capability": "gerber_export"}
        )
        self.assertInvalid(doc, "same tool id/version with conflicting capability")

    def test_duplicate_compiler_identity_conflict_fails_closed(self) -> None:
        doc = fx.complete_document()
        doc["compilers"].append(
            {
                "compiler_id": "hir-to-kicad",
                "compiler_version": "1.0.0",
                "output_kind": "kicad_sch",
                "required_coverage_ids": ["ERC"],
            }
        )
        self.assertInvalid(doc, "same compiler id/version/output with conflicting coverage")

    def test_duplicate_verifier_identity_conflict_fails_closed(self) -> None:
        doc = fx.complete_document()
        doc["verifiers"].append(
            {
                "verifier_id": "kicad-audit",
                "verifier_version": "1.0.0",
                "artifact_kind": "kicad_sch",
                "coverage_ids": ["ERC"],
            }
        )
        self.assertInvalid(doc, "same verifier id/version/artifact with conflicting coverage")

    def test_file_policy_constants_are_frozen(self) -> None:
        self.assertInvalid(fx.complete_document(file_policy={}), "empty file policy")

        doc = fx.complete_document()
        doc["file_policy"]["candidate_root_only"] = False
        self.assertInvalid(doc, "candidate_root_only must stay true")

        doc = fx.complete_document()
        doc["file_policy"]["direct_kicad_write"] = True
        self.assertInvalid(doc, "direct_kicad_write must stay false")

    def test_network_policy_must_remain_offline(self) -> None:
        self.assertInvalid(
            fx.complete_document(network_policy={"runtime_access": True}),
            "runtime network access must not be expressible",
        )
        self.assertInvalid(fx.complete_document(network_policy={}), "empty network policy")

    def test_shell_policy_must_remain_disabled(self) -> None:
        self.assertInvalid(
            fx.complete_document(shell_policy={"arbitrary_shell": True}),
            "arbitrary shell must not be expressible",
        )
        self.assertInvalid(fx.complete_document(shell_policy={}), "empty shell policy")

    def test_prerequisites_and_available_shape_are_strict(self) -> None:
        for key in ("required_contract_ids", "required_evidence_ids", "required_component_resolutions"):
            doc = fx.complete_document()
            doc["prerequisites"].pop(key)
            self.assertInvalid(doc, f"prerequisites missing {key}")

        for key in ("contract_ids", "evidence_ids"):
            doc = fx.complete_document()
            doc["available"].pop(key)
            self.assertInvalid(doc, f"available missing {key}")

    def test_active_rule_shape_is_strict(self) -> None:
        doc = fx.complete_document()
        doc["active_rules"][0].pop("fingerprint")
        self.assertInvalid(doc, "active rule missing fingerprint")

        doc = fx.complete_document()
        doc["active_rules"][0]["extra"] = 1
        self.assertInvalid(doc, "active rule with unknown key")

        self.assertInvalid(fx.complete_document(active_rules={}), "active_rules must be a list")

    def test_duplicate_authoritative_rule_conflict_fails_closed(self) -> None:
        doc = fx.complete_document()
        doc["active_rules"].append(
            {
                "rule_id": "PIN_PSRAM_HARD_FORBIDDEN",
                "source_contract_id": "another_contract.json",
                "kind": "pin_constraint",
                "fingerprint": "a" * 64,
            }
        )
        self.assertInvalid(doc, "same rule id with conflicting fingerprint")

    def test_duplicate_authoritative_rule_identical_fingerprint_is_tolerated(self) -> None:
        doc = fx.complete_document()
        doc["active_rules"].append(dict(doc["active_rules"][0]))
        self.assertValid(doc, "same rule id with identical fingerprint")


if __name__ == "__main__":
    unittest.main()
