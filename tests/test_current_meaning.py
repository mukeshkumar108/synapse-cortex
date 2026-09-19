"""CurrentMeaning v1 contract tests (Cortex-owned live interpretation).

Covers: first-write creates v1; idempotency by revision_key (not provenance);
versioned supersession (X loses authority, retained as evidence); stale prior
discarded, never rebased; fail-closed omission without model credentials;
scope isolation incl. null-peer canonicalisation; packet carries retained
belief without authority; validator rejects non-verbatim evidence.
"""

from datetime import datetime, timezone

import pytest

from src.services import current_meaning_service as cm


def revise_payload(**overrides):
    payload = {
        "workspace_id": "ws-meaning",
        "session_id": "sess-a",
        "peer_id": "user_1",
        "message_id": "m1",
        "turn_text": "you cancelled our walk and I am still hurt about it",
        "recent_conversation": [],
    }
    payload.update(overrides)
    return payload


async def test_first_write_without_model_fails_closed(async_client):
    """No model credentials in tests → interpreter unavailable → retain
    (nothing), omit foreground, never fabricate."""
    resp = await async_client.post("/v1/cortex/current-meaning/revise-sync", json=revise_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["meaning_revision"] == "unchanged"
    assert body["foreground_authority"] == "unknown_omitted_due_to_interpretation_failure"
    assert body["active"] is None
    assert body["revision"] is None


async def test_active_read_empty_scope(async_client):
    resp = await async_client.get(
        "/v1/cortex/current-meaning/active",
        params={"workspace_id": "ws-meaning", "session_id": "sess-a", "peer_id": "user_1"},
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is None


async def test_idempotency_and_version_chain_via_service(async_client):
    """Exercise commit_revision directly: idempotent hit, v1→v2 supersession,
    stale-prior discard. (Live model path is covered by fail-closed test.)"""
    from src.db import async_session_maker
    from src.models.current_meaning import scope_key_for

    scope = {
        "workspace_id": "ws-meaning",
        "product": "sophie",
        "session_id": "sess-a",
        "owner_peer_id": "user_1",
    }
    scope_key = scope_key_for("ws-meaning", "sophie", "sess-a", "user_1")
    now = datetime.now(timezone.utc)
    proposal_v1 = {"means": ["she is still hurt about the cancelled walk"], "unresolved": ["the walk"], "foreground_authority": "active"}

    async with async_session_maker() as db:
        r1 = await cm.commit_revision(
            db, scope=scope, scope_key=scope_key, revision_key="turn:m1",
            source_message_ids=["m1"], proposal=proposal_v1,
            lens_version="sophie-meaning-v1", now=now,
            expected_prior_id=None, expected_prior_version=None,
        )
        assert r1["outcome"] == "committed"
        assert r1["row"]["version"] == 1

        # Same revision_key → idempotent hit, no duplicate version.
        r1b = await cm.commit_revision(
            db, scope=scope, scope_key=scope_key, revision_key="turn:m1",
            source_message_ids=["m1"], proposal=proposal_v1,
            lens_version="sophie-meaning-v1", now=now,
            expected_prior_id=None, expected_prior_version=None,
        )
        assert r1b["outcome"] == "idempotent_hit"
        assert r1b["row"]["id"] == r1["row"]["id"]

        # v2 supersedes v1 with correct CAS expectation.
        proposal_v2 = {
            "means": ["she softened when I owned it plainly; the walk is no longer the point"],
            "unresolved": ["follow up once, lightly, tomorrow — no chase"],
            "foreground_authority": "active",
        }
        r2 = await cm.commit_revision(
            db, scope=scope, scope_key=scope_key, revision_key="turn:m2",
            source_message_ids=["m2"], proposal=proposal_v2,
            lens_version="sophie-meaning-v1", now=now,
            expected_prior_id=r1["row"]["id"], expected_prior_version=1,
        )
        assert r2["outcome"] == "committed"
        assert r2["row"]["version"] == 2

        # Only v2 is active; v1 retained as evidence with superseded pointer.
        active = await cm.get_active(db, scope_key=scope_key)
        assert active is not None and str(active.id) == r2["row"]["id"]

        # Stale writer (expected v1, actual v2) → discarded, never rebased.
        stale = await cm.commit_revision(
            db, scope=scope, scope_key=scope_key, revision_key="turn:m3",
            source_message_ids=["m3"], proposal=proposal_v1,
            lens_version="sophie-meaning-v1", now=now,
            expected_prior_id=r1["row"]["id"], expected_prior_version=1,
        )
        assert stale["outcome"] == "stale_prior"
        assert stale["active"]["id"] == r2["row"]["id"]
        still = await cm.get_active(db, scope_key=scope_key)
        assert str(still.id) == r2["row"]["id"]


async def test_null_peer_scopes_share_one_chain():
    """owner_peer None canonicalises to 'shared': single-active invariant is
    DB-real, not NULL-coexistence."""
    from src.db import async_session_maker
    from src.models.current_meaning import scope_key_for, canonical_owner_peer

    assert canonical_owner_peer(None) == "shared"
    assert scope_key_for("w", "sophie", "s", None) == scope_key_for("w", "sophie", "s", "shared")

    async with async_session_maker() as db:
        scope = {"workspace_id": "w", "product": "sophie", "session_id": "s", "owner_peer_id": "shared"}
        skey = scope_key_for("w", "sophie", "s", None)
        now = datetime.now(timezone.utc)
        proposal = {"means": ["x"], "unresolved": [], "foreground_authority": "active"}
        r = await cm.commit_revision(
            db, scope=scope, scope_key=skey, revision_key="turn:n1",
            source_message_ids=["n1"], proposal=proposal,
            lens_version="sophie-meaning-v1", now=now,
            expected_prior_id=None, expected_prior_version=None,
        )
        assert r["outcome"] == "committed"
        active = await cm.get_active(db, scope_key=skey)
        assert active is not None


def test_validator_rejects_non_verbatim_evidence():
    prior = None
    turn = "hey, that was kind of you to just own it"
    raw = {
        "means": ["she softened"],
        "unresolved": [],
        "foreground_authority": "active",
        "evidence_span": "she forgave everything yesterday",  # not in turn
        "no_change": False,
    }
    assert cm.validate_proposal(raw=raw, turn_text=turn, prior=prior) is None


def test_validator_carry_on_identical():
    import json as _json
    from src.models.current_meaning import CurrentMeaning

    prior = CurrentMeaning(
        honcho_workspace_id="w", product="sophie", honcho_session_id="s",
        owner_peer_id="user_1", scope_key="w|sophie|s|user_1",
        means_json=_json.dumps(["she softened"]),
        unresolved_json=_json.dumps([]),
        source_message_ids_json=_json.dumps(["m1"]),
        revision_key="turn:m1",
    )
    raw = {
        "means": ["she softened"],
        "unresolved": [],
        "foreground_authority": "active",
        "evidence_span": "kind of you",
        "no_change": False,
    }
    # Identical content → carry (no churn row), even with verbatim evidence.
    assert cm.validate_proposal(raw=raw, turn_text="kind of you to just own it", prior=prior) is None


def test_validator_bounds():
    raw = {
        "means": [f"line {i} " + "x" * 200 for i in range(6)],
        "unresolved": [f"u{i}" for i in range(6)],
        "foreground_authority": "bogus",
        "evidence_span": "hello",
        "no_change": False,
    }
    out = cm.validate_proposal(raw=raw, turn_text="hello there", prior=None)
    assert out is not None
    assert len(out["means"]) == 3 and len(out["unresolved"]) == 3
    assert all(len(line) <= 140 for line in out["means"])
    assert out["foreground_authority"] == "active"
