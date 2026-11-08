"""IAM condition evaluation (spec 9.3).

Evaluation returns TRUE, FALSE or UNRESOLVED. Every request-context key is in one of
three states: ``Present`` (with its value set; an empty set is a null dataset),
``Absent`` (the key is known never to be sent for this request) or ``Unknown`` (the offline
analyser has no information). Unknown information never becomes a definite TRUE/FALSE:
the result is only definite when every completion of the unknown keys (each replaced by
Present(any values) or Absent) would give the same answer.

Semantics follow the AWS IAM pages "IAM JSON policy elements: Condition operators"
(reference_policies_elements_condition_operators) and "Multivalued context keys"
(reference_policies_condition-single-vs-multi-valued-context-keys). A request value
"matches" when some policy value matches it; a negated operator is satisfied when no
request value matches any policy value. Reasons carry a diagnostic code where the
outcome is a data problem rather than a missing fact:

- D-COND-UNSUPPORTED-OP: operator name is not implemented
- D-COND-MALFORMED: a policy or context value cannot be parsed for the operator
- D-COND-POLICY-VARIABLE: a policy variable needs run-time values
- D-COND-AMBIGUOUS: the AWS documents can be read to give opposite answers
- D-COND-UNKNOWN-KEY: the key is not known to the offline analyser
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from nhi_blast.aws.glob import glob_intersects, glob_match, has_wildcard

POLICY_VARIABLE = "${"

CODE_UNSUPPORTED_OP = "D-COND-UNSUPPORTED-OP"
CODE_MALFORMED = "D-COND-MALFORMED"
CODE_POLICY_VARIABLE = "D-COND-POLICY-VARIABLE"
CODE_AMBIGUOUS = "D-COND-AMBIGUOUS"
CODE_UNKNOWN_KEY = "D-COND-UNKNOWN-KEY"


class ConditionMode(StrEnum):
    CONCRETE = "concrete"
    CANDIDATE = "candidate"


class ConditionTruth(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class Present:
    """Key is sent with these values; an empty tuple is a null dataset."""

    values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Absent:
    """Key is documented as never sent for this request."""


@dataclass(frozen=True, slots=True)
class Unknown:
    """The offline analyser has no information about this key."""


KeyState = Present | Absent | Unknown
ABSENT = Absent()
UNKNOWN = Unknown()


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    truth: ConditionTruth
    reasons: tuple[str, ...] = ()
    unresolved_keys: tuple[str, ...] = ()
    dead_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _Operator:
    family: str
    relation: str
    negated: bool = False


_OPERATORS: dict[str, _Operator] = {
    "StringEquals": _Operator("string", "eq"),
    "StringNotEquals": _Operator("string", "eq", negated=True),
    "StringEqualsIgnoreCase": _Operator("string", "fold"),
    "StringNotEqualsIgnoreCase": _Operator("string", "fold", negated=True),
    "StringLike": _Operator("string", "like"),
    "StringNotLike": _Operator("string", "like", negated=True),
    "NumericEquals": _Operator("numeric", "eq"),
    "NumericNotEquals": _Operator("numeric", "eq", negated=True),
    "NumericLessThan": _Operator("numeric", "lt"),
    "NumericLessThanEquals": _Operator("numeric", "le"),
    "NumericGreaterThan": _Operator("numeric", "gt"),
    "NumericGreaterThanEquals": _Operator("numeric", "ge"),
    "DateEquals": _Operator("date", "eq"),
    "DateNotEquals": _Operator("date", "eq", negated=True),
    "DateLessThan": _Operator("date", "lt"),
    "DateLessThanEquals": _Operator("date", "le"),
    "DateGreaterThan": _Operator("date", "gt"),
    "DateGreaterThanEquals": _Operator("date", "ge"),
    "Bool": _Operator("bool", "eq"),
    "BinaryEquals": _Operator("binary", "eq"),
    "IpAddress": _Operator("ip", "eq"),
    "NotIpAddress": _Operator("ip", "eq", negated=True),
    "ArnEquals": _Operator("arn", "eq"),
    "ArnLike": _Operator("arn", "like"),
    "ArnNotEquals": _Operator("arn", "eq", negated=True),
    "ArnNotLike": _Operator("arn", "like", negated=True),
}
_GLOB_FAMILIES = frozenset({"string", "arn"})
_NULL = "Null"
_FOR_ALL = "ForAllValues"
_FOR_ANY = "ForAnyValue"
_QUALIFIERS = (f"{_FOR_ANY}:", f"{_FOR_ALL}:")
_ARN_COMPONENTS = 6

_NUMBER = re.compile(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", re.ASCII)
_EPOCH = re.compile(r"\d+(\.\d+)?", re.ASCII)
_ISO_8601 = re.compile(
    r"(\d{4})-(\d{2})(?:-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?(Z|[+-]\d{2}:\d{2}))?)?",
    re.ASCII,
)
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class _MalformedError(ValueError):
    """A policy or context value cannot be parsed for its operator."""


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


def _shown(value: str) -> str:
    return repr(value if len(value) <= 40 else value[:37] + "...")


def _parse_number(value: str) -> Decimal:
    if _NUMBER.fullmatch(value) is None:
        message = f"{_shown(value)} is not a number"
        raise _MalformedError(message)
    try:
        return Decimal(value)
    except InvalidOperation as error:
        message = f"{_shown(value)} is not a representable number"
        raise _MalformedError(message) from error


def _iso_seconds(value: str) -> Decimal | None:
    parts = _ISO_8601.fullmatch(value)
    if parts is None:
        return None
    year, month, day, hour, minute, second, fraction, zone = parts.groups()
    offset = timedelta(0)
    if zone is not None and zone != "Z":
        sign = -1 if zone[0] == "-" else 1
        offset = sign * timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
    try:
        moment = datetime(
            int(year),
            int(month),
            int(day or 1),
            int(hour or 0),
            int(minute or 0),
            int(second or 0),
            tzinfo=timezone(offset),
        )
    except (ValueError, OverflowError) as error:
        message = f"{_shown(value)} is not a valid date"
        raise _MalformedError(message) from error
    delta = moment - _UNIX_EPOCH
    seconds = Decimal(delta.days * 86400 + delta.seconds)
    return seconds + Decimal(f"0.{fraction}") if fraction else seconds


def _parse_date(value: str) -> Decimal:
    if _EPOCH.fullmatch(value) is not None:
        return Decimal(value)
    seconds = _iso_seconds(value)
    if seconds is None:
        message = f"{_shown(value)} is neither W3C ISO 8601 nor epoch seconds"
        raise _MalformedError(message)
    return seconds


def _parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered not in {"true", "false"}:
        message = f"{_shown(value)} is not true or false"
        raise _MalformedError(message)
    return lowered == "true"


def _parse_binary(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        message = f"{_shown(value)} is not valid base64"
        raise _MalformedError(message) from error


def _parse_network(value: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    try:
        return ipaddress.ip_network(value, strict=False)
    except ValueError as error:
        message = f"{_shown(value)} is not an IP address or CIDR block"
        raise _MalformedError(message) from error


def _parse_address(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        return ipaddress.ip_address(value)
    except ValueError as error:
        message = f"{_shown(value)} is not an IP address"
        raise _MalformedError(message) from error


_Parsed = (
    str
    | Decimal
    | bool
    | bytes
    | ipaddress.IPv4Network
    | ipaddress.IPv6Network
    | ipaddress.IPv4Address
    | ipaddress.IPv6Address
)


def _parse_policy_value(spec: _Operator, value: str) -> _Parsed:
    if spec.family == "numeric":
        return _parse_number(value)
    if spec.family == "date":
        return _parse_date(value)
    if spec.family == "bool":
        return _parse_bool(value)
    if spec.family == "binary":
        return _parse_binary(value)
    if spec.family == "ip":
        return _parse_network(value)
    return value


def _parse_context_value(spec: _Operator, value: str) -> _Parsed:
    if spec.family == "ip":
        return _parse_address(value)
    return _parse_policy_value(spec, value)


def _prepare_policy(
    spec: _Operator, policy_values: tuple[str, ...]
) -> tuple[tuple[_Parsed, ...], bool]:
    parsed: list[_Parsed] = []
    has_variable = False
    for value in policy_values:
        if POLICY_VARIABLE in value:
            if spec.family in {"bool", "binary"}:
                message = f"policy variables are not allowed for {spec.family} values"
                raise _MalformedError(message)
            has_variable = True
            continue
        parsed.append(_parse_policy_value(spec, value))
    return tuple(parsed), has_variable


def _arn_match(pattern: str, value: str) -> bool:
    pattern_parts = pattern.split(":", _ARN_COMPONENTS - 1)
    value_parts = value.split(":", _ARN_COMPONENTS - 1)
    if len(pattern_parts) == _ARN_COMPONENTS and len(value_parts) == _ARN_COMPONENTS:
        return all(glob_match(p, v) for p, v in zip(pattern_parts, value_parts, strict=True))
    return glob_match(pattern, value)


def _compare(relation: str, left: Decimal, right: Decimal) -> bool:
    if relation == "lt":
        return left < right
    if relation == "le":
        return left <= right
    if relation == "gt":
        return left > right
    if relation == "ge":
        return left >= right
    return left == right


def _string_pair_matches(
    spec: _Operator, policy_value: str, context_value: str, mode: ConditionMode
) -> bool:
    if mode is ConditionMode.CANDIDATE:
        return glob_intersects(policy_value, context_value, fold=spec.relation == "fold")
    if spec.family == "arn":
        return _arn_match(policy_value, context_value)
    if spec.relation == "fold":
        return policy_value.lower() == context_value.lower()
    if spec.relation == "like":
        return glob_match(policy_value, context_value)
    return policy_value == context_value


def _pair_matches(
    spec: _Operator, policy_value: _Parsed, context_value: _Parsed, mode: ConditionMode
) -> bool:
    if isinstance(policy_value, str) and isinstance(context_value, str):
        return _string_pair_matches(spec, policy_value, context_value, mode)
    if isinstance(policy_value, Decimal) and isinstance(context_value, Decimal):
        # Request value on the left: NumericLessThan 10 is satisfied by a request value < 10.
        return _compare(spec.relation, context_value, policy_value)
    if isinstance(policy_value, bool) and isinstance(context_value, bool):
        return policy_value is context_value
    if isinstance(policy_value, bytes) and isinstance(context_value, bytes):
        return policy_value == context_value
    if isinstance(policy_value, ipaddress.IPv4Network | ipaddress.IPv6Network) and isinstance(
        context_value, ipaddress.IPv4Address | ipaddress.IPv6Address
    ):
        return policy_value.version == context_value.version and context_value in policy_value
    return False


_FILTERABLE_OPERATORS = frozenset(
    name for name, spec in _OPERATORS.items() if spec.family in _GLOB_FAMILIES and not spec.negated
)


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


def _absent_truth(
    label: str, spec: _Operator, qualifier: str | None, if_exists: bool
) -> tuple[ConditionTruth, str]:
    if qualifier == _FOR_ANY and (spec.negated or if_exists):
        return (
            ConditionTruth.UNRESOLVED,
            f"{CODE_AMBIGUOUS}: {label} on an absent key; the AWS documents can be read both ways",
        )
    if if_exists or qualifier == _FOR_ALL:
        return ConditionTruth.TRUE, f"{label}: key absent, IfExists/ForAllValues is satisfied"
    if qualifier == _FOR_ANY:
        return ConditionTruth.FALSE, f"{label}: key absent, ForAnyValue has no value to match"
    if spec.negated:
        return ConditionTruth.TRUE, f"{label}: key absent, negated operator is satisfied"
    return ConditionTruth.FALSE, f"{label}: key absent, positive operator cannot match"


def _present_truth(
    label: str,
    spec: _Operator,
    qualifier: str | None,
    policy: tuple[_Parsed, ...],
    has_variable: bool,
    values: tuple[str, ...],
    mode: ConditionMode,
) -> tuple[ConditionTruth, str]:
    if not values:
        if qualifier == _FOR_ALL or (qualifier is None and spec.negated):
            return ConditionTruth.TRUE, f"{label}: null dataset is vacuously satisfied"
        return ConditionTruth.FALSE, f"{label}: null dataset has no value to match"
    if has_variable:
        return (
            ConditionTruth.UNRESOLVED,
            f"{CODE_POLICY_VARIABLE}: {label} uses a policy variable resolved at run time",
        )
    if mode is ConditionMode.CANDIDATE and spec.negated:
        return (
            ConditionTruth.UNRESOLVED,
            f"negative operator {label} against a candidate glob",
        )
    if (
        mode is ConditionMode.CANDIDATE
        and spec.family not in _GLOB_FAMILIES
        and any(has_wildcard(value) for value in values)
    ):
        return (
            ConditionTruth.UNRESOLVED,
            f"{label}: candidate glob cannot be compared as a {spec.family} value",
        )
    try:
        context_values = [_parse_context_value(spec, value) for value in values]
    except _MalformedError as error:
        return ConditionTruth.UNRESOLVED, f"{CODE_MALFORMED}: {label} context value {error}"
    satisfied = [
        any(_pair_matches(spec, item, value, mode) for item in policy) != spec.negated
        for value in context_values
    ]
    if qualifier == _FOR_ALL or (qualifier is None and spec.negated):
        outcome = all(satisfied)
    else:
        outcome = any(satisfied)
    truth = ConditionTruth.TRUE if outcome else ConditionTruth.FALSE
    return truth, f"{label} {truth.value.lower()}"


def _null_truth(
    label: str,
    qualifier: str | None,
    if_exists: bool,
    policy_values: tuple[str, ...],
    state: KeyState,
) -> tuple[ConditionTruth, str]:
    if qualifier is not None or if_exists:
        return (
            ConditionTruth.UNRESOLVED,
            f"{CODE_MALFORMED}: {label} Null cannot be combined with IfExists or a qualifier",
        )
    wanted: list[bool] = []
    for value in policy_values:
        lowered = value.lower()
        if lowered not in {"true", "false"}:
            return (
                ConditionTruth.UNRESOLVED,
                f"{CODE_MALFORMED}: {label} Null value {_shown(value)} is not true or false",
            )
        wanted.append(lowered == "true")
    if not wanted:
        return ConditionTruth.UNRESOLVED, f"{CODE_MALFORMED}: {label} Null has no value"
    if isinstance(state, Unknown):
        return ConditionTruth.UNRESOLVED, f"{CODE_UNKNOWN_KEY}: {label} key presence is unknown"
    if isinstance(state, Absent):
        truth = ConditionTruth.TRUE if any(wanted) else ConditionTruth.FALSE
        return truth, f"{label}: key absent"
    if not state.values:
        return (
            ConditionTruth.UNRESOLVED,
            f"{label}: key present with a null dataset; presence is not decidable",
        )
    truth = ConditionTruth.TRUE if any(not want for want in wanted) else ConditionTruth.FALSE
    return truth, f"{label}: key present"


def _evaluate_key(
    key: str,
    operator_raw: str,
    expected: object,
    state: KeyState,
    *,
    mode: ConditionMode,
) -> tuple[ConditionTruth, str]:
    qualifier, operator, if_exists = _split_operator(operator_raw)
    label = f"{operator_raw.strip()}({key})"
    policy_values = _values(expected)
    if operator == _NULL:
        return _null_truth(label, qualifier, if_exists, policy_values, state)
    spec = _OPERATORS.get(operator)
    if spec is None:
        return (
            ConditionTruth.UNRESOLVED,
            f"{CODE_UNSUPPORTED_OP}: operator {_shown(operator_raw.strip())} is not supported",
        )
    try:
        policy, has_variable = _prepare_policy(spec, policy_values)
    except _MalformedError as error:
        return ConditionTruth.UNRESOLVED, f"{CODE_MALFORMED}: {label} policy value {error}"
    if isinstance(state, Unknown):
        return ConditionTruth.UNRESOLVED, f"{CODE_UNKNOWN_KEY}: {key} not available in context"
    if isinstance(state, Absent):
        return _absent_truth(label, spec, qualifier, if_exists)
    return _present_truth(label, spec, qualifier, policy, has_variable, state.values, mode)


def is_request_context_key(key: str) -> bool:
    """Namespaced request keys are not normalized OIDC-provider claims.

    A provider claim allowlist cannot establish absence of AWS global or service
    request context; use supplied state, or Unknown when it is unavailable offline.
    """
    return ":" in key


def _coerce_state(raw: KeyState | frozenset[str] | None) -> KeyState:
    """Adapt legacy ``frozenset`` contexts: in the map means Present, not in the map Unknown."""
    if raw is None:
        return UNKNOWN
    if isinstance(raw, frozenset):
        return Present(tuple(sorted(raw)))
    return raw


def evaluate_conditions(
    conditions: Mapping[str, Mapping[str, Sequence[str]]],
    context: Mapping[str, KeyState | frozenset[str]],
    *,
    mode: ConditionMode,
    supported_keys: frozenset[str] | None = None,
) -> ConditionEvaluation:
    """Evaluate a condition block with Kleene AND: FALSE, then UNRESOLVED, then TRUE.

    Normalized provider claims outside ``supported_keys`` are treated as unavailable
    from that provider and reported in ``dead_keys``. Namespaced AWS/service request
    keys are outside this claim allowlist: missing offline information stays Unknown.
    """
    dead: list[str] = []
    unresolved: list[str] = []
    reasons: list[str] = []
    saw_false = False
    for operator_raw, key_map in conditions.items():
        for raw_key, expected in key_map.items():
            key = str(raw_key).strip()
            if (
                supported_keys is not None
                and key not in supported_keys
                and not is_request_context_key(key)
            ):
                dead.append(key)
                reasons.append(f"{key} is not a documented AWS condition key for this provider")
                state: KeyState = ABSENT
            else:
                state = _coerce_state(context.get(key))
            truth, reason = _evaluate_key(key, str(operator_raw), expected, state, mode=mode)
            reasons.append(reason)
            if truth is ConditionTruth.FALSE:
                saw_false = True
            elif truth is ConditionTruth.UNRESOLVED:
                unresolved.append(key)
    if saw_false:
        overall = ConditionTruth.FALSE
    elif unresolved:
        overall = ConditionTruth.UNRESOLVED
    else:
        overall = ConditionTruth.TRUE
    return ConditionEvaluation(
        truth=overall,
        reasons=tuple(reasons),
        unresolved_keys=tuple(sorted(set(unresolved))),
        dead_keys=tuple(sorted(set(dead))),
    )
