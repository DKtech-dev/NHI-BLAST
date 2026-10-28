"""Deterministic layered graph layout and vector semantics (report graph)."""

from __future__ import annotations

import json
from itertools import pairwise

from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.models import Edge, EdgeKind, GraphData, Node, NodeKind, Report
from nhi_blast.report.graph_layout import LAYOUT_FORMAT, build_layout, render_graph_svg
from nhi_blast.report.ui import TEMPLATE
from tests.report_support import make_report

_JOB = "job:.github/workflows/release.yml#publish"


def _node(node_id: str, kind: NodeKind, label: str) -> Node:
    return Node(id=node_id, kind=kind, label=label, attrs={})


def _edge(
    edge_id: str, src: str, dst: str, confidence: EvidenceClass, kind: EdgeKind = EdgeKind.RUNS_IN
) -> Edge:
    return Edge(
        id=edge_id,
        kind=kind,
        src=src,
        dst=dst,
        confidence=confidence,
        evidence=(Evidence(cls=confidence, rule="test"),),
    )


def _layered_report() -> Report:
    nodes = (
        _node("repo:acme/shop", NodeKind.REPOSITORY, "acme/shop"),
        _node("wf:release.yml", NodeKind.WORKFLOW, "release"),
        _node(_JOB, NodeKind.JOB, "publish"),
        _node("action:checkout@" + "a" * 40, NodeKind.ACTION_REF, "actions/checkout@" + "a" * 40),
        _node(
            "oidc:token.actions.githubusercontent.com",
            NodeKind.AWS_OIDC_PROVIDER,
            "token.actions.githubusercontent.com",
        ),
        _node("role:deploy", NodeKind.AWS_ROLE, "deploy-prod"),
        _node("sink:db", NodeKind.SINK, "prod/db-master"),
        _node("cred:db", NodeKind.CREDENTIAL, "database password"),
        _node("external:vendor", NodeKind.EXTERNAL_TARGET, "vendor.example"),
    )
    edges = (
        _edge(
            "e-repo",
            "repo:acme/shop",
            "wf:release.yml",
            EvidenceClass.DECLARED,
            EdgeKind.CONTAINS,
        ),
        _edge("e-job", "wf:release.yml", _JOB, EvidenceClass.DERIVED, EdgeKind.CONTAINS),
        _edge("e-action", _JOB, "action:checkout@" + "a" * 40, EvidenceClass.ASSUMED),
        _edge("e-oidc", _JOB, "oidc:token.actions.githubusercontent.com", EvidenceClass.UNKNOWN),
        _edge(
            "e-role",
            "oidc:token.actions.githubusercontent.com",
            "role:deploy",
            EvidenceClass.DECLARED,
            EdgeKind.CAN_ASSUME,
        ),
        _edge("e-sink", "role:deploy", "sink:db", EvidenceClass.DERIVED, EdgeKind.CAN_READ_VALUE),
        _edge("e-cred", "sink:db", "cred:db", EvidenceClass.DECLARED, EdgeKind.STORES),
        _edge("e-cycle", "role:deploy", _JOB, EvidenceClass.ASSUMED, EdgeKind.CAN_ASSUME),
        _edge("e-external", _JOB, "external:vendor", EvidenceClass.UNKNOWN),
    )
    return make_report().model_copy(
        update={"graph": GraphData(nodes=nodes, edges=edges), "scenarios": ()}
    )


def test_layout_is_deterministic_and_stage_ordered() -> None:
    report = _layered_report()
    first = build_layout(report)
    second = build_layout(report)

    assert first == second
    assert first["format"] == LAYOUT_FORMAT
    assert [stage["key"] for stage in first["stages"]] == [
        "repository",
        "workflows",
        "jobs",
        "identity",
        "roles",
        "stores",
        "credentials",
    ]
    xs = [stage["x"] for stage in first["stages"]]
    assert xs == sorted(xs)
    assert all(left < right for left, right in pairwise(xs))
    assert first["counts"]["nodes"] == 9
    assert first["counts"]["edges"] == 9


def test_nodes_never_overlap_within_a_stage() -> None:
    layout = build_layout(_layered_report())
    stages: dict[int, list[dict[str, object]]] = {}
    for node in layout["nodes"]:
        stages.setdefault(int(node["stage"]), []).append(node)

    for nodes in stages.values():
        ordered = sorted(nodes, key=lambda item: float(item["y"]))
        for previous, current in pairwise(ordered):
            previous_bottom = float(previous["y"]) + float(previous["height"])
            assert float(current["y"]) >= previous_bottom
        for node in ordered:
            x = float(node["x"])
            y = float(node["y"])
            width = float(node["width"])
            height = float(node["height"])
            assert width >= 112
            assert height >= 50
            assert x >= 0
            assert y >= 0
            assert x + width <= float(layout["width"])
            assert y + height <= float(layout["height"])


def test_every_edge_and_node_carries_a_rendered_identity() -> None:
    report = _layered_report()
    layout = build_layout(report)
    svg = render_graph_svg(layout, report)

    for node in layout["nodes"]:
        node_id = str(node["id"])
        assert f'data-id="{node_id}"' in svg
        assert f"id {node_id}" in svg
    for edge in layout["edges"]:
        edge_id = str(edge["id"])
        assert f'data-id="{edge_id}"' in svg
        assert edge["path"]
        assert str(edge["src"]) in svg
        assert str(edge["dst"]) in svg


def test_edges_encode_confidence_through_style_classes() -> None:
    report = _layered_report()
    svg = render_graph_svg(build_layout(report), report)

    for confidence in ("declared", "derived", "assumed", "unknown"):
        assert f"conf-{confidence}" in svg
    assert ".gedge.conf-assumed .gedge-line" in _template_css()
    assert "stroke-dasharray: 7 4" in _template_css()
    assert ".gedge.conf-unknown .gedge-line" in _template_css()
    assert "stroke-dasharray: 2 4" in _template_css()


def test_layout_marks_entrypoints_and_keeps_full_labels_in_accessibility_metadata() -> None:
    report = make_report()
    svg = render_graph_svg(build_layout(report), report)

    assert 'class="gnode kind-job stage-jobs is-entry"' in svg
    assert 'aria-label="publish, job, id ' + _JOB + ', entrypoint"' in svg
    assert "database password" in svg
    assert 'role="button"' in svg
    assert 'tabindex="-1"' in svg


def test_layout_is_vector_only_and_free_of_active_content() -> None:
    report = make_report(hostile=True)
    svg = render_graph_svg(build_layout(report), report)

    assert "<image" not in svg
    assert "<foreignObject" not in svg
    assert "<script" not in svg
    assert "<iframe" not in svg
    assert "<img" not in svg
    assert "javascript:" not in svg
    assert "&lt;/script&gt;" in svg


def test_empty_graph_renders_an_explicit_placeholder() -> None:
    report = make_report().model_copy(update={"graph": GraphData(), "scenarios": ()})
    layout = build_layout(report)
    svg = render_graph_svg(layout, report)

    assert layout["counts"]["nodes"] == 0
    assert layout["counts"]["edges"] == 0
    assert "The report graph has no renderable nodes." in svg
    assert "0 nodes and 0 edges arranged in 0 authority stages." in svg


def test_rendering_limit_is_reported_when_nodes_are_omitted() -> None:
    report = _layered_report()
    layout = build_layout(report, max_nodes=4)
    svg = render_graph_svg(layout, report)
    counts = layout["counts"]

    assert counts["nodes"] == 4
    assert counts["total_nodes"] == 9
    assert counts["omitted_nodes"] == 5
    assert "Rendering limit: 5 nodes are not drawn" in svg
    assert "the JSON report contains the complete graph" in svg


def test_description_uses_singular_forms_for_one_item() -> None:
    report = make_report().model_copy(
        update={
            "graph": GraphData(nodes=(_node("role:one", NodeKind.AWS_ROLE, "one"),)),
            "scenarios": (),
        }
    )
    svg = render_graph_svg(build_layout(report), report)

    assert "1 node and 0 edges arranged in 1 authority stage." in svg


def test_layout_serialises_as_stable_json() -> None:
    report = _layered_report()
    first = json.dumps(build_layout(report), sort_keys=True)
    second = json.dumps(build_layout(report), sort_keys=True)

    assert first == second


def _template_css() -> str:
    return TEMPLATE.split("<style>", 1)[1].split("</style>", 1)[0]
