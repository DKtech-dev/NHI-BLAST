"""Locate the CLI console script installed into the running interpreter's environment.

The console script is not always beside ``python.exe``: virtual environments place
both in ``Scripts``/``bin``, while python.org-layout interpreters (including the
GitHub-hosted toolcache) keep ``python.exe`` at the prefix root and install scripts
into the configured ``Scripts`` directory.
"""

from __future__ import annotations

import os
import shutil
import sys
import sysconfig
from collections.abc import Callable
from pathlib import Path


class EntrypointNotFoundError(RuntimeError):
    """This environment has no installed CLI entrypoint."""


def resolve_cli_entrypoint(
    *,
    executable: Path | None = None,
    scripts_directory: Path | None = None,
    platform: str | None = None,
    which: Callable[[str], str | None] | None = None,
) -> Path:
    executable = Path(sys.executable) if executable is None else Path(executable)
    platform = os.name if platform is None else platform
    locate = shutil.which if which is None else which
    if scripts_directory is None:
        configured = sysconfig.get_path("scripts")
        scripts_directory = Path(configured) if configured else None
    name = "nhi-blast.exe" if platform == "nt" else "nhi-blast"

    candidates: list[Path] = []
    if scripts_directory is not None:
        candidates.append(scripts_directory / name)
    located = locate("nhi-blast")
    if located:
        candidates.append(Path(located))
    candidates.append(executable.parent / name)

    searched: list[Path] = []
    for candidate in candidates:
        if candidate in searched:
            continue
        searched.append(candidate)
        if candidate.is_file():
            return candidate.absolute()
    listing = ", ".join(str(candidate) for candidate in searched)
    message = (
        f"installed CLI entrypoint {name!r} not found for interpreter {executable}; "
        f"searched: {listing}; install the project into this environment with "
        'python -m pip install -e ".[dev,rich,hcl]"'
    )
    raise EntrypointNotFoundError(message)
