import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from gates.gate_core import (
    BOARD_REVIEW_ALGORITHM_CONTRACT,
    BOARD_REVIEW_ALGORITHM_REVISION,
    BOARD_REVIEW_IDS,
    board_review_implementation_sha256,
    compute_board_review_algorithm_revision,
    count_drc_findings,
    count_erc_errors,
    drc_gate_verdict,
    erc_gate_verdict,
    validate_board_review_auto_report,
    validate_bom,
)


ROOT = Path(__file__).resolve().parents[1]


class GateCoreReviewTests(unittest.TestCase):
    def _write_json(self, root, name, data):
        path = Path(root) / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_empty_erc_sheets_fail_closed(self):
        report = {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_sch",
            "sheets": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(temp_dir, "erc.json", report)
            with self.assertRaises(ValueError):
                count_erc_errors(path)

    def test_erc_violation_missing_severity_fails_closed(self):
        report = {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_sch",
            "sheets": [{"path": "/", "violations": [{"type": "unknown"}]}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(temp_dir, "erc.json", report)
            with self.assertRaises(ValueError):
                count_erc_errors(path)

    def test_erc_unknown_severity_fails_closed(self):
        report = {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_sch",
            "sheets": [{"path": "/", "violations": [{"severity": "mystery"}]}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(temp_dir, "erc.json", report)
            with self.assertRaises(ValueError):
                count_erc_errors(path)

    def test_empty_drc_arrays_without_kicad_metadata_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(
                temp_dir,
                "drc.json",
                {"violations": [], "unconnected_items": []},
            )
            with self.assertRaises(ValueError):
                count_drc_findings(path)

    def test_valid_empty_kicad_reports_remain_green(self):
        erc = {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_sch",
            "sheets": [{"path": "/", "violations": []}],
        }
        drc = {
            "$schema": "https://schemas.kicad.org/drc.v1.json",
            "kicad_version": "10.0.5",
            "source": "board.kicad_pcb",
            "violations": [],
            "unconnected_items": [],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            erc_path = self._write_json(temp_dir, "erc.json", erc)
            drc_path = self._write_json(temp_dir, "drc.json", drc)
            self.assertEqual(count_erc_errors(erc_path), 0)
            self.assertEqual(count_drc_findings(drc_path), (0, 0))

    def test_each_bom_constraint_rejects_a_single_defect(self):
        valid = {
            "_meta": {"frozen_at": "2026-08-25T05:44:05Z"},
            "items": [
                {
                    "ref": "R1",
                    "value": "1k",
                    "lcsc": "C123",
                    "jlc_lib": "base",
                    "stock": 1,
                    "footprint": "Resistor_SMD:R_0603_1608Metric",
                }
            ],
        }
        cases = (
            ("duplicate ref", lambda data: data["items"][0].update(ref="R1,R1"), "duplicate ref"),
            ("missing ref", lambda data: data["items"][0].update(ref=""), "missing refs"),
            ("TBD LCSC", lambda data: data["items"][0].update(lcsc="TBD"), "TBD"),
            ("missing LCSC", lambda data: data["items"][0].pop("lcsc"), "LCSC"),
            ("zero stock", lambda data: data["items"][0].update(stock=0), "stock"),
            ("missing footprint", lambda data: data["items"][0].update(footprint=""), "footprint"),
            ("missing library", lambda data: data["items"][0].update(jlc_lib=""), "library"),
            ("date-only freeze", lambda data: data["_meta"].update(frozen_at="2026-08-25"), "frozen_at"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, (name, mutate, expected) in enumerate(cases):
                with self.subTest(name=name):
                    fixture = copy.deepcopy(valid)
                    mutate(fixture)
                    path = self._write_json(temp_dir, f"bom-{index}.json", fixture)
                    errors = validate_bom(path)
                    self.assertTrue(errors)
                    self.assertTrue(any(expected in error for error in errors), errors)

    def test_minimal_legal_bom_returns_no_errors(self):
        valid = {
            "_meta": {"frozen_at": "2026-08-25T05:44:05Z"},
            "items": [
                {
                    "ref": "R1",
                    "value": "1k",
                    "lcsc": "C123",
                    "jlc_lib": "base",
                    "stock": 1,
                    "footprint": "Resistor_SMD:R_0603_1608Metric",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write_json(temp_dir, "bom.json", valid)
            self.assertEqual(validate_bom(path), [])

    def test_erc_two_errors_has_explicit_fail_exit_semantics(self):
        verdict = erc_gate_verdict(ROOT / "tests/fixtures/g2_erc_before_reset.json")
        self.assertEqual(
            verdict,
            {"status": "fail", "exit_code": 1, "error_count": 2},
        )

    def test_drc_zero_findings_has_explicit_pass_exit_semantics(self):
        verdict = drc_gate_verdict(ROOT / "notes/m1-evidence/g4_drc_final.json")
        self.assertEqual(
            verdict,
            {
                "status": "pass",
                "exit_code": 0,
                "violation_count": 0,
                "unconnected_count": 0,
            },
        )


def _auto_report(revision="__ABSENT__"):
    """A minimal all-pass auto report; revision='__ABSENT__' omits the field
    (the exact shape of the pre-P11-B 2026-08-30 report)."""
    report = {
        "reviews": [{"id": rid, "status": "pass"} for rid in BOARD_REVIEW_IDS],
        "summary": {rid: "pass" for rid in BOARD_REVIEW_IDS},
    }
    if revision != "__ABSENT__":
        report["algorithm_revision"] = revision
    return report


class BoardReviewAlgorithmRevisionTests(unittest.TestCase):
    """P11-B issue 3: the auto report must be bound to the review algorithm
    revision that produced it, so a stale report can never be re-signed."""

    def _validate(self, report):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "board_review_auto.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            return validate_board_review_auto_report(path)

    def test_revision_is_a_stable_nonempty_identifier(self):
        self.assertIsInstance(BOARD_REVIEW_ALGORITHM_REVISION, str)
        self.assertTrue(BOARD_REVIEW_ALGORITHM_REVISION.strip())

    def test_report_with_current_revision_passes(self):
        errors = self._validate(_auto_report(BOARD_REVIEW_ALGORITHM_REVISION))
        self.assertEqual(errors, [])

    def test_old_report_without_revision_fails_closed(self):
        errors = self._validate(_auto_report())
        self.assertTrue(
            any("algorithm revision" in e for e in errors), errors)

    def test_report_with_a_stale_revision_fails_closed(self):
        errors = self._validate(_auto_report("sha256:" + "0" * 64))
        self.assertTrue(
            any("algorithm revision" in e for e in errors), errors)


class AlgorithmRevisionBindingTests(unittest.TestCase):
    """P1-2: the revision must bind the ACTUAL judgement implementation, not
    just the role-set/threshold contract. Editing a verdict-affecting code path
    (without touching a constant) must change the revision and reject any
    report produced by the previous code."""

    @staticmethod
    def _digest_of(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _impl_text(self):
        return (ROOT / "tools" / "board_review.py").read_text(encoding="utf-8")

    def test_current_implementation_revision_passes(self):
        # 1: the revision derived from the current file must be the active one.
        self.assertEqual(
            BOARD_REVIEW_ALGORITHM_REVISION,
            compute_board_review_algorithm_revision(
                BOARD_REVIEW_ALGORITHM_CONTRACT, board_review_implementation_sha256()),
        )
        self.assertRegex(BOARD_REVIEW_ALGORITHM_REVISION, r"^sha256:[0-9a-f]{64}$")

    def test_revision_binds_implementation_not_just_contract(self):
        # The whole point of P1-2: revision != sha256(contract alone). If a
        # verdict-affecting code edit did not change the revision, this would be
        # an equality with the contract-only digest.
        contract_only = "sha256:" + hashlib.sha256(
            json.dumps(BOARD_REVIEW_ALGORITHM_CONTRACT, ensure_ascii=False,
                       sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertNotEqual(BOARD_REVIEW_ALGORITHM_REVISION, contract_only)

    def test_implementation_change_alters_revision(self):
        # 3: change one judgement line in a copy of the source -> revision changes.
        original = self._impl_text()
        altered = original.replace("0 <= d <= USB_EDGE_MAX_MM", "0 <= d <= 999.0")
        self.assertNotEqual(altered, original, "needle must be present in the source")
        original_digest = board_review_implementation_sha256()
        altered_digest = self._digest_of(altered)
        self.assertNotEqual(original_digest, altered_digest)
        self.assertNotEqual(
            compute_board_review_algorithm_revision(BOARD_REVIEW_ALGORITHM_CONTRACT, original_digest),
            compute_board_review_algorithm_revision(BOARD_REVIEW_ALGORITHM_CONTRACT, altered_digest),
        )

    def test_report_from_previous_implementation_is_rejected(self):
        # 4: a report signed by the previous implementation is rejected by the
        #    current validator (which uses the current file's revision).
        altered = self._impl_text().replace(
            "0 <= d <= USB_EDGE_MAX_MM", "0 <= d <= 999.0")
        stale_revision = compute_board_review_algorithm_revision(
            BOARD_REVIEW_ALGORITHM_CONTRACT, self._digest_of(altered))
        self.assertNotEqual(stale_revision, BOARD_REVIEW_ALGORITHM_REVISION)
        report = {
            "reviews": [{"id": rid, "status": "pass"} for rid in BOARD_REVIEW_IDS],
            "summary": {rid: "pass" for rid in BOARD_REVIEW_IDS},
            "algorithm_revision": stale_revision,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "board_review_auto.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            errors = validate_board_review_auto_report(path)
        self.assertTrue(any("algorithm revision" in e for e in errors), errors)

    def test_contract_threshold_and_role_change_alters_revision(self):
        # 5: threshold or role-set changes still change the revision.
        impl = board_review_implementation_sha256()
        threshold_changed = copy.deepcopy(BOARD_REVIEW_ALGORITHM_CONTRACT)
        threshold_changed["thresholds_mm"]["usb_edge_max"] = 2.5
        self.assertNotEqual(
            compute_board_review_algorithm_revision(BOARD_REVIEW_ALGORITHM_CONTRACT, impl),
            compute_board_review_algorithm_revision(threshold_changed, impl),
        )
        role_changed = copy.deepcopy(BOARD_REVIEW_ALGORITHM_CONTRACT)
        role_changed["role_sets"]["expected_ics"] = ("U1", "U2", "U3", "U4")
        self.assertNotEqual(
            compute_board_review_algorithm_revision(BOARD_REVIEW_ALGORITHM_CONTRACT, impl),
            compute_board_review_algorithm_revision(role_changed, impl),
        )

    def test_revision_computation_is_deterministic(self):
        # 6: same contract + implementation -> identical revision, every time.
        impl = board_review_implementation_sha256()
        first = compute_board_review_algorithm_revision(BOARD_REVIEW_ALGORITHM_CONTRACT, impl)
        second = compute_board_review_algorithm_revision(BOARD_REVIEW_ALGORITHM_CONTRACT, impl)
        self.assertEqual(first, second)
        self.assertEqual(first, BOARD_REVIEW_ALGORITHM_REVISION)

    def test_missing_fake_and_stale_revisions_all_fail(self):
        # 2: missing / malformed / stale revisions are all rejected.
        for revision in (None, "sha256:" + "0" * 64, "not-a-revision"):
            report = {
                "reviews": [{"id": rid, "status": "pass"} for rid in BOARD_REVIEW_IDS],
                "summary": {rid: "pass" for rid in BOARD_REVIEW_IDS},
            }
            if revision is not None:
                report["algorithm_revision"] = revision
            with tempfile.TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "board_review_auto.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                errors = validate_board_review_auto_report(path)
            self.assertTrue(any("algorithm revision" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
