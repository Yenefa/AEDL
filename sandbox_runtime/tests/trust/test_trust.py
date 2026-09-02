"""Trust sandbox tests (Agent L, EDD-001 sandbox runtime V1).

RED/GREEN sequence per task packet: canonicalization + bundle validation,
then evidence receipts, then promotion truth table, then the real EDD-001
manifest. Evidence and manifests are never filled in to manufacture a PASS.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aedl_sandbox.protocol import (
    ApprovalStatus,
    EvidenceEvent,
    EvidenceStatus,
    Outcome,
    PromotionRequest,
    VerificationStatus,
)
from aedl_sandbox.trust import FileTrustStore

REPO_ROOT = Path(__file__).resolve().parents[3]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_file(root: Path, rel: str, payload: bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def manifest_for(files, mirror_sets=None, missing=None, compiler=(), verifier=(), **overrides):
    manifest = {
        "schema_version": 1,
        "domain_id": "TEST-DOMAIN",
        "board_id": "test-board",
        "scope_status": "DRAFT",
        "evidence_status": "PARTIAL",
        "execution_status": "NOT_READY",
        "verification_status": "NOT_RUN",
        "approval_status": "NOT_REQUIRED",
        "files": files,
        "mirror_sets": mirror_sets or [],
        "missing_requirements": missing or [],
        "tool_coverage": {"compilers": list(compiler), "verifiers": list(verifier)},
        "notes": [],
    }
    manifest.update(overrides)
    return manifest


def file_entry(root: Path, rel: str, role="contract", source_class="VERIFIED_SOURCE", required=True,
               repo_path=None):
    data = (root / rel).read_bytes()
    return {
        "role": role,
        "repo_path": repo_path or rel,
        "size_bytes": len(data),
        "sha256": sha(data),
        "source_class": source_class,
        "required": required,
    }


def make_store(tmp: Path) -> tuple[FileTrustStore, Path, Path]:
    repo = tmp / "repo"
    receipts = tmp / "receipts"
    repo.mkdir()
    receipts.mkdir()
    return FileTrustStore(repo, receipts), repo, receipts


class CanonicalizationTests(unittest.TestCase):
    def test_key_order_does_not_change_event_hash(self):
        store, _, _ = make_store(Path(tempfile.mkdtemp()))
        a = EvidenceEvent("r1", "c1", "verification", {"candidate_sha256": "a" * 64}, {"x": 1, "y": "z"})
        b = EvidenceEvent("r1", "c1", "verification", {"candidate_sha256": "a" * 64}, {"y": "z", "x": 1})
        ra, rb = store.record(a), store.record(b)
        self.assertEqual(ra.event_hash, rb.event_hash)
        self.assertTrue(ra.valid and rb.valid)

    def test_one_byte_semantic_change_yields_different_hash(self):
        store, _, _ = make_store(Path(tempfile.mkdtemp()))
        a = store.record(EvidenceEvent("r1", "c1", "verification", {"candidate_sha256": "a" * 64}, {"x": 1}))
        b = store.record(EvidenceEvent("r1", "c1", "verification", {"candidate_sha256": "a" * 64}, {"x": 2}))
        self.assertNotEqual(a.event_hash, b.event_hash)

    def test_nan_and_non_json_values_are_rejected(self):
        store, _, _ = make_store(Path(tempfile.mkdtemp()))
        with self.assertRaises(ValueError):
            store.record(EvidenceEvent("r1", "c1", "verification", {"candidate_sha256": "a" * 64}, {"x": float("nan")}))
        with self.assertRaises(ValueError):
            store.record(EvidenceEvent("r1", "c1", "verification", {"candidate_sha256": "a" * 64}, {"x": {1, 2}}))


class BundleValidationTests(unittest.TestCase):
    def build_valid_bundle(self, root: Path):
        write_file(root, "gates/contracts/a.json", b"{}\n")
        write_file(root, "src/hardware/x/evidence/contracts/a.json", b"{}\n")
        files = [
            file_entry(root, "gates/contracts/a.json", role="gate_contract"),
            file_entry(root, "src/hardware/x/evidence/contracts/a.json", role="evidence_contract"),
        ]
        mirrors = [{
            "authoritative_path": "gates/contracts/a.json",
            "mirror_path": "src/hardware/x/evidence/contracts/a.json",
            "expected_equal": True,
        }]
        return manifest_for(files, mirrors, compiler=["kicad-9"], verifier=["aedl-verifier-1"])

    def test_complete_bundle_passes(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        status, findings = store.validate_bundle(path)
        self.assertEqual(status, EvidenceStatus.COMPLETE, [f.message for f in findings])
        self.assertEqual(findings, ())

    def test_hash_or_size_mismatch_is_invalid(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        m["files"][0]["sha256"] = "0" * 64
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        status, findings = store.validate_bundle(path)
        self.assertEqual(status, EvidenceStatus.INVALID)

    def test_mirror_mismatch_is_invalid(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        write_file(repo, "src/hardware/x/evidence/contracts/a.json", b"{}\nchanged")
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        status, _ = store.validate_bundle(path)
        self.assertEqual(status, EvidenceStatus.INVALID)

    def test_required_file_missing_is_invalid(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        (repo / "gates/contracts/a.json").unlink()
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        status, _ = store.validate_bundle(path)
        self.assertEqual(status, EvidenceStatus.INVALID)

    def test_declared_missing_requirements_partial(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        m["tool_coverage"] = {"compilers": [], "verifiers": []}
        m["missing_requirements"] = [
            {"id": "DATASHEET_X", "kind": "datasheet", "reason_code": "EVIDENCE_MISSING",
             "description": "datasheet not frozen yet"},
        ]
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        status, _ = store.validate_bundle(path)
        self.assertEqual(status, EvidenceStatus.PARTIAL)

    def test_path_escape_and_absolute_paths_fail_closed(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        for bad in ("../outside.json", "C:/abs/path.json", "/abs/path.json"):
            m = self.build_valid_bundle(repo)
            m["files"][0]["repo_path"] = bad
            path = write_file(repo, "manifest.json", json.dumps(m).encode())
            status, _ = store.validate_bundle(path)
            self.assertEqual(status, EvidenceStatus.INVALID, bad)

    def test_symlink_escape_fails_closed(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        outside = write_file(Path(tempfile.mkdtemp()), "out.json", b"{}\n")
        link = repo / "link.json"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlink creation not permitted on this host")
        m = self.build_valid_bundle(repo)
        m["files"][0]["repo_path"] = "link.json"
        m["files"][0]["size_bytes"] = outside.stat().st_size
        m["files"][0]["sha256"] = sha(outside.read_bytes())
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        status, _ = store.validate_bundle(path)
        self.assertEqual(status, EvidenceStatus.INVALID)

    def test_duplicate_paths_fail_closed(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        m["files"].append(dict(m["files"][0]))
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        status, _ = store.validate_bundle(path)
        self.assertEqual(status, EvidenceStatus.INVALID)

    def test_malformed_hash_and_unknown_fields_fail_closed(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        m["files"][0]["sha256"] = "NOTAHASH"
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        self.assertEqual(store.validate_bundle(path)[0], EvidenceStatus.INVALID)
        m2 = self.build_valid_bundle(repo)
        m2["surprise_field"] = True
        path = write_file(repo, "manifest.json", json.dumps(m2).encode())
        self.assertEqual(store.validate_bundle(path)[0], EvidenceStatus.INVALID)

    def test_model_prior_cannot_satisfy_required_engineering_source(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        m["files"][0]["source_class"] = "MODEL_PRIOR"
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        status, findings = store.validate_bundle(path)
        self.assertEqual(status, EvidenceStatus.PARTIAL)
        self.assertTrue(any("MODEL_PRIOR" in (f.code + f.message) for f in findings))

    def test_url_only_entry_is_not_verified_source(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        m["files"][0]["repo_path"] = "https://example.com/a.json"
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        status, _ = store.validate_bundle(path)
        self.assertEqual(status, EvidenceStatus.INVALID)

    def test_findings_are_stable_and_sorted(self):
        store, repo, _ = make_store(Path(tempfile.mkdtemp()))
        m = self.build_valid_bundle(repo)
        m["files"][0]["sha256"] = "0" * 64
        m["files"][1]["size_bytes"] = 999
        path = write_file(repo, "manifest.json", json.dumps(m).encode())
        _, f1 = store.validate_bundle(path)
        _, f2 = store.validate_bundle(path)
        self.assertEqual(f1, f2)
        self.assertEqual([(f.code, f.source, f.message) for f in f1],
                         sorted((f.code, f.source, f.message) for f in f1))


class RealEdd001ManifestTests(unittest.TestCase):
    REAL = REPO_ROOT / "src" / "hardware" / "edd001-board" / "evidence" / "sandbox_bundle_manifest_v1.json"

    def test_real_manifest_validates_as_partial(self):
        self.assertTrue(self.REAL.is_file(), "real EDD-001 manifest must exist")
        store = FileTrustStore(REPO_ROOT, REPO_ROOT / "sandbox_runtime" / "out" / "receipts")
        status, findings = store.validate_bundle(self.REAL)
        self.assertEqual(status, EvidenceStatus.PARTIAL,
                         [(f.code, f.message) for f in findings])
        data = json.loads(self.REAL.read_text(encoding="utf-8"))
        self.assertEqual(data["domain_id"], "EDD-001")
        self.assertEqual(data["board_id"], "project-027-edd001")
        self.assertEqual(data["scope_status"], "FROZEN")
        self.assertEqual(data["execution_status"], "NOT_READY")
        self.assertEqual(data["verification_status"], "NOT_RUN")
        self.assertEqual(data["approval_status"], "PENDING")
        self.assertEqual(len(data["files"]), 6)
        self.assertEqual(len(data["mirror_sets"]), 3)
        self.assertEqual(data["tool_coverage"], {"compilers": [], "verifiers": []})
        missing_ids = {m["id"] for m in data["missing_requirements"]}
        self.assertEqual(
            missing_ids,
            {
                "EDD001_POWER_CONTRACT",
                "ESP32_S3_WROOM_1_N8R8_DATASHEET",
                "AP63203WU_7_DATASHEET",
                "TYPE_C_31_M_12_DRAWING",
                "USBLC6_2SC6_DATASHEET",
                "SS34_DATASHEET",
            },
        )
        for m in data["missing_requirements"]:
            blob = json.dumps(m)
            self.assertNotIn("http://", blob)
            self.assertNotIn("https://", blob)
            self.assertNotIn("http://", blob)


if __name__ == "__main__":
    unittest.main()
