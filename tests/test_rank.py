"""Mutable third-party action blast-radius ranking (M4)."""

from __future__ import annotations

from pathlib import Path

from nhi_blast.analysis.rank import rank_mutable_actions
from nhi_blast.core.models import Inputs, PinKind
from tests.test_graph_builder import build_fixture, build_inline

INPUTS = Inputs(digest="abc123", repo_slug="acme/shop", repo_slug_source="test")


def test_fx07_rank_reproduces_reference_counts(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph

    report = rank_mutable_actions(graph, inputs=INPUTS)

    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.action == "tj-actions/changed-files@v45"
    assert row.pin_kind is PinKind.TAG
    assert row.use_sites == 2
    assert row.jobs_with_oidc == 1
    assert row.r_count == 3
    assert row.e_count == 2
    assert row.z_count == 5
    assert row.highest_criticality == 100


def test_rank_excludes_first_party_actions_and_sorts_by_surviving_count() -> None:
    graph = build_inline(
        """
name: Rank
on: push
jobs:
  larger:
    runs-on: ubuntu-latest
    env:
      FIRST: ${{ secrets.FIRST_SECRET }}
      SECOND: ${{ secrets.SECOND_SECRET }}
    steps:
      - uses: actions/checkout@v4
      - uses: example/a@v1
  smaller:
    runs-on: ubuntu-latest
    env:
      THIRD: ${{ secrets.THIRD_SECRET }}
    steps:
      - uses: example/b@v1
"""
    ).graph

    rows = rank_mutable_actions(graph, inputs=INPUTS).rows

    assert [row.action for row in rows] == ["example/a@v1", "example/b@v1"]
    assert [row.z_count for row in rows] == [2, 1]
    assert [row.r_count for row in rows] == [1, 1]
    assert all(row.jobs_with_oidc == 0 for row in rows)
    assert all(row.highest_criticality == 55 for row in rows)


def test_rank_output_is_deterministic(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph

    first = rank_mutable_actions(graph, inputs=INPUTS).model_dump_json()
    second = rank_mutable_actions(graph, inputs=INPUTS).model_dump_json()

    assert first == second
