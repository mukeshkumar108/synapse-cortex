"""Working-space demonstration against the DEPLOYED Runtime + Cortex (real models; disclose when run).

  docker cp scripts/smoke/sophie_scenarios.py companion-runtime:/tmp/ss.py
  docker cp working_space_demo.py companion-runtime:/tmp/wsd.py
  docker exec -i companion-runtime python /tmp/wsd.py fg <label> <companion> "<text>" ...   # one foreground sitting, one turn per text
  docker exec -i companion-runtime python /tmp/wsd.py end <label>                          # the sitting really ends (Runtime -> Cortex consolidation signal)
  docker exec -i companion-runtime python /tmp/wsd.py solo <label> <companion> [identity-file]
  docker exec -i companion-runtime python /tmp/wsd.py items <label> <companion>

Users are "smoke-*" so scripts/ops/clean_smoke_data.sh can sweep them. State lives in /tmp/wsd_<label>.json (uid, chat, history).
"""
import importlib.util
import json
import os
import sys
import time
import urllib.request
import uuid
from datetime import timedelta

spec = importlib.util.spec_from_file_location("ss", "/tmp/ss.py")
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)

CORTEX = os.environ["SYNAPSE_CORTEX_URL"].rstrip("/")
TOKEN = os.environ["SYNAPSE_CORTEX_API_TOKEN"]
WS = os.environ.get("HONCHO_WORKSPACE_ID", "llm-test-agent")


def cortex(method, path, body=None):
    req = urllib.request.Request(CORTEX + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def state_path(label):
    return f"/tmp/wsd_{label}.json"


def load(label):
    try:
        return json.load(open(state_path(label)))
    except FileNotFoundError:
        return {"uid": f"smoke-ws-{label}-{uuid.uuid4().hex[:5]}", "chats": {}}


def save(label, st):
    json.dump(st, open(state_path(label), "w"))


def turn(uid, chat, history, n, text, companion, model=os.environ.get("DEMO_MODEL") or None):   # None = the companion's own production model policy
    tid = f"{chat}-{n}"
    hist = [{"id": f"{chat}-h{i}", "role": r, "content": t, "created_at": (ss.now() - timedelta(seconds=(len(history) - i) * 20)).isoformat()} for i, (r, t) in enumerate(history)]
    body = {"turn_id": tid, "conversation_id": chat, "companion_id": companion, "current_sanitized_message": text, "medium": "desktop", "canonical_history": hist,
            "selected_model_id": model, "trusted_user_context": {"user_id": uid, "timezone": ss.TZ, "medium": "desktop"}}
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
    p = ss.packet(chat, tid)
    return tid, reply, p


def cmd_fg(label, companion, texts):
    st = load(label)
    chat = os.environ.get("CHAT") or f"smoke-ws-{label}-{companion}-{uuid.uuid4().hex[:5]}"      # CHAT=<id> continues a chat of this label
    st["chats"].setdefault(chat, {"companion": companion, "history": []})
    first = len(st["chats"][chat]["history"]) // 2 + 1
    for i, text in enumerate(texts, first):
        h = st["chats"][chat]["history"]
        tid, reply, p = turn(st["uid"], chat, h, i, text, companion)
        h += [["user", text], ["assistant", reply]]
        prompt = p["prompt"]
        work_block = ""
        if "[YOUR WORKING SPACE" in prompt:
            work_block = prompt[prompt.index("[YOUR WORKING SPACE"):].split("\n\n[OUTPUT CONTRACT]")[0][:3000]
        tools = (p["state"] or {}).get("tools") or []
        print(json.dumps({"turn": tid, "user": text, "reply": reply, "work_block_delivered": work_block or None,
                          "tool_trace": [t for t in tools if str(t.get("tool", "")).startswith("work_") or t.get("tool") == "_availability"],
                          "other_tools": [t.get("tool") for t in tools if not str(t.get("tool", "")).startswith("work_")]}, ensure_ascii=False), flush=True)
        ss.bff_mirror(st["uid"], chat, tid, text, reply)
    save(label, st)
    print(json.dumps({"owner": f"user_{st['uid']}", "chat": chat, "companion": companion}))


def cmd_end(label):
    st = load(label)
    for chat, c in st["chats"].items():
        if c.get("ended"):
            continue
        msgs = [{"id": f"{chat}-e{i}", "role": r, "content": t, "created_at": ss.now().isoformat()} for i, (r, t) in enumerate(c["history"])]
        print(chat, json.dumps(ss.call(f"/v1/conversations/{chat}/end", {"user_id": st["uid"], "companion_id": c["companion"], "canonical_history": msgs})))
        c["ended"] = True
    save(label, st)


def cmd_solo(label, companion, identity_file=None):
    st = load(label)
    owner = f"user_{st['uid']}"
    sid = f"solo-ws-{uuid.uuid4().hex[:6]}"
    body = {"workspace_id": WS, "owner": owner, "sitting_id": sid, "companion_id": companion, "max_iterations": 8, "max_tool_calls": 6, "max_model_calls": 10}
    if identity_file:
        body["identity"] = open(identity_file).read()
    print(json.dumps(cortex("POST", "/v1/memory/independent-sitting", body)))
    print(json.dumps({"sitting_id": sid, "owner": owner}))


def cmd_items(label, companion):
    st = load(label)
    out = cortex("GET", f"/v1/work/items?workspace_id={WS}&owner=user_{st['uid']}&companion_id={companion}")
    for it in out["items"]:
        det = cortex("GET", f"/v1/work/items/{it['id']}?workspace_id={WS}&owner=user_{st['uid']}&companion_id={companion}")
        print(json.dumps(det, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    c = sys.argv[1]
    {"fg": lambda: cmd_fg(sys.argv[2], sys.argv[3], sys.argv[4:]), "end": lambda: cmd_end(sys.argv[2]),
     "solo": lambda: cmd_solo(sys.argv[2], sys.argv[3], *(sys.argv[4:5])), "items": lambda: cmd_items(sys.argv[2], sys.argv[3])}[c]()
