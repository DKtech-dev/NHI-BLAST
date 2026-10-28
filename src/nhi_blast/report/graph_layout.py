"""Deterministic layered layout and vector artwork for the authority graph.

The geometry is computed here rather than in the browser so the interactive
report and the print page share one layout. Nodes occupy semantic columns, long
or backward edges travel outside the columns in reserved gutters, and labels
wrap with measured line widths instead of being clipped at a fixed width. No
third-party layout engine is required.
"""

from __future__ import annotations

import html
import math
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from nhi_blast.core.models import Edge, Node, NodeKind, Report

LAYOUT_FORMAT = "nhi-blast-graph-layout/1"
MAX_RENDER_NODES = 1500
MAX_RAIL_LANES = 10

_STAGE_DEFS: tuple[tuple[str, str, tuple[NodeKind, ...]], ...] = (
    ("repository", "Repository", (NodeKind.REPOSITORY,)),
    ("workflows", "Workflows", (NodeKind.WORKFLOW,)),
    ("jobs", "Jobs", (NodeKind.JOB,)),
    (
        "identity",
        "Actions & identity",
        (NodeKind.ACTION_REF, NodeKind.OIDC_IDENTITY, NodeKind.AWS_OIDC_PROVIDER),
    ),
    ("roles", "AWS roles", (NodeKind.AWS_ROLE,)),
    ("stores", "Stores & targets", (NodeKind.SINK, NodeKind.EXTERNAL_TARGET)),
    ("credentials", "Credentials", (NodeKind.CREDENTIAL,)),
)
_STAGE_INDEX: dict[NodeKind, int] = {
    kind: index for index, (_key, _label, kinds) in enumerate(_STAGE_DEFS) for kind in kinds
}
_STAGE_LABELS = tuple((key, label) for key, label, _kinds in _STAGE_DEFS)

_SHAPES: dict[NodeKind, str] = {
    NodeKind.REPOSITORY: "round-rectangle",
    NodeKind.WORKFLOW: "cut-rectangle",
    NodeKind.JOB: "round-rectangle",
    NodeKind.ACTION_REF: "rhomboid",
    NodeKind.OIDC_IDENTITY: "ellipse",
    NodeKind.AWS_OIDC_PROVIDER: "ellipse",
    NodeKind.AWS_ROLE: "hexagon",
    NodeKind.SINK: "barrel",
    NodeKind.CREDENTIAL: "round-tag",
    NodeKind.EXTERNAL_TARGET: "rhomboid",
}

_CREDENTIAL_WORDS = {
    "GITHUB_TOKEN": "GitHub token",
    "OIDC_REQUEST_TOKEN": "OIDC request token",
    "OIDC_JWT": "OIDC JWT",
    "STS_SESSION": "STS session",
    "GITHUB_SECRET": "GitHub secret",
    "AWS_ACCESS_KEY": "AWS access key",
    "DATABASE_PASSWORD": "Database password",
    "PRIVATE_KEY": "Private key",
    "API_KEY": "API key",
    "API_TOKEN": "API token",
    "WEBHOOK_URL": "Webhook URL",
    "GENERIC_SECRET": "Generic secret",
}
_SINK_WORDS = {
    "secretsmanager_secret": "Secrets Manager",
    "ssm_parameter": "SSM parameter",
    "github_secret": "GitHub secret",
    "environment_secret": "Environment secret",
    "variable": "Repository variable",
}

_MARGIN_X = 28.0
_MARGIN_TOP = 18.0
_MARGIN_BOTTOM = 20.0
_HEADER_HEIGHT = 34.0
_COLUMN_GAP = 34.0
_COLUMN_PAD = 26.0
_NODE_GAP = 12.0
_NODE_PAD_X = 14.0
_NODE_PAD_Y = 8.0
_LABEL_SIZE = 14.0
_LABEL_LINE = 16.5
_META_SIZE = 11.5
_META_LINE = 14.5
_BADGE_SIZE = 9.5
_BADGE_LINE = 13.0
_MAX_TEXT_WIDTH = 184.0
_MIN_NODE_WIDTH = 112.0
_MAX_NODE_WIDTH = 232.0
_RAIL_START = 30.0
_RAIL_STEP = 12.0
_CORNER = 8.0
_GUTTER_INSET = 6.0
_GUTTER_LANE = 5.0


@dataclass
class _Box:
    node: Node
    stage: int
    lines: tuple[str, ...]
    meta_lines: tuple[str, ...]
    shape: str
    width: float
    height: float
    entry: bool
    critical: bool
    x: float = 0.0
    y: float = 0.0

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class _RoutedEdge:
    edge: Edge
    path: str
    lane: int
    long: bool


def build_layout(report: Report, *, max_nodes: int = MAX_RENDER_NODES) -> dict[str, Any]:
    """Return a deterministic, renderable layout for the report graph."""
    graph = report.graph
    entry_ids = {node_id for scenario in report.scenarios for node_id in scenario.start_nodes}
    all_nodes = tuple(sorted(graph.nodes, key=_node_sort_key))
    omitted_nodes = 0
    if len(all_nodes) > max_nodes:
        all_nodes = _select_render_nodes(all_nodes, graph.edges, entry_ids, max_nodes)
        omitted_nodes = len(graph.nodes) - len(all_nodes)

    rendered_ids = {node.id for node in all_nodes}
    visible_entries = entry_ids & rendered_ids
    boxes = [_make_box(node, entry=node.id in visible_entries) for node in all_nodes]
    original_stages = sorted({box.stage for box in boxes})
    stage_number = {stage: index for index, stage in enumerate(original_stages)}
    for box in boxes:
        box.stage = stage_number[box.stage]
    active_stages = sorted({box.stage for box in boxes})

    edges = tuple(
        sorted(
            (edge for edge in graph.edges if edge.src in rendered_ids and edge.dst in rendered_ids),
            key=_edge_sort_key,
        )
    )
    omitted_edges = len(graph.edges) - len(edges)

    if not boxes:
        return _empty_layout(len(graph.nodes), len(graph.edges), omitted_nodes)

    by_id = {box.node.id: box for box in boxes}
    _order_columns(boxes, edges)
    columns = _place_boxes(boxes, active_stages)
    content_bottom = max(box.bottom for box in boxes)
    routed, rail_lanes = _route_edges(edges, by_id, columns, content_bottom)
    rail_bottom = (
        content_bottom + _RAIL_START + (rail_lanes - 1) * _RAIL_STEP
        if rail_lanes
        else content_bottom
    )
    column_right = max(left + width for left, width in columns.values())
    right = max(column_right + 26.0, *(box.right for box in boxes))
    width = right + _MARGIN_X
    height = rail_bottom + _MARGIN_BOTTOM
    stage_rows = [
        {
            "index": stage + 1,
            "key": _STAGE_LABELS[original_stages[stage]][0],
            "label": _STAGE_LABELS[original_stages[stage]][1],
            "x": _round(columns[stage][0]),
            "y": _round(_MARGIN_TOP),
            "width": _round(columns[stage][1]),
            "height": _round(content_bottom - _MARGIN_TOP + 12),
            "count": sum(1 for box in boxes if box.stage == stage),
        }
        for stage in active_stages
    ]
    node_rows = [
        {
            "id": box.node.id,
            "kind": box.node.kind.value,
            "label": box.node.label,
            "display_label": list(box.lines),
            "meta_lines": list(box.meta_lines),
            "shape": box.shape,
            "stage": box.stage,
            "stage_key": _STAGE_LABELS[_STAGE_INDEX[box.node.kind]][0],
            "x": _round(box.x),
            "y": _round(box.y),
            "cx": _round(box.x + box.width / 2),
            "cy": _round(box.y + box.height / 2),
            "width": _round(box.width),
            "height": _round(box.height),
            "entry": box.entry,
            "critical": box.critical,
        }
        for box in sorted(boxes, key=_box_draw_key)
    ]
    edge_rows = [
        {
            "id": item.edge.id,
            "kind": item.edge.kind.value,
            "confidence": item.edge.confidence.value,
            "src": item.edge.src,
            "dst": item.edge.dst,
            "path": item.path,
            "long": item.long,
        }
        for item in routed
    ]
    return {
        "format": LAYOUT_FORMAT,
        "width": _round(width),
        "height": _round(height),
        "content_bottom": _round(content_bottom),
        "stages": stage_rows,
        "nodes": node_rows,
        "edges": edge_rows,
        "counts": {
            "nodes": len(node_rows),
            "edges": len(edge_rows),
            "total_nodes": len(graph.nodes),
            "total_edges": len(graph.edges),
            "omitted_nodes": omitted_nodes,
            "omitted_edges": omitted_edges,
        },
    }


def render_graph_svg(layout: Mapping[str, Any], report: Report) -> str:
    """Render the layout as an inline, print-safe SVG document fragment."""
    width = _number(layout.get("width"))
    height = _number(layout.get("height"))
    nodes = layout.get("nodes") or []
    edges = layout.get("edges") or []
    description = _graph_description(report, layout)
    if not nodes:
        return (
            '<svg id="graph-svg" class="graph-svg" viewBox="0 0 640 160" '
            'width="640" height="160" data-width="640" data-height="160" '
            'preserveAspectRatio="xMidYMid meet" role="group" '
            'aria-labelledby="graph-svg-title graph-svg-desc">'
            '<title id="graph-svg-title">Authority graph</title>'
            f'<desc id="graph-svg-desc">{html.escape(description, quote=False)}</desc>'
            '<text class="graph-empty" x="320" y="92" text-anchor="middle">'
            "The report graph has no renderable nodes.</text></svg>"
        )

    parts: list[str] = [
        f'<svg id="graph-svg" class="graph-svg" viewBox="0 0 {_fmt(width)} {_fmt(height)}" '
        f'width="{_fmt(width)}" height="{_fmt(height)}" '
        f'data-width="{_fmt(width)}" data-height="{_fmt(height)}" '
        'preserveAspectRatio="xMidYMid meet" role="group" '
        'aria-labelledby="graph-svg-title graph-svg-desc">',
        '<title id="graph-svg-title">Authority graph</title>',
        f'<desc id="graph-svg-desc">{html.escape(description, quote=False)}</desc>',
        '<defs><marker id="graph-arrow" viewBox="0 0 8 8" refX="7.2" refY="4" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L8,4 L0,8 Z" class="graph-arrow-head"></path></marker></defs>',
        '<g class="graph-viewport" id="graph-viewport">',
        '<g class="graph-stages" aria-hidden="true">',
    ]
    for stage in layout.get("stages") or []:
        x = _number(stage.get("x"))
        y = _number(stage.get("y"))
        stage_width = _number(stage.get("width"))
        stage_height = _number(stage.get("height"))
        label = html.escape(str(stage.get("label", "")), quote=False)
        key = html.escape(str(stage.get("key", "")), quote=True)
        count = int(stage.get("count", 0))
        index = f"{int(stage.get('index', 0)):02d}"
        parts.append(
            f'<g class="gstage" data-stage="{key}">'
            f'<rect class="gstage-band" x="{_fmt(x)}" y="{_fmt(y)}" '
            f'width="{_fmt(stage_width)}" height="{_fmt(stage_height)}" rx="3"></rect>'
            f'<text class="gstage-index" x="{_fmt(x + 12)}" y="{_fmt(y + 20)}">{index}</text>'
            f'<text class="gstage-title" x="{_fmt(x + 32)}" y="{_fmt(y + 20)}">{label}</text>'
            f'<text class="gstage-count" x="{_fmt(x + stage_width - 12)}" y="{_fmt(y + 20)}" '
            f'text-anchor="end">{count}</text></g>'
        )
    parts.append('</g><g class="graph-edges">')
    for edge in edges:
        confidence = html.escape(str(edge.get("confidence", "unknown")), quote=True)
        kind = html.escape(str(edge.get("kind", "")), quote=False)
        src = html.escape(str(edge.get("src", "")), quote=False)
        dst = html.escape(str(edge.get("dst", "")), quote=False)
        edge_id = html.escape(str(edge.get("id", "")), quote=True)
        path = html.escape(str(edge.get("path", "")), quote=True)
        parts.append(
            f'<g class="gedge conf-{confidence}" data-id="{edge_id}" aria-hidden="true">'
            f"<title>{kind} edge, confidence {confidence}: {src} to {dst}</title>"
            f'<path class="gedge-hit" d="{path}"></path>'
            f'<path class="gedge-line" d="{path}" marker-end="url(#graph-arrow)"></path></g>'
        )
    parts.append('</g><g class="graph-nodes">')
    for node in nodes:
        parts.append(_render_node(node))
    parts.append("</g></g></svg>")
    return "".join(parts)


def _render_node(node: Mapping[str, Any]) -> str:
    x = _number(node.get("x"))
    y = _number(node.get("y"))
    width = _number(node.get("width"))
    height = _number(node.get("height"))
    shape = str(node.get("shape", "round-rectangle"))
    kind = str(node.get("kind", ""))
    node_id = str(node.get("id", ""))
    label = _clean(str(node.get("label", "")))
    lines = [_clean(str(line)) for line in node.get("display_label") or ()]
    meta_lines = [_clean(str(line)) for line in node.get("meta_lines") or ()]
    entry = bool(node.get("entry"))
    critical = bool(node.get("critical"))
    kind_class = kind.lower().replace("_", "-")
    classes = ["gnode", f"kind-{kind_class}", f"stage-{node.get('stage_key', '')}"]
    if entry:
        classes.append("is-entry")
    if critical:
        classes.append("is-critical")
    accessible = f"{label}, {kind.replace('_', ' ').lower()}, id {node_id}"
    if entry:
        accessible += ", entrypoint"
    if critical:
        accessible += ", critical resource"
    parts = [
        f'<g class="{" ".join(classes)}" data-id="{html.escape(node_id, quote=True)}" '
        f'data-kind="{html.escape(kind, quote=True)}" data-stage="{int(node.get("stage", 0))}" '
        f'data-x="{_fmt(x)}" data-y="{_fmt(y)}" data-width="{_fmt(width)}" '
        f'data-height="{_fmt(height)}" role="button" tabindex="-1" '
        f'aria-label="{html.escape(accessible, quote=True)}">',
        f"<title>{html.escape(label, quote=False)} — {html.escape(kind, quote=False)} — "
        f"{html.escape(node_id, quote=False)}</title>",
        f'<rect class="gnode-halo" x="{_fmt(x - 5)}" y="{_fmt(y - 5)}" '
        f'width="{_fmt(width + 10)}" height="{_fmt(height + 10)}" rx="10"></rect>',
    ]
    if entry:
        parts.append(
            f'<rect class="gnode-entry-frame" x="{_fmt(x - 3)}" y="{_fmt(y - 3)}" '
            f'width="{_fmt(width + 6)}" height="{_fmt(height + 6)}" rx="9"></rect>'
        )
    parts.append(_shape_markup(shape, x, y, width, height))
    parts.append(_text_markup(x + width / 2, y, height, lines, meta_lines, entry, critical))
    parts.append("</g>")
    return "".join(parts)


def _shape_markup(shape: str, x: float, y: float, width: float, height: float) -> str:
    if shape == "ellipse":
        return (
            f'<ellipse class="gnode-shape" cx="{_fmt(x + width / 2)}" '
            f'cy="{_fmt(y + height / 2)}" rx="{_fmt(width / 2)}" '
            f'ry="{_fmt(height / 2)}"></ellipse>'
        )
    if shape == "cut-rectangle":
        cut = 10.0
        d = (
            f"M{_fmt(x + cut)},{_fmt(y)} H{_fmt(x + width)} "
            f"V{_fmt(y + height - cut)} L{_fmt(x + width - cut)},{_fmt(y + height)} "
            f"H{_fmt(x)} V{_fmt(y + cut)} Z"
        )
        return f'<path class="gnode-shape" d="{d}"></path>'
    if shape == "rhomboid":
        d = (
            f"M{_fmt(x + 12)},{_fmt(y)} H{_fmt(x + width)} "
            f"L{_fmt(x + width - 12)},{_fmt(y + height)} H{_fmt(x)} Z"
        )
        return f'<path class="gnode-shape" d="{d}"></path>'
    if shape == "hexagon":
        d = (
            f"M{_fmt(x + 14)},{_fmt(y)} H{_fmt(x + width - 14)} "
            f"L{_fmt(x + width)},{_fmt(y + height / 2)} "
            f"L{_fmt(x + width - 14)},{_fmt(y + height)} H{_fmt(x + 14)} "
            f"L{_fmt(x)},{_fmt(y + height / 2)} Z"
        )
        return f'<path class="gnode-shape" d="{d}"></path>'
    if shape == "barrel":
        d = (
            f"M{_fmt(x + 9)},{_fmt(y)} H{_fmt(x + width - 9)} "
            f"Q{_fmt(x + width - 2)},{_fmt(y)} {_fmt(x + width)},{_fmt(y + height / 2)} "
            f"Q{_fmt(x + width - 2)},{_fmt(y + height)} {_fmt(x + width - 9)},"
            f"{_fmt(y + height)} H{_fmt(x + 9)} "
            f"Q{_fmt(x + 2)},{_fmt(y + height)} {_fmt(x)},{_fmt(y + height / 2)} "
            f"Q{_fmt(x + 2)},{_fmt(y)} {_fmt(x + 9)},{_fmt(y)} Z"
        )
        return f'<path class="gnode-shape" d="{d}"></path>'
    if shape == "round-tag":
        d = (
            f"M{_fmt(x + 8)},{_fmt(y)} H{_fmt(x + width - 12)} "
            f"L{_fmt(x + width)},{_fmt(y + height / 2)} "
            f"L{_fmt(x + width - 12)},{_fmt(y + height)} H{_fmt(x + 8)} "
            f"Q{_fmt(x)},{_fmt(y + height)} {_fmt(x)},{_fmt(y + height - 8)} "
            f"V{_fmt(y + 8)} Q{_fmt(x)},{_fmt(y)} {_fmt(x + 8)},{_fmt(y)} Z"
        )
        return f'<path class="gnode-shape" d="{d}"></path>'
    return (
        f'<rect class="gnode-shape" x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(width)}" '
        f'height="{_fmt(height)}" rx="{_fmt(min(8.0, height / 3))}"></rect>'
    )


def _text_markup(
    center_x: float,
    top: float,
    height: float,
    lines: list[str],
    meta_lines: list[str],
    entry: bool,
    critical: bool,
) -> str:
    rows = max(len(lines), 1)
    badges = bool(entry or critical)
    content_height = (
        rows * _LABEL_LINE + len(meta_lines) * _META_LINE + (_BADGE_LINE if badges else 0)
    )
    cursor = top + (height - content_height) / 2
    first_baseline = cursor + 12
    parts = ['<text class="gnode-label" text-anchor="middle">']
    for index, line in enumerate(lines or [" "]):
        parts.append(
            f'<tspan x="{_fmt(center_x)}" y="{_fmt(first_baseline + index * _LABEL_LINE)}">'
            f"{html.escape(line, quote=False)}</tspan>"
        )
    parts.append("</text>")
    meta_baseline = first_baseline + rows * _LABEL_LINE
    if meta_lines:
        parts.append(
            f'<text class="gnode-meta" x="{_fmt(center_x)}" '
            f'y="{_fmt(meta_baseline)}" text-anchor="middle">'
        )
        for index, line in enumerate(meta_lines):
            parts.append(
                f'<tspan x="{_fmt(center_x)}" y="{_fmt(meta_baseline + index * _META_LINE)}">'
                f"{html.escape(line, quote=False)}</tspan>"
            )
        parts.append("</text>")
    if badges:
        baseline = meta_baseline + len(meta_lines) * _META_LINE
        parts.append(
            f'<text class="gnode-badges" x="{_fmt(center_x)}" y="{_fmt(baseline)}" '
            f'text-anchor="middle">'
        )
        if entry:
            parts.append('<tspan class="badge-entry">ENTRY</tspan>')
        if entry and critical:
            parts.append('<tspan class="badge-sep"> · </tspan>')
        if critical:
            parts.append('<tspan class="badge-critical">CRITICAL</tspan>')
        parts.append("</text>")
    return "".join(parts)


def _make_box(node: Node, *, entry: bool) -> _Box:
    label, meta = _display_parts(node)
    lines = _wrap(label, _MAX_TEXT_WIDTH, _LABEL_SIZE, max_lines=6)
    padding = _shape_padding(node.kind)
    label_width = max((_text_width(line, _LABEL_SIZE) for line in lines), default=0.0)
    meta_width = min(max(_text_width(meta, _META_SIZE), 96.0), 130.0) if meta else 0.0
    critical = _is_critical(node)
    badge_width = 0.0
    if entry or critical:
        badge = "ENTRY · " if entry and critical else "ENTRY" if entry else "CRITICAL"
        badge_width = _text_width(badge, _BADGE_SIZE)
    width = min(
        _MAX_NODE_WIDTH,
        max(
            _MIN_NODE_WIDTH,
            label_width + _NODE_PAD_X * 2 + padding,
            meta_width + _NODE_PAD_X * 2 + padding,
            badge_width + _NODE_PAD_X * 2 + padding,
        ),
    )
    inner_width = width - _NODE_PAD_X * 2 - padding
    lines = _wrap(label, inner_width, _LABEL_SIZE, max_lines=6)
    meta_lines = _wrap(meta, inner_width, _META_SIZE, max_lines=3) if meta else []
    height = (
        _NODE_PAD_Y * 2
        + len(lines) * _LABEL_LINE
        + len(meta_lines) * _META_LINE
        + (_BADGE_LINE if entry or critical else 0)
    )
    return _Box(
        node=node,
        stage=_STAGE_INDEX[node.kind],
        lines=tuple(lines),
        meta_lines=tuple(meta_lines),
        shape=_SHAPES[node.kind],
        width=width,
        height=max(height, 50.0),
        entry=entry,
        critical=critical,
    )


def _display_parts(node: Node) -> tuple[str, str]:
    label = _clean(node.label).strip() or _clean(node.id)
    attrs = node.attrs
    kind = node.kind
    if kind is NodeKind.ACTION_REF:
        raw = _clean(str(attrs.get("raw") or label))
        name, separator, ref = raw.rpartition("@")
        if separator and len(ref) > 16:
            ref = ref[:12] + "…"
        display = f"{name}@{ref}" if separator else raw
        if attrs.get("mutable"):
            return display, "Action · mutable"
        if str(attrs.get("pin_kind") or "") == "SHA":
            return display, "Action · SHA pin"
        return display, "Action"
    if kind is NodeKind.WORKFLOW:
        path = _basename(str(attrs.get("path") or ""))
        return label, f"Workflow{f' · {path}' if path else ''}"
    if kind is NodeKind.JOB:
        path = _basename(str(attrs.get("path") or attrs.get("workflow") or ""))
        return label, f"Job{f' · {path}' if path else ''}"
    if kind is NodeKind.REPOSITORY:
        branch = str(attrs.get("default_branch") or "")
        return label, f"Repository{f' · {branch}' if branch else ''}"
    if kind is NodeKind.AWS_ROLE:
        name = _clean(str(attrs.get("name") or "")).strip()
        if not name:
            arn = _clean(str(attrs.get("arn") or label))
            name = arn.rsplit("/", 1)[-1].strip() or label
        duration = attrs.get("max_session_duration")
        suffix = f" · {_duration(duration)} session" if isinstance(duration, int) else ""
        return name, f"IAM role{suffix}"
    if kind is NodeKind.SINK:
        sink_type = _SINK_WORDS.get(str(attrs.get("sink_type") or ""), "")
        return label, sink_type or "Credential store"
    if kind is NodeKind.CREDENTIAL:
        credential = _CREDENTIAL_WORDS.get(str(attrs.get("credential_kind") or ""), "Credential")
        job = str(attrs.get("job") or "")
        window = str(attrs.get("survival_window") or "")
        ttl = attrs.get("ttl_seconds")
        if job:
            detail = f"job {job.rsplit('#', 1)[-1]}"
        elif isinstance(ttl, int):
            detail = f"up to {_duration(ttl)}"
        elif window:
            detail = _lifetime(window)
        elif credential == "STS session":
            detail = ""
        else:
            detail = _lifetime(str(attrs.get("lifetime") or ""))
        return label, " · ".join(part for part in (credential, detail) if part)
    if kind is NodeKind.OIDC_IDENTITY:
        audience = str(attrs.get("audience") or "")
        return "OIDC identity", audience or "Federated identity"
    if kind is NodeKind.AWS_OIDC_PROVIDER:
        return label, "OIDC provider"
    if kind is NodeKind.EXTERNAL_TARGET:
        return label, "External target"


def _order_columns(boxes: list[_Box], edges: tuple[Edge, ...]) -> None:
    by_stage: dict[int, list[_Box]] = {}
    for box in boxes:
        by_stage.setdefault(box.stage, []).append(box)
    for members in by_stage.values():
        members.sort(key=_initial_box_key)
    incoming: dict[str, list[Edge]] = {}
    outgoing: dict[str, list[Edge]] = {}
    stage_of = {box.node.id: box.stage for box in boxes}
    for edge in edges:
        incoming.setdefault(edge.dst, []).append(edge)
        outgoing.setdefault(edge.src, []).append(edge)
    stage_count = max(by_stage, default=-1) + 1
    positions = {
        box.node.id: index for members in by_stage.values() for index, box in enumerate(members)
    }
    for _ in range(4):
        for stage in range(1, stage_count):
            members = by_stage.get(stage, [])
            _sort_rank(members, incoming, positions, stage_of, stage, before=True)
            _refresh_positions(members, positions)
        for stage in range(stage_count - 2, -1, -1):
            members = by_stage.get(stage, [])
            _sort_rank(members, outgoing, positions, stage_of, stage, before=False)
            _refresh_positions(members, positions)
    boxes[:] = [box for stage in range(stage_count) for box in by_stage.get(stage, [])]


def _sort_rank(
    members: list[_Box],
    neighbours: Mapping[str, list[Edge]],
    positions: Mapping[str, int],
    stage_of: Mapping[str, int],
    stage: int,
    *,
    before: bool,
) -> None:
    def key(box: _Box) -> tuple[int, float, int, str, str]:
        values = [
            positions[other]
            for edge in neighbours.get(box.node.id, [])
            for other in (edge.src if before else edge.dst,)
            if other in positions
            and (
                (stage_of.get(other, stage) < stage)
                if before
                else (stage_of.get(other, stage) > stage)
            )
        ]
        average = sum(values) / len(values) if values else math.inf
        return (
            0 if values else 1,
            average,
            _STAGE_INDEX[box.node.kind],
            box.node.label.casefold(),
            box.node.id,
        )

    members.sort(key=key)


def _refresh_positions(members: Iterable[_Box], positions: dict[str, int]) -> None:
    for index, box in enumerate(members):
        positions[box.node.id] = index


def _place_boxes(boxes: list[_Box], active_stages: list[int]) -> dict[int, tuple[float, float]]:
    widths: dict[int, float] = {}
    totals: dict[int, float] = {}
    for stage in active_stages:
        members = [box for box in boxes if box.stage == stage]
        widths[stage] = max(
            _COLUMN_PAD + 40.0, max((box.width for box in members), default=0.0) + _COLUMN_PAD
        )
        totals[stage] = sum(box.height for box in members) + _NODE_GAP * max(len(members) - 1, 0)
    content_top = _MARGIN_TOP + _HEADER_HEIGHT + 12
    content_height = max(totals.values(), default=0.0)
    running_x = _MARGIN_X
    columns: dict[int, tuple[float, float]] = {}
    for stage in active_stages:
        members = [box for box in boxes if box.stage == stage]
        column_width = widths[stage]
        center = running_x + column_width / 2
        y = content_top + (content_height - totals[stage]) / 2
        for box in members:
            box.x = center - box.width / 2
            box.y = y
            y += box.height + _NODE_GAP
        columns[stage] = (running_x, column_width)
        running_x += column_width + _COLUMN_GAP
    return columns


def _route_edges(
    edges: tuple[Edge, ...],
    by_id: Mapping[str, _Box],
    columns: Mapping[int, tuple[float, float]],
    content_bottom: float,
) -> tuple[list[_RoutedEdge], int]:
    long_edges = [edge for edge in edges if by_id[edge.dst].stage != by_id[edge.src].stage + 1]
    long_ids = {edge.id for edge in long_edges}
    lane_of = {edge.id: index % MAX_RAIL_LANES for index, edge in enumerate(long_edges)}
    source_offsets = _side_offsets(edges, by_id, source=True)
    target_offsets = _side_offsets(edges, by_id, source=False)
    routed: list[_RoutedEdge] = []
    for edge in edges:
        source = by_id[edge.src]
        target = by_id[edge.dst]
        sy = source.y + source.height / 2 + source_offsets.get((edge.src, edge.id), 0.0)
        ty = target.y + target.height / 2 + target_offsets.get((edge.dst, edge.id), 0.0)
        if edge.id in long_ids:
            lane = lane_of[edge.id]
            rail_y = content_bottom + _RAIL_START + lane * _RAIL_STEP
            lane_inset = (lane % 3) * _GUTTER_LANE
            source_left, source_width = columns[source.stage]
            target_left, _target_width = columns[target.stage]
            source_gutter = source_left + source_width + _GUTTER_INSET + lane_inset
            target_gutter = max(2.0, target_left - _GUTTER_INSET - lane_inset)
            path = _rail_path(
                source.right,
                sy,
                target.x,
                ty,
                source_gutter,
                target_gutter,
                rail_y,
            )
            routed.append(_RoutedEdge(edge=edge, path=path, lane=lane, long=True))
            continue
        source_x = source.right
        target_x = target.x
        mid = (source_x + target_x) / 2
        path = (
            f"M{_fmt(source_x)},{_fmt(sy)} C{_fmt(mid)},{_fmt(sy)} "
            f"{_fmt(mid)},{_fmt(ty)} {_fmt(target_x)},{_fmt(ty)}"
        )
        routed.append(_RoutedEdge(edge=edge, path=path, lane=0, long=False))
    lanes = max((item.lane for item in routed if item.long), default=-1) + 1
    return routed, lanes


def _side_offsets(
    edges: tuple[Edge, ...],
    by_id: Mapping[str, _Box],
    *,
    source: bool,
) -> dict[tuple[str, str], float]:
    groups: dict[str, list[Edge]] = {}
    for edge in edges:
        node_id = edge.src if source else edge.dst
        groups.setdefault(node_id, []).append(edge)
    offsets: dict[tuple[str, str], float] = {}
    for node_id, members in groups.items():
        box = by_id[node_id]
        span = max(box.height - 26.0, 8.0)
        members.sort(key=lambda edge: edge.id)
        count = len(members)
        if count == 1:
            values = [0.0]
        else:
            step = min(10.0, span / (count - 1))
            start = -(count - 1) * step / 2
            values = [start + index * step for index in range(count)]
        for edge, value in zip(members, values, strict=True):
            offsets[(node_id, edge.id)] = value
    return offsets


def _rail_path(
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    source_gutter: float,
    target_gutter: float,
    rail_y: float,
) -> str:
    r = _CORNER
    horizontal = 1.0 if target_gutter >= source_gutter else -1.0
    parts = [f"M{_fmt(sx)},{_fmt(sy)}", f"H{_fmt(source_gutter)}"]
    parts.append(f"Q{_fmt(source_gutter)},{_fmt(sy)} {_fmt(source_gutter)},{_fmt(sy + r)}")
    parts.append(f"V{_fmt(rail_y - r)}")
    parts.append(
        f"Q{_fmt(source_gutter)},{_fmt(rail_y)} "
        f"{_fmt(source_gutter + horizontal * r)},{_fmt(rail_y)}"
    )
    if abs(target_gutter - source_gutter) > 2 * r:
        parts.append(f"H{_fmt(target_gutter - horizontal * r)}")
    parts.append(f"Q{_fmt(target_gutter)},{_fmt(rail_y)} {_fmt(target_gutter)},{_fmt(rail_y - r)}")
    parts.append(f"V{_fmt(ty + r)}")
    parts.append(f"Q{_fmt(target_gutter)},{_fmt(ty)} {_fmt(target_gutter + r)},{_fmt(ty)}")
    parts.append(f"H{_fmt(tx)}")
    return " ".join(parts)


def _wrap(text: str, max_width: float, font_size: float, max_lines: int) -> list[str]:
    text = " ".join(_clean(text).split())
    if not text:
        return [" "]
    lines: list[str] = []
    current = ""
    overflow = False
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if _text_width(candidate, font_size) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
            if len(lines) >= max_lines:
                overflow = True
                break
        if _text_width(word, font_size) <= max_width:
            current = word
            continue
        pieces = _split_token(word, max_width, font_size)
        lines.extend(pieces[:-1])
        current = pieces[-1]
        if len(lines) >= max_lines:
            overflow = True
            break
    if current and not overflow:
        if len(lines) < max_lines:
            lines.append(current)
        else:
            overflow = True
    if overflow:
        lines = lines[:max_lines]
        if not lines:
            lines = [""]
        lines[-1] = _ellipsize(lines[-1], max_width, font_size)
    return [line for line in lines if line] or [" "]


def _ellipsize(text: str, max_width: float, font_size: float) -> str:
    ellipsis = "…"
    if _text_width(text + ellipsis, font_size) <= max_width:
        return text + ellipsis
    while text and _text_width(text + ellipsis, font_size) > max_width:
        text = text[:-1]
    return text.rstrip() + ellipsis


def _split_token(text: str, max_width: float, font_size: float) -> list[str]:
    pieces: list[str] = []
    rest = text
    while rest and _text_width(rest, font_size) > max_width:
        cut = 1
        for index in range(1, len(rest) + 1):
            if _text_width(rest[:index], font_size) <= max_width:
                cut = index
            else:
                break
        for index in range(cut, 0, -1):
            if rest[index - 1] in "/_.:@#-":
                cut = index
                break
        pieces.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        pieces.append(rest)
    return pieces


def _text_width(text: str, font_size: float) -> float:
    units = 0.0
    for character in text:
        if unicodedata.east_asian_width(character) in {"W", "F"}:
            units += 1.0
        elif character == " ":
            units += 0.29
        elif character in "/_.:@#-":
            units += 0.38
        elif character.isupper() or character.isdigit():
            units += 0.63
        elif character.islower():
            units += 0.55
        else:
            units += 0.52
    return units * font_size


def _basename(path: str) -> str:
    if not path:
        return ""
    return path.replace("\\", "/").rsplit("/", 1)[-1]


def _lifetime(value: str) -> str:
    return {
        "job_bound": "job-bound",
        "session_ttl": "session TTL",
        "persistent": "persistent",
        "persistent_rotating": "rotating",
        "until_rotated": "until rotated",
    }.get(value, value.replace("_", " ") if value else "")


def _duration(value: int) -> str:
    if value and value % 3600 == 0:
        return f"{value // 3600}h"
    if value and value % 60 == 0:
        return f"{value // 60}m"
    return f"{value}s"


def _is_critical(node: Node) -> bool:
    value = node.attrs.get("criticality")
    return type(value) is int and value >= 80


def _shape_padding(kind: NodeKind) -> float:
    if kind in {NodeKind.OIDC_IDENTITY, NodeKind.AWS_OIDC_PROVIDER}:
        return 34.0
    if kind is NodeKind.AWS_ROLE:
        return 28.0
    if kind in {NodeKind.ACTION_REF, NodeKind.EXTERNAL_TARGET}:
        return 22.0
    if kind in {NodeKind.SINK, NodeKind.CREDENTIAL}:
        return 20.0
    return 0.0


def _node_sort_key(node: Node) -> tuple[int, str, str, str]:
    return (_STAGE_INDEX[node.kind], node.kind.value, node.label.casefold(), node.id)


def _initial_box_key(box: _Box) -> tuple[int, str, str, str]:
    return (
        _STAGE_INDEX[box.node.kind],
        box.node.kind.value,
        box.node.label.casefold(),
        box.node.id,
    )


def _edge_sort_key(edge: Edge) -> tuple[int, str, str]:
    confidence = {"unknown": 0, "assumed": 1, "derived": 2, "declared": 3}
    return (confidence.get(edge.confidence.value, 0), edge.kind.value, edge.id)


def _box_draw_key(box: _Box) -> tuple[str, str]:
    return (box.node.kind.value, box.node.id)


def _select_render_nodes(
    nodes: tuple[Node, ...],
    edges: tuple[Edge, ...],
    entry_ids: set[str],
    max_nodes: int,
) -> tuple[Node, ...]:
    degree = dict.fromkeys((node.id for node in nodes), 0)
    for edge in edges:
        if edge.src in degree:
            degree[edge.src] += 1
        if edge.dst in degree:
            degree[edge.dst] += 1

    def priority(node: Node) -> tuple[int, int, int, str, str]:
        return (
            0 if node.id in entry_ids else 1,
            -degree.get(node.id, 0),
            _STAGE_INDEX[node.kind],
            node.label.casefold(),
            node.id,
        )

    return tuple(sorted(nodes, key=priority)[:max_nodes])


def _empty_layout(total_nodes: int, total_edges: int, omitted_nodes: int) -> dict[str, Any]:
    return {
        "format": LAYOUT_FORMAT,
        "width": 640.0,
        "height": 160.0,
        "content_bottom": 0.0,
        "stages": [],
        "nodes": [],
        "edges": [],
        "counts": {
            "nodes": 0,
            "edges": 0,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "omitted_nodes": omitted_nodes,
            "omitted_edges": total_edges,
        },
    }


def _graph_description(report: Report, layout: Mapping[str, Any]) -> str:
    counts = layout.get("counts") or {}
    nodes = counts.get("nodes", 0)
    edges = counts.get("edges", 0)
    stages = len(layout.get("stages") or [])
    parts = [
        f"{_plural(nodes, 'node')} and {_plural(edges, 'edge')} arranged in "
        f"{_plural(stages, 'authority stage')}.",
        "Line style encodes evidence: solid for declared or derived, dashed for assumed, "
        "dotted for unknown.",
    ]
    if counts.get("omitted_nodes"):
        omitted = _plural(int(counts.get("omitted_nodes", 0)), "node is", "nodes are")
        parts.append(
            f"Rendering limit: {omitted} not drawn; the JSON report contains the complete graph."
        )
    if report.scenarios:
        parts.append(f"Entrypoints are marked for {_plural(len(report.scenarios), 'scenario')}.")
    return " ".join(parts)


def _plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return f"{count} {singular if count == 1 else plural_form or singular + 's'}"


def _clean(value: str) -> str:
    output: list[str] = []
    for character in value:
        code = ord(character)
        if character in "\n\t\r":
            output.append(" ")
        elif code < 0x20 or 0xD800 <= code <= 0xDFFF or code in {0xFFFE, 0xFFFF}:
            continue
        else:
            output.append(character)
    return "".join(output)


def _number(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _round(value: float) -> float:
    return round(value, 2)


def _fmt(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


__all__ = [
    "LAYOUT_FORMAT",
    "MAX_RENDER_NODES",
    "build_layout",
    "render_graph_svg",
]
