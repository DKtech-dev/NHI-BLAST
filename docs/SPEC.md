<!--
Source: "NHI-Blast Complete Architecture and Build Specification (v2.0)".
Supplied as a 50-page PDF (25 October 2026). Extracted with pypdf and lightly
normalised: page markers and repeated page footers removed, runs of blank lines
collapsed. Wording, identifiers, numbers and equations are preserved.

The PDF's linearised extraction of complex tables puts cell text on separate
lines; where a table's meaning depends on column alignment, consult the original
PDF committed under docs/spec-source/.

SOURCE PDF SHA-256: e048497fc0720203cd6565a6031b9b4ffba3d8b1216f2c0383108e6295826df8

NORMATIVE STATUS: this file is the project's primary requirements source.

COMPLETENESS NOTE (do not delete): the supplied PDF ends at section 14.4. The PDF
itself references section 15 (testing, conformance, benchmark), section 16
(milestones), section 17 (agent rules), section 18 (VERIFY list) and section 19
(backlog/release). Those sections are NOT present in the supplied 50-page file.
The repository therefore records a derived milestone and release plan in
docs/implementation-status.md and docs/requirements-traceability.md, explicitly
marked as derived rather than quoted from the specification.
-->

# NHI-Blast: Complete Architecture and Build Specification

**Version 2.0 | 25 October 2026**

NHI-Blast: Complete Architecture and Build
Specification
Version 2.0 | 25 October 2026 | Supersedes the NHI-Blast Flagship Blueprint (20 Oct
2026) | Written for AI coding agents and human implementers
0. How to use this document
1. Save this file in the repo as docs/SPEC.md . Copy section 17 into AGENTS.md  (it also
works as .cursorrules , CLAUDE.md  or Copilot instructions).
2. Build milestone by milestone (section 16). Give the agent one milestone prompt at a
time. Do not start milestone N+1 until the acceptance tests of milestone N pass.
3. MUST, SHOULD and MAY follow RFC 2119. Identifiers in code  font are normative
names.
4. Anything marked VERIFY (collected in section 18) could not be confirmed from a
primary source during research. Code MUST treat such a fact as ASSUMED  evidence
and list it in the report assumptions. It MUST NOT present it as a configuration fact.
5. When this spec is silent, choose the behaviour that is deterministic, offline and labels
uncertainty as UNKNOWN  rather than guessing.
1. Research findings that change the blueprint
Research was done on 25 Oct 2026 using primary sources where possible (Appendix A).
Each row is an instruction to the implementer.
Part Sections Content
A 1-5 Research corrections, product definition, evidence
model, formal model, architecture
B 6-11 Inputs, GitHub Actions parser, Terraform ingestion,
AWS policy engine, OIDC solver, graph rules
C 12-19 Analysis engine, findings and reports, CLI, testing,
milestones, agent rules, VERIFY list, release
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

# Blueprint claim What research found Consequence in this
spec
1 NYT breach in Jan 2025
via token on a self-hosted
runner
NYT said a credential for a
cloud code platform (GitHub)
was exposed in January 2024;
the data surfaced on 4chan in
June 2024. No public mention
of a self-hosted runner.
Cite only as ‘exposed
long-lived token, Jan
2024’. Drop the
runner claim.
2 ‘No open-source tool can
answer this’, ‘complete
vacuum’
SpecterOps GitHound /
OpenHound and the
BloodHound OpenGraph
GitHub extension already
model repo, branch and
environment to AWS role or
Azure federated credential
( GH_CanAssumeIdentity ),
pwn-request paths
( GH_CanPwnRequest ) and
secrets ( GH_HasSecret ), but
from live GitHub API data.
Cartography (CNCF, Neo4j)
ingests live AWS and GitHub
data. zizmor, poutine and
Scorecard lint workflows.
subvectors publishes OIDC
subject test vectors. Prowler
added a GitHub provider in
mid 2026 (per the subvectors
docs).
Positioning rewritten
in 2.1. Offline repo-file
analysis, revocation-
survival and rotation
ordering are
hypotheses to
benchmark (15.4).
Optional BloodHound
OpenGraph export is
on the roadmap for
interop.
3 ‘Mathematically proves’
exploitability
Matching trust-policy patterns
against candidate subjects is
deterministic, but
environment protection,
branch protection, fork
settings, SCPs and org policies
are not in repo files.
Language rules in 2.2.
All results are
‘potential’.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

# Blueprint claim What research found Consequence in this
spec
4 ‘2026 subvectors
conformance vectors’
Real project: subvectors  on
PyPI (Dashtid/subvectors).
Cited vectors for ‘does subject
S satisfy trust condition C, and
is C safe’. Vector data is CC0,
code is Apache-2.0, suites
cover GitHub to AWS, Azure,
GCP and others.
Used as a dev-time
conformance oracle
(15.3). Not a runtime
dependency.
5 sub  is always
repo:org/repo:...
Repos created after 2026-07-
15, plus renames and transfers
after that date, get
repo:OWNER@OWNER-
ID/REPO@REPO-ID:... . Older
repos keep the classic form
unless opted in. Not on GHES.
Colons inside metadata are
escaped as %3A . A classic
pattern such as repo:acme/*
does not match an immutable
subject because @  follows the
owner name.
Solver evaluates both
formats (section 10).
Repo age is unknown
from files, so both
variants are emitted
and labelled.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

# Blueprint claim What research found Consequence in this
spec
6 Only aud  and sub
matter for AWS
AWS documents ten GitHub
claim keys usable in trust
policies besides aud and sub:
actor, actor_id,
job_workflow_ref, repository,
repository_id,
repository_owner_id,
workflow, ref, environment,
enterprise_id (none available
in session). Not usable:
repository_owner,
event_name, head_ref,
base_ref, workflow_ref,
runner_environment. AWS
release notes of 30 Sep 2026
say IAM accepts either sub  or
job_workflow_ref  as the
required control. GitHub's
AWS guide still says custom
claims are unavailable, so the
docs disagree.
Supported-key list is a
data file with a
retrieval date (9.5).
Solver warns on dead
conditions.
7 Subject assembly environment  beats
pull_request , which beats
ref . Environments named
Production:V1  and
Production%3AV1  mint the
same sub (observed by
subvectors), and workflow
editors can create
environments. Environment-
pinned policies are only as
strong as environment
protection, which files cannot
show.
Rules in 10.2.
Assumption A-ENV-
UNPROTECTED.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

# Blueprint claim What research found Consequence in this
spec
8 tj-actions ‘runner memory
of workflow release.yml’
CVE-2025-30066 (GHSA-
mrrh-fwg8-r2c3): tags
repointed to one malicious
commit on 14-15 Mar 2025. A
script read Runner.Worker
memory and printed secrets
to logs. More than 23,000
repos affected. Secrets are
materialised per job.
Blast radius is per job,
never per workflow
(section 7, fixture
fx09).
9 Two sets, R(u) and Z(u) A third class is missing: an
AWS STS session already
minted from the OIDC token
keeps working until its TTL
even after the GitHub-side
entrypoint is stopped.
Three-way partition R
/ E / Z (4.4).
10 A compromised step can
only use the role it is
configured for
A step in a job with id-token:
write  can request a token
itself and call STS for any role
whose trust policy accepts
that token.
CAN_ASSUME edges
go to every matching
role. The configured
role is only flagged
intended  (10.6).
11 Drift example UNC6395 used stolen Drift
OAuth tokens on 8-18 Aug
2025. Salesloft and Salesforce
revoked all tokens on 20 Aug
2025. Attackers searched
exported Salesforce data for
AWS keys (AKIA), Snowflake
tokens and passwords. This is
SaaS data, not repo files.
Motivating pattern
only (‘a reachable
store contains static
credentials’). Not
modelled.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

2. Product definition
2.1 Summary and positioning
NHI-Blast is an offline, local-first command-line tool. It reads repository files (GitHub
Actions workflows, Terraform plan or state JSON, IAM policy JSON) and answers three
incident questions:
# Blueprint claim What research found Consequence in this
spec
12 python-hcl2  as primary
Terraform parser
It does not resolve variables,
modules, for_each  or data
sources. terraform show -
json  returns resolved values
with unknowns flagged in
after_unknown , but values
computed at apply time stay
unknown.
Primary input is plan
or state JSON. HCL is
a best-effort fallback.
The tool never runs
terraform (section 8).
13 PyYAML Plain loaders drop line
numbers. YAML 1.1 parses the
key on  as boolean True.
Use the compose API
with marks and
handle the True key
(7.1).
14 Scope: GitLab, MCP, K8s,
Cloudflare, GCP, Azure
Contradicts the narrow MVP
boundary.
MVP fixed in 2.3. The
rest is backlog (19.4).
15 Sample output slack_webhook_url  was
listed as surviving but the
traversal shown never reached
it.
New sample in 14.4,
derived from the
algorithm.
16 SARIF GitHub code scanning uses a
SARIF 2.1.0 subset. At most
5,000 results are kept per
upload (highest severity first),
10 MB gzip, 20 runs per file.
partialFingerprints
prevent duplicate alerts.
Reporter constraints
in 13.3.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

1. From a hypothetical compromised entrypoint (an unpinned action, a job, a leaked
secret, a user with write access), which cloud roles, stores and credentials are
potentially reachable?
2. If that entrypoint is revoked now, which credentials are revoked, which expire on their
own, and which survive?
3. In what order should surviving credentials be rotated so a surviving credential cannot
re-read a freshly rotated one?
Positioning (honest version): live-collection graph tools (GitHound, Cartography) tell you
what exists. Workflow linters (zizmor, poutine) tell you what is unsafe in a file. NHI-Blast is
a hypothesis that a deterministic, offline, evidence-labelled analysis of repo files, centred
on revocation-survival and rotation order, is useful to responders and reviewers. The
benchmark in 15.4 decides whether that hypothesis holds.
2.2 Claim hygiene (MUST)
Never write proves, guaranteed, exploitable or takeover as facts. Write ‘potentially
reachable’, ‘accepted by the trust policy as written’, ‘survives revocation if the path
was exercised’.
Every finding and edge shows its evidence class (DECLARED, DERIVED, ASSUMED,
UNKNOWN) and file:line.
Every report opens with a Scope and Limits box: what was analysed, and what was not
(live cloud state, SCPs, environment protection, branch protection, runtime logs).
Severity names are labels, not verdicts. Tone is neutral.
README and CLI output make no novelty claims.
2.3 MVP scope
In: GitHub Actions workflows and local composite actions; AWS IAM roles, the GitHub
OIDC provider, Secrets Manager, SSM Parameter Store, RDS-managed master secrets
(optional); Terraform plan or state JSON (primary) and HCL (fallback); outputs:
console, JSON, SARIF, single-file HTML.
Out (backlog, 19.4): role chaining, IAM users and access keys, S3 and KMS key-policy
modelling, CloudFormation, GitLab CI, Azure, GCP, Kubernetes, MCP configs,
Cloudflare, live API collection, GitHub settings ingestion.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

2.4 User stories and acceptance
2.5 Threat model of the tool itself
The scanned repository is untrusted input. Requirements:
Safe YAML only (no object construction). Limits on file size, node count, alias
expansion, depth, file count.
Never execute terraform, git, shell or any scanned content. No network access at
runtime.
Resolve every path inside the scan root. Do not follow symlinks that leave it.
Never print or store secret values. Literals found in files are shown as kind plus length.
HTML report builds DOM with textContent  only; embedded data is escaped; a CSP
forbids network access.
No regex with nested quantifiers on untrusted text. Use the linear glob matcher (9.2).
Output is byte-for-byte deterministic for equal inputs.
2.6 Non-goals
No exploitation, no live cloud calls, no secret reading, no claim of runtime compromise, no
replacement for secret scanners (use gitleaks or TruffleHog) or workflow linters (use
zizmor).
ID Story Acceptance
US1 Responder: an action may be
compromised. Show reach, R/E/Z and a
rotation plan.
On fixture fx07, scan --simulate-
compromise action:tj-
actions/changed-files@v45  prints R, E,
Z and a plan. Runtime under 5 s for 200
workflows and 2,000 Terraform
resources.
US2 Platform engineer: audit OIDC trust
policies.
On fx03 the run exits 1 with --fail-on
high  and names the policy line.
US3 Reviewer: see findings on a pull request. SARIF uploads to code scanning; alerts
land on workflow or Terraform lines.
US4 Hardening lead: which mutable action
matters most?
rank  lists every mutable third-party
action ordered by size of Z.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

3. Concepts and evidence model
3.1 Glossary
3.2 Evidence classes
Ordered strongest to weakest: DECLARED  > DERIVED  > ASSUMED  > UNKNOWN .
DECLARED: literally stated in a parsed file (for example permissions: id-token:
write  at line 14).
DERIVED: deterministic computation over DECLARED facts (effective permissions,
trust-policy match).
ASSUMED: depends on a registered platform assumption A-*  or heuristic H-*  (3.3).
UNKNOWN: could not be resolved. The path is shown as ‘potential’ and is never
counted in R, E or Z.
Path confidence is the weakest class among its edges. An edge's class is the weakest
class among its evidence.
Term Meaning
Entrypoint The hypothetical compromised thing the analysis
starts from.
Scenario One entrypoint selector plus options, run against
the graph.
Job context One job and the candidate OIDC subjects it could
mint.
Principal Something that can hold permissions: an OIDC
identity, an AWS role.
Credential A value that grants access: GitHub secret,
GITHUB_TOKEN, OIDC token, STS session,
password, API key.
Sink A store that can contain credentials: Secrets
Manager secret, SSM parameter.
Obtained The attacker could read the credential value (not
merely use access while it lasts).
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

3.3 Assumption and heuristic registry
Stored in data/assumptions.yaml , rendered in every report.
ID Statement VERIFY
A-STEP-SHARE All steps of a job, including third-party
actions, share the runner process
space and environment, so a
compromised action inherits what the
job holds.
Platform design;
supported by tj-actions
A-RUNNER-
SECRETS
Only secrets referenced by
expressions in the job are materialised
in the runner. secrets: inherit  or
toJSON(secrets)  exposes every
secret the repo can see (set unknown).
Yes
A-OIDC-ENV With id-token: write , any step can
request an OIDC token through the
runner URL and bearer env vars.
Documented
A-DEFAULT-NO-
IDTOKEN
With no permissions  block, id-token
is not writable.
Yes
A-FORK-NO-OIDC Fork pull_request  runs get neither
secrets nor OIDC tokens.
Yes
A-PRT-SUB pull_request_target  runs mint a sub
for the base-branch ref.
Yes, record a real token
A-DISPATCH-
ANYREF
A user with write access can run
workflow_dispatch  or push on any
branch or tag.
Low risk
A-ENV-
UNPROTECTED
Environment protection and branch
rules are unknown. Anyone who can
edit workflows can satisfy an
environment:  claim.
Needs GitHub settings
input
A-STS-TTL An AssumeRoleWithWebIdentity
session lasts at most the role
max_session_duration  (default 3600
s).
Documented
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

4. Formal model
4.1 Graph and models
The authority graph is a directed multigraph G = (V, E) . Policy documents are node
attributes, not nodes. Evaluating them produces edges.
class EvidenceClass(StrEnum):
    DECLARED = 'declared'
    DERIVED = 'derived'
    ASSUMED = 'assumed'
    UNKNOWN = 'unknown'
ID Statement VERIFY
A-NO-SCP SCPs, RCPs, session policies and
permission boundaries that were not
supplied are not modelled. Allow results
may over-approximate.
By design
A-SCOPE-INPUT Only resources present in the inputs
exist. Resource: *  may cover
resources outside them (reported
UNKNOWN_EXTERNAL ).
By design
A-DEFAULT-
BRANCH
Default branch is main  unless
configured.
Config
A-REPO-AGE Whether a repo mints classic or
immutable subjects is unknown from
files, so both are evaluated.
By design
H-SECRET-NAME Whether a secret or parameter holds a
credential, and of what kind, is inferred
from resource type and name patterns.
Heuristic
H-ROT-WINDOW A rotation resource means periodic
rotation. The next rotation time is
unknown, so survival is ‘up to N days’.
Heuristic
H-LITERAL A small regex set recognises literal
credentials in workflow values.
Heuristic
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

class Lifetime(StrEnum):
    JOB_BOUND = 'job_bound'                    # dies with the job or token
expiry
    SESSION_TTL = 'session_ttl'                # fixed TTL, not revocable
from the entrypoint side
    PERSISTENT = 'persistent'                  # valid until someone rotates
it
    PERSISTENT_ROTATING = 'persistent_rotating'  # rotates on a schedule
    NA = 'na'
class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    cls: EvidenceClass
    rule: str                  # 'GHA.perm.id-token', 'A-RUNNER-SECRETS', 'H-
SECRET-NAME'
    file: str | None = None    # repo-relative POSIX path or input label
    line: int | None = None
    end_line: int | None = None
    detail: str = ''           # human text. MUST NOT contain secret values
class Node(BaseModel):
    id: str
    kind: NodeKind
    label: str
    attrs: dict[str, Any] = {}
    evidence: tuple[Evidence, ...] = ()
class Edge(BaseModel):
    id: str
    kind: EdgeKind
    src: str
    dst: str
    lifetime: Lifetime
    confidence: EvidenceClass  # weakest class among evidence
    evidence: tuple[Evidence, ...]
    attrs: dict[str, Any] = {}
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

4.2 Node kinds (MVP)
GitHub secrets, GITHUB_TOKEN, OIDC tokens, STS sessions, literal values and stored
secret values are all CREDENTIAL nodes with a kind  and a lifetime .
Kind Canonical key Key attributes
REPOSITORY repo:<owner>/<name> slug, default_branch, sub_format
(CLASSIC, IMMUTABLE,
UNKNOWN)
WORKFLOW wf:<relpath> name, triggers, trigger_profiles
JOB job:<relpath>#<job_id> runs_on, self_hosted, environment,
perms_effective, id_token_write
(true, false, unknown),
secrets_inherit,
untrusted_checkout
ACTION_REF action:<owner>/<repo>
[/path]@<ref>
pin_kind (SHA, TAG, BRANCH,
AMBIGUOUS, DOCKER, LOCAL),
mutable, first_party
CREDENTIAL cred:<owner-node-id>:
<label>
kind, lifetime, ttl_seconds,
rotation_interval_days, criticality
OIDC_IDENTITY oidc:<job-id>:
<audience>
audience, candidates (list of
SubjectCandidate)
AWS_OIDC_PROVIDER aws:oidc:<url-host> url, client_ids
AWS_ROLE aws:role:<arn-or-tf-
address>
name, arn, max_session_duration,
trust_statements, policies,
boundary
SINK aws:secret:<name>  or
aws:ssm:<name>
sink_type, kms_key, rotation,
resource_policy
EXTERNAL_TARGET ext:<label> what a credential unlocks
(database, SaaS)
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

4.3 Edge kinds (MVP)
Kind From to Meaning Lifetime Weakest
allowed
evidence
CONTAINS repo to workflow to
job to step
Structure.
Never
traversed for
authority.
NA DECLARED
RUNS_IN ACTION_REF to JOB Code of this
action
executes
inside the
job runner
(one edge
per use site,
composite
actions
expanded).
JOB_BOUND DECLARED
HOLDS JOB to CREDENTIAL The
credential is
present in
the runner
during the
job.
per credential DECLARED
(explicit
reference),
ASSUMED
(inherit)
CAN_MINT JOB to
OIDC_IDENTITY
Job can
request an
OIDC token
( id-token:
write ).
JOB_BOUND DERIVED
CAN_ASSUME OIDC_IDENTITY to
AWS_ROLE
Trust policy
accepts at
least one
candidate
subject.
Carries the
sts session
credential.
SESSION_TTL DERIVED,
ASSUMED
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

4.4 Partition definitions
Let U  be the start set of a scenario. Authority edges are RUNS_IN, HOLDS, CAN_MINT,
CAN_ASSUME, CAN_READ_VALUE, STORES and AUTHENTICATES_AS. Reach(U)  is
every node reachable over authority edges whose class is not UNKNOWN.
A credential c  is obtained if c  is in Reach(U)  and the last edge of some path to it is
HOLDS or STORES, or c is the session credential attached to a CAN_ASSUME edge.
R(U) : obtained credentials with lifetime JOB_BOUND (GITHUB_TOKEN, OIDC
request token, minted OIDC JWT). They end with the job or at token expiry.
E(U) : STS session credentials from CAN_ASSUME. They are not revoked by stopping
the entrypoint. They expire after at most ttl_seconds  (A-STS-TTL). Revoking them
needs an AWS-side action.
Z0(U) : obtained credentials with lifetime PERSISTENT or PERSISTENT_ROTATING.
Kind From to Meaning Lifetime Weakest
allowed
evidence
CAN_READ_VALUE AWS_ROLE to SINK IAM
evaluation
allows
reading the
stored value
(and KMS if
known).
session scoped DERIVED,
ASSUMED
STORES SINK to CREDENTIAL The sink
holds a
credential
value.
PERSISTENT or
PERSISTENT_ROTATING
ASSUMED
(H-SECRET-
NAME)
AUTHENTICATES_AS CREDENTIAL to
AWS_ROLE or
EXTERNAL_TARGET
Holding the
credential
gives access
to the
target.
PERSISTENT DERIVED,
ASSUMED
CAN_MODIFY AWS_ROLE to SINK Role can
write or
rotate the
sink (used
for rotation
ordering and
findings).
session scoped DERIVED
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Z(U) : Z0(U)  plus a bounded closure. If c  in Z has an AUTHENTICATES_AS edge to a
principal p , and p  reaches further stored credentials c'  through CAN_READ_VALUE
and STORES, then c'  is in Z at depth+1. Default max depth 3.
Potential(U) : nodes reachable only through UNKNOWN-class edges. Reported
separately, never counted in R, E or Z.
This refines the blueprint formula: Z(u)  required a path from u to a sink and a STORES
edge, and now also requires that the value was obtained, not merely usable.
4.5 Invariants (enforced by tests)
1. Every node and edge has at least one Evidence entry.
2. Z contains only obtained credentials (never merely usable access).
3. UNKNOWN-class edges never contribute to R, E or Z.
4. A job without id-token: write  has no CAN_MINT edge. Reach from steps in that job
never includes roles (fixture fx09).
5. Graph, report and plan are deterministic: equal inputs produce byte-identical output.
6. No report field contains a secret value.
5. System architecture
5.1 Pipeline
inputs ---> discovery ---> parsers ---> facts ---> resolvers ---> graph
builder ---> analysis ---> reporters
 repo dir     walk+limits    gha          Workflow    permissions
nodes+edges       scenarios     console
 tf json      classify       tf_json      Job         expressions    evidence
R/E/Z         json
 iam json                    tf_hcl       TfResource  policy eval
closure        sarif
 config                      iam_json     PolicyDoc   OIDC solver
rotation plan  html

rank           opengraph (later)
Parsers are pure functions of (path, text) and know nothing about other files. Cross-file
linking happens only in resolvers and the graph builder.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

5.2 Module contracts
# parsers: pure, no I/O
def parse_workflow(rel_path: str, text: str) -> ParseResult[WorkflowFact]:
...
def parse_tf_json(label: str, text: str) -> ParseResult[TfModelFact]: ...
def parse_tf_hcl(rel_path: str, text: str) -> ParseResult[TfModelFact]: ...
def parse_policy_json(label: str, text: str) -> ParseResult[PolicyDocFact]:
...
# resolvers
def effective_permissions(wf: WorkflowFact, job_id: str, callers:
list[JobFact]) -> EffectivePerms: ...
def subject_candidates(job: JobFact, repo: RepoFact) ->
list[SubjectCandidate]: ...
def evaluate_trust(role: RoleFact, cands: list[SubjectCandidate]) ->
list[TrustMatch]: ...
def can_read(role: RoleFact, sink: SinkFact, ctx: PolicyContext) ->
ReadDecision: ...
# graph and analysis
def build_graph(facts: FactSet, cfg: Config) -> AuthorityGraph: ...
def run_scenario(g: AuthorityGraph, sel: Selector, cfg: Config) ->
ScenarioResult: ...
def plan_rotation(g: AuthorityGraph, res: ScenarioResult) -> RotationPlan:
...
# reporters
def render(report: Report, fmt: Format) -> bytes: ...
ParseResult  holds facts  and diagnostics . A parser never raises on bad input. It
returns a diagnostic and partial facts.
5.3 Repository layout
nhi-blast/
|-- pyproject.toml  README.md  LICENSE(proprietary)  NOTICE  SECURITY.md
CONTRIBUTING.md  AGENTS.md
|-- docs/  SPEC.md  assumptions.md  rules/NHB-*.md  benchmark.md
|-- scripts/  vendor_assets.py  gen_schema.py  record_oidc_claims.md
|-- src/nhi_blast/
|   |-- cli/        app.py scan.py rank.py explain.py export.py
|   |-- core/       models.py ids.py evidence.py diagnostics.py limits.py
config.py
|   |-- discovery/  walker.py classify.py
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

|   |-- parsers/
|   |   |-- yaml_marked.py
|   |   |-- gha/        workflow.py triggers.py permissions.py expressions.py
uses.py literals.py
|   |   |-- terraform/  tfjson.py tfhcl.py normalize.py
|   |   `-- iam/        policy_doc.py
|   |-- aws/        glob.py conditions.py policy_eval.py trust.py sinks.py
|   |-- oidc/       github_subject.py solver.py breadth.py
|   |-- graph/      builder.py store.py query.py
|   |-- analysis/   selectors.py reach.py partition.py closure.py rotation.py
rank.py findings.py
|   |-- report/     console.py json_report.py sarif.py html.py opengraph.py
assets/ templates/
|   `-- data/       assumptions.yaml aws_github_condition_keys.yaml
sinks_catalog.yaml
|                   credential_heuristics.yaml rotation_hints.yaml
trigger_profiles.yaml rules.yaml
|-- tests/  unit/ integration/ conformance/ property/ security/ golden/
fixtures/fx01..fx15/
`-- .github/workflows/  ci.yml release.yml      # all third-party actions
pinned to full SHAs
5.4 Technology stack
Concern Choice Notes
Language Python 3.12 or newer Typed, mypy --strict  clean
Models pydantic v2 JSON Schema generation for the report
YAML PyYAML (SafeLoader,
yaml.compose )
Marks give line numbers. No extra
dependency.
Terraform
JSON
standard json Primary input
Terraform
HCL
python-hcl2 (optional extra
hcl )
Output shape changed between major
versions. Isolate behind an adapter with
golden tests.
Graph networkx 3.x MultiDiGraph, condensation ,
lexicographical_topological_sort  for
determinism
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Supply-chain rule for a security tool: pin every dependency and every CI action, and pick
releases at least 14 days old.
5.5 Determinism and identifiers
node.id = kind-prefix + ':' + canonical_key  (table 4.2). Edge id is
sha256(kind|src|dst|sorted evidence keys)[:16] .
Finding id is NHB-<rule>-<sha256(rule|node ids|primary evidence)[:8]> .
Adjacency lists, findings and report arrays are sorted by (kind rank, id). JSON uses
sorted keys and fixed separators.
No wall-clock time in artifacts unless --timestamp  is given. The report carries
inputs_digest , the sha256 over sorted (path, file sha256) pairs.
5.6 Diagnostics
Diagnostic(level, code, file, line, message) . Codes: D-IO-*  (limits, unreadable),
D-YAML-* , D-GHA-* , D-TF-* , D-IAM-* , D-EXPR-* . One bad file never stops a scan. Exit
code 3 signals partial results when diagnostics of level error exist and --strict  is set.
5.7 Data files
Facts that change with the platforms live in src/nhi_blast/data/*.yaml , never in code.
Each entry carries source_url  and verified_on  (ISO date). nhi-blast version --
data  prints data versions and ages. Reports warn when a data file is older than 180 days.
Concern Choice Notes
CLI typer; rich as optional extra Plain-text fallback when rich is absent
HTML string.Template  plus a
deterministic layered SVG
layout computed in Python
No Jinja or runtime layout
engine. The same geometry is
used by screen and print. Record
SHA-256 of each embedded font in
assets/MANIFEST.json .
Dev pytest, hypothesis, pytest-cov,
ruff, mypy, jsonschema,
subvectors
subvectors  is a dev dependency only
Packaging hatchling, console script nhi-
blast
Lock with hashes ( uv lock  or pip-
compile --generate-hashes )
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

6. Inputs and discovery
6.1 Inputs
6.2 Limits (defaults, all configurable)
Input Flag Discovery Notes
Scan root positional PATH n/a All paths in reports
are relative to it,
POSIX style
Workflows auto .github/workflows/*.yml  and
*.yaml
Parsed by section 7
Local
composite
actions
auto uses: ./path  targets:
action.yml  or action.yaml
Expanded into the
calling job (7.7)
Terraform
JSON
--tf-json
FILE
(repeatable)
Also any *.json  whose top
level has format_version  plus
planned_values  or values
Primary Terraform
input
Terraform
HCL
--tf-hcl **/*.tf  and *.tf.json ,
excluding .terraform/
Fallback. Every fact
capped at DERIVED,
usually UNKNOWN
IAM policy
JSON
--iam-json
FILE
none Raw policy
documents or aws
iam get-role
output saved by the
user
Config nhi-
blast.toml
scan root Bindings, repo slug,
default branch,
account, region
(14.3)
Limit Default
max file size, YAML and policy JSON 5 MiB
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

A breach produces diagnostic D-IO-LIMIT , skips that file and continues.
6.3 Path safety
Resolve every candidate path and require path.is_relative_to(root) . Skip symlinks
whose target leaves the root.
Ignore .git/ , node_modules/ , .terraform/ , vendor/ .
To infer the repo slug, read .git/config  as plain text (never run git). Take the origin
URL and extract owner and name from the forms github.com:owner/name  and
github.com/owner/name , with or without a .git  suffix.
6.4 Repository identity
Precedence: --repo-slug , then nhi-blast.toml , then .git/config . If none works,
subjects use the symbolic repo */* , every OIDC result is capped at ASSUMED, and the
report says so on its first screen.
7. GitHub Actions parser
7.1 YAML loading
Use yaml.compose(text, Loader=SafeLoader)  and walk the node tree into
Marked(value, line)  objects. Keys keep their own line numbers.
Enforce the 6.2 limits while walking (nodes, depth, alias expansion).
Limit Default
max file size, Terraform JSON 64 MiB
max files scanned 20,000
max YAML nodes per file 200,000
max YAML depth 64
alias expansion factor 10
max graph nodes 500,000
per-scenario time budget 60 s, checked cooperatively
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Gotcha: YAML 1.1 turns the key on  into boolean True. Accept the keys 'on'  and True
and normalise to on .
Only the first YAML document is read.
PyYAML silently keeps the last duplicate key. Detect duplicates during the walk and
emit D-YAML-DUPKEY  (hostile files can hide values this way).
Never evaluate ${{ ... }}  expressions.
7.2 Facts
class Trigger(BaseModel):   event: str; branches: list[str]; branches_ignore:
list[str]; tags: list[str]; paths: list[str]; types: list[str]; line: int
class ExprRefs(BaseModel):  secrets: set[str]; secrets_all: bool; vars:
set[str]; head_ref_use: bool; custom_oidc_request: bool
class UsesRef(BaseModel):   raw: str; kind: str   # REMOTE, LOCAL, DOCKER
                            owner: str|None; repo: str|None; subpath:
str|None; ref: str|None
                            pin_kind: str; mutable: bool; first_party: bool;
line: int
class AwsAuthUse(BaseModel): role_ref_kind: str  # ARN, EXPR, NONE
                             role_arn: str|None; audience: str; static_keys:
bool; line: int
class StepFact(BaseModel):  index: int; line: int; uses: UsesRef|None; refs:
ExprRefs; literals: list[LiteralHit]; aws_auth: AwsAuthUse|None
class JobFact(BaseModel):   id: str; line: int; self_hosted: bool|None;
permissions: Perms|None
                            environment: str|None; environment_unresolved:
bool
                            uses_workflow: UsesRef|None; secrets_mode:
str|None  # EXPLICIT, INHERIT
                            steps: list[StepFact]; refs: ExprRefs;
untrusted_checkout: bool
class WorkflowFact(BaseModel): path: str; name: str|None; triggers:
list[Trigger]; permissions: Perms|None; jobs: dict[str, JobFact]
7.3 Triggers and profiles
Normalise all on:  forms (string, list, mapping, workflow_call , schedule  entries). The
profile table lives in data/trigger_profiles.yaml  and feeds both findings and subject
candidates (10.2).
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Event Who can start
it
Code that
runs
Secrets
and OIDC
Candidate ref in
sub
push anyone with
write access,
any branch or
tag unless
filtered
pushed
commit
yes heads or tags per
filter, else all
pull_request any
contributor.
Fork runs are
read-only
PR merge
commit
same-repo
yes, fork
none (A-
FORK-NO-
OIDC)
pull_request
pull_request_target any contributor
including forks
workflow
from base
branch. PR
code only if
the job
checks it out
yes base branch ref
(A-PRT-SUB)
workflow_run completion of
another
workflow,
possibly
started by a
fork PR
workflow
from default
branch
yes default branch
ref
issue_comment,
issues, discussion
any user who
can comment
default
branch
yes default branch
ref
workflow_dispatch write access chosen ref yes all branches and
tags (A-
DISPATCH-
ANYREF)
repository_dispatch token with
repo scope
default
branch
yes default branch
ref
schedule none (cron) default
branch
yes default branch
ref
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

7.4 Effective permissions
effective(job) =
  if job.permissions is set      -> expand(job.permissions)       # job block
replaces the workflow block
  elif workflow.permissions set  -> expand(workflow.permissions)
  else                           -> DEFAULT    # id-token = none (A-DEFAULT-
NO-IDTOKEN); other scopes UNKNOWN
expand('read-all')  = every scope read
expand('write-all') = every scope write, including id-token
expand({})          = every scope none
expand(map)         = listed scopes at their level; every unlisted scope none
Reusable workflow call: effective(callee job) = min(callee effective, caller
job effective).
  Callee file outside the repo: use only the caller grant, evidence ASSUMED.
id_token_write = (effective['id-token'] == 'write'); an expression value
gives UNKNOWN.
7.5 Expression scanner
Find every ${{ ... }}  span (and bare if:  values) in env, with, run, if and name fields of
the job and its steps. Extract without evaluating:
secrets.NAME  and secrets['NAME']  into the named set (store upper case for
matching, keep original for display).
Bare secrets , toJSON(secrets)  or a dynamic index into secrets_all = true .
vars.NAME , env.NAME .
github.event.pull_request.head.sha , .head.ref , .head.repo.full_name  and
github.head_ref  into head_ref_use .
The text ACTIONS_ID_TOKEN_REQUEST  anywhere in a run  value into
custom_oidc_request .
Event Who can start
it
Code that
runs
Secrets
and OIDC
Candidate ref in
sub
release, create,
delete
write access tag yes all tags
workflow_call the calling job per caller per caller caller candidates
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

7.6 uses  parsing and pin classification
local : starts with './'                       -> LOCAL
docker: starts with 'docker://'                -> DOCKER (pinned only if it
contains '@sha256:')
remote: '<owner>/<repo>[/<subpath>]@<ref>'     -> split at the last '@';
owner and repo are the first two path segments
pin_kind(ref):
  40 or 64 hex characters                      -> SHA       (mutable = false)
  starts with 'v' + digit, or digits and dots  -> TAG       (mutable = true)
  one of main, master, develop, dev, trunk     -> BRANCH    (mutable = true)
  anything else                                -> AMBIGUOUS (mutable = true;
could be tag or branch)
first_party = owner in {actions, github}  (still mutable unless SHA; used
only to rank lower)
Job-level uses is a reusable workflow:
'<owner>/<repo>/.github/workflows/<file>@<ref>' or
'./.github/workflows/<file>'.
7.7 Composite actions
For uses: ./path , read path/action.yml  or .yaml . If runs.using  is composite , treat
runs.steps  as steps of the calling job (same job context, same RUNS_IN target). Depth
limit 5, with cycle detection. A remote composite action cannot be read: emit D-GHA-
REMOTE-OPAQUE  and assume (A-STEP-SHARE) that its nested steps run in the job.
7.8 Untrusted checkout
In workflows triggered by pull_request_target , workflow_run  or issue_comment , set
untrusted_checkout = true  on a job when an actions/checkout  step has with.ref  or
with.repository  containing a head-ref expression (7.5) or the text refs/pull/ . Any
run  or uses  step after that checkout counts as executing attacker-controlled content
(class DECLARED for the pattern, ASSUMED for execution).
7.9 AWS authentication recognition
Recognise aws-actions/configure-aws-credentials  at any ref. Read inputs role-to-
assume , audience  (default sts.amazonaws.com ), aws-access-key-id , aws-secret-
access-key , aws-session-token , role-duration-seconds  (VERIFY input names against
the action's action.yml ).
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Literal role ARN: role_ref_kind = ARN .
Expression ( vars.X , secrets.X ): role_ref_kind = EXPR . Resolve through nhi-
blast.toml  bindings, otherwise leave unbound.
Key inputs filled from secrets: static_keys = true . These secrets become
CREDENTIAL nodes of kind AWS_ACCESS_KEY (persistent).
Other OIDC consumers (azure/login, google-github-actions/auth, hashicorp/vault-
action): diagnostic D-GHA-UNSUPPORTED-CONSUMER .
Important: a role named in role-to-assume  is only the intended role. Any step in the
job can request a token and call STS directly (10.6).
7.10 Literal credential finder
A tiny regex set, applied to scalar values of env , with  and run  (never comments).
Written without backslashes so it is safe to paste anywhere:
Output LiteralHit(kind, line, length)  only. The value is never stored or printed. This
is not a secret scanner. README points users to gitleaks or TruffleHog for that job.
7.11 Runner type and job scope
runs-on  containing self-hosted  sets self_hosted = true  (an expression gives
unknown). Report as info finding NHB-GHA-003, with a note that state may persist
across jobs.
Kind Pattern
AWS access key id (AKIA  or ASIA)  followed by 16 characters of [0-
9A-Z] , neighbours not alphanumeric
GitHub token gh[pousr]_[A-Za-z0-9]{36,}  or github_pat_[A-
Za-z0-9_]{22,}
Slack webhook https://hooks[.]slack[.]com/services/T[A-
Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]+
Slack token xox[abprs]-[A-Za-z0-9-]{10,}
Private key line beginning -----BEGIN  and containing
PRIVATE KEY-----
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Job-scope rule (regression guard): RUNS_IN and HOLDS edges attach to a JOB, never
to a WORKFLOW. A compromised step reaches only what its own job holds. Job
outputs and artifacts are a cross-job channel that version 1 does not model. State this
under Limits.
8. Terraform ingestion
8.1 Detection
A JSON file is Terraform JSON when its top level has format_version  and either
planned_values  (plan) or values  (state). Supported format_version  major: 1. Anything
else gives D-TF-FORMAT  and the file is skipped.
8.2 JSON walker
Plan: read planned_values.root_module  and prior_state.values.root_module .
State: read values.root_module . Recurse into child_modules .
A resource has address , mode  (managed or data), type , name , index , values . For
the same address prefer planned_values  (after state) over prior_state . Data
sources found only in prior_state  are accepted.
resource_changes[].change.after_unknown  is a boolean tree. A true leaf marks the
field UNKNOWN. planned_values  omits unknown fields.
Sensitive leaves ( sensitive_values , after_sensitive ): never read their content.
Record only that a value exists.
configuration.root_module.resources[].expressions[*].references  links
resources when values  lack the literal. Use it only to resolve references, never to
compute values.
Result: TfModelFact(resources by address, source=plan or state,
terraform_version, format_version) .
8.3 Resource handlers (MVP)
Resource type Facts used Produces
aws_iam_openid_connect_provider url, client_id_list AWS_OIDC_PROVIDER. GitHub when the url
host is
token.actions.githubusercontent.com
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Phase 2 handlers: aws_iam_user , aws_iam_access_key , aws_kms_key , aws_s3_bucket .
8.4 Unknown handling and policy-string resolution
Field unknown: evidence class UNKNOWN, a Potential edge, and diagnostic D-TF-
UNKNOWN(address, field)  suggesting that the user supply state JSON after apply.
Resolution order for a policy string: (1) the known string value, (2) the json  of a
referenced data.aws_iam_policy_document  in prior_state , (3) UNKNOWN.
8.5 HCL fallback
Use python-hcl2 behind an adapter. Resolve only: literal strings, jsonencode({...})  of
literals, heredoc JSON, data.aws_iam_policy_document  blocks with literal content
(converted to policy JSON), and var.x  with a literal default. Everything else is
UNKNOWN with D-TF-HCL-LIMIT . No module expansion, no for_each , no count . Facts
from HCL never exceed DERIVED.
Resource type Facts used Produces
aws_iam_role name, arn, assume_role_policy,
max_session_duration, inline_policy,
managed_policy_arns,
permissions_boundary
AWS_ROLE with trust statements and inline
policies
aws_iam_role_policy role, name, policy Inline policy on a role
aws_iam_policy ,
aws_iam_role_policy_attachment ,
aws_iam_policy_attachment
arn, policy, role or roles, policy_arn Managed policy links
data.aws_iam_policy_document json Resolves policy strings through references
aws_secretsmanager_secret name, arn, kms_key_id, policy SINK (secret)
aws_secretsmanager_secret_version secret_id only. Never read
secret_string
Marks the value as managed by Terraform (it
then also lives in state)
aws_secretsmanager_secret_rotation secret_id, rotation_rules,
rotation_lambda_arn
Sink rotation interval, lifetime
PERSISTENT_ROTATING
aws_secretsmanager_secret_policy secret_arn, policy Sink resource policy
aws_ssm_parameter name, type, key_id. Never read the
value
SINK (parameter)
aws_db_instance identifier, username,
manage_master_user_password,
master_user_secret_kms_key_id,
whether a password is set
EXTERNAL_TARGET (database) plus master
credential
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

8.6 Safety
Never run terraform or tofu (plan can execute provider and external-data code). Never
download providers or modules. Treat .terraform/  as absent.
9. AWS policy engine
9.1 Types
Statement(effect, actions, not_actions, resources, not_resources, principals,
conditions, sid, evidence) . Normalise scalar to list. Action names compare case-
insensitively. Resource ARNs and condition values compare case-sensitively.
9.2 Linear glob matcher and glob intersection
Never translate IAM globs to regular expressions on untrusted input. Use these:
def glob_match(pat: str, text: str, *, fold: bool = False) -> bool:
    # '*' matches any run (including empty), '?' matches one character
    if fold:
        pat, text = pat.lower(), text.lower()
    p = t = 0
    star = -1
    mark = 0
    while t < len(text):
        if p < len(pat) and pat[p] != '*' and (pat[p] == '?' or pat[p] ==
text[t]):
            p += 1
            t += 1
        elif p < len(pat) and pat[p] == '*':
            star, mark = p, t
            p += 1
        elif star != -1:
            p = star + 1
            mark += 1
            t = mark
        else:
            return False
    while p < len(pat) and pat[p] == '*':
        p += 1
    return p == len(pat)
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

def glob_intersects(a: str, b: str, *, fold: bool = False) -> bool:
    # True if some string matches both globs. Memoised DP over (i, j);
O(len(a) * len(b)).
    if fold:
        a, b = a.lower(), b.lower()
    @lru_cache(maxsize=None)
    def x(i: int, j: int) -> bool:
        if i == len(a) and j == len(b):
            return True
        if i < len(a) and a[i] == '*':
            return x(i + 1, j) or (j < len(b) and x(i, j + 1))
        if j < len(b) and b[j] == '*':
            return x(i, j + 1) or (i < len(a) and x(i + 1, j))
        if i < len(a) and j < len(b) and (a[i] == b[j] or a[i] == '?' or b[j]
== '?'):
            return x(i + 1, j + 1)
        return False
    return x(0, 0)
Use an iterative table instead of recursion when either string exceeds 400 characters.
Both functions need property tests (15.3) comparing them with a brute-force enumerator
on small alphabets.
9.3 Condition evaluation
Evaluate to TRUE, FALSE or UNRESOLVED against a context of known keys (each a set of
values). An unknown key is UNRESOLVED, and so is any value containing a policy variable
${...} .
Operator Static rule
StringEquals, StringNotEquals exact, case-sensitive
StringEqualsIgnoreCase folded compare
StringLike, StringNotLike glob_match  for known values, glob_intersects
for candidate languages
ArnEquals, ArnLike (and Not) whole-string glob
Bool compare to true or false
Null key present or absent
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

A statement applies when every condition is TRUE. If any is FALSE it does not apply.
Otherwise it is CONDITIONAL.
9.4 Decision procedure can(role, action, resource)
1. Collect statements: role inline policies, attached managed policies, optional permission
boundary (when supplied), sink resource policy (same account, union).
2. If any applicable statement is a definite Deny: DENY .
3. Else if any definite Allow (and, when a boundary was supplied, also allowed by the
boundary): ALLOW .
4. Else if any CONDITIONAL Allow: CONDITIONAL_ALLOW  (edge class ASSUMED, reasons
listed).
5. Else NOT_APPLICABLE  (implicit deny).
A CONDITIONAL Deny does not remove access, because the analysis is conservative. It is
listed in the edge detail. A resource of *  that could cover resources outside the inputs
adds a Potential edge UNKNOWN_EXTERNAL  (A-SCOPE-INPUT).
Operator Static rule
Numeric, Date, IpAddress families UNRESOLVED unless the key is known
ForAnyValue:  and ForAllValues: apply over multi-valued keys
IfExists  suffix absent key counts as TRUE
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

9.5 Data files
# data/aws_github_condition_keys.yaml
provider_host: token.actions.githubusercontent.com
source_url:
https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-
condition-keys.html
verified_on: 2026-10-25
supported: [aud, sub, actor, actor_id, job_workflow_ref, repository,
repository_id, repository_owner_id, workflow, ref, environment,
enterprise_id]
not_documented: [repository_owner, event_name, head_ref, base_ref,
workflow_ref, runner_environment]
required_control_any_of: [sub, job_workflow_ref]   # AWS IAM release notes,
2026-09-30
# data/sinks_catalog.yaml
secretsmanager_secret:
  value_read_actions: [secretsmanager:GetSecretValue,
secretsmanager:BatchGetSecretValue]
  modify_actions: [secretsmanager:PutSecretValue,
secretsmanager:UpdateSecret, secretsmanager:RotateSecret]
  arn_pattern: 'arn:aws:secretsmanager:{region}:{account}:secret:
{name}-??????'
  default_kms_alias: alias/aws/secretsmanager
ssm_parameter:
  value_read_actions: [ssm:GetParameter, ssm:GetParameters,
ssm:GetParametersByPath, ssm:GetParameterHistory]
  modify_actions: [ssm:PutParameter]
  arn_pattern: 'arn:aws:ssm:{region}:
{account}:parameter/{name_without_leading_slash}'
  credential_bearing_types: [SecureString]
9.6 ARN construction and KMS
Unknown region becomes * . Account comes from the role ARN, --aws-account  or
config, else * . Secrets Manager adds a hyphen and six random characters, modelled
as -?????? .
Policy resources are compared with candidate ARN globs using glob_intersects .
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

KMS: when the sink uses the default AWS-managed key, no extra requirement. When it
uses a customer key, require kms:Decrypt  on that key. Key policies are not modelled,
so a missing explicit grant gives CONDITIONAL with assumption A-KMS-
UNMODELLED (add to assumptions.yaml ).
10. OIDC claim-binding solver
10.1 Purpose
For each job that may mint an OIDC token and each AWS role that trusts the GitHub
provider, decide whether the trust policy, as written, accepts a token the job could
produce, and how broad the accepted set of subjects is. The result is a deterministic
pattern comparison over stated candidate sets. It is not a proof of exploitability.
10.2 Subject candidates
A candidate is a glob string describing the set of sub  values a job could mint. Build one
set per (job, trigger) and for both formats (classic repo:O/R  and immutable
repo:O@*/R@* ). Precedence follows GitHub: environment, then pull_request, then ref.
Case Candidate (classic form)
Job has environment: E  (literal) repo:O/R:environment:E  with :  in E written
as %3A
Job has an expression environment repo:O/R:environment:*  (UNKNOWN class)
No environment, event pull_request repo:O/R:pull_request
push with literal branches repo:O/R:ref:refs/heads/<branch>  per
branch
push with glob branch filters or none repo:O/R:ref:refs/heads/*  (filter **
becomes * )
push on tags repo:O/R:ref:refs/tags/<filter or *>
workflow_dispatch repo:O/R:ref:refs/heads/*  and
repo:O/R:ref:refs/tags/*  (A-DISPATCH-
ANYREF)
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Each candidate carries format , trigger , evidence  (workflow line) and the claim values
the job can state for other keys: repository , ref , environment , workflow ,
job_workflow_ref .
10.3 Trust statement evaluation
A statement is relevant when Principal.Federated  ends with oidc-
provider/token.actions.githubusercontent.com , the action includes
sts:AssumeRoleWithWebIdentity  and the effect is Allow. For each candidate:
1. Build the context: sub  as the candidate glob, aud  as the job audience, and any other
claim the job fixes ( repository , ref , environment , workflow , job_workflow_ref ).
2. Evaluate the Condition block with 9.3. Positive string operators use
glob_intersects(pattern, candidate) . A negative operator on sub  is
UNRESOLVED.
3. Claims that the job cannot fix statically ( actor , actor_id , repository_id ,
repository_owner_id , enterprise_id ) are UNRESOLVED. They narrow who can
match, so they are listed as ‘additional constraint not evaluable’ and the edge becomes
ASSUMED.
4. A condition key not in the supported list (data file 9.5) is a dead condition. Fail closed
for that statement and emit NHB-OIDC-006.
5. Check aud : a missing audience condition emits NHB-OIDC-004. A custom job
audience that differs from the policy value means no match.
Case Candidate (classic form)
schedule, workflow_run, issue_comment,
repository_dispatch
repo:O/R:ref:refs/heads/<default>
release, create repo:O/R:ref:refs/tags/*
pull_request_target repo:O/R:ref:refs/heads/<base>  (A-PRT-
SUB, base from filter or default branch)
workflow_call union of the caller job candidates. Unresolved
callers give repo:O/R:*  (UNKNOWN)
Customised sub template (config
oidc_sub_template )
built from the configured claim keys
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

6. Check the required control: if neither sub  nor job_workflow_ref  is constrained,
mark the statement UNCONSTRAINED.
10.4 Breadth classes
Parse each sub  pattern as repo:<org>[@id]/<name>[@id]:<context>  (or a customised
template) and classify. Severity is a label for ordering, not a verdict.
Severity adjustment: +1 level (cap CRITICAL) if the role can read any persistent credential
sink (Z not empty); +1 if the matching job has untrusted_checkout ; -1 when GitHub
settings input proves environment protection (Phase 2). A classic pattern like
repo:ORG/*  that matches only the classic variant yields NHB-OIDC-005 (format drift)
because immutable-format repos in the org will not match it.
10.5 Output
TrustMatch(job_id, role_id, matched_candidates, class, breadth, confidence,
unresolved_reasons, evidence) . One CAN_ASSUME edge per (OIDC_IDENTITY,
AWS_ROLE), listing every matched candidate.
Class Example pattern Potentially accepted
subjects
Base
severity
UNCONSTRAINED no sub  or job_workflow_ref
condition
any GitHub Actions
workflow that passes
the aud  check
CRITICAL
ANY_ORG *  or repo:* any repository CRITICAL
SAME_ORG repo:ORG/* , repo:ORG/*:* any repository in the
organisation
HIGH
REPO_ANY_CONTEXT repo:ORG/REPO:* any branch, tag, PR run
or environment in the
repo
HIGH
REPO_ANY_BRANCH repo:ORG/REPO:ref:refs/heads/* any pusher with write
access
MEDIUM
REPO_PULL_REQUEST repo:ORG/REPO:pull_request same-repo PR runs MEDIUM
ENVIRONMENT repo:ORG/REPO:environment:prod jobs that reference that
environment (A-ENV-
UNPROTECTED)
LOW
EXACT_REF repo:ORG/REPO:ref:refs/heads/main one named ref INFO
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

10.6 Role binding and the intended flag
Create CAN_ASSUME edges to every role whose trust policy matches, whether or not
the workflow names it. Set intended = true  on the role named by a literal role-to-
assume  (or a configured binding). Report unintended matches as the more important
result, because a compromised step can call STS itself.
10.7 Findings produced here
NHB-OIDC-001 to 006 (13.1). Each links the trust-policy file and line, the matching
workflow line and the breadth class.
11. Graph construction rules
Apply in this order. Each rule states its edge class.
Rule Input Creates
R1 Structure parsed files REPOSITORY, WORKFLOW, JOB
nodes and CONTAINS edges
R2 Action use
sites
step uses  (remote,
composite-expanded)
ACTION_REF node and one RUNS_IN
edge to the job per use site.
DECLARED
R3 Built-in
credentials
every job CREDENTIAL GITHUB_TOKEN
(JOB_BOUND, DECLARED). When
id_token_write  is not false,
CREDENTIAL OIDC request token
(JOB_BOUND, DERIVED). HOLDS
edges
R4 Referenced
secrets
refs.secrets CREDENTIAL (kind by H-SECRET-
NAME, PERSISTENT) and HOLDS.
DECLARED for explicit references.
secrets_all  or secrets: inherit :
one wildcard credential via an
UNKNOWN-class edge (A-RUNNER-
SECRETS) plus D-GHA-SECRETS-ALL
R5 Literal
credentials
LiteralHit CREDENTIAL (PERSISTENT,
DECLARED) and HOLDS
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Rule Input Creates
R6 OIDC minting job id_token_write OIDC_IDENTITY per audience and
CAN_MINT. DERIVED when true,
UNKNOWN when unknown
R7 Cloud
principals
Terraform facts AWS_OIDC_PROVIDER and
AWS_ROLE nodes
R8 Trust 10.3 results CAN_ASSUME, with a session
CREDENTIAL (SESSION_TTL, ttl = role
max_session_duration or 3600)
R9 Reads 9.4 results CAN_READ_VALUE. ALLOW is
DERIVED, CONDITIONAL_ALLOW is
ASSUMED, external wildcard is
UNKNOWN
R10 Stored
credentials
sinks and H-SECRET-NAME CREDENTIAL via STORES. Lifetime
PERSISTENT, or
PERSISTENT_ROTATING with
rotation_interval_days  from a
rotation resource (H-ROT-WINDOW).
Non-credential-looking sinks get no
STORES edge but are listed as
reachable data
R11 Static AWS
keys
secrets used as aws-access-
key-id
AUTHENTICATES_AS to ext:aws-
identity-unbound  unless bound in
config. Finding NHB-CRED-001
R12 Database
credentials
aws_db_instance  plus
matching secret
EXTERNAL_TARGET and
AUTHENTICATES_AS from the master
credential. Binding by
master_user_secret  reference or
config
R13 Modify rights 9.4 with modify_actions CAN_MODIFY edges (rotation
ordering, finding NHB-ROT-002)
R14 Intended flag 7.9 and 10.6 intended = true  attribute on the
CAN_ASSUME edge for the named
role
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

credential_heuristics.yaml  holds the H-SECRET-NAME patterns, each with a
credential kind , a criticality  weight (used in 12.5) and a rotation hint key.
12. Analysis engine
12.1 Selectors (compromise scenarios)
selector := 'action:' OWNER/REPO[/PATH]@REF   every use site of that exact
action and ref
          | 'action-any:' OWNER/REPO          every use site at any ref
          | 'job:' RELPATH '#' JOB_ID
          | 'workflow:' RELPATH               every job in the workflow
          | 'secret:' NAME                    a GitHub secret value is
leaked; starts at every job that holds it
          | 'role:' ROLE_ID_OR_TF_ADDRESS     an AWS role session is
compromised
          | 'repo-write'                      an actor with push access who
can edit workflows on a branch
          | 'fork-pr'                         an outside contributor; jobs
with untrusted_checkout
          | 'all-mutable-actions'             one scenario per mutable third-
party action (used by rank)
action:  resolves to ACTION_REF nodes, then follows RUNS_IN to the jobs. The start
set is those jobs. Use sites in jobs that hold nothing beyond GITHUB_TOKEN are still
listed, with an explicit ‘no path to any role’ line.
secret:  starts from the credential (already obtained) and from its holding jobs.
role:  starts at the AWS_ROLE with an E-class session.
repo-write  adds synthetic CAN_ASSUME edges (class ASSUMED) to every role
whose trust accepts repo:O/R:ref:refs/heads/* . A writer who edits a workflow on a
branch can add id-token: write  themselves. The report states this.
fork-pr  uses jobs flagged untrusted_checkout . Their OIDC edges carry A-PRT-SUB.
12.2 Reach
Breadth-first search from the start set over authority edges of class DECLARED,
DERIVED or ASSUMED. Deterministic order: sort out-edges by (edge kind rank,
destination id). Keep, per node, the best path: strongest weakest-edge class first, then
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

fewest hops, then lexicographically smallest edge-id list. UNKNOWN-class edges feed
Potential  only.
def reach(g, starts):
    seen = {s: Path(()) for s in sorted(starts)}
    queue = deque(sorted(starts))
    while queue:
        n = queue.popleft()
        for e in sorted(g.out_edges(n, authority=True), key=edge_order):
            cand = seen[n].extend(e)
            if e.dst not in seen or better(cand, seen[e.dst]):
                seen[e.dst] = cand
                queue.append(e.dst)
    return seen
12.3 Partition and closure
def analyze(g, starts, max_depth=3):
    rc = reach(g, starts)
    obtained = {c for c in rc if g.kind(c) is CREDENTIAL and
last_edge(rc[c]).kind in (HOLDS, STORES, CAN_ASSUME)}
    R = {c for c in obtained if g.lifetime(c) is JOB_BOUND}
    E = {c for c in obtained if g.lifetime(c) is SESSION_TTL}
    Z = {c: 0 for c in obtained if g.lifetime(c) in (PERSISTENT,
PERSISTENT_ROTATING)}
    frontier, depth = sorted(Z), 0
    while frontier and depth < max_depth:
        depth += 1
        nxt = []
        for c in frontier:
            for p in g.successors(c, AUTHENTICATES_AS):             #
principal the credential unlocks
                for sink in g.reads(p):                             #
CAN_READ_VALUE, class not UNKNOWN
                    for c2 in g.successors(sink, STORES):
                        if c2 not in Z and g.lifetime(c2) in
PERSISTENT_KINDS:
                            Z[c2] = depth
                            nxt.append(c2)
        frontier = sorted(nxt)
    return Partition(R, E, Z, potential=unknown_reach(g, starts),
truncated=bool(frontier))
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

If the loop ends with a non-empty frontier, the result is flagged truncated  and the report
says the depth limit was reached.
12.4 Unknowns
Potential paths show what an UNKNOWN edge would add, labelled ‘blocked by:
<diagnostic>’. They are never counted in R, E or Z. A scenario with many unknowns prints
a prominent line: ‘Result is a lower bound: N unresolved inputs’.
12.5 Rotation planner
Goal: an order in which a surviving credential never remains able to read a freshly rotated
one.
Nodes: Z plus the principals those credentials unlock. Edge p -> c  when the holder
of p  can read or modify c  (CAN_READ_VALUE or CAN_MODIFY, then STORES).
Rotate p  before c , because otherwise the attacker re-reads the new c  through p .
Cycles: condense strongly connected components. A component with more than one
member is a batch: freeze (temporarily deny or disable the principals involved), rotate
all members, then re-enable.
Order: topological generations of the condensation. Inside a generation sort by
(descending max criticality, ascending id).
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

def plan_rotation(g, res):
    Z = sorted(res.partition.Z)
    D = nx.DiGraph()
    D.add_nodes_from(Z)
    for p in Z:
        for c in controlled_by(g, p):            # credentials that p, or the
principal p unlocks, can read or modify
            if c in D and c != p:
                D.add_edge(p, c)                 # rotate p BEFORE c
    C = nx.condensation(D)
    steps = []
    for gi, gen in enumerate(nx.topological_generations(C)):
        comps = sorted(gen, key=lambda n: (-max_crit(C.nodes[n]['members']),
min(C.nodes[n]['members'])))
        for comp in comps:
            members = sorted(C.nodes[comp]['members'], key=lambda c: (-
crit(c), c))
            steps.append(Step(members=members, batch=len(members) > 1,
generation=gi))
    return RotationPlan(containment_steps(res), steps, verify_steps(res))
Criticality weights (data file): DB_MASTER_PASSWORD 100, AWS_ACCESS_KEY 90,
PRIVATE_KEY 85, API_KEY 70, API_TOKEN 65, GENERIC_SECRET 55, WEBHOOK_URL 40,
GITHUB_TOKEN 30.
Per step the plan shows: credential, kind, survival window (‘until rotated’, or ‘up to N days’
for PERSISTENT_ROTATING, H-ROT-WINDOW), depends-on list, evidence, confidence,
and a suggested action from rotation_hints.yaml . Hints are text for a human. The tool
never executes them.
12.6 Containment and verification steps
Containment (phase 0) is chosen by selector kind and is always listed before rotation:
action:  pin to a verified full commit SHA or remove it, disable the affected workflow,
review run logs for the exposure window.
secret:  rotate immediately (it is in Z).
role:  and any non-empty E set: revoke active sessions for the roles (ASSUMED hint:
the IAM console action that attaches a deny policy keyed on token issue time.
VERIFY), then tighten the trust policy.
repo-write : review recent pushes and branch rules, remove the actor.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Verification (final phase), ASSUMED and marked VERIFY: search CloudTrail for
AssumeRoleWithWebIdentity  on the E-set roles and for GetSecretValue  or
GetParameter  on Z sinks inside the exposure window.
12.7 Ranking
rank  runs all-mutable-actions , then sorts by (count of Z descending, count of E
descending, number of use sites descending, id). Output columns: action, pin kind, use
sites, jobs with OIDC, |R|, |E|, |Z|, highest criticality.
12.8 Performance budget
Graph build and one scenario for 200 workflows and 2,000 Terraform resources: under 5 s
on a laptop. rank  over 300 mutable actions: under 60 s. Cache per-role read decisions.
Use iterative DP for long glob inputs.
13. Findings, reports and exports
13.1 Findings catalog
Rule documentation lives in docs/rules/NHB-*.md  (what it means, evidence, false-
positive notes, fix).
Rule Title Trigger Base severity
NHB-
OIDC-
001
Trust policy has no sub  or
job_workflow_ref  control
10.3 step 6 CRITICAL
NHB-
OIDC-
002
Organisation-wide or global
wildcard in sub
classes ANY_ORG,
SAME_ORG
CRITICAL or HIGH
(10.4)
NHB-
OIDC-
003
Repo-wide wildcard (any ref,
PR or environment)
class
REPO_ANY_CONTEXT
HIGH
NHB-
OIDC-
004
Audience not constrained 10.3 step 5 MEDIUM
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Rule Title Trigger Base severity
NHB-
OIDC-
005
Subject format drift (classic
pattern, immutable repos)
10.4 LOW
NHB-
OIDC-
006
Dead condition key for AWS 10.3 step 4 LOW
NHB-
OIDC-
007
Environment-only trust,
protection unknown
class ENVIRONMENT INFO
NHB-
GHA-001
Mutable third-party action in
a job that holds secrets or
OIDC
R2 with R4 or R6 MEDIUM, HIGH if
Z is non-empty
NHB-
GHA-002
Untrusted checkout under a
privileged trigger with
secrets or OIDC
7.8 HIGH, CRITICAL if
a role is reachable
NHB-
GHA-003
Self-hosted runner 7.11 INFO
NHB-
GHA-004
secrets: inherit  or whole
secrets  context
R4 MEDIUM
NHB-
GHA-005
Literal credential in workflow 7.10 HIGH
NHB-
CRED-
001
Static AWS keys used where
OIDC could be used
R11 MEDIUM
NHB-
SURV-
001
Credentials survive
revocation of the entrypoint
any scenario with Z non-
empty
by highest
criticality in Z
NHB-
ROT-001
Reachable credential sink
without rotation
R10 LOW
NHB-
ROT-002
Role can modify a sink
reachable from a mutable
entrypoint
R13 MEDIUM
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

A finding message follows one template: what the files say, what that potentially allows,
evidence class, and the assumption IDs involved.
13.2 JSON report ( nhi-blast-report/1.0 )
Generated from the pydantic models with scripts/gen_schema.py  and committed under
docs/schema/ . Shown as YAML for brevity, output is JSON with sorted keys.
schema: nhi-blast-report/1.0
tool: {name: nhi-blast, version: 0.1.0}
inputs: {digest: <sha256>, repo_slug: acme/shop, files: [{path: <rel>,
sha256: <hex>, kind: workflow}]}
scope_and_limits: [<string>]
assumptions: [{id: A-STS-TTL, statement: <text>, used_by: [<edge id>]}]
diagnostics: [{level: warning, code: D-TF-UNKNOWN, file: <rel>, line: 12,
message: <text>}]
findings: [{id: NHB-OIDC-002-1a2b3c4d, rule: NHB-OIDC-002, severity: HIGH,
confidence: derived, title: <text>, message: <text>, evidence: [<Evidence>],
path: [<node id>]}]
graph: {nodes: [<Node>], edges: [<Edge>]}
scenarios:
  - selector: 'action:tj-actions/changed-files@v45'
    start_nodes: [<job id>]
    partition: {R: [<cred id>], E: [{credential: <id>, ttl_seconds: 3600}],
Z: [{credential: <id>, depth: 0, lifetime: persistent, survival_window:
until_rotated, criticality: 100}]}
    potential: [<edge id>]
    truncated: false
    rotation_plan: {containment: [<Step>], rotation: [<Step>], verify:
[<Step>]}
13.3 SARIF 2.1.0
One run. tool.driver : name nhi-blast , version , informationUri , one rule per
finding rule with shortDescription.text , fullDescription.text  (at most 1,000
characters), help.text  and help.markdown , defaultConfiguration.level ,
properties.tags , properties.precision .
Result: ruleId , level  (CRITICAL and HIGH map to error, MEDIUM to warning, LOW
and INFO to note), message.text , locations[0].physicalLocation  with
artifactLocation.uri  (relative, uriBaseId  of %SRCROOT% ) and region.startLine .
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

properties.security-severity  (string): CRITICAL 9.5, HIGH 8.0, MEDIUM 5.5, LOW
3.0. Omit for INFO.
partialFingerprints : key nhiBlast/v1  with sha256(rule | node ids | primary
evidence file) . Stable across line shifts.
codeFlows[0].threadFlows[0].locations : the attack path, one location per edge
that has a file and line, each with a message such as ‘workflow grants id-token: write’.
properties.confidence  and properties.assumptions  carry evidence class and
assumption IDs.
Limits: GitHub keeps at most 5,000 results per upload, 10 MB gzip, 20 runs per file. Sort
by severity then id, truncate, and add a tool notification saying how many were
dropped. Validate output against the vendored SARIF 2.1.0 JSON Schema in tests.
13.4 HTML report (single self-contained file)
Sections: Scope and Limits, Summary, Scenario picker, Graph, Survival panel (R, E, Z
tables), Rotation plan (print-friendly), Findings, Assumptions and Unknowns,
Diagnostics.
Graph: deterministic layered SVG computed by the reporter and inlined in the file
(no browser layout engine). Node colour by layer, edge style by evidence class
(solid for DECLARED and DERIVED, dashed for ASSUMED, dotted for UNKNOWN). Clicking a
node or edge shows its evidence with file and line. The print stylesheet emits the same
layout on an A3 landscape page.
Security (MUST): the report data is embedded in <script
type='application/json'>  with < , >  and &  escaped as unicode escapes. All text
reaches the DOM through textContent  or setAttribute  with escaped values, never
innerHTML . A meta CSP of default-src 'none'; style-src 'unsafe-inline';
script-src 'sha256-...'  lists the hash of each inline script. No network requests. A
test feeds hostile strings ( <img src=x onerror=...> ) through step names, secret
names and file paths and asserts they render inert.
Works offline. File size target under 3 MB.
13.5 Console
Four stages (parse, trust audit, scenario, survival) plus the rotation plan. Colour only on a
TTY. Every line that states a fact ends with its evidence class and a file:line  when one
exists. Never print secret values.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

13.6 Exports
export --format dot  and json  ship in the MVP. opengraph  (Phase 2) writes
BloodHound OpenGraph JSON so users can combine results with GitHound data. Node
and edge mapping is a documented table in docs/opengraph.md .
14. CLI specification
14.1 Commands
14.2 scan  options and exit codes
Command Purpose
nhi-blast scan PATH Parse, build the graph, audit trust policies, run
scenarios, write reports
nhi-blast rank PATH Rank mutable third-party actions by blast radius
nhi-blast explain ID --report
FILE
Show the evidence chain for a finding or node
from a saved JSON report
nhi-blast export PATH --format F Export the graph (json, dot, opengraph)
nhi-blast schema Print the report JSON Schema
nhi-blast version [--data] Tool version, and data-file versions with ages
Option Meaning Default
--tf-json FILE Terraform plan or state JSON
(repeatable)
auto-detect
--tf-hcl / --no-tf-hcl Enable the HCL fallback on only if no JSON
found
--iam-json FILE Extra policy documents
(repeatable)
none
--simulate-compromise SEL Scenario selector
(repeatable)
none
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

Exit codes: 0 success, 1 findings at or above --fail-on , 2 usage error, 3 partial results
with --strict , 4 internal error.
Option Meaning Default
--format F console, json, sarif, html
(repeatable)
console
--out DIR Output directory ./nhi-blast-out
--fail-on LEVEL critical, high, medium, low or
never
never
--max-depth N Closure depth (12.3) 3
--repo-slug , --default-branch ,
--aws-account , --aws-region
Identity overrides from config or files
--config FILE Config path nhi-blast.toml  in
the root
--strict Treat error diagnostics as exit
code 3
off
--timestamp Add wall-clock time to
artifacts
off
--no-color Disable colour auto
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

14.3 Config file
repo_slug = 'acme/shop'
default_branch = 'main'
aws_account = '111122223333'
aws_region = 'us-east-1'
[bindings.roles]         # variable or secret name used in role-to-assume ->
role address or ARN
AWS_DEPLOY_ROLE_ARN = 'aws_iam_role.deploy_prod'
[bindings.credentials]   # stored credential label -> target it unlocks
'prod/db-master' = 'aws_db_instance.main'
[oidc]
sub_template = ['repo', 'context']   # only if the organisation customised
sub claims
[ignore]
rules = []
paths = ['examples/**']
14.4 Reference output (fixture fx07, derived from the algorithm)
Fixture: release.yml  job publish  (push on tags v* , id-token: write , uses the tj-
actions action at tag v45, configure-aws-credentials  with role deploy-prod ,
references secrets.SLACK_WEBHOOK_URL ) and ci.yml  job test  (pull_request, no
permissions block, same action). Terraform state has roles deploy-prod  (trust
repo:acme/shop:ref:refs/tags/v* ) and legacy-ci  (trust repo:acme/* ).
$ nhi-blast scan . --tf-json tfstate.json --simulate-compromise 'action:tj-
actions/changed-files@v45'
NHI-Blast 0.1.0 | repo acme/shop (from .git/config) | inputs 9c1f3a7e
Scope: 2 workflows, 2 jobs, 9 Terraform resources.
Not analysed: SCPs, environment protection, branch rules, live AWS state, job
outputs and artifacts.
[1/4] Parsed 2 workflows and tfstate.json (state). 0 errors, 1 warning.
[2/4] OIDC trust audit
  CRITICAL NHI-OIDC-002 aws_iam_role.legacy_ci  main.tf:61
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

           pattern 'repo:acme/*' is accepted for any repository in org 'acme'
[SAME_ORG, DERIVED]
           raised from HIGH: this role can read 1 persistent credential
  LOW      NHB-OIDC-005 aws_iam_role.legacy_ci  main.tf:61
           classic-form pattern will not match repositories that use
immutable subjects [DERIVED]
[3/4] Scenario action:tj-actions/changed-files@v45 (2 use sites, mutable TAG)
  release.yml#publish  holds GITHUB_TOKEN, OIDC request token,
secrets.SLACK_WEBHOOK_URL   (id-token: write, release.yml:9)
  ci.yml#test          holds GITHUB_TOKEN only. No path to any role.
  Potentially assumable from release.yml#publish (sub
repo:acme/shop:ref:refs/tags/v*):
    deploy-prod  intended    [DERIVED]  trust main.tf:48
    legacy-ci    UNINTENDED  [DERIVED]  trust main.tf:61
  Potentially readable stores:
    deploy-prod -> prod/db-master, prod/app-config, /prod/stripe/live_key
    legacy-ci   -> /legacy/ci-token
[4/4] Revocation-survival
  R  ends with the job .................... 3   GITHUB_TOKEN x2, OIDC request
token
  E  expires, not revocable from GitHub ... 2   STS sessions deploy-prod and
legacy-ci, up to 3600 s [A-STS-TTL]
  Z  survives revocation of the action .... 5
     1  prod/db-master          DB master password   until rotated   [ASSUMED
H-SECRET-NAME]
     2  /prod/stripe/live_key   API key              until rotated   [ASSUMED
H-SECRET-NAME]
     3  /legacy/ci-token        API token            until rotated   [ASSUMED
H-SECRET-NAME]
     4  prod/app-config         generic secret       up to 30 days   [ASSUMED
H-ROT-WINDOW]
     5  SLACK_WEBHOOK_URL       webhook URL          until rotated
[DECLARED release.yml:31]
Rotation plan
  Phase 0 contain:  pin or remove the action (release.yml:14, ci.yml:11);
revoke sessions for deploy-prod and legacy-ci;
                    tighten legacy-ci trust to an exact subject.
  Phase 1 rotate:   no dependencies among these credentials, ordered by
criticality: 1, 2, 3, 4, 5.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)

  Phase 2 verify:   look for AssumeRoleWithWebIdentity and reads of the five
stores since the first run that used v45 [ASSUMED, VERIFY].
Written: ./nhi-blast-out/report.json  report.sarif  report.html
The fixture NHI-OIDC typo above must not exist in code: the rule ID is NHB-OIDC-002 .
Golden files for fx07 define the exact bytes.
NHI-Blast: Complete Architecture and Build Speciﬁcation (v2.0)
