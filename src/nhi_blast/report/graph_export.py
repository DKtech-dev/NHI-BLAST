"""Graph exports: canonical JSON, escaped Graphviz DOT, and BloodHound OpenGraph (spec 13.6)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import Any

from nhi_blast.core.diagnostics import Diagnostic
from nhi_blast.core.evidence import weakest
from nhi_blast.core.models import (
    NODE_KIND_ORDER,
    DataFileInfo,
    Edge,
    GraphData,
    Inputs,
    Node,
    ToolInfo,
)
from nhi_blast.report._text import safe_text
from nhi_blast.report.redaction import redact_model, redact_payload

GRAPH_SCHEMA = "nhi-blast-graph/1.0"
_OPENGRAPH_RESERVED_KEYS = frozenset({"objectid", "lastseen", "reconcile"})
_OPENGRAPH_CORE_NODE_KEYS = frozenset({"name", "nhi_id", "nhi_kind", "confidence"})


def _sorted_nodes(graph: GraphData) -> tuple[Node, ...]:
    return tuple(sorted(graph.nodes, key=lambda node: (NODE_KIND_ORDER[node.kind], node.id)))


def _sorted_edges(graph: GraphData) -> tuple[Edge, ...]:
    return tuple(sorted(graph.edges, key=Edge.sort_key))


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def graph_export_payload(
    *,
    tool: ToolInfo,
    inputs: Inputs,
    data_files: Sequence[DataFileInfo],
    diagnostics: Sequence[Diagnostic],
    graph: GraphData,
    generated_at: str | None = None,
) -> dict[str, Any]:
    nodes = _sorted_nodes(graph)
    edges = _sorted_edges(graph)
    payload: dict[str, Any] = {
        "schema": GRAPH_SCHEMA,
        "tool": _dump(tool),
        "inputs": _dump(inputs),
        "data_files": [_dump(item) for item in sorted(data_files, key=lambda item: item.name)],
        "diagnostics": [
            _dump(item) for item in sorted(diagnostics, key=lambda item: item.sort_key())
        ],
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "graph": {
            "nodes": [_dump(node) for node in nodes],
            "edges": [_dump(edge) for edge in edges],
        },
    }
    if generated_at is not None:
        payload["generated_at"] = generated_at
    return redact_payload(payload)


def graph_export_json(
    *,
    tool: ToolInfo,
    inputs: Inputs,
    data_files: Sequence[DataFileInfo],
    diagnostics: Sequence[Diagnostic],
    graph: GraphData,
    generated_at: str | None = None,
) -> str:
    payload = graph_export_payload(
        tool=tool,
        inputs=inputs,
        data_files=data_files,
        diagnostics=diagnostics,
        graph=graph,
        generated_at=generated_at,
    )
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


def _dot_text(value: object, limit: int = 200) -> str:
    text = safe_text(value, limit)
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _dot_label(parts: Sequence[object]) -> str:
    escaped = "\\n".join(_dot_text(part, 200) for part in parts)
    return f'"{escaped}"'


def _dot_comment(value: object, limit: int = 300) -> str:
    return f"// {safe_text(value, limit)}"


def graph_export_dot(
    *,
    tool: ToolInfo,
    inputs: Inputs,
    graph: GraphData,
    generated_at: str | None = None,
) -> str:
    """Emit DOT with numeric vertex ids so hostile labels cannot inject syntax."""
    graph = redact_model(graph)
    nodes = _sorted_nodes(graph)
    node_index = {node.id: index for index, node in enumerate(nodes)}
    lines = [
        _dot_comment("NHI-Blast graph export"),
        _dot_comment(f"schema: {GRAPH_SCHEMA}"),
        _dot_comment(f"tool: {tool.name} {tool.version}"),
        _dot_comment(f"repository: {inputs.repo_slug} [declared {inputs.repo_slug_source}]"),
        _dot_comment(f"inputs: {inputs.digest}"),
    ]
    if generated_at is not None:
        lines.append(_dot_comment(f"generated_at: {generated_at}"))
    graph_label = _dot_label(
        (
            "NHI-Blast authority graph",
            f"repository {inputs.repo_slug}",
            f"inputs {inputs.digest}",
        )
    )
    lines.extend(
        (
            "digraph nhi_blast {",
            f'  graph [rankdir="LR", label={graph_label}, labelloc="t"];',
            '  node [shape="box", style="rounded"];',
            '  edge [fontsize="10"];',
        )
    )
    for index, node in enumerate(nodes):
        label = _dot_label((node.kind.value, safe_text(node.label, 160), node.id))
        lines.append(f'  n{index} [label={label}, kind="{node.kind.value}"];')
    for edge in _sorted_edges(graph):
        source = node_index.get(edge.src)
        target = node_index.get(edge.dst)
        if source is None or target is None:
            continue
        label = _dot_label((f"{edge.kind.value} [{edge.confidence.value}]",))
        lines.append(
            f"  n{source} -> n{target} [label={label}, "
            f'kind="{edge.kind.value}", confidence="{edge.confidence.value}"];'
        )
    lines.append("}")
    return "\n".join(lines) + "\n"


def _opengraph_kind(kind_value: str) -> str:
    parts = [part.capitalize() for part in kind_value.replace("-", "_").split("_") if part]
    return "NHI_" + "".join(parts)


def _opengraph_prop_value(value: Any) -> Any | None:
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        if not value:
            return []
        if all(isinstance(item, bool) for item in value):
            return list(value)
        if all(isinstance(item, str) for item in value):
            return list(value)
        if all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return list(value)
        if all(isinstance(item, float) for item in value):
            return list(value)
        return None
    return None


def _opengraph_node_id_map(nodes: Sequence[Node], reserved_ids: set[str]) -> dict[str, str]:
    used = set(reserved_ids)
    mapping: dict[str, str] = {}
    for node in nodes:
        base = node.id.replace(":", "_")
        candidate = base
        if candidate in used:
            suffix = hashlib.sha256(node.id.encode("utf-8")).hexdigest()[:8]
            candidate = f"{base}_{suffix}"
            counter = 1
            while candidate in used:
                candidate = f"{base}_{suffix}_{counter}"
                counter += 1
        used.add(candidate)
        mapping[node.id] = candidate
    return mapping


def _opengraph_node_properties(node: Node) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for raw_key, raw_value in sorted(node.attrs.items(), key=lambda pair: str(pair[0])):
        key = str(raw_key).lower()
        if key in _OPENGRAPH_RESERVED_KEYS or key in _OPENGRAPH_CORE_NODE_KEYS:
            continue
        coerced = _opengraph_prop_value(raw_value)
        if coerced is not None:
            props[key] = coerced
    props["name"] = safe_text(node.label, 200)
    props["nhi_id"] = node.id
    props["nhi_kind"] = node.kind.value
    props["confidence"] = (
        weakest(*(e.cls for e in node.evidence)).value if node.evidence else "unknown"
    )
    return props


def graph_export_opengraph(
    *,
    tool: ToolInfo,
    inputs: Inputs,
    graph: GraphData,
    generated_at: str | None = None,
) -> str:
    """Emit deterministic, redacted BloodHound CE OpenGraph v9.0.0 JSON."""
    graph = redact_model(graph)
    nodes = _sorted_nodes(graph)
    edges = _sorted_edges(graph)
    env_id = f"nhi_env_{inputs.digest[:12]}".replace(":", "_")
    env_props: dict[str, Any] = {
        "name": safe_text(inputs.repo_slug, 200),
        "tool_version": tool.version,
        "repository": inputs.repo_slug,
        "inputs_digest": inputs.digest,
    }
    if generated_at is not None:
        env_props["generated_at"] = generated_at
    env_node: dict[str, Any] = {
        "id": env_id,
        "kinds": ["NHI_Environment"],
        "properties": env_props,
    }
    id_map = _opengraph_node_id_map(nodes, reserved_ids={env_id})
    og_nodes: list[dict[str, Any]] = [
        env_node,
        *(
            {
                "id": id_map[node.id],
                "kinds": [_opengraph_kind(node.kind.value)],
                "properties": _opengraph_node_properties(node),
            }
            for node in nodes
        ),
    ]
    og_edges = [
        {
            "kind": _opengraph_kind(edge.kind.value),
            "start": {"match_by": "id", "value": id_map.get(edge.src, edge.src.replace(":", "_"))},
            "end": {"match_by": "id", "value": id_map.get(edge.dst, edge.dst.replace(":", "_"))},
            "properties": {
                "edge_id": edge.id,
                "confidence": edge.confidence.value,
                "lifetime": edge.lifetime.value,
            },
        }
        for edge in edges
    ]
    payload: dict[str, Any] = {
        "metadata": {
            "source_kind": "NHI_Blast",
        },
        "graph": {
            "nodes": og_nodes,
            "edges": og_edges,
        },
    }
    return (
        json.dumps(
            redact_payload(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )


__all__ = [
    "GRAPH_SCHEMA",
    "graph_export_dot",
    "graph_export_json",
    "graph_export_opengraph",
    "graph_export_payload",
]
