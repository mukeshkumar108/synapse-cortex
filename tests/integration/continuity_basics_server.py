"""Local contract server. External semantic extraction is scripted explicitly.
Never deploy this module. All HTTP, storage, lifecycle and packet code is real.
"""
from src.main import app
from src.routers import v1_events
from src.schemas.candidate import ExtractionCandidate
from src.services.turn_extractor import RuleBasedExtractorProvider

class ContractProvider(RuleBasedExtractorProvider):
    def extract(self, text, peer_id=None, prior_state=None):
        if text == 'I am planning to apply to Cambridge.':
            return [ExtractionCandidate(candidate_key='cambridge-intention', observation=text,
                raw_evidence=text, source_start=0, source_end=len(text), actor_peer_id=peer_id,
                operational_kind='open_loop', canonical_title='Cambridge application',
                open_loop_hint='Cambridge application', confidence=.95)]
        if text == "I don't want to talk about that.":
            # Scripted semantic decision; prior state supplies the owner-scoped
            # topic being suppressed. This is not an extraction-quality test.
            topics=(prior_state or {}).get('attention') or []
            if topics:
                return [ExtractionCandidate(candidate_key='suppress-hospital',observation=text,
                    raw_evidence=text,source_start=0,source_end=len(text),actor_peer_id=peer_id,
                    operational_kind='suppression',suppression_hint={'target_type':'topic',
                        'topic_or_entity':'Friend in hospital','reason':'user_explicit_suppression',
                        'reopen_condition':'user_mentions_topic','surface_scope':'all_surfaces'})]
        return super().extract(text,peer_id=peer_id,prior_state=prior_state)

v1_events.turn_extractor.provider=ContractProvider()
