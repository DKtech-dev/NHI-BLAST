"""Explain a finding, node or edge from a saved JSON report (spec 14.1)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nhi_blast import SCHEMA_VERSION
from nhi_blast.core.evidence import Evidence, dedupe_evidence, evidence_sort_key
from nhi_blast.core.models import Edge, Finding, Node, Report
from nhi_blast.report._text import safe_text

_MAX_REPORT_BYTES = 512 * 1024 * 1024
_MAX_INCIDENT_EDGES = 200


class ExplainError(ValueError):
    """The saved report or identifier cannot be explained."""


def load_report(path: Path) -> Report:
    candidate = path.expanduser()
    try:
        size = candidate.stat().st_size
    except OSError as exc:
        msg = f"cannot read report {path}: {exc.strerror or exc}"
        raise ExplainError(msg) from None
    if not candidate.is_file():
        msg = f"report path is not a file: {path}"
        raise ExplainError(msg)
    if size > _MAX_REPORT_BYTES:
        msg = f"report is larger than the {_MAX_REPORT_BYTES}-byte limit: {path}"
        raise ExplainError(msg)
    try:
        text = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"cannot read report {path}: {exc}"
        raise ExplainError(msg) from None
    try:
        report = Report.model_validate_json(text)
    except ValidationError as exc:
        location = "document"
        if exc.errors():
            location = ".".join(str(part) for part in exc.errors()[0]["loc"]) or location
        msg = f"report is not valid nhi-blast JSON at {location}"
        raise ExplainError(msg) from None
    if report.schema_id != SCHEMA_VERSION:
        msg = f"unsupported report schema: {safe_text(report.schema_id, 80)}"
        raise ExplainError(msg)
    return report


def _evidence_lines(evidence: tuple[Evidence, ...], *, indent: str = "    ") -> list[str]:
    ordered = sorted(dedupe_evidence(evidence), key=evidence_sort_key)
    if not ordered:
        return [f"{indent}None recorded."]
    lines: list[str] = []
    for item in ordered:
        detail = f" {safe_text(item.detail, 400)}" if item.detail else ""
        lines.append(
            f"{indent}[{item.cls.value}] {safe_text(item.rule, 80)} "
            f"{safe_text(item.location(), 240)}{detail}"
        )
    return lines


def _node_name(nodes: dict[str, Node], node_id: str) -> str:
    node = nodes.get(node_id)
    if node is None:
        return safe_text(node_id, 200)
    return f"{safe_text(node.label, 160)} ({safe_text(node.id, 200)})"


def _finding_text(finding: Finding, nodes: dict[str, Node], edges: dict[str, Edge]) -> list[str]:
    lines = [
        f"Finding {safe_text(finding.id, 120)}",
        f"  Rule: {safe_text(finding.rule, 80)}",
        f"  Severity: {finding.severity.value}",
        f"  Confidence: {finding.confidence.value}",
        f"  Title: {safe_text(finding.title, 240)}",
        f"  Message: {safe_text(finding.message, 800)}",
    ]
    if finding.scenario:
        lines.append(f"  Scenario: {safe_text(finding.scenario, 300)}")
    if finding.assumptions:
        lines.append(
            "  Assumptions: " + ", ".join(safe_text(item, 80) for item in finding.assumptions)
        )
    lines.append("  Evidence:")
    lines.extend(_evidence_lines(finding.evidence))
    if finding.path:
        lines.append("  Path:")
        for position, node_id in enumerate(finding.path, start=1):
            lines.append(f"    {position}. {_node_name(nodes, node_id)}")
    if finding.path_edges:
        lines.append("  Path edges:")
        for position, edge_id_value in enumerate(finding.path_edges, start=1):
            edge = edges.get(edge_id_value)
            if edge is None:
                lines.append(f"    {position}. {safe_text(edge_id_value, 200)}")
                continue
            lines.append(
                f"    {position}. {safe_text(edge.id, 200)} "
                f"[{edge.kind.value}] {safe_text(edge.src, 160)} -> "
                f"{safe_text(edge.dst, 160)} ({edge.confidence.value})"
            )
            lines.extend(_evidence_lines(edge.evidence, indent="       "))
    return lines


def _attr(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    else:
        rendered = str(value)
    return safe_text(rendered, 300)


def _edge_summary(edge: Edge) -> str:
    return (
        f"{safe_text(edge.id, 200)} [{edge.kind.value}] "
        f"{safe_text(edge.src, 160)} -> {safe_text(edge.dst, 160)} "
        f"({edge.confidence.value})"
    )


def _node_text(node: Node, nodes: dict[str, Node], edges: tuple[Edge, ...]) -> list[str]:
    lines = [
        f"Node {safe_text(node.id, 200)}",
        f"  Kind: {node.kind.value}",
        f"  Label: {safe_text(node.label, 240)}",
    ]
    if node.attrs:
        lines.append("  Attributes:")
        for key in sorted(node.attrs):
            lines.append(f"    {safe_text(key, 80)}: {_attr(node.attrs[key])}")
    lines.append("  Evidence:")
    lines.extend(_evidence_lines(node.evidence))
    incoming = tuple(
        sorted((edge for edge in edges if edge.dst == node.id), key=lambda edge: edge.sort_key())
    )
    outgoing = tuple(
        sorted((edge for edge in edges if edge.src == node.id), key=lambda edge: edge.sort_key())
    )
    lines.append(f"  Incoming edges: {len(incoming)}")
    for edge in incoming[:_MAX_INCIDENT_EDGES]:
        lines.append(f"    {_edge_summary(edge)}")
        lines.extend(_evidence_lines(edge.evidence, indent="       "))
    if len(incoming) > _MAX_INCIDENT_EDGES:
        lines.append(f"    ... {len(incoming) - _MAX_INCIDENT_EDGES} more")
    lines.append(f"  Outgoing edges: {len(outgoing)}")
    for edge in outgoing[:_MAX_INCIDENT_EDGES]:
        target = nodes.get(edge.dst)
        suffix = "" if target is None else f" -> {safe_text(target.label, 160)}"
        lines.append(f"    {_edge_summary(edge)}{suffix}")
        lines.extend(_evidence_lines(edge.evidence, indent="       "))
    if len(outgoing) > _MAX_INCIDENT_EDGES:
        lines.append(f"    ... {len(outgoing) - _MAX_INCIDENT_EDGES} more")
    return lines


def _edge_text(edge: Edge, nodes: dict[str, Node]) -> list[str]:
    lines = [
        f"Edge {safe_text(edge.id, 200)}",
        f"  Kind: {edge.kind.value}",
        f"  Source: {_node_name(nodes, edge.src)}",
        f"  Target: {_node_name(nodes, edge.dst)}",
        f"  Lifetime: {edge.lifetime.value}",
        f"  Confidence: {edge.confidence.value}",
        "  Evidence:",
    ]
    lines.extend(_evidence_lines(edge.evidence))
    if edge.attrs:
        lines.append("  Attributes:")
        for key in sorted(edge.attrs):
            lines.append(f"    {safe_text(key, 80)}: {_attr(edge.attrs[key])}")
    return lines


def render_explanation(report: Report, identifier: str) -> str:
    """Resolve one id and render its evidence chain; raise ExplainError if absent."""
    nodes = {node.id: node for node in report.graph.nodes}
    edges = {edge.id: edge for edge in report.graph.edges}
    finding = next((item for item in report.findings if item.id == identifier), None)
    if finding is not None:
        return "\n".join(_finding_text(finding, nodes, edges)) + "\n"
    node = nodes.get(identifier)
    if node is not None:
        return "\n".join(_node_text(node, nodes, report.graph.edges)) + "\n"
    edge = edges.get(identifier)
    if edge is not None:
        return "\n".join(_edge_text(edge, nodes)) + "\n"
    msg = f"id {safe_text(identifier, 160)!r} was not found in the report"
    raise ExplainError(msg)


__all__ = ["ExplainError", "load_report", "render_explanation"]
