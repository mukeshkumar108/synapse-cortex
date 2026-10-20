"""Connected-understanding scenario: one person, several sittings over days, people/projects/situations that change.
Runs real consolidation (witness -> ledger agent -> connect pass) against a live Cortex with CONNECTED_WORLD_ENABLED, then prints what the
foreground would actually receive (packet for a given user message), entity views and the full inspect dump, plus a few property checks
about the PERSON'S WORLD (never about which tool calls a model made).

Usage: CORTEX_URL=.. CORTEX_TOKEN=.. CORTEX_WORKSPACE=.. python scripts/eval_world.py [--product sophie|bloom] [--out reports/world_<ts>.md]
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime

BASE = os.environ.get("CORTEX_URL", "http://127.0.0.1:8010").rstrip("/")
TOKEN = os.environ.get("CORTEX_TOKEN", "")
WS = os.environ.get("CORTEX_WORKSPACE", "llm-test-agent")
TZ = "Europe/London"


def api(path, body=None):
    H = {"Content-Type": "application/json", **({"Authorization": "Bearer " + TOKEN} if TOKEN else {})}
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, headers=H, method="POST" if body is not None else "GET")
    return json.loads(urllib.request.urlopen(req, timeout=180).read().decode())


def msgs(sid, pairs):
    out = []
    for i, (u, a) in enumerate(pairs):
        out += [{"id": f"{sid}-{i}-u", "speaker": "user", "text": u}, {"id": f"{sid}-{i}-a", "speaker": "assistant", "text": a}]
    return out


SESSIONS = [
 ("w1", "2026-10-19T20:00:00+01:00", [
  ("Big week. I started at Northwind last month and my manager Morgan Ellis has put me on the Bloom pilot, the wellbeing app trial with the church groups.", "That's a lot of trust early on. How are you feeling about it?"),
  ("Excited, mostly. Ashley, my partner, thinks I should take the lead on it even though it means evenings. Ashley's mum Ruth hasn't been well though, so I'm torn.", "Both things matter. What's going on with Ruth?"),
  ("She's got a chest infection that won't clear, they're waiting on test results. Ashley is quite worried.", "I'm sorry. I hope the results come back clear soon."),
  ("Anyway, dentist on Thursday at 9, I have to remember that.", "Noted, Thursday at 9.")]),
 ("w2", "2026-10-20T19:30:00+01:00", [
  ("Morgan moved the Bloom pilot demo to Friday afternoon. Honestly I think Morgan is annoyed with me, I missed a standup.", "That might be worth checking rather than assuming. Did Morgan say anything?"),
  ("No, just a short message. Could be nothing. Oh and Ruth's results are back, it's pneumonia, she's in hospital for a few days.", "That's frightening. How is Ashley?"),
  ("Shaken. I'm going to cook for her tonight.", "That sounds like a good thing to do.")]),
 ("w3", "2026-10-22T18:00:00+01:00", [
  ("Update: Morgan has actually left Northwind. Still helping informally with the Bloom pilot though, more like an advisor now. My new manager is Priya Nair.", "That's a big change. How are you finding it?"),
  ("Fine. And I need to correct something, Ruth is Ashley's aunt, not her mum. I said mum the other day. She's home from hospital and recovering.", "Thanks for telling me. Good that she's home."),
  ("Priya wants a status update on the Bloom pilot tomorrow. The demo went ok on Friday by the way, no wait, that's tomorrow, I'm muddled. The demo is Friday.", "Then tomorrow is the status update and the demo is Friday.")]),
]
QUERIES = [("Morgan texted me again about the pilot", "mention of a person whose relationship changed"),
           ("Priya wants the status update on Bloom", "new manager + project"),
           ("Can't focus today, tired", "no entity mentioned: overview only"),
           ("how is Ruth doing?", "corrected relationship + state change")]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--product", default="sophie"); ap.add_argument("--out", default="")
    a = ap.parse_args()
    owner = f"{'bloom-' if a.product == 'bloom' else 'world:lab:'}wld-{int(time.time()) % 1000000}"
    out = [f"# Connected understanding scenario ({a.product}) — {datetime.now().isoformat(timespec='seconds')}", f"owner `{owner}`", ""]
    for sid, when, pairs in SESSIONS:
        rid = api("/v1/memory/consolidate", {"workspace_id": WS, "owner": owner, "conversation_id": f"wld-{sid}", "session_id": f"wld-{sid}:{sid}",
                                              "messages": msgs(sid, pairs), "companion_id": a.product, "session_time": when, "time_zone": TZ})["run_id"]
        st = {}
        for _ in range(120):
            time.sleep(4); st = api(f"/v1/memory/run/{rid}")
            if st["status"] in ("consolidated", "replay_noop", "empty", "failed"): break
        summ = st.get("summary") or {}
        w = summ.get("world_agent") or {}
        out += [f"## After sitting {sid} ({when}) — status {st['status']}", f"connect pass: `{json.dumps(w, default=str)[:900]}`", ""]
        q = f"workspace_id={WS}&owner={urllib.parse.quote(owner)}&companion_id={a.product}&time_zone={urllib.parse.quote(TZ)}&now={urllib.parse.quote(when)}"
        ov = api(f"/v1/memory/world?{q}&view=overview")
        out += ["### overview as the foreground would see it", "```", ov.get("text") or "(empty)", "```", ""]
    now = "2026-10-22T19:00:00+01:00"
    q = f"workspace_id={WS}&owner={urllib.parse.quote(owner)}&companion_id={a.product}&time_zone={urllib.parse.quote(TZ)}&now={urllib.parse.quote(now)}"
    for text, why in QUERIES:
        p = api(f"/v1/memory/world?{q}&view=packet&q={urllib.parse.quote(text)}")
        out += [f"## Packet for: “{text}” — {why}", "```", (p.get("overview") or "") + "\n\n" + (p.get("mentions") or ""), "```", f"shown: {p.get('shown')}", ""]
    for name in ("Morgan", "Ruth", "Bloom pilot"):
        for depth in ("connected", "deep"):
            e = api(f"/v1/memory/world?{q}&view=entity&q={urllib.parse.quote(name)}&depth={depth}")
            out += [f"## know({name}, {depth})", "```", e.get("text") or "(none)", "```", ""]
    ins = api(f"/v1/memory/world?{q}&view=inspect")
    out += ["## inspect", "```json", json.dumps(ins, indent=1, default=str)[:14000], "```", ""]
    text = "\n".join(out)
    path = a.out or f"reports/world_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    open(path, "w").write(text)
    print(path, len(text))


if __name__ == "__main__":
    main()
