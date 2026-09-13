"""Synthetic contract tests only. No production case answers or private reads."""

import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import y4_dry_runner as y4


def public_input(number=1):
    inputs = {
        "experiment_version": y4.EXPERIMENT_VERSION,
        "case_public_id": "Y4-%03d" % number,
        "context_id": "synthetic-%d" % number,
        "target": "design/example.kicad_sch",
        "source_utf8": "(synthetic_source %d)\r\n" % number,
        "current_observation": {"objects": [{"kind": "label", "name": "TEST"}]},
        "public_facts": [{"id": "F1", "text": "Synthetic fact.", "status": "UNKNOWN"}],
        "budget": {"max_ops": 8, "max_request_bytes": 65536,
                   "max_output_tokens": 4096, "timeout_ms": 180000},
        "placement_grants": [{"x_mil": 100, "y_mil": 200},
                             {"x_mil": 200, "y_mil": 200}],
    }
    bind_observation(inputs)
    return inputs


def bind_observation(inputs):
    """Synthetic producer declaration, independent of the runtime validator."""
    observation = json.dumps(inputs["current_observation"], sort_keys=True,
                             separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    inputs["observation_binding"] = {
        "source_sha256": hashlib.sha256(inputs["source_utf8"].encode("utf-8")).hexdigest(),
        "observation_sha256": hashlib.sha256(observation).hexdigest(),
        "producer_id": "synthetic-reader-v1",
    }


def metadata(arm="C"):
    return {
        "run_id": "synthetic-run", "arm": arm, "repetition": 1, "attempt": 1,
        "model_or_script_id": "synthetic-test-adapter", "settings": {},
        "exposure": {"session_id": "synthetic-session", "fresh_session": True,
                     "input_scope": "PUBLIC_PACKAGE_ONLY", "prior_case_exposure": "UNKNOWN",
                     "author_exposure": "YES", "declaration": "Synthetic testing only."},
    }


def refusal(package):
    context = json.loads(package)["public_context"]
    return {"schema_version": 1,
            **{key: context[key] for key in ("context_id", "target", "base_source_sha256")},
            "decision": "REFUSE", "diagnosis": [],
            "refusal": {"reason_code": "INSUFFICIENT_FACTS", "missing_fact_ids": ["F1"],
                        "explanation": "Synthetic refusal.", "required_human_decision": "Review fact."}}


class PublicPackageTests(unittest.TestCase):
    def test_canonical_protocol_identity_is_pinned(self):
        self.assertEqual(y4.EXPERIMENT_VERSION, "y4-dry-5case-20260910-v1")
        self.assertEqual(y4.RUNNER_VERSION, "y4-dry.v5")
        self.assertEqual(y4.CASE_IDS,
                         ("Y4-001", "Y4-002", "Y4-003", "Y4-004", "Y4-005"))
        self.assertEqual(y4.REPETITIONS, 3)
        self.assertEqual(y4.ATTEMPTS_PER_SLOT, 1)

    def test_canonical_slot_arithmetic_is_thirty_with_one_attempt(self):
        # Five scored cases x two arms x three repetitions x one attempt = 30.
        self.assertEqual(len(y4.CASE_IDS), 5)
        self.assertEqual(len(y4.CASE_IDS) * 2 * y4.REPETITIONS
                         * y4.ATTEMPTS_PER_SLOT, 30)
        # The retired six-case structure would be 36 slots; it is not canonical.
        self.assertNotEqual(6 * 2 * 3, 30)

    def test_dry_runner_has_no_apply_after_observation_or_c2_capability(self):
        source = Path(y4.__file__).read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertFalse(imported & {"subprocess", "socket", "urllib", "http",
                                     "requests", "shutil", "ctypes"})
        for token in ("apply_proposal", "execute_repair", "os.system", "os.popen",
                      "Popen", "compare_delta", "compare_protected",
                      "AfterObservation", "after_observation"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_rebuild_is_deterministic_and_preserves_source_bytes(self):
        inputs = public_input()
        raw = y4.build_package(inputs)
        self.assertEqual(raw, y4.build_package(copy.deepcopy(inputs)))
        doc = y4.load_package(raw, y4.hash_bytes(raw))
        self.assertEqual(doc["public_context"]["base_source_sha256"],
                         y4.hash_bytes(inputs["source_utf8"].encode()))
        inputs["source_utf8"] = inputs["source_utf8"].replace("\r\n", "\n")
        bind_observation(inputs)
        self.assertNotEqual(raw, y4.build_package(inputs))

    def test_source_observation_binding_rejects_cross_case_or_changed_source(self):
        inputs = public_input()
        raw = y4.build_package(inputs)
        doc = y4.load_package(raw, y4.hash_bytes(raw))
        self.assertEqual(doc["observation_binding"], inputs["observation_binding"])
        self.assertEqual(doc["schema_version"], "y4-public.v3")
        for source in (public_input(2)["source_utf8"], inputs["source_utf8"].replace("\r\n", "\n")):
            changed = copy.deepcopy(inputs)
            changed["source_utf8"] = source
            with self.assertRaisesRegex(y4.Y4Error, "observation source hash mismatch"):
                y4.build_package(changed)

    def test_observation_binding_detects_stale_payload_and_rehashed_package(self):
        inputs = public_input()
        raw = y4.build_package(inputs)
        y4.load_package(raw, y4.hash_bytes(raw))
        changed = copy.deepcopy(inputs)
        changed["current_observation"]["objects"][0]["name"] = "CHANGED"
        with self.assertRaisesRegex(y4.Y4Error, "observation content hash mismatch"):
            y4.build_package(changed)
        doc = json.loads(raw)
        doc["public_context"]["current_observation"] = changed["current_observation"]
        doc["public_context_sha256"] = y4.public_context_digest(doc["public_context"])
        tampered = y4.canonical_json_bytes(doc)
        with self.assertRaisesRegex(y4.Y4Error, "observation content hash mismatch"):
            y4.load_package(tampered, y4.hash_bytes(tampered))

    def test_placement_grants_are_required_and_closed(self):
        mutations = [
            lambda i: i.pop("placement_grants"),
            lambda i: i.__setitem__("placement_grants", []),
            lambda i: i.__setitem__("placement_grants", [{"x_mil": 1, "y_mil": 2},
                                                         {"x_mil": 1, "y_mil": 2}]),
            lambda i: i.__setitem__("placement_grants", [{"x_mil": True, "y_mil": 2}]),
            lambda i: i.__setitem__("placement_grants", [{"x_mil": 1, "y_mil": 2, "z": 3}]),
        ]
        for index, change in enumerate(mutations):
            with self.subTest(index=index):
                inputs = public_input()
                change(inputs)
                with self.assertRaises(y4.Y4Error):
                    y4.build_package(inputs)

    def test_uses_c1_whitelist_projection(self):
        with patch.object(y4, "make_public_context", wraps=y4.make_public_context) as projection:
            doc = json.loads(y4.build_package(public_input()))
        projection.assert_called_once()
        self.assertEqual(set(doc["public_context"]), set(y4.PUBLIC_CONTEXT_FIELDS))

    def test_rejects_host_only_and_unknown_input_fields(self):
        for key in ("host_context", "rules", "expected_after", "authorized_delta", "score"):
            with self.subTest(key=key):
                inputs = public_input()
                inputs[key] = {}
                with self.assertRaises(y4.Y4Error):
                    y4.build_package(inputs)

    def test_nested_denied_fields_and_tokens_are_rejected(self):
        for key in sorted(y4.DENIED):
            with self.subTest(key=key):
                inputs = public_input()
                inputs["current_observation"][key] = "test"
                with self.assertRaises(ValueError):
                    y4.build_package(inputs)
        for text in ("EXPECTED_AFTER", "tests\\fixtures\\repair_pr1\\private\\x", "repair_ops.json"):
            inputs = public_input()
            inputs["public_facts"][0]["text"] = text
            with self.assertRaises(y4.Y4Error):
                y4.build_package(inputs)

    def test_every_single_byte_mutation_fails_pinned_hash(self):
        raw = y4.build_package(public_input())
        digest = y4.hash_bytes(raw)
        for index in range(len(raw)):
            corrupted = raw[:index] + bytes([raw[index] ^ 1]) + raw[index + 1:]
            with self.assertRaises(y4.Y4Error):
                y4.load_package(corrupted, digest)

    def test_rehashed_forged_derived_fields_fail_validation(self):
        original = json.loads(y4.build_package(public_input()))
        for field, value in (("instruction", "changed"), ("schema_version", "v2"),
                             ("public_context_sha256", "0" * 64), ("exposure_fields", [])):
            doc = copy.deepcopy(original)
            doc[field] = value
            raw = y4.canonical_json_bytes(doc)
            with self.assertRaises(y4.Y4Error):
                y4.load_package(raw, y4.hash_bytes(raw))
        original["public_context"]["generic_op_schema"] = {}
        raw = y4.canonical_json_bytes(original)
        with self.assertRaises(y4.Y4Error):
            y4.load_package(raw, y4.hash_bytes(raw))

    def test_invalid_budgets_are_rejected(self):
        for key, value in (("max_ops", 9), ("max_ops", True), ("timeout_ms", 0),
                           ("max_request_bytes", 65537), ("max_output_tokens", -1)):
            inputs = public_input()
            inputs["budget"][key] = value
            with self.assertRaises(y4.Y4Error):
                y4.build_package(inputs)

    def test_five_case_freeze_is_order_independent(self):
        cases = [public_input(n) for n in range(1, 6)]
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "one", Path(tmp) / "two"
            manifest = y4.freeze_cases(cases, first)
            y4.freeze_cases(list(reversed(cases)), second)
            self.assertEqual(len(manifest["cases"]), 5)
            self.assertEqual(manifest["experiment_version"], y4.EXPERIMENT_VERSION)
            for file in first.iterdir():
                self.assertEqual(file.read_bytes(), (second / file.name).read_bytes())
            with self.assertRaises(FileExistsError):
                y4.freeze_cases(cases, first)

    def test_incomplete_duplicate_or_mixed_batch_writes_nothing(self):
        cases = [public_input(n) for n in range(1, 6)]
        invalid = [cases[:4], [public_input(n) for n in range(1, 7)],
                   [cases[0]] * 5]
        changed = copy.deepcopy(cases)
        changed[-1]["experiment_version"] = "different"
        invalid.append(changed)
        changed = copy.deepcopy(cases)
        changed[-1]["budget"]["max_ops"] = 1
        invalid.append(changed)
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "batch"
            for inputs in invalid:
                with self.assertRaises(y4.Y4Error):
                    y4.freeze_cases(inputs, destination)
                self.assertFalse(destination.exists())

    def test_wrong_experiment_or_protocol_version_is_rejected(self):
        for version in ("y4-dry-20260910-review1", "synthetic-test-v1",
                        "y4-dry-5case-20260910-v2", "y4-dry-v2"):
            with self.subTest(version=version):
                inputs = public_input()
                inputs["experiment_version"] = version
                with self.assertRaisesRegex(y4.Y4Error, "wrong experiment/protocol version"):
                    y4.build_package(inputs)

    def test_retired_six_case_identities_are_never_accepted(self):
        inputs = public_input()
        inputs["case_public_id"] = "Y4-006"
        with self.assertRaisesRegex(y4.Y4Error, "case_public_id"):
            y4.build_package(inputs)
        self.assertEqual(len(y4.CASE_IDS), 5)
        source = Path(y4.__file__).read_text(encoding="utf-8")
        for invalidated in ("c854aa4cc6d3ffc40cfc84ac225b7b2609818b924662595e236e3c76e8ad5489",
                            "d31f26ea0a6580b5d1ad8f72c0d1b6ad809322ff5c937dfd228ded2d6c098a7f",
                            "658142fb427618b64fee72c7d273b50319e2721a9a8e1f284471d11e6b12055b",
                            "a3c95954bf83f44fab434a437295b10091d19bab685b2b39c6a4991d73e7741e"):
            self.assertNotIn(invalidated, source)

    def test_invalidated_six_case_hash_is_not_a_trusted_pin(self):
        package = y4.build_package(public_input())
        with self.assertRaisesRegex(y4.Y4Error, "public package byte hash mismatch"):
            y4.load_package(package, "d31f26ea0a6580b5d1ad8f72c0d1b6ad809322ff5c937dfd228ded2d6c098a7f")


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.package = y4.build_package(public_input())
        self.digest = y4.hash_bytes(self.package)
        self.output = y4.canonical_json_bytes(refusal(self.package))

    def collect(self, output=None, meta=None, elapsed=10):
        raw = y4.collect_result(self.package, self.digest,
                                self.output if output is None else output,
                                meta or metadata(), elapsed)
        return y4.load_result(raw, self.package, self.digest)

    def test_c_and_d_accept_same_c1_proposal_without_scoring(self):
        for arm in ("C", "D"):
            result = self.collect(meta=metadata(arm))
            self.assertEqual(result["record_status"], "RECORDED")
            self.assertEqual(result["proposal_parse_status"], "PASS")
            self.assertEqual(result["binding_status"], "PASS")
            self.assertEqual(result["scoring"], "NOT_RUN")

    def test_exact_raw_bytes_and_normalized_proposal_both_preserved(self):
        raw = json.dumps(refusal(self.package), indent=2).encode() + b"\n"
        result = self.collect(raw)
        self.assertEqual(base64.b64decode(result["raw_output_base64"]), raw)
        self.assertEqual(result["raw_output_sha256"], y4.hash_bytes(raw))
        self.assertEqual(result["proposal"], refusal(self.package))

    def test_patch_defaults_are_normalized_by_c1_without_changing_raw(self):
        proposal = refusal(self.package)
        del proposal["refusal"]
        proposal["decision"] = "PATCH"
        proposal["oplist"] = {"protocol_version": 2, "target_format": "kicad", "ops": [
            {"op": "place_component", "lib_id": "Device:R", "designator": "R_TEST",
             "x_mil": 100, "y_mil": 200, "value": "test", "footprint": "test"}]}
        raw = y4.canonical_json_bytes(proposal)
        result = self.collect(raw)
        self.assertEqual(result["record_status"], "RECORDED")
        self.assertEqual(result["proposal"]["oplist"]["ops"][0]["rotation"], 0)
        self.assertEqual(base64.b64decode(result["raw_output_base64"]), raw)
        self.assertEqual(result["token_budget_status"], "NOT_VERIFIED")

    def test_operation_budget_edge_is_exactly_eight(self):
        from tools.repair_pipeline import MAX_OPS
        self.assertEqual(MAX_OPS, 8)
        self.assertEqual(self.package and json.loads(self.package)["budget"]["max_ops"], 8)

        def patch_with(count):
            proposal = refusal(self.package)
            del proposal["refusal"]
            proposal["decision"] = "PATCH"
            proposal["oplist"] = {"protocol_version": 2, "target_format": "kicad", "ops": [
                {"op": "add_net_label", "name": "N%d" % i, "at": "R1.%d" % i}
                for i in range(1, count + 1)]}
            return y4.canonical_json_bytes(proposal)

        eight = self.collect(patch_with(8))
        self.assertEqual(eight["proposal_parse_status"], "PASS")
        self.assertEqual(eight["budget_status"], "PASS")
        self.assertEqual(eight["record_status"], "RECORDED")

        nine = self.collect(patch_with(9))
        self.assertEqual(nine["proposal_parse_status"], "FAIL")
        self.assertEqual(nine["record_status"], "REJECTED")
        self.assertEqual(base64.b64decode(nine["raw_output_base64"]), patch_with(9))

    def test_place_component_must_use_a_granted_slot(self):
        proposal = refusal(self.package)
        del proposal["refusal"]
        proposal["decision"] = "PATCH"
        proposal["oplist"] = {"protocol_version": 2, "target_format": "kicad", "ops": [
            {"op": "place_component", "lib_id": "Device:R", "designator": "R_TEST",
             "x_mil": 9999, "y_mil": 9999, "value": "test", "footprint": "test"}]}
        result = self.collect(y4.canonical_json_bytes(proposal))
        self.assertEqual(result["proposal_parse_status"], "PASS")
        self.assertEqual(result["binding_status"], "FAIL")
        self.assertEqual(result["record_status"], "REJECTED")
        proposal["oplist"]["ops"][0]["x_mil"] = 100
        proposal["oplist"]["ops"][0]["y_mil"] = 200
        result = self.collect(y4.canonical_json_bytes(proposal))
        self.assertEqual(result["binding_status"], "PASS")
        self.assertEqual(result["record_status"], "RECORDED")

    def test_package_operation_budget_is_stricter_than_c1_limit(self):
        inputs = public_input()
        inputs["budget"]["max_ops"] = 1
        self.package = y4.build_package(inputs)
        self.digest = y4.hash_bytes(self.package)
        proposal = refusal(self.package)
        del proposal["refusal"]
        proposal["decision"] = "PATCH"
        proposal["oplist"] = {"protocol_version": 2, "target_format": "kicad", "ops": [
            {"op": "add_net_label", "name": "TEST", "at": "R1.1", "scope": "local", "rotation": 0},
            {"op": "add_net_label", "name": "TEST", "at": "R2.1", "scope": "local", "rotation": 0}]}
        result = self.collect(y4.canonical_json_bytes(proposal))
        self.assertEqual(result["proposal_parse_status"], "PASS")
        self.assertEqual(result["record_status"], "REJECTED")
        self.assertEqual(result["budget_status"], "FAIL")

    def test_rehashed_nested_host_field_still_rejected(self):
        doc = json.loads(self.package)
        doc["public_context"]["current_observation"]["authorized_delta"] = {}
        raw = y4.canonical_json_bytes(doc)
        with self.assertRaises(y4.Y4Error):
            y4.load_package(raw, y4.hash_bytes(raw))

    def test_tuple_nested_denied_field_is_rejected_at_build(self):
        inputs = public_input()
        inputs["current_observation"] = {"objects": ({"a_score": 1},)}
        inputs["observation_binding"]["observation_sha256"] = y4.hash_bytes(
            y4.canonical_json_bytes(inputs["current_observation"]))
        with self.assertRaises(y4.Y4Error):
            y4.build_package(inputs)

    def test_non_json_public_value_is_rejected_at_build(self):
        inputs = public_input()
        inputs["current_observation"] = {"objects": [{"labels": {"x", "y"}}]}
        inputs["observation_binding"]["observation_sha256"] = "0" * 64
        with self.assertRaises(y4.Y4Error):
            y4.build_package(inputs)

    def test_duplicate_result_json_keys_are_rejected(self):
        raw = y4.collect_result(self.package, self.digest, self.output, metadata(), 10)
        raw = b'{"scoring":"NOT_RUN",' + raw[1:]
        with self.assertRaises(y4.Y4Error):
            y4.load_result(raw, self.package, self.digest)

    def test_malformed_output_is_never_repaired(self):
        invalid = [b"{", b"\xff", b"```json\n" + self.output + b"\n```", b"{}",
                   b'{"schema_version":1,"schema_version":1}', b"[]", b" " * 65537]
        for output in invalid:
            with self.subTest(output=output[:12]):
                result = self.collect(output)
                self.assertEqual(result["proposal_parse_status"], "FAIL")
                self.assertIsNone(result["proposal"])
                self.assertEqual(result["record_status"], "REJECTED")
                self.assertEqual(base64.b64decode(result["raw_output_base64"]), output)

    def test_unknown_proposal_field_reaches_c1_and_fails(self):
        proposal = refusal(self.package)
        proposal["accepted"] = True
        with patch.object(y4, "parse_proposal", wraps=y4.parse_proposal) as parse:
            result = self.collect(y4.canonical_json_bytes(proposal))
        self.assertGreaterEqual(parse.call_count, 1)
        self.assertEqual(result["proposal_parse_status"], "FAIL")

    def test_wrong_context_target_and_source_are_rejected(self):
        for key, value in (("context_id", "wrong"), ("target", "design/wrong.kicad_sch"),
                           ("base_source_sha256", "0" * 64)):
            proposal = refusal(self.package)
            proposal[key] = value
            result = self.collect(y4.canonical_json_bytes(proposal))
            self.assertEqual(result["proposal_parse_status"], "PASS")
            self.assertEqual(result["binding_status"], "FAIL")
            self.assertEqual(result["record_status"], "REJECTED")

    def test_result_cannot_be_rebound_to_another_case(self):
        raw = y4.collect_result(self.package, self.digest, self.output, metadata(), 10)
        other = y4.build_package(public_input(2))
        with self.assertRaises(y4.Y4Error):
            y4.load_result(raw, other, y4.hash_bytes(other))

    def test_derived_result_tampering_or_scores_are_rejected(self):
        original = self.collect()
        for key, value in (("a_score", 1), ("b_score", 1), ("scoring", "PASS"),
                           ("raw_output_sha256", "0" * 64), ("runtime_ms", True),
                           ("proposal", {}), ("proposal_parse_status", "FAIL")):
            result = copy.deepcopy(original)
            result[key] = value
            with self.assertRaises(y4.Y4Error):
                y4.load_result(y4.canonical_json_bytes(result), self.package, self.digest)

    def test_exceeded_runtime_is_recorded_as_rejected(self):
        result = self.collect(elapsed=180001)
        self.assertEqual(result["budget_status"], "FAIL")
        self.assertEqual(result["record_status"], "REJECTED")
        self.assertEqual(result["proposal_parse_status"], "PASS")

    def test_metadata_cannot_add_score_or_omit_exposure(self):
        meta = metadata()
        meta["a_score"] = 1
        with self.assertRaises(y4.Y4Error):
            self.collect(meta=meta)
        meta = metadata()
        del meta["exposure"]["author_exposure"]
        with self.assertRaises(y4.Y4Error):
            self.collect(meta=meta)

    def test_attempt_must_be_exactly_one_but_repetitions_remain_three(self):
        for attempt in (2, 3):
            with self.subTest(attempt=attempt):
                meta = metadata()
                meta["attempt"] = attempt
                with self.assertRaisesRegex(y4.Y4Error, "attempts_per_slot=1"):
                    self.collect(meta=meta)
        for repetition in (2, 3):
            with self.subTest(repetition=repetition):
                meta = metadata()
                meta["repetition"] = repetition
                result = self.collect(meta=meta)
                self.assertEqual(result["metadata"]["repetition"], repetition)

    def test_retry_cannot_create_a_second_formal_slot(self):
        def failing_adapter(request):
            raise RuntimeError("simulated provider failure")

        first_raw = y4.run_adapter(self.package, self.digest, metadata(),
                                   failing_adapter)
        first = y4.load_result(first_raw, self.package, self.digest)
        self.assertEqual(first["invocation_error"], "ADAPTER_ERROR")
        self.assertEqual(first["record_status"], "REJECTED")
        retry_meta = metadata()
        retry_meta["attempt"] = 2
        with self.assertRaisesRegex(y4.Y4Error, "attempts_per_slot=1"):
            y4.collect_result(self.package, self.digest, self.output,
                              retry_meta, 10)
        tampered = json.loads(first_raw)
        tampered["metadata"]["attempt"] = 2
        with self.assertRaises(y4.Y4Error):
            y4.load_result(y4.canonical_json_bytes(tampered), self.package,
                           self.digest)

    def test_run_metadata_domain_is_closed(self):
        mutations = [
            ("arm", "E"), ("repetition", 0), ("repetition", 4),
            ("repetition", True), ("attempt", 0), ("attempt", 4),
            ("attempt", True), ("run_id", ""), ("run_id", "bad id!"),
            ("model_or_script_id", "  "), ("model_or_script_id", 7),
            ("settings", []),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                meta = metadata()
                meta[field] = value
                with self.assertRaises(y4.Y4Error):
                    self.collect(meta=meta)
        exposure_mutations = [
            ("session_id", ""), ("fresh_session", "yes"),
            ("input_scope", "HOST_POLICY"), ("prior_case_exposure", "MAYBE"),
            ("author_exposure", 1), ("declaration", ""),
        ]
        for field, value in exposure_mutations:
            with self.subTest(exposure=field, value=value):
                meta = metadata()
                meta["exposure"][field] = value
                with self.assertRaises(y4.Y4Error):
                    self.collect(meta=meta)

    def test_recorded_is_integrity_state_not_repair_success(self):
        result = self.collect()
        self.assertEqual(result["record_status"], "RECORDED")
        self.assertEqual(result["proposal_parse_status"], "PASS")
        self.assertEqual(result["binding_status"], "PASS")
        self.assertEqual(result["scoring"], "NOT_RUN")
        self.assertEqual(result["token_budget_status"], "NOT_VERIFIED")
        self.assertEqual(set(result), {
            "schema_version", "runner_version", "experiment_version",
            "case_public_id", "metadata", "public_input_sha256",
            "public_context_sha256", "raw_output_base64", "raw_output_sha256",
            "proposal", "proposal_sha256", "proposal_parse_status", "parse_error",
            "binding_status", "budget_status", "runtime_ms", "invocation_error",
            "token_budget_status", "record_status", "scoring",
        })
        for claim in ("repair_success", "applied", "after_observation", "erc",
                      "accepted", "a_score", "b_score", "success"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, result)

    def test_results_are_exclusively_created_and_not_overwritten(self):
        raw = y4.collect_result(self.package, self.digest, self.output, metadata(), 10)
        with tempfile.TemporaryDirectory() as tmp:
            saved = y4.save_result(tmp, raw, self.package, self.digest)
            with self.assertRaises(FileExistsError):
                y4.save_result(tmp, raw, self.package, self.digest)
            self.assertEqual(saved.read_bytes(), raw)

    def test_adapter_receives_identical_c_d_payload_and_no_retry(self):
        calls = []
        def adapter(request):
            calls.append(request)
            return b"not valid JSON"
        for arm in ("C", "D"):
            raw = y4.run_adapter(self.package, self.digest, metadata(arm), adapter)
            self.assertEqual(y4.load_result(raw, self.package, self.digest)["record_status"], "REJECTED")
        self.assertEqual(calls, [self.package, self.package])

    def test_adapter_exception_is_failed_invocation_not_refusal(self):
        def adapter(request):
            raise RuntimeError("synthetic provider failure")
        raw = y4.run_adapter(self.package, self.digest, metadata(), adapter)
        result = y4.load_result(raw, self.package, self.digest)
        self.assertEqual(result["invocation_error"], "ADAPTER_ERROR")
        self.assertEqual(result["proposal_parse_status"], "NOT_RUN")
        self.assertIsNone(result["proposal"])

    def test_runtime_path_never_opens_policy_private_or_scorer(self):
        real_open = Path.open
        opened = []
        def checked_open(path, *args, **kwargs):
            normalized = str(path).lower().replace("\\", "/")
            self.assertFalse(any(token in normalized for token in
                                 ("/private/", "topology_policy", "repair_ops", "oracle")))
            opened.append(normalized)
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", checked_open):
            package = y4.build_package(public_input())
            raw = y4.run_adapter(package, y4.hash_bytes(package), metadata(), lambda request: self.output)
            y4.load_result(raw, package, y4.hash_bytes(package))
        self.assertTrue(opened)
        source = Path(y4.__file__).read_text(encoding="utf-8")
        self.assertNotIn("compare_delta(", source)
        self.assertNotIn("compare_protected(", source)

    def test_cli_records_verifies_and_preserves_invalid_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_bytes(self.package)
            (root / "metadata.json").write_bytes(y4.canonical_json_bytes(metadata()))
            (root / "response.bin").write_bytes(b"{broken")
            command = [sys.executable, "-m", "tools.y4_dry_runner", "record",
                       "--package", str(root / "package.json"), "--package-sha256", self.digest,
                       "--metadata", str(root / "metadata.json"), "--raw", str(root / "response.bin"),
                       "--runtime-ms", "10", "--out", str(root / "results")]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            saved = Path(json.loads(result.stdout)["path"])
            record = y4.load_result(saved.read_bytes(), self.package, self.digest)
            self.assertEqual(base64.b64decode(record["raw_output_base64"]), b"{broken")
            verify = subprocess.run([sys.executable, "-m", "tools.y4_dry_runner", "verify",
                                     "--package", str(root / "package.json"),
                                     "--package-sha256", self.digest, "--result", str(saved)],
                                    capture_output=True, text=True)
            self.assertEqual(verify.returncode, 1, verify.stderr)
            self.assertEqual(json.loads(verify.stdout)["integrity"], "PASS")


if __name__ == "__main__":
    unittest.main()
