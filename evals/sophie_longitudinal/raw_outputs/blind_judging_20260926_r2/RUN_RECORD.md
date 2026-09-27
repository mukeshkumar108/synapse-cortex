# Run record R2 — full current-head benchmark after four fixes, 2026-09-26

Command (×4 scenarios via `--scenario all` equivalent in one invocation):
`./.venv/bin/python evals/sophie_longitudinal/runner.py --mode model --scenario all`
Runner/fixture/model identical to previous runs (manifest v1.0.0,
gemini-2.5-flash-lite, isolated /tmp SQLite, Honcho disabled, agenda None).

## Versions

- synapse-cortex HEAD at run: `5f0dce7` (counterparty `1a93e64` + agency
  `347a93d` + matter-identity/title fixes in `5f0dce7`; canon `6ae9df9` ancestor).
- Checkpoints: A = frozen baseline outputs (2026-09-25, `44a89d1`);
  B = previous head (pre-fix, `705f5a6`-era, preserved in
  `blind_judging_20260926/RUN-A`); C = this run.

## Result

All 4 scenarios completed, HTTP 202 throughout, no failures/timeouts.
Traps: S1 2/2, S2 4/4, S3 2/2, S4 2/2 (same as A and B tallies).
Final counts C: S1 exp=6 comm=4 loops=11 facts=9 entities=5;
S2 exp=1 comm=1 loops=2 facts=1 entities=2;
S3 exp=6 comm=1 loops=11 facts=5 entities=2;
S4 exp=0 comm=3 loops=3 facts=3 entities=3.
Full stdout not persisted (tail captured live); summaries + checkpoints committed.
