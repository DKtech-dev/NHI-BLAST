"""Soundness of condition evaluation under unknown runtime information.

Invariant: unknown information never yields a definite TRUE/FALSE unless every
completion of the unknown keys (each replaced by Present(any values) or Absent) gives
the same result. Also holds the regressions for the old "missing from the map means
absent" defect.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nhi_blast.aws.conditions import (
    ABSENT,
    UNKNOWN,
    ConditionEvaluation,
    ConditionMode,
    ConditionTruth,
    KeyState,
    Present,
    evaluate_conditions,
)
from nhi_blast.aws.trust import evaluate_trust_statements
from nhi_blast.core.data import condition_keys
from tests.support import ASSUME_ACTION, candidate, role, statement

Conditions = dict[str, dict[str, list[str]]]
SUB_MAIN = "repo:acme/shop:ref:refs/heads/main"
KEYS = ("a", "b", "c")

# Policy values that are well-formed for each operator family, plus a few hostile ones.
_STRING_VALUES = ["a", "b", "a*", "B", "?", ""]
_NUMERIC_VALUES = ["1", "2", "10", "-3", "2.5"]
_DATE_VALUES = ["2026-01-01T00:00:00Z", "1767225600", "2025-06-01", "2026-01-01T05:30:00+05:30"]
_BOOL_VALUES = ["true", "false"]
_BINARY_VALUES = ["YQ==", "Yg=="]
_IP_VALUES = ["10.0.0.0/8", "10.1.1.1", "2001:db8::/32", "::1"]
_ARN_VALUES = ["arn:aws:s3:::a", "arn:aws:s3:::*", "arn:aws:iam::*:role/x"]
_HOSTILE_VALUES = ["${aws:username}", "x${y}", "not-a-number", "999.9.9.9", "***"]

_FAMILIES: list[tuple[list[str], list[str]]] = [
    (
        ["StringEquals", "StringNotEquals", "StringEqualsIgnoreCase", "StringNotEqualsIgnoreCase"],
        _STRING_VALUES,
    ),
    (["StringLike", "StringNotLike"], _STRING_VALUES),
    (
        [
            "NumericEquals",
            "NumericNotEquals",
            "NumericLessThan",
            "NumericLessThanEquals",
            "NumericGreaterThan",
            "NumericGreaterThanEquals",
        ],
        _NUMERIC_VALUES,
    ),
    (
        [
            "DateEquals",
            "DateNotEquals",
            "DateLessThan",
            "DateLessThanEquals",
            "DateGreaterThan",
            "DateGreaterThanEquals",
        ],
        _DATE_VALUES,
    ),
    (["Bool"], _BOOL_VALUES),
    (["BinaryEquals"], _BINARY_VALUES),
    (["IpAddress", "NotIpAddress"], _IP_VALUES),
    (["ArnEquals", "ArnLike", "ArnNotEquals", "ArnNotLike"], _ARN_VALUES),
    (["Null"], _BOOL_VALUES),
]
_CONTEXT_ALPHABET = [
    "a",
    "b",
    "a*",
    "1",
    "2",
    "10.1.1.1",
    "true",
    "YQ==",
    "arn:aws:s3:::a",
    "2026-01-01T00:00:00Z",
    "x",
]


@st.composite
def _condition_entry(draw: st.DrawFn) -> tuple[str, str, list[str]]:
    operators, values = draw(st.sampled_from(_FAMILIES))
    operator = draw(st.sampled_from(operators))
    pool = values + (_HOSTILE_VALUES if draw(st.booleans()) else [])
    policy_values = draw(st.lists(st.sampled_from(pool), min_size=1, max_size=3))
    qualifier = draw(st.sampled_from(["", "", "", "ForAllValues:", "ForAnyValue:"]))
    suffix = draw(st.sampled_from(["", "", "IfExists"]))
    return f"{qualifier}{operator}{suffix}", draw(st.sampled_from(KEYS)), policy_values


@st.composite
def _blocks(draw: st.DrawFn) -> Conditions:
    block: Conditions = {}
    for operator, key, values in draw(st.lists(_condition_entry(), min_size=1, max_size=4)):
        block.setdefault(operator, {})[key] = values
    return block


_values = st.lists(st.sampled_from(_CONTEXT_ALPHABET), max_size=3).map(tuple)
_known_states: st.SearchStrategy[KeyState] = st.one_of(_values.map(Present), st.just(ABSENT))


def _evaluate(
    block: Conditions,
    context: Mapping[str, KeyState],
    mode: ConditionMode,
    supported: frozenset[str] | None,
) -> ConditionEvaluation:
    return evaluate_conditions(block, context, mode=mode, supported_keys=supported)


@settings(max_examples=2000, deadline=None)
@given(
    block=_blocks(),
    known=st.fixed_dictionaries(dict.fromkeys(KEYS, _known_states)),
    unknown_keys=st.sets(st.sampled_from(KEYS)),
    completions=st.lists(
        st.fixed_dictionaries(dict.fromkeys(KEYS, _known_states)), min_size=1, max_size=6
    ),
    mode=st.sampled_from(list(ConditionMode)),
    supported=st.one_of(st.none(), st.sets(st.sampled_from(KEYS)).map(frozenset)),
)
def test_unknown_keys_never_become_a_definite_result_unless_every_completion_agrees(
    block: Conditions,
    known: dict[str, KeyState],
    unknown_keys: set[str],
    completions: list[dict[str, KeyState]],
    mode: ConditionMode,
    supported: frozenset[str] | None,
) -> None:
    partial: dict[str, KeyState] = {
        key: (UNKNOWN if key in unknown_keys else state) for key, state in known.items()
    }
    result = _evaluate(block, partial, mode, supported)
    if result.truth is ConditionTruth.UNRESOLVED:
        return
    for completion in completions:
        full = {
            key: (completion[key] if key in unknown_keys else state) for key, state in known.items()
        }
        assert _evaluate(block, full, mode, supported).truth is result.truth, (
            block,
            partial,
            full,
        )


@settings(max_examples=500, deadline=None)
@given(
    operator=st.sampled_from([name for names, _ in _FAMILIES for name in names]),
    qualifier=st.sampled_from(["", "ForAllValues:", "ForAnyValue:"]),
    suffix=st.sampled_from(["", "IfExists"]),
    policy_values=st.lists(st.text(max_size=12), max_size=3),
    context_values=st.lists(st.text(max_size=12), max_size=3),
    mode=st.sampled_from(list(ConditionMode)),
)
def test_arbitrary_text_never_raises_and_always_yields_a_truth(
    operator: str,
    qualifier: str,
    suffix: str,
    policy_values: list[str],
    context_values: list[str],
    mode: ConditionMode,
) -> None:
    result = evaluate_conditions(
        {f"{qualifier}{operator}{suffix}": {"k": policy_values}},
        {"k": Present(tuple(context_values))},
        mode=mode,
    )
    assert isinstance(result.truth, ConditionTruth)


# ---- regressions that fail on the old "not in map means absent" evaluator


def _single(operator: str, values: list[str], state: KeyState | None = None) -> ConditionEvaluation:
    context: dict[str, KeyState] = {} if state is None else {"k": state}
    return evaluate_conditions({operator: {"k": values}}, context, mode=ConditionMode.CONCRETE)


def test_if_exists_on_an_unknown_key_is_unresolved() -> None:
    result = _single("StringEqualsIfExists", ["prod"])
    assert result.truth is ConditionTruth.UNRESOLVED
    assert result.unresolved_keys == ("k",)


@pytest.mark.parametrize("wanted", ["true", "false"])
def test_null_on_an_unknown_key_is_unresolved(wanted: str) -> None:
    assert _single("Null", [wanted]).truth is ConditionTruth.UNRESOLVED
    assert _single("Null", [wanted], UNKNOWN).truth is ConditionTruth.UNRESOLVED


def test_unmapped_key_is_unknown_not_absent() -> None:
    assert _single("StringNotEquals", ["x"]).truth is ConditionTruth.UNRESOLVED
    assert _single("StringNotEquals", ["x"], ABSENT).truth is ConditionTruth.TRUE


def test_negated_dead_key_no_longer_forces_false() -> None:
    # An undocumented key is never sent, so it is Absent: a negated operator is TRUE for an
    # absent key (AWS condition-operators page), not FALSE.
    result = evaluate_conditions(
        {"StringNotEquals": {"head_ref": ["x"]}},
        {},
        mode=ConditionMode.CONCRETE,
        supported_keys=frozenset({"sub"}),
    )
    assert result.truth is ConditionTruth.TRUE
    assert result.dead_keys == ("head_ref",)


@pytest.mark.parametrize(
    ("block", "truth"),
    [
        ({"StringEqualsIfExists": {"head_ref": ["x"]}}, ConditionTruth.TRUE),
        ({"Null": {"head_ref": ["true"]}}, ConditionTruth.TRUE),
        ({"Null": {"head_ref": ["false"]}}, ConditionTruth.FALSE),
        ({"ForAllValues:StringEquals": {"head_ref": ["x"]}}, ConditionTruth.TRUE),
        ({"StringEquals": {"head_ref": ["x"]}}, ConditionTruth.FALSE),
    ],
)
def test_dead_key_follows_absent_key_rules(block: dict[str, Any], truth: ConditionTruth) -> None:
    result = evaluate_conditions(
        block,
        {"head_ref": Present(("x",))},
        mode=ConditionMode.CONCRETE,
        supported_keys=frozenset({"sub"}),
    )
    assert result.truth is truth
    assert result.dead_keys == ("head_ref",)


def test_dead_keys_are_reported_even_when_the_block_is_not_false() -> None:
    result = evaluate_conditions(
        {"StringNotEquals": {"head_ref": ["x"]}, "StringEquals": {"sub": ["s"]}},
        {"sub": Present(("s",))},
        mode=ConditionMode.CONCRETE,
        supported_keys=frozenset({"sub"}),
    )
    assert result.truth is ConditionTruth.TRUE
    assert result.dead_keys == ("head_ref",)


def test_block_combination_is_kleene_and() -> None:
    context: dict[str, KeyState] = {"a": Present(("1",)), "b": UNKNOWN}
    unresolved_only = evaluate_conditions(
        {"StringEquals": {"a": ["1"], "b": ["x"]}}, context, mode=ConditionMode.CONCRETE
    )
    assert unresolved_only.truth is ConditionTruth.UNRESOLVED
    false_wins = evaluate_conditions(
        {"StringEquals": {"a": ["2"], "b": ["x"]}}, context, mode=ConditionMode.CONCRETE
    )
    assert false_wins.truth is ConditionTruth.FALSE


def test_legacy_frozenset_context_still_means_present() -> None:
    assert (
        evaluate_conditions(
            {"StringEquals": {"k": ["a"]}}, {"k": frozenset({"a"})}, mode=ConditionMode.CONCRETE
        ).truth
        is ConditionTruth.TRUE
    )
    assert (
        evaluate_conditions(
            {"StringEquals": {"k": ["a"]}},
            {"other": frozenset({"a"})},
            mode=ConditionMode.CONCRETE,
        ).truth
        is ConditionTruth.UNRESOLVED
    )


def test_candidate_mode_negated_operator_stays_unresolved_for_present_candidates() -> None:
    result = evaluate_conditions(
        {"StringNotLike": {"sub": ["repo:acme/*"]}},
        {"sub": Present(("repo:acme/shop:ref:refs/heads/*",))},
        mode=ConditionMode.CANDIDATE,
    )
    assert result.truth is ConditionTruth.UNRESOLVED


def test_candidate_mode_non_string_operator_on_a_glob_is_unresolved() -> None:
    result = evaluate_conditions(
        {"IpAddress": {"k": ["10.0.0.0/8"]}},
        {"k": Present(("10.*",))},
        mode=ConditionMode.CANDIDATE,
    )
    assert result.truth is ConditionTruth.UNRESOLVED


# ---- effect of an UNRESOLVED trust condition


def _trust(conditions: dict[str, dict[str, list[str]]]) -> Any:
    registry = condition_keys()
    trust = role(statements=(statement(actions=(ASSUME_ACTION,), conditions=conditions),))
    return evaluate_trust_statements(trust, [candidate(SUB_MAIN)], registry=registry)


def test_trust_if_exists_on_an_unprovided_claim_is_a_conditional_match() -> None:
    evaluation = _trust(
        {
            "StringEquals": {"sub": [SUB_MAIN]},
            "StringEqualsIfExists": {"environment": ["prod"]},
        }
    )
    assert len(evaluation.matches) == 1
    assert evaluation.matches[0].truth is ConditionTruth.UNRESOLVED
    assert evaluation.matches[0].conditional
    assert evaluation.matches[0].unresolved_keys == ("environment",)


def test_trust_null_on_an_unprovided_claim_is_a_conditional_match() -> None:
    evaluation = _trust({"StringEquals": {"sub": [SUB_MAIN]}, "Null": {"environment": ["true"]}})
    assert len(evaluation.matches) == 1
    assert evaluation.matches[0].conditional


def test_trust_definite_claims_remain_unconditional() -> None:
    evaluation = _trust({"StringEquals": {"sub": [SUB_MAIN]}})
    assert len(evaluation.matches) == 1
    assert not evaluation.matches[0].conditional
