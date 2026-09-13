"""Neutral host-granted placement slots derived ONLY from public information.

The grant pool is generated from the proposer-visible `source_utf8` alone:
paper size (sheet bounds), existing symbol positions (occupancy/spacing), and
fixed experiment-wide constants. It never reads private repair data, the good
board, expected coordinates, fault classes or case identity; it deliberately
does not inject the hidden correct repair position. The same algorithm runs for
every case.

Semantics: a `place_component` proposal is host-granted iff its (x_mil, y_mil)
pair appears in the package `placement_grants` list; the runner enforces this.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from notes.y4.source_parser import parse_schematic

MM_PER_MIL = 0.0254
PAPER_MM = {
    "A4": (297.0, 210.0),
    "A3": (420.0, 297.0),
    "A5": (210.0, 148.0),
    "A2": (594.0, 420.0),
    "Letter": (279.4, 215.9),
}
MARGIN_MM = 10.16
SPACING_MM = 10.16
CLEARANCE_MM = 5.08
MIN_SLOTS = 32
MAX_SLOTS = 2048


class GrantError(ValueError):
    pass


def generate_grants(source_text: str) -> Dict[str, Any]:
    """Deterministic neutral slot pool for one public source."""
    paper_match = re.search(r'\(paper\s+"([^"]+)"', source_text)
    if not paper_match:
        raise GrantError("schematic has no paper size")
    paper = paper_match.group(1)
    if paper not in PAPER_MM:
        raise GrantError("unsupported paper size: %s" % paper)
    width_mm, height_mm = PAPER_MM[paper]

    schematic = parse_schematic(source_text)
    occupied = [(s.x, s.y) for s in schematic.symbols]

    slots: List[Tuple[int, int]] = []
    x = MARGIN_MM
    while x <= width_mm - MARGIN_MM:
        y = MARGIN_MM
        while y <= height_mm - MARGIN_MM:
            if all((x - px) ** 2 + (y - py) ** 2 >= CLEARANCE_MM ** 2
                   for px, py in occupied):
                slots.append((round(x / MM_PER_MIL), round(y / MM_PER_MIL)))
            y += SPACING_MM
        x += SPACING_MM

    slots = sorted(set(slots), key=lambda p: (p[1], p[0]))
    if len(slots) < MIN_SLOTS:
        raise GrantError("insufficient placement capacity: %d slots" % len(slots))
    if len(slots) > MAX_SLOTS:
        raise GrantError("placement capacity exceeds policy cap")
    return {
        "paper": paper,
        "spacing_mil": round(SPACING_MM / MM_PER_MIL),
        "clearance_mil": round(CLEARANCE_MM / MM_PER_MIL),
        "margin_mil": round(MARGIN_MM / MM_PER_MIL),
        "slot_count": len(slots),
        "slots": [{"x_mil": sx, "y_mil": sy} for sx, sy in slots],
    }


def canonical_grants_bytes(grants: Dict[str, Any]) -> bytes:
    return json.dumps(grants, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def slot_set(grants: List[Dict[str, int]]) -> set:
    return {(int(s["x_mil"]), int(s["y_mil"])) for s in grants}


def validate_grants(grants: Any) -> List[Dict[str, int]]:
    """Closed validation used by the runner; returns the canonical slot list."""
    if not isinstance(grants, list) or not grants:
        raise GrantError("placement_grants must be a nonempty list")
    if len(grants) > MAX_SLOTS:
        raise GrantError("placement_grants exceeds policy cap")
    seen = set()
    slots = []
    for index, slot in enumerate(grants):
        if not isinstance(slot, dict) or set(slot) != {"x_mil", "y_mil"}:
            raise GrantError("placement_grants[%d] must hold x_mil and y_mil" % index)
        pair = (slot["x_mil"], slot["y_mil"])
        if any(type(v) is not int or not (0 <= v <= 1000000) for v in pair):
            raise GrantError("placement_grants[%d] coordinates must be integer mil" % index)
        if pair in seen:
            raise GrantError("placement_grants[%d] duplicates a slot" % index)
        seen.add(pair)
        slots.append({"x_mil": pair[0], "y_mil": pair[1]})
    return slots


def nearest_slot(grants: List[Dict[str, int]], x_mm: float, y_mm: float) -> Dict[str, int]:
    """Deterministic public choice: the granted slot nearest a public anchor."""
    return min(grants, key=lambda s: ((s["x_mil"] * MM_PER_MIL - x_mm) ** 2
                                      + (s["y_mil"] * MM_PER_MIL - y_mm) ** 2,
                                      s["y_mil"], s["x_mil"]))
