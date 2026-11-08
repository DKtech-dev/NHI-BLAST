"""Revocation axes: validity and access are independent and never inferred from gaps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from nhi_blast.whatif.sessions import (
    TimestampError,
    assess_session,
    format_timestamp,
    parse_timestamp,
    resolve_cutoff,
)


def at(text: str) -> datetime:
    return parse_timestamp(f"2026-03-01T{text}Z")


# (issued_no_later_than, revoked_at, cutoff, assessed_at, ttl) ->
# (validity, access, display state, conditional on propagation)
# These inputs supply only upper bounds: before the latest possible expiry,
# validity is unknown. A deny or propagating policy does not establish validity;
# an issue-time upper bound at/after the cutoff does not establish absence of deny.
DENIED = "access denied - expiry not established"
TABLE: list[tuple[str, tuple[object, ...], tuple[object, ...]]] = [
    ("nothing known", (None, None, None, None, 3600), ("unknown", "unknown", "unknown", False)),
    (
        "assumed cutoff, no assessment time",
        ("09:30:00", "10:00:00", None, None, 3600),
        ("unknown", "denied_by_revocation_policy", DENIED, True),
    ),
    (
        "assessed after the assumed cutoff",
        ("09:30:00", "10:00:00", None, "10:05:00", 3600),
        ("unknown", "denied_by_revocation_policy", DENIED, False),
    ),
    (
        "assessed exactly at the cutoff",
        ("09:30:00", "10:00:00", None, "10:00:30", 3600),
        ("unknown", "denied_by_revocation_policy", DENIED, False),
    ),
    (
        "assessed inside the propagation window",
        ("09:30:00", "10:00:00", None, "10:00:10", 3600),
        ("unknown", "revocation_propagating", "unknown", False),
    ),
    (
        "assessed exactly at revoked_at",
        ("09:30:00", "10:00:00", None, "10:00:00", 3600),
        ("unknown", "revocation_propagating", "unknown", False),
    ),
    (
        "assessed before revoked_at",
        ("09:30:00", "10:00:00", None, "09:59:59", 3600),
        ("unknown", "not_denied", "unknown", False),
    ),
    (
        "issuance upper bound after the cutoff",
        ("10:01:00", "10:00:00", None, "10:05:00", 3600),
        ("unknown", "unknown", "unknown", False),
    ),
    (
        "issuance upper bound exactly at the cutoff",
        ("10:00:30", "10:00:00", None, "10:05:00", 3600),
        ("unknown", "unknown", "unknown", False),
    ),
    (
        "given cutoff without revoked_at, assessed after it",
        ("09:30:00", None, "10:00:30", "10:05:00", 3600),
        ("unknown", "denied_by_revocation_policy", DENIED, False),
    ),
    (
        "given cutoff without revoked_at, assessed before it",
        ("09:30:00", None, "10:00:30", "10:00:10", 3600),
        ("unknown", "unknown", "unknown", False),
    ),
    (
        "given cutoff without revoked_at or assessment time",
        ("09:30:00", None, "10:00:30", None, 3600),
        ("unknown", "denied_by_revocation_policy", DENIED, True),
    ),
    (
        "issue time missing",
        (None, "10:00:00", None, "10:05:00", 3600),
        ("unknown", "unknown", "unknown", False),
    ),
    (
        "cutoff and revoked_at missing",
        ("09:30:00", None, None, "10:05:00", 3600),
        ("unknown", "unknown", "unknown", False),
    ),
    (
        "given cutoff wins over revoked_at plus 30 s",
        ("10:00:40", "10:00:00", "10:01:00", "10:05:00", 3600),
        ("unknown", "denied_by_revocation_policy", DENIED, False),
    ),
    (
        "expired exactly at issuance upper bound plus TTL",
        ("09:30:00", "10:00:00", None, "10:30:00", 3600),
        ("expired", "denied_by_revocation_policy", "expired", False),
    ),
    (
        "one second before latest possible expiry",
        ("09:30:00", "10:00:00", None, "10:29:59", 3600),
        ("unknown", "denied_by_revocation_policy", DENIED, False),
    ),
    (
        "expired without any revocation input",
        ("08:00:00", None, None, "10:00:00", 3600),
        ("expired", "unknown", "expired", False),
    ),
    (
        "expired and issuance upper bound after the cutoff",
        ("08:00:00", "07:00:00", None, "10:00:00", 3600),
        ("expired", "unknown", "expired", False),
    ),
    (
        "TTL upper bound missing",
        ("09:30:00", "10:00:00", None, "20:00:00", None),
        ("unknown", "denied_by_revocation_policy", DENIED, False),
    ),
    (
        "TTL upper bound not positive",
        ("09:30:00", "10:00:00", None, "20:00:00", 0),
        ("unknown", "denied_by_revocation_policy", DENIED, False),
    ),
    (
        "no assessment time keeps validity open",
        ("08:00:00", None, None, None, 3600),
        ("unknown", "unknown", "unknown", False),
    ),
]


def _stamp(value: object) -> datetime | None:
    return None if value is None else at(str(value))


@pytest.mark.parametrize(("name", "given", "expected"), TABLE, ids=[row[0] for row in TABLE])
def test_every_combination_of_known_and_unknown_inputs(
    name: str, given: tuple[object, ...], expected: tuple[object, ...]
) -> None:
    issued, revoked_at, cutoff, assessed_at, ttl = given
    effective, _ = resolve_cutoff(_stamp(revoked_at), _stamp(cutoff))
    result = assess_session(
        issued_no_later_than=_stamp(issued),
        ttl_seconds=ttl if isinstance(ttl, int) else None,
        revoked_at=_stamp(revoked_at),
        cutoff=effective,
        assessed_at=_stamp(assessed_at),
    )
    assert (
        result.validity,
        result.access,
        result.display_state,
        result.conditional_on_propagation,
    ) == expected, name


def test_expired_state_requires_validity_expired_for_every_input_combination() -> None:
    values = (None, "07:00:00", "09:30:00", "10:00:00", "10:00:30", "10:05:00", "12:00:00")
    for issued in values:
        for revoked in values:
            for cutoff_in in (None, "10:00:30"):
                for assessed in values:
                    effective, _ = resolve_cutoff(_stamp(revoked), _stamp(cutoff_in))
                    result = assess_session(
                        issued_no_later_than=_stamp(issued),
                        ttl_seconds=3600,
                        revoked_at=_stamp(revoked),
                        cutoff=effective,
                        assessed_at=_stamp(assessed),
                    )
                    assert (result.display_state == "expired") == (result.validity == "expired")
                    if result.validity == "expired":
                        assert issued is not None
                        assert assessed is not None


@pytest.mark.parametrize(
    ("upper", "earlier", "later", "expected_access"),
    [
        ("10:00:30", "08:00:00", "10:00:30", "unknown"),
        ("10:01:00", "08:00:00", "10:00:45", "unknown"),
        ("09:30:00", "08:00:00", "09:30:00", "denied_by_revocation_policy"),
    ],
)
def test_two_possible_issue_times_beneath_one_bound_keep_validity_unknown(
    upper: str, earlier: str, later: str, expected_access: str
) -> None:
    # With cutoff 10:00:30 and assessment 10:05, issuance at 08:00 is expired
    # and covered by the deny, while the later issuance is not expired. In the
    # first two rows it is also outside the deny. Both witnesses satisfy the
    # same upper bound, so treating that bound as an exact issue time is unsound.
    cutoff = at("10:00:30")
    assessed = at("10:05:00")
    assert at(earlier) < at(later) <= at(upper)
    assert at(earlier) + timedelta(seconds=3600) <= assessed
    assert assessed < at(later) + timedelta(seconds=3600)
    assert at(earlier) < cutoff
    if expected_access == "unknown":
        assert at(later) >= cutoff
    else:
        assert at(later) < cutoff

    result = assess_session(
        issued_no_later_than=at(upper),
        ttl_seconds=3600,
        revoked_at=at("10:00:00"),
        cutoff=cutoff,
        assessed_at=assessed,
    )
    assert result.validity == "unknown"
    assert result.access == expected_access
    assert result.display_state == (
        "unknown" if expected_access == "unknown" else "access denied - expiry not established"
    )


def test_propagation_state_does_not_establish_credential_validity() -> None:
    result = assess_session(
        issued_no_later_than=at("09:30:00"),
        ttl_seconds=3600,
        revoked_at=at("10:00:00"),
        cutoff=at("10:00:30"),
        assessed_at=at("10:00:10"),
    )
    assert result.access == "revocation_propagating"
    assert result.validity == "unknown"
    assert result.display_state == "unknown"


def test_cutoff_sources() -> None:
    assert resolve_cutoff(None, None) == (None, "missing")
    assumed = resolve_cutoff(at("10:00:00"), None)
    assert assumed == (at("10:00:30"), "assumed_revoked_at_plus_30s")
    assert resolve_cutoff(at("10:00:00"), at("10:07:00")) == (at("10:07:00"), "given")
    assert resolve_cutoff(None, at("10:07:00")) == (at("10:07:00"), "given")


@pytest.mark.parametrize(
    "bad", [None, 5, "", "yesterday", "2026-03-01", "2026-03-01T10:00:00", "x" * 100]
)
def test_timestamps_need_an_offset(bad: object) -> None:
    with pytest.raises(TimestampError):
        parse_timestamp(bad)


def test_timestamp_round_trip_is_normalised_to_utc() -> None:
    parsed = parse_timestamp("2026-03-01T15:30:00+05:30")
    assert parsed.tzinfo is UTC or parsed.utcoffset() is not None
    assert format_timestamp(parsed) == "2026-03-01T10:00:00Z"
