"""Create a smoke user with real stored data in every layer (Runtime turns/packets/evidence, Honcho mirror, Cortex consolidation), print its id.
  docker cp companion-runtime/scripts/smoke/sophie_scenarios.py companion-runtime:/tmp/ss.py ; docker cp this companion-runtime:/tmp/seed.py
  docker exec -i companion-runtime python /tmp/seed.py [product]          # product defaults to sophie; user ids are smoke-* so the sweeper can clean strays
"""
import importlib.util, json, os, sys, time, urllib.request, uuid
from datetime import timedelta
spec = importlib.util.spec_from_file_location("ss", "/tmp/ss.py"); ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
product = sys.argv[1] if len(sys.argv) > 1 else "sophie"
uid = f"smoke-er-{uuid.uuid4().hex[:6]}"; chat = f"smoke-er-{uuid.uuid4().hex[:6]}"
TEXTS = ["I started at Northwind and my manager is Morgan Ellis. My partner Ashley is worried about her aunt Ruth, who is in hospital.",
         "My favourite book is The Count of Monte Cristo. Dentist is Thursday at 9.",
         "I kissed Rebecca last night and I don't know what to do."]
hist = []
for i, t in enumerate(TEXTS, 1):
    tid = f"{chat}-{i}"
    h = [{"id": f"{chat}-h{j}", "role": r, "content": c, "created_at": (ss.now() - timedelta(seconds=(len(hist) - j) * 20)).isoformat()} for j, (r, c) in enumerate(hist)]
    body = {"turn_id": tid, "conversation_id": chat, "companion_id": product, "current_sanitized_message": t, "medium": "desktop", "canonical_history": h,
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
    hist += [["user", t], ["assistant", reply]]
    ss.bff_mirror(uid, chat, tid, t, reply)
msgs = [{"id": f"{chat}-e{i}", "role": r, "content": t, "created_at": ss.now().isoformat()} for i, (r, t) in enumerate(hist)]
print(json.dumps({"uid": uid, "product": product, "chat": chat, "end": ss.call(f"/v1/conversations/{chat}/end", {"user_id": uid, "companion_id": product, "canonical_history": msgs})}))
