"""Performance acceptance checks (spec 12.8)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from nhi_blast.analysis.scenario import analyze_scenario
from nhi_blast.analysis.selectors import parse_selector, resolve_starts
from nhi_blast.pipeline import (
    RankOptions,
    SourceOptions,
    build_repository_graph,
    load_repository,
    run_rank,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = 200
RESOURCES = 2_000
IDEAL_ACTION_COUNT = 400
GRAPH_AND_SCENARIO_BUDGET_SECONDS = 5.0
RANK_BUDGET_SECONDS = 60.0


@pytest.fixture(scope="session")
def scale_repository(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("scale") / "repo"
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "gen_fixtures.py"),
            str(root),
            "--workflows",
            str(WORKFLOWS),
            "--resources",
            str(RESOURCES),
            "--actions-per-workflow",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return root


@pytest.mark.slow
def test_graph_build_and_one_scenario_within_budget(scale_repository: Path) -> None:
    parsed = load_repository(SourceOptions(root=scale_repository))
    selector = parse_selector("repo-write")

    started = time.perf_counter()
    build = build_repository_graph(parsed)
    starts = resolve_starts(selector, build.graph, jobs=parsed.expanded_jobs)
    analysis = analyze_scenario(
        build.graph,
        starts,
        selector=selector.raw,
        selector_kind=selector.kind.value,
        max_depth=parsed.limits.max_closure_depth,
        limits=parsed.limits,
        config=parsed.config,
        strict=False,
    )
    elapsed = time.perf_counter() - started

    assert len(build.graph.nodes) > 4_000
    assert len(analysis.partition.R) >= WORKFLOWS
    assert len(analysis.partition.E) == WORKFLOWS
    assert len(analysis.partition.Z) >= WORKFLOWS
    assert elapsed < GRAPH_AND_SCENARIO_BUDGET_SECONDS, (
        f"graph build plus one scenario took {elapsed:.2f}s "
        f"for {WORKFLOWS} workflows and {RESOURCES} resources"
    )


@pytest.mark.slow
def test_rank_three_hundred_mutable_actions_within_budget(scale_repository: Path) -> None:
    started = time.perf_counter()
    outcome = run_rank(RankOptions(root=scale_repository))
    elapsed = time.perf_counter() - started

    assert len(outcome.report.rows) >= 300
    assert len(outcome.report.rows) == IDEAL_ACTION_COUNT
    assert elapsed < RANK_BUDGET_SECONDS, (
        f"rank took {elapsed:.2f}s for {len(outcome.report.rows)} mutable actions"
    )
