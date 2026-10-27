"""Repository identity resolution (spec 6.4).

Precedence: --repo-slug, then nhi-blast.toml, then .git/config. If nothing resolves,
subjects use the symbolic repo */* and every OIDC result is capped at ASSUMED.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from nhi_blast.core.models import SubFormat

_ORIGIN_URL = re.compile(r"^\s*url\s*=\s*(?P<url>\S+)\s*$")
_OWNER_REPO = re.compile(r"github\.com[:/](?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$")
_MAX_GIT_CONFIG_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class RepoIdentity:
    slug: str | None
    source: str
    default_branch: str
    sub_format: SubFormat

    @property
    def symbolic(self) -> bool:
        return self.slug is None

    def owner(self) -> str | None:
        if self.slug is None:
            return None
        return self.slug.split("/", 1)[0]

    def name(self) -> str | None:
        if self.slug is None:
            return None
        parts = self.slug.split("/", 1)
        return parts[1] if len(parts) == 2 else None


def parse_git_config_origin(text: str) -> str | None:
    """Extract owner/repo from an origin URL without running git."""
    match = _OWNER_REPO.search(text)
    if match is None:
        return None
    return f"{match.group('owner')}/{match.group('repo')}"


def read_git_origin_slug(root: Path) -> str | None:
    config = root / ".git" / "config"
    try:
        resolved = config.resolve(strict=True)
        root_resolved = root.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root_resolved) or not resolved.is_file():
        return None
    try:
        with resolved.open("rb") as handle:
            data = handle.read(_MAX_GIT_CONFIG_BYTES + 1)
    except OSError:
        return None
    if len(data) > _MAX_GIT_CONFIG_BYTES:
        return None
    text = data.decode("utf-8", errors="replace")
    section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            continue
        if section == 'remote "origin"':
            match = _ORIGIN_URL.match(line)
            if match is not None:
                return parse_git_config_origin(match.group("url"))
    return None


def resolve_identity(
    *,
    root: Path,
    cli_repo_slug: str | None,
    cli_default_branch: str | None,
    config_repo_slug: str | None,
    config_default_branch: str,
) -> RepoIdentity:
    if cli_repo_slug:
        slug, source = cli_repo_slug, "--repo-slug"
    elif config_repo_slug:
        slug, source = config_repo_slug, "nhi-blast.toml"
    else:
        git_slug = read_git_origin_slug(root)
        if git_slug is not None:
            slug, source = git_slug, ".git/config"
        else:
            slug, source = None, "unresolved"
    default_branch = cli_default_branch or config_default_branch or "main"
    return RepoIdentity(
        slug=slug,
        source=source,
        default_branch=default_branch,
        sub_format=SubFormat.UNKNOWN,
    )
