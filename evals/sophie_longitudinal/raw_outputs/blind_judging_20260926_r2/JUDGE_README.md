# Blind Judging Packet R2 — three-way, Sophie longitudinal

> For: Gemini behavioural evaluation (`docs/GEMINI_BEHAVIOURAL_EVAL.md` sheet).
> Three runs, same 4 scenarios, same fixtures (manifest v1.0.0), same model
> (`google/gemini-2.5-flash-lite`). Timestamps redacted. One run is the frozen
> 2026-09-25 baseline, one is a previous current-head run, one is the new
> current-head run after four fixes (counterparty authority, expectation
> agency, actor-correct titles, OpenLoop matter identity). Labels carry no
> information about which is which.

## Contents

- `RUN-X/`, `RUN-Y/`, `RUN-Z/` — each: 4× `scenario_N_raw_checkpoints.md`
  (state dumps per checkpoint) + 4× `scenario_N_summary.json` (counts, traps,
  provider metadata, timestamps redacted).

## Scenario key (inputs NOT included — judge state evolution only)

1. Ashley Event Ops + Children + External Evidence (11 checkpoints).
2. Ordinary Sophie: plans, half-intentions, changed mind, missing detail (5).
3. Multi-source conflict, same-name disambiguation, indirect closure (6).
4. Health, worry & texture: bidirectional check-ins (9).

Oracles were runner-side only and are not in this packet. Trap scoreboards are
inside each `summary.json`.

## What to judge

Per-run and comparative, using your behavioural sheet: which evolutions are
more truthful, more continuous, less passive, less puppeted — and where any run
exhibits a named failure mode (counterparty misattribution, wrong-actor
titles, loop proliferation, spurious violation, premature closure,
shelf pollution, same-name confusion). Read checkpoint narratives, not counts.
