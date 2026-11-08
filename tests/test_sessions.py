"""Session duration provenance and configure-aws-credentials inputs (plan C2)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from nhi_blast.aws.sessions import (
    RequestedDuration,
    effective_ttl,
)
from nhi_blast.core.evidence import EvidenceClass
from nhi_blast.core.models import EdgeKind, Node, Report
from nhi_blast.pipeline import ScanOptions, run_scan

FX07 = Path(__file__).parent / "fixtures" / "fx07-incident"
ACTION = "action:tj-actions/changed-files@v45"
SHA_REF = "abcdef0123456789abcdef0123456789abcdef02"
VERIFIED = "v6"


def _ttl(kind: str, seconds: int | None = None, **kwargs: object):  # type: ignore[no-untyped-def]
    defaults: dict[str, object] = {
        "role_max": 3600,
        "role_max_source": "declared",
        "chained": False,
        "action_default_seconds": 3600,
    }
    defaults.update(kwargs)
    return effective_ttl(RequestedDuration(kind, seconds), **defaults)  # type: ignore[arg-type]


def test_declared_duration_within_the_role_maximum_keeps_its_class() -> None:
    declared = _ttl("declared", 1800)
    assert (declared.seconds, declared.evidence_class) == (1800, EvidenceClass.DECLARED)
    derived = _ttl("declared", 1800, role_max_source="aws_default")
    assert derived.evidence_class is EvidenceClass.DERIVED
    assert derived.outcome == "issued"


def test_declared_duration_above_the_role_maximum_fails_as_declared() -> None:
    result = _ttl("declared", 43_200, role_max=3600)
    assert result.outcome == "fails_as_declared"
    assert result.evidence_class is EvidenceClass.UNKNOWN
    assert result.seconds == 3600


def test_role_chaining_caps_at_one_hour_and_rejects_more() -> None:
    capped = _ttl("action_default_verified", role_max=43_200, chained=True)
    assert capped.seconds == 3600
    over = _ttl("declared", 7200, role_max=43_200, chained=True)
    assert over.outcome == "fails_as_declared"
    assert "role-chaining" in over.provenance
    exact = _ttl("declared", 3600, role_max=43_200, chained=True)
    assert exact.outcome == "issued"


def test_action_default_is_derived_only_for_verified_refs() -> None:
    verified = _ttl("action_default_verified")
    assert (verified.evidence_class, verified.assumptions) == (EvidenceClass.DERIVED, ())
    unverified = _ttl("action_default_unverified")
    assert unverified.evidence_class is EvidenceClass.ASSUMED
    assert unverified.assumptions == ("A-CAC-DEFAULT",)


@pytest.mark.parametrize(
    ("role_max", "role_max_source", "chained", "expected_seconds"),
    [
        (21_600, "declared", False, 21_600),
        (21_600, "declared", None, 21_600),
        (21_600, "declared", True, 3600),
        (3600, "unknown", False, 43_200),
        (3600, "unknown", None, 43_200),
        (3600, "unknown", True, 3600),
        (3600, "aws_default", False, 3600),
    ],
)
def test_unverified_action_default_uses_conservative_bound_not_another_refs_default(
    role_max: int, role_max_source: str, chained: bool | None, expected_seconds: int
) -> None:
    # An unread action ref can request more than a verified ref; unknown chaining
    # cannot establish the one-hour cap either. An unset known role maximum can.
    result = _ttl(
        "action_default_unverified",
        role_max=role_max,
        role_max_source=role_max_source,
        chained=chained,
    )
    assert result.seconds == expected_seconds
    assert result.evidence_class is EvidenceClass.ASSUMED
    assert result.assumptions == ("A-CAC-DEFAULT",)
    assert result.requested_kind == "action_default_unverified"
    assert "not verified" in result.provenance
    assert "upper bound" in result.provenance


@pytest.mark.parametrize("chained", [False, None, True])
def test_verified_action_default_remains_one_hour_with_a_larger_role_maximum(
    chained: bool | None,
) -> None:
    result = _ttl("action_default_verified", role_max=43_200, chained=chained)
    assert result.seconds == 3600
    assert result.evidence_class is EvidenceClass.DERIVED
    assert result.assumptions == ()


@pytest.mark.parametrize("kind", ["unknown", "not_requested"])
def test_unknown_request_is_bounded_by_the_role_maximum_never_guessed(kind: str) -> None:
    result = _ttl(kind, role_max=21_600)
    assert result.seconds == 21_600
    assert result.evidence_class is EvidenceClass.ASSUMED
    assert result.assumptions == ("A-STS-TTL",)


def test_unknown_role_maximum_falls_back_to_the_sts_limit() -> None:
    result = _ttl("unknown", role_max=43_200, role_max_source="unknown")
    assert result.seconds == 43_200
    assert result.evidence_class is EvidenceClass.UNKNOWN
    chained = _ttl("unknown", role_max=43_200, role_max_source="unknown", chained=True)
    assert chained.seconds == 3600
    assert _ttl("unknown", role_max=3600, chained=None).seconds == 3600


# ---------------------------------------------------------------------- end to end


def _scan(tmp_path: Path, with_lines: str = "", ref: str = SHA_REF) -> Report:
    root = tmp_path / "repo"
    shutil.copytree(FX07, root)
    workflow = root / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8").replace(
        "configure-aws-credentials@" + SHA_REF, "configure-aws-credentials@" + ref
    )
    marker = "          audience: sts.amazonaws.com\n"
    assert marker in text
    extra = "".join(f"          {line}\n" for line in with_lines.splitlines())
    workflow.write_text(text.replace(marker, marker + extra), encoding="utf-8")
    options = ScanOptions(root=root, repo_slug="acme/shop", selectors=(ACTION,))
    return run_scan(options).report


def _session(report: Report) -> Node:
    sessions = [
        node
        for node in report.graph.nodes
        if node.attrs.get("credential_kind") == "STS_SESSION"
        and "release.yml#publish" in str(node.attrs.get("identity"))
        and node.attrs.get("role", "").endswith("deploy-prod")
    ]
    assert len(sessions) == 1
    return sessions[0]


def _assumption_ids(report: Report) -> set[str]:
    return {item.id for item in report.assumptions}


def test_unverified_action_ref_reports_the_role_bound_as_assumed(tmp_path: Path) -> None:
    report = _scan(tmp_path)
    session = _session(report)
    # This fixture declares a 3600 s role maximum, not a verified action default.
    assert session.attrs["ttl_seconds"] == 3600
    assert session.attrs["ttl_requested"] == "action_default_unverified"
    assert "A-CAC-DEFAULT" in _assumption_ids(report)


def test_verified_action_ref_derives_the_default(tmp_path: Path) -> None:
    report = _scan(tmp_path, ref=VERIFIED)
    assert _session(report).attrs["ttl_requested"] == "action_default_verified"
    assert "A-CAC-DEFAULT" not in _assumption_ids(report)


def test_declared_duration_sets_a_declared_ttl(tmp_path: Path) -> None:
    report = _scan(tmp_path, "role-duration-seconds: 1800")
    session = _session(report)
    assert session.attrs["ttl_seconds"] == 1800
    assert session.attrs["ttl_requested"] == "declared"
    rules = {(item.rule, item.cls) for item in session.evidence}
    assert ("CAC.role-duration-seconds", EvidenceClass.DECLARED) in rules


def test_duration_above_the_role_maximum_stays_out_of_the_definite_sets(tmp_path: Path) -> None:
    report = _scan(tmp_path, "role-duration-seconds: 7200")
    session = _session(report)
    assert session.attrs["issuance"] == "fails_as_declared"
    assert session.attrs["ttl_seconds"] == 3600
    edges = [
        edge
        for edge in report.graph.edges
        if edge.kind is EdgeKind.CAN_ASSUME and edge.attrs.get("session_credential") == session.id
    ]
    assert edges
    assert all(edge.attrs["session_outcome"] == "fails_as_declared" for edge in edges)
    assert all(edge.confidence is EvidenceClass.UNKNOWN for edge in edges)
    for scenario in report.scenarios:
        assert session.id not in {item.credential for item in scenario.partition.E}


def test_expression_duration_is_unknown_not_a_default(tmp_path: Path) -> None:
    report = _scan(tmp_path, "role-duration-seconds: ${{ vars.SESSION_SECONDS }}")
    session = _session(report)
    assert session.attrs["ttl_requested"] == "unknown"
    assert session.attrs["ttl_seconds"] == 3600
    assert "A-STS-TTL" in _assumption_ids(report)
    assert "A-CAC-DEFAULT" not in _assumption_ids(report)


@pytest.mark.parametrize("value", ["99", "86400", "1h", "-5", "1800.5"])
def test_invalid_duration_raises_a_diagnostic_and_is_unknown(tmp_path: Path, value: str) -> None:
    report = _scan(tmp_path, f"role-duration-seconds: {value}")
    assert "D-CAC-DURATION-INVALID" in {item.code for item in report.diagnostics}
    assert _session(report).attrs["ttl_requested"] == "unknown"


def test_role_chaining_is_reported_and_enforces_the_one_hour_limit(tmp_path: Path) -> None:
    report = _scan(tmp_path, "role-chaining: true\nrole-duration-seconds: 7200")
    assert "D-GHA-ROLE-CHAINING" in {item.code for item in report.diagnostics}
    assert _session(report).attrs["issuance"] == "fails_as_declared"


def test_session_policy_is_recorded_but_never_treated_as_evaluated(tmp_path: Path) -> None:
    report = _scan(
        tmp_path,
        'inline-session-policy: \'{"Version":"2012-10-17","Statement":[]}\'\n'
        "managed-session-policies: arn:aws:iam::111122223333:policy/narrow",
    )
    attrs = _session(report).attrs
    assert attrs["session_policy_inline"] == "literal"
    assert attrs["session_policy_managed"] == ["arn:aws:iam::111122223333:policy/narrow"]
    assert attrs["session_policy_evaluated"] is False
    assert "A-SESSION-POLICY" in _assumption_ids(report)
