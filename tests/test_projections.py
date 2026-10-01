"""Projections are views over canonical state: provenance on every claim,
nothing persisted of their own."""
from datetime import timedelta

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.matter import Matter
from src.services.projection_service import open_projections, why
from tests.cortex_fixtures import NOW, USER, WS, ago, build_longitudinal_world, naive

TZ = "Europe/London"


async def proj(**kw):
    async with async_session_maker() as db:
        return await open_projections(db, workspace_id=WS, owner_peer_id=USER, now=NOW, tz=TZ, **kw)


async def matter_by_title(p, needle):
    return next(m for m in p.r.matters.values() if needle.lower() in m.title.lower())


@pytest.mark.asyncio
async def test_user_overview_who_is_this_person():
    await build_longitudinal_world()
    ov = (await proj()).person()
    titles = {f["title"] for f in ov["facts"]}
    assert {"Grew up in Leeds", "Freelance designer", "Mum lives in Spain"} <= titles
    assert all(f["formation"] == "explicit" and f["evidence_refs"] for f in ov["facts"])
    assert {c["name"] for c in ov["circle"]} >= {"Ashley", "Mati", "Carlos", "Mum"}
    assert ov["routines_declared"] and ov["alive_matters"]
    assert not any("overextended" in c["title"] for c in ov["claims"])      # system perspective is not about the person


@pytest.mark.asyncio
async def test_person_card_for_an_entity_with_matters_claims_and_gaps():
    ids = await build_longitudinal_world()
    p = await proj()
    ash = p.person(ids["ashley"])
    assert ash["name"] == "Ashley" and ash["relationships"]
    assert any("unheard" in m["title"] for m in ash["matters"])
    claim = next(c for c in ash["claims"] if "defended" in c["title"])
    assert claim["formation"] == "reported" and claim["evidence_refs"][:2] == ["l-ash", "l-ash2"]
    mati = p.person(ids["mati"])
    assert any(c["subject_key"].endswith("/relationship") and c["status"] == "unknown" for c in mati["coverage"])
    assert p.person(__import__("uuid").uuid4())["found"] is False


@pytest.mark.asyncio
async def test_matter_card_separates_directions_claims_and_system_perspective():
    ids = await build_longitudinal_world()
    p = await proj()
    m = await matter_by_title(p, "feeling unheard")
    card = p.matter(m.id)
    assert card["found"] and card["kind"] == "relationship_situation"      # from a structured STRUGGLE tag
    assert card["components"] and "raw" not in card["components"]
    assert [c["formation"] for c in card["claims"]] == ["reported"]
    assert card["system_perspectives"] == []
    pres = p.matter((await matter_by_title(p, "Client presentation")).id)
    dirs = pres["by_direction"]
    assert any("stretch video" in i["title"] or "stretch video" in (i.get("summary") or "")
               for i in dirs["system_to_user"])        # the work Sophie owes lives under the same matter
    assert "user_self" in dirs
    assert card["summary"] is None                                          # no summary claim exists: not invented
    assert card["depth"]["longitudinal_read"]["matter_refs"] == [str(m.id)]


@pytest.mark.asyncio
async def test_matter_summary_is_a_reference_to_a_model_entry_not_a_second_truth():
    from src.services import matter_service as ms
    await build_longitudinal_world()
    p = await proj()
    m = await matter_by_title(p, "Client presentation")
    async with async_session_maker() as db:
        mm = await db.get(Matter, m.id)
        entry = await ms.set_matter_summary(db, mm, claim="Kai is presenting to a client this afternoon",
                                            formation="explicit", confidence=0.9, evidence_verbatim="presentation at 2",
                                            session_id="lane-1", message_id="e-pres", evidence_refs=["e-pres"])
        entry2 = await ms.set_matter_summary(db, mm, claim="Kai presented to the client", formation="explicit",
                                             confidence=0.9, evidence_verbatim="it went fine", session_id="lane-1",
                                             message_id="m-after")
        assert not hasattr(Matter, "current_summary")
        assert mm.summary_entry_id == entry2.id and (await db.get(type(entry), entry.id)).superseded_by_id == entry2.id
        read = await ms.current_summary(db, mm)
    assert read["claim"] == "Kai presented to the client" and read["formation"] == "explicit"
    card = (await proj()).matter(m.id)
    assert card["summary"]["claim"] == "Kai presented to the client"


@pytest.mark.asyncio
async def test_today_what_occupied_them_and_what_is_expected():
    await build_longitudinal_world()
    today = (await proj()).today()
    assert today["user_day"] == "2026-10-01"
    expected = {e["title"] for e in today["expected"]}
    assert "Client presentation" in expected
    assert "Send invoice to Carlos" not in expected                         # due in 2 days
    assert any(r["title"] == "Walk every morning" for r in today["routines_today"])
    assert today["activity"]["items_touched"] >= 1


@pytest.mark.asyncio
async def test_week_covers_occupied_resolved_and_the_week_ahead():
    await build_longitudinal_world()
    wk = (await proj()).week()
    assert {e["title"] for e in wk["expected_ahead"]} >= {"Send invoice to Carlos", "Call Mum on Sunday",
                                                         "Visit Mati in Manchester"}
    assert any(r["title"] == "Finish logo draft" for r in wk["resolved_this_week"])
    assert wk["occupied_this_week"]
    assert wk["changes"]


@pytest.mark.asyncio
async def test_period_and_timeline_are_ordered_and_provenanced():
    ids = await build_longitudinal_world()
    p = await proj()
    per = p.period(naive(NOW) - timedelta(days=10), naive(NOW) - timedelta(days=5))
    assert per["window"][0] < per["window"][1]
    m = await matter_by_title(p, "Visit Mati")
    tl = p.timeline(("matter", m.id))
    ats = [e["at"] for e in tl["events"]]
    assert ats == sorted(ats) and tl["events"][0]["event"] == "matter_first_seen"
    ent_tl = p.timeline(("entity", ids["carlos"]))
    assert ent_tl["events"] and all("formation" in e for e in ent_tl["events"] if e.get("ref"))
    with pytest.raises(ValueError):
        p.timeline(("topic", "x"))


@pytest.mark.asyncio
async def test_unresolved_keeps_unknown_outcomes_distinct_from_failure_and_shows_owed():
    await build_longitudinal_world()
    u = (await proj()).unresolved()
    assert u["constraints"]["unknown_is_not_failed"] is True
    titles = {o["title"] for g in u["by_matter"] for o in g["open"]}
    assert {"Carlos payment still outstanding", "Dentist appointment"} <= titles
    dentist = next(o for g in u["by_matter"] for o in g["open"] if o["title"] == "Dentist appointment")
    assert dentist["status"] == "unknown" and dentist["temporal_state"] in ("window_elapsed", "deadline_passed")
    assert any("Check in after the presentation" in o["title"] for o in u["owed_by_system"])
    assert [r["claim_kind"] for r in u["repair"]] == ["repair"] and "pushy" in u["repair"][0]["title"]


@pytest.mark.asyncio
async def test_recent_changes_surface_new_resolved_revised_and_relationship_developments():
    ids = await build_longitudinal_world()
    kinds = {c["change"] for c in (await proj()).recent_changes(days=14)["changes"]}
    assert {"new_matter", "matter_resolved", "relationship_development", "repair"} <= kinds
    assert {"user_to_system_recorded", "system_to_user_recorded"} & kinds
    assert "claim_conflict" in kinds


@pytest.mark.asyncio
async def test_depth_index_says_what_deeper_state_exists_and_how_to_reach_it():
    await build_longitudinal_world()
    d = (await proj()).depth()
    assert d["state"]["items_by_kind"]["expectation"] >= 6 and d["state"]["matters_by_status"]
    assert d["history"]["earliest_evidence_at"]
    assert "matter(matter_id)" in d["available_via"]["matter"]
    assert "longitudinal" in d["available_via"]["exact_quotes_and_obscure_history"]


@pytest.mark.asyncio
async def test_why_projection_explains_belief_from_canonical_rows():
    ids = await build_longitudinal_world()
    async with async_session_maker() as db:
        out = await why(db, "model_entry", ids["pattern"], naive(NOW))
    assert out["formation"] == "observed" and out["status"] == "current"
    assert out["claim_kind"] == "pattern"


@pytest.mark.asyncio
async def test_projections_persist_nothing_of_their_own():
    await build_longitudinal_world()
    p = await proj()
    p.today(); p.week(); p.unresolved(); p.person(); p.depth()
    from sqlalchemy import inspect as sa_inspect
    from src.db import engine
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: sa_inspect(c).get_table_names())
    assert not {"person_cards", "project_cards", "period_views", "projections"} & set(tables)


@pytest.mark.asyncio
async def test_product_weights_change_ranking_not_stored_truth():
    await build_longitudinal_world()
    neutral = await proj()
    weighted = await proj(kind_weights={"relationship_situation": 5.0})
    top_weighted = weighted._ranked_matters()[0]
    assert top_weighted.kind == "relationship_situation"
    async with async_session_maker() as db:
        kinds = {m.kind for m in (await db.execute(select(Matter))).scalars().all()}
    assert kinds <= {"project", "topic", "concern", "relationship_situation", "goal", "life_situation", "routine", "other"}
