"""Regressions for hostile YAML and explicit malformed permissions (spec 7.1/7.4)."""

from __future__ import annotations

import json

import pytest

from nhi_blast.core.diagnostics import DiagnosticLevel
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import PermLevel
from nhi_blast.parsers.gha.workflow import parse_workflow
from nhi_blast.parsers.yaml_marked import load_marked_document, to_plain
from nhi_blast.resolvers.permissions import effective_permissions

pytestmark = pytest.mark.security

PATH = ".github/workflows/boundary.yml"
SENTINEL = "REJECTED_YAML_BOUNDARY_SENTINEL"


@pytest.mark.parametrize(
    "value", ["null", "~", "", "true", "false", "7", "1.5", "[]", "[write-all]"]
)
@pytest.mark.parametrize("at_job", [False, True], ids=["workflow", "job"])
def test_malformed_explicit_permissions_stay_unknown_without_losing_jobs(
    value: str, *, at_job: bool
) -> None:
    text = (
        "on: push\n"
        + ("permissions: write-all\n" if at_job else f"permissions: {value}\n")
        + "jobs:\n  affected:\n"
        + (f"    permissions: {value}\n" if at_job else "")
        + "    steps:\n      - run: build\n"
        + "  sibling:\n    permissions: {}\n    steps: []\n"
    )

    parsed = parse_workflow(PATH, text, limits=Limits())

    assert parsed.facts is not None
    workflow = parsed.facts
    assert set(workflow.jobs) == {"affected", "sibling"}
    affected = workflow.jobs["affected"]
    assert affected.steps[0].has_run
    perms = affected.permissions if at_job else workflow.permissions
    assert perms is not None
    resolved = effective_permissions(workflow, affected)
    assert resolved.id_token_write is None
    assert not resolved.default_block
    assert set(resolved.levels.values()) == {PermLevel.UNKNOWN}
    assert effective_permissions(workflow, workflow.jobs["sibling"]).id_token_write is False
    assert [item.code for item in parsed.diagnostics] == ["D-GHA-PERM-SHAPE"]
    assert parsed.diagnostics[0].file == PATH
    assert parsed.diagnostics[0].line == (5 if at_job else 2)


@pytest.mark.parametrize(
    ("block", "id_token_write", "contents"),
    [
        ("", False, PermLevel.UNKNOWN),
        ("permissions: {}\n", False, PermLevel.NONE),
        ("permissions: read-all\n", False, PermLevel.READ),
        ("permissions: write-all\n", True, PermLevel.WRITE),
        ("permissions: {contents: read}\n", False, PermLevel.READ),
        ("permissions: {id-token: '${{ inputs.permission }}'}\n", None, PermLevel.NONE),
    ],
)
def test_valid_and_absent_permissions_keep_existing_semantics(
    block: str, id_token_write: bool | None, contents: PermLevel
) -> None:
    parsed = parse_workflow(
        PATH, "on: push\n" + block + "jobs: {build: {steps: []}}\n", limits=Limits()
    )

    assert parsed.facts is not None
    resolved = effective_permissions(parsed.facts, parsed.facts.jobs["build"])
    assert resolved.id_token_write is id_token_write
    assert resolved.levels["contents"] is contents
    assert resolved.default_block is (not block)


def test_composition_recursion_becomes_a_diagnostic() -> None:
    parsed = parse_workflow(PATH, "[" * 600 + "value" + "]" * 600, limits=Limits())

    assert parsed.facts is None
    assert [item.code for item in parsed.diagnostics] == ["D-YAML-DEPTH"]
    assert parsed.diagnostics[0].level is DiagnosticLevel.ERROR


def test_postcompose_recursion_preserves_prior_diagnostics() -> None:
    marked, diagnostics = load_marked_document(
        "first: one\nfirst: two\ncycle: &loop [*loop]\n",
        rel_path=PATH,
        limits=Limits(max_yaml_depth=10_000, alias_expansion_factor=10_000),
    )

    assert marked is None
    assert [item.code for item in diagnostics] == ["D-YAML-DUPKEY", "D-YAML-DEPTH"]
    assert diagnostics[0].line == 1
    assert diagnostics[-1].level is DiagnosticLevel.ERROR


@pytest.mark.parametrize("escape", [r"\U00110000", r"\UFFFFFFFF"])
def test_out_of_range_unicode_escape_is_a_safe_parse_failure(escape: str) -> None:
    marked, diagnostics = load_marked_document(
        f'name: "{SENTINEL}{escape}"\n', rel_path=PATH, limits=Limits()
    )

    assert marked is None
    assert diagnostics
    assert diagnostics[0].level is DiagnosticLevel.ERROR
    assert SENTINEL not in diagnostics[0].message
    json.dumps([item.model_dump(mode="json") for item in diagnostics], ensure_ascii=False).encode(
        "utf-8"
    )


@pytest.mark.parametrize("escape", [r"\uD800", r"\uDFFF", r"\uD800\uDC00"])
@pytest.mark.parametrize("as_key", [False, True], ids=["value", "key"])
def test_decoded_surrogates_are_rejected_not_retained_or_replaced(
    escape: str, *, as_key: bool
) -> None:
    scalar = f'"{SENTINEL}{escape}"'
    text = f"{scalar}: value\n" if as_key else f"name: {scalar}\n"

    marked, diagnostics = load_marked_document(text, rel_path=PATH, limits=Limits())

    assert marked is None
    assert diagnostics
    assert diagnostics[0].level is DiagnosticLevel.ERROR
    assert diagnostics[0].file == PATH
    assert diagnostics[0].line == 1
    assert SENTINEL not in diagnostics[0].message
    json.dumps([item.model_dump(mode="json") for item in diagnostics], ensure_ascii=False).encode(
        "utf-8"
    )


@pytest.mark.parametrize("codepoint", [0xD800, 0xDFFF])
def test_raw_surrogates_become_safe_diagnostics(codepoint: int) -> None:
    marked, diagnostics = load_marked_document(
        "name: " + chr(codepoint), rel_path=PATH, limits=Limits()
    )

    assert marked is None
    assert diagnostics[0].level is DiagnosticLevel.ERROR
    json.dumps([item.model_dump(mode="json") for item in diagnostics], ensure_ascii=False).encode(
        "utf-8"
    )


def test_valid_unicode_is_preserved_without_normalizing_distinct_keys() -> None:
    marked, diagnostics = load_marked_document(
        'name: "caf\\u00E9 \\u6771\\u4EAC \\U0001D11E"\n'
        '"\\uFFFD": replacement character\n'
        '"?": question mark\n'
        '"\\u00E9": composed\n'
        '"e\\u0301": decomposed\n',
        rel_path=PATH,
        limits=Limits(),
    )

    assert diagnostics == ()
    assert to_plain(marked) == {
        "name": "caf\u00e9 \u6771\u4eac \U0001d11e",
        "\ufffd": "replacement character",
        "?": "question mark",
        "\u00e9": "composed",
        "e\u0301": "decomposed",
    }


@pytest.mark.parametrize(
    ("text", "code", "line"),
    [
        (f"{SENTINEL}: first\n{SENTINEL}: second\n", "D-YAML-DUPKEY", 1),
        (f"name: *{SENTINEL}\n", "D-YAML-PARSE", 1),
        (f"name: !{SENTINEL} value\n", "D-YAML-TAG", 1),
    ],
)
def test_yaml_diagnostics_do_not_echo_input(text: str, code: str, line: int) -> None:
    _marked, diagnostics = load_marked_document(text, rel_path=PATH, limits=Limits())

    assert [item.code for item in diagnostics] == [code]
    assert diagnostics[0].file == PATH
    assert diagnostics[0].line == line
    assert "SENTINEL" not in diagnostics[0].message


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (SENTINEL, "D-GHA-PERM-VALUE"),
        (f"{{{SENTINEL}: read}}", "D-GHA-PERM-SCOPE"),
        (f"{{contents: {SENTINEL}}}", "D-GHA-PERM-VALUE"),
    ],
)
def test_permission_diagnostics_do_not_echo_rejected_values(value: str, code: str) -> None:
    parsed = parse_workflow(
        PATH,
        f"on: push\npermissions: {value}\njobs: {{build: {{steps: []}}}}\n",
        limits=Limits(),
    )

    assert parsed.facts is not None
    assert [item.code for item in parsed.diagnostics] == [code]
    assert parsed.diagnostics[0].line == 2
    assert "sentinel" not in parsed.diagnostics[0].message.lower()
