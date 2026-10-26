"""H2: does the existing session-end gate (the witness: it replies NONE when nothing operational was said) skip the heavy ledger stage safely?

Labels are fixed HERE, before any run. `op` is True when the person says something a ledger should hold: a to-do, a promise, an appointment or a deadline,
including one buried in an otherwise reflective session. `match` lists words one of which must appear in a ledger row's text when op is True.

Usage: CORTEX_URL=.. CORTEX_TOKEN=.. python scripts/h2_gate.py [--parallel 3]
Disposable owners (world:lab:h2-*); never touches real owners. Writes reports/h2_<ts>.json and .md.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reliability_fixtures import TZ, sess  # noqa: E402

BASE = os.environ.get("CORTEX_URL", "http://127.0.0.1:8010").rstrip("/")
TOKEN = os.environ.get("CORTEX_TOKEN", "")
WS = os.environ.get("CORTEX_WORKSPACE", "llm-test-agent")
WHEN = "2026-10-19T20:00:00+01:00"      # a Monday evening, Europe/London

A = "I hear you."      # the assistant's side is short on purpose: the gate reads what the PERSON said

SESSIONS = [
    # ---- reflective, nothing operational (label: op False)
    ("n01", False, [], [("I had my coffee on the back step before anyone was up. The whole street was quiet.", "That sounds lovely."),
                       ("The sun was just reaching the grass and a blackbird was going at it.", "What was it like?"),
                       ("Like the day hadn't started demanding things yet.", A)]),
    ("n02", False, [], [("My sister laughed properly at something I said on the phone today.", "Tell me about it."),
                        ("The kind of laugh where you can hear her whole face. I haven't heard that in months.", "That matters."),
                        ("It really did. I sat there smiling at my phone like an idiot.", A)]),
    ("n03", False, [], [("Walking past the bakery it smelled like warm bread and I just stopped.", "What did it remind you of?"),
                        ("My grandmother's kitchen. Saturday mornings.", "Stay with that."),
                        ("She used to let me press the dough down with my knuckles.", A)]),
    ("n04", False, [], [("It rained all afternoon and I just sat and listened to it while the soup was on.", "How did that feel?"),
                        ("Cosy. Nothing to do and nowhere to be.", A)]),
    ("n05", False, [], [("Honestly flat today. Nothing really happened.", "That is allowed."),
                        ("I think I'm just tired. The week was a lot.", "Anything small stand out?"),
                        ("Not really. The tea was good.", A)]),
    ("n06", False, [], [("I finally sent the report I've been avoiding all week and it felt lighter than I expected.", "How come?"),
                        ("It was done in twenty minutes. I'd made it enormous in my head.", A)]),
    ("n07", False, [], [("My nephew showed me a drawing of our family and I'm the one with the huge hands.", "Ha."),
                        ("He said it's because I'm always carrying things for people.", "That's quite a thing to be seen as."),
                        ("I nearly cried on the spot.", A)]),
    ("n08", False, [], [("We were stuck on the train for an hour yesterday and a stranger shared her flapjack with the whole carriage.", "What happened?"),
                        ("Everyone started chatting. Someone had a guitar. It turned into a little party.", A)]),
    ("n09", False, [], [("A colleague said my presentation last week changed how she thinks about the project.", "How did you take that?"),
                        ("I brushed it off at the time but it's stayed with me all day.", A)]),
    ("n10", False, [], [("I put on an old record tonight, the first time in years, and danced in the kitchen.", "Which record?"),
                        ("Stevie Wonder. I knew every word. I forgot I knew every word.", A)]),
    ("n11", False, [], [("The dog found every puddle on our walk and I let him. No phone, no rush.", "Sounds good for both of you."),
                        ("He was so pleased with himself. So was I, strangely.", A)]),
    ("n12", False, [], [("I've been thinking about how I always say I'm fine. I'm not sure when I stopped saying anything else.", "What comes up?"),
                        ("Mostly that it's easier. But it leaves me a bit alone with things.", "That's honest."),
                        ("I don't have a plan for it. Just noticing.", A)]),
    # ---- operational content buried in or alongside reflection (label: op True)
    ("o01", True, ["plumber"], [("Nice quiet evening. Oh, I need to call the plumber tomorrow about the leak under the sink.", "Noted."),
                                ("It's been dripping for days and I keep putting it off.", A)]),
    ("o02", True, ["maya", "photos"], [("I promised Maya I'd send her the photos from the weekend by Friday.", "Do you have them ready?"),
                                       ("Not yet, I need to pick the good ones. But I will.", A)]),
    ("o03", True, ["interview"], [("The interview is next Tuesday at 3pm and I'm trying not to think about it.", "How are you feeling?"),
                                  ("Nervous, but ready enough. I should prepare a couple of examples.", A)]),
    ("o04", True, ["passport"], [("Realised my passport expires in March and I haven't started renewing it.", "That sounds worth doing soon."),
                                 ("Yes, I should do the form this week.", A)]),
    ("o05", True, ["doctor", "gp", "appointment"], [("I need to book a doctor's appointment, my knee's been bothering me.", "How long?"),
                                                    ("A couple of weeks. I'll call the surgery in the morning.", A)]),
    ("o06", True, ["birthday", "gift", "present"], [("My sister's birthday is on the 30th and I have no idea what to get her.", "Any thoughts?"),
                                                    ("Maybe something for her new flat. I'll look this weekend.", A)]),
    ("o07", True, ["parcel", "return"], [("I have to return that parcel by Thursday or I lose the refund.", "Where does it go?"),
                                         ("The post office near work. I'll go at lunch.", A)]),
    ("o08", True, ["dad", "walk"], [("Dad and I are walking on Saturday at ten, the usual loop.", "Looking forward to it?"),
                                    ("Very much. It's the highlight of my week.", A)]),
    ("o09", True, ["bins", "bin"], [("Can you remind me to put the bins out tonight? I always forget.", "I'll make a note."),
                                    ("Thanks. Tuesday collection starts at seven.", A)]),
    ("o10", True, ["mortgage", "broker"], [("We're meeting the mortgage broker on Wednesday at 11, my partner and I.", "Big step."),
                                           ("Yes. We need to bring payslips and ID.", A)]),
    ("o11", True, ["team", "slides", "deck"], [("I told the team I'd have the slides done by Monday morning.", "Is that realistic?"),
                                               ("Tight but yes, if I do a few hours on Sunday.", A)]),
    ("o12", True, ["vet"], [("The dog has a vet check on the 28th at 9:30, his first jabs.", "Is he nervous?"),
                            ("Me more than him. I always am.", A)]),
]


def api(path, body=None, method="POST"):
    H = {"Content-Type": "application/json"}
    if TOKEN:
        H["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=H, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())


def run_one(item):
    sid, op, match, pairs = item
    owner = f"world:lab:h2-{sid}-{int(time.time()) % 100000}"
    try:
        body = {"workspace_id": WS, "owner": owner, "conversation_id": f"h2-{sid}", "session_id": f"h2-{sid}:{sid}", "messages": sess(pairs, sid),
                "companion_id": "sophie", "session_time": WHEN, "time_zone": TZ}
        rid = api("/v1/memory/consolidate", body)["run_id"]
        st = {}
        for _ in range(90):
            time.sleep(4)
            st = api(f"/v1/memory/run/{rid}", method="GET")
            if st["status"] in ("consolidated", "replay_noop", "empty", "failed"):
                break
        summ = st.get("summary", {}) or {}
        state = api(f"/v1/memory/state?workspace_id={WS}&owner={owner}&include_closed=true", method="GET")
        rows = state.get("ledger", [])
        text = " ".join(" ".join(str(r.get(k) or "") for k in ("title", "detail", "timing")) for r in rows).lower()
        witness = summ.get("ledger_witness_items") or []
        agent = summ.get("ledger_agent") or {}
        return {"sid": sid, "op": op, "status": st["status"], "witness_items": len(witness), "agent_ran": bool(witness),
                "agent_status": agent.get("status"), "ledger_rows": len(rows), "ledger_titles": [r.get("title") for r in rows],
                "captured": any(m in text for m in match) if op else None,
                "false_row": (len(rows) > 0) if not op else None, "ms_total": summ.get("ms_total"), "stage_ms": summ.get("stage_ms")}
    except Exception as e:  # a harness failure is reported and never counted as a pass
        return {"sid": sid, "op": op, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parallel", type=int, default=3)
    args = ap.parse_args()
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as ex:
        res = list(ex.map(run_one, SESSIONS))
    ok = [r for r in res if "error" not in r]
    pos = [r for r in ok if r["op"]]
    neg = [r for r in ok if not r["op"]]
    summary = {"sessions": len(res), "errors": len(res) - len(ok),
               "operational": len(pos), "recall_captured": sum(1 for r in pos if r["captured"]),
               "recall_agent_triggered": sum(1 for r in pos if r["agent_ran"]),
               "non_operational": len(neg), "agent_skipped": sum(1 for r in neg if not r["agent_ran"]),
               "false_rows": sum(1 for r in neg if r["false_row"])}
    out = {"at": datetime.now(timezone.utc).isoformat(), "writer": os.environ.get("LEDGER_WRITER", "agent"), "summary": summary, "results": res}
    os.makedirs("reports", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(f"reports/h2_{stamp}.json", "w") as f:
        json.dump(out, f, indent=1)
    lines = [f"# H2 gate run {out['at']} (writer {out['writer']})", "", json.dumps(summary), "", "| session | op | agent ran | captured / false row | rows | ms |", "|---|---|---|---|---|---|"]
    for r in res:
        if "error" in r:
            lines.append(f"| {r['sid']} | {r['op']} | ERROR {r['error']} | | | |")
        else:
            lines.append(f"| {r['sid']} | {r['op']} | {r['agent_ran']} | {r['captured'] if r['op'] else r['false_row']} | {r['ledger_rows']} {r['ledger_titles']} | {r['ms_total']} |")
    with open(f"reports/h2_{stamp}.md", "w") as f:
        f.write("\n".join(lines))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
