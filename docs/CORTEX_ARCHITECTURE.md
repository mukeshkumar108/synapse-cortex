# Cortex Architecture

Status: Accepted architecture — implementation source of truth
Date: 2026-10-01

> This document records WHY and WHAT. `CORTEX_CUTOVER.md` records HOW (repo
> mapping, schema, sequence, results). It sits under `COMPANION_CANON.md`
> (principles 1, 11, 14, 15, 16 are load-bearing here) and does not redefine it.

## 1. Purpose

Cortex already holds the hard primitives (expectations, recurring intentions,
open loops, attention/commitment/clarification candidates, suppressions,
entities and edges, model entries, semantic claims/relations, facts, domain
annotations, current meaning, work items, derived signals, chronology and
consolidation machinery). The problem was never missing primitives. They did
not resolve into one *prepared model of the shared world*, so Runtime
rebuilt trajectory, continuity, pressure, repair and memory on every turn.

```
Evidence → authoritative Cortex primitives → shared world model
        → projections / attention → tiny Turn Working Set
        → product/runtime judgement → foreground generation
```

Cortex understands durable state and trajectory. Runtime decides what to do
about the current moment. Cortex prepares; Runtime decides.

## 2. What Cortex is a model of

An evidence-backed model of the **shared world**: actors, matters, time,
relationships, expectations, commitments, patterns, perspectives and
uncertainty. It is not a profile of the user. It also models the evolving
relationship between human and system over years.

### 2.1 Actors and direction (never flattened)

State carries *who holds it* and *which way it points*:

| Direction | Meaning | Canonical home |
|---|---|---|
| `user_to_system` | request / expectation the user places on the system | Expectation, OpenLoop (invited), CommitmentCandidate |
| `system_to_user` | commitment or owed follow-up the system holds toward the user | Expectation, CommitmentCandidate (character promise), AttentionCandidate (promise/question), WorkItem(owner=system) |
| `system_to_user` + `formation=inferred` | system's *working prediction/expectation* about the user | Expectation (inferred, system-held) |
| `shared` | unresolved human↔system repair, shared work, collaboration pattern | ModelEntry (`claim_kind=repair/relationship_development`), WorkItem |
| `user_self` | the user's own plan/intention; no system party | Expectation, RecurringIntention |
| `world` | third-party or external dependency | Expectation (external_dependency), SemanticClaim |

System-owned perspectives (thoughts, hypotheses, questions) are
`ModelEntry(claim_kind=perspective, holder_actor=system)`: explicitly
actor-owned, evidence-qualified, and **never promoted to world truth**.
Human and system ontologies are not pretended identical.

## 3. Matter

A **Matter** is something in the shared world with enough continuity to
maintain: project, topic, concern, relationship situation, goal, life
situation/event, routine, other. It is a *generic coherence layer*, not a new
ontology. Specialised primitives retain their semantics:

- Expectation owns expected-state/outcome lifecycle.
- OpenLoop owns unresolved-loop semantics.
- RecurringIntention owns recurrence.
- WorkItem owns executable planner work.
  (Matter = what is going on; Expectation/Commitment = what is expected/owed;
  WorkItem = what machinery can act on.)

A Matter owns only: kind, title, lifecycle (`active|dormant|resolved|archived`,
`first_seen`, `active_since`, `last_touched`, `resolved_at`) and inspectable
foreground/salience components. Invariants:

1. **A Matter is never session-owned.** It is scoped to workspace + the person
   whose world it is. A session/message may appear only as optional provenance
   (`origin_*`, `last_touched_session_id`). Matters outlive sessions by years.
2. **Identity before creation.** `resolve_or_create_matter()` resolves, in
   order: existing links → lineage (supersession/parent/sibling) → existing
   semantic relations → exact canonical key → linked-entity + content overlap →
   bounded semantic judgement for genuinely ambiguous cases → else create. A
   dedupe pass repairs fragments that already exist.
   One real-world matter must not fragment because many primitives mention
   it. No keyword hacks assign meaning; structured metadata, DomainAnnotation
   and semantic judgement do. Under-merging is repairable (`merge_matters`);
   over-merging corrupts, so ambiguity defaults to *not* merging.
3. **No parallel truth.** `Matter.summary_entry_id` references the current
   summary `ModelEntry`; any denormalised summary text is a reconstructable
   cache. A Matter holds no canonical narrative.
4. Matter↔Matter relations stay deliberately small: `related_to`, `part_of`,
   `depends_on`. Entity↔Matter reuses `EntityLink(object_type='matter')`.
   Primitive↔Matter is a many-to-many link (`matter_links`), because one
   expectation may belong to more than one matter and Matters must not require
   column changes on every primitive.

## 4. Epistemics

`ModelEntry` is the single epistemic/supersession machinery. It preserves:
formation class (`explicit/reported`, `source_linked`, `observed`, `inferred`,
`hypothesis`), confidence, evidence/provenance, subject, actor + direction,
supersession/revision, and status (`current|uncertain|conflicting|stale|superseded`).
`EpistemicAnnotation.provenance_type` maps into the same five classes.

A derived interpretation never silently becomes fact. Valid: "User has
repeatedly reported feeling Ashley defended her actions rather than
acknowledging hurt" (reported, evidence-linked). Invalid compression:
"Ashley is defensive." Projections surface formation and evidence with every
claim and can answer *why does Cortex believe this*.

## 5. Authoritative vs derived

- **Authoritative:** the primitives + evidence/provenance (Honcho messages stay
  canonical evidence; ModelEntry/Expectation/OpenLoop/… stay canonical state).
- **Derived (disposable, reconstructable, never truth):** WorldModel snapshots,
  AttentionState, projections, Turn Working Set, Matter salience components and
  summary cache, KnowledgeCoverage derivations, SessionEpisode summaries.
  Delete any of them and Cortex recompiles it from authoritative state.

Reads never mutate canonical state: reconciliation of primitives into Matters
is owned by mutation boundaries (sweeper, session consolidation, backfill,
explicit sync); WorldModel/projection/attention reads only rebuild disposable
derived state. No event bus, event sourcing or distributed materialised views. The repo-native
mechanism is a persisted, versioned snapshot with per-section source
fingerprints: stale sections are patched, everything is rebuildable.

## 6. WorldModel

A persisted, versioned, reconstructable representation Runtime may inspect and
cache. It is broad and compressed: person overview; relationship with system
(directional state, repair, shared work, boundaries, history); recent
(today / yesterday / recent days / significant changes); active matters by kind
(projects, concerns, topics); currently/recently salient people;
routines/patterns (declared vs observed); forward landscape (today / this week
/ later); unresolved state; uncertainty; knowledge coverage; depth index.

Invariants: not authoritative; reconstructable; **never inserted wholesale into
a prompt**; Runtime queries it and projects small fragments. A private
transient gather step is allowed internally; it must not become an exposed
mega-packet, a cache, or a prompt payload.

## 7. Projections

Views over shared Cortex state, not memory systems and not truth stores:
`person(entity)`, `matter(id)`, `timeline(subject, window)`, `today()`,
`week()`, `period(start,end)`, `unresolved()`, `recent_changes()`,
`knowledge_gaps()`, `depth()`, plus `why(object)` (provenance explanation).
Person cards, project cards and period views are projections.

## 8. AttentionState

Answers: *of everything Cortex knows, what has unusually high relevance in this
temporal window?* It is the refactored lifecycle/temporal machinery of the old
AttentionPacket (expectation windows, elapsed-unknown handling, reminder
windows, recurrence occurrences, follow-through ledger, suppression), scoped as
`immediate`, `today`, `upcoming`, `unresolved`, `review_needed`, with items
linked to Matters. Inputs include obligations/events, expectations, unresolved
outcomes, relational state, concerns, routines, patterns, curiosity and
supported repair pressure.

**Eligibility never means "mention this."** Runtime/product policy chooses
whether and how. WorldModel (what is true/known) and AttentionState (what is
unusually relevant now) are separate concepts. Handover, state_views,
candidate_moves and the session working set are retired; they were
overlapping editorial layers over the same primitives.

## 9. Salience

No single opaque emotional score. Matters expose inspectable components:
recency, frequency/reinforcement, explicit importance, temporal pressure,
unresolvedness, repeated user initiation, recent activity. Inferred emotional
significance, where present, remains an inference with confidence/evidence
(DomainAnnotation/ModelEntry), not a component. Foreground salience and
historical persistence are different: low salience never erases history.
Products may weight generic Matter kinds (ProductProfile); the components are
product-neutral.

## 10. Turn Working Set

The tiny per-turn selection (3–5 items) Runtime reads when it needs help:
chosen from AttentionState + WorldModel fragments by relevance to the current
turn, each with provenance and a pointer to the projection holding more depth.
Disposable, never canonical. Honcho/longitudinal retrieval is the bottom of the
ladder for exact quotes and obscure history, not for ordinary continuity.

## 11. Knowledge coverage / known unknowns

Cortex represents `known | partial | unknown | stale | conflicting` over a
generic hierarchical `subject_key` path (e.g. `routines/daily = partial`,
`routines/weekday_morning = unknown`, `routines/exercise = known`) — not coarse
areas, not a profile ontology. Only *useful* gaps are represented: those that
hang off something Cortex has evidence about, are registered by consolidation,
or belong to a minimal generic acquaintance frame. Missing information is never
filled to complete a profile; an `unknown` row carries no value. Gaps may feed
curiosity/attention when naturally relevant; Runtime/product policy decides
whether and how to ask. Onboarding is continuous acquaintance over the lifetime
of the relationship.

## 12. Session consolidation and the sweeper

One coherent Cortex write path. Session consolidation and the Lane-2 sweeper
write canonical state into the right primitives (new matters, matter status
changes, decisions, entity↔matter links, resolutions, patterns, hypotheses,
corrections, relationship developments, user→system and system→user
expectations, repair state). A **SessionEpisode** is a provenance-linked record
of what occurred/was detected and *references* those writes; it is not a second
store of repair state, expectations, decisions or relationship truth.

## 13. Product boundary

Cortex is product-agnostic: no Sophie/Bloom/RPD2/health-specific Matter kinds,
truth, or ontology. A Matter may carry operational, emotional and relational
dimensions at once. Product/character policy owns relevance weighting,
interpretation, expression, allowed actions, style and initiative. Shared
reality stays shared.

## 14. Acceptance (prepared-state questions)

From realistic longitudinal state, without raw Honcho retrieval:

1 who is this person · 2 what is our relationship/history · 3 what occupied
them today · 4 this week · 5 what materially changed · 6 which Matters are alive ·
7 who is currently/recently important · 8 what is unresolved · 9 what is expected
today/this week · 10 what concerns may be ongoing · 11 declared routines vs
observed patterns · 12 which topics could be naturally resumed · 13 what is
uncertain · 14 which claims are explicit/reported/observed/inferred/hypothetical ·
15 why does Cortex believe an important claim · 16 what deeper state exists ·
17 which 3–5 pieces matter for *this* turn · 18 what important things are
unknown · 19 what is partial/stale/conflicting · 20 what is useful to learn
naturally over time.

Ordinary continuity should almost never need raw Honcho retrieval (a benchmark,
not dogma). Exact quotes and deep obscure history may fall through to bounded
longitudinal retrieval (`LongitudinalRead`).
