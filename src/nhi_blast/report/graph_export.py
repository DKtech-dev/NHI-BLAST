"""Graph exports: canonical JSON and escaped Graphviz DOT (spec 13.6)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from nhi_blast.core.diagnostics import Diagnostic
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


__all__ = ["GRAPH_SCHEMA", "graph_export_dot", "graph_export_json", "graph_export_payload"]
