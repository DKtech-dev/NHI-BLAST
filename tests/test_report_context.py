"""Reproducibility record: ReportContext, canonical digests and integrity checks."""

from __future__ import annotations

import json
import shutil
import unicodedata
from pathlib import Path

import pytest

from nhi_blast import ENGINE_SEMANTICS, SCHEMA_VERSION
from nhi_blast.core.canonical import (
    CanonicalError,
    canonical_json,
    digest_of,
    normalize_rel_path,
    path_collisions,
)
from nhi_blast.core.context import integrity_failures
from nhi_blast.core.data import data_digests
from nhi_blast.core.models import Report
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.json_report import report_json, write_json
from nhi_blast.report.loader import load_report

FX07 = Path(__file__).parent / "fixtures" / "fx07-incident"
SELECTORS = ("action:tj-actions/changed-files@v45", "repo-write")


def _scan(root: Path, **kwargs: object) -> Report:
    options = ScanOptions(root=root, repo_slug="acme/app", selectors=SELECTORS, **kwargs)  # type: ignore[arg-type]
    return run_scan(options).report


def test_context_records_every_replay_parameter() -> None:
    report = _scan(FX07)
    context = report.context
    assert context is not None
    assert report.schema_id == SCHEMA_VERSION
    assert context.analyzer.engine_semantics == ENGINE_SEMANTICS
    assert context.analyzer.tool_version == report.tool.version
    assert context.analyzer.rules_digest == context.analyzer.data_digests["rules.yaml"]
    assert set(context.analyzer.data_digests) == {item.name for item in report.data_files}
    assert context.limits["max_closure_depth"] == context.max_depth
    assert context.scenarios
    assert {item.selector for item in context.scenarios} == {
        scenario.selector for scenario in report.scenarios
    }
    for item in context.scenarios:
        assert item.selector_kind
        assert item.start_nodes
        assert item.time_budget_exhausted is False


def test_context_survives_a_json_round_trip_with_intact_digests(tmp_path: Path) -> None:
    report = _scan(FX07)
    target = tmp_path / "report.json"
    write_json(report, target)
    loaded = load_report(target)
    assert loaded.context == report.context
    assert integrity_failures(loaded) == ()
    assert report_json(loaded) == report_json(report)


def test_tampered_graph_or_context_is_detected() -> None:
    report = _scan(FX07)
    assert report.context is not None
    changed_graph = report.model_copy(
        update={"graph": report.graph.model_copy(update={"edges": report.graph.edges[1:]})}
    )
    assert integrity_failures(changed_graph) == ("graph-digest-mismatch",)
    changed_context = report.model_copy(
        update={"context": report.context.model_copy(update={"strict": not report.context.strict})}
    )
    assert integrity_failures(changed_context) == ("context-digest-mismatch",)
    assert integrity_failures(report.model_copy(update={"context": None})) == ("context-missing",)


def test_context_is_identical_for_different_checkout_locations(tmp_path: Path) -> None:
    shallow = tmp_path / "a"
    deep = tmp_path / "very" / "deep nested" / "tmp-é" / "checkout"
    for destination in (shallow, deep):
        shutil.copytree(FX07, destination)
    first, second = _scan(shallow), _scan(deep)
    assert first.context is not None
    assert first.context == second.context
    assert first.inputs.digest == second.inputs.digest


def test_exhausted_time_budget_is_recorded_per_scenario(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    shutil.copytree(FX07, root)
    config = root / "budget.toml"
    config.write_text("[limits]\nscenario_time_budget_seconds = 0\n", encoding="utf-8")
    report = _scan(root, config_path=config)
    assert report.context is not None
    assert report.context.scenarios
    assert all(item.time_budget_exhausted for item in report.context.scenarios)


@pytest.mark.security
def test_credential_literal_in_a_binding_is_redacted_and_digest_still_verifies(
    tmp_path: Path,
) -> None:
    canary = "ghp_" + "Q" * 36
    root = tmp_path / "repo"
    shutil.copytree(FX07, root)
    config = root / "bindings.toml"
    config.write_text(f'[bindings.roles]\nci = "{canary}"\n', encoding="utf-8")
    report = _scan(root, config_path=config)
    target = tmp_path / "out.json"
    write_json(report, target)
    assert canary not in target.read_text(encoding="utf-8")
    assert integrity_failures(load_report(target)) == ()


def test_data_digests_ignore_line_ending_style() -> None:
    digests = data_digests()
    assert digests == dict(sorted(digests.items()))
    assert all(len(value) == 64 for value in digests.values())


# ------------------------------------------------------------------ canonical module


def test_canonical_json_is_key_order_independent_and_rejects_non_finite() -> None:
    assert canonical_json({"b": 1, "a": [2, {"d": 1, "c": 2}]}) == canonical_json(
        {"a": [2, {"c": 2, "d": 1}], "b": 1}
    )
    assert digest_of({"é": 1}) == digest_of(json.loads('{"\\u00e9": 1}'))
    for bad in (float("nan"), float("inf")):
        with pytest.raises(CanonicalError):
            canonical_json({"x": bad})


@pytest.mark.parametrize(
    "bad",
    ["", "/abs/x", "C:/x", "a\\b", "a/../b", "./a", "a//b", "a/./b", "a/", "a\x00b"],
)
def test_normalize_rel_path_rejects_non_canonical_paths(bad: str) -> None:
    with pytest.raises(CanonicalError):
        normalize_rel_path(bad)


def test_normalize_rel_path_uses_nfc() -> None:
    decomposed = unicodedata.normalize("NFD", ".github/workflows/café.yml")
    assert normalize_rel_path(decomposed) == unicodedata.normalize("NFC", decomposed)
    assert decomposed != normalize_rel_path(decomposed)


def test_path_collisions_flag_case_and_normalisation_only_differences() -> None:
    nfd = unicodedata.normalize("NFD", "a/café.yml")
    nfc = unicodedata.normalize("NFC", "a/café.yml")
    groups = path_collisions([nfd, nfc, "a/CI.yml", "a/ci.yml", "a/other.yml"])
    assert len(groups) == 2
    assert path_collisions(["a/x.yml", "a/y.yml"]) == ()


STATIC_KEY_WORKFLOW = """name: Static
on: push
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: aws-actions/configure-aws-credentials@v6
        with:
          aws-access-key-id: ${{ secrets.PROD_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.PROD_SECRET_ACCESS_KEY }}
          aws-region: us-east-1
"""


@pytest.mark.security
def test_config_file_is_named_by_a_relative_path_and_no_host_path_leaks(tmp_path: Path) -> None:
    role = "arn:aws:iam::111122223333:role/deploy-prod"
    config = f'[bindings.credentials]\nPROD_ACCESS_KEY_ID = "{role}"\n'
    reports: list[Report] = []
    roots: list[Path] = []
    for root in (tmp_path / "a", tmp_path / "deep" / "nested dir" / "b"):
        shutil.copytree(FX07, root)
        (root / ".github" / "workflows" / "static.yml").write_text(STATIC_KEY_WORKFLOW, "utf-8")
        (root / "nhi-blast.toml").write_text(config, "utf-8")
        reports.append(_scan(root))
        roots.append(root)
    first, second = reports
    evidence_files = {
        item.file for edge in first.graph.edges for item in edge.evidence if item.file
    }
    assert "nhi-blast.toml" in evidence_files
    assert report_json(first) == report_json(second)
    assert first.context == second.context
    for report, root in zip(reports, roots, strict=True):
        text = report_json(report)
        assert str(root) not in text
        assert root.as_posix() not in text
        assert str(root).replace("\\", "\\\\") not in text
