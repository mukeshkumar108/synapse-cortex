"""Query discipline: every read must be pulled by a specific current need.

Banned (recreate the killed broad-scanning architecture):
  analyse the user / what matters in their life / find important patterns /
  what should the companion know / any generic profile-dossier request.
"""

from __future__ import annotations

import re

BANNED_PATTERNS = [
    r"\banalyse the user\b",
    r"\banalyze the user\b",
    r"\bwhat matters in their life\b",
    r"\bwhat matters in (his|her|your) life\b",
    r"\bfind important patterns\b",
    r"\bfind (all |any )?patterns\b",
    r"\bwhat should the companion know\b",
    r"\bget_?user_?profile\b",
    r"\buser profile\b",
    r"\bdossier\b",
    r"\btell me about (the user|this person|them)\b",
    r"\bsummarise the (user|person)\b",
    r"\bsummarize the (user|person)\b",
]


class QueryRejected(ValueError):
    pass


def validate_bounded(question: str, scope: str, need: str) -> None:
    """Raise QueryRejected if the request is open-ended scanning."""
    q = (question or "").lower()
    for pat in BANNED_PATTERNS:
        if re.search(pat, q):
            raise QueryRejected(f"open-ended scan refused (pattern {pat!r})")
    if not (question or "").strip():
        raise QueryRejected("empty question")
    if not (scope or "").strip():
        raise QueryRejected("scope is required: reads must be matter/frame bounded")
    if (scope or "").strip().lower() in {"user", "person", "life", "all", "everything"}:
        raise QueryRejected("scope too broad: must name a matter/frame, never 'the user'")
    if not (need or "").strip():
        raise QueryRejected("need is required: every read must be pulled by a current need")
