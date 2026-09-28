"""Evidence corpus loader: frozen S1-S4 fixtures as the retrieval substrate.

This is the offline stand-in for "Honcho evidence storage": the same 53
events ingested into the VPS probe workspace (rerun report §2). Timestamps,
speakers, source types and verbatim content are preserved exactly as
committed. Oracle files are NEVER loaded here (blindness: synthesis sees
questions + evidence only).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from src.longitudinal_read.models import EvidenceItem

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "evals" / "sophie_longitudinal"

INPUT_FILES = [
    "scenario_1_ashley_event_ops_input.json",
    "scenario_2_ordinary_sophie_plans_input.json",
    "scenario_3_multisource_conflict_input.json",
    "scenario_4_health_worry_texture_input.json",
]

# Matter tags per event: which bounded matter(s) an event can bear on.
# Tags are retrieval hints, not answers. Kept deliberately coarse so the
# synthesis gates (not the tags) do the judgement work.
MATTER_TAGS: Dict[str, List[str]] = {
    "s1_e01": ["carlos_debt", "school_payment", "matias_form", "yoshi_activity"],
    "s1_e02": ["matias_form"],
    "s1_e03": ["carlos_debt"],
    "s1_e04": ["carlos_debt"],
    "s1_e05": ["chairs"],
    "s1_e06": ["yoshi_activity"],
    "s1_e07": ["carlos_debt", "chairs"],
    "s1_e08": ["florist"],
    "s1_e09": ["carlos_debt", "florist", "yoshi_activity", "matias_form"],
    "s1_e10": ["surfacing_restraint"],
    "s1_e11": ["carlos_debt", "matias_form"],
    "s1_e12": ["school_payment"],
    "s1_e13": ["school_payment"],
    "s1_e14": ["carlos_debt"],
    "s2_e01": ["noise"],
    "s2_e02": ["noise"],
    "s2_e03": ["noise"],
    "s2_e04": ["noise"],
    "s2_e05": ["noise"],
    "s2_e06": ["noise"],
    "s2_e07": ["noise"],
    "s2_e08": ["noise"],
    "s2_e09": ["noise"],
    "s2_e10": ["noise"],
    "s3_e01": ["studio_contract", "cousin_pickup", "lucy_payment", "sam_identity"],
    "s3_e02": ["lucy_payment"],
    "s3_e03": ["studio_contract", "sam_identity"],
    "s3_e04": ["dentist"],
    "s3_e05": ["studio_contract", "lucy_payment", "dentist"],
    "s3_e06": ["studio_contract", "lucy_payment", "sam_identity"],
    "s3_e07": ["studio_contract", "sam_identity"],
    "s3_e08": ["lucy_payment"],
    "s3_e09": ["cousin_pickup", "lucy_payment", "sam_identity"],
    "s3_e10": ["cousin_pickup"],
    "s3_e11": ["cousin_pickup", "studio_contract"],
    "s3_e12": ["studio_contract", "sam_identity"],
    "s3_e13": ["studio_contract", "sam_identity"],
    "s3_e14": ["studio_contract"],
    "s4_e01": ["neck_watch", "headache_single"],
    "s4_e02": ["neck_watch"],
    "s4_e03": ["noise"],
    "s4_e04": ["neck_watch", "noise"],
    "s4_e05": ["noise"],
    "s4_e06": ["neck_watch"],
    "s4_e07": ["neck_watch"],
    "s4_e08": ["noise"],
    "s4_e09": ["noise"],
    "s4_e10": ["neck_watch"],
    "s4_e11": ["neck_watch"],
    "s4_e12": ["noise"],
    "s4_e13": ["noise"],
    "s4_e14": ["noise"],
    "s4_e15": ["noise"],
}

ENTITY_TAGS: Dict[str, List[str]] = {
    "s3_e01": ["sam_studio", "sam_cousin"],
    "s3_e03": ["sam_studio"],
    "s3_e06": ["sam_studio"],
    "s3_e07": ["sam_studio"],
    "s3_e09": ["sam_cousin"],
    "s3_e10": ["sam_cousin"],
    "s3_e11": ["sam_cousin"],
    "s3_e12": ["sam_studio"],
    "s3_e13": ["sam_studio", "sam_cousin"],
    "s3_e14": ["sam_studio"],
}


def load_corpus() -> List[EvidenceItem]:
    items: List[EvidenceItem] = []
    for name in INPUT_FILES:
        scenario = name.split("_input")[0]
        raw = json.loads((FIXTURE_DIR / name).read_text())
        for ev in raw["events"]:
            eid = ev["id"]
            items.append(
                EvidenceItem(
                    event_id=eid,
                    timestamp=ev["timestamp"],
                    sender=ev.get("sender", ""),
                    role=ev.get("role", ""),
                    source_type=ev.get("source_type", ""),
                    content=ev.get("content", ""),
                    provenance=f"fixture:{scenario}:{eid}",
                    matter_tags=list(MATTER_TAGS.get(eid, [])),
                    entity_tags=list(ENTITY_TAGS.get(eid, [])),
                )
            )
    items.sort(key=lambda e: e.timestamp)
    return items
