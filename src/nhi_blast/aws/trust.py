"""AWS trust-policy evaluation against OIDC subject candidates (spec 10.3).

A statement is relevant when it allows sts:AssumeRoleWithWebIdentity for the GitHub
OIDC provider. Conditions are evaluated against the candidate's claim context in
CANDIDATE mode: a positive string operator intersects the policy pattern with the
candidate glob, negative operators are undecidable, and the claims a job cannot fix
statically are reported as additional constraints rather than silently ignored.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from nhi_blast.aws.conditions import (
    _OPERATORS,
    ConditionMode,
    ConditionTruth,
    _split_operator,
    _values,
    evaluate_conditions,
    is_request_context_key,
    required_positive_patterns,
)
from nhi_blast.aws.glob import GlobRelation, glob_match, glob_relation, has_wildcard, literal_prefix
from nhi_blast.aws.solver import SolverStatus, StringPredicate, solve_string_predicates
from nhi_blast.core.data import ConditionKeyRegistry
from nhi_blast.core.evidence import EvidenceClass, rank, weakest
from nhi_blast.core.models import (
    PolicyEffect,
    RoleFact,
    Statement,
    SubjectCandidate,
)

ASSUME_ACTION = "sts:AssumeRoleWithWebIdentity"


@dataclass(frozen=True, slots=True)
class TrustCandidateMatch:
    statement: Statement
    candidate: SubjectCandidate
    truth: ConditionTruth
    conditional: bool
    unresolved_keys: tuple[str, ...]
    dead_keys: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrustAuditAlternative:
    """One relevant Allow statement that is missing a policy-wide control."""

    statement: Statement
    unconstrained: bool
    missing_audience: bool
    dead_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrustEvaluation:
    role_id: str
    matches: tuple[TrustCandidateMatch, ...] = ()
    dead_keys: tuple[str, ...] = ()
    missing_audience: bool = False
    unconstrained: bool = False
    additional_constraints: tuple[str, ...] = ()
    sub_patterns: tuple[str, ...] = ()
    job_workflow_ref_patterns: tuple[str, ...] = ()
    confidence: EvidenceClass = EvidenceClass.DERIVED
    audit_alternatives: tuple[TrustAuditAlternative, ...] = ()


def _action_matches_assume(statement: Statement) -> bool:
    if statement.actions and not any(
        glob_match(pattern, ASSUME_ACTION, fold=True) for pattern in statement.actions
    ):
        return False
    if statement.not_actions and any(
        glob_match(pattern, ASSUME_ACTION, fold=True) for pattern in statement.not_actions
    ):
        return False
    return bool(statement.actions or statement.not_actions)


def _principal_matches_github_oidc(
    statement: Statement,
    provider_host: str,
    *,
    wildcard_keys: tuple[str, ...] = ("*", "Federated"),
) -> bool:
    federated = statement.principals.get("Federated", ())
    suffix = f"oidc-provider/{provider_host}".lower()
    if any(principal.lower().endswith(suffix) for principal in federated):
        return True
    return any("*" in statement.principals.get(key, ()) for key in wildcard_keys)


def is_github_oidc_statement(statement: Statement, provider_host: str) -> bool:
    if statement.effect is not PolicyEffect.ALLOW:
        return False
    if not _action_matches_assume(statement):
        return False
    return _principal_matches_github_oidc(
        statement, provider_host, wildcard_keys=("*", "Federated")
    )


def is_github_oidc_deny_statement(statement: Statement, provider_host: str) -> bool:
    if statement.effect is not PolicyEffect.DENY:
        return False
    if not _action_matches_assume(statement):
        return False
    return _principal_matches_github_oidc(
        statement, provider_host, wildcard_keys=("*", "Federated", "AWS")
    )


def _condition_key_maps(statement: Statement) -> tuple[Mapping[str, Sequence[str]], ...]:
    maps: list[Mapping[str, Sequence[str]]] = []
    for key_map in statement.conditions.values():
        if isinstance(key_map, Mapping):
            maps.append(key_map)
    return tuple(maps)


def _policy_values_for(statements: Sequence[Statement], claim: str) -> tuple[str, ...]:
    """Extract positive string bindings, not presence checks or unresolved exclusions.

    Inspect each conjunct separately: adding Null alongside StringEquals must not
    erase the binding, nor turn the Null operand into a subject breadth pattern.
    """
    values: set[str] = set()
    for statement in statements:
        for operator, key_map in statement.conditions.items():
            patterns = required_positive_patterns({operator: key_map}, claim)
            if patterns:
                values.update(patterns)
    return tuple(sorted(values))


def _context_for(candidate: SubjectCandidate) -> dict[str, frozenset[str]]:
    context: dict[str, frozenset[str]] = {
        "sub": frozenset({candidate.subject}),
        "aud": frozenset({candidate.audience}),
    }
    for claim, value in candidate.claims.items():
        context[claim] = frozenset({value})
    return context


def _normalise_statement(statement: Statement, provider_host: str) -> Statement:
    """Strip the provider-host prefix from condition keys for claim matching.

    AWS trust policies name claims as ``token.actions.githubusercontent.com:sub``
    while the candidate context uses the short claim names ``sub``/``aud``. The
    prefix is provider metadata, not part of the claim.
    """
    prefix_lower = f"{provider_host.lower()}:"
    prefix_len = len(prefix_lower)
    normalized: dict[str, dict[str, tuple[str, ...]]] = {}
    for operator, key_map in statement.conditions.items():
        normalized[operator] = {
            (key[prefix_len:] if key.lower().startswith(prefix_lower) else key): values
            for key, values in key_map.items()
        }
    return statement.model_copy(update={"conditions": normalized})


def _relevant_statements(role: RoleFact, registry: ConditionKeyRegistry) -> list[Statement]:
    return [
        _normalise_statement(statement, registry.provider_host)
        for statement in role.trust_statements
        if is_github_oidc_statement(statement, registry.provider_host)
    ]


def _relevant_deny_statements(role: RoleFact, registry: ConditionKeyRegistry) -> list[Statement]:
    return [
        _normalise_statement(statement, registry.provider_host)
        for statement in role.trust_statements
        if is_github_oidc_deny_statement(statement, registry.provider_host)
    ]


@dataclass(frozen=True, slots=True)
class TrustSubjectFilter:
    """Conservative pre-filter for trust evaluation against one job's candidates.

    A role whose relevant statements all constrain ``sub`` through positive string
    operators can only accept a subject that intersects one of those patterns.
    Concrete subjects use literal prefixes; wildcard-bearing subjects are compared
    exactly, because a wildcard can absorb literal pattern text. Patterns and
    subjects are lowercased so case-insensitive operators only ever admit extra
    pairs. The filter never rules a possible match out.
    """

    prefixes: tuple[str, ...]
    exact_patterns: tuple[str, ...]
    wildcard_patterns: tuple[str, ...]
    unfiltered: bool

    def may_match(self, candidates: Sequence[SubjectCandidate]) -> bool:
        if not candidates:
            return False
        if self.unfiltered:
            return True
        for candidate in candidates:
            subject = candidate.subject.lower()
            if has_wildcard(subject):
                if any(glob_match(subject, pattern) for pattern in self.exact_patterns):
                    return True
                if any(
                    glob_relation(pattern, subject, fold=True) is not GlobRelation.DISJOINT
                    for pattern in self.wildcard_patterns
                ):
                    return True
                continue
            if any(subject.startswith(prefix) for prefix in self.prefixes):
                return True
        return False


def trust_subject_filter(role: RoleFact, registry: ConditionKeyRegistry) -> TrustSubjectFilter:
    relevant = _relevant_statements(role, registry)
    empty = TrustSubjectFilter(
        prefixes=(), exact_patterns=(), wildcard_patterns=(), unfiltered=False
    )
    if not relevant:
        return empty
    unfiltered = TrustSubjectFilter(
        prefixes=(), exact_patterns=(), wildcard_patterns=(), unfiltered=True
    )
    prefixes: set[str] = set()
    exact_patterns: set[str] = set()
    wildcard_patterns: set[str] = set()
    for statement in relevant:
        patterns = required_positive_patterns(statement.conditions, "sub")
        if patterns is None:
            return unfiltered
        for pattern in patterns:
            lowered = pattern.lower()
            prefixes.add(literal_prefix(lowered))
            if has_wildcard(pattern):
                wildcard_patterns.add(lowered)
            else:
                exact_patterns.add(lowered)
    return TrustSubjectFilter(
        prefixes=tuple(sorted(prefixes)),
        exact_patterns=tuple(sorted(exact_patterns)),
        wildcard_patterns=tuple(sorted(wildcard_patterns)),
        unfiltered=False,
    )


def no_match_evaluation(role: RoleFact, registry: ConditionKeyRegistry) -> TrustEvaluation:
    """Evaluation fields for a role that provably accepts no candidate.

    Mirrors the no-match return of :func:`evaluate_trust_statements` without
    evaluating conditions against candidates.
    """
    return _audit_statements(role.id, _relevant_statements(role, registry), registry)


def _statement_dead_keys(statement: Statement, registry: ConditionKeyRegistry) -> tuple[str, ...]:
    supported_lower = {k.lower() for k in registry.supported}
    return tuple(
        sorted(
            {
                str(key).strip()
                for key_map in _condition_key_maps(statement)
                for key in key_map
                if str(key).strip().lower() not in supported_lower
                and not is_request_context_key(str(key).strip())
            }
        )
    )


def _statement_missing_audience(statement: Statement) -> bool:
    return not _policy_values_for((statement,), "aud")


def _statement_unconstrained(statement: Statement, registry: ConditionKeyRegistry) -> bool:
    return not any(
        _policy_values_for((statement,), claim) for claim in registry.required_control_any_of
    )


def _audit_statements(
    role_id: str, relevant: Sequence[Statement], registry: ConditionKeyRegistry
) -> TrustEvaluation:
    # Allow statements are alternatives, not conjuncts. Audit even when no current
    # job matches so the pre-filter and full evaluator report the same controls.
    alternatives: list[TrustAuditAlternative] = []
    for statement in relevant:
        dead = _statement_dead_keys(statement, registry)
        missing_audience = _statement_missing_audience(statement)
        unconstrained = _statement_unconstrained(statement, registry)
        if dead or missing_audience or unconstrained:
            alternatives.append(
                TrustAuditAlternative(
                    statement=statement,
                    unconstrained=unconstrained,
                    missing_audience=missing_audience,
                    dead_keys=dead,
                )
            )
    return TrustEvaluation(
        role_id=role_id,
        dead_keys=tuple(sorted({key for item in alternatives for key in item.dead_keys})),
        missing_audience=any(item.missing_audience for item in alternatives),
        unconstrained=any(item.unconstrained for item in alternatives),
        audit_alternatives=tuple(alternatives),
    )


def _deny_covers_candidate(
    deny_stmt: Statement,
    context: Mapping[str, frozenset[str]],
) -> bool:
    """True only when every concrete instance of a candidate is provably denied."""
    if not deny_stmt.conditions:
        return True
    if not any(has_wildcard(val) for vals in context.values() for val in vals):
        return True
    lower_context = {k.lower(): v for k, v in context.items()}
    for operator_raw, key_map in deny_stmt.conditions.items():
        qualifier, operator, _ = _split_operator(str(operator_raw))
        spec = _OPERATORS.get(operator)
        for raw_key, expected in key_map.items():
            key_lower = str(raw_key).strip().lower()
            cand_values = lower_context.get(key_lower, frozenset())
            if not any(has_wildcard(val) for val in cand_values):
                continue
            if (
                qualifier is not None
                or spec is None
                or spec.negated
                or spec.family not in {"string", "arn"}
            ):
                return False
            raw_vals = _values(expected)
            for cand_val in cand_values:
                if not has_wildcard(cand_val):
                    continue
                res = solve_string_predicates(
                    (
                        StringPredicate(
                            label="candidate",
                            patterns=(cand_val,),
                            negated=False,
                            fold=False,
                            is_glob=True,
                        ),
                        StringPredicate(
                            label="not_deny",
                            patterns=raw_vals,
                            negated=True,
                            fold=spec.relation == "fold",
                            is_glob=spec.relation == "like" or spec.family == "arn",
                        ),
                    )
                )
                if res.status is not SolverStatus.UNSAT:
                    return False
    return True


def evaluate_trust_statements(
    role: RoleFact,
    candidates: Sequence[SubjectCandidate],
    *,
    registry: ConditionKeyRegistry,
) -> TrustEvaluation:
    relevant = _relevant_statements(role, registry)
    deny_statements = _relevant_deny_statements(role, registry)
    audit = _audit_statements(role.id, relevant, registry)
    matches: list[TrustCandidateMatch] = []
    for statement in relevant:
        for candidate in candidates:
            context = _context_for(candidate)
            evaluation = evaluate_conditions(
                statement.conditions,
                context,
                mode=ConditionMode.CANDIDATE,
                supported_keys=registry.supported,
            )
            if evaluation.truth is ConditionTruth.FALSE:
                continue
            denied = False
            deny_conditional = False
            deny_reasons: list[str] = []
            deny_unresolved: list[str] = []
            for deny_stmt in deny_statements:
                deny_eval = evaluate_conditions(
                    deny_stmt.conditions,
                    context,
                    mode=ConditionMode.CANDIDATE,
                    supported_keys=registry.supported,
                )
                if deny_eval.truth is ConditionTruth.TRUE:
                    if _deny_covers_candidate(deny_stmt, context):
                        denied = True
                        break
                    deny_conditional = True
                    deny_reasons.append("deny statement only partially matches wildcard candidate")
                    deny_reasons.extend(deny_eval.reasons)
                    deny_unresolved.extend(deny_eval.unresolved_keys)
                elif deny_eval.truth is ConditionTruth.UNRESOLVED:
                    deny_conditional = True
                    deny_reasons.extend(deny_eval.reasons)
                    deny_unresolved.extend(deny_eval.unresolved_keys)
            if denied:
                continue
            conditional = evaluation.truth is ConditionTruth.UNRESOLVED or deny_conditional
            truth = ConditionTruth.UNRESOLVED if conditional else evaluation.truth
            matches.append(
                TrustCandidateMatch(
                    statement=statement,
                    candidate=candidate,
                    truth=truth,
                    conditional=conditional,
                    unresolved_keys=tuple(sorted({*evaluation.unresolved_keys, *deny_unresolved})),
                    dead_keys=evaluation.dead_keys,
                    reasons=(*evaluation.reasons, *deny_reasons),
                )
            )
    if not matches:
        return audit
    matched_statements: list[Statement] = []
    for match in matches:
        if match.statement not in matched_statements:
            matched_statements.append(match.statement)
    constrained_claims = {
        str(key).strip()
        for statement in matched_statements
        for key_map in _condition_key_maps(statement)
        for key in key_map
    }
    bound_claims = (
        set.intersection(*(set(match.candidate.claims) for match in matches)) if matches else set()
    )
    additional = tuple(
        sorted(
            claim
            for claim in constrained_claims
            if claim in registry.not_statically_fixable and claim not in bound_claims
        )
    )
    match_classes = [
        weakest(
            EvidenceClass.DERIVED if not match.conditional else EvidenceClass.ASSUMED,
            match.candidate.evidence_class,
        )
        for match in matches
    ]
    strongest_confidence = min(match_classes, key=rank) if match_classes else EvidenceClass.ASSUMED
    return replace(
        audit,
        matches=tuple(matches),
        additional_constraints=additional,
        sub_patterns=_policy_values_for(matched_statements, "sub"),
        job_workflow_ref_patterns=_policy_values_for(matched_statements, "job_workflow_ref"),
        confidence=strongest_confidence,
        dead_keys=tuple(
            sorted(
                {
                    key
                    for statement in matched_statements
                    for key in _statement_dead_keys(statement, registry)
                }
            )
        ),
        missing_audience=any(
            _statement_missing_audience(statement) for statement in matched_statements
        ),
        unconstrained=any(
            _statement_unconstrained(statement, registry) for statement in matched_statements
        ),
    )
