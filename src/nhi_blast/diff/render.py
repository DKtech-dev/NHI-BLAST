"""Renderers for a diff payload: canonical JSON, console text and a registry for more.

Wording rule: a "resolved" finding is "no longer observed under comparable analysis"; the
diff never claims a problem is fixed, safe or proven absent.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from nhi_blast.core.models import Severity, severity_rank
from nhi_blast.report._text import safe_text
from nhi_blast.report.diff_html import render_diff_html
from nhi_blast.report.redaction import redact_payload

Payload = Mapping[str, Any]


def to_json_text(payload: Payload) -> str:
    """Deterministic JSON: sorted keys, no timestamps, secrets redacted, trailing newline."""
    cleaned = redact_payload(dict(payload))
    return json.dumps(cleaned, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def _t(value: object, limit: int = 160) -> str:
    return safe_text(value, limit)


def _md_cell(value: object, limit: int = 160) -> str:
    return _t(value, limit).replace("|", "\\|")


def _is_severity_escalation(record: Mapping[str, Any]) -> bool:
    if record.get("class") != "changed":
        return False
    base_raw = record.get("base_severity")
    head_raw = record.get("head_severity") or record.get("severity")
    if not isinstance(base_raw, str) or not isinstance(head_raw, str):
        return False
    return severity_rank(Severity(head_raw)) < severity_rank(Severity(base_raw))


_CLASS_TITLES = {
    "new": "New findings (not present in BASE)",
    "changed": "Changed findings (same logical key, different content)",
    "not_observed": "Not observed in HEAD (comparison does not support calling these resolved)",
    "resolved": "No longer observed under comparable analysis",
    "unchanged": "Unchanged findings",
}


def _finding_line(record: Mapping[str, Any]) -> str:
    parts = [
        f"  [{_t(record['severity'])}] {_t(record['rule'])}",
        f"scenario={_t(record['scenario'] or '-')}",
        f"lk={_t(record['lk'])[:12]}",
    ]
    if record["class"] in {"not_observed"} and record["reasons"]:
        parts.append("reasons=" + ",".join(_t(item) for item in record["reasons"]))
    if record["changed_fields"]:
        parts.append("changed=" + ",".join(_t(item) for item in record["changed_fields"]))
    if record["possible_rename_of"]:
        parts.append(
            "possible_rename_of=" + ",".join(_t(i)[:12] for i in record["possible_rename_of"])
        )
    if record["ambiguous_match"]:
        parts.append("ambiguous_match")
    if record.get("suppressed_by_baseline"):
        parts.append("baselined")
    return " ".join(parts) + f"\n    {_t(record['title'])}"


def _drift_lines(payload: Payload) -> list[str]:
    lines: list[str] = []
    for item in payload["comparability"]["incomparable"]:
        lines.append(f"  INCOMPARABLE: {_t(item['code'])}")
    for item in payload["comparability"]["context_drift"]:
        base = _t(item.get("base"), 20)
        head = _t(item.get("head"), 20)
        lines.append(f"  drift {_t(item['code'])} {_t(item['field'])}: {base} -> {head}")
    return lines


def _scenario_lines(payload: Payload) -> list[str]:
    lines: list[str] = []
    scenarios = payload["scenarios"]
    for name in scenarios["only_in_base"]:
        lines.append(f"  scenario {_t(name)}: only in BASE")
    for name in scenarios["only_in_head"]:
        lines.append(f"  scenario {_t(name)}: only in HEAD")
    for delta in scenarios["compared"]:
        parts: list[str] = []
        for key in ("R", "E", "Z"):
            added = len(delta[key]["added"])
            removed = len(delta[key]["removed"])
            if added or removed:
                parts.append(f"{key} +{added}/-{removed}")
        ttl = len(delta["E"]["ttl_changed"])
        window = len(delta["Z"]["changed"])
        rotation = (
            len(delta["rotation_dependencies"]["added"])
            + len(delta["rotation_dependencies"]["removed"])
            + len(delta["rotation_dependencies"]["changed"])
        )
        if ttl:
            parts.append(f"E ttl changed {ttl}")
        if window:
            parts.append(f"Z details changed {window}")
        if rotation:
            parts.append(f"rotation dependencies changed {rotation}")
        if parts:
            lines.append(f"  scenario {_t(delta['selector'])}: " + ", ".join(parts))
        for credential in delta["Z"]["added"]:
            lines.append(f"    Z gained {_t(credential, 200)}")
    return lines


def render_console(payload: Payload) -> str:
    counts = payload["summary"]["counts"]
    lines = [
        "NHI-Blast diff (" + _t(payload["schema"]) + ")",
        "Comparability: " + _t(payload["comparability"]["status"]),
    ]
    lines.extend(_drift_lines(payload))
    if payload["comparability"]["status"] == "incomparable":
        lines.append("The reports cannot be compared; no finding classification was made.")
        return "\n".join(lines) + "\n"
    lines.append("Findings: " + ", ".join(f"{name}={counts[name]}" for name in _CLASS_TITLES))
    for klass, title in _CLASS_TITLES.items():
        records = [r for r in payload["findings"] if r["class"] == klass]
        if not records or klass == "unchanged":
            continue
        lines.append(title + ":")
        lines.extend(_finding_line(record) for record in records)
    scenario_lines = _scenario_lines(payload)
    if scenario_lines:
        lines.append("Scenario changes:")
        lines.extend(scenario_lines)
    for change in payload["completeness"]:
        lines.append(
            f"  completeness {_t(change['family'])}: {_t(change['base'])} -> {_t(change['head'])}"
            f" ({_t(change['direction'])})"
        )
    for item in payload["diagnostics"]["added"]:
        lines.append(f"  diagnostic added: {_t(item['code'])} {_t(item['file'] or '')}".rstrip())
    for item in payload["diagnostics"]["baseline"]:
        lines.append(f"  baseline diagnostic: {_t(item['code'])} {_t(item['lk'])[:12]}")
    gate = payload.get("gate")
    if gate is not None:
        level = _t(gate["fail_on"] or "never").lower()
        lines.append(
            f"Gate: fail_on={level} blocking={len(gate['blocking'])} "
            f"baselined={len(gate['suppressed'])} exit={gate['exit_code']}"
        )
    return "\n".join(lines) + "\n"


def _pr_z_additions(payload: Payload) -> list[tuple[str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str]] = []
    for delta in payload.get("scenarios", {}).get("compared", ()):
        z_section = delta.get("Z", {})
        added = z_section.get("added", ())
        if not added:
            continue
        details_by_cred = {
            item["credential"]: item
            for item in z_section.get("added_details", ())
            if isinstance(item, Mapping) and "credential" in item
        }
        selector = _md_cell(delta.get("selector", "-"), 120)
        for cred in added:
            detail = details_by_cred.get(cred, {})
            lifetime = _md_cell(detail.get("lifetime", "-"), 40)
            window = _md_cell(detail.get("survival_window", "-"), 60)
            crit_raw = detail.get("criticality")
            crit = "-" if crit_raw is None else _md_cell(crit_raw, 20)
            rows.append((selector, _md_cell(cred, 160), lifetime, window, crit))
    return rows


def render_pr_comment(payload: Payload) -> str:
    """Compact Markdown summary suitable for GitHub Pull Request comments."""
    counts = payload["summary"]["counts"]
    comparability = payload["comparability"]
    status = _t(comparability["status"])
    lines = [
        "## NHI-Blast Diff Summary",
        "",
        f"- **Comparability:** `{status}`",
    ]
    incomparable = comparability.get("incomparable", ())
    if status == "incomparable":
        for item in incomparable:
            lines.append(f"- **Incomparable cause:** `{_t(item.get('code', 'unknown'))}`")
        lines.append("")
        lines.append("The reports cannot be compared; no finding classification was made.")
        gate = payload.get("gate")
        if gate is not None:
            level = _t(gate["fail_on"] or "never").lower()
            lines.append("")
            lines.append(
                f"**Gate:** `fail_on={level}`, blocking=`{len(gate['blocking'])}`, "
                f"baselined=`{len(gate['suppressed'])}`, exit=`{gate['exit_code']}`"
            )
        return "\n".join(lines).rstrip() + "\n"

    lines.append(
        f"- **New:** {counts['new']} | **Changed:** {counts['changed']} | "
        f"**No longer observed:** {counts['resolved']} | "
        f"**Not observed:** {counts['not_observed']}"
    )
    lines.append("")

    context_drift = comparability.get("context_drift", ())
    if context_drift:
        lines.append("### Comparability drift")
        lines.append("")
        for item in context_drift:
            code = _t(item.get("code", "drift"))
            field = _t(item.get("field", "-"))
            base = _t(item.get("base"), 24)
            head = _t(item.get("head"), 24)
            lines.append(f"- `{code}` (`{field}`): `{base}` -> `{head}`")
        lines.append("")

    degraded = [
        item for item in payload.get("completeness", ()) if item.get("direction") == "degraded"
    ]
    if degraded:
        lines.append("### Completeness degradations")
        lines.append("")
        for item in degraded:
            lines.append(
                f"- `{_t(item.get('family', '-'))}`: "
                f"`{_t(item.get('base'))}` -> `{_t(item.get('head'))}` (`degraded`)"
            )
        lines.append("")

    z_rows = _pr_z_additions(payload)
    if z_rows:
        lines.extend(
            [
                "### Blast Radius Delta (`Z` Persistent Additions)",
                "",
                "| Scenario | Credential (`Z`) | Lifetime | Survival Window | Criticality |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for selector, cred, lifetime, window, crit in z_rows:
            lines.append(f"| `{selector}` | `{cred}` | `{lifetime}` | `{window}` | `{crit}` |")
        lines.append("")

    escalations = [r for r in payload["findings"] if _is_severity_escalation(r)]
    if escalations:
        lines.extend(
            [
                "### Severity Escalations",
                "",
                "| Change | Rule | Scenario | Title |",
                "| --- | --- | --- | --- |",
            ]
        )
        for rec in escalations:
            base_sev = _md_cell(rec.get("base_severity", "-"), 20)
            head_sev = _md_cell(rec.get("head_severity") or rec.get("severity", "-"), 20)
            lines.append(
                f"| `{base_sev} -> {head_sev}` | `{_md_cell(rec['rule'])}` | "
                f"`{_md_cell(rec['scenario'] or '-')}` | {_md_cell(rec['title'], 140)} |"
            )
        lines.append("")

    new_recs = [r for r in payload["findings"] if r["class"] == "new"]
    if new_recs:
        lines.extend(
            [
                "### New findings",
                "",
                "| Severity | Rule | Scenario | Status | Title |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for rec in new_recs:
            rec_status = "baselined (suppressed)" if rec.get("suppressed_by_baseline") else "active"
            lines.append(
                f"| `{_md_cell(rec['severity'])}` | `{_md_cell(rec['rule'])}` | "
                f"`{_md_cell(rec['scenario'] or '-')}` | `{rec_status}` | "
                f"{_md_cell(rec['title'], 140)} |"
            )
        lines.append("")

    gate = payload.get("gate")
    if gate is not None:
        level = _t(gate["fail_on"] or "never").lower()
        lines.append(
            f"**Gate:** `fail_on={level}`, blocking=`{len(gate['blocking'])}`, "
            f"baselined=`{len(gate['suppressed'])}`, exit=`{gate['exit_code']}`"
        )
    return "\n".join(lines).rstrip() + "\n"


@dataclass(frozen=True, slots=True)
class Renderer:
    name: str
    extension: str
    render: Callable[[Payload], str]


RENDERERS: dict[str, Renderer] = {
    "console": Renderer("console", "txt", render_console),
    "json": Renderer("json", "json", to_json_text),
    "html": Renderer("html", "html", render_diff_html),
    "pr-comment": Renderer("pr-comment", "md", render_pr_comment),
}


def register_renderer(renderer: Renderer) -> None:
    """Hook for further formats (for example html); the diff command accepts any registered name."""
    RENDERERS[renderer.name] = renderer
