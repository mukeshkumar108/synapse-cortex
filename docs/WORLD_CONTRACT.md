> **STATUS (2026-10-04): design history, partly superseded.** The Flash Lite producer and the conditional judge described below were replaced by the Cortex world interpreter (Luna Pro) with a mechanics-only materialiser. The as-built description is `COGNITION_ARCHITECTURE.md` Part A; the handoff is `NEXT_INSTANCE_HANDOFF.md`.

# World contract and materialiser (design, 2026-10-03; nothing here is implemented)

Status: design for review. It extends `CORTEX_ARCHITECTURE.md` (§2 actors and direction, §3 Matter, §4 epistemics, §5 authoritative vs derived,
§12 one write path); it does not replace it. Evidence behind it: the comparative replay and Honcho/ledger traces in
`companion-runtime/docs/DECISION_ARCHITECTURE.md` (Amendments B-D).

## 0. The idea in one paragraph
Several producers read conversation text; none exchanges typed state with the others. Define ONE typed interchange contract (`WorldDelta`).
Producers (the Runtime checkpoint, Honcho's interpretation, the narrow operational lane) emit typed *candidates* into it. Cortex never reads prose
to rediscover meaning: it grounds, judges, resolves identity, and **materialises** candidates into its canonical primitives, with full provenance of
which producer, model and run produced each row, so a faulty interpretation can be traced and re-derived. Honcho stays the interpretive memory and
evidence archive; the Runtime ledger stays working memory. The narrative layer lives in Cortex (stored, traceable, not re-fetched each turn).

```
raw turns ---------------------------> Honcho (evidence, summaries, deductions, dialectic)
Runtime ledger (per turn, typed) --\
Runtime checkpoint (every ~10 ex.) --+--> WorldDelta candidates --> [ground] --> [epistemic judge] --> Cortex materialiser
Honcho deductions/summaries --------/                                                                   |
narrow operational lane (reminders, completions) -- unchanged deterministic commit ----------------------+
                                                                                                         v
                          canonical primitives (authoritative) --> WorldModelSnapshot (derived) --> resident packet in Runtime
```

## 1. Semantic model and invariants
Primitives (all scoped to a Cortex **owner** = the world; see I1):
* **Actor**: stable identity that can act, be referred to, hold a perspective, or participate. Humans, companion characters, organisations/teams.
* **Matter**: something that needs continuity. Not everything is a Matter (promotion rule below).
* **Event**: something that happened; time/place/participants may be partial; need not stay active.
* **Claim**: a proposition about the world with subject, text/value, formation, holder (perspective), epistemic status, conflict/supersession.
* **Relationship**: a stateful edge between Actors with its own history; its *state* is carried by narrative claims.
* **Narrative state**: typed interpretive claims (relationship shift, trust change, disclosure/concealment, rupture/reconciliation, emotional state,
  ambiguity, perspective). Same epistemic machinery as claims; never silently hard facts.
* **Evidence**: source material (Honcho message ids, verbatim spans). Plans, commitments, expectations, routines, decisions are MEMBERS of Matters
  (or attached to Actors/Events), not new top-level objects. Project = a Matter kind. Artifact: extension point only.

Invariants:
* **I1 Owner is not Actor.** The owner answers "whose world is this Cortex?"; an Actor answers "who exists inside this world?". Audrey and Kai are Actors
  in an RPD2 world without being owners/peers. Owner validation is NOT weakened: ops about actors reference actors (subject/holder/participants),
  never claim an actor as owner. (This removes the `ungrounded_owner` rejections seen in the replay: 10 of 13 in the whole-conversation run.)
* **I2 Narration is evidence; interpretation is a candidate; canonical state requires epistemic promotion** (the existing firmness ladder:
  explicit > source_linked > reported > observed > inferred > hypothesis; a lower class never replaces a higher one, it sits beside it as `conflicting`).
* **I3 Every materialised row records its producer** (producer, model, schema/prompt version, run id, input message range). Retracting a run retracts
  its rows; `explain()` answers "why does Cortex believe this?" down to messages and the producing run.
* **I4 Perspective is never flattened.** "Audrey kissed X" / "Audrey says she kissed X" / "Kai says Audrey kissed X" / "the model inferred ..." are four
  different rows (holder + formation + status).
* **I5 Promote to a Matter only when it needs its own continuity** ("where are we with X?"). Facts are Claims, one-offs are Events, ephemeral actions
  are evidence. "I'm getting off the bus" is an Event/evidence, not a Matter.
* **I6 Resolve before create.** Candidates are grouped, then resolved against existing Matters/Actors before anything is founded. Common evidence
  (same message, same actor, same objective) is a strong *grouping signal*, never an identity rule: one message can legitimately start several
  continuities.
* **I7 Title is not identity.** A Matter has a stable id and concept (`canonical_key`), a display title that may improve, and aliases. Raw utterances
  are provenance and never become identity.
* **I8 Reads never mutate** (existing). The snapshot and projections are derived and rebuildable.
* **I9 Rhetoric is not world truth.** Self-expression, hyperbole and performance ("I'm not a good girl") are stored at most as a perspective with
  low firmness, never as a durable Claim about the world.

## 2. Mapping: primitive -> current Cortex -> gap
| Primitive | Current representation (verified in code/schema) | Gap |
|---|---|---|
| Actor | `entities` (entity_type, display_name, frame_scope, provisional, confidence), `entity_aliases`, `entity_links` (object_type/id, role, entity_id). `entity_service`: exact-alias resolution, provisional entities, naming assertions | 0 rows in production. No producer creates them (narrow lane has no subjects; Lane 2 vocabulary has no actors). Need: typed Actor candidates, promotion rule, `character` type, owner/actor separation in consolidation ops |
| Relationship | `relationship_edges` (role, effective_at, end_at, confidence, provenance) | 0 rows. Edge state lives nowhere: use narrative claims linked to both actors (via `entity_links` role `party`) |
| Claim / perspective | `model_entries` (claim, claim_kind, formation, epistemic_status, holder_actor, direction, subject_entity_id, subject_matter_id, evidence_refs_json, superseded_by_id, effective_at) + `epistemics.py` (firmness, conflict, `explain`) | Exists and is the right store. Missing: optional `predicate`/value for stable attributes, producer provenance, bulk path |
| Stable attribute ("Jasmine is a nurse") | `facts` (category, title, evidence, formation) | 0 rows. Prefer ModelEntry claim with subject actor; keep `facts` for owner-holder biography |
| Narrative state | `CLAIM_KINDS` already has `relationship_development`, `repair`, `perspective`, `pattern`, `observation`, `correction`, `decision`, `matter_summary` | Add kinds: `relationship_shift`, `trust_change`, `disclosure`, `concealment`, `rupture`, `reconciliation`, `emotional_state`, `ambiguity`, `self_expression` (the last rejected as world claim, kept only as perspective) |
| Event | none first-class (the old extractor's `event` kind landed in `facts`; 0 rows). `matters.kind=life_situation` is used as a stand-in | **New table `world_events`** (below). Participants via `entity_links(object_type='event')`; Matter membership via `matter_links(object_type='event')` |
| Matter | `matters` (canonical_key, kind, status, salience, summary_entry_id, formation, origin_*), `matter_links`, `matter_relations` (same_as etc.) | Resolution-before-creation; canonical label at founding; twins repair (backfill artifact) |
| Commitment / plan / decision | expectations, open loops, work items, commitment candidates; ledger commitments in Runtime | Typed candidate with `committer`/`to`/`tentative`; keep deterministic commit path for operational ones |
| Evidence | Honcho message ids, `evidence_refs_json`, `evidence_verbatim` | RPD2 not written to Honcho (Runtime should write); producer run link |
| Snapshot / resident | `world_model_snapshots` (version, compiled_at, fingerprints), 12 sections | Add `actors`, `relationships`, `events`, `narrative` sections, an index manifest, `covered_through` |

## 3. Reuse vs add
Reuse unchanged: Matter machinery and lifecycle, epistemics (`record_claim`, firmness, conflict, `explain`), entity resolution, matter_links, snapshot
patching, attention/agenda, the narrow operational lane, scoped apply by owner prefix.
Add (additive, no destructive migration): (a) `WorldDelta` schema + validators; (b) `world_events`; (c) new claim kinds + optional `predicate`;
(d) `produced_by` provenance (producer, model, version, run id, input range) on materialised rows (reuse `consolidation_runs` as the producer-run
ledger, adding `producer`); (e) actor-reference fields in consolidation ops (separate from owner); (f) the materialiser endpoint `POST /v1/world/delta`
returning a receipt; (g) snapshot sections + manifest + `covered_through`.

## 4. The contract (`WorldDelta`)
```jsonc
{
  "contract_version": "world-delta-v1",
  "owner": "world:rpd2:...",                       // Cortex world scope (NOT an actor)
  "source": {"producer": "runtime-checkpoint|honcho|narrow-lane", "model": "...", "version": "...", "run_id": "...",
             "input": {"session_id": "...", "message_ids": ["..."], "from": "...", "to": "..."},
             "covered_through": {"message_id": "...", "ordinal": 0}},
  "actors":        [{"ref":"a1","name":"Audrey","aliases":[], "entity_type":"character|person|organisation|team",
                     "relation_hint":"partner of a2", "explicit":true, "confidence":0.9, "evidence":["m12"]}],
  "relationships": [{"ref":"r1","actors":["a1","a2"],"type":"partners","formation":"explicit","since":null,"evidence":["m3"]}],
  "events":        [{"ref":"e1","label":"night at the hotel","kind":"encounter",
                     "when":{"start":null,"end":null,"precision":"approx","phrase":"three weeks ago"},"where":"Bristol",
                     "participants":["a1","a3"],"formation":"reported","holder":"a1","confidence":0.7,"evidence":["m14"],"supersedes":[]}],
  "claims":        [{"ref":"c1","subject":"e1","predicate":"occasion","text":"it was at a work conference","holder":"a1",
                     "formation":"reported","status":"current","conflicts_with":["c0"],"supersedes":[],
                     "temporal_scope":null,"confidence":0.8,"evidence":["m14"]}],
  "narrative":     [{"ref":"n1","kind":"trust_change","about":["r1"],"holder":"model","text":"trust deteriorated after the disclosure",
                     "formation":"inferred","confidence":0.7,"evidence":["m30","m31"]}],
  "commitments":   [{"ref":"k1","committer":"a1","to":"a2","text":"to make this right","tentative":false,"due":null,"evidence":["m44"]}],
  "matter_candidates": [{"ref":"mc1","concept":"trust-after-disclosure","display_title":"Rebuilding trust after the disclosure","kind":"relationship_thread",
                         "actors":["a1","a2"],"members":["e1","n1","k1"],"attach_to_hint":null,"evidence":["m14","m44"]}]
}
```
Rules: every item carries `evidence` (message ids) and `formation`; `holder` is an actor ref, `model` (the system's inference) or `narrator`; refs are
local to the delta and resolved to ids in the receipt; nothing in a delta can claim ownership. A candidate with no evidence is rejected.

## 5. Pipeline: candidates -> grounding -> epistemic judgement -> materialisation
1. **Producers** emit candidates. High recall, cheap, any model (the Runtime checkpoint on a flash-lite class model; Honcho deductions/summaries via a
   thin adapter; the narrow lane for operational actions). The contract must not be designed around one extractor model.
2. **Deterministic grounding/provenance repair:** spans verbatim in cited messages, message ids exist, speaker attribution corrected from message role
   (`repair_attribution` already does this in the ledger), refs resolve, duplicates by evidence collapse. Failing candidates are rejected with a reason.
3. **Epistemic judgement** (model, non-latency-sensitive, default Luna Pro; use its `:batch` variant when latency is irrelevant): explicit vs inferred,
   tentative vs real commitment, rhetoric vs claim (I9), contradiction vs mere inconsistency, speaker attribution doubts. Evidence from a manual
   experiment: Flash Lite was faster and more exhaustive but misattributed speakers, promoted rhetoric and treated relational inconsistency as factual
   contradiction; Luna Pro was less exhaustive but materially better on attribution, explicit-vs-inferred, tentative commitments and contradiction semantics.
   Luna Pro is also cheaper than the model Honcho runs today ($0.20/$1.20 vs $0.75/$4.50 per M tokens; batch variant half that).
4. **Materialisation (Cortex, deterministic):** identity resolution (below), epistemic placement (firmness ladder, supersession/conflict), Matter
   resolution, lifecycle, links, producer provenance, snapshot invalidation, receipt.

## 6. Identity and resolution
* **Actors:** normalised alias exact match within the world frame; unmatched named mention => provisional Actor; promoted when named explicitly, mentioned
  across checkpoints or given a relationship; role phrases ("my daughter") attach as aliases to the single recent matching provisional actor; no
  cross-frame auto-merge; ambiguous (>1 hit) => link nothing, queue for judgement. Companion characters are `entity_type=character`, frame = world.
* **Matters:** resolution order: (1) explicit `attach_to_hint`; (2) existing members/actors/`canonical_key` overlap; (3) a typed attach-vs-create-separate
  decision over the top-k candidate Matters (a natural System-One/Jev job; deterministic fallback = create separate); (4) found a new Matter only with a
  canonical label from the candidate (never raw text). Same message/actor/objective raise the grouping score, never force identity.
* **Events:** dedupe by (kind, participants, time window, place) plus shared evidence; a later retelling is a new *claim about* the event, not a new event.
* **Claims:** `record_claim` supersession/conflict rules, unchanged.

## 7. Resident snapshot and index (what Runtime caches)
New snapshot sections (compact stubs, never full histories): `actors` ("Jasmine - daughter; estranged; nurse; 2 active matters; last event X;
actor_ref"), `relationships`, `events` (recent + timeline index), `narrative` (current states per relationship/Matter), plus the existing sections.
A manifest `index` (names, refs, counts, `available_via` projections) supports the staged cascade: **resident stub -> targeted Cortex projection
(actor/matter/timeline) -> Honcho evidence**. The staged Jev design routes over this: Jev A (tiny every-turn gate); Jev B (only when memory is needed)
sees the manifest, not the packet, and chooses resident / targeted projection / deeper Cortex / Honcho; an optional Jev C picks among a bounded
retrieved set. Nothing large is force-fed to Jev. The snapshot also carries `covered_through` (below).

## 8. Checkpoint reconciliation (`covered_through`)
A delta states what it covers. The materialiser returns a **receipt**: `{run_id, snapshot_version, covered_through, applied/rejected counts,
refs -> ids}`. The Runtime stores the receipt in its ledger state and retires provisional items Cortex now covers (matched via the ref->id map) with
ordinal <= `covered_through`, keeping everything newer and anything Cortex rejected or cannot hold. Cortex covers Actors, Events, Claims, narrative,
commitments and Matter state; the ledger keeps the fresh edge. The resident cache refreshes when the receipt's snapshot version advances.

## 9. Acceptance tests
**Audrey (primary; the recorded transcript, scratch DB, no production writes).** Pass = the materialised world contains: Audrey and Kai as Actors;
third parties as Actors where evidence supports; an Audrey<->Kai Relationship with state; conference/party/hotel/beach-house/kiss/confession as
Events (not Matters); claims for when/where/who initiated/sequence with the **8 known conflicts preserved with holder Audrey and provenance**;
commitments/promises (tentative ones marked); narrative states (disclosure, trust change, rupture) with formation `inferred`; **no rhetoric promoted**;
Matters only where continuity warrants, each with a canonical title (not a raw utterance); every row `explain()`-able to messages and producing run.
Baselines to beat (measured today): narrow lane 0 Matters/actors; Lane 2 0 candidates; whole-conversation consolidation 30/32 `incidental`;
progressive consolidation 2 Matters, 1 expectation, 3 model entries, 0 actors.
**Sophie (grounded; second test).** A person exists with no active Matter; "Jasmine is a nurse" is a Claim about the Actor; "I'm on the bus" is an
Event, not a Matter; an assistant hallucination ("no dentist appointment") never becomes user-world truth; "Bluum" resolves to ONE project Matter
holding its decisions/tasks/events instead of many unrelated Matters; the walking example yields one Matter with goal + recurrence + commitment members.

## 10. Migration and backfill
* Schema: additive only (`world_events`, link types, claim kinds, optional `predicate`, `produced_by`, snapshot sections). The old Runtime and
  products keep working; new sections are ignored until read.
* Data: the 13 same-message twin groups (35 of 58 Matters, created by the Oct 1 cutover backfill) are repaired once by the resolver using
  `matter_relations(same_as)`/merge, reviewed before applying; loop-founded Matters with raw titles are re-labelled from checkpoint-derived
  canonical labels; Actors/Claims are populated going forward (and from Honcho's existing deductive facts as candidates, prototyped on a scratch DB first).
* Rollout: scoped by owner prefix (`world:*` first), then Sophie after a parity replay of a real day. Rollback = ignore the new sections and stop
  calling `/v1/world/delta`; canonical rows carry `produced_by`, so a bad run is retractable.

## 11. What becomes redundant (only after parity is shown on real transcripts)
For companion conversations that send checkpoints: Cortex prose readers (`turn_extractor` 3-stage, `turn_interpretation`, session reconstruction
reading raw transcript), the Lane 2 sweeper (its goal/strategy/promise vocabulary is subsumed by commitments and Matter candidates), regex cues in the
Runtime ledger (replaced by the Jev gate and epistemic judge). Kept: the narrow operational lane (deterministic reminders/completions), Matter
lifecycle, epistemics, entity resolution, snapshot/attention/agenda, Honcho (evidence + interpretive memory + dialectic).

## 12. Model policy (starting point, to be confirmed by measurement)
* Epistemic judgement and deep, non-latency-sensitive semantics: Luna Pro (`:batch` when latency is irrelevant).
* Fast, high-recall structured extraction: Flash Lite class (Runtime ledger/checkpoint).
* Fast typed decisions and routing (gate, attach-vs-create, aperture): Jev.
* Honcho's deriver/summaries/dream/dialectic: move from `gpt-5.4-mini` (OpenAI direct) to Luna Pro through OpenRouter (Honcho's model config accepts a
  base URL and key), on a dedicated OpenRouter key so its cost is visible. Validate structured-output compatibility and quality on a scratch Honcho
  against the existing `rpd2-step3-replay-*` baseline before switching production.
