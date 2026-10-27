# NHB-OIDC-003 — Repository-wide wildcard in subject

**Base severity:** HIGH · **Precision:** high · **Tags:** oidc, aws, wildcard

## What it detects

The trust policy's `sub` condition matches any branch, tag, pull-request run or
environment in one repository, such as `repo:acme/shop:*` or
`repo:acme/shop:ref:refs/heads/*`.

## Why it matters

Every workflow in the repository that can obtain an OIDC token may satisfy the
policy, including workflows added on short-lived branches by anyone with write
access. The role is therefore broader than the reviewed deployment workflow.

## Evidence

`DECLARED` policy text and `DERIVED` subject candidates. The graph records matching
workflow lines when they are present in the scan.

## Limits

Branch protection, environment protection rules and actor permissions are not
modelled. A repository-wide pattern can be acceptable in a repository where every
writer is trusted, but the files alone cannot establish that.

## Remediation

Pin `sub` to a specific environment or ref and constrain `aud`. If a reusable
workflow is the intended entrypoint, pin `job_workflow_ref` instead.

## Related

[NHB-OIDC-002](NHB-OIDC-002.md) · [NHB-OIDC-007](NHB-OIDC-007.md)
