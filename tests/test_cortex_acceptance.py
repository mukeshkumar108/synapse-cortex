"""ACCEPTANCE: from realistic longitudinal state Cortex answers the 20 prepared-state
questions WITHOUT raw Honcho retrieval (any Honcho call fails the test).

Fixture: one person ("Kai"), ~6 weeks, several durable lanes, system and user
state in both directions, declared and observed routines, reported/observed/
inferred/hypothesis claims, a repair, a boundary, a conflict, an unknown.
"""
import json

import pytest

from src.db import async_session_maker
from src.services import world_model_service as wm
from src.services.projection_service import open_projections, why
from tests.cortex_fixtures import NOW, USER, WS, build_longitudinal_world, naive

TZ = "Europe/London"


@pytest.fixture(autouse=True)
def no_honcho(monkeypatch):
    """Record (and fail) any raw Honcho request; swallowed exceptions can't hide it."""
    from src.clients import honcho_client
    calls = []

    async def forbidden(self, method, path, **k):
        calls.append((method, path))
        raise AssertionError("raw Honcho retrieval used for ordinary continuity")

    monkeypatch.setattr(honcho_client.HonchoClient, "_request", forbidden)
    yield calls
    assert calls == [], f"Honcho was called: {calls}"


@pytest.fixture
async def world():
    ids = await build_longitudinal_world()
    async with async_session_maker() as db:
        model = await wm.get_world_model(db, workspace_id=WS, owner_peer_id=USER, now=NOW, timezone_str=TZ)
        proj = await open_projections(db, workspace_id=WS, owner_peer_id=USER, now=NOW, tz=TZ)
    return ids, model, proj


def titles(items):
    return {i["title"] for i in items}


@pytest.mark.asyncio
async def test_q01_who_is_this_person(world):
    ids, model, proj = world
    ov = proj.person()
    assert {"Freelance designer", "Grew up in Leeds"} <= titles(ov["facts"])
    assert {"Ashley", "Mati", "Carlos", "Mum"} <= {c["name"] for c in ov["circle"]}
    assert model["person"]["facts"] and model["person"]["circle"]


@pytest.mark.asyncio
async def test_q02_relationship_and_history_with_the_system(world):
    _, model, _ = world
    rel = model["relationship_with_system"]
    assert rel["history"]["first_evidence_at"] and rel["history"]["items_recorded"] > 10
    assert rel["user_to_system"] and rel["system_to_user"]["commitments"]
    assert rel["shared"]["repair"] and rel["boundaries_and_preferences"][0]["topic"] == "the divorce"


@pytest.mark.asyncio
async def test_q03_what_occupied_them_today(world):
    _, model, proj = world
    today = proj.today()
    assert today["user_day"] == "2026-10-01" and today["activity"]["items_touched"] >= 1
    assert model["recent"]["today"]["activity"]


@pytest.mark.asyncio
async def test_q04_what_occupied_them_this_week(world):
    _, model, proj = world
    wk = proj.week()
    assert wk["occupied_this_week"] and wk["activity"]["distinct_user_messages"] >= 3
    assert model["recent"]["recent_days"]["occupied"] or model["recent"]["yesterday"]["occupied"]


@pytest.mark.asyncio
async def test_q05_what_materially_changed_recently(world):
    _, model, proj = world
    kinds = {c["change"] for c in model["recent"]["significant_changes"]}
    assert {"matter_resolved", "new_matter"} & kinds
    assert {"repair", "relationship_development"} & {c["change"] for c in proj.recent_changes(14)["changes"]}


@pytest.mark.asyncio
async def test_q06_which_matters_are_alive(world):
    _, model, _ = world
    active = titles(model["matters"]["active"])
    assert {"Client presentation", "Send invoice to Carlos", "Decide which flat to rent"} <= active
    assert model["matters"]["active_total"] >= 8 and model["matters"]["recently_resolved"]


@pytest.mark.asyncio
async def test_q07_currently_important_people(world):
    _, model, _ = world
    names = [p["name"] for p in model["people"]["salient"]]
    assert {"Ashley", "Carlos", "Mati"} <= set(names)
    assert all(p["matters"] for p in model["people"]["salient"])


@pytest.mark.asyncio
async def test_q08_what_remains_unresolved(world):
    _, model, proj = world
    u = proj.unresolved()
    flat = {o["title"] for g in u["by_matter"] for o in g["open"]}
    assert {"Carlos payment still outstanding", "Dentist appointment"} <= flat
    assert u["repair"] and u["owed_by_system"]
    assert model["unresolved"]["by_matter"] and model["unresolved"]["repair"]


@pytest.mark.asyncio
async def test_q09_what_is_expected_today_and_this_week(world):
    _, model, _ = world
    fwd = model["forward"]
    assert "Client presentation" in {i["title"] for i in fwd["today"]}
    assert {"Send invoice to Carlos", "Call Mum on Sunday"} <= {i["title"] for i in fwd["this_week"]}
    assert "Walk every morning" in fwd["routines_today"]


@pytest.mark.asyncio
async def test_q10_concerns_that_may_still_be_ongoing(world):
    ids, model, proj = world
    concerns = {m["title"] for m in model["matters"]["active"] if m["kind"] in ("concern", "relationship_situation")}
    assert "Conversation with Ashley about feeling unheard" in concerns


@pytest.mark.asyncio
async def test_q11_declared_routines_versus_observed_patterns(world):
    _, model, _ = world
    r = model["routines_patterns"]
    assert {"Walk every morning", "Evening meditation"} <= titles(r["declared"])
    assert "Gym on weekdays" in titles(r["observed"]) and "Gym on weekdays" not in titles(r["declared"])
    assert all(i["formation"] == "explicit" for i in r["declared"]) and all(i["formation"] == "observed" for i in r["observed"])
    assert r["pattern_claims"][0]["formation"] == "observed"


@pytest.mark.asyncio
async def test_q12_topics_that_could_be_naturally_resumed(world):
    _, model, proj = world
    topics = {m["title"] for m in model["matters"]["active"] if m["kind"] in ("topic", "life_situation", "goal")}
    assert {"Decide which flat to rent", "Mati's news about the new job"} <= topics
    resumable = proj.unresolved()["by_matter"]
    assert any("flat" in g["title"].lower() for g in resumable)


@pytest.mark.asyncio
async def test_q13_what_is_uncertain(world):
    _, model, _ = world
    u = model["uncertainty"]
    assert any(c["status"] == "conflicting" for c in u["claims"])
    assert any(o["title"] == "Dentist appointment" for o in u["outcome_unknown"])
    assert "not failure" in u["note"]


@pytest.mark.asyncio
async def test_q14_which_claims_are_explicit_reported_observed_inferred_hypothetical(world):
    _, model, _ = world
    seen = {c["formation"] for c in model["person"]["claims"]}
    seen |= {c["formation"] for c in model["routines_patterns"]["pattern_claims"]}
    seen |= {c["formation"] for c in model["relationship_with_system"]["shared"]["developments"]}
    seen |= {e["formation"] for e in model["system_perspective"]["entries"]}
    assert {"explicit", "reported", "observed", "hypothesis"} <= seen
    reported = next(c for c in model["relationship_with_system"]["shared"]["developments"] if "defended" in c["title"])
    assert reported["title"].startswith("kai has repeatedly reported") or "reported feeling" in reported["title"].lower()
    assert "ashley is defensive" not in json.dumps(model).lower()          # interpretation never compressed into fact


@pytest.mark.asyncio
async def test_q15_why_does_cortex_believe_an_important_claim(world):
    ids, _, _ = world
    async with async_session_maker() as db:
        out = await why(db, "model_entry", ids["reported"], naive(NOW))
        loop_out = await why(db, "open_loop", ids["ash_loop"], naive(NOW))
    assert out["formation"] == "reported" and out["evidence_refs"][:2] == ["l-ash", "l-ash2"] and out["confidence"] == 0.9
    assert out["evidence_verbatim"] and loop_out["evidence_refs"] == ["l-ash"]


@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_q18_what_important_things_do_we_not_know(world):
    _, model, proj = world
    gaps = {g["subject_key"]: g for g in model["coverage"]["gaps"]}
    assert "routines/walk_morning/timing" in gaps and gaps["routines/walk_morning/timing"]["status"] == "unknown"
    assert "people/mati/relationship" in gaps
    assert all("value" not in g for g in gaps.values())                    # an unknown never holds a guess


@pytest.mark.asyncio
async def test_q19_what_is_partial_stale_or_conflicting(world):
    _, model, proj = world
    cov = {c["subject_key"]: c["status"] for c in proj.coverage}
    assert cov["routines/gym_weekdays"] == "partial"
    assert "conflicting" in cov.values() and "known" in cov.values()
    assert model["coverage"]["counts"].keys() >= {"known", "partial", "unknown", "conflicting"}


@pytest.mark.asyncio
async def test_q20_what_would_be_useful_to_learn_naturally_over_time(world):
    _, _, proj = world
    gaps = proj.knowledge_gaps()["gaps"]
    assert gaps and all(g["eligible_for_curiosity"] and g["why_useful"] for g in gaps if g["evidence_count"] or "/" in g["subject_key"])
    assert any(g["subject_key"] == "people/mati/relationship" for g in gaps)
    assert all("not an instruction" in g["note"] for g in gaps)


@pytest.mark.asyncio
async def test_unknown_never_leaks_into_inference_and_nothing_filled_to_complete_a_profile(world):
    _, model, proj = world
    blob = json.dumps(model).lower()
    # we know Mati only as a person with unstated role: no invented relationship anywhere
    for invented in ("mati is kai's brother", "mati's role", "friend of kai", "mati, kai's"):
        assert invented not in blob
    mati = proj.person(world[0]["mati"])
    assert mati["relationships"] == [] and any(c["status"] == "unknown" for c in mati["coverage"])
    # walk timing: no preferred_window invented for the declared walk
    walk = next(i for i in model["routines_patterns"]["declared"] if i["title"] == "Walk every morning")
    assert "preferred_window" not in walk or walk["preferred_window"] is None


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_deep_history_falls_through_to_bounded_longitudinal_read_by_matter(world):
    _, model, proj = world
    from src.longitudinal_read.interface import ask_longitudinal
    from src.longitudinal_read.query_discipline import QueryRejected
    mid = next(m["id"] for m in model["matters"]["active"] if "Carlos" in m["title"])
    card = proj.matter(__import__("uuid").UUID(mid))
    ref = card["depth"]["longitudinal_read"]["matter_refs"][0]
    read = ask_longitudinal(question="What exactly did Carlos say about the invoice?", scope=f"matter:{ref}",
                            temporal_cutoff="2026-10-01T10:00:00Z", matter_refs=[ref],
                            need="user asks for the exact wording", query_terms=["carlos", "invoice"])
    assert read is not None                                               # the rung exists and is matter-bounded
    with pytest.raises(QueryRejected):
        ask_longitudinal(question="Tell me about this person", scope="person", temporal_cutoff="2026-10-01T10:00:00Z",
                         need="x")                                          # a profile dossier is never a read
