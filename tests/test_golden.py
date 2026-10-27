"""Reviewed golden output for the SPEC 14.4 fx07 incident."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nhi_blast.core.models import Report
from nhi_blast.pipeline import ScanOptions, run_scan

FIXTURE = Path(__file__).parent / "fixtures" / "fx07-incident"
GOLDEN = Path(__file__).parent / "golden"
ACTION = "action:tj-actions/changed-files@v45"


def _summary(report: Report) -> str:
    scenario = report.scenarios[0]
    labels = {node.id: node.label for node in report.graph.nodes}
    payload = {
        "schema": report.schema_id,
        "selector": scenario.selector,
        "scope_and_limits": list(report.scope_and_limits),
        "diagnostics": [item.code for item in report.diagnostics],
        "finding_ids": [item.id for item in report.findings],
        "partition": {
            "R": [labels[item] for item in scenario.partition.R],
            "E": [
                {"label": labels[item.credential], "ttl_seconds": item.ttl_seconds}
                for item in scenario.partition.E
            ],
            "Z": [
                {
                    "label": labels[item.credential],
                    "depth": item.depth,
                    "survival_window": item.survival_window,
                    "criticality": item.criticality,
                }
                for item in scenario.partition.Z
            ],
        },
        "rotation": [
            [credential.label for credential in step.credentials]
            for step in scenario.rotation_plan.rotation
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _read_golden(name: str) -> str:
    path = GOLDEN / name
    assert path.is_file(), f"reviewed golden is missing: {path}"
    return path.read_text(encoding="utf-8")


@pytest.mark.golden
def test_fx07_console_exact_bytes() -> None:
    outcome = run_scan(ScanOptions(root=FIXTURE, selectors=(ACTION,)))
    assert outcome.console_text == _read_golden("fx07-console.txt")


@pytest.mark.golden
def test_fx07_compact_summary() -> None:
    outcome = run_scan(ScanOptions(root=FIXTURE, selectors=(ACTION,)))
    assert _summary(outcome.report) == _read_golden("fx07-summary.json")
