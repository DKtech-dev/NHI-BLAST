"""OIDC subject candidates (spec 10.2).

A candidate is a glob describing the ``sub`` values a job could mint for one
trigger. GitHub's precedence is environment, then pull-request context, then ref.
Both classic and immutable repository formats are emitted because the repository's
mint format cannot be determined from files (A-REPO-AGE).
"""

from __future__ import annotations

from collections.abc import Sequence

from nhi_blast.core.evidence import Evidence, EvidenceClass, weakest
from nhi_blast.core.models import SubFormat, SubjectCandidate
from nhi_blast.parsers.gha.facts import JobFact, Trigger, WorkflowFact

DEFAULT_AUDIENCE = "sts.amazonaws.com"

_PR_DEFAULT_BRANCH_EVENTS = frozenset(
    {
        "schedule",
        "workflow_run",
        "issue_comment",
        "issues",
        "discussion",
        "discussion_comment",
        "repository_dispatch",
        "merge_group",
    }
)
_TAG_EVENTS = frozenset({"release", "create", "delete"})
_ANY_REF_EVENTS = frozenset({"workflow_dispatch"})


def _escape_context(value: str) -> str:
    return value.replace(":", "%3A")


def _strip_ref(value: str) -> str:
    for prefix in ("refs/heads/", "refs/tags/"):
        if value.startswith(prefix):
            return value[len(prefix) :]
    return value


def _ref_candidate(repo: str, ref: str) -> str:
    return f"{repo}:ref:{ref}"


def _bump_double_star(pattern: str) -> str:
    return pattern.replace("**", "*")


def _audiences(job: JobFact) -> tuple[str, ...]:
    values = {
        step.aws_auth.audience
        for step in job.steps
        if step.aws_auth is not None and step.aws_auth.audience
    }
    if not values:
        values.add(DEFAULT_AUDIENCE)
    return tuple(sorted(values))


def _candidate(
    *,
    subject: str,
    fmt: SubFormat,
    trigger: Trigger,
    audience: str,
    workflow: WorkflowFact,
    job: JobFact,
    evidence_class: EvidenceClass,
    rule: str,
    detail: str,
    claims: dict[str, str],
) -> SubjectCandidate:
    line = trigger.line or job.line
    return SubjectCandidate(
        subject=subject,
        format=fmt,
        trigger=trigger.event,
        audience=audience,
        claims=claims,
        evidence_class=evidence_class,
        evidence=(
            Evidence(
                cls=evidence_class,
                rule=rule,
                file=workflow.path,
                line=line,
                detail=detail,
            ),
        ),
    )


def _contexts_for_trigger(
    trigger: Trigger, *, default_branch: str
) -> tuple[tuple[str, EvidenceClass, str], ...]:
    """Return (context suffix, class, rule) triples for one trigger."""
    event = trigger.event
    if event == "pull_request":
        return (("pull_request", EvidenceClass.ASSUMED, "A-FORK-NO-OIDC"),)
    if event == "pull_request_target":
        base = _strip_ref(trigger.branches[0]) if trigger.branches else default_branch
        return (
            (
                f"ref:refs/heads/{base}",
                EvidenceClass.ASSUMED,
                "A-PRT-SUB",
            ),
        )
    if event in _ANY_REF_EVENTS:
        return (
            ("ref:refs/heads/*", EvidenceClass.ASSUMED, "A-DISPATCH-ANYREF"),
            ("ref:refs/tags/*", EvidenceClass.ASSUMED, "A-DISPATCH-ANYREF"),
        )
    if event in _TAG_EVENTS:
        contexts = [("ref:refs/tags/*", EvidenceClass.DERIVED, "OIDC.subject")]
        if trigger.tags:
            contexts = [
                (
                    f"ref:refs/tags/{_bump_double_star(_strip_ref(tag))}",
                    EvidenceClass.DERIVED,
                    "OIDC.subject",
                )
                for tag in trigger.tags
            ]
        return tuple(contexts)
    if event in _PR_DEFAULT_BRANCH_EVENTS:
        return (
            (
                f"ref:refs/heads/{default_branch}",
                EvidenceClass.ASSUMED,
                "A-DEFAULT-BRANCH",
            ),
        )
    if event == "workflow_call":
        return ()
    if event == "push":
        push_contexts: list[tuple[str, EvidenceClass, str]] = []
        if trigger.branches:
            for branch in trigger.branches:
                name = _strip_ref(branch)
                push_contexts.append(
                    (
                        f"ref:refs/heads/{_bump_double_star(name)}",
                        EvidenceClass.DERIVED,
                        "OIDC.subject",
                    )
                )
        if trigger.tags:
            for tag in trigger.tags:
                name = _strip_ref(tag)
                push_contexts.append(
                    (
                        f"ref:refs/tags/{_bump_double_star(name)}",
                        EvidenceClass.DERIVED,
                        "OIDC.subject",
                    )
                )
        if not trigger.branches and not trigger.tags:
            push_contexts.extend(
                (
                    ("ref:refs/heads/*", EvidenceClass.DERIVED, "OIDC.subject"),
                    ("ref:refs/tags/*", EvidenceClass.DERIVED, "OIDC.subject"),
                )
            )
        return tuple(push_contexts)
    return (
        (
            "*",
            EvidenceClass.ASSUMED,
            "OIDC.subject-unknown-trigger",
        ),
    )


def _repo_formats(repo_slug: str | None) -> tuple[tuple[SubFormat, str], ...]:
    if repo_slug is None:
        return ((SubFormat.UNKNOWN, "*/*"),)
    owner, _, name = repo_slug.partition("/")
    return (
        (SubFormat.CLASSIC, f"repo:{owner}/{name}"),
        (SubFormat.IMMUTABLE, f"repo:{owner}@*/{name}@*"),
    )


def _contexts_for(
    job: JobFact, trigger: Trigger, *, default_branch: str
) -> tuple[tuple[str, EvidenceClass, str], ...]:
    if job.environment_unresolved:
        return (("environment:*", EvidenceClass.UNKNOWN, "OIDC.subject-environment-expr"),)
    if job.environment:
        return (
            (
                f"environment:{_escape_context(job.environment)}",
                EvidenceClass.ASSUMED,
                "A-ENV-UNPROTECTED",
            ),
        )
    return _contexts_for_trigger(trigger, default_branch=default_branch)


def _claims(
    workflow: WorkflowFact,
    *,
    repo_slug: str | None,
    base_repo: str,
    job: JobFact,
    suffix: str,
) -> dict[str, str]:
    claims = {"repository": base_repo}
    if suffix.startswith("ref:"):
        claims["ref"] = suffix[len("ref:") :]
        if repo_slug is not None:
            claims["job_workflow_ref"] = f"{repo_slug}/{workflow.path}@{claims['ref']}"
    elif suffix.startswith("environment:"):
        claims["environment"] = job.environment or "*"
    if workflow.name and "${{" not in workflow.name:
        claims["workflow"] = workflow.name
    return claims


def _subject(repo_prefix: str, context: str, sub_template: tuple[str, ...] | None) -> str:
    if sub_template is None:
        return f"{repo_prefix}:{context}"
    parts = [repo_prefix]
    if "context" in sub_template:
        parts.append(context)
    return ":".join(parts)


def _unknown_caller_candidates(
    workflow: WorkflowFact,
    job: JobFact,
    trigger: Trigger,
    audiences: tuple[str, ...],
    *,
    repo_slug: str | None,
) -> list[SubjectCandidate]:
    base_repo = repo_slug or "*/*"
    fmt = SubFormat.UNKNOWN if repo_slug is None else SubFormat.CLASSIC
    return [
        _candidate(
            subject=f"repo:{base_repo}:*",
            fmt=fmt,
            trigger=trigger,
            audience=audience,
            workflow=workflow,
            job=job,
            evidence_class=EvidenceClass.UNKNOWN,
            rule="OIDC.subject-unresolved-caller",
            detail="workflow_call has no local caller; candidate union is unknown",
            claims={},
        )
        for audience in audiences
    ]


def subject_candidates(
    job: JobFact,
    workflow: WorkflowFact,
    *,
    repo_slug: str | None,
    default_branch: str = "main",
    sub_template: tuple[str, ...] | None = None,
    caller_candidates: Sequence[SubjectCandidate] = (),
) -> tuple[SubjectCandidate, ...]:
    """Build deterministic OIDC subject candidates for a job."""
    base_repo = repo_slug or "*/*"
    formats = _repo_formats(repo_slug)
    repo_class = EvidenceClass.ASSUMED if repo_slug is None else EvidenceClass.DERIVED
    triggers = workflow.triggers or (Trigger(event="unknown", line=job.line),)
    audiences = _audiences(job)
    candidates: list[SubjectCandidate] = []
    for trigger in triggers:
        if trigger.event == "workflow_call":
            if caller_candidates:
                candidates.extend(caller_candidates)
            else:
                candidates.extend(
                    _unknown_caller_candidates(
                        workflow,
                        job,
                        trigger,
                        audiences,
                        repo_slug=repo_slug,
                    )
                )
            continue
        contexts = _contexts_for(job, trigger, default_branch=default_branch)
        for audience in audiences:
            for suffix, context_class, rule in contexts:
                claims = _claims(
                    workflow,
                    repo_slug=repo_slug,
                    base_repo=base_repo,
                    job=job,
                    suffix=suffix,
                )
                for fmt, repo_prefix in formats:
                    candidates.append(
                        _candidate(
                            subject=_subject(repo_prefix, suffix, sub_template),
                            fmt=fmt,
                            trigger=trigger,
                            audience=audience,
                            workflow=workflow,
                            job=job,
                            evidence_class=weakest(context_class, repo_class),
                            rule=rule,
                            detail=f"candidate for {trigger.event}",
                            claims=dict(claims),
                        )
                    )
    unique: dict[tuple[str, SubFormat, str, str], SubjectCandidate] = {}
    for candidate in candidates:
        key = (candidate.subject, candidate.format, candidate.trigger, candidate.audience)
        unique.setdefault(key, candidate)
    return tuple(unique[key] for key in sorted(unique))
