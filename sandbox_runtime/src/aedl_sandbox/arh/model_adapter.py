"""Model adapter layer for the AEDL Agent Runtime Harness (ARH).

Scope, straight from RFC §1.2 (ModelAdapter row)::

    属于它:   provider 调用、prompt/消息格式化、token 记账（四类 token 分列）
    不属于它: 状态机、判决、写 candidate、构造 PolicyRequest 权威字段

Token accounting basis — RFC §4.1 metric row ``tokens`` / ``cost_usd`` /
``latency_ms`` (decision D4.2, docs/research/agent-runtime/05-eval-protocol.md):

* **四类 token 分列** — ``input_tokens`` / ``output_tokens`` /
  ``cache_read_tokens`` / ``cache_write_tokens`` stay four independent
  columns and are never summed into a "total" here: Budget&Stop ceilings
  and the benchmark tables consume them apart (RFC §1.2 cites [05 D4.1]).
* **``cache_read`` 单列** — cached prompt tokens are billed at roughly a
  fifth of the base input rate, so folding
  ``prompt_tokens_details.cached_tokens`` into ``input_tokens`` over-states
  cost by ≈5× and invalidates cross-model comparison (D4.2). That provider
  field therefore maps to ``cache_read_tokens`` and to nothing else.
* **计价不在本模块** — 价目 × as-of (price table joined at the token's
  timestamp) is the benchmark runner's job: ADR-016 splits "benchmark
  工具链与 runtime 预算分账", and RFC §4.1 lists ``cost_usd`` as a derived
  metric. Pricing inside the runtime would freeze one price table into the
  harness and break the as-of requirement. This module emits raw counts,
  the untouched provider ``usage`` payload (``ModelUsage.raw``) and
  ``latency_ms`` only.

Stopping is not here either: call-count / token / wall-clock /
consecutive-invalid-proposal / consecutive-format-error ceilings live in
the Budget&Stop module (RFC §5 D4, ARH-N6). The adapter *reports* numbers;
it never decides to stop.

Retry policy is NOT implemented in V1: RFC §1.2 lists "重试与 FormatError
类熔断" under ModelAdapter, but no retry/backoff semantics were specified
for this layer (TO_VERIFY — retry belongs to the adapter or to the
caller's budget loop, unresolved; a retry here would silently multiply
token spend against Budget&Stop's call ceiling).

Zero-network boundary: the constructor takes a REQUIRED ``transport`` and
provides no default, so no code path can fall through to a real socket.
``urllib_default_transport`` is the single real-network entry point and
must be passed in explicitly by runtime wiring; it is NOT_RUN in the test
suite (ARH-HARNESS acceptance: 测试全程零网络).
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

__all__ = [
    "Transport",
    "ModelMessage",
    "ModelRequest",
    "ModelUsage",
    "ModelResponse",
    "ModelAdapter",
    "ModelError",
    "ModelTransportError",
    "ModelFormatError",
    "FakeModelAdapter",
    "OpenAICompatibleAdapter",
    "urllib_default_transport",
]

#: Injected HTTP call: ``(url, headers, body) -> (status_code, response_bytes)``.
#: There is deliberately no default — the caller must state which transport
#: it wants, which is what makes every offline test provably offline.
Transport = Callable[[str, dict, bytes], tuple[int, bytes]]


# --------------------------------------------------------------------------
# Boundary dataclasses (frozen: a response is an observed fact, not a mutable
# accumulator — usage numbers must not be edited after the fact)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelMessage:
    """One chat turn. ``role`` is provider vocabulary, passed through verbatim."""

    role: str
    content: str


@dataclass(frozen=True)
class ModelRequest:
    """Everything this layer is allowed to know about a completion call.

    Deliberately carries no authority: no run_id, no candidate path, no
    policy fields (RFC §2.3 never-grant / schema.AUTHORITY_FIELDS).
    """

    messages: tuple[ModelMessage, ...]
    max_tokens: int = 2048
    temperature: float = 0.0


@dataclass(frozen=True)
class ModelUsage:
    """Four-column token accounting (RFC §4.1 / D4.2). No money, ever.

    ``raw`` keeps the provider's own usage object verbatim so the benchmark
    runner can price it as-of and audit the mapping without replaying the
    HTTP call.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    raw: Mapping | None = None


@dataclass(frozen=True)
class ModelResponse:
    """One completed call as the harness sees it."""

    text: str
    usage: ModelUsage
    model_id: str
    latency_ms: int = 0


class ModelAdapter(Protocol):
    """The structural contract RepairAgent programs against."""

    def complete(self, request: ModelRequest) -> ModelResponse: ...


class ModelError(RuntimeError):
    """Base class: every failure this layer admits."""


class ModelTransportError(ModelError):
    """Network/HTTP failure: non-200 status, socket error, unusable framing."""


class ModelFormatError(ModelError):
    """Response body parsed but did not match the chat.completions contract."""


# --------------------------------------------------------------------------
# Fake adapter — the offline path (ARH-HARNESS: zero network, zero real model)
# --------------------------------------------------------------------------


class FakeModelAdapter:
    """Scripted ``ModelAdapter`` for tests and dry runs.

    Semantics (deliberately strict, because a fake that "helps" hides bugs):

    * responses are consumed in order, one per ``complete()`` call;
    * an exhausted script raises ``ModelError`` instead of silently reusing
      the last response — reusing would let a test pass while the real
      caller loops on a stale answer, which is exactly the failure mode
      Budget&Stop exists to catch (RFC §5 D4);
    * a scripted ``Exception`` is raised verbatim (identity preserved), so
      transport/format failures can be rehearsed without a socket;
    * **every** call is appended to ``requests``, including one that ends in
      an error: the ledger answers "how many model calls were attempted",
      which is the number the budget module counts.
    """

    def __init__(self, responses: Sequence[ModelResponse | Exception]):
        self._script = list(responses)
        for item in self._script:
            if not isinstance(item, (ModelResponse, Exception)):
                raise TypeError(
                    "FakeModelAdapter script entries must be ModelResponse or "
                    f"Exception, got {type(item).__name__}"
                )
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._script:
            raise ModelError("FakeModelAdapter: no scripted response left")
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# --------------------------------------------------------------------------
# OpenAI-compatible HTTP adapter
# --------------------------------------------------------------------------


def urllib_default_transport(
    url: str, headers: dict, body: bytes, timeout: int = 60
) -> tuple[int, bytes]:
    """The only real-network entry point in this module (runtime wiring only).

    POSTs ``body`` with ``urllib.request`` and returns ``(status, bytes)``.
    Non-2xx responses come back as ``(code, body)`` rather than raising, so
    the adapter's non-200 branch can report the server's diagnostic body
    uniformly. Tests never pass this function (zero-network acceptance);
    the real-network path is **NOT_RUN** — only the injected-transport
    contract around it is exercised.
    """
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        try:
            return int(exc.code), exc.read()
        finally:
            exc.close()


def _join_url(base_url: str, path: str) -> str:
    """Append ``path`` to an API root without ever producing ``//``.

    ``base_url`` is taken verbatim as the provider's API root: trailing
    slashes are stripped, but no ``/v1`` prefix is invented — whether an
    endpoint lives under ``/v1`` is provider-specific and the caller has
    already put the correct root in ``base_url`` (TO_VERIFY per provider;
    AEDL hard-codes no single OpenAI-compatible deployment).
    """
    return base_url.rstrip("/") + path


def _as_count(value: Any) -> int:
    """Coerce a provider-supplied counter to a non-negative int, else 0.

    Fail-safe by design: a malformed or oddly typed count degrades to 0 (an
    under-count the runner can cross-check against ``raw``) instead of
    raising — one bad numeric field must not abort a whole repair run.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value if value >= 0 else 0


def _extract_text(data: dict) -> str:
    """Pull ``choices[0].message.content``, or refuse with ``ModelFormatError``.

    Every structural miss is an error rather than a default: a silent
    ``""`` would be handed to RepairAgent as a legitimate empty answer and
    burn a budget slot on nothing (the format-error counter needs to see it).
    """
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ModelFormatError("response has no choices[0]")
    first = choices[0]
    if not isinstance(first, dict):
        raise ModelFormatError("response.choices[0] is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ModelFormatError("response.choices[0].message missing or not an object")
    content = message.get("content")
    if not isinstance(content, str):
        # Non-string content (null / tool-call arrays) is not a usable answer
        # for a proposal-only harness: this layer only ever emits text.
        raise ModelFormatError("response.choices[0].message.content missing or not a string")
    return content


def _extract_usage(data: dict) -> ModelUsage:
    """Map provider ``usage`` onto the four columns (RFC §4.1 / D4.2).

    ``prompt_tokens_details.cached_tokens`` → ``cache_read_tokens`` ONLY, so
    the cached share stays separable and cannot silently inflate
    ``input_tokens`` (D4.2: folding it in ≈5× over-states cost).
    ``raw`` stores the untouched provider payload for the runner's as-of
    pricing; no arithmetic is done on it here.
    """
    usage = data.get("usage")
    if not isinstance(usage, dict):
        # TO_VERIFY: some OpenAI-compatible servers omit `usage`. Treated as
        # "unknown" (all-zero columns, raw=None) rather than a format error,
        # because the call itself succeeded and Budget&Stop still has to
        # count it; cross-check against the runner's own totals.
        return ModelUsage()
    details = usage.get("prompt_tokens_details")
    if not isinstance(details, dict):
        details = {}
    cache_write = _as_count(details.get("cache_creation_tokens"))
    if cache_write == 0:
        # Provider-vocabulary variants for the same quantity; both are
        # optional, absence means 0 (open-weight/compat servers differ).
        cache_write = _as_count(usage.get("cache_write_tokens"))
    return ModelUsage(
        input_tokens=_as_count(usage.get("prompt_tokens")),
        output_tokens=_as_count(usage.get("completion_tokens")),
        cache_read_tokens=_as_count(details.get("cached_tokens")),
        cache_write_tokens=cache_write,
        raw=dict(usage),
    )


class OpenAICompatibleAdapter:
    """``POST {base_url}/chat/completions`` over an injected transport.

    ``transport`` is required and has no default: real I/O only happens if
    runtime wiring explicitly hands in ``urllib_default_transport``. The API
    key exists solely inside the ``Authorization`` header — it is never
    placed in an exception message, in a recorded field, or in ``repr``
    (see ``_redact`` and ``__repr__``); tests assert all three.

    ``clock`` is injectable so ``latency_ms`` is reproducible under test;
    it measures the transport round trip only (start → transport return),
    i.e. network latency, not local JSON parse cost.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        transport: Transport,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.base_url = base_url
        self.model = model
        # Private-by-name: never read via attribute explosion, never repr'd.
        self._api_key = api_key
        self._transport = transport
        self._clock = clock

    def __repr__(self) -> str:
        """Deliberately key-free: the key must not leak through logs/reprs."""
        return (
            f"{type(self).__name__}(base_url={self.base_url!r}, "
            f"model={self.model!r}, transport=<injected>, api_key=<redacted>)"
        )

    def _redact(self, text: str) -> str:
        """Strip the API key from any text bound for an exception message.

        Response bodies and transport errors are third-party controlled and
        may echo request headers; redaction is applied at the last moment,
        to the message itself, rather than trusting each call site.
        """
        if self._api_key:
            return text.replace(self._api_key, "<REDACTED_API_KEY>")
        return text

    def _build_body(self, request: ModelRequest) -> bytes:
        """The chat.completions request payload, messages passed through verbatim."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }
        # ensure_ascii=False + explicit UTF-8: non-ASCII prompts (Chinese
        # finding messages) go over the wire as real UTF-8, not \u escapes;
        # both are legal JSON, and tests decode as UTF-8 either way.
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def complete(self, request: ModelRequest) -> ModelResponse:
        url = _join_url(self.base_url, "/chat/completions")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        body = self._build_body(request)

        started = self._clock()
        try:
            status, raw_body = self._transport(url, headers, body)
        except Exception as exc:
            # Any transport failure (OSError, timeout, DNS, a fake's
            # AssertionError) is one family: a transport error. The original
            # is chained, never re-raised bare, so callers can tell "the
            # network failed" from "the model said something unparseable".
            raise ModelTransportError(
                self._redact(
                    f"transport call to {url} failed: "
                    f"{type(exc).__name__}: {exc}"
                )
            ) from exc
        latency_ms = int(round((self._clock() - started) * 1000.0))

        if status != 200:
            snippet = raw_body.decode("utf-8", errors="replace")[:500]
            raise ModelTransportError(
                self._redact(f"HTTP {status} from {url}: {snippet}")
            )

        try:
            data = json.loads(raw_body.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise ModelFormatError(
                self._redact(f"response from {url} is not valid JSON: {exc}")
            ) from exc
        if not isinstance(data, dict):
            raise ModelFormatError(
                self._redact(
                    f"response from {url} is JSON "
                    f"{type(data).__name__}, expected an object"
                )
            )

        text = _extract_text(data)
        model = data.get("model")
        model_id = model if isinstance(model, str) and model else self.model
        return ModelResponse(
            text=text,
            usage=_extract_usage(data),
            model_id=model_id,
            latency_ms=latency_ms,
        )
