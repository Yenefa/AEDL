# Gate core review-fix RED/GREEN evidence

This evidence addresses the independent review of commit `0eec2fb`. It contains no physical validation.

## Fail-open parser RED

Command:

```powershell
py -3 -m unittest tests.test_gate_core_review -v
```

Exit code: `1`

Observed result: the isolated BOM constraints passed, but all four hostile structured-report cases were incorrectly accepted.

```text
test_each_bom_constraint_rejects_a_single_defect ... ok
test_empty_drc_arrays_without_kicad_metadata_fail_closed ... FAIL
test_empty_erc_sheets_fail_closed ... FAIL
test_erc_unknown_severity_fails_closed ... FAIL
test_erc_violation_missing_severity_fails_closed ... FAIL
test_minimal_legal_bom_returns_no_errors ... ok
test_valid_empty_kicad_reports_remain_green ... ok

Ran 7 tests in 0.034s
FAILED (failures=4)
```

## Fail-open parser GREEN

Command:

```powershell
py -3 -m unittest tests.test_gate_core_review -v
```

Exit code: `0`

```text
Ran 7 tests in 0.031s
OK
```

## Explicit verdict API RED

Command:

```powershell
py -3 -m unittest tests.test_gate_core_review -v
```

Exit code: `1`

```text
ImportError: cannot import name 'drc_gate_verdict' from 'gates.gate_core'
Ran 1 test in 0.000s
FAILED (errors=1)
```

## Explicit verdict API GREEN

Command:

```powershell
py -3 -m unittest tests.test_gate_core_review -v
```

Exit code: `0`

```text
test_drc_zero_findings_has_explicit_pass_exit_semantics ... ok
test_each_bom_constraint_rejects_a_single_defect ... ok
test_empty_drc_arrays_without_kicad_metadata_fail_closed ... ok
test_empty_erc_sheets_fail_closed ... ok
test_erc_two_errors_has_explicit_fail_exit_semantics ... ok
test_erc_unknown_severity_fails_closed ... ok
test_erc_violation_missing_severity_fails_closed ... ok
test_minimal_legal_bom_returns_no_errors ... ok
test_valid_empty_kicad_reports_remain_green ... ok

Ran 9 tests in 0.034s
OK
```

The verdict assertions are exact: ERC `2` errors maps to `status=fail, exit_code=1`; DRC `0/0` maps to `status=pass, exit_code=0`.
