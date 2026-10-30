"""Windows standalone distribution: bundle inputs, build pinning and workflow policy."""

from __future__ import annotations

import importlib.util
import os
import posixpath
import re
import tomllib
from pathlib import Path
from types import ModuleType

import pytest
import yaml

pytestmark = pytest.mark.security

ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_windows_exe.py"
ENTRY_SCRIPT = ROOT / "scripts" / "windows_entry.py"
BUILD_LOCK = ROOT / "requirements-windows-build.lock"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"
DATA_DIR = ROOT / "src" / "nhi_blast" / "data"
ASSETS_DIR = ROOT / "src" / "nhi_blast" / "report" / "assets"
VERSION_PIN = re.compile(r"^[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+$")


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _builder() -> ModuleType:
    return _module("build_windows_exe", BUILD_SCRIPT)


def _expected_resources() -> set[str]:
    expected = {f"nhi_blast/data/{path.name}" for path in DATA_DIR.glob("*.yaml")}
    for path in ASSETS_DIR.rglob("*"):
        if not path.is_file() or path.suffix == ".py" or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(ASSETS_DIR).as_posix()
        expected.add(f"nhi_blast/report/assets/{relative}")
    return expected


def test_build_bundles_every_runtime_data_file_and_report_asset() -> None:
    builder = _builder()

    destinations = {destination for _, destination in builder.resource_pairs()}

    assert destinations == _expected_resources() | {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"}
    assert any(name.endswith("rules.yaml") for name in destinations)
    assert any(name.endswith("MANIFEST.json") for name in destinations)
    assert any(name.endswith("geist-latin.woff2") for name in destinations)
    assert any(name.endswith("motion-14.7.1.min.js") for name in destinations)
    assert not any(
        "__pycache__" in name or name.endswith((".pyc", ".pyo")) for name in destinations
    )
    assert not any(name.endswith(".py") for name in destinations)


def test_build_is_a_console_one_file_executable_with_optional_support() -> None:
    builder = _builder()
    command = builder.pyinstaller_command(dist_dir=ROOT / "out", work_dir=ROOT / "work")

    assert "--onefile" in command
    assert "--console" in command
    assert "--noupx" in command
    assert command[command.index("--name") + 1] == "nhi-blast-windows-x64"
    assert str(ENTRY_SCRIPT) in command
    hidden = [command[index + 1] for index, item in enumerate(command) if item == "--hidden-import"]
    assert {"hcl2", "rich"} <= set(hidden)
    pairs = [command[index + 1] for index, item in enumerate(command) if item == "--collect-data"]
    assert "hcl2" in pairs
    modules = [
        command[index + 1] for index, item in enumerate(command) if item == "--collect-submodules"
    ]
    assert {"hcl2", "lark", "rich"} <= set(modules)
    assert any("nhi_blast/data" in argument for argument in command)
    assert any("nhi_blast/report/assets" in argument for argument in command)


def test_build_adds_each_resource_to_its_parent_directory() -> None:
    builder = _builder()
    command = builder.pyinstaller_command(dist_dir=ROOT / "out", work_dir=ROOT / "work")
    arguments = [command[index + 1] for index, item in enumerate(command) if item == "--add-data"]

    destinations = {argument.rsplit(os.pathsep, 1)[1] for argument in arguments}

    assert destinations == {
        posixpath.dirname(name) or "." for name in builder.bundled_resource_names()
    }
    assert "." in destinations
    assert not any(
        destination.endswith((".yaml", ".json", ".woff2", ".js", ".txt"))
        for destination in destinations
    )


def test_frozen_entrypoint_calls_the_installed_cli_main() -> None:
    text = ENTRY_SCRIPT.read_text(encoding="utf-8")

    assert "from nhi_blast.cli.app import main" in text
    assert "main()" in text


def test_windows_build_lock_pins_the_whole_build_toolchain() -> None:
    lines = [
        line.strip()
        for line in BUILD_LOCK.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert lines
    for line in lines:
        assert VERSION_PIN.fullmatch(line), line
        assert "http" not in line
        assert "-e " not in line
    pins = dict(line.split("==", 1) for line in lines)
    assert pins["pyinstaller"] == "6.22.3"
    assert pins["pyinstaller-hooks-contrib"] == "2026.8"
    assert {"altgraph", "packaging", "pefile", "pywin32-ctypes", "setuptools"} <= set(pins)


def test_sdist_contains_the_windows_build_inputs() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = config["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]

    assert "requirements-windows-build.lock" in include


def test_windows_workflow_is_manual_only_and_never_publishes() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    document = yaml.safe_load(text)

    assert set(document["on"]) == {"workflow_dispatch"}
    assert document["jobs"]["build"]["runs-on"] == "windows-latest"
    for step in (
        "python scripts/build_windows_exe.py",
        "python scripts/check_artifacts.py dist/windows --windows-exe",
        "python -m pytest -q tests/test_windows_executable.py",
    ):
        assert step in text, step
    assert "actions/upload-artifact@" in text
    assert "nhi-blast-windows-x64.exe" in text
    assert "nhi-blast-windows-x64.exe.sha256" in text
    assert "THIRD_PARTY_NOTICES.md" in text
    for forbidden in (
        "gh release",
        "twine",
        "pypi",
        "action-gh-release",
        "docker push",
        "publish:",
    ):
        assert forbidden not in text.lower(), forbidden


def test_readme_and_contributing_document_the_verified_windows_flow() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "nhi-blast-windows-x64.exe" in readme
    assert "Get-FileHash" in readme
    assert "does not require Python" in readme
    assert "Releases" in readme
    assert "unsigned" in readme.lower()
    assert "scripts/build_windows_exe.py" in contributing
    assert "requirements-windows-build.lock" in contributing
    assert "nhi-blast-windows-x64.exe" in contributing
