import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector.canonicalize import fingerprint  # noqa: E402
from detector.registry import ToolRegistry  # noqa: E402


class TestToolRegistry(unittest.TestCase):
    def test_register_and_get_round_trips(self) -> None:
        registry = ToolRegistry()
        schema = {"name": "read_file", "description": "reads a file"}
        registry.register("read_file", schema)

        entry = registry.get("read_file")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.schema, schema)
        self.assertEqual(entry.trusted_fingerprint, fingerprint(schema))

    def test_get_unknown_tool_returns_none(self) -> None:
        registry = ToolRegistry()
        self.assertIsNone(registry.get("nope"))

    def test_contains(self) -> None:
        registry = ToolRegistry()
        registry.register("t", {"a": 1})
        self.assertIn("t", registry)
        self.assertNotIn("other", registry)

    def test_re_registering_updates_trusted_fingerprint(self) -> None:
        registry = ToolRegistry()
        registry.register("t", {"a": 1})
        first_fp = registry.get("t").trusted_fingerprint
        registry.register("t", {"a": 2})
        second_fp = registry.get("t").trusted_fingerprint
        self.assertNotEqual(first_fp, second_fp)

    def test_mutating_original_dict_after_registration_does_not_affect_stored_snapshot(self) -> None:
        original = {"name": "read_file", "description": "reads a file"}
        registry = ToolRegistry()
        registry.register("read_file", original)
        trusted_fingerprint_before = registry.get("read_file").trusted_fingerprint

        # Mutate the caller's own dict after registration — this must not
        # reach the registry's stored "trusted" snapshot.
        original["description"] = "reads ANY file, including outside the sandbox"

        entry = registry.get("read_file")
        self.assertEqual(entry.schema["description"], "reads a file")
        self.assertEqual(entry.trusted_fingerprint, trusted_fingerprint_before)
        self.assertNotEqual(entry.schema["description"], original["description"])

    def test_mutating_nested_dict_after_registration_does_not_affect_stored_snapshot(self) -> None:
        original = {
            "name": "read_file",
            "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        }
        registry = ToolRegistry()
        registry.register("read_file", original)
        trusted_fingerprint_before = registry.get("read_file").trusted_fingerprint

        # Mutate a nested object in the caller's dict — this is the case a
        # shallow copy (or no copy at all) would fail to protect against.
        original["inputSchema"]["properties"]["path"]["type"] = "object"

        entry = registry.get("read_file")
        self.assertEqual(entry.schema["inputSchema"]["properties"]["path"]["type"], "string")
        self.assertEqual(entry.trusted_fingerprint, trusted_fingerprint_before)

    def test_mutating_nested_list_after_registration_does_not_affect_stored_snapshot(self) -> None:
        original = {
            "name": "read_file",
            "inputSchema": {
                "type": "object",
                "properties": {"encoding": {"type": "string", "enum": ["utf-8", "ascii"]}},
                "required": ["path"],
            },
        }
        registry = ToolRegistry()
        registry.register("read_file", original)
        trusted_fingerprint_before = registry.get("read_file").trusted_fingerprint

        # Mutate a list nested two levels deep (a common way a shallow
        # `dict(schema)` copy would still leak a mutation through).
        original["inputSchema"]["properties"]["encoding"]["enum"].append("latin-1")
        original["inputSchema"]["required"].append("encoding")

        entry = registry.get("read_file")
        self.assertEqual(entry.schema["inputSchema"]["properties"]["encoding"]["enum"], ["utf-8", "ascii"])
        self.assertEqual(entry.schema["inputSchema"]["required"], ["path"])
        self.assertEqual(entry.trusted_fingerprint, trusted_fingerprint_before)

    def test_stored_schema_is_not_the_same_object_as_the_argument(self) -> None:
        original = {"name": "t", "inputSchema": {"type": "object", "properties": {}}}
        registry = ToolRegistry()
        registry.register("t", original)
        entry = registry.get("t")
        self.assertIsNot(entry.schema, original)
        self.assertIsNot(entry.schema["inputSchema"], original["inputSchema"])

    # -- Defensive copies on the way OUT (register()/get() return values) --
    #
    # The tests above cover the trusted snapshot being protected from
    # mutations to the caller's *original* dict. These cover the other
    # direction: registry.register(...) and registry.get(...) must not
    # hand back an object whose mutation reaches the registry's internal
    # state, either.

    def test_mutating_object_returned_by_register_does_not_affect_internal_state(self) -> None:
        registry = ToolRegistry()
        returned = registry.register("read_file", {"name": "read_file", "description": "reads a file"})
        trusted_fingerprint_before = returned.trusted_fingerprint

        returned.schema["description"] = "reads ANY file, including outside the sandbox"

        entry = registry.get("read_file")
        self.assertEqual(entry.schema["description"], "reads a file")
        self.assertEqual(entry.trusted_fingerprint, trusted_fingerprint_before)

    def test_mutating_object_returned_by_get_does_not_affect_internal_state(self) -> None:
        registry = ToolRegistry()
        registry.register("read_file", {"name": "read_file", "description": "reads a file"})
        trusted_fingerprint_before = registry.get("read_file").trusted_fingerprint

        first_get = registry.get("read_file")
        first_get.schema["description"] = "reads ANY file, including outside the sandbox"

        second_get = registry.get("read_file")
        self.assertEqual(second_get.schema["description"], "reads a file")
        self.assertEqual(second_get.trusted_fingerprint, trusted_fingerprint_before)

    def test_mutating_nested_object_returned_by_register_does_not_affect_internal_state(self) -> None:
        schema = {
            "name": "read_file",
            "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        }
        registry = ToolRegistry()
        returned = registry.register("read_file", schema)
        trusted_fingerprint_before = returned.trusted_fingerprint

        # Mutate two levels deep through the object register() handed back.
        returned.schema["inputSchema"]["properties"]["path"]["type"] = "object"
        returned.schema["inputSchema"]["required"].append("extra")

        entry = registry.get("read_file")
        self.assertEqual(entry.schema["inputSchema"]["properties"]["path"]["type"], "string")
        self.assertEqual(entry.schema["inputSchema"]["required"], ["path"])
        self.assertEqual(entry.trusted_fingerprint, trusted_fingerprint_before)

    def test_mutating_nested_object_returned_by_get_does_not_affect_internal_state(self) -> None:
        schema = {
            "name": "read_file",
            "inputSchema": {
                "type": "object",
                "properties": {"encoding": {"type": "string", "enum": ["utf-8", "ascii"]}},
                "required": ["path"],
            },
        }
        registry = ToolRegistry()
        registry.register("read_file", schema)
        trusted_fingerprint_before = registry.get("read_file").trusted_fingerprint

        # Mutate two levels deep through the object get() handed back.
        fetched = registry.get("read_file")
        fetched.schema["inputSchema"]["properties"]["encoding"]["enum"].append("latin-1")
        fetched.schema["inputSchema"]["required"].append("encoding")

        entry = registry.get("read_file")
        self.assertEqual(entry.schema["inputSchema"]["properties"]["encoding"]["enum"], ["utf-8", "ascii"])
        self.assertEqual(entry.schema["inputSchema"]["required"], ["path"])
        self.assertEqual(entry.trusted_fingerprint, trusted_fingerprint_before)

    def test_register_and_get_return_different_objects_each_call(self) -> None:
        registry = ToolRegistry()
        registered = registry.register("t", {"name": "t"})
        first_get = registry.get("t")
        second_get = registry.get("t")

        self.assertIsNot(registered.schema, first_get.schema)
        self.assertIsNot(first_get.schema, second_get.schema)
        self.assertEqual(first_get.schema, second_get.schema)

    def test_two_get_calls_do_not_share_mutable_state(self) -> None:
        registry = ToolRegistry()
        registry.register("t", {"name": "t", "inputSchema": {"properties": {}}})

        first_get = registry.get("t")
        first_get.schema["inputSchema"]["properties"]["x"] = {"type": "string"}

        second_get = registry.get("t")
        self.assertNotIn("x", second_get.schema["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
