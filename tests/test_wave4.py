"""Wave 4 tests: UI templates, companion diff/whatif HTML, and OpenGraph export."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from nhi_blast.cli.app import app
from nhi_blast.diff.render import RENDERERS, render_diff_html
from nhi_blast.pipeline import ExportOptions, ScanOptions, run_export, run_scan
from nhi_blast.report.html import html_report
from nhi_blast.report.json_report import write_json
from nhi_blast.report.whatif_html import render_whatif_html
from nhi_blast.whatif.engine import run_whatif
from nhi_blast.whatif.plan import synthesize_auto_plan

FX07 = Path("tests/fixtures/fx07-incident")
FX14 = Path("tests/fixtures/fx14-hostile")


def test_w41_main_html_contains_graph_table_and_containment_sim() -> None:
    outcome = run_scan(ScanOptions(root=FX07, repo_slug="acme/shop", selectors=("repo-write",)))
    doc = html_report(outcome.report)
    assert 'id="graph-table-toggle"' in doc
    assert 'id="graph-table-panel"' in doc
    assert 'id="containment-sim"' in doc
    assert "function renderGraphTable(" in doc
    assert "function renderContainmentSim(" in doc


def test_w42_diff_html_cli_and_xss_escaping(tmp_path: Path) -> None:
    assert "html" in RENDERERS
    base_scan = run_scan(ScanOptions(root=FX07, repo_slug="acme/shop", selectors=("repo-write",)))
    head_scan = run_scan(ScanOptions(root=FX14, repo_slug="acme/shop", selectors=("repo-write",)))
    base_json = tmp_path / "base.json"
    head_json = tmp_path / "head.json"
    write_json(base_scan.report, base_json)
    write_json(head_scan.report, head_json)

    out_dir = tmp_path / "diff-out"
    runner = CliRunner()
    res = runner.invoke(
        app,
        ["diff", str(base_json), str(head_json), "--format", "html", "--out", str(out_dir)],
    )
    assert res.exit_code in (0, 1, 3), res.output
    html_file = out_dir / "diff.html"
    assert html_file.exists()
    content = html_file.read_text(encoding="utf-8")
    assert "Content-Security-Policy" in content
    assert "default-src 'none'" in content
    assert "motion-14.7.1" not in content
    assert content.count("<script") == 1

    # Hostile payload escaping check
    evil = render_diff_html(
        {
            "schema": "nhi-blast-diff/1.0",
            "comparability": {"status": "comparable", "incomparable": [], "context_drift": []},
            "summary": {
                "counts": {
                    "new": 1,
                    "changed": 0,
                    "not_observed": 0,
                    "resolved": 0,
                    "unchanged": 0,
                }
            },
            "findings": [
                {
                    "class": "new",
                    "severity": "HIGH",
                    "rule": "NHB-OIDC-002",
                    "scenario": "repo-write",
                    "title": "<script>alert(1)</script>",
                    "lk": "deadbeef1234",
                    "changed_fields": [],
                    "reasons": [],
                }
            ],
            "scenarios": {"only_in_base": [], "only_in_head": [], "compared": []},
        }
    )
    assert "<script>alert(1)</script>" not in evil
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in evil


def test_w42_whatif_html_cli_and_determinism(tmp_path: Path) -> None:
    scan = run_scan(ScanOptions(root=FX07, repo_slug="acme/shop", selectors=("repo-write",)))
    report_path = tmp_path / "report.json"
    write_json(scan.report, report_path)
    out_dir = tmp_path / "whatif-out"

    runner = CliRunner()
    res = runner.invoke(
        app,
        [
            "whatif",
            str(report_path),
            "--auto-plan",
            "--format",
            "json",
            "--format",
            "md",
            "--format",
            "html",
            "--out",
            str(out_dir),
        ],
    )
    assert res.exit_code == 0, res.output
    html_file = out_dir / "whatif.html"
    assert html_file.exists()
    text = html_file.read_text(encoding="utf-8")
    assert "Containment simulation report" in text
    assert "Content-Security-Policy" in text
    assert "motion-14.7.1" not in text
    assert text.count("<script") == 1

    # Determinism check
    auto = synthesize_auto_plan(scan.report)
    payload = run_whatif(scan.report, auto)
    assert render_whatif_html(scan.report, payload) == render_whatif_html(scan.report, payload)


def test_w43_opengraph_export_cli_and_schema(tmp_path: Path) -> None:
    out1 = tmp_path / "og1"
    out2 = tmp_path / "og2"
    r1 = run_export(ExportOptions(root=FX07, repo_slug="acme/shop", fmt="opengraph", out_dir=out1))
    r2 = run_export(ExportOptions(root=FX07, repo_slug="acme/shop", fmt="opengraph", out_dir=out2))
    assert r1.exit_code == 0
    assert r2.exit_code == 0
    p1 = out1 / "graph.opengraph.json"
    p2 = out2 / "graph.opengraph.json"
    assert p1.read_bytes() == p2.read_bytes()

    data = json.loads(p1.read_text(encoding="utf-8"))
    # Strict BloodHound CE OpenGraph v9.0.0 metadata (additionalProperties: false)
    assert data["metadata"] == {"source_kind": "NHI_Blast"}
    nodes = data["graph"]["nodes"]
    edges = data["graph"]["edges"]
    assert len(nodes) > 1
    assert len(edges) > 0

    env_nodes = [n for n in nodes if "NHI_Environment" in n["kinds"]]
    assert len(env_nodes) == 1
    env_props = env_nodes[0]["properties"]
    assert env_props["repository"] == "acme/shop"
    assert "tool_version" in env_props
    assert "inputs_digest" in env_props

    node_ids = set()
    for node in nodes:
        assert ":" not in node["id"]
        assert node["id"] not in node_ids
        node_ids.add(node["id"])
        assert node["kinds"][0].startswith("NHI_")
        assert "properties" in node
        for key in node["properties"]:
            assert key == key.lower()
            assert key not in {"objectid", "lastseen", "reconcile"}

    for edge in edges:
        assert edge["start"]["match_by"] == "id"
        assert edge["end"]["match_by"] == "id"
        assert ":" not in edge["start"]["value"]
        assert ":" not in edge["end"]["value"]
        assert edge["kind"].startswith("NHI_")
