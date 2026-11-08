"""Runs the Playwright browser tests for the themed report (plan G4).

The browser stack is dev-time tooling (Node, @playwright/test, axe-core and the browsers); the
report itself makes no network requests. The test is skipped, with the reason, when that stack is
not installed. See tests/ui/README.md.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

UI_DIR = Path(__file__).resolve().parent
_PROBE = (
    "const t=require('@playwright/test');const fs=require('fs');"
    "console.log(['chromium','firefox','webkit'].filter("
    "n=>fs.existsSync(t[n].executablePath())).join(','))"
)


def _node() -> str | None:
    return shutil.which("node")


def _available_engines(node: str) -> list[str]:
    if not (UI_DIR / "node_modules" / "@playwright" / "test").is_dir():
        return []
    probe = subprocess.run(
        [node, "-e", _PROBE], cwd=UI_DIR, capture_output=True, text=True, check=False, timeout=60
    )
    if probe.returncode != 0:
        return []
    return [name for name in probe.stdout.strip().split(",") if name]


def test_report_theme_in_real_browsers() -> None:
    if os.environ.get("NHB_SKIP_UI_TESTS") == "1":
        pytest.skip("NHB_SKIP_UI_TESTS=1")
    node = _node()
    if node is None:
        pytest.skip("node is not installed; see tests/ui/README.md")
    engines = _available_engines(node)
    if "chromium" not in engines:
        pytest.skip("Playwright chromium is not installed; run 'npm install' in tests/ui first")
    npx = shutil.which("npx")
    assert npx is not None
    command = [npx, "playwright", "test", *(f"--project={name}" for name in engines)]
    env = {**os.environ, "PYTHONUTF8": "1", "FORCE_COLOR": "0"}
    result = subprocess.run(
        command, cwd=UI_DIR, capture_output=True, text=True, check=False, timeout=900, env=env
    )
    assert result.returncode == 0, result.stdout[-6000:] + result.stderr[-2000:]
