import json
import logging
import os
from typing import Dict, Any, List

from src.services.turn_extractor import RuleBasedExtractorProvider, LLMExtractorProvider
from src.services.expectation_shaper import ExpectationShaper

logger = logging.getLogger("eval_runner")
shaper = ExpectationShaper()


def run_evaluation(provider, provider_name: str, fixtures: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(fixtures)
    tp = 0  # True positives: correctly identified state that should persist
    fp = 0  # False positives: persisted state when should_persist is False
    tn = 0  # True negatives: correctly rejected non-state turn
    fn = 0  # False negatives: failed to persist valid state
    
    type_matches = 0
    actor_matches = 0
    type_evaluated_total = 0
    actor_evaluated_total = 0
    candidate_count_matches = 0

    for fix in fixtures:
        text = fix["text"]
        peer_id = fix.get("peer_id", "mukesh")
        should_persist = fix.get("should_persist", False)
        
        candidates = provider.extract(text, peer_id=peer_id)
        if len(candidates) == fix.get("expected_candidates", len(candidates)):
            candidate_count_matches += 1
        
        # Shape candidates
        persisted_candidates = []
        for cand in candidates:
            shaped = shaper.shape_expectation(cand, peer_id)
            if shaped:
                persisted_candidates.append((cand, shaped))

        did_persist = len(persisted_candidates) > 0

        if should_persist and did_persist:
            tp += 1
            # Check type & actor match if specified
            exp_type = fix.get("expected_type")
            exp_actor = fix.get("expected_actor")
            
            cand_0, shaped_0 = persisted_candidates[0]
            if exp_type:
                type_evaluated_total += 1
                if shaped_0["expectation_type"].value == exp_type:
                    type_matches += 1
                    
            if exp_actor:
                actor_evaluated_total += 1
                if shaped_0["subject_peer_id"] == exp_actor or cand_0.actor_peer_id == exp_actor:
                    actor_matches += 1

        elif not should_persist and not did_persist:
            tn += 1
        elif not should_persist and did_persist:
            fp += 1
        elif should_persist and not did_persist:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    accuracy = (tp + tn) / total if total > 0 else 1.0
    fp_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    type_acc = type_matches / type_evaluated_total if type_evaluated_total > 0 else 1.0

    return {
        "provider": provider_name,
        "total_fixtures": total,
        "true_positives": tp,
        "true_negatives": tn,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "accuracy": round(accuracy, 4),
        "false_positive_rate": round(fp_rate, 4),
        "expectation_type_accuracy": round(type_acc, 4),
        "actor_attribution_accuracy": round(actor_matches / actor_evaluated_total, 4) if actor_evaluated_total > 0 else 1.0,
        "candidate_count_accuracy": round(candidate_count_matches / total, 4) if total else 1.0,
        "metric_scope": "expectation persistence only; lifecycle hints are not scored",
    }


def main():
    with open("evals/fixtures.json", "r") as f:
        fixtures = json.load(f)
    adversarial_path = "evals/adversarial_fixtures.json"
    if os.path.exists(adversarial_path):
        with open(adversarial_path, "r") as f:
            fixtures.extend(json.load(f))

    print(f"Loaded {len(fixtures)} fixtures from evals/fixtures.json\n")

    # 1. Evaluate Rule-Based Provider
    rule_provider = RuleBasedExtractorProvider()
    rule_metrics = run_evaluation(rule_provider, "RuleBasedExtractorProvider", fixtures)

    print("==================================================")
    print("      SYNAPSE-CORTEX V4 EVALUATION REPORT        ")
    print("==================================================")
    print(f"Provider:                   {rule_metrics['provider']}")
    print(f"Total Fixtures Evaluated:   {rule_metrics['total_fixtures']}")
    print(f"True Positives:             {rule_metrics['true_positives']}")
    print(f"True Negatives:             {rule_metrics['true_negatives']}")
    print(f"False Positives:            {rule_metrics['false_positives']}")
    print(f"False Negatives:            {rule_metrics['false_negatives']}")
    print(f"Precision:                  {rule_metrics['precision'] * 100:.2f}%")
    print(f"Recall:                     {rule_metrics['recall'] * 100:.2f}%")
    print(f"Overall Accuracy:           {rule_metrics['accuracy'] * 100:.2f}%")
    print(f"False Positive Rate:        {rule_metrics['false_positive_rate'] * 100:.2f}%")
    print(f"Type Classification Acc:    {rule_metrics['expectation_type_accuracy'] * 100:.2f}%")
    print(f"Actor Attribution Acc:      {rule_metrics['actor_attribution_accuracy'] * 100:.2f}%")
    print("==================================================\n")

    model_metrics = None
    if os.getenv("OPENAI_API_KEY") or os.getenv("XAI_API_KEY"):
        try:
            model_provider = LLMExtractorProvider(fallback_on_error=False)
            model_metrics = run_evaluation(model_provider, "LLMExtractorProvider", fixtures)
            print("MODEL PROVIDER")
            print(json.dumps(model_metrics, indent=2))
        except Exception as err:
            print(f"MODEL PROVIDER: unavailable ({err})")
    else:
        print("MODEL PROVIDER: not run (credentials unavailable; no rule fallback counted as model)\n")

    # Save results to evals/results.json
    results = {"rule_based": rule_metrics, "model": model_metrics}
    with open("evals/results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
