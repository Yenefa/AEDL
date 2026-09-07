"""Tests for gates/requirements_runtime_server.py (P2 frontend's real-API mode).

Focus areas (TASK-P7, docs/OVERNIGHT_20260901.md):
- finalize() writes {intent_path, intent_semantic_sha256} exactly and its
  output passes the C1-C7 gate (P5 session AI-20260831-006 measured the older
  revision failing C4; the fix landed later in the P1 commit 1857db4 - these
  tests pin the behavior so it cannot regress silently);
- finalize() error paths fail closed (no binding, empty path, unreadable intent);
- the HTTP layer turns handler ValueErrors into 400 JSON responses instead of
  dropping the connection (the code raises ValueError("malformed JSON body")
  with the clear intent of an error response).

Fixtures are self-contained (temp dir, minimal intent), so they do not depend
on the M2 board files.
"""

from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
from datetime import datetime, timezone
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gates.requirements_contract import (
    INTENT_BINDING_FIELDS,
    compute_contract_sha256,
    intent_semantic_sha256,
    validate_requirements_contract,
)
from gates.requirements_runtime_server import RequirementsRuntime, _Handler


def _make_intent(requirements_contract_ref: dict | None = None) -> dict:
    intent = {
        "protocol_version": "v1",
        "components": {
            "U1": {"lib_id": "RF_Module:ESP32-C3-WROOM-02", "value": "ESP32-C3"},
        },
        "nets": {"/3V3": ["U1.1"]},
    }
    if requirements_contract_ref is not None:
        intent["requirements_contract"] = requirements_contract_ref
    return intent


def _make_draft(intent_path: str = "intent.json") -> dict:
    return {
        "$schema": "https://aedl.local/schemas/requirements-contract.v1.json",
        "schema_version": 1,
        "board_id": "test-board",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "author": "test",
        "user_goal": "ESP32-C3 temperature sensor carrier for gate testing",
        "source_statements": [
            {"id": "S1", "text": "MCU board with a temperature sensor", "type": "mcu"},
        ],
        "resolved_requirements": [
            {"id": "R1", "text": "onboard MCU", "source_ids": ["S1"]},
        ],
        "open_questions": [
            {
                "id": "Q1", "question": "power source?",
                "answer": "unknown", "kind": "blocking", "source_ids": ["S1"],
            },
        ],
        "assumptions": [],
        "forbidden_assumptions": [],
        "intent_binding": {"intent_path": intent_path},
    }


class _TempRepoCase(unittest.TestCase):
    """Base: temp dir acting as the server's repo root."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write_intent(self, intent: dict, name: str = "intent.json") -> Path:
        path = self.root / name
        path.write_text(json.dumps(intent), encoding="utf-8")
        return path


class FinalizeSemanticsTests(_TempRepoCase):
    def test_finalize_writes_semantic_hash_and_output_passes_gate(self):
        intent = _make_intent({"sha256": "0" * 64, "path": "requirements_contract_v1.json"})
        self.write_intent(intent)
        runtime = RequirementsRuntime()
        contract = runtime.finalize(_make_draft(), self.root)

        self.assertEqual(set(contract["intent_binding"]), set(INTENT_BINDING_FIELDS))
        self.assertEqual(
            contract["intent_binding"]["intent_semantic_sha256"],
            intent_semantic_sha256(intent),
        )
        self.assertEqual(contract["contract_sha256"], compute_contract_sha256(contract))

        contract_path = self.root / "requirements_contract_v1.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        # The intent's back-reference must name this exact contract revision.
        # Filling it AFTER finalize is legal and cycle-free precisely because
        # requirements_contract is excluded from the semantic-hash whitelist.
        intent["requirements_contract"]["sha256"] = contract["contract_sha256"]
        self.write_intent(intent)
        errors = validate_requirements_contract(contract_path, self.root / "intent.json")
        self.assertEqual(errors, [])

    def test_gate_rejects_contract_when_intent_circuit_changes_after_signing(self):
        intent = _make_intent({"sha256": "0" * 64, "path": "requirements_contract_v1.json"})
        self.write_intent(intent)
        runtime = RequirementsRuntime()
        contract = runtime.finalize(_make_draft(), self.root)
        contract_path = self.root / "requirements_contract_v1.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")

        intent["components"]["R9"] = {"lib_id": "Device:R", "value": "10k"}
        self.write_intent(intent)

        errors = validate_requirements_contract(contract_path, self.root / "intent.json")
        self.assertTrue(
            any("语义内容已变更" in e or "semantic sha256 mismatch" in e for e in errors),
            errors,
        )

    def test_gate_rejects_unanswered_blocking_question_even_after_server_finalize(self):
        # The server assembles (it never infers); the gate is the authority that
        # rejects unanswered blocking questions. This test pins that layering:
        # a smuggled null answer must never reach a passing verdict.
        intent = _make_intent({"sha256": "0" * 64, "path": "requirements_contract_v1.json"})
        self.write_intent(intent)
        draft = _make_draft()
        draft["open_questions"][0]["answer"] = None
        contract = RequirementsRuntime().finalize(draft, self.root)
        contract_path = self.root / "requirements_contract_v1.json"
        contract_path.write_text(json.dumps(contract), encoding="utf-8")
        errors = validate_requirements_contract(contract_path, self.root / "intent.json")
        self.assertTrue(
            any("unanswered" in e for e in errors), errors,
        )

    def test_finalize_rejects_non_object_binding(self):
        draft = _make_draft()
        draft["intent_binding"] = "intent.json"
        with self.assertRaises(ValueError):
            RequirementsRuntime().finalize(draft, self.root)

    def test_finalize_rejects_empty_intent_path(self):
        draft = _make_draft(intent_path="   ")
        with self.assertRaises(ValueError):
            RequirementsRuntime().finalize(draft, self.root)

    def test_finalize_rejects_unreadable_bound_intent(self):
        with self.assertRaises(ValueError) as ctx:
            RequirementsRuntime().finalize(_make_draft(intent_path="missing/intent.json"), self.root)
        self.assertIn("unable to read bound intent", str(ctx.exception))


class _HttpServerCase(_TempRepoCase):
    """Boots the real HTTPServer on an ephemeral port."""

    def setUp(self) -> None:
        super().setUp()
        self.write_intent(_make_intent({"sha256": "0" * 64, "path": "requirements_contract_v1.json"}))
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        _Handler.runtime = RequirementsRuntime()
        _Handler.root = self.root
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self._shutdown)

    def _shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _post(self, path: str, payload=None, raw: bytes | None = None):
        # GH-31: transient connection failures (reset/aborted) have been observed
        # against this test-local HTTPServer on some interpreter/thread-timing
        # combinations, unrelated to the assertions under test - each test method
        # spins up and tears down its own real server+thread. Retry only on
        # connection-level failures, never on a real HTTP error response (that is
        # a valid, meaningful test outcome and must not be retried away).
        data = raw if raw is not None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.url + path, data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        attempts = 3
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                body = error.read().decode("utf-8")
                try:
                    return error.code, json.loads(body)
                except json.JSONDecodeError:
                    return error.code, {"_raw": body}
            except (ConnectionError, http.client.HTTPException, urllib.error.URLError):
                if attempt == attempts - 1:
                    raise
                time.sleep(0.05 * (attempt + 1))
        raise AssertionError("unreachable")  # pragma: no cover


class FinalizeEndpointTests(_HttpServerCase):
    def test_finalize_endpoint_returns_contract_with_semantic_hash(self):
        status, body = self._post("/api/finalize", {"contract": _make_draft()})
        self.assertEqual(status, 200)
        self.assertEqual(set(body["intent_binding"]), set(INTENT_BINDING_FIELDS))

    def test_finalize_endpoint_returns_400_json_on_value_error(self):
        payload = {"contract": {"intent_binding": "not-an-object"}}
        status, body = self._post("/api/finalize", payload)
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_malformed_json_body_returns_400_json(self):
        status, body = self._post("/api/propose", raw=b"{not json")
        self.assertEqual(status, 400)
        self.assertIn("malformed JSON body", body.get("error", ""))

    def test_unknown_endpoint_returns_404_json(self):
        status, body = self._post("/api/nope", {})
        self.assertEqual(status, 404)
        self.assertIn("error", body)


if __name__ == "__main__":
    unittest.main()


class ValidateEndpointRealContractTests(_HttpServerCase):
    """Live check against the real repo contract (the endpoint's production path)."""

    def setUp(self) -> None:
        _TempRepoCase.setUp(self)  # skip _HttpServerCase's temp intent setup
        repo_root = Path(__file__).resolve().parents[1]
        self.server = HTTPServer(("127.0.0.1", 0), _Handler)
        # Fixed clock pinned INSIDE the contract's 7-day freshness window (signed
        # 2026-08-30T16:37:37Z). The test asserts the production validate path,
        # not the calendar: without this injection the test rots on 2026-09-07+
        # and turns CI deterministically red (contract is stale by design, C5).
        # The stale behavior itself is still covered below by the fixed-future
        # clock counterpart.
        fresh_clock = lambda: datetime(2026, 9, 1, tzinfo=timezone.utc)  # noqa: E731
        _Handler.runtime = RequirementsRuntime(clock=fresh_clock)
        _Handler.root = repo_root
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self._shutdown)

    def test_validate_endpoint_passes_the_real_m2_contract(self):
        status, body = self._post("/api/validate", {})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "pass", body["errors"])

    def test_validate_endpoint_reports_stale_contract_when_clock_is_past_window(self):
        # Proves the injected clock is not bypassing the freshness gate: a date
        # past the 7-day window must still produce the designed stale failure.
        stale_clock = lambda: datetime(2026, 10, 1, tzinfo=timezone.utc)  # noqa: E731
        _Handler.runtime = RequirementsRuntime(clock=stale_clock)
        status, body = self._post("/api/validate", {})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "fail")
        self.assertTrue(any("stale" in e for e in body["errors"]), body["errors"])
        # restore the fresh-clock runtime for any test ordering
        fresh_clock = lambda: datetime(2026, 9, 1, tzinfo=timezone.utc)  # noqa: E731
        _Handler.runtime = RequirementsRuntime(clock=fresh_clock)

    def test_validate_endpoint_reports_missing_contract_file_as_fail(self):
        status, body = self._post("/api/validate", {"path": "gates/requirements/nope.json"})
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "fail")
        self.assertTrue(body["errors"])
