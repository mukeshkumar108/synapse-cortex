# Track A — Behavioural Machinery Inventory (PROPOSED, not decided)

> Owner: Spark. Status: draft 2026-09-26. Every row is a proposal for the
> programme lead + product owner to confirm. Classes: KEEP / DELETE / DORMANT /
> EXPERIMENT / DUPLICATE / UNKNOWN. Live-scale: live / shadow / dormant /
> eval-only / dead (per-row in "Live?" column). Products affected, original
> problem, evidence, owner/caller and overlap inline in "Why" or tables below.
> Do not infer product intent from code.

## Track B verified current-head facts (2026-09-26, committed HEADs — fold-in, not proposal)

Source: `docs/TRACK_B_CURRENT_HEAD_HOT_PATH_2026-09-26.md` (ash-ai `447164b`,
companion-runtime `351ed35`, synapse-cortex `6da210f`; uncommitted excluded).
Required/duplicates as verified on one ordinary Sophie `reply_only` turn:

- Duplicate Cortex packet compilation: same `compile_attention_packet` runs 3× on
  new sessions (attention + handshake + handover/preview) and 2× on continuing
  sessions. Verified: §5/§8 of Track B doc.
- `handover/preview` is the normal foreground Cortex surface (tiny
  owed/scene/patterns/avoid/clarifications/available); broad packet is fallback.
- `candidates/query` fetched but inert to foreground (decision-record only).
- `current-meaning/revise-sync` live, durable, state-mutating; rendered only on
  `active` authority (fail-closed omission otherwise).
- Cortex `/route` and `session-working-set`/`working-set-v1` dormant on this path;
  app daily packet + `Chat.sessionRouting` + `CompanionUserState` act as the
  persisted session state instead.
- Attention packet has read-side mutations (suppression expiry, daily occurrence
  creation, surface eligibility) — not a pure read.
- Honcho compiler (10s) + targeted retrieval (12s) run every turn even when
  `select_prompt_modules` later omits the packet (rendered only on
  callback/advance/close plans); local config routing, not Cortex `/route`.
- Meaning timeout (correction): Track C verified `MEANING_TIMEOUT_SECONDS` defaults to 12 (not 1.5) and is dead/unused; the live bound is `AGENDA_RANKER_TIMEOUT_SECONDS` (also 12). No `1.5` exists in `src/`. Prior claim struck.
Also flagged by Track C (not fixed, out of mandate): `v1_cortex.py:1001-1003` normalizes invalid/missing `foreground_authority` to `"active"` in both ternary branches — possible bug, owning track to confirm intent.

## Track B sessions 2–4 verified additions (fold-in 2026-09-26 — VERIFIED facts)

Source: `docs/TRACK_B_CURRENT_HEAD_HOT_PATH_2026-09-26.md` Sessions 2–4
(harnesses with focused regression suites; no production flags added).

- `candidates/query` safely default-disabled with parity: deterministic 50ms
  candidate delay removed from first-wave barrier (end-to-end reduction >30ms
  required and met); focused runtime suite 38 passed; delivery-receipt enqueue
  was already a no-op (no `candidate_refs` populated). Classification: inert
  plumbing removal, NOT a behaviour change.
- Handshake retained: session-entry harness (handover held fixed, entry context
  fixed) showed prompt/routing parity WITHOUT handshake except four uniquely
  populated contract fields — `daypart`, `live` (live_threads), `avoidSurface`,
  `memoryRefs` — unconsumed by current Sophie prompt but unique returned context
  for non-prompt/future callers. Removal fails strict parity: RETAIN.
- Attention→handover projection reuse proved equivalent in harness: normal vs
  captured-packet preview arms identical (handover projection, agenda/admission,
  durable state clean) excluding `metrics.cortex_ms`; 26→8 SQL statements,
  19.1→5.05ms request time. Request params (`turn_text`, `message_id`,
  `director_hints.product`) validated downstream-only, not packet-invalidating.
- Status: VALIDATED OPTIMISATION / NOT AUTHORISED FOR IMPLEMENTATION YET.
  Blocked at transport/deployment semantics (separate HTTP requests/transactions,
  possibly processes; no packet-bearing contract; process-local cache raises
  race/eviction/identity/multi-worker questions). Revisit only with an explicitly
  authorized cross-request contract; no implicit cache. Next smallest bounded cut
  per Track B: delete default-off candidates plumbing (done above), NOT packet
  combination.
- Attention read-side mutations verified as exactly three classes (seeded read):
  suppression ACTIVE→EXPIRED; daily RecurringOccurrence creation; over-age
  clarification PENDING→DISMISSED. Surface eligibility reads only. Neither preview
  arm altered these. Any future combination must preserve the mutation-bearing
  attention read alongside preview's rollback/no-write contract.

## Runtime / perception / selection

| # | Mechanism | Where | Live? | Proposed | Why (one line) |
|---|---|---|---|---|---|
| 1 | Dual Aperture (HOLD/ENRICH/LEAD/ATTEND) | `companion-runtime/companion_core/policy/conversational_agency.py`, `turn_executor.py:1114-1162` | Yes (Sophie) | KEEP | Track C verified (governor map 2026-09-26): LEAD/ATTEND path is the sanctioned initiative mechanism (SELECT/OVERRIDE pre-gen, 1500ms budget, fail-open HOLD) — exception-triggering intervention per canon, NOT over-governance. Not a duplicate of Navigator/Director (different position, strength, product). DUPLICATE* RESOLVED. |
| 2 | Gears + tenure (base/mid/frontier, 2-turn min) | `companion-runtime/.../conversational_agency.py:117-131`, `turn_executor.py` | Yes | EXPERIMENT | Model-tier routing, not behaviour; keep iff it changes outcomes vs single strong model. |
| 3 | Epistemic classifier (gemini-lite, 340 tok) | `companion-runtime/.../epistemic_policy.py` | Yes, per turn | KEEP | Cheap intent/act gate; proven pattern (classifier bakeoffs). |
| 4 | Memory compiler + Honcho packet (threshold 0.65) | `companion-runtime/adapters/honcho/client.py:151-484` | Yes, per turn | KEEP | Only semantic-recall path; needs bakeoff vs representation/context before any replacement. |
| 5 | Jev bus (8 signals, wake-only) | `rpd2/lib/ai/jev.ts`; `companion-runtime/docs/JEV_DISPATCHER_2026-09-25.md`, `policy/jev_dispatcher.py` | RPD2 live; Runtime dispatched, default off | KEEP | Track C verified OBSERVE, zero authority (code matches doc); only 3/8 signals have live wakes, rest logged headroom. Runtime Jev vs rpd2 Jev are NOT duplicates (separate instances, repos, decision points). Wire remaining signals to consumers instead of rupture-only. |
| 6 | Perception gate (shadow-only default; enforce opt-in) | `companion-runtime/.../perception_gate.py`, wired `turn_executor.py:1171-1198` | Shipped, shadow-only default since Track C patch | KEEP | Track C verified CONFIRMED over-governance: docstring claimed OBSERVE ("telemetry only") while code forced HOLD by default (opt-out). Patched: suppression now requires `PERCEPTION_GATE_ENFORCE=1`; `OFF=1` hard kill-switch; 11/11 tests. Shadow signal accumulates unchanged for validation. |
| 7 | Navigator (open-loop next-option) | `rpd2/lib/ai/trajectory-observer.ts:309-357` | Yes (RPD2 bg, post-response) | DUPLICATE* — STAYS OPEN | Track C verified: real intentional logged A/B duplication with Observer at same decision point (ledger-only evidence, never transcript). Write real but behaviourally shadow (unconsumed). Do NOT resolve by deletion; awaits cutover decision. |
| 8 | Trajectory observer (direction+rupture+guards) | `rpd2/lib/ai/trajectory-observer.ts:147-189,366-550` | Yes (RPD2 bg, wake-gated) | KEEP | Track C verified: post-response only (cannot touch served turn), wake-gated (rupture/stall/salient/scene-directive/12-turn backstop), character-identity-aware. Exception-gated SUGGEST/REFRAME — canon-consistent. DUPLICATE* RESOLVED (kept; distinct from Navigator by A/B design, not accidental). |
| 9 | Interaction observer (semantic deltas) | `rpd2/lib/ai/interaction-observer.ts:146-165 (gate), 264-335 (call)` | Gated (deterministic-signal OR suspicion-tripwire OR rupture-open+substantive>100ch OR Jev-wake override) | KEEP | Track C verified OBSERVE, header-accurate (never dialogue/plans/canon), exception-triggered pre-response. Upgrade from EXPERIMENT on this evidence. |
| 10 | Director select/none + moves bank (21, not 17) | `rpd2/lib/ai/director.ts`, `moves.ts` (21 entries verified by direct count) | Yes (RPD2, sync pre-response, trivial-skip fast path: decision 'none', no model call when no concerns) | EXPERIMENT | Union-schema commitment proven (3/9→9/9); only rpd2 mechanism with explicit autonomy-by-default code path. Move *content* product-owned. Count corrected per governor map (was 17 — verify if drift or stale count). |
| 11 | Overlays + stance registry (≤280ch, ≤3) + caps/backoffs | `test-starter/.../overlaySelector.ts`; `companion-runtime/.../overlay_selector.py` | Test-starter proven; Runtime additive | KEEP | Only anti-nag system with receipts; caps are hypotheses, mechanism is keep. |
| 12 | SessionMode (session_one ~20 / invited_discovery ~8) + beliefs (≤3) | `companion-runtime/.../session_mode.py`, `profiles/sophie_beliefs.*` | Yes | KEEP | Explicit granted authority; beliefs fenced as stances not evidence. Track C verified OVERRIDE that widens foreground room (pins frontier, bypasses Director) — canon-consistent, not silent governance. |
| 12b | Runtime-foreground substitution (rpd2→Runtime delegation) | `rpd2/lib/ai/runtime-foreground.ts`, wired `app/(chat)/api/chat/route.ts:3082-3189` | Flag-gated (allowlist `RPD2_RUNTIME_FOREGROUND`, chars elena/isabella only; default-off; hard-excluded when controlRepair) | KEEP (flagged) | Track C verified: single highest-capability mechanism found (OVERRIDE — replaces native generation entirely, falls back on failure). Flag gates only final-source substitution; Jev/observer/Control/Director still compute unconditionally. New row from governor map. |
| 12c | Control repair-mode state machine (`updateControl`) | `rpd2/lib/ai/control.ts` | Yes (RPD2, sync pre-Director) | KEEP | Track C verified SELECT, corroboration-gated (Jev alone cannot force repair) — exception-consistent by construction. Known undecided tension with active_trajectory cadence flagged, not resolved. New row from governor map. |

## Cortex state / packets (all in `synapse-cortex/src/`)

| # | Mechanism | Live? | Proposed | Why |
|---|---|---|---|---|
| 13 | Turn extractor (rules vs LLM loose+shape) + shaper + temporal grounding | Per-turn ingest | KEEP | Only lifecycle writer; narrow cutover pending credits+soak. |
| 14 | Narrow realtime gate + shadow trace | Flag-gated | EXPERIMENT | Bakeoff winner 0.929; graduate after full matrix + 7-day soak. |
| 15 | Sweeper Lane-2 (peer_search ×5 + synthesis) + 300s/10-turn/24h triggers | Debounced in-process | EXPERIMENT | Catches Lane-1 misses; make durable (cron) or accept loss on restart. |
| 16 | `attention-packet` + `handover/preview` + `candidates/query` + `handshake` + `revise-sync` (5-call fan-out) | Per-turn fetch | DUPLICATE | Replace with session snapshot + turn query; fan-out is the dumping source. |
| 17 | `/working-set`, `/session-working-set`, agenda snapshot (3.5h) | Exposed, unused by ordinary path | DORMANT | Keep snapshot; wire or retire HOT branch per convergence map. |
| 18 | CurrentMeaning + revise-sync (fail-closed) | LIVE (ledger) | KEEP | Only now-meaning holder. Track C verified: NO quiet-turn gate exists in-repo and NONE justified (Account must rewrite every turn; length-gates confuse "fine"-after-rupture with noise; canon prefers over-interpretation). Speculative gate explicitly NOT adopted. |
| 19 | Release/backgrounding-v1, first-beat, sustain/yield | LIVE | KEEP | Parity-graduated; backgrounding + sustain/yield proven. |
| 20 | Semantic relations/claims, 9-kind judge, 11 views | Pending validation | EXPERIMENT | Validate live before any consumer. |
| 21 | Easing full loop, subtraction, executability, write screens, initiative pin/sustain | Queued, not started | UNKNOWN | Do not claim; port iff behaviour cut demands. |
| 22 | Initiative tick/complete + reminders/due (exactly-once) + proactive log | Cron-driven | KEEP | Only exactly-once proactivity; clock owner undecided (open question). |
| 23 | Scene CurrentScene/epochs + runtime regex derivation | Both live, split | DUPLICATE | One truth (Cortex authority, runtime detects); unify or keep drifting. |

## Honcho reads (all fail-open)

| # | Mechanism | Live? | Proposed | Why |
|---|---|---|---|---|
| 24 | recent/search/summaries/conclusions-list (Cortex) + compiler packet (Runtime) | Per-turn | KEEP | Only semantic evidence; bakeoff vs representation/context/query before change. |
| 25 | representation / session.context / conclusions/query / peer.chat(depth) / cards / Dream | Unused by us | EXPERIMENT | Latent power we're paying for; test, don't assume. |
| 26 | Targeted evidence recruitment (`evidence_recruitment.py` + `history_provider` at reconciliation boundary, `SEMANTIC_RECRUIT_HISTORY=0` kill-switch) | IMPLEMENTED (banked) | KEEP | One bounded retrieval after local ambiguity; re-judge, single grounded winner or hold; no clarification; provenance in existing traces. First live implementation of Canon 12–13. |

## Trusted primitives (converged — not a framework)

Recent tranches converge on six primitives: ownership/agency, matter identity, evidence accumulation, confidence/uncertainty, lifecycle reconciliation, targeted evidence recruitment for self-resolution.

## Test procedure (canonical — parallel-safe since maintenance commit)

- Command: `./.venv/bin/python -m pytest tests/ -q` (433 collected). Full suite ~130s.
- `tests/conftest.py` assigns each pytest process its own `/tmp/synapse_test_<pid>_<rand>.db` and removes it at session end. Concurrent runs are isolated by construction (proven: distinct DBs per process, 433 green during a concurrent run).
- Legacy single-path `/tmp/synapse_test.db` is gone; do not reintroduce shared mutable test state.

## Orphans (writers without consumers — wire or retire, no third option)

Epistemic/domain annotations, WorkItem external checks, streaming receipts
(`effect=null`), outbox `createdAt` (uses delivery `now`), `same_as` writer,
`restated`, source-coverage telemetry. Refs: `audit-current-code-2026-09-24/REPORT.md:122-131`.

## Outright dead (keep dead)

Graphiti/FalkorDB, monolith user model, 6-pass verbatim prompts, fictional
clocks/offscreen-sim/gifts, per-fetish taxonomy, keyword-as-authority, local
Shadow Judge per-turn, summary-spine-as-truth, per-message ingest, live
startbrief blocking, lexical goodbye triggers, TTS caps, filler clips without
tool signal.
