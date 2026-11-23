"""Phase 1 polish tests: CLI ergonomics, runner groups, OWASP/CWE SARIF, PR comment diff."""

from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from nhi_blast import __version__
from nhi_blast.cli.app import app
from nhi_blast.diff.render import RENDERERS
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.json_report import write_json
from nhi_blast.report.sarif import sarif_report

FX07 = Path("tests/fixtures/fx07-incident")


def test_root_version_flag_and_export_help() -> None:
    runner = CliRunner()
    v1 = runner.invoke(app, ["--version"])
    assert v1.exit_code == 0
    assert f"nhi-blast {__version__}" in v1.output

    v2 = runner.invoke(app, ["-V"])
    assert v2.exit_code == 0
    assert f"nhi-blast {__version__}" in v2.output

    exp_help = runner.invoke(app, ["export", "--help"])
    assert exp_help.exit_code == 0
    assert "opengraph" in exp_help.output.lower()


def test_init_scaffolds_config_and_respects_force(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/acme/demo-app.git\n',
        encoding="utf-8",
    )
    runner = CliRunner()
    res = runner.invoke(app, ["init", str(tmp_path)])
    assert res.exit_code == 0, res.output
    cfg = tmp_path / "nhi-blast.toml"
    assert cfg.is_file()
    text = cfg.read_text(encoding="utf-8")
    assert 'repo_slug = "acme/demo-app"' in text
    assert "[repo]" not in text
    assert "https://github.com/DKtech-dev/nhi-blast#configuration" in text

    # Refuses to overwrite without --force
    again = runner.invoke(app, ["init", str(tmp_path)])
    assert again.exit_code == 2

    # Overwrites with --force
    forced = runner.invoke(app, ["init", str(tmp_path), "--force"])
    assert forced.exit_code == 0


def test_init_then_scan_round_trip(tmp_path: Path) -> None:
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/acme/demo-app.git\n',
        encoding="utf-8",
    )
    runner = CliRunner()
    init_res = runner.invoke(app, ["init", str(tmp_path)])
    assert init_res.exit_code == 0, init_res.output

    scan_res = runner.invoke(app, ["scan", str(tmp_path)])
    assert scan_res.exit_code == 0, scan_res.output


def test_runs_on_group_object_triggers_self_hosted_finding(tmp_path: Path) -> None:
    wf = tmp_path / ".github" / "workflows" / "ci.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text(
        """name: CI
on: push
jobs:
  build:
    runs-on:
      group: prod-runners
      labels: [linux-x64]
    steps:
      - run: echo hi
""",
        encoding="utf-8",
    )
    outcome = run_scan(ScanOptions(root=tmp_path, repo_slug="acme/app"))
    rules = {f.rule for f in outcome.report.findings}
    assert "NHB-GHA-003" in rules


def test_sarif_rules_carry_owasp_nhi_and_cwe_tags() -> None:
    outcome = run_scan(ScanOptions(root=FX07, repo_slug="acme/shop", selectors=("repo-write",)))
    sarif = sarif_report(outcome.report)
    rules = sarif["runs"][0]["tool"]["driver"]["rules"]
    assert rules
    for rule in rules:
        tags = rule["properties"]["tags"]
        assert any(tag.startswith("OWASP-NHI") for tag in tags), rule["id"]
        assert any(tag.startswith("CWE-") for tag in tags), rule["id"]


def test_diff_pr_comment_format_renders_markdown(tmp_path: Path) -> None:
    assert "pr-comment" in RENDERERS
    scan = run_scan(ScanOptions(root=FX07, repo_slug="acme/shop", selectors=("repo-write",)))
    rep = tmp_path / "report.json"
    write_json(scan.report, rep)
    out = tmp_path / "diff-out"
    runner = CliRunner()
    res = runner.invoke(
        app,
        ["diff", str(rep), str(rep), "--format", "pr-comment", "--out", str(out)],
    )
    assert res.exit_code == 0, res.output
    md = (out / "diff.md").read_text(encoding="utf-8")
    assert "## NHI-Blast Diff Summary" in md
    assert "**Comparability:**" in md


def test_pre_commit_and_citation_files_are_valid() -> None:
    hooks = yaml.safe_load(Path(".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    assert isinstance(hooks, list)
    assert hooks[0]["id"] == "nhi-blast"
    citation = yaml.safe_load(Path("CITATION.cff").read_text(encoding="utf-8"))
    assert citation["cff-version"] == "1.2.0"
    assert citation["license"] == "MIT"


def test_init_refuses_dangling_symlink_and_sanitizes_slug(tmp_path: Path) -> None:
    outside = tmp_path / "outside.toml"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "nhi-blast.toml").symlink_to(outside)
    runner = CliRunner()
    res = runner.invoke(app, ["init", str(repo), "--force"])
    assert res.exit_code == 2
    assert not outside.exists()

    # Hostile git remote with quote/newline cannot inject TOML
    repo2 = tmp_path / "repo2"
    (repo2 / ".git").mkdir(parents=True)
    (repo2 / ".git" / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/evil/"injected\n',
        encoding="utf-8",
    )
    res2 = runner.invoke(app, ["init", str(repo2)])
    assert res2.exit_code == 0
    assert 'repo_slug = "OWNER/REPO"' in (repo2 / "nhi-blast.toml").read_text(encoding="utf-8")
