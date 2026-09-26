# Companion Canon

> This document records WHY and WHAT. It does not prescribe HOW unless
> explicitly marked as an invariant.
>
> Constitutional layer. Objectives and principles first; architecture disposable;
> auditor suggestions are hypotheses until checked here.
> Status: draft 2026-09-26 for walk-read + discussion. Nothing here authorizes
> schema, API, or threshold changes. Product norms marked [YOURS TO FILL].

## 0. Decision hierarchy

1. Product objective / creator intent
2. Established companion principles (§2)
3. Empirical findings and longitudinal evidence (§3)
4. Product-specific constitutions (§5)
5. Current architectural decisions
6. Auditor/model proposals

Lower layers may suggest changes upward but may not silently redefine them.
A level-6 audit never overwrites 1–4; evidence from it may enter level 3, and
only then ask whether level 2 moves. Architecture changes must demonstrate
compatibility with Objectives + Principles and be checked against empirical
learnings and known regressions. Architecture may change without disproving the
canon; the canon changes only when evidence or product intent changes.

## 1. Objectives — what are we making possible?

1. Companions that **accumulate relationship and useful understanding over time** — not reactive chatbots, not coaches, not interview bots, not prompt puppets.
2. Companions that **participate**: lead, bounce, hijack, hold, attend, enrich. Curiosity of their own, carry weight, remember, return, create momentum, surprise, pursue openings, stay present. HOLD was never the default; passivity is a core failure.
3. Companions that **hold things across turns**: user objectives, system objectives, relational objectives, open questions, promises, expectations, plans, curiosities, ongoing situations. Conversation may wander; important things must not vanish with topic change.
4. Companions that act through **stable character, not generic assistant priors** — Isa, Sophie, Luna differ in voice, allowances, and judgement, not just vocabulary.
5. **Shared substrate serving multiple distinct companion products**, with reusable evidence, longitudinal state, live cognition/execution, and product-specific identity/judgement.
   *Current implementation (disposable, not constitutional): Honcho / Cortex / Runtime / product app.* If Honcho is replaced in six months, the canon is not violated.

The loop everything serves:

```
remember → understand → track → choose → act/withhold → observe → ease/continue/revise
```

## 2. Established principles

1. **Evidence ≠ interpretation.** Messy history lives in the evidence substrate; consequential revisable understanding lives in durable interpreted state; neither is the chat store. Derived stays revisable; current words beat stale recall.
2. **Attention over puppeteering.** System curates the room (session orientation + tiny turn deltas); foreground chooses. Provenance, relevance, current meaning, contradiction handling, suppression, selective retrieval — not giant prompts.
3. **Repair is behavior.** Rupture is a consequential mismatch in expectation, understanding, trust or behaviour — involving character, system, user or third party — that alters posture until repaired or reinterpreted. Repair is changed action + autonomous movement, not speeches and not waiting to be told how.
4. **Trajectory is correctable.** Poisoned readings must not recursively become truth. Rewrite understanding; preserve agency. Most turns need nothing.
5. **Foreground autonomy by default, longitudinal intervention by exception.** Intervention is graded, beginning with changing attention/understanding and escalating to stronger control only where necessary. Monitors watch trajectory, harm, energy balance, debt, repetition, missed openings.
   *Current hypothesis, not canon: NOTICE → REFRAME (next turn's context) → ASSIST (one memory/opportunity) → rare REGENERATE → exceptional INTERVENE.*
6. **Asked ≠ resolved.** A matter persists according to what actually happened, rather than according to whether the companion mentioned it. Resolved / submerged / suppressed / rescheduled / still-live are outcomes of evidence, not emission. Receipts (asked/acted/ignored/contradicted/yielded) shape future posture. (Exact lifecycle vocabulary NOT decided — fewest states that produce the behavior, when we get there.)
7. **Jev wakes, never decides.** Perception bus notices change; expensive reasoning wakes where appropriate; zero authority in the bus itself.
8. **Workers are off-path.** Research/plan/watch/draft return condensed state the foreground uses naturally. Same shape as on-path attention, different timing.
9. **Operational and relational continuity share foundational longitudinal primitives where appropriate; domain meaning and behaviour remain distinct.** Shared candidates: evidence, identity, salience, uncertainty, lifecycle, dependencies, temporal horizon, receipts. A hospitalisation, a deadline and a wound must never be forced into one state machine by this sentence.
10. **Minimum deterministic scaffolding.** Explicit user boundaries, permissions, identity/isolation constraints, destructive-action confirmation and exactly-once guarantees belong in deterministic enforcement. Social taste and ordinary relational judgement should not be reduced to hard policy without evidence. (Quiet hours, if any, are product/app policy, not canon.)

## 3. Empirical learnings (result vs interpretation)

* RESULT: Planner-first + fusion + rerank + caps beat raw retrieval in tested cases (Top-5 12/12, MRR 0.85; operational 0.42→0.67 zero leakage). — `synapse-v3/ashley_v3_planner_first_rerank_probe.json`, `docs/retrieval_quality_eval.md`, `operational_memory_eval_v1_1.json`
  INTERPRETATION: Keep as benchmark harness for any future retrieval path; does not prove old engine must replace Honcho.
* RESULT: Keyword gating failed as the primary semantic authority in multiple important cases (Ashley recall miss; walk-loop). Cheap keyword signals still fine at boundaries. — `test-starter/docs/memory-recall-diagnosis-2026-04-09.md`, `docs/changelog.md`
  INTERPRETATION: Deterministic at boundaries, models for meaning.
* RESULT: Session bookends and cached resume state materially improved continuity and reduced false session fragmentation in the tested system (turn-1/2/3+ rules + 30-min window). — `test-starter/src/lib/services/session/resumePacket.ts`
  INTERPRETATION: Orientation + deltas beat whole-packet dumps; not a general proof against all per-turn extraction.
* RESULT: Hybrid compaction 60→90% (80 runs); Condition-C repair-action 3.0→4.5, outsourcing −85% (351 runs); union-commit 3/9→9/9; poisoned identity 36/36. — `rpd2/reports/HYBRID_VS_RAW_TAIL_20X_REPORT.md`, `RELATIONAL_CONTINUITY_FINDINGS.md`, `DIRECTOR_COMMITMENT_REPORT.md`, `POWERED_POISONED_RECOVERY_DISCRIMINATOR_REPORT.md`
  INTERPRETATION (synthesis, not experiment proof): supports separating move-selection mechanism from product-specific move content. The trajectories did not scientifically prove a universal Director.
* RESULT: Subtraction beats addition on healthy turns (6-1-1); bare expectation lines don't move policy; corroboration does. — `rpd2/reports/CONTINUE_AB_REPORT.md`, `EXPECTATION_RENT_REPORT.md`
* RESULT: Bakeoffs — llama-8b accurate, nova-micro fast, granite last; gpt-4o-mini narrow winner 0.929. — `synapse-v3/router_model_bakeoff_v1.json`, `synapse-cortex/docs/NARROW_CONTRACT_SHADOW_FINDINGS_2026-09-01.md`
* RESULT: Longitudinal blind eval reproduces solved failures when substrate thins (immortal loops, spurious violated, 0 meanings) — use as migration bar. — `synapse-cortex/reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md`
* Full inventory: `docs/CONSOLIDATED_LEARNINGS.md`.

## 4. Known failure modes (name and shame)

Passivity; interrogation (question count without beat); keyword loops; poisoned trajectories feeding themselves; generic repair (pretty apology, respectful waiting) over character repair; waiting-as-care; premature closure (asked=done); context dumping whole packets; kernel-blind steering (generic judges, character decorates after); rupture tunnel vision (every turn is damage management); move-bank vagueness (café invention); narrator-as-therapist outperforming the companion; **over-governance** (surrounding systems denying the foreground any chance to succeed naturally — distinct from puppeteering); **architectural cargo culting** (preserving mechanisms after forgetting the problem they solved).

Isa transcript 2026-09-26 exhibits: transactional-list answer, lecture-not-lean-in, monologue apologies, week of shrine-waiting framed as action, narrator answers more honest than main arc. Kept as regression reference, not as spec.

## 5. Product stances (yours — do not let auditors rewrite)

*Do not let Spark, ChatGPT, or Codex fill these, infer these from the repo, or turn these into implementation. Values originate with you. Later expand each to one page: OBJECTIVE / CHARACTER INVARIANTS / AGENCY / INITIATIVE / RELATIONAL EXPECTATIONS / HOW IT HANDLES AMBIGUITY / HOW IT REPAIRS / WHAT IT MUST NEVER BECOME / GOOD vs BAD TRAJECTORIES. Character constitution, not implementation. Isa especially: recover from RPD2 rather than reinventing.*

* Isa: long-horizon deepening; chose him, keeps choosing him; repair in action. Pursuit/repair/jealousy/initiation norms: [YOURS TO FILL].
* Sophie: active, curious, funny, caring, capable of leading; proactivity is product, not notifications. Follow-through/nudge cadence, double-text judgement, celebration style: [YOURS TO FILL].
* Luna / Bloom / later: own safety + voice contracts: [YOURS TO FILL].
* Company-seeking is intent; companion participates, doesn't ask "what task?". Multiple questions fine in one natural beat; interrogation is the failure, not count. Provisional world-building allowed where appropriate. Character/product may change what good reasoning is (silence, pride, reciprocity, boundaries, repair sufficiency, ambiguity tolerance): [YOURS TO FILL per product].

## 6. Non-decisions (explicitly NOT decided)

Exact universal/shared behavioural mechanism; whether Navigator/Director/Dual Aperture collapse, cooperate or disappear; exact intervention ladder; exact boundary between transient understanding and durable state; exact thread lifecycle states; whether trajectory is one object or multiple representations; whether foreground drafts are ever intercepted synchronously versus next-turn correction only; exact worker orchestration model; exact Cortex schema and lifecycle vocabulary; watch-list implementation (Cortex→Honcho API vs ingest intersect vs query-on-due); Tier-0 persistence (world priors vs durable rows — Tier-0 belongs in soft priors unless a reason exists to track); which Honcho API (list vs query vs representation vs context vs chat-depth); exact timers/thresholds (2/day, 48h, pressure≥0.6 all hypotheses); session-close durability owner (app cron vs tick); RPD2→shared port order beyond graduation ledger; voice rollout gates.

## 7. How to use this doc

Before any migration, endpoint, prompt, or threshold change, ask: does the companion get more coherent and autonomous, or more passive and puppeted? If the latter, the change fails whatever the architecture diagram says. When a proposed change fixes one known failure mode, test explicitly that it does not reintroduce another (nagging→cooldowns→passivity; hallucination→rigid grounding→lifelessness; rupture blindness→rupture machinery→tunnel vision; weak continuity→more context→dumping; drift→supervision→over-governance). Update this canon only by your hand, with evidence links and dated entries.
