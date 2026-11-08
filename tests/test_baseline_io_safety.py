"""Real baseline CLI writes preserve every loaded diff identity while allowing updates."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from nhi_blast.cli import diff_cmd
from nhi_blast.cli.app import app
from nhi_blast.diff.baseline import Baseline
from tests.test_diff_support import FIXTURES

runner = CliRunner()
KEEP = "b" * 64


def _diff_input(directory: Path, command: str) -> tuple[Path, str, bytes]:
    older = FIXTURES / "diff" / "base-without-oidc.json"
    newer = FIXTURES / "diff" / "base.json"
    if command == "prune":
        older, newer = newer, older
    result = runner.invoke(
        app, ["diff", str(older), str(newer), "--format", "json", "--out", str(directory)]
    )
    assert result.exit_code == 0, result.stderr
    path = directory / "diff.json"
    raw = path.read_bytes()
    payload = json.loads(raw)
    klass = "new" if command == "accept" else "resolved"
    records = [record for record in payload["findings"] if record["class"] == klass]
    assert len(records) == 1
    assert records[0]["rule"] == "NHB-OIDC-002"
    return path, records[0]["lk"], raw


def _baseline_file(path: Path, command: str, lk: str) -> bytes:
    keys = [KEEP] if command == "accept" else [lk, KEEP]
    raw = json.dumps(
        {
            "schema": "nhi-blast-baseline/1.0",
            "created_from_report_digest": "a" * 64,
            "entries": [
                {"lk": key, "rule": "NHB-OIDC-002", "reason": "reviewed", "reviewer": "alice"}
                for key in keys
            ],
        }
    ).encode("utf-8")
    path.write_bytes(raw)
    return raw


def _args(command: str, diff_path: Path, baseline: Path, lk: str) -> list[str]:
    args = ["baseline", command]
    if command == "accept":
        args.extend([lk, "--reason", "tracked in INC-7", "--reviewer", "bob"])
    return [*args, "--diff", str(diff_path), "--baseline", str(baseline)]


def _symlink(source: Path, target: Path) -> None:
    try:
        target.symlink_to(source)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc.strerror}")


@pytest.mark.parametrize("command", ["accept", "prune"])
@pytest.mark.parametrize("kind", ["exact", "resolved", "input-symlink"])
def test_baseline_cli_preserves_diff_path_aliases_after_successful_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, kind: str
) -> None:
    generated, lk, raw_diff = _diff_input(tmp_path / "generated", command)
    target = tmp_path / "baseline.json"
    _baseline_file(target, command, lk)
    diff_path = target
    if kind == "resolved":
        nested = tmp_path / "nested"
        nested.mkdir()
        diff_path = nested / ".." / target.name
    elif kind == "input-symlink":
        diff_path = tmp_path / "diff-link.json"
        _symlink(target, diff_path)
    original_load = diff_cmd.load_baseline

    def replace_after_baseline_load(path: Path) -> Baseline:
        baseline = original_load(path)
        # Static aliases fail baseline/diff schema validation before reaching output.
        # Replace the shared path between real loads so both documents are valid.
        target.write_bytes(raw_diff)
        return baseline

    monkeypatch.setattr(diff_cmd, "load_baseline", replace_after_baseline_load)
    result = runner.invoke(app, _args(command, diff_path, target, lk))
    assert result.exit_code == 4, (result.exit_code, result.stdout, result.stderr)
    assert "protected input" in result.stderr
    assert "Baseline updated" not in result.stdout
    assert "Baseline pruned" not in result.stdout
    assert target.read_bytes() == raw_diff
    assert diff_path.read_bytes() == raw_diff
    assert generated.read_bytes() == raw_diff
    assert not list(tmp_path.rglob(".nhi-blast-stage-*"))


@pytest.mark.parametrize("command", ["accept", "prune"])
@pytest.mark.parametrize("kind", ["hardlink", "symlink", "opened-hardlink"])
def test_baseline_cli_preserves_diff_alias_introduced_after_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, kind: str
) -> None:
    diff_path, lk, raw_diff = _diff_input(tmp_path / "generated", command)
    target = tmp_path / "baseline.json"
    _baseline_file(target, command, lk)
    operation = "accept_entry" if command == "accept" else "prune_entries"
    original = getattr(diff_cmd, operation)
    replacement = b"replacement input path"

    def alias_after_operation(*args: Any, **kwargs: Any) -> Any:
        updated = original(*args, **kwargs)
        target.unlink()
        if kind == "symlink":
            _symlink(diff_path, target)
        else:
            os.link(diff_path, target)
        if kind == "opened-hardlink":
            # Keep the opened inode at target, but replace its original path.
            newer = tmp_path / "replacement.json"
            newer.write_bytes(replacement)
            os.replace(newer, diff_path)
        return updated

    monkeypatch.setattr(diff_cmd, operation, alias_after_operation)
    result = runner.invoke(app, _args(command, diff_path, target, lk))
    assert result.exit_code == 4, (result.exit_code, result.stdout, result.stderr)
    assert "protected input" in result.stderr
    assert "Baseline updated" not in result.stdout
    assert "Baseline pruned" not in result.stdout
    assert target.read_bytes() == raw_diff
    assert diff_path.read_bytes() == (replacement if kind == "opened-hardlink" else raw_diff)
    assert not list(tmp_path.rglob(".nhi-blast-stage-*"))


@pytest.mark.parametrize("existing", [False, True])
def test_baseline_cli_accept_allows_normal_creation_and_in_place_updates(
    tmp_path: Path, existing: bool
) -> None:
    diff_path, lk, raw_diff = _diff_input(tmp_path / "generated", "accept")
    baseline = tmp_path / "baseline.json"
    before = _baseline_file(baseline, "accept", lk) if existing else None
    result = runner.invoke(app, _args("accept", diff_path, baseline, lk))
    assert result.exit_code == 0, result.stderr
    assert "Baseline updated" in result.stdout
    assert baseline.read_bytes() != before
    saved = json.loads(baseline.read_bytes())
    assert saved["schema"] == "nhi-blast-baseline/1.0"
    assert {entry["lk"] for entry in saved["entries"]} == ({KEEP, lk} if existing else {lk})
    entry = next(entry for entry in saved["entries"] if entry["lk"] == lk)
    assert entry == {
        "lk": lk,
        "rule": "NHB-OIDC-002",
        "scenario": "repo-write",
        "reason": "tracked in INC-7",
        "reviewer": "bob",
    }
    expected_digest = "a" * 64 if existing else json.loads(raw_diff)["head"]["report_digest"]
    assert saved["created_from_report_digest"] == expected_digest
    assert diff_path.read_bytes() == raw_diff
    assert not list(tmp_path.rglob(".nhi-blast-stage-*"))


def test_baseline_cli_prune_allows_normal_in_place_update_and_noop(tmp_path: Path) -> None:
    diff_path, lk, raw_diff = _diff_input(tmp_path / "generated", "prune")
    baseline = tmp_path / "baseline.json"
    before = _baseline_file(baseline, "prune", lk)
    result = runner.invoke(app, _args("prune", diff_path, baseline, lk))
    assert result.exit_code == 0, result.stderr
    assert "1 removed, 1 kept" in result.stdout
    after = baseline.read_bytes()
    assert after != before
    assert json.loads(after)["entries"] == [
        {"lk": KEEP, "rule": "NHB-OIDC-002", "reason": "reviewed", "reviewer": "alice"}
    ]
    assert json.loads(after)["created_from_report_digest"] == "a" * 64
    repeated = runner.invoke(app, _args("prune", diff_path, baseline, lk))
    assert repeated.exit_code == 0, repeated.stderr
    assert "0 removed, 1 kept" in repeated.stdout
    assert baseline.read_bytes() == after
    assert diff_path.read_bytes() == raw_diff
    assert not list(tmp_path.rglob(".nhi-blast-stage-*"))


@pytest.mark.parametrize("command", ["accept", "prune"])
@pytest.mark.parametrize("committed", [True, False])
def test_baseline_cli_preserves_truthful_cleanup_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, committed: bool
) -> None:
    diff_path, lk, raw_diff = _diff_input(tmp_path / "generated", command)
    baseline = tmp_path / "baseline.json"
    before = _baseline_file(baseline, command, lk)
    rmdir = Path.rmdir
    replace = os.replace

    def broken_rmdir(path: Path) -> None:
        if path.name.startswith(".nhi-blast-stage-"):
            msg = "FIXTURE_ONLY_PRIVATE_CLEANUP_DETAIL"
            raise OSError(msg)
        rmdir(path)

    def broken_promotion(source: Any, destination: Any) -> None:
        if Path(source).name == "payload" and Path(destination) == baseline:
            msg = "FIXTURE_ONLY_PRIVATE_PROMOTION_DETAIL"
            raise OSError(msg)
        replace(source, destination)

    monkeypatch.setattr(Path, "rmdir", broken_rmdir)
    if not committed:
        monkeypatch.setattr(os, "replace", broken_promotion)
    result = runner.invoke(app, _args(command, diff_path, baseline, lk))
    assert result.exit_code == 4, (result.exit_code, result.stdout, result.stderr)
    assert "staging cleanup incomplete" in result.stderr
    assert "FIXTURE_ONLY_PRIVATE" not in result.stderr
    assert "Baseline updated" not in result.stdout
    assert "Baseline pruned" not in result.stdout
    if committed:
        assert "artifacts committed" in result.stderr
        assert "cannot write baseline file" not in result.stderr
        assert baseline.read_bytes() != before
        keys = {entry["lk"] for entry in json.loads(baseline.read_bytes())["entries"]}
        assert keys == ({KEEP, lk} if command == "accept" else {KEEP})
    else:
        assert "artifact write failed; rollback completed" in result.stderr
        assert "artifacts committed" not in result.stderr
        assert baseline.read_bytes() == before
    assert diff_path.read_bytes() == raw_diff
    assert len(list(tmp_path.glob(".nhi-blast-stage-*"))) == 1


@pytest.mark.parametrize("command", ["accept", "prune"])
def test_baseline_cli_promotion_failure_exits_four_and_preserves_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    diff_path, lk, raw_diff = _diff_input(tmp_path / "generated", command)
    baseline = tmp_path / "baseline.json"
    before = _baseline_file(baseline, command, lk)
    replace = os.replace

    def broken_promotion(source: Any, destination: Any) -> None:
        if Path(source).name == "payload" and Path(destination) == baseline:
            msg = "FIXTURE_ONLY_PRIVATE_PROMOTION_DETAIL"
            raise OSError(msg)
        replace(source, destination)

    monkeypatch.setattr(os, "replace", broken_promotion)
    result = runner.invoke(app, _args(command, diff_path, baseline, lk))
    assert result.exit_code == 4, (result.exit_code, result.stdout, result.stderr)
    assert result.stderr.startswith("error:")
    assert "cannot write baseline file" in result.stderr
    assert "FIXTURE_ONLY_PRIVATE" not in result.stderr
    assert "Baseline updated" not in result.stdout
    assert "Baseline pruned" not in result.stdout
    assert baseline.read_bytes() == before
    assert diff_path.read_bytes() == raw_diff
    assert not list(tmp_path.rglob(".nhi-blast-stage-*"))


@pytest.mark.parametrize("command", ["accept", "prune"])
@pytest.mark.parametrize("invalid", ["diff", "baseline"])
def test_baseline_cli_invalid_inputs_still_exit_two_without_writes(
    tmp_path: Path, command: str, invalid: str
) -> None:
    diff_path, lk, _raw_diff = _diff_input(tmp_path / "generated", command)
    baseline = tmp_path / "baseline.json"
    _baseline_file(baseline, command, lk)
    invalid_path = diff_path if invalid == "diff" else baseline
    invalid_path.write_bytes(b"not a JSON document")
    before_diff, before_baseline = diff_path.read_bytes(), baseline.read_bytes()
    result = runner.invoke(app, _args(command, diff_path, baseline, lk))
    assert result.exit_code == 2, (result.exit_code, result.stdout, result.stderr)
    assert result.stderr.startswith("error:")
    assert "Traceback" not in result.stderr
    assert "Baseline updated" not in result.stdout
    assert "Baseline pruned" not in result.stdout
    assert diff_path.read_bytes() == before_diff
    assert baseline.read_bytes() == before_baseline
    assert not list(tmp_path.rglob(".nhi-blast-stage-*"))
