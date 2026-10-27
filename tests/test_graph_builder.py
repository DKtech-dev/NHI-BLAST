"""Graph builder rules R1-R14 and invariants (M3)."""

from __future__ import annotations

from pathlib import Path

from nhi_blast.core.config import Config
from nhi_blast.core.evidence import EvidenceClass, weakest
from nhi_blast.core.ids import edge_id
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    NODE_KIND_ORDER,
    CredentialKind,
    Edge,
    EdgeKind,
    Lifetime,
    NodeKind,
    PolicyContext,
    RoleFact,
    SinkFact,
    SinkType,
    SubFormat,
)
from nhi_blast.discovery.repo import RepoIdentity, resolve_identity
from nhi_blast.graph.builder import GraphBuild, GraphInputs, build_graph
from nhi_blast.parsers.gha.facts import CompositeActionFact, WorkflowFact
from nhi_blast.parsers.gha.workflow import parse_composite_action, parse_workflow
from nhi_blast.parsers.terraform.tfjson import parse_tf_json
from nhi_blast.resolvers.composite import expand_jobs
from nhi_blast.resolvers.roles import CloudFacts, resolve_cloud_facts
from tests.support import evidence

LIMITS = Limits()
SHA = "abcdef0123456789abcdef0123456789abcdef01"
ROLE_DEPLOY = "aws:role:arn:aws:iam::111122223333:role/deploy-prod"
ROLE_LEGACY = "aws:role:arn:aws:iam::111122223333:role/legacy-ci"
PUBLISH_JOB = "job:.github/workflows/release.yml#publish"
TEST_JOB = "job:.github/workflows/ci.yml#test"


def _identity() -> RepoIdentity:
    return RepoIdentity(
        slug="acme/shop",
        source="--repo-slug",
        default_branch="main",
        sub_format=SubFormat.CLASSIC,
    )


def empty_cloud() -> CloudFacts:
    return CloudFacts(
        roles=(),
        sinks=(),
        providers=(),
        externals=(),
        policy_context=PolicyContext(),
        diagnostics=(),
    )


def _composites(root: Path) -> dict[str, CompositeActionFact]:
    composites: dict[str, CompositeActionFact] = {}
    for path in sorted(root.glob(".github/actions/*/action.y*ml")):
        rel = path.relative_to(root).as_posix()
        parsed = parse_composite_action(rel, path.read_text(encoding="utf-8"), limits=LIMITS)
        if parsed.facts is not None:
            composites[rel] = parsed.facts
    return composites


def build_fixture(
    fixtures_dir: Path,
    folder: str,
    *,
    limits: Limits | None = None,
) -> GraphBuild:
    root = fixtures_dir / folder
    effective_limits = limits or LIMITS
    workflows: list[WorkflowFact] = []
    for path in sorted(root.glob(".github/workflows/*.y*ml")):
        rel = path.relative_to(root).as_posix()
        parsed = parse_workflow(rel, path.read_text(encoding="utf-8"), limits=effective_limits)
        assert parsed.facts is not None
        workflows.append(parsed.facts)
    expanded = expand_jobs(workflows, _composites(root), limits=effective_limits)
    config_path = root / "nhi-blast.toml"
    config = Config.from_file(config_path) if config_path.exists() else Config.empty()
    state_path = root / "tfstate.json"
    models = []
    if state_path.exists():
        parsed_state = parse_tf_json(
            "tfstate.json", state_path.read_text(encoding="utf-8"), limits=effective_limits
        )
        assert parsed_state.facts is not None
        models.append(parsed_state.facts)
    cloud = resolve_cloud_facts(models, [], config=config)
    identity = resolve_identity(
        root=root,
        cli_repo_slug=None,
        cli_default_branch=None,
        config_repo_slug=config.repo_slug,
        config_default_branch=config.default_branch,
    )
    return build_graph(
        GraphInputs(
            repository=identity,
            workflows=tuple(workflows),
            expanded_jobs=expanded,
            cloud=cloud,
            config=config,
            limits=effective_limits,
        )
    )


def build_inline(
    text: str,
    *,
    cloud: CloudFacts | None = None,
    config: Config | None = None,
    limits: Limits | None = None,
) -> GraphBuild:
    effective_limits = limits or LIMITS
    path = ".github/workflows/test.yml"
    parsed = parse_workflow(path, text, limits=effective_limits)
    assert parsed.facts is not None
    expanded = expand_jobs([parsed.facts], {}, limits=effective_limits)
    return build_graph(
        GraphInputs(
            repository=_identity(),
            workflows=(parsed.facts,),
            expanded_jobs=expanded,
            cloud=cloud or empty_cloud(),
            config=config or Config.empty(),
            limits=effective_limits,
        )
    )


def edges_of(build: GraphBuild, kind: EdgeKind) -> tuple[Edge, ...]:
    return tuple(edge for edge in build.graph.edges if edge.kind is kind)


def assert_graph_invariants(build: GraphBuild) -> None:
    nodes = {node.id: node for node in build.graph.nodes}
    assert len(nodes) == len(build.graph.nodes)
    assert [node.id for node in build.graph.nodes] == [
        node.id
        for node in sorted(
            build.graph.nodes, key=lambda item: (NODE_KIND_ORDER[item.kind], item.id)
        )
    ]
    assert list(build.graph.edges) == sorted(build.graph.edges, key=Edge.sort_key)
    prefixes = ("repo:", "wf:", "job:", "action:", "cred:", "oidc:", "aws:", "ext:")
    for node in build.graph.nodes:
        assert node.evidence, node.id
        assert node.id.startswith(prefixes), node.id
    seen: set[str] = set()
    for edge in build.graph.edges:
        assert edge.id not in seen, edge.id
        seen.add(edge.id)
        assert edge.evidence, edge.id
        assert edge.confidence is weakest(*(item.cls for item in edge.evidence)), edge.id
        assert edge.id == edge_id(edge.kind.value, edge.src, edge.dst, edge.evidence)
        assert edge.src in nodes, edge.id
        assert edge.dst in nodes, edge.id
        if edge.kind in {EdgeKind.RUNS_IN, EdgeKind.HOLDS}:
            assert edge.src.startswith("job:"), edge.id
        if edge.kind is EdgeKind.STORES:
            assert edge.src.startswith("aws:"), edge.id


def test_fx07_graph_contains_expected_principals_credentials_and_sinks(
    fixtures_dir: Path,
) -> None:
    build = build_fixture(fixtures_dir, "fx07-incident")
    assert not build.truncated
    assert_graph_invariants(build)

    nodes = {node.id: node for node in build.graph.nodes}
    assert "repo:acme/shop" in nodes
    assert "wf:.github/workflows/release.yml" in nodes
    assert PUBLISH_JOB in nodes
    assert TEST_JOB in nodes
    assert ROLE_DEPLOY in nodes
    assert ROLE_LEGACY in nodes
    identity = "oidc:job:.github/workflows/release.yml#publish:sts.amazonaws.com"
    session = (
        "cred:oidc:job:.github/workflows/release.yml#publish:sts.amazonaws.com:"
        f"sts-session:{ROLE_DEPLOY}"
    )
    assert identity in nodes
    assert session in nodes
    session_node = nodes[session]
    assert session_node.attrs["lifetime"] == Lifetime.SESSION_TTL.value
    assert session_node.attrs["ttl_seconds"] == 3600
    assert session_node.attrs["credential_kind"] == CredentialKind.STS_SESSION.value

    secrets = [node for node in build.graph.nodes if node.label == "SLACK_WEBHOOK_URL"]
    assert len(secrets) == 1
    secret = secrets[0]
    assert secret.attrs["secret"] is True
    assert secret.attrs["lifetime"] == Lifetime.PERSISTENT.value
    assert secret.attrs["credential_kind"] == CredentialKind.WEBHOOK_URL.value
    holds = [edge for edge in edges_of(build, EdgeKind.HOLDS) if edge.dst == secret.id]
    assert [edge.src for edge in holds] == [PUBLISH_JOB]

    sink_ids = {node.id for node in build.graph.nodes if node.kind is NodeKind.SINK}
    assert sink_ids == {
        "aws:secret:prod/app-config",
        "aws:secret:prod/db-master",
        "aws:ssm:/legacy/ci-token",
        "aws:ssm:/prod/stripe/live_key",
    }
    stores = {edge.src: edge.lifetime for edge in edges_of(build, EdgeKind.STORES)}
    assert stores["aws:secret:prod/app-config"] is Lifetime.PERSISTENT_ROTATING
    assert stores["aws:secret:prod/db-master"] is Lifetime.PERSISTENT
    assert stores["aws:ssm:/prod/stripe/live_key"] is Lifetime.PERSISTENT

    assume = {
        (edge.dst, edge.confidence, edge.attrs["intended"])
        for edge in edges_of(build, EdgeKind.CAN_ASSUME)
    }
    assert assume == {
        (ROLE_DEPLOY, EvidenceClass.DERIVED, True),
        (ROLE_LEGACY, EvidenceClass.DERIVED, False),
    }
    deploy_edge = next(
        edge for edge in edges_of(build, EdgeKind.CAN_ASSUME) if edge.dst == ROLE_DEPLOY
    )
    assert deploy_edge.attrs["session_credential"] == session
    assert deploy_edge.attrs["audience"] == "sts.amazonaws.com"
    assert deploy_edge.lifetime is Lifetime.SESSION_TTL

    reads = {edge.src: set() for edge in build.graph.edges if edge.kind is EdgeKind.CAN_READ_VALUE}
    for edge in edges_of(build, EdgeKind.CAN_READ_VALUE):
        reads.setdefault(edge.src, set()).add(edge.dst)
    assert reads[ROLE_DEPLOY] == {
        "aws:secret:prod/app-config",
        "aws:secret:prod/db-master",
        "aws:ssm:/prod/stripe/live_key",
    }
    assert reads[ROLE_LEGACY] == {"aws:ssm:/legacy/ci-token"}

    assert "A-OIDC-ENV" in build.assumptions_used
    assert "A-STS-TTL" in build.assumptions_used
    assert "A-REPO-AGE" in build.assumptions_used
    assert "H-SECRET-NAME" in build.assumptions_used
    assert build.diagnostics == ()


def test_fx09_read_all_grants_no_oidc_identity(fixtures_dir: Path) -> None:
    build = build_fixture(fixtures_dir, "fx09-no-id-token")
    assert not build.truncated
    assert_graph_invariants(build)
    assert edges_of(build, EdgeKind.CAN_MINT) == ()
    assert edges_of(build, EdgeKind.CAN_ASSUME) == ()
    kinds = {node.kind for node in build.graph.nodes}
    assert NodeKind.OIDC_IDENTITY not in kinds
    assert not any("OIDC_REQUEST_TOKEN" in node.id for node in build.graph.nodes)

    jobs = {node.attrs["job_id"]: node for node in build.graph.nodes if node.kind is NodeKind.JOB}
    constrained = jobs["constrained"]
    assert constrained.attrs["permissions"]["id-token"] == "read"
    assert constrained.attrs["id_token_write"] is False
    empty = jobs["empty"]
    assert empty.attrs["id_token_write"] is False
    assert set(empty.attrs["permissions"].values()) == {"none"}


def test_fx11_config_bindings_form_a_rotation_cycle(fixtures_dir: Path) -> None:
    build = build_fixture(fixtures_dir, "fx11-rotation-cycle")
    assert not build.truncated
    assert_graph_invariants(build)
    auth = {
        (edge.src, edge.dst, edge.confidence) for edge in edges_of(build, EdgeKind.AUTHENTICATES_AS)
    }
    key_a = "cred:aws:secret:cycle/aws-access-key-a:stored"
    key_b = "cred:aws:secret:cycle/aws-access-key-b:stored"
    role_a = "aws:role:arn:aws:iam::111122223333:role/cycle-role-a"
    role_b = "aws:role:arn:aws:iam::111122223333:role/cycle-role-b"
    assert auth == {
        (key_a, role_b, EvidenceClass.ASSUMED),
        (key_b, role_a, EvidenceClass.ASSUMED),
    }
    assert edges_of(build, EdgeKind.CAN_MODIFY) == ()
    reads = {(edge.src, edge.dst) for edge in edges_of(build, EdgeKind.CAN_READ_VALUE)}
    assert (role_b, "aws:ssm:/cycle/api-token-leaf") in reads


def test_local_composite_steps_share_the_calling_job_scope(fixtures_dir: Path) -> None:
    build = build_fixture(fixtures_dir, "fx06-composite")
    assert_graph_invariants(build)
    setup = "action:.github/actions/setup@local"
    nested = "action:.github/actions/nested@local"
    assert any(node.id == setup for node in build.graph.nodes)
    assert any(node.id == nested for node in build.graph.nodes)
    runs = {(edge.src, edge.dst) for edge in edges_of(build, EdgeKind.RUNS_IN)}
    assert ("job:.github/workflows/build.yml#build", setup) in runs
    assert ("job:.github/workflows/build.yml#build", nested) in runs
    secrets = [node for node in build.graph.nodes if node.label == "NPM_TOKEN"]
    assert len(secrets) == 1
    holds = [edge for edge in edges_of(build, EdgeKind.HOLDS) if edge.dst == secrets[0].id]
    assert [edge.src for edge in holds] == ["job:.github/workflows/build.yml#build"]


def test_literal_credentials_record_kind_and_length_but_never_the_value() -> None:
    token = "ghp_" + "A" * 36
    build = build_inline(
        f"""
name: Leak
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    env:
      TOKEN: {token}
    steps:
      - run: echo build
"""
    )
    assert_graph_invariants(build)
    literal = [node for node in build.graph.nodes if node.attrs.get("literal")]
    assert len(literal) == 1
    node = literal[0]
    assert node.attrs["credential_kind"] == CredentialKind.GITHUB_TOKEN.value
    assert node.attrs["length"] == len(token)
    assert node.attrs["lifetime"] == Lifetime.PERSISTENT.value
    assert token not in node.label
    assert token not in build.graph.model_dump_json()
    assert token not in str(build.diagnostics)


def test_static_keys_bind_to_an_unbound_identity_and_wildcard_secrets() -> None:
    build = build_inline(
        f"""
name: Static
on: push
permissions:
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    env:
      ALL_SECRETS: ${{{{ toJSON(secrets) }}}}
    steps:
      - uses: aws-actions/configure-aws-credentials@{SHA}
        with:
          aws-access-key-id: ${{{{ secrets.PROD_ACCESS_KEY_ID }}}}
          aws-secret-access-key: ${{{{ secrets.PROD_SECRET_ACCESS_KEY }}}}
          role-to-assume: arn:aws:iam::111122223333:role/deploy
"""
    )
    assert_graph_invariants(build)
    nodes = {node.id: node for node in build.graph.nodes}
    job_id = "job:.github/workflows/test.yml#deploy"
    access_key = nodes[f"cred:{job_id}:PROD_ACCESS_KEY_ID"]
    assert access_key.attrs["credential_kind"] == CredentialKind.AWS_ACCESS_KEY.value
    assert access_key.attrs["static_aws_key"] is True
    wildcard = nodes[f"cred:{job_id}:*"]
    assert wildcard.attrs["wildcard"] is True
    assert any(
        edge.dst == wildcard.id and edge.confidence is EvidenceClass.UNKNOWN
        for edge in edges_of(build, EdgeKind.HOLDS)
    )
    auth = [
        edge for edge in edges_of(build, EdgeKind.AUTHENTICATES_AS) if edge.src == access_key.id
    ]
    assert [edge.dst for edge in auth] == ["ext:aws-identity-unbound"]
    wildcard_holds = [edge for edge in edges_of(build, EdgeKind.HOLDS) if edge.dst == wildcard.id]
    assert len(wildcard_holds) == 1
    assert wildcard_holds[0].confidence is EvidenceClass.UNKNOWN


def test_unresolved_trust_becomes_an_unknown_assume_edge() -> None:
    role = RoleFact(
        id=ROLE_DEPLOY,
        address="aws_iam_role.deploy_prod",
        name="deploy-prod",
        arn="arn:aws:iam::111122223333:role/deploy-prod",
        trust_unresolved=True,
        evidence=(evidence(EvidenceClass.DERIVED, rule="TF.trust", file="main.tf", line=4),),
    )
    cloud = empty_cloud()
    cloud = CloudFacts(
        roles=(role,),
        sinks=(),
        providers=(),
        externals=(),
        policy_context=PolicyContext(),
        diagnostics=(),
    )
    build = build_inline(
        """
name: Deploy
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
    )
    assert_graph_invariants(build)
    assume = edges_of(build, EdgeKind.CAN_ASSUME)
    assert len(assume) == 1
    edge = assume[0]
    assert edge.dst == ROLE_DEPLOY
    assert edge.confidence is EvidenceClass.UNKNOWN
    assert edge.attrs["unresolved"] is True
    assert "session_credential" not in edge.attrs
    assert "A-TRUST-UNMODELLED" in build.assumptions_used
    assert not any(
        node.attrs.get("credential_kind") == CredentialKind.STS_SESSION.value
        for node in build.graph.nodes
    )


def test_unresolved_policy_bodies_create_unknown_read_edges() -> None:
    sink = SinkFact(
        id="aws:secret:prod/unknown-policy",
        name="prod/unknown-policy",
        sink_type=SinkType.SECRETSMANAGER_SECRET,
        arn="arn:aws:secretsmanager:us-east-1:111122223333:secret:prod/unknown-policy-??????",
        credential_kind=CredentialKind.GENERIC_SECRET,
        criticality=55,
        evidence=(evidence(EvidenceClass.DERIVED, rule="TF.secret", file="main.tf", line=8),),
    )
    role = RoleFact(
        id="aws:role:aws_iam_role.unresolved_policy",
        address="aws_iam_role.unresolved_policy",
        name="unresolved-policy",
        arn="arn:aws:iam::111122223333:role/unresolved-policy",
        unresolved_policy_refs=("arn:aws:iam::111122223333:policy/missing",),
        evidence=(evidence(EvidenceClass.DERIVED, rule="TF.role", file="main.tf", line=12),),
    )
    cloud = CloudFacts(
        roles=(role,),
        sinks=(sink,),
        providers=(),
        externals=(),
        policy_context=PolicyContext(),
        diagnostics=(),
    )
    build = build_inline(
        """
name: Policy
on: push
jobs:
  read:
    runs-on: ubuntu-latest
    steps:
      - run: echo policy
""",
        cloud=cloud,
    )
    assert_graph_invariants(build)
    reads = edges_of(build, EdgeKind.CAN_READ_VALUE)
    assert len(reads) == 1
    assert reads[0].dst == sink.id
    assert reads[0].confidence is EvidenceClass.UNKNOWN
    assert reads[0].attrs["decision"] == "unknown"
    assert reads[0].attrs["unresolved_policy_refs"] == ["arn:aws:iam::111122223333:policy/missing"]
    assert "A-POLICY-UNMODELLED" in build.assumptions_used


def test_expression_permissions_produce_unknown_mint_without_claiming_oidc_env() -> None:
    build = build_inline(
        """
name: Unknown
on: push
permissions: ${{ inputs.permissions }}
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo deploy
"""
    )
    assert_graph_invariants(build)
    mint = edges_of(build, EdgeKind.CAN_MINT)
    assert len(mint) == 1
    assert mint[0].confidence is EvidenceClass.UNKNOWN
    assert "assumption" not in mint[0].attrs
    assert "A-OIDC-ENV" not in build.assumptions_used
    assert edges_of(build, EdgeKind.CAN_ASSUME) == ()
    job = next(node for node in build.graph.nodes if node.kind is NodeKind.JOB)
    assert job.attrs["id_token_write"] is None
    assert job.attrs["permissions_confidence"] == EvidenceClass.DECLARED.value


def test_graph_budget_truncates_without_dangling_edges(fixtures_dir: Path) -> None:
    build = build_fixture(fixtures_dir, "fx07-incident", limits=Limits(max_graph_nodes=6))
    assert build.truncated
    assert len(build.graph.nodes) <= 6
    assert_graph_invariants(build)


def test_two_builds_are_byte_identical(fixtures_dir: Path) -> None:
    first = build_fixture(fixtures_dir, "fx07-incident")
    second = build_fixture(fixtures_dir, "fx07-incident")
    assert first.graph.model_dump_json() == second.graph.model_dump_json()
    assert first.diagnostics == second.diagnostics
    assert first.assumptions_used == second.assumptions_used
