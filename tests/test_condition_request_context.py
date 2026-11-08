"""A provider-claim registry is not a closed world for AWS request context keys."""

from __future__ import annotations

import pytest

from nhi_blast.aws.conditions import (
    ABSENT,
    ConditionMode,
    ConditionTruth,
    Present,
    evaluate_conditions,
)


@pytest.mark.parametrize("key", ["aws:SourceIp", "aws:TokenIssueTime", "sts:SourceIdentity"])
@pytest.mark.parametrize("operator", ["StringNotEquals", "StringEqualsIfExists", "Null"])
def test_unavailable_request_key_remains_unknown_outside_provider_claim_registry(
    key: str, operator: str
) -> None:
    values = ["false"] if operator == "Null" else ["203.0.113.5"]
    result = evaluate_conditions(
        {operator: {key: values}},
        {},
        mode=ConditionMode.CONCRETE,
        supported_keys=frozenset({"sub", "aud"}),
    )
    assert result.truth is ConditionTruth.UNRESOLVED
    assert key in result.unresolved_keys
    assert key not in result.dead_keys


@pytest.mark.parametrize(
    ("value", "expected"),
    [("203.0.113.5", ConditionTruth.TRUE), ("198.51.100.8", ConditionTruth.FALSE)],
)
def test_present_request_context_is_evaluated_independently_of_provider_registry(
    value: str, expected: ConditionTruth
) -> None:
    result = evaluate_conditions(
        {"StringEquals": {"aws:SourceIp": ["203.0.113.5"]}},
        {"aws:SourceIp": Present((value,))},
        mode=ConditionMode.CONCRETE,
        supported_keys=frozenset({"sub", "aud"}),
    )
    assert result.truth is expected
    assert result.dead_keys == ()


def test_explicitly_absent_request_context_preserves_ifexists_semantics() -> None:
    result = evaluate_conditions(
        {"StringEqualsIfExists": {"aws:SourceIp": ["203.0.113.5"]}},
        {"aws:SourceIp": ABSENT},
        mode=ConditionMode.CONCRETE,
        supported_keys=frozenset({"sub", "aud"}),
    )
    assert result.truth is ConditionTruth.TRUE
