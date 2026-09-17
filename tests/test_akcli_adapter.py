"""PR-1 C4 acceptance tests for tools.akcli_adapter (contract section 11 C4).

Every test here is software-only: a host-supplied stub akcli package and a stub
akcli CLI stand in for the pinned tool.  The optional NativeQualificationTests
class runs the same adapter against the real pinned toolchain and only executes
when the host opts in through AEDL_PR1_NATIVE=1 and AEDL_AKCLI_PYTHON.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from gates.repair_verification import canonical_sha256, hash_bytes, observe_source
from tools import akcli_adapter as adapter


STAGE_SEXPR = b'(kicad_sch (version 20231120) (uuid "ac3cd9a8-1c8c-4a4b-9cc4-1d3ba4b0d111")\n' \
              b'  (label "USB_DM" (uuid "ac3cd9a8-1c8c-4a4b-9cc4-1d3ba4b0d222")))\n'


def _insert_into_document(path, uuids):
    """Insert real top-level objects inside the document, the way a writer does."""
    lines = ['\t(label "stub-%d" (at 0 0 0) (effects (font (size 1.27 1.27))) (uuid "%s"))'
             % (index, item) for index, item in enumerate(uuids)]
    with open(path, encoding="utf-8") as handle:
        body = handle.read().rstrip()
    if not body.endswith(")"):
        raise AssertionError("the stage is not a closed S-expression")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body[:-1] + "\n" + "\n".join(lines) + "\n)\n")

PIN = {"number": "1", "name": "", "electrical": "passive", "x_mil": 0, "y_mil": 0}


def sidecar(reference="R9", second_pin=False, connectivity=None):
    pins = [dict(PIN)] + ([{"number": "2", "name": "", "electrical": "passive",
                            "x_mil": 0, "y_mil": 100}] if second_pin else [])
    return {
        "components": [{"reference": reference, "lib_id": "Device:R", "value": "10k",
                        "footprint": "Resistor_SMD:R_0603_1608Metric",
                        "uuid": "11111111-2222-3333-4444-555555555555",
                        "x_mil": 1350, "y_mil": 10150, "pins": pins}],
        "nets": [{"name": "+3V3", "members": [[reference, pin["number"]] for pin in pins]}],
        "library": [{"lib_id": "Device:R", "pins": [dict(PIN)] + (
            [{"number": "2", "name": "", "electrical": "passive", "x_mil": 0, "y_mil": 100}]
            if second_pin else [])}],
        "connectivity": list(connectivity or []),
        "writer": {},
    }


_FAKE_MODULES = {
    "akcli/__init__.py": "__all__ = []\n",
    "akcli/sexpr.py": "class SNode(object):\n    pass\n\n"
                      "def parse(text):\n    return SNode()\n\n"
                      "def dumps(node):\n    return node if isinstance(node, str) else repr(node)\n",
    "akcli/readers/__init__.py": "from . import kicad  # noqa: F401\n",
    "akcli/readers/kicad.py": '''
import json


def _sidecar(path):
    with open(str(path) + ".native.json", encoding="utf-8") as handle:
        return json.load(handle)


class Pin(object):
    def __init__(self, row):
        self.number = row["number"]
        self.name = row.get("name", "")
        self.electrical_type = row.get("electrical", "passive")
        self.x_mil = row.get("x_mil", 0)
        self.y_mil = row.get("y_mil", 0)
        self.owner_part_id = 1
        self.unique_id = None
        self.orientation = 0


class Component(object):
    def __init__(self, row):
        self.designator = row["reference"]
        self.library_ref = row["lib_id"]
        self.x_mil = row["x_mil"]
        self.y_mil = row["y_mil"]
        self.rotation = row.get("rotation", 0)
        self.mirror = row.get("mirror", "none")
        self.value = row.get("value", "")
        self.footprint = row.get("footprint", "")
        self.unique_id = row["uuid"]
        self.part_count = row.get("part_count", 1)
        self.sheet = ""
        self.parameters = {}
        self.undesignated = False
        self.dnp = row.get("dnp", False)
        self.in_bom = row.get("in_bom", True)
        self.on_board = row.get("on_board", True)
        self.pins = [Pin(item) for item in row.get("pins", [])]


class Net(object):
    def __init__(self, row):
        self.name = row["name"]
        self.members = [tuple(item) for item in row["members"]]
        self.aliases = []
        self.source_names = [row["name"]]
        self.is_named = True
        self.confidence = 1.0
        self.merge_reasons = []
        self.sheet_path = "/"


class Schematic(object):
    def __init__(self, data):
        self.components = [Component(row) for row in data["components"]]
        self.nets = [Net(row) for row in data["nets"]]
        if "metadata" in data:
            self.metadata = data["metadata"]
        else:
            self.metadata = {"component_count": len(self.components),
                             "pin_count": sum(len(row.pins) for row in self.components)}


class Symbol(object):
    def __init__(self, row):
        self.lib_id = row["lib_id"]
        self.pins = [Pin(item) for item in row.get("pins", [])]
        self.body_sexpr = row.get("body", "")


class Library(object):
    def __init__(self, data):
        self.symbols = [Symbol(row) for row in data.get("library", [])]


class Primitives(object):
    def __init__(self, pin_count):
        self.wires = []
        self.junctions = []
        self.labels = []
        self.pins = [None] * pin_count
        self.buses = []
        self.bus_entries = []


def read_sch(path):
    return Schematic(_sidecar(path))


def read_primitives(path):
    data = _sidecar(path)
    count = data.get("primitive_pin_count")
    if count is None:
        count = sum(len(row.get("pins", [])) for row in data.get("components", []))
    return Primitives(count)


def read_embedded_library(path):
    return Library(_sidecar(path))
''',
    "akcli/writers/__init__.py": "from . import kicad, lib_cache, connectivity  # noqa: F401\n",
    "akcli/writers/lib_cache.py": "cache_dir = None\n",
    "akcli/writers/connectivity.py": '''
import json


class Finding(object):
    def __init__(self, row):
        self.code = row.get("code", "UNKNOWN_FINDING")
        self.severity = row.get("severity", "INFO")
        self.message = row.get("message", "")
        self.refs = row.get("refs", [])
        self.status = "open"


def verify(doc, tol_nm=0, path=None):
    with open(str(path) + ".native.json", encoding="utf-8") as handle:
        data = json.load(handle)
    return [Finding(row) for row in data.get("connectivity", [])]
''',
    "akcli/writers/kicad.py": '''
import json
import os


def _sidecar(path):
    with open(str(path) + ".native.json", encoding="utf-8") as handle:
        return json.load(handle)


class Finding(object):
    def __init__(self, row):
        self.code = row.get("code", "UNKNOWN_FINDING")
        self.severity = row.get("severity", "INFO")
        self.message = row.get("message", "")
        self.refs = row.get("refs", [])


class OpResult(object):
    def __init__(self, row):
        self.op_index = row["op_index"]
        self.op = row.get("op")
        self.status = row.get("status", "ok")
        self.created_uuids = row.get("created_uuids", [])
        self.error_code = row.get("error_code")
        self.message = row.get("message", "")
        self.remediation = None


def _insert_into_document(path, uuids):
    lines = ['  (label "stub-%d" (at 0 0 0) (effects (font (size 1.27 1.27))) (uuid "%s"))'
             % (index, item) for index, item in enumerate(uuids)]
    with open(path, encoding="utf-8") as handle:
        body = handle.read().rstrip()
    if not body.endswith(")"):
        raise ValueError("the stub stage is not a closed S-expression")
    with open(path, "w", encoding="utf-8", newline=chr(10)) as handle:
        handle.write(body[:-1] + chr(10) + chr(10).join(lines) + chr(10) + ")" + chr(10))


def apply(oplist, path, apply=False, sources=None, backup_dir=None, backup_depth=3,
          tol_nm=0, verify_out=None, allow_open=False):
    calls = os.environ.get("FAKE_AKCLI_CALLS")
    if calls:
        with open(calls, "a", encoding="utf-8") as handle:
            handle.write("worker-apply\\n")
    data = _sidecar(path)
    writer = data.get("writer", {})
    rows = writer.get("op_results")
    if rows is None:
        rows = [{"op_index": index, "op": op.get("op"), "status": "ok",
                 "created_uuids": ["aaaaaaaa-bbbb-cccc-dddd-%012d" % index]}
                for index, op in enumerate(oplist.get("ops", []))]
    if apply and writer.get("change_bytes", True):
        created = [item for row in rows for item in (row.get("created_uuids") or [])]
        _insert_into_document(path, created)
    if verify_out is not None:
        for row in data.get("connectivity", []):
            verify_out.append(Finding(row))
    return [OpResult(row) for row in rows]
''',
}

_CLI_STUB = r'''
import json
import os
import sys


def _bump(kind):
    calls = os.environ.get("FAKE_AKCLI_CALLS")
    if calls:
        with open(calls, "a", encoding="utf-8") as handle:
            handle.write(kind + "\n")


def _rewrite_sidecar(target, findings):
    path = target + ".native.json"
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    data["connectivity"] = findings
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)


def _uuid(index):
    return "aaaaaaaa-bbbb-cccc-dddd-%012d" % index


def _insert_into_document(path, uuids):
    lines = ['\t(label "stub-%d" (at 0 0 0) (effects (font (size 1.27 1.27))) (uuid "%s"))'
             % (index, item) for index, item in enumerate(uuids)]
    with open(path, encoding="utf-8") as handle:
        body = handle.read().rstrip()
    if not body.endswith(")"):
        raise SystemExit("the stub stage is not a closed S-expression")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body[:-1] + "\n" + "\n".join(lines) + "\n)\n")


def _ops(count, status="ok"):
    return [{"op_index": index, "op": "place_component" if index == 0 else "add_net_label",
             "status": status, "created_uuids": [_uuid(index)],
             "error_code": None if status == "ok" else "OP_FAILED", "message": ""}
            for index in range(count)]


def main():
    args = sys.argv[1:]
    target = args[1]
    oplist_path = args[args.index("--ops") + 1]
    with open(oplist_path, encoding="utf-8") as handle:
        oplist = json.load(handle)
    count = len(oplist.get("ops", []))
    mode = os.environ.get("FAKE_AKCLI_MODE", "applied")
    _bump("cli:" + mode)
    if mode == "malformed":
        sys.stdout.write("this is not a receipt\n")
        return 6
    if mode == "broken":
        return 3
    if mode == "refused-net":
        sys.stdout.write(json.dumps({
            "schema_version": "1", "akcli_version": "0.21.0",
            "error": {"code": "OPLIST", "exit": 6,
                      "message": "REFUSED: --strict-nets: net split/merge touches a named net; nothing written",
                      "remediation": "nothing was written"}}))
        return 6
    if mode == "refused-op":
        sys.stdout.write(json.dumps({"schema_version": "1.0", "applied": False,
                                     "status": "refused", "ops": _ops(count, "error"),
                                     "connectivity": [], "net_diff": None, "preview": None}))
        return 6
    if mode == "dry-run":
        sys.stdout.write(json.dumps({"schema_version": "1.0", "applied": False,
                                     "status": "dry-run", "ops": _ops(count),
                                     "connectivity": [], "net_diff": {"lines": []},
                                     "preview": None}))
        return 0
    connectivity = []
    if mode == "new-warning":
        connectivity = [{"code": "DANGLING_ENDPOINT", "severity": "WARNING",
                         "message": "new dangling endpoint"}]
    elif mode == "no-connect":
        connectivity = [{"code": "NO_CONNECT_CONFLICT", "severity": "WARNING",
                         "message": "NC pin still wired"}]
    elif mode == "error-severity":
        connectivity = [{"code": "DUPLICATE_UUID", "severity": "ERROR",
                         "message": "duplicate uuid"}]
    elif mode == "unknown-severity":
        connectivity = [{"code": "MYSTERY", "severity": "CATASTROPHIC",
                         "message": "unknown level"}]
    if mode in ("new-warning", "no-connect", "error-severity", "unknown-severity"):
        _rewrite_sidecar(target, connectivity)
    elif mode == "silent-warning":
        # the receipt stays clean; only the fresh read can see the new warning
        _rewrite_sidecar(target, [{"code": "DANGLING_ENDPOINT", "severity": "WARNING",
                                   "message": "introduced by the write", "refs": ["U7"]}])
    elif mode == "moved-warning":
        _rewrite_sidecar(target, [{"code": "DANGLING_ENDPOINT", "severity": "WARNING",
                                   "message": "same code, different object", "refs": ["U7"]}])
    elif mode == "receipt-only-nc":
        # the receipt claims an NC conflict the fresh read cannot see
        connectivity = [{"code": "NO_CONNECT_CONFLICT", "severity": "WARNING",
                         "message": "receipt only"}]
    reported = [_uuid(index) for index in range(count)]
    written = list(reported)
    if mode == "uuid-mismatch":
        # the receipt names an object the write never created
        reported = ["99999999-9999-4999-8999-%012d" % index for index in range(count)]
    elif mode == "unreported-object":
        # the write creates one more top-level object than it reports
        written = written + ["00000000-0000-4000-8000-0000000000ff"]
    elif mode == "bad-uuid":
        reported = ["NOT-A-UUID"] * count
    elif mode == "duplicate-uuid":
        # two operations name the same created object while the write really did
        # create distinct ones
        reported = [_uuid(0)] * count
    if mode != "forged-applied":
        _insert_into_document(target, written)
    ops = _ops(count)
    for index, row in enumerate(ops):
        row["created_uuids"] = [reported[index % len(reported)]] if reported else []
    payload = {"schema_version": "1.0", "status": "applied", "ops": ops,
               "connectivity": connectivity, "net_diff": {"lines": []}, "preview": None}
    if mode == "no-applied":
        pass
    elif mode == "missing-op":
        payload["applied"] = True
        payload["ops"] = _ops(count)[:max(1, count - 1)]
    elif mode == "duplicate-op":
        # a mis-numbered index, but three distinct objects really were created: the
        # index violation must be the only one this perturbation introduces
        payload["applied"] = True
        payload["ops"] = [dict(row, op_index=0) for row in _ops(count)]
    elif mode == "op-error":
        payload["applied"] = True
        payload["ops"] = _ops(count, "error")
    else:
        payload["applied"] = True
    sys.stdout.write(json.dumps(payload))
    return 0


sys.exit(main())
'''


def _write_fake_package(root, version="0.21.0"):
    package = os.path.join(root, "pkg")
    for name, body in _FAKE_MODULES.items():
        path = os.path.join(package, *name.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
    cli = os.path.join(root, "fake_akcli.py")
    with open(cli, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(_CLI_STUB)
    dist_info = os.path.join(package, "akcli_kicad-%s.dist-info" % version)
    os.makedirs(dist_info, exist_ok=True)
    with open(os.path.join(dist_info, "METADATA"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("Metadata-Version: 2.1\nName: akcli-kicad\nVersion: %s\n" % version)
    rows = []
    for base, _dirs, files in os.walk(package):
        for name in sorted(files):
            path = os.path.join(base, name)
            relative = os.path.relpath(path, package).replace(os.sep, "/")
            if relative.startswith("akcli_kicad-%s.dist-info" % version):
                continue
            with open(path, "rb") as source:
                rows.append((relative, source.read()))
    with open(os.path.join(dist_info, "RECORD"), "w", encoding="utf-8", newline="\n") as handle:
        for relative, raw in rows:
            digest = __import__("base64").urlsafe_b64encode(
                __import__("hashlib").sha256(raw).digest()).rstrip(b"=").decode("ascii")
            handle.write("%s,sha256=%s,%d\n" % (relative, digest, len(raw)))
        handle.write("akcli_kicad-%s.dist-info/METADATA,,\n" % version)
        handle.write("akcli_kicad-%s.dist-info/RECORD,,\n" % version)
    return package, cli


def _distribution_digest(package, version="0.21.0"):
    """Mirror the adapter's RECORD-driven distribution digest exactly."""
    record = os.path.join(package, "akcli_kicad-%s.dist-info" % version, "RECORD")
    rows = []
    with open(record, encoding="utf-8") as handle:
        for line in handle:
            entry = line.split(",")[0].strip()
            if not entry:
                continue
            path = os.path.join(package, *entry.split("/"))
            if not os.path.isfile(path):
                continue
            with open(path, "rb") as source:
                rows.append([entry, hash_bytes(source.read())])
    rows.sort()
    return canonical_sha256("manifest", rows)


def _make_directory_link(target, link):
    """Create a directory junction/symlink, or return None when unavailable."""
    if os.name == "nt":
        completed = subprocess.run(["cmd", "/c", "mklink", "/J", link, target],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return link if completed.returncode == 0 else None
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        return None
    return link


def _symbol_digest(payload):
    """Mirror the adapter's embedded-library symbol digest exactly."""
    rows = []
    for symbol in payload.get("library", []):
        pins = sorted([[item["number"], item.get("name", ""), item.get("electrical", "passive")]
                       for item in symbol.get("pins", [])])
        rows.append([symbol["lib_id"], canonical_sha256("protected", pins),
                     hash_bytes(str(symbol.get("body", "")).encode("utf-8"))])
    rows.sort()
    return canonical_sha256("manifest", rows)


class AdapterCase(unittest.TestCase):
    """Shared stub host: fake akcli package, fake CLI, one scratch stage."""

    rule = "DC-04"
    route = "STRICT"
    oplist_ops = [{"op": "place_component", "lib_id": "Device:R", "designator": "R9",
                   "x_mil": 1350, "y_mil": 10150, "value": "10k",
                   "footprint": "Resistor_SMD:R_0603_1608Metric"},
                  {"op": "add_net_label", "name": "+3V3", "at": "R9.1"},
                  {"op": "add_net_label", "name": "BOOT", "at": "R9.2"}]

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="aedl-c4-")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.calls = os.path.join(self.root, "calls.log")
        open(self.calls, "w").close()
        self.package, self.cli = _write_fake_package(self.root)
        self.stage = os.path.join(self.root, "stage")
        os.makedirs(self.stage)
        self.target = os.path.join(self.stage, "fault.kicad_sch")
        self.payload = sidecar()
        self.write_stage(self.payload)
        self.oplist_path = os.path.join(self.stage, "oplist.json")
        with open(self.oplist_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"protocol_version": 2, "target_format": "kicad",
                       "ops": self.oplist_ops}, handle)
        self.artifacts = os.path.join(self.root, "native-artifacts")
        self.mode = "applied"

    def write_stage(self, payload, name="fault.kicad_sch", raw=STAGE_SEXPR):
        target = os.path.join(self.stage, name)
        with open(target, "wb") as handle:
            handle.write(raw)
        with open(target + ".native.json", "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle)
        self.target = target
        self.payload = payload
        return target

    def toolchain(self, version="0.21.0", artifact=None, symbol=None, **overrides):
        manifest = {"version": 1, "akcli_executable": self.cli, "akcli_version": "0.21.0",
                    "akcli_artifact_sha256": artifact or _distribution_digest(self.package),
                    "akcli_upstream_commit": adapter.AKCLI_UPSTREAM_COMMIT,
                    "worker_python": sys.executable,
                    "symbol_digest": symbol or _symbol_digest(self.payload),
                    "launcher_argv": [sys.executable], "timeout_seconds": 60,
                    "environment": {"PYTHONPATH": self.package,
                                    "FAKE_AKCLI_CALLS": self.calls,
                                    "FAKE_AKCLI_MODE": self.mode}}
        manifest.update(overrides)
        return manifest

    def stage_bytes(self):
        with open(self.target, "rb") as handle:
            return handle.read()

    def proposal(self, ops=None, base_source_sha256=None):
        return {"schema_version": 1, "context_id": "CTX-1", "target": "design/fault.kicad_sch",
                "base_source_sha256": base_source_sha256 or hash_bytes(self.stage_bytes()),
                "decision": "PATCH",
                "oplist": {"protocol_version": 2, "target_format": "kicad",
                           "ops": ops if ops is not None else self.oplist_ops},
                "diagnosis": []}

    def host_patch(self, rule=None, route=None, toolchain=None, ops=None, patch_id="PATCH-1"):
        toolchain = toolchain or self.toolchain()
        proposal = self.proposal(ops)
        body = {"schema_version": 1, "run_id": "RUN-1", "candidate_id": "CAND-1",
                "round_id": "ROUND-1", "patch_id": patch_id, "context_id": "CTX-1",
                "proposal": proposal,
                "proposal_sha256": canonical_sha256("proposal", proposal),
                "target": "design/fault.kicad_sch",
                "base": {"files": {}, "topology_sha256": canonical_sha256("topology", "T")},
                "policy": {"id": "POLICY-1", "file_sha256": canonical_sha256("manifest", "F"),
                           "bound_rule_id": rule or self.rule,
                           "bound_policy_sha256": canonical_sha256("policy-bound", "B")},
                "authority": {"context_digest": canonical_sha256("context", "C"),
                              "resolved_authorization_refs": ["host:ledger:1"],
                              "decisions": [{"capability": "TOOL_EXECUTE", "effect": "ALLOW"},
                                            {"capability": "FILE_WRITE", "effect": "ALLOW"}]},
                "toolchain_manifest": toolchain,
                "toolchain_sha256": adapter._toolchain_digest(toolchain),
                "route": route or self.route,
                "bound_policy": {"version": 1}}
        body["patch_sha256"] = canonical_sha256("patch", body)
        return body

    def stage_request(self, host_patch=None):
        return {"host_patch": host_patch or self.host_patch(),
                "txn_id": "TXN-1", "stage_root": self.stage,
                "stage_target": os.path.basename(self.target),
                "oplist_path": self.oplist_path,
                "native_artifact_root": self.artifacts}

    def codes(self, result):
        return [row["code"] for row in result["reasons"]]

    def call_log(self):
        with open(self.calls, encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]


class StrictReceiptTests(AdapterCase):
    """strict exit6 / dry-run / applied contradictions (C4 acceptance)."""

    def test_an_applied_write_with_real_byte_change_is_accepted(self):
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "APPLIED_TO_STAGE", result["reasons"])
        self.assertTrue(result["changed"])
        self.assertIs(result["tool"]["tool_applied"], True)
        self.assertEqual([row["op_index"] for row in result["tool"]["op_results"]], [0, 1, 2])
        self.assertTrue(result["native_before"]["observation"]["components"])

    def test_exactly_one_write_call_is_made(self):
        adapter.apply_stage(self.stage_request())
        self.assertEqual(self.call_log(), ["cli:applied"])

    def test_exit_six_with_a_legal_refusal_object_is_blocked_and_never_written(self):
        self.mode = "refused-net"
        with open(self.target, "rb") as handle:
            before = handle.read()
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_STRICT_REFUSED", self.codes(result))
        with open(self.target, "rb") as handle:
            self.assertEqual(handle.read(), before)
        self.assertEqual(self.call_log(), ["cli:refused-net"])

    def test_a_malformed_exit_six_is_a_tool_error_not_a_refusal(self):
        self.mode = "malformed"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "TOOL_ERROR")
        self.assertIn("REPAIR_TOOL_PROTOCOL_ERROR", self.codes(result))

    def test_an_op_level_refusal_is_blocked(self):
        self.mode = "refused-op"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_STRICT_REFUSED", self.codes(result))

    def test_a_dry_run_receipt_is_never_applied(self):
        self.mode = "dry-run"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_EFFECT_MISMATCH", self.codes(result))
        self.assertNotEqual(result["status"], "APPLIED_TO_STAGE")

    def test_a_missing_applied_field_is_never_applied(self):
        self.mode = "no-applied"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["tool"]["tool_applied"])

    def test_a_forged_applied_true_without_a_byte_change_is_blocked(self):
        self.mode = "forged-applied"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_EFFECT_MISMATCH", self.codes(result))
        self.assertFalse(result["changed"])

    def test_a_missing_op_index_is_blocked(self):
        self.mode = "missing-op"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_TOOL_PROTOCOL_ERROR", self.codes(result))

    def test_a_duplicated_op_index_is_blocked(self):
        self.mode = "duplicate-op"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")

    def test_an_error_op_status_is_blocked(self):
        self.mode = "op-error"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_EFFECT_MISMATCH", self.codes(result))

    def test_a_broken_exit_code_is_a_tool_error(self):
        self.mode = "broken"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "TOOL_ERROR")

    def test_a_new_warning_blocks(self):
        self.mode = "new-warning"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_EFFECT_MISMATCH", self.codes(result))

    def test_an_existing_warning_that_is_not_host_frozen_still_blocks(self):
        warnings = [{"code": "DANGLING_ENDPOINT", "severity": "WARNING", "message": "known",
                     "refs": ["R1"]}]
        self.write_stage(sidecar(connectivity=warnings))
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_EFFECT_MISMATCH", self.codes(result))

    def test_a_warning_that_moved_to_another_object_blocks(self):
        warnings = [{"code": "DANGLING_ENDPOINT", "severity": "WARNING", "message": "on R1",
                     "refs": ["R1"]}]
        self.write_stage(sidecar(connectivity=warnings))
        self.mode = "moved-warning"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        details = " | ".join(row["detail"] for row in result["reasons"])
        self.assertIn("new WARNING", details)
        before = adapter.normalize_connectivity(
            [{"code": "DANGLING_ENDPOINT", "severity": "WARNING", "refs": ["R1"]}])[0]
        after = adapter.normalize_connectivity(
            [{"code": "DANGLING_ENDPOINT", "severity": "WARNING", "refs": ["U7"]}])[0]
        self.assertEqual(before[0]["object_id"], "R1")
        self.assertEqual(after[0]["object_id"], "U7")

    def test_a_clean_receipt_cannot_hide_a_new_warning_in_the_fresh_read(self):
        self.mode = "silent-warning"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_EFFECT_MISMATCH", self.codes(result))
        self.assertEqual(result["tool"]["connectivity_findings"], [])

    def test_a_no_connect_conflict_blocks(self):
        self.mode = "no-connect"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")

    def test_an_error_severity_blocks(self):
        self.mode = "error-severity"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")

    def test_an_unknown_severity_is_unknown_not_info(self):
        self.mode = "unknown-severity"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertNotEqual(result["status"], "APPLIED_TO_STAGE")


class RouteAndBindingTests(AdapterCase):
    """route frozen at PRECHECK, version/path/authority boundaries."""

    def test_a_rule_that_must_use_exception_is_refused_on_the_strict_route(self):
        patch = self.host_patch(rule="E1", route="STRICT")
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_AUTH_DENIED", self.codes(result))
        self.assertEqual(self.call_log(), [])

    def test_a_rule_that_must_use_strict_is_refused_on_the_exception_route(self):
        patch = self.host_patch(rule="DC-04", route="CONSTRAINED_EXCEPTION")
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(self.call_log(), [])

    def test_an_unknown_rule_has_no_route(self):
        patch = self.host_patch(rule="E9", route="STRICT")
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_POLICY_DISABLED", self.codes(result))

    def test_a_strict_refusal_is_never_retried_through_the_exception_writer(self):
        self.mode = "refused-net"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(self.call_log(), ["cli:refused-net"])
        self.assertNotIn("worker-apply", self.call_log())

    def test_a_toolchain_version_other_than_0_21_0_is_refused(self):
        toolchain = self.toolchain(akcli_version="0.19.0")
        result = adapter.apply_stage(self.stage_request(self.host_patch(toolchain=toolchain)))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(self.call_log(), [])

    def test_a_running_version_mismatch_is_a_tool_error(self):
        package, cli = _write_fake_package(os.path.join(self.root, "old"), version="0.19.0")
        manifest = self.toolchain()
        manifest["akcli_executable"] = cli
        manifest["akcli_artifact_sha256"] = _distribution_digest(package, version="0.19.0")
        manifest["environment"]["PYTHONPATH"] = package
        before = self.stage_bytes()
        result = adapter.apply_stage(self.stage_request(self.host_patch(toolchain=manifest)))
        self.assertEqual(result["status"], "TOOL_ERROR")
        self.assertIn("REPAIR_TOOL_UNAVAILABLE", self.codes(result))
        # PRECHECK settles the toolchain, so a mismatched writer is never started
        self.assertEqual(self.call_log(), [])
        self.assertEqual(self.stage_bytes(), before)

    def test_a_distribution_digest_mismatch_is_a_tool_error(self):
        toolchain = self.toolchain(artifact="0" * 64)
        before = self.stage_bytes()
        result = adapter.apply_stage(self.stage_request(self.host_patch(toolchain=toolchain)))
        self.assertEqual(result["status"], "TOOL_ERROR")
        self.assertIn("REPAIR_TOOL_UNAVAILABLE", self.codes(result))
        self.assertEqual(self.call_log(), [])
        self.assertEqual(self.stage_bytes(), before)

    def test_a_symbol_digest_mismatch_is_a_tool_error(self):
        toolchain = self.toolchain(symbol="1" * 64)
        before = self.stage_bytes()
        result = adapter.apply_stage(self.stage_request(self.host_patch(toolchain=toolchain)))
        self.assertEqual(result["status"], "TOOL_ERROR")
        self.assertIn("REPAIR_TOOL_UNAVAILABLE", self.codes(result))
        self.assertEqual(self.call_log(), [])
        self.assertEqual(self.stage_bytes(), before)

    def test_an_akcli_that_changes_between_the_two_reads_is_a_tool_error(self):
        """The one toolchain property that genuinely cannot be settled before the write."""
        real = adapter._native_read
        seen = []

        def drifting(toolchain, root, relative, artifact_root):
            result = real(toolchain, root, relative, artifact_root)
            seen.append(result)
            if result["status"] == "PASS" and len(seen) == 2:
                probe = dict(result["tool"] or {})
                probe["artifact_sha256"] = "2" * 64
                result = dict(result, tool=probe)
            return result

        with mock.patch.object(adapter, "_native_read", side_effect=drifting):
            result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "TOOL_ERROR")
        self.assertIn("REPAIR_TOOL_UNAVAILABLE", self.codes(result))
        self.assertNotEqual(result["status"], "APPLIED_TO_STAGE")

    def test_a_tampered_host_patch_is_input_drift(self):
        patch = self.host_patch()
        patch["round_id"] = "ROUND-2"
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))

    def test_missing_write_authority_is_refused(self):
        patch = self.host_patch()
        patch["authority"]["decisions"] = [{"capability": "TOOL_EXECUTE", "effect": "ALLOW"}]
        patch["patch_sha256"] = canonical_sha256(
            "patch", {key: value for key, value in patch.items() if key != "patch_sha256"})
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_AUTH_DENIED", self.codes(result))

    def test_an_op_list_that_disagrees_with_the_proposal_is_input_drift(self):
        patch = self.host_patch(ops=[{"op": "place_component"}, {"op": "add_net_label"}])
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))

    def test_the_same_operation_with_different_arguments_is_input_drift(self):
        disk_ops = [{"op": "add_net_label", "name": "GND", "at": "U1.44"}]
        with open(self.oplist_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"protocol_version": 2, "target_format": "kicad", "ops": disk_ops}, handle)
        patch = self.host_patch(ops=[{"op": "add_net_label", "name": "BOOT0", "at": "U1.44"}])
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))
        self.assertEqual(self.call_log(), [])

    def test_a_proposal_that_does_not_match_its_own_digest_is_input_drift(self):
        patch = self.host_patch()
        patch["proposal_sha256"] = "0" * 64
        patch["patch_sha256"] = canonical_sha256(
            "patch", {key: value for key, value in patch.items() if key != "patch_sha256"})
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))
        self.assertEqual(self.call_log(), [])

    def test_malformed_nested_inputs_are_blocked_without_raising(self):
        mutations = [{"proposal": []},
                     {"proposal": {"oplist": []}},
                     {"proposal": {"oplist": {"protocol_version": 2, "target_format": "kicad",
                                              "ops": [{"op": "delete_object", "uuid": "u",
                                                       "cascade": True}]}}},
                     {"base": []},
                     {"authority": {"context_digest": "0" * 64,
                                    "resolved_authorization_refs": "not-a-list",
                                    "decisions": []}},
                     {"authority": {"context_digest": "0" * 64,
                                    "resolved_authorization_refs": ["host:ledger:1"],
                                    "decisions": [{}]}},
                     {"policy": {"id": "POLICY-1", "file_sha256": "0" * 64,
                                 "bound_rule_id": "DC-04"}}]
        for mutation in mutations:
            patch = self.host_patch()
            patch.update(mutation)
            if "proposal" in mutation:
                patch["proposal_sha256"] = canonical_sha256("proposal", patch["proposal"])
            patch["patch_sha256"] = canonical_sha256(
                "patch", {key: value for key, value in patch.items() if key != "patch_sha256"})
            result = adapter.apply_stage(self.stage_request(patch))
            self.assertEqual(result["status"], "BLOCKED", mutation)
            self.assertEqual(self.call_log(), [], mutation)

    def test_malformed_operations_are_blocked_without_raising(self):
        cases = [[{"op": "add_net_label", "name": "BOOT0"}],
                 [{"op": "explode", "uuid": "u"}],
                 [{"op": "delete_object", "uuid": "u", "cascade": True}],
                 [{"op": "place_component", "lib_id": "Device:R", "designator": "R9",
                   "x_mil": "1350", "y_mil": 10150, "value": "10k", "footprint": "f"}],
                 [{"op": "add_net_label", "name": "n", "at": "not-a-pin"}],
                 [{"op": "add_net_label", "name": "n", "at": "U1.44", "scope": "global"}]]
        for ops in cases:
            result = adapter.apply_stage(self.stage_request(self.host_patch(ops=ops)))
            self.assertEqual(result["status"], "BLOCKED", ops)
            self.assertEqual(self.call_log(), [], ops)

    def test_an_op_list_that_escapes_through_a_linked_directory_is_blocked(self):
        outside = os.path.join(self.root, "outside")
        os.makedirs(outside)
        with open(os.path.join(outside, "oplist.json"), "w", encoding="utf-8",
                  newline="\n") as handle:
            json.dump({"protocol_version": 2, "target_format": "kicad", "ops": self.oplist_ops},
                      handle)
        link = os.path.join(self.stage, "linked")
        if _make_directory_link(outside, link) is None:
            self.skipTest("this platform cannot create a directory link without elevation")
        request = self.stage_request()
        request["oplist_path"] = os.path.join(link, "oplist.json")
        result = adapter.apply_stage(request)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))
        self.assertEqual(self.call_log(), [])

    def test_an_op_list_outside_the_stage_root_is_refused(self):
        outside = os.path.join(self.root, "outside.json")
        with open(outside, "w", encoding="utf-8") as handle:
            json.dump({"ops": self.oplist_ops}, handle)
        request = self.stage_request()
        request["oplist_path"] = outside
        result = adapter.apply_stage(request)
        self.assertEqual(result["status"], "BLOCKED")

    def test_a_stage_target_escaping_its_root_is_refused(self):
        request = self.stage_request()
        request["stage_target"] = "../escape.kicad_sch"
        result = adapter.apply_stage(request)
        self.assertEqual(result["status"], "BLOCKED")

    def test_a_stale_proposal_base_is_input_drift(self):
        patch = self.host_patch()
        _insert_into_document(self.target, ["00000000-0000-4000-8000-000000000009"])
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))
        self.assertEqual(self.call_log(), [])

    def test_a_proposal_that_disagrees_with_the_host_patch_is_input_drift(self):
        for mutation in ({"context_id": "CTX-2"}, {"target": "design/other.kicad_sch"}):
            patch = self.host_patch()
            patch["proposal"].update(mutation)
            patch["proposal_sha256"] = canonical_sha256("proposal", patch["proposal"])
            patch["patch_sha256"] = canonical_sha256(
                "patch", {key: value for key, value in patch.items() if key != "patch_sha256"})
            result = adapter.apply_stage(self.stage_request(patch))
            self.assertEqual(result["status"], "BLOCKED", mutation)
            self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))
            self.assertEqual(self.call_log(), [], mutation)

    def test_a_conflicting_or_duplicated_authority_decision_is_refused(self):
        mutations = [[{"capability": "TOOL_EXECUTE", "effect": "ALLOW"},
                      {"capability": "TOOL_EXECUTE", "effect": "DENY"},
                      {"capability": "FILE_WRITE", "effect": "ALLOW"}],
                     [{"capability": "TOOL_EXECUTE", "effect": "ALLOW"},
                      {"capability": "TOOL_EXECUTE", "effect": "ALLOW"},
                      {"capability": "FILE_WRITE", "effect": "ALLOW"}],
                     [{"capability": "TOOL_EXECUTE", "effect": "ALLOW"},
                      {"capability": "FILE_WRITE", "effect": "ALLOW"},
                      {"capability": "HOUSEKEEPING", "effect": "DENY"}]]
        for decisions in mutations:
            patch = self.host_patch()
            patch["authority"]["decisions"] = decisions
            patch["patch_sha256"] = canonical_sha256(
                "patch", {key: value for key, value in patch.items() if key != "patch_sha256"})
            result = adapter.apply_stage(self.stage_request(patch))
            self.assertEqual(result["status"], "BLOCKED", decisions)
            self.assertIn("REPAIR_AUTH_DENIED", self.codes(result))
            self.assertEqual(self.call_log(), [], decisions)

    def test_a_cross_drive_op_list_is_an_input_error_not_a_crash(self):
        other = os.path.join(self.root, "other-drive")
        os.makedirs(other)
        op_list = os.path.join(other, "oplist.json")
        with open(op_list, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({"protocol_version": 2, "target_format": "kicad", "ops": self.oplist_ops},
                      handle)
        request = self.stage_request()
        request["oplist_path"] = op_list
        with mock.patch.object(adapter.os.path, "commonpath",
                               side_effect=ValueError("Paths don't have the same drive")):
            result = adapter.apply_stage(request)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))
        self.assertEqual(self.call_log(), [])

    def test_a_receipt_only_no_connect_conflict_is_an_inconsistency(self):
        self.mode = "receipt-only-nc"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_TOOL_PROTOCOL_ERROR", self.codes(result))

    def test_a_receipt_that_names_an_object_it_never_created_is_blocked(self):
        self.mode = "uuid-mismatch"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_DELTA_MISMATCH", self.codes(result))

    def test_a_created_object_nobody_reported_is_blocked(self):
        self.mode = "unreported-object"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_DELTA_MISMATCH", self.codes(result))

    def test_a_non_canonical_created_uuid_is_a_tool_error(self):
        self.mode = "bad-uuid"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "TOOL_ERROR")
        self.assertIn("REPAIR_TOOL_PROTOCOL_ERROR", self.codes(result))
        self.assertNotEqual(result["status"], "APPLIED_TO_STAGE")

    def test_a_created_uuid_reported_twice_is_a_tool_error(self):
        self.mode = "duplicate-uuid"
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "TOOL_ERROR")
        self.assertIn("REPAIR_TOOL_PROTOCOL_ERROR", self.codes(result))
        self.assertNotEqual(result["status"], "APPLIED_TO_STAGE")
        # the write did add real, distinct objects: the refusal is the malformed
        # reported set, not a missing delta
        self.assertNotIn("REPAIR_DELTA_MISMATCH", self.codes(result))

    def test_a_native_read_from_another_revision_never_supplies_the_uuid_delta(self):
        real = adapter._native_read

        def drifted(toolchain, root, relative, artifact_root):
            result = real(toolchain, root, relative, artifact_root)
            if result["status"] == "PASS":
                result = dict(result, source_sha256="0" * 64)
            return result

        with mock.patch.object(adapter, "_native_read", side_effect=drifted):
            result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_SOURCE_UNBOUND", self.codes(result))
        self.assertNotEqual(result["status"], "APPLIED_TO_STAGE")

    def test_only_the_after_read_drifting_is_also_unbound(self):
        real = adapter._native_read
        calls = []

        def drifted(toolchain, root, relative, artifact_root):
            result = real(toolchain, root, relative, artifact_root)
            calls.append(result.get("source_sha256"))
            if result["status"] == "PASS" and len(calls) == 2:
                result = dict(result, source_sha256="1" * 64)
            return result

        with mock.patch.object(adapter, "_native_read", side_effect=drifted):
            result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_SOURCE_UNBOUND", self.codes(result))
        self.assertNotEqual(result["status"], "APPLIED_TO_STAGE")

    def test_the_report_and_the_artifact_agree_on_a_healthy_write(self):
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "APPLIED_TO_STAGE", result["reasons"])
        reported = {item for row in result["tool"]["op_results"]
                    for item in row["created_uuids"]}
        before = {row["identity"] for row in result["native_before"]["observation"]["source_objects"]}
        after = {row["identity"] for row in result["native_after"]["observation"]["source_objects"]}
        self.assertEqual(reported, after - before)
        self.assertTrue(reported)

    def test_p1_an_operation_outside_operation_v1_never_reaches_the_writer(self):
        """The real collapsed-wire shape: exit 0, applied, ok op, no byte change."""
        ops = [{"op": "add_wire", "vertices": [[1000, 1000], [1000, 1000]]}]
        result = adapter.apply_stage(self.stage_request(self.host_patch(ops=ops)))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))
        self.assertEqual(self.call_log(), [])

    def test_malformed_stage_requests_are_blocked_without_raising(self):
        mutations = [{"txn_id": []}, {"txn_id": "bad id!"}, {"oplist_path": 5},
                     {"native_artifact_root": None}, {"stage_root": "relative/path"},
                     {"stage_target": 42}, {"host_patch": []}]
        for mutation in mutations:
            request = self.stage_request()
            request.update(mutation)
            result = adapter.apply_stage(request)
            self.assertEqual(result["status"], "BLOCKED", mutation)
            self.assertEqual(self.call_log(), [], mutation)

    def test_a_missing_stage_target_is_blocKed(self):
        request = self.stage_request()
        request["stage_target"] = "absent.kicad_sch"
        result = adapter.apply_stage(request)
        self.assertEqual(result["status"], "BLOCKED")


class StubPerturbationTests(AdapterCase):
    """C4-P2/P7 perturbations the live writer cannot be made to produce.

    A pinned akcli 0.21.0 always answers with a complete, well-formed receipt on the
    success path, so "a forged flag" and "two batches in one op-list" exist only at
    the software boundary.  These are labelled stub-level deliberately: they qualify
    the adapter's own refusal, not the pinned tool's behaviour.  The receipt-level
    C4-P2/P4 cases (applied missing/false, op_results incomplete, op status=error)
    and the C4-P8 connectivity cases live in StrictReceiptTests.
    """

    def test_p2_a_json_forged_authorized_flag_is_refused(self):
        """Authority enters through authority.decisions, never a bare forgeable flag."""
        patch = self.host_patch()
        patch["authorized"] = True
        patch["patch_sha256"] = canonical_sha256(
            "patch", {key: value for key, value in patch.items() if key != "patch_sha256"})
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))
        self.assertNotEqual(result["status"], "APPLIED_TO_STAGE")
        self.assertEqual(self.call_log(), [])

    def test_p7_an_op_list_carrying_two_batches_is_refused(self):
        """The contract is single-batch, so a two-batch container never reaches a writer."""
        ops = self.oplist_ops
        proposal = self.proposal()
        proposal["oplist"] = {"protocol_version": 2, "target_format": "kicad",
                              "batches": [ops[:1], ops[1:]]}
        patch = self.host_patch()
        patch["proposal"] = proposal
        patch["proposal_sha256"] = canonical_sha256("proposal", proposal)
        patch["patch_sha256"] = canonical_sha256(
            "patch", {key: value for key, value in patch.items() if key != "patch_sha256"})
        result = adapter.apply_stage(self.stage_request(patch))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_INPUT_DRIFT", self.codes(result))
        self.assertEqual(self.call_log(), [])


class ExceptionWriterTests(AdapterCase):
    """the constrained writer has no applied field and is never trusted blindly."""

    rule = "E1"
    route = "CONSTRAINED_EXCEPTION"

    def test_the_api_path_reports_tool_applied_null_and_still_verifies_the_bytes(self):
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "APPLIED_TO_STAGE", result["reasons"])
        self.assertIsNone(result["tool"]["tool_applied"])
        self.assertEqual(result["tool"]["mode"], "PYTHON_WRITER")
        self.assertTrue(result["changed"])

    def test_a_non_empty_api_result_without_a_byte_change_is_blocked(self):
        payload = sidecar()
        payload["writer"] = {"change_bytes": False}
        self.write_stage(payload)
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_EFFECT_MISMATCH", self.codes(result))

    def test_an_api_op_error_is_blocked(self):
        payload = sidecar()
        payload["writer"] = {"op_results": [{"op_index": 0, "op": "delete_object",
                                             "status": "error", "error_code": "OP_FAILED"}]}
        self.write_stage(payload)
        result = adapter.apply_stage(self.stage_request())
        self.assertEqual(result["status"], "BLOCKED")

    def test_a_symlinked_worker_interpreter_is_accepted(self):
        link = os.path.join(self.root, "python-link")
        try:
            os.symlink(sys.executable, link)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("this platform cannot create a file symlink without elevation")
        toolchain = self.toolchain()
        toolchain["worker_python"] = link
        result = adapter.apply_stage(self.stage_request(self.host_patch(toolchain=toolchain)))
        self.assertEqual(result["status"], "APPLIED_TO_STAGE", result["reasons"])

    def test_exactly_one_worker_write_call_is_made(self):
        adapter.apply_stage(self.stage_request())
        self.assertEqual(self.call_log(), ["worker-apply"])


class ReadNativeTests(AdapterCase):
    """the read path is closed, authorized and path-confined."""

    def binding(self, toolchain=None):
        toolchain = toolchain or self.toolchain()
        return {"run_id": "RUN-1", "candidate_id": "CAND-1", "txn_id": "TXN-1",
                "toolchain_manifest": toolchain,
                "toolchain_sha256": adapter._toolchain_digest(toolchain),
                "read_authorization": {"context_digest": canonical_sha256("context", "C"),
                                       "resolved_authorization_refs": ["host:ledger:1"],
                                       "decisions": []}}

    def test_a_read_returns_a_normalized_native_observation(self):
        result = adapter.read_native({"host_binding": self.binding(),
                                      "absolute_read_root": self.stage,
                                      "relative_target": "fault.kicad_sch"},
                                     artifact_root=self.artifacts)
        self.assertEqual(result["status"], "PASS", result["reasons"])
        observation = result["observation"]
        self.assertEqual(len(observation["components"]), 1)
        self.assertEqual(observation["components"][0]["reference"], "R9")
        self.assertTrue(observation["coverage"]["complete"])
        with open(self.target, "rb") as handle:
            self.assertEqual(observation["source_sha256"], hash_bytes(handle.read()))

    def test_a_source_that_changed_after_the_worker_read_is_not_bound(self):
        """The worker's inventories and the host's parse must describe one revision."""
        real = adapter._read_bytes

        def changed(path):
            return real(path) + b"\n"

        with mock.patch.object(adapter, "_read_bytes", side_effect=changed):
            result = adapter.read_native({"host_binding": self.binding(),
                                          "absolute_read_root": self.stage,
                                          "relative_target": "fault.kicad_sch"},
                                         artifact_root=self.artifacts)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_SOURCE_UNBOUND", [row["code"] for row in result["reasons"]])
        # no observation is handed out from an unbound revision
        self.assertIsNone(result["observation"])

    def test_a_read_without_host_authorization_is_blocked(self):
        binding = self.binding()
        binding["read_authorization"]["resolved_authorization_refs"] = []
        result = adapter.read_native({"host_binding": binding, "absolute_read_root": self.stage,
                                      "relative_target": "fault.kicad_sch"},
                                     artifact_root=self.artifacts)
        self.assertEqual(result["status"], "BLOCKED")

    def test_a_read_outside_its_root_is_blocked(self):
        result = adapter.read_native({"host_binding": self.binding(),
                                      "absolute_read_root": self.stage,
                                      "relative_target": "../outside.kicad_sch"},
                                     artifact_root=self.artifacts)
        self.assertEqual(result["status"], "BLOCKED")

    def test_a_reader_inventory_disagreement_is_unknown_not_complete(self):
        payload = sidecar()
        payload["metadata"] = {"component_count": 5, "pin_count": 5}
        self.write_stage(payload)
        result = adapter.read_native({"host_binding": self.binding(),
                                      "absolute_read_root": self.stage,
                                      "relative_target": "fault.kicad_sch"},
                                     artifact_root=self.artifacts)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("REPAIR_COVERAGE_INCOMPLETE", [row["code"] for row in result["reasons"]])

    def test_a_reader_that_offers_no_cross_check_is_unknown_not_complete(self):
        payload = sidecar()
        payload["metadata"] = {}
        payload["primitive_pin_count"] = 0
        self.write_stage(payload)
        result = adapter.read_native({"host_binding": self.binding(),
                                      "absolute_read_root": self.stage,
                                      "relative_target": "fault.kicad_sch"},
                                     artifact_root=self.artifacts)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("REPAIR_COVERAGE_INCOMPLETE", [row["code"] for row in result["reasons"]])

    def test_the_read_reports_connectivity_findings(self):
        self.write_stage(sidecar(connectivity=[{"code": "DANGLING_ENDPOINT",
                                                "severity": "WARNING", "message": "x"}]))
        result = adapter.read_native({"host_binding": self.binding(),
                                      "absolute_read_root": self.stage,
                                      "relative_target": "fault.kicad_sch"},
                                     artifact_root=self.artifacts)
        self.assertEqual(result["status"], "PASS", result["reasons"])
        self.assertEqual([row["code"] for row in result["connectivity_findings"]],
                         ["DANGLING_ENDPOINT"])


class SourceObjectParityTests(unittest.TestCase):
    """The native reader's top-level objects use C2's own source encoding.

    This card exists because source_objects() once described a single document root
    where observe_source() saw 114 objects.  Pinning both readers to one encoding is
    what stops the traversal or the AST helper drifting apart again.
    """

    FIXTURE = os.path.join(REPO, "tests", "fixtures", "repair_pr1", "native",
                           "DC-04", "fault.kicad_sch")

    def test_the_native_reader_reuses_the_c2_source_object_encoding(self):
        with open(self.FIXTURE, "rb") as handle:
            raw = handle.read()
        native = adapter.source_objects(raw)
        source = observe_source(raw)["source_objects"]
        self.assertGreater(len(native), 1)
        self.assertEqual(len(native), len(source))
        # normalize_observation sorts source_objects, so the two readers are compared
        # keyed by identity; each object's encoding has to match exactly.
        self.assertEqual({row["identity"]: (row["kind"], row["semantic_ast_sha256"])
                          for row in native},
                         {row["identity"]: (row["kind"], row["semantic_ast_sha256"])
                          for row in source})


class NormalizationTests(unittest.TestCase):
    def test_note_is_normalized_to_info_with_the_raw_level_kept(self):
        findings, status = adapter.normalize_connectivity(
            [{"code": "X", "severity": "NOTE", "message": "m"}])
        self.assertEqual(status, "OK")
        self.assertEqual(findings[0]["severity"], "INFO")
        self.assertEqual(findings[0]["raw_severity"], "NOTE")

    def test_a_background_frozen_warning_is_the_only_tolerated_warning(self):
        before = [{"code": "DANGLING_ENDPOINT", "severity": "WARNING", "message": "known",
                   "object_id": "R1"}]
        after = [{"code": "DANGLING_ENDPOINT", "severity": "WARNING", "message": "known",
                  "object_id": "R1"}]
        self.assertEqual(adapter.connectivity_verdict(before, after)[0], "BLOCKED")
        self.assertEqual(
            adapter.connectivity_verdict(before, after,
                                         background={("DANGLING_ENDPOINT", "R1")})[0], "PASS")
        moved = [{"code": "DANGLING_ENDPOINT", "severity": "WARNING", "message": "known",
                  "object_id": "U7"}]
        status, reasons = adapter.connectivity_verdict(
            before, moved, background={("DANGLING_ENDPOINT", "R1")})
        self.assertEqual(status, "BLOCKED")
        self.assertIn("new WARNING", " | ".join(row["detail"] for row in reasons))

    def test_an_unknown_severity_is_indeterminate(self):
        findings, status = adapter.normalize_connectivity(
            [{"code": "X", "severity": "CATASTROPHIC", "message": "m"}])
        self.assertEqual(status, "UNKNOWN")
        self.assertEqual(findings[0]["severity"], "UNKNOWN")

    def test_duplicate_json_keys_are_refused(self):
        with self.assertRaises(adapter.AdapterInputError):
            adapter.parse_json_bytes(b'{"a": 1, "a": 2}', "test")

    def test_non_finite_json_constants_are_refused(self):
        with self.assertRaises(adapter.AdapterInputError):
            adapter.parse_json_bytes(b'{"a": NaN}', "test")

    def test_the_frozen_strict_argv_is_the_contract_command(self):
        toolchain = {"launcher_argv": [], "akcli_executable": os.path.abspath("akcli")}
        argv = adapter._strict_argv(toolchain, "stage.kicad_sch", "ops.json")
        self.assertEqual(argv[1:], ["draw", "stage.kicad_sch", "--ops", "ops.json",
                                    "--apply", "--strict-nets", "--no-erc", "--json"])


class _NativeToolchainMixin(object):
    """Shared opt-in harness for the real pinned toolchain."""

    FIXTURES = os.path.join(REPO, "tests", "fixtures", "repair_pr1", "native")

    def setUp(self):
        if os.environ.get("AEDL_PR1_NATIVE") != "1":
            self.skipTest("native qualification is not opted in (AEDL_PR1_NATIVE=1)")
        self.python = os.environ.get("AEDL_AKCLI_PYTHON")
        if not self.python or not os.path.isfile(self.python):
            self.fail("AEDL_PR1_NATIVE=1 requires AEDL_AKCLI_PYTHON to point at the pinned interpreter")
        self.root = tempfile.mkdtemp(prefix="aedl-c4-native-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def toolchain(self, cli):
        return {"version": 1, "akcli_executable": cli, "akcli_version": "0.21.0",
                "akcli_artifact_sha256": "0" * 64,
                "akcli_upstream_commit": adapter.AKCLI_UPSTREAM_COMMIT,
                "worker_python": self.python, "symbol_digest": "0" * 64,
                "launcher_argv": [], "timeout_seconds": 60, "environment": {}}

    def _akcli(self):
        import shutil as _shutil
        cli = _shutil.which("akcli") or os.path.join(os.path.dirname(self.python), "akcli.exe")
        if not os.path.isfile(cli):
            self.fail("the pinned akcli executable was not found next to the interpreter")
        return cli

    def _measure(self, cli, case):
        """Freeze the manifest from what the real toolchain actually reports."""
        import shutil as _shutil
        stage = os.path.join(self.root, "measure-" + case)
        os.makedirs(stage)
        _shutil.copy2(os.path.join(self.FIXTURES, case, "fault.kicad_sch"),
                      os.path.join(stage, "fault.kicad_sch"))
        toolchain = self.toolchain(cli)
        binding = {"run_id": "RUN-MEASURE", "candidate_id": "CAND-1", "txn_id": "TXN-1",
                   "toolchain_manifest": toolchain,
                   "toolchain_sha256": adapter._toolchain_digest(toolchain),
                   "read_authorization": {"context_digest": canonical_sha256("context", case),
                                          "resolved_authorization_refs": ["host:ledger:1"],
                                          "decisions": []}}
        read = adapter.read_native({"host_binding": binding, "absolute_read_root": stage,
                                    "relative_target": "fault.kicad_sch"},
                                   artifact_root=os.path.join(self.root, "artifacts"))
        self.assertEqual(read["status"], "PASS", read["reasons"])
        probe = read["tool"]
        self.assertEqual(probe["version"], adapter.AKCLI_VERSION)
        self.assertRegex(probe["artifact_sha256"] or "", r"^[0-9a-f]{64}$")
        self.assertRegex(probe["symbol_digest"] or "", r"^[0-9a-f]{64}$")
        toolchain["akcli_artifact_sha256"] = probe["artifact_sha256"]
        toolchain["symbol_digest"] = probe["symbol_digest"]
        return toolchain

    def _patch(self, toolchain, ops, rule, stage, ctx="CTX-1", route="STRICT"):
        """Build a contract-shaped HostPatch over a prepared stage.

        route defaults to STRICT so every existing caller is unchanged; the E1/E2/E3
        rules reach the constrained writer and need CONSTRAINED_EXCEPTION here.
        """
        with open(os.path.join(stage, "fault.kicad_sch"), "rb") as handle:
            base_source_sha256 = hash_bytes(handle.read())
        proposal = {"schema_version": 1, "context_id": ctx, "target": "design/fault.kicad_sch",
                    "base_source_sha256": base_source_sha256, "decision": "PATCH",
                    "oplist": {"protocol_version": 2, "target_format": "kicad", "ops": ops},
                    "diagnosis": []}
        body = {"schema_version": 1, "run_id": "RUN-1", "candidate_id": "CAND-1",
                "round_id": "ROUND-1", "patch_id": "PATCH-" + rule, "context_id": ctx,
                "proposal": proposal,
                "proposal_sha256": canonical_sha256("proposal", proposal),
                "target": "design/fault.kicad_sch",
                "base": {"files": {}, "topology_sha256": canonical_sha256("topology", "T")},
                "policy": {"id": "POLICY-1", "file_sha256": canonical_sha256("manifest", "F"),
                           "bound_rule_id": rule,
                           "bound_policy_sha256": canonical_sha256("policy-bound", "B")},
                "authority": {"context_digest": canonical_sha256("context", "C"),
                              "resolved_authorization_refs": ["host:ledger:1"],
                              "decisions": [{"capability": "TOOL_EXECUTE", "effect": "ALLOW"},
                                            {"capability": "FILE_WRITE", "effect": "ALLOW"}]},
                "toolchain_manifest": toolchain,
                "toolchain_sha256": adapter._toolchain_digest(toolchain),
                "route": route, "bound_policy": {"version": 1}}
        body["patch_sha256"] = canonical_sha256("patch", body)
        return body

    def _stage_request(self, body, stage, artifact_root):
        return {"host_patch": body, "txn_id": "TXN-1", "stage_root": stage,
                "stage_target": "fault.kicad_sch",
                "oplist_path": os.path.join(stage, "oplist.json"),
                "native_artifact_root": artifact_root}

    def _fixture_ops(self, case):
        with open(os.path.join(self.FIXTURES, case, "repair_ops.json"), encoding="utf-8") as handle:
            return json.load(handle)["ops"]

    def _stage(self, case, name, ops=None):
        """A scratch copy of a frozen fixture, optionally with its own op-list.

        Perturbations only ever act on copies, so the frozen fixtures stay read-only.
        """
        stage = os.path.join(self.root, name)
        os.makedirs(stage, exist_ok=True)
        shutil.copy2(os.path.join(self.FIXTURES, case, "fault.kicad_sch"),
                     os.path.join(stage, "fault.kicad_sch"))
        if ops is None:
            shutil.copy2(os.path.join(self.FIXTURES, case, "repair_ops.json"),
                         os.path.join(stage, "oplist.json"))
        else:
            with open(os.path.join(stage, "oplist.json"), "w", encoding="utf-8",
                      newline="\n") as handle:
                json.dump({"protocol_version": 2, "target_format": "kicad", "ops": ops}, handle)
        return stage

    def _runs(self):
        """Record every subprocess the adapter starts, so write calls can be counted.

        The contract allows exactly one write call per round; that is an observable
        property, so the qualification measures it rather than assuming it.
        """
        calls = []
        real = adapter.subprocess.run

        def record(argv, *args, **kwargs):
            calls.append(list(argv))
            return real(argv, *args, **kwargs)

        return calls, mock.patch.object(adapter.subprocess, "run", side_effect=record)

    @staticmethod
    def _draws(calls):
        return [row for row in calls if "draw" in row]

    @staticmethod
    def _exception_writes(calls):
        return [row for row in calls if "APPLY_EXCEPTION" in row]

    @staticmethod
    def _source_sha256(path):
        with open(path, "rb") as handle:
            return hash_bytes(handle.read())


class NativeQualificationTests(_NativeToolchainMixin, unittest.TestCase):
    """Real pinned toolchain. Opt-in: AEDL_PR1_NATIVE=1 and AEDL_AKCLI_PYTHON."""

    # Independently recorded by the 2026-09-16 cross-machine reproduction of the
    # same pinned toolchain; a mismatch means this adapter changed the bytes.
    RECORDED = {"DC-04": ("655F585DF2E913A8AAADE3D8A0A291591EC1E7E275920006A54AEC8F75DDE7A0",
                          "2F660180AB180009656DA7D47E7B686A75CE42CE9084B610904E2B6D28DB99C6"),
                "DC-05": ("08393EE96D2D5F2AB15B721FC962A2C6E731330B855A26845D6F530DBA4EBF16",
                          "033E4EFA94BC800FA60D8CB66182BA35478C6EFBD85213DB0A6C87A3C828F83B")}

    def test_the_pinned_reader_produces_a_normalized_observation_for_every_case(self):
        import shutil as _shutil
        cli = _shutil.which("akcli") or os.path.join(
            os.path.dirname(self.python), "akcli.exe")
        if not os.path.isfile(cli):
            self.fail("the pinned akcli executable was not found next to the interpreter")
        for case in ("DC-01", "DC-02", "DC-03", "DC-04", "DC-05"):
            stage = os.path.join(self.root, case)
            os.makedirs(stage)
            source = os.path.join(self.FIXTURES, case, "fault.kicad_sch")
            _shutil.copy2(source, os.path.join(stage, "fault.kicad_sch"))
            toolchain = self.toolchain(cli)
            binding = {"run_id": "RUN-1", "candidate_id": "CAND-1", "txn_id": "TXN-1",
                       "toolchain_manifest": toolchain,
                       "toolchain_sha256": adapter._toolchain_digest(toolchain),
                       "read_authorization": {"context_digest": canonical_sha256("context", case),
                                              "resolved_authorization_refs": ["host:ledger:1"],
                                              "decisions": []}}
            result = adapter.read_native({"host_binding": binding, "absolute_read_root": stage,
                                          "relative_target": "fault.kicad_sch"},
                                         artifact_root=os.path.join(self.root, "artifacts"))
            self.assertEqual(result["status"], "PASS",
                             "%s: %s" % (case, result["reasons"]))

    def test_the_real_strict_route_applies_dc04_and_dc05_byte_identically(self):
        import shutil as _shutil
        cli = self._akcli()
        for case in ("DC-04", "DC-05"):
            toolchain = self._measure(cli, case)
            stage = os.path.join(self.root, "stage-" + case)
            os.makedirs(stage)
            _shutil.copy2(os.path.join(self.FIXTURES, case, "fault.kicad_sch"),
                          os.path.join(stage, "fault.kicad_sch"))
            _shutil.copy2(os.path.join(self.FIXTURES, case, "repair_ops.json"),
                          os.path.join(stage, "oplist.json"))
            with open(os.path.join(stage, "oplist.json"), encoding="utf-8") as handle:
                ops = json.load(handle)["ops"]
            body = self._patch(toolchain, ops, case, stage)
            result = adapter.apply_stage(self._stage_request(
                body, stage, os.path.join(self.root, "artifacts-" + case)))
            self.assertEqual(result["status"], "APPLIED_TO_STAGE",
                             "%s: %s" % (case, result["reasons"]))
            recorded_before, recorded_after = self.RECORDED[case]
            self.assertEqual(result["before_source_sha256"].upper(), recorded_before)
            self.assertEqual(result["after_source_sha256"].upper(), recorded_after)
            self.assertEqual([row["status"] for row in result["tool"]["op_results"]],
                             ["ok"] * len(ops))
            # contract section 8: the reported created UUIDs are exactly the
            # top-level objects this write added
            reported = {item for row in result["tool"]["op_results"]
                        for item in row["created_uuids"]}
            before_objects = {row["identity"]
                              for row in result["native_before"]["observation"]["source_objects"]}
            after_objects = {row["identity"]
                             for row in result["native_after"]["observation"]["source_objects"]}
            self.assertEqual(reported, after_objects - before_objects)
            self.assertEqual(len(reported), len(ops))


class NativePerturbationTests(_NativeToolchainMixin, unittest.TestCase):
    """C4-P1..P8 native perturbation qualification (B5 criteria sheet, section C4).

    Same opt-in gates as NativeQualificationTests: these drive the real pinned
    toolchain, so they must never run by accident in the ordinary suite, and with
    AEDL_PR1_NATIVE=1 a missing or wrong toolchain fails instead of skipping.
    """

    # Captured 2026-09-17 with the pinned, unpatched akcli 0.21.0: C1.1 is already
    # on +5V, so the writer reports status/applied "applied" with a created UUID,
    # an ok op and zero connectivity findings -- while the artefact never changes.
    P1_REPEAT_LABEL = [{"op": "add_net_label", "name": "+5V", "at": "C1.1"}]

    def test_the_writer_is_never_started_when_the_symbol_digest_does_not_match(self):
        """PRECHECK settles the toolchain, so a mismatched tool must not write first.

        Regression for the ordering defect PR #78 found in the P6 qualification: the
        real write used to run to completion (exit 0, stage bytes already modified)
        before the digest comparison happened in the effect check.
        """
        import shutil as _shutil
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        toolchain["symbol_digest"] = "1" * 64
        stage = os.path.join(self.root, "precheck")
        os.makedirs(stage)
        _shutil.copy2(os.path.join(self.FIXTURES, "DC-04", "fault.kicad_sch"),
                      os.path.join(stage, "fault.kicad_sch"))
        _shutil.copy2(os.path.join(self.FIXTURES, "DC-04", "repair_ops.json"),
                      os.path.join(stage, "oplist.json"))
        with open(os.path.join(stage, "oplist.json"), encoding="utf-8") as handle:
            ops = json.load(handle)["ops"]
        body = self._patch(toolchain, ops, "DC-04", stage)
        with open(os.path.join(stage, "fault.kicad_sch"), "rb") as handle:
            before = handle.read()

        calls = []
        real = adapter.subprocess.run

        def record(argv, *args, **kwargs):
            calls.append(list(argv))
            return real(argv, *args, **kwargs)

        with mock.patch.object(adapter.subprocess, "run", side_effect=record):
            result = adapter.apply_stage(self._stage_request(
                body, stage, os.path.join(self.root, "artifacts-precheck")))

        self.assertEqual(result["status"], "TOOL_ERROR", result["reasons"])
        self.assertIn("REPAIR_TOOL_UNAVAILABLE", [row["code"] for row in result["reasons"]])
        # the strict writer was never invoked ...
        self.assertEqual([row for row in calls if "draw" in row], [])
        # ... and the stage is byte-identical to what it was before the attempt
        with open(os.path.join(stage, "fault.kicad_sch"), "rb") as handle:
            self.assertEqual(handle.read(), before)

    def test_the_native_read_matches_the_c2_source_objects(self):
        """C4's own observation must describe the same objects C2's reader sees."""
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        stage = os.path.join(self.root, "parity")
        os.makedirs(stage)
        shutil.copy2(os.path.join(self.FIXTURES, "DC-04", "fault.kicad_sch"),
                     os.path.join(stage, "fault.kicad_sch"))
        binding = {"run_id": "RUN-PARITY", "candidate_id": "CAND-1", "txn_id": "TXN-1",
                   "toolchain_manifest": toolchain,
                   "toolchain_sha256": adapter._toolchain_digest(toolchain),
                   "read_authorization": {"context_digest": canonical_sha256("context", "parity"),
                                          "resolved_authorization_refs": ["host:ledger:1"],
                                          "decisions": []}}
        read = adapter.read_native({"host_binding": binding, "absolute_read_root": stage,
                                    "relative_target": "fault.kicad_sch"},
                                   artifact_root=os.path.join(self.root, "artifacts-parity"))
        self.assertEqual(read["status"], "PASS", read["reasons"])
        with open(os.path.join(stage, "fault.kicad_sch"), "rb") as handle:
            raw = handle.read()
        self.assertEqual(read["observation"]["source_sha256"], hash_bytes(raw))
        native = read["observation"]["source_objects"]
        source = observe_source(raw)["source_objects"]
        self.assertGreater(len(native), 1)
        self.assertEqual([row["identity"] for row in native],
                         [row["identity"] for row in source])
        self.assertEqual([row["kind"] for row in native],
                         [row["kind"] for row in source])
        self.assertEqual([row["semantic_ast_sha256"] for row in native],
                         [row["semantic_ast_sha256"] for row in source])

    def test_p1_an_applied_receipt_with_an_unchanged_artifact_is_blocked(self):
        import shutil as _shutil
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        stage = os.path.join(self.root, "p1")
        os.makedirs(stage)
        _shutil.copy2(os.path.join(self.FIXTURES, "DC-04", "fault.kicad_sch"),
                      os.path.join(stage, "fault.kicad_sch"))
        with open(os.path.join(stage, "oplist.json"), "w", encoding="utf-8",
                  newline="\n") as handle:
            json.dump({"protocol_version": 2, "target_format": "kicad",
                       "ops": self.P1_REPEAT_LABEL}, handle)
        body = self._patch(toolchain, self.P1_REPEAT_LABEL, "DC-04", stage)
        result = adapter.apply_stage(self._stage_request(
            body, stage, os.path.join(self.root, "artifacts-p1")))
        # the pinned writer really does claim success ...
        self.assertIs(result["tool"]["tool_applied"], True)
        self.assertEqual([row["status"] for row in result["tool"]["op_results"]], ["ok"])
        self.assertEqual(result["tool"]["connectivity_findings"], [])
        # ... naming an object it never wrote: the UUID is deterministic for these
        # input bytes (two independent runs produced the same value), so it is
        # pinned rather than merely asserted non-empty
        self.assertEqual(result["tool"]["op_results"][0]["created_uuids"],
                         ["2b641f80-6d0c-53f9-b3d3-42a61cb19163"])
        # ... on an artefact that never changed ...
        self.assertFalse(result["changed"])
        # ... and the adapter refuses to call that an applied stage
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("REPAIR_EFFECT_MISMATCH",
                      [row["code"] for row in result["reasons"]])
    # Captured 2026-09-17 with the pinned akcli 0.21.0 on the frozen DC-04 fixture:
    # U1.6 carries a no_connect marker and sits on an unnamed net, so naming it GND
    # merges a named net and the strict route refuses before writing anything.
    P5_REFUSED_LABEL = [{"op": "add_net_label", "name": "GND", "at": "U1.6"}]

    def test_p5_a_refused_strict_write_is_never_retried_through_the_exception_writer(self):
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        stage = self._stage("DC-04", "p5", ops=self.P5_REFUSED_LABEL)
        body = self._patch(toolchain, self.P5_REFUSED_LABEL, "DC-04", stage)
        before = self._source_sha256(os.path.join(stage, "fault.kicad_sch"))
        calls, recorder = self._runs()
        with recorder:
            result = adapter.apply_stage(self._stage_request(
                body, stage, os.path.join(self.root, "artifacts-p5")))
        # the pinned writer really did refuse, before touching the artefact -- the red
        # is at the writer/refusal boundary, not an unrelated pre-write rejection
        self.assertEqual(result["status"], "BLOCKED", result["reasons"])
        self.assertEqual(result["tool"]["exit_code"], 6)
        self.assertIn("REPAIR_STRICT_REFUSED", [row["code"] for row in result["reasons"]])
        self.assertFalse(result["changed"])
        self.assertEqual(self._source_sha256(os.path.join(stage, "fault.kicad_sch")), before)
        # ... and the refusal is terminal: exactly one write call, no fallback route
        self.assertEqual(len(self._draws(calls)), 1, calls)
        self.assertEqual(self._exception_writes(calls), [])

    def test_p6_a_perturbed_symbol_digest_is_refused_not_silently_continued(self):
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        # the real toolchain still runs; only the host binding is perturbed
        toolchain["symbol_digest"] = "1" * 64
        ops = self._fixture_ops("DC-04")
        stage = self._stage("DC-04", "p6-digest")
        body = self._patch(toolchain, ops, "DC-04", stage)
        result = adapter.apply_stage(self._stage_request(
            body, stage, os.path.join(self.root, "artifacts-p6-digest")))
        self.assertEqual(result["status"], "TOOL_ERROR", result["reasons"])
        self.assertIn("REPAIR_TOOL_UNAVAILABLE", [row["code"] for row in result["reasons"]])
        self.assertNotEqual(result["status"], "APPLIED_TO_STAGE")
        # the real write itself succeeded (exit 0), so the refusal comes from the
        # perturbed binding and not from an unrelated early rejection
        self.assertEqual(result["tool"]["exit_code"], 0)

    def test_p6_a_perturbed_toolchain_version_is_refused_before_any_write(self):
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        toolchain["akcli_version"] = "0.19.0"
        ops = self._fixture_ops("DC-04")
        stage = self._stage("DC-04", "p6-version")
        body = self._patch(toolchain, ops, "DC-04", stage)
        calls, recorder = self._runs()
        with recorder:
            result = adapter.apply_stage(self._stage_request(
                body, stage, os.path.join(self.root, "artifacts-p6-version")))
        self.assertEqual(result["status"], "BLOCKED", result["reasons"])
        self.assertIn("REPAIR_INPUT_DRIFT", [row["code"] for row in result["reasons"]])
        self.assertEqual(self._draws(calls), [])

    def test_p7_the_frozen_route_issues_exactly_one_write_call_per_round(self):
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        ops = self._fixture_ops("DC-04")
        stage = self._stage("DC-04", "p7-single")
        body = self._patch(toolchain, ops, "DC-04", stage)
        calls, recorder = self._runs()
        with recorder:
            result = adapter.apply_stage(self._stage_request(
                body, stage, os.path.join(self.root, "artifacts-p7-single")))
        self.assertEqual(result["status"], "APPLIED_TO_STAGE", result["reasons"])
        self.assertEqual(len(self._draws(calls)), 1, calls)
        self.assertEqual(self._exception_writes(calls), [])

    def test_p7_splitting_the_batch_is_refused_and_is_not_equivalent(self):
        """One batch of three ops applies; the same ops sent as two batches do not."""
        cli = self._akcli()
        toolchain = self._measure(cli, "DC-04")
        ops = self._fixture_ops("DC-04")
        first, second = ops[:1], ops[1:]

        single = self._stage("DC-04", "p7-one-batch")
        applied = adapter.apply_stage(self._stage_request(
            self._patch(toolchain, ops, "DC-04", single), single,
            os.path.join(self.root, "artifacts-p7-one")))
        self.assertEqual(applied["status"], "APPLIED_TO_STAGE", applied["reasons"])

        # the split: batch 1 leaves the artefact in a state the single batch never
        # reaches (the placed part has dangling unnamed nets), and batch 2 is
        # refused by the pinned writer
        split = self._stage("DC-04", "p7-two-batches", ops=first)
        part_one = adapter.apply_stage(self._stage_request(
            self._patch(toolchain, first, "DC-04", split), split,
            os.path.join(self.root, "artifacts-p7-two-a")))
        self.assertEqual(part_one["status"], "APPLIED_TO_STAGE", part_one["reasons"])
        # batch 1 really did land: the artefact moved away from its base bytes, so a
        # rejected later batch leaves a half-applied design rather than nothing
        self.assertTrue(part_one["changed"])

        # batch 2 is a second write call on the same artefact, with its own op-list
        with open(os.path.join(split, "oplist.json"), "w", encoding="utf-8",
                  newline="\n") as handle:
            json.dump({"protocol_version": 2, "target_format": "kicad", "ops": second}, handle)
        part_two = adapter.apply_stage(self._stage_request(
            self._patch(toolchain, second, "DC-04", split), split,
            os.path.join(self.root, "artifacts-p7-two-b")))
        self.assertEqual(part_two["status"], "BLOCKED", part_two["reasons"])
        self.assertIn("REPAIR_STRICT_REFUSED", [row["code"] for row in part_two["reasons"]])

        # therefore the split round does not reproduce the qualified outcome
        self.assertNotEqual(
            self._source_sha256(os.path.join(split, "fault.kicad_sch")),
            self._source_sha256(os.path.join(single, "fault.kicad_sch")))


class NativeP3QualificationTests(_NativeToolchainMixin, unittest.TestCase):
    """C4-P3: the constrained-writer route, as a positive control plus a real perturbation.

    Criteria sheet C4-P3 (draft-5) defines the item as both at once:

      positive control : tool_applied=null AND every independent condition holds -- a
                         complete all-ok op_results, a real byte delta, a successful fresh
                         reread, the connectivity gate -> APPLIED_TO_STAGE is permitted
      negative perturb : tool_applied=null, op_results non-empty and all ok, but the
                         source bytes do NOT change -> must not be APPLIED_TO_STAGE, with
                         REPAIR_EFFECT_MISMATCH

    The item's verdict is carried by the negative perturbation; the control is the control
    group.  The sheet also fixes the validity rule: if the control fails the item is
    NOT_RUN / qualification invalid, so a red perturbation on its own may never be scored
    as PASS.  That is enforced here by re-running the control on the same fixture inside
    the negative case, so a broken control fails the negative case too.
    """

    # DC-01/02/03 are the E1/E2/E3 cases, i.e. they reach the constrained writer.
    RULE_FOR_CASE = {"DC-01": "E1", "DC-02": "E2", "DC-03": "E3"}

    # Captured 2026-09-18 with the pinned akcli 0.21.0: C2.1 is already on +3V3, so the
    # constrained writer reports the operation ok and even a created UUID while the file
    # never changes -- the false success the effect check exists to catch.  Two
    # independent runs agreed field for field, including the created UUID
    # 1d801691-1263-56ad-b675-4a56a3e789b5.
    P3_NO_OP_LABEL = [{"op": "add_net_label", "name": "+3V3", "at": "C2.1"}]

    def _p3_ops(self, case):
        with open(os.path.join(self.FIXTURES, case, "repair_ops.json"), encoding="utf-8") as handle:
            return json.load(handle)["ops"]

    def _p3_stage(self, case, ops, name):
        """A scratch copy of a frozen fixture with its own op-list."""
        stage = os.path.join(self.root, name)
        os.makedirs(stage, exist_ok=True)
        shutil.copy2(os.path.join(self.FIXTURES, case, "fault.kicad_sch"),
                     os.path.join(stage, "fault.kicad_sch"))
        with open(os.path.join(stage, "oplist.json"), "w", encoding="utf-8",
                  newline="\n") as handle:
            json.dump({"protocol_version": 2, "target_format": "kicad", "ops": ops}, handle)
        return stage

    def _p3_apply(self, toolchain, case, ops, name):
        stage = self._p3_stage(case, ops, name)
        body = self._patch(toolchain, ops, self.RULE_FOR_CASE[case], stage,
                           route="CONSTRAINED_EXCEPTION")
        return adapter.apply_stage(self._stage_request(
            body, stage, os.path.join(self.root, "artifacts-" + name)))

    def test_p3_positive_control_a_null_applied_field_still_permits_success(self):
        cli = self._akcli()
        for case in ("DC-01", "DC-02", "DC-03"):
            ops = self._p3_ops(case)
            toolchain = self._measure(cli, case)
            result = self._p3_apply(toolchain, case, ops, "p3-positive-" + case)
            self.assertEqual(result["status"], "APPLIED_TO_STAGE",
                             "%s: %s" % (case, result["reasons"]))
            # the API route has no applied field at all, by contract ...
            self.assertIsNone(result["tool"]["tool_applied"])
            self.assertEqual(result["tool"]["mode"], "PYTHON_WRITER")
            # ... so success must come from the independent conditions
            self.assertEqual(result["tool"]["exit_code"], 0)
            self.assertTrue(result["changed"], case)
            self.assertEqual([row["status"] for row in result["tool"]["op_results"]],
                             ["ok"] * len(ops), case)
            self.assertEqual([row["op_index"] for row in result["tool"]["op_results"]],
                             list(range(len(ops))), case)

    def test_p3_negative_perturbation_a_no_op_write_is_not_applied(self):
        cli = self._akcli()
        for case in ("DC-01", "DC-02", "DC-03"):
            # Measured once and reused: the control and the perturbation must resolve
            # against one and the same frozen toolchain binding.
            toolchain = self._measure(cli, case)
            # Validity first: the control has to hold on this very fixture.  Otherwise
            # the item is invalid rather than red, and this case must fail with it.
            control = self._p3_apply(toolchain, case, self._p3_ops(case),
                                     "p3-control-" + case)
            self.assertEqual(control["status"], "APPLIED_TO_STAGE",
                             "%s control: %s" % (case, control["reasons"]))

            result = self._p3_apply(toolchain, case, self.P3_NO_OP_LABEL,
                                    "p3-negative-" + case)
            self.assertNotEqual(result["status"], "APPLIED_TO_STAGE", case)
            self.assertIn("REPAIR_EFFECT_MISMATCH",
                          [row["code"] for row in result["reasons"]], case)
            # the red has to land past the writer, not on an early rejection: the
            # operation really ran, reported ok, and still changed nothing
            self.assertEqual(result["tool"]["exit_code"], 0, case)
            self.assertIsNone(result["tool"]["tool_applied"], case)
            self.assertFalse(result["changed"], case)
            self.assertTrue(result["tool"]["op_results"], case)
            self.assertEqual([row["status"] for row in result["tool"]["op_results"]],
                             ["ok"], case)


if __name__ == "__main__":
    unittest.main()
