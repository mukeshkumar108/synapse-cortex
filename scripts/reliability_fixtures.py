"""Reliability fixtures: fixed multi-sitting transcripts + independently defined
expectations about the USER'S AFFAIRS (rows, statuses, dates) — never which tags,
ops or titles a model must emit. Equivalent correct end states all pass.

Every sitting carries its own `session_time` and `time_zone`, so relative words
("Thursday", "tomorrow") resolve against when the person spoke and expectations
never rot with the calendar. Sittings run on Monday 2026-10-19, Europe/London.

An expectation is a dict evaluated by eval_reliability.check():
  select   - which rows it is about: {"any": [needles]}  (needle in title|detail|timing)
             optionally {"title_any": [...]} (needle in title only)
  count    - (min, max) rows selected
  status_in / status_not_in / date_in / kind
  mention  - regexes; EVERY one must match somewhere in the selected rows' text
  mention_any - at least one regex must match
  none_with_status - no selected row may have these statuses
  `at` - the session after which it is checked (default: the last)
"""
import json

TZ = "Europe/London"
MON_EVE = "2026-10-19T20:00:00+01:00"
MON_LATE = "2026-10-19T20:30:00+01:00"
MON_LATER = "2026-10-19T21:00:00+01:00"

TWO_PM = r"\b(2\s?pm|2:00\s?pm|2\s?p\.m\.|14[:.]00)\b"


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
            ("dl1", MON_EVE, [("Dentist on Thursday, not sure what time yet.", "We will pin down the time.")]),
            ("dl2", MON_LATE, [("Did you ever find out what time the dentist is?", "Not yet, no idea honestly.")]),
            ("dl3", MON_LATER, [("Mum just texted, dentist is at 2pm.", "Thursday 2pm, locked in.")]),
        ],
        "expected": [
            {"name": "dentist: one row, still open/waiting, Thursday date", "at": "dl1",
             "select": {"any": ["dentist"]}, "count": (1, 1), "status_in": ["open", "waiting"], "date_in": ["2026-10-22"]},
            {"name": "dentist: one row, not closed by a non-event", "at": "dl2",
             "select": {"any": ["dentist"]}, "count": (1, 1), "status_in": ["open", "waiting"]},
            {"name": "dentist after dl3: one row, OPEN (time confirmed does not close it), Thursday, 2pm kept",
             "select": {"any": ["dentist"]}, "count": (1, 1), "status_in": ["open"], "date_in": ["2026-10-22"],
             "mention": [TWO_PM]},
        ],
    },
    "vinesh-reschedule": {
        "sessions": [
            ("vr1", MON_EVE, [("I promised Vinesh I would send the proposal by Thursday.", "Noted, Thursday.")]),
            ("vr2", MON_LATE, [("Ana finally sent the numbers. Also Vinesh moved the review to Friday morning.", "Friday it is.")]),
            ("vr3", MON_LATER, [("Sent the Vinesh proposal this morning, all done.", "Great, closed.")]),
        ],
        "expected": [
            {"name": "proposal recorded with its Thursday deadline", "at": "vr1",
             "select": {"title_any": ["proposal"], "exclude_title_any": ["review", "meeting"]}, "count": (1, 1), "status_in": ["open", "waiting"], "date_in": ["2026-10-22"]},
            {"name": "a moved review does NOT close the proposal; Friday is recorded somewhere", "at": "vr2",
             "select": {"title_any": ["proposal"], "exclude_title_any": ["review", "meeting"]}, "count": (1, 1), "status_in": ["open", "waiting", "watching"]},
            {"name": "Friday recorded (date 2026-10-23 or the word Friday) on a vinesh/review row", "at": "vr2",
             "select": {"any": ["vinesh", "review"]}, "mention_any": [r"2026-10-23", r"friday"]},
            {"name": "proposal done exactly once, date kept (Thursday or the moved Friday), never today",
             "select": {"title_any": ["proposal"], "exclude_title_any": ["review", "meeting"]}, "count": (1, 1), "status_in": ["done"], "date_in": ["2026-10-22", "2026-10-23"]},
            {"name": "no stray open rows about the finished proposal",
             "select": {"title_any": ["proposal"], "exclude_title_any": ["review", "meeting"]}, "none_with_status": ["open", "waiting", "watching"]},
            {"name": "bounded size (no junk rows)", "select": {"any": ["vinesh", "proposal", "review", "ana", "numbers"]}, "count": (1, 4)},
        ],
    },
    "mixed-plate": {
        "sessions": [
            ("mp1", MON_EVE, [("Invoice from James is waiting on his approval.", "Watching it."),
                              ("I might run a marathon someday.", "Someday, sure."),
                              ("Remind me to call Mum tomorrow at 6.", "Will do.")]),
            ("mp2", MON_LATE, [("James approved the invoice this morning.", "Closed loop."),
                               ("Pete keeps pinging about SSH; ignore him tonight.", "Ignoring.")]),
        ],
        "expected": [
            {"name": "invoice tracked after mp1", "at": "mp1", "select": {"any": ["invoice"]}, "count": (1, 1),
             "status_in": ["open", "waiting", "watching"]},
            {"name": "marathon is an open aspiration, never a task", "at": "mp1", "select": {"any": ["marathon"]}, "count": (1, 1),
             "status_in": ["open"], "kind": "aspiration"},
            {"name": "call Mum: open, tomorrow = 2026-10-20 (resolved against Monday), the 6 kept", "at": "mp1",
             "select": {"any": ["mum"]}, "count": (1, 1), "status_in": ["open"], "date_in": ["2026-10-20"],
             "mention": [r"\b(6|6\s?pm|18[:.]00)\b"]},
            {"name": "invoice done after approval", "select": {"any": ["invoice"]}, "count": (1, 1), "status_in": ["done"]},
            {"name": "marathon still an open aspiration", "select": {"any": ["marathon"]}, "count": (1, 1),
             "status_in": ["open"], "kind": "aspiration"},
            {"name": "call Mum still open", "select": {"any": ["mum"]}, "count": (1, 1), "status_in": ["open"]},
            {"name": "Pete is suppressed, not deleted, no duplicate", "select": {"any": ["pete"]}, "count": (1, 1),
             "status_in": ["suppressed"]},
        ],
    },
    "busy-day": {
        "sessions": [
            ("bd1", "2026-10-20T08:30:00+01:00", [
                ("Busy day. I've got a call with Vinesh at 3pm today, and I need to submit the proposal by 5pm. Also the dentist is on Thursday but I don't know what time yet.", "Noted."),
                ("Oh and remind me to call Mum tomorrow at 6. Still waiting on Ana for the figures.", "Will do."),
                ("And I never paid the electricity bill, it was due on Sunday.", "Noted.")]),
        ],
        "expected": [
            {"name": "call: Tuesday 15:00, happens", "select": {"title_any": ["vinesh"]}, "count": (1, 1), "date_in": ["2026-10-20"],
             "fields": {"expected_time": ["15:00"], "time_basis": ["stated"], "time_role": ["happens"]}},
            {"name": "proposal: Tuesday 17:00, deadline", "select": {"title_any": ["proposal"], "exclude_title_any": ["review", "meeting"]}, "count": (1, 1), "date_in": ["2026-10-20"],
             "fields": {"expected_time": ["17:00"], "time_basis": ["stated"], "time_role": ["deadline"]}},
            {"name": "dentist: Thursday, time NOT invented, happens, the gap is recorded", "select": {"title_any": ["dentist"]}, "count": (1, 1),
             "date_in": ["2026-10-22"], "fields": {"expected_time": [""], "time_role": ["happens"]}, "mention": [r"time|what time|when"]},
            {"name": "Mum: tomorrow; an ambiguous 6 may be read as 18:00 ONLY if recorded as assumed, with the person's words and the open question kept",
             "select": {"title_any": ["mum"]}, "count": (1, 1), "date_in": ["2026-10-21"],
             "fields": {"expected_time": ["", "18:00"]}, "when_set": {"expected_time": {"time_basis": ["assumed"]}}, "mention": [r"\b6\b", r"am|pm|morning|evening"]},
            {"name": "Ana's outstanding figures are recorded (as their own row or as the wait on the proposal)", "select": {"any": ["ana", "figures"]}, "count": (1, 3),
             "mention": [r"ana"]},
            {"name": "electricity bill: due Sunday, a deadline", "select": {"title_any": ["electric"]}, "count": (1, 1), "date_in": ["2026-10-18"],
             "fields": {"time_role": ["deadline"]}},
        ],
        "views": [
            {"now": "2026-10-20T09:00:00+01:00", "in": {"Today": ["Vinesh", "proposal"], "Overdue": ["electric"], "This week": ["Dentist", "Mum"]},
             "not_in": {"Right now": ["Vinesh"]}},
            {"now": "2026-10-20T12:30:00+01:00", "in": {"Right now": ["Vinesh"], "Today": ["proposal"]}},
            {"now": "2026-10-20T14:30:00+01:00", "in": {"Right now": ["Vinesh", "proposal"]}},
            {"now": "2026-10-20T15:30:00+01:00", "in": {"Things to check up on": ["Vinesh"], "Right now": ["proposal"]}, "not_in": {"Overdue": ["Vinesh"]}},
            {"now": "2026-10-20T17:30:00+01:00", "in": {"Overdue": ["proposal", "electric"], "Things to check up on": ["Vinesh"]}},
            {"now": "2026-10-21T09:00:00+01:00", "in": {"Today": ["Mum"], "Overdue": ["proposal"], "Things to check up on": ["Vinesh"]}},
        ],
        "range": {"now": "2026-10-20T08:30:00+01:00", "period": "week", "contains": ["Tuesday 20 October", "Thursday 22 October", "Dentist", "time not recorded", "3:00pm"]},
    },
}

if __name__ == "__main__":
    print(json.dumps({k: {"sessions": len(v["sessions"]), "expected": [e["name"] for e in v["expected"]]}
                      for k, v in FIXTURES.items()}, indent=1))
