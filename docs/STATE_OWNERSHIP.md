# Who owns what: situational and conversational state (Honcho + Cortex + Runtime only)

Audited from the code and production data on 2026-10-05; the live-scene section was then BUILT the same day (see 'Live scene: as built'). Product-agnostic: RPD2 and Sophie consume the same substrate.

Roles: **Honcho** = evidence ledger and raw retrieval (no interpretation). **Cortex** = semantic interpretation (durable and recent meaning). **Runtime** = live per-turn mechanics, resident working set, compiler, serving.

## The map

| Piece of state | Where it lives today | Written by | Reaches the foreground via | Freshness | Status |
|---|---|---|---|---|---|
| Raw evidence | Honcho (mirrored exchanges; Sophie's app mirrors her own) + Cortex's message-id ledger | Runtime `mirror_exchange` / the app | interpreter input; depth retrieval | immediate | **working** |
| Live participants, location, activity, physical state, "when" phrase | **Runtime `current_scene`** (session state + resident). Extracted by a cheap model from the **user's turn only**, **only when Jev flags `scene_change`**. Aged at render (fresh < 1 sitting, stale ≤ 12h, then dropped) | Runtime | `[CURRENT SCENE]` / `[LAST OBSERVED SCENE — stale]` | per turn, but only on a flagged user change | **half-built, duplicated** (see below) |
| Same live scene, second copy | **Cortex `current_scenes` + `scene_epochs`** (authority ranks, epochs; 14 rows in prod, last written 2026-10-04) | Runtime `report_scene` (post-reply) | **nobody reads it** (`/scene/active` is never called by the Runtime; the world model and attention state don't include it) | n/a | **write-only dead weight** |
| Fictional / story time | not represented; `[TEMPORAL FACTS]` states the **real** wall clock ("It is Sunday 22:48 where the user is") | — | — | — | **missing** (matters for any roleplay product) |
| Time since last interaction, new-session boundaries | Runtime chronology (interaction times in session state, history timestamps, turn records) | Runtime | `[TEMPORAL FACTS]` | per turn | **working** (real time only) |
| Travel / transitions | no model; only the free-text `temporal_position` field of the live scene | — | — | — | **missing** |
| Recent conversational compaction (what just happened, what's open, what changed) | **Cortex `continuation_briefs.scene_json`** = `now / unresolved / transient / changed / spent / raw_turns` | interpreter pass (every 3 user turns, session end, time-bound/awaiting-reply) | `[WHAT IS HAPPENING NOW]` | ≤ 3 turns stale; the gap is shown raw, capped | **working** (`spent` unvalidated) |
| …second copy of the same job | Runtime **episode ledger** (`[ESTABLISHED EARLIER…]`) and **working note** (context surgery) | Runtime extractors | only for non-interpreted (evaluation-without-world) turns / Jev `trajectory_degraded` | — | **legacy duplicate**; delete when the lab stops needing evaluation-mode without a world |
| Open loops, questions, promises (structured) | Cortex operational state (expectations, open loops, commitments, work items) + executive "carrying" | interpreter, executive | `[SELECTED WORLD CONTEXT]`, `[WHAT YOU ARE CARRYING]` | per pass | **working** |
| Open loops (narrative) | `brief.unresolved` free text | interpreter | `Still open:` lines | per pass | **working** (two representations on purpose: structured for action, narrative for voice) |
| Spent material (asked / told / joked / promised / settled) | `brief.spent` | interpreter | `Already covered earlier:` lines | per pass | **new, not validated** |
| Transient affect | `durability` tiers (acute→durable) + TTL; `brief.transient` | interpreter | transient lines; acute state expires | per pass | **working** |
| Durable world (actors, relationships, events, claims, narrative, matters, dimensions) | Cortex world model | interpreter | resident; **mostly not rendered** — reaches the model via the story brief and attention selection | per pass | **working, under-surfaced** (no canon roster block) |
| Trajectory, objectives | Cortex | interpreter | `[WHAT EACH PERSON IS TRYING TO DO]`, `[TRAJECTORY NOTE]` | per pass | **working** |
| Attention / working set | Cortex attention state + Runtime `project_resident` + Jev flags | Cortex, Runtime | `[SELECTED WORLD CONTEXT]`, retrieved evidence | per turn | **working** |
| Raw tail | Runtime frontier window (6 messages; at most +4 for the unabsorbed gap) | Runtime | the message list | per turn | **working**; policy not model-aware |
| Compile | Runtime `compile_foreground_prompt` | Runtime | system prompt (+ lab-only late placement) | per turn | **working** |

## The overlap, stated plainly
"Scene" is **three things**:
1. **Runtime `current_scene`** — the physical/situational scene (who, where, doing what). The only one the foreground actually uses for that job.
2. **Cortex `current_scenes`** — a more careful version of the same thing (authority ranks, epochs), **written but never read**.
3. **Interpreter `brief.now`** — the narrative description of the latest exchange. Not the same job, but it incidentally carries setting ("at dinner"), which is why short-tail replies kept the restaurant.

(1) and (2) are one system split across two services with the reader missing. (1) and (3) overlap at the edges. Recent-turn compaction exists once for live worlds (the interpreter) plus a legacy copy.

## Gaps that matter
* The live-scene extractor only reads the **user's** turn. In roleplay the **assistant** narrates location changes ("she pulls you into the hallway"), so those are missed.
* It is a cheap model gated by another cheap model (Jev's `scene_change`), so a change can be missed entirely.
* No fictional clock: roleplay is told the real time.
* The lab runs no extractor during ingest, so **every lab world so far has an empty physical scene** (no `[CURRENT SCENE]` block). Experiments tested kernel + interpreted story + tail, not live scene.
* Scene state in session routing is client-held: a client that drops `next_session_state` loses it (the Cortex world survives).

## Recommendation (for decision)
1. **One live-scene owner: Cortex.** Finish the half-built loop instead of building another system: the Runtime keeps the cheap per-turn extractor but (a) it also reads the assistant's reply, (b) writes detections to Cortex's `current_scenes`, (c) the resident hydration reads it back, so the scene survives devices, sessions and modality (voice ↔ text). The Runtime's session copy becomes a cache.
2. **Add a story clock** as a typed field (generative worlds), and stop stating the real wall clock to roleplay products.
3. **Keep `brief.now` as the narrative layer** and say so in the contract; don't make the interpreter also extract physical scene.
4. **Lab fidelity:** replay the extractor over the transcript during ingest so frozen worlds carry a real scene; until then results should not be read as scene-inclusive.
5. **Delete the legacy** episode ledger / working note path once the lab no longer needs it.

Not yet decided: whether the live scene should instead be produced by the interpreter pass (fewer systems, but ≤ 3 turns stale). My view: no — physical scene needs per-turn freshness, narrative can lag.


## Live scene: as built (2026-10-05)

**Owner: Cortex** (`current_scenes`, the store that already had authority ranks and epochs; it is now read as well as written). **Runtime senses, reads back each turn, renders.**

Two layers, never merged by the substrate:
* **real** — the person's actual situation (where they are, what they're doing, declared journeys). Keyed by the PERSON in Cortex (`real_<user>`), so it is shared across chats, devices and modality. The wall clock in `[TEMPORAL FACTS]` is always real time (kept for every product: the character can orient the user in their real day even mid-story).
* **story** — this conversation's fiction (setting, scene time, who is present). Only for `generative` products. Keyed by chat.

Authority: the user's own words are written as `user_explicit` and persist until the user changes them; the character's reply is read for story changes and written as `model_inferred`, which cannot move a scene the user set (the "morning in the kitchen → suddenly night somewhere else" failure). If the user goes along, their next turn ratifies it.

Journeys are typed (`from`, `to`, `departed_at`, `expected_arrival_at`, `expected_return_at`): the model reads the sentence once; code does arithmetic at render time ("was expected there by 11:30, probably there now; expects to be back ~18:00") instead of asking "have you left the house?". A place stated before the expected arrival drops out once that time has passed. Each field carries its own age.

Flow per turn: probe (`/v1/world/version` now also returns `scene.story` and `scene.real`) → cheap sensing of the user's turn (gated by Jev's `scene_change`) overlaid locally so THIS turn sees it → reply → background: persist the user's detections, then sense the character's reply for story changes. Mechanical scene-change triggers still hand the stretch to the interpreter.

Posture (greeting the user in their real morning, bringing them back from a story) is NOT substrate: it belongs in the character's kernel; the substrate guarantees the facts are present and labelled.

**Still open:** a real-traffic smoke through the app routes; deleting the Runtime's local `current_scene` fallback (still used when there is no interpreted world) and the legacy episode ledger; the story clock currently comes only from explicit statements (`clock`); Jev still gates user-turn sensing (a missed flag is a missed change); lab worlds frozen before today have no live scene until `scripts/lab.sh <spec> rescene`.
