"""Focused hostile-input regressions for Terraform and IAM parsers."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nhi_blast.core.config import Config
from nhi_blast.core.diagnostics import Diagnostic
from nhi_blast.core.limits import Limits
from nhi_blast.parsers._json import MAX_JSON_DEPTH, JsonDepthError, decode_json
from nhi_blast.parsers.iam.policy_doc import parse_iam_document, parse_policy_text
from nhi_blast.parsers.terraform.facts import TfModelFact
from nhi_blast.parsers.terraform.tfhcl import parse_tf_hcl
from nhi_blast.parsers.terraform.tfjson import parse_tf_json
from nhi_blast.resolvers.roles import resolve_cloud_facts

pytestmark = pytest.mark.security

_CANARY = "SYNTHETIC_MASK_CANARY_NOT_A_CREDENTIAL"
_ADDRESS = "aws_iam_role.example"
_DOCUMENT = "data.aws_iam_policy_document.trust"


def _resource(
    values: dict[str, Any], *, mask: Any = None, address: str = _ADDRESS
) -> dict[str, Any]:
    return {
        "address": address,
        "mode": "data" if address.startswith("data.") else "managed",
        "type": "aws_iam_policy_document" if address == _DOCUMENT else "aws_iam_role",
        "name": address.rsplit(".", 1)[-1],
        "values": values,
        "sensitive_values": mask,
    }


def _state(resources: list[dict[str, Any]]) -> dict[str, Any]:
    return {"format_version": "1.0", "values": {"root_module": {"resources": resources}}}


def _parse_state(payload: dict[str, Any]) -> TfModelFact:
    result = parse_tf_json("state.json", json.dumps(payload), limits=Limits())
    assert result.facts is not None
    assert result.diagnostics == ()
    return result.facts


def _no_canary(model: TfModelFact) -> None:
    # Check the complete returned facts without displaying the sentinel on failure.
    retained = _CANARY in model.model_dump_json()
    assert not retained, "sensitive synthetic input was retained"


@pytest.mark.parametrize(
    ("values", "mask", "expected", "paths"),
    [
        (
            {"inline_policy": [{"name": _CANARY, "policy": "public"}, {"name": "keep"}]},
            {"inline_policy": [{"name": True}]},
            {"inline_policy": [{"policy": "public"}, {"name": "keep"}]},
            ("inline_policy[0].name",),
        ),
        (
            {"tags": {"key.with.dots[0]": _CANARY, "public": "keep"}},
            {"tags": {"key.with.dots[0]": True}},
            {"tags": {"public": "keep"}},
            ("tags.key.with.dots[0]",),
        ),
        (
            {"list": [_CANARY, "keep", [_CANARY, "last"]]},
            {"list": [True, False, [True, False]]},
            {"list": [None, "keep", [None, "last"]]},
            ("list[0]", "list[2][0]"),
        ),
        (
            {"nested": {"list[1]": {"name": _CANARY}}, "keep": 1},
            {"nested": True},
            {"keep": 1},
            ("nested",),
        ),
        ({"name": _CANARY}, True, {}, ("",)),
    ],
    ids=["list-of-objects", "literal-key", "stable-indices", "subtree", "whole-resource"],
)
def test_sensitive_masks_follow_structure(
    values: dict[str, Any], mask: Any, expected: dict[str, Any], paths: tuple[str, ...]
) -> None:
    model = _parse_state(_state([_resource(values, mask=mask)]))

    _no_canary(model)
    resource = model.resources[_ADDRESS]
    assert resource.values == expected
    assert resource.sensitive_fields == paths


@pytest.mark.parametrize("whole_resource", [False, True], ids=["leaves", "whole-resource"])
def test_after_sensitive_is_combined_with_resource_mask(whole_resource: bool) -> None:
    payload = _state(
        [_resource({"list": [_CANARY, _CANARY, "keep"]}, mask={"list": [False, True]})]
    )
    payload["resource_changes"] = [
        {
            "address": _ADDRESS,
            "change": {"after_sensitive": True if whole_resource else {"list": [True, False]}},
        }
    ]

    model = _parse_state(payload)

    _no_canary(model)
    assert model.resources[_ADDRESS].values == (
        {} if whole_resource else {"list": [None, None, "keep"]}
    )


@pytest.mark.parametrize("source", ["state", "prior-only", "planned-over-prior", "after-sensitive"])
def test_sensitive_policy_document_cannot_resolve_authority(source: str) -> None:
    body = json.dumps(
        {"Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole", "Sid": _CANARY}]}
    )
    masked = _resource({"json": body}, mask={"json": True}, address=_DOCUMENT)
    role = _resource({"name": "example", "assume_role_policy": f"{_DOCUMENT}.json"})
    payload = _state([masked, role])
    if source == "prior-only":
        payload = {
            "format_version": "1.0",
            "planned_values": {"root_module": {"resources": [role]}},
            "prior_state": _state([masked]),
        }
    elif source == "planned-over-prior":
        payload = {
            "format_version": "1.0",
            "planned_values": {"root_module": {"resources": [masked, role]}},
            "prior_state": _state([_resource({"json": body}, address=_DOCUMENT)]),
        }
    elif source == "after-sensitive":
        masked.pop("sensitive_values")
        payload["resource_changes"] = [
            {"address": _DOCUMENT, "change": {"after_sensitive": {"json": True}}}
        ]

    model = _parse_state(payload)

    _no_canary(model)
    document = model.policy_documents[_DOCUMENT]
    assert document.json_text is None
    assert document.unknown
    cloud = resolve_cloud_facts([model], [], config=Config.empty())
    assert cloud.roles[0].trust_unresolved
    assert cloud.roles[0].trust_statements == ()


def test_unmasked_prior_only_policy_remains_resolvable() -> None:
    body = '{"Statement":[{"Effect":"Allow","Action":"sts:AssumeRole"}]}'
    payload = {
        "format_version": "1.0",
        "planned_values": {"root_module": {}},
        "prior_state": _state([_resource({"json": body}, address=_DOCUMENT)]),
    }

    model = _parse_state(payload)

    assert model.policy_documents[_DOCUMENT].json_text == body
    assert not model.policy_documents[_DOCUMENT].unknown


def _parse_cloud(parser: str, text: str) -> tuple[object, tuple[Diagnostic, ...]]:
    if parser == "iam":
        return parse_iam_document(text, label="role.json")
    if parser == "policy":
        return parse_policy_text(text, file="policy.json", rule="test")
    if parser == "tfjson":
        result = parse_tf_json("state.json", text, limits=Limits())
    else:
        result = parse_tf_hcl("main.tf.json", text, limits=Limits())
    return result.facts, result.diagnostics


@pytest.mark.parametrize("parser", ["iam", "policy", "tfjson", "tfhcl"])
@pytest.mark.parametrize("shape", ["decoder-depth", "large-integer"])
def test_decoder_limits_return_diagnostics(parser: str, shape: str) -> None:
    value = "[" * 5_000 + "0" + "]" * 5_000 if shape == "decoder-depth" else "1" * 5_000
    text = '{"unused":' + value + "}"

    facts, diagnostics = _parse_cloud(parser, text)

    assert not facts
    assert diagnostics
    assert all(item.code.endswith("PARSE") for item in diagnostics)


def test_deep_hcl_normalization_returns_diagnostic() -> None:
    nested = "[" * 1_500 + "0" + "]" * 1_500
    text = '{"resource":{"aws_iam_role":{"example":{"name":' + nested + "}}}}"

    facts, diagnostics = _parse_cloud("tfhcl", text)

    assert not facts
    assert diagnostics
    assert all(item.code.endswith("PARSE") for item in diagnostics)


def test_json_depth_limit_is_interpreter_independent() -> None:
    at_limit = "[" * MAX_JSON_DEPTH + "0" + "]" * MAX_JSON_DEPTH
    over_limit = "[" * (MAX_JSON_DEPTH + 1) + "0" + "]" * (MAX_JSON_DEPTH + 1)

    decoded = decode_json(at_limit)
    for _ in range(MAX_JSON_DEPTH - 1):
        decoded = decoded[0]
    assert decoded == [0]
    with pytest.raises(JsonDepthError):
        decode_json(over_limit)


def test_json_depth_limit_ignores_brackets_inside_strings() -> None:
    note = "[" * 5_000 + "{" * 5_000

    assert decode_json(json.dumps({"note": note}))["note"] == note


def _unicode_input(parser: str, value: str, *, key: bool) -> str:
    field = {value: "public"} if key else {"name": value}
    if parser == "tfjson":
        return json.dumps(_state([_resource(field)]))
    if parser == "tfhcl":
        return json.dumps({"resource": {"aws_iam_role": {"example": field}}})
    if parser == "iam":
        return json.dumps({"Role": {"RoleName": value, "metadata": field}})
    return json.dumps({"Statement": [{"Effect": "Allow", "Action": value, "Condition": field}]})


@pytest.mark.parametrize("parser", ["tfjson", "tfhcl", "iam", "policy"])
@pytest.mark.parametrize("key", [False, True], ids=["scalar", "key"])
@pytest.mark.parametrize("codepoint", [0xD800, 0xDFFF], ids=["high-surrogate", "low-surrogate"])
def test_invalid_unicode_is_rejected_without_unsafe_diagnostics(
    parser: str, key: bool, codepoint: int
) -> None:
    value = chr(codepoint)
    facts, diagnostics = _parse_cloud(parser, _unicode_input(parser, value, key=key))

    assert not facts
    assert diagnostics
    assert all(item.code.endswith("PARSE") for item in diagnostics)
    for diagnostic in diagnostics:
        diagnostic.model_dump_json().encode("utf-8")
        diagnostic.message.encode("utf-8")


@pytest.mark.parametrize("parser", ["tfjson", "tfhcl", "iam", "policy"])
def test_valid_unicode_including_surrogate_pairs_is_preserved(parser: str) -> None:
    value = "caf\u00e9-\u4e2d-\U00010400"

    facts, diagnostics = _parse_cloud(parser, _unicode_input(parser, value, key=False))

    assert facts
    assert not any(item.code.endswith("PARSE") for item in diagnostics)
    if isinstance(facts, TfModelFact):
        assert facts.resources[_ADDRESS].values["name"] == value
    elif parser == "iam":
        assert facts.role_name == value
    else:
        assert facts[0].actions == (value,)


@pytest.mark.parametrize("form", ["policy-string", "jsonencode"])
def test_nested_policy_decoder_recursion_is_a_controlled_hcl_failure(form: str) -> None:
    inner = '{"unused":' + "[" * 5_000 + "0" + "]" * 5_000 + "}"
    value = f"jsonencode({inner})" if form == "jsonencode" else inner
    text = json.dumps({"resource": {"aws_iam_role": {"example": {"policy": value}}}})

    facts, diagnostics = _parse_cloud("tfhcl", text)

    assert not facts
    assert [item.code for item in diagnostics] == ["D-TF-HCL-PARSE"]


@pytest.mark.parametrize("codepoint", [0xD800, 0xDFFF])
def test_native_hcl_rejects_raw_surrogates(codepoint: int) -> None:
    text = 'resource "aws_iam_role" "example" { name = "' + chr(codepoint) + '" }'

    result = parse_tf_hcl("main.tf", text, limits=Limits())

    assert result.facts is None
    assert [item.code for item in result.diagnostics] == ["D-TF-HCL-PARSE"]
    result.diagnostics[0].message.encode("utf-8")


@pytest.mark.parametrize("parser", ["iam", "policy", "tfjson", "tfhcl"])
def test_cloud_parse_errors_do_not_echo_source(parser: str) -> None:
    sentinel = "REJECTED_CLOUD_BOUNDARY_SENTINEL"

    facts, diagnostics = _parse_cloud(parser, '{"' + sentinel + '": invalid}')

    assert not facts
    assert diagnostics
    assert all(item.code.endswith("PARSE") for item in diagnostics)
    assert all(sentinel not in item.message for item in diagnostics)
