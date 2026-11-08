"""Replay guard: every abort path, in order, and nothing written on abort."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from nhi_blast.cli.whatif_cmd import whatif
from nhi_blast.core.canonical import digest_of
from nhi_blast.core.context import analyzer_identity
from nhi_blast.core.models import Partition, Report, ReportContext, ScenarioReport
from nhi_blast.report.loader import load_report
from nhi_blast.whatif.engine import WhatIfAbort, run_whatif
from nhi_blast.whatif.guard import (
    CONTEXT_MISSING,
    ENGINE_MISMATCH,
    INTEGRITY,
    NONDETERMINISTIC_SOURCE,
    REPLAY_MISMATCH,
    budget_guard,
    context_failures,
    engine_guard,
    guard_failures,
    integrity_guard,
    pristine_graph,
    replay_failures,
)
from tests.test_whatif_support import (
    DEPLOY_KEY,
    FIXTURES,
    FX16,
    ROLE_SELECTOR,
    fx16_report,
    plan_of,
    rotate,
    save,
    scan,
    write_plan,
)

FX07 = FIXTURES / "fx07-incident"
OLD_REPORT = FIXTURES / "reports" / "fx07-report-1.0.json"

app = typer.Typer()
app.command("whatif")(whatif)


@app.command("noop")
def _noop() -> None:
    """Keeps typer in multi-command mode so that the subcommand name is required."""


runner = CliRunner()


def with_context(report: Report, **updates: Any) -> Report:
    """A report whose context is changed and whose context digest is made consistent."""
    assert report.context is not None
    changed = report.context.model_copy(update=updates)
    payload = changed.model_dump(
        mode="json", by_alias=True, exclude_none=True, exclude={"context_digest"}
    )
    fixed: ReportContext = changed.model_copy(update={"context_digest": digest_of(payload)})
    return report.model_copy(update={"context": fixed})


def codes(report: Report) -> list[str]:
    return [item.code for item in guard_failures(report)]


def test_an_untouched_report_passes_every_stage() -> None:
    assert guard_failures(fx16_report()) == ()
    assert replay_failures(fx16_report()) == ()


def test_schema_1_0_report_has_no_context() -> None:
    old = load_report(OLD_REPORT)
    assert old.schema_id == "nhi-blast-report/1.0"
    failures = context_failures(old)
    assert [item.code for item in failures] == [CONTEXT_MISSING]
    assert "re-scan with nhi-blast >= 0.3.0" in failures[0].message


def test_report_without_context_is_refused() -> None:
    bare = fx16_report().model_copy(update={"context": None})
    assert codes(bare) == [CONTEXT_MISSING]


def test_context_with_invalid_limits_or_scenarios_is_refused() -> None:
    report = fx16_report()
    assert report.context is not None
    bad_limits = with_context(report, limits={**report.context.limits, "bogus": 1})
    assert codes(bad_limits) == [CONTEXT_MISSING]
    depth = with_context(report, max_depth=report.context.max_depth + 1)
    assert codes(depth) == [CONTEXT_MISSING]
    dropped = with_context(report, scenarios=report.context.scenarios[1:])
    assert codes(dropped) == [CONTEXT_MISSING]
    moved = report.context.scenarios[0].model_copy(update={"start_nodes": ("job:elsewhere",)})
    changed = with_context(report, scenarios=(moved, *report.context.scenarios[1:]))
    assert codes(changed) == [CONTEXT_MISSING]


def test_tampered_graph_or_context_fails_integrity() -> None:
    report = fx16_report()
    assert report.context is not None
    graph = report.graph.model_copy(update={"edges": report.graph.edges[1:]})
    assert codes(report.model_copy(update={"graph": graph})) == [INTEGRITY]
    context = report.context.model_copy(update={"strict": not report.context.strict})
    assert codes(report.model_copy(update={"context": context})) == [INTEGRITY]
    assert [item.code for item in integrity_guard(report)] == []


def test_a_different_analyzer_is_refused() -> None:
    report = fx16_report()
    other = analyzer_identity().model_copy(update={"engine_semantics": "not-this-engine"})
    assert [item.code for item in engine_guard(report, other)] == [ENGINE_MISMATCH]
    assert [item.code for item in guard_failures(report, other)] == [ENGINE_MISMATCH]
    assert "re-scan with this version" in engine_guard(report, other)[0].message
    assert report.context is not None
    for field, value in (("tool_version", "0.0.1"), ("rules_digest", "0" * 64)):
        analyzer = report.context.analyzer.model_copy(update={field: value})
        changed = with_context(report, analyzer=analyzer)
        assert codes(changed) == [ENGINE_MISMATCH], field
    digests = {**report.context.analyzer.data_digests, "rules.yaml": "1" * 64}
    analyzer = report.context.analyzer.model_copy(update={"data_digests": digests})
    assert codes(with_context(report, analyzer=analyzer)) == [ENGINE_MISMATCH]


def test_a_wall_clock_cut_in_the_source_is_refused() -> None:
    report = fx16_report()
    assert report.context is not None
    first = report.context.scenarios[0].model_copy(update={"time_budget_exhausted": True})
    cut = with_context(report, scenarios=(first, *report.context.scenarios[1:]))
    assert [item.code for item in budget_guard(cut)] == [NONDETERMINISTIC_SOURCE]
    assert codes(cut) == [NONDETERMINISTIC_SOURCE]


def test_a_scan_that_ran_out_of_time_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FX16, root)
    config = root / "budget.toml"
    config.write_text("[limits]\nscenario_time_budget_seconds = 0\n", encoding="utf-8")
    report = scan(root, config_path=config)
    assert codes(report) == [NONDETERMINISTIC_SOURCE]


@pytest.mark.parametrize(
    "tamper",
    [
        lambda s: s.model_copy(update={"partition": Partition()}),
        lambda s: s.model_copy(update={"potential": ("0123456789abcdef",)}),
        lambda s: s.model_copy(update={"potential_nodes": ("job:ghost",)}),
        lambda s: s.model_copy(update={"unresolved_inputs": ("made-up blocker",)}),
        lambda s: s.model_copy(update={"truncated": not s.truncated}),
        lambda s: s.model_copy(
            update={"rotation_plan": s.rotation_plan.model_copy(update={"rotation": ()})}
        ),
    ],
    ids=["partition", "potential", "potential_nodes", "unresolved", "truncated", "rotation"],
)
def test_replay_must_reproduce_the_saved_scenario_exactly(tamper: Any) -> None:
    report = fx16_report()
    scenarios: tuple[ScenarioReport, ...] = (tamper(report.scenarios[0]), *report.scenarios[1:])
    changed = report.model_copy(update={"scenarios": scenarios})
    assert codes(changed) == [REPLAY_MISMATCH]


def test_stages_are_checked_in_order() -> None:
    report = fx16_report()
    assert report.context is not None
    graph = report.graph.model_copy(update={"edges": report.graph.edges[1:]})
    both = report.model_copy(update={"graph": graph})
    other = analyzer_identity().model_copy(update={"tool_version": "0.0.1"})
    assert [item.code for item in guard_failures(both, other)] == [INTEGRITY]
    assert [
        item.code for item in guard_failures(report.model_copy(update={"context": None}), other)
    ] == [CONTEXT_MISSING]


def test_replay_reproduces_a_graph_that_already_contains_synthetic_nodes() -> None:
    report = scan(
        FX07,
        ("action:tj-actions/changed-files@v45", "repo-write", "role:aws_iam_role.legacy_ci"),
    )
    assert any(
        node.attrs.get("repo_write") or node.attrs.get("hypothetical")
        for node in report.graph.nodes
    ) or any(edge.attrs.get("repo_write") for edge in report.graph.edges)
    stripped = pristine_graph(report.graph)
    assert len(stripped.edges) < len(report.graph.edges)
    assert guard_failures(report) == ()


def test_depth_truncation_is_allowed_and_flagged() -> None:
    report = scan(FX16, max_depth=0)
    assert any(item.truncated for item in report.scenarios)
    assert guard_failures(report) == ()
    payload = run_whatif(report, plan_of(rotate(DEPLOY_KEY)))
    flagged = {
        item["detail"] for item in payload["warnings"] if item["code"] == "W-WHATIF-DEPTH-TRUNCATED"
    }
    assert flagged == {item.selector for item in report.scenarios if item.truncated}


def test_engine_refuses_to_run_after_a_failed_guard() -> None:
    bare = fx16_report().model_copy(update={"context": None})
    with pytest.raises(WhatIfAbort) as caught:
        run_whatif(bare, plan_of())
    assert caught.value.code == CONTEXT_MISSING


def _tampered_files(tmp_path: Path) -> list[tuple[str, Path, str]]:
    report = fx16_report()
    assert report.context is not None
    graph = report.graph.model_copy(update={"edges": report.graph.edges[1:]})
    first = report.context.scenarios[0].model_copy(update={"time_budget_exhausted": True})
    other = report.context.analyzer.model_copy(update={"tool_version": "0.0.1"})
    mismatch = (Partition(), *(item.partition for item in report.scenarios[1:]))
    scenarios = tuple(
        item.model_copy(update={"partition": part})
        for item, part in zip(report.scenarios, mismatch, strict=True)
    )
    cases = {
        "context": (report.model_copy(update={"context": None}), CONTEXT_MISSING),
        "integrity": (report.model_copy(update={"graph": graph}), INTEGRITY),
        "engine": (with_context(report, analyzer=other), ENGINE_MISMATCH),
        "budget": (
            with_context(report, scenarios=(first, *report.context.scenarios[1:])),
            NONDETERMINISTIC_SOURCE,
        ),
        "replay": (report.model_copy(update={"scenarios": scenarios}), REPLAY_MISMATCH),
    }
    return [
        (name, save(item, tmp_path / f"{name}.json"), code) for name, (item, code) in cases.items()
    ]


def test_cli_aborts_with_exit_2_one_code_and_writes_nothing(tmp_path: Path) -> None:
    plan = write_plan(tmp_path / "plan.json", rotate(DEPLOY_KEY))
    for name, report_path, code in _tampered_files(tmp_path):
        out = tmp_path / f"out-{name}"
        result = runner.invoke(
            app, ["whatif", str(report_path), "--plan", str(plan), "--out", str(out)]
        )
        assert result.exit_code == 2, name
        assert result.stderr.count("D-WHATIF-") == 1, name
        assert code in result.stderr, name
        assert not out.exists(), name
    assert ROLE_SELECTOR
