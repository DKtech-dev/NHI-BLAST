#!/usr/bin/env python3
"""Run canonical local verification gates for NHI-Blast."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run(label: str, cmd: list[str], *, cwd: Path = REPO_ROOT) -> int:
    print(f"==> {label}: {' '.join(cmd)}", flush=True)
    completed = subprocess.run(cmd, cwd=cwd, check=False)  # noqa: S603 - fixed local gate commands
    if completed.returncode != 0:
        sys.stderr.write(f"FAILED [{completed.returncode}]: {label}\n")
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--fast",
        action="store_true",
        help="Run lint, format, strict types, schema parity, bandit, and non-slow pytest.",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="Run all canonical Python gates including full pytest, slow tests, and coverage.",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Also run the Playwright + axe-core UI suite under tests/ui/.",
    )
    args = parser.parse_args(argv)

    py = sys.executable
    steps: list[tuple[str, list[str], Path]] = [
        ("ruff check", [py, "-m", "ruff", "check", "src", "tests", "scripts"], REPO_ROOT),
        (
            "ruff format",
            [py, "-m", "ruff", "format", "--check", "src", "tests", "scripts"],
            REPO_ROOT,
        ),
        ("mypy --strict", [py, "-m", "mypy", "--strict", "src", "scripts"], REPO_ROOT),
        ("schema parity", [py, "scripts/gen_schema.py", "--check"], REPO_ROOT),
        ("bandit", [py, "-m", "bandit", "-c", "pyproject.toml", "-r", "src"], REPO_ROOT),
    ]

    if args.full or not args.fast:
        steps.extend(
            [
                ("pytest (full)", [py, "-m", "pytest", "-q", "-W", "error"], REPO_ROOT),
                ("coverage gate", [py, "scripts/check_coverage.py"], REPO_ROOT),
            ]
        )
    else:
        steps.append(
            (
                "pytest (fast)",
                [py, "-m", "pytest", "-q", "-W", "error", "-m", "not slow"],
                REPO_ROOT,
            )
        )

    for label, cmd, cwd in steps:
        rc = _run(label, cmd, cwd=cwd)
        if rc != 0:
            return rc

    if args.browser:
        npx = shutil.which("npx")
        if npx is None:
            sys.stderr.write("FAILED: npx not found on PATH for browser gate\n")
            return 127
        ui_dir = REPO_ROOT / "tests" / "ui"
        if not (ui_dir / "node_modules").is_dir():
            sys.stderr.write("FAILED: tests/ui/node_modules is missing (PENDING_BROWSER_RUNTIME)\n")
            return 127
        rc = _run("playwright UI & a11y", [npx, "playwright", "test"], cwd=ui_dir)
        if rc != 0:
            return rc

    print("All requested gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
