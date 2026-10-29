"""The read side: deterministic, time-aware views over stored records. No model; plain rows + a clock.

A scheduled thing whose time passed is "to check up on" (outcome unknown), NOT overdue; a deadline that passed
while open IS overdue; precision is never invented; time passing never completes anything.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from src.services import ledger_views as lv

LON = ZoneInfo("Europe/London")


def row(key, title, date_=None, time_="", role="", status="open", imp=2, waiting_on="", question="", tz="Europe/London", updated="2026-10-19", created="2026-10-18T09:00:00"):
    return {"key": key, "title": title, "status": status, "kind": "event", "expected_date": date_, "expected_time": time_, "time_role": role,
            "importance": imp, "waiting_on": waiting_on, "question": question, "time_zone": tz, "detail": "", "updated_at": updated, "created_at": created}


LEDGER = [
    row("vinesh-call", "Call with Vinesh", "2026-10-20", "15:00", "happens", imp=3),
    row("proposal", "Submit the proposal", "2026-10-20", "17:00", "deadline", imp=3),
    row("dentist", "Dentist appointment", "2026-10-19", "14:00", "happens"),
    row("dentist2", "Dental check-up", "2026-10-22", "", "happens", question="what time?"),
    row("invoice", "Pay the invoice", "2026-10-18", "", "deadline"),
    row("review", "Project review", "2026-10-23", "", "happens"),
    row("ana", "Ana's figures", None, "", "", status="waiting", waiting_on="Ana"),
    row("marathon", "Run a marathon", None, "", ""),
    row("james", "James's invoice approval", None, status="done", updated="2026-10-19"),
]


def at(h, m=0, day=20, tz=LON):
    return datetime(2026, 10, day, h, m, tzinfo=tz)


def bands(now, rows=LEDGER, tz="Europe/London"):
    v = lv.compute(rows, now, tz)
    return {b: [i.key for i in items] for b, items in v["bands"].items() if items}, v


def test_the_morning_picture():
    b, v = bands(at(9))
    assert b["today"] == ["vinesh-call", "proposal"]                 # 6h and 8h away: today, not imminent
    assert "imminent" not in b
    assert b["check_up_on"] == ["dentist"]                           # scheduled yesterday 2pm: outcome unknown, NOT overdue
    assert b["overdue"] == ["invoice"]                               # a deadline that passed while open
    assert b["waiting"] == ["ana"] and b["undated"] == ["marathon"]
    assert b["week"] == ["dentist2", "review"]
    assert [i.title for i in v["closed"]] == ["James's invoice approval"]


def test_imminent_window_and_what_changes_as_the_day_passes():
    assert bands(at(12, 30))[0]["imminent"] == ["vinesh-call"]       # 2.5h away
    assert bands(at(14, 30))[0]["imminent"] == ["vinesh-call", "proposal"]
    b, _ = bands(at(15, 30))
    assert "vinesh-call" in b["check_up_on"] and "vinesh-call" not in b.get("overdue", [])      # the call time passed: not "missed"
    assert b["imminent"] == ["proposal"]
    b, _ = bands(at(17, 30))
    assert "proposal" in b["overdue"] and "proposal" not in b.get("check_up_on", [])               # the deadline passed: overdue
    b, _ = bands(at(9, day=21))
    assert "vinesh-call" in b["check_up_on"] and "dentist" in b["check_up_on"]


def test_passed_items_stop_claiming_the_foreground_but_are_not_deleted():
    b, v = bands(at(9, day=25))
    assert "dentist" in b["older"] and "dentist" not in b.get("check_up_on", [])
    assert v["bands"]["older"] and "Older, still open" in lv.render(v)


def test_time_zones_are_respected_not_assumed():
    la = [row("c", "Call", "2026-10-19", "21:30", "happens", tz="America/Los_Angeles")]
    now_utc = datetime(2026, 10, 20, 4, 0, tzinfo=timezone.utc)               # 21:00 Monday in Los Angeles
    b, _ = bands(now_utc, la, "America/Los_Angeles")
    assert b["imminent"] == ["c"]                                              # 30 minutes away in HER time
    b, _ = bands(datetime(2026, 10, 20, 5, 0, tzinfo=timezone.utc), la, "America/Los_Angeles")
    assert b["check_up_on"] == ["c"]
    # the same instant seen from a UK reader of that record is still the record's own zone
    b, _ = bands(datetime(2026, 10, 20, 4, 0, tzinfo=timezone.utc), la, "Europe/London")
    assert b["imminent"] == ["c"]


def test_precision_is_never_invented():
    only_day = [row("d", "Dentist", "2026-10-20", "", "happens"), row("e", "Pay rent", "2026-10-20", "", "deadline")]
    b, v = bands(at(23, 30), only_day)
    assert b["today"] == ["d", "e"]                                            # date-only items stay "today" until the day is over
    txt = lv.render(v)
    assert "time not recorded" in txt                                          # a scheduled thing with no time says so
    assert lv.render(lv.compute([row("n", "Call", "2026-10-21", "", "deadline")], at(9), "Europe/London")).count("time not recorded") == 0
    b, _ = bands(at(0, 5, day=21), only_day)
    assert b["check_up_on"] == ["d"] and b["overdue"] == ["e"]                 # next day: event -> check up on, deadline -> overdue


def test_importance_orders_within_a_band_only_and_time_still_leads():
    rs = [row("a", "Casual", "2026-10-22", "", "happens", imp=1), row("b", "Major", "2026-10-22", "", "happens", imp=3),
          row("c", "Earlier but casual", "2026-10-21", "", "happens", imp=1)]
    b, _ = bands(at(9), rs)
    assert b["week"] == ["c", "b", "a"]                                        # date first, then importance


def test_render_is_factual_and_never_instructs():
    txt = lv.render(lv.compute(LEDGER, at(12), "Europe/London"))
    for must in ("[OPERATIONAL AWARENESS — Tuesday 20 October 2026, 12:00pm (Europe/London)", "Right now (next 3 hours):", "Today:", "Overdue:",
                 "Things to check up on:", "Waiting on:", "This week:", "was scheduled for yesterday (Mon 19 Oct), 2:00pm; outcome not recorded",
                 "was due Sun 18 Oct; not marked done", "waiting on Ana", "open question: what time?", "Recently closed: James's invoice approval."):
        assert must in txt, must
    low = txt.lower()
    for banned in ("consider", "perhaps", "you could", "if relevant", "you might", "remind", "should"):
        assert banned not in low, banned
    assert lv.render(lv.compute([], at(9), "Europe/London")) == ""             # nothing to say, nothing said


def test_cues_have_one_shared_shape_and_do_not_duplicate_state():
    v = lv.compute(LEDGER, at(14), "Europe/London")
    cs = lv.cues(v)
    assert all(set(c) == {"source", "key", "title", "band", "line", "when", "time_basis", "importance"} and c["source"] == "ledger" for c in cs)
    assert len({c["key"] for c in cs}) == len(cs)                              # each record appears once


@pytest.mark.parametrize("kw,expect", [("today", ("2026-10-20", "2026-10-20")), ("tomorrow", ("2026-10-21", "2026-10-21")),
                                       ("week", ("2026-10-20", "2026-10-26")), ("next_week", ("2026-10-26", "2026-11-01")),
                                       ("month", ("2026-10-20", "2026-10-31")), ("next_month", ("2026-11-01", "2026-11-30"))])
def test_period_keywords(kw, expect):
    s, e = lv.resolve_range(kw, date(2026, 10, 20))
    assert (s.isoformat(), e.isoformat()) == expect
    with pytest.raises(ValueError):
        lv.resolve_range("fortnight", date(2026, 10, 20))


def test_schedule_for_the_week_is_a_full_range_query_over_the_same_records():
    s, e = lv.resolve_range("week", date(2026, 10, 20))
    out = lv.render_range(LEDGER, s, e, at(14), "Europe/London")
    t = out["text"]
    assert t.index("Tuesday 20 October (today):") < t.index("Thursday 22 October:") < t.index("Friday 23 October:")
    assert "- 3:00pm Call with Vinesh" in t and "- 5:00pm due Submit the proposal" in t
    assert "Earlier, still open:" in t and "Dentist appointment" in t and "Pay the invoice" in t
    assert "Dental check-up" in t and "time not recorded" in t
    assert "Ana's figures" not in t and "marathon" not in t.lower()            # undated items are not in a date range
    empty = lv.render_range(LEDGER, date(2026, 12, 1), date(2026, 12, 7), at(14), "Europe/London")
    assert "Nothing recorded for this period." in empty["text"]
    done = lv.render_range(LEDGER + [row("x", "Finished thing", "2026-10-20", "09:00", "happens", status="done")], s, e, at(14), "Europe/London", include_closed=True)
    assert "Finished thing [done]" in done["text"]


def test_a_malformed_row_degrades_instead_of_breaking_the_picture():
    bad = [{"key": "z", "title": "Odd", "status": "open", "expected_date": "not-a-date", "expected_time": "99:99", "importance": None}]
    v = lv.compute(bad, at(9), "Not/AZone")
    assert [i.key for i in v["bands"]["undated"]] == ["z"]


def test_an_assumed_time_informs_the_view_but_is_labelled_and_never_authorises_an_action():
    rows = [row("mum", "Call Mum", "2026-10-20", "18:00", "happens") | {"time_basis": "assumed", "question": "6 am or 6 pm?"},
            row("vin", "Call with Vinesh", "2026-10-20", "15:00", "happens") | {"time_basis": "stated"}]
    v = lv.compute(rows, at(16), "Europe/London")
    txt = lv.render(v)
    assert "Call Mum: 6:00pm (assumed; not confirmed) today; open question: 6 am or 6 pm?" in txt     # used for the picture, honestly labelled
    assert "Call with Vinesh" in txt and "(assumed" not in txt.split("Call with Vinesh")[1].split("\n")[0]
    items = {i.key: i for items in v["bands"].values() for i in items}
    assert lv.confirmed_instant(items["mum"]) is None                                         # an assumption never authorises a timed action
    assert lv.confirmed_instant(items["vin"]) is not None
    assert {c["key"]: c["time_basis"] for c in lv.cues(v)} == {"mum": "assumed", "vin": "stated"}
    sched = lv.render_range(rows, date(2026, 10, 20), date(2026, 10, 20), at(9), "Europe/London")["text"]
    assert "6:00pm (assumed) Call Mum" in sched


def test_a_companions_own_matters_never_appear_on_the_persons_plate():
    mine = row("see-photos", "See photos of the walks")
    mine["party"] = "companion"
    theirs = row("dentist-x", "Dentist", "2026-10-22", "09:00", "happens")
    theirs["party"] = "user"
    view = lv.compute([mine, theirs, row("legacy", "Old row with no party recorded")], datetime(2026, 10, 20, 12, tzinfo=LON), "Europe/London")
    text = lv.render(view)
    assert "Dentist" in text and "Old row with no party recorded" in text and "See photos" not in text      # unknown party is treated as the person's


# --- the companion's own commitments reach her, as hers ---------------------------------------------------------------------------------------------------------------

def hers_rows():
    promise = row("sophie-questions", "Sophie to prepare questions for Josh", "2026-10-29", "", "deadline", status="waiting", waiting_on="Sophie")
    promise["party"] = "shared"
    walk = row("walk", "Morning walk", "2026-10-29", "", "happens")
    walk["party"] = "shared"                                    # something they do together: his plate, nobody's debt
    wish = row("owl", "See the owl photos", None, "", "")
    wish["party"], wish["kind"] = "companion", "curiosity"      # a private wish: nobody's plate, nobody's promise
    own = row("list", "Send Mukesh the reading list", "2026-10-30", "", "")
    own["party"], own["kind"] = "companion", "commitment"       # hers alone, but a promise to him
    lunch = row("lunch", "Lunch with friend in Cambridge", "2026-10-29", "", "happens")
    return [promise, walk, wish, own, lunch]


def test_a_promise_the_companion_made_is_shown_to_her_as_hers_and_not_as_the_persons_to_do():
    text = lv.render(lv.compute(hers_rows(), at(11, day=29), "Europe/London", companion_name="Sophie"))
    persons_part, hers_part = text.split("Yours (", 1)
    assert "Sophie to prepare questions for Josh" not in persons_part and "Send Mukesh the reading list" not in persons_part
    assert "Morning walk" in persons_part and "Lunch with friend" in persons_part
    assert "Sophie to prepare questions for Josh: today" in hers_part and "Send Mukesh the reading list: tomorrow" in hers_part
    assert "waiting on Sophie" not in hers_part, "she is not told she is waiting on herself"
    assert "owl" not in text, "a private wish stays private"


def test_without_a_companion_the_view_is_what_it_was():
    text = lv.render(lv.compute(hers_rows(), at(11, day=29), "Europe/London"))
    assert "Yours (" not in text and "Sophie to prepare questions for Josh" in text and "owl" not in text


def test_a_promise_whose_day_has_passed_is_history_not_an_overdue_debt():
    text = lv.render(lv.compute(hers_rows(), at(9, day=30), "Europe/London", companion_name="Sophie"))
    hers_part = text.split("Yours (", 1)[1]
    assert "Sophie to prepare questions for Josh: was for yesterday (Thu 29 Oct); not recorded as done" in hers_part
    assert "overdue" not in hers_part.lower() and "was due" not in hers_part


def test_an_old_promise_leaves_the_picture_like_anything_else_and_a_done_one_never_shows():
    old = hers_rows()
    done = [dict(r, status="done") for r in old]
    assert "Yours (" not in lv.render(lv.compute(done, at(11, day=29), "Europe/London", companion_name="Sophie"))
    assert "Sophie to prepare questions for Josh" not in lv.render(lv.compute(old, at(11, day=5, tz=LON).replace(month=11), "Europe/London", companion_name="Sophie"))


def test_the_schedule_never_shows_the_companions_private_rows():
    out = lv.render_range(hers_rows(), date(2026, 10, 29), date(2026, 10, 31), at(11, day=29), "Europe/London")
    assert "owl" not in out["text"] and "reading list" not in out["text"]
