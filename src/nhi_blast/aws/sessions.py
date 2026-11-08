"""Effective STS session lifetime and its provenance (plan C2).

The TTL is the duration the job asked for, bounded by the role's maximum session duration
and, for role chaining, by one hour. Every value says where it came from. An expression, an
invalid input or an unknown role maximum is never replaced by a guessed default.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.parsers.gha.facts import AwsAuthUse

STS_MAX_SECONDS = 43_200
CHAINED_MAX_SECONDS = 3_600
AWS_DEFAULT_ROLE_MAX_SECONDS = 3_600

RequestedKind = Literal[
    "declared",
    "action_default_verified",
    "action_default_unverified",
    "unknown",
    "not_requested",
]
Outcome = Literal["issued", "fails_as_declared"]


@dataclass(frozen=True, slots=True)
class RequestedDuration:
    kind: RequestedKind
    seconds: int | None = None


@dataclass(frozen=True, slots=True)
class SessionTtl:
    seconds: int
    evidence_class: EvidenceClass
    provenance: str
    outcome: Outcome = "issued"
    assumptions: tuple[str, ...] = ()
    requested_kind: str = "unknown"


def requested_duration(
    auth: AwsAuthUse | None,
    *,
    action_ref: str | None,
    verified_refs: frozenset[str],
) -> RequestedDuration:
    """What the job asks STS for. ``auth`` is None when no step targets the role."""
    if auth is None:
        return RequestedDuration("not_requested")
    if auth.duration_kind == "literal" and auth.duration_seconds is not None:
        return RequestedDuration("declared", auth.duration_seconds)
    if auth.duration_kind == "default":
        if action_ref is not None and action_ref in verified_refs:
            return RequestedDuration("action_default_verified")
        return RequestedDuration("action_default_unverified")
    return RequestedDuration("unknown")


def effective_ttl(
    requested: RequestedDuration,
    *,
    role_max: int,
    role_max_source: str,
    chained: bool | None,
    action_default_seconds: int,
) -> SessionTtl:
    """Upper bound on the session lifetime, with the provenance of that bound."""
    ceiling = STS_MAX_SECONDS if role_max_source == "unknown" else role_max
    role_text = {
        "declared": f"role max_session_duration {role_max} s",
        "unknown": f"role maximum unknown, bounded by the STS limit {STS_MAX_SECONDS} s",
    }.get(role_max_source, "role maximum session duration (1 h when unset)")
    chain_cap = CHAINED_MAX_SECONDS if chained else None
    kind = requested.kind

    if kind == "declared" and requested.seconds is not None:
        seconds = requested.seconds
        too_long = seconds > ceiling or (chain_cap is not None and seconds > chain_cap)
        bound = min(seconds, ceiling, chain_cap or STS_MAX_SECONDS)
        cls = EvidenceClass.DECLARED if role_max_source == "declared" else EvidenceClass.DERIVED
        if role_max_source == "unknown":
            cls = EvidenceClass.ASSUMED
        if too_long:
            limit = "1 h role-chaining limit" if chain_cap and seconds > chain_cap else role_text
            return SessionTtl(
                bound,
                EvidenceClass.UNKNOWN,
                f"role-duration-seconds {seconds} exceeds the {limit}; "
                "AssumeRole fails as declared, so this session is only potential",
                outcome="fails_as_declared",
                requested_kind=kind,
            )
        return SessionTtl(
            bound,
            cls,
            f"role-duration-seconds {seconds} s declared in the workflow, within the {role_text}",
            requested_kind=kind,
        )

    if kind == "action_default_verified":
        bound = min(action_default_seconds, ceiling, chain_cap or STS_MAX_SECONDS)
        return SessionTtl(
            bound,
            EvidenceClass.DERIVED,
            f"role-duration-seconds not set; the action default is {action_default_seconds} s",
            requested_kind=kind,
        )

    if kind == "action_default_unverified":
        # Defaults from other refs cannot bound what this unread ref requests.
        bound = min(ceiling, chain_cap or STS_MAX_SECONDS)
        chain_text = "; capped by the 1 h role-chaining limit" if chain_cap is not None else ""
        return SessionTtl(
            bound,
            EvidenceClass.ASSUMED,
            "role-duration-seconds not set; the action default is not verified for this ref "
            f"and may request more; upper bound is the {role_text}{chain_text}",
            assumptions=("A-CAC-DEFAULT",),
            requested_kind=kind,
        )

    bound = min(ceiling, chain_cap or STS_MAX_SECONDS)
    why = (
        "no step in this job requests this role, so the duration is the caller's choice"
        if kind == "not_requested"
        else "role-duration-seconds is an expression or invalid"
    )
    cls = EvidenceClass.UNKNOWN if role_max_source == "unknown" else EvidenceClass.ASSUMED
    return SessionTtl(
        bound,
        cls,
        f"{why}; upper bound is the {role_text}",
        assumptions=("A-STS-TTL",),
        requested_kind=kind,
    )


__all__ = [
    "AWS_DEFAULT_ROLE_MAX_SECONDS",
    "CHAINED_MAX_SECONDS",
    "STS_MAX_SECONDS",
    "RequestedDuration",
    "SessionTtl",
    "effective_ttl",
    "requested_duration",
]
