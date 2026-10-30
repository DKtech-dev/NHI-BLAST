"""Local composite-action expansion (spec 7.7).

Expansion is a pure transformation of already parsed facts: no file is read here.
Depth is capped by ``Limits.max_composite_depth`` and cycles are detected by the
chain of action files, so hostile metadata cannot cause unbounded recursion.
"""

from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from nhi_blast.core.diagnostics import Diagnostic, DiagnosticBag, info, warning
from nhi_blast.core.limits import Limits
from nhi_blast.parsers.gha.facts import (
    CompositeActionFact,
    ExprRefs,
    JobFact,
    StepFact,
    WorkflowFact,
)

_COMPOSITE_FILES = ("action.yml", "action.yaml")


@dataclass(frozen=True, slots=True)
class ExpandedStep:
    step: StepFact
    composite_paths: tuple[str, ...] = ()
    depth: int = 0


@dataclass(frozen=True, slots=True)
class ExpandedJob:
    workflow: WorkflowFact
    job: JobFact
    refs: ExprRefs
    steps: tuple[ExpandedStep, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(slots=True)
class _Expansion:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    used: set[str] = field(default_factory=set)


def _safe_local_path(raw: str) -> str | None:
    """Resolve a repository-relative local path, rejecting escapes.

    The empty string denotes the repository root, which GitHub accepts as the
    local action reference ``./``.
    """
    value = raw.strip()
    if value == ".":
        return ""
    if not value.startswith("./") or "\\" in value:
        return None
    body = value[2:].rstrip("/")
    if not body:
        return ""
    normalised = posixpath.normpath(body)
    if normalised in {".", ".."} or normalised.startswith("../") or normalised.startswith("/"):
        return None
    return normalised


def _action_file_candidates(raw: str) -> tuple[str, ...]:
    path = _safe_local_path(raw)
    if path is None:
        return ()
    if path == "":
        return _COMPOSITE_FILES
    if path.endswith((".yml", ".yaml")):
        return (path,)
    return tuple(f"{path}/{name}" for name in _COMPOSITE_FILES)


def _lookup_composite(
    candidates: Sequence[str], composites: Mapping[str, CompositeActionFact]
) -> tuple[str, CompositeActionFact] | None:
    for candidate in candidates:
        fact = composites.get(candidate) or composites.get(f"./{candidate}")
        if fact is not None:
            return candidate, fact
    return None


def _expand_step(
    step: StepFact,
    *,
    source_file: str,
    depth: int,
    chain: tuple[str, ...],
    composites: Mapping[str, CompositeActionFact],
    limits: Limits,
    state: _Expansion,
) -> list[ExpandedStep]:
    expanded = [ExpandedStep(step=step, composite_paths=chain, depth=depth)]
    uses = step.uses
    if uses is None or uses.kind != "LOCAL":
        if uses is not None and uses.kind == "REMOTE" and depth > 0:
            state.diagnostics.append(
                info(
                    "D-GHA-REMOTE-OPAQUE",
                    "nested remote action steps are assumed to share the job (A-STEP-SHARE)",
                    file=source_file,
                    line=step.line,
                )
            )
        return expanded
    candidates = _action_file_candidates(uses.raw)
    if not candidates:
        state.diagnostics.append(
            warning(
                "D-GHA-COMPOSITE-INVALID",
                f"local action reference {uses.raw} is not a safe repository path",
                file=source_file,
                line=step.line,
            )
        )
        return expanded
    found = _lookup_composite(candidates, composites)
    if found is None:
        state.diagnostics.append(
            warning(
                "D-GHA-COMPOSITE-MISSING",
                f"local action {uses.raw} was not found in the scanned inputs",
                file=source_file,
                line=step.line,
            )
        )
        return expanded
    path, fact = found
    if path in chain:
        state.diagnostics.append(
            warning(
                "D-GHA-COMPOSITE-CYCLE",
                f"composite action cycle detected at {path}",
                file=source_file,
                line=step.line,
            )
        )
        return expanded
    if depth + 1 > limits.max_composite_depth:
        state.diagnostics.append(
            warning(
                "D-GHA-COMPOSITE-DEPTH",
                f"composite expansion stopped at depth {limits.max_composite_depth}",
                file=source_file,
                line=step.line,
            )
        )
        return expanded
    if fact.using != "composite":
        state.diagnostics.append(
            info(
                "D-GHA-COMPOSITE-OPAQUE",
                f"{path} is not a composite action; its steps are not expanded",
                file=source_file,
                line=step.line,
            )
        )
        return expanded
    state.used.add(path)
    child_chain = (*chain, path)
    for nested in fact.steps:
        expanded.extend(
            _expand_step(
                nested,
                source_file=fact.path,
                depth=depth + 1,
                chain=child_chain,
                composites=composites,
                limits=limits,
                state=state,
            )
        )
    return expanded


def _expand_job(
    workflow: WorkflowFact,
    job: JobFact,
    composites: Mapping[str, CompositeActionFact],
    limits: Limits,
) -> ExpandedJob:
    state = _Expansion()
    steps: list[ExpandedStep] = []
    for step in job.steps:
        steps.extend(
            _expand_step(
                step,
                source_file=workflow.path,
                depth=0,
                chain=(),
                composites=composites,
                limits=limits,
                state=state,
            )
        )
    refs = job.refs
    for path in sorted(state.used):
        refs = refs.merge(composites[path].refs)
    return ExpandedJob(
        workflow=workflow,
        job=job,
        refs=refs,
        steps=tuple(steps),
        diagnostics=DiagnosticBag(state.diagnostics).sorted(),
    )


def expand_jobs(
    workflows: Sequence[WorkflowFact],
    composites: Mapping[str, CompositeActionFact],
    *,
    limits: Limits,
) -> tuple[ExpandedJob, ...]:
    """Expand local composite actions into the calling job's step sequence."""
    expanded: list[ExpandedJob] = []
    for workflow in sorted(workflows, key=lambda item: item.path):
        for job_id in sorted(workflow.jobs):
            expanded.append(_expand_job(workflow, workflow.jobs[job_id], composites, limits))
    return tuple(expanded)
