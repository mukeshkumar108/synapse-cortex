"""Live check of the cases the keyword guards in turn_extractor used to correct, against the real extractor model.

Run with the NanoGPT key in the environment (LLM_NANO_ONLY=true SYNAPSE_EXTRACTOR_MODEL=<model>). Prints what the model did with each message
so a person can read it; it asserts nothing, because the point is to see the model's own interpretation.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.services.turn_extractor import LLMExtractorProvider

CASES = [
    "yes, I need to fix this audio transcription bug because it's been happening every single day, so you need to remind me keep on top of me",
    "we talk everyday obviously",
    "I try to walk most mornings before work",
    "I want to do morning and evening prayers every day",
    "I take my medication every morning",
    "my goal is at least 10k steps per day",
    "I haven't really built a habit of flossing yet, but I should do it daily",
    "honestly the garden is more interesting than the shed project right now",
    "I'm working on the app because I want to build something people actually use",
    "fine to talk about my sister now",
    "I don't want it to feel clinical when you check in",
    "I'm thinking about maybe getting back into running",
]
p = LLMExtractorProvider()
print("model:", p.model, "key:", bool(p.api_key))
for text in CASES:
    out = p.extract(text, peer_id="u")
    print("\n>>", text)
    print("   backend:", p.last_backend, "failure:", p.last_failure)
    for c in out:
        d = c.model_dump(mode="json")
        print("   ", {k: d.get(k) for k in ("operational_kind", "recurrence_semantic_type", "cadence", "confidence", "canonical_title", "suppression_hint") if d.get(k) is not None})
