"""Loop 2 tests: escalation gate, PR comment, rename accuracy, and criticality rank."""

from __future__ import annotations

import re

from nhi_blast.analysis.rank import rank_mutable_actions, rank_sort_key
from nhi_blast.core.models import (
    Inputs,
    PinKind,
    RankRow,
    Severity,
    ZCredential,
)
from nhi_blast.diff.baseline import Baseline, BaselineEntry, apply_gate, is_severity_escalation
from nhi_blast.diff.compare import diff_reports
from nhi_blast.diff.render import render_pr_comment
from tests.test_diff_support import (
    base_report,
    classes,
    first_finding,
    replace_finding,
    with_analyzer,
    with_family,
    without_rule,
)
from tests.test_graph_builder import build_inline

DIGEST = "a" * 64
INPUTS = Inputs(digest="abc123", repo_slug="acme/shop", repo_slug_source="test")


# ------------------------------------------------------------ 1. apply_gate severity escalations


def _escalated_diff(base_sev: Severity, head_sev: Severity) -> dict:
    rep = base_report()
    finding = first_finding(rep, "NHB-OIDC-002")
    base = replace_finding(rep, finding, finding.model_copy(update={"severity": base_sev}))
    head = replace_finding(rep, finding, finding.model_copy(update={"severity": head_sev}))
    return diff_reports(base, head)


def test_gate_fails_on_severity_escalation_at_or_above_fail_on() -> None:
    diff = _escalated_diff(Severity.LOW, Severity.HIGH)
    changed = classes(diff, "changed")
    assert len(changed) == 1
    assert is_severity_escalation(changed[0]) is True

    gated_high = apply_gate(diff, None, fail_on=Severity.HIGH, as_of=None)
    assert gated_high["gate"]["exit_code"] == 1
    assert gated_high["gate"]["blocking"] == [changed[0]["lk"]]

    gated_crit = apply_gate(diff, None, fail_on=Severity.CRITICAL, as_of=None)
    assert gated_crit["gate"]["exit_code"] == 0
    assert gated_crit["gate"]["blocking"] == []

    gated_never = apply_gate(diff, None, fail_on=None, as_of=None)
    assert gated_never["gate"]["exit_code"] == 0
    assert gated_never["gate"]["blocking"] == []


def test_gate_fails_on_medium_to_critical_escalation() -> None:
    diff = _escalated_diff(Severity.MEDIUM, Severity.CRITICAL)
    lk = classes(diff, "changed")[0]["lk"]
    gated = apply_gate(diff, None, fail_on=Severity.HIGH, as_of=None)
    assert gated["gate"]["exit_code"] == 1
    assert gated["gate"]["blocking"] == [lk]


def test_gate_ignores_escalation_below_fail_on_and_ignores_downgrades() -> None:
    below = _escalated_diff(Severity.INFO, Severity.MEDIUM)
    gated_below = apply_gate(below, None, fail_on=Severity.HIGH, as_of=None)
    assert gated_below["gate"]["exit_code"] == 0
    assert gated_below["gate"]["blocking"] == []

    downgrade = _escalated_diff(Severity.CRITICAL, Severity.HIGH)
    assert is_severity_escalation(classes(downgrade, "changed")[0]) is False
    gated_down = apply_gate(downgrade, None, fail_on=Severity.LOW, as_of=None)
    assert gated_down["gate"]["exit_code"] == 0
    assert gated_down["gate"]["blocking"] == []


def test_gate_ignores_non_severity_changed_finding_and_does_not_suppress_escalation() -> None:
    rep = base_report()
    finding = first_finding(rep, "NHB-OIDC-002")
    same_sev_head = replace_finding(
        rep,
        finding,
        finding.model_copy(update={"assumptions": (*finding.assumptions, "A-EXTRA")}),
    )
    same_sev_diff = diff_reports(rep, same_sev_head)
    assert classes(same_sev_diff, "changed")
    gated_same = apply_gate(same_sev_diff, None, fail_on=Severity.LOW, as_of=None)
    assert gated_same["gate"]["exit_code"] == 0
    assert gated_same["gate"]["blocking"] == []

    # Baseline entry cannot suppress a changed finding's severity escalation
    esc = _escalated_diff(Severity.LOW, Severity.HIGH)
    lk = classes(esc, "changed")[0]["lk"]
    baseline = Baseline(
        created_from_report_digest=DIGEST,
        entries=(BaselineEntry(lk=lk, rule="NHB-OIDC-002", reason="old", reviewer="alice"),),
    )
    gated_esc = apply_gate(esc, baseline, fail_on=Severity.HIGH, as_of=None)
    assert gated_esc["gate"]["exit_code"] == 1
    assert gated_esc["gate"]["blocking"] == [lk]
    assert gated_esc["gate"]["suppressed"] == []


# --------------------------------------------------------------- 2. render_pr_comment upgrades


def test_pr_comment_shows_z_additions_escalations_baseline_drift_and_degradations() -> None:
    base = without_rule(base_report(), "NHB-OIDC-002")
    # Make NHB-GHA-001 LOW in BASE so it escalates to HIGH in HEAD
    gha = first_finding(base, "NHB-GHA-001")
    base = replace_finding(base, gha, gha.model_copy(update={"severity": Severity.LOW}))

    # Build HEAD with analyzer drift, completeness degradation, and an extra Z persistent credential
    head = with_family(
        with_analyzer(base_report(), tool_version="9.9.9"),
        "tf_plan_state",
        "not_provided",
    )
    scenario = head.scenarios[0]
    new_z = ZCredential(
        credential="cred:prod-deploy-key",
        lifetime=scenario.partition.Z[0].lifetime,
        survival_window="until rotated",
        criticality=95,
        depth=1,
    )
    new_part = scenario.partition.model_copy(update={"Z": (*scenario.partition.Z, new_z)})
    head_scenario = scenario.model_copy(update={"partition": new_part})
    head = head.model_copy(update={"scenarios": (head_scenario, *head.scenarios[1:])})

    diff = diff_reports(base, head)
    new_rec = classes(diff, "new")[0]
    baseline = Baseline(
        created_from_report_digest=DIGEST,
        entries=(
            BaselineEntry(
                lk=new_rec["lk"],
                rule=new_rec["rule"],
                reason="accepted in SEC-42",
                reviewer="alice",
            ),
        ),
    )
    gated = apply_gate(diff, baseline, fail_on=Severity.HIGH, as_of=None)
    md = render_pr_comment(gated)

    assert "## NHI-Blast Diff Summary" in md
    assert "**Comparability:** `comparable_with_drift`" in md
    assert "### Comparability drift" in md
    assert "analyzer_changed" in md
    assert "### Completeness degradations" in md
    assert "tf_plan_state" in md
    assert "degraded" in md
    assert "### Blast Radius Delta (`Z` Persistent Additions)" in md
    assert "cred:prod-deploy-key" in md
    assert "until rotated" in md
    assert "95" in md
    assert "### Severity Escalations" in md
    assert "LOW -> HIGH" in md
    assert "NHB-GHA-001" in md
    assert "### New findings" in md
    assert "baselined (suppressed)" in md
    assert "**Gate:** `fail_on=high`, blocking=`1`, baselined=`1`, exit=`1`" in md

    banned = re.compile(
        r"\b(proves?|proven|guarantee[sd]?|safe|fixed|exploitable|taken over)\b", re.I
    )
    assert banned.search(md) is None


def test_pr_comment_surfaces_incomparable_causes() -> None:
    base = base_report()
    head = base.model_copy(update={"inputs": base.inputs.model_copy(update={"repo_slug": "x/y"})})
    gated = apply_gate(diff_reports(base, head), None, fail_on=Severity.LOW, as_of=None)
    md = render_pr_comment(gated)

    assert "## NHI-Blast Diff Summary" in md
    assert "**Comparability:** `incomparable`" in md
    assert "repo_slug_differs" in md
    assert "exit=`3`" in md


# ----------------------------------------------------------- 3. compare.py possible_rename fix


def test_preexisting_duplicate_file_does_not_emit_false_possible_rename() -> None:
    base = base_report()
    release_input = next(f for f in base.inputs.files if f.path.endswith("release.yml"))
    dup_input = release_input.model_copy(update={"path": ".github/workflows/release-dup.yml"})

    # Both release.yml and release-dup.yml exist in BASE with identical sha256
    base_with_dup = base.model_copy(
        update={"inputs": base.inputs.model_copy(update={"files": (*base.inputs.files, dup_input)})}
    )
    # In HEAD, release.yml still exists (edited with a new sha256), release-dup.yml is unchanged,
    # and the NHB-GHA-001 finding in release.yml is no longer present.
    edited_release = release_input.model_copy(update={"sha256": "f" * 64})
    head_files = tuple(
        edited_release if f.path == release_input.path else f for f in base_with_dup.inputs.files
    )
    head = without_rule(
        base_with_dup.model_copy(
            update={"inputs": base_with_dup.inputs.model_copy(update={"files": head_files})}
        ),
        "NHB-GHA-001",
    )

    payload = diff_reports(base_with_dup, head)
    resolved = [r for r in classes(payload, "resolved") if r["rule"] == "NHB-GHA-001"]
    not_obs = [r for r in classes(payload, "not_observed") if r["rule"] == "NHB-GHA-001"]
    assert len(resolved) == 1
    assert not_obs == []


def test_deleted_evidence_file_with_matching_sha_elsewhere_still_emits_possible_rename() -> None:
    base = base_report()
    release_input = next(f for f in base.inputs.files if f.path.endswith("release.yml"))
    moved_input = release_input.model_copy(update={"path": ".github/workflows/deploy.yml"})
    head_files = tuple(
        moved_input if f.path == release_input.path else f for f in base.inputs.files
    )
    head = without_rule(
        base.model_copy(update={"inputs": base.inputs.model_copy(update={"files": head_files})}),
        "NHB-GHA-001",
    )

    payload = diff_reports(base, head)
    not_obs = [r for r in classes(payload, "not_observed") if r["rule"] == "NHB-GHA-001"]
    assert len(not_obs) == 1
    assert "evidence_file_missing" in not_obs[0]["reasons"]
    assert "possible_rename" in not_obs[0]["reasons"]


# -------------------------------------------------------------------- 4. rank.py criticality


def test_rank_prioritizes_highest_criticality_over_raw_z_count() -> None:
    graph = build_inline(
        """
name: CriticalityRank
on: push
jobs:
  low_crit_many:
    runs-on: ubuntu-latest
    env:
      A: ${{ secrets.FIRST_SECRET }}
      B: ${{ secrets.SECOND_SECRET }}
      C: ${{ secrets.THIRD_SECRET }}
    steps:
      - uses: example/many-low@v1
  high_crit_one:
    runs-on: ubuntu-latest
    env:
      GPG_PRIVATE_KEY: ${{ secrets.GPG_PRIVATE_KEY }}
    steps:
      - uses: example/one-high@v1
"""
    ).graph

    rows = rank_mutable_actions(graph, inputs=INPUTS).rows
    assert [r.action for r in rows] == ["example/one-high@v1", "example/many-low@v1"]
    assert rows[0].highest_criticality > rows[1].highest_criticality
    assert rows[0].z_count == 1
    assert rows[1].z_count == 3


def test_rank_sort_key_tiebreaks_deterministically() -> None:
    a = RankRow(
        action="org/a@v1",
        pin_kind=PinKind.TAG,
        use_sites=1,
        jobs_with_oidc=0,
        r_count=1,
        e_count=0,
        z_count=1,
        highest_criticality=90,
    )
    b = RankRow(
        action="org/b@v1",
        pin_kind=PinKind.TAG,
        use_sites=5,
        jobs_with_oidc=1,
        r_count=2,
        e_count=3,
        z_count=4,
        highest_criticality=55,
    )
    c = RankRow(
        action="org/c@v1",
        pin_kind=PinKind.TAG,
        use_sites=2,
        jobs_with_oidc=0,
        r_count=1,
        e_count=1,
        z_count=2,
        highest_criticality=90,
    )
    ordered = sorted([a, b, c], key=rank_sort_key)
    assert [row.action for row in ordered] == ["org/c@v1", "org/a@v1", "org/b@v1"]
