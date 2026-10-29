from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nhi_blast.cli.app import app
from nhi_blast.parsers.gha.literals import redact_literals
from nhi_blast.pipeline import RankOptions, ScanOptions, run_rank, run_scan
from nhi_blast.report.graph_export import graph_export_dot, graph_export_json
from nhi_blast.report.html import html_report
from nhi_blast.report.json_report import report_json
from nhi_blast.report.rank import rank_json
from nhi_blast.report.redaction import redact_payload
from nhi_blast.report.sarif import sarif_report

pytestmark = pytest.mark.security


@pytest.mark.parametrize("terminated", [True, False])
def test_private_key_redaction_covers_body_and_overlapping_literal(terminated: bool) -> None:
    token = "ghp_" + "P" * 36
    body = "SYNTHETIC_PRIVATE_KEY_CANARY"
    # Assembled at runtime so the scanner gate stays strict without an allowlist.
    header = "-----BEGIN " + "PRIVATE KEY-----"
    footer = "-----END " + "PRIVATE KEY-----"
    value = f"prefix {header}\n{body}\n{token}\n"
    if terminated:
        value += f"{footer} suffix"
    result = redact_literals(value)
    leaked = body in result or token in result or "PRIVATE KEY-----" in result
    assert not leaked
    assert result.startswith("prefix [REDACTED")
    assert result.endswith(" suffix") == terminated
    assert redact_literals(result) == result


def test_redaction_preserves_distinct_keys_and_identifier_references() -> None:
    tokens = ("ghp_" + "J" * 36, "ghp_" + "L" * 36)
    payload = {
        "nodes": [{"id": token} for token in tokens],
        "references": list(tokens),
        "metadata": dict.fromkeys(tokens, "value"),
    }
    result = redact_payload(payload)
    assert len(result["metadata"]) == 2
    assert result["references"] == [node["id"] for node in result["nodes"]]
    leaked = any(token in json.dumps(result) for token in tokens)
    assert not leaked
    assert redact_payload(result) == result


def test_rank_json_redacts_recognized_literals_in_action_references(tmp_path: Path) -> None:
    token = "ghp_" + "T" * 36
    workflow = tmp_path / ".github/workflows/build.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "on: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
        f"      - uses: stranger/repo@{token}\n",
        encoding="utf-8",
    )
    outcome = run_rank(RankOptions(root=tmp_path))
    serialized = rank_json(outcome.report)
    assert json.loads(serialized)["rows"]
    leaked = token in serialized or token[4:20] in serialized
    assert not leaked


def test_recognized_literals_in_identifiers_are_redacted_without_merging(tmp_path: Path) -> None:
    tokens = ("ghp_" + "Q" * 36, "ghp_" + "R" * 36)
    workflow = tmp_path / ".github/workflows/build.yml"
    workflow.parent.mkdir(parents=True)
    text = (
        "on: push\npermissions: read-all\njobs:\n  build:\n"
        "    runs-on: ubuntu-latest\n    env:\n"
        f"      TOKEN: {tokens[0]}\n    steps:\n"
        f"      - uses: stranger/repo@{tokens[0]}\n"
        f"      - uses: stranger/repo@{tokens[1]}\n"
    )
    workflow.write_text(text, encoding="utf-8")
    outcome = run_scan(ScanOptions(root=tmp_path, selectors=("all-mutable-actions", "repo-write")))
    report = outcome.report
    outputs = {
        "console": outcome.console_text,
        "json": report_json(report),
        "sarif": json.dumps(sarif_report(report)),
        "html": html_report(report),
        "dot": graph_export_dot(tool=report.tool, inputs=report.inputs, graph=report.graph),
        "graph_json": graph_export_json(
            tool=report.tool,
            inputs=report.inputs,
            graph=report.graph,
            data_files=report.data_files,
            diagnostics=report.diagnostics,
        ),
    }
    for name, output in outputs.items():
        leaked = any(token in output or token[4:20] in output for token in tokens)
        assert not leaked, name
    data = json.loads(outputs["json"])
    actions = [n for n in data["graph"]["nodes"] if n["kind"] == "ACTION_REF"]
    assert len(actions) == 2
    assert len({n["id"] for n in actions}) == 2
    assert all(n["id"] in outputs["dot"] for n in actions)
    assert all(n["id"] in outputs["console"] for n in actions)
    node_ids = {n["id"] for n in data["graph"]["nodes"]}
    assert all(e["src"] in node_ids and e["dst"] in node_ids for e in data["graph"]["edges"])
    assert data["inputs"]["files"][0]["sha256"] == hashlib.sha256(workflow.read_bytes()).hexdigest()
    assert any(f["rule"] == "NHB-GHA-005" for f in data["findings"])
    assert outputs["json"] == report_json(report)


def test_diagnostic_and_usage_errors_do_not_echo_recognized_literals(tmp_path: Path) -> None:
    token = "ghp_" + "V" * 36
    workflow = tmp_path / ".github/workflows/build.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        f"permissions: {token}\non: push\njobs:\n  build:\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    result = run_scan(ScanOptions(root=tmp_path))
    leaked = token in report_json(result.report) or token in result.console_text
    assert not leaked
    (tmp_path / "nhi-blast.toml").write_text(f"{token} = 1\n", encoding="utf-8")
    usage = CliRunner().invoke(app, ["scan", str(tmp_path)])
    assert usage.exit_code == 2
    leaked = token in usage.output
    assert not leaked


@pytest.mark.parametrize(
    ("command", "filename"),
    [("scan", "report.json"), ("rank", "rank.json"), ("export", "graph.json")],
)
def test_written_output_path_does_not_echo_recognized_credentials(
    tmp_path: Path, command: str, filename: str
) -> None:
    token = "ghp_" + "K" * 36
    usage = CliRunner().invoke(
        app, [command, str(tmp_path), "--format", "json", "--out", str(tmp_path / token)]
    )
    assert usage.exit_code == 0
    assert (tmp_path / token / filename).is_file()
    leaked = token in usage.output
    assert not leaked


def test_cli_legacy_redirected_stdout_does_not_abort_unicode_scan(tmp_path: Path) -> None:
    workflow = tmp_path / ".github/workflows/build.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "name: Snowman \u2603\non: push\njobs:\n  build:\n    name: Snowman \u2603\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - uses: example/action@v1\n"
        "    env:\n      API_TOKEN: ${{ secrets.API_TOKEN }}\n",
        encoding="utf-8",
    )
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from nhi_blast.cli.app import main; main()",
            "scan",
            str(tmp_path),
            "--simulate-compromise",
            "repo-write",
            "--format",
            "json",
            "--out",
            str(tmp_path / "out"),
        ],
        capture_output=True,
        check=False,
        timeout=30,
        env={**os.environ, "PYTHONIOENCODING": "cp1252:strict"},
        cwd=tmp_path,
    )
    assert process.returncode == 0, process.stderr.decode("ascii", errors="replace")
    data = json.loads((tmp_path / "out/report.json").read_text(encoding="utf-8"))
    assert any("\u2603" in node["label"] for node in data["graph"]["nodes"])
