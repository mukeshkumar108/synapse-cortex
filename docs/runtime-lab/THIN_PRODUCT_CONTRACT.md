> Mirrored from companion-runtime/docs/THIN_PRODUCT_CONTRACT.md (canonical copy lives there).

# Thin product contract (what a product sends vs what Runtime/Cortex own)

Written for RPD2 ("Pure Mode"); valid for any product. A thin product is an identity + a UI + a transport. It does **not** keep a second brain.

## The product owns
| Thing | How it crosses the seam |
|---|---|
| Character identity, constitution (kernel + voice), already bound to the user's display name | `application_context.character_constitution` (≤40k chars) |
| Authored, STATIC canon / scene facts (a few lines, true by authorship) | `application_context.scene_facts` (≤6), `canon_lines` (≤6), each ≤500 chars |
| Product policy that is explicit | lives in the **Runtime registry**, not per turn: `epistemic_policy` (RPD2 = `generative`: invented fiction is canon, attributed) |
| The current user event | `current_sanitized_message`, `message_parts` |
| Persisted conversation history | `canonical_history` (≤20): stable persisted ids, role, content, `created_at` ISO — the same ids every turn |
| Identity of the world and the person | `trusted_user_context.user_id`, `.world_scope` (**must contain the conversation id** for a conversation-isolated product such as RPD2 — the Runtime refuses a live turn with 422 otherwise; `rpd2:<userId>:<characterId>:<chatId>`; `[A-Za-z0-9:_.-]{1,160}`), `.user_display_name` (must equal the name bound into the constitution), `.timezone` |
| Session routing | round-trip `execution_metadata.next_session_state` → `trusted_user_context.session_routing` EVERY turn (this is where turn count, the resident world cache and the checkpoint cadence live) |
| Model choice | `selected_model_id`; the product must log `execution_metadata.foreground_requested_model`, `foreground_fell_back` and `model_used` — a fallback is a different experiment |
| Identity of the turn | `turn_id` = the user message id; on an ambiguous POST, `GET /v1/turns/{turn_id}` before any retry; never run one turn twice |
| Grants | `capability_grant` all-false unless the product genuinely offers tools |
| Mode | `execution_mode: "live"` for real traffic; `"evaluation"` (+ `evaluation_namespace`) writes nothing |

## Runtime / Cortex own (the product must NOT compute, store or send these)
Evolving scene · evolving canon (names, events and relationships invented in play) · relationship/world state · Matters · objectives · trajectory ·
interpretation (when, by whom, with what cadence) · attention and what is selected for a turn · compilation of the foreground prompt · the size and shape of the
raw tail · retrieval · transient-versus-lasting judgement · fallback chains. Unknown keys are rejected (`extra="forbid"`): `director_move`, `turn_job`,
`control_mode`, `account_means/unresolved` and similar cannot be smuggled back in.

## What "thin" means for RPD2 in practice
Delete (after the graduation test below) any product-side: compiler/director/move bank, hot ledgers, trajectory observer, consolidator, relational extraction,
scene grammar state, local canon accrual, local memory retrieval. Keep: kernels + voice, static authored canon, UI/auth/chat persistence, message ids, session
round-trip, model dropdown, logging.

## Remaining gaps (honest)
1. **No canon roster block.** Established names/places/people are carried only inside the story brief. With a very short tail a minor invented name could be
   dropped. Candidate fix (Runtime, mine): render a small "established in this story" roster from the world's actors/relationships. Test in the lab first.
2. **`canonical_history` is capped at 20** and the Runtime decides how much to show; products must still send persisted ids and `created_at` or coverage/recency
   reasoning degrades (frontier shows `unabsorbed: "unknown"`).
3. **The scene is as fresh as the last interpreter pass** (every 3 user turns). Between passes the foreground sees the raw gap (capped). A lighter scene-only pass is
   designed, not built.
4. **Tail policy is not yet model-aware.** Currently a fixed cap (6 messages, +4 max). The lab shows ≥4 raw messages let a poisoned local frame win on this model;
   the per-model tail profile is the next change.
5. **Conversational expenditure (`spent`) is new and unvalidated.**
6. **No native A/B yet at the marked cuts** (Spark: run the native path at each cut and save the reply; keep the native path until this is done).

## Graduation test for Pure Mode (before deleting native)
(a) a real live turn through the app route returns `model_used == requested` and `foreground_fell_back == false`; (b) `session_routing` round-trips (turn number
advances; `execution_metadata.world.checkpoint_handed_off` becomes true every 3rd turn); (c) the lab report for a cut shows the world and prompt the product expects;
(d) native A/B replies exist for the marked cuts. Only then remove the local cognition.


## Continuity isolation (enforced by the Runtime)
Each registered product declares `isolation`: `person` (Sophie: one continuity per person across chats, devices and voice) or `world` (RPD2: every chat is its own continuity).
For `world` products the Runtime (a) refuses a LIVE turn (422 `world_scope_required` / `world_scope_must_name_the_conversation`) unless `world_scope` includes the
conversation id, so a product bug can never silently merge two chats into one Honcho peer / Cortex world; (b) skips the cross-conversation chronology lookup (the
model is never told, from other chats, when the person last spoke); (c) keys the REAL-world scene layer by the world, not the person (`real_scene_scope: "world"`;
flip to `person` only as a product decision to share the person's real-world situation across their chats). Retrieval, interpretation, the scene and the
executive are all keyed by the world owner (`world:<scope>`), covered by `tests/test_world_scope_isolation.py` and `tests/test_isolation.py`.

## Which model/fallback keys are canonical
`execution_metadata.foreground_requested_model`, `execution_metadata.foreground_fell_back` and top-level `model_used` / `used_fallback` all exist on the wire.
Use `foreground_fell_back` for "served ≠ requested" (it is also true when the model differs without the provider-level fallback flag); `model_used` is the model that served.

## Precedence
The product's constitution is authoritative. The substrate describes (story, scene, trajectory, objectives) and never rewrites or overrides it: it is placed first in
the compiled prompt, the interpreter treats the character's output as evidence rather than authority, and the "constitutional orientation" the interpreter judges
against is product-authored (companion definition), never extracted. There is no substrate self-concept layer today; if one is added it renders as description under
the constitution and loses every disagreement.

## Clocks
Session boundaries and `[TEMPORAL FACTS]` use the WALL clock (history timestamps / turn records). Narrative time is a separate typed story clock (`Scene time`,
read by the model from what the user says) and never opens or closes a session; a story scene/time jump only triggers interpretation of the stretch that just ended.
There is no arithmetic story calendar: "three days later" is stored as text.


## Model expectations for RPD2 (product decision, 2026-10-05)
Default and fallback chain: **doubao-seed-character first, DeepSeek v4 flash second** (both NanoGPT). MeroMero is not a default (flaky upstream) but stays selectable from the dropdown, which
always leads the chain. Any turn served by a model other than the one requested carries `foreground_fell_back: true` and the reason `foreground_fell_back` in `execution_metadata.degraded`; the
daily digest alerts when more than 30% of a product's turns fall back. The real-world scene layer is isolated per chat for RPD2 (confirmed decision; do not share across chats).

## Entity handling (shipped 2026-10-05)
* The cheap router is given the world's FULL actor index (names, capped at 60) and classifies a mention as none / known / new / ambiguous.
* A mentioned **known** person is looked up locally by name in the packet; their established relations and one claim are added to the prompt (independent of the router).
* A **new** or **ambiguous** person goes to the evidence ledger (Honcho) directly, even when the router said no look-back is needed.
* Names of durable actors that appear nowhere in the prompt, scene or tail are listed in a short roster (names only).
