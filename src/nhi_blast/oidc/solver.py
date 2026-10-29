"""OIDC trust solving: candidates in, TrustMatch out (spec 10.3-10.6).

The solver combines AWS condition evaluation with breadth classification. It is a
deterministic comparison of a stated trust policy against the candidate subject set
a job could mint; it is not a proof that a token was ever issued or used.
"""

from __future__ import annotations

from collections.abc import Sequence

from nhi_blast.aws.glob import has_wildcard
from nhi_blast.aws.trust import TrustEvaluation, evaluate_trust_statements
from nhi_blast.core.data import ConditionKeyRegistry, condition_keys
from nhi_blast.core.evidence import Evidence, EvidenceClass, dedupe_evidence, weakest
from nhi_blast.core.models import (
    Breadth,
    RoleFact,
    SubFormat,
    SubjectCandidate,
    TrustMatch,
)
from nhi_blast.oidc.breadth import classify_breadth, worst_breadth

_FORMAT_ORDER = {SubFormat.CLASSIC: 0, SubFormat.IMMUTABLE: 1, SubFormat.UNKNOWN: 2}


def _candidate_sort_key(candidate: SubjectCandidate) -> tuple[str, int, str, str]:
    return (
        candidate.subject,
        _FORMAT_ORDER[candidate.format],
        candidate.trigger,
        candidate.audience,
    )


def _job_workflow_ref_breadth(pattern: str) -> Breadth:
    """Map a job_workflow_ref pattern onto the subject breadth classes.

    The claim is ``OWNER/REPO/PATH@REF`` (optionally with AWS's ``repo:``
    prefix); the wildcard position that matters is the owner, the repository,
    or the ref, in that order of breadth.
    """
    text = pattern.strip()
    body = text[len("repo:") :] if text.startswith("repo:") else text
    path, separator, ref = body.partition("@")
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return Breadth.ANY_ORG
    owner, name = segments[0], segments[1]
    if has_wildcard(owner):
        return Breadth.ANY_ORG
    if has_wildcard(name):
        return Breadth.SAME_ORG
    if not separator:
        return Breadth.REPO_ANY_CONTEXT
    return Breadth.REPO_ANY_BRANCH if has_wildcard(ref) else Breadth.EXACT_REF


def _breadth_for(evaluation: TrustEvaluation) -> Breadth:
    if evaluation.unconstrained:
        return Breadth.UNCONSTRAINED
    breadths: list[Breadth] = [classify_breadth(pattern) for pattern in evaluation.sub_patterns]
    breadths.extend(
        _job_workflow_ref_breadth(pattern) for pattern in evaluation.job_workflow_ref_patterns
    )
    if not breadths:
        return Breadth.UNCONSTRAINED
    return worst_breadth(tuple(breadths))


def _unresolved_reasons(evaluation: TrustEvaluation) -> tuple[str, ...]:
    reasons: set[str] = set()
    for match in evaluation.matches:
        if match.candidate.evidence_class is EvidenceClass.UNKNOWN:
            reasons.add("candidate subject set is unresolved")
        for key in match.unresolved_keys:
            reasons.add(f"claim {key} cannot be evaluated from repository facts")
    for constraint in evaluation.additional_constraints:
        reasons.add(f"claim {constraint} is not fixed statically by the job")
    return tuple(sorted(reasons))


def _evidence(
    role: RoleFact, evaluation: TrustEvaluation, confidence: EvidenceClass
) -> tuple[Evidence, ...]:
    entries: list[Evidence] = list(role.evidence)
    for match in evaluation.matches:
        entries.extend(match.statement.evidence)
        entries.extend(match.candidate.evidence)
    if not entries:
        entries.append(
            Evidence(
                cls=confidence,
                rule="OIDC.trust",
                file=role.address,
                detail="trust policy evaluated against candidate subjects",
            )
        )
    return dedupe_evidence(entries)


def evaluate_trust(
    role: RoleFact,
    candidates: Sequence[SubjectCandidate],
    *,
    job_id: str = "",
    registry: ConditionKeyRegistry | None = None,
) -> TrustMatch | None:
    """Return a TrustMatch when the trust policy accepts at least one candidate."""
    if not candidates:
        return None
    key_registry = registry if registry is not None else condition_keys()
    evaluation = evaluate_trust_statements(role, candidates, registry=key_registry)
    return trust_match_from_evaluation(role, candidates, evaluation, job_id=job_id)


def trust_match_from_evaluation(
    role: RoleFact,
    candidates: Sequence[SubjectCandidate],
    evaluation: TrustEvaluation,
    *,
    job_id: str = "",
) -> TrustMatch | None:
    """Build the TrustMatch for a completed trust-statement evaluation."""
    if not evaluation.matches:
        return None
    # SubjectCandidate carries a claims mapping and is therefore not hashable;
    # deduplicate on the identity fields that also define its sort key.
    unique = {_candidate_sort_key(match.candidate): match.candidate for match in evaluation.matches}
    matched = tuple(unique[key] for key in sorted(unique))
    formats = tuple(
        sorted({candidate.format for candidate in matched}, key=lambda item: _FORMAT_ORDER[item])
    )
    candidate_formats = {candidate.format for candidate in candidates}
    breadth = _breadth_for(evaluation)
    # Spec 10.4: drift warns that an org/repo wildcard misses immutable-format
    # repositories elsewhere in the organisation. An exact repository pattern is a
    # compatibility concern for that one repository, not a breadth finding.
    format_drift = (
        breadth in {Breadth.ANY_ORG, Breadth.SAME_ORG}
        and SubFormat.IMMUTABLE in candidate_formats
        and SubFormat.IMMUTABLE not in formats
        and SubFormat.CLASSIC in formats
    )
    confidence = weakest(
        evaluation.confidence,
        *(match.candidate.evidence_class for match in evaluation.matches),
    )
    evidence = _evidence(role, evaluation, confidence)
    confidence = weakest(confidence, *(entry.cls for entry in evidence))
    return TrustMatch(
        job_id=job_id,
        role_id=role.id,
        matched_candidates=matched,
        matched_formats=formats,
        breadth=breadth,
        format_drift=format_drift,
        confidence=confidence,
        unresolved_reasons=_unresolved_reasons(evaluation),
        additional_constraints=evaluation.additional_constraints,
        unconstrained=evaluation.unconstrained,
        dead_condition_keys=evaluation.dead_keys,
        missing_audience=evaluation.missing_audience,
        evidence=evidence,
    )
