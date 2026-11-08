"""Bounded opened reads and input-preserving multi-artifact output regressions."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

import pytest

from nhi_blast.core import artifact_io
from nhi_blast.core.artifact_io import (
    ArtifactReadError,
    InputCollisionError,
    identify_input,
    read_bounded_stream,
    read_bounded_utf8,
    write_artifacts,
)
from nhi_blast.diff.baseline import Baseline, write_baseline
from nhi_blast.diff.render import RENDERERS, Payload, Renderer
from nhi_blast.diff.run import DiffOptions, DiffOutputError, run_diff
from nhi_blast.whatif.engine import WhatIfAbort
from nhi_blast.whatif.run import execute
from tests.test_diff_support import base_report, save_report
from tests.test_whatif_support import fx16_report, save, write_plan


def _alias(source: Path, target: Path, kind: str) -> None:
    if kind == "exact":
        return
    if kind == "hardlink":
        os.link(source, target)
    else:
        try:
            target.symlink_to(source)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc.strerror}")


@pytest.mark.parametrize("kind", ["exact", "hardlink", "symlink"])
@pytest.mark.parametrize("which", ["base", "head", "baseline"])
def test_diff_preserves_every_source_alias(tmp_path: Path, kind: str, which: str) -> None:
    out = tmp_path / "out"
    out.mkdir()
    target = out / "diff.json"
    source = target if kind == "exact" else tmp_path / "source.json"
    base = save_report(base_report(), tmp_path / "base.json")
    head = save_report(base_report(), tmp_path / "head.json")
    baseline = None
    if which == "baseline":
        write_baseline(source, Baseline(created_from_report_digest="a" * 64))
        baseline = source
    else:
        save_report(base_report(), source)
        if which == "base":
            base = source
        else:
            head = source
    _alias(source, target, kind)
    before = source.read_bytes()
    with pytest.raises(DiffOutputError, match=r"input|source|overwrite"):
        run_diff(DiffOptions(base, head, baseline=baseline, formats=("json",), out_dir=out))
    assert source.read_bytes() == before
    assert target.read_bytes() == before


@pytest.mark.parametrize("kind", ["exact", "hardlink", "symlink"])
@pytest.mark.parametrize("which", ["report", "plan"])
def test_whatif_preserves_report_and_plan_aliases(tmp_path: Path, kind: str, which: str) -> None:
    out = tmp_path / "out"
    out.mkdir()
    target = out / "whatif.json"
    source = target if kind == "exact" else tmp_path / "source.json"
    report = save(fx16_report(), tmp_path / "report.json")
    plan = write_plan(tmp_path / "plan.json")
    if which == "report":
        save(fx16_report(), source)
        report = source
    else:
        write_plan(source)
        plan = source
    _alias(source, target, kind)
    before = source.read_bytes()
    with pytest.raises(WhatIfAbort, match=r"input|source|overwrite"):
        execute(report, plan, ("json",), out)
    assert source.read_bytes() == before
    assert target.read_bytes() == before


def test_diff_second_render_failure_preserves_prior_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = save_report(base_report(), tmp_path / "base.json")
    out = tmp_path / "out"
    out.mkdir()
    (out / "diff.json").write_bytes(b"previous json")
    (out / "diff.md").write_bytes(b"previous markdown")

    def broken(_payload: Payload) -> str:
        msg = "second render failed"
        raise OSError(msg)

    monkeypatch.setitem(RENDERERS, "md", Renderer("md", "md", broken))
    with pytest.raises(DiffOutputError):
        run_diff(DiffOptions(base, base, formats=("json", "md"), out_dir=out))
    assert (out / "diff.json").read_bytes() == b"previous json"
    assert (out / "diff.md").read_bytes() == b"previous markdown"


def test_whatif_second_write_failure_preserves_prior_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = save(fx16_report(), tmp_path / "report.json")
    plan = write_plan(tmp_path / "plan.json")
    out = tmp_path / "out"
    out.mkdir()
    (out / "whatif.json").write_bytes(b"previous json")
    (out / "playbook.md").write_bytes(b"previous markdown")
    original = Path.open
    writes = 0

    def broken(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        nonlocal writes
        if any(flag in mode for flag in "wx"):
            writes += 1
        if writes == 2 and any(flag in mode for flag in "wx"):
            msg = "second write failed"
            raise OSError(msg)
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken)
    with pytest.raises(WhatIfAbort):
        execute(report, plan, ("json", "md"), out)
    assert (out / "whatif.json").read_bytes() == b"previous json"
    assert (out / "playbook.md").read_bytes() == b"previous markdown"


def test_stream_limit_consumes_only_max_plus_one_bytes() -> None:
    stream = io.BytesIO(b"abcdefghijk")
    with pytest.raises(ArtifactReadError, match="limit"):
        read_bounded_stream(stream, 4)
    assert stream.tell() == 5


def test_stream_limit_handles_short_reads() -> None:
    class ShortReads(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            return super().read(2 if size is None or size < 0 else min(size, 2))

    stream = ShortReads(b"abcdefghijk")
    with pytest.raises(ArtifactReadError, match="limit"):
        read_bounded_stream(stream, 4)
    assert stream.tell() == 5
    assert read_bounded_stream(ShortReads(b"abcd"), 4) == b"abcd"


def test_bounded_utf8_rejects_binary_without_echoing_bytes(tmp_path: Path) -> None:
    path = tmp_path / "binary.json"
    path.write_bytes(b"marker" + b"\xff")
    with pytest.raises(ArtifactReadError, match="UTF-8") as caught:
        read_bounded_utf8(path, 20)
    assert "marker" not in str(caught.value)


@pytest.mark.parametrize("prior", [True, False])
def test_commit_failure_rolls_back_promoted_artifacts_and_commits_manifest_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior: bool
) -> None:
    data = tmp_path / "report.json"
    manifest = tmp_path / "manifest.json"
    if prior:
        data.write_bytes(b"old report")
        manifest.write_bytes(b"old manifest")
    original = os.replace

    def broken(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
        if Path(destination) == manifest and Path(source).name == "payload":
            assert data.read_bytes() == b"new report"
            msg = "manifest commit failed"
            raise OSError(msg)
        original(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(artifact_io.ArtifactOutputError):
        artifact_io.write_artifacts(
            [(manifest, b"new manifest"), (data, b"new report")], manifest=manifest
        )
    if prior:
        assert data.read_bytes() == b"old report"
        assert manifest.read_bytes() == b"old manifest"
    else:
        assert not data.exists()
        assert not manifest.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == (
        ["manifest.json", "report.json"] if prior else []
    )


def test_identity_protects_original_path_after_input_replacement(tmp_path: Path) -> None:
    path = tmp_path / "source.json"
    path.write_bytes(b"source")
    identity = identify_input(path)
    path.unlink()
    path.write_bytes(b"replacement input")
    with pytest.raises(InputCollisionError):
        write_artifacts([(path, b"output")], inputs=(identity,))
    assert path.read_bytes() == b"replacement input"


def test_regular_output_replacement_preserves_hardlinked_prior_file(tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    target.write_bytes(b"prior output")
    alias = tmp_path / "prior-copy.json"
    os.link(target, alias)
    assert write_artifacts([(target, b"new output")]) == (target,)
    assert target.read_bytes() == b"new output"
    assert alias.read_bytes() == b"prior output"


def test_artifact_named_previous_does_not_collide_with_stage_backup(tmp_path: Path) -> None:
    target = tmp_path / "previous"
    target.write_bytes(b"old output")
    write_artifacts([(target, b"new output")])
    assert target.read_bytes() == b"new output"


def test_manifest_relative_spelling_is_committed_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.json"
    data = tmp_path / "report.json"
    promotions: list[str] = []
    original = os.replace

    def observe(source: Any, destination: Any, *args: Any, **kwargs: Any) -> None:
        if Path(destination).name in {"manifest.json", "report.json"}:
            promotions.append(Path(destination).name)
        original(source, destination, *args, **kwargs)

    monkeypatch.setattr(os, "replace", observe)
    write_artifacts(
        [(manifest, b"manifest"), (data, b"report")],
        manifest=Path(os.path.relpath(manifest)),
    )
    assert promotions == ["report.json", "manifest.json"]


def test_manifest_must_be_an_included_artifact(tmp_path: Path) -> None:
    with pytest.raises(artifact_io.ArtifactOutputError, match="manifest"):
        write_artifacts([(tmp_path / "report.json", b"report")], manifest=tmp_path / "missing")
    assert list(tmp_path.iterdir()) == []
