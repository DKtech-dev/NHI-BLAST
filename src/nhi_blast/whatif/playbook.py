"""Deterministic Markdown playbook for a what-if result.

Every item is a human task. The playbook carries owner placeholders, evidence references,
a verification task and rollback or validation notes; it executes nothing.
"""

from __future__ import annotations

import re
from pathlib import PureWindowsPath
from typing import Any

from nhi_blast.core.evidence import Evidence
from nhi_blast.core.models import Edge, Node, Report
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


def _revoke_section(builder: _Builder) -> None:
    builder.add("## 1. Revoke role sessions", "")
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
            f"Step 1.{number}: revoke sessions of role {_code(role)} (plan step {step['index']})",
            _evidence_lines(builder.nodes.get(str(role)), "role"),
            "In the IAM console confirm that the role carries the AWSRevokeOlderSessions inline "
            "policy, that its condition compares aws:TokenIssueTime with the cutoff above, and "
            "review CloudTrail for sessions of this role issued after the cutoff.",
            "Removing the inline policy undoes the deny for every user of the role. Try the "
            "change on a non-production role first and record the role's current inline "
            "policies before editing.",
            details,
        )
    builder.add("Caveats that apply to every revoke step:")
    for caveat in builder.payload["caveats"]:
        if caveat["id"].startswith("C-REVOKE"):
            builder.add(f"- {caveat['text']}")
    builder.add("")


def _containment_section(builder: _Builder) -> None:
    builder.add("## 2. Remove trust or disable entrypoint", "")
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
        if step["type"] == "remove_trust":
            title = f"Step 2.{number}: remove trust into {_code(step['args']['role'])}"
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
            title = f"Step 2.{number}: disable entrypoint {_code(step['args']['node'])}"
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
            [f"- Modelled edges removed: {len(removed)}"],
        )


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
    _revoke_section(builder)
    _containment_section(builder)
    _rotation_section(builder)
    _verify_section(builder)
    _tail_section(builder)
    return "\n".join(builder.lines).rstrip("\n") + "\n"


__all__ = ["render_playbook"]
