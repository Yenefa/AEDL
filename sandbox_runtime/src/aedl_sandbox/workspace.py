"""Content-addressed candidate workspace confinement (Agent H, Wave 1).

All writes are confined to run/<run_id>/candidate/<candidate_id>/ under the
caller-supplied workspace root. The frozen baseline (contracts, frozen
evidence, repository sources) is never written through this API.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePath
from typing import Any, Mapping

LEDGER_NAME = ".actions.jsonl"

# Internal bookkeeping files excluded from the candidate content hash. These
# are runtime records (append-only audit state), not design content: hashing
# them would change the candidate identity on every ledger append. Everything
# else inside the candidate root — hidden files and hidden directories
# included — participates in the hash, so mutating any engineering file,
# hidden or not, invalidates evidence receipts bound to the previous hash.
HASH_EXCLUDED_INTERNAL_FILES = frozenset({LEDGER_NAME})

_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class WorkspaceEscapeError(ValueError):
    """A requested identifier or path would leave the candidate workspace."""


class CandidateWorkspace:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    @staticmethod
    def _validate_segment(name: str, what: str) -> str:
        if not isinstance(name, str) or not name:
            raise WorkspaceEscapeError(f"{what} must be a non-empty string")
        if name.lower() in _WINDOWS_RESERVED:
            raise WorkspaceEscapeError(f"{what} {name!r} is a reserved device name")
        pure = PurePath(name)
        if pure.is_absolute() or Path(name).is_absolute():
            raise WorkspaceEscapeError(f"{what} {name!r} must not be absolute")
        if pure.drive:
            raise WorkspaceEscapeError(f"{what} {name!r} must not contain a drive specifier")
        parts = pure.parts
        if (
            len(parts) != 1
            or parts[0] in {".", ".."}
            or "/" in name
            or "\\" in name
        ):
            raise WorkspaceEscapeError(
                f"{what} {name!r} must be a single safe path segment"
            )
        return name

    def run_root(self, run_id: str) -> Path:
        return self._root / "run" / self._validate_segment(run_id, "run_id")

    def candidate_root(self, run_id: str, candidate_id: str) -> Path:
        return self.run_root(run_id) / "candidate" / self._validate_segment(
            candidate_id, "candidate_id"
        )

    def create_candidate(self, run_id: str, candidate_id: str) -> Path:
        root = self.candidate_root(run_id, candidate_id)
        root.mkdir(parents=True, exist_ok=True)
        self._ensure_confined(root)
        return root

    def _ensure_confined(self, path: Path) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise WorkspaceEscapeError(
                f"path {path} escapes the workspace root"
            ) from exc
        return resolved

    def resolve_candidate_path(
        self, run_id: str, candidate_id: str, relative: str | Path
    ) -> Path:
        text = str(relative)
        rel = PurePath(text)
        if rel.is_absolute() or Path(text).is_absolute():
            raise WorkspaceEscapeError(f"candidate path {relative!r} must be relative")
        if rel.drive:
            raise WorkspaceEscapeError(f"candidate path {relative!r} must not contain a drive specifier")
        if len(rel.parts) == 0 or any(part in {"..", "."} for part in rel.parts):
            raise WorkspaceEscapeError(
                f"candidate path {relative!r} must stay inside the candidate root"
            )
        candidate = self.candidate_root(run_id, candidate_id)
        target = candidate.joinpath(*rel.parts)
        self._ensure_confined(target)
        return target

    def write_candidate_bytes(
        self, run_id: str, candidate_id: str, relative: str | Path, data: bytes
    ) -> Path:
        target = self.resolve_candidate_path(run_id, candidate_id, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_confined(target)
        target.write_bytes(data)
        self._ensure_confined(target)
        return target

    def ledger_path(self, run_id: str, candidate_id: str) -> Path:
        return self.candidate_root(run_id, candidate_id) / LEDGER_NAME

    def record_action(
        self, run_id: str, candidate_id: str, action_id: str, result: Mapping[str, Any]
    ) -> None:
        entry = json.dumps(
            {"action_id": action_id, "result": dict(result)},
            sort_keys=True,
            ensure_ascii=False,
        )
        path = self.ledger_path(run_id, candidate_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry + "\n")

    def get_recorded_action(
        self, run_id: str, candidate_id: str, action_id: str
    ) -> dict[str, Any] | None:
        path = self.ledger_path(run_id, candidate_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("action_id") == action_id:
                    result = entry.get("result")
                    return dict(result) if isinstance(result, dict) else None
        return None

    def candidate_hash(self, run_id: str, candidate_id: str) -> str:
        """Deterministic content hash over candidate content.

        All files under the candidate root participate — hidden files and
        hidden directories included — except the declared internal
        bookkeeping set (HASH_EXCLUDED_INTERNAL_FILES, currently the action
        ledger). Mutating any engineering file, hidden or not, changes the
        hash and invalidates evidence receipts bound to the previous hash.
        """
        root = self.candidate_root(run_id, candidate_id)
        digest = hashlib.sha256()
        if not root.exists():
            digest.update(b"<missing>")
            return digest.hexdigest()
        files = sorted(
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.relative_to(root).as_posix() not in HASH_EXCLUDED_INTERNAL_FILES
        )
        if not files:
            digest.update(b"<empty>")
        for path in files:
            relative = path.relative_to(root).as_posix()
            content = hashlib.sha256(path.read_bytes()).hexdigest()
            digest.update(relative.encode("utf-8") + b"\0" + content.encode("ascii") + b"\0")
        return digest.hexdigest()

    @staticmethod
    def derive_candidate_id(
        run_id: str, domain_id: str, bundle_hash: str, subject: Mapping[str, Any]
    ) -> str:
        canonical = json.dumps(
            {
                "run_id": run_id,
                "domain_id": domain_id,
                "bundle_hash": bundle_hash,
                "subject": dict(subject),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return "cand-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
