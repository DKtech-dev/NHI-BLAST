"""OIDC subject candidate assembly (spec 10.2)."""

from __future__ import annotations

from collections.abc import Sequence

from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.models import SubFormat, SubjectCandidate
from nhi_blast.oidc.github_subject import subject_candidates
from nhi_blast.parsers.gha.facts import Trigger
from tests.support import candidate, job, workflow


def build(
    *,
    triggers: Sequence[Trigger] = (),
    environment: str | None = None,
    environment_unresolved: bool = False,
    audience: str | None = None,
    repo_slug: str | None = "acme/shop",
    default_branch: str = "main",
    sub_template: tuple[str, ...] | None = None,
    caller_candidates: Sequence[SubjectCandidate] = (),
):
    return subject_candidates(
        job(
            environment=environment,
            environment_unresolved=environment_unresolved,
            audience=audience,
        ),
        workflow(triggers=triggers),
        repo_slug=repo_slug,
        default_branch=default_branch,
        sub_template=sub_template,
        caller_candidates=caller_candidates,
    )


def classic_subjects(candidates) -> set[str]:
    return {item.subject for item in candidates if item.format is SubFormat.CLASSIC}


def immutable_subjects(candidates) -> set[str]:
    return {item.subject for item in candidates if item.format is SubFormat.IMMUTABLE}


def test_push_tag_filter_emits_both_formats_with_claims() -> None:
    candidates = build(triggers=(Trigger(event="push", tags=("v*",), line=3),))
    assert classic_subjects(candidates) == {"repo:acme/shop:ref:refs/tags/v*"}
    assert immutable_subjects(candidates) == {"repo:acme@*/shop@*:ref:refs/tags/v*"}
    for item in candidates:
        assert item.evidence_class is EvidenceClass.DERIVED
        assert item.trigger == "push"
        assert item.audience == "sts.amazonaws.com"
        assert item.claims == {
            "repository": "acme/shop",
            "ref": "refs/tags/v*",
            "job_workflow_ref": ("acme/shop/.github/workflows/release.yml@refs/tags/v*"),
            "workflow": "Release",
        }
        assert item.evidence[0].line == 3


def test_push_without_filters_covers_all_branches_and_tags() -> None:
    candidates = build(triggers=(Trigger(event="push", line=2),))
    assert classic_subjects(candidates) == {
        "repo:acme/shop:ref:refs/heads/*",
        "repo:acme/shop:ref:refs/tags/*",
    }


def test_push_branch_globs_bump_double_star() -> None:
    candidates = build(triggers=(Trigger(event="push", branches=("main", "releases/**"), line=2),))
    assert classic_subjects(candidates) == {
        "repo:acme/shop:ref:refs/heads/main",
        "repo:acme/shop:ref:refs/heads/releases/*",
    }


def test_push_tag_prefix_is_stripped() -> None:
    candidates = build(triggers=(Trigger(event="push", tags=("refs/tags/v1.*",), line=2),))
    assert "repo:acme/shop:ref:refs/tags/v1.*" in classic_subjects(candidates)


def test_pull_request_has_no_ref_claim() -> None:
    candidates = build(triggers=(Trigger(event="pull_request", line=4),))
    assert classic_subjects(candidates) == {"repo:acme/shop:pull_request"}
    for item in candidates:
        assert item.evidence_class is EvidenceClass.ASSUMED
        assert "ref" not in item.claims
        assert "job_workflow_ref" not in item.claims


def test_pull_request_target_uses_first_branch_filter() -> None:
    candidates = build(
        triggers=(Trigger(event="pull_request_target", branches=("release/**", "main")),)
    )
    classic = classic_subjects(candidates)
    assert classic == {"repo:acme/shop:ref:refs/heads/release/**"}
    item = next(c for c in candidates if c.format is SubFormat.CLASSIC)
    assert item.claims["job_workflow_ref"] == (
        "acme/shop/.github/workflows/release.yml@refs/heads/release/**"
    )


def test_pull_request_target_defaults_to_default_branch() -> None:
    candidates = build(triggers=(Trigger(event="pull_request_target"),))
    assert classic_subjects(candidates) == {"repo:acme/shop:ref:refs/heads/main"}


def test_schedule_uses_default_branch() -> None:
    candidates = build(
        triggers=(Trigger(event="schedule"),),
        default_branch="trunk",
    )
    assert classic_subjects(candidates) == {"repo:acme/shop:ref:refs/heads/trunk"}


def test_workflow_dispatch_covers_branches_and_tags() -> None:
    candidates = build(triggers=(Trigger(event="workflow_dispatch"),))
    assert classic_subjects(candidates) == {
        "repo:acme/shop:ref:refs/heads/*",
        "repo:acme/shop:ref:refs/tags/*",
    }


def test_release_defaults_to_tags() -> None:
    candidates = build(triggers=(Trigger(event="release"),))
    assert classic_subjects(candidates) == {"repo:acme/shop:ref:refs/tags/*"}


def test_environment_beats_ref() -> None:
    candidates = build(
        triggers=(Trigger(event="push", branches=("main",)),),
        environment="Production:V1",
    )
    assert classic_subjects(candidates) == {"repo:acme/shop:environment:Production%3AV1"}
    item = next(c for c in candidates if c.format is SubFormat.CLASSIC)
    assert item.claims == {
        "repository": "acme/shop",
        "environment": "Production:V1",
        "workflow": "Release",
    }
    assert item.evidence_class is EvidenceClass.ASSUMED


def test_expression_environment_is_unknown() -> None:
    candidates = build(
        triggers=(Trigger(event="schedule"),),
        environment_unresolved=True,
    )
    assert classic_subjects(candidates) == {"repo:acme/shop:environment:*"}
    assert all(item.evidence_class is EvidenceClass.UNKNOWN for item in candidates)


def test_unknown_trigger_is_an_arbitrary_ref() -> None:
    candidates = build(triggers=(Trigger(event="deployment", line=7),))
    assert classic_subjects(candidates) == {"repo:acme/shop:*"}
    item = next(c for c in candidates if c.format is SubFormat.CLASSIC)
    assert item.evidence_class is EvidenceClass.ASSUMED
    assert "ref" not in item.claims


def test_missing_triggers_are_unknown() -> None:
    candidates = build()
    assert classic_subjects(candidates) == {"repo:acme/shop:*"}


def test_workflow_call_without_caller_is_unknown() -> None:
    candidates = build(triggers=(Trigger(event="workflow_call", line=3),))
    assert classic_subjects(candidates) == {"repo:acme/shop:*"}
    item = next(c for c in candidates if c.format is SubFormat.CLASSIC)
    assert item.evidence_class is EvidenceClass.UNKNOWN
    assert item.evidence[0].rule == "OIDC.subject-unresolved-caller"
    assert item.trigger == "workflow_call"


def test_workflow_call_uses_caller_candidates() -> None:
    caller = candidate("repo:acme/shop:ref:refs/heads/main")
    candidates = build(
        triggers=(Trigger(event="workflow_call", line=3),),
        caller_candidates=(caller,),
    )
    assert candidates == (caller,)


def test_symbolic_repository_is_assumed_unknown_format() -> None:
    candidates = build(
        triggers=(Trigger(event="push", branches=("main",)),),
        repo_slug=None,
    )
    assert len(candidates) == 1
    item = candidates[0]
    assert item.format is SubFormat.UNKNOWN
    assert item.subject == "*/*:ref:refs/heads/main"
    assert item.evidence_class is EvidenceClass.ASSUMED
    assert "job_workflow_ref" not in item.claims


def test_custom_sub_template_without_context() -> None:
    candidates = build(
        triggers=(Trigger(event="push", branches=("main",)),),
        sub_template=("repo",),
    )
    assert classic_subjects(candidates) == {"repo:acme/shop"}
    assert immutable_subjects(candidates) == {"repo:acme@*/shop@*"}


def test_custom_audience_replaces_default() -> None:
    candidates = build(
        triggers=(Trigger(event="push", branches=("main",)),),
        audience="custom.audience",
    )
    assert {item.audience for item in candidates} == {"custom.audience"}


def test_workflow_name_expression_is_not_claimed() -> None:
    candidates = subject_candidates(
        job(),
        workflow(
            name="Release ${{ inputs.channel }}",
            triggers=(Trigger(event="push", branches=("main",)),),
        ),
        repo_slug="acme/shop",
    )
    assert all("workflow" not in item.claims for item in candidates)


def test_candidates_are_deterministic_and_sorted() -> None:
    triggers = (
        Trigger(event="push", branches=("main", "dev")),
        Trigger(event="workflow_dispatch"),
    )
    first = build(triggers=triggers)
    second = build(triggers=triggers)
    assert first == second
    keys = [(c.subject, c.format.value, c.trigger, c.audience) for c in first]
    assert keys == sorted(keys)
