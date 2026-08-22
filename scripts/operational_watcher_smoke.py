"""Live-model pre-release smoke for the natural-language failure corpus."""
import json

from src.services.turn_extractor import LLMExtractorProvider


TURNS = [
    "I want to get a proper walk in every day, ideally about an hour.",
    "I still need to apply for jobs.",
    "I'd like to check in with Ashley later and see how her event went.",
    "I sent three applications today but I still need to keep applying.",
    "Actually forget the ten-minute tidy thing. I'm not doing that every day.",
    "I'm working on Bluum because I want to create a tiny daily gratitude ritual that genuinely helps people feel better.",
    "I need to start exercising properly again, but I haven't really turned it into a routine yet.",
]


def main() -> None:
    provider = LLMExtractorProvider(fallback_on_error=False)
    rows = []
    for turn in TURNS:
        candidates = provider.extract(turn, peer_id="smoke-user")
        rows.append({
            "turn": turn,
            "backend": provider.last_backend,
            "failure": provider.last_failure,
            "loose_observations": [item.model_dump(mode="json") for item in provider.last_observations],
            "shaped_candidates": [item.model_dump(mode="json") for item in candidates],
            "stage_metrics": provider.last_stage_metrics,
        })
    print(json.dumps(rows, indent=2))
    failures = [row for row in rows if row["backend"] != "model" or not row["loose_observations"]]
    if failures:
        raise SystemExit(f"live watcher smoke failed for {len(failures)}/{len(rows)} turns")


if __name__ == "__main__":
    main()
