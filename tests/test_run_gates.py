import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from gates.run_gates import (
    EXPECTED_AKCLI_VERSION,
    EXPECTED_OPS_GENERATOR,
    EXPECTED_OPS_VALIDATOR,
    REQUIRED_ZIP_ENTRIES,
    _evaluate_delivery,
    _evaluate_intent,
    _evaluate_ops,
    _validate_ops_with_live_akcli,
    evaluate_evidence,
    run,
)


ROOT = Path(__file__).resolve().parents[1]


def _accept_live_ops_validation():
    """Keep structural gate tests independent of the host akcli installation."""
    return mock.patch(
        "gates.run_gates._validate_ops_with_live_akcli",
        return_value=({"version": EXPECTED_AKCLI_VERSION, "exit_code": 0}, []),
    )


class RunGatesTests(unittest.TestCase):
    def test_delivery_gate_rejects_cpl_that_differs_from_fresh_pcb_export(self):
        current = (ROOT / "delivery/pos.csv").read_text(encoding="utf-8-sig")
        with tempfile.TemporaryDirectory() as temp_dir:
            fresh = Path(temp_dir) / "fresh-cpl.csv"
            fresh.write_text(
                current.replace("C1,54.000000", "C1,55.000000", 1),
                encoding="utf-8-sig",
            )
            result = _evaluate_delivery(ROOT, fresh)

        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("fresh" in error.lower() for error in result["errors"]))

    def test_delivery_gate_rejects_stale_self_consistent_bom_and_pos(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "gates/bom").mkdir(parents=True)
            (root / "delivery").mkdir()
            (root / "src/hardware/m2-board").mkdir(parents=True)
            (root / "gates/bom/bom_v1.json").write_text(
                json.dumps({"items": [{"ref": "U1"}]}), encoding="utf-8"
            )
            (root / "delivery/pos.csv").write_text(
                "Ref,PosX,PosY\nU1,0,0\n", encoding="utf-8"
            )
            (root / "delivery/bom.csv").write_text(
                "Designator,Comment\nU1,part\n", encoding="utf-8"
            )
            (root / "src/hardware/m2-board/intent_v1.json").write_text(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "components": {
                            "U1": {"lib_id": "Device:R"},
                            "U2": {"lib_id": "Device:R"},
                            "#FLG01": {"lib_id": "power:PWR_FLAG", "virtual": True},
                        },
                        "nets": {"N": ["U1.1", "U2.1"]},
                    }
                ),
                encoding="utf-8",
            )
            with zipfile.ZipFile(root / "delivery/jlc_gerber_upload.zip", "w") as archive:
                for name in REQUIRED_ZIP_ENTRIES:
                    archive.writestr(name, "data")

            result = _evaluate_delivery(root)

        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("intent" in error.lower() for error in result["errors"]))

    def test_m2_intent_declares_two_virtual_power_flags(self):
        intent = json.loads(
            (ROOT / "src" / "hardware" / "m2-board" / "intent_v1.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            {
                ref
                for ref, component in intent["components"].items()
                if component.get("virtual")
                and component.get("lib_id") == "power:PWR_FLAG"
                and component.get("value") == "PWR_FLAG"
            },
            {"#FLG01", "#FLG02"},
        )
        self.assertIn("#FLG01.1", intent["nets"]["+5V"])
        self.assertIn("#FLG02.1", intent["nets"]["GND"])

    def test_m2_intent_encodes_repaired_datasheet_semantics(self):
        intent = json.loads(
            (ROOT / "src" / "hardware" / "m2-board" / "intent_v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {ref for ref, component in intent["components"].items() if not component.get("virtual")},
            {
                "U1", "U2", "U3", "J1", "SW1", "SW2", "D1",
                "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9",
                "C1", "C2", "C3", "C4", "C5",
            },
        )
        self.assertEqual(intent["components"]["R7"]["value"], "22R")
        self.assertEqual(intent["components"]["R8"]["value"], "22R")
        self.assertEqual(intent["components"]["R9"]["value"], "10k")
        self.assertEqual(intent["components"]["C5"]["value"], "1uF")
        self.assertEqual(intent["nets"]["USB_DP_CONN"], ["J1.A6", "J1.B6", "R7.1"])
        self.assertEqual(intent["nets"]["USB_DP"], ["R7.2", "U1.14"])
        self.assertEqual(intent["nets"]["USB_DM_CONN"], ["J1.A7", "J1.B7", "R8.1"])
        self.assertEqual(intent["nets"]["USB_DM"], ["R8.2", "U1.13"])
        self.assertIn("U2.2", intent["nets"]["GND"])
        self.assertIn("C5.2", intent["nets"]["GND"])
        self.assertIn("C5.1", intent["nets"]["EN"])
        self.assertIn("R9.1", intent["nets"]["+3V3"])
        self.assertIn("R9.2", intent["nets"]["BOOT"])
        all_members = {member for members in intent["nets"].values() for member in members}
        self.assertNotIn("U2.3", all_members)
        self.assertNotIn("U2.6", all_members)

    def test_m2_schematic_declares_power_flags_at_their_power_labels(self):
        schematic = (
            ROOT / "src" / "hardware" / "m2-board" / "m2_board.kicad_sch"
        ).read_text(encoding="utf-8")

        self.assertIn('(symbol "power:PWR_FLAG"', schematic)
        self.assertIn('(lib_id "power:PWR_FLAG") (at 15.24 15.24 0)', schematic)
        self.assertIn('(lib_id "power:PWR_FLAG") (at 45.72 15.24 0)', schematic)
        self.assertRegex(schematic, r'\(label "\+5V" \(at 15\.24 15\.24 (?:90|270)\)')
        self.assertRegex(schematic, r'\(label "GND" \(at 45\.72 15\.24 (?:90|270)\)')

    def test_intent_accepts_virtual_power_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            intent_path = root / "src" / "hardware" / "m2-board" / "intent_v1.json"
            intent_path.parent.mkdir(parents=True)
            intent_path.write_text(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "components": {
                            "U3": {"lib_id": "Regulator_Linear:ME6211C33M5"},
                            "U1": {"lib_id": "RF_Module:ESP32-C3-WROOM-02"},
                            "#FLG01": {
                                "lib_id": "power:PWR_FLAG",
                                "value": "PWR_FLAG",
                                "virtual": True,
                            },
                            "#FLG02": {
                                "lib_id": "power:PWR_FLAG",
                                "value": "PWR_FLAG",
                                "virtual": True,
                            },
                        },
                        "nets": {
                            "+5V": ["U3.1", "#FLG01.1"],
                            "GND": ["U1.9", "#FLG02.1"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = _evaluate_intent(root)

        self.assertEqual(result["status"], "pass", result["errors"])

    def test_historical_evidence_is_reported_as_blocked_not_green(self):
        manifest = evaluate_evidence(
            ROOT,
            ROOT / "notes/m1-evidence/g2_erc_m2board.json",
            ROOT / "notes/m1-evidence/g4_drc_final.json",
            ROOT / "tests/fixtures/board_review_before_release.json",
        )

        self.assertEqual(manifest["status"], "fail")
        by_name = {gate["name"]: gate for gate in manifest["gates"]}
        self.assertEqual(by_name["erc"]["status"], "fail")
        self.assertEqual(by_name["erc"]["details"]["error_count"], 2)
        self.assertEqual(by_name["drc"]["status"], "pass")
        self.assertEqual(by_name["board_review"]["status"], "fail")
        self.assertEqual(by_name["board_review"]["details"]["review_count"], 8)
        self.assertEqual(
            by_name["board_review"]["details"]["status_counts"],
            {"needs_physical": 8},
        )

    def test_m1_ops_proxy_cannot_satisfy_current_m2_gate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            proxy = root / "notes" / "m1-evidence" / "ops_validate.json"
            proxy.parent.mkdir(parents=True)
            proxy.write_text(
                json.dumps({"protocol_version": 2, "valid": True, "op_count": 99, "errors": []}),
                encoding="utf-8",
            )

            gate = _evaluate_ops(root)

        self.assertEqual(gate["status"], "fail")
        self.assertIn("m2-evidence-reset", gate["details"]["path"])
        self.assertNotIn("m1-evidence", gate["details"]["path"])

    def test_current_m2_ops_evidence_is_bound_to_ops_hash_and_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ops_path = root / "src" / "hardware" / "m2-board" / "ops_gen.json"
            evidence_path = root / "notes" / "m2-evidence-reset" / "generated" / "ops_validate_current.json"
            ops_path.parent.mkdir(parents=True)
            evidence_path.parent.mkdir(parents=True)
            ops = {"protocol_version": 2, "target_format": "kicad", "ops": [{"op": "place_component"}]}
            encoded = (json.dumps(ops) + "\n").encode("utf-8")
            ops_path.write_bytes(encoded)
            evidence_path.write_text(
                json.dumps(
                    {
                        "$schema": "https://aedl.local/schemas/m2-ops-validation.v1.json",
                        "schema_version": 1,
                        "generated_at": "2026-08-30T00:00:00Z",
                        "target": "src/hardware/m2-board/ops_gen.json",
                        "ops_sha256": hashlib.sha256(encoded).hexdigest(),
                        "op_count": 1,
                        "valid": True,
                        "errors": [],
                        "generator": EXPECTED_OPS_GENERATOR,
                        "validator": EXPECTED_OPS_VALIDATOR,
                    }
                ),
                encoding="utf-8",
            )

            with _accept_live_ops_validation():
                self.assertEqual(_evaluate_ops(root)["status"], "pass")
            ops["ops"].append({"op": "add_net_label"})
            ops_path.write_text(json.dumps(ops), encoding="utf-8")
            with _accept_live_ops_validation():
                stale = _evaluate_ops(root)

        self.assertEqual(stale["status"], "fail")
        self.assertTrue(any("hash" in error for error in stale["errors"]))

    def test_malformed_tool_reports_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            erc = root / "erc.json"
            drc = root / "drc.json"
            review = root / "review.json"
            erc.write_text(json.dumps({"sheets": []}), encoding="utf-8")
            drc.write_text(json.dumps({"violations": [], "unconnected_items": []}), encoding="utf-8")
            review.write_text(json.dumps({}), encoding="utf-8")

            manifest = evaluate_evidence(root, erc, drc, review)

        self.assertEqual(manifest["status"], "fail")
        self.assertTrue(all(gate["status"] == "fail" for gate in manifest["gates"]))
        self.assertTrue(any("invalid schema metadata" in error for error in manifest["gates"][0]["errors"]))
        self.assertEqual(
            {gate["name"] for gate in manifest["gates"]},
            {"erc", "drc", "bom", "delivery", "intent", "ops", "schematic_semantics", "learning", "requirements_contract", "board_review", "datasheet_contract"},
        )
        # The 10th gate must also fail closed on an empty sandbox (missing
        # contract file counts as unreadable evidence, never as a skip).
        rc_gate = next(g for g in manifest["gates"] if g["name"] == "requirements_contract")
        self.assertEqual(rc_gate["status"], "fail")
        self.assertTrue(any("unreadable" in error or "missing" in error.lower()
                            for error in rc_gate["errors"]), rc_gate["errors"])
        # The 11th gate (datasheet truth layer) fails closed without a manifest.
        ds_gate = next(g for g in manifest["gates"] if g["name"] == "datasheet_contract")
        self.assertEqual(ds_gate["status"], "fail")
        self.assertTrue(any("missing datasheet manifest" in error for error in ds_gate["errors"]), ds_gate["errors"])

    def test_output_root_alias_writes_a_manifest(self):
        # The runner must leave the repository's formal evidence files
        # untouched: manifest goes to output_root and every rewritten report
        # goes to the injectable evidence_dir (a full temp directory), so the
        # in-repo current-*.json files are byte-identical before and after.
        watched = [
            ROOT / "notes" / "m2-evidence-reset" / "generated" / name
            for name in (
                "schematic_semantics_current.json",
                "semantic_fault_injection_current.json",
                "learning_gate_current.json",
            )
        ]
        before = {path: path.read_bytes() for path in watched}
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "runs"
            evidence_dir = Path(temp_dir) / "evidence"
            with _accept_live_ops_validation():
                manifest = run(
                    ROOT, skip_kicad=True, output_root=output_root,
                    evidence_dir=evidence_dir,
                )
            self.assertEqual(manifest["status"], "fail")
            self.assertTrue((output_root / "run_manifest.json").is_file())
            self.assertTrue((evidence_dir / "learning_gate_current.json").is_file())
        after = {path: path.read_bytes() for path in watched}
        self.assertEqual(before, after)

    def test_isolated_evidence_dir_run_is_self_consistent(self):
        # Problem 4: an isolated run must be internally consistent. Before the
        # path-plumbing fix, learning compared its freshly written fault
        # report against the repo formal copy ("learning input hash mismatch:
        # fault_injection_proof"), the semantic gate read the formal netlist
        # instead of the isolated one, and the OPS gate PASSED off formal
        # evidence while the manifest recorded a missing artifact under
        # evidence_dir. A PASS gate must never reference a missing artifact.
        with tempfile.TemporaryDirectory() as temp_dir:
            output_root = Path(temp_dir) / "runs"
            evidence_dir = Path(temp_dir) / "evidence"
            with _accept_live_ops_validation():
                manifest = run(
                    ROOT, skip_kicad=True, output_root=output_root,
                    evidence_dir=evidence_dir,
                )
            artifacts = manifest["artifacts"]
            gate_by_name = {g["name"]: g for g in manifest["gates"]}
            # No gate may PASS while its artifact is missing under the
            # isolated evidence_dir.
            gate_artifacts = {
                "ops": "ops_evidence",
                "schematic_semantics": "semantic_report",
                "learning": "learning_report",
                "erc": "erc_report",
                "drc": "drc_report",
            }
            for gate_name, artifact_name in gate_artifacts.items():
                gate = gate_by_name.get(gate_name)
                if gate is None or gate["status"] != "pass":
                    continue
                record = artifacts.get(artifact_name)
                self.assertIsNotNone(record, f"{gate_name} gate has no {artifact_name} artifact")
                self.assertTrue(
                    record["exists"],
                    f"{gate_name} PASS but {artifact_name} missing: {record}",
                )
            # The isolated learning report must validate against the isolated
            # fault report, not the repo formal one.
            learning_report = json.loads(
                (evidence_dir / "learning_gate_current.json").read_text(encoding="utf-8-sig"))
            self.assertEqual(learning_report["status"], "pass", learning_report["errors"])
            fault_path = Path(learning_report["inputs"]["fault_injection_proof"]["path"])
            # Compare at the same resolution level: TEMP may sit behind a
            # junction, so one side resolved and the other not would false-fail.
            self.assertTrue(
                str(fault_path.resolve()).startswith(str(Path(evidence_dir).resolve())),
                f"learning input must point inside isolated dir: {fault_path}",
            )


class OpsIndependenceTests(unittest.TestCase):
    """P1-1: OPS PASS must come from the independent verifier (akcli 0.21.0 /
    tools/generate_m2_ops.py), never from the runner self-deriving valid=true
    from ops_gen.json. The runner may only reproduce a copy of the formal
    evidence in an isolated run; it must not author evidence itself."""

    OPS_SCHEMA = "https://aedl.local/schemas/m2-ops-validation.v1.json"

    @staticmethod
    def _write_ops_gen(root, ops):
        path = root / "src" / "hardware" / "m2-board" / "ops_gen.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(ops) + "\n").encode("utf-8")
        path.write_bytes(encoded)
        return encoded

    def _write_evidence(self, root, ops_encoded, generator, validator, *,
                        op_count=1, valid=True, errors=None,
                        target="src/hardware/m2-board/ops_gen.json"):
        path = root / "notes" / "m2-evidence-reset" / "generated" / "ops_validate_current.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "$schema": self.OPS_SCHEMA,
            "schema_version": 1,
            "generated_at": "2026-08-30T00:00:00Z",
            "target": target,
            "ops_sha256": hashlib.sha256(ops_encoded).hexdigest(),
            "op_count": op_count,
            "valid": valid,
            "errors": [] if errors is None else errors,
            "generator": generator,
            "validator": validator,
        }
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    @staticmethod
    def _ops_gen():
        return {"protocol_version": 2, "target_format": "kicad", "ops": [{"op": "place_component"}]}

    def test_ops_fails_with_legal_ops_gen_but_no_independent_evidence(self):
        # 1: a legal ops_gen.json alone must never yield an OPS PASS.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self._write_ops_gen(root, self._ops_gen())
            gate = _evaluate_ops(root)
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(any("missing" in e.lower() for e in gate["errors"]), gate["errors"])

    def test_runner_does_not_author_ops_evidence_in_isolated_run(self):
        # 2: the runner must not fabricate a valid=true evidence of its own.
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir) / "evidence"
            output_root = Path(temp_dir) / "runs"
            with _accept_live_ops_validation():
                run(
                    ROOT, skip_kicad=True, output_root=output_root,
                    evidence_dir=evidence_dir,
                )
            copied = evidence_dir / "ops_validate_current.json"
            if copied.is_file():
                content = copied.read_text(encoding="utf-8")
                self.assertNotIn("gates/run_gates.py", content,
                                 "runner-authored evidence must not be produced")
                self.assertIn("akcli", content,
                              "copied evidence must retain independent provenance")

    def test_independent_akcli_evidence_passes(self):
        # 3: independent akcli evidence consistent with ops hash/count -> PASS.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            encoded = self._write_ops_gen(root, self._ops_gen())
            self._write_evidence(
                root, encoded, EXPECTED_OPS_GENERATOR, EXPECTED_OPS_VALIDATOR
            )
            with _accept_live_ops_validation():
                gate = _evaluate_ops(root)
        self.assertEqual(gate["status"], "pass", gate["errors"])

    def test_runner_authored_evidence_is_rejected(self):
        # 4a: source constraint - runner-authored provenance must FAIL.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            encoded = self._write_ops_gen(root, self._ops_gen())
            self._write_evidence(root, encoded,
                                 "gates/run_gates.py run() derived from ops_gen.json",
                                 "gates/run_gates.py _evaluate_ops structural checks")
            with _accept_live_ops_validation():
                gate = _evaluate_ops(root)
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(any("locked" in e for e in gate["errors"]), gate["errors"])

    def test_evidence_without_akcli_provenance_is_rejected(self):
        # 4b: source constraint - provenance not referencing akcli must FAIL.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            encoded = self._write_ops_gen(root, self._ops_gen())
            self._write_evidence(root, encoded, "some-other-tool", "some-other-validator")
            with _accept_live_ops_validation():
                gate = _evaluate_ops(root)
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(any("locked" in e for e in gate["errors"]), gate["errors"])

    def test_spoofed_akcli_text_cannot_pass_when_live_validator_fails(self):
        # Free-text generator/validator fields are untrusted evidence. Merely
        # inserting the word "akcli" must not substitute for executing akcli.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            encoded = self._write_ops_gen(root, self._ops_gen())
            self._write_evidence(
                root,
                encoded,
                "handwritten fake containing word akcli",
                "not executed; fake akcli claim",
            )
            failed_run = mock.Mock(returncode=1, stdout=b"", stderr=b"validator unavailable")
            with mock.patch("gates.run_gates.subprocess.run", return_value=failed_run):
                gate = _evaluate_ops(root)

        self.assertEqual(gate["status"], "fail", gate)
        self.assertTrue(
            any("live" in error.lower() or "validator" in error.lower()
                for error in gate["errors"]),
            gate["errors"],
        )

    def test_locked_evidence_cannot_pass_when_live_validator_fails(self):
        # Even byte-for-byte canonical provenance strings are only claims in
        # JSON. A failed external process must override those claims.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            encoded = self._write_ops_gen(root, self._ops_gen())
            self._write_evidence(
                root, encoded, EXPECTED_OPS_GENERATOR, EXPECTED_OPS_VALIDATOR
            )
            failed_run = mock.Mock(returncode=1, stdout=b"", stderr=b"validator unavailable")
            with mock.patch("gates.run_gates.subprocess.run", return_value=failed_run):
                gate = _evaluate_ops(root)

        self.assertEqual(gate["status"], "fail", gate)
        self.assertTrue(any("live akcli" in error for error in gate["errors"]), gate["errors"])

    def test_live_akcli_result_is_bound_to_current_hash_and_count(self):
        # Exercise the subprocess boundary itself, not the unit-test shortcut.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ops_path = root / "ops.json"
            ops_path.write_text("{}", encoding="utf-8")
            expected_hash = "a" * 64
            version_run = {
                "command": ["akcli", "--version"],
                "exit_code": 0,
                "stdout": EXPECTED_AKCLI_VERSION,
                "stderr": "",
            }
            valid_run = {
                "command": ["akcli", "ops", "validate"],
                "exit_code": 0,
                "stdout": json.dumps({
                    "protocol_version": 2,
                    "valid": True,
                    "ops_sha256": expected_hash,
                    "op_count": 3,
                    "errors": [],
                }),
                "stderr": "",
            }
            with mock.patch("gates.run_gates._find_akcli", return_value=Path("akcli")), \
                    mock.patch("gates.run_gates._run_tool", side_effect=[version_run, valid_run]):
                details, errors = _validate_ops_with_live_akcli(
                    root, ops_path, expected_hash, 3
                )
            self.assertEqual(errors, [])
            self.assertTrue(details["result"]["valid"])

            valid_run["stdout"] = json.dumps({
                "protocol_version": 2,
                "valid": True,
                "ops_sha256": "b" * 64,
                "op_count": 3,
                "errors": [],
            })
            with mock.patch("gates.run_gates._find_akcli", return_value=Path("akcli")), \
                    mock.patch("gates.run_gates._run_tool", side_effect=[version_run, valid_run]):
                _, errors = _validate_ops_with_live_akcli(
                    root, ops_path, expected_hash, 3
                )
            self.assertTrue(any("hash" in error for error in errors), errors)

    def test_evidence_with_invalid_flag_or_errors_fails(self):
        # 4c/4d: valid=False or non-empty errors must FAIL even with akcli provenance.
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            encoded = self._write_ops_gen(root, self._ops_gen())
            self._write_evidence(
                root, encoded, EXPECTED_OPS_GENERATOR, EXPECTED_OPS_VALIDATOR,
                valid=False,
            )
            with _accept_live_ops_validation():
                self.assertEqual(_evaluate_ops(root)["status"], "fail")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            encoded = self._write_ops_gen(root, self._ops_gen())
            self._write_evidence(
                root, encoded, EXPECTED_OPS_GENERATOR, EXPECTED_OPS_VALIDATOR,
                errors=["bad op"],
            )
            with _accept_live_ops_validation():
                self.assertEqual(_evaluate_ops(root)["status"], "fail")

    def test_isolated_pass_ops_artifact_exists_with_independent_provenance(self):
        # 5: when ops gate passes in an isolated run, its artifact must exist
        #    and still carry independent provenance.
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence_dir = Path(temp_dir) / "evidence"
            output_root = Path(temp_dir) / "runs"
            with _accept_live_ops_validation():
                manifest = run(
                    ROOT, skip_kicad=True, output_root=output_root,
                    evidence_dir=evidence_dir,
                )
            gate = next(g for g in manifest["gates"] if g["name"] == "ops")
            artifact = manifest["artifacts"].get("ops_evidence")
            if gate["status"] == "pass":
                self.assertIsNotNone(artifact)
                self.assertTrue(artifact["exists"], artifact)
                content = Path(artifact["path"]).read_text(encoding="utf-8")
                self.assertIn("akcli", content)
                self.assertNotIn("gates/run_gates.py", content)

    def test_isolated_run_does_not_overwrite_formal_ops_evidence(self):
        # 6: an isolated run must not touch the repo's formal ops evidence.
        formal = ROOT / "notes" / "m2-evidence-reset" / "generated" / "ops_validate_current.json"
        before = formal.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            with _accept_live_ops_validation():
                run(
                    ROOT, skip_kicad=True,
                    output_root=Path(temp_dir) / "runs",
                    evidence_dir=Path(temp_dir) / "evidence",
                )
        self.assertEqual(formal.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
