"""CLI cleanup errors disclose commitment instead of implying outputs were not written."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from nhi_blast.cli.app import app
from tests.test_diff_support import base_report, save_report
from tests.test_whatif_support import fx16_report, save, write_plan

pytestmark = pytest.mark.security


@pytest.mark.parametrize("command", ["scan", "rank", "export", "diff", "whatif"])
def test_cleanup_failure_keeps_committed_status_at_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    out = tmp_path / "out"
    if command == "diff":
        report = save_report(base_report(), tmp_path / "input.json")
        args = ["diff", str(report), str(report), "--format", "json"]
        filename = "diff.json"
    elif command == "whatif":
        report = save(fx16_report(), tmp_path / "input.json")
        plan = write_plan(tmp_path / "plan.json")
        args = ["whatif", str(report), "--plan", str(plan), "--format", "json"]
        filename = "whatif.json"
    else:
        root = tmp_path / "repo"
        root.mkdir()
        args = [command, str(root), "--format", "json"]
        filename = {"scan": "report.json", "rank": "rank.json", "export": "graph.json"}[command]
    args.extend(["--out", str(out)])
    original = Path.rmdir

    def broken(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name.startswith(".nhi-blast-stage-"):
            msg = "stage cleanup failed"
            raise OSError(msg)
        original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "rmdir", broken)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 4, result.output
    assert "artifacts committed; staging cleanup incomplete" in result.output
    assert "cannot write" not in result.output
    assert "Written:" not in result.output
    assert "Exported" not in result.output
    assert isinstance(json.loads((out / filename).read_text(encoding="utf-8")), dict)
