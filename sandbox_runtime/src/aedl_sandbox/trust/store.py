"""Trust sandbox (Agent L): deterministic bundle/receipt/promotion primitives."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from aedl_sandbox.protocol import (
    ApprovalStatus,
    HumanApprovalReceipt,
    EvidenceEvent,
    EvidenceReceipt,
    EvidenceStatus,
    Finding,
    Outcome,
    PromotionDecision,
    PromotionRequest,
    VerificationStatus,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

_MANIFEST_TOP_FIELDS = {
    "schema_version", "domain_id", "board_id", "scope_status", "evidence_status",
    "execution_status", "verification_status", "approval_status", "files",
    "mirror_sets", "missing_requirements", "tool_coverage", "notes",
}
_MANIFEST_OPTIONAL_FIELDS = {"metadata"}
_FILE_FIELDS = {"role", "repo_path", "size_bytes", "sha256", "source_class", "required"}
_MIRROR_FIELDS = {"authoritative_path", "mirror_path", "expected_equal"}
_MISSING_FIELDS = {"id", "kind", "reason_code", "description"}
_SCOPE_VALUES = {"DRAFT", "FROZEN"}
_EVIDENCE_VALUES = {"MISSING", "PARTIAL", "COMPLETE", "INVALID"}
_EXECUTION_VALUES = {"NOT_READY", "READY", "RUNNING", "COMPLETE", "FAILED", "BLOCKED"}
_VERIFICATION_VALUES = {"NOT_RUN", "PASS", "FAIL", "BLOCKED"}
_APPROVAL_VALUES = {"NOT_REQUIRED", "PENDING", "APPROVED", "REJECTED"}
_SOURCE_CLASSES = {"VERIFIED_SOURCE", "UNVERIFIED_SOURCE", "MODEL_PRIOR", "HUMAN_INPUT"}


def canonical_json(value: Any) -> bytes:
    """Canonical JSON: sorted keys, tight separators, UTF-8, NaN/inf rejected.

    Any non-JSON-serializable value (NaN, set, object, ...) raises ValueError,
    never TypeError: callers fail closed on one exception type.
    """
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value is not canonicalizable JSON: {exc}") from exc


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


_SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _safe_path_segment(name: Any) -> bool:
    """True only for a single, boring, path-safe segment (no separators/..)."""
    if not isinstance(name, str):
        return False
    if not _SAFE_SEGMENT_RE.fullmatch(name):
        return False
    return name not in {".", ".."} and ".." not in name


def _finding(code: str, message: str, source: str,
             details: Optional[dict] = None) -> Finding:
    return Finding(code=code, message=message, source=source, details=details or {})


class FileTrustStore:
    """Deterministic bundle validation, append-only evidence receipts, promotion gate."""

    def __init__(self, repo_root: Path, receipt_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.receipt_root = Path(receipt_root).resolve()

    # -- hashing ----------------------------------------------------------
    def sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # -- path containment -------------------------------------------------
    def _contained_path(self, repo_path: Any, source: str) -> tuple[Optional[Path], list]:
        errors: list = []
        if not isinstance(repo_path, str) or not repo_path.strip():
            return None, [_finding("EVIDENCE_PATH_INVALID", "repo_path must be a non-empty string", source)]
        if "://" in repo_path or repo_path.startswith("//"):
            return None, [_finding(
                "EVIDENCE_URL_ONLY",
                f"URL-only reference {repo_path!r} is not frozen local evidence and can never "
                "count as VERIFIED_SOURCE", source)]
        candidate = Path(repo_path)
        if candidate.is_absolute() or "\\" in repo_path or repo_path.startswith("/"):
            return None, [_finding(
                "EVIDENCE_PATH_INVALID",
                f"repo_path {repo_path!r} must be a repository-relative POSIX path", source)]
        parts = candidate.parts
        if ".." in parts or "." in parts or not parts:
            return None, [_finding(
                "EVIDENCE_PATH_ESCAPE", f"repo_path {repo_path!r} escapes the repository root", source)]
        resolved = (self.repo_root / candidate).resolve()
        try:
            resolved.relative_to(self.repo_root)
        except ValueError:
            return None, [_finding(
                "EVIDENCE_PATH_ESCAPE",
                f"repo_path {repo_path!r} resolves outside the repository root (symlink escape)", source)]
        return resolved, errors

    # -- bundle validation --------------------------------------------------
    def validate_bundle(self, manifest_path: Path) -> tuple[EvidenceStatus, tuple[Finding, ...]]:
        manifest_path = Path(manifest_path)
        if not manifest_path.is_file():
            return EvidenceStatus.MISSING, (
                _finding("EVIDENCE_MANIFEST_MISSING", f"bundle manifest is missing: {manifest_path}", "manifest"),
            )
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            return EvidenceStatus.INVALID, (
                _finding("EVIDENCE_MANIFEST_UNREADABLE",
                         f"bundle manifest unreadable: {type(exc).__name__}: {exc}", "manifest"),
            )
        findings: list = []
        if not isinstance(data, dict):
            return EvidenceStatus.INVALID, (_finding("EVIDENCE_MANIFEST_INVALID", "manifest root must be an object", "manifest"),)

        unknown = sorted(set(data) - _MANIFEST_TOP_FIELDS - _MANIFEST_OPTIONAL_FIELDS)
        if unknown:
            findings.append(_finding("EVIDENCE_FIELD_UNKNOWN", f"manifest has unknown fields: {unknown}", "manifest"))
        required_top = _MANIFEST_TOP_FIELDS - {"metadata"}
        missing = sorted(required_top - set(data))
        if missing:
            findings.append(_finding("EVIDENCE_FIELD_MISSING", f"manifest is missing fields: {missing}", "manifest"))
        if data.get("schema_version") != 1:
            findings.append(_finding("EVIDENCE_SCHEMA_VERSION", "schema_version must be exactly 1", "manifest"))
        for field, allowed in (
            ("scope_status", _SCOPE_VALUES), ("evidence_status", _EVIDENCE_VALUES),
            ("execution_status", _EXECUTION_VALUES), ("verification_status", _VERIFICATION_VALUES),
            ("approval_status", _APPROVAL_VALUES),
        ):
            if data.get(field) not in allowed:
                findings.append(_finding("EVIDENCE_ENUM_INVALID", f"{field} must be one of {sorted(allowed)}", "manifest"))
        for field in ("domain_id", "board_id"):
            if not isinstance(data.get(field), str) or not data.get(field):
                findings.append(_finding("EVIDENCE_FIELD_INVALID", f"{field} must be a non-empty string", "manifest"))
        if "metadata" in data and not isinstance(data.get("metadata"), dict):
            findings.append(_finding("EVIDENCE_FIELD_INVALID", "metadata must be an object", "manifest"))
        if not isinstance(data.get("notes"), list) or any(not isinstance(n, str) for n in data.get("notes", [])):
            findings.append(_finding("EVIDENCE_FIELD_INVALID", "notes must be an array of strings", "manifest"))

        coverage = data.get("tool_coverage")
        if not isinstance(coverage, dict) or set(coverage) != {"compilers", "verifiers"} \
                or any(not isinstance(v, list) or any(not isinstance(i, str) for i in v)
                       for v in coverage.values()):
            findings.append(_finding(
                "EVIDENCE_COVERAGE_INVALID",
                "tool_coverage must be an object with exactly compilers/verifiers string arrays", "manifest"))

        # files
        files = data.get("files")
        file_ok: dict[str, dict] = {}
        seen_paths: set[str] = set()
        if not isinstance(files, list) or not files:
            findings.append(_finding("EVIDENCE_FILES_EMPTY", "files must be a non-empty array", "manifest"))
            files = []
        for index, entry in enumerate(files):
            source = f"files[{index}]"
            if not isinstance(entry, dict):
                findings.append(_finding("EVIDENCE_FILE_INVALID", f"{source} must be an object", source))
                continue
            if set(entry) != _FILE_FIELDS:
                findings.append(_finding(
                    "EVIDENCE_FILE_FIELDS",
                    f"{source} must contain exactly {sorted(_FILE_FIELDS)}", source))
                continue
            role = entry["role"]
            if not isinstance(role, str) or not role:
                findings.append(_finding("EVIDENCE_FILE_INVALID", f"{source} has an invalid role", source))
            repo_path = entry["repo_path"]
            if repo_path in seen_paths:
                findings.append(_finding("EVIDENCE_PATH_DUPLICATE", f"duplicate repo_path {repo_path!r}", source))
            seen_paths.add(repo_path)
            if not isinstance(entry["size_bytes"], int) or isinstance(entry["size_bytes"], bool) or entry["size_bytes"] < 0:
                findings.append(_finding("EVIDENCE_SIZE_INVALID", f"{source} size_bytes must be a non-negative integer", source))
            if not isinstance(entry["sha256"], str) or not _SHA256_RE.fullmatch(entry["sha256"]):
                findings.append(_finding("EVIDENCE_HASH_MALFORMED", f"{source} sha256 must be 64 lowercase hex chars", source))
            source_class = entry["source_class"]
            if source_class not in _SOURCE_CLASSES:
                findings.append(_finding("EVIDENCE_SOURCE_CLASS_UNKNOWN",
                                         f"{source} has unknown source_class {source_class!r}", source))
            if entry["required"] not in (True, False):
                findings.append(_finding("EVIDENCE_FILE_INVALID", f"{source} required must be a boolean", source))
            resolved, path_errors = self._contained_path(repo_path, source)
            findings.extend(path_errors)
            if resolved is None:
                continue
            if not resolved.is_file():
                message = (f"required file {repo_path!r} is missing on disk"
                           if entry["required"] else f"optional file {repo_path!r} is missing on disk")
                code = "EVIDENCE_REQUIRED_FILE_MISSING" if entry["required"] else "EVIDENCE_FILE_MISSING"
                findings.append(_finding(code, message, source))
                if entry["required"]:
                    findings[-1] = _finding(code, message, source)
                continue
            if not isinstance(entry["size_bytes"], int) or isinstance(entry["size_bytes"], bool):
                continue
            actual_size = resolved.stat().st_size
            actual_hash = self.sha256_file(resolved)
            if actual_size != entry["size_bytes"]:
                findings.append(_finding(
                    "EVIDENCE_SIZE_MISMATCH",
                    f"{repo_path!r} size mismatch (declared {entry['size_bytes']}, actual {actual_size})", source))
            if entry["sha256"] and _SHA256_RE.fullmatch(entry.get("sha256", "")) and actual_hash != entry["sha256"]:
                findings.append(_finding(
                    "EVIDENCE_HASH_MISMATCH",
                    f"{repo_path!r} sha256 mismatch (declared {entry['sha256'][:12]}…, actual {actual_hash[:12]}…)",
                    source))
            if actual_size == entry["size_bytes"] and actual_hash == entry.get("sha256"):
                file_ok[repo_path] = entry
                if entry["required"] and source_class in ("MODEL_PRIOR", "HUMAN_INPUT"):
                    findings.append(_finding(
                        "EVIDENCE_SOURCE_CLASS_INSUFFICIENT",
                        f"required engineering source {repo_path!r} is declared {source_class}; "
                        "MODEL_PRIOR and HUMAN_INPUT cannot satisfy a required engineering-source record",
                        source))

        # mirror sets
        mirrors = data.get("mirror_sets")
        if not isinstance(mirrors, list):
            mirrors = []
            if "mirror_sets" in data:
                findings.append(_finding("EVIDENCE_MIRRORS_INVALID", "mirror_sets must be an array", "manifest"))
        for index, mirror in enumerate(mirrors):
            source = f"mirror_sets[{index}]"
            if not isinstance(mirror, dict) or set(mirror) != _MIRROR_FIELDS or mirror.get("expected_equal") is not True:
                findings.append(_finding(
                    "EVIDENCE_MIRROR_INVALID",
                    f"{source} must contain exactly authoritative_path/mirror_path with expected_equal=true", source))
                continue
            auth, err1 = self._contained_path(mirror["authoritative_path"], source)
            mir, err2 = self._contained_path(mirror["mirror_path"], source)
            findings.extend(err1 + err2)
            if auth is None or mir is None:
                continue
            if not auth.is_file() or not mir.is_file():
                findings.append(_finding(
                    "EVIDENCE_MIRROR_MISSING",
                    f"mirror pair missing on disk: {mirror['authoritative_path']!r} / {mirror['mirror_path']!r}", source))
                continue
            if self.sha256_file(auth) != self.sha256_file(mir):
                findings.append(_finding(
                    "EVIDENCE_MIRROR_MISMATCH",
                    f"mirror contents differ: {mirror['authoritative_path']!r} vs {mirror['mirror_path']!r}", source))

        # missing requirements
        for index, missing_req in enumerate(data.get("missing_requirements", []) or []):
            source = f"missing_requirements[{index}]"
            if not isinstance(missing_req, dict) or set(missing_req) != _MISSING_FIELDS:
                findings.append(_finding(
                    "EVIDENCE_MISSING_REQ_INVALID",
                    f"{source} must contain exactly id/kind/reason_code/description", source))
                continue
            for field in _MISSING_FIELDS:
                if not isinstance(missing_req.get(field), str) or not missing_req[field].strip():
                    findings.append(_finding(
                        "EVIDENCE_MISSING_REQ_INVALID", f"{source}.{field} must be a non-empty string", source))

        invalid = any(f.code in {
            "EVIDENCE_MANIFEST_UNREADABLE", "EVIDENCE_FIELD_UNKNOWN", "EVIDENCE_FIELD_MISSING",
            "EVIDENCE_SCHEMA_VERSION", "EVIDENCE_ENUM_INVALID", "EVIDENCE_FIELD_INVALID",
            "EVIDENCE_COVERAGE_INVALID", "EVIDENCE_FILES_EMPTY", "EVIDENCE_FILE_INVALID",
            "EVIDENCE_FILE_FIELDS", "EVIDENCE_PATH_INVALID", "EVIDENCE_PATH_ESCAPE",
            "EVIDENCE_PATH_DUPLICATE", "EVIDENCE_SIZE_INVALID", "EVIDENCE_HASH_MALFORMED",
            "EVIDENCE_SOURCE_CLASS_UNKNOWN", "EVIDENCE_REQUIRED_FILE_MISSING",
            "EVIDENCE_SIZE_MISMATCH", "EVIDENCE_HASH_MISMATCH", "EVIDENCE_URL_ONLY",
            "EVIDENCE_MIRROR_INVALID", "EVIDENCE_MIRROR_MISSING", "EVIDENCE_MIRROR_MISMATCH",
            "EVIDENCE_MISSING_REQ_INVALID",
        } for f in findings)

        missing_reqs = data.get("missing_requirements") or []
        coverage_ok = bool(isinstance(coverage, dict) and coverage.get("compilers") and coverage.get("verifiers"))
        required_entries = [e for e in files if isinstance(e, dict) and e.get("required") is True]
        all_required_verified = bool(required_entries) and all(
            e.get("source_class") == "VERIFIED_SOURCE" and e.get("repo_path") in file_ok
            for e in required_entries
        )
        if invalid:
            return EvidenceStatus.INVALID, tuple(sorted(findings, key=lambda f: (f.code, f.source, f.message)))
        if missing_reqs:
            return EvidenceStatus.PARTIAL, tuple(sorted(findings, key=lambda f: (f.code, f.source, f.message)))
        if coverage_ok and all_required_verified:
            return EvidenceStatus.COMPLETE, tuple(sorted(findings, key=lambda f: (f.code, f.source, f.message)))
        return EvidenceStatus.PARTIAL, tuple(sorted(findings, key=lambda f: (f.code, f.source, f.message)))

    # -- evidence receipts ---------------------------------------------------
    def _receipt_path(self, run_id: str, event_hash: str) -> Path:
        return self.receipt_root / run_id / f"{event_hash}.json"

    def record(self, event: EvidenceEvent) -> EvidenceReceipt:
        # Fail closed on run_id: it becomes a path segment, so anything beyond
        # a single boring segment (separators, "..", leading dots, drives) is
        # rejected before it can ever reach the filesystem.
        if not _safe_path_segment(event.run_id):
            raise ValueError(
                f"run_id {event.run_id!r} is not a single safe path segment")
        if event.event_type in ("verification", "promotion"):
            candidate_hash = event.input_hashes.get("candidate_sha256")
            if not isinstance(candidate_hash, str) or not _SHA256_RE.fullmatch(candidate_hash):
                raise ValueError(
                    f"{event.event_type} events must carry a well-formed candidate_sha256 in input_hashes")
        event_payload = {
            "run_id": event.run_id,
            "candidate_id": event.candidate_id,
            "event_type": event.event_type,
            "input_hashes": dict(event.input_hashes),
            "payload": dict(event.payload),
        }
        blob = canonical_json(event_payload)
        event_hash = hashlib.sha256(blob).hexdigest()
        target = self._receipt_path(event.run_id, event_hash)
        # Containment re-check on the resolved path (defense in depth).
        try:
            target.resolve().relative_to(self.receipt_root)
        except ValueError:
            raise ValueError("receipt path escapes receipt_root") from None
        if target.exists():
            return EvidenceReceipt(event_hash=event_hash, run_id=event.run_id,
                                   candidate_id=event.candidate_id,
                                   valid=target.read_bytes() == blob)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic + never-overwrite: exclusive create (O_CREAT|O_EXCL). A racing
        # writer or a pre-existing collision file can never be overwritten.
        try:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return EvidenceReceipt(event_hash=event_hash, run_id=event.run_id,
                                   candidate_id=event.candidate_id,
                                   valid=target.read_bytes() == blob)
        try:
            os.write(fd, blob)
        finally:
            os.close(fd)
        return EvidenceReceipt(event_hash=event_hash, run_id=event.run_id,
                               candidate_id=event.candidate_id, valid=True)

    def _latest_verification_hash(self, run_id: str, candidate_id: str) -> Optional[str]:
        """Latest candidate hash from FULLY re-verified PASS verification receipts.

        A receipt file is only trusted when every layer checks out: the bytes
        are exactly the canonical form of the event they contain, the sha256
        of those bytes equals the filename stem, run_id/candidate_id match the
        request, the event is a verification event with a PASS payload, and
        the recorded candidate_sha256 is well-formed. Anything else - forged
        files, drifted bytes, FAIL/other-status payloads - is ignored.
        """
        if not _safe_path_segment(run_id):
            return None
        directory = self.receipt_root / run_id
        if not directory.is_dir():
            return None
        best: Optional[tuple[int, str]] = None
        best_value: Optional[str] = None
        for path in directory.glob("*.json"):
            try:
                raw = path.read_bytes()
                event = json.loads(raw)
            except (OSError, ValueError):
                continue
            if not isinstance(event, dict):
                continue
            try:
                canonical = canonical_json(event)
            except ValueError:
                continue
            if hashlib.sha256(canonical).hexdigest() != path.stem:
                continue  # content does not match its content address
            if canonical != raw:
                continue  # bytes on disk are not the canonical serialization
            if event.get("run_id") != run_id:
                continue
            if event.get("event_type") != "verification":
                continue
            if event.get("candidate_id") != candidate_id:
                continue
            if event.get("payload", {}).get("status") != "PASS":
                continue
            candidate_hash = (event.get("input_hashes") or {}).get("candidate_sha256")
            if not isinstance(candidate_hash, str) or not _SHA256_RE.fullmatch(candidate_hash):
                continue
            sequence = event.get("payload", {}).get("sequence")
            order = sequence if isinstance(sequence, int) and not isinstance(sequence, bool) else 0
            key = (order, path.name)
            if best is None or key > best:
                best = key
                best_value = candidate_hash
        return best_value

    # -- promotion ------------------------------------------------------------
    def assess_promotion(self, request: PromotionRequest) -> PromotionDecision:
        def decision(outcome: Outcome, reason: str) -> PromotionDecision:
            return PromotionDecision(outcome=outcome, reason_code=reason, findings=())

        if request.verification_status == VerificationStatus.FAIL:
            return decision(Outcome.DENY, "VERIFY_FAILED")
        if request.verification_status in (VerificationStatus.BLOCKED, VerificationStatus.NOT_RUN):
            return decision(Outcome.BLOCKED, "VERIFY_NOT_COMPLETE")
        if request.evidence_status == EvidenceStatus.INVALID:
            return decision(Outcome.DENY, "EVIDENCE_INVALID")
        if request.evidence_status in (EvidenceStatus.MISSING, EvidenceStatus.PARTIAL):
            return decision(Outcome.BLOCKED, "EVIDENCE_INCOMPLETE")
        # V2: a candidate-bound HumanApprovalReceipt supersedes the bare
        # approval_status. The receipt must be internally well-formed and
        # bound to THIS run and THIS candidate hash; anything else fails
        # closed. Without a receipt, the bare V1 approval_status applies
        # (V1 callers keep working; orchestrator always sends the receipt).
        approval_status = request.approval_status
        receipt = getattr(request, "approval_receipt", None)
        if receipt is not None:
            problems: list[str] = []
            if not isinstance(receipt, HumanApprovalReceipt):
                problems.append("approval receipt is not a HumanApprovalReceipt")
            else:
                if receipt.run_id != request.run_id:
                    problems.append("approval receipt run_id does not match the request")
                if receipt.candidate_sha256 != request.candidate_hash:
                    problems.append("approval receipt is bound to a different candidate hash")
                if receipt.decision not in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
                    problems.append("approval receipt has an undecidable status")
                if not isinstance(receipt.approved_by, str) or not receipt.approved_by.strip():
                    problems.append("approval receipt has no named approver")
            if problems:
                return PromotionDecision(
                    outcome=Outcome.DENY,
                    reason_code="APPROVAL_RECEIPT_INVALID",
                    findings=tuple(
                        _finding("APPROVAL_RECEIPT_INVALID", message, "promotion")
                        for message in problems
                    ),
                )
            approval_status = receipt.decision
        if approval_status == ApprovalStatus.PENDING:
            return decision(Outcome.BLOCKED, "APPROVAL_REQUIRED")
        if approval_status == ApprovalStatus.REJECTED:
            return decision(Outcome.DENY, "APPROVAL_REJECTED")
        latest = self._latest_verification_hash(request.run_id, request.candidate_id)
        if latest is None or latest != request.candidate_hash:
            return decision(Outcome.DENY, "EVIDENCE_STALE")
        return decision(Outcome.ALLOW, "PROMOTION_ALLOWED")
