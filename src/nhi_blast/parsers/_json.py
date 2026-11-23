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
import math
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
            if depth < 0:
                return True
    return False


def _reject_constant(token: str) -> Any:
    msg = f"non-standard JSON constant is not allowed: {token}"
    raise ValueError(msg)


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        msg = f"non-finite JSON float is not allowed: {token}"
        raise ValueError(msg)
    return value


def decode_json(text: str, *, max_depth: int = MAX_JSON_DEPTH) -> Any:
    """Decode JSON text, rejecting nesting deeper than ``max_depth`` and non-finite numbers."""
    if _exceeds_depth(text, max_depth):
        msg = f"JSON nesting exceeds {max_depth} levels"
        raise JsonDepthError(msg)
    return json.loads(
        text,
        parse_constant=_reject_constant,
        parse_float=_parse_finite_float,
    )
