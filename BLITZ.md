# BLITZ — cross-repo behavioural tracks

This file did not exist before this session. `docs/COMPANION_NORTH_STAR.md` and
`docs/COMPANION_CANON.md` also do not exist anywhere in `synapse-cortex`,
`companion-runtime`, `rpd2`, or `ash-ai` (checked: file search + `git log
--all` for the filenames, all four repos). Treated
`ash-ai/docs/COMPANION_PLATFORM_RUNTIME.md` (explicitly named by
`synapse-cortex/README.md` as "the canonical full-system handoff"),
`companion-runtime/docs/CONVERSATIONAL_AGENCY_RUNTIME.md`,
`companion-runtime/docs/PERCEPTION_CONSOLIDATION_SPEC.md`,
`rpd2/docs/AUTHORITY-CONTRACT.md`, and `synapse-cortex/docs/GRADUATION-LEDGER.md`
as the closest available canon for product intent, since they were already
being used that way by the programme (cited by each other, cited by recent
reports). **Tell the user this gap exists** before trusting any future
session's claim to have "read canon" here.

---

## Track C — Behaviour / trajectory (foreground autonomy vs longitudinal control)

Session: 2026-09-26. Scope: map only, per instruction ("if the right patch is
not obvious, mapping only is a successful session") — one small bounded change
was identified with enough confidence to ship; everything else is mapping.

### Verified facts about the repo boundary itself

- `synapse-cortex` (this repo) **does not** select HOLD/ENRICH/LEAD/ATTEND,
  gears, or the user-visible response — this is stated in its own README and
  confirmed by code: no route or function here chooses a foreground move.
  Cortex owns durable/derived state and a few pure/library functions
  (`turn_selection.select_for_turn`) that are reference implementations, not
  live endpoints called by anything traced this session.
- The **actual foreground control path** (Dual Aperture, gears, Jev, Director,
  Observer, Control, trajectory) lives in two other repos:
  `companion-runtime` (Sophie, and now Elena/Isa when foreground-bridged) and
  `rpd2` (Elena/Isa native path). Both were added read-only to this session
  (`mukeshkumar108/companion-runtime` @ `351ed35c`, `mukeshkumar108/rpd2` @
  `d553b103`) specifically because the task's named mechanisms
  (Navigator/Director/Observer/Jev/gears) do not exist in `synapse-cortex`.
  **Any future Track C session needs these two repos attached, not just
  synapse-cortex, to answer this question.**
- Prior audits in `synapse-cortex/reports/` (`control_convergence_2026-09-25`,
  `jev_reconciliation_2026-09-25`, `jev_consumer_and_reactivation_2026-09-25`)
  were the best available planning documents but were **already stale in
  places** relative to current HEAD — e.g. the convergence map's claim
  "Jev stays RPD2-side... no shared Jev" was itself superseded same-day by
  `jev_reconciliation`'s destination correction, and `companion-runtime` has
  since shipped its own `jev_dispatcher.py` (gated off by default) plus a
  separate, unrelated `perception_gate.py` shadow/wake mechanism not
  mentioned in the convergence map at all. Verified against current source,
  not re-cited from the old maps.

### Mechanism map (file + function level, code-verified this session)

Legend — Class: `KEEP` fits its job cleanly · `DUPLICATE` overlaps another
mechanism doing the same job · `EXPERIMENT` in-flight/partial rollout ·
`DORMANT` code exists, nothing live calls it · `UNKNOWN` not resolvable from
source in scope. Strength: `OBSERVE` (logs/classifies only) ·
`SUGGEST` (adds optional prompt content) · `REFRAME` (changes what
context/objective means without picking the reply) · `SELECT` (picks a
move/tier/authority block) · `OVERRIDE` (supersedes another mechanism's
choice) · `REGENERATE` (triggers a second model call on the same turn).

#### synapse-cortex (this repo)

| Mechanism | File:Function | Runs | Status | Inputs | Sees product lens? | Outputs | Can it… | Affects | Duplicate of |
|---|---|---|---|---|---|---|---|---|---|
| CurrentMeaning revise-sync | `src/routers/v1_cortex.py:930 revise_current_meaning_sync` + `src/services/current_meaning_service.py` | Every turn, called by companion-runtime's gather (unconditional, pre-this-session) | **LIVE** (graduated per `GRADUATION-LEDGER.md`) | turn_text, 6-turn local history, Cortex-owned evidence (objectives/loops/suppressions) | Yes — per-product `meaning_lens` (`resolve_lens(product)`) | `foreground_authority` (active/backgrounded/omitted) + means/unresolved lines, ephemeral per turn | inform (prompt module), mutate durable state (versioned row on genuine revision only) | Sophie (confirmed live); Elena/Isa only if/when their Cortex continuity leg is wired the same way (not confirmed this session — RPD2 agent found RPD2's own `Account` is the live interpretation store for Elena/Isa, not CurrentMeaning) | RPD2 `lib/ai/account.ts` `mergeAccountReading` — same job ("current defensible interpretation"), different store, not unified; explicitly queued but not started per `GRADUATION-LEDGER.md` |
| Session/scene working-set compiler + `select_for_turn` | `src/services/session_workingset.py`, `src/services/turn_selection.py:135 select_for_turn` | N/A — pure function / HTTP endpoints exist (`/session-working-set`, `/surfacing/report`, `/background-sweep`) | **DORMANT** for foreground selection — no call site found in companion-runtime's traced turn path (`turn_executor.py`) or rpd2's route. Docstring says it's meant to be ported and run **locally inside Runtime**, not called over HTTP per turn. | working_set dict, jev_flags (optional) | Via `product_profile.py` policy param (sophie/rpd2/healthcare) | posture (HOLD/FOLLOW/LEAD/REPAIR), compiler_flags, minimal bundle | Would select+veto+suppress if wired | None currently confirmed live | Overlaps conceptually with Dual Aperture's HOLD/ENRICH/LEAD/ATTEND and RPD2's Control mode — never reconciled |
| `jev_flags` param on `select_for_turn` | `turn_selection.py:144` | N/A (function never called with real jev_flags in production, since the function itself isn't wired) | **DORMANT** | shared-dispatcher `CompilerFlags` shape | n/a | posture default when present, else local derivation (offline-safe) | inform only, by design | none | — |

#### companion-runtime (Sophie; also Elena/Isa when foreground-bridged)

Entry point: `TurnExecutionPipeline.execute_turn`,
`companion_core/runtime/turn_executor.py:611` (~1575-line method).

| Mechanism | File:Function | Runs | Status | Inputs | Sees product lens? | Outputs | Can it… | Affects | Duplicate of |
|---|---|---|---|---|---|---|---|---|---|
| Lane decision | `lane_decision.py` `decide_turn` | Every turn | **LIVE** | epistemic classification, capability grants | n/a | `ExecutionLane` (REPLY_ONLY/RESEARCH/LIVE_DATA/READ_TOOLS) | **veto generation entirely** (the only genuine pre-model veto: non-REPLY_ONLY lanes go to `_defer_or_deny_lane`, no foreground reply produced) | all companions on this runtime | — |
| Perception-shadow sense pass | `companion_core/policy/perception_gate.py:297 run_perception_shadow` | **Every single turn, unconditionally launched** (turn_executor.py:841) — no quiet-turn/tier1 skip exists for the launch itself | **LIVE gate** on the REPLY_ONLY fast path; **SHADOW/telemetry-only** on deferred lanes. Module's own docstring ("never changes routing... telemetry only") is **false** for the fast path — doc/code mismatch confirmed by direct read. | last turns, deterministic scene/sensor signals | via product profile eligibility | `{status, aperture_gate_open, wakes, delta dims}` | **REFRAME/SELECT** — can skip Dual Aperture entirely (gate closed → forced HOLD) | Sophie (and Elena/Isa on the bridge) | Same job as RPD2's `jev.ts` wake gate and Cortex's `jev_dispatcher.py` tier1_gate — three separate "is this turn worth a semantic pass" implementations, not unified despite `jev_reconciliation.md`'s explicit "one Jev path" destination |
| Dual Aperture | `conversational_agency.py:95 evaluate_peripheral`, closure `run_dual_aperture` (turn_executor.py:1114) | Every eligible ordinary/REPLY_ONLY turn **unless** perception-gate skips it | **LIVE**, partially exception-gated (perception gate live but single-deployment/single-user rollout per `PERCEPTION_CONSOLIDATION_SPEC.md` programme log #9 — not yet fleet-wide) | literally `User N-1 / Sophie N-1 / User N` + optional Cortex handover digest | via companion profile | HOLD/ENRICH/LEAD/ATTEND + impulse + trajectory tag | **SELECT** authority block; can **trigger REGENERATE** (optional second beat, mechanism below) | Sophie confirmed; Elena/Isa native path does not use this (RPD2 has its own Director/Control instead) | Same job as RPD2's Director+Control pair — two different implementations of "decide this turn's behavioural authority," not reconciled; explicitly acknowledged in `GRADUATION-LEDGER.md`'s "queued" section |
| Jev dispatcher (companion-runtime's own) | `policy/jev_dispatcher.py` | Only if `JEV_DISPATCH_ENABLED` truthy (repo's own `.env.example` ships it **off**; prod value not verifiable from source) | **GATED**, off in checked-in config | last turns | via `jev_question_pack` per profile | `JevFlags` (gear/initiative/memory_scope/domains/posture_satisfied/clarification_needed/reasoning_need) | **SUGGEST only** — explicitly "never selects prompt modules, never chooses providers/models" (own docstring, confirmed by trace) | Sophie/Elena profiles that opt in | Same job as RPD2's `jev.ts` — not the same code, both called "Jev," genuinely separate |
| Gear/capability routing | `conversational_agency.py:134 assess_capability_need`, `:232 route_gear` | Every REPLY_ONLY turn not session-mode-owned | **LIVE**, but for Sophie specifically its output is **immediately discarded** | deterministic regex/keyword classifier (not model-based) | n/a | tier (default/mid/frontier) + tenure state | **SELECT** model tier — except for Sophie, see next row | Sophie (computed, then overridden), other companions (live) | **Self-duplicate for Sophie**: fully computed and logged into `routing_provenance` every turn, then overridden — dead work, not a behavioural risk but a cost/telemetry-confusion one |
| Sophie foreground-model freeze | `turn_executor.py:1515-1518` | Every turn, `companion_id=="sophie"`, outside session mode | **LIVE, unconditional** | env `SOPHIE_FOREGROUND_MODEL` | n/a | fixed model id | **OVERRIDE** gear's tier selection | Sophie only | overrides the row above |
| Trajectory reaction classifier (sustain/yield) | `companion_core/policy/trajectory_reaction.py:57 classify_reaction`, `gate_prior:95` | Only if a prior consumed/sustained trajectory verdict exists without release | **GATED** (state-dependent — this is the one mechanism in the whole map that is already correctly exception-only) | prior trajectory id/impulse, current turn | n/a | welcomed/neutral/redirected/refused | **OVERRIDE** (forces current-turn Dual Aperture decision to HOLD) + mutate gear sustain/release/yield state | Sophie | — |
| LIVE SITUATION proposer | `live_situation.py:72 propose_live_situation`, `:91 commit_live_situation` | Every REPLY_ONLY/READ_TOOLS/LIVE_DATA/RESEARCH turn, unconditional | **LIVE**, no pre-filter | prior committed facts | n/a | activity/location/movement/journey/currentPlan fields | mutate state **for next turn only** — code-verified it never gates/vetoes the current reply | Sophie | — |
| Prompt compiler | `sophie_prompt_builder.py build_sophie_reply_system_prompt` | Every turn | **LIVE** | typed context modules | yes (profile-selected modules) | assembled system prompt | **assemble only** — confirmed no rewrite/moderation/post-process path exists anywhere in the repo (grepped) | all | — |
| Optional second-beat regeneration | `turn_executor.py:1852-1939` | Conditional: unconsumed actionable Dual Aperture opportunity (ENRICH/LEAD/ATTEND with impulse, <3 beats) | **LIVE** | first reply + impulse | n/a | appended second beat (fresh generation, not a rewrite) | **REGENERATE** (the only same-turn second-model-call path) | Sophie | — |
| Session-mode bypass | `session_mode.py`, `turn_executor.py:962-1403` | Whenever the calling app sets `session_routing.sessionMode.active` | **LIVE** | app-set flag (decided outside this repo) | n/a | bypasses director/gears/Dual Aperture/capability assessment, pins model | **OVERRIDE** everything above | Sophie (product-level UX feature, not a longitudinal-control question) | — |
| `_decision_record` | `turn_executor.py:194` | Every turn | **LIVE** | everything decided upstream | n/a | audit projection | **OBSERVE only** — its own docstring says it is non-authoritative | all | — |
| Director / session judgment | `session_controller.py evaluate_session` | Only non-ordinary, non-session-mode turns (task/mixed/judgment-seeking) | **GATED** — correctly exception-only for its scope | turn + epistemic classification | n/a | plan consumed in prompt | **SUGGEST** | all | job overlaps RPD2's Director in name only; different trigger conditions, not reconciled |

#### rpd2 (Elena/Isa native path; bypassed when foreground-bridged, see below)

Entry point: `app/(chat)/api/chat/route.ts` `POST()` (~3600 lines).

| Mechanism | File:Function | Runs | Status | Inputs | Sees product lens? | Outputs | Can it… | Affects | Duplicate of |
|---|---|---|---|---|---|---|---|---|---|
| Jev | `lib/ai/jev.ts:96 runJevBus`, `:147 decideObserverWake` | Every turn unless `isDirectiveTurn` or `INTERACTION_OBSERVER=0` | **LIVE** | recent turns | via product-tuned thresholds | 8 probs + observer-wake bool | **SELECT** — gates whether Observer runs (fully overrides deterministic fallback trigger, positive or negative); zero authority over the reply itself | Elena/Isa native | Same job as companion-runtime's perception_gate/jev_dispatcher — three parallel sensing layers, see above |
| Observer | `lib/ai/interaction-observer.ts:146 shouldRunInteractionObserver`, `:264 observeInteraction` | Only when Jev (or deterministic fallback) wakes it | **GATED**, correctly exception-only | 10-turn window, signals, prior Account | n/a | `InteractionDelta` (emotionalLoad/rupture/account/…) | **SUGGEST/REFRAME** — feeds Control + Director inputs; explicitly forbidden from writing dialogue | Elena/Isa native | — |
| Director | `lib/ai/director.ts:318 selectDirectorInputs`, `:661 generateDirectorBriefing` | Every turn, but **deterministic no-op fast path on trivial turns** (no concerns/drift/stall/frustration/pressure → no model call) | **LIVE with a genuine exception-only fast path** | Control state, Account, eligible move set | via move bank content | one moveId (constrained to code-filtered candidates) + prose briefing | **SELECT** move + inject briefing; downstream `judgeMoveDelivery` can **REGENERATE** (one shared regen budget) if the reply doesn't deliver the selected move | Elena/Isa native | Same job as companion-runtime's Dual Aperture — two different "what should this turn do" deciders |
| Control | `lib/ai/control.ts:131 updateControl` | Every turn, unconditional, pure deterministic (no model call) | **LIVE** | whatever evidence Jev/Observer produced that turn (degrades gracefully if they didn't run) | n/a | `mode: normal\|repair` + objective/constraints/exit condition | **REFRAME** — renders `[ACTIVE OBJECTIVE]` block, restricts Director's eligible move set in repair mode; never itself picks a move | Elena/Isa native | — |
| Move bank | `lib/ai/moves.ts:55 MOVE_BANK`, `:308 eligibleMoves` | Every turn (deterministic filtering) | **LIVE** | Control/Account state | product-authored content | eligible move id list | structural constraint only, not an actor | Elena/Isa native | — |
| Trajectory (brief/ledger/time-jump/reentry) | `lib/ai/trajectory.ts` | Every turn, deterministic, no model call | **LIVE** | Account/Control history | n/a | formatted brief text | **SUGGEST**; time-jump detection feeds one regen check | Elena/Isa native | — |
| Trajectory-observer (medium-horizon) | `lib/ai/trajectory-observer.ts:366 runTrajectoryObservation`, `:121 shouldWakeTrajectory` | Background only, inside `after()` via `refreshChatContinuityState`; **own independent deterministic wake gate** (rupture/stall/salience/scene-directive/12-turn backstop) — **not** wired to Jev's wake signal at all | **GATED + BACKFILL** — never blocks or feeds the turn that triggered it; writes only affect *future* turns' Director inputs | 10+ turn window | n/a | `active_trajectory`/`rupture_state`/`action_guards` | mutate state for future turns only | Elena/Isa native | **DUPLICATE wake-gating mechanism** — this is the concrete instance of the prior audit's flagged-but-unfixed item ("RPD2's expensive watchers... get Jev-wake gating where missing"); confirmed still unfixed at current HEAD |
| Navigator | `trajectory-observer.ts:309 runNavigator` | Alongside trajectory-observer | **EVAL-ONLY / SHADOW** — explicit comment: "Shadow comparison (logged, never applied)... cutover... over days, evidence not a judgment call" | same as above | n/a | shadow verdict, logged only | **OBSERVE only**, confirmed | none live | intended eventual replacement for part of trajectory-observer, not cut over |
| Compiler | `lib/ai/compiler.ts:1272 compileSystemPrompt` | Every turn | **LIVE** | typed state | yes | assembled prompt (deterministic module order, asserted byte-identical for a trivial-turn test) | **assemble only** — `assertLiveDelivery` (L1366) only logs violations, never blocks | Elena/Isa native | — |
| Account | `lib/ai/account.ts:509 mergeAccountReading` | Written in background (`consolidator.ts`, `trajectory-observer.ts`); **read live every turn** | **LIVE** | Observer deltas, consolidation | n/a | current interpretation ("means"/"unresolved") | **REFRAME** — feeds Director's `accountMeaning` input | Elena/Isa native | Same job as Cortex's CurrentMeaning; not unified (see synapse-cortex table above) |
| **Runtime-foreground bridge** | `lib/ai/runtime-foreground.ts:81 isRuntimeForegroundEligible`, `:334 serveRuntimeForegroundTurn` | Elena/Isa only, when `RPD2_RUNTIME_FOREGROUND` allowlist (or legacy `RPD2_RUNTIME_FOREGROUND_ELENA`/`_ISA`) includes the character, `COMPANION_RUNTIME_URL`/`SECRET` set, and **not** in repair-Control mode | **GATED-LIVE** — genuinely serves the visible reply for Elena/Isa in this configuration (confirmed by `prod_deploy_2026-09-26.md`: `RPD2_RUNTIME_FOREGROUND=elena-voss,isabella-morales` set on the VPS) | RPD2's Account means/unresolved, Control mode, Director's selected move, scene facts — passed **as read-only context**, execution mode `'evaluation'` | yes (via companion-runtime's own profile handling) | reply generated by companion-runtime, not RPD2 | **OVERRIDE — redirects entire foreground ownership to a different codebase's stack** | Elena, Isa | This *is* the resolution of the Jev/Director/Observer duplication for these two characters specifically: **all** of RPD2's native post-generation regen/veto machinery (pivot-reference regen, temporal-jump regen, attribution regen, `judgeMoveDelivery` delivery regen) is bypassed on success and companion-runtime's Dual Aperture/gear/perception-gate stack governs instead — but RPD2's Jev/Observer/Director/Control still compute upstream and are merely passed through as inert context, i.e. **two full control stacks run per turn for Elena/Isa, one of which (RPD2's) has no effect on the served text.** Confirmed not a bug — `runtime-foreground.ts:13-15` frames this as deliberate rollback-safe evaluation, but it is real double compute, unresolved, on every Elena/Isa turn under this flag. |
| Runtime shadow (Elena) | `lib/runtime-shadow/shadow.ts`, `RPD2_RUNTIME_SHADOW_ELENA` | Background, `after()` | **SHADOW/EVAL-ONLY**, read-only by construction — do not conflate with the bridge above (separate flag, separate purpose: diagnostic diff only) | — | — | — | **OBSERVE only** | none | — |

### The behavioural question, answered as far as evidence supports

For Sophie (companion-runtime): the canon principle
("foreground autonomy by default, longitudinal intervention by exception") is
**mostly upheld structurally** — Dual Aperture's HOLD is restraint not
suspension of judgment, LEAD/ATTEND require a real reason, and the one
already-exception-gated mechanism in the whole map (trajectory
sustain/yield) is a template for what "by exception" looks like done right.
It is **violated on cost/attention grounds, not authority grounds**, by three
mechanisms that assume every turn needs a semantic look before the model
speaks: `revise_current_meaning_sync` (unconditional every turn — this
session's fix, below), the companion-runtime `perception_shadow` sense pass
(unconditional every turn, no tier1 skip despite Jev already having one), and
LIVE SITUATION's proposer (unconditional every turn). None of these can
override the foreground model's actual words, so the violation is "the system
assumes it needs to check" rather than "the system overrides what Sophie
says" — but constant checking is itself the pattern the canon principle warns
against, and it is the direct cause of the multi-hundred-ms per-turn tax
`PERCEPTION_CONSOLIDATION_SPEC.md` is independently trying to fix for Dual
Aperture specifically.

For Elena/Isa (rpd2, foreground-bridged): the more serious violation is
**architectural duplication, not over-intervention** — two full control
stacks (RPD2 native: Jev→Observer→Director→Control; companion-runtime:
Dual Aperture→gears) compute every turn, only one of which reaches the user.
This doesn't reduce foreground autonomy (the bridge is currently pushing
toward *more* autonomy, since it bypasses RPD2's own regen/veto layer more
often) but it is real duplicate cost and a genuine "which mechanism does the
same job" case the task asked to flag.

### Classification summary

| Mechanism | Class | Strength |
|---|---|---|
| Cortex CurrentMeaning revise-sync | KEEP (with this session's gate) | SUGGEST |
| Cortex working-set / `select_for_turn` | DORMANT | n/a |
| companion-runtime perception-shadow | DUPLICATE (3-way with Jev variants) + EXPERIMENT (partial rollout) | REFRAME/SELECT |
| companion-runtime Dual Aperture | KEEP | SELECT |
| companion-runtime Jev dispatcher | EXPERIMENT (gated off) | SUGGEST |
| companion-runtime gear routing (Sophie) | DUPLICATE (self — computed then discarded) | SELECT (vestigial) |
| companion-runtime foreground freeze (Sophie) | KEEP | OVERRIDE |
| companion-runtime trajectory sustain/yield | KEEP (model for the rest) | OVERRIDE |
| companion-runtime LIVE SITUATION | KEEP | OBSERVE (mutate-future-only) |
| companion-runtime second-beat | KEEP | REGENERATE |
| companion-runtime session-mode bypass | KEEP | OVERRIDE |
| rpd2 Jev | KEEP | SELECT (gate only) |
| rpd2 Observer | KEEP | SUGGEST/REFRAME |
| rpd2 Director | KEEP | SELECT + limited REGENERATE |
| rpd2 Control | KEEP | REFRAME |
| rpd2 trajectory-observer wake gate | DUPLICATE (unfixed, flagged in prior audit) | REFRAME (future-turn only) |
| rpd2 Navigator | EXPERIMENT (shadow) | OBSERVE |
| rpd2 Account | DUPLICATE-of-CurrentMeaning (unreconciled) | REFRAME |
| rpd2→companion-runtime foreground bridge | EXPERIMENT (gated-live) | OVERRIDE |
| rpd2 runtime-shadow | EXPERIMENT (eval-only) | OBSERVE |

### The one bounded change made this session

**What**: `synapse-cortex` gained a conservative quiet-turn gate in front of
the CurrentMeaning interpreter model call.

- `src/services/current_meaning_service.py`: new `is_quiet_turn(turn_text)` —
  true only for empty input or an exact match (after trimming trailing
  punctuation) against a closed set of pure acknowledgment/filler tokens
  (`ok`, `thanks`, `lol`, `np`, …), never a length heuristic alone, never
  matching if a `?` is present. False negatives (skipping a turn that did
  carry new meaning) are the dangerous error, so the set is deliberately
  narrow.
- `src/routers/v1_cortex.py`: `revise_current_meaning_sync` checks the gate
  (env `MEANING_QUIET_GATE_ENABLED`, default on) **before** calling
  `_cm.run_interpreter`, and short-circuits to the same fail-closed
  `unknown_omitted_due_to_interpretation_failure` outcome already used for
  interpreter-unavailable, tagged `reason: quiet_turn_gate_skip`. Flip
  `MEANING_QUIET_GATE_ENABLED=0` to restore the exact prior every-turn
  behavior — one env var, no code path deleted.
- Tests added in `tests/test_current_meaning.py`: gate matches/misses table,
  a test proving `run_interpreter` is never invoked for a quiet turn (not
  just that its result is discarded), and a test proving the flag restores
  old behavior byte-for-byte. `20 passed` in that file (2 pre-existing
  failures in the same file are unrelated DB-fixture-ordering issues,
  reproduced identically on clean HEAD before this change). Full suite:
  `144 failed, 230 passed` after vs `144 failed, 215 passed` before (same 144
  pre-existing failures reproduced on clean HEAD — a full-suite SQLite
  contention issue unrelated to this change, not touched this session).

**Why this one**: it is the cleanest instance in the whole map of "assume the
foreground needs a longitudinal check every turn" that (a) I could verify
completely in-repo, (b) has push access from this session, (c) is genuinely
reversible by one flag, and (d) does not touch any mechanism that already has
in-flight work elsewhere (`perception_shadow`'s tier1 gap is the more
consequential twin of this fix, but it lives in `companion-runtime` under an
active, partially-rolled-out programme — `PERCEPTION_CONSOLIDATION_SPEC.md`
— and copying its exact tier1-gate pattern into that repo's `perception_gate.py`
mid-rollout is exactly the kind of change that belongs to that programme's
own next log entry, not to a scoped Track C session working from read-only
access to that repo).

**Not done, and why**: did not touch `perception_shadow`'s missing tier1 gate
(companion-runtime, read-only access, active in-flight programme owns it),
did not touch the RPD2 trajectory-observer/Jev wake-gate duplication (rpd2,
read-only access, background-only so no live-turn cost), did not attempt to
unify CurrentMeaning/Account (explicitly named in the task as out of scope —
"don't redesign Honcho/Cortex retrieval," and this is the same class of
substrate merge), did not touch the Sophie gear-routing dead-work (real, but
telemetry-confusion not a behavioural-autonomy issue, and fixing it means
deciding what Sophie's model-tier policy *should* be, which is a product
decision this session has no standing to make).

### Open questions for the next Track C session

1. Is `JEV_DISPATCH_ENABLED` actually on in the companion-runtime production
   env? Not verifiable from source (`.env.example` ships it off). If on, its
   `reasoning_need` field is unused for model-tier selection anywhere traced
   this session — worth confirming intentional.
2. Is the RPD2→companion-runtime foreground bridge (`RPD2_RUNTIME_FOREGROUND`)
   intended to fully replace RPD2's native stack for Elena/Isa eventually, or
   stay dual-compute "for rollback safety" indefinitely? If the former, RPD2's
   Jev/Observer/Director/Control upstream computation for those two
   characters is waste today, not safety margin.
3. `perception_gate.py`'s own docstring should be corrected regardless of any
   other change — it currently claims universal telemetry-only behavior that
   is false on the REPLY_ONLY fast path. This is a one-line doc fix, not a
   behavioural change, and is safe for a future session to make immediately.

---

## Handoff

**State**: Track C mapping complete and verified against current HEAD in all
three repos that matter for this question (`synapse-cortex` `6da210f`,
`companion-runtime` `351ed35c`, `rpd2` `d553b103`). One bounded, flagged,
tested, reversible change shipped in `synapse-cortex` on branch
`claude/zen-archimedes-ufifxq` (not yet pushed as of this handoff — see
commit below). No changes made to `companion-runtime` or `rpd2` (read-only
access, correctly not used to push).

**Verify before extending**: re-run `python -m pytest tests/test_current_meaning.py -q`
after any future change near `revise_current_meaning_sync`; the 2 unrelated
pre-existing failures in that file and the 144 unrelated pre-existing
full-suite failures are both reproduced on clean HEAD in this session's log
above — don't chase them as regressions from this work.

**Next agent**: read this file's "Open questions" section first. Do not
re-run the full companion-runtime/rpd2 mapping — it's captured above with
file:line citations; spend budget on the three open questions or on the
`perception_shadow` tier1-gate fix in `companion-runtime` (needs push access
to that repo, which this session had only as read-only).
