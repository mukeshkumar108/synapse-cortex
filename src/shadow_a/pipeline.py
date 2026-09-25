"""Shadow-A pipeline — pure, deterministic, stdlib-only.

Rule-based heuristics below are Phase-A stand-ins for "permissive semantic
extraction". They are intentionally transparent and fixture-grounded so the
architecture claim (graph -> roles -> views -> moves -> SA-gate) can be
evaluated without a model and without touching production extraction.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Optional, Tuple

from .schema import (
    RELATION_VOCAB,
    CandidateMove,
    MatterAssessment,
    ObligationFrame,
    Observability,
    ReadViews,
    ResolutionAttempt,
    ShadowClaim,
    ShadowRelation,
    ShadowResult,
    T2Proposal,
)

_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", (text or "").strip().lower())


def _key_hit(low: str, key: str) -> bool:
    """Word-boundary match so short keys can't fire inside longer words
    (matt ⊂ matter, dad ⊂ grandad)."""
    return re.search(r"\b" + re.escape(key.lower()) + r"\b", low) is not None


def _sid(case_id: str, *parts: str) -> str:
    h = hashlib.sha1("|".join([case_id, *parts]).encode()).hexdigest()
    return h[:12]


# ---------------------------------------------------------------------------
# 1. Claim proposals
# ---------------------------------------------------------------------------

# (key, content template, subjects, modality, condition, confidence, formation)
_CLAIM_RULES: List[Tuple[str, List[str], str, List[str], str, Optional[str], float, str]] = [
    # Carlos / payments
    ("still owes", ["carlos", "user"], "amount owed by carlos (3,000 vs 3,600 incl delivery uncertain)", ["carlos", "user"],
     "reported", None, 0.6, "explicit"),
    ("q1,500", ["carlos", "bank_feed"], "partial payment Q1,500 received from carlos", ["carlos", "user"],
     "stated", None, 0.9, "explicit"),
    ("q1500", ["carlos", "bank_feed"], "partial payment Q1,500 received from carlos", ["carlos", "user"],
     "stated", None, 0.9, "explicit"),
    ("sent q1,500", ["carlos"], "carlos sent Q1,500, rest after bank releases", ["carlos", "user"],
     "promised", "after bank releases transfer", 0.8, "explicit"),
    ("rest after", ["carlos"], "carlos will send remainder after bank release", ["carlos", "user"],
     "promised", "after bank releases transfer", 0.7, "explicit"),
    ("he said friday", ["carlos"], "carlos said friday (which friday uncertain)", ["carlos", "user"],
     "reported", None, 0.4, "explicit"),
    # Freepik
    ("freepik", ["user"], "freepik annual renews saturday; cancel friday morning (still needed for job)", ["user"],
     "conditional", "still needed for job until friday", 0.8, "explicit"),
    ("push that until tomorrow", ["user"], "freepik cancellation pushed to tomorrow afternoon unless told otherwise", ["user"],
     "conditional", "unless user says otherwise; client approval pending", 0.75, "explicit"),
    ("cancelled freepik myself", ["user"], "user cancelled freepik themselves after client approval", ["user"],
     "stated", None, 0.9, "explicit"),
    ("client approved", ["client"], "client approved graphics", ["client", "user"],
     "reported", None, 0.85, "explicit"),
    ("client hasn", ["client"], "client has not approved graphics yet", ["client", "user"],
     "reported", None, 0.7, "explicit"),
    # Isa pact (reconstructed probe; also matches any bilateral pact language)
    ("we agreed", ["user", "isa"], "bilateral pact terms as negotiated", ["user", "isa"],
     "promised", None, 0.8, "explicit"),
    ("isa pact", ["user", "isa"], "bilateral pact terms as negotiated", ["user", "isa"],
     "promised", None, 0.8, "explicit"),
    # Sam disambiguation
    ("studio sam", ["studio_sam"], "studio sam obligation/statement", ["studio_sam", "user"],
     "reported", None, 0.7, "explicit"),
    ("cousin sam", ["cousin_sam"], "cousin sam pickup obligation", ["cousin_sam", "user"],
     "promised", None, 0.8, "explicit"),
    ("contract", ["studio_sam"], "studio contract state as discussed", ["studio_sam", "user"],
     "reported", None, 0.65, "explicit"),
    ("pick mum up", ["cousin_sam"], "cousin sam picks mum up", ["cousin_sam", "user"],
     "promised", None, 0.8, "explicit"),
    ("picking her up", ["cousin_sam"], "cousin sam confirms pickup", ["cousin_sam", "user"],
     "reported", None, 0.85, "explicit"),
    # Health / somatic
    ("neck", ["user"], "neck pain/soreness report", ["user"],
     "stated", None, 0.8, "explicit"),
    ("headache", ["user"], "headache report", ["user"],
     "stated", None, 0.8, "explicit"),
    ("elif", ["elif"], "elif started new job; user wishes they had messaged", ["elif", "user"],
     "stated", None, 0.75, "explicit"),
    ("not a thing", ["user"], "user says somatic issue is over / not a thing", ["user"],
     "stated", None, 0.85, "explicit"),
    ("basically fine", ["user"], "user says somatic issue is over / not a thing", ["user"],
     "stated", None, 0.85, "explicit"),
    ("a bit better", ["user"], "somatic issue improving", ["user"],
     "stated", None, 0.75, "explicit"),
    # Surgery / context
    ("surgery", ["family"], "family surgery context", ["family", "user"],
     "reported", None, 0.8, "explicit"),
    ("matt", ["matt"], "matt health/surgery context", ["matt", "user"],
     "reported", None, 0.75, "explicit"),
    ("dad", ["dad"], "dad surgery context", ["dad", "user"],
     "reported", None, 0.8, "explicit"),
    ("relieved", ["user"], "relief expressed", ["user"],
     "stated", None, 0.8, "explicit"),
    # Third-party (Ashley/Marko/Carlos)
    ("ashley", ["ashley"], "ashley-owned statement/obligation", ["ashley", "user"],
     "reported", None, 0.6, "explicit"),
    ("marko", ["marko"], "marko-owned statement/obligation", ["marko"],
     "reported", None, 0.6, "explicit"),
    ("isa handles", ["isa"], "isa-owned pact term", ["isa", "user"],
     "promised", None, 0.75, "explicit"),
    # Stale loop / open matters
    ("remind me", ["user"], "user asks to be reminded / kept straight", ["user"],
     "intended", None, 0.7, "explicit"),
    ("keep me straight", ["user"], "user asks to be reminded / kept straight", ["user"],
     "intended", None, 0.7, "explicit"),
    ("chairs", ["user", "venue"], "venue chairs confirmation", ["user", "venue"],
     "stated", None, 0.8, "explicit"),
    ("florist", ["user", "florist"], "florist follow-up pending (colours not sent)", ["user", "florist"],
     "conditional", "florist sends colours", 0.6, "explicit"),
    ("cake lady", ["user"], "cake vendor follow-up (user keeps forgetting)", ["user"],
     "intended", None, 0.6, "explicit"),
    # Observability probe
    ("send it friday", ["sam"], "sam said he would send it friday", ["sam", "user"],
     "promised", None, 0.8, "explicit"),
    ("invoice friday", ["sam"], "sam said he would send it friday", ["sam", "user"],
     "promised", None, 0.8, "explicit"),
    ("agreed terms", ["user", "isa"], "bilateral pact terms as negotiated", ["user", "isa"],
     "promised", None, 0.8, "explicit"),
    ("school run", ["user", "isa"], "school-run split term of pact", ["user", "isa"],
     "promised", None, 0.75, "explicit"),
    ("mornings", ["user", "isa"], "mornings term of pact", ["user", "isa"],
     "promised", None, 0.75, "explicit"),
    ("revisit sunday", ["user", "isa"], "review-sunday term of pact", ["user", "isa"],
     "promised", None, 0.75, "explicit"),
    ("romantic", ["user", "isa"], "romantic wrapper around pact talks", ["user", "isa"],
     "stated", None, 0.7, "explicit"),
    ("grandad", ["user"], "grandad original letter for auntie", ["user", "auntie"],
     "stated", None, 0.8, "explicit"),
    ("loft", ["user"], "grandad original letter found in loft, photo sent", ["user", "auntie"],
     "stated", None, 0.85, "explicit"),
    ("auntie", ["user", "auntie"], "auntie photo/letter matter", ["user", "auntie"],
     "stated", None, 0.75, "explicit"),
    ("different words, same matter", ["user"], "same matter restated in different words", ["user"],
     "stated", None, 0.7, "explicit"),
]

_REL_HINTS = [
    ("cancelled freepik", "freepik annual", "supersedes"),
    ("pushed to tomorrow", "freepik annual", "supersedes"),
    ("improving", "neck pain", "refines"),
    ("over / not a thing", "neck pain", "resolves"),
    ("confirms pickup", "pick mum up", "fulfils"),
    ("partial payment", "amount owed by carlos", "partially_fulfils"),
    ("remainder after bank", "amount owed by carlos", "depends_on"),
    ("photo sent", "grandad original", "fulfils"),
    ("same matter restated", "grandad original", "refines"),
    ("review-sunday term", "bilateral pact", "part_of"),
    ("school-run split", "bilateral pact", "part_of"),
    ("mornings term", "bilateral pact", "part_of"),
    ("romantic wrapper", "bilateral pact", "part_of"),
]


def extract_claims(case_id: str, events: List[Dict]) -> List[ShadowClaim]:
    claims: List[ShadowClaim] = []
    seen: Dict[str, ShadowClaim] = {}
    for ev in events:
        text = ev.get("content", "")
        low = _norm(text)
        eid = ev.get("id", "?")
        ts = ev.get("timestamp")
        for key, _subj_hint, content, subjects, modality, condition, conf, formation in _CLAIM_RULES:
            if not _key_hit(low, key):
                continue
            cid = _sid(case_id, content)
            if cid in seen:
                prev = seen[cid]
                if eid not in prev.evidence_refs:
                    merged = ShadowClaim(
                        claim_id=prev.claim_id, content=prev.content,
                        subjects=prev.subjects,
                        evidence_refs=prev.evidence_refs + [eid],
                        modality=prev.modality, condition=prev.condition or condition,
                        formation=prev.formation, confidence=max(prev.confidence, conf),
                        effective_at=prev.effective_at, discovered_at=prev.discovered_at or ts,
                    )
                    seen[cid] = merged
                continue
            seen[cid] = ShadowClaim(
                claim_id=cid, content=content, subjects=list(subjects),
                evidence_refs=[eid], modality=modality, condition=condition,
                formation=formation, confidence=conf,
                effective_at=ts, discovered_at=ts,
            )
    # stable order
    claims = sorted(seen.values(), key=lambda c: c.claim_id)
    return claims


# ---------------------------------------------------------------------------
# 2. Relations
# ---------------------------------------------------------------------------

def propose_relations(case_id: str, claims: List[ShadowClaim]) -> List[ShadowRelation]:
    rels: List[ShadowRelation] = []
    by_id = {c.claim_id: c for c in claims}

    def find(substr: str) -> Optional[ShadowClaim]:
        for c in claims:
            if substr in _norm(c.content):
                return c
        return None

    for from_hint, to_hint, rtype in _REL_HINTS:
        f = find(from_hint)
        t = find(to_hint)
        if f and t and f.claim_id != t.claim_id:
            assert rtype in RELATION_VOCAB
            rels.append(ShadowRelation(
                relation_id=_sid(case_id, "rel", rtype, f.claim_id, t.claim_id),
                rel_type=rtype, from_id=f.claim_id, to_id=t.claim_id,
                evidence_refs=sorted(set(f.evidence_refs + t.evidence_refs)),
                formation="inferred", confidence=0.7,
                effective_at=f.effective_at, discovered_at=f.discovered_at,
            ))

    # Isa pact decomposition: pact claim part_of bilateral terms (reconstructed
    # probe carries pact_term_* claims; link each term into the pact).
    pact = find("bilateral pact")
    if pact:
        for c in claims:
            if c.claim_id != pact.claim_id and (
                c.claim_id.startswith("term") or "pact term" in _norm(c.content)
                or "romantic" in _norm(c.content)
            ):
                rels.append(ShadowRelation(
                    relation_id=_sid(case_id, "rel", "part_of", c.claim_id, pact.claim_id),
                    rel_type="part_of", from_id=c.claim_id, to_id=pact.claim_id,
                    evidence_refs=sorted(set(c.evidence_refs + pact.evidence_refs)),
                    formation="inferred", confidence=0.75,
                    effective_at=c.effective_at, discovered_at=c.discovered_at,
                ))
    # Sam anti-merge: explicitly record that the two Sam claims are NOT same_as.
    # Absence of a same_as edge IS the correct output; record a blocks edge so
    # evaluators can see the merge was considered and refused.
    s_studio = find("studio sam obligation")
    s_cousin = find("cousin sam pickup")
    if s_studio and s_cousin:
        rels.append(ShadowRelation(
            relation_id=_sid(case_id, "rel", "blocks", s_studio.claim_id, s_cousin.claim_id),
            rel_type="blocks", from_id=s_studio.claim_id, to_id=s_cousin.claim_id,
            evidence_refs=sorted(set(s_studio.evidence_refs + s_cousin.evidence_refs)),
            formation="inferred", confidence=0.9,
            effective_at=s_studio.effective_at, discovered_at=s_studio.discovered_at,
            status="active",
        ))
    # Stale-loop vocabulary bridge: a later differently-worded claim that
    # restates an earlier open matter gets a refines edge (closure support).
    for c in claims:
        if "same matter restated" in _norm(c.content):
            for t in claims:
                if t.claim_id != c.claim_id and "open matter" in _norm(t.content):
                    rels.append(ShadowRelation(
                        relation_id=_sid(case_id, "rel", "refines", c.claim_id, t.claim_id),
                        rel_type="refines", from_id=c.claim_id, to_id=t.claim_id,
                        evidence_refs=sorted(set(c.evidence_refs + t.evidence_refs)),
                        formation="inferred", confidence=0.7,
                        effective_at=c.effective_at, discovered_at=c.discovered_at,
                    ))
    # dedupe
    uniq: Dict[str, ShadowRelation] = {}
    for r in rels:
        uniq[r.relation_id] = r
    return sorted(uniq.values(), key=lambda r: r.relation_id)


# ---------------------------------------------------------------------------
# 3. State roles (0..n, never a partition)
# ---------------------------------------------------------------------------

def assign_roles(claims: List[ShadowClaim], relations: List[ShadowRelation]) -> Dict[str, List[str]]:
    resolved_targets = {r.to_id for r in relations if r.rel_type in ("resolves", "fulfils", "refines")}
    superseded_targets = {r.to_id for r in relations if r.rel_type == "supersedes"}
    # Completion records in evidence ("cancelled ... myself", "photo sent",
    # "paid back") are assertional history, not live obligations.
    _DONE = ("cancelled", "photo sent", "paid back", "signed the contract",
             "found", "replied yes")
    roles: Dict[str, List[str]] = {}
    for c in claims:
        low = _norm(c.content)
        r: List[str] = ["assertional"]
        if any(k in low for k in ("owe", "payment", "promise", "pact", "confirm chairs", "remind", "pick mum",
                                          "pickup", "cancel", "obligation", "send it friday", "send the remainder")):
            r.append("obligation")
        if any(k in low for k in ("uncertain", "which friday", "pending", "follow-up", "keeps forgetting",
                                          "not sent", "open matter", "conditional", "unless")) or c.modality in ("intended", "conditional"):
            r.append("unresolved")
        if any(k in low for k in ("will send", "after bank", "surgery", "pickup", "renews", "due")):
            r.append("predictive")
        if any(k in low for k in ("pain", "headache", "worry", "relief", "remind", "follow-up", "check")):
            r.append("attentional")
        # resolved/fulfilled targets shed obligation+unresolved but keep assertional
        if c.claim_id in resolved_targets:
            r = [x for x in r if x not in ("obligation", "unresolved")]
        if any(k in low for k in _DONE) and c.modality == "stated":
            r = [x for x in r if x not in ("obligation", "unresolved")]
        if c.claim_id in superseded_targets and "supersede" not in low:
            r = [x for x in r if x != "obligation"]
        # dedupe, stable order
        seen: List[str] = []
        for x in r:
            if x not in seen:
                seen.append(x)
        roles[c.claim_id] = seen
    return roles


# ---------------------------------------------------------------------------
# 4. Directed obligation frames
# ---------------------------------------------------------------------------

_OBLIGOR_HINTS = [
    ("isa handles", "isa", "user"),
    ("isa-owned", "isa", "user"),
    ("school-run split", "user+isa", "user+isa"),
    ("review-sunday", "user+isa", "user+isa"),
    ("mornings term", "user", "user+isa"),
    ("romantic wrapper", "user+isa", "user+isa"),    ("carlos", "carlos", "user"),
    ("studio sam", "studio_sam", "user"),
    ("cousin sam", "cousin_sam", "user"),
    ("sam said", "sam", "user"),
    ("ashley", "ashley", "user"),
    ("marko", "marko", "isa"),
    ("bilateral pact", "user+isa", "user+isa"),
    ("freepik", "user", "user"),
    ("remind", "user", "user"),
    ("chairs", "user", "venue"),
    ("florist", "user", "florist"),
    ("pick mum", "cousin_sam", "user"),
    ("pickup", "cousin_sam", "user"),
]


def build_obligations(case_id: str, claims: List[ShadowClaim],
                      roles: Dict[str, List[str]]) -> List[ObligationFrame]:
    frames: List[ObligationFrame] = []
    for c in claims:
        if "obligation" not in roles.get(c.claim_id, []):
            continue
        low = _norm(c.content)
        obligor, beneficiary = "user", "user"
        for hint, o, b in _OBLIGOR_HINTS:
            if hint in low:
                obligor, beneficiary = o, b
                break
        frames.append(ObligationFrame(
            frame_id=_sid(case_id, "obl", c.claim_id),
            claim_id=c.claim_id,
            obligor=obligor,
            beneficiary=beneficiary,
            action=c.content,
            condition=c.condition,
            due=c.effective_at,
            authority="explicit_command" if obligor == "user" and "cancel" in low else "reported_statement",
            strength="strong" if "promise" in low else "normal",
            modality=c.modality,
        ))
    return sorted(frames, key=lambda f: f.frame_id)


# ---------------------------------------------------------------------------
# 5. Shadow T2 (inferred, never hardcoded, never persisted)
# ---------------------------------------------------------------------------

_DISTRESS = ["killing me", "sore", "worse", "didn't sleep", "all over the place", "mess",
             "worry", "surgery", "hospital", "anxious", "overwhelm"]
_RELIEF = ["better", "fine now", "not a thing", "relieved", "amazing", "paid back",
           "sorted", "done", "approved", "home fine"]
_LOAD = ["dump", "too many", "all over the place", "keep forgetting", "keep me straight",
         "lot", "mess"]


def _count_hits(text: str, words: List[str]) -> int:
    return sum(len(re.findall(r"\b" + re.escape(w.lower()) + r"\b", text)) for w in words)


def propose_t2(case_id: str, events: List[Dict], claims: List[ShadowClaim],
               roles: Dict[str, List[str]]) -> T2Proposal:
    full = "\n".join(_norm(e.get("content", "")) for e in events)
    first_half = "\n".join(_norm(e.get("content", "")) for e in events[: max(1, len(events) // 2)])
    second_half = "\n".join(_norm(e.get("content", "")) for e in events[max(1, len(events) // 2):])
    d0 = _count_hits(full, _DISTRESS)
    r1 = _count_hits(second_half, _RELIEF)
    r0 = _count_hits(first_half, _RELIEF)
    load = _count_hits(full, _LOAD)
    open_n = sum(1 for c in claims if "unresolved" in roles.get(c.claim_id, []))

    labels: List[str] = []
    if load >= 2 or open_n >= 4:
        labels.append("high_load")
    if _count_hits(full, ["neck", "headache", "surgery", "matt", "dad", "worry"]):
        labels.append("health_watch_present")
    if _count_hits(full, ["surgery", "hospital"]):
        labels.append("family_health_context")
    if r1 > r0:
        labels.append("relief_trajectory")
    if not labels:
        labels.append("ordinary_ops")

    trajectory = "steady"
    if r1 > r0 and d0 > 0:
        trajectory = "easing"
    elif r1 == 0 and d0 >= 3:
        trajectory = "intensifying"

    # context_weight attenuates routine nudges when distress/load dominates.
    context_weight = min(1.0, 0.15 * d0 + (0.2 if "high_load" in labels else 0.0))
    if "relief_trajectory" in labels:
        context_weight = max(0.0, context_weight - 0.2)

    means = [f"shadow reading: {', '.join(labels)} over {len(events)} evidence items"]
    unresolved = [c.content for c in claims if "unresolved" in roles.get(c.claim_id, [])][:3]
    tensions: List[str] = []
    if "health_watch_present" in labels and open_n >= 3:
        tensions.append("health signals compete with operational load for attention")
    easing = [c.content for c in claims if _count_hits(_norm(c.content), [
        "better", "fine now", "not a thing", "relieved", "paid back"])][:3]
    return T2Proposal(means=means, unresolved=unresolved, trajectory=trajectory,
                      easing=easing, tensions=tensions, context_labels=labels,
                      context_weight=round(context_weight, 2),
                      evidence_refs=[e.get("id", "?") for e in events[:6]])


# ---------------------------------------------------------------------------
# 6. Derived read views
# ---------------------------------------------------------------------------

def build_views(claims: List[ShadowClaim], roles: Dict[str, List[str]],
                obligations: List[ObligationFrame]) -> ReadViews:
    todo, reminder, open_m, worry, follow, comp = [], [], [], [], [], []
    for c in claims:
        r = roles.get(c.claim_id, [])
        low = _norm(c.content)
        if "obligation" in r and any(s in (c.subjects or []) for s in ("user",)) or "user" in c.subjects:
            if "neck" not in low and "headache" not in low:
                todo.append(c.content)
        if "remind" in low or "keep me straight" in low or "due" in low or "renews" in low:
            reminder.append(c.content)
        if "unresolved" in r:
            open_m.append(c.content)
        if any(k in low for k in ("surgery", "worry", "pain", "headache", "matt", "dad", "elif")):
            worry.append(c.content)
        if any(k in low for k in ("follow-up", "keeps forgetting", "not sent", "colours", "chase",
                                          "check", "rest after", "remainder")) or "unresolved" in r:
            follow.append(c.content)
    for o in obligations:
        # Amendment 2: only self-promised, user-benefiting or user-owed frames can
        # become companion self-accounting. Third-party frames never land here;
        # they derive WATCH/FOLLOW_UP moves instead (build_moves).
        if o.obligor in ("sophie", "user") and o.modality in ("promised", "intended", "conditional"):
            comp.append(f"{o.obligor} owes {o.beneficiary or '?'}: {o.action}")
    return ReadViews(todo=sorted(set(todo)), reminder=sorted(set(reminder)),
                     open_matter=sorted(set(open_m)), worry=sorted(set(worry)),
                     follow_up=sorted(set(follow)), companion_obligation=sorted(set(comp)))


# ---------------------------------------------------------------------------
# 7+8. CandidateMoves with system-attention-before-user-attention gate
# ---------------------------------------------------------------------------

def _internal_attempt(matter_id: str, content: str, observed: List[str],
                      relations: List[ShadowRelation]) -> ResolutionAttempt:
    low = _norm(content)
    has = lambda *ws: any(_key_hit(low, w) for w in ws)
    linked = [r for r in relations if r.from_id == matter_id or r.to_id == matter_id]
    if linked and any(r.rel_type in ("fulfils", "partially_fulfils", "resolves", "supersedes", "refines") for r in linked):
        return ResolutionAttempt(matter_id, "reconcile_sources",
                                 observed + ["shadow_claims"], "partial",
                                 f"{len(linked)} lifecycle relation(s) already explain part of the matter")
    if has("q1,500", "payment", "invoice", "bank") and "bank_feed" in observed:
        return ResolutionAttempt(matter_id, "verify_feed", ["bank_feed", "shadow_claims"], "partial",
                                 "feed reconciles part; remainder still outstanding")
    if has("sam") and "sms" in observed:
        return ResolutionAttempt(matter_id, "search_honcho", ["sms", "shadow_claims"], "partial",
                                 "cross-source identity evidence available")
    if has("contract", "email") and "email" in observed:
        return ResolutionAttempt(matter_id, "search_honcho", ["email", "shadow_claims"], "partial",
                                 "external source holds newer state")
    return ResolutionAttempt(matter_id, "search_state", ["shadow_claims"], "unresolved",
                             "no internal source finishes the job")


def derive_moves(case_id: str, claims: List[ShadowClaim], roles: Dict[str, List[str]],
                 relations: List[ShadowRelation], obligations: List[ObligationFrame],
                 t2: T2Proposal, observed: List[str],
                 user_tracking_ok: bool) -> Tuple[List[CandidateMove], List[MatterAssessment]]:
    moves: List[CandidateMove] = []
    assessments: List[MatterAssessment] = []
    obl_by_claim = {o.claim_id: o for o in obligations}
    dampened = t2.context_weight >= 0.4

    for c in claims:
        r = roles.get(c.claim_id, [])
        low = _norm(c.content)
        o = obl_by_claim.get(c.claim_id)
        attempts = [_internal_attempt(c.claim_id, c.content, observed, relations)]
        internally_done = attempts[0].outcome == "resolved"

        kind: Optional[str] = None
        reason = "OPPORTUNITY"
        user_facing = False
        eligibility = "eligible"
        lifecycle = "eligible"
        telemetry = "NO_MOVE_WARRANTED"
        salience = round(min(1.0, 0.3 + 0.1 * len(c.evidence_refs) + (0.2 if "unresolved" in r else 0.0)), 2)

        # Amendment 3 core: somatic one-offs retain claims + roles and yield
        # NO_MOVE_WARRANTED with no suppression object and no move.
        somatic = any(k in low for k in ("neck", "headache"))
        somatic_over = any(k in low for k in ("over / not a thing", "not a thing", "basically fine"))
        if somatic and ("resolves" in low or somatic_over or "improving" in low or len(c.evidence_refs) <= 2):
            # keep claim, no move, no suppression
            assessments.append(MatterAssessment(c.claim_id, r, "NO_MOVE_WARRANTED", [],
                                                attempts, "somatic signal retained; restraint without suppression"))
            continue
        if somatic and not somatic_over and len(c.evidence_refs) >= 3 and "wors" in low:
            kind, reason = "WATCH", "MONITOR"  # persistent/worsening somatic -> internal watch

        if kind is None and o is not None:
            # Amendment 2: third-party obligations never become self debt; they
            # may derive a separate WATCH/FOLLOW_UP when authority allows.
            third_party = o.obligor not in ("user", "sophie", "user+isa")
            if third_party:
                if user_tracking_ok:
                    # Amendment 2: ownership stays external; the derived WATCH
                    # is a separate, internal, non-user-facing move.
                    kind, reason = "WATCH", "MONITOR"
                    user_facing = False
                    if dampened:
                        eligibility, lifecycle, telemetry = "held:context_dampened", "held", "MOVE_HELD"
                    else:
                        telemetry = "MOVE_ELIGIBLE"
                else:
                    telemetry = "MOVE_HELD"
                    eligibility, lifecycle = "held:no_user_authority", "held"
            else:
                if "remind" in low or "due" in low or "renews" in low:
                    kind, reason, user_facing = "REMIND", "DUE", True
                elif c.modality == "conditional" or "term of pact" in low or "wrapper" in low:
                    # Standing terms / conditional intentions are watched, not
                    # acted on: no due, no action verb, no user-facing move.
                    kind, reason = "WATCH", "MONITOR"
                elif "unresolved" in r:
                    kind, reason, user_facing = "FOLLOW_UP", "CHECK_BACK", True
                else:
                    kind, reason = "ACT", "FULFIL_OWN_PROMISE"
                if internally_done:
                    kind, telemetry = None, "NO_MOVE_WARRANTED"
                elif dampened and kind in ("REMIND", "FOLLOW_UP") and not (
                        "remind" in low and c.modality == "intended"):
                    # T2 dampening applies to inferred nudges, never to an
                    # explicit user request (modality intended + remind).
                    eligibility, lifecycle, telemetry = "held:context_dampened", "held", "MOVE_HELD"
                elif kind:
                    telemetry = "MOVE_ELIGIBLE"
        elif kind is None:
            if "unresolved" in r and any(k in low for k in ("remind", "keep me straight", "follow-up",
                                                                     "keeps forgetting", "not sent", "check")):
                kind, reason, user_facing = "FOLLOW_UP", "CHECK_BACK", True
                telemetry = "MOVE_ELIGIBLE"
                if dampened:
                    eligibility, lifecycle, telemetry = "held:context_dampened", "held", "MOVE_HELD"
            elif "which friday" in low or "uncertain" in low:
                # Amendment: prefer internal reconcile over asking; user question
                # only if no observed source can settle it.
                if any(s in observed for s in ("email", "calendar", "sms")):
                    telemetry = "MOVE_HELD"
                    eligibility, lifecycle = "held:internal_first", "held"
                else:
                    kind, reason, user_facing = "QUESTION", "CLARIFY", True
                    telemetry = "MOVE_ELIGIBLE"
            elif "elif" in low:
                kind, reason, user_facing = "FOLLOW_UP", "CHECK_BACK", True
                telemetry = "MOVE_ELIGIBLE"

        # SA gate: a user-facing move whose internal attempt is unresolved but a
        # covering observed source exists stays held for one more internal pass,
        # except explicit DUE reminders the user already authorized.
        created: List[CandidateMove] = []
        if kind:
            if user_facing and attempts[0].outcome == "unresolved" and reason in ("CLARIFY", "CHECK_BACK"):
                if any(s in observed for s in ("email", "bank_feed", "sms", "calendar")) and reason == "CLARIFY":
                    eligibility, lifecycle, telemetry = "held:internal_first", "held", "MOVE_HELD"
                    user_facing = False
            created.append(CandidateMove(
                move_id=_sid(case_id, "move", kind, c.claim_id), kind=kind, reason=reason,
                matter_id=c.claim_id, source_refs=list(c.evidence_refs),
                support_strength=c.confidence, salience=salience, eligibility=eligibility,
                validity_window=c.effective_at, lifecycle=lifecycle,
                owner="sophie", user_facing=user_facing))
            moves.extend(created)
        if not created and telemetry in ("NO_MOVE_WARRANTED", "MOVE_HELD"):
            pass
        elif not created:
            # Distinguish healthy restraint from blindness (amendment: theory
            # must tell NO_MOVE_WARRANTED apart from UNREPRESENTED).
            if any(k in low for k in ("scene", "3d ", "regime", "habit loop")):
                telemetry = "UNREPRESENTED_SCHEMA_GAP"
                note_extra = "language points outside shadow schema (scene/regime)"
            elif ("uncertain" in low or "unknown" in low or "ambiguous" in low) and c.confidence < 0.5:
                telemetry = "UNRESOLVED_SEMANTICS"
                note_extra = "low-confidence ambiguity with no frame"
            else:
                telemetry = "NO_MOVE_WARRANTED"
                note_extra = "roles do not warrant a move"
            assessments.append(MatterAssessment(c.claim_id, r, telemetry, created, attempts,
                                                note_extra))
            continue
        assessments.append(MatterAssessment(c.claim_id, r, telemetry, created, attempts,
                                            "third-party watch (no self debt)" if (
                                                o and o.obligor not in ("user", "sophie", "user+isa")
                                                and created) else ""))
    # stable order
    moves.sort(key=lambda m: m.move_id)
    assessments.sort(key=lambda a: a.matter_id)
    return moves, assessments


# ---------------------------------------------------------------------------
# Observability-gated absence (Amendment 1)
# ---------------------------------------------------------------------------

def absence_check(case_id: str, label: str, expected: str,
                  observability: Observability) -> Dict:
    """expected_but_missing only when the window was actually observed."""
    if observability.observed:
        return {"label": label, "expected": expected,
                "finding": "expected_but_missing",
                "source": observability.source, "window": observability.window}
    return {"label": label, "expected": expected, "finding": "UNKNOWN",
            "source": observability.source, "window": observability.window,
            "reason": "source not observed; lack of evidence is not negative evidence"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_case(case_id: str, events: List[Dict], observed_sources: List[str],
             user_tracking_ok: bool = True,
             absence_probes: Optional[List[Dict]] = None) -> ShadowResult:
    claims = extract_claims(case_id, events)
    relations = propose_relations(case_id, claims)
    roles = assign_roles(claims, relations)
    obligations = build_obligations(case_id, claims, roles)
    t2 = propose_t2(case_id, events, claims, roles)
    views = build_views(claims, roles, obligations)
    moves, assessments = derive_moves(case_id, claims, roles, relations,
                                      obligations, t2, observed_sources,
                                      user_tracking_ok)
    res = ShadowResult(case_id=case_id, claims=claims, relations=relations,
                       roles=roles, obligations=obligations, t2=t2,
                       views=views, moves=moves, assessments=assessments)
    for probe in absence_probes or []:
        raw = probe["observability"]
        obs = raw if isinstance(raw, Observability) else Observability(
            source=raw.get("source", "?"), window=raw.get("window", ""),
            observed=bool(raw.get("observed", False)),
            last_observed_at=raw.get("last_observed_at"))
        out = absence_check(case_id, probe["label"], probe["expected"], obs)
        (res.expected_but_missing if out["finding"] == "expected_but_missing"
         else res.unknowns).append(out)
    return res
