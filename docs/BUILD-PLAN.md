# NHI-Blast — Architecture and Execution Plan

Status: active build plan, derived from `docs/SPEC.md`, `AGENTS.md` and the verified
repository state on 2026-10-25. The specification is normative; this document turns
it into an ordered, executable programme. Where this plan and the specification
disagree, the specification wins and this plan must be corrected.

This plan is written so a less capable agent can execute it without inventing
architecture. Follow it in order. Do not skip a milestone. Do not weaken a test or a
gate to get a green result.

---

## 0. How to execute this plan

### 0.1 Environment

```sh
cd /c/Cyber
./.venv/Scripts/python.exe -m pip install -e ".[dev,rich,hcl]"
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m ruff check src tests
./.venv/Scripts/python.exe -m ruff format --check src tests
./.venv/Scripts/python.exe -m mypy src
```

The shell is Git Bash on Windows. Use forward slashes. Prefer the `Read`, `Write` and
`Edit` tools for files; never inline Python containing braces into a shell command.
When a command needs a temporary script, write it to `scripts/_tmp.py` and run it.

### 0.2 Working rules

1. One file per write. After each file run `ruff check` and `mypy` on `src`.
2. Write or extend a test before or with each behaviour. Never delete a failing
   assertion; diagnose the root cause.
3. Parsers never raise on hostile input. They return partial facts plus diagnostics.
4. Never read, store, print, log or snapshot a credential value. Literal hits carry
   kind, length, line and pattern id only. Sensitive Terraform leaves are never read.
5. No runtime network access, no execution of scanned content, no expression
   evaluation.
6. Determinism: sorted arrays, no set iteration in output, no wall clock unless
   `--timestamp`.
7. Update `docs/implementation-status.md` and `docs/requirements-traceability.md`
   after every milestone with the commands actually run and their actual results.
8. If a gate genuinely cannot pass, record the blocker and next action. Never claim
   success from a command that did not run.

### 0.3 Definition of “done” for a change

- The new behaviour has a focused test.
- The relevant suite passes, and `ruff check`, `ruff format --check` and
  `mypy --strict` are clean.
- No secret value appears in any artifact.
- The change is documented where the specification requires it.
- The traceability row for the relevant specification section is updated.

---

## 1. Product invariants (never violate)

1. **Evidence honesty.** Every node and edge carries at least one `Evidence` with
   class `DECLARED > DERIVED > ASSUMED > UNKNOWN`. Edge confidence is the weakest
   class among its evidence. UNKNOWN edges never contribute to R, E or Z; they feed
   `potential` only.
2. **Claim hygiene.** Use “potentially reachable”, “accepted by the trust policy as
   written”, “survives revocation if the path was exercised”. Never “proves”,
   “guarantees”, “is exploitable” or “is taken over”.
3. **No secret values.** A credential identified is not a credential proven obtained.
4. **No execution.** Never run terraform/tofu/git/shell/actions. Never fetch modules
   or providers. Never evaluate GitHub expressions.
5. **Safe parsing.** `yaml.compose` plus `SafeLoader`, marks, duplicate-key
   detection, YAML 1.1 `on` normalisation, first document only, configured limits.
6. **Path safety.** Resolve every path; it must stay inside the scan root; never
   follow an escaping symlink.
7. **Determinism.** Equal inputs produce byte-identical artifacts. Identifiers per
   specification 5.5. No wall clock unless `--timestamp`.
8. **Report security.** HTML data uses unicode-escaped JSON, DOM via `textContent`
   and `setAttribute`, restrictive CSP with inline-script hashes, no network.
9. **No fabrication.** Do not invent sources, benchmarks, compatibility claims,
   tests, audits or results. Anything marked VERIFY is ASSUMED and listed.
10. **Job scope.** `RUNS_IN` and `HOLDS` attach to a job, never a workflow. A
    compromised step reaches only its own job. Job outputs and artifacts are not
    modelled.

---

## 2. Verified current state

At the start of this phase the following command sequence is green:

```sh
ruff check src              # clean
ruff format --check src     # clean
mypy src                    # clean, 41 files
pytest --collect-only -q    # no tests collected
```

Implemented and usable:

- `core/`: evidence, diagnostics, ids, limits, models, config, data accessors.
- `discovery/`: path guard, repository identity, walking/classification/loading.
- `parsers/`: marked YAML, GHA workflow/composite/expressions/permissions/triggers/
  uses/literals, Terraform JSON, Terraform HCL, IAM policy documents.
- `aws/`: glob matcher/intersection, condition evaluation, policy evaluation,
  trust evaluation, sink action catalogs.
- `oidc/`: subject candidates, breadth classification, trust solver.
- `resolvers/permissions.py`: effective permissions including reusable callers.

Not yet implemented:

- `resolvers/roles.py`, `resolvers/composite.py`, reusable-workflow resolution.
- `graph/store.py`, `graph/builder.py`.
- `analysis/` (selectors, reach, partition/closure, rotation, rank, findings).
- `report/` (console, JSON, SARIF, HTML, schema generator, assets).
- `cli/` (scan, rank, explain, export, schema, version).
- Tests, fixture READMEs, fx15 generator, goldens, security suite, performance suite.
- Packaging docs, ADRs, rule docs, schemas, lock files, CI, release evidence.

Contract corrections applied before this plan:

- `sink_node_id` maps sink types to specification prefixes `aws:secret:` and
  `aws:ssm:`.
- `Partition` carries only R/E/Z; `ScenarioReport` carries `potential`,
  `potential_nodes`, `unresolved_inputs` and `truncated` at scenario level, matching
  specification 13.2.
- `ProviderFact` and `ExternalTargetFact` are typed core models.
- `RoleFact` records unresolved trust and unresolved policy bodies so they can become
  UNKNOWN potential paths instead of false denies.
- `Finding.path_edges` exists so SARIF code flows can use real edges.
- Assumptions `A-TRUST-UNMODELLED` and `A-POLICY-UNMODELLED` exist.

Known deliberate deviations to document, not hide:

- `oidc/breadth.format_of_pattern` and solver breadth are heuristic interpretations
  of specification 10.4; test matrix fixes their meaning.
- Format drift (`NHB-OIDC-005`) is emitted for org/repo wildcard patterns, matching
  the specification 14.4 reference output (fx07 flags `repo:acme/*`, not the exact
  repository pattern of `deploy-prod`).

---

## 3. Target architecture

### 3.1 Layers and import rules

```
cli/            boundary: argv, config, exit codes, console/file writing
report/         boundary: pure rendering of Report/RankReport
pipeline.py     orchestration only: discovery -> parsers -> resolvers -> graph ->
                analysis -> Report; no rendering, no argv
analysis/       pure analysis over GraphData + facts
graph/          pure deterministic graph construction and traversal
resolvers/      pure transformations of parsed facts (no file I/O)
parsers/        pure functions of rel_path + text + limits (no I/O)
discovery/      boundary: the only module that reads repository files
core/           models, evidence, diagnostics, ids, limits, config, data
```

Allowed imports point downward only. `core` imports nothing from upper layers.
`analysis` may import `graph` and `core`. `report` imports `core` and `analysis`
result types only. `cli` imports `pipeline` and `report`. No parser imports a
resolver or graph module. No runtime module imports `typer`, `rich` or `networkx`
except their designated boundary modules (`cli`, `report/console.py`,
`analysis/rotation.py`).

### 3.2 Target package tree

```
src/nhi_blast/
  __init__.py                    version, SCHEMA_VERSION
  pipeline.py                    NEW: ScanOptions, LoadedRepository, ScanOutcome, run_scan, run_rank
  core/                          existing + ordering helpers if needed
  discovery/                     existing
  parsers/                       existing; extend gha/facts for static key secret refs
  resolvers/
    permissions.py               existing
    roles.py                     NEW: cloud facts (roles, sinks, providers, externals)
    composite.py                 NEW: local composite expansion + composite action facts
    workflows.py                 NEW: reusable-call graph and effective permissions
  oidc/                          existing solver
  graph/
    store.py                     NEW: GraphStore, integrity checks, traversal indexes
    builder.py                   NEW: rules R1-R14
  analysis/
    selectors.py                 NEW: selector parsing and start-set resolution
    reach.py                     NEW: best-path reach and potential reach
    partition.py                 NEW: R/E/Z + closure
    rotation.py                  NEW: containment/generations/verify
    rank.py                      NEW: all-mutable-actions ranking
    findings.py                  NEW: catalog → Finding objects
  report/
    __init__.py
    model_json.py                NEW: canonical report dict/JSON, schema
    console.py                   NEW: deterministic console/plain-text report
    json_report.py               NEW: JSON writer
    sarif.py                     NEW: SARIF 2.1.0 writer
    html.py                      NEW: single-file HTML writer
    assets/vendor/               NEW: pinned Cytoscape + dagre + MANIFEST.json
  cli/
    __init__.py
    app.py                       NEW: typer app and exception boundary
    commands.py                  NEW: scan/rank/explain/export/schema/version
scripts/
  gen_schema.py                  NEW: docs/schema/report.schema.json
  gen_fixtures.py                NEW: deterministic fx15 generator
  check_coverage.py              NEW: per-module coverage gates
```

### 3.3 End-to-end data flow

```
argv/config
  -> discovery.discover + InputLoader          (files, digests, diagnostics)
  -> parsers.parse_*                           (WorkflowFact, CompositeActionFact,
                                                TfModelFact, IamDocumentFact)
  -> resolvers.workflows                       (call sites, effective permissions)
  -> resolvers.composite                       (ExpandedJob / ExpandedStep)
  -> resolvers.roles                           (CloudFacts)
  -> graph.builder.GraphBuilder                (GraphData)
  -> analysis.partition/rotation/findings      (ScenarioReport, findings)
  -> Report
  -> report.console/json/sarif/html            (stdout/files)
  -> cli exit code
```

The pipeline must be reusable from tests without a subprocess. The CLI must contain
no parsing, graph or analysis logic beyond argument mapping.

### 3.4 Contracts to implement

Create these signatures exactly unless a later documented decision changes them.

#### pipeline.py

```python
@dataclass(frozen=True, slots=True)
class ScanOptions:
    root: Path
    tf_json: tuple[Path, ...] = ()
    tf_hcl: bool | None = None          # None = only when no TF JSON input found
    iam_json: tuple[Path, ...] = ()
    selectors: tuple[str, ...] = ()
    formats: tuple[str, ...] = ("console",)
    out_dir: Path = Path("nhi-blast-out")
    fail_on: Severity | None = None      # None = never
    max_depth: int = 3
    repo_slug: str | None = None
    default_branch: str | None = None
    aws_account: str | None = None
    aws_region: str | None = None
    config_path: Path | None = None
    strict: bool = False
    timestamp: bool = False
    no_color: bool = False

@dataclass(frozen=True, slots=True)
class ParsedRepository:
    root: Path
    guard: PathGuard
    identity: RepoIdentity
    config: Config
    limits: Limits
    files: tuple[InputFile, ...]
    digest: str
    workflows: tuple[WorkflowFact, ...]
    composites: dict[str, CompositeActionFact]
    tf_models: tuple[TfModelFact, ...]
    iam_documents: tuple[IamDocumentFact, ...]
    diagnostics: tuple[Diagnostic, ...]

@dataclass(frozen=True, slots=True)
class ScanOutcome:
    report: Report
    exit_code: int
    console_text: str
    written: tuple[Path, ...] = ()

def load_repository(options: ScanOptions) -> ParsedRepository: ...
def run_scan(options: ScanOptions) -> ScanOutcome: ...
def run_rank(options: ScanOptions) -> tuple[RankReport, int]: ...
```

`load_repository` is the only function that reads inputs. It parses every discovered
file, sorts all collections, builds `Inputs`, and aggregates diagnostics. It must not
raise for bad repository content; only missing/invalid CLI paths raise
`PathError`/`ConfigError` (mapped to exit 2).

#### resolvers/roles.py

```python
@dataclass(frozen=True, slots=True)
class CloudFacts:
    roles: tuple[RoleFact, ...]
    sinks: tuple[SinkFact, ...]
    providers: tuple[ProviderFact, ...]
    externals: tuple[ExternalTargetFact, ...]
    policy_context: PolicyContext
    diagnostics: tuple[Diagnostic, ...]

def resolve_cloud_facts(
    models: Sequence[TfModelFact],
    iam_documents: Sequence[IamDocumentFact],
    *,
    config: Config,
) -> CloudFacts: ...
```

#### resolvers/composite.py

```python
@dataclass(frozen=True, slots=True)
class ExpandedStep:
    step: StepFact
    composite_paths: tuple[str, ...] = ()   # local action files that contributed it
    depth: int = 0

@dataclass(frozen=True, slots=True)
class ExpandedJob:
    workflow: WorkflowFact
    job: JobFact
    refs: ExprRefs                          # caller refs merged with composite refs
    steps: tuple[ExpandedStep, ...]
    diagnostics: tuple[Diagnostic, ...]

def expand_jobs(
    workflows: Sequence[WorkflowFact],
    composites: Mapping[str, CompositeActionFact],
    *,
    limits: Limits,
) -> tuple[ExpandedJob, ...]: ...
```

#### resolvers/workflows.py

```python
@dataclass(frozen=True, slots=True)
class CallSite:
    caller_job: JobFact
    callee_path: str                       # rel path inside the repository
    line: int

@dataclass(frozen=True, slots=True)
class ReusableInfo:
    call_sites: tuple[CallSite, ...] = ()
    remote_uses: tuple[UsesRef, ...] = ()

def reusable_index(workflows: Sequence[WorkflowFact]) -> dict[str, ReusableInfo]: ...
def effective_job_permissions(
    workflow: WorkflowFact,
    job: JobFact,
    callers: Sequence[tuple[WorkflowFact, JobFact]],
) -> EffectivePerms: ...
```

For multiple local callers, use the per-scope **most permissive** `min(callee, caller)`
across call sites (a path can exist through the permissive caller). Record
`A-REUSABLE-CALLER` as an assumption and emit `D-GHA-REUSABLE-MULTI-CALLER` when
callers disagree. Remote reusable workflows are modelled on the caller job only and
emit `D-GHA-REMOTE-REUSABLE`; never fabricate callee steps.

#### graph/store.py

```python
class GraphIntegrityError(RuntimeError): ...

class GraphStore:
    def add_node(self, node: Node) -> None: ...
    def add_edge(self, edge: Edge) -> None: ...
    def node(self, node_id: str) -> Node: ...
    def edge(self, edge_id: str) -> Edge: ...
    def nodes_of_kind(self, kind: NodeKind) -> tuple[Node, ...]: ...
    def out_edges(self, node_id: str, *, kinds: frozenset[EdgeKind] | None = None) -> tuple[Edge, ...]: ...
    def in_edges(self, node_id: str, *, kinds: frozenset[EdgeKind] | None = None) -> tuple[Edge, ...]: ...
    def successors(self, node_id: str, kind: EdgeKind) -> tuple[str, ...]: ...
    def data(self) -> GraphData: ...       # validated, sorted, immutable
```

`add_node`/`add_edge` merge duplicate ids by unioning evidence and recomputing
confidence; a duplicate with a different kind/src/dst is an integrity error.
`data()` raises `GraphIntegrityError` if any node or edge has no evidence, if an edge
confidence disagrees with `weakest(evidence)`, or if an edge endpoint is missing.
It enforces `limits.max_graph_nodes`.

#### analysis

```python
@dataclass(frozen=True, slots=True)
class ScenarioAnalysis:
    selector: str
    selector_kind: str
    start_nodes: tuple[str, ...]
    partition: Partition
    reach: dict[str, PathInfo]
    potential_edges: tuple[str, ...]
    potential_nodes: tuple[str, ...]
    unresolved_inputs: tuple[str, ...]
    truncated: bool
    rotation_plan: RotationPlan
    findings: tuple[Finding, ...]
    notes: tuple[str, ...]

def parse_selector(text: str) -> Selector: ...
def resolve_starts(selector: Selector, graph: GraphData, *, jobs: Sequence[ExpandedJob]) -> tuple[str, ...]: ...
def reach(graph: GraphData, starts: Sequence[str]) -> dict[str, PathInfo]: ...
def analyze_scenario(graph, starts, *, selector_kind, max_depth, ...) -> ScenarioAnalysis: ...
def plan_rotation(graph, partition, *, selector_kind, start_nodes) -> RotationPlan: ...
def build_findings(...) -> tuple[Finding, ...]: ...
def rank_mutable_actions(parsed, graph, *, max_depth) -> RankReport: ...
```

`PathInfo` holds `node`, `edges`, `classes`, `weakest`, `hops`, `ids` and implements
the specification 12.2 ordering.

#### report

```python
def report_dict(report: Report) -> dict[str, Any]: ...
def report_json(report: Report) -> str: ...
def report_schema() -> dict[str, Any]: ...
def render_console(report: Report, *, color: bool) -> str: ...
def write_json(report: Report, path: Path) -> None: ...
def write_sarif(report: Report, path: Path) -> None: ...
def write_html(report: Report, path: Path) -> None: ...
```

All writers produce a trailing newline, use `sort_keys=True` for JSON and never
include a wall clock unless `report.generated_at` is set.

### 3.5 Cross-cutting utilities

- `report/_text.py`: `safe_text(value, limit=...)` removes C0/C1 control characters
  and ANSI escapes, normalises newlines, caps length with an ellipsis. Console,
  finding messages and HTML static text use it. JSON keeps exact strings but is
  escaped by the JSON encoder; HTML embeds JSON with `<`, `>`, `&` as unicode
  escapes.
- `core/ordering.py`: optional shared sort keys for nodes/edges/diagnostics; only add
  it when two modules would otherwise duplicate the same key.
- `analysis/cache.py`: optional memoisation for `(role_id, sink_id) -> DecisionResult`.
  Add only if the performance test shows a need; keep it deterministic.

---

## 4. Algorithms (canonical)

### 4.1 OIDC subject candidates (spec 10.2)

- Emit candidates per trigger and per audience used by `configure-aws-credentials`
  in that job (default `sts.amazonaws.com`).
- Precedence: environment > pull_request/pull_request_target > ref.
- Environment literal escapes `:` as `%3A`; expression environment gives
  `environment:*` with UNKNOWN class.
- `push`: branch filters each produce `ref:refs/heads/<filter>`; tag filters produce
  `ref:refs/tags/<filter>`; no filters produce both `*` forms. `**` becomes `*`.
- `pull_request`: `pull_request`. `pull_request_target`: base branch from filter or
  default branch. `workflow_dispatch`: heads and tags wildcards.
  `schedule`, `workflow_run`, `issue_comment`, `repository_dispatch`: default branch.
  `release`, `create`, `delete`: tags wildcard. Unknown trigger: `*`, ASSUMED.
- `workflow_call`: union of local caller candidates; no local caller gives
  `repo:<slug>:*` UNKNOWN.
- Every candidate carries claims `repository`, `ref` or `environment` where fixed.
  Add `workflow` (owner/repo/workflow path@ref) when the ref is known; never invent
  a ref. `job_workflow_ref` may only be set by a reusable caller.
- Both formats are emitted when the slug is known: classic `repo:O/R...` and
  immutable `repo:O@*/R@*...`. Symbolic repo `*/*` gives one UNKNOWN candidate.

### 4.2 Trust solving (spec 10.3-10.6)

- Relevant statement: Allow, `sts:AssumeRoleWithWebIdentity`, Federated principal
  ending `oidc-provider/<provider_host>`.
- Normalise provider-host prefixes in condition keys.
- Evaluate in CANDIDATE mode against the claim context. Missing claims are
  UNRESOLVED; negative operators are UNRESOLVED; dead keys fail the statement.
- `missing_audience` when no relevant matched statement constrains `aud`.
- `unconstrained` when matched statements constrain neither `sub` nor
  `job_workflow_ref`.
- Additional constraints: claims in `not_statically_fixable`; edge ASSUMED.
- Breadth: worst of matched `sub` patterns, or mapped `job_workflow_ref` patterns;
  UNCONSTRAINED when neither.
- Format drift: only when breadth is ANY_ORG/SAME_ORG, immutable candidates exist,
  classic matched, immutable did not.
- Matched formats, candidates and reasons sorted deterministically.
- `TrustMatch.confidence` = weakest of evaluation and candidate classes.

### 4.3 Cloud facts (spec 8.3)

Iterate resources in address order. Never read sensitive leaves (already stripped by
the parser). Policy string resolution order: literal known string; `references` to a
`data.aws_iam_policy_document` in prior state; otherwise UNKNOWN and diagnostic.

Role assembly:

1. `aws_iam_role` gives name, arn, max_session_duration (default 3600), trust policy,
   inline policy list, managed policy ARNs, boundary.
2. `aws_iam_role_policy` attaches inline policy to the role named by `role`.
3. `aws_iam_policy` gives a policy body keyed by ARN.
4. `aws_iam_role_policy_attachment` and `aws_iam_policy_attachment` attach policy
   ARNs to roles.
5. A boundary ARN with no body sets `boundary_supplied = False` and a diagnostic.
6. Unknown trust sets `trust_unresolved = True`; unknown attached bodies append to
   `unresolved_policy_refs`.
7. IAM JSON get-role output adds trust/inline statements when it can be associated
   by ARN/name. Unattached policy documents emit `D-IAM-UNBOUND` and do not guess.

Sinks:

- `aws_secretsmanager_secret`: name, ARN, KMS key, resource policy (from
  `aws_secretsmanager_secret_policy`). Kind/criticality from H-SECRET-NAME.
- `aws_secretsmanager_secret_rotation`: interval in days and `rotation_enabled`;
  associates by `secret_id` to the sink. Interval absent/disabled leaves the sink
  non-rotating.
- `aws_secretsmanager_secret_version`: never read `secret_string`; only mark managed.
- `aws_ssm_parameter`: name, type, key_id. Credential classification only for
  `SecureString` and credential-looking names/parameter types per data.
- `aws_db_instance`: external target `database:<identifier>`; master credential
  binding via `master_user_secret` / config `[bindings.credentials]`; if unmatched,
  diagnostic `D-TF-DB-UNBOUND`.
- `aws_iam_openid_connect_provider`: record only GitHub-hosted providers as
  `ProviderFact` for the GitHub solver; other providers are recorded but not used.

### 4.4 Composite expansion (spec 7.7)

- Input is pure parsed `CompositeActionFact` data; the resolver performs no I/O.
- Local `uses: ./path` resolves to `path/action.yml` or `path/action.yaml` inside the
  repository. Missing → `D-GHA-COMPOSITE-MISSING`.
- Only `runs.using: composite` is expanded; other runners are opaque.
- Expansion depth limit 5; cycles are detected by the chain of paths and stop with
  `D-GHA-COMPOSITE-CYCLE`. Depth hit → `D-GHA-COMPOSITE-DEPTH`.
- Composite refs (secrets, vars, env, head-ref, custom OIDC) merge into the calling
  job’s `refs`. Composite literal hits attach to the job credential evidence.
- A remote composite cannot be read: `D-GHA-REMOTE-OPAQUE`, `A-STEP-SHARE`; do not
  fabricate nested steps.
- Each expanded step preserves the original step line and records its composite
  chain; graph R2 creates a `RUNS_IN` edge for the outer local action and for every
  nested action use, all targeting the same job.

### 4.5 Graph rules R1-R14

Apply in this order, all deterministic.

| Rule | Required implementation |
| --- | --- |
| R1 | One REPOSITORY node; WORKFLOW per parsed workflow; JOB per effective job; CONTAINS repo→workflow and workflow→job. No step nodes. |
| R2 | ACTION_REF per use site (remote/docker/local), RUNS_IN to the job, DECLARED. Composite nested actions also RUNS_IN. One edge per use site, line in evidence. |
| R3 | Per job: GITHUB_TOKEN credential JOB_BOUND DECLARED + HOLDS. If id-token is definitely writable: OIDC request token JOB_BOUND DERIVED + HOLDS. If unknown: same node/edge UNKNOWN. |
| R4 | Named secrets: PERSISTENT credential, kind from H-SECRET-NAME, HOLDS DECLARED. `secrets_all`/inherit: one wildcard credential, HOLDS UNKNOWN, A-RUNNER-SECRETS, D-GHA-SECRETS-ALL. |
| R5 | LiteralHit: PERSISTENT credential, HOLDS DECLARED, label carries kind and location only. |
| R6 | OIDC_IDENTITY per audience when id-token is writable; CAN_MINT DERIVED. Unknown permission: identity + CAN_MINT UNKNOWN. No identity when id-token is false. |
| R7 | AWS_OIDC_PROVIDER and AWS_ROLE nodes from CloudFacts; provider node has URL/client IDs. |
| R8 | For every job identity × role, solver result → CAN_ASSUME SESSION_TTL; create STS session credential node SESSION_TTL with `ttl = max_session_duration or 3600`; edge `attrs["session_credential"]` names it. `intended` from literal/configured role binding. Unresolved trust → UNKNOWN CAN_ASSUME to every identity with A-TRUST-UNMODELLED. |
| R9 | For every role × sink: `can_read`. ALLOW→DERIVED, CONDITIONAL→ASSUMED, external wildcard→UNKNOWN. Missing attached policy body that could change a NOT_APPLICABLE result→CONDITIONAL/UNKNOWN with A-POLICY-UNMODELLED. |
| R10 | STORES sink→credential when the sink classifies as credential-bearing. Lifetime PERSISTENT, or PERSISTENT_ROTATING with interval days. Non-credential sinks remain SINK nodes with no STORES edge. |
| R11 | Static AWS keys used by configure-aws-credentials: AUTHENTICATES_AS from the static-key credential to `ext:aws-identity-unbound`, unless config binds it. Finding NHB-CRED-001. |
| R12 | Database master credential → EXTERNAL_TARGET and AUTHENTICATES_AS; binding by `master_user_secret` or config. |
| R13 | For every role × sink: `can_modify` → CAN_MODIFY edge, DERIVED (UNKNOWN on external wildcard). Used by rotation and NHB-ROT-002, never by authority reach. |
| R14 | `attrs["intended"] = True` on the CAN_ASSUME edge for the role named by literal/configured role-to-assume. |

Node/edge ids use `core/ids.py` with specification 5.5 prefixes. Every attr value
must be JSON-serialisable. Every node/edge gets evidence; edges get
`confidence=weakest(*evidence)`.

### 4.6 Reach, potential and R/E/Z

- Authority edge kinds: RUNS_IN, HOLDS, CAN_MINT, CAN_ASSUME, CAN_READ_VALUE,
  STORES, AUTHENTICATES_AS. CONTAINS is structural; CAN_MODIFY is not authority.
- Reach from sorted starts over non-UNKNOWN authority edges. Keep the best path per
  node using `(strongest weakest class, fewest hops, lexicographically smallest edge
  id list)`. Re-enqueue when a better path is found.
- Obtained credential: last edge of the best path is HOLDS or STORES, or it is the
  session credential attached to a traversed CAN_ASSUME edge.
- R: obtained lifetime JOB_BOUND. E: obtained SESSION_TTL (session credential).
  Z0: obtained PERSISTENT/PERSISTENT_ROTATING.
- Closure: for each Z credential, follow AUTHENTICATES_AS to a principal, then
  non-UNKNOWN CAN_READ_VALUE or CAN_MODIFY to a sink, then STORES to a credential.
  Add persistent credentials at depth+1 up to `max_depth`; sort frontier; if the
  frontier is non-empty at the limit, `truncated=True`.
- Z output sorted by `(depth, -criticality, credential id)`. R sorted by id. E sorted
  by credential id.
- Potential: BFS including UNKNOWN authority edges; nodes whose best path is UNKNOWN
  and that are not in authority reach are potential nodes; record the UNKNOWN edge
  ids used. Never include them in R/E/Z.
- `unresolved_inputs`: unique diagnostic codes/messages that blocked potential
  paths, sorted.

### 4.7 Rotation planner (spec 12.5)

- Nodes are Z credentials plus principals they unlock.
- Directed edge `p → c` when p (or a principal p authenticates as) can read or
  modify a sink that STORES c; p is rotated before c. Ignore self edges.
- Condense strongly connected components (networkx `condensation` is acceptable).
  Multi-member components are batches: freeze principals, rotate all, re-enable.
- Iterate topological generations in deterministic order. Sort components by
  descending max criticality, then minimum member id. Sort members by descending
  criticality, then id.
- `depends_on` contains the member ids of predecessor components.
- Containment (phase 0) by selector kind:
  - action/action-any/all-mutable-actions: pin/remove, disable affected workflow,
    review run logs.
  - secret: rotate immediately; it is in Z.
  - role: revoke sessions and tighten trust.
  - repo-write: review pushes/branch rules, remove the actor.
  - fork-pr: disable untrusted-checkout workflows, remove credentials.
  - job/workflow: disable it, revoke sessions, rotate Z.
- Verification (phase 2): CloudTrail searches for AssumeRoleWithWebIdentity on E
  roles and GetSecretValue/GetParameter on Z sinks; ASSUMED, VERIFY, evidence from
  the scenario.

### 4.8 Findings

Use `data/rules.yaml` for title/description/tags/precision/doc. Build findings only
from graph facts and scenario results, never from untracked booleans. Finding id uses
`finding_id(rule, nodes, primary evidence)`. Deduplicate by id. Apply dynamic
severity adjustments exactly:

- NHB-OIDC-001: UNCONSTRAINED match → CRITICAL.
- NHB-OIDC-002: ANY_ORG → CRITICAL; SAME_ORG → HIGH, +1 level if the role reads a
  persistent sink or the matching job has untrusted checkout (cap CRITICAL).
- NHB-OIDC-003: REPO_ANY_CONTEXT.
- NHB-OIDC-004: missing audience.
- NHB-OIDC-005: format drift.
- NHB-OIDC-006: dead condition key.
- NHB-OIDC-007: ENVIRONMENT breadth only.
- NHB-GHA-001: mutable third-party action in a job with secrets/OIDC; HIGH when the
  scenario Z is non-empty.
- NHB-GHA-002: untrusted checkout under a privileged trigger; CRITICAL when a role
  is reachable.
- NHB-GHA-003: self-hosted runner.
- NHB-GHA-004: secrets inherit/whole context.
- NHB-GHA-005: literal credential.
- NHB-CRED-001: static AWS keys where OIDC is available.
- NHB-SURV-001: Z non-empty; severity from the highest Z criticality.
- NHB-ROT-001: reachable sink without rotation.
- NHB-ROT-002: CAN_MODIFY sink reachable from a mutable entrypoint.

Every finding has evidence, assumptions and a deterministic path when a scenario is
available. Apply `[ignore]` rules and paths after generation; paths match finding
evidence files/primary path. Never silently drop a finding without a diagnostic when
`--strict` is set.

### 4.9 Reports

- **JSON:** Pydantic dump with aliases, `exclude_none=True`, sorted keys, compact
  separators, trailing newline. Scenario shape follows specification 13.2.
- **Console:** four stages plus rotation; every fact line ends with evidence class and
  file:line when available; colour only on a TTY and when not disabled; hostile
  control characters neutralised.
- **SARIF:** one run, tool driver metadata, rules from the catalog, sorted results by
  severity then id, level mapping, security-severity strings, partial fingerprints,
  code flows from `path_edges`, truncate at 5000 with a tool notification. Validate
  against the vendored SARIF schema in tests.
- **HTML:** single file; embedded report JSON with `<`, `>`, `&` replaced by
  `\u003c`, `\u003e`, `\u0026`; inline vendored Cytoscape/dagre with SHA-256 hashes in
  a MANIFEST; CSP `default-src 'none'; style-src 'unsafe-inline'; script-src` with
  each inline script hash; all text via `textContent`/`setAttribute`; no `innerHTML`,
  no external URLs; sections per specification 13.4; under 3 MB for fx07.

### 4.10 Exit codes

Priority `4 > 2 > 3 > 1 > 0`:

- 0 success.
- 1 any finding at or above `--fail-on` (threshold none means no failure).
- 2 usage/config/path/selector error.
- 3 `--strict` and at least one error-level diagnostic (partial results).
- 4 unexpected internal error; print a short message and no traceback unless an
  explicit debug flag is added later.

---

## 5. Milestones

Each milestone ends with the listed tests and commands. Do not start the next
milestone until they pass or a blocker is recorded.

### M1 — OIDC and trust conformance (complete: see implementation-status.md)

Files:

- `tests/conftest.py`
- `tests/test_glob.py`
- `tests/test_conditions.py`
- `tests/test_trust.py`
- `tests/test_subjects.py`
- `tests/test_solver.py`

Tests:

1. `glob_match`/`glob_intersects` example table and Hypothesis property vs a brute
   force enumerator on alphabet `{a,b}` with patterns containing `*` and `?`.
2. Conditions: exact/like/bool/null, IfExists, qualifiers, dead key fails closed,
   candidate negative unresolved, policy variable unresolved.
3. Trust: exact repo, org wildcard, environment, dead key, missing aud, unconstrained,
   non-GitHub principal, negative operator, additional constraint, immutable format,
   format drift only for wildcard breadth.
4. Subjects: trigger matrix, environment precedence, expression environment, tags,
   branches, `**`→`*`, symbolic repo, audiences, workflow claim, workflow_call caller
   union, unresolved caller.
5. Solver: fx02/fx03-style roles with candidates; assert breadth, formats, drift,
   confidence, missing audience, dead keys, deterministic ordering.

Acceptance:

```sh
pytest -q tests/test_glob.py tests/test_conditions.py tests/test_trust.py \
  tests/test_subjects.py tests/test_solver.py
ruff check src tests && ruff format --check src tests && mypy src
```

### M2 — Resolvers

Files:

- `resolvers/roles.py`
- `resolvers/composite.py`
- `resolvers/workflows.py`
- `parsers/gha/facts.py` + `parsers/gha/workflow.py` (static-key secret refs)
- `tests/test_roles.py`, `tests/test_composite.py`, `tests/test_workflows.py`

Steps:

1. Extend `AwsAuthUse` with `static_secret_refs: tuple[str, ...]`; populate from
   `with` values containing `secrets.X` or `secrets['X']` for the three static key
   inputs. Never store values.
2. Implement `resolve_cloud_facts` per 4.3. Test against fx02, fx03, fx07, fx10.
3. Implement composite expansion per 4.4. Test fx06 including cycle and depth.
4. Implement reusable indexing/effective permissions per 3.4. Test fx13 and fx06.
5. Ensure every resolver result is sorted and diagnostics are deterministic.

Acceptance: fx02/fx03/fx07/fx10 role names, trust patterns, sink kinds and rotation
intervals match the fixture expectations; fx06 cycle terminates under all limits;
no sensitive sentinel appears in any fact.

### M3 — Graph

Files:

- `graph/store.py`
- `graph/builder.py`
- `tests/test_graph_store.py`
- `tests/test_graph_builder.py`

Steps:

1. Implement the store with duplicate merging, indexes, integrity validation and
   deterministic serialisation.
2. Implement R1-R14 in order. Every node/edge has evidence. Add tests for every rule.
3. Invariant tests: no CAN_MINT in fx09; UNKNOWN edges absent from R/E/Z; weakest
   evidence equals confidence; job scope (RUNS_IN/HOLDS target jobs only); all ids
   match prefixes; graph sorted.
4. Budget: reject when `max_graph_nodes` is reached and record `truncated`.

Acceptance: `pytest -q tests/test_graph_store.py tests/test_graph_builder.py`; graph
on fx07 includes the expected role, session, sink, secret and literal nodes.

### M4 — Analysis

Files:

- `analysis/selectors.py`, `reach.py`, `partition.py`, `closure.py` (merge closure
  into partition if smaller), `rotation.py`, `rank.py`, `findings.py`, `cache.py`
  (only if needed)
- `tests/test_selectors.py`, `tests/test_reach.py`, `tests/test_partition.py`,
  `tests/test_rotation.py`, `tests/test_rank.py`, `tests/test_findings.py`

Steps:

1. Selector parser and start resolution, including `repo-write` synthetic ASSUMED
   CAN_ASSUME edges and `fork-pr` untrusted jobs.
2. Reach with best-path ordering and potential reach; cooperative time/size limits.
3. R/E/Z and closure; verify fx07 membership and fx09 empty role reach.
4. Rotation on fx11 cycle: SCC batch, dependencies, deterministic generations.
5. Rank on fx07-style mutable actions.
6. Findings catalog and severity adjustments; `[ignore]` filtering.

Acceptance: fx07 reproduces the specification 14.4 R/E/Z membership and rotation
spirit; fx11 produces one batch; two runs are byte-identical.

### M5 — Reporters

Files:

- `report/model_json.py`, `console.py`, `json_report.py`, `sarif.py`, `html.py`,
  `_text.py`, `assets/vendor/*`, `assets/MANIFEST.json`
- `docs/schema/report.schema.json`, `docs/schema/sarif-2.1.0.schema.json`
- `scripts/gen_schema.py`
- `tests/test_json_report.py`, `tests/test_sarif.py`, `tests/test_html.py`,
  `tests/test_console.py`, `tests/test_report_security.py`

Steps:

1. Canonical dict/JSON and schema generation. Validate every report.
2. Console renderer with evidence classes, no colour when redirected, ANSI/control
   sanitisation.
3. SARIF with rules, results, fingerprints, code flows, truncation.
4. HTML with vendored assets, CSP hashes, escaped JSON, textContent-only DOM,
   no network.
5. Security tests: hostile strings in every field, literal credential sentinel absent
   from all four outputs, HTML no `<img onerror>` execution surface, CSP hash matches
   every inline script.

Acceptance: JSON and SARIF schema validation; HTML size target; secret-leak tests
green.

### M6 — CLI and pipeline

Files:

- `pipeline.py`
- `cli/app.py`, `cli/commands.py`
- `tests/test_cli.py`, `tests/test_pipeline.py`

Steps:

1. Implement `load_repository`, `run_scan`, `run_rank` with diagnostics and identity
   precedence.
2. Implement commands and options from specification 14.2. `scan` writes only
   requested formats; console goes to stdout; files to `--out`.
3. Exit-code mapping and exception boundary.
4. `explain` reads a saved report, resolves finding/node/edge id and prints evidence.
5. `export` writes dot/json graph.
6. `schema` prints the report schema; `version --data` shows data versions and ages.
7. End-to-end tests on fx07 and fx03, including `--fail-on`, `--strict`, bad config,
   path outside root, invalid selector and unsupported format.

Acceptance: installed console script works; all exit codes tested.

### M7 — Full test, security and performance suite

Files:

- Fixture READMEs for fx01-fx14 and `tests/fixtures/README.md`
- `scripts/gen_fixtures.py` and checked-in fx15 smoke variant
- `tests/test_fixtures.py`, `tests/test_security.py`, `tests/test_determinism.py`,
  `tests/test_performance.py`, `tests/test_golden.py`, golden files under
  `tests/golden/`
- `docs/testing.md`

Steps:

1. Document each fixture: scenario, features, expected diagnostics, expected graph
   facts, expected R/E/Z, specification sections. Do not guess; derive from the
   fixture and the spec.
2. Generate fx15 deterministically (200 workflows, 2000 Terraform resources) and
   keep a small smoke variant checked in.
3. Golden outputs for fx07 (reviewed against 14.4), compact and deterministic.
4. Adversarial tests: duplicate keys, billion laughs, deep nesting, oversize YAML/TF,
   path traversal and symlink escape, malformed JSON/HCL, HTML injection, control
   characters, secret leakage across console/JSON/SARIF/HTML.
5. Property tests for glob, selectors, identifiers and condition truth tables.
6. Performance test with a documented machine, CPU/RAM/OS/Python/commit; mark
   `slow`; target 200 workflows + 2000 resources under 5 s and rank 300 actions
   under 60 s.
7. Determinism: two scans byte-identical; no network calls (socket guard).

### M8 — Packaging, docs, CI and release evidence

Files:

- README update with only exercised commands.
- `docs/architecture.md`, `docs/cli.md`, `docs/config.md`, `docs/assumptions.md`,
  `docs/known-limitations.md`, `docs/implementation-status.md`,
  `docs/requirements-traceability.md`, `docs/production-readiness.md`,
  `docs/research/sources.md` plus topic notes, `docs/rules/NHB-*.md` (16),
  `docs/decisions/ADR-*.md`, `docs/schema/*`, `docs/opengraph.md` only if implemented.
- `SECURITY.md`, `CONTRIBUTING.md`, `NOTICE`, `CHANGELOG.md`.
- `scripts/fetch_assets.py` with pinned asset URLs and hashes (if used), lock files
  with hashes, `.github/workflows/ci.yml` with full-SHA pinned actions.
- Reproducible build procedure.

Release gates (record actual results, never invent):

- pytest full suite green; coverage thresholds met.
- ruff/format/mypy clean.
- JSON/SARIF schema validation green.
- determinism and secret-leak tests green.
- clean install and console script green in a fresh venv.
- performance measured on a documented machine.
- all exit codes tested.
- installation, wheel/sdist hashes and reproducibility result recorded.
- docs/traceability/status/readiness complete.

---

## 6. Test matrix (minimum)

| Module | Unit | Property | Conformance | Security | E2E |
| --- | --- | --- | --- | --- | --- |
| glob/conditions | yes | yes | trust matrix | long inputs | — |
| parsers | yes | — | fx01-fx14 | hostile YAML/JSON/HCL | scan |
| roles/composite | yes | — | fx02/03/06/07/10 | sensitive sentinels | scan |
| graph | yes | invariants | fx07/fx09 | hostile labels | scan |
| reach/partition | yes | — | fx07 R/E/Z | UNKNOWN isolation | scan |
| rotation/rank | yes | — | fx11/fx07 | — | rank |
| reports | yes | — | schema | injection/leak/CSP | scan |
| CLI | yes | — | exit codes | path traversal | console script |

---

## 7. Decisions to record (ADRs)

1. Specification sections 15-19 are absent; milestone and VERIFY handling is derived.
2. Path/config/selector errors map to exit 2.
3. Only files inside the scan root are read; `--tf-json/--iam-json/--config` outside
   the root are usage errors.
4. Unknown config keys are rejected.
5. Data-file staleness appears only with `--timestamp`; ages always in
   `version --data`.
6. `permission_scopes.yaml` is an additional data file because GitHub permission
   scopes are platform facts.
7. Unavailable managed/inline policy bodies never become confident allows or denies;
   they become UNKNOWN potential access with A-POLICY-UNMODELLED.
8. Unresolvable trust policies produce UNKNOWN potential CAN_ASSUME paths with
   A-TRUST-UNMODELLED.
9. Multiple local callers of a reusable workflow use the permissive per-scope
   `min(callee, caller)` across call sites; this avoids false negatives and is
   labelled A-REUSABLE-CALLER.
10. Remote reusable workflows are modelled on the caller job and never fabricated.
11. Format drift is reported only for org/repo wildcard breadth.
12. Exit-code priority 4 > 2 > 3 > 1 > 0.
13. `scan` default format is console; files are written only for requested formats.
14. HTML vendors pinned Cytoscape/dagre with hashes and a restrictive CSP.
15. Open: Terraform `.tf.json` configuration handling; recommend a minimal JSON
    configuration reader in the HCL adapter, otherwise a recorded limitation.
16. Open: managed-policy association for `--iam-json` without a role target;
    recommend `D-IAM-UNBOUND` and no guessing.

---

## 8. Master checklist

Use this as the live work queue. Tick only after the command has actually run.

### Foundation already green

- [x] `ruff check src`
- [x] `ruff format --check src`
- [x] `mypy src`
- [x] OIDC solver module written
- [x] Contract corrections applied

### M1

- [x] `tests/conftest.py`
- [x] glob + condition tests
- [x] trust conformance tests
- [x] subject candidate tests
- [x] solver tests
- [x] M1 commands green

### M2

- [x] static-key secret refs in parser
- [x] `resolvers/roles.py`
- [x] `resolvers/composite.py`
- [x] `resolvers/workflows.py`
- [x] resolver fixture tests
- [x] M2 commands green

### M3

- [x] `graph/store.py`
- [x] `graph/builder.py`
- [x] R1-R14 tests and invariants
- [x] graph budget
- [x] M3 commands green

Result (2026-10-25): 21 M3 tests and 157 total tests passed; lint, format and mypy
green. R5 literal retention is verified with a synthetic workflow because the
spec-derived fx07 fixture contains no literal credential (recorded in
`implementation-status.md`).

### M4

- [ ] selectors
- [ ] reach + potential
- [ ] partition + closure
- [ ] rotation
- [ ] rank
- [ ] findings
- [ ] fx07/fx11 analysis tests
- [ ] M4 commands green

### M5

- [ ] JSON + schema
- [ ] console
- [ ] SARIF
- [ ] HTML + assets + CSP
- [ ] security tests
- [ ] M5 commands green

### M6

- [ ] pipeline
- [ ] CLI commands/options
- [ ] exit codes
- [ ] explain/export/schema/version
- [ ] E2E tests
- [ ] M6 commands green

### M7

- [ ] fixture READMEs
- [ ] fx15 generator
- [ ] goldens
- [ ] adversarial suite
- [ ] determinism suite
- [ ] coverage gates
- [ ] performance measurement
- [ ] M7 commands green

### M8

- [ ] all docs and ADRs
- [ ] rule docs (16)
- [ ] schemas checked in
- [ ] lock files
- [ ] CI pinned to SHAs
- [ ] reproducible build evidence
- [ ] release-gate table completed honestly

---

## 9. First implementation slice after this plan

1. Add `tests/conftest.py` and M1 tests.
2. Run them; fix solver/subject/trust defects found.
3. Only then extend the parser for static-key secret refs and begin M2.
4. Keep `ruff`, format and mypy green after every file.
