"""One epistemic system (ModelEntry): formation classes, supersession rules,
status, provenance — and no silent hardening of interpretation into fact."""
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.epistemic import EpistemicAnnotation, EpistemicProvenance
from src.models.identity import ModelEntry
from src.services import epistemics as ep
from tests.cortex_fixtures import NOW, USER, WS, ago, build_longitudinal_world, naive, save


def test_formation_classes_map_every_stored_vocabulary_without_upgrading_unknowns():
    for provenance in EpistemicProvenance:
        assert ep.formation_class(provenance) in ep.FORMATION_CLASSES
    assert ep.formation_class("direct_statement") == "explicit"
    assert ep.formation_class("reported_statement") == "reported"
    assert ep.formation_class("attributed_belief") == "reported"
    assert ep.formation_class("external_source") == "source_linked"
    assert ep.formation_class("pattern") == "observed"
    assert ep.formation_class("hypothesis") == "hypothesis"
    assert ep.formation_class("something-new") == "inferred"   # never promoted to firm
    assert ep.formation_class(None) == "inferred"
    assert ep.is_firm("explicit") and ep.is_firm("reported") and not ep.is_firm("observed")


async def _write(**kw):
    base = dict(workspace_id=WS, session_id="lane-1", message_id=f"m-{uuid4().hex[:6]}",
                owner_peer_id=USER, model_kind="user", evidence_verbatim="ev", confidence=0.9)
    base.update(kw)
    async with async_session_maker() as db:
        return await ep.write_claim(db, **base)


@pytest.mark.asyncio
async def test_interpretation_cannot_supersede_what_the_user_actually_said():
    firm = await _write(claim="Kai does not drink coffee", formation="explicit")
    soft = await _write(claim="Kai drinks coffee most mornings", formation="inferred", confidence=0.5,
                        supersedes_id=firm.id)
    async with async_session_maker() as db:
        f, s = await db.get(ModelEntry, firm.id), await db.get(ModelEntry, soft.id)
    assert f.superseded_by_id is None                      # the explicit claim stands
    assert f.epistemic_status == s.epistemic_status == "conflicting"
    assert ep.derive_status(f, naive(NOW)) == "conflicting"


@pytest.mark.asyncio
async def test_firm_claim_can_supersede_an_inference_and_history_is_kept():
    guess = await _write(claim="Kai prefers mornings", formation="inferred", confidence=0.5)
    said = await _write(claim="Kai says evenings suit him better", formation="explicit", supersedes_id=guess.id)
    async with async_session_maker() as db:
        g = await db.get(ModelEntry, guess.id)
        exp_ = await ep.explain(db, "model_entry", guess.id)
    assert g.superseded_by_id == said.id and ep.derive_status(g, naive(NOW)) == "superseded"
    assert [c["id"] for c in exp_["superseded_by_chain"]] == [str(said.id)]


@pytest.mark.asyncio
async def test_system_perspective_is_actor_owned_never_testimony():
    e = await _write(claim="Sophie wonders whether Kai is overextended", formation="explicit",
                     holder_actor="system", claim_kind="decision")
    assert e.claim_kind == "perspective" and e.holder_actor == "system"
    assert ep.formation_class(e.formation) == "inferred"   # downgraded: the system's own thought


@pytest.mark.asyncio
async def test_write_is_idempotent_and_validates_claim_kind():
    a = await _write(claim="Kai walks most mornings", formation="observed", message_id="m-fixed",
                     claim_kind="pattern")
    b = await _write(claim="kai walks most mornings", formation="observed", message_id="m-fixed",
                     claim_kind="pattern")
    assert a.id == b.id
    with pytest.raises(ValueError):
        await _write(claim="x", formation="explicit", claim_kind="gospel")


def test_status_derivation_uncertain_stale_superseded():
    now = naive(NOW)

    class E:  # ModelEntry-shaped
        superseded_by_id = None
        epistemic_status = "current"
        confidence = 0.9
        formation = "explicit"
        effective_at = None
        updated_at = created_at = now

    e = E()
    assert ep.derive_status(e, now) == "current"
    e.confidence = 0.3
    assert ep.derive_status(e, now) == "uncertain"
    e.confidence = 0.9
    e.updated_at = e.created_at = now - timedelta(days=ep.STALE_AFTER_DAYS_SOFT + 5)
    assert ep.derive_status(e, now) == "current"           # firm claims outlive soft ones
    e.formation = "inferred"
    assert ep.derive_status(e, now) == "stale"
    e.superseded_by_id = uuid4()
    assert ep.derive_status(e, now) == "superseded"


@pytest.mark.asyncio
async def test_explain_answers_why_with_evidence_annotation_and_formation():
    ids = await build_longitudinal_world()
    await save(EpistemicAnnotation(
        honcho_workspace_id=WS, honcho_session_id="lane-1", honcho_message_id="l-ash",
        perspective_peer_id=USER, target_peer_id="ashley",
        provenance_type=EpistemicProvenance.REPORTED_STATEMENT,
        claim_summary="Kai says Ashley defended her actions", confidence=0.9))
    async with async_session_maker() as db:
        why = await ep.explain(db, "model_entry", ids["reported"], naive(NOW))
        loop_why = await ep.explain(db, "open_loop", ids["ash_loop"], naive(NOW))
    assert why["formation"] == "reported" and why["status"] == "current"
    assert why["evidence_refs"][:2] == ["l-ash", "l-ash2"] and why["confidence"] == 0.9
    assert why["claim"].startswith("Kai has repeatedly reported")     # NOT "Ashley is defensive"
    assert "defensive" not in why["claim"]
    assert loop_why["annotations"][0]["formation_class"] == "reported"
    assert loop_why["annotations"][0]["perspective_peer_id"] == USER
    missing = None
    async with async_session_maker() as db:
        missing = await ep.explain(db, "model_entry", uuid4())
    assert missing["found"] is False
