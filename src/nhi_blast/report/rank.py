"""Deterministic ranking output for mutable third-party actions (spec 12.7)."""

from __future__ import annotations

import json
from pathlib import Path

from nhi_blast.core.models import RankReport
from nhi_blast.report._text import safe_text
from nhi_blast.report.redaction import redact_payload


def rank_json(report: RankReport) -> str:
    data = redact_payload(report.model_dump(mode="json", by_alias=True, exclude_none=True))
    return (
        json.dumps(data, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    )


def write_rank_json(report: RankReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rank_json(report), encoding="utf-8", newline="\n")


def _diagnostic_line(level: str, code: str, message: str, location: str) -> str:
    return f"  [{level}] {safe_text(code, 60)}: {safe_text(message, 500)}{location}"


def render_rank_console(report: RankReport) -> str:
    """Render a stable table; severity-free so it is safe in any terminal."""
    lines = [
        f"NHI-Blast {safe_text(report.tool.version, 40)}",
        f"Rank schema: {safe_text(report.schema_id, 80)}",
        f"Repository: {safe_text(report.inputs.repo_slug, 200)} "
        f"[declared {safe_text(report.inputs.repo_slug_source, 160)}]",
        f"Inputs digest: {safe_text(report.inputs.digest, 128)}",
        "",
        f"Mutable third-party actions: {len(report.rows)}",
    ]
    if report.rows:
        width = min(max(9, *(len(safe_text(row.action, 200)) for row in report.rows)), 60)
        lines.append(f"  {'ACTION':<{width}}  {'PIN':<9}  USE  OIDC  R  E  Z  CRIT")
        for row in report.rows:
            action = safe_text(row.action, 200)
            lines.append(
                f"  {action:<{width}}  {row.pin_kind.value:<9}  "
                f"{row.use_sites:>3}  {row.jobs_with_oidc:>4}  "
                f"{row.r_count:>1}  {row.e_count:>1}  {row.z_count:>1}  "
                f"{row.highest_criticality:>4}"
            )
    else:
        lines.append("  None found.")
    diagnostics = tuple(sorted(report.diagnostics, key=lambda item: item.sort_key()))
    lines.extend(("", f"Diagnostics: {len(diagnostics)}"))
    for diagnostic in diagnostics:
        location = ""
        if diagnostic.file:
            location = f" {safe_text(diagnostic.file, 260)}"
            if diagnostic.line is not None:
                location += f":{diagnostic.line}"
        lines.append(
            _diagnostic_line(diagnostic.level.value, diagnostic.code, diagnostic.message, location)
        )
    return "\n".join(lines).rstrip() + "\n"


__all__ = ["rank_json", "render_rank_console", "write_rank_json"]
