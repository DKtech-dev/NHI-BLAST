"""Comparability, resolution safety and deltas of the report diff (nhi-blast-diff/1.0)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from nhi_blast.core.data import rules
from nhi_blast.core.diagnostics import warning
from nhi_blast.core.models import (
    CompletenessStatus,
    EvidenceClass,
    InputFamily,
    Lifetime,
    Report,
    Severity,
    ZCredential,
)
from nhi_blast.diff.baseline import apply_gate
from nhi_blast.diff.compare import REASON_CODES, diff_reports
from nhi_blast.diff.families import RULE_FAMILIES, STATUS_RANK, families_for
from nhi_blast.report.loader import load_report
from tests.test_diff_support import (
    FIXTURES,
    RELEASE,
    add_scenario,
    as_report_10,
    base_report,
    classes,
    counts,
    diff_checked,
    duplicate_of,
    edit_file,
    first_finding,
    replace_finding,
    scan_variant,
    with_analyzer,
    with_context,
    with_family,
    with_scenario,
    without_rule,
)

PIN = "abcdef0123456789abcdef0123456789abcdef09"


def _rename_release(root: Path) -> None:
    target = root / ".github/workflows/deploy.yml"
    target.write_text((root / RELEASE).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    (root / RELEASE).unlink()


def _pin_action(root: Path) -> None:
    edit_file(root, RELEASE, "tj-actions/changed-files@v45", f"tj-actions/changed-files@{PIN}")


# ------------------------------------------------------------------ the rule table


def test_every_rule_is_mapped_to_families() -> None:
    catalogue = {rule.id for rule in rules().all()}
    assert catalogue == set(RULE_FAMILIES)
    for rule_id, families in RULE_FAMILIES.items():
        assert families, rule_id
        assert InputFamily.ANALYSIS_BUDGET in families, rule_id
        assert set(families) <= set(InputFamily)


def test_unknown_rules_depend_on_every_family() -> None:
    assert set(families_for("NHB-FUTURE-999")) == set(InputFamily)


def test_status_ranks_follow_the_contract() -> None:
    assert (
        STATUS_RANK[CompletenessStatus.NOT_APPLICABLE] == STATUS_RANK[CompletenessStatus.ANALYSED]
    )
    assert (
        STATUS_RANK[CompletenessStatus.ANALYSED]
        < STATUS_RANK[CompletenessStatus.PARTIALLY_ANALYSED]
    )
    assert (
        STATUS_RANK[CompletenessStatus.PARTIALLY_ANALYSED]
        < STATUS_RANK[CompletenessStatus.NOT_PROVIDED]
    )
    assert (
        STATUS_RANK[CompletenessStatus.NOT_PROVIDED]
        == STATUS_RANK[CompletenessStatus.NOT_SUPPORTED]
    )


# ----------------------------------------------------------------------- self diff


def test_self_diff_is_empty_and_comparable() -> None:
    base = base_report()
    payload = diff_checked(base, base)
    assert payload["comparability"]["status"] == "comparable"
    assert payload["comparability"]["context_drift"] == []
    assert counts(payload) == {
        "new": 0,
        "changed": 0,
        "not_observed": 0,
        "resolved": 0,
        "unchanged": len(base.findings),
    }
    assert payload["graph"]["nodes"] == {"added": [], "removed": [], "changed": []}
    assert payload["graph"]["edges"] == {"added": [], "removed": [], "changed": []}
    assert payload["paths"] == {"added": [], "removed": [], "changed": []}
    assert payload["diagnostics"]["added"] == payload["diagnostics"]["removed"] == []
    for delta in payload["scenarios"]["compared"]:
        assert delta["R"] == {"added": [], "removed": []}
        assert delta["E"]["ttl_changed"] == []
        assert delta["Z"]["changed"] == []


def test_diff_is_deterministic_and_has_no_timestamp() -> None:
    base = base_report()
    first = json.dumps(diff_reports(base, base), sort_keys=True)
    second = json.dumps(diff_reports(base, base), sort_keys=True)
    assert first == second
    assert "generated_at" not in first


# --------------------------------------------------------------- genuine resolution


def test_pinning_a_mutable_action_is_resolved_only_under_comparable_analysis(
    tmp_path: Path,
) -> None:
    head = scan_variant(tmp_path, _pin_action)
    payload = diff_checked(base_report(), head)
    resolved = classes(payload, "resolved")
    assert [item["rule"] for item in resolved] == ["NHB-GHA-001"]
    assert resolved[0]["reasons"] == []
    assert counts(payload)["new"] == 0
    assert counts(payload)["not_observed"] == 0


def test_resolved_requires_a_comparable_context_not_just_a_missing_finding() -> None:
    head = without_rule(base_report(), "NHB-GHA-001")
    payload = diff_checked(base_report(), head)
    assert [item["rule"] for item in classes(payload, "resolved")] == ["NHB-GHA-001"]


# ------------------------------------------------------------ analyzer regressions


def test_rule_disabled_by_an_engine_bump_is_not_observed_never_resolved() -> None:
    head = with_analyzer(without_rule(base_report(), "NHB-GHA-001"), engine_semantics="99")
    payload = diff_checked(base_report(), head)
    assert counts(payload)["resolved"] == 0
    missing = classes(payload, "not_observed")
    assert [item["rule"] for item in missing] == ["NHB-GHA-001"]
    assert missing[0]["reasons"] == ["analyzer_changed"]
    assert payload["comparability"]["status"] == "comparable_with_drift"


def test_tampered_rules_digest_with_identical_version_is_not_observed() -> None:
    head = with_analyzer(without_rule(base_report(), "NHB-GHA-001"), rules_digest="0" * 64)
    assert base_report().context is not None
    assert head.context is not None
    assert head.context.analyzer.tool_version == base_report().context.analyzer.tool_version  # type: ignore[union-attr]
    payload = diff_checked(base_report(), head)
    assert counts(payload)["resolved"] == 0
    assert classes(payload, "not_observed")[0]["reasons"] == ["rules_changed"]


def test_changed_data_file_is_not_observed() -> None:
    base = base_report()
    assert base.context is not None
    data = {**base.context.analyzer.data_digests, "sinks_catalog.yaml": "1" * 64}
    head = with_analyzer(without_rule(base, "NHB-ROT-001"), data_digests=data)
    payload = diff_checked(base, head)
    assert counts(payload)["resolved"] == 0
    assert {tuple(i["reasons"]) for i in classes(payload, "not_observed")} == {("data_changed",)}


def test_tool_version_change_is_not_observed() -> None:
    head = with_analyzer(without_rule(base_report(), "NHB-GHA-001"), tool_version="9.9.9")
    payload = diff_checked(base_report(), head)
    assert counts(payload)["resolved"] == 0


def test_changed_configuration_blocks_resolution() -> None:
    for change in ({"max_depth": 1}, {"strict": True}, {"selectors": ("repo-write", "x")}):
        head = with_context(without_rule(base_report(), "NHB-GHA-001"), **change)
        payload = diff_checked(base_report(), head)
        assert counts(payload)["resolved"] == 0, change
        assert classes(payload, "not_observed")[0]["reasons"] == ["context_changed"]


def test_changed_oidc_settings_and_limits_block_resolution() -> None:
    base = base_report()
    assert base.context is not None
    oidc = base.context.oidc.model_copy(update={"subject_format": "immutable"})
    limits = {**base.context.limits, "max_files": 5}
    for change in ({"oidc": oidc}, {"limits": limits}):
        head = with_context(without_rule(base, "NHB-GHA-001"), **change)
        assert counts(diff_checked(base, head))["resolved"] == 0


# ---------------------------------------------------------------------- changed


def test_changed_finding_is_changed_never_resolved_plus_new() -> None:
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    for update, field in (
        ({"severity": Severity.LOW}, "severity"),
        ({"confidence": EvidenceClass.ASSUMED}, "confidence"),
        (
            {
                "evidence": (
                    *finding.evidence,
                    finding.evidence[0].model_copy(update={"detail": "an added detail"}),
                )
            },
            "evidence",
        ),
        ({"path": tuple(reversed(finding.path))}, "path"),
    ):
        head = replace_finding(base, finding, finding.model_copy(update=update))
        payload = diff_checked(base, head)
        assert counts(payload)["changed"] == 1, field
        assert counts(payload)["resolved"] == 0
        assert counts(payload)["new"] == 0
        assert classes(payload, "changed")[0]["changed_fields"] == [field]


def test_changed_severity_reports_both_severities() -> None:
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    head = replace_finding(base, finding, finding.model_copy(update={"severity": Severity.LOW}))
    record = classes(diff_checked(base, head), "changed")[0]
    assert record["base_severity"] == finding.severity.value
    assert record["head_severity"] == "LOW"
    assert record["severity"] == "LOW"


# ------------------------------------------------------ incomplete or degraded HEAD


def test_truncated_head_scenario_is_not_observed() -> None:
    head = with_scenario(without_rule(base_report(), "NHB-GHA-001"), "repo-write", truncated=True)
    payload = diff_checked(base_report(), head)
    assert counts(payload)["resolved"] == 0
    assert classes(payload, "not_observed")[0]["reasons"] == ["scenario_incomplete"]


def test_time_budget_exhaustion_is_not_observed() -> None:
    base = base_report()
    assert base.context is not None
    scenarios = tuple(
        item.model_copy(update={"time_budget_exhausted": True}) for item in base.context.scenarios
    )
    head = with_context(without_rule(base, "NHB-GHA-001"), scenarios=scenarios)
    payload = diff_checked(base, head)
    assert counts(payload)["resolved"] == 0
    assert classes(payload, "not_observed")[0]["reasons"] == ["scenario_incomplete"]


def test_new_unresolved_inputs_are_not_observed() -> None:
    head = with_scenario(
        without_rule(base_report(), "NHB-GHA-001"), "repo-write", unresolved_inputs=("env.X",)
    )
    payload = diff_checked(base_report(), head)
    assert counts(payload)["resolved"] == 0
    assert classes(payload, "not_observed")[0]["reasons"] == ["scenario_incomplete"]


def test_unresolved_inputs_already_in_base_do_not_block() -> None:
    base = with_scenario(base_report(), "repo-write", unresolved_inputs=("env.X",))
    head = without_rule(base, "NHB-GHA-001")
    assert counts(diff_checked(base, head))["resolved"] == 1


@pytest.mark.parametrize("status", ["not_provided", "not_supported", "partially_analysed"])
def test_degraded_dependency_family_is_not_observed(status: str) -> None:
    head = with_family(without_rule(base_report(), "NHB-GHA-001"), "gha_workflows", status)
    payload = diff_checked(base_report(), head)
    assert counts(payload)["resolved"] == 0
    record = classes(payload, "not_observed")[0]
    assert "dependency_degraded" in record["reasons"]
    assert any(
        item["family"] == "gha_workflows" and item["direction"] == "degraded"
        for item in payload["completeness"]
    )


def test_degradation_of_an_unrelated_family_does_not_block() -> None:
    # NHB-GHA-001 does not read Terraform inputs.
    head = with_family(without_rule(base_report(), "NHB-GHA-001"), "tf_plan_state", "not_provided")
    assert counts(diff_checked(base_report(), head))["resolved"] == 1


def test_improved_family_does_not_block() -> None:
    base = with_family(base_report(), "gha_workflows", "partially_analysed")
    head = without_rule(base_report(), "NHB-GHA-001")
    assert counts(diff_checked(base, head))["resolved"] == 1


def test_analysis_budget_degradation_blocks_every_rule() -> None:
    head = with_family(
        without_rule(base_report(), "NHB-ROT-001"), "analysis_budget", "partially_analysed"
    )
    payload = diff_checked(base_report(), head)
    assert counts(payload)["resolved"] == 0
    assert len(classes(payload, "not_observed")) == 3


# --------------------------------------------------------------- incomplete context


def test_scenario_missing_in_head_is_not_observed() -> None:
    base = add_scenario(base_report(), "fork-pr")
    payload = diff_checked(base, base_report())
    missing = [i for i in classes(payload, "not_observed") if i["scenario"] == "fork-pr"]
    assert missing
    assert all("scenario_missing" in item["reasons"] for item in missing)
    assert payload["scenarios"]["only_in_base"] == ["fork-pr"]
    assert counts(payload)["resolved"] == 0


def test_disjoint_selector_sets_are_incomparable() -> None:
    base = base_report()
    head = base.model_copy(
        update={
            "scenarios": tuple(s.model_copy(update={"selector": "other"}) for s in base.scenarios)
        }
    )
    payload = diff_reports(base, head)
    assert payload["comparability"]["status"] == "incomparable"
    assert [i["code"] for i in payload["comparability"]["incomparable"]] == [
        "scenario_selectors_disjoint"
    ]
    assert payload["findings"] == []


def test_different_repository_is_incomparable() -> None:
    base = base_report()
    head = base.model_copy(
        update={"inputs": base.inputs.model_copy(update={"repo_slug": "acme/other"})}
    )
    payload = diff_reports(base, head)
    assert payload["comparability"]["status"] == "incomparable"
    assert payload["comparability"]["incomparable"][0]["code"] == "repo_slug_differs"
    assert "acme/other" not in json.dumps(payload["comparability"])


def test_major_schema_mismatch_is_incomparable() -> None:
    base = base_report()
    head = base.model_copy(update={"schema_id": "nhi-blast-report/2.0"})
    payload = diff_reports(base, head)
    assert payload["comparability"]["status"] == "incomparable"
    assert payload["comparability"]["incomparable"][0]["code"] == "schema_major_mismatch"


# ------------------------------------------------------------------ schema versions


def test_schema_1_0_against_1_1_has_drift_and_no_resolved() -> None:
    base = as_report_10(base_report())
    head = without_rule(base_report(), "NHB-GHA-001")
    payload = diff_checked(base, head)
    codes = [item["code"] for item in payload["comparability"]["context_drift"]]
    assert "schema_changed" in codes
    assert payload["comparability"]["status"] == "comparable_with_drift"
    assert counts(payload)["resolved"] == 0
    assert "schema_changed" in classes(payload, "not_observed")[0]["reasons"]


def test_two_context_free_reports_never_resolve_anything() -> None:
    base = as_report_10(base_report())
    head = as_report_10(without_rule(base_report(), "NHB-GHA-001"))
    payload = diff_checked(base, head)
    assert counts(payload)["resolved"] == 0
    assert counts(payload)["not_observed"] == 1


def test_saved_schema_1_0_fixture_loads_and_diffs_without_resolved() -> None:
    saved = load_report(FIXTURES / "reports" / "fx07-report-1.0.json")
    payload = diff_checked(saved, base_report())
    assert saved.context is None
    assert counts(payload)["resolved"] == 0
    assert "schema_changed" in [i["code"] for i in payload["comparability"]["context_drift"]]


# ----------------------------------------------------------------------- line shifts


def test_pure_line_shift_is_unchanged(tmp_path: Path) -> None:
    def shift(root: Path) -> None:
        edit_file(root, RELEASE, "jobs:\n", "\n\n# a comment\njobs:\n")

    head = scan_variant(tmp_path, shift)
    payload = diff_checked(base_report(), head)
    assert counts(payload) == {
        "new": 0,
        "changed": 0,
        "not_observed": 0,
        "resolved": 0,
        "unchanged": len(base_report().findings),
    }
    assert payload["graph"]["edges"]["changed"] == []
    assert payload["graph"]["nodes"]["changed"] == []


_SHIFT_POINTS = ("jobs:", "  publish:", "      - uses: tj-actions", "      - name: Notify Slack")


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    inserts=st.lists(
        st.tuples(st.sampled_from(_SHIFT_POINTS), st.sampled_from(["", "# note", "", "  # n"])),
        min_size=1,
        max_size=4,
    )
)
def test_generated_blank_line_and_comment_insertions_are_unchanged(
    tmp_path_factory: pytest.TempPathFactory, inserts: list[tuple[str, str]]
) -> None:
    def shift(root: Path) -> None:
        path = root / RELEASE
        text = path.read_text(encoding="utf-8")
        for anchor, extra in inserts:
            marker = anchor if anchor in text else None
            if marker is None:
                continue
            indent = " " * (len(anchor) - len(anchor.lstrip()))
            text = text.replace(anchor, f"{indent}{extra.strip()}\n{anchor}".lstrip("\n"), 1)
        path.write_text(text, encoding="utf-8", newline="\n")

    head = scan_variant(tmp_path_factory.mktemp("shift"), shift)
    payload = diff_checked(base_report(), head)
    assert counts(payload)["unchanged"] == len(base_report().findings)
    assert counts(payload)["new"] == counts(payload)["not_observed"] == 0


# ----------------------------------------------------------------------- renames


def test_renamed_workflow_is_possible_rename_and_nothing_is_resolved(tmp_path: Path) -> None:
    head = scan_variant(tmp_path, _rename_release)
    payload = diff_checked(base_report(), head)
    assert counts(payload)["resolved"] == 0
    assert counts(payload)["unchanged"] == 0
    renamed = [i for i in classes(payload, "not_observed") if "possible_rename" in i["reasons"]]
    assert renamed
    assert all("evidence_file_missing" in item["reasons"] for item in renamed)
    new = [i for i in classes(payload, "new") if i["possible_rename_of"]]
    assert new
    base_keys = {item["lk"] for item in classes(payload, "not_observed")}
    for item in new:
        assert set(item["possible_rename_of"]) <= base_keys


def test_copy_of_an_evidence_file_at_another_path_is_possible_rename(tmp_path: Path) -> None:
    def copy_file(root: Path) -> None:
        text = (root / RELEASE).read_text(encoding="utf-8")
        (root / ".github/workflows/release-copy.yml").write_text(
            text, encoding="utf-8", newline="\n"
        )

    base = base_report()
    head = without_rule(scan_variant(tmp_path, copy_file), "NHB-GHA-001")
    payload = diff_checked(base, head)
    record = next(i for i in classes(payload, "not_observed") if i["rule"] == "NHB-GHA-001")
    assert "possible_rename" in record["reasons"]


def test_renamed_findings_still_count_as_new() -> None:
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    renamed_path = tuple(item.replace("release.yml", "deploy.yml") for item in finding.path)
    renamed_evidence = tuple(
        e.model_copy(update={"file": (e.file or "").replace("release.yml", "deploy.yml") or None})
        for e in finding.evidence
    )
    head_finding = finding.model_copy(
        update={"id": "moved", "path": renamed_path, "evidence": renamed_evidence}
    )
    head = replace_finding(base, finding, head_finding)
    files = tuple(
        f.model_copy(update={"path": f.path.replace("release.yml", "deploy.yml")})
        for f in head.inputs.files
    )
    head = head.model_copy(update={"inputs": head.inputs.model_copy(update={"files": files})})
    payload = diff_checked(base, head)
    new = classes(payload, "new")
    assert [i["rule"] for i in new] == ["NHB-OIDC-002"]
    assert len(new[0]["possible_rename_of"]) == 1


def test_same_path_with_a_different_primary_file_is_a_possible_rename() -> None:
    # Every evidence file still exists unchanged, so only the path signature can flag this.
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    moved_evidence = (
        finding.evidence[0].model_copy(update={"file": ".github/workflows/ci.yml", "line": 3}),
    )
    head = replace_finding(
        base, finding, finding.model_copy(update={"id": "moved", "evidence": moved_evidence})
    )
    payload = diff_checked(base, head)
    old = [i for i in classes(payload, "not_observed") if i["rule"] == "NHB-OIDC-002"]
    assert old[0]["reasons"] == ["possible_rename"]
    new = classes(payload, "new")
    assert new[0]["possible_rename_of"] == [old[0]["lk"]]
    assert counts(payload)["resolved"] == 0


# ------------------------------------------------------------------ ambiguous matches


def test_duplicate_logical_keys_leave_the_surplus_ambiguous() -> None:
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    doubled = replace_finding(base, finding, finding, duplicate_of(finding))
    payload = diff_checked(doubled, base)
    surplus = [i for i in classes(payload, "not_observed") if i["rule"] == "NHB-OIDC-002"]
    assert len(surplus) == 1
    assert surplus[0]["ambiguous_match"] is True
    assert "ambiguous_match" in surplus[0]["reasons"]
    assert counts(payload)["resolved"] == 0
    reverse = diff_checked(base, doubled)
    extra = [i for i in classes(reverse, "new") if i["rule"] == "NHB-OIDC-002"]
    assert len(extra) == 1
    assert extra[0]["ambiguous_match"] is True


def test_unpaired_finding_sharing_a_terminal_node_with_a_new_one_is_ambiguous() -> None:
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    rerouted = finding.model_copy(
        update={"id": "rerouted", "path": ("job:other#x", *finding.path[1:])}
    )
    head = replace_finding(base, finding, rerouted)
    payload = diff_checked(base, head)
    assert counts(payload)["resolved"] == 0
    old = [i for i in classes(payload, "not_observed") if i["rule"] == "NHB-OIDC-002"]
    assert old[0]["reasons"] == ["ambiguous_match"]
    assert classes(payload, "new")[0]["ambiguous_match"] is True


# ----------------------------------------------------------- reason codes are reachable


def _case_analyzer(_: Path) -> tuple[Report, Report]:
    return base_report(), with_analyzer(
        without_rule(base_report(), "NHB-GHA-001"), tool_version="x"
    )


def _case_rules(_: Path) -> tuple[Report, Report]:
    head = with_analyzer(without_rule(base_report(), "NHB-GHA-001"), rules_digest="1" * 64)
    return base_report(), head


def _case_data(_: Path) -> tuple[Report, Report]:
    base = base_report()
    assert base.context is not None
    data = {**base.context.analyzer.data_digests, "rules_hints.yaml": "2" * 64}
    return base, with_analyzer(without_rule(base, "NHB-GHA-001"), data_digests=data)


def _case_schema(_: Path) -> tuple[Report, Report]:
    return as_report_10(base_report()), without_rule(base_report(), "NHB-GHA-001")


def _case_context(_: Path) -> tuple[Report, Report]:
    return base_report(), with_context(without_rule(base_report(), "NHB-GHA-001"), max_depth=1)


def _case_scenario_missing(_: Path) -> tuple[Report, Report]:
    return add_scenario(base_report(), "fork-pr"), base_report()


def _case_scenario_incomplete(_: Path) -> tuple[Report, Report]:
    head = with_scenario(without_rule(base_report(), "NHB-GHA-001"), "repo-write", truncated=True)
    return base_report(), head


def _case_degraded(_: Path) -> tuple[Report, Report]:
    head = with_family(without_rule(base_report(), "NHB-GHA-001"), "gha_workflows", "not_provided")
    return base_report(), head


def _case_file_missing(tmp_path: Path) -> tuple[Report, Report]:
    return base_report(), scan_variant(tmp_path, _rename_release, name="missing")


def _case_rename(tmp_path: Path) -> tuple[Report, Report]:
    return base_report(), scan_variant(tmp_path, _rename_release, name="renamed")


def _case_ambiguous(_: Path) -> tuple[Report, Report]:
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    return replace_finding(base, finding, finding, duplicate_of(finding)), base


REASON_CASES: dict[str, Callable[[Path], tuple[Report, Report]]] = {
    "analyzer_changed": _case_analyzer,
    "rules_changed": _case_rules,
    "data_changed": _case_data,
    "schema_changed": _case_schema,
    "context_changed": _case_context,
    "scenario_missing": _case_scenario_missing,
    "scenario_incomplete": _case_scenario_incomplete,
    "dependency_degraded": _case_degraded,
    "evidence_file_missing": _case_file_missing,
    "possible_rename": _case_rename,
    "ambiguous_match": _case_ambiguous,
}


def test_every_reason_code_has_a_case() -> None:
    assert set(REASON_CASES) == set(REASON_CODES)


@pytest.mark.parametrize("code", REASON_CODES)
def test_every_reason_code_is_reachable_and_blocks_resolution(code: str, tmp_path: Path) -> None:
    base, head = REASON_CASES[code](tmp_path)
    payload = diff_checked(base, head)
    seen = {reason for item in payload["findings"] for reason in item["reasons"]}
    assert code in seen, (code, seen)
    assert counts(payload)["resolved"] == 0


# ---------------------------------------------------------------- scenario and graph


def test_new_persistent_credential_is_a_new_finding_and_a_z_entry() -> None:
    base = base_report()
    scenario = base.scenarios[0]
    added = ZCredential(
        credential="cred:aws:ssm:/prod/new-api-key:stored",
        depth=0,
        lifetime=Lifetime.PERSISTENT,
        survival_window="until rotated",
        criticality=70,
    )
    partition = scenario.partition.model_copy(update={"Z": (*scenario.partition.Z, added)})
    head = with_scenario(base, "repo-write", partition=partition)
    rot = first_finding(base, "NHB-ROT-001")
    head = head.model_copy(
        update={
            "findings": (
                *head.findings,
                rot.model_copy(
                    update={
                        "id": "NHB-ROT-001-new",
                        "path": (*rot.path[:-1], "sink:aws:ssm:/prod/new-api-key"),
                    }
                ),
            )
        }
    )
    payload = diff_checked(base, head)
    assert [i["rule"] for i in classes(payload, "new")] == ["NHB-ROT-001"]
    delta = payload["scenarios"]["compared"][0]
    assert delta["Z"]["added"] == [added.credential]
    assert delta["Z"]["added_details"][0]["survival_window"] == "until rotated"
    assert delta["Z"]["removed"] == []


def test_scenario_delta_reports_membership_ttl_and_window_changes() -> None:
    base = base_report()
    scenario = base.scenarios[0]
    e_first = scenario.partition.E[0]
    z_first = scenario.partition.Z[0]
    partition = scenario.partition.model_copy(
        update={
            "R": scenario.partition.R[1:],
            "E": (e_first.model_copy(update={"ttl_seconds": 60}), *scenario.partition.E[1:]),
            "Z": (
                z_first.model_copy(update={"survival_window": "1 day"}),
                *scenario.partition.Z[1:],
            ),
        }
    )
    delta = diff_checked(base, with_scenario(base, "repo-write", partition=partition))["scenarios"][
        "compared"
    ][0]
    assert delta["R"]["removed"] == [scenario.partition.R[0]]
    assert delta["E"]["ttl_changed"] == [
        {"credential": e_first.credential, "base": e_first.ttl_seconds, "head": 60}
    ]
    assert delta["Z"]["changed"] == [
        {
            "credential": z_first.credential,
            "field": "survival_window",
            "base": z_first.survival_window,
            "head": "1 day",
        }
    ]


def test_rotation_dependency_changes_are_reported() -> None:
    base = base_report()
    scenario = base.scenarios[0]
    step = scenario.rotation_plan.rotation[0]
    altered = step.model_copy(update={"depends_on": ("step:other",)})
    plan = scenario.rotation_plan.model_copy(
        update={"rotation": (altered, *scenario.rotation_plan.rotation[1:])}
    )
    delta = diff_checked(base, with_scenario(base, "repo-write", rotation_plan=plan))["scenarios"][
        "compared"
    ][0]
    assert delta["rotation_dependencies"]["changed"][0]["head"] == ["step:other"]


def test_graph_delta_uses_node_ids_and_edge_triples_not_edge_ids() -> None:
    base = base_report()
    edge = base.graph.edges[0]
    renumbered = edge.model_copy(update={"id": "0000000000000000"})
    graph = base.graph.model_copy(update={"edges": (renumbered, *base.graph.edges[1:])})
    same = diff_checked(base, base.model_copy(update={"graph": graph}))
    assert same["graph"]["edges"] == {"added": [], "removed": [], "changed": []}
    removed_node = base.graph.nodes[0]
    smaller = base.graph.model_copy(
        update={
            "nodes": base.graph.nodes[1:],
            "edges": tuple(e for e in base.graph.edges if removed_node.id not in (e.src, e.dst)),
        }
    )
    payload = diff_checked(base, base.model_copy(update={"graph": smaller}))
    assert {"id": removed_node.id, "kind": removed_node.kind.value} in payload["graph"]["nodes"][
        "removed"
    ]
    assert payload["graph"]["edges"]["removed"]


def test_diagnostics_delta_lists_added_codes() -> None:
    base = base_report()
    head = base.model_copy(
        update={"diagnostics": (*base.diagnostics, warning("D-TEST", "msg", file="a.yml", line=3))}
    )
    payload = diff_checked(base, head)
    assert payload["diagnostics"]["added"] == [
        {"level": "warning", "code": "D-TEST", "file": "a.yml", "count": 1}
    ]
    assert "msg" not in json.dumps(payload["diagnostics"])


def test_path_delta_lists_added_removed_and_changed_paths() -> None:
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    head = replace_finding(
        base, finding, finding.model_copy(update={"path": tuple(reversed(finding.path))})
    )
    payload = diff_checked(base, head)
    assert len(payload["paths"]["changed"]) == 1
    assert len(payload["paths"]["added"]) == len(payload["paths"]["removed"]) == 1


def test_context_drift_lists_codes_with_digests_only() -> None:
    base = base_report()
    head = with_context(base, max_depth=1, aws_account="111122223333")
    drift = diff_reports(base, head)["comparability"]["context_drift"]
    by_field = {item["field"]: item for item in drift}
    assert by_field["max_depth"]["code"] == "context_changed"
    assert by_field["max_depth"]["head"] == 1
    assert "111122223333" not in json.dumps(drift)
    assert len(by_field["aws_account"]["head"]) == 64


def test_completeness_status_change_is_drift_without_blocking_unrelated_rules() -> None:
    head = with_family(base_report(), "tf_plan_state", "not_provided")
    payload = diff_checked(base_report(), head)
    assert payload["comparability"]["status"] == "comparable_with_drift"
    assert payload["comparability"]["context_drift"][0]["code"] == "completeness_changed"
    assert counts(payload)["unchanged"] == len(base_report().findings)


def test_findings_are_sorted_deterministically() -> None:
    base = base_report()
    shuffled = base.model_copy(update={"findings": tuple(reversed(base.findings))})
    shuffled_diff = diff_reports(base, shuffled)
    plain = diff_reports(base, base)
    # The digest of a report whose arrays were re-ordered legitimately differs.
    shuffled_diff.pop("head")
    plain.pop("head")
    assert json.dumps(shuffled_diff, sort_keys=True) == json.dumps(plain, sort_keys=True)


# ------------------------------------------------- scenario attribution (regression)

_ATTRIBUTION_SELECTORS = ("all-mutable-actions", "repo-write")
_PIN_SHA = "0123456789abcdef0123456789abcdef01234567"


def _pin_one_of_two(root: Path) -> None:
    # release.yml pinned; ci.yml keeps the mutable reference, so the action scenario still exists.
    edit_file(root, RELEASE, "tj-actions/changed-files@v45", f"tj-actions/changed-files@{_PIN_SHA}")


def test_reattributed_trust_findings_are_unchanged_not_resolved_plus_new(tmp_path: Path) -> None:
    base = scan_variant(tmp_path, None, name="base", selectors=_ATTRIBUTION_SELECTORS)
    head = scan_variant(tmp_path, _pin_one_of_two, name="head", selectors=_ATTRIBUTION_SELECTORS)
    # The scanner re-attributes the trust-audit findings to another scenario in HEAD.
    base_scenarios = {i.rule: i.scenario for i in base.findings if i.rule.startswith("NHB-OIDC")}
    head_scenarios = {i.rule: i.scenario for i in head.findings if i.rule.startswith("NHB-OIDC")}
    assert base_scenarios != head_scenarios
    payload = diff_checked(base, head)
    by_rule = {
        rule: [i["class"] for i in payload["findings"] if i["rule"] == rule]
        for rule in ("NHB-OIDC-002", "NHB-OIDC-005")
    }
    assert by_rule == {"NHB-OIDC-002": ["unchanged"], "NHB-OIDC-005": ["unchanged"]}
    assert [i["rule"] for i in classes(payload, "resolved")] == ["NHB-GHA-001"]
    assert counts(payload)["new"] == 0
    assert counts(payload)["changed"] == 0
    gated = apply_gate(payload, None, fail_on=Severity.HIGH, as_of=None)
    assert gated["gate"]["exit_code"] == 0


def test_scenario_bound_finding_still_keys_by_scenario() -> None:
    base = add_scenario(base_report(), "fork-pr")
    surv = [i for i in base.findings if i.rule == "NHB-SURV-001"]
    assert {i.scenario for i in surv} == {"repo-write", "fork-pr"}
    payload = diff_checked(base, base_report())
    missing = [i for i in classes(payload, "not_observed") if i["rule"] == "NHB-SURV-001"]
    assert [i["scenario"] for i in missing] == ["fork-pr"]
    assert [
        i["scenario"]
        for i in payload["findings"]
        if i["class"] == "unchanged" and i["rule"] == "NHB-SURV-001"
    ] == ["repo-write"]


def test_moved_attribution_alone_is_never_reported_as_changed() -> None:
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    head = replace_finding(base, finding, finding.model_copy(update={"scenario": "fork-pr"}))
    payload = diff_checked(base, head)
    assert counts(payload)["unchanged"] == len(base.findings)


def test_non_scenario_rule_resolution_needs_every_shared_scenario_complete() -> None:
    base = add_scenario(base_report(), "fork-pr")
    head = with_scenario(without_rule(base, "NHB-GHA-001"), "fork-pr", truncated=True)
    payload = diff_checked(base, head)
    assert counts(payload)["resolved"] == 0
    record = next(i for i in classes(payload, "not_observed") if i["rule"] == "NHB-GHA-001")
    assert record["reasons"] == ["scenario_incomplete"]


def test_non_scenario_rule_resolution_ignores_a_scenario_that_only_base_had() -> None:
    base = add_scenario(base_report(), "fork-pr")
    head = without_rule(base_report(), "NHB-GHA-001")
    payload = diff_checked(base, head)
    # The selector set differs (context_changed), but no scenario_* reason is added for a scenario
    # HEAD does not have.
    record = next(i for i in classes(payload, "not_observed") if i["rule"] == "NHB-GHA-001")
    assert record["reasons"] == ["context_changed"]
