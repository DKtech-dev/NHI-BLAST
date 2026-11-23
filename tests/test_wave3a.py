"""Wave 3A threat-model tests: IAM persistence, role chaining, and 2026 GHA rules."""

from __future__ import annotations

import json
from pathlib import Path

from nhi_blast.core.models import CompletenessStatus, InputFamily, Severity
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.whatif.engine import run_whatif
from nhi_blast.whatif.plan import synthesize_auto_plan
from nhi_blast.whatif.playbook import render_playbook


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def test_iam_persistence_and_role_chaining_end_to_end(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github" / "workflows" / "deploy.yml",
        """name: Deploy
on:
  push:
    branches: [main]
permissions:
  id-token: write
  contents: read
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@v6
        with:
          role-to-assume: arn:aws:iam::111122223333:role/ci-entry
          audience: sts.amazonaws.com
""",
    )
    tf = {
        "format_version": "1.2",
        "values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_iam_openid_connect_provider.github",
                        "type": "aws_iam_openid_connect_provider",
                        "values": {
                            "url": "https://token.actions.githubusercontent.com",
                            "client_id_list": ["sts.amazonaws.com"],
                        },
                    },
                    {
                        "address": "aws_iam_role.ci_entry",
                        "type": "aws_iam_role",
                        "values": {
                            "name": "ci-entry",
                            "arn": "arn:aws:iam::111122223333:role/ci-entry",
                            "assume_role_policy": json.dumps(
                                {
                                    "Version": "2012-10-17",
                                    "Statement": [
                                        {
                                            "Effect": "Allow",
                                            "Principal": {
                                                "Federated": (
                                                    "arn:aws:iam::111122223333:oidc-provider/"
                                                    "token.actions.githubusercontent.com"
                                                )
                                            },
                                            "Action": "sts:AssumeRoleWithWebIdentity",
                                            "Condition": {
                                                "StringEquals": {
                                                    "token.actions.githubusercontent.com:aud": (
                                                        "sts.amazonaws.com"
                                                    ),
                                                    "token.actions.githubusercontent.com:sub": (
                                                        "repo:acme/app:ref:refs/heads/main"
                                                    ),
                                                }
                                            },
                                        }
                                    ],
                                }
                            ),
                        },
                    },
                    {
                        "address": "aws_iam_role_policy.ci_entry_policy",
                        "type": "aws_iam_role_policy",
                        "values": {
                            "name": "ci-entry-policy",
                            "role": "ci-entry",
                            "policy": json.dumps(
                                {
                                    "Version": "2012-10-17",
                                    "Statement": [
                                        {
                                            "Effect": "Allow",
                                            "Action": [
                                                "iam:CreateAccessKey",
                                                "sts:AssumeRole",
                                            ],
                                            "Resource": "*",
                                        }
                                    ],
                                }
                            ),
                        },
                    },
                    {
                        "address": "aws_iam_role.prod_admin",
                        "type": "aws_iam_role",
                        "values": {
                            "name": "prod-admin",
                            "arn": "arn:aws:iam::111122223333:role/prod-admin",
                            "assume_role_policy": json.dumps(
                                {
                                    "Version": "2012-10-17",
                                    "Statement": [
                                        {
                                            "Effect": "Allow",
                                            "Principal": {
                                                "AWS": "arn:aws:iam::111122223333:role/ci-entry"
                                            },
                                            "Action": "sts:AssumeRole",
                                        }
                                    ],
                                }
                            ),
                        },
                    },
                ]
            }
        },
    }
    _write(tmp_path / "tfstate.json", json.dumps(tf))

    outcome = run_scan(ScanOptions(root=tmp_path, repo_slug="acme/app", selectors=("repo-write",)))
    report = outcome.report
    rule_ids = {f.rule for f in report.findings}
    assert "NHB-PERSIST-001" in rule_ids
    assert "NHB-CHAIN-001" in rule_ids

    # Completeness reflects partially analysed role chaining
    assert report.completeness is not None
    chain_item = next(
        item for item in report.completeness.items if item.family is InputFamily.AWS_ROLE_CHAINING
    )
    assert chain_item.status is CompletenessStatus.PARTIALLY_ANALYSED

    # Rotation plan & playbook include Cloud Persistence Audit
    verify_texts = [
        action for step in report.scenarios[0].rotation_plan.verify for action in step.actions
    ]
    assert any("Cloud Persistence Audit" in text for text in verify_texts)

    auto = synthesize_auto_plan(report)
    whatif_payload = run_whatif(report, auto)
    playbook = render_playbook(report, whatif_payload)
    assert "## Cloud Persistence Audit" in playbook


def test_2026_gha_hardening_rules_unsafe_checkout_ai_agent_and_pkg_hooks(tmp_path: Path) -> None:
    _write(
        tmp_path / ".github" / "workflows" / "triage.lock.yml",
        """name: AI Triage
on:
  issue_comment:
    types: [created]
permissions:
  id-token: write
  contents: read
jobs:
  agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@abcdef0123456789abcdef0123456789abcdef01
        with:
          allow-unsafe-pr-checkout: true
      - uses: anthropics/claude-code-action@abcdef0123456789abcdef0123456789abcdef02
        env:
          API_TOKEN: ${{ secrets.ANTHROPIC_API_KEY }}
      - run: npm install
""",
    )
    outcome = run_scan(ScanOptions(root=tmp_path, repo_slug="acme/app", selectors=("repo-write",)))
    by_rule = {f.rule: f for f in outcome.report.findings}
    assert "NHB-GHA-002" in by_rule
    assert "NHB-GHA-006" in by_rule
    assert "triage.md" in by_rule["NHB-GHA-006"].message
    assert "NHB-GHA-007" in by_rule
    assert by_rule["NHB-GHA-007"].severity in {Severity.MEDIUM, Severity.HIGH}
