"""Bounded input/config reads and controlled hostile-input failures."""

from __future__ import annotations

import ctypes
import io
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import IO, Any

import pytest
from typer.testing import CliRunner

from nhi_blast.cli.app import app
from nhi_blast.core.config import Config, ConfigError
from nhi_blast.core.limits import Limits
from nhi_blast.discovery.paths import PathGuard
from nhi_blast.discovery.walker import FileKind, InputLoader, discover

pytestmark = pytest.mark.security

_CONFIG_CAP = 5 * 1024 * 1024


class _ReadProbe(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.requests: list[int] = []
        self.bytes_read = 0

    def read(self, size: int = -1, /) -> bytes:
        self.requests.append(size)
        data = super().read(size)
        self.bytes_read += len(data)
        return data


def _observe_reads(path: Path, monkeypatch: pytest.MonkeyPatch) -> _ReadProbe:
    probe = _ReadProbe(path.read_bytes())
    original = Path.open

    def recording_open(self: Path, *args: Any, **kwargs: Any) -> IO[Any]:
        if self == path:
            return probe
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording_open)
    return probe


@pytest.mark.parametrize("kind", list(FileKind))
def test_input_loader_reads_only_limit_plus_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: FileKind
) -> None:
    path = tmp_path / "oversize.input"
    path.write_bytes(b"x" * 128)
    probe = _observe_reads(path, monkeypatch)
    loader = InputLoader(
        guard=PathGuard.create(tmp_path),
        limits=Limits(max_yaml_policy_file_bytes=8, max_tf_json_bytes=16),
    )
    limit = 16 if kind is FileKind.TF_JSON else 8

    assert loader.load(path, kind) is None
    assert probe.requests == [limit + 1]
    assert probe.bytes_read == limit + 1
    assert loader.loaded_inputs() == ()
    assert len(loader.diagnostics) == 1
    diagnostic = loader.diagnostics[0]
    assert (diagnostic.code, diagnostic.level.value) == ("D-IO-LIMIT", "error")
    assert str(limit) in diagnostic.message
    assert f"file is {limit + 1} bytes" not in diagnostic.message


def test_config_read_is_bounded_and_exact_cap_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "nhi-blast.toml"
    prefix = b"repo_slug = 'acme/shop'\n#"
    path.write_bytes(prefix + b" " * (_CONFIG_CAP - len(prefix)))
    probe = _observe_reads(path, monkeypatch)

    config = Config.from_file(path)

    assert probe.requests == [_CONFIG_CAP + 1]
    assert probe.bytes_read == _CONFIG_CAP
    assert config.repo_slug == "acme/shop"


@pytest.mark.parametrize("self_override", [False, True])
def test_oversize_config_rejected_before_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, self_override: bool
) -> None:
    path = tmp_path / "nhi-blast.toml"
    prefix = b"repo_slug = 'acme/oversized'\n"
    if self_override:
        prefix += b"[limits]\nmax_yaml_policy_file_bytes = 10485760\n"
    prefix += b"#"
    path.write_bytes(prefix + b" " * (_CONFIG_CAP + 100 - len(prefix)))
    probe = _observe_reads(path, monkeypatch)

    def unexpected_parse(_text: str) -> dict[str, Any]:
        pytest.fail("oversized configuration must not reach the TOML parser")

    monkeypatch.setattr("nhi_blast.core.config.tomllib.loads", unexpected_parse)

    with pytest.raises(ConfigError, match="limit"):
        Config.from_file(path)

    assert probe.requests == [_CONFIG_CAP + 1]
    assert probe.bytes_read == _CONFIG_CAP + 1


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("self_override", [False, True])
def test_cli_never_applies_oversize_config(
    tmp_path: Path, explicit: bool, self_override: bool
) -> None:
    path = tmp_path / ("explicit.toml" if explicit else "nhi-blast.toml")
    prefix = b"repo_slug = 'acme/oversized'\n"
    if self_override:
        prefix += b"[limits]\nmax_yaml_policy_file_bytes = 10485760\n"
    prefix += b"#"
    path.write_bytes(prefix + b" " * (_CONFIG_CAP + 1 - len(prefix)))
    out = tmp_path / "reports"
    args = ["scan", str(tmp_path), "--format", "json", "--out", str(out)]
    if explicit:
        args.extend(["--config", str(path)])

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 2
    assert "limit" in result.stderr
    assert "acme/oversized" not in result.output
    assert not out.exists()


@pytest.mark.parametrize("failure", ["recursion", "duplicate_table", "utf8", "giant_integer"])
def test_config_parse_errors_are_controlled_and_do_not_echo_input(
    tmp_path: Path, failure: str
) -> None:
    path = tmp_path / "nhi-blast.toml"
    sentinel = "FIXTURE_ONLY_PRIVATE_CONFIG_KEY"
    payloads = {
        "recursion": f"{sentinel} = " + "[" * 600 + "0" + "]" * 600,
        "duplicate_table": f"[{sentinel}]\n[{sentinel}]\n",
        "utf8": f"{sentinel} = '",
        # CPython int parsing rejects >4300 digits with a plain ValueError, not
        # TOMLDecodeError; the config boundary must still produce a usage error.
        "giant_integer": f"# {sentinel}\nmax_files = " + "1" * 5000 + "\n",
    }
    data = payloads[failure].encode("utf-8")
    if failure == "utf8":
        data += b"\xff'"
    path.write_bytes(data)

    with pytest.raises(ConfigError) as caught:
        Config.from_file(path)

    assert sentinel not in str(caught.value)
    result = CliRunner().invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 2
    assert sentinel not in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("budget", [float("nan"), float("inf"), float("-inf")])
def test_limits_reject_nonfinite_budgets(budget: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        Limits.from_mapping({"scenario_time_budget_seconds": budget})


@pytest.mark.parametrize("budget", ["nan", "+nan", "-nan", "inf", "+inf", "-inf", "1e999"])
def test_nonfinite_config_budget_is_a_usage_error(tmp_path: Path, budget: str) -> None:
    path = tmp_path / "nhi-blast.toml"
    path.write_text(f"[limits]\nscenario_time_budget_seconds = {budget}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="finite"):
        Config.from_file(path)

    result = CliRunner().invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 2
    assert "finite" in result.stderr


@pytest.mark.parametrize("budget", [0, 0.0, 0.25, 60, 60.0])
def test_finite_nonnegative_budget_remains_valid(budget: int | float) -> None:
    config = Config.from_mapping({"limits": {"scenario_time_budget_seconds": budget}})

    assert (
        Limits.from_mapping({"scenario_time_budget_seconds": budget}).scenario_time_budget_seconds
        == budget
    )
    assert config.limits().scenario_time_budget_seconds == budget


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("fail_during_read", [False, True])
def test_unreadable_autodetect_json_is_diagnostic_and_preserves_strict_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, strict: bool, fail_during_read: bool
) -> None:
    path = tmp_path / "ordinary.json"
    path.write_text("{}", encoding="utf-8")
    (tmp_path / "action.yml").write_text(
        "name: local\nruns:\n  using: composite\n  steps: []\n", encoding="utf-8"
    )
    original = Path.open
    sentinel = "FIXTURE_ONLY_PRIVATE_IO_DETAIL"

    class UnreadableStream(io.BytesIO):
        def read(self, size: int = -1, /) -> bytes:
            del size
            raise PermissionError(sentinel)

    def unreadable_open(self: Path, *args: Any, **kwargs: Any) -> IO[Any]:
        if self == path:
            if fail_during_read:
                return UnreadableStream()
            raise PermissionError(sentinel)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unreadable_open)
    discovery = discover(tmp_path, limits=Limits())

    assert [item.rel for item in discovery.files] == ["action.yml"]
    assert len(discovery.diagnostics) == 1
    diagnostic = discovery.diagnostics[0]
    assert (diagnostic.code, diagnostic.level.value, diagnostic.file) == (
        "D-IO-UNREADABLE",
        "error",
        "ordinary.json",
    )
    assert sentinel not in diagnostic.message

    out = tmp_path / "reports"
    args = ["scan", str(tmp_path), "--format", "json", "--out", str(out)]
    if strict:
        args.append("--strict")
    result = CliRunner().invoke(app, args)

    assert result.exit_code == (3 if strict else 0)
    payload = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert any(
        item["code"] == "D-IO-UNREADABLE" and item["file"] == "ordinary.json"
        for item in payload["diagnostics"]
    )
    assert sentinel not in result.output
    assert sentinel not in json.dumps(payload)


@pytest.mark.skipif(os.name != "nt", reason="requires Windows file sharing semantics")
def test_windows_sharing_violation_is_a_strict_scan_error(tmp_path: Path) -> None:
    path = tmp_path / "locked.json"
    path.write_text("{}", encoding="utf-8")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    # Open an existing file for reading without sharing access with other handles.
    handle = create_file(str(path), 0x80000000, 0, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    try:
        result = CliRunner().invoke(app, ["scan", str(tmp_path), "--strict"])

        assert result.exit_code == 3
        assert "D-IO-UNREADABLE" in result.stdout
        assert "locked.json" in result.stdout
    finally:
        assert close_handle(handle)
