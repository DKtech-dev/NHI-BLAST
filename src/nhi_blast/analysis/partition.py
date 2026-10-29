"""Obtained-credential partitioning and bounded survival closure (spec 12.3)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from nhi_blast.analysis.reach import PathInfo, PotentialReach, potential_reach, reach
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.models import (
    PERSISTENT_LIFETIMES,
    ECredential,
    Edge,
    EdgeKind,
    GraphData,
    Lifetime,
    Node,
    NodeKind,
    Partition,
    ZCredential,
)

_OBTAINING_EDGES = frozenset({EdgeKind.HOLDS, EdgeKind.STORES, EdgeKind.CAN_ASSUME})
_CLOSURE_EDGES = frozenset(
    {
        EdgeKind.AUTHENTICATES_AS,
        EdgeKind.CAN_READ_VALUE,
        EdgeKind.STORES,
    }
)


@dataclass(frozen=True, slots=True)
class PartitionResult:
    partition: Partition
    reach: dict[str, PathInfo]
    potential: PotentialReach
    truncated: bool


def _lifetime(node: Node) -> Lifetime:
    return Lifetime(str(node.attrs.get("lifetime", Lifetime.NA.value)))


def _survival_window(node: Node, lifetime: Lifetime) -> str:
    configured = node.attrs.get("survival_window")
    if isinstance(configured, str) and configured:
        return configured
    interval = node.attrs.get("rotation_interval_days")
    if lifetime is Lifetime.PERSISTENT_ROTATING and interval is not None:
        return f"up to {interval} days"
    return "until rotated"


def _z_credential(node: Node, depth: int) -> ZCredential:
    lifetime = _lifetime(node)
    return ZCredential(
        credential=node.id,
        depth=depth,
        lifetime=lifetime,
        survival_window=_survival_window(node, lifetime),
        criticality=int(node.attrs.get("criticality", 0)),
    )


def _closure_outgoing(graph: GraphData) -> dict[str, list[Edge]]:
    outgoing: dict[str, list[Edge]] = {}
    for edge in graph.edges:
        if edge.kind in _CLOSURE_EDGES and edge.confidence is not EvidenceClass.UNKNOWN:
            outgoing.setdefault(edge.src, []).append(edge)
    for edges in outgoing.values():
        edges.sort(key=Edge.sort_key)
    return outgoing


def _close_persistent(
    graph: GraphData,
    nodes: Mapping[str, Node],
    initial: Mapping[str, int],
    max_depth: int,
    should_stop: Callable[[], bool] | None,
) -> tuple[dict[str, int], bool]:
    depths = dict(initial)
    outgoing = _closure_outgoing(graph)
    frontier = sorted(depths)
    depth = 0
    while frontier and depth < max_depth:
        if should_stop is not None and should_stop():
            return depths, True
        depth += 1
        following: set[str] = set()
        for credential in frontier:
            for auth in outgoing.get(credential, ()):
                if auth.kind is not EdgeKind.AUTHENTICATES_AS:
                    continue
                for read in outgoing.get(auth.dst, ()):
                    if read.kind is not EdgeKind.CAN_READ_VALUE:
                        continue
                    for stores in outgoing.get(read.dst, ()):
                        if stores.kind is not EdgeKind.STORES:
                            continue
                        candidate = nodes[stores.dst]
                        if (
                            candidate.kind is NodeKind.CREDENTIAL
                            and _lifetime(candidate) in PERSISTENT_LIFETIMES
                            and candidate.id not in depths
                        ):
                            depths[candidate.id] = depth
                            following.add(candidate.id)
        frontier = sorted(following)
    return depths, bool(frontier)


def partition_graph(
    graph: GraphData,
    starts: Sequence[str],
    *,
    max_depth: int = 3,
    reachable: Mapping[str, PathInfo] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> PartitionResult:
    if max_depth < 0:
        msg = "max_depth must be non-negative"
        raise ValueError(msg)
    paths = reach(graph, starts, should_stop=should_stop) if reachable is None else dict(reachable)
    nodes = {node.id: node for node in graph.nodes}
    initial_starts = set(starts)
    obtained: set[str] = set()
    for node_id, path in paths.items():
        node = nodes[node_id]
        if node.kind is not NodeKind.CREDENTIAL:
            continue
        if node_id in initial_starts or (path.edges and path.edges[-1].kind in _OBTAINING_EDGES):
            obtained.add(node_id)

    r: list[str] = []
    e: list[ECredential] = []
    depths: dict[str, int] = {}
    for credential in sorted(obtained):
        node = nodes[credential]
        lifetime = _lifetime(node)
        if lifetime is Lifetime.JOB_BOUND:
            r.append(credential)
        elif lifetime is Lifetime.SESSION_TTL:
            e.append(
                ECredential(
                    credential=credential,
                    ttl_seconds=int(node.attrs.get("ttl_seconds", 3600)),
                )
            )
        elif lifetime in PERSISTENT_LIFETIMES:
            depths[credential] = 0

    depths, truncated = _close_persistent(graph, nodes, depths, max_depth, should_stop)
    z = sorted(
        (_z_credential(nodes[credential], depth) for credential, depth in depths.items()),
        key=lambda item: (item.depth, -item.criticality, item.credential),
    )
    return PartitionResult(
        partition=Partition(R=tuple(r), E=tuple(e), Z=tuple(z)),
        reach=paths,
        potential=potential_reach(graph, starts, reachable=paths, should_stop=should_stop),
        truncated=truncated,
    )


__all__ = ["PartitionResult", "partition_graph"]
