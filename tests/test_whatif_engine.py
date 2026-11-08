"""Interventions on fx16: each type, fail-closed handling and honest state labels."""

from __future__ import annotations

import json
from typing import Any

import pytest

from nhi_blast.core.models import EdgeKind
from nhi_blast.whatif.plan import PlanError, parse_plan
from tests.test_whatif_support import (
    ACTION,
    DB_PASSWORD,
    DEPLOY_KEY,
    FIXTURES,
    FORBIDDEN,
    ISSUED,
    JOB,
    OIDC,
    OPS_ROLE,
    REGISTRY_TOKEN,
    REPO_WRITE,
    REVOKED_AT,
    ROLE,
    ROLE_SELECTOR,
    SESSION,
    disable_job,
    fx16_report,
    remove_oidc_trust,
    revoke,
    rotate,
    run,
    scan,
    scenario,
)

ASSESSED_EXPIRED = "2026-03-01T11:00:00Z"
Z_IDS = {DEPLOY_KEY, REGISTRY_TOKEN, DB_PASSWORD}


def z_ids(items: list[dict[str, Any]]) -> set[str]:
    return {item["credential"] for item in items}


def warning_codes(payload: dict[str, Any]) -> set[str]:
    return {item["code"] for item in payload["warnings"]}


def step(payload: dict[str, Any], index: int) -> dict[str, Any]:
    found = payload["steps"][index]
    assert isinstance(found, dict)
    return found


def test_empty_plan_changes_nothing() -> None:
    payload = run(fx16_report())
    assert payload["schema"] == "nhi-blast-whatif/1.0"
    assert payload["header"] == "Offline model. Not executed. Verify in your account."
    assert payload["steps"] == []
    for item in payload["per_scenario"]:
        assert item["after"]["R"] == item["before"]["R"]
        assert item["after"]["E"] == item["before"]["E"]
        assert item["after"]["Z"] == item["before"]["Z"]
        assert item["future_reach"]["E"] == item["before"]["E"]
        assert z_ids(item["future_reach"]["Z"]) == z_ids(item["before"]["Z"])
        assert item["after"]["issued_before_containment"] == []
        assert item["after"]["revoked_access"] == []
    action = scenario(payload, ACTION)
    assert z_ids(action["before"]["Z"]) == Z_IDS
    assert [item["credential"] for item in action["before"]["E"]] == [SESSION]
    role_scenario = scenario(payload, ROLE_SELECTOR)
    assert role_scenario["before"]["R"] == []


def test_disable_entrypoint_stops_future_runs_but_not_issued_state() -> None:
    payload = run(fx16_report(), disable_job())
    assert step(payload, 0)["status"] == "applied"
    assert len(step(payload, 0)["effects"]["removed_edges"]) == 6
    for selector in (ACTION, REPO_WRITE):
        item = scenario(payload, selector)
        assert item["future_reach"]["R"] == []
        assert item["future_reach"]["E"] == []
        assert item["future_reach"]["Z"] == []
        assert z_ids(item["after"]["Z"]) == Z_IDS
        assert item["after"]["R"] == item["before"]["R"]
        issued = item["after"]["issued_before_containment"]
        assert [(row["credential"], row["label"]) for row in issued] == [
            (SESSION, "issued_before_containment")
        ]
        assert issued[0]["max_remaining_seconds"] == 3600
        assert issued[0]["still_obtainable_by_new_runs"] is False
    role_scenario = scenario(payload, ROLE_SELECTOR)
    assert z_ids(role_scenario["future_reach"]["Z"]) == Z_IDS


def test_disabling_a_workflow_disables_its_jobs() -> None:
    payload = run(
        fx16_report(), {"type": "disable_entrypoint", "node": "wf:.github/workflows/deploy.yml"}
    )
    assert step(payload, 0)["effects"]["disabled_jobs"] == [JOB]
    assert scenario(payload, ACTION)["future_reach"]["Z"] == []


@pytest.mark.parametrize(
    ("entry", "reason"),
    [
        ({"type": "disable_entrypoint", "node": "job:not-there"}, "unresolved_reference"),
        ({"type": "disable_entrypoint", "node": ROLE}, "unresolved_reference"),
        ({"type": "remove_trust", "role": "nope", "principal": OIDC}, "unresolved_reference"),
        ({"type": "remove_trust", "role": ROLE, "principal": "nope"}, "unresolved_reference"),
        ({"type": "remove_trust", "role": ROLE, "principal": DEPLOY_KEY}, "no_matching_trust_edge"),
        (
            {"type": "remove_trust", "role": ROLE, "edge": "0123456789abcdef"},
            "no_matching_trust_edge",
        ),
        ({"type": "remove_trust", "role": ROLE}, "invalid_field"),
        ({"type": "remove_trust", "role": ROLE, "principal": OIDC, "edge": "x"}, "invalid_field"),
        ({"type": "rotate_credential", "credential": "nope"}, "unresolved_reference"),
        ({"type": "rotate_credential", "credential": SESSION}, "not_persistent_credential"),
        ({"type": "revoke_role_sessions", "role": "nope"}, "unresolved_reference"),
        (
            {"type": "revoke_role_sessions", "role": ROLE, "revoked_at": "10:00"},
            "invalid_timestamp",
        ),
        (
            {"type": "revoke_role_sessions", "role": ROLE, "cutoff": "2026-03-01T10:00:00"},
            "invalid_timestamp",
        ),
        (
            {"type": "revoke_role_sessions", "role": ROLE, "issued_no_later_than": "x"},
            "invalid_timestamp",
        ),
        ({"type": "revoke_role_sessions", "role": ROLE, "extra": 1}, "unsupported_field"),
        ({"type": "revoke_role_sessions"}, "missing_field"),
        ({"type": "rotate_credential", "credential": ""}, "invalid_field"),
        ({"type": "disable_entrypoint", "node": 5}, "invalid_field"),
    ],
)
def test_bad_references_and_fields_are_rejected_not_ignored(
    entry: dict[str, Any], reason: str
) -> None:
    payload = run(fx16_report(), entry)
    assert payload["rejected"][0]["reason"] == reason
    assert step(payload, 0)["status"] == "rejected"
    for item in payload["per_scenario"]:
        assert item["after"]["Z"] == item["before"]["Z"]
        assert z_ids(item["future_reach"]["Z"]) == z_ids(item["before"]["Z"])


def test_unknown_and_refused_types_fail_closed() -> None:
    payload = run(
        fx16_report(),
        {"type": "teleport", "node": JOB},
        {"type": "inject_deny_policy", "policy": "{}"},
        {"type": "min_cut"},
        {"type": "apply"},
        {"type": 7},
        disable_job(),
    )
    rejected = {row["index"]: row for row in payload["rejected"]}
    assert rejected[0] == {"index": 0, "type": "teleport", "reason": "unsupported"}
    assert rejected[1]["reason"] == "rejected"
    assert "deny-policy" in rejected[1]["detail"]
    assert "minimum-cut" in rejected[2]["detail"]
    assert "never mutates" in rejected[3]["detail"]
    assert rejected[4]["reason"] == "unsupported"
    assert 5 not in rejected
    assert [item["status"] for item in payload["steps"]] == ["rejected"] * 5 + ["applied"]
    assert scenario(payload, ACTION)["future_reach"]["Z"] == []


def test_plan_shape_errors_are_not_silent() -> None:
    documents: tuple[object, ...] = (
        [],
        {"schema": "other/1.0", "interventions": []},
        {"schema": "nhi-blast-interventions/1.0"},
        {"schema": "nhi-blast-interventions/1.0", "interventions": {}},
        {"schema": "nhi-blast-interventions/1.0", "interventions": [], "extra": 1},
        {"schema": "nhi-blast-interventions/1.0", "interventions": [{}] * 501},
    )
    for document in documents:
        with pytest.raises(PlanError):
            parse_plan(document)
    plan = parse_plan({"schema": "nhi-blast-interventions/1.0", "interventions": ["x", None]})
    assert [entry.rejection.reason for entry in plan.entries if entry.rejection] == [
        "unsupported",
        "unsupported",
    ]


def test_remove_trust_leaves_issued_sessions_active_until_expiry() -> None:
    payload = run(fx16_report(), remove_oidc_trust())
    assert step(payload, 0)["status"] == "applied"
    action = scenario(payload, ACTION)
    assert action["future_reach"]["E"] == []
    assert action["future_reach"]["Z"] == []
    assert z_ids(action["after"]["Z"]) == Z_IDS
    assert action["after"]["E"] == action["before"]["E"]
    issued = action["after"]["issued_before_containment"][0]
    assert issued["credential"] == SESSION
    assert "remains active until its expiry" in issued["note"]
    assert "W-WHATIF-REMOVE-TRUST-WITHOUT-REVOKE" in warning_codes(payload)
    assert "W-WHATIF-REPO-WRITE-ACCEPTANCE-CLEARED" in warning_codes(payload)
    assert scenario(payload, REPO_WRITE)["future_reach"]["E"] == []
    assert scenario(payload, ROLE_SELECTOR)["future_reach"]["E"] != []


def test_remove_trust_by_edge_id_and_repeat_is_a_no_op() -> None:
    report = fx16_report()
    edge = next(
        item
        for item in report.graph.edges
        if item.kind is EdgeKind.CAN_ASSUME and item.src == OIDC and item.dst == ROLE
    )
    payload = run(
        report,
        {"type": "remove_trust", "role": ROLE, "edge": edge.id},
        {"type": "remove_trust", "role": ROLE, "principal": OIDC},
    )
    assert [item["status"] for item in payload["steps"]] == ["applied", "no_effect"]
    assert step(payload, 0)["effects"]["removed_edges"] == [edge.id]
    assert "W-WHATIF-STEP-NO-EFFECT" in warning_codes(payload)


def test_removing_the_credential_binding_edge_cuts_the_second_level_credential() -> None:
    payload = run(
        fx16_report(), {"type": "remove_trust", "role": OPS_ROLE, "principal": DEPLOY_KEY}
    )
    for selector in (ACTION, ROLE_SELECTOR):
        item = scenario(payload, selector)
        assert z_ids(item["future_reach"]["Z"]) == {DEPLOY_KEY, REGISTRY_TOKEN}
        assert z_ids(item["after"]["Z"]) == Z_IDS


def test_repo_write_scenario_follows_a_role_level_acceptance() -> None:
    synthetic = [edge for edge in fx16_report().graph.edges if edge.attrs.get("repo_write") is True]
    assert synthetic
    payload = run(fx16_report(), {"type": "remove_trust", "role": ROLE, "edge": synthetic[0].id})
    assert step(payload, 0)["status"] == "applied"
    assert step(payload, 0)["effects"]["repo_write_acceptance_cleared"] is True
    # The real OIDC trust edge is untouched, so the writer's job still reaches the role.
    assert scenario(payload, REPO_WRITE)["future_reach"]["E"] != []
    assert "W-WHATIF-REPO-WRITE-ACCEPTANCE-CLEARED" in warning_codes(payload)


def test_revocation_is_an_access_deny_never_a_credential_state_change() -> None:
    payload = run(
        fx16_report(),
        revoke(
            revoked_at=REVOKED_AT,
            assessed_at="2026-03-01T10:05:00Z",
            issued_no_later_than={SESSION: ISSUED},
        ),
    )
    baseline = run(fx16_report())
    for item, base in zip(payload["per_scenario"], baseline["per_scenario"], strict=True):
        assert item["future_reach"] == base["future_reach"]
        assert item["after"]["Z"] == base["after"]["Z"]
        assert item["after"]["E"] == base["after"]["E"]
        row = item["after"]["revoked_access"][0]
        assert row["access"] == "denied_by_revocation_policy"
        # Denial is independent of validity: the issuance upper bound also admits
        # older sessions that have expired before this assessment.
        assert row["validity"] == "unknown"
        assert row["display_state"] == "access denied - expiry not established"
        assert row["cutoff"] == "2026-03-01T10:00:30Z"
        assert row["cutoff_assumed"] is True
        assert row["re_issue_possible"] is True
        assert row["residual_unknown"][0]["kind"] == "derived_credentials"
    assert "W-WHATIF-REVOKE-WITHOUT-REMOVE-TRUST" in warning_codes(payload)
    ids = {item["id"] for item in payload["caveats"]}
    assert {f"C-REVOKE-{number}" for number in range(1, 7)} <= ids
    text = " ".join(item["text"] for item in payload["caveats"])
    assert "propagation window" in text
    assert "issued after the cutoff" in text
    assert "every user of the role" in text
    assert "Service-linked roles" in text
    assert "residual_unknown" in text
    assert (
        "https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_revoke-sessions.html" in text
    )


@pytest.mark.parametrize("upper", ["2026-03-01T10:00:30Z", "2026-03-01T10:01:00Z"])
def test_issuance_upper_bound_at_or_after_cutoff_keeps_offline_axes_unknown(upper: str) -> None:
    # This input also admits earlier sessions that were denied or already expired.
    payload = run(
        fx16_report(),
        revoke(
            revoked_at=REVOKED_AT,
            assessed_at="2026-03-01T10:05:00Z",
            issued_no_later_than={SESSION: upper},
        ),
    )
    for item in payload["per_scenario"]:
        row = item["after"]["revoked_access"][0]
        assert (row["validity"], row["access"], row["display_state"]) == (
            "unknown",
            "unknown",
            "unknown",
        )
        assert row["issued_no_later_than"] == upper


def test_revocation_with_remove_trust_does_not_flag_re_issue() -> None:
    payload = run(fx16_report(), revoke(revoked_at=REVOKED_AT), remove_oidc_trust())
    row = scenario(payload, ACTION)["after"]["revoked_access"][0]
    assert row["re_issue_possible"] is False
    assert "W-WHATIF-REVOKE-WITHOUT-REMOVE-TRUST" not in warning_codes(payload)
    assert "W-WHATIF-REMOVE-TRUST-WITHOUT-REVOKE" not in warning_codes(payload)
    assert "note" not in scenario(payload, ACTION)["after"]["issued_before_containment"][0]


def test_missing_inputs_leave_both_axes_unknown() -> None:
    row = scenario(run(fx16_report(), revoke()), ACTION)["after"]["revoked_access"][0]
    assert (row["validity"], row["access"], row["display_state"]) == (
        "unknown",
        "unknown",
        "unknown",
    )
    assert row["cutoff"] is None
    assert row["cutoff_source"] == "missing"


def test_expired_is_reported_only_from_validity() -> None:
    payload = run(
        fx16_report(),
        revoke(revoked_at=REVOKED_AT, assessed_at=ASSESSED_EXPIRED, issued_no_later_than=ISSUED),
    )
    row = scenario(payload, ACTION)["after"]["revoked_access"][0]
    assert row["validity"] == "expired"
    assert row["display_state"] == "expired"
    assert row["access"] == "denied_by_revocation_policy"
    other = run(fx16_report(), revoke(revoked_at=REVOKED_AT, assessed_at="2026-03-01T10:05:00Z"))
    assert scenario(other, ACTION)["after"]["revoked_access"][0]["validity"] == "unknown"


def test_revoking_a_role_without_sessions_has_no_effect() -> None:
    payload = run(fx16_report(), {"type": "revoke_role_sessions", "role": OPS_ROLE})
    assert step(payload, 0)["status"] == "no_effect"
    assert "W-WHATIF-REVOKE-NO-SESSIONS" in warning_codes(payload)
    assert scenario(payload, ACTION)["after"]["revoked_access"] == []


def test_unused_issue_time_keys_are_reported() -> None:
    payload = run(fx16_report(), revoke(issued_no_later_than={"cred:not-a-session": ISSUED}))
    assert "W-WHATIF-UNUSED-ISSUE-TIME" in warning_codes(payload)


def test_rotation_with_a_surviving_path_keeps_the_credential_in_z() -> None:
    payload = run(fx16_report(), rotate(DEPLOY_KEY))
    action = scenario(payload, ACTION)
    assert z_ids(action["after"]["Z"]) == Z_IDS
    assert action["after"]["rotated"] == []
    risk = action["after"]["re_exposure_risk"]
    assert [item["credential"] for item in risk] == [DEPLOY_KEY]
    assert risk[0]["path_edges"]
    assert risk[0]["weakest"] in {"declared", "derived", "assumed"}


def test_rotation_after_closing_the_path_removes_the_credential_from_z() -> None:
    payload = run(fx16_report(), disable_job(), rotate(DEPLOY_KEY))
    action = scenario(payload, ACTION)
    assert z_ids(action["after"]["Z"]) == Z_IDS - {DEPLOY_KEY}
    assert action["after"]["rotated"] == [DEPLOY_KEY]
    assert action["after"]["re_exposure_risk"] == []
    role_scenario = scenario(payload, ROLE_SELECTOR)
    assert [item["credential"] for item in role_scenario["after"]["re_exposure_risk"]] == [
        DEPLOY_KEY
    ]
    assert "W-WHATIF-ROTATE-BEFORE-CLOSING-PATH" not in warning_codes(payload)


def test_rotating_before_closing_the_path_is_flagged() -> None:
    payload = run(fx16_report(), rotate(DEPLOY_KEY), disable_job())
    assert "W-WHATIF-ROTATE-BEFORE-CLOSING-PATH" in warning_codes(payload)
    assert scenario(payload, ACTION)["after"]["rotated"] == [DEPLOY_KEY]


def test_rotation_follows_the_dependency_order_and_flags_inversions() -> None:
    ordered = run(fx16_report(), disable_job(), rotate(DEPLOY_KEY), rotate(DB_PASSWORD))
    assert "W-WHATIF-ROTATION-ORDER" not in warning_codes(ordered)
    inverted = run(fx16_report(), disable_job(), rotate(DB_PASSWORD), rotate(DEPLOY_KEY))
    assert "W-WHATIF-ROTATION-ORDER" in warning_codes(inverted)
    order = scenario(inverted, ACTION)["rotation_order"]
    flat = [ref["id"] for item in order for ref in item["credentials"]]
    assert flat.index(DEPLOY_KEY) < flat.index(DB_PASSWORD)
    assert order[-1]["depends_on"] == [DEPLOY_KEY]


def test_rotating_a_credential_outside_z_has_no_effect() -> None:
    report = scan(FIXTURES / "fx01-minimal", ("repo-write",))
    token = next(
        node.id
        for node in report.graph.nodes
        if node.attrs.get("credential_kind") == "GITHUB_TOKEN"
    )
    payload = run(report, {"type": "rotate_credential", "credential": token})
    assert step(payload, 0)["status"] == "rejected"


def test_unknown_class_edges_never_contribute() -> None:
    report = scan(FIXTURES / "fx08-tf-plan-unknowns", ("repo-write",))
    assert report.scenarios[0].potential
    payload = run(report)
    item = payload["per_scenario"][0]
    assert item["potential"]["before"]["edges"] == list(report.scenarios[0].potential)
    assert item["potential"]["after"]["edges"] == item["potential"]["before"]["edges"]
    assert item["potential"]["after"]["unresolved_inputs"]
    unknown = {edge.id for edge in report.graph.edges if edge.confidence.value == "unknown"}
    assert unknown
    for path in item["residual_paths"]:
        assert not unknown & set(path["path_edges"])
    assert z_ids(item["future_reach"]["Z"]) == z_ids(item["before"]["Z"])


def test_every_output_uses_only_permitted_language() -> None:
    payload = run(
        fx16_report(),
        revoke(revoked_at=REVOKED_AT, assessed_at=ASSESSED_EXPIRED, issued_no_later_than=ISSUED),
        remove_oidc_trust(),
        disable_job(),
        rotate(DEPLOY_KEY),
        {"type": "teleport"},
    )
    text = json.dumps(payload)
    assert FORBIDDEN.search(text) is None
