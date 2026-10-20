"""Inspect the Runtime's in-session continuity (rolling account, checkpoints, reconciliation) over one longer synthetic conversation.
Run INSIDE the Runtime container (it has provider keys):  docker exec -i companion-runtime python - < scripts/inspect_rolling_continuity.py
Pure except for the model calls rolling_continuity.step makes; writes nothing. Prints the account the foreground would receive after
every step, so 'what has been lost or distorted by message N' can be read directly."""
import asyncio, json
from companion_core.runtime import rolling_continuity as rc

T = [
 ("Big week. I started at Northwind last month and my manager Morgan Ellis has put me on the Bloom pilot, the wellbeing app trial with church groups.", "That's a lot of trust early on. How are you feeling about it?"),
 ("Excited, mostly. Ashley, my partner, thinks I should take the lead even though it means evenings. Ashley's mum Ruth hasn't been well though.", "Both things matter. What's going on with Ruth?"),
 ("She's got a chest infection that won't clear, they're waiting on test results. Ashley is quite worried.", "I'm sorry. I hope the results come back clear."),
 ("Anyway, dentist on Thursday at 9, I have to remember that.", "Noted, Thursday at 9."),
 ("Also the church groups want a demo. Morgan moved it to Friday afternoon.", "Friday afternoon, got it."),
 ("Honestly I think Morgan is annoyed with me, I missed a standup.", "That might be worth checking rather than assuming. Did Morgan say anything?"),
 ("No, just a short message. Could be nothing.", "It might be. A short message isn't much to go on."),
 ("Ruth's results are back, it's pneumonia, she's in hospital for a few days.", "That's frightening. How is Ashley?"),
 ("Shaken. I'm going to cook for her tonight.", "That sounds like a good thing to do."),
 ("I've been thinking about whether I even want the lead. The evenings would wreck us right now.", "What does your gut say when you picture saying no?"),
 ("Relief, mostly. And then guilt, because Morgan trusted me with it.", "Relief and guilt can both be true."),
 ("I could ask Morgan whether Priya, who works on the other team, could co-lead instead.", "That could keep the trust and shrink the load."),
 ("Right. I'll sleep on it. Oh, I should also book the car in for its MOT before the 30th.", "MOT before the 30th, noted."),
 ("Actually update: Morgan has left Northwind. Still helping informally with Bloom as an advisor. My new manager is Priya Nair.", "That's a big change. How are you finding it?"),
 ("Fine. I need to correct something, Ruth is Ashley's aunt, not her mum. She's home from hospital and recovering.", "Thanks for the correction. Good that she's home."),
 ("Priya wants a status update on the Bloom pilot tomorrow. The demo is still Friday.", "Then tomorrow is the status update and the demo is Friday."),
 ("I don't think I'll take the lead after all. I'll tell Priya in the update.", "That sounds like a clear decision."),
 ("What should I put in the update, do you think?", "Progress so far, the demo date, and that you'd rather support than lead."),
 ("Good. Can you remind me about the MOT too?", "Yes, I'll keep the MOT in mind."),
 ("Thanks. I'm tired, going to bed.", "Sleep well."),
]
MSGS = []
for u, a in T:
    MSGS += [{"role": "user", "text": u}, {"role": "assistant", "text": a}]
KEYS = ["Ruth", "aunt", "Morgan", "left Northwind", "Priya", "Friday", "dentist", "MOT", "lead", "Ashley"]


async def main():
    state, out = None, []
    for n in range(rc.STEP_EVERY, len(MSGS) + 1):
        if not rc.should_step(n, int((state or {}).get("covered_through") or 0)):
            continue
        state = await rc.step(companion_id="sophie", messages=MSGS[:n], state=state, sitting_id="inspect")
        lines = rc.render_account(state)
        text = "\n".join(lines)
        out.append({"after_messages": n, "trace": {k: v for k, v in (state.get("trace") or {}).items() if k in ("pass", "checkpoint", "reconciled_chars", "model")},
                    "chars": len(text), "checkpoints": len(state.get("checkpoints") or []), "lines": lines,
                    "mentions": {k: (k.lower() in text.lower()) for k in KEYS}})
    print(json.dumps({"model": rc.model_for("sophie"), "total_messages": len(MSGS), "steps": out}, indent=1))

asyncio.run(main())
