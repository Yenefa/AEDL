# M2 evidence reset RED/GREEN log

This log records commands and observed outputs from the 2026-08-28 reset. It is not physical validation or fresh inventory evidence.

## Task 1 - gate core import RED

Command:

```powershell
py -3 -m unittest tests.test_gate_core -v
```

Exit code: `1`

Observed output:

```text
test_gate_core (unittest.loader._FailedTest) ... ERROR

======================================================================
ERROR: test_gate_core (unittest.loader._FailedTest)
----------------------------------------------------------------------
ImportError: Failed to import test module: test_gate_core
Traceback (most recent call last):
  File "C:\Program Files (x86)\Microsoft Visual Studio\Shared\Python39_64\lib\unittest\loader.py", line 154, in loadTestsFromName
    module = __import__(module_name)
  File "C:\Users\fuker\Desktop\workspace\project-027-autonomous-hardware-agent\tests\test_gate_core.py", line 4, in <module>
    from gates.gate_core import count_drc_findings, count_erc_errors, validate_bom
ModuleNotFoundError: No module named 'gates.gate_core'

----------------------------------------------------------------------
Ran 1 test in 0.000s

FAILED (errors=1)
```

## Task 1 - gate core regression GREEN

Command:

```powershell
py -3 -m unittest tests.test_gate_core -v
```

Exit code: `0`

Observed output:

```text
test_bom_rejects_tbd (tests.test_gate_core.GateCoreTests) ... ok
test_current_drc_is_green (tests.test_gate_core.GateCoreTests) ... ok
test_current_erc_is_not_green (tests.test_gate_core.GateCoreTests) ... ok

----------------------------------------------------------------------
Ran 3 tests in 0.005s

OK
```

## Task 2 - source-only BOM generator RED

Command:

```powershell
py -3 -m unittest tests.test_gate_core.GateCoreTests.test_generated_bom_matches_every_canonical_field -v
```

Exit code: `1`

```text
ImportError: cannot import name 'generate_bom_csv' from 'gates.make_bom_csv'
Ran 1 test in 0.000s
FAILED (errors=1)
```

## Task 2 - source-only BOM generator GREEN

Command:

```powershell
py -3 -m unittest tests.test_gate_core.GateCoreTests.test_generated_bom_matches_every_canonical_field tests.test_gate_core.GateCoreTests.test_invalid_bom_does_not_overwrite_existing_csv -v
```

Exit code: `0`

```text
test_generated_bom_matches_every_canonical_field (tests.test_gate_core.GateCoreTests) ... ok
test_invalid_bom_does_not_overwrite_existing_csv (tests.test_gate_core.GateCoreTests) ... ok

----------------------------------------------------------------------
Ran 2 tests in 0.018s

OK
```

Actual regeneration command:

```powershell
py -3 gates/make_bom_csv.py
```

Exit code: `0`

```json
{"status": "pass", "rows": 17, "message": "bom rows=17", "source": "C:\\Users\\fuker\\Desktop\\workspace\\project-027-autonomous-hardware-agent\\gates\\bom\\bom_v1.json", "output": "C:\\Users\\fuker\\Desktop\\workspace\\project-027-autonomous-hardware-agent\\delivery\\bom.csv"}
```

Task 2 regression command:

```powershell
py -3 -m unittest tests.test_gate_core -v
```

Exit code: `0`; `Ran 11 tests in 0.047s`; `OK`.

## Task 2 - canonical BOM completeness RED

Command:

```powershell
py -3 -m unittest tests.test_gate_core.GateCoreTests.test_canonical_bom_is_complete -v
```

Exit code: `1`

Observed failure: 12 canonical-source defects, including malformed date-only `frozen_at`, missing footprints, and R5/R6 `TBD` / missing stock / missing library.

```text
test_canonical_bom_is_complete (tests.test_gate_core.GateCoreTests) ... FAIL
AssertionError: Lists differ: ["malformed frozen_at: '2026-08-24'", ...] != []
First list contains 12 additional elements.
Ran 1 test in 0.002s
FAILED (failures=1)
```

## Task 2 - canonical BOM completeness GREEN

Command:

```powershell
py -3 -m unittest tests.test_gate_core.GateCoreTests.test_canonical_bom_is_complete -v
```

Exit code: `0`

```text
test_canonical_bom_is_complete (tests.test_gate_core.GateCoreTests) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.002s

OK
```

## Task 1 - remaining pure helper API RED

Command:

```powershell
py -3 -m unittest tests.test_gate_core -v
```

Exit code: `1`

Expected and observed failure: the tests imported the required helper API before it existed.

```text
ImportError: cannot import name 'read_bom_refs' from 'gates.gate_core'
Ran 1 test in 0.000s
FAILED (errors=1)
```

## Task 1 - remaining pure helper API GREEN

Command:

```powershell
py -3 -m unittest tests.test_gate_core -v
```

Exit code: `0`

Observed output:

```text
test_board_review_requires_all_items_and_release_authorization (tests.test_gate_core.GateCoreTests) ... ok
test_bom_rejects_tbd (tests.test_gate_core.GateCoreTests) ... ok
test_complete_released_board_review_is_valid (tests.test_gate_core.GateCoreTests) ... ok
test_current_delivery_refs_match_all_17_physical_parts (tests.test_gate_core.GateCoreTests) ... ok
test_current_drc_is_green (tests.test_gate_core.GateCoreTests) ... ok
test_current_erc_is_not_green (tests.test_gate_core.GateCoreTests) ... ok
test_malformed_structured_reports_fail_closed (tests.test_gate_core.GateCoreTests) ... ok
test_zip_entries_and_sha256_are_deterministic (tests.test_gate_core.GateCoreTests) ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.031s

OK
```
