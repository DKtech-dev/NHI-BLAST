"""Deterministic evaluation of the recovered labelled synthetic cases (AUD-01).

Each directory under tests/fixtures/labelled is a scan root; cases.json records the
expected label for one rule per case. The expectations were recovered verbatim from
the 2026-10-29 audit harness and are never regenerated from scanner output.

The sample is synthetic, small and rule-targeted. A clean run demonstrates regression
coverage for the labelled rules; it is not real-world detection accuracy.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
try:
    import nhi_blast  # noqa: F401
except ModuleNotFoundError:  # running from a source checkout with no installation
    sys.path.insert(0, str(PROJECT / "src"))

from nhi_blast.pipeline import ScanOptions, run_scan  # noqa: E402
from nhi_blast.report.html import html_report  # noqa: E402
from nhi_blast.report.json_report import report_json  # noqa: E402
from nhi_blast.report.sarif import sarif_report  # noqa: E402

FIXTURES = PROJECT / "tests" / "fixtures" / "labelled"
_CASE_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
_RULE_ID = re.compile(r"NHB-[A-Z]+-[0-9]{3}\Z")
# Assembled at runtime so repository secret scans stay strict without an allowlist.
_CANARY = "ghp_" + "Z" * 36


class EvaluationError(ValueError):
    """A fixed diagnostic for malformed evaluation inputs."""


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    rule: str
    expected: bool
    rationale: str
    canary_absent: bool = False


def _case(entry: Any) -> Case:
    if not isinstance(entry, dict):
        msg = "each labelled case must be an object"
        raise EvaluationError(msg)
    identifier = entry.get("id")
    rule = entry.get("rule")
    expected = entry.get("expected")
    rationale = entry.get("rationale")
    canary = entry.get("canary_absent", False)
    if not isinstance(identifier, str) or not _CASE_ID.fullmatch(identifier):
        msg = "labelled case id must match [a-z0-9][a-z0-9-]*"
        raise EvaluationError(msg)
    if not isinstance(rule, str) or not _RULE_ID.fullmatch(rule):
        msg = f"labelled case {identifier} has an invalid rule id"
        raise EvaluationError(msg)
    if not isinstance(expected, bool):
        msg = f"labelled case {identifier} must record a boolean expectation"
        raise EvaluationError(msg)
    if not isinstance(rationale, str) or not rationale.strip():
        msg = f"labelled case {identifier} needs a non-empty rationale"
        raise EvaluationError(msg)
    if not isinstance(canary, bool):
        msg = f"labelled case {identifier} canary_absent must be boolean"
        raise EvaluationError(msg)
    return Case(
        id=identifier,
        rule=rule,
        expected=expected,
        rationale=rationale,
        canary_absent=canary,
    )


def load_cases(fixtures_root: Path) -> tuple[dict[str, Any], tuple[Case, ...]]:
    manifest_path = fixtures_root / "cases.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = f"cannot read labelled-case manifest {manifest_path.name}"
        raise EvaluationError(msg) from exc
    if not isinstance(manifest, dict) or manifest.get("format_version") != "1.0":
        msg = "labelled-case manifest must be an object with format_version 1.0"
        raise EvaluationError(msg)
    scan = manifest.get("scan")
    selectors = scan.get("selectors") if isinstance(scan, dict) else None
    if (
        not isinstance(scan, dict)
        or not isinstance(scan.get("repo_slug"), str)
        or not isinstance(selectors, list)
        or not selectors
        or not all(isinstance(item, str) for item in selectors)
    ):
        msg = "labelled-case manifest scan block is invalid"
        raise EvaluationError(msg)
    provenance = manifest.get("provenance")
    limitations = manifest.get("limitations")
    if not isinstance(provenance, dict) or not isinstance(limitations, list) or not limitations:
        msg = "labelled-case manifest provenance or limitations are missing"
        raise EvaluationError(msg)
    if not all(isinstance(item, str) and item.strip() for item in limitations):
        msg = "labelled-case limitations must be non-empty strings"
        raise EvaluationError(msg)
    entries = manifest.get("cases")
    if not isinstance(entries, list) or not entries:
        msg = "labelled-case manifest has no cases"
        raise EvaluationError(msg)
    cases: list[Case] = []
    seen: set[str] = set()
    for entry in entries:
        case = _case(entry)
        if case.id in seen:
            msg = f"duplicate labelled case id: {case.id}"
            raise EvaluationError(msg)
        seen.add(case.id)
        cases.append(case)
    directories = sorted(path.name for path in fixtures_root.iterdir() if path.is_dir())
    if directories != sorted(case.id for case in cases):
        msg = "labelled fixture directories do not match the manifest"
        raise EvaluationError(msg)
    for case in cases:
        if not (fixtures_root / case.id / ".github" / "workflows" / "build.yml").is_file():
            msg = f"labelled case is missing its workflow file: {case.id}"
            raise EvaluationError(msg)
    return manifest, tuple(cases)


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(1 for row in rows if row["expected"] and row["actual"])
    fp = sum(1 for row in rows if not row["expected"] and row["actual"])
    fn = sum(1 for row in rows if row["expected"] and not row["actual"])
    tn = sum(1 for row in rows if not row["expected"] and not row["actual"])
    return {
        "sample": len(rows),
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
    }


def evaluate(fixtures_root: Path) -> dict[str, Any]:
    root = Path(fixtures_root)
    manifest, cases = load_cases(root)
    scan = manifest["scan"]
    repo_slug: str = scan["repo_slug"]
    selectors = tuple(str(item) for item in scan["selectors"])
    rows: list[dict[str, Any]] = []
    for case in cases:
        outcome = run_scan(
            ScanOptions(root=root / case.id, repo_slug=repo_slug, selectors=selectors)
        )
        observed = any(finding.rule == case.rule for finding in outcome.report.findings)
        row: dict[str, Any] = {
            "id": case.id,
            "rule": case.rule,
            "expected": case.expected,
            "actual": observed,
            "passed": case.expected == observed,
            "rationale": case.rationale,
            "canary_absent": None,
        }
        if case.canary_absent:
            payloads = (
                outcome.console_text,
                report_json(outcome.report),
                json.dumps(sarif_report(outcome.report), sort_keys=True),
                html_report(outcome.report),
            )
            row["canary_absent"] = all(_CANARY not in payload for payload in payloads)
        rows.append(row)
    return {
        "format_version": manifest["format_version"],
        "provenance": manifest["provenance"],
        "limitations": manifest["limitations"],
        "cases": rows,
        "metrics": _metrics(rows),
        "passed": all(row["passed"] and row["canary_absent"] is not False for row in rows),
    }


def _ratio(value: Any) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def render(summary: dict[str, Any]) -> str:
    lines = ["Labelled synthetic evaluation (not real-world accuracy):"]
    for row in summary["cases"]:
        status = "pass" if row["passed"] and row["canary_absent"] is not False else "FAIL"
        expected = "reported" if row["expected"] else "absent"
        actual = "reported" if row["actual"] else "absent"
        lines.append(
            f"  [{status}] {row['id']:<24} {row['rule']} expected={expected:<8} observed={actual}"
        )
    metrics = summary["metrics"]
    lines.append(
        f"metrics: TP={metrics['TP']} FP={metrics['FP']} FN={metrics['FN']} "
        f"TN={metrics['TN']} precision={_ratio(metrics['precision'])} "
        f"recall={_ratio(metrics['recall'])}"
    )
    lines.append("limitations:")
    lines.extend(f"  - {item}" for item in summary["limitations"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the recovered labelled synthetic evaluation (AUD-01)."
    )
    parser.add_argument("--fixtures", type=Path, default=FIXTURES)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = evaluate(args.fixtures)
    except EvaluationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json_out is not None:
        args.json_out.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if not args.quiet:
        print(render(summary))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
