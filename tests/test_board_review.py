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
