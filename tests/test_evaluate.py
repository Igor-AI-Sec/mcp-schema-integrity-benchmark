import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector import evaluate  # noqa: E402


class TestRunEvaluation(unittest.TestCase):
    """These expected numbers are derived from fixtures/mutation_corpus.json --
    19 cases: 13 genuine mutations (all detected and correctly classified via
    exact-hash comparison + rule-based classification) and 6 unmutated-control
    cases. Three of the six are benign-equivalence controls the detector gets
    wrong: a reordered enum list, a reordered `required` list, and an
    annotation explicitly set to its own MCP-defined default. All three are
    semantically inert but still change the canonical JSON form, so all three
    are false positives. See README.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.results = evaluate.run_evaluation()

    def test_corpus_size_is_19(self) -> None:
        self.assertEqual(self.results["corpus_size"], 19)

    def test_all_genuine_mutations_are_detected(self) -> None:
        self.assertEqual(self.results["metrics"]["mutation_detection_rate"], 1.0)

    def test_false_positive_rate_reflects_the_three_benign_equivalence_cases(self) -> None:
        # 3 false positives out of 6 unmutated-control cases.
        self.assertEqual(self.results["metrics"]["false_positive_rate"], 0.5)

    def test_no_undetected_mutations(self) -> None:
        self.assertEqual(self.results["metrics"]["number_of_undetected_mutations"], 0)

    def test_all_13_mutations_correctly_classified(self) -> None:
        self.assertEqual(self.results["metrics"]["number_of_correctly_classified_mutations"], 13)

    def test_detection_rate_by_category_is_complete_for_every_mutation_category(self) -> None:
        by_category = self.results["metrics"]["detection_rate_by_category"]
        expected_categories = {
            "parameter_type_change", "required_field_change", "description_change",
            "enum_expansion", "annotation_change", "unexpected_additional_fields",
            "schema_hash_mismatch_unclassified",
        }
        self.assertEqual(set(by_category.keys()), expected_categories)
        for category, rate in by_category.items():
            self.assertEqual(rate, 1.0, f"expected 100% detection for {category}")

    def test_enum_reorder_case_is_a_false_positive(self) -> None:
        reorder_case = next(c for c in self.results["case_results"] if c["case_id"] == "send_notification-benign-enum-reorder")
        self.assertFalse(reorder_case["actually_mutated"])
        self.assertTrue(reorder_case["predicted_mutated"])
        self.assertFalse(reorder_case["detection_correct"])
        # Not applicable for a control case -- there was never a mutation
        # category to get right in the first place.
        self.assertIsNone(reorder_case["category_classification_correct"])
        # No rule explains a same-set reorder: the enum-expansion rule needs
        # a new distinct member, so the enum branch falls back to the
        # unclassified category. The hash mismatch is still reported as a
        # mutation, which is the false positive.
        self.assertEqual(reorder_case["predicted_categories"], ["schema_hash_mismatch_unclassified"])

    def test_required_reorder_case_is_a_false_positive(self) -> None:
        # Same underlying cause as the enum reorder: canonicalize() sorts
        # dict keys but not list contents, so reordering `required` still
        # flips the fingerprint even though the set of required fields is
        # unchanged.
        case = next(c for c in self.results["case_results"] if c["case_id"] == "send_notification-required-reorder")
        self.assertFalse(case["actually_mutated"])
        self.assertTrue(case["predicted_mutated"])
        self.assertFalse(case["detection_correct"])
        self.assertIsNone(case["category_classification_correct"])
        self.assertEqual(case["predicted_categories"], ["required_field_change"])

    def test_explicit_annotation_default_case_is_a_false_positive(self) -> None:
        # readOnlyHint explicitly set to its own MCP-defined default (false)
        # is semantically identical to omitting it, but the detector has no
        # concept of MCP annotation defaults -- any new key is a diff.
        case = next(c for c in self.results["case_results"] if c["case_id"] == "list_directory-explicit-readonlyhint-default")
        self.assertFalse(case["actually_mutated"])
        self.assertTrue(case["predicted_mutated"])
        self.assertFalse(case["detection_correct"])
        self.assertIsNone(case["category_classification_correct"])
        self.assertEqual(case["predicted_categories"], ["annotation_change"])

    def test_detection_correct_is_true_for_exact_duplicate_controls(self) -> None:
        for case_id in ["read_file-unmutated-control", "send_notification-unmutated-control", "query_database-unmutated-control"]:
            case = next(c for c in self.results["case_results"] if c["case_id"] == case_id)
            self.assertTrue(case["detection_correct"], case_id)
            self.assertIsNone(case["category_classification_correct"], case_id)

    def test_category_classification_correct_is_true_for_every_genuine_mutation(self) -> None:
        for case in self.results["case_results"]:
            if case["actually_mutated"]:
                self.assertIs(case["category_classification_correct"], True, case["case_id"])
                self.assertTrue(case["detection_correct"], case["case_id"])

    def test_case_results_length_matches_corpus_size(self) -> None:
        self.assertEqual(len(self.results["case_results"]), self.results["corpus_size"])

    def test_run_evaluation_is_deterministic_apart_from_timestamp(self) -> None:
        first = evaluate.run_evaluation()
        second = evaluate.run_evaluation()
        first.pop("generated_at")
        second.pop("generated_at")
        self.assertEqual(first, second)


class TestCommittedResultsAreCurrent(unittest.TestCase):
    """The committed results/results.json is what the evaluation produces now.

    Only `generated_at` is allowed to differ. Reading the file as text and
    parsing it as JSON makes the comparison independent of line endings.
    """

    @classmethod
    def setUpClass(cls) -> None:
        committed = json.loads(evaluate.DEFAULT_RESULTS_PATH.read_text(encoding="utf-8"))
        fresh = json.loads(json.dumps(evaluate.run_evaluation()))
        cls.committed_timestamp = committed.pop("generated_at", None)
        fresh.pop("generated_at")
        cls.committed = committed
        cls.fresh = fresh

    def test_the_committed_file_records_a_timestamp(self) -> None:
        self.assertIsInstance(self.committed_timestamp, str)

    def test_a_fresh_evaluation_matches_the_committed_results_apart_from_the_timestamp(self) -> None:
        self.assertEqual(self.fresh, self.committed)

    def test_the_top_level_keys_match(self) -> None:
        self.assertEqual(set(self.fresh), set(self.committed))
        self.assertEqual(self.fresh["corpus_size"], self.committed["corpus_size"])
        self.assertEqual(self.fresh["corpus_path"], self.committed["corpus_path"])

    def test_every_case_result_matches(self) -> None:
        self.assertEqual(len(self.fresh["case_results"]), len(self.committed["case_results"]))
        for fresh, committed in zip(self.fresh["case_results"], self.committed["case_results"]):
            self.assertEqual(fresh, committed, fresh["case_id"])

    def test_the_metrics_match(self) -> None:
        self.assertEqual(self.fresh["metrics"], self.committed["metrics"])
        self.assertEqual(self.fresh["metrics"]["detection_rate_by_category"], self.committed["metrics"]["detection_rate_by_category"])

    def test_the_comparison_notices_drift(self) -> None:
        drifted = json.loads(json.dumps(self.committed))
        drifted["case_results"][0]["predicted_categories"] = ["description_change"]
        self.assertNotEqual(self.fresh, drifted)
        drifted = json.loads(json.dumps(self.committed))
        drifted["metrics"]["_counts"]["false_positives"] += 1
        self.assertNotEqual(self.fresh, drifted)


class TestCategoryClassificationCorrectness(unittest.TestCase):
    def test_extra_predicted_category_is_not_fully_correct(self) -> None:
        # A case that trips two categories at once (description AND
        # annotation both changed) must not be scored "correct" just
        # because the ground-truth category happens to be one of the two
        # predicted -- these fixtures each inject exactly one mutation, so
        # an extra, unexpected category means the classification was wrong,
        # not merely noisy.
        case = {
            "case_id": "synthetic-multi-category-diff",
            "tool_name": "t",
            "ground_truth_category": "description_change",
            "original_schema": {"name": "t", "description": "a", "annotations": {"readOnlyHint": True}},
            "presented_schema": {"name": "t", "description": "b", "annotations": {"readOnlyHint": False}},
        }
        result = evaluate.run_case(case)
        self.assertEqual(set(result["predicted_categories"]), {"description_change", "annotation_change"})
        self.assertFalse(result["category_classification_correct"])

    def test_exact_matching_single_category_is_still_correct(self) -> None:
        case = {
            "case_id": "synthetic-single-category-diff",
            "tool_name": "t",
            "ground_truth_category": "description_change",
            "original_schema": {"name": "t", "description": "a"},
            "presented_schema": {"name": "t", "description": "b"},
        }
        result = evaluate.run_case(case)
        self.assertEqual(result["predicted_categories"], ["description_change"])
        self.assertTrue(result["category_classification_correct"])


def _case(case_id: str, truth: str, original: dict, presented: dict, tool_name: str = "t") -> dict:
    return {
        "case_id": case_id,
        "tool_name": tool_name,
        "ground_truth_category": truth,
        "original_schema": original,
        "presented_schema": presented,
    }


DESCRIBED = {"name": "t", "description": "a"}
DESCRIPTION_CHANGED = {"name": "t", "description": "b"}
ANNOTATED = {"name": "t", "annotations": {"readOnlyHint": True}}
ANNOTATION_CHANGED = {"name": "t", "annotations": {"readOnlyHint": False}}


class TestMissedMutationAccounting(unittest.TestCase):
    """The real corpus misses nothing, so these use synthetic cases: a case
    labelled as a mutation whose presented schema is identical to the
    original, which the detector cannot flag."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = [
            _case("detected-description", "description_change", DESCRIBED, DESCRIPTION_CHANGED),
            _case("missed-description", "description_change", DESCRIBED, dict(DESCRIBED)),
            _case("detected-annotation", "annotation_change", ANNOTATED, ANNOTATION_CHANGED),
            _case("clean-control", "unmutated_control", DESCRIBED, dict(DESCRIBED)),
            _case("flagged-control", "unmutated_control", DESCRIBED, DESCRIPTION_CHANGED),
        ]
        cls.case_results = [evaluate.run_case(c) for c in cls.cases]
        cls.by_id = {r["case_id"]: r for r in cls.case_results}
        cls.groups = evaluate.partition_cases(cls.case_results)
        cls.metrics = evaluate.compute_metrics(cls.case_results)

    def test_a_missed_mutation_is_scored_as_not_detected_and_not_classified(self) -> None:
        missed = self.by_id["missed-description"]
        self.assertTrue(missed["actually_mutated"])
        self.assertFalse(missed["predicted_mutated"])
        self.assertFalse(missed["detection_correct"])
        self.assertIs(missed["category_classification_correct"], False)
        self.assertEqual(missed["predicted_categories"], [])

    def test_the_false_negatives_list_contains_exactly_the_missed_case(self) -> None:
        self.assertEqual([c["case_id"] for c in self.groups["false_negatives"]], ["missed-description"])

    def test_the_false_negative_count_and_undetected_metric_increment(self) -> None:
        self.assertEqual(self.metrics["_counts"]["false_negatives"], 1)
        self.assertEqual(self.metrics["number_of_undetected_mutations"], 1)
        self.assertEqual(self.metrics["_counts"]["true_positives"], 2)
        self.assertEqual(self.metrics["_counts"]["actual_mutations"], 3)

    def test_the_missed_mutation_is_not_counted_as_correctly_classified(self) -> None:
        self.assertEqual([c["case_id"] for c in self.groups["correctly_classified"]], ["detected-description", "detected-annotation"])
        self.assertEqual(self.metrics["number_of_correctly_classified_mutations"], 2)

    def test_the_detection_rate_reflects_the_miss(self) -> None:
        self.assertAlmostEqual(self.metrics["mutation_detection_rate"], 2 / 3)

    def test_per_category_detection_rates_reflect_the_miss(self) -> None:
        by_category = self.metrics["detection_rate_by_category"]
        self.assertEqual(by_category["description_change"], 0.5)
        self.assertEqual(by_category["annotation_change"], 1.0)
        self.assertEqual(set(by_category), {"description_change", "annotation_change"})

    def test_controls_are_counted_separately_from_misses(self) -> None:
        self.assertEqual([c["case_id"] for c in self.groups["false_positives"]], ["flagged-control"])
        self.assertEqual(self.metrics["_counts"]["false_positives"], 1)
        self.assertEqual(self.metrics["_counts"]["actual_unmutated"], 2)
        self.assertEqual(self.metrics["false_positive_rate"], 0.5)

    def test_a_missed_case_in_every_category_gives_zero_rates(self) -> None:
        missed = [
            evaluate.run_case(_case("m1", "description_change", DESCRIBED, dict(DESCRIBED))),
            evaluate.run_case(_case("m2", "annotation_change", ANNOTATED, dict(ANNOTATED))),
        ]
        metrics = evaluate.compute_metrics(missed)
        self.assertEqual(metrics["mutation_detection_rate"], 0.0)
        self.assertEqual(metrics["detection_rate_by_category"], {"description_change": 0.0, "annotation_change": 0.0})
        self.assertEqual(metrics["number_of_undetected_mutations"], 2)
        self.assertEqual(metrics["number_of_correctly_classified_mutations"], 0)

    def test_rates_are_none_when_a_group_is_empty(self) -> None:
        only_controls = evaluate.compute_metrics([evaluate.run_case(_case("c", "unmutated_control", DESCRIBED, dict(DESCRIBED)))])
        self.assertIsNone(only_controls["mutation_detection_rate"])
        self.assertEqual(only_controls["false_positive_rate"], 0.0)
        only_mutations = evaluate.compute_metrics([evaluate.run_case(_case("m", "description_change", DESCRIBED, DESCRIPTION_CHANGED))])
        self.assertIsNone(only_mutations["false_positive_rate"])
        self.assertEqual(only_mutations["mutation_detection_rate"], 1.0)

    def test_the_real_corpus_has_no_missed_mutation(self) -> None:
        real = evaluate.partition_cases(evaluate.run_evaluation()["case_results"])
        self.assertEqual(real["false_negatives"], [])
        self.assertEqual(len(real["actual_mutations"]), 13)
        self.assertEqual(len(real["actual_unmutated"]), 6)
        self.assertEqual(len(real["false_positives"]), 3)


if __name__ == "__main__":
    unittest.main()
