"""Bounded input reads and rollback-capable artifact promotion.

Identities are transient input guards, never report metadata. Staging protects prior
outputs against render/write failures; promotion is not cross-file atomic and assumes
output directories are not concurrently modified by a hostile process.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4


class ArtifactReadError(ValueError):
    """An input cannot be read within its byte and encoding bounds."""


class ArtifactOutputError(OSError):
    """Artifacts could not be staged or committed."""


class ArtifactCleanupError(ArtifactOutputError):
    """Cleanup or recovery is incomplete; filesystem paths stay out of the message."""

    def __init__(
        self,
        message: str,
        *,
        committed_paths: tuple[Path, ...],
        retained_staging_paths: tuple[Path, ...],
    ) -> None:
        super().__init__(message)
        self.committed_paths = committed_paths
        self.retained_staging_paths = retained_staging_paths


class InputCollisionError(ArtifactOutputError):
    """An output aliases a protected input."""


@dataclass(frozen=True, slots=True)
class InputIdentity:
    path: Path
    resolved_path: Path
    device: int
    inode: int


def _identity(path: Path, info: os.stat_result) -> InputIdentity:
    return InputIdentity(
        Path(os.path.abspath(path.expanduser())),
        path.expanduser().resolve(),
        info.st_dev,
        info.st_ino,
    )


def identify_input(path: Path) -> InputIdentity:
    """Capture an existing input's names and same-file identity without reading its bytes."""
    try:
        return _identity(path, path.expanduser().stat())
    except (OSError, RuntimeError, ValueError):
        msg = "cannot identify input file"
        raise ArtifactReadError(msg) from None


def identify_open_input(path: Path, handle: BinaryIO) -> InputIdentity:
    """Capture names and the actual opened regular file's fstat identity."""
    try:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            msg = "opened input is not a regular file"
            raise ArtifactReadError(msg)
        return _identity(path, info)
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, ArtifactReadError):
            raise
        msg = "cannot identify opened input file"
        raise ArtifactReadError(msg) from None


def read_bounded_stream(
    handle: BinaryIO,
    max_bytes: int,
    *,
    chunk_bytes: int = 64 * 1024,
    stop_at_file_end: bool = False,
) -> bytes:
    """Read at most max_bytes+1 bytes, including streams that return short reads."""
    if max_bytes < 0:
        msg = "byte limit must be non-negative"
        raise ArtifactReadError(msg)
    if chunk_bytes < 1:
        msg = "read chunk size must be positive"
        raise ArtifactReadError(msg)
    chunks: list[bytes] = []
    consumed = 0
    while consumed <= max_bytes:
        requested = min(chunk_bytes, max_bytes + 1 - consumed)
        chunk = handle.read(requested)
        if not chunk:
            break
        chunks.append(chunk)
        consumed += len(chunk)
        # Opened regular files can establish EOF without an extra read probe. A short
        # read before that position still loops; the byte cap is independent of stat.
        if (
            stop_at_file_end
            and len(chunk) < requested
            and handle.tell() >= os.fstat(handle.fileno()).st_size
        ):
            break
    if consumed > max_bytes:
        msg = f"input is larger than the {max_bytes}-byte limit"
        raise ArtifactReadError(msg)
    return b"".join(chunks)


def read_bounded_utf8(path: Path, max_bytes: int) -> tuple[str, InputIdentity]:
    """Strictly decode the bounded actual opened regular file and capture its fstat identity."""
    candidate = path.expanduser()
    try:
        if not candidate.is_file():
            msg = "input path is not a file"
            raise ArtifactReadError(msg)
        with candidate.open("rb") as handle:
            identity = identify_open_input(candidate, handle)
            raw = read_bounded_stream(handle, max_bytes)
        return raw.decode("utf-8"), identity
    except UnicodeDecodeError:
        msg = "input file is not UTF-8"
        raise ArtifactReadError(msg) from None
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, ArtifactReadError):
            raise
        msg = "cannot read input file"
        raise ArtifactReadError(msg) from None


def _aliases(path: Path, identity: InputIdentity) -> bool:
    absolute = Path(os.path.abspath(path.expanduser()))
    resolved = path.expanduser().resolve()
    if absolute in {identity.path, identity.resolved_path} or resolved in {
        identity.path,
        identity.resolved_path,
    }:
        return True
    try:
        info = path.stat()
    except FileNotFoundError:
        return False
    return (info.st_dev, info.st_ino) == (identity.device, identity.inode)


def _check_targets(targets: Sequence[Path], inputs: Sequence[InputIdentity]) -> None:
    seen: list[InputIdentity] = []
    names: set[Path] = set()
    for target in targets:
        if any(_aliases(target, source) for source in inputs):
            msg = "output would overwrite a protected input file"
            raise InputCollisionError(msg)
        resolved = target.resolve()
        if resolved in names or any(_aliases(target, prior) for prior in seen):
            msg = "output artifact paths alias one another"
            raise ArtifactOutputError(msg)
        names.add(resolved)
        if target.exists():
            if not target.is_file():
                msg = "output artifact path is not a file"
                raise ArtifactOutputError(msg)
            seen.append(_identity(target, target.stat()))


def _create_staging_directory(parent: Path) -> Path:
    """Retry only genuine name collisions, never permission denial or other IO errors.

    Windows tempfile.mkdtemp can mistake denied parent writes for name collisions
    because os.access does not reliably reflect ACLs. Bound collision retries and
    let all other mkdir failures reach the artifact error boundary immediately.
    """
    for _attempt in range(32):
        directory = parent / f".nhi-blast-stage-{uuid4().hex}"
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            continue
        return directory
    msg = "cannot allocate a staging directory within 32 attempts"
    raise ArtifactOutputError(msg)


@dataclass(slots=True)
class _Staged:
    target: Path
    directory: Path
    content: Path
    backup: Path
    device: int
    inode: int
    backed_up: bool = False
    promoted: bool = False


def _rollback(stages: Sequence[_Staged]) -> bool:
    restored = True
    for stage in reversed(stages):
        try:
            if stage.promoted:
                info = stage.target.stat()
                if (info.st_dev, info.st_ino) != (stage.device, stage.inode):
                    restored = False
                    continue
                if not stage.backed_up:
                    stage.target.unlink()
            if stage.backed_up:
                os.replace(stage.backup, stage.target)
                stage.backed_up = False
            stage.promoted = False
        except OSError:
            restored = False
    return restored


def _cleanup(
    stages: Sequence[_Staged], *, committed: bool = False
) -> tuple[tuple[Path, ...], bool]:
    retained: list[Path] = []
    clean = True
    for stage in stages:
        try:
            stage.content.unlink(missing_ok=True)
            # Failed rollback backups remain available for explicit recovery.
            if committed or not stage.backed_up:
                stage.backup.unlink(missing_ok=True)
                stage.backed_up = False
                stage.directory.rmdir()
            else:
                retained.append(stage.directory)
        except OSError:
            clean = False
            retained.append(stage.directory)
    return tuple(retained), clean


def write_artifacts(
    artifacts: Sequence[tuple[Path, bytes]],
    *,
    inputs: Sequence[InputIdentity] = (),
    manifest: Path | None = None,
) -> tuple[Path, ...]:
    """Stage every rendered artifact, then promote with an optional manifest last.

    Existing target files are prior outputs, not permission to replace any protected
    input: callers must supply every input identity even with a force option.
    """
    output_paths = tuple(path.expanduser() for path, _ in artifacts)
    targets = tuple(Path(os.path.abspath(path)) for path in output_paths)
    manifest_path = None if manifest is None else Path(os.path.abspath(manifest.expanduser()))
    stages: list[_Staged] = []
    try:
        if manifest_path is not None and manifest_path not in targets:
            msg = "manifest must be an included output artifact"
            raise ArtifactOutputError(msg)
        _check_targets(targets, inputs)
        for (_, data), target in zip(artifacts, targets, strict=True):
            target.parent.mkdir(parents=True, exist_ok=True)
            directory = _create_staging_directory(target.parent)
            content = directory / "payload"
            stage = _Staged(target, directory, content, directory / "previous", 0, 0)
            stages.append(stage)
            with content.open("xb") as handle:
                handle.write(data)
            info = content.stat()
            stage.device, stage.inode = info.st_dev, info.st_ino
        _check_targets(targets, inputs)
        ordered = sorted(stages, key=lambda stage: stage.target == manifest_path)
        for stage in ordered:
            if stage.target.exists() or stage.target.is_symlink():
                os.replace(stage.target, stage.backup)
                stage.backed_up = True
            os.replace(stage.content, stage.target)
            stage.promoted = True
    except (OSError, RuntimeError, ValueError) as exc:
        restored = _rollback(stages)
        retained, clean = _cleanup(stages)
        if not clean or not restored:
            status = "rollback completed" if restored else "rollback incomplete"
            msg = f"artifact write failed; {status}; staging cleanup incomplete"
            raise ArtifactCleanupError(
                msg,
                committed_paths=tuple(stage.target for stage in stages if stage.promoted),
                retained_staging_paths=retained,
            ) from None
        if isinstance(exc, ArtifactOutputError):
            raise
        msg = "cannot write artifacts"
        raise ArtifactOutputError(msg) from None
    retained, clean = _cleanup(stages, committed=True)
    if not clean:
        msg = "artifacts committed; staging cleanup incomplete"
        raise ArtifactCleanupError(
            msg, committed_paths=output_paths, retained_staging_paths=retained
        ) from None
    return output_paths
