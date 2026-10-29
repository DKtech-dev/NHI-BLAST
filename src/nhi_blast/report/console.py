"""Deterministic terminal report (spec 13.5)."""

from __future__ import annotations

from collections.abc import Iterable

from nhi_blast.core.evidence import Evidence, dedupe_evidence, evidence_sort_key
from nhi_blast.core.models import (
    Edge,
    Finding,
    Node,
    Report,
    RotationStep,
    ScenarioReport,
    Severity,
)
from nhi_blast.report._text import safe_text
from nhi_blast.report.redaction import redact_model

_SEVERITY_COLOUR = {
    Severity.CRITICAL: "1;31",
    Severity.HIGH: "31",
    Severity.MEDIUM: "33",
    Severity.LOW: "36",
    Severity.INFO: "2",
}


def _styled(text: str, code: str, *, color: bool) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if color else text


def _heading(title: str, *, color: bool) -> str:
    return _styled(title, "1;36", color=color)


def _evidence(evidence: Iterable[Evidence]) -> str:
    ordered = sorted(dedupe_evidence(evidence), key=evidence_sort_key)
    if not ordered:
        return ""
    primary = ordered[0]
    return f" [{primary.cls.value} {safe_text(primary.location(), 160)}]"


def _node_line(node: Node) -> str:
    label = safe_text(node.label, 160)
    ident = safe_text(node.id, 200)
    return f"{label} ({ident}){_evidence(node.evidence)}"


def _edge_location(edge: Edge | None) -> str:
    return "" if edge is None else _evidence(edge.evidence)


def _format_step(step: RotationStep) -> list[str]:
    prefix = "batch " if step.batch else ""
    generation = "" if step.generation is None else f" generation {step.generation}"
    lines = [f"  {prefix}step {step.order}{generation}:"]
    for action in step.actions:
        lines.append(f"    {safe_text(action, 300)}{_evidence(step.evidence)}")
    for credential in step.credentials:
        lines.append(
            f"    {safe_text(credential.label, 160)} "
            f"({safe_text(credential.id, 200)}){_evidence(credential.evidence)}"
        )
    if step.depends_on:
        lines.append(f"    depends on: {', '.join(safe_text(v, 120) for v in step.depends_on)}")
    return lines


def _scenario_brief(
    scenario: ScenarioReport, nodes: dict[str, Node], edges: dict[str, Edge]
) -> list[str]:
    selector = safe_text(scenario.selector, 300)
    lines = [f"  Selector: {selector}"]
    for start in scenario.start_nodes:
        node = nodes.get(start)
        if node is None:
            lines.append(f"    start {safe_text(start, 200)}")
        else:
            lines.append(f"    start {_node_line(node)}")
    lines.append(f"  Potential edges (UNKNOWN authority): {len(scenario.potential)}")
    if scenario.potential:
        for edge_id_value in scenario.potential[:20]:
            edge = edges.get(edge_id_value)
            detail = ""
            if edge is not None:
                detail = (
                    f" {safe_text(edge.kind.value, 40)} {safe_text(edge.src, 160)}"
                    f" -> {safe_text(edge.dst, 160)}"
                )
            lines.append(f"    {safe_text(edge_id_value, 200)}{detail}{_edge_location(edge)}")
        if len(scenario.potential) > 20:
            lines.append(f"    ... {len(scenario.potential) - 20} more")
    if scenario.unresolved_inputs:
        lines.append(f"  Unresolved inputs: {len(scenario.unresolved_inputs)}")
    if scenario.truncated:
        lines.append("  Truncated: closure or traversal reached a configured limit")
    for note in scenario.notes:
        lines.append(f"  Note: {safe_text(note, 400)}")
    return lines


def _survival(scenario: ScenarioReport, nodes: dict[str, Node]) -> list[str]:
    lines = [
        f"  R (ends with entrypoint): {len(scenario.partition.R)}",
        f"  E (expires on its own): {len(scenario.partition.E)}",
        f"  Z (survives): {len(scenario.partition.Z)}",
    ]
    for credential_id in scenario.partition.R:
        node = nodes.get(credential_id)
        lines.append(f"    R {_node_line(node) if node else safe_text(credential_id, 200)}")
    for entry in scenario.partition.E:
        node = nodes.get(entry.credential)
        detail = _node_line(node) if node else safe_text(entry.credential, 200)
        lines.append(f"    E {detail}; ttl {entry.ttl_seconds}s")
    for surviving in scenario.partition.Z:
        node = nodes.get(surviving.credential)
        detail = _node_line(node) if node else safe_text(surviving.credential, 200)
        lines.append(
            f"    Z {detail}; depth {surviving.depth}; {safe_text(surviving.survival_window, 120)}"
            f"; criticality {surviving.criticality}"
        )
    return lines


def _finding_line(finding: Finding, *, color: bool) -> list[str]:
    severity = _styled(finding.severity.value, _SEVERITY_COLOUR[finding.severity], color=color)
    lines = [
        f"  [{severity}] {safe_text(finding.rule, 80)} {safe_text(finding.id, 100)}: "
        f"{safe_text(finding.title, 240)}{_evidence(finding.evidence)}"
    ]
    message = safe_text(finding.message, 600)
    lines.append(f"    {message}{_evidence(finding.evidence)}")
    if finding.scenario:
        lines.append(f"    scenario: {safe_text(finding.scenario, 300)}")
    if finding.path:
        lines.append(f"    path: {' -> '.join(safe_text(node, 160) for node in finding.path)}")
    return lines


def _parse_section(report: Report) -> list[str]:
    lines = [
        f"  Repository: {safe_text(report.inputs.repo_slug, 200)} "
        f"[declared {safe_text(report.inputs.repo_slug_source, 160)}]",
        f"  Inputs digest: {safe_text(report.inputs.digest, 128)}",
    ]
    for input_file in report.inputs.files:
        lines.append(
            f"  Input: {safe_text(input_file.path, 300)} "
            f"({safe_text(input_file.kind, 40)}, sha256 {safe_text(input_file.sha256[:16], 16)}) "
            f"[declared {safe_text(input_file.path, 260)}]"
        )
    for scope in report.scope_and_limits:
        lines.append(f"  {safe_text(scope, 300)}")
    for data_file in report.data_files:
        lines.append(
            f"  Data: {safe_text(data_file.name, 120)} "
            f"(verified {safe_text(data_file.verified_on, 40)})"
        )
    return lines


def _trust_section(report: Report) -> list[str]:
    roles = [node for node in report.graph.nodes if node.kind.value == "AWS_ROLE"]
    providers = [node for node in report.graph.nodes if node.kind.value == "AWS_OIDC_PROVIDER"]
    lines = [f"  AWS roles: {len(roles)}"]
    lines.extend(f"    {_node_line(role)}" for role in roles)
    lines.append(f"  OIDC providers: {len(providers)}")
    lines.extend(f"    {_node_line(provider)}" for provider in providers)
    audit_findings = [
        finding for finding in report.sorted_findings() if finding.rule.startswith("NHB-OIDC")
    ]
    lines.append(f"  Trust findings: {len(audit_findings)}")
    return lines


def _scenario_section(report: Report, nodes: dict[str, Node], edges: dict[str, Edge]) -> list[str]:
    if not report.scenarios:
        return ["  No scenarios selected; graph and findings only."]
    lines: list[str] = []
    for scenario in report.scenarios:
        lines.extend(_scenario_brief(scenario, nodes, edges))
    return lines


def _survival_section(report: Report, nodes: dict[str, Node]) -> list[str]:
    if not report.scenarios:
        return ["  No scenario partition available."]
    lines: list[str] = []
    for scenario in report.scenarios:
        lines.append(f"  {safe_text(scenario.selector, 300)}")
        lines.extend(_survival(scenario, nodes))
    return lines


def _rotation_section(report: Report) -> list[str]:
    lines: list[str] = []
    plan_count = 0
    for scenario in report.scenarios:
        plan = scenario.rotation_plan
        for label, steps in (
            ("Containment", plan.containment),
            ("Rotation", plan.rotation),
            ("Verify", plan.verify),
        ):
            if steps:
                plan_count += 1
                lines.append(f"  {safe_text(scenario.selector, 300)} - {label}")
                for step in steps:
                    lines.extend(_format_step(step))
        for note in plan.notes:
            lines.append(f"  Note: {safe_text(note, 400)}")
    if plan_count == 0:
        lines.append("  No rotation plan was required.")
    return lines


def _findings_section(report: Report, *, color: bool) -> list[str]:
    findings = report.sorted_findings()
    lines = [f"  Total: {len(findings)}"]
    for finding in findings:
        lines.extend(_finding_line(finding, color=color))
    return lines


def _assumptions_section(report: Report) -> list[str]:
    lines: list[str] = []
    if not report.assumptions and not any(s.potential for s in report.scenarios):
        lines.append("  None recorded.")
    for assumption in report.assumptions:
        marker = "VERIFY" if assumption.verify else "ASSUMED"
        lines.append(
            f"  [{marker}] {safe_text(assumption.id, 80)}: {safe_text(assumption.statement, 500)}"
        )
    for scenario in report.scenarios:
        if not scenario.unresolved_inputs:
            continue
        lines.append(
            f"  Unknown inputs in {safe_text(scenario.selector, 240)}: "
            f"{len(scenario.unresolved_inputs)}"
        )
        for unresolved in scenario.unresolved_inputs[:20]:
            lines.append(f"    {safe_text(unresolved, 300)}")
    return lines


def _diagnostics_section(report: Report) -> list[str]:
    diagnostics = tuple(sorted(report.diagnostics, key=lambda item: item.sort_key()))
    lines = [f"  Total: {len(diagnostics)}"]
    for diagnostic in diagnostics:
        location = ""
        if diagnostic.file:
            location = diagnostic.file
            if diagnostic.line is not None:
                location += f":{diagnostic.line}"
            location = f" {safe_text(location, 260)}"
        lines.append(
            f"  [{diagnostic.level.value}] {safe_text(diagnostic.code, 60)}: "
            f"{safe_text(diagnostic.message, 500)}{location}"
        )
    return lines


def render_console(report: Report, *, color: bool = False) -> str:
    """Render a human-readable report; colour is used only when requested."""
    report = redact_model(report)
    nodes = {node.id: node for node in report.graph.nodes}
    edges = {edge.id: edge for edge in report.graph.edges}
    lines = [
        _styled(f"NHI-Blast {safe_text(report.tool.version, 40)}", "1", color=color),
        f"Report schema: {safe_text(report.schema_id, 80)}",
        "",
        _heading("Parse", color=color),
        *_parse_section(report),
        "",
        _heading("Trust audit", color=color),
        *_trust_section(report),
        "",
        _heading("Scenario", color=color),
        *_scenario_section(report, nodes, edges),
        "",
        _heading("Survival", color=color),
        *_survival_section(report, nodes),
        "",
        _heading("Rotation plan", color=color),
        *_rotation_section(report),
        "",
        _heading("Findings", color=color),
        *_findings_section(report, color=color),
        "",
        _heading("Assumptions and unknowns", color=color),
        *_assumptions_section(report),
        "",
        _heading("Diagnostics", color=color),
        *_diagnostics_section(report),
    ]
    return "\n".join(lines).rstrip() + "\n"
