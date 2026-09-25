"""Phase-A shadow prototype — SHADOW ONLY.

Hard constraints (do not relax):
- No schema migration, no new production table, no foreground integration.
- No imports from src.models, src.services, src.routers, src.db.
  This package is stdlib-only + reads fixture JSON. It never writes prod state.
- Existing production output remains authoritative. Shadow output is
  separately inspectable and disposable (reports/shadow_phase_a_output.json).
- No new primitive: claims/relations/roles/views/moves below are in-memory
  proposal structs for evaluation, not persisted domain tables.
"""

__all__ = []
