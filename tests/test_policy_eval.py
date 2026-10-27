"""IAM decision procedure: allow/deny ordering, boundaries, resource policies, KMS."""

from __future__ import annotations

from nhi_blast.aws.policy_eval import (
    ASSUMPTION_KMS,
    ASSUMPTION_NO_SCP,
    ASSUMPTION_SCOPE_INPUT,
    can_modify,
    can_read,
    evaluate_action,
)
from nhi_blast.aws.sinks import modify_actions, read_actions
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.models import (
    Decision,
    PolicyContext,
    PolicyEffect,
    RoleFact,
    SinkFact,
    SinkType,
    Statement,
)

ACCOUNT = "111122223333"
REGION = "us-east-1"
ACTION = "ssm:GetParameter"
RESOURCE = f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/prod/token"
ROLE_ID = "role:test"


def _statement(
    effect: PolicyEffect = PolicyEffect.ALLOW,
    *,
    actions: tuple[str, ...] = (ACTION,),
    resources: tuple[str, ...] = (RESOURCE,),
    not_actions: tuple[str, ...] = (),
    not_resources: tuple[str, ...] = (),
    conditions: dict[str, dict[str, tuple[str, ...]]] | None = None,
) -> Statement:
    return Statement(
        effect=effect,
        actions=actions,
        resources=resources,
        not_actions=not_actions,
        not_resources=not_resources,
        conditions=conditions or {},
    )


def _role(
    *statements: Statement,
    managed: tuple[str, ...] = (),
    boundary: tuple[Statement, ...] = (),
) -> RoleFact:
    return RoleFact(
        id=ROLE_ID,
        address="aws_iam_role.test",
        name="test",
        inline_statements=statements,
        managed_policy_arns=managed,
        boundary_statements=boundary,
        boundary_supplied=bool(boundary),
    )


def _ctx(managed: dict[str, tuple[Statement, ...]] | None = None) -> PolicyContext:
    return PolicyContext(account=ACCOUNT, region=REGION, managed_policies=managed or {})


def _sink(*, arn: str = RESOURCE, kms_key_id: str | None = None) -> SinkFact:
    return SinkFact(
        id="sink:test",
        name="/prod/token",
        sink_type=SinkType.SSM_PARAMETER,
        arn=arn,
        kms_key_id=kms_key_id,
    )


def test_definite_allow_is_derived_with_scope_assumption() -> None:
    result = evaluate_action(_role(_statement()), ACTION, RESOURCE, _ctx())

    assert result.decision is Decision.ALLOW
    assert result.evidence_class is EvidenceClass.DERIVED
    assert ASSUMPTION_NO_SCP in result.assumptions
    assert result.external_wildcard is False


def test_definite_deny_wins_over_allow() -> None:
    role = _role(_statement(), _statement(PolicyEffect.DENY))

    result = evaluate_action(role, ACTION, RESOURCE, _ctx())

    assert result.decision is Decision.DENY
    assert result.evidence_class is EvidenceClass.DERIVED


def test_conditional_deny_does_not_remove_a_definite_allow() -> None:
    conditional_deny = _statement(
        PolicyEffect.DENY,
        conditions={"StringEquals": {"aws:SourceAccount": (ACCOUNT,)}},
    )

    result = evaluate_action(_role(_statement(), conditional_deny), ACTION, RESOURCE, _ctx())

    assert result.decision is Decision.ALLOW
    assert result.conditional_reasons


def test_conditional_allow_only_is_assumed() -> None:
    conditional_allow = _statement(conditions={"StringEquals": {"aws:SourceAccount": (ACCOUNT,)}})

    result = evaluate_action(_role(conditional_allow), ACTION, RESOURCE, _ctx())

    assert result.decision is Decision.CONDITIONAL_ALLOW
    assert result.evidence_class is EvidenceClass.ASSUMED


def test_action_mismatch_is_not_applicable() -> None:
    result = evaluate_action(_role(_statement()), "s3:GetObject", RESOURCE, _ctx())

    assert result.decision is Decision.NOT_APPLICABLE


def test_not_action_and_not_resource_are_applied() -> None:
    not_action = _statement(actions=(), resources=(RESOURCE,), not_actions=("ssm:DeleteParameter",))
    not_resource = _statement(
        actions=(ACTION,),
        resources=(),
        not_resources=("arn:aws:ssm:*:*:parameter/blocked/*",),
    )

    allowed = evaluate_action(_role(not_action), ACTION, RESOURCE, _ctx())
    excluded = evaluate_action(
        _role(not_resource),
        ACTION,
        f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/blocked/token",
        _ctx(),
    )

    assert allowed.decision is Decision.ALLOW
    assert excluded.decision is Decision.NOT_APPLICABLE


def test_managed_policy_statements_are_unioned() -> None:
    policy_arn = f"arn:aws:iam::{ACCOUNT}:policy/reads"
    role = _role(managed=(policy_arn,))

    result = evaluate_action(role, ACTION, RESOURCE, _ctx({policy_arn: (_statement(),)}))

    assert result.decision is Decision.ALLOW


def test_resource_policy_extra_statements_are_unioned() -> None:
    role = _role()

    result = evaluate_action(
        role,
        ACTION,
        RESOURCE,
        _ctx(),
        extra_statements=(_statement(actions=("ssm:GetParameter",)),),
    )

    assert result.decision is Decision.ALLOW


def test_permissions_boundary_limits_a_definite_allow() -> None:
    role = _role(
        _statement(),
        boundary=(_statement(actions=("s3:GetObject",), resources=("*",)),),
    )

    result = evaluate_action(role, ACTION, RESOURCE, _ctx())

    assert result.decision is Decision.DENY
    assert "boundary" in result.reasons[0]


def test_permissions_boundary_conditional_allow_downgrades_to_conditional() -> None:
    conditional = _statement(conditions={"StringEquals": {"aws:SourceAccount": (ACCOUNT,)}})
    role = _role(_statement(), boundary=(conditional,))

    result = evaluate_action(role, ACTION, RESOURCE, _ctx())

    assert result.decision is Decision.CONDITIONAL_ALLOW
    assert result.evidence_class is EvidenceClass.ASSUMED


def test_wildcard_resource_is_flagged_as_outside_input_scope() -> None:
    result = evaluate_action(_role(_statement(resources=("*",))), ACTION, RESOURCE, _ctx())

    assert result.decision is Decision.ALLOW
    assert result.external_wildcard is True
    assert ASSUMPTION_SCOPE_INPUT in result.assumptions


def test_can_read_requires_a_read_action() -> None:
    assert ACTION in read_actions(SinkType.SSM_PARAMETER)

    allowed = can_read(_role(_statement()), _sink(), _ctx(), region=REGION, account=ACCOUNT)
    denied = can_read(_role(), _sink(), _ctx(), region=REGION, account=ACCOUNT)

    assert allowed.decision is Decision.ALLOW
    assert denied.decision is Decision.NOT_APPLICABLE


def test_can_read_with_default_kms_needs_no_kms_statement() -> None:
    sink = _sink(kms_key_id="alias/aws/ssm")

    result = can_read(_role(_statement()), sink, _ctx(), region=REGION, account=ACCOUNT)

    assert result.decision is Decision.ALLOW
    assert ASSUMPTION_KMS not in result.assumptions


def test_can_read_with_customer_key_requires_kms_decrypt() -> None:
    sink = _sink(kms_key_id="key-123")
    key_arn = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/key-123"

    missing = can_read(_role(_statement()), sink, _ctx(), region=REGION, account=ACCOUNT)
    granted = can_read(
        _role(
            _statement(),
            _statement(actions=("kms:Decrypt",), resources=(key_arn,)),
        ),
        sink,
        _ctx(),
        region=REGION,
        account=ACCOUNT,
    )

    assert missing.decision is Decision.NOT_APPLICABLE
    assert "customer-managed key" in missing.reasons[0]
    assert granted.decision is Decision.ALLOW


def test_conditional_kms_decrypt_makes_the_read_conditional() -> None:
    sink = _sink(kms_key_id="key-123")
    key_arn = f"arn:aws:kms:{REGION}:{ACCOUNT}:key/key-123"
    conditional_kms = _statement(
        actions=("kms:Decrypt",),
        resources=(key_arn,),
        conditions={"StringEquals": {"aws:SourceAccount": (ACCOUNT,)}},
    )

    result = can_read(
        _role(_statement(), conditional_kms),
        sink,
        _ctx(),
        region=REGION,
        account=ACCOUNT,
    )

    assert result.decision is Decision.CONDITIONAL_ALLOW
    assert ASSUMPTION_KMS in result.assumptions


def test_can_modify_uses_modify_actions() -> None:
    modify = modify_actions(SinkType.SSM_PARAMETER)
    assert modify

    read_only = can_modify(_role(_statement()), _sink(), _ctx(), region=REGION, account=ACCOUNT)
    writable = can_modify(
        _role(_statement(actions=(modify[0],), resources=(RESOURCE,))),
        _sink(),
        _ctx(),
        region=REGION,
        account=ACCOUNT,
    )

    assert read_only.decision is Decision.NOT_APPLICABLE
    assert writable.decision is Decision.ALLOW
