"""Zero-Motion offline HTML renderer for `nhi-blast whatif`."""

from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape
from typing import Any

from nhi_blast.core.models import Report
from nhi_blast.report._text import safe_text
from nhi_blast.report.html import render_document
from nhi_blast.report.redaction import redact_payload

_APPLIED_STATUSES = frozenset({"applied", "no_effect"})


def _esc(value: object, limit: int = 240) -> str:
    return escape(safe_text(value, limit), quote=True)


def _step_status(step: Mapping[str, Any]) -> str:
    raw = step.get("status")
    if raw is None or not str(raw).strip():
        return "applied"
    return str(raw)


def _step_pill_class(status: str) -> str:
    if status == "rejected":
        return "pill-crit"
    if status == "no_effect":
        return "pill-warn"
    return "pill-ok"


def _step_target(step: Mapping[str, Any]) -> str:
    if step.get("target"):
        return str(step["target"])
    args = step.get("args")
    if isinstance(args, Mapping):
        for key in ("role", "node", "credential", "edge"):
            val = args.get(key)
            if val:
                return str(val)
    return "-"


def _revoke_policy_json(cutoff: object) -> str:
    cutoff_val = safe_text(cutoff, 64) if cutoff else "<YYYY-MM-DDTHH:MM:SSZ>"
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AWSRevokeOlderSessions",
                "Effect": "Deny",
                "Action": "*",
                "Resource": "*",
                "Condition": {
                    "DateLessThan": {
                        "aws:TokenIssueTime": cutoff_val,
                    }
                },
            }
        ],
    }
    return json.dumps(policy, indent=2)


def render_whatif_html(report: Report, payload: Mapping[str, Any]) -> str:
    """Render a deterministic, self-contained, zero-Motion what-if HTML report."""
    del report  # payload already carries redacted scenario projections
    data = redact_payload(dict(payload))
    scenarios = list(data.get("per_scenario", ()))
    all_steps = list(data.get("steps") or data.get("applied") or ())
    applied_steps = [step for step in all_steps if _step_status(step) in _APPLIED_STATUSES]
    rejected_steps = [step for step in all_steps if _step_status(step) == "rejected"]
    rejected = list(data.get("rejected", ()))
    rejected_entries = rejected or rejected_steps
    warnings = list(data.get("warnings", ()))

    sections: list[str] = []

    # Metadata summary
    cards = [
        ("Scenarios", str(len(scenarios))),
        ("Applied steps", str(len(applied_steps))),
        ("Rejected steps", str(len(rejected_entries))),
        ("Warnings", str(len(warnings))),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><span class="kpi-label">{_esc(k, 40)}</span>'
        f'<strong class="kpi-val">{_esc(v, 40)}</strong></div>'
        for k, v in cards
    )
    src_digest = _esc(data.get("source_report_digest"), 80)
    plan_digest = _esc(data.get("plan_digest"), 80)
    sections.append(
        '<section class="card"><h2>Model summary</h2>'
        f'<div class="kpi-grid">{kpi_html}</div>'
        '<div class="meta-row">'
        '<span class="meta-item">Source report digest: '
        f"<code>{src_digest}</code>"
        f'<button type="button" class="copy-btn" data-copy-text="{src_digest}" '
        'data-copy-label="Source digest">Copy</button></span>'
        '<span class="meta-item">Plan digest: '
        f"<code>{plan_digest}</code>"
        f'<button type="button" class="copy-btn" data-copy-text="{plan_digest}" '
        'data-copy-label="Plan digest">Copy</button></span>'
        "</div></section>"
    )

    # Applied interventions (never includes rejected steps)
    if applied_steps:
        step_rows = "".join(
            "<tr>"
            f"<td class='num'>{_esc(step.get('index'))}</td>"
            f"<td><code>{_esc(step.get('type'), 60)}</code></td>"
            f"<td><code>{_esc(_step_target(step), 140)}</code></td>"
            f"<td><span class='pill {_step_pill_class(_step_status(step))}'>"
            f"{_esc(_step_status(step), 40)}</span></td>"
            "</tr>"
            for step in applied_steps
        )
        sections.append(
            '<section class="card"><h2>Applied interventions</h2>'
            '<div class="table-wrap"><table><thead><tr>'
            '<th scope="col" class="num">Step</th><th scope="col">Action</th>'
            '<th scope="col">Target</th><th scope="col">Status</th>'
            f"</tr></thead><tbody>{step_rows}</tbody></table></div></section>"
        )

    # AWSRevokeOlderSessions IAM policy snippets for non-rejected session revocation steps
    revoke_steps = [
        step for step in applied_steps if str(step.get("type", "")) == "revoke_role_sessions"
    ]
    if revoke_steps:
        snippet_blocks: list[str] = []
        for idx, step in enumerate(revoke_steps):
            effects = step.get("effects") if isinstance(step.get("effects"), Mapping) else {}
            role_label = _step_target(step)
            cutoff = effects.get("cutoff") if isinstance(effects, Mapping) else None
            snippet_id = f"revoke-policy-{idx}"
            snippet_json = escape(_revoke_policy_json(cutoff), quote=False)
            snippet_blocks.append(
                '<div class="code-block">'
                '<div class="code-block-head">'
                f'<span class="code-block-title">AWSRevokeOlderSessions &middot; '
                f"{_esc(role_label, 140)}</span>"
                f'<button type="button" class="copy-btn" data-copy-target="{snippet_id}" '
                'data-copy-label="AWSRevokeOlderSessions JSON">Copy JSON</button>'
                "</div>"
                f'<pre id="{snippet_id}"><code>{snippet_json}</code></pre>'
                "</div>"
            )
        sections.append(
            '<section class="card"><h2>Session revocation policies (AWSRevokeOlderSessions)</h2>'
            "<p class='lead'>Inline IAM Deny policy templates for role session revocation. "
            "Confirm the cutoff timestamp and test on a non-production role before applying.</p>"
            f"{''.join(snippet_blocks)}</section>"
        )

    # Before / after per scenario
    if scenarios:
        s_rows: list[str] = []
        for scen in scenarios:
            before = scen["before"]
            after = scen["after"]
            future = scen["future_reach"]
            s_rows.append(
                "<tr>"
                f"<td><code>{_esc(scen.get('selector'), 100)}</code></td>"
                f"<td class='num'>R={len(before['R'])} / "
                f"E={len(before['E'])} / Z={len(before['Z'])}</td>"
                f"<td class='num'>R={len(after['R'])} / "
                f"E={len(after['E'])} / Z={len(after['Z'])}</td>"
                f"<td class='num'>R={len(future['R'])} / "
                f"E={len(future['E'])} / Z={len(future['Z'])}</td>"
                f"<td class='num'>{len(after.get('re_exposure_risk', ()))}</td>"
                f"<td class='num'>{len(scen.get('residual_paths', ()))}</td>"
                "</tr>"
            )
        sections.append(
            '<section class="card"><h2>Before vs. after containment</h2>'
            '<div class="table-wrap"><table><thead><tr>'
            '<th scope="col">Scenario</th><th scope="col" class="num">Before (R/E/Z)</th>'
            '<th scope="col" class="num">After (R/E/Z)</th>'
            '<th scope="col" class="num">Future reach</th>'
            '<th scope="col" class="num">Re-exposure risks</th>'
            '<th scope="col" class="num">Residual paths</th>'
            f"</tr></thead><tbody>{''.join(s_rows)}</tbody></table></div></section>"
        )

    # Warnings & rejected entries
    if warnings:
        w_items = "".join(
            f"<li><span class='pill pill-warn'>{_esc(w.get('code'), 60)}</span> "
            f"{_esc(w.get('detail'), 200)}</li>"
            for w in warnings
        )
        sections.append(
            '<section class="card"><h2>Warnings</h2>'
            f'<ul class="plain-list">{w_items}</ul></section>'
        )
    if rejected_entries:
        r_items = "".join(
            f"<li><span class='pill pill-crit'>rejected</span> "
            f"Step {_esc(r.get('index'))} <code>{_esc(r.get('type'), 60)}</code>: "
            f"{_esc(r.get('reason'), 160)}</li>"
            for r in rejected_entries
        )
        sections.append(
            '<section class="card"><h2>Rejected plan entries</h2>'
            f'<ul class="plain-list">{r_items}</ul></section>'
        )

    toolbar_html = (
        '<div class="doc-toolbar" role="region" aria-label="Report controls">'
        '<span class="doc-brand">NHI-Blast '
        '<span class="doc-brand-chip">Offline what-if</span></span>'
        '<div class="doc-toolbar-actions">'
        '<div id="companion-theme-host"></div>'
        '<button type="button" class="copy-btn" data-action="print">Print / PDF</button>'
        "</div></div>"
    )
    body_html = (
        toolbar_html + '<header class="doc-head">'
        "<h1>Containment simulation report</h1>"
        "<p class='lead'>Offline model. Nothing was executed. "
        "Verify every action in your cloud account.</p>"
        "</header>" + "".join(sections)
    )
    return render_document(title="NHI-Blast What-If Report", body_html=body_html)


__all__ = ["render_whatif_html"]
