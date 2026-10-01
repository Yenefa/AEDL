# GH-117 bounded investigation and specialist stage

Runtime: one lead and one on-demand address specialist, hard roster cap three. All roles share eight-call, 24k-token and 300s per-episode limits. Only registered read-only projections are available, with content and source SHA256 recorded separately. Default single-agent assembly has no inspection or recovery callback.

Run the ordinary real episode from the repo with a configured key in AEDL_ARH_API_KEY (never argv):

```text
python -m tools.run_arh_episode --run-root <fresh-directory> --worker-python <isolated-akcli-python> --kicad-cli <pinned-kicad-cli> --base-url <configured-provider> --model <configured-model> --adaptive --specialist --max-calls 8
```

The operator registers current_netlist, address_contract and firmware_address. Neutral findings do not supply the target repair; the lead selects up to two source IDs. Final proposals still pass the existing three static checks, policy, native C5 transaction and independent frozen contract verifier. Models have no path, shell, writer, verifier-selection or approval capability.

Final all-real run gh117-real-04: two real DeepSeek calls (inspection and proposal), real native U2.2 FLOATING -> GND, independent fresh KiCad FAIL -> PASS, C5 COMMITTED, HUMAN_REVIEW. The specialist was configured but never needed. Input3168/output785/cache_read1280 tokens, 9.109s whole episode.

Final mixed stall control gh117-mixed-stall-03: first lead inspection and FLOATING no-op proposal are explicitly scripted. The unchanged native fault independently fails twice; one bounded recovery then runs four real lead/expert calls. The expert's advice cites measured contract/netlist projection hashes. The next real proposal repairs the candidate and the same fresh verifier returns PASS. Six total calls, two repairs, HUMAN_REVIEW, no promotion. This is CONTROL_RUN/MIXED_CONTROL, not an all-real autonomous episode.

Failure history is preserved in summary.json and the hashed archive: first real inspection plan was rejected; first mixed second-round investigation hit its output ceiling and failed JSON parsing. Exact read limits and a source-selection-only prompt were added, within the existing hard output ceiling. No validation or budget was waived. Historical passing probes precede final guard changes; only the two final roots match the current implementation hash snapshot.

New tests exercise catalog/path/authority injections, resource drift and aliases, citation mismatch, role/read/budget caps, provider failure accounting, oversized advice and actual native FAIL/FAIL/PASS. A SQLite reconstruction regression proves the single recovery allowance is checkpoint bounded. Arbitrary external BudgetStop reconstruction remains caller responsibility; this driver refuses reused roots.

This is development proof for one fixture and one rule. It is not formal gates/run_gates.py Evidence, benchmark uplift, general engineering readiness or physical/manufacturing approval. Next evaluation needs frozen multiple fault types and equal per-run budgets for baseline versus adaptive repair, including regressions and costs.
