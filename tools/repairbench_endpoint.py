# -*- coding: utf-8 -*-
"""Wire the LLM arms to a locally configured provider.

RES-012 already registers DeepSeek as the project's model provider for real
repair episodes, so the arms use that rather than introducing a new third party.

Credential handling, deliberately minimal and in line with ADR-022 decision 5
clause 2 (do not touch another party's account, do not spend without
authorisation):
  * AEDL_ARH_API_KEY in the environment wins, if present.
  * Otherwise the key is read at RUN TIME from the locally configured provider
    file. It is never copied into this repository, never written to a log line,
    never passed on an argv, and never printed.
  * Only the key NAME, its length, and the endpoint host appear in any output.

Budget: the arms are single-shot by design, so the per-arm ceiling is one call
per episode. Total across the two arms and five episodes that is ten calls,
which is why the model is deepseek-v4-flash.
"""

import io
import os
import re
from pathlib import Path
from typing import Optional, Tuple

ENV_KEY = "AEDL_ARH_API_KEY"
ENV_BASE = "AEDL_RB_BASE_URL"
ENV_MODEL = "AEDL_RB_MODEL"

# Local provider configuration files, in priority order. Both are the user's own
# machine configuration; neither is part of any repository.
CONFIG_CANDIDATES = (
    Path.home() / "AppData" / "Local" / "hermes" / "config.yaml",
    Path.home() / ".config" / "hermes" / "config.yaml",
)

DEFAULT_PROVIDER = "deepseek"
DEFAULT_MODEL = "deepseek-v4-flash"


def _custom_providers(text: str) -> dict:
    """Parse custom_providers into {name: {base_url, api_key}}. Keys stay in memory."""
    out: dict = {}
    cur: dict = {}
    inside = False
    for line in text.splitlines():
        if re.match(r"^custom_providers:", line):
            inside = True
            continue
        if inside:
            if line and not line[:1] in (" ", "\t", "-"):
                break
            m = re.match(r"^\s*-\s*name:\s*(\S+)", line)
            if m:
                if cur.get("name"):
                    out[cur["name"]] = cur
                cur = {"name": m.group(1)}
                continue
            m = re.match(r"^\s*base_url:\s*(\S+)", line)
            if m and cur:
                cur["base_url"] = m.group(1)
                continue
            m = re.match(r"^\s*api_key:\s*(\S+)", line)
            if m and cur:
                cur["api_key"] = m.group(1)
    if cur.get("name"):
        out[cur["name"]] = cur
    return out


def resolve_endpoint(provider: str = DEFAULT_PROVIDER,
                     model: str = DEFAULT_MODEL) -> Tuple[str, str, str]:
    """Return (base_url, api_key, model). Raises LlmUnavailable when impossible."""
    base_url = os.environ.get(ENV_BASE, "")
    key = os.environ.get(ENV_KEY, "")
    chosen_model = os.environ.get(ENV_MODEL, model)

    if key and base_url:
        return base_url, key, chosen_model

    for path in CONFIG_CANDIDATES:
        if not path.is_file():
            continue
        providers = _custom_providers(path.read_text(encoding="utf-8", errors="replace"))
        info = providers.get(provider)
        if not info:
            continue
        if not base_url:
            base_url = info.get("base_url", "")
        if not key:
            key = info.get("api_key", "")
        if base_url and key:
            return base_url, key, chosen_model

    raise RuntimeError(
        "no usable model endpoint: set %s and %s, or configure custom_providers.%s "
        "in %s" % (ENV_KEY, ENV_BASE, provider, CONFIG_CANDIDATES[0]))


def describe_endpoint() -> str:
    """A log-safe one-liner: host and model only, never the key."""
    try:
        base_url, key, model = resolve_endpoint()
    except Exception as exc:
        return "unavailable (%s)" % type(exc).__name__
    host = re.sub(r"^https?://", "", base_url).split("/")[0]
    return "host=%s model=%s key_len=%d" % (host, model, len(key))


if __name__ == "__main__":
    print(describe_endpoint())