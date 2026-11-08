"""Date arithmetic and bounded plan JSON failures remain controlled."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from nhi_blast.whatif.engine import WhatIfAbort
from nhi_blast.whatif.plan import MAX_INTERVENTIONS, PlanError, parse_plan_text
from nhi_blast.whatif.run import execute
from nhi_blast.whatif.sessions import (
    TimestampError,
    assess_session,
    format_timestamp,
    parse_timestamp,
    resolve_cutoff,
)
from tests.test_whatif_support import ROLE, fx16_report, revoke, save, write_plan


@pytest.mark.parametrize("value", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"])
def test_utc_conversion_overflow_is_a_timestamp_error(value: str) -> None:
    with pytest.raises(TimestampError, match=r"range|overflow"):
        parse_timestamp(value)


@pytest.mark.parametrize(
    "value", [datetime.min.replace(tzinfo=UTC), datetime.max.replace(tzinfo=UTC)]
)
def test_utc_year_boundaries_still_format(value: datetime) -> None:
    assert parse_timestamp(format_timestamp(value)) == value


def test_format_utc_conversion_overflow_is_controlled() -> None:
    value = datetime.max.replace(tzinfo=timezone(-timedelta(hours=1)))
    with pytest.raises(TimestampError, match=r"range|overflow"):
        format_timestamp(value)


def test_assumed_propagation_window_overflow_is_controlled() -> None:
    with pytest.raises(TimestampError, match=r"range|overflow"):
        resolve_cutoff(datetime.max.replace(tzinfo=UTC), None)


def test_explicit_cutoff_preserves_maximal_timestamp() -> None:
    value = datetime.max.replace(tzinfo=UTC)
    assert resolve_cutoff(value, value) == (value, "given")


@pytest.mark.parametrize("ttl", [1, 10**100])
def test_session_latest_expiry_overflow_is_controlled(ttl: int) -> None:
    value = datetime.max.replace(tzinfo=UTC)
    with pytest.raises(TimestampError, match=r"range|overflow"):
        assess_session(
            issued_no_later_than=value,
            ttl_seconds=ttl,
            revoked_at=None,
            cutoff=None,
            assessed_at=value,
        )


def test_minimal_timestamp_retains_expiry_semantics() -> None:
    issued = datetime.min.replace(tzinfo=UTC)
    result = assess_session(
        issued_no_later_than=issued,
        ttl_seconds=30,
        revoked_at=None,
        cutoff=None,
        assessed_at=issued + timedelta(seconds=30),
    )
    assert result.validity == "expired"
    assert result.display_state == "expired"


@pytest.mark.parametrize(
    "fields",
    [
        {"revoked_at": "9999-12-31T23:59:59Z"},
        {
            "issued_no_later_than": "9999-12-31T23:59:59Z",
            "assessed_at": "9999-12-31T23:59:59Z",
        },
    ],
)
def test_whatif_date_overflow_aborts_without_output(tmp_path: Path, fields: dict[str, str]) -> None:
    report = save(fx16_report(), tmp_path / "report.json")
    plan = write_plan(tmp_path / "plan.json", revoke(**fields))
    out = tmp_path / "out"
    with pytest.raises(WhatIfAbort, match=r"timestamp|range|overflow"):
        execute(report, plan, ("json", "md"), out)
    assert not out.exists()
    assert json.loads(plan.read_text(encoding="utf-8"))["interventions"][0]["role"] == ROLE


def test_plan_json_depth_budget_ignores_string_brackets() -> None:
    text = json.dumps(
        {"schema": "nhi-blast-interventions/1.0", "interventions": [{"type": "[" * 100}]}
    )
    assert len(parse_plan_text(text, suffix=".json", max_depth=3).entries) == 1


def test_plan_json_depth_budget_rejects_nested_unknown_entries() -> None:
    text = '{"schema":"nhi-blast-interventions/1.0","interventions":[' + "[" * 10
    text += "0" + "]" * 10 + "]}"
    with pytest.raises(PlanError, match=r"depth|nesting"):
        parse_plan_text(text, suffix=".json", max_depth=5)


def test_plan_json_node_budget_rejects_shallow_breadth() -> None:
    text = json.dumps({"schema": "nhi-blast-interventions/1.0", "interventions": [[0] * 20]})
    with pytest.raises(PlanError, match=r"node|budget"):
        parse_plan_text(text, suffix=".json", max_nodes=10)


def test_plan_json_accepts_current_maximum_interventions() -> None:
    text = json.dumps(
        {
            "schema": "nhi-blast-interventions/1.0",
            "interventions": [{"type": "unknown"}] * MAX_INTERVENTIONS,
        }
    )
    assert len(parse_plan_text(text, suffix=".json").entries) == MAX_INTERVENTIONS


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_plan_nonfinite_json_is_controlled(value: str) -> None:
    text = '{"schema":"nhi-blast-interventions/1.0","interventions":[' + value + "]}"
    with pytest.raises(PlanError):
        parse_plan_text(text, suffix=".json")
