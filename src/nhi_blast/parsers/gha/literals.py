"""Literal credential heuristics (spec 7.10).

This is a small heuristic set, not a secret scanner. Hits carry only kind, length
and line; the matched value is never stored, returned or logged.
"""

from __future__ import annotations

import functools
import re

from nhi_blast.core.data import LiteralPattern, credential_heuristics
from nhi_blast.parsers.gha.facts import LiteralHit

_COMPILED: dict[str, re.Pattern[str]] = {}


@functools.lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[LiteralPattern, re.Pattern[str]], ...]:
    compiled: list[tuple[LiteralPattern, re.Pattern[str]]] = []
    for pattern in credential_heuristics().literal_patterns():
        regex = re.compile(pattern.pattern)
        compiled.append((pattern, regex))
    return tuple(compiled)


def _boundary_ok(value: str, start: int, end: int, boundary: str) -> bool:
    if boundary != "alnum":
        return True
    before = value[start - 1] if start > 0 else " "
    after = value[end] if end < len(value) else " "
    return not (before.isalnum() or after.isalnum())


def find_literals(value: str, *, line: int) -> tuple[LiteralHit, ...]:
    """Return literal-credential hits without retaining the matched text."""
    if not value:
        return ()
    hits: dict[tuple[str, int, int, str], LiteralHit] = {}
    for pattern, regex in _patterns():
        for match in regex.finditer(value):
            if not _boundary_ok(value, match.start(), match.end(), pattern.boundary):
                continue
            match_line = line + value.count("\n", 0, match.start())
            length = match.end() - match.start()
            hit = LiteralHit(
                kind=pattern.kind,
                line=match_line,
                length=length,
                pattern_id=pattern.id,
            )
            hits.setdefault((pattern.id, match_line, length, pattern.kind.value), hit)
    return tuple(
        sorted(hits.values(), key=lambda h: (h.line, h.kind.value, h.length, h.pattern_id))
    )
