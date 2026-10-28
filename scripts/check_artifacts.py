#!/usr/bin/env python
"""Inspect built distributions for required and forbidden content.

This is a release check, not part of the runtime. It protects two properties:
the wheel contains every data and report asset the installed CLI needs, and
neither artifact ships caches, private research caches, scratch files or
credential material.
"""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path

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
    ".buildcheck/",
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
    args = parser.parse_args(argv)

    wheels = sorted(args.dist.glob("*.whl"))
    sdists = sorted(args.dist.glob("*.tar.gz"))
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
