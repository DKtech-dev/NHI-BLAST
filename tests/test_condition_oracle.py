"""Hand-written AWS condition vectors (one per truth-table cell and malformed case).

The vectors live in tests/oracles/aws_conditions.json and cite the two AWS IAM pages the
semantics are taken from. The evaluator must agree with every vector exactly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nhi_blast.aws.conditions import (
    ABSENT,
    UNKNOWN,
    ConditionMode,
    ConditionTruth,
    KeyState,
    Present,
    evaluate_conditions,
)

ORACLE = Path(__file__).parent / "oracles" / "aws_conditions.json"
ALLOWED_SOURCES = {
    "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition_operators.html",
    "https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-single-vs-multi-valued-context-keys.html",
}
SUPPORTED_OPERATORS = frozenset(
    {
        "StringEquals",
        "StringNotEquals",
        "StringEqualsIgnoreCase",
        "StringNotEqualsIgnoreCase",
        "StringLike",
        "StringNotLike",
        "NumericEquals",
        "NumericNotEquals",
        "NumericLessThan",
        "NumericLessThanEquals",
        "NumericGreaterThan",
        "NumericGreaterThanEquals",
        "DateEquals",
        "DateNotEquals",
        "DateLessThan",
        "DateLessThanEquals",
        "DateGreaterThan",
        "DateGreaterThanEquals",
        "Bool",
        "BinaryEquals",
        "IpAddress",
        "NotIpAddress",
        "ArnEquals",
        "ArnLike",
        "ArnNotEquals",
        "ArnNotLike",
        "Null",
    }
)


def _vectors() -> list[dict[str, Any]]:
    loaded = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    return loaded


def _state(spec: dict[str, Any]) -> KeyState:
    kind = spec["state"]
    if kind == "present":
        return Present(tuple(spec["values"]))
    if kind == "absent":
        return ABSENT
    assert kind == "unknown"
    return UNKNOWN


def _base_operator(name: str) -> str:
    for prefix in ("ForAllValues:", "ForAnyValue:"):
        name = name.removeprefix(prefix)
    return name.removesuffix("IfExists")


def _prefix(operator: str) -> str:
    for prefix in ("ForAllValues:", "ForAnyValue:"):
        if operator.startswith(prefix):
            return prefix
    return "IfExists" if operator.endswith("IfExists") else ""


VECTORS = _vectors()


@pytest.mark.parametrize(
    "vector",
    VECTORS,
    ids=[
        f"{index}-{vector['operator']}-{vector['context']['k']['state']}"
        for index, vector in enumerate(VECTORS)
    ],
)
def test_vector_agrees_with_oracle(vector: dict[str, Any]) -> None:
    context = {key: _state(spec) for key, spec in vector["context"].items()}
    result = evaluate_conditions(
        {vector["operator"]: {"k": vector["policy_values"]}},
        context,
        mode=ConditionMode.CONCRETE,
    )
    assert result.truth is ConditionTruth(vector["expected"]), (vector, result.reasons)
    code = vector.get("reason_code")
    if code is not None:
        assert any(code in reason for reason in result.reasons), (vector, result.reasons)


def test_every_vector_cites_an_allowed_aws_page() -> None:
    for vector in VECTORS:
        assert vector["source_url"] in ALLOWED_SOURCES, vector
        assert vector["expected"] in {"TRUE", "FALSE", "UNRESOLVED"}
        assert vector["context"]["k"]["state"] in {"present", "absent", "unknown"}


def test_every_supported_operator_has_oracle_vectors_in_every_key_state() -> None:
    seen: dict[str, set[str]] = {}
    for vector in VECTORS:
        seen.setdefault(_base_operator(vector["operator"]), set()).add(
            vector["context"]["k"]["state"]
        )
    for operator in SUPPORTED_OPERATORS:
        assert seen.get(operator, set()) >= {"present", "absent", "unknown"}, operator


def test_every_truth_table_cell_for_the_string_family_is_covered() -> None:
    cells = {
        (_prefix(vector["operator"]), vector["context"]["k"]["state"], vector["expected"])
        for vector in VECTORS
        if _base_operator(vector["operator"]) in {"StringEquals", "StringNotEquals"}
    }
    required = {
        ("", "present", "TRUE"),
        ("", "present", "FALSE"),
        ("", "absent", "TRUE"),
        ("", "absent", "FALSE"),
        ("", "unknown", "UNRESOLVED"),
        ("IfExists", "absent", "TRUE"),
        ("IfExists", "unknown", "UNRESOLVED"),
        ("ForAllValues:", "present", "TRUE"),
        ("ForAllValues:", "present", "FALSE"),
        ("ForAllValues:", "absent", "TRUE"),
        ("ForAnyValue:", "present", "TRUE"),
        ("ForAnyValue:", "present", "FALSE"),
        ("ForAnyValue:", "absent", "FALSE"),
        ("ForAnyValue:", "absent", "UNRESOLVED"),
    }
    assert required <= cells
