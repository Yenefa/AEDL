"""Deterministic EDD-001 sandbox policy kernel (Agent M ownership).

Public symbols: ``SandboxPolicyEngine`` and
``load_contracts_bound_to_manifest`` (the V2 trust-manifest binding loader
used by the adapter layer to build an engine whose contracts are pinned to a
trust-validated bundle manifest). Everything else lives in submodules and is
not part of the public interface.
"""

from __future__ import annotations

from .errors import PolicyDocumentError
from .edd001 import load_contracts_bound_to_manifest
from .engine import SandboxPolicyEngine

__all__ = ["PolicyDocumentError", "SandboxPolicyEngine", "load_contracts_bound_to_manifest"]
