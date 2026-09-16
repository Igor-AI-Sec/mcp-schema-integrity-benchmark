"""Detection logic: ties registry, fingerprinting, diffing, and classification together."""

from __future__ import annotations

from dataclasses import dataclass, field

from .canonicalize import fingerprint
from .classify import classify_mutation
from .diff import diff_schemas
from .registry import ToolRegistry


@dataclass
class DetectionResult:
    tool_name: str
    mutated: bool
    hash_matched: bool
    mutation_categories: set[str] = field(default_factory=set)
    diff: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "mutated": self.mutated,
            "hash_matched": self.hash_matched,
            "mutation_categories": sorted(self.mutation_categories),
            "diff": self.diff,
        }


class SchemaIntegrityMonitor:
    """Sits between a trusted registry and an agent's tool-invocation step.

    check(tool_name, presented_schema) answers: does the schema an agent is
    about to act on still match what was trusted at registration time, and
    if not, what changed?
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def check(self, tool_name: str, presented_schema: dict) -> DetectionResult:
        registered = self.registry.get(tool_name)
        if registered is None:
            raise KeyError(f"tool '{tool_name}' is not registered")

        presented_fingerprint = fingerprint(presented_schema)
        if presented_fingerprint == registered.trusted_fingerprint:
            return DetectionResult(tool_name=tool_name, mutated=False, hash_matched=True)

        diff_entries = diff_schemas(registered.schema, presented_schema)
        categories = classify_mutation(diff_entries)
        return DetectionResult(
            tool_name=tool_name,
            mutated=True,
            hash_matched=False,
            mutation_categories=categories,
            diff=[e.to_dict() for e in diff_entries],
        )
