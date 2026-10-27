"""Reusable-workflow call indexing and effective permissions (spec 7.4, BUILD-PLAN 4.4).

Calls inside the repository are indexed by callee path. Remote calls carry no local
callee facts, so they are recorded separately and are never expanded into made-up
jobs: their behaviour is modelled on the caller grant only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from nhi_blast.core.data import permission_scopes
from nhi_blast.core.diagnostics import Diagnostic, warning
from nhi_blast.core.evidence import Evidence, EvidenceClass, weakest
from nhi_blast.core.models import PermLevel
from nhi_blast.parsers.gha.facts import JobFact, UsesRef, WorkflowFact
from nhi_blast.parsers.gha.uses import local_action_dir
from nhi_blast.resolvers.permissions import (
    EffectivePerms,
    effective_permissions,
    id_token_flag,
    min_level,
    most_permissive_level,
)

REMOTE_PREFIX = "remote:"


@dataclass(frozen=True, slots=True)
class CallSite:
    caller_job: JobFact
    callee_path: str
    line: int
    caller_path: str = ""


@dataclass(frozen=True, slots=True)
class ReusableInfo:
    call_sites: tuple[CallSite, ...] = ()
    remote_uses: tuple[UsesRef, ...] = ()


def _local_workflow_path(uses: UsesRef) -> str | None:
    if uses.kind != "LOCAL":
        return None
    path = local_action_dir(uses)
    if path is not None:
        return path
    raw = uses.raw.strip()
    if raw.startswith("./") and raw.endswith((".yml", ".yaml")):
        return raw[2:]
    return None


def reusable_index(workflows: Sequence[WorkflowFact]) -> dict[str, ReusableInfo]:
    """Index reusable-workflow callers by callee path (remote keys prefixed)."""
    call_sites: dict[str, list[CallSite]] = {}
    remote: dict[str, list[UsesRef]] = {}
    for workflow in sorted(workflows, key=lambda item: item.path):
        for job_id in sorted(workflow.jobs):
            job = workflow.jobs[job_id]
            uses = job.uses_workflow
            if uses is None:
                continue
            local_path = _local_workflow_path(uses) if uses.kind == "LOCAL" else None
            if local_path is not None:
                call_sites.setdefault(local_path, []).append(
                    CallSite(
                        caller_job=job,
                        callee_path=local_path,
                        line=uses.line,
                        caller_path=workflow.path,
                    )
                )
            elif uses.kind == "REMOTE":
                remote.setdefault(f"{REMOTE_PREFIX}{uses.raw}", []).append(uses)
    keys = sorted({*call_sites, *remote})
    result: dict[str, ReusableInfo] = {}
    for key in keys:
        sites = sorted(
            call_sites.get(key, ()),
            key=lambda site: (site.caller_path, site.line, site.caller_job.id),
        )
        remote_uses = sorted(
            remote.get(key, ()),
            key=lambda uses: (uses.line, uses.raw),
        )
        result[key] = ReusableInfo(
            call_sites=tuple(sites),
            remote_uses=tuple(remote_uses),
        )
    return result


def _callers(
    callers: Sequence[tuple[WorkflowFact, JobFact]],
) -> tuple[tuple[WorkflowFact, JobFact], ...]:
    unique: dict[tuple[str, str], tuple[WorkflowFact, JobFact]] = {}
    for workflow, job in callers:
        unique.setdefault((workflow.path, job.id), (workflow, job))
    return tuple(unique[key] for key in sorted(unique))


def effective_job_permissions(
    workflow: WorkflowFact,
    job: JobFact,
    callers: Sequence[tuple[WorkflowFact, JobFact]],
) -> EffectivePerms:
    """Bound a reusable job's grant by its local call sites (spec 7.4).

    With several local callers the per-scope result is the most permissive of the
    per-caller minima, because a path through the permissive caller is possible.
    Callers that disagree make the result ASSUMED and raise
    D-GHA-REUSABLE-MULTI-CALLER.
    """
    base = effective_permissions(workflow, job)
    ordered = _callers(callers)
    if not ordered:
        return base
    scopes = permission_scopes().scopes
    bounded: list[tuple[WorkflowFact, JobFact, dict[str, PermLevel], EffectivePerms]] = []
    for caller_workflow, caller_job in ordered:
        caller_effective = effective_permissions(caller_workflow, caller_job)
        levels = {
            scope: min_level(base.levels[scope], caller_effective.levels[scope]) for scope in scopes
        }
        bounded.append((caller_workflow, caller_job, levels, caller_effective))
    combined: dict[str, PermLevel] = {}
    for _caller_workflow, _caller_job, levels, _caller_effective in bounded:
        for scope in scopes:
            current = combined.get(scope)
            combined[scope] = (
                levels[scope] if current is None else most_permissive_level(current, levels[scope])
            )
    evidence = list(base.evidence)
    notes = list(base.notes)
    classes: list[EvidenceClass] = []
    for caller_workflow, caller_job, _levels, caller_effective in bounded:
        classes.append(caller_effective.cls)
        evidence.append(
            Evidence(
                cls=EvidenceClass.DERIVED,
                rule="GHA.perm.reusable",
                file=caller_workflow.path,
                line=caller_job.line,
                detail=f"caller job {caller_job.id} bounds the reusable workflow grant",
            )
        )
        notes.append(f"bounded by caller {caller_workflow.path}#{caller_job.id}")
    diagnostics: list[Diagnostic] = []
    differing = sorted(
        scope for scope in scopes if len({levels[scope] for _w, _j, levels, _e in bounded}) > 1
    )
    if differing:
        evidence.append(
            Evidence(
                cls=EvidenceClass.ASSUMED,
                rule="A-REUSABLE-CALLER",
                file=workflow.path,
                line=job.line,
                detail="multiple call sites grant different permissions: " + ", ".join(differing),
            )
        )
        diagnostics.append(
            warning(
                "D-GHA-REUSABLE-MULTI-CALLER",
                "reusable workflow callers disagree on: " + ", ".join(differing),
                file=workflow.path,
                line=job.line,
            )
        )
        notes.append(
            "multiple callers: per-scope most permissive bound is used (A-REUSABLE-CALLER)"
        )
    confidence = weakest(base.cls, *classes)
    return EffectivePerms(
        levels=combined,
        id_token_write=id_token_flag(combined),
        cls=confidence,
        evidence=tuple(evidence),
        notes=tuple(notes),
        default_block=base.default_block,
        diagnostics=tuple(diagnostics),
    )
