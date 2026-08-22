import logging
import json
import re
from typing import Optional, List, Tuple
from uuid import UUID
from datetime import datetime, timezone
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from src.models.expectation import Expectation, OutcomeState
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.suppression import Suppression, SuppressionStatus, SuppressionTarget
from src.models.epistemic import EpistemicAnnotation, EpistemicProvenance
from src.models.domain_annotation import DomainAnnotation, DomainTag, CategoryTag
from src.models.clarification import (
    ClarificationCandidate, ClarificationStatus, ClarificationType,
)
from src.schemas.candidate import ExtractionCandidate
from src.services.temporal_grounding import TemporalGrounding

logger = logging.getLogger(__name__)
temporal_grounder = TemporalGrounding()


class LifecycleService:
    """
    Manages V4 companion-state mutations:
    - Outcome mutations (fulfilled, cancelled, superseded, corrected)
    - Open loop lifecycle (open -> resolved / abandoned / suppressed)
    - Suppression lifecycle (active -> expired / reopened)
    - Versioning & supersession for reprocessed messages
    - Epistemic & Domain annotation persistence
    """

    async def handle_outcome_mutations(
        self,
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        message_id: str,
        candidate: ExtractionCandidate,
        now: datetime,
    ) -> List[UUID]:
        """Processes resolution or cancellation hints against active expectations."""
        if not candidate.resolution_hint:
            return []

        action = candidate.resolution_hint.get("action")
        evidence = f"honcho_message:{message_id}#candidate:{candidate.candidate_key}"
        modified_ids: List[UUID] = []

        stmt = select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.honcho_session_id == session_id,
            Expectation.outcome_state == OutcomeState.UNKNOWN,
        )
        res = await db.execute(stmt)
        active_expectations = list(res.scalars().all())
        targets = self._resolve_targets(active_expectations, candidate)
        if len(targets) != 1:
            await self._create_clarification(
                db, workspace_id, session_id, message_id, candidate,
                "Outcome or correction target is ambiguous",
                active_expectations,
            )
            return []

        exp = targets[0]
        if action == "cancel":
            exp.outcome_state = OutcomeState.CANCELLED
        elif action == "fulfill":
            exp.outcome_state = OutcomeState.FULFILLED
            await self._resolve_open_loop_for_expectation(db, exp.id, evidence)
        elif action in ("correct", "reschedule"):
            replacement = await self._create_replacement(
                db, exp, message_id, candidate, now
            )
            exp.outcome_state = OutcomeState.SUPERSEDED
            exp.superseded_by_id = replacement.id
            await self._supersede_open_loops(db, exp.id, evidence)
        else:
            return []

        exp.resolution_evidence = evidence
        exp.updated_at = self._naive_utc(now)
        db.add(exp)
        modified_ids.append(exp.id)
        logger.info("Expectation id=%s outcome=%s", exp.id, exp.outcome_state.value)

        if modified_ids:
            await db.commit()

        return modified_ids

    async def _create_replacement(self, db, old, message_id, candidate, now):
        hint = candidate.resolution_hint or {}
        new_temporal = hint.get("correct_value") or candidate.temporal_phrase
        win_start, win_end, deadline = temporal_grounder.ground_expression(
            new_temporal, now, old.anchor_timezone
        )
        replacement = Expectation(
            honcho_workspace_id=old.honcho_workspace_id,
            honcho_session_id=old.honcho_session_id,
            honcho_message_id=message_id,
            candidate_key=f"{candidate.candidate_key}:replacement",
            source_start=candidate.source_start,
            source_end=candidate.source_end,
            version=old.version + 1,
            subject_peer_id=old.subject_peer_id,
            expectation_type=old.expectation_type,
            title=old.title,
            summary=f"{old.title} ({new_temporal or 'corrected plan'})",
            raw_temporal_phrase=new_temporal,
            anchor_timezone=old.anchor_timezone,
            expected_window_start=win_start,
            expected_window_end=win_end,
            hard_deadline_at=deadline,
            extraction_confidence=min(old.extraction_confidence, candidate.confidence),
        )
        db.add(replacement)
        await db.flush()
        return replacement

    async def _supersede_open_loops(self, db, expectation_id, evidence):
        rows = (await db.execute(select(OpenLoop).where(
            OpenLoop.expectation_id == expectation_id,
            OpenLoop.status == OpenLoopStatus.OPEN,
        ))).scalars().all()
        for loop in rows:
            loop.status = OpenLoopStatus.SUPERSEDED
            loop.resolution_evidence = evidence
            db.add(loop)

    def _resolve_targets(
        self, expectations: List[Expectation], candidate: ExtractionCandidate
    ) -> List[Expectation]:
        hint = candidate.resolution_hint or {}
        target_id = hint.get("target_id")
        if target_id:
            return [exp for exp in expectations if str(exp.id) == str(target_id)]

        wrong_value = str(hint.get("wrong_value") or "").lower()
        if wrong_value:
            matches = [
                exp for exp in expectations
                if wrong_value in exp.title.lower()
                or wrong_value in (exp.raw_temporal_phrase or "").lower()
                or wrong_value in exp.summary.lower()
            ]
            if matches:
                return matches

        actor = str(hint.get("actor") or "").lower()
        if actor and actor not in ("i", "me", "user"):
            return [
                exp for exp in expectations
                if actor == exp.subject_peer_id.lower() or actor in exp.title.lower()
            ]

        text = f"{candidate.observation} {hint.get('target_text') or ''}".lower()
        ordinal = re.search(r"\b(?:the\s+)?(first|second|third)\s+(?:one|thing)\b", text)
        if ordinal:
            ordered = sorted(expectations, key=lambda e: (e.created_at, e.source_start or 0))
            index = {"first": 0, "second": 1, "third": 2}[ordinal.group(1)]
            return [ordered[index]] if len(ordered) > index else []

        scored = []
        stop = {"that", "this", "thing", "one", "actually", "done", "sent", "it", "the"}
        words = {w for w in re.findall(r"[a-z0-9]+", text) if len(w) > 2 and w not in stop}
        for exp in expectations:
            haystack = " ".join((exp.title, exp.summary, exp.raw_temporal_phrase or "", exp.subject_peer_id)).lower()
            score = sum(1 for word in words if word in haystack)
            if score:
                scored.append((score, exp))
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        if hint.get("action") == "cancel" and hint.get("target_text") and scored and scored[0][0] < 2:
            return []
        if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return [scored[0][1]]

        # A genuinely deictic outcome is safe only when exactly one unresolved target
        # exists. Explicit unmatched nouns (for example "tidy" versus "walk") must
        # never mutate that sole unrelated row.
        deictic = (
            not hint.get("target_text")
            and bool(re.search(r"\b(?:it|that|this|the thing)\b", candidate.observation.lower()))
        )
        if len(expectations) == 1 and hint.get("action") != "cancel":
            return expectations
        return expectations if deictic and len(expectations) == 1 else []

    async def _create_clarification(
        self, db: AsyncSession, workspace_id: str, session_id: str,
        message_id: str, candidate: ExtractionCandidate, description: str,
        possible_targets: List[Expectation],
    ) -> ClarificationCandidate:
        stmt = select(ClarificationCandidate).where(
            ClarificationCandidate.honcho_workspace_id == workspace_id,
            ClarificationCandidate.honcho_message_id == message_id,
            ClarificationCandidate.candidate_key == candidate.candidate_key,
            ClarificationCandidate.clarification_type == ClarificationType.UNCLEAR_TARGET,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing
        clarification = ClarificationCandidate(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            honcho_message_id=message_id,
            candidate_key=candidate.candidate_key,
            clarification_type=ClarificationType.UNCLEAR_TARGET,
            description=description,
            candidates_json=json.dumps([
                {"id": str(exp.id), "title": exp.title} for exp in possible_targets[:5]
            ]),
            status=ClarificationStatus.PENDING,
        )
        db.add(clarification)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return (await db.execute(stmt)).scalar_one()
        await db.refresh(clarification)
        return clarification

    @staticmethod
    def _naive_utc(value: datetime) -> datetime:
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    async def _resolve_open_loop_for_expectation(
        self, db: AsyncSession, expectation_id: UUID, evidence: str
    ):
        stmt = select(OpenLoop).where(
            OpenLoop.expectation_id == expectation_id,
            OpenLoop.status == OpenLoopStatus.OPEN,
        )
        res = await db.execute(stmt)
        loops = res.scalars().all()
        for loop in loops:
            loop.status = OpenLoopStatus.RESOLVED
            loop.resolution_evidence = evidence
            db.add(loop)
            logger.info("OpenLoop id=%s resolved via expectation fulfillment", loop.id)

    async def create_open_loop_if_needed(
        self,
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        message_id: str,
        candidate: ExtractionCandidate,
        expectation_id: Optional[UUID] = None,
        now: Optional[datetime] = None,
        timezone_str: str = "UTC",
    ) -> Optional[OpenLoop]:
        if not candidate.open_loop_hint:
            return None

        stmt = select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.honcho_message_id == message_id,
            OpenLoop.candidate_key == candidate.candidate_key,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        expires_at = None
        expiry_phrase = candidate.expiry_phrase or candidate.temporal_phrase
        if expiry_phrase and now:
            _start, window_end, deadline = temporal_grounder.ground_expression(
                raw_phrase=expiry_phrase, now=now, timezone_str=timezone_str
            )
            expires_at = deadline or window_end
        open_loop = OpenLoop(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            honcho_message_id=message_id,
            candidate_key=candidate.candidate_key,
            expectation_id=expectation_id,
            title="Invited follow-up" if "follow" in candidate.open_loop_hint.lower() or candidate.operational_kind == "open_loop" else "Open loop",
            summary=candidate.canonical_title or candidate.open_loop_hint,
            status=OpenLoopStatus.OPEN,
            expires_at=expires_at,
        )
        db.add(open_loop)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return (await db.execute(stmt)).scalar_one()
        await db.refresh(open_loop)
        logger.info("Created OpenLoop id=%s", open_loop.id)
        return open_loop

    async def create_suppression_if_needed(
        self,
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        message_id: str,
        candidate: ExtractionCandidate,
        now: datetime,
        timezone_str: str,
    ) -> Optional[Suppression]:
        if not candidate.suppression_hint:
            return None

        hint = candidate.suppression_hint
        if hint.get("ambiguous_target"):
            await self._create_clarification(
                db, workspace_id, session_id, message_id, candidate,
                "Suppression target is ambiguous", [],
            )
            return None
        if hint.get("action") == "reopen":
            topic = str(hint.get("topic_or_entity") or "").lower()
            stmt = select(Suppression).where(
                Suppression.honcho_workspace_id == workspace_id,
                Suppression.honcho_session_id == session_id,
                Suppression.status == SuppressionStatus.ACTIVE,
            )
            matches = [
                item for item in (await db.execute(stmt)).scalars().all()
                if (item.topic_or_entity or "").lower() == topic
            ]
            for item in matches:
                item.status = SuppressionStatus.REOPENED
                item.updated_at = self._naive_utc(now)
                db.add(item)
            if matches:
                await db.commit()
                return matches[0]
            return None
        stmt = select(Suppression).where(
            Suppression.honcho_workspace_id == workspace_id,
            Suppression.honcho_message_id == message_id,
            Suppression.candidate_key == candidate.candidate_key,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing
        raw_temporal = hint.get("raw_temporal_phrase") or candidate.temporal_phrase
        win_start, win_end, hard_deadline = temporal_grounder.ground_expression(
            raw_phrase=raw_temporal, now=now, timezone_str=timezone_str
        )
        suppressed_until = win_end or hard_deadline

        try:
            target_type = SuppressionTarget(hint.get("target_type", "topic"))
        except ValueError:
            logger.warning("Rejected invalid suppression target_type=%r", hint.get("target_type"))
            return None
        suppression = Suppression(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            honcho_message_id=message_id,
            candidate_key=candidate.candidate_key,
            target_type=target_type,
            topic_or_entity=hint.get("topic_or_entity"),
            reason="user_explicit_suppression",
            surface_scope=hint.get("action_scope") or "all_surfaces",
            suppressed_until=suppressed_until,
            reopen_condition=hint.get("reopen_condition"),
            status=SuppressionStatus.ACTIVE,
        )
        db.add(suppression)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return (await db.execute(stmt)).scalar_one()
        await db.refresh(suppression)
        logger.info("Created Suppression id=%s target=%s until=%s", suppression.id, suppression.topic_or_entity, suppressed_until)
        return suppression

    async def create_epistemic_annotation_if_needed(
        self,
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        message_id: str,
        candidate: ExtractionCandidate,
        expectation_id: Optional[UUID] = None,
    ) -> Optional[EpistemicAnnotation]:
        if not candidate.epistemic_provenance:
            return None

        stmt = select(EpistemicAnnotation).where(
            EpistemicAnnotation.honcho_workspace_id == workspace_id,
            EpistemicAnnotation.honcho_message_id == message_id,
            EpistemicAnnotation.candidate_key == candidate.candidate_key,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        claim = candidate.epistemic_claim or {}
        annotation = EpistemicAnnotation(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            honcho_message_id=message_id,
            candidate_key=candidate.candidate_key,
            target_expectation_id=expectation_id,
            perspective_peer_id=claim.get("perspective") or candidate.actor_peer_id or "user",
            target_peer_id=claim.get("target") or candidate.subject_peer_id,
            provenance_type=EpistemicProvenance(candidate.epistemic_provenance),
            claim_summary=claim.get("claim") or (
                f"source-linked {candidate.epistemic_provenance}"
                + (f" about {candidate.subject_peer_id}" if candidate.subject_peer_id else "")
            ),
            confidence=candidate.confidence,
        )
        db.add(annotation)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return (await db.execute(stmt)).scalar_one()
        await db.refresh(annotation)
        return annotation

    async def create_domain_annotation_if_needed(
        self,
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        message_id: str,
        candidate: ExtractionCandidate,
    ) -> Optional[DomainAnnotation]:
        if not candidate.domain_tag:
            return None

        stmt = select(DomainAnnotation).where(
            DomainAnnotation.honcho_workspace_id == workspace_id,
            DomainAnnotation.honcho_message_id == message_id,
            DomainAnnotation.candidate_key == candidate.candidate_key,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            return existing

        annotation = DomainAnnotation(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            honcho_message_id=message_id,
            candidate_key=candidate.candidate_key,
            domain=DomainTag(candidate.domain_tag),
            category=CategoryTag(candidate.category_tag or "ask_about_later"),
            annotation_summary=f"source-linked {candidate.domain_tag} annotation",
        )
        db.add(annotation)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return (await db.execute(stmt)).scalar_one()
        await db.refresh(annotation)
        return annotation
