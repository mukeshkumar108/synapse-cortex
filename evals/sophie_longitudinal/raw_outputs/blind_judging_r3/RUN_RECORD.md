# Run record R3 — Track D head benchmark, 2026-09-27

Command: `./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario all`
Runner/fixture/model identical to R2 (manifest v1.0.0, gemini-2.5-flash-lite,
isolated /tmp SQLite per scenario, Honcho disabled, agenda adapter None).
No prompt/fixture/threshold/extractor/evaluator changes.

## Versions

- synapse-cortex HEAD at run: `adc2038` ("Track D: longitudinal matter
  continuity"; from trusted `d542395`; canon `6ae9df9` ancestor).
- Compared: R2 previous head run (5f0dce7-era, in `blind_judging_20260926_r2/RUN-Z`)
  and frozen baseline (44a89d1, in `.../RUN-X`).
- companion-runtime not exercised (Cortex-ingest benchmark only).

## Result

All 4 scenarios completed, HTTP 202 throughout, no failures/timeouts.
Traps: S1 2/2, S2 4/4, S3 2/2, S4 2/2.
Final counts R3: S1 exp=7 comm=3 loops=9 facts=9 entities=4;
S2 exp=1 comm=1 loops=2 facts=2 entities=2;
S3 exp=5 comm=1 loops=5 facts=5 entities=2;
S4 exp=2 comm=3 loops=1 facts=2 entities=2.
Full stdout not persisted (tail captured live); summaries + checkpoints in
`raw_outputs/model/` (overwrote R2-era files; R2 outputs preserved in R2 packet).
