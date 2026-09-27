# Blind Judging Packet R3 — R2 head vs Track D head (+ frozen baseline context)

> For: Gemini behavioural evaluation (existing behavioural framework).
> This is Cortex-ingest longitudinal evaluation, NOT companion-runtime
> foreground behaviour. D2/D5/D6/D7 remain N/O where appropriate.
> Three runs, same 4 scenarios, same fixtures (manifest v1.0.0), same model
> (`google/gemini-2.5-flash-lite`). Timestamps redacted. One run is the
> previous current-head run (R2), one is the new Track D head run (R3), one is
> the frozen 2026-09-25 baseline (context only). Labels carry no information
> about which is which.

## Contents

- `RUN-P/`, `RUN-Q/`, `RUN-R/` — each: 4× `scenario_N_raw_checkpoints.md`
  (state dumps per checkpoint) + 4× `scenario_N_summary.json` (counts, traps,
  provider metadata, timestamps redacted).

## Scenario key (inputs NOT included — judge state evolution only)

1. Ashley Event Ops + Children + External Evidence (11 checkpoints).
2. Ordinary Sophie: plans, half-intentions, changed mind, missing detail (5).
3. Multi-source conflict, same-name disambiguation, indirect closure (6).
4. Health, worry & texture: bidirectional check-ins (9).

Oracles were runner-side only and are not in this packet. Trap scoreboards are
inside each `summary.json` (all runs: 2/2, 4/4, 2/2, 2/2 — tallies identical,
judge the state content, not the scores).

## What to judge (Track D focus)

Whether the newer head improves, vs the R2 head: lifecycle continuity,
completion/resolution, false violation, matter duplication, retrospective
resurrection, partial fulfilment, actor/owner correctness, uncertainty
handling, attention restraint, entity integrity, revision over time.
And whether it creates new failures: false merges, premature closure,
attention spam, meaningful matters disappearing, unresolved ambiguity being
silently flattened. Read checkpoint narratives, not counts.
