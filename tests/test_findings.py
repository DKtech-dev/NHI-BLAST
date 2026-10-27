"""Findings catalog, dynamic severity and ignore filtering (M4)."""

from __future__ import annotations

from pathlib import Path

from nhi_blast.analysis.findings import build_findings, filter_findings
from nhi_blast.analysis.partition import partition_graph
from nhi_blast.analysis.selectors import parse_selector, resolve_starts
from nhi_blast.core.config import Config
from nhi_blast.core.diagnostics import DiagnosticLevel
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.ids import edge_id
from nhi_blast.core.models import Edge, EdgeKind, PolicyContext, ScenarioReport, Severity
from nhi_blast.resolvers.roles import CloudFacts
from tests.test_graph_builder import ROLE_DEPLOY, build_fixture, build_inline
from tests.test_solver import make_role


def scenario(graph, selector: str) -> ScenarioReport:
    starts = resolve_starts(parse_selector(selector), graph, jobs=())
    result = partition_graph(graph, starts)
    return ScenarioReport(
        selector=selector,
        start_nodes=starts,
        partition=result.partition,
        potential=result.potential.edges,
        potential_nodes=result.potential.nodes,
        unresolved_inputs=result.potential.unresolved_inputs,
        truncated=result.truncated,
    )


def by_rule(findings, rule: str):
    return [finding for finding in findings if finding.rule == rule]


def test_fx07_findings_apply_reference_and_survivor_severities(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    current = scenario(graph, "action:tj-actions/changed-files@v45")

    findings = build_findings(graph, scenarios=(current,)).findings

    wildcard = by_rule(findings, "NHB-OIDC-002")
    assert len(wildcard) == 1
    assert wildcard[0].severity is Severity.CRITICAL
    assert "legacy-ci" in wildcard[0].message
    assert wildcard[0].evidence
    assert by_rule(findings, "NHB-OIDC-005")[0].severity is Severity.LOW
    mutable = by_rule(findings, "NHB-GHA-001")
    assert len(mutable) == 1
    assert mutable[0].severity is Severity.HIGH
    survivors = by_rule(findings, "NHB-SURV-001")
    assert len(survivors) == 1
    assert survivors[0].severity is Severity.CRITICAL
    assert survivors[0].scenario == current.selector
    assert len(survivors[0].path) > 1
    assert survivors[0].path_edges
    assert len(by_rule(findings, "NHB-ROT-001")) == 3
    assert by_rule(findings, "NHB-ROT-002") == []


def test_environment_trust_reports_unknown_protection(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx04-environment").graph

    findings = build_findings(graph).findings

    environment = by_rule(findings, "NHB-OIDC-007")
    assert len(environment) == 1
    assert environment[0].severity is Severity.INFO
    assert "protection" in environment[0].message


def test_wildcard_fixture_covers_unconstrained_and_missing_audience(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx03-wildcard-trust").graph

    findings = build_findings(graph).findings

    assert by_rule(findings, "NHB-OIDC-001")[0].severity is Severity.CRITICAL
    assert by_rule(findings, "NHB-OIDC-004")[0].severity is Severity.MEDIUM


def test_repo_wide_and_dead_condition_audits_survive_without_matching_edges() -> None:
    repo_wide = make_role({"StringLike": {"sub": ["repo:acme/shop:*"]}}).model_copy(
        update={"id": "aws:role:repo-wide", "name": "repo-wide"}
    )
    dead = make_role(
        {"StringEquals": {"repository_owner": ["acme"]}},
        {"StringLike": {"sub": ["repo:acme/shop:*"]}},
    ).model_copy(update={"id": "aws:role:dead", "name": "dead"})
    cloud = CloudFacts(
        roles=(repo_wide, dead),
        sinks=(),
        providers=(),
        externals=(),
        policy_context=PolicyContext(),
        diagnostics=(),
    )
    graph = build_inline(
        """
name: Trust audit
on: push
permissions:
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo deploy
""",
        cloud=cloud,
    ).graph

    findings = build_findings(graph).findings

    assert by_rule(findings, "NHB-OIDC-003")[0].severity is Severity.HIGH
    dead_findings = by_rule(findings, "NHB-OIDC-006")
    assert len(dead_findings) == 1
    assert dead_findings[0].severity is Severity.LOW
    assert "dead" in dead_findings[0].message


def test_job_fact_findings_cover_runner_wildcard_literal_and_static_keys() -> None:
    token = "ghp_" + "A" * 36
    graph = build_inline(
        f"""
name: Findings
on: push
permissions:
  id-token: write
jobs:
  deploy:
    runs-on: [self-hosted, linux]
    env:
      ALL_SECRETS: ${{{{ toJSON(secrets) }}}}
      TOKEN: {token}
    steps:
      - uses: aws-actions/configure-aws-credentials@abcdef0123456789abcdef0123456789abcdef02
        with:
          aws-access-key-id: ${{{{ secrets.PROD_ACCESS_KEY_ID }}}}
          aws-secret-access-key: ${{{{ secrets.PROD_SECRET_ACCESS_KEY }}}}
"""
    ).graph

    result = build_findings(graph)

    assert by_rule(result.findings, "NHB-GHA-003")[0].severity is Severity.INFO
    assert by_rule(result.findings, "NHB-GHA-004")[0].severity is Severity.MEDIUM
    literal = by_rule(result.findings, "NHB-GHA-005")
    assert len(literal) == 1
    assert literal[0].severity is Severity.HIGH
    assert f"{len(token)} chars" in literal[0].message
    assert token not in str(result)
    static = by_rule(result.findings, "NHB-CRED-001")
    assert len(static) == 2
    assert all(finding.severity is Severity.MEDIUM for finding in static)


def test_untrusted_checkout_is_critical_when_a_role_is_reachable(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx12-untrusted-checkout").graph
    current = scenario(graph, "fork-pr")

    findings = build_findings(graph, scenarios=(current,)).findings

    untrusted = by_rule(findings, "NHB-GHA-002")
    assert len(untrusted) == 2
    assert sorted(finding.severity for finding in untrusted) == [
        Severity.CRITICAL,
        Severity.HIGH,
    ]
    assert all(finding.path for finding in untrusted)


def test_mutable_entrypoint_reports_reachable_role_sink_modification(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    sink_id = "aws:secret:prod/db-master"
    proof = Evidence(
        cls=EvidenceClass.DERIVED,
        rule="R13.can_modify",
        file="tfstate.json",
        line=37,
        detail="fixture policy allows PutSecretValue",
    )
    modify = Edge(
        id=edge_id(EdgeKind.CAN_MODIFY.value, ROLE_DEPLOY, sink_id, (proof,)),
        kind=EdgeKind.CAN_MODIFY,
        src=ROLE_DEPLOY,
        dst=sink_id,
        confidence=EvidenceClass.DERIVED,
        evidence=(proof,),
    )
    graph = graph.model_copy(
        update={"edges": tuple(sorted((*graph.edges, modify), key=Edge.sort_key))}
    )
    current = scenario(graph, "action:tj-actions/changed-files@v45")

    findings = build_findings(graph, scenarios=(current,)).findings

    modifying = by_rule(findings, "NHB-ROT-002")
    assert len(modifying) == 1
    assert modifying[0].severity is Severity.MEDIUM
    assert modifying[0].path[-1] == sink_id
    assert modifying[0].path_edges[-1] == modify.id


def test_ignore_filters_rules_and_paths_with_strict_diagnostics(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    findings = build_findings(graph).findings
    config = Config(
        ignore_rules=("NHB-OIDC-005",),
        ignore_paths=("tfstate.json",),
    )

    ignored = filter_findings(findings, config=config, strict=True)

    assert by_rule(ignored.findings, "NHB-OIDC-002") == []
    assert by_rule(ignored.findings, "NHB-OIDC-005") == []
    assert by_rule(ignored.findings, "NHB-GHA-001")
    assert len(ignored.diagnostics) == 2
    assert all(item.level is DiagnosticLevel.INFO for item in ignored.diagnostics)
    assert all(item.code == "D-FINDING-IGNORED" for item in ignored.diagnostics)
    assert filter_findings(findings, config=config).diagnostics == ()


def test_findings_are_deduplicated_and_deterministic(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    current = scenario(graph, "action:tj-actions/changed-files@v45")

    first = build_findings(graph, scenarios=(current, current))
    second = build_findings(graph, scenarios=(current,))

    assert first == second
    assert len({finding.id for finding in first.findings}) == len(first.findings)
    assert list(first.findings) == sorted(first.findings, key=lambda finding: finding.sort_key())
