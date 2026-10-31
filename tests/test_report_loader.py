"""Schema 1.1 compatibility: 1.0 reports stay readable and the context is recorded."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from nhi_blast import READABLE_SCHEMAS, SCHEMA_VERSION
from nhi_blast.core.config import Config
from nhi_blast.core.models import RankReport
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.explain import render_explanation
from nhi_blast.report.loader import ReportLoadError, load_report

ROOT = Path(__file__).resolve().parents[1]
FX07 = ROOT / "tests" / "fixtures" / "fx07-incident"
REPORT_10 = ROOT / "tests" / "fixtures" / "reports" / "fx07-report-1.0.json"
SCHEMA_10 = ROOT / "docs" / "schema" / "report-1.0.schema.json"
SCHEMA_11 = ROOT / "docs" / "schema" / "report.schema.json"
ACTION = "action:tj-actions/changed-files@v45"


def _scan_json(tmp_path: Path) -> dict[str, object]:
    run_scan(
        ScanOptions(root=FX07, selectors=(ACTION,), formats=("json",), out_dir=tmp_path / "out")
    )
    return json.loads((tmp_path / "out" / "report.json").read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def test_readable_schemas_cover_both_versions() -> None:
    assert set(READABLE_SCHEMAS) == {"nhi-blast-report/1.0", "nhi-blast-report/1.1"}
    assert SCHEMA_VERSION == "nhi-blast-report/1.1"


def test_frozen_1_0_report_loads_without_context() -> None:
    report = load_report(REPORT_10)
    assert report.schema_id == "nhi-blast-report/1.0"
    assert report.context is None
    assert report.findings
    assert report.scenarios


def test_frozen_1_0_report_matches_the_frozen_1_0_schema() -> None:
    schema = json.loads(SCHEMA_10.read_text(encoding="utf-8"))
    document = json.loads(REPORT_10.read_text(encoding="utf-8"))
    jsonschema.validate(document, schema)
    assert "context" not in schema["properties"]


def test_frozen_1_0_report_can_still_be_explained() -> None:
    report = load_report(REPORT_10)
    text = render_explanation(report, report.findings[0].id)
    assert text.startswith(f"Finding {report.findings[0].id}")


def test_new_scan_emits_1_1_with_recorded_context(tmp_path: Path) -> None:
    document = _scan_json(tmp_path)
    assert document["schema"] == "nhi-blast-report/1.1"
    context = document["context"]
    assert isinstance(context, dict)
    assert len(context["config_digest"]) == 64
    assert context["selectors"] == [ACTION]
    assert context["limits"]["max_closure_depth"] == 3
    jsonschema.validate(document, json.loads(SCHEMA_11.read_text(encoding="utf-8")))


def test_max_depth_override_is_recorded_as_the_effective_limit() -> None:
    outcome = run_scan(ScanOptions(root=FX07, selectors=(ACTION,), max_depth=1))
    assert outcome.report.context is not None
    assert outcome.report.context.limits["max_closure_depth"] == 1


def test_context_is_identical_across_runs() -> None:
    first = run_scan(ScanOptions(root=FX07, selectors=(ACTION,))).report.context
    second = run_scan(ScanOptions(root=FX07, selectors=(ACTION,))).report.context
    assert first == second


@pytest.mark.parametrize("schema", ["nhi-blast-report/2.0", "other/0.0", ""])
def test_unreadable_schema_is_rejected(tmp_path: Path, schema: str) -> None:
    document = json.loads(REPORT_10.read_text(encoding="utf-8"))
    document["schema"] = schema
    target = tmp_path / "report.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ReportLoadError, match="unsupported report schema"):
        load_report(target)


def test_unknown_top_level_field_is_rejected(tmp_path: Path) -> None:
    document = json.loads(REPORT_10.read_text(encoding="utf-8"))
    document["surprise"] = 1
    target = tmp_path / "report.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ReportLoadError, match="not valid nhi-blast JSON"):
        load_report(target)


def test_config_digest_ignores_file_path_and_list_order() -> None:
    first = Config(path="a.toml", ignore_rules=("NHB-A", "NHB-B"), aws_region="us-east-1")
    second = Config(path="b.toml", ignore_rules=("NHB-B", "NHB-A"), aws_region="us-east-1")
    assert first.digest() == second.digest()


@pytest.mark.parametrize(
    "changed",
    [
        {"aws_region": "eu-west-1"},
        {"default_branch": "release"},
        {"ignore_rules": ("NHB-A",)},
        {"role_bindings": {"AWS_ROLE_ARN": "arn:aws:iam::111122223333:role/x"}},
        {"limits_overrides": {"max_closure_depth": 1}},
    ],
)
def test_config_digest_changes_when_a_setting_changes(changed: dict[str, object]) -> None:
    assert (
        Config(aws_region="us-east-1").digest()
        != Config(**{"aws_region": "us-east-1", **changed}).digest()
    )  # type: ignore[arg-type]


def test_rank_report_keeps_its_own_schema_label() -> None:
    assert RankReport.model_fields["schema_id"].default == "nhi-blast-report/1.0/rank"
