# Primary sources

This page records the external documents that platform facts were derived from. A
source is listed only if it was actually consulted during the research phase; the
data files under `src/nhi_blast/data/` name the source used for each individual
dataset.

## Sources used for platform data

| Source | Used for | Notes |
| --- | --- | --- |
| [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax) | Permissions scopes, trigger syntax, workflow structure | Referenced by `permission_scopes.yaml`. The fetched copy was truncated, so only the permission-scope list was used. |
| [GitHub Actions events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) | Trigger profiles: who can start an event, which ref is used, whether fork code runs | Referenced by `trigger_profiles.yaml`. |
| [GitHub OIDC concepts](https://docs.github.com/en/actions/concepts/security/openid-connect) | Available OIDC claims and subject construction | The original security-hardening URL redirected here. The fetched copy was truncated; claim behaviour that could not be confirmed is recorded as an assumption. |
| [GitHub Actions security hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions) | Mutable action references, literal credential handling, `pull_request_target` guidance | Referenced by `rules.yaml` and `credential_heuristics.yaml`. |
| [AWS IAM condition elements](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition.html) | Condition operators, `IfExists`, `Null`, multivalued behaviour | Used for the policy-evaluation semantics. |
| [AWS IAM condition keys for GitHub](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html) | Accepted GitHub OIDC provider claims | Referenced by `aws_github_condition_keys.yaml`. AWS and GitHub documentation disagree about custom claims; the data file records the disagreement and follows AWS. |
| [AWS Secrets Manager IAM reference](https://docs.aws.amazon.com/secretsmanager/latest/userguide/reference_iam-permissions.html) | Read and write actions for Secrets Manager sinks | Referenced by `sinks_catalog.yaml`. |
| [AWS IAM access-key rotation](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html) | Rotation hints for access keys | Referenced by `rotation_hints.yaml`. |
| [SARIF 2.1.0 specification](https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html) | Report structure and required fields | The vendored schema and the SARIF validation test use this specification. |
| [GitHub SARIF support](https://docs.github.com/en/code-security/reference/code-scanning/sarif-files/sarif-support) | GitHub code-scanning limits for SARIF output | Used for the 5,000-result cap and size considerations. |
| [docs/SPEC.md](../SPEC.md) | Normative product requirements | Extracted from the supplied project specification. See `docs/spec-source/README.md` for provenance and the completeness gap. |

The SSM Parameter Store, STS `AssumeRoleWithWebIdentity`, AWS policy-evaluation and
CSP references that informed implementation details are present in the working cache
described below. They are not reproduced here because the cache index does not record
a verified URL for every raw file; a file without a recorded URL is not treated as a
citation.

## Research cache

`docs/research/_cache/` contains the raw fetch output from the research phase
(68 files at the time of writing, dated 2026-10-25). It is working material:

- It may be truncated, formatted for reading or partially extracted.
- It is excluded from both the wheel and the sdist by the packaging configuration.
- It is not a citation record and does not ship with the tool.
- It contains no credential values and no private data.

One planned source, the GitHub changelog entry for immutable subject claims, could
not be fetched because its hostname resolved to a non-public address in the research
environment. Consequently, the repository's subject format (classic versus immutable)
is not treated as known: both formats are evaluated and `A-REPO-AGE` records the
uncertainty.

## How to update a source

1. Re-read the primary document. Do not rely on the cache.
2. Update the relevant data file and its `source_url` and `verified_on` fields.
3. If the semantics changed, update evaluation code and add a regression test.
4. Update `docs/data-provenance.md` and this page if the source list changed.
5. Never mark a source verified on a date when it was not actually read.
