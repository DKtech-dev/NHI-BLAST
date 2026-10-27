"""Effective permissions resolution (spec 7.4).

A job permissions block replaces the workflow block. With no block at all,
id-token is not writable (A-DEFAULT-NO-IDTOKEN) and every other scope is UNKNOWN.
For a reusable workflow call the callee's effective permissions are bounded by the
caller job's grant.
"""

from __future__ import annotations

from dataclasses import dataclass

from nhi_blast.core.data import permission_scopes
from nhi_blast.core.diagnostics import Diagnostic
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.models import PermLevel
from nhi_blast.parsers.gha.facts import JobFact, Perms, WorkflowFact

_LEVEL_RANK = {PermLevel.NONE: 0, PermLevel.READ: 1, PermLevel.WRITE: 2}


@dataclass(frozen=True, slots=True)
class EffectivePerms:
    levels: dict[str, PermLevel]
    id_token_write: bool | None
    cls: EvidenceClass
    evidence: tuple[Evidence, ...]
    notes: tuple[str, ...] = ()
    default_block: bool = False
    diagnostics: tuple[Diagnostic, ...] = ()


def _expand(perms: Perms, scopes: tuple[str, ...]) -> dict[str, PermLevel]:
    if perms.all_read:
        return dict.fromkeys(scopes, PermLevel.READ)
    if perms.all_write:
        return dict.fromkeys(scopes, PermLevel.WRITE)
    if perms.empty:
        return dict.fromkeys(scopes, PermLevel.NONE)
    if perms.has_expression and not perms.levels:
        return dict.fromkeys(scopes, PermLevel.UNKNOWN)
    levels = dict.fromkeys(scopes, PermLevel.NONE)
    for scope, level in perms.levels.items():
        if scope in levels:
            levels[scope] = level
    return levels


def _default_levels(scopes: tuple[str, ...]) -> dict[str, PermLevel]:
    levels = dict.fromkeys(scopes, PermLevel.UNKNOWN)
    levels["id-token"] = PermLevel.NONE
    return levels


def id_token_flag(levels: dict[str, PermLevel]) -> bool | None:
    level = levels.get("id-token", PermLevel.NONE)
    if level is PermLevel.WRITE:
        return True
    if level is PermLevel.NONE or level is PermLevel.READ:
        return False
    return None


def min_level(left: PermLevel, right: PermLevel) -> PermLevel:
    """The grant both a caller and a callee must allow (spec 7.4)."""
    if PermLevel.NONE in (left, right):
        return PermLevel.NONE
    if PermLevel.UNKNOWN in (left, right):
        return PermLevel.UNKNOWN
    return left if _LEVEL_RANK[left] <= _LEVEL_RANK[right] else right


def most_permissive_level(left: PermLevel, right: PermLevel) -> PermLevel:
    """The stronger possible grant across call sites; a definite NONE always loses."""
    if left is right:
        return left
    if PermLevel.WRITE in (left, right):
        return PermLevel.WRITE
    if PermLevel.READ in (left, right):
        return PermLevel.READ
    if PermLevel.UNKNOWN in (left, right):
        return PermLevel.UNKNOWN
    return PermLevel.NONE


def effective_permissions(workflow: WorkflowFact, job: JobFact) -> EffectivePerms:
    scopes = permission_scopes().scopes
    notes: list[str] = []
    if job.permissions is not None:
        levels = _expand(job.permissions, scopes)
        evidence = (
            Evidence(
                cls=EvidenceClass.DECLARED,
                rule="GHA.perm.job",
                file=workflow.path,
                line=job.permissions.line,
                detail="job permissions block",
            ),
        )
        cls = EvidenceClass.DECLARED
        default_block = False
    elif workflow.permissions is not None:
        levels = _expand(workflow.permissions, scopes)
        evidence = (
            Evidence(
                cls=EvidenceClass.DECLARED,
                rule="GHA.perm.workflow",
                file=workflow.path,
                line=workflow.permissions.line,
                detail="workflow permissions block",
            ),
        )
        cls = EvidenceClass.DECLARED
        default_block = False
    else:
        levels = _default_levels(scopes)
        evidence = (
            Evidence(
                cls=EvidenceClass.ASSUMED,
                rule="A-DEFAULT-NO-IDTOKEN",
                file=workflow.path,
                line=job.line,
                detail="no permissions block: id-token not writable, other scopes unknown",
            ),
        )
        cls = EvidenceClass.ASSUMED
        default_block = True
        notes.append(
            "no permissions block: id-token is treated as not writable and other scopes as unknown"
        )

    return EffectivePerms(
        levels=levels,
        id_token_write=id_token_flag(levels),
        cls=cls,
        evidence=evidence,
        notes=tuple(notes),
        default_block=default_block,
    )
