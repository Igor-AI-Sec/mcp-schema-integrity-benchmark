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
        # Misclassified as parameter_type_change: the enum-expansion rule
        # only fires when the new enum is a strict superset of the old one,
        # and a same-set reorder isn't a superset (same length, no growth),
        # so classify.py's enum branch falls to its own parameter_type_change
        # case instead. This is a documented, honest limitation.
        self.assertEqual(reorder_case["predicted_categories"], ["parameter_type_change"])

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


if __name__ == "__main__":
    unittest.main()
