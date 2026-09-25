# Jev reconciliation: shared dispatcher, collapsed gates, compiler contract (2026-09-25)

Status: thinking + proposal. No behaviour changed. Reconciles the convergence
map (`4fda62e`, "Jev stays RPD2-side") against the settled programme design
(Jev is shared System-1 that directly owns bounded compiler/routing
decisions). The convergence report described current placement correctly;
read as target architecture it was wrong. Corrected below.

Evidence base: RPD2 `lib/ai/jev.ts` (read in full); test-starter vnext
triage→router→overlay chain (`src/app/api/chat/route.ts`); RPD2 watcher +
domain inventory (~23 watchers, 39 compiler modules, 6 expressive domains);
bounded-LLM-call inventory across cortex/runtime/RPD2 (8 + 9 + 8 call sites);
test-starter runtime docs; synapse-v3 behavioural baseline (preserve
behaviour, redesign implementation freely).

## 1. Settled position (agreed)

- Jev is a SHARED System-1 / Tier-1 semantic dispatcher, not an RPD2-local
  wake gate and not a Cortex-only helper.
- It directly owns bounded compiler/routing decisions: gear/initiative,
  memory scope, domain/module applicability, posture/frame satisfaction,
  clarification need, burst/reasoning-depth routing.
- It replaces redundant sequential LLM routing (triage→router→overlay;
  extractor loose→shape→re-judge; epistemic→director→peripheral→reaction).
  Deeper models are for open-ended reasoning/generation, never for
  re-deciding a bounded Jev output.
- RPD2's `jev.ts` is the reference implementation and stays the RPD2-domain
  instance; the shared dispatcher is one code path with product-parameterized
  question packs (base pack + sophie pack + rpd2 pack carrying the 8
  relationship questions).

## 2. Resolution rule: wide/shallow bus vs narrow/deep probe (both stay)

The apparent overlap between a shared Jev bus and Cortex's `semantic_judge`
dissolves once stated as resolution:
- Jev answers WIDE/SHALLOW window questions (rupture? motive? scene shift?
  gear? domain applicable? burst warranted?) over last ~3 turns.
- The judge answers NARROW/DEEP matter questions (does THIS turn resolve THAT
  loop? with verbatim span) over full matter context.
- Direction of control: Jev SELECTS which deep probes run (replacing today's
  token-overlap prefilter where Jev is available); the judge CONFIRMS;
  deterministic code PROMOTES. Model understands twice at different
  resolutions; code governs once. No chain re-decides the same question.

## 3. Disposition of every sequential chain found

**Collapse into Jev (one batched call replaces two+):**
- test-starter `runTriageGate → runRouterGate → posture/overlay` (the vnext
  specimen): triage's should-route + router's posture/mood/energy/intent
  become Jev questions; deterministic overlay selector stays. Posture
  vocabularies are NOT unified (COMPANION/MOMENTUM/… vs HOLD/FOLLOW/LEAD/
  REPAIR vs gears) — map at consumers.
- Runtime `epistemic → director → peripheral → reaction` (R4→R1→R2→R5):
  Jev absorbs R2's gear decision and R5's reaction classification;
  R1 keeps intent/act ownership (conversational authority, distinct);
  R4 keeps capability routing (not semantic state). R5's determinism
  (never sustain without positive evidence) survives as CODE around Jev
  output. Expected saving: 2–3 calls on non-ordinary turns.
- Cortex extractor loose→shape stays (different resolutions: noticing vs
  typing), but downstream re-judges of the SAME classification
  (completion↔fulfils, suppression direction, open_loop↔resolves) route
  through Jev-gated probes instead of independent verdicts.

**Keep (no overlap):** R4 capability/research routing; R1 intent/act;
kernels/voice/move banks/canon stores; Cortex extractor lanes; meaning
interpreter (open-text lines, not bounded); consolidator/extractor packets;
all deterministic watchers (stall, guards, utterance-scope, output-judge —
$0, already bounded, Jev never replaces free code).

**Gate, don't run (watchers):** RPD2's expensive watchers (observer ×2 legs,
director briefing, trajectory ×3) get Jev-wake gating where missing
(director briefing is the gap: runs on substantive turns, should require
Jev deep/rupture signal + existing trivial-gate). Deterministic watchers
stay as-is; they are the Tier-1 suspicion layer, not Jev candidates.

## 4. The compiler contract (what Jev emits; what consumes it)

```python
CompilerFlags = {
  "gear": "hold|follow|lead|repair",        # owned by Jev (absorbs R2/peripheral gear)
  "initiative": "none|guide|check_in|callback",  # owned by Jev (absorbs initiative pins)
  "memory_scope": "none|targeted|broad",    # owned by Jev (absorbs memory-need triple)
  "domains": ["teaching", "sexual_expression", ...],  # owned by Jev (absorbs domain deltas)
  "posture_satisfied": True|False,          # owned by Jev (frame/posture check)
  "clarification_needed": True|False,       # owned by Jev
  "reasoning_depth": "routine|deep|burst",  # owned by Jev (burst routing)
  "foreground_model_tier": "fast|strong",   # owned by Jev (model selection)
}
```

Consumers (none re-decide; all apply budgets/policy around flags):
- working-set selector: posture default + gear hint (fallback to current
  derivation when flags absent — backwards compatible, offline-safe).
- reconciliation probe selection: Jev rupture/new-fact/scene signals add
  probe pairs alongside overlap prefilter.
- prompt compilers (runtime projector, RPD2 compiler): module on/off from
  domains + memory_scope + gear; kernels/voice/taboo ceilings stay domain-owned.
- lane decision: model TIER from Jev, lane from epistemic — separate axes.
- scheduler: initiative flag + budgets (silence still valid).

## 5. Cost discipline (the "every turn?" question, answered with numbers)

- RPD2 evidence: Jev-class call ≈300ms / ~$0.00002, recall-heavy by policy.
- Policy: Tier-1 deterministic signals (third-party mention, scene markers,
  sensitive threads, open rupture/acute state, longitudinal non-quiet) gate
  whether Jev runs; quiet turns skip entirely (pure deterministic path).
  This preserves the no-unconditional-semantic-call constraint while covering
  ~all turns that matter. Measure before tightening.
- Caps already in force stay: ≤3 judge probes/turn + trace markers (Cortex),
  1500ms peripheral timeout + perception-gate skip (runtime), wake-gating
  (RPD2 background observers).

## 6. What changes in Cortex code (when authorized — NOT this turn)

1. New `jev_dispatcher.py`: Tier-1 gate + one batched call + base/sophie/rpd2
   question packs + `CompilerFlags` output. RPD2 `jev.ts` questions become the
   rpd2 pack (port the 8 questions + thresholds as defaults, not the transport).
2. `turn_selection`: accept optional Jev flags (posture/gear default with
   fallback); unchanged otherwise. Selector stays pure and model-free.
3. Reconciliation probe selection: overlap OR Jev-signal selection.
4. `select_for_turn` output gains `compiler_flags` for prompt assemblers.
5. Runtime/RPD2 adoption is their repos' decision; Cortex exposes flags,
   never calls their compilers.

## 7. Open questions (genuine, for ChatGPT)

1. Threshold provenance: RPD2 Jev thresholds are dev-fitted n=46 and need
   refit; shared dispatcher thresholds start as copies — acceptable, or
   require a calibration harness first?
2. R1 intent/act vs Jev scene/shift signals: adjacent but distinct today.
   Merge later or hold the line permanently?
3. test-starter posture vocabulary (7 postures) vs shared 4 vs runtime gears:
   mapping table needed before any consumer migration, or migrate
   mechanics first and map later?

## 8. Destination correction (post-review, same day)

The wording "RPD2 `jev.ts` stays the RPD2-domain instance" above describes
current placement only and is WRONG as a destination. Corrected target:

```text
PRODUCT PROFILE (RPD2/Sophie/Bluum/healthcare)
= voice/persona + policy + domain/question-pack config
        ↓
COMPANION RUNTIME
= Jev/System-1 + modular compiler + attention/surfacing + bursting
+ routing + local session state + shared control mechanics
        ↓
CORTEX / shared state substrate
        ↓
ACTOR / foreground model
```

RPD2 is not a peer runtime. Its `jev.ts` is mined for the shared dispatcher
plus the rpd2 question pack, then retired — never run alongside a second
Jev. Same fate for its compiler, Control, Director, watchers, and initiative
machinery: each is a source of reusable behaviour to absorb (mechanics) or
preserve as profile content (persona, domains, ceilings, canon policy), never
a permanent peer service. One Jev path: base questions + active product
profile questions + state-dependent questions. No double routing.

Consequences for the Cortex side built so far: `PRESSURE_POLICIES` in
`session_workingset.py` and `product_profile.kind_priority` are two embryonic
halves of the product-profile concept and must unify into one config (not a
third copy); the proposed `jev_dispatcher.py` question packs ARE the profile
mechanism; story/canon FACTS remain substrate state, never profile content —
profile carries config, content, and policy, not truth.
