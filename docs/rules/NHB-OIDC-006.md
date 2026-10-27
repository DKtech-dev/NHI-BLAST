# NHB-OIDC-006 — Dead condition key for AWS

**Base severity:** LOW · **Precision:** medium · **Tags:** oidc, aws, correctness

## What it detects

A trust condition uses a claim key outside the documented set AWS accepts for
`token.actions.githubusercontent.com`. Depending on the operator, the condition can
never be satisfied or can be silently ignored, so the analysis treats the statement
as failing closed.

## Why it matters

A policy that looks constrained may not be, or may block legitimate federation.
Both outcomes surprise operators during an incident.

## Evidence

`DECLARED` condition keys compared with
`src/nhi_blast/data/aws_github_condition_keys.yaml`, which records its source and
verification date.

## Limits

Cloud providers add condition keys over time. A key added after the data file's
`verified_on` date can produce a false positive. The condition-key data is printed
by `nhi-blast version --data`; re-verify against current AWS documentation before
acting.

## Remediation

Remove the unused key or move the constraint to a supported key such as `sub`,
`job_workflow_ref`, `ref` or `environment`.

## Related

[NHB-OIDC-004](NHB-OIDC-004.md) · [NHB-OIDC-007](NHB-OIDC-007.md)
