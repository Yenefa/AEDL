"""Deterministically lengthen M2 USB D- after the locked freerouting pass.

The router leaves both logical USB channels connected and DRC-clean except for
length skew.  Replace one open-area B.Cu segment with a bounded two-segment
detour.  The exact target, net, layer, and added length all fail closed.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys


ORIGINAL_START = (38.8409, 4.7841)
ORIGINAL_END = (41.3371, 4.7841)
POLISH_MIDPOINT = (40.0890, 3.3841)
UNSAFE_LEGACY_MIDPOINT = (40.0890, 6.1841)
TARGET_NET = "USB_DM_CONN"
MATCH_TOLERANCE_MM = 0.02


def distance_mm(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def same_segment(start, end, expected_start=ORIGINAL_START, expected_end=ORIGINAL_END):
    """Return true for the target segment in either orientation."""
    direct = distance_mm(start, expected_start) <= MATCH_TOLERANCE_MM and \
        distance_mm(end, expected_end) <= MATCH_TOLERANCE_MM
    reverse = distance_mm(start, expected_end) <= MATCH_TOLERANCE_MM and \
        distance_mm(end, expected_start) <= MATCH_TOLERANCE_MM
    return direct or reverse


def added_length_mm(start, end, midpoint):
    return distance_mm(start, midpoint) + distance_mm(midpoint, end) - distance_mm(start, end)


def _point_mm(pcbnew, vector):
    return pcbnew.ToMM(vector.x), pcbnew.ToMM(vector.y)


def _new_track(board, pcbnew, net, layer, width, start, end):
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(net)
    track.SetLayer(layer)
    track.SetWidth(width)
    track.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(start[0]), pcbnew.FromMM(start[1])))
    track.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(end[0]), pcbnew.FromMM(end[1])))
    board.Add(track)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.root.resolve()
    board_path = root / "src" / "hardware" / "m2-board" / "m2_board.kicad_pcb"

    import pcbnew

    board = pcbnew.LoadBoard(str(board_path))
    target = []
    polished_parts = {"start_mid": [], "mid_end": []}
    unsafe_parts = {"start_mid": [], "mid_end": []}
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        if item.GetNetname() != TARGET_NET or item.GetLayer() != pcbnew.B_Cu:
            continue
        start = _point_mm(pcbnew, item.GetStart())
        end = _point_mm(pcbnew, item.GetEnd())
        if same_segment(start, end):
            target.append(item)
        if same_segment(start, end, ORIGINAL_START, POLISH_MIDPOINT):
            polished_parts["start_mid"].append(item)
        if same_segment(start, end, POLISH_MIDPOINT, ORIGINAL_END):
            polished_parts["mid_end"].append(item)
        if same_segment(start, end, ORIGINAL_START, UNSAFE_LEGACY_MIDPOINT):
            unsafe_parts["start_mid"].append(item)
        if same_segment(start, end, UNSAFE_LEGACY_MIDPOINT, ORIGINAL_END):
            unsafe_parts["mid_end"].append(item)

    polished_counts = {name: len(items) for name, items in polished_parts.items()}
    unsafe_counts = {name: len(items) for name, items in unsafe_parts.items()}
    if len(target) == 0 and polished_counts == {"start_mid": 1, "mid_end": 1} and not any(unsafe_counts.values()):
        print("usb_skew_polish=already_applied")
        return 0
    if len(target) == 1 and not any(polished_counts.values()) and not any(unsafe_counts.values()):
        originals = target
    elif len(target) == 0 and not any(polished_counts.values()) and unsafe_counts == {"start_mid": 1, "mid_end": 1}:
        originals = unsafe_parts["start_mid"] + unsafe_parts["mid_end"]
    else:
        raise ValueError(
            "expected one pristine or one known unsafe target; "
            f"target={len(target)} polished={polished_counts} unsafe={unsafe_counts}"
        )

    added = added_length_mm(ORIGINAL_START, ORIGINAL_END, POLISH_MIDPOINT)
    if not 1.2 < added < 1.3:
        raise ValueError(f"polish added length outside audited bound: {added:.4f}mm")

    original = originals[0]
    width = original.GetWidth()
    net = original.GetNet()
    layer = original.GetLayer()
    for item in originals:
        board.Remove(item)
    _new_track(board, pcbnew, net, layer, width, ORIGINAL_START, POLISH_MIDPOINT)
    _new_track(board, pcbnew, net, layer, width, POLISH_MIDPOINT, ORIGINAL_END)
    saved = pcbnew.SaveBoard(str(board_path), board)
    print(f"usb_skew_polish_saved={saved} added_length_mm={added:.4f}")
    return 0 if saved else 5


if __name__ == "__main__":
    sys.exit(main())
