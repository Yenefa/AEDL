# GH-86 vertical probe — INTEGRATION FINDING: C1 also erases `rotation` presence

**Severity**: P0 (same invariant as #86; different layer). **Status**: REPORTED, NOT FIXED.
**Provenance**: read-only probe `notes/gh-86/probe_c1_presence.py` (output `probe_c1_presence.txt`),
run on `fix-pr1-c4-rotation-presence` @ base `d282c0b` with the C4 fix applied.
**Owner boundary**: the GH-86 grant forbids `tools/repair_pipeline.py`; this note reports, it does not fix.

## What the probe shows

A raw PATCH proposal whose `add_net_label` op **omits** `rotation` and one that carries an
**explicit** `rotation: 0` both parse through C1 `tools.repair_pipeline.parse_proposal` into:

```text
{"op": "add_net_label", "name": "BOOT0", "at": "U1.44", "scope": "local", "rotation": 0}
```

and they produce the **same `proposal_sha256`**
(`bb9c5c669759c9699f5934fbcb21c74fb8d5a0444d3ada500a954726c66ae137`).
Cause: `_parse_op` (`tools/repair_pipeline.py:838-848`) always emits the key:

```python
rotation = 0
if "rotation" in op:
    rotation = _integer(op["rotation"], path + ".rotation")
    if rotation != 0:
        _reject(...)
return {..., "rotation": rotation}
```

After that parse, the C4 normalization the #86 fix introduced reports `EXPLICIT_0` for
**both** inputs — C4 cannot recover a presence C1 already discarded.

## Why this matters for the #86 invariant

#86 fixes C4 so that PRECHECK compares presence, not the default-filled value. That is
necessary but, on its own, may not be sufficient end-to-end. The invariant

> PRECHECK-equivalent authorized operations must have identical writer execution semantics

can still be violated *before* C4 runs, whenever the host derives the **executed** op-list
from C1's parsed output: C1 has already turned "derived-from-pin" (absent) into "explicit 0".

Path analysis (HostPatch proposal vs on-disk op-list), with the #86 C4 fix in place:

| proposal source | on-disk source | C4 verdict | executed semantics |
|---|---|---|---|
| C1 parse (explicit 0) | raw (absent) | BLOCKED (C4 fix catches it) | none |
| raw (absent) | C1 parse (explicit 0) | BLOCKED (C4 fix catches it) | none |
| raw (absent) | raw (absent) | allowed | derived angle (proposer intent) |
| C1 parse (explicit 0) | C1 parse (explicit 0) | allowed | **0, silently changed by C1** |

The last row is the open hole: if C5 serializes the executed op-list from C1's parsed ops,
the writer receives explicit 0 while the proposer asked for the derived angle, and C4 sees
two equal explicit-0 sides.

## What is UNKNOWN / TO_VERIFY

C5 (`run_round` / `bind_policy`) is not implemented on this base, so **which** source C5
will serialize to `oplist_path` is `UNKNOWN` here. If C5 serializes from the raw proposer
bytes and passes a raw-derived proposal into C4, the #86 fix is sufficient. If it serializes
C1's parsed ops, C1 must be made presence-preserving.

## Recommendation (needs Owner decision; NOT actioned in #86)

Either:
1. **New C1 card** — make `_parse_op` presence-preserving (emit `rotation` only when the raw
   op carried it, or add an explicit presence marker), accepting the resulting change to
   `to_dict()` / `proposal_sha256` semantics (contract review required); or
2. **C5 requirement** — forbid serializing the executed op-list from C1's normalized parse;
   the executed bytes must derive from the raw proposer bytes.

#86 remains a correct, self-contained C4 fix: it closes the C4-layer drift and is a
prerequisite for either option. It does not, by itself, guarantee the end-to-end invariant
if option 2 is not honored.
