"""Canonical report JSON and generated schema (M5, spec 13.2)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from nhi_blast import SCHEMA_VERSION
from nhi_blast.report.json_report import report_json
from nhi_blast.report.model_json import report_dict, report_schema
from tests.report_support import make_report

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "docs" / "schema" / "report.schema.json"


def test_report_json_uses_aliases_sorted_keys_compact_form_and_trailing_newline() -> None:
    report = make_report()

    text = report_json(report)
    data = json.loads(text)

    assert text.endswith("\n")
    assert data["schema"] == SCHEMA_VERSION
    assert "schema_id" not in data
    assert "generated_at" not in data
    assert text == (
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    )
    assert data["scenarios"][0]["partition"]["E"][0]["ttl_seconds"] == 3600


def test_report_dict_round_trips_through_serialized_json() -> None:
    report = make_report()

    data = report_dict(report)

    assert report_dict(report) == data
    assert json.loads(report_json(report)) == data
    assert list(data) == sorted(data)


def test_multi_scenario_report_serializes_matrix_inputs() -> None:
    report = make_report()
    first = report.scenarios[0]
    second = first.model_copy(update={"selector": "repo-write"})
    report = report.model_copy(update={"scenarios": (first, second)})

    data = report_dict(report)

    assert [scenario["selector"] for scenario in data["scenarios"]] == [
        first.selector,
        "repo-write",
    ]
    for scenario in data["scenarios"]:
        assert scenario["partition"]["R"]
        assert scenario["partition"]["E"][0]["credential"]
        assert scenario["partition"]["Z"][0]["credential"]
        assert scenario["potential_nodes"]


def test_checked_in_schema_matches_generator_and_validates_report() -> None:
    generated = report_schema()
    on_disk = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert on_disk == generated
    jsonschema.Draft202012Validator.check_schema(generated)
    jsonschema.Draft202012Validator(generated).validate(report_dict(make_report()))


def test_schema_rejects_report_without_required_tool_metadata() -> None:
    generated = report_schema()
    data = report_dict(make_report())
    del data["tool"]["version"]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(generated).validate(data)
