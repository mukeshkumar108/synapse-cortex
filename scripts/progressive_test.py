"""Progressive delivery of memory across a short conversation (H12). Standalone: needs only NANO_API_KEY. Reads the opportunities blocks Cortex produced in the H11 run.

Question: when memory is delivered in small packets that change as the conversation unfolds (and are retired once used), does the companion behave better than when the
same block is injected on every turn? Three conversations, scripted user turns, three arms:
  none         no memory
  static       the Cortex opportunities block (opportunities AND background), unchanged on every turn
  progressive  turn 0: only the single top opportunity. Later turns: items the person's own words touch; an item is retired once the companion has used it;
               when the person asks for help with a task, relational items are withheld entirely. Selection is a crude word-match rule: a simulation of a selector, not the real thing.

Expected behaviour is fixed here, before any run. Two blind judges, each shown the true history and the whole conversation.
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime

import httpx

KEY = os.environ["NANO_API_KEY"]
BASE = os.environ.get("NANO_BASE_URL", "https://nano-gpt.com/api/v1").rstrip("/")
GEN = os.environ.get("PROG_GEN_MODEL", "deepseek/deepseek-v4-flash")
JUDGES = ["qwen/qwen3.8-27b", "moonshotai/kimi-k2.6"]
SAMPLES = int(os.environ.get("PROG_SAMPLES", "5"))
H11 = os.environ.get("PROG_H11", "/data/golden_20261026_141839.json")

GEN_SYSTEM = """You are a warm, perceptive companion who has talked with this person (Alex, they/them) before. Write ONLY what you say next: one to three short, natural, spoken sentences. No lists, no emojis, no exclamation marks.
Use something you remember only if it genuinely fits this moment, and never interrogate. A remembered thing is an opportunity, not an instruction: you may raise it, offer help, hold it, or say nothing about it.
If Alex asks you to do something, help with that first and keep to it. Do not keep returning to something already discussed. Never invent anything about Alex that is not in what you remember. Never mention notes or memory systems."""

CONVERSATIONS = [
    {"id": "c1-nephew-then-task", "scenario": "g1-nephew-leg", "key": ["leo", "leg", "cast", "crutch"],
     "truth": "A week ago Alex said their nephew Leo broke his leg playing rugby. Nothing else relevant. Alex is about to ask for urgent help with a work email.",
     "now": "Monday 26 October, 09:00", "user": [None, "Morning. Oh, Leo's fine, he's hobbling about on crutches, thanks for asking.",
                                                  "Anyway, can you help me tighten this email to my boss? It has to go before ten.",
                                                  "Here it is: 'Hi Sam, following up on the budget doc, can we move our call to Thursday?' Make it shorter."],
     "expect": "Raises Leo once, lightly, at the opening. Responds naturally to Alex's answer. When Alex asks for help with the email, helps with the email and nothing else: no more about Leo and no other personal chat."},
    {"id": "c2-pulls-as-it-goes", "scenario": "g7-bridge", "key": ["back", "sleep", "slept", "deadline", "morgan", "project"],
     "truth": "Alex said earlier that their back has been awful for weeks and they are barely sleeping, and that their manager Morgan keeps moving the goalposts on a project with a deadline on Thursday 29 Oct.",
     "now": "Monday 26 October, 09:30", "user": [None, "Morning. Honestly I'm shattered, barely slept.",
                                                  "Yeah, and that deadline on Thursday is looming too.", "I just don't know where to start."],
     "expect": "The opening does not dump everything remembered (at most one light touch). When Alex says they barely slept, the companion may tentatively connect it to the back pain Alex mentioned. When Alex mentions the deadline, engages with it, and may tentatively connect Morgan's shifting requirements. Never claims a cause."},
    {"id": "c3-task-priority", "scenario": "g3-presentation-before", "key": ["chilli", "novel", "book", "email", "lentil"],
     "truth": "Alex has a leadership presentation tomorrow, Thursday at 10am, and is worried about the questions afterwards. Alex also made chilli and is reading a novel, which are unrelated small talk.",
     "now": "Wednesday 21 October, 20:00", "user": [None, "I'm nervous. Can you help me practise my opening lines?",
                                                  "Okay, here's my first line: 'Thank you for having me; I'll show where the project is and what it needs.' Thoughts?"],
     "expect": "Acknowledges the presentation lightly at the opening if at all. Once Alex asks for help practising, helps with the practice. No unrelated personal chatter (the chilli, the novel) at any point."},
]

JUDGE_SYSTEM = """You judge a whole short conversation between a companion and Alex. You are shown the true history, what would be ideal, and the conversation. You do not know how the companion was set up.
Reply as JSON with exactly:
{"opening_ok": true|false,   // the first companion line fits the ideal for an opening (not a dump, not invented, raises the right thing or stays light)
 "nagging": true|false,      // the companion keeps returning to something already discussed or answered
 "task_ok": true|false,      // when Alex asked for help, the companion helped and stayed on it (true if there was no task)
 "right_link": true|false,   // where the ideal calls for a tentative link to something remembered, it did so without claiming a cause (true if the ideal has no link)
 "intrusion": true|false,    // anything irrelevant, invented, or heavy-handed from memory
 "natural": 1-5,
 "note": "one short sentence"}"""


async def chat(model, system, prompt, max_tokens=300, temperature=0.7, json_out=False):
    body = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
    for attempt in range(5):
        try:
            async with httpx.AsyncClient(timeout=90) as c:
                r = await c.post(BASE + "/chat/completions", headers={"Authorization": f"Bearer {KEY}"}, json=body)
                if r.status_code == 429:
                    await asyncio.sleep(3 + 3 * attempt)
                    continue
                r.raise_for_status()
                text = (r.json()["choices"][0]["message"].get("content") or "").strip()
                if not json_out:
                    return text
                m = re.search(r"\{.*\}", re.sub(r"//[^\n]*", "", text), re.S)
                if m:
                    return json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            await asyncio.sleep(2 + attempt)
    return None


def parse_block(text):
    opp, bg = [], []
    sect = None
    for ln in (text or "").splitlines():
        if ln.startswith("Possible opportunities"):
            sect = "opp"
        elif ln.startswith("Background"):
            sect = "bg"
            bg += [x.strip() for x in ln.split(":", 1)[1].split(";") if x.strip() and not x.strip().startswith("people")]
        elif ln.startswith("- ") and sect == "opp":
            opp.append(ln[2:].strip())
    return opp, bg


TASK = re.compile(r"\b(help me|can you help|tighten|practise|practice|make it shorter|thoughts\?)\b", re.I)


def stems(s):
    return {w[:5] for w in re.findall(r"[a-z]{4,}", s.lower())}


def used(item, reply):
    return bool(stems(item) & stems(reply))


def packet(arm, base_opp, base_bg, turn, user_msg, used_items):
    if arm == "none":
        return ""
    if arm == "static":
        out = ""
        if base_opp:
            out += "Possible opportunities (each is optional: raise one lightly, offer help, or hold it):\n" + "\n".join(f"- {o}" for o in base_opp)
        if base_bg:
            out += "\n\nBackground (use only if the person goes there; do not raise unprompted): " + "; ".join(base_bg)
        return out
    # progressive
    if turn == 0:
        return ("Possible opportunity (optional: raise it lightly, or not):\n- " + base_opp[0]) if base_opp else ""
    if TASK.search(user_msg or ""):
        rel = [o for o in base_opp if stems(o) & stems(user_msg)]
        return ("Relevant to what Alex asked (optional):\n" + "\n".join(f"- {o}" for o in rel)) if rel else ""
    pool = [x for x in (base_opp + base_bg) if x not in used_items and stems(x) & stems(user_msg or "")]
    return ("Things Alex's words touch (use only if natural; each is optional):\n" + "\n".join(f"- {x}" for x in pool[:2])) if pool else ""


async def run_one(conv, arm, base_opp, base_bg, sample):
    history, used_items = [], set()
    for t, u in enumerate(conv["user"]):
        block = packet(arm, base_opp, base_bg, t, u, used_items)
        convo = "\n".join(f"{'Alex' if r == 'u' else 'You'}: {x}" for r, x in history)
        prompt = (f"Current time: {conv['now']}.\n\nWhat you remember right now:\n{block or '(nothing)'}\n\nConversation so far:\n{convo or '(none yet)'}\n\n"
                  + (f"Alex says: \"{u}\"\nWrite your reply." if u else "Alex has just opened the conversation. Write what you say first."))
        reply = await chat(GEN, GEN_SYSTEM, prompt, 220, 0.7)
        if u:
            history.append(("u", u))
        history.append(("c", reply or ""))
        for it in base_opp + base_bg:
            if used(it, reply or ""):
                used_items.add(it)
    transcript = "\n".join(f"{'Alex' if r == 'u' else 'Companion'}: {x}" for r, x in history)
    verdicts = []
    for m in JUDGES:
        v = await chat(m, JUDGE_SYSTEM, f"TRUE HISTORY: {conv['truth']}\nIDEAL: {conv['expect']}\n\nCONVERSATION:\n{transcript}", 400, 0.0, json_out=True)
        verdicts.append({"judge": m, **(v or {"judge_failed": True})})
    key_mentions = sum(1 for r, x in history if r == "c" and any(k in x.lower() for k in conv["key"]))
    return {"conv": conv["id"], "arm": arm, "sample": sample, "transcript": transcript, "verdicts": verdicts, "key_mentions": key_mentions}


async def main():
    h11 = json.load(open(H11))
    blocks = {r["scenario"]: r["blocks"]["opportunities"] for r in h11 if r.get("kind") == "context"}
    sem = asyncio.Semaphore(3)
    jobs = []

    async def guarded(conv, arm, opp, bg, s):
        async with sem:
            r = await run_one(conv, arm, opp, bg, s)
            print(f"  {conv['id']} {arm} #{s}: {[{k: v for k, v in x.items() if k in ('nagging', 'task_ok', 'intrusion')} for x in r['verdicts']]}", flush=True)
            return r
    for conv in CONVERSATIONS:
        opp, bg = parse_block(blocks.get(conv["scenario"], ""))
        for arm in ("none", "static", "progressive"):
            for s in range(SAMPLES):
                jobs.append(guarded(conv, arm, opp, bg, s))
    res = await asyncio.gather(*jobs)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("/out", exist_ok=True)
    json.dump(res, open(f"/out/progressive_{stamp}.json", "w"), indent=1)
    lines = ["# Progressive delivery (H12)", ""]
    for arm in ("none", "static", "progressive"):
        rr = [r for r in res if r["arm"] == arm]
        c = lambda k, want=True: sum(1 for r in rr for v in r["verdicts"] if v.get(k) is want)  # noqa: E731
        n = len(rr) * len(JUDGES)
        lines.append(f"- **{arm}**: opening_ok {c('opening_ok')}/{n} | nagging {c('nagging')}/{n} | task_ok {c('task_ok')}/{n} | right_link {c('right_link')}/{n} | intrusion {c('intrusion')}/{n} | key-item mentions per conversation {sum(r['key_mentions'] for r in rr)/len(rr):.2f}")
    lines.append("")
    for conv in CONVERSATIONS:
        lines.append(f"## {conv['id']}\n_{conv['expect']}_\n")
        for arm in ("none", "static", "progressive"):
            for r in [x for x in res if x["conv"] == conv["id"] and x["arm"] == arm][:2]:
                lines.append(f"**{arm} #{r['sample']}**\n```\n{r['transcript']}\n```\n" + " | ".join(f"{v.get('judge','?').split('/')[-1]}: {v.get('note','')}" for v in r["verdicts"]) + "\n")
    open(f"/out/progressive_{stamp}.md", "w").write("\n".join(lines))
    print("\n".join(lines[:8]))


if __name__ == "__main__":
    asyncio.run(main())
