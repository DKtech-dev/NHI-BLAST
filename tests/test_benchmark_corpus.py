"""Corpus integrity gates and installed-entrypoint/report integration."""

from __future__ import annotations

import ctypes
import hashlib
import importlib.util
import json
import os
import socket
import struct
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from nhi_blast.report.html import write_html
from nhi_blast.report.json_report import write_json
from nhi_blast.report.model_json import report_dict
from nhi_blast.report.sarif import sarif_report, write_sarif
from tests.report_support import make_report

PROJECT = Path(__file__).resolve().parents[1]
HARNESS = PROJECT / "scripts" / "benchmark_corpus.py"


@pytest.fixture
def corpus() -> ModuleType:
    assert HARNESS.is_file(), "the standalone corpus harness is not implemented"
    spec = importlib.util.spec_from_file_location("benchmark_corpus", HARNESS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli() -> Path:
    entry = Path(sys.executable).parent / ("nhi-blast.exe" if os.name == "nt" else "nhi-blast")
    assert entry.is_file(), "integration requires this environment's installed CLI entrypoint"
    return entry.absolute()


def save(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


@pytest.fixture
def sample(tmp_path: Path) -> tuple[Path, Path, Path]:
    datasets = tmp_path / "datasets"
    root = datasets / "acme--small"
    workflow = root / ".github" / "workflows" / "build.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "name: build\non: push\npermissions: read-all\njobs:\n"
        "  build:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - uses: actions/checkout@v4\n",
        encoding="utf-8",
    )
    save(root / "policy.json", {"Version": "2012-10-17", "Statement": []})
    files = [
        {
            "path": p.relative_to(root).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(root.rglob("*"))
        if p.is_file()
    ]
    manifest = tmp_path / "manifest.json"
    save(
        manifest,
        {
            "version": 1,
            "datasets": [
                {
                    "id": root.name,
                    "slug": "acme/small",
                    "repository": "https://github.com/acme/small",
                    "revision": "a" * 40,
                    "license": "MIT",
                    "retrieved_on": "2026-10-28",
                    "external": True,
                    "archive_sha256": "b" * 64,
                    "files": files,
                    "iam_json": ["policy.json"],
                    "selection": {"rationale": "synthetic control"},
                }
            ],
        },
    )
    return datasets, manifest, tmp_path / "results"


def no_process(*_args: Any, **_kwargs: Any) -> Any:
    pytest.fail("preflight must not start the CLI")


@pytest.mark.parametrize("damage", ["missing", "mutated", "size", "extra"])
def test_inventory_damage_blocks_all_scans(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    damage: str,
) -> None:
    datasets, manifest, out = sample
    policy = datasets / "acme--small" / "policy.json"
    if damage == "missing":
        policy.unlink()
    elif damage == "mutated":
        original = policy.read_bytes()
        policy.write_bytes(original.replace(b"2012", b"2013"))
    elif damage == "size":
        policy.write_bytes(policy.read_bytes() + b" ")
    else:
        (policy.parent / "extra.txt").write_text("unexpected", encoding="utf-8")
    monkeypatch.setattr(corpus.subprocess, "run", no_process)
    with pytest.raises(corpus.BenchmarkError, match=damage):
        corpus.run_benchmark(cli, datasets, manifest, out, 2)
    assert not out.exists()


@pytest.mark.parametrize(
    "unsafe",
    [
        "../outside.json",
        "/outside",
        "C:/outside",
        "a\\b",
        "a/../b",
        "a//b",
        "a:stream",
        "CON",
        "trailing. ",
    ],
)
def test_manifest_path_escape_is_rejected(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
    unsafe: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datasets, manifest, out = sample
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["datasets"][0]["files"][0]["path"] = unsafe
    save(manifest, data)
    monkeypatch.setattr(corpus.subprocess, "run", no_process)
    with pytest.raises(corpus.BenchmarkError, match="unsafe_path"):
        corpus.run_benchmark(cli, datasets, manifest, out, 2)
    assert not out.exists()


def test_entire_corpus_is_validated_before_first_process(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datasets, manifest, out = sample
    data = json.loads(manifest.read_text(encoding="utf-8"))
    second = dict(data["datasets"][0], id="z--missing", slug="z/missing")
    data["datasets"].append(second)
    save(manifest, data)
    monkeypatch.setattr(corpus.subprocess, "run", no_process)
    with pytest.raises(corpus.BenchmarkError, match="missing"):
        corpus.run_benchmark(cli, datasets, manifest, out, 2)
    assert not out.exists()


def test_unlisted_iam_policy_is_rejected(
    corpus: ModuleType,
    sample: tuple[Path, Path, Path],
) -> None:
    datasets, manifest, _ = sample
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["datasets"][0]["iam_json"] = ["not-listed.json"]
    save(manifest, data)
    with pytest.raises(corpus.BenchmarkError, match="iam"):
        corpus.validate_manifest(manifest, datasets)


def test_symlink_escape_is_rejected(corpus: ModuleType, sample: tuple[Path, Path, Path]) -> None:
    datasets, manifest, out = sample
    outside = out.parent / "outside"
    outside.mkdir()
    try:
        (datasets / "acme--small" / "escape").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege is unavailable; junction test covers reparse points")
    with pytest.raises(corpus.BenchmarkError, match="link"):
        corpus.validate_manifest(manifest, datasets)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction security boundary")
def test_junction_escape_is_rejected(corpus: ModuleType, sample: tuple[Path, Path, Path]) -> None:
    datasets, manifest, out = sample
    outside = out.parent / "outside"
    outside.mkdir()
    junction = datasets / "acme--small" / "junction"
    junction.mkdir()
    substitute = ("\\??\\" + str(outside)).encode("utf-16-le")
    printable = str(outside).encode("utf-16-le")
    buffer = substitute + b"\0\0" + printable + b"\0\0"
    data = (
        struct.pack(
            "<IHHHHHH",
            0xA0000003,
            8 + len(buffer),
            0,
            0,
            len(substitute),
            len(substitute) + 2,
            len(printable),
        )
        + buffer
    )
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.restype = ctypes.c_void_p
    handle = kernel.CreateFileW(str(junction), 0x40000000, 0, None, 3, 0x02200000, None)
    assert handle not in (None, ctypes.c_void_p(-1).value)
    returned = ctypes.c_ulong()
    try:
        assert kernel.DeviceIoControl(
            ctypes.c_void_p(handle),
            0x000900A4,
            data,
            len(data),
            None,
            0,
            ctypes.byref(returned),
            None,
        ), ctypes.get_last_error()
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        with pytest.raises(corpus.BenchmarkError, match="link"):
            corpus.validate_manifest(manifest, datasets)
    finally:
        junction.rmdir()


@pytest.mark.parametrize("stale_file", [True, False])
def test_stale_output_is_never_reused(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
    stale_file: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datasets, manifest, out = sample
    if stale_file:
        out.write_bytes(b"existing evidence")
    else:
        out.mkdir()
        (out / "summary.json").write_bytes(b"existing evidence")
    monkeypatch.setattr(corpus.subprocess, "run", no_process)
    with pytest.raises(corpus.BenchmarkError, match="stale"):
        corpus.run_benchmark(cli, datasets, manifest, out, 2)
    assert (out if stale_file else out / "summary.json").read_bytes() == b"existing evidence"


def artifacts(path: Path) -> None:
    path.mkdir(parents=True)
    report = make_report()
    write_json(report, path / "report.json")
    write_sarif(report, path / "report.sarif")
    write_html(report, path / "report.html")


@pytest.mark.parametrize(
    "damage", ["missing", "invalid", "html", "sarif", "fingerprint", "message", "properties"]
)
def test_report_boundary_rejects_missing_invalid_or_inconsistent_artifacts(
    corpus: ModuleType,
    tmp_path: Path,
    damage: str,
) -> None:
    path = tmp_path / "artifacts"
    artifacts(path)
    if damage == "missing":
        (path / "report.html").unlink()
    elif damage == "invalid":
        save(path / "report.json", {"schema": "not-a-report"})
    elif damage == "html":
        html = path / "report.html"
        text = html.read_text(encoding="utf-8")
        html.write_text(
            text.replace('"repo_slug":"acme/shop"', '"repo_slug":"acme/other"'), encoding="utf-8"
        )
    else:
        sarif = path / "report.sarif"
        data = json.loads(sarif.read_text(encoding="utf-8"))
        result = data["runs"][0]["results"][0]
        if damage == "sarif":
            data["runs"][0]["results"] = []
        elif damage == "message":
            result["message"]["text"] = "unrelated finding text"
        elif damage == "properties":
            result["properties"]["assumptions"] = [{"unexpected": "object"}]
        else:
            result["partialFingerprints"]["nhiBlast/v1"] = "0" * 64
        save(sarif, data)
    with pytest.raises(corpus.BenchmarkError, match=r"artifact|inconsistent"):
        corpus.validate_artifacts(path)


@pytest.mark.parametrize(
    ("damage", "code"),
    [
        ("edge-src", "artifact_graph_reference_invalid"),
        ("edge-dst", "artifact_graph_reference_invalid"),
        ("finding-path", "artifact_finding_node_reference_invalid"),
        ("finding-path-edges", "artifact_finding_edge_reference_invalid"),
        ("scenario-start", "artifact_scenario_start_reference_invalid"),
        ("scenario-r", "artifact_scenario_credential_reference_invalid"),
        ("scenario-e", "artifact_scenario_credential_reference_invalid"),
        ("scenario-z", "artifact_scenario_credential_reference_invalid"),
        ("scenario-potential", "artifact_scenario_potential_edge_reference_invalid"),
        ("scenario-potential-nodes", "artifact_scenario_potential_node_reference_invalid"),
        ("scenario-findings", "artifact_scenario_finding_reference_invalid"),
        ("rotation-credential", "artifact_rotation_credential_reference_invalid"),
        ("rotation-depends-on", "artifact_rotation_dependency_reference_invalid"),
        ("assumption-owner", "artifact_assumption_reference_invalid"),
    ],
)
def test_report_boundary_rejects_dangling_references(
    corpus: ModuleType, tmp_path: Path, damage: str, code: str
) -> None:
    report = make_report()
    scenario = report.scenarios[0]
    if damage in {"edge-src", "edge-dst"}:
        field = "src" if damage == "edge-src" else "dst"
        edges = tuple(
            edge.model_copy(update={field: "missing-node"}) if index == 0 else edge
            for index, edge in enumerate(report.graph.edges)
        )
        report = report.model_copy(
            update={"graph": report.graph.model_copy(update={"edges": edges})}
        )
    elif damage in {"finding-path", "finding-path-edges"}:
        field = "path" if damage == "finding-path" else "path_edges"
        value = ("missing-node",) if damage == "finding-path" else ("missing-edge",)
        finding = report.findings[0].model_copy(update={field: value})
        report = report.model_copy(update={"findings": (finding,)})
    elif damage == "scenario-start":
        scenario = scenario.model_copy(update={"start_nodes": ("missing-node",)})
    elif damage in {"scenario-r", "scenario-e", "scenario-z"}:
        partition = scenario.partition
        if damage == "scenario-r":
            partition = partition.model_copy(update={"R": ("missing-credential",)})
        else:
            entries = partition.E if damage == "scenario-e" else partition.Z
            broken = entries[0].model_copy(update={"credential": "missing-credential"})
            partition = partition.model_copy(update={damage[-1].upper(): (broken,)})
        scenario = scenario.model_copy(update={"partition": partition})
    elif damage == "scenario-potential":
        scenario = scenario.model_copy(update={"potential": ("missing-edge",)})
    elif damage == "scenario-potential-nodes":
        scenario = scenario.model_copy(update={"potential_nodes": ("missing-node",)})
    elif damage == "scenario-findings":
        scenario = scenario.model_copy(update={"findings": ("NHB-XXX-00000000",)})
    elif damage in {"rotation-credential", "rotation-depends-on"}:
        plan = scenario.rotation_plan
        step = plan.rotation[0]
        if damage == "rotation-credential":
            broken = step.credentials[0].model_copy(update={"id": "missing-credential"})
            step = step.model_copy(update={"credentials": (broken,)})
        else:
            step = step.model_copy(update={"depends_on": ("missing-credential",)})
        plan = plan.model_copy(update={"rotation": (step, *plan.rotation[1:])})
        scenario = scenario.model_copy(update={"rotation_plan": plan})
    elif damage == "assumption-owner":
        assumption = report.assumptions[0].model_copy(update={"used_by": ("missing-owner",)})
        report = report.model_copy(update={"assumptions": (assumption,)})
    report = report.model_copy(update={"scenarios": (scenario,)})
    path = tmp_path / "artifacts"
    path.mkdir()
    write_json(report, path / "report.json")
    write_sarif(report, path / "report.sarif")
    write_html(report, path / "report.html")
    with pytest.raises(corpus.BenchmarkError, match=code):
        corpus.validate_artifacts(path)


def test_local_schema_validator_refuses_remote_references(
    corpus: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema = tmp_path / "schema.json"
    save(
        schema,
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$ref": "https://example.invalid/remote.json",
        },
    )
    monkeypatch.setattr(socket, "socket", no_process)
    with pytest.raises(corpus.BenchmarkError, match="schema_reference"):
        corpus.load_validator(schema)


@pytest.mark.parametrize("failure", ["nonzero", "spawn", "missing", "inconsistent"])
def test_process_and_artifact_failures_fail_aggregate_without_raw_logs(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    datasets, manifest, out = sample
    canary = b"synthetic-log-sentinel-must-not-be-retained"
    calls: list[list[str]] = []

    def process(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        assert Path(kwargs["cwd"]).is_absolute()
        assert not Path(kwargs["cwd"]).is_relative_to(PROJECT)
        assert kwargs.get("shell", False) is False
        if failure == "spawn":
            raise OSError(canary.decode())
        target = Path(command[command.index("--out") + 1])
        if failure != "missing":
            artifacts(target)
        if failure == "inconsistent":
            save(target / "report.sarif", {"version": "2.1.0", "runs": []})
        return subprocess.CompletedProcess(
            command, 4 if failure == "nonzero" else 0, canary, canary
        )

    monkeypatch.setattr(corpus.subprocess, "run", process)
    summary = corpus.run_benchmark(cli, datasets, manifest, out, 2)
    assert len(calls) == 2
    assert summary["status"] == "FAIL"
    assert summary["deterministic"] is False
    row = summary["datasets"][0]["runs"][0]
    assert row["status"] == "FAIL"
    assert canary not in (out / "summary.json").read_bytes()
    assert row["stderr"]["bytes"] == (0 if failure == "spawn" else len(canary))
    assert (
        row["stderr"]["sha256"] == hashlib.sha256(b"" if failure == "spawn" else canary).hexdigest()
    )


@pytest.mark.parametrize("repeats", [1, 2])
def test_real_installed_cli_integration(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
    repeats: int,
) -> None:
    datasets, manifest, out = sample
    summary = corpus.run_benchmark(cli, datasets, manifest, out, repeats)
    assert summary["status"] == "PASS"
    assert summary["deterministic"] is (repeats >= 2)
    assert summary["cli"]["sha256"] == hashlib.sha256(cli.read_bytes()).hexdigest()
    assert summary["source_tree"]["files"]
    runs = summary["datasets"][0]["runs"]
    assert len(runs) == repeats
    for run in runs:
        assert run["exit"] == 0
        assert run["validated"] is True
        assert run["elapsed_seconds"] >= 0
        assert run["graph"]["nodes"] > 0
        assert run["input_categories"]["workflow"] == 1
        assert run["input_categories"]["iam_json"] == 1
        assert run["scenarios"]
        assert all(set(s["partition"]) == {"R", "E", "Z"} for s in run["scenarios"])
        command = run["command"]
        assert command[0] == str(cli)
        assert command[command.index("--iam-json") + 1] == str(
            datasets / "acme--small" / "policy.json"
        )
        assert command.count("--simulate-compromise") == 2
        assert command[command.index("--fail-on") + 1] == "never"
        assert set(run["artifacts"]) == {"report.json", "report.sarif", "report.html"}
    assert json.loads((out / "summary.json").read_text(encoding="utf-8")) == summary


def test_valid_but_different_repeats_are_not_deterministic(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datasets, manifest, out = sample
    count = 0

    def process(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal count
        count += 1
        target = Path(command[command.index("--out") + 1])
        target.mkdir(parents=True)
        report = make_report().model_copy(update={"scope_and_limits": (str(count),)})
        write_json(report, target / "report.json")
        write_sarif(report, target / "report.sarif")
        write_html(report, target / "report.html")
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(corpus.subprocess, "run", process)
    summary = corpus.run_benchmark(cli, datasets, manifest, out, 2)
    assert summary["status"] == "FAIL"
    assert summary["deterministic"] is False
    assert all(r["validated"] for r in summary["datasets"][0]["runs"])


def test_determinism_rechecks_actual_artifact_bytes_after_validation(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datasets, manifest, out = sample
    validate = corpus.validate_artifacts
    count = 0

    def process(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        artifacts(Path(command[command.index("--out") + 1]))
        return subprocess.CompletedProcess(command, 0, b"", b"")

    def changed(path: Path, checks: Any) -> Any:
        nonlocal count
        result = validate(path, checks)
        count += 1
        if count == 1:
            target = path / "report.json"
            target.write_bytes(target.read_bytes() + b" ")
        return result

    monkeypatch.setattr(corpus.subprocess, "run", process)
    monkeypatch.setattr(corpus, "validate_artifacts", changed)
    summary = corpus.run_benchmark(cli, datasets, manifest, out, 2)
    assert summary["status"] == "FAIL"
    assert summary["deterministic"] is False


@pytest.mark.parametrize("hostile", [False, True])
def test_valid_report_correspondence_accepts_reporter_text_normalization(
    corpus: ModuleType,
    tmp_path: Path,
    hostile: bool,
) -> None:
    path = tmp_path / "valid-artifacts"
    path.mkdir()
    report = make_report(hostile=hostile)
    write_json(report, path / "report.json")
    write_sarif(report, path / "report.sarif")
    write_html(report, path / "report.html")
    assert corpus.validate_artifacts(path)["report"] == report_dict(report)


def test_sarif_truncation_requires_correspondence_and_disclosure(corpus: ModuleType) -> None:
    base = make_report()
    report = base.model_copy(
        update={
            "findings": tuple(
                base.findings[0].model_copy(update={"id": f"finding-{index:05d}"})
                for index in range(5001)
            )
        }
    )
    data = report_dict(report)
    sarif = sarif_report(report)
    assert len(sarif["runs"][0]["results"]) == 5000
    corpus.verify_sarif_correspondence(data, sarif)
    sarif["runs"][0].pop("invocations")
    with pytest.raises(corpus.BenchmarkError, match="truncation"):
        corpus.verify_sarif_correspondence(data, sarif)


def test_nonworkflow_dataset_does_not_request_repo_write(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
) -> None:
    datasets, manifest, out = sample
    data = json.loads(manifest.read_text(encoding="utf-8"))
    workflow = datasets / "acme--small" / ".github" / "workflows" / "build.yml"
    workflow.unlink()
    data["datasets"][0]["files"] = [
        file for file in data["datasets"][0]["files"] if not file["path"].startswith(".github/")
    ]
    save(manifest, data)
    dataset = corpus.validate_manifest(manifest, datasets)[0]
    command = corpus.scan_command(cli, dataset, out)
    assert command.count("--simulate-compromise") == 1
    assert "all-mutable-actions" in command
    assert "repo-write" not in command


def test_timeout_is_aggregated_without_retaining_process_output(
    corpus: ModuleType,
    cli: Path,
    sample: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datasets, manifest, out = sample
    sentinel = b"synthetic-timeout-log-not-to-store"

    def process(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(command, 300, output=sentinel, stderr=sentinel)

    monkeypatch.setattr(corpus.subprocess, "run", process)
    summary = corpus.run_benchmark(cli, datasets, manifest, out, 2)
    assert summary["status"] == "FAIL"
    for run in summary["datasets"][0]["runs"]:
        assert "process_timeout" in run["errors"]
        assert run["exit"] is None
        assert run["stdout"]["sha256"] == hashlib.sha256(sentinel).hexdigest()
    assert sentinel not in (out / "summary.json").read_bytes()


def test_script_success_from_external_cwd_uses_no_project_import_path(
    cli: Path,
    sample: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    datasets, manifest, out = sample
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--cli",
            str(cli),
            "--datasets",
            str(datasets),
            "--manifest",
            str(manifest),
            "--out",
            str(out),
            "--repeats",
            "2",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.startswith(b"PASS:")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["deterministic"] is True


def test_script_works_from_external_cwd_and_returns_failure_status(
    cli: Path,
    sample: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    datasets, manifest, out = sample
    (datasets / "acme--small" / "policy.json").unlink()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--cli",
            str(cli),
            "--datasets",
            str(datasets),
            "--manifest",
            str(manifest),
            "--out",
            str(out),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert b"missing" in result.stderr
    assert not out.exists()
