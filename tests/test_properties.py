"""Properties for conservative filters, selector parsing, identifiers and conditions."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nhi_blast.analysis.selectors import SelectorError, SelectorKind, parse_selector
from nhi_blast.aws.conditions import ConditionMode, ConditionTruth, evaluate_conditions
from nhi_blast.aws.glob import glob_match
from nhi_blast.aws.policy_eval import action_filter, evaluate_action
from nhi_blast.aws.trust import (
    ASSUME_ACTION,
    evaluate_trust_statements,
    trust_subject_filter,
)
from nhi_blast.core.data import condition_keys
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.ids import (
    action_node_id,
    credential_node_id,
    digest_pairs,
    edge_id,
    file_sha256,
    finding_id,
    job_node_id,
    local_action_node_id,
    role_node_id,
    sink_node_id,
    workflow_node_id,
)
from nhi_blast.core.models import (
    Decision,
    PolicyContext,
    PolicyEffect,
    RoleFact,
    Statement,
    SubFormat,
    SubjectCandidate,
)

ACTION = "s3:GetObject"
ACCOUNT = "111122223333"
REGION = "us-east-1"
PROVIDER_HOST = condition_keys().provider_host
FEDERATED_PRINCIPAL = f"arn:aws:iam::{ACCOUNT}:oidc-provider/{PROVIDER_HOST}"

PATTERN = st.text(alphabet="abAB:/*?", max_size=10)
CANDIDATE = st.text(alphabet="abAB:/*?", max_size=12)
SEGMENT = st.text(alphabet="abcXYZ019._-", min_size=1, max_size=10)
OWNER = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9_-]{0,7}", fullmatch=True)
REPO = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,7}", fullmatch=True)
REF = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9._-]{0,9}", fullmatch=True)


def _role_with_allow(pattern: str) -> RoleFact:
    statement = Statement(
        effect=PolicyEffect.ALLOW,
        actions=(ACTION,),
        resources=(pattern,),
    )
    return RoleFact(
        id="role:test",
        address="aws_iam_role.test",
        name="test",
        inline_statements=(statement,),
    )


def _trust_role(pattern: str) -> RoleFact:
    statement = Statement(
        effect=PolicyEffect.ALLOW,
        actions=(ASSUME_ACTION,),
        principals={"Federated": (FEDERATED_PRINCIPAL,)},
        conditions={
            "StringLike": {f"{PROVIDER_HOST}:sub": (pattern,)},
            "StringEquals": {f"{PROVIDER_HOST}:aud": ("sts.amazonaws.com",)},
        },
    )
    return RoleFact(
        id="role:trust",
        address="aws_iam_role.trust",
        name="trust",
        trust_statements=(statement,),
    )


@pytest.mark.security
@given(pattern=PATTERN, candidate=CANDIDATE)
@settings(max_examples=300, deadline=None)
def test_action_prefilter_never_drops_a_possible_allow(pattern: str, candidate: str) -> None:
    role = _role_with_allow(pattern)
    ctx = PolicyContext(account=ACCOUNT, region=REGION)

    decision = evaluate_action(role, ACTION, candidate, ctx).decision

    if decision in {Decision.ALLOW, Decision.CONDITIONAL_ALLOW}:
        prefilter = action_filter(role, ctx, (ACTION,))
        assert prefilter.could_apply((candidate,))


@pytest.mark.security
@given(
    pattern=PATTERN,
    subject=st.text(alphabet="abAB:/*?", max_size=12),
    audience=st.sampled_from(["sts.amazonaws.com", "other"]),
)
@settings(max_examples=300, deadline=None)
def test_trust_prefilter_never_drops_a_possible_match(
    pattern: str, subject: str, audience: str
) -> None:
    role = _trust_role(pattern)
    candidate = SubjectCandidate(
        subject=subject,
        format=SubFormat.CLASSIC,
        trigger="push",
        audience=audience,
    )
    registry = condition_keys()

    evaluation = evaluate_trust_statements(role, (candidate,), registry=registry)

    if evaluation.matches:
        assert trust_subject_filter(role, registry).may_match((candidate,))


@given(owner=OWNER, repo=REPO, ref=REF)
def test_action_selector_round_trips(owner: str, repo: str, ref: str) -> None:
    raw = f"action:{owner}/{repo}@{ref}"

    selector = parse_selector(raw)

    assert selector.kind is SelectorKind.ACTION
    assert selector.raw == raw
    assert selector.value == f"{owner}/{repo}@{ref}"


@given(owner=OWNER, repo=REPO)
def test_action_any_selector_round_trips(owner: str, repo: str) -> None:
    raw = f"action-any:{owner}/{repo}"

    selector = parse_selector(raw)

    assert selector.kind is SelectorKind.ACTION_ANY
    assert selector.value == f"{owner}/{repo}"


@given(
    path=st.text(alphabet="abc/._-", min_size=1, max_size=12),
    job=st.text(alphabet="abcXYZ019_-", min_size=1, max_size=8),
)
def test_job_selector_round_trips(path: str, job: str) -> None:
    raw = f"job:{path}#{job}"

    selector = parse_selector(raw)

    assert selector.kind is SelectorKind.JOB
    assert selector.value == f"{path}#{job}"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "nope",
        "repo-write:",
        "fork-pr:x",
        "all-mutable-actions:x",
        "action:",
        "action:owner",
        "action:owner/repo",
        "action-any:owner",
        "action-any:owner/repo@v1",
        "job:no-hash",
        "secret:",
        "role:",
        "workflow:",
    ],
)
def test_malformed_selectors_are_rejected(raw: str) -> None:
    with pytest.raises(SelectorError):
        parse_selector(raw)


@given(first=SEGMENT, second=SEGMENT)
def test_job_identifiers_are_stable_and_content_sensitive(first: str, second: str) -> None:
    assert job_node_id("wf.yml", first) == job_node_id("wf.yml", first)
    if first != second:
        assert job_node_id("wf.yml", first) != job_node_id("wf.yml", second)
        assert job_node_id(first, "job") != job_node_id(second, "job")


@given(first=SEGMENT, second=SEGMENT)
def test_action_identifiers_are_stable_and_content_sensitive(first: str, second: str) -> None:
    base = action_node_id("owner", "repo", None, "v1")

    assert action_node_id("owner", "repo", None, "v1") == base
    if first != second:
        assert action_node_id(first, "repo", None, "v1") != base
        assert action_node_id("owner", first, None, "v1") != base
        assert action_node_id("owner", "repo", None, first) != base


def test_other_identifier_families_have_distinct_prefixes() -> None:
    identifiers = {
        workflow_node_id("a.yml"),
        job_node_id("a.yml", "job"),
        action_node_id("o", "r", None, "v1"),
        local_action_node_id("./x"),
        credential_node_id("job:a.yml#job", "TOKEN"),
        role_node_id("arn:aws:iam::1:role/x"),
        sink_node_id("ssm_parameter", "/x"),
    }

    assert len(identifiers) == 7
    assert all(
        value.startswith(("wf:", "job:", "action:", "cred:", "aws:")) for value in identifiers
    )


def test_edge_and_finding_ids_ignore_evidence_and_node_order() -> None:
    declared = Evidence(cls=EvidenceClass.DECLARED, rule="R1", file="a.yml", line=1)
    derived = Evidence(cls=EvidenceClass.DERIVED, rule="R9", file="b.yml", line=9)

    assert edge_id("RUNS_IN", "job:a", "action:b", (declared, derived)) == edge_id(
        "RUNS_IN", "job:a", "action:b", (derived, declared)
    )
    assert finding_id("NHB-TEST", ("n2", "n1"), (declared, derived)) == finding_id(
        "NHB-TEST", ("n1", "n2"), (derived, declared)
    )


def test_edge_and_finding_ids_change_with_content() -> None:
    declared = Evidence(cls=EvidenceClass.DECLARED, rule="R1", file="a.yml", line=1)
    derived = Evidence(cls=EvidenceClass.DERIVED, rule="R9", file="b.yml", line=9)

    assert edge_id("RUNS_IN", "job:a", "action:b", (declared,)) != edge_id(
        "RUNS_IN", "job:a", "action:c", (declared,)
    )
    assert edge_id("RUNS_IN", "job:a", "action:b", (declared,)) != edge_id(
        "RUNS_IN", "job:a", "action:b", (derived,)
    )
    assert finding_id("NHB-TEST", ("n1",), (declared,)) != finding_id(
        "NHB-TEST", ("n1",), (derived,)
    )


def test_digest_pairs_is_order_independent_and_content_sensitive() -> None:
    pairs = [("b.yml", "22"), ("a.yml", "11")]

    assert digest_pairs(pairs) == digest_pairs(reversed(pairs))
    assert digest_pairs(pairs) != digest_pairs([("a.yml", "11")])
    assert file_sha256(b"same") == file_sha256(b"same")
    assert file_sha256(b"same") != file_sha256(b"other")


@given(
    policy_values=st.lists(st.text(alphabet="ab", max_size=2), max_size=3),
    context_values=st.frozensets(st.text(alphabet="ab", max_size=2), max_size=3),
)
def test_string_equals_truth_is_set_membership(
    policy_values: list[str], context_values: frozenset[str]
) -> None:
    evaluation = evaluate_conditions(
        {"StringEquals": {"k": tuple(policy_values)}},
        {"k": context_values},
        mode=ConditionMode.CONCRETE,
        supported_keys=None,
    )

    if not context_values:
        assert evaluation.truth is ConditionTruth.UNRESOLVED
    elif any(value in context_values for value in policy_values):
        assert evaluation.truth is ConditionTruth.TRUE
    else:
        assert evaluation.truth is ConditionTruth.FALSE


@given(
    policy_values=st.lists(st.text(alphabet="ab*?", max_size=3), max_size=3),
    context_values=st.frozensets(st.text(alphabet="ab", max_size=3), max_size=3),
)
def test_string_like_truth_is_glob_intersection(
    policy_values: list[str], context_values: frozenset[str]
) -> None:
    evaluation = evaluate_conditions(
        {"StringLike": {"k": tuple(policy_values)}},
        {"k": context_values},
        mode=ConditionMode.CONCRETE,
        supported_keys=None,
    )

    matched = any(
        glob_match(pattern, value) for pattern in policy_values for value in context_values
    )
    if not context_values:
        assert evaluation.truth is ConditionTruth.UNRESOLVED
    elif matched:
        assert evaluation.truth is ConditionTruth.TRUE
    else:
        assert evaluation.truth is ConditionTruth.FALSE


@given(
    policy_values=st.lists(st.text(alphabet="aAbB", max_size=2), max_size=3),
    context_values=st.frozensets(st.text(alphabet="aAbB", max_size=2), max_size=3),
)
def test_case_insensitive_equals_truth(
    policy_values: list[str], context_values: frozenset[str]
) -> None:
    evaluation = evaluate_conditions(
        {"StringEqualsIgnoreCase": {"k": tuple(policy_values)}},
        {"k": context_values},
        mode=ConditionMode.CONCRETE,
        supported_keys=None,
    )

    matched = any(
        pattern.lower() == value.lower() for pattern in policy_values for value in context_values
    )
    if not context_values:
        assert evaluation.truth is ConditionTruth.UNRESOLVED
    elif matched:
        assert evaluation.truth is ConditionTruth.TRUE
    else:
        assert evaluation.truth is ConditionTruth.FALSE


def test_empty_condition_block_is_true_for_any_context() -> None:
    assert (
        evaluate_conditions({}, {}, mode=ConditionMode.CONCRETE, supported_keys=None).truth
        is ConditionTruth.TRUE
    )
    assert (
        evaluate_conditions(
            {}, {"anything": frozenset({"x"})}, mode=ConditionMode.CANDIDATE, supported_keys=None
        ).truth
        is ConditionTruth.TRUE
    )
