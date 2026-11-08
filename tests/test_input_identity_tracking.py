"""Actual opened input identities survive read rejection and path replacement."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, BinaryIO

import pytest

from nhi_blast.core import artifact_io
from nhi_blast.core.config import Config
from nhi_blast.core.limits import Limits
from nhi_blast.discovery import repo, walker
from nhi_blast.discovery.paths import PathGuard
from nhi_blast.discovery.walker import FileKind, InputLoader

pytestmark = pytest.mark.security


class _ShortReadHandle:
    def __init__(self, handle: BinaryIO) -> None:
        self.handle = handle
        self.bytes_read = 0

    def __enter__(self) -> _ShortReadHandle:
        return self

    def __exit__(self, *_args: object) -> None:
        self.handle.close()

    def fileno(self) -> int:
        return self.handle.fileno()

    def tell(self) -> int:
        return self.handle.tell()

    def read(self, size: int = -1) -> bytes:
        data = self.handle.read(min(size, 2))
        self.bytes_read += len(data)
        return data


def _short_reads(path: Path, monkeypatch: pytest.MonkeyPatch) -> list[_ShortReadHandle]:
    original = Path.open
    opened: list[_ShortReadHandle] = []

    def short_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        handle = original(self, *args, **kwargs)
        if self == path and args == ("rb",):
            probe = _ShortReadHandle(handle)
            opened.append(probe)
            return probe
        return handle

    monkeypatch.setattr(Path, "open", short_open)
    return opened


def test_identify_open_input_uses_handle_not_path_stat(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    other = tmp_path / "other.json"
    source.write_bytes(b"source")
    other.write_bytes(b"other")
    with other.open("rb") as handle:
        identity = artifact_io.identify_open_input(source, handle)
        info = os.fstat(handle.fileno())
    assert identity.path == source
    assert (identity.device, identity.inode) == (info.st_dev, info.st_ino)
    with pytest.raises(artifact_io.InputCollisionError):
        artifact_io.write_artifacts([(other, b"output")], inputs=(identity,))
    assert other.read_bytes() == b"other"


@pytest.mark.parametrize("kind", list(FileKind))
@pytest.mark.parametrize("failure", ["oversize", "encoding", "read"])
def test_loader_protects_opened_rejected_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: FileKind, failure: str
) -> None:
    source = tmp_path / "source.input"
    source.write_bytes(b"x" * 9 if failure == "oversize" else b"\xff")
    alias = tmp_path / "output.input"
    os.link(source, alias)
    if failure == "read":
        original = Path.open

        class BrokenRead(_ShortReadHandle):
            def read(self, size: int = -1) -> bytes:
                del size
                msg = "FIXTURE_ONLY_PRIVATE_IO_DETAIL"
                raise OSError(msg)

        def broken_open(self: Path, *args: Any, **kwargs: Any) -> Any:
            handle = original(self, *args, **kwargs)
            return BrokenRead(handle) if self == source else handle

        monkeypatch.setattr(Path, "open", broken_open)
    loader = InputLoader(
        PathGuard.create(tmp_path), Limits(max_yaml_policy_file_bytes=8, max_tf_json_bytes=8)
    )
    assert loader.load(source, kind) is None
    assert loader.loaded_inputs() == ()
    inputs = loader.protected_inputs()
    assert len(inputs) == 1
    assert "FIXTURE_ONLY_PRIVATE" not in repr(loader.diagnostics)
    with pytest.raises(artifact_io.InputCollisionError):
        artifact_io.write_artifacts([(alias, b"output")], inputs=inputs)


@pytest.mark.parametrize("oversize", [False, True])
def test_loader_short_reads_are_complete_and_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, oversize: bool
) -> None:
    source = tmp_path / "source.input"
    data = b"\xef\xbb\xbfhello" if not oversize else b"0123456789"
    source.write_bytes(data)
    probes = _short_reads(source, monkeypatch)
    loader = InputLoader(PathGuard.create(tmp_path), Limits(max_yaml_policy_file_bytes=8))
    loaded = loader.load(source, FileKind.IAM_JSON)
    assert probes[0].bytes_read == (9 if oversize else len(data))
    if oversize:
        assert loaded is None
        assert loader.diagnostics[0].code == "D-IO-LIMIT"
    else:
        assert loaded is not None
        assert loaded.text == "hello"
    assert len(loader.protected_inputs()) == 1


def test_loader_protects_original_name_and_inode_after_replacement(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(b"{}")
    alias = tmp_path / "retained.json"
    os.link(source, alias)
    loader = InputLoader(PathGuard.create(tmp_path), Limits())
    assert loader.load(source, FileKind.IAM_JSON) is not None
    source.unlink()
    source.write_bytes(b"replacement")
    for target in (source, alias):
        with pytest.raises(artifact_io.InputCollisionError):
            artifact_io.write_artifacts([(target, b"output")], inputs=loader.protected_inputs())


@pytest.mark.parametrize("kind", list(FileKind))
def test_loader_protects_source_when_open_is_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: FileKind
) -> None:
    source = tmp_path / "source.input"
    source.write_bytes(b"source bytes")
    alias = tmp_path / "output.input"
    os.link(source, alias)
    original = Path.open

    def denied_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == source and args == ("rb",):
            msg = "FIXTURE_ONLY_PRIVATE_IO_DETAIL"
            raise PermissionError(msg)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_open)
    loader = InputLoader(PathGuard.create(tmp_path), Limits())
    assert loader.load(source, kind) is None
    assert loader.diagnostics[0].code == "D-IO-UNREADABLE"
    assert "FIXTURE_ONLY_PRIVATE" not in repr(loader.diagnostics)
    for target in (source, alias):
        with pytest.raises(artifact_io.InputCollisionError):
            artifact_io.write_artifacts([(target, b"output")], inputs=loader.protected_inputs())
    assert alias.read_bytes() == b"source bytes"


def test_loader_retains_initial_and_actual_opened_inodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.input"
    opened = tmp_path / "opened.input"
    source.write_bytes(b"old source")
    opened.write_bytes(b"actual source")
    prior_alias = tmp_path / "prior-alias.input"
    opened_alias = tmp_path / "opened-alias.input"
    os.link(source, prior_alias)
    os.link(opened, opened_alias)
    original = Path.open

    def swapped_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        return original(opened if self == source else self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", swapped_open)
    loader = InputLoader(PathGuard.create(tmp_path), Limits())
    loaded = loader.load(source, FileKind.IAM_JSON)
    assert loaded is not None
    assert loaded.text == "actual source"
    assert len(loader.protected_inputs()) == 2
    for target in (source, prior_alias, opened_alias):
        with pytest.raises(artifact_io.InputCollisionError):
            artifact_io.write_artifacts([(target, b"output")], inputs=loader.protected_inputs())
    assert prior_alias.read_bytes() == b"old source"
    assert opened_alias.read_bytes() == b"actual source"


@pytest.mark.parametrize("outcome", ["positive", "negative", "open_error", "read_error"])
def test_discovery_sniff_guards_positive_and_uncertain_candidates_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    source = tmp_path / "candidate.json"
    source.write_bytes(b'{"format_version":"1.2","values":{}}' if outcome == "positive" else b"{}")
    alias = tmp_path / "output.json"
    os.link(source, alias)
    original = Path.open

    class BrokenRead(_ShortReadHandle):
        def read(self, size: int = -1) -> bytes:
            del size
            msg = "FIXTURE_ONLY_PRIVATE_SNIFF_DETAIL"
            raise OSError(msg)

    def failing_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == source:
            if outcome == "open_error":
                msg = "FIXTURE_ONLY_PRIVATE_SNIFF_DETAIL"
                raise PermissionError(msg)
            if outcome == "read_error":
                return BrokenRead(original(self, *args, **kwargs))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    discovery = walker.discover(tmp_path, limits=Limits())
    inputs = discovery.protected_inputs
    if outcome == "negative":
        assert inputs == ()
        artifact_io.write_artifacts([(alias, b"ordinary output")], inputs=inputs)
        assert alias.read_bytes() == b"ordinary output"
    else:
        assert inputs
        for target in (source, alias):
            with pytest.raises(artifact_io.InputCollisionError):
                artifact_io.write_artifacts([(target, b"output")], inputs=inputs)
    assert "FIXTURE_ONLY_PRIVATE" not in repr(discovery.diagnostics)


@pytest.mark.parametrize("cap", [8, 65_536, 131_072])
def test_discovery_sniff_reads_only_the_applicable_prefix_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cap: int
) -> None:
    source = tmp_path / "candidate.json"
    source.write_bytes(b"x" * (cap + 1))
    probes = _short_reads(source, monkeypatch)
    discovery = walker.discover(tmp_path, limits=Limits(max_tf_json_bytes=cap))
    assert probes[0].bytes_read == min(65_536, cap)
    assert discovery.files == ()
    assert discovery.protected_inputs == ()


def test_positive_discovery_identity_survives_replacement_before_loading(tmp_path: Path) -> None:
    source = tmp_path / "candidate.json"
    source.write_bytes(b'{"format_version":"1.2","values":{}}')
    alias = tmp_path / "retained.input"
    os.link(source, alias)
    discovery = walker.discover(tmp_path, limits=Limits())
    source.unlink()
    source.write_bytes(b"replacement")
    loader = InputLoader(PathGuard.create(tmp_path), Limits())
    assert loader.load(source, FileKind.TF_JSON) is not None
    inputs = (*discovery.protected_inputs, *loader.protected_inputs())
    with pytest.raises(artifact_io.InputCollisionError):
        artifact_io.write_artifacts([(alias, b"output")], inputs=inputs)
    assert alias.read_bytes().startswith(b'{"format_version"')


def test_config_identity_is_external_and_precedes_its_lowered_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "nhi-blast.toml"
    source.write_text(
        "repo_slug = 'acme/shop'\n[limits]\nmax_yaml_policy_file_bytes = 8\n", encoding="utf-8"
    )
    _short_reads(source, monkeypatch)
    config, identity = Config.from_file_with_identity(source)
    assert config == Config.from_file(source)
    assert config.repo_slug == "acme/shop"
    assert config.limits().max_yaml_policy_file_bytes == 8
    assert not hasattr(config, "protected_inputs")
    assert config.digest() == Config.from_file(source).digest()
    with pytest.raises(artifact_io.InputCollisionError):
        artifact_io.write_artifacts([(source, b"output")], inputs=(identity,))


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\xff",
        b"x" * (1_048_576 + 1),
        b'[remote "origin"]\nurl = git@github.com:acme/shop.git\n',
    ],
    ids=["empty", "encoding", "oversize", "origin"],
)
def test_git_origin_tracks_every_opened_input(tmp_path: Path, payload: bytes) -> None:
    source = tmp_path / ".git" / "config"
    source.parent.mkdir()
    source.write_bytes(payload)
    identity, inputs = repo.resolve_identity_with_inputs(
        root=tmp_path,
        cli_repo_slug=None,
        cli_default_branch=None,
        config_repo_slug=None,
        config_default_branch="main",
    )
    assert identity.slug == ("acme/shop" if b"origin" in payload else None)
    assert len(inputs) == 1
    assert repo.read_git_origin_slug(tmp_path) == identity.slug
    with pytest.raises(artifact_io.InputCollisionError):
        artifact_io.write_artifacts([(source, b"output")], inputs=inputs)


def test_git_origin_open_denied_retains_candidate_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / ".git" / "config"
    source.parent.mkdir()
    source.write_bytes(b'[remote "origin"]\nurl = git@github.com:acme/shop.git\n')
    alias = tmp_path / "output.json"
    os.link(source, alias)
    original = Path.open

    def denied_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self == source and args == ("rb",):
            msg = "FIXTURE_ONLY_PRIVATE_IO_DETAIL"
            raise PermissionError(msg)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_open)
    identity, inputs = repo.resolve_identity_with_inputs(
        root=tmp_path,
        cli_repo_slug=None,
        cli_default_branch=None,
        config_repo_slug=None,
        config_default_branch="main",
    )
    assert identity.slug is None
    for target in (source, alias):
        with pytest.raises(artifact_io.InputCollisionError):
            artifact_io.write_artifacts([(target, b"output")], inputs=inputs)
    assert alias.read_bytes().startswith(b'[remote "origin"]')


@pytest.mark.parametrize("which", ["loader", "git"])
def test_selected_candidate_identity_failure_aborts_conservatively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    source = tmp_path / ".git" / "config" if which == "git" else tmp_path / "source.input"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(b"candidate")

    def unavailable_identity(_path: Path) -> artifact_io.InputIdentity:
        msg = "cannot identify input file"
        raise artifact_io.ArtifactReadError(msg)

    module = repo if which == "git" else walker
    monkeypatch.setattr(module, "identify_input", unavailable_identity, raising=False)
    if which == "git":
        with pytest.raises(artifact_io.ArtifactReadError, match="cannot identify"):
            repo.resolve_identity_with_inputs(
                root=tmp_path,
                cli_repo_slug=None,
                cli_default_branch=None,
                config_repo_slug=None,
                config_default_branch="main",
            )
    else:
        with pytest.raises(artifact_io.ArtifactReadError, match="cannot identify"):
            InputLoader(PathGuard.create(tmp_path), Limits()).load(source, FileKind.IAM_JSON)
    assert source.read_bytes() == b"candidate"


def test_git_origin_short_reads_and_existing_identity_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / ".git" / "config"
    source.parent.mkdir()
    source.write_bytes(b'[remote "origin"]\nurl = git@github.com:acme/shop.git\n')
    _short_reads(source, monkeypatch)
    kwargs: dict[str, Any] = {
        "root": tmp_path,
        "cli_repo_slug": None,
        "cli_default_branch": "release",
        "config_repo_slug": None,
        "config_default_branch": "main",
    }
    identity, inputs = repo.resolve_identity_with_inputs(**kwargs)
    assert identity == repo.resolve_identity(**kwargs)
    assert identity.slug == "acme/shop"
    assert identity.default_branch == "release"
    assert len(inputs) == 1
    overridden, unconsumed = repo.resolve_identity_with_inputs(
        **(kwargs | {"cli_repo_slug": "x/y"})
    )
    assert overridden.slug == "x/y"
    assert unconsumed == ()
