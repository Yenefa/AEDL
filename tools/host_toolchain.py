"""PR1-C5-PRE: one host-level toolchain identity for the C3 and C4 layers.

Contract section 9 fixes "KiCad 10.0.5 and the host-configured symbol
environment"; section 8 binds the akcli distribution and the worker interpreter
for the native writer.  Those are two slices of one host toolchain, and C5's
commit predicate has to prove that both receipts came from the same machine and
the same pinned toolchain.  It cannot prove that by comparing the two receipt
hashes: the slices have different shapes, so their digests are never equal.  The
property is "same common ancestor":

    c3_toolchain_sha256 == sha256(derive_kicad_slice(binding))
    AND
    c4_toolchain_sha256 == sha256(derive_akcli_slice(binding, symbol_digest))

HostToolchainBinding has two layers:

  manifest    the portable, frozen declaration.  Byte-shape aligned with
              src/repair/patch_schema_v1.json#/$defs/ToolchainManifest, which
              this module never modifies.
  resolution  host-only execution binding: absolute executable paths, the
              logical-path -> absolute-host-path map for libraries/configs, the
              per-tool execution environments, the launcher argv, and the
              observed installed akcli distribution identity.

The split is the contract, not a convenience: a portable declaration cannot name
a machine's absolute paths, and a machine observation is not portable.  A digest
from one domain MUST NOT be substituted for a digest from another domain unless
this contract defines an explicit canonical derivation.  In particular
manifest.akcli.sdist_sha256 and manifest.akcli.package_files_sha256 are
declarations, while the digest C4 verifies is an observation of the installed
distribution; this contract defines no derivation between them, so the observed
value is carried in resolution and never cast from a declaration.

candidate_symbol_digest is NOT part of HostToolchainBinding.  It is computed from
the current candidate's embedded symbol library, so it is a candidate-specific
binding input rather than a host property.

This module is pure data: it runs no tool, reads no file, publishes nothing.
"""

import copy
import os
import re

from gates.repair_verification import (canonical_sha256, EXPORT_ARGUMENTS,
                                       REQUIRED_KICAD_VERSION)
from gates.repair_verification import toolchain_manifest as _kicad_validator
from tools.akcli_adapter import AKCLI_UPSTREAM_COMMIT, AKCLI_VERSION
from tools.akcli_adapter import toolchain_manifest as _akcli_validator


class HostBindingError(ValueError):
    """The host toolchain binding is not a valid, derivable identity."""


VERSION = 1
ARGV_PROFILE = "PR1_V1"
MAX_TIMEOUT_SECONDS = 60
AKCLI_PACKAGE = "akcli-kicad"
_READONLY_ROLE = "READONLY_DEPENDENCY"

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_TOP_FIELDS = {"version", "manifest", "resolution"}
_MANIFEST_FIELDS = {"version", "akcli", "python", "kicad", "libraries", "configs",
                    "execution"}
_AKCLI_FIELDS = {"version", "sdist_sha256", "package_files_sha256"}
_PYTHON_FIELDS = {"version", "executable_sha256"}
_KICAD_FIELDS = {"version", "executable_sha256"}
_EXECUTION_FIELDS = {"worker_timeout_seconds", "kicad_timeout_seconds", "argv_profile"}
_RESOLUTION_FIELDS = {"executables", "files", "environment", "launcher_argv",
                      "installed_akcli"}
_EXECUTABLE_FIELDS = {"akcli", "python", "kicad"}
_RESOLUTION_FILE_FIELDS = {"libraries", "configs"}
_ENVIRONMENT_FIELDS = {"kicad", "akcli"}
_INSTALLED_FIELDS = {"package", "version", "files", "sha256"}
_FILE_MANIFEST_FIELDS = {"version", "files"}
_FILE_ENTRY_FIELDS = {"path", "sha256", "size_bytes", "role"}


def _closed(value, fields, label):
    if not isinstance(value, dict) or set(value) != fields:
        raise HostBindingError("%s has missing or unknown fields" % label)
    return value


def _text(value, label, empty=False):
    if not isinstance(value, str) or (not value and not empty) or any(ord(c) < 32 for c in value):
        raise HostBindingError("invalid %s" % label)
    return value


def _sha(value, label):
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise HostBindingError("invalid digest %s" % label)
    return value


def _integer(value, label, minimum=None, maximum=None):
    if type(value) is not int:
        raise HostBindingError("invalid integer %s" % label)
    if minimum is not None and value < minimum:
        raise HostBindingError("invalid integer %s" % label)
    if maximum is not None and value > maximum:
        raise HostBindingError("%s exceeds the frozen maximum of %d" % (label, maximum))
    return value


def _absolute(value, label):
    text = _text(value, label)
    if not os.path.isabs(text):
        raise HostBindingError("%s must be an absolute host path" % label)
    return text


def _logical_path(value, label):
    """A portable declaration path: candidate-relative, never a host path."""
    text = _text(value, label)
    if text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", text):
        raise HostBindingError("%s must be candidate-relative, not absolute" % label)
    if any(part in ("", ".", "..") for part in text.split("/")):
        raise HostBindingError("unsafe %s" % label)
    if any(char in text for char in '\\:<>"|?*'):
        raise HostBindingError("unsafe %s" % label)
    return text


def _environment(value, label):
    if not isinstance(value, dict):
        raise HostBindingError("the %s environment must be a mapping" % label)
    for key, item in value.items():
        _text(key, "environment name")
        _text(item, "environment value", empty=True)
    return dict(value)


def _declared_files(value, label):
    """Validate one portable FileManifest and index it by logical path."""
    _closed(value, _FILE_MANIFEST_FIELDS, "%s manifest" % label)
    if type(value["version"]) is not int or value["version"] != 1:
        raise HostBindingError("unsupported %s manifest version" % label)
    rows = value["files"]
    if not isinstance(rows, list):
        raise HostBindingError("the %s manifest files must be a list" % label)
    indexed, folded = {}, set()
    for row in rows:
        _closed(row, _FILE_ENTRY_FIELDS, "%s entry" % label)
        path = _logical_path(row["path"], "%s path" % label)
        if path.casefold() in folded:
            raise HostBindingError("duplicate or case-colliding %s path" % label)
        folded.add(path.casefold())
        _sha(row["sha256"], "%s digest" % label)
        _integer(row["size_bytes"], "%s size" % label, 0)
        if row["role"] != _READONLY_ROLE:
            raise HostBindingError("a %s file must be a %s" % (label, _READONLY_ROLE))
        indexed[path] = row
    return indexed


def validate_host_binding(binding):
    """Validate both layers and return a normalized copy, or raise.

    Normalization only rewrites host paths to their normpath form, so two hosts
    that spell the same path differently agree on the binding digest.  Nothing is
    inferred: every value that reaches a derived slice is read from this binding.
    """
    _closed(binding, _TOP_FIELDS, "host toolchain binding")
    if type(binding["version"]) is not int or binding["version"] != VERSION:
        raise HostBindingError("unsupported host toolchain binding version")

    manifest = _closed(binding["manifest"], _MANIFEST_FIELDS, "portable manifest")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise HostBindingError("unsupported portable manifest version")

    akcli = _closed(manifest["akcli"], _AKCLI_FIELDS, "akcli declaration")
    _text(akcli["version"], "akcli version")
    if akcli["version"] != AKCLI_VERSION:
        raise HostBindingError("the binding does not pin akcli %s" % AKCLI_VERSION)
    _sha(akcli["sdist_sha256"], "akcli sdist digest")
    _declared_files(akcli["package_files_sha256"], "akcli package files")

    python_decl = _closed(manifest["python"], _PYTHON_FIELDS, "python declaration")
    _text(python_decl["version"], "python version")
    _sha(python_decl["executable_sha256"], "python executable digest")

    kicad = _closed(manifest["kicad"], _KICAD_FIELDS, "kicad declaration")
    _text(kicad["version"], "kicad version")
    if kicad["version"] != REQUIRED_KICAD_VERSION:
        raise HostBindingError("the binding does not pin KiCad %s" % REQUIRED_KICAD_VERSION)
    _sha(kicad["executable_sha256"], "kicad executable digest")

    libraries = _declared_files(manifest["libraries"], "library")
    configs = _declared_files(manifest["configs"], "config")

    execution = _closed(manifest["execution"], _EXECUTION_FIELDS, "execution declaration")
    _integer(execution["worker_timeout_seconds"], "worker timeout", 1, MAX_TIMEOUT_SECONDS)
    _integer(execution["kicad_timeout_seconds"], "kicad timeout", 1, MAX_TIMEOUT_SECONDS)
    if execution["argv_profile"] != ARGV_PROFILE:
        raise HostBindingError("the binding does not use the frozen argv profile %s"
                               % ARGV_PROFILE)

    resolution = _closed(binding["resolution"], _RESOLUTION_FIELDS, "host resolution")
    executables = _closed(resolution["executables"], _EXECUTABLE_FIELDS, "executable map")
    for name in ("akcli", "python", "kicad"):
        _absolute(executables[name], "%s executable" % name)

    files = _closed(resolution["files"], _RESOLUTION_FILE_FIELDS, "resolution file map")
    for label, declared in (("libraries", libraries), ("configs", configs)):
        mapping = files[label]
        if not isinstance(mapping, dict):
            raise HostBindingError("the %s resolution must be a mapping" % label)
        for logical, host in mapping.items():
            _logical_path(logical, "%s logical path" % label)
            _absolute(host, "%s host path" % label)
        if set(mapping) != set(declared):
            raise HostBindingError(
                "the %s resolution must map exactly the declared logical paths" % label)

    environment = _closed(resolution["environment"], _ENVIRONMENT_FIELDS,
                          "resolution environment")
    _environment(environment["kicad"], "kicad")
    _environment(environment["akcli"], "akcli")

    launcher = resolution["launcher_argv"]
    if not isinstance(launcher, list) or any(
            not isinstance(item, str) or not item or not os.path.isabs(item)
            for item in launcher):
        raise HostBindingError("launcher_argv entries must be absolute host paths")

    installed = _closed(resolution["installed_akcli"], _INSTALLED_FIELDS,
                        "installed akcli observation")
    if installed["package"] != AKCLI_PACKAGE:
        raise HostBindingError("the binding does not pin the %s distribution" % AKCLI_PACKAGE)
    _text(installed["version"], "installed akcli version")
    if installed["version"] != akcli["version"]:
        raise HostBindingError("the declared and the installed akcli versions disagree")
    _integer(installed["files"], "installed file count", 0)
    _sha(installed["sha256"], "installed akcli digest")

    normalized = copy.deepcopy(binding)
    resolved = normalized["resolution"]
    for name in ("akcli", "python", "kicad"):
        resolved["executables"][name] = os.path.normpath(resolved["executables"][name])
    for label in ("libraries", "configs"):
        resolved["files"][label] = {logical: os.path.normpath(host)
                                    for logical, host in resolved["files"][label].items()}
    resolved["launcher_argv"] = [os.path.normpath(item)
                                 for item in resolved["launcher_argv"]]
    return normalized


def host_binding_sha256(binding):
    """The canonical digest of the whole two-layer host identity."""
    return canonical_sha256("toolchain", validate_host_binding(binding))


def toolchain_slice_sha256(slice_manifest):
    """The digest a C3/C4 receipt carries for one derived slice."""
    return canonical_sha256("toolchain", slice_manifest)


def _resolved_files(declared, mapping):
    """Project portable declarations onto their resolved host paths for C3."""
    rows = []
    for path in sorted(declared):
        entry = declared[path]
        rows.append({"path": mapping[path], "sha256": entry["sha256"],
                     "size_bytes": entry["size_bytes"], "role": entry["role"]})
    return {"version": 1, "files": rows}


def _accepted(slice_manifest, validator, label):
    """A derived slice is only a slice if its own layer accepts it unchanged."""
    try:
        validator(slice_manifest)
    except (ValueError, TypeError) as exc:
        raise HostBindingError("the derived %s slice is not accepted by its layer: %s"
                               % (label, exc)) from exc
    return slice_manifest


def derive_kicad_slice(binding):
    """Derive the C3 KiCad slice; gates.repair_verification accepts it unchanged."""
    normalized = validate_host_binding(binding)
    manifest = normalized["manifest"]
    resolution = normalized["resolution"]
    slice_manifest = {
        "version": 1,
        "kicad_cli": resolution["executables"]["kicad"],
        "kicad_version": manifest["kicad"]["version"],
        "kicad_cli_sha256": manifest["kicad"]["executable_sha256"],
        # The frozen command runs kicad-cli directly.  C3 refuses any launcher, so
        # the akcli launcher in resolution never reaches this slice.
        "launcher_argv": [],
        "arguments": list(EXPORT_ARGUMENTS),
        "timeout_seconds": manifest["execution"]["kicad_timeout_seconds"],
        "environment": dict(resolution["environment"]["kicad"]),
        "libraries": _resolved_files(_declared_files(manifest["libraries"], "library"),
                                     resolution["files"]["libraries"]),
        "configs": _resolved_files(_declared_files(manifest["configs"], "config"),
                                   resolution["files"]["configs"]),
    }
    return _accepted(slice_manifest, _kicad_validator, "kicad")


def derive_akcli_slice(binding, candidate_symbol_digest):
    """Derive the C4 akcli/Python slice; tools.akcli_adapter accepts it unchanged.

    candidate_symbol_digest is a candidate-specific input, not a host property:
    the C4 adapter computes it from the current document's embedded library.
    """
    normalized = validate_host_binding(binding)
    _sha(candidate_symbol_digest, "candidate symbol digest")
    manifest = normalized["manifest"]
    resolution = normalized["resolution"]
    slice_manifest = {
        "version": 1,
        "akcli_executable": resolution["executables"]["akcli"],
        "akcli_version": manifest["akcli"]["version"],
        # An observation of the installed distribution, taken from the host layer.
        # It is NOT derived from manifest.akcli.sdist_sha256 or
        # manifest.akcli.package_files_sha256: those are declarations in another
        # domain and this contract defines no canonical derivation between them.
        "akcli_artifact_sha256": resolution["installed_akcli"]["sha256"],
        # One frozen truth source: the upstream commit follows from the frozen argv
        # profile instead of a second host-supplied field.
        "akcli_upstream_commit": AKCLI_UPSTREAM_COMMIT,
        "worker_python": resolution["executables"]["python"],
        "symbol_digest": candidate_symbol_digest,
        "launcher_argv": list(resolution["launcher_argv"]),
        "timeout_seconds": manifest["execution"]["worker_timeout_seconds"],
        "environment": dict(resolution["environment"]["akcli"]),
    }
    return _accepted(slice_manifest, _akcli_validator, "akcli")


def _reason(detail):
    return {"code": "REPAIR_INPUT_DRIFT", "stage": "PRECHECK", "object_id": None,
            "detail": detail}


def same_host_toolchain(c3_toolchain_sha256, c4_toolchain_sha256, binding,
                        candidate_symbol_digest):
    """Prove both receipts trace back to one host toolchain binding.

    PASS means each receipt hash equals the digest of the slice derived from this
    binding.  It does NOT mean the two receipt hashes are equal: they are
    different slices and their digests never match.
    """
    result = {"status": "BLOCKED", "host_binding_sha256": None,
              "expected_c3_sha256": None, "expected_c4_sha256": None, "reasons": []}
    try:
        _sha(c3_toolchain_sha256, "C3 toolchain digest")
        _sha(c4_toolchain_sha256, "C4 toolchain digest")
        normalized = validate_host_binding(binding)
        expected_c3 = toolchain_slice_sha256(derive_kicad_slice(normalized))
        expected_c4 = toolchain_slice_sha256(
            derive_akcli_slice(normalized, candidate_symbol_digest))
        result.update(host_binding_sha256=host_binding_sha256(normalized),
                      expected_c3_sha256=expected_c3,
                      expected_c4_sha256=expected_c4)
        reasons = []
        if c3_toolchain_sha256 != expected_c3:
            reasons.append(_reason("the C3 receipt was not produced by this host "
                                   "binding's KiCad slice"))
        if c4_toolchain_sha256 != expected_c4:
            reasons.append(_reason("the C4 receipt was not produced by this host "
                                   "binding's akcli slice"))
        if reasons:
            result["reasons"] = reasons
            return result
        result["status"] = "PASS"
    except (HostBindingError, ValueError, TypeError) as exc:
        result["reasons"] = [_reason("unverifiable host toolchain binding: %s" % exc)]
    return result
