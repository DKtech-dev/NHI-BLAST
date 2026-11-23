"""Loop 6 soundness tests: unit regressions and Hypothesis property tests.

Covers all 5 AWS solver, condition evaluator, and policy evaluation soundness fixes:
1. Cross-repo reusable workflow ``job_workflow_ref`` independence in correlated OIDC solving
2. Per-predicate case folding (no global ``force_fold``) in ``solve_string_predicates``
3. Unknown-state CIDR / Numeric / Date contradiction detection in ``_joint_candidate_solve``
4. Customer-managed KMS ``NOT_APPLICABLE`` -> ``CONDITIONAL_ALLOW`` vs explicit ``DENY``
5. ``can_assume_role`` condition evaluation (skipping ``FALSE`` trust statements) and
   ``_resource_applies`` ``NotResource`` coverage semantics against wildcard candidates.
"""

from __future__ import annotations

import ipaddress
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from nhi_blast.aws.conditions import (
    ConditionMode,
    ConditionTruth,
    Present,
    evaluate_conditions,
)
from nhi_blast.aws.glob import glob_match
from nhi_blast.aws.policy_eval import (
    ASSUMPTION_KMS,
    _resource_applies,
    can_assume_role,
    can_read,
    evaluate_action,
    persistence_capabilities,
)
from nhi_blast.aws.solver import (
    SolverStatus,
    StringPredicate,
    solve_correlated_oidc_predicates,
    solve_string_predicates,
)
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.models import (
    Decision,
    PolicyContext,
    PolicyEffect,
    RoleFact,
    SinkFact,
    SinkType,
    Statement,
)

ACCOUNT = "111122223333"
OTHER_ACCOUNT = "999988887777"
REGION = "us-east-1"


def _ctx() -> PolicyContext:
    return PolicyContext(account=ACCOUNT, region=REGION, managed_policies={})


# ------------------------------------------------ 1. Correlated OIDC job_workflow_ref


def test_reusable_workflow_jwr_does_not_contradict_caller_sub_owner_repo_or_ref() -> None:
    res = solve_correlated_oidc_predicates(
        {
            "sub": (
                StringPredicate(
                    label="sub_eq",
                    patterns=("repo:org-a/app:ref:refs/heads/main",),
                    is_glob=False,
                ),
            ),
            "repository": (
                StringPredicate(label="repo_eq", patterns=("org-a/app",), is_glob=False),
            ),
            "repository_owner": (
                StringPredicate(label="owner_eq", patterns=("org-a",), is_glob=False),
            ),
            "ref": (StringPredicate(label="ref_eq", patterns=("refs/heads/main",), is_glob=False),),
            "job_workflow_ref": (
                StringPredicate(
                    label="jwr_eq",
                    patterns=("org-b/shared/.github/workflows/deploy.yml@refs/tags/v1",),
                    is_glob=False,
                ),
            ),
        }
    )
    assert res.status is SolverStatus.SAT
    assert res.witnesses["sub"] == "repo:org-a/app:ref:refs/heads/main"
    assert res.witnesses["repository"] == "org-a/app"
    assert res.witnesses["repository_owner"] == "org-a"
    assert res.witnesses["ref"] == "refs/heads/main"
    assert (
        res.witnesses["job_workflow_ref"]
        == "org-b/shared/.github/workflows/deploy.yml@refs/tags/v1"
    )


def test_sub_still_projects_repo_owner_ref_and_environment() -> None:
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

    unsat_env = solve_correlated_oidc_predicates(
        {
            "sub": (
                StringPredicate(
                    label="sub",
                    patterns=("repo:org-a/app:environment:prod",),
                    is_glob=False,
                ),
            ),
            "environment": (StringPredicate(label="env", patterns=("staging",), is_glob=False),),
        }
    )
    assert unsat_env.status is SolverStatus.UNSAT


def test_jwr_self_contradiction_is_still_unsat() -> None:
    res = solve_correlated_oidc_predicates(
        {
            "job_workflow_ref": (
                StringPredicate(
                    label="jwr_pos",
                    patterns=("org-b/shared/.github/workflows/deploy.yml@refs/tags/v1",),
                    is_glob=False,
                ),
                StringPredicate(
                    label="jwr_neg",
                    patterns=("org-b/shared/*",),
                    negated=True,
                    is_glob=True,
                ),
            ),
        }
    )
    assert res.status is SolverStatus.UNSAT


_SLUG_PART = st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=8)


@settings(max_examples=80, deadline=None)
@given(
    owner_a=_SLUG_PART,
    repo_a=_SLUG_PART,
    branch_a=_SLUG_PART,
    owner_b=_SLUG_PART,
    repo_b=_SLUG_PART,
    tag_b=_SLUG_PART,
)
def test_property_reusable_jwr_never_falsely_unsat_against_caller_sub(
    owner_a: str,
    repo_a: str,
    branch_a: str,
    owner_b: str,
    repo_b: str,
    tag_b: str,
) -> None:
    sub_val = f"repo:{owner_a}/{repo_a}:ref:refs/heads/{branch_a}"
    jwr_val = f"{owner_b}/{repo_b}/.github/workflows/reusable.yml@refs/tags/{tag_b}"
    res = solve_correlated_oidc_predicates(
        {
            "sub": (StringPredicate("sub", (sub_val,), is_glob=False),),
            "repository": (StringPredicate("repo", (f"{owner_a}/{repo_a}",), is_glob=False),),
            "repository_owner": (StringPredicate("owner", (owner_a,), is_glob=False),),
            "ref": (StringPredicate("ref", (f"refs/heads/{branch_a}",), is_glob=False),),
            "job_workflow_ref": (StringPredicate("jwr", (jwr_val,), is_glob=False),),
        }
    )
    assert res.status is SolverStatus.SAT
    assert res.witnesses["sub"] == sub_val
    assert res.witnesses["job_workflow_ref"] == jwr_val


# ------------------------------------------------ 2. Per-predicate case folding


def test_mixed_fold_and_case_sensitive_negation_is_sat_with_mixed_case_witness() -> None:
    preds = (
        StringPredicate("eq_fold", ("main",), fold=True, is_glob=False),
        StringPredicate("not_eq", ("main",), negated=True, fold=False, is_glob=False),
    )
    res = solve_string_predicates(preds)
    assert res.status is SolverStatus.SAT
    assert res.witness is not None
    assert res.witness.lower() == "main"
    assert res.witness != "main"


def test_mixed_fold_and_exact_negation_via_evaluate_conditions_candidate_mode() -> None:
    ev = evaluate_conditions(
        {
            "StringEqualsIgnoreCase": {"ref": ("main",)},
            "StringNotEquals": {"ref": ("main",)},
        },
        {"ref": Present(("*",))},
        mode=ConditionMode.CANDIDATE,
    )
    assert ev.truth is not ConditionTruth.FALSE
    witness_map = dict(ev.witnesses)
    assert "ref" in witness_map
    assert witness_map["ref"].lower() == "main"
    assert witness_map["ref"] != "main"


def test_fold_without_letters_plus_exact_negation_is_unsat() -> None:
    preds = (
        StringPredicate("eq_fold", ("1234",), fold=True, is_glob=False),
        StringPredicate("not_eq", ("1234",), negated=True, fold=False, is_glob=False),
    )
    assert solve_string_predicates(preds).status is SolverStatus.UNSAT


def test_both_folded_positive_and_negative_same_word_is_unsat() -> None:
    preds = (
        StringPredicate("eq_fold", ("main",), fold=True, is_glob=False),
        StringPredicate("not_eq_fold", ("MAIN",), negated=True, fold=True, is_glob=False),
    )
    assert solve_string_predicates(preds).status is SolverStatus.UNSAT


_MIXED_PAT = st.text(alphabet="abAB1*?", min_size=1, max_size=6)
_MIXED_EXACT = st.text(alphabet="abAB1", min_size=1, max_size=6)


def _matches_pred(pred: StringPredicate, candidate: str) -> bool:
    if pred.is_glob:
        matched = any(glob_match(p, candidate, fold=pred.fold) for p in pred.patterns)
    elif pred.fold:
        matched = any(p.lower() == candidate.lower() for p in pred.patterns)
    else:
        matched = any(p == candidate for p in pred.patterns)
    return (not matched) if pred.negated else matched


@settings(max_examples=120, deadline=None)
@given(
    p1=_MIXED_PAT,
    p2=_MIXED_PAT,
    fold1=st.booleans(),
    fold2=st.booleans(),
    glob1=st.booleans(),
    glob2=st.booleans(),
)
def test_property_mixed_fold_sat_witness_satisfies_each_predicate_with_own_fold(
    p1: str,
    p2: str,
    fold1: bool,
    fold2: bool,
    glob1: bool,
    glob2: bool,
) -> None:
    pred1 = StringPredicate("p1", (p1,), negated=False, fold=fold1, is_glob=glob1)
    pred2 = StringPredicate("p2", (p2,), negated=True, fold=fold2, is_glob=glob2)
    res = solve_string_predicates((pred1, pred2))
    if res.status is SolverStatus.SAT:
        assert res.witness is not None
        assert _matches_pred(pred1, res.witness)
        assert _matches_pred(pred2, res.witness)


@settings(max_examples=120, deadline=None)
@given(
    p1=_MIXED_PAT,
    p2=_MIXED_PAT,
    fold1=st.booleans(),
    fold2=st.booleans(),
    glob1=st.booleans(),
    glob2=st.booleans(),
    concrete=_MIXED_EXACT,
)
def test_property_mixed_fold_concrete_witness_never_rejected_as_unsat(
    p1: str,
    p2: str,
    fold1: bool,
    fold2: bool,
    glob1: bool,
    glob2: bool,
    concrete: str,
) -> None:
    pred1 = StringPredicate("p1", (p1,), negated=False, fold=fold1, is_glob=glob1)
    pred2 = StringPredicate("p2", (p2,), negated=True, fold=fold2, is_glob=glob2)
    if not (_matches_pred(pred1, concrete) and _matches_pred(pred2, concrete)):
        return
    res = solve_string_predicates((pred1, pred2))
    assert res.status is not SolverStatus.UNSAT


# ------------------------------------------------ 3. Unknown CIDR / Numeric / Date UNSAT


def test_unknown_ip_contradiction_is_unsat_in_candidate_mode() -> None:
    ev = evaluate_conditions(
        {
            "IpAddress": {"aws:SourceIp": ("10.0.0.0/8",)},
            "NotIpAddress": {"aws:SourceIp": ("10.0.0.0/8",)},
        },
        {},
        mode=ConditionMode.CANDIDATE,
    )
    assert ev.truth is ConditionTruth.FALSE
    assert any("joint solver UNSAT" in r for r in ev.reasons)


def test_unknown_date_contradiction_is_unsat_in_candidate_mode() -> None:
    ev = evaluate_conditions(
        {
            "DateGreaterThan": {"aws:CurrentTime": ("2026-06-01T00:00:00Z",)},
            "DateLessThan": {"aws:CurrentTime": ("2026-01-01T00:00:00Z",)},
        },
        {},
        mode=ConditionMode.CANDIDATE,
    )
    assert ev.truth is ConditionTruth.FALSE
    assert any("joint solver UNSAT" in r for r in ev.reasons)


def test_unknown_numeric_contradiction_is_unsat_in_candidate_mode() -> None:
    ev = evaluate_conditions(
        {
            "NumericGreaterThan": {"aws:MultiFactorAuthAge": ("100",)},
            "NumericLessThan": {"aws:MultiFactorAuthAge": ("50",)},
        },
        {},
        mode=ConditionMode.CANDIDATE,
    )
    assert ev.truth is ConditionTruth.FALSE
    assert any("joint solver UNSAT" in r for r in ev.reasons)


def test_unknown_if_exists_or_all_negated_ip_stays_unresolved_for_absent_soundness() -> None:
    # Absent satisfies both *IfExists clauses, so Unknown must stay UNRESOLVED.
    ev_if_exists = evaluate_conditions(
        {
            "IpAddressIfExists": {"aws:SourceIp": ("10.0.0.0/8",)},
            "NotIpAddressIfExists": {"aws:SourceIp": ("10.0.0.0/8",)},
        },
        {},
        mode=ConditionMode.CANDIDATE,
    )
    assert ev_if_exists.truth is ConditionTruth.UNRESOLVED

    # Absent satisfies NotIpAddress even when all IPv4+IPv6 ranges are excluded.
    ev_all_neg = evaluate_conditions(
        {"NotIpAddress": {"aws:SourceIp": ("0.0.0.0/0", "::/0")}},
        {},
        mode=ConditionMode.CANDIDATE,
    )
    assert ev_all_neg.truth is ConditionTruth.UNRESOLVED


@settings(max_examples=80, deadline=None)
@given(
    lo=st.integers(min_value=-1000, max_value=1000),
    hi=st.integers(min_value=-1000, max_value=1000),
)
def test_property_unknown_numeric_interval_unsat_iff_empty(lo: int, hi: int) -> None:
    ev = evaluate_conditions(
        {
            "NumericGreaterThan": {"aws:MultiFactorAuthAge": (str(Decimal(lo)),)},
            "NumericLessThan": {"aws:MultiFactorAuthAge": (str(Decimal(hi)),)},
        },
        {},
        mode=ConditionMode.CANDIDATE,
    )
    if lo >= hi:
        assert ev.truth is ConditionTruth.FALSE
    else:
        assert ev.truth is ConditionTruth.UNRESOLVED


@settings(max_examples=80, deadline=None)
@given(
    prefix_a=st.integers(min_value=16, max_value=30),
    prefix_b=st.integers(min_value=16, max_value=30),
    third_a=st.integers(min_value=0, max_value=3),
    third_b=st.integers(min_value=0, max_value=3),
)
def test_property_unknown_cidr_unsat_iff_excluded_supernet(
    prefix_a: int, prefix_b: int, third_a: int, third_b: int
) -> None:
    net_a = ipaddress.IPv4Network(f"10.0.{third_a}.0/{prefix_a}", strict=False)
    net_b = ipaddress.IPv4Network(f"10.0.{third_b}.0/{prefix_b}", strict=False)
    ev = evaluate_conditions(
        {
            "IpAddress": {"aws:SourceIp": (str(net_a),)},
            "NotIpAddress": {"aws:SourceIp": (str(net_b),)},
        },
        {},
        mode=ConditionMode.CANDIDATE,
    )
    if net_b.supernet_of(net_a):
        assert ev.truth is ConditionTruth.FALSE
    else:
        assert ev.truth is ConditionTruth.UNRESOLVED


# ------------------------------------------------ 4. can_read CMK NOT_APPLICABLE vs DENY


def test_can_read_cmk_not_applicable_returns_conditional_allow_with_kms_assumption() -> None:
    param_arn = f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/prod/secret"
    sink = SinkFact(
        id="sink:ssm:prod",
        name="/prod/secret",
        sink_type=SinkType.SSM_PARAMETER,
        arn=param_arn,
        kms_key_id="key-123",
    )
    role = RoleFact(
        id="role:reader",
        address="aws_iam_role.reader",
        name="reader",
        arn=f"arn:aws:iam::{ACCOUNT}:role/reader",
        inline_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("ssm:GetParameter",),
                resources=(param_arn,),
            ),
        ),
    )

    result = can_read(role, sink, _ctx(), region=REGION, account=ACCOUNT)
    assert result.decision is Decision.CONDITIONAL_ALLOW
    assert result.evidence_class is EvidenceClass.ASSUMED
    assert ASSUMPTION_KMS in result.assumptions
    assert result.conditional_reasons


def test_can_read_cmk_explicit_deny_returns_deny() -> None:
    param_arn = f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/prod/secret"
    key_arn = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/key-123"
    sink = SinkFact(
        id="sink:ssm:prod",
        name="/prod/secret",
        sink_type=SinkType.SSM_PARAMETER,
        arn=param_arn,
        kms_key_id="key-123",
    )
    role = RoleFact(
        id="role:reader",
        address="aws_iam_role.reader",
        name="reader",
        arn=f"arn:aws:iam::{ACCOUNT}:role/reader",
        inline_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("ssm:GetParameter",),
                resources=(param_arn,),
            ),
            Statement(
                effect=PolicyEffect.DENY,
                actions=("kms:Decrypt",),
                resources=(key_arn,),
            ),
        ),
    )

    result = can_read(role, sink, _ctx(), region=REGION, account=ACCOUNT)
    assert result.decision is Decision.DENY
    assert result.evidence_class is EvidenceClass.DERIVED
    assert ASSUMPTION_KMS in result.assumptions


# ------------------------------------------------ 5. can_assume_role & NotResource


def test_can_assume_role_skips_provably_false_principal_account_condition() -> None:
    target_arn = f"arn:aws:iam::{ACCOUNT}:role/target"
    source_role = RoleFact(
        id="role:source",
        address="aws_iam_role.source",
        name="source",
        arn=f"arn:aws:iam::{ACCOUNT}:role/source",
        inline_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("sts:AssumeRole",),
                resources=(target_arn,),
            ),
        ),
    )
    target_role = RoleFact(
        id="role:target",
        address="aws_iam_role.target",
        name="target",
        arn=target_arn,
        trust_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("sts:AssumeRole",),
                principals={"AWS": (f"arn:aws:iam::{ACCOUNT}:root",)},
                conditions={"StringEquals": {"aws:PrincipalAccount": (OTHER_ACCOUNT,)}},
            ),
        ),
    )

    res = can_assume_role(source_role, target_role, _ctx())
    assert res.decision is Decision.NOT_APPLICABLE


def test_can_assume_role_skips_contradictory_ip_trust_condition() -> None:
    target_arn = f"arn:aws:iam::{ACCOUNT}:role/target"
    source_role = RoleFact(
        id="role:source",
        address="aws_iam_role.source",
        name="source",
        arn=f"arn:aws:iam::{ACCOUNT}:role/source",
        inline_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("sts:AssumeRole",),
                resources=(target_arn,),
            ),
        ),
    )
    target_role = RoleFact(
        id="role:target",
        address="aws_iam_role.target",
        name="target",
        arn=target_arn,
        trust_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("sts:AssumeRole",),
                principals={"AWS": (source_role.arn or "",)},
                conditions={
                    "IpAddress": {"aws:SourceIp": ("10.0.0.0/8",)},
                    "NotIpAddress": {"aws:SourceIp": ("10.0.0.0/8",)},
                },
            ),
        ),
    )

    res = can_assume_role(source_role, target_role, _ctx())
    assert res.decision is Decision.NOT_APPLICABLE


def test_can_assume_role_matching_principal_account_is_definite_allow() -> None:
    target_arn = f"arn:aws:iam::{ACCOUNT}:role/target"
    source_role = RoleFact(
        id="role:source",
        address="aws_iam_role.source",
        name="source",
        arn=f"arn:aws:iam::{ACCOUNT}:role/source",
        inline_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("sts:AssumeRole",),
                resources=(target_arn,),
            ),
        ),
    )
    target_role = RoleFact(
        id="role:target",
        address="aws_iam_role.target",
        name="target",
        arn=target_arn,
        trust_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("sts:AssumeRole",),
                principals={"AWS": (f"arn:aws:iam::{ACCOUNT}:root",)},
                conditions={"StringEquals": {"aws:PrincipalAccount": (ACCOUNT,)}},
            ),
        ),
    )

    res = can_assume_role(source_role, target_role, _ctx())
    assert res.decision is Decision.ALLOW
    assert res.evidence_class is EvidenceClass.DERIVED


def test_can_assume_role_unresolved_external_id_is_conditional_allow() -> None:
    target_arn = f"arn:aws:iam::{ACCOUNT}:role/target"
    source_role = RoleFact(
        id="role:source",
        address="aws_iam_role.source",
        name="source",
        arn=f"arn:aws:iam::{ACCOUNT}:role/source",
        inline_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("sts:AssumeRole",),
                resources=(target_arn,),
            ),
        ),
    )
    target_role = RoleFact(
        id="role:target",
        address="aws_iam_role.target",
        name="target",
        arn=target_arn,
        trust_statements=(
            Statement(
                effect=PolicyEffect.ALLOW,
                actions=("sts:AssumeRole",),
                principals={"AWS": (source_role.arn or "",)},
                conditions={"StringEquals": {"sts:ExternalId": ("secret-ext-id",)}},
            ),
        ),
    )

    res = can_assume_role(source_role, target_role, _ctx())
    assert res.decision is Decision.CONDITIONAL_ALLOW
    assert res.evidence_class is EvidenceClass.ASSUMED


def test_not_resource_specific_arn_does_not_suppress_wildcard_candidate() -> None:
    breakglass = "arn:aws:iam::123456789012:user/breakglass"
    stmt = Statement(
        effect=PolicyEffect.ALLOW,
        actions=("iam:*",),
        not_resources=(breakglass,),
    )
    role = RoleFact(
        id="role:admin",
        address="aws_iam_role.admin",
        name="admin",
        arn=f"arn:aws:iam::{ACCOUNT}:role/admin",
        inline_statements=(stmt,),
    )

    # Against wildcard "*", the statement still applies to all non-breakglass IAM resources.
    assert _resource_applies(stmt, ("*",)) == (True, False)
    assert evaluate_action(role, "iam:CreateAccessKey", "*", _ctx()).decision is Decision.ALLOW
    caps = dict(persistence_capabilities(role, _ctx()))
    assert "iam:CreateAccessKey" in caps
    assert caps["iam:CreateAccessKey"].decision is Decision.ALLOW

    # Against the exact excluded ARN, the statement does NOT apply.
    assert _resource_applies(stmt, (breakglass,)) == (False, False)
    assert (
        evaluate_action(role, "iam:CreateAccessKey", breakglass, _ctx()).decision
        is Decision.NOT_APPLICABLE
    )

    # Against NotResource: "*", even wildcard "*" is fully covered -> does NOT apply.
    exclude_all = Statement(effect=PolicyEffect.ALLOW, actions=("iam:*",), not_resources=("*",))
    assert _resource_applies(exclude_all, ("*",)) == (False, False)


@settings(max_examples=80, deadline=None)
@given(user=_SLUG_PART)
def test_property_specific_not_resource_never_excludes_star_candidate(user: str) -> None:
    excluded_arn = f"arn:aws:iam::123456789012:user/{user}"
    stmt = Statement(
        effect=PolicyEffect.ALLOW,
        actions=("iam:*",),
        not_resources=(excluded_arn,),
    )
    assert _resource_applies(stmt, ("*",)) == (True, False)
    assert _resource_applies(stmt, (excluded_arn,)) == (False, False)
