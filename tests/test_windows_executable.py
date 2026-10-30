"""End-to-end checks for the built Windows executable (requires NHI_BLAST_WINDOWS_EXE)."""

from __future__ import annotations

import getpass
import json
import locale
import os
import shutil
import socket
import subprocess
from pathlib import Path

import jsonschema
import pytest

from tests.entrypoint_support import resolve_cli_entrypoint

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
FX03 = FIXTURES / "fx03-wildcard-trust"
FX07 = FIXTURES / "fx07-incident"
FX10 = FIXTURES / "fx10-hcl-fallback"
ACTION = "action:tj-actions/changed-files@v45"
EXE_NAME = "nhi-blast-windows-x64.exe"
EXE_ENV = "NHI_BLAST_WINDOWS_EXE"
REFERENCE_ENV = "NHI_BLAST_REFERENCE_CLI"

pytestmark = [
    pytest.mark.skipif(os.name != "nt", reason="Windows executable packaging"),
    pytest.mark.skipif(
        not os.environ.get(EXE_ENV), reason=f"set {EXE_ENV} to the built executable"
    ),
]

EXPECTED_FINDINGS = [
    "NHB-OIDC-002-f3384765",
    "NHB-SURV-001-233ec620",
    "NHB-GHA-001-69442ef8",
    "NHB-OIDC-005-39d43eb0",
    "NHB-ROT-001-142a69ca",
    "NHB-ROT-001-88df584d",
    "NHB-ROT-001-f1aba26d",
]


def _exe() -> Path:
    path = Path(os.environ[EXE_ENV]).resolve()
    assert path.is_file(), path
    assert path.name == EXE_NAME, path
    return path


def _reference() -> Path:
    configured = os.environ.get(REFERENCE_ENV)
    return Path(configured).resolve() if configured else resolve_cli_entrypoint()


def _decode(payload: bytes) -> str:
    for encoding in ("utf-8", locale.getpreferredencoding(False), "cp1252"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace")


def _run(
    executable: Path,
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 180,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [str(executable), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return subprocess.CompletedProcess(
        completed.args,
        completed.returncode,
        _decode(completed.stdout).replace("\r\n", "\n"),
        _decode(completed.stderr).replace("\r\n", "\n"),
    )


def _clean_env(tmp_path: Path) -> dict[str, str]:
    system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    temporary = tmp_path / "temp with spaces"
    temporary.mkdir(parents=True, exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "SystemRoot": system_root,
        "WINDIR": os.environ.get("WINDIR", system_root),
        "PATH": str(Path(system_root) / "System32"),
        "PATHEXT": ".COM;.EXE;.BAT;.CMD",
        "TEMP": str(temporary),
        "TMP": str(temporary),
        "USERPROFILE": str(home),
        "HOME": str(home),
        "PYTHONHASHSEED": "0",
        "PYTHONHOME": str(tmp_path / "no-python-home"),
        "PYTHONPATH": str(tmp_path / "no-python-path"),
        "NO_COLOR": "1",
    }


def _reference_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    return env


def _fixture_copy(tmp_path: Path, fixture: Path) -> Path:
    destination = tmp_path / "répository with spaces" / fixture.name
    shutil.copytree(fixture, destination)
    return destination


def _normalise(text: str, *paths: Path) -> str:
    for path in paths:
        text = text.replace(str(path), "<OUT>").replace(path.as_posix(), "<OUT>")
    return text


def _artifacts(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in sorted(directory.iterdir()) if path.is_file()}


def _assert_report_schema(report: Path) -> None:
    schema = json.loads((ROOT / "docs" / "schema" / "report.schema.json").read_text("utf-8"))
    jsonschema.Draft202012Validator(schema).validate(json.loads(report.read_text("utf-8")))


def _assert_sarif_schema(sarif: Path) -> None:
    schema = json.loads((ROOT / "docs" / "schema" / "sarif-2.1.0.schema.json").read_text("utf-8"))
    jsonschema.Draft7Validator(schema).validate(json.loads(sarif.read_text("utf-8")))


def test_standalone_copy_runs_without_python_or_the_repository(tmp_path: Path) -> None:
    standalone = tmp_path / "standalone copy ü"
    standalone.mkdir()
    exe = standalone / EXE_NAME
    shutil.copy2(_exe(), exe)
    cwd = tmp_path / "working directory with spaces"
    cwd.mkdir()
    env = _clean_env(tmp_path)

    assert shutil.which("python", path=env["PATH"]) is None
    help_result = _run(exe, ["--help"], cwd=cwd, env=env)
    version = _run(exe, ["version"], cwd=cwd, env=env)
    data = _run(exe, ["version", "--data"], cwd=cwd, env=env)
    schema = _run(exe, ["schema"], cwd=cwd, env=env)

    assert help_result.returncode == 0, help_result.stderr
    for command in ("scan", "rank", "explain", "export", "schema", "version"):
        assert command in help_result.stdout
    assert version.returncode == 0, version.stderr
    assert version.stdout == "nhi-blast 0.2.0\nreport schema nhi-blast-report/1.0\n"
    assert data.returncode == 0
    assert "Data files: 8" in data.stdout
    for name in (
        "assumptions.yaml",
        "aws_github_condition_keys.yaml",
        "credential_heuristics.yaml",
        "permission_scopes.yaml",
        "rotation_hints.yaml",
        "rules.yaml",
        "sinks_catalog.yaml",
        "trigger_profiles.yaml",
    ):
        assert name in data.stdout
    assert schema.returncode == 0
    assert json.loads(schema.stdout)["properties"]
    assert version.stderr == data.stderr == schema.stderr == ""


def test_cli_metadata_matches_the_python_installation(tmp_path: Path) -> None:
    env = _clean_env(tmp_path)
    reference = _reference()
    for args in (["--help"], ["version"], ["version", "--data"], ["schema"]):
        exe_result = _run(_exe(), args, cwd=ROOT, env=env)
        python_result = _run(reference, args, cwd=ROOT, env=_reference_env())
        assert exe_result.returncode == python_result.returncode, args
        assert exe_result.stdout == python_result.stdout, args
        assert exe_result.stderr == python_result.stderr, args


def test_scan_formats_match_the_reference_cli(tmp_path: Path) -> None:
    root = _fixture_copy(tmp_path, FX07)
    exe_out = tmp_path / "exe output ü"
    python_out = tmp_path / "python output ü"
    args = [
        "scan",
        str(root),
        "--simulate-compromise",
        ACTION,
        "--format",
        "json",
        "--format",
        "sarif",
        "--format",
        "html",
        "--fail-on",
        "high",
    ]

    exe_result = _run(
        _exe(), [*args, "--out", str(exe_out)], cwd=tmp_path, env=_clean_env(tmp_path)
    )
    python_result = _run(
        _reference(), [*args, "--out", str(python_out)], cwd=tmp_path, env=_reference_env()
    )

    assert exe_result.returncode == python_result.returncode == 1
    assert _normalise(exe_result.stdout, exe_out) == _normalise(python_result.stdout, python_out)
    assert exe_result.stderr == python_result.stderr == ""
    assert _artifacts(exe_out) == _artifacts(python_out)
    assert set(_artifacts(exe_out)) == {"report.json", "report.sarif", "report.html"}

    payload = json.loads((exe_out / "report.json").read_text(encoding="utf-8"))
    assert [finding["id"] for finding in payload["findings"]] == EXPECTED_FINDINGS
    partition = payload["scenarios"][0]["partition"]
    assert len(partition["R"]) == 3
    assert len(partition["E"]) == 2
    assert len(partition["Z"]) == 5
    assert {finding["rule"] for finding in payload["findings"]} >= {"NHB-OIDC-002", "NHB-SURV-001"}
    _assert_report_schema(exe_out / "report.json")
    _assert_sarif_schema(exe_out / "report.sarif")

    html = (exe_out / "report.html").read_text(encoding="utf-8")
    assert '<script type="application/json" id="report-data">' in html
    assert "Content-Security-Policy" in html
    assert "https://fonts.gstatic.com" not in html
    assert 'src="http' not in html


def test_rank_export_and_explain_match_the_reference_cli(tmp_path: Path) -> None:
    root = _fixture_copy(tmp_path, FX07)
    env = _clean_env(tmp_path)
    reference = _reference()

    exe_rank = tmp_path / "exe rank"
    python_rank = tmp_path / "python rank"
    exe_json = tmp_path / "exe graph json"
    python_json = tmp_path / "python graph json"
    exe_dot = tmp_path / "exe graph dot"
    python_dot = tmp_path / "python graph dot"
    comparisons = [
        (
            "rank-console",
            ["rank", str(root)],
            ["rank", str(root)],
            None,
        ),
        (
            "rank-json",
            ["rank", str(root), "--format", "json", "--out", str(exe_rank)],
            ["rank", str(root), "--format", "json", "--out", str(python_rank)],
            (exe_rank / "rank.json", python_rank / "rank.json"),
        ),
        (
            "export-json",
            ["export", str(root), "--format", "json", "--out", str(exe_json)],
            ["export", str(root), "--format", "json", "--out", str(python_json)],
            (exe_json / "graph.json", python_json / "graph.json"),
        ),
        (
            "export-dot",
            ["export", str(root), "--format", "dot", "--out", str(exe_dot)],
            ["export", str(root), "--format", "dot", "--out", str(python_dot)],
            (exe_dot / "graph.dot", python_dot / "graph.dot"),
        ),
    ]
    for label, exe_args, python_args, artifacts in comparisons:
        exe_result = _run(_exe(), exe_args, cwd=tmp_path, env=env)
        python_result = _run(reference, python_args, cwd=tmp_path, env=_reference_env())
        assert exe_result.returncode == python_result.returncode == 0, (label, exe_result.stderr)
        assert _normalise(exe_result.stdout, exe_rank, exe_json, exe_dot) == _normalise(
            python_result.stdout, python_rank, python_json, python_dot
        ), label
        assert exe_result.stderr == python_result.stderr == "", label
        if artifacts is not None:
            assert artifacts[0].read_bytes() == artifacts[1].read_bytes(), label

    assert (
        (exe_dot / "graph.dot").read_text(encoding="utf-8").startswith("// NHI-Blast graph export")
    )
    graph = json.loads((exe_json / "graph.json").read_text(encoding="utf-8"))
    assert graph["graph"]["nodes"]
    assert graph["graph"]["edges"]

    report = tmp_path / "report" / "report.json"
    scan_args = [
        "scan",
        str(root),
        "--simulate-compromise",
        ACTION,
        "--format",
        "json",
        "--out",
        str(report.parent),
    ]
    assert _run(_exe(), scan_args, cwd=tmp_path, env=env).returncode == 0
    finding_id = json.loads(report.read_text(encoding="utf-8"))["findings"][0]["id"]
    explain_args = ["explain", finding_id, "--report", str(report)]
    exe_explain = _run(_exe(), explain_args, cwd=tmp_path, env=env)
    python_explain = _run(reference, explain_args, cwd=tmp_path, env=_reference_env())
    assert exe_explain.returncode == python_explain.returncode == 0
    assert exe_explain.stdout == python_explain.stdout
    assert exe_explain.stdout.startswith(f"Finding {finding_id}")


def test_hcl_fallback_is_bundled_and_matches_the_reference_cli(tmp_path: Path) -> None:
    root = _fixture_copy(tmp_path, FX10)
    exe_out = tmp_path / "hcl exe"
    python_out = tmp_path / "hcl python"
    args = ["scan", str(root), "--format", "json"]

    exe_result = _run(
        _exe(), [*args, "--out", str(exe_out)], cwd=tmp_path, env=_clean_env(tmp_path)
    )
    python_result = _run(
        _reference(), [*args, "--out", str(python_out)], cwd=tmp_path, env=_reference_env()
    )

    assert exe_result.returncode == python_result.returncode == 0
    assert exe_result.stderr == python_result.stderr == ""
    assert (exe_out / "report.json").read_bytes() == (python_out / "report.json").read_bytes()
    payload = json.loads((exe_out / "report.json").read_text(encoding="utf-8"))
    codes = {diagnostic["code"] for diagnostic in payload["diagnostics"]}
    assert "D-TF-HCL-LIMIT" in codes
    assert "D-TF-HCL-UNAVAILABLE" not in codes
    assert payload["scope_and_limits"][0] == "Scope: 1 workflow, 1 job, 5 Terraform resources."


def test_exit_codes_and_error_boundaries_match_the_reference_cli(tmp_path: Path) -> None:
    env = _clean_env(tmp_path)
    reference = _reference()
    blocking = tmp_path / "blocking"
    blocking.write_text("not a directory", encoding="utf-8")
    malformed = tmp_path / "malformed"
    workflow = malformed / ".github" / "workflows" / "broken.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("name: broken\non: push\njobs:\n  build:\n    steps: [\n", "utf-8")
    missing = tmp_path / "does-not-exist"
    cases = [
        (["scan", str(FX03), "--fail-on", "high"], 1),
        (["scan", str(FX03)], 0),
        (["scan", str(FX07), "--format", "xml"], 2),
        (["scan", str(missing)], 2),
        (["scan", str(FX07), "--fail-on", "high", "--format", "json", "--out", str(blocking)], 4),
        (["scan", str(malformed), "--strict"], 3),
        ([], 2),
        (["export", str(FX07)], 2),
        (["rank", str(FX07), "--format", "sarif"], 2),
        (["explain", "missing", "--report", str(missing)], 2),
    ]
    for args, expected in cases:
        exe_result = _run(_exe(), args, cwd=tmp_path, env=env)
        python_result = _run(reference, args, cwd=tmp_path, env=_reference_env())
        assert exe_result.returncode == expected, (args, exe_result.returncode, exe_result.stderr)
        assert python_result.returncode == expected, (args, python_result.returncode)
        assert exe_result.stderr == python_result.stderr, args


def _deny_writes(path: Path) -> str | None:
    principal = getpass.getuser()
    completed = subprocess.run(
        ["icacls", str(path), "/deny", f"{principal}:(W)"],
        capture_output=True,
        text=True,
        check=False,
    )
    return principal if completed.returncode == 0 else None


def _restore_writes(path: Path, principal: str) -> None:
    subprocess.run(
        ["icacls", str(path), "/remove:d", principal], capture_output=True, text=True, check=False
    )


def test_unwritable_output_directory_reports_an_output_error(tmp_path: Path) -> None:
    env = _clean_env(tmp_path)
    target = tmp_path / "unwritable"
    target.mkdir()
    principal = _deny_writes(target)
    if principal is None:
        pytest.skip("cannot create a deny-write ACL in this environment")
    try:
        result = _run(
            _exe(),
            ["scan", str(FX07), "--format", "json", "--out", str(target)],
            cwd=tmp_path,
            env=env,
        )
    finally:
        _restore_writes(target, principal)

    assert result.returncode == 4
    assert result.stderr.startswith("error: cannot write report.json")
    assert "Traceback" not in result.stderr


def test_runtime_makes_no_proxy_mediated_network_request(tmp_path: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(0.5)
    port = listener.getsockname()[1]
    env = _clean_env(tmp_path)
    proxy = f"http://127.0.0.1:{port}"
    env.update({"HTTP_PROXY": proxy, "HTTPS_PROXY": proxy, "ALL_PROXY": proxy, "NO_PROXY": ""})
    try:
        result = _run(
            _exe(),
            ["scan", str(FX07), "--format", "json", "--out", str(tmp_path / "offline")],
            cwd=tmp_path,
            env=env,
        )
        try:
            connection, _ = listener.accept()
        except TimeoutError:
            pass
        else:
            connection.close()
            pytest.fail("the executable attempted a network connection")
    finally:
        listener.close()

    assert result.returncode == 0, result.stderr
