"""CLI contract: commands, exit codes and the exception boundary (M6)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nhi_blast.cli.app import app
from nhi_blast.report.model_json import report_schema
from tests.entrypoint_support import resolve_cli_entrypoint

FIXTURES = Path(__file__).parent / "fixtures"
FX03 = FIXTURES / "fx03-wildcard-trust"
FX07 = FIXTURES / "fx07-incident"
ACTION = "action:tj-actions/changed-files@v45"

MALFORMED_WORKFLOW = """name: broken
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps: [
"""

runner = CliRunner()


def _invoke(*args: str) -> object:
    return runner.invoke(app, list(args))


def _write_malformed(root: Path) -> None:
    path = root / ".github" / "workflows" / "broken.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(MALFORMED_WORKFLOW, encoding="utf-8")


def test_root_help_lists_every_command() -> None:
    result = _invoke("--help")

    assert result.exit_code == 0
    for command in ("scan", "rank", "explain", "export", "schema", "version"):
        assert command in result.stdout
    assert "Offline, evidence-labelled" in result.stdout


def test_no_arguments_is_usage_error() -> None:
    result = _invoke()

    assert result.exit_code == 2
    assert "Usage:" in result.stderr


def test_version_and_data_report() -> None:
    plain = _invoke("version")
    assert plain.exit_code == 0
    assert "nhi-blast " in plain.stdout
    assert "report schema nhi-blast-report/1.0" in plain.stdout
    assert "Data files:" not in plain.stdout

    data = _invoke("version", "--data")
    assert data.exit_code == 0
    assert "Data files: 8" in data.stdout
    assert "rules.yaml" in data.stdout
    assert "verified 20" in data.stdout
    assert "https://" in data.stdout


def test_schema_matches_the_embedded_report_schema() -> None:
    result = _invoke("schema")

    assert result.exit_code == 0
    assert json.loads(result.stdout) == report_schema()


def test_scan_console_is_default_and_writes_nothing(tmp_path: Path) -> None:
    out_dir = tmp_path / "not-requested"
    result = _invoke(
        "scan",
        str(FX07),
        "--simulate-compromise",
        ACTION,
        "--out",
        str(out_dir),
    )

    assert result.exit_code == 0
    assert "R (ends with entrypoint): 3" in result.stdout
    assert "E (expires on its own): 2" in result.stdout
    assert "Z (survives): 5" in result.stdout
    assert "Written:" not in result.stdout
    assert not out_dir.exists()
    assert "\x1b" not in result.stdout


def test_scan_writes_every_requested_format(tmp_path: Path) -> None:
    out_dir = tmp_path / "reports"
    result = _invoke(
        "scan",
        str(FX07),
        "--simulate-compromise",
        ACTION,
        "--format",
        "json",
        "--format",
        "sarif",
        "--format",
        "html",
        "--out",
        str(out_dir),
    )

    assert result.exit_code == 0
    assert (out_dir / "report.json").is_file()
    assert (out_dir / "report.sarif").is_file()
    assert (out_dir / "report.html").is_file()
    assert "Written:" in result.stdout
    assert "report.json" in result.stdout


def test_scan_fail_on_and_finding_location() -> None:
    result = _invoke("scan", str(FX03), "--fail-on", "high")

    assert result.exit_code == 1
    assert "tfstate.json:23" in result.stdout
    assert _invoke("scan", str(FX03), "--fail-on", "never").exit_code == 0
    assert _invoke("scan", str(FX03)).exit_code == 0


def test_strict_exit_three_and_priority_over_fail_on(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed"
    _write_malformed(malformed)

    relaxed = _invoke("scan", str(malformed))
    assert relaxed.exit_code == 0
    strict = _invoke("scan", str(malformed), "--strict")
    assert strict.exit_code == 3
    assert "D-YAML-PARSE" in strict.stdout

    combined = tmp_path / "combined"
    shutil.copytree(FX03, combined)
    _write_malformed(combined)
    result = _invoke("scan", str(combined), "--strict", "--fail-on", "high")
    assert result.exit_code == 3


def test_output_error_wins_over_fail_on(tmp_path: Path) -> None:
    blocking = tmp_path / "blocking"
    blocking.write_text("not a directory", encoding="utf-8")

    result = _invoke(
        "scan",
        str(FX03),
        "--fail-on",
        "high",
        "--format",
        "json",
        "--out",
        str(blocking),
    )

    assert result.exit_code == 4
    assert "error: cannot write report.json" in result.stderr


def test_usage_errors_exit_two(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text('{"format_version": "1.0"}', encoding="utf-8")
    bad_config = tmp_path / "bad-config"
    bad_config.mkdir()
    (bad_config / "nhi-blast.toml").write_text("wat = true\n", encoding="utf-8")

    cases = [
        ("scan", str(FX07), "--format", "xml"),
        ("scan", str(FX07), "--fail-on", "info"),
        ("scan", str(FX07), "--simulate-compromise", "nope"),
        ("scan", str(FX07), "--tf-json", str(outside)),
        ("scan", str(FX07), "--iam-json", str(outside)),
        ("scan", str(FX07), "--config", str(outside)),
        ("scan", str(bad_config)),
        ("scan", str(tmp_path / "missing")),
        ("scan"),
        ("rank", str(FX07), "--format", "sarif"),
        ("export", str(FX07)),
        ("export", str(FX07), "--format", "opengraph"),
        ("explain", "anything", "--report", str(tmp_path / "missing.json")),
    ]
    for args in cases:
        result = _invoke(*args)
        assert result.exit_code == 2, (args, result.exit_code, result.stderr)
        assert result.stderr.startswith(("error:", "Usage:")), (args, result.stderr)


def test_internal_errors_are_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = "SENTINEL_SECRET_VALUE_DO_NOT_PRINT"

    def explode(options: object, *, color: bool = False) -> object:
        del options, color
        raise RuntimeError(sentinel)

    monkeypatch.setattr("nhi_blast.cli.commands.run_scan", explode)
    result = _invoke("scan", str(FX07))

    assert result.exit_code == 4
    combined = result.stdout + result.stderr
    assert "internal error: RuntimeError" in combined
    assert sentinel not in combined
    assert "Traceback" not in combined


def test_explain_reads_a_saved_report(tmp_path: Path) -> None:
    out_dir = tmp_path / "reports"
    saved = _invoke(
        "scan",
        str(FX07),
        "--simulate-compromise",
        ACTION,
        "--format",
        "json",
        "--out",
        str(out_dir),
    )
    assert saved.exit_code == 0
    payload = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    finding_id = payload["findings"][0]["id"]
    node_id = payload["graph"]["nodes"][0]["id"]

    finding = _invoke("explain", finding_id, "--report", str(out_dir / "report.json"))
    assert finding.exit_code == 0
    assert finding.stdout.startswith(f"Finding {finding_id}")
    assert "Evidence:" in finding.stdout

    node = _invoke("explain", node_id, "--report", str(out_dir / "report.json"))
    assert node.exit_code == 0
    assert node.stdout.startswith(f"Node {node_id}")

    missing = _invoke("explain", "missing-id", "--report", str(out_dir / "report.json"))
    assert missing.exit_code == 2
    assert "was not found in the report" in missing.stderr


def test_rank_console_and_json(tmp_path: Path) -> None:
    console = _invoke("rank", str(FX07))
    assert console.exit_code == 0
    assert "tj-actions/changed-files@v45" in console.stdout
    assert "TAG" in console.stdout

    out_dir = tmp_path / "rank"
    saved = _invoke("rank", str(FX07), "--format", "json", "--out", str(out_dir))
    assert saved.exit_code == 0
    assert (out_dir / "rank.json").is_file()
    assert "Written:" in saved.stdout
    payload = json.loads((out_dir / "rank.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "nhi-blast-report/1.0/rank"


def test_export_json_and_dot(tmp_path: Path) -> None:
    json_dir = tmp_path / "json"
    json_result = _invoke("export", str(FX07), "--format", "json", "--out", str(json_dir))
    assert json_result.exit_code == 0
    assert (json_dir / "graph.json").is_file()
    assert "Exported" in json_result.stdout

    dot_dir = tmp_path / "dot"
    dot_result = _invoke("export", str(FX07), "--format", "dot", "--out", str(dot_dir))
    assert dot_result.exit_code == 0
    dot_text = (dot_dir / "graph.dot").read_text(encoding="utf-8")
    assert dot_text.startswith("// NHI-Blast graph export")
    assert "digraph nhi_blast {" in dot_text


def test_scan_no_color_flag_is_accepted() -> None:
    result = _invoke("scan", str(FX07), "--no-color")

    assert result.exit_code == 0
    assert "\x1b" not in result.stdout


def test_installed_console_script_runs() -> None:
    executable = resolve_cli_entrypoint()

    completed = subprocess.run(
        [str(executable), "version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0
    assert "report schema nhi-blast-report/1.0" in completed.stdout
    assert completed.stderr == ""
