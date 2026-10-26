# H1 and H2, 2026-10-26 (scratch stack on the VPS, flat-rate NanoGPT only, no paid fallback)

- `reliability_20261026_114137` agent, `_115924` one-call writer (`LEDGER_WRITER=light`), `_121828` hybrid. Four fixtures x three reps, concurrency 1.
- `h2_*`: 24 labelled sessions through the existing witness gate (labels fixed in `scripts/h2_gate.py` before the run).
- `h1_sweep2.log`: totals and new-429 counts per writer.
- A first sweep at concurrency 3 was INVALID and is not kept: NanoGPT returned HTTP 429 (34, 15 and 35 times), and the agent, with no retry and no paid fallback,
  ended unfinished in 18 of 27 sessions. It measured the rate limit, not the writers (D-P2: invalid runs are deleted and the deletion stated).
