"""Shared pytest fixtures for the NHI-Blast test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
GIT_CONFIG = """[core]
\trepositoryformatversion = 0
\tfilemode = true
\tbare = false
[remote "origin"]
\turl = https://github.com/{slug}.git
\tfetch = +refs/heads/*:refs/remotes/origin/*
"""
GIT_SLUG_OVERRIDES = {"fx15-scale-smoke": "acme/scale"}


@pytest.fixture(scope="session", autouse=True)
def fixture_git_identity() -> None:
    # Git cannot track nested .git directories, so recreate each fixture's
    # identity from reviewed data before any test scans it.
    for root in sorted(FIXTURES.glob("fx*")):
        slug = GIT_SLUG_OVERRIDES.get(root.name, "acme/shop")
        config = root / ".git" / "config"
        config.parent.mkdir(exist_ok=True)
        config.write_bytes(GIT_CONFIG.format(slug=slug).encode("utf-8"))


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES
