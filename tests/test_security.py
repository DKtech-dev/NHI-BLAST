"""Adversarial input, path-containment and secret-leak regression tests."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from nhi_blast.core.diagnostics import Diagnostic
from nhi_blast.core.limits import Limits
from nhi_blast.discovery.paths import OutsideRootError, PathGuard
from nhi_blast.discovery.walker import FileKind, InputLoader, discover
from nhi_blast.parsers.terraform.tfhcl import parse_tf_hcl
from nhi_blast.parsers.terraform.tfjson import parse_tf_json
from nhi_blast.parsers.yaml_marked import load_marked_document
from nhi_blast.pipeline import ScanOptions, run_scan

pytestmark = pytest.mark.security


def _codes(diagnostics: tuple[Diagnostic, ...] | list[Diagnostic]) -> set[str]:
    return {item.code for item in diagnostics}


def _symlink(target: Path, link: Path) -> None:
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable in this environment: {exc}")


def _directory_link(target: Path, link: Path) -> None:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"directory junctions are unavailable: {result.stderr.strip()}")
        return
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable in this environment: {exc}")


def test_duplicate_normalized_yaml_keys_keep_last_value_and_first_line() -> None:
    marked, diagnostics = load_marked_document(
        "on: push\ntrue: pull_request\n", rel_path="dup.yml", limits=Limits()
    )

    assert marked is not None
    assert marked.get_str("on") == "pull_request"
    assert _codes(diagnostics) == {"D-YAML-DUPKEY"}
    assert diagnostics[0].line == 1


def test_only_first_yaml_document_is_read() -> None:
    marked, diagnostics = load_marked_document(
        "name: first\n---\nname: second\n", rel_path="multi.yml", limits=Limits()
    )

    assert diagnostics == ()
    assert marked is not None
    assert marked.get_str("name") == "first"


@pytest.mark.parametrize(
    ("text", "limits", "code"),
    [
        ("[[[[[x]]]]]", Limits(max_yaml_depth=4), "D-YAML-DEPTH"),
        ("a: b", Limits(max_yaml_nodes=2), "D-YAML-NODES"),
        (
            "a: &a [x]\nb: *a\nc: *a\nd: *a\n",
            Limits(alias_expansion_factor=2),
            "D-YAML-ALIAS",
        ),
        (
            "a0: &a0 [x]\na1: &a1 [*a0, *a0]\na2: &a2 [*a1, *a1]\n"
            "a3: &a3 [*a2, *a2]\na4: &a4 [*a3, *a3]\n",
            Limits(alias_expansion_factor=4),
            "D-YAML-ALIAS",
        ),
    ],
)
def test_hostile_yaml_limits_fail_closed(text: str, limits: Limits, code: str) -> None:
    marked, diagnostics = load_marked_document(text, rel_path="hostile.yml", limits=limits)

    assert marked is None
    assert code in _codes(diagnostics)


def test_yaml_exact_node_limit_is_accepted() -> None:
    marked, diagnostics = load_marked_document(
        "a: b", rel_path="boundary.yml", limits=Limits(max_yaml_nodes=3)
    )

    assert marked is not None
    assert diagnostics == ()


@pytest.mark.parametrize(
    ("parser", "label", "text", "code"),
    [
        (parse_tf_json, "broken.json", "{", "D-TF-PARSE"),
        (parse_tf_hcl, "broken.tf", 'resource "aws_iam_role" "broken" {', "D-TF-HCL-PARSE"),
    ],
)
def test_malformed_terraform_returns_diagnostic(
    parser: object, label: str, text: str, code: str
) -> None:
    result = parser(label, text, limits=Limits())

    assert result.facts is None
    assert code in _codes(result.diagnostics)


def test_deep_terraform_json_never_raises_recursion_error() -> None:
    depth = 1_200
    text = (
        '{"format_version":"1.0","values":{"root_module":'
        + '{"child_modules":[' * depth
        + "{}"
        + "]}" * depth
        + "}}"
    )
    result = parse_tf_json("deep.json", text, limits=Limits())

    assert result.facts is not None
    assert result.facts.resources == {}
    assert _codes(result.diagnostics) == {"D-TF-EMPTY"}


def test_json_nesting_beyond_decoder_limit_returns_a_safe_diagnostic() -> None:
    text = "[" * 100_000 + "]" * 100_000

    result = parse_tf_json("deeper.json", text, limits=Limits())

    assert result.facts is None
    # CPython 3.14's decoder accepts nesting that earlier versions reject, so the
    # safe outcome is either a parse diagnostic or the not-an-object diagnostic.
    assert _codes(result.diagnostics) in ({"D-TF-PARSE"}, {"D-TF-FORMAT"})


def test_malformed_terraform_shapes_are_skipped_not_fatal() -> None:
    payload = {
        "format_version": "1.0",
        "planned_values": {"root_module": {"resources": 5, "child_modules": "not-a-list"}},
        "resource_changes": 7,
    }

    result = parse_tf_json("shapes.json", json.dumps(payload), limits=Limits())

    assert result.facts is not None
    assert _codes(result.diagnostics) == {"D-TF-EMPTY"}


@pytest.mark.parametrize("kind", [FileKind.WORKFLOW, FileKind.TF_JSON])
def test_input_loader_enforces_exact_byte_limit(tmp_path: Path, kind: FileKind) -> None:
    guard = PathGuard.create(tmp_path)
    limits = Limits(max_yaml_policy_file_bytes=8, max_tf_json_bytes=8)
    exact = tmp_path / f"exact-{kind.value}"
    over = tmp_path / f"over-{kind.value}"
    exact.write_bytes(b"12345678")
    over.write_bytes(b"123456789")

    exact_loader = InputLoader(guard=guard, limits=limits)
    over_loader = InputLoader(guard=guard, limits=limits)
    assert exact_loader.load(exact, kind) is not None
    assert exact_loader.diagnostics == []
    assert over_loader.load(over, kind) is None
    assert _codes(over_loader.diagnostics) == {"D-IO-LIMIT"}


def test_invalid_utf8_is_diagnostic_not_exception(tmp_path: Path) -> None:
    path = tmp_path / "invalid.yml"
    path.write_bytes(b"name: \xff")
    loader = InputLoader(guard=PathGuard.create(tmp_path), limits=Limits())

    assert loader.load(path, FileKind.WORKFLOW) is None
    assert _codes(loader.diagnostics) == {"D-IO-ENCODING"}


def test_file_count_limit_allows_exact_boundary_and_rejects_excess(tmp_path: Path) -> None:
    for index in range(3):
        (tmp_path / f"{index}.txt").write_text("ignored", encoding="utf-8")

    exact = discover(tmp_path, limits=Limits(max_files=3))
    excess = discover(tmp_path, limits=Limits(max_files=2))

    assert exact.visited_files == 3
    assert exact.diagnostics == ()
    assert excess.visited_files == 2
    assert _codes(excess.diagnostics) == {"D-IO-LIMIT"}


def test_path_guard_rejects_relative_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    guard = PathGuard.create(root)

    with pytest.raises(OutsideRootError):
        guard.require_inside(root / ".." / "outside.json")


def test_escaping_symlink_is_never_opened_during_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps({"format_version": "1.0", "values": {"root_module": {}}}),
        encoding="utf-8",
    )
    link = root / "linked.json"
    _symlink(outside, link)
    opened: list[Path] = []
    original = Path.open

    def recording_open(self: Path, *args: object, **kwargs: object) -> object:
        opened.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", recording_open)
    result = discover(root, limits=Limits())

    assert result.files == ()
    assert _codes(result.diagnostics) == {"D-IO-SYMLINK"}
    assert outside not in opened
    assert link not in opened


def test_escaping_directory_link_is_never_traversed(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "outside.json").write_text(
        json.dumps({"format_version": "1.0", "values": {"root_module": {}}}),
        encoding="utf-8",
    )
    _directory_link(outside, root / "linked")

    result = discover(root, limits=Limits())

    assert result.files == ()
    assert _codes(result.diagnostics) == {"D-IO-SYMLINK"}


def test_real_pipeline_never_emits_literal_or_sensitive_values(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    workflow = root / ".github" / "workflows" / "release.yml"
    workflow.parent.mkdir(parents=True)
    token = "ghp_" + "Q" * 36
    workflow.write_text(
        "name: release\non: push\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n"
        f"    env:\n      TOKEN: {token}\n    steps:\n      - run: echo deploy\n",
        encoding="utf-8",
    )
    sentinel = "FIXTURE_ONLY_SENSITIVE_PIPELINE_SENTINEL"
    (root / "tfstate.json").write_text(
        json.dumps(
            {
                "format_version": "1.0",
                "values": {
                    "root_module": {
                        "resources": [
                            {
                                "address": "aws_secretsmanager_secret_version.current",
                                "mode": "managed",
                                "type": "aws_secretsmanager_secret_version",
                                "name": "current",
                                "values": {"secret_string": sentinel},
                                "sensitive_values": {"secret_string": True},
                            }
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    outcome = run_scan(
        ScanOptions(
            root=root,
            selectors=("repo-write",),
            formats=("console", "json", "sarif", "html"),
            out_dir=tmp_path / "out",
        )
    )
    outputs = [outcome.console_text, outcome.report.model_dump_json()]
    outputs.extend(path.read_text(encoding="utf-8") for path in outcome.written)

    assert len(outcome.written) == 3
    assert any(finding.rule == "NHB-GHA-005" for finding in outcome.report.findings)
    for output in outputs:
        assert token not in output
        assert token[4:20] not in output
        assert sentinel not in output
