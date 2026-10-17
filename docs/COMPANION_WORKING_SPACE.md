# Companion working space

What it is: durable, companion-scoped storage for things **the companion itself chose to keep** — a thought it did not say aloud, a question to look into, a draft, an intention. Written by the companion, read by the companion, never interpreted by Cortex. It exists so a companion no longer has to speak something aloud, or wait for a conversation to be consolidated, before it can preserve something it wants to pursue.

This is shared substrate. Sophie is the first identity that uses it; nothing here is Sophie-specific except the default policy entry and the (pre-existing) Sophie-only notebook consolidation.

## Boundaries (what it is not)

* Not memory interpretation. A write never calls a model, never creates a `memory_runs` row, never touches `notebook_pages`, `ledger_items`, `continuing_arcs` or `sitting_preparations`, so it cannot trigger listening, Ling, consolidation or a preparation rebuild — mid-sitting or otherwise. Asserted by `tests/test_companion_work.py::test_lifecycle_provenance_and_no_interpretation_side_effects` (a model function that raises is installed; all five memory tables are checked empty).
* Not instructions. Items are shown as possibilities, in the companion's own framing ("things you wrote for yourself … never obligations"); nothing schedules, nudges or compels. The scheduler does not look at the working space and does not offer a sitting because items exist.
* Not an ontology. `kind` is the companion's own free label, never validated. There is no score, priority, due date or type system. Lifecycle is `open → completed | abandoned`; `revise` reopens.
* Not an external actor. Nothing here can send, buy, post or change anything outside itself.

## Data

`companion_work` (current state) and `companion_work_events` (append-only; one row per companion act: create, revise, continue, complete, abandon). Scope of every row and every query: `(honcho_workspace_id, owner_peer_id, companion_id)`. Each event carries `author = companion:<id>`, the surface (`foreground` | `independent`), the sitting id, the chat/conversation id, the text written, an optional note, and `evidence_json`.

Evidence: in an independent sitting a write may cite the refs shown in square brackets in her transcript (`[a3]` a model's answer, `[s2]` a search, `[r4]` a page read). The runner stores the **verbatim captured result** next to the cite; a cite it cannot resolve is stored as `{"ref": …, "unresolved": true}`. The record therefore distinguishes what she claims to rest on from what was actually returned.

## Policy

`COMPANION_WORK_POLICY` (Cortex env, JSON): `{"<companion_id>": {"foreground": "off|read|write", "independent": "off|read|write"}}`. A companion not listed is `off`. Empty env = built-in default (`sophie`: write/write). Enforced in Cortex on **every** call (`require()`), whoever the caller is. Independently, the Runtime offers the tools only if the application grants `work_read` / `work_write` in `ApplicationDefinition.tool_ids`. So a product can: enable (grant + policy), restrict (read only), or suppress (no grant or policy off) per surface. Independent sittings for a companion whose `independent` level is `off` are refused (403). Rollback: remove the env line (reverts to Sophie-only default) or remove the grants.

## Surfaces

**Foreground (Runtime).** `work_read` and `work_write` are ordinary optional model tools (`companion_core/runtime/work_space.py`), offered on the streaming path next to `recall`/`note`. At the start of each turn the system prompt carries a short block ("YOUR WORKING SPACE …") with the open items (id, title, where/when written, an excerpt) — one cheap Cortex SQL read, no model call. Caps: 3 reads and 3 writes per turn; writes are off in evaluation mode. When the model has already begun its reply and then calls `work_write`, the turn ends after the write (`SILENT_AFTER_TEXT` in the provider): a second round made models restate the reply they had already streamed. No per-turn reflection step, no compulsory call.

**Independent sittings (Cortex).** The existing runner (`exploration.run_independent_sitting`) now takes `companion_id` and an optional `identity` (the companion's constitution text from the product/Runtime registry). Her open items lead the context. New actions `work_read` / `work_write` go through the same `companion_work.run_tool` the foreground uses. A sitting that only used the working space is recorded with status `worked` and **not** consolidated; her private writes are tagged `private` and never fed to listening. A sitting with real exploration still consolidates exactly as before (Sophie only — see Limits). An action with no `type` is reported to her ("nothing was done") instead of ending the sitting.

**Tools and delegated execution.** What exists today is what she gets: `ask_model`, `web_search`, `web_read` inside an independent sitting. The foreground has no external tools (the shared capability layer is a parked branch), so the delegation path is: foreground writes an item ("look into this") → a later independent sitting picks it up, uses its tools, and revises the item with cited evidence → the next foreground sitting sees the result. Nothing was invented for this and nothing externally consequential is executed.

## Endpoints (`/v1/work/*`)

`POST /tool` (what a companion's call executes; the response `text` is exactly what the model is shown), `GET /context` (pre-rendered open items, policy-enforced), `GET /items`, `GET /items/{id}` (operator inspection: full text and event history).

## Limits, honestly

* Whether a model uses the tool is its choice and varies by model. In production-path tests on 2026-10-17 Solar Pro 4 (the Sophie default) and DeepSeek V4 Flash never called `work_write` (7 turns); Claude Haiku 5.5 did, when the user had deferred a thought, and not when the thought had just been voiced.
* Items are written in whatever voice the model chooses; some read as third-person memos and one invented a name for the user. The store does not correct them.
* Notebook/exploring consolidation of independent sittings is Sophie-specific (prompts name her). Other companions' independent sittings that explored are recorded (`recorded`) but not consolidated; their durable continuity is the working space.
* The scheduler's allowlist, workspace and daily cap are still single-companion (Sophie) configuration.
