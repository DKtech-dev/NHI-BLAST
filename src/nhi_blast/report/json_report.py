"""Canonical JSON report serialization (spec 13.2)."""

from __future__ import annotations

import json
from pathlib import Path

from nhi_blast.core.models import Report
from nhi_blast.report.model_json import report_dict


def report_json(report: Report) -> str:
    data = report_dict(report)
    return (
        json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def write_json(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_json(report), encoding="utf-8", newline="\n")
