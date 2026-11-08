"""Offline model of the IAM revoke-older-sessions deny.

The AWS console action attaches an inline policy that denies every action when
`aws:TokenIssueTime` is earlier than a cutoff. It never changes the validity of a
credential: denial alone establishes neither expiry nor continued validity.
Validity and access are therefore two independent axes and neither is inferred
from missing input or from treating an issuance upper bound as an exact time.

Source for the propagation window (ASSUMED, never a guarantee):
https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html
("approximately 30 seconds into the future").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

AWS_REVOKE_URL = (
    "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html"
)
PROPAGATION_SECONDS = 30

Validity = Literal["expired", "unknown"]
Access = Literal["denied_by_revocation_policy", "revocation_propagating", "not_denied", "unknown"]
DisplayState = Literal["access denied - expiry not established", "expired", "unknown"]
CutoffSource = Literal["given", "assumed_revoked_at_plus_30s", "missing"]


class TimestampError(ValueError):
    """A plan timestamp is not an RFC 3339 date-time with a UTC offset."""


def parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        msg = "timestamp must be a string"
        raise TimestampError(msg)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        msg = "timestamp is not ISO 8601"
        raise TimestampError(msg) from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = "timestamp needs a UTC offset"
        raise TimestampError(msg)
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError):
        msg = "timestamp UTC conversion is outside the supported date range"
        raise TimestampError(msg) from None


def _add_seconds(value: datetime, seconds: int) -> datetime:
    try:
        return value + timedelta(seconds=seconds)
    except OverflowError:
        msg = "timestamp arithmetic is outside the supported date range"
        raise TimestampError(msg) from None


def format_timestamp(value: datetime) -> str:
    return _utc(value).isoformat().replace("+00:00", "Z")


def resolve_cutoff(
    revoked_at: datetime | None, cutoff: datetime | None
) -> tuple[datetime | None, CutoffSource]:
    """A given cutoff wins; otherwise revoked_at plus the ASSUMED 30 s window."""
    if cutoff is not None:
        return cutoff, "given"
    if revoked_at is not None:
        return _add_seconds(revoked_at, PROPAGATION_SECONDS), "assumed_revoked_at_plus_30s"
    return None, "missing"


@dataclass(frozen=True, slots=True)
class SessionAssessment:
    validity: Validity
    access: Access
    display_state: DisplayState
    conditional_on_propagation: bool


def _validity(
    issued: datetime | None, ttl_seconds: int | None, assessed_at: datetime | None
) -> Validity:
    if issued is None or assessed_at is None or ttl_seconds is None or ttl_seconds <= 0:
        return "unknown"
    if assessed_at >= _add_seconds(issued, ttl_seconds):
        return "expired"
    # An earlier issue time (or shorter TTL) may already have expired.
    return "unknown"


def _access(
    issued: datetime | None,
    cutoff: datetime | None,
    revoked_at: datetime | None,
    assessed_at: datetime | None,
) -> tuple[Access, bool]:
    if issued is None or cutoff is None:
        return "unknown", False
    if issued >= cutoff:
        # The actual issue time may still precede the cutoff.
        return "unknown", False
    if assessed_at is None:
        return "denied_by_revocation_policy", True
    if assessed_at >= cutoff:
        return "denied_by_revocation_policy", False
    if revoked_at is None:
        return "unknown", False
    if assessed_at >= revoked_at:
        return "revocation_propagating", False
    return "not_denied", False


def _display(validity: Validity, access: Access) -> DisplayState:
    if validity == "expired":
        return "expired"
    if access == "denied_by_revocation_policy":
        return "access denied - expiry not established"
    return "unknown"


def assess_session(
    *,
    issued_no_later_than: datetime | None,
    ttl_seconds: int | None,
    revoked_at: datetime | None,
    cutoff: datetime | None,
    assessed_at: datetime | None,
) -> SessionAssessment:
    """Two independent axes for one in-scope session.

    `issued_no_later_than` is an upper bound on the issue time. `expired` needs the
    assessment time, that bound and a known TTL upper bound. A bound earlier than
    the cutoff establishes policy coverage, subject to propagation; a bound at or
    after the cutoff cannot establish either coverage or absence of the deny.
    Before the latest possible expiry, validity remains unknown, never active.
    `cutoff` is the effective cutoff from `resolve_cutoff`.
    """
    validity = _validity(issued_no_later_than, ttl_seconds, assessed_at)
    access, conditional = _access(issued_no_later_than, cutoff, revoked_at, assessed_at)
    return SessionAssessment(
        validity=validity,
        access=access,
        display_state=_display(validity, access),
        conditional_on_propagation=conditional,
    )


REVOKE_CAVEATS: tuple[tuple[str, str], ...] = (
    (
        "C-REVOKE-1",
        "Sessions issued inside the propagation window (the assumed 30 s before the "
        "cutoff) are covered by the deny.",
    ),
    (
        "C-REVOKE-2",
        "Sessions issued after the cutoff are not covered; a role that can still be "
        "assumed yields new sessions.",
    ),
    (
        "C-REVOKE-3",
        "The deny applies to every user of the role, including legitimate sessions "
        "issued before the cutoff.",
    ),
    (
        "C-REVOKE-4",
        "Service-linked roles cannot be revoked this way.",
    ),
    (
        "C-REVOKE-5",
        "Derived credentials (chained role sessions, access keys created by the session, "
        "secrets already read) are not affected by the deny; role chaining is not "
        "modelled, so they are listed as residual_unknown.",
    ),
    (
        "C-REVOKE-6",
        "The 30 s propagation window is ASSUMED from "
        + AWS_REVOKE_URL
        + ' ("approximately 30 seconds into the future") and is not a guarantee.',
    ),
)

__all__ = [
    "AWS_REVOKE_URL",
    "PROPAGATION_SECONDS",
    "REVOKE_CAVEATS",
    "Access",
    "CutoffSource",
    "DisplayState",
    "SessionAssessment",
    "TimestampError",
    "Validity",
    "assess_session",
    "format_timestamp",
    "parse_timestamp",
    "resolve_cutoff",
]
