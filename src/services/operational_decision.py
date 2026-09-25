"""Operationalisation decisions: form vs authority, structurally separated.

Given an understood matter, decide (1) which operational form fits
(calendar/task/reminder/watch/waiting/chase/clarify/plan/callback/share/
narrative/nothing) from deterministic signals (grounded time, ownership,
dependency, recurrence, model-judged texture already in state), and
(2) whether authority exists to execute it.

Authority rule: nothing external is created unless an existing explicit
authority path permits it (user-issued command with ACT authority, or
machinery that already executes like reminder windows / occurrence ledger).
Otherwise the decision is propose/hold/output — never silent execution.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FORMS = ("calendar", "task", "reminder", "watch", "waiting", "chase",
         "clarify", "plan", "callback", "share", "narrative", "nothing")


@dataclass(frozen=True)
class OperationalDecision:
    matter_kind: str
    matter_id: str
    title: str
    form: str
    authorized: bool
    via: str  # existing authority path, or "none"
    action: str  # execute | propose | hold | output | nothing
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def decide_for_view_item(item: Dict[str, Any], *, owner_peer_id: Optional[str],
                         now: datetime) -> OperationalDecision:
    """Pure decision over one view item. No DB, no execution."""
    kind = str(item.get("kind") or "")
    title = str(item.get("title") or "matter")
    matter_id = str(item.get("id") or "")
    why = str(item.get("why") or "")

    if kind in ("reminder", "occurrence"):
        return OperationalDecision(
            kind, matter_id, title, form="reminder", authorized=True,
            via="reminder_windows/occurrence_ledger",
            action="execute" if kind == "occurrence" else "propose",
            reason="due window machinery already governs execution")
    if kind == "event" or "planned event" in why:
        # Calendar-shaped, but creation needs an explicit user command.
        return OperationalDecision(
            kind, matter_id, title, form="calendar", authorized=False,
            via="none", action="propose",
            reason="fixed-time shape without explicit create authority")
    if kind in ("waiting", "graph") and "waiting" in (why + kind):
        return OperationalDecision(
            kind, matter_id, title, form="waiting", authorized=True,
            via="internal_watch", action="execute",
            reason="waiting-on is internal monitoring, no external effect")
    if kind == "graph":
        return OperationalDecision(
            kind, matter_id, title, form="watch", authorized=True,
            via="internal_watch", action="execute",
            reason="graph-derived watch stays internal")
    if kind in ("followup", "clarification", "open_loop"):
        return OperationalDecision(
            kind, matter_id, title, form="chase" if "reentry" in why or "loop" in kind else "clarify",
            authorized=False, via="none", action="propose",
            reason="user-facing contact needs runtime surfacing decision")
    if kind in ("attention",):
        return OperationalDecision(
            kind, matter_id, title, form="callback", authorized=False,
            via="none", action="hold",
            reason="callback opportunity held for initiative policy")
    if kind in ("annotation",):
        return OperationalDecision(
            kind, matter_id, title, form="watch", authorized=True,
            via="internal_watch", action="execute",
            reason="worry context monitored silently")
    if kind in ("commitment", "work_item"):
        return OperationalDecision(
            kind, matter_id, title, form="task", authorized=False,
            via="none", action="propose",
            reason="task shape without task-create authority")
    if kind in ("expectation", "todo"):
        return OperationalDecision(
            kind, matter_id, title, form="task", authorized=False,
            via="none", action="hold",
            reason="tracked as todo; operational form deferred")
    return OperationalDecision(
        kind, matter_id, title, form="nothing", authorized=True,
        via="none", action="nothing", reason="no operational shape warranted")


def decide_views(views: Dict[str, List[Dict[str, Any]]], *,
                 owner_peer_id: Optional[str],
                 now: datetime) -> Dict[str, List[Dict[str, Any]]]:
    """Decide per view section. Pure; returns decisions grouped by view."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for section, view_items in views.items():
        decisions = []
        for item in view_items or []:
            if not isinstance(item, dict):
                continue
            try:
                decisions.append(decide_for_view_item(
                    item, owner_peer_id=owner_peer_id, now=now).to_dict())
            except Exception as err:
                logger.warning("operational decision failed: %s", err)
        out[section] = decisions
    return out
