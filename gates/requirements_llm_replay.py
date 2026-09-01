"""RecordedProvider: deterministic replay of recorded LLM outputs.

Idea-level adaptation of KiCadAI's RecordedProvider pattern (see
notes/open_source_intake/kicadai.md - "AI 输出录制回放测试模式"); no code is
copied. Purpose: make LLM-layer tests and demos deterministic - the runtime's
propose hook receives the recorded payload instead of calling a live model.

Fail-closed semantics:
- a request with no matching record raises ValueError (never a silent fallback
  to the heuristic proposal, never a fabricated response);
- a malformed fixture file raises ValueError at load time;
- recorded responses are payloads exactly as a model would emit them (raw
  string, possibly JSON wrapped in prose) - parse_llm_proposal downstream
  applies the usual junk-degradation, so replay exercises the real boundary.

Fixture shape (JSON):
{
  "records": [
    {"label": "optional exact-match name",
     "contains": "optional substring matcher",
     "response": "<raw model output, string or JSON object>"}
  ]
}
At least one of label/contains per record; first match wins.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List


def load_replay_provider(path: Path) -> Callable[[str], Any]:
    fixture_path = Path(path)
    try:
        with fixture_path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"replay fixture unreadable {fixture_path}: {exc}") from exc
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list) or not records:
        raise ValueError(f"replay fixture {fixture_path} must hold a non-empty records list")
    normalized: List[Dict[str, Any]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"replay fixture record[{index}] must be an object")
        label = record.get("label")
        contains = record.get("contains")
        if not isinstance(label, str) and not isinstance(contains, str):
            raise ValueError(
                f"replay fixture record[{index}] needs a 'label' or 'contains' matcher"
            )
        if "response" not in record:
            raise ValueError(f"replay fixture record[{index}] has no 'response'")
        normalized.append({"label": label, "contains": contains, "response": record["response"]})

    def provider(request: str) -> Any:
        for record in normalized:
            if isinstance(record["label"], str) and record["label"] == request:
                return record["response"]
            if isinstance(record["contains"], str) and record["contains"] in request:
                return record["response"]
        raise ValueError(
            f"no recorded LLM response matches request {request[:80]!r} "
            f"(fixture: {fixture_path.name}); replay is fail-closed - add a record "
            "or switch to a live propose hook"
        )

    return provider
