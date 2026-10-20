# What actually runs on a Sophie turn (audited 2026-10-20 on the live Runtime)

Method: six real turns through the deployed Runtime; per turn the Runtime's model-call ledger (`model_calls`), `execution_metadata`, the rendered prompt blocks, and the Cortex
logs for the same minute; plus 30 days of the ledger grouped by product. Script: `scripts/demo/trace_turns.py`.

| Component | Runs when | Model call | Writes | Verdict |
|---|---|---|---|---|
| Jev (`jev-1.13`) | every turn, before the reply | yes, ~0.35 s | routing flags | intended |
| Foreground model | every turn | yes | the reply | intended |
| Rolling continuity | after the reply once there are ≥6 messages (every 3 turns); checkpoint at ~25 messages; reconcile over all checkpoints | yes, async, cheap model (**not in the `model_calls` ledger**: it calls the provider directly) | `rolling_continuity` in the sitting state | intended; was being erased every turn (fixed) |
| **Scene narrator** (`/v1/world/narrate`, Cortex `scene_narrative`, a paid OpenAI model) | every turn once the raw tail starts to evict (turn ≥4), 3 calls in 6 turns | yes, ~2k tokens each | `narrative` (a ~1,000-character "picture"), anchors, standing/sitting requests in the sitting state | **retired for Sophie**: its output never reached the prompt (checked: none of the picture or anchor text appears in the final prompt) and its writes erased the rolling account. Still runs for products on the legacy scene assembly (RPD2) |
| Live scene sensing (`live_scene`, flash-lite) | only when the scene changes (~4% of Sophie turns) | yes, blocking ~1 s | the "[CURRENT SCENE]" block | keep for now; it is the only source of location |
| Headspace writer | RPD2 playground only (162 calls in the ledger, none for Sophie) | yes, async | RPD2 headspace | not Sophie's; leave |
| Embeddings | recall / evidence writes | yes, async | evidence index | needed for `recall` |
| Cortex reads (world packet, operational view, exposure report, gap block) | every turn | no | none (exposure counts) | intended |
| Cortex consolidation | sitting end / hand-off / idle | yes, background (2-4 min) | the memory | intended; duplicates removed earlier today |

Result for a Sophie turn now: Jev + foreground, plus rolling continuity in the background every third turn, plus Cortex reads. Nothing else ran in the six-turn trace after the change
(0 narrator calls). Not audited: the Solo/attention schedulers on the Cortex side (feature, not conversation path) and Bloom's non-unified path (still uses the legacy scene assembly and narrator).

Open point worth a decision: the rolling-continuity model's calls are invisible to the cost ledger; routing them through it would make the cost of the summariser visible.
