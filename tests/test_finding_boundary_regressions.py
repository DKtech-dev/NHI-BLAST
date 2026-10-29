"""Selector, finding provenance and scenario deadline boundary regressions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import nhi_blast.analysis.scenario as scenario_module
from nhi_blast.analysis.findings import build_findings, filter_findings
from nhi_blast.analysis.scenario import analyze_scenario
from nhi_blast.analysis.selectors import SelectorError, parse_selector, resolve_starts
from nhi_blast.cli.app import app
from nhi_blast.core.config import Config
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.ids import edge_id
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    Edge,
    EdgeKind,
    GraphData,
    Lifetime,
    Node,
    NodeKind,
    PolicyContext,
    ScenarioReport,
    Severity,
    SubFormat,
)
from nhi_blast.discovery.repo import RepoIdentity
from nhi_blast.graph.builder import GraphInputs, build_graph
from nhi_blast.parsers.gha.workflow import parse_workflow
from nhi_blast.resolvers.composite import expand_jobs
from nhi_blast.resolvers.roles import CloudFacts

SHA = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "a" * 64
PRIVILEGED = """on: push
permissions: {}
jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      KEY: ${{ secrets.API_KEY }}
    steps:
      - uses: example/action@v1
"""
PWN = f"""on: pull_request_target
permissions: {{}}
jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      KEY: ${{{{ secrets.API_KEY }}}}
    steps:
      - uses: actions/checkout@{SHA}
        with:
          ref: refs/pull/123/head
      - run: 'true'
"""


def _workflows(texts: Sequence[tuple[str, str]]) -> GraphData:
    workflows = []
    for path, text in texts:
        parsed = parse_workflow(path, text, limits=Limits())
        assert parsed.facts is not None
        workflows.append(parsed.facts)
    return build_graph(
        GraphInputs(
            repository=RepoIdentity(
                slug="acme/shop",
                source="--repo-slug",
                default_branch="main",
                sub_format=SubFormat.CLASSIC,
            ),
            workflows=tuple(workflows),
            expanded_jobs=expand_jobs(workflows, {}, limits=Limits()),
            cloud=CloudFacts(
                roles=(),
                sinks=(),
                providers=(),
                externals=(),
                policy_context=PolicyContext(),
                diagnostics=(),
            ),
            config=Config.empty(),
        )
    ).graph


@pytest.mark.parametrize("kind", ["action", "action-any", "job", "workflow", "secret", "role"])
@pytest.mark.parametrize("suffix", ["", ":"])
def test_value_selectors_require_a_value(kind: str, suffix: str) -> None:
    with pytest.raises(SelectorError):
        parse_selector(kind + suffix)


@pytest.mark.parametrize("kind", ["action", "action-any", "job", "workflow", "secret", "role"])
def test_bare_value_selector_is_cli_usage_error(kind: str, tmp_path: Path) -> None:
    result = CliRunner().invoke(app, ["scan", str(tmp_path), "--simulate-compromise", kind])
    assert result.exit_code == 2, result.output
    assert "internal error" not in result.output.lower()


@pytest.mark.parametrize("prefix", ["", "action:"])
@pytest.mark.parametrize("reference", ["alpine:3.19", "alpine@" + DIGEST])
def test_docker_selector_resolves_only_exact_image_use_sites(prefix: str, reference: str) -> None:
    graph = _workflows(
        [
            (
                ".github/workflows/tag.yml",
                PRIVILEGED.replace("example/action@v1", "docker://alpine:3.19"),
            ),
            (
                ".github/workflows/digest.yml",
                PRIVILEGED.replace("example/action@v1", "docker://alpine@" + DIGEST),
            ),
        ]
    )
    selector = parse_selector(prefix + "docker://" + reference)
    assert selector.kind == "action"
    path = "tag" if reference == "alpine:3.19" else "digest"
    assert resolve_starts(selector, graph, jobs=()) == (f"job:.github/workflows/{path}.yml#deploy",)


@pytest.mark.parametrize(
    "raw", ["docker://", "action:docker://", "docker://alpine bad", "action-any:docker://alpine"]
)
def test_docker_selector_rejects_missing_image_or_invalid_form(raw: str) -> None:
    with pytest.raises(SelectorError):
        parse_selector(raw)


def test_all_mutable_docker_scan_completes_through_real_cli(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "docker.yml").write_text(
        PRIVILEGED.replace("example/action@v1", "docker://alpine:3.19")
        + f"      - uses: docker://alpine@{DIGEST}\n",
        encoding="utf-8",
    )
    output = tmp_path / "reports"
    result = CliRunner().invoke(
        app,
        [
            "scan",
            str(tmp_path),
            "--repo-slug",
            "acme/shop",
            "--simulate-compromise",
            "all-mutable-actions",
            "--format",
            "json",
            "--out",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert [item["selector"] for item in report["scenarios"]] == ["docker://alpine:3.19"]
    current = report["scenarios"][0]
    assert len(current["partition"]["R"]) == 1
    assert len(current["partition"]["Z"]) == 1
    assert not current["truncated"]
    assert any(item["rule"] == "NHB-SURV-001" for item in report["findings"])


def test_shared_action_evidence_does_not_suppress_another_jobs_finding() -> None:
    prod = ".github/workflows/prod.yml"
    example = ".github/workflows/example.yml"
    graph = _workflows([(prod, PRIVILEGED), (example, PRIVILEGED)])
    findings = tuple(item for item in build_findings(graph).findings if item.rule == "NHB-GHA-001")
    assert len(findings) == 2
    production = next(item for item in findings if f"job:{prod}#deploy" in item.path)
    assert {item.file for item in production.evidence} == {prod}
    assert any(item.line == 9 and item.rule == "R2.action-use" for item in production.evidence)
    filtered = filter_findings(findings, config=Config(ignore_paths=(example,)), strict=True)
    assert filtered.findings == (production,)
    assert len(filtered.diagnostics) == 1


def test_untrusted_checkout_finding_cites_callsite_and_assumed_execution() -> None:
    graph = _workflows([(".github/workflows/test.yml", PWN)])
    (finding,) = [item for item in build_findings(graph).findings if item.rule == "NHB-GHA-002"]
    assert finding.confidence is EvidenceClass.ASSUMED
    assert finding.severity is Severity.HIGH
    assert "A-STEP-SHARE" in finding.assumptions
    assert any(item.cls is EvidenceClass.DECLARED and item.line == 9 for item in finding.evidence)
    assert any(
        item.cls is EvidenceClass.ASSUMED
        and item.line == 12
        and item.file == ".github/workflows/test.yml"
        for item in finding.evidence
    )


@pytest.mark.parametrize(
    "text", [PWN.replace("pull_request_target", "push"), PWN.replace("      - run: 'true'\n", "")]
)
def test_checkout_without_privileged_execution_has_no_gha002(text: str) -> None:
    graph = _workflows([(".github/workflows/test.yml", text)])
    assert not any(item.rule == "NHB-GHA-002" for item in build_findings(graph).findings)


def _node(node_id: str, kind: NodeKind, **attrs: Any) -> Node:
    return Node(
        id=node_id,
        kind=kind,
        label=node_id,
        attrs=attrs,
        evidence=(
            Evidence(cls=EvidenceClass.DECLARED, rule="test.node", file="input.json", line=1),
        ),
    )


def _edge(
    src: str,
    dst: str,
    kind: EdgeKind,
    *,
    confidence: EvidenceClass = EvidenceClass.DERIVED,
    lifetime: Lifetime = Lifetime.NA,
    **attrs: Any,
) -> Edge:
    entries = (Evidence(cls=confidence, rule="test." + kind.value, file="input.json", line=2),)
    return Edge(
        id=edge_id(kind.value, src, dst, entries),
        src=src,
        dst=dst,
        kind=kind,
        confidence=confidence,
        lifetime=lifetime,
        evidence=entries,
        attrs=attrs,
    )


@pytest.mark.parametrize(
    ("lifetime", "confidence", "untrusted", "severity"),
    [
        (Lifetime.PERSISTENT, EvidenceClass.DERIVED, False, Severity.CRITICAL),
        (Lifetime.PERSISTENT_ROTATING, EvidenceClass.ASSUMED, False, Severity.CRITICAL),
        (Lifetime.PERSISTENT, EvidenceClass.UNKNOWN, False, Severity.HIGH),
        (Lifetime.JOB_BOUND, EvidenceClass.DERIVED, False, Severity.HIGH),
        (Lifetime.JOB_BOUND, EvidenceClass.DERIVED, True, Severity.CRITICAL),
    ],
)
def test_repo_wide_trust_applies_persistent_and_checkout_adjustments(
    lifetime: Lifetime,
    confidence: EvidenceClass,
    untrusted: bool,
    severity: Severity,
) -> None:
    graph = GraphData(
        nodes=(
            _node("job", NodeKind.JOB, untrusted_checkout=untrusted),
            _node("oidc", NodeKind.OIDC_IDENTITY, job="job"),
            _node("role", NodeKind.AWS_ROLE),
            _node("sink", NodeKind.SINK),
            _node("credential", NodeKind.CREDENTIAL, lifetime=lifetime.value),
        ),
        edges=(
            _edge("oidc", "role", EdgeKind.CAN_ASSUME, breadth="REPO_ANY_CONTEXT"),
            _edge("role", "sink", EdgeKind.CAN_READ_VALUE, confidence=confidence),
            _edge("sink", "credential", EdgeKind.STORES, lifetime=lifetime),
        ),
    )
    (finding,) = [item for item in build_findings(graph).findings if item.rule == "NHB-OIDC-003"]
    assert finding.severity is severity


def _rotation_graph(*, docker: bool = False, mutable: bool = True) -> GraphData:
    nodes = [_node("sink", NodeKind.SINK)]
    edges: list[Edge] = []
    for suffix, ref, is_mutable in (("mutable", "v1", mutable), ("pinned", SHA, False)):
        raw = (
            ("docker://alpine:3.19" if suffix == "mutable" else "docker://alpine@" + DIGEST)
            if docker
            else "example/action@" + ref
        )
        action_id = "action:" + raw
        job_id, identity, role_id = "job:" + suffix, "oidc:" + suffix, "role:" + suffix
        nodes.extend(
            (
                _node(
                    action_id,
                    NodeKind.ACTION_REF,
                    raw=raw,
                    mutable=is_mutable,
                    first_party=False,
                    owner=None if docker else "example",
                    repo=None if docker else "action",
                ),
                _node(job_id, NodeKind.JOB),
                _node(identity, NodeKind.OIDC_IDENTITY, job=job_id),
                _node(role_id, NodeKind.AWS_ROLE),
            )
        )
        edges.extend(
            (
                _edge(job_id, action_id, EdgeKind.RUNS_IN),
                _edge(job_id, identity, EdgeKind.CAN_MINT),
                _edge(identity, role_id, EdgeKind.CAN_ASSUME),
                _edge(role_id, "sink", EdgeKind.CAN_MODIFY),
            )
        )
    return GraphData(nodes=tuple(nodes), edges=tuple(edges))


@pytest.mark.parametrize(
    ("selector", "docker", "mutable", "roles"),
    [
        ("action:example/action@v1", False, True, {"role:mutable"}),
        ("action:example/action@" + SHA, False, True, set()),
        ("action-any:example/action", False, True, {"role:mutable"}),
        ("action-any:example/action", False, False, set()),
        ("action:example/missing@v1", False, True, set()),
        ("all-mutable-actions", False, True, {"role:mutable"}),
        ("docker://alpine:3.19", True, True, {"role:mutable"}),
        ("docker://alpine@" + DIGEST, True, True, set()),
    ],
)
def test_rot002_requires_role_reachable_from_matched_mutable_action(
    selector: str,
    docker: bool,
    mutable: bool,
    roles: set[str],
) -> None:
    graph = _rotation_graph(docker=docker, mutable=mutable)
    # Reports may contain several start jobs; unrelated and pinned refs cannot
    # establish the mutable-entrypoint premise for a role.
    report = ScenarioReport(selector=selector, start_nodes=("job:mutable", "job:pinned"))
    findings = [
        item
        for item in build_findings(graph, scenarios=(report,)).findings
        if item.rule == "NHB-ROT-002"
    ]
    assert {item.path[-2] for item in findings} == roles
    assert all(item.path[0] == "job:mutable" for item in findings)


@pytest.mark.parametrize(
    "stage", ["partition_graph", "plan_rotation", "build_findings", "filter_findings"]
)
def test_scenario_rechecks_deadline_after_stages_and_keeps_completed_data(
    stage: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _workflows([(".github/workflows/test.yml", PRIVILEGED)])
    now = [0.0]
    original = getattr(scenario_module, stage)

    def completes_at_deadline(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        now[0] = 1.0
        return result

    monkeypatch.setattr(scenario_module, stage, completes_at_deadline)
    result = analyze_scenario(
        graph,
        ("job:.github/workflows/test.yml#deploy",),
        selector="job:.github/workflows/test.yml#deploy",
        selector_kind="job",
        limits=Limits(scenario_time_budget_seconds=1),
        clock=lambda: now[0],
    )
    assert result.truncated
    assert result.to_report().truncated
    assert [item.code for item in result.diagnostics] == ["D-ANALYSIS-TIME"]
    assert len(result.partition.R) == 1
    assert len(result.partition.Z) == 1
    assert not any("depth limit" in note for note in result.notes)
    if stage != "partition_graph":
        assert result.rotation_plan.rotation
    if stage in {"build_findings", "filter_findings"}:
        assert any(item.rule == "NHB-SURV-001" for item in result.findings)


def test_timeout_during_closure_is_not_reported_as_depth_limit() -> None:
    graph = GraphData(nodes=(_node("credential", NodeKind.CREDENTIAL, lifetime="persistent"),))
    result = analyze_scenario(
        graph,
        ("credential",),
        selector="secret:KEY",
        selector_kind="secret",
        limits=Limits(scenario_time_budget_seconds=0),
        clock=lambda: 0.0,
    )
    assert result.truncated
    assert [item.code for item in result.diagnostics] == ["D-ANALYSIS-TIME"]
    assert not any("depth limit" in note for note in result.notes)
