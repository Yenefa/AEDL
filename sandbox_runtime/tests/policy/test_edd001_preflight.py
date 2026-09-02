"""Real EDD-001 contract bundle: preflight, supersession and order invariance.

These tests read the actual frozen contracts in ``gates/contracts/``. They are
the ones that must keep the real domain honestly BLOCKED while synthetic
TEST_ONLY documents prove the ALLOW paths.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aedl_sandbox.protocol import Outcome
from aedl_sandbox.policy import SandboxPolicyEngine
from aedl_sandbox.policy.errors import PolicyDocumentError

from . import fixtures as fx

REPO_ROOT = Path(__file__).resolve().parents[3]

# V2 (Wave 3, frozen by Agent H): notes/edd001-sandbox/agent-h-handoff.md §-2.0.
# The V1 value f053aae2… is retired; re-pinning is the expected post-freeze drift.
FROZEN_PROTOCOL_SHA256 = (
    "f7d44732785d17a20283f3a18fde7689eebfee78f10a93ae899e1dd116383cad"
)

REAL_BUNDLE_MANIFEST = (
    REPO_ROOT / "src" / "hardware" / "edd001-board" / "evidence" / "sandbox_bundle_manifest_v1.json"
)

CONTRACT_FILENAMES = (
    "edd001_core_base_contract_v1.json",
    "edd001_pin_constraints_v1.json",
    "edd001_usb_contract_v1.json",
)

EXPECTED_SUPERSEDED_RULE_IDS = {
    "PIN_STRAP_GPIO0",
    "PIN_STRAP_GPIO3",
    "PIN_STRAP_GPIO45",
    "PIN_STRAP_GPIO46",
    "EN_RESET_NETWORK",
    "BOOT_BUTTON_GPIO0",
    "POWER_3V3_DECOUPLING",
    "ANTENNA_KEEPOUT",
}

EXPECTED_ACTIVE_PIN_RULE_IDS = {"USB_DIFFERENTIAL", "POWER_SOURCE_SEPARATION"}


def read_contract(name: str) -> dict[str, Any]:
    document = json.loads((REPO_ROOT / "gates" / "contracts" / name).read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def make_evidence_dir(datasheets: Path, evidence_id: str) -> None:
    """Create a locally verifiable evidence directory: non-empty and holding
    at least one file with size > 0."""
    target = datasheets / evidence_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "datasheet.md").write_text("frozen local snapshot\n", encoding="utf-8")


def load_real_contracts() -> list[tuple[str, dict[str, Any]]]:
    return [(name, read_contract(name)) for name in CONTRACT_FILENAMES]


class FrozenProtocolTests(unittest.TestCase):
    def test_protocol_sha256_matches_the_frozen_value(self) -> None:
        path = REPO_ROOT / "sandbox_runtime" / "src" / "aedl_sandbox" / "protocol.py"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(digest, FROZEN_PROTOCOL_SHA256)


class RealEdd001PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SandboxPolicyEngine.for_edd001(REPO_ROOT)
        self.candidate_root = REPO_ROOT / "sandbox_runtime" / ".runs" / "agent-m-preflight"

    def test_real_preflight_is_blocked(self) -> None:
        decision = self.engine.preflight("run-edd001-real", self.candidate_root)
        fx.assert_sorted_findings(self, decision)
        self.assertEqual(decision.outcome, Outcome.BLOCKED)

    def test_real_preflight_reports_every_required_finding_code(self) -> None:
        decision = self.engine.preflight("run-edd001-real", self.candidate_root)
        present = fx.codes(decision)
        for code in (
            "EVIDENCE_REQUIRED_CONTRACT_MISSING",
            "EVIDENCE_COMPONENT_SOURCE_MISSING",
            "POLICY_COMPILER_NOT_REGISTERED",
            "POLICY_VERIFIER_COVERAGE_MISSING",
        ):
            self.assertIn(code, present, msg=f"missing finding code {code}")

    def test_missing_power_contract_is_reported(self) -> None:
        decision = self.engine.preflight("run-edd001-real", self.candidate_root)
        power = [f for f in decision.findings if f.code == "EVIDENCE_REQUIRED_CONTRACT_MISSING"]
        self.assertEqual(len(power), 1)
        self.assertEqual(power[0].details["contract_id"], "EDD-001.POWER")
        self.assertEqual(power[0].source, "contract_bundle")

    def test_every_allowed_component_lacks_local_datasheet_evidence(self) -> None:
        decision = self.engine.preflight("run-edd001-real", self.candidate_root)
        component_findings = [
            f for f in decision.findings if f.code == "EVIDENCE_COMPONENT_SOURCE_MISSING"
        ]
        self.assertTrue(component_findings, "expected component evidence findings")
        for finding in component_findings:
            self.assertTrue(finding.details["missing_evidence_ids"], msg=str(finding.details))
        mpns = sorted(str(f.details["mpn"]) for f in component_findings)
        self.assertEqual(
            mpns,
            [
                "AP63203WU-7",
                "ESP32-S3-WROOM-1-N8R8",
                "SS34",
                "TYPE-C-31-M-12",
                "USBLC6-2SC6",
            ],
        )

    def test_nested_and_direct_power_parts_are_both_required(self) -> None:
        """GH-20 Tasks 6-7: both power-path parts must be collected.

        ``USB_VBUS_REVERSE_PROTECTION`` declares SS34 directly under its
        constraint; ``POWER_SOURCE_SEPARATION`` declares AP63203WU-7 nested
        inside ``constraint.regulator_3v3.device``. Collection must be
        recursive so the real preflight reports BOTH — dropping either
        declaration is a regression against the frozen-contract adjudication.
        """
        document = self.engine.document
        self.assertEqual(document.components["SS34"].role, "USB_VBUS_REVERSE_PROTECTION")
        self.assertEqual(
            document.components["SS34"].required_evidence_ids,
            ("ESPRESSIF_S3_LCD_EV_BOARD",),
        )
        self.assertEqual(document.components["AP63203WU-7"].role, "POWER_SOURCE_SEPARATION")
        self.assertEqual(
            document.components["AP63203WU-7"].required_evidence_ids,
            ("ESP32_S3_TECHPEDIA",),
        )
        decision = self.engine.preflight("run-edd001-real", self.candidate_root)
        reported = {
            str(f.details["mpn"])
            for f in decision.findings
            if f.code == "EVIDENCE_COMPONENT_SOURCE_MISSING"
        }
        self.assertIn("SS34", reported)
        self.assertIn("AP63203WU-7", reported)

    def test_source_urls_are_not_treated_as_local_evidence(self) -> None:
        document = self.engine.document
        self.assertEqual(document.available_evidence_ids, frozenset())
        for mpn, record in document.components.items():
            self.assertTrue(record.required_evidence_ids, msg=f"{mpn} declares no evidence")

    def test_preflight_is_deterministic(self) -> None:
        first = self.engine.preflight("run-edd001-real", self.candidate_root)
        second = self.engine.preflight("run-edd001-real", self.candidate_root)
        self.assertEqual(first, second)

    def test_no_action_is_allowed_on_the_real_bundle(self) -> None:
        """The real bundle is incomplete, so nothing may return ALLOW."""
        probes = [
            ("DESIGN_ASSIGN_PIN", {"pin": "GPIO1", "function": "LED", "approval_status": "NOT_REQUIRED"}),
            ("DESIGN_ASSIGN_PIN", {"pin": "GPIO2", "function": "LED", "approval_status": "NOT_REQUIRED"}),
            (
                "DESIGN_SELECT_COMPONENT",
                {"mpn": "ESP32-S3-WROOM-1-N8R8", "role": "mcu_module", "evidence_ids": ["WROOM1_DATASHEET"]},
            ),
        ]
        for action, subject in probes:
            decision = self.engine.evaluate(
                fx.request(action, subject, candidate_root=self.candidate_root)
            )
            self.assertNotEqual(decision.outcome, Outcome.ALLOW, msg=f"{action} must not be allowed")
            self.assertEqual(decision.outcome, Outcome.BLOCKED, msg=action)

    def test_violations_still_deny_on_the_real_bundle(self) -> None:
        decision = self.engine.evaluate(
            fx.request(
                "DESIGN_ASSIGN_PIN",
                {"pin": "GPIO35", "function": "LED", "approval_status": "NOT_REQUIRED"},
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_PIN_HARD_FORBIDDEN")

        decision = self.engine.evaluate(
            fx.request(
                "NETWORK_ACCESS",
                {"destination": "espressif.com", "purpose": "datasheet"},
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_NETWORK_DISABLED")

    def test_preflight_outside_the_repository_is_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            decision = self.engine.preflight("run-edd001-real", Path(tmp))
            self.assertEqual(decision.outcome, Outcome.DENY)
            self.assertEqual(decision.reason_code, "POLICY_PATH_ESCAPE")


class RealEdd001PinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SandboxPolicyEngine.for_edd001(REPO_ROOT)
        self.candidate_root = REPO_ROOT / "sandbox_runtime" / ".runs" / "agent-m-preflight"
        self.pins = self.engine.document.pins

    def test_agent_gpio_pool_matches_core_base(self) -> None:
        core_base = read_contract("edd001_core_base_contract_v1.json")
        self.assertEqual(set(self.pins.allowed), set(core_base["pin_policy"]["agent_gpio_pool"]))

    def test_hard_forbidden_pins(self) -> None:
        self.assertEqual(self.pins.hard_forbidden, {"GPIO35", "GPIO36", "GPIO37"})

    def test_core_reserved_pins(self) -> None:
        self.assertEqual(
            self.pins.core_reserved, {"GPIO0", "GPIO3", "GPIO19", "GPIO20", "GPIO45", "GPIO46"}
        )

    def test_soft_reserved_pins(self) -> None:
        self.assertEqual(self.pins.soft_reserved, {"GPIO43", "GPIO44"})

    def test_excluded_pins_are_not_in_the_pool(self) -> None:
        for pin in ("GPIO26", "GPIO27", "GPIO28", "GPIO33", "GPIO34"):
            self.assertNotIn(pin, self.pins.allowed, msg=f"{pin} must not be inferred available")

    def test_no_pin_class_overlaps(self) -> None:
        classes = [self.pins.allowed, self.pins.core_reserved, self.pins.hard_forbidden, self.pins.soft_reserved]
        for i, left in enumerate(classes):
            for right in classes[i + 1 :]:
                self.assertFalse(left & right, msg="pin classes must be disjoint")

    def test_hard_forbidden_pin_is_denied_even_without_any_evidence(self) -> None:
        for pin in sorted(self.pins.hard_forbidden):
            decision = self.engine.evaluate(
                fx.request(
                    "DESIGN_ASSIGN_PIN",
                    {"pin": pin, "function": "LED", "approval_status": "NOT_REQUIRED"},
                    candidate_root=self.candidate_root,
                )
            )
            self.assertEqual(decision.outcome, Outcome.DENY, msg=pin)
            self.assertEqual(decision.reason_code, "POLICY_PIN_HARD_FORBIDDEN")

    def test_soft_reserved_pin_requires_approval(self) -> None:
        decision = self.engine.evaluate(
            fx.request(
                "DESIGN_ASSIGN_PIN",
                {"pin": "GPIO43", "function": "U0TXD", "approval_status": "NOT_REQUIRED"},
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "APPROVAL_PIN_OVERRIDE_REQUIRED")


class SupersessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SandboxPolicyEngine.for_edd001(REPO_ROOT)
        self.rules = {rule.rule_id: rule for rule in self.engine.document.active_rules}

    def test_superseded_rules_do_not_re_enter_the_active_set(self) -> None:
        """The pin contract's superseded copies must never become active.

        ``EN_RESET_NETWORK`` legitimately stays active, but sourced from
        CORE_BASE; only the pin contract's copy is retired.
        """
        pin_contract = read_contract("edd001_pin_constraints_v1.json")
        active = self.engine.document.active_rules
        active_ids = {rule.rule_id for rule in active}
        pin_sourced = {
            rule.rule_id for rule in active if rule.source_contract_id == "edd001_pin_constraints_v1.json"
        }

        for rule_id in EXPECTED_SUPERSEDED_RULE_IDS:
            self.assertNotIn(
                rule_id,
                pin_sourced,
                msg=f"{rule_id} was superseded by CORE_BASE and must not be sourced from the pin contract",
            )

        declared = {rule["id"] for rule in pin_contract["rules"]}
        still_active = declared - EXPECTED_SUPERSEDED_RULE_IDS
        self.assertEqual(still_active, EXPECTED_ACTIVE_PIN_RULE_IDS)
        self.assertTrue(EXPECTED_ACTIVE_PIN_RULE_IDS.issubset(active_ids))
        self.assertEqual(pin_sourced, EXPECTED_ACTIVE_PIN_RULE_IDS)

    def test_active_pin_rules_are_kept(self) -> None:
        for rule_id in EXPECTED_ACTIVE_PIN_RULE_IDS:
            self.assertIn(rule_id, self.rules, msg=rule_id)
            self.assertEqual(
                self.rules[rule_id].source_contract_id, "edd001_pin_constraints_v1.json"
            )

    def test_core_base_is_authoritative_for_the_shared_rule_id(self) -> None:
        # EN_RESET_NETWORK exists in both contracts. CORE_BASE must win.
        rule = self.rules["EN_RESET_NETWORK"]
        self.assertEqual(rule.source_contract_id, "edd001_core_base_contract_v1.json")

    def test_ignoring_supersession_fails_closed(self) -> None:
        """Supersession is load-bearing, not decorative.

        EN_RESET_NETWORK exists in both contracts with different payloads, so
        dropping supersession surfaces a duplicate-conflict and must fail
        closed instead of picking a winner.
        """
        from aedl_sandbox.policy.edd001 import build_document_from_contracts

        contracts = load_real_contracts()
        document = build_document_from_contracts(contracts, REPO_ROOT, honor_supersession=False)
        with self.assertRaises(PolicyDocumentError):
            SandboxPolicyEngine.from_document(document, REPO_ROOT)

    def test_active_rule_count(self) -> None:
        core_base = read_contract("edd001_core_base_contract_v1.json")
        usb = read_contract("edd001_usb_contract_v1.json")
        expected = len(core_base["rules"]) + len(usb["rules"]) + len(EXPECTED_ACTIVE_PIN_RULE_IDS)
        self.assertEqual(len(self.engine.document.active_rules), expected)


class ContractOrderInvarianceTests(unittest.TestCase):
    def setUp(self) -> None:
        from aedl_sandbox.policy.edd001 import build_document_from_contracts

        self.build = build_document_from_contracts
        self.contracts = load_real_contracts()
        self._tmp = tempfile.TemporaryDirectory()
        self.candidate_root = Path(self._tmp.name) / "candidate"
        self.candidate_root.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def probe(self, document: dict[str, Any]) -> list[tuple[Any, Any, Any]]:
        engine = SandboxPolicyEngine.from_document(document, REPO_ROOT)
        requests = [
            ("DESIGN_ASSIGN_PIN", {"pin": "GPIO35", "function": "LED", "approval_status": "NOT_REQUIRED"}),
            ("DESIGN_ASSIGN_PIN", {"pin": "GPIO0", "function": "LED", "approval_status": "NOT_REQUIRED"}),
            ("DESIGN_ASSIGN_PIN", {"pin": "GPIO43", "function": "LED", "approval_status": "NOT_REQUIRED"}),
            ("DESIGN_ASSIGN_PIN", {"pin": "GPIO1", "function": "LED", "approval_status": "NOT_REQUIRED"}),
            ("DESIGN_ASSIGN_PIN", {"pin": "GPIO99", "function": "LED", "approval_status": "NOT_REQUIRED"}),
            ("NETWORK_ACCESS", {"destination": "x", "purpose": "y"}),
            ("SHELL_EXECUTE", {"command_class": "arbitrary"}),
            (
                "DESIGN_SELECT_COMPONENT",
                {"mpn": "ESP32-S3-WROOM-1-N8R8", "role": "mcu_module", "evidence_ids": ["WROOM1_DATASHEET"]},
            ),
            (
                "DESIGN_SELECT_COMPONENT",
                {"mpn": "NOT-A-PART", "role": "mcu_module", "evidence_ids": []},
            ),
            (
                "DESIGN_SET_PARAMETER",
                {
                    "parameter_id": "USB_SERIES_RESISTOR_OHM",
                    "value": 22.0,
                    "unit": "ohm",
                    "evidence_ids": ["ESPRESSIF_SCHEMATIC_CHECKLIST"],
                },
            ),
            (
                "DESIGN_SET_PARAMETER",
                {
                    "parameter_id": "USB_DIFF_IMPEDANCE_OHM",
                    "value": 95.0,
                    "unit": "ohm",
                    "evidence_ids": ["ESPRESSIF_LAYOUT_GUIDE"],
                },
            ),
            (
                "FILE_WRITE",
                {"path": "design.kicad_sch", "artifact_kind": "kicad_sch", "writer": "agent"},
            ),
            (
                "FILE_WRITE",
                {"path": "../escape.net", "artifact_kind": "netlist", "writer": "agent"},
            ),
        ]
        results = []
        for action, subject in requests:
            decision = engine.evaluate(fx.request(action, subject, candidate_root=self.candidate_root))
            results.append((decision.outcome, decision.reason_code, tuple(decision.findings)))
        return results

    def test_contract_order_does_not_change_decisions_or_findings(self) -> None:
        forward = self.probe(self.build(self.contracts, REPO_ROOT))
        reversed_contracts = list(reversed(self.contracts))
        backward = self.probe(self.build(reversed_contracts, REPO_ROOT))
        self.assertEqual(forward, backward)

    def test_document_is_identical_under_permutation(self) -> None:
        import itertools

        baseline = json.dumps(self.build(self.contracts, REPO_ROOT), sort_keys=True)
        for permutation in itertools.permutations(self.contracts):
            produced = json.dumps(self.build(list(permutation), REPO_ROOT), sort_keys=True)
            self.assertEqual(produced, baseline)


class MalformedContractBundleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo_root = Path(self._tmp.name)
        (self.repo_root / "gates" / "contracts").mkdir(parents=True)
        (self.repo_root / "src" / "hardware" / "edd001-board" / "evidence" / "datasheets").mkdir(
            parents=True
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def install(self, name: str, document: Any) -> None:
        target = self.repo_root / "gates" / "contracts" / name
        if isinstance(document, str):
            target.write_text(document, encoding="utf-8")
        else:
            target.write_text(json.dumps(document), encoding="utf-8")

    def install_real_bundle(self) -> None:
        for name in CONTRACT_FILENAMES:
            self.install(name, read_contract(name))

    def test_malformed_json_fails_closed(self) -> None:
        self.install_real_bundle()
        self.install("edd001_core_base_contract_v1.json", "{ this is not json")
        with self.assertRaises(PolicyDocumentError):
            SandboxPolicyEngine.for_edd001(self.repo_root)

    def test_wrong_board_id_fails_closed(self) -> None:
        self.install_real_bundle()
        core = read_contract("edd001_core_base_contract_v1.json")
        core["board_id"] = "project-027-edd002"
        self.install("edd001_core_base_contract_v1.json", core)
        with self.assertRaises(PolicyDocumentError):
            SandboxPolicyEngine.for_edd001(self.repo_root)

    def test_wrong_schema_version_fails_closed(self) -> None:
        self.install_real_bundle()
        core = read_contract("edd001_core_base_contract_v1.json")
        core["schema_version"] = 2
        self.install("edd001_core_base_contract_v1.json", core)
        with self.assertRaises(PolicyDocumentError):
            SandboxPolicyEngine.for_edd001(self.repo_root)

    def test_missing_contract_file_fails_closed(self) -> None:
        self.install("edd001_core_base_contract_v1.json", read_contract("edd001_core_base_contract_v1.json"))
        with self.assertRaises(PolicyDocumentError):
            SandboxPolicyEngine.for_edd001(self.repo_root)

    def test_empty_contract_directory_fails_closed(self) -> None:
        with self.assertRaises(PolicyDocumentError):
            SandboxPolicyEngine.for_edd001(self.repo_root)

    def test_local_datasheets_are_discovered(self) -> None:
        self.install_real_bundle()
        datasheets = self.repo_root / "src" / "hardware" / "edd001-board" / "evidence" / "datasheets"
        make_evidence_dir(datasheets, "WROOM1_DATASHEET")
        make_evidence_dir(datasheets, "S3_DATASHEET")
        engine = SandboxPolicyEngine.for_edd001(self.repo_root)
        self.assertEqual(
            engine.document.available_evidence_ids, {"WROOM1_DATASHEET", "S3_DATASHEET"}
        )

    def test_empty_evidence_directory_is_not_local_evidence(self) -> None:
        """Audit counterexample (Wave 3): an empty directory (or one holding
        only empty files) is missing evidence and must stay BLOCKED."""
        self.install_real_bundle()
        datasheets = self.repo_root / "src" / "hardware" / "edd001-board" / "evidence" / "datasheets"
        (datasheets / "WROOM1_DATASHEET").mkdir()          # empty directory
        only_empty = datasheets / "S3_DATASHEET"           # directory with an empty file
        only_empty.mkdir()
        (only_empty / "empty.pdf").write_text("", encoding="utf-8")
        engine = SandboxPolicyEngine.for_edd001(self.repo_root)
        self.assertEqual(engine.document.available_evidence_ids, frozenset())

    def test_bundle_stays_blocked_even_with_all_datasheets_present(self) -> None:
        """Adding local datasheets must not manufacture a false PASS."""
        self.install_real_bundle()
        datasheets = self.repo_root / "src" / "hardware" / "edd001-board" / "evidence" / "datasheets"
        for evidence_id in (
            "WROOM1_DATASHEET",
            "S3_DATASHEET",
            "LCSC_C165948",
            "ST_USBLC6_2",
            "ESPRESSIF_S3_LCD_EV_BOARD",
            "ESPRESSIF_SCHEMATIC_CHECKLIST",
            "ESPRESSIF_LAYOUT_GUIDE",
            "ESPTOOL_BOOT_MODE",
            "ESP32_S3_SCHEMATIC_CHECKLIST",
            "ESP32_S3_TECHPEDIA",
        ):
            make_evidence_dir(datasheets, evidence_id)
        engine = SandboxPolicyEngine.for_edd001(self.repo_root)
        candidate_root = self.repo_root / "runs" / "candidate"
        decision = engine.preflight("run-complete-evidence", candidate_root)
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        present = fx.codes(decision)
        self.assertIn("EVIDENCE_REQUIRED_CONTRACT_MISSING", present)
        self.assertIn("POLICY_COMPILER_NOT_REGISTERED", present)
        self.assertIn("POLICY_VERIFIER_COVERAGE_MISSING", present)
        self.assertNotIn("EVIDENCE_COMPONENT_SOURCE_MISSING", present)


class RegistryEmptinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SandboxPolicyEngine.for_edd001(REPO_ROOT)

    def test_no_tools_compilers_or_verifiers_are_registered(self) -> None:
        document = self.engine.document
        self.assertEqual(document.tools, ())
        self.assertEqual(document.compilers, ())
        self.assertEqual(document.verifiers, ())

    def test_no_component_resolutions_are_declared(self) -> None:
        self.assertEqual(self.engine.document.prerequisites.required_component_resolutions, ())

    def test_required_contract_ids_include_the_missing_power_contract(self) -> None:
        self.assertEqual(
            self.engine.document.prerequisites.required_contract_ids,
            ("EDD-001.CORE_BASE", "EDD-001.PIN_CONSTRAINTS", "EDD-001.POWER", "EDD-001.USB"),
        )


class Wave3CounterexampleTests(unittest.TestCase):
    """Audit CHANGES_REQUIRED regressions against the real EDD-001 bundle.

    Any counterexample that still yields ALLOW fails this suite: all four
    audit blocks must be fail-closed.
    """

    def setUp(self) -> None:
        self.engine = SandboxPolicyEngine.for_edd001(REPO_ROOT)
        self.candidate_root = REPO_ROOT / "sandbox_runtime" / ".runs" / "agent-m-preflight"

    def test_nan_against_real_bounds_is_denied_not_allowed(self) -> None:
        """USB_DIFF_IMPEDANCE_OHM is declared 90ohm +/-10% (bounds 81..99).
        NaN compares False against every bound and previously slipped into
        the admissible range; it must now be refused."""
        for value in (float("nan"), float("inf"), float("-inf")):
            decision = self.engine.evaluate(
                fx.request(
                    "DESIGN_SET_PARAMETER",
                    {
                        "parameter_id": "USB_DIFF_IMPEDANCE_OHM",
                        "value": value,
                        "unit": "ohm",
                        "evidence_ids": ["ESPRESSIF_LAYOUT_GUIDE"],
                    },
                    candidate_root=self.candidate_root,
                )
            )
            self.assertNotEqual(decision.outcome, Outcome.ALLOW, msg=repr(value))
            self.assertEqual(decision.outcome, Outcome.DENY, msg=repr(value))
            self.assertEqual(decision.reason_code, "POLICY_SUBJECT_MALFORMED", msg=repr(value))
        # Sanity: a finite in-range value keeps the ordinary (evidence)
        # BLOCKED outcome, proving the bounds path itself still works.
        decision = self.engine.evaluate(
            fx.request(
                "DESIGN_SET_PARAMETER",
                {
                    "parameter_id": "USB_DIFF_IMPEDANCE_OHM",
                    "value": 95.0,
                    "unit": "ohm",
                    "evidence_ids": ["ESPRESSIF_LAYOUT_GUIDE"],
                },
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_PARAMETER_SOURCE_MISSING")

    def test_self_declared_pin_approval_on_the_real_bundle_is_blocked(self) -> None:
        """GPIO43/GPIO44 are soft-reserved; a requester-written APPROVED must
        never unlock them."""
        for pin in ("GPIO43", "GPIO44"):
            for approval in ("APPROVED", "PENDING", "NOT_REQUIRED"):
                decision = self.engine.evaluate(
                    fx.request(
                        "DESIGN_ASSIGN_PIN",
                        {"pin": pin, "function": "U0TXD", "approval_status": approval},
                        candidate_root=self.candidate_root,
                    )
                )
                self.assertNotEqual(decision.outcome, Outcome.ALLOW, msg=f"{pin} {approval}")
                self.assertEqual(decision.outcome, Outcome.BLOCKED, msg=f"{pin} {approval}")
                self.assertEqual(
                    decision.reason_code, "APPROVAL_PIN_OVERRIDE_REQUIRED", msg=f"{pin} {approval}"
                )

    def test_self_declared_compiler_writer_on_the_real_bundle_is_denied(self) -> None:
        decision = self.engine.evaluate(
            fx.request(
                "FILE_WRITE",
                {"path": "design.kicad_sch", "artifact_kind": "kicad_sch", "writer": "compiler"},
                candidate_root=self.candidate_root,
            )
        )
        self.assertEqual(decision.outcome, Outcome.DENY)
        self.assertEqual(decision.reason_code, "POLICY_CAPABILITY_NOT_GRANTED")


class TrustBundleBindingTests(unittest.TestCase):
    """V2 (Wave 3): policy input is bound to the trust-validated bundle."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        (self.repo / "gates" / "contracts").mkdir(parents=True)
        manifest_target = self.repo / REAL_BUNDLE_MANIFEST.relative_to(REPO_ROOT)
        manifest_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_BUNDLE_MANIFEST, manifest_target)
        self.manifest = manifest_target
        self.candidate_root = self.repo / "sandbox_runtime" / ".runs" / "binding-test"
        self.candidate_root.mkdir(parents=True)

    def install_contracts(self) -> None:
        for name in CONTRACT_FILENAMES:
            shutil.copyfile(REPO_ROOT / "gates" / "contracts" / name, self.repo / "gates" / "contracts" / name)

    def tamper_contract(self, name: str) -> None:
        path = self.repo / "gates" / "contracts" / name
        document = json.loads(path.read_text(encoding="utf-8"))
        document["rules"] = document.get("rules", []) + [
            {"id": "WAVE3_TAMPER_PROBE", "kind": "tamper", "constraint": {}}
        ]
        path.write_text(json.dumps(document), encoding="utf-8")

    def test_real_port_preflight_matches_the_unbound_engine(self) -> None:
        from aedl_sandbox import adapters

        port = adapters.build_real_edd001_policy_port(REPO_ROOT)
        bound = port.evaluate(
            fx.request("preflight", {}, candidate_root=REPO_ROOT / "sandbox_runtime" / ".runs" / "agent-m-preflight")
        )
        direct = SandboxPolicyEngine.for_edd001(REPO_ROOT).preflight(
            "run-test-0001", REPO_ROOT / "sandbox_runtime" / ".runs" / "agent-m-preflight"
        )
        self.assertEqual(bound.outcome, Outcome.BLOCKED)
        self.assertEqual(sorted(f.code for f in bound.findings), sorted(f.code for f in direct.findings))
        # 8 findings: 5 component evidence gaps (incl. nested AP63203WU-7) +
        # missing POWER contract + compiler + verifier coverage.
        self.assertEqual(len(bound.findings), 8)
        # The port stamps the validated manifest identity on its requests.
        self.assertEqual(len(port.verified_bundle_sha256), 64)

    def test_tampered_contract_fails_closed_blocked(self) -> None:
        from aedl_sandbox import adapters

        self.install_contracts()
        self.tamper_contract("edd001_core_base_contract_v1.json")
        port = adapters.build_real_edd001_policy_port(self.repo)
        decision = port.evaluate(
            fx.request("preflight", {}, candidate_root=self.candidate_root)
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_BUNDLE_INVALID")
        for action, subject in (
            ("DESIGN_ASSIGN_PIN", {"pin": "GPIO1", "function": "LED", "approval_status": "NOT_REQUIRED"}),
            (
                "DESIGN_SELECT_COMPONENT",
                {"mpn": "ESP32-S3-WROOM-1-N8R8", "role": "mcu_module", "evidence_ids": []},
            ),
        ):
            decision = port.evaluate(
                fx.request(action, subject, candidate_root=self.candidate_root)
            )
            self.assertEqual(decision.outcome, Outcome.BLOCKED, msg=action)
            self.assertNotEqual(decision.outcome, Outcome.ALLOW, msg=action)

    def test_missing_manifest_fails_closed_blocked(self) -> None:
        from aedl_sandbox import adapters

        self.manifest.unlink()  # bundle manifest absent: nothing to bind to
        port = adapters.build_real_edd001_policy_port(self.repo)
        decision = port.evaluate(
            fx.request("preflight", {}, candidate_root=self.candidate_root)
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_BUNDLE_INVALID")

    def test_contract_drift_from_manifest_fails_engine_construction(self) -> None:
        from aedl_sandbox.policy import PolicyDocumentError, load_contracts_bound_to_manifest

        self.install_contracts()
        self.tamper_contract("edd001_usb_contract_v1.json")
        with self.assertRaises(PolicyDocumentError):
            load_contracts_bound_to_manifest(self.repo, self.manifest)
        with self.assertRaises(PolicyDocumentError):
            SandboxPolicyEngine.for_edd001(self.repo, manifest_path=self.manifest)

    def test_request_citing_a_different_bundle_is_blocked(self) -> None:
        engine = SandboxPolicyEngine.for_edd001(REPO_ROOT, manifest_path=REAL_BUNDLE_MANIFEST)
        self.assertEqual(len(engine.verified_bundle_sha256), 64)
        decision = engine.evaluate(
            fx.request(
                "DESIGN_ASSIGN_PIN",
                {"pin": "GPIO1", "function": "LED", "approval_status": "NOT_REQUIRED"},
                candidate_root=REPO_ROOT / "sandbox_runtime" / ".runs" / "agent-m-preflight",
                verified_bundle_sha256="f" * 64,
            )
        )
        self.assertEqual(decision.outcome, Outcome.BLOCKED)
        self.assertEqual(decision.reason_code, "EVIDENCE_BUNDLE_MISMATCH")

    def test_request_citing_the_true_bundle_is_not_mismatched(self) -> None:
        engine = SandboxPolicyEngine.for_edd001(REPO_ROOT, manifest_path=REAL_BUNDLE_MANIFEST)
        decision = engine.evaluate(
            fx.request(
                "DESIGN_ASSIGN_PIN",
                {"pin": "GPIO1", "function": "LED", "approval_status": "NOT_REQUIRED"},
                candidate_root=REPO_ROOT / "sandbox_runtime" / ".runs" / "agent-m-preflight",
                verified_bundle_sha256=engine.verified_bundle_sha256,
            )
        )
        self.assertNotEqual(decision.reason_code, "EVIDENCE_BUNDLE_MISMATCH")
        self.assertEqual(decision.outcome, Outcome.BLOCKED)  # real bundle prereqs


if __name__ == "__main__":
    unittest.main()
