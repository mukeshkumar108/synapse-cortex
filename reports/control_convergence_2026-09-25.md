# Control architecture convergence map (2026-09-25)

Audit-only mission: no behaviour implemented, no routes changed. Three
codebase maps were produced in parallel (their detail stands behind this
synthesis): Cortex control stack, RPD2 control machinery, companion-runtime
controls. Base: cortex `66ec6dd`.

## 0. Headline: no collision exists yet — convergence is still cheap

The new attention controller (`turn_selection`, `session_workingset`,
`surfacing`, `background_sweep`, `candidate_moves`, `state_views`,
`operational_decision`) has exactly three live writers (reconciliation, T2
maintenance, deterministic promotion) and **zero foreground consumers**.
Runtime still runs its own gather → director/peripheral → subtractive
projector; RPD2 still runs Jev → observer → Account → Control → director →
compiler. Nothing yet chooses HOLD while another chooses LEAD on the same
turn. The incoherence ChatGPT feared is a future risk, not a present bug —
which is why this map comes before the next build.

## 1. Canonical control flow (single map)

```text
EVIDENCE / CANONICAL STATE (cold, authoritative, append-only)
  Cortex durable rows (expectations/loops/commitments/attention/claims/
  relations/facts/model/suppressions) + Honcho + RPD2 canon stores
        ↓
MEANING-GATED WRITES (warm; model understands, code governs)
  semantic judge + reconciliation + grounding gates + lifecycle/operational
  writers + sweeper discovery + consolidation/demotion mechanics
        ↓
DERIVED INTELLIGENCE (cold→warm; queryable, never foreground-shaped)
  roles (0..n) + 11 independent views + unified moves + operational
  proposals (form × authority) + T2/current meaning
        ↓
WORKING-SET COMPILE (warm; disposable, versioned, fingerprinted)
  session composition (Sophie) / scene composition (RPD2) + budgets +
  suppressions/deferrals + pressure policy param
        ↓  refresh protocol (hash poll; recompile on material change)
RUNTIME-LOCAL HOT PATH (no Cortex round trip per turn)
  gate economy (deterministic windows/cooldowns/budgets; Jev probs where
  available as domain signals, never as authority)
  → per-turn select_for_turn (attention posture HOLD/FOLLOW/LEAD/REPAIR,
     dominant/combine/hold arbitration, minimal bundle)
  → conversational authority (runtime director / peripheral gear /
     RPD2 Control+director+move bank —unchanged owners, see §3)
  → subtractive projector (modules in, most left out; trace omissions)
  → actor
        ↓
REPORT-BACK (bounded batches, async)
  surfaced/ignored → cooldown bookkeeping (ignored ≠ resolved)
  answered/resolved → settle source rows + receipts
  deferred → reopenable suppression; dismissed → strong suppression
  → reconcile → fingerprint changes → refresh → background sweep diffs
BACKGROUND (cold)
  sweep eligible views → scheduler → proactive compose (silence valid)
  → prediction/action/outcome/evaluation kept separate
```

Key separations the map enforces: attention posture (which matters join
foreground) vs conversational authority (what the character does/says);
views (queryable products) vs packets (task assemblies); surfacing state
(disposable) vs semantic truth (durable); capability (form) vs permission
(authority); unknown subjects merge vs disjoint subjects never merge.

## 2. Decision ownership after convergence

| Decision | Owner | Notes |
|---|---|---|
| What is true / what happened | Cortex durable + RPD2 canon stores | one writable truth per fact; supersede never delete |
| Whether evidence settles/changes a matter | semantic judge verdict + deterministic promotion/governance | verbatim grounding required; fail-closed |
| What something currently means (T2) | CurrentMeaning versions (Cortex) | RPD2 Account merges here when parity proven |
| Which matters are eligible for attention | views + moves + working set | 0..n roles; full lists, no truncation |
| What joins this turn's foreground | runtime-local `select_for_turn` (+ gate economy) | user-first; budgets; protective override ≤1 |
| What the character does/says | runtime director / peripheral / RPD2 Control+director | unchanged authorities; consume selection as input |
| What enters the prompt | subtractive projector (runtime; RPD2 compiler discipline) | absence is a composition decision; trace omissions |
| Whether to reach out unprompted | background sweep origin + initiative ledger gate + selection admission | silence valid; stop-asking wins |
| Surfacing outcomes | report-back → SurfaceRegistry/suppressions/receipts | ignored ≠ resolved; not-now ≠ never |
| Capability routing / research depth | runtime epistemic+lane policy | never overridden by attention pressure |
| Persona/voice/kernel/scene grammar | RPD2 domain package, permanently | never migrates to shared |
| Delegated external execution | bounded workers (future) | capability ≠ permission, structurally |

## 3. Duplicate / conflict register with verdicts

**Retire (after stated condition):**
- `working_set_service` HOT/WARM compiler + `/working-set` old branch: superseded
  by session-working-set + local select; keep route for compat only. (One
  reuse kept deliberately: the `_tokens` tokenizer.)
- `AgendaSnapshot` + agenda-as-center: ranking policy moves to moves+selection;
  freeze fallback rank as safety until runtime cutover.
- Packet-as-center: strangler pattern — freeze new logic, port remaining gates
  (36h stale-open, asked-receipt filter, reminder-window machine), keep as
  debug view, retire as compiler.
- RPD2 local Account merge logic (after CurrentMeaning parity), union-selector
  (after select|none without fallback crutch), memory-slice paths and dead
  steer code (already quarantine-marked), B/C kernels.
- Runtime neutral-candidate fetch, old working-set branch, live SynapseService
  window path (after withheld-vs-surfaced parity).

**Migrate (presenter stays, gate/source swaps):**
- `followthrough.compute_admission` → `select_for_turn` (preserve
  arrival-reopen + acknowledged-this-sitting).
- Handover/handshake presenters → present over session working set
  (preserve chronology-ownership rule).
- Runtime Cortex fan-out (attention/handshake/handover/candidates) →
  session-working-set cache + refresh poll + local select; keep handshake
  re-entry + revise-sync paths.
- Runtime proactive scheduler → background-sweep origin + selection admission
  (honor empty selection = no-send).
- Runtime local surfacing state → net-new build (biggest adoption gap) +
  batched `surfacing/report`.
- RPD2 surfacing/exhaustion/debt → shared lifecycle (Cortex structurally ahead).

**Compose (shared mechanics + domain content, permanent split):**
- Jev signals → shared gating consumes `{probs, wake, reason}`; model call
  stays RPD2-side (opposite cost model to the pure selector).
- Control corroboration bars/exit conjuncts → posture-policy parameters.
- Director/judge + move bank: shared arbitration, domain bank stays.
- Initiative pins, compiler discipline, scene clock mechanics, learning
  packets, restraint doctrine ("travels without code changes").
- Initiative ledger gate: re-point agenda input to views+moves eligible set;
  share one proactive counter (duplicate budget accounting found).

**Remain (no overlap):** SurfaceRegistry, reminder executor (sole firing
authority), action projection, operational-state + lifecycle + commitment
authority + object lifecycle writers, sleep signal (+ wire to worry),
narrow-realtime experiment, router service, receipts ledger, epistemic/lane
routing, director/reciprocity/session-mode/peripheral/gear/trajectory,
prompt projector + adapters + beliefs + live_situation, revise-sync path,
persona/kernel/scene-grammar/RP banks/red-team rigs, IdempotencyStore.

**Unify (two of the same table):** `product_profile.kind_priority` +
`PRESSURE_POLICIES` → one product-policy module.

## 4. Where Jev belongs

Jev stays RPD2-side as a domain-tuned signal bus (rupture/motive/scene
questions, ~300ms, read-only, zero authority). The shared stack consumes its
signals where available but builds no shared Jev: the pure selector must stay
model-free, and gate economy covers the generic need. If a product without
Jev needs rupture signals later, that is a new explicit decision, not an
implication of this map.

## 5. RPD2 discoveries with no shared counterpart (landings assigned)

- Actor-owned agenda (fulfill-on-behaviour, never-re-express, release-on-lapse)
  → extend moves lifecycle + background sweep; not present today.
- Temporary posture + clean release (one-turn breather, rotation,
  reactivation trail) → turn_selection local-state + report-back outcomes.
- Scene executability (`his-location` filters, watching-vs-participating,
  never-canon rule) → scene composition + selection gates.
- Handled-vs-resolved dormant ladder (parked-reopens-on-signal, easing
  step-down) → surfacing outcomes + suppression reopen conditions.
- Disclosure semantics (vulnerability as signal, declarations ≠ proof,
  repair counts behaviour only) → judge kinds + promotion bar.
- Affect non-persistence (transient release channel; arousal never redefines
  identity) → T2 easing handling; no durable affect store, by decision.
- High-consequence friction (phased containment, executability grounding,
  exit bars) → protective override is step one; phasing is missing.
- Session consolidation (single-owner story writer, coverage discipline) →
  lifecycle/demotion mechanics shared; truth stores stay domain.

## 6. Genuinely missing (neither side)

Same-as writer from entity mentions; `restated` predicate; source-coverage
telemetry for observability-gated absence; CANCELLED/NOT_FULFILLED predicates
(absent by decision); no-response-gesture runtime support (runtime cannot stay
silent today); per-matter channel/daypart gating runtime-side; trajectory
objective/avoid/attempt-outcome object shared-side.

## 7. Recommended next experiment (substantial, not a ticket)

**Runtime adoption slice on Sophie:** cache session-working-set + refresh poll
+ local select_for_turn + new prompt branch, behind a parity harness on
withheld-vs-surfaced behavior (prove: useful surfaces, irrelevant stays
latent, completed stops nagging, deferred returns, user intent not hijacked,
foreground gets less-better context). Only then retire handover-preview
fan-out and old working-set branch. RPD2 port follows the same harness with
scene composition. No new ontology work until the harness is green.
