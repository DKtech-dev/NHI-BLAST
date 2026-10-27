"""Best-effort Terraform HCL fallback (spec 8.5).

The adapter is deliberately narrow: literal values, ``jsonencode`` of literal
objects, heredoc JSON, literal ``data.aws_iam_policy_document`` blocks and
``var.x`` with a literal default. Modules, ``for_each`` and ``count`` are not
expanded. Facts produced here never exceed DERIVED evidence, and a value that
cannot be resolved is marked unknown rather than guessed.
"""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from nhi_blast.core.diagnostics import Diagnostic, error, warning
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import ParseResult, TfSource
from nhi_blast.parsers.terraform.facts import (
    TfModelFact,
    TfPolicyDocumentFact,
    TfResource,
)

_INTERPOLATION = re.compile(r"\$\{([^{}]*)\}")
_RESOURCE_LINE = re.compile(r'^\s*resource\s+"([^"]+)"\s+"([^"]+)"')
_DATA_LINE = re.compile(r'^\s*data\s+"([^"]+)"\s+"([^"]+)"')
_VAR_EXPR = re.compile(r"^var\.([A-Za-z_][A-Za-z0-9_]*)$")
_RESOURCE_REF = re.compile(r"^(aws_[a-z0-9_]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_]+)?)$")
_JSONENCODE = re.compile(r"^jsonencode\((.*)\)$", re.DOTALL)
_POLICY_DOCUMENT_REF = re.compile(r"^data\.aws_iam_policy_document\.[A-Za-z0-9_-]+(?:\.json)?$")
_SECRET_FIELDS = frozenset(
    {"value", "secret_string", "secret_binary", "password", "master_password"}
)


def _line_map(text: str) -> dict[str, int]:
    lines: dict[str, int] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        match = _RESOURCE_LINE.match(line)
        if match is not None:
            lines.setdefault(f"{match.group(1)}.{match.group(2)}", number)
            continue
        match = _DATA_LINE.match(line)
        if match is not None:
            lines.setdefault(f"data.{match.group(1)}.{match.group(2)}", number)
    return lines


def _substitute_variables(value: str, variables: Mapping[str, Any]) -> tuple[str, bool]:
    """Replace ``${var.x}`` with a literal default; return (text, resolved)."""

    unresolved = False

    def replace(match: re.Match[str]) -> str:
        nonlocal unresolved
        expression = match.group(1).strip()
        if expression.startswith("var."):
            name = expression[len("var.") :]
            replacement = variables.get(name)
            if isinstance(replacement, str):
                return replacement
            if isinstance(replacement, (int, float, bool)):
                return (
                    str(replacement).lower() if isinstance(replacement, bool) else str(replacement)
                )
        unresolved = True
        return match.group(0)

    substituted = _INTERPOLATION.sub(replace, value)
    return substituted, not unresolved


def _resolve_string(
    value: str,
    variables: Mapping[str, Any],
) -> tuple[Any, bool]:
    """Resolve a scalar string. Returns (value, known)."""
    match = _JSONENCODE.match(value.strip())
    if match is not None:
        inner, ok = _substitute_variables(match.group(1).strip(), variables)
        if not ok:
            return None, False
        try:
            return json.loads(inner), True
        except (json.JSONDecodeError, ValueError):
            return None, False
    if (
        value.startswith("${")
        and value.endswith("}")
        and (value.count("${") == 1 or value[2:-1].strip().startswith(("jsonencode(", "var.")))
    ):
        expression = value[2:-1].strip()
        var_match = _VAR_EXPR.match(expression)
        if var_match is not None:
            variable = variables.get(var_match.group(1))
            if isinstance(variable, (str, int, float, bool)):
                return variable, True
            return None, False
        if expression.startswith("data.") and expression.endswith(".json"):
            return expression, True
        if _RESOURCE_REF.match(expression):
            return expression, True
        if expression.startswith("jsonencode("):
            return _resolve_string(expression, variables)
        return None, False
    if "${" in value:
        substituted, ok = _substitute_variables(value, variables)
        if not ok:
            return None, False
        return substituted, True
    return value, True


def _resource_values(
    raw: Mapping[str, Any],
    variables: Mapping[str, Any],
    *,
    comparison: bool,
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    values: dict[str, Any] = {}
    unknown: list[str] = []
    sensitive: list[str] = []
    for key, value in raw.items():
        field = str(key)
        if field in _SECRET_FIELDS:
            sensitive.append(field)
            continue
        if comparison:
            unknown.append(field)
            continue
        resolved, known = _resolve_value(value, variables)
        if not known:
            unknown.append(field)
            continue
        values[field] = resolved
    return values, tuple(sorted(unknown)), tuple(sorted(sensitive))


def _resolve_value(value: Any, variables: Mapping[str, Any]) -> tuple[Any, bool]:
    if value is None or isinstance(value, (bool, int, float)):
        return value, True
    if isinstance(value, str):
        return _resolve_string(value, variables)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        known = True
        for key, item in value.items():
            resolved, item_known = _resolve_value(item, variables)
            if not item_known:
                known = False
                continue
            result[str(key)] = resolved
        return result, known
    if isinstance(value, Sequence):
        items: list[Any] = []
        known = True
        for item in value:
            resolved, item_known = _resolve_value(item, variables)
            if not item_known:
                known = False
                continue
            items.append(resolved)
        return items, known
    return None, False


def _normalise_policy_value(value: Any) -> tuple[str | None, bool]:
    if isinstance(value, Mapping):
        return json.dumps(value, sort_keys=True, separators=(",", ":")), True
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{"):
            try:
                json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                return None, False
            return stripped, True
        return None, False
    return None, False


def _policy_reference(value: str) -> str | None:
    """Return the policy-document address when the value is only a reference."""
    text = value.strip()
    if text.startswith("${") and text.endswith("}"):
        text = text[2:-1].strip()
    return text if _POLICY_DOCUMENT_REF.match(text) else None


def _json_configuration(
    text: str, rel_path: str
) -> tuple[Mapping[str, Any] | None, Diagnostic | None]:
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, error(
            "D-TF-HCL-PARSE",
            f"Terraform JSON configuration could not be parsed: {exc.msg} at line {exc.lineno}",
            file=rel_path,
        )
    if not isinstance(document, Mapping):
        return None, error(
            "D-TF-HCL-PARSE",
            "Terraform JSON configuration is not an object",
            file=rel_path,
        )
    return document, None


def _json_variables(document: Mapping[str, Any]) -> dict[str, Any]:
    raw = document.get("variable")
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(name): body["default"]
        for name, body in raw.items()
        if isinstance(body, Mapping) and "default" in body
    }


def _json_blocks(
    document: Mapping[str, Any], section: str
) -> tuple[tuple[str, str, Mapping[str, Any]], ...]:
    raw = document.get(section)
    if not isinstance(raw, Mapping):
        return ()
    blocks: list[tuple[str, str, Mapping[str, Any]]] = []
    for type_name, typed in raw.items():
        if not isinstance(typed, Mapping):
            continue
        for name, attributes in typed.items():
            if isinstance(attributes, Mapping):
                blocks.append((str(type_name), str(name), attributes))
    return tuple(blocks)


def _policy_document_json(raw: Mapping[str, Any], variables: Mapping[str, Any]) -> str | None:
    """Convert a literal data.aws_iam_policy_document block to policy JSON."""
    statements_raw = raw.get("statement", ())
    if not isinstance(statements_raw, Sequence):
        return None
    statements: list[dict[str, Any]] = []
    for entry in statements_raw:
        if not isinstance(entry, Mapping):
            return None
        statement: dict[str, Any] = {}
        if "sid" in entry:
            sid, known = _resolve_value(entry["sid"], variables)
            if not known:
                return None
            statement["Sid"] = sid
        effect, known = _resolve_value(entry.get("effect", "Allow"), variables)
        if not known:
            return None
        statement["Effect"] = effect
        for source, target in (
            ("actions", "Action"),
            ("not_actions", "NotAction"),
            ("resources", "Resource"),
            ("not_resources", "NotResource"),
        ):
            if source in entry:
                resolved, known = _resolve_value(entry[source], variables)
                if not known:
                    return None
                statement[target] = resolved
        principals = entry.get("principals")
        if isinstance(principals, Sequence):
            principal_map: dict[str, list[Any]] = {}
            for principal in principals:
                if not isinstance(principal, Mapping):
                    return None
                kind, known = _resolve_value(principal.get("type", ""), variables)
                identifiers, identifiers_known = _resolve_value(
                    principal.get("identifiers", ()), variables
                )
                if not known or not identifiers_known:
                    return None
                values = identifiers if isinstance(identifiers, Sequence) else (identifiers,)
                principal_map.setdefault(str(kind), []).extend(values)
            statement["Principal"] = principal_map
        conditions = entry.get("condition")
        if isinstance(conditions, Sequence):
            condition_map: dict[str, dict[str, Any]] = {}
            for condition in conditions:
                if not isinstance(condition, Mapping):
                    return None
                test, known = _resolve_value(condition.get("test", ""), variables)
                variable, variable_known = _resolve_value(condition.get("variable", ""), variables)
                values, values_known = _resolve_value(condition.get("values", ()), variables)
                if not known or not variable_known or not values_known:
                    return None
                condition_map.setdefault(str(test), {})[str(variable)] = values
            if condition_map:
                statement["Condition"] = condition_map
        statements.append(statement)
    return json.dumps(
        {"Version": "2012-10-17", "Statement": statements},
        sort_keys=True,
        separators=(",", ":"),
    )


def _variables(document: Mapping[str, Any]) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    raw = document.get("variable", ())
    if not isinstance(raw, Sequence):
        return variables
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        for name, body in entry.items():
            if isinstance(body, Mapping) and "default" in body:
                variables[str(name)] = body["default"]
    return variables


def _iter_blocks(
    document: Mapping[str, Any], section: str
) -> tuple[tuple[str, str, Mapping[str, Any]], ...]:
    blocks: list[tuple[str, str, Mapping[str, Any]]] = []
    raw = document.get(section, ())
    if not isinstance(raw, Sequence):
        return ()
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        for type_name, body in entry.items():
            if not isinstance(body, Mapping):
                continue
            for name, attributes in body.items():
                if isinstance(attributes, Mapping):
                    blocks.append((str(type_name), str(name), attributes))
    return tuple(blocks)


def parse_tf_hcl(rel_path: str, text: str, *, limits: Limits) -> ParseResult[TfModelFact]:
    """Parse literal HCL or Terraform JSON configuration facts.

    Never raises on malformed or hostile input. The optional ``hcl2`` dependency is
    only required for HCL text; ``*.tf.json`` configuration is read with the standard
    library JSON decoder.
    """
    del limits  # the loader enforces the byte limit before parsing
    # python-hcl2 rejects CRLF inside blocks; Windows checkouts commonly use it.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    diagnostics: list[Diagnostic] = []
    if text.lstrip().startswith("{"):
        document, failure = _json_configuration(text, rel_path)
        if document is None:
            assert failure is not None
            return ParseResult(facts=None, diagnostics=(failure,))
        variables = _json_variables(document)
        lines: dict[str, int] = {}
        data_blocks = _json_blocks(document, "data")
        resource_blocks = _json_blocks(document, "resource")
        modules_present = bool(document.get("module"))
    else:
        try:
            hcl2: Any = importlib.import_module("hcl2")
        except ImportError:
            return ParseResult(
                facts=None,
                diagnostics=(
                    error(
                        "D-TF-HCL-UNAVAILABLE",
                        "the optional HCL parser is not installed; install the 'hcl' extra "
                        "or provide Terraform plan/state JSON",
                        file=rel_path,
                    ),
                ),
            )
        try:
            document = hcl2.loads(text)
        except Exception as exc:  # parser boundary: third-party parser may raise any error
            return ParseResult(
                facts=None,
                diagnostics=(
                    error(
                        "D-TF-HCL-PARSE",
                        f"HCL could not be parsed: {type(exc).__name__}",
                        file=rel_path,
                    ),
                ),
            )
        if not isinstance(document, Mapping):
            return ParseResult(
                facts=None,
                diagnostics=(
                    error("D-TF-HCL-PARSE", "HCL document is not an object", file=rel_path),
                ),
            )
        variables = _variables(document)
        lines = _line_map(text)
        data_blocks = _iter_blocks(document, "data")
        resource_blocks = _iter_blocks(document, "resource")
        modules = document.get("module", ())
        modules_present = isinstance(modules, Sequence) and bool(modules)

    resources: dict[str, TfResource] = {}
    policy_documents: dict[str, TfPolicyDocumentFact] = {}

    for type_name, name, attributes in data_blocks:
        if type_name != "aws_iam_policy_document":
            continue
        address = f"data.{type_name}.{name}"
        json_text = _policy_document_json(attributes, variables)
        policy_documents[address] = TfPolicyDocumentFact(
            address=address,
            json_text=json_text,
            unknown=json_text is None,
            file=rel_path,
            line=lines.get(address),
        )
        if json_text is None:
            diagnostics.append(
                warning(
                    "D-TF-HCL-LIMIT",
                    f"{address}: policy document contains values the fallback cannot resolve",
                    file=rel_path,
                    line=lines.get(address),
                )
            )

    for type_name, name, attributes in resource_blocks:
        address = f"{type_name}.{name}"
        comparison = "for_each" in attributes or "count" in attributes
        if comparison:
            diagnostics.append(
                warning(
                    "D-TF-HCL-LIMIT",
                    f"{address}: for_each/count is not expanded; resource facts are partial",
                    file=rel_path,
                    line=lines.get(address),
                )
            )
        values, unknown, sensitive = _resource_values(attributes, variables, comparison=comparison)
        if not comparison:
            for field in ("assume_role_policy", "policy", "json"):
                if field not in attributes:
                    continue
                resolved, known = _resolve_value(attributes[field], variables)
                if not known:
                    unknown = tuple(sorted({*unknown, field}))
                    values.pop(field, None)
                    continue
                if isinstance(resolved, str):
                    reference = _policy_reference(resolved)
                    if reference is not None:
                        values[field] = reference
                        continue
                policy_text, policy_known = _normalise_policy_value(resolved)
                if not policy_known:
                    unknown = tuple(sorted({*unknown, field}))
                    values.pop(field, None)
                    continue
                values[field] = policy_text
        resources[address] = TfResource(
            address=address,
            mode="managed",
            type=type_name,
            name=name,
            values=values,
            unknown_fields=unknown,
            sensitive_fields=sensitive,
            source=TfSource.HCL,
            file=rel_path,
            line=lines.get(address),
        )

    if modules_present:
        diagnostics.append(
            warning(
                "D-TF-HCL-LIMIT",
                "module blocks are not expanded; resources inside modules are not analysed",
                file=rel_path,
            )
        )
    return ParseResult(
        facts=TfModelFact(
            source=TfSource.HCL,
            file=rel_path,
            resources=resources,
            policy_documents=policy_documents,
            variables=variables,
        ),
        diagnostics=tuple(diagnostics),
    )
