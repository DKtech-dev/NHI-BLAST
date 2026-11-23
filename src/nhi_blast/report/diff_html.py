"""Zero-Motion offline HTML renderer for `nhi-blast diff`."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape
from typing import Any

from nhi_blast.report._text import safe_text
from nhi_blast.report.html import render_document
from nhi_blast.report.redaction import redact_payload

_CLASS_ORDER = (
    ("new", "New findings"),
    ("changed", "Changed findings"),
    ("not_observed", "Not observed in HEAD"),
    ("resolved", "No longer observed under comparable analysis"),
    ("unchanged", "Unchanged findings"),
)


def _esc(value: object, limit: int = 240) -> str:
    return escape(safe_text(value, limit), quote=True)


def _badge(label: str, tone: str = "neutral") -> str:
    return f'<span class="pill pill-{escape(tone, quote=True)}">{_esc(label, 60)}</span>'


def _sev_tone(severity: str) -> str:
    if severity == "CRITICAL":
        return "crit"
    if severity == "HIGH":
        return "high"
    if severity == "MEDIUM":
        return "warn"
    return "neutral"


def render_diff_html(payload: Mapping[str, Any]) -> str:
    """Render a deterministic, self-contained, zero-Motion diff HTML report."""
    data = redact_payload(dict(payload))
    comp = data["comparability"]
    status = str(comp["status"])
    counts = data["summary"]["counts"]

    sections: list[str] = []
    # Header summary cards
    cards = [
        ("Comparability", status),
        ("New", str(counts.get("new", 0))),
        ("Changed", str(counts.get("changed", 0))),
        ("Not observed", str(counts.get("not_observed", 0))),
        ("No longer observed", str(counts.get("resolved", 0))),
        ("Unchanged", str(counts.get("unchanged", 0))),
    ]
    card_html = "".join(
        f'<div class="kpi"><span class="kpi-label">{_esc(k, 40)}</span>'
        f'<strong class="kpi-val">{_esc(v, 40)}</strong></div>'
        for k, v in cards
    )
    sections.append(
        f'<section class="card"><h2>Summary</h2><div class="kpi-grid">{card_html}</div></section>'
    )

    # Comparability & drift
    drift_rows: list[str] = []
    for item in comp.get("incomparable", ()):
        drift_rows.append(f"<li>{_badge('INCOMPARABLE', 'crit')} {_esc(item.get('code'))}</li>")
    for item in comp.get("context_drift", ()):
        drift_rows.append(
            f"<li>{_badge('DRIFT', 'warn')} {_esc(item.get('code'))} "
            f"<code>{_esc(item.get('field'))}</code>: "
            f"{_esc(item.get('base'), 80)} &rarr; {_esc(item.get('head'), 80)}</li>"
        )
    if drift_rows:
        sections.append(
            '<section class="card"><h2>Comparability and drift</h2>'
            f'<ul class="plain-list">{"".join(drift_rows)}</ul></section>'
        )

    # Gate summary
    gate = data.get("gate")
    if gate is not None:
        blocking_count = len(gate.get("blocking", ()))
        exit_code = gate.get("exit_code")
        is_incomparable = (
            exit_code == 3 or status == "incomparable" or comp.get("state") == "incomparable"
        )
        if is_incomparable:
            gate_tone = "warn"
            gate_label = "INCOMPARABLE"
        elif blocking_count:
            gate_tone = "crit"
            gate_label = "BLOCKING"
        elif exit_code not in (None, 0):
            gate_tone = "crit"
            gate_label = "FAIL"
        else:
            gate_tone = "ok"
            gate_label = "PASS"
        sections.append(
            '<section class="card"><h2>Policy gate</h2>'
            f"<p>{_badge(gate_label, gate_tone)} "
            f"fail_on=<code>{_esc(gate.get('fail_on') or 'never')}</code>, "
            f"blocking=<strong>{blocking_count}</strong>, "
            f"baselined=<strong>{len(gate.get('suppressed', ()))}</strong>, "
            f"exit=<code>{_esc(exit_code)}</code></p></section>"
        )

    # Findings tables by class
    if status != "incomparable":
        findings = list(data.get("findings", ()))
        for klass, heading in _CLASS_ORDER:
            subset = [r for r in findings if r.get("class") == klass]
            if not subset or klass == "unchanged":
                continue
            rows_html = []
            for rec in subset:
                sev = str(rec.get("severity", ""))
                tone = _sev_tone(sev)
                notes: list[str] = []
                if rec.get("changed_fields"):
                    notes.append("changed: " + ", ".join(str(x) for x in rec["changed_fields"]))
                if rec.get("reasons"):
                    notes.append("reasons: " + ", ".join(str(x) for x in rec["reasons"]))
                if rec.get("suppressed_by_baseline"):
                    notes.append("baselined")
                lk_full = str(rec.get("lk", ""))
                rows_html.append(
                    "<tr>"
                    f"<td>{_badge(sev, tone)}</td>"
                    f"<td><code>{_esc(rec.get('rule'), 40)}</code></td>"
                    f"<td>{_esc(rec.get('scenario') or '-', 80)}</td>"
                    f"<td>{_esc(rec.get('title'), 220)}</td>"
                    f"<td><code>{_esc(lk_full[:12], 16)}</code></td>"
                    f"<td>{_esc('; '.join(notes), 160)}</td>"
                    "</tr>"
                )
            sections.append(
                f'<section class="card"><h2>{_esc(heading, 80)} ({len(subset)})</h2>'
                '<div class="table-wrap"><table><thead><tr>'
                '<th scope="col">Severity</th><th scope="col">Rule</th>'
                '<th scope="col">Scenario</th><th scope="col">Title</th>'
                '<th scope="col">Key</th><th scope="col">Details</th>'
                f"</tr></thead><tbody>{''.join(rows_html)}</tbody></table></div></section>"
            )

        # Scenario deltas
        scen = data.get("scenarios", {})
        compared = scen.get("compared", ())
        if compared or scen.get("only_in_base") or scen.get("only_in_head"):
            s_rows: list[str] = []
            for name in scen.get("only_in_base", ()):
                s_rows.append(f"<tr><td>{_esc(name)}</td><td colspan='4'>Only in BASE</td></tr>")
            for name in scen.get("only_in_head", ()):
                s_rows.append(f"<tr><td>{_esc(name)}</td><td colspan='4'>Only in HEAD</td></tr>")
            for delta in compared:
                s_rows.append(
                    "<tr>"
                    f"<td><code>{_esc(delta.get('selector'))}</code></td>"
                    f"<td class='num'>+{len(delta['R']['added'])} / "
                    f"-{len(delta['R']['removed'])}</td>"
                    f"<td class='num'>+{len(delta['E']['added'])} / -{len(delta['E']['removed'])} "
                    f"(ttl {len(delta['E']['ttl_changed'])})</td>"
                    f"<td class='num'>+{len(delta['Z']['added'])} / -{len(delta['Z']['removed'])} "
                    f"(chg {len(delta['Z']['changed'])})</td>"
                    f"<td class='num'>+{len(delta['rotation_dependencies']['added'])} / "
                    f"-{len(delta['rotation_dependencies']['removed'])}</td>"
                    "</tr>"
                )
            sections.append(
                '<section class="card"><h2>Scenario deltas</h2>'
                '<div class="table-wrap"><table><thead><tr>'
                '<th scope="col">Scenario</th><th scope="col" class="num">R</th>'
                '<th scope="col" class="num">E</th>'
                '<th scope="col" class="num">Z</th>'
                '<th scope="col" class="num">Rotation deps</th>'
                f"</tr></thead><tbody>{''.join(s_rows)}</tbody></table></div></section>"
            )

    toolbar_html = (
        '<div class="doc-toolbar" role="region" aria-label="Report controls">'
        '<span class="doc-brand">NHI-Blast <span class="doc-brand-chip">Offline diff</span></span>'
        '<div class="doc-toolbar-actions">'
        '<div id="companion-theme-host"></div>'
        '<button type="button" class="copy-btn" data-action="print">Print / PDF</button>'
        "</div></div>"
    )
    body_html = (
        toolbar_html + '<header class="doc-head">'
        f"<h1>Report comparison ({_esc(data.get('schema'), 40)})</h1>"
        "<p class='lead'>A finding marked no longer observed reflects comparable inputs only; "
        "verify remediation in the target environment.</p>"
        "</header>" + "".join(sections)
    )
    return render_document(title="NHI-Blast Diff Report", body_html=body_html)


__all__ = ["render_diff_html"]
