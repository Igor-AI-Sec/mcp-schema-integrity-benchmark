"""Runs the detector over fixtures/mutation_corpus.json and produces results/results.json.

This is the one place actual numbers get computed — nothing in this
project hand-writes a metric; results.json is always the output of
running this module against the fixture corpus.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .classify import ALL_CATEGORIES
from .detector import SchemaIntegrityMonitor
from .registry import ToolRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS_PATH = PROJECT_ROOT / "fixtures" / "mutation_corpus.json"
DEFAULT_RESULTS_PATH = PROJECT_ROOT / "results" / "results.json"

UNMUTATED_LABEL = "unmutated_control"


def load_corpus(path: Path = DEFAULT_CORPUS_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_case(case: dict) -> dict:
    """Run one corpus case through a fresh registry + monitor and score it against ground truth.

    Two different questions get two different, unambiguous fields:
    `detection_correct` answers "did the yes/no mutated call match reality"
    (meaningful for every case, including controls). `category_classification_correct`
    answers "was the *category* right" and is only meaningful for cases that
    actually contain a mutation — it's `None` (not applicable) for
    unmutated controls, rather than a misleading `False` for a case where
    there was never a category to get right in the first place.
    """
    registry = ToolRegistry()
    registry.register(case["tool_name"], case["original_schema"])
    monitor = SchemaIntegrityMonitor(registry)

    result = monitor.check(case["tool_name"], case["presented_schema"])

    ground_truth_category = case["ground_truth_category"]
    actually_mutated = ground_truth_category != UNMUTATED_LABEL
    detection_correct = result.mutated == actually_mutated

    if not actually_mutated:
        category_classification_correct = None
    elif not result.mutated:
        category_classification_correct = False
    else:
        category_classification_correct = ground_truth_category in result.mutation_categories

    return {
        "case_id": case["case_id"],
        "tool_name": case["tool_name"],
        "ground_truth_category": ground_truth_category,
        "actually_mutated": actually_mutated,
        "predicted_mutated": result.mutated,
        "detection_correct": detection_correct,
        "predicted_categories": sorted(result.mutation_categories),
        "category_classification_correct": category_classification_correct,
    }


def compute_metrics(case_results: list[dict]) -> dict:
    actual_mutations = [c for c in case_results if c["actually_mutated"]]
    actual_unmutated = [c for c in case_results if not c["actually_mutated"]]

    true_positives = [c for c in actual_mutations if c["predicted_mutated"]]
    false_negatives = [c for c in actual_mutations if not c["predicted_mutated"]]
    false_positives = [c for c in actual_unmutated if c["predicted_mutated"]]
    correctly_classified = [c for c in actual_mutations if c["category_classification_correct"] is True]

    mutation_detection_rate = len(true_positives) / len(actual_mutations) if actual_mutations else None
    false_positive_rate = len(false_positives) / len(actual_unmutated) if actual_unmutated else None

    detection_rate_by_category: dict[str, float] = {}
    for category in ALL_CATEGORIES:
        category_cases = [c for c in actual_mutations if c["ground_truth_category"] == category]
        if not category_cases:
            continue
        detected = [c for c in category_cases if c["predicted_mutated"]]
        detection_rate_by_category[category] = len(detected) / len(category_cases)

    return {
        "mutation_detection_rate": mutation_detection_rate,
        "false_positive_rate": false_positive_rate,
        "detection_rate_by_category": detection_rate_by_category,
        "number_of_undetected_mutations": len(false_negatives),
        "number_of_correctly_classified_mutations": len(correctly_classified),
        "_counts": {
            "total_cases": len(case_results),
            "actual_mutations": len(actual_mutations),
            "actual_unmutated": len(actual_unmutated),
            "true_positives": len(true_positives),
            "false_negatives": len(false_negatives),
            "false_positives": len(false_positives),
        },
    }


def run_evaluation(corpus_path: Path = DEFAULT_CORPUS_PATH) -> dict:
    corpus = load_corpus(corpus_path)
    case_results = [run_case(case) for case in corpus]
    metrics = compute_metrics(case_results)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "corpus_path": corpus_path.relative_to(PROJECT_ROOT).as_posix(),
        "corpus_size": len(corpus),
        "metrics": metrics,
        "case_results": case_results,
    }


def main() -> int:
    results = run_evaluation()
    DEFAULT_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"[evaluate] ran {results['corpus_size']} cases")
    print(f"[evaluate] mutation_detection_rate: {results['metrics']['mutation_detection_rate']}")
    print(f"[evaluate] false_positive_rate: {results['metrics']['false_positive_rate']}")
    print(f"[evaluate] number_of_undetected_mutations: {results['metrics']['number_of_undetected_mutations']}")
    print(f"[evaluate] number_of_correctly_classified_mutations: {results['metrics']['number_of_correctly_classified_mutations']}")
    print(f"[evaluate] wrote {DEFAULT_RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
