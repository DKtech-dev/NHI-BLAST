"""Linear IAM glob matching and glob intersection (spec 9.2).

IAM patterns are matched without translating them into regular expressions: a
backtracking matcher for concrete strings and an O(len(a)*len(b)) dynamic program
for deciding whether two patterns can match a common string. Both run in bounded
time on hostile input, which is why the specification forbids regex translation.
"""

from __future__ import annotations

from enum import StrEnum

MAX_GLOB_LENGTH = 4096


class GlobRelation(StrEnum):
    INTERSECTS = "INTERSECTS"
    DISJOINT = "DISJOINT"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


def glob_match(pattern: str, text: str, *, fold: bool = False) -> bool:
    """True when text matches pattern; '*' matches any run, '?' one character."""
    if fold:
        pattern = pattern.lower()
        text = text.lower()
    p = 0
    t = 0
    star = -1
    mark = 0
    while t < len(text):
        if p < len(pattern) and pattern[p] != "*" and (pattern[p] == "?" or pattern[p] == text[t]):
            p += 1
            t += 1
        elif p < len(pattern) and pattern[p] == "*":
            star = p
            mark = t
            p += 1
        elif star != -1:
            p = star + 1
            mark += 1
            t = mark
        else:
            return False
    while p < len(pattern) and pattern[p] == "*":
        p += 1
    return p == len(pattern)


def _collapse_stars(pattern: str) -> str:
    """``**`` accepts the same strings as ``*``; collapsing bounds DP width."""
    out: list[str] = []
    previous_star = False
    for char in pattern:
        if char == "*":
            if previous_star:
                continue
            previous_star = True
        else:
            previous_star = False
        out.append(char)
    return "".join(out)


def _strip_common_literals(a: str, b: str) -> tuple[str, str]:
    """Remove a literal prefix and suffix the two patterns must share.

    A leading or trailing character that is neither ``*`` nor ``?`` in both
    patterns has to appear in any common string, so removing it preserves the
    intersection result while shrinking the dynamic program.
    """
    prefix = 0
    limit = min(len(a), len(b))
    while prefix < limit and a[prefix] == b[prefix] and a[prefix] not in "*?":
        prefix += 1
    a = a[prefix:]
    b = b[prefix:]
    suffix = 0
    limit = min(len(a), len(b))
    while suffix < limit and a[-1 - suffix] == b[-1 - suffix] and a[-1 - suffix] not in "*?":
        suffix += 1
    if suffix:
        a = a[:-suffix]
        b = b[:-suffix]
    return a, b


def glob_relation(a: str, b: str, *, fold: bool = False) -> GlobRelation:
    """Tri-state glob intersection returning BUDGET_EXCEEDED on oversized patterns."""
    if len(a) > MAX_GLOB_LENGTH or len(b) > MAX_GLOB_LENGTH:
        return GlobRelation.BUDGET_EXCEEDED
    if fold:
        a = a.lower()
        b = b.lower()
    if a == b:
        return GlobRelation.INTERSECTS
    if not has_wildcard(a):
        return GlobRelation.INTERSECTS if glob_match(b, a) else GlobRelation.DISJOINT
    if not has_wildcard(b):
        return GlobRelation.INTERSECTS if glob_match(a, b) else GlobRelation.DISJOINT
    a = _collapse_stars(a)
    b = _collapse_stars(b)
    if a == "*" or b == "*":
        return GlobRelation.INTERSECTS
    a, b = _strip_common_literals(a, b)
    if not a or not b:
        matched = glob_match(b, a) if not a else glob_match(a, b)
        return GlobRelation.INTERSECTS if matched else GlobRelation.DISJOINT
    len_a = len(a)
    len_b = len(b)
    below = [False] * (len_b + 1)
    below[len_b] = True
    for j in range(len_b - 1, -1, -1):
        below[j] = b[j] == "*" and below[j + 1]
    for i in range(len_a - 1, -1, -1):
        row = [False] * (len_b + 1)
        row[len_b] = a[i] == "*" and below[len_b]
        for j in range(len_b - 1, -1, -1):
            if a[i] == "*":
                row[j] = below[j] or row[j + 1]
            elif b[j] == "*":
                row[j] = row[j + 1] or below[j]
            elif a[i] == b[j] or a[i] == "?" or b[j] == "?":
                row[j] = below[j + 1]
        below = row
    return GlobRelation.INTERSECTS if below[0] else GlobRelation.DISJOINT


def glob_intersects(a: str, b: str, *, fold: bool = False) -> bool:
    """True when some string provably matches both globs within budget."""
    return glob_relation(a, b, fold=fold) is GlobRelation.INTERSECTS


def has_wildcard(pattern: str) -> bool:
    return "*" in pattern or "?" in pattern


def literal_prefix(pattern: str) -> str:
    """Literal start every string matching the pattern must share."""
    for index, char in enumerate(pattern):
        if char in "*?":
            return pattern[:index]
    return pattern


def wildcard_count(pattern: str) -> int:
    return pattern.count("*") + pattern.count("?")


def is_exact(pattern: str) -> bool:
    return not has_wildcard(pattern)
