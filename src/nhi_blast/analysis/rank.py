"""Rank mutable third-party actions by scenario blast radius (spec 12.7)."""

from __future__ import annotations

from collections.abc import Sequence

from nhi_blast import __version__
from nhi_blast.analysis.partition import partition_graph
from nhi_blast.analysis.selectors import mutable_action_nodes
from nhi_blast.core.diagnostics import Diagnostic, DiagnosticBag
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.models import (
    EdgeKind,
    GraphData,
    Inputs,
    PinKind,
    RankReport,
    RankRow,
    ToolInfo,
)


def rank_mutable_actions(
    graph: GraphData,
    *,
    inputs: Inputs,
    max_depth: int = 3,
    diagnostics: Sequence[Diagnostic] = (),
) -> RankReport:
    action_nodes = mutable_action_nodes(graph)
    mint_jobs = {
        edge.src
        for edge in graph.edges
        if edge.kind is EdgeKind.CAN_MINT and edge.confidence is not EvidenceClass.UNKNOWN
    }
    rows: list[RankRow] = []
    for action in action_nodes:
        use_edges = tuple(
            edge for edge in graph.edges if edge.kind is EdgeKind.RUNS_IN and edge.dst == action.id
        )
        starts = tuple(sorted({edge.src for edge in use_edges}))
        if not starts:
            continue
        result = partition_graph(graph, starts, max_depth=max_depth)
        rows.append(
            RankRow(
                action=action.id.removeprefix("action:"),
                pin_kind=PinKind(str(action.attrs.get("pin_kind", PinKind.AMBIGUOUS.value))),
                use_sites=len(use_edges),
                jobs_with_oidc=sum(start in mint_jobs for start in starts),
                r_count=len(result.partition.R),
                e_count=len(result.partition.E),
                z_count=len(result.partition.Z),
                highest_criticality=max(
                    (item.criticality for item in result.partition.Z), default=0
                ),
            )
        )
    return RankReport(
        tool=ToolInfo(version=__version__),
        inputs=inputs,
        rows=tuple(sorted(rows, key=RankRow.sort_key)),
        diagnostics=DiagnosticBag(diagnostics).sorted(),
    )


__all__ = ["rank_mutable_actions"]
