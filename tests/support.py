"""Builders for typed domain models used by unit tests.

Each builder fills only the fields the test cares about and keeps model defaults
for everything else, so a test failure points at behaviour rather than fixture
plumbing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.models import (
    PolicyEffect,
    RoleFact,
    Statement,
    SubFormat,
    SubjectCandidate,
)
from nhi_blast.parsers.gha.facts import (
    AwsAuthUse,
    JobFact,
    StepFact,
    Trigger,
    WorkflowFact,
)

PROVIDER_ARN = "arn:aws:iam::111122223333:oidc-provider/token.actions.githubusercontent.com"
ASSUME_ACTION = "sts:AssumeRoleWithWebIdentity"


def evidence(
    cls: EvidenceClass = EvidenceClass.DERIVED,
    *,
    rule: str = "test",
    file: str = "main.tf",
    line: int = 1,
    detail: str = "",
) -> Evidence:
    return Evidence(cls=cls, rule=rule, file=file, line=line, detail=detail)


def statement(
    *,
    effect: PolicyEffect = PolicyEffect.ALLOW,
    actions: Sequence[str] = (ASSUME_ACTION,),
    not_actions: Sequence[str] = (),
    resources: Sequence[str] = (),
    not_resources: Sequence[str] = (),
    principals: Mapping[str, Sequence[str]] | None = None,
    conditions: Mapping[str, Mapping[str, Sequence[str]]] | None = None,
    sid: str | None = None,
) -> Statement:
    if principals is None:
        principals = {"Federated": (PROVIDER_ARN,)}
    return Statement(
        effect=effect,
        actions=tuple(actions),
        not_actions=tuple(not_actions),
        resources=tuple(resources),
        not_resources=tuple(not_resources),
        principals={key: tuple(values) for key, values in principals.items()},
        conditions={
            operator: {claim: tuple(values) for claim, values in key_map.items()}
            for operator, key_map in (conditions or {}).items()
        },
        sid=sid,
        evidence=(evidence(),),
    )


def role(
    *,
    statements: Sequence[Statement] = (),
    inline_statements: Sequence[Statement] = (),
    trust_unresolved: bool = False,
    address: str = "aws_iam_role.test",
    name: str = "test",
    arn: str | None = None,
    max_session_duration: int = 3600,
) -> RoleFact:
    return RoleFact(
        id=f"aws:role:{address}",
        address=address,
        name=name,
        arn=arn,
        max_session_duration=max_session_duration,
        trust_statements=tuple(statements),
        inline_statements=tuple(inline_statements),
        trust_unresolved=trust_unresolved,
        evidence=(evidence(),),
    )


def candidate(
    subject: str = "repo:acme/shop:ref:refs/heads/main",
    *,
    fmt: SubFormat = SubFormat.CLASSIC,
    trigger: str = "push",
    audience: str = "sts.amazonaws.com",
    claims: Mapping[str, str] | None = None,
    evidence_class: EvidenceClass = EvidenceClass.DERIVED,
) -> SubjectCandidate:
    if claims is None:
        claims = {"repository": "acme/shop"}
    return SubjectCandidate(
        subject=subject,
        format=fmt,
        trigger=trigger,
        audience=audience,
        claims=dict(claims),
        evidence_class=evidence_class,
        evidence=(
            evidence(
                evidence_class,
                rule="OIDC.subject",
                file=".github/workflows/release.yml",
                line=5,
            ),
        ),
    )


def job(
    *,
    job_id: str = "publish",
    line: int = 10,
    environment: str | None = None,
    environment_unresolved: bool = False,
    audience: str | None = None,
    name: str | None = None,
) -> JobFact:
    steps: tuple[StepFact, ...] = ()
    if audience is not None:
        steps = (
            StepFact(
                index=0,
                line=line + 1,
                aws_auth=AwsAuthUse(audience=audience, line=line + 1),
            ),
        )
    return JobFact(
        id=job_id,
        line=line,
        name=name,
        environment=environment,
        environment_unresolved=environment_unresolved,
        steps=steps,
    )


def workflow(
    *,
    path: str = ".github/workflows/release.yml",
    name: str | None = "Release",
    triggers: Sequence[Trigger] = (),
) -> WorkflowFact:
    return WorkflowFact(path=path, name=name, triggers=tuple(triggers))
