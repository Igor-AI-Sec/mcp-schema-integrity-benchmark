"""Structural diff between two MCP-like tool schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiffEntry:
    path: str
    change_type: str  # "added" | "removed" | "changed"
    old_value: Any = None
    new_value: Any = None
    # The same location as `path`, as a list of keys. `path` joins keys with
    # "." for display, which cannot tell a key containing a dot apart from
    # nesting, so classification reads `parts`. When an entry is built from a
    # path alone, `parts` is the path split on ".".
    parts: tuple[str, ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        if not self.parts and self.path:
            self.parts = tuple(self.path.split("."))

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


def diff_schemas(original: dict, presented: dict, _path: str = "", _parts: tuple[str, ...] = ()) -> list[DiffEntry]:
    """Recursively diff two schema dicts, returning entries sorted by key at each level.

    Deterministic: same two inputs always produce entries in the same order.
    """
    entries: list[DiffEntry] = []

    orig_keys = set(original.keys()) if isinstance(original, dict) else set()
    pres_keys = set(presented.keys()) if isinstance(presented, dict) else set()

    for key in sorted(orig_keys - pres_keys):
        path = f"{_path}.{key}" if _path else key
        entries.append(DiffEntry(path=path, change_type="removed", old_value=original[key], parts=(*_parts, key)))

    for key in sorted(pres_keys - orig_keys):
        path = f"{_path}.{key}" if _path else key
        entries.append(DiffEntry(path=path, change_type="added", new_value=presented[key], parts=(*_parts, key)))

    for key in sorted(orig_keys & pres_keys):
        path = f"{_path}.{key}" if _path else key
        old_val = original[key]
        new_val = presented[key]
        if isinstance(old_val, dict) and isinstance(new_val, dict):
            entries.extend(diff_schemas(old_val, new_val, path, (*_parts, key)))
        elif old_val != new_val:
            entries.append(DiffEntry(path=path, change_type="changed", old_value=old_val, new_value=new_val, parts=(*_parts, key)))

    return entries
