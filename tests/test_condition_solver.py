"""Unit and Hypothesis property tests for the pure-Python condition solver."""

from __future__ import annotations

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
from nhi_blast.aws.solver import (
    CidrPredicate,
    IntervalPredicate,
    SolverStatus,
    StringPredicate,
    parse_iso8601_decimal,
    solve_cidr_predicates,
    solve_correlated_oidc_predicates,
    solve_interval_predicates,
    solve_string_predicates,
)


def test_string_solver_shared_witness_and_deterministic_shortest_output() -> None:
    preds = (
        StringPredicate("p1", ("repo:org/*:ref:refs/heads/*",)),
        StringPredicate("p2", ("repo:org/app:ref:refs/heads/rel*",)),
        StringPredicate("p3", ("repo:org/app:ref:refs/heads/release-old",), negated=True),
    )
    res_a = solve_string_predicates(preds)
    res_b = solve_string_predicates(preds)
    assert res_a.status is SolverStatus.SAT
    assert res_a.witness == res_b.witness
    assert res_a.witness is not None
    assert glob_match("repo:org/*:ref:refs/heads/*", res_a.witness)
    assert glob_match("repo:org/app:ref:refs/heads/rel*", res_a.witness)
    assert not glob_match("repo:org/app:ref:refs/heads/release-old", res_a.witness)


def test_string_solver_unsat_and_minimal_unsatisfiable_subset() -> None:
    preds = (
        StringPredicate("irrelevant_wide", ("repo:*",)),
        StringPredicate("only_main", ("repo:org/app:ref:refs/heads/main",)),
        StringPredicate("deny_main", ("repo:org/app:ref:refs/heads/main",), negated=True),
    )
    res = solve_string_predicates(preds)
    assert res.status is SolverStatus.UNSAT
    assert res.witness is None
    assert set(res.mus_labels) == {"only_main", "deny_main"}
    assert "irrelevant_wide" not in res.mus_labels


def test_string_solver_non_empty_ref_witness() -> None:
    res = solve_string_predicates((StringPredicate("p1", ("repo:org/app:ref:refs/heads/*",)),))
    assert res.status is SolverStatus.SAT
    assert res.witness is not None
    assert not res.witness.endswith("refs/heads/")
    assert len(res.witness) > len("repo:org/app:ref:refs/heads/")


def test_string_solver_case_insensitive_and_negation() -> None:
    preds = (
        StringPredicate("eq_fold", ("Repo:Org/App",), fold=True, is_glob=False),
        StringPredicate("not_eq", ("repo:org/app",), negated=True, fold=True, is_glob=False),
    )
    res = solve_string_predicates(preds)
    assert res.status is SolverStatus.UNSAT


def test_correlated_oidc_contradiction_detected_as_unsat() -> None:
    res = solve_correlated_oidc_predicates(
        {
            "sub": (StringPredicate("sub_eq", ("repo:org/app:ref:refs/heads/main",)),),
            "ref": (StringPredicate("ref_like", ("refs/heads/release*",)),),
        }
    )
    assert res.status is SolverStatus.UNSAT
    assert any("ref" in label for label in res.mus_labels)


def test_correlated_oidc_satisfiable_produces_coherent_witnesses() -> None:
    res = solve_correlated_oidc_predicates(
        {
            "sub": (StringPredicate("sub_like", ("repo:org/app:ref:refs/heads/release-*",)),),
            "ref": (StringPredicate("ref_like", ("refs/heads/release-*",)),),
            "job_workflow_ref": (
                StringPredicate(
                    "jwr",
                    ("org/app/.github/workflows/deploy.yml@refs/heads/release-1",),
                ),
            ),
        }
    )
    assert res.status is SolverStatus.SAT
    assert res.witnesses["ref"].startswith("refs/heads/release-")


def test_evaluate_conditions_uses_joint_solver_for_cross_key_contradiction() -> None:
    res = evaluate_conditions(
        {
            "StringEquals": {"sub": ("repo:org/app:ref:refs/heads/main",)},
            "StringLike": {"ref": ("refs/heads/release*",)},
        },
        {
            "sub": Present(("repo:org/app:ref:refs/heads/*",)),
            "ref": Present(("refs/heads/*",)),
        },
        mode=ConditionMode.CANDIDATE,
    )
    assert res.truth is ConditionTruth.FALSE
    assert any("joint solver UNSAT" in r for r in res.reasons)


def test_cidr_solver_conjunction_and_exclusion() -> None:
    sat = solve_cidr_predicates(
        (
            CidrPredicate("allow", ("10.0.0.0/24",)),
            CidrPredicate("deny_half", ("10.0.0.0/25",), negated=True),
        )
    )
    assert sat.status is SolverStatus.SAT
    assert sat.witness == "10.0.0.128"

    unsat = solve_cidr_predicates(
        (
            CidrPredicate("allow", ("10.0.0.0/25",)),
            CidrPredicate("deny_all", ("10.0.0.0/24",), negated=True),
        )
    )
    assert unsat.status is SolverStatus.UNSAT

    v6 = solve_cidr_predicates(
        (
            CidrPredicate("allow6", ("2001:db8::/32",)),
            CidrPredicate("deny6", ("2001:db8::/33",), negated=True),
        )
    )
    assert v6.status is SolverStatus.SAT
    assert v6.witness is not None
    assert v6.witness.startswith("2001:db8:")


def test_interval_solver_numeric_and_dates() -> None:
    sat = solve_interval_predicates(
        (
            IntervalPredicate("gt", "gt", (Decimal("10"),)),
            IntervalPredicate("lt", "lt", (Decimal("20"),)),
            IntervalPredicate("ne", "ne", (Decimal("15"),)),
        )
    )
    assert sat.status is SolverStatus.SAT
    assert sat.witness is not None
    assert Decimal("10") < sat.witness < Decimal("20")
    assert sat.witness != Decimal("15")

    unsat = solve_interval_predicates(
        (
            IntervalPredicate("ge", "ge", (Decimal("10"),)),
            IntervalPredicate("lt", "lt", (Decimal("10"),)),
        )
    )
    assert unsat.status is SolverStatus.UNSAT

    d1 = parse_iso8601_decimal("2026-01-01T00:00:00Z")
    d2 = parse_iso8601_decimal("2026-12-31T23:59:59Z")
    dsat = solve_interval_predicates(
        (
            IntervalPredicate("after", "gt", (d1,)),
            IntervalPredicate("before", "lt", (d2,)),
        )
    )
    assert dsat.status is SolverStatus.SAT
    assert dsat.witness is not None
    assert d1 < dsat.witness < d2


def test_solver_budget_cap_fails_closed(monkeypatch: object) -> None:
    import nhi_blast.aws.solver as solver_mod  # noqa: PLC0415

    monkeypatch.setattr(solver_mod, "MAX_DFA_STATES", 3)  # type: ignore[attr-defined]
    res = solve_string_predicates((StringPredicate("long", ("abcdefghijk*",)),))
    assert res.status is SolverStatus.BUDGET


_ALPHABET = st.text(alphabet="abc12*?", min_size=1, max_size=8)
_CONCRETE = st.text(alphabet="abc12", min_size=1, max_size=8)


@settings(max_examples=80, deadline=None)
@given(p1=_ALPHABET, p2=_ALPHABET, neg=_ALPHABET)
def test_property_every_sat_witness_evaluates_true_under_concrete_mode(
    p1: str, p2: str, neg: str
) -> None:
    preds = (
        StringPredicate("p1", (p1,)),
        StringPredicate("p2", (p2,)),
        StringPredicate("neg", (neg,), negated=True),
    )
    res = solve_string_predicates(preds)
    if res.status is SolverStatus.SAT:
        assert res.witness is not None
        ev = evaluate_conditions(
            {
                "StringLike": {"k": (p1,)},
                "StringNotLike": {"k": (neg,)},
            },
            {"k": Present((res.witness,))},
            mode=ConditionMode.CONCRETE,
        )
        assert ev.truth is ConditionTruth.TRUE
        assert glob_match(p2, res.witness)


@settings(max_examples=80, deadline=None)
@given(p1=_ALPHABET, neg=_ALPHABET, concrete=_CONCRETE)
def test_property_concrete_matching_string_is_never_rejected_as_unsat(
    p1: str, neg: str, concrete: str
) -> None:
    if not glob_match(p1, concrete) or glob_match(neg, concrete):
        return
    res = solve_string_predicates(
        (
            StringPredicate("p1", (p1,)),
            StringPredicate("neg", (neg,), negated=True),
        )
    )
    assert res.status is not SolverStatus.UNSAT
