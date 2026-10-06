import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector.diff import DiffEntry, diff_schemas  # noqa: E402


class TestDiffSchemas(unittest.TestCase):
    def test_identical_schemas_produce_no_diff(self) -> None:
        schema = {"name": "t", "inputSchema": {"properties": {"x": {"type": "string"}}}}
        self.assertEqual(diff_schemas(schema, dict(schema)), [])

    def test_top_level_value_change_is_detected(self) -> None:
        original = {"description": "a"}
        presented = {"description": "b"}
        entries = diff_schemas(original, presented)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, "description")
        self.assertEqual(entries[0].change_type, "changed")
        self.assertEqual(entries[0].old_value, "a")
        self.assertEqual(entries[0].new_value, "b")

    def test_nested_value_change_produces_dotted_path(self) -> None:
        original = {"inputSchema": {"properties": {"path": {"type": "string"}}}}
        presented = {"inputSchema": {"properties": {"path": {"type": "object"}}}}
        entries = diff_schemas(original, presented)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, "inputSchema.properties.path.type")

    def test_added_key_is_reported(self) -> None:
        original = {"a": 1}
        presented = {"a": 1, "b": 2}
        entries = diff_schemas(original, presented)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].change_type, "added")
        self.assertEqual(entries[0].path, "b")
        self.assertEqual(entries[0].new_value, 2)

    def test_removed_key_is_reported(self) -> None:
        original = {"a": 1, "b": 2}
        presented = {"a": 1}
        entries = diff_schemas(original, presented)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].change_type, "removed")
        self.assertEqual(entries[0].path, "b")
        self.assertEqual(entries[0].old_value, 2)

    def test_list_value_change_is_detected_as_single_entry(self) -> None:
        original = {"inputSchema": {"required": ["path"]}}
        presented = {"inputSchema": {"required": ["path", "encoding"]}}
        entries = diff_schemas(original, presented)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, "inputSchema.required")
        self.assertEqual(entries[0].old_value, ["path"])
        self.assertEqual(entries[0].new_value, ["path", "encoding"])

    def test_multiple_changes_are_all_reported(self) -> None:
        original = {"description": "a", "annotations": {"readOnlyHint": False}}
        presented = {"description": "b", "annotations": {"readOnlyHint": True}}
        entries = diff_schemas(original, presented)
        paths = {e.path for e in entries}
        self.assertEqual(paths, {"description", "annotations.readOnlyHint"})


class TestDiffEntryOutputShape(unittest.TestCase):
    PUBLIC_KEYS = {"path", "change_type", "old_value", "new_value"}

    def test_to_dict_has_exactly_the_public_keys(self) -> None:
        entry = DiffEntry(path="a.b", change_type="changed", old_value=1, new_value=2)
        self.assertEqual(set(entry.to_dict()), self.PUBLIC_KEYS)
        self.assertEqual(entry.to_dict(), {"path": "a.b", "change_type": "changed", "old_value": 1, "new_value": 2})

    def test_parts_are_not_serialized_for_a_path_only_entry(self) -> None:
        self.assertNotIn("parts", DiffEntry(path="a.b", change_type="added").to_dict())

    def test_entries_from_diff_schemas_serialize_without_parts(self) -> None:
        original = {"inputSchema": {"properties": {"a.b": {"type": "string"}}}}
        presented = {"inputSchema": {"properties": {"a.b": {"type": "integer"}, "c": {"type": "string"}}}}
        entries = diff_schemas(original, presented)
        self.assertEqual(len(entries), 2)
        for entry in entries:
            self.assertEqual(set(entry.to_dict()), self.PUBLIC_KEYS)
            self.assertTrue(entry.parts)
        self.assertEqual(entries[0].to_dict()["path"], "inputSchema.properties.c")

    def test_parts_carry_a_dotted_key_as_one_element_while_path_stays_readable(self) -> None:
        entries = diff_schemas({"p": {"a.b": 1}}, {"p": {"a.b": 2}})
        self.assertEqual(entries[0].path, "p.a.b")
        self.assertEqual(entries[0].parts, ("p", "a.b"))


if __name__ == "__main__":
    unittest.main()
