"""End-to-end pipeline behaviour (M6)."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nhi_blast import SCHEMA_VERSION
from nhi_blast.core.models import DataFileInfo, Severity
from nhi_blast.pipeline import (
    ExportOptions,
    OutputError,
    RankOptions,
    ScanOptions,
    SourceOptions,
    UsageError,
    load_repository,
    parse_fail_on,
    run_export,
    run_rank,
    run_scan,
)
from nhi_blast.report.explain import ExplainError, load_report, render_explanation
from nhi_blast.report.graph_export import GRAPH_SCHEMA

FIXTURES = Path(__file__).parent / "fixtures"
FX03 = FIXTURES / "fx03-wildcard-trust"
FX07 = FIXTURES / "fx07-incident"
FX10 = FIXTURES / "fx10-hcl-fallback"
ACTION = "action:tj-actions/changed-files@v45"

MALFORMED_WORKFLOW = """name: broken
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps: [
"""


def _write_workflow(root: Path, text: str, name: str = "ci.yml") -> Path:
    path = root / ".github" / "workflows" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _malformed_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _write_workflow(root, MALFORMED_WORKFLOW)
    return root


def test_role_compromise_session_is_in_serialized_report_graph(tmp_path: Path) -> None:
    resource = {
        "address": "aws_iam_role.deploy",
        "type": "aws_iam_role",
        "values": {
            "name": "deploy",
            "arn": "arn:aws:iam::111122223333:role/deploy",
            "max_session_duration": 7200,
            "assume_role_policy": '{"Version":"2012-10-17","Statement":[]}',
        },
    }
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "format_version": "1.0",
                "terraform_version": "1.9.8",
                "values": {"root_module": {"resources": [resource]}},
            }
        ),
        encoding="utf-8",
    )
    outcome = run_scan(
        ScanOptions(
            root=tmp_path,
            selectors=("role:aws_iam_role.deploy",),
            formats=("json", "sarif", "html"),
            out_dir=tmp_path / "out",
        )
    )
    report = json.loads((tmp_path / "out/report.json").read_text(encoding="utf-8"))
    scenario = report["scenarios"][0]
    assert len(scenario["partition"]["E"]) == 1
    session = scenario["partition"]["E"][0]
    assert session["ttl_seconds"] == 7200
    nodes = {node["id"]: node for node in report["graph"]["nodes"]}
    assert session["credential"] in nodes
    assert nodes[session["credential"]]["attrs"]["credential_kind"] == "STS_SESSION"
    assert "A-STS-TTL" in {item["id"] for item in report["assumptions"]}
    assert outcome.exit_code == 0


def test_scenario_findings_use_one_local_path_and_serialized_edge_references() -> None:
    report = run_scan(
        ScanOptions(root=FIXTURES / "fx11-rotation-cycle", selectors=("repo-write",))
    ).report
    assert len([item for item in report.findings if item.rule == "NHB-SURV-001"]) == 1
    rotation = [item for item in report.findings if item.rule == "NHB-ROT-001"]
    assert len(rotation) == 3
    assert len({item.path[-1] for item in rotation}) == 3
    edges = {edge.id for edge in report.graph.edges}
    assert all(set(item.path_edges) <= edges for item in report.findings)
    nodes = {node.id for node in report.graph.nodes}
    assert all(item.credential in nodes for item in report.scenarios[0].partition.E)


# ----------------------------------------------------------------- repository load


def test_load_fx07_reads_identity_inputs_and_counts() -> None:
    parsed = load_repository(SourceOptions(root=FX07))

    assert parsed.identity.slug == "acme/shop"
    assert parsed.identity.source == ".git/config"
    assert [item.path for item in parsed.workflows] == [
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    ]
    assert len(parsed.expanded_jobs) == 2
    assert len(parsed.tf_models) == 1
    assert [(item.path, item.kind) for item in parsed.inputs.files] == [
        (".git/config", "git_config"),
        (".github/workflows/ci.yml", "workflow"),
        (".github/workflows/release.yml", "workflow"),
        ("tfstate.json", "tf_json"),
    ]
    assert len(parsed.inputs.digest) == 64
    assert parsed.inputs.repo_slug == "acme/shop"
    assert parsed.inputs.repo_slug_source == ".git/config"
    assert not [item for item in parsed.diagnostics if item.level.value == "error"]


def test_identity_precedence_controls_config_inputs(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "config").write_text(
        '[remote "origin"]\n    url = git@github.com:git/from-git.git\n',
        encoding="utf-8",
    )
    (root / "nhi-blast.toml").write_text("repo_slug = 'cfg/from-config'\n", encoding="utf-8")

    from_config = load_repository(SourceOptions(root=root))
    assert from_config.identity.slug == "cfg/from-config"
    assert from_config.identity.source == "nhi-blast.toml"
    assert [item.path for item in from_config.inputs.files] == ["nhi-blast.toml"]

    from_cli = load_repository(SourceOptions(root=root, repo_slug="cli/override"))
    assert from_cli.identity.slug == "cli/override"
    assert from_cli.identity.source == "--repo-slug"
    assert [item.path for item in from_cli.inputs.files] == ["nhi-blast.toml"]

    (root / "nhi-blast.toml").unlink()
    from_git = load_repository(SourceOptions(root=root))
    assert from_git.identity.slug == "git/from-git"
    assert from_git.identity.source == ".git/config"
    assert [item.path for item in from_git.inputs.files] == [".git/config"]


def test_hcl_fallback_auto_and_override() -> None:
    auto = load_repository(SourceOptions(root=FX10))
    assert len(auto.tf_models) == 1
    assert any(item.path.endswith(".tf") for item in auto.inputs.files)

    disabled = load_repository(SourceOptions(root=FX10, tf_hcl=False))
    assert disabled.tf_models == ()
    assert not any(item.path.endswith(".tf") for item in disabled.inputs.files)

    with_json = load_repository(SourceOptions(root=FX07))
    assert not any(item.path.endswith(".tf") for item in with_json.inputs.files)
    forced = load_repository(SourceOptions(root=FX07, tf_hcl=True))
    assert any(item.path == "main.tf" for item in forced.inputs.files)
    assert len(forced.tf_models) == 2


def test_tf_json_configuration_is_discovered_without_parse_errors(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write_workflow(root, "name: ci\non: push\njobs: {}\n")
    (root / "main.tf.json").write_text(
        json.dumps(
            {
                "resource": {
                    "aws_iam_role": {
                        "deploy": {
                            "name": "deploy",
                            "assume_role_policy": json.dumps(
                                {
                                    "Version": "2012-10-17",
                                    "Statement": [
                                        {
                                            "Effect": "Allow",
                                            "Principal": {"Service": "ec2.amazonaws.com"},
                                            "Action": "sts:AssumeRole",
                                        }
                                    ],
                                }
                            ),
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    parsed = load_repository(SourceOptions(root=root))

    assert [model.file for model in parsed.tf_models] == ["main.tf.json"]
    assert "aws_iam_role.deploy" in parsed.tf_models[0].resources
    assert "D-TF-HCL-PARSE" not in {diagnostic.code for diagnostic in parsed.diagnostics}


# --------------------------------------------------------------------------- scan


def test_scan_fx07_reference_partition_findings_and_scope(tmp_path: Path) -> None:
    outcome = run_scan(
        ScanOptions(
            root=FX07,
            selectors=(ACTION,),
            out_dir=tmp_path / "out",
        )
    )
    report = outcome.report

    assert outcome.exit_code == 0
    assert outcome.written == ()
    assert not (tmp_path / "out").exists()
    assert "\x1b" not in outcome.console_text
    assert "R (ends with entrypoint): 3" in outcome.console_text
    assert "E (expires on its own): 2" in outcome.console_text
    assert "Z (survives): 5" in outcome.console_text

    assert len(report.scenarios) == 1
    scenario = report.scenarios[0]
    assert scenario.selector == ACTION
    assert len(scenario.partition.R) == 3
    assert [(item.ttl_seconds) for item in scenario.partition.E] == [3600, 3600]
    assert len(scenario.partition.Z) == 5
    assert [item.criticality for item in scenario.partition.Z] == [100, 70, 65, 55, 40]
    assert [item.depth for item in scenario.partition.Z] == [0, 0, 0, 0, 0]
    assert len(scenario.rotation_plan.containment) == 1
    assert len(scenario.rotation_plan.rotation) == 5
    assert len(scenario.rotation_plan.verify) == 1
    assert scenario.truncated is False

    assert [finding.rule for finding in report.findings] == [
        "NHB-OIDC-002",
        "NHB-SURV-001",
        "NHB-GHA-001",
        "NHB-OIDC-005",
        "NHB-ROT-001",
        "NHB-ROT-001",
        "NHB-ROT-001",
    ]
    assert {finding.scenario for finding in report.findings} == {ACTION}
    assert set(scenario.findings) == {finding.id for finding in report.findings}

    assert report.scope_and_limits == (
        "Scope: 2 workflows, 2 jobs, 9 Terraform resources.",
        "Not analysed: SCPs, environment protection, branch rules, live AWS state, "
        "job outputs and artifacts.",
        "Limits: closure depth 3, graph node budget 500000, scenario time budget 60 s.",
    )
    assert {item.id for item in report.assumptions} == {
        "A-NO-SCP",
        "A-OIDC-ENV",
        "A-REPO-AGE",
        "A-STS-TTL",
        "H-ROT-WINDOW",
        "H-SECRET-NAME",
    }
    assert "A-REPO-WRITE" not in {item.id for item in report.assumptions}
    assert all(item.used_by for item in report.assumptions)
    assert report.diagnostics == ()
    assert report.schema_id == SCHEMA_VERSION
    assert report.generated_at is None


def test_scan_repo_write_scenario_registers_its_assumption() -> None:
    outcome = run_scan(ScanOptions(root=FX07, selectors=("repo-write",)))

    entry = next(item for item in outcome.report.assumptions if item.id == "A-REPO-WRITE")
    hypothetical_edges = {
        edge.id
        for edge in outcome.report.graph.edges
        if any(item.rule == "A-REPO-WRITE" for item in edge.evidence)
    }
    assert hypothetical_edges
    assert set(entry.used_by) == {"scenario:repo-write", *hypothetical_edges}
    assert outcome.exit_code == 0


def test_scan_all_mutable_actions_expands_and_deduplicates_scenarios() -> None:
    outcome = run_scan(ScanOptions(root=FX07, selectors=("all-mutable-actions", ACTION)))

    assert outcome.exit_code == 0
    assert [scenario.selector for scenario in outcome.report.scenarios] == [ACTION]
    scenario = outcome.report.scenarios[0]
    assert scenario.start_nodes == (
        "job:.github/workflows/ci.yml#test",
        "job:.github/workflows/release.yml#publish",
    )
    assert len(scenario.partition.R) == 3
    assert len(scenario.partition.E) == 2
    assert len(scenario.partition.Z) == 5
    assert {finding.scenario for finding in outcome.report.findings} == {ACTION}


def test_scan_all_mutable_actions_without_targets_reports_no_scenarios(
    tmp_path: Path,
) -> None:
    root = tmp_path / "pinned"
    _write_workflow(
        root,
        """
name: Pinned
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@abcdef0123456789abcdef0123456789abcdef01
""",
    )

    outcome = run_scan(ScanOptions(root=root, selectors=("all-mutable-actions",)))

    assert outcome.exit_code == 0
    assert outcome.report.scenarios == ()
    assert "No scenario partition available." in outcome.console_text


def test_scan_is_byte_deterministic_in_memory(tmp_path: Path) -> None:
    first = run_scan(
        ScanOptions(
            root=FX07,
            selectors=(ACTION,),
            formats=("json",),
            out_dir=tmp_path / "one",
        )
    )
    second = run_scan(
        ScanOptions(
            root=FX07,
            selectors=(ACTION,),
            formats=("json",),
            out_dir=tmp_path / "two",
        )
    )

    assert first.report.model_dump_json() == second.report.model_dump_json()
    assert (tmp_path / "one" / "report.json").read_bytes() == (
        tmp_path / "two" / "report.json"
    ).read_bytes()


def test_scan_writes_each_requested_format(tmp_path: Path) -> None:
    outcome = run_scan(
        ScanOptions(
            root=FX07,
            selectors=(ACTION,),
            formats=("json", "sarif", "html"),
            out_dir=tmp_path / "reports",
        )
    )

    assert [path.name for path in outcome.written] == [
        "report.json",
        "report.sarif",
        "report.html",
    ]
    payload = json.loads((tmp_path / "reports" / "report.json").read_text(encoding="utf-8"))
    assert payload["schema"] == SCHEMA_VERSION
    assert payload["inputs"]["repo_slug"] == "acme/shop"
    sarif = json.loads((tmp_path / "reports" / "report.sarif").read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"
    assert len(sarif["runs"]) == 1
    html = (tmp_path / "reports" / "report.html").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html
    assert "__SCRIPTS__" not in html
    assert "__CSP__" not in html


def test_scan_timestamp_and_staleness_are_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clean = run_scan(ScanOptions(root=FX07, timestamp=True))
    assert clean.report.generated_at is not None
    assert clean.report.generated_at.endswith("Z")
    datetime.fromisoformat(clean.report.generated_at.replace("Z", "+00:00"))

    untimestamped = run_scan(ScanOptions(root=FX07))
    assert untimestamped.report.generated_at is None
    assert not [item for item in untimestamped.report.diagnostics if item.code == "D-DATA-STALE"]

    old = DataFileInfo(
        name="old.yaml",
        verified_on="2020-01-01",
        source_url="https://example.invalid/old",
        entry_count=1,
    )
    monkeypatch.setattr("nhi_blast.pipeline.all_data_file_infos", lambda: (old,))
    stale_untimestamped = run_scan(ScanOptions(root=FX07))
    assert not [
        item for item in stale_untimestamped.report.diagnostics if item.code == "D-DATA-STALE"
    ]
    stale_timestamped = run_scan(ScanOptions(root=FX07, timestamp=True))
    stale = [item for item in stale_timestamped.report.diagnostics if item.code == "D-DATA-STALE"]
    assert len(stale) == 1
    assert stale[0].level.value == "warning"


def test_scan_strict_and_fail_on_exit_codes(tmp_path: Path) -> None:
    relaxed = run_scan(ScanOptions(root=FX03))
    strict = run_scan(ScanOptions(root=FX03, strict=True))
    assert relaxed.exit_code == 0
    assert strict.exit_code == 0

    assert run_scan(ScanOptions(root=FX03, fail_on=Severity.CRITICAL)).exit_code == 1
    assert run_scan(ScanOptions(root=FX03, fail_on=Severity.HIGH)).exit_code == 1
    assert run_scan(ScanOptions(root=FX03, fail_on=Severity.MEDIUM)).exit_code == 1
    assert run_scan(ScanOptions(root=FX03, fail_on=Severity.LOW)).exit_code == 1
    assert run_scan(ScanOptions(root=FX03, fail_on=None)).exit_code == 0

    malformed = _malformed_repo(tmp_path)
    broken = run_scan(ScanOptions(root=malformed, strict=True))
    assert broken.exit_code == 3
    assert [item.code for item in broken.report.diagnostics] == ["D-YAML-PARSE"]
    assert broken.report.diagnostics[0].level.value == "error"
    assert run_scan(ScanOptions(root=malformed)).exit_code == 0


def test_fail_on_parsing() -> None:
    assert parse_fail_on("critical") is Severity.CRITICAL
    assert parse_fail_on(" HIGH ") is Severity.HIGH
    assert parse_fail_on("never") is None
    for invalid in ("info", "none", "warning", ""):
        with pytest.raises(UsageError):
            parse_fail_on(invalid)


def test_invalid_inputs_are_usage_errors(tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=FX07, tf_json=(outside,)))
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=FX07, iam_json=(outside,)))
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=FX07, config_path=outside))
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=FX07, formats=("xml",)))
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=FX07, selectors=("not-a-selector",)))
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=FX07, selectors=("action:unknown/action@v1",)))
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=FX07, max_depth=-1))
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=tmp_path / "missing"))

    broken_config = tmp_path / "bad-config"
    broken_config.mkdir()
    (broken_config / "nhi-blast.toml").write_text("unknown = 1\n", encoding="utf-8")
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=broken_config))

    (broken_config / "nhi-blast.toml").write_text("[limits\n", encoding="utf-8")
    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=broken_config))


def test_output_failures_are_output_errors(tmp_path: Path) -> None:
    blocking = tmp_path / "blocking"
    blocking.write_text("not a directory", encoding="utf-8")

    with pytest.raises(OutputError):
        run_scan(ScanOptions(root=FX07, formats=("json",), out_dir=blocking))
    with pytest.raises(OutputError):
        run_rank(RankOptions(root=FX07, fmt="json", out_dir=blocking))
    with pytest.raises(OutputError):
        run_export(ExportOptions(root=FX07, fmt="json", out_dir=blocking))


# --------------------------------------------------------------------------- rank


def test_rank_fx07_rows_and_json(tmp_path: Path) -> None:
    outcome = run_rank(RankOptions(root=FX07, fmt="json", out_dir=tmp_path / "rank"))

    assert outcome.exit_code == 0
    assert "tj-actions/changed-files@v45" in outcome.console_text
    assert outcome.written == (tmp_path / "rank" / "rank.json",)
    payload = json.loads((tmp_path / "rank" / "rank.json").read_text(encoding="utf-8"))
    assert payload["schema"] == SCHEMA_VERSION + "/rank"
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["action"] == "tj-actions/changed-files@v45"
    assert row["pin_kind"] == "TAG"
    assert (row["use_sites"], row["jobs_with_oidc"]) == (2, 1)
    assert (row["r_count"], row["e_count"], row["z_count"]) == (3, 2, 5)
    assert row["highest_criticality"] == 100

    strict_broken = _malformed_repo(tmp_path)
    assert run_rank(RankOptions(root=strict_broken, strict=True)).exit_code == 3
    with pytest.raises(UsageError):
        run_rank(RankOptions(root=FX07, fmt="sarif"))


# ------------------------------------------------------------------------- export


def test_export_json_and_dot_are_deterministic(tmp_path: Path) -> None:
    json_out = run_export(ExportOptions(root=FX07, fmt="json", out_dir=tmp_path / "one"))
    dot_out = run_export(ExportOptions(root=FX07, fmt="dot", out_dir=tmp_path / "two"))
    run_export(ExportOptions(root=FX07, fmt="json", out_dir=tmp_path / "three"))

    assert json_out.exit_code == 0
    assert json_out.node_count > 0
    assert json_out.edge_count > 0
    assert json_out.written == (tmp_path / "one" / "graph.json",)
    assert dot_out.written == (tmp_path / "two" / "graph.dot",)
    assert (tmp_path / "one" / "graph.json").read_bytes() == (
        tmp_path / "three" / "graph.json"
    ).read_bytes()

    payload = json.loads((tmp_path / "one" / "graph.json").read_text(encoding="utf-8"))
    assert payload["schema"] == GRAPH_SCHEMA
    assert payload["counts"] == {
        "nodes": len(payload["graph"]["nodes"]),
        "edges": len(payload["graph"]["edges"]),
    }
    assert payload["inputs"]["digest"] == load_repository(SourceOptions(root=FX07)).inputs.digest

    dot_text = (tmp_path / "two" / "graph.dot").read_text(encoding="utf-8")
    assert dot_text.startswith("// NHI-Blast graph export\n")
    assert dot_text.endswith("}\n")
    assert "digraph nhi_blast {" in dot_text
    assert "n0 [label=" in dot_text

    stamped = run_export(
        ExportOptions(root=FX07, fmt="dot", timestamp=True, out_dir=tmp_path / "stamped")
    )
    stamped_text = stamped.written[0].read_text(encoding="utf-8")
    assert "// generated_at: " in stamped_text
    with pytest.raises(UsageError):
        run_export(ExportOptions(root=FX07, fmt="opengraph"))
    with pytest.raises(UsageError):
        run_export(ExportOptions(root=FX07, fmt="yaml"))


def test_dot_export_escapes_hostile_labels(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write_workflow(
        root,
        "name: 'evil\"]; subgraph x { rank=same; \"pwn'\n"
        "on: push\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo hi\n",
    )

    outcome = run_export(ExportOptions(root=root, fmt="dot", out_dir=tmp_path / "out"))
    text = outcome.written[0].read_text(encoding="utf-8")

    assert 'evil\\"]; subgraph x { rank=same; \\"pwn' in text
    assert 'evil"]; subgraph x' not in text


# ------------------------------------------------------------------------ explain


def test_explain_resolves_finding_node_and_edge(tmp_path: Path) -> None:
    outcome = run_scan(
        ScanOptions(
            root=FX07,
            selectors=(ACTION,),
            formats=("json",),
            out_dir=tmp_path / "out",
        )
    )
    report_path = outcome.written[0]
    report = load_report(report_path)

    finding = outcome.report.findings[0]
    finding_text = render_explanation(report, finding.id)
    assert finding_text.startswith(f"Finding {finding.id}")
    assert "Evidence:" in finding_text
    assert "Path:" in finding_text

    node = outcome.report.graph.nodes[0]
    node_text = render_explanation(report, node.id)
    assert node_text.startswith(f"Node {node.id}")
    assert "Incoming edges:" in node_text

    edge = outcome.report.graph.edges[0]
    edge_text = render_explanation(report, edge.id)
    assert edge_text.startswith(f"Edge {edge.id}")
    assert "Confidence:" in edge_text

    with pytest.raises(ExplainError):
        render_explanation(report, "does-not-exist")


def test_load_report_rejects_bad_documents(tmp_path: Path) -> None:
    with pytest.raises(ExplainError):
        load_report(tmp_path / "missing.json")

    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(ExplainError):
        load_report(directory)

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ExplainError):
        load_report(invalid)

    mismatch = tmp_path / "mismatch.json"
    mismatch.write_text(
        json.dumps(
            {
                "schema": "other/0.0",
                "tool": {"version": "x"},
                "inputs": {
                    "digest": "0" * 64,
                    "repo_slug": "acme/shop",
                    "repo_slug_source": "test",
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExplainError, match="unsupported report schema"):
        load_report(mismatch)


# ----------------------------------------------------------------------- safety


def test_scan_does_not_read_outside_the_root(tmp_path: Path) -> None:
    root = _malformed_repo(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text('{"format_version": "1.0", "values": {}}', encoding="utf-8")

    with pytest.raises(UsageError):
        run_scan(ScanOptions(root=root, tf_json=(outside,)))

    parsed = load_repository(SourceOptions(root=root))
    assert all(not Path(item.path).is_absolute() for item in parsed.inputs.files)
    assert all(".." not in Path(item.path).parts for item in parsed.inputs.files)


def test_inputs_digest_changes_with_content(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    path = _write_workflow(
        root,
        "name: one\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo one\n",
    )
    first = load_repository(SourceOptions(root=root)).inputs.digest
    path.write_text(
        "name: two\non: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo two\n",
        encoding="utf-8",
    )
    second = load_repository(SourceOptions(root=root)).inputs.digest

    assert first != second


def test_timestamp_is_utc_and_deterministic_fields_are_stable() -> None:
    first = run_scan(ScanOptions(root=FX07, timestamp=True)).report
    second = run_scan(ScanOptions(root=FX07, timestamp=True)).report

    parsed = datetime.fromisoformat((first.generated_at or "").replace("Z", "+00:00"))
    assert parsed.tzinfo == UTC
    assert first.inputs == second.inputs
    assert first.findings == second.findings
    assert first.graph == second.graph


def test_copying_repository_keeps_absolute_paths_out_of_inputs(tmp_path: Path) -> None:
    root = tmp_path / "copy"
    shutil.copytree(FX07, root)
    parsed = load_repository(SourceOptions(root=root))

    serialized = parsed.inputs.model_dump_json()
    assert str(tmp_path).replace("\\", "/") not in serialized
    assert all(not item.path.startswith("/") for item in parsed.inputs.files)
