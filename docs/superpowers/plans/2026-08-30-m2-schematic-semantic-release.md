# M2 Schematic Semantic Release Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the confirmed M2 schematic/PCB semantic defects, prevent the same common-mode validation failure from reaching release again, and convert the incident into project-owned executable learning.

**Architecture:** Keep syntax/electrical/geometry gates, but add an independent datasheet-derived contract that cross-checks intent, exported KiCad connectivity, PCB pad-to-net mapping, and firmware assumptions. Manufacturing release remains fail-closed and human-signed. Critical lessons become structured records with regression and fault-injection evidence, not prose-only notes.

**Tech Stack:** Python 3, pytest/unittest, KiCad 10 CLI and bundled `pcbnew` Python, akcli ops pipeline, freerouting 2.3.0 (`-mt 1`), JSON evidence, Markdown governance records.

---

## Task 1: Freeze the failure and revoke release

**Files:**
- Modify: `gates/board_review_v1.json`
- Modify: `tests/test_gate_core.py`
- Create: `notes/m2-semantic-repair/baseline_failure.json`

- [x] Add a failing test requiring `manufacturing_release=false` and explicit revocation metadata for the superseded sign-off.
- [x] Run the focused test and confirm RED against the currently signed release.
- [x] Record the confirmed USB polarity, SHT30 ADDR, nRESET, EN, and GPIO9 defects without rewriting historical machine evidence.
- [x] Set release false with reason, timestamp, superseded signer/evidence reference, and `human_resign_required=true`.
- [x] Run the focused test and confirm GREEN.
- [x] Commit only task-owned files.

## Task 2: Add an independent schematic semantics contract

**Files:**
- Create: `gates/contracts/m2_schematic_contract_v1.json`
- Create: `gates/schematic_semantics.py`
- Create: `tests/test_schematic_semantics.py`
- Create: `tests/fixtures/schematic_semantics/*`

- [x] Write tests for required USB pin polarity, connector-side resistor nets, SHT30 ADDR=GND/0x44, ALERT/nRESET NC policy, EN RC, GPIO9 pull-up, and firmware address agreement.
- [x] Write fail-closed tests for missing files, malformed JSON, duplicate/unknown pins, unknown severities/rules, and incomplete observations.
- [x] Add deliberate fault-injection fixtures for reversed USB, floating ADDR, missing EN capacitor, missing GPIO9 pull-up, and firmware/address mismatch.
- [x] Run focused tests and confirm RED because the evaluator does not yet exist.
- [x] Implement a deterministic evaluator with structured findings and non-zero exit on any contract violation.
- [x] Cross-check four independently obtained views: intent, KiCad netlist, PCB pad-to-net mapping, and firmware constants.
- [x] Run all semantic tests and confirm GREEN.
- [x] Commit implementation, contract, fixtures, and tests.

## Task 3: Turn the incident into an executable learning gate

**Files:**
- Create: `gates/lessons_registry_v1.json`
- Create: `gates/learning_gate.py`
- Create: `tests/test_learning_gate.py`
- Create: `docs/knowledge/PROJECT_PITFALLS.md`
- Create: `docs/knowledge/IMPROVEMENT_SYSTEM.md`

- [x] Add tests requiring every critical lesson to include root cause, escaped controls, failing fixture, regression test, fail-closed control, prior failure evidence, and passing fault-injection evidence.
- [x] Confirm RED before the gate exists.
- [x] Implement strict schema/content validation; missing or unknown fields fail.
- [x] Register `PIT-20260830-001` for common-mode intent validation and link it to Task 2 artifacts.
- [x] Document promotion criteria from project pitfall to reusable AEDL optimization rule.
- [x] Run focused tests and confirm GREEN.
- [x] Commit the learning loop.

## Task 4: Integrate gates and eliminate proxy evidence

**Files:**
- Modify: `gates/run_gates.py`
- Modify: `tests/test_run_gates.py`
- Modify: `gates/gate_core.py` if required
- Create: `notes/m2-evidence-reset/generated/schematic_semantics_current.json`
- Create: `notes/m2-evidence-reset/generated/learning_gate_current.json`

- [x] Add tests proving ops validation reads current M2 evidence, never the M1 proxy.
- [x] Add tests proving semantic and learning reports are mandatory and empty/malformed/unknown results fail.
- [x] Confirm focused RED.
- [x] Integrate both gates into the runner and manifest.
- [x] Keep release false as a deliberate final blocker after machine checks pass.
- [x] Confirm focused GREEN and commit.

## Task 5: Repair intent and regenerate the source schematic

**Files:**
- Modify: `src/hardware/m2-board/intent_v1.json`
- Modify: `src/hardware/m2-board/m2_board.kicad_sch`
- Regenerate: `src/hardware/m2-board/ops_gen.json`
- Create or update: `notes/m2-evidence-reset/generated/ops_validate_current.json`
- Modify: `tests/test_run_gates.py`

- [x] Encode D+ -> `USB_DP_CONN` -> R7 22 ohm -> `USB_DP` -> U1.14 and D- -> `USB_DM_CONN` -> R8 22 ohm -> `USB_DM` -> U1.13.
- [x] Ground U2.2 ADDR for 0x44; leave U2.3 ALERT and U2.6 nRESET intentionally NC.
- [x] Add C5 1 uF from EN to GND and R9 10 kohm from +3V3 to GPIO9/BOOT.
- [x] Restore the locked akcli generator or implement a controlled, tested, reproducible compatibility step; do not hand-author final machine evidence.
- [x] Regenerate ops/schematic and verify PWR_FLAG intent is represented and loadable in KiCad.
- [x] Export a fresh netlist and run ERC with JSON/severity-all/exit-code-violations.
- [x] Run semantic tests against actual artifacts and commit.

## Task 6: Repair PCB topology and routing

**Files:**
- Modify: `tools/build_board.py`
- Modify: `src/hardware/m2-board/m2_board.kicad_pcb`
- Modify or create: `tests/test_board_review.py`
- Modify: `tools/board_review.py`

- [ ] Add R7/R8/R9/C5 footprints and deterministic placement; place R7/R8 close to U1 USB pins.
- [ ] Update connector fanout nets to `USB_DP_CONN`/`USB_DM_CONN`.
- [ ] Add tests that USB review measures each complete logical channel across its series resistor and rejects crossed endpoint identities.
- [ ] Regenerate PCB, export DSN, route with freerouting 2.3.0 telemetry blocked and `-mt 1`, then import SES.
- [ ] Apply only controlled routing polish needed for DRC convergence.
- [ ] Run KiCad DRC and require 0 violations / 0 unconnected.
- [ ] Run semantic and board-review gates on the actual PCB and commit.

## Task 7: Refresh BOM, placement, and delivery artifacts

**Files:**
- Modify: `gates/bom/bom_v1.json`
- Regenerate: `delivery/bom.csv`
- Regenerate: `delivery/pos.csv`
- Regenerate: `delivery/jlc_gerber_upload.zip`
- Modify: `docs/third-party/THIRD_PARTY_INVENTORY.md` only if a new dependency is introduced

- [ ] Verify exact MPN/LCSC identities and current stock for R7/R8/C5; never infer a catalog number from value alone.
- [ ] Add R7/R8/R9/C5 and confirm reference parity among schematic, PCB, BOM, and position file.
- [ ] Re-export Gerbers/drill/BOM/CPL from the repaired PCB.
- [ ] Validate ZIP contents, freshness, checksums, and delivery cross-file consistency.
- [ ] Commit refreshed manufacturing artifacts, while keeping ordering unauthorized and release false.

## Task 8: Regenerate board review and evidence

**Files:**
- Modify: `gates/board_review_v1.json`
- Regenerate: `notes/m2-evidence-reset/generated/board_review_auto.json`
- Regenerate: `notes/m2-evidence-reset/generated/g2_erc_current.json`
- Regenerate: `notes/m2-evidence-reset/generated/g4_drc_current.json`
- Regenerate: `notes/m2-evidence-reset/run_manifest.json`

- [ ] Regenerate all reports from the repaired sources; do not manually edit generated truth files.
- [ ] Verify the eight software/geometry reviews separately from pending physical C-level tests.
- [ ] Confirm all machine checks pass but overall release remains blocked by `manufacturing_release=false` and `human_resign_required=true`.
- [ ] Record exact commands, tool versions, report hashes, and timestamps.
- [ ] Commit final machine evidence.

## Task 9: Close governance, compliance, and handoff

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/HANDOFF.md`
- Modify: `docs/M2板级工程评审.md`
- Modify: `docs/M2测试报告.md`
- Modify: `docs/compliance/AI_USAGE_LOG.md`
- Create: `docs/adr/ADR-0003-independent-hardware-semantic-contract.md`

- [ ] Require future hardware agents to read project pitfalls and improvement system before hardware release work.
- [ ] Correct false historical prose such as “ADDR grounded,” preserving a clear before/after incident record.
- [ ] Explain why the defect escaped: common-source intent, conformance-only ops check, ERC/DRC semantic limits, geometry-only USB review, and prose not tied to netlist.
- [ ] Record actual AI/tool/model usage and human review status without claiming physical validation.
- [ ] Update handoff with branch, commits, release-block state, pending human re-sign, pending physical tests, and no-order status.
- [ ] Run `git diff --check`, focused tests, the full test suite, and `py -3 gates\\run_gates.py`.
- [ ] Read and follow verification-before-completion before making any success claim.
- [ ] Commit locally; do not push.

## Final acceptance

- [ ] Confirm fault injection catches every reproduced defect.
- [ ] Confirm fresh ERC 0 error and DRC 0 violation / 0 unconnected.
- [ ] Confirm current M2 ops, semantic, learning, review, BOM, and delivery evidence are internally consistent.
- [ ] Confirm overall manufacturing release is still blocked pending human re-review.
- [ ] Report unrun physical tests explicitly: power-on, current, BLE range, temperature/humidity accuracy, USB eye diagram, transients, and 24/168 h stability.
- [ ] Report local commit hashes and push status (`not pushed`).
