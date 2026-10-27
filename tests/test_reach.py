"""Best-path authority reach and UNKNOWN potential reach (M4)."""

from __future__ import annotations

from collections.abc import Iterable

from nhi_blast.analysis.reach import potential_reach, reach
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.ids import edge_id
from nhi_blast.core.models import Edge, EdgeKind, GraphData, Node, NodeKind
from nhi_blast.graph.store import GraphStore


def make_graph(
    edges: Iterable[tuple[EdgeKind, str, str, EvidenceClass, str]],
    *,
    session_edges: set[str] | None = None,
) -> GraphData:
    store = GraphStore()
    node_ids = {"start"}
    materialised = list(edges)
    if session_edges:
        node_ids.add("session")
    for _, src, dst, _, _ in materialised:
        node_ids.update((src, dst))
    for node_id in sorted(node_ids):
        store.add_node(
            Node(
                id=node_id,
                kind=NodeKind.CREDENTIAL if node_id == "session" else NodeKind.JOB,
                label=node_id,
                evidence=(Evidence(cls=EvidenceClass.DECLARED, rule="test.node", detail=node_id),),
            )
        )
    for kind, src, dst, confidence, detail in materialised:
        evidence = Evidence(cls=confidence, rule="test.edge", detail=detail)
        attrs = {"session_credential": "session"} if detail in (session_edges or set()) else {}
        store.add_edge(
            Edge(
                id=edge_id(kind.value, src, dst, (evidence,)),
                kind=kind,
                src=src,
                dst=dst,
                confidence=confidence,
                evidence=(evidence,),
                attrs=attrs,
            )
        )
    return store.data()


def one_edge(graph: GraphData, src: str, dst: str) -> Edge:
    return next(edge for edge in graph.edges if edge.src == src and edge.dst == dst)


def test_stronger_weakest_evidence_beats_a_shorter_path() -> None:
    graph = make_graph(
        [
            (EdgeKind.CAN_ASSUME, "start", "target", EvidenceClass.ASSUMED, "direct"),
            (EdgeKind.CAN_MINT, "start", "middle", EvidenceClass.DECLARED, "strong-1"),
            (EdgeKind.CAN_ASSUME, "middle", "target", EvidenceClass.DERIVED, "strong-2"),
        ]
    )

    path = reach(graph, ["start"])["target"]

    assert path.weakest is EvidenceClass.DERIVED
    assert path.hops == 2
    assert path.ids == (
        one_edge(graph, "start", "middle").id,
        one_edge(graph, "middle", "target").id,
    )


def test_fewer_hops_wins_when_weakest_evidence_is_equal() -> None:
    graph = make_graph(
        [
            (EdgeKind.CAN_ASSUME, "start", "target", EvidenceClass.ASSUMED, "direct"),
            (EdgeKind.CAN_MINT, "start", "middle", EvidenceClass.DECLARED, "long-1"),
            (EdgeKind.CAN_ASSUME, "middle", "target", EvidenceClass.ASSUMED, "long-2"),
        ]
    )

    path = reach(graph, ["start"])["target"]

    assert path.weakest is EvidenceClass.ASSUMED
    assert path.hops == 1
    assert path.ids == (one_edge(graph, "start", "target").id,)


def test_equal_strength_and_length_paths_use_lexicographic_edge_ids() -> None:
    graph = make_graph(
        [
            (EdgeKind.CAN_MINT, "start", "a", EvidenceClass.DERIVED, "a-1"),
            (EdgeKind.CAN_ASSUME, "a", "target", EvidenceClass.DERIVED, "a-2"),
            (EdgeKind.CAN_MINT, "start", "b", EvidenceClass.DERIVED, "b-1"),
            (EdgeKind.CAN_ASSUME, "b", "target", EvidenceClass.DERIVED, "b-2"),
        ]
    )
    through_a = (one_edge(graph, "start", "a").id, one_edge(graph, "a", "target").id)
    through_b = (one_edge(graph, "start", "b").id, one_edge(graph, "b", "target").id)

    assert reach(graph, ["start"])["target"].ids == min(through_a, through_b)


def test_unknown_edges_feed_only_potential_and_name_the_blocker() -> None:
    graph = make_graph(
        [
            (EdgeKind.CAN_MINT, "start", "known", EvidenceClass.DERIVED, "known"),
            (EdgeKind.CAN_ASSUME, "start", "unknown", EvidenceClass.UNKNOWN, "blocked"),
            (EdgeKind.CAN_READ_VALUE, "unknown", "potential", EvidenceClass.DERIVED, "after"),
        ]
    )

    confirmed = reach(graph, ["start"])
    potential = potential_reach(graph, ["start"], reachable=confirmed)

    assert set(confirmed) == {"start", "known"}
    assert potential.nodes == ("potential", "unknown")
    assert potential.edges == (one_edge(graph, "start", "unknown").id,)
    assert potential.unresolved_inputs == ("test.edge: blocked",)


def test_can_assume_reaches_the_attached_session_credential() -> None:
    graph = make_graph(
        [
            (EdgeKind.CAN_MINT, "start", "identity", EvidenceClass.DERIVED, "mint"),
            (EdgeKind.CAN_ASSUME, "identity", "role", EvidenceClass.DERIVED, "assume"),
        ],
        session_edges={"assume"},
    )

    paths = reach(graph, ["start"])

    assert paths["session"].ids == (
        one_edge(graph, "start", "identity").id,
        one_edge(graph, "identity", "role").id,
    )
    assert paths["session"].weakest is EvidenceClass.DERIVED
    assert paths["session"].hops == 2
