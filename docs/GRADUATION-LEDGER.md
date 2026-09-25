# Graduation Ledger — RPD2 primitives into the shared engine

Status values: `PORT` (approved to port, not built) → `SHARED / GRADUATED / LIVE VALIDATION PENDING`
(deployed, automated smoke green) → `SHARED / GRADUATED / LIVE` (live traffic calibrated).

RPD2 itself is frozen read-only reference; this ledger tracks what crossed the boundary.

## CurrentMeaning (live Account rewrite) — SHARED / GRADUATED / LIVE

* Graduated in: `0018_current_meaning` + `POST /v1/cortex/current-meaning/revise-sync`
  (commit `graduate CurrentMeaning into Cortex fast lane`).
* Semantic owner: Cortex fast lane. `current_meanings` versions means/unresolved/
  provenance only; per-turn foreground authority is ephemeral, never persisted.
* Consumer: Python companion-runtime (parallel 4th gather leg, `[CURRENT MEANING]`
  prompt module iff authority == active, id/version/authority in composition trace).
* Integrity boundaries: Cortex owns the canonical product lens; Cortex assembles
  its own evidence; no keyword/regex gate; stale writes discarded, never rebased;
  `revision_key` (idempotency) separate from `source_message_ids` (provenance);
  fail-closed omission on interpreter failure.
* Live validation PASSED (2026-09-20, VPS): `scripts/smoke_current_meaning.py`
  green against the deployed stack — health, empty-scope missing, live
  model-authored v1 revision (revised/active with means shape), stale-prior
  discard with omission. Runtime (new code, healthy) points at Cortex over the
  container network, so the 4th gather leg is live in production traffic.
* Live calibration watchlist (opportunistic, via traces — no manual QA gate):
  revision precision vs no-change rate, background rate in ordinary chat,
  leak-back of superseded meaning, 4th-leg latency distribution, omission rate
  (incl. while Cortex was down on Neon quota), version churn per scope.

## Release / backgrounding v1 — SHARED / GRADUATED / LIVE

* Proven claim: **Cortex can semantically reduce and restore foreground
  authority over retained CurrentMeaning without deleting it, without TTL
  expiry, and without lexical gating. Authority-only transitions can occur
  with zero version churn.**
* What graduated: machinery (release/reactivation with identical id/version,
  deterministic tests) + narrow lens calibration (`sophie-meaning-v2`:
  measure both directions; carry unless meaning itself changed; irrelevance
  cannot reactivate). No easing schema, no TTL, no keywords, no activation
  gradient, no CurrentMeaning changes.
* Evidence: 8-cell contrasted matrix N=3 on the live stack — resolution
  backgrounds 3/3, banter never reactivates (3/3 unchanged, no rows),
  topic-shift/warmth background with zero churn (9/9 authority-only calls
  row-free), pain stays active, relevance return reactivates.
* Recorded, not fixed: revision eagerness on pain restatement; version churn
  on genuine reactivation (v3 vs carry); sharpening/space-demand ambiguity —
  future eval labels must distinguish "issue intensifies" (stays active)
  from "user requests disengagement" (backgrounds, retained).
* Watches (existing): version churn, authority calibration, 4th-leg latency,
  omission rate. No further changes absent a failing transcript or
  materially bad live metrics.

## First-beat trajectory authority — SHARED / GRADUATED / LIVE

* Proven property: **on ordinary REPLY_ONLY turns, Companion Runtime can
  make a bounded semantic trajectory decision before generation and give a
  LEAD/STEER decision executive authority over the first foreground beat.
  The decision is single-consumption and fails open to HOLD.**
* What graduated (runtime-side, no new store): pre-generation verdict inside
  the existing gather window (`TRAJECTORY_PREGEN_TIMEOUT_MS`, default
  1500ms); executive render reusing the existing objective block with
  personality/continuity retained; `FIRST_BEAT` consumption barring
  second-beat/NEXT reuse; verdict provenance in existing state (inspection
  only — no N+1 executive carry; sustain/yield is separate). Task, session,
  deferred, CurrentMeaning, and release paths untouched.
* Evidence: `tests/test_trajectory_first_beat.py` (failed before, green
  after), full suite green, deployed healthy, CurrentMeaning smoke still
  green post-deploy.
* Recorded, not fixed: first-token latency from the bounded pre-generation
  leg; gear/model-tier effects from real ordinary-turn triggers;
  `is_release` regex remains debt owned by sustain/yield; existing
  authority-transition calibration watches remain live.

Shared spine now reads: **meaning → authority/release → trajectory →
first-beat action.**

## Sustain / yield — SHARED / GRADUATED / LIVE

* Proven property: **after a consumed first-beat lead, the next turn's
  semantic reaction exclusively determines sustain, release, or yield
  under the same trajectory identity, with no new store and no lexical
  gating.**
* What graduated (runtime-side): state-gated N+1 reaction classifier
  (welcomed/neutral/redirected/refused, bounded, temp 0); sustain reuses
  the recorded impulse + verdict id as executive first-beat context (no
  fresh LEAD minted); neutral releases to ordinary conversation; paraphrased
  refusal yields into the existing guard lifecycle with history retained;
  multi-turn sustain under one id with per-turn fresh evidence (no
  self-perpetuation); reaction outcome owns exclusive trajectory authority
  for its turn (fresh autonomous LEAD suppressed; ordinary responsiveness
  and director/task lanes untouched); fail-open releases, never sustains
  without positive evidence.
* Evidence: `tests/test_trajectory_sustain_yield.py` (A–F incl. exclusivity
  regression), full suite green, deployed healthy, CurrentMeaning smoke
  still green post-deploy.
* Recorded, not fixed: first-token latency (two bounded semantic legs on
  lead-following turns — measure p50/p95 live before any optimisation);
  `is_release` retained in session-mode + degraded paths; live calibration
  of reaction classification.

Closed loop now live: **sense → lead → observe → sustain/yield → repeat.**

## Queued (from the agreed port table — choose deliberately, no parallel chaos)

* Activation / easing / backgrounding (needs CurrentMeaning as substrate; strongest
  remaining RPD2 finding).
* Union-selector Director, subtraction projection regimes, executability filter,
  write screen, initiative pin/sustain — still PORT, not started.

## Semantic relations + operational intelligence — SHARED / GRADUATED / LIVE VALIDATION PENDING

* Graduated in: `0028_semantic_relations` + `0029_claim_occurrence_identity`
  (`semantic_claims` occurrence identity, `semantic_relations` bounded 13-type
  reified edges with provenance), deterministic promotion from lifecycle
  transitions, bounded semantic judge (9 kinds, reused adapter, verbatim
  grounding), event-driven reconciliation, fulfillment grounding gate,
  structural roles, 11 independent views, read-side moves, form-vs-authority
  operational decisions, event-driven T2 maintenance.
* Integrity boundaries: model understands, deterministic code governs; no
  keyword/regex semantics; occurrence identity (same wording, different
  speaker/evidence = different rows); no family column; no salience/authority
  columns; ASK never promoted; expiry never resolves; external execution only
  via pre-existing authority paths; fail-open everywhere off the mutation path.
* Evidence: `tests/test_semantic_pipeline.py`, `test_operational_views.py`,
  `test_semantic_relations.py`, `test_semantic_views.py`,
  `test_rpd2_elena_key_turns.py`; Sophie S1–S4 rules+model replays traps green;
  115-turn Elena live replay (ownership/ACT-boundary/T2-trajectory verified).
* Live validation pending: judge cost/latency in traffic, `same_as` writer,
  source-coverage telemetry for observability-gated absence.
