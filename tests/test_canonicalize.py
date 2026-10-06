import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detector.canonicalize import canonicalize, fingerprint  # noqa: E402


class TestCanonicalize(unittest.TestCase):
    def test_key_order_does_not_affect_canonical_form(self) -> None:
        a = {"b": 1, "a": 2}
        b = {"a": 2, "b": 1}
        self.assertEqual(canonicalize(a), canonicalize(b))

    def test_different_values_produce_different_canonical_form(self) -> None:
        a = {"a": 1}
        b = {"a": 2}
        self.assertNotEqual(canonicalize(a), canonicalize(b))

    def test_nested_key_order_does_not_affect_canonical_form(self) -> None:
        a = {"outer": {"y": 1, "x": 2}}
        b = {"outer": {"x": 2, "y": 1}}
        self.assertEqual(canonicalize(a), canonicalize(b))


class TestNumericRepresentation(unittest.TestCase):
    """Equal numbers written with a different representation hash differently."""

    def test_integer_and_float_forms_of_the_same_number_have_different_fingerprints(self) -> None:
        self.assertNotEqual(fingerprint({"x": 1}), fingerprint({"x": 1.0}))
        self.assertNotEqual(fingerprint({"x": 100}), fingerprint({"x": 100.0}))

    def test_exponent_notation_in_json_text_loads_to_the_same_float(self) -> None:
        import json
        self.assertEqual(fingerprint(json.loads('{"x": 1e2}')), fingerprint({"x": 100.0}))


class TestFingerprint(unittest.TestCase):
    def test_identical_schemas_produce_identical_fingerprints(self) -> None:
        schema = {"name": "t", "inputSchema": {"properties": {"x": {"type": "string"}}}}
        self.assertEqual(fingerprint(schema), fingerprint(dict(schema)))

    def test_key_order_does_not_affect_fingerprint(self) -> None:
        a = {"name": "t", "description": "d"}
        b = {"description": "d", "name": "t"}
        self.assertEqual(fingerprint(a), fingerprint(b))

    def test_mutated_schema_produces_different_fingerprint(self) -> None:
        a = {"name": "t", "description": "d"}
        b = {"name": "t", "description": "different"}
        self.assertNotEqual(fingerprint(a), fingerprint(b))

    def test_fingerprint_is_a_64_char_hex_sha256_digest(self) -> None:
        digest = fingerprint({"a": 1})
        self.assertEqual(len(digest), 64)
        int(digest, 16)  # raises ValueError if not valid hex


if __name__ == "__main__":
    unittest.main()
