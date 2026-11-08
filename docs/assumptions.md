# Assumptions and heuristics

Every report carries the assumptions and heuristics that shaped it. The normative
registry is [`src/nhi_blast/data/assumptions.yaml`](../src/nhi_blast/data/assumptions.yaml);
this page is the human-readable index. `VERIFY` means the statement could not be
confirmed from a primary source during specification research and is treated as
`ASSUMED`, never as a configuration fact.

| ID | Kind | VERIFY | Meaning |
| --- | --- | --- | --- |
| A-STEP-SHARE | assumption | no | All steps in a job share the runner environment, so a compromised action inherits what the job holds. |
| A-RUNNER-SECRETS | assumption | yes | Only secrets referenced by expressions are materialised; `secrets: inherit` or `toJSON(secrets)` may expose every repository secret, so the edge is UNKNOWN. |
| A-OIDC-ENV | assumption | no | With `id-token: write`, any step can request a token for every audience through the runner. |
| A-DEFAULT-NO-IDTOKEN | assumption | yes | A job with no `permissions` block does not have writable `id-token`. |
| A-FORK-NO-OIDC | assumption | yes | Fork pull-request runs receive neither repository secrets nor OIDC tokens. |
| A-PRT-SUB | assumption | yes | `pull_request_target` mints a subject for the base-branch ref. |
| A-DISPATCH-ANYREF | assumption | no | A user with write access can dispatch a workflow or push on any branch or tag. |
| A-ENV-UNPROTECTED | assumption | yes | Environment protection and branch rules are unknown, so anyone who can edit workflows may satisfy an environment claim. |
| A-STS-TTL | assumption | no | When the requested session duration is not declared or cannot be read, a session is assumed to last at most the role's `max_session_duration` (1 h when unset, 12 h when the role maximum is unknown). |
| A-CAC-DEFAULT | assumption | yes | The action default for this ref is unverified. Use the known role maximum or the STS 43200 s cap as the conservative upper bound; the one-hour chaining cap applies only when chaining is established. Verified refs are listed in `configure_aws_credentials.yaml`. |
| A-SESSION-POLICY | assumption | no | A session policy can only narrow access. It is not evaluated, so reachable access may be broader than the session allows; a resource policy naming the session ARN is not limited by it. |
| A-NO-SCP | assumption | no | SCPs, RCPs, session policies and permission boundaries that were not supplied are not modelled; Allow results may over-approximate. |
| A-SCOPE-INPUT | assumption | no | Only resources present in the inputs exist; a wildcard resource may cover resources outside the scan and is reported as `UNKNOWN_EXTERNAL`, feeding potential paths only. |
| A-DEFAULT-BRANCH | assumption | no | The default branch is `main` unless configured. |
| A-REPO-AGE | assumption | no | Whether a repository mints classic or immutable subjects is unknown, so both are evaluated; declare `[github] subject_format` to settle it. GitHub documents the immutable form `repo:OWNER@OWNER-ID/REPO@REPO-ID` as the default for repositories created after 2026-07-15, as opt-in for older ones, as the result of a rename or transfer after that date, and as unavailable on GitHub Enterprise Server. |
| A-REPO-WRITE | assumption | yes | A repository writer can edit a workflow on a branch, add `id-token: write` and request the default audience; branch protection is unknown. |
| A-KMS-UNMODELLED | assumption | yes | KMS key policies are not modelled; a customer-managed-key read without an explicit grant is conditional. |
| A-TRUST-UNMODELLED | assumption | yes | An unresolved role trust policy produces UNKNOWN-class potential paths, never declared authority. |
| A-POLICY-UNMODELLED | assumption | yes | A missing managed or inline policy body produces potential access only, never a confident allow or deny. |
| A-REUSABLE-CALLER | assumption | no | When several callers use the same reusable workflow, the per-scope most permissive caller bound is used and the disagreement is diagnosed. |
| H-SECRET-NAME | heuristic | no | Credential-bearing sinks and credential kinds are inferred from resource type and name patterns. |
| H-ROT-WINDOW | heuristic | no | A rotation resource means periodic rotation; the next rotation time is unknown, so survival is reported as "up to N days". |
| H-LITERAL | heuristic | no | A small regex set recognises literal credentials; hits report kind and length only. |

## How assumptions appear in output

- Every node and edge carries at least one evidence item. Assumption-backed
  attributes name the relevant `A-*` or `H-*` ID.
- The report lists only assumptions that are actually attached to a node, edge,
  finding or scenario. A registry entry that did not affect the result is not shown.
- UNKNOWN-class edges are counted in `potential`, never in R, E or Z.

## Changing an assumption

Treat a registry change as a product change: update the YAML entry, its `verify`
flag and impact, add or adjust a behavioural test, and update this table. Do not
silently flip an assumption to make a scenario look stronger.
