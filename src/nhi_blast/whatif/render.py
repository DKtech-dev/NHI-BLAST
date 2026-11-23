"""Serialisation of the what-if document: canonical JSON and a short console summary."""

from __future__ import annotations

from typing import Any

from nhi_blast.core.canonical import canonical_json
from nhi_blast.report._text import safe_text
from nhi_blast.whatif import HEADER


def whatif_json(payload: dict[str, Any]) -> str:
    return canonical_json(payload) + "\n"


def _ids(items: list[Any]) -> int:
    return len(items)


def console_summary(payload: dict[str, Any]) -> str:
    lines = [HEADER, ""]
    steps = payload["steps"]
    applied = sum(1 for step in steps if step["status"] == "applied")
    lines.append(
        f"Plan: {len(steps)} intervention(s), {applied} applied, "
        f"{len(payload['rejected'])} rejected."
    )
    for item in payload["per_scenario"]:
        before, after, future = item["before"], item["after"], item["future_reach"]
        lines.append(f"Scenario {safe_text(item['selector'], 200)}")
        lines.append(f"  before: R={_ids(before['R'])} E={_ids(before['E'])} Z={_ids(before['Z'])}")
        lines.append(
            f"  carried: R={_ids(after['R'])} E={_ids(after['E'])} Z={_ids(after['Z'])}"
            f" (issued before containment: {_ids(after['issued_before_containment'])},"
            f" re-exposure risk: {_ids(after['re_exposure_risk'])})"
        )
        lines.append(
            f"  new runs could still reach: R={_ids(future['R'])} E={_ids(future['E'])}"
            f" Z={_ids(future['Z'])}"
        )
        for row in after["revoked_access"]:
            lines.append(
                f"  session {safe_text(row['credential'], 120)}: "
                f"{safe_text(row['display_state'], 80)} "
                f"(validity={safe_text(row['validity'], 80)}, "
                f"access={safe_text(row['access'], 80)})"
            )
    for item in payload["rejected"]:
        lines.append(
            f"Rejected step {safe_text(item['index'], 32)} "
            f"({safe_text(item['type'], 80)}): {safe_text(item['reason'], 200)}"
        )
    for item in payload["warnings"]:
        lines.append(f"Warning {safe_text(item['code'], 80)}: {safe_text(item['detail'], 200)}")
    return "\n".join(lines) + "\n"


__all__ = ["console_summary", "whatif_json"]
