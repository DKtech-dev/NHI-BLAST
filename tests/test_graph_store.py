"""Graph store merging, integrity and deterministic serialisation (M3)."""

from __future__ import annotations

import pytest

from nhi_blast.core.evidence import EvidenceClass, weakest
from nhi_blast.core.ids import edge_id
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    NODE_KIND_ORDER,
    Edge,
    EdgeKind,
    Lifetime,
    Node,
    NodeKind,
)
from nhi_blast.graph.store import (
    GraphBudgetError,
    GraphIntegrityError,
    GraphStore,
)
from tests.support import evidence


def make_node(
    node_id: str = "job:wf#deploy",
    kind: NodeKind = NodeKind.JOB,
    *,
    cls: EvidenceClass = EvidenceClass.DECLARED,
    label: str = "deploy",
) -> Node:
    return Node(
        id=node_id,
        kind=kind,
        label=label,
        attrs={"test": True},
        evidence=(evidence(cls),),
    )


def make_edge(
    src: str,
    dst: str,
    *,
    kind: EdgeKind = EdgeKind.CONTAINS,
    evidence_items: tuple = (evidence(),),
    lifetime: Lifetime = Lifetime.NA,
    edge_identifier: str | None = None,
    confidence: EvidenceClass | None = None,
) -> Edge:
    ordered = tuple(evidence_items)
    return Edge(
        id=edge_identifier or edge_id(kind.value, src, dst, ordered),
        kind=kind,
        src=src,
        dst=dst,
        lifetime=lifetime,
        confidence=confidence or weakest(*(item.cls for item in ordered)),
        evidence=ordered,
        attrs={},
    )


def test_nodes_require_evidence_and_conflicting_kinds_are_rejected() -> None:
    store = GraphStore()
    bare = Node(id="job:a#b", kind=NodeKind.JOB, label="b")
    with pytest.raises(GraphIntegrityError, match="no evidence"):
        store.add_node(bare)
    store.add_node(make_node("job:a#b", NodeKind.JOB))
    with pytest.raises(GraphIntegrityError, match="was added as JOB and then WORKFLOW"):
        store.add_node(make_node("job:a#b", NodeKind.WORKFLOW))


def test_duplicate_nodes_merge_evidence_without_duplicates() -> None:
    store = GraphStore()
    first = make_node(cls=EvidenceClass.DERIVED)
    store.add_node(first)
    extra = make_node(cls=EvidenceClass.DECLARED)
    merged_item = evidence(EvidenceClass.ASSUMED, rule="R8.test")
    second = first.model_copy(update={"evidence": (*first.evidence, merged_item)})
    store.add_node(second)

    assert store.node_count == 1
    stored = store.node("job:wf#deploy")
    assert {item.cls for item in stored.evidence} == {
        EvidenceClass.DERIVED,
        EvidenceClass.ASSUMED,
    }
    assert len(stored.evidence) == 2
    assert stored.attrs == {"test": True}
    assert extra.kind is NodeKind.JOB


def test_edges_require_evidence_and_matching_confidence() -> None:
    store = GraphStore()
    store.add_node(make_node("node:a", NodeKind.REPOSITORY))
    store.add_node(make_node("node:b", NodeKind.WORKFLOW))
    bare = Edge(
        id=edge_id(EdgeKind.CONTAINS.value, "node:a", "node:b", ()),
        kind=EdgeKind.CONTAINS,
        src="node:a",
        dst="node:b",
        confidence=EvidenceClass.DECLARED,
    )
    with pytest.raises(GraphIntegrityError, match="no evidence"):
        store.add_edge(bare)

    strong = evidence(EvidenceClass.DECLARED)
    weak = evidence(EvidenceClass.UNKNOWN, rule="R8.unknown")
    tampered = make_edge(
        "node:a",
        "node:b",
        evidence_items=(strong, weak),
        confidence=EvidenceClass.DECLARED,
    )
    with pytest.raises(GraphIntegrityError, match="weakest evidence"):
        store.add_edge(tampered)


def test_edge_identifier_must_match_content() -> None:
    store = GraphStore()
    store.add_node(make_node("node:a", NodeKind.REPOSITORY))
    store.add_node(make_node("node:b", NodeKind.WORKFLOW))
    forged = make_edge("node:a", "node:b", edge_identifier="0" * 16)
    with pytest.raises(GraphIntegrityError, match="identifier"):
        store.add_edge(forged)


def test_edge_lifetime_conflict_is_rejected() -> None:
    store = GraphStore()
    store.add_node(make_node("node:a", NodeKind.JOB))
    store.add_node(make_node("node:b", NodeKind.ACTION_REF))
    first = make_edge("node:a", "node:b", kind=EdgeKind.RUNS_IN, lifetime=Lifetime.JOB_BOUND)
    store.add_edge(first)
    conflicting = first.model_copy(update={"lifetime": Lifetime.PERSISTENT})
    with pytest.raises(GraphIntegrityError, match="conflicts"):
        store.add_edge(conflicting)
    assert store.edge_count == 1
    assert store.edge(first.id).lifetime is Lifetime.JOB_BOUND


def test_data_rejects_missing_endpoints_and_prune_removes_them() -> None:
    store = GraphStore()
    store.add_node(make_node("node:a", NodeKind.REPOSITORY))
    missing = make_edge("node:a", "node:missing")
    store.add_edge(missing)
    with pytest.raises(GraphIntegrityError, match="missing endpoint"):
        store.data()

    assert store.prune_dangling() == 1
    assert store.edge_count == 0
    assert store.data().edges == ()


def test_indexes_and_successors_are_deterministic() -> None:
    store = GraphStore()
    for node_id, kind in (
        ("node:a", NodeKind.REPOSITORY),
        ("node:b", NodeKind.WORKFLOW),
        ("node:c", NodeKind.WORKFLOW),
        ("node:d", NodeKind.JOB),
    ):
        store.add_node(make_node(node_id, kind))
    first = make_edge("node:a", "node:b")
    second = make_edge("node:a", "node:c")
    third = make_edge("node:a", "node:d", kind=EdgeKind.RUNS_IN)
    for edge_value in (second, first, third):
        store.add_edge(edge_value)

    assert [node.id for node in store.nodes_of_kind(NodeKind.WORKFLOW)] == [
        "node:b",
        "node:c",
    ]
    assert [edge.id for edge in store.out_edges("node:a")] == sorted(
        [first.id, second.id, third.id],
        key=lambda identifier: Edge.sort_key(store.edge(identifier)),
    )
    assert store.successors("node:a", EdgeKind.CONTAINS) == ("node:b", "node:c")
    assert store.successors("node:a", EdgeKind.RUNS_IN) == ("node:d",)
    assert [edge.id for edge in store.in_edges("node:b")] == [first.id]

    store.remove_edge(second.id)
    assert store.successors("node:a", EdgeKind.CONTAINS) == ("node:b",)


def test_node_budget_stops_admission_and_records_truncation() -> None:
    store = GraphStore(limits=Limits(max_graph_nodes=2))
    store.add_node(make_node("node:a", NodeKind.REPOSITORY))
    store.add_node(make_node("node:b", NodeKind.WORKFLOW))
    with pytest.raises(GraphBudgetError, match="budget"):
        store.add_node(make_node("node:c", NodeKind.JOB))
    assert store.budget_exceeded is True
    assert store.node_count == 2
    assert store.data().nodes == (
        store.node("node:a"),
        store.node("node:b"),
    )


def test_data_sorts_nodes_by_kind_then_id_and_edges_by_sort_key() -> None:
    store = GraphStore()
    store.add_node(make_node("job:z#b", NodeKind.JOB))
    store.add_node(make_node("repo:z", NodeKind.REPOSITORY))
    store.add_node(make_node("job:a#a", NodeKind.JOB))
    store.add_node(make_node("action:b@v1", NodeKind.ACTION_REF))
    store.add_node(make_node("action:a@v1", NodeKind.ACTION_REF))
    for src, dst in (
        ("repo:z", "job:a#a"),
        ("repo:z", "job:z#b"),
        ("action:b@v1", "job:z#b"),
    ):
        store.add_edge(make_edge(src, dst))

    first = store.data()
    second = store.data()
    assert first == second
    assert [node.id for node in first.nodes] == [
        "repo:z",
        "job:a#a",
        "job:z#b",
        "action:a@v1",
        "action:b@v1",
    ]
    assert all(
        NODE_KIND_ORDER[first.nodes[index].kind] <= NODE_KIND_ORDER[first.nodes[index + 1].kind]
        for index in range(len(first.nodes) - 1)
    )
    assert list(first.edges) == sorted(first.edges, key=Edge.sort_key)


def test_unknown_evidence_yields_unknown_confidence() -> None:
    store = GraphStore()
    store.add_node(make_node("node:a", NodeKind.JOB))
    store.add_node(make_node("node:b", NodeKind.SINK))
    unknown = evidence(EvidenceClass.UNKNOWN, rule="A-POLICY-UNMODELLED")
    store.add_edge(
        make_edge(
            "node:a",
            "node:b",
            kind=EdgeKind.CAN_READ_VALUE,
            evidence_items=(evidence(EvidenceClass.DECLARED), unknown),
        )
    )
    stored = store.out_edges("node:a")[0]
    assert stored.confidence is EvidenceClass.UNKNOWN
