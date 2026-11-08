"""The diff and baseline commands end to end (exit codes, determinism, hostile input)."""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from nhi_blast.cli.diff_cmd import baseline_app, diff
from nhi_blast.diff.render import RENDERERS, Renderer, register_renderer
from nhi_blast.report import loader
from tests.test_diff_support import (
    FIXTURES,
    base_report,
    save_report,
    with_analyzer,
    without_rule,
)

DIFFS = FIXTURES / "diff"
CANARY = "ghp_" + "Canary9876543210" * 3

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)
app.command("diff")(diff)
app.add_typer(baseline_app, name="baseline")
runner = CliRunner()


def _args(base: Path, head: Path, *extra: str) -> list[str]:
    return ["diff", str(base), str(head), *extra]


def _copy(name: str, directory: Path) -> Path:
    target = directory / name
    shutil.copyfile(DIFFS / name, target)
    return target


def test_self_diff_exits_zero_and_is_empty() -> None:
    base = DIFFS / "base.json"
    result = runner.invoke(app, _args(base, base, "--fail-on", "low"))
    assert result.exit_code == 0, result.stderr
    assert "Comparability: comparable" in result.stdout
    assert "unchanged=7" in result.stdout
    assert "Gate: fail_on=low blocking=0" in result.stdout


def test_new_findings_at_or_above_the_threshold_exit_one() -> None:
    base = DIFFS / "base-without-oidc.json"
    head = DIFFS / "base.json"
    assert runner.invoke(app, _args(base, head, "--fail-on", "high")).exit_code == 1
    assert runner.invoke(app, _args(base, head, "--fail-on", "never")).exit_code == 0
    assert runner.invoke(app, _args(base, head)).exit_code == 0
    out = runner.invoke(app, _args(base, head, "--fail-on", "HIGH")).stdout
    assert "New findings (not present in BASE)" in out
    assert "NHB-OIDC-002" in out


def test_resolved_is_worded_as_no_longer_observed() -> None:
    result = runner.invoke(app, _args(DIFFS / "base.json", DIFFS / "head-pinned.json"))
    assert result.exit_code == 0
    assert "No longer observed under comparable analysis" in result.stdout
    assert "NHB-GHA-001" in result.stdout


def test_incomparable_exits_three(tmp_path: Path) -> None:
    other = base_report().model_copy(
        update={
            "inputs": base_report().inputs.model_copy(update={"repo_slug": "acme/other"}),
        }
    )
    head = save_report(other, tmp_path / "other.json")
    result = runner.invoke(app, _args(DIFFS / "base.json", head, "--fail-on", "low"))
    assert result.exit_code == 3
    assert "INCOMPARABLE" in result.stdout
    assert "no finding classification" in result.stdout


def test_usage_and_input_errors_exit_two(tmp_path: Path) -> None:
    base = DIFFS / "base.json"
    cases = [
        _args(base, tmp_path / "missing.json"),
        _args(tmp_path / "missing.json", base),
        _args(base, base, "--fail-on", "urgent"),
        _args(base, base, "--format", "pdf"),
        _args(base, base, "--as-of", "yesterday"),
        _args(base, base, "--baseline", str(tmp_path / "nope.json")),
        _args(base, tmp_path),
    ]
    for args in cases:
        result = runner.invoke(app, args)
        assert result.exit_code == 2, (args, result.exit_code, result.stderr)
        assert result.stderr.startswith("error:"), (args, result.stderr)
        assert "Traceback" not in result.stderr


def _hostile_texts() -> list[str]:
    return [
        "",
        "not json",
        "[]",
        "null",
        '{"schema":"nhi-blast-report/9.9"}',
        '{"schema":"nhi-blast-report/1.1"}',
        "[" * 200000,
        '{"a":' * 50000,
        "\ufeff{}",
        '{"schema":"nhi-blast-report/1.1","tool":{"name":"x","version":"1"},"inputs":1}',
    ]


@pytest.mark.parametrize("index", range(10))
def test_hostile_report_json_is_a_controlled_exit_two(tmp_path: Path, index: int) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(_hostile_texts()[index], encoding="utf-8")
    for args in (_args(bad, DIFFS / "base.json"), _args(DIFFS / "base.json", bad)):
        result = runner.invoke(app, args)
        assert result.exit_code == 2, (index, result.exit_code, result.stderr[:200])
        assert result.stderr.startswith("error:")
        assert "Traceback" not in result.stderr
        assert len(result.stderr) < 1000


def test_binary_and_oversized_reports_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "bin.json"
    binary.write_bytes(b"\xff\xfe\x00\x01" * 100)
    assert runner.invoke(app, _args(binary, DIFFS / "base.json")).exit_code == 2
    monkeypatch.setattr(loader, "_MAX_REPORT_BYTES", 1000)
    result = runner.invoke(app, _args(DIFFS / "base.json", DIFFS / "base.json"))
    assert result.exit_code == 2
    assert "larger than" in result.stderr


def test_json_output_is_byte_deterministic_across_runs_and_locations(tmp_path: Path) -> None:
    outputs: list[bytes] = []
    for name in ("a/deep/place", "b"):
        where = tmp_path / name
        where.mkdir(parents=True)
        base = _copy("base.json", where)
        head = _copy("head-pinned.json", where)
        out = where / "out"
        result = runner.invoke(app, _args(base, head, "--format", "json", "--out", str(out)))
        assert result.exit_code == 0, result.stderr
        outputs.append((out / "diff.json").read_bytes())
    assert outputs[0] == outputs[1]
    text = outputs[0].decode("utf-8")
    assert str(tmp_path) not in text
    assert "generated_at" not in text
    payload = json.loads(text)
    assert payload["schema"] == "nhi-blast-diff/1.0"
    assert payload["comparability"]["status"] == "comparable"
    assert payload["summary"]["counts"]["resolved"] == 1


def test_console_output_is_deterministic() -> None:
    first = runner.invoke(app, _args(DIFFS / "base.json", DIFFS / "head-pinned.json"))
    second = runner.invoke(app, _args(DIFFS / "base.json", DIFFS / "head-pinned.json"))
    assert first.stdout == second.stdout


def test_no_network_and_no_subprocess(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def blocked(*_a: object, **_k: object) -> None:
        msg = "diff attempted network or subprocess use"
        raise AssertionError(msg)

    for name in ("socket", "create_connection", "getaddrinfo", "socketpair"):
        monkeypatch.setattr(socket, name, blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)
    monkeypatch.setattr(subprocess, "run", blocked)
    result = runner.invoke(
        app,
        _args(
            DIFFS / "base.json",
            DIFFS / "head-pinned.json",
            "--format",
            "json",
            "--out",
            str(tmp_path),
        ),
    )
    assert result.exit_code == 0, result.stderr


def test_canary_secret_never_reaches_outputs(tmp_path: Path) -> None:
    base_data = json.loads((DIFFS / "base.json").read_text(encoding="utf-8"))
    head_data = json.loads((DIFFS / "base.json").read_text(encoding="utf-8"))
    for data in (base_data, head_data):
        finding = data["findings"][0]
        finding["title"] = f"leaks {CANARY}"
        finding["message"] = f"value {CANARY}"
        finding["evidence"][0]["detail"] = CANARY
        finding["path"][0] = finding["path"][0] + CANARY
        data["graph"]["nodes"][0]["label"] = CANARY
        data["diagnostics"] = [
            {"level": "warning", "code": "D-X", "file": f"{CANARY}.yml", "message": CANARY}
        ]
    head_data["findings"] = head_data["findings"][1:]
    base = tmp_path / "base.json"
    head = tmp_path / "head.json"
    base.write_text(json.dumps(base_data), encoding="utf-8")
    head.write_text(json.dumps(head_data), encoding="utf-8")
    out = tmp_path / "out"
    result = runner.invoke(
        app,
        _args(
            base,
            head,
            "--format",
            "console",
            "--format",
            "json",
            "--out",
            str(out),
            "--fail-on",
            "low",
        ),
    )
    assert result.exit_code in (0, 1), result.stderr
    assert CANARY not in result.stdout
    assert CANARY not in result.stderr
    assert CANARY not in (out / "diff.json").read_text(encoding="utf-8")
    assert "Canary98765" not in result.stdout + (out / "diff.json").read_text(encoding="utf-8")


def test_output_avoids_overclaiming_words() -> None:
    texts = [
        runner.invoke(app, _args(DIFFS / "base.json", DIFFS / "head-pinned.json")).stdout,
        runner.invoke(app, _args(DIFFS / "base-without-oidc.json", DIFFS / "base.json")).stdout,
    ]
    banned = re.compile(
        r"\b(proves?|proven|guarantee[sd]?|safe|fixed|exploitable|taken over)\b", re.I
    )
    for text in texts:
        assert banned.search(text) is None


def test_baseline_accept_then_diff_then_prune(tmp_path: Path) -> None:
    base = DIFFS / "base-without-oidc.json"
    head = DIFFS / "base.json"
    out = tmp_path / "out"
    gated = runner.invoke(
        app, _args(base, head, "--fail-on", "low", "--format", "json", "--out", str(out))
    )
    assert gated.exit_code == 1
    diff_json = out / "diff.json"
    lk = next(
        item["lk"]
        for item in json.loads(diff_json.read_text(encoding="utf-8"))["findings"]
        if item["class"] == "new"
    )
    baseline = tmp_path / "baseline.json"
    accepted = runner.invoke(
        app,
        [
            "baseline",
            "accept",
            lk,
            "--diff",
            str(diff_json),
            "--reason",
            "tracked in INC-7",
            "--reviewer",
            "alice",
            "--expires",
            "2030-01-01",
            "--baseline",
            str(baseline),
        ],
    )
    assert accepted.exit_code == 0, accepted.stderr
    saved = json.loads(baseline.read_text(encoding="utf-8"))
    assert saved["entries"][0]["lk"] == lk
    assert (
        saved["created_from_report_digest"]
        == json.loads(diff_json.read_text(encoding="utf-8"))["head"]["report_digest"]
    )

    suppressed = runner.invoke(
        app, _args(base, head, "--fail-on", "low", "--baseline", str(baseline))
    )
    assert suppressed.exit_code == 0, suppressed.stderr
    assert "baselined" in suppressed.stdout
    assert "NHB-OIDC-002" in suppressed.stdout
    expired = runner.invoke(
        app,
        _args(base, head, "--fail-on", "low", "--baseline", str(baseline), "--as-of", "2030-01-01"),
    )
    assert expired.exit_code == 1
    assert "D-DIFF-BASELINE-EXPIRED" in expired.stdout

    again = runner.invoke(
        app,
        [
            "baseline",
            "accept",
            lk,
            "--diff",
            str(diff_json),
            "--reason",
            "r",
            "--reviewer",
            "a",
            "--baseline",
            str(baseline),
        ],
    )
    assert again.exit_code == 2
    assert "already in the baseline" in again.stderr

    keep = runner.invoke(
        app, ["baseline", "prune", "--diff", str(diff_json), "--baseline", str(baseline)]
    )
    assert keep.exit_code == 0
    assert "0 removed" in keep.stdout

    reverse_out = tmp_path / "reverse"
    runner.invoke(app, _args(head, base, "--format", "json", "--out", str(reverse_out)))
    pruned = runner.invoke(
        app,
        [
            "baseline",
            "prune",
            "--diff",
            str(reverse_out / "diff.json"),
            "--baseline",
            str(baseline),
        ],
    )
    assert pruned.exit_code == 0, pruned.stderr
    assert "1 removed" in pruned.stdout
    assert json.loads(baseline.read_text(encoding="utf-8"))["entries"] == []


def test_baseline_accept_refuses_a_finding_that_is_not_new(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(
        app, _args(DIFFS / "base.json", DIFFS / "base.json", "--format", "json", "--out", str(out))
    )
    lk = json.loads((out / "diff.json").read_text(encoding="utf-8"))["findings"][0]["lk"]
    result = runner.invoke(
        app,
        [
            "baseline",
            "accept",
            lk,
            "--diff",
            str(out / "diff.json"),
            "--reason",
            "r",
            "--reviewer",
            "a",
            "--baseline",
            str(tmp_path / "b.json"),
        ],
    )
    assert result.exit_code == 2
    assert "only new findings" in result.stderr
    assert not (tmp_path / "b.json").exists()


def test_baseline_reason_is_redacted(tmp_path: Path) -> None:
    out = tmp_path / "out"
    runner.invoke(
        app,
        _args(
            DIFFS / "base-without-oidc.json",
            DIFFS / "base.json",
            "--format",
            "json",
            "--out",
            str(out),
        ),
    )
    diff_json = out / "diff.json"
    lk = next(
        i["lk"]
        for i in json.loads(diff_json.read_text(encoding="utf-8"))["findings"]
        if i["class"] == "new"
    )
    baseline = tmp_path / "b.json"
    result = runner.invoke(
        app,
        [
            "baseline",
            "accept",
            lk,
            "--diff",
            str(diff_json),
            "--reason",
            f"token {CANARY}",
            "--reviewer",
            "a",
            "--baseline",
            str(baseline),
        ],
    )
    assert result.exit_code == 0
    assert CANARY not in baseline.read_text(encoding="utf-8")


def test_baseline_files_and_diffs_with_wrong_shape_exit_two(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    for args in (
        ["baseline", "prune", "--diff", str(bad), "--baseline", str(bad)],
        [
            "baseline",
            "accept",
            "a" * 64,
            "--diff",
            str(bad),
            "--reason",
            "r",
            "--reviewer",
            "a",
            "--baseline",
            str(tmp_path / "x.json"),
        ],
        _args(DIFFS / "base.json", DIFFS / "base.json", "--baseline", str(bad)),
    ):
        result = runner.invoke(app, args)
        assert result.exit_code == 2, args
        assert result.stderr.startswith("error:")


def test_html_hook_accepts_a_registered_renderer(tmp_path: Path) -> None:
    register_renderer(
        Renderer("custom", "txt", lambda payload: "custom:" + payload["schema"] + "\n")
    )
    try:
        out = tmp_path / "out"
        result = runner.invoke(
            app,
            _args(
                DIFFS / "base.json", DIFFS / "base.json", "--format", "custom", "--out", str(out)
            ),
        )
        assert result.exit_code == 0, result.stderr
        assert (out / "diff.txt").read_text(encoding="utf-8") == "custom:nhi-blast-diff/1.0\n"
    finally:
        del RENDERERS["custom"]


def test_analyzer_regression_through_the_cli_is_not_a_resolved_finding(tmp_path: Path) -> None:
    head = save_report(
        with_analyzer(without_rule(base_report(), "NHB-GHA-001"), engine_semantics="99"),
        tmp_path / "head.json",
    )
    result = runner.invoke(app, _args(DIFFS / "base.json", head, "--fail-on", "low"))
    assert result.exit_code == 0
    assert "No longer observed" not in result.stdout
    assert "analyzer_changed" in result.stdout
    assert "resolved=0" in result.stdout
