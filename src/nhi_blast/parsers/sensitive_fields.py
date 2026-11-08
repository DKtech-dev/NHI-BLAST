"""Allow-project Terraform metadata before constructing returned fact models.

Policy fields are approved only in the shapes consumed by the existing IAM parser.
Literal redaction is heuristic: arbitrary strings inside approved condition metadata
are not claimed to be secret-free. Credential values and unsupported source fields
are excluded independently of Terraform producer sensitivity masks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from nhi_blast.core.data import SensitiveFieldPolicy, sensitive_field_policy
from nhi_blast.parsers._json import decode_json
from nhi_blast.parsers.gha.literals import redact_literals

_POLICY_REFERENCE = re.compile(
    r"(?:module[.][A-Za-z0-9_-]+[.])*data[.]aws_iam_policy_document[.][A-Za-z0-9_-]+(?:[.]json)?"
)


@dataclass(frozen=True, slots=True)
class ResourceProjection:
    values: dict[str, Any]
    sensitive_fields: tuple[str, ...]
    unknown_fields: tuple[str, ...]


def _policy_scalar(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str):
        # A rewritten semantic literal is a different policy, not resolved metadata.
        return (value, True) if redact_literals(value) == value else (None, False)
    if value is None or isinstance(value, (bool, int, float)):
        return value, True
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            if isinstance(item, (dict, list)):
                return None, False
            cleaned, known = _policy_scalar(item)
            if not known:
                return None, False
            result.append(cleaned)
        return result, True
    return None, False


def _policy_mapping(
    value: Any, *, conditions: bool, policy: SensitiveFieldPolicy
) -> tuple[Any, bool]:
    if not isinstance(value, Mapping):
        return _policy_scalar(value) if not conditions else (None, False)
    result: dict[str, Any] = {}
    for key, child in value.items():
        if not isinstance(key, str):
            return None, False
        if redact_literals(key) != key or (
            not conditions and key not in policy.policy_principal_types
        ):
            return None, False
        if conditions:
            if not isinstance(child, Mapping):
                return None, False
            nested: dict[str, Any] = {}
            for name, item in child.items():
                cleaned, known = _policy_scalar(item)
                if not isinstance(name, str) or redact_literals(name) != name or not known:
                    return None, False
                nested[name] = cleaned
            result[key] = nested
        else:
            cleaned, known = _policy_scalar(child)
            if not known:
                return None, False
            result[key] = cleaned
    return result, True


def project_policy_value(value: Any) -> tuple[Any, bool]:
    """Retain consumed policy shape or a policy-document reference, never opaque text."""
    original = value
    if isinstance(value, str):
        reference = value.strip()
        if reference.startswith("${") and reference.endswith("}"):
            reference = reference[2:-1].strip()
        if _POLICY_REFERENCE.fullmatch(reference):
            return value, True
        try:
            value = decode_json(value)
        except (ValueError, RecursionError):
            return None, False
    if not isinstance(value, Mapping):
        return None, False
    policy = sensitive_field_policy()
    result = {key: value[key] for key in policy.policy_root_fields if key in value}
    if "Version" in result:
        cleaned, known = _policy_scalar(result["Version"])
        if not known:
            return None, False
        result["Version"] = cleaned
    raw = value.get("Statement")
    entries = [raw] if isinstance(raw, Mapping) else raw
    if entries is not None:
        if not isinstance(entries, list):
            return None, False
        statements: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                return None, False
            if policy.policy_unsupported_semantic_fields.intersection(entry):
                return None, False
            statement: dict[str, Any] = {}
            for key in policy.policy_statement_fields:
                if key not in entry:
                    continue
                if key in {"Principal", "Condition"}:
                    cleaned, known = _policy_mapping(
                        entry[key], conditions=key == "Condition", policy=policy
                    )
                else:
                    cleaned, known = _policy_scalar(entry[key])
                if not known:
                    return None, False
                statement[key] = cleaned
            statements.append(statement)
        result["Statement"] = statements[0] if isinstance(raw, Mapping) else statements
    if isinstance(original, str):
        if result == value:
            return original, True
        return json.dumps(result, sort_keys=True, separators=(",", ":")), True
    return result, True


def _project_kind(
    value: Any, kind: str, path: str, policy: SensitiveFieldPolicy, masks: tuple[str, ...]
) -> ResourceProjection:
    if kind == "policy" and any(
        mask == path or mask.startswith((path + ".", path + "[")) for mask in masks
    ):
        # Missing a sensitive restriction cannot become an unconditional policy.
        return ResourceProjection({}, (), (path,))
    if value is None:
        return ResourceProjection({path: None}, (), ())
    if kind == "policy":
        cleaned, known = project_policy_value(value)
        return ResourceProjection({path: cleaned} if known else {}, (), () if known else (path,))
    if kind == "text" and isinstance(value, str):
        return ResourceProjection({path: redact_literals(value)}, (), ())
    if kind == "integer" and isinstance(value, int) and not isinstance(value, bool):
        return ResourceProjection({path: value}, (), ())
    if kind == "boolean" and isinstance(value, bool):
        return ResourceProjection({path: value}, (), ())
    if kind == "text_list" and isinstance(value, (str, list)):
        items = [value] if isinstance(value, str) else value
        if all(item is None or isinstance(item, str) for item in items):
            cleaned = [redact_literals(item) if isinstance(item, str) else None for item in items]
            return ResourceProjection(
                {path: cleaned if isinstance(value, list) else cleaned[0]}, (), ()
            )
    if kind.startswith("block:") and isinstance(value, (Mapping, list)):
        entries = [value] if isinstance(value, Mapping) else value
        projected: list[Any] = []
        sensitive: list[str] = []
        unknown: list[str] = []
        for index, entry in enumerate(entries):
            entry_path = path if isinstance(value, Mapping) else f"{path}[{index}]"
            if entry is None:
                projected.append(None)
                continue
            if not isinstance(entry, Mapping):
                projected.append(None)
                unknown.append(entry_path)
                continue
            child = _project_mapping(entry, policy.blocks[kind[6:]], entry_path, policy, masks)
            projected.append(child.values)
            sensitive.extend(child.sensitive_fields)
            unknown.extend(child.unknown_fields)
        block = projected[0] if isinstance(value, Mapping) else projected
        return ResourceProjection({path: block}, tuple(sensitive), tuple(unknown))
    return ResourceProjection({}, (), (path,))


def _project_mapping(
    values: Mapping[str, Any],
    shape: Mapping[str, str],
    prefix: str,
    policy: SensitiveFieldPolicy,
    masks: tuple[str, ...],
) -> ResourceProjection:
    result: dict[str, Any] = {}
    sensitive: list[str] = []
    unknown: list[str] = []
    for key, value in values.items():
        field = redact_literals(str(key))
        path = f"{prefix}.{field}" if prefix else field
        if key in policy.credential_fields:
            sensitive.append(path)
            continue
        kind = shape.get(key)
        if kind is None:
            unknown.append(path)
            continue
        projected = _project_kind(value, kind, path, policy, masks)
        if path in projected.values:
            result[field] = projected.values[path]
        sensitive.extend(projected.sensitive_fields)
        unknown.extend(projected.unknown_fields)
    return ResourceProjection(result, tuple(sorted(set(sensitive))), tuple(sorted(set(unknown))))


def project_resource_values(
    resource_type: str,
    values: Mapping[str, Any],
    *,
    sensitive_fields: tuple[str, ...] = (),
) -> ResourceProjection:
    """Unknown resource types retain field markers, never arbitrary raw values."""
    policy = sensitive_field_policy()
    return _project_mapping(
        values, policy.resources.get(resource_type, {}), "", policy, sensitive_fields
    )
