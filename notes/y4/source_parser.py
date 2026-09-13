"""CANDIDATE — source parser for y4-public.v2 `source_utf8` (D compatibility work).

Proves that operands classified RAW_SOURCE_PARSEABLE in the G6 host-only audit
are mechanically extractable from the public package: existing object UUIDs
(wires/labels/symbols), schematic geometry (wire endpoints/midpoints, label and
symbol positions) and designator gaps for unplaced parts. This is tooling, not a
D baseline, and it never reads private data: it only consumes exactly what a
proposer receives in the public package.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

_UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'


@dataclass
class Wire:
    uuid: str
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def mid(self) -> Tuple[float, float]:
        return (round((self.x1 + self.x2) / 2, 4), round((self.y1 + self.y2) / 2, 4))


@dataclass
class Label:
    name: str
    x: float
    y: float
    uuid: Optional[str]


@dataclass
class Symbol:
    ref: Optional[str]
    lib_id: str
    x: float
    y: float
    uuid: Optional[str]
    pins: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class Schematic:
    wires: List[Wire]
    labels: List[Label]
    symbols: List[Symbol]

    def refs(self) -> List[str]:
        return [s.ref for s in self.symbols if s.ref]

    def wire_midpoints(self) -> List[Tuple[float, float]]:
        return [w.mid for w in self.wires]

    def wire_by_uuid(self, uuid: str) -> Optional[Wire]:
        return next((w for w in self.wires if w.uuid == uuid), None)

    def labels_at(self, x: float, y: float, tol: float = 0.001) -> List[Label]:
        return [l for l in self.labels if abs(l.x - x) <= tol and abs(l.y - y) <= tol]

    def label_by_uuid(self, uuid: str) -> Optional[Label]:
        return next((l for l in self.labels if l.uuid == uuid), None)

    def _used_designators(self, prefix: str) -> List[int]:
        used = []
        for ref in self.refs():
            m = re.fullmatch(r'%s(\d+)' % re.escape(prefix), ref)
            if m:
                used.append(int(m.group(1)))
        return sorted(used)

    def designator_gaps(self, prefix: str) -> List[int]:
        """Numbers missing from a contiguous-looking designator sequence."""
        used = self._used_designators(prefix)
        if not used:
            return []
        return [n for n in range(1, max(used) + 1) if n not in used]

    def next_designator(self, prefix: str) -> Optional[int]:
        """max(used)+1: the next free designator when the fault removed the last
        member rather than an interior gap."""
        used = self._used_designators(prefix)
        return (max(used) + 1) if used else None


def _balanced_blocks(source_text: str, opener: str):
    """Yield balanced-paren blocks that start with `opener`.

    Limitation: quoted strings containing parentheses are not unescaped; the
    parser is a best-effort extractor over public source text, not a full s-expr
    reader.
    """
    start = re.compile(opener)
    index = 0
    while True:
        m = start.search(source_text, index)
        if not m:
            return
        depth = 0
        for j in range(m.start(), len(source_text)):
            ch = source_text[j]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    yield source_text[m.start():j + 1]
                    index = j + 1
                    break
        else:
            return


def parse_schematic(source_text: str) -> Schematic:
    wires: List[Wire] = []
    for block in _balanced_blocks(source_text, r'\(wire\s'):
        pts = re.search(r'\(pts\s+\(xy\s+([\-0-9.]+)\s+([\-0-9.]+)\)\s+'
                        r'\(xy\s+([\-0-9.]+)\s+([\-0-9.]+)\)\)', block)
        uuid_match = re.search(r'\(uuid\s+"(%s)"\)' % _UUID, block)
        if pts and uuid_match:
            wires.append(Wire(uuid_match.group(1), float(pts.group(1)),
                              float(pts.group(2)), float(pts.group(3)),
                              float(pts.group(4))))
    labels: List[Label] = []
    for block in _balanced_blocks(source_text, r'\(label\s'):
        head = re.search(r'\(label\s+"([^"]*)"\s+\(at\s+([\-0-9.]+)\s+([\-0-9.]+)\s+'
                         r'[\-0-9.]+\)', block)
        uuid_match = re.search(r'\(uuid\s+"(%s)"\)' % _UUID, block)
        if head:
            labels.append(Label(head.group(1), float(head.group(2)),
                                float(head.group(3)),
                                uuid_match.group(1) if uuid_match else None))
    symbols: List[Symbol] = []
    for block in _balanced_blocks(source_text, r'\(symbol\s+\(lib_id\s'):
        lib = re.search(r'\(lib_id\s+"([^"]+)"\)', block)
        at = re.search(r'\(at\s+([\-0-9.]+)\s+([\-0-9.]+)', block)
        ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]*)"', block)
        uuid_match = re.search(r'\(uuid\s+"(%s)"\)' % _UUID, block)
        pins = [{"pin": p.group(1), "uuid": p.group(2)} for p in re.finditer(
            r'\(pin\s+"([^"]+)"\s+\(uuid\s+"(%s)"\)\)' % _UUID, block)]
        if lib and at:
            symbols.append(Symbol(ref_match.group(1) if ref_match else None,
                                  lib.group(1), float(at.group(1)), float(at.group(2)),
                                  uuid_match.group(1) if uuid_match else None, pins))
    return Schematic(wires, labels, symbols)
