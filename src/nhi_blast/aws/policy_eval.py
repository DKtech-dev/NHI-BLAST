"""IAM policy decision procedure (spec 9.4).

can(role, action, resource) collects the role inline policies, the attached managed
policies available in the context and any same-account resource policy, then applies
explicit-deny-wins semantics. A conditional allow becomes CONDITIONAL_ALLOW with
ASSUMED evidence; a resource pattern that can cover resources outside the supplied
inputs is flagged so the graph can add a potential edge instead of a confirmed one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from nhi_blast.aws.conditions import ConditionMode, ConditionTruth, evaluate_conditions
from nhi_blast.aws.glob import (
    glob_intersects,
    glob_match,
    has_wildcard,
    literal_prefix,
)
from nhi_blast.aws.sinks import (
    candidate_arns,
    kms_key_arn,
    modify_actions,
    read_actions,
    uses_default_kms,
)
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.models import (
    Decision,
    DecisionResult,
    PolicyContext,
    PolicyEffect,
    RoleFact,
    SinkFact,
    Statement,
)

ASSUMPTION_NO_SCP = "A-NO-SCP"
ASSUMPTION_SCOPE_INPUT = "A-SCOPE-INPUT"
ASSUMPTION_KMS = "A-KMS-UNMODELLED"


def _action_applies(statement: Statement, action: str) -> bool:
    if statement.actions and not any(
        glob_match(pattern, action, fold=True) for pattern in statement.actions
    ):
        return False
    if statement.not_actions and any(
        glob_match(pattern, action, fold=True) for pattern in statement.not_actions
    ):
        return False
    return bool(statement.actions or statement.not_actions)


def _resource_applies(statement: Statement, resource_globs: tuple[str, ...]) -> bool:
    if statement.resources and not any(
        glob_intersects(pattern, candidate)
        for pattern in statement.resources
        for candidate in resource_globs
    ):
        return False
    if statement.not_resources and any(
        glob_intersects(pattern, candidate)
        for pattern in statement.not_resources
        for candidate in resource_globs
    ):
        return False
    return bool(statement.resources or statement.not_resources)


def _covers_outside_inputs(pattern: str) -> bool:
    if pattern.strip() == "*":
        return True
    parts = pattern.split(":")
    if len(parts) >= 6:
        return parts[3] == "*" or parts[4] == "*"
    return not pattern.startswith("arn:")


class _StatementOutcome:
    __slots__ = ("conditional", "effect", "reasons", "statement")

    def __init__(
        self,
        statement: Statement,
        effect: PolicyEffect,
        conditional: bool,
        reasons: tuple[str, ...],
    ) -> None:
        self.statement = statement
        self.effect = effect
        self.conditional = conditional
        self.reasons = reasons


def _outcomes(
    statements: Sequence[Statement], action: str, resource_globs: tuple[str, ...]
) -> tuple[list[_StatementOutcome], bool]:
    outcomes: list[_StatementOutcome] = []
    external_wildcard = False
    for statement in statements:
        if not _action_applies(statement, action):
            continue
        if not _resource_applies(statement, resource_globs):
            continue
        evaluation = evaluate_conditions(
            statement.conditions, {}, mode=ConditionMode.CONCRETE, supported_keys=None
        )
        if evaluation.truth is ConditionTruth.FALSE:
            continue
        reasons = tuple(evaluation.reasons)
        if statement.effect is PolicyEffect.ALLOW and any(
            _covers_outside_inputs(pattern) for pattern in statement.resources
        ):
            external_wildcard = True
        outcomes.append(
            _StatementOutcome(
                statement=statement,
                effect=statement.effect,
                conditional=evaluation.truth is ConditionTruth.UNRESOLVED,
                reasons=reasons,
            )
        )
    return outcomes, external_wildcard


def _statement_label(statement: Statement) -> str:
    source = statement.evidence[0].location() if statement.evidence else "policy document"
    sid = f" sid={statement.sid}" if statement.sid else ""
    return f"{statement.effect.value}{sid} at {source}"


def _collect_statements(
    role: RoleFact, ctx: PolicyContext, extra: Sequence[Statement]
) -> list[Statement]:
    statements: list[Statement] = list(role.inline_statements)
    for arn in role.managed_policy_arns:
        statements.extend(ctx.managed_policies.get(arn, ()))
    statements.extend(extra)
    return statements


def _action_could_match(statement: Statement, action: str) -> bool:
    if statement.actions:
        return any(glob_match(pattern, action, fold=True) for pattern in statement.actions)
    if statement.not_actions:
        return not any(glob_match(pattern, action, fold=True) for pattern in statement.not_actions)
    return False


@dataclass(frozen=True, slots=True)
class CandidateFilter:
    """Conservative pre-filter for role/sink policy evaluation.

    Holds resource patterns from ALLOW statements whose action patterns can match
    one of the requested actions. Concrete candidate ARNs are checked against the
    patterns' literal prefixes; a candidate that is itself a glob (for example an
    unknown region or account) is intersected exactly, because a wildcard could
    absorb literal pattern text. Conditions are ignored on purpose: the filter may
    admit extra pairs, but it never drops a pair that could produce an ALLOW or
    CONDITIONAL_ALLOW edge.
    """

    prefixes: tuple[str, ...]
    exact_patterns: tuple[str, ...]
    wildcard_patterns: tuple[str, ...]
    not_resources_only: bool

    def could_apply(self, candidates: Sequence[str]) -> bool:
        if self.not_resources_only:
            return True
        for candidate in candidates:
            if has_wildcard(candidate):
                if any(glob_match(candidate, pattern) for pattern in self.exact_patterns):
                    return True
                if any(glob_intersects(pattern, candidate) for pattern in self.wildcard_patterns):
                    return True
                continue
            lowered = candidate.lower()
            if any(lowered.startswith(prefix) for prefix in self.prefixes):
                return True
        return False


def action_filter(role: RoleFact, ctx: PolicyContext, actions: Sequence[str]) -> CandidateFilter:
    """Statements that could allow at least one of ``actions`` on some resource."""
    prefixes: set[str] = set()
    exact_patterns: set[str] = set()
    wildcard_patterns: set[str] = set()
    not_resources_only = False
    for statement in _collect_statements(role, ctx, ()):
        if statement.effect is not PolicyEffect.ALLOW:
            continue
        if not any(_action_could_match(statement, action) for action in actions):
            continue
        if statement.resources:
            for pattern in statement.resources:
                prefixes.add(literal_prefix(pattern).lower())
                if has_wildcard(pattern):
                    wildcard_patterns.add(pattern)
                else:
                    exact_patterns.add(pattern)
        elif statement.not_resources:
            not_resources_only = True
    return CandidateFilter(
        prefixes=tuple(sorted(prefixes)),
        exact_patterns=tuple(sorted(exact_patterns)),
        wildcard_patterns=tuple(sorted(wildcard_patterns)),
        not_resources_only=not_resources_only,
    )


def evaluate_action(
    role: RoleFact,
    action: str,
    resource: str,
    ctx: PolicyContext,
    *,
    extra_statements: Sequence[Statement] = (),
) -> DecisionResult:
    """Evaluate one action against one resource glob."""
    statements = _collect_statements(role, ctx, extra_statements)
    resource_globs = (resource,)
    outcomes, external_wildcard = _outcomes(statements, action, resource_globs)
    assumptions: list[str] = []
    if not role.boundary_supplied:
        assumptions.append(ASSUMPTION_NO_SCP)
    if external_wildcard:
        assumptions.append(ASSUMPTION_SCOPE_INPUT)

    definite_denies = [o for o in outcomes if o.effect is PolicyEffect.DENY and not o.conditional]
    conditional_denies = [o for o in outcomes if o.effect is PolicyEffect.DENY and o.conditional]
    definite_allows = [o for o in outcomes if o.effect is PolicyEffect.ALLOW and not o.conditional]
    conditional_allows = [o for o in outcomes if o.effect is PolicyEffect.ALLOW and o.conditional]

    if definite_denies:
        return DecisionResult(
            decision=Decision.DENY,
            evidence_class=EvidenceClass.DERIVED,
            reasons=tuple(_statement_label(o.statement) for o in definite_denies),
            assumptions=tuple(assumptions),
            conditional_reasons=tuple(_statement_label(o.statement) for o in conditional_denies),
            external_wildcard=external_wildcard,
        )

    if definite_allows:
        if role.boundary_supplied:
            boundary = _boundary_outcome(role, action, resource_globs)
            if boundary is Decision.DENY or boundary is Decision.NOT_APPLICABLE:
                return DecisionResult(
                    decision=Decision.DENY,
                    evidence_class=EvidenceClass.DERIVED,
                    reasons=("permissions boundary does not allow this action",),
                    assumptions=tuple(assumptions),
                    external_wildcard=external_wildcard,
                )
            if boundary is Decision.CONDITIONAL_ALLOW:
                return DecisionResult(
                    decision=Decision.CONDITIONAL_ALLOW,
                    evidence_class=EvidenceClass.ASSUMED,
                    reasons=tuple(_statement_label(o.statement) for o in definite_allows),
                    assumptions=tuple(assumptions),
                    conditional_reasons=("permissions boundary allows conditionally",),
                    external_wildcard=external_wildcard,
                )
        return DecisionResult(
            decision=Decision.ALLOW,
            evidence_class=EvidenceClass.DERIVED,
            reasons=tuple(_statement_label(o.statement) for o in definite_allows),
            assumptions=tuple(assumptions),
            conditional_reasons=tuple(_statement_label(o.statement) for o in conditional_denies),
            external_wildcard=external_wildcard,
        )

    if conditional_allows:
        return DecisionResult(
            decision=Decision.CONDITIONAL_ALLOW,
            evidence_class=EvidenceClass.ASSUMED,
            reasons=tuple(_statement_label(o.statement) for o in conditional_allows),
            assumptions=tuple(assumptions),
            conditional_reasons=tuple(reason for o in conditional_allows for reason in o.reasons),
            external_wildcard=external_wildcard,
        )

    if conditional_denies or definite_denies:
        return DecisionResult(
            decision=Decision.DENY,
            evidence_class=EvidenceClass.DERIVED,
            reasons=tuple(
                _statement_label(o.statement) for o in definite_denies + conditional_denies
            ),
            assumptions=tuple(assumptions),
            external_wildcard=external_wildcard,
        )
    return DecisionResult(
        decision=Decision.NOT_APPLICABLE,
        evidence_class=EvidenceClass.DERIVED,
        reasons=("implicit deny: no statement matches",),
        assumptions=tuple(assumptions),
        external_wildcard=external_wildcard,
    )


def _boundary_outcome(role: RoleFact, action: str, resource_globs: tuple[str, ...]) -> Decision:
    outcomes, _ = _outcomes(role.boundary_statements, action, resource_globs)
    if any(o.effect is PolicyEffect.DENY and not o.conditional for o in outcomes):
        return Decision.DENY
    if any(o.effect is PolicyEffect.ALLOW and not o.conditional for o in outcomes):
        return Decision.ALLOW
    if any(o.effect is PolicyEffect.ALLOW and o.conditional for o in outcomes):
        return Decision.CONDITIONAL_ALLOW
    return Decision.NOT_APPLICABLE


def _best_result(results: list[DecisionResult]) -> DecisionResult:
    for decision in (
        Decision.ALLOW,
        Decision.CONDITIONAL_ALLOW,
        Decision.DENY,
        Decision.NOT_APPLICABLE,
    ):
        for result in results:
            if result.decision is decision:
                merged_assumptions = tuple(
                    sorted({assumption for r in results for assumption in r.assumptions})
                )
                return DecisionResult(
                    decision=result.decision,
                    evidence_class=result.evidence_class,
                    reasons=result.reasons,
                    assumptions=merged_assumptions,
                    conditional_reasons=result.conditional_reasons,
                    external_wildcard=any(r.external_wildcard for r in results),
                )
    return DecisionResult(decision=Decision.NOT_APPLICABLE, evidence_class=EvidenceClass.DERIVED)


def can_read(
    role: RoleFact,
    sink: SinkFact,
    ctx: PolicyContext,
    *,
    region: str | None = None,
    account: str | None = None,
) -> DecisionResult:
    arns = candidate_arns(sink, region=region, account=account)
    results = [
        evaluate_action(role, action, arn, ctx)
        for action in read_actions(sink.sink_type)
        for arn in arns
    ]
    best = _best_result(results)
    if best.decision in (Decision.NOT_APPLICABLE, Decision.DENY):
        return best
    if uses_default_kms(sink):
        return best
    key_arn = kms_key_arn(sink, region=region, account=account)
    if key_arn is None:
        return best
    kms_result = evaluate_action(role, "kms:Decrypt", key_arn, ctx)
    if kms_result.decision is Decision.ALLOW:
        return best
    assumptions = tuple(sorted({*best.assumptions, ASSUMPTION_KMS}))
    if kms_result.decision is Decision.NOT_APPLICABLE or kms_result.decision is Decision.DENY:
        return DecisionResult(
            decision=Decision.NOT_APPLICABLE,
            evidence_class=EvidenceClass.DERIVED,
            reasons=("customer-managed key is not readable by this role", *kms_result.reasons),
            assumptions=assumptions,
        )
    return DecisionResult(
        decision=Decision.CONDITIONAL_ALLOW,
        evidence_class=EvidenceClass.ASSUMED,
        reasons=best.reasons,
        assumptions=assumptions,
        conditional_reasons=("kms:Decrypt is conditional or unevaluated", *kms_result.reasons),
        external_wildcard=best.external_wildcard,
    )


def can_modify(
    role: RoleFact,
    sink: SinkFact,
    ctx: PolicyContext,
    *,
    region: str | None = None,
    account: str | None = None,
) -> DecisionResult:
    arns = candidate_arns(sink, region=region, account=account)
    results = [
        evaluate_action(role, action, arn, ctx)
        for action in modify_actions(sink.sink_type)
        for arn in arns
    ]
    return _best_result(results)
