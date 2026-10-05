> Mirrored from companion-runtime/docs/THIN_PRODUCT_CONTRACT.md (canonical copy lives there; regenerate this mirror if it changes).

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
| Identity of the world and the person | `trusted_user_context.user_id`, `.world_scope` (`rpd2:<userId>:<characterId>:<chatId>`; `[A-Za-z0-9:_.-]{1,160}`), `.user_display_name` (must equal the name bound into the constitution), `.timezone` |
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
