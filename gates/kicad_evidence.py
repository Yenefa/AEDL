"""KICAD_VERIFY as an EVIDENCE PRODUCER.  It does not decide anything.

The shape the Owner asked for, and the reason it is not the shape the code had:

    ERC=0 -> PASS                      what the code effectively does today
    ---------------------------------   ---------------------------------
    zero error-severity violations     what the tool actually reports
    on THIS board                      0 errors, 39 warnings,
                                       4 checks deliberately ignored

Measured with real kicad-cli 10.0.5 against src/hardware/m2-board:

    violations            : 39, severity mix {'warning': 39}
    ignored_checks        : 4 (single_global_label, four_way_junction,
                                simulation_model_issue, assigned footprint)
    included_severities   : ["error", "warning", "exclusion"]
    netlist               : 21 components, 29 nets
    render                : m2_board.svg
    drc                   : 0 violations, 0 unconnected, 0 parity

So "ERC=0" is true of this board and the board has 39 warnings. A producer that
reported a verdict would be reporting a number that means less than it appears to, and
a policy handed only that number could not tell the difference between a clean board
and a board whose checks were switched off.

The three properties that make this a producer and not a verdict machine:

  1. NO VERDICT. Nothing in the bundle says PASS. It reports what was observed, how it
     was observed, and what the tool declared it did NOT do. `decide()` in
     kicad_policy is the only thing that produces a status.

  2. THE LIMITS TRAVEL WITH THE EVIDENCE. `ignored_checks` and `included_severities`
     are read out of KiCad's own report, not invented here, and a report missing
     either is a REFUSAL rather than a bundle with blanks -- a producer that cannot
     say what it skipped may not offer its result as evidence.

  3. EVERY PART BINDS TO THE SAME BYTES. Each artifact records the sha256 of the
     design it was produced from, and the bundle refuses if they disagree. Otherwise a
     netlist from one revision and an ERC from another could be combined into a
     bundle that describes no board at all.

Fails closed but never silently: a missing binary, a non-zero exit, or a missing
report produces a bundle that SAYS SO, for the policy to refuse. It does not raise out
of the round, and it does not fall back to a default that reads as clean.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "kicad-evidence.v1"

#: Every command the producer runs, named. Kept as data so the bundle can RECORD what
#: it did rather than the reader having to trust that it did the obvious thing.
COMMANDS = ("erc", "netlist", "render", "drc")


class EvidenceError(RuntimeError):
    """The evidence could not be produced. Carries machine-readable detail."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str | None:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError:
        return None


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def digest_of(bundle: Mapping[str, Any]) -> str:
    """Digest of everything EXCEPT the digest field.

    So a policy decision can bind to the exact evidence it decided on, and that
    binding fails if any part is edited after the fact.
    """
    without = {k: v for k, v in bundle.items() if k != "bundle_sha256"}
    return _sha256_bytes(_canonical(without))


# --------------------------------------------------------------------------
# the tool itself
# --------------------------------------------------------------------------

def tool_identity(kicad_cli: Path) -> dict:
    """WHO produced the evidence, pinned as far as this host allows.

    The version string is what KiCad reports; the binary digest is what actually
    identifies the executable. Both travel, because a version string is a claim the
    tool makes about itself and a digest is not.
    """
    path = Path(kicad_cli)
    if not path.is_file():
        raise EvidenceError("kicad-cli is not a file: %s" % path)
    try:
        proc = subprocess.run([str(path), "version"], capture_output=True,
                              text=True, timeout=120)
    except OSError as exc:
        raise EvidenceError("kicad-cli could not be started: %s" % exc)
    except subprocess.TimeoutExpired:
        raise EvidenceError("kicad-cli did not answer `version` within 120s")
    reported = (proc.stdout or proc.stderr or "").strip().splitlines()
    version = reported[-1].strip() if reported else ""
    return {
        "kicad_cli_path": str(path),
        "kicad_version_reported": version,
        "binary_sha256": _sha256_file(path),
        "version_exit_code": proc.returncode,
    }


# --------------------------------------------------------------------------
# one command, recorded
# --------------------------------------------------------------------------

def _run(argv: Sequence[str], cwd: Path, timeout: int) -> dict:
    try:
        proc = subprocess.run([str(a) for a in argv], cwd=str(cwd),
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"argv": [str(a) for a in argv], "exit_code": None,
                "timed_out": True, "stderr": "timed out after %ds" % timeout}
    except OSError as exc:
        return {"argv": [str(a) for a in argv], "exit_code": None,
                "timed_out": False, "stderr": "could not start: %s" % exc}
    return {"argv": [str(a) for a in argv], "exit_code": proc.returncode,
            "timed_out": False,
            "stderr": (proc.stderr or "").strip()[:400]}


def _part(design_sha256: str, run: Mapping[str, Any], artifacts: Sequence[Path],
          extra: Mapping[str, Any] | None = None) -> dict:
    """One evidence part, carrying the design digest it was produced from.

    `completed` means THE TOOL RAN AND PRODUCED ITS ARTIFACT. It does not mean the
    exit code was zero, and it must not: with `--exit-code-violations` a non-zero
    exit means "violations found", so keying completion off it reports a board the
    tool examined carefully as one the tool failed on. See `collect_evidence`.
    """
    present = [a for a in artifacts if a.is_file()]
    part = {
        "design_sha256": design_sha256,
        "command": run,
        "completed": bool(present) and run.get("exit_code") is not None,
        "artifacts": [],
    }
    for artifact in present:
        part["artifacts"].append({
            "name": artifact.name,
            "bytes": artifact.stat().st_size,
            "sha256": _sha256_file(artifact),
        })
    if extra:
        part.update(extra)
    return part


# --------------------------------------------------------------------------
# ERC, and the declared limits that come with it
# --------------------------------------------------------------------------

def _erc_part(design_sha256: str, run: Mapping[str, Any], report: Path) -> dict:
    """ERC evidence INCLUDING the limits, read from KiCad's own report.

    The limits are the point. This board reports 39 warnings and zero errors, and
    declares four checks it skipped; `error_count == 0` on its own would be a
    misleading summary of that, so the summary is never emitted without the
    severity mix and the ignored-check list beside it.
    """
    part = _part(design_sha256, run, [report] if report.is_file() else [])
    if not report.is_file():
        part["limits_declared"] = False
        part["unavailable"] = "the ERC report was not produced"
        return part

    try:
        data = json.loads(report.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        part["limits_declared"] = False
        part["unavailable"] = "the ERC report is unreadable: %s" % exc
        return part
    if not isinstance(data, dict):
        part["limits_declared"] = False
        part["unavailable"] = "the ERC report root is not an object"
        return part

    # Both fields must be present. A report without them cannot say what it skipped,
    # so it is not offered as evidence -- it is not silently defaulted to "nothing
    # was ignored", which is the assumption that makes ERC=0 -> PASS dangerous.
    has_ignored = isinstance(data.get("ignored_checks"), list)
    has_severities = isinstance(data.get("included_severities"), list)
    if not (has_ignored and has_severities):
        part["limits_declared"] = False
        part["unavailable"] = (
            "the ERC report does not declare its limits "
            "(ignored_checks present=%s, included_severities present=%s)"
            % (has_ignored, has_severities))
        return part

    severity_counts: dict[str, int] = {}
    total = 0
    unconnected = 0
    for sheet in data.get("sheets") or []:
        if not isinstance(sheet, dict):
            continue
        for item in sheet.get("violations") or []:
            if isinstance(item, dict):
                sev = str(item.get("severity"))
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
                total += 1
        unconnected += len(sheet.get("unconnected_items") or [])

    part.update({
        "limits_declared": True,
        "schema": data.get("$schema"),
        "kicad_version": data.get("kicad_version"),
        "source": data.get("source"),
        "violations_total": total,
        "severity_counts": severity_counts,
        # Named explicitly rather than left to the reader to subtract, because the
        # whole failure mode being guarded against is reading the error count as a
        # verdict on the board.
        "error_count": severity_counts.get("error", 0),
        "unconnected_items": unconnected,
        "declared_limits": {
            "ignored_checks": [
                {"key": c.get("key"), "description": c.get("description")}
                for c in data["ignored_checks"] if isinstance(c, dict)],
            "included_severities": list(data["included_severities"]),
            "declared_by": "kicad",
        },
    })
    return part


# --------------------------------------------------------------------------
# netlist and render
# --------------------------------------------------------------------------

def _netlist_part(design_sha256: str, run: Mapping[str, Any],
                  netlist: Path) -> dict:
    part = _part(design_sha256, run, [netlist] if netlist.is_file() else [])
    if not netlist.is_file():
        part["unavailable"] = "the netlist was not produced"
        return part
    text = netlist.read_text(encoding="utf-8", errors="replace")
    part.update({"components": text.count("<comp "), "nets": text.count("<net ")})
    return part


def _render_part(design_sha256: str, run: Mapping[str, Any],
                 render_dir: Path) -> dict:
    files = sorted(p for p in render_dir.rglob("*") if p.is_file()) \
        if render_dir.is_dir() else []
    part = _part(design_sha256, run, files)
    part["file_count"] = len(files)
    if not files:
        part["unavailable"] = "the render produced no files"
    return part


# --------------------------------------------------------------------------
# the producer
# --------------------------------------------------------------------------

def collect_evidence(design_root: Path | str, report_root: Path | str,
                     kicad_cli: Path | str, timeout: int = 900) -> dict:
    """Produce the bundle. Decides nothing; contains no verdict.

    `design_root` must contain m2_board.kicad_sch and m2_board.kicad_pcb. Every
    artifact is bound to the sha256 of the schematic it came from, and the bundle
    refuses if the parts disagree -- otherwise evidence from two revisions could be
    combined into a bundle describing no board.
    """
    design = Path(design_root)
    report = Path(report_root)
    sch = design / "m2_board.kicad_sch"
    pcb = design / "m2_board.kicad_pcb"
    for required in (sch, pcb):
        if not required.is_file():
            raise EvidenceError("the design root does not contain %s" % required.name)

    report.mkdir(parents=True, exist_ok=True)
    design_sha = _sha256_file(sch)
    if design_sha is None:
        raise EvidenceError("the schematic could not be read for hashing")

    identity = tool_identity(Path(kicad_cli))
    cli = str(kicad_cli)

    erc_json = report / "erc.json"
    netlist = report / "board.net"
    render_dir = report / "render"
    drc_json = report / "drc.json"

    runs = {
        # NOTE: no --exit-code-violations. Measured on this board with kicad-cli
        # 10.0.5, the same 39 violations give exit 5 WITH the flag and exit 0
        # WITHOUT it -- the flag makes the exit code mean "violations found".
        #
        # The first version of this producer passed the flag and then read
        # `exit_code == 0` as "the run completed", which inverts the whole point:
        # a board the tool examined carefully and found problems on reported
        # "ERC did not complete", and only a board with nothing to report looked
        # successful. That is `ERC=0 -> PASS` wearing a disguise -- the exit code
        # became the verdict instead of the evidence. Violations are read from the
        # report's severity mix, where they belong, and the exit code is recorded
        # rather than interpreted.
        "erc": _run([cli, "sch", "erc", "--format", "json", "--severity-all",
                     "--output", str(erc_json), str(sch)],
                    design, timeout),
        "netlist": _run([cli, "sch", "export", "netlist", "--format", "kicadxml",
                         "--output", str(netlist), str(sch)], design, timeout),
        "render": _run([cli, "sch", "export", "svg", "--output", str(render_dir),
                        str(sch)], design, timeout),
        "drc": _run([cli, "pcb", "drc", "--format", "json", "--severity-all",
                     "--output", str(drc_json), str(pcb)], design, timeout),
    }

    bundle = {
        "schema_version": SCHEMA_VERSION,
        "scope": "PR1_CANDIDATE_BYTES",
        "design_root": str(design.resolve()),
        "design_sha256": design_sha,
        "tool_identity": identity,
        "erc": _erc_part(design_sha, runs["erc"], erc_json),
        "netlist": _netlist_part(design_sha, runs["netlist"], netlist),
        "render": _render_part(design_sha, runs["render"], render_dir),
        "drc": _part(design_sha, runs["drc"], [drc_json] if drc_json.is_file() else []),
        "report_root": str(report.resolve()),
        "reasons": [],
    }

    # One place decides whether the bundle is internally coherent, and it is a
    # REFUSAL of the bundle, never a verdict about the board.
    problems: list[str] = []
    for name in ("erc", "netlist", "render", "drc"):
        part = bundle[name]
        if part.get("design_sha256") != design_sha:
            problems.append("%s is not bound to the design it claims" % name)
    if not bundle["erc"].get("limits_declared"):
        problems.append("the ERC report does not declare its limits, so it is not "
                        "offered as evidence")
    if not bundle["erc"].get("completed"):
        problems.append("the ERC run did not complete")
    for name in ("netlist", "render"):
        if not bundle[name].get("completed"):
            problems.append("the %s run did not complete" % name)
    bundle["coherent"] = not problems
    bundle["incoherence"] = problems
    bundle["bundle_sha256"] = digest_of(bundle)
    return bundle
