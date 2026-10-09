"""HTTP surface of the WorldModel / projections / coverage / Matter / working set."""
import pytest

from tests.cortex_fixtures import NOW, USER, WS, build_longitudinal_world

BASE = {"workspace_id": WS, "peer_id": USER, "now": NOW.isoformat(), "timezone": "Europe/London"}


async def post(client, path, **extra):
    return await client.post(f"/v1/cortex{path}", json={**BASE, **extra})


@pytest.mark.asyncio
async def test_world_model_endpoint_versions_and_invalidates(async_client):
    await build_longitudinal_world()
    r = await post(async_client, "/world-model")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["meta"]["freshness"] == "compiled" and body["meta"]["authoritative"] is False
    again = (await post(async_client, "/world-model")).json()
    assert again["meta"]["freshness"] == "fresh"
    inv = await async_client.post("/v1/cortex/world-model/invalidate",
                                  json={"workspace_id": WS, "peer_id": USER, "sections": ["forward", "bogus"]})
    assert inv.json()["invalidated"] == ["forward"]
    forced = (await post(async_client, "/world-model", force=True)).json()
    assert forced["meta"]["version"] == 2 and forced["meta"]["freshness"] == "compiled"


@pytest.mark.asyncio
async def test_every_projection_endpoint_answers(async_client):
    ids = await build_longitudinal_world()
    ok = {
        "/projection/person": {"entity_id": str(ids["ashley"])},
        "/projection/today": {}, "/projection/week": {}, "/projection/unresolved": {},
        "/projection/recent-changes": {"days": 14}, "/projection/knowledge-gaps": {}, "/projection/depth": {},
        "/projection/period": {"start": "2026-09-25T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
    }
    for path, extra in ok.items():
        r = await post(async_client, path, **extra)
        assert r.status_code == 200, (path, r.text)
    person = (await post(async_client, "/projection/person")).json()        # no entity -> user overview
    assert person["subject"] == "user"
    listed = (await post(async_client, "/matters/list", status="active")).json()["matters"]
    assert listed and all(m["status"] == "active" for m in listed)
    mid = listed[0]["id"]
    card = (await post(async_client, "/projection/matter", matter_id=mid)).json()
    assert card["found"] and card["id"] == mid
    tl = (await post(async_client, "/projection/timeline", subject_type="matter", subject_id=mid)).json()
    assert tl["subject"] == {"type": "matter", "id": mid}
    why = await async_client.post("/v1/cortex/projection/why",
                                  json={"object_type": "model_entry", "object_id": str(ids["reported"])})
    assert why.json()["formation"] == "reported"


@pytest.mark.asyncio
async def test_input_validation_and_not_found(async_client):
    await build_longitudinal_world()
    assert (await post(async_client, "/projection/matter", matter_id="nope")).status_code == 422
    assert (await post(async_client, "/projection/timeline", subject_type="topic", subject_id="x")).status_code == 422
    assert (await post(async_client, "/projection/period", start="2026-10-02T00:00:00Z",
                       end="2026-10-01T00:00:00Z")).status_code == 422
    assert (await post(async_client, "/knowledge-coverage", statuses=["bogus"])).status_code == 422
    assert (await post(async_client, "/knowledge-coverage/gap", subject_key="Bad Key")).status_code == 422
    miss = await async_client.post("/v1/cortex/matters/merge",
                                   json={"keep_id": "00000000-0000-0000-0000-000000000001",
                                         "drop_id": "00000000-0000-0000-0000-000000000002"})
    assert miss.status_code == 404


@pytest.mark.asyncio
async def test_knowledge_coverage_and_gap_registration(async_client):
    await build_longitudinal_world()
    r = await post(async_client, "/knowledge-coverage/gap", subject_key="routines/weekday_morning",
                   why_useful="what a normal weekday morning looks like")
    assert r.status_code == 200 and r.json()["status"] == "unknown" and "value" not in r.json()
    cov = (await post(async_client, "/knowledge-coverage", prefix="routines")).json()
    keys = {c["subject_key"]: c for c in cov["coverage"]}
    assert keys["routines/weekday_morning"]["source"] == "registered"
    assert keys["routines/walk_morning/timing"]["status"] == "unknown"
    assert keys["routines/walk_morning"]["status"] == "known"
    only_unknown = (await post(async_client, "/knowledge-coverage", statuses=["unknown"])).json()["coverage"]
    assert only_unknown and {c["status"] for c in only_unknown} == {"unknown"}


@pytest.mark.asyncio
async def test_matter_merge_and_sync_endpoints(async_client):
    await build_longitudinal_world()
    from tests.cortex_fixtures import loop, save, ago
    await save(loop("Fresh unreconciled thread about the boiler", message="l-boil", created=ago(0, 1)))
    first = (await post(async_client, "/matters/sync")).json()
    assert first["created"] == 1
    second = (await post(async_client, "/matters/sync")).json()
    assert second["linked"] == 0 and second["created"] == 0      # idempotent
    listed = (await post(async_client, "/matters/list")).json()["matters"]
    keep, drop = listed[0]["id"], listed[1]["id"]
    merged = await async_client.post("/v1/cortex/matters/merge", json={"keep_id": keep, "drop_id": drop})
    assert merged.status_code == 200 and merged.json() == {"kept": keep, "merged": drop}
    after = {m["id"] for m in (await post(async_client, "/matters/list")).json()["matters"]}
    assert drop not in after and keep in after


@pytest.mark.asyncio
async def test_product_weights_are_policy_over_generic_kinds_only(async_client):
    await build_longitudinal_world()
    neutral = (await post(async_client, "/matters/list")).json()["matters"]
    weighted = (await post(async_client, "/matters/list", product="health")).json()["matters"]
    assert {m["id"] for m in neutral} == {m["id"] for m in weighted}          # same truth
    assert {m["kind"] for m in neutral} == {m["kind"] for m in weighted}




@pytest.mark.asyncio
async def test_a_past_world_version_can_be_read_back_exactly(async_client):
    """The replay bundle names a turn's world by (owner, version); the superseded snapshot must come back as it was, and a version that never existed is a 404."""
    await build_longitudinal_world()
    v1 = (await post(async_client, "/world-model")).json()
    await async_client.post("/v1/cortex/world-model/invalidate", json={"workspace_id": WS, "peer_id": USER, "sections": ["forward"]})
    v2 = (await post(async_client, "/world-model", force=True)).json()
    assert v1["meta"]["version"] == 1 and v2["meta"]["version"] == 2
    old = await async_client.post("/v1/cortex/world-model/at", json={"workspace_id": WS, "peer_id": USER, "version": 1})
    assert old.status_code == 200, old.text
    assert old.json()["snapshot"]["meta"]["version"] == 1 and old.json()["superseded_by_id"]
    assert (await async_client.post("/v1/cortex/world-model/at", json={"workspace_id": WS, "peer_id": USER, "version": 99})).status_code == 404
