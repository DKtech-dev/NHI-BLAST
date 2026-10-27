"""IAM condition evaluation (spec 9.3).

Evaluation returns TRUE, FALSE or UNRESOLVED. UNRESOLVED means the analysis cannot
decide with the facts available (unknown key, policy variable, unsupported
operator family, or a negative operator against a candidate glob); a statement with
any UNRESOLVED condition is conditional rather than certain.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from nhi_blast.aws.glob import glob_intersects, glob_match

POLICY_VARIABLE = "${"


class ConditionMode(StrEnum):
    CONCRETE = "concrete"
    CANDIDATE = "candidate"


class ConditionTruth(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    truth: ConditionTruth
    reasons: tuple[str, ...] = ()
    unresolved_keys: tuple[str, ...] = ()
    dead_keys: tuple[str, ...] = ()


_EXACT = frozenset({"StringEquals", "ArnEquals"})
_EXACT_IGNORE_CASE = frozenset({"StringEqualsIgnoreCase"})
_LIKE = frozenset({"StringLike", "ArnLike"})
_NEGATIVE = frozenset(
    {
        "StringNotEquals",
        "StringNotEqualsIgnoreCase",
        "StringNotLike",
        "ArnNotEquals",
        "ArnNotLike",
    }
)
_BOOL = frozenset({"Bool"})
_NULL = frozenset({"Null"})
_UNSUPPORTED_PREFIXES = ("Numeric", "Date", "IpAddress", "Binary")
_QUALIFIERS = ("ForAnyValue:", "ForAllValues:")


def _split_operator(raw: str) -> tuple[str | None, str, bool]:
    qualifier: str | None = None
    operator = raw.strip()
    for prefix in _QUALIFIERS:
        if operator.startswith(prefix):
            qualifier = prefix[:-1]
            operator = operator[len(prefix) :]
            break
    if_exists = False
    if operator.endswith("IfExists"):
        if_exists = True
        operator = operator[: -len("IfExists")]
    return qualifier, operator, if_exists


def _values(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, Sequence):
        return tuple(str(item) for item in raw)
    return (str(raw),)


def _pair_matches(
    operator: str, policy_value: str, context_value: str, mode: ConditionMode
) -> bool:
    if mode is ConditionMode.CANDIDATE:
        if operator in _EXACT_IGNORE_CASE:
            return glob_intersects(policy_value, context_value, fold=True)
        return glob_intersects(policy_value, context_value)
    if operator in _EXACT:
        return policy_value == context_value
    if operator in _EXACT_IGNORE_CASE:
        return policy_value.lower() == context_value.lower()
    if operator in _LIKE:
        return glob_match(policy_value, context_value)
    return False


def _positive_truth(
    operator: str,
    qualifier: str | None,
    policy_values: tuple[str, ...],
    context_values: tuple[str, ...],
    mode: ConditionMode,
) -> ConditionTruth:
    if not context_values:
        return ConditionTruth.UNRESOLVED
    outcomes = [
        any(
            _pair_matches(operator, policy_value, context_value, mode)
            for policy_value in policy_values
        )
        for context_value in context_values
    ]
    if qualifier == "ForAllValues":
        if all(outcomes):
            return ConditionTruth.TRUE
    elif any(outcomes):
        return ConditionTruth.TRUE
    return ConditionTruth.FALSE


_FILTERABLE_OPERATORS = _EXACT | _EXACT_IGNORE_CASE | _LIKE


def required_positive_patterns(
    conditions: Mapping[str, Mapping[str, Sequence[str]]], key: str
) -> tuple[str, ...] | None:
    """Positive string patterns every matching context must satisfy for ``key``.

    Returns ``None`` when the block cannot be pre-filtered: the key is absent, an
    operator is negative or unsupported, or a pattern contains a policy variable.
    A non-empty result is a necessary condition, not a decision.
    """
    patterns: list[str] = []
    saw_key = False
    for operator_raw, key_map in conditions.items():
        _, operator, _ = _split_operator(operator_raw)
        for raw_key, expected in key_map.items():
            if str(raw_key).strip() != key:
                continue
            saw_key = True
            if operator not in _FILTERABLE_OPERATORS:
                return None
            values = _values(expected)
            if any(POLICY_VARIABLE in value for value in values):
                return None
            patterns.extend(values)
    if not saw_key:
        return None
    return tuple(patterns)


def _evaluate_key(
    key: str,
    operator_raw: str,
    expected: object,
    context: Mapping[str, frozenset[str]],
    *,
    mode: ConditionMode,
) -> tuple[ConditionTruth, str]:
    qualifier, operator, if_exists = _split_operator(operator_raw)
    policy_values = _values(expected)
    present = key in context
    if if_exists and not present:
        return ConditionTruth.TRUE, f"{key} absent and IfExists applies"
    if operator in _NULL:
        wants_absent = [value.strip().lower() in {"true", "1"} for value in policy_values]
        result = all(wants_absent) if qualifier == "ForAllValues" else any(wants_absent)
        absent = not present or not context[key]
        return (
            ConditionTruth.TRUE if result == absent else ConditionTruth.FALSE,
            f"Null({key}) {'absent' if wants_absent else 'present'}",
        )
    if any(POLICY_VARIABLE in value for value in policy_values):
        return ConditionTruth.UNRESOLVED, f"{key} uses a policy variable"
    if operator in _BOOL:
        if not present:
            return ConditionTruth.UNRESOLVED, f"{key} not available in context"
        expected_bool = policy_values[0].strip().lower() in {"true", "1"}
        actual = [value.strip().lower() in {"true", "1"} for value in context[key]]
        matched = any(value is expected_bool for value in actual)
        return (
            ConditionTruth.TRUE if matched else ConditionTruth.FALSE,
            f"Bool({key})",
        )
    if any(operator.startswith(prefix) for prefix in _UNSUPPORTED_PREFIXES):
        return ConditionTruth.UNRESOLVED, f"{operator} is not evaluated"
    if operator in _NEGATIVE:
        if mode is ConditionMode.CANDIDATE:
            return (
                ConditionTruth.UNRESOLVED,
                f"negative operator {operator} against a candidate glob",
            )
        positive = operator.replace("Not", "", 1)
        truth = _positive_truth(
            positive, qualifier, policy_values, tuple(context.get(key, frozenset())), mode
        )
        if truth is ConditionTruth.UNRESOLVED:
            return truth, f"{operator}({key}) undecidable"
        return (
            ConditionTruth.FALSE if truth is ConditionTruth.TRUE else ConditionTruth.TRUE,
            f"{operator}({key})",
        )
    if operator in _EXACT or operator in _EXACT_IGNORE_CASE or operator in _LIKE:
        if not present:
            return ConditionTruth.UNRESOLVED, f"{key} not available in context"
        truth = _positive_truth(operator, qualifier, policy_values, tuple(context[key]), mode)
        return truth, f"{operator}({key}) {truth.value.lower()}"
    return ConditionTruth.UNRESOLVED, f"operator {operator} is not evaluated"


def evaluate_conditions(
    conditions: Mapping[str, Mapping[str, Sequence[str]]],
    context: Mapping[str, frozenset[str]],
    *,
    mode: ConditionMode,
    supported_keys: frozenset[str] | None = None,
) -> ConditionEvaluation:
    """Evaluate a condition block; every condition must be TRUE for the block."""
    dead: list[str] = []
    unresolved: list[str] = []
    reasons: list[str] = []
    saw_false = False
    for operator_raw, key_map in conditions.items():
        for raw_key, expected in key_map.items():
            key = str(raw_key).strip()
            if supported_keys is not None and key not in supported_keys:
                dead.append(key)
                reasons.append(f"{key} is not a documented AWS condition key for this provider")
                continue
            truth, reason = _evaluate_key(key, str(operator_raw), expected, context, mode=mode)
            reasons.append(reason)
            if truth is ConditionTruth.FALSE:
                saw_false = True
            elif truth is ConditionTruth.UNRESOLVED:
                unresolved.append(key)
    if dead:
        return ConditionEvaluation(
            truth=ConditionTruth.FALSE,
            reasons=tuple(reasons),
            unresolved_keys=tuple(sorted(set(unresolved))),
            dead_keys=tuple(sorted(set(dead))),
        )
    if saw_false:
        return ConditionEvaluation(
            truth=ConditionTruth.FALSE,
            reasons=tuple(reasons),
            unresolved_keys=tuple(sorted(set(unresolved))),
            dead_keys=(),
        )
    if unresolved:
        return ConditionEvaluation(
            truth=ConditionTruth.UNRESOLVED,
            reasons=tuple(reasons),
            unresolved_keys=tuple(sorted(set(unresolved))),
            dead_keys=(),
        )
    return ConditionEvaluation(truth=ConditionTruth.TRUE, reasons=tuple(reasons))
