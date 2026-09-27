"""Session reconstruction V2: evidence-first canonical post-session state.

V1 asked the model to review existing rows via imperative ops — conservative
by construction: missing rows could not be established, lifecycle needed
targets, and session-created rows were framed as objects to affirm. V2 asks
the stronger question:

  Given session-start state + complete raw session evidence, what should
  now be durably true?

The model proposes a CANONICAL POST-SESSION INTERPRETATION (state-first,
not op-list: a set of matters with status, no imperative ordering, temp
pids instead of invented ids). Deterministic code validates, then diffs
start-state -> proposed-state into the V1 op vocabulary for the shadow
would-apply report. Same guarantees, stronger semantic task.

Framing rules (structural, not per-scenario):
- Evidence-first prompt order: START STATE -> RAW TRANSCRIPT -> PROVISIONAL
  rows labeled UNTRUSTED (may be correct, duplicate, incomplete, or wrong).
  Never "are these rows okay" — always "what actually changed".
- Session-created rows are provisional hypotheses, never semantic authority.
  The model may preserve, supersede, mark redundant, ignore, or fill gaps.
- SHADOW ONLY. Nothing here mutates interpreted state except one audit
  trace. No apply switch in this tranche.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.services.session_consolidation import (
    MIN_CONFIDENCE,
    SessionTurn,
    SnapshotMatter,
    StartSnapshot,
    ValidatedOp,
    capture_session_created,
    capture_snapshot,
    check_would_apply,
)

logger = logging.getLogger(__name__)

TRANSCRIPT_CHAR_CAP = 6000
MAX_TURNS = 40
# Segment budget: long real sessions (100+ verbose turns) need ~15 windows
# at the char cap. Each window is one bounded model call (~$0.001), so
# the budget is cost, not semantics; coverage accounting stays explicit.
MAX_SEGMENTS = 20
MAX_MATTERS = 20
MAX_PROPOSED = 24
MATTER_TITLE_CAP = 160
MAX_SUBJECTS = 4
SUBJECT_CAP = 40

MATTER_KINDS = ("obligation", "watch", "uncertainty", "event", "expectation")
# "redundant": this start-state row should not survive (junk, duplicate, or
# superseded — use superseded_by_pid when another pid continues it). The
# explicit negative assertion is what lets reconstruction REJECT provisional
# junk instead of affirming-by-default; omission alone is ambiguous.
MATTER_STATUS = ("open", "resolved", "partial", "uncertain", "redundant")
MATTER_VIA = ("completed", "cancelled", "superseded")
OWNER_ALLOW = ("user", "unknown")
PROVISIONAL_VERDICTS = ("keep", "redundant", "superseded")


@dataclass
class ReconstructionResult:
    accepted: List[ValidatedOp] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    provisional_marks: List[Dict[str, Any]] = field(default_factory=list)
    would_apply: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    error: str = ""
    prompt_chars: int = 0
    latency_s: float = 0.0


def build_reconstruction_prompt(snapshot: StartSnapshot,
                                transcript: List[SessionTurn],
                                provisional: List[SnapshotMatter],
                                user_peer_id: Optional[str] = None,
                                checkpoints: Optional[List[Dict[str, Any]]] = None,
                                receipts: Optional[List[Dict[str, Any]]] = None,
                                prior_proposals: Optional[List[Dict[str, Any]]] = None) -> str:
    turns = transcript[:MAX_TURNS]
    lines = [
        "SESSION RECONSTRUCTOR: given the session-start longitudinal state and the",
        "complete raw session evidence below, propose the canonical durable state that",
        "should hold AFTER this session. Reason from the EVIDENCE, not from any",
        "provisional interpretation. Conservative: fewer matters over guessing; never",
        "invent facts, people, amounts, message IDs, or matter IDs.",
        "Ordinary daily trivia (meals, weather, jokes, small talk, passing remarks)",
        "belongs in incidental_mids — never in matters — even when mentioned next to",
        "a real matter. A turn that ONLY expresses uncertainty about an ordinary daily",
        "detail, with no person owed, no commitment, no amount, and no outcome at stake,",
        "is incidental, not an uncertainty-matter. Restraint is correctness: the best",
        "proposal for a trivial session is the smallest one.",
        "",
        "1. CORTEX STATE AT SESSION START:",
    ]
    if user_peer_id:
        lines.append(f"(The user's own speaker name is '{user_peer_id}': their matters "
                     f"use owner 'user'. Start-state rows may show owner={user_peer_id}.)")
    if snapshot.matters:
        for m in snapshot.matters[:MAX_MATTERS]:
            lines.append(
                f"- [matter {m.id}] {m.kind} {m.status}"
                + (f" owner={m.owner}" if m.owner else "")
                + f": {(m.title or 'untitled')[:MATTER_TITLE_CAP]}")
    else:
        lines.append("(nothing tracked)")
    if snapshot.people:
        lines.append("PEOPLE: " + ", ".join(snapshot.people[:12]))
    if snapshot.suppressions:
        lines.append("ACTIVE SUPPRESSIONS: " + "; ".join(snapshot.suppressions[:8]))
    lines.append("")
    lines.append("2. FULL RAW SESSION EVIDENCE (in order; speakers: user / external:<name> / bank_feed):")
    used = 0
    for t in turns:
        chunk = f"[msg:{t.message_id}] {t.speaker}: {(t.text or '').strip()}"
        if used + len(chunk) > TRANSCRIPT_CHAR_CAP:
            break
        lines.append(chunk)
        used += len(chunk)
    if receipts:
        lines.append("")
        lines.append("2b. ACTION RECEIPTS (factual evidence of what happened during the session — "
                     "quotable as [receipt:N] spans exactly like transcript turns):")
        for i, r in enumerate(receipts[:12]):
            if isinstance(r, dict) and str(r.get("text") or "").strip():
                lines.append(f"[receipt:{i}] {str(r.get('kind') or 'action')}: "
                             f"{str(r.get('text') or '').strip()[:300]}")
    if checkpoints:
        lines.append("")
        lines.append("2c. NAVIGATION CHECKPOINTS (provisional working-memory summaries — orientation "
                     "only, NEVER evidence: do not cite their claims as spans, do not affirm them):")
        for c in checkpoints[:6]:
            if isinstance(c, dict) and str(c.get("text") or "").strip():
                lines.append(f"- ({str(c.get('label') or 'checkpoint')[:40]}): "
                             f"{str(c.get('text') or '').strip()[:300]}")
    if prior_proposals:
        lines.append("")
        lines.append("2d. ALREADY PROPOSED EARLIER THIS SESSION (from prior segments — do not "
                     "re-propose these; build on them or leave them):")
        for p in prior_proposals[:24]:
            if isinstance(p, dict) and str(p.get("title") or "").strip():
                lines.append(f"- [{str(p.get('op') or 'op')}] {str(p.get('title') or '')[:120]}")
    lines.append("")
    lines.append("3. UNTRUSTED PROVISIONAL INTERPRETATION (produced live during ingestion; "
                 "may be correct, duplicate, incomplete, or WRONG — do not affirm by default):")
    if provisional:
        for m in provisional[:MAX_MATTERS]:
            lines.append(
                f"- [provisional {m.id}] {m.kind} {m.status}: "
                f"{(m.title or 'untitled')[:MATTER_TITLE_CAP]}")
    else:
        lines.append("(none)")
    lines.extend([
        "",
        "Propose the post-session state. matters[]: every durable matter that should hold",
        "after this session (both continued and newly established), each with pid (m1, m2, ...),",
        "kind obligation|watch|uncertainty|event|expectation (use exactly one of these words):",
        "obligation = an action owed by someone; watch = an ongoing trajectory or outcome worth",
        "carrying because it plausibly matters later (pain, recovery, waiting, an important",
        "uncertain event) — NOT a one-off description, which belongs in incidental_mids;",
        "uncertainty = an open question with no action; event = something that happened;",
        "expectation = a future belief about what will happen.",
        "title, status open|resolved|partial|uncertain|redundant,",
        "title, status open|resolved|partial|uncertain|redundant,",
        "owner: 'user' when the matter belongs to the user speaking in the evidence;",
        "'external:<name>' ONLY when that party speaks in the evidence as 'external:<name>';",
        "otherwise 'unknown'. Never invent external identities; never label the user as external.",
        "basis existing|new (use 'new' with matter_id omitted whenever the matter",
        "is NOT listed in section 1 — including the common case where section 1 is",
        "empty; 'existing' requires the exact [matter id]),",
        "matter_id (the [matter id] when basis=existing), via completed|cancelled|superseded",
        "(required when status=resolved), remainder (required when partial), same_as_pid (another",
        "pid when two entries are the same matter), status redundant (with optional superseded_by_pid)",
        "when a start-state row should NOT survive (junk/duplicate/superseded — never affirm junk by default),",
        "especially generic question-shaped rows ('inquire about...', 'follow up on...',",
        "'check whether...') with no supporting evidence: a row whose title could describe",
        "almost any conversation is not a matter and must be marked redundant, not affirmed.",
        "subjects: the people or named entities the matter is about, using words from the evidence",
        "(e.g. [\"Matt\"]); empty list when none. Subjects let later evidence reattach to this thread.",
        "follow_up (natural future attention, if any),",
        "evidence{message_ids[], spans[{message_id, span}] with VERBATIM spans — evidence holds ONLY",
        "these two keys}, confidence (0..1), rationale (one line). confidence and rationale are",
        "TOP-LEVEL fields on every entry: never nest them inside evidence.",
        "Change assertions (new basis, resolved/partial/redundant status) REQUIRE verbatim spans;",
        "pure continuations (basis existing, status unchanged) may cite message_ids: [] when no",
        "turn touched them. uncertainties[]/attentions[] need verbatim spans OR a link to a",
        "proposed/existing matter plus cited message_ids. suppressions[] need topic+reason+spans.",
        "incidental_mids[] lists turns with nothing durable. provisional_review[] judges each",
        "[provisional id] as keep|redundant|superseded with reason. Max "
        f"{MAX_PROPOSED} matters.",
    ])
    return "\n".join(lines)


def _ground_spans(spans: Any, by_msg: Dict[str, str]) -> Optional[list]:
    if not isinstance(spans, list):
        return None
    out = []
    for entry in spans:
        if not isinstance(entry, dict):
            return None
        mid = str(entry.get("message_id") or "")
        span = str(entry.get("span") or "")
        if mid not in by_msg or not span.strip():
            return None
        if span.strip() not in (by_msg[mid] or ""):
            return None
        out.append({"message_id": mid, "span": span.strip()})
    return out


def _mids(raw: Any, by_msg: Dict[str, str]) -> Optional[list]:
    if not isinstance(raw, list):
        return None
    out = []
    for m in raw:
        if not isinstance(m, str) or m not in by_msg:
            return None
        out.append(m)
    return out


def _conf(raw: Any) -> Optional[float]:
    try:
        conf = float(raw.get("confidence") if isinstance(raw, dict) else raw)
    except (TypeError, ValueError):
        conf = None
    if conf is not None and MIN_CONFIDENCE <= conf <= 1.0:
        return conf
    # Format tolerance (values, not standards): some models nest the SAME
    # attested fields inside the evidence block. The floor and range apply
    # identically; only the location is forgiven, and the forgiveness is
    # recorded nowhere because the validated output is identical either way.
    if isinstance(raw, dict) and isinstance(raw.get("evidence"), dict):
        try:
            nested = float(raw["evidence"].get("confidence"))
        except (TypeError, ValueError):
            return None
        if MIN_CONFIDENCE <= nested <= 1.0:
            return nested
    return None


def _rationale(raw: Any) -> str:
    if isinstance(raw, dict):
        top = str(raw.get("rationale") or "").strip()
        if top:
            return top[:280]
        ev = raw.get("evidence")
        if isinstance(ev, dict) and str(ev.get("rationale") or "").strip():
            return str(ev["rationale"]).strip()[:280]
    return ""


def _receipt_map(receipts: Any) -> Dict[str, str]:
    """Quotable receipt texts keyed receipt:N. Receipts are factual session
    evidence (action results that happened); checkpoints are not quotable."""
    out: Dict[str, str] = {}
    if isinstance(receipts, list):
        for i, r in enumerate(receipts[:12]):
            if isinstance(r, dict) and str(r.get("text") or "").strip():
                out[f"receipt:{i}"] = str(r.get("text"))
    return out


def validate_reconstruction(raw: Any, *, snapshot: StartSnapshot,
                            transcript: List[SessionTurn],
                            provisional_ids: set,
                            user_peer_ids: Optional[set] = None,
                            receipts: Any = None) -> tuple[dict, list]:
    """Validate a state-first proposal. Returns (validated, rejected).
    `validated` holds matters/uncertainties/attentions/suppressions/
    incidental_mids/provisional_review in normalized form. Never raises.

    `user_peer_ids`: caller-asserted identities of the user (e.g. {"ashley"}).
    An owner naming the user normalizes to "user" — identity aliasing, not
    semantic judgement (the caller, not the model, asserts who the user is)."""
    rejected: List[Dict[str, Any]] = []
    validated: dict = {"matters": [], "uncertainties": [], "attentions": [],
                       "suppressions": [], "incidental_mids": [],
                       "provisional_review": []}
    if not isinstance(raw, dict):
        return validated, [{"where": "root", "reason": "proposal_not_an_object"}]
    by_msg = {t.message_id: t.text or "" for t in transcript}
    quotable = dict(by_msg)
    quotable.update(_receipt_map(receipts))
    known_ids = {m.id for m in snapshot.matters} | set(provisional_ids or set())
    speakers = {t.speaker for t in transcript}
    start_by_id = {m.id: m for m in snapshot.matters}

    def _owner(value: Any) -> Optional[str]:
        owner = str(value or "").strip()
        if owner in OWNER_ALLOW:
            return owner
        lowered = owner.lower()
        if user_peer_ids and lowered in {str(u).lower() for u in user_peer_ids}:
            return "user"
        if owner.startswith("external:"):
            name = owner.split("external:", 1)[1].strip().lower()
            if not name:
                return None
            # Grounded actor rule (generic): the external party must have
            # spoken in this session AS an external speaker, or already own
            # start-state rows. A bare substring match against the user's own
            # speaker tag is not grounding (it would bless "external:ashley").
            if any(s.lower().startswith("external:") and name in s.lower()
                   for s in speakers):
                return owner
            if any((m.owner or "").lower() == owner.lower()
                   for m in snapshot.matters):
                return owner
            return None
        return None

    pids: Dict[str, dict] = {}
    raw_matters = raw.get("matters")
    if not isinstance(raw_matters, list):
        return validated, [{"where": "matters", "reason": "matters_not_a_list"}]
    for entry in raw_matters[:MAX_PROPOSED]:
        where = f"matters[{entry.get('pid') if isinstance(entry, dict) else '?'}]"
        if not isinstance(entry, dict):
            rejected.append({"where": where, "reason": "not_an_object"})
            continue
        pid = str(entry.get("pid") or "").strip()
        if not pid or pid in pids:
            rejected.append({"where": where, "reason": "bad_or_duplicate_pid"})
            continue
        kind = str(entry.get("kind") or "").strip()
        status = str(entry.get("status") or "").strip()
        title = str(entry.get("title") or "").strip()
        basis = str(entry.get("basis") or "").strip()
        if kind not in MATTER_KINDS or status not in MATTER_STATUS \
                or not title or basis not in ("existing", "new"):
            rejected.append({"where": where, "reason": "bad_kind_status_title_basis"})
            continue
        owner = _owner(entry.get("owner"))
        if owner is None:
            rejected.append({"where": where, "reason": "ungrounded_owner"})
            continue
        mid = str(entry.get("matter_id") or "") if basis == "existing" else ""
        if basis == "existing" and mid not in known_ids:
            if mid:
                # A non-empty but unknown id may be a mistyped link: minting
                # would duplicate, linking would misfire. Reject, don't guess.
                rejected.append({"where": where, "reason": "unknown_matter_id"})
                continue
            # Target-less "existing": the model supplied no linkable target,
            # so there is nothing to attach to — read it as establishment.
            # Mechanical reading of the model's own fields (no target given),
            # not a semantic override: evidence requirements for new
            # assertions still apply unchanged below. Flagged for audit.
            basis = "new"
            repaired_basis = True
        else:
            repaired_basis = False
        ev_raw = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
        mids = _mids(ev_raw.get("message_ids"), quotable)
        spans = _ground_spans(ev_raw.get("spans"), quotable)
        if mids is None or spans is None:
            rejected.append({"where": where, "reason": "bad_evidence"})
            continue
        start_status = ""
        if basis == "existing" and mid in start_by_id:
            start_status = start_by_id[mid].status.upper()
        asserts_change = basis == "new" or status.upper() != start_status.upper()
        if not mids and asserts_change:
            # Provenance rule: asserting CHANGE (new matter, resolution,
            # partiality, redundancy) without citing any session turn is
            # unauditable. A pure continuation (nothing changed) may cite
            # nothing — there may be no turn that touched it.
            rejected.append({"where": where, "reason": "no_transcript_provenance"})
            continue
        if asserts_change and not spans:
            rejected.append({"where": where, "reason": "change_needs_verbatim_spans"})
            continue
        via = str(entry.get("via") or "").strip()
        if status == "resolved" and via not in ("completed", "cancelled", "superseded"):
            rejected.append({"where": where, "reason": "resolved_needs_via"})
            continue
        remainder = str(entry.get("remainder") or "").strip()
        if status == "partial" and not remainder:
            rejected.append({"where": where, "reason": "partial_needs_remainder"})
            continue
        same = str(entry.get("same_as_pid") or "").strip()
        if same and same == pid:
            rejected.append({"where": where, "reason": "same_as_self"})
            continue
        subjects = entry.get("subjects")
        if subjects is None:
            subjects = []
        if not isinstance(subjects, list):
            rejected.append({"where": where, "reason": "bad_subjects"})
            continue
        clean_subjects: List[str] = []
        for s in subjects:
            if len(clean_subjects) >= MAX_SUBJECTS:
                break
            if not isinstance(s, str):
                continue
            name = s.strip()[:SUBJECT_CAP]
            if name and name not in clean_subjects:
                clean_subjects.append(name)
        sup_by = str(entry.get("superseded_by_pid") or "").strip()
        if sup_by and sup_by == pid:
            rejected.append({"where": where, "reason": "superseded_by_self"})
            continue
        conf = _conf(entry)
        if conf is None:
            rejected.append({"where": where, "reason": "confidence_below_floor"})
            continue
        if status == "redundant" and basis != "existing":
            rejected.append({"where": where, "reason": "redundant_needs_existing"})
            continue
        pids[pid] = {"pid": pid, "kind": kind, "title": title[:280],
                     "status": status, "owner": owner, "basis": basis,
                     "matter_id": mid, "via": via, "remainder": remainder[:280],
                     "same_as_pid": same, "superseded_by_pid": sup_by,
                     "repaired_basis": repaired_basis,
                     "subjects": clean_subjects,
                     "follow_up": str(entry.get("follow_up") or "")[:280],
                     "evidence": {"message_ids": mids, "spans": spans},
                     "confidence": conf,
                     "rationale": _rationale(entry)}
    for pid, same in [(p["pid"], p["same_as_pid"]) for p in pids.values()]:
        if same and same not in pids:
            rejected.append({"where": f"matters[{pid}]",
                             "reason": "same_as_unknown_pid"})
            pids[pid]["same_as_pid"] = ""
    for pid, sup in [(p["pid"], p["superseded_by_pid"]) for p in pids.values()]:
        if sup and sup not in pids:
            rejected.append({"where": f"matters[{pid}]",
                             "reason": "superseded_by_unknown_pid"})
            pids[pid]["superseded_by_pid"] = ""
    validated["matters"] = list(pids.values())

    def _linked(items: Any) -> Optional[list]:
        """Resolve related refs: known uuids kept; proposed pids resolved to
        their matter_id when existing-basis, else kept as new:<pid> note."""
        if items is None:
            return []
        if not isinstance(items, list):
            return None
        out = []
        for item in items[:6]:
            s = str(item or "").strip()
            if s in known_ids:
                out.append(s)
            elif s in pids and pids[s]["matter_id"]:
                out.append(pids[s]["matter_id"])
            elif s in pids:
                out.append(f"new:{s}")
        return out

    for section in ("uncertainties", "attentions"):
        items = raw.get(section)
        if items is None:
            continue
        if not isinstance(items, list):
            rejected.append({"where": section, "reason": "not_a_list"})
            continue
        for i, entry in enumerate(items[:8]):
            where = f"{section}[{i}]"
            if not isinstance(entry, dict):
                rejected.append({"where": where, "reason": "not_an_object"})
                continue
            content = str(entry.get("content") or "").strip()
            if not content:
                rejected.append({"where": where, "reason": "empty_content"})
                continue
            ev_raw = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
            mids = _mids(ev_raw.get("message_ids"), quotable)
            spans = _ground_spans(ev_raw.get("spans"), quotable)
            if mids is None or spans is None:
                rejected.append({"where": where, "reason": "bad_evidence"})
                continue
            linked = _linked(entry.get("related_pids",
                                       entry.get("related_ids")))
            if linked is None:
                rejected.append({"where": where, "reason": "bad_related"})
                continue
            # Generic grounding rule: verbatim spans, OR a link to a proposed
            # or existing matter plus cited transcript provenance.
            if not spans and not ([r for r in linked if not r.startswith("new:")] or
                                  [p for p in (entry.get("related_pids") or []) if p in pids]):
                rejected.append({"where": where, "reason": "ungrounded_no_spans_no_link"})
                continue
            conf = _conf(entry)
            if conf is None:
                rejected.append({"where": where, "reason": "confidence_below_floor"})
                continue
            item = {"content": content[:500], "related": linked,
                    "evidence": {"message_ids": mids, "spans": spans},
                    "confidence": conf,
                    "rationale": _rationale(entry)}
            if section == "uncertainties":
                alts = [str(a)[:160] for a in (entry.get("alternatives") or [])
                        if str(a or "").strip()][:4]
                item["alternatives"] = alts
            validated[section].append(item)

    supps = raw.get("suppressions")
    if supps is not None:
        if not isinstance(supps, list):
            rejected.append({"where": "suppressions", "reason": "not_a_list"})
        for i, entry in enumerate(supps[:6]):
            where = f"suppressions[{i}]"
            if not isinstance(entry, dict):
                rejected.append({"where": where, "reason": "not_an_object"})
                continue
            topic = str(entry.get("topic_or_entity") or "").strip()
            reason = str(entry.get("reason") or "").strip()
            if not topic or not reason:
                rejected.append({"where": where, "reason": "bad_suppress"})
                continue
            ev_raw = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
            mids = _mids(ev_raw.get("message_ids"), quotable)
            spans = _ground_spans(ev_raw.get("spans"), quotable)
            if not mids or not spans:
                rejected.append({"where": where, "reason": "suppress_needs_spans"})
                continue
            conf = _conf(entry)
            if conf is None:
                rejected.append({"where": where, "reason": "confidence_below_floor"})
                continue
            validated["suppressions"].append(
                {"topic_or_entity": topic[:160], "reason": reason[:280],
                 "evidence": {"message_ids": mids, "spans": spans},
                 "confidence": conf,
                 "rationale": _rationale(entry)})

    inc = raw.get("incidental_mids")
    if inc is not None:
        mids = _mids(inc, by_msg)
        if mids is None:
            rejected.append({"where": "incidental_mids",
                             "reason": "unknown_message_ids"})
        else:
            validated["incidental_mids"] = mids

    rev = raw.get("provisional_review")
    if rev is not None:
        if not isinstance(rev, list):
            rejected.append({"where": "provisional_review", "reason": "not_a_list"})
        for entry in rev:
            if not isinstance(entry, dict):
                rejected.append({"where": "provisional_review",
                                 "reason": "not_an_object"})
                continue
            mid = str(entry.get("matter_id") or "")
            verdict = str(entry.get("verdict") or "").strip()
            if mid not in provisional_ids or verdict not in PROVISIONAL_VERDICTS:
                rejected.append({"where": "provisional_review",
                                 "reason": "bad_review_target"})
                continue
            conf = _conf(entry)
            if conf is None:
                rejected.append({"where": "provisional_review",
                                 "reason": "confidence_below_floor"})
                continue
            validated["provisional_review"].append(
                {"matter_id": mid, "verdict": verdict,
                 "reason": str(entry.get("reason") or "")[:280],
                 "confidence": conf})
    if isinstance(raw_matters, list) and len(raw_matters) > MAX_PROPOSED:
        rejected.append({"where": "matters", "reason": f"capped_at_{MAX_PROPOSED}"})
    return validated, rejected


def translate_to_ops(validated: dict, *, start_by_id: Dict[str, SnapshotMatter],
                     pid_to_uuid: Dict[str, str]) -> tuple[list, list]:
    """Deterministic diff: proposed canonical state -> V1 op vocabulary plus
    discard marks for redundant rows. The model never emits imperative ops;
    code computes the delta. Returns (ops, discards)."""
    ops: List[ValidatedOp] = []
    discards: List[Dict[str, Any]] = []

    def _status_of(mid: str) -> str:
        m = start_by_id.get(mid)
        return (m.status if m else "").upper()

    def _resolve_pid(pid: str) -> str:
        if pid in pid_to_uuid:
            return pid_to_uuid[pid]
        return ""

    for m in validated.get("matters", []):
        ev = m["evidence"]
        conf, rat = m["confidence"], m["rationale"]
        if m["status"] == "redundant":
            sup = _resolve_pid(m.get("superseded_by_pid") or "")
            discards.append({"matter_id": m.get("matter_id", ""),
                             "reason": rat, "superseded_by": sup,
                             "confidence": conf})
            continue
        if m["basis"] == "existing":
            mid = m.get("matter_id", "")
            start_status = _status_of(mid)
            new_status = m["status"].upper()
            changed = (new_status != start_status
                       and not (not start_status and new_status == "OPEN"))
            if m.get("same_as_pid") and m["same_as_pid"] in pid_to_uuid:
                ops.append(ValidatedOp(
                    op="same_as",
                    data={"matter_id_a": mid,
                          "matter_id_b": pid_to_uuid[m["same_as_pid"]],
                          "evidence": ev},
                    confidence=conf, rationale=rat))
            if not changed:
                ops.append(ValidatedOp(op="affirm_matter",
                                       data={"matter_id": mid},
                                       confidence=conf, rationale=rat))
            elif new_status == "RESOLVED":
                ops.append(ValidatedOp(
                    op="resolve_matter",
                    data={"matter_id": mid, "via": m.get("via") or "completed",
                          "evidence": ev},
                    confidence=conf, rationale=rat))
            elif new_status == "PARTIAL":
                ops.append(ValidatedOp(
                    op="partial_fulfilment",
                    data={"matter_id": mid, "evidence": ev,
                          "remainder": m.get("remainder", "")},
                    confidence=conf, rationale=rat))
            elif new_status == "UNCERTAIN":
                ops.append(ValidatedOp(
                    op="uncertainty",
                    data={"content": f"{m['title']} — status uncertain",
                          "alternatives": [], "related_ids": [mid],
                          "evidence": ev},
                    confidence=conf, rationale=rat))
            else:  # reopened or re-asserted open: affirm carries it
                ops.append(ValidatedOp(op="affirm_matter",
                                       data={"matter_id": mid},
                                       confidence=conf, rationale=rat))
        else:
            data = {"title": m["title"], "matter_kind": m["kind"],
                    "evidence": ev, "owner": m["owner"],
                    "subjects": list(m.get("subjects") or [])}
            if m["status"] == "partial":
                # Establishment with partiality: the remainder is the point
                # (e.g. a newly established debt already partly paid). Carry
                # status + remainder on the creation proposal itself, since
                # there is no existing row to attach a partial op to.
                data["status"] = "partial"
                data["remainder"] = m["remainder"]
            ops.append(ValidatedOp(op="new_matter", data=data,
                                   confidence=conf, rationale=rat))
        if m.get("follow_up"):
            related = ([m["matter_id"]] if m["matter_id"] else [])
            ops.append(ValidatedOp(
                op="attend",
                data={"content": m["follow_up"], "related_ids": related,
                      "evidence": {"message_ids": ev["message_ids"],
                                   "spans": []}},
                confidence=conf, rationale=rat))
    for u in validated.get("uncertainties", []):
        ops.append(ValidatedOp(
            op="uncertainty",
            data={"content": u["content"],
                  "alternatives": u.get("alternatives", []),
                  "related_ids": [r for r in u["related"]
                                  if not r.startswith("new:")],
                  "evidence": u["evidence"]},
            confidence=u["confidence"], rationale=u["rationale"]))
    for a in validated.get("attentions", []):
        ops.append(ValidatedOp(
            op="attend",
            data={"content": a["content"],
                  "related_ids": [r for r in a["related"]
                                  if not r.startswith("new:")],
                  "evidence": a["evidence"]},
            confidence=a["confidence"], rationale=a["rationale"]))
    for s in validated.get("suppressions", []):
        ops.append(ValidatedOp(
            op="suppress",
            data={"topic_or_entity": s["topic_or_entity"],
                  "reason": s["reason"], "evidence": s["evidence"]},
            confidence=s["confidence"], rationale=s["rationale"]))
    for mid in validated.get("incidental_mids", []):
        ops.append(ValidatedOp(op="incidental",
                               data={"message_ids": [mid]},
                               confidence=0.9, rationale="model-marked incidental"))
    return ops, discards


@dataclass
class V2Result:
    accepted: List[ValidatedOp] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    discards: List[Dict[str, Any]] = field(default_factory=list)
    provisional_marks: List[Dict[str, Any]] = field(default_factory=list)
    would_apply: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    error: str = ""
    prompt_chars: int = 0
    latency_s: float = 0.0
    retries: int = 0


def segment_transcript(turns: List[SessionTurn]) -> List[List[SessionTurn]]:
    """Deterministic packing of a long session into bounded raw windows.

    Purely mechanical (turn count + char budget, order preserved): no
    semantic selection, so no turn is ever silently judged irrelevant.
    Every turn lands in exactly one segment; raw text stays authoritative
    and every op cites the real turn it came from."""
    segments: List[List[SessionTurn]] = []
    current: List[SessionTurn] = []
    used = 0
    for t in turns:
        chunk_len = len(f"[msg:{t.message_id}] {t.speaker}: {(t.text or '').strip()}")
        if current and (len(current) >= MAX_TURNS or used + chunk_len > TRANSCRIPT_CHAR_CAP):
            segments.append(current)
            current = []
            used = 0
        current.append(t)
        used += chunk_len
    if current:
        segments.append(current)
    return segments


async def consolidate_long_session(
    db: Any,
    *,
    workspace_id: str,
    session_id: str,
    transcript: List[SessionTurn] | List[Dict[str, Any]],
    start_snapshot: Optional[StartSnapshot] = None,
    adapter: Any = ...,
    model_id: Optional[str] = None,
    max_tokens: int = 4000,
    user_peer_id: Optional[str] = None,
    temporal_session_id: Optional[str] = None,
    checkpoints: Optional[List[Dict[str, Any]]] = None,
    receipts: Optional[List[Dict[str, Any]]] = None,
    mode: str = "shadow",
) -> Dict[str, Any]:
    """Long-session orchestration over sequential bounded windows.

    Apply mode: reconstruct segment -> apply -> refresh authoritative
    snapshot -> next segment sees applied rows as start state (no
    re-minting, no extra machinery). Shadow mode: no mutations; earlier
    segments' accepted proposals travel as `prior_proposals` context so
    later windows build instead of duplicating. Caps at MAX_SEGMENTS
    windows with explicit coverage accounting — the remainder is reported
    dropped, never silently absorbed into a summary."""
    from src.services.session_apply import apply_enabled, apply_reconstruction

    turns = [t if isinstance(t, SessionTurn) else SessionTurn(
        message_id=str(t.get("message_id") or ""),
        speaker=str(t.get("speaker") or ""),
        text=str(t.get("text") or "")) for t in (transcript or [])]
    turns = [t for t in turns if t.message_id and (t.text or "").strip()]
    segments = segment_transcript(turns)
    truncated = len(segments) > MAX_SEGMENTS
    segments = segments[:MAX_SEGMENTS]
    aggregate: Dict[str, Any] = {
        "accepted": [], "rejected": [], "discards": [],
        "provisional_marks": [], "would_apply": [],
        "applied": [], "deferred": [],
        "segment_reports": [], "prompt_chars": 0, "latency_s": 0.0,
        "summaries": [], "error": "",
    }
    coverage = {"complete": not truncated, "segments": len(segments),
                "turns_in": sum(len(s) for s in segments),
                "turns_total": len(turns),
                "turns_dropped": len(turns) - sum(len(s) for s in segments),
                "window": {"turns": MAX_TURNS, "chars": TRANSCRIPT_CHAR_CAP}}
    if not turns:
        aggregate["coverage"] = coverage
        return aggregate
    if start_snapshot is None:
        start_snapshot = await capture_snapshot(
            db, workspace_id=workspace_id, session_id=session_id)
    snapshot = start_snapshot
    prior_proposals: List[Dict[str, Any]] = []
    can_apply = mode == "apply"
    for i, seg in enumerate(segments):
        result = await reconstruct_session(
            db, workspace_id=workspace_id, session_id=session_id,
            transcript=seg, start_snapshot=snapshot, adapter=adapter,
            model_id=model_id, max_tokens=max_tokens,
            user_peer_id=user_peer_id,
            temporal_session_id=temporal_session_id,
            checkpoints=checkpoints, receipts=receipts,
            prior_proposals=prior_proposals if i > 0 else None,
            trace_suffix=f"seg{i}" if len(segments) > 1 else "")
        aggregate["prompt_chars"] += result.prompt_chars
        aggregate["latency_s"] = round(aggregate["latency_s"] + result.latency_s, 2)
        aggregate["summaries"].append(result.summary)
        if result.error:
            aggregate["error"] = aggregate["error"] or result.error
            aggregate["segment_reports"].append(
                {"segment": i, "turns": len(seg), "error": result.error})
            continue
        aggregate["accepted"].extend(
            [{"op": o.op, "data": o.data, "confidence": o.confidence,
              "rationale": o.rationale} for o in result.accepted])
        aggregate["rejected"].extend(result.rejected)
        aggregate["discards"].extend(result.discards)
        aggregate["provisional_marks"].extend(result.provisional_marks)
        aggregate["would_apply"].extend(result.would_apply)
        seg_applied: list = []
        seg_deferred: list = []
        if can_apply and apply_enabled():
            report = await apply_reconstruction(
                db, workspace_id=workspace_id, session_id=session_id,
                result=result, user_peer_id=user_peer_id or "user",
                temporal_session_id=temporal_session_id)
            seg_applied = report["applied"]
            seg_deferred = report["deferred"]
            aggregate["applied"].extend(seg_applied)
            aggregate["deferred"].extend(seg_deferred)
            snapshot = await capture_snapshot(
                db, workspace_id=workspace_id, session_id=session_id)
        else:
            titles_by_id = {m.id: (m.title or "") for m in
                            (snapshot.matters if snapshot else [])}
            for o in result.accepted:
                title = str((o.data.get("title") or o.data.get("content")
                             or o.data.get("topic_or_entity") or ""))[:120]
                if not title:
                    mid = (o.data.get("matter_id") or o.data.get("expectation_id")
                           or o.data.get("matter_id_a") or "")
                    title = titles_by_id.get(str(mid), "")[:120]
                if title:
                    prior_proposals.append({"op": o.op, "title": title})
        aggregate["segment_reports"].append(
            {"segment": i, "turns": len(seg), "accepted": len(result.accepted),
             "applied": len(seg_applied), "deferred": len(seg_deferred),
             "error": ""})
    aggregate["coverage"] = coverage
    return aggregate


async def reconstruct_session(
    db: Any,
    *,
    workspace_id: str,
    session_id: str,
    transcript: List[SessionTurn] | List[Dict[str, Any]],
    start_snapshot: Optional[StartSnapshot] = None,
    adapter: Any = ...,
    model_id: Optional[str] = None,
    max_tokens: int = 4000,
    user_peer_id: Optional[str] = None,
    temporal_session_id: Optional[str] = None,
    checkpoints: Optional[List[Dict[str, Any]]] = None,
    receipts: Optional[List[Dict[str, Any]]] = None,
    prior_proposals: Optional[List[Dict[str, Any]]] = None,
    trace_suffix: str = "",
) -> V2Result:
    """Evidence-first session reconstruction, SHADOW ONLY.

    Identity contract: `session_id` is the STABLE durable lane — every DB
    read/write in this call scopes to it, so reconstructed state lands in
    the same namespace the live system reads next session. The temporal
    session id (this conversation's boundary) travels separately as
    `temporal_session_id` and is used ONLY for provenance (traces, run
    ledger, created-row message ids), never for state scoping.
    Checkpoints are navigation-only (never evidence); receipts are factual
    quotable evidence. `prior_proposals` carries earlier-segment titles so
    long sessions do not re-mint across segments."""
    """Evidence-first session reconstruction, SHADOW ONLY. Validates the
    canonical proposal, diffs to ops, reports would-apply. Mutates nothing
    except one audit trace. Any failure holds existing state for retry."""
    import time

    from src.models.operational_state import ExtractionTrace
    from src.services import semantic_judge
    from src.services.session_consolidation import consolidation_enabled

    t0 = time.time()
    result = V2Result()
    turns = [t if isinstance(t, SessionTurn) else SessionTurn(
        message_id=str(t.get("message_id") or ""),
        speaker=str(t.get("speaker") or ""),
        text=str(t.get("text") or "")) for t in (transcript or [])]
    turns = [t for t in turns if t.message_id and (t.text or "").strip()]
    if not consolidation_enabled():
        result.error = "disabled"
        return result
    if not turns:
        result.summary = "empty session: no change, raw evidence retained"
        return result
    if start_snapshot is None:
        start_snapshot = await capture_snapshot(
            db, workspace_id=workspace_id, session_id=session_id)
    session_mids = {t.message_id for t in turns}
    provisional = await capture_session_created(
        db, workspace_id=workspace_id, session_mids=session_mids)
    provisional_ids = {m.id for m in provisional}
    prompt = build_reconstruction_prompt(
        start_snapshot, turns, provisional, user_peer_id=user_peer_id,
        checkpoints=checkpoints, receipts=receipts,
        prior_proposals=prior_proposals)
    result.prompt_chars = len(prompt)
    provenance_tag = temporal_session_id or session_id
    # Per-segment trace keys: the (workspace, message, stage, item_key)
    # ledger is unique, so sequential windows of one boundary must not
    # share a key or all but the first trace is lost to the constraint.
    trace_tag = (f"{provenance_tag}:{trace_suffix}" if trace_suffix
                 else provenance_tag)

    async def _trace(status: str, detail: Dict[str, Any]) -> None:
        try:
            db.add(ExtractionTrace(
                honcho_workspace_id=workspace_id,
                honcho_session_id=session_id,
                honcho_message_id=f"reconstruction:{trace_tag}",
                stage="session_reconstruction",
                item_key=f"reconstruction:{trace_tag}",
                status=status,
                model=(model_id or semantic_judge.judge_model_id()),
                detail_json=json.dumps({**detail,
                                        "temporal_session_id": temporal_session_id or "",
                                        "lane_session_id": session_id}, default=str)[:4000],
            ))
            await db.commit()
        except Exception as err:
            logger.warning("reconstruction trace failed: %s", err)
            try:
                await db.rollback()
            except Exception:
                pass

    if adapter is ...:
        adapter = semantic_judge._adapter()
    if adapter is None:
        result.error = "no_adapter"
        result.summary = "no model available: existing state holds, retry later"
        await _trace("error", {"error": result.error})
        return result
    mid = model_id or semantic_judge.judge_model_id()
    schema = {
        "type": "object",
        "properties": {
            "session_summary": {"type": "string"},
            "matters": {
                "type": "array", "maxItems": MAX_PROPOSED,
                "items": {
                    "type": "object",
                    "properties": {
                        "pid": {"type": "string"},
                        "kind": {"type": "string"},
                        "title": {"type": "string"},
                        "status": {"type": "string"},
                        "owner": {"type": "string"},
                        "basis": {"type": "string"},
                        "matter_id": {"type": "string"},
                        "via": {"type": "string"},
                        "remainder": {"type": "string"},
                        "same_as_pid": {"type": "string"},
                        "subjects": {"type": "array",
                                     "items": {"type": "string"}},
                        "follow_up": {"type": "string"},
                        "confidence": {"type": "number"},
                        "rationale": {"type": "string"},
                        "evidence": {"type": "object"},
                    },
                    "required": ["pid", "kind", "title", "status", "owner",
                                 "basis", "confidence", "rationale", "evidence"],
                    "additionalProperties": True,
                },
            },
            "uncertainties": {"type": "array", "maxItems": 8, "items": {
                "type": "object",
                "required": ["content", "confidence", "rationale", "evidence"],
                "additionalProperties": True}},
            "attentions": {"type": "array", "maxItems": 8, "items": {
                "type": "object",
                "required": ["content", "confidence", "rationale", "evidence"],
                "additionalProperties": True}},
            "suppressions": {"type": "array", "maxItems": 6, "items": {
                "type": "object",
                "required": ["topic_or_entity", "reason", "confidence",
                             "rationale", "evidence"],
                "additionalProperties": True}},
            "incidental_mids": {"type": "array", "items": {"type": "string"}},
            "provisional_review": {"type": "array", "maxItems": 12,
                                   "items": {"type": "object"}},
        },
        "required": ["session_summary", "matters"],
        "additionalProperties": False,
    }
    raw: Any = None
    responded = False
    call_error = ""
    for attempt in range(3):
        try:
            raw = await adapter.generate_structured(
                system=(
                    "You are a session reconstructor for a companion-memory system. "
                    "Propose the durable state implied by the whole session's evidence. "
                    "Conservative: fewer matters over guessing. Never invent facts, "
                    "people, amounts, message IDs, or matter IDs."
                ),
                prompt=prompt, json_schema=schema, model_id=mid,
                max_tokens=max_tokens, temperature=0.0, strict=True)
        except Exception as exc:
            logger.warning("reconstruction call failed (attempt %d, fail-open): %s",
                           attempt, exc)
            # Normal transport retry: one extra attempt on exception, then hold.
            # Record only the exception class (operability without content).
            call_error = type(exc).__name__
            result.retries += 1
            raw = None
            if attempt >= 1:
                break
            continue
        if isinstance(raw, dict):
            responded = True
        if isinstance(raw, dict) and isinstance(raw.get("matters"), list):
            break
        logger.warning("reconstruction malformed (attempt %d), retrying once", attempt)
        result.retries += 1
        raw = None
        if attempt >= 1:
            break
    result.latency_s = round(__import__("time").time() - t0, 2)
    if not isinstance(raw, dict) or not isinstance(raw.get("matters"), list):
        result.error = "malformed" if responded else "call_failed"
        result.summary = "model unavailable or invalid: existing state holds, retry later"
        await _trace("error", {"error": result.error, "retries": result.retries,
                               "call_error": call_error})
        return result
    result.summary = str(raw.get("session_summary") or "")[:500]
    validated, rejected = validate_reconstruction(
        raw, snapshot=start_snapshot, transcript=turns,
        provisional_ids=provisional_ids,
        user_peer_ids={user_peer_id} if user_peer_id else None,
        receipts=receipts)
    result.rejected = rejected
    start_by_id = {m.id: m for m in start_snapshot.matters}
    pid_to_uuid = {p["pid"]: p["matter_id"] for p in validated["matters"]
                   if p["matter_id"]}
    ops, discards = translate_to_ops(validated, start_by_id=start_by_id,
                                     pid_to_uuid=pid_to_uuid)
    result.accepted = ops
    result.discards = discards
    for entry in validated["provisional_review"]:
        target_ok = entry["matter_id"] in provisional_ids
        result.provisional_marks.append({**entry, "would_apply": target_ok,
                                         "reason": "target_session_created"
                                         if target_ok else "target_not_provisional"})
    for d in discards:
        d["would_apply"] = d["matter_id"] in {m.id for m in start_snapshot.matters}
        d["would_reason"] = "target_present_for_review" if d["would_apply"] \
            else "target_missing"
    if not result.accepted and not result.rejected and not result.error:
        await _trace("held_empty", {"summary": result.summary})
    else:
        try:
            result.would_apply = await check_would_apply(
                db, workspace_id=workspace_id, accepted=result.accepted)
        except Exception as err:
            logger.warning("would-apply check failed: %s", err)
            result.would_apply = []
        await _trace("shadow", {
            "summary": result.summary,
            "accepted": [(o.op, o.data) for o in result.accepted],
            "rejected": rejected,
            "discards": result.discards,
            "provisional_marks": result.provisional_marks,
            "would_apply": result.would_apply,
        })
    return result
