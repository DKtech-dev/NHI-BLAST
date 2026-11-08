"""CLI contract, plan loading, offline guarantees, determinism and output hygiene."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from nhi_blast.cli.whatif_cmd import whatif
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.models import Node, NodeKind
from nhi_blast.whatif.plan import PlanError, load_plan, parse_plan_text
from nhi_blast.whatif.playbook import _evidence_lines
from tests.test_whatif_support import (
    DB_PASSWORD,
    DEPLOY_KEY,
    FORBIDDEN,
    FX16,
    GOLDEN,
    ROLE,
    SESSION,
    disable_job,
    fx16_report,
    remove_oidc_trust,
    revoke,
    rotate,
    save,
    scan,
    sha,
    write_plan,
)

app = typer.Typer()
app.command("whatif")(whatif)


@app.command("noop")
def _noop() -> None:
    """Keeps typer in multi-command mode so that the subcommand name is required."""


runner = CliRunner()
CANARY = "ghp_" + "Q" * 36
FULL_PLAN = GOLDEN / "fx16-plan-full.json"
REVOKE_PLAN = GOLDEN / "fx16-plan-revoke.yaml"


def invoke(report: Path, plan: Path, out: Path, *extra: str) -> Any:
    return runner.invoke(
        app, ["whatif", str(report), "--plan", str(plan), "--out", str(out), *extra]
    )


@pytest.fixture(scope="module")
def report_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return save(fx16_report(), tmp_path_factory.mktemp("report") / "report.json")


def test_cli_writes_json_and_playbook_and_prints_a_summary(
    report_file: Path, tmp_path: Path
) -> None:
    result = invoke(report_file, FULL_PLAN, tmp_path / "out")
    assert result.exit_code == 0, result.stderr
    assert result.stdout.startswith("Offline model. Not executed. Verify in your account.")
    assert (tmp_path / "out" / "whatif.json").is_file()
    assert (tmp_path / "out" / "playbook.md").is_file()
    document = json.loads((tmp_path / "out" / "whatif.json").read_text(encoding="utf-8"))
    assert document["schema"] == "nhi-blast-whatif/1.0"
    assert set(document) == {
        "caveats",
        "header",
        "per_scenario",
        "plan_digest",
        "rejected",
        "schema",
        "source_report_digest",
        "steps",
        "warnings",
    }
    assert "generated_at" not in json.dumps(document)


def test_cli_format_selection_and_validation(report_file: Path, tmp_path: Path) -> None:
    only_json = tmp_path / "json"
    assert invoke(report_file, FULL_PLAN, only_json, "--format", "json").exit_code == 0
    assert sorted(path.name for path in only_json.iterdir()) == ["whatif.json"]
    only_md = tmp_path / "md"
    assert invoke(report_file, FULL_PLAN, only_md, "--format", "md").exit_code == 0
    assert sorted(path.name for path in only_md.iterdir()) == ["playbook.md"]
    bad = invoke(report_file, FULL_PLAN, tmp_path / "html", "--format", "html")
    assert bad.exit_code == 2
    assert "D-WHATIF-USAGE" in bad.stderr
    assert not (tmp_path / "html").exists()


def test_source_report_is_never_modified(report_file: Path, tmp_path: Path) -> None:
    before = sha(report_file)
    stamp = report_file.stat().st_mtime_ns
    assert invoke(report_file, FULL_PLAN, tmp_path / "out").exit_code == 0
    assert invoke(report_file, REVOKE_PLAN, tmp_path / "out2").exit_code == 0
    assert sha(report_file) == before
    assert report_file.stat().st_mtime_ns == stamp


def test_output_that_would_replace_the_report_is_refused(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    report = save(fx16_report(), out / "whatif.json")
    before = sha(report)
    result = invoke(report, FULL_PLAN, out, "--format", "json")
    assert result.exit_code == 4
    assert "D-WHATIF-OUTPUT" in result.stderr
    assert sha(report) == before


def test_missing_or_invalid_inputs_exit_2_without_output(report_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert invoke(tmp_path / "missing.json", FULL_PLAN, out).exit_code == 2
    assert invoke(report_file, tmp_path / "missing.json", out).exit_code == 2
    junk = tmp_path / "junk.json"
    junk.write_text("{not json", encoding="utf-8")
    assert invoke(junk, FULL_PLAN, out).exit_code == 2
    bad_plan = tmp_path / "plan.json"
    bad_plan.write_text('{"schema": "nope"}', encoding="utf-8")
    result = invoke(report_file, bad_plan, out)
    assert result.exit_code == 2
    assert "D-WHATIF-PLAN-INVALID" in result.stderr
    assert not out.exists()


def test_outputs_are_byte_identical_across_runs(report_file: Path, tmp_path: Path) -> None:
    for plan in (FULL_PLAN, REVOKE_PLAN):
        first, second = tmp_path / "a", tmp_path / "b"
        assert invoke(report_file, plan, first).exit_code == 0
        assert invoke(report_file, plan, second).exit_code == 0
        for name in ("whatif.json", "playbook.md"):
            assert (first / name).read_bytes() == (second / name).read_bytes()
        shutil.rmtree(first)
        shutil.rmtree(second)


def test_outputs_are_identical_from_two_checkout_locations(tmp_path: Path) -> None:
    shallow = tmp_path / "a"
    deep = tmp_path / "very" / "deep nested" / "tmp-é" / "checkout"
    for destination in (shallow, deep):
        shutil.copytree(FX16, destination)
    results = []
    for index, root in enumerate((shallow, deep)):
        report = scan(root)
        path = save(report, tmp_path / f"report-{index}.json")
        out = tmp_path / f"out-{index}"
        assert invoke(path, FULL_PLAN, out).exit_code == 0
        results.append({name: (out / name).read_bytes() for name in ("whatif.json", "playbook.md")})
        assert str(root).encode() not in results[-1]["whatif.json"]
    assert results[0] == results[1]
    joined = results[0]["whatif.json"] + results[0]["playbook.md"]
    assert b"pytest-of" not in joined
    assert tmp_path.name.encode() not in joined
    assert "tmp-é".encode() not in joined


def test_runtime_makes_no_network_or_subprocess_calls(
    report_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        message = "what-if attempted a forbidden call"
        raise AssertionError(message)

    for owner, name in (
        (socket, "socket"),
        (socket, "create_connection"),
        (socket, "getaddrinfo"),
        (socket, "socketpair"),
        (subprocess, "Popen"),
        (subprocess, "run"),
        (os, "system"),
        (os, "popen"),
    ):
        monkeypatch.setattr(owner, name, blocked)
    result = invoke(report_file, FULL_PLAN, tmp_path / "out")
    assert result.exit_code == 0, result.stderr


def test_outputs_contain_no_forbidden_language(report_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = invoke(report_file, FULL_PLAN, out)
    texts = [result.stdout, *(path.read_text(encoding="utf-8") for path in out.iterdir())]
    for text in texts:
        assert FORBIDDEN.search(text) is None, FORBIDDEN.search(text)
    document = json.loads((out / "whatif.json").read_text(encoding="utf-8"))
    states = [row for item in document["per_scenario"] for row in item["after"]["revoked_access"]]
    expired_allowed = any(row["validity"] == "expired" for row in states)
    for text in texts:
        if re.search(r"\bexpired\b", text):
            assert expired_allowed


def test_the_word_expired_appears_only_with_validity_expired(tmp_path: Path) -> None:
    report = save(fx16_report(), tmp_path / "report.json")
    plan = write_plan(
        tmp_path / "plan.json",
        revoke(revoked_at="2026-03-01T10:00:00Z", assessed_at="2026-03-01T10:05:00Z"),
        remove_oidc_trust(),
        rotate(DEPLOY_KEY),
    )
    out = tmp_path / "out"
    result = invoke(report, plan, out)
    for text in (result.stdout, *(path.read_text(encoding="utf-8") for path in out.iterdir())):
        assert re.search(r"\bexpired\b", text) is None
    expired_plan = write_plan(
        tmp_path / "plan2.json",
        revoke(
            revoked_at="2026-03-01T10:00:00Z",
            assessed_at="2026-03-01T12:00:00Z",
            issued_no_later_than={SESSION: "2026-03-01T09:30:00Z"},
        ),
    )
    out2 = tmp_path / "out2"
    invoke(report, expired_plan, out2)
    document = json.loads((out2 / "whatif.json").read_text(encoding="utf-8"))
    rows = [row for item in document["per_scenario"] for row in item["after"]["revoked_access"]]
    assert rows
    assert all(row["validity"] == "expired" and row["display_state"] == "expired" for row in rows)


@pytest.mark.security
def test_a_credential_literal_never_reaches_any_output(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FX16, root)
    config = root / "nhi-blast.toml"
    config.write_text(
        config.read_text(encoding="utf-8") + f'\n[bindings.roles]\nci = "{CANARY}"\n',
        encoding="utf-8",
    )
    report = scan(root)
    report_path = save(report, tmp_path / "report.json")
    assert CANARY not in report_path.read_text(encoding="utf-8")
    plan = write_plan(
        tmp_path / "plan.json",
        {"type": CANARY},
        {"type": "disable_entrypoint", "node": CANARY},
        {"type": "rotate_credential", "credential": f"cred:{CANARY}"},
        revoke(revoked_at="2026-03-01T10:00:00Z"),
        remove_oidc_trust(),
    )
    out = tmp_path / "out"
    result = invoke(report_path, plan, out)
    assert result.exit_code == 0, result.stderr
    everything = (
        result.stdout
        + result.stderr
        + "".join(path.read_text(encoding="utf-8") for path in out.iterdir())
    )
    assert CANARY not in everything
    assert "ghp_" + "Q" * 8 not in everything
    document = json.loads((out / "whatif.json").read_text(encoding="utf-8"))
    assert document["rejected"]


def test_playbook_structure_and_placeholders(report_file: Path, tmp_path: Path) -> None:
    invoke(report_file, FULL_PLAN, tmp_path)
    text = (tmp_path / "playbook.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "Offline model. Not executed. Verify in your account."
    headings = [line for line in lines if line.startswith("## ")]
    assert headings[:4] == [
        "## 1. Revoke role sessions",
        "## 2. Remove trust or disable entrypoint",
        "## 3. Rotate surviving credentials in dependency order",
        "## 4. Verify",
    ]
    assert text.count("- Owner: `<owner: assign a person or team>`") >= 8
    for marker in ("- Human verification task:", "- Rollback / validation:", "- Evidence ("):
        assert marker in text
    assert text.count("- Evidence (") >= 4
    scenario_block = text.split("### Scenario `action:acme/build-helper@v1`")[1]
    first = scenario_block.index(DEPLOY_KEY)
    assert first < scenario_block.index(DB_PASSWORD)
    assert "Rejected plan entries" in text


def test_playbook_never_prints_an_absolute_evidence_path() -> None:
    node = Node(
        id="n",
        kind=NodeKind.JOB,
        label="n",
        evidence=(
            Evidence(
                cls=EvidenceClass.DECLARED, rule="X", file="C:\\Users\\someone\\a.toml", line=3
            ),
            Evidence(cls=EvidenceClass.DECLARED, rule="Y", file="/home/someone/b.toml", line=4),
        ),
    )
    text = "\n".join(_evidence_lines(node, "Evidence"))
    assert "someone" not in text
    assert "a.toml (absolute path omitted)" in text
    assert "b.toml (absolute path omitted)" in text


# ------------------------------------------------------------------ plan loading


def test_json_and_yaml_plans_give_the_same_document(tmp_path: Path) -> None:
    as_json = write_plan(tmp_path / "plan.json", rotate(DEPLOY_KEY), disable_job())
    as_yaml = tmp_path / "plan.yaml"
    as_yaml.write_text(
        "schema: nhi-blast-interventions/1.0\ninterventions:\n"
        f"  - {{type: rotate_credential, credential: '{DEPLOY_KEY}'}}\n"
        "  - type: disable_entrypoint\n"
        "    node: 'job:.github/workflows/deploy.yml#deploy'\n",
        encoding="utf-8",
    )
    assert load_plan(as_json).digest == load_plan(as_yaml).digest
    assert load_plan(REVOKE_PLAN).entries[0].type == "revoke_role_sessions"


HOSTILE_PLANS: dict[str, tuple[str, str]] = {
    "json-duplicate-key": (
        "plan.json",
        '{"schema": "nhi-blast-interventions/1.0", "interventions": [], "interventions": []}',
    ),
    "json-deep-nesting": ("plan.json", "[" * 100000),
    "json-bom": ("plan.json", "\ufeff{"),
    "yaml-duplicate-key": ("plan.yaml", "schema: x\nschema: y\n"),
    "yaml-python-tag": ("plan.yaml", "!!python/object/apply:os.system ['echo hi']\n"),
    "yaml-alias-fanout": (
        "plan.yaml",
        "a: &a [x, x, x, x, x, x, x, x, x, x, x, x]\n"
        "b: [*a, *a, *a, *a, *a, *a, *a, *a, *a, *a, *a, *a]\n",
    ),
    "yaml-deep-nesting": ("plan.yaml", "- " * 100 + "x\n"),
    "yaml-empty": ("plan.yaml", ""),
    "yaml-truncated": ("plan.yaml", "schema: nhi-blast-interventions/1.0\ninterventions: ["),
    "unsupported-extension": ("plan.txt", "{}"),
}


@pytest.mark.parametrize("case", sorted(HOSTILE_PLANS))
def test_hostile_or_malformed_plans_are_refused(tmp_path: Path, case: str) -> None:
    name, text = HOSTILE_PLANS[case]
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PlanError):
        load_plan(path)


def test_alias_bombs_are_refused_before_expansion() -> None:
    bomb = "a: &a [x, x, x, x, x, x, x, x, x, x]\n" + "".join(
        f"{chr(98 + index)}: &{chr(98 + index)} [{', '.join(['*' + chr(97 + index)] * 10)}]\n"
        for index in range(8)
    )
    with pytest.raises(PlanError):
        parse_plan_text(bomb, suffix=".yaml")


def test_oversized_and_non_utf8_plans_are_refused(tmp_path: Path) -> None:
    big = tmp_path / "big.json"
    big.write_text('{"schema": "' + "x" * (1024 * 1024 + 10) + '"}', encoding="utf-8")
    with pytest.raises(PlanError, match="byte limit"):
        load_plan(big)
    binary = tmp_path / "bin.json"
    binary.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(PlanError):
        load_plan(binary)
    with pytest.raises(PlanError):
        load_plan(tmp_path / "absent.json")
    with pytest.raises(PlanError):
        load_plan(tmp_path)


def test_a_plan_symlink_that_leaves_its_directory_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    inside = tmp_path / "inside"
    outside.mkdir()
    inside.mkdir()
    target = write_plan(outside / "plan.json", rotate(DEPLOY_KEY))
    link = inside / "plan.json"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available")
    with pytest.raises(PlanError):
        load_plan(link)


def test_timestamps_in_yaml_plans_stay_strings(tmp_path: Path) -> None:
    path = tmp_path / "plan.yaml"
    path.write_text(
        "schema: nhi-blast-interventions/1.0\ninterventions:\n"
        f"  - type: revoke_role_sessions\n    role: '{ROLE}'\n"
        "    revoked_at: 2026-03-01T10:00:00Z\n",
        encoding="utf-8",
    )
    entry = load_plan(path).entries[0]
    assert entry.rejection is None
    assert entry.intervention is not None
