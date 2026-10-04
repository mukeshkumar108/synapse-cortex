# Companion cognition architecture

Two parts, kept apart on purpose (design docs have repeatedly described things that were not running):
**Part A: AS BUILT** is verified against production on 2026-10-04 (commands in `NEXT_INSTANCE_HANDOFF.md` §1).
**Part B: DESIGNED / NOT BUILT** is intent only. Nothing in Part B should be assumed to exist.

Standing rule behind all of it: **models own open-ended meaning; code owns mechanics** (see `SEMANTIC_BOUNDARY_INVENTORY.md`). Code validates, grounds,
canonicalises identity, versions, expires, caches and renders. It never decides what something means, why someone acted, whether it matters,
whether two accounts are the same event, or what a plausible way forward is.

---

# Part A: AS BUILT (production, 2026-10-04, after the Layer-2 protocol pass)

Deployed: Runtime `22c69db`, Cortex `b1d861c` (+ the `deferred` relabel, committed after). Rollback images: `deploy-api:pre-layer2-protocol`, `companion-runtime:pre-layer2-protocol`; live tag `companion-runtime:live-layer2-protocol`. The new Cortex tables/columns are additive.

## Responsibilities

| Layer | Owns | Does not own |
|---|---|---|
| **Foreground model** (RPD2: NanoGPT less-constrained models, deliberately decoupled from the backend reasoner; Sophie: grounded chain) | Behaviour and language, from a small resident packet | Memory, state, interpretation |
| **Runtime** | Hot path, resident packet cache, latency routing, evidence hand-off, product policy from the registry (epistemic policy, per-character `relationship_objective`, default shared) | Interpretation of conversation history (it still runs its own episode ledger: see Part A "Known duplication") |
| **Jev** (typesafe, ~300ms) | Fast typed per-turn judgements (capability, model route, memory relevance, overview scope, scene change, safety, entity reference...) and the post-reply gate | Durable interpretation |
| **Cortex world interpreter** (Luna Pro by default, async, one call per checkpoint) | The semantic pass for `world:` owners: reads new evidence + current world state with ids + product policy + Honcho context, returns actors (recognised by id), relationships and directional open-vocabulary dimensions (with durability, with `supersedes`), events (incl. same_as / possibly_same_as), propositions, narrative state (open kinds), commitments, objective reconciliation (create / update / resolve by id), Matter continuity judgement, trajectory assessment for the constitutional actor, brief | Storage |
| **Cortex interpretation protocol** (`world_interpreter.interpret`) | One transaction per pass over a world: open run (`queued`) -> cross-process **lease** (`world_leases` row + expiry) -> under the lease compute by message id what is uninterpreted (ledger = message ids of `applied` runs) -> `running` -> model -> structural cleanup (every drop recorded with a reason) -> materialise -> `applied` (before the snapshot compiles, so the resident frontier is current) | Meaning |
| **Cortex identities** (`world_identities`) | Product-supplied `user_actor` / `companion_actor` pinned to stable entities per world and injected into every delta as fixed refs `user` / `companion`. An unnamed human is a typed placeholder. A later-supplied name pins the existing actor that answers to it (no twin) | Reading identities from prose |
| **Cortex materialiser** | Mechanics only: reference resolution (a reference is a local ref OR a known id; known ids become link-by-id stubs), evidence grounding (ids, verbatim spans), speaker-attribution repair, identity by echoed id or exact key, firmness ladder, grounded-policy downgrade of companion assertions (claims and events), provenance per run, versioning, expiry, supersession, durability promotion policy (a durable reading may replace a facet of any tier; an acute/provisional one never replaces a durable one) | Any meaning |
| **Cortex projections / resident snapshot** | Renders stored state: interpreter brief, objectives, directional dimensions, live trajectory note, routing manifest, `covered_through` per producer | Selecting meaning |
| **Cortex working set** | One cheap-model call (`judge`): relevance of each candidate item to the turn and the time span the user refers to; code packs under budgets | Word matching |
| **Honcho** | For `world:` owners: raw evidence store (Runtime mirrors every exchange, `observe_me=false`), embeddings/semantic search, session summaries (code-verified, see handoff), consumed by the interpreter as lower-grade context | Reasoning over `world:` evidence (disabled by config), canonical meaning |

## Live paths (verified)

**RPD2 (`world:` owners):** turn -> Jev tier-1 (one call, small hot state; `memory_relevance`, `overview_scope` choose depth) -> resident packet
(+ continuation brief / trajectory note) + **raw window that starts at Cortex's coverage frontier** (`covered_through` of the resident snapshot, bounded) ->
NanoGPT foreground -> post-reply: Honcho evidence mirror (raw only). The Runtime episode ledger is OFF for interpreted worlds
(`WORLD_OWNERS_USE_EPISODE_LEDGER=true` restores it). Every 10 turns, and at session/episode end, Runtime offers a window of **persisted messages with real ids**
(60 at a checkpoint, the whole session at session end) plus product config (policy, constitution, `user_actor` from `trusted_user_context.user_display_name`,
`companion_actor`) to `POST /v1/world/interpret`; Cortex decides by id what is new, so overlap and redelivery are free and a failed pass is recovered by the
next (bounded by the window). Runtime probes `POST /v1/world/version` every turn and refreshes its packet when the snapshot is newer. One diagnostic surface:
`GET /v1/world/trace?workspace_id&owner` (runs, lifecycle, evidence ranges, Honcho use, kept/dropped/rejected with reasons, supersessions, state reviews,
snapshot before/after, lease) joined by owner to the `world` block in each turn's execution metadata (cortex/resident version, frontier, unabsorbed count).

**Depth ladder (A0-A3), as built:** A0 raw window + frontier; A1 resident Cortex state; A2 Cortex working set (cheap model `judge` over candidate items = the
"manifest -> aperture" decision) + Matter / overview projections; A3 Honcho semantic retrieval (last rung). Jev-A is the per-turn call; the designed separate
Jev-B is realised by the working-set judge, so no second Jev call exists.

**Sophie (`user_*` owners):** unchanged legacy path: the app mirrors her turns to Honcho and the Cortex outbox; Cortex narrow lane (model decides,
deterministic validator grounds), 3-stage session consolidation (global apply OFF), Lane 2/sweeper (endpoint-driven; not scheduled in-process per code
inspection), turn extractor (model: `deepseek/deepseek-v4-flash`). Runtime serves her through the same resident/Jev/foreground path as RPD2.

## Policies in code (explicit, not meaning)
- **State review:** the interpreter returns a verdict (`holds | superseded | resolved | unclear`) for every objective and dimension it was shown; replacement
  travels in the normal arrays; a verdict whose replacement never arrived is recorded as unapplied in the run trace, never silently treated as true or changed.
- **Ambiguity:** an unresolvable reference is stored as a narrative item of kind `ambiguous_reference` listing candidates; it is never guessed.
- **Durability:** the interpreter judges acute / provisional / durable on objectives and dimensions. Code policy: an acute or provisional facet never
  supersedes a durable one (they coexist); acute state lapses from the projection after 72h unless re-affirmed; a facet is retired only by the
  interpreter (by id) or exact identity; relationship edges are never ended by code; the constitutional objective is never writable by an objective op
  and never travels inside a delta.
- **Awareness:** "not established" unless evidence shows they do not know (prompt rule; verified in replays).
- **Grounded vs generative:** grounded products downgrade companion-only assertions (claims and events) to low-confidence hypotheses; companion
  commitments and shared acts still stand. Generative products keep invented detail as attributed canon.
- **Thresholds that are policy over model scores:** working-set relevance floor 0.2; Jev per-question thresholds; agenda fallback arithmetic; vague
  relative-phrase lapse 36h; matter activity components (measured counts and recency).

## Known duplication / weaknesses in what is built (do not paper over)
- **Two brains:** RPD2 on the interpreter, Sophie on legacy readers (plan: `SOPHIE_CONVERGENCE_PLAN.md`). Honcho's deriver/dreams still run for `user_*` owners and hold a competing representation for Sophie.
- **Cortex ingest** (turn extractor, semantic judge, current_meaning, zero-yield rescue, 3-stage consolidation) is still Sophie's reader. In production the extractor provider is `model`; the regex rule provider in `turn_extractor.py` is offline/test only.
- **Coverage is per message id and bounded by the offered window:** a failed pass is recovered only while its messages are inside the next window (checkpoint 60 messages; session end the whole session).
- **Runtime ledger ids:** worlds interpreted before this pass hold synthetic `-a` message ids in their ledger; the first window after deploy re-offers about one window under real ids (bounded overlap, handled by id recognition).
- **State shown to the interpreter is the 30 most recently updated items per kind**, not relevance-selected; very long worlds can hide old facets from review.
- **Interpreter quality is model-dependent:** the review obligation and by-id references fixed the observed stale-state failure in a real-model replay; sustained real-session behaviour is still being observed.

---

# Part B: DESIGNED / NOT BUILT

- **Sophie on the interpreter** with a typed `operational[]` output (reminders, loops, completion, routines) feeding the existing deterministic lifecycle, shadow first: `SOPHIE_CONVERGENCE_PLAN.md`. Needs two product decisions listed there.
- **Retire Cortex ingest duplication and Honcho reasoning for `user_*`** after Sophie parity.
- **Relevance-selected state for the interpreter** (today: recency-limited).
- **Per-stage coverage beyond `covered_through`** (evidence-ingested vs interpreted vs materialised are separate ledgers only for interpretation today; Honcho ingestion is idempotent but not ledgered).
- **Red-team recovery at scale** and sustained-use evaluation of durability semantics.
- **Per-character constitution wording** in the registry (default text says "the user").
- **Layer 3 executive function:** attention over time, planning, initiative, action selection, tools, receipts, observation, revision. Seam left ready: canonical world rows, commitments and Matters with ids, run/provenance ledger, `world_events`.
