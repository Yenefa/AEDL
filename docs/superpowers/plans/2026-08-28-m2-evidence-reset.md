# M2 Evidence Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore truthful G1/G2/G4/G10 machine gates for the ESP32-C3/SHT30 board, remove split BOM truth, generate a reproducible run manifest, and block manufacturing until a documented board-level review has no high-risk findings.

**Architecture:** Put all deterministic parsing and checks in a Python standard-library core, with a thin CLI that runs KiCad and writes immutable evidence. Keep physical layout review as an explicit structured gate instead of pretending DRC proves usability. Preserve the existing board and evidence until regenerated outputs pass the new runner.

**执行状态（2026-08-28）**：Task 1、Task 2、Task 4 和 Task 5 的确定性部分已落地；Task 3 的电源语义修复尚未完成。对 `m2_board.kicad_sch` 的手工 PWR_FLAG 尝试曾导致 KiCad 无法加载，已恢复原文件并保留真实 ERC=2 证据；不得把该任务标记为通过。当前 runner 预期退出码为 1，制造放行继续阻断。

**Tech Stack:** Python 3.9 standard library and `unittest`, KiCad 10 CLI, existing akcli/pcbnew/freerouting tools, CSV/JSON/ZIP/SHA-256 evidence.

---

## File map

- Create `gates/gate_core.py`: pure parsers and validators.
- Create `gates/run_gates.py`: M2 gate CLI and manifest writer.
- Create `gates/board_review_v1.json`: structured manufacturing review with blockers.
- Create `tests/test_gate_core.py`: regression tests for false-green ERC and BOM split truth.
- Create `tests/test_run_gates.py`: CLI/manifest tests with a fake command runner.
- Modify `gates/bom/bom_v1.json`: canonical per-part data with no `TBD`.
- Modify `gates/make_bom_csv.py`: generate only from canonical BOM and fail closed.
- Modify `src/hardware/m2-board/intent_v1.json`: model power-source semantics.
- Modify `src/hardware/m2-board/ops_gen.json`: regenerate from intent.
- Modify `src/hardware/m2-board/m2_board.kicad_sch`: regenerate and obtain ERC 0.
- Modify `tools/build_board.py`: ignore virtual schematic-only components and remove absolute root dependency.
- Create `docs/M2板级工程评审.md`: evidence-backed board review.
- Modify `docs/M2测试报告.md`, `docs/HANDOFF.md`, `README.md`: truthful current status.

## Task 1: Reproduce false green with unit tests

**Files:**
- Create: `gates/gate_core.py`
- Create: `tests/test_gate_core.py`

- [ ] **Step 1: Write failing tests against current evidence**

```python
from pathlib import Path
import unittest

from gates.gate_core import count_erc_errors, count_drc_findings, validate_bom

ROOT = Path(__file__).resolve().parents[1]

class GateCoreTests(unittest.TestCase):
    def test_current_erc_is_not_green(self):
        report = ROOT / "notes/m1-evidence/g2_erc_m2board.json"
        self.assertEqual(count_erc_errors(report), 2)

    def test_current_drc_is_green(self):
        report = ROOT / "notes/m1-evidence/g4_drc_final.json"
        self.assertEqual(count_drc_findings(report), (0, 0))

    def test_bom_rejects_tbd(self):
        errors = validate_bom(ROOT / "gates/bom/bom_v1.json")
        self.assertTrue(any("TBD" in error for error in errors))
```

- [ ] **Step 2: Run and verify RED**

Run: `py -3 -m unittest tests.test_gate_core -v`  
Expected: FAIL because `gates.gate_core` does not exist.

- [ ] **Step 3: Implement pure validators**

Export these exact functions:

```python
def count_erc_errors(path: Path) -> int: ...
def count_drc_findings(path: Path) -> tuple[int, int]: ...
def validate_bom(path: Path) -> list[str]: ...
def read_bom_refs(path: Path) -> set[str]: ...
def read_pos_refs(path: Path) -> set[str]: ...
def zip_entry_names(path: Path) -> list[str]: ...
def sha256_file(path: Path) -> str: ...
def validate_board_review(path: Path) -> list[str]: ...
```

ERC counting must traverse every sheet and count severity `error`; DRC returns violation and unconnected counts. BOM validation must reject missing/duplicate refs, `TBD`, missing LCSC code, non-positive stock, missing footprint, and malformed freeze timestamp.

- [ ] **Step 4: Run and verify GREEN**

Run: `py -3 -m unittest tests.test_gate_core -v`  
Expected: the ERC and DRC regression tests PASS; the current BOM rejection test PASSes by finding its known defect.

- [ ] **Step 5: Commit**

```powershell
git add gates/gate_core.py tests/test_gate_core.py
git commit -m "test: capture M2 false-green gate evidence"
```

## Task 2: Make BOM one truthful source

**Files:**
- Modify: `gates/bom/bom_v1.json`
- Modify: `gates/make_bom_csv.py`
- Modify: `tests/test_gate_core.py`

- [ ] **Step 1: Change the BOM test to require a valid canonical source**

Replace the temporary rejection assertion with:

```python
def test_canonical_bom_is_complete(self):
    self.assertEqual(validate_bom(ROOT / "gates/bom/bom_v1.json"), [])
```

Add a temporary copied fixture with `lcsc="TBD"` and assert it still fails, preserving the regression.

- [ ] **Step 2: Run and verify RED**

Run: `py -3 -m unittest tests.test_gate_core.GateCoreTests.test_canonical_bom_is_complete -v`  
Expected: FAIL on R5/R6 and incomplete footprints.

- [ ] **Step 3: Fix canonical data and generator**

- Set R5/R6 to C22356467, Extended library, the recorded freeze stock, and the 0603 footprint.
- Correct R1/R2 role to GPIO4/GPIO5.
- Add the actual KiCad footprint for every physical reference group.
- Use ISO-8601 UTC `frozen_at` and record the source query/evidence path.
- Remove the special-case R5/R6 rows from `make_bom_csv.py`.
- Make the generator call `validate_bom` and return nonzero without writing output when errors exist.

- [ ] **Step 4: Regenerate and verify refs**

Run: `py -3 gates/make_bom_csv.py`  
Expected: `bom rows=17` and exit 0.  
Run: `py -3 -m unittest tests.test_gate_core -v`  
Expected: all tests PASS and BOM/POS reference sets both equal the 17 physical refs.

- [ ] **Step 5: Commit**

```powershell
git add gates/bom/bom_v1.json gates/make_bom_csv.py delivery/bom.csv tests/test_gate_core.py
git commit -m "fix: make M2 BOM a single validated source"
```

## Task 3: Repair G2 power semantics at the intent source

**Files:**
- Modify: `src/hardware/m2-board/intent_v1.json`
- Modify: `src/hardware/m2-board/ops_gen.json`
- Modify: `src/hardware/m2-board/m2_board.kicad_sch`
- Modify: `tools/build_board.py`
- Modify: `tests/test_gate_core.py`

- [ ] **Step 1: Add a test that the authoritative current ERC is zero**

```python
def test_authoritative_current_erc_is_green(self):
    self.assertEqual(
        count_erc_errors(ROOT / "notes/m1-evidence/g2_erc_m2board.json"),
        0,
    )
```

- [ ] **Step 2: Run and verify RED**

Run: `py -3 -m unittest tests.test_gate_core.GateCoreTests.test_authoritative_current_erc_is_green -v`  
Expected: FAIL with `2 != 0`.

- [ ] **Step 3: Model the two power sources**

Add schematic-only `power:PWR_FLAG` intent components for +5V and GND, attach pin 1 to the corresponding nets, and mark them `virtual=true`. Update `build_board.py` to derive `ROOT` from `__file__`, accept an optional `--root`, and skip components whose intent has `virtual=true` rather than looking them up in `FP_MAP`.

Regenerate the op list and schematic from intent using the existing akcli flow. Do not suppress the two ERC errors and do not edit only the report JSON.

- [ ] **Step 4: Run authoritative checks**

Run:

```powershell
akcli ops from-intent src\hardware\m2-board\intent_v1.json -o src\hardware\m2-board\ops_gen.json
akcli draw src\hardware\m2-board\m2_board.kicad_sch --ops src\hardware\m2-board\ops_gen.json --apply --strict-nets
& $env:KICAD_CLI sch erc --format json --severity-all --exit-code-violations --output notes\m1-evidence\g2_erc_m2board.json src\hardware\m2-board\m2_board.kicad_sch
```

Expected: KiCad prints 0 violations and exits 0.  
Run: `py -3 -m unittest tests.test_gate_core -v`  
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hardware/m2-board/intent_v1.json src/hardware/m2-board/ops_gen.json src/hardware/m2-board/m2_board.kicad_sch tools/build_board.py notes/m1-evidence/g2_erc_m2board.json tests/test_gate_core.py
git commit -m "fix: model M2 power sources and restore ERC gate"
```

## Task 4: One-command manifest runner

**Files:**
- Create: `gates/run_gates.py`
- Create: `tests/test_run_gates.py`
- Create: `gates/board_review_v1.json`

- [ ] **Step 1: Write failing runner tests**

Use `tempfile.TemporaryDirectory` and an injected command runner. Test that a nonzero tool start, an ERC JSON error, a DRC finding, invalid BOM, mismatched BOM/POS refs, missing required Gerber, stale/blocked board review, or dirty checkout sets `status="fail"`. Test that every manifest contains commit, dirty state, command, exit code, counts, evidence grade, input/output SHA-256, and a stable `run_id`.

- [ ] **Step 2: Run and verify RED**

Run: `py -3 -m unittest tests.test_run_gates -v`  
Expected: FAIL because runner is missing.

- [ ] **Step 3: Implement fail-closed CLI**

CLI:

```text
py -3 gates/run_gates.py --scope m2 --output-root notes/runs
```

Required gates for `m2`: G1 BOM, G2 ERC, G4 DRC, G10 production package, and `BOARD_REVIEW`. Use `--exit-code-violations` but still parse JSON. Always write a manifest; only copy a production ZIP into the run directory when every required gate passes. Exit 0 on pass and 1 on gate failure; exit 2 on runner/configuration failure.

- [ ] **Step 4: Verify tests and real project behavior**

Run: `py -3 -m unittest tests.test_run_gates -v`  
Expected: PASS.  
Run: `py -3 gates/run_gates.py --scope m2 --output-root notes/runs`  
Expected before board review closure: exit 1 with truthful `BOARD_REVIEW=fail`, while G1/G2/G4/G10 report their actual states.

- [ ] **Step 5: Commit**

```powershell
git add gates/run_gates.py gates/board_review_v1.json tests/test_run_gates.py
git commit -m "feat: add fail-closed M2 gate manifest"
```

## Task 5: Board-level engineering review and status repair

**Files:**
- Create: `docs/M2板级工程评审.md`
- Modify: `gates/board_review_v1.json`
- Modify: `docs/M2测试报告.md`
- Modify: `docs/HANDOFF.md`
- Modify: `README.md`

- [ ] **Step 1: Record measurable review findings**

Review JSON entries must include `id`, `item`, `status` (`pass`, `fail`, `needs_physical`), `evidence`, and `decision`. Required ids: `USB_EDGE`, `ESP_ANTENNA`, `GROUND_RETURN`, `DECOUPLING`, `USB_ROUTING`, `SHT30_THERMAL`, `PROTECTION`, and `ASSEMBLY`.

Use current KiCad coordinates/rendering to record facts. Do not mark a check pass merely because DRC is zero. Any unresolved mechanical/electrical high-risk item keeps `manufacturing_release=false`.

- [ ] **Step 2: Run the gate runner**

Run: `py -3 gates/run_gates.py --scope m2 --output-root notes/runs`  
Expected: either a fully evidenced pass or an explicit exit 1 listing the remaining board blockers. No “ready to order” statement is permitted on exit 1.

- [ ] **Step 3: Repair documentation from the manifest**

README status must say “M2 evidence reset / manufacturing blocked” unless all gates pass. M2 report must state the actual ERC, DRC, BOM, simulated-sensor boundary, and board-review result. HANDOFF must point to current HEAD/run id, remove the stale “immediate order” next step, and list physical validation separately.

- [ ] **Step 4: Run final repository verification**

Run: `py -3 -m unittest discover -s tests -v`  
Expected: all tests PASS.  
Run: `git diff --check`  
Expected: no whitespace errors.  
Run the real gate command again and preserve its final manifest.

- [ ] **Step 5: Commit**

```powershell
git add gates/board_review_v1.json docs/M2板级工程评审.md docs/M2测试报告.md docs/HANDOFF.md README.md notes/runs
git commit -m "docs: reset M2 status to verified evidence"
```
