"""Loop 2 IR, What-If & Partition safety regression tests (Audit #5)."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from nhi_blast.analysis.partition import _close_persistent, partition_graph
from nhi_blast.analysis.reach import PathInfo
from nhi_blast.analysis.rotation import plan_rotation
from nhi_blast.analysis.scenario import analyze_scenario
from nhi_blast.core.canonical import digest_of
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.ids import edge_id
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    AnalyzerIdentity,
    CredentialKind,
    Edge,
    EdgeKind,
    GraphData,
    Inputs,
    Lifetime,
    Node,
    NodeKind,
    Report,
    ReportContext,
    ScenarioContext,
    ToolInfo,
)
from nhi_blast.graph.store import GraphStore
from nhi_blast.whatif.engine import (
    _Executed,
    _issued_before_containment,
    _Outcome,
    _Run,
    _State,
    run_whatif,
)
from nhi_blast.whatif.plan import (
    MAX_INTERVENTIONS,
    PlanEntry,
    RemoveTrust,
    RevokeRoleSessions,
    parse_plan,
    synthesize_auto_plan,
)
from nhi_blast.whatif.playbook import render_playbook
from nhi_blast.whatif.sessions import assess_session, parse_timestamp, resolve_cutoff
from tests.support import evidence


def _at(time_str: str) -> datetime:
    return parse_timestamp(f"2026-03-01T{time_str}Z")


def _add_node(
    store: GraphStore,
    node_id: str,
    kind: NodeKind,
    *,
    label: str | None = None,
    attrs: dict[str, object] | None = None,
) -> None:
    store.add_node(
        Node(
            id=node_id,
            kind=kind,
            label=label or node_id,
            attrs=attrs or {},
            evidence=(evidence(EvidenceClass.DECLARED, rule="test.node"),),
        )
    )


def _add_edge(
    store: GraphStore,
    kind: EdgeKind,
    src: str,
    dst: str,
    *,
    confidence: EvidenceClass = EvidenceClass.DECLARED,
    attrs: dict[str, object] | None = None,
) -> str:
    ev = evidence(confidence, rule=f"test.{kind.value}", detail=f"{src}->{dst}")
    eid = edge_id(kind.value, src, dst, (ev,))
    store.add_edge(
        Edge(
            id=eid,
            kind=kind,
            src=src,
            dst=dst,
            confidence=confidence,
            evidence=(ev,),
            attrs=attrs or {},
        )
    )
    return eid


def _add_persistent_cred(store: GraphStore, cred_id: str, label: str | None = None) -> None:
    _add_node(
        store,
        cred_id,
        NodeKind.CREDENTIAL,
        label=label or cred_id,
        attrs={
            "credential_kind": CredentialKind.GENERIC_SECRET.value,
            "lifetime": Lifetime.PERSISTENT.value,
            "criticality": 70,
            "survival_window": "until rotated",
        },
    )


def _add_sts_session(store: GraphStore, cred_id: str, role_id: str, ttl: int = 3600) -> None:
    _add_node(
        store,
        cred_id,
        NodeKind.CREDENTIAL,
        label=f"STS session for {role_id}",
        attrs={
            "credential_kind": CredentialKind.STS_SESSION.value,
            "lifetime": Lifetime.SESSION_TTL.value,
            "ttl_seconds": ttl,
            "role": role_id,
        },
    )


def _build_report(
    graph: GraphData,
    starts: tuple[str, ...],
    *,
    selector: str = "job:.github/workflows/ci.yml#compromised",
    selector_kind: str = "job",
    max_depth: int = 3,
) -> Report:
    analysis = analyze_scenario(
        graph,
        starts,
        selector=selector,
        selector_kind=selector_kind,
        max_depth=max_depth,
    )
    limits = Limits()
    graph_digest = digest_of(graph.model_dump(mode="json"))
    sc_ctx = ScenarioContext(
        selector=selector,
        selector_kind=selector_kind,
        start_nodes=starts,
    )
    ctx_payload = {
        "max_depth": max_depth,
        "strict": False,
        "limits": asdict(limits),
        "scenarios": [sc_ctx.model_dump(mode="json")],
    }
    ctx = ReportContext(
        analyzer=AnalyzerIdentity(
            tool_version="0.3.0-test",
            rules_digest="0" * 64,
            data_digests={},
            engine_semantics="test",
        ),
        default_branch="main",
        limits=asdict(limits),
        max_depth=max_depth,
        strict=False,
        selectors=(selector,),
        scenarios=(sc_ctx,),
        config_digest="0" * 64,
        graph_digest=graph_digest,
        context_digest=digest_of(ctx_payload),
    )
    return Report(
        tool=ToolInfo(version="0.3.0-test"),
        inputs=Inputs(digest="0" * 64, repo_slug="acme/demo", repo_slug_source="test"),
        graph=graph,
        scenarios=(analysis.to_report(),),
        context=ctx,
    )


# ------------------------------------------------------------------ 1. Playbook


def test_playbook_reorders_containment_before_revocation() -> None:
    job = "job:.github/workflows/deploy.yml#deploy"
    store = GraphStore()
    _add_node(store, job, NodeKind.JOB)
    _add_node(store, "oidc:deploy", NodeKind.OIDC_IDENTITY)
    _add_node(store, "aws:role:deploy", NodeKind.AWS_ROLE, label="deploy")
    _add_sts_session(store, "cred:sts:deploy", "aws:role:deploy")
    _add_edge(store, EdgeKind.CAN_MINT, job, "oidc:deploy")
    trust_edge = _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:deploy",
        "aws:role:deploy",
        attrs={"session_credential": "cred:sts:deploy"},
    )
    report = _build_report(store.data(), (job,), selector=job)
    plan = parse_plan(
        {
            "schema": "nhi-blast-interventions/1.0",
            "interventions": [
                {"type": "remove_trust", "role": "aws:role:deploy", "edge": trust_edge},
                {
                    "type": "revoke_role_sessions",
                    "role": "aws:role:deploy",
                    "revoked_at": "2026-03-01T10:00:00Z",
                },
            ],
        }
    )
    payload = run_whatif(report, plan, check=False)
    md = render_playbook(report, payload)
    headings = [line for line in md.splitlines() if line.startswith("## ")]
    assert headings[:4] == [
        "## 1. Remove trust or disable entrypoint",
        "## 2. Revoke role sessions",
        "## 3. Rotate surviving credentials in dependency order",
        "## 4. Verify",
    ]
    assert "### Step 1.1: remove trust into `aws:role:deploy`" in md
    assert "### Step 2.1: revoke sessions of role `aws:role:deploy`" in md
    assert md.index("## 1. Remove trust or disable entrypoint") < md.index(
        "## 2. Revoke role sessions"
    )


def test_playbook_filters_persistence_audit_to_reachable_roles() -> None:
    job = "job:.github/workflows/deploy.yml#deploy"
    store = GraphStore()
    _add_node(store, job, NodeKind.JOB)
    _add_node(store, "oidc:deploy", NodeKind.OIDC_IDENTITY)
    _add_node(
        store,
        "aws:role:reachable-admin",
        NodeKind.AWS_ROLE,
        label="reachable-admin",
        attrs={"persistence_actions": ["iam:CreateAccessKey"]},
    )
    _add_node(
        store,
        "aws:role:unrelated-admin",
        NodeKind.AWS_ROLE,
        label="unrelated-admin",
        attrs={"persistence_actions": ["iam:PutRolePolicy"]},
    )
    _add_sts_session(store, "cred:sts:reachable", "aws:role:reachable-admin")
    _add_edge(store, EdgeKind.CAN_MINT, job, "oidc:deploy")
    _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:deploy",
        "aws:role:reachable-admin",
        attrs={"session_credential": "cred:sts:reachable"},
    )
    report = _build_report(store.data(), (job,), selector=job)
    plan = parse_plan({"schema": "nhi-blast-interventions/1.0", "interventions": []})
    payload = run_whatif(report, plan, check=False)
    md = render_playbook(report, payload)
    assert "## Cloud Persistence Audit" in md
    assert "reachable-admin" in md
    assert "unrelated-admin" not in md


def test_playbook_omits_persistence_audit_when_only_unreachable_roles_persist() -> None:
    job = "job:.github/workflows/deploy.yml#deploy"
    store = GraphStore()
    _add_node(store, job, NodeKind.JOB)
    _add_node(
        store,
        "aws:role:unrelated-admin",
        NodeKind.AWS_ROLE,
        label="unrelated-admin",
        attrs={"persistence_actions": ["iam:CreateAccessKey"]},
    )
    report = _build_report(store.data(), (job,), selector=job)
    plan = parse_plan({"schema": "nhi-blast-interventions/1.0", "interventions": []})
    payload = run_whatif(report, plan, check=False)
    md = render_playbook(report, payload)
    assert "## Cloud Persistence Audit" not in md
    assert "unrelated-admin" not in md


def test_playbook_shows_collateral_impact_for_shared_roles() -> None:
    deploy_job = "job:.github/workflows/deploy.yml#deploy"
    backup_job = "job:.github/workflows/nightly.yml#backup"
    store = GraphStore()
    _add_node(store, "workflow:.github/workflows/deploy.yml", NodeKind.WORKFLOW)
    _add_node(store, deploy_job, NodeKind.JOB)
    _add_node(store, "workflow:.github/workflows/nightly.yml", NodeKind.WORKFLOW)
    _add_node(store, backup_job, NodeKind.JOB)
    _add_node(store, "oidc:deploy", NodeKind.OIDC_IDENTITY)
    _add_node(store, "oidc:nightly", NodeKind.OIDC_IDENTITY)
    _add_node(store, "aws:role:shared", NodeKind.AWS_ROLE, label="shared")
    _add_sts_session(store, "cred:sts:shared", "aws:role:shared")
    _add_edge(store, EdgeKind.CONTAINS, "workflow:.github/workflows/deploy.yml", deploy_job)
    _add_edge(store, EdgeKind.CONTAINS, "workflow:.github/workflows/nightly.yml", backup_job)
    _add_edge(store, EdgeKind.CAN_MINT, deploy_job, "oidc:deploy")
    _add_edge(store, EdgeKind.CAN_MINT, backup_job, "oidc:nightly")
    e_deploy = _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:deploy",
        "aws:role:shared",
        attrs={"session_credential": "cred:sts:shared"},
    )
    _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:nightly",
        "aws:role:shared",
        attrs={"session_credential": "cred:sts:shared"},
    )
    report = _build_report(store.data(), (deploy_job,), selector=deploy_job)
    plan = parse_plan(
        {
            "schema": "nhi-blast-interventions/1.0",
            "interventions": [
                {"type": "remove_trust", "role": "aws:role:shared", "edge": e_deploy},
                {
                    "type": "revoke_role_sessions",
                    "role": "aws:role:shared",
                    "revoked_at": "2026-03-01T10:00:00Z",
                },
            ],
        }
    )
    payload = run_whatif(report, plan, check=False)
    md = render_playbook(report, payload)
    section1, section2_and_rest = md.split("## 2. Revoke role sessions", maxsplit=1)
    section2 = section2_and_rest.split("## 3. Rotate", maxsplit=1)[0]
    assert "**Collateral Impact**" in section1
    assert backup_job in section1
    assert "**Collateral Impact**" in section2
    assert backup_job in section2


# ------------------------------------------------------------------ 2. Engine


def test_multi_trust_role_keeps_re_issue_possible_until_all_trust_removed() -> None:
    job = "job:.github/workflows/ci.yml#a"
    store = GraphStore()
    _add_node(store, job, NodeKind.JOB)
    _add_node(store, "oidc:a", NodeKind.OIDC_IDENTITY)
    _add_node(store, "oidc:b", NodeKind.OIDC_IDENTITY)
    _add_node(store, "aws:role:multi", NodeKind.AWS_ROLE, label="multi")
    _add_sts_session(store, "cred:sts:multi", "aws:role:multi")
    _add_edge(store, EdgeKind.CAN_MINT, job, "oidc:a")
    edge_a = _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:a",
        "aws:role:multi",
        attrs={"session_credential": "cred:sts:multi"},
    )
    edge_b = _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:b",
        "aws:role:multi",
        attrs={"session_credential": "cred:sts:multi"},
    )
    report = _build_report(store.data(), (job,), selector=job)

    # Removing only edge_a leaves oidc:b -> aws:role:multi intact -> re_issue_possible is True.
    partial_plan = parse_plan(
        {
            "schema": "nhi-blast-interventions/1.0",
            "interventions": [
                {"type": "remove_trust", "role": "aws:role:multi", "edge": edge_a},
                {
                    "type": "revoke_role_sessions",
                    "role": "aws:role:multi",
                    "revoked_at": "2026-03-01T10:00:00Z",
                },
            ],
        }
    )
    partial_payload = run_whatif(report, partial_plan, check=False)
    row_partial = partial_payload["per_scenario"][0]["after"]["revoked_access"][0]
    assert row_partial["re_issue_possible"] is True

    # Removing both edge_a and edge_b eliminates all trust -> re_issue_possible is False.
    full_plan = parse_plan(
        {
            "schema": "nhi-blast-interventions/1.0",
            "interventions": [
                {"type": "remove_trust", "role": "aws:role:multi", "edge": edge_a},
                {"type": "remove_trust", "role": "aws:role:multi", "edge": edge_b},
                {
                    "type": "revoke_role_sessions",
                    "role": "aws:role:multi",
                    "revoked_at": "2026-03-01T10:00:00Z",
                },
            ],
        }
    )
    full_payload = run_whatif(report, full_plan, check=False)
    row_full = full_payload["per_scenario"][0]["after"]["revoked_access"][0]
    assert row_full["re_issue_possible"] is False


def test_issued_before_containment_ignores_no_effect_remove_trust() -> None:
    job = "job:.github/workflows/ci.yml#a"
    store = GraphStore()
    _add_node(store, job, NodeKind.JOB)
    _add_node(store, "oidc:a", NodeKind.OIDC_IDENTITY)
    _add_node(store, "aws:role:r", NodeKind.AWS_ROLE, label="r")
    _add_sts_session(store, "cred:sts:r", "aws:role:r")
    _add_edge(store, EdgeKind.CAN_MINT, job, "oidc:a")
    edge_a = _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:a",
        "aws:role:r",
        attrs={"session_credential": "cred:sts:r"},
    )
    report = _build_report(store.data(), (job,), selector=job)

    plan = parse_plan(
        {
            "schema": "nhi-blast-interventions/1.0",
            "interventions": [{"type": "remove_trust", "role": "aws:role:r", "edge": edge_a}],
        }
    )
    run_obj = _Run(report, plan)
    entry = PlanEntry(0, "remove_trust", intervention=RemoveTrust(role="aws:role:r", edge=edge_a))
    no_effect_exec = [
        _Executed(entry, _Outcome("no_effect", state=_State(), role="aws:role:r"), _State())
    ]
    future = run_obj.analyses(_State())[job]
    rows = _issued_before_containment(run_obj, no_effect_exec, report.scenarios[0], future)
    assert len(rows) == 1
    assert "note" not in rows[0]

    applied_exec = [
        _Executed(entry, _Outcome("applied", state=_State(), role="aws:role:r"), _State())
    ]
    rows_applied = _issued_before_containment(run_obj, applied_exec, report.scenarios[0], future)
    assert "note" in rows_applied[0]


def test_rotate_credential_guards_invalid_lifetime_value() -> None:
    job = "job:.github/workflows/ci.yml#a"
    store = GraphStore()
    _add_node(store, job, NodeKind.JOB)
    _add_node(
        store,
        "cred:corrupt",
        NodeKind.CREDENTIAL,
        label="corrupt",
        attrs={"lifetime": "not_a_valid_lifetime"},
    )
    report = _build_report(store.data(), (job,), selector=job)
    plan = parse_plan(
        {
            "schema": "nhi-blast-interventions/1.0",
            "interventions": [{"type": "rotate_credential", "credential": "cred:corrupt"}],
        }
    )
    payload = run_whatif(report, plan, check=False)
    assert payload["steps"][0]["status"] == "rejected"
    assert payload["steps"][0]["reason"] == "not_persistent_credential"


# ------------------------------------------------------------------ 3. Sessions


def test_sessions_separates_propagation_from_cutoff() -> None:
    # Explicit cutoff earlier than revoked_at: assessed_at < revoked_at MUST NOT be denied.
    cutoff, source = resolve_cutoff(_at("10:00:00"), _at("09:50:00"))
    assert source == "given"
    before_revoke = assess_session(
        issued_no_later_than=_at("09:30:00"),
        ttl_seconds=3600,
        revoked_at=_at("10:00:00"),
        cutoff=cutoff,
        assessed_at=_at("09:55:00"),
    )
    assert before_revoke.access == "not_denied"
    assert before_revoke.conditional_on_propagation is False

    # Inside propagation window [revoked_at, revoked_at + 30s): conditional_on_propagation=True.
    propagating = assess_session(
        issued_no_later_than=_at("09:30:00"),
        ttl_seconds=3600,
        revoked_at=_at("10:00:00"),
        cutoff=cutoff,
        assessed_at=_at("10:00:15"),
    )
    assert propagating.access == "revocation_propagating"
    assert propagating.conditional_on_propagation is True

    # Exactly at revoked_at is also inside propagation window.
    at_revoke = assess_session(
        issued_no_later_than=_at("09:30:00"),
        ttl_seconds=3600,
        revoked_at=_at("10:00:00"),
        cutoff=_at("10:00:30"),
        assessed_at=_at("10:00:00"),
    )
    assert at_revoke.access == "revocation_propagating"
    assert at_revoke.conditional_on_propagation is True

    # Explicit future cutoff (10:05:00), assessed after propagation (10:01:00):
    # policy is propagated and issued < cutoff -> denied_by_revocation_policy.
    after_prop = assess_session(
        issued_no_later_than=_at("09:30:00"),
        ttl_seconds=3600,
        revoked_at=_at("10:00:00"),
        cutoff=_at("10:05:00"),
        assessed_at=_at("10:01:00"),
    )
    assert after_prop.access == "denied_by_revocation_policy"
    assert after_prop.conditional_on_propagation is False


# ------------------------------------------------------------------ 4. Auto Plan


def test_synthesize_auto_plan_scopes_to_reachable_oidc_and_role_chaining() -> None:
    comp_job = "job:.github/workflows/ci.yml#compromised"
    prod_job = "job:.github/workflows/prod.yml#prod"
    store = GraphStore()
    _add_node(store, comp_job, NodeKind.JOB)
    _add_node(store, "oidc:comp", NodeKind.OIDC_IDENTITY)
    _add_node(store, "aws:role:stage", NodeKind.AWS_ROLE, label="stage")
    _add_node(store, "aws:role:chained", NodeKind.AWS_ROLE, label="chained")
    _add_sts_session(store, "cred:sts:stage", "aws:role:stage")
    _add_sts_session(store, "cred:sts:chained", "aws:role:chained")

    # Unrelated production workflow and role in the same graph
    _add_node(store, prod_job, NodeKind.JOB)
    _add_node(store, "oidc:prod", NodeKind.OIDC_IDENTITY)
    _add_node(store, "aws:role:prod", NodeKind.AWS_ROLE, label="prod")
    _add_sts_session(store, "cred:sts:prod", "aws:role:prod")

    _add_edge(store, EdgeKind.CAN_MINT, comp_job, "oidc:comp")
    e_oidc = _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:comp",
        "aws:role:stage",
        attrs={"session_credential": "cred:sts:stage"},
    )
    e_chain = _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "aws:role:stage",
        "aws:role:chained",
        attrs={"session_credential": "cred:sts:chained"},
    )
    _add_edge(store, EdgeKind.CAN_MINT, prod_job, "oidc:prod")
    e_prod = _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:prod",
        "aws:role:prod",
        attrs={"session_credential": "cred:sts:prod"},
    )

    report = _build_report(store.data(), (comp_job,), selector=comp_job)
    plan = synthesize_auto_plan(report)

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
    assert e_oidc in removed_edges
    assert e_chain in removed_edges
    assert e_prod not in removed_edges
    assert "aws:role:prod" not in revoked_roles


def test_synthesize_auto_plan_caps_at_max_interventions() -> None:
    job = "job:.github/workflows/ci.yml#massive"
    store = GraphStore()
    _add_node(store, job, NodeKind.JOB)
    for idx in range(MAX_INTERVENTIONS + 50):
        cred_id = f"cred:secret-{idx:04d}"
        _add_persistent_cred(store, cred_id)
        _add_edge(store, EdgeKind.HOLDS, job, cred_id)
    report = _build_report(store.data(), (job,), selector=job)
    plan = synthesize_auto_plan(report)
    assert len(plan.entries) == MAX_INTERVENTIONS


# ------------------------------------------------------------------ 5. Partition


def test_partition_truncated_flag_not_set_on_exact_depth_or_dead_end() -> None:
    store = GraphStore()
    _add_node(store, "role:r1", NodeKind.AWS_ROLE)
    _add_node(store, "role:r2", NodeKind.AWS_ROLE)
    _add_node(store, "sink:s1", NodeKind.SINK)
    _add_node(store, "sink:s2", NodeKind.SINK)
    _add_persistent_cred(store, "cred:z0")
    _add_persistent_cred(store, "cred:z1")
    _add_persistent_cred(store, "cred:z2")

    _add_edge(store, EdgeKind.AUTHENTICATES_AS, "cred:z0", "role:r1")
    _add_edge(store, EdgeKind.CAN_READ_VALUE, "role:r1", "sink:s1")
    _add_edge(store, EdgeKind.STORES, "sink:s1", "cred:z1")
    _add_edge(store, EdgeKind.AUTHENTICATES_AS, "cred:z1", "role:r2")
    _add_edge(store, EdgeKind.CAN_READ_VALUE, "role:r2", "sink:s2")
    _add_edge(store, EdgeKind.STORES, "sink:s2", "cred:z2")

    graph = store.data()
    nodes = {node.id: node for node in graph.nodes}

    # At max_depth=0: z0 has an unexplored closure edge to z1 -> truncated=True
    depths0, trunc0 = _close_persistent(graph, nodes, {"cred:z0": 0}, max_depth=0, should_stop=None)
    assert depths0 == {"cred:z0": 0}
    assert trunc0 is True

    # At max_depth=1: z1 has an unexplored closure edge to z2 -> truncated=True
    depths1, trunc1 = _close_persistent(graph, nodes, {"cred:z0": 0}, max_depth=1, should_stop=None)
    assert depths1 == {"cred:z0": 0, "cred:z1": 1}
    assert trunc1 is True

    # At max_depth=2: z2 has NO unexplored outgoing closure edge -> truncated=False!
    depths2, trunc2 = _close_persistent(graph, nodes, {"cred:z0": 0}, max_depth=2, should_stop=None)
    assert depths2 == {"cred:z0": 0, "cred:z1": 1, "cred:z2": 2}
    assert trunc2 is False

    # Dead-end leaf at max_depth=0 -> truncated=False
    depths_leaf, trunc_leaf = _close_persistent(
        graph, nodes, {"cred:z2": 0}, max_depth=0, should_stop=None
    )
    assert depths_leaf == {"cred:z2": 0}
    assert trunc_leaf is False


def test_partition_closure_supports_direct_read_and_can_assume_chaining() -> None:
    store = GraphStore()
    _add_node(store, "sink:direct", NodeKind.SINK)
    _add_node(store, "role:r1", NodeKind.AWS_ROLE)
    _add_node(store, "role:r2", NodeKind.AWS_ROLE)
    _add_node(store, "sink:chained", NodeKind.SINK)
    _add_persistent_cred(store, "cred:z0")
    _add_persistent_cred(store, "cred:z_direct")
    _add_persistent_cred(store, "cred:z_chained")

    # Direct CREDENTIAL -> CAN_READ_VALUE -> SINK -> STORES -> CREDENTIAL
    _add_edge(store, EdgeKind.CAN_READ_VALUE, "cred:z0", "sink:direct")
    _add_edge(store, EdgeKind.STORES, "sink:direct", "cred:z_direct")

    # Role chaining: CREDENTIAL -> AUTHENTICATES_AS -> role:r1 -> CAN_ASSUME -> role:r2 -> read
    _add_edge(store, EdgeKind.AUTHENTICATES_AS, "cred:z0", "role:r1")
    _add_edge(store, EdgeKind.CAN_ASSUME, "role:r1", "role:r2")
    _add_edge(store, EdgeKind.CAN_READ_VALUE, "role:r2", "sink:chained")
    _add_edge(store, EdgeKind.STORES, "sink:chained", "cred:z_chained")

    graph = store.data()
    # Provide pre-computed reachable containing only cred:z0 so _close_persistent drives depth 1.
    result = partition_graph(
        graph,
        ["cred:z0"],
        max_depth=1,
        reachable={"cred:z0": PathInfo(node="cred:z0")},
    )
    by_id = {item.credential: item.depth for item in result.partition.Z}
    assert by_id == {"cred:z0": 0, "cred:z_direct": 1, "cred:z_chained": 1}
    assert result.truncated is False


# ------------------------------------------------------------------ 6. Rotation


def test_plan_rotation_filters_persist_roles_to_scenario_reachable() -> None:
    job = "job:.github/workflows/deploy.yml#deploy"
    store = GraphStore()
    _add_node(store, job, NodeKind.JOB)
    _add_node(store, "oidc:deploy", NodeKind.OIDC_IDENTITY)
    _add_node(
        store,
        "aws:role:reachable",
        NodeKind.AWS_ROLE,
        label="reachable-role",
        attrs={"persistence_actions": ["iam:CreateAccessKey"]},
    )
    _add_node(
        store,
        "aws:role:unreachable",
        NodeKind.AWS_ROLE,
        label="unreachable-role",
        attrs={"persistence_actions": ["iam:PutRolePolicy"]},
    )
    _add_sts_session(store, "cred:sts:reachable", "aws:role:reachable")
    _add_edge(store, EdgeKind.CAN_MINT, job, "oidc:deploy")
    _add_edge(
        store,
        EdgeKind.CAN_ASSUME,
        "oidc:deploy",
        "aws:role:reachable",
        attrs={"session_credential": "cred:sts:reachable"},
    )

    graph = store.data()
    part = partition_graph(graph, [job]).partition
    rot = plan_rotation(graph, part, selector_kind="job", start_nodes=[job])
    audit_texts = [
        action
        for step in rot.verify
        for action in step.actions
        if "Cloud Persistence Audit" in action
    ]
    assert len(audit_texts) == 1
    assert "reachable-role" in audit_texts[0]
    assert "unreachable-role" not in audit_texts[0]


def test_plan_rotation_omits_persist_audit_when_no_reachable_persist_role() -> None:
    job = "job:.github/workflows/deploy.yml#deploy"
    store = GraphStore()
    _add_node(store, job, NodeKind.JOB)
    _add_node(
        store,
        "aws:role:unreachable",
        NodeKind.AWS_ROLE,
        label="unreachable-role",
        attrs={"persistence_actions": ["iam:CreateAccessKey"]},
    )
    graph = store.data()
    part = partition_graph(graph, [job]).partition
    rot = plan_rotation(graph, part, selector_kind="job", start_nodes=[job])
    assert not any(
        "Cloud Persistence Audit" in action for step in rot.verify for action in step.actions
    )
