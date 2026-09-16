"""Structural diff between two MCP-like tool schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DiffEntry:
    path: str
    change_type: str  # "added" | "removed" | "changed"
    old_value: Any = None
    new_value: Any = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


def diff_schemas(original: dict, presented: dict, _path: str = "") -> list[DiffEntry]:
    """Recursively diff two schema dicts, returning entries sorted by key at each level.

    Deterministic: same two inputs always produce entries in the same order.
    """
    entries: list[DiffEntry] = []

    orig_keys = set(original.keys()) if isinstance(original, dict) else set()
    pres_keys = set(presented.keys()) if isinstance(presented, dict) else set()

    for key in sorted(orig_keys - pres_keys):
        path = f"{_path}.{key}" if _path else key
        entries.append(DiffEntry(path=path, change_type="removed", old_value=original[key]))

    for key in sorted(pres_keys - orig_keys):
        path = f"{_path}.{key}" if _path else key
        entries.append(DiffEntry(path=path, change_type="added", new_value=presented[key]))

    for key in sorted(orig_keys & pres_keys):
        path = f"{_path}.{key}" if _path else key
        old_val = original[key]
        new_val = presented[key]
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            entries.extend(diff_schemas(old_val, new_val, path))
        elif old_val != new_val:
            entries.append(DiffEntry(path=path, change_type="changed", old_value=old_val, new_value=new_val))

    return entries
