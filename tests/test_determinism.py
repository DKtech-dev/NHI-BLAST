"""Deterministic artifacts and offline-runtime guards (spec 5.5, 11, 13.2)."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from nhi_blast.pipeline import (
    ExportOptions,
    RankOptions,
    ScanOptions,
    ScanOutcome,
    run_export,
    run_rank,
    run_scan,
)

ALL_FORMATS = ("console", "json", "sarif", "html")


def _scan(root: Path, out: Path, *, selectors: tuple[str, ...] = ("repo-write",)) -> ScanOutcome:
    return run_scan(ScanOptions(root=root, selectors=selectors, formats=ALL_FORMATS, out_dir=out))


def _artifact_bytes(outcome: ScanOutcome) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in outcome.written}


def test_scan_artifacts_are_byte_identical_across_runs(fixtures_dir: Path, tmp_path: Path) -> None:
    root = fixtures_dir / "fx07-incident"

    first = _scan(root, tmp_path / "first")
    second = _scan(root, tmp_path / "second")

    assert first.report.generated_at is None
    assert first.console_text == second.console_text
    assert first.report.model_dump_json() == second.report.model_dump_json()
    assert _artifact_bytes(first) == _artifact_bytes(second)
    assert set(_artifact_bytes(first)) == {"report.json", "report.sarif", "report.html"}


def test_selector_order_does_not_change_artifacts(fixtures_dir: Path, tmp_path: Path) -> None:
    root = fixtures_dir / "fx07-incident"

    first = run_scan(
        ScanOptions(
            root=root,
            selectors=("repo-write", "fork-pr"),
            formats=("json",),
            out_dir=tmp_path / "first",
        )
    )
    second = run_scan(
        ScanOptions(
            root=root,
            selectors=("fork-pr", "repo-write"),
            formats=("json",),
            out_dir=tmp_path / "second",
        )
    )

    assert first.report.model_dump_json() == second.report.model_dump_json()
    assert _artifact_bytes(first) == _artifact_bytes(second)


def test_timestamp_is_opt_in_and_only_changes_generated_at(
    fixtures_dir: Path, tmp_path: Path
) -> None:
    root = fixtures_dir / "fx07-incident"
    plain = run_scan(
        ScanOptions(
            root=root, selectors=("repo-write",), formats=("json",), out_dir=tmp_path / "plain"
        )
    )
    stamped = run_scan(
        ScanOptions(
            root=root,
            selectors=("repo-write",),
            formats=("json",),
            out_dir=tmp_path / "stamped",
            timestamp=True,
        )
    )

    assert plain.report.generated_at is None
    assert stamped.report.generated_at is not None
    assert "T" in stamped.report.generated_at
    plain_data = plain.report.model_dump(mode="json")
    stamped_data = stamped.report.model_dump(mode="json")
    plain_data.pop("generated_at")
    stamped_data.pop("generated_at")
    assert plain_data == stamped_data
    payload = json.loads(stamped.written[0].read_text(encoding="utf-8"))
    assert payload["generated_at"] == stamped.report.generated_at


def test_rank_and_export_artifacts_are_deterministic(fixtures_dir: Path, tmp_path: Path) -> None:
    root = fixtures_dir / "fx07-incident"

    first_rank = run_rank(RankOptions(root=root, fmt="json", out_dir=tmp_path / "rank-a"))
    second_rank = run_rank(RankOptions(root=root, fmt="json", out_dir=tmp_path / "rank-b"))
    first_json = run_export(ExportOptions(root=root, fmt="json", out_dir=tmp_path / "json-a"))
    second_json = run_export(ExportOptions(root=root, fmt="json", out_dir=tmp_path / "json-b"))
    first_dot = run_export(ExportOptions(root=root, fmt="dot", out_dir=tmp_path / "dot-a"))
    second_dot = run_export(ExportOptions(root=root, fmt="dot", out_dir=tmp_path / "dot-b"))

    assert first_rank.report.model_dump_json() == second_rank.report.model_dump_json()
    assert first_rank.written[0].read_bytes() == second_rank.written[0].read_bytes()
    assert first_json.written[0].read_bytes() == second_json.written[0].read_bytes()
    assert first_dot.written[0].read_bytes() == second_dot.written[0].read_bytes()


def test_scan_makes_no_network_calls(
    fixtures_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        msg = "runtime attempted a network call"
        raise AssertionError(msg)

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "socketpair", blocked)

    outcome = _scan(fixtures_dir / "fx13-secrets-inherit", tmp_path / "offline")

    assert outcome.exit_code == 0
    assert len(outcome.report.graph.nodes) > 0
