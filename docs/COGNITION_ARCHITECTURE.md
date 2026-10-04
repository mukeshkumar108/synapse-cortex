# Companion cognition architecture (as built and live for `world:` owners, 2026-10-04)

Principle: **models own open-ended meaning; code owns mechanics.** Code validates, grounds, canonicalises identity, versions, expires, caches and
renders. It never decides what something means, why someone acted, whether it matters, whether two accounts are the same event, or what a
plausible way forward is. (Audit: `SEMANTIC_BOUNDARY_INVENTORY.md`. Rule saved as a standing constraint.)

## Responsibilities

| Layer | Owns | Does not own |
|---|---|---|
| **Foreground model** (RPD2: NanoGPT less-constrained models; Sophie: grounded chain) | Behaviour and language, from a small resident packet | Memory, state, interpretation |
| **Runtime** | Hot path, resident packet cache, latency routing, evidence hand-off, product policy from the registry (epistemic policy, per-character constitutional orientation) | Any semantic interpretation of conversation history |
| **Jev** (typesafe, ~300ms) | Fast typed judgements per turn (memory need, overview scope, scene change, safety, ...) and the post-reply gate | Durable interpretation |
| **Cortex world interpreter** (Luna Pro by default, async, one call per checkpoint) | The semantic pass: reads new evidence + current world state with ids + product policy; returns actors, relationships and **directional open-vocabulary dimensions**, events (incl. same_as / possibly_same_as against known events), propositions, narrative state (open kinds), commitments, **objective reconciliation** (create / update / resolve by id), **Matter continuity judgement**, **trajectory assessment** for the companion character, and the **brief** | Storage |
| **Cortex materialiser** | Mechanics only: evidence grounding (ids, verbatim spans), speaker attribution repair, identity by echoed id or exact key, firmness ladder (a weaker candidate never replaces a firmer one), grounded-policy downgrade of companion assertions, provenance per run, versioning, expiry, supersession | Any meaning |
| **Cortex projections / resident snapshot** | Renders stored state: brief (the interpreter's text), objectives, directional dimensions, trajectory note, routing manifest, `covered_through` per producer | Selecting meaning |
| **Honcho** | Raw evidence store and long-horizon retrieval. For `world:` owners Runtime writes every exchange (`observe_me=false`: stored, embedded, searchable, summarised, **never reasoned over**); the interpreter reads its session summaries and semantic search as lower-grade context. Honcho is not a second semantic author for these worlds. Peer ids are encoded (`honcho_peer_id`) because Honcho rejects `:`. | A second interpreter |

## Semantic ownership (decided)
Honcho = evidence store + retrieval. Cortex interpreter = the single canonical semantic author at checkpoints. Jev = fast per-turn typed judgements.
For `world:` owners the legacy Cortex consolidation reader is retired (the interpreter replaces it at checkpoints and session ends). Sophie
(`user_*` owners) keeps the legacy readers (narrow lane, 3-stage consolidation) because the interpreter does not yet emit Expectations/OpenLoops
lifecycle objects; converging them is the next step and needs a product decision about her reminder semantics.

## Durability and promotion policy
The interpreter judges `durability` (acute / provisional / durable) on objectives and dimensions. Explicit code policy over that judgement: an
acute or provisional facet never supersedes a durable one (they coexist), acute state lapses from the projection after 72h unless re-affirmed,
a facet is only retired when the interpreter says so by id (`supersedes`) or by exact identity, relationship edges are never ended by code, the
constitutional objective is never writable. A chaotic foreground turn is therefore preserved as an event and as acute state, and only sustained
evidence becomes durable.

## Flow
1. Every turn: Runtime serves from the resident packet (brief + what each person is trying to do + trajectory note + manifest), Jev decides routing.
2. Every N turns for `world:` owners (checkpoint): Runtime sends the evidence stretch + registry policy/constitution to `POST /v1/world/interpret`.
3. Cortex builds the current-world prompt, one Luna Pro call, tolerant structural validation, materialise, compile snapshot, return a receipt.
4. Runtime probes `POST /v1/world/version` (cheap) and refreshes the cached packet when Cortex's snapshot is newer than the one it holds.

## Invariants kept
Canonicalise identity, never perspective (directional dimensions; conflicting accounts coexist; `possible_same_as` not merges). The
constitutional orientation is product configuration from the registry, never extracted from dialogue, never writable by an objective op. The
trajectory note is an expiring, evidence-linked **interpretation**, not a fact or a script. Contradictions from a less constrained foreground are
recorded as conflicts, never silently resolved.

## Switches
`WORLD_INTERPRETATION_ENABLED` (Runtime; **on in production since 2026-10-04**), `WORLD_EVIDENCE_MIRROR_ENABLED` (on), `WORLD_INTERPRETER_MODEL` (default `openai/gpt-5.6-luna-pro`), `WORKING_SET_MODEL`.
