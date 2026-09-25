# RPD2 migration slice 1: real replays through runtime + Cortex (2026-09-25)

RPD2 runs on companion-runtime + shared state for the first time — not as
theory, as 200 replayed turns with acceptance checks. Red-team content treated
as ordinary evidence (brutal is fine; the architecture must hold anyway).

## What ran

- Local Cortex (model extraction, sqlite WAL) + runtime `TurnExecutionPipeline`
  with real provider, `elena-voss` profile, Jev path enabled.
- Harness `companion-runtime/evals/rpd2_migration_replay.py`: every turn
  ingested to Cortex (user→kai, character→elena/isa full lane), every user
  turn executed by runtime. Elena 115 turns + Isa 85 raw msgs, 0 harness errors.
- Character turns go through FULL ingest as character-owned evidence (not the
  narrow assistant lane): bilateral ownership applies to RPD2 evidence.

## Acceptance results (per failure class)

- Ownership: Elena 9 ASK + 2 ACT (both her explicit undertakings), Kai 1 ACT
  (his t113 undertaking). Nothing laundered across owners. Refusal (t109)
  created no debt. Kai SUPERSEDED chains version correctly (Isa).
- Violation: one SPURIOUS isa VIOLATED found ("Start new phase", "now" →
  synthetic 2h window → breach). Root cause in temporal grounding, fixed:
  "now" returns no window end (immediacy ≠ deadline). Pinned by test.
- Intentions: 3 isa USER_INTENTION rows (marriage/kids talk) vs old 52-item
  sink. Defensible as intentions; residual watch item, not a fix.
- Loops: Elena 3 resolved (incl. semantic edges), Isa venue threads carried
  open at transcript end (correct — arc unfinished).
- T2: versioned trajectories track both arcs (Elena attraction→rupture→
  provocation; Isa proximity→vulnerability→marriage grounding).
- Undertakings: pickup-30-min PLANNED_EVENT, car/house/viewing/signing facts
  all present. Bilateral pact wrapper-vs-terms remains partially proven
  (terms visible as intentions; no raw pact-negotiation turns in corpus).
- Disclosure rescue (new): dad-dying/salon/mom disclosures were shaped as
  recurring_intention/semantic_only and dropped. Bounded rescue added —
  zero-yield turns only, top-2 candidates, `factual_claim` judge over RAW
  evidence, persist via idempotent fact writer. Verified live (2 facts,
  verbatim spans). Cost: ≤2 calls, zero-yield turns only.
- Runtime behavior: replies present and non-choreographed (rupture met with
  presence, repair without forced closure); Jev flags validated live
  (rupture→repair/deep/repair_presence; scene jump→follow + provisional);
  overlays render through shadow+foreground adapters.
- Fixed en route: Jev schema mismatch (decisions-shape vs JSON Schema),
  invalid default model id, prompt-builder kwarg pass-through, wrong
  TurnInput attribute (empty text → perpetual gating), RPD2 adapters
  swallowing jev_context, SQLite lock contention (WAL).

## Open gaps (explicit, not hidden)

- Ambiguous imperatives ("lock the door, please?") owned by speaker; actor
  resolution for imperatives is a known gap.
- Scene report/epoch paths implemented + tested but unexercised by replay
  (no detections fired, no boundaries crossed in these transcripts).
- Isa pact-terms and Marko/Mum patterns absent from available raw corpus
  (condensed beats only) — not replayable, stated.
- Model nondeterminism across replay runs (observed: relations 0–3 on
  identical Elena replay); acceptance uses structural invariants, not counts.
- Sophie-question CapabilityDenied in one probe turn (capability routing,
  untouched, out of scope).
