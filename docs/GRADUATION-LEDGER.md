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

## Queued (from the agreed port table — choose deliberately, no parallel chaos)

* Activation / easing / backgrounding (needs CurrentMeaning as substrate; strongest
  remaining RPD2 finding).
* Union-selector Director, subtraction projection regimes, executability filter,
  write screen, initiative pin/sustain — still PORT, not started.
