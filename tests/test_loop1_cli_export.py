"""Loop 1 verification tests: CLI, config, pipeline, OpenGraph v9.0.0, SARIF, and Action."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from nhi_blast.cli.app import app
from nhi_blast.core.config import Config, ConfigError
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.models import (
    Edge,
    EdgeKind,
    Finding,
    GraphData,
    Inputs,
    Lifetime,
    Node,
    NodeKind,
    Severity,
    ToolInfo,
)
from nhi_blast.pipeline import ExportOptions, UsageError, run_export
from nhi_blast.report.graph_export import graph_export_opengraph
from nhi_blast.report.sarif import _code_flow, _fingerprint

FX07 = Path("tests/fixtures/fx07-incident")
ACTION_YML = Path("action/action.yml")


# --------------------------------------------------------------------------- CLI & pipeline


def test_init_config_is_valid_toml_and_round_trips_scan(tmp_path: Path) -> None:
    runner = CliRunner()
    res = runner.invoke(app, ["init", str(tmp_path)])
    assert res.exit_code == 0, res.output

    cfg_path = tmp_path / "nhi-blast.toml"
    text = cfg_path.read_text(encoding="utf-8")
    assert 'repo_slug = "OWNER/REPO"' in text
    assert 'default_branch = "main"' in text
    assert "[repo]" not in text
    assert "https://github.com/DKtech-dev/nhi-blast#configuration" in text

    parsed = Config.from_file(cfg_path)
    assert parsed.repo_slug == "OWNER/REPO"
    assert parsed.default_branch == "main"

    scan_res = runner.invoke(app, ["scan", str(tmp_path)])
    assert scan_res.exit_code == 0, scan_res.output


def test_export_defaults_to_json_and_mentions_opengraph_in_help_and_error(tmp_path: Path) -> None:
    runner = CliRunner()
    help_res = runner.invoke(app, ["export", "--help"])
    assert help_res.exit_code == 0
    assert "JSON, Graphviz DOT, or BloodHound OpenGraph" in help_res.output

    out_dir = tmp_path / "export-default"
    res = runner.invoke(app, ["export", str(FX07), "--out", str(out_dir)])
    assert res.exit_code == 0, res.output
    assert (out_dir / "graph.json").is_file()

    with pytest.raises(UsageError, match=r"choose json, dot or opengraph"):
        run_export(ExportOptions(root=FX07, fmt="xml", out_dir=tmp_path / "bad"))


# --------------------------------------------------------------------------- whatif_cmd


def test_whatif_catches_unexpected_exception_and_guards_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sentinel = "SUPER_SECRET_INTERNAL_TOKEN"

    def explode(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError(sentinel)

    monkeypatch.setattr("nhi_blast.cli.whatif_cmd.execute", explode)
    runner = CliRunner()
    res = runner.invoke(app, ["whatif", str(tmp_path / "report.json")])
    assert res.exit_code == 4
    combined = res.stdout + res.stderr
    assert "error: internal error: RuntimeError" in combined
    assert sentinel not in combined
    assert "Traceback" not in combined

    def empty_written(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return SimpleNamespace(console_text="Done\n", written=())

    monkeypatch.setattr("nhi_blast.cli.whatif_cmd.execute", empty_written)
    res_empty = runner.invoke(app, ["whatif", str(tmp_path / "report.json")])
    assert res_empty.exit_code == 0
    assert "Done" in res_empty.stdout
    assert "Written:" not in res_empty.stdout

    out_file = tmp_path / "whatif.json"

    def with_written(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return SimpleNamespace(console_text="Done\n", written=(out_file,))

    monkeypatch.setattr("nhi_blast.cli.whatif_cmd.execute", with_written)
    res_written = runner.invoke(app, ["whatif", str(tmp_path / "report.json")])
    assert res_written.exit_code == 0
    assert "Written:" in res_written.stdout
    assert out_file.as_posix() in res_written.stdout


# --------------------------------------------------------------------------- config


@pytest.mark.parametrize(
    ("section", "bad_value"),
    [
        ("bindings", False),
        ("bindings", []),
        ("oidc", ""),
        ("oidc", 0),
        ("ignore", []),
        ("ignore", False),
        ("limits", 0),
        ("limits", ""),
    ],
)
def test_config_rejects_falsy_non_table_sections(section: str, bad_value: object) -> None:
    with pytest.raises(ConfigError, match="must be a table"):
        Config.from_mapping({section: bad_value})


def test_config_with_identity_preserves_empty_string_overrides() -> None:
    base = Config(
        repo_slug="acme/shop",
        default_branch="main",
        aws_account="123456789012",
        aws_region="us-east-1",
    )
    unchanged = base.with_identity()
    assert unchanged == base

    cleared = base.with_identity(
        repo_slug="",
        default_branch="",
        aws_account="",
        aws_region="",
    )
    assert cleared.repo_slug == ""
    assert cleared.default_branch == ""
    assert cleared.aws_account == ""
    assert cleared.aws_region == ""


# --------------------------------------------------------------------------- OpenGraph v9.0.0


def test_opengraph_v9_strict_metadata_env_node_id_sanitization_and_properties() -> None:
    ev = (
        Evidence(
            cls=EvidenceClass.DECLARED,
            rule="test",
            file=".github/workflows/ci.yml",
            line=1,
        ),
    )
    n1 = Node(
        id="job:ci:build",
        kind=NodeKind.JOB,
        label="Build Job",
        attrs={
            "ObjectID": "should-be-stripped",
            "lastseen": 123,
            "RECONCILE": True,
            "MixedCaseKey": "ok",
            "Tags": ["a", "b"],
            "Nums": (1, 2, 3),
            "Flags": [True, False],
            "Floats": [1.25, 2.5],
            "Hetero": [1, "two"],
            "BoolIntMix": [True, 1],
            "Nested": {"k": "v"},
        },
        evidence=ev,
    )
    # Intentionally collides with n1 after ":" -> "_"
    n2 = Node(
        id="job_ci_build",
        kind=NodeKind.JOB,
        label="Colliding Job",
        attrs={"name": "cannot-overwrite-core"},
        evidence=ev,
    )
    edge = Edge(
        id="edge:1",
        kind=EdgeKind.RUNS_IN,
        src=n1.id,
        dst=n2.id,
        confidence=EvidenceClass.DECLARED,
        lifetime=Lifetime.JOB_BOUND,
        evidence=ev,
    )
    digest = "abcdef0123456789fedcba9876543210"
    raw = graph_export_opengraph(
        tool=ToolInfo(version="0.3.0"),
        inputs=Inputs(digest=digest, repo_slug="acme/shop", repo_slug_source="cli", files=()),
        graph=GraphData(nodes=(n1, n2), edges=(edge,)),
        generated_at="2026-01-01T00:00:00Z",
    )
    data = json.loads(raw)

    assert data["metadata"] == {"source_kind": "NHI_Blast"}

    nodes = data["graph"]["nodes"]
    assert len(nodes) == 3

    env_node = nodes[0]
    assert env_node["id"] == f"nhi_env_{digest[:12]}"
    assert env_node["kinds"] == ["NHI_Environment"]
    assert env_node["properties"]["tool_version"] == "0.3.0"
    assert env_node["properties"]["repository"] == "acme/shop"
    assert env_node["properties"]["inputs_digest"] == digest
    assert env_node["properties"]["generated_at"] == "2026-01-01T00:00:00Z"

    by_orig = {n["properties"]["nhi_id"]: n for n in nodes[1:]}
    assert set(by_orig) == {"job:ci:build", "job_ci_build"}
    assert by_orig["job:ci:build"]["id"] != by_orig["job_ci_build"]["id"]
    for node in nodes:
        assert ":" not in node["id"]

    p1 = by_orig["job:ci:build"]["properties"]
    assert p1["nhi_id"] == "job:ci:build"
    assert p1["mixedcasekey"] == "ok"
    assert p1["tags"] == ["a", "b"]
    assert p1["nums"] == [1, 2, 3]
    assert p1["flags"] == [True, False]
    assert p1["floats"] == [1.25, 2.5]
    assert "hetero" not in p1
    assert "boolintmix" not in p1
    assert "nested" not in p1
    for reserved in ("objectid", "lastseen", "reconcile"):
        assert reserved not in p1

    p2 = by_orig["job_ci_build"]["properties"]
    assert p2["name"] == "Colliding Job"

    og_edge = data["graph"]["edges"][0]
    assert ":" not in og_edge["start"]["value"]
    assert ":" not in og_edge["end"]["value"]
    assert og_edge["start"]["value"] == by_orig["job:ci:build"]["id"]
    assert og_edge["end"]["value"] == by_orig["job_ci_build"]["id"]


# --------------------------------------------------------------------------- SARIF


def test_sarif_fingerprint_disambiguates_empty_path_findings() -> None:
    f_line10 = Finding(
        id="NHB-GHA-001-a",
        rule="NHB-GHA-001",
        severity=Severity.HIGH,
        confidence=EvidenceClass.DECLARED,
        title="Unpinned action",
        message="Unpinned action at line 10",
        path=(),
        evidence=(
            Evidence(
                cls=EvidenceClass.DECLARED,
                rule="NHB-GHA-001",
                file=".github/workflows/ci.yml",
                line=10,
            ),
        ),
    )
    f_line25 = f_line10.model_copy(
        update={
            "id": "NHB-GHA-001-b",
            "evidence": (f_line10.evidence[0].model_copy(update={"line": 25}),),
        }
    )
    assert _fingerprint(f_line10) != _fingerprint(f_line25)

    f_noline_a = f_line10.model_copy(
        update={
            "id": "NHB-GHA-001-c",
            "evidence": (f_line10.evidence[0].model_copy(update={"line": None}),),
        }
    )
    f_noline_b = f_noline_a.model_copy(update={"id": "NHB-GHA-001-d"})
    assert _fingerprint(f_noline_a) != _fingerprint(f_noline_b)


def test_sarif_code_flow_allows_file_without_line_and_prefers_line_when_present() -> None:
    edge_no_line = Edge(
        id="e-noline",
        kind=EdgeKind.CAN_ASSUME,
        src="job:a",
        dst="role:b",
        confidence=EvidenceClass.DECLARED,
        lifetime=Lifetime.SESSION_TTL,
        attrs={"message": "assumes role"},
        evidence=(
            Evidence(
                cls=EvidenceClass.DECLARED,
                rule="test",
                file="terraform/iam.tf",
                line=None,
            ),
        ),
    )
    edge_mixed = Edge(
        id="e-mixed",
        kind=EdgeKind.CAN_ASSUME,
        src="job:a",
        dst="role:c",
        confidence=EvidenceClass.DECLARED,
        lifetime=Lifetime.SESSION_TTL,
        attrs={"message": "assumes role with line"},
        evidence=(
            Evidence(cls=EvidenceClass.DECLARED, rule="test", file="a.tf", line=None),
            Evidence(cls=EvidenceClass.DECLARED, rule="test", file="b.tf", line=42),
        ),
    )
    finding = Finding(
        id="NHB-OIDC-001-1",
        rule="NHB-OIDC-001",
        severity=Severity.HIGH,
        confidence=EvidenceClass.DECLARED,
        title="Wildcard trust",
        message="Wildcard trust",
        path=("job:a", "role:b"),
        path_edges=("e-noline", "e-mixed"),
    )
    flow = _code_flow(finding, {"e-noline": edge_no_line, "e-mixed": edge_mixed})
    assert flow is not None
    locs = flow["threadFlows"][0]["locations"]
    assert len(locs) == 2

    first_phys = locs[0]["location"]["physicalLocation"]
    assert first_phys["artifactLocation"]["uri"] == "terraform/iam.tf"
    assert "region" not in first_phys

    second_phys = locs[1]["location"]["physicalLocation"]
    assert second_phys["artifactLocation"]["uri"] == "b.tf"
    assert second_phys["region"]["startLine"] == 42


# --------------------------------------------------------------------------- action/action.yml


def _find_bash() -> str:
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Git" / "bin" / "bash.exe",
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            / "Git"
            / "usr"
            / "bin"
            / "bash.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Git"
            / "bin"
            / "bash.exe",
        ]
        git_exe = shutil.which("git")
        if git_exe:
            candidates.append(Path(git_exe).resolve().parent.parent / "bin" / "bash.exe")
        for cand in candidates:
            if cand.is_file():
                return str(cand)
        found = shutil.which("bash")
        if not found or "system32" in found.lower():
            pytest.skip("Git Bash not available on Windows runner")
        return found
    return shutil.which("bash") or "bash"


def _run_action_script(tmp_path: Path, env_overrides: dict[str, str]) -> tuple[int, str, list[str]]:
    data = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    run_step = next(step for step in data["runs"]["steps"] if step.get("name") == "Run nhi-blast")
    script = run_step["run"]

    tmp_path.mkdir(parents=True, exist_ok=True)
    log_file = tmp_path / "calls.log"
    summary_file = tmp_path / "summary.md"
    wrapper = 'nhi-blast() { printf "%s\\n" "$*" >> "$NHB_TEST_LOG"; }\n' + script
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NHB_", "GITHUB_"))}
    env.update(
        {
            "NHB_TEST_LOG": log_file.as_posix(),
            "GITHUB_STEP_SUMMARY": summary_file.as_posix(),
            "NHB_MODE": "scan",
            "NHB_PATH": ".",
            "NHB_REPO": "acme/shop",
            "NHB_OUT": (tmp_path / "out").as_posix(),
            "NHB_FAIL_ON": "high",
            "NHB_BASE": "",
            "NHB_SIMULATE": "",
            **env_overrides,
        }
    )
    completed = subprocess.run(
        [_find_bash(), "-c", wrapper],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log_file.read_text(encoding="utf-8").splitlines() if log_file.exists() else []
    return completed.returncode, completed.stderr, calls


def test_action_yml_scan_fail_on_simulate_and_diff_base_validation(tmp_path: Path) -> None:
    data = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    assert "simulate-compromise" in data["inputs"]

    # scan mode with fail-on=high and simulate-compromise
    rc1, err1, calls1 = _run_action_script(
        tmp_path / "t1",
        {"NHB_MODE": "scan", "NHB_FAIL_ON": "high", "NHB_SIMULATE": "repo-write"},
    )
    assert rc1 == 0, err1
    assert len(calls1) == 1
    assert "--fail-on high" in calls1[0]
    assert "--simulate-compromise repo-write" in calls1[0]

    # scan mode with fail-on=never omits --fail-on
    rc2, err2, calls2 = _run_action_script(
        tmp_path / "t2",
        {"NHB_MODE": "scan", "NHB_FAIL_ON": "never", "NHB_SIMULATE": ""},
    )
    assert rc2 == 0, err2
    assert len(calls2) == 1
    assert "--fail-on" not in calls2[0]
    assert "--simulate-compromise" not in calls2[0]

    # diff mode with empty base-report fails clearly
    rc3, err3, calls3 = _run_action_script(
        tmp_path / "t3",
        {"NHB_MODE": "diff", "NHB_BASE": ""},
    )
    assert rc3 != 0
    assert "base-report" in err3
    assert calls3 == []

    # diff mode with base-report runs scan + diff
    rc4, err4, calls4 = _run_action_script(
        tmp_path / "t4",
        {"NHB_MODE": "diff", "NHB_BASE": "base.json", "NHB_FAIL_ON": "critical"},
    )
    assert rc4 == 0, err4
    assert len(calls4) == 2
    assert calls4[0].startswith("scan ")
    assert calls4[1].startswith("diff base.json ")
    assert "--fail-on critical" in calls4[1]
