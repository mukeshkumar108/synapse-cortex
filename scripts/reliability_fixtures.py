"""Reliability fixtures: fixed multi-sitting transcripts + independently defined
expected final ledger states. Expectations describe the USER'S AFFAIRS (rows,
statuses, dates), never which tags or ops the model must emit."""
import json

def msg(sid, i, role, text):
    return {"id": f"{sid}-{i}-{role[0]}", "speaker": role, "text": text}

def sess(pairs, sid):
    out = []
    for i, (u, a) in enumerate(pairs):
        out.append(msg(sid, i, "user", u))
        out.append(msg(sid, i, "assistant", a))
    return out

FIXTURES = {
    "dentist-lifecycle": {
        "sessions": [
            ("dl1", [("Dentist on Thursday, not sure what time yet.", "We will pin down the time.")]),
            ("dl2", [("Did you ever find out what time the dentist is?", "Not yet, no idea honestly.")]),
            ("dl3", [("Mum just texted, dentist is at 2pm.", "Thursday 2pm, locked in.")]),
        ],
        "expected": [
            {"title_contains": "dentist", "status": "open", "expected_date": "2026-10-22",
             "must_mention": ["2pm", "Thursday"]},
        ],
        "forbidden": ["duplicate dentist rows", "closed before appointment"],
    },
    "vinesh-reschedule": {
        "sessions": [
            ("vr1", [("I promised Vinesh I would send the proposal by Thursday.", "Noted, Thursday.")]),
            ("vr2", [("Ana finally sent the numbers. Also Vinesh moved the review to Friday morning.", "Friday it is.")]),
            ("vr3", [("Sent the Vinesh proposal this morning, all done.", "Great, closed.")]),
        ],
        "expected": [
            {"title_contains": "vinesh", "status": "done", "expected_date": "2026-10-23"},
        ],
        "forbidden": ["two vinesh rows", "thursday date surviving the move"],
    },
    "mixed-plate": {
        "sessions": [
            ("mp1", [("Invoice from James is waiting on his approval.", "Watching it."),
                     ("I might run a marathon someday.", "Someday, sure."),
                     ("Remind me to call Mum tomorrow at 6.", "Will do.")]),
            ("mp2", [("James approved the invoice this morning.", "Closed loop."),
                     ("Pete keeps pinging about SSH; ignore him tonight.", "Ignoring.")]),
        ],
        "expected": [
            {"title_contains": "invoice", "status": "done"},
            {"title_contains": "marathon", "status": "open", "kind": "aspiration"},
            {"title_contains": "mum", "status": "open"},
            {"title_contains": "pete", "status": "suppressed"},
        ],
        "forbidden": ["marathon as commitment", "marathon closed by silence", "pete deleted"],
    },
}

if __name__ == "__main__":
    print(json.dumps({k: {"sessions": len(v["sessions"]), "expected": v["expected"]} for k, v in FIXTURES.items()}, indent=1))
