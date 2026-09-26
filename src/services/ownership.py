"""Bilateral ownership resolution (Step 3 Slice 2).

A companion relationship has two actors. Rows about character-owned content
(promises, expectations, facts) must be ownable by the character peer — but
only when the extractor attributes content to an explicit, evidenced peer id.
Generic role words and hallucinated peers fall back to the turn sender, so a
model slip can never strand rows on ghost owners or launder assistant text
into user authority.

Future dreaming cognition writes companion-owned inferred rows directly with
holder=companion; this helper governs turn-extraction attribution only.
"""
from typing import Collection, Optional

_GENERIC_ACTORS = frozenset({"", "user", "assistant", "system", "unknown", "nobody"})


def resolve_owner(
    sender_peer_id: str,
    actor_peer_id: Optional[str],
    known_peer_ids: Collection[str] = (),
) -> str:
    """Owner for a newly persisted row derived from a turn candidate."""
    actor = (actor_peer_id or "").strip()
    if not actor or actor.lower() in _GENERIC_ACTORS:
        return sender_peer_id
    if actor == sender_peer_id or actor in set(known_peer_ids or ()):
        return actor
    return sender_peer_id


def is_external_counterparty(owner_peer_id: str) -> bool:
    """Return whether resolved ownership identifies a non-user sender.

    External feeds preserve their speaker identity as ``external:<sender>``.
    Extractor labels (types, hints, categories) are model-derived and
    fallible; this provenance is supplied by the ingest adapter at the turn
    boundary, so it is the authoritative signal for whether a row may be
    minted as user/companion-owned action state (a commitment the user/
    companion is bound to, or an expectation asserting the user/companion as
    the acting party) versus longitudinal evidence about a third party.
    """
    return (owner_peer_id or "").strip().casefold().startswith("external:")
