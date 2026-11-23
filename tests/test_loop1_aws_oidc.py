"""Comprehensive tests for Loop 1 AWS IAM, Solver, OIDC, and Terraform fixes."""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest

from nhi_blast.aws.conditions import (
    ConditionMode,
    ConditionTruth,
    evaluate_conditions,
)
from nhi_blast.aws.sinks import kms_key_arn
from nhi_blast.aws.solver import (
    SolverStatus,
    StringPredicate,
    solve_correlated_oidc_predicates,
)
from nhi_blast.aws.trust import (
    evaluate_trust_statements,
    is_github_oidc_statement,
)
from nhi_blast.core.data import condition_keys
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    Breadth,
    PolicyEffect,
    SinkFact,
    SinkType,
    SubFormat,
)
from nhi_blast.oidc.breadth import classify_breadth
from nhi_blast.oidc.github_subject import subject_candidates
from nhi_blast.parsers.gha.facts import Trigger
from nhi_blast.parsers.iam.policy_doc import parse_iam_document
from nhi_blast.parsers.terraform.tfjson import parse_tf_json
from tests.support import ASSUME_ACTION, candidate, job, role, statement, workflow

REGISTRY = condition_keys()


# --------------------------------------------------------------- 1. conditions.py


def test_exact_operators_treat_wildcards_literally_in_candidate_mode() -> None:
    # Policy has literal '*' in StringEquals: must NOT match concrete ref in CANDIDATE mode.
    res_eq = evaluate_conditions(
        {"StringEquals": {"sub": ("repo:acme/shop:*",)}},
        {"sub": frozenset({"repo:acme/shop:ref:refs/heads/main"})},
        mode=ConditionMode.CANDIDATE,
    )
    assert res_eq.truth is ConditionTruth.FALSE

    # StringEqualsIgnoreCase also treats '*'/'?' literally while folding case.
    res_fold_nomatch = evaluate_conditions(
        {"StringEqualsIgnoreCase": {"sub": ("REPO:ACME/SHOP:*",)}},
        {"sub": frozenset({"repo:acme/shop:ref:refs/heads/main"})},
        mode=ConditionMode.CANDIDATE,
    )
    assert res_fold_nomatch.truth is ConditionTruth.FALSE

    res_fold_match = evaluate_conditions(
        {"StringEqualsIgnoreCase": {"sub": ("REPO:ACME/SHOP:REF:REFS/HEADS/MAIN",)}},
        {"sub": frozenset({"repo:acme/shop:ref:refs/heads/*"})},
        mode=ConditionMode.CANDIDATE,
    )
    assert res_fold_match.truth is ConditionTruth.TRUE

    # Per AWS IAM & SPEC.md, ArnEquals matches wildcards (same as ArnLike) in CANDIDATE mode.
    res_arn_eq = evaluate_conditions(
        {"ArnEquals": {"aws:SourceArn": ("arn:aws:s3:::bucket/*",)}},
        {"aws:SourceArn": frozenset({"arn:aws:s3:::bucket/key"})},
        mode=ConditionMode.CANDIDATE,
    )
    assert res_arn_eq.truth is ConditionTruth.TRUE

    # StringLike still treats '*' as wildcard in CANDIDATE mode.
    res_like = evaluate_conditions(
        {"StringLike": {"sub": ("repo:acme/shop:*",)}},
        {"sub": frozenset({"repo:acme/shop:ref:refs/heads/main"})},
        mode=ConditionMode.CANDIDATE,
    )
    assert res_like.truth is ConditionTruth.TRUE


def test_joint_solver_respects_literal_exact_operators_in_candidate_mode() -> None:
    # Conjunctive StringEquals with literal '?' vs StringEquals with a different literal
    # against a wildcard candidate must be UNSAT (not treated as glob intersection).
    res = evaluate_conditions(
        {
            "StringEquals": {"sub": ("repo:acme/shop:ref:refs/heads/a?",)},
            "StringEqualsIgnoreCase": {"sub": ("repo:acme/shop:ref:refs/heads/ab",)},
        },
        {"sub": frozenset({"repo:acme/shop:ref:refs/heads/*"})},
        mode=ConditionMode.CANDIDATE,
    )
    assert res.truth is ConditionTruth.FALSE


def test_condition_keys_are_case_insensitive_while_preserving_diagnostics() -> None:
    res = evaluate_conditions(
        {
            "StringEquals": {
                "Sub": ("repo:acme/shop:ref:refs/heads/main",),
                "AUD": ("sts.amazonaws.com",),
            }
        },
        {
            "sub": frozenset({"repo:acme/shop:ref:refs/heads/main"}),
            "aud": frozenset({"sts.amazonaws.com"}),
        },
        mode=ConditionMode.CANDIDATE,
        supported_keys=frozenset({"sub", "aud"}),
    )
    assert res.truth is ConditionTruth.TRUE
    assert res.dead_keys == ()
    assert any("Sub" in reason for reason in res.reasons)
    assert any("AUD" in reason for reason in res.reasons)

    # Unsupported key preserves original case in dead_keys.
    dead_res = evaluate_conditions(
        {"StringEquals": {"Repository_Owner": ("acme",)}},
        {"repository_owner": frozenset({"acme"})},
        mode=ConditionMode.CANDIDATE,
        supported_keys=frozenset({"sub"}),
    )
    assert dead_res.truth is ConditionTruth.FALSE
    assert dead_res.dead_keys == ("Repository_Owner",)


# --------------------------------------------------------------- 2. solver.py


def test_solver_projects_repository_and_owner_from_sub_and_jwr() -> None:
    # sub implies org-a/app (owner org-a), contradicting repository_owner=org-b.
    unsat_owner = solve_correlated_oidc_predicates(
        {
            "sub": (
                StringPredicate(
                    label="sub",
                    patterns=("repo:org-a/app:ref:refs/heads/main",),
                    is_glob=False,
                ),
            ),
            "repository_owner": (
                StringPredicate(label="owner", patterns=("org-b",), is_glob=False),
            ),
        }
    )
    assert unsat_owner.status is SolverStatus.UNSAT

    # sub implies org-a/app, contradicting repository=org-a/other.
    unsat_repo = solve_correlated_oidc_predicates(
        {
            "sub": (
                StringPredicate(
                    label="sub",
                    patterns=("repo:org-a@123/app@456:ref:refs/heads/main",),
                    is_glob=False,
                ),
            ),
            "repository": (
                StringPredicate(label="repo", patterns=("org-a/other",), is_glob=False),
            ),
        }
    )
    assert unsat_repo.status is SolverStatus.UNSAT

    # Cross-repo reusable job_workflow_ref (org-a/app) is SAT with repository_owner=org-b.
    unsat_jwr = solve_correlated_oidc_predicates(
        {
            "job_workflow_ref": (
                StringPredicate(
                    label="jwr",
                    patterns=("org-a/app/.github/workflows/deploy.yml@refs/heads/main",),
                    is_glob=False,
                ),
            ),
            "repository_owner": (
                StringPredicate(label="owner", patterns=("org-b",), is_glob=False),
            ),
        }
    )
    assert unsat_jwr.status is SolverStatus.SAT

    # Consistent sub + repository_owner + job_workflow_ref is SAT.
    sat = solve_correlated_oidc_predicates(
        {
            "sub": (
                StringPredicate(
                    label="sub",
                    patterns=("repo:org-a/app:ref:refs/heads/main",),
                    is_glob=False,
                ),
            ),
            "repository_owner": (
                StringPredicate(label="owner", patterns=("org-a",), is_glob=False),
            ),
            "job_workflow_ref": (
                StringPredicate(
                    label="jwr",
                    patterns=("org-a/app/.github/workflows/deploy.yml@refs/heads/main",),
                    is_glob=False,
                ),
            ),
        }
    )
    assert sat.status is SolverStatus.SAT
    assert sat.witnesses["repository"] == "org-a/app"
    assert sat.witnesses["repository_owner"] == "org-a"


# --------------------------------------------------------------- 3. trust.py


def test_trust_partial_deny_on_wildcard_candidate_is_conditional_not_suppressed() -> None:
    allow = statement(
        actions=(ASSUME_ACTION,),
        conditions={"StringLike": {"token.actions.githubusercontent.com:sub": ("repo:org/app:*",)}},
    )
    deny_main_only = statement(
        effect=PolicyEffect.DENY,
        actions=(ASSUME_ACTION,),
        conditions={
            "StringEquals": {
                "token.actions.githubusercontent.com:sub": ("repo:org/app:ref:refs/heads/main",)
            }
        },
    )
    trust_role = role(statements=(allow, deny_main_only))
    wildcard_cand = candidate("repo:org/app:ref:refs/heads/*")

    res = evaluate_trust_statements(trust_role, (wildcard_cand,), registry=REGISTRY)
    assert len(res.matches) == 1
    assert res.matches[0].conditional is True
    assert res.matches[0].truth is ConditionTruth.UNRESOLVED


def test_trust_full_coverage_deny_on_wildcard_candidate_still_suppresses() -> None:
    allow = statement(
        actions=(ASSUME_ACTION,),
        conditions={"StringLike": {"token.actions.githubusercontent.com:sub": ("repo:org/*",)}},
    )
    deny_all_app = statement(
        effect=PolicyEffect.DENY,
        actions=(ASSUME_ACTION,),
        conditions={"StringLike": {"token.actions.githubusercontent.com:sub": ("repo:org/app:*",)}},
    )
    trust_role = role(statements=(allow, deny_all_app))
    wildcard_cand = candidate("repo:org/app:ref:refs/heads/*")

    res = evaluate_trust_statements(trust_role, (wildcard_cand,), registry=REGISTRY)
    assert res.matches == ()


def test_is_github_oidc_statement_allows_wildcard_federated_and_star_principal() -> None:
    star_fed = statement(principals={"Federated": ("*",)}, actions=(ASSUME_ACTION,))
    star_all = statement(principals={"*": ("*",)}, actions=(ASSUME_ACTION,))
    other_fed = statement(
        principals={"Federated": ("arn:aws:iam::123:oidc-provider/other.example.com",)},
        actions=(ASSUME_ACTION,),
    )
    assert is_github_oidc_statement(star_fed, REGISTRY.provider_host)
    assert is_github_oidc_statement(star_all, REGISTRY.provider_host)
    assert not is_github_oidc_statement(other_fed, REGISTRY.provider_host)


def test_trust_normalise_statement_strips_provider_host_case_insensitively() -> None:
    upper_host = REGISTRY.provider_host.upper()
    stmt = statement(
        actions=(ASSUME_ACTION,),
        conditions={
            "StringEquals": {
                f"{upper_host}:sub": ("repo:acme/shop:ref:refs/heads/main",),
                f"{upper_host}:aud": ("sts.amazonaws.com",),
            }
        },
    )
    res = evaluate_trust_statements(
        role(statements=(stmt,)),
        (candidate("repo:acme/shop:ref:refs/heads/main"),),
        registry=REGISTRY,
    )
    assert len(res.matches) == 1
    assert not res.missing_audience
    assert not res.unconstrained
    assert res.dead_keys == ()


# --------------------------------------------------------------- 4. sinks.py


def test_kms_key_arn_handles_alias_without_key_prefix() -> None:
    sink_alias = SinkFact(
        id="sink:sm:app",
        sink_type=SinkType.SECRETSMANAGER_SECRET,
        name="app",
        kms_key_id="alias/custom-app-key",
    )
    assert (
        kms_key_arn(sink_alias, region="us-east-1", account="111122223333")
        == "arn:aws:kms:us-east-1:111122223333:alias/custom-app-key"
    )

    sink_uuid = SinkFact(
        id="sink:sm:app2",
        sink_type=SinkType.SECRETSMANAGER_SECRET,
        name="app2",
        kms_key_id="1234abcd-12ab-34cd-56ef-1234567890ab",
    )
    assert (
        kms_key_arn(sink_uuid, region="us-east-1", account="111122223333")
        == "arn:aws:kms:us-east-1:111122223333:key/1234abcd-12ab-34cd-56ef-1234567890ab"
    )


# --------------------------------------------------------------- 5. breadth.py


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("repo:acme/shop:environment:production", Breadth.ENVIRONMENT),
        ("repo:acme/shop:environment:*", Breadth.REPO_ANY_CONTEXT),
        ("repo:acme/shop:environment:prod-*", Breadth.REPO_ANY_CONTEXT),
        ("repo:acme/shop:environment:prod?", Breadth.REPO_ANY_CONTEXT),
        ("repo:acme/shop:environment:", Breadth.REPO_ANY_CONTEXT),
    ],
)
def test_classify_breadth_wildcard_or_empty_environment(pattern: str, expected: Breadth) -> None:
    assert classify_breadth(pattern) is expected


# --------------------------------------------------------------- 6. github_subject.py


def test_pull_request_target_emits_all_branches_and_populates_claims() -> None:
    cands = subject_candidates(
        job(),
        workflow(
            triggers=(Trigger(event="pull_request_target", branches=("main", "release/*"), line=4),)
        ),
        repo_slug="acme/shop",
    )
    classic = {c.subject for c in cands if c.format is SubFormat.CLASSIC}
    assert classic == {
        "repo:acme/shop:ref:refs/heads/main",
        "repo:acme/shop:ref:refs/heads/release/*",
    }
    for item in cands:
        assert item.claims["repository_owner"] == "acme"
        assert item.claims["event_name"] == "pull_request_target"


def test_environment_candidate_populates_owner_event_and_job_workflow_ref() -> None:
    cands = subject_candidates(
        job(environment="prod"),
        workflow(triggers=(Trigger(event="push", branches=("main",), line=2),)),
        repo_slug="acme/shop",
    )
    classic = next(c for c in cands if c.format is SubFormat.CLASSIC)
    assert classic.claims["repository"] == "acme/shop"
    assert classic.claims["repository_owner"] == "acme"
    assert classic.claims["event_name"] == "push"
    assert classic.claims["environment"] == "prod"
    assert classic.claims["job_workflow_ref"] == "acme/shop/.github/workflows/release.yml@*"


# --------------------------------------------------------------- 7. policy_doc.py


def test_parse_iam_document_unwraps_policy_document_and_policy_version() -> None:
    inner = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": "*",
            }
        ],
    }

    # aws iam get-role-policy (dict)
    get_role_policy_dict = json.dumps(
        {
            "RoleName": "deploy-role",
            "PolicyName": "inline-read",
            "PolicyDocument": inner,
        }
    )
    fact1, diags1 = parse_iam_document(get_role_policy_dict, label="role-policy.json")
    assert fact1 is not None
    assert not diags1
    assert fact1.role_name == "deploy-role"
    assert len(fact1.statements) == 1
    assert fact1.statements[0].actions == ("secretsmanager:GetSecretValue",)

    # aws iam get-role-policy (URL-encoded JSON string)
    get_role_policy_encoded = json.dumps(
        {
            "RoleName": "deploy-role",
            "PolicyName": "inline-read",
            "PolicyDocument": quote(json.dumps(inner)),
        }
    )
    fact2, diags2 = parse_iam_document(get_role_policy_encoded, label="role-policy-enc.json")
    assert fact2 is not None
    assert not diags2
    assert len(fact2.statements) == 1
    assert fact2.statements[0].actions == ("secretsmanager:GetSecretValue",)

    # aws iam get-policy-version (dict and URL-encoded string)
    for doc_val in (inner, quote(json.dumps(inner))):
        pv_text = json.dumps(
            {
                "PolicyVersion": {
                    "Document": doc_val,
                    "VersionId": "v1",
                    "IsDefaultVersion": True,
                }
            }
        )
        fact3, diags3 = parse_iam_document(pv_text, label="policy-version.json")
        assert fact3 is not None
        assert not diags3
        assert len(fact3.statements) == 1
        assert fact3.statements[0].actions == ("secretsmanager:GetSecretValue",)


# --------------------------------------------------------------- 8. tfjson.py


def test_tfjson_does_not_resurrect_deleted_prior_state_resources() -> None:
    payload = {
        "format_version": "1.2",
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_iam_role.kept",
                        "mode": "managed",
                        "type": "aws_iam_role",
                        "name": "kept",
                        "values": {"name": "kept"},
                    }
                ]
            }
        },
        "prior_state": {
            "values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_iam_role.deleted_role",
                            "mode": "managed",
                            "type": "aws_iam_role",
                            "name": "deleted_role",
                            "values": {"name": "deleted_role"},
                        },
                        {
                            "address": "aws_iam_role.unchanged_prior",
                            "mode": "managed",
                            "type": "aws_iam_role",
                            "name": "unchanged_prior",
                            "values": {"name": "unchanged_prior"},
                        },
                    ]
                }
            }
        },
        "resource_changes": [
            {
                "address": "aws_iam_role.deleted_role",
                "change": {
                    "actions": ["delete"],
                    "before": {"name": "deleted_role"},
                    "after": None,
                },
            },
            {
                "address": "aws_iam_role.unchanged_prior",
                "change": {"actions": ["no-op"], "before": {"name": "unchanged_prior"}},
            },
        ],
    }
    parsed = parse_tf_json("plan.json", json.dumps(payload), limits=Limits())
    assert parsed.facts is not None
    assert "aws_iam_role.kept" in parsed.facts.resources
    assert "aws_iam_role.unchanged_prior" in parsed.facts.resources
    assert "aws_iam_role.deleted_role" not in parsed.facts.resources


def test_tfjson_collects_module_calls_expression_references() -> None:
    payload = {
        "format_version": "1.2",
        "planned_values": {
            "root_module": {
                "child_modules": [
                    {
                        "address": "module.iam",
                        "resources": [
                            {
                                "address": "module.iam.aws_iam_role.deployer",
                                "mode": "managed",
                                "type": "aws_iam_role",
                                "name": "deployer",
                                "values": {"name": "deployer"},
                            }
                        ],
                    }
                ]
            }
        },
        "configuration": {
            "root_module": {
                "module_calls": {
                    "iam": {
                        "module": {
                            "resources": [
                                {
                                    "address": "aws_iam_role.deployer",
                                    "expressions": {
                                        "assume_role_policy": {
                                            "references": [
                                                "data.aws_iam_policy_document.trust.json"
                                            ]
                                        }
                                    },
                                }
                            ]
                        }
                    }
                }
            }
        },
    }
    parsed = parse_tf_json("plan.json", json.dumps(payload), limits=Limits())
    assert parsed.facts is not None
    role_res = parsed.facts.resources["module.iam.aws_iam_role.deployer"]
    assert role_res.references["assume_role_policy"] == ("data.aws_iam_policy_document.trust.json",)
