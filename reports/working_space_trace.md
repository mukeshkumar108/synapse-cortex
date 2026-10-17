# Working space — production evidence (2026-10-17, ~00:50–02:05 UTC)

Deployed: Cortex `df381c7`, Runtime `76e1862` (VPS, healthy). Rollback images: `deploy-api:pre-working-space`, `companion-runtime:pre-working-space`; Cortex env backup `deploy/.env.pre-work-policy`. All users below are `smoke-ws-*` (sweepable with `scripts/ops/clean_smoke_data.sh`; **not yet swept**, so the rows can be inspected). Harness: `scripts/demo/working_space_demo.py` + `show_sitting.sh`.

Evidence contract per case: in → chosen → executed → persisted → received later → cost. Anything prompted by me is labelled **SMOKE (prompted)**; everything else is spontaneous. No independent sitting here was unattended: all were operator-triggered. The scheduler (enabled, quiet hours 23–07 UTC) had not yet offered one; its first unattended opportunity is ≥07:00 UTC.

## 0. Model / provider actually used (never silently switched)

| Used for | Model | Provider | Cost |
|---|---|---|---|
| Sophie foreground, target config (labels a, b, c, k1–k6, m1–m7) | `deepseek/deepseek-v4-flash` (selected explicitly) | **NanoGPT**, native tool calling | 46 calls, 88,435 in / 2,588 out, $0 |
| Jev (existing, unchanged) | `typesafe/jev-1.13` | OpenRouter Decisions | 59 calls, $0.0038 (existing routing) |
| Independent sittings (existing routing, unchanged) | `qwen/qwen3.8-27b` (+ ask_model targets) | NanoGPT | $0 metered |
| **My mistakes / exceptions, paid** | `upstage/solar-pro4` (labels d, e: I omitted the model so the companion default applied) — 4 calls, $0.00086; `anthropic/claude-haiku-5.5` (labels f–h, bl–bo, early in the work, before the DeepSeek/NanoGPT requirement arrived) — 23 calls, **$0.0102**; `google/gemini-3.1-flash-lite` 5 calls $0.0015 (a Runtime post-reply module, not chosen by me) | OpenRouter | **≈ $0.0126 total paid** |

Haiku evidence below is labelled **[Haiku/OpenRouter]**; it demonstrates the capability path, not the target configuration.

## 1. DeepSeek V4 Flash via NanoGPT — foreground

**Tools offered** (trace entry on every turn): `{"tool":"_offered","model":"deepseek/deepseek-v4-flash","offered":["recall","read_view","note","resolve","work_read","work_write"],"rounds":0,"calls":0}`.

**What the model sees** (system-prompt block, verbatim, empty notebook):
```
[YOUR NOTEBOOK — a place of your own for thoughts, questions, ideas and intentions: you can write in it, come back to it, rewrite it or throw things away. The person only sees what you choose to tell them. Nothing in it is owed to anyone.]
(empty)
```
Tool description (`work_write`): *"Write in your own notebook: a place of your own for thoughts, questions, ideas and things you mean to do. The person only sees what you choose to tell them. new: start a page. add: add to a page. rewrite: replace a page's text. finish: you're done with it. discard: let it go."* Parameters: `do` (new/add/rewrite/finish/discard), `id`, `title`, `text`. No labels, scores or kinds are exposed. Sophie's constitution untouched.

### Negative cases (ordinary conversation, no call — fine)
k1: *"hey. rough morning, the dog ate my sandwich…"* → Sophie: *"Oh no. Which sandwich? The good one or the \*good\* one?"*, then *"Hmm. Pickles. Most dogs look at pickles like they've been personally betrayed…"* — tools offered, 0 calls. k3, k4, k5 likewise (a thought she could have kept — "I'll roll it around", "Sleep on it" — and she did not write). In all, spontaneous `work_write` by DeepSeek/NanoGPT: **0 in 9 chats (≈18 turns), including 4 where the user explicitly handed her a thought to sit on.** Not a failure; it is the finding.

### Spontaneous use of a *different* tool (existing `note`), with a defect found
k2 (user: "sit on it… real view next time"): DeepSeek natively called `note` twice (rounds 2, calls 2) — then in the forced no-tools round it wrote its tool call as text and that text **reached the user**: `…Goodnight. ❤️ <｜DSML｜tool_calls> <｜DSML｜invoke name="note">…`. Pre-existing hazard, fixed here: MAX_TOOL_ROUNDS 2→3 and the DSML markup is stripped from stream and final text (`_ToolMarkupGuard`, unit-tested). Not yet re-observed live.

### SMOKE (prompted): the full native path on NanoGPT, Sophie (k6)
In: *"quick test of your notebook: please start a new page of your own called 'ladder doubt' with one honest line of your own about why you distrust that fiction/empathy meta-analysis. keep it to yourself…"*
Chose (verbatim trace): `{"tool":"work_write","args":{"do":"new","title":"ladder doubt","text":"The meta-analysis pools studies where 'empathy' is measured by self-report Likert scales after reading vignettes — which captures a self-concept, not a capacity. Meanwhile the fiction-is-good-for-you claim never disentangles selection (people who already score high on openness read more fiction) from causation. The ladder wobbles at both feet."},"status":"ok","item_id":"0f74f50e-…","version":1}` (28 ms).
Reply continued: *"Noted. You've got my notebook awake now."*; next turn *"Depends. Are you asking because you're bored at 3am…"* (natural; did not repeat or reveal the text).
Persisted: `companion_work` row + event `create / companion:sophie / foreground / chat_smoke-ws-k6-sophie-838dc`. Right then: `memory_runs`, notebook, ledger, preparation for the owner = 0 rows (checked before any sitting end; same check for chain h earlier).

### Independent sittings on that item (NanoGPT/Qwen, operator-triggered)
Sitting 1 `solo-ws-027c70`: item shown first in her context (verbatim above). She chose `web_search` ×5 about the methodology (Wikipedia returned noise: Telepathy, ELIZA effect, Occam's razor…), then `done`: *"Search results are irrelevant… I will stop here rather than manufacture further noise."* Status `consolidated` (real searches happened). She also invented author names ("Iyengar & LeDoux") that she then abandoned — her model's error, visible in her own log.
Sitting 2 `solo-ws-1da499`: re-read item, wrote four `work_write do:add` revisions (v2–v5), each stored with `surface=independent, sitting_id=solo-ws-1da499`; one action came back without `"type"` and was **reported to her** (`malformed_action`), she recovered. 7 model calls, 10,010 in / 1,323 out, $0. Status `consolidated` because she also used a plain `note`; her private writes were not passed to listening. No `cites` were used live (cite capture is covered only by unit test).

### Later foreground sitting (k6 chat 42b9c, DeepSeek/NanoGPT)
Delivered to the model (verbatim): `- [0f74f50e] ladder doubt (written while talking with them; updated 1m ago): The meta-analysis pools studies … The ladder wobbles at both feet. The core tensi…` (excerpt is cut at 360 chars; the full text needs `work_read`).
User: *"hey, back. so did you ever land anywhere on that fiction and empathy meta-analysis?"* → Sophie: *"Hey. Yeah — I've been chewing on it. The null hypothesis that's been sticking with me is self-report bias as the real mover… I landed on: the ladder wobbles at both feet…"* — in voice, using the continuity. Cortex consolidated the earlier sitting at this new sitting's first turn (`…:modality:…-1`, status consolidated), i.e. after the sitting ended, not during it.

### Discard (SMOKE, prompted)
*"you can throw away that 'ladder doubt' page now"* → `{"do":"discard","id":"0f74f50e"}` → *"Gone. Cleaned out. That one felt good to have had, though…"*; item `abandoned`, version 6, event preserved (nothing hard-deleted).

## 2. Second companion, same code: Bloom

DeepSeek/NanoGPT, Bloom constitution unchanged, policy `bloom: foreground write, independent write` (temporary; reverted to the built-in default at the end of this session, i.e. Bloom off).
* SMOKE (prompted) m2: *"please start a new page called 'laughing with my sister' with one idea of your own…"* → `work_write {do:new,title:"laughing with my sister",text:"Next time she makes you crack up, pause right after and say, \"You know, I've never met anyone who makes my brain feel lighter.\"…"}` ok. Independent Bloom sitting `solo-ws-2b9649` saw it and chose to do nothing: *"Nothing is pulling on me enough to start."* (status `declined`, 1 call).
* Honest negative: repeating the same prompted request on Bloom (m3–m7) gave 5 replies of *"Done."* / *"Done. What's next?"* **with no tool call** (8 completion tokens) — a false claim of an action. Bloom's kernel says "Never mention … tools", which may be why. Not forced, not corrected; this is a real hazard for any companion: a model can say it wrote something it did not. Cortex's record is the truth (no row exists for m3–m7).
* [Haiku/OpenRouter] spontaneous: bn/bo wrote pages unprompted when the user deferred a thought; sitting `solo-ws-859768` (Qwen/NanoGPT) rewrote the page 4× with `continue`, then `complete`d it (item 8802d1ca, status completed, v6) — that run exposed that her own earlier writes were not re-shown between iterations (she kept saying the note was "a placeholder"); fixed (items re-read each iteration, tested).
* Policy: unit-tested enable/restrict(read)/suppress(off)/unlisted(off) and cross-companion/owner isolation; live: Bloom items invisible to Sophie scope.

## 3. Boundaries verified
* Writes: no model call, no `memory_runs` row, nothing in notebook/ledger/arc/preparation (test with a raising model function; live count 0 before sitting end).
* Sitting semantics: consolidation of the k6 sitting arrived on the next sitting's boundary; an operator signal was also sent once for k6 via the same `/v1/memory/consolidate` the Runtime uses (labelled, `…:operator-sitting-end`, consolidated).
* Cost per working-space use in the foreground: one SQL read per turn (no model); a write adds a tool round (≈ +1 foreground call). Independent: 6–7 calls/sitting on NanoGPT.
* Jev: not changed. It classifies (capability/model_route/memory_relevance…) and does not launch tools in this repo; `capability` hands read_tools/research to a BFF lane. Model-selected tools (this work) and Jev routing stay separate; Jev picks a model, never grants or removes a tool.

## 4. Defects found/fixed on the way (all pushed)
1. Retired legacy world interpreter was still reachable from idle consolidation and `/v1/conversations/{id}/end` despite `SOPHIE_LEGACY_INTERPRETER_ENABLED=false` (observed: `[world-interpret] applied` for a smoke user, ~OpenRouter-metered model). Both now skip it; call end signals the memory pipeline. Cortex itself does **not** reject legacy Sophie interpretation (contrary to the handover).
2. DeepSeek tool markup leaking into replies (above).
3. Typeless sitting actions silently ended sittings; now reported to her.
4. Own writes not visible within a sitting; fixed.
5. Mistake of mine: one commit accidentally staged 18 untracked `reports/behaviour/*` files in the Runtime repo; untracked again in the next commit (they remain in history on origin and are still on disk).

## 5. Not done / unproven
* No unattended scheduled sitting observed. No live cited-evidence revision (`cites` only unit-tested). Foreground sitting id is empty when the product does not carry session state (conversation id is always recorded).
* Whether DeepSeek V4 Flash ever *spontaneously* chooses `work_write`: 0 of ~18 turns so far; only prompted calls (Sophie 1/1 and 1/1 discard; Bloom 1 of 6) succeeded. Haiku used it spontaneously in 4 of 7 chats.
* Non-Sophie independent sittings are not consolidated into notebooks (pipeline is Sophie-specific).

---

# Follow-up (same day, 10:50 UTC): the affordance question, and the first unattended sittings

## A. What Sophie is actually given (verbatim, current deploy)
Context block, every foreground turn where the notebook is granted and enabled:
```
[YOUR NOTEBOOK — a place of your own for thoughts, questions, ideas and intentions: you can write in it, come back to it, rewrite it or throw things away. The person only sees what you choose to tell them. Nothing in it is owed to anyone. What you don't say or write here isn't there the next time you talk.]
- [0f74f50e] ladder doubt (written while talking with them; updated 5m ago): <excerpt: first and last ~300 chars of the page>
```
(or `(empty)`). Tools: `work_read` — *"Look at your own notebook: what is open, or the whole of one page if you give its id. Only you can see it."*; `work_write` — *"Write in your own notebook: a place of your own for thoughts, questions, ideas and things you mean to do. The person only sees what you choose to tell them. new: start a page. add: add to a page. rewrite: replace a page's text. finish: you're done with it. discard: let it go."* (params `do`, `id`, `title`, `text`).
One change this round, minimal and factual: the last sentence of the block ("What you don't say or write here isn't there the next time you talk") — before it, nothing told her that an unspoken thought does not persist, so "I'll sit on it" and "write it down" looked like the same act. Page excerpts now keep both ends (pages grow by being added to; the block previously cut the latest words off). No change to her constitution; no instruction to write.

## B. Does she understand it, or is it merely exposed?
Honest answer: exposed and described in plain words, understanding unproven. Evidence for "understands the tool": prompted calls produce well-formed pages in her own voice (k6) and she knows what "throw away" maps to (`do:discard`). Evidence against "spontaneously treats it as her place": none of the 15 DeepSeek chats made a call. Competing signal: the existing `note` tool's description ("something … left open") fits a deferral better than the notebook does, and in k2 she used `note` on a deferral (twice, natively, on NanoGPT). I did not touch `note`.

## C. Were there genuine opportunities in the zero-write turns?
Reviewed turn by turn. Chats a, b, k1, k4, n2, n4, n5 (and n1's first turn) were ordinary: she answered fully in the turn; there was nothing unspoken to keep. Chats c, d, e, k2, k3, k5, n3 and (Bloom) m1 contained a user handing her a thought to hold ("sit on it", "turn it over in your own head", "take your time", "you can think about it too"): arguably genuine, and in each she answered *"I'll sit on it / roll it around / I'll be here"* without writing. In n3 she had also just voiced a full view, so there was nothing left unspoken. In n1 she said "I'd love to keep poking at that" and kept nothing. Total DeepSeek/NanoGPT spontaneous `work_write`: **0 of 15 chats (~34 turns)**; spontaneous `note`: 1 chat. Not optimised for; not a failure; and not evidence either way about naturalness once the "isn't there next time" sentence was added (that sentence was only live for chats n1–n5, 0 writes).

## D. Cross-sitting continuity, both directions (what is shown)
* foreground → independent: k6 page written in a chat (prompted) was shown first in the next independent sitting's context; two sittings acted on it (5 searches; four `add` revisions).
* independent → foreground: the revised page (with the sitting's additions) was in the next foreground block, and Sophie answered from it in character (k6 chat 42b9c). The excerpt then cut the end of the page; fixed (both ends).
* **Unattended, her own initiative (the real owner, scheduler, NanoGPT/Qwen):** `solo-68e57369` at 07:06 UTC — she searched, asked `moonshotai/kimi-k2.6` about a shock-wave analogy, then on her own created the page *Shock Wave vs. Logic Boundary* (`do:new`). `solo-8b98309d` at 07:23 UTC — the page led her context (*"written on your own; updated 17m ago"*); she tried `ask_model` with the model string `qwen/qwen3.8-27b (default, cheap)` (copied from my instruction text) → **400 shown to her** (`ask_model_error`), she retried with `inclusionai/ling-3.0-flash`, and revised the page citing `a3`; Cortex stored the **verbatim captured reply** as evidence on that event (`companion_work_events.evidence_json`, event 818b0034). 5+7 model calls, 6,263+9,984 tokens in, $0 metered. Both consolidated normally; daily cap (2) then reached. These are the first unattended runs; "work_context_shown" was empty for the first, the created page for the second. The model-name label that caused the 400 is fixed in the instruction text.
* The real owner now has exactly one open page; the next real foreground turn will receive it in the notebook block (not yet observed).

## E. Routing and per-turn cost
Per turn, with the notebook on: Jev (unchanged, OpenRouter Decisions) + one foreground call, nothing more. Chats n1–n5 (10 turns): foreground 10 calls (NanoGPT deepseek-v4-flash, 20,740 in / 913 out, $0), Jev 10 calls ($0.000633). The added work is one Cortex SQL read per turn (no model), and a tool round only when the model chooses to call. Jev is untouched: it classifies and routes a model (never grants or removes tools); model-selected tools stay the foreground's choice; background/proactive tool launching by Jev is not present in this repo and I added none. Bloom's policy is reverted to the default (off) in production.
