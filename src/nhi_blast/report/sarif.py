"""SARIF 2.1.0 report generation (spec 13.3)."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from nhi_blast.core.data import RuleDefinition, rules
from nhi_blast.core.evidence import Evidence, dedupe_evidence, evidence_sort_key
from nhi_blast.core.models import Edge, Finding, Report, Severity
from nhi_blast.report._text import safe_text

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA_URI = "https://json.schemastore.org/sarif-2.1.0.json"
MAX_RESULTS = 5000
_ABSOLUTE_WINDOWS = re.compile(r"^[A-Za-z]:")
_SECURITY_SEVERITY = {
    Severity.CRITICAL: "9.5",
    Severity.HIGH: "8.0",
    Severity.MEDIUM: "5.5",
    Severity.LOW: "3.0",
}
_LEVEL = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}


def _rule_level(severity: Severity) -> str:
    return _LEVEL[severity]


def _artifact_location(file_name: str | None) -> dict[str, str] | None:
    if not file_name:
        return None
    path = file_name.replace("\\", "/")
    if path.startswith("/") or _ABSOLUTE_WINDOWS.match(path):
        return None
    normalised = posixpath.normpath(path)
    if normalised in {"", ".", ".."} or normalised.startswith("../"):
        return None
    return {
        "uri": quote(normalised, safe="/-._~"),
        "uriBaseId": "%SRCROOT%",
    }


def _ordered_evidence(evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    return tuple(sorted(dedupe_evidence(evidence), key=evidence_sort_key))


def _primary_evidence(finding: Finding) -> Evidence | None:
    for item in _ordered_evidence(finding.evidence):
        if item.file:
            return item
    return None


def _physical_location(evidence: Evidence) -> dict[str, Any] | None:
    artifact = _artifact_location(evidence.file)
    if artifact is None:
        return None
    physical: dict[str, Any] = {"artifactLocation": artifact}
    if evidence.line is not None:
        physical["region"] = {"startLine": max(1, evidence.line)}
    return {"physicalLocation": physical}


def _fingerprint(finding: Finding) -> str:
    primary = _primary_evidence(finding)
    file_name = "" if primary is None else primary.file or ""
    payload = "|".join(
        (
            finding.rule,
            ",".join(sorted(finding.path)),
            file_name,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _rule_payload(rule: RuleDefinition) -> dict[str, Any]:
    description = safe_text(rule.full_description, 1000)
    help_text = safe_text(rule.help, 1000)
    return {
        "id": rule.id,
        "name": safe_text(rule.title, 200),
        "shortDescription": {"text": safe_text(rule.short_description, 500)},
        "fullDescription": {"text": description},
        "help": {
            "text": f"{safe_text(rule.title, 200)}\n\n{help_text}",
            "markdown": f"# {safe_text(rule.title, 200)}\n\n{help_text}",
        },
        "defaultConfiguration": {"level": _rule_level(rule.base_severity)},
        "properties": {
            "tags": list(rule.tags),
            "precision": rule.precision,
        },
    }


def _code_flow(finding: Finding, edges: dict[str, Edge]) -> dict[str, Any] | None:
    locations: list[dict[str, Any]] = []
    for edge_id_value in finding.path_edges:
        edge = edges.get(edge_id_value)
        if edge is None:
            continue
        evidence = next(
            (item for item in _ordered_evidence(edge.evidence) if item.file and item.line),
            None,
        )
        if evidence is None:
            continue
        location = _physical_location(evidence)
        if location is None:
            continue
        message = safe_text(
            edge.attrs.get("message", f"{edge.kind.value} edge"),
            500,
        )
        location["message"] = {"text": message}
        locations.append({"location": location})
    if not locations:
        return None
    return {"threadFlows": [{"locations": locations}]}


def _result_payload(
    finding: Finding,
    *,
    rule_index: dict[str, int],
    edges: dict[str, Edge],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ruleId": finding.rule,
        "ruleIndex": rule_index[finding.rule],
        "level": _LEVEL[finding.severity],
        "message": {"text": safe_text(finding.message, 4000)},
        "partialFingerprints": {"nhiBlast/v1": _fingerprint(finding)},
        "properties": {
            "confidence": finding.confidence.value,
            "assumptions": list(finding.assumptions),
        },
    }
    security_severity = _SECURITY_SEVERITY.get(finding.severity)
    if security_severity is not None:
        result["properties"]["security-severity"] = security_severity
    primary = _primary_evidence(finding)
    if primary is not None:
        location = _physical_location(primary)
        if location is not None:
            result["locations"] = [location]
    flow = _code_flow(finding, edges)
    if flow is not None:
        result["codeFlows"] = [flow]
    return result


def sarif_report(report: Report) -> dict[str, Any]:
    """Build a deterministic SARIF log for the report."""
    catalog = rules()
    definitions = catalog.all()
    rule_index = {definition.id: index for index, definition in enumerate(definitions)}
    edges = {edge.id: edge for edge in report.graph.edges}
    ordered = report.sorted_findings()
    kept = ordered[:MAX_RESULTS]
    results = [_result_payload(finding, rule_index=rule_index, edges=edges) for finding in kept]
    run: dict[str, Any] = {
        "tool": {
            "driver": {
                "name": report.tool.name,
                "version": report.tool.version,
                "informationUri": "https://example.invalid/nhi-blast",
                "rules": [_rule_payload(definition) for definition in definitions],
            }
        },
        "results": results,
    }
    dropped = len(ordered) - len(kept)
    if dropped:
        run["invocations"] = [
            {
                "executionSuccessful": True,
                "toolExecutionNotifications": [
                    {
                        "level": "warning",
                        "message": {
                            "text": (
                                f"{dropped} findings were omitted because GitHub accepts "
                                f"at most {MAX_RESULTS} results per upload."
                            )
                        },
                    }
                ],
            }
        ]
    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [run],
    }


def write_sarif(report: Report, path: Path) -> None:
    data = sarif_report(report)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
