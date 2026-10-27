"""Dependency-ordered human rotation plans with SCC batches (spec 12.5-12.6)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import networkx as nx

from nhi_blast.analysis.selectors import SelectorKind
from nhi_blast.core.data import rotation_hints
from nhi_blast.core.evidence import (
    Evidence,
    EvidenceClass,
    dedupe_evidence,
    evidence_sort_key,
    weakest,
)
from nhi_blast.core.models import (
    CredentialKind,
    CredentialRef,
    Edge,
    EdgeKind,
    GraphData,
    Lifetime,
    Node,
    NodeKind,
    Partition,
    RotationPlan,
    RotationStep,
    StepPhase,
    ZCredential,
)

_CONTROL_EDGES = frozenset(
    {
        EdgeKind.AUTHENTICATES_AS,
        EdgeKind.CAN_READ_VALUE,
        EdgeKind.CAN_MODIFY,
        EdgeKind.STORES,
    }
)


def _ordered_evidence(items: Iterable[Evidence]) -> tuple[Evidence, ...]:
    return tuple(sorted(dedupe_evidence(items), key=evidence_sort_key))


def _outgoing(graph: GraphData) -> dict[str, list[Edge]]:
    outgoing: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        if edge.kind in _CONTROL_EDGES and edge.confidence is not EvidenceClass.UNKNOWN:
            outgoing.setdefault(edge.src, []).append(edge)
    for edges in outgoing.values():
        edges.sort(key=Edge.sort_key)
    return outgoing


def _dependencies(
    graph: GraphData, z_ids: set[str]
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], list[Evidence]]]:
    outgoing = _outgoing(graph)
    dependencies: set[tuple[str, str]] = set()
    supporting: dict[tuple[str, str], list[Evidence]] = {}
    for credential in sorted(z_ids):
        principals: list[tuple[str, tuple[Evidence, ...]]] = [(credential, ())]
        principals.extend(
            (edge.dst, edge.evidence)
            for edge in outgoing.get(credential, ())
            if edge.kind is EdgeKind.AUTHENTICATES_AS
        )
        for principal, auth_evidence in sorted(principals, key=lambda item: item[0]):
            for control in outgoing.get(principal, ()):
                if control.kind not in {EdgeKind.CAN_READ_VALUE, EdgeKind.CAN_MODIFY}:
                    continue
                for stores in outgoing.get(control.dst, ()):
                    target = stores.dst
                    if stores.kind is not EdgeKind.STORES or target not in z_ids:
                        continue
                    if target == credential:
                        continue
                    key = (credential, target)
                    dependencies.add(key)
                    supporting.setdefault(key, []).extend(
                        (*auth_evidence, *control.evidence, *stores.evidence)
                    )
    return dependencies, supporting


def _credential_ref(node: Node, surviving: ZCredential) -> CredentialRef:
    kind = CredentialKind(
        str(node.attrs.get("credential_kind", CredentialKind.GENERIC_SECRET.value))
    )
    return CredentialRef(
        id=node.id,
        label=node.label,
        kind=kind,
        lifetime=surviving.lifetime,
        survival_window=surviving.survival_window,
        criticality=surviving.criticality,
        evidence=_ordered_evidence(node.evidence),
    )


def _human_evidence(rule: str, detail: str) -> Evidence:
    return Evidence(cls=EvidenceClass.ASSUMED, rule=rule, detail=detail)


def _step(
    *,
    phase: StepPhase,
    order: int,
    generation: int | None = None,
    credentials: tuple[CredentialRef, ...] = (),
    batch: bool = False,
    depends_on: tuple[str, ...] = (),
    actions: tuple[str, ...],
    evidence: Iterable[Evidence],
    rule: str,
    detail: str,
) -> RotationStep:
    entries = _ordered_evidence((*evidence, _human_evidence(rule, detail)))
    return RotationStep(
        phase=phase,
        order=order,
        generation=generation,
        credentials=credentials,
        batch=batch,
        depends_on=depends_on,
        actions=actions,
        confidence=weakest(*(item.cls for item in entries)),
        evidence=entries,
    )


def _hint(credential: CredentialRef) -> str:
    hints = rotation_hints()
    action = hints.hint(credential.kind) or hints.hint(CredentialKind.GENERIC_SECRET)
    return f"{credential.label}: {action}"


def _rotation_steps(
    graph: GraphData, partition: Partition
) -> tuple[tuple[RotationStep, ...], bool]:
    surviving = {item.credential: item for item in partition.Z}
    nodes = {node.id: node for node in graph.nodes}
    z_ids = set(surviving)
    dependency_pairs, supporting = _dependencies(graph, z_ids)
    dependencies = nx.DiGraph()
    dependencies.add_nodes_from(sorted(z_ids))
    dependencies.add_edges_from(sorted(dependency_pairs))
    condensation: nx.DiGraph = nx.condensation(dependencies)

    def members(component: int) -> tuple[str, ...]:
        values = {str(member) for member in condensation.nodes[component]["members"]}
        return tuple(sorted(values, key=lambda item: (-surviving[item].criticality, item)))

    def component_key(component: int) -> tuple[int, str]:
        component_members = members(component)
        maximum = max(surviving[item].criticality for item in component_members)
        return (-maximum, min(component_members))

    steps: list[RotationStep] = []
    has_batch = False
    for generation, group in enumerate(nx.topological_generations(condensation)):
        for component in sorted(group, key=component_key):
            component_members = members(component)
            batch = len(component_members) > 1
            has_batch = has_batch or batch
            depends_on = tuple(
                sorted(
                    {
                        member
                        for predecessor in condensation.predecessors(component)
                        for member in members(predecessor)
                    }
                )
            )
            credentials = tuple(
                _credential_ref(nodes[item], surviving[item]) for item in component_members
            )
            actions = tuple(_hint(credential) for credential in credentials)
            if batch:
                actions = (
                    "Freeze (temporarily deny or disable) the principals involved "
                    "in this dependency cycle.",
                    *actions,
                    "Re-enable the principals only after every batch member has been rotated.",
                )
            evidence = [item for credential in credentials for item in credential.evidence]
            member_set = set(component_members)
            for (source, _), entries in supporting.items():
                if source in member_set:
                    evidence.extend(entries)
            steps.append(
                _step(
                    phase=StepPhase.ROTATION,
                    order=len(steps) + 1,
                    generation=generation,
                    credentials=credentials,
                    batch=batch,
                    depends_on=depends_on,
                    actions=actions,
                    evidence=evidence,
                    rule="ROTATION.human-action",
                    detail="dependency order and rotation hints are human response guidance",
                )
            )
    return tuple(steps), has_batch


def _containment(
    graph: GraphData,
    partition: Partition,
    selector_kind: str,
    start_nodes: Sequence[str],
) -> RotationStep:
    kind = SelectorKind(selector_kind)
    actions: list[str] = []
    if kind in {
        SelectorKind.ACTION,
        SelectorKind.ACTION_ANY,
        SelectorKind.ALL_MUTABLE_ACTIONS,
    }:
        actions.extend(
            (
                "Pin the action to a verified full commit SHA or remove it.",
                "Disable the affected workflow(s) and review run logs for the exposure window.",
            )
        )
    elif kind is SelectorKind.SECRET:
        actions.append("Rotate the leaked secret immediately; it is included in the surviving set.")
    elif kind is SelectorKind.REPO_WRITE:
        actions.append("Review recent pushes and branch rules, then remove the actor's access.")
    elif kind is SelectorKind.FORK_PR:
        actions.append("Disable untrusted-checkout workflows and remove exposed credentials.")
    elif kind in {SelectorKind.JOB, SelectorKind.WORKFLOW}:
        actions.extend(
            (
                "Disable the affected job or workflow.",
                "Rotate surviving credentials in dependency order.",
            )
        )

    nodes = {node.id: node for node in graph.nodes}
    evidence_ids = set(start_nodes)
    roles = {
        str(nodes[item.credential].attrs["role"])
        for item in partition.E
        if "role" in nodes[item.credential].attrs
    }
    roles.update(node_id for node_id in start_nodes if nodes[node_id].kind is NodeKind.AWS_ROLE)
    evidence_ids.update(item.credential for item in partition.E)
    evidence_ids.update(roles)
    if kind is SelectorKind.ROLE or partition.E:
        actions.extend(
            (
                "Revoke active sessions for the affected roles with a deny keyed "
                "on token issue time (VERIFY).",
                "Tighten the affected role trust policies before restoring federation.",
            )
        )
    evidence = [item for node_id in sorted(evidence_ids) for item in nodes[node_id].evidence]
    return _step(
        phase=StepPhase.CONTAINMENT,
        order=0,
        actions=tuple(actions),
        evidence=evidence,
        rule="CONTAINMENT.human-action",
        detail="containment is suggested human action; session revocation requires verification",
    )


def _verification(
    graph: GraphData, partition: Partition, rotation_count: int
) -> RotationStep | None:
    if not partition.E and not partition.Z:
        return None
    nodes = {node.id: node for node in graph.nodes}
    evidence_ids = {item.credential for item in partition.E}
    evidence_ids.update(item.credential for item in partition.Z)
    for item in partition.Z:
        sink = nodes[item.credential].attrs.get("sink")
        if isinstance(sink, str):
            evidence_ids.add(sink)
    evidence = [item for node_id in sorted(evidence_ids) for item in nodes[node_id].evidence]
    return _step(
        phase=StepPhase.VERIFY,
        order=rotation_count + 1,
        actions=(f"VERIFY: {rotation_hints().verify_default()}",),
        evidence=evidence,
        rule="VERIFY.cloudtrail",
        detail="CloudTrail review inside the exposure window is required and is not executed",
    )


def plan_rotation(
    graph: GraphData,
    partition: Partition,
    *,
    selector_kind: str,
    start_nodes: Sequence[str],
) -> RotationPlan:
    rotation, has_batch = _rotation_steps(graph, partition)
    containment = _containment(graph, partition, selector_kind, start_nodes)
    verification = _verification(graph, partition, len(rotation))
    notes: list[str] = []
    if has_batch:
        notes.append(rotation_hints().note("frozen"))
    if any(item.lifetime is Lifetime.PERSISTENT_ROTATING for item in partition.Z):
        notes.append(rotation_hints().note("rotating"))
    return RotationPlan(
        containment=(containment,),
        rotation=rotation,
        verify=(verification,) if verification is not None else (),
        notes=tuple(notes),
    )


__all__ = ["plan_rotation"]
