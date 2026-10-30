#!/usr/bin/env python
"""Inspect built distributions for required and forbidden content.

This is a release check, not part of the runtime. It protects two properties:
the wheel contains every data and report asset the installed CLI needs, and
neither artifact ships caches, private research caches, scratch files or
credential material.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import re
import sys
import tarfile
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath
from typing import Any

REQUIRED_WHEEL_DATA = frozenset(
    {
        "nhi_blast/data/assumptions.yaml",
        "nhi_blast/data/aws_github_condition_keys.yaml",
        "nhi_blast/data/credential_heuristics.yaml",
        "nhi_blast/data/permission_scopes.yaml",
        "nhi_blast/data/rotation_hints.yaml",
        "nhi_blast/data/rules.yaml",
        "nhi_blast/data/sinks_catalog.yaml",
        "nhi_blast/data/trigger_profiles.yaml",
    }
)
REQUIRED_WHEEL_ASSETS = frozenset(
    {
        "nhi_blast/report/assets/MANIFEST.json",
        "nhi_blast/report/assets/fonts/OFL.txt",
        "nhi_blast/report/assets/fonts/OFL-InstrumentSerif.txt",
        "nhi_blast/report/assets/fonts/geist-latin.woff2",
        "nhi_blast/report/assets/fonts/geist-mono-latin.woff2",
        "nhi_blast/report/assets/fonts/instrument-serif-latin.woff2",
        "nhi_blast/report/assets/vendor/MIT-Motion.txt",
        "nhi_blast/report/assets/vendor/motion-14.7.1.min.js",
    }
)
WINDOWS_EXE_NAME = "nhi-blast-windows-x64.exe"
WINDOWS_REQUIRED_RESOURCES = REQUIRED_WHEEL_DATA | REQUIRED_WHEEL_ASSETS
# PyInstaller stores Python modules as bytecode, so the wheel rules that reject
# .pyc caches cannot apply to its archive. These are distribution paths that
# must never appear in the standalone executable.
WINDOWS_FORBIDDEN_PARTS = (
    ".venv/",
    ".git/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".hypothesis/",
    "docs/research/_cache/",
    "tests/fixtures/_validate_tmp.py",
    "nhi-blast-out/",
    ".taste-skill/",
    ".agents/",
    ".claude/",
    ".buildcheck/",
    "node_modules/",
    "docs/",
    "tests/",
)
WINDOWS_CHECKSUM = re.compile(r"^([0-9a-f]{64}) [ *](.+)$")
# High-signal value formats only. The tool's own detection patterns are regex
# text and do not match these; a match means a credential value was bundled.
WINDOWS_SECRET_PATTERNS = (
    ("private key", re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("GitHub token", re.compile(rb"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("GitHub fine-grained token", re.compile(rb"github_pat_[A-Za-z0-9_]{22,}")),
    ("Slack token", re.compile(rb"xox[abprs]-[A-Za-z0-9-]{10,}")),
    (
        "Slack webhook",
        re.compile(rb"https://hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+"),
    ),
)
REQUIRED_SDIST = frozenset(
    {
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "NOTICE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "requirements.lock",
        "requirements-dev.lock",
        "requirements-windows-build.lock",
    }
)
# An explicit allowlist is the only reliable guard against a build accidentally
# sweeping untracked scratch trees into the sdist.
ALLOWED_SDIST_ROOTS = frozenset(
    {
        ".gitignore",
        "PKG-INFO",
        "assets",
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "NOTICE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CHANGELOG.md",
        "requirements.lock",
        "requirements-dev.lock",
        "requirements-windows-build.lock",
        "docs",
        "scripts",
        "src",
        "tests",
    }
)
FORBIDDEN_PARTS = (
    "__pycache__",
    ".pyc",
    ".venv/",
    ".git/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".hypothesis/",
    "docs/research/_cache/",
    "tests/fixtures/_validate_tmp.py",
    "nhi-blast-out/",
    ".taste-skill/",
    ".agents/",
    ".claude/",
    ".buildcheck/",
)
# Local-only working files that must never be distributed. The sdist excludes
# them explicitly, but the guard does not rely on build configuration alone.
LOCAL_ONLY_PATHS = frozenset(
    {
        "docs/engineering-checkpoint.md",
        "HANDOVER.md",
        "_spec_extract.txt",
        "_blueprint_extract.txt",
        "skills-lock.json",
    }
)


def _normalise(name: str) -> str:
    normalised = name.replace("\\", "/")
    while normalised.startswith("./"):
        normalised = normalised[2:]
    return normalised


def _forbidden(name: str) -> str | None:
    normalised = _normalise(name)
    for marker in FORBIDDEN_PARTS:
        if marker in normalised:
            return marker
    return None


def _local_only(name: str) -> str | None:
    normalised = _normalise(name)
    return normalised if normalised in LOCAL_ONLY_PATHS else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_pe_header(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            if handle.read(2) != b"MZ":
                return False
            handle.seek(0x3C)
            offset = handle.read(4)
            if len(offset) != 4:
                return False
            handle.seek(int.from_bytes(offset, "little"))
            return handle.read(4) == b"PE\0\0"
    except OSError:
        return False


def check_windows_metadata(exe: Path, checksum_path: Path | None = None) -> list[str]:
    failures: list[str] = []
    if exe.name != WINDOWS_EXE_NAME:
        failures.append(f"windows: unexpected executable name {exe.name!r}")
    if not exe.is_file():
        failures.append(f"windows: missing executable {exe}")
        return failures
    if not _has_pe_header(exe):
        failures.append(f"windows: {exe.name} is not a PE executable")
    checksum_path = exe.with_name(exe.name + ".sha256") if checksum_path is None else checksum_path
    if not checksum_path.is_file():
        failures.append(f"windows: missing checksum {checksum_path}")
        return failures
    try:
        lines = checksum_path.read_text(encoding="ascii", errors="replace").splitlines()
    except OSError as exc:
        failures.append(f"windows: cannot read checksum {checksum_path}: {exc}")
        return failures
    if len(lines) != 1:
        failures.append("windows: checksum file must contain exactly one line")
        return failures
    match = WINDOWS_CHECKSUM.fullmatch(lines[0].strip())
    if match is None:
        failures.append("windows: checksum file is not a SHA-256 record")
        return failures
    digest, name = match.groups()
    if name != exe.name:
        failures.append(f"windows: checksum does not name {exe.name!r}")
    if digest != _sha256(exe):
        failures.append("windows: SHA-256 checksum does not match the executable")
    return failures


def _unsafe_windows_path(name: str) -> bool:
    path = PurePosixPath(name)
    return not name or ":" in name or path.is_absolute() or ".." in path.parts


def _credential_label(payload: bytes) -> str | None:
    for label, pattern in WINDOWS_SECRET_PATTERNS:
        if pattern.search(payload):
            return label
    return None


def _archive_payloads(reader: Any) -> Iterator[tuple[str, bytes]]:
    for name, toc_entry in reader.toc.items():
        if toc_entry[-1] == "z":
            embedded = reader.open_embedded_archive(name)
            for module in embedded.toc:
                payload = embedded.extract(module, raw=True)
                if payload:
                    yield f"{name}:{module}", payload
        else:
            yield name, reader.extract(name)


def _check_archive_secrets(reader: Any) -> list[str]:
    failures: list[str] = []
    for name, payload in _archive_payloads(reader):
        label = _credential_label(payload)
        if label is not None:
            failures.append(f"windows: {name!r} contains credential material ({label})")
    return failures


def check_windows_entries(entries: Iterable[str]) -> list[str]:
    names = {_normalise(name) for name in entries}
    failures: list[str] = []
    for name in sorted(names):
        if _unsafe_windows_path(name):
            failures.append(f"windows: unsafe archive path {name!r}")
            continue
        local = _local_only(name)
        if local is not None:
            failures.append(f"windows: local-only file {name!r} must not be distributed")
            continue
        marker = next((item for item in WINDOWS_FORBIDDEN_PARTS if item in name), None)
        if marker is not None:
            failures.append(f"windows: forbidden content {name!r} matched {marker!r}")
    missing = sorted(WINDOWS_REQUIRED_RESOURCES - names)
    failures.extend(f"windows: missing {name}" for name in missing)
    if not names:
        failures.append("windows: executable archive is empty")
    return failures


def load_archive(exe: Path) -> Any:
    try:
        readers = importlib.import_module("PyInstaller.archive.readers")
    except ImportError as exc:
        msg = "PyInstaller is required to inspect the executable archive"
        raise RuntimeError(msg) from exc
    return readers.CArchiveReader(str(exe))


def check_windows_executable(exe: Path, checksum_path: Path | None = None) -> list[str]:
    failures = check_windows_metadata(exe, checksum_path)
    try:
        reader = load_archive(exe)
    except Exception as exc:  # archive inspection boundary: PyInstaller can raise many types
        failures.append(f"windows: cannot inspect executable archive: {type(exc).__name__}: {exc}")
        return failures
    failures.extend(check_windows_entries(str(name) for name in reader.toc))
    try:
        failures.extend(_check_archive_secrets(reader))
    except Exception as exc:  # payload boundary: decompression can raise many types
        failures.append(f"windows: cannot scan executable payloads: {type(exc).__name__}: {exc}")
    return failures


def _wheel_entries(wheel: Path) -> tuple[dict[str, int], str]:
    with zipfile.ZipFile(wheel) as archive:
        entries = {_normalise(info.filename): info.file_size for info in archive.infolist()}
        metadata_name = next(
            (name for name in entries if name.endswith(".dist-info/METADATA")), None
        )
        metadata = archive.read(metadata_name).decode("utf-8") if metadata_name else ""
    return entries, metadata


def _unexpected_sdist_roots(entries: dict[str, int]) -> list[str]:
    roots = {name.split("/", 1)[0] for name in entries}
    return sorted(roots - ALLOWED_SDIST_ROOTS)


def _sdist_entries(sdist: Path) -> dict[str, int]:
    with tarfile.open(sdist) as archive:
        entries: dict[str, int] = {}
        for member in archive.getmembers():
            if not member.isfile():
                continue
            parts = _normalise(member.name).split("/", 1)
            relative = parts[1] if len(parts) == 2 else parts[0]
            entries[relative] = member.size
    return entries


def _check_common(label: str, entries: dict[str, int]) -> list[str]:
    failures: list[str] = []
    for name in entries:
        marker = _forbidden(name)
        if marker is not None:
            failures.append(f"{label}: forbidden content {name!r} matched {marker!r}")
        local = _local_only(name)
        if local is not None:
            failures.append(f"{label}: local-only file {name!r} must not be distributed")
    if not entries:
        failures.append(f"{label}: artifact is empty")
    return failures


def _requirement_names(metadata: str, *, runtime_only: bool = False) -> set[str]:
    names: set[str] = set()
    for line in metadata.splitlines():
        if not line.startswith("Requires-Dist:"):
            continue
        spec = line.removeprefix("Requires-Dist:").strip()
        requirement, separator, marker = spec.partition(";")
        if runtime_only and separator and "extra" in marker:
            continue
        names.add(re.split(r"[<>=!~\[; ]", requirement.strip(), maxsplit=1)[0].lower())
    return names


def check_wheel(wheel: Path) -> list[str]:
    entries, metadata = _wheel_entries(wheel)
    failures = _check_common("wheel", entries)
    missing = sorted((REQUIRED_WHEEL_DATA | REQUIRED_WHEEL_ASSETS) - entries.keys())
    failures.extend(f"wheel: missing {name}" for name in missing)
    if "Requires-Python: >=3.12" not in metadata:
        failures.append("wheel: metadata does not declare Python >=3.12")
    requirements = _requirement_names(metadata, runtime_only=True)
    for requirement in ("pydantic", "pyyaml", "networkx", "typer"):
        if requirement not in requirements:
            failures.append(f"wheel: metadata is missing runtime dependency {requirement}")
    if "pytest" in requirements:
        failures.append("wheel: test tooling leaked into runtime requirements")
    print(f"wheel: {len(entries)} files, {sum(entries.values())} bytes, assets present")
    return failures


def check_sdist(sdist: Path) -> list[str]:
    entries = _sdist_entries(sdist)
    failures = _check_common("sdist", entries)
    missing = sorted(REQUIRED_SDIST - entries.keys())
    failures.extend(f"sdist: missing {name}" for name in missing)
    failures.extend(
        f"sdist: unexpected top-level entry {root!r}" for root in _unexpected_sdist_roots(entries)
    )
    for required in ("src/nhi_blast/__init__.py", "docs/SPEC.md", "tests/test_security.py"):
        if required not in entries:
            failures.append(f"sdist: missing {required}")
    print(f"sdist: {len(entries)} files, {sum(entries.values())} bytes")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", nargs="?", type=Path, default=Path("dist"))
    parser.add_argument("--windows-exe", type=Path)
    parser.add_argument("--windows-checksum", type=Path)
    args = parser.parse_args(argv)
    if args.windows_checksum is not None and args.windows_exe is None:
        parser.error("--windows-checksum requires --windows-exe")

    wheels = sorted(args.dist.glob("*.whl"))
    sdists = sorted(args.dist.glob("*.tar.gz"))
    if args.windows_exe is not None:
        failures = check_windows_executable(args.windows_exe, args.windows_checksum)
        if failures:
            for failure in failures:
                sys.stderr.write(f"artifact check failed: {failure}\n")
            return 1
        print(f"windows: {args.windows_exe.name} and required resources present")
        if not wheels and not sdists:
            print("windows artifact check passed")
            return 0

    if len(wheels) != 1 or len(sdists) != 1:
        sys.stderr.write(
            f"expected exactly one wheel and one sdist in {args.dist}, "
            f"found {len(wheels)} and {len(sdists)}\n"
        )
        return 1

    failures = check_wheel(wheels[0]) + check_sdist(sdists[0])
    for failure in failures:
        sys.stderr.write(f"artifact check failed: {failure}\n")
    if failures:
        return 1
    print("artifact check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
