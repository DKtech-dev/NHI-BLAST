"""Regression checks for the distribution artifact inspector."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.security

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_artifacts.py"


def _checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_artifacts", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
