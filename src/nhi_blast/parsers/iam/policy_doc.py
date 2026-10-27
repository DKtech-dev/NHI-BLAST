"""IAM policy document parsing and normalisation (spec 9.1, 6.1).

Accepts raw policy documents, get-policy output, get-role-policy output and aws iam
get-role output. Scalars are normalised to tuples; action names are compared
case-insensitively later, so they are kept as written here.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from nhi_blast.core.diagnostics import Diagnostic, error, warning
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.models import PolicyEffect, Statement
from nhi_blast.parsers.terraform.facts import IamDocumentFact


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence):
        return tuple(str(item) for item in value if item is not None)
    return (str(value),)


def _line_index(text: str) -> dict[str, list[int]]:
    """Map key names to the 1-based lines where they appear as JSON keys."""
    index: dict[str, list[int]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith('"'):
            continue
        end = stripped.find('"', 1)
        if end <= 1:
            continue
        key = stripped[1:end]
        index.setdefault(key, []).append(number)
    return index


def _conditions(raw: Any) -> dict[str, dict[str, tuple[str, ...]]]:
    result: dict[str, dict[str, tuple[str, ...]]] = {}
    if not isinstance(raw, Mapping):
        return result
    for operator, key_map in raw.items():
        if not isinstance(key_map, Mapping):
            continue
        result[str(operator)] = {str(key): _as_tuple(value) for key, value in key_map.items()}
    return result


def _principals(raw: Any) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    if not isinstance(raw, Mapping):
        return result
    for principal_type, value in raw.items():
        result[str(principal_type)] = _as_tuple(value)
    return result


def _statement(
    raw: Mapping[str, Any],
    *,
    file: str,
    line: int | None,
    rule: str,
    detail: str,
) -> Statement | None:
    effect_raw = str(raw.get("Effect", "")).strip().lower()
    if effect_raw not in {"allow", "deny"}:
        return None
    effect = PolicyEffect.ALLOW if effect_raw == "allow" else PolicyEffect.DENY
    sid = raw.get("Sid")
    return Statement(
        effect=effect,
        actions=_as_tuple(raw.get("Action")),
        not_actions=_as_tuple(raw.get("NotAction")),
        resources=_as_tuple(raw.get("Resource")),
        not_resources=_as_tuple(raw.get("NotResource")),
        principals=_principals(raw.get("Principal")),
        conditions=_conditions(raw.get("Condition")),
        sid=str(sid) if sid is not None else None,
        evidence=(
            Evidence(
                cls=EvidenceClass.DECLARED,
                rule=rule,
                file=file,
                line=line,
                detail=detail,
            ),
        ),
    )


def statements_from_policy_object(
    document: Mapping[str, Any],
    *,
    file: str,
    line: int | None,
    rule: str,
    detail: str,
) -> tuple[Statement, ...]:
    raw_statements = document.get("Statement")
    if raw_statements is None:
        return ()
    if isinstance(raw_statements, Mapping):
        raw_list: Sequence[Any] = (raw_statements,)
    elif isinstance(raw_statements, Sequence):
        raw_list = raw_statements
    else:
        return ()
    statements: list[Statement] = []
    for entry in raw_list:
        if not isinstance(entry, Mapping):
            continue
        parsed = _statement(entry, file=file, line=line, rule=rule, detail=detail)
        if parsed is not None:
            statements.append(parsed)
    return tuple(statements)


def parse_policy_text(
    text: str, *, file: str, rule: str, detail: str = "", line: int | None = None
) -> tuple[tuple[Statement, ...], tuple[Diagnostic, ...]]:
    """Parse a policy document held as a JSON string."""
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        return (), (
            error(
                "D-IAM-PARSE",
                f"policy document is not valid JSON: {exc.msg if hasattr(exc, 'msg') else exc}",
                file=file,
                line=line,
            ),
        )
    if not isinstance(payload, Mapping):
        return (), (error("D-IAM-SHAPE", "policy document is not an object", file=file, line=line),)
    index = _line_index(text)
    effect_lines = index.get("Effect", [])
    statements: list[Statement] = []
    raw_statements = payload.get("Statement")
    if isinstance(raw_statements, Mapping):
        raw_list: Sequence[Any] = (raw_statements,)
    elif isinstance(raw_statements, Sequence) and not isinstance(raw_statements, str):
        raw_list = raw_statements
    else:
        raw_list = ()
    for position, entry in enumerate(raw_list):
        if not isinstance(entry, Mapping):
            continue
        statement_line = effect_lines[position] if position < len(effect_lines) else line
        parsed = _statement(
            entry,
            file=file,
            line=statement_line if statement_line is not None else line,
            rule=rule,
            detail=detail,
        )
        if parsed is not None:
            statements.append(parsed)
    return tuple(statements), ()


def parse_iam_document(
    text: str, *, label: str, kind: str = "iam_json"
) -> tuple[IamDocumentFact | None, tuple[Diagnostic, ...]]:
    """Parse --iam-json input: a policy document, get-role-policy or get-role output."""
    diagnostics: list[Diagnostic] = []
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        message = getattr(exc, "msg", str(exc))
        return None, (error("D-IAM-PARSE", f"invalid JSON: {message}", file=label),)
    if not isinstance(payload, Mapping):
        return None, (error("D-IAM-SHAPE", "input is not a JSON object", file=label),)
    role_arn: str | None = None
    role_name: str | None = None
    assume_statements: tuple[Statement, ...] = ()
    if isinstance(payload.get("Role"), Mapping):
        role = payload["Role"]
        role_arn = str(role.get("Arn")) if role.get("Arn") else None
        role_name = str(role.get("RoleName")) if role.get("RoleName") else None
        trust = role.get("AssumeRolePolicyDocument")
        if isinstance(trust, Mapping):
            assume_statements = statements_from_policy_object(
                trust, file=label, line=None, rule="IAM.trust", detail="get-role trust policy"
            )
            if not assume_statements:
                diagnostics.append(
                    warning(
                        "D-IAM-EMPTY",
                        "get-role output has no usable trust statements",
                        file=label,
                    )
                )
    if isinstance(payload.get("Policy"), Mapping):
        payload = payload["Policy"]
    statements = statements_from_policy_object(
        payload, file=label, line=None, rule="IAM.statement", detail=f"{kind} policy document"
    )
    if not statements and not assume_statements:
        diagnostics.append(
            warning("D-IAM-EMPTY", "no usable statements found in the document", file=label)
        )
    return (
        IamDocumentFact(
            label=label,
            file=label,
            statements=statements,
            role_arn=role_arn,
            role_name=role_name,
            assume_role_statements=assume_statements,
        ),
        tuple(diagnostics),
    )
