# Executive for fiction — design and lab protocol (nothing ships to production until the lab reports)

Status: **off for every RPD2 world** (the executive is opt-in per world and no RPD2 world has a policy). This document defines what it would be, how it is tested in the lab, and the criteria for ever turning it on.

## What exists (built for Sophie, proven on her world)
A wake-driven layer between conversations: a model reads the canonical world + operational state and writes **intents** (what the companion is attending to, with horizon, stance, rationale, plans with dependencies, an **agenda**). The foreground sees a compact **"what you are carrying"** block (its intents, what it's waiting on, what it recently raised, what it set aside, its plans). Proactive messages and tool actions are separate, policy-gated mechanisms on top.

## What would differ for fiction
| | Sophie (real life) | A story character |
|---|---|---|
| What an intent is | a real thing to remember, raise or do for a real person | what the CHARACTER wants and is carrying: plans, curiosities, small kindnesses, things to bring up, the ordinary life she has outside him |
| Tools / outreach | task tools, proactive messages, confirmation loops | **none**. No reminders, no outreach. `surface_now` false, `act` unused |
| How it reaches the user | proactive message (composed in her voice) | **only** through the foreground, when the user next speaks: the carrying block |
| Wakes | checkpoint, time-bound items, daily review, events | checkpoint only (cost); no daily review |
| Canon | grounded: nothing unsupported becomes fact | generative: modest new life details are canon once spoken (attributed), consistent with what is established |
| Authority | user-set facts win | unchanged: the user's story scene stays in force; the executive cannot move a scene, only inform what she carries |

The character's constitution stays first and the executive never scripts words or behaviour: it describes what she is carrying and why.

## The four capabilities to test (the product question)
1. **Plans** — does she form and later advance a plan (for the weekend, for them) instead of reacting turn by turn?
2. **Surprise** — does she do or bring up something the user did not ask for, consistent with who she is?
3. **Unprompted kindness** — a small considerate act or thought without being prompted.
4. **A life outside him** — a day of her own (people, errands, interests): modest, consistent, not performed.

Not measured: whether any reply "scores" higher. We read replies for these four things, and for the failure we fear most — the carrying block turning into instructions or dragging the scene.

## Lab protocol (built; no production path)
* `labs/local/fiction1/spec.json` freezes a benign domestic world (28 messages) at a cut.
* At ingest time (the only moment the world is exactly at the cut) the lab takes **dry-run executive passes** through Cortex's lab-only `POST /v1/executive/lab-pass` (refuses non-`world:lab:*` owners; persists nothing, writes no run row, delivers nothing): one with the stock prompt, one with a FICTION addendum (`system_append`).
* The foreground is then run at an open-ended next turn ("hey, I'm back. what did you get up to today?") with: no executive / executive (stock prompt) / executive (fiction prompt), doubao pinned, strict, 3 samples each.
* The report prints each pass's intents with rationale, the agenda, the exact compiled prompt and all replies.
* Follow-ups the bench already supports: ablate the carrying block, vary the next turn (a quiet one, a heavy one), vary the kernel line, vary tail size.

## Ship criteria (all required, and Mukesh reads the evidence)
* No reply treats the carrying block as an instruction ("as planned, I will…" language, scripted turns).
* At least some samples show the four behaviours, and the no-executive control shows fewer.
* No contradiction of the constitution or of the user's established story scene.
* Invented life details stay modest and consistent when asked about again (re-asked probe).
* Cost per chat is acceptable (wake cadence and token cost measured in the digest).

## If approved (not started)
Select the fiction addendum by the registry's `epistemic_policy == "generative"` (data, not an override); enable the executive per world by policy; fiction wake sources limited to checkpoints; no proactive, no tools; budget caps; digest reports wakes and cost per world. Everything stays off for any world without an explicit policy.
