"""Characterization / golden / fail-closed regression tests for
tools/board_review.py (TASK-P9).

History: the first round of this file froze *quirks* (negative off-board
distance still passing, rotated courtyard silently dropped, keyword-based IC
selection). The follow-up board-review fix removed those quirks; the tests
here now lock the FIXED, fail-closed behaviour so any regression back to the
old semantics becomes a visible diff:

- USB connector outside the board outline must FAIL with a non-negative
  outside distance (never a negative "pass").
- Rotated footprints keep a correctly transformed courtyard; an unmeasurable
  courtyard fails closed instead of degrading to a centroid distance.
- ICs / heat sources / polarity-sensitive parts are selected by the explicit
  review-contract ref sets (EXPECTED_IC_REFS / HEAT_SOURCE_REFS /
  POLARITY_REFS) — package keywords are gone, so renaming U3's package to
  SC-70-5 can no longer make it vanish from DECOUPLING / SHT30_THERMAL /
  ASSEMBLY.
- A decoupling cap must share a power net with its IC; an unrelated cap
  cannot impersonate one.
- ASSEMBLY verifies each Reference property sits on F.SilkS/B.SilkS and is
  not hidden — a global string search is no longer enough.

Conventions:
- `Characterization*` classes assert the current (fixed) behaviour.
- `Adversarial*` / `FailClosedRegression*` lock the failure paths.
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
    EXPECTED_IC_REFS,
    HEAT_SOURCE_REFS,
    POLARITY_REFS,
    boundary_distance,
    dist,
    edge_distance,
    find_kicad_cli,
    inside_edge,
    parse_pcb,
    point_to_rect_distance,
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
# pure-function characterization
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

    def test_edge_distance_is_signed_and_callers_must_check_inside_first(self):
        """edge_distance stays a signed helper (negative outside the outline);
        the FAIL-CLOSED contract lives in the callers, which must branch on
        inside_edge / point_to_rect_distance instead of using abs()."""
        edge = (0.0, 0.0, 60.0, 40.0)
        self.assertAlmostEqual(edge_distance({"x": -3.0, "y": 20.0}, edge), -3.0)
        self.assertFalse(inside_edge(-3.0, 20.0, edge))
        self.assertTrue(inside_edge(30.0, 20.0, edge))

    def test_point_to_rect_distance_is_non_negative_everywhere(self):
        edge = (0.0, 0.0, 60.0, 40.0)
        self.assertAlmostEqual(point_to_rect_distance(-3.0, 20.0, edge), 3.0)
        self.assertAlmostEqual(point_to_rect_distance(65.0, 20.0, edge), 5.0)
        # diagonal outside: distance to the nearest corner
        self.assertAlmostEqual(point_to_rect_distance(-3.0, 44.0, edge), 5.0)
        # inside → 0
        self.assertAlmostEqual(point_to_rect_distance(30.0, 20.0, edge), 0.0)

    def test_boundary_distance_measures_gap_outside_courtyard(self):
        ic = {"x": 30.0, "y": 15.0, "courtyard": (-9.0, -12.7, 9.0, 12.7)}
        # courtyard in board coords: x 21..39, y 2.3..27.7 → cap at y=30 is 2.3mm out
        self.assertAlmostEqual(boundary_distance({"x": 30.0, "y": 30.0}, ic), 2.3, places=6)

    def test_boundary_distance_is_zero_inside_courtyard(self):
        ic = {"x": 30.0, "y": 15.0, "courtyard": (-9.0, -12.7, 9.0, 12.7)}
        self.assertAlmostEqual(boundary_distance({"x": 30.0, "y": 15.0}, ic), 0.0)

    def test_boundary_distance_is_unmeasurable_without_courtyard(self):
        """FIXED (was: silently degraded to centroid distance). None means
        'cannot measure reliably' and callers must fail closed with a reason."""
        ic = {"x": 30.0, "y": 15.0, "courtyard": None}
        self.assertIsNone(boundary_distance({"x": 30.0, "y": 25.0}, ic))

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
        """Locked, and it must stay this way: an empty review list is a FAIL,
        not a pass. Silently dropping every review must never read as OK."""
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
# parse_pcb characterization
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
                         ["+3V3", "+5V", "GND", "USB_DM", "USB_DM_CONN", "USB_DP", "USB_DP_CONN"])

    def test_footprint_record_shape_is_stable(self):
        """Any plugin consuming footprints depends on exactly these keys."""
        j1 = parsed_fixture()["footprints"][0]
        self.assertEqual(set(j1), {"ref", "lib_id", "x", "y", "rot", "courtyard",
                                   "ref_layer", "ref_hidden"})
        self.assertEqual(j1["ref"], "J1")
        self.assertEqual(j1["lib_id"], "USB_C_Receptacle_USB2.0")
        self.assertEqual(j1["rot"], 0.0)
        # courtyard is a TUPLE (min_x, min_y, max_x, max_y) in footprint-local
        # coordinates (already rotation-compensated), and None only when the
        # footprint carries no F.CrtYd lines at all.
        self.assertIsInstance(j1["courtyard"], tuple)
        self.assertEqual(j1["courtyard"], (-4.5, -5.27, 4.5, 2.0))
        self.assertEqual(j1["ref_layer"], "F.SilkS")
        self.assertFalse(j1["ref_hidden"])

    def test_courtyard_is_rotated_not_dropped(self):
        """FIXED (was: rot != 0 silently dropped the courtyard, degrading every
        downstream boundary check). An asymmetric courtyard rotated 90deg must
        come back as the rotated bbox: (x,y) -> (-y, x)."""
        rotated = parse_pcb(
            '(footprint "Test:ASYM" (at 1 2 90) '
            '(property "Reference" "X1" (at 1 2 0) (layer "F.SilkS")) '
            '(fp_line (start -2 -1) (end 1 -1) (layer "F.CrtYd"))'
            '(fp_line (start 1 -1) (end 1 1) (layer "F.CrtYd"))'
            '(fp_line (start 1 1) (end -2 1) (layer "F.CrtYd"))'
            '(fp_line (start -2 1) (end -2 -1) (layer "F.CrtYd")))'
        )
        fp_rec = rotated["footprints"][0]
        self.assertEqual(fp_rec["rot"], 90.0)
        for actual, expected in zip(fp_rec["courtyard"], (-1.0, -2.0, 1.0, 1.0)):
            self.assertAlmostEqual(actual, expected, places=9)

    def test_courtyard_is_none_only_when_no_crtyd_lines_exist(self):
        parsed = parse_pcb(
            '(footprint "Test:PLAIN" (at 1 2) '
            '(property "Reference" "X2" (at 1 2 0) (layer "F.SilkS")))'
        )
        self.assertIsNone(parsed["footprints"][0]["courtyard"])

    def test_reference_layer_and_hide_are_extracted(self):
        parsed = parse_pcb(
            '(footprint "Test:HIDDEN" (at 1 2) '
            '(property "Reference" "X3" (at 1 2 0) (layer "F.Fab") (hide yes)) '
            '(property "Value" "V" (at 1 3 0) (layer "F.Fab")))'
        )
        fp_rec = parsed["footprints"][0]
        self.assertEqual(fp_rec["ref_layer"], "F.Fab")
        self.assertTrue(fp_rec["ref_hidden"])

    def test_vbus_caps_counts_only_capacitors_tied_to_5v(self):
        """vbus_caps lives in parse_pcb so review_protection stays pure.
        C4 is the only cap with a +5V pad in the fixture."""
        self.assertEqual(parsed_fixture()["vbus_caps"], 1)

    def test_pins_map_keys_are_ref_dot_pad(self):
        pins = parsed_fixture()["pins"]
        self.assertEqual(pins["J1.A6"], "USB_DP_CONN")
        self.assertEqual(pins["U1.14"], "USB_DP")
        self.assertEqual(pins["R7.2"], "USB_DP")
        self.assertEqual(pins["C1.1"], "+3V3")
        self.assertEqual(pins["U3.VIN"], "+5V")

    def test_pad_without_a_net_is_recorded_as_none(self):
        """An unconnected pad must still appear in the map (as None) so that
        review_usb_routing can report it as a mismatch rather than skip it."""
        pcb = parse_pcb(
            '(footprint "Device:R" (at 1 2) '
            '(property "Reference" "R1" (at 1 2 0) (layer "F.SilkS")) '
            '(pad "1" smd roundrect (at 1 2) (size 1 1) (layers "F.Cu")))'
        )
        self.assertEqual(pcb["pins"], {"R1.1": None})

    def test_conflicting_pad_nets_are_collapsed_to_a_sentinel(self):
        """Two pads with the same ref.number but different nets cannot be
        reconciled; the parse must not silently pick one."""
        text = (
            '(footprint "Device:R" (at 1 2) '
            '(property "Reference" "R1" (at 1 2 0) (layer "F.SilkS")) '
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
# per-review characterization (all 8, asserting current output)
# ---------------------------------------------------------------------------


class ReviewCharacterizationTests(unittest.TestCase):
    def setUp(self):
        self.pcb = parsed_fixture()
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

    def test_decoupling_passes_and_records_every_expected_ic(self):
        verdict = self._review(review_decoupling(self.pcb["footprints"], self.pcb["pins"]))
        self.assertEqual(verdict["id"], "DECOUPLING")
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"]["worst_distance_mm"], 3.9)
        self.assertEqual(verdict["measured"]["problems"], [])
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

    def test_assembly_passes_when_every_reference_is_on_visible_silkscreen(self):
        verdict = self._review(review_assembly(self.pcb["footprints"]))
        self.assertEqual(verdict["id"], "ASSEMBLY")
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"]["silk_missing"], [])
        self.assertEqual(verdict["measured"]["polarity_parts"], ["J1", "U2", "U3", "D1"])
        self.assertEqual(verdict["measured"]["polarity_missing"], [])

    def test_all_eight_reviews_pass_on_the_fixture(self):
        """The fixture is deliberately a 'good' board; the golden report relies on it."""
        verdicts = [
            review_usb_edge(self.pcb["footprints"], self.pcb["edge"]),
            review_antenna(self.pcb["footprints"], self.pcb["edge"]),
            review_ground_return(self.pcb),
            review_decoupling(self.pcb["footprints"], self.pcb["pins"]),
            review_usb_routing(self.pcb["segments"], self.pcb["pins"]),
            review_thermal(self.pcb["footprints"]),
            review_protection(self.sch, self.pcb),
            review_assembly(self.pcb["footprints"]),
        ]
        self.assertEqual([v["id"] for v in verdicts], list(REVIEW_IDS))
        self.assertEqual(review_exit_code(verdicts), 0)


# ---------------------------------------------------------------------------
# golden end-to-end
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
            "algorithm_revision", "generated_at", "pcb", "board_outline_mm",
            "footprint_count", "nets", "reviews", "summary", "note",
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
# adversarial / fail-closed regression
# ---------------------------------------------------------------------------


def fp(ref, lib_id, x, y, courtyard=None):
    return {"ref": ref, "lib_id": lib_id, "x": x, "y": y, "rot": 0.0,
            "courtyard": courtyard}


class AdversarialTests(unittest.TestCase):
    def setUp(self):
        self.pcb = parsed_fixture()
        self.sch = load_fixture_sch()
        self.fps = self.pcb["footprints"]
        self.edge = self.pcb["edge"]
        self.pins = self.pcb["pins"]

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

    def test_usb_without_courtyard_inside_the_outline_is_measured_non_negative(self):
        near = [fp("J1", "Connector_USB:USB_C_Receptacle_USB2.0", 0.5, 20.0)]
        verdict = review_usb_edge(near, self.edge)
        self.assertEqual(verdict["status"], "pass")
        self.assertEqual(verdict["measured"], {"centroid_to_edge_mm": 0.5})

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
            if f["ref"] == "U1":
                f["rot"] = 90.0
        verdict = review_antenna(rotated, self.edge)
        self.assertFalse(verdict["measured"]["antenna_facing_edge"])

    # --- GROUND_RETURN ----------------------------------------------------

    def test_ground_return_fails_with_too_few_vias_or_no_zone(self):
        self.assertEqual(review_ground_return({"vias": 3, "has_zone": True})["status"], "fail")
        self.assertEqual(review_ground_return({"vias": 9, "has_zone": False})["status"], "fail")

    # --- DECOUPLING -------------------------------------------------------

    def test_decoupling_fails_when_a_cap_is_too_far(self):
        spread = [dict(f) for f in self.fps]
        for f in spread:
            if f["ref"] == "C3":
                f["y"] = 5.0  # now far from U3's courtyard
        verdict = review_decoupling(spread, self.pins)
        self.assertEqual(verdict["status"], "fail")
        self.assertGreater(verdict["measured"]["worst_distance_mm"], 8.0)

    def test_decoupling_fails_closed_when_caps_are_absent(self):
        self.assertEqual(review_decoupling([], {})["status"], "fail")
        self.assertEqual(
            review_decoupling([fp("C1", "Capacitor_SMD:C_0402", 0, 0)], {})["status"],
            "fail")

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
        moved = [dict(f) for f in self.fps]
        for f in moved:
            if f["ref"] == "U3":
                f["x"], f["y"] = 14.0, 34.0  # LDO dragged next to the SHT30
        verdict = review_thermal(moved)
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

    def test_assembly_fails_closed_on_an_empty_footprint_list(self):
        self.assertEqual(review_assembly([])["status"], "fail")


class FailClosedRegressionTests(unittest.TestCase):
    """Negative tests for the TASK-P9-round-2 mandated fixes. Each one used to
    be a silent pass; they must stay fail-closed."""

    def setUp(self):
        self.pcb = parsed_fixture()
        self.fps = self.pcb["footprints"]
        self.edge = self.pcb["edge"]
        self.pins = self.pcb["pins"]

    # --- 1. USB outside the outline ----------------------------------------

    def test_usb_without_courtyard_outside_the_outline_fails_closed(self):
        """Was: edge_distance went negative and `d <= MAX` still passed.
        Now: inside/outside is decided explicitly, the distance is the
        non-negative gap to the outline, and the verdict is FAIL."""
        outside = [fp("J1", "Connector_USB:USB_C_Receptacle_USB2.0", -3.0, 20.0)]
        verdict = review_usb_edge(outside, self.edge)
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(verdict["measured"], {"centroid_outside_outline_mm": 3.0})
        self.assertIn("板框之外", verdict["evidence"])

    # --- 2. rotated courtyard ----------------------------------------------

    def test_rotated_courtyard_drives_boundary_distance(self):
        """The rotated bbox (fixture: (-1,-2,1,1) after 90deg) must be what the
        boundary distance is measured against — never a centroid fallback."""
        ic = {"ref": "X1", "lib_id": "Test:ASYM", "x": 0.0, "y": 0.0, "rot": 90.0,
              "courtyard": (-1.0, -2.0, 1.0, 1.0)}
        self.assertAlmostEqual(boundary_distance({"x": 0.0, "y": 3.0}, ic), 2.0)
        self.assertAlmostEqual(boundary_distance({"x": 2.0, "y": 0.0}, ic), 1.0)
        self.assertAlmostEqual(boundary_distance({"x": 0.0, "y": 0.0}, ic), 0.0)

    def test_decoupling_fails_closed_when_courtyard_is_unmeasurable(self):
        """Stripping U3's courtyard must FAIL the review with a reason, not
        quietly degrade to centroid distances."""
        stripped = [dict(f) for f in self.fps]
        for f in stripped:
            if f["ref"] == "U3":
                f["courtyard"] = None
        verdict = review_decoupling(stripped, self.pins)
        self.assertEqual(verdict["status"], "fail")
        self.assertTrue(any("U3" in p and "courtyard" in p
                            for p in verdict["measured"]["problems"]),
                        verdict["measured"]["problems"])

    # --- 3./4. role sets instead of keywords --------------------------------

    def test_u3_renamed_to_sc70_5_stays_in_every_review(self):
        """Mandated regression: package rename must not drop U3 from
        DECOUPLING, SHT30_THERMAL heat sources, or ASSEMBLY polarity parts."""
        renamed = [dict(f) for f in self.fps]
        for f in renamed:
            if f["ref"] == "U3":
                f["lib_id"] = "Package_TO_SOT_SMD:SC-70-5"
        dec = review_decoupling(renamed, self.pins)
        self.assertEqual(dec["status"], "pass", dec["evidence"])
        self.assertIn("U3", [f["ic"] for f in dec["measured"]["ics"]])
        therm = review_thermal(renamed)
        self.assertEqual(therm["status"], "pass", therm["evidence"])
        self.assertIn("U3", therm["evidence"])
        asm = review_assembly(renamed)
        self.assertEqual(asm["status"], "pass", asm["evidence"])
        self.assertIn("U3", asm["measured"]["polarity_parts"])

    def test_role_sets_are_the_contract_not_keywords(self):
        """Lock the exact review-contract ref sets; widening them is a
        deliberate, reviewable change."""
        self.assertEqual(EXPECTED_IC_REFS, ("U1", "U2", "U3"))
        self.assertEqual(HEAT_SOURCE_REFS, ("U3", "J1", "D1"))
        self.assertEqual(POLARITY_REFS, ("J1", "U2", "U3", "D1"))

    # --- 5. missing expected IC / impersonating cap --------------------------

    def test_decoupling_fails_when_an_expected_ic_is_missing(self):
        gone = [f for f in self.fps if f["ref"] != "U3"]
        verdict = review_decoupling(gone, self.pins)
        self.assertEqual(verdict["status"], "fail")
        self.assertTrue(any("U3" in p and "未在板上找到" in p
                            for p in verdict["measured"]["problems"]),
                        verdict["measured"]["problems"])

    def test_decoupling_rejects_caps_on_unrelated_nets(self):
        """An unrelated capacitor must not impersonate the decoupling cap of a
        power net it is not connected to."""
        isolated_pins = {
            "U1.VDD": "+3V3", "U2.VDD": "+3V3",
            "U3.VIN": "+5V", "U3.VOUT": "+3V3",
            "C1.1": "LED_A", "C2.1": "LED_A",
            "C3.1": "LED_A", "C4.1": "LED_A",
        }
        verdict = review_decoupling(self.fps, isolated_pins)
        self.assertEqual(verdict["status"], "fail")
        problems = verdict["measured"]["problems"]
        for ref in ("U1", "U2", "U3"):
            self.assertTrue(any(p.startswith(ref) and "电源网络" in p for p in problems),
                            problems)

    # --- 5b. missing expected heat source ------------------------------------

    def test_thermal_fails_when_an_expected_heat_source_is_missing(self):
        gone = [f for f in self.fps if f["ref"] != "D1"]
        verdict = review_thermal(gone)
        self.assertEqual(verdict["status"], "fail")
        self.assertIn("D1", verdict["evidence"])
        self.assertIsNone(verdict["measured"]["nearest_heat_source_mm"])

    # --- 6. silkscreen layer + hidden ----------------------------------------

    def test_assembly_fails_when_a_reference_is_hidden(self):
        hidden = [dict(f) for f in self.fps]
        for f in hidden:
            if f["ref"] == "U3":
                f["ref_hidden"] = True
        verdict = review_assembly(hidden)
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(verdict["measured"]["silk_missing"], ["U3"])

    def test_assembly_fails_when_a_reference_is_not_on_a_silkscreen_layer(self):
        """A reference string existing somewhere in the file is no longer
        enough — the property itself must sit on F.SilkS/B.SilkS."""
        moved = [dict(f) for f in self.fps]
        for f in moved:
            if f["ref"] == "D1":
                f["ref_layer"] = "F.Fab"
        verdict = review_assembly(moved)
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(verdict["measured"]["silk_missing"], ["D1"])

    def test_assembly_fails_when_an_expected_polarity_part_is_missing(self):
        gone = [f for f in self.fps if f["ref"] != "J1"]
        verdict = review_assembly(gone)
        self.assertEqual(verdict["status"], "fail")
        self.assertEqual(verdict["measured"]["polarity_missing"], ["J1"])

    # --- 7. ESP32 rotation ----------------------------------------------------

    def test_antenna_rot180_near_top_edge_is_facing_inwards(self):
        """Was: rot=0 and rot=180 were treated identically, so a module near
        the top edge rotated 180deg (antenna at local -Y now pointing +Y,
        into the board) was misread as facing outward. Now the direction
        vector decides, and the verdict must be FAIL."""
        rotated = [dict(f) for f in self.fps]
        for f in rotated:
            if f["ref"] == "U1":
                f["rot"] = 180.0
        verdict = review_antenna(rotated, self.edge)
        self.assertFalse(verdict["measured"]["antenna_facing_edge"])
        self.assertEqual(verdict["status"], "fail")

    def test_antenna_rot180_near_bottom_edge_is_facing_outwards(self):
        """Control case for the fix: the same rotation is correct when the
        module sits near the bottom edge."""
        rotated = [dict(f) for f in self.fps]
        for f in rotated:
            if f["ref"] == "U1":
                f["rot"] = 180.0
                f["y"] = 30.0
        verdict = review_antenna(rotated, self.edge)
        self.assertTrue(verdict["measured"]["antenna_facing_edge"])


class OffBoardFailClosedTests(unittest.TestCase):
    """P11-B repro regressions: off-board parts must FAIL, never PASS.

    Both bugs reproduced before the fix:
    - a courtyard-carrying USB at x=-5 still returned PASS (only the front-Y
      distance was checked, never the X direction or outline containment);
    - an antenna module at y=-1 returned edge_distance=-1.0 and still PASSed
      because review_antenna never checked the module was on the board.
    """

    def setUp(self):
        self.pcb = parsed_fixture()
        self.fps = self.pcb["footprints"]
        self.edge = self.pcb["edge"]

    # --- issue 1: USB with courtyard outside the outline --------------------

    def test_usb_with_courtyard_left_of_the_outline_fails(self):
        # reviewer repro: board 0..60 x 0..40, J1 x=-5 y=0.5
        off = [fp("J1", "Connector_USB:USB_C_Receptacle_USB2.0",
                  -5.0, 0.5, courtyard=(-1.0, -0.4, 1.0, 0.4))]
        verdict = review_usb_edge(off, self.edge)
        self.assertEqual(verdict["status"], "fail")

    def test_usb_with_courtyard_overhanging_the_right_edge_fails(self):
        off = [fp("J1", "Connector_USB:USB_C_Receptacle_USB2.0",
                  59.5, 5.3, courtyard=(-4.5, -5.27, 4.5, 2.0))]
        verdict = review_usb_edge(off, self.edge)
        self.assertEqual(verdict["status"], "fail")

    def test_usb_with_courtyard_protruding_over_the_top_edge_fails(self):
        off = [fp("J1", "Connector_USB:USB_C_Receptacle_USB2.0",
                  45.0, 0.2, courtyard=(-4.5, -5.27, 4.5, 2.0))]
        verdict = review_usb_edge(off, self.edge)
        self.assertEqual(verdict["status"], "fail")

    def test_usb_with_courtyard_fully_inside_still_passes(self):
        verdict = review_usb_edge(self.fps, self.edge)
        self.assertEqual(verdict["status"], "pass")

    # --- issue 2: antenna module outside the outline ------------------------

    def test_antenna_module_outside_any_edge_fails(self):
        positions = [(-1.0, 18.0), (61.0, 18.0), (12.0, -1.0), (12.0, 41.0)]
        for x, y in positions:
            with self.subTest(position=(x, y)):
                moved = [dict(f) for f in self.fps]
                for f in moved:
                    if f["ref"] == "U1":
                        f["x"], f["y"] = x, y
                verdict = review_antenna(moved, self.edge)
                self.assertEqual(verdict["status"], "fail")

    def test_antenna_module_inside_keeps_orientation_verdicts(self):
        # rot=0 near the top edge stays outward-facing (existing behaviour kept)
        verdict = review_antenna(self.fps, self.edge)
        self.assertEqual(verdict["status"], "pass")
        self.assertTrue(verdict["measured"]["antenna_facing_edge"])


# ---------------------------------------------------------------------------
# golden maintenance
# ---------------------------------------------------------------------------


def regenerate_golden() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "board_review_auto.json"
        _, report = run_main(PCB_FIXTURE, SCH_FIXTURE, out)
    # Path.write_text(newline=...) needs Python 3.10+; the repo runs on 3.9.
    with GOLDEN.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(stable(report), ensure_ascii=False, indent=2) + "\n")
    print(f"regenerated {GOLDEN}")


if __name__ == "__main__":
    if "--regen" in sys.argv:
        regenerate_golden()
    else:
        unittest.main()
