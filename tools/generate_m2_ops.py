"""Generate current M2 ops with akcli 0.21.0 plus controlled PWR_FLAG support."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Mapping, Optional, Tuple


EXPECTED_AKCLI_VERSION = "akcli 0.21.0 (protocol 2)"
DEFAULT_AKCLI = Path(r"C:\Users\fuker\AppData\Local\hermes\hermes-agent\venv\Scripts\akcli.exe")
EVIDENCE_SCHEMA = "https://aedl.local/schemas/m2-ops-validation.v1.json"
POWER_FLAG_POSITIONS = {
    "#FLG01": (600, 600),
    "#FLG02": (1800, 600),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_object(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def split_akcli_intent(intent: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
    """Return an akcli-schema intent and the supported project virtual parts."""
    if intent.get("protocol_version") != 1:
        raise ValueError("intent protocol_version must be 1")
    components = intent.get("components")
    nets = intent.get("nets")
    if not isinstance(components, dict) or not isinstance(nets, dict):
        raise ValueError("intent components/nets must be objects")

    virtual: Dict[str, Dict[str, Any]] = {}
    for ref, component in components.items():
        if not isinstance(component, dict):
            raise ValueError(f"component {ref} must be an object")
        if component.get("virtual"):
            if (
                ref not in POWER_FLAG_POSITIONS
                or component.get("lib_id") != "power:PWR_FLAG"
                or component.get("value") != "PWR_FLAG"
                or set(component) != {"lib_id", "value", "virtual"}
            ):
                raise ValueError(f"unsupported virtual component {ref}")
            virtual[ref] = copy.deepcopy(component)
    if set(virtual) != set(POWER_FLAG_POSITIONS):
        raise ValueError(f"virtual PWR_FLAG set must be exactly {sorted(POWER_FLAG_POSITIONS)}")

    result = copy.deepcopy(dict(intent))
    result["components"] = {
        ref: component for ref, component in result["components"].items() if ref not in virtual
    }
    filtered_nets: Dict[str, List[str]] = {}
    for net_name, members in result["nets"].items():
        if not isinstance(members, list):
            raise ValueError(f"intent net {net_name} must be a list")
        filtered = [member for member in members if member.split(".", 1)[0] not in virtual]
        if not filtered:
            raise ValueError(f"intent net {net_name} becomes empty after virtual filtering")
        filtered_nets[net_name] = filtered
    result["nets"] = filtered_nets
    return result, virtual


def inject_virtual_power_ops(
    base_ops: Mapping[str, Any],
    canonical_intent: Mapping[str, Any],
    virtual: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    """Inject deterministic PWR_FLAG placement and net-label operations."""
    if base_ops.get("protocol_version") != 2 or not isinstance(base_ops.get("ops"), list):
        raise ValueError("akcli output must be protocol 2 with an ops list")
    if set(virtual) != set(POWER_FLAG_POSITIONS):
        raise ValueError("virtual PWR_FLAG set is incomplete")
    nets = canonical_intent.get("nets")
    if not isinstance(nets, dict):
        raise ValueError("canonical intent nets must be an object")
    result = copy.deepcopy(dict(base_ops))
    ops: List[Dict[str, Any]] = result["ops"]
    existing_refs = {
        op.get("designator") for op in ops if isinstance(op, dict) and op.get("op") == "place_component"
    }
    if existing_refs & set(virtual):
        raise ValueError("akcli output already contains project virtual power flags")

    place_ops: List[Dict[str, Any]] = []
    label_ops: List[Dict[str, Any]] = []
    for ref in sorted(virtual):
        pin = f"{ref}.1"
        matched_nets = [name for name, members in nets.items() if isinstance(members, list) and pin in members]
        if len(matched_nets) != 1:
            raise ValueError(f"{pin} must belong to exactly one canonical net")
        component = virtual[ref]
        x_mil, y_mil = POWER_FLAG_POSITIONS[ref]
        place_ops.append(
            {
                "op": "place_component",
                "lib_id": component["lib_id"],
                "designator": ref,
                "x_mil": x_mil,
                "y_mil": y_mil,
                "value": component["value"],
            }
        )
        label_ops.append({"op": "add_net_label", "name": matched_nets[0], "at": pin})

    first_non_place = next(
        (index for index, op in enumerate(ops) if not isinstance(op, dict) or op.get("op") != "place_component"),
        len(ops),
    )
    ops[first_non_place:first_non_place] = place_ops
    first_no_connect = next(
        (index for index, op in enumerate(ops) if isinstance(op, dict) and op.get("op") == "add_no_connect"),
        len(ops),
    )
    ops[first_no_connect:first_no_connect] = label_ops
    result["_generator"] = (
        "tools/generate_m2_ops.py: akcli 0.21.0 from-intent + "
        "controlled virtual PWR_FLAG compatibility"
    )
    return result


def _run(command: List[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=str(cwd), capture_output=True, timeout=180)


def generate(
    root: Path,
    intent_path: Path,
    output_path: Path,
    evidence_path: Path,
    akcli_path: Path,
) -> Dict[str, Any]:
    root = Path(root).resolve()
    intent_path = Path(intent_path).resolve()
    output_path = Path(output_path).resolve()
    evidence_path = Path(evidence_path).resolve()
    akcli_path = Path(akcli_path).resolve()
    if not akcli_path.is_file():
        raise ValueError(f"locked akcli executable does not exist: {akcli_path}")
    version_run = _run([str(akcli_path), "--version"], root)
    version = version_run.stdout.decode("utf-8", errors="replace").strip()
    if version_run.returncode != 0 or version != EXPECTED_AKCLI_VERSION:
        raise ValueError(f"akcli version mismatch: expected {EXPECTED_AKCLI_VERSION!r}, observed {version!r}")

    canonical = _load_object(intent_path)
    akcli_intent, virtual = split_akcli_intent(canonical)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".m2-ops-", dir=str(output_path.parent)) as temp_dir:
        temporary_root = Path(temp_dir)
        compatible_intent = temporary_root / "intent_akcli_v0.21.0.json"
        physical_ops = temporary_root / "ops_physical.json"
        injected_ops = temporary_root / "ops_injected.json"
        compatible_intent.write_text(
            json.dumps(akcli_intent, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        from_intent = _run(
            [str(akcli_path), "ops", "from-intent", str(compatible_intent), "-o", str(physical_ops), "--json"],
            root,
        )
        if from_intent.returncode != 0 or not physical_ops.is_file():
            stderr = from_intent.stderr.decode("utf-8", errors="replace")[-2000:]
            stdout = from_intent.stdout.decode("utf-8", errors="replace")[-2000:]
            raise ValueError(f"akcli ops from-intent failed: {stdout} {stderr}".strip())
        final_ops = inject_virtual_power_ops(_load_object(physical_ops), canonical, virtual)
        injected_ops.write_text(json.dumps(final_ops, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validation = _run([str(akcli_path), "ops", "validate", str(injected_ops), "--json"], root)
        if validation.returncode != 0:
            stderr = validation.stderr.decode("utf-8", errors="replace")[-2000:]
            stdout = validation.stdout.decode("utf-8", errors="replace")[-2000:]
            raise ValueError(f"akcli ops validate failed: {stdout} {stderr}".strip())
        injected_ops.replace(output_path)

    final_data = _load_object(output_path)
    evidence = {
        "$schema": EVIDENCE_SCHEMA,
        "schema_version": 1,
        "generated_at": _utc_now(),
        "target": "src/hardware/m2-board/ops_gen.json",
        "ops_sha256": _sha256(output_path),
        "op_count": len(final_data["ops"]),
        "valid": True,
        "errors": [],
        "generator": f"{EXPECTED_AKCLI_VERSION}; tools/generate_m2_ops.py controlled virtual compatibility",
        "validator": f"{EXPECTED_AKCLI_VERSION}; akcli ops validate --json",
    }
    _write_json_atomic(evidence_path, evidence)
    return evidence


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--intent", type=Path, default=Path("src/hardware/m2-board/intent_v1.json"))
    parser.add_argument("--output", type=Path, default=Path("src/hardware/m2-board/ops_gen.json"))
    parser.add_argument(
        "--evidence",
        type=Path,
        default=Path("notes/m2-evidence-reset/generated/ops_validate_current.json"),
    )
    parser.add_argument("--akcli", type=Path, default=DEFAULT_AKCLI)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        evidence = generate(
            root,
            args.intent if args.intent.is_absolute() else root / args.intent,
            args.output if args.output.is_absolute() else root / args.output,
            args.evidence if args.evidence.is_absolute() else root / args.evidence,
            args.akcli,
        )
    except Exception as exc:
        print(f"[M2-OPS] FAIL {type(exc).__name__}: {exc}")
        return 1
    print(f"[M2-OPS] PASS op_count={evidence['op_count']} sha256={evidence['ops_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
