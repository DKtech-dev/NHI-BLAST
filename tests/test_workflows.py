"""Reusable-workflow indexing and effective permissions (M2, spec 7.4)."""

from __future__ import annotations

from pathlib import Path

from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import PermLevel
from nhi_blast.parsers.gha.facts import WorkflowFact
from nhi_blast.parsers.gha.workflow import parse_workflow
from nhi_blast.resolvers.permissions import effective_permissions, min_level, most_permissive_level
from nhi_blast.resolvers.workflows import (
    REMOTE_PREFIX,
    effective_job_permissions,
    reusable_index,
)

LIMITS = Limits()


def workflow(text: str, path: str = ".github/workflows/caller.yml") -> WorkflowFact:
    parsed = parse_workflow(path, text, limits=LIMITS)
    assert parsed.facts is not None
    assert parsed.diagnostics == ()
    return parsed.facts


def fixture_workflow(fixtures_dir: Path, folder: str, name: str) -> WorkflowFact:
    base = fixtures_dir / folder
    path = base / ".github" / "workflows" / name
    rel = path.relative_to(base).as_posix()
    parsed = parse_workflow(rel, path.read_text(encoding="utf-8"), limits=LIMITS)
    assert parsed.facts is not None
    return parsed.facts


def test_fx13_reusable_index_and_bounded_permissions(fixtures_dir: Path) -> None:
    caller = fixture_workflow(fixtures_dir, "fx13-secrets-inherit", "caller.yml")
    callee = fixture_workflow(fixtures_dir, "fx13-secrets-inherit", "reusable.yml")

    index = reusable_index([caller, callee])
    assert sorted(index) == [".github/workflows/reusable.yml"]
    info = index[".github/workflows/reusable.yml"]
    assert len(info.call_sites) == 1
    site = info.call_sites[0]
    assert site.caller_path == ".github/workflows/caller.yml"
    assert site.caller_job.id == "call"
    assert site.callee_path == ".github/workflows/reusable.yml"

    assert caller.jobs["call"].secrets_mode == "INHERIT"
    inner = callee.jobs["inner"]
    base = effective_permissions(callee, inner)
    bounded = effective_job_permissions(callee, inner, [(caller, caller.jobs["call"])])

    assert bounded.levels == base.levels
    assert bounded.id_token_write is True
    assert bounded.cls is EvidenceClass.DECLARED
    assert any(evidence.rule == "GHA.perm.reusable" for evidence in bounded.evidence)
    assert bounded.diagnostics == ()
    assert inner.refs.secrets == ("DEPLOY_TOKEN",)
    assert inner.steps[1].refs.secrets == ("DEPLOY_TOKEN",)


def test_caller_with_no_permissions_caps_callee_to_none() -> None:
    caller = workflow(
        """
name: Caller
on: push
permissions: {}
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
"""
    )
    callee = workflow(
        """
name: Reusable
on: workflow_call
permissions:
  contents: write
  id-token: write
jobs:
  inner:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@abcdef0123456789abcdef0123456789abcdef01
""",
        path=".github/workflows/reusable.yml",
    )
    bounded = effective_job_permissions(
        callee, callee.jobs["inner"], [(caller, caller.jobs["call"])]
    )
    assert bounded.levels["contents"] is PermLevel.NONE
    assert bounded.levels["id-token"] is PermLevel.NONE
    assert bounded.id_token_write is False


def test_most_permissive_bound_across_callers_is_assumed() -> None:
    permissive = workflow(
        """
name: Permissive caller
on: push
permissions:
  contents: write
  id-token: write
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
""",
        path=".github/workflows/permissive.yml",
    )
    restrictive = workflow(
        """
name: Restrictive caller
on: push
permissions:
  contents: read
jobs:
  call:
    uses: ./.github/workflows/reusable.yml
""",
        path=".github/workflows/restrictive.yml",
    )
    callee = workflow(
        """
name: Reusable
on: workflow_call
permissions:
  contents: write
  id-token: write
jobs:
  inner:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@abcdef0123456789abcdef0123456789abcdef01
""",
        path=".github/workflows/reusable.yml",
    )
    index = reusable_index([callee, permissive, restrictive])
    assert [site.caller_path for site in index[".github/workflows/reusable.yml"].call_sites] == [
        ".github/workflows/permissive.yml",
        ".github/workflows/restrictive.yml",
    ]

    bounded = effective_job_permissions(
        callee,
        callee.jobs["inner"],
        [
            (permissive, permissive.jobs["call"]),
            (restrictive, restrictive.jobs["call"]),
            (permissive, permissive.jobs["call"]),
        ],
    )
    assert bounded.levels["contents"] is PermLevel.WRITE
    assert bounded.levels["id-token"] is PermLevel.WRITE
    assert any(evidence.rule == "A-REUSABLE-CALLER" for evidence in bounded.evidence)
    assert [diagnostic.code for diagnostic in bounded.diagnostics] == [
        "D-GHA-REUSABLE-MULTI-CALLER"
    ]
    assert len([e for e in bounded.evidence if e.rule == "GHA.perm.reusable"]) == 2


def test_permission_level_composition() -> None:
    assert min_level(PermLevel.WRITE, PermLevel.READ) is PermLevel.READ
    assert min_level(PermLevel.UNKNOWN, PermLevel.WRITE) is PermLevel.UNKNOWN
    assert min_level(PermLevel.NONE, PermLevel.UNKNOWN) is PermLevel.NONE
    assert most_permissive_level(PermLevel.NONE, PermLevel.UNKNOWN) is PermLevel.UNKNOWN
    assert most_permissive_level(PermLevel.NONE, PermLevel.READ) is PermLevel.READ
    assert most_permissive_level(PermLevel.NONE, PermLevel.NONE) is PermLevel.NONE
    assert most_permissive_level(PermLevel.READ, PermLevel.WRITE) is PermLevel.WRITE
    assert most_permissive_level(PermLevel.UNKNOWN, PermLevel.READ) is PermLevel.READ


def test_remote_reusable_calls_are_indexed_but_not_expanded() -> None:
    caller = workflow(
        """
name: Caller
on: push
jobs:
  remote:
    uses: acme/shared-workflows/.github/workflows/deploy.yml@v1
  local:
    uses: ./.github/workflows/reusable.yml
"""
    )
    index = reusable_index([caller])
    remote_key = f"{REMOTE_PREFIX}acme/shared-workflows/.github/workflows/deploy.yml@v1"
    assert sorted(index) == [".github/workflows/reusable.yml", remote_key]
    assert index[".github/workflows/reusable.yml"].call_sites[0].caller_job.id == "local"
    remote = index[remote_key]
    assert remote.call_sites == ()
    assert len(remote.remote_uses) == 1
    assert remote.remote_uses[0].kind == "REMOTE"


def test_static_key_inputs_are_recorded_without_values() -> None:
    parsed = parse_workflow(
        ".github/workflows/static.yml",
        """
name: Static
on: push
permissions:
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@abcdef0123456789abcdef0123456789abcdef02
        with:
          aws-access-key-id: ${{ secrets.PROD_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.PROD_SECRET_ACCESS_KEY }}
          aws-session-token: ${{ secrets.PROD_SESSION_TOKEN }}
          role-to-assume: arn:aws:iam::111122223333:role/deploy-prod
""",
        limits=LIMITS,
    )
    assert parsed.facts is not None
    step = parsed.facts.jobs["deploy"].steps[0]
    assert step.aws_auth is not None
    assert step.aws_auth.static_keys is True
    assert step.aws_auth.static_secret_refs == (
        "PROD_ACCESS_KEY_ID",
        "PROD_SECRET_ACCESS_KEY",
        "PROD_SESSION_TOKEN",
    )
    assert step.aws_auth.role_arn == "arn:aws:iam::111122223333:role/deploy-prod"
    assert step.aws_auth.role_ref_kind == "ARN"
    assert not hasattr(step.aws_auth, "aws_access_key_id")


def test_oidc_only_step_has_no_static_keys() -> None:
    workflow_fact = fixture_workflow(
        Path(__file__).parent / "fixtures", "fx02-exact-trust", "release.yml"
    )
    step = workflow_fact.jobs["deploy"].steps[1]
    assert step.aws_auth is not None
    assert step.aws_auth.static_keys is False
    assert step.aws_auth.static_secret_refs == ()
