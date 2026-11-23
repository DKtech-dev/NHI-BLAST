"""Regression tests for Loop 8 Team A cross-module engine and parser seam fixes."""

from __future__ import annotations

import json

from nhi_blast.analysis.findings import build_findings
from nhi_blast.aws.conditions import ConditionMode, ConditionTruth, evaluate_conditions
from nhi_blast.aws.policy_eval import PolicyContext
from nhi_blast.aws.solver import (
    SolverStatus,
    StringPredicate,
    _project_env_from_sub,
    solve_correlated_oidc_predicates,
)
from nhi_blast.aws.trust import evaluate_trust_statements, is_github_oidc_statement
from nhi_blast.core.data import condition_keys
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import CredentialKind, NodeKind, PolicyEffect, SubFormat
from nhi_blast.discovery.repo import RepoIdentity
from nhi_blast.graph.builder import GraphInputs, build_graph
from nhi_blast.oidc.solver import evaluate_trust
from nhi_blast.parsers.gha.workflow import parse_workflow
from nhi_blast.parsers.iam.policy_doc import parse_policy_text
from nhi_blast.parsers.terraform.tfhcl import parse_tf_hcl
from nhi_blast.resolvers.composite import ExpandedJob, ExpandedStep
from nhi_blast.resolvers.roles import CloudFacts
from tests.support import ASSUME_ACTION, candidate, role, statement

REGISTRY = condition_keys()


# ---------------------------------------------------------------------- Seam 1
# ArnEquals / ArnNotEquals wildcards in CANDIDATE mode


def test_arn_equals_wildcards_in_candidate_mode() -> None:
    conditions = {
        "ArnEquals": {
            "aws:SourceArn": ("arn:aws:s3:::prod-bucket/*",),
        }
    }
    res = evaluate_conditions(
        conditions,
        {"aws:SourceArn": frozenset({"arn:aws:s3:::prod-bucket/reports/2026.csv"})},
        mode=ConditionMode.CANDIDATE,
    )
    assert res.truth is ConditionTruth.TRUE

    disjoint = evaluate_conditions(
        conditions,
        {"aws:SourceArn": frozenset({"arn:aws:s3:::other-bucket/*"})},
        mode=ConditionMode.CANDIDATE,
    )
    assert disjoint.truth is ConditionTruth.FALSE


def test_arn_equals_and_arn_not_equals_joint_candidate_unsat() -> None:
    conditions = {
        "ArnEquals": {"aws:SourceArn": ("arn:aws:s3:::prod-bucket/a/*",)},
        "ArnNotEquals": {"aws:SourceArn": ("arn:aws:s3:::prod-bucket/*",)},
    }
    res = evaluate_conditions(
        conditions,
        {"aws:SourceArn": frozenset({"arn:aws:s3:::prod-bucket/a/*"})},
        mode=ConditionMode.CANDIDATE,
    )
    assert res.truth is ConditionTruth.FALSE


def test_arn_equals_deny_covers_wildcard_candidate() -> None:
    allow = statement(
        actions=(ASSUME_ACTION,),
        conditions={"StringLike": {"token.actions.githubusercontent.com:sub": ("repo:acme/*",)}},
    )
    deny = statement(
        effect=PolicyEffect.DENY,
        actions=(ASSUME_ACTION,),
        conditions={"ArnEquals": {"aws:PrincipalArn": ("arn:aws:iam::111122223333:role/*",)}},
    )
    r = role(statements=(allow, deny))
    cand = candidate(
        "repo:acme/app:ref:refs/heads/main",
        claims={"aws:PrincipalArn": "arn:aws:iam::111122223333:role/ci-*"},
    )
    evaluation = evaluate_trust_statements(r, (cand,), registry=REGISTRY)
    assert evaluation.matches == ()


# ---------------------------------------------------------------------- Seam 2
# Disjunctive OIDC candidate matches keep strongest confidence & evidence


def test_disjunctive_oidc_match_does_not_downgrade_derived_to_unknown() -> None:
    trust_role = role(
        statements=(
            statement(
                actions=(ASSUME_ACTION,),
                conditions={
                    "StringLike": {"token.actions.githubusercontent.com:sub": ("repo:acme/app:*",)},
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": ("sts.amazonaws.com",)
                    },
                },
            ),
        )
    )
    push_cand = candidate(
        "repo:acme/app:ref:refs/heads/main",
        trigger="push",
        evidence_class=EvidenceClass.DERIVED,
    )
    wf_call_cand = candidate(
        "repo:acme/app:*",
        trigger="workflow_call",
        evidence_class=EvidenceClass.UNKNOWN,
    )

    evaluation = evaluate_trust_statements(trust_role, (push_cand, wf_call_cand), registry=REGISTRY)
    assert len(evaluation.matches) == 2
    assert evaluation.confidence is EvidenceClass.DERIVED

    match = evaluate_trust(
        trust_role, (push_cand, wf_call_cand), job_id="deploy", registry=REGISTRY
    )
    assert match is not None
    assert match.confidence is EvidenceClass.DERIVED
    assert all(ev.cls is not EvidenceClass.UNKNOWN for ev in match.evidence)


def test_only_unknown_candidate_remains_unknown() -> None:
    trust_role = role(
        statements=(
            statement(
                actions=(ASSUME_ACTION,),
                conditions={
                    "StringLike": {"token.actions.githubusercontent.com:sub": ("repo:acme/app:*",)},
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": ("sts.amazonaws.com",)
                    },
                },
            ),
        )
    )
    wf_call_cand = candidate(
        "repo:acme/app:*",
        trigger="workflow_call",
        evidence_class=EvidenceClass.UNKNOWN,
    )
    match = evaluate_trust(trust_role, (wf_call_cand,), job_id="deploy", registry=REGISTRY)
    assert match is not None
    assert match.confidence is EvidenceClass.UNKNOWN


# ---------------------------------------------------------------------- Seam 3
# %3A-escaped sub vs unescaped environment claim in aws/solver.py


def test_project_env_from_sub_unquotes_percent_encoded_colon() -> None:
    assert _project_env_from_sub("repo:acme/app:environment:Production%3AV1") == "Production:V1"

    sat = solve_correlated_oidc_predicates(
        {
            "sub": [
                StringPredicate(
                    label="sub",
                    patterns=("repo:acme/app:environment:Production%3AV1",),
                    is_glob=False,
                )
            ],
            "environment": [
                StringPredicate(
                    label="env",
                    patterns=("Production:V1",),
                    is_glob=False,
                )
            ],
        }
    )
    assert sat.status is SolverStatus.SAT
    assert sat.witnesses["environment"] == "Production:V1"

    unsat = solve_correlated_oidc_predicates(
        {
            "sub": [
                StringPredicate(
                    label="sub",
                    patterns=("repo:acme/app:environment:Production%3AV1",),
                    is_glob=False,
                )
            ],
            "environment": [
                StringPredicate(
                    label="env",
                    patterns=("Staging:V1",),
                    is_glob=False,
                )
            ],
        }
    )
    assert unsat.status is SolverStatus.UNSAT


# ---------------------------------------------------------------------- Seam 4
# Policy-wide OIDC trust audit in IaC-only repos


def test_iac_only_repo_audits_wide_open_oidc_trust_policies() -> None:
    wide_open_role = role(
        address="aws_iam_role.open_oidc",
        name="open-oidc",
        arn="arn:aws:iam::111122223333:role/open-oidc",
        statements=(
            statement(
                actions=(ASSUME_ACTION,),
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:repository_owner": ("acme",),
                    }
                },
            ),
        ),
    )
    build = build_graph(
        GraphInputs(
            repository=RepoIdentity(
                slug="acme/iac-only",
                source="nhi-blast.toml",
                default_branch="main",
                sub_format=SubFormat.CLASSIC,
            ),
            workflows=(),
            expanded_jobs=(),
            cloud=CloudFacts(
                roles=(wide_open_role,),
                sinks=(),
                providers=(),
                externals=(),
                policy_context=PolicyContext(),
                diagnostics=(),
            ),
        )
    )
    role_nodes = [n for n in build.graph.nodes if n.kind is NodeKind.AWS_ROLE]
    assert len(role_nodes) == 1
    assert role_nodes[0].attrs["trust_policy_audit"]

    findings = build_findings(build.graph).findings
    rules = {f.rule for f in findings}
    assert "NHB-OIDC-001" in rules
    assert "NHB-OIDC-004" in rules
    assert "NHB-OIDC-006" in rules


# ---------------------------------------------------------------------- Seam 5
# IAM "Principal": "*" scalar string


def test_iam_policy_doc_scalar_wildcard_principal() -> None:
    doc = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": "*",
                    "Action": "sts:AssumeRoleWithWebIdentity",
                }
            ],
        }
    )
    statements, diagnostics = parse_policy_text(doc, file="trust.json", rule="IAM.trust")
    assert diagnostics == ()
    assert len(statements) == 1
    assert statements[0].principals == {"*": ("*",)}
    assert is_github_oidc_statement(statements[0], REGISTRY.provider_host)


# ---------------------------------------------------------------------- Seam 6
# GHA jobs.<id>.secrets: mapping & top-level workflow env: scanning


def test_gha_job_secrets_mapping_and_workflow_env_scanned() -> None:
    workflow_text = """\
name: Deploy
on: push
env:
  TOP_KEY: AKIAIOSFODNN7EXAMPLE
  TOP_REF: ${{ secrets.WORKFLOW_ENV_SECRET }}
jobs:
  call-reusable:
    uses: ./.github/workflows/reusable.yml
    secrets:
      DEPLOY_TOKEN: ${{ secrets.JOB_EXPLICIT_SECRET }}
      HARDCODED: ghp_1234567890abcdefghijklmnopqrstuvwxyz
"""
    parsed = parse_workflow(".github/workflows/deploy.yml", workflow_text, limits=Limits())
    assert parsed.facts is not None
    job = parsed.facts.jobs["call-reusable"]
    assert job.secrets_mode == "EXPLICIT"
    assert "JOB_EXPLICIT_SECRET" in job.refs.secrets
    assert "WORKFLOW_ENV_SECRET" in job.refs.secrets
    literal_kinds = {hit.kind for hit in job.literals}
    assert CredentialKind.AWS_ACCESS_KEY in literal_kinds
    assert CredentialKind.GITHUB_TOKEN in literal_kinds

    expanded = (
        ExpandedJob(
            workflow=parsed.facts,
            job=job,
            refs=job.refs,
            steps=tuple(ExpandedStep(step=s) for s in job.steps),
            diagnostics=(),
        ),
    )
    build = build_graph(
        GraphInputs(
            repository=RepoIdentity(
                slug="acme/app",
                source="nhi-blast.toml",
                default_branch="main",
                sub_format=SubFormat.CLASSIC,
            ),
            workflows=(parsed.facts,),
            expanded_jobs=expanded,
            cloud=CloudFacts(
                roles=(),
                sinks=(),
                providers=(),
                externals=(),
                policy_context=PolicyContext(),
                diagnostics=(),
            ),
        )
    )
    findings = build_findings(build.graph).findings
    assert any(f.rule == "NHB-GHA-005" for f in findings)


# ---------------------------------------------------------------------- Seam 7
# tfhcl.py scalar string identifiers not split character-by-character


def test_tfhcl_scalar_string_identifiers_not_split() -> None:
    tf_text = """\
data "aws_iam_policy_document" "trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = "arn:aws:iam::111122223333:root"
    }
  }
}
"""
    parsed = parse_tf_hcl("trust.tf", tf_text, limits=Limits())
    assert parsed.facts is not None
    assert "data.aws_iam_policy_document.trust" in parsed.facts.policy_documents
    raw_json = parsed.facts.policy_documents["data.aws_iam_policy_document.trust"].json_text
    assert raw_json is not None
    doc = json.loads(raw_json)
    assert doc["Statement"][0]["Principal"] == {"AWS": ["arn:aws:iam::111122223333:root"]}
