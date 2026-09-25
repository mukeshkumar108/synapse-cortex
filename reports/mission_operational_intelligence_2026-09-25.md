# Mission completion: semantic state → operational intelligence (2026-09-25)

Base: `88f1be8` (Phase B.1). End state below; guardrails held throughout (see
per-section notes). Full suite green (353 passed).

## What was built (production, not shadow)

1. **Bounded semantic judge** (`src/services/semantic_judge.py`): 9 closed
   question kinds (resolves, fulfils, partially_fulfils, same_person, accepts,
   eased, supersedes, undertaking, revisit_worthy). Reuses the agenda adapter;
   zero new HTTP code. `adjudicate()` is always inspectable (verdict +
   confidence + span + rationale + machine note); `judge()` additionally
   requires verbatim grounding. Unknown kinds rejected, never improvised.
2. **Event-driven reconciliation** (`src/services/semantic_reconciliation.py`):
   post-ingest, runs on empty turns too. Deterministic overlap prefilter,
   ≤3 judge calls/turn, ≥40ch floor, per-(kind,target,message) trace markers
   (no re-judging), fail-open. Accepted `resolves` closes the loop with the
   same mutation shape as deterministic release; `partially_fulfils` writes
   relations only (partial ≠ outcome, structurally).
3. **Fulfillment grounding gate** (`lifecycle_service._fulfill_grounded`):
   overlap ≥2 proceeds deterministically; weak overlap needs judge
   confirmation; no adapter = prior behavior (rules mode byte-identical).
   Same gate retrofitted to the completion lane after a live replay caught a
   false FULFILLED (clause-7 email vs cousin-Sam reminder). Every decision
   traced (`fulfill_grounding` stage).
4. **Structural roles** (`state_roles.py`): 0..n, derived, never stored; no
   family column. Relation overlays shed obligation on fulfilment/resolution.
5. **Independent views** (`state_views.py`, 11 products): direct queries +
   pure derivations (expectation read-models, follow-up eligibility,
   graph reads, model-produced annotations). Does NOT call the packet
   compiler — views are queryable intelligence; the packet stays the
   foreground assembly consumer. Full lists; consumers narrow per turn.
6. **Unified moves** (`candidate_moves.py`): read-side over existing tables +
   graph; ASK surfaced as PROPOSE only (ACT boundary intact); SA-first
   internal-answer check suppresses answerable questions; SurfaceRegistry
   cooldowns; expiry can never resolve (read-side recompute).
7. **Operationalisation** (`operational_decision.py`): form vs authority
   separated structurally. Only pre-existing execution paths (reminder
   windows, occurrence ledger, internal watch) are `execute`; everything
   external is propose/hold. No auto-created calendar/tasks.
8. **T2 repair** (`maybe_revise_after_turn` + ingest wiring): revise on
   mutating turns with 45-min cooldown, plus liveness fallback (≥3 user turns
   + 10-min age, zero content inspection) for zero-write rupture/repair
   stretches. Fail-closed. T2 went from 0 rows in all prior replays to live
   trajectories (e.g. Elena v1→v7, S4 neck persist→improve→resolve).

## Replay/acceptance results

- Sophie S1–S4 rules: all traps pass, determinism floor unchanged.
- Sophie S1–S4 model: traps pass; S1 10 relations (1 fulfils/3 partial/6 resolves),
  11 T2 rows, 8/12 loops resolved; S3 cousin-Sam false fulfil eliminated
  (stays UNKNOWN); S2 all loops resolved; S4 Elif off-shelf, neck retired, T2
  easing trajectory; 1 grounding block verified correct (payment ≠ PE kit).
- RPD2 Elena 115-turn live replay (`evals/rpd2_elena_replay.py`): 0 errors;
  9 elena-owned ASK (never ACT/laundered), 2 kai-owned ACT (user's own),
  no elena USER_INTENTION sink, refusal creates no debt, 3 loops resolved
  via semantic edges, T2 v1→v7 tracks attraction→coercion→rupture→provocation.
- Isa: no raw transcript exists locally (RPD2 Postgres unreachable; only
  condensed beats + ground-truth ledger). NOT replayed; stated, not faked.
- Observability-gated absence: logic proven in shadow; prod lacks
  source-coverage telemetry — open gap (deferred-violation covers time-based).

## Still shadow / read-only vs authoritative

- Shadow `src/shadow_a/` untouched (superseded by prod path for covered cases).
- `semantic_views`, roles, moves, operational decisions: read-only, no
  foreground consumer wired except reconciliation/T2/promotion writes.
- `same_person` judge kind tested but unwired (needs mention-evidence
  plumbing); `supersedes`/`contradicts` vocab without deterministic writers;
  CANCELLED/NOT_FULFILLED predicates absent by decision.
- Packet/handover/runtime projection paths unchanged.

## Unresolved / next milestone

1. Wire moves + operational decisions into packet/handover as advisory
   sections (runtime decides surfacing) — the operationalisation activation.
2. `same_as` writer from entity mentions; `restated` predicate evaluation.
3. Source-coverage telemetry for true observability-gated absence.
4. Isa replay when raw transcript accessible; duplicate-clarification noise
   (pre-existing) triage.
5. Cost/latency calibration of judge calls in live traffic (caps held in
   replays: ≤3/turn + markers).
