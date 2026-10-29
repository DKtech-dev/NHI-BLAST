"""Terraform plan/state JSON ingestion (spec 8.1, 8.2).

Primary Terraform input. Unknown values come from the after_unknown boolean tree;
sensitive leaves are removed from the values retained in memory, so the analysis
never carries a sensitive value forward. data.aws_iam_policy_document bodies are
collected so policy strings can be resolved through references instead of values.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from nhi_blast.core.diagnostics import Diagnostic, error, warning
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import ParseResult, TfSource
from nhi_blast.parsers._json import decode_json
from nhi_blast.parsers._unicode import validate_unicode
from nhi_blast.parsers.terraform.facts import (
    TfModelFact,
    TfPolicyDocumentFact,
    TfResource,
)

SUPPORTED_FORMAT_MAJOR = "1"
_ADDRESS_LINE = re.compile(r'"address"\s*:\s*"([^"]+)"')


def _flatten_unknown(tree: Any, prefix: str = "") -> tuple[str, ...]:
    paths: list[str] = []
    stack: list[tuple[Any, str]] = [(tree, prefix)]
    while stack:
        node, node_prefix = stack.pop()
        if isinstance(node, Mapping):
            for key, value in reversed(list(node.items())):
                child = f"{node_prefix}.{key}" if node_prefix else str(key)
                stack.append((value, child))
        elif isinstance(node, Sequence) and not isinstance(node, str):
            for position in range(len(node) - 1, -1, -1):
                child = f"{node_prefix}[{position}]" if node_prefix else f"[{position}]"
                stack.append((node[position], child))
        elif node is True:
            paths.append(node_prefix)
    return tuple(paths)


def _strip_sensitive(values: Mapping[str, Any], mask: Any) -> dict[str, Any]:
    """Apply the boolean tree without interpreting keys or shifting list indices."""
    if mask is True:
        return {}
    result = dict(values)
    stack: list[tuple[Any, Any]] = [(result, mask)]
    while stack:
        current, tree = stack.pop()
        if isinstance(current, dict) and isinstance(tree, Mapping):
            children = [(key, child) for key, child in tree.items() if key in current]
        elif isinstance(current, list) and isinstance(tree, list):
            children = list(enumerate(tree[: len(current)]))
        else:
            continue
        for key, child_mask in children:
            if child_mask is True:
                if isinstance(current, dict):
                    del current[key]
                else:
                    current[key] = None
            elif isinstance(child_mask, (Mapping, list)):
                child = current[key]
                if isinstance(child, dict):
                    current[key] = dict(child)
                elif isinstance(child, list):
                    current[key] = list(child)
                else:
                    continue
                stack.append((current[key], child_mask))
    return result


def _address_lines(text: str) -> dict[str, int]:
    lines: dict[str, int] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        match = _ADDRESS_LINE.search(line)
        if match is not None:
            lines.setdefault(match.group(1), number)
    return lines


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _iter_modules(module: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    modules: list[Mapping[str, Any]] = []
    stack: list[Mapping[str, Any]] = [module]
    while stack:
        current = stack.pop()
        modules.append(current)
        for child in reversed(_as_sequence(current.get("child_modules"))):
            if isinstance(child, Mapping):
                stack.append(child)
    return tuple(modules)


def _resource_entries(root_module: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    entries: list[Mapping[str, Any]] = []
    for module in _iter_modules(root_module):
        for resource in _as_sequence(module.get("resources")):
            if isinstance(resource, Mapping):
                entries.append(resource)
    return tuple(entries)


def _expression_parameters(root_module: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    parameters: dict[str, Mapping[str, Any]] = {}
    for module in _iter_modules(root_module):
        for resource in _as_sequence(module.get("resources")):
            if not isinstance(resource, Mapping):
                continue
            address = resource.get("address")
            expressions = resource.get("expressions")
            if isinstance(address, str) and isinstance(expressions, Mapping):
                parameters[address] = expressions
    return parameters


def _module_block(container: Any) -> Mapping[str, Any] | None:
    if not isinstance(container, Mapping):
        return None
    block = container.get("root_module")
    return block if isinstance(block, Mapping) else None


def _collect_iam_policy_documents(
    resources: Mapping[str, TfResource],
) -> dict[str, TfPolicyDocumentFact]:
    documents: dict[str, TfPolicyDocumentFact] = {}
    for address, resource in resources.items():
        if resource.type != "aws_iam_policy_document":
            continue
        json_text: str | None = None
        candidate = resource.values.get("json")
        if isinstance(candidate, str) and candidate.strip().startswith("{"):
            json_text = candidate
        documents[address] = TfPolicyDocumentFact(
            address=address,
            json_text=json_text,
            unknown=json_text is None,
            file=resource.file,
            line=resource.line,
        )
    return documents


def _change_trees(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    trees: dict[str, Any] = {}
    for change in _as_sequence(payload.get("resource_changes")):
        if not isinstance(change, Mapping):
            continue
        address = change.get("address")
        change_block = change.get("change")
        if isinstance(address, str) and isinstance(change_block, Mapping):
            trees[address] = change_block.get(field)
    return trees


def parse_tf_json(label: str, text: str, *, limits: Limits) -> ParseResult[TfModelFact]:
    """Parse a Terraform plan or state JSON document."""
    del limits  # size limits are enforced by the loader before this point
    diagnostics: list[Diagnostic] = []
    try:
        payload = decode_json(text)
        validate_unicode(payload)
    except (ValueError, RecursionError) as exc:
        line = exc.lineno if isinstance(exc, json.JSONDecodeError) else None
        return ParseResult(
            facts=None,
            diagnostics=(
                error(
                    "D-TF-PARSE",
                    "invalid JSON, invalid Unicode or excessive nesting/numeric size",
                    file=label,
                    line=line,
                ),
            ),
        )
    if not isinstance(payload, Mapping):
        return ParseResult(
            facts=None,
            diagnostics=(error("D-TF-FORMAT", "Terraform document is not an object", file=label),),
        )
    format_version = str(payload.get("format_version", ""))
    if not format_version:
        return ParseResult(
            facts=None,
            diagnostics=(
                error(
                    "D-TF-FORMAT",
                    "missing format_version; not a Terraform plan or state document",
                    file=label,
                ),
            ),
        )
    if format_version.split(".", 1)[0] != SUPPORTED_FORMAT_MAJOR:
        return ParseResult(
            facts=None,
            diagnostics=(
                error(
                    "D-TF-FORMAT",
                    f"unsupported format_version {format_version}; only 1.x is supported",
                    file=label,
                ),
            ),
        )
    planned_values = payload.get("planned_values")
    state_values = payload.get("values")
    prior_state = payload.get("prior_state")
    if planned_values is None and state_values is None:
        return ParseResult(
            facts=None,
            diagnostics=(
                warning(
                    "D-TF-FORMAT",
                    "document has neither planned_values nor values; skipped",
                    file=label,
                ),
            ),
        )
    source = TfSource.PLAN if planned_values is not None else TfSource.STATE
    primary_root = _module_block(planned_values)
    if primary_root is None:
        primary_root = _module_block(state_values)
    prior_root = (
        _module_block(prior_state.get("values")) if isinstance(prior_state, Mapping) else None
    )

    lines = _address_lines(text)
    unknown_trees = _change_trees(payload, "after_unknown")
    sensitive_trees = _change_trees(payload, "after_sensitive")
    configuration = payload.get("configuration")
    configuration_root = (
        configuration.get("root_module") if isinstance(configuration, Mapping) else None
    )
    references = (
        _expression_parameters(configuration_root)
        if isinstance(configuration_root, Mapping)
        else {}
    )

    resources: dict[str, TfResource] = {}

    def add_resources(root: Mapping[str, Any] | None, *, secondary: bool) -> None:
        if root is None:
            return
        for resource in _resource_entries(root):
            address = resource.get("address")
            if not isinstance(address, str) or (secondary and address in resources):
                continue
            values = resource.get("values")
            plain_values = dict(values) if isinstance(values, Mapping) else {}
            blind: list[str] = []
            for mask in (sensitive_trees.get(address), resource.get("sensitive_values")):
                blind.extend(_flatten_unknown(mask))
                plain_values = _strip_sensitive(plain_values, mask)
            sensitive_fields = tuple(sorted(set(blind)))
            unknown_tree = unknown_trees.get(address)
            unknown_fields = _flatten_unknown(unknown_tree) if unknown_tree else ()
            expressions = references.get(address)
            reference_map: dict[str, tuple[str, ...]] = {}
            if isinstance(expressions, Mapping):
                for field_name, body in expressions.items():
                    if isinstance(body, Mapping) and isinstance(body.get("references"), Sequence):
                        reference_map[str(field_name)] = tuple(
                            str(item) for item in body["references"] if isinstance(item, str)
                        )
            resources[address] = TfResource(
                address=address,
                mode=str(resource.get("mode", "managed")),
                type=str(resource.get("type", "")),
                name=str(resource.get("name", "")),
                index=resource.get("index")
                if isinstance(resource.get("index"), (int, str))
                else None,
                values=plain_values,
                unknown_fields=unknown_fields,
                sensitive_fields=sensitive_fields,
                references=reference_map,
                source=source,
                file=label,
                line=lines.get(address),
            )

    add_resources(primary_root, secondary=False)
    add_resources(prior_root, secondary=True)

    documents = _collect_iam_policy_documents(resources)

    if not resources:
        diagnostics.append(
            warning("D-TF-EMPTY", "no Terraform resources found in the document", file=label)
        )
    return ParseResult(
        facts=TfModelFact(
            source=source,
            file=label,
            format_version=format_version,
            terraform_version=str(payload.get("terraform_version", "")) or None,
            resources=resources,
            policy_documents=documents,
        ),
        diagnostics=tuple(diagnostics),
    )
