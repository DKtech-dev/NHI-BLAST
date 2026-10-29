"""Safe plain-text normalisation for terminal and HTML-facing text."""

from __future__ import annotations

import re

from nhi_blast.parsers.gha.literals import redact_literals

_ANSI_OR_OSC = re.compile(
    r"""
    \x1b
    (?:
        \[[0-?]*[ -/]*[@-~]
      | \][^\x07\x1b]*(?:\x07|\x1b\\)
      | [@-Z\\-_]
    )
    """,
    re.VERBOSE,
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_BIDI = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
_SPACES = re.compile(r"[ \t\f\v]+")
_NEWLINES = re.compile(r"\s*\n\s*")


def safe_text(value: object, limit: int = 500) -> str:
    """Normalise untrusted text to one inert line and cap it with an ellipsis."""
    text = _ANSI_OR_OSC.sub("", str(value))
    text = _BIDI.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = redact_literals(text)
    text = _NEWLINES.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    if limit >= 0 and len(text) > limit:
        text = text[:limit] if limit <= 3 else text[: limit - 3].rstrip() + "..."
    return text
