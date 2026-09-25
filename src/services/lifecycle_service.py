import logging
import json
import re
from typing import Any, Optional, List, Tuple
from uuid import UUID
from datetime import datetime, timezone
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_
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
from src.services.semantic_promotion import promote_transition
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

    async def _fulfill_grounded(self, db, *, exp, evidence_text: str,
                               candidate, message_id: str) -> bool:
        """Fulfillment claims need grounding: strong lexical overlap proceeds
        deterministically; weak overlap requires a bounded semantic-judge
        confirmation (verbatim span in the evidence); no adapter means prior
        behavior (proceed) so rules mode is untouched. Every decision is
        traced for inspection."""
        from src.models.operational_state import ExtractionTrace

        async def trace(status: str, detail: dict) -> None:
            try:
                db.add(ExtractionTrace(
                    honcho_workspace_id=exp.honcho_workspace_id,
                    honcho_session_id=exp.honcho_session_id,
                    honcho_message_id=message_id,
                    stage="fulfill_grounding",
                    item_key=f"{exp.id}:{message_id}",
                    status=status,
                    model="deterministic+judge",
                    detail_json=json.dumps(detail, default=str)[:2000],
                ))
                await db.commit()
            except Exception as err:
                logger.warning("fulfill grounding trace failed: %s", err)
                try:
                    await db.rollback()
                except Exception:
                    pass

        overlap = len(self._significant_tokens(evidence_text or "") & self._significant_tokens(
            f"{exp.title or ''} {exp.summary or ''}"))
        if overlap >= 2:
            await trace("proceeded-deterministic", {"overlap": overlap})
            return True
        try:
            from src.services import semantic_judge
            result = await semantic_judge.adjudicate(
                kind="fulfils",
                earlier=f"{exp.title or ''} {exp.summary or ''}".strip(),
                later=evidence_text or "")
        except Exception as err:
            logger.warning("fulfill grounding check failed (fail-open): %s", err)
            return True
        if result.verdict == "unavailable":
            return True  # no adapter etc: prior behavior
        if result.accepted and result.evidence_span.strip() \
                and result.evidence_span.strip() in (evidence_text or ""):
            await trace("proceeded-judged", {
                "overlap": overlap, "confidence": result.confidence,
                "evidence_span": result.evidence_span,
                "rationale": result.rationale})
            return True
        logger.info(
            "Blocked ungrounded fulfillment for expectation id=%s "
            "(overlap=%d, verdict=%s)", exp.id, overlap, result.verdict)
        await trace("blocked", {
            "overlap": overlap, "verdict": result.verdict,
            "confidence": result.confidence, "rationale": result.rationale})
        return False

    async def handle_outcome_mutations(
        self,
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        message_id: str,
        candidate: ExtractionCandidate,
        now: datetime,
        owner_peer_id: Optional[str] = None,
    ) -> List[UUID]:
        """Processes resolution or cancellation hints against active expectations."""
        if not candidate.resolution_hint:
            return []

        from src.models.attention_candidate import AttentionCandidate, AttentionCandidateStatus
        hint = candidate.resolution_hint
        kind = hint.get("target_kind")
        if kind in ("open_loop", "attention", "clarification"):
            evidence_text = " ".join(filter(None, [candidate.raw_evidence, candidate.observation]))
            if self._has_marker(evidence_text, self.COUNTERFACTUAL_MARKERS):
                return []
            if hint.get("action") == "fulfill" and self._has_marker(evidence_text, self.NEGATIVE_OUTCOME_MARKERS):
                return []
            # The existing semantic extractor supplies identity and user evidence;
            # deterministic code requires an exact owner-scoped target.
            if candidate.is_hypothetical or candidate.is_quoted or candidate.is_reported_speech:
                return []
            model = {"open_loop": OpenLoop, "attention": AttentionCandidate, "clarification": ClarificationCandidate}[kind]
            try:
                target_id = UUID(str(hint.get("target_id")))
            except ValueError:
                return []
            row = (await db.execute(select(model).where(model.id == target_id,
                model.honcho_workspace_id == workspace_id,
                model.owner_peer_id == owner_peer_id))).scalar_one_or_none() if owner_peer_id else None
            if row is None or hint.get("action") not in ("fulfill", "cancel", "supersede"):
                return []
            if kind == "open_loop":
                row.status = {"fulfill": OpenLoopStatus.RESOLVED, "cancel": OpenLoopStatus.ABANDONED,
                    "supersede": OpenLoopStatus.SUPERSEDED}[hint["action"]]
                row.resolution_evidence = f"honcho_message:{message_id}#candidate:{candidate.candidate_key}"
            elif kind == "clarification":
                row.status = ClarificationStatus.RESOLVED if hint["action"] == "fulfill" else ClarificationStatus.DISMISSED
            else:
                row.status = AttentionCandidateStatus.RESOLVED if hint["action"] == "fulfill" else AttentionCandidateStatus.DISMISSED
            row.updated_at = self._naive_utc(now)
            db.add(row)
            await db.commit()
            return [row.id]

        action = candidate.resolution_hint.get("action")
        evidence = f"honcho_message:{message_id}#candidate:{candidate.candidate_key}"
        modified_ids: List[UUID] = []

        stmt = select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.honcho_session_id == session_id,
            Expectation.outcome_state == OutcomeState.UNKNOWN,
            Expectation.source_system.is_(None),
        )
        res = await db.execute(stmt)
        active_expectations = list(res.scalars().all())
        targets = self._resolve_targets(active_expectations, candidate)
        if len(targets) != 1:
            # Resolve-before-clarify: a unique entity referent in the hint can
            # narrow the field to the single UNKNOWN expectation linked to
            # it, avoiding a question the evidence already answers.
            resolved = await self._resolve_target_via_entity(
                db, workspace_id=workspace_id, session_id=session_id,
                candidate=candidate, message_id=message_id,
                action=action, evidence=evidence,
                active_expectations=active_expectations,
            )
            if resolved is not None:
                return [resolved]
            await self._create_clarification(
                db, workspace_id, session_id, message_id, candidate,
                "Outcome or correction target is ambiguous",
                active_expectations, owner_peer_id=owner_peer_id,
            )
            return []

        exp = targets[0]
        evidence_text = " ".join(filter(None, [
            candidate.observation, candidate.canonical_title,
            str(candidate.resolution_hint.get("evidence") or ""),
        ]))
        # Phase-B promotion intent: recorded here, emitted post-commit below.
        # Only predicates with distinct endpoint content are emitted:
        # versioning supersession keeps identical titles (the v+1 row itself
        # is the record), and CANCELLED / NOT_FULFILLED have no bounded
        # predicate yet — both skipped, never force-fit.
        pending_promotion = None
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
                if not await self._fulfill_grounded(
                    db, exp=exp, evidence_text=evidence_text,
                    candidate=candidate, message_id=message_id,
                ):
                    # Lexically disconnected fulfillment claim with no semantic
                    # confirmation: leave UNKNOWN rather than fulfill wrongly.
                    # Rules mode (no adapter) keeps prior behavior.
                    return []
                exp.outcome_state = OutcomeState.FULFILLED
                pending_promotion = (
                    "fulfils",
                    candidate.observation or candidate.canonical_title or "",
                    exp.title,
                )
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
            exp.resolution_evidence = (
                f"superseded:revised_by_replacement:{replacement.id}"
            )
            await self._supersede_open_loops(db, exp.id, evidence)
        else:
            return []

        if not exp.resolution_evidence:
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
            # Phase-B deterministic promotion (advisory, post-commit).
            if pending_promotion is not None:
                rel_type, from_text, to_text = pending_promotion
                try:
                    await promote_transition(
                        db, workspace_id=workspace_id, rel_type=rel_type,
                        from_text=from_text, to_text=to_text,
                        source_key=evidence,
                        evidence_refs=[evidence],
                        subjects_from=[owner_peer_id] if owner_peer_id else [],
                        subjects_to=[exp.subject_peer_id] if exp.subject_peer_id else [],
                        formation="inferred", confidence=0.9)
                except Exception:
                    logger.exception(
                        "semantic promotion failed for outcome %s",
                        exp.outcome_state.value)

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
            Expectation.source_system.is_(None),
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
        Prior UNKNOWN expectations for the same owner describing the SAME plan
        are superseded onto it, so old 'tomorrow' rows cannot outlive newer
        evidence. Same-plan is deliberately strict: a shared subject pair, or
        high content-token overlap. Mere topical resemblance ("both turns were
        about the relationship") must NOT retire rows — that turns ingestion
        into a destructive FIFO queue."""
        stmt = select(Expectation).where(
            Expectation.honcho_workspace_id == expectation.honcho_workspace_id,
            Expectation.outcome_state == OutcomeState.UNKNOWN,
            Expectation.source_system.is_(None),
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
            row_tokens = self._significant_tokens(row.title)
            shared = row_tokens & new_tokens
            overlap = len(shared) / max(len(row_tokens), len(new_tokens), 1)
            if not (same_subject or overlap >= 0.6):
                continue
            row.outcome_state = OutcomeState.SUPERSEDED
            row.superseded_by_id = expectation.id
            row.resolution_evidence = (
                f"superseded:same_plan_replacement:{expectation.id}"
            )
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
            # Generic cognition verbs: every model-shaped title contains
            # them, so they carry no plan identity. Both inflected and stem
            # forms (the stemmer below adds stems separately).
            "reflecting", "reflect", "engaging", "engage", "continuing",
            "continue", "expressing", "express", "seeking", "seek",
            "questioning", "question", "exploring", "explore", "ongoing",
            "current", "indicating", "indicate", "suggesting", "suggest",
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
            Expectation.source_system.is_(None),
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
            evidence_text = f"{candidate.canonical_title or ''} {candidate.observation}"
            if not await self._fulfill_grounded(
                db, exp=exp, evidence_text=evidence_text,
                candidate=candidate, message_id=message_id,
            ):
                return []
            exp.outcome_state = OutcomeState.FULFILLED
        exp.resolution_evidence = evidence
        exp.updated_at = self._naive_utc(now)
        db.add(exp)
        await self._resolve_open_loop_for_expectation(db, exp.id, evidence)
        await db.commit()
        if not negative:
            # Phase-B deterministic promotion (advisory, post-commit).
            try:
                await promote_transition(
                    db, workspace_id=workspace_id, rel_type="fulfils",
                    from_text=candidate.observation or candidate.canonical_title or "",
                    to_text=exp.title,
                    source_key=evidence,
                    evidence_refs=[evidence],
                    subjects_to=[exp.subject_peer_id] if exp.subject_peer_id else [],
                    formation="inferred", confidence=0.9)
            except Exception:
                logger.exception("semantic promotion failed for explicit completion")
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

    async def close_answered_loops(
        self, db: AsyncSession, *, workspace_id: str, session_id: str,
        message_id: str, text: str, now: datetime,
    ) -> List[UUID]:
        """Structural release: a later turn that takes up a loop's unfinished
        matter resolves it, without requiring the original turn to have
        emitted a completion object. Single strict winner (best token overlap
        >= 0.5, strictly above runner-up, different message) or nothing —
        ambiguous continuations stay open rather than close wrongly."""
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.honcho_session_id == session_id,
            OpenLoop.status == OpenLoopStatus.OPEN,
            OpenLoop.honcho_message_id != message_id,
        ))).scalars().all()
        if not loops:
            return []
        turn_tokens = self._significant_tokens(text or "")
        if not turn_tokens:
            return []
        scored = []
        for loop in loops:
            loop_tokens = self._significant_tokens(
                f"{loop.title or ''} {loop.summary or ''}")
            if not loop_tokens:
                continue
            overlap = len(turn_tokens & loop_tokens) / max(len(loop_tokens), 1)
            scored.append((overlap, loop))
        scored.sort(key=lambda item: item[0], reverse=True)
        # Same bar as the completion matcher: the strict-winner rule (must
        # beat any runner-up outright) carries the safety, not the threshold.
        if not scored or scored[0][0] < 0.34:
            return []
        if len(scored) > 1 and scored[1][0] >= scored[0][0]:
            return []
        loop = scored[0][1]
        loop.status = OpenLoopStatus.RESOLVED
        loop.resolution_evidence = f"answered_in_turn:{message_id}"
        loop.updated_at = self._naive_utc(now)
        db.add(loop)
        await db.commit()
        # Phase-B deterministic promotion (advisory, post-commit): semantic
        # closure across vocabulary change, with its own provenance.
        try:
            await promote_transition(
                db, workspace_id=workspace_id, rel_type="resolves",
                from_text=text,
                to_text=f"{loop.title or ''} {loop.summary or ''}".strip() or "open loop",
                source_key=f"answered_in_turn:{message_id}",
                evidence_refs=[f"answered_in_turn:{message_id}"],
                subjects_to=[loop.owner_peer_id] if loop.owner_peer_id else [],
                formation="inferred", confidence=0.7)
        except Exception:
            logger.exception("semantic promotion failed for loop resolution")
        logger.info("Closed loop id=%s via later evidence %s", loop.id, message_id)
        return [loop.id]

    async def _resolve_target_via_entity(
        self, db: AsyncSession, *, workspace_id: str, session_id: str,
        candidate: ExtractionCandidate, message_id: str, action: Optional[str],
        evidence: str, active_expectations: List[Expectation],
    ) -> Optional[UUID]:
        """Resolve-before-clarify: when the hint names a textual target, try
        entity resolution first. A unique entity with exactly one linked
        UNKNOWN expectation takes the fulfill/cancel directly, so a question
        is asked only when evidence cannot answer it. Anything else falls
        through to clarification. Correct/reschedule need replacement
        machinery and are left to the clarification path."""
        if action not in ("fulfill", "cancel"):
            return None
        hint = candidate.resolution_hint or {}
        target_text = str(hint.get("target_text") or "").strip()
        if not target_text:
            return None
        from src.models.identity import EntityLink
        from src.services import entity_service
        entity, status = await entity_service.resolve_mention(
            db, workspace_id=workspace_id, session_id=session_id,
            mention=target_text, frame=None, message_id=message_id)
        if entity is None or status not in ("linked", "provisioned"):
            return None
        linked_ids = {
            link.object_id for link in (await db.execute(select(EntityLink).where(
                EntityLink.entity_id == entity.id,
                EntityLink.object_type == "expectation",
            ))).scalars().all()
        }
        options = [exp for exp in active_expectations if exp.id in linked_ids]
        if len(options) != 1:
            return None
        exp = options[0]
        exp.outcome_state = (
            OutcomeState.CANCELLED if action == "cancel" else OutcomeState.FULFILLED
        )
        exp.resolution_evidence = evidence
        exp.updated_at = self._naive_utc(datetime.now(timezone.utc))
        db.add(exp)
        await db.commit()
        if action == "fulfill":
            await self._resolve_open_loop_for_expectation(db, exp.id, evidence)
            try:
                await promote_transition(
                    db, workspace_id=workspace_id, rel_type="fulfils",
                    from_text=candidate.observation or candidate.canonical_title or "",
                    to_text=exp.title, source_key=evidence,
                    evidence_refs=[evidence],
                    subjects_from=[candidate.actor_peer_id] if getattr(
                        candidate, "actor_peer_id", None) else [],
                    subjects_to=[exp.subject_peer_id] if exp.subject_peer_id else [],
                    formation="inferred", confidence=0.9)
            except Exception:
                logger.exception("semantic promotion failed for entity-resolved fulfill")
        logger.info("Entity-resolved %s for expectation id=%s", action, exp.id)
        return exp.id

    async def _create_clarification(
        self, db: AsyncSession, workspace_id: str, session_id: str,
        message_id: str, candidate: ExtractionCandidate, description: str,
        possible_targets: List[Expectation], owner_peer_id: Optional[str] = None,
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
            owner_peer_id=owner_peer_id,
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

    async def _resolve_open_loop_for_expectation(        self, db: AsyncSession, expectation_id: UUID, evidence: str
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
            # Titles come from the model's own words: a loop row must say what
            # is unfinished. Hardcoded labels ("Open loop") made every loop
            # unmatchable and unjudgeable in replay.
            title=(candidate.canonical_title or candidate.open_loop_hint or "Open loop")[:280],
            summary=candidate.open_loop_hint or candidate.canonical_title,
            invited=bool(
                (candidate.open_loop_hint and "follow" in candidate.open_loop_hint.lower())
                or candidate.operational_kind == "open_loop"
            ),
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
        owner_peer_id: Optional[str] = None,
    ) -> Optional[Suppression]:
        if not candidate.suppression_hint:
            return None
        hint = dict(candidate.suppression_hint)
        if hint.get("ambiguous_target"):
            await self._create_clarification(
                db, workspace_id, session_id, message_id, candidate,
                "Suppression target is ambiguous", [], owner_peer_id=owner_peer_id,
            )
            return None
        # Direction gate: a suppression WRITE must prove its polarity. Turns
        # that invite, permit or request MORE of a topic must never become
        # suppressions (take-8: permission for emotional expression, pleas
        # for authenticity). Missing/unknown direction fails closed.
        # Ambiguous-target clarifications above are unaffected: they ask a
        # question rather than writing a suppression.
        direction = hint.get("direction")
        if direction not in ("refuse", "allow"):
            logger.warning("Suppression rejected: missing direction (msg=%s)", message_id)
            return None
        if direction == "allow" and hint.get("action") != "reopen":
            # Invitation/permission phrasing with suppression scaffolding is a
            # reopen at most, never a new suppression. Without an
            # identifiable topic there is nothing to reopen: drop it.
            if not hint.get("topic_or_entity"):
                return None
            hint["action"] = "reopen"

        if hint.get("ambiguous_target"):
            await self._create_clarification(
                db, workspace_id, session_id, message_id, candidate,
                "Suppression target is ambiguous", [], owner_peer_id=owner_peer_id,
            )
            return None
        if hint.get("action") == "reopen":
            topic = str(hint.get("topic_or_entity") or "").lower()
            stmt = select(Suppression).where(
                Suppression.honcho_workspace_id == workspace_id,
                or_(Suppression.owner_peer_id == owner_peer_id, and_(Suppression.owner_peer_id.is_(None), Suppression.honcho_session_id == session_id)) if owner_peer_id else Suppression.honcho_session_id == session_id,
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
            owner_peer_id=owner_peer_id,
            target_id=hint.get("target_id"),
            topic_or_entity=hint.get("topic_or_entity"),
            reason="user_explicit_suppression",
            surface_scope=hint.get("action_scope") or "all_surfaces",
            suppressed_until=suppressed_until,
            reopen_condition=hint.get("reopen_condition"),
            status=SuppressionStatus.ACTIVE,
            review_note=(str(hint.get("review_note"))[:500]
                         if isinstance(hint.get("review_note"), str) else None),
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
        owner_peer_id: Optional[str] = None,
    ) -> List[str]:
        """Consumer for stored reopen_condition.

        A suppression created with reopen_condition="user_mentions_topic"
        reopens the moment the user mentions the topic again. Subsequent turns
        are no longer suppressed by it.
        """
        lower = text.lower().replace("’", "'")
        if re.search(r"\b(don't|do not|stop|not want|rather not|leave it)\b", lower):
            return []
        candidates = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == workspace_id,
            or_(Suppression.owner_peer_id == owner_peer_id, and_(Suppression.owner_peer_id.is_(None), Suppression.honcho_session_id == session_id)) if owner_peer_id else Suppression.honcho_session_id == session_id,
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
