# Run record — current-head Sophie longitudinal benchmark, 2026-09-26

Command: `./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario all`
Runner: `evals/sophie_longitudinal/runner.py` at current HEAD (in-process ASGI app, per-scenario isolated SQLite in /tmp, Honcho disabled, agenda adapter None).

## Versions

- synapse-cortex HEAD: `705f5a6` (canon baseline `6ae9df9` is ancestor — verified).
- Frozen baseline: synapse-cortex `44a89d1`, companion-runtime `6b2f78d` (per manifest v1.0.0 + evals README).
- Fixtures: manifest v1.0.0 unchanged. Model both sides: `google/gemini-2.5-flash-lite` via OpenRouter.
- companion-runtime not exercised by this runner (Cortex-ingest benchmark only).

## Baseline parity / deltas (recorded BEFORE running)

- Code delta: 44a89d1 → 705f5a6 includes operational-intelligence build, attention controller, Jev consumer/reactivation, control-convergence map, slices/relations, Track B verified findings, programme docs. Runner file itself is current-HEAD version (possible drift vs 44a89d1-era runner — unquantified).
- Env delta: same model id; fresh API quota; /tmp DBs recreated per scenario (no state carryover).
- Frozen baseline outputs preserved at `raw_outputs/model_baseline_44a89d1_20260925/` (copied before run); live `raw_outputs/model/` now holds current-head outputs.

## Result (full log not persisted to file — tail captured in operator terminal)

- All 4 scenarios completed, HTTP 202 throughout, no failures/timeouts.
- S1: 11 cps, traps 2/2 (base 2/2). S2: 5 cps, traps 4/4 (base 4/4). S3: 6 cps, traps 2/2 (base 2/2). S4: 9 cps, traps 2/2 (base 2/2).
- Final-state count deltas vs baseline (LLM nondeterminism + code changes — for Gemini to interpret, not me): S1 loops 12→10, facts 10→8, supp 2→3, clarif 1→2, comm 3→2; S2 exp 3→2, loops 4→6, comm 1→2, facts 1→2; S3 loops 9→7, meaning 11→12, supp 0→1, facts 5→4, entities 2→1; S4 exp 1→0, loops 2→3, facts 2→3, supp 0→1.
- No cases hidden; trap evaluations inside each summary.json.
