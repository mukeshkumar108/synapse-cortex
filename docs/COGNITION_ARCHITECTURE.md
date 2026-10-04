# Companion cognition architecture

Two parts, kept apart on purpose (design docs have repeatedly described things that were not running):
**Part A: AS BUILT** is verified against production on 2026-10-04 (commands in `NEXT_INSTANCE_HANDOFF.md` §1).
**Part B: DESIGNED / NOT BUILT** is intent only. Nothing in Part B should be assumed to exist.

Standing rule behind all of it: **models own open-ended meaning; code owns mechanics** (see `SEMANTIC_BOUNDARY_INVENTORY.md`). Code validates, grounds,
canonicalises identity, versions, expires, caches and renders. It never decides what something means, why someone acted, whether it matters,
whether two accounts are the same event, or what a plausible way forward is.

---

# Part A: AS BUILT (production, 2026-10-04)

Deployed: Runtime `e6417f0`, Cortex `00a7a05` (docs since: `ba5ad7e` and later). Rollback: see handoff §1.

## Responsibilities

| Layer | Owns | Does not own |
|---|---|---|
| **Foreground model** (RPD2: NanoGPT less-constrained models, deliberately decoupled from the backend reasoner; Sophie: grounded chain) | Behaviour and language, from a small resident packet | Memory, state, interpretation |
| **Runtime** | Hot path, resident packet cache, latency routing, evidence hand-off, product policy from the registry (epistemic policy, per-character `relationship_objective`, default shared) | Interpretation of conversation history (it still runs its own episode ledger: see Part A "Known duplication") |
| **Jev** (typesafe, ~300ms) | Fast typed per-turn judgements (capability, model route, memory relevance, overview scope, scene change, safety, entity reference...) and the post-reply gate | Durable interpretation |
| **Cortex world interpreter** (Luna Pro by default, async, one call per checkpoint) | The semantic pass for `world:` owners: reads new evidence + current world state with ids + product policy + Honcho context, returns actors (recognised by id), relationships and directional open-vocabulary dimensions (with durability, with `supersedes`), events (incl. same_as / possibly_same_as), propositions, narrative state (open kinds), commitments, objective reconciliation (create / update / resolve by id), Matter continuity judgement, trajectory assessment for the constitutional actor, brief | Storage |
| **Cortex materialiser** | Mechanics only: evidence grounding (ids, verbatim spans), speaker-attribution repair, identity by echoed id or exact key, firmness ladder, grounded-policy downgrade of companion assertions (claims and events), provenance per run, versioning, expiry, supersession, durability promotion policy | Any meaning |
| **Cortex projections / resident snapshot** | Renders stored state: interpreter brief, objectives, directional dimensions, live trajectory note, routing manifest, `covered_through` per producer | Selecting meaning |
| **Cortex working set** | One cheap-model call (`judge`): relevance of each candidate item to the turn and the time span the user refers to; code packs under budgets | Word matching |
| **Honcho** | For `world:` owners: raw evidence store (Runtime mirrors every exchange, `observe_me=false`), embeddings/semantic search, session summaries (code-verified, see handoff), consumed by the interpreter as lower-grade context | Reasoning over `world:` evidence (disabled by config), canonical meaning |

## Live paths (verified)

**RPD2 (`world:` owners):** turn -> Jev tier-1 -> resident packet (+ continuation brief / active intent / trajectory note) -> NanoGPT foreground
-> post-reply: Runtime episode ledger extraction (gated by Jev) and Honcho evidence mirror. Every 10 turns, and at session/episode end: evidence +
registry policy go to `POST /v1/world/interpret`; the legacy Cortex `consolidate_session` reader is NOT called for these owners. Runtime probes
`POST /v1/world/version` and refreshes its cached packet when Cortex's snapshot is newer.

**Sophie (`user_*` owners):** unchanged legacy path: the app mirrors her turns to Honcho and the Cortex outbox; Cortex narrow lane (model decides,
deterministic validator grounds), 3-stage session consolidation (global apply OFF), Lane 2/sweeper (endpoint-driven; not scheduled in-process per code
inspection), turn extractor (model: `deepseek/deepseek-v4-flash`). Runtime serves her through the same resident/Jev/foreground path as RPD2.

## Policies in code (explicit, not meaning)
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
- **Two brains:** RPD2 on the interpreter, Sophie on legacy readers.
- **Runtime episode ledger** (episode_state/episode_store) still extracts claims per exchange for the "established" prompt lines and digests. It is a
  second semantic reader beside the interpreter for RPD2.
- **Cortex ingest** (turn extractor, semantic judge, current_meaning, zero-yield rescue) is still the Sophie reader and carries its own context assembly.
- **Rule-based extractor** remains as an explicit test/offline provider, not on any live path.
- **Interpreter output is new in production**: no sustained real RPD2 session has been observed through it yet.

---

# Part B: DESIGNED / NOT BUILT

- **Layer 2 convergence:** one owner per kind of meaning/state transition; Sophie on the interpreter (needs the interpreter to emit Expectations /
  OpenLoops lifecycle objects and a product decision on reminders); retire the Runtime ledger or make it a pure cache of interpreter output.
- **Staged Jev retrieval (A0-A3):** a two-stage aperture ladder. Today: depth ladder with `memory_relevance`, `overview_scope`, Cortex working set.
- **Per-stage coverage / moving frontier:** `covered_through` is keyed per producer only; evidence-ingested vs interpreted vs materialised stages are not
  separately tracked and nothing in Runtime retires state on it.
- **Unified cognition observability:** one trace explaining Jev decision -> evidence fetched -> interpreter output -> what entered Cortex -> packet
  that reached the foreground. Today: scattered metadata, debug endpoints, reports.
- **Layer 3 executive function:** attention over time, planning, initiative, action selection, tools, receipts, observation, revision.
- **Red-team recovery at scale** (identity-breaking RPD2 scenarios) and sustained-use evaluation of durability semantics.
- **Per-character constitution wording** in the registry (default text says "the user" and reaches the foreground prompt).
