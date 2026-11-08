"""Returned Terraform facts minimize hostile source values, not just CLI output."""

from __future__ import annotations

import json
import os
import socket
import subprocess
from typing import Any, NoReturn

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nhi_blast.core.config import Config
from nhi_blast.core.limits import Limits
from nhi_blast.parsers.terraform.facts import TfModelFact
from nhi_blast.parsers.terraform.tfhcl import parse_tf_hcl
from nhi_blast.parsers.terraform.tfjson import parse_tf_json
from nhi_blast.resolvers.roles import resolve_cloud_facts

pytestmark = pytest.mark.security
_CANARY = "SYNTHETIC_FACT_CANARY_NOT_A_CREDENTIAL"
_FIELDS = [
    ("aws_secretsmanager_secret_version", "secret_string"),
    ("aws_secretsmanager_secret_version", "secret_binary"),
    ("aws_ssm_parameter", "value"),
    ("aws_db_instance", "password"),
    ("aws_db_instance", "master_password"),
    ("aws_rds_cluster", "master_password"),
    ("aws_iam_access_key", "secret"),
]


def _state(
    resource_type: str, values: dict[str, Any], mask: Any = None, *, plan: bool = False
) -> TfModelFact:
    address = f"{resource_type}.example"
    resource = {
        "address": address,
        "type": resource_type,
        "name": "example",
        "values": values,
    }
    payload: dict[str, Any] = {"format_version": "1.0"}
    section = "planned_values" if plan else "values"
    payload[section] = {"root_module": {"resources": [resource]}}
    if mask is not None:
        if plan:
            payload["resource_changes"] = [
                {"address": address, "change": {"after_sensitive": mask}}
            ]
        else:
            resource["sensitive_values"] = mask
    result = parse_tf_json("state.json", json.dumps(payload), limits=Limits())
    assert result.facts is not None
    return result.facts


def _no_canary(model: TfModelFact) -> None:
    retained = _CANARY in model.model_dump_json()
    assert not retained, "synthetic sensitive input retained in returned facts"


@pytest.mark.parametrize(("resource_type", "field"), _FIELDS)
@pytest.mark.parametrize(
    "mask_kind", ["absent", "empty", "false", "true", "malformed", "whole", "nested"]
)
@pytest.mark.parametrize("plan", [False, True], ids=["state", "plan"])
def test_known_credential_fields_ignore_producer_mask(
    resource_type: str, field: str, mask_kind: str, plan: bool
) -> None:
    masks: dict[str, Any] = {
        "absent": None,
        "empty": {},
        "false": {field: False},
        "true": {field: True},
        "malformed": {field: "false"},
        "whole": True,
        "nested": {field: {"nested": False}},
    }
    model = _state(resource_type, {field: _CANARY, "name": "safe"}, masks[mask_kind], plan=plan)
    _no_canary(model)
    resource = model.resources[f"{resource_type}.example"]
    assert field not in resource.values
    assert field in resource.sensitive_fields or "" in resource.sensitive_fields


@pytest.mark.parametrize("parser", ["hcl", "tf-json"])
@pytest.mark.parametrize(("resource_type", "field"), _FIELDS)
def test_hcl_known_credential_fields_are_markers(
    parser: str, resource_type: str, field: str
) -> None:
    if parser == "hcl":
        text = f'''resource "{resource_type}" "example" {{
 {field} = "{_CANARY}"
}}'''
    else:
        text = json.dumps({"resource": {resource_type: {"example": {field: _CANARY}}}})
    result = parse_tf_hcl(
        "main.tf.json" if parser == "tf-json" else "main.tf", text, limits=Limits()
    )
    assert result.facts is not None
    _no_canary(result.facts)
    assert field in result.facts.resources[f"{resource_type}.example"].sensitive_fields


@pytest.mark.parametrize("parser", ["hcl", "tf-json"])
@pytest.mark.parametrize("use", ["unused", "direct", "interpolation", "policy"])
def test_declared_sensitive_defaults_never_materialize_metadata(parser: str, use: str) -> None:
    attrs: dict[str, Any] = {"name": "safe"}
    if use == "direct":
        attrs["name"] = "${var.confidential}"
    elif use == "interpolation":
        attrs["name"] = "prefix-${var.confidential}"
    elif use == "policy":
        attrs["assume_role_policy"] = {
            "Statement": [{"Effect": "Allow", "Sid": "${var.confidential}"}]
        }
    document = {
        "variable": {"confidential": {"sensitive": True, "default": _CANARY}},
        "resource": {"aws_iam_role": {"example": attrs}},
    }
    text = json.dumps(document)
    if parser == "hcl":
        assignments = []
        for key, value in attrs.items():
            rendered = json.dumps(value)
            assignments.append(f"{key} = {rendered}")
        text = f'''variable "confidential" {{
 sensitive = true
 default = "{_CANARY}"
}}
'''
        text += chr(10).join(['resource "aws_iam_role" "example" {', *assignments, "}"])
    result = parse_tf_hcl("main.tf", text, limits=Limits())
    assert result.facts is not None
    _no_canary(result.facts)
    assert result.facts.variables == {}
    if use != "unused":
        field = "assume_role_policy" if use == "policy" else "name"
        assert field in result.facts.resources["aws_iam_role.example"].unknown_fields


@pytest.mark.parametrize("parser", ["state", "hcl", "tf-json"])
def test_unknown_resources_do_not_retain_arbitrary_values(parser: str) -> None:
    values = {"name": _CANARY, "payload": {"nested": [_CANARY]}, "command": "$(hostile)"}
    if parser == "state":
        model = _state("unknown_provider_object", values)
    else:
        text = json.dumps({"resource": {"unknown_provider_object": {"example": values}}})
        if parser == "hcl":
            text = f'''resource "unknown_provider_object" "example" {{
 name = "{_CANARY}"
}}'''
        result = parse_tf_hcl("main.tf", text, limits=Limits())
        assert result.facts is not None
        model = result.facts
    _no_canary(model)
    assert model.resources["unknown_provider_object.example"].values == {}


def test_safe_blocks_and_policy_shapes_drop_unconsumed_hidden_content() -> None:
    policy = {
        "Version": "2012-10-17",
        "hidden": _CANARY,
        "Statement": [
            {"Effect": "Allow", "Action": "sts:AssumeRole", "Resource": "*", "hidden": _CANARY}
        ],
    }
    model = _state(
        "aws_iam_role",
        {
            "name": "deploy",
            "arn": "arn:aws:iam::111122223333:role/deploy",
            "max_session_duration": 7200,
            "assume_role_policy": json.dumps(policy),
            "tags": {"secret": _CANARY},
            "inline_policy": [{"name": "read", "policy": json.dumps(policy), "hidden": _CANARY}],
        },
    )
    _no_canary(model)
    resource = model.resources["aws_iam_role.example"]
    assert resource.values["name"] == "deploy"
    assert resource.values["max_session_duration"] == 7200
    assert set(resource.values["inline_policy"][0]) == {"name", "policy"}
    cloud = resolve_cloud_facts([model], [], config=Config.empty())
    assert cloud.roles[0].trust_statements[0].actions == ("sts:AssumeRole",)


def test_nonsensitive_defaults_resolve_without_returning_variable_defaults() -> None:
    text = json.dumps(
        {
            "variable": {"role_name": {"default": "deploy"}, "unused": {"default": _CANARY}},
            "resource": {"aws_iam_role": {"example": {"name": "${var.role_name}"}}},
        }
    )
    result = parse_tf_hcl("main.tf.json", text, limits=Limits())
    assert result.facts is not None
    _no_canary(result.facts)
    assert result.facts.variables == {}
    assert result.facts.resources["aws_iam_role.example"].values["name"] == "deploy"


@pytest.mark.parametrize("parser", ["hcl", "tf-json"])
def test_hcl_safe_links_preserve_reference_map(parser: str) -> None:
    attributes = {
        "secret_id": "${aws_secretsmanager_secret.main.id}",
        "secret_string": "${var.confidential}",
    }
    text = json.dumps({"resource": {"aws_secretsmanager_secret_version": {"example": attributes}}})
    if parser == "hcl":
        text = """resource "aws_secretsmanager_secret_version" "example" {
 secret_id = aws_secretsmanager_secret.main.id
 secret_string = var.confidential
}"""
    result = parse_tf_hcl("main.tf", text, limits=Limits())
    assert result.facts is not None
    resource = result.facts.resources["aws_secretsmanager_secret_version.example"]
    assert resource.values["secret_id"] == "aws_secretsmanager_secret.main.id"
    assert resource.references == {
        "secret_id": ("aws_secretsmanager_secret.main.id",),
        "secret_string": ("var.confidential",),
    }


def test_metadata_masks_remain_effective_at_real_fact_boundary() -> None:
    policy = '{"Statement":[{"Effect":"Allow","Action":"ssm:GetParameter","Resource":"*"}]}'
    model = _state(
        "aws_iam_role",
        {
            "name": _CANARY,
            "managed_policy_arns": [_CANARY, "arn:aws:iam::111122223333:policy/read"],
            "inline_policy": [
                {"name": _CANARY, "policy": policy},
                {"name": "unmasked", "policy": _CANARY},
            ],
        },
        {
            "name": True,
            "managed_policy_arns": [True, False],
            "inline_policy": [{"name": True}, {"policy": True}],
        },
    )
    _no_canary(model)
    resource = model.resources["aws_iam_role.example"]
    assert resource.values == {
        "managed_policy_arns": [None, "arn:aws:iam::111122223333:policy/read"],
        "inline_policy": [{"policy": policy}, {"name": "unmasked"}],
    }
    assert resource.sensitive_fields == (
        "inline_policy[0].name",
        "inline_policy[1].policy",
        "managed_policy_arns[0]",
        "name",
    )


@pytest.mark.parametrize("parser", ["state", "hcl", "tf-json"])
def test_hostile_source_never_executes_or_uses_network(
    parser: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> NoReturn:
        message = "parser attempted external execution or network access"
        raise AssertionError(message)

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    command = '$(curl example.invalid); file("../outside"); <script>hostile()</script>'
    values = {"value": _CANARY, "command": command, "name": "/prod/key", "type": "SecureString"}
    if parser == "state":
        model = _state("aws_ssm_parameter", values)
    else:
        text = json.dumps({"resource": {"aws_ssm_parameter": {"example": values}}})
        if parser == "hcl":
            text = """resource "aws_ssm_parameter" "example" {
 name = "/prod/key"
 type = "SecureString"
 value = file("../outside")
 command = "$(curl example.invalid)"
}"""
        result = parse_tf_hcl("main.tf", text, limits=Limits())
        assert result.facts is not None
        model = result.facts
    _no_canary(model)
    assert model.resources["aws_ssm_parameter.example"].values == {
        "name": "/prod/key",
        "type": "SecureString",
    }


@pytest.mark.parametrize(
    "mask", [None, {}, False, "false", {"master_user_secret": [{"password": False}]}]
)
def test_safe_db_links_drop_nested_credential_and_unknown_values(mask: Any) -> None:
    model = _state(
        "aws_db_instance",
        {
            "identifier": "database",
            "manage_master_user_password": True,
            "master_user_secret": [
                {
                    "secret_arn": "arn:aws:secretsmanager:us-east-1:111122223333:secret:database",
                    "password": _CANARY,
                    "unused": _CANARY,
                }
            ],
        },
        mask,
    )
    _no_canary(model)
    resource = model.resources["aws_db_instance.example"]
    assert resource.values["master_user_secret"] == [
        {"secret_arn": "arn:aws:secretsmanager:us-east-1:111122223333:secret:database"},
    ]
    assert resource.sensitive_fields == ("master_user_secret[0].password",)
    assert "master_user_secret[0].unused" in resource.unknown_fields


@pytest.mark.parametrize("sensitive", [True, "true", "false", None, 1, {}, []])
def test_malformed_sensitive_declarations_do_not_resolve_defaults(sensitive: Any) -> None:
    text = json.dumps(
        {
            "variable": {"confidential": {"sensitive": sensitive, "default": _CANARY}},
            "resource": {"aws_iam_role": {"example": {"name": "${var.confidential}"}}},
        }
    )
    result = parse_tf_hcl("main.tf.json", text, limits=Limits())
    assert result.facts is not None
    _no_canary(result.facts)
    resource = result.facts.resources["aws_iam_role.example"]
    assert "name" not in resource.values
    assert "name" in resource.unknown_fields


@pytest.mark.parametrize(
    "location", ["action", "resource", "principal", "condition-value", "condition-key"]
)
def test_policy_literal_redaction_withholds_semantics_instead_of_rewriting(location: str) -> None:
    synthetic_pattern = "ghp_" + "x" * 36
    statement: dict[str, Any] = {"Effect": "Allow", "Action": "sts:AssumeRole", "Resource": "*"}
    if location == "action":
        statement["Action"] = synthetic_pattern
    elif location == "resource":
        statement["Resource"] = synthetic_pattern
    elif location == "principal":
        statement["Principal"] = {"AWS": synthetic_pattern}
    elif location == "condition-value":
        statement["Condition"] = {"StringEquals": {"aws:PrincipalTag/key": synthetic_pattern}}
    else:
        statement["Condition"] = {"StringEquals": {synthetic_pattern: "required"}}
    model = _state(
        "aws_iam_role",
        {"name": "safe", "assume_role_policy": json.dumps({"Statement": [statement]})},
    )
    retained = synthetic_pattern in model.model_dump_json()
    assert not retained, "synthetic credential-shaped policy content was retained"
    resource = model.resources["aws_iam_role.example"]
    assert "assume_role_policy" not in resource.values
    assert "assume_role_policy" in resource.unknown_fields
    cloud = resolve_cloud_facts([model], [], config=Config.empty())
    assert cloud.roles[0].trust_unresolved
    assert cloud.roles[0].trust_statements == ()


@pytest.mark.parametrize("restriction", ["not-principal", "unknown-principal-kind"])
def test_unsupported_semantic_policy_restrictions_are_not_dropped(restriction: str) -> None:
    statement: dict[str, Any] = {"Effect": "Allow", "Action": "sts:AssumeRole", "Resource": "*"}
    if restriction == "not-principal":
        statement["NotPrincipal"] = {"AWS": "arn:aws:iam::111122223333:role/excluded"}
    else:
        statement["Principal"] = {"UnrecognizedKind": "restricted"}
    model = _state("aws_iam_role", {"assume_role_policy": json.dumps({"Statement": [statement]})})
    resource = model.resources["aws_iam_role.example"]
    assert "assume_role_policy" not in resource.values
    assert "assume_role_policy" in resource.unknown_fields
    cloud = resolve_cloud_facts([model], [], config=Config.empty())
    assert cloud.roles[0].trust_unresolved


@pytest.mark.parametrize(
    "reference",
    [
        "module.security.data.aws_iam_policy_document.trust.json",
        "${data.aws_iam_policy_document.trust.json}",
    ],
)
def test_known_policy_reference_forms_remain_metadata(reference: str) -> None:
    model = _state("aws_iam_role", {"assume_role_policy": reference})
    assert model.resources["aws_iam_role.example"].values["assume_role_policy"] == reference


@pytest.mark.parametrize("plan", [False, True], ids=["state", "plan"])
@pytest.mark.parametrize("nested", [False, True], ids=["trust", "inline"])
def test_sensitive_policy_restrictions_are_withheld_not_removed(plan: bool, nested: bool) -> None:
    policy = {
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:PrincipalTag/restricted": _CANARY},
                },
            }
        ]
    }
    values: dict[str, Any] = {"assume_role_policy": policy}
    mask: dict[str, Any] = {"assume_role_policy": {"Statement": [{"Condition": True}]}}
    if nested:
        values = {"inline_policy": [{"name": "read", "policy": policy}]}
        mask = {"inline_policy": [{"policy": {"Statement": [{"Condition": True}]}}]}
    model = _state("aws_iam_role", values, mask, plan=plan)
    _no_canary(model)
    resource = model.resources["aws_iam_role.example"]
    if nested:
        assert resource.values["inline_policy"] == [{"name": "read"}]
        assert "inline_policy[0].policy" in resource.unknown_fields
    else:
        assert "assume_role_policy" not in resource.values
        assert "assume_role_policy" in resource.unknown_fields
    cloud = resolve_cloud_facts([model], [], config=Config.empty())
    assert cloud.roles[0].trust_unresolved
    assert cloud.roles[0].trust_statements == ()
    assert cloud.roles[0].inline_statements == ()


@settings(max_examples=75, deadline=None)
@given(
    mask=st.recursive(
        st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=20)),
        lambda children: st.one_of(
            st.lists(children, max_size=3),
            st.dictionaries(st.sampled_from(["value", "name", "nested"]), children, max_size=3),
        ),
        max_leaves=15,
    )
)
def test_ssm_credential_retention_is_independent_of_any_mask(mask: Any) -> None:
    model = _state("aws_ssm_parameter", {"name": "/prod/key", "value": _CANARY}, mask)
    _no_canary(model)
    assert "value" not in model.resources["aws_ssm_parameter.example"].values
