"""Discovery: safe walking, classification and input loading (spec 6.1-6.3).

The walker never follows symlinks, prunes vendor and build directories and enforces
the file/size limits. Parsing happens elsewhere; this module only classifies files
and reads bytes once.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from nhi_blast.core.diagnostics import Diagnostic, error, warning
from nhi_blast.core.ids import file_sha256
from nhi_blast.core.limits import Limits
from nhi_blast.discovery.paths import PathGuard, is_link_like

PRUNED_DIRECTORIES = frozenset(
    {
        ".git",
        "node_modules",
        ".terraform",
        "vendor",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".agents",
        "nhi-blast-out",
    }
)

_TF_JSON_MARKERS = (b'"format_version"',)
_TF_JSON_VALUE_MARKERS = (b'"planned_values"', b'"values"', b'"resource_changes"')
_JSON_SNIFF_BYTES = 65_536


class FileKind(StrEnum):
    WORKFLOW = "workflow"
    COMPOSITE_ACTION = "composite_action"
    TF_JSON = "tf_json"
    TF_HCL = "tf_hcl"
    IAM_JSON = "iam_json"
    CONFIG = "config"
    GIT_CONFIG = "git_config"


@dataclass(frozen=True, slots=True)
class DiscoveredFile:
    path: Path
    rel: str
    kind: FileKind


@dataclass(frozen=True, slots=True)
class LoadedText:
    rel: str
    kind: FileKind
    text: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Discovery:
    files: tuple[DiscoveredFile, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    visited_files: int = 0


@dataclass(slots=True)
class InputLoader:
    """Reads discovered files once, enforcing per-kind size limits."""

    guard: PathGuard
    limits: Limits
    loaded: dict[str, LoadedText] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def _size_limit(self, kind: FileKind) -> int:
        if kind is FileKind.TF_JSON:
            return self.limits.max_tf_json_bytes
        return self.limits.max_yaml_policy_file_bytes

    def load(self, path: Path, kind: FileKind) -> LoadedText | None:
        rel = self.guard.relative(path)
        if rel is None:
            self.diagnostics.append(
                warning(
                    "D-IO-OUTSIDE-ROOT",
                    f"skipped path outside the scan root: {path.name}",
                    file=str(path),
                )
            )
            return None
        if rel in self.loaded:
            return self.loaded[rel]
        try:
            resolved = self.guard.require_inside(path)
        except (OSError, ValueError):
            self.diagnostics.append(
                warning(
                    "D-IO-SYMLINK",
                    "skipped symlink or path that resolves outside the scan root",
                    file=rel,
                )
            )
            return None
        try:
            data = resolved.read_bytes()
        except OSError as exc:
            self.diagnostics.append(
                error("D-IO-UNREADABLE", f"cannot read file: {exc.strerror or exc}", file=rel)
            )
            return None
        limit = self._size_limit(kind)
        if len(data) > limit:
            self.diagnostics.append(
                error(
                    "D-IO-LIMIT",
                    f"file is {len(data)} bytes, above the {limit}-byte limit; skipped",
                    file=rel,
                )
            )
            return None
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            self.diagnostics.append(
                error(
                    "D-IO-ENCODING",
                    f"file is not valid UTF-8 ({exc.reason} at byte {exc.start}); skipped",
                    file=rel,
                )
            )
            return None
        loaded = LoadedText(rel=rel, kind=kind, text=text, sha256=file_sha256(data))
        self.loaded[rel] = loaded
        return loaded

    def loaded_inputs(self) -> tuple[LoadedText, ...]:
        return tuple(self.loaded[rel] for rel in sorted(self.loaded))


def _is_workflow(rel_parts: tuple[str, ...]) -> bool:
    return (
        len(rel_parts) == 3
        and rel_parts[0] == ".github"
        and rel_parts[1] == "workflows"
        and rel_parts[2].endswith((".yml", ".yaml"))
    )


def _peek_is_tf_json(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(_JSON_SNIFF_BYTES)
    except OSError:
        return False
    if not any(marker in head for marker in _TF_JSON_MARKERS):
        return False
    return any(marker in head for marker in _TF_JSON_VALUE_MARKERS)


def classify_path(path: Path, rel: str) -> FileKind | None:
    parts = tuple(rel.split("/"))
    name = parts[-1]
    if _is_workflow(parts):
        return FileKind.WORKFLOW
    if name in {"action.yml", "action.yaml"} and not _is_workflow(parts):
        return FileKind.COMPOSITE_ACTION
    if name.endswith(".tf"):
        return FileKind.TF_HCL
    if name.endswith(".tf.json"):
        return FileKind.TF_HCL
    if name.endswith(".json") and _peek_is_tf_json(path):
        return FileKind.TF_JSON
    return None


def _walk(
    root: Path, limits: Limits, guard: PathGuard
) -> tuple[tuple[tuple[Path, str], ...], bool, tuple[str, ...]]:
    found: list[tuple[Path, str]] = []
    escaped: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        kept: list[str] = []
        for name in sorted(dirnames):
            if name in PRUNED_DIRECTORIES:
                continue
            child = current / name
            if is_link_like(child):
                if not guard.contains(child):
                    escaped.append(child.relative_to(root).as_posix())
                continue
            kept.append(name)
        dirnames[:] = kept
        for filename in sorted(filenames):
            if len(found) >= limits.max_files:
                return tuple(found), True, tuple(escaped)
            candidate = current / filename
            rel = candidate.relative_to(root).as_posix()
            found.append((candidate, rel))
    return tuple(found), False, tuple(escaped)


def discover(
    root: Path,
    *,
    limits: Limits,
    extra_tf_json: tuple[Path, ...] = (),
    extra_iam_json: tuple[Path, ...] = (),
    config_path: Path | None = None,
    hcl_enabled: bool = True,
) -> Discovery:
    guard = PathGuard(root=root.resolve())
    diagnostics: list[Diagnostic] = []
    visited, truncated, escaped_dirs = _walk(root, limits, guard)
    for rel in escaped_dirs:
        diagnostics.append(
            warning("D-IO-SYMLINK", "skipped directory link escaping the scan root", file=rel)
        )
    if truncated:
        diagnostics.append(
            error(
                "D-IO-LIMIT",
                f"file scan stopped at the {limits.max_files}-file limit; results are partial",
            )
        )

    forced: dict[str, FileKind] = {}
    forced_paths: dict[str, Path] = {}

    def force(path: Path, kind: FileKind, flag: str) -> None:
        try:
            resolved = guard.require_inside(path)
        except (OSError, ValueError) as exc:
            msg = f"{flag} path must be inside the scan root: {path} ({exc})"
            raise ValueError(msg) from exc
        rel = resolved.relative_to(guard.root).as_posix()
        previous = forced.get(rel)
        if previous is not None and previous is not kind:
            msg = (
                f"{rel} was supplied with conflicting input kinds ({previous.value}, {kind.value})"
            )
            raise ValueError(msg)
        forced[rel] = kind
        forced_paths[rel] = resolved

    for path in extra_tf_json:
        force(path, FileKind.TF_JSON, "--tf-json")
    for path in extra_iam_json:
        force(path, FileKind.IAM_JSON, "--iam-json")
    if config_path is not None:
        force(config_path, FileKind.CONFIG, "--config")

    visited_list = list(visited)
    visited_rels = {rel for _, rel in visited_list}
    for rel in sorted(forced):
        if rel not in visited_rels:
            visited_list.append((forced_paths[rel], rel))

    files: list[DiscoveredFile] = []
    for candidate, rel in visited_list:
        kind = forced.get(rel)
        if kind is None:
            if not guard.contains(candidate):
                code = "D-IO-SYMLINK" if is_link_like(candidate) else "D-IO-OUTSIDE-ROOT"
                diagnostics.append(
                    warning(code, "skipped path that resolves outside the scan root", file=rel)
                )
                continue
            kind = classify_path(candidate, rel)
        if kind is None:
            continue
        if kind is FileKind.TF_HCL and not hcl_enabled:
            continue
        files.append(DiscoveredFile(path=candidate, rel=rel, kind=kind))
    return Discovery(
        files=tuple(sorted(files, key=lambda f: (f.kind.value, f.rel))),
        diagnostics=tuple(diagnostics),
        visited_files=len(visited),
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
