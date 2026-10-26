# Opportunities packet contract, version 1

Status: implemented behind no flag as a READ-ONLY endpoint (`GET /v1/memory/opportunities`); nothing consumes it yet. Evidence: `reports/h11_golden_moments_2026-10-26`, `reports/h12_progressive_2026-10-26`.
Why it exists: the companion should get a small, moment-sized piece of what Cortex holds, not a biography. A packet is a temporary piece of attention; it is never part of the companion's prompt or personality.

## One shape, however it is made

The same packet is produced today ON DEMAND from the maintained records (the world layer and the ledger). Later it may be PREPARED AHEAD OF TIME (per part of the day, refreshed when a significant event touches it). Consumers must not be able to tell the difference: `built_at` and `valid_until` are the only hints. A runtime written against this contract today keeps working unchanged when preparation arrives.

```json
{
  "version": 1,
  "id": "3f9c0a12b7de",
  "stage": "opening | moment | survey",
  "purpose": "reconnect | touched | task_support | survey",
  "built_at": "2026-10-26T09:00:00+01:00",
  "valid_until": "2026-10-26T15:00:00+01:00",
  "items": [
    {"id": "world:<entity id> | ledger:<situation key>", "kind": "opportunity | background", "text": "Leo breaks his leg in rugby",
     "when": "Sat 17 Oct, 9 days ago", "said": "the person's own last words about it, if any", "stakes": 3, "source": {"system": "world | ledger", "ref": "..."}}
  ],
  "text": "the items rendered as the companion's own thought (opening) or plain facts (moment)",
  "retire": {"packet": "...", "matter": "..."}
}
```

Empty `items` means: give the companion nothing.

## Stages (how a packet is chosen)

- `opening` (re-entry): at most ONE item, the top opportunity. No background list (measured: the list dilutes the one real opportunity).
- `moment`: only items the person's own words touch (`user_text`), at most two. If the person is asking for help with a task (`task=true`, or detected from the text), only items relevant to that task. `used` carries ids already used in this conversation.
- `survey`: everything, as the older single block.

## Rules that every packet obeys (each from a measured failure)

1. Tense comes from DATES, never from stored words. Summaries and timing text are not shown (they carry relative words written days earlier).
2. A candidate needs real stakes; everything else is background. Nothing is ranked on recency alone.
3. No behavioural instruction, no condition, no stance, no privacy marking. At an opening the items are the companion's own thoughts, first person and active ("I want to ask how it has gone"); mid-conversation they are plain facts. Whether and how to raise anything is the product's policy, carried by the persona, never by Cortex. (D-R10)
4. The only boundary honoured is the person's own: an entity they asked not to be prompted about (`suppressed`) is never offered. Their own words about a matter travel with it (`said`), so the model reads the person, not a category.

## Packet life cycle is not matter life cycle

Retiring a packet (its items were used, or the conversation moved on) is NOT retiring the matter. If the person answers "he's having surgery next Thursday", the matter is still developing and may yield a new opportunity later; "he's fine now, all sorted" may resolve it. A matter's life cycle belongs to the ledger and the world records. Exposure and use are recorded separately (existing `POST /v1/memory/world/exposure`, keyed by the item's `source.ref`).

## Five events to record separately (only the last two exist today)

available (Cortex holds it) -> eligible (it fits this moment) -> selected (the runtime chose it) -> shown (the companion was given it; `world/exposure`) -> used (the companion acted on it; engagement).
