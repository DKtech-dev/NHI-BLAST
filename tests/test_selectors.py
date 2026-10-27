"""Compromise-selector parsing and start-set resolution (M4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nhi_blast.analysis.selectors import (
    SelectorError,
    mutable_action_scenarios,
    parse_selector,
    resolve_starts,
)
from tests.test_graph_builder import PUBLISH_JOB, ROLE_DEPLOY, TEST_JOB, build_fixture, build_inline


@pytest.mark.parametrize(
    ("text", "kind", "value"),
    [
        ("action:tj-actions/changed-files@v45", "action", "tj-actions/changed-files@v45"),
        ("action-any:tj-actions/changed-files", "action-any", "tj-actions/changed-files"),
        (
            "job:.github/workflows/release.yml#publish",
            "job",
            ".github/workflows/release.yml#publish",
        ),
        ("workflow:.github/workflows/release.yml", "workflow", ".github/workflows/release.yml"),
        ("secret:SLACK_WEBHOOK_URL", "secret", "SLACK_WEBHOOK_URL"),
        ("role:aws_iam_role.deploy_prod", "role", "aws_iam_role.deploy_prod"),
        ("repo-write", "repo-write", ""),
        ("fork-pr", "fork-pr", ""),
        ("all-mutable-actions", "all-mutable-actions", ""),
    ],
)
def test_parse_selector_accepts_specification_grammar(text: str, kind: str, value: str) -> None:
    selector = parse_selector(text)
    assert selector.kind == kind
    assert selector.value == value
    assert selector.raw == text


@pytest.mark.parametrize(
    "text",
    [
        "",
        "action:",
        "action:owner/repo",
        "action-any:owner/repo/path",
        "job:missing-job-separator",
        "workflow:",
        "secret:",
        "role:",
        "unknown:value",
        "repo-write:extra",
    ],
)
def test_parse_selector_rejects_invalid_input(text: str) -> None:
    with pytest.raises(SelectorError):
        parse_selector(text)


def test_action_selectors_start_at_every_using_job(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph

    exact = parse_selector("action:tj-actions/changed-files@v45")
    any_ref = parse_selector("action-any:tj-actions/changed-files")

    assert resolve_starts(exact, graph, jobs=()) == (TEST_JOB, PUBLISH_JOB)
    assert resolve_starts(any_ref, graph, jobs=()) == (TEST_JOB, PUBLISH_JOB)


def test_job_workflow_secret_and_role_selectors(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    secret = f"cred:{PUBLISH_JOB}:SLACK_WEBHOOK_URL"
    session = (
        "cred:oidc:job:.github/workflows/release.yml#publish:sts.amazonaws.com:"
        f"sts-session:{ROLE_DEPLOY}"
    )

    assert resolve_starts(parse_selector(f"job:{PUBLISH_JOB[4:]}"), graph, jobs=()) == (
        PUBLISH_JOB,
    )
    assert resolve_starts(
        parse_selector("workflow:.github/workflows/release.yml"), graph, jobs=()
    ) == (PUBLISH_JOB,)
    assert resolve_starts(parse_selector("secret:SLACK_WEBHOOK_URL"), graph, jobs=()) == (
        secret,
        PUBLISH_JOB,
    )
    assert resolve_starts(parse_selector("role:aws_iam_role.deploy_prod"), graph, jobs=()) == (
        ROLE_DEPLOY,
        session,
    )


def test_fork_pr_starts_only_at_untrusted_checkout_jobs(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx12-untrusted-checkout").graph

    assert resolve_starts(parse_selector("fork-pr"), graph, jobs=()) == (
        "job:.github/workflows/issue-comment.yml#command",
        "job:.github/workflows/workflow-run.yml#triage",
    )


def test_selector_with_no_matching_target_is_a_usage_error(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph

    with pytest.raises(SelectorError, match="matched no"):
        resolve_starts(parse_selector("action:example/missing@v1"), graph, jobs=())


def test_all_mutable_actions_expands_to_one_scenario_per_action(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph

    assert mutable_action_scenarios(graph) == (
        ("action:tj-actions/changed-files@v45", (TEST_JOB, PUBLISH_JOB)),
    )


def test_all_mutable_actions_excludes_pinned_and_first_party_and_labels_docker() -> None:
    graph = build_inline(
        """
name: Rank
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: example/pinned@abcdef0123456789abcdef0123456789abcdef01
      - uses: example/mutable@main
      - uses: docker://alpine:3.19
  other:
    runs-on: ubuntu-latest
    steps:
      - uses: example/mutable@main
"""
    ).graph

    assert mutable_action_scenarios(graph) == (
        ("docker://alpine:3.19", ("job:.github/workflows/test.yml#build",)),
        (
            "action:example/mutable@main",
            (
                "job:.github/workflows/test.yml#build",
                "job:.github/workflows/test.yml#other",
            ),
        ),
    )


def test_all_mutable_actions_without_targets_expands_to_nothing() -> None:
    graph = build_inline(
        """
name: Pinned
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@abcdef0123456789abcdef0123456789abcdef01
"""
    ).graph

    assert mutable_action_scenarios(graph) == ()
