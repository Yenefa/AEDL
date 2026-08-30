"""Advisory requirements runtime: LLM proposes, deterministic code disposes.

Two-layer architecture (the deliberate answer to CircuitBot's flaw):

Layer A (advisory, fallible, optional):
    An LLM looks at the user's natural language and *proposes* open questions
    and assumptions. It can fail, hallucinate, or return garbage - nothing
    downstream trusts it structurally.

Layer B (contract, deterministic, fail-closed):
    gates/requirements_contract.py validates the final artifact. Every
    question the LLM proposed must be either answered by the human or
    explicitly resolved before the contract passes; the gate never calls the
    LLM and never forgives a gap.

The boundary between the layers is `proposal_to_questions`: a pure function
that takes raw LLM output and produces well-formed question records with
every field defaulted to "needs a human". It never fabricates answers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from gates.requirements_contract import finalize_contract

PROPOSAL_SCHEMA = "https://aedl.local/schemas/requirements-proposal.v1.json"

_MAX_QUESTIONS = 5  # same cap as CircuitBot's clarify; one topic per question

# CircuitBot's dimension frame (MIT, ff9b003), extended per AEDL design.
_DIMENSION_TYPES = {
    "power": "power",
    "mcu": "mcu",
    "processor": "mcu",
    "sensor": "sensor",
    "input": "sensor",
    "connectivity": "connectivity",
    "communication": "connectivity",
    "display": "display",
    "output": "display",
    "formfactor": "formfactor",
    "form factor": "formfactor",
    "size": "formfactor",
}


def parse_llm_proposal(raw: Any) -> Dict[str, Any]:
    """Parse raw LLM output into a proposal envelope. Lenient about junk, strict about structure.

    Returns {"ok": bool, "questions": [...], "assumptions": [...], "warnings": [...]}.
    A failed parse is an *empty* proposal with warnings - never an exception,
    and never a fabricated question or answer.
    """
    warnings: List[str] = []
    questions: List[Dict[str, Any]] = []
    assumptions: List[Dict[str, Any]] = []

    if isinstance(raw, str):
        text = raw.strip()
        # Extract the first JSON object if the model wrapped it in prose.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                raw = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                raw = None
        else:
            raw = None
    if not isinstance(raw, dict):
        return {"ok": False, "questions": [], "assumptions": [],
                "warnings": ["LLM output was not a JSON object; proposal ignored"]}

    raw_questions = raw.get("questions")
    if raw_questions is None:
        raw_questions = []
    elif not isinstance(raw_questions, list):
        warnings.append("proposal questions was not a list; ignored")
        raw_questions = []

    seen_ids = set()
    for index, item in enumerate(raw_questions[:_MAX_QUESTIONS]):
        if not isinstance(item, dict):
            warnings.append(f"question[{index}] was not an object; skipped")
            continue
        text = item.get("question")
        if not isinstance(text, str) or not text.strip():
            warnings.append(f"question[{index}] had no question text; skipped")
            continue
        kind = item.get("kind")
        if kind not in ("blocking", "nonblocking"):
            kind = "blocking"  # unknown severity escalates to blocking, never down
            warnings.append(f"question[{index}] had unknown kind; escalated to blocking")
        options = item.get("options")
        if not isinstance(options, list) or any(not isinstance(o, str) for o in options):
            options = None
        dimension = item.get("dimension")
        if not isinstance(dimension, str):
            dimension = "other"
        question_id = item.get("id")
        if not isinstance(question_id, str) or not question_id or question_id in seen_ids:
            question_id = f"Q{index + 1}"
            if question_id in seen_ids:
                warnings.append(f"question[{index}] had a duplicate id; renamed to {question_id}_")
                question_id = f"Q{index + 1}_"
        seen_ids.add(question_id)
        # The answer is ALWAYS unset here. Answers come from humans only.
        questions.append({
            "id": question_id,
            "question": text.strip(),
            "kind": kind,
            "options": options,
            "dimension": dimension,
            "source": "llm_proposal",
            "answer": None,
        })
    if len(raw_questions) > _MAX_QUESTIONS:
        warnings.append(f"proposal had {len(raw_questions)} questions; truncated to {_MAX_QUESTIONS}")

    raw_assumptions = raw.get("assumptions")
    if raw_assumptions is None:
        raw_assumptions = []
    elif not isinstance(raw_assumptions, list):
        warnings.append("proposal assumptions was not a list; ignored")
        raw_assumptions = []
    for index, item in enumerate(raw_assumptions):
        if not isinstance(item, dict):
            warnings.append(f"assumption[{index}] was not an object; skipped")
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            warnings.append(f"assumption[{index}] had no text; skipped")
            continue
        assumptions.append({
            "id": f"A{index + 1}",
            "text": text.strip(),
            "source": "llm_proposal",
            "requires_human_confirmation": True,
        })

    return {"ok": not warnings or True, "questions": questions,
            "assumptions": assumptions, "warnings": warnings}


PROPOSAL_PROMPT_TEMPLATE = """You are the requirements-clarification advisor of a hardware engineering agent (AEDL).

Look at the user's natural-language board request and propose what MUST be clarified
before a requirements contract can be signed. You do NOT design the board. You only
surface ambiguity.

Return ONLY a JSON object:
{{
  "questions": [
    {{
      "id": "Q1",
      "question": "one concrete question, one topic",
      "kind": "blocking" | "nonblocking",
      "dimension": "power|mcu|sensor|connectivity|display|formfactor|other",
      "options": ["2-4 concrete options (optional)"]
    }}
  ],
  "assumptions": [
    {{ "text": "an assumption the design would silently rely on if nobody asks" }}
  ]
}}

Rules:
- Maximum {max_questions} questions, most important first.
- A question is "blocking" if the schematic/netlist would differ depending on the answer.
- "No preference" is a valid human answer; your job is to make the gap visible, not to resolve it.
- Do not propose questions the request already answers explicitly.
- Do not invent component choices - that is a later, evidence-gated stage.

User request:
{request}
"""


def build_proposal_prompt(request: str) -> str:
    return PROPOSAL_PROMPT_TEMPLATE.format(max_questions=_MAX_QUESTIONS, request=request.strip())


def draft_contract(
    user_goal: str,
    statements: List[Dict[str, Any]],
    resolved_requirements: List[Dict[str, Any]],
    questions: List[Dict[str, Any]],
    assumptions: List[Dict[str, Any]],
    forbidden_assumptions: List[str],
    board_id: str,
    author: str,
    created_at: str,
    intent_path: str,
    intent_semantic_sha256: str,
) -> Dict[str, Any]:
    """Assemble a contract dict and finalize the self-hash.

    All inputs here are already human-reviewed records (questions carry answers).
    The deterministic gate re-validates everything afterwards; this function
    only assembles, it never infers.

    `intent_semantic_sha256` must be computed by the caller from the intent this
    contract is being signed against, via
    `gates.requirements_contract.intent_semantic_sha256(intent_data)`. It is
    passed in rather than derived here for two reasons: this module deliberately
    does no file I/O, and "which circuit revision is being signed" is a human
    decision that belongs at the call site, not buried inside a helper.
    """
    contract = {
        "$schema": "https://aedl.local/schemas/requirements-contract.v1.json",
        "schema_version": 1,
        "board_id": board_id,
        "created_at": created_at,
        "author": author,
        "user_goal": user_goal,
        "source_statements": [
            {"id": s["id"], "text": s["text"], "type": s.get("type", "other")}
            for s in statements
        ],
        "resolved_requirements": [
            {"id": r["id"], "text": r["text"], "source_ids": list(r["source_ids"])}
            for r in resolved_requirements
        ],
        "open_questions": [
            {
                "id": q["id"], "question": q["question"], "answer": q["answer"],
                "kind": q["kind"], "source_ids": list(q.get("source_ids", [])),
            }
            for q in questions
        ],
        "assumptions": [
            {
                "id": a["id"], "text": a["text"],
                "source_ids": list(a.get("source_ids", [])), "status": "recorded",
            }
            for a in assumptions
        ],
        "forbidden_assumptions": list(forbidden_assumptions),
        # Semantic lock: the contract is signed against a specific circuit
        # revision (components + nets), not merely against a file path.
        "intent_binding": {
            "intent_path": intent_path,
            "intent_semantic_sha256": intent_semantic_sha256,
        },
    }
    return finalize_contract(contract)


def write_contract(contract: Dict[str, Any], path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(contract, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path
