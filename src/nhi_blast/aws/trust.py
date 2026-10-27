"""AWS trust-policy evaluation against OIDC subject candidates (spec 10.3).

A statement is relevant when it allows sts:AssumeRoleWithWebIdentity for the GitHub
OIDC provider. Conditions are evaluated against the candidate's claim context in
CANDIDATE mode: a positive string operator intersects the policy pattern with the
candidate glob, negative operators are undecidable, and the claims a job cannot fix
statically are reported as additional constraints rather than silently ignored.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from nhi_blast.aws.conditions import (
    ConditionMode,
    ConditionTruth,
    evaluate_conditions,
    required_positive_patterns,
)
from nhi_blast.aws.glob import glob_intersects, glob_match, has_wildcard, literal_prefix
from nhi_blast.core.data import ConditionKeyRegistry
from nhi_blast.core.evidence import EvidenceClass, weakest
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


def is_github_oidc_statement(statement: Statement, provider_host: str) -> bool:
    if statement.effect is not PolicyEffect.ALLOW:
        return False
    if not any(glob_match(pattern, ASSUME_ACTION, fold=True) for pattern in statement.actions):
        return False
    federated = statement.principals.get("Federated", ())
    suffix = f"oidc-provider/{provider_host}"
    return any(principal.endswith(suffix) for principal in federated)


def _condition_key_maps(statement: Statement) -> tuple[Mapping[str, Sequence[str]], ...]:
    maps: list[Mapping[str, Sequence[str]]] = []
    for key_map in statement.conditions.values():
        if isinstance(key_map, Mapping):
            maps.append(key_map)
    return tuple(maps)


def _policy_values_for(statements: Sequence[Statement], claim: str) -> tuple[str, ...]:
    values: set[str] = set()
    for statement in statements:
        for key_map in _condition_key_maps(statement):
            for key, raw in key_map.items():
                if str(key).strip() != claim:
                    continue
                if isinstance(raw, str):
                    values.add(raw)
                elif isinstance(raw, Sequence):
                    values.update(str(item) for item in raw)
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
    prefix = f"{provider_host}:"
    normalized: dict[str, dict[str, tuple[str, ...]]] = {}
    for operator, key_map in statement.conditions.items():
        normalized[operator] = {
            (key[len(prefix) :] if key.startswith(prefix) else key): values
            for key, values in key_map.items()
        }
    return statement.model_copy(update={"conditions": normalized})


def _relevant_statements(role: RoleFact, registry: ConditionKeyRegistry) -> list[Statement]:
    return [
        _normalise_statement(statement, registry.provider_host)
        for statement in role.trust_statements
        if is_github_oidc_statement(statement, registry.provider_host)
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
                    glob_intersects(pattern, subject, fold=True)
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
    relevant = _relevant_statements(role, registry)
    if not relevant:
        return TrustEvaluation(role_id=role.id)
    dead: set[str] = set()
    has_audience = False
    for statement in relevant:
        for key_map in _condition_key_maps(statement):
            for raw_key in key_map:
                key = str(raw_key).strip()
                if key == "aud":
                    has_audience = True
                if key not in registry.supported:
                    dead.add(key)
    return TrustEvaluation(
        role_id=role.id,
        dead_keys=tuple(sorted(dead)),
        missing_audience=not has_audience,
    )


def evaluate_trust_statements(
    role: RoleFact,
    candidates: Sequence[SubjectCandidate],
    *,
    registry: ConditionKeyRegistry,
) -> TrustEvaluation:
    relevant = _relevant_statements(role, registry)
    if not relevant:
        return TrustEvaluation(role_id=role.id)
    missing_audience = not any(
        "aud" in key_map for statement in relevant for key_map in _condition_key_maps(statement)
    )
    matches: list[TrustCandidateMatch] = []
    dead_keys: set[str] = set()
    for statement in relevant:
        for candidate in candidates:
            evaluation = evaluate_conditions(
                statement.conditions,
                _context_for(candidate),
                mode=ConditionMode.CANDIDATE,
                supported_keys=registry.supported,
            )
            dead_keys.update(evaluation.dead_keys)
            if evaluation.truth is ConditionTruth.FALSE:
                continue
            matches.append(
                TrustCandidateMatch(
                    statement=statement,
                    candidate=candidate,
                    truth=evaluation.truth,
                    conditional=evaluation.truth is ConditionTruth.UNRESOLVED,
                    unresolved_keys=evaluation.unresolved_keys,
                    dead_keys=evaluation.dead_keys,
                    reasons=evaluation.reasons,
                )
            )
    if not matches:
        return TrustEvaluation(
            role_id=role.id,
            dead_keys=tuple(sorted(dead_keys)),
            missing_audience=missing_audience,
        )
    matched_statements = [match.statement for match in matches]
    constrained_claims = {
        str(key).strip()
        for statement in matched_statements
        for key_map in _condition_key_maps(statement)
        for key in key_map
    }
    unconstrained = not (constrained_claims & set(registry.required_control_any_of))
    additional = tuple(
        sorted(claim for claim in constrained_claims if claim in registry.not_statically_fixable)
    )
    classes = [
        EvidenceClass.DERIVED if not match.conditional else EvidenceClass.ASSUMED
        for match in matches
    ] + [match.candidate.evidence_class for match in matches]
    return TrustEvaluation(
        role_id=role.id,
        matches=tuple(matches),
        dead_keys=tuple(sorted(dead_keys)),
        missing_audience=missing_audience,
        unconstrained=unconstrained,
        additional_constraints=additional,
        sub_patterns=_policy_values_for(matched_statements, "sub"),
        job_workflow_ref_patterns=_policy_values_for(matched_statements, "job_workflow_ref"),
        confidence=weakest(*classes) if classes else EvidenceClass.ASSUMED,
    )
