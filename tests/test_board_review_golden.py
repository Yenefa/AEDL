"""Characterization / golden tests for tools/board_review.py (TASK-P9).

These tests lock in **what the code actually does today**, not what it ideally
should do. That is deliberate: the point of this file is to make the upcoming
BoardReview / RouteRepair protocol extraction safe. Once behaviour is frozen,
any future change to a verdict, a threshold, or a measured key becomes a
visible diff instead of a silent regression.

Conventions:
- `Characterization*` classes assert current observed behaviour, including
  quirks (see the notes on `edge_distance` and `review_exit_code`).
- `Adversarial*` classes lock the failure paths and known blind spots.
- The golden report is frozen at tests/fixtures/board_review/golden_minimal.json.
  Regenerate deliberately with:  py -3 tests/test_board_review_golden.py --regen

The end-to-end golden test stubs out kicad-cli on purpose: the real renderer
takes ~26s and its PNG bytes are not reproducible across KiCad builds, which
would make the golden flaky.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import board_review
from tools.board_review import (
    boundary_distance,
    dist,
    edge_distance,
    find_kicad_cli,
    parse_pcb,
    render_board_views,
    review_antenna,
    review_assembly,
    review_decoupling,
    review_exit_code,
    review_ground_return,
    review_protection,
    review_thermal,
    review_usb_edge,
    review_usb_routing,
    sha256_file,
    utc_now,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "board_review"
PCB_FIXTURE = FIXTURES / "minimal.kicad_pcb"
SCH_FIXTURE = FIXTURES / "minimal.kicad_sch"
GOLDEN = FIXTURES / "golden_minimal.json"

REVIEW_IDS = (
    "USB_EDGE", "ESP_ANTENNA", "GROUND_RETURN", "DECOUPLING",
    "USB_ROUTING", "SHT30_THERMAL", "PROTECTION", "ASSEMBLY",
)


def load_fixture_pcb() -> str:
    return PCB_FIXTURE.read_text(encoding="utf-8")


def load_fixture_sch() -> str:
    return SCH_FIXTURE.read_text(encoding="utf-8")


def parsed_fixture() -> dict:
    return parse_pcb(load_fixture_pcb())


# ---------------------------------------------------------------------------
# 待办#2 — pure-function characterization
# ---------------------------------------------------------------------------


class PureFunctionCharacterizationTests(unittest.TestCase):
    """Lock the arithmetic helpers; these are the primitives any plugin will reuse."""

    def test_dist_is_euclidean(self):
        self.assertAlmostEqual(dist({"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 4.0}), 5.0)
        self.assertAlmostEqual(dist({"x": -1.0, "y": 2.0}, {"x": 2.0, "y": -2.0}), 5.0)

    def test_edge_distance_returns_min_gap_to_any_of_four_edges(self):
        edge = (0.0, 0.0, 60.0, 40.0)
        self.assertAlmostEqual(edge_distance({"x": 30.0, "y": 20.0}, edge), 20.0)
        # nearest of (x-x1, x2-x, y-y1, y2-y) = min(10, 50, 5, 35)
        self.assertAlmostEqual(edge_distance({"x": 10.0, "y": 5.0}, edge), 5.0)

    def test_edge_distance_is_negative_outside_the_outline(self):
        """QUIRK (locked on purpose): no abs() is applied, so an off-board part
        reports a negative distance. review_usb_edge compensates with
        `0 <= d <= MAX`; any future caller must clamp it themselves."""
        edge = (0.0, 0.0, 60.0, 40.0)
        self.assertAlmostEqual(edge_distance({"x": -3.0, "y": 20.0}, edge), -3.0)
        self.assertTrue(edge_distance({"x": 65.0, "y": 20.0}, edge) < 0)

    def test_boundary_distance_measures_gap_outside_courtyard(self):
        ic = {"x": 30.0, "y": 15.0, "courtyard": (-9.0, -12.7, 9.0, 12.7)}
        # courtyard in board coords: x 21..39, y 2.3..27.7 → cap at y=30 is 2.3mm out
        self.assertAlmostEqual(boundary_distance({"x": 30.0, "y": 30.0}, ic), 2.3, places=6)

    def test_boundary_distance_is_zero_inside_courtyard(self):
        ic = {"x": 30.0, "y": 15.0, "courtyard": (-9.0, -12.7, 9.0, 12.7)}
        self.assertAlmostEqual(boundary_distance({"x": 30.0, "y": 15.0}, ic), 0.0)

    def test_boundary_distance_falls_back_to_centroid_when_no_courtyard(self):
        """QUIRK (locked): a rotated/unknown package silently degrades to a
        centroid-to-centroid distance, i.e. a weaker check, with no warning."""
        ic = {"x": 30.0, "y": 15.0, "courtyard": None}
        self.assertAlmostEqual(boundary_distance({"x": 30.0, "y": 25.0}, ic), 10.0)

    def test_utc_now_is_second_precision_utc(self):
        stamp = utc_now()
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertNotIn(".", stamp)  # microseconds dropped
        self.assertNotIn("+00:00", stamp)

    def test_sha256_file_matches_known_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blob.bin"
            path.write_bytes(b"abc")
            self.assertEqual(
                sha256_file(path),
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            )

    def test_review_exit_code_fails_closed_on_empty_input(self):
        """QUIRK (locked, and it must stay this way): an empty review list is a
        FAIL, not a pass. Silently dropping every review must never read as OK."""
        self.assertEqual(review_exit_code([]), 1)
        self.assertEqual(review_exit_code(None), 1)
        self.assertEqual(review_exit_code([{"status": "pass"}]), 0)
        self.assertEqual(review_exit_code([{"status": "pass"}, {"status": "fail"}]), 1)

    def test_find_kicad_cli_honours_environment_variable_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "kicad-cli"
            fake.write_bytes(b"")
            with mock.patch.dict("os.environ", {"KICAD_CLI": str(fake)}):
                self.assertEqual(find_kicad_cli(), fake.resolve())


# ---------------------------------------------------------------------------
# 待办#2 — parse_pcb characterization
# ---------------------------------------------------------------------------


class ParsePcbCharacterizationTests(unittest.TestCase):
    def test_fixture_parses_to_expected_geometry(self):
        pcb = parsed_fixture()
        self.assertEqual(pcb["edge"], (0.0, 0.0, 60.0, 40.0))
        self.assertEqual([f["ref"] for f in pcb["footprints"]],
                         ["J1", "U1", "U2", "U3", "C1", "C2", "C3", "C4", "D1", "R7", "R8"])
        self.assertEqual(pcb["vias"], 5)
        self.assertTrue(pcb["has_zone"])
        self.assertEqual(len(pcb["segments"]), 4)
        self.assertEqual(pcb["nets"],
                         ["+5V", "GND", "USB_DM", "USB_DM_CONN", "USB_DP", "USB_DP_CONN"])

    def test_footprint_record_shape_is_stable(self):
        """Any plugin consuming footprints depends on exactly these keys."""
        j1 = parsed_fixture()["footprints"][0]
        self.assertEqual(set(j1), {"ref", "lib_id", "x", "y", "rot", "courtyard"})
        self.assertEqual(j1["ref"], "J1")
        self.assertEqual(j1["lib_id"], "USB_C_Receptacle_USB2.0")
        self.assertEqual(j1["rot"], 0.0)
        # courtyard is a TUPLE (min_x, min_y, max_x, max_y), and None for a
        # rotated part - both facts are load-bearing for geometry plugins.
        self.assertIsInstance(j1["courtyard"], tuple)
        self.assertEqual(j1["courtyard"], (-4.5, -5.27, 4.5, 2.0))

    def test_courtyard_is_none_for_rotated_footprints(self):
        """QUIRK (locked): rotation is not compensated for, so a rotated part
        silently loses its courtyard and downstream checks degrade."""
        rotated = parse_pcb(
            '(footprint "Device:R" (at 1 2 90) '
            '(property "Reference" "R1" (at 1 2 0)) '
            '(fp_line (start -1 -1) (end 1 -1) (layer "F.CrtYd")))'
        )
        self.assertEqual(rotated["footprints"][0]["rot"], 90.0)
        self.assertIsNone(rotated["footprints"][0]["courtyard"])

    def test_vbus_caps_counts_only_capacitors_tied_to_5v(self):
        """vbus_caps was moved into parse_pcb so review_protection stays pure
        (TASK-P9 bug-1). C4 is the only cap with a +5V pad in the fixture."""
        self.assertEqual(parsed_fixture()["vbus_caps"], 1)

    def test_pins_map_keys_are_ref_dot_pad(self):
        pins = parsed_fixture()["pins"]
        self.assertEqual(pins["J1.A6"], "USB_DP_CONN")
        self.assertEqual(pins["U1.14"], "USB_DP")
        self.assertEqual(pins["R7.2"], "USB_DP")

    def test_pad_without_a_net_is_recorded_as_none(self):
        """An unconnected pad must still appear in the map (as None) so that
        review_usb_routing can report it as a mismatch rather than skip it."""
        pcb = parse_pcb(
            '(footprint "Device:R" (at 1 2) '
            '(property "Reference" "R1" (at 1 2 0)) '
            '(pad "1" smd roundrect (at 1 2) (size 1 1) (layers "F.Cu")))'
        )
        self.assertEqual(pcb["pins"], {"R1.1": None})

    def test_conflicting_pad_nets_are_collapsed_to_a_sentinel(self):
        """Two pads with the same ref.number but different nets cannot be
        reconciled; the parse must not silently pick one."""
        text = (
            '(footprint "Device:R" (at 1 2) '
            '(property "Reference" "R1" (at 1 2 0)) '
            '(pad "1" smd roundrect (layers "F.Cu") (net "A"))'
            '(pad "1" smd roundrect (layers "F.Cu") (net "B")))'
        )
        self.assertEqual(parse_pcb(text)["pins"]["R1.1"], "<conflicting duplicate pad nets>")

    def test_empty_text_yields_empty_geometry_not_a_crash(self):
        pcb = parse_pcb("")
        self.assertIsNone(pcb["edge"])
        self.assertEqual(pcb["footprints"], [])
        self.assertEqual(pcb["vbus_caps"], 0)


# ---------------------------------------------------------------------------
# 待办#2 — per-review characterization (all 8, asserting current output)
# ---------------------------------------------------------------------------


class ReviewCharacterizationTests(unittest.TestCase):
    def setUp(self):
        self.pcb = parsed_fixture()
        self.text = load_fixture_pcb()
        self.sch = load_fixture_sch()

    def _review(self, verdict):
        self.assertEqual(set(verdict), {"id", "status", "evidence", "measured"})
        self.assertIn(verdict["status"], ("pass", "fail"))
        self.assertIsInstance(verdict["evidence"], str)
        self.assertTrue(verdict["evidence"].strip())
        return verdict

    def test_usb_edge_passes_with_courtyard_front_hugging_the_edge(self):
        verdict = self._review(review_usb_edge(self.pcb["footprints"], self.pcb["edge"]))
        self.assertEqual(verdict["id"], "USB_EDGE")
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"], {"courtyard_front_to_edge_mm": 0.03})

    def test_antenna_passes_with_clear_keepout_and_correct_orientation(self):
        verdict = self._review(review_antenna(self.pcb["footprints"], self.pcb["edge"]))
        self.assertEqual(verdict["id"], "ESP_ANTENNA")
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"]["keepout_intruders"], [])
        self.assertTrue(verdict["measured"]["antenna_facing_edge"])
        self.assertEqual(verdict["measured"]["edge_distance_mm"], 15.0)

    def test_ground_return_passes_on_via_count_and_zone(self):
        verdict = self._review(review_ground_return(self.pcb))
        self.assertEqual(verdict["id"], "GROUND_RETURN")
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"], {"via_count": 5, "zones": True})

    def test_decoupling_passes_and_records_every_ic(self):
        verdict = self._review(review_decoupling(self.pcb["footprints"]))
        self.assertEqual(verdict["id"], "DECOUPLING")
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"]["worst_distance_mm"], 3.9)
        self.assertEqual(
            [(f["ic"], f["nearest_cap"], f["boundary_distance_mm"])
             for f in verdict["measured"]["ics"]],
            [("U1", "C1", 2.3), ("U2", "C2", 3.75), ("U3", "C3", 3.9)],
        )

    def test_usb_routing_passes_with_small_skew(self):
        verdict = self._review(review_usb_routing(self.pcb["segments"], self.pcb["pins"]))
        self.assertEqual(verdict["id"], "USB_ROUTING")
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"]["logical_channel_lengths_mm"],
                         {"D+": 20.0, "D-": 19.7})
        self.assertEqual(verdict["measured"]["skew_mm"], 0.3)
        self.assertEqual(verdict["measured"]["endpoint_mismatches"], [])
        self.assertEqual(verdict["measured"]["missing_nets"], [])

    def test_thermal_passes_when_nearest_heat_source_is_far(self):
        verdict = self._review(review_thermal(self.pcb["footprints"]))
        self.assertEqual(verdict["id"], "SHT30_THERMAL")
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"]["nearest_heat_source_mm"], 36.0)

    def test_protection_passes_on_bulk_cap_and_reports_missing_tvs(self):
        verdict = self._review(review_protection(self.sch, self.pcb))
        self.assertEqual(verdict["id"], "PROTECTION")
        self.assertEqual(verdict["status"], "pass")
        # A missing TVS is reported but is only advisory on this board.
        self.assertEqual(verdict["measured"], {"vbus_caps": 1, "tvs": False})

    def test_assembly_passes_when_every_reference_is_silkscreened(self):
        verdict = self._review(review_assembly(self.pcb["footprints"], self.text))
        self.assertEqual(verdict["id"], "ASSEMBLY")
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"]["silk_missing"], [])
        self.assertEqual(verdict["measured"]["polarity_parts"], ["J1", "U2", "U3", "D1"])

    def test_all_eight_reviews_pass_on_the_fixture(self):
        """The fixture is deliberately a 'good' board; the golden report relies on it."""
        verdicts = [
            review_usb_edge(self.pcb["footprints"], self.pcb["edge"]),
            review_antenna(self.pcb["footprints"], self.pcb["edge"]),
            review_ground_return(self.pcb),
            review_decoupling(self.pcb["footprints"]),
            review_usb_routing(self.pcb["segments"], self.pcb["pins"]),
            review_thermal(self.pcb["footprints"]),
            review_protection(self.sch, self.pcb),
            review_assembly(self.pcb["footprints"], self.text),
        ]
        self.assertEqual([v["id"] for v in verdicts], list(REVIEW_IDS))
        self.assertEqual(review_exit_code(verdicts), 0)


# ---------------------------------------------------------------------------
# 待办#3 — golden end-to-end
# ---------------------------------------------------------------------------


def run_main(pcb_path: Path, sch_path: Path, out_path: Path,
             kicad_cli=None, render_errors=None):
    """Run board_review.main() against explicit paths with rendering stubbed out."""
    with mock.patch.object(board_review, "PCB_PATH", pcb_path), \
         mock.patch.object(board_review, "SCH_PATH", sch_path), \
         mock.patch.object(board_review, "OUT_PATH", out_path), \
         mock.patch.object(board_review, "find_kicad_cli", lambda: kicad_cli), \
         mock.patch.object(board_review, "render_board_views",
                           lambda *args, **kwargs: list(render_errors or [])):
        code = board_review.main()
    return code, json.loads(out_path.read_text(encoding="utf-8"))


def stable(report: dict) -> dict:
    """Report with the nondeterministic bits removed.

    - `generated_at` changes on every run.
    - `pcb` is `Path.relative_to(...)`, which emits backslashes on Windows and
      forward slashes elsewhere. Normalized here rather than in board_review.py,
      because changing the production path separator would rewrite the frozen
      M2 evidence (notes/m2-evidence-reset/ is off-limits for this task).
    """
    return {
        key: (value.replace("\\", "/") if key == "pcb" else value)
        for key, value in report.items()
        if key != "generated_at"
    }


class GoldenEndToEndTests(unittest.TestCase):
    def test_report_matches_frozen_golden(self):
        if not GOLDEN.is_file():
            self.fail(f"golden file missing: {GOLDEN} (regenerate with --regen)")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "board_review_auto.json"
            code, report = run_main(PCB_FIXTURE, SCH_FIXTURE, out)
        self.assertEqual(code, 1, "renderer is stubbed off, so main must fail closed")
        expected = stable(json.loads(GOLDEN.read_text(encoding="utf-8")))
        self.assertEqual(stable(report), expected)

    def test_report_schema_matches_the_real_board_evidence(self):
        """Same top-level shape as notes/.../board_review_auto.json, minus
        render_evidence (which only exists when rendering succeeds)."""
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "board_review_auto.json"
            _, report = run_main(PCB_FIXTURE, SCH_FIXTURE, out)
        self.assertEqual(set(report), {
            "generated_at", "pcb", "board_outline_mm", "footprint_count",
            "nets", "reviews", "summary", "note",
        })
        self.assertEqual(report["board_outline_mm"], [0.0, 0.0, 60.0, 40.0])
        self.assertEqual(report["footprint_count"], 11)
        self.assertEqual([r["id"] for r in report["reviews"]], list(REVIEW_IDS))
        self.assertEqual(report["summary"], {rid: "pass" for rid in REVIEW_IDS})

    def test_render_evidence_is_written_when_rendering_succeeds(self):
        """Covers the other main() branch without ever invoking kicad-cli."""
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            out = out_dir / "board_review_auto.json"
            (out_dir / "board_top.png").write_bytes(b"TOP")
            (out_dir / "board_bottom.png").write_bytes(b"BOTTOM")
            fake_cli = out_dir / "kicad-cli"
            fake_cli.write_bytes(b"")
            code, report = run_main(PCB_FIXTURE, SCH_FIXTURE, out,
                                    kicad_cli=fake_cli, render_errors=[])
            self.assertEqual(code, 0)
            self.assertIn("render_evidence", report)
            self.assertEqual(set(report["render_evidence"]), {
                "pcb_sha256", "top_png_sha256", "bottom_png_sha256", "rendered_at",
            })
            self.assertEqual(report["render_evidence"]["pcb_sha256"],
                             sha256_file(PCB_FIXTURE))

    def test_render_failure_is_reported_and_suppresses_render_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            out = out_dir / "board_review_auto.json"
            fake_cli = out_dir / "kicad-cli"
            fake_cli.write_bytes(b"")
            code, report = run_main(PCB_FIXTURE, SCH_FIXTURE, out,
                                    kicad_cli=fake_cli,
                                    render_errors=["kicad-cli render top failed (exit 1)"])
            self.assertEqual(code, 1)
            self.assertNotIn("render_evidence", report)

    def test_render_board_views_builds_the_documented_command(self):
        """Lock the CLI invocation shape; the render contract is part of the
        evidence chain (gates/gate_core.validate_render_evidence)."""
        calls = []

        def fake_run(command, **kwargs):
            calls.append(list(command))
            out = Path(command[command.index("-o") + 1])
            out.write_bytes(b"PNG")

            class _Done:
                returncode = 0
                stderr = b""
            return _Done()

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            with mock.patch.object(board_review.subprocess, "run", fake_run):
                errors = render_board_views(Path("kicad-cli"), PCB_FIXTURE, out_dir)

        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1:3], ["pcb", "render"])
        self.assertEqual(calls[0][calls[0].index("--side") + 1], "top")
        self.assertEqual(calls[1][calls[1].index("--side") + 1], "bottom")
        self.assertEqual(calls[0][calls[0].index("--width") + 1], "1600")


# ---------------------------------------------------------------------------
# 待办#5 — adversarial / blind-spot regression
# ---------------------------------------------------------------------------


def fp(ref, lib_id, x, y, courtyard=None):
    return {"ref": ref, "lib_id": lib_id, "x": x, "y": y, "rot": 0.0,
            "courtyard": courtyard}


class AdversarialTests(unittest.TestCase):
    def setUp(self):
        self.pcb = parsed_fixture()
        self.text = load_fixture_pcb()
        self.sch = load_fixture_sch()
        self.fps = self.pcb["footprints"]
        self.edge = self.pcb["edge"]

    # --- USB_EDGE ---------------------------------------------------------

    def test_usb_edge_fails_when_connector_sits_away_from_the_edge(self):
        moved = [dict(f) for f in self.fps]
        for f in moved:
            if "USB_C" in f["lib_id"]:
                f["y"] = 15.0  # courtyard front now ~9.7mm from the edge
        verdict = review_usb_edge(moved, self.edge)
        self.assertEqual(verdict["status"], "fail")
        self.assertGreater(verdict["measured"]["courtyard_front_to_edge_mm"], 1.0)

    def test_usb_edge_fails_closed_when_connector_missing(self):
        verdict = review_usb_edge([], self.edge)
        self.assertEqual(verdict["status"], "fail")
        self.assertIn("not found", verdict["evidence"])

    # --- ESP_ANTENNA ------------------------------------------------------

    def test_antenna_fails_when_a_part_invades_the_keepout(self):
        intruder = fp("C9", "Capacitor_SMD:C_0402_1005Metric", 30.0, 20.0)
        verdict = review_antenna(self.fps + [intruder], self.edge)
        self.assertEqual(verdict["status"], "fail")
        self.assertIn("C9", [ref for ref, _ in verdict["measured"]["keepout_intruders"]])

    def test_antenna_fails_when_module_is_rotated_away_from_the_edge(self):
        """Rotating the module 90deg flips the antenna inwards; the check tracks it."""
        rotated = [dict(f) for f in self.fps]
        for f in rotated:
            if "ESP32" in f["lib_id"]:
                f["rot"] = 90.0
        verdict = review_antenna(rotated, self.edge)
        self.assertFalse(verdict["measured"]["antenna_facing_edge"])

    # --- GROUND_RETURN ----------------------------------------------------

    def test_ground_return_fails_with_too_few_vias_or_no_zone(self):
        self.assertEqual(review_ground_return({"vias": 3, "has_zone": True})["status"], "fail")
        self.assertEqual(review_ground_return({"vias": 9, "has_zone": False})["status"], "fail")

    # --- DECOUPLING (the known blind spot) --------------------------------

    def test_decoupling_fails_when_a_cap_is_too_far(self):
        spread = [dict(f) for f in self.fps]
        for f in spread:
            if f["ref"] == "C3":
                f["y"] = 5.0  # now far from U3's courtyard
        verdict = review_decoupling(spread)
        self.assertEqual(verdict["status"], "fail")
        self.assertGreater(verdict["measured"]["worst_distance_mm"], 8.0)

    def test_decoupling_silently_drops_an_ic_whose_package_is_renamed(self):
        """BLIND SPOT (locked, not fixed): ICs are selected by lib_id keyword.
        Rename U3 from SOT-353 to SC-70-5 - the very package M2's replacement
        LDO actually uses - and U3 silently disappears from the check while the
        verdict stays 'pass'. This is the '换封装后检查项静默消失' class of bug.
        If this test ever starts failing, the keyword list was widened."""
        renamed = [dict(f) for f in self.fps]
        for f in renamed:
            if f["ref"] == "U3":
                f["lib_id"] = "Package_TO_SOT_SMD:SC-70-5"
        verdict = review_decoupling(renamed)
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual([f["ic"] for f in verdict["measured"]["ics"]], ["U1", "U2"])
        self.assertNotIn("U3", [f["ic"] for f in verdict["measured"]["ics"]])

    def test_decoupling_fails_closed_when_caps_or_ics_are_absent(self):
        self.assertEqual(review_decoupling([])["status"], "fail")
        self.assertEqual(review_decoupling([fp("U1", "RF_Module:ESP32-C3", 0, 0)])["status"], "fail")
        self.assertEqual(review_decoupling([fp("C1", "Capacitor_SMD:C_0402", 0, 0)])["status"], "fail")

    # --- USB_ROUTING ------------------------------------------------------

    def test_usb_routing_fails_on_excessive_skew(self):
        skewed = [dict(s) for s in self.pcb["segments"]]
        for s in skewed:
            if s["net"] == "USB_DM_CONN":
                s["x2"] = s["x1"] + 25.0  # D- now 27.1mm vs D+ 20.0mm
        verdict = review_usb_routing(skewed, self.pcb["pins"])
        self.assertEqual(verdict["status"], "fail")
        self.assertGreater(verdict["measured"]["skew_mm"], 1.0)

    def test_usb_routing_fails_when_a_net_is_never_routed(self):
        verdict = review_usb_routing([], self.pcb["pins"])
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(verdict["measured"]["missing_nets"],
                         ["USB_DM", "USB_DM_CONN", "USB_DP", "USB_DP_CONN"])

    def test_usb_routing_fails_when_a_pin_is_bound_to_the_wrong_net(self):
        pins = dict(self.pcb["pins"])
        pins["U1.14"] = "USB_DM"
        verdict = review_usb_routing(self.pcb["segments"], pins)
        self.assertEqual(verdict["status"], "fail")
        self.assertIn("U1.14", " ".join(verdict["measured"]["endpoint_mismatches"]))

    # --- SHT30_THERMAL ----------------------------------------------------

    def test_thermal_fails_when_a_heat_source_sits_too_close(self):
        hot = fp("D9", "LED_SMD:LED_0402_1005Metric", 14.0, 34.0)  # 2mm from U2
        verdict = review_thermal(self.fps + [hot])
        self.assertEqual(verdict["status"], "fail")
        self.assertLess(verdict["measured"]["nearest_heat_source_mm"], 10.0)

    def test_thermal_fails_closed_when_sensor_is_missing(self):
        self.assertEqual(review_thermal([])["status"], "fail")

    # --- PROTECTION -------------------------------------------------------

    def test_protection_fails_without_a_bulk_capacitor(self):
        no_bulk = dict(self.pcb)
        no_bulk["vbus_caps"] = 0
        verdict = review_protection(self.sch, no_bulk)
        self.assertEqual(verdict["status"], "fail")

    def test_protection_fails_closed_without_a_schematic(self):
        verdict = review_protection("", self.pcb)
        self.assertEqual(verdict["status"], "fail")
        self.assertIn("schematic not found", verdict["evidence"])

    def test_protection_uses_the_parsed_pcb_not_the_global_path(self):
        """REGRESSION for TASK-P9 bug-1: review_protection used to ignore its
        `pcb` argument and re-read the module-level PCB_PATH, so it returned a
        verdict for the wrong board. It must now be a function of its inputs."""
        other = dict(self.pcb)
        other["vbus_caps"] = 0
        with mock.patch.object(board_review, "PCB_PATH", PCB_FIXTURE):
            # The global points at a board that DOES have a bulk cap; the parsed
            # input says it does not. The verdict must follow the input.
            self.assertEqual(review_protection(self.sch, other)["status"], "fail")
            self.assertEqual(review_protection(self.sch, self.pcb)["status"], "pass")

    def test_protection_detects_tvs_when_present(self):
        sch = self.sch + '\n  (property "Value" "USBLC6-2SC6")\n'
        self.assertTrue(review_protection(sch, self.pcb)["measured"]["tvs"])

    # --- ASSEMBLY ---------------------------------------------------------

    def test_assembly_fails_when_a_reference_is_not_silkscreened(self):
        verdict = review_assembly(self.fps, "(kicad_pcb)")  # no reference strings
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(len(verdict["measured"]["silk_missing"]), len(self.fps))

    def test_assembly_fails_closed_on_an_empty_footprint_list(self):
        self.assertEqual(review_assembly([], self.text)["status"], "fail")


# ---------------------------------------------------------------------------
# golden maintenance
# ---------------------------------------------------------------------------


def regenerate_golden() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "board_review_auto.json"
        _, report = run_main(PCB_FIXTURE, SCH_FIXTURE, out)
    GOLDEN.write_text(json.dumps(stable(report), ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    print(f"regenerated {GOLDEN}")


if __name__ == "__main__":
    if "--regen" in sys.argv:
        regenerate_golden()
    else:
        unittest.main()
