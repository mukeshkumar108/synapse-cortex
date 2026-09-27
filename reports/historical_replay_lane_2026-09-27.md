# Historical replay lane — first tranche (2026-09-27)

## Sources actually found

- Old Sophie / `test-starter` Postgres is reachable read-only. It contains
  225 `Session` rows (2026-01-23 through 2026-04-30), 2,020 `Message` rows,
  plus `SessionState`, `SessionSummary`, `Memory`, `SummarySpine`, `Todo`, and
  ingest/librarian traces. One user/persona trajectory spans 192 sessions / 771
  recorded turns. Only 462 messages retain an explicit session id in metadata.
- New Sophie / `llm-agent-test` has a complete Neon connection manifest, but
  every saved database URL currently fails authentication. It was not used.
- RPD2 live Postgres is reachable but empty (0 chats/messages). Its configured
  backup Postgres is reachable read-only and contains 124 chats / 4,217
  `Message_v2` rows dated 2026-09-11 through 2026-09-26. Top chats contain
  80–302 messages. `ContinuityAttempt` and `ShadowRuntimeTurn` also survive in
  the backup.
- RPD2 also has local preserved Markdown transcripts and a 115-turn redacted
  fixture. Synapse V3 has Ashley evidence exports and evaluation artefacts;
  these are useful derived evidence but are not treated as raw Sophie history.
- No remote VPS was mutated or needed for this tranche. No unlinked Sophie
  message was assigned to a session by time guesswork.

## Mechanism

`scripts/historical_replay.py` has two operations:

1. `export` opens historical Postgres inside an explicit read-only transaction
   and produces provenance-bearing corpus JSON. Sophie uses source session ids.
   RPD2 uses source chat ids and observed >=30-minute timestamp gaps as scene
   boundaries.
2. `run` refuses to overwrite its output DB, creates a fresh SQLite Cortex,
   and replays boundaries chronologically through V2 session reconstruction and
   bounded apply. One stable internal lane id carries today's session-scoped
   Cortex state; source session/message ids and timestamps remain in the report.

Per boundary the report contains the full transcript, validated consolidation
proposal, apply/defer report, snapshot, diff, coverage/truncation status, and
conservative lexical leads into later transcript evidence. Private corpora,
reports, and databases live under gitignored `replay-private/`.

## First Sophie replay

Corpus: seven explicit linked sessions from 2026-04-29–30, 448 messages total
(4, 38, 16, 14, 24, 176, 176 messages).

- Four boundaries completed model reconstruction; three failed closed on
  malformed/truncated model JSON. One successful final boundary intentionally
  held empty. Existing state held on every failure.
- A repeated dentist reminder became two pending ASK commitments, one polluted
  with an internal task id (`manual-mokbaq1a`). Later transcript text refers to
  the same dentist matter, but replay neither merged nor resolved the pair.
- Earlier sessions containing the same reminder were marked entirely
  incidental. The same evidence therefore moved from “nothing durable” to two
  durable duplicates depending on surrounding session context.
- The two 176-message sessions exceed today's 40-turn / 6,000-character input
  caps and are marked as possibly truncated rather than silently split.

## First RPD2 replay

Corpus: Elena chat `8ae17baf-ce93-4917-a3df-d81adafb175f`, 243 messages,
four observed idle-gap scenes (129, 20, 52, 42 messages).

- The opening betrayal/rupture/divorce scene produced 12 incidental ops and no
  durable relational injury, expectation, repair need, or unresolved matter.
  The shared substrate forgot the highest-value state in the corpus.
- A later scene created open loops for both `User's struggle with sleep and neck
  ache` and `User woke up happy`. Future transcript lexically references both,
  but the positive moment was retained as an unresolved loop alongside the
  genuine health concern.
- The next two scenes affirmed both loops. No suppression or resolution was
  applied, demonstrating stale-state ratcheting and trivia/positive-state
  retention in a relational corpus.
- Scene 3 proposed a new proactivity/authenticity question, but its creation
  guard did not apply it. This is visible in the accepted-vs-applied report.
- Every RPD2 scene exceeded a current transcript cap by turns or characters;
  the opening scene is especially lossy at 129 messages.

## What this enables next

- Select five deep chats by measured length/scene count instead of authoring
  new examples.
- Compare a post-boundary snapshot directly with later recorded evidence.
- Audit forget/retain/duplicate/stale/resolution/suppression behavior without
  touching production Cortex.
- Test alternative consolidator models or caps on exactly the same provenance-
  stable corpus.
- Add attention/runtime packet inspection entering the next boundary; the
  stored historical timestamps and isolated database make this straightforward.

## Biggest corpus limitation

Boundary completeness is the largest limitation. Most old Sophie messages lack
an explicit session id (only 462/2,020 are safely linked), while long RPD2 chats
have scene changes but no authoritative semantic scene markers. The adapter can
use explicit Sophie sessions and observed RPD2 idle gaps, but it must not invent
where the missing history belongs. Today's 40-turn / 6,000-character
consolidation cap compounds that incompleteness on the longest real sessions.
