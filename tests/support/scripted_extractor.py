"""A scripted extraction provider for tests of everything downstream of extraction.

There is no keyword extractor any more, so a test that needs "this message produced these candidates" says so
explicitly: the table in tests/fixtures/scripted_extractions.json maps a message text to the candidates a model
would have returned. An unscripted text yields nothing, exactly as a failed extraction does. Set
SCRIPTED_EXTRACTIONS_RECORD=<path to the old keyword module> to regenerate entries (one-off migration use only).
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.schemas.candidate import ExtractionCandidate
from src.services.turn_extractor import BaseExtractorProvider

TABLE = Path(__file__).resolve().parent.parent / "fixtures" / "scripted_extractions.json"


def _load() -> Dict[str, List[dict]]:
    try:
        return json.loads(TABLE.read_text())
    except FileNotFoundError:
        return {}


class ScriptedExtractor(BaseExtractorProvider):
    def __init__(self, table: Optional[Dict[str, List[dict]]] = None):
        self.table = _load() if table is None else table
        self.last_backend = "model"
        self.last_failure = None
        self.last_observations: list = []
        self.misses: List[str] = []
        self._recorder = None
        old = os.getenv("SCRIPTED_EXTRACTIONS_RECORD")
        if old:
            import importlib.util
            spec = importlib.util.spec_from_file_location("old_turn_extractor", old)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self._recorder = mod.RuleBasedExtractorProvider()

    def extract(self, text: str, peer_id: Optional[str] = None,
                prior_state: Optional[Dict[str, Any]] = None) -> List[ExtractionCandidate]:
        if self._recorder is not None and text not in self.table:
            fresh = _load()                      # several instances record in one run: merge, never overwrite another's entries
            fresh[text] = [c.model_dump(mode="json") for c in self._recorder.extract(text, peer_id=peer_id)]
            TABLE.write_text(json.dumps(fresh, indent=1, ensure_ascii=False, sort_keys=True))
            self.table = fresh
        rows = self.table.get(text)
        if rows is None:
            self.misses.append(text)
            return []
        out = []
        for row in rows:
            row = dict(row)
            if peer_id is not None and row.get("actor_peer_id") in (None, "mukesh", "u", "user"):
                row["actor_peer_id"] = peer_id if row.get("actor_peer_id") is not None else None
            out.append(ExtractionCandidate(**row))
        return out
