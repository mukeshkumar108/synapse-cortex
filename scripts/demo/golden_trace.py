"""One real conversation, turn by turn: what the assembled prompt contains and how it changes. Phase 1 gives a synthetic user a past (two short sittings, ended and
consolidated by Cortex); phase 2 is a new sitting that opens small, goes into Bloom, deepens, changes topic, then brings up Ashley.
Prints per turn: prompt size, block headers with sizes, and the world/pertinent/continuity blocks in full. Saves full prompts to /tmp/golden_prompts.json.
  docker exec -i companion-runtime python /tmp/gt.py ; then erase the smoke user."""
import importlib.util, json, os, re, time, urllib.request, uuid
from datetime import timedelta
spec = importlib.util.spec_from_file_location("ss", "/tmp/ss.py"); ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
CORTEX = os.environ["SYNAPSE_CORTEX_URL"].rstrip("/"); TOKEN = os.environ["SYNAPSE_CORTEX_API_TOKEN"]; WS = os.environ.get("HONCHO_WORKSPACE_ID", "llm-test-agent")
uid = f"smoke-gt-{uuid.uuid4().hex[:6]}"; owner = f"user_{uid}"


def turn(chat, hist, i, t, first=False):
    tid = f"{chat}-{i}"
    h = [{"id": f"{chat}-h{j}", "role": r, "content": c, "created_at": (ss.now() - timedelta(seconds=(len(hist) - j) * 20)).isoformat()} for j, (r, c) in enumerate(hist)]
    body = {"turn_id": tid, "conversation_id": chat, "companion_id": "sophie", "current_sanitized_message": t, "medium": "desktop", "canonical_history": h, "selected_model_id": None,
            "trusted_user_context": {"user_id": uid, "timezone": ss.TZ, "medium": "desktop", **({"entry_context": {"chronology": {"temporalSession": "new"}}} if first else {})}}
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
    hist += [["user", t], ["assistant", reply]]
    ss.bff_mirror(uid, chat, tid, t, reply)
    return tid, reply


def sitting(texts):
    chat = f"smoke-gt-{uuid.uuid4().hex[:6]}"; hist = []
    for i, t in enumerate(texts, 1):
        turn(chat, hist, i, t, first=(i == 1))
    msgs = [{"id": f"{chat}-e{i}", "role": r, "content": c, "created_at": ss.now().isoformat()} for i, (r, c) in enumerate(hist)]
    ss.call(f"/v1/conversations/{chat}/end", {"user_id": uid, "companion_id": "sophie", "canonical_history": msgs})


def pending():
    req = urllib.request.Request(CORTEX + f"/v1/memory/world?workspace_id={WS}&owner={owner}&companion_id=sophie&view=overview", headers={"Authorization": f"Bearer {TOKEN}"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read()).get("pending_consolidations", 0)


sitting(["I started at Northwind last month and my manager Morgan Ellis put me on the Bloom pilot, a wellbeing app trial with church groups. I'm weighing whether to lead it.",
         "My partner Ashley thinks I should lead it even though it means evenings. Her aunt Ruth is in hospital with pneumonia, so I'm torn.",
         "Dentist is Thursday at 9. And I kissed Rebecca last night, no idea what I was thinking."])
time.sleep(20)
t0 = time.time()
while time.time() - t0 < 900 and (pending() > 0 or time.time() - t0 < 60):
    time.sleep(15)
print(f"[past consolidated after {int(time.time()-t0)}s]", flush=True)

PLAN = [("opening", "Hi. Long day, I'm wrecked."), ("opening", "Not much. Just wanted to sit for a bit."),
        ("bloom", "Actually I've been thinking about the Bloom pilot again."), ("bloom-deep", "What do you think I'm actually afraid of with it?"),
        ("change", "Anyway. What should I cook tonight? Something easy."), ("change", "Lemon chicken sounds good. Do I have anything on tomorrow?"),
        ("ashley", "Ashley and I are looking at flats together next week, I'm nervous."), ("ashley", "I just don't want to mess this up.")]
chat = f"smoke-gt-{uuid.uuid4().hex[:6]}"; hist = []; out = []
for i, (phase, t) in enumerate(PLAN, 1):
    tid, reply = turn(chat, hist, i, t, first=(i == 1))
    time.sleep(6)
    p = ss.packet(chat, tid); pr = p["prompt"]
    blocks = re.split(r"\n\n(?=\[)", pr)
    out.append({"turn": i, "phase": phase, "user": t, "reply": reply, "chars": len(pr), "n_messages": len(p["messages"] or []),
                "blocks": [(b.split("\n", 1)[0][:70], len(b)) for b in blocks if b.startswith("[")],
                "shown": [b for b in blocks if re.match(r"\[(THEIR WORLD|WHO OR WHAT|REMEMBERED|JUST BEFORE|ESTABLISHED|OPERATIONAL)", b)], "prompt": pr})
json.dump(out, open("/tmp/golden_prompts.json", "w"))
for o in out:
    print(f"\n=== turn {o['turn']} [{o['phase']}] user: {o['user']}\n    prompt {o['chars']} chars, {o['n_messages']} raw messages; blocks: {o['blocks']}")
    print("    reply:", o["reply"][:260].replace("\n", " "))
    for b in o["shown"]:
        print("    ---", b[:700].replace("\n", "\n    "))
print(json.dumps({"uid": uid}))
