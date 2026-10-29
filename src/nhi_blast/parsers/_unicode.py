"""Reject undecodable Unicode in parsed trees without replacing distinct identifiers."""

from __future__ import annotations

from collections.abc import Mapping


def validate_unicode(value: object) -> None:
    """Require UTF-8-encodable strings in keys and values, without recursive walking."""
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, str):
            current.encode("utf-8")
        elif isinstance(current, Mapping):
            for key, item in current.items():
                stack.append(key)
                stack.append(item)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)
