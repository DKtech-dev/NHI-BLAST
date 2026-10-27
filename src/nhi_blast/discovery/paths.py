"""Path safety helpers (spec 6.3).

Every candidate path is resolved and must stay inside the scan root. Symlinks whose
target leaves the root are skipped with a diagnostic rather than followed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class OutsideRootError(ValueError):
    """A caller-supplied path resolves outside the scan root."""


@dataclass(frozen=True, slots=True)
class PathGuard:
    """Resolves paths relative to a scan root and rejects escapes."""

    root: Path

    @classmethod
    def create(cls, root: str | Path) -> PathGuard:
        resolved = Path(root).resolve()
        if not resolved.is_dir():
            msg = f"scan root is not a directory: {root}"
            raise OutsideRootError(msg)
        return cls(root=resolved)

    def relative(self, candidate: Path) -> str | None:
        """POSIX relative path, or None when the candidate escapes the root."""
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            return None
        try:
            rel = resolved.relative_to(self.root)
        except ValueError:
            return None
        return rel.as_posix()

    def contains(self, candidate: Path) -> bool:
        return self.relative(candidate) is not None

    def require_inside(self, candidate: Path) -> Path:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError) as exc:
            msg = f"path cannot be resolved safely: {candidate}"
            raise OutsideRootError(msg) from exc
        if not resolved.is_relative_to(self.root):
            msg = f"path escapes the scan root: {candidate}"
            raise OutsideRootError(msg)
        return resolved

    def is_symlink_escape(self, candidate: Path) -> bool:
        return is_link_like(candidate) and not self.contains(candidate)


def is_link_like(candidate: Path) -> bool:
    if candidate.is_symlink():
        return True
    is_junction = getattr(candidate, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def posix_join(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part)


def normalise_rel_path(path: str) -> str:
    return path.replace(os.sep, "/")
