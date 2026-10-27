"""Local composite-action expansion and termination (M2)."""

from __future__ import annotations

from pathlib import Path

from nhi_blast.core.limits import Limits
from nhi_blast.parsers.gha.facts import CompositeActionFact, UsesRef
from nhi_blast.parsers.gha.uses import local_action_dir
from nhi_blast.parsers.gha.workflow import parse_composite_action, parse_workflow
from nhi_blast.resolvers.composite import ExpandedJob, expand_jobs

LIMITS = Limits()


def load_composites(fixtures_dir: Path, folder: str) -> dict[str, CompositeActionFact]:
    base = fixtures_dir / folder
    composites: dict[str, CompositeActionFact] = {}
    for path in sorted(base.glob(".github/actions/*/action.y*ml")):
        rel = path.relative_to(base).as_posix()
        parsed = parse_composite_action(rel, path.read_text(encoding="utf-8"), limits=LIMITS)
        assert parsed.facts is not None
        composites[rel] = parsed.facts
    return composites


def load_workflow(fixtures_dir: Path, folder: str, name: str) -> ExpandedJob:
    base = fixtures_dir / folder
    path = base / ".github" / "workflows" / name
    rel = path.relative_to(base).as_posix()
    parsed = parse_workflow(rel, path.read_text(encoding="utf-8"), limits=LIMITS)
    assert parsed.facts is not None
    jobs = {
        job.job.id: job
        for job in expand_jobs([parsed.facts], load_composites(fixtures_dir, folder), limits=LIMITS)
    }
    return jobs


def test_local_action_dir_keeps_hidden_directories() -> None:
    uses = UsesRef(raw="./.github/actions/setup/", kind="LOCAL")
    assert local_action_dir(uses) == ".github/actions/setup"
    assert local_action_dir(UsesRef(raw=".", kind="LOCAL")) == "."
    assert local_action_dir(UsesRef(raw="actions/checkout@v4", kind="REMOTE")) is None


def test_root_local_action_is_expanded() -> None:
    workflow = parse_workflow(
        ".github/workflows/root.yml",
        """
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: ./
""",
        limits=LIMITS,
    )
    action = parse_composite_action(
        "action.yml",
        """
name: root
runs:
  using: composite
  steps:
    - name: Root step
      run: echo root
      shell: bash
""",
        limits=LIMITS,
    )
    assert workflow.facts is not None
    assert action.facts is not None

    jobs = {
        item.job.id: item
        for item in expand_jobs([workflow.facts], {"action.yml": action.facts}, limits=LIMITS)
    }
    build = jobs["build"]

    assert build.diagnostics == ()
    assert [(step.step.name, step.depth) for step in build.steps] == [
        (None, 0),
        ("Root step", 1),
    ]
    assert build.steps[1].composite_paths == ("action.yml",)


def test_nested_composites_expand_with_provenance(fixtures_dir: Path) -> None:
    jobs = load_workflow(fixtures_dir, "fx06-composite", "build.yml")
    build = jobs["build"]

    assert build.diagnostics == ()
    assert [(step.step.name or step.step.uses.raw, step.depth) for step in build.steps] == [
        ("actions/checkout@abcdef0123456789abcdef0123456789abcdef01", 0),
        ("./.github/actions/setup", 0),
        ("Install tooling", 1),
        ("./.github/actions/nested", 1),
        ("Configure npm", 2),
        ("Publish package", 0),
    ]
    nested = build.steps[4]
    assert nested.composite_paths == (
        ".github/actions/setup/action.yml",
        ".github/actions/nested/action.yml",
    )
    assert build.refs.secrets == ("NPM_TOKEN",)


def test_cycle_terminates_and_is_reported(fixtures_dir: Path) -> None:
    jobs = load_workflow(fixtures_dir, "fx06-composite", "build.yml")
    cycle = jobs["cycle"]

    assert [step.depth for step in cycle.steps] == [0, 1, 2]
    assert [diagnostic.code for diagnostic in cycle.diagnostics] == ["D-GHA-COMPOSITE-CYCLE"]
    assert "cycle-a" in cycle.diagnostics[0].message


def test_depth_limit_stops_expansion(fixtures_dir: Path) -> None:
    jobs = load_workflow(fixtures_dir, "fx06-composite", "build.yml")
    deep = jobs["deep"]

    assert [step.depth for step in deep.steps] == [0, 1, 2, 3, 4, 5]
    assert deep.steps[-1].step.uses is not None
    assert deep.steps[-1].step.uses.raw == "./.github/actions/deep-6"
    assert [diagnostic.code for diagnostic in deep.diagnostics] == ["D-GHA-COMPOSITE-DEPTH"]

    shallow = expand_jobs(
        [load_workflow(fixtures_dir, "fx06-composite", "build.yml")["deep"].workflow],
        load_composites(fixtures_dir, "fx06-composite"),
        limits=Limits(max_composite_depth=1),
    )
    deep_job = next(job for job in shallow if job.job.id == "deep")
    assert [step.depth for step in deep_job.steps] == [0, 1]
    assert [diagnostic.code for diagnostic in deep_job.diagnostics] == ["D-GHA-COMPOSITE-DEPTH"]


def test_top_level_remote_action_is_not_flagged_opaque(fixtures_dir: Path) -> None:
    jobs = load_workflow(fixtures_dir, "fx06-composite", "build.yml")
    deploy = jobs["deploy"]
    assert [step.depth for step in deploy.steps] == [0]
    assert deploy.diagnostics == ()


def _workflow(text: str, path: str = ".github/workflows/build.yml") -> object:
    parsed = parse_workflow(path, text, limits=LIMITS)
    assert parsed.facts is not None
    return parsed.facts


def test_nested_remote_action_is_marked_share_assumption() -> None:
    workflow = _workflow(
        """
name: Build
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/wrapper
"""
    )
    composite = CompositeActionFact(
        path=".github/actions/wrapper/action.yml",
        name="Wrapper",
        using="composite",
        steps=(
            parse_composite_action(
                "action.yml",
                """
name: Wrapper
runs:
  using: composite
  steps:
    - uses: acme/remote-action@v1
""",
                limits=LIMITS,
            ).facts.steps[0],
        ),
    )
    expanded = expand_jobs(
        [workflow],
        {".github/actions/wrapper/action.yml": composite},
        limits=LIMITS,
    )
    job = expanded[0]
    assert [step.depth for step in job.steps] == [0, 1]
    assert [diagnostic.code for diagnostic in job.diagnostics] == ["D-GHA-REMOTE-OPAQUE"]
    assert job.diagnostics[0].level.value == "info"


def test_missing_invalid_and_non_composite_references() -> None:
    workflow = _workflow(
        """
name: Build
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/missing
      - uses: ./../outside
      - uses: ./.github/actions/node
"""
    )
    node_action = parse_composite_action(
        ".github/actions/node/action.yml",
        """
name: Node action
runs:
  using: node20
  main: index.js
""",
        limits=LIMITS,
    )
    assert node_action.facts is not None
    expanded = expand_jobs(
        [workflow],
        {".github/actions/node/action.yml": node_action.facts},
        limits=LIMITS,
    )
    codes = [diagnostic.code for diagnostic in expanded[0].diagnostics]
    assert codes == [
        "D-GHA-COMPOSITE-MISSING",
        "D-GHA-COMPOSITE-INVALID",
        "D-GHA-COMPOSITE-OPAQUE",
    ]


def test_composites_are_not_expanded_twice_for_shared_paths() -> None:
    workflow = _workflow(
        """
name: Build
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: ./.github/actions/setup
      - uses: ./.github/actions/setup
"""
    )
    action = parse_composite_action(
        ".github/actions/setup/action.yml",
        """
name: Setup
runs:
  using: composite
  steps:
    - shell: bash
      env:
        TOKEN: ${{ secrets.NPM_TOKEN }}
      run: echo ok
""",
        limits=LIMITS,
    )
    expanded = expand_jobs(
        [workflow], {".github/actions/setup/action.yml": action.facts}, limits=LIMITS
    )
    job = expanded[0]
    assert len(job.steps) == 4
    assert job.refs.secrets == ("NPM_TOKEN",)
