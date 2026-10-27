"""Canonical JSON-compatible report data and its generated schema (spec 13.2)."""

from __future__ import annotations

import json
from typing import Any

from nhi_blast import SCHEMA_VERSION
from nhi_blast.core.models import Report

_SCHEMA_URI = "urn:nhi-blast:report:1.0"


def report_dict(report: Report) -> dict[str, Any]:
    """Return the alias-based JSON shape with stable key ordering and no nulls."""
    payload = report.model_dump(mode="json", by_alias=True, exclude_none=True)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    decoded: dict[str, Any] = json.loads(canonical)
    return decoded


def report_schema() -> dict[str, Any]:
    """Return the checked-in report schema generated from the Pydantic model."""
    schema = Report.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = _SCHEMA_URI
    schema["title"] = "NHI-Blast report"
    schema["description"] = f"Schema for {SCHEMA_VERSION}."
    return schema
