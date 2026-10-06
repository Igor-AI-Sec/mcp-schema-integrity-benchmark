"""Rule-based classification of schema diffs into mutation categories.

Categories are keyed off where in an MCP Tool object (`name`,
`description`, `inputSchema`, `annotations`, ...) a diff entry's location
falls; see fixtures/mutation_corpus.json for the exact shape this is
built against. The location is read as a list of keys, and each key is
treated as either a schema keyword (`description`, `required`, `enum`,
`type`, ...) or a user-chosen name or data (a property under `properties`,
an annotation name, a `_meta` key, a key inside a `default`, `const` or
`examples` value). Only keywords select a category, so a property that
happens to be called `description` or `enum` is not mistaken for the
keyword, a name containing a dot is not mistaken for nesting, and a
`default` object that has a `type` key is not mistaken for a type change.
Constructs that carry names or nested schemas other than `properties`
(`$defs`, `patternProperties`, `dependentSchemas`, ...) are outside this
model and may fall back or be misclassified.

Known limitation (see README): this is a deterministic, location-based
heuristic classifier, not a learned model. It recognizes the specific
diff shapes the fixture corpus is built from. An enum edit is labelled
`enum_expansion` only when the new enum keeps every old value and adds at
least one distinct new value. Every other enum edit (a reorder, a
duplicate, a removal or replacement of values, an enum added to or removed
from a parameter) falls back to `schema_hash_mismatch_unclassified`. Any
diff shape that matches no rule at all falls back to the same category; the
hash mismatch is still detected even when the specific category isn't.
"""

from __future__ import annotations

import json
from typing import Any

from .diff import DiffEntry

PARAMETER_TYPE_CHANGE = "parameter_type_change"
REQUIRED_FIELD_CHANGE = "required_field_change"
DESCRIPTION_CHANGE = "description_change"
ENUM_EXPANSION = "enum_expansion"
ANNOTATION_CHANGE = "annotation_change"
UNEXPECTED_ADDITIONAL_FIELDS = "unexpected_additional_fields"
SCHEMA_HASH_MISMATCH_UNCLASSIFIED = "schema_hash_mismatch_unclassified"

ALL_CATEGORIES = [
    PARAMETER_TYPE_CHANGE,
    REQUIRED_FIELD_CHANGE,
    DESCRIPTION_CHANGE,
    ENUM_EXPANSION,
    ANNOTATION_CHANGE,
    UNEXPECTED_ADDITIONAL_FIELDS,
    SCHEMA_HASH_MISMATCH_UNCLASSIFIED,
]


def _normalize_enum_value(value: Any) -> Any:
    """Rewrite a JSON value so that JSON Schema equality is Python equality.

    JSON Schema treats numbers by numeric value, so `1` and `1.0` are the
    same enum member, while booleans are a separate type and `true` is not
    `1`. Arrays compare positionally and objects by key and value, both
    recursively. Python agrees on all of this except that `True == 1`, so
    booleans are kept as booleans (which serialize as `true`/`false`) and a
    float with an integral value is rewritten as the equal integer.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_normalize_enum_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalize_enum_value(v) for k, v in value.items()}
    return value


def _enum_key(value: Any) -> str:
    """Canonical, hashable key for a JSON-compatible enum value.

    A bare `set(values)` crashes with TypeError the moment an enum value is
    a list or dict (unhashable), and it would also merge `true` with `1`.
    This normalizes the value by JSON Schema equality (see
    _normalize_enum_value) and then serializes it with sorted keys, which
    gives every JSON-compatible type (string, number, bool, null, array,
    object) a stable string form for set membership and subset comparisons.
    Two values get the same key exactly when JSON Schema would consider them
    the same enum member.
    """
    return json.dumps(_normalize_enum_value(value), sort_keys=True)


# Keys whose children are user-chosen names rather than schema keywords.
_NAME_CONTAINER_KEYWORDS = {"properties"}
# Keywords whose value is arbitrary JSON data, not a schema. Keys inside it
# are never schema keywords.
_DATA_KEYWORDS = {"default", "const", "examples"}
# Top-level Tool fields whose whole subtree is names or free-form data.
_FREE_FORM_TOP_LEVEL = {"annotations", "_meta"}


def _key_roles(parts: tuple[str, ...]) -> list[str]:
    """Label each key in `parts` as "keyword" or "name".

    The key after a `properties` keyword is a property name, everything
    below the top-level `annotations` / `_meta` fields is a name, and
    everything below a `default`, `const` or `examples` keyword is data.
    Anything else is read as a schema keyword.
    """
    roles: list[str] = []
    expecting_name = False
    in_data = False
    for index, key in enumerate(parts):
        if in_data or (index > 0 and parts[0] in _FREE_FORM_TOP_LEVEL):
            roles.append("name")
            continue
        if expecting_name:
            roles.append("name")
            expecting_name = False
            continue
        roles.append("keyword")
        if key in _NAME_CONTAINER_KEYWORDS:
            expecting_name = True
        elif key in _DATA_KEYWORDS:
            in_data = True
    return roles


def _enum_is_expansion(old_value: Any, new_value: Any) -> bool:
    """True only when the new enum keeps every old value and adds a new one.

    Both sides must be non-empty lists. Values are compared by JSON Schema
    equality (see _enum_key), so duplicates, reordering and a number written
    in another representation (`1` vs `1.0`) never count as growth, and an
    enum that is created or removed outright is not an expansion either.
    """
    if not isinstance(old_value, list) or not isinstance(new_value, list) or not old_value:
        return False
    old_keys = {_enum_key(v) for v in old_value}
    new_keys = {_enum_key(v) for v in new_value}
    return old_keys < new_keys


def classify_mutation(diff_entries: list[DiffEntry]) -> set[str]:
    """Map each diff entry onto one mutation category; return the union across all entries.

    Only called after a fingerprint mismatch has already been detected (see
    detector.py), so an empty `diff_entries` here doesn't mean nothing
    changed -- it means the structural diff, which compares values with
    ordinary Python equality, found nothing to explain a mismatch the hash
    already proved is real. That happens for representations Python treats
    as equal but that canonicalize() does not: `1` and `1.0` compare equal
    (`1 == 1.0`) but serialize as "1" and "1.0", and `True`/`1` do the same
    (`True == 1`). The hash is authoritative for strict content integrity,
    so this must never silently report "no categories" -- it falls back to
    schema_hash_mismatch_unclassified instead, the same bucket used when a
    diff entry doesn't match any known rule below.
    """
    if not diff_entries:
        return {SCHEMA_HASH_MISMATCH_UNCLASSIFIED}

    categories: set[str] = set()

    for entry in diff_entries:
        parts = entry.parts
        roles = _key_roles(parts)
        leaf = parts[-1] if parts else ""
        leaf_is_keyword = bool(roles) and roles[-1] == "keyword"

        if parts and parts[0] == "annotations":
            # Tool annotations (readOnlyHint, destructiveHint,
            # idempotentHint, openWorldHint, title) are the MCP-defined
            # place a tool declares its own risk/behavior profile. Any
            # change under the top-level `annotations` field, including
            # removing the whole block, lands here.
            categories.add(ANNOTATION_CHANGE)
            continue

        if leaf_is_keyword and leaf == "description":
            categories.add(DESCRIPTION_CHANGE)
            continue

        if leaf_is_keyword and leaf == "required":
            # `required` as a keyword is a JSON Schema array of required
            # property names, not a per-property boolean. Any change to
            # that array (an addition or removal) lands here. A property
            # that is merely *named* "required" does not.
            categories.add(REQUIRED_FIELD_CHANGE)
            continue

        if leaf_is_keyword and leaf == "enum":
            if _enum_is_expansion(entry.old_value, entry.new_value):
                categories.add(ENUM_EXPANSION)
            else:
                categories.add(SCHEMA_HASH_MISMATCH_UNCLASSIFIED)
            continue

        if (
            leaf_is_keyword
            and leaf == "type"
            and len(parts) >= 4
            and parts[0] == "inputSchema"
            and parts[1] == "properties"
        ):
            # A `type` keyword somewhere under a property. The top-level
            # `inputSchema.type` is not a parameter type and is left to the
            # fallback below.
            categories.add(PARAMETER_TYPE_CHANGE)
            continue

        if entry.change_type == "added":
            # "Unexpected" is relative to the trusted baseline only; it
            # means this key wasn't present at registration time, not that
            # it's invalid under the MCP spec. `_meta`, for instance, is an
            # MCP-permitted field; adding one here still counts, because
            # the question is "did this differ from what was trusted,"
            # not "is this a legal MCP Tool object." A new property that
            # is merely named like a keyword also ends up here.
            categories.add(UNEXPECTED_ADDITIONAL_FIELDS)
            continue

        categories.add(SCHEMA_HASH_MISMATCH_UNCLASSIFIED)

    return categories
