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

from nhi_blast.aws.conditions import (
    ConditionMode,
    ConditionTruth,
    KeyState,
    Present,
    evaluate_conditions,
)
from nhi_blast.aws.glob import (
    MAX_GLOB_LENGTH,
    GlobRelation,
    glob_match,
    glob_relation,
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
ASSUMPTION_NO_BOUNDARY = "A-NO-BOUNDARY"
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


def _resource_applies(statement: Statement, resource_globs: tuple[str, ...]) -> tuple[bool, bool]:
    """Return (applies, budget_exceeded) for a statement's resource clauses."""
    budget_exceeded = False
    if statement.resources:
        rels = [
            glob_relation(pattern, candidate)
            for pattern in statement.resources
            for candidate in resource_globs
        ]
        if GlobRelation.INTERSECTS not in rels:
            if GlobRelation.BUDGET_EXCEEDED in rels:
                budget_exceeded = True
            else:
                return False, False
    if statement.not_resources and resource_globs:
        all_covered = True
        for candidate in resource_globs:
            candidate_covered = False
            for pattern in statement.not_resources:
                covered, hit_budget = _not_resource_covers(pattern, candidate)
                if hit_budget:
                    budget_exceeded = True
                if covered:
                    candidate_covered = True
                    break
            if not candidate_covered:
                all_covered = False
        if all_covered:
            return False, False
    return bool(statement.resources or statement.not_resources), budget_exceeded


def _not_resource_covers(pattern: str, candidate: str) -> tuple[bool, bool]:
    """Return (covered, budget_exceeded): True iff ``pattern`` covers all of ``candidate``."""
    if len(pattern) > MAX_GLOB_LENGTH or len(candidate) > MAX_GLOB_LENGTH:
        return False, True
    stripped = pattern.strip()
    if stripped and set(stripped) == {"*"}:
        return True, False
    if pattern == candidate:
        return True, False
    if not has_wildcard(candidate):
        rel = glob_relation(pattern, candidate)
        if rel is GlobRelation.INTERSECTS:
            return True, False
        return False, rel is GlobRelation.BUDGET_EXCEEDED
    if pattern.endswith("*"):
        prefix = pattern[:-1]
        if not has_wildcard(prefix) and candidate.startswith(prefix):
            return True, False
    return False, False


def _covers_outside_inputs(pattern: str) -> bool:
    if pattern.strip() == "*":
        return True
    parts = pattern.split(":")
    if len(parts) >= 6:
        return parts[3] == "*" or parts[4] == "*"
    return not pattern.startswith("arn:")


def _role_account(role: RoleFact) -> str | None:
    if not role.arn:
        return None
    parts = role.arn.split(":")
    return parts[4] if len(parts) >= 6 and parts[4] else None


def _role_name_from_arn(role: RoleFact) -> str:
    if role.arn and ":role/" in role.arn:
        return role.arn.rsplit("/", 1)[-1]
    return role.name


def _resource_principal_match(statement: Statement, role: RoleFact) -> tuple[bool, bool]:
    """Return (applies_to_role, is_session_arn_grant) for a resource-policy statement."""
    if not statement.principals:
        return False, False
    values: list[str] = []
    for key, entries in statement.principals.items():
        if key in {"*", "AWS"}:
            values.extend(entries)
    if not values:
        return False, False
    role_arn = role.arn or ""
    acct = _role_account(role)
    role_name = _role_name_from_arn(role)
    session_prefix = f"arn:aws:sts::{acct}:assumed-role/{role_name}/" if acct else ""
    matched = False
    session_arn = False
    for principal in values:
        p = principal.strip()
        if not p:
            continue
        if p == "*":
            matched = True
            continue
        if acct and p in {acct, f"arn:aws:iam::{acct}:root"}:
            matched = True
            continue
        if role_arn and glob_match(p, role_arn, fold=False):
            matched = True
            continue
        if session_prefix and (
            p.startswith(session_prefix) or glob_match(p, f"{session_prefix}session", fold=False)
        ):
            matched = True
            session_arn = True
    return matched, session_arn


class _StatementOutcome:
    __slots__ = ("conditional", "effect", "from_session_arn", "reasons", "statement")

    def __init__(
        self,
        statement: Statement,
        effect: PolicyEffect,
        conditional: bool,
        reasons: tuple[str, ...],
        *,
        from_session_arn: bool = False,
    ) -> None:
        self.statement = statement
        self.effect = effect
        self.conditional = conditional
        self.reasons = reasons
        self.from_session_arn = from_session_arn


def _outcomes(
    statements: Sequence[Statement],
    action: str,
    resource_globs: tuple[str, ...],
    *,
    from_session_arn: bool = False,
) -> tuple[list[_StatementOutcome], bool]:
    outcomes: list[_StatementOutcome] = []
    external_wildcard = False
    for statement in statements:
        if not _action_applies(statement, action):
            continue
        applies, budget_exceeded = _resource_applies(statement, resource_globs)
        if not applies:
            continue
        evaluation = evaluate_conditions(
            statement.conditions, {}, mode=ConditionMode.CONCRETE, supported_keys=None
        )
        if evaluation.truth is ConditionTruth.FALSE:
            continue
        reasons = tuple(evaluation.reasons)
        if budget_exceeded:
            reasons = (*reasons, "D-COND-BUDGET: resource pattern exceeded glob length budget")
        if statement.effect is PolicyEffect.ALLOW and any(
            _covers_outside_inputs(pattern) for pattern in statement.resources
        ):
            external_wildcard = True
        outcomes.append(
            _StatementOutcome(
                statement=statement,
                effect=statement.effect,
                conditional=evaluation.truth is ConditionTruth.UNRESOLVED or budget_exceeded,
                reasons=reasons,
                from_session_arn=from_session_arn,
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
    """Conservative pre-filter for role/sink policy evaluation."""

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
                if any(
                    glob_relation(pattern, candidate) is not GlobRelation.DISJOINT
                    for pattern in self.wildcard_patterns
                ):
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


def _resource_outcomes(
    role: RoleFact,
    resource_statements: Sequence[Statement],
    action: str,
    resource_globs: tuple[str, ...],
) -> tuple[list[_StatementOutcome], bool]:
    outcomes: list[_StatementOutcome] = []
    external_wildcard = False
    for statement in resource_statements:
        matched, is_session_arn = _resource_principal_match(statement, role)
        if not matched:
            continue
        stmt_outcomes, ext = _outcomes(
            (statement,), action, resource_globs, from_session_arn=is_session_arn
        )
        outcomes.extend(stmt_outcomes)
        external_wildcard = external_wildcard or ext
    return outcomes, external_wildcard


def _apply_boundary(
    role: RoleFact,
    action: str,
    resource_globs: tuple[str, ...],
    allows: Sequence[_StatementOutcome],
    *,
    is_conditional: bool,
    base_conditional_reasons: tuple[str, ...],
    assumptions: tuple[str, ...],
    external_wildcard: bool,
) -> DecisionResult:
    """Enforce permissions boundary across both definite and conditional allows."""
    boundary, boundary_reasons = _boundary_outcome(role, action, resource_globs)
    if boundary is Decision.DENY:
        return DecisionResult(
            decision=Decision.DENY,
            evidence_class=EvidenceClass.DERIVED,
            reasons=("permissions boundary denies this action",),
            assumptions=assumptions,
            external_wildcard=external_wildcard,
        )
    # Same-account resource-policy Allow naming an assumed-role session ARN bypasses
    # permissions-boundary implicit deny; only explicit Deny in the boundary overrides it.
    session_bypass = [o for o in allows if o.from_session_arn]
    if boundary is Decision.NOT_APPLICABLE:
        if not session_bypass:
            return DecisionResult(
                decision=Decision.DENY,
                evidence_class=EvidenceClass.DERIVED,
                reasons=("permissions boundary does not allow this action",),
                assumptions=assumptions,
                external_wildcard=external_wildcard,
            )
        allows = session_bypass
    elif boundary is Decision.CONDITIONAL_ALLOW and not session_bypass:
        merged_reasons = (
            *base_conditional_reasons,
            "permissions boundary allows conditionally",
            *boundary_reasons,
        )
        return DecisionResult(
            decision=Decision.CONDITIONAL_ALLOW,
            evidence_class=EvidenceClass.ASSUMED,
            reasons=tuple(_statement_label(o.statement) for o in allows),
            assumptions=assumptions,
            conditional_reasons=merged_reasons,
            external_wildcard=external_wildcard,
        )

    if is_conditional or base_conditional_reasons:
        return DecisionResult(
            decision=Decision.CONDITIONAL_ALLOW,
            evidence_class=EvidenceClass.ASSUMED,
            reasons=tuple(_statement_label(o.statement) for o in allows),
            assumptions=assumptions,
            conditional_reasons=base_conditional_reasons,
            external_wildcard=external_wildcard,
        )
    return DecisionResult(
        decision=Decision.ALLOW,
        evidence_class=EvidenceClass.DERIVED,
        reasons=tuple(_statement_label(o.statement) for o in allows),
        assumptions=assumptions,
        external_wildcard=external_wildcard,
    )


def evaluate_action(
    role: RoleFact,
    action: str,
    resource: str,
    ctx: PolicyContext,
    *,
    extra_statements: Sequence[Statement] = (),
    resource_statements: Sequence[Statement] = (),
) -> DecisionResult:
    """Evaluate one action against one resource glob."""
    statements = _collect_statements(role, ctx, extra_statements)
    resource_globs = (resource,)
    id_outcomes, id_ext = _outcomes(statements, action, resource_globs)
    rp_outcomes, rp_ext = _resource_outcomes(role, resource_statements, action, resource_globs)
    outcomes = id_outcomes + rp_outcomes
    external_wildcard = id_ext or rp_ext

    assumptions_list: list[str] = [ASSUMPTION_NO_SCP]
    if not role.boundary_supplied:
        assumptions_list.append(ASSUMPTION_NO_BOUNDARY)
    if external_wildcard:
        assumptions_list.append(ASSUMPTION_SCOPE_INPUT)
    assumptions = tuple(sorted(set(assumptions_list)))

    definite_denies = [o for o in outcomes if o.effect is PolicyEffect.DENY and not o.conditional]
    conditional_denies = [o for o in outcomes if o.effect is PolicyEffect.DENY and o.conditional]
    definite_allows = [o for o in outcomes if o.effect is PolicyEffect.ALLOW and not o.conditional]
    conditional_allows = [o for o in outcomes if o.effect is PolicyEffect.ALLOW and o.conditional]

    if definite_denies:
        return DecisionResult(
            decision=Decision.DENY,
            evidence_class=EvidenceClass.DERIVED,
            reasons=tuple(_statement_label(o.statement) for o in definite_denies),
            assumptions=assumptions,
            conditional_reasons=tuple(_statement_label(o.statement) for o in conditional_denies),
            external_wildcard=external_wildcard,
        )

    possible_deny_reasons = tuple(
        reason for o in conditional_denies for reason in (_statement_label(o.statement), *o.reasons)
    )

    if definite_allows:
        if role.boundary_supplied:
            return _apply_boundary(
                role,
                action,
                resource_globs,
                definite_allows,
                is_conditional=bool(conditional_denies),
                base_conditional_reasons=possible_deny_reasons,
                assumptions=assumptions,
                external_wildcard=external_wildcard,
            )
        if conditional_denies:
            return DecisionResult(
                decision=Decision.CONDITIONAL_ALLOW,
                evidence_class=EvidenceClass.ASSUMED,
                reasons=tuple(_statement_label(o.statement) for o in definite_allows),
                assumptions=assumptions,
                conditional_reasons=possible_deny_reasons,
                external_wildcard=external_wildcard,
            )
        return DecisionResult(
            decision=Decision.ALLOW,
            evidence_class=EvidenceClass.DERIVED,
            reasons=tuple(_statement_label(o.statement) for o in definite_allows),
            assumptions=assumptions,
            external_wildcard=external_wildcard,
        )

    if conditional_allows:
        cond_reasons = (
            *(reason for o in conditional_allows for reason in o.reasons),
            *possible_deny_reasons,
        )
        if role.boundary_supplied:
            return _apply_boundary(
                role,
                action,
                resource_globs,
                conditional_allows,
                is_conditional=True,
                base_conditional_reasons=cond_reasons,
                assumptions=assumptions,
                external_wildcard=external_wildcard,
            )
        return DecisionResult(
            decision=Decision.CONDITIONAL_ALLOW,
            evidence_class=EvidenceClass.ASSUMED,
            reasons=tuple(_statement_label(o.statement) for o in conditional_allows),
            assumptions=assumptions,
            conditional_reasons=cond_reasons,
            external_wildcard=external_wildcard,
        )

    if conditional_denies or definite_denies:
        return DecisionResult(
            decision=Decision.DENY,
            evidence_class=EvidenceClass.DERIVED,
            reasons=tuple(
                _statement_label(o.statement) for o in definite_denies + conditional_denies
            ),
            assumptions=assumptions,
            external_wildcard=external_wildcard,
        )
    return DecisionResult(
        decision=Decision.NOT_APPLICABLE,
        evidence_class=EvidenceClass.DERIVED,
        reasons=("implicit deny: no statement matches",),
        assumptions=assumptions,
        external_wildcard=external_wildcard,
    )


def _boundary_outcome(
    role: RoleFact, action: str, resource_globs: tuple[str, ...]
) -> tuple[Decision, tuple[str, ...]]:
    outcomes, _ = _outcomes(role.boundary_statements, action, resource_globs)
    if any(o.effect is PolicyEffect.DENY and not o.conditional for o in outcomes):
        return Decision.DENY, ()
    conditional_denies = [o for o in outcomes if o.effect is PolicyEffect.DENY and o.conditional]
    possible_deny_reasons = tuple(
        reason for o in conditional_denies for reason in (_statement_label(o.statement), *o.reasons)
    )
    if any(o.effect is PolicyEffect.ALLOW and not o.conditional for o in outcomes):
        if conditional_denies:
            return Decision.CONDITIONAL_ALLOW, possible_deny_reasons
        return Decision.ALLOW, ()
    conditional_allows = [o for o in outcomes if o.effect is PolicyEffect.ALLOW and o.conditional]
    if conditional_allows:
        reasons = (
            *(reason for o in conditional_allows for reason in o.reasons),
            *possible_deny_reasons,
        )
        return Decision.CONDITIONAL_ALLOW, reasons
    return Decision.NOT_APPLICABLE, ()


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
        evaluate_action(
            role,
            action,
            arn,
            ctx,
            resource_statements=sink.resource_policy_statements,
        )
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
    if kms_result.decision is Decision.DENY:
        return DecisionResult(
            decision=Decision.DENY,
            evidence_class=EvidenceClass.DERIVED,
            reasons=("customer-managed key is not readable by this role", *kms_result.reasons),
            assumptions=assumptions,
        )
    conditional_reason = (
        "customer-managed key policy is unmodelled; kms:Decrypt not granted in identity policy"
        if kms_result.decision is Decision.NOT_APPLICABLE
        else "kms:Decrypt is conditional or unevaluated"
    )
    return DecisionResult(
        decision=Decision.CONDITIONAL_ALLOW,
        evidence_class=EvidenceClass.ASSUMED,
        reasons=best.reasons,
        assumptions=assumptions,
        conditional_reasons=(conditional_reason, *kms_result.reasons),
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
        evaluate_action(
            role,
            action,
            arn,
            ctx,
            resource_statements=sink.resource_policy_statements,
        )
        for action in modify_actions(sink.sink_type)
        for arn in arns
    ]
    return _best_result(results)


PERSISTENCE_ACTIONS: tuple[str, ...] = (
    "iam:CreateAccessKey",
    "iam:UpdateAssumeRolePolicy",
    "iam:PutRolePolicy",
    "iam:AttachRolePolicy",
    "iam:CreateLoginProfile",
    "iam:AddUserToGroup",
)


def persistence_capabilities(
    role: RoleFact, ctx: PolicyContext
) -> tuple[tuple[str, DecisionResult], ...]:
    """Return IAM persistence actions this role is allowed (definitely or conditionally) to call."""
    found: list[tuple[str, DecisionResult]] = []
    for action in PERSISTENCE_ACTIONS:
        res = evaluate_action(role, action, "*", ctx)
        if res.decision in (Decision.ALLOW, Decision.CONDITIONAL_ALLOW):
            found.append((action, res))
    return tuple(found)


def can_assume_role(
    source_role: RoleFact, target_role: RoleFact, ctx: PolicyContext
) -> DecisionResult:
    """Evaluate intra-input STS role chaining: source_role -> target_role."""
    if not target_role.arn or source_role.id == target_role.id:
        return DecisionResult(
            decision=Decision.NOT_APPLICABLE, evidence_class=EvidenceClass.DERIVED
        )
    id_res = evaluate_action(source_role, "sts:AssumeRole", target_role.arn, ctx)
    if id_res.decision not in (Decision.ALLOW, Decision.CONDITIONAL_ALLOW):
        return DecisionResult(
            decision=Decision.NOT_APPLICABLE, evidence_class=EvidenceClass.DERIVED
        )
    # Match target trust statements for sts:AssumeRole from source_role; explicit Deny wins.
    trust_context: dict[str, KeyState] = {}
    source_account = _role_account(source_role)
    if source_account is not None:
        trust_context["aws:PrincipalAccount"] = Present((source_account,))
    if source_role.arn:
        trust_context["aws:PrincipalArn"] = Present((source_role.arn,))
    trust_matches: list[tuple[Statement, bool]] = []
    for stmt in target_role.trust_statements:
        matched, _ = _resource_principal_match(stmt, source_role)
        if not matched or not _action_applies(stmt, "sts:AssumeRole"):
            continue
        if stmt.conditions:
            cond_eval = evaluate_conditions(
                stmt.conditions,
                trust_context,
                mode=ConditionMode.CANDIDATE,
                supported_keys=None,
            )
            if cond_eval.truth is ConditionTruth.FALSE:
                continue
            is_conditional = cond_eval.truth is ConditionTruth.UNRESOLVED
        else:
            is_conditional = False
        trust_matches.append((stmt, is_conditional))
    if any(stmt.effect is PolicyEffect.DENY and not cond for stmt, cond in trust_matches):
        return DecisionResult(decision=Decision.DENY, evidence_class=EvidenceClass.DERIVED)
    trust_allows = [
        (stmt, cond) for stmt, cond in trust_matches if stmt.effect is PolicyEffect.ALLOW
    ]
    if not trust_allows:
        return DecisionResult(
            decision=Decision.NOT_APPLICABLE, evidence_class=EvidenceClass.DERIVED
        )
    conditional = (
        id_res.decision is Decision.CONDITIONAL_ALLOW
        or all(cond for _, cond in trust_allows)
        or any(stmt.effect is PolicyEffect.DENY and cond for stmt, cond in trust_matches)
    )
    return DecisionResult(
        decision=Decision.CONDITIONAL_ALLOW if conditional else Decision.ALLOW,
        evidence_class=EvidenceClass.ASSUMED if conditional else EvidenceClass.DERIVED,
        reasons=(*id_res.reasons, *(_statement_label(stmt) for stmt, _ in trust_allows)),
        assumptions=id_res.assumptions,
    )
