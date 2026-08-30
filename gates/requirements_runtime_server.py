"""HTTP shell for the requirements runtime (P2 frontend's "real API" mode).

Zero-dependency, standard-library only (Python 3.9-compatible). This is the
server side of docs/api/requirements_api.md. It exposes the five endpoints the
frontend (web/api-client.js HttpTransport) already expects:

    POST /api/propose    {"request": str}                 -> ProposalResponse
    GET  /api/contract   (404 until finalized)           -> contract JSON
    POST /api/answer     {"question_id", "answer"}       -> {"unanswered_blocking": [...]}
    POST /api/finalize   {"contract": draft}             -> contract JSON (self-hash written here)
    POST /api/validate   {"path": str}                   -> {"status", "errors"}

Design rules (same as gates/requirements_contract.py):
- The server only ASSEMBLES and VERIFIES deterministically; it never infers.
- The self-hash is written here (not in the browser) - the browser draft never
  carries contract_sha256, mirroring the mock transport's contract.
- LLM proposal is a pluggable hook. With no hook configured, propose() returns
  an explicit heuristic fallback and marks source="fallback-heuristic", never
  a fake "llm" verdict.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gates.requirements_contract import (
    compute_contract_sha256,
    intent_semantic_sha256,
    validate_requirements_contract,
)
from gates.requirements_runtime import build_proposal_prompt, parse_llm_proposal

DEFAULT_PORT = 8787


def _read_intent(root: Path, intent_path: str) -> Dict[str, Any]:
    """Read the bound intent JSON from `root`, resolving repo-relative paths.

    The browser cannot read the intent file, so the server owns this read. Paths
    are repo-relative (forward slashes, as written into intent_binding), which is
    also what the gate's own reference comparison uses.
    """
    resolved = (root / intent_path).resolve()
    try:
        with resolved.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read bound intent {intent_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"bound intent {intent_path} must be a JSON object")
    return data


def _heuristic_proposal(request: str) -> Dict[str, Any]:
    """Fallback when no LLM hook is configured.

    Deliberately small and honest: it surfaces the same five dimensions the
    contract schema cares about, marks everything blocking (a human must
    resolve), and never pretends the LLM produced it.
    """
    lowered = (request or "").lower()
    questions: List[Dict[str, Any]] = []
    dims = [
        ("power", "电路如何供电？", ["USB-C 5V", "锂电池", "外部电源"]),
        ("mcu", "主控用什么平台？", ["ESP32-C3", "RP2040", "STM32", "其他"]),
        ("sensor", "需要什么传感器/输入？", ["无", "温湿度", "其他"]),
        ("connectivity", "需要无线/通信吗？", ["无", "BLE", "Wi-Fi"]),
        ("display", "需要显示/输出吗？", ["无", "LED 指示", "OLED 屏"]),
    ]
    for index, (dimension, question, options) in enumerate(dims, start=1):
        # Skip questions the request already answers explicitly (best-effort,
        # keyword-level, same honesty caveat as C6).
        if dimension == "power" and any(k in lowered for k in ("usb", "电池", "lipo", "5v", "3.3v")):
            continue
        if dimension == "mcu" and any(k in lowered for k in ("esp32", "rp2040", "stm32", "atmega")):
            continue
        if dimension == "sensor" and any(k in lowered for k in ("温湿度", "sht", "传感器", "ds18b20", "bme280")):
            continue
        if dimension == "connectivity" and any(k in lowered for k in ("ble", "wifi", "蓝牙", "无线", "串口", "uart")):
            continue
        if dimension == "display" and any(k in lowered for k in ("led", "oled", "显示", "屏")):
            continue
        questions.append({
            "id": f"Q{index}",
            "question": question,
            "kind": "blocking",
            "dimension": dimension,
            "options": options,
            "source": "fallback-heuristic",
            "answer": None,
        })
    return {
        "questions": questions,
        "assumptions": [
            {"id": "A1", "text": "两层板、常规民用温度范围", "requires_human_confirmation": True},
        ],
        "warnings": ["LLM 建议层未配置（无 propose 钩子）；返回启发式草案，请人工逐条确认"],
    }


class RequirementsRuntime:
    """In-memory runtime state. One contract + one proposal per server process."""

    def __init__(self, propose: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
        self._propose = propose
        self.proposal: Optional[Dict[str, Any]] = None
        self.answers: Dict[str, str] = {}
        self.contract: Optional[Dict[str, Any]] = None

    def propose(self, request: str) -> Dict[str, Any]:
        if self._propose is not None:
            parsed = parse_llm_proposal(self._propose(request))
        else:
            # _heuristic_proposal already returns the final shape (source
            # = "fallback-heuristic", answer=None). Do NOT route it through
            # parse_llm_proposal, which would overwrite source to "llm_proposal"
            # and drop the honest fallback warning.
            parsed = _heuristic_proposal(request)
        self.proposal = parsed
        self.answers = {}
        self.contract = None
        return {
            "questions": parsed["questions"],
            "assumptions": parsed["assumptions"],
            "warnings": parsed["warnings"],
        }

    def answer(self, question_id: str, answer: str) -> Dict[str, Any]:
        if not isinstance(question_id, str) or not question_id:
            raise ValueError("question_id must be a non-empty string")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("answer must be a non-empty string (explicit 'unknown' allowed)")
        self.answers[question_id] = answer.strip()
        unanswered = []
        for question in (self.proposal or {}).get("questions", []):
            if question.get("kind") == "blocking" and question["id"] not in self.answers:
                unanswered.append(question["id"])
        return {"unanswered_blocking": unanswered}

    def finalize(self, draft: Dict[str, Any], root: Path) -> Dict[str, Any]:
        if not isinstance(draft, dict):
            raise ValueError("contract must be an object")
        # The browser draft has no self-hash; the server writes it (single writer).
        contract = dict(draft)
        contract.pop("contract_sha256", None)
        # The browser draft carries intent_binding.intent_path but not the
        # semantic hash (a browser cannot read the intent file). The server
        # computes it from the intent the contract is signed against, so the
        # finalized contract satisfies the C4 semantic lock.
        binding = contract.get("intent_binding")
        if not isinstance(binding, dict):
            raise ValueError("contract intent_binding must be an object")
        intent_path = binding.get("intent_path")
        if not isinstance(intent_path, str) or not intent_path.strip():
            raise ValueError("contract intent_binding.intent_path is empty")
        intent_data = _read_intent(root, intent_path)
        contract["intent_binding"] = {
            "intent_path": intent_path,
            "intent_semantic_sha256": intent_semantic_sha256(intent_data),
        }
        contract["contract_sha256"] = compute_contract_sha256(contract)
        self.contract = contract
        return contract

    def get_contract(self) -> Optional[Dict[str, Any]]:
        return self.contract

    def validate(self, path: str, root: Path) -> Dict[str, Any]:
        # Validate the finalized contract against the real gate, using the M2
        # intent as the bound design source (the runtime only validates; it does
        # not write the intent reference itself).
        contract_path = Path(path) if path else (root / "gates" / "requirements" / "requirements_contract_v1.json")
        intent_path = root / "src" / "hardware" / "m2-board" / "intent_v1.json"
        errors = validate_requirements_contract(contract_path, intent_path)
        return {"status": "pass" if not errors else "fail", "errors": errors}


class _Handler(BaseHTTPRequestHandler):
    runtime: RequirementsRuntime = None  # type: ignore[assignment]
    root: Path = None  # type: ignore[assignment]

    def _send_json(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON body: {exc}")
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _route(self) -> None:
        if self.path == "/api/propose" and self.command == "POST":
            body = self._read_json()
            result = self.runtime.propose(body.get("request", ""))
            self._send_json(200, result)
            return
        if self.path == "/api/contract" and self.command == "GET":
            contract = self.runtime.get_contract()
            if contract is None:
                self._send_json(404, {"error": "no contract yet (404)"})
            else:
                self._send_json(200, contract)
            return
        if self.path == "/api/answer" and self.command == "POST":
            body = self._read_json()
            result = self.runtime.answer(body.get("question_id"), body.get("answer", ""))
            self._send_json(200, result)
            return
        if self.path == "/api/finalize" and self.command == "POST":
            body = self._read_json()
            result = self.runtime.finalize(body.get("contract"), self.root)
            self._send_json(200, result)
            return
        if self.path == "/api/validate" and self.command == "POST":
            body = self._read_json()
            result = self.runtime.validate(body.get("path", ""), self.root)
            self._send_json(200, result)
            return
        if self.command == "OPTIONS":
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            return
        self._send_json(404, {"error": f"no such endpoint: {self.command} {self.path}"})

    def do_GET(self) -> None:
        self._safe_route()

    def do_POST(self) -> None:
        self._safe_route()

    def _safe_route(self) -> None:
        # Handler logic raises ValueError for every bad request (malformed
        # body, failed finalize preconditions, ...). Those must reach the
        # client as a 400 JSON error, never as a dropped connection - the
        # frontend renders errors[] verbatim.
        try:
            self._route()
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})

    def do_OPTIONS(self) -> None:
        self._route()

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep console output readable; errors are still surfaced via responses.
        pass


def serve(port: int = DEFAULT_PORT, propose: Optional[Callable[[str], Dict[str, Any]]] = None) -> None:
    root = Path(__file__).resolve().parents[1]
    _Handler.runtime = RequirementsRuntime(propose=propose)
    _Handler.root = root
    server = HTTPServer(("127.0.0.1", port), _Handler)
    print(f"AEDL requirements runtime listening on http://127.0.0.1:{port}")
    print(f"  propose hook: {'configured' if propose else 'NOT configured (heuristic fallback)'}")
    print("  Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
