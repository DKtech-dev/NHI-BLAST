"""Loop 3 coverage hardening tests for low-coverage module branches."""

from __future__ import annotations

import importlib
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from nhi_blast import __version__
from nhi_blast.core.config import Config, ConfigError
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    Breadth,
    Edge,
    EdgeKind,
    Finding,
    GraphData,
    Inputs,
    Lifetime,
    Node,
    NodeKind,
    Report,
    Severity,
    ToolInfo,
)
from nhi_blast.discovery.paths import OutsideRootError, PathGuard, normalise_rel_path, posix_join
from nhi_blast.oidc.breadth import (
    base_severity,
    classify_breadth,
    format_of_pattern,
    worst_breadth,
)
from nhi_blast.parsers.gha.triggers import _string_list, parse_triggers
from nhi_blast.parsers.yaml_marked import Marked, load_marked_document
from nhi_blast.report.explain import ExplainError, render_explanation

# ---------------------------------------------------------------------------
# 1. src/nhi_blast/__main__.py
# ---------------------------------------------------------------------------


def test_python_m_nhi_blast_version_subprocess() -> None:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run(
        [sys.executable, "-m", "nhi_blast", "--version"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0
    assert __version__ in proc.stdout


def test_python_m_nhi_blast_version_inprocess(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["nhi-blast", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("nhi_blast", run_name="__main__")
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out
    importlib.import_module("nhi_blast.__main__")


# ---------------------------------------------------------------------------
# 2. src/nhi_blast/oidc/breadth.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("repo:acme/shop:ref:refs/heads/main", "CLASSIC"),
        ("repo:acme@123/shop@456:ref:refs/heads/main", "IMMUTABLE"),
        ("repo:*", "UNKNOWN"),
        ("repo:*/*:ref:refs/heads/main", "UNKNOWN"),
        ("job_workflow_ref:acme/shop/.github/workflows/ci.yml", "UNKNOWN"),
        ("  *  ", "UNKNOWN"),
    ],
)
def test_format_of_pattern_branches(pattern: str, expected: str) -> None:
    assert format_of_pattern(pattern) == expected


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("", Breadth.ANY_ORG),
        ("*", Breadth.ANY_ORG),
        ("repo:*", Breadth.ANY_ORG),
        ("custom:*", Breadth.ANY_ORG),
        ("custom:exact-value", Breadth.REPO_ANY_CONTEXT),
        ("repo:single-segment:ref:refs/heads/main", Breadth.ANY_ORG),
        ("repo:*/shop:ref:refs/heads/main", Breadth.ANY_ORG),
        ("repo:?/shop:ref:refs/heads/main", Breadth.ANY_ORG),
        ("repo:ac*/shop:ref:refs/heads/main", Breadth.ANY_ORG),
        ("repo:acme/*:ref:refs/heads/main", Breadth.SAME_ORG),
        ("repo:acme/shop*:ref:refs/heads/main", Breadth.SAME_ORG),
        ("repo:acme/shop", Breadth.REPO_ANY_CONTEXT),
        ("repo:acme/shop:*", Breadth.REPO_ANY_CONTEXT),
        ("repo:acme/shop:environment:*", Breadth.REPO_ANY_CONTEXT),
        ("repo:acme/shop:environment:", Breadth.REPO_ANY_CONTEXT),
        ("repo:acme/shop:environment:production", Breadth.ENVIRONMENT),
        ("repo:acme/shop:pull_request", Breadth.REPO_PULL_REQUEST),
        ("repo:acme/shop:ref:refs/heads/*", Breadth.REPO_ANY_BRANCH),
        ("repo:acme/shop:ref:refs/heads/main", Breadth.EXACT_REF),
        ("repo:acme/shop:job_workflow_ref:*", Breadth.REPO_ANY_CONTEXT),
        ("repo:acme/shop:custom_context", Breadth.EXACT_REF),
    ],
)
def test_classify_breadth_branches(pattern: str, expected: Breadth) -> None:
    assert classify_breadth(pattern) is expected


def test_base_severity_and_worst_breadth() -> None:
    assert base_severity(Breadth.UNCONSTRAINED) is Severity.CRITICAL
    assert base_severity(Breadth.EXACT_REF) is Severity.INFO
    assert worst_breadth((Breadth.EXACT_REF, Breadth.SAME_ORG, Breadth.ENVIRONMENT)) is (
        Breadth.SAME_ORG
    )


# ---------------------------------------------------------------------------
# 3. src/nhi_blast/parsers/gha/triggers.py
# ---------------------------------------------------------------------------


def _on_node(yaml_text: str) -> Marked | None:
    loaded, _diags = load_marked_document(
        yaml_text, rel_path=".github/workflows/ci.yml", limits=Limits()
    )
    assert loaded is not None
    return loaded.get("on")


def test_triggers_missing_on_block() -> None:
    triggers, diags = parse_triggers(None, rel_path=".github/workflows/ci.yml")
    assert triggers == ()
    assert len(diags) == 1
    assert diags[0].code == "D-GHA-ON-MISSING"


def test_triggers_sequence_and_invalid_entries() -> None:
    node = _on_node("on: [push, pull_request, 123]\n")
    triggers, diags = parse_triggers(node, rel_path=".github/workflows/ci.yml")
    assert [t.event for t in triggers] == ["pull_request", "push"]
    assert len(diags) == 1
    assert diags[0].code == "D-GHA-TRIGGER-SHAPE"


def test_triggers_schedule_cron_list_and_non_schedule_sequence() -> None:
    yaml_text = (
        "on:\n"
        "  schedule:\n"
        "    - cron: '0 2 * * *'\n"
        "    - other: ignored\n"
        "  pull_request:\n"
        "    - opened\n"
        "    - synchronize\n"
    )
    triggers, diags = parse_triggers(_on_node(yaml_text), rel_path=".github/workflows/ci.yml")
    assert diags == ()
    by_event = {t.event: t for t in triggers}
    assert by_event["schedule"].types == ("0 2 * * *",)
    assert by_event["pull_request"].types == ("opened", "synchronize")


def test_triggers_scalar_filter_values_and_string_list_helper() -> None:
    yaml_text = "on:\n  push:\n    branches: main\n    tags: 123\n    unknown_filter: ignored\n"
    triggers, diags = parse_triggers(_on_node(yaml_text), rel_path=".github/workflows/ci.yml")
    assert diags == ()
    assert len(triggers) == 1
    assert triggers[0].branches == ("main",)
    assert triggers[0].tags == ()
    assert _string_list(None) == ()
    assert _string_list(Marked(value="v1", line=1, end_line=1)) == ("v1",)
    assert _string_list(Marked(value=42, line=1, end_line=1)) == ()
    str_triggers, str_diags = parse_triggers(
        _on_node("on: push\n"), rel_path=".github/workflows/ci.yml"
    )
    assert [t.event for t in str_triggers] == ["push"]
    assert str_diags == ()
    null_triggers, null_diags = parse_triggers(
        _on_node("on:\n  push:\n"), rel_path=".github/workflows/ci.yml"
    )
    assert [t.event for t in null_triggers] == ["push"]
    assert null_diags == ()


def test_triggers_non_string_seq_map_diagnostic() -> None:
    node = _on_node("on: 42\n")
    triggers, diags = parse_triggers(node, rel_path=".github/workflows/ci.yml")
    assert triggers == ()
    assert len(diags) == 1
    assert diags[0].code == "D-GHA-TRIGGER-SHAPE"


# ---------------------------------------------------------------------------
# 4. src/nhi_blast/core/config.py
# ---------------------------------------------------------------------------


def test_config_unreadable_file_raises_config_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.toml"
    with pytest.raises(ConfigError, match="cannot read config file"):
        Config.from_file(missing)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"bindings": False}, r"\[bindings\] must be a table"),
        ({"oidc": []}, r"\[oidc\] must be a table"),
        ({"ignore": ""}, r"\[ignore\] must be a table"),
        ({"limits": 0}, r"\[limits\] must be a table"),
        ({"bindings": {"unknown": {}}}, r"unknown config binding\(s\): unknown"),
        ({"oidc": {"bogus": "x"}}, r"unknown config key\(s\) under \[oidc\]: bogus"),
        ({"ignore": {"bogus": []}}, r"unknown config key\(s\) under \[ignore\]: bogus"),
        ({"oidc": {"sub_template": "repo"}}, r"\[oidc\]\.sub_template must be a list of strings"),
        ({"oidc": {"sub_template": [123]}}, r"\[oidc\]\.sub_template must be a list of strings"),
        ({"oidc": {"sub_template": ["repo", "extra"]}}, r"unknown key\(s\): extra"),
        ({"oidc": {"sub_template": []}}, r"must not be empty"),
        ({"repo_slug": 123}, r"repo_slug must be a string"),
        ({"bindings": {"roles": "not-a-table"}}, r"\[bindings\.roles\] must be a table of strings"),
        ({"bindings": {"roles": {"deploy": 99}}}, r"\[bindings\.roles\]\.deploy must be a string"),
        ({"ignore": {"rules": "NHB-GHA-001"}}, r"\[ignore\]\.rules must be a list of strings"),
    ],
)
def test_config_validation_errors(payload: dict[str, object], match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        Config.from_mapping(payload)


def test_config_valid_sub_template_and_role_binding() -> None:
    cfg = Config.from_mapping(
        {
            "oidc": {"sub_template": ["repo", "context"]},
            "bindings": {
                "roles": {"deploy": "arn:aws:iam::111122223333:role/deploy"},
                "credentials": {"TOKEN": "arn:aws:secretsmanager:us-east-1:111122223333:secret:s"},
            },
        }
    )
    assert cfg.sub_template == ("repo", "context")
    assert cfg.role_binding("deploy") == "arn:aws:iam::111122223333:role/deploy"
    assert cfg.role_binding("missing") is None
    assert cfg.credential_binding("TOKEN") is not None


# ---------------------------------------------------------------------------
# 5. src/nhi_blast/discovery/paths.py
# ---------------------------------------------------------------------------


def test_path_guard_outside_root_and_non_dir(tmp_path: Path) -> None:
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("hi", encoding="utf-8")
    with pytest.raises(OutsideRootError, match="not a directory"):
        PathGuard.create(not_a_dir)

    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    guard = PathGuard.create(root)
    assert guard.relative(outside) is None
    assert guard.contains(outside) is False
    with pytest.raises(OutsideRootError, match="escapes the scan root"):
        guard.require_inside(outside)


def test_path_guard_symlink_escape_and_resolve_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    inside = root / "inside.txt"
    inside.write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("escape", encoding="utf-8")

    escape_link = root / "escape.yml"
    escape_link.symlink_to(outside)
    safe_link = root / "safe.yml"
    safe_link.symlink_to(inside)

    guard = PathGuard.create(root)
    assert guard.is_symlink_escape(escape_link) is True
    assert guard.is_symlink_escape(safe_link) is False
    assert guard.is_symlink_escape(inside) is False
    assert guard.require_inside(inside) == inside.resolve()

    def _boom(_self: Path, *, _strict: bool = False) -> Path:
        msg = "symlink loop"
        raise RuntimeError(msg)

    monkeypatch.setattr(Path, "resolve", _boom)
    assert guard.relative(inside) is None
    with pytest.raises(OutsideRootError, match="cannot be resolved safely"):
        guard.require_inside(inside)


def test_path_helpers_posix_join_and_normalise() -> None:
    assert posix_join("a/", "/b/", "", "c.yml") == "a/b/c.yml"
    assert normalise_rel_path(f"a{os.sep}b{os.sep}c.yml") == "a/b/c.yml"


# ---------------------------------------------------------------------------
# 6. src/nhi_blast/report/explain.py
# ---------------------------------------------------------------------------


def _sample_report(
    *,
    nodes: tuple[Node, ...] = (),
    edges: tuple[Edge, ...] = (),
    findings: tuple[Finding, ...] = (),
) -> Report:
    return Report(
        tool=ToolInfo(version=__version__),
        inputs=Inputs(digest="0" * 64, repo_slug="acme/shop", repo_slug_source="cli"),
        graph=GraphData(nodes=nodes, edges=edges),
        findings=findings,
    )


def test_explain_missing_node_and_edge_fallback_and_empty_evidence() -> None:
    finding = Finding(
        id="F-001",
        rule="NHB-GHA-001",
        severity=Severity.HIGH,
        confidence=EvidenceClass.DECLARED,
        title="Test finding",
        message="Missing graph references should fall back cleanly.",
        evidence=(),
        path=("missing-node-id",),
        path_edges=("missing-edge-id",),
        assumptions=("A-TEST",),
        scenario=None,
    )
    bare_finding = Finding(
        id="F-002",
        rule="NHB-GHA-002",
        severity=Severity.LOW,
        confidence=EvidenceClass.DERIVED,
        title="Bare finding",
        message="No path or path_edges.",
    )
    report = _sample_report(findings=(finding, bare_finding))

    out1 = render_explanation(report, "F-001")
    assert "None recorded." in out1
    assert "Assumptions: A-TEST" in out1
    assert "1. missing-node-id" in out1
    assert "1. missing-edge-id" in out1

    out2 = render_explanation(report, "F-002")
    assert "Path:" not in out2
    assert "Path edges:" not in out2

    with pytest.raises(ExplainError, match="was not found"):
        render_explanation(report, "DOES-NOT-EXIST")


def test_explain_node_truncates_over_200_incident_edges_and_attrs() -> None:
    hub = Node(
        id="node:hub",
        kind=NodeKind.JOB,
        label="Hub Job",
        attrs={"nested": {"k": "v"}, "items": [1, 2]},
        evidence=(),
    )
    plain = Node(id="node:plain", kind=NodeKind.WORKFLOW, label="Plain", attrs={})
    ev = Evidence(cls=EvidenceClass.DECLARED, rule="R1", file="a.yml", line=1, detail="d")
    incoming = tuple(
        Edge(
            id=f"e:in:{i:03d}",
            kind=EdgeKind.CONTAINS,
            src=f"src:{i:03d}",
            dst="node:hub",
            lifetime=Lifetime.JOB_BOUND,
            confidence=EvidenceClass.DECLARED,
            evidence=(ev,),
        )
        for i in range(205)
    )
    outgoing = tuple(
        Edge(
            id=f"e:out:{i:03d}",
            kind=EdgeKind.HOLDS,
            src="node:hub",
            dst="node:plain" if i == 0 else f"dst:{i:03d}",
            lifetime=Lifetime.PERSISTENT,
            confidence=EvidenceClass.DECLARED,
            evidence=(),
        )
        for i in range(205)
    )
    report = _sample_report(nodes=(hub, plain), edges=incoming + outgoing)

    hub_text = render_explanation(report, "node:hub")
    assert "Incoming edges: 205" in hub_text
    assert "Outgoing edges: 205" in hub_text
    assert hub_text.count("... 5 more") == 2
    assert '{"k": "v"}' in hub_text

    plain_text = render_explanation(report, "node:plain")
    assert "Attributes:" not in plain_text

    edge_text = render_explanation(report, "e:out:000")
    assert "Attributes:" not in edge_text
    assert "Hub Job (node:hub)" in edge_text
    assert "Plain (node:plain)" in edge_text
