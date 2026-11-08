"""Cleanup failures expose committed state and retain rollback recovery material."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from nhi_blast.core import artifact_io

pytestmark = pytest.mark.security


@pytest.mark.parametrize("operation", ["unlink", "rmdir"])
def test_postcommit_cleanup_failure_reports_committed_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    target = tmp_path / "report.json"
    target.write_bytes(b"old output")
    original = getattr(Path, operation)

    def broken(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.name.startswith(".nhi-blast-stage-") or self.name == "previous":
            msg = "FIXTURE_ONLY_PRIVATE_CLEANUP_DETAIL"
            raise OSError(msg)
        original(self, *args, **kwargs)

    monkeypatch.setattr(Path, operation, broken)
    with pytest.raises(artifact_io.ArtifactOutputError) as caught:
        artifact_io.write_artifacts([(target, b"new output")])
    assert isinstance(caught.value, artifact_io.ArtifactCleanupError)
    assert caught.value.committed_paths == (target,)
    assert "committed" in str(caught.value)
    assert "cleanup" in str(caught.value)
    assert "FIXTURE_ONLY_PRIVATE" not in str(caught.value)
    assert target.read_bytes() == b"new output"
    assert caught.value.retained_staging_paths
    assert all(path.is_dir() for path in caught.value.retained_staging_paths)


def test_cleanup_failure_after_rollback_does_not_mask_failed_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_bytes(b"old first")
    second.write_bytes(b"old second")
    replace = os.replace
    rmdir = Path.rmdir

    def broken_replace(source: Any, destination: Any) -> None:
        if Path(source).name == "payload" and Path(destination) == second:
            msg = "FIXTURE_ONLY_PRIVATE_PROMOTION_DETAIL"
            raise OSError(msg)
        replace(source, destination)

    def broken_rmdir(self: Path) -> None:
        if self.name.startswith(".nhi-blast-stage-"):
            msg = "FIXTURE_ONLY_PRIVATE_CLEANUP_DETAIL"
            raise OSError(msg)
        rmdir(self)

    monkeypatch.setattr(os, "replace", broken_replace)
    monkeypatch.setattr(Path, "rmdir", broken_rmdir)
    with pytest.raises(artifact_io.ArtifactOutputError) as caught:
        artifact_io.write_artifacts([(first, b"new first"), (second, b"new second")])
    assert isinstance(caught.value, artifact_io.ArtifactCleanupError)
    assert caught.value.committed_paths == ()
    assert "rollback" in str(caught.value)
    assert "cleanup" in str(caught.value)
    assert "FIXTURE_ONLY_PRIVATE" not in str(caught.value)
    assert first.read_bytes() == b"old first"
    assert second.read_bytes() == b"old second"
    assert len(caught.value.retained_staging_paths) == 2


def test_failed_rollback_retains_prior_output_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    first.write_bytes(b"old first")
    second.write_bytes(b"old second")
    replace = os.replace

    def broken_replace(source: Any, destination: Any) -> None:
        source_path, target = Path(source), Path(destination)
        if (source_path.name == "payload" and target == second) or (
            source_path.name == "previous" and target == first
        ):
            msg = "FIXTURE_ONLY_PRIVATE_RECOVERY_DETAIL"
            raise OSError(msg)
        replace(source, destination)

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(artifact_io.ArtifactOutputError, match="rollback incomplete"):
        artifact_io.write_artifacts([(first, b"new first"), (second, b"new second")])
    assert first.read_bytes() == b"new first"
    assert second.read_bytes() == b"old second"
    backups = list(tmp_path.glob(".nhi-blast-stage-*/previous"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"old first"


def test_cleanup_continues_after_one_staging_directory_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    rmdir = Path.rmdir
    attempts: list[Path] = []

    def broken_rmdir(self: Path) -> None:
        if self.name.startswith(".nhi-blast-stage-"):
            attempts.append(self)
            if len(attempts) == 1:
                msg = "cleanup failure"
                raise OSError(msg)
        rmdir(self)

    monkeypatch.setattr(Path, "rmdir", broken_rmdir)
    with pytest.raises(artifact_io.ArtifactOutputError) as caught:
        artifact_io.write_artifacts([(first, b"first"), (second, b"second")])
    assert isinstance(caught.value, artifact_io.ArtifactCleanupError)
    assert caught.value.committed_paths == (first, second)
    assert len(attempts) == 2
    assert caught.value.retained_staging_paths == (attempts[0],)
