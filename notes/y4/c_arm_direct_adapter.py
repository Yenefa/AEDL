"""Direct single-shot C adapter for OpenCode Go (formal C path — config v2).

Discovered from the local provider catalog (`~/.cache/opencode/models.json`) and
the official Go docs: provider `opencode-go`, OpenAI-compatible
`POST https://opencode.ai/zen/go/v1/chat/completions`, credential env
`OPENCODE_API_KEY`, client UA, stable `x-opencode-session` header.

Guarantees: exactly one inference request / one completion / zero tools / zero
agent loops; max_retries = 0; exact package is the only task content; exact
request and response bytes retained with hashes; timeout enforced; output-token
ceiling supplied by the caller (budget lives in the versioned config, not here);
failure consumes the slot; no parse-repair re-prompt.

Model identity: owner_model_id `deepseek-flash`; runtime slug
`opencode-go/deepseek-v4.1-flash`; only slugs resolving to "DeepSeek V4.1 Flash"
are accepted.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

IDENTITY = "DeepSeek V4.1 Flash"
OWNER_MODEL_ID = "deepseek-flash"
RUNTIME_SLUGS = {"opencode-go/deepseek-v4.1-flash": IDENTITY}
API_BASE = "https://opencode.ai/zen/go/v1"
CHAT_ENDPOINT = API_BASE + "/chat/completions"
CREDENTIAL_ENV = "OPENCODE_API_KEY"
USER_AGENT = "aedl-y4-dry-direct-c/1.0"
TIMEOUT_MS = 120000


class DirectAdapterError(ValueError):
    pass


@dataclass
class DirectResponse:
    request_bytes: bytes
    response_bytes: bytes
    content_bytes: bytes
    http_status: int
    latency_ms: int
    response_id: Optional[str]
    usage: Optional[Dict[str, Any]]
    finish_reason: Optional[str]
    tool_calls: List[Any] = field(default_factory=list)

    def to_receipt(self) -> Dict[str, Any]:
        import hashlib
        return {
            "http_status": self.http_status,
            "latency_ms": self.latency_ms,
            "response_id": self.response_id,
            "usage": self.usage,
            "finish_reason": self.finish_reason,
            "tool_calls": self.tool_calls,
            "agent_steps": 0,
            "request_body_sha256": hashlib.sha256(self.request_bytes).hexdigest(),
            "response_sha256": hashlib.sha256(self.response_bytes).hexdigest(),
            "content_sha256": hashlib.sha256(self.content_bytes).hexdigest(),
            "content_bytes": len(self.content_bytes),
        }


def resolve_slug(slug: str) -> str:
    if slug not in RUNTIME_SLUGS:
        raise DirectAdapterError(
            "runtime slug %r does not resolve to the locked identity %r"
            % (slug, IDENTITY))
    return RUNTIME_SLUGS[slug]


def build_request(slug: str, package_bytes: bytes, max_tokens: int) -> bytes:
    resolve_slug(slug)
    if not isinstance(package_bytes, bytes) or not package_bytes:
        raise DirectAdapterError("package must be non-empty bytes")
    if type(max_tokens) is not int or max_tokens <= 0:
        raise DirectAdapterError("max_tokens must be a positive integer")
    body = {
        "model": slug.split("/", 1)[1],
        "messages": [{"role": "user", "content": package_bytes.decode("utf-8")}],
        "max_tokens": max_tokens,
        "stream": False,
    }
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _default_transport(request_bytes: bytes, api_key: str,
                       session_id: str, timeout_s: float) -> Tuple[int, bytes]:
    request = urllib.request.Request(
        CHAT_ENDPOINT, data=request_bytes, method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": USER_AGENT,
                 "x-opencode-session": session_id,
                 "Authorization": "Bearer %s" % api_key})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout_s) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def invoke(package_bytes: bytes, slug: str, api_key: str, max_tokens: int,
           session_id: str, transport=None,
           timeout_ms: int = TIMEOUT_MS) -> DirectResponse:
    """Exactly one provider call. Any failure raises (slot consumed)."""
    resolve_slug(slug)
    if not api_key:
        raise DirectAdapterError("missing provider credential (environment-only)")
    request_bytes = build_request(slug, package_bytes, max_tokens)
    transport = transport or _default_transport
    started = time.monotonic()
    try:
        status, response_bytes = transport(request_bytes, api_key, session_id,
                                           timeout_ms / 1000.0)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise DirectAdapterError("provider/transport failure: %s" % type(exc).__name__) from exc
    latency_ms = int((time.monotonic() - started) * 1000)
    if status != 200:
        snippet = response_bytes.decode("utf-8", errors="replace")[:200]
        raise DirectAdapterError("provider returned HTTP %s: %s" % (status, snippet))
    try:
        payload = json.loads(response_bytes.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise DirectAdapterError("provider response is not UTF-8 JSON") from exc
    choices = payload.get("choices") or []
    if not choices:
        raise DirectAdapterError("provider response has no choices")
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise DirectAdapterError("provider response has no text content")
    return DirectResponse(
        request_bytes=request_bytes,
        response_bytes=response_bytes,
        content_bytes=content.encode("utf-8"),
        http_status=status,
        latency_ms=latency_ms,
        response_id=payload.get("id"),
        usage=payload.get("usage"),
        finish_reason=choice.get("finish_reason"),
        tool_calls=list(message.get("tool_calls") or []),
    )
