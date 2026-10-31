"""Load a saved nhi-blast JSON report, accepting every readable schema version."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from nhi_blast import READABLE_SCHEMAS
from nhi_blast.core.models import Report
from nhi_blast.report._text import safe_text

_MAX_REPORT_BYTES = 512 * 1024 * 1024


class ReportLoadError(ValueError):
    """The saved report cannot be read or is not a supported nhi-blast report."""


def load_report(path: Path) -> Report:
    candidate = path.expanduser()
    try:
        size = candidate.stat().st_size
    except OSError as exc:
        msg = f"cannot read report {path}: {exc.strerror or exc}"
        raise ReportLoadError(msg) from None
    if not candidate.is_file():
        msg = f"report path is not a file: {path}"
        raise ReportLoadError(msg)
    if size > _MAX_REPORT_BYTES:
        msg = f"report is larger than the {_MAX_REPORT_BYTES}-byte limit: {path}"
        raise ReportLoadError(msg)
    try:
        text = candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        msg = f"cannot read report {path}: {exc}"
        raise ReportLoadError(msg) from None
    try:
        report = Report.model_validate_json(text)
    except ValidationError as exc:
        location = "document"
        if exc.errors():
            location = ".".join(str(part) for part in exc.errors()[0]["loc"]) or location
        msg = f"report is not valid nhi-blast JSON at {location}"
        raise ReportLoadError(msg) from None
    if report.schema_id not in READABLE_SCHEMAS:
        msg = f"unsupported report schema: {safe_text(report.schema_id, 80)}"
        raise ReportLoadError(msg)
    return report


__all__ = ["ReportLoadError", "load_report"]
