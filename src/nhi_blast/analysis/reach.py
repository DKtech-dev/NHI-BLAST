"""Deterministic best-path reach over authority edges (spec 12.2 and 12.4)."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from nhi_blast.core.evidence import EvidenceClass, rank, weakest
from nhi_blast.core.models import (
    AUTHORITY_EDGE_KINDS,
    Edge,
    EdgeKind,
    GraphData,
)


@dataclass(frozen=True, slots=True)
class PathInfo:
    node: str
    edges: tuple[Edge, ...] = ()
    classes: tuple[EvidenceClass, ...] = ()
    weakest: EvidenceClass = EvidenceClass.DECLARED
    hops: int = 0
    ids: tuple[str, ...] = ()

    def extend(self, edge: Edge, destination: str) -> PathInfo:
        return PathInfo(
            node=destination,
            edges=(*self.edges, edge),
            classes=(*self.classes, edge.confidence),
            weakest=weakest(self.weakest, edge.confidence),
            hops=self.hops + 1,
            ids=(*self.ids, edge.id),
        )

    def order_key(self) -> tuple[int, int, tuple[str, ...]]:
        return (rank(self.weakest), self.hops, self.ids)


@dataclass(frozen=True, slots=True)
class PotentialReach:
    paths: dict[str, PathInfo]
    edges: tuple[str, ...]
    nodes: tuple[str, ...]
    unresolved_inputs: tuple[str, ...]


def _traverse(
    graph: GraphData,
    starts: Sequence[str],
    *,
    include_unknown: bool,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, PathInfo]:
    nodes = {node.id: node for node in graph.nodes}
    initial = tuple(sorted(set(starts)))
    for start in initial:
        if start not in nodes:
            msg = f"unknown start node: {start}"
            raise ValueError(msg)
    outgoing: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        if edge.kind not in AUTHORITY_EDGE_KINDS:
            continue
        if not include_unknown and edge.confidence is EvidenceClass.UNKNOWN:
            continue
        outgoing.setdefault(edge.src, []).append(edge)
    for edges in outgoing.values():
        edges.sort(key=Edge.sort_key)

    seen = {start: PathInfo(node=start) for start in initial}
    queue = deque(initial)
    while queue:
        if should_stop is not None and should_stop():
            break
        current = queue.popleft()
        base = seen[current]
        for edge in outgoing.get(current, ()):
            candidates = [(edge.dst, base.extend(edge, edge.dst))]
            session = edge.attrs.get("session_credential")
            if edge.kind is EdgeKind.CAN_ASSUME and isinstance(session, str) and session in nodes:
                candidates.append((session, base.extend(edge, session)))
            for destination, candidate in candidates:
                existing = seen.get(destination)
                if existing is None or candidate.order_key() < existing.order_key():
                    seen[destination] = candidate
                    queue.append(destination)
    return seen


def reach(
    graph: GraphData,
    starts: Sequence[str],
    *,
    should_stop: Callable[[], bool] | None = None,
) -> dict[str, PathInfo]:
    return _traverse(graph, starts, include_unknown=False, should_stop=should_stop)


def potential_reach(
    graph: GraphData,
    starts: Sequence[str],
    *,
    reachable: Mapping[str, PathInfo] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> PotentialReach:
    confirmed = reach(graph, starts, should_stop=should_stop) if reachable is None else reachable
    every_path = _traverse(graph, starts, include_unknown=True, should_stop=should_stop)
    paths = {
        node_id: every_path[node_id]
        for node_id in sorted(every_path)
        if node_id not in confirmed and every_path[node_id].weakest is EvidenceClass.UNKNOWN
    }
    edges_by_id = {edge.id: edge for edge in graph.edges}
    unknown_edges = {
        edge_id
        for path in paths.values()
        for edge_id in path.ids
        if edges_by_id[edge_id].confidence is EvidenceClass.UNKNOWN
    }
    blockers: set[str] = set()
    for edge_id in sorted(unknown_edges):
        for item in edges_by_id[edge_id].evidence:
            if item.cls is EvidenceClass.UNKNOWN:
                blockers.add(f"{item.rule}: {item.detail}" if item.detail else item.rule)
    return PotentialReach(
        paths=paths,
        edges=tuple(sorted(unknown_edges)),
        nodes=tuple(paths),
        unresolved_inputs=tuple(sorted(blockers)),
    )


__all__ = ["PathInfo", "PotentialReach", "potential_reach", "reach"]
