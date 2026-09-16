"""Rule-based classification of schema diffs into mutation categories.

Categories are keyed off where in an MCP Tool object (`name`,
`description`, `inputSchema`, `annotations`, ...) a diff entry's path
falls — see fixtures/mutation_corpus.json for the exact shape this is
built against.

Known limitation (see README): this is a deterministic, path-based
heuristic classifier, not a learned model. It recognizes the specific
diff shapes the fixture corpus is built from. An enum edit that removes
or replaces values rather than strictly adding to them falls back to
`parameter_type_change` rather than a dedicated category, since the spec
only names "enum expansion" as a category. Any diff shape that matches no
rule at all falls back to `schema_hash_mismatch_unclassified` — the hash
mismatch is still detected even when the specific category isn't.
"""

from __future__ import annotations

from .diff import DiffEntry

# inputSchema is JSON Schema; parameter-level detail (type, enum, ...)
# lives under inputSchema.properties.<name>.
INPUT_SCHEMA_PROPERTIES_PREFIX = "inputSchema.properties."

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


def classify_mutation(diff_entries: list[DiffEntry]) -> set[str]:
    """Map each diff entry onto one mutation category; return the union across all entries."""
    categories: set[str] = set()

    for entry in diff_entries:
        path = entry.path
        segments = path.split(".")

        if path == "description" or path.endswith(".description"):
            categories.add(DESCRIPTION_CHANGE)
            continue

        if path.endswith(".required"):
            # inputSchema.required is a JSON Schema array of required
            # property names, not a per-property boolean — any change to
            # that array (an addition or removal) lands here.
            categories.add(REQUIRED_FIELD_CHANGE)
            continue

        if path.endswith(".enum"):
            old_values = entry.old_value if isinstance(entry.old_value, list) else []
            new_values = entry.new_value if isinstance(entry.new_value, list) else []
            if set(old_values) <= set(new_values) and len(new_values) > len(old_values):
                categories.add(ENUM_EXPANSION)
            else:
                categories.add(PARAMETER_TYPE_CHANGE)
            continue

        if path.endswith(".type") and path.startswith(INPUT_SCHEMA_PROPERTIES_PREFIX):
            categories.add(PARAMETER_TYPE_CHANGE)
            continue

        if "annotations" in segments:
            # Tool annotations (readOnlyHint, destructiveHint,
            # idempotentHint, openWorldHint, title) are the MCP-defined
            # place a tool declares its own risk/behavior profile — a
            # change here is the realistic analogue of what the old,
            # non-standard "permissions"/"capabilities" fields stood in for.
            categories.add(ANNOTATION_CHANGE)
            continue

        if entry.change_type == "added":
            # "Unexpected" is relative to the trusted baseline only — it
            # means this key wasn't present at registration time, not that
            # it's invalid under the MCP spec. `_meta`, for instance, is an
            # MCP-permitted field; adding one here still counts, because
            # the question is "did this differ from what was trusted,"
            # not "is this a legal MCP Tool object."
            categories.add(UNEXPECTED_ADDITIONAL_FIELDS)
            continue

        categories.add(SCHEMA_HASH_MISMATCH_UNCLASSIFIED)

    return categories
