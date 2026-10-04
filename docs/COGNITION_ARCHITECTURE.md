# Companion cognition architecture (as built, 2026-10-04)

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
| **Honcho** | Raw evidence store and its own derivations; not yet an input to the interpreter (see limitations) | |

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
`WORLD_INTERPRETATION_ENABLED` (Runtime, **default off**), `WORLD_INTERPRETER_MODEL` (default `openai/gpt-5.6-luna-pro`).
