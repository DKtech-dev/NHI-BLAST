from __future__ import annotations

import pytest

from nhi_blast.core.diagnostics import Diagnostic
from nhi_blast.core.limits import Limits
from nhi_blast.parsers.gha.permissions import _scope_label
from nhi_blast.parsers.gha.workflow import ParseResult, WorkflowFact, parse_workflow


def _parse(text: str) -> ParseResult[WorkflowFact]:
    return parse_workflow(".github/workflows/build.yml", text, limits=Limits())


def _messages(diagnostics: tuple[Diagnostic, ...]) -> list[str]:
    return [diagnostic.message for diagnostic in diagnostics if "permission" in diagnostic.message]


def test_scope_label_leaves_plain_scope_names_unchanged() -> None:
    assert _scope_label("contents") == "contents"
    assert _scope_label("id-token") == "id-token"
    assert _scope_label("pull-requests") == "pull-requests"


def test_scope_label_quotes_and_escapes_unusual_characters() -> None:
    label = _scope_label('evil"name\\path\n\t')
    assert label == '"evil\\"name\\\\path\\u000a\\u0009"'


def test_scope_label_escapes_non_ascii_and_bidi_characters() -> None:
    label = _scope_label("sco\u202epe\u00e9")
    assert label == '"sco\\u202epe\\u00e9"'


@pytest.mark.parametrize("scope", ["\x00", "\x1b[31m", "a\rb", "a\tb", ""])
def test_scope_label_never_emits_raw_control_characters(scope: str) -> None:
    label = _scope_label(scope)
    assert all(0x20 <= ord(character) < 0x7F for character in label)
    assert label.startswith('"')
    assert label.endswith('"')


def test_known_scope_diagnostics_use_a_consistent_safe_label() -> None:
    bad_level = "on: push\npermissions:\n  contents: sideways\njobs: {}\n"
    expression = "on: push\npermissions:\n  contents: ${{ inputs.level }}\njobs: {}\n"

    first = _messages(_parse(bad_level).diagnostics)
    second = _messages(_parse(bad_level).diagnostics)
    assert first == ["unknown level for permission contents"]
    assert second == first
    assert _messages(_parse(expression).diagnostics) == [
        "permission contents is set by an expression; treated as unknown"
    ]


def test_unknown_scope_diagnostics_do_not_echo_the_key() -> None:
    text = 'on: push\npermissions:\n  "evil\\tname": write\njobs: {}\n'
    result = _parse(text)
    message = next(d.message for d in result.diagnostics if d.code == "D-GHA-PERM-SCOPE")
    assert message == "unknown permission scope; ignored"
    assert "\t" not in message
