"""Cloud fact resolution against state, HCL and IAM JSON inputs (M2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhi_blast.core.config import Config
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    CredentialKind,
    SinkType,
    TfSource,
)
from nhi_blast.parsers.iam.policy_doc import parse_iam_document
from nhi_blast.parsers.terraform.facts import TfModelFact, TfPolicyDocumentFact, TfResource
from nhi_blast.parsers.terraform.tfhcl import parse_tf_hcl
from nhi_blast.parsers.terraform.tfjson import parse_tf_json
from nhi_blast.resolvers.roles import CloudFacts, resolve_cloud_facts

LIMITS = Limits()
TRUSTED_PROVIDER = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
SUB_KEY = "token.actions.githubusercontent.com:sub"


def load_json_state(fixtures_dir: Path, folder: str) -> TfModelFact:
    path = fixtures_dir / folder / "tfstate.json"
    result = parse_tf_json("tfstate.json", path.read_text(encoding="utf-8"), limits=LIMITS)
    assert result.facts is not None
    assert result.diagnostics == ()
    return result.facts


def resolve_fixture(fixtures_dir: Path, folder: str) -> CloudFacts:
    return resolve_cloud_facts(
        [load_json_state(fixtures_dir, folder)],
        [],
        config=Config.empty(),
    )


def dump(facts: CloudFacts) -> str:
    return json.dumps(
        {
            "roles": [role.model_dump(mode="json") for role in facts.roles],
            "sinks": [sink.model_dump(mode="json") for sink in facts.sinks],
            "providers": [provider.model_dump(mode="json") for provider in facts.providers],
            "externals": [target.model_dump(mode="json") for target in facts.externals],
            "policy_context": facts.policy_context.model_dump(mode="json"),
            "diagnostics": [diagnostic.model_dump(mode="json") for diagnostic in facts.diagnostics],
        },
        sort_keys=True,
    )


def _resource(
    address: str,
    type_name: str,
    values: dict[str, object],
    *,
    source: TfSource = TfSource.STATE,
) -> TfResource:
    kind, _, name = address.partition(".")
    return TfResource(
        address=address,
        mode="data" if kind == "data" else "managed",
        type=type_name,
        name=name.rsplit(".", 1)[-1],
        values=dict(values),
        source=source,
        file="main.tfstate.json",
        line=1,
    )


def test_fx02_exact_trust_role_sink_and_provider(fixtures_dir: Path) -> None:
    facts = resolve_fixture(fixtures_dir, "fx02-exact-trust")

    assert [role.name for role in facts.roles] == ["deploy-prod"]
    role = facts.roles[0]
    assert role.arn == "arn:aws:iam::111122223333:role/deploy-prod"
    assert role.max_session_duration == 3600
    assert role.trust_unresolved is False
    assert role.unresolved_policy_refs == ()
    statement = role.trust_statements[0]
    assert statement.principals == {"Federated": (TRUSTED_PROVIDER,)}
    assert statement.conditions["StringLike"]["token.actions.githubusercontent.com:sub"] == (
        "repo:acme/shop:ref:refs/tags/v*",
    )
    assert statement.conditions["StringEquals"]["token.actions.githubusercontent.com:aud"] == (
        "sts.amazonaws.com",
    )
    assert role.inline_statements[0].actions == ("ssm:GetParameter",)

    assert len(facts.sinks) == 1
    sink = facts.sinks[0]
    assert sink.name == "/prod/stripe/live_key"
    assert sink.sink_type is SinkType.SSM_PARAMETER
    assert sink.credential_kind is CredentialKind.API_KEY
    assert sink.criticality == 70
    assert sink.rotation_interval_days is None

    assert [(provider.host, provider.client_ids) for provider in facts.providers] == [
        ("token.actions.githubusercontent.com", ("sts.amazonaws.com",))
    ]
    assert facts.policy_context.account == "111122223333"
    assert facts.policy_context.region == "us-east-1"
    assert facts.diagnostics == ()


def test_fx03_wildcard_roles_preserve_trust_variants(fixtures_dir: Path) -> None:
    facts = resolve_fixture(fixtures_dir, "fx03-wildcard-trust")
    by_name = {role.name: role for role in facts.roles}

    assert sorted(by_name) == [
        "admin-unconstrained",
        "dead-condition",
        "legacy-ci",
        "no-audience",
    ]
    legacy = by_name["legacy-ci"].trust_statements[0]
    assert legacy.conditions["StringLike"]["token.actions.githubusercontent.com:sub"] == (
        "repo:acme/*",
    )
    assert legacy.principals == {"Federated": (TRUSTED_PROVIDER,)}

    admin = by_name["admin-unconstrained"].trust_statements[0]
    assert "StringLike" not in admin.conditions

    dead = by_name["dead-condition"].trust_statements[0]
    assert dead.conditions["StringEquals"][
        "token.actions.githubusercontent.com:repository_owner"
    ] == ("acme",)

    no_aud = by_name["no-audience"].trust_statements[0]
    assert "StringEquals" not in no_aud.conditions

    assert [(sink.name, sink.credential_kind) for sink in facts.sinks] == [
        ("/legacy/ci-token", CredentialKind.API_TOKEN)
    ]


def test_fx07_sink_kinds_and_rotation(fixtures_dir: Path) -> None:
    facts = resolve_fixture(fixtures_dir, "fx07-incident")
    sinks = {sink.name: sink for sink in facts.sinks}

    assert sorted(sinks) == [
        "/legacy/ci-token",
        "/prod/stripe/live_key",
        "prod/app-config",
        "prod/db-master",
    ]
    assert sinks["prod/app-config"].rotation_interval_days == 30
    assert sinks["prod/db-master"].rotation_interval_days is None
    assert sinks["/prod/stripe/live_key"].rotation_interval_days is None
    assert sinks["/prod/stripe/live_key"].credential_kind is CredentialKind.API_KEY
    assert sinks["/legacy/ci-token"].credential_kind is CredentialKind.API_TOKEN
    assert sinks["prod/app-config"].sink_type is SinkType.SECRETSMANAGER_SECRET
    assert sinks["prod/app-config"].arn == (
        "arn:aws:secretsmanager:us-east-1:111122223333:secret:prod/app-config-??????"
    )

    roles = {role.name: role for role in facts.roles}
    assert sorted(roles) == ["deploy-prod", "legacy-ci"]
    deploy_actions = {
        action
        for statement in roles["deploy-prod"].inline_statements
        for action in statement.actions
    }
    assert "secretsmanager:GetSecretValue" in deploy_actions
    assert "ssm:GetParameter" in deploy_actions

    rendered = dump(facts)
    assert "FIXTURE_ONLY_PLACEHOLDER_DB_MASTER_VALUE" not in rendered


def test_hcl_fallback_is_derived_and_never_guesses_for_each(fixtures_dir: Path) -> None:
    path = fixtures_dir / "fx10-hcl-fallback" / "main.tf"
    parsed = parse_tf_hcl("main.tf", path.read_text(encoding="utf-8"), limits=LIMITS)
    assert parsed.facts is not None
    assert {diagnostic.code for diagnostic in parsed.diagnostics} == {"D-TF-HCL-LIMIT"}

    facts = resolve_cloud_facts([parsed.facts], [], config=Config.empty())
    roles = {role.name: role for role in facts.roles}

    assert sorted(roles) == ["deploy-prod", "multi"]
    assert roles["deploy-prod"].trust_unresolved is False
    assert roles["deploy-prod"].trust_statements[0].conditions["StringLike"][
        "token.actions.githubusercontent.com:sub"
    ] == ("repo:acme/shop:ref:refs/heads/main",)
    assert roles["deploy-prod"].inline_statements[0].actions == ("ssm:GetParameter",)
    assert roles["multi"].trust_unresolved is True
    assert all(
        evidence.cls is EvidenceClass.DERIVED for role in facts.roles for evidence in role.evidence
    )
    assert {diagnostic.code for diagnostic in facts.diagnostics} == {"D-TF-UNKNOWN"}

    assert [(sink.name, sink.credential_kind) for sink in facts.sinks] == [
        ("/prod/pipeline-token", CredentialKind.API_TOKEN)
    ]
    assert "FIXTURE_PLACEHOLDER_VALUE_NOT_A_SECRET" not in dump(facts)


def test_hcl_parser_accepts_crlf_line_endings() -> None:
    text = (
        'resource "aws_iam_role" "deploy" {\r\n'
        '  name = "deploy"\r\n'
        '  assume_role_policy = jsonencode({ Version = "2012-10-17" })\r\n'
        "}\r\n"
    )

    parsed = parse_tf_hcl("main.tf", text, limits=LIMITS)

    assert parsed.facts is not None
    assert parsed.facts.resources
    assert "D-TF-HCL-PARSE" not in {diagnostic.code for diagnostic in parsed.diagnostics}


def test_hcl_parser_reports_missing_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(_name: str) -> object:
        message = "hcl2"
        raise ModuleNotFoundError(message)

    monkeypatch.setattr("nhi_blast.parsers.terraform.tfhcl.importlib.import_module", unavailable)
    parsed = parse_tf_hcl("main.tf", 'resource "x" "y" {}', limits=LIMITS)

    assert parsed.facts is None
    [diagnostic] = parsed.diagnostics
    assert diagnostic.code == "D-TF-HCL-UNAVAILABLE"
    assert "install the 'hcl' extra" in diagnostic.message


def test_tf_json_configuration_is_read_without_the_hcl_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(_name: str) -> object:
        message = "hcl2"
        raise ModuleNotFoundError(message)

    monkeypatch.setattr("nhi_blast.parsers.terraform.tfhcl.importlib.import_module", unavailable)
    document = {
        "variable": {
            "trusted_ref": {
                "type": "string",
                "default": "repo:acme/shop:ref:refs/heads/main",
            }
        },
        "data": {
            "aws_iam_policy_document": {
                "trust": {
                    "statement": [
                        {
                            "effect": "Allow",
                            "principals": [
                                {"type": "Federated", "identifiers": [TRUSTED_PROVIDER]}
                            ],
                            "actions": ["sts:AssumeRoleWithWebIdentity"],
                            "condition": [
                                {
                                    "test": "StringLike",
                                    "variable": SUB_KEY,
                                    "values": ["${var.trusted_ref}"],
                                }
                            ],
                        }
                    ]
                }
            }
        },
        "resource": {
            "aws_iam_role": {
                "deploy": {
                    "name": "deploy",
                    "assume_role_policy": "${data.aws_iam_policy_document.trust.json}",
                }
            },
            "aws_ssm_parameter": {
                "token": {
                    "name": "/prod/token",
                    "type": "SecureString",
                    "value": "FIXTURE_ONLY_PLACEHOLDER_VALUE",
                }
            },
        },
    }

    parsed = parse_tf_hcl("main.tf.json", json.dumps(document), limits=LIMITS)

    assert parsed.facts is not None
    assert "D-TF-HCL-PARSE" not in {diagnostic.code for diagnostic in parsed.diagnostics}
    assert parsed.facts.resources["aws_iam_role.deploy"].source is TfSource.HCL
    assert parsed.facts.policy_documents["data.aws_iam_policy_document.trust"].json_text is not None

    facts = resolve_cloud_facts([parsed.facts], [], config=Config.empty())
    role = facts.roles[0]
    assert role.name == "deploy"
    assert role.trust_unresolved is False
    assert role.trust_statements[0].principals == {"Federated": (TRUSTED_PROVIDER,)}
    assert role.trust_statements[0].conditions["StringLike"][SUB_KEY] == (
        "repo:acme/shop:ref:refs/heads/main",
    )
    assert [sink.name for sink in facts.sinks] == ["/prod/token"]
    assert "FIXTURE_ONLY_PLACEHOLDER_VALUE" not in dump(facts)


def test_tf_json_configuration_reports_malformed_json() -> None:
    parsed = parse_tf_hcl("main.tf.json", "{", limits=LIMITS)

    assert parsed.facts is None
    [diagnostic] = parsed.diagnostics
    assert diagnostic.code == "D-TF-HCL-PARSE"
    assert "JSON configuration" in diagnostic.message


def test_hcl_policy_document_reference_survives_parsing() -> None:
    text = """
data "aws_iam_policy_document" "trust" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = ["PROVIDER_PLACEHOLDER"]
    }
    actions = ["sts:AssumeRoleWithWebIdentity"]
  }
}

resource "aws_iam_role" "referenced" {
  name                 = "referenced"
  assume_role_policy   = data.aws_iam_policy_document.trust.json
}
""".replace("PROVIDER_PLACEHOLDER", TRUSTED_PROVIDER)

    parsed = parse_tf_hcl("main.tf", text, limits=LIMITS)

    assert parsed.facts is not None
    assert parsed.facts.resources["aws_iam_role.referenced"].values["assume_role_policy"] == (
        "data.aws_iam_policy_document.trust.json"
    )
    facts = resolve_cloud_facts([parsed.facts], [], config=Config.empty())
    role = facts.roles[0]
    assert role.trust_unresolved is False
    assert role.trust_statements[0].principals == {"Federated": (TRUSTED_PROVIDER,)}


def test_managed_policy_attachment_and_boundary_resolution() -> None:
    policy_arn = "arn:aws:iam::111122223333:policy/shared"
    model = TfModelFact(
        source=TfSource.STATE,
        file="tfstate.json",
        resources={
            "aws_iam_policy.shared": _resource(
                "aws_iam_policy.shared",
                "aws_iam_policy",
                {
                    "name": "shared",
                    "arn": policy_arn,
                    "policy": json.dumps(
                        {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Action": ["s3:GetObject"],
                                    "Resource": ["arn:aws:s3:::bucket/*"],
                                }
                            ],
                        }
                    ),
                },
            ),
            "aws_iam_role.worker": _resource(
                "aws_iam_role.worker",
                "aws_iam_role",
                {
                    "name": "worker",
                    "arn": "arn:aws:iam::111122223333:role/worker",
                    "assume_role_policy": json.dumps(
                        {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Principal": {"Service": "ec2.amazonaws.com"},
                                    "Action": "sts:AssumeRole",
                                }
                            ],
                        }
                    ),
                    "managed_policy_arns": [policy_arn],
                },
            ),
            "aws_iam_role.bounded": _resource(
                "aws_iam_role.bounded",
                "aws_iam_role",
                {
                    "name": "bounded",
                    "arn": "arn:aws:iam::111122223333:role/bounded",
                    "assume_role_policy": json.dumps(
                        {
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Principal": {"Service": "lambda.amazonaws.com"},
                                    "Action": "sts:AssumeRole",
                                }
                            ],
                        }
                    ),
                    "permissions_boundary": policy_arn,
                },
            ),
        },
    )

    facts = resolve_cloud_facts([model], [], config=Config.empty())
    roles = {role.name: role for role in facts.roles}

    assert roles["worker"].managed_policy_arns == (policy_arn,)
    assert facts.policy_context.managed_policies[policy_arn][0].actions == ("s3:GetObject",)
    assert roles["bounded"].boundary_supplied is True
    assert roles["bounded"].boundary_statements[0].actions == ("s3:GetObject",)


def test_policy_document_reference_resolves_trust() -> None:
    document_json = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": TRUSTED_PROVIDER},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {"StringLike": {SUB_KEY: "repo:acme/shop:ref:refs/heads/main"}},
                }
            ],
        }
    )
    model = TfModelFact(
        source=TfSource.STATE,
        file="tfstate.json",
        resources={
            "aws_iam_role.referenced": _resource(
                "aws_iam_role.referenced",
                "aws_iam_role",
                {
                    "name": "referenced",
                    "arn": "arn:aws:iam::111122223333:role/referenced",
                    "assume_role_policy": "${data.aws_iam_policy_document.trust.json}",
                },
            )
        },
        policy_documents={
            "data.aws_iam_policy_document.trust": TfPolicyDocumentFact(
                address="data.aws_iam_policy_document.trust",
                json_text=document_json,
                file="tfstate.json",
            )
        },
    )

    facts = resolve_cloud_facts([model], [], config=Config.empty())
    role = facts.roles[0]
    assert role.trust_unresolved is False
    assert role.trust_statements[0].principals == {"Federated": (TRUSTED_PROVIDER,)}


def test_unresolved_policy_is_reported_not_guessed() -> None:
    model = TfModelFact(
        source=TfSource.STATE,
        file="tfstate.json",
        resources={
            "aws_iam_role.opaque": _resource(
                "aws_iam_role.opaque",
                "aws_iam_role",
                {
                    "name": "opaque",
                    "arn": "arn:aws:iam::111122223333:role/opaque",
                    "assume_role_policy": "not-json",
                },
            )
        },
    )
    facts = resolve_cloud_facts([model], [], config=Config.empty())
    assert facts.roles[0].trust_unresolved is True
    assert "D-TF-POLICY-UNRESOLVED" in {diagnostic.code for diagnostic in facts.diagnostics}


def test_iam_json_role_only_and_unbound_policy() -> None:
    get_role = {
        "Role": {
            "Arn": "arn:aws:iam::111122223333:role/from-iam",
            "RoleName": "from-iam",
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Federated": TRUSTED_PROVIDER},
                        "Action": "sts:AssumeRoleWithWebIdentity",
                        "Condition": {
                            "StringLike": {SUB_KEY: "repo:acme/shop:ref:refs/heads/main"}
                        },
                    }
                ],
            },
        }
    }
    role_document, role_diagnostics = parse_iam_document(
        json.dumps(get_role), label="get-role.json"
    )
    assert role_document is not None
    assert role_diagnostics == ()

    unbound_document, unbound_diagnostics = parse_iam_document(
        json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": ["*"]}],
            }
        ),
        label="unbound.json",
    )
    assert unbound_document is not None
    assert unbound_diagnostics == ()

    facts = resolve_cloud_facts(
        [],
        [role_document, unbound_document],
        config=Config.empty(),
    )
    assert [role.name for role in facts.roles] == ["from-iam"]
    assert facts.roles[0].trust_statements[0].principals == {"Federated": (TRUSTED_PROVIDER,)}
    codes = {diagnostic.code for diagnostic in facts.diagnostics}
    assert "D-IAM-ROLE-ONLY" in codes
    assert "D-IAM-UNBOUND" in codes


def test_database_external_target_requires_a_binding() -> None:
    model = TfModelFact(
        source=TfSource.STATE,
        file="tfstate.json",
        resources={
            "aws_db_instance.unbound": _resource(
                "aws_db_instance.unbound",
                "aws_db_instance",
                {"identifier": "orders"},
            ),
            "aws_db_instance.bound": _resource(
                "aws_db_instance.bound",
                "aws_db_instance",
                {"identifier": "billing", "manage_master_user_password": True},
            ),
        },
    )
    facts = resolve_cloud_facts([model], [], config=Config.empty())
    assert [target.label for target in facts.externals] == [
        "database:billing",
        "database:orders",
    ]
    unbound = [
        diagnostic for diagnostic in facts.diagnostics if diagnostic.code == "D-TF-DB-UNBOUND"
    ]
    assert len(unbound) == 1
    assert "orders" in unbound[0].message
