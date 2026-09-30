"""Bounded M2 SHT30-address episode; no EDD-001 or manufacturing claim.

The model proposes an existing DESIGN_ASSIGN_PIN action. The host translates
it into one C1 op; the existing C5 single-writer transaction owns application,
topology checks and commit to a private candidate. Acceptance is a separately
pinned datasheet contract checked against a fresh KiCad XML export.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .protocol import (ExecutionResult, Finding, Outcome, PolicyDecision,
                       VerificationResult, VerificationStatus)
from .toolports import design_envelope

DOMAIN = "M2-SHT30-ADDRESS"
INITIAL_SUBJECT = {"design_action": "DESIGN_ASSIGN_PIN", "design_subject": {
    "pin": "U2.2", "function": "FLOATING", "approval_status": "NOT_REQUIRED"},
    "output_kind": "kicad_sch"}
SDIST_SHA256 = "949ea4d51497ec5413ec19ad15454972d2c30b58f1447493b7b5d99031330df6"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    def encode(item):
        if is_dataclass(item):
            return asdict(item)
        raise TypeError("unsupported report value: %s" % type(item).__name__)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=encode), encoding="utf-8")


def measure_toolchain(repo_root, worker_python, kicad_cli, source):
    """Measure the installed distribution and embedded symbols in the worker.

    The sdist declaration is the published PyPI 0.21.0 digest, NOT the installed
    digest. Runtime binding uses the independently observed installed files.
    """
    from tools import host_toolchain
    worker_python, kicad_cli = Path(worker_python).resolve(), Path(kicad_cli).resolve()
    script = (
        "import sys,json,platform,importlib.metadata as m,hashlib;"
        "sys.path.insert(0,sys.argv[1]);from tools import akcli_adapter as a;"
        "d=m.distribution('akcli-kicad');"
        "rows=[{'path':str(p).replace(chr(92),'/'),'sha256':hashlib.sha256(d.locate_file(p).read_bytes()).hexdigest(),"
        "'size_bytes':d.locate_file(p).stat().st_size,'role':'READONLY_DEPENDENCY'} "
        "for p in d.files if str(p).startswith('akcli/') and d.locate_file(p).is_file()];"
        "print(json.dumps({'installed':a._distribution_manifest(),'symbols':a._symbol_digest(sys.argv[2]),"
        "'python':platform.python_version(),'files':rows}))"
    )
    proc = subprocess.run([str(worker_python), "-c", script, str(repo_root), str(source)],
                          capture_output=True, text=True, timeout=60, check=True)
    measured = json.loads(proc.stdout)
    version = subprocess.run([str(kicad_cli), "version"], capture_output=True,
                             text=True, timeout=60, check=True).stdout.strip()
    environment = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR")
                   if name in os.environ}
    empty = {"version": 1, "files": []}
    binding = {"version": 1, "manifest": {
        "version": 1, "akcli": {"version": "0.21.0", "sdist_sha256": SDIST_SHA256,
            "package_files_sha256": {"version": 1, "files": measured["files"]}},
        "python": {"version": measured["python"], "executable_sha256": sha(worker_python)},
        "kicad": {"version": version, "executable_sha256": sha(kicad_cli)},
        "libraries": copy.deepcopy(empty), "configs": copy.deepcopy(empty),
        "execution": {"worker_timeout_seconds": 60, "kicad_timeout_seconds": 60,
                      "argv_profile": "PR1_V1"}},
        "resolution": {"executables": {"akcli": str(worker_python.with_name(
            "akcli.exe" if os.name == "nt" else "akcli")), "python": str(worker_python),
            "kicad": str(kicad_cli)}, "files": {"libraries": {}, "configs": {}},
            "environment": {"kicad": environment, "akcli": environment},
            "launcher_argv": [], "installed_akcli": measured["installed"]}}
    return host_toolchain.validate_host_binding(binding), measured["symbols"]


class NativeEpisodePolicy:
    """Explicit operator scope, independent of model authority declarations."""
    def evaluate(self, request):
        if request.domain_id != DOMAIN or request.action not in ("preflight", "execute_candidate"):
            return PolicyDecision(Outcome.BLOCKED, "NATIVE_EPISODE_SCOPE")
        try:
            action, subject, kind = design_envelope(request)
        except ValueError:
            return PolicyDecision(Outcome.BLOCKED, "NATIVE_EPISODE_ENVELOPE")
        valid = (action == "DESIGN_ASSIGN_PIN" and subject.get("pin") == "U2.2"
                 and subject.get("function") in ("FLOATING", "GND")
                 and subject.get("approval_status") == "NOT_REQUIRED"
                 and set(subject) == {"pin", "function", "approval_status"}
                 and kind in ("", "kicad_sch", None))
        return PolicyDecision(Outcome.ALLOW if valid else Outcome.BLOCKED,
                              "NATIVE_EPISODE_ALLOWED" if valid else "NATIVE_EPISODE_SCOPE")


class NativeEpisodePorts:
    """Concrete executor and read-only verifier sharing only host configuration."""
    def __init__(self, repo_root, report_root, worker_python, kicad_cli):
        from gates import schematic_semantics
        self.repo = Path(repo_root).resolve()
        self.report = Path(report_root).resolve()
        self.source = self.repo / "tests/fixtures/repair_pr1/native/DC-02/fault.kicad_sch"
        self.contract_path = self.repo / "gates/contracts/m2_schematic_contract_v1.json"
        self.source_sha = sha(self.source)
        self.contract_sha = sha(self.contract_path)
        self.contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        schematic_semantics.validate_contract(self.contract)
        self.rule = next(r for r in self.contract["rules"] if r["id"] == "SHT30_ADDRESS")
        self.binding, self.symbol_digest = measure_toolchain(
            self.repo, worker_python, kicad_cli, self.source)
        self.policy = NativeEpisodePolicy()
        self.observations = []
        self.transactions = []
        self.identities = {}
        save(self.report / "toolchain.json", self.binding)

    def execute(self, request):
        from tools import repair_pipeline as pipeline
        decision = self.policy.evaluate(request)
        root = Path(request.candidate_root).resolve()
        if decision.outcome != Outcome.ALLOW:
            return ExecutionResult(False, request.action_id, root.name,
                findings=(Finding(decision.reason_code, "outside bounded native scope", "native"),))
        if sha(self.source) != self.source_sha or sha(self.contract_path) != self.contract_sha:
            return ExecutionResult(False, request.action_id, root.name,
                findings=(Finding("NATIVE_INPUT_DRIFT", "frozen source or contract changed", "native"),))
        design = root / "design"
        design.mkdir(parents=True, exist_ok=True)
        target = design / "fault.kicad_sch"
        shutil.copyfile(self.source, target)
        firmware = design / "src/firmware/include/sht30.h"
        firmware.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.repo / "src/firmware/include/sht30.h", firmware)
        self.identities[str(root)] = (request.run_id, root.name)
        _, subject, _ = design_envelope(request)
        if subject["function"] == "GND":
            txn = "txn-" + uuid.uuid4().hex
            scratch = self.report / "transactions" / txn
            stage = scratch / "stage"
            stage.mkdir(parents=True)
            oplist = {"protocol_version": 2, "target_format": "kicad", "ops": [
                {"op": "add_net_label", "name": subject["function"], "at": subject["pin"]}]}
            save(stage / "ops.json", oplist)
            policy = pipeline.load_topology_policy()
            policy_sha = pipeline.canonical_sha256("policy-bound", policy)
            context_sha = hashlib.sha256((request.run_id + root.name + self.contract_sha).encode()).hexdigest()
            context_id = "ctx-" + uuid.uuid4().hex
            host = {"run_id": request.run_id, "candidate_id": root.name,
                "round_id": txn, "patch_id": txn, "context_id": context_id,
                "target": "fault.kicad_sch", "base_source_sha256": sha(target),
                "initial_context_digest": context_sha, "limits": {"max_ops": 1},
                "workspace": {"candidate_root": str(root), "design_root": str(design),
                    "repair_root": str(scratch / "repair"), "lock_path": str(scratch / "repair.lock")},
                "toolchain_binding": self.binding, "candidate_symbol_digest": self.symbol_digest,
                "policy_path": str(pipeline.TOPOLOGY_POLICY_PATH),
                "authority": {"context_digest": context_sha,
                    "resolved_authorization_refs": ["GH110-Owner-Session"],
                    "decisions": [{"capability": c, "effect": "ALLOW"}
                                  for c in ("TOOL_EXECUTE", "FILE_WRITE")],
                    "approvals": [{"policy_file_sha256": policy_sha, "rule_id": "E2",
                        "run_id": request.run_id, "candidate_id": root.name, "paths": [str(design)]}]},
                "native": {"read_root": str(design), "artifact_root": str(scratch / "read")}}
            proposal = {"schema_version": 1, "context_id": context_id,
                "target": host["target"], "base_source_sha256": host["base_source_sha256"],
                "decision": "PATCH", "oplist": oplist, "diagnosis": [{
                    "rule_id": "E2", "observed": "U2.2 floating in frozen native fixture",
                    "fact_ids": ["SHT30_ADDRESS"], "requirement_level": "MANDATORY",
                    "rationale": "fixed 0x44 address requires ADDR=GND in the independent contract"}]}
            receipt = pipeline.run_round({"host_context": host,
                "proposal_raw": json.dumps(proposal).encode(), "txn_id": txn,
                "stage_root": str(stage), "stage_target": target.name,
                "oplist_path": str(stage / "ops.json"),
                "native_artifact_root": str(scratch / "artifacts")})
            save(scratch / "receipt.json", receipt)
            self.transactions.append(receipt)
            if receipt["status"] != "COMMITTED":
                rows = [asdict(r) if is_dataclass(r) else r for r in receipt["reasons"]]
                findings = tuple(Finding(r.get("code", r.get("rule_id", "NATIVE_TRANSACTION_REFUSED")),
                    r.get("detail", r.get("message", str(r))), "C5") for r in rows)
                return ExecutionResult(False, request.action_id, root.name, findings=findings)
        return ExecutionResult(True, request.action_id, root.name, artifacts=(target,), actor_id="akcli-c5")

    def verify(self, run_id, candidate_id, candidate_root):
        from gates import repair_verification, schematic_semantics
        from tools import host_toolchain
        root = Path(candidate_root).resolve()
        if self.identities.get(str(root)) != (run_id, candidate_id):
            return VerificationResult(VerificationStatus.BLOCKED, candidate_id,
                (Finding("NATIVE_IDENTITY_MISMATCH", "candidate is not bound to this run", "native"),))
        if sha(self.contract_path) != self.contract_sha:
            return VerificationResult(VerificationStatus.BLOCKED, candidate_id,
                (Finding("NATIVE_CONTRACT_DRIFT", "independent contract changed", "native"),))
        report = self.report / "verification" / (candidate_id + "-" + uuid.uuid4().hex)
        export = repair_verification.fresh_export({"role": "AFTER", "txn_id": "verify-" + uuid.uuid4().hex,
            "toolchain": host_toolchain.derive_kicad_slice(self.binding),
            "source_root": str(root / "design"), "relative_source": "fault.kicad_sch",
            "output_dir": str(report)})
        proof = {key: value for key, value in export.items() if key != "xml_bytes"}
        save(report / "export.json", proof)
        if export["status"] != "PASS":
            findings = tuple(Finding(r["code"], r["detail"], "KiCad") for r in export["reasons"])
            return VerificationResult(VerificationStatus.BLOCKED, candidate_id, findings)
        observed = schematic_semantics._parse_netlist(report / "after.net.xml")
        expected = self.rule["checks"]["netlist"]["pins"]["U2.2"]
        actual = observed["pins"].get("U2.2")
        passed = isinstance(actual, dict) and all(actual.get(k) == v for k, v in expected.items())
        result = {"run_id": run_id, "candidate_id": candidate_id,
            "source_sha256": sha(root / "design/fault.kicad_sch"),
            "netlist_sha256": sha(report / "after.net.xml"), "contract_sha256": self.contract_sha,
            "rule_id": self.rule["id"], "scope": "netlist.U2.2 only",
            "expected": expected, "observed": actual, "status": "PASS" if passed else "FAIL"}
        save(report / "semantic.json", result)
        self.observations.append(result)
        finding = Finding("SHT30_ADDRESS", "SHT30 ADDR U2.2 must be GND for the fixed 0x44 address; "
            + ("fresh KiCad netlist confirms GND" if passed else "fresh KiCad netlist shows a floating pin"),
            "independent-M2-contract", details=result)
        return VerificationResult(VerificationStatus.PASS if passed else VerificationStatus.FAIL,
                                  candidate_id, (finding,), actor_id="kicad-contract")
