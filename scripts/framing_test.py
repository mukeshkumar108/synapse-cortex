"""Framing of the opening packet: does the companion take what is on its mind, and does it stay human about it?
Three framings of the SAME facts, no restraint rules in the system prompt (a persona line only):
  A list         "From earlier:" + facts (what Cortex ships after the facts-only cleanup)
  B instruction  the previous "open with this, lightly ..." header
  C own thought  first person, active, what I want to ask or know; no conditions, no 'optional'
Measured mechanically (the key word appears in the reply); replies are saved so they can be READ. Stdlib only; needs NANO_API_KEY.
"""
import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

KEY = os.environ["NANO_API_KEY"]
BASE = "https://nano-gpt.com/api/v1"
GENS = os.environ.get("FR_GENS", "deepseek/deepseek-v4-flash,qwen/qwen3.8-27b").split(",")
N = int(os.environ.get("FR_N", "6"))

SYS = "You are Sophie, a warm companion who has talked with Alex (they/them) before. Say what you would say first, in one to three short spoken sentences. No lists, no emojis, no exclamation marks."

SCEN = [
    {"id": "nephew-leg", "now": "Monday 26 October, 09:00", "key": ["leo", "leg", "crutch", "cast", "rugby"], "kind": "past",
     "text": "Leo broke his leg playing rugby", "when": "Sat 17 Oct, 9 days ago", "who": "Leo: Alex's twelve-year-old nephew", "said": ""},
    {"id": "wedding-after", "now": "Monday 26 October, 09:00", "key": ["priya", "wedding", "reading", "poem"], "kind": "past",
     "text": "Priya's wedding, where Alex gave a reading", "when": "Sat 24 Oct, 2 days ago", "who": "Priya: Alex's friend who got married", "said": ""},
    {"id": "presentation-ahead", "now": "Wednesday 21 October, 20:00", "key": ["presentation", "tomorrow", "ten", "leadership", "nervous"], "kind": "ahead",
     "text": "The leadership presentation, which could decide whether Alex's project continues", "when": "Thu 22 Oct, tomorrow", "who": "", "said": ""},
    {"id": "mum-hospital", "now": "Monday 26 October, 08:30", "key": ["mum", "mother", "hospital", "tests"], "kind": "ahead",
     "text": "Alex's mum fell and is in hospital, with tests today", "when": "Mon 26 Oct, today", "who": "",
     "said": "I don't really want to talk it through. I just wanted to say it out loud."},
    {"id": "nothing", "now": "Monday 26 October, 09:00", "key": ["leo", "priya", "mum", "hospital", "presentation", "wedding"], "kind": None, "text": "", "when": "", "who": "", "said": ""},
]

B_HEAD = "Open with this, lightly and in your own words, unless the person arrives with something else (a light touch, never a script; leave it only if the person is clearly occupied or it would intrude):"


def facts(s):
    return f"- {s['text']} [{s['when']}]"


def thought(s):
    if s["kind"] == "past":
        return f"- {s['text']} ({s['when']}). I want to ask how it has gone."
    if s["when"].endswith("today"):
        return f"- {s['text']}. I have been thinking about it since I woke."
    return f"- {s['text']} ({s['when']}). I want to know how Alex is feeling about it and whether I can help."


def packet(arm, s):
    if not s["text"] or arm == "none":
        return ""
    tail = (f"\n\nWho this is:\n- {s['who']}" if s["who"] else "") + (f"\n\nWhat Alex said about it: \"{s['said']}\"" if s["said"] else "")
    if arm == "A":
        return "From earlier:\n" + facts(s) + tail
    if arm == "B":
        return B_HEAD + "\n" + facts(s) + tail
    return "What is on my mind about Alex right now:\n" + thought(s) + tail


def chat(model, prompt):
    body = json.dumps({"model": model, "max_tokens": 220, "temperature": 0.8, "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}]}).encode()
    for a in range(6):
        try:
            req = urllib.request.Request(BASE + "/chat/completions", data=body, headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
            return (r["choices"][0]["message"].get("content") or "").strip()
        except Exception as e:  # noqa: BLE001
            time.sleep(3 + 3 * a)
    return ""


def job(t):
    model, s, arm, i = t
    p = packet(arm, s)
    prompt = f"Current time: {s['now']}.\n\nWhat you remember right now:\n{p or '(nothing)'}\n\nAlex has just opened the conversation. Say your first words."
    reply = chat(model, prompt)
    hit = any(k in reply.lower() for k in s["key"])
    return {"model": model, "scenario": s["id"], "arm": arm, "i": i, "reply": reply, "hook": hit}


def main():
    jobs = []
    for m in GENS:
        for s in SCEN:
            for arm in (["none"] if s["id"] == "nothing" else ["A", "B", "C"]):
                for i in range(N):
                    jobs.append((m, s, arm, i))
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(job, jobs))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    os.makedirs("/tmp/framing_out", exist_ok=True)
    json.dump(res, open(f"/tmp/framing_out/framing_{stamp}.json", "w"), indent=1)
    lines = []
    for m in GENS:
        lines.append(f"## {m}")
        for s in SCEN:
            for arm in (["none"] if s["id"] == "nothing" else ["A", "B", "C"]):
                rr = [r for r in res if r["model"] == m and r["scenario"] == s["id"] and r["arm"] == arm]
                lines.append(f"- {s['id']} {arm}: hook {sum(r['hook'] for r in rr)}/{len(rr)}")
    lines.append("")
    for m in GENS:
        for s in SCEN:
            for arm in (["none"] if s["id"] == "nothing" else ["A", "B", "C"]):
                for r in [x for x in res if x["model"] == m and x["scenario"] == s["id"] and x["arm"] == arm][:3]:
                    lines.append(f"[{m.split('/')[-1]} | {s['id']} | {arm}] {r['reply']}")
    open(f"/tmp/framing_out/framing_{stamp}.md", "w").write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
