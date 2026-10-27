"""Complete scenario analysis and cooperative resource limits (spec 12)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import monotonic

from nhi_blast.analysis.findings import build_findings, filter_findings
from nhi_blast.analysis.partition import partition_graph
from nhi_blast.analysis.reach import PathInfo
from nhi_blast.analysis.rotation import plan_rotation
from nhi_blast.analysis.selectors import SelectorKind
from nhi_blast.core.config import Config
from nhi_blast.core.diagnostics import Diagnostic, DiagnosticBag, warning
from nhi_blast.core.evidence import Evidence, EvidenceClass, dedupe_evidence, evidence_sort_key
from nhi_blast.core.ids import credential_node_id, edge_id
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    NODE_KIND_ORDER,
    CredentialKind,
    Edge,
    EdgeKind,
    Finding,
    GraphData,
    Lifetime,
    Node,
    NodeKind,
    Partition,
    RotationPlan,
    ScenarioReport,
)


@dataclass(frozen=True, slots=True)
class ScenarioAnalysis:
    selector: str
    selector_kind: str
    start_nodes: tuple[str, ...]
    partition: Partition
    reach: dict[str, PathInfo]
    potential_edges: tuple[str, ...]
    potential_nodes: tuple[str, ...]
    unresolved_inputs: tuple[str, ...]
    truncated: bool
    rotation_plan: RotationPlan
    findings: tuple[Finding, ...]
    notes: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    def to_report(self) -> ScenarioReport:
        return ScenarioReport(
            selector=self.selector,
            start_nodes=self.start_nodes,
            partition=self.partition,
            potential=self.potential_edges,
            potential_nodes=self.potential_nodes,
            unresolved_inputs=self.unresolved_inputs,
            truncated=self.truncated,
            rotation_plan=self.rotation_plan,
            findings=tuple(
                finding.id for finding in self.findings if finding.scenario == self.selector
            ),
            notes=self.notes,
        )


def _ordered_evidence(items: Sequence[Evidence]) -> tuple[Evidence, ...]:
    return tuple(sorted(dedupe_evidence(items), key=evidence_sort_key))


def _repo_write_graph(graph: GraphData, starts: Sequence[str]) -> GraphData:
    nodes = {node.id: node for node in graph.nodes}
    edges = {edge.id: edge for edge in graph.edges}
    for role in graph.nodes:
        if role.kind is not NodeKind.AWS_ROLE or role.attrs.get("repo_write_accepted") is not True:
            continue
        ttl = int(role.attrs.get("max_session_duration", 3600))
        session = next(
            (
                node
                for node in graph.nodes
                if node.kind is NodeKind.CREDENTIAL and node.attrs.get("role") == role.id
            ),
            None,
        )
        if session is None:
            session_id = credential_node_id("repo-write", f"sts-session:{role.id}")
            session_evidence = _ordered_evidence(
                (
                    *role.evidence,
                    Evidence(
                        cls=EvidenceClass.ASSUMED,
                        rule="A-REPO-WRITE",
                        detail="hypothetical repository-writer role session",
                    ),
                    Evidence(
                        cls=EvidenceClass.ASSUMED,
                        rule="A-STS-TTL",
                        detail=f"session lasts at most {ttl} s",
                    ),
                )
            )
            session = Node(
                id=session_id,
                kind=NodeKind.CREDENTIAL,
                label=f"STS session for {role.label}",
                attrs={
                    "credential_kind": CredentialKind.STS_SESSION.value,
                    "lifetime": Lifetime.SESSION_TTL.value,
                    "ttl_seconds": ttl,
                    "role": role.id,
                    "audience": "sts.amazonaws.com",
                    "criticality": 50,
                    "survival_window": f"up to {ttl} s",
                    "repo_write": True,
                },
                evidence=session_evidence,
            )
            nodes[session.id] = session
        for start in starts:
            assumption = Evidence(
                cls=EvidenceClass.ASSUMED,
                rule="A-REPO-WRITE",
                detail="writer can add id-token: write; role trust accepts the branch candidate",
            )
            entries = _ordered_evidence((*nodes[start].evidence, *role.evidence, assumption))
            edge = Edge(
                id=edge_id(EdgeKind.CAN_ASSUME.value, start, role.id, entries),
                kind=EdgeKind.CAN_ASSUME,
                src=start,
                dst=role.id,
                lifetime=Lifetime.SESSION_TTL,
                confidence=EvidenceClass.ASSUMED,
                evidence=entries,
                attrs={
                    "session_credential": session.id,
                    "audience": "sts.amazonaws.com",
                    "repo_write": True,
                    "intended": False,
                },
            )
            edges[edge.id] = edge
    return GraphData(
        nodes=tuple(sorted(nodes.values(), key=lambda node: (NODE_KIND_ORDER[node.kind], node.id))),
        edges=tuple(sorted(edges.values(), key=Edge.sort_key)),
    )


def analyze_scenario(
    graph: GraphData,
    starts: Sequence[str],
    *,
    selector: str,
    selector_kind: str,
    max_depth: int | None = None,
    limits: Limits | None = None,
    config: Config | None = None,
    strict: bool = False,
    clock: Callable[[], float] = monotonic,
) -> ScenarioAnalysis:
    effective_limits = limits or Limits()
    effective_config = config or Config.empty()
    kind = SelectorKind(selector_kind)
    start_nodes = tuple(sorted(set(starts)))
    local_graph = (
        _repo_write_graph(graph, start_nodes) if kind is SelectorKind.REPO_WRITE else graph
    )
    deadline = clock() + effective_limits.scenario_time_budget_seconds

    def expired() -> bool:
        return clock() >= deadline

    result = partition_graph(
        local_graph,
        start_nodes,
        max_depth=effective_limits.max_closure_depth if max_depth is None else max_depth,
        should_stop=expired,
    )
    truncated = result.truncated or expired()
    notes: list[str] = []
    if kind is SelectorKind.REPO_WRITE:
        notes.append(
            "Repository-write paths are ASSUMED: the writer can add id-token: write "
            "on an editable branch; branch protection was not evaluated."
        )
    local_nodes = {node.id: node for node in local_graph.nodes}
    if not any(local_nodes[node_id].kind is NodeKind.AWS_ROLE for node_id in result.reach):
        notes.append("No path to any role from the selected entrypoint.")
    if result.potential.unresolved_inputs:
        notes.append(
            f"Result is a lower bound: {len(result.potential.unresolved_inputs)} unresolved inputs."
        )
    if result.truncated:
        notes.append("Persistent-credential closure reached the configured depth limit.")
    diagnostics: list[Diagnostic] = []
    rotation = RotationPlan()
    findings: tuple[Finding, ...] = ()
    preliminary = ScenarioReport(
        selector=selector,
        start_nodes=start_nodes,
        partition=result.partition,
        potential=result.potential.edges,
        potential_nodes=result.potential.nodes,
        unresolved_inputs=result.potential.unresolved_inputs,
        truncated=truncated,
    )
    if expired():
        diagnostics.append(
            warning(
                "D-ANALYSIS-TIME",
                "scenario time budget exhausted; results are partial",
            )
        )
        notes.append("Scenario time budget exhausted; rotation and findings were not completed.")
    else:
        rotation = plan_rotation(
            local_graph,
            result.partition,
            selector_kind=kind.value,
            start_nodes=start_nodes,
        )
        generated = build_findings(local_graph, scenarios=(preliminary,))
        filtered = filter_findings(generated.findings, config=effective_config, strict=strict)
        findings = filtered.findings
        diagnostics.extend(filtered.diagnostics)
        notes.extend(rotation.notes)
    return ScenarioAnalysis(
        selector=selector,
        selector_kind=kind.value,
        start_nodes=start_nodes,
        partition=result.partition,
        reach=result.reach,
        potential_edges=result.potential.edges,
        potential_nodes=result.potential.nodes,
        unresolved_inputs=result.potential.unresolved_inputs,
        truncated=truncated,
        rotation_plan=rotation,
        findings=findings,
        notes=tuple(notes),
        diagnostics=DiagnosticBag(diagnostics).sorted(),
    )


__all__ = ["ScenarioAnalysis", "analyze_scenario"]
