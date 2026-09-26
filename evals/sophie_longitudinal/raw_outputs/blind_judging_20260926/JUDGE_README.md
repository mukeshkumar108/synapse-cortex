# Blind Judging Packet — Sophie longitudinal, current-head vs frozen baseline

> For: Gemini behavioural evaluation (`docs/GEMINI_BEHAVIOURAL_EVAL.md` sheet).
> Two runs, same 4 scenarios, same fixtures (`manifest.json` v1.0.0), same model
> (`google/gemini-2.5-flash-lite`). Timestamps redacted. One run is the frozen
> baseline, one is current HEAD. Labels carry no information about which is which.

## Contents

- `RUN-A/` — 4× `scenario_N_raw_checkpoints.md` (state dumps per checkpoint) + 4× `scenario_N_summary.json` (counts, traps, provider metadata).
- `RUN-B/` — same layout.

## Scenario key (inputs NOT included — judge state evolution only)

1. Ashley Event Ops + Children + External Evidence (11 checkpoints; conversation, email, payment_feed, calendar).
2. Ordinary Sophie: plans, half-intentions, changed mind, missing detail (5 checkpoints; conversation, email).
3. Multi-source conflict, same-name disambiguation, indirect closure (6 checkpoints; conversation, payment_feed, email, sms, message, calendar).
4. Health, worry & texture: bidirectional check-ins (9 checkpoints; conversation).

Oracles (expected transitions, traps, release conditions) were used by the
runner's assertion layer only and are not in this packet. Trap scoreboards are
inside each `summary.json` (`traps_passed/traps_evaluated` + violations).

## What to judge

Use your behavioural sheet (agency, continuity, initiative, character
integrity, over-governance, passivity, poisoned trajectory, repair-as-action).
Compare RUN-A vs RUN-B per scenario: which state evolution is more truthful,
more continuous, less passive, less puppeted — and where either run exhibits a
named failure mode. Read the checkpoint narratives, not just counts.
