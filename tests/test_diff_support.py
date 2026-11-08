"""Shared builders for the diff tests: real scans of mutated fixture copies."""

from __future__ import annotations

import functools
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nhi_blast.analysis.findings import SCENARIO_RULES
from nhi_blast.core.models import CompletenessStatus, Finding, Report
from nhi_blast.diff.compare import diff_reports
from nhi_blast.diff.families import RULE_FAMILIES
from nhi_blast.pipeline import ScanOptions, run_scan
from nhi_blast.report.model_json import report_dict

FIXTURES = Path(__file__).parent / "fixtures"
SELECTORS = ("repo-write",)
RELEASE = ".github/workflows/release.yml"


def scan_root(root: Path, selectors: tuple[str, ...] = SELECTORS) -> Report:
    return run_scan(
        ScanOptions(root=root, selectors=selectors, formats=("console",), out_dir=root / "_out")
    ).report


@functools.cache
def base_report() -> Report:
    return scan_root(FIXTURES / "fx07-incident")


def scan_variant(
    tmp_path: Path,
    mutate: Callable[[Path], None] | None = None,
    *,
    name: str = "variant",
    fixture: str = "fx07-incident",
    selectors: tuple[str, ...] = SELECTORS,
) -> Report:
    root = tmp_path / name
    shutil.copytree(FIXTURES / fixture, root)
    if mutate is not None:
        mutate(root)
    return scan_root(root, selectors)


def edit_file(root: Path, relative: str, old: str, new: str) -> None:
    path = root / relative
    text = path.read_text(encoding="utf-8")
    assert old in text, (relative, old)
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def with_context(report: Report, **changes: Any) -> Report:
    assert report.context is not None
    return report.model_copy(update={"context": report.context.model_copy(update=changes)})


def with_analyzer(report: Report, **changes: Any) -> Report:
    assert report.context is not None
    analyzer = report.context.analyzer.model_copy(update=changes)
    return with_context(report, analyzer=analyzer)


def with_scenario(report: Report, selector: str, **changes: Any) -> Report:
    scenarios = tuple(
        item.model_copy(update=changes) if item.selector == selector else item
        for item in report.scenarios
    )
    return report.model_copy(update={"scenarios": scenarios})


def with_family(report: Report, family: str, status: str) -> Report:
    assert report.completeness is not None
    items = tuple(
        item.model_copy(update={"status": CompletenessStatus(status)})
        if item.id == family
        else item
        for item in report.completeness.items
    )
    return report.model_copy(
        update={"completeness": report.completeness.model_copy(update={"items": items})}
    )


def classes(payload: dict[str, Any], klass: str) -> list[dict[str, Any]]:
    return [item for item in payload["findings"] if item["class"] == klass]


def counts(payload: dict[str, Any]) -> dict[str, int]:
    return dict(payload["summary"]["counts"])


def without_rule(report: Report, rule: str) -> Report:
    kept = tuple(item for item in report.findings if item.rule != rule)
    ids = {item.id for item in kept}
    scenarios = tuple(
        item.model_copy(update={"findings": tuple(f for f in item.findings if f in ids)})
        for item in report.scenarios
    )
    return report.model_copy(update={"findings": kept, "scenarios": scenarios})


def without_findings(report: Report) -> Report:
    return report.model_copy(update={"findings": ()})


def first_finding(report: Report, rule: str) -> Finding:
    return next(item for item in report.findings if item.rule == rule)


def replace_finding(report: Report, old: Finding, *new: Finding) -> Report:
    findings = tuple(item for item in report.findings if item != old) + tuple(new)
    return report.model_copy(update={"findings": findings})


def duplicate_of(finding: Finding, suffix: str = "-dup", **changes: Any) -> Finding:
    return finding.model_copy(update={"id": finding.id + suffix, **changes})


def add_scenario(report: Report, selector: str) -> Report:
    """Copy the first scenario (and its scenario-bound findings) under another selector."""
    assert report.context is not None
    source = report.scenarios[0]
    scenario = source.model_copy(update={"selector": selector})
    extra = tuple(
        item.model_copy(update={"id": f"{item.id}-{selector}", "scenario": selector})
        for item in report.findings
        if item.scenario == source.selector and item.rule in SCENARIO_RULES
    )
    context = report.context.model_copy(
        update={
            "selectors": (*report.context.selectors, selector),
            "scenarios": (
                *report.context.scenarios,
                report.context.scenarios[0].model_copy(update={"selector": selector}),
            ),
        }
    )
    return report.model_copy(
        update={
            "scenarios": (*report.scenarios, scenario),
            "findings": (*report.findings, *extra),
            "context": context,
        }
    )


def as_report_10(report: Report) -> Report:
    return report.model_copy(
        update={"schema_id": "nhi-blast-report/1.0", "context": None, "completeness": None}
    )


def save_report(report: Report, path: Path) -> Path:
    path.write_text(json.dumps(report_dict(report), sort_keys=True), encoding="utf-8")
    return path


_RANK = {
    CompletenessStatus.NOT_APPLICABLE: 0,
    CompletenessStatus.ANALYSED: 0,
    CompletenessStatus.PARTIALLY_ANALYSED: 1,
    CompletenessStatus.NOT_PROVIDED: 2,
    CompletenessStatus.NOT_SUPPORTED: 2,
}


def assert_resolved_sound(base: Report, head: Report, payload: dict[str, Any]) -> None:
    """Re-derive the seven "resolved" conditions from the two reports, independently."""
    for record in classes(payload, "resolved"):
        finding = next(item for item in base.findings if item.id == record["base_id"])
        assert base.context is not None
        assert head.context is not None
        assert base.completeness is not None
        assert head.completeness is not None
        # 1: analyzer identity byte-equal
        assert base.context.analyzer.model_dump_json() == head.context.analyzer.model_dump_json()
        assert base.schema_id == head.schema_id
        # 2: only input files differ
        for name in ("config_digest", "limits", "max_depth", "strict", "selectors", "oidc"):
            assert getattr(base.context, name) == getattr(head.context, name), name
        head_scenarios = {item.selector: item for item in head.scenarios}
        base_scenarios = {item.selector: item for item in base.scenarios}
        budgets = {item.selector: item for item in head.context.scenarios}
        # 3 and 4: scenario-bound rules need their own scenario; every other rule needs every
        # scenario both reports share to be complete, because its scenario field is attribution.
        if finding.rule in SCENARIO_RULES:
            checked = [] if finding.scenario is None else [finding.scenario]
            for selector in checked:
                assert selector in head_scenarios
        else:
            checked = [name for name in base_scenarios if name in head_scenarios]
        for selector in checked:
            assert not head_scenarios[selector].truncated
            assert not budgets[selector].time_budget_exhausted
            assert set(head_scenarios[selector].unresolved_inputs) <= set(
                base_scenarios[selector].unresolved_inputs
            )
        # 5: no family the rule depends on got worse
        before = {item.id: item.status for item in base.completeness.items}
        after = {item.id: item.status for item in head.completeness.items}
        for family in RULE_FAMILIES[finding.rule]:
            assert _RANK[after[family.value]] <= _RANK[before[family.value]], family
        # 6: every evidence file still exists at the same path
        head_files = {item.path for item in head.inputs.files}
        for item in finding.evidence:
            if item.file is not None:
                assert item.file in head_files, item.file
        # 7: no rename candidate
        base_paths = [item.path for item in base.inputs.files]
        head_paths = [item.path for item in head.inputs.files]

        def strip(nodes: tuple[str, ...], paths: list[str]) -> tuple[str, ...]:
            result = []
            for node in nodes:
                stripped = node
                for known in sorted(paths, key=len, reverse=True):
                    stripped = stripped.replace(known, "<file>")
                result.append(stripped)
            return tuple(result)

        signature = strip(finding.path, base_paths)

        def slot(item: Finding) -> str | None:
            return item.scenario if item.rule in SCENARIO_RULES else None

        for other in head.findings:
            if other.rule == finding.rule and slot(other) == slot(finding):
                assert strip(other.path, head_paths) != signature
        base_sha = {item.path: item.sha256 for item in base.inputs.files}
        for item in finding.evidence:
            sha = base_sha.get(item.file or "")
            if sha is not None:
                assert not any(
                    entry.sha256 == sha and entry.path != item.file for entry in head.inputs.files
                )


def diff_checked(base: Report, head: Report) -> dict[str, Any]:
    payload = diff_reports(base, head)
    assert_resolved_sound(base, head, payload)
    return payload
