"""Typed domain models shared across the pipeline (spec chapters 4, 9, 10, 12, 13).

Parsers produce facts; resolvers derive policy decisions; the graph builder emits
Node/Edge records; the analysis engine emits the partition, rotation plan and
findings; reporters render a Report. All models are immutable so a stage cannot
silently mutate another stage's output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from nhi_blast import SCHEMA_VERSION
from nhi_blast.core.diagnostics import Diagnostic
from nhi_blast.core.evidence import Evidence, EvidenceClass


class NodeKind(StrEnum):
    REPOSITORY = "REPOSITORY"
    WORKFLOW = "WORKFLOW"
    JOB = "JOB"
    ACTION_REF = "ACTION_REF"
    CREDENTIAL = "CREDENTIAL"
    OIDC_IDENTITY = "OIDC_IDENTITY"
    AWS_OIDC_PROVIDER = "AWS_OIDC_PROVIDER"
    AWS_ROLE = "AWS_ROLE"
    SINK = "SINK"
    EXTERNAL_TARGET = "EXTERNAL_TARGET"


class EdgeKind(StrEnum):
    CONTAINS = "CONTAINS"
    RUNS_IN = "RUNS_IN"
    HOLDS = "HOLDS"
    CAN_MINT = "CAN_MINT"
    CAN_ASSUME = "CAN_ASSUME"
    CAN_READ_VALUE = "CAN_READ_VALUE"
    STORES = "STORES"
    AUTHENTICATES_AS = "AUTHENTICATES_AS"
    CAN_MODIFY = "CAN_MODIFY"


class Lifetime(StrEnum):
    JOB_BOUND = "job_bound"
    SESSION_TTL = "session_ttl"
    PERSISTENT = "persistent"
    PERSISTENT_ROTATING = "persistent_rotating"
    NA = "na"


PERSISTENT_LIFETIMES: frozenset[Lifetime] = frozenset(
    {Lifetime.PERSISTENT, Lifetime.PERSISTENT_ROTATING}
)

# CONTAINS is structural only and never traversed for authority (spec 4.3).
AUTHORITY_EDGE_KINDS: frozenset[EdgeKind] = frozenset(
    {
        EdgeKind.RUNS_IN,
        EdgeKind.HOLDS,
        EdgeKind.CAN_MINT,
        EdgeKind.CAN_ASSUME,
        EdgeKind.CAN_READ_VALUE,
        EdgeKind.STORES,
        EdgeKind.AUTHENTICATES_AS,
    }
)

# Deterministic traversal order for out-edges (spec 12.2).
EDGE_KIND_ORDER: dict[EdgeKind, int] = {kind: index for index, kind in enumerate(EdgeKind)}

NODE_KIND_ORDER: dict[NodeKind, int] = {kind: index for index, kind in enumerate(NodeKind)}


class CredentialKind(StrEnum):
    GITHUB_TOKEN = "GITHUB_TOKEN"
    OIDC_REQUEST_TOKEN = "OIDC_REQUEST_TOKEN"
    OIDC_JWT = "OIDC_JWT"
    STS_SESSION = "STS_SESSION"
    GITHUB_SECRET = "GITHUB_SECRET"
    AWS_ACCESS_KEY = "AWS_ACCESS_KEY"
    DATABASE_PASSWORD = "DATABASE_PASSWORD"
    PRIVATE_KEY = "PRIVATE_KEY"
    API_KEY = "API_KEY"
    API_TOKEN = "API_TOKEN"
    WEBHOOK_URL = "WEBHOOK_URL"
    GENERIC_SECRET = "GENERIC_SECRET"


class PinKind(StrEnum):
    SHA = "SHA"
    TAG = "TAG"
    BRANCH = "BRANCH"
    AMBIGUOUS = "AMBIGUOUS"
    DOCKER = "DOCKER"
    LOCAL = "LOCAL"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


_SEVERITY_RANK = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def severity_rank(value: Severity) -> int:
    return _SEVERITY_RANK[value]


def severity_at_least(value: Severity, threshold: Severity) -> bool:
    return _SEVERITY_RANK[value] <= _SEVERITY_RANK[threshold]


def parse_severity(text: str) -> Severity:
    """Case-insensitive parse used by --fail-on; raises ValueError on bad input."""
    try:
        return Severity(text.upper())
    except ValueError:
        msg = f"unknown severity: {text}"
        raise ValueError(msg) from None


class PermLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    NONE = "none"
    UNKNOWN = "unknown"


class SubFormat(StrEnum):
    CLASSIC = "CLASSIC"
    IMMUTABLE = "IMMUTABLE"
    UNKNOWN = "UNKNOWN"


class SinkType(StrEnum):
    SECRETSMANAGER_SECRET = "secretsmanager_secret"
    SSM_PARAMETER = "ssm_parameter"


class TfSource(StrEnum):
    PLAN = "plan"
    STATE = "state"
    HCL = "hcl"
    IAM_JSON = "iam_json"


class Decision(StrEnum):
    ALLOW = "ALLOW"
    CONDITIONAL_ALLOW = "CONDITIONAL_ALLOW"
    DENY = "DENY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PolicyEffect(StrEnum):
    ALLOW = "Allow"
    DENY = "Deny"


class Breadth(StrEnum):
    UNCONSTRAINED = "UNCONSTRAINED"
    ANY_ORG = "ANY_ORG"
    SAME_ORG = "SAME_ORG"
    REPO_ANY_CONTEXT = "REPO_ANY_CONTEXT"
    REPO_ANY_BRANCH = "REPO_ANY_BRANCH"
    REPO_PULL_REQUEST = "REPO_PULL_REQUEST"
    ENVIRONMENT = "ENVIRONMENT"
    EXACT_REF = "EXACT_REF"


class Node(BaseModel):
    """A vertex of the authority multigraph (spec 4.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: NodeKind
    label: str
    attrs: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[Evidence, ...] = ()


class Edge(BaseModel):
    """A directed edge; confidence is the weakest class among its evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: EdgeKind
    src: str
    dst: str
    lifetime: Lifetime = Lifetime.NA
    confidence: EvidenceClass = EvidenceClass.UNKNOWN
    evidence: tuple[Evidence, ...] = ()
    attrs: dict[str, Any] = Field(default_factory=dict)

    def sort_key(self) -> tuple[int, int, str, str, str]:
        return (EDGE_KIND_ORDER[self.kind], 0, self.dst, self.src, self.id)


class GraphData(BaseModel):
    """Serialised graph included in the JSON report."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()


class Statement(BaseModel):
    """One normalised IAM statement (spec 9.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    effect: PolicyEffect
    actions: tuple[str, ...] = ()
    not_actions: tuple[str, ...] = ()
    resources: tuple[str, ...] = ()
    not_resources: tuple[str, ...] = ()
    principals: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    conditions: dict[str, dict[str, tuple[str, ...]]] = Field(default_factory=dict)
    sid: str | None = None
    evidence: tuple[Evidence, ...] = ()


class RoleFact(BaseModel):
    """An AWS IAM role as resolved from Terraform and/or IAM JSON inputs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    address: str
    name: str
    arn: str | None = None
    max_session_duration: int = 3600
    trust_statements: tuple[Statement, ...] = ()
    inline_statements: tuple[Statement, ...] = ()
    managed_policy_arns: tuple[str, ...] = ()
    boundary_statements: tuple[Statement, ...] = ()
    boundary_supplied: bool = False
    trust_unresolved: bool = False
    unresolved_policy_refs: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()


class SinkFact(BaseModel):
    """A credential store that may hold a value (spec 8.3, R10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    sink_type: SinkType
    arn: str | None = None
    kms_key_id: str | None = None
    rotation_interval_days: int | None = None
    resource_policy_statements: tuple[Statement, ...] = ()
    credential_kind: CredentialKind | None = None
    criticality: int = 0
    evidence: tuple[Evidence, ...] = ()


class ProviderFact(BaseModel):
    """A cloud OIDC provider as resolved from Terraform or IAM JSON."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str
    url: str
    client_ids: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()


class ExternalTargetFact(BaseModel):
    """A non-AWS target a credential unlocks (database, SaaS endpoint)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str
    kind: str = "external"
    address: str | None = None
    credential_refs: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()


class PolicyContext(BaseModel):
    """Ambient facts needed to evaluate a policy decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account: str | None = None
    region: str | None = None
    managed_policies: dict[str, tuple[Statement, ...]] = Field(default_factory=dict)


class DecisionResult(BaseModel):
    """Outcome of can(role, action, resource) with its evidence class."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Decision
    evidence_class: EvidenceClass
    reasons: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    conditional_reasons: tuple[str, ...] = ()
    external_wildcard: bool = False


class SubjectCandidate(BaseModel):
    """A glob describing the sub values a job could mint for one trigger."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    format: SubFormat
    trigger: str
    audience: str
    claims: dict[str, str] = Field(default_factory=dict)
    evidence_class: EvidenceClass = EvidenceClass.DERIVED
    evidence: tuple[Evidence, ...] = ()


class TrustMatch(BaseModel):
    """Result of evaluating a role trust policy against a job's candidates."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str
    role_id: str
    matched_candidates: tuple[SubjectCandidate, ...] = ()
    matched_formats: tuple[SubFormat, ...] = ()
    breadth: Breadth = Breadth.EXACT_REF
    format_drift: bool = False
    confidence: EvidenceClass = EvidenceClass.DERIVED
    unresolved_reasons: tuple[str, ...] = ()
    additional_constraints: tuple[str, ...] = ()
    unconstrained: bool = False
    dead_condition_keys: tuple[str, ...] = ()
    missing_audience: bool = False
    evidence: tuple[Evidence, ...] = ()


class ECredential(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    credential: str
    ttl_seconds: int


class ZCredential(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    credential: str
    depth: int
    lifetime: Lifetime
    survival_window: str
    criticality: int


class Partition(BaseModel):
    """R/E/Z membership for one scenario (spec 4.4, 13.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    R: tuple[str, ...] = ()
    E: tuple[ECredential, ...] = ()
    Z: tuple[ZCredential, ...] = ()


class StepPhase(StrEnum):
    CONTAINMENT = "containment"
    ROTATION = "rotation"
    VERIFY = "verify"


class CredentialRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    label: str
    kind: CredentialKind
    lifetime: Lifetime
    survival_window: str
    criticality: int
    evidence: tuple[Evidence, ...] = ()


class RotationStep(BaseModel):
    """One rotation or containment action; a batch step covers one SCC."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: StepPhase
    order: int
    generation: int | None = None
    credentials: tuple[CredentialRef, ...] = ()
    batch: bool = False
    depends_on: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    confidence: EvidenceClass = EvidenceClass.ASSUMED
    evidence: tuple[Evidence, ...] = ()


class RotationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    containment: tuple[RotationStep, ...] = ()
    rotation: tuple[RotationStep, ...] = ()
    verify: tuple[RotationStep, ...] = ()
    notes: tuple[str, ...] = ()


class Finding(BaseModel):
    """A rule hit with provenance; severity is a label for ordering, not a verdict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    rule: str
    severity: Severity
    confidence: EvidenceClass
    title: str
    message: str
    evidence: tuple[Evidence, ...] = ()
    path: tuple[str, ...] = ()
    path_edges: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    scenario: str | None = None

    def sort_key(self) -> tuple[int, str, str]:
        return (severity_rank(self.severity), self.rule, self.id)


class ScenarioReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    selector: str
    start_nodes: tuple[str, ...] = ()
    partition: Partition = Field(default_factory=Partition)
    potential: tuple[str, ...] = ()
    potential_nodes: tuple[str, ...] = ()
    unresolved_inputs: tuple[str, ...] = ()
    truncated: bool = False
    rotation_plan: RotationPlan = Field(default_factory=RotationPlan)
    findings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


class ToolInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = "nhi-blast"
    version: str


class InputFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    sha256: str
    kind: str


class Inputs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    digest: str
    repo_slug: str
    repo_slug_source: str
    files: tuple[InputFile, ...] = ()


class AssumptionUse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    statement: str
    verify: bool = False
    used_by: tuple[str, ...] = ()


class DataFileInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    verified_on: str
    source_url: str
    entry_count: int = 0


class Report(BaseModel):
    """nhi-blast-report/1.0 JSON document (spec 13.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_id: str = Field(default=SCHEMA_VERSION, serialization_alias="schema", alias="schema")
    tool: ToolInfo
    inputs: Inputs
    scope_and_limits: tuple[str, ...] = ()
    assumptions: tuple[AssumptionUse, ...] = ()
    data_files: tuple[DataFileInfo, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    findings: tuple[Finding, ...] = ()
    graph: GraphData = Field(default_factory=GraphData)
    scenarios: tuple[ScenarioReport, ...] = ()
    generated_at: str | None = None

    def sorted_findings(self) -> tuple[Finding, ...]:
        return tuple(sorted(self.findings, key=lambda f: f.sort_key()))


class RankRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: str
    pin_kind: PinKind
    use_sites: int
    jobs_with_oidc: int
    r_count: int
    e_count: int
    z_count: int
    highest_criticality: int

    def sort_key(self) -> tuple[int, int, int, str]:
        return (-self.z_count, -self.e_count, -self.use_sites, self.action)


class RankReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_id: str = Field(
        default=SCHEMA_VERSION + "/rank", serialization_alias="schema", alias="schema"
    )
    tool: ToolInfo
    inputs: Inputs
    rows: tuple[RankRow, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class ParseResult[T]:
    """A parser never raises on bad input: partial facts plus diagnostics."""

    facts: T | None
    diagnostics: tuple[Diagnostic, ...] = ()
