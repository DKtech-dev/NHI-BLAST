"""OIDC subject breadth classification (spec 10.4).

Breadth describes how many subjects a trust-policy pattern can accept. Severity is a
label used for ordering findings, not a verdict about live access.
"""

from __future__ import annotations

from nhi_blast.core.models import Breadth, Severity

BREADTH_SEVERITY: dict[Breadth, Severity] = {
    Breadth.UNCONSTRAINED: Severity.CRITICAL,
    Breadth.ANY_ORG: Severity.CRITICAL,
    Breadth.SAME_ORG: Severity.HIGH,
    Breadth.REPO_ANY_CONTEXT: Severity.HIGH,
    Breadth.REPO_ANY_BRANCH: Severity.MEDIUM,
    Breadth.REPO_PULL_REQUEST: Severity.MEDIUM,
    Breadth.ENVIRONMENT: Severity.LOW,
    Breadth.EXACT_REF: Severity.INFO,
}

BREADTH_ORDER: tuple[Breadth, ...] = (
    Breadth.UNCONSTRAINED,
    Breadth.ANY_ORG,
    Breadth.SAME_ORG,
    Breadth.REPO_ANY_CONTEXT,
    Breadth.REPO_ANY_BRANCH,
    Breadth.REPO_PULL_REQUEST,
    Breadth.ENVIRONMENT,
    Breadth.EXACT_REF,
)


def breadth_rank(breadth: Breadth) -> int:
    """Lower is broader."""
    return BREADTH_ORDER.index(breadth)


def worst_breadth(breadths: tuple[Breadth, ...]) -> Breadth:
    return min(breadths, key=breadth_rank)


def _base(value: str) -> str:
    return value.split("@", 1)[0]


def _has_wildcard(value: str) -> bool:
    return "*" in value or "?" in value


def format_of_pattern(pattern: str) -> str:
    """CLASSIC, IMMUTABLE or UNKNOWN for a subject pattern."""
    text = pattern.strip()
    if not text.startswith("repo:"):
        return "UNKNOWN"
    body = text[len("repo:") :]
    repo_part = body.split(":", 1)[0]
    if "@" in repo_part:
        return "IMMUTABLE"
    if repo_part in {"*", "*/*"}:
        return "UNKNOWN"
    return "CLASSIC"


def classify_breadth(pattern: str) -> Breadth:
    text = pattern.strip()
    if text in {"", "*", "repo:*"}:
        return Breadth.ANY_ORG
    if not text.startswith("repo:"):
        if _has_wildcard(text):
            return Breadth.ANY_ORG
        return Breadth.REPO_ANY_CONTEXT
    body = text[len("repo:") :]
    repo_part, _, context = body.partition(":")
    segments = repo_part.split("/")
    if len(segments) < 2:
        return Breadth.ANY_ORG
    owner_part, name_part = segments[0], "/".join(segments[1:])
    if _base(owner_part) in {"*", "?"} or _has_wildcard(_base(owner_part)):
        return Breadth.ANY_ORG
    if _base(name_part) in {"*", "?"} or _has_wildcard(_base(name_part)):
        return Breadth.SAME_ORG
    context = context.strip()
    if context in {"", "*"}:
        return Breadth.REPO_ANY_CONTEXT
    if context.startswith("environment:"):
        return Breadth.ENVIRONMENT
    if context == "pull_request":
        return Breadth.REPO_PULL_REQUEST
    if context.startswith("ref:refs/") or context.startswith("ref:refs"):
        ref = context[len("ref:") :]
        if _has_wildcard(ref):
            return Breadth.REPO_ANY_BRANCH
        return Breadth.EXACT_REF
    if _has_wildcard(context):
        return Breadth.REPO_ANY_CONTEXT
    return Breadth.EXACT_REF


def base_severity(breadth: Breadth) -> Severity:
    return BREADTH_SEVERITY[breadth]
