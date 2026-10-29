"""Deterministic Report builders shared by reporter tests."""

from __future__ import annotations

from nhi_blast import __version__
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.models import (
    AssumptionUse,
    CredentialKind,
    CredentialRef,
    ECredential,
    Edge,
    EdgeKind,
    Finding,
    GraphData,
    InputFile,
    Inputs,
    Lifetime,
    Node,
    NodeKind,
    Partition,
    Report,
    RotationPlan,
    RotationStep,
    ScenarioReport,
    Severity,
    StepPhase,
    ToolInfo,
    ZCredential,
)

HOSTILE = '</script><img src=x onerror="alert(1)">\x1b[31mred\x00'
SENTINEL = "FIXTURE_ONLY_REPORTER_SENTINEL_DO_NOT_EMIT"


def declared(
    rule: str = "R1", *, file: str = ".github/workflows/release.yml", line: int = 7
) -> Evidence:
    return Evidence(
        cls=EvidenceClass.DECLARED,
        rule=rule,
        file=file,
        line=line,
        detail="declared in repository input",
    )


def make_report(*, hostile: bool = False) -> Report:
    workflow = ".github/workflows/release.yml"
    job_id = f"job:{workflow}#publish"
    role_id = "aws:role:arn:aws:iam::111122223333:role/deploy-prod"
    session_id = f"cred:{role_id}:sts-session"
    sink_id = "aws:secret:prod/db-master"
    value_id = f"cred:{sink_id}:database-password"
    hostile_text = HOSTILE if hostile else "publish"
    evidence = declared(file=workflow, line=14)
    graph = GraphData(
        nodes=(
            Node(
                id=job_id,
                kind=NodeKind.JOB,
                label=hostile_text,
                attrs={"workflow": workflow, "job_id": "publish"},
                evidence=(evidence,),
            ),
            Node(
                id=role_id,
                kind=NodeKind.AWS_ROLE,
                label="deploy-prod",
                attrs={"arn": "arn:aws:iam::111122223333:role/deploy-prod"},
                evidence=(declared("R8", file="tfstate.json", line=21),),
            ),
            Node(
                id=session_id,
                kind=NodeKind.CREDENTIAL,
                label="STS session for deploy-prod",
                attrs={
                    "credential_kind": "STS_SESSION",
                    "lifetime": "session_ttl",
                    "ttl_seconds": 3600,
                    "criticality": 50,
                },
                evidence=(declared("R9", file="tfstate.json", line=31),),
            ),
            Node(
                id=sink_id,
                kind=NodeKind.SINK,
                label=hostile_text if hostile else "prod/db-master",
                attrs={"sink_type": "secretsmanager_secret", "criticality": 100},
                evidence=(declared("R10", file="tfstate.json", line=40),),
            ),
            Node(
                id=value_id,
                kind=NodeKind.CREDENTIAL,
                label="database password",
                attrs={
                    "credential_kind": "DATABASE_PASSWORD",
                    "lifetime": "persistent",
                    "criticality": 100,
                    "survival_window": "until_rotated",
                },
                evidence=(declared("R10", file="tfstate.json", line=40),),
            ),
        ),
        edges=(
            Edge(
                id="edge-runs-in",
                kind=EdgeKind.RUNS_IN,
                src=job_id,
                dst=role_id,
                lifetime=Lifetime.SESSION_TTL,
                confidence=EvidenceClass.DECLARED,
                evidence=(evidence,),
                attrs={"message": "workflow grants id-token: write"},
            ),
            Edge(
                id="edge-holds-session",
                kind=EdgeKind.HOLDS,
                src=job_id,
                dst=session_id,
                lifetime=Lifetime.SESSION_TTL,
                confidence=EvidenceClass.DECLARED,
                evidence=(evidence,),
            ),
            Edge(
                id="edge-reads",
                kind=EdgeKind.CAN_READ_VALUE,
                src=role_id,
                dst=sink_id,
                lifetime=Lifetime.PERSISTENT,
                confidence=EvidenceClass.DECLARED,
                evidence=(declared("R10", file="tfstate.json", line=42),),
            ),
            Edge(
                id="edge-stores",
                kind=EdgeKind.STORES,
                src=sink_id,
                dst=value_id,
                lifetime=Lifetime.PERSISTENT,
                confidence=EvidenceClass.DECLARED,
                evidence=(declared("R10", file="tfstate.json", line=43),),
            ),
        ),
    )
    finding = Finding(
        id="NHB-SURV-001-1234abcd",
        rule="NHB-SURV-001",
        severity=Severity.CRITICAL,
        confidence=EvidenceClass.DECLARED,
        title="Credentials survive revocation of the entrypoint",
        message=hostile_text,
        evidence=(evidence,),
        path=(job_id, role_id, sink_id, value_id),
        path_edges=("edge-runs-in", "edge-reads", "edge-stores"),
        assumptions=("A-STS-TTL",),
        scenario="action:example/action@v1",
    )
    rotation = RotationPlan(
        containment=(
            RotationStep(
                phase=StepPhase.CONTAINMENT,
                order=1,
                credentials=(),
                actions=("Disable the entrypoint workflow.",),
                confidence=EvidenceClass.ASSUMED,
                evidence=(evidence,),
            ),
        ),
        rotation=(
            RotationStep(
                phase=StepPhase.ROTATION,
                order=1,
                generation=1,
                credentials=(
                    CredentialRef(
                        id=value_id,
                        label=hostile_text if hostile else "prod/db-master database password",
                        kind=CredentialKind.DATABASE_PASSWORD,
                        lifetime=Lifetime.PERSISTENT,
                        survival_window="until_rotated",
                        criticality=100,
                        evidence=(evidence,),
                    ),
                ),
                actions=("Rotate the database password.",),
                confidence=EvidenceClass.ASSUMED,
                evidence=(evidence,),
            ),
        ),
        verify=(
            RotationStep(
                phase=StepPhase.VERIFY,
                order=1,
                actions=("Confirm the old value no longer authenticates.",),
                confidence=EvidenceClass.ASSUMED,
                evidence=(evidence,),
            ),
        ),
    )
    scenario = ScenarioReport(
        selector="action:example/action@v1",
        start_nodes=(job_id,),
        partition=Partition(
            R=(session_id,),
            E=(ECredential(credential=session_id, ttl_seconds=3600),),
            Z=(
                ZCredential(
                    credential=value_id,
                    depth=1,
                    lifetime=Lifetime.PERSISTENT,
                    survival_window="until_rotated",
                    criticality=100,
                ),
            ),
        ),
        potential=("edge-reads",),
        potential_nodes=(sink_id,),
        rotation_plan=rotation,
        findings=(finding.id,),
        notes=("Result is a lower bound: 1 unresolved input.",),
    )
    return Report(
        tool=ToolInfo(version=__version__),
        inputs=Inputs(
            digest="a" * 64,
            repo_slug="acme/shop",
            repo_slug_source=".git/config",
            files=(
                InputFile(path=workflow, sha256="b" * 64, kind="workflow"),
                InputFile(path="tfstate.json", sha256="c" * 64, kind="terraform_state"),
            ),
        ),
        scope_and_limits=("closure depth 3", "max graph nodes 500000"),
        assumptions=(
            AssumptionUse(
                id="A-STS-TTL",
                statement="STS credentials expire after the configured duration.",
                verify=False,
                used_by=("edge-runs-in",),
            ),
        ),
        diagnostics=(),
        findings=(finding,),
        graph=graph,
        scenarios=(scenario,),
    )
