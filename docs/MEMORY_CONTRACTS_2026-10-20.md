# Memory pipeline contracts (2026-10-20)

Why this exists: production traces showed the operational ledger's intermittent failures were interface failures, not model randomness. The same witness
signal produced three different agent behaviours, `create_item` could not carry a date, one observation was silently dropped, and the evaluation reported
only the last-written fault. These are the contracts that replace that. See `reports/reliability_*.md` for the evidence runs.

## Witness → agent (what the observations mean)
| Tag | Meaning | Agent consequence |
|---|---|---|
| `CHANGED:` | something about a matter changed but it did not end: an unknown was answered, a time/date/place was fixed or moved, terms changed | **update** the existing record (detail, timing_text, expected_date; clear answered `waiting_on`/`question_text`; `waiting` → `open`). Never closes. |
| `ENDED:` | the matter itself is over (happened, delivered, cancelled, dropped) + the proving quote | only this (or clear transcript proof) closes; the quote must exist in the session transcript |
| `RESOLVED:` | legacy, unclassified | rendered to the agent as `RESOLVED (legacy tag)`; the deterministic fallback keeps its old behaviour |

`ITEM` is the thing itself (the appointment), never the open question about it. Items are things with real-world follow-through: commitments, appointments,
deadlines, awaited things, requested reminders, agreed experiments, voiced aspirations. Ideas, metaphors, feelings and explorations belong to the notebook.
A moved review/deadline changes that matter; it does not end or re-date other matters.

Observations reach the agent **numbered** (`[O1]…`) with every field the witness produced (confidence, waiting-on, question, people, blocked-by, evidence
quotes, status hint, reminder-authorised, changed, ended).

## Agent interface (code-enforced)
- Unknown tool arguments are rejected, never ignored. Malformed or truncated (`finish_reason=length`) calls never run (they used to run as `{}`).
- `create_item` takes the complete state: status, expected_date, timing, waiting_on, question_text, confidence, reminder_authorised, evidence.
- `update_item` returns what changed (before/after) and keeps the superseded detail in `source_refs.detail_history`; an explicit empty `waiting_on`/`question_text` clears them.
- `finish(accounting=[{obs, treatment, key, note}])` is accepted only if (1) the records were re-listed after the last write, (2) every observation number is
  accounted for, (3) `applied`/`merged` name a record **touched in this run**, `no_change` names an existing record, `skipped` carries a reason, (4) advisories
  (e.g. timing says Friday but `expected_date` is empty) were shown once. Refused twice at most; a third attempt is accepted as `finished_unchecked`
  (recorded, never `verified`). Advisories are advice: code never writes a value on the agent's behalf.
- The agent also receives the **session transcript** (ground truth). Observations are a witness's quick reading; the agent may handle a matter the witness missed
  (`accounting` entry `obs: 0`, must name a record touched in this run) and sets aside an unsupported observation (`skipped` + reason). Verified runs get no second deterministic pass.
- Several observations about one matter fold into one record (`merged`); accounting never pressures duplicate rows.
- The deterministic fallback runs **only if the agent made zero writes**. After partial writes the run is flagged `ledger_needs_review` and the agent's state stands.
- Full tool trace (args, results, finish_reason) is stored in the run bundle; `GET /v1/memory/run/{id}` returns it.
- Primary model `qwen/qwen3.8-27b` (NanoGPT, flat rate). The earlier "primary" `qwen3.7-flash` returned HTTP 403 on every call in production, so every run had silently been on the fallback.
  Fallback is OpenRouter `qwen3.7-flash` (cross-provider).

## Records are read later
Stored `timing_text`/`detail` never carry bare relative words (named day + date instead). Times of day given without am/pm are kept as said and flagged
("at 6, am/pm not stated") with an open question, never turned into 06:00 or 18:00; the attention agent leaves `due_at` null rather than guessing.
The cached preparation anchors time-relative statements to a named day/date.

## Attention (kept; hardened)
`schedule_action` rejects an unknown matter key, a closed matter, and a `due_at` already in the past. Closing a matter supersedes its pending/due/held follow-ups
mechanically (audited). `due_at` is emitted with its UTC offset; the Runtime renders it on the person's clock.

## Time
Consolidation carries `session_time` (ISO) and `time_zone` (IANA) from the Runtime. Relative words resolve against when/where the person spoke, never the worker's
clock: witness prompt, observation date reference, `expected_date` annotations, preparation clock, and the attention cycle's `due_at` (the agent writes local
wall-clock; code stores UTC). No zone supplied → the last one that person's sittings reported → the product default. Current labels (the Runtime anchor) remain deterministic.

## Ownership and scope
- **The person is shared; a product's relationship, perspective and experience are product-specific.**
- Product-owned (column `product`): notebook pages, continuing arc, prepared perspective. The operational ledger and its facts stay with the person.
- `src/services/product_memory.py` is configuration only (pages, scopes, prompts, labels, `ledger_enabled`, `attention_enabled`, default zone). Sophie's text is
  unchanged; `bloom_memory.py` is an initial hypothesis (pages: life, reflections, concerns, growth; experiments live in the ledger as kind `experiment`).
  Unknown `companion_id` → HTTP 422, never silently Sophie.
- A companion's **independent sitting never writes the ledger** and never edits the shared arc (the real user's three ledger rows were all solo-sitting output).
- Runtime: `MEMORY_PIPELINE_COMPANIONS` (default `sophie`) decides which companions use the pipeline. `bloom` is code-ready but off until set.

## Execution
Consolidations are serialised per `(workspace, owner)`: in-process lock + Postgres session advisory lock on a dedicated connection. A waiter then sees the first
run's coverage (replay is a no-op). Lock timeout marks the run `failed` for replay. Orphan recovery (startup) is unchanged.

## Evidence
`reports/reliability_20261020_*.md`: first corrected sweep 42/48; then fixes at the parser (a marker ahead of an item dropped it; `ENDED: (none)` closed matters) and
contract (STATUS-HINT, delivered-under-CHANGED, transcript grounding); sweeps 5-8 on the final code: 48/48, 9/9 clean reps each (sweep 4 scored 46/48 until an oracle
false-failure was fixed). `sophie_packet_20261020.txt` is the rendered foreground packet; `bloom_session_demo_20261020.json` a real two-sitting Bloom run.
Postgres-only checks (advisory lock, cross-owner overlap) were run on a scratch Postgres.

## Known gaps (do not assume)
- The witness (a 27B model, one shot) still mis-tags occasionally; the grounded agent catches most of it, not provably all. Watch `ledger_agent.accounting` skipped/obs-0 rates.
- Cached preparation text is model prose in the companion's voice and can still contain flourishes or a stale "tomorrow".
- A cross-product shared person-knowledge layer is deliberately not built.
- Attention actions have no delivery path yet; Bloom has attention off by default.
- Cortex has no user-data deletion endpoint (needed before Bloom wellbeing data at scale).
- Real conversations through this pipeline: 3 sittings for the founder so far, 0 operational items.
