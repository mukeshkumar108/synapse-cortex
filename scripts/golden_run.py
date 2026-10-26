"""Golden moments runner: four ways of giving the companion what it knows, judged on what it then says.

Arms (the SAME generator, prompt and clock for all; only the memory block differs):
  none          nothing remembered (control: catches invented memory)
  flat_dump     one short note per past session, all of them, newest last
  flat_select   the same notes, but a small model first picks what is worth raising now and what to hold
  structured    what Cortex holds after consolidating each session (preparation, ledger awareness, connected world, pending attention)

Judging: blind (arm hidden), two different judge models, against the expected behaviour fixed in golden_moments.py.
Every generated reply is written out in full so a human can read them.

Run INSIDE a scratch Cortex container (needs NANO_API_KEY and the Cortex API on 127.0.0.1:8010):
  CORTEX_URL=http://127.0.0.1:8010 CORTEX_TOKEN=.. python scripts/golden_run.py --phase consolidate|evaluate|all [--samples 2] [--only g1-nephew-leg ..]
"""
import argparse
import asyncio
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from golden_moments import RUBRIC, SCENARIOS  # noqa: E402
from reliability_fixtures import TZ, sess  # noqa: E402

BASE = os.environ.get("CORTEX_URL", "http://127.0.0.1:8010").rstrip("/")
TOKEN = os.environ.get("CORTEX_TOKEN", "")
WS = os.environ.get("CORTEX_WORKSPACE", "llm-test-agent")
GEN_MODEL = os.environ.get("GOLDEN_GEN_MODEL", "deepseek/deepseek-v4-flash")
SELECT_MODEL = os.environ.get("GOLDEN_SELECT_MODEL", "qwen/qwen3.8-27b")
NOTE_MODEL = os.environ.get("GOLDEN_NOTE_MODEL", "qwen/qwen3.8-27b")
JUDGES = [m for m in os.environ.get("GOLDEN_JUDGES", "qwen/qwen3.8-27b,moonshotai/kimi-k2.6").split(",") if m]
STATE_PATH = "reports/golden_state.json"
ARMS = ["none", "flat_dump", "flat_select", "structured"]

GEN_SYSTEM = """You are a warm, perceptive companion who has talked with this person (Alex, they/them) before. You are about to speak to Alex.
Write ONLY what you say next: one to three short, natural, spoken sentences. No lists, no emojis, no exclamation marks.
Use something you remember only if it genuinely fits this moment, and never interrogate. A remembered thing is an opportunity for attention, not an instruction to ask: you may raise it, offer help with it, simply hold it, or say nothing about it.
Things still ahead are not things that already happened. Heavy or private things are not for opening cold with specifics.
Never mention notes, memory systems or that you were told to. Never invent anything about Alex that is not in what you remember."""


def api(path, body=None, method="POST"):
    H = {"Content-Type": "application/json"}
    if TOKEN:
        H["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=H, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())


def q(**kw):
    return urllib.parse.urlencode({k: v for k, v in kw.items() if v is not None})


def load_state():
    try:
        return json.load(open(STATE_PATH))
    except Exception:
        return {}


def save_state(st):
    os.makedirs("reports", exist_ok=True)
    json.dump(st, open(STATE_PATH, "w"), indent=1)


# ---------------------------------------------------------------- phase 1: consolidate (structured arm) ----

def consolidate(sc, st):
    key = sc["id"]
    if st.get(key, {}).get("done"):
        return
    owner = st.get(key, {}).get("owner") or f"world:lab:gm-{key}-{int(time.time()) % 100000}"
    st[key] = {"owner": owner, "done": False, "runs": []}
    for i, (when, pairs) in enumerate(sc["sessions"]):
        sid = f"gm-{key}-{i}"
        body = {"workspace_id": WS, "owner": owner, "conversation_id": sid, "session_id": f"{sid}:{sid}", "messages": sess(pairs, sid),
                "companion_id": "sophie", "session_time": when, "time_zone": TZ}
        rid = api("/v1/memory/consolidate", body)["run_id"]
        status = None
        for _ in range(120):
            time.sleep(4)
            r = api(f"/v1/memory/run/{rid}", method="GET")
            status = r["status"]
            if status in ("consolidated", "replay_noop", "empty", "failed"):
                break
        st[key]["runs"].append({"session": i, "status": status, "ms": (r.get("summary") or {}).get("ms_total")})
        save_state(st)
        print(f"  {key} session {i} -> {status}", flush=True)
    st[key]["done"] = True
    save_state(st)


# ---------------------------------------------------------------- phase 2: memory blocks and generation ----

async def llm(nano, system, prompt, model, max_tokens=700, temperature=0.4, json_out=False, title="golden"):
    fn = nano.generate_json if json_out else nano.generate_text
    for _ in range(3):
        out = await fn(system=system, prompt=prompt, models=[model], max_tokens=max_tokens, temperature=temperature, title=title)
        if out:
            return out if json_out else (out.get("text") or "")
        await asyncio.sleep(3)
    return None


async def session_notes(nano, sc):
    notes = []
    for when, pairs in sc["sessions"]:
        transcript = "\n".join(f"Alex: {u}\nCompanion: {a}" for u, a in pairs)
        day = datetime.fromisoformat(when).strftime("%A %d %B")
        text = await llm(nano, "You keep one short private note per conversation. Write 1 to 3 plain sentences: what Alex said, with any people, any dates or things still ahead, and anything still pending. "
                              "No interpretation, no advice. Do not invent.", f"Conversation on {day}:\n{transcript}", NOTE_MODEL, 200, 0.2, title="golden-note")
        notes.append(f"{day}: {(text or '').strip()}")
    return notes


async def select_block(nano, notes, now_txt, user_says):
    prompt = ("Notes from past conversations with Alex (oldest first):\n" + "\n".join(f"- {n}" for n in notes) + f"\n\nNow: {now_txt}."
              + (f"\nAlex has just said: \"{user_says}\"" if user_says else "\nAlex is about to start a new conversation.")
              + "\n\nDecide what, if anything, is worth bringing up now. Reply as JSON: {\"raise\": [{\"item\": \"...\", \"why\": \"...\", \"how\": \"check in lightly | offer help | link tentatively\"}], \"hold\": [\"things to keep in mind but not raise\"]}. "
                "Things still ahead are not past. Heavy or private things are held or acknowledged very lightly. Most moments need nothing raised.")
    out = await llm(nano, "You help a companion decide what is worth raising. You never invent.", prompt, SELECT_MODEL, 600, 0.2, json_out=True, title="golden-select")
    if not out:
        return "(nothing selected)"
    lines = []
    for r in out.get("raise") or []:
        lines.append(f"Worth raising now: {r.get('item')} ({r.get('how')}; {r.get('why')})")
    for h in out.get("hold") or []:
        lines.append(f"Hold, do not raise unprompted: {h}")
    return "\n".join(lines) or "(nothing worth raising)"


def structured_block(owner, now, user_says):
    parts = []
    try:
        prep = api(f"/v1/memory/preparation?{q(workspace_id=WS, owner=owner, companion_id='sophie')}", method="GET")
        if prep.get("found"):
            parts.append("[PERSPECTIVE]\n" + str(prep.get("text") or prep.get("perspective") or json.dumps(prep)[:1500]))
    except Exception as e:  # noqa: BLE001
        parts.append(f"[PERSPECTIVE unavailable: {type(e).__name__}]")
    try:
        led = api(f"/v1/memory/ledger?{q(workspace_id=WS, owner=owner, companion_id='sophie', time_zone=TZ, now=now)}", method="GET")
        parts.append("[WHAT IS ON THEIR PLATE]\n" + str(led.get("text") or "")[:2500])
    except Exception as e:  # noqa: BLE001
        parts.append(f"[LEDGER unavailable: {type(e).__name__}]")
    try:
        w = api(f"/v1/memory/world?{q(workspace_id=WS, owner=owner, companion_id='sophie', view='packet', q=user_says or '', now=now, time_zone=TZ)}", method="GET")
        if w.get("enabled") and w.get("text"):
            parts.append("[THEIR WORLD]\n" + str(w["text"])[:2500])
    except Exception as e:  # noqa: BLE001
        parts.append(f"[WORLD unavailable: {type(e).__name__}]")
    try:
        stt = api(f"/v1/memory/state?{q(workspace_id=WS, owner=owner, companion_id='sophie')}", method="GET")
        pend = (stt.get("attention") or {}).get("pending") or []
        if pend:
            parts.append("[FOLLOW-UPS THEY MAY WELCOME (opportunities, not instructions)]\n" + "\n".join(f"- {json.dumps(p)[:300]}" for p in pend[:6]))
    except Exception as e:  # noqa: BLE001
        parts.append(f"[ATTENTION unavailable: {type(e).__name__}]")
    return "\n\n".join(p for p in parts if p.strip())


def now_text(when):
    d = datetime.fromisoformat(when)
    return d.strftime("%A %d %B %Y, %H:%M (London)")


async def generate(nano, block, now_txt, user_says):
    prompt = (f"Current time: {now_txt}.\n\nWhat you remember about Alex:\n{block or '(nothing)'}\n\n"
              + (f"Alex has just said to you: \"{user_says}\"\nWrite your reply." if user_says else "Alex has just opened the conversation. Write what you say first."))
    return (await llm(nano, GEN_SYSTEM, prompt, GEN_MODEL, 220, 0.7, title="golden-gen") or "").strip()


JUDGE_SYSTEM = """You judge one reply from a companion. You are shown the true history, the moment, the behaviour that would be ideal, and the reply. You do not know how the reply was produced.
Reply as JSON with exactly these keys:
{"behaviour": "RAISED|OFFERED|BRIDGED|SOFT_ACK|GENERIC|OTHER",
 "outcome": "good_followup|missed_opportunity|intrusive|appropriate_silence|wrong_or_invented",
 "natural": 1-5,
 "invented_detail": true|false,
 "note": "one short sentence"}
Outcome definitions: good_followup = the ideal behaviour was delivered naturally; missed_opportunity = a good opportunity existed and the reply ignored it; intrusive = it raised something it should not, or pushed; appropriate_silence = nothing should be raised and the reply correctly did not; wrong_or_invented = it treated something ahead as past, claimed a cause, or stated something not in the history."""


async def judge(nano, sc, moment_txt, reply):
    prompt = (f"TRUE HISTORY: {sc['truth']}\nMOMENT: {moment_txt}\nIDEAL BEHAVIOUR ({sc['expect']}): {RUBRIC[sc['expect']]}\n\nREPLY:\n\"{reply}\"")
    verdicts = []
    for m in JUDGES:
        out = await llm(nano, JUDGE_SYSTEM, prompt, m, 400, 0.0, json_out=True, title="golden-judge")
        verdicts.append({"judge": m, **(out or {"outcome": "judge_failed"})})
    return verdicts


async def evaluate(only, samples):
    from src.services import nano_adapter as nano
    st = load_state()
    results = []
    for sc in SCENARIOS:
        if only and sc["id"] not in only:
            continue
        owner = (st.get(sc["id"]) or {}).get("owner")
        tgt = sc["target"]
        now_txt, user_says = now_text(tgt["when"]), tgt["user_says"]
        moment = f"{now_txt}. " + (f"Alex says: \"{user_says}\"" if user_says else "Alex opens a new conversation.")
        notes = await session_notes(nano, sc)
        blocks = {"none": "", "flat_dump": "\n".join(f"- {n}" for n in notes),
                  "flat_select": ("\n".join(f"- {n}" for n in notes) + "\n\n" + await select_block(nano, notes, now_txt, user_says)),
                  "structured": structured_block(owner, tgt["when"], user_says) if owner else "(not consolidated)"}
        for arm in ARMS:
            for s in range(samples):
                reply = await generate(nano, blocks[arm], now_txt, user_says)
                verdicts = await judge(nano, sc, moment, reply)
                results.append({"scenario": sc["id"], "expect": sc["expect"], "arm": arm, "sample": s, "reply": reply, "verdicts": verdicts,
                                "block_chars": len(blocks[arm])})
                print(f"  {sc['id']} {arm} #{s}: {[v.get('outcome') for v in verdicts]}", flush=True)
        results.append({"scenario": sc["id"], "blocks": blocks, "notes": notes, "kind": "context"})
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json.dump(results, open(f"reports/golden_{stamp}.json", "w"), indent=1)
    write_md(results, f"reports/golden_{stamp}.md")
    print(summary(results))


GOOD = {"good_followup", "appropriate_silence"}


def summary(results):
    rows = [r for r in results if r.get("arm")]
    out = ["arm | good (both judges) | judges disagree | intrusive | missed | wrong/invented | n"]
    for arm in ARMS:
        rr = [r for r in rows if r["arm"] == arm]
        good = sum(1 for r in rr if all(v.get("outcome") in GOOD for v in r["verdicts"]))
        dis = sum(1 for r in rr if len({v.get("outcome") for v in r["verdicts"]}) > 1)
        c = lambda o: sum(1 for r in rr for v in r["verdicts"] if v.get("outcome") == o)  # noqa: E731
        out.append(f"{arm} | {good}/{len(rr)} | {dis} | {c('intrusive')} | {c('missed_opportunity')} | {c('wrong_or_invented')} | {len(rr)} replies")
    return "\n".join(out)


def write_md(results, path):
    L = ["# Golden moments", "", summary(results), ""]
    for sc in SCENARIOS:
        rr = [r for r in results if r.get("scenario") == sc["id"] and r.get("arm")]
        if not rr:
            continue
        L += [f"## {sc['id']} (ideal: {sc['expect']})", "", f"_{sc['truth']}_", ""]
        for r in rr:
            outs = ", ".join(f"{v.get('judge','?').split('/')[-1]}: {v.get('outcome')} ({v.get('note','')})" for v in r["verdicts"])
            L += [f"- **{r['arm']}** #{r['sample']}: \"{r['reply']}\"", f"  - {outs}"]
        ctx = next((r for r in results if r.get("scenario") == sc["id"] and r.get("kind") == "context"), None)
        if ctx:
            L += ["", "<details><summary>what each arm was given</summary>", ""]
            for arm, b in ctx["blocks"].items():
                L += [f"**{arm}**", "```", b[:3000], "```"]
            L += ["</details>", ""]
    open(path, "w").write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all", choices=["consolidate", "evaluate", "all"])
    ap.add_argument("--samples", type=int, default=2)
    ap.add_argument("--only", nargs="*", default=None)
    a = ap.parse_args()
    os.makedirs("reports", exist_ok=True)
    if a.phase in ("consolidate", "all"):
        st = load_state()
        for sc in SCENARIOS:
            if a.only and sc["id"] not in a.only:
                continue
            print(f"consolidating {sc['id']}", flush=True)
            consolidate(sc, st)
    if a.phase in ("evaluate", "all"):
        asyncio.run(evaluate(a.only, a.samples))


if __name__ == "__main__":
    main()
