"""Graph construction rules R1-R14 (spec 11, BUILD-PLAN 4.5).

Every node and edge carries evidence; an edge's confidence is the weakest class
among its evidence. The builder consumes parsed workflow facts, expanded composite
steps, resolved cloud facts and configuration, and produces a deterministic graph.
It never reads a file and never executes scanned content.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from nhi_blast.aws.policy_eval import (
    CandidateFilter,
    action_filter,
    can_modify,
    can_read,
)
from nhi_blast.aws.sinks import candidate_arns, modify_actions, read_actions
from nhi_blast.aws.trust import (
    TrustEvaluation,
    TrustSubjectFilter,
    evaluate_trust_statements,
    no_match_evaluation,
    trust_subject_filter,
)
from nhi_blast.core.config import Config
from nhi_blast.core.data import ConditionKeyRegistry, condition_keys, credential_heuristics
from nhi_blast.core.diagnostics import Diagnostic, DiagnosticBag, error, info
from nhi_blast.core.evidence import (
    Evidence,
    EvidenceClass,
    dedupe_evidence,
    evidence_sort_key,
    weakest,
)
from nhi_blast.core.ids import (
    action_node_id,
    credential_node_id,
    edge_id,
    external_node_id,
    job_node_id,
    local_action_node_id,
    oidc_node_id,
    provider_node_id,
    repo_node_id,
    role_node_id,
    workflow_node_id,
)
from nhi_blast.core.limits import Limits
from nhi_blast.core.models import (
    CredentialKind,
    Decision,
    DecisionResult,
    Edge,
    EdgeKind,
    ExternalTargetFact,
    GraphData,
    Lifetime,
    Node,
    NodeKind,
    RoleFact,
    SinkFact,
    SinkType,
    Statement,
    SubFormat,
    SubjectCandidate,
    TrustMatch,
)
from nhi_blast.discovery.repo import RepoIdentity
from nhi_blast.graph.store import GraphBudgetError, GraphIntegrityError, GraphStore
from nhi_blast.oidc.github_subject import subject_candidates
from nhi_blast.oidc.solver import evaluate_trust, trust_match_from_evaluation
from nhi_blast.parsers.gha.facts import JobFact, LiteralHit, UsesRef, WorkflowFact
from nhi_blast.parsers.gha.uses import local_action_dir
from nhi_blast.resolvers.composite import ExpandedJob, ExpandedStep
from nhi_blast.resolvers.permissions import EffectivePerms
from nhi_blast.resolvers.roles import CloudFacts
from nhi_blast.resolvers.workflows import effective_job_permissions, reusable_index

DEFAULT_AUDIENCE = "sts.amazonaws.com"


def _repo_write_candidates(repository: RepoIdentity) -> tuple[SubjectCandidate, ...]:
    if repository.slug is None or "/" not in repository.slug:
        return ()
    owner, name = repository.slug.split("/", 1)
    ref = "refs/heads/*"
    evidence = Evidence(
        cls=EvidenceClass.ASSUMED,
        rule="A-REPO-WRITE",
        detail="a repository writer can add id-token: write on an editable branch",
    )
    claims = {
        "repository": repository.slug,
        "repository_owner": owner,
        "ref": ref,
        "job_workflow_ref": f"{repository.slug}/.github/workflows/*@{ref}",
    }
    return (
        SubjectCandidate(
            subject=f"repo:{repository.slug}:ref:{ref}",
            format=SubFormat.CLASSIC,
            trigger="repo-write",
            audience=DEFAULT_AUDIENCE,
            claims=claims,
            evidence_class=EvidenceClass.ASSUMED,
            evidence=(evidence,),
        ),
        SubjectCandidate(
            subject=f"repo:{owner}@*/{name}@*:ref:{ref}",
            format=SubFormat.IMMUTABLE,
            trigger="repo-write",
            audience=DEFAULT_AUDIENCE,
            claims=claims,
            evidence_class=EvidenceClass.ASSUMED,
            evidence=(evidence,),
        ),
    )


@dataclass(frozen=True, slots=True)
class GraphInputs:
    repository: RepoIdentity
    workflows: tuple[WorkflowFact, ...]
    expanded_jobs: tuple[ExpandedJob, ...]
    cloud: CloudFacts
    config: Config = field(default_factory=Config.empty)
    limits: Limits = field(default_factory=Limits)


@dataclass(frozen=True, slots=True)
class GraphBuild:
    graph: GraphData
    diagnostics: tuple[Diagnostic, ...]
    assumptions_used: tuple[str, ...]
    truncated: bool


def _ordered_evidence(items: Iterable[Evidence]) -> tuple[Evidence, ...]:
    return tuple(sorted(dedupe_evidence(items), key=evidence_sort_key))


def _source_file(step: ExpandedStep, workflow: WorkflowFact) -> str:
    return step.composite_paths[-1] if step.composite_paths else workflow.path


def _job_key(workflow: WorkflowFact, job: JobFact) -> tuple[str, str]:
    return (workflow.path, job.id)


def _docker_action_id(raw: str) -> str:
    reference = raw.strip()
    if reference.startswith("docker://"):
        reference = reference[len("docker://") :]
    image, _, digest = reference.partition("@")
    return f"action:docker:{image}@{digest or 'unresolved'}"


def _action_id(uses: UsesRef) -> str:
    if uses.kind == "LOCAL":
        directory = local_action_dir(uses)
        if directory is not None:
            return local_action_node_id(directory)
        return local_action_node_id(uses.raw)
    if uses.kind == "DOCKER":
        return _docker_action_id(uses.raw)
    if uses.owner is not None and uses.repo is not None:
        return action_node_id(uses.owner, uses.repo, uses.subpath, uses.ref)
    return f"action:{uses.raw}@unresolved"


def _subject_key(candidate: SubjectCandidate) -> tuple[str, str, str, str]:
    return (
        candidate.subject,
        candidate.format.value,
        candidate.trigger,
        candidate.audience,
    )


class _Builder:
    def __init__(self, inputs: GraphInputs) -> None:
        self.inputs = inputs
        self.store = GraphStore(limits=inputs.limits)
        self.diagnostics: list[Diagnostic] = []
        self.assumptions: set[str] = set()
        self.truncated = False
        self.workflow_by_path = {workflow.path: workflow for workflow in inputs.workflows}
        self.expanded_by_key = {
            _job_key(item.workflow, item.job): item for item in inputs.expanded_jobs
        }
        self.reusable = reusable_index(inputs.workflows)
        self.effective: dict[tuple[str, str], EffectivePerms] = {}
        self.job_nodes: dict[tuple[str, str], str] = {}
        self.identities: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
        self.intended: dict[tuple[str, str], frozenset[str]] = {}
        self.candidates: dict[tuple[str, str], tuple[SubjectCandidate, ...]] = {}
        self.trust_audit: dict[str, list[dict[str, object]]] = {}
        self.trust_policy_audit: dict[str, list[dict[str, object]]] = {}
        self.trust_matched_statements: dict[str, list[Statement]] = {}
        self.repo_write_roles: set[str] = set()
        self.roles = tuple(sorted(inputs.cloud.roles, key=lambda role: role.id))
        self.sinks = tuple(sorted(inputs.cloud.sinks, key=lambda sink: sink.id))
        self.trust_filters: dict[str, TrustSubjectFilter] = {}
        self.no_match_evaluations: dict[str, TrustEvaluation] = {}
        self.trust_matches: dict[tuple[str, str, str], TrustMatch | None] = {}
        self.stored_credential: dict[str, str] = {}
        self.credential_sink: dict[str, SinkFact] = {}
        self.externals = tuple(sorted(inputs.cloud.externals, key=lambda target: target.label))

    # ------------------------------------------------------------- helpers

    def _use(self, assumption_id: str) -> None:
        if assumption_id.startswith(("A-", "H-")):
            self.assumptions.add(assumption_id)

    def _tag(self, evidence: Iterable[Evidence]) -> None:
        for item in evidence:
            self._use(item.rule)

    def _add_node(self, node: Node) -> bool:
        if self.truncated:
            return False
        self._tag(node.evidence)
        try:
            self.store.add_node(node)
        except GraphBudgetError:
            self.truncated = True
            return False
        return True

    def _add_edge(self, edge: Edge) -> bool:
        if self.truncated:
            return False
        self._tag(edge.evidence)
        try:
            self.store.add_edge(edge)
        except GraphBudgetError:
            self.truncated = True
            return False
        return True

    def _node(
        self,
        node_id: str,
        kind: NodeKind,
        label: str,
        evidence: Iterable[Evidence],
        attrs: dict[str, object] | None = None,
    ) -> bool:
        entries = _ordered_evidence(evidence)
        if not entries:
            msg = f"node {node_id} would have no evidence"
            raise GraphIntegrityError(msg)
        return self._add_node(
            Node(id=node_id, kind=kind, label=label, attrs=attrs or {}, evidence=entries)
        )

    def _edge(
        self,
        kind: EdgeKind,
        src: str,
        dst: str,
        evidence: Iterable[Evidence],
        *,
        lifetime: Lifetime = Lifetime.NA,
        attrs: dict[str, object] | None = None,
    ) -> bool:
        entries = _ordered_evidence(evidence)
        if not entries:
            msg = f"edge {kind} {src}->{dst} would have no evidence"
            raise GraphIntegrityError(msg)
        confidence = weakest(*(item.cls for item in entries))
        edge = Edge(
            id=edge_id(kind.value, src, dst, entries),
            kind=kind,
            src=src,
            dst=dst,
            lifetime=lifetime,
            confidence=confidence,
            evidence=entries,
            attrs=attrs or {},
        )
        return self._add_edge(edge)

    def _evidence(
        self,
        cls: EvidenceClass,
        rule: str,
        *,
        file: str | None = None,
        line: int | None = None,
        detail: str = "",
    ) -> Evidence:
        return Evidence(cls=cls, rule=rule, file=file, line=line, detail=detail)

    def _first_location(self, evidence: Sequence[Evidence]) -> tuple[str | None, int | None]:
        for item in evidence:
            if item.file is not None:
                return item.file, item.line
        return None, None

    # ------------------------------------------------------------- prepare

    def _prepare(self) -> None:
        for item in self.inputs.expanded_jobs:
            key = _job_key(item.workflow, item.job)
            callers: list[tuple[WorkflowFact, JobFact]] = []
            reusable = self.reusable.get(item.workflow.path)
            if reusable is not None:
                for site in reusable.call_sites:
                    caller_workflow = self.workflow_by_path.get(site.caller_path)
                    if caller_workflow is not None:
                        callers.append((caller_workflow, site.caller_job))
            effective = effective_job_permissions(item.workflow, item.job, callers)
            self.effective[key] = effective
            self.diagnostics.extend(effective.diagnostics)
            self.intended[key] = self._intended_roles(item)
        registry = condition_keys()
        for item in self.inputs.expanded_jobs:
            key = _job_key(item.workflow, item.job)
            if self.effective[key].id_token_write is not True:
                continue
            candidates = self._candidates_for(item)
            for role in self.roles:
                if role.trust_unresolved:
                    continue
                cache_key = (role.id, item.workflow.path, item.job.id)
                candidates_filter = self.trust_filters.get(role.id)
                if candidates_filter is None:
                    candidates_filter = trust_subject_filter(role, registry)
                    self.trust_filters[role.id] = candidates_filter
                if candidates and not candidates_filter.may_match(candidates):
                    evaluation = self.no_match_evaluations.get(role.id)
                    if evaluation is None:
                        evaluation = no_match_evaluation(role, registry)
                        self.no_match_evaluations[role.id] = evaluation
                    match = None
                else:
                    evaluation = evaluate_trust_statements(role, candidates, registry=registry)
                    match = trust_match_from_evaluation(
                        role, candidates, evaluation, job_id=item.job.id
                    )
                self.trust_matches[cache_key] = match
                if match is not None:
                    self._record_trust_matches(role.id, evaluation)
                audited_job = self.job_nodes.get(key, job_node_id(item.workflow.path, item.job.id))
                audit: dict[str, object]
                if match is not None:
                    audit = {
                        "job": audited_job,
                        "breadth": match.breadth.value,
                        "format_drift": match.format_drift,
                        "unconstrained": match.unconstrained,
                        "dead_condition_keys": list(match.dead_condition_keys),
                        "missing_audience": match.missing_audience,
                    }
                else:
                    audit = {
                        "job": audited_job,
                        "breadth": None,
                        "format_drift": False,
                        "unconstrained": evaluation.unconstrained,
                        "dead_condition_keys": list(evaluation.dead_keys),
                        "missing_audience": evaluation.missing_audience,
                    }
                self.trust_audit.setdefault(role.id, []).append(audit)
        repo_write_candidates = _repo_write_candidates(self.inputs.repository)
        for role in self.roles:
            if role.trust_unresolved:
                continue
            match = evaluate_trust(
                role,
                repo_write_candidates,
                job_id="repo-write",
                registry=registry,
            )
            if match is not None and match.confidence is not EvidenceClass.UNKNOWN:
                self.repo_write_roles.add(role.id)
        self._collect_trust_policy_audit(registry)

    def _record_trust_matches(self, role_id: str, evaluation: TrustEvaluation) -> None:
        bucket = self.trust_matched_statements.setdefault(role_id, [])
        for match in evaluation.matches:
            if match.statement not in bucket:
                bucket.append(match.statement)

    def _collect_trust_policy_audit(self, registry: ConditionKeyRegistry) -> None:
        """Record policy-wide audit alternatives not already matched by an edge.

        Matched edges describe only the statements that accepted a candidate; a
        different offending Allow still needs its own provenance and weakest class.
        """
        for role in self.roles:
            if role.id not in self.trust_audit:
                continue
            evaluation = self.no_match_evaluations.get(role.id)
            if evaluation is None:
                evaluation = no_match_evaluation(role, registry)
            matched = self.trust_matched_statements.get(role.id, [])
            remaining = [
                item
                for item in evaluation.audit_alternatives
                if all(item.statement != statement for statement in matched)
            ]
            if not remaining:
                continue
            self.trust_policy_audit[role.id] = [
                {
                    "unconstrained": item.unconstrained,
                    "missing_audience": item.missing_audience,
                    "dead_condition_keys": list(item.dead_keys),
                    "evidence": [row.model_dump(mode="json") for row in item.statement.evidence],
                }
                for item in remaining
            ]

    def _expanded_for_ref(self, path: str, job: JobFact) -> ExpandedJob | None:
        return self.expanded_by_key.get((path, job.id))

    def _candidate_job(self, item: ExpandedJob) -> JobFact:
        steps = tuple(step.step for step in item.steps)
        if steps == item.job.steps:
            return item.job
        return item.job.model_copy(update={"steps": steps})

    def _candidates_for(
        self,
        item: ExpandedJob,
        stack: frozenset[tuple[str, str]] = frozenset(),
    ) -> tuple[SubjectCandidate, ...]:
        key = _job_key(item.workflow, item.job)
        cached = self.candidates.get(key)
        if cached is not None and key not in stack:
            return cached
        workflow_call = any(trigger.event == "workflow_call" for trigger in item.workflow.triggers)
        caller_candidates: tuple[SubjectCandidate, ...] = ()
        if workflow_call and key not in stack:
            nested = stack | {key}
            collected: dict[tuple[str, str, str, str], SubjectCandidate] = {}
            reusable = self.reusable.get(item.workflow.path)
            if reusable is not None:
                for site in reusable.call_sites:
                    caller_workflow = self.workflow_by_path.get(site.caller_path)
                    if caller_workflow is None:
                        continue
                    caller_item = self._expanded_for_ref(site.caller_path, site.caller_job)
                    if caller_item is None:
                        caller_item = ExpandedJob(
                            workflow=caller_workflow,
                            job=site.caller_job,
                            refs=site.caller_job.refs,
                            steps=tuple(ExpandedStep(step=step) for step in site.caller_job.steps),
                            diagnostics=(),
                        )
                    for candidate in self._candidates_for(caller_item, nested):
                        collected.setdefault(_subject_key(candidate), candidate)
            caller_candidates = tuple(collected[k] for k in sorted(collected))
        candidates = subject_candidates(
            self._candidate_job(item),
            item.workflow,
            repo_slug=self.inputs.repository.slug,
            default_branch=self.inputs.repository.default_branch,
            sub_template=self.inputs.config.sub_template,
            caller_candidates=caller_candidates,
        )
        if key not in stack:
            self.candidates[key] = candidates
        return candidates

    def _find_role(self, value: str) -> RoleFact | None:
        text = value.strip()
        for role in self.roles:
            if text in {role.arn, role.address, role.id}:
                return role
        return None

    def _intended_roles(self, item: ExpandedJob) -> frozenset[str]:
        roles: set[str] = set()
        for expanded in item.steps:
            auth = expanded.step.aws_auth
            if auth is None:
                continue
            target: str | None = None
            if auth.role_ref_kind == "ARN" and auth.role_arn:
                target = auth.role_arn
            elif auth.role_ref_kind == "EXPR" and auth.role_ref_name:
                target = self.inputs.config.role_binding(auth.role_ref_name)
            if target is None:
                continue
            role = self._find_role(target)
            if role is not None:
                roles.add(role.id)
        return frozenset(roles)

    # ----------------------------------------------------------------- R1

    def _repository_evidence(self) -> Evidence:
        identity = self.inputs.repository
        if identity.slug is not None:
            file = identity.source if identity.source in {".git/config", "nhi-blast.toml"} else None
            return self._evidence(
                EvidenceClass.DECLARED,
                "REPO.identity",
                file=file,
                detail=f"repository {identity.slug} resolved from {identity.source}",
            )
        return self._evidence(
            EvidenceClass.ASSUMED,
            "REPO.identity",
            detail="repository identity unresolved; subjects use */* and trust results are capped",
        )

    def _r1_structure(self) -> None:
        identity = self.inputs.repository
        slug = identity.slug or "*/*"
        repo_id = repo_node_id(slug)
        self._node(
            repo_id,
            NodeKind.REPOSITORY,
            slug,
            (self._repository_evidence(),),
            {
                "slug": identity.slug,
                "symbolic": identity.symbolic,
                "source": identity.source,
                "default_branch": identity.default_branch,
            },
        )
        for workflow in sorted(self.inputs.workflows, key=lambda item: item.path):
            workflow_id = workflow_node_id(workflow.path)
            evidence = self._evidence(
                EvidenceClass.DECLARED,
                "R1.workflow",
                file=workflow.path,
                line=1,
                detail=f"workflow {workflow.name or workflow.path}",
            )
            self._node(
                workflow_id,
                NodeKind.WORKFLOW,
                workflow.name or workflow.path,
                (evidence,),
                {
                    "path": workflow.path,
                    "name": workflow.name,
                    "triggers": [trigger.model_dump(mode="json") for trigger in workflow.triggers],
                },
            )
            self._edge(
                EdgeKind.CONTAINS,
                repo_id,
                workflow_id,
                (evidence,),
                attrs={"path": workflow.path},
            )
        for item in sorted(
            self.inputs.expanded_jobs,
            key=lambda entry: (entry.workflow.path, entry.job.id),
        ):
            self._add_job(item, workflow_node_id(item.workflow.path))

    def _add_job(self, item: ExpandedJob, workflow_id: str) -> None:
        key = _job_key(item.workflow, item.job)
        job_id = job_node_id(item.workflow.path, item.job.id)
        self.job_nodes[key] = job_id
        effective = self.effective[key]
        evidence = self._evidence(
            EvidenceClass.DECLARED,
            "R1.job",
            file=item.workflow.path,
            line=item.job.line,
            detail=f"job {item.job.id}",
        )
        self._node(
            job_id,
            NodeKind.JOB,
            item.job.name or item.job.id,
            (evidence,),
            {
                "path": item.workflow.path,
                "job_id": item.job.id,
                "runs_on": list(item.job.runs_on),
                "self_hosted": item.job.self_hosted,
                "environment": item.job.environment,
                "environment_unresolved": item.job.environment_unresolved,
                "secrets_mode": item.job.secrets_mode,
                "untrusted_checkout": item.job.untrusted_checkout,
                "untrusted_checkout_line": item.job.untrusted_checkout_line,
                "id_token_write": effective.id_token_write,
                "permissions": {
                    scope: level.value for scope, level in sorted(effective.levels.items())
                },
                "permissions_confidence": effective.cls.value,
                "permissions_default": effective.default_block,
            },
        )
        self._edge(
            EdgeKind.CONTAINS,
            workflow_id,
            job_id,
            (evidence,),
            attrs={"path": item.workflow.path, "job_id": item.job.id},
        )
        uses = item.job.uses_workflow
        if uses is not None and uses.kind == "REMOTE":
            self.diagnostics.append(
                info(
                    "D-GHA-REMOTE-REUSABLE",
                    f"reusable workflow {uses.raw} is remote; modelled on the caller grant only",
                    file=item.workflow.path,
                    line=uses.line,
                )
            )

    # ----------------------------------------------------------------- R2

    def _r2_actions(self) -> None:
        for item in sorted(
            self.inputs.expanded_jobs,
            key=lambda entry: (entry.workflow.path, entry.job.id),
        ):
            key = _job_key(item.workflow, item.job)
            job_id = self.job_nodes[key]
            for expanded in item.steps:
                uses = expanded.step.uses
                if uses is None:
                    continue
                source = _source_file(expanded, item.workflow)
                evidence = self._evidence(
                    EvidenceClass.DECLARED,
                    "R2.action-use",
                    file=source,
                    line=uses.line,
                    detail=f"uses {uses.raw}",
                )
                action_id = _action_id(uses)
                self._node(
                    action_id,
                    NodeKind.ACTION_REF,
                    uses.raw,
                    (evidence,),
                    {
                        "raw": uses.raw,
                        "kind": uses.kind,
                        "pin_kind": uses.pin_kind.value,
                        "mutable": uses.mutable,
                        "first_party": uses.first_party,
                        "owner": uses.owner,
                        "repo": uses.repo,
                        "subpath": uses.subpath,
                        "ref": uses.ref,
                        "composite": bool(expanded.composite_paths),
                    },
                )
                self._edge(
                    EdgeKind.RUNS_IN,
                    job_id,
                    action_id,
                    (evidence,),
                    lifetime=Lifetime.JOB_BOUND,
                    attrs={
                        "use_site": f"{source}:{uses.line}",
                        "composite_chain": list(expanded.composite_paths),
                    },
                )

    # ----------------------------------------------------------------- R3

    def _r3_builtin_credentials(self) -> None:
        for item in sorted(
            self.inputs.expanded_jobs,
            key=lambda entry: (entry.workflow.path, entry.job.id),
        ):
            key = _job_key(item.workflow, item.job)
            job_id = self.job_nodes[key]
            effective = self.effective[key]
            workflow = item.workflow
            evidence = self._evidence(
                EvidenceClass.DECLARED,
                "R3.github-token",
                file=workflow.path,
                line=item.job.line,
                detail="the runner exposes GITHUB_TOKEN to every job",
            )
            token_id = credential_node_id(job_id, "GITHUB_TOKEN")
            self._node(
                token_id,
                NodeKind.CREDENTIAL,
                "GITHUB_TOKEN",
                (evidence,),
                {
                    "credential_kind": "GITHUB_TOKEN",
                    "lifetime": Lifetime.JOB_BOUND.value,
                    "job": job_id,
                    "criticality": credential_heuristics().criticality(CredentialKind.GITHUB_TOKEN),
                },
            )
            self._edge(
                EdgeKind.HOLDS,
                job_id,
                token_id,
                (evidence,),
                lifetime=Lifetime.JOB_BOUND,
                attrs={"source": "built-in"},
            )
            if effective.id_token_write is False:
                continue
            cls = EvidenceClass.DERIVED if effective.id_token_write else EvidenceClass.UNKNOWN
            request_evidence = [
                *effective.evidence,
                self._evidence(
                    cls,
                    "R3.oidc-request-token",
                    file=workflow.path,
                    line=item.job.line,
                    detail="id-token is writable"
                    if cls is EvidenceClass.DERIVED
                    else "id-token writability is unresolved",
                ),
            ]
            request_id = credential_node_id(job_id, "OIDC_REQUEST_TOKEN")
            self._node(
                request_id,
                NodeKind.CREDENTIAL,
                "OIDC request token",
                request_evidence,
                {
                    "credential_kind": "OIDC_REQUEST_TOKEN",
                    "lifetime": Lifetime.JOB_BOUND.value,
                    "job": job_id,
                    "criticality": credential_heuristics().criticality(
                        CredentialKind.OIDC_REQUEST_TOKEN
                    ),
                },
            )
            self._edge(
                EdgeKind.HOLDS,
                job_id,
                request_id,
                request_evidence,
                lifetime=Lifetime.JOB_BOUND,
                attrs={"source": "permissions", "confidence": cls.value},
            )

    # ----------------------------------------------------------------- R4

    def _static_secret_sites(self, item: ExpandedJob) -> dict[str, list[tuple[str, int, str]]]:
        sites: dict[str, list[tuple[str, int, str]]] = {}
        for expanded in item.steps:
            auth = expanded.step.aws_auth
            if auth is None:
                continue
            source = _source_file(expanded, item.workflow)
            action = expanded.step.uses.raw if expanded.step.uses is not None else ""
            for name in auth.static_secret_refs:
                sites.setdefault(name, []).append((source, expanded.step.line, action))
        return sites

    def _r4_secrets(self) -> None:
        heuristics = credential_heuristics()
        for item in sorted(
            self.inputs.expanded_jobs,
            key=lambda entry: (entry.workflow.path, entry.job.id),
        ):
            key = _job_key(item.workflow, item.job)
            job_id = self.job_nodes[key]
            static_sites = self._static_secret_sites(item)
            for name in sorted(item.refs.secrets):
                if name in static_sites:
                    kind = CredentialKind.AWS_ACCESS_KEY
                    criticality = heuristics.criticality(kind)
                else:
                    kind, criticality = heuristics.classify_label(name)
                evidence = [
                    self._evidence(
                        EvidenceClass.DECLARED,
                        "R4.secret-reference",
                        file=item.workflow.path,
                        line=item.job.line,
                        detail=f"job references secret {name}",
                    ),
                    self._evidence(
                        EvidenceClass.ASSUMED,
                        "H-SECRET-NAME",
                        file=item.workflow.path,
                        line=item.job.line,
                        detail=(
                            f"secret name classified as {kind.value} (criticality {criticality})"
                        ),
                    ),
                ]
                for source, line, action in static_sites.get(name, ()):
                    evidence.append(
                        self._evidence(
                            EvidenceClass.DECLARED,
                            "GHA.static-aws-key",
                            file=source,
                            line=line,
                            detail=f"secret {name} fills static credential inputs of {action}",
                        )
                    )
                credential_id = credential_node_id(job_id, name)
                self._node(
                    credential_id,
                    NodeKind.CREDENTIAL,
                    name,
                    evidence,
                    {
                        "credential_kind": kind.value,
                        "criticality": criticality,
                        "lifetime": Lifetime.PERSISTENT.value,
                        "secret": True,
                        "static_aws_key": name in static_sites,
                    },
                )
                self._edge(
                    EdgeKind.HOLDS,
                    job_id,
                    credential_id,
                    (evidence[0],),
                    lifetime=Lifetime.JOB_BOUND,
                    attrs={"secret": name},
                )
            if item.refs.secrets_all or item.job.secrets_mode == "INHERIT":
                wildcard_id = credential_node_id(job_id, "*")
                wildcard_evidence = self._evidence(
                    EvidenceClass.UNKNOWN,
                    "A-RUNNER-SECRETS",
                    file=item.workflow.path,
                    line=item.job.line,
                    detail="every repository secret may be materialised; names and values unknown",
                )
                self._node(
                    wildcard_id,
                    NodeKind.CREDENTIAL,
                    "secrets.*",
                    (wildcard_evidence,),
                    {
                        "credential_kind": "GENERIC_SECRET",
                        "lifetime": Lifetime.PERSISTENT.value,
                        "wildcard": True,
                        "job": job_id,
                        "criticality": heuristics.criticality(CredentialKind.GENERIC_SECRET),
                    },
                )
                self._edge(
                    EdgeKind.HOLDS,
                    job_id,
                    wildcard_id,
                    (wildcard_evidence,),
                    lifetime=Lifetime.JOB_BOUND,
                    attrs={"wildcard": True},
                )

    # ----------------------------------------------------------------- R5

    def _r5_literals(self) -> None:
        for item in sorted(
            self.inputs.expanded_jobs,
            key=lambda entry: (entry.workflow.path, entry.job.id),
        ):
            key = _job_key(item.workflow, item.job)
            job_id = self.job_nodes[key]
            sites: list[tuple[LiteralHit, str]] = [
                (hit, item.workflow.path) for hit in item.job.literals
            ]
            for expanded in item.steps:
                source = _source_file(expanded, item.workflow)
                sites.extend((hit, source) for hit in expanded.step.literals)
            for hit, source in sites:
                key_part = f"literal:{source}:{hit.line}:{hit.pattern_id or hit.kind.value}"
                credential_id = credential_node_id(job_id, key_part)
                evidence = self._evidence(
                    EvidenceClass.DECLARED,
                    "H-LITERAL",
                    file=source,
                    line=hit.line,
                    detail=(
                        f"literal pattern {hit.pattern_id or hit.kind.value} matched; "
                        f"kind {hit.kind.value}; length {hit.length}; value not retained"
                    ),
                )
                self._node(
                    credential_id,
                    NodeKind.CREDENTIAL,
                    f"{hit.kind.value} literal ({hit.length} chars)",
                    (evidence,),
                    {
                        "credential_kind": hit.kind.value,
                        "criticality": credential_heuristics().criticality(hit.kind),
                        "lifetime": Lifetime.PERSISTENT.value,
                        "literal": True,
                        "length": hit.length,
                        "file": source,
                        "line": hit.line,
                    },
                )
                self._edge(
                    EdgeKind.HOLDS,
                    job_id,
                    credential_id,
                    (evidence,),
                    lifetime=Lifetime.JOB_BOUND,
                    attrs={"literal": True, "length": hit.length},
                )

    # ----------------------------------------------------------------- R6

    def _audiences(self, item: ExpandedJob) -> tuple[str, ...]:
        audiences = {
            expanded.step.aws_auth.audience
            for expanded in item.steps
            if expanded.step.aws_auth is not None and expanded.step.aws_auth.audience
        }
        return tuple(sorted(audiences or {DEFAULT_AUDIENCE}))

    def _r6_identities(self) -> None:
        for item in sorted(
            self.inputs.expanded_jobs,
            key=lambda entry: (entry.workflow.path, entry.job.id),
        ):
            key = _job_key(item.workflow, item.job)
            effective = self.effective[key]
            if effective.id_token_write is False:
                continue
            job_id = self.job_nodes[key]
            cls = EvidenceClass.DERIVED if effective.id_token_write else EvidenceClass.UNKNOWN
            entries: list[tuple[str, str]] = []
            for audience in self._audiences(item):
                evidence = [
                    *effective.evidence,
                    self._evidence(
                        cls,
                        "R6.oidc-identity",
                        file=item.workflow.path,
                        line=item.job.line,
                        detail=f"job can mint an OIDC token for audience {audience}",
                    ),
                ]
                identity_id = oidc_node_id(job_id, audience)
                self._node(
                    identity_id,
                    NodeKind.OIDC_IDENTITY,
                    f"OIDC identity ({audience})",
                    evidence,
                    {
                        "audience": audience,
                        "job": job_id,
                        "path": item.workflow.path,
                    },
                )
                self._edge(
                    EdgeKind.CAN_MINT,
                    job_id,
                    identity_id,
                    evidence,
                    lifetime=Lifetime.JOB_BOUND,
                    attrs={
                        "audience": audience,
                        **({"assumption": "A-OIDC-ENV"} if effective.id_token_write else {}),
                    },
                )
                entries.append((audience, identity_id))
            self.identities[key] = tuple(entries)
            if effective.id_token_write is True:
                self._use("A-OIDC-ENV")

    # ----------------------------------------------------------------- R7

    def _r7_cloud_principals(self) -> None:
        for provider in sorted(self.inputs.cloud.providers, key=lambda item: (item.host, item.url)):
            evidence = provider.evidence or (
                self._evidence(
                    EvidenceClass.DERIVED,
                    "R7.provider",
                    file=provider.host,
                    detail=f"OIDC provider {provider.host}",
                ),
            )
            self._node(
                provider_node_id(provider.host),
                NodeKind.AWS_OIDC_PROVIDER,
                provider.host,
                evidence,
                {"url": provider.url, "client_ids": list(provider.client_ids)},
            )
        for role in self.roles:
            evidence = role.evidence or (
                self._evidence(
                    EvidenceClass.DERIVED,
                    "R7.role",
                    file=role.address,
                    detail=f"AWS role {role.name}",
                ),
            )
            self._node(
                role.id,
                NodeKind.AWS_ROLE,
                role.arn or role.name,
                evidence,
                {
                    "address": role.address,
                    "name": role.name,
                    "arn": role.arn,
                    "max_session_duration": role.max_session_duration,
                    "trust_unresolved": role.trust_unresolved,
                    "unresolved_policy_refs": list(role.unresolved_policy_refs),
                    "managed_policy_arns": list(role.managed_policy_arns),
                    "has_boundary": role.boundary_supplied,
                    "inline_statement_count": len(role.inline_statements),
                    "trust_audit": self.trust_audit.get(role.id, []),
                    "trust_policy_audit": self.trust_policy_audit.get(role.id, []),
                    "repo_write_accepted": role.id in self.repo_write_roles,
                },
            )

    # ----------------------------------------------------------------- R8

    def _r8_trust(self) -> None:
        registry = condition_keys()
        for item in sorted(
            self.inputs.expanded_jobs,
            key=lambda entry: (entry.workflow.path, entry.job.id),
        ):
            key = _job_key(item.workflow, item.job)
            identities = self.identities.get(key, ())
            if not identities:
                continue
            candidates = self._candidates_for(item)
            intended = self.intended.get(key, frozenset())
            for role in self.roles:
                if role.trust_unresolved:
                    for audience, identity_id in identities:
                        self._unresolved_trust_edge(
                            role, identity_id, audience, role.id in intended
                        )
                    continue
                cache_key = (role.id, item.workflow.path, item.job.id)
                if cache_key in self.trust_matches:
                    match = self.trust_matches[cache_key]
                else:
                    match = evaluate_trust(role, candidates, job_id=item.job.id, registry=registry)
                if match is None:
                    continue
                self._use("A-REPO-AGE")
                for audience, identity_id in identities:
                    self._trust_edge(
                        role,
                        identity_id,
                        audience,
                        match,
                        intended=role.id in intended,
                    )

    def _role_evidence(self, role: RoleFact) -> tuple[Evidence, ...]:
        if role.evidence:
            return role.evidence
        return (
            self._evidence(
                EvidenceClass.DERIVED,
                "R7.role",
                file=role.address,
                detail=f"AWS role {role.name}",
            ),
        )

    def _unresolved_trust_edge(
        self,
        role: RoleFact,
        identity_id: str,
        audience: str,
        intended: bool,
    ) -> None:
        evidence = [
            *self._role_evidence(role),
            self._evidence(
                EvidenceClass.UNKNOWN,
                "A-TRUST-UNMODELLED",
                file=role.address,
                detail=f"trust policy for {role.name} could not be resolved",
            ),
        ]
        self._edge(
            EdgeKind.CAN_ASSUME,
            identity_id,
            role.id,
            evidence,
            attrs={
                "unresolved": True,
                "intended": intended,
                "audience": audience,
            },
        )

    def _trust_edge(
        self,
        role: RoleFact,
        identity_id: str,
        audience: str,
        match: TrustMatch,
        *,
        intended: bool,
    ) -> None:
        role_evidence = self._role_evidence(role)
        file, line = self._first_location(role_evidence)
        ttl = role.max_session_duration or 3600
        session_id = credential_node_id(identity_id, f"sts-session:{role.id}")
        session_evidence = [
            *role_evidence,
            *match.evidence,
            self._evidence(
                EvidenceClass.ASSUMED,
                "A-STS-TTL",
                file=file,
                line=line,
                detail=f"session lasts at most {ttl} s (role max_session_duration)",
            ),
        ]
        self._node(
            session_id,
            NodeKind.CREDENTIAL,
            f"STS session for {role.name}",
            session_evidence,
            {
                "credential_kind": "STS_SESSION",
                "lifetime": Lifetime.SESSION_TTL.value,
                "ttl_seconds": ttl,
                "role": role.id,
                "identity": identity_id,
                "audience": audience,
                "criticality": credential_heuristics().criticality(CredentialKind.STS_SESSION),
                "survival_window": f"up to {ttl} s",
            },
        )
        edge_evidence = [
            *match.evidence,
            *role_evidence,
            self._evidence(
                match.confidence,
                "R8.can-assume",
                file=file,
                line=line,
                detail=(
                    f"trust policy accepted {len(match.matched_candidates)} candidate "
                    f"subject(s); breadth {match.breadth.value}"
                ),
            ),
        ]
        matched_subjects = sorted({candidate.subject for candidate in match.matched_candidates})
        self._edge(
            EdgeKind.CAN_ASSUME,
            identity_id,
            role.id,
            edge_evidence,
            lifetime=Lifetime.SESSION_TTL,
            attrs={
                "session_credential": session_id,
                "intended": intended,
                "audience": audience,
                "breadth": match.breadth.value,
                "format_drift": match.format_drift,
                "unconstrained": match.unconstrained,
                "matched_candidates": matched_subjects,
                "matched_formats": [item.value for item in match.matched_formats],
                "additional_constraints": list(match.additional_constraints),
                "unresolved_reasons": list(match.unresolved_reasons),
                "dead_condition_keys": list(match.dead_condition_keys),
                "missing_audience": match.missing_audience,
                "assumptions": ["A-REPO-AGE"],
            },
        )
        self._use("A-STS-TTL")

    # ----------------------------------------------------------------- R9

    def _candidate_filters(
        self, actions_for: Callable[[SinkType], tuple[str, ...]]
    ) -> dict[tuple[str, SinkType], CandidateFilter]:
        context = self.inputs.cloud.policy_context
        return {
            (role.id, sink_type): action_filter(role, context, actions_for(sink_type))
            for role in self.roles
            for sink_type in SinkType
        }

    def _may_act(
        self,
        role: RoleFact,
        candidate_arns: Sequence[str],
        candidates: CandidateFilter,
    ) -> bool:
        # Unresolved policy bodies can still produce A-POLICY-UNMODELLED edges from
        # a NOT_APPLICABLE decision, so their policy pairs are always evaluated.
        if role.unresolved_policy_refs:
            return True
        return candidates.could_apply(candidate_arns)

    def _decision_evidence(
        self,
        result: DecisionResult,
        rule: str,
        role_file: str | None,
        role_line: int | None,
    ) -> Evidence | None:
        if result.decision in {Decision.DENY, Decision.NOT_APPLICABLE}:
            return None
        reasons = [*result.reasons, *result.conditional_reasons]
        detail = "; ".join(reasons) or result.decision.value
        if result.external_wildcard:
            return self._evidence(
                EvidenceClass.UNKNOWN,
                "A-SCOPE-INPUT",
                file=role_file,
                line=role_line,
                detail=f"policy resource can cover resources outside the inputs: {detail}",
            )
        return self._evidence(
            result.evidence_class,
            rule,
            file=role_file,
            line=role_line,
            detail=f"{result.decision.value}: {detail}",
        )

    def _policy_edge(
        self,
        kind: EdgeKind,
        rule: str,
        role: RoleFact,
        sink: SinkFact,
        result: DecisionResult,
    ) -> None:
        role_evidence = self._role_evidence(role)
        file, line = self._first_location(role_evidence)
        decision = self._decision_evidence(result, rule, file, line)
        if decision is None:
            if result.decision is Decision.NOT_APPLICABLE and role.unresolved_policy_refs:
                missing = self._evidence(
                    EvidenceClass.UNKNOWN,
                    "A-POLICY-UNMODELLED",
                    file=file,
                    line=line,
                    detail=(
                        "attached policy bodies are unresolved: "
                        + ", ".join(role.unresolved_policy_refs)
                    ),
                )
                self._edge(
                    kind,
                    role.id,
                    sink.id,
                    [*role_evidence, *sink.evidence, missing],
                    attrs={
                        "decision": "unknown",
                        "unresolved_policy_refs": list(role.unresolved_policy_refs),
                    },
                )
                self._use("A-POLICY-UNMODELLED")
            return
        self._edge(
            kind,
            role.id,
            sink.id,
            [*role_evidence, *sink.evidence, decision],
            attrs={
                "decision": result.decision.value,
                "reasons": list(result.reasons),
                "conditional_reasons": list(result.conditional_reasons),
                "assumptions": list(result.assumptions),
                "external_wildcard": result.external_wildcard,
            },
        )
        for assumption in result.assumptions:
            self._use(assumption)

    def _r9_reads(self) -> None:
        context = self.inputs.cloud.policy_context
        filters = self._candidate_filters(read_actions)
        arns_by_sink = {
            sink.id: candidate_arns(sink, region=context.region, account=context.account)
            for sink in self.sinks
        }
        for role in self.roles:
            for sink in self.sinks:
                candidates = filters[(role.id, sink.sink_type)]
                if not self._may_act(role, arns_by_sink[sink.id], candidates):
                    continue
                result = can_read(
                    role,
                    sink,
                    context,
                    region=context.region,
                    account=context.account,
                )
                self._policy_edge(EdgeKind.CAN_READ_VALUE, "R9.can_read", role, sink, result)

    # ---------------------------------------------------------------- R10

    def _r10_sinks(self) -> None:
        for sink in self.sinks:
            sink_evidence = sink.evidence or (
                self._evidence(
                    EvidenceClass.DERIVED,
                    "R10.sink",
                    file=sink.arn or sink.name,
                    detail=f"credential store {sink.name}",
                ),
            )
            self._node(
                sink.id,
                NodeKind.SINK,
                sink.name,
                sink_evidence,
                {
                    "sink_type": sink.sink_type.value,
                    "arn": sink.arn,
                    "kms_key_id": sink.kms_key_id,
                    "rotation_interval_days": sink.rotation_interval_days,
                    "credential_bearing": sink.credential_kind is not None,
                    "credential_kind": (
                        sink.credential_kind.value if sink.credential_kind else None
                    ),
                    "criticality": sink.criticality,
                },
            )
            if sink.credential_kind is None:
                continue
            file, line = self._first_location(sink_evidence)
            lifetime = (
                Lifetime.PERSISTENT_ROTATING
                if sink.rotation_interval_days is not None
                else Lifetime.PERSISTENT
            )
            credential_id = credential_node_id(sink.id, "stored")
            evidence = [
                *sink_evidence,
                self._evidence(
                    EvidenceClass.ASSUMED,
                    "H-SECRET-NAME",
                    file=file,
                    line=line,
                    detail=(
                        f"{sink.name} classified as {sink.credential_kind.value} "
                        f"(criticality {sink.criticality})"
                    ),
                ),
            ]
            if sink.rotation_interval_days is not None:
                evidence.append(
                    self._evidence(
                        EvidenceClass.ASSUMED,
                        "H-ROT-WINDOW",
                        file=file,
                        line=line,
                        detail=f"rotation every {sink.rotation_interval_days} days",
                    )
                )
            self._node(
                credential_id,
                NodeKind.CREDENTIAL,
                sink.name,
                evidence,
                {
                    "credential_kind": sink.credential_kind.value,
                    "criticality": sink.criticality,
                    "lifetime": lifetime.value,
                    "sink": sink.id,
                    "rotation_interval_days": sink.rotation_interval_days,
                    "survival_window": (
                        f"up to {sink.rotation_interval_days} days"
                        if sink.rotation_interval_days is not None
                        else "until rotated"
                    ),
                },
            )
            self._edge(
                EdgeKind.STORES,
                sink.id,
                credential_id,
                evidence,
                lifetime=lifetime,
                attrs={"credential_kind": sink.credential_kind.value},
            )
            self.stored_credential[sink.id] = credential_id
            self.credential_sink[credential_id] = sink

    # ---------------------------------------------------------------- R11

    def _config_role_node(self, binding: str) -> str:
        existing = self._find_role(binding)
        if existing is not None:
            return existing.id
        node_id = role_node_id(binding)
        evidence = self._evidence(
            EvidenceClass.DECLARED,
            "CONFIG.credential-binding",
            file=self.inputs.config.path,
            detail=f"configured identity {binding}",
        )
        self._node(
            node_id,
            NodeKind.AWS_ROLE,
            binding,
            (evidence,),
            {"bound_only": True, "arn": binding if binding.startswith("arn:") else None},
        )
        return node_id

    def _unbound_identity_node(self) -> str:
        node_id = external_node_id("aws-identity-unbound")
        evidence = self._evidence(
            EvidenceClass.ASSUMED,
            "R11.static-aws-key",
            detail="static AWS keys authenticate without a bound role identity",
        )
        self._node(
            node_id,
            NodeKind.EXTERNAL_TARGET,
            "aws-identity-unbound",
            (evidence,),
            {"kind": "aws_identity", "unbound": True},
        )
        return node_id

    def _r11_static_keys(self) -> None:
        for item in sorted(
            self.inputs.expanded_jobs,
            key=lambda entry: (entry.workflow.path, entry.job.id),
        ):
            key = _job_key(item.workflow, item.job)
            job_id = self.job_nodes[key]
            for expanded in item.steps:
                auth = expanded.step.aws_auth
                if auth is None or not auth.static_keys or not auth.static_secret_refs:
                    continue
                source = _source_file(expanded, item.workflow)
                action = expanded.step.uses.raw if expanded.step.uses is not None else ""
                for name in sorted(auth.static_secret_refs):
                    credential_id = credential_node_id(job_id, name)
                    if not self.store.has_node(credential_id):
                        continue
                    binding = self.inputs.config.credential_binding(
                        name
                    ) or self.inputs.config.credential_binding(f"secrets.{name}")
                    if binding:
                        target = self._config_role_node(binding)
                    else:
                        target = self._unbound_identity_node()
                    evidence = [
                        self._evidence(
                            EvidenceClass.DECLARED,
                            "GHA.static-aws-key",
                            file=source,
                            line=expanded.step.line,
                            detail=f"secret {name} fills static credential inputs of {action}",
                        ),
                        self._evidence(
                            EvidenceClass.ASSUMED,
                            "H-SECRET-NAME",
                            file=source,
                            line=expanded.step.line,
                            detail=f"secret {name} classified as AWS_ACCESS_KEY",
                        ),
                    ]
                    if binding:
                        evidence.append(
                            self._evidence(
                                EvidenceClass.DECLARED,
                                "CONFIG.credential-binding",
                                file=self.inputs.config.path,
                                detail=f"secret {name} is bound to {binding}",
                            )
                        )
                    else:
                        evidence.append(
                            self._evidence(
                                EvidenceClass.ASSUMED,
                                "R11.static-aws-key",
                                file=source,
                                line=expanded.step.line,
                                detail="no configured identity binding for the static key",
                            )
                        )
                    self._edge(
                        EdgeKind.AUTHENTICATES_AS,
                        credential_id,
                        target,
                        evidence,
                        attrs={
                            "secret": name,
                            "binding": binding,
                            "unbound": binding is None,
                            "action": action,
                        },
                    )

    # ---------------------------------------------------------------- R12

    def _target_values(self, target: ExternalTargetFact) -> set[str]:
        identifier = target.label.partition(":")[2]
        values = {target.label, identifier}
        if target.address:
            values.update(
                {
                    target.address,
                    f"{target.address}.id",
                    f"{target.address}.arn",
                }
            )
        return {value for value in values if value}

    def _sink_for_label(self, label: str) -> SinkFact | None:
        options = {label, label.lstrip("/")}
        for sink in self.sinks:
            if sink.name in options or label in (sink.arn, sink.id):
                return sink
        return None

    def _r12_databases(self) -> None:
        bindings = [
            (key.strip(), value.strip())
            for key, value in sorted(self.inputs.config.credential_bindings.items())
        ]
        for target in self.externals:
            node_id = external_node_id(target.label)
            evidence = target.evidence or (
                self._evidence(
                    EvidenceClass.DERIVED,
                    "R12.database",
                    file=target.address,
                    detail=f"external target {target.label}",
                ),
            )
            self._node(
                node_id,
                NodeKind.EXTERNAL_TARGET,
                target.label,
                evidence,
                {
                    "kind": target.kind,
                    "address": target.address,
                    "credential_refs": list(target.credential_refs),
                },
            )
            bound: dict[str, str] = {}
            for candidate in self.sinks:
                credential_id = self.stored_credential.get(candidate.id)
                if credential_id is None:
                    continue
                if candidate.arn is not None and candidate.arn in target.credential_refs:
                    bound.setdefault(credential_id, "master_user_secret")
                if candidate.id in target.credential_refs:
                    bound.setdefault(credential_id, "master_user_secret")
            target_values = self._target_values(target)
            for label, value in bindings:
                if value not in target_values:
                    continue
                matched = self._sink_for_label(label)
                if matched is None:
                    continue
                credential_id = self.stored_credential.get(matched.id)
                if credential_id is not None:
                    bound.setdefault(credential_id, "config")
            for credential_id in sorted(bound):
                origin = self.credential_sink.get(credential_id)
                sink_evidence = origin.evidence if origin is not None else ()
                binding_kind = bound[credential_id]
                binding_evidence = [
                    self._evidence(
                        EvidenceClass.ASSUMED,
                        "R12.database",
                        file=target.address,
                        detail=f"master credential bound via {binding_kind}",
                    )
                ]
                if binding_kind == "config":
                    binding_evidence.append(
                        self._evidence(
                            EvidenceClass.DECLARED,
                            "CONFIG.credential-binding",
                            file=self.inputs.config.path,
                            detail=f"stored credential bound to {target.address or target.label}",
                        )
                    )
                self._edge(
                    EdgeKind.AUTHENTICATES_AS,
                    credential_id,
                    node_id,
                    [*sink_evidence, *evidence, *binding_evidence],
                    attrs={"target": target.label, "binding": binding_kind},
                )

    def _r12_credential_bindings(self) -> None:
        """Spec 14.3: a stored credential label may unlock a role or external target."""
        bindings = sorted(
            (key.strip(), value.strip())
            for key, value in self.inputs.config.credential_bindings.items()
        )
        external_values: set[str] = set()
        for target in self.externals:
            external_values.update(self._target_values(target))
        seen: set[tuple[str, str]] = set()
        for label, value in bindings:
            if not label or not value or value in external_values:
                continue
            sink = self._sink_for_label(label)
            if sink is None:
                continue
            credential_id = self.stored_credential.get(sink.id)
            if credential_id is None:
                continue
            role = self._find_role(value)
            target_id = role.id if role is not None else self._config_role_node(value)
            key = (credential_id, target_id)
            if key in seen:
                continue
            seen.add(key)
            evidence = [
                self._evidence(
                    EvidenceClass.DECLARED,
                    "CONFIG.credential-binding",
                    file=self.inputs.config.path,
                    detail=f"stored credential {label} is bound to {value}",
                ),
                self._evidence(
                    EvidenceClass.ASSUMED,
                    "R12.credential-binding",
                    file=self.inputs.config.path,
                    detail=f"holding {sink.name} grants the bound identity",
                ),
            ]
            self._edge(
                EdgeKind.AUTHENTICATES_AS,
                credential_id,
                target_id,
                evidence,
                attrs={"credential": sink.name, "binding": value, "config": True},
            )

    # ---------------------------------------------------------------- R13

    def _r13_modify(self) -> None:
        context = self.inputs.cloud.policy_context
        filters = self._candidate_filters(modify_actions)
        arns_by_sink = {
            sink.id: candidate_arns(sink, region=context.region, account=context.account)
            for sink in self.sinks
        }
        for role in self.roles:
            for sink in self.sinks:
                candidates = filters[(role.id, sink.sink_type)]
                if not self._may_act(role, arns_by_sink[sink.id], candidates):
                    continue
                result = can_modify(
                    role,
                    sink,
                    context,
                    region=context.region,
                    account=context.account,
                )
                self._policy_edge(EdgeKind.CAN_MODIFY, "R13.can_modify", role, sink, result)

    # ------------------------------------------------------------- assemble

    def build(self) -> GraphBuild:
        self._prepare()
        self._r1_structure()
        self._r2_actions()
        self._r3_builtin_credentials()
        self._r4_secrets()
        self._r5_literals()
        self._r6_identities()
        self._r7_cloud_principals()
        self._r8_trust()
        self._r9_reads()
        self._r10_sinks()
        self._r11_static_keys()
        self._r12_databases()
        self._r12_credential_bindings()
        self._r13_modify()
        truncated = self.truncated or self.store.budget_exceeded
        if truncated:
            self.store.prune_dangling()
            self.diagnostics.append(
                error(
                    "D-GRAPH-LIMIT",
                    "graph reached the configured node budget; results are partial",
                )
            )
        return GraphBuild(
            graph=self.store.data(),
            diagnostics=DiagnosticBag(self.diagnostics).sorted(),
            assumptions_used=tuple(sorted(self.assumptions)),
            truncated=truncated,
        )


def build_graph(inputs: GraphInputs) -> GraphBuild:
    """Apply R1-R14 and return the validated graph."""
    return _Builder(inputs).build()


__all__ = [
    "GraphBuild",
    "GraphInputs",
    "build_graph",
]
