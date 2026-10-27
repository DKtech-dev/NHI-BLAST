"""Generate the deterministic fx15 scale fixture (spec 12.8).

The generator writes plain repository files: no random data, no wall clock, no
network access and no credential values. Every run with the same arguments
produces byte-identical files. The checked-in `fx15-scale-smoke` variant is the
same content produced with four workflows and forty Terraform resources.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ACCOUNT = "111122223333"
REGION = "us-east-1"
PROVIDER_ARN = f"arn:aws:iam::{ACCOUNT}:oidc-provider/token.actions.githubusercontent.com"
CHECKOUT_SHA = "abcdef0123456789abcdef0123456789abcdef01"
CREDENTIALS_SHA = "abcdef0123456789abcdef0123456789abcdef02"
REPOSITORY = "acme/scale"
PINNED_CHECKOUT = f"actions/checkout@{CHECKOUT_SHA}"
PINNED_CREDENTIALS = f"aws-actions/configure-aws-credentials@{CREDENTIALS_SHA}"
RESOURCES_PER_WORKFLOW = 9


def _trust_policy(environment: str) -> str:
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Federated": PROVIDER_ARN},
                "Action": "sts:AssumeRoleWithWebIdentity",
                "Condition": {
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": (
                            f"repo:{REPOSITORY}:environment:{environment}"
                        )
                    },
                },
            }
        ],
    }
    return json.dumps(policy, sort_keys=True, separators=(",", ":"))


def _read_policy(index: int) -> str:
    secret_prefix = f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:scale/secret-{index:03d}"
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "secretsmanager:GetSecretValue",
                ],
                "Resource": [
                    (f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/scale/param-{index:03d}/token"),
                    (f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/scale/param-{index:03d}/live-key"),
                    (
                        f"arn:aws:ssm:{REGION}:{ACCOUNT}:"
                        f"parameter/scale/param-{index:03d}/webhook-url"
                    ),
                    f"{secret_prefix}/db-master-*",
                    f"{secret_prefix}/app-config-*",
                ],
            }
        ],
    }
    return json.dumps(policy, sort_keys=True, separators=(",", ":"))


def _workflow_text(index: int, actions_per_workflow: int) -> str:
    environment = f"scale-env-{index:03d}"
    lines = [
        f"name: Scale workflow {index:03d}",
        "on:",
        "  push:",
        "    branches: [main]",
        "permissions:",
        "  contents: read",
        "  id-token: write",
        "jobs:",
        f"  build-{index:03d}:",
        "    runs-on: ubuntu-latest",
        f"    environment: {environment}",
        "    steps:",
        f"      - uses: {PINNED_CHECKOUT}",
    ]
    for action_index in range(actions_per_workflow):
        lines.append(f"      - uses: acme-scale/action-{index:03d}-{action_index}@v1")
    lines.extend(
        (
            f"      - uses: {PINNED_CREDENTIALS}",
            "        with:",
            (f"          role-to-assume: arn:aws:iam::{ACCOUNT}:role/scale-role-{index:03d}"),
            f"          aws-region: {REGION}",
            "      - name: Exercise the fixture",
            '        run: echo "scale fixture"',
        )
    )
    return "\n".join(lines) + "\n"


def _workflow_resources(index: int) -> list[dict[str, Any]]:
    environment = f"scale-env-{index:03d}"
    secret_prefix = f"scale/secret-{index:03d}"
    return [
        {
            "address": f"aws_iam_role.role_{index:03d}",
            "mode": "managed",
            "type": "aws_iam_role",
            "name": f"role_{index:03d}",
            "values": {
                "name": f"scale-role-{index:03d}",
                "arn": f"arn:aws:iam::{ACCOUNT}:role/scale-role-{index:03d}",
                "max_session_duration": 3600,
                "assume_role_policy": _trust_policy(environment),
            },
        },
        {
            "address": f"aws_iam_role_policy.policy_{index:03d}",
            "mode": "managed",
            "type": "aws_iam_role_policy",
            "name": f"policy_{index:03d}",
            "values": {
                "name": f"scale-policy-{index:03d}",
                "role": f"aws_iam_role.role_{index:03d}.id",
                "policy": _read_policy(index),
            },
        },
        {
            "address": f"aws_ssm_parameter.param_{index:03d}_token",
            "mode": "managed",
            "type": "aws_ssm_parameter",
            "name": f"param_{index:03d}_token",
            "values": {
                "name": f"/scale/param-{index:03d}/token",
                "arn": (f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/scale/param-{index:03d}/token"),
                "type": "SecureString",
                "key_id": "alias/aws/ssm",
            },
        },
        {
            "address": f"aws_ssm_parameter.param_{index:03d}_live_key",
            "mode": "managed",
            "type": "aws_ssm_parameter",
            "name": f"param_{index:03d}_live_key",
            "values": {
                "name": f"/scale/param-{index:03d}/live-key",
                "arn": (
                    f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/scale/param-{index:03d}/live-key"
                ),
                "type": "SecureString",
                "key_id": "alias/aws/ssm",
            },
        },
        {
            "address": f"aws_ssm_parameter.param_{index:03d}_webhook",
            "mode": "managed",
            "type": "aws_ssm_parameter",
            "name": f"param_{index:03d}_webhook",
            "values": {
                "name": f"/scale/param-{index:03d}/webhook-url",
                "arn": (
                    f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/scale/param-{index:03d}/webhook-url"
                ),
                "type": "SecureString",
                "key_id": "alias/aws/ssm",
            },
        },
        {
            "address": f"aws_secretsmanager_secret.db_master_{index:03d}",
            "mode": "managed",
            "type": "aws_secretsmanager_secret",
            "name": f"db_master_{index:03d}",
            "values": {
                "name": f"{secret_prefix}/db-master",
                "arn": (
                    f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:"
                    f"secret:{secret_prefix}/db-master-a1b2c3"
                ),
            },
        },
        {
            "address": f"aws_secretsmanager_secret.app_config_{index:03d}",
            "mode": "managed",
            "type": "aws_secretsmanager_secret",
            "name": f"app_config_{index:03d}",
            "values": {
                "name": f"{secret_prefix}/app-config",
                "arn": (
                    f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:"
                    f"secret:{secret_prefix}/app-config-d4e5f6"
                ),
            },
        },
        {
            "address": f"aws_secretsmanager_secret_version.app_config_{index:03d}",
            "mode": "managed",
            "type": "aws_secretsmanager_secret_version",
            "name": f"app_config_{index:03d}",
            "values": {"secret_id": f"{secret_prefix}/app-config"},
        },
        {
            "address": f"aws_secretsmanager_secret_rotation.app_config_{index:03d}",
            "mode": "managed",
            "type": "aws_secretsmanager_secret_rotation",
            "name": f"app_config_{index:03d}",
            "values": {"rotation_rules": [{"automatically_after_days": 30}]},
        },
    ]


def _extra_parameter(index: int) -> dict[str, Any]:
    return {
        "address": f"aws_ssm_parameter.extra_{index:04d}",
        "mode": "managed",
        "type": "aws_ssm_parameter",
        "name": f"extra_{index:04d}",
        "values": {
            "name": f"/scale/extra/{index:04d}",
            "arn": f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/scale/extra/{index:04d}",
            "type": "SecureString",
            "key_id": "alias/aws/ssm",
        },
    }


def _provider_resource() -> dict[str, Any]:
    return {
        "address": "aws_iam_openid_connect_provider.github",
        "mode": "managed",
        "type": "aws_iam_openid_connect_provider",
        "name": "github",
        "values": {
            "url": "https://token.actions.githubusercontent.com",
            "client_id_list": ["sts.amazonaws.com"],
        },
    }


def _state_text(*, workflows: int, resources: int) -> str:
    minimum = 1 + workflows * RESOURCES_PER_WORKFLOW
    if resources < minimum:
        msg = (
            f"--resources must be at least {minimum} for {workflows} workflows "
            f"(one provider plus {RESOURCES_PER_WORKFLOW} resources per workflow)"
        )
        raise ValueError(msg)
    remaining = resources - workflows * RESOURCES_PER_WORKFLOW - 1
    all_resources: list[dict[str, Any]] = [_provider_resource()]
    for index in range(workflows):
        all_resources.extend(_workflow_resources(index))
    for index in range(remaining):
        all_resources.append(_extra_parameter(index))
    if len(all_resources) != resources:
        msg = f"generated {len(all_resources)} resources, expected {resources}"
        raise AssertionError(msg)
    state = {
        "format_version": "1.0",
        "version": 4,
        "terraform_version": "1.9.8",
        "serial": 1,
        "lineage": "0f0f0f0f-1111-2222-3333-444444444444",
        "outputs": {},
        "resources": [],
        "values": {"root_module": {"resources": all_resources}},
    }
    return json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _readme_text(*, workflows: int, resources: int, actions_per_workflow: int) -> str:
    return (
        "# fx15 scale fixture (generated)\n"
        "\n"
        "Generated by `scripts/gen_fixtures.py`; do not edit by hand. The exact\n"
        "command for this variant is recorded in the root fixture README.\n"
        "\n"
        f"- Workflows: {workflows}\n"
        f"- Jobs: {workflows}\n"
        f"- Terraform resources: {resources}\n"
        f"- Mutable actions per workflow: {actions_per_workflow}\n"
        f"- Total mutable action use sites: {workflows * actions_per_workflow}\n"
        "\n"
        "Every workflow job uses a unique GitHub environment, and each IAM role\n"
        "trusts only that environment subject. Terraform reads stay per role, so the\n"
        "fixture exercises quantity without quadratic cross-role authority.\n"
        "\n"
        "No credential values are present. Parameter, secret and version resources\n"
        "carry names and metadata only.\n"
    )


def generate_fixture(
    out: Path,
    *,
    workflows: int = 200,
    resources: int = 2000,
    actions_per_workflow: int = 2,
) -> None:
    """Write one deterministic fixture tree to ``out``."""
    if workflows < 1:
        msg = "--workflows must be at least 1"
        raise ValueError(msg)
    if actions_per_workflow < 1:
        msg = "--actions-per-workflow must be at least 1"
        raise ValueError(msg)
    state = _state_text(workflows=workflows, resources=resources)
    out.mkdir(parents=True, exist_ok=True)
    git_dir = out / ".git"
    git_dir.mkdir(exist_ok=True)
    (git_dir / "config").write_text(
        '[remote "origin"]\n'
        f"    url = https://github.com/{REPOSITORY}.git\n"
        "    fetch = +refs/heads/*:refs/remotes/origin/*\n",
        encoding="utf-8",
        newline="\n",
    )
    workflow_dir = out / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    for index in range(workflows):
        path = workflow_dir / f"wf-{index:03d}.yml"
        path.write_text(
            _workflow_text(index, actions_per_workflow),
            encoding="utf-8",
            newline="\n",
        )
    (out / "tfstate.json").write_text(state, encoding="utf-8", newline="\n")
    (out / "README.md").write_text(
        _readme_text(
            workflows=workflows,
            resources=resources,
            actions_per_workflow=actions_per_workflow,
        ),
        encoding="utf-8",
        newline="\n",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "out",
        nargs="?",
        type=Path,
        help="output directory (default: a full fixture under the system temp directory)",
    )
    parser.add_argument("--workflows", type=int, default=200)
    parser.add_argument("--resources", type=int, default=2000)
    parser.add_argument("--actions-per-workflow", type=int, default=2)
    args = parser.parse_args(argv)
    out = args.out
    if out is None:
        out = Path(tempfile.gettempdir()) / "nhi-blast-fx15"
    try:
        generate_fixture(
            out,
            workflows=args.workflows,
            resources=args.resources,
            actions_per_workflow=args.actions_per_workflow,
        )
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"cannot generate fixture: {exc}\n")
        return 1
    sys.stdout.write(
        f"Generated {args.workflows} workflows, {args.resources} Terraform resources in {out}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
