"""Findings derived from graph facts and scenario results (spec 13.1)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase

from nhi_blast.analysis.reach import PathInfo, reach
from nhi_blast.analysis.selectors import Selector, matching_action_nodes, parse_selector
from nhi_blast.core.config import Config
from nhi_blast.core.data import rules
from nhi_blast.core.diagnostics import Diagnostic, info
from nhi_blast.core.evidence import (
    Evidence,
    EvidenceClass,
    dedupe_evidence,
    evidence_sort_key,
    weakest_of,
)
from nhi_blast.core.ids import finding_id
from nhi_blast.core.models import (
    PERSISTENT_LIFETIMES,
    Edge,
    EdgeKind,
    Finding,
    GraphData,
    Node,
    NodeKind,
    ScenarioReport,
    Severity,
)

# Rules whose finding belongs to one scenario's partition. Every other rule is derived from
# graph facts alone; its `scenario` field only records which scenario reached it first.
SCENARIO_RULES = frozenset({"NHB-SURV-001", "NHB-ROT-001", "NHB-ROT-002"})


@dataclass(frozen=True, slots=True)
class FindingBuild:
    findings: tuple[Finding, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


def _evidence(groups: Iterable[Iterable[Evidence]]) -> tuple[Evidence, ...]:
    return tuple(
        sorted(
            dedupe_evidence(item for group in groups for item in group),
            key=evidence_sort_key,
        )
    )


def _assumptions(evidence: Iterable[Evidence]) -> tuple[str, ...]:
    return tuple(sorted({item.rule for item in evidence if item.rule.startswith(("A-", "H-"))}))


def _survivor_severity(criticality: int) -> Severity:
    if criticality >= 90:
        return Severity.CRITICAL
    if criticality >= 70:
        return Severity.HIGH
    if criticality >= 40:
        return Severity.MEDIUM
    return Severity.LOW


def _path_nodes(path: PathInfo) -> tuple[str, ...]:
    if not path.edges:
        return (path.node,)
    nodes = [path.edges[0].src, *(edge.dst for edge in path.edges)]
    if nodes[-1] != path.node:
        nodes[-1] = path.node
    return tuple(nodes)


class _FindingsBuilder:
    def __init__(self, graph: GraphData, scenarios: Sequence[ScenarioReport]) -> None:
        self.graph = graph
        self.scenarios = tuple({item.selector: item for item in scenarios}.values())
        self.nodes = {node.id: node for node in graph.nodes}
        self.outgoing: dict[str, list[Edge]] = {}
        self.incoming: dict[str, list[Edge]] = {}
        for edge in graph.edges:
            self.outgoing.setdefault(edge.src, []).append(edge)
            self.incoming.setdefault(edge.dst, []).append(edge)
        self.paths = {
            scenario.selector: reach(graph, scenario.start_nodes) for scenario in self.scenarios
        }
        self.job_reach: dict[str, dict[str, PathInfo]] = {}
        self.findings: dict[str, Finding] = {}

    def _add(
        self,
        rule_id: str,
        severity: Severity,
        message: str,
        *,
        nodes: Iterable[str],
        evidence: Iterable[Iterable[Evidence]],
        path: Sequence[str] = (),
        path_edges: Sequence[str] = (),
        scenario: str | None = None,
    ) -> None:
        entries = _evidence(evidence)
        if not entries:
            msg = f"finding {rule_id} would have no evidence"
            raise ValueError(msg)
        node_ids = tuple(sorted(set(nodes)))
        confidence = weakest_of(item.cls for item in entries)
        assumptions = _assumptions(entries)
        detail = f"{message} Evidence class: {confidence.value}."
        if assumptions:
            detail += f" Assumptions: {', '.join(assumptions)}."
        definition = rules().get(rule_id)
        finding = Finding(
            id=finding_id(rule_id, node_ids, entries),
            rule=rule_id,
            severity=severity,
            confidence=confidence,
            title=definition.title,
            message=detail,
            evidence=entries,
            path=tuple(path),
            path_edges=tuple(path_edges),
            assumptions=assumptions,
            scenario=scenario,
        )
        self.findings.setdefault(finding.id, finding)

    def _scenario_path(self, node_id: str) -> tuple[PathInfo, str] | None:
        for scenario in self.scenarios:
            path = self.paths[scenario.selector].get(node_id)
            if path is not None:
                return path, scenario.selector
        return None

    def _role_reads_persistent(self, role_id: str) -> bool:
        for read in self.outgoing.get(role_id, ()):
            if read.kind is not EdgeKind.CAN_READ_VALUE or read.confidence is EvidenceClass.UNKNOWN:
                continue
            for stores in self.outgoing.get(read.dst, ()):
                if (
                    stores.kind is EdgeKind.STORES
                    and stores.confidence is not EvidenceClass.UNKNOWN
                    and stores.lifetime in PERSISTENT_LIFETIMES
                ):
                    return True
        return False

    def _broad_trust_severity(self, role_id: str, edges: Sequence[Edge]) -> Severity:
        untrusted = any(
            self.nodes[edge.src].attrs.get("job") is not None
            and self.nodes[str(self.nodes[edge.src].attrs["job"])].attrs.get("untrusted_checkout")
            is True
            for edge in edges
        )
        return (
            Severity.CRITICAL
            if any(edge.attrs.get("breadth") == "ANY_ORG" for edge in edges)
            or self._role_reads_persistent(role_id)
            or untrusted
            else Severity.HIGH
        )

    def _trust_findings(self) -> None:
        assume_by_role: dict[str, list[Edge]] = {}
        for edge in self.graph.edges:
            if edge.kind is EdgeKind.CAN_ASSUME and not edge.attrs.get("unresolved"):
                assume_by_role.setdefault(edge.dst, []).append(edge)
        audited_roles = {
            node.id
            for node in self.graph.nodes
            if node.kind is NodeKind.AWS_ROLE
            and (node.attrs.get("trust_audit") or node.attrs.get("trust_policy_audit"))
        }
        for role_id in sorted(set(assume_by_role) | audited_roles):
            edges = assume_by_role.get(role_id, [])
            role = self.nodes[role_id]
            groups: list[tuple[str, Severity, str, list[Edge]]] = []
            unconstrained = [edge for edge in edges if edge.attrs.get("unconstrained")]
            if unconstrained:
                groups.append(
                    (
                        "NHB-OIDC-001",
                        Severity.CRITICAL,
                        f"Trust policy for {role.label} has no sub or job_workflow_ref control.",
                        unconstrained,
                    )
                )
            broad = [edge for edge in edges if edge.attrs.get("breadth") in {"ANY_ORG", "SAME_ORG"}]
            if broad:
                groups.append(
                    (
                        "NHB-OIDC-002",
                        self._broad_trust_severity(role_id, broad),
                        (
                            f"Trust policy for {role.label} accepts organisation-wide "
                            "or global subjects."
                        ),
                        broad,
                    )
                )
            repo_wide = [edge for edge in edges if edge.attrs.get("breadth") == "REPO_ANY_CONTEXT"]
            if repo_wide:
                groups.append(
                    (
                        "NHB-OIDC-003",
                        self._broad_trust_severity(role_id, repo_wide),
                        f"Trust policy for {role.label} accepts any repository context.",
                        repo_wide,
                    )
                )
            missing_audience = [edge for edge in edges if edge.attrs.get("missing_audience")]
            if missing_audience:
                groups.append(
                    (
                        "NHB-OIDC-004",
                        Severity.MEDIUM,
                        f"Trust policy for {role.label} does not constrain the audience.",
                        missing_audience,
                    )
                )
            drift = [edge for edge in edges if edge.attrs.get("format_drift")]
            if drift:
                groups.append(
                    (
                        "NHB-OIDC-005",
                        Severity.LOW,
                        f"Trust policy for {role.label} matches only the classic subject format.",
                        drift,
                    )
                )
            dead = [edge for edge in edges if edge.attrs.get("dead_condition_keys")]
            if dead:
                groups.append(
                    (
                        "NHB-OIDC-006",
                        Severity.LOW,
                        f"Trust policy for {role.label} uses a condition key undocumented for AWS.",
                        dead,
                    )
                )
            environment = [edge for edge in edges if edge.attrs.get("breadth") == "ENVIRONMENT"]
            if environment:
                groups.append(
                    (
                        "NHB-OIDC-007",
                        Severity.INFO,
                        (
                            f"Trust policy for {role.label} uses an environment whose "
                            "protection is unknown."
                        ),
                        environment,
                    )
                )
            for rule_id, severity, message, matched in groups:
                entries = _evidence(edge.evidence for edge in matched)
                path_info = self._scenario_path(role_id)
                self._add(
                    rule_id,
                    severity,
                    message,
                    nodes=(role_id, *(edge.src for edge in matched)),
                    evidence=(entries,),
                    path=_path_nodes(path_info[0]) if path_info else (),
                    path_edges=path_info[0].ids if path_info else (),
                    scenario=path_info[1] if path_info else None,
                )
            audits = role.attrs.get("trust_policy_audit", [])
            if not isinstance(audits, list):
                continue
            audit_rules = (
                ("unconstrained", "NHB-OIDC-001", Severity.CRITICAL, "has no subject control"),
                ("missing_audience", "NHB-OIDC-004", Severity.MEDIUM, "has no audience control"),
                (
                    "dead_condition_keys",
                    "NHB-OIDC-006",
                    Severity.LOW,
                    "uses a condition key undocumented for AWS",
                ),
            )
            for attribute, rule_id, severity, description in audit_rules:
                matched_audits = [audit for audit in audits if audit.get(attribute)]
                if not matched_audits:
                    continue
                statement_evidence = tuple(
                    Evidence.model_validate(row)
                    for audit in matched_audits
                    for row in audit.get("evidence", [])
                )
                self._add(
                    rule_id,
                    severity,
                    f"Trust policy for {role.label} {description}.",
                    nodes=(role_id,),
                    evidence=(role.evidence, statement_evidence),
                    path=(role_id,),
                )

    def _privilege_edges(self, job_id: str) -> tuple[Edge, ...]:
        privileges = []
        for edge in self.outgoing.get(job_id, ()):
            if edge.kind is EdgeKind.CAN_MINT and edge.confidence is not EvidenceClass.UNKNOWN:
                privileges.append(edge)
            elif edge.kind is EdgeKind.HOLDS and edge.confidence is not EvidenceClass.UNKNOWN:
                credential = self.nodes[edge.dst]
                if any(
                    credential.attrs.get(name)
                    for name in ("secret", "literal", "static_aws_key", "wildcard")
                ):
                    privileges.append(edge)
        return tuple(privileges)

    def _has_surviving_scenario(self, job_id: str) -> str | None:
        for scenario in self.scenarios:
            if job_id in scenario.start_nodes and scenario.partition.Z:
                return scenario.selector
        return None

    def _checkout_evidence(self, job: Node) -> tuple[Evidence, ...]:
        path = job.attrs.get("path")
        line = job.attrs.get("untrusted_checkout_line")
        # The parser records the first executing step after the head-ref checkout.
        execution = Evidence(
            cls=EvidenceClass.ASSUMED,
            rule="A-STEP-SHARE",
            file=path if isinstance(path, str) else None,
            line=line if isinstance(line, int) else None,
            detail="a step after the untrusted checkout may execute contributor-controlled content",
        )
        callsites = (
            runs.evidence
            for runs in self.outgoing.get(job.id, ())
            if runs.kind is EdgeKind.RUNS_IN
            and str(self.nodes[runs.dst].attrs.get("owner", "")).lower() == "actions"
            and str(self.nodes[runs.dst].attrs.get("repo", "")).lower() == "checkout"
        )
        return _evidence(((execution,), *callsites))

    def _job_findings(self) -> None:
        for job in self.graph.nodes:
            if job.kind is not NodeKind.JOB:
                continue
            privileges = self._privilege_edges(job.id)
            for runs in self.outgoing.get(job.id, ()):
                if runs.kind is not EdgeKind.RUNS_IN:
                    continue
                action = self.nodes[runs.dst]
                if not (
                    action.attrs.get("mutable") is True
                    and action.attrs.get("first_party") is False
                    and privileges
                ):
                    continue
                scenario = self._has_surviving_scenario(job.id)
                self._add(
                    "NHB-GHA-001",
                    Severity.HIGH if scenario else Severity.MEDIUM,
                    (
                        f"Mutable third-party action {action.label} runs in privileged "
                        f"job {job.label}."
                    ),
                    nodes=(job.id, action.id),
                    evidence=(job.evidence, runs.evidence, privileges[0].evidence),
                    path=(job.id, action.id),
                    path_edges=(runs.id,),
                    scenario=scenario,
                )
            if job.attrs.get("untrusted_checkout") is True and privileges:
                paths = self.job_reach.get(job.id) or reach(self.graph, (job.id,))
                role_path = next(
                    (
                        path
                        for node_id, path in sorted(paths.items())
                        if self.nodes[node_id].kind is NodeKind.AWS_ROLE
                    ),
                    None,
                )
                self._add(
                    "NHB-GHA-002",
                    Severity.CRITICAL if role_path else Severity.HIGH,
                    f"Job {job.label} checks out untrusted content under a privileged trigger.",
                    nodes=(job.id, *((role_path.node,) if role_path else ())),
                    evidence=(
                        job.evidence,
                        self._checkout_evidence(job),
                        privileges[0].evidence,
                        role_path.edges[-1].evidence if role_path else (),
                    ),
                    path=_path_nodes(role_path) if role_path else (job.id,),
                    path_edges=role_path.ids if role_path else (),
                )
            if (
                job.attrs.get("ai_agent_workflow") is True
                and privileges
                and (
                    set(job.attrs.get("trigger_events", ()))
                    & {
                        "pull_request",
                        "pull_request_target",
                        "issue_comment",
                        "issues",
                        "discussion",
                        "discussion_comment",
                        "pull_request_review_comment",
                    }
                )
            ):
                paths = self.job_reach.get(job.id) or reach(self.graph, (job.id,))
                role_path = next(
                    (
                        path
                        for node_id, path in sorted(paths.items())
                        if self.nodes[node_id].kind is NodeKind.AWS_ROLE
                    ),
                    None,
                )
                wf_path = str(job.attrs.get("path", ""))
                lock_note = ""
                if job.attrs.get("compiled_lock_workflow") and wf_path.endswith(".lock.yml"):
                    source_md = wf_path[: -len(".lock.yml")] + ".md"
                    lock_note = f" Compiled from {source_md}; review source instructions."
                self._add(
                    "NHB-GHA-006",
                    Severity.CRITICAL if role_path else Severity.HIGH,
                    (
                        f"Job {job.label} runs an AI coding agent on an untrusted PR or issue "
                        f"trigger while holding secrets or OIDC authority.{lock_note}"
                    ),
                    nodes=(job.id, *((role_path.node,) if role_path else ())),
                    evidence=(
                        job.evidence,
                        privileges[0].evidence,
                        role_path.edges[-1].evidence if role_path else (),
                    ),
                    path=_path_nodes(role_path) if role_path else (job.id,),
                    path_edges=role_path.ids if role_path else (),
                )
            if job.attrs.get("unconstrained_pkg_install") is True and privileges:
                untrusted_pkg = bool(
                    set(job.attrs.get("trigger_events", ()))
                    & {"pull_request", "pull_request_target", "issue_comment"}
                )
                self._add(
                    "NHB-GHA-007",
                    Severity.HIGH if untrusted_pkg else Severity.MEDIUM,
                    (
                        f"Job {job.label} runs a package install without lifecycle-script "
                        f"suppression while holding secrets or OIDC authority."
                    ),
                    nodes=(job.id,),
                    evidence=(job.evidence, privileges[0].evidence),
                    path=(job.id,),
                )
            if job.attrs.get("self_hosted") is True:
                self._add(
                    "NHB-GHA-003",
                    Severity.INFO,
                    f"Job {job.label} targets a self-hosted runner; state may persist across jobs.",
                    nodes=(job.id,),
                    evidence=(job.evidence,),
                    path=(job.id,),
                )

        for credential in self.graph.nodes:
            if credential.kind is not NodeKind.CREDENTIAL:
                continue
            holds = [
                edge for edge in self.incoming.get(credential.id, ()) if edge.kind is EdgeKind.HOLDS
            ]
            if credential.attrs.get("wildcard") is True:
                self._add(
                    "NHB-GHA-004",
                    Severity.MEDIUM,
                    f"Job {credential.attrs.get('job', '')} exposes the whole secrets context.",
                    nodes=(credential.id, *(edge.src for edge in holds)),
                    evidence=(credential.evidence, *(edge.evidence for edge in holds)),
                    path=(credential.id,),
                )
            if credential.attrs.get("literal") is True:
                self._add(
                    "NHB-GHA-005",
                    Severity.HIGH,
                    (
                        f"Workflow contains a {credential.attrs.get('credential_kind')} literal "
                        f"({credential.attrs.get('length')} chars); the value was not retained."
                    ),
                    nodes=(credential.id, *(edge.src for edge in holds)),
                    evidence=(credential.evidence,),
                    path=(credential.id,),
                )
            if credential.attrs.get("static_aws_key") is True:
                for hold in holds:
                    if self.nodes[hold.src].attrs.get("id_token_write") is not True:
                        continue
                    self._add(
                        "NHB-CRED-001",
                        Severity.MEDIUM,
                        f"Job {hold.src} uses static AWS keys where OIDC is available.",
                        nodes=(credential.id, hold.src),
                        evidence=(credential.evidence, hold.evidence),
                        path=(hold.src, credential.id),
                        path_edges=(hold.id,),
                    )

    def _mutable_entrypoint_paths(
        self, selector: Selector, scenario: ScenarioReport
    ) -> dict[str, PathInfo]:
        actions = {
            node.id
            for node in matching_action_nodes(selector, self.graph)
            if node.attrs.get("mutable") is True
        }
        starts = tuple(
            job_id
            for job_id in scenario.start_nodes
            if any(
                edge.kind is EdgeKind.RUNS_IN and edge.dst in actions
                for edge in self.outgoing.get(job_id, ())
            )
        )
        if not starts:
            return {}
        if starts == scenario.start_nodes:
            return self.paths[scenario.selector]
        # An action-any scenario may also start at pinned refs in unrelated jobs.
        return reach(self.graph, starts)

    def _scenario_findings(self) -> None:
        for scenario in self.scenarios:
            paths = self.paths[scenario.selector]
            selector = parse_selector(scenario.selector)
            if scenario.partition.Z:
                highest = max(item.criticality for item in scenario.partition.Z)
                credential_id = next(
                    item.credential for item in scenario.partition.Z if item.criticality == highest
                )
                path = paths.get(credential_id)
                credential = self.nodes[credential_id]
                entries = _evidence(
                    (
                        credential.evidence,
                        *((edge.evidence for edge in path.edges) if path else ()),
                    )
                )
                self._add(
                    "NHB-SURV-001",
                    _survivor_severity(highest),
                    (
                        f"{len(scenario.partition.Z)} persistent credential(s) survive revocation "
                        "of the entrypoint if the authority path was exercised."
                    ),
                    nodes=(
                        *scenario.start_nodes,
                        *(item.credential for item in scenario.partition.Z),
                    ),
                    evidence=(entries,),
                    path=_path_nodes(path) if path else (credential_id,),
                    path_edges=path.ids if path else (),
                    scenario=scenario.selector,
                )
            for node_id, path in sorted(paths.items()):
                sink = self.nodes[node_id]
                if (
                    sink.kind is NodeKind.SINK
                    and sink.attrs.get("credential_bearing") is True
                    and sink.attrs.get("rotation_interval_days") is None
                ):
                    self._add(
                        "NHB-ROT-001",
                        Severity.LOW,
                        f"Reachable credential sink {sink.label} has no rotation configured.",
                        nodes=(*scenario.start_nodes, sink.id),
                        evidence=(sink.evidence, *(edge.evidence for edge in path.edges)),
                        path=_path_nodes(path),
                        path_edges=path.ids,
                        scenario=scenario.selector,
                    )
            mutable_paths = self._mutable_entrypoint_paths(selector, scenario)
            for role_id, path in sorted(mutable_paths.items()):
                if self.nodes[role_id].kind is not NodeKind.AWS_ROLE:
                    continue
                for modify in self.outgoing.get(role_id, ()):
                    if (
                        modify.kind is not EdgeKind.CAN_MODIFY
                        or modify.confidence is EvidenceClass.UNKNOWN
                    ):
                        continue
                    sink = self.nodes[modify.dst]
                    self._add(
                        "NHB-ROT-002",
                        Severity.MEDIUM,
                        (
                            f"Reachable role {self.nodes[role_id].label} can modify "
                            f"credential sink {sink.label}."
                        ),
                        nodes=(*scenario.start_nodes, role_id, sink.id),
                        evidence=(
                            sink.evidence,
                            modify.evidence,
                            *(edge.evidence for edge in path.edges),
                        ),
                        path=(*_path_nodes(path), sink.id),
                        path_edges=(*path.ids, modify.id),
                        scenario=scenario.selector,
                    )

    def build(self) -> FindingBuild:
        self.job_reach = {
            job.id: reach(self.graph, (job.id,))
            for job in self.graph.nodes
            if job.kind is NodeKind.JOB
        }
        self._trust_findings()
        self._job_findings()
        self._persistence_and_chain_findings()
        self._scenario_findings()
        return FindingBuild(findings=tuple(sorted(self.findings.values(), key=Finding.sort_key)))

    def _persistence_and_chain_findings(self) -> None:
        untrusted_triggers = {
            "pull_request_target",
            "issue_comment",
            "issues",
            "discussion",
            "discussion_comment",
        }
        for edge in self.graph.edges:
            if edge.kind is EdgeKind.CAN_ASSUME and edge.attrs.get("chained") is True:
                src = self.nodes.get(edge.src)
                dst = self.nodes.get(edge.dst)
                if src is None or dst is None:
                    continue
                if not any(src.id in paths for paths in self.job_reach.values()):
                    continue
                dst_paths = reach(self.graph, (dst.id,))
                reaches_z = any(
                    self.nodes[nid].kind is NodeKind.CREDENTIAL
                    and self.nodes[nid].attrs.get("lifetime")
                    in {"persistent", "persistent_rotating"}
                    for nid in dst_paths
                )
                self._add(
                    "NHB-CHAIN-001",
                    Severity.CRITICAL if reaches_z else Severity.HIGH,
                    (
                        f"Role {src.label} can assume {dst.label} via sts:AssumeRole "
                        f"(3600 s chained session cap)."
                    ),
                    nodes=(src.id, dst.id),
                    evidence=(src.evidence, dst.evidence, edge.evidence),
                    path=(src.id, dst.id),
                    path_edges=(edge.id,),
                )

        for role in self.graph.nodes:
            if role.kind is not NodeKind.AWS_ROLE:
                continue
            actions = role.attrs.get("persistence_actions")
            if not actions:
                continue
            reaching_jobs: list[Node] = []
            untrusted_entry = False
            for job in self.graph.nodes:
                if job.kind is not NodeKind.JOB:
                    continue
                if role.id not in self.job_reach[job.id]:
                    continue
                reaching_jobs.append(job)
                if set(job.attrs.get("trigger_events", ())) & untrusted_triggers:
                    untrusted_entry = True
                for runs in self.outgoing.get(job.id, ()):
                    if runs.kind is EdgeKind.RUNS_IN and self.nodes[runs.dst].attrs.get("mutable"):
                        untrusted_entry = True
            if not reaching_jobs:
                continue
            role_path = self.job_reach[reaching_jobs[0].id][role.id]
            action_list = ", ".join(str(a) for a in actions)
            self._add(
                "NHB-PERSIST-001",
                Severity.CRITICAL if untrusted_entry else Severity.HIGH,
                (
                    f"Reachable role {role.label} permits IAM persistence action(s): "
                    f"{action_list}. Revoking STS sessions does not remove newly created "
                    f"IAM access keys or modified trust policies."
                ),
                nodes=(reaching_jobs[0].id, role.id),
                evidence=(
                    reaching_jobs[0].evidence,
                    role.evidence,
                    *(edge.evidence for edge in role_path.edges),
                ),
                path=_path_nodes(role_path),
                path_edges=role_path.ids,
            )


def build_findings(graph: GraphData, *, scenarios: Sequence[ScenarioReport] = ()) -> FindingBuild:
    return _FindingsBuilder(graph, scenarios).build()


def _ignored_path(finding: Finding, patterns: Sequence[str]) -> str | None:
    candidates = sorted(
        {item.file for item in finding.evidence if item.file is not None} | set(finding.path)
    )
    for candidate in candidates:
        if any(fnmatchcase(candidate, pattern) for pattern in patterns):
            return candidate
    return None


def filter_findings(
    findings: Iterable[Finding], *, config: Config, strict: bool = False
) -> FindingBuild:
    kept: list[Finding] = []
    diagnostics: list[Diagnostic] = []
    ignored_rules = set(config.ignore_rules)
    for finding in sorted(findings, key=Finding.sort_key):
        matched_path = _ignored_path(finding, config.ignore_paths)
        if finding.rule not in ignored_rules and matched_path is None:
            kept.append(finding)
            continue
        if strict:
            reason = "rule" if finding.rule in ignored_rules else f"path {matched_path}"
            diagnostics.append(
                info(
                    "D-FINDING-IGNORED",
                    f"finding {finding.id} suppressed by configured {reason}",
                    file=matched_path,
                )
            )
    return FindingBuild(findings=tuple(kept), diagnostics=tuple(diagnostics))


__all__ = ["SCENARIO_RULES", "FindingBuild", "build_findings", "filter_findings"]
