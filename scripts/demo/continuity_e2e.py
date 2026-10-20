"""Correction propagation through the REAL Runtime executor across a compaction boundary (real Sophie, synthetic user).
One long sitting (18 turns = 36 messages: crosses the 6-message steps and the 25-message checkpoint). Early turns establish facts; a later turn
corrects them; the rest change topic. For every turn the stored system prompt is read back and checked for the stale phrases. Output: JSON per turn.
  docker cp companion-runtime/scripts/smoke/sophie_scenarios.py companion-runtime:/tmp/ss.py ; docker cp this companion-runtime:/tmp/ce.py
  docker exec -i companion-runtime python /tmp/ce.py > out.json ; then erase the user (companion_core.runtime.erase_user)
"""
import importlib.util, json, os, re, sys, time, urllib.request, uuid
from datetime import timedelta
spec = importlib.util.spec_from_file_location("ss", "/tmp/ss.py"); ss = importlib.util.module_from_spec(spec); spec.loader.exec_module(ss)
uid = f"smoke-ce-{uuid.uuid4().hex[:6]}"; chat = f"smoke-ce-{uuid.uuid4().hex[:6]}"
T = [
 "Big week. I started at Northwind last month and my manager Morgan Ellis put me on the Bloom pilot.",
 "Ashley, my partner, is stressed. Her mum Ruth is in hospital with pneumonia.",
 "I'm cooking for Ashley tonight to take the edge off. Keep me honest about that.",
 "I missed a standup and I think Morgan is annoyed with me.",
 "Dentist is Thursday at 9, I keep forgetting it.",
 "The church groups want a demo and Morgan moved it to Friday afternoon.",
 "I'm wondering whether to ask Morgan if Priya could co-lead instead of me.",
 "Honestly the evenings would wreck us right now with Ruth in hospital.",
 "Big update. Morgan has left Northwind. My new manager is Priya Nair. And I need to correct something: Ruth is Ashley's aunt, not her mum, and she's home from hospital now.",
 "So Priya wants a status update on the pilot tomorrow.",
 "I think I'll tell her I'd rather support than lead.",
 "Separate thing: what should I cook for Ashley this weekend?",
 "She likes anything with lemon. Also my car needs an MOT before the 30th.",
 "Do you think I should get a dog? I've been wondering.",
 "Probably not until the pilot settles. Anyway.",
 "How is my week looking overall?",
 "What's actually going on with Morgan these days?",
 "And how is Ruth?",
]
STALE = {"ruth_in_hospital": ["hospital stay", "in hospital", "ruth’s hospital", "ruth's hospital"], "her_mum": ["her mum", "her mother", "ashley’s mum", "ashley's mum", "ashley’s mother", "ashley's mother"],
         "morgan_annoyed": ["morgan is annoyed", "morgan may be annoyed", "morgan is upset", "annoyed with"], "morgan_manager": ["manager morgan", "morgan, my manager", "morgan ellis, the person's manager", "morgan is the manager"]}
hist = []; out = []
for i, t in enumerate(T, 1):
    tid = f"{chat}-{i}"
    h = [{"id": f"{chat}-h{j}", "role": r, "content": c, "created_at": (ss.now() - timedelta(seconds=(len(hist) - j) * 20)).isoformat()} for j, (r, c) in enumerate(hist)]
    body = {"turn_id": tid, "conversation_id": chat, "companion_id": "sophie", "current_sanitized_message": t, "medium": "desktop", "canonical_history": h,
            "selected_model_id": None, "trusted_user_context": {"user_id": uid, "timezone": ss.TZ, "medium": "desktop",
                                     **({"entry_context": {"chronology": {"temporalSession": "new", "firstContactToday": True}}} if i == 1 else {})}}   # the app marks a sitting's first turn
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
    time.sleep(8)                                    # the rolling continuity step runs after the reply; give it time to land before the next turn
    p = ss.packet(chat, tid)
    pr = p["prompt"]
    # the part of the prompt that is NOT the raw recent messages: split on bracketed block headers, keep continuity-like blocks
    blocks = re.split(r"\n\n(?=\[)", pr)
    cont = [b for b in blocks if re.match(r"\[(CONTINUITY|THIS SITTING|SO FAR|WHERE WE ARE)", b)] or [b for b in blocks if "Since then" in b or "[H1]" in b or "[L1]" in b]
    low = pr.lower()
    out.append({"turn": i, "user": t, "reply": reply[:200], "continuity_block": "\n\n".join(cont)[:3000],
                "stale_in_prompt": {k: [x for x in v if x in low] for k, v in STALE.items() if any(x in low for x in v)},
                "headers": [b.split("\n", 1)[0][:60] for b in blocks if b.startswith("[")]})
print(json.dumps({"uid": uid, "owner": f"user_{uid}", "chat": chat, "turns": out}, ensure_ascii=False, indent=1))
