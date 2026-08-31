import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gates.gate_core import validate_render_evidence
from tools.board_review import review_exit_code, review_usb_routing


GOOD_PINS = {
    "J1.A6": "USB_DP_CONN",
    "J1.B6": "USB_DP_CONN",
    "R7.1": "USB_DP_CONN",
    "R7.2": "USB_DP",
    "U1.14": "USB_DP",
    "J1.A7": "USB_DM_CONN",
    "J1.B7": "USB_DM_CONN",
    "R8.1": "USB_DM_CONN",
    "R8.2": "USB_DM",
    "U1.13": "USB_DM",
}


def segment(net, length):
    return {"net": net, "x1": 0.0, "y1": 0.0, "x2": length, "y2": 0.0}


class BoardReviewTests(unittest.TestCase):
    def test_board_review_process_fails_closed_on_any_non_pass_status(self):
        self.assertEqual(review_exit_code([{"status": "pass"}]), 0)
        self.assertEqual(review_exit_code([{"status": "fail"}]), 1)
        self.assertEqual(review_exit_code([{"status": "unknown"}]), 1)
        self.assertEqual(review_exit_code([{}]), 1)

    def test_usb_review_measures_both_sides_of_each_series_resistor(self):
        segments = [
            segment("USB_DP_CONN", 18.0),
            segment("USB_DP", 2.0),
            segment("USB_DM_CONN", 17.6),
            segment("USB_DM", 2.1),
        ]

        result = review_usb_routing(segments, GOOD_PINS)

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["measured"]["logical_channel_lengths_mm"]["D+"], 20.0)
        self.assertEqual(result["measured"]["logical_channel_lengths_mm"]["D-"], 19.7)
        self.assertEqual(result["measured"]["endpoint_mismatches"], [])

    def test_usb_review_rejects_crossed_mcu_endpoint_identity(self):
        crossed = dict(GOOD_PINS)
        crossed["U1.14"] = "USB_DM"
        crossed["U1.13"] = "USB_DP"
        segments = [
            segment("USB_DP_CONN", 18.0),
            segment("USB_DP", 2.0),
            segment("USB_DM_CONN", 18.0),
            segment("USB_DM", 2.0),
        ]

        result = review_usb_routing(segments, crossed)

        self.assertEqual(result["status"], "fail")
        self.assertIn("U1.14", " ".join(result["measured"]["endpoint_mismatches"]))
        self.assertIn("U1.13", " ".join(result["measured"]["endpoint_mismatches"]))


def build_render_fixture(root: Path) -> dict:
    generated = root / "notes" / "m2-evidence-reset" / "generated"
    generated.mkdir(parents=True)
    pcb = root / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb"
    pcb.parent.mkdir(parents=True)
    pcb.write_bytes(b"(kicad_pcb (version 20260831) (pcb-v1))")
    top = generated / "board_top.png"
    bottom = generated / "board_bottom.png"
    top.write_bytes(b"PNG-TOP")
    bottom.write_bytes(b"PNG-BOTTOM")
    auto = generated / "board_review_auto.json"
    auto.write_text(
        json.dumps(
            {
                "render_evidence": {
                    "pcb_sha256": hashlib.sha256(pcb.read_bytes()).hexdigest(),
                    "top_png_sha256": hashlib.sha256(top.read_bytes()).hexdigest(),
                    "bottom_png_sha256": hashlib.sha256(bottom.read_bytes()).hexdigest(),
                    "rendered_at": "2026-08-31T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    return {"auto": auto, "pcb": pcb, "top": top, "bottom": bottom}


class RenderEvidenceTests(unittest.TestCase):
    def test_current_render_evidence_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture = build_render_fixture(root)

            errors = validate_render_evidence(fixture["auto"], fixture["pcb"])

        self.assertEqual(errors, [])

    def test_missing_render_evidence_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture = build_render_fixture(root)
            fixture["auto"].write_text(json.dumps({"reviews": []}), encoding="utf-8")

            errors = validate_render_evidence(fixture["auto"], fixture["pcb"])

        self.assertEqual(len(errors), 1)
        self.assertIn("render_evidence", errors[0])

    def test_missing_auto_evidence_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture = build_render_fixture(root)
            fixture["auto"].unlink()

            errors = validate_render_evidence(fixture["auto"], fixture["pcb"])

        self.assertEqual(len(errors), 1)
        self.assertIn("missing", errors[0])

    def test_stale_pcb_sha256_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture = build_render_fixture(root)
            fixture["pcb"].write_bytes(b"(kicad_pcb (version 20260831) (pcb-v2))")

            errors = validate_render_evidence(fixture["auto"], fixture["pcb"])

        self.assertEqual(len(errors), 1)
        self.assertIn("pcb_sha256", errors[0])

    def test_missing_png_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture = build_render_fixture(root)
            fixture["top"].unlink()

            errors = validate_render_evidence(fixture["auto"], fixture["pcb"])

        self.assertEqual(len(errors), 1)
        self.assertIn("board_top.png", errors[0])

    def test_png_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture = build_render_fixture(root)
            fixture["bottom"].write_bytes(b"PNG-BOTTOM-STALE")

            errors = validate_render_evidence(fixture["auto"], fixture["pcb"])

        self.assertEqual(len(errors), 1)
        self.assertIn("bottom_png_sha256", errors[0])


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Gate-level regressions (task: manufacturing gate strictness, 2026-08-31).
# The board_review GATE must fail when the machine report disagrees with the
# manual sign-off, and a release must be pinned to exact evidence versions.
# ---------------------------------------------------------------------------

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from gates.gate_core import BOARD_REVIEW_ALGORITHM_REVISION, sha256_file
from gates.run_gates import _evaluate_board_review

BOARD_REVIEW_IDS = (
    "USB_EDGE", "ESP_ANTENNA", "GROUND_RETURN", "DECOUPLING",
    "USB_ROUTING", "SHT30_THERMAL", "PROTECTION", "ASSEMBLY",
)

PCB_BYTES = b"(footprint \"m2 board fixture\")"
SCH_BYTES = b"(schematic \"m2 sch fixture\")"


def _write_bytes(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class BoardReviewGateRegressionTests(unittest.TestCase):
    """Full temp-root sandboxes; repo evidence is never touched."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.pcb = _write_bytes(
            self.root / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb", PCB_BYTES)
        self.sch = _write_bytes(
            self.root / "src" / "hardware" / "m2-board" / "m2_board.kicad_sch", SCH_BYTES)
        self.evidence = self.root / "notes" / "m2-evidence-reset" / "generated"

    def _write_auto(self, statuses=None, summary=None):
        statuses = statuses or {rid: "pass" for rid in BOARD_REVIEW_IDS}
        reviews = [{"id": rid, "status": status} for rid, status in statuses.items()]
        report = {
            "algorithm_revision": BOARD_REVIEW_ALGORITHM_REVISION,
            "generated_at": "2026-08-31T00:00:00Z",
            "pcb": "src/hardware/m2-board/m2_board.kicad_pcb",
            "reviews": reviews,
            "summary": summary if summary is not None else dict(statuses),
            "render_evidence": {
                "pcb_sha256": _sha_bytes(PCB_BYTES),
                "top_png_sha256": _sha_bytes(b"top"),
                "bottom_png_sha256": _sha_bytes(b"bottom"),
                "rendered_at": "2026-08-31T00:00:00Z",
            },
        }
        auto = _write_bytes(self.evidence / "board_review_auto.json",
                            json.dumps(report).encode("utf-8"))
        _write_bytes(self.evidence / "board_top.png", b"top")
        _write_bytes(self.evidence / "board_bottom.png", b"bottom")
        return auto

    def _write_manual(self, release=True, auto=None, signoff_schematic=None,
                      include_bindings=True, include_auto_hash=True):
        meta = {
            "manufacturing_release": release,
            "reviewer": "human reviewer",
            "reviewed_at": "2026-08-31T00:00:00Z",
            "auto_evidence": str(auto) if auto else "notes/m2-evidence-reset/generated/board_review_auto.json",
        }
        if include_auto_hash:
            meta["auto_evidence_sha256"] = sha256_file(
                self.root / meta["auto_evidence"]) if auto is None or Path(auto).is_file() else "0" * 64
        if include_bindings:
            meta["signoff_inputs_sha256"] = {
                "pcb": _sha_bytes(PCB_BYTES),
                "schematic": signoff_schematic or _sha_bytes(SCH_BYTES),
            }
        reviews = [{"id": rid, "status": "pass", "item": rid,
                    "evidence": "manual visual check", "decision": "confirmed"}
                   for rid in BOARD_REVIEW_IDS]
        if not release:
            meta["release_revocation"] = {
                "incident_id": "PIT-20260830-001",
                "revoked_at": "2026-08-30T00:00:00Z",
                "reason": "fixture revocation",
                "human_resign_required": True,
                "superseded_signoff": {"reviewer": "a", "reviewed_at": "2026-08-29T00:00:00Z",
                                       "auto_evidence": "old", "drc_evidence": "old"},
            }
        manual = _write_bytes(self.root / "gates" / "board_review_v1.json",
                              json.dumps({"_meta": meta, "reviews": reviews}).encode("utf-8"))
        return manual

    def _evaluate(self):
        return _evaluate_board_review(self.root / "gates" / "board_review_v1.json")

    def test_all_pass_with_fresh_bindings_and_release_passes(self):
        self._write_auto()
        self._write_manual(release=True)
        gate = self._evaluate()
        self.assertEqual(gate["status"], "pass", gate["errors"])

    def test_auto_failure_fails_the_gate_even_with_manual_release(self):
        self._write_auto(statuses={**{rid: "pass" for rid in BOARD_REVIEW_IDS},
                                   "SHT30_THERMAL": "fail"})
        self._write_manual(release=True)
        gate = self._evaluate()
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(any("auto review SHT30_THERMAL is not pass" in e for e in gate["errors"]),
                        gate["errors"])

    def test_gate_fails_when_schematic_drifts_after_signoff(self):
        self._write_auto()
        self._write_manual(release=True, signoff_schematic=_sha_bytes(b"old schematic"))
        _write_bytes(self.sch, SCH_BYTES)  # current file differs from the signed hash
        gate = self._evaluate()
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(any("signoff_inputs_sha256.schematic does not match" in e
                            for e in gate["errors"]), gate["errors"])

    def test_gate_fails_on_summary_mismatch(self):
        self._write_auto(summary={rid: "pass" for rid in BOARD_REVIEW_IDS}
                         | {"USB_EDGE": "fail"})
        self._write_manual(release=True)
        gate = self._evaluate()
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(any("summary does not match" in e for e in gate["errors"]),
                        gate["errors"])

    def test_gate_fails_on_missing_duplicate_and_unknown_review_ids(self):
        cases = {
            "missing": [r for r in ({"id": rid, "status": "pass"} for rid in BOARD_REVIEW_IDS)
                        if r["id"] != "PROTECTION"],
            "duplicate": [{"id": "USB_EDGE", "status": "pass"}] * 2
                         + [{"id": rid, "status": "pass"} for rid in BOARD_REVIEW_IDS[1:]],
            "unknown": [{"id": rid, "status": "pass"} for rid in BOARD_REVIEW_IDS]
                       + [{"id": "BOGUS", "status": "pass"}],
        }
        for label, reviews in cases.items():
            with self.subTest(case=label):
                auto = self._write_auto()
                report = json.loads(auto.read_text(encoding="utf-8"))
                report["reviews"] = reviews
                report["summary"] = {rid: "pass" for rid in BOARD_REVIEW_IDS}
                auto.write_text(json.dumps(report), encoding="utf-8")
                self._write_manual(release=True)
                gate = self._evaluate()
                self.assertEqual(gate["status"], "fail", f"{label}: {gate['errors']}")

    def test_release_without_version_pin_is_rejected(self):
        self._write_auto()
        self._write_manual(release=True, include_bindings=False, include_auto_hash=False)
        gate = self._evaluate()
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(any("auto_evidence_sha256" in e for e in gate["errors"]), gate["errors"])
        self.assertTrue(any("signoff_inputs_sha256" in e for e in gate["errors"]), gate["errors"])

    def test_auto_report_without_algorithm_revision_is_rejected(self):
        # Problem 3: an auto report that predates the review algorithm (or was
        # generated by any other revision) must not pass strict validation -
        # otherwise a human re-signing hashes could pin stale-algorithm evidence.
        auto = self._write_auto()
        report = json.loads(auto.read_text(encoding="utf-8"))
        report.pop("algorithm_revision", None)
        auto.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        self._write_manual(release=True)
        gate = self._evaluate()
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(any("algorithm revision" in e for e in gate["errors"]),
                        gate["errors"])

    def test_auto_report_with_stale_algorithm_revision_is_rejected(self):
        auto = self._write_auto()
        report = json.loads(auto.read_text(encoding="utf-8"))
        report["algorithm_revision"] = "board-review-alg-2000-01-01-0"
        auto.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        self._write_manual(release=True)
        gate = self._evaluate()
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(any("algorithm revision" in e for e in gate["errors"]),
                        gate["errors"])

    def test_release_false_does_not_require_version_pins(self):
        # Pre-signoff state: the only honest error is the missing release
        # itself; machine-report strictness still applies.
        self._write_auto()
        self._write_manual(release=False)

        gate = self._evaluate()
        self.assertEqual(gate["status"], "fail")
        self.assertEqual(gate["errors"], ["manufacturing_release is false"], gate["errors"])


if __name__ == "__main__":
    unittest.main()
