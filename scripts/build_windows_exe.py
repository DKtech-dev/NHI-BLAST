#!/usr/bin/env python
"""Build the standalone Windows executable with PyInstaller.

The executable is deliberately one file and console-only: it embeds the Python
runtime, the optional HCL parser and rich console support, and every runtime data
and report asset. Build it from a clean environment; the checked-in lock pins the
build toolchain. The project licence and third-party notices are embedded at the
bundle root so the distributed binary carries its own notices.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import posixpath
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE_NAME = "nhi-blast-windows-x64"
ENTRY_SCRIPT = ROOT / "scripts" / "windows_entry.py"
DATA_SOURCE = ROOT / "src" / "nhi_blast" / "data"
ASSETS_SOURCE = ROOT / "src" / "nhi_blast" / "report" / "assets"
DEFAULT_DIST = ROOT / "dist" / "windows"
DEFAULT_WORK = ROOT / "build" / "windows"
LICENCE_FILES = ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md")
_REQUIRED_BUILD_MODULES = ("PyInstaller", "hcl2", "rich")
_SKIPPED_SUFFIXES = frozenset({".py", ".pyc", ".pyo"})


def _resource_root(source: Path, destination: str) -> list[tuple[Path, str]]:
    pairs: list[tuple[Path, str]] = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix in _SKIPPED_SUFFIXES:
            continue
        relative = path.relative_to(source).as_posix()
        pairs.append((path, f"{destination}/{relative}"))
    return pairs


def resource_pairs() -> list[tuple[Path, str]]:
    """Every non-module runtime file with its destination inside the bundle."""
    return [
        *_resource_root(DATA_SOURCE, "nhi_blast/data"),
        *_resource_root(ASSETS_SOURCE, "nhi_blast/report/assets"),
        *((ROOT / name, name) for name in LICENCE_FILES),
    ]


def bundled_resource_names() -> frozenset[str]:
    return frozenset(destination for _, destination in resource_pairs())


def pyinstaller_command(*, dist_dir: Path, work_dir: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--noupx",
        "--log-level",
        "WARN",
        "--name",
        EXE_NAME,
        "--paths",
        str(ROOT / "src"),
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(work_dir),
        "--hidden-import",
        "hcl2",
        "--hidden-import",
        "rich",
        "--collect-data",
        "hcl2",
        "--collect-submodules",
        "hcl2",
        "--collect-submodules",
        "lark",
        "--collect-submodules",
        "rich",
        "--exclude-module",
        "coverage",
        "--exclude-module",
        "hypothesis",
        "--exclude-module",
        "jsonschema",
        "--exclude-module",
        "mypy",
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "ruff",
    ]
    for source, destination in resource_pairs():
        # PyInstaller copies a file into the named directory; passing the full
        # file destination would create a redundant <name>/<name> nesting.
        directory = posixpath.dirname(destination) or "."
        command.extend(["--add-data", f"{source}{os.pathsep}{directory}"])
    command.append(str(ENTRY_SCRIPT))
    return command


def _check_environment() -> None:
    missing = [
        module for module in _REQUIRED_BUILD_MODULES if importlib.util.find_spec(module) is None
    ]
    if missing:
        names = ", ".join(missing)
        message = (
            f"build environment is missing {names}; install the project with "
            '".[rich,hcl]" and requirements-windows-build.lock, then retry'
        )
        raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksum(exe: Path) -> Path:
    path = exe.with_name(exe.name + ".sha256")
    path.write_text(f"{sha256(exe)}  {exe.name}\n", encoding="ascii", newline="\n")
    return path


def build(*, dist_dir: Path = DEFAULT_DIST, work_dir: Path = DEFAULT_WORK) -> Path:
    if os.name != "nt":
        message = "the Windows executable can only be built on Windows"
        raise SystemExit(message)
    _check_environment()
    dist_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603 - fixed interpreter and generated argument list
        pyinstaller_command(dist_dir=dist_dir, work_dir=work_dir),
        cwd=ROOT,
        check=True,
    )
    exe = dist_dir / f"{EXE_NAME}.exe"
    if not exe.is_file():
        message = f"PyInstaller did not produce {exe}"
        raise SystemExit(message)
    checksum = write_checksum(exe)
    print(f"built {exe}")
    print(f"sha256 {sha256(exe)}  {exe.name}")
    print(f"checksum {checksum}")
    return exe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    args = parser.parse_args(argv)
    build(dist_dir=args.dist.resolve(), work_dir=args.work.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
