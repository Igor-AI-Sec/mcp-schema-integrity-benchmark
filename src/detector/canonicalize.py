"""Deterministic canonicalization and fingerprinting of MCP-like tool schemas."""

from __future__ import annotations

import hashlib
import json


def canonicalize(schema: dict) -> str:
    """Deterministic JSON form: sorted keys, no extraneous whitespace.

    Two schemas that are structurally identical but differ only in key
    order or formatting must canonicalize to the same string.
    """
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))


def fingerprint(schema: dict) -> str:
    """SHA-256 hex digest of the canonical form."""
    return hashlib.sha256(canonicalize(schema).encode("utf-8")).hexdigest()
