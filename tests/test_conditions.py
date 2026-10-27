"""Condition evaluation truth table (spec 9.3)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from nhi_blast.aws.conditions import (
    ConditionMode,
    ConditionTruth,
    evaluate_conditions,
)

Context = Mapping[str, frozenset[str]]


def evaluate(
    conditions: dict[str, dict[str, Any]],
    context: dict[str, frozenset[str]] | None = None,
    *,
    mode: ConditionMode = ConditionMode.CONCRETE,
    supported: frozenset[str] | None = None,
):
    return evaluate_conditions(
        conditions,
        context or {},
        mode=mode,
        supported_keys=supported,
    )


def test_empty_conditions_are_true() -> None:
    assert evaluate({}).truth is ConditionTruth.TRUE


@pytest.mark.parametrize(
    ("operator", "expected", "context", "truth"),
    [
        ("StringEquals", ["a"], {"k": frozenset({"a"})}, ConditionTruth.TRUE),
        ("StringEquals", ["a"], {"k": frozenset({"b"})}, ConditionTruth.FALSE),
        (
            "StringEqualsIgnoreCase",
            ["A"],
            {"k": frozenset({"a"})},
            ConditionTruth.TRUE,
        ),
        ("StringLike", ["a*"], {"k": frozenset({"abc"})}, ConditionTruth.TRUE),
        ("StringLike", ["a*"], {"k": frozenset({"b"})}, ConditionTruth.FALSE),
        (
            "ArnLike",
            ["arn:aws:iam::*:role/x"],
            {"k": frozenset({"arn:aws:iam::1:role/x"})},
            ConditionTruth.TRUE,
        ),
        ("Bool", ["true"], {"k": frozenset({"true"})}, ConditionTruth.TRUE),
        ("Bool", ["false"], {"k": frozenset({"true"})}, ConditionTruth.FALSE),
        ("NumericLessThan", ["10"], {"k": frozenset({"5"})}, ConditionTruth.UNRESOLVED),
        (
            "DateLessThan",
            ["2026-01-01"],
            {"k": frozenset({"2025-01-01"})},
            ConditionTruth.UNRESOLVED,
        ),
        ("IpAddress", ["10.0.0.0/8"], {"k": frozenset({"10.1.1.1"})}, ConditionTruth.UNRESOLVED),
    ],
)
def test_string_and_unsupported_operators(
    operator: str,
    expected: list[str],
    context: dict[str, frozenset[str]],
    truth: ConditionTruth,
) -> None:
    assert evaluate({operator: {"k": expected}}, context).truth is truth


def test_unknown_key_is_unresolved() -> None:
    result = evaluate({"StringEquals": {"missing": ["a"]}})
    assert result.truth is ConditionTruth.UNRESOLVED
    assert result.unresolved_keys == ("missing",)


def test_unsupported_key_is_a_dead_condition() -> None:
    result = evaluate(
        {"StringEquals": {"repository_owner": ["acme"]}},
        {"repository_owner": frozenset({"acme"})},
        supported=frozenset({"sub", "repository"}),
    )
    assert result.truth is ConditionTruth.FALSE
    assert result.dead_keys == ("repository_owner",)


def test_dead_key_fails_closed_even_when_other_conditions_are_true() -> None:
    result = evaluate(
        {
            "StringEquals": {"sub": ["repo:acme/shop:ref:refs/heads/main"]},
            "StringLike": {"repository_owner": ["acme"]},
        },
        {"sub": frozenset({"repo:acme/shop:ref:refs/heads/main"})},
        supported=frozenset({"sub"}),
    )
    assert result.truth is ConditionTruth.FALSE


def test_policy_variable_is_unresolved() -> None:
    result = evaluate(
        {"StringEquals": {"sub": ["${aws:PrincipalTag/repo}"]}},
        {"sub": frozenset({"repo:acme/shop:ref:refs/heads/main"})},
    )
    assert result.truth is ConditionTruth.UNRESOLVED


def test_null_operator() -> None:
    assert evaluate({"Null": {"k": ["true"]}}).truth is ConditionTruth.TRUE
    assert (
        evaluate({"Null": {"k": ["true"]}}, {"k": frozenset({"present"})}).truth
        is ConditionTruth.FALSE
    )
    assert (
        evaluate({"Null": {"k": ["false"]}}, {"k": frozenset({"present"})}).truth
        is ConditionTruth.TRUE
    )
    assert evaluate({"Null": {"k": ["false"]}}).truth is ConditionTruth.FALSE


def test_if_exists_absent_key_is_true() -> None:
    result = evaluate({"StringEqualsIfExists": {"environment": ["prod"]}})
    assert result.truth is ConditionTruth.TRUE


def test_negative_operator_inverts_concrete_result() -> None:
    context = {"sub": frozenset({"repo:acme/shop:ref:refs/heads/dev"})}
    conditions = {"StringNotEquals": {"sub": ["repo:acme/shop:ref:refs/heads/main"]}}
    assert evaluate(conditions, context).truth is ConditionTruth.TRUE
    assert (
        evaluate(
            {"StringEquals": {"sub": ["repo:acme/shop:ref:refs/heads/main"]}},
            context,
        ).truth
        is ConditionTruth.FALSE
    )


def test_negative_operator_against_candidate_glob_is_unresolved() -> None:
    conditions = {"StringNotLike": {"sub": ["repo:acme/shop:ref:refs/heads/main"]}}
    context = {"sub": frozenset({"repo:acme/shop:ref:refs/heads/*"})}
    result = evaluate(conditions, context, mode=ConditionMode.CANDIDATE)
    assert result.truth is ConditionTruth.UNRESOLVED


def test_positive_operators_intersect_candidates() -> None:
    conditions = {"StringEquals": {"sub": ["repo:acme/shop:ref:refs/heads/main"]}}
    context = {"sub": frozenset({"repo:acme/shop:ref:refs/heads/*"})}
    assert evaluate(conditions, context, mode=ConditionMode.CANDIDATE).truth is ConditionTruth.TRUE
    other = {"sub": frozenset({"repo:acme/other:ref:refs/heads/*"})}
    assert evaluate(conditions, other, mode=ConditionMode.CANDIDATE).truth is ConditionTruth.FALSE


def test_any_and_all_qualifiers() -> None:
    context = {"k": frozenset({"a1", "b2"})}
    any_match = {"ForAnyValue:StringLike": {"k": ["a*"]}}
    all_match = {"ForAllValues:StringLike": {"k": ["a*"]}}
    both_match = {"ForAllValues:StringLike": {"k": ["a*", "b*"]}}
    assert evaluate(any_match, context).truth is ConditionTruth.TRUE
    assert evaluate(all_match, context).truth is ConditionTruth.FALSE
    assert evaluate(both_match, context).truth is ConditionTruth.TRUE


def test_every_condition_must_be_true() -> None:
    context = {"a": frozenset({"1"}), "b": frozenset({"2"})}
    conditions = {"StringEquals": {"a": ["1"], "b": ["3"]}}
    assert evaluate(conditions, context).truth is ConditionTruth.FALSE


def test_unresolved_and_false_combine_to_false() -> None:
    context = {"a": frozenset({"1"})}
    conditions = {"StringEquals": {"missing": ["x"], "a": ["2"]}}
    result = evaluate(conditions, context)
    assert result.truth is ConditionTruth.FALSE
