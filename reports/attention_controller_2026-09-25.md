# Attention/surfacing controller + two-speed working sets (2026-09-25)

Outcome contract implementation. Base: `22a3511`. Full suite green (367 passed).

## Architecture (as briefed: two speeds, views ≠ packets)

```text
Cortex (cold/slow, authoritative):
  evidence/state/relations -> judge + reconciliation -> roles ->
  independent views -> session/scene working-set compiler
Runtime (hot, disposable):
  cached working set -> per-turn local selection -> foreground model;
  local surfacing state -> bounded report-back -> Cortex reconciles
```

## What was built

1. **Session/scene working sets** (`session_workingset.py` + 4 routes):
   compiled from independent views (never the foreground packet), versioned
   with `source_version` fingerprint + budgets + suppressions/deferrals.
   One builder, policy parameter (sophie/rpd2/healthcare), scene composition
   for narrative (anchor, undertakings, threads, pact terms, expected events).
   `needs_refresh` answers staleness by hash without recompiling.
2. **Pure turn selection** (`turn_selection.py`, no IO): user-first (answer,
   only protective/duty joins), proactive budgets, 5 pressure tiers from
   machine signals, dominant/combine/hold arbitration, repetition avoidance,
   suppression handling (user inquiry pierces topic suppression; initiative
   restraint preserved for proactive injection), temporal window gates +
   scene-clock override (Monday→Friday wakes latent items locally; never
   mutates claims), postures HOLD/FOLLOW/LEAD/REPAIR, no-response flags.
3. **Surfacing report-back** (`surfacing.py` + route): surfaced/ignored advance
   cooldown only (ignored ≠ resolved); answered/resolved settle source rows;
   deferred writes reopenable suppressions; dismissed writes strong
   suppression (stop-asking outranks silence); unknown outcomes skipped.
4. **Background watcher** (`background_sweep.py` + route): eligible-set
   snapshot diff in DerivedSignal; newly-eligible items for the scheduler;
   no repeat nag; prediction/outcome history preserved separately.
5. **View signals** (`state_views` additive `signals` + `protective/urgent/
   actionable` provenance): pressure tiers read enums, never content.

## Validation (real replay DBs, differential injection proven)

- Sophie S1: direct question → 3 relevant items (FOLLOW); unrelated → 0
  (no hijack); quiet scheduler → 2 opportunistic (LEAD). Suppressed topics
  stay suppressed proactively but yield to direct inquiry.
- RPD2 Elena scene: presence check → 0; door question → "lock the door"
  undertaking only; quiet → 3 narrative threads. Scene sections carry zero
  operational junk; undertakings never become self-debt.
- Fixes from validation: possessive tokenizer (`Carlos's`→`carlos`),
  rationale-text leak into relevance (owner names in `why` matched turns),
  matter-identity combining across sections, worry-view graph spillover,
  session-user excluded from character undertakings.

## Still out / next

- Moves + operational decisions as advisory packet sections (runtime decides).
- `same_as` writer; source-coverage telemetry; Isa raw transcript.
- Judge cost/latency calibration in live traffic.
- Delegated external workers (email/browser/phone) come after the attention
  controller proves itself — explicitly not this mission.
