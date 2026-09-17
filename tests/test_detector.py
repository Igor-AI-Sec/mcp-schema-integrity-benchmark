import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector.detector import SchemaIntegrityMonitor  # noqa: E402
from detector.registry import ToolRegistry  # noqa: E402


ORIGINAL_SCHEMA = {
    "name": "read_file",
    "description": "Reads a file.",
    "inputSchema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    "annotations": {
        "title": "Read File",
        "readOnlyHint": True,
        "destructiveHint": False,
    },
}


class TestSchemaIntegrityMonitor(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register("read_file", dict(ORIGINAL_SCHEMA))
        self.monitor = SchemaIntegrityMonitor(self.registry)

    def test_unchanged_schema_is_not_flagged_as_mutated(self) -> None:
        result = self.monitor.check("read_file", dict(ORIGINAL_SCHEMA))
        self.assertFalse(result.mutated)
        self.assertTrue(result.hash_matched)
        self.assertEqual(result.mutation_categories, set())

    def test_mutated_schema_is_flagged(self) -> None:
        mutated = dict(ORIGINAL_SCHEMA)
        mutated["description"] = "Reads any file, including outside the sandbox."
        result = self.monitor.check("read_file", mutated)
        self.assertTrue(result.mutated)
        self.assertFalse(result.hash_matched)
        self.assertIn("description_change", result.mutation_categories)

    def test_annotation_mutation_is_flagged(self) -> None:
        import copy
        mutated = copy.deepcopy(ORIGINAL_SCHEMA)
        mutated["annotations"]["destructiveHint"] = True
        result = self.monitor.check("read_file", mutated)
        self.assertTrue(result.mutated)
        self.assertIn("annotation_change", result.mutation_categories)

    def test_diff_is_populated_on_mutation(self) -> None:
        import copy
        mutated = copy.deepcopy(ORIGINAL_SCHEMA)
        mutated["annotations"]["readOnlyHint"] = False
        result = self.monitor.check("read_file", mutated)
        self.assertTrue(result.diff)
        self.assertEqual(result.diff[0]["path"], "annotations.readOnlyHint")

    def test_numeric_representation_mismatch_falls_back_to_unclassified(self) -> None:
        # 1 and 1.0 compare equal in Python (1 == 1.0), so the structural
        # diff finds nothing, but canonicalize() serializes them as "1"
        # and "1.0" -- different fingerprints. The hash mismatch is real
        # and must not be reported with an empty category set.
        registry = ToolRegistry()
        registry.register("t", {"name": "t", "inputSchema": {"properties": {"x": {"default": 1}}}})
        monitor = SchemaIntegrityMonitor(registry)
        result = monitor.check("t", {"name": "t", "inputSchema": {"properties": {"x": {"default": 1.0}}}})
        self.assertTrue(result.mutated)
        self.assertFalse(result.hash_matched)
        self.assertEqual(result.diff, [])
        self.assertEqual(result.mutation_categories, {"schema_hash_mismatch_unclassified"})

    def test_boolean_vs_numeric_mismatch_falls_back_to_unclassified(self) -> None:
        # Same invariant as the 1 vs 1.0 case, via True == 1 instead.
        registry = ToolRegistry()
        registry.register("t", {"name": "t", "inputSchema": {"properties": {"x": {"default": True}}}})
        monitor = SchemaIntegrityMonitor(registry)
        result = monitor.check("t", {"name": "t", "inputSchema": {"properties": {"x": {"default": 1}}}})
        self.assertTrue(result.mutated)
        self.assertFalse(result.hash_matched)
        self.assertEqual(result.diff, [])
        self.assertEqual(result.mutation_categories, {"schema_hash_mismatch_unclassified"})

    def test_unregistered_tool_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            self.monitor.check("nonexistent_tool", {})

    def test_to_dict_is_json_serializable_shape(self) -> None:
        mutated = dict(ORIGINAL_SCHEMA)
        mutated["description"] = "changed"
        result = self.monitor.check("read_file", mutated)
        d = result.to_dict()
        self.assertIn("mutation_categories", d)
        self.assertIsInstance(d["mutation_categories"], list)  # not a set; must be JSON-serializable


if __name__ == "__main__":
    unittest.main()
