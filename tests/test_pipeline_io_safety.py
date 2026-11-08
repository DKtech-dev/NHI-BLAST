"""Real pipeline output preserves consumed inputs and previously committed artifacts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from nhi_blast import pipeline
from nhi_blast.cli.app import app
from nhi_blast.core import artifact_io
from nhi_blast.pipeline import ExportOptions, OutputError, RankOptions, ScanOptions

pytestmark = pytest.mark.security

TF = b'{"format_version":"1.0","values":{"root_module":{"resources":[]}}}'
IAM = b'{"Version":"2012-10-17","Statement":[]}'
CONFIG = b"""
[limits]
max_yaml_policy_file_bytes = 8
"""
MODES = ["scan-json", "scan-sarif", "scan-html", "rank", "export-json", "export-dot"]


def _run(mode: str, root: Path, out: Path, **inputs: Any) -> object:
    if mode.startswith("scan-"):
        return pipeline.run_scan(
            ScanOptions(root=root, out_dir=out, formats=(mode.removeprefix("scan-"),), **inputs)
        )
    if mode == "rank":
        return pipeline.run_rank(RankOptions(root=root, out_dir=out, fmt="json", **inputs))
    return pipeline.run_export(
        ExportOptions(root=root, out_dir=out, fmt=mode.removeprefix("export-"), **inputs)
    )


def _filename(mode: str) -> str:
    return {
        "scan-json": "report.json",
        "scan-sarif": "report.sarif",
        "scan-html": "report.html",
        "rank": "rank.json",
        "export-json": "graph.json",
        "export-dot": "graph.dot",
    }[mode]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("source_kind", ["tf", "iam", "config", "invalid", "oversize"])
@pytest.mark.parametrize("alias", ["exact", "hardlink", "symlink"])
def test_pipeline_preserves_consumed_input_aliases(
    tmp_path: Path, mode: str, source_kind: str, alias: str
) -> None:
    root = tmp_path / "repo"
    out = root / "out"
    out.mkdir(parents=True)
    target = out / _filename(mode)
    source = target if alias == "exact" else root / "source.input"
    data = {"tf": TF, "iam": IAM, "config": CONFIG, "invalid": b"\xff", "oversize": b"x" * 20}[
        source_kind
    ]
    source.write_bytes(data)
    inputs: dict[str, Any] = {"repo_slug": "acme/shop"}
    if source_kind == "config":
        inputs["config_path"] = source
    elif source_kind == "tf":
        inputs["tf_json"] = (source,)
    else:
        inputs["iam_json"] = (source,)
        if source_kind == "oversize":
            config = root / "nhi-blast.toml"
            config.write_bytes(CONFIG)
    if alias == "hardlink":
        os.link(source, target)
    elif alias == "symlink":
        try:
            target.symlink_to(source)
        except OSError:
            pytest.skip("file symlink privilege unavailable")
    with pytest.raises(OutputError, match=r"input|overwrite"):
        _run(mode, root, out, **inputs)
    assert source.read_bytes() == data
    assert target.read_bytes() == data


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("kind", ["workflow", "action", "git"])
def test_pipeline_preserves_automatically_consumed_inputs(
    tmp_path: Path, mode: str, kind: str
) -> None:
    root = tmp_path / "repo"
    out = root / "out"
    out.mkdir(parents=True)
    relative, text = {
        "workflow": (".github/workflows/ci.yml", "name: ci\non: push\njobs: {}\n"),
        "action": ("local/action.yml", "name: local\nruns:\n  using: composite\n  steps: []\n"),
        "git": (".git/config", '[remote "origin"]\nurl = https://github.com/acme/shop.git\n'),
    }[kind]
    source = root / relative
    source.parent.mkdir(parents=True)
    source.write_text(text, encoding="utf-8", newline="\n")
    original = source.read_bytes()
    target = out / _filename(mode)
    os.link(source, target)
    with pytest.raises(OutputError, match=r"input|overwrite"):
        _run(mode, root, out)
    assert source.read_bytes() == original
    assert target.read_bytes() == original


def test_git_read_before_lower_loader_limit_is_protected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    out = root / "out"
    out.mkdir(parents=True)
    config = root / ".git" / "config"
    config.parent.mkdir()
    config.write_bytes(b'[remote "origin"]\nurl = https://github.com/acme/shop.git\n')
    (root / "nhi-blast.toml").write_bytes(CONFIG)
    target = out / "report.json"
    os.link(config, target)
    before = config.read_bytes()
    with pytest.raises(OutputError, match=r"input|overwrite"):
        _run("scan-json", root, out)
    assert config.read_bytes() == before
    assert target.read_bytes() == before


def test_input_path_replaced_after_open_is_still_protected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "report.json"
    source.write_bytes(TF)
    original = pipeline.load_repository

    def replaced(options: pipeline.SourceOptions) -> pipeline.ParsedRepository:
        parsed = original(options)
        source.unlink()
        source.write_bytes(b"replacement input")
        return parsed

    monkeypatch.setattr(pipeline, "load_repository", replaced)
    with pytest.raises(OutputError, match=r"input|overwrite"):
        _run("scan-json", tmp_path, tmp_path, tf_json=(source,))
    assert source.read_bytes() == b"replacement input"


def test_second_renderer_failure_preserves_previous_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.json").write_bytes(b"old json")
    (out / "report.html").write_bytes(b"old html")

    def broken(*_args: object) -> str:
        msg = "html renderer failed"
        raise OSError(msg)

    monkeypatch.setattr("nhi_blast.report.html.html_report", broken)
    monkeypatch.setattr(pipeline, "html_report", broken, raising=False)
    with pytest.raises(OutputError):
        pipeline.run_scan(ScanOptions(root=tmp_path, formats=("json", "html"), out_dir=out))
    assert (out / "report.json").read_bytes() == b"old json"
    assert (out / "report.html").read_bytes() == b"old html"


@pytest.mark.parametrize("failure", ["staging", "promotion"])
def test_later_write_failure_preserves_previous_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.json").write_bytes(b"old json")
    (out / "report.sarif").write_bytes(b"old sarif")
    if failure == "staging":
        original_open = Path.open
        writes = 0

        def broken_open(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            nonlocal writes
            if any(flag in mode for flag in "wx"):
                writes += 1
                if writes == 2:
                    msg = "second write failed"
                    raise OSError(msg)
            return original_open(path, mode, *args, **kwargs)

        monkeypatch.setattr(Path, "open", broken_open)
    else:
        original_replace = os.replace

        def broken_replace(source: Any, target: Any, *args: Any, **kwargs: Any) -> None:
            if Path(target) == out / "report.sarif" and Path(source).name == "payload":
                msg = "second promotion failed"
                raise OSError(msg)
            original_replace(source, target, *args, **kwargs)

        monkeypatch.setattr(artifact_io.os, "replace", broken_replace)
    with pytest.raises(OutputError):
        pipeline.run_scan(ScanOptions(root=tmp_path, formats=("json", "sarif"), out_dir=out))
    assert (out / "report.json").read_bytes() == b"old json"
    assert (out / "report.sarif").read_bytes() == b"old sarif"


def test_rank_console_render_failure_preserves_previous_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "rank.json"
    target.write_bytes(b"old rank")

    def broken(_report: object) -> str:
        msg = "console renderer failed"
        raise OSError(msg)

    monkeypatch.setattr(pipeline, "render_rank_console", broken)
    with pytest.raises(OutputError):
        _run("rank", tmp_path, tmp_path)
    assert target.read_bytes() == b"old rank"


@pytest.mark.parametrize("mode", MODES)
def test_selected_unreadable_source_is_never_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    source = tmp_path / _filename(mode)
    source.write_bytes(IAM)
    original = Path.open

    def unreadable(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if path == source and mode == "rb":
            msg = "selected source cannot be opened"
            raise PermissionError(msg)
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unreadable)
    with pytest.raises(OutputError, match=r"input|overwrite"):
        _run(mode, tmp_path, tmp_path, iam_json=(source,))
    monkeypatch.undo()
    assert source.read_bytes() == IAM


@pytest.mark.parametrize("which", ["loader", "git"])
def test_input_identity_failure_is_controlled_input_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    source = tmp_path / ".git" / "config" if which == "git" else tmp_path / "source.input"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(IAM)

    def unavailable(_path: Path) -> artifact_io.InputIdentity:
        msg = "cannot identify input file"
        raise artifact_io.ArtifactReadError(msg)

    module = "nhi_blast.discovery.repo" if which == "git" else "nhi_blast.discovery.walker"
    monkeypatch.setattr(module + ".identify_input", unavailable)
    args = ["scan", str(tmp_path), "--format", "json", "--out", str(tmp_path / "out")]
    if which == "loader":
        args.extend(["--iam-json", str(source)])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2, result.output
    assert "cannot identify input file" in result.output
    assert "internal error" not in result.output
    assert not (tmp_path / "out").exists()
    assert source.read_bytes() == IAM


@pytest.mark.parametrize("mode", MODES)
def test_cli_input_collision_exits_four_without_written_claim(tmp_path: Path, mode: str) -> None:
    source = tmp_path / _filename(mode)
    source.write_bytes(TF)
    if mode.startswith("scan-"):
        args = ["scan", str(tmp_path), "--format", mode.removeprefix("scan-")]
    else:
        command = "rank" if mode == "rank" else "export"
        fmt = "json" if mode == "rank" else mode.removeprefix("export-")
        args = [command, str(tmp_path), "--format", fmt]
    args.extend(["--tf-json", str(source), "--out", str(tmp_path)])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 4, result.output
    assert "Written:" not in result.output
    assert source.read_bytes() == TF
