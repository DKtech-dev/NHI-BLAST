"""JSON decoding with an explicit, interpreter-independent nesting limit.

CPython 3.14's C scanner no longer raises ``RecursionError`` for deeply nested
documents, so a hostile file that older interpreters rejected would be accepted.
The nesting limit is therefore counted from the raw text before decoding; it
ignores brackets inside strings and never depends on the recursion limit.

2500 syntactic levels accept the 1200-level Terraform ``child_modules`` state the
parser contract already supports (each level is an object inside an array, so two
syntactic levels) while rejecting the 5000-level hostile shapes.
"""

from __future__ import annotations

import json
from typing import Any

MAX_JSON_DEPTH = 2500


class JsonDepthError(ValueError):
    """JSON nesting exceeds :data:`MAX_JSON_DEPTH`."""


def _exceeds_depth(text: str, max_depth: int) -> bool:
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > max_depth:
                return True
        elif char in "]}":
            depth -= 1
    return False


def decode_json(text: str, *, max_depth: int = MAX_JSON_DEPTH) -> Any:
    """Decode JSON text, rejecting nesting deeper than ``max_depth``."""
    if _exceeds_depth(text, max_depth):
        msg = f"JSON nesting exceeds {max_depth} levels"
        raise JsonDepthError(msg)
    return json.loads(text)
