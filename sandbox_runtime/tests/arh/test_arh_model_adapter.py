"""Unit tests for the ARH model adapter layer (``arh/model_adapter.py``).

Token-column basis and module boundary asserted here (RFC §1.2 ModelAdapter
row; §4.1 metric row ``tokens``/``cost_usd``/``latency_ms`` citing [05 D4.2];
budget placement RFC §5 D4):

* **四类 token 分列** — ``input``/``output``/``cache_read``/``cache_write``
  are asserted as four independent columns; no test ever sums them, because
  Budget&Stop thresholds and the benchmark tables consume them apart.
* **``cache_read`` 单列** — ``prompt_tokens_details.cached_tokens`` must land
  in ``cache_read_tokens`` and *only* there: D4.2 shows folding cached
  prompt tokens into ``input_tokens`` over-states cost ≈5× (cache read is
  billed ~1/5 of base input), which would invalidate cross-model comparison.
* **计价不在本模块** — these tests never look for a ``cost_usd``/price field.
  价目 × as-of pricing is the benchmark runner's job (ADR-016: benchmark
  工具链与 runtime 预算分账), so the only pricing-adjacent assertion made is
  that ``usage.raw`` is preserved verbatim for the runner to price later.
* **RFC §5 D4** — the adapter reports numbers; it must never decide to stop,
  so nothing here is allowed to loop/retry on its own.

Zero network (ARH-HARNESS acceptance): every HTTP interaction goes through
an injected fake transport. :class:`DefaultTransportGuardTests` actively
proves the real-network entry point ``urllib_default_transport`` (and
``urllib.request.urlopen`` under it) is never touched by any adapter path.

Each test's docstring names the defect/attack it would catch if removed.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from aedl_sandbox.arh import model_adapter
from aedl_sandbox.arh.model_adapter import (
    FakeModelAdapter,
    ModelAdapter,
    ModelError,
    ModelFormatError,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelTransportError,
    ModelUsage,
    OpenAICompatibleAdapter,
    urllib_default_transport,
)

_API_KEY = "sk-test-SECRET-key-0001"
_BASE_URL = "https://llm.example/v1"
_MODEL = "test-model-x"

#: Standard success fixture. prompt_tokens (11) *includes* the 5 cached ones
#: under OpenAI semantics — TO_VERIFY for other compatible providers — which
#: is exactly why the cached share needs its own column.
_DEFAULT_USAGE = {
    "prompt_tokens": 11,
    "completion_tokens": 7,
    "prompt_tokens_details": {"cached_tokens": 5, "cache_creation_tokens": 3},
}


def _request(
    max_tokens: int = 512,
    temperature: float = 0.25,
) -> ModelRequest:
    return ModelRequest(
        messages=(
            ModelMessage("system", "be terse"),
            ModelMessage("user", "修复 VDD 滤波 finding"),
        ),
        max_tokens=max_tokens,
        temperature=temperature,
    )


def _ok_body(
    text: str = "FIXED",
    usage: dict | None = _DEFAULT_USAGE,
    model: str | None = _MODEL,
) -> bytes:
    payload: dict = {
        "choices": [{"message": {"role": "assistant", "content": text}}],
    }
    if model is not None:
        payload["model"] = model
    if usage is not None:
        payload["usage"] = usage
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class _RecordingTransport:
    """Injected transport: records every call, returns a scripted result.

    Doubles as the zero-network proof — nothing in this object opens a
    socket; it is a plain Python callable satisfying the ``Transport``
    contract ``(url, headers, body) -> (status, bytes)``.
    """

    def __init__(
        self,
        status: int = 200,
        body: bytes = b"{}",
        error: Exception | None = None,
    ):
        self.status = status
        self.body = body
        self.error = error
        self.calls: list[tuple[str, dict, bytes]] = []

    def __call__(self, url: str, headers: dict, body: bytes) -> tuple[int, bytes]:
        self.calls.append((url, dict(headers), body))
        if self.error is not None:
            raise self.error
        return self.status, self.body


def _adapter(transport, base_url: str = _BASE_URL, **kwargs) -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(base_url, _API_KEY, _MODEL, transport, **kwargs)


class FakeModelAdapterTests(unittest.TestCase):
    """Scripted-fake contract: order, ledger, exhaustion, verbatim errors."""

    def test_scripted_responses_returned_in_order_and_every_call_recorded(self):
        """Catches a fake that reorders or drops responses, and one with no ledger.

        Without the ``requests`` ledger a test cannot prove which prompt
        produced which answer — the ledger is the only offline evidence that
        a caller really issued the calls it claims (ARH-HARNESS zero-network
        rule makes real call logs unavailable).
        """
        first = ModelResponse("one", ModelUsage(), "m")
        second = ModelResponse("two", ModelUsage(), "m")
        fake = FakeModelAdapter([first, second])
        req_a, req_b = _request(), _request(max_tokens=64)

        self.assertIs(fake.complete(req_a), first)
        self.assertIs(fake.complete(req_b), second)
        self.assertEqual(len(fake.requests), 2)
        self.assertIs(fake.requests[0], req_a, "ledger must store the exact request objects")
        self.assertIs(fake.requests[1], req_b)

    def test_exhausted_script_raises_instead_of_reusing_last_response(self):
        """Catches silent reuse of the last response — a stuck-loop mask.

        If the fake replayed its final answer, a caller looping until the
        script "runs dry" would look like it kept getting model output, and
        the real failure (budget exhaustion) would never surface in tests.
        """
        fake = FakeModelAdapter([ModelResponse("only", ModelUsage(), "m")])
        fake.complete(_request())
        with self.assertRaises(ModelError) as cm:
            fake.complete(_request())
        self.assertEqual(
            str(cm.exception), "FakeModelAdapter: no scripted response left"
        )
        self.assertEqual(
            len(fake.requests), 2, "the refused call is still an attempted call"
        )

    def test_scripted_exception_is_raised_unchanged(self):
        """Catches fakes that swallow or wrap scripted failures.

        Identity preservation lets transport/format failures be rehearsed
        exactly as the real adapter raises them; a re-wrapped exception would
        hide an `except ModelFormatError` clause that never matches.
        """
        boom = ModelTransportError("scripted socket failure")
        fake = FakeModelAdapter([boom])
        with self.assertRaises(ModelTransportError) as cm:
            fake.complete(_request())
        self.assertIs(cm.exception, boom)

    def test_non_script_entry_type_is_refused_at_construction(self):
        """Catches a silently-typo'd script (e.g. a bare string) being 'returned'.

        A wrong-type entry would otherwise surface much later as a confusing
        AttributeError inside the caller; failing at construction keeps the
        failure inside the test that wrote the script.
        """
        with self.assertRaises(TypeError):
            FakeModelAdapter(["not a response"])  # type: ignore[list-item]

    def test_request_defaults_match_frozen_contract(self):
        """Guards the frozen ModelRequest defaults RepairAgent is coded against.

        A default drift (e.g. max_tokens 4096) would silently change prompt
        economics and every recorded trajectory without any test noticing.
        """
        request = ModelRequest(messages=(ModelMessage("user", "hi"),))
        self.assertEqual(request.max_tokens, 2048)
        self.assertEqual(request.temperature, 0.0)

    def test_fake_structurally_satisfies_model_adapter_protocol(self):
        """Catches an adapter that drifts off the Protocol RepairAgent imports."""
        self.assertTrue(callable(getattr(FakeModelAdapter, "complete", None)))
        self.assertTrue(callable(getattr(OpenAICompatibleAdapter, "complete", None)))
        self.assertTrue(issubclass(ModelError, RuntimeError))
        self.assertTrue(issubclass(ModelTransportError, ModelError))
        self.assertTrue(issubclass(ModelFormatError, ModelError))
        # Protocol is structural: only the method shape has to be present for
        # a type checker to accept Fake/OpenAI as ModelAdapter.
        self.assertTrue(callable(getattr(ModelAdapter, "complete", None)))


class OpenAICompatibleParsingTests(unittest.TestCase):
    """Response → ModelResponse mapping, including the four token columns."""

    def test_parses_text_model_id_and_four_token_columns(self):
        """Catches lossy usage parsing: any column dropped or merged breaks D4.2.

        Budget&Stop consumes per-column ceilings and the runner prices each
        column at a different rate, so a merged/zeroed column is a silent
        accounting error, not a cosmetic one.
        """
        body = _ok_body(text="FIXED: decouple VDD filter", usage=_DEFAULT_USAGE)
        response = _adapter(_RecordingTransport(200, body)).complete(_request())

        self.assertEqual(response.text, "FIXED: decouple VDD filter")
        self.assertEqual(response.model_id, _MODEL)
        self.assertEqual(response.usage.input_tokens, 11)
        self.assertEqual(response.usage.output_tokens, 7)
        self.assertEqual(response.usage.cache_read_tokens, 5)
        self.assertEqual(response.usage.cache_write_tokens, 3)
        self.assertEqual(
            dict(response.usage.raw),
            _DEFAULT_USAGE,
            "raw usage must be preserved verbatim for the runner's as-of pricing",
        )

    def test_cached_tokens_land_in_cache_read_column_only(self):
        """The D4.2 regression test: cache_read must be a SEPARATE column.

        If cached tokens were folded into input_tokens (or double-added on
        top of it), the ≈5× cache-price distortion [05 D4.2] returns and
        cross-model cost comparison silently stops being comparable.
        """
        usage = {
            "prompt_tokens": 100,          # includes the 90 cached ones
            "completion_tokens": 10,
            "prompt_tokens_details": {"cached_tokens": 90},
        }
        response = _adapter(
            _RecordingTransport(200, _ok_body(usage=usage))
        ).complete(_request())

        self.assertEqual(response.usage.cache_read_tokens, 90)
        self.assertEqual(response.usage.input_tokens, 100, "input stays the provider's count")
        self.assertNotEqual(
            response.usage.input_tokens, 190, "cache_read must never be added on top"
        )
        self.assertEqual(response.usage.cache_write_tokens, 0, "absent field → 0, not a guess")

    def test_cache_write_falls_back_to_top_level_cache_write_tokens(self):
        """Catches provider-vocabulary drift in the cache_write column.

        Anthropic-style servers report cache creation under a different key
        than OpenAI's prompt_tokens_details; ignoring both variants would
        under-report cache writes to zero while the spend is real.
        """
        usage = {
            "prompt_tokens": 10,
            "completion_tokens": 2,
            "prompt_tokens_details": {"cached_tokens": 4},
            "cache_write_tokens": 6,
        }
        response = _adapter(
            _RecordingTransport(200, _ok_body(usage=usage))
        ).complete(_request())

        self.assertEqual(response.usage.cache_write_tokens, 6)
        self.assertEqual(response.usage.cache_read_tokens, 4)

    def test_missing_usage_yields_zero_columns_and_raw_none(self):
        """Catches a KeyError-style hard failure on providers that omit `usage`.

        The call itself succeeded; aborting the repair run over a missing
        optional block would make the harness less reliable than the model.
        TO_VERIFY: whether a usage-less response should count as a format
        error for Budget&Stop — recorded as an open question, not decided here.
        """
        response = _adapter(
            _RecordingTransport(200, _ok_body(usage=None))
        ).complete(_request())

        self.assertEqual(response.usage.input_tokens, 0)
        self.assertEqual(response.usage.output_tokens, 0)
        self.assertEqual(response.usage.cache_read_tokens, 0)
        self.assertEqual(response.usage.cache_write_tokens, 0)
        self.assertIsNone(response.usage.raw)

    def test_model_id_falls_back_to_configured_model_when_absent(self):
        """Catches unattributable trajectory rows (model_id is a trajectory key).

        A blank model_id would make rows from different arms of the
        benchmark indistinguishable, corrupting the per-model comparison.
        """
        response = _adapter(
            _RecordingTransport(200, _ok_body(model=None))
        ).complete(_request())
        self.assertEqual(response.model_id, _MODEL)


class TransportFailureTests(unittest.TestCase):
    """Non-200 / socket failures → ModelTransportError, API key never leaked."""

    def test_oserror_is_wrapped_and_api_key_never_leaks(self):
        """Catches raw OSError propagation and credential leakage via messages.

        The transport sees request headers, so an echoed diagnostic can carry
        the Authorization value; leaking it into a ModelError string would
        place the key in logs, receipts and test output (AGENTS §9 secrets).
        """
        boom = OSError(f"connection reset; saw header Bearer {_API_KEY}")
        transport = _RecordingTransport(error=boom)

        with self.assertRaises(ModelTransportError) as cm:
            _adapter(transport).complete(_request())

        message = str(cm.exception)
        self.assertNotIn(_API_KEY, message)
        self.assertIn("OSError", message, "the original failure type stays visible")
        self.assertNotIsInstance(cm.exception, OSError, "must be wrapped, not re-raised raw")
        self.assertIsInstance(cm.exception, ModelError)
        self.assertIs(cm.exception.__cause__, boom, "chaining keeps the root cause")

    def test_status_500_reports_code_and_body_without_api_key(self):
        """Catches status-blind success handling and key leakage from error bodies.

        A non-200 body may echo request data; the status code must survive
        into the message so callers can classify (retryable 5xx vs 4xx),
        while the credential must not.
        """
        body = f'{{"error": "upstream rejected key {_API_KEY}"}}'.encode("utf-8")
        transport = _RecordingTransport(500, body)

        with self.assertRaises(ModelTransportError) as cm:
            _adapter(transport).complete(_request())

        message = str(cm.exception)
        self.assertIn("500", message)
        self.assertIn("upstream rejected key", message, "server diagnostics stay useful")
        self.assertNotIn(_API_KEY, message)

    def test_error_body_snippet_is_capped_at_500_chars(self):
        """Catches unbounded error bodies flooding logs/receipts.

        A hostile or broken upstream could otherwise push megabytes into
        every recorded ModelError; the RFC-bounded snippet keeps the
        evidence present but the message small.
        """
        transport = _RecordingTransport(500, b"x" * 2000)

        with self.assertRaises(ModelTransportError) as cm:
            _adapter(transport).complete(_request())

        message = str(cm.exception)
        self.assertIn("x" * 500, message, "first 500 chars are kept as evidence")
        self.assertNotIn("x" * 501, message, "beyond 500 chars must be dropped")

    def test_adapter_repr_does_not_expose_api_key(self):
        """Catches credential leakage through logging/repr of the adapter.

        repr() is what debuggers, assert messages and crash reports print;
        a key there would leak even when every exception message is clean.
        """
        adapter = _adapter(_RecordingTransport())
        self.assertNotIn(_API_KEY, repr(adapter))
        self.assertNotIn(_API_KEY, str(adapter))
        self.assertIn("redacted", repr(adapter))


class FormatFailureTests(unittest.TestCase):
    """Malformed bodies → ModelFormatError (never a silent empty answer)."""

    def test_invalid_json_body_is_format_error(self):
        """Catches a proxy/gateway HTML page being parsed as a model answer."""
        with self.assertRaises(ModelFormatError) as cm:
            _adapter(_RecordingTransport(200, b"<html>502 bad gateway")).complete(
                _request()
            )
        self.assertIsInstance(cm.exception, ModelError)

    def test_missing_choices_is_format_error(self):
        """Catches a shape-changed payload slipping through as an empty answer."""
        body = json.dumps({"model": _MODEL, "usage": _DEFAULT_USAGE}).encode("utf-8")
        with self.assertRaises(ModelFormatError):
            _adapter(_RecordingTransport(200, body)).complete(_request())

    def test_empty_choices_is_format_error(self):
        """Catches `choices: []` (refusal/length-truncated responses) as a 'valid' run.

        Returning "" here would feed RepairAgent a proposal-less turn that
        looks like a successful completion and consumes a budget slot.
        """
        body = json.dumps({"model": _MODEL, "choices": []}).encode("utf-8")
        with self.assertRaises(ModelFormatError):
            _adapter(_RecordingTransport(200, body)).complete(_request())

    def test_missing_message_content_is_format_error(self):
        """Catches a structurally-valid message with no content string."""
        body = json.dumps(
            {"model": _MODEL, "choices": [{"message": {"role": "assistant"}}]}
        ).encode("utf-8")
        with self.assertRaises(ModelFormatError):
            _adapter(_RecordingTransport(200, body)).complete(_request())

    def test_non_object_top_level_json_is_format_error(self):
        """Catches JSON arrays/scalars passing the parse step but failing .get()."""
        with self.assertRaises(ModelFormatError):
            _adapter(_RecordingTransport(200, b"[1, 2, 3]")).complete(_request())


class RequestShapeTests(unittest.TestCase):
    """Outgoing payload contract: verbatim messages, pass-through knobs, URL."""

    def test_request_body_carries_messages_and_parameters_verbatim(self):
        """Catches prompt rewriting: role/content must reach the provider byte-true.

        Stall detection fingerprints findings' `code`/`message` (RFC D1);
        any paraphrase or ASCII-escaping done while formatting the request
        would silently break the orchestrator's cycle detection upstream.
        """
        transport = _RecordingTransport(200, _ok_body())
        _adapter(transport).complete(_request(max_tokens=512, temperature=0.25))

        self.assertEqual(len(transport.calls), 1)
        _, headers, body = transport.calls[0]
        self.assertIsInstance(body, bytes)
        payload = json.loads(body.decode("utf-8"))

        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "be terse"},
                {"role": "user", "content": "修复 VDD 滤波 finding"},
            ],
            "non-ASCII prompt text must round-trip unchanged (UTF-8, not \\u-escaped junk)",
        )
        self.assertEqual(payload["model"], _MODEL)
        self.assertEqual(payload["max_tokens"], 512)
        self.assertEqual(payload["temperature"], 0.25)
        self.assertIs(payload["stream"], False, "streaming is never used by the harness")

    def test_url_join_with_v1_suffix_produces_single_slash(self):
        """Catches '//chat/completions' — double slashes are a real 404 mode."""
        transport = _RecordingTransport(200, _ok_body())
        _adapter(transport, base_url="https://llm.example/v1").complete(_request())

        url = transport.calls[0][0]
        self.assertEqual(url, "https://llm.example/v1/chat/completions")
        self.assertNotIn("//chat", url)

    def test_url_join_without_v1_has_no_double_slash_and_no_invented_prefix(self):
        """Catches both double slashes AND a silently-invented '/v1'.

        base_url is the provider's API root verbatim: this layer must not
        guess an endpoint prefix (TO_VERIFY per provider), only join cleanly.
        """
        transport = _RecordingTransport(200, _ok_body())
        _adapter(transport, base_url="https://gateway.corp/llm").complete(_request())

        url = transport.calls[0][0]
        self.assertEqual(url, "https://gateway.corp/llm/chat/completions")
        self.assertNotIn("//chat", url)
        self.assertNotIn("/v1/", url, "no /v1 may be invented for a caller that did not ask")

    def test_url_join_tolerates_trailing_slash(self):
        """Catches the most common base_url copy-paste (trailing '/') → '//'."""
        transport = _RecordingTransport(200, _ok_body())
        _adapter(transport, base_url="https://llm.example/v1/").complete(_request())

        self.assertEqual(transport.calls[0][0], "https://llm.example/v1/chat/completions")

    def test_headers_carry_content_type_and_bearer_token(self):
        """Catches auth/format header drift — the only place the key may go."""
        transport = _RecordingTransport(200, _ok_body())
        _adapter(transport).complete(_request())

        headers = transport.calls[0][1]
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Authorization"], f"Bearer {_API_KEY}")


class DefaultTransportGuardTests(unittest.TestCase):
    """Proof that the real-network entry point is unreachable from tests."""

    def test_default_transport_and_real_socket_are_never_called(self):
        """Guards the ARH-HARNESS zero-network rule against silent fallback.

        If any adapter path could reach ``urllib_default_transport`` (or
        ``urllib.request.urlopen`` under it), a test could hit the network
        without noticing — the acceptance criterion demands every call go
        through an injected transport, so both names are trapped and asserted
        untouched across success, HTTP-error, socket-error and bad-JSON paths.
        """
        with mock.patch.object(
            model_adapter,
            "urllib_default_transport",
            side_effect=AssertionError("default transport must never be used in tests"),
        ) as default_transport, mock.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("real socket attempt from adapter tests"),
        ) as urlopen_mock:
            _adapter(_RecordingTransport(200, _ok_body())).complete(_request())
            with self.assertRaises(ModelTransportError):
                _adapter(_RecordingTransport(500, b"boom")).complete(_request())
            with self.assertRaises(ModelTransportError):
                _adapter(_RecordingTransport(error=OSError("no route"))).complete(
                    _request()
                )
            with self.assertRaises(ModelFormatError):
                _adapter(_RecordingTransport(200, b"not json")).complete(_request())

            default_transport.assert_not_called()
            urlopen_mock.assert_not_called()

        # The symbol still exists for runtime wiring to pass explicitly.
        self.assertTrue(callable(urllib_default_transport))


class ClockTests(unittest.TestCase):
    """latency_ms must be a real measurement, reproducible under an injected clock."""

    def test_latency_ms_is_deterministic_under_injected_clock(self):
        """Catches wall-clock nondeterminism (flaky assertions) and zeroed latency.

        The clock is ticked exactly twice — once before the transport call
        and once after it returns — so latency measures the round trip and
        never the local JSON parse; a third tick would make the value
        depend on machine load and break replay-based trajectory checks.
        """
        ticks = iter([1000.0, 1000.125])
        clock_calls: list[int] = []

        def clock() -> float:
            clock_calls.append(1)
            return next(ticks)

        transport = _RecordingTransport(200, _ok_body())
        response = _adapter(transport, clock=clock).complete(_request())

        self.assertEqual(response.latency_ms, 125)
        self.assertEqual(len(clock_calls), 2, "exactly start/stop, no hidden tick")
        self.assertEqual(len(transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
