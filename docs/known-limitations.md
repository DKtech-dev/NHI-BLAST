# Known limitations

This page records what NHI-Blast does not model, what it deliberately leaves
conditional, and where its results stop. Read it before treating a report as a
complete inventory of authority.

## 1. What a result means

NHI-Blast answers a hypothetical question from the files it was given: *if this
entrypoint were compromised and the described path were exercised, which authority
would potentially be reachable, and what would survive revocation?* It does not prove
that a compromise occurred, that a path was exercised, that a credential was read, or
that a role can be taken over. Severity orders findings for review; it is not a
verdict.

The tool reads static repository content. It does not contact GitHub, AWS or any other
system, and it cannot observe live permissions, running jobs, or whether a human
actually performed a rotation.

## 2. Input scope

Supported inputs:

- GitHub Actions workflow YAML under the repository's workflow directory.
- Local composite actions referenced by workflows.
- Terraform plan or state JSON (primary), Terraform JSON configuration (`.tf.json`)
  and Terraform HCL (best-effort fallback).
- IAM policy documents, `get-policy` output and `get-role` output supplied with
  `--iam-json`.

Not read or fetched:

- Remote reusable workflows and remote composite actions. Their internals are not
  downloaded; a remote callee contributes only the caller grant, with assumptions.
- Marketplace action source code. A mutable `uses:` reference is reported as a
  supply-chain fact, not analysed for malicious behaviour.
- CloudFormation, CDK, Pulumi, GitLab CI, Azure, GCP, Kubernetes or MCP
  configuration.
- GitHub organisation, repository, environment or branch-protection settings, and
  live AWS state.
- Secrets, environment values, job outputs, artifacts or runner state.

Only the first YAML document in a file is analysed. A second document produces a
diagnostic and is not merged. A workflow that is syntactically invalid yields partial
facts plus diagnostics; absence of a finding is not evidence of absence.

## 3. Unmodelled AWS and GitHub controls

The following are not evaluated and appear as assumptions in the report:

- Service control policies, resource control policies, session policies and
  permission boundaries that were not supplied (`A-NO-SCP`).
- KMS key policies and grants. A customer-managed-key read without an explicit grant
  is conditional (`A-KMS-UNMODELLED`).
- AWS role chaining. Role-to-role chaining is outside the specification's scope and
  is not followed.
- Managed policy contents whose ARN is attached but whose document was not supplied
  (`A-POLICY-UNMODELLED`). A missing body never becomes an automatic deny.
- GitHub environment protection rules, required reviewers, deployment branch rules
  and branch protection (`A-ENV-UNPROTECTED`, `A-REPO-WRITE`). Whether a repository
  mints classic or immutable OIDC subjects is unknown, so both formats are evaluated
  (`A-REPO-AGE`).
- Whether a job with no explicit `permissions` block can mint an OIDC token depends
  on repository settings; the default is treated as no writable `id-token`
  (`A-DEFAULT-NO-IDTOKEN`), and the uncertainty is recorded.
- Which secrets are materialised when `secrets: inherit`, the bare `secrets` context,
  `toJSON(secrets)` or a dynamic index is used. Those become an UNKNOWN-class wildcard
  credential edge (`A-RUNNER-SECRETS`).

The report lists only assumptions that were attached to a result, not the entire
registry. The registry is in `docs/assumptions.md`.

## 4. OIDC and IAM evaluation limits

- The trust audit evaluates the documented GitHub provider claim keys listed in
  `aws_github_condition_keys.yaml`. A claim that is not documented for the provider
  fails the statement closed and is reported as a dead key (`NHB-OIDC-006`). AWS and
  GitHub documentation disagree about some custom claims; the data file follows AWS
  and records the disagreement.
- Condition evaluation supports the positive string and ARN operators
  (`StringEquals`, `StringEqualsIgnoreCase`, `StringLike`, `ArnEquals`, `ArnLike`),
  their negative forms in concrete mode, `Bool`, `Null`, `IfExists` and the
  `ForAnyValue`/`ForAllValues` qualifiers. `Numeric*`, `Date*`, `IpAddress`, `Binary*`
  and policy variables are not evaluated; a statement that depends on them is
  conditional, never a confident allow.
- A negative operator compared with a candidate glob is unresolved rather than
  guessed. Unresolved conditions make a statement conditional (`ASSUMED`), not true.
- A subject pattern is evaluated against candidate subjects derived from the trigger
  profile, repository identity and default branch. If the identity is symbolic
  (unknown owner or repository), the match is necessarily weaker.
- A reusable workflow with multiple local callers uses the most permissive caller
  bound per permission scope and emits a diagnostic when callers disagree
  (`A-REUSABLE-CALLER`). A workflow with `workflow_call` and no local caller is
  bounded by assumptions, not by an observed invocation.
- Action-level OIDC behaviour is represented at job level. The analysis assumes all
  steps in a job share the runner environment (`A-STEP-SHARE`); it does not model a
  malicious step declining to expose a token, or a runner that isolates steps.

## 5. Terraform and HCL limits

- Plan/state JSON is the primary source. Terraform JSON configuration (`.tf.json`) is
  read without the optional HCL parser. Unknown values, sensitive values and unresolved
  references remain unknown; sensitive leaves are never read.
- The HCL fallback resolves literal strings, `jsonencode` of literals, heredoc JSON,
  literal `data.aws_iam_policy_document` blocks and variables with literal defaults.
  Dynamic blocks, computed expressions, module outputs and provider functions remain
  unknown and produce `D-TF-HCL-LIMIT`. HCL facts never exceed `DERIVED` evidence.
- Policy strings inside plan/state JSON are single-line JSON, so a statement's line
  evidence falls back to the resource address line.
- Only IAM policy documents that are visible in the supplied inputs are evaluated.
  Policies created outside the repository are absent.

## 6. Graph, closure and rotation

- Persistent-credential closure is bounded (default depth 3, configurable). Reaching
  the bound sets `truncated` and emits a diagnostic; deeper authority is not claimed.
- Scenario work is bounded by a time budget and a node budget. Exceeding a budget
  produces a partial result with diagnostics, never an unbounded run.
- UNKNOWN-class edges are reported in the separate `potential` set. They never
  contribute to R, E or Z. A path that depends on an unresolved input therefore does
  not appear as certain survival.
- Rotation ordering is only as complete as the modelled edges and the platform
  rotation hints. The plan states *what to rotate and in what order*; it does not
  execute or verify a rotation. The verification step is a human instruction (for
  example a CloudTrail search), not an automated check.
- "Survives" means the credential is not invalidated by revoking the entrypoint. It
  does not mean the credential has a known remaining lifetime. Where periodic
  rotation is configured, the plan says "up to N days" and asks the operator to
  confirm the schedule ran.

## 7. Reporting limits

- Console output is a summary. The JSON report is the complete machine-readable
  record; SARIF is for code-scanning ingestion; the HTML report is a single offline
  document.
- The HTML report needs JavaScript to render its embedded data. Without JavaScript it
  shows only a note explaining that; use the console or JSON report instead. The graph
  canvas is pointer-operated and is not keyboard operable; the scenario, survival,
  findings and cross-scenario matrix sections present the same evidence as text, with
  labelled tables, a skip link and keyboard-operable trace buttons, so the report
  remains usable without interacting with the graph. Wide tables scroll inside
  labelled, keyboard-focusable regions instead of widening the page.
- SARIF output is capped at 5,000 results with a notification, matching GitHub
  code-scanning limits. Findings beyond the cap are counted but not listed.
- A suppressed rule is removed from the findings list. Suppression does not alter the
  graph or the survival partition, so a suppressed risk can still affect a scenario.

## 8. Environment and packaging

- Python 3.12 or newer is required. The project is tested on CPython 3.12, 3.13 and
  3.14 on Windows; Linux execution and remote CI remain external gates.
- The HCL parser is an optional extra. Without it, `.tf` files are still discovered
  but cannot be parsed; each produces an error diagnostic (`D-TF-HCL-UNAVAILABLE`)
  that names the missing extra. Terraform JSON still works, and `--strict` turns the
  partial result into exit code 3.
- The `rich` extra changes console styling only. Reports and exit codes are identical
  with and without it.
- On Windows, creating a real symlink requires a privilege that the test environment
  may not hold; a test that cannot create one is skipped, and directory-junction
  escape coverage is used instead. This is a test-environment gap, not a claim that
  symlink handling is unverified on Windows.
- The performance figures in `docs/benchmark.md` describe one documented machine and
  Python version. They are not a promise for every environment.

## 9. Deliberately out of scope

Role chaining, IAM users and long-lived access keys as first-class entrypoints, S3 or
KMS key-policy modelling, CloudFormation, GitLab, Azure, GCP, Kubernetes, MCP
configuration, Cloudflare, live API collection, GitHub settings ingestion, and any
SaaS, service, database or web application are out of scope. Requests to add them
conflict with the specification and should be treated as product changes, not bug
fixes.
