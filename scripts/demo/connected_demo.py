"""End-to-end connected-understanding demonstration against the DEPLOYED Runtime + Cortex (real models; disclose when run).

  docker cp scripts/smoke/sophie_scenarios.py companion-runtime:/tmp/ss.py        (from companion-runtime)
  docker cp scripts/demo/connected_demo.py companion-runtime:/tmp/cd.py            (from synapse-cortex)
  docker exec -i companion-runtime python /tmp/cd.py > run.json
  scripts/ops/clean_smoke_data.sh                                                   (companion-runtime; users are smoke-*)

Several sittings over real turns (the Runtime talks as Sophie), each ended through the Runtime -> Cortex consolidation path, then PROBE turns whose
system prompt is read back from turn_packets: did the connected world, the pertinent happenings and the preference reach the model, and what did
she say. Checks are substring checks on the packet (retrieval) and are printed with the prose for a human to judge.
"""
import importlib.util, json, os, sys, time, urllib.request, uuid
from datetime import timedelta

spec = importlib.util.spec_from_file_location("ss", "/tmp/ss.py"); ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
sys.path.insert(0, "/tmp")
spec2 = importlib.util.spec_from_file_location("wsd", "/tmp/wsd.py")
CORTEX = os.environ["SYNAPSE_CORTEX_URL"].rstrip("/"); TOKEN = os.environ["SYNAPSE_CORTEX_API_TOKEN"]; WS = os.environ.get("HONCHO_WORKSPACE_ID", "llm-test-agent")
SETTLE = int(os.environ.get("CD_SETTLE", "200"))
COMPANION = "sophie"


def cortex(path):
    req = urllib.request.Request(CORTEX + path, headers={"Authorization": f"Bearer {TOKEN}"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def run_turn(uid, chat, history, n, text):
    tid = f"{chat}-{n}"
    hist = [{"id": f"{chat}-h{i}", "role": r, "content": t, "created_at": (ss.now() - timedelta(seconds=(len(history) - i) * 20)).isoformat()} for i, (r, t) in enumerate(history)]
    body = {"turn_id": tid, "conversation_id": chat, "companion_id": COMPANION, "current_sanitized_message": text, "medium": "desktop", "canonical_history": hist,
            "selected_model_id": None, "trusted_user_context": {"user_id": uid, "timezone": ss.TZ, "medium": "desktop"}}
    req = urllib.request.Request(ss.BASE + "/v1/turns/stream", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "X-Companion-Runtime-Key": ss.KEY})
    reply = ""
    with urllib.request.urlopen(req, timeout=240) as resp:
        for raw in resp:
            line = raw.decode().strip()
            if line.startswith("data:"):
                try:
                    d = json.loads(line[5:])
                except Exception:
                    continue
                if isinstance(d, dict) and (d.get("result") or {}).get("assistant_message"):
                    reply = d["result"]["assistant_message"]
    time.sleep(1.5)
    return tid, reply, ss.packet(chat, tid)


def sitting(uid, texts, probe=None):
    chat = f"smoke-cd-{uuid.uuid4().hex[:6]}"; hist = []; out = []
    for i, t in enumerate(texts, 1):
        tid, reply, p = run_turn(uid, chat, hist, i, t)
        hist += [["user", t], ["assistant", reply]]
        ss.bff_mirror(uid, chat, tid, t, reply)
        rec = {"user": t, "reply": reply, "tools": [x.get("tool") for x in ((p["state"] or {}).get("tools") or [])]}
        if probe and i in probe:
            pr = p["prompt"]; rec["prompt"] = pr; rec["checks"] = {k: (k.lower() in pr.lower()) for k in probe[i]}
        out.append(rec)
    return chat, hist, out


def end(uid, chat, hist):
    msgs = [{"id": f"{chat}-e{i}", "role": r, "content": t, "created_at": ss.now().isoformat()} for i, (r, t) in enumerate(hist)]
    return ss.call(f"/v1/conversations/{chat}/end", {"user_id": uid, "companion_id": COMPANION, "canonical_history": msgs})


uid = f"smoke-cd-{uuid.uuid4().hex[:6]}"; owner = f"user_{uid}"; results = {"owner": owner, "sittings": []}
S = [
 ["Big week. I started at Northwind last month and my manager Morgan Ellis has put me on the Bloom pilot, the wellbeing app trial with church groups.",
  "Ashley, my partner, thinks I should take the lead even though it means evenings. Her aunt Ruth has had a chest infection that won't clear.",
  "My favourite book is The Count of Monte Cristo, I've read it four times. It's what I turn to when work gets heavy.",
  "I kissed Rebecca last night. She's on the other team. I have no idea what I was thinking.",
  "Anyway, dentist is Thursday at 9. Remind me later."],
 ["Back. I stayed at my mum's again last night. We argued about the house, I barely slept and my neck hurts.",
  "It's the third time I've stayed over this month and it's gone the same way every time: tense, no sleep.",
  "Morgan moved the Bloom demo to Friday afternoon."],
 ["Update: Morgan has left Northwind but still helps informally. My new manager is Priya Nair. Also Ruth is home from hospital now, she had pneumonia.",
  "I told Ashley I'd think about moving in together properly."],
]
for i, texts in enumerate(S):
    chat, hist, out = sitting(uid, texts)
    results["sittings"].append({"n": i + 1, "turns": out, "end": end(uid, chat, hist)})
    print(f"sitting {i+1} done; settling {SETTLE}s for consolidation + connect pass", flush=True)
    time.sleep(SETTLE)
ins = cortex(f"/v1/memory/world?workspace_id={WS}&owner={owner}&companion_id={COMPANION}&view=inspect")
results["inspect"] = {"entities": [{k: e.get(k) for k in ("name", "kind", "form", "tags", "occurred_on", "significance", "basis", "sensitive", "summary")} for e in ins.get("entities", [])],
                      "links": [{k: l.get(k) for k in ("from", "relation", "target", "basis", "status")} for l in ins.get("links", [])]}
PROBES = [
 ("Any book recommendations for the weekend? Something I'd actually love.", ["Monte Cristo"]),
 ("Ashley and I are looking at flats together next week, I'm nervous.", ["Rebecca", "REMEMBERED THAT BEARS"]),
 ("I'm heading to my mum's again on Saturday.", ["provisional pattern", "poor sleep"]),
 ("Morgan texted me about the pilot again.", ["Former manager", "Priya"]),
]
results["probes"] = []
chat = f"smoke-cd-{uuid.uuid4().hex[:6]}"; hist = []
for i, (text, keys) in enumerate(PROBES, 1):
    tid, reply, p = run_turn(uid, chat, hist, i, text)
    hist += [["user", text], ["assistant", reply]]
    pr = p["prompt"]
    results["probes"].append({"user": text, "reply": reply, "checks": {k: (k.lower() in pr.lower()) for k in keys}, "tools": [x.get("tool") for x in ((p["state"] or {}).get("tools") or [])], "prompt": pr})
print(json.dumps(results, ensure_ascii=False, indent=1))
