"""Independent path-order oracles and authority acquisition regressions."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any

import pytest

from nhi_blast.analysis.partition import partition_graph
from nhi_blast.analysis.reach import potential_reach, reach
from nhi_blast.analysis.rotation import plan_rotation
from nhi_blast.analysis.scenario import analyze_scenario
from nhi_blast.analysis.selectors import parse_selector, resolve_starts
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.models import Edge, EdgeKind, GraphData, Node, NodeKind


def _node(node_id: str, kind: NodeKind = NodeKind.JOB, **attrs: Any) -> Node:
    return Node(
        id=node_id,
        kind=kind,
        label=node_id,
        attrs=attrs,
        evidence=(Evidence(cls=EvidenceClass.DECLARED, rule="test.node"),),
    )


def _edge(
    edge_id: str,
    src: str,
    dst: str,
    confidence: EvidenceClass,
    kind: EdgeKind = EdgeKind.HOLDS,
    **attrs: Any,
) -> Edge:
    return Edge(
        id=edge_id,
        src=src,
        dst=dst,
        kind=kind,
        confidence=confidence,
        evidence=(Evidence(cls=confidence, rule="test.edge", detail=edge_id),),
        attrs=attrs,
    )


@pytest.mark.parametrize("suffix_kind", [EdgeKind.HOLDS, EdgeKind.CAN_ASSUME])
def test_weak_suffix_uses_shorter_weaker_prefix(suffix_kind: EdgeKind) -> None:
    graph = GraphData(
        nodes=tuple(_node(name) for name in ("start", "a", "merge", "target", "session")),
        edges=(
            _edge("01", "start", "a", EvidenceClass.DERIVED),
            _edge("02", "a", "merge", EvidenceClass.DECLARED),
            _edge("03", "start", "merge", EvidenceClass.ASSUMED),
            _edge(
                "04",
                "merge",
                "target",
                EvidenceClass.ASSUMED,
                suffix_kind,
                session_credential="session",
            ),
        ),
    )
    paths = reach(graph, ("start",))
    assert paths["merge"].order_key() == (1, 2, ("01", "02"))
    assert paths["target"].order_key() == (2, 2, ("03", "04"))
    if suffix_kind is EdgeKind.CAN_ASSUME:
        assert paths["session"].order_key() == (2, 2, ("03", "04"))


def test_weak_suffix_uses_lexicographically_smaller_weaker_prefix() -> None:
    graph = GraphData(
        nodes=tuple(_node(name) for name in ("start", "a", "b", "merge", "target")),
        edges=(
            _edge("30", "start", "a", EvidenceClass.DERIVED),
            _edge("31", "a", "merge", EvidenceClass.DECLARED),
            _edge("10", "start", "b", EvidenceClass.ASSUMED),
            _edge("11", "b", "merge", EvidenceClass.DECLARED),
            _edge("40", "merge", "target", EvidenceClass.ASSUMED),
        ),
    )
    paths = reach(graph, ("start",))
    assert paths["merge"].ids == ("30", "31")
    assert paths["target"].order_key() == (2, 3, ("10", "11", "40"))


def test_unknown_suffix_uses_shortest_path_without_entering_partition() -> None:
    graph = GraphData(
        nodes=(
            _node("start"),
            _node("a"),
            _node("merge"),
            _node("target", NodeKind.CREDENTIAL, lifetime="persistent"),
        ),
        edges=(
            _edge("01", "start", "a", EvidenceClass.DECLARED),
            _edge("02", "a", "merge", EvidenceClass.DECLARED),
            _edge("03", "start", "merge", EvidenceClass.ASSUMED),
            _edge("04", "merge", "target", EvidenceClass.UNKNOWN),
        ),
    )
    confirmed = reach(graph, ("start",))
    potential = potential_reach(graph, ("start",), reachable=confirmed)
    assert set(confirmed) == {"start", "a", "merge"}
    assert potential.nodes == ("target",)
    assert potential.edges == ("04",)
    assert potential.paths["target"].order_key() == (3, 2, ("03", "04"))
    assert partition_graph(graph, ("start",)).partition.Z == ()


_REFERENCE_CLASSES = {
    EvidenceClass.DECLARED: 0,
    EvidenceClass.DERIVED: 1,
    EvidenceClass.ASSUMED: 2,
    EvidenceClass.UNKNOWN: 3,
}
_REFERENCE_AUTHORITY = {
    EdgeKind.RUNS_IN,
    EdgeKind.HOLDS,
    EdgeKind.CAN_MINT,
    EdgeKind.CAN_ASSUME,
    EdgeKind.CAN_READ_VALUE,
    EdgeKind.STORES,
    EdgeKind.AUTHENTICATES_AS,
}


def _simple_path_oracle(
    graph: GraphData,
    starts: Sequence[str],
    *,
    include_unknown: bool = False,
) -> dict[str, tuple[int, int, tuple[str, ...]]]:
    """Enumerate full simple paths; do not prune or rank their prefixes."""
    adjacency: dict[str, list[tuple[str, Edge]]] = {}
    node_ids = {node.id for node in graph.nodes}
    for edge in graph.edges:
        if edge.kind not in _REFERENCE_AUTHORITY:
            continue
        if not include_unknown and edge.confidence is EvidenceClass.UNKNOWN:
            continue
        adjacency.setdefault(edge.src, []).append((edge.dst, edge))
        session = edge.attrs.get("session_credential")
        if edge.kind is EdgeKind.CAN_ASSUME and isinstance(session, str) and session in node_ids:
            adjacency[edge.src].append((session, edge))
    best: dict[str, tuple[int, int, tuple[str, ...]]] = {}

    def visit(node: str, visited: frozenset[str], ids: tuple[str, ...], worst: int) -> None:
        score = (worst, len(ids), ids)
        if node not in best or score < best[node]:
            best[node] = score
        for destination, edge in adjacency.get(node, ()):
            if destination not in visited:
                visit(
                    destination,
                    visited | {destination},
                    (*ids, edge.id),
                    max(worst, _REFERENCE_CLASSES[edge.confidence]),
                )

    for start in starts:
        visit(start, frozenset({start}), (), 0)
    return best


def test_600_graphs_match_independent_full_path_enumeration() -> None:
    random_source = random.Random(7421)
    for case in range(600):
        nodes = tuple(_node(str(index)) for index in range(6))
        edges = tuple(
            _edge(
                f"{source}{destination}",
                str(source),
                str(destination),
                random_source.choice(tuple(EvidenceClass)),
            )
            for source in range(6)
            for destination in range(6)
            if source != destination and random_source.random() < 0.25
        )
        graph = GraphData(nodes=nodes, edges=edges)
        starts = ("0", "1") if case % 4 == 0 else ("0",)
        expected = _simple_path_oracle(graph, starts)
        paths = reach(graph, starts)
        assert {node: path.order_key() for node, path in paths.items()} == expected, case
        all_expected = _simple_path_oracle(graph, starts, include_unknown=True)
        potential = potential_reach(graph, starts, reachable=paths)
        assert {node: path.order_key() for node, path in potential.paths.items()} == {
            node: score for node, score in all_expected.items() if node not in expected
        }, case
        permuted = GraphData(nodes=tuple(reversed(nodes)), edges=tuple(reversed(edges)))
        assert {
            node: path.order_key() for node, path in reach(permuted, starts).items()
        } == expected


@pytest.mark.parametrize("control", [EdgeKind.CAN_MODIFY, EdgeKind.CAN_READ_VALUE])
def test_stored_value_acquisition_requires_read_authority(control: EdgeKind) -> None:
    graph = GraphData(
        nodes=(
            _node("job"),
            _node("key", NodeKind.CREDENTIAL, lifetime="persistent"),
            _node("role", NodeKind.AWS_ROLE),
            _node("sink", NodeKind.SINK),
            _node("stored", NodeKind.CREDENTIAL, lifetime="persistent"),
        ),
        edges=(
            _edge("01", "job", "key", EvidenceClass.DECLARED),
            _edge("02", "key", "role", EvidenceClass.DERIVED, EdgeKind.AUTHENTICATES_AS),
            _edge("03", "role", "sink", EvidenceClass.DERIVED, control),
            _edge("04", "sink", "stored", EvidenceClass.ASSUMED, EdgeKind.STORES),
        ),
    )
    result = partition_graph(graph, ("job",))
    expected = {"key"} if control is EdgeKind.CAN_MODIFY else {"key", "stored"}
    assert {item.credential for item in result.partition.Z} == expected
    assert ("stored" in result.reach) is (control is EdgeKind.CAN_READ_VALUE)
    assert ("sink" in result.reach) is (control is EdgeKind.CAN_READ_VALUE)
    assert result.partition.R == ()
    assert result.partition.E == ()
    assert result.potential.nodes == ()


def test_write_authority_still_orders_independently_obtained_credentials() -> None:
    graph = GraphData(
        nodes=(
            _node("job"),
            _node("key", NodeKind.CREDENTIAL, lifetime="persistent"),
            _node("role", NodeKind.AWS_ROLE),
            _node("sink", NodeKind.SINK),
            _node("stored", NodeKind.CREDENTIAL, lifetime="persistent"),
        ),
        edges=(
            _edge("01", "job", "key", EvidenceClass.DECLARED),
            _edge("02", "job", "stored", EvidenceClass.DECLARED),
            _edge("03", "key", "role", EvidenceClass.DERIVED, EdgeKind.AUTHENTICATES_AS),
            _edge("04", "role", "sink", EvidenceClass.DERIVED, EdgeKind.CAN_MODIFY),
            _edge("05", "sink", "stored", EvidenceClass.ASSUMED, EdgeKind.STORES),
        ),
    )
    partition = partition_graph(graph, ("job",)).partition
    plan = plan_rotation(graph, partition, selector_kind="job", start_nodes=("job",))
    assert [tuple(item.id for item in step.credentials) for step in plan.rotation] == [
        ("key",),
        ("stored",),
    ]
    assert plan.rotation[1].depends_on == ("key",)


@pytest.mark.parametrize("ttl", [3600, 7200])
def test_role_compromise_supplies_hypothetical_session_without_minted_session(ttl: int) -> None:
    role_attrs: dict[str, Any] = {"address": "aws_iam_role.deploy"}
    if ttl != 3600:
        role_attrs["max_session_duration"] = ttl
    graph = GraphData(nodes=(_node("aws:role:deploy", NodeKind.AWS_ROLE, **role_attrs),))
    selector = parse_selector("role:aws_iam_role.deploy")
    starts = resolve_starts(selector, graph, jobs=())
    assert starts == ("aws:role:deploy",)
    result = analyze_scenario(graph, starts, selector=selector.raw, selector_kind="role")
    assert len(result.partition.E) == 1
    assert result.partition.E[0].ttl_seconds == ttl
    assert result.partition.R == ()
    assert result.partition.Z == ()
    assert result.start_nodes == starts
    assert result.partition.E[0].credential in result.reach
    assert tuple(node.id for node in result.synthetic_nodes) == (result.partition.E[0].credential,)
    assert any(item.rule == "A-STS-TTL" for item in result.rotation_plan.containment[0].evidence)
    assert any("hypothetical" in note.lower() for note in result.notes)
    assert result.to_report().partition.E == result.partition.E
    assert graph.nodes == (_node("aws:role:deploy", NodeKind.AWS_ROLE, **role_attrs),)
    assert analyze_scenario(graph, starts, selector=selector.raw, selector_kind="role") == result


def test_role_selector_reuses_only_sts_session_credentials() -> None:
    graph = GraphData(
        nodes=(
            _node("aws:role:deploy", NodeKind.AWS_ROLE, address="aws_iam_role.deploy"),
            _node(
                "session",
                NodeKind.CREDENTIAL,
                role="aws:role:deploy",
                credential_kind="STS_SESSION",
                lifetime="session_ttl",
                ttl_seconds=1800,
            ),
            _node(
                "not-session",
                NodeKind.CREDENTIAL,
                role="aws:role:deploy",
                credential_kind="GENERIC_SECRET",
                lifetime="persistent",
            ),
        ),
    )
    selector = parse_selector("role:aws_iam_role.deploy")
    starts = resolve_starts(selector, graph, jobs=())
    assert starts == ("aws:role:deploy", "session")
    result = analyze_scenario(graph, starts, selector=selector.raw, selector_kind="role")
    assert [(entry.credential, entry.ttl_seconds) for entry in result.partition.E] == [
        ("session", 1800),
    ]
    assert result.partition.Z == ()
    assert result.synthetic_nodes == ()


def test_repo_writer_does_not_reuse_a_persistent_credential_as_an_sts_session() -> None:
    graph = GraphData(
        nodes=(
            _node("job"),
            _node("role", NodeKind.AWS_ROLE, repo_write_accepted=True),
            _node(
                "key",
                NodeKind.CREDENTIAL,
                role="role",
                credential_kind="GENERIC_SECRET",
                lifetime="persistent",
            ),
        ),
    )
    result = analyze_scenario(graph, ("job",), selector="repo-write", selector_kind="repo-write")
    assert len(result.partition.E) == 1
    assert result.partition.Z == ()
    assert result.partition.E[0].credential != "key"
    assert len(result.synthetic_nodes) == 1


def test_multi_confidence_traversal_respects_cooperative_stop() -> None:
    graph = GraphData(
        nodes=tuple(_node(name) for name in ("start", "a", "b", "target")),
        edges=(
            _edge("01", "start", "a", EvidenceClass.DECLARED),
            _edge("02", "start", "b", EvidenceClass.ASSUMED),
            _edge("03", "a", "target", EvidenceClass.DECLARED),
            _edge("04", "b", "target", EvidenceClass.ASSUMED),
        ),
    )
    checks = 0

    def stopped() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 2

    paths = reach(graph, ("start",), should_stop=stopped)
    assert set(paths) == {"start", "a", "b"}
    assert "target" not in paths
    assert checks == 2
