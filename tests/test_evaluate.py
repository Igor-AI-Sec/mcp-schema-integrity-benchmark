import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector import evaluate  # noqa: E402


class TestRunEvaluation(unittest.TestCase):
    """These expected numbers are hand-derived from fixtures/mutation_corpus.json —
    17 cases: 13 genuine mutations (all detected and correctly classified via
    exact-hash comparison + rule-based classification) and 4 unmutated-control
    cases, one of which (a benign enum value reorder) is a known, deliberate
    false positive: list-order-sensitive hashing flags it as mutated even
    though the tool's permitted values are unchanged as a set. See README.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.results = evaluate.run_evaluation()

    def test_corpus_size_is_17(self) -> None:
        self.assertEqual(self.results["corpus_size"], 17)

    def test_all_genuine_mutations_are_detected(self) -> None:
        self.assertEqual(self.results["metrics"]["mutation_detection_rate"], 1.0)

    def test_false_positive_rate_reflects_the_enum_reorder_case(self) -> None:
        # 1 false positive out of 4 unmutated-control cases.
        self.assertEqual(self.results["metrics"]["false_positive_rate"], 0.25)

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

    def test_enum_reorder_case_is_the_one_false_positive(self) -> None:
        reorder_case = next(c for c in self.results["case_results"] if c["case_id"] == "send_notification-benign-enum-reorder")
        self.assertFalse(reorder_case["actually_mutated"])
        self.assertTrue(reorder_case["predicted_mutated"])
        self.assertFalse(reorder_case["detection_correct"])
        # Not applicable for a control case — there was never a mutation
        # category to get right in the first place.
        self.assertIsNone(reorder_case["category_classification_correct"])
        # Misclassified as parameter_type_change — the enum-expansion rule
        # requires strict growth, so a same-set reorder falls through to the
        # generic fallback bucket. This is a documented, honest limitation.
        self.assertEqual(reorder_case["predicted_categories"], ["parameter_type_change"])

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


if __name__ == "__main__":
    unittest.main()
