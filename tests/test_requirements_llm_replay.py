"""Tests for gates/requirements_llm_replay.py (KiCadAI-inspired replay mode).

The replay provider makes the LLM advisory layer deterministic: recorded
payloads flow through the real parse_llm_proposal boundary, and a request with
no matching record fails closed instead of silently falling back.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gates.requirements_llm_replay import load_replay_provider
from gates.requirements_runtime_server import RequirementsRuntime

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "llm_replay" / "proposal_fixture.json"


class ReplayProviderTests(unittest.TestCase):
    def setUp(self):
        self.provider = load_replay_provider(FIXTURE)

    def test_exact_label_match_returns_recorded_payload(self):
        payload = self.provider("temperature sensor carrier")
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["questions"][0]["id"], "Q1")

    def test_substring_match_returns_recorded_payload(self):
        payload = self.provider("design an ESP32 board please")
        self.assertIsInstance(payload, str)  # raw model output, prose-wrapped
        self.assertIn("天线净空", payload)

    def test_unmatched_request_fails_closed(self):
        with self.assertRaises(ValueError) as ctx:
            self.provider("a totally unknown request")
        self.assertIn("fail-closed", str(ctx.exception))

    def test_runtime_through_replay_is_deterministic(self):
        runtime = RequirementsRuntime(propose=self.provider)
        first = runtime.propose("temperature sensor carrier")
        second = RequirementsRuntime(propose=load_replay_provider(FIXTURE)).propose(
            "temperature sensor carrier"
        )
        self.assertEqual(first, second)
        # The recorded answers stay unset: humans answer, recordings never do.
        self.assertTrue(all(q["answer"] is None for q in first["questions"]))
        # Unknown kind in the recording still escalates to blocking.
        esp32 = RequirementsRuntime(propose=self.provider).propose("an ESP32 thing")
        self.assertEqual(esp32["questions"][0]["kind"], "blocking")
        # Garbage recording degrades to warnings, never an exception.
        junk = RequirementsRuntime(propose=self.provider).propose("garbage")
        self.assertEqual(junk["questions"], [])
        self.assertTrue(any("not a JSON object" in w for w in junk["warnings"]))


class FixtureValidationTests(unittest.TestCase):
    def _write(self, data):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, tmp.file, ensure_ascii=False)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return Path(tmp.name)

    def test_malformed_fixture_fails_at_load(self):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        tmp.write("{broken")
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        with self.assertRaises(ValueError):
            load_replay_provider(Path(tmp.name))

    def test_empty_records_rejected(self):
        with self.assertRaises(ValueError):
            load_replay_provider(self._write({"records": []}))

    def test_record_without_matcher_rejected(self):
        with self.assertRaises(ValueError):
            load_replay_provider(self._write({"records": [{"response": "x"}]}))

    def test_record_without_response_rejected(self):
        with self.assertRaises(ValueError):
            load_replay_provider(self._write({"records": [{"label": "a"}]}))


if __name__ == "__main__":
    unittest.main()
