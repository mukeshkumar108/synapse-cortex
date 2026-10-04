# Track C — Governor / Control Map (VERIFIED, 2026-09-26)

> Owner: Claude Code. Every row below was re-derived from current-HEAD source
> (not from other tracks' docs) via three independent code-tracing passes:
> companion-runtime, rpd2, synapse-cortex. File:line citations are exact as of
> the HEADs in the table below. Classifications: Lifecycle =
> KEEP/DELETE/DORMANT/EXPERIMENT/DUPLICATE/UNKNOWN. Control strength =
> OBSERVE/SUGGEST/REFRAME/SELECT/OVERRIDE/REGENERATE.

Verified HEADs at time of tracing: `companion-runtime 547e848`,
`rpd2 7e5167b`, `synapse-cortex 705f5a6` (canon baseline `6ae9df9` is an
ancestor of all three checkouts used).

## Central question, answered per mechanism

Canon §2.5: foreground autonomy by default, longitudinal intervention by
exception. Each row below states whether the mechanism can act on a healthy,
undisturbed turn (over-governance risk) or only on evidenced drift/harm/
one-sidedness (exception-consistent).

## companion-runtime (Sophie's path)

| Mechanism | File:Func | Lifecycle | Control | When it runs | Lens? | Durable write? | Foreground-autonomy verdict |
|---|---|---|---|---|---|---|---|
| Dual Aperture (HOLD/ENRICH/LEAD/ATTEND) | `companion_core/policy/conversational_agency.py` (`evaluate_peripheral`), `companion_core/runtime/turn_executor.py:1114-1162` (`run_dual_aperture`) | KEEP | SELECT/OVERRIDE for LEAD/ATTEND (injects `[YOU HAVE THE REINS]`/`[ATTEND]` directives, can generate an unsolicited second beat); SUGGEST/REFRAME for HOLD/ENRICH | Pre-generation, sync, 1500ms budget (`TRAJECTORY_PREGEN_TIMEOUT_MS`), fails open to HOLD on timeout | Lens-blind classifier (fixed "Sophie's Dual Aperture" system prompt); output is injected into the foreground's system prompt, so foreground sees it | Not directly (writes `next_session_state`; the actual DB persistence call site was not located in this file — flag for follow-up) | This IS the sanctioned initiative mechanism — its LEAD/ATTEND path is the exception-triggering intervention Canon calls for, not over-governance. |
| Perception gate | `companion_core/policy/perception_gate.py`, wired at `turn_executor.py:1171-1198` | **KEEP, but was silently OVERRIDE-class; patched to REFRAME/OBSERVE this session** | Docstring claims OBSERVE ("telemetry only... never changes routing"); **code was OVERRIDE by default** — it forced Dual Aperture to HOLD (`aperture_gated_skip=True`) on any turn its cheap semantic classifier scored as not matching `APERTURE_WAKES`, and this ran **unconditionally unless the operator opted out** (`PERCEPTION_GATE_OFF` default `"0"` = enforcing) | Pre-generation, async race with 500ms budget, before Dual Aperture would otherwise run | Lens-blind (generic 0..1 semantic scorer, no persona) | No | **CONFIRMED over-governance**: a cheap guess that a turn is "quiet" is not evidence of drift/harm/flatness/repetition — it is a prediction about ordinary conversational content, and it was denying the foreground's own initiative mechanism a chance to run by default. This is the bounded patch (see below). |
| Gears + tenure | `companion_core/policy/conversational_agency.py:117-333` (`gear_policy`, `assess_capability_need`, `route_gear`) | EXPERIMENT | SELECT (model tier) with an OVERRIDE branch (`stakes=="high"`/`interaction_mode=="safety"` forces frontier regardless of peripheral decision) | Sync, after Dual Aperture, before generation; `evaluate_continuation` runs after generation to set next turn's tenure (hysteresis) | Lens-blind (regex/state machine) | No (session state only, same unresolved-persistence caveat) | Model-tier routing, not a behavioral governor in the Canon sense — leave as Track A already proposed (EXPERIMENT). |
| Epistemic classifier | `companion_core/policy/epistemic_policy.py` | KEEP | SELECT/REFRAME (capability route, interaction mode, stakes) | Sync, every turn, concurrent with memory/cortex gather, 8s budget | Lens-blind | No | Runs every turn unconditionally — but it classifies *what kind of turn this is* (research need, stakes) rather than judging the relationship as failing; consistent with "curate the room," not puppeteering. |
| Jev dispatcher (companion-runtime's own, distinct from rpd2's `jev.ts`) | `companion_core/policy/jev_dispatcher.py` | KEEP (dormant by default) | REFRAME/SUGGEST (selects overlay *stance lines* rendered into the prompt; explicitly never selects prompt modules, never writes state) | Late pre-generation, sync (awaited), only when `JEV_DISPATCH_ENABLED=1` (default off) | Lens-adjacent (overlay stances are profile-authored persona material; the dispatch classifier itself is lens-blind) | No | Dormant by default; doc and code agree (unlike perception gate). Has the one length-based quiet-turn short-circuit in this repo — see below — but it is currently inert because the parent flag is off. |
| SessionMode | `companion_core/policy/session_mode.py` | KEEP | OVERRIDE (pins model to frontier, bypasses Director, hands multi-turn authority to the foreground via injected instruction text) | Sync, evaluated early, before Dual Aperture/gears | Lens-aware (injected into the same system prompt as persona) | No (session state) | Explicit, user-invoked authority handoff, not a silent governor — Canon-consistent (foreground gets *more* room, not less). |
| Overlay selector | `companion_core/policy/overlay_selector.py` | KEEP | REFRAME (≤3 profile-authored stance lines, deterministic match) | Only reached via Jev dispatcher (dormant by default) | Lens-aware (profile-authored) | No | Same status as Jev dispatcher: dormant by default, additive when live. |

### companion-runtime quiet-turn / short-message finding

One literal length-based short-circuit exists in this repo:
`jev_dispatcher.tier1_gate()` (lines 60-68) skips the Jev dispatcher call for
messages under `JEV_MIN_TEXT_CHARS` (default 40 chars) unless there is open
longitudinal state or a scene change. **This currently has zero effect**
because `JEV_DISPATCH_ENABLED` defaults off — the mechanism it gates never
runs. If that flag is ever turned on, this gate would skip semantic
dispatch for exactly the danger-case messages named in this session's brief
("ok", "thanks ❤️", "lol", "fine", "sure") — flag this for review at the
same time the flag is turned on, not before.

The Perception Gate's own wake derivation (`derive_wakes`) is **not** a raw
length check — it scores semantic dimensions (affective_load,
relational_shift, stakes, ambiguity) via a small model call — but a short,
low-drama, high-relational-value message ("thanks ❤️") can plausibly still
score low on all of `APERTURE_WAKES`'s trigger conditions (none of which are
about warmth/gratitude/opportunity, only about strain/explicitness/
memory-need/tool-need/ambiguity+stakes). The gate was built to catch
*problems*, then repurposed by default to suppress the *opportunity*
mechanism (Dual Aperture ENRICH/LEAD) on anything that isn't a problem —
this is the precise mechanism of the over-governance finding above, not a
separate issue.

No triviality/length gate exists anywhere else in companion-runtime:
epistemic classifier, Dual Aperture, perception-shadow's own model call,
memory/Honcho, and Cortex lookup all run unconditionally every turn
regardless of message length (verified by repo-wide grep for
`len(...) <`, `trivial`, `short_message`, `quiet`).

## rpd2 (Isa/Elena path)

| Mechanism | File:Func | Lifecycle | Control | When it runs | Lens? | Durable write? | Foreground-autonomy verdict |
|---|---|---|---|---|---|---|---|
| Jev bus | `lib/ai/jev.ts` (`runJevBus`, `decideObserverWake`) | KEEP | OBSERVE (confirmed: zero authority, pure classification; the doc's own "wake-only, never decides" claim holds up against the code) | Sync, before response, every turn (gated only by API-key presence + 5s timeout) | Lens-blind (deliberately excludes kernel/biography/Account/history) | No | Matches Canon principle 7 exactly ("Jev wakes, never decides"). Only 3 of 8 signals have live wake thresholds; the other 5 are logged-only telemetry today — not a problem, just headroom. |
| Navigator (`runNavigator`) | `lib/ai/trajectory-observer.ts:309-357` | **DUPLICATE\* (unresolved), partially live not fully shadow** | SUGGEST | Background, inside `after()`, post-response (does not affect the served turn) | Lens-blind (ledger-only by design — deliberately never sees raw transcript) | **Yes, partially**: `open_loops[loopKey]` is persisted whenever `navLoop.objective` is truthy, but the field is not consumed as an authoritative input anywhere else found — de facto shadow for behavior even though the write is real | Explicitly logged as an A/B shadow comparison against `observeTrajectory` (same decision point — "next direction" — different evidence sources). Not accidental duplication; a deliberate, documented experiment awaiting a cutover decision. Track A's DUPLICATE* flag is correct to leave open, not resolve by deletion. |
| Trajectory observer (`observeTrajectory`, `runTrajectoryObservation`) | `lib/ai/trajectory-observer.ts:147-189, 366-550` | KEEP | SUGGEST/REFRAME (feeds Director's `trajectoryObjective`; also writes fail-closed `action_guards`) | Background, inside `after()`, wake-gated (`shouldWakeTrajectory`: rupture/stalling/salient-keyword/scene-directive/12-turn backstop; "most turns" no-op per its own comment) | Character-identity-aware, persona-blind | Yes: `active_trajectory`, `rupture_state`, `action_guards`, `open_loops` | Runs post-response only — cannot affect the turn just served, only sets up context for the *next* turn. Exception-gated (wake conditions), not every-turn. Canon-consistent. |
| Interaction observer (`observeInteraction`) | `lib/ai/interaction-observer.ts:146-165 (gate), 264-335 (call)` | KEEP | OBSERVE (file's own header: never generates dialogue/plans/canon) | Sync, before response, gated on deterministic-signal OR suspicion-tripwire OR (rupture-open AND substantive>100 chars) OR Jev-wake (Jev wake overrides a negative deterministic result outright) | Character-aware but role-blind (reads name, doesn't perform voice) | No directly (caller writes `interaction_impact`) | Confirmed exactly matches the brief's suspected gating (`ruptureOpen && substantive`). Exception-triggered, not every-turn — Canon-consistent. |
| Director (`selectDirectorInputs`, `generateDirectorBriefing`, `judgeMoveDelivery`) | `lib/ai/director.ts`, `lib/ai/moves.ts` | EXPERIMENT | SELECT + REFRAME (chooses a moveId from a bounded set; briefing text reframes the foreground's generation) | Sync, before response, but with a **trivial-skip fast path**: when there are no concerns/drift/stall/charged-scope/frustration/pressure, it returns `decision:'none'` with **no model call at all** ("ordinary moments stay uncluttered") | Most lens-aware mechanism in the map — directly shapes injected prose | No (pure computation; caller persists diagnostics) | This is the one rpd2 mechanism that already implements "foreground autonomy by default, exception escalates" as an explicit code path, not just a policy statement. **Correction to Track A inventory: MOVE_BANK has 21 entries at current HEAD, not 17** (verified via direct count in `moves.ts`). |
| Runtime-foreground substitution | `lib/ai/runtime-foreground.ts` (`isRuntimeForegroundEligible`), wired at `app/(chat)/api/chat/route.ts:3082-3189` | KEEP (flagged, allowlisted) | **OVERRIDE — the single highest-capability mechanism found in either repo.** When eligible, it replaces the entire native-model generation with a call to the external companion-runtime service and serves that text directly, skipping the native `modelCandidates` loop entirely. Falls back to native on any Runtime failure (soft REGENERATE-adjacent). | Sync, attempted first, before native generation | N/A — it delegates to a different generation source's own lens (companion-runtime's Sophie/character prompt) | No (route.ts persists the served message as usual afterward) | Gated by `RPD2_RUNTIME_FOREGROUND` (comma-separated character allowlist, takes precedence) or legacy per-character flags `RPD2_RUNTIME_FOREGROUND_ISA`/`_ELENA` (`==='1'`), both requiring `COMPANION_RUNTIME_URL`+`COMPANION_RUNTIME_SECRET` configured, restricted to `{elena-voss, isabella-morales}`, and **hard-excluded whenever `controlRepair` is true** ("rupture/repair turns are never eligible" — the one place in rpd2 where the control stack itself vetoes the override). Default-off (empty allowlist + unset per-character flags). This is an rpd2-owned flag that gates rpd2→companion-runtime delegation; it does **not** exist in companion-runtime, and nothing in rpd2 gates the surrounding Jev/interaction-observer/Control/Director stack behind it — that stack runs unconditionally (subject to its own internal wake-gates) regardless of this flag's state. |
| Control (`updateControl`) | `lib/ai/control.ts` | KEEP | SELECT (repair-mode entry/exit) | Sync, before Director, consumes Jev's `jevRupture` scalar + interaction-observer's `observerConfirmed`/`impactLevel` as corroborating evidence before entering repair mode | N/A (state machine) | Not directly traced in this pass (route.ts persists `control`) | Corroboration-gated (Jev alone cannot force repair mode) — exception-consistent by construction. Its own header already flags the `active_trajectory` cadence-vs-Control overlap as a known, undecided tension (not accidental duplication). |

### rpd2 turn-lifecycle order (verified, `route.ts`)

Jev bus → interaction-observer gate/run → Account merge → `updateControl` →
`selectDirectorInputs` → `generateDirectorBriefing` → **runtime-foreground
attempt (OVERRIDE point, returns here if eligible+successful)** → native
model-candidates loop (only if runtime-foreground was ineligible/failed) →
response served → `after()`: register-repair, `runTrajectoryObservation`
(→ Navigator), relational-learning extraction, thread-account write. No
mechanism other than runtime-foreground touches the served reply text
itself; everything else shapes upstream inputs or runs strictly after the
response.

**"17 moves" correction**: Track A's inventory (row #10) states 17 moves;
current HEAD has 21 (`lib/ai/moves.ts`). Recommend Track A verify whether
this is drift since the inventory was written or a stale count.

## synapse-cortex (this repo)

| Mechanism | File:Func | Lifecycle | Control | Gating | Durable write? | Foreground-autonomy verdict |
|---|---|---|---|---|---|---|
| CurrentMeaning + revise-sync | `src/routers/v1_cortex.py:930`, `src/services/current_meaning_service.py` | KEEP | REFRAME/SELECT | **None pre-LLM-call** — runs unconditionally on every invocation regardless of `turn_text` length/content; the only branches (`raw is None`, `no_change`) happen after the model call | Yes — `commit_revision()` inserts a new `CurrentMeaning` row under CAS + advisory lock | No quiet-turn gate exists, and **none is justified**: this is the single "what does the conversation currently mean" holder (RPD2 lesson: Account must rewrite every turn, not accumulate) — see explicit recommendation below. |
| Attention packet compiler | `src/services/cortex_packet_service.py:56` (`compile_attention_packet`) | KEEP | OBSERVE, but with real write side-effects | None (runs whenever endpoint invoked) | Yes — 4 distinct write paths confirmed inside a nominal "read": suppression expiry (88-100), attention-candidate expiry (326-345), daily-occurrence creation (443-461), surface-cooldown/clarification-dismissal (941-1033) | Not a move-selector; the writes are ledger bookkeeping (expiry, cooldowns) triggered as a side effect of compiling context, not behavioral steering. Track A/B's characterization stands verified. |
| `/route`, `/working-set`, `/session-working-set` | `src/routers/v1_cortex.py:829, 290, 355` | DORMANT (on ordinary path) | OBSERVE | `/route` has the repo's only other triviality regex (`^(lol|haha|hey|hello|hi|...|thanks|ok|okay)[.!?]*$` → `NO_RETRIEVAL`), but has no internal caller anywhere in `src/` — confirmed exposed-but-unwired from this side | `/working-set`/`/session-working-set` inherit §2's writes when called | Confirms Track B's "dormant on ordinary path" claim from this repo's side (cannot see companion-runtime's call graph, but nothing in this repo's own code calls these three). |
| Scene / CurrentScene | `src/services/scene_state.py`, `/scene/*` endpoints | KEEP | OBSERVE/SUGGEST | Deterministic authority-ranked merge (`user_explicit(3) > external_event(2) > model_inferred(1) > default(0)`), "nothing here reads prose semantically" | Yes (`CurrentScene`/`SceneEpoch`, fail-open) | Supplies context to handover/working-set; does not itself select a move. Any move-selection use of scene data happens downstream in companion-runtime, outside this repo. |
| "Release/backgrounding-v1, first-beat, sustain/yield" (Track A inventory row #19) | — | **NOT FOUND** | — | — | — | **Inventory error to flag**: exhaustive grep for `backgrounding`, `first_beat`, `sustain`, `release_v1`, `\byield\b` in `src/` found nothing matching this description (only unrelated Python generator `yield` statements and prose). The only "backgrounding" concept in this repo is the unrelated `foreground_authority: "backgrounded"` enum value inside CurrentMeaning. Recommend Track A re-locate this mechanism (likely companion-runtime or rpd2) or mark the row unverifiable-in-Cortex. |

### synapse-cortex correction to Track A doc

Track A's inventory claims "Meaning timeout: code default 1.5s; production
tuned to 12s." Current code does not support this: `MEANING_TIMEOUT_SECONDS`
(`current_meaning_service.py:53`) defaults to **12**, not 1.5, and is
dead/unused (defined once, never read elsewhere). The timeout that actually
bounds the interpreter's LLM call is `AGENDA_RANKER_TIMEOUT_SECONDS`
(`src/runtime_model.py:39`, also default 12). No occurrence of `1.5` exists
anywhere in `src/`. Flag as stale/inaccurate rather than asserting what the
number used to be.

Also flagged (not fixed — out of Track C's mandate): `v1_cortex.py:1001-1003`
normalizes any invalid/missing `foreground_authority` value to `"active"` in
both branches of a ternary that reads as though it should distinguish
`"active"` from `"backgrounded"` — looks like a bug, left for the owning
track to confirm intent before touching.

### synapse-cortex quiet-turn finding

No quiet-turn/triviality gate exists anywhere in this repo that skips
CurrentMeaning revise-sync or attention-packet compilation. The repo's only
two triviality-style checks are `/route`'s short-banter regex (unwired
internally) and an unrelated length gate inside semantic reconciliation
(`semantic_reconciliation.py:98`, a different mechanism — zero-yield-turn
rescue, not CurrentMeaning/attention gating).

## The prior cloud session's hypotheses — verified

1. "Some companion-runtime paths already behave exception-first" — TRUE:
   Director's trivial-skip fast path (rpd2) and Trajectory observer's
   wake-gating (rpd2) are both genuine exception-first mechanisms already in
   production, not hypothetical.
2. "`revise_current_meaning_sync`, `perception_shadow`, and a LIVE SITUATION
   proposer may run every turn" — PARTIALLY TRUE: `revise_current_meaning_sync`
   runs whenever called (no internal gate) but is a synapse-cortex *endpoint*,
   not a per-turn automatic call from this repo's side — whether
   companion-runtime calls it every turn is outside this repo's visibility.
   `run_perception_shadow` is launched unconditionally every eligible turn in
   companion-runtime — TRUE, confirmed. Did not independently identify a
   distinct "LIVE SITUATION proposer" by that name; Dual Aperture's
   opportunity/second-beat mechanism is the closest match found.
3. "RPD2 Jev/Observer/Director/Control and Runtime Dual Aperture/gears may
   duplicate some work" — PARTIALLY TRUE, with nuance: Navigator vs
   Trajectory-observer is a real, intentional, logged A/B duplication
   (§ rpd2 table). Jev (rpd2) vs Perception Gate (companion-runtime) are
   *not* duplicates of each other — they are separate cheap-wake-classifier
   instances in two different repos/products, structurally analogous but not
   the same code path or decision point.
4. "Under `RPD2_RUNTIME_FOREGROUND`, the RPD2 control stack may still compute
   while not affecting served output" — TRUE, confirmed exactly: the flag
   gates only the final-generation-source substitution; Jev/interaction-
   observer/Control/Director/trajectory-observer all run unconditionally
   (subject to their own wake-gates) regardless of this flag.
5. "`perception_gate.py` documentation may disagree with actual live gating
   behaviour" — **TRUE, and this is the most consequential finding in this
   map.** The module's own docstring and its test file's docstring both claim
   "telemetry only, never changes routing" while the wired code suppressed
   Dual Aperture by default. See patch below.

## Quiet-turn gate for CurrentMeaning — first-principles verdict

**Not justified. Do not port the prior cloud session's speculative patch.**
Reasoning:
- No evidence was found that CurrentMeaning revise-sync causes measurable
  harm, cost, or latency problems on trivial turns severe enough to warrant
  gating — Track A/B's own evidence treats CurrentMeaning as the "only
  now-meaning holder" (inventory row #18, KEEP) and the RPD2 archaeology doc
  identifies "Account must be rewritten every turn, not accumulated" as a
  hard-won lesson, not an optional-per-turn one.
- The brief's own danger case is real and demonstrated in this repo's
  neighbor: a length/triviality-based gate applied to a *different*
  mechanism (companion-runtime's `tier1_gate`, 40 chars) would treat "ok",
  "thanks ❤️", "lol", "fine", "sure" identically to true noise, when several
  of these carry real relational weight depending on trajectory (a "fine"
  after a rupture is not the same signal as a "fine" mid-banter). The same
  risk would attach to any length-based CurrentMeaning gate.
- Canon's own instruction is explicit: "Prefer unnecessary interpretation
  over suppressing meaningful interpretation." Absent concrete evidence of
  harm, the correct action is no action.

## The bounded patch made this session

**File**: `companion-runtime/companion_core/runtime/turn_executor.py`
(lines ~1201-1223) + `companion-runtime/tests/test_perception_gate.py`.

**Change**: Perception Gate's suppression of Dual Aperture (forcing HOLD by
default on any turn its cheap classifier didn't recognize as a "wake"
pattern) now requires an explicit `PERCEPTION_GATE_ENFORCE=1` opt-in. Default
behavior: the shadow pass still runs and logs identically on every eligible
turn (`aperture_gate_open`, `wakes`, `perception_shadow_ms` — nothing
removed), but it no longer sets `aperture_gated_skip` or forces
`peripheral={"decision":"HOLD", ...}` by default. `PERCEPTION_GATE_OFF=1`
remains a hard kill-switch even if enforcement is later turned back on.

This is exactly the code/docstring contradiction described in
`perception_gate.py`'s own header ("telemetry only... never changes
routing") — the patch makes the code match its own documented contract, and
matches Canon §2.5 (foreground autonomy by default). It is a one-flag flip
(reversible: set `PERCEPTION_GATE_ENFORCE=1` to restore prior behavior for
controlled A/B), touches no other mechanism, and does not remove any
longitudinal observation — the shadow signal keeps accumulating exactly as
before for whoever wants to validate it before turning enforcement back on.

Tests: `tests/test_perception_gate.py` — 11/11 pass, including a new
`test_default_is_shadow_only_quiet_turn_still_runs_aperture` proving the new
default, and `test_kill_switch_overrides_enforce_flag` proving the hard
kill-switch still wins. Full `companion-runtime` suite: 321 passed, 14
failed/11 errored — all pre-existing on `main` before this patch (verified
via `git stash`/re-run): Postgres-dependent lease-fencing tests
(`psycopg.OperationalError`, no local Postgres), one pre-existing parity
fixture mismatch (`test_parity_fixtures.py`), one pre-existing memory
hot-path fixture mismatch, and one pre-existing v3-control-loop call-count
assertion (`test_social_agency_v3.py`) that already failed on unmodified
`main`. Zero regressions attributable to this patch.
