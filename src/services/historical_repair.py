"""Controlled historical reconciliation/repair (CP2).

The live historical state contains extraction/lifecycle pollution (e.g. stale
"take a shower now" expectations, narration promoted to expectation, one-off
work turned into a daily recurring intention, weakly-fulfilled recurrences).

Principles:
- Evidence is never deleted. Only derived state is repaired.
- Classification is deterministic and inspectable (a report first).
- Mutations are limited to: superseding exact duplicates, and writing
  epistemic annotations that mark re-extraction candidates.
- Sensitive material is reclassified backstage by annotation, not removed.

Run as: python -m scripts.repair_history --workspace WS [--apply]
Without --apply it is a dry-run report.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy import or_, and_
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.expectation import Expectation, OutcomeState, ExpectationType
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.operational_state import (
    RecurringIntention, RecurringOccurrence, OperationalStatus,
)
from src.models.epistemic import EpistemicAnnotation, EpistemicProvenance
from src.services.cortex_packet_service import ELAPSED_EXPECTATION_FOREGROUND_HOURS

# Life narration cues that must never have become foreground expectations.
# Used only as a *repair* heuristic over historical rows, never as an
# extraction-time rule, and never for sensitivity decisions.
NARRATION_CUES = (
    "ordered a", "went to the toilet", "made a coffee", "ordered a flat white",
    "take a shower now", "brushed teeth", "had lunch", "had dinner",
    "made tea", "took a shower",
)


@dataclass
class RepairAction:
    target_type: str
    target_id: str
    title: str
    classification: str
    action: str  # 'none' | 'supersede' | 'annotate_reextract' | 'annotate_backstage'
    reason: str


@dataclass
class RepairReport:
    workspace_id: str
    generated_at: str
    actions: List[RepairAction] = field(default_factory=list)
    applied: bool = False

    def summary(self) -> Dict:
        counts: Dict[str, int] = {}
        for action in self.actions:
            counts[action.classification] = counts.get(action.classification, 0) + 1
        return {
            "workspace_id": self.workspace_id,
            "generated_at": self.generated_at,
            "total_actions": len(self.actions),
            "by_classification": counts,
            "applied": self.applied,
        }


class HistoricalRepairService:
    """Classifies historical polluted state and repairs derived state only."""

    async def classify_and_repair(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        now: datetime,
        apply: bool = False,
        owner_peer_id: str | None = None,
    ) -> RepairReport:
        report = RepairReport(
            workspace_id=workspace_id,
            generated_at=now.isoformat(),
            applied=apply,
        )
        now_utc = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now
        stale_cutoff = now_utc - timedelta(
            hours=ELAPSED_EXPECTATION_FOREGROUND_HOURS
        )

        stmt = select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.superseded_by_id.is_(None),
        )
        expectations = (await db.execute(stmt)).scalars().all()

        seen_keys: Dict[str, Expectation] = {}
        for exp in expectations:
            title_fold = " ".join((exp.title or "").lower().split())
            text = f"{exp.title} {exp.summary}".lower()

            # 1. Exact duplicates: same normalized title, keep the earliest.
            if title_fold in seen_keys:
                original = seen_keys[title_fold]
                action = RepairAction(
                    target_type="expectation", target_id=str(exp.id),
                    title=exp.title, classification="duplicate",
                    action="supersede",
                    reason=f"duplicate of {original.id} (same normalized title)",
                )
                report.actions.append(action)
                if apply:
                    exp.superseded_by_id = original.id
                    exp.outcome_state = OutcomeState.SUPERSEDED
                    db.add(exp)
                continue
            seen_keys[title_fold] = exp

            # Terminal states are historical evidence; leave untouched.
            if exp.outcome_state in (
                OutcomeState.FULFILLED, OutcomeState.CANCELLED,
                OutcomeState.SUPERSEDED,
            ):
                report.actions.append(RepairAction(
                    target_type="expectation", target_id=str(exp.id),
                    title=exp.title, classification="valid",
                    action="none", reason=f"terminal: {exp.outcome_state.value}",
                ))
                continue

            window_end = exp.expected_window_end
            if window_end is not None and window_end.tzinfo is not None:
                window_end = window_end.astimezone(timezone.utc).replace(tzinfo=None)
            window_elapsed = bool(
                window_end and window_end < stale_cutoff
            ) and exp.outcome_state == OutcomeState.UNKNOWN

            # 2. Narration promoted to expectation -> re-extraction candidate.
            if any(cue in text for cue in NARRATION_CUES) and not exp.source_system:
                report.actions.append(RepairAction(
                    target_type="expectation", target_id=str(exp.id),
                    title=exp.title, classification="incorrectly_typed",
                    action="annotate_reextract",
                    reason="life narration was promoted to an expectation",
                ))
                if apply:
                    await self._annotate(
                        db, exp, now_utc,
                        claim=(
                            "Historical extraction likely promoted ordinary "
                            "life narration into an expectation; re-extract "
                            "as semantic_only."
                        ),
                    )
                continue

            # 3. Stale unknown: should expire from foreground (packet already
            # enforces the 36h bound); mark re-extraction if it also looks
            # like narration, otherwise leave as inspectable unresolved.
            if window_elapsed:
                report.actions.append(RepairAction(
                    target_type="expectation", target_id=str(exp.id),
                    title=exp.title, classification="stale_unresolved",
                    action="none",
                    reason=(
                        "outcome unknown and window long elapsed; foreground "
                        "expiry is enforced by the packet, row stays inspectable"
                    ),
                ))
                continue

            report.actions.append(RepairAction(
                target_type="expectation", target_id=str(exp.id),
                title=exp.title, classification="valid",
                action="none", reason="active state with live temporal semantics",
            ))

        # 4. Recurring intentions with no fulfilled occurrence and no cadence
        # corroboration are candidates for re-extraction (e.g. one-off work
        # turned into a daily recurrence). The definition and its occurrences
        # are preserved; only a re-extraction annotation is added.
        rec_stmt = select(RecurringIntention).where(
            RecurringIntention.honcho_workspace_id == workspace_id,
            RecurringIntention.status == OperationalStatus.ACTIVE,
        )
        recurrences = (await db.execute(rec_stmt)).scalars().all()
        for recurrence in recurrences:
            occ_stmt = select(RecurringOccurrence).where(
                RecurringOccurrence.recurring_intention_id == recurrence.id,
            )
            occurrences = (await db.execute(occ_stmt)).scalars().all()
            fulfilled = [o for o in occurrences if str(getattr(o.status, "value", o.status)) == "fulfilled"]
            if not fulfilled:
                report.actions.append(RepairAction(
                    target_type="recurring_intention",
                    target_id=str(recurrence.id),
                    title=recurrence.title,
                    classification="reextract_candidate",
                    action="annotate_reextract",
                    reason=(
                        "no occurrence has ever been fulfilled; verify the "
                        "cadence is real, not a one-off promotion"
                    ),
                ))
                if apply:
                    await self._annotate(
                        db, None, now_utc,
                        claim=(
                            f"Recurring intention '{recurrence.title}' has no "
                            "fulfilled occurrence; verify cadence before "
                            "treating it as an established routine."
                        ),
                        target_loop_id=recurrence.id,
                    )
            else:
                report.actions.append(RepairAction(
                    target_type="recurring_intention",
                    target_id=str(recurrence.id),
                    title=recurrence.title,
                    classification="valid", action="none",
                    reason=f"{len(fulfilled)} fulfilled occurrence(s)",
                ))

        # 5. Resolved open loops / old open loops are inspected via the
        # unresolved horizon; nothing to mutate.
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.status == OpenLoopStatus.OPEN,
        ))).scalars().all()
        for loop in loops:
            report.actions.append(RepairAction(
                target_type="open_loop", target_id=str(loop.id),
                title=loop.title, classification="valid", action="none",
                reason="open loop participates in the unresolved horizon",
            ))

        if apply:
            await db.commit()
        return report

    async def _annotate(
        self,
        db: AsyncSession,
        exp: Expectation | None,
        now: datetime,
        *,
        claim: str,
        target_loop_id=None,
    ) -> None:
        annotation = EpistemicAnnotation(
            honcho_workspace_id=exp.honcho_workspace_id if exp else "",
            honcho_session_id=exp.honcho_session_id if exp else "",
            honcho_message_id=exp.honcho_message_id if exp else "repair-pass",
            candidate_key="historical-repair",
            target_expectation_id=exp.id if exp else None,
            target_loop_id=target_loop_id,
            perspective_peer_id="system:historical-repair",
            provenance_type=EpistemicProvenance.INFERENCE,
            claim_summary=claim,
            confidence=0.8,
        )
        db.add(annotation)
