"""Fixtures shared by the tool-port tests.

Everything here builds its own temporary run root: a test that reached into the
repository's own .runs area could pass because of state left by another test,
which is the failure mode these tests exist to avoid.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The sandbox package is imported from source by the rest of this suite; make
# that explicit here rather than depending on how the runner was invoked.
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from aedl_sandbox import adapters  # noqa: E402
from aedl_sandbox.policy import SandboxPolicyEngine  # noqa: E402
from aedl_sandbox.protocol import PolicyRequest  # noqa: E402
from aedl_sandbox.toolports import design_envelope  # noqa: E402

HIR_OUTPUT_KIND = "hir"


def engine_for(document, root: Path) -> SandboxPolicyEngine:
    return SandboxPolicyEngine.from_document(document, Path(root))


def test_only_engine(root: Path) -> SandboxPolicyEngine:
    return engine_for(adapters.test_only_document(), root)


def design_envelope_for(
    root: Path,
    *,
    action: str = "DESIGN_SELECT_COMPONENT",
    subject: dict | None = None,
    output_kind: str = HIR_OUTPUT_KIND,
) -> dict:
    """An envelope of the shape cli.py run-arh builds from the operator's file."""
    inner = subject or {
        "mpn": adapters.TEST_ONLY_COMPONENT_MPN,
        "role": adapters.TEST_ONLY_COMPONENT_ROLE,
        "evidence_ids": [adapters.TEST_ONLY_EVIDENCE_ID],
    }
    return adapters.design_subject(action, inner, output_kind=output_kind)


def execute_request(root: Path, envelope: dict, *, candidate: str = "cand-1") -> PolicyRequest:
    candidate_root = Path(root) / candidate
    candidate_root.mkdir(parents=True, exist_ok=True)
    return PolicyRequest(
        run_id="run-1",
        domain_id="EDD-001",
        action_id="execute:%s" % candidate,
        action="execute_candidate",
        candidate_root=candidate_root,
        subject=envelope,
    )


def split(envelope: dict) -> tuple:
    request = PolicyRequest(
        run_id="run-1",
        domain_id="EDD-001",
        action_id="assemble",
        action="execute_candidate",
        candidate_root=Path("."),
        subject=envelope,
    )
    return design_envelope(request)


def artifact_path(candidate_root: Path) -> Path:
    return Path(candidate_root) / "hir.json"


def read_artifact(candidate_root: Path) -> dict:
    return json.loads(artifact_path(candidate_root).read_text(encoding="utf-8"))


def write_artifact(candidate_root: Path, payload: dict) -> None:
    """Rewrite the artifact in the CANONICAL form, so a tamper test cannot pass
    merely because the writer reordered keys."""
    artifact_path(candidate_root).write_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
