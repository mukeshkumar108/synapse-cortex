# Connected understanding (Cortex)

Status: **built and tested, deployed dark (flag off), not enabled for any real user.** Written 2026-10-20. Read `IMPLEMENTATION_STATUS.md` for what is
done / partial / deferred and `DECISIONS.md` for why. This file is the architecture and the evidence.

## 1. What it is, and why

A companion should know that "Morgan" is the person's former manager who now advises on the Bloom pilot, that Ruth is Ashley's *aunt* (corrected last
Thursday), that Ruth was in hospital and is home, and that a status update is due tomorrow — **without** searching a transcript, without a model call per
turn, and without pretending a guess is a fact. Operational memory (the ledger) already answers "what is on their plate and when". This adds the layer
that answers "who and what is their world about, and how does it connect".

Product invariant, unchanged: **Cortex is shared technology, not shared personal memory.** Every row below is scoped by product workspace + owner; one
product can never read another's entities (route-level and data-level tests, section 9).

## 2. Ownership (who decides what)

| Concern | Owner | Never |
|---|---|---|
| What an entity *is*, how two things relate, whether a relation changed | the **connect pass** (a tool-using model agent, `world_agent.py`) | code deciding meaning |
| Validity: stated claims need an exact quote from the person's own words; links must point at real records; unknown/malformed/truncated tool calls refused; finish gate (re-read + `considered`) | **code** (`world_agent._tool`, `run`) | silently repairing a claim |
| Operational facts (dates, times, status of appointments, promises) | the **ledger** — the connected layer *links* to a ledger row by key and reads it live | copying a date or status into an entity |
| Retrieval ("who did they just mention", overview, snapshots) | **deterministic code** (`known_world.py`): alias match nomination, scoring, rendering | calling a model on a turn |
| Whether to follow up on something | the **attention layer** (`attention_cycle.py`), which may now hold an intention whose `source` is an entity | deciding from the overview text |
| Placement in the prompt, the `know` tool, exposure reporting | the **Runtime** (`world_context.py`, `know_tool.py`, `cutover_executor.py`) | interpreting the records |

## 3. Data model (additive; four new tables, three new columns)

`KnownEntity` (kind is free text; `self` is reserved; `basis` stated|inferred; `sensitive`, `suppressed`, `status` active|dormant|resolved|merged,
`merged_into_id`, `summary` ≤500 chars, `source_refs_json` = session + verified quote), `KnownEntityAlias`, `KnownLink` (from entity → target
`entity|ledger|attention|page|arc|exploration`; `relation` free text read as "<from> <relation> <to>"; `basis`; `evidence` = verified quote;
`status` current|superseded; `note` = why superseded), `CueExposure` (per entity/cue: how many *sittings* it was composed into, and whether the person
engaged — exposure counted once per 45-minute window, never per turn). `AttentionAction` gained `source`, `source_ref`, `expires_at` so an intention can
belong to an entity. Schema is created by `Base.metadata.create_all` plus `_ADDITIVE_COLUMNS` (no migration, nothing existing is altered).

The person themself is a reserved entity (`kind=self`, "the person"), created by code on first use. Without it the first real run attached "partner of
Ashley" and "manager of Morgan" to *Bloom* because nothing else stood for the user (section 8, finding F2).

## 4. Writing: the connect pass

Runs inside consolidation, **after** the ledger agent has committed, in its **own DB session**, fail-open (a crash cannot touch operational records),
only when `CONNECTED_WORLD_ENABLED` and the product's `world_enabled`, not for independent sittings, not for transcripts under 120 characters. One agent
loop (≤14 model turns; `qwen/qwen3.8-27b` via NanoGPT, flat-rate; fallback OpenRouter `qwen3.7-flash`) with tools:
`list_entities, search_entities, get_entity, create_entity, update_entity, link_entity, supersede_link, restore_link, merge_entities, finish`.

Code-enforced: unknown arguments rejected; truncated calls never run; a `stated` basis requires a quote that appears **verbatim (case/whitespace/
apostrophe-normalised) in the person's own lines** — an assistant line cannot back a stated claim; otherwise the claim is stored `inferred` and the agent
is told why; `supersede_link` reports exactly which link it retired and `restore_link` undoes it; relations to ledger rows must name an existing key;
"the person" cannot be created, edited or duplicated; `finish` is refused (twice at most) until the registry is re-read after the last write and a
`considered` line says what was deliberately not recorded. The agent is told never to assume the person's gender or marital status.

Cost: one agent loop per significant consolidation (observed 6–12 model calls for a 4-turn session; roughly 2–11k input tokens each). Zero model
calls on any conversational turn.

## 5. Reading (all deterministic)

`GET /v1/memory/world` — product-credentialed, default-deny listed route. `view=`:
- `packet` (what the foreground uses): `overview` + `mentions` + `shown` (what was composed). `q` = the person's current message.
- `overview`: ≤6 people/projects/places by score (open matters, recency; "Relationship to the person: …" from links) and ≤4 developing situations;
  situations shown ≥3 sittings without engagement and untouched ≥3 days drop out; suppressed entities never appear; sensitive situations render minimally
  if the product says so.
- `entity` (`depth=snapshot|connected|deep`): one entity, its links (superseded ones under "Earlier understanding"), open and recently closed ledger
  matters read **from the ledger now**, connected situations, follow-ups intended, and at `deep` the supporting quotes. An ambiguous name returns the
  candidates and says which one was meant "has not been established".
- `inspect`: everything the layer holds with provenance (for "was it Cortex's understanding, retrieval, or her response?").

Mentions are a **nomination, not a decision**: whole-word match of alias/name, plus the first name of a multi-word `person` entity. Two Morgans →
ambiguity is reported, never guessed.

`POST /v1/memory/world/exposure` records what the Runtime composed. Engagement (the person responded/the companion raised it) is recorded by the
attention review, separately. This keeps the five states distinct: *state* (ledger/entity), *computed cue* (view), *durable intention* (AttentionAction),
*exposed* (CueExposure), *engaged*.

## 6. Runtime integration (companion-runtime; off by default, `CONNECTED_WORLD_ENABLED`)

- `world_context.fetch` per turn (one GET, 3s timeout, fail-open) → `composed_packet.build_sections(world_text=…)` after continuity, before operational
  awareness (Sophie / unified packet); for non-unified memory-pipeline products the same blocks go before `[OUTPUT CONTRACT]` together with operational
  awareness. `report_exposure` is submitted to `post_reply` in the background (not for evaluation turns).
- `know` tool (`know_tool.py`): `know(entity, depth)` → the `entity` view; ≤3 calls/turn; granted to Sophie and Bloom via `tool_ids`; registered only when
  the Runtime flag is on and the companion uses the memory pipeline.
- `rolling_continuity.render_account` now labels post-checkpoint lines "Since then (more recent; where this differs from the above, this is current)".

## 7. Safety and boundaries

- No product reads another's entities: workspace is derived from the product credential at the request boundary; cross-product `GET /world` returns the
  caller's own (empty) world; tests assert it for Sophie↔Bloom, overview/entity/inspect/exposure, and that an unlisted route stays default-deny.
- Suppression is of *prompting*, never of memory: `suppressed` entities leave the overview and any live attention intention is dropped from pending
  attention; the entity stays inspectable and is not deleted.
- A guessed relationship is never shown as confirmed: inferred links and entities carry "(inferred, not confirmed)" in every view; a link is upgraded only
  when a verified quote arrives.
- Nothing is deleted by the layer; corrections supersede (history kept), merges keep resolving by alias.
- **No user-data deletion/export endpoint exists yet** for this or any layer (known gap; needed before sensitive-data products go live).

## 8. Evidence (intended / implemented / observed)

Real models on an isolated scratch Cortex (own Postgres, copied provider keys, torn down afterwards). Scenario: three sittings over four days — new job,
partner, partner's relative ill (corrected: aunt, not mum; then home), manager leaves and becomes an adviser, a new manager appears, a decision is
considered. Harness `scripts/eval_world.py`; raw outputs `reports/world_20261020_170140.md` (run 1, before fixes), `reports/world_run2.md` (run 2,
after fixes), `reports/world_run3_bloom.md` (the same scenario as Bloom, second product); in-session continuity `reports/rolling_continuity_inspect.json`.

**Run 1 worked on the hard parts and exposed real defects.** Worked: the relationship correction (mum→aunt) superseded the old link with the person's words as
the reason; Morgan's change (manager→left→adviser) kept history; Ruth's hospital→home state change reached the overview; ledger-owned facts were read live
("tomorrow (Fri 23 Oct)"). Defects, all fixed before run 2:

| # | Observed in run 1 | Fix |
|---|---|---|
| F1 | Summaries said "he/his" and "mother-in-law" — gender and marriage the person never stated | contract rule (applies to notes too); same rule added to the ledger agent |
| F2 | No stand-in for the user: "Bloom — partner of — Ashley", "Bloom — manager of — Morgan" | reserved `self` entity + contract; overview shows "Relationship to the person: …" |
| F3 | Evidence quotes mangled at apostrophes ("s got a chest infection that won / re waiting…") — stitched fragments stored as quotes | whole-quote verification against the person's own lines only; no stitching |
| F4 | "Morgan texted…" matched nothing (alias was "Morgan Ellis"); "Priya wants…" showed no snapshot | first-name nomination for person entities |
| F5 | A link retired by mistake with an unrelated reason (a dentist link with a note about Morgan) | `supersede_link` echoes what it retired; `restore_link`; contract: take the id from `get_entity` |
| F6 | Entity created without a quote stayed "inferred" even after the person said it (Ashley) | `update_entity(basis=stated, evidence=quote)` upgrades when verified |
| F7 | Ambiguity text cut mid-word ("consideri;") | word-boundary cut |
| F8 | Run summary exposed no connect-pass information | `world_agent` + `world_agent_trace` in `GET /run/{id}` |

**Run 2 (after fixes):** no gender/marital assumptions in entity summaries; every relationship to the user hangs off the person; Morgan and Priya resolve
by first name; the aunt correction and Morgan's departure are in "Earlier understanding"; Ruth's stale "awaiting results" ledger row no longer attached.
Remaining observed imperfections (not fixed, recorded honestly):
1. One summary stated the decision the person was only *considering* as done ("the person is leading it") — an unsupported leap. Contract line added after run 2.
2. A superseded note still said "she" for Morgan (gender assumed). Contract extended to notes; residual risk — a model rule, not a mechanical guarantee.
3. A situation created by the pass shows "(inferred, not confirmed)" although the person stated the fact: the agent supplied no verifying quote, so the system
   stayed honest rather than generous.
4. Ledger-side: row *titles* go stale ("…awaiting test results") when only `detail` is updated; the connected view prints titles. Ledger concern, unchanged here.

**Run 3 (same scenario as a second product, Bloom; after the "say only what was said" line).** Product separation held (separate owner, `bloom-` prefix, nothing from
the Sophie run visible). The overclaim did not recur ("Ashley thinks they should take the lead", no "is leading it"); "they" is used for the person throughout; the
aunt correction and Morgan's departure were handled; the standup worry was created as a situation and **resolved** when Morgan left. New defect: **kinship between
other people leaked into prose and was wrong** — Ashley's summary read "Ruth's child" and, after the correction, "Ruth's sibling" (she is Ruth's niece; the link
was correct, the prose was not). Contract line added (kinship between other people belongs in links, not summaries); **not re-run** — treat as unverified. Also: the
first sitting's connect pass ended `unfinished` (it hit the 14-turn cap after writing 6 entities / 11 links, no `finish`); its writes stand, and nothing marks them
as unchecked except that status — a candidate for a lower-cost first pass or a higher cap.

**In-session continuity (Runtime `rolling_continuity`) — real packets, 40 messages.** It works as designed (six-message steps, one checkpoint at 24 messages,
reconciled narrative) and it handled the correction and the manager change in its newest patch. Two problems: (a) between checkpoints the *old* narrative
("her mum", "Morgan may be annoyed", "decide whether to take the lead") sits in the same block as the *new* patch lines ("aunt", "Morgan left", "decided
not to") — the foreground sees both with no signal which is current (fixed with the "Since then …" label; the underlying cause, a patch cannot retract
narrative text, is **not** fixed); (b) the small model (`ling-3.0-flash`) invented "is now leading the Bloom pilot" at step 2. Operational details (dentist,
MOT, Friday demo) are *not* in the continuity account at all — correctly, they live in the operational view; but it means in-session continuity and operational
awareness must both be in the packet (they are, on Sophie's unified path).

**Not done / not observed:** the full executor was not run end to end against the new code (unit tests cover the wiring; the Runtime assembly path was
exercised only through `build_sections` and handler tests); no real-user conversation; no multi-week decay behaviour; curiosity candidates and health
observations are *supported* (`kind` free text, situations) but only a health-like situation (pneumonia) was exercised; the attention agent was not
re-evaluated with entity-sourced intentions on real models (unit tests only).

## 9. Tests (all passing at the commit below)

Cortex: `test_known_world.py` (views, state change with no copy, exposure per sitting, ambiguity, supersession, inspect, first-name nomination, self anchor),
`test_world_agent.py` (interface guarantees, quote verification incl. apostrophes and assistant-only claims, self protection, restore, pipeline hook, fail-open,
flag off by default, independent sittings skipped), `test_world_endpoint.py` (flag-gated, product-isolated, exposure), `test_attention_cycle.py` (entity-sourced
intentions: live-entity check, one per entity, suppression, expiry), `test_product_isolation.py` (route inventory). Runtime: `test_world_context.py`
(off by default; product credential; fail-open; placement; exposure; `know` cap/depth), `test_rolling_continuity.py`.

## 10. Enabling it for real users (needs the founder's explicit review)

The layer stores new categories of personal data (family, health-adjacent situations). Before enabling: (1) review `inspect` output on a real
non-founder-owner scratch run; (2) decide `world_sensitive` per product (`minimal` hides sensitive situation text in the overview); (3) build the
user-data export/delete path; (4) set `CONNECTED_WORLD_ENABLED=true` in Cortex `.env` **and** Runtime `.env`, restart both. Rollback: set both flags to
`false` (instant; stored rows are inert). Image rollback tags are listed in `IMPLEMENTATION_STATUS.md`.

## 11. Continuing the work

Highest value next: (1) make a patch able to retract narrative text in `rolling_continuity` (or have the checkpoint step re-run on correction); (2) run the
attention agent on real models with entity-sourced intentions and measure whether anything is raised that shouldn't be; (3) a replay of real (consented)
sessions through the connect pass and a human read of `inspect`; (4) merge-suggestion for duplicate entities across sittings (the agent can merge but is
rarely shown a reason to); (5) retire legacy `Entity`-service tables the audit found unsafe for cross-product use (section 12).

## 12. Audit note: the legacy entity tables

Cortex already had `entity_service`/lifecycle tables. They are keyed by owner but not product-qualified in several read paths and carry model-extracted
`subject_refs` of unreliable quality; this layer deliberately does **not** reuse them and nothing reads them for the packet. They are the likeliest place
a future change could leak across products; treat any new reader of them as needing the isolation tests first.
