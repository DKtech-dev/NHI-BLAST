"""Canonical serialisation and digests shared by every reproducibility check.

Equal logical content must give equal bytes on every operating system and checkout
location: UTF-8, sorted keys, minimal separators, no NaN or infinity, scan-root-relative
POSIX paths in Unicode NFC, and arrays that the caller has already sorted by a declared key.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from typing import Any

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


class CanonicalError(ValueError):
    """A value cannot be represented canonically."""


def canonical_json(value: Any) -> str:
    """Deterministic JSON text. Finite floats use Python's shortest round-trip form."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        msg = f"value is not canonically serialisable: {exc}"
        raise CanonicalError(msg) from None


def sha256_hex(data: str | bytes) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def digest_of(value: Any) -> str:
    """SHA-256 over the canonical JSON text of ``value``."""
    return sha256_hex(canonical_json(value))


def normalize_rel_path(path: str) -> str:
    """Scan-root-relative POSIX path in NFC; rejects anything that is not one."""
    if not path or "\\" in path or "\x00" in path:
        msg = "path must be non-empty POSIX text without backslashes or NUL"
        raise CanonicalError(msg)
    if path.startswith("/") or _DRIVE_PREFIX.match(path):
        msg = "path must be relative to the scan root"
        raise CanonicalError(msg)
    normalized = unicodedata.normalize("NFC", path)
    for segment in normalized.split("/"):
        if segment in {"", ".", ".."}:
            msg = "path has an empty, '.' or '..' segment"
            raise CanonicalError(msg)
    return normalized


def path_collisions(paths: Iterable[str]) -> tuple[tuple[str, ...], ...]:
    """Groups of distinct paths that differ only by Unicode normalisation or case."""
    groups: dict[str, set[str]] = {}
    for path in paths:
        key = unicodedata.normalize("NFC", path).casefold()
        groups.setdefault(key, set()).add(path)
    return tuple(
        tuple(sorted(members, key=lambda item: item.encode("utf-8")))
        for _, members in sorted(groups.items())
        if len(members) > 1
    )


__all__ = [
    "CanonicalError",
    "canonical_json",
    "digest_of",
    "normalize_rel_path",
    "path_collisions",
    "sha256_hex",
]
