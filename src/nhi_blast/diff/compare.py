"""Comparability and the canonical diff of two saved reports (nhi-blast-diff/1.0).

Safety rule: a finding is only reported as resolved when the two analyses are demonstrably
comparable for it. Anything short of that is "not_observed" with machine-readable reasons,
because a false "resolved" is false assurance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from nhi_blast import __version__
from nhi_blast.analysis.findings import SCENARIO_RULES
from nhi_blast.core.canonical import digest_of
from nhi_blast.core.models import (
    CompletenessStatus,
    Finding,
    Report,
    ScenarioReport,
    Severity,
    severity_rank,
)
from nhi_blast.diff.families import families_for, status_worse
from nhi_blast.diff.keys import (
    KeyedFinding,
    edge_digest,
    edge_key,
    evidence_files,
    key_scenario,
    node_digest,
    pair_findings,
    path_signature,
)
from nhi_blast.report.model_json import report_dict

DIFF_SCHEMA = "nhi-blast-diff/1.0"

REASON_CODES: tuple[str, ...] = (
    "analyzer_changed",
    "rules_changed",
    "data_changed",
    "schema_changed",
    "context_changed",
    "scenario_missing",
    "scenario_incomplete",
    "dependency_degraded",
    "evidence_file_missing",
    "possible_rename",
    "ambiguous_match",
)
_REASON_ORDER = {code: index for index, code in enumerate(REASON_CODES)}

FINDING_CLASSES: tuple[str, ...] = ("new", "changed", "not_observed", "resolved", "unchanged")

# Analysis parameters that must be equal for a finding to be reported as resolved.
_CONTEXT_FIELDS = (
    "config_digest",
    "limits",
    "max_depth",
    "strict",
    "selectors",
    "oidc",
    "default_branch",
    "aws_account",
    "aws_region",
    "role_bindings",
    "credential_bindings",
    "sub_template",
    "ignore_rules",
    "ignore_paths",
)
_PLAIN_FIELDS = frozenset({"max_depth", "strict"})


class Comparability(StrEnum):
    COMPARABLE = "comparable"
    COMPARABLE_WITH_DRIFT = "comparable_with_drift"
    INCOMPARABLE = "incomparable"


@dataclass(frozen=True, slots=True)
class Assessment:
    status: Comparability
    incomparable: tuple[dict[str, Any], ...]
    drift: tuple[dict[str, Any], ...]


def report_digest(report: Report) -> str:
    """Digest of the saved report content; the optional timestamp is not part of it."""
    payload = report_dict(report)
    payload.pop("generated_at", None)
    return digest_of(payload)


def _major(schema_id: str) -> str:
    return schema_id.rsplit("/", 1)[-1].split(".", 1)[0]


def _shown(value: Any) -> Any:
    return value if isinstance(value, (bool, int)) else digest_of(value)


def _display(name: str, value: Any) -> Any:
    return value if name in _PLAIN_FIELDS else _shown(value)


def _context_values(report: Report) -> dict[str, Any]:
    context = report.context
    if context is None:
        return {}
    dumped = context.model_dump(mode="json")
    return {name: dumped[name] for name in _CONTEXT_FIELDS}


def _completeness_view(report: Report) -> dict[str, tuple[str, str]]:
    if report.completeness is None:
        return {}
    return {
        item.id: (
            item.status.value,
            digest_of([list(item.diagnostics), list(item.assumptions)]),
        )
        for item in report.completeness.items
    }


def _analyzer_drift(base: Report, head: Report) -> list[dict[str, Any]]:
    if base.context is None or head.context is None:
        return [
            {
                "code": "schema_changed",
                "field": "context",
                "base": "no-context" if base.context is None else base.schema_id,
                "head": "no-context" if head.context is None else head.schema_id,
            }
        ]
    left = base.context.analyzer
    right = head.context.analyzer
    drift: list[dict[str, Any]] = []
    for name in ("tool_version", "engine_semantics"):
        if getattr(left, name) != getattr(right, name):
            drift.append(
                {
                    "code": "analyzer_changed",
                    "field": name,
                    "base": getattr(left, name),
                    "head": getattr(right, name),
                }
            )
    if left.rules_digest != right.rules_digest:
        drift.append(
            {
                "code": "rules_changed",
                "field": "rules_digest",
                "base": left.rules_digest,
                "head": right.rules_digest,
            }
        )
    if left.data_digests != right.data_digests:
        names = sorted(
            name
            for name in set(left.data_digests) | set(right.data_digests)
            if left.data_digests.get(name) != right.data_digests.get(name)
        )
        rules_only = names == ["rules.yaml"] and left.rules_digest != right.rules_digest
        if not rules_only:
            drift.append(
                {
                    "code": "data_changed",
                    "field": "data_digests",
                    "names": names,
                    "base": digest_of(left.data_digests),
                    "head": digest_of(right.data_digests),
                }
            )
    return drift


def _completeness_drift(base: Report, head: Report) -> list[dict[str, Any]]:
    left = _completeness_view(base)
    right = _completeness_view(head)
    drift: list[dict[str, Any]] = []
    for name in sorted(set(left) | set(right)):
        before = left.get(name)
        after = right.get(name)
        if before is None or after is None:
            drift.append(
                {
                    "code": "completeness_changed",
                    "field": name,
                    "base": None if before is None else before[0],
                    "head": None if after is None else after[0],
                }
            )
        elif before[0] != after[0]:
            drift.append(
                {"code": "completeness_changed", "field": name, "base": before[0], "head": after[0]}
            )
        elif before[1] != after[1]:
            drift.append(
                {
                    "code": "completeness_changed",
                    "field": f"{name}.detail",
                    "base": before[1],
                    "head": after[1],
                }
            )
    return drift


def assess(base: Report, head: Report) -> Assessment:
    incomparable: list[dict[str, Any]] = []
    if _major(base.schema_id) != _major(head.schema_id):
        incomparable.append(
            {"code": "schema_major_mismatch", "base": base.schema_id, "head": head.schema_id}
        )
    if base.inputs.repo_slug != head.inputs.repo_slug:
        incomparable.append(
            {
                "code": "repo_slug_differs",
                "base": digest_of(base.inputs.repo_slug),
                "head": digest_of(head.inputs.repo_slug),
            }
        )
    base_selectors = {item.selector for item in base.scenarios}
    head_selectors = {item.selector for item in head.scenarios}
    if base_selectors != head_selectors and not (base_selectors & head_selectors):
        incomparable.append(
            {
                "code": "scenario_selectors_disjoint",
                "base": digest_of(sorted(base_selectors)),
                "head": digest_of(sorted(head_selectors)),
            }
        )
    drift: list[dict[str, Any]] = []
    if base.schema_id != head.schema_id or base.context is None or head.context is None:
        drift.append(
            {
                "code": "schema_changed",
                "field": "context",
                "base": base.schema_id if base.context is not None else "no-context",
                "head": head.schema_id if head.context is not None else "no-context",
            }
        )
    else:
        drift.extend(_analyzer_drift(base, head))
        left = _context_values(base)
        right = _context_values(head)
        for name in _CONTEXT_FIELDS:
            if left[name] != right[name]:
                drift.append(
                    {
                        "code": "context_changed",
                        "field": name,
                        "base": _display(name, left[name]),
                        "head": _display(name, right[name]),
                    }
                )
    drift.extend(_completeness_drift(base, head))
    if incomparable:
        status = Comparability.INCOMPARABLE
    elif drift:
        status = Comparability.COMPARABLE_WITH_DRIFT
    else:
        status = Comparability.COMPARABLE
    return Assessment(status=status, incomparable=tuple(incomparable), drift=tuple(drift))


# ------------------------------------------------------------------ resolved conditions


@dataclass(frozen=True, slots=True)
class _Resolution:
    """Everything the seven "resolved" conditions need, computed once per diff."""

    base: Report
    head: Report
    identity: tuple[str, ...]
    parameters: tuple[str, ...]
    base_status: dict[str, CompletenessStatus]
    head_status: dict[str, CompletenessStatus]
    base_scenarios: dict[str, ScenarioReport]
    head_scenarios: dict[str, ScenarioReport]
    head_budget: dict[str, bool]
    head_files: frozenset[str]
    base_sha: dict[str, str]
    head_by_sha: dict[str, frozenset[str]]


def _identity_reasons(base: Report, head: Report) -> tuple[str, ...]:
    if base.context is None or head.context is None:
        return ("schema_changed",)
    reasons: set[str] = set()
    if base.schema_id != head.schema_id:
        reasons.add("schema_changed")
    for entry in _analyzer_drift(base, head):
        reasons.add(entry["code"])
    return tuple(sorted(reasons, key=_REASON_ORDER.__getitem__))


def _parameter_reasons(base: Report, head: Report) -> tuple[str, ...]:
    if base.context is None or head.context is None:
        return ()
    if _context_values(base) != _context_values(head):
        return ("context_changed",)
    return ()


def _statuses(report: Report) -> dict[str, CompletenessStatus]:
    if report.completeness is None:
        return {}
    return {item.id: item.status for item in report.completeness.items}


def _resolution(base: Report, head: Report) -> _Resolution:
    head_by_sha: dict[str, set[str]] = {}
    for item in head.inputs.files:
        head_by_sha.setdefault(item.sha256, set()).add(item.path)
    budget = (
        {}
        if head.context is None
        else {item.selector: item.time_budget_exhausted for item in head.context.scenarios}
    )
    return _Resolution(
        base=base,
        head=head,
        identity=_identity_reasons(base, head),
        parameters=_parameter_reasons(base, head),
        base_status=_statuses(base),
        head_status=_statuses(head),
        base_scenarios={item.selector: item for item in base.scenarios},
        head_scenarios={item.selector: item for item in head.scenarios},
        head_budget=budget,
        head_files=frozenset(item.path for item in head.inputs.files),
        base_sha={item.path: item.sha256 for item in base.inputs.files},
        head_by_sha={key: frozenset(value) for key, value in head_by_sha.items()},
    )


def _report_level_reasons(res: _Resolution) -> list[str]:
    """Scenario-independent rules: no scenario both reports share may be incomplete in HEAD."""
    for selector, base_scenario in res.base_scenarios.items():
        head_scenario = res.head_scenarios.get(selector)
        if head_scenario is None:
            continue
        if (
            head_scenario.truncated
            or selector not in res.head_budget
            or res.head_budget[selector]
            or set(head_scenario.unresolved_inputs) - set(base_scenario.unresolved_inputs)
        ):
            return ["scenario_incomplete"]
    return []


def _scenario_reasons(finding: Finding, res: _Resolution) -> list[str]:
    if finding.rule not in SCENARIO_RULES:
        return _report_level_reasons(res)
    if finding.scenario is None:
        return []
    selector = finding.scenario
    head_scenario = res.head_scenarios.get(selector)
    if head_scenario is None:
        return ["scenario_missing"]
    base_scenario = res.base_scenarios.get(selector)
    base_unresolved = set() if base_scenario is None else set(base_scenario.unresolved_inputs)
    if (
        head_scenario.truncated
        or selector not in res.head_budget
        or res.head_budget[selector]
        or set(head_scenario.unresolved_inputs) - base_unresolved
    ):
        return ["scenario_incomplete"]
    return []


def _family_reasons(finding: Finding, res: _Resolution) -> list[str]:
    if res.base.completeness is None or res.head.completeness is None:
        return ["dependency_degraded"]
    for family in families_for(finding.rule):
        before = res.base_status.get(family.value, CompletenessStatus.NOT_PROVIDED)
        after = res.head_status.get(family.value, CompletenessStatus.NOT_PROVIDED)
        if status_worse(before, after):
            return ["dependency_degraded"]
    return []


def _file_reasons(finding: Finding, res: _Resolution) -> list[str]:
    files = evidence_files(finding)
    reasons: list[str] = []
    if any(name not in res.head_files for name in files):
        reasons.append("evidence_file_missing")
    for name in files:
        sha = res.base_sha.get(name)
        if sha is not None and res.head_by_sha.get(sha, frozenset()) - {name}:
            reasons.append("possible_rename")
            break
    return reasons


def _unobserved_reasons(finding: Finding, res: _Resolution) -> list[str]:
    reasons = [*res.identity, *res.parameters]
    reasons.extend(_scenario_reasons(finding, res))
    reasons.extend(_family_reasons(finding, res))
    reasons.extend(_file_reasons(finding, res))
    return reasons


# ------------------------------------------------------------------------ finding records


def _record(
    item: Finding,
    lk: str,
    klass: str,
    *,
    base: Finding | None,
    head: Finding | None,
) -> dict[str, Any]:
    return {
        "lk": lk,
        "rule": item.rule,
        "scenario": item.scenario,
        "class": klass,
        "title": item.title,
        "severity": item.severity.value,
        "base_severity": None if base is None else base.severity.value,
        "head_severity": None if head is None else head.severity.value,
        "base_id": None if base is None else base.id,
        "head_id": None if head is None else head.id,
        "path": list(item.path),
        "evidence_files": list(evidence_files(item)),
        "reasons": [],
        "changed_fields": [],
        "possible_rename_of": [],
        "ambiguous_match": False,
    }


def _changed_fields(left: KeyedFinding, right: KeyedFinding) -> list[str]:
    fields: list[str] = []
    if left.finding.severity != right.finding.severity:
        fields.append("severity")
    if left.finding.confidence != right.finding.confidence:
        fields.append("confidence")
    if left.evidence_digest != right.evidence_digest:
        fields.append("evidence")
    if left.finding.path != right.finding.path:
        fields.append("path")
    if left.finding.assumptions != right.finding.assumptions:
        fields.append("assumptions")
    return fields


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {name: index for index, name in enumerate(FINDING_CLASSES)}
    return sorted(
        records,
        key=lambda r: (
            order[r["class"]],
            severity_rank(Severity(r["severity"])),
            r["rule"],
            r["scenario"] or "",
            r["lk"],
            r["base_id"] or "",
            r["head_id"] or "",
        ),
    )


def _classify(base: Report, head: Report, res: _Resolution) -> list[dict[str, Any]]:
    pairing = pair_findings(base.findings, head.findings)
    records: list[dict[str, Any]] = []
    for left, right in pairing.pairs:
        fields = _changed_fields(left, right)
        record = _record(
            right.finding,
            right.lk,
            "changed" if fields else "unchanged",
            base=left.finding,
            head=right.finding,
        )
        record["changed_fields"] = fields
        records.append(record)

    base_paths = [item.path for item in base.inputs.files]
    head_paths = [item.path for item in head.inputs.files]
    head_open = list(pairing.head_unpaired)
    head_records: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(head_open):
        record = _record(item.finding, item.lk, "new", base=None, head=item.finding)
        record["ambiguous_match"] = item.lk in pairing.ambiguous
        head_records[index] = record

    for left in pairing.base_unpaired:
        reasons = _unobserved_reasons(left.finding, res)
        signature = path_signature(left.finding, base_paths)
        ambiguous = left.lk in pairing.ambiguous
        for index, item in enumerate(head_open):
            same_slot = item.finding.rule == left.finding.rule and key_scenario(
                item.finding
            ) == key_scenario(left.finding)
            if not same_slot:
                continue
            if path_signature(item.finding, head_paths) == signature:
                reasons.append("possible_rename")
                head_records[index]["possible_rename_of"].append(left.lk)
            elif (
                signature
                and item.finding.path
                and path_signature(item.finding, head_paths)[-1] == signature[-1]
            ):
                ambiguous = True
                head_records[index]["ambiguous_match"] = True
        if ambiguous:
            reasons.append("ambiguous_match")
        klass = "not_observed" if reasons else "resolved"
        record = _record(left.finding, left.lk, klass, base=left.finding, head=None)
        record["reasons"] = sorted(set(reasons), key=_REASON_ORDER.__getitem__)
        record["ambiguous_match"] = ambiguous
        records.append(record)

    for record in head_records.values():
        record["possible_rename_of"] = sorted(set(record["possible_rename_of"]))
        records.append(record)
    return _sort_records(records)


# ---------------------------------------------------------------------------- deltas


def _set_delta(before: set[str], after: set[str]) -> dict[str, list[str]]:
    return {"added": sorted(after - before), "removed": sorted(before - after)}


def _rotation_view(scenario: ScenarioReport) -> dict[str, list[str]]:
    view: dict[str, set[str]] = {}
    plan = scenario.rotation_plan
    for step in (*plan.containment, *plan.rotation, *plan.verify):
        for credential in step.credentials:
            view.setdefault(f"{step.phase.value}:{credential.id}", set()).update(step.depends_on)
    return {key: sorted(value) for key, value in view.items()}


def _scenario_delta(left: ScenarioReport, right: ScenarioReport) -> dict[str, Any]:
    base_e = {item.credential: item.ttl_seconds for item in left.partition.E}
    head_e = {item.credential: item.ttl_seconds for item in right.partition.E}
    base_z = {item.credential: item for item in left.partition.Z}
    head_z = {item.credential: item for item in right.partition.Z}
    z_changed: list[dict[str, Any]] = []
    for name in sorted(set(base_z) & set(head_z)):
        for field in ("survival_window", "lifetime", "criticality", "depth"):
            before = getattr(base_z[name], field)
            after = getattr(head_z[name], field)
            if before != after:
                z_changed.append(
                    {
                        "credential": name,
                        "field": field,
                        "base": getattr(before, "value", before),
                        "head": getattr(after, "value", after),
                    }
                )
    base_rot = _rotation_view(left)
    head_rot = _rotation_view(right)
    return {
        "selector": left.selector,
        "truncated": {"base": left.truncated, "head": right.truncated},
        "R": _set_delta(set(left.partition.R), set(right.partition.R)),
        "E": {
            **_set_delta(set(base_e), set(head_e)),
            "ttl_changed": [
                {"credential": name, "base": base_e[name], "head": head_e[name]}
                for name in sorted(set(base_e) & set(head_e))
                if base_e[name] != head_e[name]
            ],
        },
        "Z": {
            **_set_delta(set(base_z), set(head_z)),
            "added_details": [
                {
                    "credential": name,
                    "lifetime": head_z[name].lifetime.value,
                    "survival_window": head_z[name].survival_window,
                    "criticality": head_z[name].criticality,
                }
                for name in sorted(set(head_z) - set(base_z))
            ],
            "changed": z_changed,
        },
        "potential": _set_delta(set(left.potential), set(right.potential)),
        "unresolved_inputs": _set_delta(set(left.unresolved_inputs), set(right.unresolved_inputs)),
        "rotation_dependencies": {
            "added": sorted(set(head_rot) - set(base_rot)),
            "removed": sorted(set(base_rot) - set(head_rot)),
            "changed": [
                {"step": key, "base": base_rot[key], "head": head_rot[key]}
                for key in sorted(set(base_rot) & set(head_rot))
                if base_rot[key] != head_rot[key]
            ],
        },
    }


def _scenarios(base: Report, head: Report) -> dict[str, Any]:
    left = {item.selector: item for item in base.scenarios}
    right = {item.selector: item for item in head.scenarios}
    return {
        "compared": [
            _scenario_delta(left[name], right[name]) for name in sorted(set(left) & set(right))
        ],
        "only_in_base": sorted(set(left) - set(right)),
        "only_in_head": sorted(set(right) - set(left)),
    }


def _graph(base: Report, head: Report) -> dict[str, Any]:
    base_nodes = {node.id: node for node in base.graph.nodes}
    head_nodes = {node.id: node for node in head.graph.nodes}
    changed_nodes: list[dict[str, Any]] = []
    for name in sorted(set(base_nodes) & set(head_nodes)):
        before = node_digest(base_nodes[name])
        after = node_digest(head_nodes[name])
        fields = sorted(key for key in before if before[key] != after[key])
        if fields:
            changed_nodes.append(
                {"id": name, "kind": head_nodes[name].kind.value, "fields": fields}
            )

    def group(report: Report) -> dict[tuple[str, str, str], list[dict[str, str]]]:
        grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
        for edge in report.graph.edges:
            grouped.setdefault(edge_key(edge), []).append(edge_digest(edge))
        for members in grouped.values():
            members.sort(key=lambda item: sorted(item.items()))
        return grouped

    base_edges = group(base)
    head_edges = group(head)
    changed_edges: list[dict[str, Any]] = []
    for key in sorted(set(base_edges) & set(head_edges)):
        before_list = base_edges[key]
        after_list = head_edges[key]
        if before_list == after_list:
            continue
        fields = (
            ["multiplicity"]
            if len(before_list) != len(after_list)
            else sorted(
                {f for b, a in zip(before_list, after_list, strict=True) for f in b if b[f] != a[f]}
            )
        )
        changed_edges.append({"kind": key[0], "src": key[1], "dst": key[2], "fields": fields})

    def edge_item(key: tuple[str, str, str]) -> dict[str, str]:
        return {"kind": key[0], "src": key[1], "dst": key[2]}

    return {
        "nodes": {
            "added": [
                {"id": name, "kind": head_nodes[name].kind.value}
                for name in sorted(set(head_nodes) - set(base_nodes))
            ],
            "removed": [
                {"id": name, "kind": base_nodes[name].kind.value}
                for name in sorted(set(base_nodes) - set(head_nodes))
            ],
            "changed": changed_nodes,
        },
        "edges": {
            "added": [edge_item(key) for key in sorted(set(head_edges) - set(base_edges))],
            "removed": [edge_item(key) for key in sorted(set(base_edges) - set(head_edges))],
            "changed": changed_edges,
        },
    }


def _paths(base: Report, head: Report, records: list[dict[str, Any]]) -> dict[str, Any]:
    def view(report: Report) -> set[tuple[str, str, tuple[str, ...]]]:
        return {(item.rule, key_scenario(item), item.path) for item in report.findings}

    def item(entry: tuple[str, str, tuple[str, ...]]) -> dict[str, Any]:
        return {"rule": entry[0], "scenario": entry[1] or None, "path": list(entry[2])}

    left = view(base)
    right = view(head)
    return {
        "added": [item(entry) for entry in sorted(right - left)],
        "removed": [item(entry) for entry in sorted(left - right)],
        "changed": [
            {"lk": record["lk"], "rule": record["rule"], "scenario": record["scenario"]}
            for record in records
            if "path" in record["changed_fields"]
        ],
    }


def _diagnostics(base: Report, head: Report) -> dict[str, Any]:
    def counts(report: Report) -> dict[tuple[str, str, str], int]:
        result: dict[tuple[str, str, str], int] = {}
        for item in report.diagnostics:
            key = (item.level.value, item.code, item.file or "")
            result[key] = result.get(key, 0) + 1
        return result

    left = counts(base)
    right = counts(head)

    def entry(key: tuple[str, str, str], count: int) -> dict[str, Any]:
        return {"level": key[0], "code": key[1], "file": key[2] or None, "count": count}

    return {
        "added": [
            entry(key, right[key] - left.get(key, 0))
            for key in sorted(right)
            if right[key] > left.get(key, 0)
        ],
        "removed": [
            entry(key, left[key] - right.get(key, 0))
            for key in sorted(left)
            if left[key] > right.get(key, 0)
        ],
        "baseline": [],
    }


def _completeness_changes(base: Report, head: Report) -> list[dict[str, Any]]:
    left = _statuses(base)
    right = _statuses(head)
    changes: list[dict[str, Any]] = []
    for name in sorted(set(left) | set(right)):
        before = left.get(name)
        after = right.get(name)
        if before == after:
            continue
        if before is None or after is None:
            direction = "changed"
        elif status_worse(before, after):
            direction = "degraded"
        elif status_worse(after, before):
            direction = "improved"
        else:
            direction = "changed"
        changes.append(
            {
                "family": name,
                "base": None if before is None else before.value,
                "head": None if after is None else after.value,
                "direction": direction,
            }
        )
    return changes


def _side(report: Report) -> dict[str, Any]:
    analyzer = None
    if report.context is not None:
        identity = report.context.analyzer
        analyzer = {
            "tool_version": identity.tool_version,
            "engine_semantics": identity.engine_semantics,
            "rules_digest": identity.rules_digest,
            "data_digest": digest_of(identity.data_digests),
        }
    return {
        "report_digest": report_digest(report),
        "schema": report.schema_id,
        "repo_slug": report.inputs.repo_slug,
        "inputs_digest": report.inputs.digest,
        "completeness_digest": None if report.completeness is None else report.completeness.digest,
        "analyzer": analyzer,
    }


def diff_reports(base: Report, head: Report) -> dict[str, Any]:
    """Compare two reports. The result is plain JSON-compatible data (before baseline/gate)."""
    assessment = assess(base, head)
    payload: dict[str, Any] = {
        "schema": DIFF_SCHEMA,
        "tool": {"name": "nhi-blast", "version": __version__},
        "base": _side(base),
        "head": _side(head),
        "comparability": {
            "status": assessment.status.value,
            "incomparable": list(assessment.incomparable),
            "context_drift": list(assessment.drift),
        },
    }
    counts = dict.fromkeys(FINDING_CLASSES, 0)
    if assessment.status is Comparability.INCOMPARABLE:
        payload.update(
            {
                "summary": {"counts": counts},
                "findings": [],
                "paths": {"added": [], "removed": [], "changed": []},
                "scenarios": {"compared": [], "only_in_base": [], "only_in_head": []},
                "graph": {
                    "nodes": {"added": [], "removed": [], "changed": []},
                    "edges": {"added": [], "removed": [], "changed": []},
                },
                "diagnostics": {"added": [], "removed": [], "baseline": []},
                "completeness": [],
            }
        )
        return payload
    resolution = _resolution(base, head)
    records = _classify(base, head, resolution)
    for record in records:
        counts[record["class"]] += 1
    payload.update(
        {
            "summary": {"counts": counts},
            "findings": records,
            "paths": _paths(base, head, records),
            "scenarios": _scenarios(base, head),
            "graph": _graph(base, head),
            "diagnostics": _diagnostics(base, head),
            "completeness": _completeness_changes(base, head),
        }
    )
    return payload


__all__ = [
    "DIFF_SCHEMA",
    "FINDING_CLASSES",
    "REASON_CODES",
    "Assessment",
    "Comparability",
    "assess",
    "diff_reports",
    "report_digest",
]
