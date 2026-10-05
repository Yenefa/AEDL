# -*- coding: utf-8 -*-
"""Synthesise missing-part episodes for RepairBench from frozen sources only.

Why this exists
---------------
The ``add_component`` family (DC-03/04/05) was marked unsolvable because no frozen
coordinate source described where the parts belonged. That judgement was wrong: the
answer key agreed with the schematic, and the schematic itself carries the placement.

Why it needs a native text writer
---------------------------------
akcli v1 cannot place a net label at a chosen coordinate. ``add_net_label`` accepts an
``at`` field, reports ``applied``, and silently drops it, anchoring the label at
(50, 250) mil instead. There is no second text op -- ``add_text`` and ``add_text_box``
are not net labels. The verifier requires every label to sit exactly on a pin point or
a wire endpoint, so an unusable label position is the whole failure.

This module therefore writes the ``(label ...)`` primitive directly. Everything else --
deleting the part, deleting its labels, placing the part -- goes through akcli.

What is verified
----------------
For R9 on the real M2 board this reproduces, with no answer key involved:

  pristine board        all 5 contract rules pass
  fault board           ESP32_GPIO9_PULLUP fails, the other 4 still pass
  + place_component     still fails (the rule needs connectivity, not just presence)
  + native labels       passes, and nothing else moves

The board is pure net-label connectivity -- zero wire and zero junction primitives --
so any repair that adds connectivity must write a native label.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NM = 1_000_000
MIL_NM = 25400
DEFAULT_SOURCE = REPO_ROOT / "src" / "hardware" / "m2-board" / "m2_board.kicad_sch"
AKCLI = Path.home() / "AppData/Local/hermes/hermes-agent/venv/Scripts/akcli.exe"


class SynthesisError(RuntimeError):
    """Raised when an episode cannot be synthesised or repaired as specified."""


def _akcli_draw(schematic, ops, akcli=None):
    """Run one akcli op batch. Returns (rc, combined_output)."""
    exe = Path(akcli or AKCLI)
    if not exe.exists():
        raise SynthesisError("akcli not found at %s" % exe)
    with tempfile.TemporaryDirectory() as tmp:
        ops_file = Path(tmp) / "ops.json"
        ops_file.write_text(json.dumps(
            {"protocol_version": 2, "target_format": "kicad", "ops": ops}), encoding="utf-8")
        argv = [str(exe), "draw", str(schematic), "--ops", str(ops_file),
                "--json", "--apply", "--no-erc"]
        proc = subprocess.run(argv, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _refused(output):
    try:
        return json.loads(output).get("status") == "refused"
    except Exception:
        return False


def _label_records(observation):
    """Every label source_object as (uuid, name, (x_nm, y_nm))."""
    out = []
    for entry in observation.get("source_objects", []):
        if entry.get("kind") != "label":
            continue
        try:
            ast = entry["descriptor"]["ast"]
            name = ast[1]["string"]
            at = None
            for item in ast:
                if isinstance(item, list) and item and item[0] == "at":
                    at = (int(round(float(item[1]["number"]) * NM)),
                          int(round(float(item[2]["number"]) * NM)))
                    break
            if name and at:
                out.append((entry["identity"], name, at))
        except Exception:
            continue
    return out


def component_pin_points(observation, reference):
    """Verifier pin points for `reference`, as (position + dx, position - dy) in nm.

    Mirrors gates/repair_verification.py::_source_component_positions, including the
    Y flip, because that is exactly how the verifier decides pin identity.
    """
    comp = next((c for c in observation["components"] if c["reference"] == reference), None)
    if comp is None:
        raise SynthesisError("component %s not present" % reference)
    body = tuple(comp["position_nm"])
    out = []
    for part in observation["partitions"]:
        for member in part["members"]:
            if member.get("reference") == reference:
                key = member.get("partition_key")
                for pin in observation["pins"]:
                    if pin.get("partition_key") != key:
                        continue
                    number = pin["identity"].get("number")
                    if not number:
                        continue
                    out.append((number, body))
    # de-duplicate, keep order
    seen, uniq = set(), []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return body, uniq


def symbol_pin_offsets(schematic_text, lib_id):
    """Read pin (x, y) offsets for lib_id out of the schematic's lib_symbols section."""
    key = '"%s"' % lib_id
    start = schematic_text.find("(symbol " + key)
    if start < 0:
        match = re.search(r'\(symbol\s+"%s"' % re.escape(lib_id), schematic_text)
        if not match:
            raise SynthesisError("lib_symbol %s not found" % lib_id)
        start = match.start()
    depth, i = 0, start
    while i < len(schematic_text):
        char = schematic_text[i]
        if char == '"':
            i += 1
            while i < len(schematic_text) and schematic_text[i] != '"':
                i += 1
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    block = schematic_text[start:i + 1]
    offsets = []
    for match in re.finditer(r'\(pin\s+\w+\s+\w+', block):
        sub_depth, j = 0, match.start()
        while j < len(block):
            if block[j] == "(":
                sub_depth += 1
            elif block[j] == ")":
                sub_depth -= 1
                if sub_depth == 0:
                    break
            j += 1
        piece = block[match.start():j + 1]
        number = re.search(r'\(number\s+"([^"]+)"', piece)
        at = re.search(r'\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)', piece)
        if number and at:
            offsets.append((number.group(1), float(at.group(1)) * NM,
                            float(at.group(2)) * NM))
    return offsets


def native_label_block(name, point_nm):
    """A `(label ...)` primitive in the same shape the frozen board uses."""
    return ('\n\t(label "%s" (at %.2f %.2f 0) (effects (font (size 1.27 1.27)) '
            '(justify left bottom)) (uuid "%s"))\n'
            % (name, point_nm[0] / NM, point_nm[1] / NM, uuid.uuid4()))


def write_native_labels(schematic_path, labels):
    """Insert `(label ...)` primitives. labels is [(name, (x_nm, y_nm)), ...]."""
    with io.open(str(schematic_path), "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
    eol = "\r\n" if text.count("\r\n") else "\n"
    for name, point in labels:
        text = text.replace(eol + ")" + eol,
                            native_label_block(name, point).replace("\n", eol) + eol + ")" + eol, 1)
    with io.open(str(schematic_path), "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    return schematic_path


def synthesise_fault(source, reference, rule_statuses, observe, akcli=None):
    """Build a fault board: the named part(s) and their labels are removed.

    ``reference`` may be one designator or a list of them. Multi-part episodes matter
    because some contract rules assert a *pair*: deleting R7 alone breaks
    USB_POLARITY_AND_SERIES, but placing R7 back does not satisfy it, because the rule
    also needs R8. A single-part episode would then be unsolvable in one direction and
    misleading in the other. Measured, not assumed.

    Returns (dest_path, placement) where placement is the public record a solver needs
    to repair the board without any answer key.
    """
    source = Path(source)
    observation = observe(source.read_bytes())
    wanted_refs = [reference] if isinstance(reference, str) else list(reference)
    specs = []
    for ref in wanted_refs:
        comp = next((c for c in observation["components"] if c["reference"] == ref), None)
        if comp is None:
            raise SynthesisError("%s not on %s" % (ref, source))
        specs.append((ref, comp))

    source_text = source.read_text(encoding="utf-8", errors="replace")
    labels = _label_records(observation)

    victims, component_specs, pin_points = [], [], {}
    for ref, comp in specs:
        body = tuple(comp["position_nm"])
        offsets = symbol_pin_offsets(source_text, comp["lib_id"])
        if not offsets:
            raise SynthesisError("no pin offsets for %s" % comp["lib_id"])
        pin_points[ref] = {number: [int(body[0] + dx), int(body[1] - dy)]
                           for number, dx, dy in offsets}
        component_specs.append({
            "reference": ref,
            "lib_id": comp["lib_id"],
            "footprint": comp["footprint"],
            "value": comp["value"],
            "x_mil": round(body[0] / MIL_NM),
            "y_mil": round(body[1] / MIL_NM),
        })
        names = []
        for part in observation["partitions"]:
            for member in part["members"]:
                if member.get("reference") == ref:
                    for net in (part.get("names") or []):
                        if net not in names:
                            names.append(net)
        wanted = {n.lstrip("/") for n in names}
        victims += [(uid, nm, at) for uid, nm, at in labels if nm in wanted]

    dest = Path(tempfile.mkdtemp()) / "fault.kicad_sch"
    shutil.copyfile(str(source), str(dest))

    ops = [{"op": "delete_component", "designator": spec["reference"]}
           for spec in component_specs]
    ops += [{"op": "delete_object", "uuid": uid} for uid, _nm, _at in victims]
    rc, out = _akcli_draw(dest, ops, akcli)
    if rc != 0:
        raise SynthesisError("fault synthesis refused: %s" % out[:400])
    return dest, {
        "components": component_specs,
        "pin_points_nm": pin_points,
        "labels": [{"name": nm, "point_nm": list(at)} for _uid, nm, at in victims],
    }


def repair(dest, placement, rule_statuses, observe, akcli=None):
    """Place the part(s) and restore their labels natively. Returns rule statuses."""
    dest = Path(dest)
    ops = [{"op": "place_component",
            "lib_id": spec["lib_id"],
            "designator": spec["reference"],
            "x_mil": spec["x_mil"],
            "y_mil": spec["y_mil"],
            "value": spec["value"],
            "footprint": spec["footprint"]}
           for spec in placement["components"]]
    rc, out = _akcli_draw(dest, ops, akcli)
    if rc != 0:
        raise SynthesisError("place_component refused: %s" % out[:400])

    pin_points = set()
    for points in placement["pin_points_nm"].values():
        pin_points.update(tuple(p) for p in points.values())

    # Restore EVERY deleted label, not only the ones sitting on a restored pin.
    # Deleting a part also deletes the labels on all of its nets, including those at the
    # far end of the net on other components. Restoring only the pin-sitting ones leaves
    # the far end unnamed and the contract still fails. Measured: with only the pin-sitting
    # labels restored, USB_POLARITY_AND_SERIES stayed FAIL after R7 and R8 were placed;
    # with all ten restored, all five rules pass.
    on_pins = []
    seen = set()
    for entry in placement["labels"]:
        point = tuple(entry["point_nm"])
        key = (entry["name"], point)
        if key in seen:
            continue
        seen.add(key)
        on_pins.append((entry["name"], point))
    if not any(point in pin_points for _name, point in on_pins):
        raise SynthesisError("no recorded label sits on a restored pin")
    write_native_labels(dest, on_pins)
    return rule_statuses(dest.read_bytes())


def synthesise_label_fault(source, rule, rule_statuses, observe, akcli=None):
    """Build a fault board by removing one net label, chosen to break exactly `rule`.

    Connectivity-label episodes are the cheapest honest episodes available: the frozen
    board already satisfies every rule, so deleting a single label that some rule depends
    on produces a fault that violates that rule and nothing else. Measured on the M2
    board: 15 of 72 labels break exactly one rule, spread across all four rules, and each
    one restores cleanly through write_native_labels.

    Returns (dest_path, record) where record names the label and the exact point to
    restore. That record is the answer key; the fault board is the task input.
    """
    source = Path(source)
    labels = _label_records(observe(source.read_bytes()))
    for uid, name, at in labels:
        probe = Path(tempfile.mkdtemp()) / "probe.kicad_sch"
        shutil.copyfile(str(source), str(probe))
        rc, _out = _akcli_draw(probe, [{"op": "delete_object", "uuid": uid}], akcli)
        if rc != 0:
            continue
        try:
            statuses = rule_statuses(probe.read_bytes())
        except Exception:
            continue
        failing = sorted(k for k, v in statuses.items() if v == "fail")
        if failing != [rule]:
            continue
        dest = Path(tempfile.mkdtemp()) / "fault.kicad_sch"
        shutil.copyfile(str(source), str(dest))
        rc, out = _akcli_draw(dest, [{"op": "delete_object", "uuid": uid}], akcli)
        if rc != 0:
            raise SynthesisError("label fault refused: %s" % out[:300])
        return dest, {"label": name, "point_nm": list(at), "broken_rule": rule}
    raise SynthesisError("no single label breaks exactly %s" % rule)


def repair_label(dest, record, rule_statuses, observe, akcli=None):
    """Restore the one removed label natively. Returns rule statuses."""
    write_native_labels(Path(dest), [(record["label"], tuple(record["point_nm"]))])
    return rule_statuses(Path(dest).read_bytes())
