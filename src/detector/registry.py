"""A mock, in-process trusted MCP-like tool registry.

This is NOT a real MCP server and never talks to one over any network or
process boundary. It exists only to model "a tool schema was trusted at
registration time" so the detector has a trusted fingerprint to check
later-presented schemas against.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from .canonicalize import fingerprint


@dataclass
class RegisteredTool:
    name: str
    schema: dict
    trusted_fingerprint: str


class ToolRegistry:
    """Synthetic registry: register(name, schema) at 'registration' time, get(name) later."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, name: str, schema: dict) -> RegisteredTool:
        """Stores an independent deep copy of `schema`, not a reference to it.

        Without this, mutating the caller's original dict (or anything
        nested inside it) after registration would silently change what
        this registry considers "trusted" — defeating the whole point of
        a trusted baseline. Returns a defensive copy too (see `_snapshot()`)
        so mutating the returned `RegisteredTool.schema` can't reach back
        into the registry's internal state either.
        """
        snapshot = copy.deepcopy(schema)
        entry = RegisteredTool(name=name, schema=snapshot, trusted_fingerprint=fingerprint(snapshot))
        self._tools[name] = entry
        return self._snapshot(entry)

    def get(self, name: str) -> RegisteredTool | None:
        """Returns a defensive copy of the stored entry, not the internal object.

        `registry.get(name).schema[...] = ...` (or any nested mutation)
        must not be able to change what the registry considers trusted —
        the trusted baseline can only change via `register()`.
        """
        entry = self._tools.get(name)
        if entry is None:
            return None
        return self._snapshot(entry)

    @staticmethod
    def _snapshot(entry: RegisteredTool) -> RegisteredTool:
        return RegisteredTool(name=entry.name, schema=copy.deepcopy(entry.schema), trusted_fingerprint=entry.trusted_fingerprint)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
