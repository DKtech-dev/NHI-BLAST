"""Scenario aggregation, repo-write assumptions and cooperative budgets (M4)."""

from __future__ import annotations

from pathlib import Path

from nhi_blast.analysis.scenario import analyze_scenario
from nhi_blast.analysis.selectors import parse_selector, resolve_starts
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.limits import Limits
from tests.test_graph_builder import ROLE_DEPLOY, ROLE_LEGACY, TEST_JOB, build_fixture


def test_fx07_scenario_aggregates_partition_rotation_findings_and_notes(
    fixtures_dir: Path,
) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    raw = "action:tj-actions/changed-files@v45"
    starts = resolve_starts(parse_selector(raw), graph, jobs=())

    result = analyze_scenario(graph, starts, selector=raw, selector_kind="action")

    assert len(result.partition.R) == 3
    assert len(result.partition.E) == 2
    assert len(result.partition.Z) == 5
    assert not result.truncated
    assert result.rotation_plan.containment
    assert len(result.rotation_plan.rotation) == 5
    assert any(finding.rule == "NHB-SURV-001" for finding in result.findings)
    report = result.to_report()
    assert report.selector == raw
    assert report.start_nodes == starts
    assert any(
        finding_id in report.findings
        for finding_id in [
            finding.id for finding in result.findings if finding.rule == "NHB-SURV-001"
        ]
    )
    assert result.diagnostics == ()


def test_repo_write_adds_only_assumed_accepted_role_paths(fixtures_dir: Path) -> None:
    build = build_fixture(fixtures_dir, "fx07-incident")
    graph = build.graph
    resolve_starts(parse_selector("repo-write"), graph, jobs=())
    starts = (TEST_JOB,)

    result = analyze_scenario(
        graph,
        starts,
        selector="repo-write",
        selector_kind="repo-write",
    )

    assert ROLE_LEGACY in result.reach
    assert result.reach[ROLE_LEGACY].weakest is EvidenceClass.ASSUMED
    assert ROLE_DEPLOY not in result.reach
    assert [item.credential for item in result.partition.Z] == [
        "cred:aws:ssm:/legacy/ci-token:stored"
    ]
    assert len(result.partition.E) == 1
    assert any("add id-token: write" in note for note in result.notes)
    assert not any(edge.attrs.get("repo_write") for edge in graph.edges)
    assert (
        analyze_scenario(
            graph,
            starts,
            selector="repo-write",
            selector_kind="repo-write",
        )
        == result
    )


def test_zero_time_budget_returns_partial_scenario_with_diagnostic(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    raw = "action:tj-actions/changed-files@v45"
    starts = resolve_starts(parse_selector(raw), graph, jobs=())

    result = analyze_scenario(
        graph,
        starts,
        selector=raw,
        selector_kind="action",
        limits=Limits(scenario_time_budget_seconds=0),
    )

    assert result.truncated
    assert result.partition.R == ()
    assert result.partition.E == ()
    assert result.partition.Z == ()
    assert result.findings == ()
    assert result.rotation_plan.rotation == ()
    assert [item.code for item in result.diagnostics] == ["D-ANALYSIS-TIME"]
    assert any("time budget" in note for note in result.notes)
