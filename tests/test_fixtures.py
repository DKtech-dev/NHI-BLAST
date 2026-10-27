"""Reviewed end-to-end expectations for the fx01-fx15 repositories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from nhi_blast.pipeline import (
    ScanOptions,
    SourceOptions,
    build_repository_graph,
    load_repository,
    run_scan,
)


@dataclass(frozen=True, slots=True)
class FixtureExpectation:
    workflows: int
    jobs: int
    resources: int
    nodes: int
    edges: int
    findings: int
    revoked: int
    expiring: int
    surviving: int
    potential: int = 0
    diagnostics: frozenset[str] = frozenset()


EXPECTATIONS = {
    "fx01-minimal": FixtureExpectation(1, 1, 0, 5, 4, 0, 1, 0, 0),
    "fx02-exact-trust": FixtureExpectation(1, 1, 3, 13, 10, 2, 2, 1, 1),
    "fx03-wildcard-trust": FixtureExpectation(1, 1, 6, 18, 12, 7, 2, 3, 1),
    "fx04-environment": FixtureExpectation(
        1, 2, 2, 16, 14, 1, 4, 1, 0, 1, frozenset({"D-EXPR-VALUE"})
    ),
    "fx05-pull-request": FixtureExpectation(
        2, 2, 2, 14, 12, 2, 3, 1, 0, 0, frozenset({"D-GHA-UNTRUSTED-CHECKOUT"})
    ),
    "fx06-composite": FixtureExpectation(
        1,
        4,
        0,
        23,
        23,
        1,
        4,
        0,
        1,
        0,
        frozenset({"D-GHA-COMPOSITE-CYCLE", "D-GHA-COMPOSITE-DEPTH"}),
    ),
    "fx07-incident": FixtureExpectation(2, 2, 9, 26, 24, 7, 3, 2, 5),
    "fx08-tf-plan-unknowns": FixtureExpectation(
        1, 1, 6, 13, 11, 0, 2, 0, 0, 2, frozenset({"D-TF-UNKNOWN"})
    ),
    "fx09-no-id-token": FixtureExpectation(1, 2, 3, 11, 8, 3, 2, 1, 1),
    "fx10-hcl-fallback": FixtureExpectation(
        1,
        1,
        5,
        14,
        11,
        2,
        2,
        1,
        1,
        1,
        frozenset({"D-TF-HCL-LIMIT", "D-TF-UNKNOWN"}),
    ),
    "fx11-rotation-cycle": FixtureExpectation(1, 1, 7, 19, 17, 4, 2, 1, 3),
    "fx12-untrusted-checkout": FixtureExpectation(
        2, 2, 2, 15, 13, 5, 3, 1, 1, 0, frozenset({"D-GHA-UNTRUSTED-CHECKOUT"})
    ),
    "fx13-secrets-inherit": FixtureExpectation(
        2, 3, 3, 28, 26, 5, 6, 3, 2, 2, frozenset({"D-GHA-SECRETS-ALL"})
    ),
    "fx14-hostile": FixtureExpectation(
        2, 2, 3, 18, 15, 3, 3, 1, 3, 0, frozenset({"D-YAML-DUPKEY"})
    ),
    "fx15-scale-smoke": FixtureExpectation(
        4, 4, 40, 86, 83, 33, 8, 4, 20, 0, frozenset({"D-TF-ROTATION-UNBOUND"})
    ),
}

SENTINELS = (
    "FIXTURE_ONLY_PLACEHOLDER_DB_MASTER_VALUE",
    "FIXTURE_ONLY_SENSITIVE_SENTINEL_7c1e9a_not_a_credential",
    "FIXTURE_PLACEHOLDER_VALUE_NOT_A_SECRET",
)


@pytest.mark.parametrize("name", sorted(EXPECTATIONS))
def test_fixture_matches_reviewed_expectations(fixtures_dir: Path, name: str) -> None:
    expected = EXPECTATIONS[name]
    root = fixtures_dir / name
    parsed = load_repository(SourceOptions(root=root))
    graph = build_repository_graph(parsed).graph
    outcome = run_scan(ScanOptions(root=root, selectors=("repo-write",)))
    report = outcome.report
    scenario = report.scenarios[0]
    resources = {address for model in parsed.tf_models for address in model.resources}

    assert (
        len(parsed.workflows),
        len(parsed.expanded_jobs),
        len(resources),
        len(graph.nodes),
        len(graph.edges),
        len(report.findings),
    ) == (
        expected.workflows,
        expected.jobs,
        expected.resources,
        expected.nodes,
        expected.edges,
        expected.findings,
    )
    assert (
        len(scenario.partition.R),
        len(scenario.partition.E),
        len(scenario.partition.Z),
        len(scenario.potential),
    ) == (expected.revoked, expected.expiring, expected.surviving, expected.potential)
    assert {item.code for item in report.diagnostics} == expected.diagnostics

    serialized = report.model_dump_json() + outcome.console_text
    assert all(sentinel not in serialized for sentinel in SENTINELS)


def test_fixture_inventory_is_complete(fixtures_dir: Path) -> None:
    directories = {path.name for path in fixtures_dir.glob("fx*") if path.is_dir()}
    assert directories == set(EXPECTATIONS)


def test_fixture_identity_is_rebuilt_for_every_fixture(fixtures_dir: Path) -> None:
    for name in sorted(EXPECTATIONS):
        config = (fixtures_dir / name / ".git" / "config").read_text(encoding="utf-8")
        expected = "acme/scale" if name == "fx15-scale-smoke" else "acme/shop"
        assert f"url = https://github.com/{expected}.git" in config
