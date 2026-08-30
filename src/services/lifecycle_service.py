import logging
import json
import re
from typing import Any, Optional, List, Tuple
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

    # Counterfactual/hypothetical language: text shaped like a completed event
    # but actually describing what WOULD have happened. Must never become
    # fulfillment evidence.
    COUNTERFACTUAL_MARKERS = (
        "would have", "would've", "had to do", "would have had to",
        "was meant to", "were meant to", "if he'd", "if she'd", "if i'd",
        "if we'd", "nearly", "could have", "almost went", "the plan was to",
        "was supposed to", "were supposed to", "otherwise i",
    )
    # Explicit negative outcome: the expected thing did NOT occur. Strong
    # evidence — maps to NOT_FULFILLED, never to FULFILLED/UNKNOWN.
    NEGATIVE_OUTCOME_MARKERS = (
        "didn't go", "did not go", "didnt go", "gave it a miss",
        "give it a miss", "won't be going", "wont be going", "not going",
        "didn't happen", "did not happen", "didnt happen", "called it off",
        "can't get there", "cant get there", "no way of getting there",
        "have to give it a miss", "didn't make it", "did not make it",
    )

    @staticmethod
    def _has_marker(text: str, markers) -> bool:
        lowered = (text or "").lower()
        return any(marker in lowered for marker in markers)

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
        evidence_text = " ".join(filter(None, [
            candidate.observation, candidate.canonical_title,
            str(candidate.resolution_hint.get("evidence") or ""),
        ]))
        if action == "cancel":
            exp.outcome_state = OutcomeState.CANCELLED
        elif action == "fulfill":
            if self._has_marker(evidence_text, self.NEGATIVE_OUTCOME_MARKERS):
                # "I was meant to go but I didn't" — explicit negative outcome,
                # never fulfillment.
                exp.outcome_state = OutcomeState.NOT_FULFILLED
            elif self._has_marker(evidence_text, self.COUNTERFACTUAL_MARKERS):
                # Counterfactual/hypothetical text ("would have had to...")
                # is context, not completion evidence. Leave the belief
                # UNKNOWN and let reconciliation decide.
                logger.info(
                    "Blocked counterfactual fulfillment for expectation id=%s",
                    exp.id,
                )
                return []
            else:
                exp.outcome_state = OutcomeState.FULFILLED
            if exp.outcome_state != OutcomeState.UNKNOWN:
                await self._resolve_open_loop_for_expectation(db, exp.id, evidence)
        elif action == "did_not_occur":
            exp.outcome_state = OutcomeState.NOT_FULFILLED
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
            # Belief reconciliation: a terminal outcome about one real-world
            # plan must collapse sibling representations of the same plan,
            # so cancelled/fulfilled plans cannot stay foreground UNKNOWN.
            await self._reconcile_siblings(
                db,
                workspace_id=workspace_id,
                resolved=exp,
                now=now,
            )

        return modified_ids

    async def _reconcile_siblings(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        resolved: Expectation,
        now: datetime,
    ) -> List[UUID]:
        """Belief reconciliation.

        New evidence about one real-world plan must update THE belief about
        that plan, not merely append another belief. After a terminal outcome
        (fulfilled / not_fulfilled / cancelled) is applied, any sibling
        UNKNOWN expectations that describe the same plan are superseded onto
        the resolved row, so they can no longer compete for attention.

        Sibling identity: same owner, same subject_peer_id (e.g. "mother",
        "Oxford") OR >=2 shared significant title tokens. Historical evidence
        is preserved: rows are superseded, never deleted."""
        if resolved.outcome_state not in (
            OutcomeState.FULFILLED,
            OutcomeState.NOT_FULFILLED,
            OutcomeState.CANCELLED,
        ):
            return []
        stmt = select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.outcome_state == OutcomeState.UNKNOWN,
            Expectation.superseded_by_id.is_(None),
            Expectation.id != resolved.id,
        )
        rows = (await db.execute(stmt)).scalars().all()

        resolved_tokens = self._significant_tokens(resolved.title)
        siblings: List[Expectation] = []
        for row in rows:
            if row.owner_peer_id and resolved.owner_peer_id and (
                row.owner_peer_id != resolved.owner_peer_id
            ):
                continue
            # subject_peer_id only identifies a real third party when it
            # differs from the owner; self-commitments share the owner id and
            # must rely on title identity instead.
            same_subject = (
                resolved.subject_peer_id
                and row.subject_peer_id
                and row.subject_peer_id == resolved.subject_peer_id
                and resolved.owner_peer_id
                and resolved.subject_peer_id != resolved.owner_peer_id
            )
            shared = self._significant_tokens(row.title) & resolved_tokens
            if same_subject or len(shared) >= 2:
                siblings.append(row)
            if len(siblings) >= 6:
                break

        evidence = resolved.resolution_evidence or "sibling-reconciliation"
        modified: List[UUID] = []
        for sibling in siblings:
            sibling.outcome_state = OutcomeState.SUPERSEDED
            sibling.superseded_by_id = resolved.id
            sibling.resolution_evidence = evidence
            sibling.updated_at = self._naive_utc(now)
            db.add(sibling)
            await self._supersede_open_loops(db, sibling.id, evidence)
            modified.append(sibling.id)
        if modified:
            await db.commit()
            logger.info(
                "Reconciled %d sibling expectations onto resolved id=%s",
                len(modified), resolved.id,
            )
        return modified

    async def reconcile_new_expectation(
        self,
        db: AsyncSession,
        *,
        expectation: Expectation,
        now: datetime,
    ) -> List[UUID]:
        """A newly created expectation is the CURRENT belief about its plan.
        Prior UNKNOWN expectations for the same owner describing the same plan
        are superseded onto it, so old 'tomorrow' rows cannot outlive newer
        evidence."""
        stmt = select(Expectation).where(
            Expectation.honcho_workspace_id == expectation.honcho_workspace_id,
            Expectation.outcome_state == OutcomeState.UNKNOWN,
            Expectation.superseded_by_id.is_(None),
            Expectation.id != expectation.id,
        )
        rows = (await db.execute(stmt)).scalars().all()
        new_tokens = self._significant_tokens(expectation.title)
        modified: List[UUID] = []
        for row in rows:
            if row.owner_peer_id and expectation.owner_peer_id and (
                row.owner_peer_id != expectation.owner_peer_id
            ):
                continue
            same_subject = (
                expectation.subject_peer_id
                and row.subject_peer_id
                and row.subject_peer_id == expectation.subject_peer_id
                and expectation.owner_peer_id
                and expectation.subject_peer_id != expectation.owner_peer_id
            )
            shared = self._significant_tokens(row.title) & new_tokens
            if not (same_subject or len(shared) >= 2):
                continue
            row.outcome_state = OutcomeState.SUPERSEDED
            row.superseded_by_id = expectation.id
            row.updated_at = self._naive_utc(now)
            db.add(row)
            modified.append(row.id)
            if len(modified) >= 6:
                break
        if modified:
            await db.commit()
            logger.info(
                "New expectation id=%s superseded %d stale siblings",
                expectation.id, len(modified),
            )
        return modified

    @staticmethod
    def _significant_tokens(title: str) -> set:
        stop = {
            "the", "and", "for", "with", "their", "have", "has", "had", "not",
            "user", "intends", "intend", "plans", "plan", "planning", "went",
            "going", "goes", "will", "was", "were", "that", "this", "from",
            "about", "into", "their", "them", "they", "his", "her", "its",
        }
        words = set()
        for token in re.findall(r"[a-z0-9']+", (title or "").lower()):
            if len(token) < 3 or token in stop:
                continue
            words.add(token)
            if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
                words.add(token[:-1])
            if len(token) > 5 and token.endswith("ing"):
                words.add(token[:-3])
        return words

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
            owner_peer_id=old.owner_peer_id,
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

    # Strong completion markers. Used only as a deterministic post-pass to
    # convert progress/completion-shaped turns into genuine fulfillments of a
    # matched open expectation; never to invent state.
    COMPLETION_MARKERS = (
        " done", "finished", "completed", "completed all", "fixed",
        "pushed it", "pushed it live", "shipped", "submitted", "went well",
        "managed to", "got it working", "all 14", "made it",
    )

    async def resolve_explicit_completions(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        session_id: str,
        message_id: str,
        candidate: Any,
        now: datetime,
    ) -> List[UUID]:
        """Deterministic completion pass for progress/completion-shaped
        candidates.

        The lane shaper routes accomplishments ('migration checklist done!')
        to `progress`, which has its own objective handling and therefore
        skips generic outcome mutations. Without this pass the completed plan
        stays UNKNOWN forever. Here we fulfill an open expectation only when
        the candidate text contains a strong completion marker and exactly one
        open expectation matches; ambiguity stays unresolved on purpose."""
        if candidate.operational_kind not in ("progress", "completion"):
            return []
        text = (
            f"{candidate.canonical_title or ''} {candidate.observation}".lower()
        )
        negative = self._has_marker(text, self.NEGATIVE_OUTCOME_MARKERS)
        counterfactual = self._has_marker(text, self.COUNTERFACTUAL_MARKERS)
        has_completion = any(
            marker in text for marker in self.COMPLETION_MARKERS
        )
        if counterfactual and not negative:
            # Counterfactual/hypothetical framing ("I would have had to...")
            # must never become completion or negative-outcome evidence by
            # itself: it is context about a plan that may or may not exist.
            return []
        if not negative and not has_completion:
            return []
        stmt = select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.honcho_session_id == session_id,
            Expectation.outcome_state == OutcomeState.UNKNOWN,
        )
        res = await db.execute(stmt)
        active = list(res.scalars().all())
        synthetic = candidate.model_copy(update={
            "resolution_hint": {
                "action": "did_not_occur" if negative else "fulfill",
                "target_text": candidate.canonical_title or candidate.observation,
                "evidence": candidate.observation,
            }
        })
        targets = self._resolve_targets(active, synthetic)
        if len(targets) != 1:
            return []
        exp = targets[0]
        evidence = (
            f"honcho_message:{message_id}#candidate:{candidate.candidate_key}"
        )
        if negative:
            exp.outcome_state = OutcomeState.NOT_FULFILLED
        else:
            exp.outcome_state = OutcomeState.FULFILLED
        exp.resolution_evidence = evidence
        exp.updated_at = self._naive_utc(now)
        db.add(exp)
        await self._resolve_open_loop_for_expectation(db, exp.id, evidence)
        await db.commit()
        logger.info(
            "Explicit completion resolved expectation id=%s to %s from %s",
            exp.id, exp.outcome_state.value, candidate.operational_kind,
        )
        return [exp.id]

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
        # exists AND the observation itself refers to it ("it", "that", "this").
        # An explicit target_text that merely restates the observation is
        # self-referential and does not block deictic resolution; a target_text
        # naming a distinct noun (e.g. "the report") blocks it. We never fall back
        # to "resolve the only open expectation" on arbitrary fulfill output: an
        # unrelated success while one expectation exists must not mark that
        # expectation resolved.
        deictic = bool(re.search(r"\b(?:it|that|this|the thing)\b", candidate.observation.lower()))
        if deictic and len(expectations) == 1 and hint.get("action") != "cancel":
            target_text = str(hint.get("target_text") or "")
            if not target_text:
                return expectations
            target_tokens = {
                w for w in re.findall(r"[a-z0-9]+", target_text.lower())
                if len(w) > 2 and w not in stop
            }
            obs_tokens = {
                w for w in re.findall(r"[a-z0-9]+", candidate.observation.lower())
                if len(w) > 2 and w not in stop
            }
            if target_tokens and target_tokens & obs_tokens:
                return expectations
        return []

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
        owner_peer_id: Optional[str] = None,
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
            owner_peer_id=owner_peer_id,
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
        provenance = candidate.epistemic_provenance
        if provenance not in {item.value for item in EpistemicProvenance}:
            logger.warning("Dropping epistemic annotation: invalid provenance=%r", provenance)
            return None
        annotation = EpistemicAnnotation(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            honcho_message_id=message_id,
            candidate_key=candidate.candidate_key,
            target_expectation_id=expectation_id,
            perspective_peer_id=claim.get("perspective") or candidate.actor_peer_id or "user",
            target_peer_id=claim.get("target") or candidate.subject_peer_id,
            provenance_type=EpistemicProvenance(provenance),
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

        if candidate.domain_tag not in {item.value for item in DomainTag} or (
            candidate.category_tag is not None
            and candidate.category_tag not in {item.value for item in CategoryTag}
        ):
            logger.warning(
                "Dropping domain annotation: invalid domain=%r category=%r",
                candidate.domain_tag,
                candidate.category_tag,
            )
            return None
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

    async def apply_reopen_conditions(
        self,
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        text: str,
    ) -> List[str]:
        """Consumer for stored reopen_condition.

        A suppression created with reopen_condition="user_mentions_topic"
        reopens the moment the user mentions the topic again. Subsequent turns
        are no longer suppressed by it.
        """
        lower = text.lower()
        candidates = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == workspace_id,
            Suppression.honcho_session_id == session_id,
            Suppression.status == SuppressionStatus.ACTIVE,
        ))).scalars().all()
        reopened: list[str] = []
        for item in candidates:
            if item.reopen_condition != "user_mentions_topic" or not item.topic_or_entity:
                continue
            tokens = [token for token in item.topic_or_entity.lower().split() if len(token) >= 4]
            if tokens and any(
                re.search(r"\b" + re.escape(token) + r"\b", lower) for token in tokens
            ):
                item.status = SuppressionStatus.REOPENED
                item.updated_at = self._naive_utc(datetime.now(timezone.utc))
                db.add(item)
                reopened.append(str(item.id))
        if reopened:
            await db.commit()
        return reopened
