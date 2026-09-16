import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector.diff import diff_schemas  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
