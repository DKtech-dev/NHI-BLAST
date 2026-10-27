"""Expression scanning (spec 7.5).

Expressions are inspected as text and never evaluated. The scanner finds expression
spans, extracts secrets/vars/env references, head-ref usage and the custom OIDC
request pattern, and reports them per field.
"""

from __future__ import annotations

import re

from nhi_blast.parsers.gha.facts import ExprRefs

EXPR_OPEN = "${{"
EXPR_CLOSE = "}}"

_SECRET_DOT = re.compile(r"secrets\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)")
_SECRET_INDEX = re.compile(r"secrets\s*\[\s*(['\"])([^'\"]+)\1\s*\]")
_VAR_DOT = re.compile(r"vars\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)")
_ENV_DOT = re.compile(r"env\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)")
_HEAD_REF_PATTERNS = (
    re.compile(r"github\s*\.\s*head_ref"),
    re.compile(r"pull_request\s*\.\s*head\s*\.\s*sha"),
    re.compile(r"pull_request\s*\.\s*head\s*\.\s*ref"),
    re.compile(r"pull_request\s*\.\s*head\s*\.\s*repo\s*\.\s*full_name"),
)
_HEAD_MARKER = "refs/pull/"
_BARE_SECRETS = re.compile(r"(?<![A-Za-z0-9_.])secrets(?![A-Za-z0-9_])")
_CUSTOM_OIDC = "ACTIONS_ID_TOKEN_REQUEST"


def split_expressions(text: str) -> tuple[str, ...]:
    """Return the inner text of every expression span without evaluating it."""
    spans: list[str] = []
    start = 0
    while True:
        open_at = text.find(EXPR_OPEN, start)
        if open_at < 0:
            return tuple(spans)
        body_start = open_at + len(EXPR_OPEN)
        close_at = text.find(EXPR_CLOSE, body_start)
        if close_at < 0:
            spans.append(text[body_start:])
            return tuple(spans)
        spans.append(text[body_start:close_at])
        start = close_at + len(EXPR_CLOSE)


def _bare_secrets_referenced(expression: str) -> bool:
    named_spans: list[tuple[int, int]] = []
    for regex in (_SECRET_DOT, _SECRET_INDEX):
        for match in regex.finditer(expression):
            named_spans.append(match.span())
    for match in _BARE_SECRETS.finditer(expression):
        position = match.end()
        rest = expression[position:].lstrip()
        if rest.startswith(".") or rest.startswith("["):
            if any(start <= match.start() < end for start, end in named_spans):
                continue
            if rest.startswith("["):
                inner = rest[1:].lstrip()
                if inner.startswith(("'", '"')):
                    continue
                return True
            continue
        return True
    return False


def scan_text(text: str) -> ExprRefs:
    """Scan a scalar value for expression references."""
    secrets: set[str] = set()
    vars_used: set[str] = set()
    env_used: set[str] = set()
    secrets_all = False
    head_ref_use = False
    for expression in split_expressions(text):
        secrets.update(_SECRET_DOT.findall(expression))
        secrets.update(name for _quote, name in _SECRET_INDEX.findall(expression))
        vars_used.update(_VAR_DOT.findall(expression))
        env_used.update(_ENV_DOT.findall(expression))
        if _bare_secrets_referenced(expression):
            secrets_all = True
        if any(pattern.search(expression) for pattern in _HEAD_REF_PATTERNS):
            head_ref_use = True
    return ExprRefs(
        secrets=tuple(sorted(secrets)),
        secrets_all=secrets_all,
        vars=tuple(sorted(vars_used)),
        env=tuple(sorted(env_used)),
        head_ref_use=head_ref_use,
        custom_oidc_request=_CUSTOM_OIDC in text,
    )


def scan_condition(text: str) -> ExprRefs:
    """Scan an if: value, which may omit the expression delimiters."""
    refs = scan_text(text)
    bare = ExprRefs()
    if EXPR_OPEN not in text:
        bare = scan_text(EXPR_OPEN + " " + text + " " + EXPR_CLOSE)
    return refs.merge(bare)


def merge_all(items: list[ExprRefs]) -> ExprRefs:
    merged = ExprRefs()
    for item in items:
        merged = merged.merge(item)
    return merged


def contains_head_ref_marker(text: str) -> bool:
    """True when a checkout ref/repository value points at pull-request head content."""
    refs = scan_text(text)
    if refs.head_ref_use:
        return True
    return _HEAD_MARKER in text
