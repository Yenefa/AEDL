"""Task Envelope parsing for the AEDL control plane.

The envelope is a deliberately small YAML subset with NO external dependency:
the machine fields (base / dependencies / allowed_paths / forbidden_paths)
are parsed strictly; everything else (goal, scope, acceptance, budget, ...)
is opaque free text preserved for humans and never interpreted by tooling.

Supported shapes (see docs/ENVELOPE_EXAMPLE.yaml):

    task: GH-11
    base:
      branch: master
      sha: abc123
    dependencies:
      - ref: GH-9
        required_state: merged      # merged | closed | open
      - GH-12: closed               # compact form
    allowed_paths:
      - src/**
    forbidden_paths:
      - gates/**

Fail-closed: anything malformed inside a machine section is collected in
errors; callers must BLOCK on errors rather than guessing.
"""

from __future__ import annotations

import fnmatch
import re

MACHINE_SECTIONS = ("base", "dependencies", "allowed_paths", "forbidden_paths", "exceptions")
DEPENDENCY_STATES = ("merged", "closed", "open")
EXCEPTION_FLAGS = ("allow_dirty", "allow_drift", "skip_deps")
EXCEPTION_FIELDS = ("permitted", "reason", "authority", "granted_by", "decision_ref")


def parse_envelope(text: str) -> dict:
    """Parse envelope text into machine fields. Never raises on content."""
    envelope = {
        "task": None,
        "base_branch": None,
        "base_sha": None,
        "dependencies": [],
        "allowed_paths": [],
        "forbidden_paths": [],
        "exceptions": {},
        "errors": [],
        "warnings": [],
    }
    section = None
    current_dep = None
    current_exc = None
    exc_indent = 0
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Inline comments: '#' is only a comment when preceded by whitespace,
        # so provenance refs like `GH-20#comment-1` stay byte-for-byte.
        line = re.sub(r"\s+#.*$", "", line).rstrip()
        indent = len(raw) - len(raw.lstrip(" "))
        if indent == 0:
            current_dep = None
            current_exc = None
            m = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
            if m:
                key, value = m.group(1), m.group(2).strip()
                if key == "task":
                    envelope["task"] = value.strip("\"'") or None
                    section = None
                elif key in MACHINE_SECTIONS:
                    section = key
                else:
                    section = None  # opaque free-text section
            else:
                envelope["errors"].append(f"line {lineno}: unsupported top-level syntax: {line}")
                section = None
        else:
            if section == "base":
                m = re.match(r"^(branch|sha):\s*(.*)$", line)
                if m:
                    value = m.group(2).strip().strip("\"'") or None
                    if m.group(1) == "branch":
                        envelope["base_branch"] = value
                    else:
                        envelope["base_sha"] = value
                else:
                    envelope["errors"].append(f"line {lineno}: unsupported base field: {line}")
            elif section == "dependencies":
                m = re.match(r"^-\s*(.+)$", line)
                if m:
                    item = m.group(1).strip()
                    ref = re.match(r"^ref:\s*([A-Za-z0-9_\-/#.]+)\s*$", item)
                    if ref:
                        current_dep = {"ref": ref.group(1), "required_state": None}
                        envelope["dependencies"].append(current_dep)
                    else:
                        compact = re.match(r"^([A-Za-z0-9_\-/#.]+):\s*(" + "|".join(DEPENDENCY_STATES) + r")\s*$", item)
                        if compact:
                            envelope["dependencies"].append({"ref": compact.group(1), "required_state": compact.group(2)})
                            current_dep = envelope["dependencies"][-1]
                        else:
                            envelope["errors"].append(f"line {lineno}: unsupported dependency item: {item}")
                            current_dep = None
                else:
                    dm = re.match(r"^required_state:\s*(" + "|".join(DEPENDENCY_STATES) + r")\s*$", line)
                    if dm and current_dep is not None:
                        current_dep["required_state"] = dm.group(1)
                    else:
                        envelope["errors"].append(f"line {lineno}: unsupported dependency field: {line}")
            elif section in ("allowed_paths", "forbidden_paths"):
                m = re.match(r"^-\s*(.+)$", line)
                if m:
                    envelope[section].append(m.group(1).strip())
                else:
                    envelope["errors"].append(f"line {lineno}: unsupported path item: {line}")
            elif section == "exceptions":
                m = re.match(r"^([a-z_]+):\s*(.*)$", line)
                if current_exc is None or indent <= exc_indent:
                    # a new exception flag (permitted=True + authority, or granted_by + decision_ref)
                    if m and m.group(1) in EXCEPTION_FLAGS and not m.group(2).strip():
                        current_exc = m.group(1)
                        exc_indent = indent
                        envelope["exceptions"][current_exc] = {}
                    else:
                        envelope["errors"].append(f"line {lineno}: unknown exception flag: {line}")
                        current_exc = None
                elif m and m.group(1) in EXCEPTION_FIELDS:
                    value = m.group(2).strip().strip("\"'")
                    if m.group(1) == "permitted":
                        envelope["exceptions"][current_exc]["permitted"] = value.lower() == "true"
                    else:
                        envelope["exceptions"][current_exc][m.group(1)] = value or None
                else:
                    envelope["errors"].append(f"line {lineno}: unsupported exception field: {line}")
            else:
                # free text inside an opaque section (goal/scope/acceptance/...)
                pass
    for dep in envelope["dependencies"]:
        if not dep.get("required_state"):
            envelope["errors"].append(f"dependency {dep['ref']} lacks required_state")
    for flag, exc in envelope["exceptions"].items():
        valid = (exc.get("permitted") is True and exc.get("authority")) or (
            exc.get("granted_by") and exc.get("decision_ref")
        )
        if not valid:
            envelope["errors"].append(
                f"exception {flag} malformed: need permitted+authority or granted_by+decision_ref"
            )
    return envelope


def path_in_scope(relpath: str, patterns) -> bool:
    """True when relpath matches any pattern. Patterns use forward slashes;
    'dir/**' also matches 'dir' itself and everything below it."""
    rel = relpath.replace("\\", "/")
    for pattern in patterns:
        pat = pattern.strip().replace("\\", "/")
        if not pat:
            continue
        if pat.endswith("/**"):
            prefix = pat[:-3].rstrip("/")
            if rel == prefix or rel.startswith(prefix + "/") or fnmatch.fnmatch(rel, pat):
                return True
        elif fnmatch.fnmatch(rel, pat):
            return True
    return False


def scope_violations(files, envelope) -> list:
    """Forbidden matches are violations; the whitelist is ALWAYS enforced:
    an empty/missing allowed_paths means ZERO write permission (FOREIGN =
    default read-only, AGENTS.md §2.2), so any changed file is a violation."""
    violations = []
    for rel in files:
        if path_in_scope(rel, envelope["forbidden_paths"]):
            violations.append(f"{rel}: matches forbidden path")
    for rel in files:
        if not path_in_scope(rel, envelope["allowed_paths"]):
            note = "" if envelope["allowed_paths"] else "; empty allowed_paths = zero write permission"
            violations.append(f"{rel}: outside allowed paths (FOREIGN, read-only){note}")
    return violations
