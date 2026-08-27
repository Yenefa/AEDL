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
