"""Reviewed baseline: suppression scope, expiry, accept and prune."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import nhi_blast.diff.baseline as module
from nhi_blast.core.models import Severity
from nhi_blast.diff.baseline import (
    Baseline,
    BaselineEntry,
    BaselineError,
    accept_entry,
    apply_gate,
    baseline_text,
    load_baseline,
    load_diff,
    prune_entries,
    write_baseline,
)
from nhi_blast.diff.compare import diff_reports
from nhi_blast.diff.render import to_json_text
from tests.test_diff_support import (
    base_report,
    classes,
    first_finding,
    replace_finding,
    with_analyzer,
    with_family,
    without_rule,
)

DIGEST = "a" * 64


@pytest.mark.parametrize("which", ["baseline", "diff"])
def test_file_growth_after_stat_is_rejected_by_opened_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, which: str
) -> None:
    path = tmp_path / "input.json"
    raw = (
        baseline_text(Baseline(created_from_report_digest=DIGEST))
        if which == "baseline"
        else to_json_text(diff_reports(base_report(), base_report()))
    ).encode("utf-8")
    path.write_bytes(raw)
    constant = "_MAX_FILE_BYTES" if which == "baseline" else "_MAX_DIFF_BYTES"
    monkeypatch.setattr(module, constant, len(raw) + 5)
    original = Path.open
    grown = False

    def growing(candidate: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        nonlocal grown
        if candidate == path and "r" in mode and not grown:
            grown = True
            with original(path, "ab") as handle:
                handle.write(b" " * 20)
        return original(candidate, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", growing)
    with pytest.raises(BaselineError, match=r"limit|larger"):
        (load_baseline if which == "baseline" else load_diff)(path)


def _new_finding_diff() -> dict[str, Any]:
    """HEAD adds one finding that BASE lacks."""
    base = without_rule(base_report(), "NHB-OIDC-002")
    return diff_reports(base, base_report())


def _entry(lk: str, rule: str = "NHB-OIDC-002", **extra: Any) -> BaselineEntry:
    return BaselineEntry(lk=lk, rule=rule, reason="reviewed", reviewer="alice", **extra)


def _baseline(*entries: BaselineEntry) -> Baseline:
    return Baseline(created_from_report_digest=DIGEST, entries=entries)


def test_new_finding_gates_the_exit_code_at_or_above_the_threshold() -> None:
    diff = _new_finding_diff()
    new = classes(diff, "new")
    assert [i["rule"] for i in new] == ["NHB-OIDC-002"]
    high = apply_gate(diff, None, fail_on=Severity.HIGH, as_of=None)
    assert high["gate"]["exit_code"] == 1
    assert high["gate"]["blocking"] == [new[0]["lk"]]
    critical_only = apply_gate(diff, None, fail_on=Severity.CRITICAL, as_of=None)
    assert critical_only["gate"]["exit_code"] == (1 if new[0]["severity"] == "CRITICAL" else 0)
    never = apply_gate(diff, None, fail_on=None, as_of=None)
    assert never["gate"]["exit_code"] == 0


def test_baseline_suppresses_only_the_exit_code_not_the_finding() -> None:
    diff = _new_finding_diff()
    lk = classes(diff, "new")[0]["lk"]
    gated = apply_gate(diff, _baseline(_entry(lk)), fail_on=Severity.LOW, as_of=None)
    assert gated["gate"]["exit_code"] == 0
    assert gated["gate"]["suppressed"] == [lk]
    record = classes(gated, "new")[0]
    assert record["class"] == "new"
    assert record["suppressed_by_baseline"] is True
    assert gated["summary"]["counts"]["new"] == 1


def test_baseline_entry_for_another_finding_does_not_suppress() -> None:
    diff = _new_finding_diff()
    gated = apply_gate(diff, _baseline(_entry("b" * 64)), fail_on=Severity.LOW, as_of=None)
    assert gated["gate"]["exit_code"] == 1


def test_baseline_entry_with_the_wrong_rule_is_ignored_with_a_diagnostic() -> None:
    diff = _new_finding_diff()
    lk = classes(diff, "new")[0]["lk"]
    gated = apply_gate(
        diff, _baseline(_entry(lk, rule="NHB-GHA-001")), fail_on=Severity.LOW, as_of=None
    )
    assert gated["gate"]["exit_code"] == 1
    assert [d["code"] for d in gated["diagnostics"]["baseline"]] == ["D-DIFF-BASELINE-MISMATCH"]


def test_baseline_never_hides_drift_diagnostics_or_completeness() -> None:
    base = without_rule(base_report(), "NHB-OIDC-002")
    head = with_family(
        with_analyzer(base_report(), tool_version="9.9.9"), "tf_plan_state", "not_provided"
    )
    diff = diff_reports(base, head)
    lks = [i["lk"] for i in classes(diff, "new")]
    baseline = _baseline(
        *(_entry(lk, rule=i["rule"]) for lk, i in zip(lks, classes(diff, "new"), strict=True))
    )
    plain = apply_gate(diff, None, fail_on=Severity.LOW, as_of=None)
    gated = apply_gate(diff, baseline, fail_on=Severity.LOW, as_of=None)
    for section in ("comparability", "completeness", "graph", "scenarios", "paths"):
        assert gated[section] == plain[section]
    assert gated["diagnostics"]["added"] == plain["diagnostics"]["added"]
    assert gated["comparability"]["status"] == "comparable_with_drift"
    assert gated["gate"]["exit_code"] == 0


def test_baseline_does_not_suppress_incomparable_exit_code() -> None:
    base = base_report()
    head = base.model_copy(update={"inputs": base.inputs.model_copy(update={"repo_slug": "x/y"})})
    gated = apply_gate(diff_reports(base, head), _baseline(), fail_on=Severity.LOW, as_of=None)
    assert gated["gate"]["exit_code"] == 3


def test_baseline_only_suppresses_new_findings() -> None:
    base = base_report()
    finding = first_finding(base, "NHB-OIDC-002")
    head = replace_finding(base, finding, finding.model_copy(update={"severity": Severity.LOW}))
    diff = diff_reports(base, head)
    lk = classes(diff, "changed")[0]["lk"]
    gated = apply_gate(diff, _baseline(_entry(lk)), fail_on=Severity.LOW, as_of=None)
    assert classes(gated, "changed")[0]["suppressed_by_baseline"] is False
    assert gated["gate"]["suppressed"] == []


def test_expired_entry_stops_suppressing_and_reports_a_diagnostic() -> None:
    diff = _new_finding_diff()
    lk = classes(diff, "new")[0]["lk"]
    baseline = _baseline(_entry(lk, expires="2026-06-30"))
    fresh = apply_gate(diff, baseline, fail_on=Severity.LOW, as_of=date(2026, 6, 29))
    assert fresh["gate"]["exit_code"] == 0
    assert fresh["diagnostics"]["baseline"] == []
    expired = apply_gate(diff, baseline, fail_on=Severity.LOW, as_of=date(2026, 6, 30))
    assert expired["gate"]["exit_code"] == 1
    assert expired["gate"]["expired"] == [lk]
    assert expired["diagnostics"]["baseline"] == [
        {"code": "D-DIFF-BASELINE-EXPIRED", "lk": lk, "expires": "2026-06-30"}
    ]


def test_no_expiry_check_without_an_as_of_date() -> None:
    diff = _new_finding_diff()
    lk = classes(diff, "new")[0]["lk"]
    gated = apply_gate(
        diff, _baseline(_entry(lk, expires="2000-01-01")), fail_on=Severity.LOW, as_of=None
    )
    assert gated["gate"]["exit_code"] == 0
    assert gated["gate"]["as_of"] is None


def test_gate_does_not_mutate_its_input() -> None:
    diff = _new_finding_diff()
    before = json.dumps(diff, sort_keys=True)
    apply_gate(diff, None, fail_on=Severity.LOW, as_of=None)
    assert json.dumps(diff, sort_keys=True) == before


# ------------------------------------------------------------------- files and commands


def test_baseline_file_is_sorted_canonical_and_timestamp_free(tmp_path: Path) -> None:
    baseline = _baseline(_entry("c" * 64), _entry("a" * 64, expires="2030-01-01"))
    path = tmp_path / "baseline.json"
    write_baseline(path, baseline)
    text = path.read_text(encoding="utf-8")
    assert text == baseline_text(baseline)
    data = json.loads(text)
    assert [e["lk"] for e in data["entries"]] == ["a" * 64, "c" * 64]
    assert data["schema"] == "nhi-blast-baseline/1.0"
    assert load_baseline(path) == _baseline(
        _entry("a" * 64, expires="2030-01-01"), _entry("c" * 64)
    )
    assert "T00" not in text


def test_accept_adds_an_entry_only_for_a_new_finding() -> None:
    diff = _new_finding_diff()
    new = classes(diff, "new")[0]
    updated = accept_entry(
        None, diff, lk=new["lk"], reason="tracked in INC-1", reviewer="bob", expires="2030-12-31"
    )
    assert updated.created_from_report_digest == diff["head"]["report_digest"]
    assert updated.entries[0].lk == new["lk"]
    assert updated.entries[0].rule == "NHB-OIDC-002"
    self_diff = diff_reports(base_report(), base_report())
    other = next(r["lk"] for r in self_diff["findings"] if r["lk"] != new["lk"])
    with pytest.raises(BaselineError, match="only new findings"):
        accept_entry(None, diff, lk=other, reason="r", reviewer="b", expires=None)
    with pytest.raises(BaselineError, match="already in the baseline"):
        accept_entry(updated, diff, lk=new["lk"], reason="r", reviewer="b", expires=None)
    with pytest.raises(BaselineError, match="64-character"):
        accept_entry(None, diff, lk="nope", reason="r", reviewer="b", expires=None)
    with pytest.raises(BaselineError, match="YYYY-MM-DD"):
        accept_entry(None, diff, lk=new["lk"], reason="r", reviewer="b", expires="tomorrow")
    with pytest.raises(BaselineError, match="must not be empty"):
        accept_entry(None, diff, lk=new["lk"], reason=" ", reviewer="b", expires=None)


def test_accept_never_accepts_resolved_changed_or_not_observed() -> None:
    base = base_report()
    head = with_analyzer(without_rule(base, "NHB-GHA-001"), engine_semantics="99")
    diff = diff_reports(base, head)
    lk = classes(diff, "not_observed")[0]["lk"]
    with pytest.raises(BaselineError, match="only new findings"):
        accept_entry(None, diff, lk=lk, reason="r", reviewer="b", expires=None)


def test_prune_removes_only_resolved_entries() -> None:
    base = base_report()
    head = without_rule(base, "NHB-GHA-001")
    diff = diff_reports(base, head)
    resolved = classes(diff, "resolved")[0]
    unchanged = classes(diff, "unchanged")[0]
    baseline = _baseline(
        _entry(resolved["lk"], rule=resolved["rule"]),
        _entry(unchanged["lk"], rule=unchanged["rule"]),
        _entry("d" * 64),
    )
    pruned, removed = prune_entries(baseline, diff)
    assert [e.lk for e in removed] == [resolved["lk"]]
    assert {e.lk for e in pruned.entries} == {unchanged["lk"], "d" * 64}


def test_prune_keeps_entries_whose_finding_is_only_not_observed() -> None:
    base = base_report()
    head = with_analyzer(without_rule(base, "NHB-GHA-001"), engine_semantics="99")
    diff = diff_reports(base, head)
    lk = classes(diff, "not_observed")[0]["lk"]
    pruned, removed = prune_entries(_baseline(_entry(lk, rule="NHB-GHA-001")), diff)
    assert removed == ()
    assert len(pruned.entries) == 1


HOSTILE_BASELINES = [
    "",
    "not json",
    "[]",
    '{"schema":"nhi-blast-baseline/2.0","created_from_report_digest":"'
    + "a" * 64
    + '","entries":[]}',
    '{"schema":"nhi-blast-baseline/1.0","created_from_report_digest":"short","entries":[]}',
    '{"schema":"nhi-blast-baseline/1.0","created_from_report_digest":"'
    + "a" * 64
    + '","entries":[{"lk":"x"}]}',
    '{"schema":"nhi-blast-baseline/1.0","created_from_report_digest":"'
    + "a" * 64
    + '","entries":[],"extra":1}',
    "[" * 100000,
]


@pytest.mark.parametrize("text", HOSTILE_BASELINES, ids=range(len(HOSTILE_BASELINES)))
def test_hostile_baseline_files_are_rejected_with_a_controlled_error(
    tmp_path: Path, text: str
) -> None:
    path = tmp_path / "b.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(BaselineError):
        load_baseline(path)


def test_duplicate_baseline_entries_and_bad_dates_are_rejected(tmp_path: Path) -> None:
    entry = {"lk": "a" * 64, "rule": "R", "reason": "r", "reviewer": "b"}
    for entries, message in (
        ([entry, entry], "more than once"),
        ([{**entry, "expires": "2026-13-45"}], "calendar date"),
    ):
        path = tmp_path / "b.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "nhi-blast-baseline/1.0",
                    "created_from_report_digest": DIGEST,
                    "entries": entries,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(BaselineError, match=message):
            load_baseline(path)


def test_oversized_baseline_and_diff_files_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "_MAX_FILE_BYTES", 10)
    monkeypatch.setattr(module, "_MAX_DIFF_BYTES", 10)
    path = tmp_path / "big.json"
    path.write_text("x" * 100, encoding="utf-8")
    with pytest.raises(BaselineError, match="larger"):
        load_baseline(path)
    with pytest.raises(BaselineError, match="larger"):
        load_diff(path)


def test_diff_files_must_be_nhi_blast_diffs(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    for text in ("[]", '{"schema":"other"}', '{"schema":"nhi-blast-diff/1.0"}', "{"):
        path.write_text(text, encoding="utf-8")
        with pytest.raises(BaselineError):
            load_diff(path)
    path.write_text(to_json_text(_new_finding_diff()), encoding="utf-8")
    assert load_diff(path)["schema"] == "nhi-blast-diff/1.0"
