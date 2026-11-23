"""Tests for Loop 1 GHA parser and resolver hardening fixes."""

from __future__ import annotations

import json

from nhi_blast.core.config import Config
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import PinKind, TfSource
from nhi_blast.parsers.gha.expressions import contains_head_ref_marker, scan_text
from nhi_blast.parsers.gha.uses import classify_pin, is_action, local_action_dir, parse_uses
from nhi_blast.parsers.gha.workflow import parse_composite_action, parse_workflow
from nhi_blast.parsers.terraform.facts import TfModelFact, TfResource
from nhi_blast.resolvers.composite import expand_jobs
from nhi_blast.resolvers.roles import resolve_cloud_facts


def _limits() -> Limits:
    return Limits()


# ---------------------------------------------------------------------------
# 1. expressions.py
# ---------------------------------------------------------------------------


def test_expressions_negative_lookbehind_prevents_false_matches() -> None:
    refs = scan_text(
        "${{ github.event.secrets.FOO }} "
        "${{ my_secrets.BAR }} "
        "${{ payload.secrets['BAZ'] }} "
        "${{ custom_env.TOKEN }} "
        "${{ obj.env['NESTED'] }} "
        "${{ custom_vars.FLAG }} "
        "${{ obj.vars['OTHER'] }}"
    )
    assert refs.secrets == ()
    assert refs.vars == ()
    assert refs.env == ()
    assert refs.secrets_all is False


def test_expressions_bracket_index_vars_and_env() -> None:
    refs = scan_text(
        "${{ vars['FOO'] }} ${{ vars[\"BAR-BAZ\"] }} "
        "${{ env['MY-VAR'] }} ${{ env[\"OTHER_ENV\"] }} "
        "${{ format('{0}', vars.PLAIN) }} ${{ !env.DEBUG }}"
    )
    assert refs.vars == ("BAR-BAZ", "FOO", "PLAIN")
    assert refs.env == ("DEBUG", "MY-VAR", "OTHER_ENV")


def test_expressions_expanded_head_ref_patterns() -> None:
    for expr in (
        "${{ github.event.workflow_run.head_sha }}",
        "${{ github.event.workflow_run.head_branch }}",
        "${{ github.event.workflow_run.head_repository.full_name }}",
        "${{ github.event.pull_request.merge_commit_sha }}",
    ):
        assert scan_text(expr).head_ref_use is True, expr
        assert contains_head_ref_marker(expr) is True, expr


# ---------------------------------------------------------------------------
# 2. uses.py
# ---------------------------------------------------------------------------


def test_uses_self_repository_dollar_slash_syntax() -> None:
    uses = parse_uses("$/actions/deploy/", 12)
    assert uses.kind == "LOCAL"
    assert uses.pin_kind is PinKind.LOCAL
    assert uses.mutable is False
    assert uses.first_party is True
    assert local_action_dir(uses) == "actions/deploy"

    root_uses = parse_uses("$/", 15)
    assert root_uses.kind == "LOCAL"
    assert local_action_dir(root_uses) == "."


def test_uses_strict_sha1_and_docker_digest_pinning() -> None:
    valid_sha1 = "a" * 40
    sha256_hex = "b" * 64

    pinned = parse_uses(f"actions/checkout@{valid_sha1}", 1)
    assert pinned.pin_kind is PinKind.SHA
    assert pinned.mutable is False

    # 64-char hex is NOT a valid Git SHA-1 for GitHub Actions repos
    too_long = parse_uses(f"actions/checkout@{sha256_hex}", 2)
    assert too_long.pin_kind is PinKind.AMBIGUOUS
    assert too_long.mutable is True

    short = parse_uses(f"actions/checkout@{'a' * 39}", 3)
    assert short.pin_kind is PinKind.AMBIGUOUS
    assert short.mutable is True

    # Docker image digests require strict sha256:<64 hex>
    docker_ok = parse_uses(f"docker://alpine@sha256:{sha256_hex}", 4)
    assert docker_ok.pin_kind is PinKind.SHA
    assert docker_ok.mutable is False
    assert classify_pin(f"sha256:{sha256_hex}", is_docker=True) is PinKind.SHA

    for bad_digest in (
        "sha256:deadbeef",
        f"sha256:{'b' * 63}",
        f"sha256:{'g' * 64}",
        sha256_hex,
    ):
        docker_bad = parse_uses(f"docker://alpine@{bad_digest}", 5)
        assert docker_bad.pin_kind is PinKind.DOCKER
        assert docker_bad.mutable is True
        assert classify_pin(bad_digest, is_docker=True) is PinKind.DOCKER

    assert classify_pin(None, is_docker=True) is PinKind.DOCKER


def test_uses_normalises_redundant_slashes_and_dot_segments() -> None:
    u1 = parse_uses("actions//checkout@v4", 1)
    assert u1.owner == "actions"
    assert u1.repo == "checkout"
    assert u1.subpath is None
    assert is_action(u1, "actions", "checkout") is True

    u2 = parse_uses("aws-actions/configure-aws-credentials/.@v4", 2)
    assert u2.owner == "aws-actions"
    assert u2.repo == "configure-aws-credentials"
    assert u2.subpath is None
    assert is_action(u2, "aws-actions", "configure-aws-credentials") is True

    u3 = parse_uses("actions/cache/./save@v4", 3)
    assert u3.owner == "actions"
    assert u3.repo == "cache"
    assert u3.subpath == "save"
    assert is_action(u3, "actions", "cache") is True


# ---------------------------------------------------------------------------
# 3. workflow.py
# ---------------------------------------------------------------------------


def test_workflow_accepts_aws_cn_role_arn() -> None:
    yaml_text = """
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws-cn:iam::123456789012:role/china-deploy
"""
    result = parse_workflow(".github/workflows/cn.yml", yaml_text, limits=_limits())
    assert result.facts is not None
    aws_auth = result.facts.jobs["deploy"].steps[0].aws_auth
    assert aws_auth is not None
    assert aws_auth.role_ref_kind == "ARN"
    assert aws_auth.role_arn == "arn:aws-cn:iam::123456789012:role/china-deploy"


def test_workflow_privileged_review_events_and_gh_pr_checkout() -> None:
    for event in ("pull_request_review", "pull_request_review_comment"):
        yaml_text = f"""
on: {event}
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.pull_request.head.sha }}}}
      - run: make test
"""
        result = parse_workflow(f".github/workflows/{event}.yml", yaml_text, limits=_limits())
        assert result.facts is not None
        assert result.facts.jobs["review"].untrusted_checkout is True

    gh_cli_yaml = """
on: issue_comment
jobs:
  comment:
    runs-on: ubuntu-latest
    steps:
      - run: gh pr checkout "${{ github.event.issue.number }}"
"""
    gh_result = parse_workflow(".github/workflows/gh-pr.yml", gh_cli_yaml, limits=_limits())
    assert gh_result.facts is not None
    assert gh_result.facts.jobs["comment"].untrusted_checkout is True

    commented_yaml = """
on: issue_comment
jobs:
  safe:
    runs-on: ubuntu-latest
    steps:
      - run: |
          # gh pr checkout 42
          echo "hello"
"""
    safe_result = parse_workflow(".github/workflows/safe.yml", commented_yaml, limits=_limits())
    assert safe_result.facts is not None
    assert safe_result.facts.jobs["safe"].untrusted_checkout is False


def test_workflow_unconstrained_pkg_install_hardening() -> None:
    yaml_text = """
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: comment bypass attempt
        run: npm ci # --ignore-scripts
      - name: frozen lockfile still runs scripts
        run: yarn install --frozen-lockfile
      - name: immutable still runs scripts
        run: yarn install --immutable
      - name: ignore scripts is safe
        run: npm ci --ignore-scripts
      - name: no scripts is safe
        run: poetry install --no-scripts
      - name: commented install is safe
        run: |
          # npm install
          echo done
"""
    result = parse_workflow(".github/workflows/pkg.yml", yaml_text, limits=_limits())
    assert result.facts is not None
    steps = result.facts.jobs["test"].steps
    assert steps[0].unconstrained_pkg_install is True
    assert steps[1].unconstrained_pkg_install is True
    assert steps[2].unconstrained_pkg_install is True
    assert steps[3].unconstrained_pkg_install is False
    assert steps[4].unconstrained_pkg_install is False
    assert steps[5].unconstrained_pkg_install is False


# ---------------------------------------------------------------------------
# 4. composite.py
# ---------------------------------------------------------------------------


def test_composite_case_insensitive_using_and_flag_recomputation() -> None:
    wf_yaml = """
on: pull_request_target
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: $/actions/helper
"""
    action_yaml = """
name: Helper
runs:
  using: "  Composite  "
  steps:
    - uses: actions/checkout@v4
      with:
        ref: ${{ github.event.pull_request.head.sha }}
    - uses: anthropics/claude-code-action@v1
    - run: npm ci --frozen-lockfile
"""
    wf = parse_workflow(".github/workflows/ci.yml", wf_yaml, limits=_limits()).facts
    comp = parse_composite_action("actions/helper/action.yml", action_yaml, limits=_limits()).facts
    assert wf is not None
    assert comp is not None

    # Before expansion, none of the flags are set on the calling job
    assert wf.jobs["build"].untrusted_checkout is False
    assert wf.jobs["build"].ai_agent_workflow is False
    assert wf.jobs["build"].unconstrained_pkg_install is False

    expanded = expand_jobs([wf], {"actions/helper/action.yml": comp}, limits=_limits())
    assert len(expanded) == 1
    job = expanded[0].job
    assert job.untrusted_checkout is True
    assert job.untrusted_checkout_line is not None
    assert job.ai_agent_workflow is True
    assert job.unconstrained_pkg_install is True
    assert job.unconstrained_pkg_line is not None


# ---------------------------------------------------------------------------
# 5. roles.py
# ---------------------------------------------------------------------------


def test_resolve_cloud_facts_merges_duplicate_role_drafts() -> None:
    shared_arn = "arn:aws:iam::123456789012:role/shared-ci"
    trust_a = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": "arn:aws:iam::123456789012:oidc-provider/a"},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                }
            ],
        }
    )
    trust_b = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": "arn:aws:iam::123456789012:oidc-provider/b"},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                }
            ],
        }
    )
    inline_a = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"}],
        }
    )
    inline_b = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "kms:Decrypt", "Resource": "*"}],
        }
    )
    model = TfModelFact(
        file="main.tf",
        source=TfSource.HCL,
        resources={
            "aws_iam_role.a": TfResource(
                address="aws_iam_role.a",
                mode="managed",
                type="aws_iam_role",
                name="a",
                file="main.tf",
                line=1,
                source=TfSource.HCL,
                values={
                    "name": "shared-ci",
                    "arn": shared_arn,
                    "assume_role_policy": trust_a,
                    "inline_policy": [{"name": "p_a", "policy": inline_a}],
                    "managed_policy_arns": ["arn:aws:iam::aws:policy/ReadOnlyAccess"],
                },
            ),
            "aws_iam_role.b": TfResource(
                address="aws_iam_role.b",
                mode="managed",
                type="aws_iam_role",
                name="b",
                file="other.tf",
                line=10,
                source=TfSource.HCL,
                values={
                    "name": "shared-ci",
                    "arn": shared_arn,
                    "assume_role_policy": trust_b,
                    "inline_policy": [{"name": "p_b", "policy": inline_b}],
                    "managed_policy_arns": ["arn:aws:iam::aws:policy/PowerUserAccess"],
                },
            ),
            "aws_iam_role_policy_attachment.on_b": TfResource(
                address="aws_iam_role_policy_attachment.on_b",
                mode="managed",
                type="aws_iam_role_policy_attachment",
                name="on_b",
                file="other.tf",
                line=25,
                source=TfSource.HCL,
                values={
                    "role": "aws_iam_role.b.name",
                    "policy_arn": "arn:aws:iam::aws:policy/IAMReadOnlyAccess",
                },
            ),
        },
    )
    cloud = resolve_cloud_facts([model], [], config=Config())
    assert len(cloud.roles) == 1
    role = cloud.roles[0]
    assert role.arn == shared_arn
    # Both trust statements and both inline statements are preserved
    assert len(role.trust_statements) == 2
    inline_actions = {action for stmt in role.inline_statements for action in stmt.actions}
    assert {"s3:GetObject", "kms:Decrypt"} <= inline_actions
    # All managed policies from draft a, draft b, and attachment referencing aws_iam_role.b.name
    assert set(role.managed_policy_arns) == {
        "arn:aws:iam::aws:policy/ReadOnlyAccess",
        "arn:aws:iam::aws:policy/PowerUserAccess",
        "arn:aws:iam::aws:policy/IAMReadOnlyAccess",
    }
