# Continuity rhythms — what the engine does, when, and why (2026-10-06)

## What we are building
A continuity engine: a companion that is **present every turn, understands at natural breaks, and recalls when something tugs** — three rhythms, three costs.
Nobody re-interprets their whole life between sentences. RPD2 is the stress tunnel: it invents constantly and exposes where the design is overbuilt, so its
cost is not the point; its *seams* are. Sophie is the product where code acts on state (reminders, journeys), so she needs structure RPD2 does not.

## The three rhythms
| Rhythm | Job | Mechanism | Cost |
|---|---|---|---|
| **Presence** (every turn, blocking) | she speaks | constitution + selected world context + raw tail (6 messages) → foreground model. **Nothing else gates the reply.** Jev (~0.5s) only routes retrieval depth. | the foreground call + Jev ($0.00008) |
| **Bridge** (after the reply, off the hot path) | cover what has scrolled out of the tail but is not yet interpreted | **scene narrative** (Cortex): a few plain sentences, rewritten every 2 exchanges (or at once on a significant moment) from the previous picture + the new messages | one cheap Luna call per 2 exchanges (~$0.0005) |
| **Understanding** (episode ends, backstop every 8 turns) | entities, claims, relationships, objectives, reminders, trajectory | Cortex world interpreter over everything since its last pass | ~$0.0065 per pass |
| **Recall** (on need) | what neither the tail nor the picture covers | Honcho retrieval, triggered by Jev's cheap over-firing flags (new name, "remember", correction…) | cheap |

Invariant that makes batching safe: **the picture lags by at most 3 messages and the tail shows 6**, so nothing falls between them; the interpreter backstops
the rest ("failure leaves the stretch for the next pass").

## What changed on 2026-10-06 and why
1. **Per-turn structured scene extraction is gone.** It ran 2× per fiction turn (the user's message before the reply, the character's reply after) on
   gemini-3.1-flash-lite, returned ~25–40 tokens ("nothing changed") and paid ~1.2k prompt tokens each time. The tail already holds the detail for 3 turns.
   It now runs **only on a significant moment**: Jev `scene_change` or `time_bound` (cheap, over-fires by design). Its job is where/when/journey state that
   code acts on (Sophie: "bus to Cambridge, 11:30" → dead-reckoned arrival) and the episode-close trigger.
   *Known cost:* a bare location statement with no time and no Jev flag ("I'm at the office") is not captured structurally; it lives in the tail, the narrative
   and the next interpreter pass. Watch it in the digest.
2. **The character's own story proposals are no longer extracted per reply.** They could never move a scene the user set; the narrative carries what she did.
3. **The scene narrative is batched** (Cortex buffers each exchange; one rewrite per 2 exchanges, immediate when Jev flags a significant moment). It replaces
   the structured now/unresolved/transient/changed/spent lines in the prompt with one paragraph (older than 3h → structured state again, flagged `scene_narrative_stale`).
4. **Interpreter cadence 3 → 8 turns** (`CORTEX_CHECKPOINT_EVERY_TURNS`), episode/session ends and time-bound triggers unchanged. The bridge is what makes this safe.
5. **Every model call is tagged** with the module that asked (`X-Title: companion-runtime:<module>` / `synapse-cortex:<module>`, OpenRouter log "App" column).

Per exchange, outside the foreground: before ≈ **$0.0027** (extractors $0.0008, narrative $0.0005, Jev, interpreter ~$0.0013 amortised); after ≈ **$0.0010–0.0012**.

## Product split
* **Sophie** — structure stays where code acts: operational items, journeys, objectives (interpreter + flagged extractor).
* **RPD2** — names, claims, prose continuity. It never pays for structure only Sophie consumes.

## Questions we were not asking
* **Where does hot-path time actually go?** Measured foreground turns 8–20 s wall in-process while the foreground model call itself was 3–4 s; digest p50 28 s.
  Extractors ran in parallel and never cost latency. The next latency work is the pre-reply chain (Cortex probe/hydrate, Honcho reads, Jev), not the post-reply calls.
* **What is Honcho's deriver costing?** It runs an LLM per message and is not visible in these numbers.
* **Is the interpreter's prompt cache-friendly?** Stable prefix (system prompt) first is already the case; verify `cached_tokens` once calls are tagged.
* **Is the narrative better than structured fields for the speaking model?** Hypothesis, to be tested by replies at the same cuts (lab, no scoring).

## What to watch (digest)
`scene_narrative_stale` rate; `unseen_gap` and `unabsorbed` at interpreter cadence 8; entity materialisation latency for invented names (roster); journeys captured
for Sophie; OpenRouter spend by `X-Title`.

## Tests for the Gemini lab
Prose vs structured scene at the same marked cuts; interpreter cadence 3 vs 8 on the Elena walkout transcript (does the Chicago claim still exist, and when?);
flagged vs unflagged extractor on a bare location statement.
