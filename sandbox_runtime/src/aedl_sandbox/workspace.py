"""Content-addressed candidate workspace confinement (Agent H, Wave 1).

All writes are confined to run/<run_id>/candidate/<candidate_id>/ under the
caller-supplied workspace root. The frozen baseline (contracts, frozen
evidence, repository sources) is never written through this API.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat as _stat
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


def is_link_like(path: Path) -> bool:
    """True for a symlink, a Windows junction, or any other reparse point.

    Portable, and portably is the whole difficulty here. `Path.is_symlink()` does
    NOT cover a Windows directory junction, and `Path.is_junction()` does not
    exist in Python 3.9 -- which is this repository's lane, and the version the F1
    reproduction ran on. So on Windows a reparse point is detected through
    `st_file_attributes`, and everywhere else the symlink check is the fallback.

    A junction is the case that actually reproduced: `mklink /J` needs no
    elevation, unlike a symlink, so it is the cheap way for anything holding write
    access inside a candidate to reach a sibling candidate.
    """
    candidate = Path(path)
    try:
        if candidate.is_symlink():
            return True
    except OSError:
        return True
    reparse = getattr(_stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    try:
        attributes = os.lstat(str(candidate)).st_file_attributes
    except (AttributeError, OSError, ValueError):
        return False
    return bool(attributes & reparse)


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
        """The WORKSPACE boundary. Kept, and kept as the outer one.

        `create_candidate` legitimately creates a new candidate under the
        workspace, so the workspace bound has to stay. The candidate bound is
        strictly tighter and is applied on top of it, which is why the existing
        "escapes the workspace entirely" tests keep passing unchanged.
        """
        return self._ensure_within(path, self._root, "workspace root")

    def _candidate_boundary(self, run_id: str, candidate_id: str) -> Path:
        """The resolved candidate root, itself confined to the workspace.

        Also refuses a candidate root that is ITSELF a link. A boundary you reach
        through a link is not a boundary: everything under it resolves somewhere
        else, so the comparison below would be against a directory the caller does
        not control.
        """
        root = self.candidate_root(run_id, candidate_id)
        resolved = self._ensure_within(root, self._root, "workspace root")
        if is_link_like(root):
            raise WorkspaceEscapeError(
                f"candidate root {root} is a link or junction, so it cannot be a "
                f"containment boundary"
            )
        return resolved

    def _ensure_within(self, path: Path, boundary: Path, what: str) -> Path:
        """Resolve, compare against the boundary, and refuse an ALIASED file.

        The link-count half is not redundant with the comparison, and that is
        measured rather than assumed. A HARD link is not followed by
        `Path.resolve()`: both names are legitimate paths to one inode, so
        resolving a hard link planted inside candidate A at a file in candidate B
        still yields a path INSIDE candidate A. The comparison passes and the
        write lands in B. Measured, before this check existed:

            planted.json resolve() -> .../candidate-a/planted.json   (inside A)
            st_nlink                 -> 2
            write_candidate_bytes    -> ALLOWED
            candidate-b/victim.json  -> b'WRITTEN-THROUGH'

        The same route reached the ledger, and the ledger is EXCLUDED from the
        content hash -- which makes it a convenient place to park things that are
        not design content, and therefore worth at least as much attention as the
        design files rather than less.

        So a file with more than one name is refused: contract 378's
        「文件 link count/别名与实际身份」, applied on the Sandbox side. A path that
        does not exist yet has no count to check, and cannot already be an alias.

        DIRECTORIES ARE EXEMPT, and that exemption is the whole difference between
        this working and not working. A directory's `st_nlink` is not a link count
        on POSIX: the kernel reports `2 + (number of subdirectories)`, because
        `.` and every subdirectory are names for it. So a directory that has never
        held a subdirectory still reports 2, and reading that as "this is a second
        name for bytes living elsewhere" refuses EVERY directory on Linux --
        including the candidate root `create_candidate` has just made, which is
        why the first candidate operation failed there. Measured on WSL2
        Ubuntu-24.04 at merge c6d52d9: 56 of 57 linux failures, all from this one
        comparison.

        The exemption costs nothing, because a hard link to a DIRECTORY cannot be
        made by an unprivileged process at all (`link(2)` returns EPERM), and a
        privileged one has no need to hide inside a candidate. Directory aliasing
        is caught where it actually happens instead: `resolved` has already been
        fully resolved by the `Path.resolve()` above, so a symlinked or junctioned
        directory is compared by its REAL target, and `_candidate_boundary` refuses
        a candidate root that is ITSELF a link before this point is ever reached.

        Windows is why this went unnoticed: NTFS does not report directory link
        counts, so `st_nlink` there is 1 for a directory and the identical code
        passes. A defect invisible on the platform it was written on is the reason
        the exemption is pinned by a test that fails on Windows too.
        """
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(boundary)
        except ValueError as exc:
            raise WorkspaceEscapeError(
                f"path {path} escapes the {what} {boundary}"
            ) from exc
        try:
            info = os.stat(str(resolved))
        except OSError:
            # does not exist yet, or is not stat-able: nothing to alias
            return resolved
        if _stat.S_ISDIR(info.st_mode):
            # A directory's st_nlink is a subdirectory count on POSIX, not an
            # alias count. Refusing on it rejects every directory, which is not a
            # security posture but an outage. See the docstring.
            return resolved
        links = info.st_nlink
        if links > 1:
            raise WorkspaceEscapeError(
                f"path {path} has {links} hard links, so it is a second name for "
                f"bytes that live somewhere else and cannot be confined to the "
                f"{what} {boundary}. A file inside a candidate must have exactly "
                f"one name."
            )
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
        # Bounded by the CANDIDATE, not the workspace. This is the F1 fix: a
        # destination inside the workspace but outside this candidate -- a sibling
        # candidate, or its ledger -- is not a confined destination, and
        # `relative_to(workspace_root)` said it was.
        boundary = self._candidate_boundary(run_id, candidate_id)
        target = self.candidate_root(run_id, candidate_id).joinpath(*rel.parts)
        self._ensure_within(target, boundary, "candidate root")
        return target

    def write_candidate_bytes(
        self, run_id: str, candidate_id: str, relative: str | Path, data: bytes
    ) -> Path:
        target = self.resolve_candidate_path(run_id, candidate_id, relative)
        boundary = self._candidate_boundary(run_id, candidate_id)
        # The parent mkdir can itself traverse a link, so the boundary is
        # re-checked after it. And note what the pair of checks does and does not
        # do: an escape is DETECTED after it happened, not prevented. Closing that
        # needs descriptor-relative no-follow opens, which Windows does not offer
        # the way POSIX does. Recorded rather than implied away.
        target.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_within(target, boundary, "candidate root")
        target.write_bytes(data)
        self._ensure_within(target, boundary, "candidate root")
        return target

    def ledger_path(self, run_id: str, candidate_id: str) -> Path:
        """The ledger path, confined to the candidate.

        The ledger is excluded from the content hash, which makes it a convenient
        place to put things that are not design content -- so it must be at least
        as tightly bounded as the design files, not less.
        """
        boundary = self._candidate_boundary(run_id, candidate_id)
        ledger = self.candidate_root(run_id, candidate_id) / LEDGER_NAME
        return self._ensure_within(ledger, boundary, "candidate root")

    def record_action(
        self, run_id: str, candidate_id: str, action_id: str, result: Mapping[str, Any]
    ) -> None:
        entry = json.dumps(
            {"action_id": action_id, "result": dict(result)},
            sort_keys=True,
            ensure_ascii=False,
        )
        path = self.ledger_path(run_id, candidate_id)
        boundary = self._candidate_boundary(run_id, candidate_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Confined before AND after the append: the ledger previously had NO
        # confinement call at all, so a junction at its path reached a sibling
        # candidate's ledger directly.
        self._ensure_within(path, boundary, "candidate root")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry + "\n")
        self._ensure_within(path, boundary, "candidate root")

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
        # A link inside the candidate is REFUSED, not skipped.
        #
        # `rglob` follows a Windows junction, so the walk descended into a sibling
        # candidate and mixed its files into this candidate's identity. Measured:
        # the hash of candidate-a moved when a file in candidate-b changed. That
        # breaks content addressing silently -- a receipt bound to A would be
        # invalidated by someone editing B, and A and B could be made to collide.
        #
        # Refusing rather than skipping, because a hash that quietly omits part of
        # what is on disk disagrees with the disk without saying so.
        files = sorted(self._walk_candidate_files(run_id, candidate_id, root))
        if not files:
            digest.update(b"<empty>")
        for path in files:
            relative = path.relative_to(root).as_posix()
            content = hashlib.sha256(path.read_bytes()).hexdigest()
            digest.update(relative.encode("utf-8") + b"\0" + content.encode("ascii") + b"\0")
        return digest.hexdigest()

    @staticmethod
    def _walk_candidate_files(run_id: str, candidate_id: str, root: Path) -> list:
        """Files under the candidate root, refusing any link on the way.

        `os.walk(followlinks=False)` is not sufficient on its own: on Windows a
        directory JUNCTION is a reparse point, not a symlink, and `followlinks`
        keys off symlinks. So every directory is additionally checked with
        `is_link_like`, and a hit raises rather than being pruned.
        """
        collected: list = []
        for current, directories, names in os.walk(str(root), followlinks=False):
            here = Path(current)
            for name in list(directories):
                child = here / name
                if is_link_like(child):
                    raise WorkspaceEscapeError(
                        f"candidate {candidate_id} contains a link or junction at "
                        f"{child}, so its content hash cannot be computed: the "
                        f"walk would follow it into another candidate and change "
                        f"this candidate's identity. Remove the link, or keep the "
                        f"content out of the candidate tree."
                    )
            for name in names:
                child = here / name
                if is_link_like(child):
                    raise WorkspaceEscapeError(
                        f"candidate {candidate_id} contains a linked file at "
                        f"{child}, so its content hash cannot be computed: a link "
                        f"is a second name for bytes that live somewhere else."
                    )
                relative = child.relative_to(root).as_posix()
                if relative in HASH_EXCLUDED_INTERNAL_FILES:
                    continue
                collected.append(child)
        return collected

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
