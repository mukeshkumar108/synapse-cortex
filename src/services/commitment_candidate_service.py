"""Commitment candidate lifecycle: derived, fallible, bounded.

The watcher proposes; this service stores the proposal as derived state; the
app (authority gate or the user via 'Sophie noticed') promotes or dismisses.
Deterministic guarantees:
- candidate_key is stable per (workspace, owner, message, observation) so
  redelivery/replay can never duplicate a candidate;
- canonical_key is the normalized-commitment identity, so a dismissal is
  durable against re-proposal of the same commitment;
- pending candidates expire (bounded intelligence, not a backlog).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commitment_candidate import (
    CommitmentCandidate,
    CommitmentCandidateAuthority,
    CommitmentCandidateStatus,
    utc_now,
)
from src.models.operational_state import TurnStamp
from src.schemas.candidate import ExtractionCandidate
from src.services.ownership import is_external_counterparty
from src.services.semantic_promotion import promote_transition

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")
_REPORTED_FUTURE_RE = re.compile(
    r"\b(?:said|says|told|promised|confirmed)\b.{0,100}"
    r"\b(?:he|she|they)\s*(?:['’]d|would|will)\b",
    re.IGNORECASE,
)
# Deterministic floor for granting ACT authority to an "implicit self
# commitment" reading: the evidence must contain the sender speaking of
# their OWN future action, not a third party's ("Sam said he'd send it",
# "Andree needs the school money") wrongly inferred into the sender's own
# obligation. This mirrors the same modal-verb self-reference family already
# used elsewhere in this codebase (expectation title cleaning, counterparty
# reported-future detection) — a narrow grammatical-attribution check, not a
# semantic-identity/merge decision.
_FIRST_PERSON_COMMITMENT_RE = re.compile(
    r"\bi(?:'m| am| have| need| should| must| will| promise|'ll|'d|'ve)\b",
    re.IGNORECASE,
)


def _has_first_person_commitment_marker(text: str) -> bool:
    return bool(_FIRST_PERSON_COMMITMENT_RE.search(text or ""))
_STOPWORDS = {
    "about", "after", "again", "also", "been", "could", "from", "have",
    "into", "just", "that", "their", "them", "then", "there", "they",
    "this", "what", "when", "where", "which", "with", "would", "your",
    "should", "need", "want", "maybe", "probably", "really", "actually",
    "soon", "someday", "sometime", "asap",
}


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "edly", "ed", "ly", "es", "al", "s")


def _fold(word: str) -> str:
    """Tiny deterministic suffix folder so 'renew'/'renewal' and
    'book'/'booking' share a canonical identity. Deliberately conservative:
    it only ever merges near-identical content words."""
    for suffix in _SUFFIXES:
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def canonical_key_for(title: str) -> str:
    """Normalized-commitment identity: content tokens of the canonical title,
    order-independent, lightly stemmed. Deterministic across paraphrases that
    keep the same content words; different words yield different keys
    (deliberate: a wrong merge is worse than a duplicate proposal)."""
    words = _WORD_RE.findall(title.lower())
    content = sorted({_fold(w) for w in words if len(w) >= 3 and w not in _STOPWORDS})
    if not content:
        content = sorted({_fold(w) for w in _WORD_RE.findall(title.lower())}) or ["unknown"]
    return hashlib.sha1(":".join(content).encode()).hexdigest()


def _is_reported_counterparty(
    candidate: ExtractionCandidate, *, owner_peer_id: str, evidence: str
) -> bool:
    """Recognise a promise attributed to a third party in a user's turn.

    Ownership intentionally refuses unknown actor ids and falls back to the
    sender. At this boundary the original actor attribution is still present,
    so a reported third-party promise can remain evidence without inheriting
    the sender's action authority. Known companion promises are unaffected:
    their resolved owner matches the attributed actor.
    """
    actor = (candidate.actor_peer_id or "").strip().casefold()
    owner = owner_peer_id.strip().casefold()
    actor_is_distinct = actor not in {
        "", owner, "user", "assistant", "system", "unknown", "nobody"
    }
    reported = bool(
        candidate.is_reported_speech
        or candidate.epistemic_provenance == "reported_statement"
        or _REPORTED_FUTURE_RE.search(evidence)
    )
    return actor_is_distinct and reported


async def _confirm_self_undertaking(evidence: str, *, owner_peer_id: str) -> bool:
    """Semantic actor attribution for the gray zone the deterministic marker
    cannot safely resolve: indirect self-commitment ("leave it with me"),
    named-self reference, quoted/reported text that happens to contain a
    marker, and languages/phrasings with no English first-person token at
    all. Owner identity is passed as CONTEXT (structured data already
    available, not a name special-case) so a named-self formulation can be
    recognised generically for whichever peer it is.

    Fails CLOSED (False = do not confirm) on any unavailability or
    non-'yes' verdict: this only ever gates whether ACT authority is
    GRANTED, and ASK is the safe state pending better evidence — never
    interrogates the user over it (Canon §2.12: uncertainty is held
    privately, not escalated by default)."""
    try:
        from src.services import semantic_judge
        adapter = semantic_judge._adapter()
        if adapter is None:
            return False
        result = await semantic_judge.adjudicate(
            kind="self_undertaking",
            earlier="the message's own sender",
            later=evidence,
            context=f"The message sender's own identifying name or alias is '{owner_peer_id}'.",
            adapter=adapter,
        )
    except Exception as err:
        logger.warning("self-undertaking judge check failed (fail-closed to ASK): %s", err)
        return False
    return result.accepted


class CommitmentCandidateService:
    async def upsert_from_candidate(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        session_id: str,
        owner_peer_id: str,
        message_id: str,
        candidate: ExtractionCandidate,
        now: datetime,
        frame: Optional[str] = None,
    ) -> Optional[CommitmentCandidate]:
        title = (candidate.canonical_title or candidate.observation or "").strip()
        if not title:
            return None
        candidate_key = hashlib.sha1(
            f"{workspace_id}:{owner_peer_id}:{message_id}:{candidate.candidate_key}".encode()
        ).hexdigest()
        canonical_key = canonical_key_for(title)
        evidence = (
            candidate.raw_evidence
            or candidate.observation
            or ""
        ).strip()[:2000]
        is_counterparty = (
            is_external_counterparty(owner_peer_id)
            or candidate.evidence_class == "counterparty_promise"
            or _is_reported_counterparty(
                candidate, owner_peer_id=owner_peer_id, evidence=evidence
            )
        )
        # Authority floor for an "implicit self commitment" reading: WHO
        # actually undertakes this action? A first-person marker
        # ("I'll"/"I need to"/...) is a cheap, hard-boundary guard for the
        # common, unambiguous case — it never runs a model call when the
        # sender plainly speaks of their own future action. It is NOT
        # semantic authority: it is defeated by quotation/reported-speech
        # (a quoted "I'll send it" is not the sender's own commitment — B6),
        # and it cannot recognise indirect self-commitment ("leave it with
        # me"), named-self reference ("Mukesh will sort it" when Mukesh IS
        # the sender), or genuinely absent commitment ("Andree ... needs the
        # school money" — no promise by anyone). Those genuinely ambiguous
        # or indirect shapes are resolved by the semantic judge
        # ("self_undertaking"), using owner identity as structured context
        # rather than a name special-case; the marker only ever SKIPS that
        # call when it already agrees, it never overrides a judge verdict.
        # Fails CLOSED to ASK (the safer state: ACT is what can later
        # VIOLATE) whenever nothing confirms the sender as the actor —
        # no judge available, judge unclear/no, or nothing to check with.
        resolved_model_authority = candidate.authority if candidate.authority in ("act", "ask") else None
        marker_defeated = bool(
            candidate.is_quoted
            or candidate.is_reported_speech
            or candidate.epistemic_provenance == "reported_statement"
        )
        needs_actor_check = (
            not is_counterparty
            and resolved_model_authority == "act"
            and (candidate.evidence_class or "implicit_self_commitment") == "implicit_self_commitment"
            and (marker_defeated or not _has_first_person_commitment_marker(evidence))
        )
        if needs_actor_check and not await _confirm_self_undertaking(
            evidence, owner_peer_id=owner_peer_id,
        ):
            resolved_model_authority = "ask"

        existing_canonical = (
            await db.execute(
                select(CommitmentCandidate).where(
                    CommitmentCandidate.honcho_workspace_id == workspace_id,
                    CommitmentCandidate.owner_peer_id == owner_peer_id,
                    CommitmentCandidate.canonical_key == canonical_key,
                    CommitmentCandidate.status.in_([
                        CommitmentCandidateStatus.PENDING,
                        CommitmentCandidateStatus.MATERIALIZED,
                        CommitmentCandidateStatus.DISMISSED,
                    ]),
                )
            )
        ).scalars().first()

        if existing_canonical is not None:
            # Durable dismissal: the same normalized commitment is never
            # re-proposed after the user dismissed it.
            if existing_canonical.status == CommitmentCandidateStatus.DISMISSED:
                return None
            # External first-person language belongs to the external sender,
            # not to the user or companion. Keep the evidence longitudinally
            # visible as an ASK candidate, but never let extractor output or a
            # later corroboration pass promote it into our actionable lane.
            if is_counterparty:
                existing_canonical.evidence_class = "counterparty_promise"
                existing_canonical.authority = CommitmentCandidateAuthority.ASK
            # Replay/redelivery of the same observation: idempotent no-op.
            if existing_canonical.candidate_key == candidate_key:
                if is_counterparty:
                    db.add(existing_canonical)
                    await db.commit()
                return existing_canonical
            if existing_canonical.status == CommitmentCandidateStatus.MATERIALIZED:
                return None
            # A later, fresh observation of the same commitment refreshes the
            # pending candidate's evidence rather than duplicating it.
            existing_canonical.evidence_verbatim = evidence or existing_canonical.evidence_verbatim
            existing_canonical.source_message_id = message_id
            existing_canonical.updated_at = _now_naive()
            # Corroboration promotion: explicit authority or an explicit
            # command/acceptance/resolution class on re-observation promotes
            # ASK -> ACT. Repetition alone never promotes.
            if (
                not is_counterparty
                and existing_canonical.authority != CommitmentCandidateAuthority.ACT
                and (
                    resolved_model_authority == "act"
                    or (candidate.evidence_class or "") in (
                        "explicit_command", "explicit_acceptance",
                        "explicit_resolution", "explicit_modification",
                    )
                )
            ):
                existing_canonical.authority = CommitmentCandidateAuthority.ACT
                existing_canonical.resolution_evidence = (
                    f"promoted:corroborated:{message_id}#"
                    f"{candidate.candidate_key}"
                )
            db.add(existing_canonical)
            await db.commit()
            return existing_canonical

        if not is_counterparty:
            same_matter = await self._find_same_matter_commitment(
                db, workspace_id=workspace_id, session_id=session_id,
                owner_peer_id=owner_peer_id, candidate=candidate, frame=frame,
                message_id=message_id,
            )
            if same_matter is not None:
                # Attach: one real-world obligation accumulates evidence
                # rather than multiplying active representations of itself.
                # Append (never overwrite) — distinct from the exact-
                # canonical-key refresh above, which is a paraphrase-free
                # re-observation of the identical title; here the wording
                # genuinely differs, so the earlier evidence stays legible.
                if evidence and evidence not in (same_matter.evidence_verbatim or ""):
                    same_matter.evidence_verbatim = (
                        f"{same_matter.evidence_verbatim}\n---\n{evidence}"
                    )[-4000:]
                same_matter.source_message_id = message_id
                same_matter.updated_at = _now_naive()
                if (
                    same_matter.authority != CommitmentCandidateAuthority.ACT
                    and (
                        resolved_model_authority == "act"
                        or (candidate.evidence_class or "") in (
                            "explicit_command", "explicit_acceptance",
                            "explicit_resolution", "explicit_modification",
                        )
                    )
                ):
                    same_matter.authority = CommitmentCandidateAuthority.ACT
                    same_matter.resolution_evidence = (
                        f"promoted:same_matter_corroborated:{message_id}#"
                        f"{candidate.candidate_key}"
                    )
                db.add(same_matter)
                await db.commit()
                await db.refresh(same_matter)
                try:
                    await promote_transition(
                        db, workspace_id=workspace_id, rel_type="same_as",
                        from_text=title, to_text=same_matter.title,
                        source_key=f"commitment_same_matter:{message_id}#{same_matter.id}",
                        evidence_refs=[f"honcho_message:{message_id}"],
                        subjects_to=[owner_peer_id] if owner_peer_id else [],
                        formation="inferred", confidence=0.7)
                except Exception as err:
                    logger.warning("commitment same-matter promotion failed: %s", err)
                return same_matter

        row = CommitmentCandidate(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            owner_peer_id=owner_peer_id,
            candidate_key=candidate_key,
            canonical_key=canonical_key,
            title=title[:280],
            notes=(candidate.observation or None) if candidate.observation != title else None,
            evidence_verbatim=evidence or title,
            evidence_class=(
                "counterparty_promise"
                if is_counterparty
                else (candidate.evidence_class or "implicit_self_commitment")
            ),
            authority=(
                CommitmentCandidateAuthority.ASK
                if is_counterparty
                else CommitmentCandidateAuthority(resolved_model_authority)
                if resolved_model_authority in ("act", "ask")
                else CommitmentCandidateAuthority.ASK
            ),
            status=CommitmentCandidateStatus.PENDING,
            source_message_id=message_id,
            raw_temporal_phrase=candidate.temporal_phrase,
            uttered_at=(now.replace(tzinfo=None) if now.tzinfo else now),
        )
        db.add(row)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            return (
                await db.execute(
                    select(CommitmentCandidate).where(
                        CommitmentCandidate.honcho_workspace_id == workspace_id,
                        CommitmentCandidate.owner_peer_id == owner_peer_id,
                        CommitmentCandidate.candidate_key == candidate_key,
                    )
                )
            ).scalar_one_or_none()
        return row

    async def _find_same_matter_commitment(
        self, db: AsyncSession, *, workspace_id: str, session_id: str,
        owner_peer_id: str, candidate: ExtractionCandidate, frame: Optional[str],
        message_id: str,
    ) -> Optional[CommitmentCandidate]:
        """Structured-first same-matter identity: generalises the principle
        already proven for OpenLoop (entity identity gates before any
        semantic step; lexical overlap is never the deciding authority) —
        not a mechanical copy, because commitment semantics differ from
        OpenLoop's OPEN-only reuse: a DISMISSED/VIOLATED/FULFILLED/
        MATERIALIZED commitment must never silently absorb new evidence
        (a new mention of a since-fulfilled or since-dismissed obligation is
        either a genuinely new instance or needs its own review, not a
        reopening), so this only ever considers PENDING rows.

        An EntityLink match (the same `entity_service`/`EntityLink`
        machinery already used for commitment subject-linking at the
        router) is REQUIRED before any semantic step — never lexical/title
        overlap alone (explicit instruction). Confirmation is the
        `same_matter` semantic-judge question, never a lexical threshold:
        this is what makes A3 safe (same actor + same topic ≠ same
        obligation) and A4 possible (poor lexical overlap, including
        cross-language, is irrelevant once an LLM judges meaning). Zero or
        multiple confirmed matches is treated as unresolved (A5): create a
        new row rather than guess, matching this module's own stated
        principle that a wrong merge is worse than a duplicate proposal.
        """
        refs = [r for r in (candidate.subject_refs or [])[:8] if isinstance(r, str) and r.strip()]
        if not refs:
            return None
        from src.services import entity_service
        entities = []
        for ref in refs:
            entity, status = await entity_service.resolve_mention(
                db, workspace_id=workspace_id, session_id=session_id,
                mention=ref, frame=frame, message_id=message_id)
            if entity is not None and status in ("linked", "provisioned"):
                entities.append(entity)
        if not entities:
            return None

        from src.models.identity import EntityLink
        entity_ids = [e.id for e in entities]
        linked_object_ids = (await db.execute(select(EntityLink.object_id).where(
            EntityLink.honcho_workspace_id == workspace_id,
            EntityLink.object_type == "commitment",
            EntityLink.entity_id.in_(entity_ids),
        ))).scalars().all()
        if not linked_object_ids:
            return None

        candidate_rows = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
            CommitmentCandidate.owner_peer_id == owner_peer_id,
            CommitmentCandidate.status == CommitmentCandidateStatus.PENDING,
            CommitmentCandidate.id.in_(set(linked_object_ids)),
        ).order_by(CommitmentCandidate.updated_at.desc()).limit(5))).scalars().all()
        if not candidate_rows:
            return None

        try:
            from src.services import semantic_judge
            adapter = semantic_judge._adapter()
        except Exception:
            adapter = None
        if adapter is None:
            # No confirmation available: the safe default is a new,
            # distinct row — never merge on entity identity alone.
            return None

        new_text = (candidate.canonical_title or candidate.observation or "").strip()
        if not new_text:
            return None
        confirmed = []
        for row in candidate_rows:
            try:
                result = await semantic_judge.adjudicate(
                    kind="same_matter", earlier=row.title, later=new_text, adapter=adapter)
            except Exception as err:
                logger.warning("same-matter judge check failed: %s", err)
                continue
            if result.accepted and result.evidence_span.strip() \
                    and result.evidence_span.strip() in new_text:
                confirmed.append(row)
        if len(confirmed) == 1:
            return confirmed[0]
        return None

    async def expire_stale(
        self, db: AsyncSession, *, workspace_id: str, owner_peer_id: str, now: datetime
    ) -> None:
        cutoff = _now_naive() - timedelta(
            days=CommitmentCandidate.CANDIDATE_MAX_AGE_DAYS
        )
        rows = (
            await db.execute(
                select(CommitmentCandidate).where(
                    CommitmentCandidate.honcho_workspace_id == workspace_id,
                    CommitmentCandidate.owner_peer_id == owner_peer_id,
                    CommitmentCandidate.status == CommitmentCandidateStatus.PENDING,
                    CommitmentCandidate.updated_at < cutoff,
                )
            )
        ).scalars().all()
        for row in rows:
            row.status = CommitmentCandidateStatus.EXPIRED
            row.updated_at = _now_naive()
            db.add(row)
        if rows:
            await db.commit()

    async def list_pending(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        owner_peer_id: str,
        authority: Optional[CommitmentCandidateAuthority] = None,
        limit: int = 20,
    ) -> List[CommitmentCandidate]:
        await self.expire_stale(
            db, workspace_id=workspace_id, owner_peer_id=owner_peer_id, now=_now_naive()
        )
        conditions = [
            CommitmentCandidate.honcho_workspace_id == workspace_id,
            CommitmentCandidate.owner_peer_id == owner_peer_id,
            CommitmentCandidate.status == CommitmentCandidateStatus.PENDING,
        ]
        if authority is not None:
            conditions.append(CommitmentCandidate.authority == authority)
        rows = (
            await db.execute(
                select(CommitmentCandidate)
                .where(*conditions)
                .order_by(CommitmentCandidate.created_at.desc())
                .limit(max(1, min(limit, 50)))
            )
        ).scalars().all()
        return list(rows)

    async def list_actionable(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        owner_peer_id: str,
        limit: int = 20,
    ) -> List[CommitmentCandidate]:
        """The ONLY read path future obligation machinery (due-state,
        violation derivation, projection directives) may use.

        Invariant: candidate readings (ASK) are never canonical commitments,
        no matter how many accumulate. Only ACT rows — plus, once it exists,
        corroboration promotion — count as authoritative. Proposal surfaces
        (Sophie-noticed, curiosity) keep using list_pending without filter.
        """
        return await self.list_pending(
            db, workspace_id=workspace_id, owner_peer_id=owner_peer_id,
            authority=CommitmentCandidateAuthority.ACT, limit=limit,
        )

    async def mark(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        owner_peer_id: str,
        candidate_key: str,
        status: CommitmentCandidateStatus,
        source_object_id: Optional[str] = None,
    ) -> Optional[CommitmentCandidate]:
        row = (
            await db.execute(
                select(CommitmentCandidate).where(
                    CommitmentCandidate.honcho_workspace_id == workspace_id,
                    CommitmentCandidate.owner_peer_id == owner_peer_id,
                    CommitmentCandidate.candidate_key == candidate_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.status == CommitmentCandidateStatus.DISMISSED:
            return row  # dismissal is durable; materialization cannot resurrect
        row.status = status
        if source_object_id:
            row.materialized_source_object_id = source_object_id
        row.updated_at = _now_naive()
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    async def try_fulfill(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        session_id: str,
        candidate: ExtractionCandidate,
        message_id: str,
        now: datetime,
    ) -> Optional["UUID"]:
        """Consume completion evidence for a PENDING ACT commitment — the
        primitive that was entirely missing before this fix (evaluate_due
        was previously the ONLY way out of PENDING other than dismiss/
        expire/materialize, so "I told the venue yes, so that's done" could
        never do anything but wait to VIOLATE).

        Deliberately owner-agnostic in its search, matching the existing,
        already-shipped pattern for Expectation outcome mutations
        (`handle_outcome_mutations`'s generic branch, `_resolve_targets`):
        completion evidence legitimately arrives from a different sender
        than the commitment's owner (a bank/payment feed closing a user's
        own obligation, an external party's own follow-up), so scoping the
        search to the CURRENT message's sender would silently miss exactly
        the cross-source evidence this exists to handle.

        Structured-first, lexical-as-prefilter-only, matching the required
        posture: an explicit target_id is trusted directly; otherwise
        `_significant_tokens` overlap is used only to retrieve and rank
        candidates (never as sole authority) — a strong deterministic
        overlap proceeds directly (same bar as `_fulfill_grounded`'s
        existing precedent), a weaker one is confirmed by the existing
        `semantic_judge` "fulfils" question, and anything left ambiguous
        (no clear single winner, or the judge is unavailable/unconvinced)
        is left PENDING rather than guessed — plausible-but-uncertain holds
        provisionally instead of forcing a decision, and never becomes a
        clarification question (uncertainty here is not consequential
        enough to interrogate the user over)."""
        from uuid import UUID as _UUID
        from src.services.lifecycle_service import LifecycleService

        if not candidate.resolution_hint:
            return None
        hint = candidate.resolution_hint
        if hint.get("action") != "fulfill":
            return None
        if candidate.is_hypothetical or candidate.is_quoted:
            return None
        evidence_text = " ".join(filter(None, [candidate.raw_evidence, candidate.observation]))
        if LifecycleService._has_marker(evidence_text, LifecycleService.COUNTERFACTUAL_MARKERS):
            return None
        if LifecycleService._has_marker(evidence_text, LifecycleService.NEGATIVE_OUTCOME_MARKERS):
            return None

        rows = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
            CommitmentCandidate.honcho_session_id == session_id,
            CommitmentCandidate.status == CommitmentCandidateStatus.PENDING,
            CommitmentCandidate.authority == CommitmentCandidateAuthority.ACT,
        ))).scalars().all()
        if not rows:
            return None

        target_id = hint.get("target_id")
        if target_id:
            try:
                target_uuid = _UUID(str(target_id))
            except (TypeError, ValueError):
                target_uuid = None
            if target_uuid is not None:
                for row in rows:
                    if row.id == target_uuid:
                        await self._fulfill_row(db, row, message_id=message_id, candidate=candidate,
                                                evidence_note="target_id")
                        return row.id
            return None

        scored = []
        for row in rows:
            shared = LifecycleService._significant_tokens(evidence_text) & LifecycleService._significant_tokens(row.title)
            if shared:
                scored.append((len(shared), row))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        strong = [item for item in scored if item[0] >= 2]
        if len(strong) == 1 and len(scored) == 1:
            # Sole lexical candidate overall: no competing matter shares even
            # one significant token, so row selection cannot misfire onto a
            # vocabulary neighbour ("school trip payment" vs "school trip
            # permission form"). Any competition at all routes to judged
            # confirmation below; ambiguity stays PENDING, never guessed.
            await self._fulfill_row(db, strong[0][1], message_id=message_id, candidate=candidate,
                                    evidence_note="deterministic-overlap")
            return strong[0][1].id
        # Otherwise (several strong, or one strong with weak competition):
        # selection among vocabulary neighbours is a semantic decision, not
        # a counting one — fall through to judged confirmation, which
        # requires a single confirmed winner and fails safe to PENDING.
        if len(strong) > 1:
            # Two-plus commitments both look strongly like the same
            # evidence: an ambiguous match is worse than a missed one.
            # Keep the cheap early exit (no judge calls spent); the judged
            # path below handles at most one strong winner with competition.
            return None

        # Weak lexical retrieval only (overlap==1): cheap prefilter results,
        # not authority — confirm with the existing semantic judge before
        # acting, and only when it names a single, unambiguous winner.
        try:
            from src.services import semantic_judge
            adapter = semantic_judge._adapter()
        except Exception:
            adapter = None
        if adapter is None:
            return None
        confirmed = []
        for _, row in scored[:3]:
            try:
                result = await semantic_judge.adjudicate(
                    kind="fulfils", earlier=row.title, later=evidence_text, adapter=adapter)
            except Exception as err:
                logger.warning("commitment fulfilment judge failed: %s", err)
                continue
            if result.accepted and result.evidence_span.strip() \
                    and result.evidence_span.strip() in evidence_text:
                confirmed.append(row)
        if len(confirmed) == 1:
            await self._fulfill_row(db, confirmed[0], message_id=message_id, candidate=candidate,
                                    evidence_note="judged")
            return confirmed[0].id
        return None

    async def _fulfill_row(
        self, db: AsyncSession, row: CommitmentCandidate, *, message_id: str,
        candidate: ExtractionCandidate, evidence_note: str,
    ) -> None:
        row.status = CommitmentCandidateStatus.FULFILLED
        row.resolution_evidence = (
            f"fulfilled:{evidence_note}:{message_id}#candidate:{candidate.candidate_key}"
        )
        row.updated_at = _now_naive()
        db.add(row)
        await db.commit()
        logger.info("Fulfilled CommitmentCandidate id=%s via %s", row.id, evidence_note)

    async def evaluate_due(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        now: datetime,
    ) -> List["UUID"]:
        """Derive violations from elapsed due conditions. Reads ONLY
        authoritative (ACT) pending rows: ASK-only rows can never violate,
        no matter how many accumulate. A row becomes VIOLATED with named
        evidence when its grounded due window has passed without fulfilment
        evidence; nothing is ever silently fulfilled or discarded here."""
        from uuid import UUID
        from src.services.temporal_grounding import TemporalGrounding
        now_naive = now.replace(tzinfo=None) if now.tzinfo else now
        rows = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
            CommitmentCandidate.authority == CommitmentCandidateAuthority.ACT,
            CommitmentCandidate.status == CommitmentCandidateStatus.PENDING,
            CommitmentCandidate.raw_temporal_phrase.is_not(None),
        ))).scalars().all()
        violated: List["UUID"] = []
        grounder = TemporalGrounding()
        for row in rows:
            # Anchor grounding to when the promise was uttered: the source
            # turn's stamp, else the row's own uttered_at (assistant turns
            # write no TurnStamps by design), else creation. "Tomorrow" said
            # Tuesday is due Wednesday even if evaluated Friday.
            anchor = None
            turn_at = (await db.execute(select(TurnStamp).where(
                TurnStamp.honcho_workspace_id == workspace_id,
                TurnStamp.honcho_message_id == row.source_message_id,
            ))).scalar_one_or_none()
            if turn_at is not None:
                anchor = turn_at.turn_at
            elif getattr(row, "uttered_at", None) is not None:
                anchor = row.uttered_at
            else:
                anchor = row.created_at
            if anchor is not None and anchor.tzinfo is not None:
                anchor = anchor.replace(tzinfo=None)
            try:
                win_start, win_end, deadline = grounder.ground_expression(
                    raw_phrase=row.raw_temporal_phrase, now=anchor or now,
                    timezone_str="UTC")
            except Exception:
                continue
            due = deadline or win_end
            if due is None:
                continue
            due_naive = due.replace(tzinfo=None) if due.tzinfo else due
            if due_naive > now_naive:
                continue
            if row.resolution_evidence:
                continue
            row.status = CommitmentCandidateStatus.VIOLATED
            row.resolution_evidence = (
                f"violated:due {due_naive.isoformat()} passed without "
                f"fulfilment evidence (evaluated {now_naive.isoformat()})"
            )
            row.updated_at = _now_naive()
            db.add(row)
            violated.append(row.id)
        if violated:
            await db.commit()
            logger.info("Derived %d commitment violations", len(violated))
        return violated
