"""R/E/Z partitioning and persistent-credential closure (M4)."""

from __future__ import annotations

from pathlib import Path

from nhi_blast.analysis.partition import partition_graph
from nhi_blast.analysis.selectors import parse_selector, resolve_starts
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.ids import edge_id
from nhi_blast.core.models import Edge, EdgeKind, Lifetime, Node, NodeKind
from nhi_blast.graph.store import GraphStore
from tests.support import evidence
from tests.test_graph_builder import PUBLISH_JOB, ROLE_DEPLOY, TEST_JOB, build_fixture, build_inline

ROLE_LEGACY = "aws:role:arn:aws:iam::111122223333:role/legacy-ci"
PUBLISH_IDENTITY = "oidc:job:.github/workflows/release.yml#publish:sts.amazonaws.com"
DEPLOY_SESSION = f"cred:{PUBLISH_IDENTITY}:sts-session:{ROLE_DEPLOY}"
LEGACY_SESSION = f"cred:{PUBLISH_IDENTITY}:sts-session:{ROLE_LEGACY}"


def test_fx07_action_partition_matches_the_reference_output(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    starts = resolve_starts(parse_selector("action:tj-actions/changed-files@v45"), graph, jobs=())

    result = partition_graph(graph, starts)

    assert list(result.partition.R) == [
        f"cred:{TEST_JOB}:GITHUB_TOKEN",
        f"cred:{PUBLISH_JOB}:GITHUB_TOKEN",
        f"cred:{PUBLISH_JOB}:OIDC_REQUEST_TOKEN",
    ]
    assert [(item.credential, item.ttl_seconds) for item in result.partition.E] == [
        (DEPLOY_SESSION, 3600),
        (LEGACY_SESSION, 3600),
    ]
    assert [item.credential for item in result.partition.Z] == [
        "cred:aws:secret:prod/db-master:stored",
        "cred:aws:ssm:/prod/stripe/live_key:stored",
        "cred:aws:ssm:/legacy/ci-token:stored",
        "cred:aws:secret:prod/app-config:stored",
        f"cred:{PUBLISH_JOB}:SLACK_WEBHOOK_URL",
    ]
    assert [item.depth for item in result.partition.Z] == [0, 0, 0, 0, 0]
    assert [item.criticality for item in result.partition.Z] == [100, 70, 65, 55, 40]
    assert result.partition.Z[3].lifetime is Lifetime.PERSISTENT_ROTATING
    assert result.partition.Z[3].survival_window == "up to 30 days"
    assert result.partition.Z[4].survival_window == "until rotated"
    assert not result.truncated


def test_role_selector_marks_the_starting_session_as_obtained(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx07-incident").graph
    starts = resolve_starts(parse_selector("role:aws_iam_role.deploy_prod"), graph, jobs=())

    result = partition_graph(graph, starts)

    assert [item.credential for item in result.partition.E] == [DEPLOY_SESSION]
    assert LEGACY_SESSION not in result.reach
    assert {item.credential for item in result.partition.Z} == {
        "cred:aws:secret:prod/db-master:stored",
        "cred:aws:secret:prod/app-config:stored",
        "cred:aws:ssm:/prod/stripe/live_key:stored",
    }


def test_fx09_has_no_role_or_session_reach(fixtures_dir: Path) -> None:
    graph = build_fixture(fixtures_dir, "fx09-no-id-token").graph
    starts = resolve_starts(
        parse_selector("workflow:.github/workflows/permissions.yml"), graph, jobs=()
    )

    result = partition_graph(graph, starts)

    assert not any(node_id.startswith("aws:role:") for node_id in result.reach)
    assert result.partition.E == ()
    assert result.partition.Z == ()


def test_unknown_held_credentials_never_enter_the_partition() -> None:
    build = build_inline(
        """
name: Wildcard
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    permissions: {}
    env:
      ALL_SECRETS: ${{ toJSON(secrets) }}
    steps:
      - run: echo build
"""
    )
    job_id = "job:.github/workflows/test.yml#build"
    wildcard = f"cred:{job_id}:*"

    result = partition_graph(build.graph, [job_id])

    assert list(result.partition.R) == [f"cred:{job_id}:GITHUB_TOKEN"]
    assert result.partition.Z == ()
    assert wildcard not in result.reach
    assert wildcard in result.potential.nodes
    assert result.potential.unresolved_inputs


def add_credential(store: GraphStore, name: str) -> None:
    store.add_node(
        Node(
            id=f"cred:{name}",
            kind=NodeKind.CREDENTIAL,
            label=name,
            attrs={
                "credential_kind": "GENERIC_SECRET",
                "lifetime": Lifetime.PERSISTENT.value,
                "criticality": 55,
                "survival_window": "until rotated",
            },
            evidence=(evidence(EvidenceClass.ASSUMED, rule="test.credential"),),
        )
    )


def add_closure_edge(
    store: GraphStore,
    kind: EdgeKind,
    src: str,
    dst: str,
    confidence: EvidenceClass = EvidenceClass.DERIVED,
) -> None:
    item = evidence(confidence, rule=f"test.{kind}", detail=f"{src}->{dst}")
    store.add_edge(
        Edge(
            id=edge_id(kind.value, src, dst, (item,)),
            kind=kind,
            src=src,
            dst=dst,
            confidence=confidence,
            evidence=(item,),
        )
    )


def closure_graph():
    store = GraphStore()
    for node_id, kind in [
        ("job:start", NodeKind.JOB),
        ("role:one", NodeKind.AWS_ROLE),
        ("role:two", NodeKind.AWS_ROLE),
        ("role:three", NodeKind.AWS_ROLE),
        ("sink:one", NodeKind.SINK),
        ("sink:two", NodeKind.SINK),
        ("sink:three", NodeKind.SINK),
    ]:
        store.add_node(
            Node(
                id=node_id,
                kind=kind,
                label=node_id,
                evidence=(evidence(EvidenceClass.DECLARED, rule="test.node"),),
            )
        )
    for name in ("z0", "z1", "z2", "z3"):
        add_credential(store, name)
    add_closure_edge(store, EdgeKind.HOLDS, "job:start", "cred:z0", EvidenceClass.DECLARED)
    for index, edge_kind in enumerate(
        (EdgeKind.CAN_MODIFY, EdgeKind.CAN_READ_VALUE, EdgeKind.CAN_MODIFY),
        start=1,
    ):
        previous = f"cred:z{index - 1}"
        principal = f"role:{'one' if index == 1 else 'two' if index == 2 else 'three'}"
        sink = f"sink:{'one' if index == 1 else 'two' if index == 2 else 'three'}"
        target = f"cred:z{index}"
        add_closure_edge(store, EdgeKind.AUTHENTICATES_AS, previous, principal)
        add_closure_edge(store, edge_kind, principal, sink)
        add_closure_edge(store, EdgeKind.STORES, sink, target)
    return store.data()


def test_closure_follows_read_and_modify_edges_and_reports_depth_truncation() -> None:
    graph = closure_graph()

    limited = partition_graph(graph, ["job:start"], max_depth=1)
    complete = partition_graph(graph, ["job:start"], max_depth=4)

    assert [(item.credential, item.depth) for item in limited.partition.Z] == [
        ("cred:z0", 0),
        ("cred:z1", 1),
    ]
    assert limited.truncated
    assert [(item.credential, item.depth) for item in complete.partition.Z] == [
        ("cred:z0", 0),
        ("cred:z1", 1),
        ("cred:z2", 2),
        ("cred:z3", 3),
    ]
    assert not complete.truncated
