"""What actually runs on a Sophie turn? Six short turns through the real Runtime; prints, per turn, every ledgered model call (module/mode/model/ms),
the execution metadata's cortex_calls and post_reply tasks, and which prompt blocks were rendered. Then erase the smoke user.
  docker cp sophie_scenarios.py companion-runtime:/tmp/ss.py ; docker cp this companion-runtime:/tmp/tt.py ; docker exec -i companion-runtime python /tmp/tt.py"""
import importlib.util, json, os, time, urllib.request, uuid, psycopg
from datetime import timedelta
spec = importlib.util.spec_from_file_location("ss", "/tmp/ss.py"); ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
uid = f"smoke-tt-{uuid.uuid4().hex[:6]}"; chat = f"smoke-tt-{uuid.uuid4().hex[:6]}"
T = ["Hi, I'm back. Long day.", "I started a new job at Northwind last month.", "My manager Morgan put me on a pilot.", "Ashley thinks I should lead it.", "I'm not sure I want to.", "What would you do?"]
hist = []
for i, t in enumerate(T, 1):
    tid = f"{chat}-{i}"
    h = [{"id": f"{chat}-h{j}", "role": r, "content": c, "created_at": (ss.now() - timedelta(seconds=(len(hist) - j) * 20)).isoformat()} for j, (r, c) in enumerate(hist)]
    body = {"turn_id": tid, "conversation_id": chat, "companion_id": "sophie", "current_sanitized_message": t, "medium": "desktop", "canonical_history": h, "selected_model_id": None,
            "trusted_user_context": {"user_id": uid, "timezone": ss.TZ, "medium": "desktop", **({"entry_context": {"chronology": {"temporalSession": "new"}}} if i == 1 else {})}}
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
time.sleep(25)                                           # let post-reply work finish
with psycopg.connect(os.environ["COMPANION_RUNTIME_DB_URL"]) as c:
    for i in range(1, len(T) + 1):
        tid = f"{chat}-{i}"
        calls = c.execute("select module, coalesce(trigger,''), mode, model, latency_ms from model_calls where turn_id=%s order by at", (tid,)).fetchall()
        res = c.execute("select result from companion_runtime_turns where turn_id=%s", (tid,)).fetchone()
        em = ((res[0] if isinstance(res[0], dict) else json.loads(res[0])).get("execution_metadata") or {}) if res else {}
        print(f"--- turn {i}: {T[i-1]!r}")
        print("   model_calls:", [f"{m}{('/'+t) if t else ''}[{mode}] {mod.split('/')[-1]} {ms}ms" for m, t, mode, mod, ms in calls])
        print("   cortex_calls:", json.dumps(em.get("cortex_calls"))[:300])
        print("   post_reply:", json.dumps(em.get("post_reply"))[:300])
        print("   blocks:", [str(b)[:40] for b in (em.get("prompt_blocks") or [])])
print(json.dumps({"uid": uid}))
