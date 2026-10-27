"""Console report stages, evidence suffix and terminal safety (M5, spec 13.5)."""

from __future__ import annotations

from nhi_blast.report.console import render_console
from tests.report_support import HOSTILE, SENTINEL, make_report


def test_console_has_required_stages_and_scenario_counts() -> None:
    text = render_console(make_report(), color=False)

    for heading in ("Parse", "Trust audit", "Scenario", "Survival", "Rotation plan", "Findings"):
        assert heading in text
    assert "R (ends with entrypoint): 1" in text
    assert "E (expires on its own): 1" in text
    assert "Z (survives): 1" in text
    assert "action:example/action@v1" in text
    assert "Rotate the database password." in text
    assert text.endswith("\n")


def test_console_disables_colour_by_default_and_colours_only_when_requested() -> None:
    plain = render_console(make_report(), color=False)
    coloured = render_console(make_report(), color=True)

    assert "\x1b[" not in plain
    assert "\x1b[" in coloured
    assert "\x1b[31mred" not in coloured


def test_console_ends_fact_lines_with_evidence_class_and_location() -> None:
    text = render_console(make_report(), color=False)
    lines = [line.strip() for line in text.splitlines()]

    runtime = next(line for line in lines if "STS session for deploy-prod" in line)
    sink = next(line for line in lines if "prod/db-master database password" in line)
    assert runtime.endswith("[declared tfstate.json:31]")
    assert sink.endswith("[declared .github/workflows/release.yml:14]")


def test_console_neutralises_control_sequences_and_never_emits_secret_values() -> None:
    report = make_report(hostile=True).model_copy(
        update={"scope_and_limits": (HOSTILE, "max graph nodes 500000")}
    )

    text = render_console(report, color=False)

    assert "\x1b" not in text
    assert "\x00" not in text
    assert "\r" not in text
    assert SENTINEL not in text
    assert "red" in text
    assert len(text.splitlines()) == len(
        render_console(make_report(hostile=True), color=False).splitlines()
    )


def test_console_is_deterministic() -> None:
    report = make_report()

    assert render_console(report, color=False) == render_console(report, color=False)
