# Data provenance

Platform facts live in [`src/nhi_blast/data`](../src/nhi_blast/data) rather than in
code. Each file records a `source`, `source_url` and `verified_on` date. The
`verified_on` date is the date the fact was checked during research; it is not a
claim that the external documentation is still unchanged.

| File | Purpose | Primary source | Verified |
| --- | --- | --- | --- |
| `assumptions.yaml` | Assumption and heuristic registry | [GitHub Actions documentation](https://docs.github.com/en/actions) | 2026-10-25 |
| `aws_github_condition_keys.yaml` | AWS condition keys accepted for the GitHub OIDC provider | [AWS IAM condition keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html) | 2026-10-25 |
| `credential_heuristics.yaml` | Literal credential and sink-name patterns | [GitHub security hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions) | 2026-10-25 |
| `permission_scopes.yaml` | Valid GitHub Actions permission scopes | [Workflow syntax: permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions) | 2026-10-25 |
| `rotation_hints.yaml` | Human rotation guidance per credential kind | [AWS access-key rotation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html) | 2026-10-25 |
| `rules.yaml` | Findings catalog, severity and metadata | [GitHub security hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions) | 2026-10-25 |
| `sinks_catalog.yaml` | Credential-store read/write actions and KMS defaults | [Secrets Manager IAM permissions](https://docs.aws.amazon.com/secretsmanager/latest/userguide/reference_iam-permissions.html) | 2026-10-25 |
| `trigger_profiles.yaml` | Trigger threat profiles and subject refs | [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) | 2026-10-25 |

## Known source conflict

The condition-key file records a disagreement between AWS and GitHub
documentation about custom claims for the GitHub OIDC provider. The tool follows
the AWS condition-key list because AWS evaluates the trust policy. The condition
`verified_on` date lets an operator judge staleness; `nhi-blast version --data`
prints the age of every data file.

## What is deliberately not stored

- No credential values. The literal-credential heuristics store patterns, not hits;
  hits are reported as kind and length only.
- No personal data, repository contents or downloaded provider modules.
- No live AWS or GitHub API responses. The runtime makes no network calls.

## Research cache

`docs/research/_cache` contains raw reference pages captured while researching the
specification. It is development provenance, not runtime data, and is excluded from
source and binary distributions. Those pages remain subject to their publishers'
terms.

## Updating data

1. Check the primary source and record the date.
2. Change the YAML entry and keep `source`, `source_url` and `verified_on` accurate.
3. Add or adjust a behavioural test when the change affects evaluation.
4. Run `nhi-blast version --data` and the full gate.
5. Do not bulk-refresh `verified_on` without re-checking the facts.
