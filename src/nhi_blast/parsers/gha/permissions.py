"""Workflow and job permissions parsing (spec 7.4)."""

from __future__ import annotations

from nhi_blast.core.data import permission_scopes
from nhi_blast.core.diagnostics import Diagnostic, warning
from nhi_blast.core.models import PermLevel
from nhi_blast.parsers.gha.facts import Perms
from nhi_blast.parsers.yaml_marked import Marked

_LEVELS = {"read": PermLevel.READ, "write": PermLevel.WRITE, "none": PermLevel.NONE}


def _has_expression(text: str) -> bool:
    return ("${{") in text


def _expand_all(level: PermLevel, *, read_all: bool, write_all: bool, line: int) -> Perms:
    scopes = permission_scopes().scopes
    return Perms(
        levels=dict.fromkeys(scopes, level),
        all_read=read_all,
        all_write=write_all,
        line=line,
    )


def parse_permissions(
    node: Marked | None, *, rel_path: str, fallback_line: int = 0
) -> tuple[Perms | None, tuple[Diagnostic, ...]]:
    if node is None:
        return None, ()
    line = node.line or fallback_line
    diagnostics: list[Diagnostic] = []
    if isinstance(node.value, str):
        text = node.value.strip()
        if _has_expression(text):
            return Perms(has_expression=True, line=line, raw={"": text}), (
                warning(
                    "D-EXPR-VALUE",
                    "permissions value is an expression; effective permissions are unknown",
                    file=rel_path,
                    line=line,
                ),
            )
        keyword = text.lower()
        if keyword == "read-all":
            return _expand_all(PermLevel.READ, read_all=True, write_all=False, line=line), ()
        if keyword == "write-all":
            return _expand_all(PermLevel.WRITE, read_all=False, write_all=True, line=line), ()
        diagnostics.append(
            warning(
                "D-GHA-PERM-VALUE",
                "unrecognised permissions value; treated as unknown",
                file=rel_path,
                line=line,
            )
        )
        return Perms(all_read=False, all_write=False, has_expression=True, line=line), tuple(
            diagnostics
        )
    if not node.is_mapping():
        diagnostics.append(
            warning(
                "D-GHA-PERM-SHAPE",
                "permissions must be a mapping or read-all/write-all; treated as unknown",
                file=rel_path,
                line=line,
            )
        )
        return Perms(has_expression=True, line=line), tuple(diagnostics)
    raw_mapping = node.as_mapping()
    if not raw_mapping:
        return Perms(empty=True, line=line), ()
    levels: dict[str, PermLevel] = {}
    raw: dict[str, str] = {}
    has_expression = False
    known = set(permission_scopes().scopes)
    for scope, value_node in raw_mapping.items():
        scope_name = scope.strip().lower()
        value = value_node.value
        if scope_name not in known:
            diagnostics.append(
                warning(
                    "D-GHA-PERM-SCOPE",
                    "unknown permission scope; ignored",
                    file=rel_path,
                    line=value_node.line,
                )
            )
            continue
        if isinstance(value, str) and _has_expression(value):
            levels[scope_name] = PermLevel.UNKNOWN
            has_expression = True
            raw[scope_name] = value
            diagnostics.append(
                warning(
                    "D-EXPR-VALUE",
                    f"permission {scope_name} is set by an expression; treated as unknown",
                    file=rel_path,
                    line=value_node.line,
                )
            )
            continue
        level = _LEVELS.get(str(value).strip().lower())
        if level is None:
            diagnostics.append(
                warning(
                    "D-GHA-PERM-VALUE",
                    f"unknown level for permission {scope_name}",
                    file=rel_path,
                    line=value_node.line,
                )
            )
            levels[scope_name] = PermLevel.UNKNOWN
            has_expression = True
            continue
        levels[scope_name] = level
        raw[scope_name] = level.value
    return Perms(levels=levels, has_expression=has_expression, raw=raw, line=line), tuple(
        diagnostics
    )
