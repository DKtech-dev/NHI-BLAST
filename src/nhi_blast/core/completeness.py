"""Evidence completeness: which families of inputs were analysed, and which were not.

Derived from facts the scan already has, never from a score. A family that was not
provided or is not supported means the report says nothing about it; it is not evidence
that nothing is there. Statuses are described in plan C6/C7 and surfaced in every output.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from nhi_blast.core.canonical import digest_of, path_collisions
from nhi_blast.core.diagnostics import Diagnostic, warning
from nhi_blast.core.models import (
    Completeness,
    CompletenessItem,
    CompletenessSource,
    CompletenessStatus,
    GraphData,
    InputFamily,
    InputFile,
    Inputs,
    NodeKind,
    ScenarioReport,
)

F = InputFamily
S = CompletenessStatus

FAMILY_LABELS: dict[InputFamily, str] = {
    F.GHA_WORKFLOWS: "GitHub Actions workflows",
    F.GHA_LOCAL_COMPOSITES: "local composite actions",
    F.GHA_REMOTE_CALLEES: "remote actions and reusable workflows",
    F.GH_ENVIRONMENT_PROTECTION: "GitHub environment protection",
    F.GH_BRANCH_PROTECTION: "GitHub branch protection",
    F.OIDC_SUBJECT_BINDING: "OIDC subject format binding",
    F.TF_PLAN_STATE: "Terraform plan/state JSON",
    F.TF_HCL: "Terraform HCL",
    F.TF_LOCAL_MODULES: "Terraform local modules",
    F.IAM_IDENTITY_POLICIES: "IAM identity and trust policies",
    F.IAM_MANAGED_POLICY_BODIES: "managed policy bodies",
    F.IAM_PERMISSION_BOUNDARIES: "permissions boundaries",
    F.IAM_SESSION_POLICIES: "session policies",
    F.AWS_SESSION_DURATION: "session duration",
    F.AWS_ORG_POLICIES: "SCPs and RCPs",
    F.AWS_RESOURCE_POLICIES: "resource policies",
    F.KMS_KEY_POLICIES: "KMS key policies",
    F.AWS_ROLE_CHAINING: "role chaining",
    F.LIVE_CLOUD_STATE: "live cloud state",
    F.ANALYSIS_BUDGET: "analysis limits",
}

# Every diagnostic code the tool can emit maps to the family it describes and whether it
# degrades that family. None means the code is not about input completeness. A string
# value "path" resolves the family from the file the diagnostic names.
_PATH = "path"
CODE_TO_FAMILY: dict[str, tuple[InputFamily | str | None, bool]] = {
    "D-IO-OUTSIDE-ROOT": (_PATH, True),
    "D-IO-SYMLINK": (_PATH, True),
    "D-IO-UNREADABLE": (_PATH, True),
    "D-IO-LIMIT": (_PATH, True),
    "D-IO-ENCODING": (_PATH, True),
    "D-YAML-NODES": (_PATH, True),
    "D-YAML-DEPTH": (_PATH, True),
    "D-YAML-ALIAS": (_PATH, True),
    "D-YAML-UNICODE": (_PATH, True),
    "D-YAML-TAG": (_PATH, True),
    "D-YAML-DUPKEY": (_PATH, True),
    "D-YAML-NODE": (_PATH, True),
    "D-YAML-PARSE": (_PATH, True),
    "D-YAML-EMPTY": (_PATH, True),
    "D-GHA-REMOTE-REUSABLE": (F.GHA_REMOTE_CALLEES, False),
    "D-GHA-REMOTE-OPAQUE": (F.GHA_REMOTE_CALLEES, False),
    "D-GHA-COMPOSITE-INVALID": (F.GHA_LOCAL_COMPOSITES, True),
    "D-GHA-COMPOSITE-MISSING": (F.GHA_LOCAL_COMPOSITES, True),
    "D-GHA-COMPOSITE-CYCLE": (F.GHA_LOCAL_COMPOSITES, True),
    "D-GHA-COMPOSITE-DEPTH": (F.GHA_LOCAL_COMPOSITES, True),
    "D-GHA-COMPOSITE-OPAQUE": (F.GHA_LOCAL_COMPOSITES, True),
    "D-GHA-STEP-SHAPE": (F.GHA_WORKFLOWS, True),
    "D-GHA-JOB-SHAPE": (F.GHA_WORKFLOWS, True),
    "D-GHA-JOB-USES": (F.GHA_WORKFLOWS, True),
    "D-GHA-STRUCT": (F.GHA_WORKFLOWS, True),
    "D-GHA-TRIGGER-SHAPE": (F.GHA_WORKFLOWS, True),
    "D-GHA-ON-MISSING": (F.GHA_WORKFLOWS, True),
    "D-GHA-PERM-VALUE": (F.GHA_WORKFLOWS, True),
    "D-GHA-PERM-SHAPE": (F.GHA_WORKFLOWS, True),
    "D-GHA-PERM-SCOPE": (F.GHA_WORKFLOWS, True),
    "D-EXPR-VALUE": (F.GHA_WORKFLOWS, True),
    "D-GHA-UNSUPPORTED-CONSUMER": (F.GHA_WORKFLOWS, True),
    "D-GHA-AWS-ROLE-EXPR": (F.IAM_IDENTITY_POLICIES, False),
    "D-GHA-SELF-HOSTED": (None, False),
    "D-GHA-SECRETS-ALL": (None, False),
    "D-GHA-UNTRUSTED-CHECKOUT": (None, False),
    "D-GHA-REUSABLE-MULTI-CALLER": (None, False),
    "D-GHA-ROLE-CHAINING": (F.AWS_ROLE_CHAINING, False),
    "D-CAC-DURATION-INVALID": (F.AWS_SESSION_DURATION, True),
    "D-IAM-PARSE": (F.IAM_IDENTITY_POLICIES, True),
    "D-IAM-SHAPE": (F.IAM_IDENTITY_POLICIES, True),
    "D-IAM-EMPTY": (F.IAM_IDENTITY_POLICIES, True),
    "D-IAM-UNBOUND": (F.IAM_IDENTITY_POLICIES, True),
    "D-IAM-ROLE-ONLY": (F.IAM_IDENTITY_POLICIES, True),
    "D-TF-PARSE": (F.TF_PLAN_STATE, True),
    "D-TF-FORMAT": (F.TF_PLAN_STATE, True),
    "D-TF-EMPTY": (F.TF_PLAN_STATE, True),
    "D-TF-UNKNOWN": (F.TF_PLAN_STATE, True),
    "D-TF-ROLE-UNBOUND": (F.TF_PLAN_STATE, True),
    "D-TF-ROTATION-UNBOUND": (F.TF_PLAN_STATE, True),
    "D-TF-ROTATION-CONFLICT": (F.TF_PLAN_STATE, True),
    "D-TF-SINK-UNBOUND": (F.TF_PLAN_STATE, True),
    "D-TF-DB-UNBOUND": (F.TF_PLAN_STATE, True),
    "D-TF-HCL-PARSE": (F.TF_HCL, True),
    "D-TF-HCL-UNAVAILABLE": (F.TF_HCL, True),
    "D-TF-HCL-LIMIT": (F.TF_HCL, True),
    "D-TF-POLICY-SHAPE": (F.IAM_MANAGED_POLICY_BODIES, True),
    "D-TF-POLICY-UNRESOLVED": (F.IAM_MANAGED_POLICY_BODIES, True),
    "D-TF-BOUNDARY-UNRESOLVED": (F.IAM_PERMISSION_BOUNDARIES, True),
    "D-COND-UNSUPPORTED-OP": (F.IAM_IDENTITY_POLICIES, True),
    "D-COND-MALFORMED": (F.IAM_IDENTITY_POLICIES, True),
    "D-COND-POLICY-VARIABLE": (F.IAM_IDENTITY_POLICIES, True),
    "D-COND-AMBIGUOUS": (F.IAM_IDENTITY_POLICIES, True),
    "D-COND-UNKNOWN-KEY": (F.IAM_IDENTITY_POLICIES, True),
    "D-GRAPH-LIMIT": (F.ANALYSIS_BUDGET, True),
    "D-ANALYSIS-TIME": (F.ANALYSIS_BUDGET, True),
    "D-DATA-ASSUMPTION": (None, False),
    "D-DATA-STALE": (None, False),
    "D-FINDING-IGNORED": (None, False),
    "D-PATH-COLLISION": (None, False),
}

# Assumption and heuristic ids and the family they qualify. None: not about completeness.
ASSUMPTION_TO_FAMILY: dict[str, InputFamily | None] = {
    "A-STEP-SHARE": None,
    "A-RUNNER-SECRETS": None,
    "A-OIDC-ENV": None,
    "A-DEFAULT-NO-IDTOKEN": None,
    "A-FORK-NO-OIDC": None,
    "A-PRT-SUB": None,
    "A-DISPATCH-ANYREF": F.GH_BRANCH_PROTECTION,
    "A-ENV-UNPROTECTED": F.GH_ENVIRONMENT_PROTECTION,
    "A-STS-TTL": F.AWS_SESSION_DURATION,
    "A-CAC-DEFAULT": F.AWS_SESSION_DURATION,
    "A-SESSION-POLICY": F.IAM_SESSION_POLICIES,
    "A-NO-SCP": F.AWS_ORG_POLICIES,
    "A-SCOPE-INPUT": F.IAM_IDENTITY_POLICIES,
    "A-DEFAULT-BRANCH": None,
    "A-REPO-AGE": F.OIDC_SUBJECT_BINDING,
    "A-REPO-WRITE": F.GH_BRANCH_PROTECTION,
    "A-KMS-UNMODELLED": F.KMS_KEY_POLICIES,
    "A-TRUST-UNMODELLED": F.IAM_IDENTITY_POLICIES,
    "A-POLICY-UNMODELLED": F.IAM_MANAGED_POLICY_BODIES,
    "A-REUSABLE-CALLER": None,
    "H-SECRET-NAME": None,
    "H-ROT-WINDOW": None,
    "H-LITERAL": None,
}

_KIND_TO_FAMILY = {
    "workflow": F.GHA_WORKFLOWS,
    "composite_action": F.GHA_LOCAL_COMPOSITES,
    "tf_json": F.TF_PLAN_STATE,
    "tf_hcl": F.TF_HCL,
    "iam_json": F.IAM_IDENTITY_POLICIES,
}
# Never analysed by any version, whatever the inputs.
ALWAYS_OUT_OF_SCOPE = ("job outputs and artifacts",)
_UNVERIFIED_REQUESTS = frozenset({"unknown", "not_requested", "action_default_unverified"})


@dataclass(frozen=True, slots=True)
class WorkflowFacts:
    """Facts about the workflows that are not visible in the graph."""

    remote_callees: bool = False
    environment_jobs: bool = False


def _family_from_path(path: str | None, kinds: dict[str, str]) -> InputFamily:
    if path is None:
        return F.GHA_WORKFLOWS
    known = kinds.get(path)
    if known is not None and known in _KIND_TO_FAMILY:
        return _KIND_TO_FAMILY[known]
    lowered = path.lower()
    if ".github/workflows/" in lowered:
        return F.GHA_WORKFLOWS
    if ".github/actions/" in lowered or lowered.rsplit("/", 1)[-1].startswith("action."):
        return F.GHA_LOCAL_COMPOSITES
    if lowered.endswith((".tf.json", ".tfstate")) or "plan" in lowered.rsplit("/", 1)[-1]:
        return F.TF_PLAN_STATE
    if lowered.endswith(".tf"):
        return F.TF_HCL
    if lowered.endswith(".json"):
        return F.IAM_IDENTITY_POLICIES
    return F.GHA_WORKFLOWS


def path_collision_diagnostics(files: Iterable[InputFile]) -> tuple[Diagnostic, ...]:
    """Input paths that differ only by Unicode normalisation or case collide on some systems."""
    return tuple(
        warning(
            "D-PATH-COLLISION",
            "input paths differ only by Unicode normalisation or case: " + ", ".join(group),
            file=group[0],
        )
        for group in path_collisions(item.path for item in files)
    )


def _node_attrs(graph: GraphData, kind: NodeKind) -> list[dict[str, object]]:
    return [dict(node.attrs) for node in graph.nodes if node.kind is kind]


def _status_for(
    *,
    present: bool,
    degraded: bool,
    absent: CompletenessStatus,
) -> CompletenessStatus:
    if not present:
        return absent
    return S.PARTIALLY_ANALYSED if degraded else S.ANALYSED


def derive_completeness(
    *,
    inputs: Inputs,
    graph: GraphData,
    scenarios: Sequence[ScenarioReport],
    diagnostics: Sequence[Diagnostic],
    used_assumptions: Collection[str],
    workflow_facts: WorkflowFacts,
    format_declared: bool,
) -> Completeness:
    kinds = {item.path: item.kind for item in inputs.files}
    by_family_files: dict[InputFamily, list[InputFile]] = {}
    for item in inputs.files:
        family = _KIND_TO_FAMILY.get(item.kind)
        if family is not None:
            by_family_files.setdefault(family, []).append(item)

    degraded: dict[InputFamily, set[str]] = {}
    mentioned: dict[InputFamily, set[str]] = {}
    for diagnostic in diagnostics:
        entry = CODE_TO_FAMILY.get(diagnostic.code)
        if entry is None or entry[0] is None:
            continue
        target = entry[0]
        family = (
            _family_from_path(diagnostic.file, kinds) if target == _PATH else InputFamily(target)
        )
        mentioned.setdefault(family, set()).add(diagnostic.code)
        if entry[1]:
            degraded.setdefault(family, set()).add(diagnostic.code)
    if any(item.truncated for item in scenarios):
        degraded.setdefault(F.ANALYSIS_BUDGET, set())

    roles = _node_attrs(graph, NodeKind.AWS_ROLE)
    sinks = [node for node in graph.nodes if node.kind is NodeKind.SINK]
    sessions = [
        attrs
        for attrs in _node_attrs(graph, NodeKind.CREDENTIAL)
        if attrs.get("credential_kind") == "STS_SESSION"
    ]
    has_oidc = any(node.id.startswith("oidc:") for node in graph.nodes)
    has_workflows = bool(by_family_files.get(F.GHA_WORKFLOWS))
    used = set(used_assumptions)
    hcl_module_gap = any(
        d.code == "D-TF-HCL-LIMIT" and "module blocks" in d.message for d in diagnostics
    )

    def has(family: InputFamily) -> bool:
        return family in degraded

    def used_for(family: InputFamily) -> bool:
        return any(ASSUMPTION_TO_FAMILY.get(item) is family for item in used)

    status: dict[InputFamily, CompletenessStatus] = {}
    status[F.GHA_WORKFLOWS] = _status_for(
        present=has_workflows, degraded=has(F.GHA_WORKFLOWS), absent=S.NOT_PROVIDED
    )
    composites = bool(by_family_files.get(F.GHA_LOCAL_COMPOSITES))
    status[F.GHA_LOCAL_COMPOSITES] = _status_for(
        present=composites or has(F.GHA_LOCAL_COMPOSITES),
        degraded=has(F.GHA_LOCAL_COMPOSITES),
        absent=S.NOT_APPLICABLE,
    )
    status[F.GHA_REMOTE_CALLEES] = (
        S.NOT_SUPPORTED if workflow_facts.remote_callees else S.NOT_APPLICABLE
    )
    status[F.GH_ENVIRONMENT_PROTECTION] = (
        S.NOT_PROVIDED if workflow_facts.environment_jobs else S.NOT_APPLICABLE
    )
    status[F.GH_BRANCH_PROTECTION] = S.NOT_PROVIDED if has_workflows else S.NOT_APPLICABLE
    status[F.OIDC_SUBJECT_BINDING] = _status_for(
        present=has_oidc,
        degraded=not format_declared,
        absent=S.NOT_APPLICABLE,
    )
    status[F.TF_PLAN_STATE] = _status_for(
        present=bool(by_family_files.get(F.TF_PLAN_STATE)),
        degraded=has(F.TF_PLAN_STATE),
        absent=S.NOT_PROVIDED,
    )
    status[F.TF_HCL] = _status_for(
        present=bool(by_family_files.get(F.TF_HCL)),
        degraded=has(F.TF_HCL),
        absent=S.NOT_PROVIDED,
    )
    status[F.TF_LOCAL_MODULES] = S.NOT_SUPPORTED if hcl_module_gap else S.NOT_APPLICABLE
    status[F.IAM_IDENTITY_POLICIES] = _status_for(
        present=bool(roles) or bool(by_family_files.get(F.IAM_IDENTITY_POLICIES)),
        degraded=has(F.IAM_IDENTITY_POLICIES) or used_for(F.IAM_IDENTITY_POLICIES),
        absent=S.NOT_PROVIDED,
    )
    unresolved_bodies = any(attrs.get("unresolved_policy_refs") for attrs in roles)
    status[F.IAM_MANAGED_POLICY_BODIES] = _status_for(
        present=bool(roles),
        degraded=unresolved_bodies
        or has(F.IAM_MANAGED_POLICY_BODIES)
        or used_for(F.IAM_MANAGED_POLICY_BODIES),
        absent=S.NOT_APPLICABLE,
    )
    boundaries = [bool(attrs.get("has_boundary")) for attrs in roles]
    if not roles:
        status[F.IAM_PERMISSION_BOUNDARIES] = S.NOT_APPLICABLE
    elif not any(boundaries):
        status[F.IAM_PERMISSION_BOUNDARIES] = S.NOT_PROVIDED
    elif all(boundaries) and not has(F.IAM_PERMISSION_BOUNDARIES):
        status[F.IAM_PERMISSION_BOUNDARIES] = S.ANALYSED
    else:
        status[F.IAM_PERMISSION_BOUNDARIES] = S.PARTIALLY_ANALYSED
    declared_policy = any(
        attrs.get("session_policy_inline", "none") != "none"
        or attrs.get("session_policy_managed")
        or attrs.get("session_policy_managed_expression")
        for attrs in sessions
    )
    status[F.IAM_SESSION_POLICIES] = _status_for(
        present=bool(sessions), degraded=bool(declared_policy), absent=S.NOT_APPLICABLE
    )
    unverified_ttl = any(attrs.get("ttl_requested") in _UNVERIFIED_REQUESTS for attrs in sessions)
    status[F.AWS_SESSION_DURATION] = _status_for(
        present=bool(sessions),
        degraded=unverified_ttl or has(F.AWS_SESSION_DURATION),
        absent=S.NOT_APPLICABLE,
    )
    aws_present = bool(roles)
    status[F.AWS_ORG_POLICIES] = S.NOT_SUPPORTED if aws_present else S.NOT_APPLICABLE
    status[F.AWS_RESOURCE_POLICIES] = S.NOT_SUPPORTED if aws_present or sinks else S.NOT_APPLICABLE
    status[F.KMS_KEY_POLICIES] = S.NOT_SUPPORTED if "A-KMS-UNMODELLED" in used else S.NOT_APPLICABLE
    status[F.AWS_ROLE_CHAINING] = (
        S.NOT_SUPPORTED if aws_present or F.AWS_ROLE_CHAINING in mentioned else S.NOT_APPLICABLE
    )
    status[F.LIVE_CLOUD_STATE] = S.NOT_SUPPORTED
    status[F.ANALYSIS_BUDGET] = S.PARTIALLY_ANALYSED if has(F.ANALYSIS_BUDGET) else S.ANALYSED

    items: list[CompletenessItem] = []
    for family in InputFamily:
        sources = tuple(
            CompletenessSource(path=item.path, sha256=item.sha256)
            for item in sorted(
                by_family_files.get(family, ()), key=lambda f: f.path.encode("utf-8")
            )
        )
        items.append(
            CompletenessItem(
                id=family.value,
                family=family,
                status=status[family],
                sources=sources,
                diagnostics=tuple(sorted(mentioned.get(family, ()))),
                assumptions=tuple(
                    sorted(item for item in used if ASSUMPTION_TO_FAMILY.get(item) is family)
                ),
                explanation=_explanation(family, status[family]),
            )
        )
    ordered = tuple(sorted(items, key=lambda item: item.id))
    # The explanation is derived wording; the digest covers only the substance.
    digest = digest_of([item.model_dump(mode="json", exclude={"explanation"}) for item in ordered])
    return Completeness(items=ordered, digest=digest)


_EXPLANATIONS: dict[CompletenessStatus, str] = {
    S.ANALYSED: "analysed; limits are listed in diagnostics and assumptions",
    S.PARTIALLY_ANALYSED: "partially analysed; results are a lower bound",
    S.NOT_PROVIDED: "not provided; the report says nothing about it",
    S.NOT_SUPPORTED: "not analysable offline by this version; the report says nothing about it",
    S.NOT_APPLICABLE: "does not apply to the inputs that were scanned",
}


def _explanation(family: InputFamily, status: CompletenessStatus) -> str:
    return f"{FAMILY_LABELS[family]}: {_EXPLANATIONS[status]}"


def not_analysed_summary(completeness: Completeness) -> str:
    """One line naming what the report cannot speak to; used by the scope text."""
    names = [
        FAMILY_LABELS[item.family]
        for item in completeness.items
        if item.status in {S.NOT_PROVIDED, S.NOT_SUPPORTED}
    ]
    names.extend(ALWAYS_OUT_OF_SCOPE)
    return ", ".join(names)


def status_counts(completeness: Completeness) -> dict[str, int]:
    counts = {status.value: 0 for status in CompletenessStatus}
    for item in completeness.items:
        counts[item.status.value] += 1
    return counts


__all__ = [
    "ASSUMPTION_TO_FAMILY",
    "CODE_TO_FAMILY",
    "FAMILY_LABELS",
    "WorkflowFacts",
    "derive_completeness",
    "not_analysed_summary",
    "path_collision_diagnostics",
    "status_counts",
]
