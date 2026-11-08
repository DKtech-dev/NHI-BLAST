"""Staging allocation retries name collisions, never permission or filesystem errors."""

from __future__ import annotations

import errno
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from nhi_blast.core.artifact_io import ArtifactOutputError, write_artifacts

pytestmark = pytest.mark.security


@pytest.mark.parametrize("code", [errno.EACCES, errno.ENOSPC, errno.EINVAL])
def test_staging_creation_does_not_retry_filesystem_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    target = tmp_path / "report.json"
    target.write_bytes(b"previous output")
    original = os.mkdir
    attempts: list[Path] = []

    def broken(path: Any, *args: Any, **kwargs: Any) -> None:
        candidate = Path(path)
        if candidate.name.startswith(".nhi-blast-stage-"):
            attempts.append(candidate)
            raise OSError(code, "FIXTURE_ONLY_PRIVATE_STAGING_DETAIL")
        original(path, *args, **kwargs)

    # Bound the old library loop in the reproduction, not the production behavior.
    monkeypatch.setattr(tempfile, "TMP_MAX", 3)
    monkeypatch.setattr(os, "mkdir", broken)
    monkeypatch.setattr(os, "access", lambda *_args, **_kwargs: True)
    with pytest.raises(ArtifactOutputError) as caught:
        write_artifacts([(target, b"new output")])
    assert len(attempts) == 1
    assert target.read_bytes() == b"previous output"
    assert "FIXTURE_ONLY_PRIVATE" not in str(caught.value)
    assert list(tmp_path.iterdir()) == [target]


def test_staging_name_collisions_retry_without_touching_prior_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "report.json"
    target.write_bytes(b"previous output")
    original = os.mkdir
    attempts: list[Path] = []

    def colliding(path: Any, *args: Any, **kwargs: Any) -> None:
        candidate = Path(path)
        if candidate.name.startswith(".nhi-blast-stage-"):
            attempts.append(candidate)
            assert target.read_bytes() == b"previous output"
            if len(attempts) < 3:
                raise FileExistsError(errno.EEXIST, "occupied stage name")
        original(path, *args, **kwargs)

    monkeypatch.setattr(os, "mkdir", colliding)
    assert write_artifacts([(target, b"new output")]) == (target,)
    assert len(attempts) == len(set(attempts)) == 3
    assert target.read_bytes() == b"new output"
    assert list(tmp_path.iterdir()) == [target]


def test_staging_name_collision_budget_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "report.json"
    target.write_bytes(b"previous output")
    original = os.mkdir
    attempts = 0

    def colliding(path: Any, *args: Any, **kwargs: Any) -> None:
        nonlocal attempts
        if Path(path).name.startswith(".nhi-blast-stage-"):
            attempts += 1
            raise FileExistsError(errno.EEXIST, "occupied stage name")
        original(path, *args, **kwargs)

    monkeypatch.setattr(tempfile, "TMP_MAX", 33)
    monkeypatch.setattr(os, "mkdir", colliding)
    with pytest.raises(ArtifactOutputError):
        write_artifacts([(target, b"new output")])
    assert attempts == 32
    assert target.read_bytes() == b"previous output"
    assert list(tmp_path.iterdir()) == [target]
