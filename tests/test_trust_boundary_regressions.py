"""Statement-local trust controls, provenance and synthetic writer boundaries."""

from __future__ import annotations

import pytest

from nhi_blast.analysis.findings import build_findings
from nhi_blast.analysis.scenario import analyze_scenario
from nhi_blast.analysis.selectors import parse_selector, resolve_starts
from nhi_blast.aws.trust import (
    evaluate_trust_statements,
    no_match_evaluation,
    trust_subject_filter,
)
from nhi_blast.core.data import condition_keys
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    Breadth,
    EdgeKind,
    GraphData,
    PolicyContext,
    PolicyEffect,
    RoleFact,
    Severity,
    SubFormat,
)
from nhi_blast.discovery.repo import RepoIdentity
from nhi_blast.graph.builder import GraphInputs, build_graph
from nhi_blast.oidc.solver import evaluate_trust
from nhi_blast.parsers.gha.workflow import parse_workflow
from nhi_blast.resolvers.composite import expand_jobs
from nhi_blast.resolvers.roles import CloudFacts
from tests.support import candidate, evidence, role, statement

REGISTRY = condition_keys()
SUB_MAIN = "repo:acme/shop:ref:refs/heads/main"
SUB_FEATURE = "repo:acme/shop:ref:refs/heads/feature"
WORKFLOW = """on:
  push:
    branches: [main]
permissions:
  id-token: write
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: 'true'
"""


def _graph(text: str, trust: RoleFact) -> GraphData:
    limits = Limits()
    parsed = parse_workflow(".github/workflows/test.yml", text, limits=limits)
    assert parsed.facts is not None
    workflows = (parsed.facts,)
    return build_graph(
        GraphInputs(
            repository=RepoIdentity(
                slug="acme/shop",
                source="--repo-slug",
                default_branch="main",
                sub_format=SubFormat.CLASSIC,
            ),
            workflows=workflows,
            expanded_jobs=expand_jobs(workflows, {}, limits=limits),
            cloud=CloudFacts(
                roles=(trust,),
                sinks=(),
                providers=(),
                externals=(),
                policy_context=PolicyContext(),
                diagnostics=(),
            ),
        )
    ).graph


def test_alternative_allows_cannot_supply_each_others_controls() -> None:
    trust = role(
        statements=(
            statement(conditions={"StringEquals": {"aud": ("sts.amazonaws.com",)}}),
            statement(conditions={"StringEquals": {"sub": (SUB_MAIN,)}}),
        )
    )
    match = evaluate_trust(trust, (candidate(SUB_MAIN),))
    assert match is not None
    assert match.missing_audience
    assert match.unconstrained
    assert match.breadth is Breadth.UNCONSTRAINED

    graph = _graph(WORKFLOW, trust)
    rules = {finding.rule for finding in build_findings(graph).findings}
    assert {"NHB-OIDC-001", "NHB-OIDC-004"} <= rules


@pytest.mark.parametrize("claim", ["aud", "sub", "job_workflow_ref"])
@pytest.mark.parametrize(
    ("operator", "values"),
    [
        ("Null", ("false",)),
        ("StringNotEquals", ("excluded",)),
        ("StringNotLike", ("excluded*",)),
        ("Bool", ("false",)),
        ("NumericEquals", ("1",)),
    ],
)
def test_nonpositive_conditions_do_not_supply_string_controls(
    claim: str, operator: str, values: tuple[str, ...]
) -> None:
    controls = {"aud": ("sts.amazonaws.com",), "sub": (SUB_MAIN,)}
    controls.pop("sub" if claim == "job_workflow_ref" else claim)
    trust = role(
        statements=(statement(conditions={"StringEquals": controls, operator: {claim: values}}),)
    )
    match = evaluate_trust(
        trust,
        (candidate(SUB_MAIN, claims={"job_workflow_ref": "acme/shop/ci.yml@refs/heads/main"}),),
    )
    assert match is not None
    assert match.missing_audience is (claim == "aud")
    assert match.unconstrained is (claim != "aud")


@pytest.mark.parametrize("operator", ["StringEquals", "ForAnyValue:StringLikeIfExists"])
def test_positive_binding_still_counts_alongside_presence_check(operator: str) -> None:
    trust = role(
        statements=(
            statement(
                conditions={
                    operator: {"aud": ("sts.amazonaws.com",), "sub": (SUB_MAIN,)},
                    "Null": {"aud": ("false",), "sub": ("false",)},
                }
            ),
        )
    )
    match = evaluate_trust(trust, (candidate(SUB_MAIN),))
    assert match is not None
    assert not match.missing_audience
    assert not match.unconstrained
    assert match.breadth is Breadth.EXACT_REF


def test_deny_and_unrelated_statements_do_not_supply_or_remove_controls() -> None:
    complete = {"StringEquals": {"aud": ("sts.amazonaws.com",), "sub": (SUB_MAIN,)}}
    irrelevant = (
        statement(effect=PolicyEffect.DENY),
        statement(actions=("sts:AssumeRole",)),
        statement(principals={"Federated": ("arn:aws:iam::1:oidc-provider/other.example",)}),
    )
    safe = role(statements=(statement(conditions=complete), *irrelevant))
    match = evaluate_trust(safe, (candidate(SUB_MAIN),))
    assert match is not None
    assert not match.missing_audience
    assert not match.unconstrained
    unsafe = role(
        statements=(statement(), statement(effect=PolicyEffect.DENY, conditions=complete))
    )
    match = evaluate_trust(unsafe, (candidate(SUB_MAIN),))
    assert match is not None
    assert match.missing_audience
    assert match.unconstrained


@pytest.mark.parametrize("empty_candidates", [False, True])
def test_no_match_audit_checks_each_allow_and_matches_fastpath(empty_candidates: bool) -> None:
    trust = role(
        statements=(
            statement(
                conditions={"StringEquals": {"aud": ("sts.amazonaws.com",), "sub": (SUB_FEATURE,)}}
            ),
            statement(
                conditions={"StringEquals": {"sub": (SUB_FEATURE,), "head_ref": ("feature",)}}
            ),
        )
    )
    candidates = () if empty_candidates else (candidate(SUB_MAIN),)
    assert not trust_subject_filter(trust, REGISTRY).may_match(candidates)
    direct = evaluate_trust_statements(trust, candidates, registry=REGISTRY)
    assert direct.matches == ()
    assert direct.missing_audience
    assert direct.dead_keys == ("head_ref",)
    assert direct == no_match_evaluation(trust, REGISTRY)


def test_unmatched_allow_still_has_its_own_missing_control_audit() -> None:
    trust = role(
        statements=(statement(conditions={"StringEquals": {"aud": ("custom-audience",)}}),)
    )
    direct = evaluate_trust_statements(trust, (candidate(SUB_MAIN),), registry=REGISTRY)
    assert direct.matches == ()
    assert direct.unconstrained
    assert not direct.missing_audience
    assert direct == no_match_evaluation(trust, REGISTRY)


@pytest.mark.parametrize(
    "cls", [EvidenceClass.DECLARED, EvidenceClass.ASSUMED, EvidenceClass.UNKNOWN]
)
def test_solver_keeps_matched_statement_locations_once(cls: EvidenceClass) -> None:
    location = evidence(cls, rule="IAM.statement", file="trust.json", line=37)
    excluded = evidence(EvidenceClass.DECLARED, rule="IAM.statement", file="trust.json", line=99)
    allow = statement(conditions={"StringEquals": {"aud": ("sts.amazonaws.com",)}})
    allow = allow.model_copy(update={"evidence": (location, location)})
    deny = statement(effect=PolicyEffect.DENY).model_copy(update={"evidence": (excluded,)})
    trust = role(statements=(allow, deny))
    candidates = (
        candidate(SUB_MAIN),
        candidate("repo:acme@*/shop@*:ref:refs/heads/main", fmt=SubFormat.IMMUTABLE),
    )
    match = evaluate_trust(trust, candidates)
    assert match is not None
    expected_confidence = EvidenceClass.DERIVED if cls is EvidenceClass.DECLARED else cls
    assert match.confidence is expected_confidence
    assert match.evidence.count(location) == 1
    assert excluded not in match.evidence
    assert len({item.key for item in match.evidence}) == len(match.evidence)
    graph = _graph(WORKFLOW, trust)
    assume = next(edge for edge in graph.edges if edge.kind is EdgeKind.CAN_ASSUME)
    assert assume.evidence.count(location) == 1
    assert assume.confidence is expected_confidence
    finding = next(item for item in build_findings(graph).findings if item.rule == "NHB-OIDC-001")
    assert location in finding.evidence


@pytest.mark.parametrize("cls", [EvidenceClass.ASSUMED, EvidenceClass.UNKNOWN])
def test_nonmatching_allow_does_not_taint_matched_statement_evidence(cls: EvidenceClass) -> None:
    matched_location = evidence(
        EvidenceClass.DECLARED, rule="IAM.statement", file="trust.json", line=37
    )
    excluded_location = evidence(cls, rule="IAM.statement", file="trust.json", line=99)
    allow = statement(
        conditions={"StringEquals": {"aud": ("sts.amazonaws.com",), "sub": (SUB_MAIN,)}}
    ).model_copy(update={"evidence": (matched_location,)})
    excluded = statement(
        conditions={"StringEquals": {"aud": ("other-audience",), "sub": (SUB_MAIN,)}}
    ).model_copy(update={"evidence": (excluded_location,)})
    trust = role(statements=(allow, excluded))

    match = evaluate_trust(trust, (candidate(SUB_MAIN),))
    assert match is not None
    assert match.confidence is EvidenceClass.DERIVED
    assert matched_location in match.evidence
    assert excluded_location not in match.evidence
    graph = _graph(WORKFLOW, trust)
    assume = next(edge for edge in graph.edges if edge.kind is EdgeKind.CAN_ASSUME)
    assert assume.confidence is EvidenceClass.DERIVED
    assert matched_location in assume.evidence
    assert excluded_location not in assume.evidence


def test_nonmatching_unconstrained_allow_does_not_broaden_matched_edge() -> None:
    matched_location = evidence(
        EvidenceClass.DECLARED, rule="IAM.statement", file="trust.json", line=10
    )
    audit_location = evidence(
        EvidenceClass.UNKNOWN, rule="IAM.statement", file="trust.json", line=20
    )
    narrow = statement(
        conditions={"StringEquals": {"aud": ("sts.amazonaws.com",), "sub": (SUB_MAIN,)}}
    ).model_copy(update={"evidence": (matched_location,)})
    unrelated = statement(conditions={"StringEquals": {"aud": ("other-audience",)}}).model_copy(
        update={"evidence": (audit_location,)}
    )
    trust = role(statements=(narrow, unrelated))

    match = evaluate_trust(trust, (candidate(SUB_MAIN),))
    assert match is not None
    assert not match.unconstrained
    assert not match.missing_audience
    assert match.breadth is Breadth.EXACT_REF
    assert match.confidence is EvidenceClass.DERIVED
    assert audit_location not in match.evidence

    graph = _graph(WORKFLOW, trust)
    assume = next(edge for edge in graph.edges if edge.kind is EdgeKind.CAN_ASSUME)
    assert assume.attrs["unconstrained"] is False
    assert assume.attrs["breadth"] == "EXACT_REF"
    assert assume.confidence is EvidenceClass.DERIVED
    assert audit_location not in assume.evidence
    audit = [item for item in build_findings(graph).findings if item.rule == "NHB-OIDC-001"]
    assert len(audit) == 1
    assert audit[0].severity is Severity.CRITICAL
    assert audit[0].confidence is EvidenceClass.UNKNOWN
    assert audit_location in audit[0].evidence


def test_nonmatching_allow_audits_keep_their_own_missing_controls() -> None:
    matched_location = evidence(
        EvidenceClass.DECLARED, rule="IAM.statement", file="trust.json", line=10
    )
    audit_location = evidence(
        EvidenceClass.UNKNOWN, rule="IAM.statement", file="trust.json", line=20
    )
    narrow = statement(
        conditions={"StringEquals": {"aud": ("sts.amazonaws.com",), "sub": (SUB_MAIN,)}}
    ).model_copy(update={"evidence": (matched_location,)})
    unrelated = statement(
        conditions={
            "StringEquals": {"sub": (SUB_FEATURE,), "repository_owner": ("acme",)},
        }
    ).model_copy(update={"evidence": (audit_location,)})
    trust = role(statements=(narrow, unrelated))

    match = evaluate_trust(trust, (candidate(SUB_MAIN),))
    assert match is not None
    assert not match.missing_audience
    assert not match.unconstrained
    assert match.dead_condition_keys == ()
    assert match.breadth is Breadth.EXACT_REF

    graph = _graph(WORKFLOW, trust)
    assume = next(edge for edge in graph.edges if edge.kind is EdgeKind.CAN_ASSUME)
    assert assume.attrs["missing_audience"] is False
    assert assume.attrs["dead_condition_keys"] == []
    findings = build_findings(graph).findings
    audience = [item for item in findings if item.rule == "NHB-OIDC-004"]
    assert len(audience) == 1
    assert audience[0].severity is Severity.MEDIUM
    assert audience[0].confidence is EvidenceClass.UNKNOWN
    assert audit_location in audience[0].evidence
    dead = [item for item in findings if item.rule == "NHB-OIDC-006"]
    assert len(dead) == 1
    assert dead[0].confidence is EvidenceClass.UNKNOWN
    assert audit_location in dead[0].evidence
    assert matched_location not in dead[0].evidence


def test_repo_writer_does_not_promote_unknown_trust_evidence() -> None:
    unknown = evidence(EvidenceClass.UNKNOWN, rule="IAM.statement", file="trust.json", line=37)
    allow = statement(conditions={"StringEquals": {"sub": (SUB_FEATURE,)}})
    trust = role(statements=(allow.model_copy(update={"evidence": (unknown,)}),))
    graph = _graph(WORKFLOW.replace("id-token: write", "contents: read"), trust)
    starts = resolve_starts(parse_selector("repo-write"), graph, jobs=())
    result = analyze_scenario(graph, starts, selector="repo-write", selector_kind="repo-write")
    assert trust.id not in result.reach
    assert result.partition.E == ()


@pytest.mark.parametrize("oidc_enabled", [False, True])
@pytest.mark.parametrize(
    "binding",
    [
        {"sub": (SUB_FEATURE,)},
        {"sub": ("repo:acme@123/shop@456:ref:refs/heads/feature",)},
        {"sub": ("repo:acme/shop:ref:refs/heads/feature?",)},
        {"sub": ("repo:acme/shop:*",), "ref": ("refs/heads/feature",)},
        {"job_workflow_ref": ("acme/shop/.github/workflows/new.yml@refs/heads/feature",)},
    ],
)
def test_repo_writer_reaches_feature_branch_without_broadening_jobs(
    binding: dict[str, tuple[str, ...]], *, oidc_enabled: bool
) -> None:
    trust = role(
        statements=(
            statement(conditions={"StringEquals": {"aud": ("sts.amazonaws.com",), **binding}}),
        )
    )
    text = WORKFLOW if oidc_enabled else WORKFLOW.replace("id-token: write", "contents: read")
    graph = _graph(text, trust)
    assert not any(edge.kind is EdgeKind.CAN_ASSUME for edge in graph.edges)
    starts = resolve_starts(parse_selector("repo-write"), graph, jobs=())
    result = analyze_scenario(graph, starts, selector="repo-write", selector_kind="repo-write")
    assert trust.id in result.reach
    assert result.reach[trust.id].weakest is EvidenceClass.ASSUMED
    assert len(result.partition.E) == 1
    job_selector = "job:.github/workflows/test.yml#test"
    job_starts = resolve_starts(parse_selector(job_selector), graph, jobs=())
    ordinary = analyze_scenario(graph, job_starts, selector=job_selector, selector_kind="job")
    assert trust.id not in ordinary.reach
    assert ordinary.partition.E == ()


@pytest.mark.parametrize("oidc_enabled", [False, True])
@pytest.mark.parametrize(
    "binding",
    [
        {"sub": ("repo:other/shop:ref:refs/heads/feature",)},
        {"sub": ("repo:acme/other:ref:refs/heads/feature",)},
        {"sub": ("repo:acme/shop:ref:refs/tags/v1",)},
        {"sub": ("repo:acme/shop:environment:prod",)},
        {"sub": ("repo:acme/shop:pull_request",)},
        {"job_workflow_ref": ("other/shop/.github/workflows/deploy.yml@refs/heads/main",)},
        {"job_workflow_ref": ("acme/shop/.github/workflows/deploy.yml@refs/tags/v1",)},
    ],
)
def test_repo_writer_does_not_accept_other_repositories_or_contexts(
    binding: dict[str, tuple[str, ...]], *, oidc_enabled: bool
) -> None:
    trust = role(
        statements=(
            statement(conditions={"StringEquals": {"aud": ("sts.amazonaws.com",), **binding}}),
        )
    )
    text = WORKFLOW if oidc_enabled else WORKFLOW.replace("id-token: write", "contents: read")
    graph = _graph(text, trust)
    assert not any(edge.kind is EdgeKind.CAN_ASSUME for edge in graph.edges)
    starts = resolve_starts(parse_selector("repo-write"), graph, jobs=())
    result = analyze_scenario(graph, starts, selector="repo-write", selector_kind="repo-write")
    assert trust.id not in result.reach
    assert result.partition.E == ()
