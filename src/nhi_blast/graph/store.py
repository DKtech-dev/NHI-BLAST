"""Deterministic graph store with integrity validation (BUILD-PLAN 4.5).

Duplicate identifiers merge evidence. Structural conflicts (a node kind or an
edge's kind/src/dst/lifetime) are integrity errors rather than silent overwrites.
``data()`` validates the invariants every consumer relies on: evidence on every
record, confidence equal to the weakest evidence class, endpoints present, and an
edge identifier that matches its evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from nhi_blast.core.evidence import (
    Evidence,
    dedupe_evidence,
    evidence_sort_key,
    weakest,
)
from nhi_blast.core.ids import edge_id
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    NODE_KIND_ORDER,
    Edge,
    EdgeKind,
    GraphData,
    Node,
    NodeKind,
)


class GraphIntegrityError(RuntimeError):
    """The graph would violate an invariant that downstream analysis assumes."""


class GraphBudgetError(GraphIntegrityError):
    """Adding another node would exceed ``max_graph_nodes``."""


def ordered_evidence(items: Iterable[Evidence]) -> tuple[Evidence, ...]:
    return tuple(sorted(dedupe_evidence(items), key=evidence_sort_key))


@dataclass(slots=True)
class _Indexes:
    out: dict[str, list[str]] = field(default_factory=dict)
    incoming: dict[str, list[str]] = field(default_factory=dict)
    by_kind: dict[NodeKind, list[str]] = field(default_factory=dict)


class GraphStore:
    """Mutable builder-side store; ``data()`` returns the immutable view."""

    def __init__(self, *, limits: Limits | None = None) -> None:
        effective = limits or Limits()
        self._max_nodes = effective.max_graph_nodes
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, Edge] = {}
        self._indexes = _Indexes()
        self.budget_exceeded = False

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def add_node(self, node: Node) -> None:
        if not node.evidence:
            msg = f"node {node.id} has no evidence"
            raise GraphIntegrityError(msg)
        evidence = ordered_evidence(node.evidence)
        existing = self._nodes.get(node.id)
        if existing is not None:
            if existing.kind is not node.kind:
                msg = f"node {node.id} was added as {existing.kind} and then {node.kind}"
                raise GraphIntegrityError(msg)
            merged = ordered_evidence((*existing.evidence, *evidence))
            if merged != existing.evidence:
                self._nodes[node.id] = existing.model_copy(update={"evidence": merged})
            return
        if len(self._nodes) >= self._max_nodes:
            self.budget_exceeded = True
            msg = f"graph node budget of {self._max_nodes} reached"
            raise GraphBudgetError(msg)
        stored = node.model_copy(update={"evidence": evidence})
        self._nodes[node.id] = stored
        self._indexes.by_kind.setdefault(stored.kind, []).append(node.id)
        self._indexes.out.setdefault(node.id, [])
        self._indexes.incoming.setdefault(node.id, [])

    def add_edge(self, edge: Edge) -> None:
        if not edge.evidence:
            msg = f"edge {edge.id} has no evidence"
            raise GraphIntegrityError(msg)
        evidence = ordered_evidence(edge.evidence)
        confidence = weakest(*(item.cls for item in evidence))
        if edge.confidence is not confidence:
            msg = (
                f"edge {edge.id} confidence {edge.confidence} does not match "
                f"weakest evidence {confidence}"
            )
            raise GraphIntegrityError(msg)
        expected = edge_id(edge.kind.value, edge.src, edge.dst, evidence)
        if edge.id != expected:
            msg = f"edge identifier {edge.id} does not match its content"
            raise GraphIntegrityError(msg)
        existing = self._edges.get(edge.id)
        if existing is not None:
            if (
                existing.kind is not edge.kind
                or existing.src != edge.src
                or existing.dst != edge.dst
                or existing.lifetime is not edge.lifetime
            ):
                msg = f"edge {edge.id} conflicts with an existing edge"
                raise GraphIntegrityError(msg)
            merged = ordered_evidence((*existing.evidence, *evidence))
            if merged != existing.evidence:
                self._edges[edge.id] = existing.model_copy(update={"evidence": merged})
            return
        stored = edge.model_copy(update={"evidence": evidence, "confidence": confidence})
        self._edges[edge.id] = stored
        self._indexes.out.setdefault(stored.src, []).append(edge.id)
        self._indexes.incoming.setdefault(stored.dst, []).append(edge.id)

    def node(self, node_id: str) -> Node:
        try:
            return self._nodes[node_id]
        except KeyError:
            msg = f"unknown node: {node_id}"
            raise KeyError(msg) from None

    def edge(self, edge_id_value: str) -> Edge:
        try:
            return self._edges[edge_id_value]
        except KeyError:
            msg = f"unknown edge: {edge_id_value}"
            raise KeyError(msg) from None

    def nodes_of_kind(self, kind: NodeKind) -> tuple[Node, ...]:
        ids = sorted(self._indexes.by_kind.get(kind, ()))
        return tuple(self._nodes[node_id] for node_id in ids)

    def out_edges(
        self,
        node_id: str,
        *,
        kinds: frozenset[EdgeKind] | None = None,
    ) -> tuple[Edge, ...]:
        edges = (self._edges[edge] for edge in self._indexes.out.get(node_id, ()))
        selected = [edge for edge in edges if kinds is None or edge.kind in kinds]
        return tuple(sorted(selected, key=Edge.sort_key))

    def in_edges(
        self,
        node_id: str,
        *,
        kinds: frozenset[EdgeKind] | None = None,
    ) -> tuple[Edge, ...]:
        edges = (self._edges[edge] for edge in self._indexes.incoming.get(node_id, ()))
        selected = [edge for edge in edges if kinds is None or edge.kind in kinds]
        return tuple(sorted(selected, key=Edge.sort_key))

    def successors(self, node_id: str, kind: EdgeKind) -> tuple[str, ...]:
        destinations = {
            edge.dst for edge in self.out_edges(node_id, kinds=frozenset({kind})) if edge.dst
        }
        return tuple(sorted(destinations))

    def remove_edge(self, edge_id_value: str) -> None:
        edge = self._edges.pop(edge_id_value, None)
        if edge is None:
            return
        self._indexes.out.get(edge.src, []).remove(edge_id_value)
        self._indexes.incoming.get(edge.dst, []).remove(edge_id_value)

    def prune_dangling(self) -> int:
        """Drop edges whose endpoints were not admitted under the node budget."""
        dangling = [
            identifier
            for identifier, edge in self._edges.items()
            if edge.src not in self._nodes or edge.dst not in self._nodes
        ]
        for identifier in sorted(dangling):
            self.remove_edge(identifier)
        return len(dangling)

    def data(self) -> GraphData:
        if len(self._nodes) > self._max_nodes:
            msg = f"graph node budget of {self._max_nodes} exceeded"
            raise GraphBudgetError(msg)
        for node in self._nodes.values():
            if not node.evidence:
                msg = f"node {node.id} has no evidence"
                raise GraphIntegrityError(msg)
        for edge in self._edges.values():
            if not edge.evidence:
                msg = f"edge {edge.id} has no evidence"
                raise GraphIntegrityError(msg)
            confidence = weakest(*(item.cls for item in edge.evidence))
            if edge.confidence is not confidence:
                msg = f"edge {edge.id} confidence disagrees with its evidence"
                raise GraphIntegrityError(msg)
            if edge.src not in self._nodes or edge.dst not in self._nodes:
                msg = f"edge {edge.id} references a missing endpoint"
                raise GraphIntegrityError(msg)
            expected = edge_id(edge.kind.value, edge.src, edge.dst, edge.evidence)
            if edge.id != expected:
                msg = f"edge {edge.id} identifier does not match its content"
                raise GraphIntegrityError(msg)
        nodes = tuple(
            sorted(
                self._nodes.values(),
                key=lambda node: (NODE_KIND_ORDER[node.kind], node.id),
            )
        )
        edges = tuple(sorted(self._edges.values(), key=Edge.sort_key))
        return GraphData(nodes=nodes, edges=edges)
