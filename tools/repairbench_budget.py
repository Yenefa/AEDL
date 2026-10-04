# -*- coding: utf-8 -*-
"""Hard spend ceiling for model calls made by the RepairBench arms.

Owner constraint, 2026-10-05: total API model spend must not exceed 1 CNY.

Design:

* Fail-closed. Once the recorded spend reaches the ceiling, further model calls
  are refused BEFORE the request is issued. An arm that cannot spend is scored as
  an error, never as a pass.
* The ledger is a committed JSON file, so the ceiling survives across sessions
  and cannot be silently reset by re-running.
* Cost is estimated from token usage. The per-token price is a CONFIGURABLE
  ASSUMPTION, not a verified fact: deepseek-v4-flash is not an official DeepSeek
  model id and no authoritative price sheet for it was verified from here
  (TO_VERIFY). The default below is deliberately pessimistic for a Flash-tier
  model. Raw token counts are stored alongside the estimate so the real cost can
  be recomputed the moment a real price is known, without re-running anything.
* Passing --reset-ceiling or editing CEILING_CNY requires editing this file,
  which is a visible, reviewable act rather than a runtime flag.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / "benchmarks" / "repairbench_v0_1" / "budget_ledger.json"

# ---- Owner constraint -------------------------------------------------------
CEILING_CNY = 1.00

# ---- Price assumption (TO_VERIFY, pessimistic) ------------------------------
# CNY per 1M tokens. Reasoning tokens bill as output.
ASSUMED_INPUT_CNY_PER_M = 2.00
ASSUMED_OUTPUT_CNY_PER_M = 8.00
PRICE_IS_VERIFIED = False


class BudgetExceeded(RuntimeError):
    """The ceiling is reached. Raised before any request is issued."""


def _load() -> Dict[str, Any]:
    if not LEDGER_PATH.is_file():
        return {"ceiling_cny": CEILING_CNY, "spent_cny": 0.0, "calls": 0,
                "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
                "history": [], "price_assumption": {
                    "input_cny_per_m": ASSUMED_INPUT_CNY_PER_M,
                    "output_cny_per_m": ASSUMED_OUTPUT_CNY_PER_M,
                    "verified": PRICE_IS_VERIFIED}}
    data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    data.setdefault("history", [])
    return data


def _save(data: Dict[str, Any]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def estimate_cny(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000.0 * ASSUMED_INPUT_CNY_PER_M
            + output_tokens / 1_000_000.0 * ASSUMED_OUTPUT_CNY_PER_M)


def remaining_cny() -> float:
    data = _load()
    return round(data["ceiling_cny"] - data["spent_cny"], 6)


def would_exceed(input_tokens: int, output_tokens: int) -> bool:
    data = _load()
    projected = data["spent_cny"] + estimate_cny(input_tokens, output_tokens)
    return projected > data["ceiling_cny"]


def check_before_call(estimated_input_tokens: int = 0) -> None:
    """Refuse the call if the recorded spend is already at or over the ceiling."""
    data = _load()
    if data["spent_cny"] >= data["ceiling_cny"]:
        raise BudgetExceeded(
            "model spend ceiling reached: %.4f of %.2f CNY used; no further model "
            "calls will be issued" % (data["spent_cny"], data["ceiling_cny"]))
    projected = data["spent_cny"] + estimate_cny(estimated_input_tokens, 0)
    if projected > data["ceiling_cny"]:
        raise BudgetExceeded(
            "refusing call: projected %.4f CNY would exceed the %.2f CNY ceiling "
            "(spent %.4f)" % (projected, data["ceiling_cny"], data["spent_cny"]))


def record(arm: str, episode: str, usage: Dict[str, Any]) -> Dict[str, Any]:
    """Add one call's usage to the ledger and return the updated entry."""
    data = _load()
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)

    cost = estimate_cny(prompt, completion)
    # The pre-call guard only estimates from the prompt; the real charge is
    # known only after the response. Re-check here so an unexpectedly large
    # completion can never push the ledger past the ceiling silently.
    projected = data["spent_cny"] + cost
    if projected > data["ceiling_cny"]:
        raise BudgetExceeded(
            "call exceeded the %.2f CNY ceiling: spent %.6f + this call %.6f "
            "= %.6f. Ledger NOT updated; treat the ceiling as reached."
            % (data["ceiling_cny"], data["spent_cny"], cost, projected))
    entry = {
        "arm": arm,
        "episode": episode,
        "input_tokens": prompt,
        "output_tokens": completion,
        "reasoning_tokens": reasoning,
        "cost_cny": round(cost, 8),
    }
    data["spent_cny"] = round(data["spent_cny"] + cost, 8)
    data["calls"] += 1
    data["input_tokens"] += prompt
    data["output_tokens"] += completion
    data["reasoning_tokens"] += reasoning
    data["history"].append(entry)
    _save(data)
    return entry


def snapshot() -> Dict[str, Any]:
    data = _load()
    return {
        "ceiling_cny": data["ceiling_cny"],
        "spent_cny": round(data["spent_cny"], 8),
        "remaining_cny": round(data["ceiling_cny"] - data["spent_cny"], 8),
        "calls": data["calls"],
        "input_tokens": data["input_tokens"],
        "output_tokens": data["output_tokens"],
        "reasoning_tokens": data["reasoning_tokens"],
        "price_is_verified": PRICE_IS_VERIFIED,
    }


if __name__ == "__main__":
    snap = snapshot()
    print("RepairBench model budget")
    print("  ceiling   : %.2f CNY (Owner constraint, 2026-10-05)" % snap["ceiling_cny"])
    print("  spent     : %.6f CNY" % snap["spent_cny"])
    print("  remaining : %.6f CNY" % snap["remaining_cny"])
    print("  calls     : %d" % snap["calls"])
    print("  tokens    : in=%d out=%d (reasoning=%d)" % (
        snap["input_tokens"], snap["output_tokens"], snap["reasoning_tokens"]))
    print("  price     : assumed %s/M in, %s/M out, verified=%s" % (
        ASSUMED_INPUT_CNY_PER_M, ASSUMED_OUTPUT_CNY_PER_M, PRICE_IS_VERIFIED))