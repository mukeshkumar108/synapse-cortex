"""AttentionState: what has unusually high relevance in this temporal window —
scoped, Matter-linked, permission never instruction, separate from the WorldModel."""
import pytest

from src.db import async_session_maker
from src.services import world_model_service as wm
from src.services.attention_state_service import AttentionStateService
from tests.cortex_fixtures import NOW, SYSTEM, USER, WS, ago, build_longitudinal_world, exp, loop, save

TZ = "Europe/London"
svc = AttentionStateService()


async def state(now=NOW, session="lane-1", peer=USER):
    async with async_session_maker() as db:
        return await svc.compile_attention_state(db=db, workspace_id=WS, session_id=session, now=now,
                                                 timezone_str=TZ, owner_peer_id=peer)


async def prepared():
    ids = await build_longitudinal_world()
    async with async_session_maker() as db:     # prepared Cortex: matters + coverage exist
        await wm.compile_world_model(db, workspace_id=WS, owner_peer_id=USER, now=NOW, timezone_str=TZ)
    return ids


@pytest.mark.asyncio
async def test_scopes_replace_the_brief_and_no_editorial_layers_remain():
    await prepared()
    st = await state()
    assert set(st["window"]["scopes"]) == {"immediate", "today", "upcoming", "unresolved", "review_needed"}
    for gone in ("intelligence_brief", "continuity_context", "handover"):
        assert gone not in st
    assert st["window"]["constraints"]["eligibility_is_not_instruction"] is True
    assert st["window"]["daypart"] == "morning" and st["window"]["user_day"] == "2026-10-01"
    immediate = {i["title"] for i in st["window"]["scopes"]["immediate"]}
    assert "Client presentation" in immediate or "Client presentation" in {i["title"] for i in st["window"]["scopes"]["today"]}


@pytest.mark.asyncio
async def test_elapsed_unknown_outcome_is_unresolved_not_failure():
    await prepared()
    st = await state()
    unresolved = {i["title"]: i for i in st["window"]["scopes"]["unresolved"]}
    assert "Dentist appointment" in unresolved
    assert "do not claim failure" in unresolved["Dentist appointment"]["uncertainty"].lower()
    assert unresolved["Dentist appointment"]["suggested_move"] == "ask_outcome_if_natural"


@pytest.mark.asyncio
async def test_items_and_window_link_to_matters_with_inspectable_components():
    ids = await prepared()
    st = await state()
    linked = [i for i in st["followups"] + st["active_expectations"] + st["open_loops"] if i.get("matter_id")]
    assert linked
    miw = st["matters_in_window"]
    assert miw and len(miw) <= 5
    for m in miw:
        assert set(m["components"]) >= {"recency", "temporal_pressure", "unresolvedness"}
        assert m["in_scopes"] and "salience" not in m["components"]
    assert [m["rank"] for m in miw] == sorted((m["rank"] for m in miw), reverse=True)


@pytest.mark.asyncio
async def test_eligible_list_is_bounded_and_every_entry_explains_why_now():
    await prepared()
    st = await state()
    assert len(st["eligible"]) <= 5
    assert all(e["why_relevant_now"] and "topic" in e for e in st["eligible"])


@pytest.mark.asyncio
async def test_known_unknowns_feed_curiosity_as_permission_with_cooldown():
    await prepared()
    st = await state()
    gaps = st["knowledge_gaps"]
    assert gaps and gaps[0]["type"] == "knowledge_gap" and gaps[0]["reason"]
    assert "value" not in gaps[0]
    assert any(c["type"] == "knowledge_gap" for c in st["curiosity"]) and len(st["curiosity"]) <= 3


@pytest.mark.asyncio
async def test_suppressions_still_dominate_attention():
    await prepared()
    await save(exp("Talk about the divorce paperwork", message="e-div", created=ago(1)))
    st = await state()
    titles = {i["title"] for k in ("active_expectations", "followups") for i in st[k]}
    assert "Talk about the divorce paperwork" not in titles
    assert any(s["topic_or_entity"] == "the divorce" for s in st["suppressed_targets"])


@pytest.mark.asyncio
async def test_attention_state_and_world_model_are_separate_concepts():
    await prepared()
    st = await state()
    async with async_session_maker() as db:
        world = await wm.get_world_model(db, workspace_id=WS, owner_peer_id=USER, now=NOW, timezone_str=TZ)
    assert "window" in st and "window" not in world
    assert "matters" in world and "matters" not in st            # attention only names matters in the window
    assert "person" in world and "person" not in st


@pytest.mark.asyncio
async def test_follow_through_ledger_and_evaluate_arm(async_client, monkeypatch):
    from src.routers import v1_cortex
    monkeypatch.setattr(v1_cortex, "get_agenda_adapter", lambda: None)
    await prepared()
    body = {"workspace_id": WS, "session_id": "lane-1", "peer_id": USER, "now": NOW.isoformat(),
            "timezone": TZ, "turn_text": "morning"}
    r = await async_client.post("/v1/cortex/attention-state", json=body)
    assert r.status_code == 200, r.text
    ft = r.json()["follow_through"]
    assert set(ft) >= {"owed", "optional", "scene", "agenda", "constraints"}
    assert ft["constraints"]["eligibility_is_not_instruction"] is True
    ev = await async_client.post("/v1/cortex/attention-state/evaluate", json=body)
    assert ev.status_code == 200 and ev.json()["evaluation"]["effects_rolled_back"] is True


@pytest.mark.asyncio
async def test_removed_endpoints_are_gone():
    # direct cutover: no compatibility endpoints
    from src.main import app
    paths = set(app.openapi()["paths"])
    for gone in ("/v1/cortex/handover", "/v1/cortex/handover/preview", "/v1/cortex/handover/evaluate",
                 "/v1/cortex/working-set", "/v1/cortex/session-working-set",
                 "/v1/cortex/session-working-set/refresh", "/v1/cortex/attention-packet",
                 "/v1/cortex/attention-packet/evaluate", "/v1/cortex/turn-working-set", "/v1/sessions/consolidate"):
        assert gone not in paths, gone
    for new in ("/v1/cortex/attention-state", "/v1/cortex/world-model",
                "/v1/cortex/projection/today", "/v1/cortex/knowledge-coverage", "/v1/cortex/matters/list"):
        assert new in paths, new


def test_retired_modules_are_deleted():
    import importlib
    for mod in ("handover_service", "state_views", "candidate_moves", "session_workingset",
                "working_set_service", "cortex_packet_service", "turn_selection"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(f"src.services.{mod}")
