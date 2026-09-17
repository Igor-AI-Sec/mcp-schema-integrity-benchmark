import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector import classify  # noqa: E402
from detector.diff import DiffEntry  # noqa: E402


class TestClassifyMutation(unittest.TestCase):
    def test_description_change_is_classified(self) -> None:
        entries = [DiffEntry(path="description", change_type="changed", old_value="a", new_value="b")]
        self.assertEqual(classify.classify_mutation(entries), {classify.DESCRIPTION_CHANGE})

    def test_nested_description_change_is_classified(self) -> None:
        entries = [DiffEntry(path="inputSchema.properties.path.description", change_type="changed", old_value="a", new_value="b")]
        self.assertEqual(classify.classify_mutation(entries), {classify.DESCRIPTION_CHANGE})

    def test_required_array_change_is_classified(self) -> None:
        entries = [DiffEntry(path="inputSchema.required", change_type="changed", old_value=["path"], new_value=["path", "encoding"])]
        self.assertEqual(classify.classify_mutation(entries), {classify.REQUIRED_FIELD_CHANGE})

    def test_parameter_type_change_is_classified(self) -> None:
        entries = [DiffEntry(path="inputSchema.properties.path.type", change_type="changed", old_value="string", new_value="object")]
        self.assertEqual(classify.classify_mutation(entries), {classify.PARAMETER_TYPE_CHANGE})

    def test_enum_strict_superset_is_expansion(self) -> None:
        entries = [DiffEntry(path="inputSchema.properties.encoding.enum", change_type="changed", old_value=["utf-8"], new_value=["utf-8", "ascii"])]
        self.assertEqual(classify.classify_mutation(entries), {classify.ENUM_EXPANSION})

    def test_enum_non_superset_falls_back_to_parameter_type_change(self) -> None:
        entries = [DiffEntry(path="inputSchema.properties.encoding.enum", change_type="changed", old_value=["utf-8", "ascii"], new_value=["latin-1"])]
        self.assertEqual(classify.classify_mutation(entries), {classify.PARAMETER_TYPE_CHANGE})

    def test_annotation_change_is_classified(self) -> None:
        entries = [DiffEntry(path="annotations.destructiveHint", change_type="changed", old_value=False, new_value=True)]
        self.assertEqual(classify.classify_mutation(entries), {classify.ANNOTATION_CHANGE})

    def test_annotation_title_change_is_classified(self) -> None:
        entries = [DiffEntry(path="annotations.title", change_type="changed", old_value="Read File", new_value="Read Any File")]
        self.assertEqual(classify.classify_mutation(entries), {classify.ANNOTATION_CHANGE})

    def test_added_field_is_classified_as_unexpected_additional_fields(self) -> None:
        entries = [DiffEntry(path="inputSchema.properties.debug_mode", change_type="added", new_value={"type": "boolean"})]
        self.assertEqual(classify.classify_mutation(entries), {classify.UNEXPECTED_ADDITIONAL_FIELDS})

    def test_added_meta_field_is_classified_as_unexpected_additional_fields(self) -> None:
        entries = [DiffEntry(path="_meta", change_type="added", new_value={"internal_note": "x"})]
        self.assertEqual(classify.classify_mutation(entries), {classify.UNEXPECTED_ADDITIONAL_FIELDS})

    def test_unrecognized_change_falls_back_to_unclassified(self) -> None:
        entries = [DiffEntry(path="inputSchema.properties.priority.default", change_type="changed", old_value="normal", new_value="high")]
        self.assertEqual(classify.classify_mutation(entries), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_multiple_entries_produce_multiple_categories(self) -> None:
        entries = [
            DiffEntry(path="description", change_type="changed", old_value="a", new_value="b"),
            DiffEntry(path="annotations.readOnlyHint", change_type="changed", old_value=True, new_value=False),
        ]
        self.assertEqual(classify.classify_mutation(entries), {classify.DESCRIPTION_CHANGE, classify.ANNOTATION_CHANGE})

    def test_empty_diff_falls_back_to_unclassified(self) -> None:
        # classify_mutation is only called after a fingerprint mismatch is
        # already known to be real (see detector.py) -- an empty diff here
        # means the structural diff (plain Python equality) couldn't
        # explain a mismatch the hash already proved, not that nothing
        # changed. It must not silently report zero categories.
        self.assertEqual(classify.classify_mutation([]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_enum_expansion_with_object_values_does_not_crash(self) -> None:
        entries = [DiffEntry(
            path="inputSchema.properties.level.enum",
            change_type="changed",
            old_value=[{"level": 1}],
            new_value=[{"level": 1}, {"level": 2}],
        )]
        self.assertEqual(classify.classify_mutation(entries), {classify.ENUM_EXPANSION})

    def test_enum_expansion_with_array_values_does_not_crash(self) -> None:
        entries = [DiffEntry(
            path="inputSchema.properties.tags.enum",
            change_type="changed",
            old_value=[["a"]],
            new_value=[["a"], ["b"]],
        )]
        self.assertEqual(classify.classify_mutation(entries), {classify.ENUM_EXPANSION})

    def test_enum_non_superset_with_object_values_falls_back_to_parameter_type_change(self) -> None:
        entries = [DiffEntry(
            path="inputSchema.properties.level.enum",
            change_type="changed",
            old_value=[{"level": 1}],
            new_value=[{"level": 2}],
        )]
        self.assertEqual(classify.classify_mutation(entries), {classify.PARAMETER_TYPE_CHANGE})

    def test_all_categories_list_matches_named_constants(self) -> None:
        self.assertEqual(
            set(classify.ALL_CATEGORIES),
            {
                classify.PARAMETER_TYPE_CHANGE,
                classify.REQUIRED_FIELD_CHANGE,
                classify.DESCRIPTION_CHANGE,
                classify.ENUM_EXPANSION,
                classify.ANNOTATION_CHANGE,
                classify.UNEXPECTED_ADDITIONAL_FIELDS,
                classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED,
            },
        )


if __name__ == "__main__":
    unittest.main()
