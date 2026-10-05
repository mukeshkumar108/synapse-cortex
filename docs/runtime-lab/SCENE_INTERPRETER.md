> Mirrored from companion-runtime/docs/SCENE_INTERPRETER.md (canonical copy lives there).

# The scene interpreter (as deployed)

The "scene" is not a separate component. It is part of the output of Cortex's single world interpreter (`synapse-cortex/src/services/world_interpreter.py`,
contract `wi-2`), written in the same reasoning pass as the durable world state, under the same lease and message-id ledger. There is one semantic author.

**Source of truth for the exact text:** `GET /v1/world/interpreter-config` (Cortex) — returns the live system prompt, model, section list, field list and
storage/projection description. From the lab: `docker exec -i companion-runtime python - interpreter-config < scripts/workbench.py`. This document explains it;
that endpoint cannot drift from the code.

## What it receives (one pass)
`PRODUCT POLICY` (grounded|generative) · `IDENTITIES` (product-supplied user/companion actors) · `CHARACTER CONSTITUTIONAL ORIENTATION` (product-authored,
never extracted) · `CURRENT WORLD STATE` (the existing structured world with real ids, including the last brief and trajectory note) · `HONCHO CONTEXT`
(long-term raw-evidence retrieval, when available) · `EARLIER MESSAGES` (already interpreted, context only) · `NEW EVIDENCE` (only message ids not yet
covered). Model: `WORLD_INTERPRETER_MODEL` (currently `openai/gpt-5.6-luna-pro` via OpenRouter — the only paid step).

## What it produces
Typed arrays: actors, relationships, events, claims, narrative, commitments, dimensions (directional relationship facets with `durability`), objectives
(with `scope`, `state`, `durability`, conflicts incl. against the constitution), matter candidates, trajectory (for the constitutional actor only),
state reviews (verdicts on everything it was shown), operational items, and one `brief`.

### The brief, and the live scene inside it
| Field | Meaning | Exists? |
|---|---|---|
| `brief.text` | durable story so far (a projection of the structured state) | yes |
| `brief.lines[]` | the same, as short lines citing the rows they derive from | yes |
| `brief.now` | what is actually happening in the most recent exchange | yes |
| `brief.unresolved[]` | what is genuinely still open between the people | yes |
| `brief.transient[]` | recent reactions/moods observed but not to be treated as lasting unless sustained | yes |
| `brief.changed[]` | what materially changed this stretch | yes |
| `brief.spent[]` | conversational expenditure: questions already asked (answered or not), anecdotes told, jokes/callbacks used, promises given, points settled | yes (added 2026-10-05; **not yet validated against repetition** — first thing to test) |
| `brief.raw_turns` / `raw_reason` | how many latest turns (0–3) the interpreter thinks are still worth showing verbatim, and why | yes — but treat as a hint; the tail policy belongs to the compiler/model profile (the interpreter cannot see how susceptible the foreground model is) |
| participants / location / physical scene | — | **No.** The Runtime's own `current_scene` extractor owns the physical scene (who/where/what is around). The interpreter's `now` is relational/narrative, not physical. |

How lasting vs transient is decided: the interpreter's `durability` tiers (acute = a reaction in the moment · provisional · durable · unknown). Prompt rule: a single
dramatic turn *happened* and is recorded as an event and acute state, but never by itself becomes a durable objective or ends a relationship; say what it most
plausibly is and what would confirm it. Acute state also expires by TTL in the projection.

## Where it goes
Stored versioned in `continuation_briefs` (`text`, `lines_json`, `scene_json`; superseded rows kept) → `world_model_service.build_world_layer` →
`continuation.brief.scene` in the resident world → Runtime `render_continuation` → the `[WHAT IS HAPPENING NOW …]` block in the compiled foreground prompt
(`now`, "Still open", "Observed, not lasting…", "Changed", "Already covered earlier…"). It is context for the character's voice, never an instruction.

## Cadence
The Runtime hands evidence over every `CORTEX_CHECKPOINT_EVERY_TURNS` user turns (3), at session end, and immediately for time-bound or awaiting-reply turns.
Each pass interprets only the ids not yet covered, in the background; failure leaves the stretch for the next pass. The scene is therefore as fresh as the
last pass; messages after `covered_through` are shown raw (capped; the gap is reported as `unseen_gap`).

## Changing it without editing source
Lab worlds only: spec `interpreter: {system_replace: [[old,new]], system_append, model}`. See `docs/COGNITION_WORKBENCH.md`. Changing the OUTPUT SCHEMA (new fields)
is a Cortex code change.

## Open questions this bench exists to answer
* Does `spent` actually prevent repetition when raw turns are removed? (needs a transcript with real repetition risk; read replies for re-asked questions / re-told anecdotes)
* Is `now` descriptive enough, and does any phrasing of `unresolved` nudge the model into a move (it must stay description)?
* Does a scene produced by a different prompt change the foreground more than the tail does?
