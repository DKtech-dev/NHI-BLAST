"""Regression tests for Loop 6 Team B fixes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from typer.testing import CliRunner

from nhi_blast.analysis.findings import build_findings
from nhi_blast.analysis.partition import partition_graph
from nhi_blast.analysis.rotation import plan_rotation
from nhi_blast.aws.policy_eval import PolicyContext
from nhi_blast.cli.app import app
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
    RoleFact,
    Statement,
    SubFormat,
)
from nhi_blast.discovery.repo import RepoIdentity
from nhi_blast.graph.builder import GraphInputs, build_graph
from nhi_blast.graph.store import GraphStore
from nhi_blast.parsers.gha.workflow import _has_unconstrained_pkg_install, parse_workflow
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.sarif import SCENARIO_RULES as SARIF_SCENARIO_RULES
from nhi_blast.resolvers.composite import ExpandedJob, ExpandedStep
from nhi_blast.resolvers.roles import CloudFacts
from nhi_blast.whatif.plan import RemoveTrust, RevokeRoleSessions, synthesize_auto_plan

PROJECT = Path(__file__).resolve().parents[1]
CHAIN_FIXTURE = PROJECT / "tests" / "fixtures" / "labelled" / "chain-sts-assume-role"


def _ev(rule: str = "TEST", cls: EvidenceClass = EvidenceClass.DECLARED) -> tuple[Evidence, ...]:
    return (Evidence(cls=cls, rule=rule, file="test.tf", line=1, detail=rule),)


def _add_node(
    store: GraphStore,
    node_id: str,
    kind: NodeKind,
    *,
    label: str | None = None,
    attrs: dict[str, object] | None = None,
    rule: str = "TEST",
) -> None:
    store.add_node(
        Node(
            id=node_id,
            kind=kind,
            label=label or node_id,
            attrs=attrs or {},
            evidence=_ev(rule),
        )
    )


def _add_edge(
    store: GraphStore,
    kind: EdgeKind,
    src: str,
    dst: str,
    *,
    lifetime: Lifetime = Lifetime.NA,
    attrs: dict[str, object] | None = None,
    rule: str = "TEST",
) -> str:
    ev = _ev(rule)
    eid = edge_id(kind.value, src, dst, ev)
    store.add_edge(
        Edge(
            id=eid,
            kind=kind,
            src=src,
            dst=dst,
            lifetime=lifetime,
            confidence=EvidenceClass.DECLARED,
            evidence=ev,
            attrs=attrs or {},
        )
    )
    return eid


# ---------------------------------------------------------------------------
# 1. graph/builder.py: _r8_role_chaining STS_SESSION node + partition.E + whatif
# ---------------------------------------------------------------------------


def test_role_chaining_creates_sts_session_node_in_partition_e_and_whatif() -> None:
    outcome = run_scan(
        ScanOptions(
            root=CHAIN_FIXTURE,
            repo_slug="acme/shop",
            selectors=("job:.github/workflows/build.yml#deploy",),
        )
    )
    graph = outcome.report.graph
    nodes = {n.id: n for n in graph.nodes}

    chained_edges = [
        e for e in graph.edges if e.kind is EdgeKind.CAN_ASSUME and e.attrs.get("chained") is True
    ]
    assert len(chained_edges) == 1
    chained_edge = chained_edges[0]

    session_id = chained_edge.attrs.get("session_credential")
    assert isinstance(session_id, str)
    assert session_id in nodes
    session_node = nodes[session_id]
    assert session_node.kind is NodeKind.CREDENTIAL
    assert session_node.attrs["credential_kind"] == "STS_SESSION"
    assert session_node.attrs["chained"] is True
    assert session_node.attrs["role"] == chained_edge.dst
    assert session_node.attrs["ttl_seconds"] == 3600

    # Partition E includes the chained STS session credential
    assert len(outcome.report.scenarios) == 1
    e_creds = {item.credential for item in outcome.report.scenarios[0].partition.E}
    assert session_id in e_creds

    # whatif --auto-plan handles the chained target role identically to OIDC roles
    plan = synthesize_auto_plan(outcome.report)
    removed_edges = {
        entry.intervention.edge
        for entry in plan.entries
        if isinstance(entry.intervention, RemoveTrust)
    }
    revoked_roles = {
        entry.intervention.role
        for entry in plan.entries
        if isinstance(entry.intervention, RevokeRoleSessions)
    }
    assert chained_edge.id in removed_edges
    assert chained_edge.dst in revoked_roles


def test_role_chaining_respects_lower_dst_max_session_duration() -> None:
    src_arn = "arn:aws:iam::111122223333:role/src-role"
    dst_arn = "arn:aws:iam::111122223333:role/dst-role"
    src_role = RoleFact(
        id=f"aws:role:{src_arn}",
        address="aws_iam_role.src",
        name="src-role",
        arn=src_arn,
        inline_statements=(
            Statement(
                effect="Allow",
                actions=("sts:AssumeRole",),
                resources=(dst_arn,),
                evidence=_ev("IAM.inline"),
            ),
        ),
        evidence=_ev("TF.role"),
    )
    dst_role = RoleFact(
        id=f"aws:role:{dst_arn}",
        address="aws_iam_role.dst",
        name="dst-role",
        arn=dst_arn,
        max_session_duration=1800,
        trust_statements=(
            Statement(
                effect="Allow",
                actions=("sts:AssumeRole",),
                principals={"AWS": (src_arn,)},
                evidence=_ev("IAM.trust"),
            ),
        ),
        evidence=_ev("TF.role"),
    )
    built = build_graph(
        GraphInputs(
            repository=RepoIdentity(
                slug="acme/shop",
                source="test",
                default_branch="main",
                sub_format=SubFormat.CLASSIC,
            ),
            workflows=(),
            expanded_jobs=(),
            cloud=CloudFacts(
                roles=(src_role, dst_role),
                sinks=(),
                providers=(),
                externals=(),
                policy_context=PolicyContext(),
                diagnostics=(),
            ),
        )
    )
    nodes = {n.id: n for n in built.graph.nodes}
    chained_edges = [
        e
        for e in built.graph.edges
        if e.kind is EdgeKind.CAN_ASSUME and e.attrs.get("chained") is True
    ]
    assert len(chained_edges) == 1
    session_id = str(chained_edges[0].attrs["session_credential"])
    assert nodes[session_id].attrs["ttl_seconds"] == 1800
    assert chained_edges[0].attrs["ttl_seconds"] == 1800


# ---------------------------------------------------------------------------
# 2. analysis/rotation.py: CAN_ASSUME dependency order + Cloud Persistence Audit
# ---------------------------------------------------------------------------


def test_rotation_orders_chained_role_dependencies() -> None:
    store = GraphStore()
    _add_node(
        store,
        "cred:c1",
        NodeKind.CREDENTIAL,
        label="c1",
        attrs={
            "credential_kind": "AWS_ACCESS_KEY",
            "lifetime": Lifetime.PERSISTENT.value,
            "criticality": 50,
        },
    )
    _add_node(store, "aws:role:a", NodeKind.AWS_ROLE, label="role-a")
    _add_node(store, "aws:role:b", NodeKind.AWS_ROLE, label="role-b")
    _add_node(store, "aws:secret:s2", NodeKind.SINK, label="s2")
    _add_node(
        store,
        "cred:c2",
        NodeKind.CREDENTIAL,
        label="c2",
        attrs={
            "credential_kind": "DATABASE_PASSWORD",
            "lifetime": Lifetime.PERSISTENT.value,
            "criticality": 100,
        },
    )
    _add_edge(store, EdgeKind.AUTHENTICATES_AS, "cred:c1", "aws:role:a", rule="AUTH.c1")
    _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "aws:role:a",
        "aws:role:b",
        lifetime=Lifetime.SESSION_TTL,
        attrs={"chained": True},
        rule="R8.role-chaining",
    )
    _add_edge(store, EdgeKind.CAN_READ_VALUE, "aws:role:b", "aws:secret:s2", rule="R9.read")
    _add_edge(
        store,
        EdgeKind.STORES,
        "aws:secret:s2",
        "cred:c2",
        lifetime=Lifetime.PERSISTENT,
        rule="R10.stores",
    )

    graph = store.data()
    part = partition_graph(graph, ("cred:c1",))
    plan = plan_rotation(graph, part.partition, selector_kind="secret", start_nodes=("cred:c1",))

    assert len(plan.rotation) == 2
    assert [step.credentials[0].id for step in plan.rotation] == ["cred:c1", "cred:c2"]
    assert plan.rotation[0].generation == 0
    assert plan.rotation[1].generation == 1
    assert plan.rotation[1].depends_on == ("cred:c1",)
    assert any(ev.rule == "R8.role-chaining" for ev in plan.rotation[0].evidence)


def test_rotation_persistence_audit_sequential_order_and_evidence() -> None:
    store = GraphStore()
    _add_node(store, "job:ci#deploy", NodeKind.JOB, label="deploy")
    _add_node(store, "oidc:ci#deploy", NodeKind.OIDC_IDENTITY)
    _add_node(
        store,
        "aws:role:persist",
        NodeKind.AWS_ROLE,
        label="persist-role",
        attrs={"persistence_actions": ["iam:CreateAccessKey"]},
        rule="TF.persist-role",
    )
    _add_node(
        store,
        "cred:sts:persist",
        NodeKind.CREDENTIAL,
        label="STS session",
        attrs={
            "credential_kind": "STS_SESSION",
            "lifetime": Lifetime.SESSION_TTL.value,
            "role": "aws:role:persist",
            "ttl_seconds": 3600,
        },
    )
    _add_node(store, "aws:secret:db", NodeKind.SINK, label="db")
    _add_node(
        store,
        "cred:db",
        NodeKind.CREDENTIAL,
        label="db",
        attrs={
            "credential_kind": "DATABASE_PASSWORD",
            "lifetime": Lifetime.PERSISTENT.value,
            "criticality": 100,
        },
    )
    _add_edge(store, EdgeKind.CAN_MINT, "job:ci#deploy", "oidc:ci#deploy")
    _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:ci#deploy",
        "aws:role:persist",
        lifetime=Lifetime.SESSION_TTL,
        attrs={"session_credential": "cred:sts:persist"},
    )
    _add_edge(store, EdgeKind.CAN_READ_VALUE, "aws:role:persist", "aws:secret:db")
    _add_edge(store, EdgeKind.STORES, "aws:secret:db", "cred:db", lifetime=Lifetime.PERSISTENT)

    graph = store.data()
    part = partition_graph(graph, ("job:ci#deploy",))
    plan = plan_rotation(graph, part.partition, selector_kind="job", start_nodes=("job:ci#deploy",))

    all_orders = [
        *(s.order for s in plan.containment),
        *(s.order for s in plan.rotation),
        *(s.order for s in plan.verify),
    ]
    assert all_orders == list(range(len(all_orders)))
    audit_step = next(
        s for s in plan.verify if any("Cloud Persistence Audit" in a for a in s.actions)
    )
    assert audit_step.evidence
    assert any(ev.rule == "TF.persist-role" for ev in audit_step.evidence)

    # Also verify sequential order when partition.E and partition.Z are empty (no CloudTrail verify)
    empty_part = partition_graph(
        GraphData(
            nodes=(
                Node(
                    id="aws:role:persist",
                    kind=NodeKind.AWS_ROLE,
                    label="persist-role",
                    attrs={"persistence_actions": ["iam:CreateAccessKey"]},
                    evidence=_ev("TF.persist-role"),
                ),
            ),
            edges=(),
        ),
        ("aws:role:persist",),
    )
    empty_plan = plan_rotation(
        GraphData(
            nodes=(
                Node(
                    id="aws:role:persist",
                    kind=NodeKind.AWS_ROLE,
                    label="persist-role",
                    attrs={"persistence_actions": ["iam:CreateAccessKey"]},
                    evidence=_ev("TF.persist-role"),
                ),
            ),
            edges=(),
        ),
        empty_part.partition,
        selector_kind="role",
        start_nodes=("aws:role:persist",),
    )
    empty_orders = [
        *(s.order for s in empty_plan.containment),
        *(s.order for s in empty_plan.rotation),
        *(s.order for s in empty_plan.verify),
    ]
    assert empty_orders == [0, 1]


# ---------------------------------------------------------------------------
# 3. analysis/findings.py: NHB-CHAIN-001 reachability gate + NHB-PERSIST-001 path
# ---------------------------------------------------------------------------


def test_findings_chain_gated_on_job_reachability_and_persist_full_path() -> None:
    store = GraphStore()
    _add_node(
        store, "job:wf#build", NodeKind.JOB, label="build", attrs={"trigger_events": ["push"]}
    )
    _add_node(store, "oidc:wf#build", NodeKind.OIDC_IDENTITY)
    _add_node(
        store,
        "aws:role:reachable",
        NodeKind.AWS_ROLE,
        label="reachable-role",
        attrs={"persistence_actions": ["iam:CreateAccessKey"]},
    )
    # Unreachable chained roles (not connected to any JOB)
    _add_node(store, "aws:role:orphan-src", NodeKind.AWS_ROLE, label="orphan-src")
    _add_node(store, "aws:role:orphan-dst", NodeKind.AWS_ROLE, label="orphan-dst")

    e_mint = _add_edge(store, EdgeKind.CAN_MINT, "job:wf#build", "oidc:wf#build")
    e_assume = _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:wf#build",
        "aws:role:reachable",
        lifetime=Lifetime.SESSION_TTL,
    )
    _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "aws:role:orphan-src",
        "aws:role:orphan-dst",
        lifetime=Lifetime.SESSION_TTL,
        attrs={"chained": True},
    )

    built = build_findings(store.data())
    rules = {f.rule for f in built.findings}
    assert "NHB-CHAIN-001" not in rules
    assert "NHB-PERSIST-001" in rules

    persist = next(f for f in built.findings if f.rule == "NHB-PERSIST-001")
    assert persist.path == ("job:wf#build", "oidc:wf#build", "aws:role:reachable")
    assert persist.path_edges == (e_mint, e_assume)


# ---------------------------------------------------------------------------
# 4. parsers/gha/workflow.py: ecosystem-aware pkg install + has_prt
# ---------------------------------------------------------------------------


def test_pkg_install_exemptions_are_ecosystem_aware() -> None:
    # JS installers: --ignore-scripts / --no-scripts exempt; Python flags do NOT exempt
    assert _has_unconstrained_pkg_install("npm ci --ignore-scripts") is False
    assert _has_unconstrained_pkg_install("pnpm i --ignore-scripts") is False
    assert _has_unconstrained_pkg_install("bun install --ignore-scripts") is False
    assert _has_unconstrained_pkg_install("yarn install --no-scripts") is False
    assert _has_unconstrained_pkg_install("bun install") is True
    assert _has_unconstrained_pkg_install("npm ci --locked") is True
    assert _has_unconstrained_pkg_install("npm install --require-hashes") is True

    # Python installers: Python flags exempt; --ignore-scripts does NOT exempt
    assert _has_unconstrained_pkg_install("pip install --only-binary=:all: requests") is False
    assert _has_unconstrained_pkg_install("pip install --only-binary :all: requests") is False
    assert _has_unconstrained_pkg_install("pip install --require-hashes -r reqs.txt") is False
    assert _has_unconstrained_pkg_install("pip install --no-build-isolation .") is False
    assert _has_unconstrained_pkg_install("uv sync --locked") is False
    assert _has_unconstrained_pkg_install("poetry install --locked") is False
    assert _has_unconstrained_pkg_install("poetry install --no-scripts") is False
    assert _has_unconstrained_pkg_install("pip install requests --ignore-scripts") is True
    assert _has_unconstrained_pkg_install("uv pip install requests --ignore-scripts") is True

    # Multi-command run block checks each command independently
    assert _has_unconstrained_pkg_install("npm ci --ignore-scripts && pip install requests") is True
    assert (
        _has_unconstrained_pkg_install(
            "npm ci --ignore-scripts && pip install --only-binary=:all: requests"
        )
        is False
    )


def test_workflow_run_with_plain_cache_does_not_trigger_untrusted_checkout() -> None:
    wf_run_yaml = """
name: Post CI
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
permissions:
  id-token: write
jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/cache@v4
        with:
          path: ~/.cache
          key: cache-key
      - run: echo "done"
"""
    parsed = parse_workflow(".github/workflows/post-ci.yml", wf_run_yaml, limits=Limits())
    assert parsed.facts is not None
    assert parsed.facts.jobs["report"].untrusted_checkout is False

    job = parsed.facts.jobs["report"]
    expanded = ExpandedJob(
        workflow=parsed.facts,
        job=job,
        refs=job.refs,
        steps=tuple(ExpandedStep(step=s) for s in job.steps),
        diagnostics=(),
    )
    built = build_graph(
        GraphInputs(
            repository=RepoIdentity(
                slug="acme/shop",
                source="test",
                default_branch="main",
                sub_format=SubFormat.CLASSIC,
            ),
            workflows=(parsed.facts,),
            expanded_jobs=(expanded,),
            cloud=CloudFacts(
                roles=(),
                sinks=(),
                providers=(),
                externals=(),
                policy_context=PolicyContext(),
                diagnostics=(),
            ),
        )
    )
    assert "NHB-GHA-002" not in {f.rule for f in build_findings(built.graph).findings}

    # pull_request_target with actions/cache@v4 STILL triggers untrusted_checkout
    prt_yaml = wf_run_yaml.replace(
        'workflow_run:\n    workflows: ["CI"]\n    types: [completed]',
        "pull_request_target:",
    )
    prt_parsed = parse_workflow(".github/workflows/prt.yml", prt_yaml, limits=Limits())
    assert prt_parsed.facts is not None
    assert prt_parsed.facts.jobs["report"].untrusted_checkout is True


# ---------------------------------------------------------------------------
# 5. cli/commands.py: init_config uses read_git_origin_slug
# ---------------------------------------------------------------------------


def test_init_config_scopes_to_origin_remote_and_rejects_escaping_symlink(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "config").write_text(
        '[remote "upstream"]\n'
        "\turl = https://github.com/other/upstream-repo.git\n"
        '[remote "origin"]\n'
        "\turl = git@github.com:acme/real-origin.git\n",
        encoding="utf-8",
    )
    runner = CliRunner()
    res = runner.invoke(app, ["init", str(repo)])
    assert res.exit_code == 0, res.output
    assert 'repo_slug = "acme/real-origin"' in (repo / "nhi-blast.toml").read_text(encoding="utf-8")

    # Escaping symlink for .git/config falls back to OWNER/REPO
    outside = tmp_path / "outside-git-config"
    outside.write_text(
        '[remote "origin"]\n\turl = https://github.com/evil/escaped.git\n',
        encoding="utf-8",
    )
    repo_sym = tmp_path / "repo-sym"
    (repo_sym / ".git").mkdir(parents=True)
    (repo_sym / ".git" / "config").symlink_to(outside)
    res_sym = runner.invoke(app, ["init", str(repo_sym)])
    assert res_sym.exit_code == 0, res_sym.output
    assert 'repo_slug = "OWNER/REPO"' in (repo_sym / "nhi-blast.toml").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 6. scripts/benchmark_corpus.py: imports SCENARIO_RULES from sarif
# ---------------------------------------------------------------------------


def _load_benchmark_corpus() -> ModuleType:
    harness = PROJECT / "scripts" / "benchmark_corpus.py"
    spec = importlib.util.spec_from_file_location("benchmark_corpus_loop6", harness)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_benchmark_corpus_uses_sarif_scenario_rules() -> None:
    corpus = _load_benchmark_corpus()
    assert corpus.SCENARIO_RULES == SARIF_SCENARIO_RULES

    base_ev = [{"cls": "declared", "file": ".github/workflows/ci.yml", "rule": "R1", "line": 1}]
    # NHB-ROT-001 IS in SCENARIO_RULES -> scenario changes fingerprint
    f_rot_a = {
        "rule": "NHB-ROT-001",
        "severity": "LOW",
        "confidence": "derived",
        "message": "m",
        "path": ["job:a"],
        "evidence": base_ev,
        "scenario": "repo-write",
    }
    f_rot_b = {**f_rot_a, "scenario": "all-mutable-actions"}
    assert corpus.finding_signature(f_rot_a) != corpus.finding_signature(f_rot_b)

    # NHB-GHA-001 is NOT in SCENARIO_RULES -> scenario does NOT change fingerprint
    f_gha_a = {**f_rot_a, "rule": "NHB-GHA-001"}
    f_gha_b = {**f_rot_b, "rule": "NHB-GHA-001"}
    assert corpus.finding_signature(f_gha_a) == corpus.finding_signature(f_gha_b)
