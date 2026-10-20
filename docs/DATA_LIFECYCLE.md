# Data lifecycle: what is stored about a person, where, and how it is exported and erased

Status: written 2026-10-20 night after auditing the real stores. The erase procedure below was **verified end to end on a synthetic user** (see "Verification");
it has **not** been run on any real person's data. Nothing here is legal advice; it is an engineering inventory.

## 1. Where a person's data lives (audited, not assumed)

| Store | What | Keyed by | Found by audit |
|---|---|---|---|
| **Cortex Postgres** (`synapse-cortex-postgres`) | memory pipeline (ledger, notebook pages, arc, preparation, attention, runs), connected understanding (entities, aliases, links, exposure), and the older interpretation tables (matters, expectations, open loops, world models/events, proactive log, work items, …) | `owner_peer_id` (+ `honcho_workspace_id` on newer tables) | the founder's real owner has rows in **33 tables** (e.g. `proactive_log` 2,824 rows); the first delete endpoint listed 13 by hand and would have left 20 behind. It is now schema-discovered |
| **Runtime Postgres** (`companion-runtime-postgres`) | `companion_runtime_turns`, `turn_packets` (full prompts and replies), `model_calls`, `evidence_messages`, `mirror_outbox`, `interpreter_runs`, `companion_sitting_state` (incl. rolling continuity), `companion_resident_cache` | `user_id`, `conversation_id`, `owner` | 8 tables |
| **Honcho** (`honcho-*`) | per-chat sessions with every message; derived "conclusions" (none for Sophie: `observe_me=false`) | peer `user_<id>`, session `chat_<id>` | sessions deletable; **peers cannot be deleted (HTTP 405)**: an empty peer id remains |
| Backups | nightly Postgres dumps, offsite copy | — | **not erased**; they age out with rotation |
| Model vendors | request logs at NanoGPT / OpenRouter / OpenAI | — | outside our control; flat-rate NanoGPT and per-call OpenRouter retention are the vendors' policies |

## 2. Tools

- **Cortex export / delete** (product-credentialed, scoped to the caller's product): `GET /v1/memory/export`, `POST /v1/memory/delete` (`confirm` must equal the owner id; takes the owner lock so
  an in-flight consolidation cannot write it back; returns `remaining`, which must be `{}`). Tables without a workspace column are guarded by the owner-id convention, so a Sophie credential
  cannot name a Bloom owner (403).
- **Whole-person erasure** (ops, in the Runtime container): `python -m companion_core.runtime.erase_user <user_id> <product> [--execute --confirm <user_id>]`. Default is a dry run that reports counts per store.
  `--execute` deletes Cortex → Honcho → Runtime, **waits for Honcho's queue** (it deletes asynchronously, minutes), re-reads every store and exits non-zero unless all report zero.

## 3. Boundary and honest gaps

- **Erased and verified empty:** Cortex (all owner-keyed tables), Runtime Postgres (8 tables), Honcho sessions and conclusions.
- **Not erased:** Honcho peer id (empty shell); database backups and the offsite copy until rotation; vendor-side logs; anything a person copied elsewhere.
- **Race:** a conversation already queued for consolidation when the erase runs can write new records when it runs afterwards. Erase after the person's last conversation has finished (`pending_consolidations`
  from `/v1/memory/world` or `/v1/memory/ledger` is 0), or run it again; the dry run shows leftovers.
- **Export** covers Cortex only (a JSON dump per table). A person-facing export of Runtime turns and Honcho messages is not built.
- Raw conversations are held in Runtime (`turn_packets`, `companion_runtime_turns`) and Honcho by design (evidence for recall). That is the main reason Bloom and other users stay off until the founder
  decides retention (for example: delete `turn_packets` after N days).

## 4. Recommendation (not implemented)

1. A retention rule for `turn_packets`/`model_calls` (they hold full prompts including the connected world block) — 30 days is enough for debugging.
2. A person-facing "forget me" in the product app that calls the Runtime, which runs `erase_user` as a background job and reports the verification.
3. A scheduled check that the number of owners with rows in Cortex but no Runtime user is zero (catches orphans).
