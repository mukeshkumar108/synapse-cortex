# Historical replay lane

This is deliberately a small adapter, not an evaluation platform. It exports
recorded messages from a source database under a read-only transaction, then
feeds completed source sessions/scenes chronologically through today's V2
session reconstruction and bounded apply path.

Replay never uses the configured Cortex database. `run` requires a new SQLite
path, refuses to overwrite it, and uses a `replay:` workspace plus a stable
lane session id so current session-scoped Cortex rows carry across historical
boundaries. Original session/message ids and timestamps remain in the report.
Raw exports, reports, and replay DBs belong under gitignored `replay-private/`.

```bash
./.venv/bin/python scripts/historical_replay.py export \
  --source sophie --env-file ../test-starter/.env \
  --user-id USER --persona-id PERSONA \
  --limit 8 --out replay-private/sophie.json

./.venv/bin/python scripts/historical_replay.py export \
  --source rpd2 --env-file ../rpd2/.env.local --url-key BK_POSTGRES_URL \
  --chat-id CHAT_UUID --idle-minutes 30 --out replay-private/rpd2.json

./.venv/bin/python scripts/historical_replay.py run \
  --input replay-private/sophie.json \
  --db replay-private/sophie.sqlite \
  --out replay-private/sophie-report.json
```

RPD2 scene boundaries are observational only: a scene rolls over at a recorded
gap of 30 minutes or more. Sophie uses explicit source `Session` rows and only
messages whose metadata retains that session id. No unlinked message is guessed
into a session.

Each boundary records the full provenance-bearing transcript, reconstruction
result, bounded apply/defer decisions, post-session snapshot, human-readable
state diff, and conservative lexical leads into the future transcript. Lexical
leads are navigation aids, not semantic scores.

Known constraint: today's consolidator reads at most 40 turns / 6,000 transcript
characters per boundary. The report marks possible truncation; the adapter does
not manufacture sub-session boundaries to hide it.
