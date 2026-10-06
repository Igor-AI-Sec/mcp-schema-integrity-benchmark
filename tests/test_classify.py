import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector import classify  # noqa: E402
from detector.diff import DiffEntry, diff_schemas  # noqa: E402


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

    def test_enum_non_superset_falls_back_to_unclassified(self) -> None:
        entries = [DiffEntry(path="inputSchema.properties.encoding.enum", change_type="changed", old_value=["utf-8", "ascii"], new_value=["latin-1"])]
        self.assertEqual(classify.classify_mutation(entries), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

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

    def test_enum_non_superset_with_object_values_falls_back_to_unclassified(self) -> None:
        entries = [DiffEntry(
            path="inputSchema.properties.level.enum",
            change_type="changed",
            old_value=[{"level": 1}],
            new_value=[{"level": 2}],
        )]
        self.assertEqual(classify.classify_mutation(entries), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

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


def _tool(properties: dict, **extra) -> dict:
    schema = {
        "name": "t",
        "description": "d",
        "inputSchema": {"type": "object", "properties": properties, "required": []},
    }
    schema.update(extra)
    return schema


def _classify(original: dict, presented: dict) -> set[str]:
    """Diff two whole tool schemas and classify the result, end to end."""
    return classify.classify_mutation(diff_schemas(original, presented))


KEYWORD_NAMES = ["description", "type", "enum", "annotations", "required"]


class TestPropertyNamesThatLookLikeKeywords(unittest.TestCase):
    """A user-chosen property name must not be read as the schema keyword."""

    def test_adding_a_property_named_like_a_keyword_is_an_unexpected_field(self) -> None:
        for name in KEYWORD_NAMES:
            with self.subTest(name=name):
                original = _tool({"path": {"type": "string"}})
                presented = _tool({"path": {"type": "string"}, name: {"type": "string"}})
                self.assertEqual(_classify(original, presented), {classify.UNEXPECTED_ADDITIONAL_FIELDS})

    def test_adding_a_property_named_required_with_a_boolean_schema(self) -> None:
        original = _tool({"path": {"type": "string"}})
        presented = _tool({"path": {"type": "string"}, "required": {"type": "boolean"}})
        self.assertEqual(_classify(original, presented), {classify.UNEXPECTED_ADDITIONAL_FIELDS})

    def test_adding_a_property_whose_name_contains_a_dot(self) -> None:
        for name in ["a.b", "user.description", "x.enum", "a.required", "user.type", "annotations.readOnlyHint"]:
            with self.subTest(name=name):
                original = _tool({"path": {"type": "string"}})
                presented = _tool({"path": {"type": "string"}, name: {"type": "string"}})
                self.assertEqual(_classify(original, presented), {classify.UNEXPECTED_ADDITIONAL_FIELDS})

    def test_removing_or_replacing_a_property_whose_name_contains_a_dot(self) -> None:
        for name in ["user.description", "x.enum", "a.required", "user.type"]:
            with self.subTest(name=name, change="removed"):
                original = _tool({"path": {"type": "string"}, name: {"type": "string"}})
                presented = _tool({"path": {"type": "string"}})
                self.assertEqual(_classify(original, presented), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})
            with self.subTest(name=name, change="replaced by a non-object"):
                original = _tool({name: {"type": "string"}})
                presented = _tool({name: "string"})
                self.assertEqual(_classify(original, presented), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_a_dotted_name_is_one_key_not_nesting(self) -> None:
        entries = diff_schemas(_tool({}), _tool({"a.enum": {"type": "string"}}))
        self.assertEqual(entries[0].parts, ("inputSchema", "properties", "a.enum"))
        self.assertEqual(entries[0].path, "inputSchema.properties.a.enum")

    def test_explicit_parts_override_a_path_that_would_split_wrongly(self) -> None:
        entry = DiffEntry(
            path="inputSchema.properties.a.enum",
            change_type="added",
            new_value={"type": "string"},
            parts=("inputSchema", "properties", "a.enum"),
        )
        self.assertEqual(classify.classify_mutation([entry]), {classify.UNEXPECTED_ADDITIONAL_FIELDS})

    def test_keyword_changes_inside_a_property_with_a_keyword_name_still_classify(self) -> None:
        # The property is named after a keyword; the change is to a real
        # keyword inside it.
        for name in KEYWORD_NAMES:
            with self.subTest(name=name, change="description"):
                original = _tool({name: {"type": "string", "description": "a"}})
                presented = _tool({name: {"type": "string", "description": "b"}})
                self.assertEqual(_classify(original, presented), {classify.DESCRIPTION_CHANGE})
            with self.subTest(name=name, change="type"):
                original = _tool({name: {"type": "string"}})
                presented = _tool({name: {"type": "integer"}})
                self.assertEqual(_classify(original, presented), {classify.PARAMETER_TYPE_CHANGE})
            with self.subTest(name=name, change="enum"):
                original = _tool({name: {"type": "string", "enum": ["a"]}})
                presented = _tool({name: {"type": "string", "enum": ["a", "b"]}})
                self.assertEqual(_classify(original, presented), {classify.ENUM_EXPANSION})

    def test_keyword_changes_inside_a_dotted_property_still_classify(self) -> None:
        original = _tool({"user.type": {"type": "string"}})
        presented = _tool({"user.type": {"type": "integer"}})
        self.assertEqual(_classify(original, presented), {classify.PARAMETER_TYPE_CHANGE})

    def test_removing_a_property_named_like_a_keyword_is_not_a_keyword_change(self) -> None:
        for name in KEYWORD_NAMES:
            with self.subTest(name=name):
                original = _tool({"path": {"type": "string"}, name: {"type": "string"}})
                presented = _tool({"path": {"type": "string"}})
                self.assertEqual(_classify(original, presented), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_changing_the_required_keyword_of_a_nested_object_is_a_required_change(self) -> None:
        original = _tool({"filters": {"type": "object", "properties": {"col": {"type": "string"}}, "required": ["col"]}})
        presented = _tool({"filters": {"type": "object", "properties": {"col": {"type": "string"}}, "required": []}})
        self.assertEqual(_classify(original, presented), {classify.REQUIRED_FIELD_CHANGE})

    def test_a_property_named_like_a_keyword_is_not_an_annotation(self) -> None:
        original = _tool({"path": {"type": "string"}}, annotations={"readOnlyHint": True})
        presented = _tool({"path": {"type": "string"}, "annotations": {"type": "string"}}, annotations={"readOnlyHint": True})
        self.assertEqual(_classify(original, presented), {classify.UNEXPECTED_ADDITIONAL_FIELDS})


class TestDataSubtreesAreNotSchemaKeywords(unittest.TestCase):
    """Keys inside a `default`, `const` or `examples` value are data."""

    UNCLASSIFIED = {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED}

    def test_a_type_key_inside_a_default_object_is_not_a_parameter_type_change(self) -> None:
        original = _tool({"p": {"type": "object", "default": {"type": "a"}}})
        presented = _tool({"p": {"type": "object", "default": {"type": "b"}}})
        self.assertEqual(_classify(original, presented), self.UNCLASSIFIED)

    def test_a_description_key_inside_a_default_object_is_not_a_description_change(self) -> None:
        original = _tool({"p": {"type": "object", "default": {"description": "a"}}})
        presented = _tool({"p": {"type": "object", "default": {"description": "b"}}})
        self.assertEqual(_classify(original, presented), self.UNCLASSIFIED)

    def test_a_required_key_inside_a_const_object_is_not_a_required_field_change(self) -> None:
        original = _tool({"p": {"const": {"required": [1]}}})
        presented = _tool({"p": {"const": {"required": [2]}}})
        self.assertEqual(_classify(original, presented), self.UNCLASSIFIED)

    def test_an_enum_key_inside_a_default_object_is_not_an_enum_expansion(self) -> None:
        original = _tool({"p": {"type": "object", "default": {"enum": ["a"]}}})
        presented = _tool({"p": {"type": "object", "default": {"enum": ["a", "b"]}}})
        self.assertEqual(_classify(original, presented), self.UNCLASSIFIED)

    def test_keyword_named_keys_inside_an_examples_object_are_data(self) -> None:
        for key in ["type", "description", "required", "enum"]:
            with self.subTest(key=key):
                original = _tool({"p": {"type": "object", "examples": {key: "a"}}})
                presented = _tool({"p": {"type": "object", "examples": {key: "b"}}})
                self.assertEqual(_classify(original, presented), self.UNCLASSIFIED)

    def test_deeply_nested_keys_inside_data_are_data(self) -> None:
        original = _tool({"p": {"default": {"a": {"b": {"type": "x", "description": "x"}}}}})
        presented = _tool({"p": {"default": {"a": {"b": {"type": "y", "description": "y"}}}}})
        self.assertEqual(_classify(original, presented), self.UNCLASSIFIED)

    def test_a_key_added_inside_a_default_object_is_an_added_field_not_a_keyword_change(self) -> None:
        original = _tool({"p": {"default": {"a": 1}}})
        presented = _tool({"p": {"default": {"a": 1, "type": "b"}}})
        self.assertEqual(_classify(original, presented), {classify.UNEXPECTED_ADDITIONAL_FIELDS})

    def test_a_key_removed_from_a_const_object_falls_back(self) -> None:
        original = _tool({"p": {"const": {"a": 1, "description": "d"}}})
        presented = _tool({"p": {"const": {"a": 1}}})
        self.assertEqual(_classify(original, presented), self.UNCLASSIFIED)

    def test_changing_the_default_value_itself_still_falls_back(self) -> None:
        original = _tool({"priority": {"type": "string", "default": "normal"}})
        presented = _tool({"priority": {"type": "string", "default": "high"}})
        self.assertEqual(_classify(original, presented), self.UNCLASSIFIED)

    def test_real_keywords_next_to_a_data_keyword_still_classify(self) -> None:
        original = _tool({"p": {"type": "object", "description": "a", "default": {"type": "x"}}})
        presented = _tool({"p": {"type": "object", "description": "b", "default": {"type": "x"}}})
        self.assertEqual(_classify(original, presented), {classify.DESCRIPTION_CHANGE})
        presented = _tool({"p": {"type": "array", "description": "a", "default": {"type": "x"}}})
        self.assertEqual(_classify(original, presented), {classify.PARAMETER_TYPE_CHANGE})

    def test_a_keyword_change_and_a_sibling_data_change_each_give_their_own_category(self) -> None:
        original = _tool({"p": {"type": "object", "default": {"type": "x"}}})
        presented = _tool({"p": {"type": "array", "default": {"type": "y"}}})
        self.assertEqual(_classify(original, presented), {classify.PARAMETER_TYPE_CHANGE, classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_a_property_named_default_or_const_is_a_name_not_a_data_container(self) -> None:
        for name in ["default", "const", "examples"]:
            with self.subTest(name=name):
                original = _tool({name: {"type": "string", "description": "a"}})
                presented = _tool({name: {"type": "integer", "description": "b"}})
                self.assertEqual(
                    _classify(original, presented),
                    {classify.PARAMETER_TYPE_CHANGE, classify.DESCRIPTION_CHANGE},
                )

    def test_data_subtrees_do_not_hide_keywords_in_a_property_that_follows(self) -> None:
        original = _tool({"a": {"default": {"type": "x"}}, "b": {"type": "string"}})
        presented = _tool({"a": {"default": {"type": "x"}}, "b": {"type": "integer"}})
        self.assertEqual(_classify(original, presented), {classify.PARAMETER_TYPE_CHANGE})

    def test_other_sub_schema_containers_are_not_treated_as_data(self) -> None:
        # Only default/const/examples are data. A keyword nested under another
        # sub-schema keyword is still a keyword.
        for container in ["additionalProperties", "not", "items", "if"]:
            with self.subTest(container=container, change="description"):
                original = _tool({"p": {container: {"description": "a"}}})
                presented = _tool({"p": {container: {"description": "b"}}})
                self.assertEqual(_classify(original, presented), {classify.DESCRIPTION_CHANGE})
            with self.subTest(container=container, change="type"):
                original = _tool({"p": {container: {"type": "string"}}})
                presented = _tool({"p": {container: {"type": "integer"}}})
                self.assertEqual(_classify(original, presented), {classify.PARAMETER_TYPE_CHANGE})
            with self.subTest(container=container, change="required"):
                original = _tool({"p": {container: {"required": ["a"]}}})
                presented = _tool({"p": {container: {"required": ["a", "b"]}}})
                self.assertEqual(_classify(original, presented), {classify.REQUIRED_FIELD_CHANGE})

    def test_the_role_model_leaves_other_containers_as_keywords(self) -> None:
        roles = classify._key_roles(("inputSchema", "properties", "p", "additionalProperties", "type"))
        self.assertEqual(roles, ["keyword", "keyword", "name", "keyword", "keyword"])

    def test_the_role_model_marks_data_keys_as_names(self) -> None:
        roles = classify._key_roles(("inputSchema", "properties", "p", "default", "type"))
        self.assertEqual(roles, ["keyword", "keyword", "name", "keyword", "name"])
        roles = classify._key_roles(("inputSchema", "properties", "p", "type"))
        self.assertEqual(roles, ["keyword", "keyword", "name", "keyword"])


class TestTopLevelFieldsKeepTheirMeaning(unittest.TestCase):
    def test_removing_the_whole_annotations_block_is_an_annotation_change(self) -> None:
        original = _tool({}, annotations={"readOnlyHint": True})
        presented = _tool({})
        self.assertEqual(_classify(original, presented), {classify.ANNOTATION_CHANGE})

    def test_adding_an_annotation_is_an_annotation_change(self) -> None:
        original = _tool({}, annotations={"title": "T"})
        presented = _tool({}, annotations={"title": "T", "readOnlyHint": False})
        self.assertEqual(_classify(original, presented), {classify.ANNOTATION_CHANGE})

    def test_top_level_description_change(self) -> None:
        self.assertEqual(_classify(_tool({}), {**_tool({}), "description": "other"}), {classify.DESCRIPTION_CHANGE})

    def test_input_schema_type_change_is_not_a_parameter_type_change(self) -> None:
        original = _tool({})
        presented = _tool({})
        presented["inputSchema"]["type"] = "array"
        self.assertEqual(_classify(original, presented), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_output_schema_property_type_change_is_not_an_input_parameter_type_change(self) -> None:
        original = _tool({}, outputSchema={"type": "object", "properties": {"r": {"type": "string"}}})
        presented = _tool({}, outputSchema={"type": "object", "properties": {"r": {"type": "integer"}}})
        self.assertEqual(_classify(original, presented), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_the_same_type_change_under_input_schema_is_a_parameter_type_change(self) -> None:
        original = _tool({"r": {"type": "string"}})
        presented = _tool({"r": {"type": "integer"}})
        self.assertEqual(_classify(original, presented), {classify.PARAMETER_TYPE_CHANGE})

    def test_nested_array_items_type_change_is_a_parameter_type_change(self) -> None:
        original = _tool({"tags": {"type": "array", "items": {"type": "string"}}})
        presented = _tool({"tags": {"type": "array", "items": {"type": "object"}}})
        self.assertEqual(_classify(original, presented), {classify.PARAMETER_TYPE_CHANGE})

    def test_meta_contents_are_names_not_keywords(self) -> None:
        original = _tool({}, _meta={"description": "a", "required": ["x"]})
        presented = _tool({}, _meta={"description": "b", "required": ["x", "y"]})
        self.assertEqual(_classify(original, presented), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_adding_a_meta_key_is_an_unexpected_field(self) -> None:
        original = _tool({}, _meta={"a": 1})
        presented = _tool({}, _meta={"a": 1, "b": 2})
        self.assertEqual(_classify(original, presented), {classify.UNEXPECTED_ADDITIONAL_FIELDS})

    def test_parameter_removal_and_constraint_changes_fall_back(self) -> None:
        base = _tool({"limit": {"type": "integer", "maximum": 100}, "path": {"type": "string"}})
        removed = _tool({"path": {"type": "string"}})
        loosened = _tool({"limit": {"type": "integer", "maximum": 100000}, "path": {"type": "string"}})
        self.assertEqual(_classify(base, removed), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})
        self.assertEqual(_classify(base, loosened), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})


class TestEnumClassification(unittest.TestCase):
    def _enum(self, old, new) -> set[str]:
        return _classify(_tool({"mode": {"type": "string", "enum": old}}), _tool({"mode": {"type": "string", "enum": new}}))

    def test_strict_addition_is_an_expansion(self) -> None:
        self.assertEqual(self._enum(["a", "b"], ["a", "b", "c"]), {classify.ENUM_EXPANSION})
        self.assertEqual(self._enum(["a"], ["a", "b", "c"]), {classify.ENUM_EXPANSION})

    def test_addition_that_also_reorders_is_still_an_expansion(self) -> None:
        self.assertEqual(self._enum(["a", "b"], ["c", "b", "a"]), {classify.ENUM_EXPANSION})

    def test_addition_with_a_duplicate_old_member_is_an_expansion(self) -> None:
        self.assertEqual(self._enum(["a", "a"], ["a", "b"]), {classify.ENUM_EXPANSION})

    def test_replacement_is_not_an_expansion(self) -> None:
        for old, new in ((["a", "b"], ["a", "c"]), (["a", "b"], ["c"]), (["a"], ["b"])):
            with self.subTest(old=old, new=new):
                self.assertEqual(self._enum(old, new), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_partial_overlap_with_new_members_is_not_an_expansion(self) -> None:
        self.assertEqual(self._enum(["a", "b"], ["a", "c", "d"]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_removal_of_members_is_not_an_expansion(self) -> None:
        self.assertEqual(self._enum(["a", "b", "c"], ["a", "b"]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_reorder_is_not_an_expansion(self) -> None:
        self.assertEqual(self._enum(["a", "b"], ["b", "a"]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_duplicate_members_are_not_an_expansion(self) -> None:
        self.assertEqual(self._enum(["a", "b"], ["a", "b", "b"]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})
        self.assertEqual(self._enum(["a"], ["a", "a"]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})
        self.assertEqual(self._enum(["a", "b", "b"], ["a", "b"]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_adding_an_enum_to_a_free_text_parameter_is_not_an_expansion(self) -> None:
        original = _tool({"path": {"type": "string"}})
        presented = _tool({"path": {"type": "string", "enum": ["a", "b"]}})
        self.assertEqual(_classify(original, presented), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_removing_the_enum_entirely_is_not_an_expansion(self) -> None:
        original = _tool({"path": {"type": "string", "enum": ["a", "b"]}})
        presented = _tool({"path": {"type": "string"}})
        self.assertEqual(_classify(original, presented), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_an_empty_old_enum_is_not_an_expansion(self) -> None:
        self.assertEqual(self._enum([], ["a"]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_non_list_enum_values_are_not_an_expansion(self) -> None:
        entries = [DiffEntry(path="inputSchema.properties.m.enum", change_type="changed", old_value="a", new_value=["a", "b"])]
        self.assertEqual(classify.classify_mutation(entries), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})
        entries = [DiffEntry(path="inputSchema.properties.m.enum", change_type="changed", old_value=["a"], new_value="b")]
        self.assertEqual(classify.classify_mutation(entries), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_boolean_and_number_members_are_distinct(self) -> None:
        self.assertEqual(self._enum([1], [1, True]), {classify.ENUM_EXPANSION})
        self.assertEqual(self._enum([True], [1]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})

    def test_object_and_array_members(self) -> None:
        self.assertEqual(self._enum([{"k": 1}], [{"k": 1}, {"k": 2}]), {classify.ENUM_EXPANSION})
        self.assertEqual(self._enum([["a"]], [["a"], ["b"]]), {classify.ENUM_EXPANSION})
        self.assertEqual(self._enum([{"k": 1}], [{"k": 2}]), {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED})
        self.assertEqual(self._enum([{"k": 1, "j": 2}], [{"j": 2, "k": 1}, {"z": 0}]), {classify.ENUM_EXPANSION})


class TestEnumNumericEquality(unittest.TestCase):
    """Enum members are compared by JSON Schema equality: `1` and `1.0` are
    the same member, `true` and `1` are different members, and arrays and
    objects compare recursively."""

    def _enum(self, old, new) -> set[str]:
        return _classify(_tool({"mode": {"enum": old}}), _tool({"mode": {"enum": new}}))

    UNCLASSIFIED = {classify.SCHEMA_HASH_MISMATCH_UNCLASSIFIED}
    EXPANSION = {classify.ENUM_EXPANSION}

    def test_a_number_written_as_a_float_is_not_a_new_member(self) -> None:
        self.assertEqual(self._enum([1], [1.0]), self.UNCLASSIFIED)

    def test_adding_the_float_form_of_an_existing_number_is_not_an_expansion(self) -> None:
        self.assertEqual(self._enum([1], [1, 1.0]), self.UNCLASSIFIED)

    def test_adding_a_genuinely_new_number_in_float_form_is_an_expansion(self) -> None:
        self.assertEqual(self._enum([1], [1, 2.0]), self.EXPANSION)

    def test_a_boolean_and_a_number_are_different_members(self) -> None:
        self.assertEqual(self._enum([True], [True, 1]), self.EXPANSION)
        self.assertEqual(self._enum([1], [1, True]), self.EXPANSION)
        self.assertEqual(self._enum([False], [False, 0]), self.EXPANSION)

    def test_replacing_a_boolean_with_the_equal_number_is_not_an_expansion(self) -> None:
        self.assertEqual(self._enum([True], [1]), self.UNCLASSIFIED)
        self.assertEqual(self._enum([1], [True]), self.UNCLASSIFIED)

    def test_numeric_equality_applies_inside_arrays(self) -> None:
        self.assertEqual(self._enum([[1]], [[1], [1.0]]), self.UNCLASSIFIED)
        self.assertEqual(self._enum([[1]], [[1.0]]), self.UNCLASSIFIED)
        self.assertEqual(self._enum([[1]], [[1], [2.0]]), self.EXPANSION)

    def test_array_comparison_is_positional(self) -> None:
        self.assertEqual(self._enum([[1, 2]], [[1, 2], [2, 1]]), self.EXPANSION)
        self.assertEqual(self._enum([[1, 2]], [[2, 1]]), self.UNCLASSIFIED)

    def test_booleans_stay_distinct_from_numbers_inside_arrays(self) -> None:
        self.assertEqual(self._enum([[True]], [[True], [1]]), self.EXPANSION)

    def test_numeric_equality_applies_inside_objects(self) -> None:
        self.assertEqual(self._enum([{"x": 1}], [{"x": 1}, {"x": 1.0}]), self.UNCLASSIFIED)
        self.assertEqual(self._enum([{"x": 1}], [{"x": 1.0}]), self.UNCLASSIFIED)
        self.assertEqual(self._enum([{"x": 1}], [{"x": 1}, {"x": 2.0}]), self.EXPANSION)

    def test_object_comparison_ignores_key_order_and_keeps_booleans_distinct(self) -> None:
        self.assertEqual(self._enum([{"a": 1, "b": 2}], [{"b": 2.0, "a": 1.0}]), self.UNCLASSIFIED)
        self.assertEqual(self._enum([{"x": True}], [{"x": True}, {"x": 1}]), self.EXPANSION)

    def test_numeric_equality_applies_at_any_depth(self) -> None:
        deep = [{"a": [{"b": [1]}]}]
        deep_float = [{"a": [{"b": [1.0]}]}]
        self.assertEqual(self._enum(deep, deep + deep_float), self.UNCLASSIFIED)
        self.assertEqual(self._enum(deep, deep + [{"a": [{"b": [2.0]}]}]), self.EXPANSION)

    def test_fractional_numbers_compare_by_value(self) -> None:
        self.assertEqual(self._enum([0.5], [0.5, 0.5]), self.UNCLASSIFIED)
        self.assertEqual(self._enum([0.5], [0.5, 1.5]), self.EXPANSION)

    def test_distinct_fractions_that_share_an_integer_part_are_different_members(self) -> None:
        # Truncating floats to integers would make all of these the same member.
        self.assertEqual(self._enum([0.5], [0.5, 0.7]), self.EXPANSION)
        self.assertEqual(self._enum([0.1], [0.1, 0.2]), self.EXPANSION)
        self.assertEqual(self._enum([1.5], [1.5, 1.7]), self.EXPANSION)
        self.assertEqual(self._enum([0.5], [0.7]), self.UNCLASSIFIED)
        self.assertEqual(self._enum([0.1], [0.1, 0.1]), self.UNCLASSIFIED)

    def test_a_fraction_and_the_integer_it_truncates_to_are_different_members(self) -> None:
        self.assertEqual(self._enum([0.5], [0.5, 0]), self.EXPANSION)
        self.assertEqual(self._enum([1], [1, 1.5]), self.EXPANSION)

    def test_fractions_inside_arrays_and_objects_are_not_truncated(self) -> None:
        self.assertEqual(self._enum([[0.5]], [[0.5], [0.7]]), self.EXPANSION)
        self.assertEqual(self._enum([{"x": 0.1}], [{"x": 0.1}, {"x": 0.2}]), self.EXPANSION)
        self.assertEqual(self._enum([{"x": 0.1}], [{"x": 0.1}, {"x": 0.1}]), self.UNCLASSIFIED)

    def test_the_enum_key_keeps_fractions_distinct(self) -> None:
        self.assertNotEqual(classify._enum_key(0.5), classify._enum_key(0.7))
        self.assertNotEqual(classify._enum_key(0.5), classify._enum_key(0))
        self.assertEqual(classify._enum_key(0.5), classify._enum_key(0.5))

    def test_strings_and_null_use_plain_equality(self) -> None:
        self.assertEqual(self._enum(["1"], ["1", 1]), self.EXPANSION)
        self.assertEqual(self._enum([None], [None, None]), self.UNCLASSIFIED)
        self.assertEqual(self._enum([None], [None, "null"]), self.EXPANSION)

    def test_the_enum_key_separates_exactly_what_json_schema_separates(self) -> None:
        key = classify._enum_key
        self.assertEqual(key(1), key(1.0))
        self.assertEqual(key([1, {"a": 2}]), key([1.0, {"a": 2.0}]))
        self.assertNotEqual(key(True), key(1))
        self.assertNotEqual(key(False), key(0))
        self.assertNotEqual(key([1, 2]), key([2, 1]))
        self.assertNotEqual(key("1"), key(1))
        self.assertNotEqual(key(None), key("null"))


if __name__ == "__main__":
    unittest.main()
