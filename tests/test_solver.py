"""Trust solving and breadth classification (spec 10.3-10.6)."""

from __future__ import annotations

from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.models import Breadth, RoleFact, SubFormat, SubjectCandidate
from nhi_blast.oidc.solver import evaluate_trust
from tests.support import ASSUME_ACTION, candidate, role, statement

CLASSIC_TAGS = "repo:acme/shop:ref:refs/tags/v*"
IMMUTABLE_TAGS = "repo:acme@*/shop@*:ref:refs/tags/v*"
TAG_CLAIMS = {
    "repository": "acme/shop",
    "ref": "refs/tags/v*",
    "job_workflow_ref": "acme/shop/.github/workflows/release.yml@refs/tags/v*",
    "workflow": "Release",
}


def make_role(*conditions: dict) -> RoleFact:
    merged: dict = {}
    for mapping in conditions:
        merged.update(mapping)
    return role(statements=(statement(actions=(ASSUME_ACTION,), conditions=merged),))


def tag_candidates() -> tuple[SubjectCandidate, ...]:
    return (
        candidate(CLASSIC_TAGS, claims=TAG_CLAIMS),
        candidate(IMMUTABLE_TAGS, fmt=SubFormat.IMMUTABLE, claims=TAG_CLAIMS),
    )


def test_no_candidates_returns_none() -> None:
    assert evaluate_trust(make_role(), ()) is None


def test_unmatched_trust_returns_none() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:other/shop:ref:refs/tags/*"]}})
    assert evaluate_trust(trust, tag_candidates()) is None


def test_exact_ref_is_narrow() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:acme/shop:ref:refs/tags/v1"]}})
    result = evaluate_trust(
        trust,
        (candidate(CLASSIC_TAGS, claims=TAG_CLAIMS),),
        job_id="job:release.yml#publish",
    )
    assert result is not None
    assert result.job_id == "job:release.yml#publish"
    assert result.role_id == "aws:role:aws_iam_role.test"
    assert result.breadth is Breadth.EXACT_REF
    assert result.matched_formats == (SubFormat.CLASSIC,)
    assert not result.format_drift
    assert result.missing_audience
    assert result.confidence is EvidenceClass.DERIVED
    assert result.evidence


def test_org_wildcard_matches_classic_only_and_flags_format_drift() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:acme/*"]}})
    result = evaluate_trust(trust, tag_candidates())
    assert result is not None
    assert result.breadth is Breadth.SAME_ORG
    assert result.matched_formats == (SubFormat.CLASSIC,)
    assert result.format_drift
    assert [item.subject for item in result.matched_candidates] == [CLASSIC_TAGS]


def test_global_wildcard_matches_both_formats() -> None:
    trust = make_role({"StringLike": {"sub": ["*"]}})
    result = evaluate_trust(trust, tag_candidates())
    assert result is not None
    assert result.breadth is Breadth.ANY_ORG
    assert result.matched_formats == (SubFormat.CLASSIC, SubFormat.IMMUTABLE)
    assert not result.format_drift


def test_immutable_pattern_matches_only_immutable_format() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:acme@*/shop@*:ref:refs/tags/*"]}})
    result = evaluate_trust(trust, tag_candidates())
    assert result is not None
    assert result.matched_formats == (SubFormat.IMMUTABLE,)
    assert result.breadth is Breadth.REPO_ANY_BRANCH
    assert not result.format_drift


def test_repo_any_context_breadth() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:acme/shop:*"]}})
    result = evaluate_trust(trust, tag_candidates())
    assert result is not None
    assert result.breadth is Breadth.REPO_ANY_CONTEXT


def test_repo_any_branch_breadth() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:acme/shop:ref:refs/heads/*"]}})
    result = evaluate_trust(
        trust,
        (
            candidate(
                "repo:acme/shop:ref:refs/heads/main",
                claims={"repository": "acme/shop", "ref": "refs/heads/main"},
            ),
        ),
    )
    assert result is not None
    assert result.breadth is Breadth.REPO_ANY_BRANCH


def test_pull_request_breadth() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:acme/shop:pull_request"]}})
    result = evaluate_trust(
        trust,
        (candidate("repo:acme/shop:pull_request", trigger="pull_request"),),
    )
    assert result is not None
    assert result.breadth is Breadth.REPO_PULL_REQUEST


def test_environment_breadth() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:acme/shop:environment:prod"]}})
    result = evaluate_trust(
        trust,
        (
            candidate(
                "repo:acme/shop:environment:prod",
                claims={"repository": "acme/shop", "environment": "prod"},
            ),
        ),
    )
    assert result is not None
    assert result.breadth is Breadth.ENVIRONMENT


def test_unconstrained_trust() -> None:
    trust = make_role({"StringEquals": {"aud": ["sts.amazonaws.com"]}})
    result = evaluate_trust(trust, tag_candidates())
    assert result is not None
    assert result.breadth is Breadth.UNCONSTRAINED
    assert result.unconstrained
    assert result.additional_constraints == ()


def test_job_workflow_ref_control_is_honoured() -> None:
    trust = make_role(
        {"StringLike": {"job_workflow_ref": ["acme/shop/.github/workflows/*@refs/heads/*"]}}
    )
    result = evaluate_trust(
        trust,
        (
            candidate(
                "repo:acme/shop:ref:refs/heads/main",
                claims={
                    "job_workflow_ref": ("acme/shop/.github/workflows/release.yml@refs/heads/main")
                },
            ),
        ),
    )
    assert result is not None
    assert result.breadth is Breadth.REPO_ANY_BRANCH
    assert not result.unconstrained


def test_job_workflow_ref_breadth_levels() -> None:
    cases = {
        "*/*/.github/workflows/x.yml@refs/heads/main": Breadth.ANY_ORG,
        "acme/*/.github/workflows/x.yml@refs/heads/main": Breadth.SAME_ORG,
        "acme/shop/.github/workflows/x.yml*": Breadth.REPO_ANY_CONTEXT,
        "acme/shop/.github/workflows/x.yml@refs/heads/main": Breadth.EXACT_REF,
    }
    for pattern, expected in cases.items():
        trust = make_role({"StringLike": {"job_workflow_ref": [pattern]}})
        result = evaluate_trust(
            trust,
            (
                candidate(
                    "repo:acme/shop:ref:refs/heads/main",
                    claims={
                        "job_workflow_ref": ("acme/shop/.github/workflows/x.yml@refs/heads/main")
                    },
                ),
            ),
        )
        assert result is not None, pattern
        assert result.breadth is expected, pattern


def test_additional_constraint_makes_result_conditional() -> None:
    trust = make_role(
        {
            "StringLike": {
                "sub": [CLASSIC_TAGS],
                "actor": ["release-bot"],
            }
        }
    )
    result = evaluate_trust(trust, tag_candidates())
    assert result is not None
    assert result.confidence is EvidenceClass.ASSUMED
    assert result.additional_constraints == ("actor",)
    assert any("claim actor" in reason for reason in result.unresolved_reasons)


def test_unknown_candidate_marks_result_unknown() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:acme/*"]}})
    result = evaluate_trust(
        trust,
        (
            candidate(
                "repo:acme/shop:ref:refs/tags/v*",
                evidence_class=EvidenceClass.UNKNOWN,
            ),
        ),
    )
    assert result is not None
    assert result.confidence is EvidenceClass.UNKNOWN
    assert "candidate subject set is unresolved" in result.unresolved_reasons


def test_dead_condition_key_produces_no_match() -> None:
    trust = make_role(
        {
            "StringLike": {
                "sub": [CLASSIC_TAGS],
                "repository_owner": ["acme"],
            }
        }
    )
    assert evaluate_trust(trust, tag_candidates()) is None


def test_matched_candidates_are_sorted() -> None:
    trust = make_role({"StringLike": {"sub": ["repo:acme/*"]}})
    result = evaluate_trust(trust, tag_candidates())
    assert result is not None
    keys = [
        (item.subject, item.format.value, item.trigger, item.audience)
        for item in result.matched_candidates
    ]
    assert keys == sorted(keys)


def test_default_registry_is_loaded() -> None:
    trust = make_role({"StringLike": {"sub": [CLASSIC_TAGS]}})
    result = evaluate_trust(trust, tag_candidates())
    assert result is not None
