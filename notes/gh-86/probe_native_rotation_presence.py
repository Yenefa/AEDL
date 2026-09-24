"""GH-86 native probe (READ ONLY on the repo): does rotation *presence* change the
angle the pinned writer actually writes?

Applies the frozen DC-04 op-list twice on disposable scratch copies -- once exactly as
frozen (rotation absent) and once with an explicit `rotation: 0` on the add_net_label
ops -- then reads the label angles out of the written schematic.

Requires the pinned toolchain:
    AEDL_PR1_NATIVE=1
    AEDL_AKCLI_PYTHON=<toolchain/py311/Scripts/python.exe>

Run: py -3 notes/gh-86/probe_native_rotation_presence.py
"""
import os
import re
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from tests import test_akcli_adapter as T
from tools import akcli_adapter as adapter

LABEL = re.compile(r"\(label\s+\"([^\"]+)\"\s+\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)")


class _Probe(T._NativeToolchainMixin, unittest.TestCase):
    def runTest(self):
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        frozen = self._fixture_ops("DC-04")
        explicit = [dict(row, rotation=0) if row.get("op") == "add_net_label" else row
                    for row in frozen]
        for name, ops in (("absent", frozen), ("explicit0", explicit)):
            stage = self._stage("DC-04", "angle-" + name, ops=ops)
            body = self._patch(toolchain, ops, "DC-04", stage)
            result = adapter.apply_stage(self._stage_request(
                body, stage, os.path.join(self.root, "art-" + name)))
            print("%-10s status=%s changed=%s" % (name, result["status"], result["changed"]))
            with open(os.path.join(stage, "fault.kicad_sch"), encoding="utf-8") as handle:
                text = handle.read()
            found = LABEL.findall(text)
            if found:
                for label, x, y, angle in found:
                    print("           label %-8s at (%s, %s) angle=%s" % (label, x, y, angle))
            else:
                for line in text.splitlines():
                    if "(label " in line:
                        print("           raw: " + line.strip()[:160])


if __name__ == "__main__":
    suite = unittest.TestSuite([_Probe()])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
