"""Resolution of this environment's installed CLI entrypoint across layouts."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.entrypoint_support import EntrypointNotFoundError, resolve_cli_entrypoint


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"MZ")
    return path


def _no_match(_name: str) -> None:
    return None


def test_windows_toolcache_layout_finds_scripts_directory_entrypoint(tmp_path: Path) -> None:
    prefix = tmp_path / "Python" / "3.12.10" / "x64"
    interpreter = _touch(prefix / "python.exe")
    script = _touch(prefix / "Scripts" / "nhi-blast.exe")

    resolved = resolve_cli_entrypoint(
        executable=interpreter,
        scripts_directory=prefix / "Scripts",
        platform="nt",
        which=_no_match,
    )

    assert resolved == script
    assert resolved != prefix / "nhi-blast.exe"


def test_posix_layout_finds_scripts_directory_entrypoint(tmp_path: Path) -> None:
    prefix = tmp_path / "env"
    interpreter = _touch(prefix / "bin" / "python")
    script = _touch(prefix / "bin" / "nhi-blast")

    resolved = resolve_cli_entrypoint(
        executable=interpreter,
        scripts_directory=prefix / "bin",
        platform="posix",
        which=_no_match,
    )

    assert resolved == script


def test_configured_scripts_directory_wins_over_path_and_interpreter_neighbours(
    tmp_path: Path,
) -> None:
    interpreter = _touch(tmp_path / "prefix" / "python.exe")
    configured = _touch(tmp_path / "prefix" / "Scripts" / "nhi-blast.exe")
    on_path = _touch(tmp_path / "path" / "nhi-blast.exe")
    beside = _touch(tmp_path / "prefix" / "nhi-blast.exe")

    resolved = resolve_cli_entrypoint(
        executable=interpreter,
        scripts_directory=tmp_path / "prefix" / "Scripts",
        platform="nt",
        which=lambda _name: str(on_path),
    )

    assert resolved == configured
    assert resolved not in {on_path, beside}


def test_path_lookup_is_the_fallback_when_the_scripts_directory_has_no_entrypoint(
    tmp_path: Path,
) -> None:
    interpreter = _touch(tmp_path / "prefix" / "python")
    (tmp_path / "prefix" / "bin").mkdir()
    on_path = _touch(tmp_path / "user" / "bin" / "nhi-blast")

    resolved = resolve_cli_entrypoint(
        executable=interpreter,
        scripts_directory=tmp_path / "prefix" / "bin",
        platform="posix",
        which=lambda _name: str(on_path),
    )

    assert resolved == on_path


def test_entrypoint_beside_the_interpreter_remains_a_last_resort(tmp_path: Path) -> None:
    interpreter = _touch(tmp_path / "env" / "Scripts" / "python.exe")
    beside = _touch(tmp_path / "env" / "Scripts" / "nhi-blast.exe")

    resolved = resolve_cli_entrypoint(
        executable=interpreter,
        scripts_directory=tmp_path / "elsewhere",
        platform="nt",
        which=_no_match,
    )

    assert resolved == beside


def test_missing_entrypoint_reports_every_searched_location(tmp_path: Path) -> None:
    interpreter = _touch(tmp_path / "Python" / "x64" / "python.exe")
    scripts_directory = tmp_path / "Python" / "x64" / "Scripts"
    scripts_directory.mkdir()

    with pytest.raises(EntrypointNotFoundError) as excinfo:
        resolve_cli_entrypoint(
            executable=interpreter,
            scripts_directory=scripts_directory,
            platform="nt",
            which=_no_match,
        )

    message = str(excinfo.value)
    assert str(interpreter) in message
    assert str(scripts_directory / "nhi-blast.exe") in message
    assert str(interpreter.parent / "nhi-blast.exe") in message
    assert "pip install" in message


def test_a_directory_with_the_entrypoint_name_is_not_accepted(tmp_path: Path) -> None:
    interpreter = _touch(tmp_path / "prefix" / "python.exe")
    (tmp_path / "prefix" / "Scripts" / "nhi-blast.exe").mkdir(parents=True)

    with pytest.raises(EntrypointNotFoundError):
        resolve_cli_entrypoint(
            executable=interpreter,
            scripts_directory=tmp_path / "prefix" / "Scripts",
            platform="nt",
            which=_no_match,
        )
