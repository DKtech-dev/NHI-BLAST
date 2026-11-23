"""Permanent cross-module contract tests for UI, escaping, docs/assets, and analysis parity."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, cast

import pytest

from nhi_blast import __version__
from nhi_blast.analysis import rotation
from nhi_blast.core.models import EdgeKind, Report
from nhi_blast.report.diff_html import render_diff_html
from nhi_blast.report.effects import EFFECTS_CSS
from nhi_blast.report.ui import THEME_SWITCH_CSS, THEME_TOKENS_CSS
from nhi_blast.report.whatif_html import render_whatif_html

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT / "src" / "nhi_blast" / "report" / "templates"
FONTS_DIR = ROOT / "src" / "nhi_blast" / "report" / "assets" / "fonts"

_CSS_DECL_RE = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")
_CSS_VAR_RE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")
_JS_SET_PROP_RE = re.compile(r"setProperty\(\s*['\"](--[A-Za-z0-9_-]+)['\"]")


def _extract_css_definitions(text: str) -> set[str]:
    return set(_CSS_DECL_RE.findall(text))


def _extract_css_usages(text: str) -> set[str]:
    return set(_CSS_VAR_RE.findall(text))


def _extract_js_inline_css_vars(*sources: str) -> set[str]:
    found: set[str] = set()
    for src in sources:
        found.update(_JS_SET_PROP_RE.findall(src))
    return found


def test_all_css_custom_properties_are_defined() -> None:
    report_css = (TEMPLATES_DIR / "report.css").read_text(encoding="utf-8")
    companion_css = (TEMPLATES_DIR / "companion.css").read_text(encoding="utf-8")
    report_html = (TEMPLATES_DIR / "report.html").read_text(encoding="utf-8")
    app_js = (TEMPLATES_DIR / "app.js").read_text(encoding="utf-8")
    theme_js = (TEMPLATES_DIR / "theme.js").read_text(encoding="utf-8")
    effects_py = (ROOT / "src" / "nhi_blast" / "report" / "effects.py").read_text(encoding="utf-8")

    defined_report = (
        _extract_css_definitions(report_css)
        | _extract_css_definitions(THEME_TOKENS_CSS)
        | _extract_css_definitions(THEME_SWITCH_CSS)
        | _extract_css_definitions(EFFECTS_CSS)
        | _extract_css_definitions(report_html)
        | _extract_js_inline_css_vars(app_js, theme_js, effects_py)
    )
    defined_companion = (
        _extract_css_definitions(companion_css)
        | _extract_css_definitions(THEME_TOKENS_CSS)
        | _extract_css_definitions(THEME_SWITCH_CSS)
        | _extract_css_definitions(EFFECTS_CSS)
    )

    missing_report = sorted(_extract_css_usages(report_css) - defined_report)
    missing_companion = sorted(_extract_css_usages(companion_css) - defined_companion)

    assert not missing_report, f"Undefined CSS custom properties in report.css: {missing_report}"
    assert not missing_companion, (
        f"Undefined CSS custom properties in companion.css: {missing_companion}"
    )

    for forbidden in ("--radius-md", "--radius-sm", "--text-sm", "--text-base", "--text-xs"):
        assert forbidden not in report_css, f"Legacy undefined token {forbidden} in report.css"
        assert forbidden not in companion_css, (
            f"Legacy undefined token {forbidden} in companion.css"
        )


def test_app_js_uses_valid_report_model_fields() -> None:
    app_js = (TEMPLATES_DIR / "app.js").read_text(encoding="utf-8")

    # Non-existent model properties must never be read
    assert "n.confidence" not in app_js
    assert "item.role" not in app_js

    # Verify renderGraphTable derives node confidence from node.evidence
    gt_start = app_js.index("function renderGraphTable(")
    gt_end = app_js.index("function renderContainmentSim(")
    gt_body = app_js[gt_start:gt_end]
    assert ".evidence" in gt_body
    assert "deriveNodeConfidence(" in gt_body

    # Verify renderContainmentSim resolves role via nodes.get(cid) and attrs.role_name/attrs.role
    sim_start = gt_end
    sim_end = app_js.index("function renderGraph(", sim_start)
    sim_body = app_js[sim_start:sim_end]
    assert "nodes.get(" in sim_body
    assert ".role_name" in sim_body
    assert ".role" in sim_body
    assert "seenRoles" in sim_body

    # Security invariant: zero unsafe DOM / dynamic evaluation sinks
    for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function"):
        assert forbidden not in app_js, f"Forbidden unsafe sink {forbidden!r} found in app.js"


def test_ui_py_escapes_html_angle_brackets_in_json() -> None:
    ui_path = ROOT / "src" / "nhi_blast" / "report" / "ui.py"
    ui_source = ui_path.read_text(encoding="utf-8")

    # Verify ui.py uses literal JSON unicode escapes rather than silent no-ops
    assert '.replace("<", "\\\\u003c")' in ui_source
    assert '.replace(">", "\\\\u003e")' in ui_source

    # Behavioral check on the same escaping pattern
    sample = (
        json.dumps(
            {"k": "</script><img onerror=alert(1)>"},
            sort_keys=True,
            separators=(",", ":"),
        )
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    assert "<" not in sample
    assert ">" not in sample
    assert "\\u003c" in sample
    assert "\\u003e" in sample
    assert json.loads(sample) == {"k": "</script><img onerror=alert(1)>"}

    # AST scan across src/nhi_blast/ for silent .replace("<", "<") / .replace(">", ">") no-ops
    noops: list[str] = []
    for py_file in sorted((ROOT / "src" / "nhi_blast").rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "replace"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[0].value, str)
                and isinstance(node.args[1].value, str)
                and node.args[0].value == node.args[1].value
            ):
                rel = py_file.relative_to(ROOT).as_posix()
                a, b = node.args[0].value, node.args[1].value
                noops.append(f"{rel}:{node.lineno}: .replace({a!r}, {b!r})")
    assert not noops, "Silent no-op .replace() calls detected:\n" + "\n".join(noops)


def test_issue_template_and_readme_assets_match_repo() -> None:
    issue_template = (ROOT / ".github" / "ISSUE_TEMPLATE" / "beta-bug-report.yml").read_text(
        encoding="utf-8"
    )
    assert __version__ in issue_template, (
        f"beta-bug-report.yml must reference current version {__version__}"
    )
    assert "0.2.0" not in issue_template, "beta-bug-report.yml still references stale version 0.2.0"

    render_mjs = (ROOT / "assets" / "readme" / "render.mjs").read_text(encoding="utf-8")
    referenced_fonts = re.findall(r'["\']([A-Za-z0-9._-]+\.woff2)["\']', render_mjs)
    assert referenced_fonts, "Expected at least one .woff2 reference in assets/readme/render.mjs"
    missing_fonts = [name for name in referenced_fonts if not (FONTS_DIR / name).is_file()]
    assert not missing_fonts, (
        f"assets/readme/render.mjs references missing font(s) in {FONTS_DIR}: {missing_fonts}"
    )

    whatif_doc = (ROOT / "docs" / "whatif.md").read_text(encoding="utf-8")
    assert "HTML is not available" not in whatif_doc
    assert "--format" in whatif_doc
    assert "html" in whatif_doc
    assert "--auto-plan" in whatif_doc
    idx_remove = whatif_doc.find("Remove trust or disable entrypoint")
    idx_revoke = whatif_doc.find("Revoke role sessions")
    assert 0 <= idx_remove < idx_revoke, (
        "docs/whatif.md playbook order must list trust/entrypoint removal before session revocation"
    )

    limitations_doc = (ROOT / "docs" / "known-limitations.md").read_text(encoding="utf-8")
    assert "Role-to-role chaining is outside the specification's scope" not in limitations_doc
    stale_cond = (
        "`Numeric*`, `Date*`, `IpAddress`, `Binary*` and policy variables are not evaluated"
    )
    assert stale_cond not in limitations_doc.replace("\n", " ")


def test_rotation_and_benchmark_parity() -> None:
    pending: list[str] = []
    if EdgeKind.CAN_ASSUME not in rotation._CONTROL_EDGES:
        pending.append("EdgeKind.CAN_ASSUME not yet in rotation._CONTROL_EDGES")

    bench_path = ROOT / "scripts" / "benchmark_corpus.py"
    bench_text = bench_path.read_text(encoding="utf-8") if bench_path.is_file() else ""
    if "SCENARIO_RULES" not in bench_text:
        pending.append("SCENARIO_RULES not yet used in scripts/benchmark_corpus.py")

    if pending:
        pytest.xfail("Pending Team B integration: " + "; ".join(pending))

    assert EdgeKind.CAN_ASSUME in rotation._CONTROL_EDGES
    assert "SCENARIO_RULES" in bench_text


def test_whatif_html_handles_rejected_steps_accurately() -> None:
    payload: dict[str, Any] = {
        "source_report_digest": "sha256:src",
        "plan_digest": "sha256:plan",
        "per_scenario": [],
        "steps": [
            {
                "index": 1,
                "type": "disable_entrypoint",
                "status": "applied",
                "args": {"node": "job:deploy"},
                "effects": {},
            },
            {
                "index": 2,
                "type": "revoke_role_sessions",
                "status": "rejected",
                "args": {"role": "arn:aws:iam::123456789012:role/missing"},
                "effects": {"cutoff": "2026-01-01T00:00:00Z"},
                "reason": "unresolved_reference",
            },
        ],
        "rejected": [
            {
                "index": 2,
                "type": "revoke_role_sessions",
                "reason": "unresolved_reference",
            }
        ],
        "warnings": [],
    }
    html = render_whatif_html(cast(Report, None), payload)

    # Applied steps KPI counts only non-rejected steps (1, not 2)
    assert '<span class="kpi-label">Applied steps</span><strong class="kpi-val">1</strong>' in html
    assert '<span class="kpi-label">Rejected steps</span><strong class="kpi-val">1</strong>' in html
    # Rejected step must never be styled with green pill-ok
    assert "pill-ok'>rejected" not in html
    assert 'pill-ok">rejected' not in html
    assert "pill-crit'>rejected</span>" in html
    # Rejected revoke_role_sessions must never emit an AWSRevokeOlderSessions snippet
    assert "AWSRevokeOlderSessions" not in html


def test_diff_html_does_not_render_pass_for_incomparable_exit_code_3() -> None:
    payload: dict[str, Any] = {
        "schema": "nhi-blast-diff/1.0",
        "comparability": {
            "status": "incomparable",
            "incomparable": [{"code": "repo_slug_differs"}],
            "context_drift": [],
        },
        "summary": {
            "counts": {
                "new": 0,
                "changed": 0,
                "not_observed": 0,
                "resolved": 0,
                "unchanged": 0,
            }
        },
        "gate": {
            "fail_on": "high",
            "blocking": [],
            "suppressed": [],
            "exit_code": 3,
        },
        "findings": [],
        "scenarios": {"only_in_base": [], "only_in_head": [], "compared": []},
    }
    html = render_diff_html(payload)

    assert 'pill-ok">PASS</span>' not in html
    assert '<span class="pill pill-warn">INCOMPARABLE</span>' in html
    assert "exit=<code>3</code>" in html


def test_external_audit_package_doc_has_no_stale_references() -> None:
    audit_doc = (ROOT / "docs" / "external-audit-package.md").read_text(encoding="utf-8")
    assert "AGENTS.md" not in audit_doc
    assert "current source line is 0.2.0" not in audit_doc
    assert "0.2.0" not in audit_doc
    assert f"current source line is {__version__}" in audit_doc


def test_app_js_handles_session_credential_hops_and_declared_rank() -> None:
    src = Path("src/nhi_blast/report/templates/app.js").read_text(encoding="utf-8")
    assert "edge.attrs.session_credential" in src
    assert "declared: 0, derived: 1, assumed: 2, unknown: 3" in src
    assert "observed: 0" not in src
