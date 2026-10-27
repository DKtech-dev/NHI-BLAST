"""AWS trust-policy evaluation against OIDC candidates (spec 10.3)."""

from __future__ import annotations

from nhi_blast.aws.conditions import ConditionTruth
from nhi_blast.aws.trust import evaluate_trust_statements, is_github_oidc_statement
from nhi_blast.core.data import condition_keys
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.models import PolicyEffect
from tests.support import ASSUME_ACTION, candidate, role, statement

REGISTRY = condition_keys()
SUB_MAIN = "repo:acme/shop:ref:refs/heads/main"
SUB_TAGS = "repo:acme/shop:ref:refs/tags/v*"


def trusted_role(*conditions: dict, sub: str | None = None):
    condition_map: dict = {}
    if sub is not None:
        condition_map["StringLike"] = {"sub": [sub]}
    for mapping in conditions:
        condition_map.update(mapping)
    return role(
        statements=(
            statement(
                actions=(ASSUME_ACTION,),
                conditions=condition_map,
            ),
        )
    )


def test_is_github_oidc_statement() -> None:
    stmt = statement()
    assert is_github_oidc_statement(stmt, REGISTRY.provider_host)
    assert not is_github_oidc_statement(
        statement(principals={"Federated": ("arn:aws:iam::1:oidc-provider/evil.example.com",)}),
        REGISTRY.provider_host,
    )
    assert not is_github_oidc_statement(
        statement(actions=("sts:AssumeRole",)), REGISTRY.provider_host
    )
    assert not is_github_oidc_statement(statement(effect=PolicyEffect.DENY), REGISTRY.provider_host)


def test_matching_tag_pattern_is_declared_from_conditions() -> None:
    evaluation = evaluate_trust_statements(
        trusted_role(sub=SUB_TAGS),
        [candidate("repo:acme/shop:ref:refs/tags/v1.2.3")],
        registry=REGISTRY,
    )
    assert len(evaluation.matches) == 1
    match = evaluation.matches[0]
    assert match.truth is ConditionTruth.TRUE
    assert not match.conditional
    assert evaluation.sub_patterns == (SUB_TAGS,)
    assert evaluation.missing_audience
    assert not evaluation.unconstrained
    assert evaluation.confidence is EvidenceClass.DERIVED


def test_provider_host_prefix_is_stripped_from_keys() -> None:
    conditions = {
        "StringEquals": {
            f"{REGISTRY.provider_host}:sub": [SUB_MAIN],
            f"{REGISTRY.provider_host}:aud": ["sts.amazonaws.com"],
        }
    }
    evaluation = evaluate_trust_statements(
        trusted_role(conditions),
        [candidate(SUB_MAIN)],
        registry=REGISTRY,
    )
    assert len(evaluation.matches) == 1
    assert not evaluation.missing_audience


def test_audience_mismatch_means_no_match() -> None:
    conditions = {
        "StringEquals": {
            "aud": ["api://custom"],
            "sub": [SUB_MAIN],
        }
    }
    evaluation = evaluate_trust_statements(
        trusted_role(conditions),
        [candidate(SUB_MAIN, audience="sts.amazonaws.com")],
        registry=REGISTRY,
    )
    assert evaluation.matches == ()


def test_non_matching_subject_means_no_match() -> None:
    evaluation = evaluate_trust_statements(
        trusted_role(sub="repo:other/shop:ref:refs/heads/main"),
        [candidate(SUB_MAIN)],
        registry=REGISTRY,
    )
    assert evaluation.matches == ()


def test_dead_condition_key_fails_closed() -> None:
    conditions = {
        "StringEquals": {
            "sub": [SUB_MAIN],
            "repository_owner": ["acme"],
        }
    }
    evaluation = evaluate_trust_statements(
        trusted_role(conditions),
        [candidate(SUB_MAIN, claims={"repository": "acme/shop", "repository_owner": "acme"})],
        registry=REGISTRY,
    )
    assert evaluation.matches == ()
    assert evaluation.dead_keys == ("repository_owner",)


def test_unconstrained_when_no_control_claim_is_conditioned() -> None:
    conditions = {"StringEquals": {"aud": ["sts.amazonaws.com"]}}
    evaluation = evaluate_trust_statements(
        trusted_role(conditions),
        [candidate(SUB_MAIN)],
        registry=REGISTRY,
    )
    assert len(evaluation.matches) == 1
    assert evaluation.unconstrained
    assert evaluation.sub_patterns == ()


def test_non_statically_fixable_claim_is_conditional() -> None:
    conditions = {
        "StringLike": {
            "sub": [SUB_TAGS],
            "actor": ["release-bot"],
        }
    }
    evaluation = evaluate_trust_statements(
        trusted_role(conditions),
        [candidate("repo:acme/shop:ref:refs/tags/v1")],
        registry=REGISTRY,
    )
    assert len(evaluation.matches) == 1
    match = evaluation.matches[0]
    assert match.truth is ConditionTruth.UNRESOLVED
    assert match.conditional
    assert match.unresolved_keys == ("actor",)
    assert evaluation.additional_constraints == ("actor",)
    assert evaluation.confidence is EvidenceClass.ASSUMED


def test_missing_supported_claim_is_unresolved() -> None:
    conditions = {
        "StringLike": {
            "sub": [SUB_TAGS],
            "environment": ["prod"],
        }
    }
    evaluation = evaluate_trust_statements(
        trusted_role(conditions),
        [candidate("repo:acme/shop:ref:refs/tags/v1")],
        registry=REGISTRY,
    )
    assert len(evaluation.matches) == 1
    assert evaluation.matches[0].truth is ConditionTruth.UNRESOLVED


def test_unknown_candidate_weakens_confidence() -> None:
    evaluation = evaluate_trust_statements(
        trusted_role(sub="repo:acme/*"),
        [candidate(SUB_MAIN, evidence_class=EvidenceClass.UNKNOWN)],
        registry=REGISTRY,
    )
    assert len(evaluation.matches) == 1
    assert evaluation.confidence is EvidenceClass.UNKNOWN


def test_only_one_of_several_candidates_may_match() -> None:
    evaluation = evaluate_trust_statements(
        trusted_role(sub=SUB_MAIN),
        [
            candidate(SUB_MAIN),
            candidate("repo:acme/shop:ref:refs/heads/dev"),
        ],
        registry=REGISTRY,
    )
    assert len(evaluation.matches) == 1
    assert evaluation.matches[0].candidate.subject == SUB_MAIN


def test_job_workflow_ref_patterns_are_extracted() -> None:
    conditions = {
        "StringLike": {
            "job_workflow_ref": ["acme/shop/.github/workflows/*@refs/heads/main"],
        }
    }
    evaluation = evaluate_trust_statements(
        trusted_role(conditions),
        [
            candidate(
                SUB_MAIN,
                claims={"job_workflow_ref": ("acme/shop/.github/workflows/ci.yml@refs/heads/main")},
            )
        ],
        registry=REGISTRY,
    )
    assert evaluation.job_workflow_ref_patterns == (
        "acme/shop/.github/workflows/*@refs/heads/main",
    )
    assert len(evaluation.matches) == 1


def test_no_relevant_statement_returns_empty_evaluation() -> None:
    evaluation = evaluate_trust_statements(
        role(statements=(statement(actions=("sts:AssumeRole",)),)),
        [candidate(SUB_MAIN)],
        registry=REGISTRY,
    )
    assert evaluation.matches == ()
    assert evaluation.sub_patterns == ()
    assert evaluation.confidence is EvidenceClass.DERIVED
