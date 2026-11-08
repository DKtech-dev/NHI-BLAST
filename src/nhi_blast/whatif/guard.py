"""Replay guard: pure checks that decide whether a saved report may be replayed.

Each function returns failures instead of raising, so every path is unit-testable. The
what-if aborts (exit 2, nothing written) on the first non-empty stage, in this order:
context, integrity, engine identity, time budget, replay self-check.
"""

from __future__ import annotations

from dataclasses import dataclass

from nhi_blast import SCHEMA_VERSION
from nhi_blast.analysis.scenario import ScenarioAnalysis, analyze_scenario
from nhi_blast.core.config import Config
from nhi_blast.core.context import analyzer_identity, integrity_failures
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    AnalyzerIdentity,
    GraphData,
    Report,
    ReportContext,
    ScenarioContext,
    ScenarioReport,
)

CONTEXT_MISSING = "D-WHATIF-CONTEXT-MISSING"
INTEGRITY = "D-WHATIF-INTEGRITY"
ENGINE_MISMATCH = "D-WHATIF-ENGINE-MISMATCH"
NONDETERMINISTIC_SOURCE = "D-WHATIF-NONDETERMINISTIC-SOURCE"
REPLAY_MISMATCH = "D-WHATIF-REPLAY-MISMATCH"
RESCAN_HINT = "re-scan with nhi-blast >= 0.3.0"


@dataclass(frozen=True, slots=True)
class GuardFailure:
    code: str
    message: str


def pristine_graph(graph: GraphData) -> GraphData:
    """The saved graph without the nodes and edges that scenario analysis added.

    The pipeline merges every scenario's synthetic nodes and edges into the saved graph
    but analyses each scenario on the graph as built. Replaying on the saved graph would
    let one scenario's additions leak into another, so they are removed first; the
    markers (`repo_write`, `hypothetical`) are set only by analysis/scenario.py.
    """
    nodes = tuple(
        node
        for node in graph.nodes
        if node.attrs.get("repo_write") is not True and node.attrs.get("hypothetical") is not True
    )
    edges = tuple(edge for edge in graph.edges if edge.attrs.get("repo_write") is not True)
    return GraphData(nodes=nodes, edges=edges)


def config_from_context(context: ReportContext) -> Config:
    return Config(
        default_branch=context.default_branch,
        aws_account=context.aws_account,
        aws_region=context.aws_region,
        role_bindings=dict(context.role_bindings),
        credential_bindings=dict(context.credential_bindings),
        sub_template=context.sub_template,
        ignore_rules=context.ignore_rules,
        ignore_paths=context.ignore_paths,
        github_host=context.oidc.host,
        github_subject_format=context.oidc.subject_format,
        github_owner_id=context.oidc.owner_id,
        github_repo_id=context.oidc.repo_id,
    )


def limits_from_context(context: ReportContext) -> Limits:
    return Limits.from_mapping(context.limits)


def _missing(detail: str) -> tuple[GuardFailure, ...]:
    return (GuardFailure(CONTEXT_MISSING, f"{detail}; {RESCAN_HINT}"),)


def context_failures(report: Report) -> tuple[GuardFailure, ...]:
    context = report.context
    if report.schema_id != SCHEMA_VERSION:
        return _missing(f"report schema {report.schema_id} has no replay context")
    if context is None:
        return _missing("report has no replay context")
    try:
        limits = limits_from_context(context)
    except (TypeError, ValueError):
        return _missing("report context limits are not valid")
    if limits.max_closure_depth != context.max_depth:
        return _missing("report context depth fields disagree")
    recorded = {item.selector: item for item in context.scenarios}
    saved = {item.selector: item for item in report.scenarios}
    if len(recorded) != len(context.scenarios) or len(saved) != len(report.scenarios):
        return _missing("report scenarios are not unique")
    if set(recorded) != set(saved):
        return _missing("report scenarios and context scenarios differ")
    for selector, item in sorted(saved.items()):
        if tuple(sorted(item.start_nodes)) != tuple(sorted(recorded[selector].start_nodes)):
            return _missing("report scenario start nodes differ from the context")
    return ()


def integrity_guard(report: Report) -> tuple[GuardFailure, ...]:
    failures = integrity_failures(report)
    if not failures:
        return ()
    return (
        GuardFailure(INTEGRITY, f"report digests do not match its content: {', '.join(failures)}"),
    )


def engine_guard(
    report: Report, identity: AnalyzerIdentity | None = None
) -> tuple[GuardFailure, ...]:
    context = report.context
    if context is None:
        return _missing("report has no replay context")
    running = identity if identity is not None else analyzer_identity()
    if running == context.analyzer:
        return ()
    return (
        GuardFailure(
            ENGINE_MISMATCH,
            "the report was produced by a different analyzer (tool version, engine "
            "semantics, rules or data digests); re-scan with this version",
        ),
    )


def budget_guard(report: Report) -> tuple[GuardFailure, ...]:
    context = report.context
    if context is None:
        return _missing("report has no replay context")
    cut = sorted(item.selector for item in context.scenarios if item.time_budget_exhausted)
    if not cut:
        return ()
    return (
        GuardFailure(
            NONDETERMINISTIC_SOURCE,
            "a wall-clock time budget cut the source analysis and cannot be reproduced: "
            + ", ".join(cut),
        ),
    )


def replay_scenario(
    graph: GraphData, context: ReportContext, scenario: ScenarioContext
) -> ScenarioAnalysis:
    return analyze_scenario(
        graph,
        scenario.start_nodes,
        selector=scenario.selector,
        selector_kind=scenario.selector_kind,
        max_depth=context.max_depth,
        limits=limits_from_context(context),
        config=config_from_context(context),
        strict=context.strict,
    )


def scenario_matches(saved: ScenarioReport, analysis: ScenarioAnalysis) -> bool:
    return (
        saved.partition == analysis.partition
        and saved.potential == analysis.potential_edges
        and saved.potential_nodes == analysis.potential_nodes
        and saved.unresolved_inputs == analysis.unresolved_inputs
        and saved.truncated == analysis.truncated
        and saved.rotation_plan == analysis.rotation_plan
    )


def replay_failures(report: Report) -> tuple[GuardFailure, ...]:
    """Re-run every recorded scenario on the untouched saved graph and compare."""
    context = report.context
    if context is None:
        return _missing("report has no replay context")
    graph = pristine_graph(report.graph)
    saved = {item.selector: item for item in report.scenarios}
    mismatched: list[str] = []
    for scenario in context.scenarios:
        try:
            analysis = replay_scenario(graph, context, scenario)
        except (ValueError, KeyError):
            mismatched.append(scenario.selector)
            continue
        if analysis.time_budget_exhausted:
            return (
                GuardFailure(
                    NONDETERMINISTIC_SOURCE,
                    f"replay of {scenario.selector} exhausted the time budget",
                ),
            )
        if not scenario_matches(saved[scenario.selector], analysis):
            mismatched.append(scenario.selector)
    if not mismatched:
        return ()
    return (
        GuardFailure(
            REPLAY_MISMATCH,
            "replaying the saved scenarios did not reproduce the saved result: "
            + ", ".join(sorted(mismatched)),
        ),
    )


def guard_failures(
    report: Report, identity: AnalyzerIdentity | None = None
) -> tuple[GuardFailure, ...]:
    """First failing stage, or an empty tuple when the report may be replayed."""
    for stage in (
        context_failures,
        integrity_guard,
        lambda item: engine_guard(item, identity),
        budget_guard,
        replay_failures,
    ):
        failures = stage(report)
        if failures:
            return failures
    return ()


__all__ = [
    "CONTEXT_MISSING",
    "ENGINE_MISMATCH",
    "INTEGRITY",
    "NONDETERMINISTIC_SOURCE",
    "REPLAY_MISMATCH",
    "GuardFailure",
    "budget_guard",
    "config_from_context",
    "context_failures",
    "engine_guard",
    "guard_failures",
    "integrity_guard",
    "limits_from_context",
    "pristine_graph",
    "replay_failures",
    "replay_scenario",
    "scenario_matches",
]
