"""Evidence completeness (plan C6): statuses, mapping coverage and digest determinism."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from nhi_blast.core.completeness import (
    ASSUMPTION_TO_FAMILY,
    CODE_TO_FAMILY,
    FAMILY_LABELS,
    path_collision_diagnostics,
)
from nhi_blast.core.data import assumptions
from nhi_blast.core.models import (
    Completeness,
    CompletenessStatus,
    InputFamily,
    InputFile,
    Report,
)
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.json_report import report_json
from nhi_blast.report.sarif import sarif_report
from tests.test_sessions import _scan as scan_with_workflow_inputs

FIXTURES = Path(__file__).parent / "fixtures"
FX07 = FIXTURES / "fx07-incident"
SRC = Path(__file__).resolve().parents[1] / "src" / "nhi_blast"
S = CompletenessStatus
F = InputFamily
# The completeness digest of fx07 must be identical on every operating system and
# checkout location. A change here means the canonical form or the fixture changed.
FX07_COMPLETENESS_DIGEST = "2e989be9da8113f65fcd668fdd79de0dc31ed34baa79ffeb7e97051364dc19fa"


def _report(root: Path = FX07, **kwargs: object) -> Report:
    options = ScanOptions(root=root, repo_slug="acme/shop", **kwargs)  # type: ignore[arg-type]
    return run_scan(options).report


def _status(report: Report) -> dict[InputFamily, CompletenessStatus]:
    assert report.completeness is not None
    return {item.family: item.status for item in report.completeness.items}


def test_every_emitted_diagnostic_code_is_mapped() -> None:
    emitted: set[str] = set()
    for path in SRC.rglob("*.py"):
        # Diagnostics of the diff and what-if commands describe saved reports, not inputs.
        if path.name == "completeness.py" or {"whatif", "diff"} & set(path.parts):
            continue
        emitted.update(re.findall(r'"(D-[A-Z0-9]+(?:-[A-Z0-9]+)*)"', path.read_text("utf-8")))
    unmapped = sorted(emitted - set(CODE_TO_FAMILY))
    assert not unmapped, f"diagnostic codes with no completeness mapping: {unmapped}"
    assert set(CODE_TO_FAMILY) - emitted <= {"D-PATH-COLLISION"}


def test_every_registered_assumption_is_mapped() -> None:
    registry = assumptions()
    ids = {item.id for item in (registry.get(i) for i in registry.ids())}
    assert ids <= set(ASSUMPTION_TO_FAMILY), sorted(ids - set(ASSUMPTION_TO_FAMILY))


def test_every_family_has_a_label_and_exactly_one_item() -> None:
    report = _report()
    assert report.completeness is not None
    families = [item.family for item in report.completeness.items]
    assert sorted(families) == sorted(InputFamily)
    assert set(FAMILY_LABELS) == set(InputFamily)


def test_all_five_statuses_are_reachable_on_fx07() -> None:
    status = _status(_report())
    assert status[F.GHA_WORKFLOWS] is S.ANALYSED
    assert status[F.OIDC_SUBJECT_BINDING] is S.PARTIALLY_ANALYSED
    assert status[F.TF_HCL] is S.NOT_PROVIDED
    assert status[F.AWS_ORG_POLICIES] is S.NOT_SUPPORTED
    assert status[F.GH_ENVIRONMENT_PROTECTION] is S.NOT_APPLICABLE
    assert set(status.values()) == set(CompletenessStatus)


def test_declared_oidc_format_makes_subject_binding_analysed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FX07, root)
    (root / "nhi-blast.toml").write_text('[github]\nsubject_format = "classic"\n', "utf-8")
    report = _report(root, config_path=root / "nhi-blast.toml")
    assert _status(report)[F.OIDC_SUBJECT_BINDING] is S.ANALYSED


def test_environment_jobs_mark_protection_as_not_provided() -> None:
    status = _status(_report(FIXTURES / "fx04-environment"))
    assert status[F.GH_ENVIRONMENT_PROTECTION] is S.NOT_PROVIDED


def test_exhausted_budget_marks_analysis_limits_partial(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FX07, root)
    config = root / "budget.toml"
    config.write_text("[limits]\nscenario_time_budget_seconds = 0\n", encoding="utf-8")
    report = _report(root, config_path=config, selectors=("repo-write",))
    assert _status(report)[F.ANALYSIS_BUDGET] is S.PARTIALLY_ANALYSED
    assert _status(_report())[F.ANALYSIS_BUDGET] is S.ANALYSED


def test_session_policies_and_unverified_durations_are_partial(tmp_path: Path) -> None:
    plain = _status(scan_with_workflow_inputs(tmp_path / "a"))
    assert plain[F.AWS_SESSION_DURATION] is S.PARTIALLY_ANALYSED
    assert plain[F.IAM_SESSION_POLICIES] is S.ANALYSED
    verified = _status(
        scan_with_workflow_inputs(
            tmp_path / "b",
            "role-duration-seconds: 1800\n"
            "managed-session-policies: arn:aws:iam::111122223333:policy/narrow",
        )
    )
    # fx07 also reaches a second role that no step requests, so its duration stays unknown.
    assert verified[F.AWS_SESSION_DURATION] is S.PARTIALLY_ANALYSED
    assert verified[F.IAM_SESSION_POLICIES] is S.PARTIALLY_ANALYSED


def test_sources_list_the_input_files_of_each_family() -> None:
    report = _report()
    assert report.completeness is not None
    by_family = {item.family: item for item in report.completeness.items}
    workflow_paths = [source.path for source in by_family[F.GHA_WORKFLOWS].sources]
    assert workflow_paths == sorted(workflow_paths, key=lambda path: path.encode("utf-8"))
    assert all(path.startswith(".github/workflows/") for path in workflow_paths)
    hashes = {item.path: item.sha256 for item in report.inputs.files}
    assert all(hashes[s.path] == s.sha256 for item in by_family.values() for s in item.sources)


def test_not_provided_is_not_an_error_and_there_is_no_score() -> None:
    report = _report()
    text = "\n".join(report.scope_and_limits)
    assert "%" not in text
    assert "Completeness:" in text
    assert "fully" not in text.lower()
    assert not any(d.level.value == "error" for d in report.diagnostics)


def test_scope_text_is_generated_from_completeness() -> None:
    report = _report()
    assert report.completeness is not None
    counts = dict.fromkeys(CompletenessStatus, 0)
    for item in report.completeness.items:
        counts[item.status] += 1
    line = next(line for line in report.scope_and_limits if line.startswith("Completeness:"))
    expected = (
        f"{counts[S.ANALYSED]} analysed, {counts[S.PARTIALLY_ANALYSED]} partially analysed, "
        f"{counts[S.NOT_PROVIDED]} not provided, {counts[S.NOT_SUPPORTED]} not supported, "
        f"{counts[S.NOT_APPLICABLE]} not applicable."
    )
    assert expected in line


# ----------------------------------------------------------------------- determinism


def _digest(root: Path) -> str:
    report = _report(root)
    assert report.completeness is not None
    return report.completeness.digest


def test_digest_is_identical_across_checkout_locations(tmp_path: Path) -> None:
    deep = tmp_path / "very" / "deep nested" / "tmp-é" / "checkout"
    shutil.copytree(FX07, deep)
    assert _digest(deep) == _digest(FX07)


def test_digest_matches_the_pinned_cross_platform_constant() -> None:
    assert _digest(FX07) == FX07_COMPLETENESS_DIGEST


def test_digest_follows_input_bytes_and_ignores_discovery_order(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FX07, root)
    before = _digest(root)
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.write_text(workflow.read_text("utf-8") + "# edited\n", encoding="utf-8")
    assert _digest(root) != before


def test_json_output_is_byte_identical_between_runs() -> None:
    assert report_json(_report()) == report_json(_report())


def test_path_collisions_are_reported_not_merged() -> None:
    files = [
        InputFile(path=".github/workflows/CI.yml", sha256="a" * 64, kind="workflow"),
        InputFile(path=".github/workflows/ci.yml", sha256="b" * 64, kind="workflow"),
        InputFile(path=".github/workflows/other.yml", sha256="c" * 64, kind="workflow"),
    ]
    found = path_collision_diagnostics(files)
    assert [item.code for item in found] == ["D-PATH-COLLISION"]


@pytest.mark.security
def test_hostile_fixture_completeness_carries_no_secret_literals() -> None:
    report = _report(FIXTURES / "fx14-hostile")
    assert isinstance(report.completeness, Completeness)
    dumped = report_json(report)
    assert "ghp_" + "Q" * 36 not in dumped


def test_sarif_run_carries_the_completeness_statuses() -> None:
    report = _report()
    assert report.completeness is not None
    properties = sarif_report(report)["runs"][0]["properties"]["nhiBlast/completeness"]
    assert properties["digest"] == report.completeness.digest
    assert properties["statuses"]["aws_org_policies"] == "not_supported"
    assert set(properties["statuses"]) == {item.value for item in InputFamily}
