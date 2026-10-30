"""Regression checks for the distribution artifact inspector."""

from __future__ import annotations

import hashlib
import importlib.util
import tomllib
from pathlib import Path
from types import ModuleType
from typing import ClassVar

import pytest

pytestmark = pytest.mark.security

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_artifacts.py"
EXE_NAME = "nhi-blast-windows-x64.exe"
LICENCE_FILES = ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")
BUNDLED_THIRD_PARTY_DISTRIBUTIONS = (
    "PyYAML",
    "Pygments",
    "altgraph",
    "annotated-types",
    "attrs",
    "click",
    "colorama",
    "lark",
    "markdown-it-py",
    "mdurl",
    "networkx",
    "packaging",
    "pefile",
    "pydantic",
    "pydantic_core",
    "pyinstaller",
    "python-hcl2",
    "pywin32-ctypes",
    "regex",
    "rich",
    "setuptools",
    "shellingham",
    "trove-classifiers",
    "typer",
    "typing-inspection",
    "typing_extensions",
)


def _checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_artifacts", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fake_pe(path: Path) -> None:
    payload = bytearray(0x100)
    payload[0:2] = b"MZ"
    payload[0x3C:0x40] = (0x80).to_bytes(4, "little")
    payload[0x80:0x84] = b"PE\0\0"
    path.write_bytes(bytes(payload))


def _windows_entries(checker: ModuleType, *, separators: str = "/") -> dict[str, int]:
    return {name.replace("/", separators): 1 for name in checker.WINDOWS_REQUIRED_RESOURCES} | {
        "PYZ.pyz": 1,
        "nhi_blast/cli/app.pyc": 1,
    }


def _write_checksum(exe: Path, digest: str | None = None) -> Path:
    actual = hashlib.sha256(exe.read_bytes()).hexdigest() if digest is None else digest
    path = exe.with_name(exe.name + ".sha256")
    path.write_text(f"{actual}  {exe.name}\n", encoding="ascii", newline="\n")
    return path


class _CleanArchive:
    def __init__(self, checker: ModuleType) -> None:
        self.checker = checker
        self.toc = dict.fromkeys(checker.WINDOWS_REQUIRED_RESOURCES, (0, 0, 0, 0, "x"))

    def extract(self, name: str) -> bytes:
        if name == "THIRD_PARTY_NOTICES.md":
            lines = [
                *self.checker.BUNDLED_NOTICE_COMPONENTS,
                *self.checker.NOTICE_REQUIRED_PHRASES,
            ]
            return "\n".join(lines).encode()
        return b"clean payload"


def test_optional_extras_are_not_runtime_requirements() -> None:
    checker = _checker()
    metadata = "\n".join(
        [
            "Requires-Dist: pydantic<3,>=2.9",
            "Requires-Dist: PyYAML<7,>=6.0.2",
            "Provides-Extra: dev",
            "Requires-Dist: pytest<10,>=9.0.3; extra == 'dev'",
            "Requires-Dist: hypothesis<7; extra == 'dev'",
        ]
    )
    runtime = checker._requirement_names(metadata, runtime_only=True)
    assert runtime == {"pydantic", "pyyaml"}
    assert "pytest" in checker._requirement_names(metadata)


def test_environment_markers_without_extra_stay_runtime() -> None:
    checker = _checker()
    metadata = "Requires-Dist: colorama>=0.4; sys_platform == 'win32'"
    assert checker._requirement_names(metadata, runtime_only=True) == {"colorama"}


def test_normalisation_preserves_leading_dots() -> None:
    checker = _checker()
    assert checker._normalise("./.taste-skill/direction.json") == ".taste-skill/direction.json"
    assert checker._normalise(".venv/lib/python3.12/site.py") == ".venv/lib/python3.12/site.py"
    assert checker._normalise("./src/nhi_blast/__init__.py") == "src/nhi_blast/__init__.py"


def test_sdist_allowlist_rejects_unexpected_scratch_roots() -> None:
    checker = _checker()
    entries = {
        "pyproject.toml": 1,
        "src/nhi_blast/__init__.py": 1,
        ".buildcheck/consumer/lib/site-packages/x.py": 1,
        ".buildcheck/shots/graph.png": 1,
    }

    assert checker._unexpected_sdist_roots(entries) == [".buildcheck"]


def test_local_only_files_are_rejected_in_any_artifact() -> None:
    checker = _checker()
    for label, name in (
        ("sdist", "docs/engineering-checkpoint.md"),
        ("sdist", "./docs/engineering-checkpoint.md"),
        ("wheel", "docs/engineering-checkpoint.md"),
    ):
        failures = checker._check_common(label, {name: 12, "pyproject.toml": 1})
        assert any("local-only file" in failure for failure in failures), (label, name, failures)


def test_clean_artifact_has_no_local_only_findings() -> None:
    checker = _checker()
    assert checker._check_common("wheel", {"nhi_blast/__init__.py": 10}) == []
    assert checker._check_common("sdist", {"docs/SPEC.md": 10, "pyproject.toml": 10}) == []


def test_sdist_build_config_excludes_local_only_docs() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    sdist = config["tool"]["hatch"]["build"]["targets"]["sdist"]
    assert "docs" in sdist["include"]
    assert "docs/engineering-checkpoint.md" in sdist["exclude"]
    assert "requirements-windows-build.lock" in sdist["include"]
    assert "THIRD_PARTY_NOTICES.md" in sdist["include"]


def test_project_is_mit_licensed() -> None:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]

    assert project["license"] == "MIT"
    assert set(project["license-files"]) == set(LICENCE_FILES)
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert licence.startswith("MIT License\n")
    assert "Copyright (c) 2026 NHI-Blast Maintainers" in licence
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "MIT License" in notice
    assert "proprietary" not in notice.lower()


def test_third_party_notices_cover_the_frozen_runtime() -> None:
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8").lower()

    for distribution in BUNDLED_THIRD_PARTY_DISTRIBUTIONS:
        assert distribution.lower() in notices, distribution
    assert "python software foundation" in notices
    assert "bootloader exception" in notices
    assert "apache license" in notices
    assert "bsd-3-clause" in notices
    assert "isc license" in notices


def test_wheel_metadata_must_declare_mit_and_licence_files() -> None:
    checker = _checker()
    good = "\n".join(
        [
            "Metadata-Version: 2.4",
            "License-Expression: MIT",
            "License-File: LICENSE",
            "License-File: NOTICE",
            "License-File: THIRD_PARTY_NOTICES.md",
        ]
    )
    assert checker._licence_metadata_failures(good) == []

    failures = checker._licence_metadata_failures("License-Expression: LicenseRef-Proprietary")
    assert any("License-Expression" in failure for failure in failures), failures

    failures = checker._licence_metadata_failures(
        "License-Expression: MIT\nLicense-File: LICENSE\nLicense-File: NOTICE"
    )
    assert any("THIRD_PARTY_NOTICES.md" in failure for failure in failures), failures


def test_declared_licence_files_must_exist_in_the_artifact() -> None:
    checker = _checker()
    prefix = "nhi_blast-0.2.0.dist-info/licenses/"
    entries = {f"{prefix}{name}": 1 for name in LICENCE_FILES}

    assert checker._licence_entry_failures("wheel", entries) == []

    del entries[f"{prefix}NOTICE"]
    failures = checker._licence_entry_failures("wheel", entries)
    assert any("NOTICE" in failure for failure in failures), failures


def test_windows_archive_requires_every_runtime_resource() -> None:
    checker = _checker()

    assert checker.check_windows_entries(_windows_entries(checker)) == []
    assert checker.check_windows_entries(_windows_entries(checker, separators="\\")) == []

    for name in sorted(checker.WINDOWS_REQUIRED_RESOURCES)[:3]:
        entries = _windows_entries(checker)
        del entries[name]
        failures = checker.check_windows_entries(entries)
        assert any(name in failure and "missing" in failure for failure in failures), failures


def test_windows_archive_requires_the_licence_and_notices() -> None:
    checker = _checker()

    for name in LICENCE_FILES:
        assert name in checker.WINDOWS_REQUIRED_RESOURCES
        entries = _windows_entries(checker)
        del entries[name]
        failures = checker.check_windows_entries(entries)
        assert any(name in failure and "missing" in failure for failure in failures), failures


def test_windows_archive_rejects_local_only_and_development_content() -> None:
    checker = _checker()

    for name, expected in (
        ("docs/engineering-checkpoint.md", "local-only"),
        (".claude/settings.json", "forbidden"),
        ("docs/research/_cache/source.txt", "forbidden"),
        ("nhi-blast-out/report.html", "forbidden"),
    ):
        entries = _windows_entries(checker)
        entries[name] = 1
        failures = checker.check_windows_entries(entries)
        assert any(expected in failure for failure in failures), (name, failures)


@pytest.mark.parametrize(
    "name", ["../escape.txt", "/absolute.txt", "C:/Windows/system32/evil.dll", ""]
)
def test_windows_archive_rejects_unsafe_paths(name: str) -> None:
    checker = _checker()
    entries = _windows_entries(checker)
    entries[name] = 1

    failures = checker.check_windows_entries(entries)

    assert any("unsafe archive path" in failure for failure in failures), failures


def test_windows_secret_scan_flags_values_without_echoing_them() -> None:
    checker = _checker()
    token = "ghp_" + "A" * 36

    label = checker._leak_label(f"prefix {token} suffix".encode())

    assert label == "GitHub token"
    assert token not in label
    heuristics = (ROOT / "src/nhi_blast/data/credential_heuristics.yaml").read_bytes()
    assert checker._leak_label(heuristics) is None


def test_windows_archive_scan_checks_data_entries_and_pyz_modules() -> None:
    checker = _checker()
    token = ("ghp_" + "B" * 36).encode()

    class FakePyz:
        toc: ClassVar[dict[str, None]] = {"mod": None}

        def extract(self, name: str, raw: bool = False) -> bytes:
            assert name == "mod"
            assert raw is True
            return b"const = b'" + token + b"'"

    class FakeArchive:
        toc: ClassVar[dict[str, tuple[int, int, int, int, str]]] = {
            "data.yaml": (0, 0, 0, 0, "x"),
            "PYZ.pyz": (0, 0, 0, 0, "z"),
        }

        def extract(self, name: str) -> bytes:
            return b"clean payload" if name == "data.yaml" else b""

        def open_embedded_archive(self, _name: str) -> FakePyz:
            return FakePyz()

    failures = checker._check_archive_leaks(FakeArchive())

    assert len(failures) == 1
    assert "PYZ.pyz:mod" in failures[0]
    assert "GitHub token" in failures[0]
    assert token.decode() not in failures[0]


def test_windows_checksum_must_match_the_executable(tmp_path: Path) -> None:
    checker = _checker()
    exe = tmp_path / EXE_NAME
    _fake_pe(exe)
    checksum = _write_checksum(exe)

    assert checker.check_windows_metadata(exe, checksum) == []

    checksum.write_text(f"{'0' * 64}  {EXE_NAME}\n", encoding="ascii")
    failures = checker.check_windows_metadata(exe, checksum)
    assert any("sha-256" in failure.lower() for failure in failures), failures

    checksum.write_text("not a checksum\n", encoding="ascii")
    assert checker.check_windows_metadata(exe, checksum)

    checksum.write_text(f"{hashlib.sha256(exe.read_bytes()).hexdigest()}  other.exe\n", "ascii")
    failures = checker.check_windows_metadata(exe, checksum)
    assert any("does not name" in failure for failure in failures), failures


def test_windows_metadata_rejects_non_pe_and_misnamed_files(tmp_path: Path) -> None:
    checker = _checker()
    exe = tmp_path / EXE_NAME
    exe.write_bytes(b"not a Windows executable")
    checksum = _write_checksum(exe)

    failures = checker.check_windows_metadata(exe, checksum)
    assert any("PE" in failure for failure in failures), failures

    renamed = tmp_path / "renamed.exe"
    _fake_pe(renamed)
    renamed_checksum = _write_checksum(renamed)
    failures = checker.check_windows_metadata(renamed, renamed_checksum)
    assert any("name" in failure for failure in failures), failures


def test_windows_only_invocation_does_not_require_wheel_or_sdist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    checker = _checker()
    exe = tmp_path / EXE_NAME
    _fake_pe(exe)
    checksum = _write_checksum(exe)
    empty_dist = tmp_path / "empty-dist"
    empty_dist.mkdir()
    monkeypatch.setattr(checker, "load_archive", lambda _: _CleanArchive(checker))

    result = checker.main(
        [str(empty_dist), "--windows-exe", str(exe), "--windows-checksum", str(checksum)]
    )

    assert result == 0
    assert "windows artifact check passed" in capsys.readouterr().out
