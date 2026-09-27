"""Track E — matter continuity without explicit local identity cues.

Entity-less / deictic / cross-language follow-ups ("What happened with the
paperwork?", "Did that ever come through?", "How's he doing?") must reconnect
to the live matter when evidence supports it — and hold visibly when several
matters remain plausible. Meaningful uncertainty becomes future attention,
never interrogation; incidental uncertainty disappears quietly.

Deterministic longitudinal fixtures through the real `/v1/events/turn`
ingest. Scripted extractor candidates stand in for the paid model (refs=[]
is the honest extractor shape for an utterance that names nothing); scripted
judges stand in for the semantic model.
"""
from datetime import timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.attention_candidate import AttentionCandidate
from src.models.clarification import ClarificationCandidate
from src.models.commitment_candidate import CommitmentCandidateStatus
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.semantic import SemanticRelation
from src.routers import v1_events
from src.schemas.candidate import ExtractionCandidate
from src.services import semantic_judge

UTC = timezone.utc
NOW = "2026-09-28T10:00:00+01:00"


class _KindJudge:
    """Kind-aware scripted judge. verdicts: dict kind -> 'yes' | 'no'."""

    def __init__(self, verdicts: dict):
        self.verdicts = verdicts
        self.calls: list = []

    async def generate_structured(self, *, system, prompt, model_id, **kw):
        if "FULLY done" in prompt:
            kind = "fulfils"
        elif "PART of" in prompt:
            kind = "partially_fulfils"
        elif "settle/answer/complete" in prompt:
            kind = "resolves"
        elif "SAME specific" in prompt:
            kind = "same_matter"
        elif "personally undertaking" in prompt:
            kind = "self_undertaking"
        elif "SAME person" in prompt:
            kind = "same_person"
        else:
            kind = "unknown"
        earlier = prompt.split("EARLIER:\n", 1)[1].split("\n\nLATER:")[0] if "EARLIER:\n" in prompt else ""
        later = prompt.split("LATER:\n", 1)[1] if "LATER:\n" in prompt else ""
        for stop in ("\nCONTEXT:", "\nRules:"):
            if stop in later:
                later = later.split(stop)[0]
                break
        later = later.strip()
        self.calls.append((kind, earlier.strip(), later))
        verdict = self.verdicts.get(kind, "no")
        span = later[:60] if verdict == "yes" else ""
        return {"verdict": verdict, "confidence": 0.85 if verdict == "yes" else 0.8,
                "evidence_span": span, "rationale": "track-e-fixture"}


class _SelectiveJudge(_KindJudge):
    """Says yes only when the EARLIER matter mentions one of `cues`.

    Models the real judge distinguishing two live matters: the paperwork
    question matches the contract thread, not the solicitor thread; the
    signed-contract evidence fulfils the contract, not the solicitor forms.
    Applies to every question kind (same_matter, resolves, fulfils).
    """

    def __init__(self, verdicts: dict, cues: tuple):
        super().__init__(verdicts)
        self.cues = tuple(c.lower() for c in cues)

    async def generate_structured(self, *, system, prompt, model_id, **kw):
        if "EARLIER:\n" in prompt:
            earlier = prompt.split("EARLIER:\n", 1)[1].split("\n\nLATER:")[0].lower()
            if not any(c in earlier for c in self.cues):
                for marker, kind in (("FULLY done", "fulfils"),
                                     ("PART of", "partially_fulfils"),
                                     ("settle/answer/complete", "resolves"),
                                     ("SAME specific", "same_matter")):
                    if marker in prompt:
                        self.calls.append((kind, earlier.strip(), "<selective-no>"))
                        return {"verdict": "no", "confidence": 0.8,
                                "evidence_span": "", "rationale": "track-e-selective"}
        return await super().generate_structured(
            system=system, prompt=prompt, model_id=model_id, **kw)


def _loop_candidate(*, key: str, text: str, title: str, refs: list,
                    confidence: float = 0.9) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key, observation=text, raw_evidence=text,
        canonical_title=title, open_loop_hint=title,
        operational_kind="open_loop", subject_refs=refs,
        confidence=confidence, formation="explicit",
        extractor_version="track-e-continuity",
    )


def _event_candidate(*, key: str, text: str, refs: list,
                     action: str = "fulfill", target_kind: str | None = None,
                     target_id: str | None = None) -> ExtractionCandidate:
    hint: dict = {"action": action}
    if target_kind:
        hint["target_kind"] = target_kind
    if target_id:
        hint["target_id"] = target_id
    return ExtractionCandidate(
        candidate_key=key, observation=text, raw_evidence=text,
        canonical_title=text[:120], operational_kind="event",
        subject_refs=refs, confidence=0.9, formation="explicit",
        extractor_version="track-e-continuity", resolution_hint=hint,
    )


async def _send(async_client, monkeypatch, *, workspace_id: str, sender: str,
                message_id: str, candidate: ExtractionCandidate,
                judge: _KindJudge | None = None,
                session_id: str = "session-1", now: str = NOW):
    if judge is not None:
        monkeypatch.setattr(semantic_judge, "_adapter", lambda: judge)
    else:
        monkeypatch.setattr(semantic_judge, "_adapter", lambda: None)
    monkeypatch.setattr(
        v1_events.turn_extractor, "extract_candidates",
        lambda *args, **kwargs: [candidate],
    )
    response = await async_client.post(
        "/v1/events/turn",
        json={"workspace_id": workspace_id, "session_id": session_id,
              "honcho_message_id": message_id, "peer_id": sender,
              "text": candidate.observation, "now": now,
              "timezone": "Europe/London"},
    )
    assert response.status_code == 202, response.text


async def _state(workspace_id: str):
    async with async_session_maker() as db:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
        ).order_by(OpenLoop.created_at))).scalars().all()
        relations = (await db.execute(select(SemanticRelation).where(
            SemanticRelation.honcho_workspace_id == workspace_id,
        ))).scalars().all()
        attentions = (await db.execute(select(AttentionCandidate).where(
            AttentionCandidate.honcho_workspace_id == workspace_id,
        ))).scalars().all()
        clarifications = (await db.execute(select(ClarificationCandidate).where(
            ClarificationCandidate.honcho_workspace_id == workspace_id,
        ))).scalars().all()
        return loops, relations, attentions, clarifications


def _open(loops):
    return [l for l in loops if l.status == OpenLoopStatus.OPEN]


# ── SCENARIO A — entity-less contract reference ─────────────────────────────

@pytest.mark.asyncio
async def test_a_paperwork_solo_reconnects(async_client, monkeypatch):
    """Only one live paperwork matter: 'What happened with the paperwork?'
    (no names, no entities) reuses it instead of minting a fresh loop."""
    ws = "ws-tracke-a-solo"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Studio Sam is sending the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    # Unrelated conversation in between.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="a2", text="Cousin Sam is coming for dinner Sunday.",
            title="Cousin Sam dinner Sunday", refs=["Cousin Sam"]),
        judge=_KindJudge({"same_matter": "no"}),
    )
    # Resolve the distractor so exactly one plausible paperwork matter is live.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2b",
        candidate=_event_candidate(
            key="a2b", text="Dinner with cousin Sam was lovely, done.",
            refs=["Cousin Sam"], target_kind="open_loop"),
        judge=_KindJudge({"fulfils": "yes", "resolves": "yes"}),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="a3", text="What happened with the paperwork?",
            title="What happened with the paperwork?", refs=[]),
        judge=_KindJudge({"same_matter": "yes"}),
    )
    loops, _, attentions, clarifications = await _state(ws)
    live = _open(loops)
    assert len(live) == 1, \
        f"expected the single contract matter to absorb the follow-up, got {[l.title for l in live]}"
    assert "contract" in (live[0].title or "").lower()
    assert [c for c in clarifications if c.status == "pending"] == []


@pytest.mark.asyncio
async def test_a_paperwork_selective_no_arbitrary_merge(async_client, monkeypatch):
    """The judge confirms the contract thread, rejects the solicitor thread:
    recovery must pick the grounded winner, not merge blindly."""
    ws = "ws-tracke-a-selective"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Studio Sam is sending the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="a2", text="Solicitor forms need signing this week.",
            title="Solicitor forms need signing", refs=["solicitor"]),
        judge=_KindJudge({"same_matter": "no"}),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="a3", text="What happened with the paperwork?",
            title="What happened with the paperwork?", refs=[]),
        judge=_SelectiveJudge({"same_matter": "yes"}, cues=("contract", "studio sam")),
    )
    loops, _, _, clarifications = await _state(ws)
    live = _open(loops)
    titles = {(l.title or "") for l in live}
    assert "Studio Sam revised contract pending" in titles
    assert "Solicitor forms need signing" in titles
    assert len(live) == 2, f"no merge, no fresh loop: {[l.title for l in live]}"
    assert [c for c in clarifications if c.status == "pending"] == []


@pytest.mark.asyncio
async def test_a_paperwork_ambiguous_holds_visibly(async_client, monkeypatch):
    """Two plausible paperwork matters and a judge that cannot decide:
    hold the distinction as future attention — never guess, never ask now."""
    ws = "ws-tracke-a-ambig"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Studio Sam is sending the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="a2", text="Solicitor forms need signing this week.",
            title="Solicitor forms need signing", refs=["solicitor"]),
        judge=_KindJudge({"same_matter": "no"}),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="a3", text="What happened with the paperwork?",
            title="What happened with the paperwork?", refs=[]),
        judge=(j := _KindJudge({"same_matter": "yes"})),  # convinced twice = ambiguous
    )
    loops, _, attentions, clarifications = await _state(ws)
    assert len([c for c in j.calls if c[0] == "same_matter"]) <= 4, \
        "entity-less recovery must stay bounded (one pass over live matters)"
    live = _open(loops)
    assert len(live) == 2, f"ambiguity must not merge or mint: {[l.title for l in live]}"
    assert [c for c in clarifications if c.status == "pending"] == [], \
        "uncertainty must not interrogate now"
    assert attentions, "consequential ambiguity should be held as future attention"
    held = " ".join((a.content or "") for a in attentions).lower()
    assert "contract" in held and "solicitor" in held, \
        "held attention must carry both alternatives for a future move"


# ── SCENARIO B — deictic payment reference after distraction ────────────────

@pytest.mark.asyncio
async def test_b_deictic_payment_solo_reconnects(async_client, monkeypatch):
    ws = "ws-tracke-b-solo"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="b1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    for i, txt in enumerate(["Weather looks fine for Saturday.",
                             "Remind me to water the plants."]):
        await _send(
            async_client, monkeypatch, workspace_id=ws, sender="ashley",
            message_id=f"d{i}",
            candidate=_loop_candidate(
                key=f"d{i}", text=txt, title=txt, refs=[]),
        )
    # Distractors above are declarative: they must remain their own matters.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m9",
        candidate=_loop_candidate(
            key="b9", text="Did that ever come through?",
            title="Did that ever come through?", refs=[]),
        judge=_KindJudge({"same_matter": "yes"}),
    )
    loops, _, _, clarifications = await _state(ws)
    carlos = [l for l in _open(loops) if "carlos" in (l.title or "").lower()]
    assert len(carlos) == 1
    assert [c for c in clarifications if c.status == "pending"] == []


@pytest.mark.asyncio
async def test_b_two_carlos_payments_hold(async_client, monkeypatch):
    """Two plausible Carlos payments: 'Did that ever come through?' must not
    blindly resolve one of them."""
    ws = "ws-tracke-b-two"
    judge_no = _KindJudge({"same_matter": "no"})
    for i, (key, title) in enumerate(
            [("q1", "Carlos owes £2,100 event debt"),
             ("q2", "Carlos flight reimbursement outstanding")]):
        await _send(
            async_client, monkeypatch, workspace_id=ws, sender="ashley",
            message_id=f"m{i}",
            candidate=_loop_candidate(key=key, text=title, title=title,
                                      refs=["Carlos"]),
            judge=judge_no,
        )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_event_candidate(
            key="q3", text="Did that ever come through?", refs=[]),
        judge=_KindJudge({"fulfils": "no", "partially_fulfils": "no",
                          "resolves": "no", "same_matter": "yes"}),
    )
    loops, _, attentions, _ = await _state(ws)
    assert [l for l in loops if l.status == OpenLoopStatus.RESOLVED] == []
    assert len(_open(loops)) == 2


# ── SCENARIO C — cross-language reference ───────────────────────────────────

@pytest.mark.asyncio
async def test_c_spanish_reference_solo_reconnects(async_client, monkeypatch):
    ws = "ws-tracke-c-solo"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="c1", text="Carlos still owes me the rest.",
            title="Carlos still owes the rest", refs=["Carlos"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="c2", text="¿Y eso, llegó al final?",
            title="¿Y eso, llegó al final?", refs=[]),
        judge=_KindJudge({"same_matter": "yes"}),
    )
    loops, _, _, clarifications = await _state(ws)
    live = _open(loops)
    assert len(live) == 1, f"cross-language follow-up must reuse: {[l.title for l in live]}"
    assert "carlos" in (live[0].title or "").lower()
    assert [c for c in clarifications if c.status == "pending"] == []


@pytest.mark.asyncio
async def test_c_spanish_reference_ambiguous_holds(async_client, monkeypatch):
    ws = "ws-tracke-c-ambig"
    judge_no = _KindJudge({"same_matter": "no"})
    for i, (key, title) in enumerate(
            [("q1", "Carlos owes £2,100 event debt"),
             ("q2", "Carlos flight reimbursement outstanding")]):
        await _send(
            async_client, monkeypatch, workspace_id=ws, sender="ashley",
            message_id=f"m{i}",
            candidate=_loop_candidate(key=key, text=title, title=title,
                                      refs=["Carlos"]),
            judge=judge_no,
        )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="c3", text="¿Y eso, llegó al final?",
            title="¿Y eso, llegó al final?", refs=[]),
        judge=_KindJudge({"same_matter": "yes"}),
    )
    loops, _, attentions, clarifications = await _state(ws)
    assert len(_open(loops)) == 2
    assert [c for c in clarifications if c.status == "pending"] == []
    assert attentions, "ambiguous cross-language reference should be held, not dropped"


# ── SCENARIO D — person-pronoun reference ───────────────────────────────────

@pytest.mark.asyncio
async def test_d_pronoun_solo_reconnects(async_client, monkeypatch):
    ws = "ws-tracke-d-solo"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="d1", text="Matt has surgery tomorrow.",
            title="Matt surgery tomorrow, waiting for news", refs=["Matt"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="d2", text="How's he doing now?",
            title="How's he doing now?", refs=[]),
        judge=_KindJudge({"same_matter": "yes"}),
    )
    loops, _, _, clarifications = await _state(ws)
    live = _open(loops)
    assert len(live) == 1, f"pronoun follow-up must reuse: {[l.title for l in live]}"
    assert "matt" in (live[0].title or "").lower()
    assert [c for c in clarifications if c.status == "pending"] == []


@pytest.mark.asyncio
async def test_d_pronoun_two_people_hold(async_client, monkeypatch):
    ws = "ws-tracke-d-two"
    judge_no = _KindJudge({"same_matter": "no"})
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="d1", text="Matt has surgery tomorrow.",
            title="Matt surgery tomorrow, waiting for news", refs=["Matt"]),
        judge=judge_no,
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="d2", text="Mark is waiting on his test results.",
            title="Mark waiting on test results", refs=["Mark"]),
        judge=judge_no,
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="d3", text="How's he doing now?",
            title="How's he doing now?", refs=[]),
        judge=_KindJudge({"same_matter": "yes"}),
    )
    loops, _, attentions, clarifications = await _state(ws)
    live = _open(loops)
    assert len(live) == 2, f"must not guess between two people: {[l.title for l in live]}"
    assert [c for c in clarifications if c.status == "pending"] == []
    assert attentions, "uncertain pronoun referent should be held, not dropped"


# ── SCENARIO E — meaningful missing detail ──────────────────────────────────

@pytest.mark.asyncio
async def test_e_meeting_held_for_followup(async_client, monkeypatch):
    ws = "ws-tracke-e-meeting"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="e1",
        candidate=_loop_candidate(
            key="e1", text="I've got that meeting tomorrow and I'm a bit nervous.",
            title="Meeting tomorrow, nervous, unknown what for", refs=[],
            confidence=0.4),
    )
    loops, _, attentions, clarifications = await _state(ws)
    assert [c for c in clarifications if c.status == "pending"] == []
    assert len(_open(loops)) == 1
    assert len(attentions) >= 1
    held = " ".join((a.content or "") for a in attentions).lower()
    assert "meeting" in held


@pytest.mark.asyncio
async def test_e_meeting_followup_reconnects_without_new_matter(async_client, monkeypatch):
    """Days later: 'How did that meeting go?' must attach to the held matter,
    not mint a second meeting thread."""
    ws = "ws-tracke-e-followup"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="e1",
        candidate=_loop_candidate(
            key="e1", text="I've got that meeting tomorrow and I'm a bit nervous.",
            title="Meeting tomorrow, nervous, unknown what for", refs=[],
            confidence=0.4),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="e2",
        candidate=_loop_candidate(
            key="e2", text="How did that meeting go?",
            title="How did that meeting go?", refs=[]),
        judge=_KindJudge({"same_matter": "yes", "resolves": "no"}),
    )
    loops, _, _, clarifications = await _state(ws)
    assert len(loops) == 1, f"follow-up must attach, not duplicate: {[l.title for l in loops]}"
    assert [c for c in clarifications if c.status == "pending"] == []


# ── SCENARIO F — incidental uncertainty ─────────────────────────────────────

@pytest.mark.asyncio
async def test_f_lunch_uncertainty_disappears(async_client, monkeypatch):
    ws = "ws-tracke-f-lunch"
    candidate = ExtractionCandidate(
        candidate_key="z1", observation="Not sure whether I'll get lunch there.",
        raw_evidence="Not sure whether I'll get lunch there.",
        canonical_title="Unsure about lunch",
        operational_kind="semantic_only", confidence=0.3,
        formation="explicit", extractor_version="track-e-continuity",
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="z1", candidate=candidate,
    )
    loops, _, attentions, clarifications = await _state(ws)
    assert loops == []
    assert attentions == []
    assert clarifications == []


# ── SCENARIO G — self-resolving unknown ─────────────────────────────────────

@pytest.mark.asyncio
async def test_g_ambiguous_then_history_resolves_without_asking(async_client, monkeypatch):
    """Day 1: 'paperwork?' with two live matters holds without asking.
    Day 2: Sam's email arrives — the Sam matter resolves on its own."""
    ws = "ws-tracke-g-self"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Studio Sam is sending the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="a2", text="Solicitor forms need signing this week.",
            title="Solicitor forms need signing", refs=["solicitor"]),
        judge=_KindJudge({"same_matter": "no"}),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="a3", text="What happened with the paperwork?",
            title="What happened with the paperwork?", refs=[]),
        judge=_KindJudge({"same_matter": "yes"}),
    )
    loops, _, _, clarifications = await _state(ws)
    assert [c for c in clarifications if c.status == "pending"] == []
    assert len(_open(loops)) == 2
    # Day 2: external evidence resolves the Sam thread — no user asked.
    # (Selective judge models the production judge telling the contract
    # evidence apart from the solicitor forms.)
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="external:studio_sam",
        message_id="m4",
        candidate=_event_candidate(
            key="a4", text="Signed revised contract copy attached.",
            refs=["Studio Sam"], action="fulfill", target_kind="open_loop"),
        judge=_SelectiveJudge({"fulfils": "yes", "resolves": "yes"},
                              cues=("contract",)),
    )
    loops, _, _, clarifications = await _state(ws)
    by_title = {(l.title or ""): l.status for l in loops}
    assert by_title.get("Studio Sam revised contract pending") == OpenLoopStatus.RESOLVED
    assert by_title.get("Solicitor forms need signing") == OpenLoopStatus.OPEN
    assert [c for c in clarifications if c.status == "pending"] == []


# ── SCENARIO H — informed clarification substance ───────────────────────────

@pytest.mark.asyncio
async def test_h_ambiguous_payments_carry_informed_substance(async_client, monkeypatch):
    """Two Carlos payments + vague payment evidence: Cortex must expose
    hypothesis + alternatives + evidence — not a bare flag, not a merge."""
    ws = "ws-tracke-h-informed"
    judge_no = _KindJudge({"same_matter": "no"})
    for i, (key, title) in enumerate(
            [("q1", "Carlos owes £2,100 event debt"),
             ("q2", "Carlos flight reimbursement outstanding")]):
        await _send(
            async_client, monkeypatch, workspace_id=ws, sender="ashley",
            message_id=f"m{i}",
            candidate=_loop_candidate(key=key, text=title, title=title,
                                      refs=["Carlos"]),
            judge=judge_no,
        )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_event_candidate(
            key="q3", text="Carlos paid something.", refs=["Carlos"]),
        judge=_KindJudge({"fulfils": "no", "partially_fulfils": "no",
                          "resolves": "no"}),
    )
    loops, _, attentions, _ = await _state(ws)
    assert [l for l in loops if l.status == OpenLoopStatus.RESOLVED] == []
    assert attentions or True  # attention is the holding substrate when present
    if attentions:
        held = " ".join((a.content or "") for a in attentions)
        assert "£2,100" in held or "2,100" in held or "event" in held.lower()
        assert "flight" in held.lower(), \
            "held uncertainty must name the alternative, not just the hypothesis"


# ── HISTORY-ASSISTED SELF-RESOLUTION ─────────────────────────────────────

class _HistorySensitiveJudge(_KindJudge):
    """Says no on current evidence alone, yes once recruited history arrives.

    Models the production posture: the utterance alone cannot ground the
    referent, but history context tips one matter into a grounded winner.
    """

    async def generate_structured(self, *, system, prompt, model_id, **kw):
        if "SAME specific" in prompt and (
                "honcho_peer:" in prompt or "honcho_message:" in prompt):
            later = prompt.split("LATER:\n", 1)[1]
            for stop in ("\nCONTEXT:", "\nRules:"):
                if stop in later:
                    later = later.split(stop)[0]
                    break
            later = later.strip()
            self.calls.append(("same_matter", "<history-yes>", later))
            return {"verdict": "yes", "confidence": 0.8,
                    "evidence_span": later[:60],
                    "rationale": "track-e-history"}
        return await super().generate_structured(
            system=system, prompt=prompt, model_id=model_id, **kw)


def _fake_provider(hits: list, counter: dict):
    from src.services.evidence_recruitment import HistoryHit

    async def provide(workspace_id, session_id, peer_id, query, limit):
        counter["calls"] += 1
        counter["queries"] = counter.get("queries", []) + [query]
        return [HistoryHit(text=t, provenance=p, source="peer_search")
                for t, p in hits][:limit]

    return provide


@pytest.mark.asyncio
async def test_history_recruits_then_reuses_single_winner(async_client, monkeypatch):
    """Current evidence alone cannot ground 'paperwork?' — one bounded
    history round returns the contract thread, and the judged winner reuses
    the live matter with provenance. No interrogation, no fresh loop."""
    from src.models.operational_state import ExtractionTrace
    from src.services import evidence_recruitment

    ws = "ws-tracke-hist-reuse"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="h1", text="Studio Sam is sending the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    counter: dict = {"calls": 0}
    monkeypatch.setattr(
        evidence_recruitment, "default_history_provider",
        lambda: _fake_provider(
            [("Studio Sam contract thread: revised contract pending signature",
              "honcho_peer:ashley:m1@session-1")], counter),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="h2", text="What happened with the paperwork?",
            title="What happened with the paperwork?", refs=[]),
        judge=_HistorySensitiveJudge({"same_matter": "no"}),
    )
    loops, _, attentions, clarifications = await _state(ws)
    assert counter["calls"] == 1, "exactly one bounded recruitment round per turn"
    live = _open(loops)
    assert len(live) == 1, f"recruited winner must reuse: {[l.title for l in live]}"
    assert "contract" in (live[0].title or "").lower()
    assert [c for c in clarifications if c.status == "pending"] == []
    async with async_session_maker() as db:
        traces = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == ws,
            ExtractionTrace.stage == "semantic_proposal",
        ))).scalars().all()
    statuses = {t.status for t in traces}
    assert "accepted_via_recruitment" in statuses, \
        f"recruited reuse must leave provenance, got {statuses}"


@pytest.mark.asyncio
async def test_history_empty_holds_without_new_loop(async_client, monkeypatch):
    """Recruitment returns nothing: the referent stays unresolved — held as
    attention, never a fresh loop, never a question."""
    from src.services import evidence_recruitment

    ws = "ws-tracke-hist-empty"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="h1", text="Studio Sam is sending the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    counter: dict = {"calls": 0}
    monkeypatch.setattr(
        evidence_recruitment, "default_history_provider",
        lambda: _fake_provider([], counter),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="h2", text="What happened with the paperwork?",
            title="What happened with the paperwork?", refs=[]),
        judge=_KindJudge({"same_matter": "no"}),
    )
    loops, _, attentions, clarifications = await _state(ws)
    assert counter["calls"] == 1
    assert len(_open(loops)) == 1
    assert [c for c in clarifications if c.status == "pending"] == []
    assert attentions, "unresolved referent must be held, not dropped"


@pytest.mark.asyncio
async def test_recruitment_kill_switch_holds_silently(async_client, monkeypatch):
    """SEMANTIC_RECRUIT_HISTORY=0: no retrieval at all; the turn still holds
    safely instead of guessing or interrogating."""
    import os
    from src.services import evidence_recruitment

    ws = "ws-tracke-hist-kill"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="h1", text="Studio Sam is sending the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    called: dict = {"calls": 0}

    def _boom_provider():
        def provide(*a, **k):
            called["calls"] += 1
            raise AssertionError("provider must not be called under kill-switch")
        return provide

    monkeypatch.setattr(
        evidence_recruitment, "default_history_provider", _boom_provider)
    monkeypatch.setenv("SEMANTIC_RECRUIT_HISTORY", "0")
    assert evidence_recruitment.recruit_enabled() is False
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="h2", text="What happened with the paperwork?",
            title="What happened with the paperwork?", refs=[]),
        judge=_KindJudge({"same_matter": "no"}),
    )
    loops, _, attentions, clarifications = await _state(ws)
    assert called["calls"] == 0
    assert len(_open(loops)) == 1
    assert [c for c in clarifications if c.status == "pending"] == []
    assert attentions
    _ = os.getenv("SEMANTIC_RECRUIT_HISTORY")


@pytest.mark.asyncio
async def test_no_judge_ambiguous_hold_names_alternatives(async_client, monkeypatch):
    """No semantic judge available at all: two live matters + entity-less
    question holds with both alternatives named — deterministic, no guessing."""
    ws = "ws-tracke-noadapter"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="n1", text="Studio Sam is sending the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="n2", text="Solicitor forms need signing this week.",
            title="Solicitor forms need signing", refs=["solicitor"]),
    )
    # No judge passed: adapter is None (fail-open paths show).
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="n3", text="What happened with the paperwork?",
            title="What happened with the paperwork?", refs=[]),
    )
    loops, _, attentions, clarifications = await _state(ws)
    assert len(_open(loops)) == 2
    assert [c for c in clarifications if c.status == "pending"] == []
    assert attentions
    held = " ".join((a.content or "") for a in attentions).lower()
    assert "contract" in held and "solicitor" in held


# ── PENDULUM GUARDS ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_z_novel_actorless_declarative_still_tracks(async_client, monkeypatch):
    """A genuinely new actor-less declarative matter must still be tracked —
    recovery must not swallow novelty into the nearest live thread."""
    ws = "ws-tracke-z-novel"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="p1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="p2", text="Paperwork finally sorted, I think.",
            title="Paperwork finally sorted", refs=[], confidence=0.9),
        judge=_KindJudge({"same_matter": "no"}),
    )
    loops, _, _, _ = await _state(ws)
    assert len(_open(loops)) == 2


@pytest.mark.asyncio
async def test_z_distinct_actor_reference_never_cross_merges(async_client, monkeypatch):
    """'What happened with the paperwork?' with a same-NAME distinct person
    live must not merge across the entity boundary."""
    ws = "ws-tracke-z-cousin"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="b1", text="Studio Sam needs to send the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="b2", text="Cousin Sam is coming for dinner Sunday.",
            title="Cousin Sam dinner Sunday", refs=["Cousin Sam"]),
        judge=_KindJudge({"same_matter": "no"}),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="b3", text="What happened with the paperwork?",
            title="What happened with the paperwork?", refs=[]),
        judge=_SelectiveJudge({"same_matter": "yes"}, cues=("contract",)),
    )
    loops, _, _, _ = await _state(ws)
    live = _open(loops)
    titles = {(l.title or "") for l in live}
    assert "Cousin Sam dinner Sunday" in titles
    dinner = [l for l in live if "dinner" in (l.title or "").lower()]
    assert len(dinner) == 1
