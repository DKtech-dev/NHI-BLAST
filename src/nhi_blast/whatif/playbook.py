"""Deterministic Markdown playbook for a what-if result.

Every item is a human task. The playbook carries owner placeholders, evidence references,
a verification task and rollback or validation notes; it executes nothing.
"""

from __future__ import annotations

import re
from pathlib import PureWindowsPath
from typing import Any

from nhi_blast.analysis.reach import reach
from nhi_blast.core.evidence import Evidence, EvidenceClass
from nhi_blast.core.models import (
    AUTHORITY_EDGE_KINDS,
    Edge,
    EdgeKind,
    Node,
    NodeKind,
    Report,
)
from nhi_blast.report._text import safe_text
from nhi_blast.whatif import HEADER
from nhi_blast.whatif.sessions import AWS_REVOKE_URL

_DRIVE = re.compile(r"^[A-Za-z]:")
OWNER = "`<owner: assign a person or team>`"


def _code(value: object, limit: int = 300) -> str:
    return "`" + safe_text(value, limit).replace("`", "'") + "`"


def _location(item: Evidence) -> str:
    """Evidence location without a host path: absolute files are reduced to the file name."""
    file = item.file
    if file is not None and (file.startswith(("/", "\\")) or _DRIVE.match(file) or "\\" in file):
        name = PureWindowsPath(file).name
        return f"{name} (absolute path omitted)"
    return item.location()


def _evidence_lines(node: Node | Edge | None, label: str) -> list[str]:
    if node is None:
        return [f"- Evidence ({label}): not present in the saved graph"]
    items = sorted(node.evidence, key=lambda item: (_location(item), item.rule, item.cls.value))
    shown = [f"{_location(item)} [{item.cls.value.upper()} {item.rule}]" for item in items[:4]]
    text = "; ".join(safe_text(entry, 200) for entry in shown) or "no evidence recorded"
    return [f"- Evidence ({label}): {text}"]


class _Builder:
    def __init__(self, report: Report, payload: dict[str, Any]) -> None:
        self.report = report
        self.payload = payload
        self.nodes = {node.id: node for node in report.graph.nodes}
        self.edges = {edge.id: edge for edge in report.graph.edges}
        self.lines: list[str] = []

    def add(self, *items: str) -> None:
        self.lines.extend(items)

    def block(
        self,
        title: str,
        evidence: list[str],
        verify: str,
        rollback: str,
        details: list[str] | None = None,
    ) -> None:
        self.add(f"### {title}", "", f"- Owner: {OWNER}")
        self.add(*evidence)
        self.add(*(details or []))
        self.add(f"- Human verification task: {verify}")
        self.add(f"- Rollback / validation: {rollback}", "")

    def steps(self, *types: str) -> list[dict[str, Any]]:
        return [
            step
            for step in self.payload["steps"]
            if step["type"] in types and step["status"] in {"applied", "no_effect"}
        ]


def _resolve_role_id(builder: _Builder, ref: str) -> str:
    node = builder.nodes.get(ref)
    if node is not None and node.kind is NodeKind.AWS_ROLE:
        return node.id
    for candidate in builder.nodes.values():
        if candidate.kind is NodeKind.AWS_ROLE and ref in {
            candidate.label,
            candidate.attrs.get("arn"),
            candidate.attrs.get("address"),
        }:
            return candidate.id
    return ref


def _collateral_entrypoints(builder: _Builder, role_id: str) -> list[str]:
    """Return other workflow/job entrypoints in the graph that also reach `role_id`."""
    resolved = _resolve_role_id(builder, role_id)
    if resolved not in builder.nodes:
        return []
    incoming: dict[str, list[Edge]] = {}
    for edge in builder.report.graph.edges:
        if edge.confidence is EvidenceClass.UNKNOWN:
            continue
        if edge.attrs.get("repo_write") is True:
            continue
        if edge.kind in AUTHORITY_EDGE_KINDS or edge.kind is EdgeKind.CONTAINS:
            incoming.setdefault(edge.dst, []).append(edge)

    visited: set[str] = {resolved}
    queue: list[str] = [resolved]
    while queue:
        current = queue.pop()
        for edge in incoming.get(current, ()):
            if edge.src not in visited:
                visited.add(edge.src)
                queue.append(edge.src)

    compromised_starts: set[str] = {
        node_id for scenario in builder.report.scenarios for node_id in scenario.start_nodes
    }
    compromised_jobs: set[str] = {
        node_id
        for node_id in compromised_starts
        if node_id in builder.nodes and builder.nodes[node_id].kind is NodeKind.JOB
    }
    for edge in builder.report.graph.edges:
        if (
            edge.kind is EdgeKind.CONTAINS
            and edge.src in compromised_starts
            and edge.dst in builder.nodes
            and builder.nodes[edge.dst].kind is NodeKind.JOB
        ):
            compromised_jobs.add(edge.dst)

    reaching_jobs = [
        node_id
        for node_id in visited
        if node_id in builder.nodes and builder.nodes[node_id].kind is NodeKind.JOB
    ]
    collateral_jobs = [job_id for job_id in reaching_jobs if job_id not in compromised_jobs]

    jobs_by_workflow: dict[str, set[str]] = {}
    for edge in builder.report.graph.edges:
        if edge.kind is EdgeKind.CONTAINS and edge.dst in visited:
            jobs_by_workflow.setdefault(edge.src, set()).add(edge.dst)

    collateral_workflows = [
        node_id
        for node_id in visited
        if node_id in builder.nodes
        and builder.nodes[node_id].kind is NodeKind.WORKFLOW
        and node_id not in compromised_starts
        and not jobs_by_workflow.get(node_id)
    ]
    return sorted({*collateral_jobs, *collateral_workflows})


def _collateral_line(builder: _Builder, role_id: str) -> list[str]:
    others = _collateral_entrypoints(builder, role_id)
    if not others:
        return []
    listed = ", ".join(_code(item) for item in others)
    return [f"- **Collateral Impact**: other workflow(s)/job(s) also reach this role: {listed}"]


def _reachable_role_ids(report: Report) -> set[str]:
    nodes = {node.id: node for node in report.graph.nodes}
    reachable_roles: set[str] = set()
    for scenario in report.scenarios:
        starts = [node_id for node_id in scenario.start_nodes if node_id in nodes]
        if starts:
            for node_id in reach(report.graph, starts):
                node = nodes.get(node_id)
                if node is not None and node.kind is NodeKind.AWS_ROLE:
                    reachable_roles.add(node_id)
        for ecred in scenario.partition.E:
            cred_node = nodes.get(ecred.credential)
            if cred_node is not None:
                role_id = cred_node.attrs.get("role")
                if isinstance(role_id, str) and role_id in nodes:
                    reachable_roles.add(role_id)
    return reachable_roles


def _containment_section(builder: _Builder) -> None:
    builder.add("## 1. Remove trust or disable entrypoint", "")
    steps = builder.steps("remove_trust", "disable_entrypoint")
    if not steps:
        builder.add("No remove_trust or disable_entrypoint step is in the plan.", "")
        return
    for number, step in enumerate(steps, start=1):
        removed = list(step["effects"].get("removed_edges", []))
        evidence: list[str] = []
        for edge_id in removed[:6]:
            evidence.extend(_evidence_lines(builder.edges.get(edge_id), f"edge {_code(edge_id)}"))
        if not evidence:
            evidence = ["- Evidence: no edge was removed from the saved graph by this step"]
        details = [f"- Modelled edges removed: {len(removed)}"]
        if step["type"] == "remove_trust":
            role_ref = str(step["args"]["role"])
            title = f"Step 1.{number}: remove trust into {_code(role_ref)}"
            details.extend(_collateral_line(builder, role_ref))
            verify = (
                "In the role's trust policy confirm that the statement that accepts the "
                "principal is gone, and that existing sessions of the role are handled by a "
                "revocation step (removing trust does not end sessions already issued)."
            )
            rollback = (
                "Restore the previous trust policy document; keep a copy before editing and "
                "validate the change with the policy simulator or a test assumption."
            )
        else:
            title = f"Step 1.{number}: disable entrypoint {_code(step['args']['node'])}"
            verify = (
                "Confirm in the repository settings that the workflow or job can no longer "
                "start, and review recent runs for the exposure window."
            )
            rollback = (
                "Re-enable the workflow after the surviving credentials are rotated; validate "
                "with a run on a branch that has no deploy permissions."
            )
        builder.block(
            f"{title} (plan step {step['index']})",
            evidence,
            verify,
            rollback,
            details,
        )


def _revoke_section(builder: _Builder) -> None:
    builder.add("## 2. Revoke role sessions", "")
    steps = builder.steps("revoke_role_sessions")
    if not steps:
        builder.add("No revoke_role_sessions step is in the plan.", "")
        return
    for number, step in enumerate(steps, start=1):
        role = step["effects"].get("role", step["args"]["role"])
        cutoff = step["effects"].get("cutoff")
        source = step["effects"].get("cutoff_source", "missing")
        details = [
            f"- Modelled cutoff: {_code(cutoff) if cutoff else 'not available'} (source: {source})"
        ]
        if source == "assumed_revoked_at_plus_30s":
            details.append(
                "- The cutoff is revoked_at plus an ASSUMED 30 s propagation window "
                f"({AWS_REVOKE_URL}); it is not a guarantee."
            )
        details.extend(_collateral_line(builder, str(role)))
        for scenario in builder.payload["per_scenario"]:
            for row in scenario["after"]["revoked_access"]:
                if row["step"] != step["index"]:
                    continue
                details.append(
                    f"- Scenario {_code(scenario['selector'])}, "
                    f"session {_code(row['credential'])}: "
                    f"{row['display_state']} (validity {row['validity']}, access {row['access']}"
                    + (", conditional on propagation" if row["conditional_on_propagation"] else "")
                    + (", re-issue possible" if row["re_issue_possible"] else "")
                    + ")"
                )
        builder.block(
            f"Step 2.{number}: revoke sessions of role {_code(role)} (plan step {step['index']})",
            _evidence_lines(builder.nodes.get(str(role)), "role"),
            "In the IAM console confirm that the role carries the AWSRevokeOlderSessions inline "
            "policy, that its condition compares aws:TokenIssueTime with the cutoff above, and "
            "review CloudTrail for sessions of this role issued after the cutoff.",
            "Removing the inline policy undoes the deny for every user of the role. Try the "
            "change on a non-production role first and record the role's current inline "
            "policies before editing.",
            details,
        )
        cutoff_val = str(cutoff) if cutoff else "<YYYY-MM-DDTHH:MM:SSZ>"
        builder.add(
            "```json",
            "{",
            '  "Version": "2012-10-17",',
            '  "Statement": [',
            "    {",
            '      "Sid": "AWSRevokeOlderSessions",',
            '      "Effect": "Deny",',
            '      "Action": "*",',
            '      "Resource": "*",',
            '      "Condition": {',
            f'        "DateLessThan": {{"aws:TokenIssueTime": "{safe_text(cutoff_val, 64)}"}}',
            "      }",
            "    }",
            "  ]",
            "}",
            "```",
            "",
        )
    builder.add("Caveats that apply to every revoke step:")
    for caveat in builder.payload["caveats"]:
        if caveat["id"].startswith("C-REVOKE"):
            builder.add(f"- {caveat['text']}")
    builder.add("")


def _rotation_section(builder: _Builder) -> None:
    builder.add("## 3. Rotate surviving credentials in dependency order", "")
    for scenario in builder.payload["per_scenario"]:
        builder.add(f"### Scenario {_code(scenario['selector'])}", "")
        order = scenario["rotation_order"]
        if not order:
            builder.add("No persistent credential survives in this scenario.", "")
            continue
        for step in order:
            kind = (
                "batch (rotate together after freezing the principals)"
                if step["batch"]
                else "single"
            )
            builder.add(f"{step['order']}. Generation {step['generation']}, {kind}")
            for ref in step["credentials"]:
                notes = ["in plan" if ref["planned"] else "not in plan"]
                if ref["re_exposure_risk"]:
                    notes.append("re-exposure risk: a surviving path still reaches it")
                node = builder.nodes.get(ref["id"])
                location = ""
                if node is not None and node.evidence:
                    location = "; evidence " + safe_text(_location(node.evidence[0]), 160)
                builder.add(f"   - {_code(ref['id'])} ({', '.join(notes)}){location}")
            builder.add(
                f"   - Owner: {OWNER}",
                "   - Human verification task: confirm in the store that the new value is in "
                "use and that the old value no longer authenticates; do not copy values into "
                "this document.",
                "   - Rollback / validation: record the previous version identifier before "
                "changing it and confirm in your account whether the store keeps it.",
            )
        builder.add("")


def _verify_section(builder: _Builder) -> None:
    builder.add("## 4. Verify", "")
    builder.add(
        f"- Owner: {OWNER}",
        "- Human verification task: review CloudTrail inside the exposure window for the "
        "roles, sessions and stores named in this playbook; none of that was executed here.",
        "- Rollback / validation: compare the account state with the modelled result below "
        "and re-run nhi-blast on the updated repository to confirm the new report.",
        "",
    )
    for scenario in builder.payload["per_scenario"]:
        builder.add(f"### Scenario {_code(scenario['selector'])}", "")
        future = scenario["future_reach"]
        builder.add(
            f"- New runs could still reach: R={len(future['R'])}, E={len(future['E'])}, "
            f"Z={len(future['Z'])}"
        )
        for row in scenario["after"]["issued_before_containment"]:
            builder.add(
                f"- Session {_code(row['credential'])} may have been issued before "
                f"containment (modelled); at most {row['max_remaining_seconds']} s remain."
            )
        for row in scenario["after"]["re_exposure_risk"]:
            builder.add(f"- Re-exposure risk: {_code(row['credential'])}")
        for row in scenario["residual_paths"]:
            builder.add(
                f"- Residual {row['class']} path to {_code(row['credential'])} "
                f"({len(row['path_edges'])} edge(s))"
            )
        builder.add("")


def _persistence_audit_section(builder: _Builder) -> None:
    reachable_roles = _reachable_role_ids(builder.report)
    persist_roles = sorted(
        (
            node
            for node in builder.report.graph.nodes
            if node.kind is NodeKind.AWS_ROLE
            and node.id in reachable_roles
            and node.attrs.get("persistence_actions")
        ),
        key=lambda n: n.id,
    )
    if not persist_roles:
        return
    builder.add(
        "## Cloud Persistence Audit",
        "",
        "AWSRevokeOlderSessions and secret rotation do not revoke newly created IAM access keys, "
        "login profiles, or modified trust/identity policies. Audit CloudTrail for IAM mutations "
        "performed by the following reachable role(s):",
        "",
    )
    for role in persist_roles:
        actions = ", ".join(str(a) for a in role.attrs.get("persistence_actions", ()))
        builder.add(f"- Role {_code(role.label)} ({_code(role.id)}): {actions}")
    builder.add("")


def _tail_section(builder: _Builder) -> None:
    if builder.payload["rejected"]:
        builder.add("## Rejected plan entries", "")
        for row in builder.payload["rejected"]:
            detail = f" ({safe_text(row['detail'], 200)})" if "detail" in row else ""
            builder.add(f"- Step {row['index']} {_code(row['type'], 80)}: {row['reason']}{detail}")
        builder.add("")
    if builder.payload["warnings"]:
        builder.add("## Warnings", "")
        for item in builder.payload["warnings"]:
            builder.add(f"- {item['code']}: {safe_text(item['detail'], 200)}")
        builder.add("")


def render_playbook(report: Report, payload: dict[str, Any]) -> str:
    builder = _Builder(report, payload)
    builder.add(
        HEADER,
        "",
        "# Containment playbook (what-if)",
        "",
        f"- Source report digest: {_code(payload['source_report_digest'])}",
        f"- Plan digest: {_code(payload['plan_digest'])}",
        "- Every item is a human task. Owners, times and account details are placeholders.",
        "",
    )
    _containment_section(builder)
    _revoke_section(builder)
    _rotation_section(builder)
    _verify_section(builder)
    _persistence_audit_section(builder)
    _tail_section(builder)
    return "\n".join(builder.lines).rstrip("\n") + "\n"


__all__ = ["render_playbook"]
