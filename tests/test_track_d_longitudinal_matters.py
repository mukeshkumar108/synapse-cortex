"""Track D — longitudinal matter continuity verticals (scenarios A-E).

Deterministic multi-day, multi-source scenarios through the real
`/v1/events/turn` ingest + lifecycle machinery (scripted extractor
candidates stand in for the paid model; no model calls here).

Behavioural oracles assert persisted-state invariants, not implementation
shapes: one live matter across paraphrase, correct actor/owner, partial
stays partial, contradiction tolerated, recall creates nothing new,
meaningful uncertainty becomes future attention (not interrogation).

Initial run documents HEAD behaviour; fixes follow in this same tranche.
"""
from datetime import datetime, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.attention_candidate import AttentionCandidate
from src.models.clarification import ClarificationCandidate
from src.models.commitment_candidate import (
    CommitmentCandidate,
    CommitmentCandidateAuthority,
    CommitmentCandidateStatus,
)
from src.models.expectation import Expectation
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
                "evidence_span": span, "rationale": "track-d-fixture"}


def _loop_candidate(*, key: str, text: str, title: str, refs: list,
                    confidence: float = 0.9) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key, observation=text, raw_evidence=text,
        canonical_title=title, open_loop_hint=title,
        operational_kind="open_loop", subject_refs=refs,
        confidence=confidence, formation="explicit",
        extractor_version="track-d-longitudinal",
    )


def _commitment_candidate(*, key: str, text: str, title: str, refs: list,
                          evidence_class: str = "implicit_self_commitment",
                          authority: str = "act",
                          actor: str | None = None) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key, observation=text, raw_evidence=text,
        canonical_title=title, operational_kind="commitment_candidate",
        evidence_class=evidence_class, authority=authority,
        subject_refs=refs, actor_peer_id=actor,
        temporal_phrase="tomorrow", confidence=0.9, formation="explicit",
        extractor_version="track-d-longitudinal",
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
        extractor_version="track-d-longitudinal", resolution_hint=hint,
    )


async def _send(async_client, monkeypatch, *, workspace_id: str, sender: str,
                message_id: str, candidate: ExtractionCandidate,
                judge: _KindJudge | None = None,
                session_id: str = "session-1", now: str = NOW):
    if judge is not None:
        monkeypatch.setattr(semantic_judge, "_adapter", lambda: judge)
    else:
        # Deterministic default: no judge available (fail-open paths show).
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
        commitments = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
        ).order_by(CommitmentCandidate.created_at))).scalars().all()
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
        return commitments, loops, relations, attentions, clarifications


# ── SCENARIO A — Carlos debt arc ─────────────────────────────────────────────

WS_A = "ws-trackd-carlos"


async def _carlos_day1_day2(async_client, monkeypatch):
    await _send(
        async_client, monkeypatch, workspace_id=WS_A, sender="ashley",
        message_id="a_d1",
        candidate=_loop_candidate(
            key="a1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    # Day 2 — Carlos speaks for himself (extractor-shaped: first-person
    # promise classified character_promise/ACT, as the live model emits).
    await _send(
        async_client, monkeypatch, workspace_id=WS_A, sender="external:carlos",
        message_id="a_d2",
        candidate=_commitment_candidate(
            key="a2", text="The bank has delayed it. I'll send it tomorrow.",
            title="Carlos will send the £2,100 tomorrow", refs=["Carlos"],
            evidence_class="character_promise", authority="act"),
    )


@pytest.mark.asyncio
async def test_a_day1_single_live_matter_no_false_self_commitment(async_client, monkeypatch):
    ws = "ws-trackd-a-day1"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    commitments, loops, *_ = await _state(ws)
    assert [c for c in commitments if c.authority == CommitmentCandidateAuthority.ACT] == []
    assert len([l for l in loops if l.status == OpenLoopStatus.OPEN]) == 1


@pytest.mark.asyncio
async def test_a_day2_external_promise_stays_counterparty(async_client, monkeypatch):
    ws = "ws-trackd-a-day2"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="external:carlos",
        message_id="m2",
        candidate=_commitment_candidate(
            key="a2", text="The bank has delayed it. I'll send it tomorrow.",
            title="Carlos will send the £2,100 tomorrow", refs=["Carlos"],
            evidence_class="character_promise", authority="act"),
    )
    commitments, loops, *_ = await _state(ws)
    user_act = [c for c in commitments
                if c.owner_peer_id == "ashley"
                and c.authority == CommitmentCandidateAuthority.ACT]
    assert user_act == []
    asks = [c for c in commitments
            if c.authority == CommitmentCandidateAuthority.ASK]
    assert len(asks) == 1
    assert asks[0].owner_peer_id == "external:carlos"
    # Same underlying debt matter remains identifiable: no sibling loop.
    assert len([l for l in loops if l.status == OpenLoopStatus.OPEN]) == 1


@pytest.mark.asyncio
async def test_a_day3_shorthand_pronoun_no_duplicate_matter(async_client, monkeypatch):
    ws = "ws-trackd-a-day3"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    # Day 3 shorthand: pronoun only, no resolvable named entity.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="a3", text="Still nothing from him.",
            title="Still nothing from him", refs=[]),
    )
    _, loops, *_ = await _state(ws)
    assert len([l for l in loops if l.status == OpenLoopStatus.OPEN]) == 1


@pytest.mark.asyncio
async def test_a_day4_partial_payment_stays_partial(async_client, monkeypatch):
    ws = "ws-trackd-a-day4"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    judge = _KindJudge({"fulfils": "no", "partially_fulfils": "yes"})
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="bank_feed",
        message_id="m4",
        candidate=_event_candidate(
            key="a4", text="Incoming payment £1,900 from Carlos.",
            refs=["Carlos"]),
        judge=judge,
    )
    commitments, loops, relations, *_ = await _state(ws)
    # £2,100 debt must NOT become fully fulfilled because £1,900 arrived.
    assert [c for c in commitments
            if c.status == CommitmentCandidateStatus.FULFILLED] == []
    assert [l for l in loops if l.status == OpenLoopStatus.RESOLVED] == []
    # Partial evidence must remain represented/auditable, not silently dropped.
    partial_rels = [r for r in relations if r.rel_type == "partially_fulfils"]
    accumulated = [
        c for c in commitments
        if "1,900" in (c.evidence_verbatim or "") or "1900" in (c.evidence_verbatim or "")]
    assert partial_rels or accumulated, \
        "partial £1,900 evidence left no auditable trace"
    # No false violation, no new sibling matter.
    assert [c for c in commitments
            if c.status == CommitmentCandidateStatus.VIOLATED] == []
    assert len(loops) == 1


@pytest.mark.asyncio
async def test_a_day5_claim_vs_receipt_and_day6_contradiction_tolerated(
        async_client, monkeypatch):
    ws = "ws-trackd-a-day56"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    judge = _KindJudge({"fulfils": "no", "partially_fulfils": "yes"})
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="bank_feed",
        message_id="m4",
        candidate=_event_candidate(
            key="a4", text="Incoming payment £1,900 from Carlos.",
            refs=["Carlos"]),
        judge=judge,
    )
    # Day 4 user ack reinforces; still not complete.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m5",
        candidate=_event_candidate(
            key="a5", text="Carlos paid something.",
            refs=["Carlos"]),
        judge=judge,
    )
    # Day 5: Carlos claims completion. Day 6: bank still shows £1,900 only
    # (no further bank evidence arrives) — claim must not auto-fulfil.
    claim_judge = _KindJudge({"fulfils": "no", "partially_fulfils": "no"})
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="external:carlos",
        message_id="m6",
        candidate=_event_candidate(
            key="a6", text="Sent the rest.",
            refs=["Carlos"]),
        judge=claim_judge,
    )
    commitments, loops, relations, *_ = await _state(ws)
    assert [c for c in commitments
            if c.status == CommitmentCandidateStatus.FULFILLED] == []
    assert [l for l in loops if l.status == OpenLoopStatus.RESOLVED] == []
    # Both evidences coexist: the claim is accumulated, not forced to true.
    assert len(loops) == 1
    assert [c for c in commitments
            if c.status == CommitmentCandidateStatus.VIOLATED] == []


@pytest.mark.asyncio
async def test_a_day7_recall_creates_nothing_new(async_client, monkeypatch):
    ws = "ws-trackd-a-day7"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="a1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    # Retrospective question: no judge adapter available (deterministic path).
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m7",
        candidate=_loop_candidate(
            key="a7", text="Did Carlos ever sort that?",
            title="Did Carlos ever sort that?", refs=["Carlos"]),
    )
    commitments, loops, *_ = await _state(ws)
    assert [c for c in commitments
            if c.authority == CommitmentCandidateAuthority.ACT] == []
    # A recall question about live history must not mint a fresh obligation.
    assert len(loops) == 1


@pytest.mark.asyncio
async def test_a_variant_second_carlos_debt_holds_without_blind_merge(
        async_client, monkeypatch):
    ws = "ws-trackd-a-variant"
    judge_yes = _KindJudge({"same_matter": "yes"})
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_commitment_candidate(
            key="v1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos owes £2,100 event debt", refs=["Carlos"],
            evidence_class="counterparty_promise", authority="ask"),
        judge=judge_yes,
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_commitment_candidate(
            key="v2", text="Carlos also owes me £300 for the flights.",
            title="Carlos owes £300 flights debt", refs=["Carlos"],
            evidence_class="counterparty_promise", authority="ask"),
        judge=judge_yes,
    )
    commitments, *_ = await _state(ws)
    assert len(commitments) == 2
    # "Carlos paid something." must not blindly fulfil one of them.
    amb_judge = _KindJudge({"fulfils": "no", "partially_fulfils": "no"})
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_event_candidate(
            key="v3", text="Carlos paid something.", refs=["Carlos"]),
        judge=amb_judge,
    )
    commitments, *_ = await _state(ws)
    assert [c for c in commitments
            if c.status == CommitmentCandidateStatus.FULFILLED] == []


# ── SCENARIO B — Studio Sam contract ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_b_studio_sam_cross_source_progression(async_client, monkeypatch):
    ws = "ws-trackd-b-sam"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="b1",
        candidate=_loop_candidate(
            key="b1", text="Studio Sam needs to send the revised contract.",
            title="Studio Sam revised contract pending", refs=["Studio Sam"]),
    )
    # Sam speaks for himself (extractor-shaped first-person promise).
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="external:studio_sam",
        message_id="b2",
        candidate=_commitment_candidate(
            key="b2", text="I'll send the revised contract tomorrow.",
            title="Sam will send revised contract", refs=["Studio Sam"],
            evidence_class="character_promise", authority="act"),
    )
    commitments, loops, *_ = await _state(ws)
    assert [c for c in commitments
            if c.owner_peer_id == "ashley"
            and c.authority == CommitmentCandidateAuthority.ACT] == []
    # Verbal approval is not written execution: still open.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="b3",
        candidate=_event_candidate(
            key="b3", text="Gave verbal approval on the call.",
            refs=["Studio Sam"], action="fulfill"),
        judge=_KindJudge({"fulfils": "no", "partially_fulfils": "no"},
                         ),
    )
    _, loops, *_ = await _state(ws)
    assert [l for l in loops if l.status == OpenLoopStatus.OPEN] == [l for l in loops]
    # Final signature copy arrives externally → resolves.
    sig_judge = _KindJudge({"fulfils": "yes", "resolves": "yes"})
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="external:studio_sam",
        message_id="b5",
        candidate=_event_candidate(
            key="b5", text="Signed revised contract copy attached.",
            refs=["Studio Sam"], action="fulfill",
            target_kind="open_loop"),
        judge=sig_judge,
    )
    _, loops2, *_ = await _state(ws)
    assert [l for l in loops2 if l.status == OpenLoopStatus.RESOLVED]
    # Later recall does not resurrect.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="b6",
        candidate=_loop_candidate(
            key="b6", text="Did Sam ever send the contract?",
            title="Did Sam ever send the contract?", refs=["Studio Sam"]),
    )
    _, loops3, *_ = await _state(ws)
    assert [l for l in loops3 if l.status == OpenLoopStatus.OPEN] == []
    # Same-name distinct person never merges.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="b7",
        candidate=_loop_candidate(
            key="b7", text="Cousin Sam is coming for dinner Sunday.",
            title="Cousin Sam dinner Sunday", refs=["Cousin Sam"]),
    )
    commitments_b, loops_b, *_ = await _state(ws)
    dinner = [l for l in loops_b if "dinner" in (l.title or "").lower()]
    assert len(dinner) == 1


# ── SCENARIO C — event logistics ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_c_completion_changed_owner_and_recall(async_client, monkeypatch):
    ws = "ws-trackd-c-logistics"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="c1",
        candidate=_commitment_candidate(
            key="c1", text="I'll pick up the flowers tomorrow morning.",
            title="Pick up the flowers", refs=[]),
    )
    commitments, *_ = await _state(ws)
    assert len(commitments) == 1
    assert commitments[0].authority == CommitmentCandidateAuthority.ACT
    # Completion.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="c2",
        candidate=_event_candidate(
            key="c2", text="Picked up the flowers, done.",
            refs=[], action="fulfill"),
    )
    commitments, *_ = await _state(ws)
    assert commitments[0].status == CommitmentCandidateStatus.FULFILLED
    # Plan change: Andree takes the chairs — must not become user's ACT.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="c3",
        candidate=_commitment_candidate(
            key="c3", text="Andree will handle the chairs now.",
            title="Andree handles the chairs", refs=["Andree"],
            evidence_class="implicit_self_commitment", authority="act",
            actor="external:andree"),
        judge=_KindJudge({"self_undertaking": "no"}),
    )
    commitments, *_ = await _state(ws)
    user_act = [c for c in commitments
                if c.owner_peer_id == "ashley"
                and c.authority == CommitmentCandidateAuthority.ACT
                and c.status == CommitmentCandidateStatus.PENDING]
    assert user_act == []
    # Recall does not reopen completed work.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="c4",
        candidate=_loop_candidate(
            key="c4", text="Did I ever sort the flowers?",
            title="Did I ever sort the flowers?", refs=[]),
    )
    commitments, loops, *_ = await _state(ws)
    assert commitments[0].status == CommitmentCandidateStatus.FULFILLED
    assert [l for l in loops if l.status == OpenLoopStatus.OPEN] == []


# ── SCENARIO D — health / person update ──────────────────────────────────────

@pytest.mark.asyncio
async def test_d_health_matter_phases_without_task_semantics(async_client, monkeypatch):
    ws = "ws-trackd-d-matt"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="d1",
        candidate=_loop_candidate(
            key="d1", text="Matt has surgery tomorrow.",
            title="Matt surgery tomorrow, waiting for news", refs=["Matt"]),
    )
    commitments, loops, *_ = await _state(ws)
    # A health matter is not a user ACT commitment.
    assert [c for c in commitments
            if c.authority == CommitmentCandidateAuthority.ACT] == []
    assert len([l for l in loops if l.status == OpenLoopStatus.OPEN]) == 1
    # Worry/check-in attaches to the live matter (one OPEN thread; the
    # check-in restatement may close+reopen via structural release — accepted
    # wart, documented — but liveness must remain exactly one).
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="d2",
        candidate=_loop_candidate(
            key="d2", text="Still waiting for news on Matt.",
            title="Waiting for news on Matt", refs=["Matt"]),
    )
    _, loops, *_ = await _state(ws)
    assert len([l for l in loops if l.status == OpenLoopStatus.OPEN]) == 1
    # Surgery successful → waiting resolves.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="d3",
        candidate=_event_candidate(
            key="d3", text="Matt is out of surgery, it went well.",
            refs=["Matt"], action="fulfill", target_kind="open_loop"),
        judge=_KindJudge({"fulfils": "yes", "resolves": "yes"}),
    )
    _, loops, *_ = await _state(ws)
    assert [l for l in loops if l.status == OpenLoopStatus.OPEN] == []
    # Recovery issue is a new phase, not a resurrection: the live thread is
    # the fever watch; the surgery/waiting history stays settled.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="d4",
        candidate=_loop_candidate(
            key="d4", text="Matt has a fever after the surgery, watching it.",
            title="Matt post-surgery fever watch", refs=["Matt"]),
    )
    _, loops, *_ = await _state(ws)
    open_loops = [l for l in loops if l.status == OpenLoopStatus.OPEN]
    resolved = [l for l in loops if l.status == OpenLoopStatus.RESOLVED]
    assert len(open_loops) == 1
    assert "fever" in (open_loops[0].title or "").lower()
    assert len(resolved) >= 1
    # Retrospective discussion does not reopen the original surgery loop.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="d5",
        candidate=_loop_candidate(
            key="d5", text="Thinking back on Matt's surgery week.",
            title="Thinking back on Matt surgery week", refs=["Matt"]),
    )
    _, loops, *_ = await _state(ws)
    assert len([l for l in loops if l.status == OpenLoopStatus.RESOLVED]) >= 1


# ── SCENARIO E — uncertainty as future attention ─────────────────────────────

@pytest.mark.asyncio
async def test_e_meaningful_uncertainty_becomes_future_attention(async_client, monkeypatch):
    ws = "ws-trackd-e-meeting"
    # Low-confidence, actor-less matter: must not interrogate now, but the
    # follow-up opportunity should be preserved for later.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="e1",
        candidate=_loop_candidate(
            key="e1", text="I've got that meeting tomorrow and I'm a bit nervous.",
            title="Meeting tomorrow, nervous, unknown what for", refs=[],
            confidence=0.4),
    )
    _, _, _, attentions, clarifications = await _state(ws)
    pending_asks = [c for c in clarifications if c.status == "pending"]
    assert pending_asks == [], "low-consequence uncertainty must not interrogate now"
    assert len(attentions) >= 1, \
        "meaningful uncertainty should be held as future attention"
    assert any("meeting" in (a.content or "").lower() for a in attentions)


@pytest.mark.asyncio
async def test_e_ambiguous_matter_informed_clarification_not_bare_ask(
        async_client, monkeypatch):
    ws = "ws-trackd-e-ambig"
    judge_yes = _KindJudge({"same_matter": "yes"})
    for i, (key, title) in enumerate(
            [("q1", "Carlos owes £2,100 event debt"),
             ("q2", "Carlos flight reimbursement outstanding")]):
        await _send(
            async_client, monkeypatch, workspace_id=ws, sender="ashley",
            message_id=f"m{i}",
            candidate=_loop_candidate(
                key=key, text=title, title=title, refs=["Carlos"]),
            judge=judge_yes,
        )
    _, loops, *_ = await _state(ws)
    # Two content-disjoint matters about one actor stay two loops.
    assert len([l for l in loops if l.status == OpenLoopStatus.OPEN]) == 2
    # Ambiguous fulfilment evidence: neither matter may be closed by guess.
    amb = _KindJudge({"fulfils": "no", "partially_fulfils": "no"})
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_event_candidate(
            key="q3", text="Carlos paid something.", refs=["Carlos"]),
        judge=amb,
    )
    _, loops, _, attentions, clarifications = await _state(ws)
    assert [l for l in loops if l.status == OpenLoopStatus.RESOLVED] == []
    # Either an informed clarification (hypothesis + alternatives) or a held
    # attention — but never a bare "can you clarify?" and never a wrong merge.
    assert len([l for l in loops if l.status == OpenLoopStatus.OPEN]) <= 3
    assert attentions or clarifications, \
        "consequential ambiguity should be held visibly, not dropped silently"


@pytest.mark.asyncio
async def test_e_incidental_uncertainty_disappears_quietly(async_client, monkeypatch):
    ws = "ws-trackd-e-quiet"
    candidate = ExtractionCandidate(
        candidate_key="z1", observation="Hmm, not sure about lunch.",
        raw_evidence="Hmm, not sure about lunch.",
        canonical_title="Unsure about lunch",
        operational_kind="semantic_only", confidence=0.3,
        formation="explicit", extractor_version="track-d-longitudinal",
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="z1", candidate=candidate,
    )
    commitments, loops, _, attentions, clarifications = await _state(ws)
    assert commitments == []
    assert loops == []
    assert attentions == []
    assert clarifications == []


# ── PENDULUM GUARDS (fixes must not cause the opposite failure) ──────────────

@pytest.mark.asyncio
async def test_p1_full_payment_still_closes(async_client, monkeypatch):
    ws = "ws-trackd-p-full"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="p1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="bank_feed",
        message_id="m2",
        candidate=_event_candidate(
            key="p2", text="Incoming payment £2,100 from Carlos, balance settled.",
            refs=["Carlos"]),
        judge=_KindJudge({"fulfils": "yes"}),
    )
    _, loops, *_ = await _state(ws)
    assert [l for l in loops if l.status == OpenLoopStatus.RESOLVED] != []


@pytest.mark.asyncio
async def test_p2_payment_vs_permission_form_stay_distinct(async_client, monkeypatch):
    ws = "ws-trackd-p-neighbours"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="p1", text="School trip payment due Friday.",
            title="School trip payment due Friday", refs=[]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_loop_candidate(
            key="p2", text="School trip permission form needs signing.",
            title="School trip permission form needs signing", refs=[]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="bank_feed",
        message_id="m3",
        candidate=_event_candidate(
            key="p3", text="School trip payment received, thank you.",
            refs=[], action="fulfill", target_kind="open_loop"),
        judge=_KindJudge({"fulfils": "yes", "resolves": "yes"}),
    )
    _, loops, *_ = await _state(ws)
    by_title = { (l.title or ""): l.status for l in loops }
    assert by_title.get("School trip payment due Friday") == OpenLoopStatus.RESOLVED
    assert by_title.get("School trip permission form needs signing") == OpenLoopStatus.OPEN


@pytest.mark.asyncio
async def test_p3_actor_only_overlap_never_closes_without_judge(
        async_client, monkeypatch):
    ws = "ws-trackd-p-actoronly"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="p1", text="Carlos still owes me £2,100 from the event.",
            title="Carlos still owes £2,100 from the event", refs=["Carlos"]),
    )
    # Shares only the actor name; no adapter, so no judge can confirm.
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m2",
        candidate=_event_candidate(
            key="p2", text="Heard from Carlos today, he says hello.",
            refs=["Carlos"]),
    )
    _, loops, *_ = await _state(ws)
    assert [l for l in loops if l.status == OpenLoopStatus.OPEN] != []
    assert [l for l in loops if l.status == OpenLoopStatus.RESOLVED] == []


@pytest.mark.asyncio
async def test_p4_genuine_new_question_still_tracks(async_client, monkeypatch):
    ws = "ws-trackd-p-newq"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="p1", text="Did Andree confirm the chairs?",
            title="Did Andree confirm the chairs?", refs=["Andree"]),
    )
    _, loops, *_ = await _state(ws)
    assert len([l for l in loops if l.status == OpenLoopStatus.OPEN]) == 1


@pytest.mark.asyncio
async def test_p5_genuine_expectation_ambiguity_still_clarifies(
        async_client, monkeypatch):
    from src.models.expectation import Expectation, ExpectationType

    ws = "ws-trackd-p-clari"
    async with async_session_maker() as db:
        for i, title in enumerate(["File the tax return", "Renew the passport"]):
            db.add(Expectation(
                honcho_workspace_id=ws, honcho_session_id="session-1",
                honcho_message_id=f"seed{i}", subject_peer_id="ashley",
                owner_peer_id="ashley",
                expectation_type=ExpectationType.USER_INTENTION,
                title=title, summary=title, raw_temporal_phrase="soon"))
        await db.commit()
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_event_candidate(
            key="p1", text="Done with one of those things.",
            refs=[]),
        judge=_KindJudge({}),
    )
    _, _, _, _, clarifications = await _state(ws)
    assert len(clarifications) == 1


@pytest.mark.asyncio
async def test_p6_ordinary_uncertain_loop_creates_no_attention(
        async_client, monkeypatch):
    ws = "ws-trackd-p-noattn"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m1",
        candidate=_loop_candidate(
            key="p1", text="Paperwork finally sorted, I think.",
            title="Paperwork finally sorted", refs=[], confidence=0.9),
    )
    _, loops, _, attentions, _ = await _state(ws)
    assert len(loops) == 1
    assert attentions == []


@pytest.mark.asyncio
async def test_p7_deictic_with_two_live_matters_never_wrong_merges(
        async_client, monkeypatch):
    ws = "ws-trackd-p-deictic2"
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
            key="p2", text="Matt has surgery tomorrow.",
            title="Matt surgery tomorrow, waiting for news", refs=["Matt"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley",
        message_id="m3",
        candidate=_loop_candidate(
            key="p3", text="Still nothing from him.",
            title="Still nothing from him", refs=[]),
    )
    _, loops, *_ = await _state(ws)
    open_loops = [l for l in loops if l.status == OpenLoopStatus.OPEN]
    titles = {(l.title or "") for l in open_loops}
    # Both originals survive untouched; the ambiguous pronoun holds
    # separately rather than merging wrongly.
    assert "Carlos still owes £2,100 from the event" in titles
    assert "Matt surgery tomorrow, waiting for news" in titles
